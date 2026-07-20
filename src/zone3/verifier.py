"""
Blind Citation Verifier — Zone 3 quality gate for Zone 2 extraction.

Uses LLM (Alibaba/Gemini/Ollama fallback chain) to independently verify
every citation by re-fetching the document and comparing the claimed
verbatim snippet against the actual text of the cited section.
"""

import asyncio
import csv
import json
import re
from difflib import SequenceMatcher
from typing import Optional

from src.zone2.client import llm_call
from src.zone2.config import log
from src.zone2.scraper import hybrid_scrape

VERIFICATION_SYSTEM_PROMPT = """You are a legal citation verifier. Your job is to verify whether a claimed legal clause actually appears in a given document.

You will be given:
1. A section reference (e.g. "Section 26(1)", "APP 8.1", "Seksyen 129")
2. A claimed verbatim snippet — text the extraction pipeline says comes from that section
3. The full document text

You must:
1. Locate the cited section in the document (search for the section number, part, article, etc.)
2. Extract the actual verbatim text of that section
3. Compare the claimed snippet against the actual text
4. Return a JSON verdict

Rules for comparison:
- PASS if the claimed snippet is substantially the same as the actual text (minor whitespace/formatting differences are OK)
- FAIL if the claimed snippet says something different from the actual text, or the section doesn't exist in the document
- NEEDS_REVIEW if you cannot determine (e.g. document is too short, section reference is ambiguous)

Return ONLY valid JSON with these fields:
{
  "status": "PASS" | "FAIL" | "NEEDS_REVIEW",
  "actual_text": "The verbatim text found at the cited section (max 500 chars, or empty if not found)",
  "explanation": "Brief reason for the verdict"
}"""


def _short(text: str, n: int = 55) -> str:
    return text[:n] + "..." if len(text) > n else text


def _short_err(err: Exception) -> str:
    return str(err)[:200]


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().strip())


