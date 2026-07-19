# Pillar AI - RDTII Cross-Border Data Restriction Identifier

Pillar AI is an end-to-end legal research pipeline for the UN ESCAP RDTII (Regional Digital Trade Integration Index) hackathon. It discovers relevant laws, extracts operative clauses, verifies citations, and computes RDTII 2.1 scores for Pillars 6 and 7.

The current workspace focuses on Singapore, Malaysia, and Australia.

## Setup First

### Requirements

- Python 3.11+
- Tesseract OCR for scanned PDF fallback
- Playwright Chromium for browser-based scraping
- Enough disk space for downloaded documents and cache

### Install

1. Clone the repository and open the project folder.
2. Create and activate a virtual environment.
3. Install Python dependencies.
4. Install the Playwright browser.
5. Copy `.env.example` to `.env` and add at least one LLM key.

```bash
cd pillar_ai
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
copy .env.example .env
```

If you are on macOS or Linux, use `source .venv/bin/activate` instead of the Windows activation command and use your shell's equivalent of `copy`.

### Environment variables

The pipeline can use multiple model backends. Configure at least one of these in `.env`:

- `DASHSCOPE_API_KEY` for Alibaba DashScope
- `OPENROUTER_API_KEY` for OpenRouter
- `GEMINI_API_KEY` for Google Gemini
- `OLLAMA_API_KEY` for Ollama Cloud

`PROXY_URL` is optional and only needed if your network requires a proxy for document retrieval.

## What This Project Does

Pillar AI is built to support legal research on cross-border data restriction and privacy rules. It uses a four-stage workflow:

1. Discovery finds candidate laws and public sources for each indicator.
2. Extraction downloads documents and uses an LLM to pull out the operative clause and legal rationale.
3. Verification re-fetches the source and checks the extracted text against the cited section.
4. Scoring turns verified evidence into a pillar-level score report.

The goal is to create a repeatable research pipeline that can be rerun as laws, sources, or model quality change.

## Usage

### Full Pipeline

Run both pillars for one country:

```bash
python run.py --country sg
python run.py --country my
python run.py --country au
```

Run a single pillar:

```bash
python run.py --country sg --pillar 6
python run.py --country au --pillar 7
```

### One Zone At A Time

```bash
python run.py --zone discovery --country sg
python run.py --zone extraction --country sg --pillar 6
python run.py --zone verify --country sg --pillar 6
python run.py --zone score --country sg --pillar 6
```

### Batch Run

```bash
python run.py --all
```

This runs all three countries across both pillars and prints a summary when the pipeline completes.

### CLI Flags

| Flag | Meaning |
|------|---------|
| `--country` | Country alias: `sg`/`singapore`, `my`/`malaysia`, `au`/`australia`. Required unless you use `--all`. |
| `--pillar` | Pillar `6` or `7`. If omitted, both pillars run. |
| `--zone` | `discovery`, `extraction`, `verify`, `score`, or `all`. |
| `--all` | Process all supported country and pillar combinations. |
| `--model` | Override the default LLM routing string. |
| `--limit` | Limits candidates in discovery or extracted rows in extraction. |
| `--rate-delay` | Delay between LLM calls to reduce rate-limit pressure. |

## Project Structure

```text
pillar_ai/
├── run.py
├── zone1_discovery.py
├── zone2_extraction.py
├── zone3_blindverifier.py
├── src/
│   ├── zone1/
│   ├── zone2/
│   ├── zone3/
│   └── zone4/
├── outputs/
├── Singapore, Malaysia, Australia, Legal Inventory.csv
├── .env.example
├── requirements.txt
└── README.md
```

The entry scripts are thin CLIs that call the implementation in `src/`.

## How The Pipeline Works

### Zone 1 - Discovery

Discovery searches three source types for each indicator:

- curated seed inventory data
- Wikipedia pages and law lists
- DuckDuckGo search results

Known seed URLs skip the LLM pre-filter because they are already treated as high-confidence starting points.

### Zone 2 - Extraction

For each candidate law, the extractor:

- downloads the source document using browser, HTTP, or fallback scraping
- uses OCR for scanned PDFs when needed
- sends the source text and indicator instructions to the configured LLM backend
- writes one CSV row per extracted clause

The extraction CSV contains 16 fields, including the official act name, section reference, verbatim clause, rationale, source URL, and confidence.

### Zone 3 - Verification

Verification re-fetches the cited document and compares the extracted claim with the actual source text.

It uses:

- deterministic section matching first
- fuzzy text comparison as a secondary check
- an LLM fallback only when direct matching fails

The verifier writes these statuses: `PASS`, `FAIL`, `NEEDS_REVIEW`, and `URL_BROKEN`.

### Zone 4 - Scoring

Scoring reads either the verified CSV or the raw extraction CSV and computes the final weighted pillar score. The result is written as both text and CSV into `outputs/zone4/`.

The implemented scoring logic includes country-specific handling for known edge cases such as Malaysia's sectoral data protection scope, Singapore public-agency exclusions, and the non-regulatory treatment of Pillar 6 indicator 6.5.

## Output Files

Each run produces artifacts in `outputs/`:

- `outputs/zone1/zone1_{country}_pillar{pillar}.json`
- `outputs/zone2/zone2_{country}_pillar{pillar}.csv`
- `outputs/zone3/zone2_{country}_pillar{pillar}_verified.csv`
- `outputs/zone4/zone4_{country}_pillar{pillar}_score.txt`
- `outputs/zone4/zone4_{country}_pillar{pillar}_score.csv`

The score report files are the final deliverable for a country/pillar run.

## Data And Inputs

The repository includes a curated seed inventory file named `Singapore, Malaysia, Australia, Legal Inventory.csv`. It is used as a starting point for discovery and helps the pipeline prioritize official or near-official sources.

The implementation also contains country alias handling for `sg`, `my`, and `au`, so either the short or long country names can be used at the CLI.

## Known Limitations

- Some official sources return 403 or otherwise block automated access, which can reduce extraction quality for specific indicators.
- Large PDFs can take a long time to verify, especially if OCR or LLM fallback is required.
- Pillar 6 indicator 6.5 is scored externally and is intentionally skipped in the extraction workflow.
- Output quality depends on source availability, document formatting, and the configured model backend.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `DASHSCOPE_API_KEY not set` | Add a valid key to `.env` or use a different backend. |
| `playwright not found` | Run `playwright install chromium`. |
| `TesseractNotFoundError` | Install Tesseract OCR and add it to PATH. |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` inside the virtual environment. |
| Rate limit or timeout errors | Increase `--rate-delay` and try a smaller `--limit`. |
| Windows console encoding issues | Use Windows Terminal. |

## Notes For Contributors

This repository is maintained by the PillarAI team. Changes should preserve the four-stage workflow and the CSV/output formats used by the downstream pipeline.

If you extend the project, update the README alongside the code so the setup steps, CLI flags, and output paths stay aligned.
