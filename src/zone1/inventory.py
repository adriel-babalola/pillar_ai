import csv
import os

from src.zone1.config import COUNTRY_CONFIG
from src.zone1.indicators import PILLAR_6_INDICATORS, PILLAR_7_INDICATORS

INVENTORY_CSV = "Singapore, Malaysia, Australia, Legal Inventory.csv"


def load_inventory(csv_path, country_key, pillar_id):
    country_display = COUNTRY_CONFIG[country_key]["display"]
    inventory_seeds = {}
    all_inventory_urls = set()
    existing_rows = []

    if not os.path.exists(csv_path):
        print(f"       [INVENTORY] File not found: {csv_path} — skipping")
        return inventory_seeds, all_inventory_urls, existing_rows

    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                country = (row.get("country") or "").strip().lower()
                if country != country_key:
                    continue
                existing_rows.append(row)

                act = row.get("Act.and.or.practice") or ""
                cluster = row.get("cluster") or ""
                policy = row.get("policy.description") or ""
                ref = row.get("References") or ""
                coverage = row.get("Coverage") or ""
                timeframe = row.get("Timeframe") or ""

                if ref:
                    all_inventory_urls.add(ref.strip())
                    seed_entry = {
                        "title": act.strip(),
                        "url": ref.strip(),
                        "snippet": policy.strip()[:500] or f"{act.strip()} — from legal inventory",
                        "source": "inventory",
                        "coverage": coverage.strip(),
                        "timeframe": timeframe.strip(),
                    }
                    for ind_id in list(PILLAR_6_INDICATORS) + list(PILLAR_7_INDICATORS):
                        if ind_id.startswith(pillar_id):
                            inventory_seeds.setdefault(ind_id, []).append(seed_entry)

        print(f"       [INVENTORY] Loaded {len(existing_rows)} rows for {country_key}, "
              f"{sum(len(v) for v in inventory_seeds.values())} mapped as seeds, "
              f"{len(all_inventory_urls)} unique URLs")
    except Exception as e:
        print(f"       [INVENTORY] Error reading {csv_path}: {e} — skipping")

    return inventory_seeds, all_inventory_urls, existing_rows
