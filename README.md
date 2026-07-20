# Pillar AI — AI Tool for Digital Trade Regulatory Analysis

UN Global Hackathon on AI for Digital Trade Regulatory Analysis
Team: PillarAI | Round: 1 (Final)
Last updated: 2026-07-20

---

## What This Tool Does

This tool automates two tasks required by the UN Regional Digital Trade Integration Index (RDTII):

**Task 1 — Automated Evidence Discovery**
Given an economy and pillar, the tool crawls official government legal portals, seed inventories, Wikipedia, and web search to discover relevant legislation — including scanned/image-based PDFs — and extracts clean, structured text.

**Task 2 — Intelligent Mapping, Verification & Scoring**
The extracted text is mapped to specific RDTII indicator IDs (6.1-6.5, 7.1-7.5). Each provision is recorded with article-level citation, verbatim snippet, and discovery tag (NEW/KNOWN). Citations are independently verified by re-fetching the source. A weighted RDTII 2.1 score is computed.

**Coverage:** Singapore, Malaysia, Australia | Pillars 6 (Cross-border Data Flows) and 7 (Domestic Data Protection)

---

## Quick Start

A reviewer with basic Python knowledge should be able to run this in under 10 minutes.

### 1. Clone the repository

```bash
git clone https://github.com/adriel-babalola/pillar_ai.git
cd pillar_ai
```

### 2. Set up the environment

```bash
# Python 3.10+ required
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
python -m playwright install chromium
```

### 3. Configure API keys

```bash
Copy-Item .env.example .env  # Windows
# cp .env.example .env       # macOS/Linux
```

Open `.env` and set at least one LLM API key. The pipeline uses Alibaba DashScope as primary:

```env
DASHSCOPE_API_KEY=sk-...      # Primary LLM (Alibaba Qwen 3.7 Plus)
OPENROUTER_API_KEY=sk-or-...  # Fallback LLM
GEMINI_API_KEY=...            # Fallback LLM
```

### 4. Run the validation script

```bash
python check_env.py
```

### 5. Run the pipeline

```bash
# Single country, both pillars
python run.py --country sg

# All 3 countries x 2 pillars
python run.py --all
```

**Output:** Results are written to `outputs/zone1/`, `outputs/zone2/`, `outputs/zone3/`, and `outputs/zone4/`.

---

## Full Usage

```bash
python run.py [--country {sg|my|au}] [--pillar {6|7}] [--zone {discovery,extraction,verify,score,all}]
              [--all] [--model MODEL_ID] [--limit N] [--rate-delay SECONDS]
```

| Goal | Command |
|------|---------|
| Single country, both pillars | `python run.py --country sg` |
| Single pillar | `python run.py --country sg --pillar 6` |
| All 3 countries x 2 pillars | `python run.py --all` |
| Discovery only | `python run.py --zone discovery --country sg` |
| Extraction only | `python run.py --zone extraction --country au --pillar 7` |
| Verify existing extraction | `python run.py --zone verify --country sg --pillar 6` |
| Score existing data | `python run.py --zone score --country sg --pillar 6` |

### Environment Variables

```env
# Required (at least one LLM backend)
DASHSCOPE_API_KEY=sk-...      # Primary: Alibaba DashScope
OPENROUTER_API_KEY=sk-or-...  # Fallback: OpenRouter
GEMINI_API_KEY=...            # Fallback: Google Gemini
OLLAMA_API_KEY=...            # Fallback: Ollama Cloud

# Model routing (comma-separated fallback chain)
DEFAULT_MODEL=alibaba:qwen3.7-plus,gemini,ollama:gemma4

# Optional
PROXY_URL=http://user:pass@proxy-server:port
```

---

## Pipeline Architecture (4-Zone System)

The pipeline is divided into four sequential zones. Each zone reads from the previous zone's output and writes its own structured output to `outputs/`.

