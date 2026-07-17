# Pillar AI — RDTII Cross-Border Data Restriction Identifier

Automated pipeline for the **UN ESCAP RDTII (Regional Digital Trade Integration Index)** hackathon. Discovers laws relevant to Pillars 6 & 7, extracts operative clauses, verifies citations, and produces final scores per the official methodology.

## Quick Start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Set up API keys
cp .env.example .env
# Edit .env with your keys (DashScope for extraction, OpenRouter/Gemini for verification)

# 3. Run end-to-end for one country-pillar
python run.py --country sg --pillar 6

# Or step by step:
python run.py --zone discovery --country sg --pillar 6
python run.py --zone extraction --country sg --pillar 6
python run.py --zone verify --country sg --pillar 6
python run.py --zone score --country sg --pillar 6

# Run everything (3 countries × 2 pillars)
python run.py --all
```

## Outputs

| Directory | Contents |
|---|---|
| `outputs/zone1/` | Raw discovered candidates per indicator (JSON) |
| `outputs/zone2/` | Extracted clauses in 16-column CSV format |
| `outputs/zone3/` | Verified citations with PASS/FAIL/LLM verdicts |
| `outputs/zone4/` | Final scores per RDTII 2.1 rubric + evidence mapping |

## Architecture

```
zone1_discovery.py   ──►  Firecrawl crawl + Wikipedia + DDG
zone2_extraction.py  ──►  pdfplumber + OCR fallback + LLM extraction
zone3_blindverifier.py ─►  Fresh fetch + regex/LLM citation check
run.py               ──►  Orchestrator (all zones in sequence)
src/
  zone1/               Discovery module
  zone2/               Extraction module + OCR
  zone3/               Verification module
  zone4/               Scoring module (RDTII 2.1 rubrics)
  prompts.py           Shared LLM prompt templates
```

## Supported Economies

- `sg` / `singapore` / `SGP`
- `my` / `malaysia` / `MYS`
- `au` / `australia` / `AUS`

## CSV Columns (Zone 2/3)

Economy, Law Name, Law Number Ref, Last Amended, Article/Section, Discovery Tag, Coverage, Indicator ID, Indicator Description, Pillar ID, Pillar Title, Location Reference, Verbatim Snippet, Mapping Rationale, Confidence, Source URL

## Scoring

Scores per RDTII 2.1 Methodology Guide (Pillar 6 & 7 weighted rubrics):

- **Pillar 6** (Cross-border Data): 6.1 (38%), 6.2 (12%), 6.3 (31%), 6.4 (12%), 6.5 (8%)
- **Pillar 7** (Privacy/Data Protection): 7.1 (31%), 7.2 (31%), 7.3 (16%), 7.4 (6%), 7.5 (16%)

Each indicator scores 0, 0.5, or 1 (some also allow 0.25). Pillar score = weighted average (0 = fully open, 1 = fully restrictive).

## Project Status

- **Zone 1**: Discovery — Complete (Firecrawl, Wikipedia, DDG)
- **Zone 2**: Extraction — Complete (pdfplumber, OCR fallback, LLM extraction)
- **Zone 3**: Verification — Complete (regex + LLM fallback, country-specific patterns)
- **Zone 4**: Scoring — Complete (RDTII 2.1 rubrics for Pillars 6 & 7)
- **Orchestrator**: `run.py` — Complete
