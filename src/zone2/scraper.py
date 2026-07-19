"""
Hybrid scraper — smart 3-tier fetcher for Zone 2 extraction.

Strategy:
  - PDF URLs → curl_cffi (TLS impersonation for binary download)
  - HTML URLs → Crawl4AI (renders JS → clean markdown)
  - Fallback → curl_cffi+BS4 (raw HTML stripped), then Playwright+stealth
  - URL transformations: SSO params, AustLII PDF extraction, legislation.gov.au API
  - Web archive fallback when all direct fetches fail
"""

import hashlib
import io
import json
import re
import time
import random
import asyncio
from pathlib import Path
from urllib.parse import urlparse, urljoin

import pdfplumber
import requests as std_requests

from src.zone2.config import CACHE_DIR, PROXY_URL, log
from src.zone2.sg_legislation_api import (
    sso_to_laws_sg,
    is_laws_sg_url,
    get_laws_sg_alternates,
)

# ── HTML Tier 1: Crawl4AI (renders JS → clean markdown) ─────────────

try:
    from crawl4ai import AsyncWebCrawler
    from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig
    from crawl4ai.cache_context import CacheMode
    HAS_CRAWL4AI = True
except ImportError:
    AsyncWebCrawler = None
    HAS_CRAWL4AI = False


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
        "summary",
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


# ── OCR fallback for scanned PDFs ────────────────────────────────────

try:
    import pytesseract
    from pdf2image import convert_bytes
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def _ocr_page(image) -> str:
    if not HAS_OCR or not HAS_PIL:
        return ""
    try:
        return pytesseract.image_to_string(image, lang="eng")
    except Exception as e:
        log.warning("  OCR page failed: %s", e)
        return ""


def extract_pdf_ocr(content_bytes, max_pages=50):
    if not HAS_OCR:
        log.warning("  OCR unavailable — install pytesseract + pdf2image for scanned PDF support")
        return None
    try:
        images = convert_bytes(content_bytes, dpi=300, first_page=1, last_page=max_pages)
        log.info("  OCR: converting %d pages at 300 DPI", len(images))
        parts = []
        for i, img in enumerate(images):
            text = _ocr_page(img)
            if text.strip():
                parts.append(f"--- Page {i + 1} ---\n{text.strip()}")
        full = "\n\n".join(parts)
        log.info("  OCR: %d pages, %d chars", len(images), len(full))
        return full if len(full) >= 50 else None
    except Exception as e:
        log.warning("  OCR extraction failed: %s", e)
        return None


# ── PDF ──────────────────────────────────────────────────────────────

def extract_pdf_text(content_bytes):
    text = None
    try:
        doc = pdfplumber.open(io.BytesIO(content_bytes))
        total = len(doc.pages)
        pages_to_read = min(total, 191)
        parts = [doc.pages[i].extract_text() or "" for i in range(pages_to_read)]
        doc.close()
        text = "\n".join(parts)
        log.info("  PDF: %d pages, %d chars", pages_to_read, len(text))
    except Exception as e:
        log.warning("  pdfplumber failed: %s", e)

    if not text or len(text.strip()) < 100:
        log.info("  pdfplumber returned %d chars — trying OCR (scanned PDF fallback)", len(text or ""))
        ocr_text = extract_pdf_ocr(content_bytes)
        if ocr_text and len(ocr_text) >= 50:
            return ocr_text

    return text if text and len(text.strip()) >= 50 else None


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

NAV_INDICATORS = [
    "my collections", "all collections", "as published", "acts supplement",
    "bills supplement", "subsidiary legislation", "revised editions",
    "faqs", "feedback", "my collection", "collection",
    "federal constitution", "principal", "original", "updated", "repealed",
    "translated", "reprint", "amendment ordinance", "lom.agc",
    "total act views", "all rights reserved",
]

CONTENT_INDICATORS = [
    "part i", "part ii", "part iii", "part iv", "section 1.",
    "section 2.", "section 3.", "this act", "provision of this",
    "short title", "interpretation", "commencement",
]