```
Economy + Pillar
       |
       v
+----------------------------+    outputs/zone1/
| ZONE 1: DISCOVERY          |    zone1_{country}_pillar{pillar}.json
|                            |    Dict of indicator_id -> list of candidates
|  1. Seed URLs              |
|     (curated, always 1.0)  |
|  2. Inventory CSV          |
|     (391-row legal db)     |
|  3. Wikipedia API          |
|     (curated pages + text) |
|  4. DuckDuckGo HTML search |
|     (official sites only)  |
+----------------------------+
       |  Candidate URLs + relevance scores
       v
+----------------------------+    outputs/zone2/
| ZONE 2: EXTRACTION         |    zone2_{country}_pillar{pillar}.csv
|                            |    16 columns, one row per clause
|  1. Pre-filter (LLM)       |
|     "Is this relevant?"    |
|  2. Hybrid scrape          |
|     3-tier fetcher + OCR   |
|  3. LLM clause extraction  |
|     Qwen 3.7 Plus          |
+----------------------------+
       |  Act name, section, verbatim, confidence
       v
+----------------------------+    outputs/zone3/
| ZONE 3: VERIFICATION       |    zone2_{country}_pillar{pillar}_verified.csv
|                            |    Same as Zone 2 + 3 verdict columns
|  1. Re-fetch document      |
|  2. Regex section search   |
|  3. Fuzzy text comparison  |
|  4. LLM fallback (if ambig)|
+----------------------------+
       |  PASS / FAIL / NEEDS_REVIEW verdicts
       v
+----------------------------+    outputs/zone4/
| ZONE 4: SCORING            |    zone4_{country}_pillar{pillar}_score.txt
|                            |    zone4_{country}_pillar{pillar}_score.csv
|  1. RDTII 2.1 rubric per   |
|     indicator              |
|  2. Weighted average       |
+----------------------------+
       |
       v
  Final score (0=open, 1=restrictive)
```

### Data Flow Summary

```
Zone 1 outputs candidate URLs with relevance scores.
Zone 2 reads those URLs, scrapes full text, and extracts clauses via LLM.
Zone 3 re-fetches each source independently and verifies citation accuracy.
Zone 4 applies the RDTII 2.1 weighted rubric and produces a final pillar score.
```

---

## Zone 1: Discovery — Finding Candidate Legislation

Discovery combines four independent sourcing strategies per indicator, with global deduplication across all strategies.

### Sourcing Strategy

**1. Seed URLs** (`src/zone1/seeds.py`)
Manually curated URLs from legal research. These always receive `relevance_score=1.0` and skip the LLM pre-filter in Zone 2 (treated as known-good). There are 30+ seeds per country-pillar combination, covering the core data protection and cybersecurity statutes.

**2. Legal Inventory CSV** (`src/zone1/inventory.py`)
A 391-row seed dataset of trade policies (`Singapore, Malaysia, Australia, Legal Inventory.csv`). Rows are filtered to Pillar 6/7 relevant ones (~30 per country) by checking:
- Cluster = "Digital governance policies"
- Name matches "Cross-border data policies" or "Domestic data protection & privacy"
- Act title matches data/cyber keywords

Each filtered row is mapped to its corresponding RDTII indicator ID. Inventory entries also receive `relevance_score=1.0`.

**3. Wikipedia** (`src/zone1/discovery_wikipedia.py`)
Uses the Wikipedia API (`en.wikipedia.org/w/api.php`) with two approaches:
- **Curated page titles** — manually chosen Wikipedia pages guaranteed relevant to each indicator. External links from these pages are extracted and filtered to official government URLs.
- **Text search** — searches Wikipedia article text using indicator-specific queries. Results are scored by `relevance_score()` and only kept if score > 0.5.

Wikipedia page text is fetched section by section with rate limiting (0.3s–0.5s delays between requests) to respect API limits.

**4. DuckDuckGo** (`src/zone1/discovery_searchengine.py`)
Direct HTTP search against `html.duckduckgo.com/html/` with:
- Site filters (`.gov.sg`, `.gov.my`, `.gov.au`, etc.)
- Indicator-specific query themes
- Custom HTML parser (`_DDGResultParser`) that extracts result URLs, titles, and snippets

DuckDuckGo may return 0 results on networks where it is blocked — the pipeline handles this gracefully by moving to the next indicator.

