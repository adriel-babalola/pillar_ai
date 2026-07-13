# Pillar AI — Complete Codebase Explanation

## What Is This Project?

A UN ESCAP hackathon project built for the **RDTII** (Regional Digital Trade Integration Index) framework. It automates legal research: given a country and a pillar of the RDTII, it finds relevant legal sources, extracts the operative legal clauses using LLMs, and verifies the citations — all without manual legal research.

**Target:** Singapore, Malaysia, Australia — Pillars 6 (Data Protection & Cross-Border Data Transfers) and 7 (Digital Trade Facilitation).

**Currently working end-to-end for:** Singapore Pillar 6 only.

---

## Directory Structure

```
pillar_ai/
├── .env                                          # API keys (DASHSCOPE, OPENROUTER, GEMINI, OLLAMA, FIRECRAWL)
├── .gitignore                                    # Ignored files/folders
├── README.md                                     # Brief notes
├── requirements.txt                              # Python dependencies
├── "Singapore, Malaysia, Australia, Legal Inventory.csv"  # 391-row reference dataset
│
├── zone1_discovery.py          # CLI: discover legal sources
├── zone2_extraction.py         # CLI: extract clauses from sources
├── zone3_blindverifier.py      # CLI: verify extracted citations
│
├── src/
│   ├── prompts.py              # Indicator definitions + LLM prompt templates
│   ├── zone1/                  # Source discovery package
│   │   ├── config.py           #   Country domain patterns
│   │   ├── seeds.py            #   Curated seed URLs
│   │   ├── indicators.py       #   Indicator search keywords
│   │   ├── inventory.py        #   Legal CSV loader
│   │   ├── utils.py            #   URL scoring + query generation
│   │   ├── discovery_wikipedia.py  # Wikipedia-based search engine
│   │   └── discovery.py        #   Orchestrator
│   ├── zone2/                  # Extraction & mapping package
│   │   ├── config.py           #   API keys, model config, CSV schema
│   │   ├── client.py           #   Multi-backend LLM client
│   │   ├── scraper.py          #   Hybrid web scraper (3 tiers)
│   │   └── extraction.py       #   Core extraction pipeline
│   └── zone3/
│       └── verifier.py         # Blind citation verification
│
├── outputs/
│   ├── zone1/zone1_singapore_pillar6.json        # Discovery output
│   └── zone2/
│       ├── zone2_singapore_pillar6.csv            # Extraction output
│       └── zone2_singapore_pillar6_verified.csv   # Verified output
│
├── markdowns_dev/              # Archived documentation
└── .scrape_cache/              # Cached scraped documents (MD5-keyed JSON)
```

---

## The 3-Zone Pipeline (How It All Connects)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ ZONE 1: SOURCE DISCOVERY  (zone1_discovery.py → src/zone1/)            │
│                                                                         │
│  For each indicator (6.1–6.5, 7.1–7.5):                               │
│    ┌──────────────┐    ┌───────────────┐    ┌──────────────────┐       │
│    │ seeds.py     │    │ inventory.py  │    │ discovery_       │       │
│    │ hardcoded    │    │ Legal CSV     │    │ wikipedia.py     │       │
│    │ expert URLs  │    │ 391 rows      │    │ Wikipedia API    │       │
│    └──────┬───────┘    └───────┬───────┘    └───────┬──────────┘       │
│           └────────────────────┼───────────────────┘                    │
│                                ▼                                        │
│                     discovery.py (merge, dedupe, filter)                │
│                                ▼                                        │
│                     zone1_{country}_pillar{N}.json                      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ ZONE 2: EXTRACTION & MAPPING   (zone2_extraction.py → src/zone2/)      │
│                                                                         │
│  For each candidate URL (top 5 per indicator):                         │
│    ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐        │
│    │ prefilter    │───▶│ hybrid_scrape│───▶│ LLM extract      │        │
│    │ (LLM:        │    │ (3-tier      │    │ (prompts.py      │        │
│    │  relevant?)  │    │  scraper)    │    │  → JSON clauses) │        │
│    └──────────────┘    └──────────────┘    └────────┬─────────┘        │
│                                                     ▼                   │
│                                           zone2_{country}_pillar{N}.csv │
│                                           (7 columns per row)          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ ZONE 3: BLIND VERIFICATION   (zone3_blindverifier.py → src/zone3/)     │
│                                                                         │
│  For each row in CSV:                                                  │
│    ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐        │
│    │ re-fetch     │───▶│ locate       │───▶│ compare actual   │        │
│    │ document     │    │ section in   │    │ vs claimed text  │        │
│    │ independently│    │ document     │    │ → PASS/FAIL/NR   │        │
│    └──────────────┘    └──────────────┘    └──────────────────┘        │
│                                ▼                                       │
│                     zone2_{country}_pillar{N}_verified.csv              │
│                     (+3 verification columns)                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## File-by-File Explanation

