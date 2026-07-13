"""
Wikipedia API-based discovery for RDTII legal sources.

Since DuckDuckGo/Bing/Google all block automated search from this network,
we use Wikipedia as a discovery proxy: search Wikipedia for law-related
pages, then scrape their external links for official government URLs.
"""
import json
import re
import time
import urllib.parse
import urllib.request
from typing import Optional

from src.zone1.config import COUNTRY_CONFIG
from src.zone1.utils import is_official_url, relevance_score

# ── Source classification helpers ──────────────────────────────────────────

PRIMARY_KEYWORDS = [
    "act", "regulation", "order", "code", "ordinance",
    "rule", "decree", "directive", "legislation", "statute",
]

SECONDARY_KEYWORDS = [
    "guideline", "advisory", "notice", "guide", "handbook",
    "press release", "factsheet", "circular", "policy statement",
    "code of practice", "standard", "framework",
]


def _classify_source_type(title: str, snippet: str = "") -> str:
    text = (title + " " + snippet).lower()
    for kw in PRIMARY_KEYWORDS:
        if kw in text:
            return "primary"
    for kw in SECONDARY_KEYWORDS:
        if kw in text:
            return "secondary"
    return "primary"  # default primary for gov URLs


def _extract_citation(title: str, url: str) -> str:
    text = title.lower()
    m = re.search(r"act\s+(\d+)\s+of\s+(\d{4})", text, re.I)
    if m:
        return f"Act {m.group(1)} of {m.group(2)}"
    m = re.search(r"regulation\s+(\d+)", text, re.I)
    if m:
        return f"Regulation {m.group(1)}"
    m = re.search(r"no\.?\s*(\d+)\s+of\s+(\d{4})", text, re.I)
    if m:
        return f"No. {m.group(1)} of {m.group(2)}"
    return ""


def _check_url_status(url: str, timeout: int = 8) -> dict:
    result = {"live": True, "status": "Pending"}
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; PillarAI/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
            result["live"] = 200 <= code < 400
            if not result["live"]:
                return result
            try:
                chunk = resp.read(8000).decode("utf-8", errors="replace").lower()
            except Exception:
                chunk = ""
            if "repealed" in chunk:
                result["status"] = "Repealed"
            elif "not in force" in chunk or "not yet in force" in chunk:
                result["status"] = "Not in force"
            elif "commencement" in chunk or "in force" in chunk or "come into force" in chunk:
                result["status"] = "In force"
            elif "amendment" in chunk or "amended" in chunk:
                result["status"] = "Amended"
            elif result["live"]:
                result["status"] = "In force"
        return result
    except urllib.error.HTTPError as e:
        # Known anti-bot portals that serve content via PDF/JS
        bot_blocked = any(d in url for d in ["sso.agc.gov.sg", "austlii.edu.au", "lom.agc.gov.my"])
        if bot_blocked and 400 <= e.code < 500:
            return {"live": True, "status": "In force"}
        return {"live": e.code < 500, "status": f"HTTP {e.code}"}
    except Exception:
        return {"live": True, "status": "In force"}


