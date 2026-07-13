"""
Hybrid scraper — smart 3-tier fetcher for Zone 2 extraction.

Strategy:
  - PDF URLs → curl_cffi (TLS impersonation for binary download)
  - HTML URLs → Crawl4AI (renders JS → clean markdown)
  - Fallback → curl_cffi+BS4 (raw HTML stripped), then Playwright+stealth

All async — integrates cleanly with the async extraction pipeline.
"""

import hashlib
import io
import json
import time
import random
import asyncio
from pathlib import Path

import pdfplumber
import requests as std_requests

from src.zone2.config import CACHE_DIR, PROXY_URL, log

# ── HTML Tier 1: Crawl4AI (renders JS → clean markdown) ─────────────

try:
    from crawl4ai import AsyncWebCrawler
    from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig
    from crawl4ai.cache_context import CacheMode
    HAS_CRAWL4AI = True
except ImportError:
    AsyncWebCrawler = None
    HAS_CRAWL4AI = False
    log.warning("crawl4ai not installed — HTML Tier 1 unavailable")


async def fetch_crawl4ai(url, timeout=60):
    """Stealth browser fetch via Crawl4AI — renders JS, returns clean markdown."""
    if not HAS_CRAWL4AI:
        return None, None

    browser_cfg = BrowserConfig(
        headless=True,
        enable_stealth=True,
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        extra_args=["--disable-blink-features=AutomationControlled"],
    )
    run_cfg = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        remove_overlay_elements=True,
        wait_for="body",
        magic=True,
        simulate_user=True,
        override_navigator=True,
        user_agent_mode="random",
    )

    try:
        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            result = await crawler.arun(url=url, config=run_cfg)
            if result is None:
                return None, "crawl4ai_none"
            text = None
            if hasattr(result, "markdown") and result.markdown:
                text = result.markdown
            elif hasattr(result, "text") and result.text:
                text = result.text
            elif hasattr(result, "html") and result.html:
                text = result.html
            if not text or len(text) < 200:
                return None, "crawl4ai_short"
            log.info("  Crawl4AI: %d chars extracted", len(text))
            return text, "crawl4ai"
    except Exception as e:
        log.warning("  Crawl4AI failed: %s", e)
        return None, "crawl4ai_error"


# ── PDF Tier 1: curl_cffi (TLS impersonation) ────────────────────────

try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    curl_requests = None
    HAS_CURL_CFFI = False


def fetch_curl_cffi(url, proxy=None, timeout=60):
    if not HAS_CURL_CFFI:
        return None
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,application/x-pdf,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    proxies = {"http": proxy, "https": proxy} if proxy else None
    try:
        resp = curl_requests.get(
            url, headers=headers, impersonate="chrome120",
            proxies=proxies, timeout=timeout, allow_redirects=True,
        )
        if resp.status_code == 200:
            return resp.content
        elif resp.status_code == 403:
            log.warning("  curl_cffi: HTTP 403 (blocked)")
            return None
        else:
            log.warning("  curl_cffi: HTTP %d", resp.status_code)
            return None
    except Exception as e:
        log.warning("  curl_cffi failed: %s", e)
        return None


# ── HTML Tier 2: curl_cffi + BeautifulSoup ──────────────────────────

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


def _strip_html(html):
    if HAS_BS4:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)
    import re
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def fetch_curl_cffi_html(url, proxy=None, timeout=60):
    if not HAS_CURL_CFFI:
        return None
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    proxies = {"http": proxy, "https": proxy} if proxy else None
    try:
        resp = curl_requests.get(
            url, headers=headers, impersonate="chrome120",
            proxies=proxies, timeout=timeout, allow_redirects=True,
        )
        if resp.status_code == 200:
            raw = resp.content.decode("utf-8", errors="replace")
            text = _strip_html(raw)
            if len(text) >= 200:
                log.info("  curl_cffi+BS4: %d chars", len(text))
                return text
    except Exception as e:
        log.warning("  curl_cffi HTML failed: %s", e)
    return None


# ── HTML Tier 3: Playwright + stealth ────────────────────────────────

try:
    from playwright.sync_api import sync_playwright
    try:
        from playwright_stealth import stealth_sync
        HAS_STEALTH = True
    except ImportError:
        HAS_STEALTH = False
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    HAS_STEALTH = False


def _expand_content(page):
    """Click expandable UI elements to reveal hidden content."""
    expand_selectors = [
        "text=Select All",
        "text=Read More",
        "text=Read more",
        "text=Show More",
        "text=Show more",
        "text=Expand All",
        "text=Expand all",
        "text=View More",
        "text=View more",
        "text=Show all",
        "text=Show All",
        "summary",  # HTML5 <details><summary>
        "[aria-expanded=false]",
    ]
    for selector in expand_selectors:
        try:
            elements = page.locator(selector)
            count = elements.count()
            for i in range(min(count, 20)):
                try:
                    el = elements.nth(i)
                    if el.is_visible(timeout=1000):
                        el.click()
                        page.wait_for_timeout(300)
                except Exception:
                    pass
        except Exception:
            pass
    page.wait_for_timeout(2000)


