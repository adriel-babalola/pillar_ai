"""
Blind Citation Verifier — Instance 3 quality gate for Zone 2 extraction.

Receives ONLY the URL and section reference from each CSV row,
independently re-fetches the document, locates the cited section,
and compares the actual text against the claimed snippet.
"""

import asyncio
import csv
import re
from difflib import SequenceMatcher
from typing import Optional

from openai import AsyncOpenAI

from src.zone2.config import (
    OPENROUTER_BASE, OPENROUTER_API_KEY,
    ALIBABA_API_KEY, ALIBABA_BASE,
    log,
)
from src.zone2.scraper import hybrid_scrape


def _short_err(err: Exception) -> str:
    return str(err)[:200]


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().strip())


def _fuzzy_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _extract_section_ref(row: dict) -> Optional[str]:
    impact = row.get("Impact_or_comments", "")
    patterns = [
        r"(Section|S\.|§)\s*([0-9]+[A-Z]*(?:\([0-9]+\))?)",
        r"(Article|Art\.)\s*([0-9]+(?:\([0-9]+\))?)",
        r"(Chapter|Ch\.)\s*([0-9]+)",
        r"(Part)\s+([IVXLCDM]+)",
        r"(APP)\s+([0-9]+)",
        r"(Clause|cl\.)\s*([0-9]+(?:[\.\d]+)?)",
        r"(Regulation|Reg\.)\s*([0-9]+)",
        r"(Seksyen|Perkara|Perenggan|Bahagian)\s+([0-9A-Za-z]+)",
    ]
    for prefix_pat, num_pat in [p if isinstance(p, tuple) else (p, p) for p in patterns]:
        m = re.search(prefix_pat, impact, re.IGNORECASE)
        if m:
            return m.group(0)
    m = re.search(r"Section\s+([0-9]+(?:\([0-9a-z]+\))?)", impact, re.IGNORECASE)
    if m:
        return m.group(0)
    return None


def _generate_section_patterns(section_ref: str) -> list[str]:
    ref = section_ref.strip()
    patterns = [re.escape(ref)]
    num = re.sub(r"[^0-9()]", "", ref)
    if num:
        patterns.append(r"Section\s+" + re.escape(num))
        patterns.append(r"S\.\s*" + re.escape(num))
        patterns.append(r"s\.\s*" + re.escape(num))
        patterns.append(r"\b" + re.escape(num) + r"\b")
        main_num = re.sub(r"\(.*\)", "", num)
        sub = re.search(r"\((\d+)\)", num)
        if main_num and sub:
            subsection = sub.group(1)
            patterns.append(r"\b" + re.escape(main_num) + r"\." + r"\s*\S?\s*\(" + re.escape(subsection) + r"\)")
            patterns.append(r"\b" + re.escape(main_num) + r"\." + r"\s*\(" + re.escape(subsection) + r"\)")
    return patterns


def _find_next_section(text: str, start: int) -> int:
    section_heads = re.finditer(
        r"(?:^|\n)\s*(Section\s+\d+|S\.\s*\d+|s\.\s*\d+|Part\s+[IVXLCDM]+|Article\s+\d+|APP\s+\d+|Clause\s+\d+|Division\s+\d+|Schedule\s+\d+|Seksyen\s+\d+|Bahagian\s+\w+|Perkara\s+\d+)",
        text[start + 80:],
        re.IGNORECASE,
    )
    for m in section_heads:
        return start + 80 + m.start()
    return len(text)


def _locate_section_deterministic(document: str, section_ref: str) -> Optional[str]:
    patterns = _generate_section_patterns(section_ref)
    for pat in patterns:
        for m in re.finditer(pat, document, re.IGNORECASE):
            start = m.start()
            end = _find_next_section(document, start)
            chunk = document[start:end].strip()
            if len(chunk) > 20:
                return chunk
    num = re.sub(r"[^0-9]", "", section_ref)
    for main_num in [num, re.sub(r"\(.*\)", "", num)]:
        if not main_num:
            continue
        for m in re.finditer(rf"\b{main_num}\b", document):
            start = max(0, m.start() - 300)
            end = min(len(document), m.end() + 800)
            chunk = document[start:end].strip()
            if 50 < len(chunk) < 5000:
                return chunk
    return None


def _get_claim_text(row: dict) -> str:
    impact = row.get("Impact_or_comments", "")
    text = impact.split("Interpretation:", 1)[0].strip() if "Interpretation:" in impact else impact
    # Strip leading section reference like "Section 26(1):" or "Section 26(1) - "
    text = re.sub(r"^(Section\s+\S+|S\.\s*\S+|s\.\s*\S+|Article\s+\S+|Art\.\s*\S+|APP\s+\d+|Clause\s+\S+|Seksyen\s+\S+|Perkara\s+\S+|Perenggan\s+\S+)\s*[:\-–—]?\s*", "", text, flags=re.IGNORECASE)
    return text


# ── Document fetching ─────────────────────────────────────────────

async def fetch_document(url: str) -> Optional[str]:
    """Reuse Zone 2 scraper with its SSO map, Playwright, and PDF fallback."""
    text, source = await hybrid_scrape(url)
    if text and len(text) >= 200:
        return text
    log.warning("  hybrid_scrape returned nothing (%s) for %s", source, url)
    return None


