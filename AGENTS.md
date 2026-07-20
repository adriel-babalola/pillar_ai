# Pillar AI — RDTII Hackathon Project

## What This Is

Automated extraction + scoring pipeline for the **UN ESCAP RDTII (Regional Digital Trade Integration Index)** hackathon. Given a country (SG/MY/AU) and pillar (6 or 7), we discover relevant laws, extract operative clauses via LLM, verify citations, and produce a weighted score per the official RDTII 2.1 methodology.

**Supported:** Singapore, Malaysia, Australia  
**Pillars:** 6 (Cross-border data restrictions), 7 (Data protection & privacy)  
**Final scores achieved:** MY P6=0.3069, MY P7=0.5300, AU P6=0.3069

---

## Architecture (4-Zone Pipeline)

```
zone1_discovery.py          Discovery — find candidate laws
    ↓
zone2_extraction.py         Extraction — LLM reads docs, extracts operative clauses
    ↓
zone3_blindverifier.py      Verification — independently re-fetches & checks citations
    ↓
src/zone4/scoring.py        Scoring — RDTII 2.1 weighted rubric → final score
```

Orchestrator: `run.py` — runs any/all zones for one or all combos.

### Data Flow Details

```
zone1_discovery.py
  │  Sources: seed inventory CSVs + Wikipedia API + DuckDuckGo HTTP search
  │  Output: outputs/zone1/zone1_{country}_pillar{pillar}.json
  │  Format: dict of indicator_id → list of candidate dicts
  ▼
zone2_extraction.py
  │  For each candidate: prefilter → hybrid_scrape → LLM extraction → build CSV row
  │  Output: outputs/zone2/zone2_{country}_pillar{pillar}.csv (16 columns)
  │  Important: ~$0.017 per extraction uses Alibaba Qwen 3.7 Plus
  ▼
zone3_blindverifier.py
  │  Re-fetches each document independently, locates cited section via regex + fuzzy + LLM
  │  Output: outputs/zone3/zone2_{country}_pillar{pillar}_verified.csv
  │  Verdicts: PASS / FAIL / NEEDS_REVIEW / URL_BROKEN
  ▼
src/zone4/scoring.py
  │  Applies rubric → weighted average → score report
  │  Output: outputs/zone4/zone4_{country}_pillar{pillar}_score.txt + .csv
  │  Score range: 0 (fully open) to 1 (fully restrictive)
```

---

## File Map

### Root

| File | Purpose |
|------|---------|
| `run.py` | Orchestrator — runs any combination of zones/countries/pillars |
| `zone1_discovery.py` | CLI entry: law discovery via Wikipedia + DuckDuckGo |
| `zone2_extraction.py` | CLI entry: clause extraction via LLM (prefilter → scrape → extract → CSV) |
| `zone3_blindverifier.py` | CLI entry: citation verification (re-fetch → regex → fuzzy → LLM fallback) |
| `generate_hackathon_output.py` | Builds formatted XLSX for hackathon submission from all Zone 2 CSVs |
| `check_env.py` | Stub that delegates to `scripts/check_env.py` |
| `requirements.txt` | Python dependencies (crawl4ai, openai, pdfplumber, playwright, etc.) |
| `.env` | API keys: DASHSCOPE, OPENROUTER, GEMINI, OLLAMA |
| `Singapore, Malaysia, Australia, Legal Inventory.csv` | 391-row seed dataset of trade policies |

### `src/prompts.py` — LLM Prompt Templates

- `PILLAR_6_INDICATORS` / `PILLAR_7_INDICATORS`: Dicts with `name`, `question`, `keywords`, `extraction_instructions`, optional `auto_skip`
- `PREFILTER_PROMPT`: Asks LLM "is this doc relevant?" → JSON `{"relevant": bool}`
- `EXTRACTION_PROMPT_TEMPLATE`: Full extraction prompt with `{indicator_id}`, `{indicator_question}`, `{extraction_instructions}`, `{country_display}`, `{scraped_text}`
- **CRITICAL**: Extraction prompt instructs LLM to return ONLY valid JSON with keys: `operative_clause`, `section_reference`, `act_title`, `law_number_ref`, `coverage`, `timeframe`, `last_amended`, `location_reference`, `interpretation`

