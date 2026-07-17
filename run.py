#!/usr/bin/env python3
"""
Pillar AI — Unified End-to-End Pipeline Orchestrator.

Runs all three zones (Discovery → Extraction → Verification) in sequence,
or individual zones independently.

Usage:
    # End-to-end (recommended)
    python run.py --country sg --pillar 6

    # Single zone only
    python run.py --zone discovery --country sg --pillar 6
    python run.py --zone extraction --country sg --pillar 6
    python run.py --zone verify --country sg --pillar 6

    # Score an existing Zone 2/3 CSV
    python run.py --zone score --country sg --pillar 6

    # All countries, both pillars
    python run.py --all

Flags:
    --country     Country: sg/singapore, my/malaysia, au/australia
    --pillar      Pillar: 6 or 7
    --zone        Run only specific zone: discovery, extraction, verify, score
    --all         Run all 3 countries × 2 pillars
    --model       LLM model for extraction/verification
    --limit       Max candidates per indicator (Zone 1) or max to process (Zone 2)
    --rate-delay  Seconds between LLM calls (default: 3.0)
    --help        Show help
"""

import argparse
import asyncio
import logging
import os
import subprocess
import sys


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("run")


COUNTRY_ALIASES = {
    "sg": "singapore", "sgp": "singapore", "singapore": "singapore",
    "my": "malaysia", "mys": "malaysia", "malaysia": "malaysia",
    "au": "australia", "aus": "australia", "australia": "australia",
}


def resolve(raw: str) -> str:
    return COUNTRY_ALIASES.get(raw.strip().lower(), raw.strip().lower())


def run(cmd: list[str], desc: str) -> bool:
    log.info("=" * 55)
    log.info("  %s", desc)
    log.info("  %s", " ".join(cmd))
    log.info("=" * 55)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        log.error("FAILED: %s (exit code %d)", desc, result.returncode)
        return False
    log.info("OK: %s", desc)
    return True


async def run_discovery(country: str, pillar: str, limit: int = 10):
    return run(
        ["python", "zone1_discovery.py",
         "--country", country,
         "--pillar", pillar,
         "--limit", str(limit)],
        f"Zone 1 — Discovery: {country} Pillar {pillar}",
    )


async def run_extraction(
    country: str, pillar: str, model: str = "",
    limit: int = 5, rate_delay: float = 3.0,
) -> bool:
    cmd = [
        "python", "zone2_extraction.py",
        "--country", country,
        "--pillar", pillar,
        "--max-candidates", str(limit),
        "--rate-delay", str(rate_delay),
    ]
    if model:
        cmd.extend(["--model", model])
    return run(cmd, f"Zone 2 — Extraction: {country} Pillar {pillar}")


async def run_verify(country: str, pillar: str, model: str = "") -> bool:
    csv_path = f"outputs/zone2/zone2_{resolve(country)}_pillar{pillar}.csv"
    if not os.path.exists(csv_path):
        log.error("Zone 2 CSV not found: %s — run extraction first", csv_path)
        log.error("  python run.py --zone extraction --country %s --pillar %s", country, pillar)
        return False
    cmd = [
        "python", "zone3_blindverifier.py",
        "--input", csv_path,
    ]
    if model:
        cmd.extend(["--model", model])
    return run(cmd, f"Zone 3 — Verification: {country} Pillar {pillar}")


