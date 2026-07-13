# Pillar AI — Full Codebase Context (Generated June 2026)

> **Purpose:** Comprehensive analysis of all code, data, configuration, and current state for anyone (or any AI) onboarding to this project. Covers every file, its role, key code snippets, and known issues.

---

## 1. Project Structure (File Tree)

```
C:\Users\User\Desktop\pillar_ai\
├── .env                            # API keys (FIRECRAWL, OPENROUTER, GEMINI)
├── .gitignore                      # Ignores .env, .env.example
├── context.md                      # Original project context doc (352 lines)
├── README.md                       # Brief usage instructions (18 lines)
├── requirements.txt                # crawl4ai, python-dotenv, openai
├── prompts.py                      # Shared prompt templates & indicator defs (189 lines)
├── zone1_discovery.py              # Instance 1: Source Discovery (499 lines)
├── zone1_search.py                 # Early Firecrawl prototype (76 lines, deprecated)
├── zone2_extraction.py             # Instance 2: Extraction & Mapping (437 lines)
├── zone1_singapore_pillar6.json    # Discovery output: SG Pillar 6 (3000+ lines)
├── zone1_singapore_pillar7.json    # Discovery output: SG Pillar 7 (2500+ lines)
├── zone2_singapore_pillar6.csv     # Extraction output: SG Pillar 6 (3 data rows)
├── Singapore, Malaysia, Australia, Legal Inventory.csv  # Reference dataset (391+ rows)
├── debug_output.md                 # Raw search debug artifact
├── context_fornew.md               # THIS FILE
└── .venv\                          # Python virtual environment
```

---

## 2. Configuration & Environment

### `.env` — API Keys (all live, tracked in git history then removed)

```
FIRECRAWL_API_KEY=fc-... (redacted)
OPENROUTER_API_KEY=sk-or-v1-... (redacted)
GEMINI_API_KEY=AIza... (redacted)
```

### `.gitignore`

```
.env
.env.example
```

### `requirements.txt`

```
crawl4ai>=0.9.0
python-dotenv>=1.0.0
openai>=1.0.0
```

---

## 3. Core Source Files

### 3.1 `prompts.py` (189 lines) — Shared Prompt Library

Central repository for prompt templates and RDTII indicator definitions for Pillars 6 & 7.

**Key data structures:**

```python
PILLAR_6_INDICATORS = {
    "6.1": {
        "name": "Ban on transfer and/or local processing requirement",
        "question": "Does this law impose a ban on cross-border data transfer and/or require local processing?",
        "keywords": [
            "cross-border", "transfer", "local processing", "ban", "prohibit",
            "restrict", "personal data", "data localization"
        ],
        "extraction_instructions": "Look for provisions that: (1) Prohibit or restrict transfer of personal data to other countries. (2) Require that personal data be processed or stored locally."
    },
    "6.2": {
        "name": "Local storage requirement",
        "question": "Does this law require personal data to be stored locally?",
        # ...
    },
    "6.3": {
        "name": "Infrastructure requirement",
        "question": "Does this law require local servers or data centres?",
        # ...
    },
    "6.4": {
        "name": "Conditional flow regime",
        "question": "Does this law allow transfer subject to conditions (consent, adequacy, safeguards)?",
        # ...
    },
    "6.5": {
        "name": "Not in binding data transfer agreement",
        "question": "Is this law part of a binding international data transfer agreement (CPTPP, RCEP, DEPA)?",
        # ...
    },
}

PILLAR_7_INDICATORS = {
    "7.1": {"name": "Lack of comprehensive data protection framework", ...},
    "7.2": {"name": "Lack of dedicated cybersecurity framework", ...},
    "7.3": {"name": "Minimum data retention period", ...},
    "7.4": {"name": "DPO or DPIA requirements", ...},
    "7.5": {"name": "Government access to personal data", ...},
}
```

**Prompt templates:**

