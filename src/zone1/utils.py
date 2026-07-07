import re

from src.zone1.config import COUNTRY_CONFIG


def is_official_url(url, country):
    patterns = COUNTRY_CONFIG[country]["domain_patterns"]
    return any(re.search(p, url, re.I) for p in patterns)


def relevance_score(text, keywords):
    if not text.strip():
        return 0.0
    lower = text.lower()
    matches = sum(1 for kw in keywords if kw.lower() in lower)
    return min(matches / len(keywords), 1.0)