### Deduplication & Ranking

A global `seen_urls` set prevents the same URL from appearing under multiple indicators. Within each indicator, URLs are deduplicated across seeds, inventory, Wikipedia, and DuckDuckGo (seeds take priority).

### Output Format

```json
{
  "6.1": [
    {
      "title": "Personal Data Protection Act 2012",
      "url": "https://laws.sg/legislation/personal-data-protection-act-2012",
      "relevance_score": 1.0,
      "source": "seed",
      "discovery_tag": "KNOWN",
      "snippet": "An Act to govern the collection, use and disclosure of personal data..."
    }
  ]
}
```

Each candidate carries: `indicator`, `title`, `url`, `snippet`, `query_used`, `relevance_score`, `source` (seed/inventory/wikipedia/searchengine), and `discovery_tag` (KNOWN/NEW).

---

## Zone 2: Extraction — LLM-Powered Clause Extraction

Zone 2 is the core of the pipeline. For each discovery candidate, it runs prefiltering, scraping, and LLM extraction.

### Step 1: Prefiltering

Seed URLs skip prefiltering (known-good). All other candidates go through an LLM prefilter:
- Prompt: `PREFILTER_PROMPT` asks "Is this document relevant to indicator X?"
- Response: JSON `{"relevant": true/false}`
- Irrelevant candidates are skipped, saving scraping and LLM costs
- Retries on empty/invalid response (up to 3 attempts with 2s delay)

### Step 2: Hybrid Scraping (`src/zone2/scraper.py`)

The scraper uses a three-tier strategy with caching:

```
hybrid_scrape(url)
  |
  +-- Check cache (.scrape_cache/ keyed by URL MD5)
  |
  +-- Is PDF?
  |     +-- curl_cffi (TLS impersonation) -> pdfplumber -> text
  |     +-- If pdfplumber fails -> Tesseract OCR fallback
  |     +-- SG SSO PDFs: _SSO_PDF_MAP has known URLs (PDPA2012)
  |
  +-- Is HTML?
        +-- Crawl4AI (renders JavaScript) -> text
        +-- Playwright fallback (stealth mode + content expansion)
        +-- curl_cffi + BeautifulSoup fallback
        +-- LOM Malaysia: _has_js_garbage() detects navigation chrome
```

**Scraper features:**
- **Cache:** `.scrape_cache/` stores scraped text as JSON keyed by URL MD5. Subsequent runs are instant.
- **SSO normalization:** `_normalize_ssourl()` adds `?ProvIds=WholeDoc&ViewType=Adv` to SSO URLs and `&lang=EN` to LOM Malaysia URLs.
- **Alternate URLs:** If scraping fails or returns <200 characters, `_generate_alternate_urls()` tries alternative formats (HTML version of a PDF, laws.sg mirror, etc.).
- **OCR fallback:** Tesseract + pdf2image for scanned PDFs where pdfplumber cannot extract text.

### Step 3: LLM Clause Extraction

The LLM is given the full scraped text (up to 45,000 tokens) plus indicator-specific extraction instructions. The prompt instructs the LLM to return ONLY valid JSON:

```json
{
  "operative_clause": "An organisation must not transfer...",
  "section_reference": "Section 26(1)",
  "act_title": "Personal Data Protection Act 2012",
  "law_number_ref": "Act 26 of 2012",
  "coverage": "Cross-cutting",
  "timeframe": "Since 2014; Last amended 2020",
  "last_amended": "2020",
  "location_reference": "Page 12",
  "interpretation": "This provision establishes a conditional restriction..."
}
```

**Extraction prompt design principles:**
- System prompt warns the LLM not to paraphrase — extract verbatim text
- Extraction instructions in each indicator definition tell the LLM exactly what to look for
- JSON parsing (`parse_json_response()`) strips markdown fences before parsing
- Retries on empty or invalid JSON (up to 3 attempts)

### Candidate Ranking (`_rank_candidates()`)

Before extraction, candidates are ranked to prioritize the most promising sources:

