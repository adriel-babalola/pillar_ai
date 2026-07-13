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
        "--input", required=True,
        help="Path to Zone 2 CSV output (e.g., outputs/zone2/zone2_singapore_pillar6.csv)",
    )
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

    output = args.output or args.input.replace(".csv", "_verified.csv")

    print(f"  Zone 3 — Blind Citation Verification")
    print(f"  Input:  {args.input}")
    print(f"  Output: {output}")
    print(f"  Model:  {args.model}")
    print()

    await verify_csv(args.input, output, model=args.model, retries=args.retries)


if __name__ == "__main__":
    asyncio.run(main())
