"""
Zone 1 — Source Discovery for RDTII Pillars 6 & 7.

Dynamically searches official government portals for Singapore, Malaysia,
and Australia to find primary legal instruments relevant to RDTII indicators
under Pillar 6 (Cross-Border Data Policies) and Pillar 7 (Domestic Data
Protection & Privacy). Outputs one JSON file per country-pillar combination.

Uses Crawl4AI (local, offline, no API key) instead of Firecrawl.
"""

import os
import json
import re
import argparse
import asyncio
from urllib.parse import quote_plus

from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import CrawlerRunConfig
from crawl4ai.cache_context import CacheMode

# ---------------------------------------------------------------------------
# COUNTRY CONFIGURATION
# ---------------------------------------------------------------------------
COUNTRY_CONFIG = {
    "singapore": {
        "display": "Singapore",
        "domain_patterns": [
            r"\.gov\.sg",
            r"pdpc\.gov\.sg",
            r"imda\.gov\.sg",
            r"csa\.gov\.sg",
            r"mas\.gov\.sg",
            r"sso\.agc\.gov\.sg",
            r"mti\.gov\.sg",
            r"temasek\.com\.sg",
        ],
        "site_filter": "site:.gov.sg OR site:temasek.com.sg",
    },
    "malaysia": {
        "display": "Malaysia",
        "domain_patterns": [
            r"\.gov\.my",
            r"agc\.gov\.my",
            r"pdp\.gov\.my",
            r"mcmc\.gov\.my",
            r"miti\.gov\.my",
            r"bnm\.gov\.my",
        ],
        "site_filter": "site:.gov.my",
    },
    "australia": {
        "display": "Australia",
        "domain_patterns": [
            r"\.gov\.au",
            r"legislation\.gov\.au",
            r"oaic\.gov\.au",
            r"dfat\.gov\.au",
            r"acma\.gov\.au",
        ],
        "site_filter": "site:.gov.au",
    },
}

# ---------------------------------------------------------------------------
# INDICATOR DEFINITIONS  (Pillar 6 — Cross-Border Data Policies)
# ---------------------------------------------------------------------------
PILLAR_6_INDICATORS = {
    "6.1": {
        "name": "Ban and local processing requirements",
        "keywords": ["prohibit", "must not transfer", "local processing",
                     "cross-border", "transfer personal data"],
        "query_themes": [
            "must not transfer personal data",
            "prohibit cross-border transfer",
            "local processing requirement [COUNTRY]",
            "data shall not be transferred outside",
            "prohibition on transfer of personal data",
        ],
    },
    "6.2": {
        "name": "Local storage requirements",
        "keywords": ["local storage", "store data locally",
                     "data shall be stored", "data localization",
                     "records kept in"],
        "query_themes": [
            "data localization requirement [COUNTRY]",
            "store data locally requirement",
            "records must be kept in [COUNTRY]",
            "data residency requirement",
            "stored and processed within [COUNTRY]",
        ],
    },
    "6.3": {
        "name": "Infrastructure requirements",
        "keywords": ["server located", "local server", "data centre",
                     "computing facility", "infrastructure requirement"],
        "query_themes": [
            "server must be located in [COUNTRY]",
            "local server requirement data",
            "data centre located in [COUNTRY]",
            "computing infrastructure requirement",
            "server and data centre requirements",
        ],
    },
    "6.4": {
        "name": "Conditional flow regimes",
        "keywords": ["consent", "adequacy decision",
                     "contractual safeguards", "binding corporate rules",
                     "data transfer exception"],
        "query_themes": [
            "data transfer conditions consent",
            "adequacy decision cross-border data",
            "contractual safeguards data transfer",
            "binding corporate rules data protection",
            "cross-border data flow conditions",
        ],
    },
    "6.5": {
        "name": "Not in binding data transfer agreements",
        "keywords": ["CPTPP", "RCEP", "DEPA", "digital economy agreement",
                     "free trade agreement", "cross-border data flow"],
        "query_themes": [
            "CPTPP [COUNTRY] data flows",
            "RCEP cross-border data flows",
            "DEPA digital economy partnership",
            "digital economy agreement [COUNTRY]",
            "free trade agreement data transfer",
        ],
    },
}