async def run_score(country: str, pillar: str) -> bool:
    """Score an existing Zone 2/3 CSV using the Zone 4 scoring module."""
    import csv
    from src.zone4.scoring import score_all_indicators, compute_pillar_score, print_score_report
    from src.zone2.config import COUNTRY_DISPLAY

    economy = COUNTRY_DISPLAY.get(resolve(country), resolve(country).capitalize())

    # Try verified CSV first, then raw Zone 2 CSV
    verified = f"outputs/zone3/zone2_{resolve(country)}_pillar{pillar}_verified.csv"
    raw = f"outputs/zone2/zone2_{resolve(country)}_pillar{pillar}.csv"
    csv_path = verified if os.path.exists(verified) else raw

    if not os.path.exists(csv_path):
        log.error("No CSV found at %s or %s — run extraction + verify first", verified, raw)
        return False

    log.info("Scoring from: %s", csv_path)
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    scores = score_all_indicators(rows, pillar)
    result = compute_pillar_score(scores)
    report = print_score_report(result, economy, pillar)
    print(f"\n{report}\n")

    # Save score report
    os.makedirs("outputs/zone4", exist_ok=True)
    out_path = f"outputs/zone4/zone4_{resolve(country)}_pillar{pillar}_score.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    log.info("Score report saved: %s", out_path)

    # Also save as CSV with per-indicator scores
    csv_out = f"outputs/zone4/zone4_{resolve(country)}_pillar{pillar}_score.csv"
    with open(csv_out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Indicator_ID", "Score", "Weight", "Weighted_Score", "Rationale"])
        for ind in result["indicators"]:
            w.writerow([
                ind["indicator_id"],
                ind["score"],
                ind["weight"],
                ind["weighted_score"],
                ind["rationale"],
            ])
        w.writerow([])
        w.writerow(["PILLAR_SCORE", result["overall_score"]])
    log.info("Score CSV saved: %s", csv_out)
    return True


async def process_one(
    country: str,
    pillar: str,
    zones: list[str],
    model: str,
    limit: int,
    rate_delay: float,
):
    country_key = resolve(country)
    log.info("Processing %s Pillar %s — zones: %s", country_key, pillar, ", ".join(zones))

    if "discovery" in zones or "all" in zones:
        ok = await run_discovery(country_key, pillar, limit if limit else 10)
        if not ok:
            return

    if "extraction" in zones or "all" in zones:
        ok = await run_extraction(country_key, pillar, model, limit or 5, rate_delay)
        if not ok:
            return

    if "verify" in zones or "all" in zones:
        ok = await run_verify(country_key, pillar, model)
        if not ok:
            return

    if "score" in zones or "all" in zones:
        await run_score(country_key, pillar)

    log.info("Done: %s Pillar %s", country_key, pillar)


async def main():
    parser = argparse.ArgumentParser(
        description="Pillar AI — Unified Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python run.py --country sg --pillar 6               # end-to-end\n"
            "  python run.py --zone discovery --country sg --pillar 6  # discovery only\n"
            "  python run.py --all                                  # all 6 combos\n"
        ),
    )
    parser.add_argument("--country", default=None, help="Country: sg/singapore, my/malaysia, au/australia")
    parser.add_argument("--pillar", default=None, choices=["6", "7"], help="Pillar: 6 or 7")
    parser.add_argument("--zone", default="all",
                        help="Zone(s): discovery, extraction, verify, score, all (default: all)")
    parser.add_argument("--all", action="store_true", help="Process all 6 country-pillar combinations")
    parser.add_argument("--model", default="", help="LLM model override")
    parser.add_argument("--limit", type=int, default=0, help="Max candidates per indicator")
    parser.add_argument("--rate-delay", type=float, default=3.0, help="Seconds between LLM calls")

    args = parser.parse_args()

    zones = [z.strip() for z in args.zone.split(",")]

    if args.all:
        countries = ["singapore", "malaysia", "australia"]
        pillars = ["6", "7"]
        for c in countries:
            for p in pillars:
                await process_one(c, p, zones, args.model, args.limit, args.rate_delay)
        log.info("All 6 country-pillar combinations processed.")
        return

    if not args.country or not args.pillar:
        parser.print_help()
        print("\nError: --country and --pillar are required (unless --all is set)")
        return

    await process_one(args.country, args.pillar, zones, args.model, args.limit, args.rate_delay)


if __name__ == "__main__":
    asyncio.run(main())
