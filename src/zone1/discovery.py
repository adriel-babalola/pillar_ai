import json
import os

from crawl4ai.async_configs import BrowserConfig
from crawl4ai import AsyncWebCrawler

from src.zone1.config import COUNTRY_CONFIG
from src.zone1.indicators import PILLAR_6_INDICATORS, PILLAR_7_INDICATORS
from src.zone1.seeds import SEED_URLS
from src.zone1.inventory import load_inventory, INVENTORY_CSV
from src.zone1.discovery_wikipedia import search_indicator as search_wikipedia
from src.zone1.discovery_searchengine import search_indicator as search_searchengine
from src.zone1.utils import generate_queries


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
    global_seen_urls = set()

    for ind_id in sorted(pillar_data.keys()):
        ind_data = pillar_data[ind_id]
        if ind_data.get("auto_skip"):
            print(f"\n  [{ind_id}] {ind_data['name']} — SKIP (non-regulatory indicator)")
            all_candidates[ind_id] = []
            continue

        print(f"\n  [{ind_id}] {ind_data['name']}")

        results = []
        dedup_urls = set()

        for seed in seeds.get(ind_id, []):
            results.append({
                "indicator": ind_id,
                "title": seed["title"],
                "url": seed["url"],
                "snippet": seed["snippet"],
                "query_used": "seed_url (curated)",
                "relevance_score": 1.0,
                "source": "seed",
                "discovery_tag": "KNOWN",
            })
            dedup_urls.add(seed["url"])
            print(f"       Seed: {seed['title'][:70]}")

        inv_count = 0
        for inv_seed in inv_seeds.get(ind_id, []):
            url = inv_seed["url"]
            if url not in dedup_urls:
                results.append({
                    "indicator": ind_id,
                    "title": inv_seed["title"],
                    "url": url,
                    "snippet": inv_seed["snippet"],
                    "query_used": "legal_inventory.csv",
                    "relevance_score": 1.0,
                    "source": "inventory",
                    "discovery_tag": "KNOWN",
                    "coverage": inv_seed.get("coverage", ""),
                    "timeframe": inv_seed.get("timeframe", ""),
                })
                dedup_urls.add(url)
                inv_count += 1
        if inv_count:
            print(f"       Inventory: {inv_count} entry(ies) from legal inventory CSV")

        # Pass global_seen_urls + inv_urls to skip URLs already found by other indicators
        all_known = global_seen_urls | inv_urls
        queries = generate_queries(ind_data, display_name, country_conf["site_filter"])
        # Wikipedia discovery
        search_results = await search_wikipedia(
            ind_id, queries, country_key, limit, cache,
            ind_data["keywords"], crawler, inventory_urls=all_known,
        )
        for sr in search_results:
            if sr["url"] not in dedup_urls:
                results.append(sr)
                dedup_urls.add(sr["url"])
        # DuckDuckGo discovery (additional searches beyond Wikipedia)
        ddg_results = await search_searchengine(
            ind_id, queries, country_key, limit, cache,
            ind_data["keywords"], crawler, inventory_urls=all_known,
        )
        for sr in ddg_results:
            if sr["url"] not in dedup_urls:
                results.append(sr)
                dedup_urls.add(sr["url"])

        all_candidates[ind_id] = results
        # Track discovery-found URLs globally to avoid re-processing across indicators
        for r in results:
            if r.get("source") in ("discovery",):
                global_seen_urls.add(r["url"])
        seed_count = len(seeds.get(ind_id, []))
        inv_mapped = len(inv_seeds.get(ind_id, []))
        inv_added = sum(1 for r in results if r.get("source") == "inventory")
        search_count = len(search_results)
        ddg_count = len(ddg_results)
        print(f"       Total: {len(results)} candidate(s) "
              f"({seed_count} seed + {inv_added} inv/{inv_mapped} mapped + "
              f"{search_count} wiki + {ddg_count} web)")

        if results:
            top = results[0]
            print(f"       Top: {top['title'][:70]}...")

    # Filter noise: keep seeds always, drop low-relevance discovery entries, prefer live+primary
    for ind_id in all_candidates:
        filtered = []
        for c in all_candidates[ind_id]:
            if c.get("source") in ("seed", "inventory"):
                filtered.append(c)
            elif c.get("relevance_score", 0) >= 0.3:
                if c.get("live", True):
                    # Penalise secondary sources (guidelines, advisories over primary legislation)
                    if c.get("source_type") == "secondary":
                        c["relevance_score"] = max(c["relevance_score"] * 0.5, 0.1)
                    filtered.append(c)
                else:
                    print(f"       [SKIP] Broken URL: {c.get('url','')[:60]}")
        all_candidates[ind_id] = filtered

    os.makedirs("outputs/zone1", exist_ok=True)
    filename = f"outputs/zone1/zone1_{country_key}_pillar{pillar_id}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_candidates, f, indent=2, ensure_ascii=False)
    print(f"\n  [SAVED] {filename}")
    return filename