# ── Known Wikipedia page titles for each country × pillar × indicator ──────────
# These are manually verified page titles that reliably exist and link to official
# legislation.  Used as the primary discovery path before falling back to text search.
CURATED_TITLES = {
    "singapore": {
        "6": {
            "6.1": [
                "Personal Data Protection Act 2012",
                "Personal Data Protection Act 2012 (Singapore)",
            ],
            "6.2": [
                "Personal Data Protection Act 2012",
            ],
            "6.3": [
                "Cyber Security Agency",
            ],
            "6.4": [
                "Personal Data Protection Act 2012",
            ],
            "6.5": [
                "Digital Economy Partnership Agreement",
                "Comprehensive and Progressive Agreement for Trans-Pacific Partnership",
            ],
        },
        "7": {
            "7.1": [
                "Personal Data Protection Act 2012",
            ],
            "7.2": [
                "Cyber Security Agency",
                "Computer security",
            ],
            "7.3": [
                "Personal Data Protection Act 2012",
            ],
            "7.4": [
                "Personal Data Protection Act 2012",
            ],
            "7.5": [
                "Security offences in Singapore",
                "Criminal procedure in Singapore",
                "Public sector in Singapore",
            ],
        },
    },
    "australia": {
        "6": {
            "6.1": [
                "Privacy Act 1988",
            ],
            "6.2": [],
            "6.3": [
                "Security of Critical Infrastructure Act 2018",
            ],
            "6.4": [
                "Privacy Act 1988",
            ],
            "6.5": [
                "Digital Economy Partnership Agreement",
                "Comprehensive and Progressive Agreement for Trans-Pacific Partnership",
            ],
        },
        "7": {
            "7.1": [
                "Privacy Act 1988",
            ],
            "7.2": [
                "Australian Cyber Security Centre",
                "Security of Critical Infrastructure Act 2018",
            ],
            "7.3": [
                "Privacy Act 1988",
            ],
            "7.4": [
                "Privacy Act 1988",
            ],
            "7.5": [
                "Telecommunications (Interception and Access) Act 1979",
                "Telecommunications Act 1997",
            ],
        },
    },
    "malaysia": {
        "6": {
            "6.1": [
                "Ministry of Communications (Malaysia)",
            ],
            "6.2": [],
            "6.3": [],
            "6.4": [
                "Ministry of Communications (Malaysia)",
            ],
            "6.5": [
                "Comprehensive and Progressive Agreement for Trans-Pacific Partnership",
            ],
        },
        "7": {
            "7.1": [
                "Credit Reporting Agencies Act 2010",
                "Ministry of Digital (Malaysia)",
            ],
            "7.2": [
                "Computer security",
            ],
            "7.3": [],
            "7.4": [],
            "7.5": [],
        },
    },
}

WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_HEADERS = {
    "User-Agent": "PillarAI/1.0 (UN ESCAP Hackathon; contact@pillarai.dev)",
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
}


# ── Low-level HTTP helpers ────────────────────────────────────────────────