| Criterion | Score adjustment |
|-----------|-----------------|
| Seed URL | +999 (always processed first) |
| SSO / legislation.gov.au URL | +25 to +50 |
| Official domain (pdpc, oaic, csa) | +20 |
| "Act" or "regulation" in title | +15 |
| Penalised domain (mom, go.gov.sg/explainers) | -20 |
| Title <20 characters | -5 |

### LLM Backend (comma-separated fallback chain)

The model string in `src/zone2/config.py` (`DEFAULT_MODEL`) supports multi-provider fallback:

```
alibaba:qwen3.7-plus,gemini,ollama:gemma4
```

The `llm_call()` function tries providers in order:
1. `alibaba:` prefix → Alibaba DashScope workspace endpoint
2. `gemini` → Google Gemini 2.5 Flash
3. `ollama:` prefix → Ollama Cloud
4. Any other string → OpenRouter

If the primary provider fails (timeout, rate limit, auth error), the next in the chain is tried. Each extraction costs approximately $0.017 on Alibaba Qwen 3.7 Plus.

---

## Zone 3: Blind Citation Verification

Zone 3 is a quality gate that independently verifies every citation from Zone 2. It re-fetches the source document and compares the claimed clause against the actual text.

### Verification Process

For each row in the Zone 2 CSV:

```
1. Extract section reference from Article_Section column
   (regex: Section, Article, Part, Division, APP, Clause,
    Seksyen, Perkara, Bahagian, etc.)

2. Generate search patterns for flexible matching
   (including Gazette format: "26.  (1)" with flexible whitespace)

3. Re-fetch document via hybrid_scrape()

4. Locate section deterministically
   - Regex search for section reference in document text
   - Section-by-section search for structured documents

5. Compare claimed text vs actual text
   - Exact match -> PASS
   - Fuzzy ratio > 0.85 -> PASS
   - Claim text is substring of actual -> PASS
   - Otherwise -> LLM fallback

6. LLM fallback
   - Send LLM: section ref + claimed snippet + full document text
   - LLM locates the section and compares
   - Returns JSON: {status, actual_text, explanation}
```

### Verdict Categories

| Verdict | Meaning |
|---------|---------|
| PASS | Claimed text substantially matches actual text at the cited section |
| FAIL | Claimed text differs from actual text, or section doesn't exist |
| NEEDS_REVIEW | Ambiguous — e.g., section reference unclear, document too short |
| URL_BROKEN | Source URL is unreachable (403, 404, timeout) |

### Section Pattern Coverage

The verifier handles multiple legal citation formats across all three economies:

**Singapore:** `Section 26(1)`, `s. 26`, `S. 26`, `Part IV`, `Division 2`
**Australia:** `APP 8`, `Clause 1.4`, `Schedule 1`, `s 8`, `Part III`
**Malaysia:** `Seksyen 129`, `Perkara 5`, `Bahagian IV`, `Perenggan`

---

## Zone 4: Scoring — RDTII 2.1 Methodology

Zone 4 applies the official RDTII 2.1 weighted rubric to produce a quantitative score per pillar. Each indicator scores 0 (fully open), 0.5, or 1 (fully restrictive), and the pillar score is a weighted average.

### Pillar 6 Weights (Cross-border Data Flows)

| Indicator | Description | Weight | Score logic |
|-----------|-------------|--------|-------------|
| 6.1 | Ban and local processing requirements | 38% | Checks for conditional language (except/unless/subject to) BEFORE horizontal ban check. Conditional regimes = 0.5 (not 1.0). Horizontal personal data ban = 1.0. |
| 6.2 | Local storage requirements | 12% | Detects local storage, data localization, data residency keywords. Horizontal = 1.0, sectoral = 0.5. |
| 6.3 | Infrastructure requirements | 31% | Detects data centre, server, computing infrastructure requirements. |
| 6.4 | Conditional flow regimes | 12% | Consent, adequacy, contractual safeguards, BCRs. Horizontal = 1.0. |
| 6.5 | Binding data transfer agreements | 8% | Non-regulatory — scored via external DBs (CPTPP, RCEP, DEPA membership). Auto-skipped in extraction. |

