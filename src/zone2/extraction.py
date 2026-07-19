import json
import csv
import re
import time
import asyncio

from src.zone2.config import CSV_FIELDS, MAX_TEXT_CHARS, log
from src.zone2.client import llm_call, parse_json_response
from src.zone2.scraper import hybrid_scrape, _generate_alternate_urls, _is_low_quality_text
from src.zone2.embedding import filter_candidates, deduplicate_candidates
from src.prompts import PREFILTER_PROMPT, EXTRACTION_PROMPT_TEMPLATE


def truncate_text(text, max_chars=MAX_TEXT_CHARS):
    if len(text) <= max_chars:
        return text
    log.warning("Truncating text from %d to %d chars", len(text), max_chars)
    return text[:max_chars]


async def prefilter_candidate(model, indicator_id, indicator_data, candidate):
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
    """Scrape a URL using the hybrid async scraper.

    Falls back to alternate URLs if the initial scrape fails
    or returns low-quality content.
    """
    log.info("  Scraping: %s", url)
    text, source = await hybrid_scrape(url)
    if text and len(text) >= 200:
        log.info("  Result: %d chars via %s", len(text), source)
        return text

    log.warning("  Too short (%d chars, source=%s) — trying alternate URLs", len(text) if text else 0, source)
    for alt_url in _generate_alternate_urls(url):
        log.info("  Alternate: %s", alt_url)
        text2, source2 = await hybrid_scrape(alt_url)
        if text2 and len(text2) >= 200:
            log.info("  Alternate result: %d chars via %s", len(text2), source2)
            return text2

    return None


async def extract_clauses(model, indicator_id, indicator_data, scraped_text, country_display="Singapore"):
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        indicator_id=indicator_id,
        indicator_question=indicator_data["question"],
        extraction_instructions=indicator_data["extraction_instructions"],
        country_display=country_display,
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


def build_row(indicator_id, url, candidate_title, extracted, economy="", discovery_tag="NEW"):
    act_title = extracted.get("act_title") or candidate_title or ""
    coverage = extracted.get("coverage") or "Unknown"
    section = extracted.get("section_reference", "") or ""
    op_clause = extracted.get("operative_clause", "")
    interpretation = extracted.get("interpretation", "") or ""
    law_number = extracted.get("law_number_ref") or ""
    last_amended = extracted.get("last_amended") or ""
    location_ref = extracted.get("location_reference") or ""
    confidence = extracted.get("confidence") or ""

    impact = op_clause
    if section:
        impact = f"{section}: {impact}"
    if interpretation:
        impact = f"{impact}\nInterpretation: {interpretation}"

    pillar_id = indicator_id.split(".")[0]

    return {
        "Economy": economy,
        "Pillar_ID": pillar_id,
        "Indicator_ID": indicator_id,
        "Act_and_or_practice": act_title,
        "Law_Number_Ref": law_number,
        "Last_Amended": last_amended,
        "Coverage": coverage,
        "Article_Section": section,
        "Discovery_Tag": discovery_tag,
        "Location_Reference": location_ref,
        "Verbatim_Snippet": op_clause,
        "Mapping_Rationale": interpretation,
        "Impact_or_comments": impact,
        "Timeframe": extracted.get("timeframe", ""),
        "References": url,
        "Confidence": confidence,
    }


def _rank_candidates(candidates):
    scored = []
    for c in candidates:
        url = c.get("url", "").lower()
        title = c.get("title", "").lower()
        snippet = c.get("snippet", "").lower()

        score = c.get("relevance_score", 0) * 10

        if c.get("query_used") == "seed_url (curated)":
            score += 999
        elif "laws.sg/legislation/" in url:
            score += 50
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


def _short(text: str, n: int = 55) -> str:
    return text[:n] + "..." if len(text) > n else text


async def process_indicator(
    model, indicator_id, indicator_data,
    candidates, max_candidates, rate_delay,
    economy="", country_display="Singapore",
):
    """Process all candidates for one indicator and return (rows, stats)."""
    title = indicator_data["name"]
    log.info("─" * 55)
    log.info("  [%s] %s", indicator_id, title)
    log.info("─" * 55)

    # Embedding pre-filter: batch similarity scoring (replaces most LLM pre-filter calls)
    candidates = filter_candidates(indicator_id, indicator_data, candidates, top_n=max_candidates * 2)

    # Semantic dedup: remove near-duplicate candidates
    candidates = deduplicate_candidates(candidates)

    ranked = _rank_candidates(candidates)
    if ranked and ranked[0] is not candidates[0]:
        log.info("  >> Re-ranked: '%s' promoted to top", _short(ranked[0].get("title", "")))

    rows = []
    stats = {"prefiltered": 0, "scraped": 0, "extracted": 0}

    for cand in ranked[:max_candidates]:
        url = cand["url"]
        label = _short(cand.get("title", ""))
        short_u = _short(url, 65)

        is_seed = cand.get("query_used") == "seed_url (curated)"
        if is_seed:
            pass
        elif cand.get("_embedding_score", 1.0) >= 0.25:
            pass
        else:
            relevant = await prefilter_candidate(
                model, indicator_id, indicator_data, cand,
            )
            if not relevant:
                log.info("  x %s  %s", label, short_u)
                continue

        stats["prefiltered"] += 1
        log.info("  o %s  %s", label, short_u)

        await asyncio.sleep(rate_delay * 0.5)

        text = await scrape_url(url)
        if not text:
            continue

        stats["scraped"] += 1
        await asyncio.sleep(rate_delay * 0.5)

        extracted = await extract_clauses(
            model, indicator_id, indicator_data, text,
            country_display=country_display,
        )
        if not extracted:
            log.info("      -> Extraction: no relevant clause found")
            await asyncio.sleep(rate_delay)
            continue

        stats["extracted"] += 1
        ref = extracted.get("section_reference") or "?"
        act = extracted.get("act_title") or "?"
        log.info("      -> %s  %s", ref, _short(act))

        discovery_tag = cand.get("discovery_tag", "NEW")
        row = build_row(indicator_id, url, cand.get("title", ""), extracted,
                       economy=economy, discovery_tag=discovery_tag)
        rows.append(row)

        await asyncio.sleep(rate_delay)

    log.info("  -> %d row(s) for %s", len(rows), indicator_id)
    return rows, stats