### `src/zone1/` — Discovery

| File | Purpose |
|------|---------|
| `config.py` | Country configs (display name, domain patterns, site filter), alias resolution |
| `indicators.py` | Pillar 6 & 7 indicator definitions with `query_themes` (used for search query generation) |
| `seeds.py` | `SEED_URLS` — curated URLs per country×pillar×indicator (these always get `relevance_score=1.0` and skip pre-filter) |
| `inventory.py` | Filters 391-row CSV to Pillars 6/7 relevant rows (~30 per country), maps to indicators |
| `discovery.py` | `process_country_pillar()` — main orchestration: seeds → inventory → Wikipedia → DuckDuckGo |
| `discovery_wikipedia.py` | Wikipedia API discovery — curated page titles + text search → extract external links to gov URLs |
| `discovery_searchengine.py` | DuckDuckGo search via direct HTTP to `html.duckduckgo.com/html/` with custom HTML parser |
| `utils.py` | `is_official_url()`, `relevance_score()`, `generate_queries()` |

**Discovery Strategy per indicator:**
1. **Seed URLs** from `seeds.py` — manually curated, relevance=1.0, skip pre-filter
2. **Inventory** from CSV — filtered rows mapped to indicators, relevance=1.0
3. **Wikipedia** — curated page titles (guaranteed relevant) + text search (filtered by `relevance_score > 0.5`), extract external links → filter to official gov URLs
4. **DuckDuckGo** — direct HTTP search with site filter, parse results → filter to official gov URLs
5. Duplicate prevention: global `seen_urls` across all indicators, dedup per seed+inventory+wiki+ddg

### `src/zone2/` — Extraction

| File | Purpose |
|------|---------|
| `config.py` | API keys, model config, CSV field names, cache dir, country aliases |
| `client.py` | `llm_call()` — unified entry with comma-separated fallback chain: alibaba → gemini → openrouter → ollama |
| `extraction.py` | `process_indicator()` — prefilter → scrape → extract → build_row |
| `scraper.py` | `hybrid_scrape()` — 3-tier fetcher with cache, SSO PDF maps, Playwright, OCR fallback |

**LLM Backend Priority (set in `src/zone2/config.py` `DEFAULT_MODEL`):**
- `alibaba:qwen3.7-plus` → Alibaba DashScope (workspace endpoint, ~$0.017/extraction)
- `gemini` → Google Gemini 2.5 Flash
- `ollama:gemma4` → Ollama Cloud
- OpenRouter (any model string not starting with `alibaba:`/`gemini`/`ollama:`)
- Fallback chain: comma-separated in model string, tried in order

**Scraper Strategy (`hybrid_scrape` in `scraper.py`):**
- PDFs → `curl_cffi` (TLS impersonation) → `pdfplumber` → OCR (Tesseract) fallback
- HTML → `Crawl4AI` (renders JS) → Playwright fallback (with stealth + `_expand_content()`) → `curl_cffi`+BS4 fallback
- Cache at `.scrape_cache/` (MD5 keyed by URL)
- `_normalize_ssourl()` — adds `?ProvIds=WholeDoc&ViewType=Adv` to SSO URLs, `&lang=EN` to LOM Malaysia URLs
- `_SSO_PDF_MAP` — known PDF URLs for SG acts (`PDPA2012`)
- `_MY_PDF_MAP` — known PDF URLs for MY acts (Computer Misuse Act, SOSMA, PDPA 2010)
- `_has_js_garbage()` — detects navigation chrome (LOM Malaysia portal) vs real content

### `src/zone3/verifier.py` — Blind Citation Verification