### Pillar 7 Weights (Domestic Data Protection)

| Indicator | Description | Weight | Score logic |
|-----------|-------------|--------|-------------|
| 7.1 | Legal basis for processing | 31% | Country-specific overrides: MY PDPA=0.5 (sectoral, commercial only). SG PDPA=0.0. Detects "commercial transaction" scope for MY. |
| 7.2 | Purpose limitation | 31% | Computer misuse laws = 0.5 (not dedicated cybersecurity). Dedicated cybersecurity act = 0.0. |
| 7.3 | Data subject rights | 16% | Minimum retention period vs "as long as necessary". Specific retention period = 1.0. |
| 7.4 | Data breach notification | 6% | DPO + horizontal = 1.0. DPO sectoral = 0.5. DPIA only = 0.25. |
| 7.5 | Enforcement & penalties | 16% | Government access with/without judicial authorization. Without judicial authorization = 1.0. |

### Score Calculation

```
Pillar Score = sum(Indicator_Weight * Indicator_Score for all indicators)
             where indicator weights sum to 100%
```

Scores range from **0 (fully open)** to **1 (fully restrictive)**.

### Current Scores

These are pipeline-derived estimates from LLM-extracted clauses, not legal determinations. Source URLs, section references, verbatim snippets, and verification status are available in the output CSVs for scrutiny.

| Country | Pillar | Score |
|---------|--------|-------|
| Singapore | 6 | 0.3069 |
| Singapore | 7 | 0.3800 |
| Malaysia | 6 | 0.7327 |
| Malaysia | 7 | 0.6900 |
| Australia | 6 | 0.4257 |
| Australia | 7 | 0.2200 |

---

## Project Structure

```
pillar_ai/
  run.py                            # Orchestrator — runs any zone(s) for one/all combos
  check_env.py                      # Env validator stub -> scripts/check_env.py
  zone1_discovery.py                # Zone 1 CLI entry
  zone2_extraction.py               # Zone 2 CLI entry
  zone3_blindverifier.py            # Zone 3 CLI entry
  generate_hackathon_output.py      # Builds formatted XLSX for hackathon submission

  scripts/
    check_env.py                    # Full environment validator
    reset_outputs.py                # Deletes all pipeline outputs

  src/
    prompts.py                      # Pillar 6 & 7 indicator definitions + LLM prompts
    zone1/                          # Discovery logic
      config.py                     # Country configs, domain patterns, aliases
      indicators.py                 # Indicator query themes for search generation
      seeds.py                      # Curated seed URLs per country x pillar x indicator
      inventory.py                  # 391-row CSV filter + indicator mapping
      discovery.py                  # Main orchestration: seeds -> inventory -> WP -> DDG
      discovery_wikipedia.py        # Wikipedia API: curated pages + text search
      discovery_searchengine.py     # DuckDuckGo HTTP search with HTML parser
      utils.py                      # URL validation, relevance scoring, query generation
    zone2/                          # Extraction logic
      config.py                     # API keys, model config, CSV field names
      client.py                     # llm_call() with fallback chain
      extraction.py                 # process_indicator(): prefilter -> scrape -> extract
      scraper.py                    # hybrid_scrape(): 3-tier fetcher with cache
      embedding.py                  # TF-IDF similarity scoring for ranking
    zone3/                          # Verification logic
      verifier.py                   # Blind citation verification engine
    zone4/                          # Scoring logic
      scoring.py                    # RDTII 2.1 weighted rubrics for 10 indicators

  outputs/
    zone1/                          # Discovery JSON files
    zone2/                          # Extraction CSV files (16 columns)
    zone3/                          # Verified CSV files (+3 verdict columns)
    zone4/                          # Score report TXT + CSV files
    final_output/                   # Hackathon submission XLSX

  .scrape_cache/                    # MD5-keyed scraped text cache
```

---

## Key Modules

