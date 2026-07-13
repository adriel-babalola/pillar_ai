import json
import csv
import re
import time
import asyncio

from src.zone2.config import CSV_FIELDS, MAX_TEXT_CHARS, log
from src.zone2.client import llm_call, parse_json_response
from src.zone2.scraper import hybrid_scrape
from src.prompts import PREFILTER_PROMPT, EXTRACTION_PROMPT_TEMPLATE


def truncate_text(text, max_chars=MAX_TEXT_CHARS):
    if len(text) <= max_chars:
        return text
    log.warning("Truncating text from %d to %d chars", len(text), max_chars)
    return text[:max_chars]


async def prefilter_candidate(model, indicator_id, indicator_data, candidate):
    """Use LLM to check if a candidate URL is worth scraping."""
    title = candidate.get("title", "")
    snippet = candidate.get("snippet", "")

    prompt = PREFILTER_PROMPT.format(
        indicator_id=indicator_id,
        indicator_question=indicator_data["question"],
        title=title[:500],
        snippet=snippet[:2000],
    )

    system = (
        "You are a precise legal research assistant. "
        "Always respond with valid JSON and nothing else."
    )

    # Try up to 3 times with empty-response retries
    for _ in range(3):
        result = await llm_call(model, system, prompt, max_tokens=512, retries=2)
        if result:
            parsed = parse_json_response(result)
            if parsed is not None:
                return parsed.get("relevant", True)
        log.warning("  Pre-filter: empty/invalid response, retrying...")
        await asyncio.sleep(2)

    log.warning("  Pre-filter: LLM consistently returned empty — skipping candidate")
    return False


async def scrape_url(url):
    """Scrape a URL using the hybrid 3-tier async scraper."""
    log.info("  Scraping: %s", url)
    text, source = await hybrid_scrape(url)
    if not text or len(text) < 200:
        log.warning("  Too short (%d chars, source=%s) — skipping", len(text) if text else 0, source)
        return None
    log.info("  Result: %d chars via %s", len(text), source)
    return text


async def extract_clauses(model, indicator_id, indicator_data, scraped_text):
    """Send scraped text to LLM and extract structured information."""
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        indicator_id=indicator_id,
        indicator_question=indicator_data["question"],
        extraction_instructions=indicator_data["extraction_instructions"],
        scraped_text=truncate_text(scraped_text),
    )

    system = (
        "You are an expert legal researcher specialising in digital trade law. "
        "You extract precise, verbatim legal provisions and output them as JSON. "
        "Never paraphrase legal text. Return only valid JSON, no markdown fences."
    )

    result = await llm_call(model, system, prompt, max_tokens=1000, retries=3)
    if not result:
        return None

    parsed = parse_json_response(result)
    if parsed is None:
        log.warning("  JSON parse failed on LLM output")
        return None
    if parsed.get("operative_clause") is None:
        log.warning("  LLM returned null operative_clause")
        return None
    return parsed


def build_row(indicator_id, url, candidate_title, extracted):
    """Map LLM extraction output to CSV columns."""
    act_title = extracted.get("act_title") or candidate_title or ""
    coverage = extracted.get("coverage") or "Unknown"
    section = extracted.get("section_reference", "") or ""
    op_clause = extracted.get("operative_clause", "")
    interpretation = extracted.get("interpretation", "") or ""

    impact = op_clause
    if section:
        impact = f"{section}: {impact}"
    if interpretation:
        impact = f"{impact}\nInterpretation: {interpretation}"

    pillar_id = indicator_id.split(".")[0]

    return {
        "Pillar_ID": pillar_id,
        "Indicator_ID": indicator_id,
        "Act_and_or_practice": act_title,
        "Coverage": coverage,
        "Impact_or_comments": impact,
        "Timeframe": extracted.get("timeframe", ""),
        "References": url,
    }


def _rank_candidates(candidates):
    """Re-rank candidates: promote legal document URLs, demote generic portals."""
    scored = []
    for c in candidates:
        url = c.get("url", "").lower()
        title = c.get("title", "").lower()
        snippet = c.get("snippet", "").lower()

        score = c.get("relevance_score", 0) * 10

        if c.get("query_used") == "seed_url (curated)":
            score += 999
        elif "sso.agc.gov.sg/act/" in url:
            score += 50
        elif "sso.agc.gov.sg" in url:
            score += 30
        elif "legislation.gov" in url:
            score += 40
        elif "/act/" in url or "/acts/" in url:
            score += 25

        official_domains = [
            "pdpc.gov.sg", "oaic.gov.au", "pdp.gov.my",
            "csa.gov.sg", "imda.gov.sg", "mas.gov.sg",
            "mti.gov.sg", "dfat.gov.au", "miti.gov.my",
            "bnm.gov.my", "acma.gov.au", "mcmc.gov.my",
        ]
        if any(d in url for d in official_domains):
            score += 20

        if any(w in title for w in ["act", "regulation", "order", "rule", "code of practice"]):
            score += 15
        if any(w in snippet for w in ["personal data", "data protection", "transfer", "privacy"]):
            score += 10

        penalise_domains = [
            "mom.gov.sg", "gov.sg/explainers", "gov.sg/about", "sgdi.gov.sg",
            "pmo.gov.sg", "search.gov.sg", "file.gov.sg", "singstat.gov.sg",
            "ica.gov.sg", "go.gov.sg/", "ask.gov.sg",
        ]
        if any(d in url for d in penalise_domains):
            score -= 20
        if "work permit" in title or "employment" in title or "work pass" in title:
            score -= 15
        if len(title) < 20:
            score -= 5

        scored.append((score, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored]


async def process_indicator(
    model, indicator_id, indicator_data,
    candidates, max_candidates, rate_delay,
):
    """Process all candidates for one indicator and return (rows, stats)."""
    log.info("  [%s] %s", indicator_id, indicator_data["name"])

    ranked = _rank_candidates(candidates)
    if ranked and ranked[0] is not candidates[0]:
        log.info("    Re-ranked: '%s' promoted to top", ranked[0].get("title", "")[:60])

    rows = []
    stats = {"prefiltered": 0, "scraped": 0, "extracted": 0}

    for cand in ranked[:max_candidates]:
        url = cand["url"]
        log.info("    URL: %s", url)

        relevant = await prefilter_candidate(
            model, indicator_id, indicator_data, cand,
        )
        if not relevant:
            log.info("      Pre-filter: SKIP (not relevant)")
            continue

        stats["prefiltered"] += 1
        log.info("      Pre-filter: PASS")
        await asyncio.sleep(rate_delay * 0.5)

        scraped = await scrape_url(url)
        if not scraped:
            continue

        stats["scraped"] += 1
        log.info("      Scraped: %d chars", len(scraped))
        await asyncio.sleep(rate_delay * 0.5)

        extracted = await extract_clauses(
            model, indicator_id, indicator_data, scraped,
        )
        if not extracted:
            log.info("      Extraction: no relevant clause found")
            await asyncio.sleep(rate_delay)
            continue

        stats["extracted"] += 1
        ref = extracted.get("section_reference") or "?"
        log.info("      Extracted: %s — %s", ref, extracted.get("act_title", "?")[:60])

        row = build_row(indicator_id, url, cand.get("title", ""), extracted)
        rows.append(row)

        await asyncio.sleep(rate_delay)

    log.info("    %d row(s) for %s", len(rows), indicator_id)
    return rows, stats
