COUNTRY_CONFIG = {
    "singapore": {
        "display": "Singapore",
        "domain_patterns": [
            r"\.gov\.sg",
            r"pdpc\.gov\.sg",
            r"imda\.gov\.sg",
            r"csa\.gov\.sg",
            r"mas\.gov\.sg",
            r"sso\.agc\.gov\.sg",
            r"mti\.gov\.sg",
            r"temasek\.com\.sg",
        ],
        "site_filter": "site:.gov.sg OR site:temasek.com.sg",
    },
    "malaysia": {
        "display": "Malaysia",
        "domain_patterns": [
            r"\.gov\.my",
            r"agc\.gov\.my",
            r"pdp\.gov\.my",
            r"mcmc\.gov\.my",
            r"miti\.gov\.my",
            r"bnm\.gov\.my",
        ],
        "site_filter": "site:.gov.my",
    },
    "australia": {
        "display": "Australia",
        "domain_patterns": [
            r"\.gov\.au",
            r"legislation\.gov\.au",
            r"oaic\.gov\.au",
            r"dfat\.gov\.au",
            r"acma\.gov\.au",
            r"austlii\.edu\.au",
        ],
        "site_filter": "site:.gov.au OR site:austlii.edu.au",
    },
}

COUNTRY_ALIASES = {
    "sg": "singapore",
    "sgp": "singapore",
    "singapore": "singapore",
    "my": "malaysia",
    "mys": "malaysia",
    "malaysia": "malaysia",
    "au": "australia",
    "aus": "australia",
    "australia": "australia",
}

def resolve_country(raw: str) -> str:
    """Resolve country alias to canonical key. Falls back to raw if unknown."""
    return COUNTRY_ALIASES.get(raw.strip().lower(), raw.strip().lower())