| Module | File | Description |
| :----- | :--- | :---------- |
| Discovery Orchestrator | `src/zone1/discovery.py` | Coordinates seed + inventory + Wikipedia + DuckDuckGo discovery per indicator |
| Wikipedia Proxy | `src/zone1/discovery_wikipedia.py` | Curated Wikipedia pages -> external links to gov URLs |
| Search Engine | `src/zone1/discovery_searchengine.py` | Direct DuckDuckGo HTML search with site filter |
| Hybrid Scraper | `src/zone2/scraper.py` | 3-tier fetcher (Crawl4AI, Playwright, curl_cffi, OCR) |
| LLM Client | `src/zone2/client.py` | Comma-separated fallback chain (Alibaba -> Gemini -> Ollama -> OpenRouter) |
| LLM Extraction | `src/zone2/extraction.py` | Prefilter -> scrape -> LLM extract -> CSV row |
| Blind Verifier | `src/zone3/verifier.py` | Re-fetch -> regex section search -> fuzzy comparison -> LLM fallback |
| Scoring Engine | `src/zone4/scoring.py` | RDTII 2.1 weighted rubrics for 10 indicators |
| Prompts & Indicators | `src/prompts.py` | All extraction prompts, prefilter prompts, indicator definitions |

---

## Swapping the LLM

The pipeline uses a comma-separated fallback chain with no vendor lock-in. Change one config value to switch.

### Current default chain (in `src/zone2/config.py`)

```
DEFAULT_MODEL = "alibaba:qwen3.7-plus,gemini,ollama:gemma4"
```

### Use only OpenRouter

```env
DEFAULT_MODEL=gpt-4o
OPENROUTER_API_KEY=sk-or-...
```

### Use only Gemini

```env
DEFAULT_MODEL=gemini
GEMINI_API_KEY=...
```

### Use only Ollama Cloud

```env
DEFAULT_MODEL=ollama:gemma4
OLLAMA_API_KEY=...
```

### CLI override

```bash
python run.py --country sg --model claude-3-5-sonnet:free
```

No other code changes required. The LLM interface is abstracted in `src/zone2/client.py`.

---

## Swapping the OCR Engine

The hybrid scraper uses Tesseract as the OCR fallback for scanned PDFs.

| Engine | Config | Notes |
| :----- | :----- | :---- |
| Tesseract | Add to PATH | Free, open-source; requires separate install |
| Azure Document Intelligence | N/A (not integrated) | Would require new provider class in scraper |

To use a different OCR engine, implement a new function in `src/zone2/scraper.py` following the `_ocr_page()` pattern.

---

## Supported Economies & Portals

| Economy | Official Portals | Language | Notes |
| :------ | :--------------- | :------- | :---- |
| Singapore | sso.agc.gov.sg, laws.sg, pdpc.gov.sg | English | SSO returns 403; uses PDF map + laws.sg |
| Malaysia | lom.agc.gov.my, pdp.gov.my, bnm.gov.my | English / Malay | LOM is JS-heavy; PDF extraction primary |
| Australia | legislation.gov.au, austlii.edu.au, oaic.gov.au | English | OData API available for structured text |

---

## Output Format

Each zone produces one or more output files in `outputs/`:

### Zone 1: Discovery JSON (`zone1_{country}_pillar{pillar}.json`)

```json
{
  "6.1": [
    {
      "title": "Personal Data Protection Act 2012",
      "url": "https://...",
      "relevance_score": 1.0,
      "source": "seed",
      "discovery_tag": "KNOWN"
    }
  ]
}
```

### Zone 2: Extraction CSV (16 columns)

| Column | Description |
| :----- | :---------- |
| Economy | Country name |
| Pillar_ID | 6 or 7 |
| Indicator_ID | RDTII code (6.1-6.5, 7.1-7.5) |
| Act_and_or_practice | Full official law name |
| Law_Number_Ref | Official act number (e.g. "Act 709") |
| Last_Amended | Year of latest amendment |
| Coverage | Cross-cutting or Sectoral |
| Article_Section | Specific section/article |
| Discovery_Tag | KNOWN (seed) or NEW (discovered) |
| Location_Reference | PDF page or HTML anchor |
| Verbatim_Snippet | Exact operative clause text |
| Mapping_Rationale | Legal interpretation |
| Impact_or_comments | Combined field |
| Timeframe | "Since Month Year; Last amended Month Year" |
| References | Source URL |
| Confidence | high, medium, or low |

