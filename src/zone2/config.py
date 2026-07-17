import os
import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE = "https://openrouter.ai/api/v1"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "models/gemini-2.5-flash"

OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")
OLLAMA_BASE = "https://ollama.com"

ALIBABA_API_KEY = os.getenv("DASHSCOPE_API_KEY")
ALIBABA_BASE = "https://ws-qi5wh5fl237ivx9r.ap-northeast-1.maas.aliyuncs.com/compatible-mode/v1"

DEFAULT_MODEL = "alibaba:qwen3.7-plus,gemini,ollama:gemma4"

MAX_TEXT_CHARS = 220000  # Gemini handles up to 1M tokens — increase for quality

PROXY_URL = os.getenv("PROXY_URL") or None

CACHE_DIR = Path(".scrape_cache")
CACHE_DIR.mkdir(exist_ok=True)

CSV_FIELDS = [
    "Economy",
    "Pillar_ID",
    "Indicator_ID",
    "Act_and_or_practice",
    "Law_Number_Ref",
    "Last_Amended",
    "Coverage",
    "Article_Section",
    "Discovery_Tag",
    "Location_Reference",
    "Verbatim_Snippet",
    "Mapping_Rationale",
    "Impact_or_comments",
    "Timeframe",
    "References",
    "Confidence",
]

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
    return COUNTRY_ALIASES.get(raw.strip().lower(), raw.strip().lower())

COUNTRY_DISPLAY = {
    "singapore": "Singapore",
    "malaysia": "Malaysia",
    "australia": "Australia",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)