def fetch_playwright(url, timeout=60):
    if not HAS_PLAYWRIGHT:
        return None
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1920, "height": 1080},
            )
            page = context.new_page()
            if HAS_STEALTH:
                stealth_sync(page)
            page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            page.wait_for_timeout(3000)
            _expand_content(page)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.3)")
            page.wait_for_timeout(1000)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.7)")
            page.wait_for_timeout(1000)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1000)
            content = page.content()
            browser.close()
            if content and len(content) >= 200:
                text = _strip_html(content)
                if len(text) >= 200:
                    log.info("  Playwright: %d chars", len(text))
                    return text
    except Exception as e:
        log.warning("  Playwright failed: %s", e)
    return None


# ── PDF ──────────────────────────────────────────────────────────────

def extract_pdf_text(content_bytes):
    try:
        doc = pdfplumber.open(io.BytesIO(content_bytes))
        total = len(doc.pages)
        pages_to_read = min(total, 191)
        parts = [doc.pages[i].extract_text() or "" for i in range(pages_to_read)]
        doc.close()
        text = "\n".join(parts)
        log.info("  PDF: %d pages, %d chars", pages_to_read, len(text))
        return text
    except Exception as e:
        log.warning("  PDF extraction failed: %s", e)
        return None


# ── Cache ──────────────────────────────────────────────────────────────

def _cache_key(url):
    return hashlib.md5(url.encode()).hexdigest()


def _cache_load(url):
    key = _cache_key(url)
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("text")
        except Exception:
            pass
    return None


def _cache_save(url, text, source):
    key = _cache_key(url)
    path = CACHE_DIR / f"{key}.json"
    data = {"url": url, "source": source, "text": text, "timestamp": time.time()}
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ── Content quality checks ───────────────────────────────────────────

def _has_js_garbage(text):
    """Detect if text is navigation chrome (JS shell) instead of real content."""
    nav_indicators = ["my collections", "all collections", "as published", "acts supplement",
                      "bills supplement", "subsidiary legislation", "revised editions",
                      "faqs", "feedback", "my collection", "collection"]
    content_indicators = ["part i", "part ii", "part iii", "part iv", "section 1.",
                          "section 2.", "section 3.", "this act", "provision of this"]
    text_lower = text.lower()
    nav_score = sum(1 for ni in nav_indicators if ni in text_lower)
    content_score = sum(1 for ci in content_indicators if ci in text_lower)
    if nav_score >= 3 and content_score < 2:
        log.info("  Content quality: nav=%d content=%d — JS shell detected, switching to Playwright", nav_score, content_score)
        return True
    return False


# ── Async hybrid scrape ──────────────────────────────────────────────

_SSO_PDF_MAP = {
    "PDPA2012": "https://sso.agc.gov.sg/Acts-Supp/26-2012/Published/20211231?DocDate=20121203&ViewType=Pdf",
}


def _normalize_ssourl(url):
    """SSO pages need ProvIds=WholeDoc&ViewType=Adv or known PDF URLs."""
    if "sso.agc.gov.sg" not in url:
        return url
    # Known Acts-Supp PDFs
    for act_key, pdf_url in _SSO_PDF_MAP.items():
        if f"Act/{act_key}" in url:
            log.info("  Using known PDF URL for %s", act_key)
            return pdf_url
    # Otherwise try Advanced View params for JS rendering
    if "sso.agc.gov.sg/Act/" in url and "ProvIds=" not in url and "ViewType=" not in url:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}ProvIds=WholeDoc&ViewType=Adv"
    return url


async def hybrid_scrape(url, proxy=None):
    """Try smart strategy.  Returns (text, source) or (None, reason)."""
    url = _normalize_ssourl(url)
    cached = _cache_load(url)
    if cached:
        log.info("  Cache HIT: %s (%d chars)", url, len(cached))
        return cached, "cache"

    proxy = proxy or PROXY_URL
    is_pdf = url.lower().endswith(".pdf") or "viewtype=pdf" in url.lower()

    if is_pdf:
        content = fetch_curl_cffi(url, proxy=proxy)
        if content:
            text = extract_pdf_text(content)
            if text and len(text) >= 200:
                _cache_save(url, text, "curl_cffi_pdf")
                return text, "curl_cffi_pdf"
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/pdf,application/x-pdf,*/*",
                "Referer": "https://sso.agc.gov.sg/",
            }
            resp = std_requests.get(url, headers=headers, timeout=120)
            if resp.status_code == 200 and b"%PDF" in resp.content[:100]:
                text = extract_pdf_text(resp.content)
                if text and len(text) >= 200:
                    _cache_save(url, text, "requests_pdf")
                    return text, "requests_pdf"
        except Exception as e:
            log.warning("  PDF fallback failed: %s", e)
        return None, "all_pdf_tiers_failed"

    # HTML: Crawl4AI → Playwright (if JS-heavy) → curl_cffi+BS4
    text, source = await fetch_crawl4ai(url)
    if text:
        if _has_js_garbage(text):
            log.info("  Crawl4AI returned JS shell — trying Playwright")
            text = await _run_in_thread(fetch_playwright, url)
            if text:
                _cache_save(url, text, "playwright")
                return text, "playwright"
        else:
            _cache_save(url, text, source)
            return text, source

    text = await _run_in_thread(fetch_playwright, url)
    if text:
        _cache_save(url, text, "playwright")
        return text, "playwright"

    text = await _run_in_thread(fetch_curl_cffi_html, url, proxy=proxy)
    if text:
        _cache_save(url, text, "curl_cffi_html")
        return text, "curl_cffi_html"

    return None, "all_html_tiers_failed"


async def _run_in_thread(fn, *args, **kwargs):
    """Run a synchronous function in a thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))
