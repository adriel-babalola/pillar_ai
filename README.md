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

## Architecture Overview

```
Economy + Pillar
       |
       v
+---------------------------+
| ZONE 1: Discovery          |
|  - Seed inventory (curated)|
|  - Wikipedia proxy         |
|  - DuckDuckGo HTML search  |
|  Output: candidates JSON   |
+---------------------------+
       |
       v
+---------------------------+
| ZONE 2: Extraction         |
|  - Prefilter (embedding)   |
|  - Hybrid scrape (3-tier)  |
|  - LLM clause extraction   |
|  Output: 16-column CSV     |
+---------------------------+
       |
       v
+---------------------------+
| ZONE 3: Verification       |
|  - Re-fetch document       |
|  - Regex + fuzzy matching  |
|  - LLM fallback comparison |
|  Output: verified CSV      |
+---------------------------+
       |
       v
+---------------------------+
| ZONE 4: Scoring            |
|  - RDTII 2.1 rubric per    |
|    indicator               |
|  - Weighted average        |
|  Output: score report      |
+---------------------------+
```

### Project Structure

```
pillar_ai/
  run.py                            # Orchestrator
  check_env.py                      # Env validator stub -> scripts/check_env.py
  zone1_discovery.py                # Zone 1 CLI
  zone2_extraction.py               # Zone 2 CLI
  zone3_blindverifier.py            # Zone 3 CLI
  generate_hackathon_output.py      # Submission XLSX builder
  scripts/
    check_env.py                    # Environment validator
  src/
    prompts.py                      # Indicator defs + extraction prompts
    zone1/ (discovery logic)
    zone2/ (extraction, scraping, LLM routing)
    zone3/ (verification)
    zone4/ (scoring)
  outputs/
    zone1/ (candidate JSON)
    zone2/ (extraction CSV)
    zone3/ (verified CSV)
    zone4/ (score reports)
```

### Key Modules

| Module | File | Description |
| :----- | :--- | :---------- |
| Discovery | `src/zone1/discovery.py` | Orchestrates seed + Wikipedia + DuckDuckGo discovery |
| Wikipedia Proxy | `src/zone1/discovery_wikipedia.py` | Curated Wikipedia pages -> external links to gov URLs |
| Search Engine | `src/zone1/discovery_searchengine.py` | Direct DuckDuckGo HTML search with site filter |
| Hybrid Scraper | `src/zone2/scraper.py` | 3-tier fetcher (Crawl4AI, Playwright, curl_cffi, OCR) |
| LLM Client | `src/zone2/client.py` | Comma-separated fallback chain (Alibaba -> Gemini -> Ollama -> OpenRouter) |
| Embedding Prefilter | `src/zone2/embedding.py` | TF-IDF/fastembed similarity scoring for candidate ranking |
| Extraction | `src/zone2/extraction.py` | Prefilter -> scrape -> LLM extract -> CSV row |
| Verifier | `src/zone3/verifier.py` | Deterministic + fuzzy + LLM citation verification |
| Scoring | `src/zone4/scoring.py` | RDTII 2.1 weighted rubrics for 10 indicators |

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
