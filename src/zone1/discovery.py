import json
import os

from crawl4ai.async_configs import BrowserConfig
from crawl4ai import AsyncWebCrawler

from src.zone1.config import COUNTRY_CONFIG
from src.zone1.indicators import PILLAR_6_INDICATORS, PILLAR_7_INDICATORS
from src.zone1.seeds import SEED_URLS
from src.zone1.inventory import load_inventory, update_inventory_csv, INVENTORY_CSV
from src.zone1.discovery_wikipedia import search_indicator
from src.zone1.search import generate_queries


async def process_country_pillar(country_key, pillar_id, limit, crawler):
    country_conf = COUNTRY_CONFIG[country_key]
    display_name = country_conf["display"]

    pillar_data = PILLAR_6_INDICATORS if pillar_id == "6" else PILLAR_7_INDICATORS
    pillar_label = f"Pillar {pillar_id}"

    print(f"\n{'='*60}")
    print(f"  {display_name} - {pillar_label}")
    print(f"{'='*60}")

    inv_seeds, inv_urls, inv_rows = load_inventory(INVENTORY_CSV, country_key, pillar_id)
    print(f"  [INVENTORY] {len(inv_urls)} known URLs loaded for duplicate prevention")

    all_candidates = {}
    cache = {}
    seeds = SEED_URLS.get(country_key, {})
    new_discoveries = []

    for ind_id in sorted(pillar_data.keys()):
        ind_data = pillar_data[ind_id]
        print(f"\n  [{ind_id}] {ind_data['name']}")

        results = []

        for seed in seeds.get(ind_id, []):
            if seed["url"] in inv_urls:
                print(f"       Seed: {seed['title'][:70]} (already in inventory)")
            results.append({
                "indicator": ind_id,
                "title": seed["title"],
                "url": seed["url"],
                "snippet": seed["snippet"],
                "query_used": "seed_url (curated)",
                "relevance_score": 1.0,
                "source": "seed",
            })
            print(f"       Seed: {seed['title'][:70]}")

        inv_count = 0
        for inv_seed in inv_seeds.get(ind_id, []):
            url = inv_seed["url"]
            if url not in {r["url"] for r in results}:
                results.append({
                    "indicator": ind_id,
                    "title": inv_seed["title"],
                    "url": url,
                    "snippet": inv_seed["snippet"],
                    "query_used": "legal_inventory.csv",
                    "relevance_score": 1.0,
                    "source": "inventory",
                    "coverage": inv_seed.get("coverage", ""),
                    "timeframe": inv_seed.get("timeframe", ""),
                })
                inv_count += 1
        if inv_count:
            print(f"       Inventory: {inv_count} entry(ies) from legal_inventory.csv")

        queries = generate_queries(ind_data, display_name, country_conf["site_filter"])
        search_results = await search_indicator(
            ind_id, queries, country_key, limit, cache,
            ind_data["keywords"], crawler, inventory_urls=inv_urls,
        )

        seen_urls = {r["url"] for r in results}
        for sr in search_results:
            if sr["url"] not in seen_urls:
                results.append(sr)
                seen_urls.add(sr["url"])
                title = sr.get("title", "")
                is_law_like = any(kw in title.lower() for kw in [
                    "act", "regulation", "code", "guideline", "standard",
                    "order", "bill", "amendment", "rule", "directive",
                    "policy", "framework", "strategy", "protocol",
                ])
                has_keyword_match = sr.get("relevance_score", 0) >= 0.2
                if has_keyword_match or is_law_like:
                    sr["source"] = "new_discovery"
                    sr["indicator"] = ind_id
                    new_discoveries.append(sr)

        all_candidates[ind_id] = results
        seed_count = len(seeds.get(ind_id, []))
        inv_mapped = len(inv_seeds.get(ind_id, []))
        inv_added = sum(1 for r in results if r.get("source") == "inventory")
        search_count = len(search_results)
        print(f"       Total: {len(results)} candidate(s) "
              f"({seed_count} seed + {inv_added} inventory of {inv_mapped} mapped + {search_count} search)")

        if results:
            top = results[0]
            print(f"       Top: {top['title'][:70]}...")

    os.makedirs("outputs/zone1", exist_ok=True)
    filename = f"outputs/zone1/zone1_{country_key}_pillar{pillar_id}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_candidates, f, indent=2, ensure_ascii=False)
    print(f"\n  [SAVED] {filename}")

    if new_discoveries:
        update_inventory_csv(INVENTORY_CSV, inv_rows, new_discoveries, country_key, pillar_id)
        print(f"  [INVENTORY] Added {len(new_discoveries)} new discovery(ies) to inventory")

    return filename
