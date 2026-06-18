## Day 1
What was done

zone1_discovery.py 

What it does
1. Searches official government portals for Singapore, Malaysia, and Australia to find laws related to 10 RDTII indicators (Pillar 6: cross-border data, Pillar 7: data protection/privacy)

2. For each indicator (e.g. 6.1 "Ban and local processing"), it runs 5 different search queries through Firecrawl, filters results to official .gov.sg / .gov.my / .gov.au domains only, deduplicates, scores by relevance, and outputs a JSON file per country-pillar

3. CLI usage:
python zone1_discovery.py --country singapore --pillar 6   # just one
python zone1_discovery.py                                   # all 3 countries × both pillars

4. Output — zone1_singapore_pillar6.json etc. with structure like:
{"6.1": [{"title": "PDPA 2012", "url": "https://sso.agc.gov.sg/...", "query_used": "...", "relevance_score": 0.4}], "6.2": [...]}