### Root-Level Entry Points

#### `zone1_discovery.py`
CLI entry point for Zone 1. Takes `--country`, `--pillar`, `--limit`. Calls `process_country_pillar()` which orchestrates seeds + inventory + Wikipedia search. Saves JSON. Running without args processes all 3 countries × 2 pillars (6 combos).

#### `zone2_extraction.py`
CLI entry point for Zone 2. Takes `--country`, `--pillar`, `--input` (Zone 1 JSON), `--model`, `--max-candidates`, `--rate-delay`, `--limit`. Loads the discovery JSON, then for each indicator runs pre-filter → scrape → LLM extract → build CSV row.

#### `zone3_blindverifier.py`
CLI entry point for Zone 3. Takes `--input` (Zone 2 CSV), `--output`, `--model`, `--retries`. Calls `verify_csv()` which re-fetches every URL, locates the cited section, compares text, and adds status columns.

---

### `src/prompts.py` (shared)

Defines **two copies** of the indicator data (intentional — different schema for different uses):

1. **PILLAR_6_INDICATORS / PILLAR_7_INDICATORS** (with `question`, `keywords`, `extraction_instructions`) — used by Zone 2 for LLM prompts
2. **PREFILTER_PROMPT** — LLM prompt template for the "is this document relevant?" pre-filter step
3. **EXTRACTION_PROMPT_TEMPLATE** — LLM prompt that forces verbatim legal clause extraction as JSON with fields: `operative_clause`, `section_reference`, `act_title`, `coverage`, `timeframe`, `interpretation`

The key insight: the extraction prompt (line ~168) instructs the LLM to find the **verbatim legal clause text** and combine it into `Impact_or_comments` as `"Section X: [clause text]\nInterpretation: [explanation]"`.

---

### `src/zone1/` — Source Discovery

#### `config.py`
Country configuration — domain patterns for filtering official URLs:

| Country | Official Domains |
|---------|-----------------|
| Singapore | `sso.agc.gov.sg`, `pdpc.gov.sg`, `mti.gov.sg`, `*.gov.sg` |
| Malaysia | `agc.gov.my`, `pdp.gov.my`, `*.gov.my` |
| Australia | `legislation.gov.au`, `oaic.gov.au`, `*.gov.au` |

#### `seeds.py`
273 lines of hardcoded curated URLs. For each country × pillar × indicator, 1–2 expert-selected URLs. Example: Singapore Pillar 6.1 points to `sso.agc.gov.sg/Act/PDPA2012` (Personal Data Protection Act). All 3 countries × 10 indicators are populated.

#### `indicators.py`
A DIFFERENT copy of indicator data specifically for search — includes `query_themes` (Google-style search queries like `"personal data protection" Singapore "cross-border"`) used by `utils.py` to generate queries for the Wikipedia API.

#### `inventory.py`
Loads the 391-row CSV `Singapore, Malaysia, Australia, Legal Inventory.csv`. For each indicator, finds rows whose indicator ID prefix matches, and creates candidate entries. Limitation: the mapping is over-broad — rows about import bans, GST, employment law get mapped to every indicator, producing many irrelevant candidates.

#### `utils.py`
- `is_official_url(url, country)` — checks domain patterns
- `relevance_score(text, keywords)` — simple keyword density 0.0–1.0
- `generate_queries(indicator, country_display, site_filter)` — creates search queries for Wikipedia

#### `discovery_wikipedia.py` (424 lines)
The actual search engine. Why Wikipedia? Because DuckDuckGo, Bing, and Google all block automated search from this server. Wikipedia provides a free API.

**How it works:**
1. `CURATED_TITLES` — hardcoded Wikipedia page titles per country/indicator (e.g., "Personal Data Protection Act 2012 (Singapore)")
2. `search_wikipedia(query, limit)` — Wikipedia text search API → returns page titles
3. `get_external_links(page_title)` — fetches ALL external links from a Wikipedia page
4. `discover_for_indicator(...)` — combines curated page links + search results: fetches external links, filters to official domains, scores relevance, checks URL status (HEAD request + content scan)

**Enrichment per candidate:** `source_type` (primary/secondary), `citation` (extracted from title), `status` (In force/Repealed/Unknown), `live` (URL reachable).

**Scoring:** Curated page URLs always get `relevance_score: 1.0`. Search result URLs are scored by keyword density.