- `verify_csv()` — reads Zone 2 CSV, verifies each row
- `_extract_section_ref()` — regex search for Article/Section/Part/APP/Clause/Seksyen/Perkara in CSV columns
- `_generate_section_patterns()` — creates multiple regex patterns for flexible matching (including Gazette format `26.  (1)`)
- `_locate_section_deterministic()` — regex search for section reference in document text
- `_llm_locate_section()` — fallback: ask LLM to find the section
- `_get_claim_text()` — strips section prefix from claim text before comparison
- Comparison: exact → fuzzy (>0.85) → substring → FAIL

### `src/zone4/scoring.py` — RDTII 2.1 Scoring

**Pillar 6 Weights:** 6.1=38%, 6.2=12%, 6.3=31%, 6.4=12%, 6.5=8%  
**Pillar 7 Weights:** 7.1=31%, 7.2=31%, 7.3=16%, 7.4=6%, 7.5=16%

**Scoring Logic Highlights:**
- `score_6_1()`: Checks for conditional language (`except`, `unless`, `subject to`) BEFORE horizontal ban check — avoids false positives on conditional regimes
- `score_6_2()`: Detects local storage, data localization, data residency keywords
- `score_6_3()`: Detects data centre, server, infrastructure requirements
- `score_6_4()`: Conditional flow regimes — consent, adequacy, safeguards, BCRs
- `score_6_5()`: Binding agreements — checks CPTPP, RCEP, DEPA membership. Non-regulatory indicator (auto-skipped in extraction, scored via external DBs)
- `score_7_1()`: Country-specific overrides — MY PDPA=0.5 (sectoral, commercial only), SG PDPA=0.0 (comprehensive but known limitations noted). Detects "commercial transaction" for MY
- `score_7_2()`: Computer misuse laws score 0.5 (not dedicated cybersecurity framework). Only dedicated cybersecurity act = 0.0
- `score_7_3()`: Minimum retention period vs "as long as necessary"
- `score_7_4()`: DPO + horizontal = 1.0, DPO sectoral = 0.5, DPIA only = 0.25
- `score_7_5()`: Government access with/without judicial authorization

---

## CSV Output Format (16 columns)

| Column | Source | Description |
|--------|--------|-------------|
| `Economy` | build_row param | Country name |
| `Pillar_ID` | Derived from indicator_id | 6 or 7 |
| `Indicator_ID` | From indicator config | e.g. 6.1, 7.3 |
| `Act_and_or_practice` | LLM extraction or candidate title | Full official law name |
| `Law_Number_Ref` | LLM extraction | Official act number (e.g. "Act 709") |
| `Last_Amended` | LLM extraction | Year of latest amendment |
| `Coverage` | LLM extraction | Cross-cutting or Sectoral |
| `Article_Section` | LLM extraction | Specific section/article number |
| `Discovery_Tag` | Candidate metadata | KNOWN (seed/inventory) or NEW (discovered) |
| `Location_Reference` | LLM extraction | PDF page or HTML anchor |
| `Verbatim_Snippet` | LLM extraction | Exact operative clause text |
| `Mapping_Rationale` | LLM extraction | Legal interpretation |
| `Impact_or_comments` | Combined field | `Section X: Verbatim\nInterpretation: ...` |
| `Timeframe` | LLM extraction | "Since Month Year; Last amended Month Year" |
| `References` | Candidate URL | Source URL |
| `Confidence` | LLM extraction | high, medium, or low |

---

## Key Design Decisions & Gotchas