LOW_QUALITY_TITLE_PATTERNS = [
    re.compile(r"error\s*\d{3}", re.I),
    re.compile(r"page not found", re.I),
    re.compile(r"access denied", re.I),
    re.compile(r"forbidden", re.I),
    re.compile(r"under maintenance", re.I),
]


def _has_js_garbage(text):
    if len(text) > 10000:
        return False
    text_lower = text.lower()
    nav_score = sum(1 for ni in NAV_INDICATORS if ni in text_lower)
    content_score = sum(1 for ci in CONTENT_INDICATORS if ci in text_lower)
    if nav_score >= 3 and content_score < 2:
        return True
    return False


def _is_low_quality_text(text: str, title: str = "") -> bool:
    if len(text.strip()) < 200:
        return True
    for pattern in LOW_QUALITY_TITLE_PATTERNS:
        if pattern.search(title):
            return True
    if _has_js_garbage(text):
        return True
    return False


# ── URL Transformation Layer ─────────────────────────────────────────

def _normalize_ssourl(url: str) -> str:
    """Normalize government legislation URLs for better scraping.

    Handles SSO SG, LOM Malaysia, AustLII, legislation.gov.au, laws.sg patterns.
    """
    # laws.sg – pass through as-is (Crawl4AI renders JS into clean markdown)
    if "laws.sg" in url:
        return url

    # Singapore SSO – add WholeDoc param
    if "sso.agc.gov.sg" in url:
        if "sso.agc.gov.sg/Act/" in url and "ProvIds=" not in url and "ViewType=" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}ProvIds=WholeDoc&ViewType=Adv"
        # Also try the Print-PDF view if it's not already a PDF
        if "viewtype=pdf" not in url.lower() and "viewtype=print" not in url.lower():
            pass  # Adv view is preferred
        return url

    # Malaysia AGC – ensure lang=EN
    if "lom.agc.gov.my" in url:
        if "lang=EN" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}lang=EN"
        return url

    # Legislation.gov.au – use Details/{ID}/html for structured content
    if "legislation.gov.au" in url:
        m = re.search(r'/(Details|Series)/([A-Za-z0-9/]+)', url)
        if m:
            detail_id = m.group(2)
            html_url = f"https://www.legislation.gov.au/Details/{detail_id}/html"
            return html_url
        # ComLaw IDs: C2004A03712/latest, F2021L00289, etc.
        m2 = re.search(r'/([CFA]\d{4}[A-Z]\d{4,})(?:/latest)?(?:/text)?', url)
        if m2:
            detail_id = m2.group(1)
            html_url = f"https://www.legislation.gov.au/Details/{detail_id}/html"
            return html_url
        return url

    return url


def _generate_alternate_urls(url: str) -> list[str]:
    """Generate alternative URLs for a given URL.

    Tries: laws.sg alternates, web archive, scheme switches, path variations.
    """
    alts = []

    # laws.sg alternates: for SSO URLs, add corresponding laws.sg URLs and PDFs
    laws_sg_alts = get_laws_sg_alternates(url)
    alts.extend(laws_sg_alts)

    # Web archive: check latest snapshot
    wa_url = f"https://web.archive.org/web/2020/{url}"
    alts.append(wa_url)

    # For legislation.gov.au, try Details page
    if "legislation.gov.au" in url:
        m = re.search(r'/(Details|Series)/([A-Za-z0-9/]+)', url)
        if m:
            detail_id = m.group(2)
            alts.append(f"https://www.legislation.gov.au/Details/{detail_id}")

    # For AustLII, try PDF link (search for /cgi-bin/viewdoc/ or /au/legis/)
    if "austlii.edu.au" in url:
        if '/cgi-bin/viewdoc/' in url:
            pdf_url = re.sub(r'/cgi-bin/viewdoc/', '/cgi-bin/download/', url)
            alts.append(pdf_url)
            alts.append(pdf_url + '.pdf')
        if '/au/legis/' in url:
            classic_url = url.replace('www5.', 'classic.')
            alts.append(classic_url)
            alts.append(url.rstrip('/') + '.html')
        if url.lower().endswith('.pdf'):
            pass

    # For SSO SG, try the Print view as fallback
    if "sso.agc.gov.sg" in url:
        if "ViewType=Adv" in url:
            print_url = url.replace("ViewType=Adv", "ViewType=Print")
            alts.append(print_url)

    return alts


