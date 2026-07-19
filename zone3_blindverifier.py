"""
Zone 3 — Blind Citation Verification for RDTII Pillars 6 & 7.

Independently verifies every citation from Zone 2 by re-fetching the
document and comparing actual text against the claimed clause.

Usage:
    python zone3_blindverifier.py --input outputs/zone2/zone2_singapore_pillar6.csv
    python zone3_blindverifier.py --input outputs/zone2/zone2_singapore_pillar6.csv --output custom_output.csv
"""

import argparse
import asyncio

from src.zone3.verifier import verify_csv


async def main():
    parser = argparse.ArgumentParser(
        description="Zone 3 — Blind Citation Verification"
    )
    parser.add_argument(
        "--input", default=None,
        help="Path to Zone 2 CSV output (e.g., outputs/zone2/zone2_singapore_pillar6.csv)",
    )
    parser.add_argument("--country", default=None, help="Country: sg/singapore, my/malaysia, au/australia")
    parser.add_argument("--pillar", default=None, choices=["6", "7"], help="Pillar: 6 or 7")
    parser.add_argument(
        "--output",
        help="Path for verified CSV (default: inserts '_verified' before .csv)",
    )
    parser.add_argument(
        "--model", default="alibaba:qwen3.7-plus",
        help="Model for LLM fallback section location (default: alibaba:qwen3.7-plus)",
    )
    parser.add_argument(
        "--retries", type=int, default=3,
        help="Max retries per row (default: 3)",
    )
    args = parser.parse_args()

    import os

    # Resolve input — use --country/--pillar as fallback
    input_path = args.input
    if not input_path:
        if args.country:
            from src.zone2.config import resolve_country
            country_key = resolve_country(args.country)
        else:
            print("Error: --input or --country/--pillar required")
            return
        input_path = f"outputs/zone2/zone2_{country_key}_pillar{args.pillar}.csv"
        if not os.path.exists(input_path):
            print(f"Error: {input_path} not found")
            return

    if args.output:
        output = args.output
    else:
        basename = os.path.basename(input_path).replace(".csv", "_verified.csv")
        output = f"outputs/zone3/{basename}"

    print("=" * 55)
    print("  Zone 3 — Blind Citation Verification")
    print(f"  Input:  {input_path}")
    print(f"  Output: {output}")
    print(f"  Model:  {args.model}")
    print("=" * 55)
    print()

    await verify_csv(input_path, output, model=args.model, retries=args.retries)


if __name__ == "__main__":
    asyncio.run(main())