### LLM-Related
- **Alibaba workspace endpoint is primary** — verified working, 1M context window, ~$0.017/extraction. Endpoint: `https://ws-qi5wh5fl237ivx9r.ap-northeast-1.maas.aliyuncs.com/compatible-mode/v1`
- **Model string format:** `alibaba:qwen3.7-plus`, `gemini`, `ollama:gemma4`, or any OpenRouter model ID. Comma-separated = fallback chain.
- **Prompt engineering:** `extraction_instructions` in each indicator config tells LLM what to look for. System prompt warns not to paraphrase and to return ONLY valid JSON.
- **Pre-filtering:** Seed URLs skip pre-filter (known-good). Discovery URLs get LLM pre-filter (`PREFILTER_PROMPT`) asking if the doc is relevant.
- **JSON parsing:** `parse_json_response()` strips markdown fences (` ```json `) before parsing. Retries on empty/invalid response.

### Scraper-Related
- **SSO (sso.agc.gov.sg) returns 403** — SG acts rely on the `_SSO_PDF_MAP` for PDPA2012 PDF. Other SSO URLs get `ViewType=Adv` param. If 403 persists, secondary articles are used.
- **BNM RMiT PDF (bnm.gov.my) returns 403** — MY 6.3 stays 0.0 with limitation note.
- **LOM Malaysia (lom.agc.gov.my)** — requires `&lang=EN` param, HTML pages are JS-heavy navigation chrome detected by `_has_js_garbage()`.
- **austlii.edu.au** added to AU domain patterns (federated legislation database).
- **OCR fallback:** Tesseract + pdf2image for scanned PDFs. Requires Tesseract installed on system.
- **Cache:** `.scrape_cache/` directory stores scraped text as JSON keyed by URL MD5. Cache hit returns immediately.

### Discovery-Related
- **DuckDuckGo library (`duckduckgo-search` v7/8) is broken** — hangs due to DNS-blocked fallback engines (Yahoo, Yandex, Google). Replaced with direct HTTP to `html.duckduckgo.com/html/` + custom `_DDGResultParser` HTML parser. Returns 0 results quietly if blocked.
- **Wikipedia rate limits** — curated titles are primary path. Text search falls back with 0.3s and 0.5s delays between queries.
- **My results are limited** — Wikipedia typically returns ~10-50 candidates per indicator. DDG typically returns 0 (network restrictions).
- **Inventory CSV filtering** (`inventory.py`): Only rows with cluster="Digital governance policies" AND relevant name ("Cross-border data policies", "Domestic data protection & privacy") AND keyword match. Act title must also match data/cyber keywords to avoid irrelevant acts.

### Section Pattern Matching (Zone 3)
- **Singapore style:** `Section 26(1)`, `s. 26`, `S. 26`, `Part IV`, `Division 2`
- **Australia style:** `APP 8`, `Clause 1.4`, `Schedule 1`, `s 8`, `Part III`
- **Malaysia style:** `Seksyen 129`, `Perkara 5`, `Bahagian IV`, `Perenggan`
- **Gazette format:** `26.  (1)` with flexible whitespace and possible non-breaking spaces (`\uFFFD`)

### Candidate Ranking (Zone 2 extraction.py `_rank_candidates()`)
- Seeds get +999 score bump
- SSO/legislation.gov URLs get +25–50
- Official domains (pdpc, oaic, csa, etc.) get +20
- Act/regulation in title gets +15
- Penalised domains (mom, go.gov.sg/explainers, etc.) get -20
- Short titles (<20 chars) get -5

---

## Known Issues & Limitations

| Issue | Impact | Workaround |
|-------|--------|------------|
| SSO 403 | SG sources rely on secondary articles + PDF map | `_SSO_PDF_MAP` covers PDPA2012 |
| BNM RMiT PDF 403 | MY 6.3 stays 0.0 | Accept limitation, score with note |
| DDG blocked on some networks | Only Wikipedia discovery works | DDG returns 0 results, pipeline continues |
| Wikipedia rate limits | Malaysia takes longer (fewer curated titles) | Nothing. Add more curated titles to `CURATED_TITLES` in `discovery_wikipedia.py` |
| Large PDFs >500 pages | Zone 3 verification may time out | Increase timeout or skip large docs |
| Tesseract OCR not installed | Scanned PDFs return nothing | Install Tesseract from UB-Mannheim release, add to PATH |
| Playwright browsers not installed | Crawl4AI/Playwright fallback fails | Run `playwright install chromium` |
| Unicode in console | Rendering issues on cmd.exe | Use Windows Terminal |
| Zone 2 CSV must exist for Zone 3 | Zone 3 hardcodes `outputs/zone2/` path | Run extraction first |

---

## Current Scores (from most recent full pipeline run)

**Do not take these as authoritative or as a benchmark.** These are pipeline-derived estimates from LLM-extracted clauses, not legal determinations. Source URLs + section refs + verbatim snippets + verification status are available in the CSVs for scrutiny.

| Country | Pillar | Score |
|---------|--------|-------|
| Singapore | 6 | 0.3069 |
| Singapore | 7 | 0.3800 |
| Malaysia | 6 | 0.7327 |
| Malaysia | 7 | 0.6900 |
| Australia | 6 | 0.4257 |
| Australia | 7 | 0.2200 |

---

## Key Commands

```bash
# Validate environment (all dependencies, API keys, network)
python check_env.py

# Single country, both pillars, all zones
python run.py --country sg
python run.py --country my
python run.py --country au

# Specific zone only
python run.py --zone discovery --country sg
python run.py --zone extraction --country sg --pillar 6
python run.py --zone verify --country sg --pillar 6
python run.py --zone score --country sg --pillar 6

# Every combo (3 countries × 2 pillars)
python run.py --all

# Single script execution (when you need more control)
python zone1_discovery.py --country singapore --pillar 6
python zone2_extraction.py --country singapore --pillar 6 --model alibaba:qwen3.7-plus --max-candidates 5 --rate-delay 3.0
python zone3_blindverifier.py --input outputs/zone2/zone2_singapore_pillar6.csv

# Full sweep (recommended order — sequential, each takes minutes)
# Zone 1: ~2-5 min per combo
python zone1_discovery.py --country singapore --pillar 6
python zone1_discovery.py --country singapore --pillar 7
python zone1_discovery.py --country malaysia --pillar 6
python zone1_discovery.py --country malaysia --pillar 7
python zone1_discovery.py --country australia --pillar 6
python zone1_discovery.py --country australia --pillar 7

# Zone 2: ~10-15 min per combo (LLM calls at 3s rate delay)
python zone2_extraction.py --country singapore --pillar 6
python zone2_extraction.py --country singapore --pillar 7
python zone2_extraction.py --country malaysia --pillar 6
python zone2_extraction.py --country malaysia --pillar 7
python zone2_extraction.py --country australia --pillar 6
python zone2_extraction.py --country australia --pillar 7

# Zone 3: ~1 min per file
python zone3_blindverifier.py --input outputs/zone2/zone2_singapore_pillar6.csv
python zone3_blindverifier.py --input outputs/zone2/zone2_singapore_pillar7.csv
# ... etc for all 6 verified CSVs
```

---

## Development Conventions

- **NO comments in code** — the codebase has zero comments in production files. Don't add any.
- **NO emojis** — this is a console-based CLI tool, no emojis anywhere.
- **Minimal output** — answer questions directly, no preamble or explanations unless asked.
- **Error handling** — Python `Exception` catches are non-specific. Retries use exponential backoff (2^attempt * 3s).
- **Logging** — `logging.getLogger(__name__)` format: `%(asctime)s [%(levelname)s] %(message)s` with `%H:%M:%S` time.
- **Async** — Zone 1 uses `asyncio`, scraper `hybrid_scrape` is async, Playwright is sync in thread pool (`_run_in_thread`).
- **File encoding** — CSV files use `utf-8-sig` (BOM), JSON uses `utf-8`, output uses `utf-8`.
- **Persistence** — Outputs are always saved (not printed-only). Discovery saves JSON, extraction saves CSV, verifier adds columns to CSV, scoring saves TXT+CSV.