# ---------------------------------------------------------------------------
# INDICATOR DEFINITIONS  (Pillar 7 — Domestic Data Protection & Privacy)
# ---------------------------------------------------------------------------
PILLAR_7_INDICATORS = {
    "7.1": {
        "name": "Lack of comprehensive data protection framework",
        "keywords": ["data protection", "personal data",
                     "privacy act", "data protection framework",
                     "personal information"],
        "query_themes": [
            "data protection act [COUNTRY]",
            "personal data protection law",
            "privacy act",
            "data protection framework",
            "personal information protection law",
        ],
    },
    "7.2": {
        "name": "Lack of dedicated cybersecurity framework",
        "keywords": ["cybersecurity", "cyber security",
                     "information security", "computer misuse",
                     "cybercrime"],
        "query_themes": [
            "cybersecurity act [COUNTRY]",
            "cyber security law",
            "information security act",
            "computer misuse act",
            "cybersecurity legislation",
        ],
    },
    "7.3": {
        "name": "Minimum period of data retention requirements",
        "keywords": ["retain for", "retention period", "keep records",
                     "data retention", "shall retain"],
        "query_themes": [
            "data retention requirement",
            "records shall be retained for years",
            "retention period personal data",
            "keep records for minimum period",
            "retention of personal data",
        ],
    },
    "7.4": {
        "name": "DPO/DPIA requirements",
        "keywords": ["Data Protection Officer", "DPO",
                     "Data Protection Impact Assessment", "DPIA",
                     "privacy impact assessment"],
        "query_themes": [
            "Data Protection Officer requirement",
            "appoint Data Protection Officer",
            "Data Protection Impact Assessment",
            "DPIA requirement",
            "privacy impact assessment",
        ],
    },
    "7.5": {
        "name": "Government access to personal data",
        "keywords": ["government access", "lawful access",
                     "surveillance powers", "police access",
                     "national security access"],
        "query_themes": [
            "government access to personal data",
            "lawful access to data",
            "surveillance powers data",
            "police access to personal data",
            "interception of communications law",
        ],
    },
}

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def is_official_url(url, country):
    """Return True if *url* matches the official domain patterns for *country*."""
    patterns = COUNTRY_CONFIG[country]["domain_patterns"]
    return any(re.search(p, url, re.I) for p in patterns)


def relevance_score(text, keywords):
    """Simple 0-1 score based on keyword density in text."""
    if not text.strip():
        return 0.0
    lower = text.lower()
    matches = sum(1 for kw in keywords if kw.lower() in lower)
    return min(matches / len(keywords), 1.0)


def parse_search_results(markdown):
    """Parse links and surrounding text from DuckDuckGo search result markdown."""
    results = []
    lines = markdown.split("\n")
    current = None
    snippet_parts = []

    for line in lines:
        link_match = re.match(r"^\s*\[([^\]]+)\]\(([^)]+)\)\s*$", line)
        if link_match:
            if current:
                current["snippet"] = " ".join(snippet_parts).strip()
                results.append(current)

            url = link_match.group(2)
            title = link_match.group(1)
            lower_url = url.lower()

            ddg_domains = (
                "duckduckgo.com", "duck.co", "safe.duckduckgo.com",
                "html.duckduckgo.com", "lite.duckduckgo.com",
            )
            if (url.startswith("http") and not lower_url.startswith("javascript:")
                and not any(d in lower_url for d in ddg_domains)):
                current = {"title": title, "url": url, "snippet": ""}
                snippet_parts = []
            else:
                current = None
                snippet_parts = []
        elif current and line.strip():
            snippet_parts.append(line.strip())

    if current:
        current["snippet"] = " ".join(snippet_parts).strip()
        results.append(current)

    return results


def generate_queries(indicator_data, country_display, site_filter):
    """
    Produce a list of full search queries for a given indicator by
    combining the site filter with each query theme and inserting the
    country name where [COUNTRY] appears.  Every query is suffixed
    with the country name so results stay geographically relevant.
    """
    full_queries = []
    for theme in indicator_data["query_themes"]:
        themed_q = theme.replace("[COUNTRY]", country_display)
        full_queries.append(f"{site_filter} {themed_q} {country_display}")
    return full_queries