#### `discovery.py` (114 lines)
Orchestrator. `process_country_pillar(country_key, pillar_id, limit, crawler)`:
1. For each indicator: load seeds → load inventory → run Wikipedia discovery
2. Merge and deduplicate by URL
3. Filter: keep only `live: True` + `score > 0` entries — drops dead links and irrelevant text matches
4. Save to JSON

---

### `src/zone2/` — Extraction & Mapping

#### `config.py`
- `DEFAULT_MODEL = "alibaba:qwen3.7-plus,gemini,ollama:gemma4"` — comma-separated fallback chain
- `MAX_TEXT_CHARS = 220000` — document truncation limit
- `CSV_FIELDS` — the 7 output columns for the CSV
- `CACHE_DIR = Path(".scrape_cache")` — where scraped documents are cached

#### `client.py` (220 lines)
Multi-backend LLM client with automatic fallback. Four backends:

| Backend | Trigger Prefix | SDK | Cost |
|---------|---------------|-----|------|
| **Alibaba DashScope** | `alibaba:` | OpenAI SDK → Alibaba endpoint | ~$0.017/extraction (primary) |
| **Google Gemini** | `gemini:` | google-genai SDK | Free tier (rate-limited) |
| **OpenRouter** | (default) | OpenAI SDK → OpenRouter | Token-depleted |
| **Ollama Cloud** | `ollama:` | OpenAI SDK → Ollama | Free models (weak) |

The `llm_call()` function splits the model string on commas and tries each backend in order. If one fails (rate limit, quota, error), it falls through to the next.

The Alibaba endpoint is workspace-specific: `https://ws-qi5wh5fl237ivx9r.ap-northeast-1.maas.aliyuncs.com/compatible-mode/v1` (workspace `ws-qi5wh5fl237ivx9r`, model `qwen3.7-plus`, 1M context window).

#### `scraper.py` (408 lines)
Hybrid 3-tier async web scraper. The most complex file in the codebase.

**PDF fetch strategy:**
1. Cache check (MD5 of URL → `.scrape_cache/{hash}.json`)
2. `curl_cffi` (TLS fingerprint impersonation — bypasses some bot detection)
3. `pdfplumber` text extraction
4. Fallback: `requests` with browser headers + Referer

**HTML fetch strategy:**
1. Cache check
2. **Crawl4AI** — headless browser, JS rendering, produces markdown + HTML
3. If Crawl4AI returns JS garbage → **Playwright** (stealth mode + `_expand_content()`)
4. Fallback: `curl_cffi` + BeautifulSoup

**`_expand_content()`** (line 187): Clicks "Read More", "Show More", "Show All", "Expand All", `summary`, `[aria-expanded=false]` elements. Solves the problem of truncated legal text on government sites.

**SSO handling:** `_normalize_ssourl()` — for Singapore's `sso.agc.gov.sg` URLs:
- Known Acts → uses pre-mapped PDF URL (e.g., PDPA2012 → `Acts-Supp/26-2012/Published/...?ViewType=Pdf`)
- Unknown Acts → appends `ProvIds=WholeDoc&ViewType=Adv` for full-text view

**`_has_js_garbage()`** (line 306): Detects if Crawl4AI returned a JavaScript shell instead of real content (common on SSO).

#### `extraction.py` (226 lines)
Core extraction pipeline. `process_indicator(model, indicator_id, indicator_data, candidates, max_candidates, rate_delay)`:

1. **Re-rank** candidates (`_rank_candidates`):
   - Seeds (+999), SSO URLs (+50), legislation.gov URLs (+40)
   - Generic portals (-20), irrelevant titles (-15)
2. **Pre-filter** (`prefilter_candidate`): LLM call with `PREFILTER_PROMPT` — "Is this document relevant to this indicator?"
3. **Scrape** (`scrape_url`): Call `hybrid_scrape()`, truncate to `MAX_TEXT_CHARS`
4. **Extract** (`extract_clauses`): LLM call with `EXTRACTION_PROMPT_TEMPLATE` + full document text → JSON
5. **Build row** (`build_row`): Map JSON fields to CSV columns. `Impact_or_comments` = `"Section X: [verbatim clause]\nInterpretation: [explanation]"`

The prompt tells the LLM: "If no relevant clause exists, return `operative_clause: 'N/A'`." This means indicators with no matching law still get a row with N/A, not skipped.

---

### `src/zone3/verifier.py` (276 lines)

Blind re-verification of every citation. Called the "blind" verifier because it receives ONLY the URL and section reference — it must independently re-fetch and locate the section.

**Flow for each row:**

