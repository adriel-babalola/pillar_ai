import os
import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE = "https://openrouter.ai/api/v1"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "models/gemini-2.0-flash"

DEFAULT_MODEL = "poolside/laguna-xs.2:free"
FALLBACK_MODEL = "gemini"

MAX_TEXT_CHARS = 120000  # Gemini handles up to 1M tokens — increase for quality

PROXY_URL = os.getenv("PROXY_URL") or None

CACHE_DIR = Path(".scrape_cache")
CACHE_DIR.mkdir(exist_ok=True)

CSV_FIELDS = [
    "Pillar_ID",
    "Indicator_ID",
    "Act_and_or_practice",
    "Coverage",
    "Impact_or_comments",
    "Timeframe",
    "References",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)