async def search_indicator(indicator_id, queries, country, limit, cache, keywords, crawler):
    """
    Run each query through DuckDuckGo search via Crawl4AI,
    filter to official URLs, deduplicate, and attach a relevance score.
    """
    candidates = []
    seen_urls = set()

    for q in queries:
        if q in cache:
            raw_items = cache[q]
        else:
            search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(q)}"
            try:
                config = CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS,
                    remove_overlay_elements=True,
                    wait_for="body",
                )
                result = await crawler.arun(url=search_url, config=config)
                markdown = result.markdown or ""
                raw_items = parse_search_results(markdown)
                cache[q] = raw_items
            except Exception as exc:
                print(f"    [WARN] Query failed — {q[:80]}: {exc}")
                continue

        for item in raw_items:
            url = item["url"]
            title = item["title"]
            snippet = item["snippet"]

            if not url:
                continue
            if not is_official_url(url, country):
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)

            if not title:
                continue

            score = relevance_score(f"{title} {snippet}", keywords)
            candidates.append({
                "indicator": indicator_id,
                "title": title,
                "url": url,
                "snippet": snippet[:500],
                "query_used": q,
                "relevance_score": round(score, 3),
            })

    candidates.sort(key=lambda c: c["relevance_score"], reverse=True)
    return candidates


async def process_country_pillar(country_key, pillar_id, limit, crawler):
    """Run discovery for one country + pillar combination and save JSON."""
    country_conf = COUNTRY_CONFIG[country_key]
    display_name = country_conf["display"]
    site_filter = country_conf["site_filter"]

    pillar_data = PILLAR_6_INDICATORS if pillar_id == "6" else PILLAR_7_INDICATORS
    pillar_label = f"Pillar {pillar_id}"

    print(f"\n{'='*60}")
    print(f"  {display_name} - {pillar_label}")
    print(f"{'='*60}")

    all_candidates = {}
    cache = {}

    for ind_id in sorted(pillar_data.keys()):
        ind_data = pillar_data[ind_id]
        print(f"\n  [{ind_id}] {ind_data['name']}")

        queries = generate_queries(ind_data, display_name, site_filter)
        results = await search_indicator(
            ind_id, queries, country_key, limit, cache, ind_data["keywords"], crawler
        )
        all_candidates[ind_id] = results
        print(f"       Found {len(results)} candidate(s) (from {len(queries)} queries)")

        if results:
            top = results[0]
            print(f"       Top: {top['title'][:70]}...")

    filename = f"zone1_{country_key}_pillar{pillar_id}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_candidates, f, indent=2, ensure_ascii=False)
    print(f"\n  [SAVED] {filename}")
    return filename


# ---------------------------------------------------------------------------
# CLI & MAIN
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(
        description="Zone 1 — Source Discovery for RDTII Pillars 6 & 7"
    )
    parser.add_argument(
        "--country",
        choices=["singapore", "malaysia", "australia"],
        help="Country to process (default: all three)",
    )
    parser.add_argument(
        "--pillar",
        choices=["6", "7"],
        help="Pillar to process (default: both)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Max results per query (default: 10)",
    )
    args = parser.parse_args()

    countries = [args.country] if args.country else list(COUNTRY_CONFIG.keys())
    pillars = [args.pillar] if args.pillar else ["6", "7"]

    print("ZONE 1 DISCOVERY - Source Discovery for RDTII")
    print(f"Countries: {', '.join(c.capitalize() for c in countries)}")
    print(f"Pillars:   {', '.join(pillars)}")
    print(f"Limit:     {args.limit} results per query")

    async with AsyncWebCrawler() as crawler:
        saved_files = []
        for c in countries:
            for p in pillars:
                fname = await process_country_pillar(c, p, args.limit, crawler)
                saved_files.append(fname)

    print(f"\n{'='*60}")
    print("  DONE — All outputs saved:")
    for f in saved_files:
        size = os.path.getsize(f) if os.path.exists(f) else 0
        print(f"    {f}  ({size:,} bytes)")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