def _fuzzy_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _extract_section_ref(row: dict) -> Optional[str]:
    article_section = row.get("Article_Section", "")
    if article_section and article_section.strip():
        return article_section.strip()

    impact = row.get("Impact_or_comments", "")
    patterns = [
        r"(Section|S\.|§)\s*([0-9]+[A-Z]*(?:\([0-9]+\))?)",
        r"(Article|Art\.)\s*([0-9]+(?:\([0-9]+\))?)",
        r"(Chapter|Ch\.)\s*([0-9]+)",
        r"(Part)\s+([IVXLCDM]+)",
        r"(Division)\s+([0-9]+)",
        r"(Schedule)\s+([0-9]+)",
        r"(APP)\s+([0-9]+)",
        r"(Clause|cl\.)\s*([0-9]+(?:[\.\d]+)?)",
        r"(Regulation|Reg\.)\s*([0-9]+)",
        r"(Seksyen|Perkara|Perenggan|Bahagian)\s+([0-9A-Za-z]+)",
        r"(s\.)\s*([0-9]+(?:\([0-9a-z]+\))?)",
        r"\b([0-9]+)\.\s*Section\b",
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
    patterns.append(re.sub(r"\s+", r"\\s+", re.escape(ref)))

    num_part = re.sub(r"[^0-9()IVXLCDMivxlcdm]", "", ref)
    alpha_part = re.sub(r"[^A-Za-z]", "", ref).lower()
    num = re.sub(r"[^0-9()]", "", ref)

    if num:
        patterns.append(r"Section\s+" + re.escape(num))
        patterns.append(r"S\.\s*" + re.escape(num))
        patterns.append(r"s\.\s*" + re.escape(num))
        patterns.append(r"s\s+" + re.escape(num))
        patterns.append(r"\b" + re.escape(num) + r"\b")
        main_num = re.sub(r"\(.*\)", "", num)
        sub = re.search(r"\((\d+)\)", num)
        if main_num and sub:
            subsection = sub.group(1)
            patterns.append(r"\b" + re.escape(main_num) + r"\s*\.\s*\(" + re.escape(subsection) + r"\)")
            patterns.append(r"\b" + re.escape(main_num) + r"\s*\.\s*\S?\s*\(" + re.escape(subsection) + r"\)")
            patterns.append(r"\b" + re.escape(main_num) + r"\." + r"\s*\S?\s*\(" + re.escape(subsection) + r"\)")
            patterns.append(r"\b" + re.escape(main_num) + r"\." + r"\s*\(" + re.escape(subsection) + r"\)")

    if "app" in alpha_part:
        num_only = re.sub(r"[^0-9]", "", ref)
        if num_only:
            patterns.append(r"APP\s+" + re.escape(num_only))
            patterns.append(r"Australian\s+Privacy\s+Principle\s+" + re.escape(num_only))

    if "part" in alpha_part:
        roman = re.sub(r"[^IVXLCDMivxlcdm]", "", ref).upper()
        if roman:
            patterns.append(r"Part\s+" + re.escape(roman))
            patterns.append(r"PART\s+" + re.escape(roman))

    return patterns


def _find_next_section(text: str, start: int) -> int:
    section_heads = re.finditer(
        r"(?:^|\n)\s*(Section\s+\d+|S\.\s*\d+|s\.\s*\d+|s\s+\d+|Part\s+[IVXLCDM\d]+|Article\s+\d+|APP\s+\d+|Clause\s+\d+|Division\s+\d+|Schedule\s+\d+|Seksyen\s+\d+|Bahagian\s+\w+|Perkara\s+\d+|Chapter\s+\d+)",
        text[start + 120:],
        re.IGNORECASE,
    )
    for m in section_heads:
        return start + 120 + m.start()
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
    text = re.sub(r"^(Section\s+\S+|S\.\s*\S+|s\.\s*\S+|Article\s+\S+|Art\.\s*\S+|APP\s+\d+|Clause\s+\S+|Seksyen\s+\S+|Perkara\s+\S+|Perenggan\s+\S+)\s*[:\-–—]?\s*", "", text, flags=re.IGNORECASE)
    return text


# ── Document fetching ─────────────────────────────────────────────

async def fetch_document(url: str) -> Optional[str]:
    text, source = await hybrid_scrape(url)
    if text and len(text) >= 200:
        return text
    log.warning("  hybrid_scrape returned nothing (%s) for %s", source, url)
    return None


# ── LLM-based verification (primary) ──────────────────────────────

VERIFICATION_USER_PROMPT_TEMPLATE = """Section Reference: {section_ref}

Claimed Verbatim Snippet:
{claimed_text}

Document Text:
{document_text}

Return ONLY valid JSON with fields: status ("PASS"/"FAIL"/"NEEDS_REVIEW"), actual_text, explanation."""


async def _llm_verify(document: str, section_ref: str, claimed_text: str, model: str) -> Optional[dict]:
    if not claimed_text or not section_ref:
        return None

    truncated = document[:400000]
    user_prompt = VERIFICATION_USER_PROMPT_TEMPLATE.format(
        section_ref=section_ref,
        claimed_text=claimed_text[:2000],
        document_text=truncated,
    )

    try:
        result = await llm_call(model, VERIFICATION_SYSTEM_PROMPT, user_prompt, max_tokens=800, retries=2)
        if not result:
            return None

        raw = result.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
        raw = re.sub(r"\s*```$", "", raw)

        parsed = json.loads(raw)
        if parsed.get("status") in ("PASS", "FAIL", "NEEDS_REVIEW"):
            return parsed
        return None
    except (json.JSONDecodeError, AttributeError) as e:
        log.warning("  LLM verify JSON parse failed: %s", _short_err(e))
        return None


# ── Regex-based verification (fallback) ───────────────────────────

def _regex_verify(document: str, section_ref: str, claimed_text: str) -> dict:
    actual = _locate_section_deterministic(document, section_ref)
    if not actual:
        return {"status": "FAIL", "actual_text": "", "explanation": f"Section '{section_ref}' not found in document via regex"}

    n_actual = _normalise(actual)
    n_claimed = _normalise(claimed_text)

    if n_actual == n_claimed:
        return {"status": "PASS", "actual_text": actual[:800], "explanation": "Text matches claim (exact)"}
    elif _fuzzy_ratio(n_actual, n_claimed) > 0.85:
        return {"status": "PASS", "actual_text": actual[:800], "explanation": "Text matches claim (fuzzy)"}
    elif n_claimed in n_actual or n_actual in n_claimed:
        return {"status": "PASS", "actual_text": actual[:800], "explanation": "Claim is subset of actual text"}
    else:
        preview_a = actual[:150].replace("\n", " ")
        preview_c = claimed_text[:150].replace("\n", " ")
        return {
            "status": "FAIL",
            "actual_text": actual[:800],
            "explanation": f"Text mismatch. Actual: '{preview_a}...' vs Claimed: '{preview_c}...'",
        }


# ── Main verification logic ───────────────────────────────────────

async def verify_row(
    row: dict,
    model: str = "alibaba:qwen3.7-plus,gemini,ollama:gemma4",
    retries: int = 3,
) -> dict:
    url = (row.get("References") or "").strip()
    if not url:
        url = (row.get("Source_URL") or "").strip()
    section_ref = _extract_section_ref(row)
    claimed_text = (row.get("Verbatim_Snippet") or "").strip()
    if not claimed_text:
        claimed_text = _get_claim_text(row)

    row["Verification_Status"] = "NEEDS_REVIEW"
    row["Verification_Actual_Text"] = ""
    row["Verification_Notes"] = ""

    if not url:
        row["Verification_Notes"] = "No URL provided"
        return row
    if not section_ref:
        row["Verification_Notes"] = "No section reference found"
        return row
    if not claimed_text:
        row["Verification_Notes"] = "No claimed text to verify"
        return row

    for attempt in range(retries):
        try:
            doc = await fetch_document(url)
            if not doc or len(doc) < 200:
                row["Verification_Status"] = "URL_BROKEN"
                row["Verification_Notes"] = f"Could not fetch content from {url}"
                return row

            # Primary: LLM-based verification
            llm_result = await _llm_verify(doc, section_ref, claimed_text, model)
            if llm_result:
                row["Verification_Status"] = llm_result["status"]
                row["Verification_Actual_Text"] = (llm_result.get("actual_text") or "")[:800]
                row["Verification_Notes"] = llm_result.get("explanation", "")
                return row

            # Fallback: regex-based verification
            log.info("  LLM verify unavailable, falling back to regex")
            result = _regex_verify(doc, section_ref, claimed_text)
            row["Verification_Status"] = result["status"]
            row["Verification_Actual_Text"] = result.get("actual_text", "")[:800]
            row["Verification_Notes"] = result.get("explanation", "")
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
    model: str = "alibaba:qwen3.7-plus,gemini,ollama:gemma4",
    retries: int = 3,
) -> None:
    with open(input_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        log.error("No rows to verify")
        return

    log.info("Verifying %d rows with model %s", len(rows), model)

    verified = []
    for i, row in enumerate(rows):
        ind = row.get("Indicator_ID", "?")
        act = row.get("Act_and_or_practice", "?")
        ref = row.get("Article_Section", "") or row.get("Impact_or_comments", "")[:40]
        log.info("  [%d/%d] %s | %s | %s", i + 1, len(rows), ind, _short(act, 40), _short(ref, 40))
        vr = await verify_row(row, model, retries)
        status = vr.get("Verification_Status", "?")
        icon = {"PASS": "[OK]", "FAIL": "[X]", "NEEDS_REVIEW": "[?]", "URL_BROKEN": "[X]"}.get(status, "[?]")
        log.info("    %s %s", icon, status)
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

    log.info("")
    log.info("=" * 45)
    log.info("  VERIFICATION COMPLETE")
    log.info("  %d rows | PASS: %d | FAIL: %d | ?: %d | BROKEN: %d",
             len(verified), counts["PASS"], counts["FAIL"],
             counts["NEEDS_REVIEW"], counts["URL_BROKEN"])
    log.info("  Output: %s", output_path)
    log.info("=" * 45)
