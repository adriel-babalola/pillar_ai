"""
Search-engine-based discovery (DuckDuckGo).

Used alongside Wikipedia discovery to find official legal sources.
Returns candidates in the same format as discovery_wikipedia.py.
"""

import logging
import re
import urllib.parse
from html.parser import HTMLParser

import requests as std_requests

from src.zone1.config import COUNTRY_CONFIG
from src.zone1.utils import is_official_url, relevance_score
from src.zone1.discovery_wikipedia import _classify_source_type, _extract_citation

log = logging.getLogger(__name__)


DDG_TIMEOUT = 8


def _ddg_url(raw: str) -> str:
    """Extract the real URL from a DuckDuckGo redirect link."""
    m = re.search(r"uddg=([^&]+)", raw)
    if m:
        return urllib.parse.unquote(m.group(1))
    return raw


class _DDGResultParser(HTMLParser):
    """Minimal HTML parser for DuckDuckGo /html/ results."""

    def __init__(self):
        super().__init__()
        self.results = []
        self._in_result = False
        self._reading_title = False
        self._reading_snippet = False
        self._current = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        cls = attrs.get("class", "")
        if tag == "a" and "result__a" in cls:
            self._reading_title = True
            self._current["url"] = _ddg_url(attrs.get("href", ""))
        elif tag == "a" and "result__snippet" in cls:
            self._reading_snippet = True
        elif tag == "div" and "result__body" in cls:
            self._in_result = True
            self._current = {"title": "", "url": "", "snippet": ""}

    def handle_endtag(self, tag):
        if tag == "a" and self._reading_title:
            self._reading_title = False
        if tag == "a" and self._reading_snippet:
            self._reading_snippet = False
        if tag == "div" and self._in_result:
            self._in_result = False
            if self._current.get("title") and self._current.get("url"):
                self.results.append(self._current)

    def handle_data(self, data):
        stripped = data.strip()
        if not stripped:
            return
        if self._reading_title and not self._reading_snippet:
            self._current["title"] += " " + stripped
        if self._reading_snippet:
            self._current["snippet"] += " " + stripped


def _search_ddg(query: str, limit: int = 5) -> list[dict]:
    """Run a DuckDuckGo HTML search directly. Returns list of {title, url, snippet}."""
    try:
        resp = std_requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
            timeout=DDG_TIMEOUT,
        )
        resp.raise_for_status()
        parser = _DDGResultParser()
        parser.feed(resp.text)
        return parser.results[:limit]
    except Exception:
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
                "discovery_tag": "NEW",
                "source_type": src_type,
                "citation": citation,
                "status": "Pending",
            })

    log.info("  DDG found %d candidates for %s", len(candidates), indicator_id)
    return candidates