def _extract_austlii_pdf_link(html: str, base_url: str) -> str | None:
    """Parse AustLII HTML for PDF links to the same document."""
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True).lower()
        if "pdf" in href.lower() or "pdf" in text:
            full_url = urljoin(base_url, href)
            return full_url
    return None


# ── Web Archive / Google Cache fallback ──────────────────────────────

def _fetch_web_archive(url: str, timeout: int = 60) -> str | None:
    """Try to fetch a page from the Wayback Machine."""
    wa_url = f"https://web.archive.org/web/2020/{url}"
    try:
        resp = std_requests.get(
            wa_url, timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            allow_redirects=True,
        )
        if resp.status_code == 200 and len(resp.text) > 500:
            text = _strip_html(resp.text)
            if len(text) >= 200:
                log.info("  Web Archive: %d chars from %s", len(text), wa_url)
                return text
    except Exception as e:
        log.warning("  Web Archive failed: %s", e)
    return None


def _fetch_google_cache(url: str, timeout: int = 60) -> str | None:
    """Try Google cache as a fallback."""
    cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{url}"
    try:
        resp = std_requests.get(
            cache_url, timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            allow_redirects=True,
        )
        if resp.status_code == 200 and len(resp.text) > 500:
            text = _strip_html(resp.text)
            if len(text) >= 200:
                log.info("  Google Cache: %d chars", len(text))
                return text
    except Exception as e:
        log.warning("  Google Cache failed: %s", e)
    return None


# ── Legislation.gov.au direct HTML fetch ─────────────────────────────

def _extract_comlaw_id(url: str) -> str | None:
    """Extract ComLaw ID (e.g. C2004A03712) from any legislation.gov.au URL."""
    m = re.search(r'/([CFA]\d{4}[A-Z]\d{4,})', url)
    return m.group(1) if m else None


def _fetch_legislation_au_details(clean_id: str, timeout: int = 60) -> str | None:
    """Fetch legislation.gov.au Details page directly (not /html version).

    The /html endpoint returns only navigation chrome (~1K chars).
    The Details page (no suffix) returns full act text (~300K chars as rendered HTML).
    """
    for url in [
        f"https://www.legislation.gov.au/Details/{clean_id}",
    ]:
        try:
            resp = std_requests.get(
                url, timeout=timeout,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html",
                },
                allow_redirects=True,
            )
            if resp.status_code == 200 and len(resp.text) > 1000:
                stripped = re.sub(r'<script[^>]*>.*?</script>', '', resp.text, flags=re.I|re.S)
                stripped = re.sub(r'<style[^>]*>.*?</style>', '', stripped, flags=re.I|re.S)
                text = _strip_html(stripped)
                if len(text) >= 200:
                    log.info("  legislation.gov.au Details: %d chars", len(text))
                    return text
        except Exception as e:
            log.warning("  legislation.gov.au Details failed: %s", e)
    return None


def _fetch_legislation_au_text(comlaw_id: str, timeout: int = 120) -> str | None:
    """Fetch act text for a ComLaw ID. Tries OData API PDF first, then Details page HTML.

    Uses api.prod.legislation.gov.au OData API for PDF download (fast, structured),
    falls back to www.legislation.gov.au Details page (reliable, ~300K chars HTML).
    """
    clean_id = comlaw_id.replace("/html", "").replace("/HTML", "").split("/")[0]

    # Try OData API first (PDF → structured text)
    api_url = (
        f"https://api.prod.legislation.gov.au/v1/documents/find("
        f"titleid='{clean_id}',asatspecification='Latest',type='Primary',"
        f"format='Pdf',uniqueTypeNumber=0,volumeNumber=0,rectificationVersionNumber=0)"
    )
    try:
        log.info("  AU OData: requesting PDF for %s", clean_id)
        resp = std_requests.get(
            api_url, timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            allow_redirects=True,
        )
        if resp.status_code == 200 and b"%PDF" in resp.content[:100]:
            text = extract_pdf_text(resp.content)
            if text and len(text) >= 200:
                log.info("  AU OData: %d chars from PDF for %s", len(text), clean_id)
                return text
        log.warning("  AU OData: HTTP %d or not a PDF", resp.status_code)
    except Exception as e:
        log.warning("  AU OData failed for %s: %s", clean_id, e)

    # Fallback: Details page HTML (no /html suffix)
    log.info("  AU fallback: fetching Details page for %s", clean_id)
    return _fetch_legislation_au_details(clean_id, timeout)


