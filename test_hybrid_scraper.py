"""
Hybrid scraper test — validates curl_cffi impersonation + fallbacks
against 3 target URLs before integrating into Zone 2.

Usage: python test_hybrid_scraper.py
Optional: --proxy http://user:pass@host:port
"""

import os
import json
import time
import random
import argparse
import hashlib
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("hybrid_test")

# Try curl_cffi — primary fetcher for static HTML/PDF
try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
    log.info("curl_cffi available ✓")
except ImportError:
    HAS_CURL_CFFI = False
    log.warning("curl_cffi NOT available — will fall back to requests")

# Try Crawl4AI — fallback for JS-heavy pages
try:
    from crawl4ai import AsyncWebCrawler
    from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig
    from crawl4ai.cache_context import CacheMode
    HAS_CRAWL4AI = True
    log.info("Crawl4AI available ✓")
except ImportError:
    HAS_CRAWL4AI = False
    log.warning("Crawl4AI NOT available")

# Try Playwright stealth — last resort for heavily protected pages
try:
    from playwright.sync_api import sync_playwright
    try:
        from playwright_stealth import stealth_sync
        HAS_STEALTH = True
    except ImportError:
        HAS_STEALTH = False
    HAS_PLAYWRIGHT = True
    log.info("Playwright available ✓ (stealth: %s)", HAS_STEALTH)
except ImportError:
    HAS_PLAYWRIGHT = False
    log.warning("Playwright NOT available")

import requests as std_requests
import pdfplumber
import io


CACHE_DIR = Path(".scrape_cache")
CACHE_DIR.mkdir(exist_ok=True)


# ── Tier 1: curl_cffi (TLS impersonation) ──────────────────────────────

def fetch_curl_cffi(url, proxy=None, timeout=60):
    """Primary fetcher using curl_cffi with Chrome TLS fingerprint."""
    if not HAS_CURL_CFFI:
        return None

    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
    }
    proxies = {"http": proxy, "https": proxy} if proxy else None

    try:
        resp = curl_requests.get(
            url,
            headers=headers,
            impersonate="chrome120",
            proxies=proxies,
            timeout=timeout,
            allow_redirects=True,
        )
        if resp.status_code == 200:
            content_type = resp.headers.get("Content-Type", "")
            log.info("  curl_cffi: HTTP 200 (%d bytes, type=%s)", len(resp.content), content_type[:40])
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


# ── Tier 2: Crawl4AI (stealth browser) ────────────────────────────────

async def fetch_crawl4ai(url, timeout=60):
    """Fallback fetcher using Crawl4AI AsyncWebCrawler with stealth."""
    if not HAS_CRAWL4AI:
        return None

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
                log.warning("  Crawl4AI: returned None")
                return None
            text = ""
            if hasattr(result, "markdown") and result.markdown:
                text = result.markdown
            elif hasattr(result, "text") and result.text:
                text = result.text
            elif hasattr(result, "html") and result.html:
                text = result.html
            if not text:
                log.warning("  Crawl4AI: no text content in result")
                return None
            if len(text) >= 200:
                log.info("  Crawl4AI: %d chars extracted", len(text))
                return text.encode("utf-8")
            log.warning("  Crawl4AI: too short (%d chars)", len(text))
            return None
    except Exception as e:
        log.warning("  Crawl4AI failed: %s", e)
        return None


# ── Tier 3: Playwright + Stealth (last resort) ─────────────────────────

def fetch_playwright(url, timeout=60):
    """Last-resort fetcher using Playwright with stealth plugin."""
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

            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            # Wait for body to render
            page.wait_for_selector("body", timeout=10000)
            # Simulate a brief human-like scroll
            page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.3)")
            time.sleep(random.uniform(0.5, 1.5))
            page.evaluate("window.scrollTo(0, 0)")

            content = page.content()
            browser.close()
            if content and len(content) >= 200:
                log.info("  Playwright: %d chars extracted", len(content))
                return content.encode("utf-8")
            log.warning("  Playwright: too short (%d chars)", len(content) if content else 0)
            return None
    except Exception as e:
        log.warning("  Playwright failed: %s", e)
        return None


# ── PDF extraction ─────────────────────────────────────────────────────

def extract_pdf_text(content_bytes):
    """Extract text from PDF bytes using pdfplumber."""
    try:
        doc = pdfplumber.open(io.BytesIO(content_bytes))
        total = len(doc.pages)
        pages_to_read = min(total, 191)
        parts = []
        for i, page in enumerate(doc.pages):
            if i >= pages_to_read:
                break
            txt = page.extract_text() or ""
            parts.append(txt)
        doc.close()
        text = "\n".join(parts)
        log.info("  PDF: %d pages, %d chars", pages_to_read, len(text))
        return text
    except Exception as e:
        log.warning("  PDF extraction failed: %s", e)
        return None


# ── Cache helpers ──────────────────────────────────────────────────────

def cache_key(url):
    return hashlib.md5(url.encode()).hexdigest()


def cache_load(url):
    key = cache_key(url)
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            log.info("  Cache HIT: %s (%d chars)", url, len(data.get("text", "")))
            return data.get("text")
        except Exception:
            pass
    return None


def cache_save(url, text, source):
    key = cache_key(url)
    path = CACHE_DIR / f"{key}.json"
    data = {"url": url, "source": source, "text": text, "timestamp": time.time()}
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    log.info("  Cache SAVED: %s (%d chars, via %s)", url, len(text), source)


# ── Hybrid scraper ─────────────────────────────────────────────────────