1. **`PREFILTER_PROMPT`** — LLM prompt to check if a candidate document is relevant before full scraping. Returns `{"relevant": true/false, "confidence": "high"/"medium"/"low"}`.

2. **`EXTRACTION_PROMPT_TEMPLATE`** — Main extraction prompt instructing the LLM to extract verbatim operative clauses, section references, coverage, timeframe, and interpretation. Forces JSON-only output with no markdown fences.

---

### 3.2 `zone1_discovery.py` (499 lines) — Instance 1: Source Discovery

**Role:** Crawls search engines (DuckDuckGo + Bing) via Crawl4AI to find official government legal documents for RDTII indicators.

**CLI Usage:**
```
python zone1_discovery.py --country singapore --pillar 6 --limit 10
python zone1_discovery.py --all  # Process all 6 combos (3 countries x 2 pillars)
```

**Key components:**

#### Country Config (lines 27-65)
```python
COUNTRY_CONFIG = {
    "singapore": {
        "display_name": "Singapore",
        "official_domains": ["gov.sg", "pdpc.gov.sg", "sso.agc.gov.sg", ...],
        "site_filter": "site:gov.sg OR site:pdpc.gov.sg OR site:sso.agc.gov.sg",
        "url_patterns": [r"gov\.sg", r"sso\.agc\.gov\.sg", r"pdpc\.gov\.sg"],
    },
    "malaysia": { ... },
    "australia": { ... },
}
```

#### URL Filtering (line 209)
```python
def is_official_url(url, country_key):
    """Check if URL belongs to an official government domain for this country."""
    patterns = COUNTRY_CONFIG[country_key]["url_patterns"]
    return any(re.search(p, url, re.IGNORECASE) for p in patterns)
```

#### Relevance Scoring (line 215)
```python
def relevance_score(title, snippet, keywords):
    """Score 0-1 based on keyword density in title and snippet."""
    text = f"{title} {snippet}".lower()
    matches = sum(1 for kw in keywords if kw.lower() in text)
    return matches / len(keywords) if keywords else 0
```

#### Search Execution (lines 264-347)
Uses Crawl4AI's `AsyncWebCrawler` with stealth mode, random user agents, and 2-5s delays. Falls back from DuckDuckGo to Bing if blocked. Parses raw markdown results for URLs.

#### Orchestrator (lines 395-430)
```python
async def process_country_pillar(country_key, pillar_id, limit, crawler):
    """Run discovery for one country + pillar combination and save JSON."""
    all_candidates = {}
    for ind_id in sorted(pillar_data.keys()):
        queries = generate_queries(ind_data, display_name, site_filter)
        results = await search_indicator(ind_id, queries, ...)
        all_candidates[ind_id] = results
    filename = f"zone1_{country_key}_pillar{pillar_id}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_candidates, f, indent=2, ensure_ascii=False)
```

---

### 3.3 `zone1_search.py` (76 lines) — Early Firecrawl Prototype (Deprecated)

Earlier version using Firecrawl API directly. Hardcoded to search Singapore Pillar 6.1 only. Superseded by `zone1_discovery.py`.

---

### 3.4 `zone2_extraction.py` (437 lines) — Instance 2: Extraction & Mapping

**Role:** Takes Zone 1 JSON → scrapes full text via Crawl4AI → extracts operative clauses via OpenRouter LLM (DeepSeek V3) → produces RDTII-compatible CSV.

**CLI Usage:**
```
python zone2_extraction.py --country singapore --pillar 6 [--input path] [--output path] [--model deepseek/deepseek-v3.2]
```

**Key components:**

#### LLM Call (lines 65-93)
```python
def llm_call(client, model, messages, max_retries=3):
    """Generic LLM caller with retry logic and exponential backoff."""
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.1,
                max_tokens=2000,
            )
            return response.choices[0].message.content
        except Exception as e:
            if "quota" in str(e).lower() or "insufficient_quota" in str(e).lower():
                log warning and exit
            wait with exponential backoff
```

