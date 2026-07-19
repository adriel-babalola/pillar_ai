#!/usr/bin/env python3
"""
Pillar AI — Unified End-to-End Pipeline Orchestrator.

Runs Discovery → Extraction → Verification → Scoring for RDTII Pillars 6 & 7.

Usage:
    # Single country (both pillars)
    python run.py --country sg

    # Single country + specific pillar
    python run.py --country sg --pillar 6

    # All 3 countries x both pillars
    python run.py --all

    # Single zone only
    python run.py --zone discovery --country sg
    python run.py --zone extraction --country sg --pillar 6
"""

import argparse
import csv
import logging
import os
import subprocess
import sys
import time


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


def banner(title: str):
    w = 60
    log.info("")
    log.info("#" * w)
    log.info("## " + title.center(w - 6) + " ##")
    log.info("#" * w)
    log.info("")


def run(cmd: list[str], desc: str) -> bool:
    log.info(">>> Starting: %s", desc)
    log.info(">>> Command:  %s", " ".join(cmd))
    t0 = time.time()
    try:
        result = subprocess.run(cmd)
    except KeyboardInterrupt:
        log.warning("Interrupted during %s", desc)
        return False
    elapsed = time.time() - t0
    if result.returncode != 0:
        log.error("!!! FAILED: %s (exit code %d, took %.1fs)", desc, result.returncode, elapsed)
        return False
    log.info("OK: %s (%.1fs)", desc, elapsed)
    return True


def run_discovery(country: str, pillar: str, limit: int = 10) -> bool:
    return run(
        ["python", "zone1_discovery.py",
         "--country", country,
         "--pillar", pillar,
         "--limit", str(limit)],
        f"Zone 1 :: Discovery | {country} Pillar {pillar}",
    )