# ── Known PDF URL maps ──────────────────────────────────────────────

_SSO_PDF_MAP = {
    "PDPA2012": "https://sso.agc.gov.sg/Acts-Supp/26-2012/Published/20211231?DocDate=20121203&ViewType=Pdf",
}

_MY_PDF_MAP = {
    "Computer Misuse Act 1997": "https://lom.agc.gov.my/act-view.php?lang=EN&act=563",
    "Security Offences (Special Measures) Act 2012": "https://lom.agc.gov.my/act-view.php?lang=EN&act=747",
    "Personal Data Protection Act 2010": "https://www.pdp.gov.my/ppdpv1/wp-content/uploads/2024/07/UNDANG-UNDANG-MALAYSIA_AKTA_PERLINDUNGAN_DATA_PERIBADI_2010_709_MALAY_AND-ENG_V2022.pdf",
}

_MY_ACT_DETAIL_CACHE: dict[str, str | None] = {}


def _url_safe(path: str) -> str:
    """URL-encode spaces and special chars in a URL path segment."""
    return re.sub(r'[^\w/.~\-%]', lambda m: f'%{ord(m.group(0)):02X}', path)


def _resolve_my_pdf_from_act_detail(act_no: str) -> str | None:
    """Parse LOM act-detail.php page to extract the actual PDF URL."""
    if act_no in _MY_ACT_DETAIL_CACHE:
        return _MY_ACT_DETAIL_CACHE[act_no]
    detail_url = f"https://lom.agc.gov.my/act-detail.php?language=BI&act={act_no}"
    try:
        resp = std_requests.get(
            detail_url, timeout=30,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            allow_redirects=True,
        )
        if resp.status_code == 200:
            html = resp.text
            m = re.search(r'ilims/upload/portal/akta/outputaktap/([^"\'&?]+\.pdf)', html, re.I)
            if m:
                pdf_path = _url_safe(m.group(1))
                full_url = f"https://lom.agc.gov.my/ilims/upload/portal/akta/outputaktap/{pdf_path}"
                _MY_ACT_DETAIL_CACHE[act_no] = full_url
                log.info("  MY act-detail: resolved Act %s -> %s", act_no, full_url)
                return full_url
    except Exception as e:
        log.warning("  MY act-detail parse failed for Act %s: %s", act_no, e)
    _MY_ACT_DETAIL_CACHE[act_no] = None
    return None


def _normalize_my_url(url: str) -> str | None:
    """If URL is a LOM act-view or act-detail page, try to get the PDF."""
    m = re.search(r'[?&]act=(\d+)', url)
    if m:
        pdf_url = _resolve_my_pdf_from_act_detail(m.group(1))
        if pdf_url:
            return pdf_url
        old_portal = f"https://lom.agc.gov.my/ilims/upload/portal/akta/LOM/EN/Act%20{m.group(1)}.pdf"
        return old_portal
    return None


_SG_LAWS_SG_PDF_MAP = {
    "PDPA2012": "https://arturio-pdfs.cancode.codes/sg/259.pdf",
    "CA2018": "https://arturio-pdfs.cancode.codes/sg/33.pdf",
    "CMA1993": "https://arturio-pdfs.cancode.codes/sg/19.pdf",
    "CPC2010": "https://arturio-pdfs.cancode.codes/sg/45.pdf",
    "PSGA2018": "https://arturio-pdfs.cancode.codes/sg/256.pdf",
}