#### Pre-filter (line 103)
```python
async def prefilter_candidate(client, model, indicator_id, indicator_data, candidate):
    """Cheap LLM call to see if document is relevant before scraping."""
    prompt = PREFILTER_PROMPT.format(...)
    # Returns True/False based on LLM's {"relevant": true/false} response
```

#### Scraping (line 131)
```python
async def scrape_url(url, crawler):
    """Full-text scrape via Crawl4AI with stealth mode."""
    result = await crawler.arun(url=url, ..., bypass_cache=True)
    return result.markdown[:80000] if result.markdown else None
```

#### Re-ranking (lines 213-249)
```python
def _rank_candidates(candidates):
    """Re-rank candidates: promote legal document URLs, demote generic portals."""
    # +50 for sso.agc.gov.sg/Act/
    # +40 for legislation.gov
    # -20 for generic government portals (mom.gov.sg, sgdi.gov.sg, search.gov.sg, ...)
```

#### Indicator Processing Pipeline (lines 252-311)
```python
async def process_indicator(client, model, indicator_id, indicator_data,
                            candidates, crawler, max_candidates, rate_delay):
    ranked = _rank_candidates(candidates)
    for cand in ranked[:max_candidates]:
        # Step 1: LLM pre-filter (cheap check before scrapping)
        # Step 2: Scrape full text via Crawl4AI
        # Step 3: LLM extraction → JSON parsing
        # Step 4: Build CSV row
        # Append to rows list
    return rows
```

---

## 4. Data Files

### `zone1_singapore_pillar6.json` (3000+ lines)
Discovery output for SG Pillar 6. Contains ~30-60 candidate URLs per indicator (6.1-6.5). Notable issues:
- Many irrelevant government portal pages (gov.sg homepage, sgdi.gov.sg directory pages, mom.gov.sg guides)
- Relevance scores are mostly 0.0 for irrelevant results, with a few scoring 0.2-0.4
- Genuinely relevant documents present: `sso.agc.gov.sg/Act/PDPA2012`, `sso.agc.gov.sg/SL/PDPA2012`

### `zone1_singapore_pillar7.json` (2500+ lines)
Same pattern as Pillar 6 but for indicators 7.1-7.5.

### `zone2_singapore_pillar6.csv` (3 data rows)

| Pillar_ID | Indicator_ID | Act | Coverage | Impact | Timeframe | Reference |
|-----------|--------------|-----|----------|--------|-----------|-----------|
| 6 | 6.1 | Personal Data Protection Act 2012 | Cross-cutting | Section 26 verbatim extracted | Since 02 July 2014; Last amended 05 December 2025 | sso.agc.gov.sg/Act/PDPA2012 |
| 6 | 6.1 | Personal Data Protection Regulation 2021 | Cross-cutting | Part 3 (no specific section) | Not specified | pdpc.gov.sg/... |
| 6 | 6.5 | Personal Data Protection Act | Cross-cutting | 8. Transfer Limitation Obligation | Not specified | pdpc.gov.sg/... |

**Known quality issue:** Row 3 maps to Indicator 6.5 ("Not in binding data transfer agreement") but the content is about transfer obligations which should be 6.4 ("Conditional flow regime").

### `Singapore, Malaysia, Australia, Legal Inventory.csv` (391 rows)
Reference dataset covering 11 policy clusters across all three countries: traditional trade policies, digital governance, tariffs, public procurement, FDI, IP, competition, SOEs, environmental standards, labor standards, and other domestic policies. Provided as hackathon training/reference material.

---

## 5. Git History

```
e6289dc (Wed Jun 17) - "yep" - Initial empty files (.env, .gitignore, app.py)
79b8cd7 (Thu Jun 18) - "Stop tracking .env file" - Added .env to .gitignore, committed all source files
284dea1 (Thu Jun 18) - "first commit" - README update
242a272 (Thu Jun 18) - "first commit" - Final .gitignore (HEAD, origin/main)
```