1. `_extract_section_ref(row)` — regex search in `Impact_or_comments` for `Section 26(1)`, `Art. 5`, `Part IV`, etc.
2. `_get_claim_text(row)` — extracts the operative clause text, stripping the "Section X:" prefix
3. `fetch_document(url)` — calls `hybrid_scrape()` from Zone 2 (reuses cache, SSO mapping, Playwright)
4. `_locate_section_deterministic(doc, ref)` — tries regex patterns:
   - Literal: `Section 26(1)`, `S. 26(1)`
   - Gazette format: `26.\uFFFD(1)` (Singapore Government Gazette format)
   - Numeric fallback: `\b26\b` with ±300 char context window
5. If deterministic fails → `_llm_locate_section()` — sends first 12K chars to LLM with "find this section" prompt
6. **Comparison** — normalised text exact match → PASS, fuzzy ratio > 85% → PASS, subset match → PASS, otherwise → FAIL

**Output columns added:** `Verification_Status` (PASS/FAIL/NEEDS_REVIEW/URL_BROKEN), `Verification_Actual_Text`, `Verification_Notes`.

---

## What Works Now (Tested)

### Fully functional end-to-end: Singapore Pillar 6

**Zone 1** — `zone1_singapore_pillar6.json` — discovered sources across all 5 indicators (6.1–6.5). Contains ~80+ candidates from seeds + inventory + Wikipedia. Key sources found:
- Singapore PDPA 2012 (sso.agc.gov.sg)
- PDPC guidance pages (pdpc.gov.sg)
- MTI Digital Economy Agreements page (mti.gov.sg)

**Zone 2** — `zone2_singapore_pillar6.csv` — 5 extracted rows:

| Indicator | Source | Section Extracted |
|-----------|--------|-------------------|
| 6.1 Cross-border data transfers | PDPA 2012 | Section 26(1) — transfer requirements |
| 6.2 Domestic privacy framework | PDPA 2012 | Section 26(1) — same clause (limitation) |
| 6.4 Public-private data sharing | PDPC Guide | Guidance page (no section ref) |
| 6.4 Public-private data sharing | PDPA 2012 | Section 26(1) — transfer requirements |
| 6.5 Digital economy agreements | MTI DEA | Guidance page (no section ref) |

**Zone 3** — `zone2_singapore_pillar6_verified.csv` — 3 PASS, 2 NEEDS_REVIEW (the 2 NEEDS_REVIEW are guidance pages without section references — expected).

**Model used:** Alibaba Qwen 3.7-plus via workspace-specific DashScope endpoint. Cost ~$0.017 per extraction.

---

## What Is Incomplete / Not Working

### Pipeline gaps
| Gap | Details |
|-----|---------|
| **No outputs for Malaysia or Australia** | Zone 1 discovery JSONs exist for all countries in `seeds.py`, but only Singapore Pillar 6 has been run through Zone 2/3. Malaysia and Australia have no extraction or verification results. |
| **Singapore Pillar 7 not run** | Pillar 7 (Digital Trade Facilitation) indicators are defined but never extracted. |
| **No automated end-to-end pipeline** | Each zone must be run manually as a separate CLI command. No orchestrator script. |
| **No scoring/aggregation** | RDTII requires scoring each indicator 0/0.5/1. No code implements this. |

### Discovery quality issues
| Issue | Details |
|-------|---------|
| **Legal inventory CSV over-broad** | `inventory.py` maps ALL rows whose indicator ID prefix matches — import bans, GST, employment law into every indicator. The Zone 1 JSON has many irrelevant candidates that waste extraction capacity. |
| **Wikipedia API limitations** | Wikipedia search is imprecise compared to Google/DuckDuckGo. Some relevant official pages have no Wikipedia external links. |
| **Only 6 cached scrapes** | The `.scrape_cache/` only has 6 entries — likely not all URLs were successfully scraped during the extraction run. |

### Technical limitations
| Issue | Details |
|-------|---------|
| **SSO PDF map only covers PDPA2012** | The `_SSO_PDF_MAP` in `scraper.py` only has one entry. Other Singapore Acts (`POHA`, `CMA`, `EA`, etc.) don't have mapped PDF URLs and would fall through to Crawl4AI which gets a JS shell. |
| **FIRECRAWL_API_KEY unused** | The key is in `.env` but the project switched to Wikipedia API. The key is loaded nowhere. |
| **pytesseract/pdf2image installed but unused** | These dependencies are in `requirements.txt` and were originally intended for OCR fallback on scanned PDFs, but the current code never imports them. |
| **DEFAULT_MODEL parsing fragile** | Comma-split model string with `alibaba:qwen3.7-plus` gets split at `:` which could break if model names contain colons. |
| **Playwright sync-in-async** | `sync_playwright()` is wrapped in `run_in_executor` rather than using native `async_playwright()`. Works but suboptimal. |
| **Crawl4AI instantiated per URL** | A new browser instance per scrape — slow. Should reuse a persistent instance. |