def _check_pdf_maps(url: str) -> str | None:
    for act_key, pdf_url in _SSO_PDF_MAP.items():
        if f"Act/{act_key}" in url:
            log.info("  Using known PDF URL for %s", act_key)
            return pdf_url
    for act_name, pdf_url in _MY_PDF_MAP.items():
        if act_name.lower().replace(" ", "") in url.lower().replace(" ", ""):
            log.info("  Using known PDF URL for %s", act_name)
            return pdf_url
    my_pdf = _normalize_my_url(url)
    if my_pdf:
        return my_pdf
    for act_key, pdf_url in _SG_LAWS_SG_PDF_MAP.items():
        if act_key in url or f"sso.agc.gov.sg/Act/{act_key}" in url:
            log.info("  Using laws.sg PDF URL for %s", act_key)
            return pdf_url
    return None


# ── Async hybrid scrape ──────────────────────────────────────────────

async def hybrid_scrape(url, proxy=None):
    """Try smart strategy.  Returns (text, source) or (None, reason)."""
    # Check PDF maps first
    mapped_url = _check_pdf_maps(url)
    if mapped_url:
        url = mapped_url

    url = _normalize_ssourl(url)
    cached = _cache_load(url)
    if cached:
        log.info("  Cache HIT (%d chars)", len(cached))
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

    # HTML: Crawl4AI → Playwright → curl_cffi+BS4
    text, source = await fetch_crawl4ai(url)
    if text and not _is_low_quality_text(text, url):
        # For legislation.gov.au, require >5000 chars to consider it real content
        if "legislation.gov.au" in url and len(text) < 5000:
            log.info("  Crawl4AI returned only %d chars for legislation.gov.au — trying OData API", len(text))
        else:
            _cache_save(url, text, source)
            return text, source

    if "legislation.gov.au" in url and ((text is None) or len(text) < 5000):
        comlaw_id = _extract_comlaw_id(url)
        if comlaw_id:
            log.info("  AU API: fetching text for %s", comlaw_id)
            au_text = _fetch_legislation_au_text(comlaw_id)
            if au_text:
                _cache_save(url, au_text, "legislation_au_api")
                return au_text, "legislation_au_api"

    if text and _has_js_garbage(text):
        log.info("  Crawl4AI returned JS shell — trying Playwright")
        text = await _run_in_thread(fetch_playwright, url)
        if text:
            _cache_save(url, text, "playwright")
            return text, "playwright"

    text = await _run_in_thread(fetch_playwright, url)
    if text:
        _cache_save(url, text, "playwright")
        return text, "playwright"

    text = await _run_in_thread(fetch_curl_cffi_html, url, proxy=proxy)
    if text:
        _cache_save(url, text, "curl_cffi_html")
        return text, "curl_cffi_html"

    # AustLII: if stub page returned, try to extract PDF link
    if "austlii.edu.au" in url:
        log.info("  AustLII HTML tiers failed — trying PDF extraction")
        try:
            resp = std_requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200 and len(resp.text) > 200:
                pdf_link = _extract_austlii_pdf_link(resp.text, url)
                if pdf_link:
                    log.info("  AustLII: found PDF link %s", pdf_link)
                    return await hybrid_scrape(pdf_link, proxy=proxy)
        except Exception as e:
            log.warning("  AustLII PDF extraction failed: %s", e)

    # Alternate URLs
    for alt_url in _generate_alternate_urls(url):
        log.info("  Trying alternate URL: %s", alt_url)
        result, alt_source = await hybrid_scrape(alt_url, proxy=proxy)
        if result:
            return result, f"alt_{alt_source}"



    # Try web archive or Google cache
    log.info("  Trying web archive...")
    wa_text = _fetch_web_archive(url)
    if wa_text:
        _cache_save(url, wa_text, "web_archive")
        return wa_text, "web_archive"

    log.info("  Trying Google cache...")
    gc_text = _fetch_google_cache(url)
    if gc_text:
        _cache_save(url, gc_text, "google_cache")
        return gc_text, "google_cache"

    return None, "all_tiers_failed"


async def _run_in_thread(fn, *args, **kwargs):
    """Run a synchronous function in a thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))