### Zone 3: Verified CSV (Zone 2 columns + 3 verification columns)

- `Verification_Status`: PASS / FAIL / NEEDS_REVIEW / URL_BROKEN
- `Verification_Actual_Text`: Actual text found at section
- `Verification_Notes`: Explanation of verdict

### Zone 4: Score Report (TXT + CSV)

```
=========================================================
  RDTII SCORE REPORT - Singapore, Pillar 6
=========================================================
  6.1  |  Score: 0.5  |  Weight: 38%  |  Weighted: 0.1900
  ...
-------------------------------------------------
  PILLAR SCORE: 0.3069  (range: 0=open, 1=restrictive)
=========================================================
```

### Hackathon Submission XLSX

```bash
python generate_hackathon_output.py
```

Produces `outputs/final_output/hackathon_submission.xlsx` with 51 rows covering all 10 indicator IDs across 3 countries, formatted per the official template.

---

## Actual Cost Per Document

**Measured costs from real pipeline runs (July 2026).**

| Component | Engine used | Measured cost |
| :-------- | :---------- | :------------ |
| LLM extraction | Alibaba Qwen 3.7 Plus (DashScope) | $0.017 per extraction |
| LLM verification | Alibaba Qwen 3.7 Plus | $0.008 per verification |
| Embedding prefilter | TF-IDF (scikit-learn) | $0.000 (local) |
| Crawling | Crawl4AI + Playwright | $0.000 (local) |
| OCR | Tesseract | $0.000 (local) |
| **Total per extraction** |  | **~$0.017** |
| **Total per country/pillar** (~10 extractions) |  | **~$0.25** |
| **Full pipeline (6 combos)** |  | **~$1.50** |

**Measured on:** 2026-07-18/19
**Token counts:** ~15,000-45,000 input tokens per extraction, ~250-800 output tokens
**Wall-clock time:** ~10-15 minutes per country/pillar combo (LLM rate-limited at 3s delay)

### Cost with open-weight swap

| Component | Engine | Estimated cost |
| :-------- | :------ | :------------- |
| LLM | Ollama Cloud (Gemma 4) | $0.000 (free tier) |
| OCR | Tesseract | $0.000 |
| **Total** |  | **$0.000** |

---

## Design Decisions & Gotchas

### Why conditional regimes score 0.5 not 1.0 for 6.1

The scoring rubric distinguishes between total bans (1.0) and conditional regimes (0.5). The `score_6_1()` function checks for conditional language (`except`, `unless`, `subject to`) BEFORE checking for horizontal ban keywords — otherwise a conditional regime with strong language like "must not transfer" would be misclassified as a total ban.

### Why Alibaba DashScope is primary

The Alibaba workspace endpoint (`ws-qi5wh5fl237ivx9r.ap-northeast-1.maas.aliyuncs.com`) provides Qwen 3.7 Plus with a 1M context window at ~$0.017/extraction. This is significantly cheaper than GPT-4o (~$0.15/extraction) while achieving comparable extraction quality.

### Why DuckDuckGo uses direct HTTP

The `duckduckgo-search` Python library (v7/8) is broken — it hangs due to DNS-blocked fallback search engines (Yahoo, Yandex, Google). The pipeline replaces it with direct HTTP to `html.duckduckgo.com/html/` with a custom HTML parser. Returns 0 results quietly on restricted networks.

### Why SSO Singapore needs a PDF map

SSO (sso.agc.gov.sg) returns HTTP 403 to automated requests due to Cloudflare protection. The `_SSO_PDF_MAP` in `scraper.py` provides known direct PDF URLs for key acts like PDPA 2012. Other SSO URLs fall back to laws.sg or secondary articles.

### Why indicator 6.5 is auto-skipped

