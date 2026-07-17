# Pillar AI — RDTII Cross-Border Data Restriction Identifier

Automated pipeline for the **UN ESCAP RDTII (Regional Digital Trade Integration Index)** hackathon.

Given a country and pillar, it:
1. **Discovers** relevant laws (Firecrawl + Wikipedia + DuckDuckGo)
2. **Extracts** operative clauses (PDF/text scraping + LLM)
3. **Verifies** citations (fresh fetch + regex + LLM fallback)
4. **Scores** per the official RDTII 2.1 methodology

Outputs a ready-to-submit CSV with 16 columns.

---

## Requirements

- **Python 3.11+**
- **Tesseract OCR** — for scanned PDF fallback
  - Download from https://github.com/UB-Mannheim/tesseract/wiki
  - Add to your PATH (default: `C:\Program Files\Tesseract-OCR\`)
- **Playwright browsers** — for crawling
  - Run: `playwright install chromium`
- **~5 GB free disk** for PDF downloads and cache

---

## Setup

```bash
# 1. Clone and enter the project
cd pillar_ai

# 2. Create virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate    # Windows
source .venv/bin/activate  # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Playwright browser engine
playwright install chromium

# 5. Set up API keys
cp .env.example .env
```

**Edit `.env`** with your keys. At minimum you need one LLM backend:

| Key | Where to get it | Used for |
|---|---|---|
| `DASHSCOPE_API_KEY` | aliyun.com (Alibaba Cloud) | Primary LLM (Qwen 3.7 Plus) |
| `OPENROUTER_API_KEY` | openrouter.ai/keys | Fallback LLM |
| `GEMINI_API_KEY` | aistudio.google.com | Fallback LLM (Gemini 2.5 Flash) |
| `OLLAMA_API_KEY` | cloud.ollama.com | Local/open-source fallback |

The pipeline tries backends in order: DashScope → OpenRouter → Gemini → Ollama. Only one needs to work.

**Verify setup:**
```bash
python -c "from src.zone4.scoring import score_indicator; print('OK:', score_indicator('6.1', 'Cross-cutting', 'Ban on transfers', 'Total ban')['score'])"
```

---

## Usage

### Quick run (recommended)

Run **both** Pillars 6 and 7 for a country in one go:

```bash
python run.py --country sg    # Singapore, Pillars 6 + 7
python run.py --country my    # Malaysia,  Pillars 6 + 7
python run.py --country au    # Australia, Pillars 6 + 7
```

That runs all four zones (discovery → extraction → verification → scoring) for both pillars, with clear banner headers showing what's running.

### Single pillar

Run only Pillar 6 or 7 for a country:

```bash
python run.py --country sg --pillar 6
python run.py --country sg --pillar 7
```

### Single zone

Run only one stage at a time:

```bash
# Discovery only (both pillars)
python run.py --zone discovery --country sg

# Extraction only (single pillar)
python run.py --zone extraction --country sg --pillar 6

# Verify only
python run.py --zone verify --country sg --pillar 6

# Score only
python run.py --zone score --country sg --pillar 6
```

Note: `--zone` without `--pillar` runs the zone for **both** pillars.

### All 6 combinations at once

```bash
python run.py --all
```

This runs Singapore Pillar 6, Singapore Pillar 7, Malaysia Pillar 6, Malaysia Pillar 7, Australia Pillar 6, Australia Pillar 7 in sequence, with a summary at the end showing all output files.

### run.py flags

```
--country      Country: sg/singapore, my/malaysia, au/australia (required unless --all)
--pillar       Pillar: 6 or 7 (optional — defaults to both)
--zone         Stage: discovery, extraction, verify, score, or all (default: all)
--all          Process all 3 countries x 2 pillars
--model        LLM model override (e.g. "google/gemini-2.5-flash")
--limit        Max candidates per indicator (Zone 1) or max to process (Zone 2)
--rate-delay   Seconds between LLM calls (default: 3.0, increase to avoid rate limits)
--help         Show full help
```

### Country aliases

All these work interchangeably:
- Singapore: `sg`, `singapore`, `SGP`
- Malaysia: `my`, `malaysia`, `MYS`
- Australia: `au`, `australia`, `AUS`

---

## Per-file commands

### Zone 1 — Discovery: `zone1_discovery.py`

```bash
# Single country + pillar
python zone1_discovery.py --country singapore --pillar 6

# All countries (both pillars) — no args
python zone1_discovery.py

# Limit results per query (default 10)
python zone1_discovery.py --country sg --pillar 7 --limit 5
```

Flags: `--country`, `--pillar`, `--limit`

Output: `outputs/zone1/zone1_{country}_pillar{pillar}.json`
Structure: each indicator has a list of candidate documents with title, URL, snippet, relevance score.

### Zone 2 — Extraction: `zone2_extraction.py`

```bash
# Basic
python zone2_extraction.py --country sg --pillar 6

# Custom model + rate limiting
python zone2_extraction.py --country sg --pillar 6 --model "google/gemini-2.5-flash" --rate-delay 5.0

# Limit candidates processed per indicator
python zone2_extraction.py --country sg --pillar 6 --max-candidates 3
```

Flags: `--country`, `--pillar` (required), `--model`, `--max-candidates` (default 5), `--rate-delay` (default 3.0), `--input` (custom Zone 1 JSON), `--output` (custom CSV path)

Output: `outputs/zone2/zone2_{country}_pillar{pillar}.csv` — 16-column CSV ready for submission.

### Zone 3 — Verification: `zone3_blindverifier.py`

```bash
# Auto-resolve CSV from country/pillar
python zone3_blindverifier.py --country sg --pillar 6

# Explicit input path
python zone3_blindverifier.py --input outputs/zone2/zone2_singapore_pillar6.csv

# Custom model + retries
python zone3_blindverifier.py --country my --pillar 7 --model "alibaba:qwen3.7-plus" --retries 5
```

Flags: `--input`, `--country`/`--pillar` (alternative to --input), `--output`, `--model` (default: alibaba:qwen3.7-plus), `--retries` (default 3)

What it does: re-fetches each URL, finds the cited section via regex patterns, compares the actual text to the claimed snippet (fuzzy match). If regex fails, falls back to LLM. Outputs PASS/FAIL/LLM_VERIFIED per row.

Output: `outputs/zone3/zone2_{country}_pillar{pillar}_verified.csv`

### Zone 4 — Scoring: `src/zone4/scoring.py` (via `run.py --zone score`)

```bash
# Score both pillars (runs from verified CSV, falls back to raw Zone 2 CSV)
python run.py --zone score --country sg

# Score single pillar
python run.py --zone score --country sg --pillar 6
```

Outputs:
- `outputs/zone4/zone4_{country}_pillar{pillar}_score.txt` — human-readable report
- `outputs/zone4/zone4_{country}_pillar{pillar}_score.csv` — machine-readable scores

---

## Output CSV columns (Zone 2/3)

| # | Column | Description |
|---|---|---|
| 1 | `Economy` | Country name (Singapore, Malaysia, Australia) |
| 2 | `Pillar_ID` | 6 or 7 |
| 3 | `Indicator_ID` | e.g. 6.1, 7.3 |
| 4 | `Act_and_or_practice` | Full official law name (e.g. "Personal Data Protection Act 2012") |
| 5 | `Law_Number_Ref` | Official act number (e.g. "Act 26 of 2012", "Act 709") |
| 6 | `Last_Amended` | Year of latest amendment |
| 7 | `Coverage` | "Cross-cutting" (all sectors) or "Sectoral: Banking" etc. |
| 8 | `Article_Section` | Specific section/article number (e.g. "Section 26(1)") |
| 9 | `Discovery_Tag` | "KNOWN" (from seed inventory) or "NEW" (from Wikipedia/DDG) |
| 10 | `Location_Reference` | PDF page number or HTML anchor |
| 11 | `Verbatim_Snippet` | Exact operative clause text |
| 12 | `Mapping_Rationale` | Legal interpretation (2-3 sentences) |
| 13 | `Impact_or_comments` | Combined field (section + clause + interpretation) |
| 14 | `Timeframe` | "Since Month Year; Last amended Month Year" |
| 15 | `References` | Source URL of the law |
| 16 | `Confidence` | "high", "medium", or "low" |

---

## Verification details

Zone 3 independently re-fetches the source document for each row and checks:

1. **Regex matching** — searches for the Article/Section number in the downloaded text
2. **Fuzzy comparison** — compares the Verbatim Snippet against surrounding text (70% similarity threshold)
3. **LLM fallback** — if regex fails, asks the LLM to locate the section in the full text

Per-row verdict: `PASS` (verified), `FAIL` (contradicted), or `LLM_VERIFIED` (LLM confirmed but regex didn't match).

Country-specific section patterns supported:
- **Singapore**: `Section 26(1)`, `s. 26`, `Part IV`, `Regulation 3`
- **Australia**: `APP 8`, `clause 1.4`, `Division 2`, `Schedule 1`, `s 8`
- **Malaysia**: `Seksyen 129`, `Perkara 5`, `Bahagian IV`

---

## Scoring (RDTII 2.1 Methodology)

Each indicator scores 0, 0.5, or 1 (some allow 0.25). The pillar score is a weighted average where 0 = fully open and 1 = fully restrictive.

**Pillar 6 — Cross-border data restrictions** (total weight = 1.0):

| Indicator | Weight | What it measures |
|---|---|---|
| 6.1 Ban & local processing | 38% | Restrictions on transferring data abroad |
| 6.2 Local storage | 12% | Requirements to store data locally |
| 6.3 Infrastructure | 31% | Requirements for local servers/data centres |
| 6.4 Conditional flow | 12% | Conditions on cross-border transfers |
| 6.5 Binding agreements | 8% | Whether economy is party to data flow agreements |

**Pillar 7 — Data protection & privacy** (total weight = 1.0):

| Indicator | Weight | What it measures |
|---|---|---|
| 7.1 Data protection framework | 31% | Existence of comprehensive privacy law |
| 7.2 Cybersecurity framework | 31% | Existence of dedicated cybersecurity law |
| 7.3 Data retention | 16% | Minimum data retention periods |
| 7.4 DPO/DPIA | 6% | Data Protection Officer & impact assessment requirements |
| 7.5 Gov access | 16% | Government access to personal data |

---

## Architecture

```
pillar_ai/
│
├── run.py                     # Orchestrator — runs any/all zones
├── zone1_discovery.py         # CLI: law discovery via web crawl
├── zone2_extraction.py        # CLI: clause extraction via LLM
├── zone3_blindverifier.py     # CLI: citation verification
│
├── src/
│   ├── zone1/
│   │   ├── config.py          # Country configs, seed URLs, search queries
│   │   ├── discovery.py       # Orchestrates per-indicator crawl
│   │   ├── discovery_searchengine.py  # DuckDuckGo search integration
│   │   └── discovery_wikipedia.py     # Wikipedia lookups
│   │
│   ├── zone2/
│   │   ├── config.py          # API keys, CSV fields, country aliases
│   │   ├── extraction.py      # LLM prompt + parsing for clause extraction
│   │   └── scraper.py         # PDF/text scraping with OCR fallback
│   │
│   ├── zone3/
│   │   └── verifier.py        # Blind citation verification logic
│   │
│   ├── zone4/
│   │   └── scoring.py         # RDTII 2.1 scoring rubrics + reports
│   │
│   └── prompts.py             # LLM prompt templates + indicator definitions
│
├── outputs/
│   ├── zone1/                 # Discovery JSON files
│   ├── zone2/                 # Extraction CSV files
│   ├── zone3/                 # Verified CSV files
│   └── zone4/                 # Score reports
│
├── .env.example               # API key template
├── requirements.txt           # Pinned Python dependencies
└── README.md                  # This file
```

### Data flow

```
zone1_discovery.py
  │  Searches gov portals, Wikipedia, DuckDuckGo
  │  Output: zone1_{country}_pillar{pillar}.json
  ▼
zone2_extraction.py
  │  Downloads PDFs/text, runs LLM to extract operative clauses
  │  Output: zone2_{country}_pillar{pillar}.csv (16 columns)
  ▼
zone3_blindverifier.py
  │  Re-fetches each document, verifies citations independently
  │  Output: zone2_{country}_pillar{pillar}_verified.csv
  ▼
zone4/scoring.py
  │  Applies RDTII 2.1 rubric, computes weighted scores
  │  Output: score report (txt + CSV)
```

---

## Example workflow

```bash
# 1. Full pipeline: Singapore (both pillars)
python run.py --country sg

# 2. Full pipeline: Malaysia Pillar 6 only
python run.py --country my --pillar 6

# 3. Check results
Get-ChildItem outputs/ -Recurse

# 4. View score
Get-Content outputs/zone4/zone4_singapore_pillar6_score.txt

# 5. Submit CSV — outputs/zone2/zone2_singapore_pillar6.csv
# (or the verified version if you ran verification)
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `OPENROUTER_API_KEY not set` | Edit `.env` and add your key |
| `playwright not found` | Run `playwright install chromium` |
| `TesseractNotFoundError` | Install Tesseract OCR and add to PATH |
| `Rate limit errors` | Increase `--rate-delay` (e.g. `--rate-delay 5.0`) |
| `No candidates found` | Check Firecrawl API key or try different queries |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| Unicode errors in console | Use Windows Terminal, not cmd.exe |