Entire project built in one day (June 17-18, 2026) by `adriel-babalola`.

---

## 6. Pipeline Flow (as Actually Implemented vs Original Design)

### Original Design (from context.md):
```
Firecrawl Search → Gemini 2.5 Flash → Claude Sonnet → LangGraph → MongoDB → CSV
```

### Actual Implementation:
```
Crawl4AI (DuckDuckGo/Bing) → OpenRouter (DeepSeek V3) → no orchestrator → no DB → CSV
```

### Key Deviations:
| Aspect | Planned | Actual |
|--------|---------|--------|
| Discovery engine | Firecrawl (paid API) | Crawl4AI with DuckDuckGo/Bing (free) |
| Extraction LLM | Gemini 2.5 Flash | OpenRouter / DeepSeek V3 |
| Orchestration | LangGraph | Standalone CLI scripts |
| State management | MongoDB / Upstash Redis | File-based (JSON/CSV) |
| Verification | Instance 3 | Not yet implemented |
| Multi-country | Singapore, Malaysia, Australia | Only Singapore data generated |

---

## 7. Current State & Known Issues

### What's Working
- **Zone 1 Discovery:** Fully functional for all 3 countries x 2 pillars via CLI
- **Zone 2 Extraction:** End-to-end pipeline from JSON → CSV for Singapore Pillar 6
- Generated data: SG Pillar 6 & 7 candidate JSONs, SG Pillar 6 extraction CSV

### What's Missing / In Progress
- **Instance 3 (Blind Verification):** Not started at all
- **LangGraph orchestration:** Not implemented
- **Malaysia & Australia Zone 1 data:** Not generated
- **Singapore Pillar 7 extraction:** Not run
- **Full pipeline automation:** No single-command end-to-end flow
- **Error handling for empty states:** Zone 2 doesn't handle empty candidate lists
- **`.env.example` file:** Referenced in `.gitignore` but doesn't exist

### Quality Issues
1. **Noisy discovery data:** Many irrelevant government portal pages in JSON (relevance_score=0.0)
2. **Incorrect indicator mapping:** Row 3 in CSV maps a transfer obligation to 6.5 instead of 6.4
3. **Gemini API key unused:** Despite being configured, only OpenRouter/DeepSeek is used
4. **Requirements mismatch:** `firecrawl-py` installed in .venv but not in `requirements.txt`

---

## 8. Installed Python Packages (Key Ones)

| Package | Version | Purpose |
|---------|---------|---------|
| crawl4ai | 0.9.0 | Web crawling/scraping for discovery + extraction |
| firecrawl-py | 1.0.0 | Firecrawl API client (prototype only) |
| openai | ≥1.0.0 | SDK used for OpenRouter API calls |
| python-dotenv | ≥1.0.0 | Load .env files |
| google-genai | 2.8.0 | Gemini SDK (installed but unused) |
| beautifulsoup4 | - | HTML parsing (dep of crawl4ai) |
| httpx / aiohttp | - | HTTP clients (dep of crawl4ai) |

---

## 9. Quick Reference: Running the Pipeline

```bash
# Discover sources for Singapore Pillar 6
python zone1_discovery.py --country singapore --pillar 6

# Extract & map for Singapore Pillar 6
python zone2_extraction.py --country singapore --pillar 6

# Discover for all 6 combinations
python zone1_discovery.py --all
```

---

## 10. Summary

The project is in **early Alpha** — two of three pipeline instances are coded, with rough edges in data quality. The architecture has shifted from the original paid-service plan (Firecrawl + Gemini + LangGraph) to a free/open alternative (Crawl4AI + OpenRouter + file-based). The critical Instance 3 (blind verification) remains to be built, and no automated orchestration connects the stages yet.