# ── LLM-assisted section location (fallback) ──────────────────────

async def _llm_locate_section(document: str, section_ref: str, model: str, api_key: str, base_url: str) -> Optional[str]:
    if not api_key:
        return None
    prompt = (
        f"You are a legal document parser. Find the exact text of {section_ref} "
        f"in the document below. Return ONLY the verbatim text of that section. "
        f"If not found, return 'NOT_FOUND'.\n\n---\n{document[:12000]}"
    )
    try:
        client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=2000,
        )
        text = (resp.choices[0].message.content or "").strip()
        if text == "NOT_FOUND" or len(text) < 15:
            return None
        return text
    except Exception as e:
        log.warning("  LLM locate fallback failed: %s", _short_err(e))
        return None


# ── Main verification logic ───────────────────────────────────────

async def verify_row(
    row: dict,
    model: str,
    api_key: str,
    base_url: str,
    retries: int = 3,
) -> dict:
    url = (row.get("References") or "").strip()
    section_ref = _extract_section_ref(row)
    claimed_text = _get_claim_text(row)

    row["Verification_Status"] = "NEEDS_REVIEW"
    row["Verification_Actual_Text"] = ""
    row["Verification_Notes"] = ""

    if not url:
        row["Verification_Notes"] = "No URL provided"
        return row
    if not section_ref:
        row["Verification_Notes"] = "No section reference found in Impact_or_comments"
        return row

    for attempt in range(retries):
        try:
            doc = await fetch_document(url)
            if not doc or len(doc) < 200:
                row["Verification_Status"] = "URL_BROKEN"
                row["Verification_Notes"] = f"Could not fetch content from {url}"
                return row

            actual = _locate_section_deterministic(doc, section_ref)
            if not actual:
                actual = await _llm_locate_section(doc, section_ref, model, api_key, base_url)
            if not actual:
                row["Verification_Status"] = "FAIL"
                row["Verification_Actual_Text"] = ""
                row["Verification_Notes"] = f"Section '{section_ref}' not found in document"
                return row

            row["Verification_Actual_Text"] = actual[:800]

            n_actual = _normalise(actual)
            n_claimed = _normalise(claimed_text)

            if n_actual == n_claimed:
                row["Verification_Status"] = "PASS"
                row["Verification_Notes"] = "Text matches claim"
            elif _fuzzy_ratio(n_actual, n_claimed) > 0.85:
                row["Verification_Status"] = "PASS"
                row["Verification_Notes"] = "Text matches claim (fuzzy)"
            elif n_claimed in n_actual or n_actual in n_claimed:
                row["Verification_Status"] = "PASS"
                row["Verification_Notes"] = "Claim is subset of actual text"
            else:
                row["Verification_Status"] = "FAIL"
                preview_a = actual[:150].replace("\n", " ")
                preview_c = claimed_text[:150].replace("\n", " ")
                row["Verification_Notes"] = (
                    f"Text mismatch. Actual: '{preview_a}...' vs Claimed: '{preview_c}...'"
                )
            return row

        except Exception as e:
            log.warning("  Verify attempt %d/%d failed: %s", attempt + 1, retries, _short_err(e))
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)

    row["Verification_Status"] = "NEEDS_REVIEW"
    row["Verification_Notes"] = f"Verification error after {retries} attempts"
    return row


async def verify_csv(
    input_path: str,
    output_path: str,
    model: str = "alibaba:qwen3.7-plus",
    retries: int = 3,
) -> None:
    with open(input_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        log.error("No rows to verify")
        return

    log.info("Verifying %d rows with model %s", len(rows), model)

    model_name = model.split(":", 1)[1] if ":" in model else model
    if model.startswith("alibaba:"):
        api_key, base_url = ALIBABA_API_KEY, ALIBABA_BASE
    else:
        api_key, base_url = OPENROUTER_API_KEY, OPENROUTER_BASE

    verified = []
    for i, row in enumerate(rows):
        log.info("  [%d/%d] %s", i + 1, len(rows), row.get("References", ""))
        vr = await verify_row(row, model_name, api_key, base_url, retries)
        verified.append(vr)
        await asyncio.sleep(1)

    fieldnames = list(rows[0].keys())
    for col in ["Verification_Status", "Verification_Actual_Text", "Verification_Notes"]:
        if col not in fieldnames:
            fieldnames.append(col)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(verified)

    counts = {"PASS": 0, "FAIL": 0, "NEEDS_REVIEW": 0, "URL_BROKEN": 0}
    for r in verified:
        s = r.get("Verification_Status", "NEEDS_REVIEW")
        counts[s] = counts.get(s, 0) + 1

    log.info("=" * 45)
    log.info("  VERIFICATION COMPLETE")
    log.info("  PASS:         %d", counts["PASS"])
    log.info("  FAIL:         %d", counts["FAIL"])
    log.info("  NEEDS_REVIEW: %d", counts["NEEDS_REVIEW"])
    log.info("  URL_BROKEN:   %d", counts["URL_BROKEN"])
    log.info("  Saved: %s", output_path)
    log.info("=" * 45)