def _fallback_pdf_fetch(url, timeout=60):
    """Direct requests fallback for PDFs with browser-like headers."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,application/x-pdf,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
    }
    try:
        resp = std_requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 200 and b"%PDF" in resp.content[:100]:
            log.info("  fallback_requests: HTTP 200 (%d bytes, PDF)", len(resp.content))
            text = extract_pdf_text(resp.content)
            if text and len(text) >= 200:
                return text, "fallback_requests_pdf"
        log.warning("  fallback_requests: HTTP %d or not PDF", resp.status_code)
    except Exception as e:
        log.warning("  fallback_requests failed: %s", e)
    return None, None


def hybrid_scrape(url, proxy=None):
    """Try 3 tiers in order: curl_cffi → Crawl4AI → Playwright.
    Returns extracted text or None."""
    # Check cache first
    cached = cache_load(url)
    if cached:
        return cached

    is_pdf = url.lower().endswith(".pdf")

    # Tier 1: curl_cffi (fast, TLS-spoofed)
    content = fetch_curl_cffi(url, proxy=proxy)
    if content:
        if is_pdf or b"%PDF" in content[:100]:
            text = extract_pdf_text(content)
            if text and len(text) >= 200:
                cache_save(url, text, "curl_cffi_pdf")
                return text
        else:
            text = content.decode("utf-8", errors="replace")
            if len(text) >= 200:
                cache_save(url, text, "curl_cffi_html")
                return text

    # PDF fallback: try direct requests
    if is_pdf:
        text, source = _fallback_pdf_fetch(url)
        if text:
            cache_save(url, text, source)
            return text

    # Tier 2: Crawl4AI (async, stealth browser)
    if HAS_CRAWL4AI:
        import asyncio
        content = asyncio.run(fetch_crawl4ai(url))
        if content:
            text = content.decode("utf-8", errors="replace")
            if len(text) >= 200:
                cache_save(url, text, "crawl4ai")
                return text

    # Tier 3: Playwright (last resort — skip PDFs, browser can't render them)
    if not is_pdf:
        content = fetch_playwright(url)
        if content:
            text = content.decode("utf-8", errors="replace")
            if len(text) >= 200:
                cache_save(url, text, "playwright")
                return text
    else:
        log.info("  Skipping Playwright for PDF URL")

    log.error("  All tiers FAILED for %s", url)
    return None


# ── Test 3 target URLs ────────────────────────────────────────────────

TEST_URLS = [
    {
        "label": "SGP-PDPA",
        "url": "https://sso.agc.gov.sg/Act/PDPA2012",
        "description": "Singapore PDPA — should be easy",
        "expect_success": True,
    },
    {
        "label": "AUS-LEGIS",
        "url": "https://www.legislation.gov.au/C2024A00001/latest/text",
        "description": "Australia legislation.gov.au — text view",
        "expect_success": True,
    },
    {
        "label": "MYS-PDPA",
        "url": "https://www.pdp.gov.my/ppdpv1/wp-content/uploads/2024/07/UNDANG-UNDANG-MALAYSIA_AKTA_PERLINDUNGAN_DATA_PERIBADI_2010_709_MALAY_AND-ENG_V2022.pdf",
        "description": "Malaysia PDPA PDF — curl_cffi should handle",
        "expect_success": True,
    },
]


def main():
    parser = argparse.ArgumentParser(description="Test hybrid scraper against target URLs")
    parser.add_argument("--proxy", help="Proxy URL (http://user:pass@host:port)")
    parser.add_argument("--url", help="Test a single URL instead of the defaults")
    parser.add_argument("--label", default="custom", help="Label for single URL test")
    args = parser.parse_args()

    proxy = args.proxy

    if args.url:
        urls_to_test = [{"label": args.label, "url": args.url, "description": "custom", "expect_success": True}]
    else:
        urls_to_test = TEST_URLS

    log.info("=" * 65)
    log.info("HYBRID SCRAPER TEST")
    log.info("Proxy: %s", proxy or "None (direct connection)")
    log.info("Tools: curl_cffi=%s, Crawl4AI=%s, Playwright=%s (stealth=%s)",
             HAS_CURL_CFFI, HAS_CRAWL4AI, HAS_PLAYWRIGHT, HAS_STEALTH)
    log.info("Caching: %s\n", CACHE_DIR)
    log.info("=" * 65)

    results = []

    for t in urls_to_test:
        log.info("\n" + "-" * 65)
        log.info("  [%s] %s", t["label"], t["description"])
        log.info("  URL: %s", t["url"])
        log.info("-" * 65)

        t0 = time.time()
        text = hybrid_scrape(t["url"], proxy=proxy)
        elapsed = time.time() - t0

        success = text is not None and len(text) >= 200
        status = "✅ PASS" if success else "❌ FAIL"
        log.info("\n  %s (%.1fs, %d chars)", status, elapsed, len(text) if text else 0)

        if success:
            # Show first 200 chars
            preview = text[:200].replace("\n", " ").strip()
            log.info("  Preview: %s...", preview)

        results.append({
            "label": t["label"],
            "url": t["url"],
            "success": success,
            "chars": len(text) if text else 0,
            "elapsed": round(elapsed, 1),
        })

    # Summary
    log.info("\n" + "=" * 65)
    log.info("  SUMMARY")
    log.info("=" * 65)
    passed = sum(1 for r in results if r["success"])
    total = len(results)
    for r in results:
        icon = "✅" if r["success"] else "❌"
        log.info("  %s [%s] %s (%d chars, %.1fs)", icon, r["label"], r["url"], r["chars"], r["elapsed"])
    log.info("\n  %d/%d passed", passed, total)

    return 0 if passed == total else 1


if __name__ == "__main__":
    exit(main())