### Zone 3 limitations
| Issue | Details |
|-------|---------|
| **LLM fallback gets 12K chars max** | `_llm_locate_section` only sends the first 12K characters — misses sections that appear later in long documents. |
| **No Australian/Malaysian document format support** | Pattern matching is tuned for Singapore Gazette format (`26.\uFFFD(1)`). Australian (AustLII) and Malaysian formats may need different patterns. |
| **No PDF auto-detection** | If a URL serves a PDF without `/pdf/` or `ViewType=Pdf` in the path, the old code didn't detect it. (Fixed by using `hybrid_scrape` which handles this automatically.) |

---

## Configuration & API Keys

From `.env`:

| Key | Used For | Status |
|-----|----------|--------|
| `DASHSCOPE_API_KEY` | Alibaba Qwen 3.7-plus (primary LLM) | ✅ Active |
| `OPENROUTER_API_KEY` | OpenRouter LLM fallback | ⚠️ Token depleted |
| `GEMINI_API_KEY` | Google Gemini fallback | ⚠️ Rate limited |
| `OLLAMA_API_KEY` | Ollama Cloud fallback | ⚠️ Free models too weak |
| `FIRECRAWL_API_KEY` | Firecrawl (scraper) | ❌ Unused |

**Alibaba workspace details:**
- Endpoint: `https://ws-qi5wh5fl237ivx9r.ap-northeast-1.maas.aliyuncs.com/compatible-mode/v1`
- Model: `qwen3.7-plus`
- Context: 1M tokens
- Auth: `Authorization: Bearer {DASHSCOPE_API_KEY}`
- Cost: ~$0.017 per extraction (1K input + 500 output tokens)

---

## How to Run

```bash
# Step 1: Discover sources
python zone1_discovery.py --country singapore --pillar 6

# Step 2: Extract clauses (takes ~2-3 min per indicator with rate delay)
python zone2_extraction.py --country singapore --pillar 6

# Step 3: Verify citations
python zone3_blindverifier.py --input outputs/zone2/zone2_singapore_pillar6.csv

# Full run (all 3 countries, both pillars)
python zone1_discovery.py
```

Key flags for Zone 2:
- `--model alibaba:qwen3.7-plus` — use Alibaba (current best)
- `--max-candidates 3` — only process top 3 candidates (faster)
- `--rate-delay 3.0` — seconds between LLM calls (avoids rate limits)
- `--limit 1` — process only 1 indicator (quick test)

---

## Key Design Decisions

1. **Wikipedia as search proxy:** When Google/DuckDuckGo are blocked, Wikipedia's API provides external links to official government pages. It's a clever workaround but less comprehensive.

2. **Comma-separated model fallback:** `"alibaba:qwen3.7-plus,gemini,ollama:gemma4"` — if Alibaba fails, try Gemini, then Ollama. Resilient but the parsing is fragile.

3. **Blind verification:** Zone 3 deliberately has NO access to the Zone 2 extracted text or intermediate data. It re-fetches documents independently to avoid confirmation bias. This is a strong quality gate.

4. **File-based storage:** No database. JSON for discovery, CSV for extraction, also CSV for verification. Simple, debuggable, but doesn't scale beyond hackathon scope.

5. **`Impact_or_comments` as combined field:** The extracted clause and its interpretation are concatenated into one CSV column (`"Section 26(1): [clause]\nInterpretation: [explanation]"`). This makes the CSV human-readable but couples the data — Zone 3 has to reverse-engineer the split.

---

## Summary

| Aspect | Status |
|--------|--------|
| Architecture | 3-zone pipeline: Discover → Extract → Verify |
| Countries | Singapore (working), Malaysia (partial), Australia (partial) |
| Pillars | 6 (Data Protection) partially done, 7 (Trade Facilitation) not started |
| What works end-to-end | Singapore Pillar 6: 3 PASS, 2 NEEDS_REVIEW |
| Primary LLM | Alibaba Qwen 3.7-plus, ~$0.017/extraction |
| Search engine | Wikipedia API (proxy for blocked search engines) |
| Scraper | 3-tier hybrid: Crawl4AI → Playwright → curl_cffi + PDF |
| Storage | JSON (discovery), CSV (extraction + verification) |
| Scoring | No scoring implemented (last missing piece for RDTII) |
| Biggest gap | Only 1/6 country-pillar combos fully processed |
