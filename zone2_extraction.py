"""
Zone 2 — Extraction & Structured Mapping for RDTII Pillars 6 & 7.

Usage:
    python zone2_extraction.py --country singapore --pillar 6
    python zone2_extraction.py --country singapore --pillar 7 --model google/gemma-4-31b-it:free
"""

import argparse
import asyncio
import csv
import json
import os

from src.prompts import PILLAR_6_INDICATORS, PILLAR_7_INDICATORS
from src.zone2.config import CSV_FIELDS, OPENROUTER_API_KEY, DEFAULT_MODEL, log
from src.zone2.extraction import process_indicator


INDICATOR_SETS = {"6": PILLAR_6_INDICATORS, "7": PILLAR_7_INDICATORS}


async def main():
    parser = argparse.ArgumentParser(
        description="Zone 2 — Extraction & Structured Mapping for RDTII"
    )
    parser.add_argument("--input", help="Zone 1 JSON path (default: zone1_{country}_pillar{pillar}.json)")
    parser.add_argument("--output", help="Output CSV path (default: zone2_{country}_pillar{pillar}.csv)")
    parser.add_argument("--country", default="singapore", choices=["singapore", "malaysia", "australia"])
    parser.add_argument("--pillar", required=True, choices=["6", "7"])
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"OpenRouter model ID (default: {DEFAULT_MODEL})")
    parser.add_argument("--max-candidates", type=int, default=5, help="Max candidates per indicator (default: 5)")
    parser.add_argument("--rate-delay", type=float, default=3.0, help="Seconds between LLM calls (default: 3.0)")
    parser.add_argument("--limit", type=int, default=0, help="Process only N candidates per indicator (default: all)")
    args = parser.parse_args()

    country = args.country
    pillar = args.pillar
    input_path = args.input or f"outputs/zone1/zone1_{country}_pillar{pillar}.json"
    output_path = args.output or f"outputs/zone2/zone2_{country}_pillar{pillar}.csv"

    indicators = INDICATOR_SETS[pillar]
    log.info("=" * 55)
    log.info("Zone 2 — Extraction & Mapping")
    log.info("Country: %s  |  Pillar: %s  |  Indicators: %d", country.capitalize(), pillar, len(indicators))
    log.info("Model:   %s", args.model)
    log.info("Max candidates per indicator: %d", args.max_candidates)
    log.info("=" * 55)

    if not os.path.exists(input_path):
        log.error("Input file not found: %s", input_path)
        log.error("Run zone1_discovery.py first to generate it:")
        log.error("  python zone1_discovery.py --country %s --pillar %s", country, pillar)
        return

    with open(input_path, "r", encoding="utf-8") as f:
        candidates_by_indicator = json.load(f)
    log.info("Loaded %s (%d indicators with candidates)", input_path, len(candidates_by_indicator))

    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY.startswith("sk-or-v1-your"):
        log.error("OPENROUTER_API_KEY not set or still placeholder. Set it in .env first.")
        return

    all_rows = []
    totals = {"candidates": 0, "prefiltered": 0, "scraped": 0, "extracted": 0}

    for indicator_id in sorted(indicators.keys()):
        indicator_data = indicators[indicator_id]
        candidates = candidates_by_indicator.get(indicator_id, [])

        if not candidates:
            log.warning("  [%s] No candidates in JSON", indicator_id)
            continue

        totals["candidates"] += min(len(candidates), args.max_candidates)

        limit = args.limit if args.limit > 0 else args.max_candidates
        rows, stats = await process_indicator(
            args.model, indicator_id, indicator_data,
            candidates, limit, args.rate_delay,
        )
        all_rows.extend(rows)
        totals["prefiltered"] += stats["prefiltered"]
        totals["scraped"] += stats["scraped"]
        totals["extracted"] += stats["extracted"]

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(all_rows)

    log.info("")
    log.info("=" * 55)
    log.info("  DONE")
    log.info("  Input:    %s", input_path)
    log.info("  Output:   %s", output_path)
    log.info("  Processed %d candidates", totals["candidates"])
    log.info("  Pre-filtered passed: %d", totals["prefiltered"])
    log.info("  Successfully scraped: %d", totals["scraped"])
    log.info("  Rows extracted: %d", totals["extracted"])
    log.info("=" * 55)


if __name__ == "__main__":
    asyncio.run(main())
