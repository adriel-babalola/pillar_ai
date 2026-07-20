#!/usr/bin/env python3
"""
Reset all pipeline outputs to give a fresh user a clean start.

The repo ships with reference outputs in outputs/ so newcomers can see
what expected results look like. Run this script before your own pipeline run
to clear everything.

Usage:
    python scripts/reset_outputs.py          # with prompt
    python scripts/reset_outputs.py --force  # skip prompt
    python scripts/reset_outputs.py --dry-run  # preview only
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DIRS_TO_CLEAR = [
    "outputs/zone1",
    "outputs/zone2",
    "outputs/zone3",
    "outputs/zone4",
    "outputs/final_output",
    ".scrape_cache",
]


def collect_items():
    items = []
    for d in DIRS_TO_CLEAR:
        target = ROOT / d
        if not target.exists():
            continue
        for child in target.iterdir():
            items.append((d, child))
    return items


def print_plan(items):
    print()
    print("=" * 55)
    print("  Reset Pipeline Outputs")
    print("=" * 55)
    if not items:
        print("  Nothing to reset — outputs already clean.")
        return
    by_dir: dict[str, list[str]] = {}
    for dir_name, child in items:
        by_dir.setdefault(dir_name, []).append(child.name)
    for d in DIRS_TO_CLEAR:
        names = by_dir.get(d)
        if names:
            print(f"  {d}/  ({len(names)} item(s))")
            for n in sorted(names):
                print(f"    {n}")
        else:
            print(f"  {d}/  (empty)")
    print()


def reset_items(items, dry_run=False):
    dir_counts: dict[str, int] = {}
    for dir_name, child in items:
        dir_counts.setdefault(dir_name, 0)
        dir_counts[dir_name] += 1
        if dry_run:
            continue
        if child.is_file():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)

    print()
    if dry_run:
        print("  Dry-run complete. Would delete:")
        for d in DIRS_TO_CLEAR:
            cnt = dir_counts.get(d, 0)
            if cnt:
                print(f"    {cnt} item(s) in {d}/")
        print()
        return

    for d in DIRS_TO_CLEAR:
        cnt = dir_counts.get(d, 0)
        if cnt:
            print(f"  Deleted {cnt} item(s) in {d}/")
    print("  Done. Outputs are clean.")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Reset pipeline outputs for a fresh run."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Skip confirmation prompt."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview what would be deleted without deleting."
    )
    args = parser.parse_args()

    items = collect_items()
    if not items:
        print("  Nothing to reset — outputs already clean.")
        return

    print_plan(items)

    if args.dry_run:
        reset_items(items, dry_run=True)
        return

    if not args.force:
        try:
            answer = input("  Delete these outputs? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            print("  Aborted.")
            return
        if answer not in ("y", "yes"):
            print("  Aborted.")
            return

    reset_items(items)


if __name__ == "__main__":
    main()