Indicator 6.5 (Binding data transfer agreements) asks whether a country is party to CPTPP, RCEP, DEPA, or similar agreements. This is a non-regulatory indicator — it requires external database knowledge, not legislation text. The extraction pipeline auto-skips it and the scoring module handles it via hardcoded country membership data.

---

## Reset Outputs

The repo ships with reference pipeline outputs (Zone 1-4 CSVs, score reports, and the hackathon submission XLSX) so newcomers can inspect expected format and behaviour without running the pipeline.

To delete all outputs and start fresh:

```bash
# Preview what would be deleted
python scripts/reset_outputs.py --dry-run

# Delete with confirmation prompt
python scripts/reset_outputs.py

# Skip prompt (CI / scripting)
python scripts/reset_outputs.py --force
```

This clears `outputs/zone1/`, `outputs/zone2/`, `outputs/zone3/`, `outputs/zone4/`, `outputs/final_output/`, and `.scrape_cache/`. Source code, config, and the inventory CSV are not touched.

---

## Known Limitations

- **SSO Singapore returns 403.** SG legislation relies on laws.sg and known PDF maps. PDPA 2012 is covered; other SG acts may fall back to secondary articles.
- **BNM RMiT PDF (bnm.gov.my) returns 403.** MY indicator 6.3 (Infrastructure requirements) scores 0.0 with a limitation note.
- **DuckDuckGo blocked on some networks.** Discovery falls back to Wikipedia-only mode. Returns 0 results quietly.
- **Large PDFs >500 pages.** Zone 3 verification may time out. Increase timeout or skip large docs.
- **Tesseract OCR must be installed separately.** Required only for scanned PDFs. Install from UB-Mannheim release and add to PATH.
- **Playwright browsers must be installed.** Run `python -m playwright install chromium` after `pip install -r requirements.txt`.
- **Indicator 6.5 is non-regulatory.** This indicator (binding data transfer agreements) is auto-skipped in extraction and scored via external database knowledge (CPTPP, RCEP, DEPA membership).
- **Indicators 7.2 and 7.4 have limited extraction coverage.** Purpose limitation (7.2) and data breach notification (7.4) are not extracted as standalone provisions but are addressed in scoring.
- **No automated test suite.** The pipeline is verified manually by comparing outputs against known RDTII scores.
- **LLM extraction quality depends on document formatting.** Scanned PDFs or JS-heavy HTML may produce lower-quality extractions.

---

## Running the Test Suite

This repository does not currently include an automated test suite. Pipeline correctness is validated by:

1. Running `check_env.py` to verify all dependencies and API keys
2. Comparing extraction outputs against known RDTII scores
3. Blind verification (Zone 3) that independently confirms each citation
4. Manual review of the hackathon submission XLSX

---

## CI/CD with GitHub Actions

The repository includes `.github/workflows/pillar.yml` for automated execution on free GitHub runners:

1. Add LLM API keys as GitHub Secrets (`Settings` -> `Secrets and variables` -> `Actions`)
2. Navigate to `Actions` tab -> `Run Pillar AI Pipeline` -> `Run workflow`
3. Select country, pillar, and zone options
4. Download outputs as artifact when complete (retained 90 days)

---

## Team

| Role | Name | Responsibility |
| :--- | :--- | :------------- |
| Technical Lead | Adriel Babalola | AI architecture, pipeline, scraping, LLM integration |
| Substantive Lead | [Name] | Legal/policy analysis, RDTII methodology, output QA |
| Data Engineer | [Name] | Legal inventory, seed curation, verification |

---

## License

This project is released under the **Apache License 2.0** in accordance with the hackathon submission requirements.

---

## Key Dates

| Date | Milestone |
| :--- | :-------- |
| 20 July 2026 | **Round 1 submission deadline — all 44 shortlisted teams submit** |
| 31 July 2026 | 20 teams shortlisted announced |
| 3 August 2026 | Live online pitching session |
| 5 August 2026 | 5 finalists announced |
| October 2026 | Grand Finale — Bangkok |

---

## Acknowledgements

Built as part of the UN Global Hackathon on AI for Digital Trade Regulatory Analysis, organised by UNESCAP and KMITL.