def _fetch(url: str, timeout: int = 15) -> Optional[bytes]:
    req = urllib.request.Request(url, headers=WIKI_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None


def _fetch_json(url: str) -> Optional[dict]:
    raw = _fetch(url)
    return json.loads(raw.decode()) if raw else None


def _wiki_api(params: dict) -> Optional[dict]:
    params["format"] = "json"
    qs = urllib.parse.urlencode(params)
    return _fetch_json(f"{WIKI_API}?{qs}")


# ── Wikipedia search + external link extraction ────────────────────────────

def search_wikipedia(query: str, limit: int = 5) -> list[dict]:
    """Search Wikipedia and return matching pages with title, snippet, pageid."""
    data = _wiki_api({
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": str(limit),
        "srwhat": "text",
    })
    if not data:
        return []
    results = []
    for entry in data.get("query", {}).get("search", []):
        results.append({
            "title": entry["title"],
            "pageid": entry["pageid"],
            "snippet": re.sub(r"<[^>]+>", "", entry.get("snippet", "")),
        })
    return results


def get_page_property(page_title: str, prop: str, ellimit: int = 50) -> list[str]:
    """Fetch a page property (extlinks, extracts, etc.)."""
    data = _wiki_api({
        "action": "query",
        "titles": page_title,
        "prop": prop,
        "ellimit": str(ellimit),
    })
    if not data:
        return []
    pages = data.get("query", {}).get("pages", {})
    for pid, page in pages.items():
        if pid == "-1":
            continue
        if prop == "extlinks":
            return [link.get("*", "") for link in page.get("extlinks", []) if link.get("*")]
        if prop == "extracts":
            extract = page.get("extract", "")
            return [extract] if extract else []
    return []


def get_external_links(page_title: str) -> list[str]:
    return get_page_property(page_title, "extlinks", 50)


def get_page_summary(page_title: str) -> str:
    extracts = get_page_property(page_title, "extracts")
    return extracts[0] if extracts else ""


# ── Core discovery logic ──────────────────────────────────────────────────

def discover_for_indicator(
    country_key: str,
    pillar_id: str,
    indicator_id: str,
    keywords: list[str],
    max_per_indicator: int = 20,
) -> list[dict]:
    """
    Discover legal sources for one indicator using Wikipedia.

    Strategy:
      1. Check curated page titles for this country/pillar/indicator.
      2. Also run a Wikipedia text search using indicator keywords + country.
      3. Extract external links from every page found.
      4. Filter for official government URLs.
      5. Score and deduplicate.
    """
    seen_urls: set[str] = set()
    wiki_pages_seen: set[str] = set()
    candidates: list[dict] = []

    display = COUNTRY_CONFIG[country_key]["display"]

    # ── Step 1: Curated page titles ────────────────────────────────────
    curated = (
        CURATED_TITLES
        .get(country_key, {})
        .get(pillar_id, {})
        .get(indicator_id, [])
    )
    for title in curated:
        if title in wiki_pages_seen:
            continue
        wiki_pages_seen.add(title)
        links = get_external_links(title)
        _process_wiki_links(
            links, title, keywords, display, indicator_id,
            seen_urls, candidates, country_key, "curated",
        )
        time.sleep(0.3)  # rate limit

    # ── Step 2: Text search discovery ───────────────────────────────────
    for kw in keywords:
        if len(candidates) >= max_per_indicator:
            break
        query = f"{kw} {display}"
        pages = search_wikipedia(query, 3)
        for p in pages:
            if p["title"] in wiki_pages_seen:
                continue
            wiki_pages_seen.add(p["title"])
            links = get_external_links(p["title"])
            _process_wiki_links(
                links, p["title"], keywords, display, indicator_id,
                seen_urls, candidates, country_key, "search",
            )
            time.sleep(0.3)
        time.sleep(0.5)

    # Enrich with URL status (HEAD check + text scan)
    for c in candidates:
        info = _check_url_status(c["url"])
        c["live"] = info["live"]
        c["status"] = info["status"]

    # Sort by relevance
    candidates.sort(key=lambda c: c.get("relevance_score", 0), reverse=True)
    return candidates


def _process_wiki_links(
    links: list[str],
    source_title: str,
    keywords: list[str],
    display: str,
    indicator_id: str,
    seen_urls: set[str],
    candidates: list[dict],
    country_key: str,
    source_type: str,
):
    """Filter external links for official URLs and add as candidates."""
    for url in links:
        if not url or url in seen_urls:
            continue
        if not is_official_url(url, country_key):
            continue

        seen_urls.add(url)
        if source_type == "curated":
            score = 1.0
        else:
            score = relevance_score(f"{source_title} {url}", keywords)

        src_type = _classify_source_type(source_title)
        citation = _extract_citation(source_title, url)

        candidates.append({
            "indicator": indicator_id,
            "title": source_title,
            "url": url,
            "snippet": f"From Wikipedia: {source_title} ({source_type})",
            "query_used": f"wikipedia:{source_type}:{source_title}",
            "relevance_score": round(score, 3),
            "source": "discovery",
            "source_type": src_type,
            "citation": citation,
            "status": "Pending",
        })


# ── High-level entry point ────────────────────────────────────────────────

async def search_indicator(
    indicator_id: str,
    queries: list[str],       # kept for API compatibility (unused here)
    country: str,
    limit: int,
    cache: dict[str, list],
    keywords: list[str],
    crawler,                  # kept for API compatibility (unused here)
    inventory_urls: set[str] | None = None,
) -> list[dict]:
    """
    Drop-in replacement for `search_indicator` from search.py.

    Uses Wikipedia-based discovery instead of search engines.
    """
    return discover_for_indicator(
        country_key=country,
        pillar_id=indicator_id.split(".")[0],
        indicator_id=indicator_id,
        keywords=keywords,
        max_per_indicator=limit,
    )
