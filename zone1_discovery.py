"""
Zone 1 — Source Discovery for RDTII Pillars 6 & 7.

CLI entry point — delegates to the refactored src.zone1 package.
"""
import argparse
import asyncio
import os

from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig

from src.zone1.config import COUNTRY_CONFIG
from src.zone1.discovery import process_country_pillar


async def main():
    parser = argparse.ArgumentParser(
        description="Zone 1 — Source Discovery for RDTII Pillars 6 & 7"
    )
    parser.add_argument(
        "--country",
        choices=["singapore", "malaysia", "australia"],
        help="Country to process (default: all three)",
    )
    parser.add_argument(
        "--pillar",
        choices=["6", "7"],
        help="Pillar to process (default: both)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Max results per query (default: 10)",
    )
    args = parser.parse_args()

    countries = [args.country] if args.country else list(COUNTRY_CONFIG.keys())
    pillars = [args.pillar] if args.pillar else ["6", "7"]

    print("ZONE 1 DISCOVERY — Source Discovery for RDTII")
    print(f"Countries: {', '.join(c.capitalize() for c in countries)}")
    print(f"Pillars:   {', '.join(pillars)}")
    print(f"Limit:     {args.limit} results per query")

    saved_files = []
    browser_cfg = BrowserConfig(
        headless=True,
        enable_stealth=True,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        extra_args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
        ],
    )
    try:
        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            for c in countries:
                for p in pillars:
                    fname = await process_country_pillar(c, p, args.limit, crawler)
                    saved_files.append(fname)
    except KeyboardInterrupt:
        print("\n\n  Interrupted — saving partial results...")
    finally:
        print(f"\n{'='*60}")
        print("  DONE — All outputs saved:")
        for f in saved_files:
            size = os.path.getsize(f) if os.path.exists(f) else 0
            print(f"    {f}  ({size:,} bytes)")
        print(f"{'='*60}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
