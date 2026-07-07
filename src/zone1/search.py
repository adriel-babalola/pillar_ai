import asyncio
import random
import re
from urllib.parse import quote_plus, unquote

from src.zone1.utils import is_official_url, relevance_score

SEARCH_ENGINES = [
    {
        "name": "DuckDuckGo",
        "url": lambda q: f"https://html.duckduckgo.com/html/?q={quote_plus(q)}",
    },
    {
        "name": "Bing",
        "url": lambda q: f"https://www.bing.com/search?q={quote_plus(q)}",
    },
]


def resolve_search_url(url):
    m = re.search(r"[?&]uddg=([^&]+)", url)
    if m:
        return unquote(m.group(1))
    m = re.search(r"[?&]u=([^&]+)", url)
    if m:
        return unquote(m.group(1))
    return url


# ── curl_cffi fetcher for search engines ──────────────────────────────

try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    curl_requests = None
    HAS_CURL_CFFI = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


def _curl_fetch(url, timeout=30):
    """Fetch a URL using curl_cffi with Chrome TLS impersonation."""
    if not HAS_CURL_CFFI:
        return None
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    try:
        resp = curl_requests.get(
            url, headers=headers, impersonate="chrome120",
            timeout=timeout, allow_redirects=True,
        )
        if resp.status_code == 200:
            return resp.content
    except Exception:
        pass
    return None


def _parse_ddg_html(html):
    """Parse DuckDuckGo HTML search results."""
    results = []
    soup = BeautifulSoup(html, "html.parser")
    for item in soup.select(".result"):
        link = item.select_one(".result__a")
        snippet_el = item.select_one(".result__snippet")
        if not link:
            continue
        href = link.get("href", "")
        title = link.get_text(strip=True)
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
        real_url = resolve_search_url(href)
        if real_url.startswith("http"):
            results.append({"title": title, "url": real_url, "snippet": snippet})
    return results


def _parse_bing_html(html):
    """Parse Bing HTML search results."""
    results = []
    soup = BeautifulSoup(html, "html.parser")
    for item in soup.select(".b_algo"):
        link = item.select_one("h2 a")
        snippet_el = item.select_one(".b_lineclamp2")
        if not link:
            continue
        href = link.get("href", "")
        title = link.get_text(strip=True)
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
        if href.startswith("http"):
            real_url = resolve_search_url(href)
            results.append({"title": title, "url": real_url, "snippet": snippet})
    return results


def _fetch_search_curl_cffi(q, engine_name):
    """Fetch search results using curl_cffi and parse HTML directly."""
    url = next(e["url"](q) for e in SEARCH_ENGINES if e["name"] == engine_name)
    html_bytes = _curl_fetch(url)
    if not html_bytes:
        return None, "curl_fetch_failed"
    html = html_bytes.decode("utf-8", errors="replace")

    # Detect if blocked
    if len(html) < 500 or any(signal in html.lower() for signal in [
        "verify you are human", "captcha", "blocked", "access denied",
        "too many requests", "please try again later",
    ]):
        return None, "blocked"

    if engine_name == "DuckDuckGo":
        items = _parse_ddg_html(html)
    else:
        items = _parse_bing_html(html)

    if not items:
        return None, "no_results"

    return items, "ok"


def _fetch_search_crawl4ai(q, engine_url, crawler):
    """Fallback: use Crawl4AI browser to fetch search results (legacy)."""
    try:
        from crawl4ai.async_configs import CrawlerRunConfig
        from crawl4ai.cache_context import CacheMode
        import asyncio

        async def _fetch():
            config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                remove_overlay_elements=True,
                wait_for="body",
                magic=True,
                simulate_user=True,
                override_navigator=True,
                user_agent_mode="random",
            )
            result = await crawler.arun(url=engine_url, config=config)
            markdown = result.markdown or ""
            if len(markdown) < 500:
                return None, "blocked"

            items = parse_search_results(markdown)
            return items, "ok"

        return asyncio.get_running_loop().run_until_complete(_fetch())
    except Exception as exc:
        return None, str(exc)


