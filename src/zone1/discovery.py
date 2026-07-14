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

    for ind_id in sorted(pillar_data.keys()):
        ind_data = pillar_data[ind_id]
        print(f"\n  [{ind_id}] {ind_data['name']}")

        results = []

        for seed in seeds.get(ind_id, []):
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
            print(f"       Inventory: {inv_count} entry(ies) from legal inventory CSV")

        queries = generate_queries(ind_data, display_name, country_conf["site_filter"])
        # Wikipedia discovery
        search_results = await search_wikipedia(
            ind_id, queries, country_key, limit, cache,
            ind_data["keywords"], crawler, inventory_urls=inv_urls,
        )
        seen_urls = {r["url"] for r in results}
        for sr in search_results:
            if sr["url"] not in seen_urls:
                results.append(sr)
                seen_urls.add(sr["url"])
        # DuckDuckGo discovery (additional searches beyond Wikipedia)
        ddg_results = await search_searchengine(
            ind_id, queries, country_key, limit, cache,
            ind_data["keywords"], crawler, inventory_urls=inv_urls,
        )
        for sr in ddg_results:
            if sr["url"] not in seen_urls:
                results.append(sr)
                seen_urls.add(sr["url"])

        all_candidates[ind_id] = results
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

    # Filter noise: keep seeds always, drop score-0 discovery entries, prefer live+primary
    for ind_id in all_candidates:
        filtered = []
        for c in all_candidates[ind_id]:
            if c.get("source") in ("seed", "inventory"):
                filtered.append(c)
            elif c.get("relevance_score", 0) > 0:
                if c.get("live", True):
                    filtered.append(c)
                else:
                    print(f"       [SKIP] Broken URL: {c.get('url','')[:60]}")
            if c.get("source") == "discovery" and c.get("source_type") == "secondary":
                c["relevance_score"] = max(c.get("relevance_score", 0) * 0.5, 0.1)
        all_candidates[ind_id] = filtered

    os.makedirs("outputs/zone1", exist_ok=True)
    filename = f"outputs/zone1/zone1_{country_key}_pillar{pillar_id}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_candidates, f, indent=2, ensure_ascii=False)
    print(f"\n  [SAVED] {filename}")
    return filename