def run_extraction(
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
    return run(cmd, f"Zone 2 :: Extraction | {country} Pillar {pillar}")


def run_verify(country: str, pillar: str, model: str = "") -> bool:
    csv_path = f"outputs/zone2/zone2_{resolve(country)}_pillar{pillar}.csv"
    if not os.path.exists(csv_path):
        log.error("!!! Zone 2 CSV not found: %s -- run extraction first", csv_path)
        log.error("    python run.py --zone extraction --country %s --pillar %s", country, pillar)
        return False
    cmd = ["python", "zone3_blindverifier.py", "--input", csv_path]
    if model:
        cmd.extend(["--model", model])
    return run(cmd, f"Zone 3 :: Verify | {country} Pillar {pillar}")


def run_score(country: str, pillar: str) -> bool:
    from src.zone4.scoring import score_all_indicators, compute_pillar_score, print_score_report
    from src.zone2.config import COUNTRY_DISPLAY

    economy = COUNTRY_DISPLAY.get(resolve(country), resolve(country).capitalize())
    verified = f"outputs/zone3/zone2_{resolve(country)}_pillar{pillar}_verified.csv"
    raw = f"outputs/zone2/zone2_{resolve(country)}_pillar{pillar}.csv"
    csv_path = verified if os.path.exists(verified) else raw

    if not os.path.exists(csv_path):
        log.error("!!! No CSV found at %s or %s -- run extraction first", verified, raw)
        return False

    log.info(">>> Scoring %s Pillar %s from: %s", economy, pillar, csv_path)
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    scores = score_all_indicators(rows, pillar)
    result = compute_pillar_score(scores)
    report = print_score_report(result, economy, pillar)

    banner(f"SCORE RESULT -- {economy} Pillar {pillar}")
    print(report)
    print()

    os.makedirs("outputs/zone4", exist_ok=True)
    txt_path = f"outputs/zone4/zone4_{resolve(country)}_pillar{pillar}_score.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(report)
    log.info("Score report saved: %s", txt_path)

    csv_out = f"outputs/zone4/zone4_{resolve(country)}_pillar{pillar}_score.csv"
    with open(csv_out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Indicator_ID", "Score", "Weight", "Weighted_Score", "Rationale"])
        for ind in result["indicators"]:
            w.writerow([ind["indicator_id"], ind["score"], ind["weight"], ind["weighted_score"], ind["rationale"]])
        w.writerow([])
        w.writerow(["PILLAR_SCORE", result["overall_score"]])
    log.info("Score CSV saved: %s", csv_out)
    return True


def process_one(
    country: str,
    pillar: str,
    zones: list[str],
    model: str,
    limit: int,
    rate_delay: float,
):
    country_key = resolve(country)
    from src.zone2.config import COUNTRY_DISPLAY
    display = COUNTRY_DISPLAY.get(country_key, country_key.capitalize())
    banner(f"{display} -- Pillar {pillar}")

    run_all = "all" in zones

    if run_all or "discovery" in zones:
        banner(f"ZONE 1: Discovery -- {display} Pillar {pillar}")
        ok = run_discovery(country_key, pillar, limit if limit else 10)
        if not ok:
            return
        log.info("Done Zone 1 -- %s Pillar %s", display, pillar)

    if run_all or "extraction" in zones:
        banner(f"ZONE 2: Extraction -- {display} Pillar {pillar}")
        ok = run_extraction(country_key, pillar, model, limit or 5, rate_delay)
        if not ok:
            return
        log.info("Done Zone 2 -- %s Pillar %s", display, pillar)

    if run_all or "verify" in zones:
        banner(f"ZONE 3: Verification -- {display} Pillar {pillar}")
        ok = run_verify(country_key, pillar, model)
        if not ok:
            return
        log.info("Done Zone 3 -- %s Pillar %s", display, pillar)

    if run_all or "score" in zones:
        banner(f"ZONE 4: Scoring -- {display} Pillar {pillar}")
        run_score(country_key, pillar)
        log.info("Done Zone 4 -- %s Pillar %s", display, pillar)

    log.info("Complete: %s Pillar %s", display, pillar)


def process_country(country: str, pillars: list[str], zones: list[str], model: str, limit: int, rate_delay: float):
    country_key = resolve(country)
    from src.zone2.config import COUNTRY_DISPLAY
    display = COUNTRY_DISPLAY.get(country_key, country_key.capitalize())
    banner(f"COUNTRY: {display} -- Pillars {', '.join(pillars)}")

    for p in pillars:
        process_one(country_key, p, zones, model, limit, rate_delay)

    log.info("")
    log.info("=" * 60)
    log.info("  ALL DONE -- %s (Pillars %s)", display, ", ".join(pillars))
    log.info("=" * 60)

    for p in pillars:
        z1 = f"outputs/zone1/zone1_{country_key}_pillar{p}.json"
        z2 = f"outputs/zone2/zone2_{country_key}_pillar{p}.csv"
        z3 = f"outputs/zone3/zone2_{country_key}_pillar{p}_verified.csv"
        z4 = f"outputs/zone4/zone4_{country_key}_pillar{p}_score.txt"
        for path, label in [(z1, "Zone 1"), (z2, "Zone 2"), (z3, "Zone 3"), (z4, "Zone 4")]:
            if os.path.exists(path):
                size = os.path.getsize(path)
                log.info("  %s: %s (%d bytes)", label, path, size)


def main():
    parser = argparse.ArgumentParser(
        description="Pillar AI -- Unified Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python run.py --country sg                    # both pillars, one country\n"
            "  python run.py --country sg --pillar 6         # single pillar\n"
            "  python run.py --zone discovery --country sg   # discovery only, both pillars\n"
            "  python run.py --all                           # all 6 combos\n"
        ),
    )
    parser.add_argument("--country", default=None, help="Country: sg/singapore, my/malaysia, au/australia")
    parser.add_argument("--pillar", default=None, choices=["6", "7"], help="Pillar: 6 or 7 (default: both)")
    parser.add_argument("--zone", default="all",
                        help="Zone(s): discovery, extraction, verify, score, all (default: all)")
    parser.add_argument("--all", action="store_true", help="Process all 3 countries x 2 pillars")
    parser.add_argument("--model", default="", help="LLM model override")
    parser.add_argument("--limit", type=int, default=0, help="Max candidates per indicator")
    parser.add_argument("--rate-delay", type=float, default=3.0, help="Seconds between LLM calls")

    args = parser.parse_args()
    zones = [z.strip() for z in args.zone.split(",")]

    if args.all:
        t0 = time.time()
        banner("RUNNING ALL: Singapore + Malaysia + Australia x Pillars 6 + 7")
        for c in ["singapore", "malaysia", "australia"]:
            try:
                process_country(c, ["6", "7"], zones, args.model, args.limit, args.rate_delay)
            except KeyboardInterrupt:
                log.warning("Interrupted -- skipping %s", c)
                continue
        elapsed = time.time() - t0
        banner("FULL PIPELINE COMPLETE")
        log.info("Total time: %.1fs (%.1f min)", elapsed, elapsed / 60)
        return

    if not args.country:
        parser.print_help()
        print("\nError: --country is required (or use --all)")
        return

    pillars = [args.pillar] if args.pillar else ["6", "7"]
    try:
        process_country(args.country, pillars, zones, args.model, args.limit, args.rate_delay)
    except KeyboardInterrupt:
        log.warning("Interrupted")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.warning("Pipeline interrupted by user")
