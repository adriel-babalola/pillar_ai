import csv
import os

from src.zone1.config import COUNTRY_CONFIG
from src.zone1.indicators import PILLAR_6_INDICATORS, PILLAR_7_INDICATORS

INVENTORY_CSV = "Singapore, Malaysia, Australia, Legal Inventory.csv"


RELEVANT_NAMES = {
    "Cross-border data policies",
    "Domestic data protection & privacy",
}

PILLARS_6_7_DESC_KEYWORDS = [
    "data protect", "cyber", "privacy", "personal data",
    "cross-border data", "data flow", "data localization",
    "digital economy", "digital trade", "data retention",
    "data breach", "surveillance", "government access",
    "lawful access", "critical infrastructure", "computer misuse",
    "data protection impact assessment",
    "ban", "local processing", "local storage",
    "infrastructure requirement", "conditional flow",
    "binding commitment", "data transfer",
]


def _is_relevant_row(row: dict) -> bool:
    """Check if an inventory row is relevant to Pillars 6/7."""
    cluster = (row.get("cluster") or "").strip()
    name = (row.get("name") or "").strip()
    desc = (row.get("policy.description") or "").lower()
    act = (row.get("Act.and.or.practice") or "").lower()

    # Only Digital governance policies cluster
    if cluster != "Digital governance policies":
        return False

    # Must be in a relevant name category
    if name not in RELEVANT_NAMES:
        return False

    # Combined text must match Pillars 6/7 keywords
    text = f"{act} {desc}"
    if not any(w in text for w in PILLARS_6_7_DESC_KEYWORDS):
        return False

    # Act title must contain data/cyber/privacy/digital keywords (avoids Companies Act, Employment Act, etc.)
    act_keywords = ["personal data act", "data protection", "cyber",
                    "privacy", "digital economy", "digital partnership",
                    "criminal procedure", "computer misuse",
                    "advisory guideline", "guide to data",
                    "telecommunications", "free trade agreement",
                    "regional comprehensive", "asean"]
    if any(w in act for w in act_keywords):
        return True
    if "pdpa" in act or "pdpc" in act:
        return True

    return False


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
                if not _is_relevant_row(row):
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
