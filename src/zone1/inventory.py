import csv
import os

from src.zone1.config import COUNTRY_CONFIG
from src.zone1.indicators import PILLAR_6_INDICATORS, PILLAR_7_INDICATORS


INVENTORY_CSV = "data/legal_inventory.csv"

INVENTORY_PILLAR_KEYWORDS = {
    "6": [
        "cross-border", "transfer", "localisation", "localization",
        "data flow", "digital economy", "data transfer",
        "cross border", "data residency", "transborder",
        "free trade agreement", "cptpp", "rcep", "depa",
        "server", "data centre", "infrastructure",
    ],
    "7": [
        "data protection", "personal data", "privacy",
        "cybersecurity", "cyber security", "computer misuse",
        "data retention", "retention period",
        "data protection officer", "dpo", "dpia",
        "government access", "lawful access", "surveillance",
        "interception", "personal information",
        "data breach", "notifiable data breach",
    ],
}

INVENTORY_INDICATOR_KEYWORDS = {
    "6.1": ["prohibit", "must not transfer", "ban", "restrict transfer", "local processing"],
    "6.2": ["local storage", "store locally", "data localization", "data residency"],
    "6.3": ["server", "data centre", "infrastructure", "computing facility"],
    "6.4": ["consent", "adequacy", "safeguard", "conditional", "binding corporate rules"],
    "6.5": ["cptpp", "rcep", "depa", "digital economy agreement", "free trade agreement", "trade agreement"],
    "7.1": ["data protection act", "privacy act", "personal data", "data protection framework"],
    "7.2": ["cybersecurity", "cyber security", "computer misuse", "information security"],
    "7.3": ["retention", "retain", "keep records", "minimum period"],
    "7.4": ["dpo", "data protection officer", "dpia", "impact assessment"],
    "7.5": ["government access", "lawful access", "interception", "surveillance", "police access"],
}


def load_inventory(csv_path, country_key, pillar_id):
    country_display = COUNTRY_CONFIG[country_key]["display"]
    pillar_keywords = INVENTORY_PILLAR_KEYWORDS.get(pillar_id, [])

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

                    search_text = f"{act} {cluster} {policy}".lower()
                    if not any(kw in search_text for kw in pillar_keywords):
                        continue

                    matched = False
                    for ind_id, ind_kws in INVENTORY_INDICATOR_KEYWORDS.items():
                        if ind_id.startswith(pillar_id) and any(kw in search_text for kw in ind_kws):
                            seed_entry = {
                                "title": act.strip(),
                                "url": ref.strip(),
                                "snippet": policy.strip()[:500] or f"{act.strip()} — from legal inventory",
                                "source": "inventory",
                                "coverage": coverage.strip(),
                                "timeframe": timeframe.strip(),
                            }
                            inventory_seeds.setdefault(ind_id, []).append(seed_entry)
                            matched = True

                    if not matched:
                        for ind_id in (PILLAR_6_INDICATORS if pillar_id == "6" else PILLAR_7_INDICATORS):
                            seed_entry = {
                                "title": act.strip(),
                                "url": ref.strip(),
                                "snippet": policy.strip()[:500] or f"{act.strip()} — from legal inventory",
                                "source": "inventory",
                                "coverage": coverage.strip(),
                                "timeframe": timeframe.strip(),
                            }
                            inventory_seeds.setdefault(ind_id, []).append(seed_entry)

        print(f"       [INVENTORY] Loaded {len(existing_rows)} rows for {country_key}, "
              f"{sum(len(v) for v in inventory_seeds.values())} mapped as seeds, "
              f"{len(all_inventory_urls)} unique URLs")
    except Exception as e:
        print(f"       [INVENTORY] Error reading {csv_path}: {e} — skipping")

    return inventory_seeds, all_inventory_urls, existing_rows


def update_inventory_csv(csv_path, existing_rows, new_discoveries, country_key, pillar_id):
    if not new_discoveries:
        return

    fieldnames = [
        "country", "Act.and.or.practice", "Coverage", "Timeframe",
        "References", "cluster", "Region", "Cov.Name", "name",
        "policy.description",
    ]

    new_rows = []
    for d in new_discoveries:
        new_rows.append({
            "country": country_key,
            "Act.and.or.practice": d.get("title", ""),
            "Coverage": d.get("coverage", ""),
            "Timeframe": d.get("timeframe", ""),
            "References": d.get("url", ""),
            "cluster": f"Digital Trade — Pillar {pillar_id}",
            "Region": COUNTRY_CONFIG[country_key]["display"],
            "Cov.Name": "",
            "name": d.get("indicator", ""),
            "policy.description": d.get("snippet", ""),
        })

    write_rows = existing_rows + new_rows
    try:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(write_rows)
        print(f"       [INVENTORY] Appended {len(new_rows)} new entries to {csv_path}")
    except Exception as e:
        print(f"       [INVENTORY] Error writing {csv_path}: {e}")
