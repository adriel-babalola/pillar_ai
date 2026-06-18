import os
import json
from dotenv import load_dotenv
from firecrawl import FirecrawlApp

load_dotenv()
API_KEY = os.getenv("FIRECRAWL_API_KEY")
if not API_KEY:
    raise ValueError("FIRECRAWL_API_KEY not found in .env")

app = FirecrawlApp(api_key=API_KEY, version='v0')

def search_pillar_61_singapore():
    queries = [
        "site:sso.agc.gov.sg Personal Data Protection Act cross-border transfer",
        "site:sso.agc.gov.sg PDPA transfer personal data overseas",
        "site:sso.agc.gov.sg 'must not transfer' personal data",
        "site:sso.agc.gov.sg data protection act cross border",
        "site:pdpc.gov.sg transfer personal data overseas"
    ]

    all_results = []

    for q in queries:
        print(f"[SEARCH] Searching: {q}")
        try:
            results = app.search(query=q, params={"limit": 10})
            if results and isinstance(results, list):
                for item in results:
                    metadata = item.get("metadata", {})
                    url = metadata.get("sourceURL") or metadata.get("url", "")
                    if "sso.agc.gov.sg" in url or "pdpc.gov.sg" in url:
                        all_results.append({
                            "title": metadata.get("title", "").strip(),
                            "url": url,
                            "snippet": metadata.get("description", ""),
                            "query": q
                        })
        except Exception as e:
            print(f"[WARN] Search failed for query '{q}': {e}")

    seen = set()
    unique_results = []
    for res in all_results:
        if res["url"] not in seen:
            seen.add(res["url"])
            unique_results.append(res)

    return unique_results

def main():
    print("[START] Starting Zone 1 discovery for Singapore, Pillar 6.1...")
    candidates = search_pillar_61_singapore()

    if not candidates:
        print("[FAIL] No official sources found. Check your API key or internet connection.")
        return

    print(f"\n[OK] Found {len(candidates)} candidate official documents:\n")
    for i, doc in enumerate(candidates, 1):
        print(f"{i}. {doc['title']}")
        print(f"   URL: {doc['url']}")
        print(f"   Snippet: {doc['snippet'][:150]}...")
        print()

    with open("zone1_singapore_6.1_candidates.json", "w", encoding="utf-8") as f:
        json.dump(candidates, f, indent=2, ensure_ascii=False)
    print(f"[SAVED] Candidate list saved to 'zone1_singapore_6.1_candidates.json'")

    if candidates:
        top_url = candidates[0]["url"]
        print(f"\n[INFO] To scrape the top candidate ({top_url}), use:")
        print(f"   scraped = app.scrape_url('{top_url}')")

if __name__ == "__main__":
    main()