def parse_search_results(markdown):
    """Legacy parser for Crawl4AI markdown-format search results."""
    results = []
    lines = markdown.split("\n")
    current = None
    snippet_parts = []

    for line in lines:
        link_match = re.match(r"^\s*\[([^\]]+)\]\(([^)]+)\)\s*$", line)
        if link_match:
            if current:
                current["snippet"] = " ".join(snippet_parts).strip()
                if current["url"].startswith("http"):
                    results.append(current)
            url = link_match.group(2)
            title = link_match.group(1)
            if url.startswith("http") and not url.lower().startswith("javascript:"):
                real_url = resolve_search_url(url)
                current = {"title": title.strip(), "url": real_url, "snippet": ""}
                snippet_parts = []
            else:
                current = None
                snippet_parts = []
        elif current and line.strip():
            snippet_parts.append(line.strip())

    if current and current["url"].startswith("http"):
        current["snippet"] = " ".join(snippet_parts).strip()
        results.append(current)
    return results


def generate_queries(indicator_data, country_display, site_filter):
    full_queries = []
    for theme in indicator_data["query_themes"]:
        themed_q = theme.replace("[COUNTRY]", country_display)
        full_queries.append(f"{site_filter} {themed_q} {country_display}")
    return full_queries


async def fetch_search_results(q, crawler, country):
    """Try engines using curl_cffi first, fallback to Crawl4AI."""
    for engine in SEARCH_ENGINES:
        await asyncio.sleep(random.uniform(2.0, 5.0))

        # Try curl_cffi first (TLS impersonation)
        if HAS_CURL_CFFI and HAS_BS4:
            items, status = await asyncio.to_thread(
                _fetch_search_curl_cffi, q, engine["name"]
            )
            if items:
                official = [it for it in items if is_official_url(it["url"], country)]
                if official:
                    print(f"       {engine['name']} (curl_cffi): {len(items)} results, {len(official)} official")
                    return items
                print(f"       {engine['name']} (curl_cffi): {len(items)} results, 0 official — using anyway")
                return items
            elif status == "blocked":
                print(f"       {engine['name']} (curl_cffi) blocked — trying next engine...")
                continue
            else:
                print(f"       {engine['name']} (curl_cffi): {status} — trying engine...")
                # Fall through to Crawl4AI

        # Fallback: Crawl4AI browser
        url = engine["url"](q)
        try:
            from crawl4ai.async_configs import CrawlerRunConfig
            from crawl4ai.cache_context import CacheMode

            config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                remove_overlay_elements=True,
                wait_for="body",
                magic=True,
                simulate_user=True,
                override_navigator=True,
                user_agent_mode="random",
            )
            result = await crawler.arun(url=url, config=config)
            markdown = result.markdown or ""

            if len(markdown) < 500 or any(s in markdown.lower() for s in [
                "verify you are human", "captcha", "blocked", "access denied",
                "too many requests", "enable javascript",
            ]):
                print(f"       {engine['name']} blocked — trying next engine...")
                continue

            items = parse_search_results(markdown)
            official = [it for it in items if is_official_url(it["url"], country)]
            if official:
                print(f"       {engine['name']} (Crawl4AI): {len(items)} results, {len(official)} official")
                return items
            if items:
                print(f"       {engine['name']} (Crawl4AI): {len(items)} results, 0 official — using anyway")
                return items
        except Exception as exc:
            print(f"       {engine['name']} failed ({exc}) — trying next engine...")
            continue

    return []


async def search_indicator(indicator_id, queries, country, limit, cache, keywords, crawler, inventory_urls=None):
    candidates = []
    seen_urls = set(inventory_urls or [])

    for q in queries:
        if q in cache:
            raw_items = cache[q]
        else:
            raw_items = await fetch_search_results(q, crawler, country)
            cache[q] = raw_items

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
