"""
Search-engine-based discovery (DuckDuckGo).

Used alongside Wikipedia discovery to find official legal sources.
Returns candidates in the same format as discovery_wikipedia.py.
"""

import logging
import re
import urllib.parse
from typing import Optional

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

from src.zone1.config import COUNTRY_CONFIG
from src.zone1.utils import is_official_url, relevance_score
from src.zone1.discovery_wikipedia import _classify_source_type, _extract_citation

log = logging.getLogger(__name__)

DDGS_TIMEOUT = 20
DDGS_MAX_RESULTS = 15


def _search_ddg(query: str, limit: int = 10) -> list[dict]:
    """Run a DuckDuckGo text search. Returns list of {title, url, snippet}."""
    try:
        with DDGS(timeout=DDGS_TIMEOUT) as ddgs:
            results = list(ddgs.text(query, max_results=max(limit, DDGS_MAX_RESULTS)))
            out = []
            for r in results:
                title = (r.get("title") or "").strip()
                url = (r.get("href") or "").strip()
                snippet = (r.get("body") or "").strip()
                if title and url:
                    out.append({"title": title, "url": url, "snippet": snippet, "source": "duckduckgo"})
            return out
    except Exception as e:
        log.warning("  DDG search failed for %r: %s", query[:80], e)
        return []


def _generate_search_queries(
    indicator_id: str,
    keywords: list[str],
    country_key: str,
) -> list[str]:
    """Build targeted search queries from indicator keywords + country."""
    display = COUNTRY_CONFIG[country_key]["display"]
    sf = COUNTRY_CONFIG[country_key]["site_filter"]
    queries = [f"{sf} {k} {display}" for k in keywords[:3]]
    queries.append(f"{sf} {indicator_id} {display} legislation")
    return queries


async def search_indicator(
    indicator_id: str,
    queries: list[str],
    country: str,
    limit: int,
    cache: dict[str, list],
    keywords: list[str],
    crawler,
    inventory_urls: set[str] | None = None,
) -> list[dict]:
    """
    Entry point — DuckDuckGo search for a single indicator.
    
    Returns same format as discovery_wikipedia.search_indicator():
    list of {indicator, title, url, snippet, query_used, relevance_score, source, ...}
    """
    seen_urls = set(inventory_urls) if inventory_urls else set()
    candidates = []
    search_queries = _generate_search_queries(indicator_id, keywords, country)

    for q in search_queries:
        results = _search_ddg(q, limit=limit)
        for res in results:
            url = res["url"]
            title = res["title"]
            snippet = res["snippet"]

            if not url or url in seen_urls:
                continue
            if not is_official_url(url, country):
                continue

            seen_urls.add(url)
            score = relevance_score(f"{title} {snippet}", keywords)

            src_type = _classify_source_type(title)
            citation = _extract_citation(title, url)

            candidates.append({
                "indicator": indicator_id,
                "title": title,
                "url": url,
                "snippet": snippet,
                "query_used": f"duckduckgo:{q[:80]}",
                "relevance_score": round(score, 3),
                "source": "discovery",
                "source_type": src_type,
                "citation": citation,
                "status": "Pending",
            })

    log.info("  DDG found %d candidates for %s", len(candidates), indicator_id)
    return candidates
