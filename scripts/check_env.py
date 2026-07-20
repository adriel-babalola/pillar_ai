#!/usr/bin/env python3
"""
Pillar AI — Environment & Configuration Validator.

Run: python check_env.py

Checks every dependency, API key, and system requirement.
Outputs grouped into CRITICAL (must fix), USEFUL (nice to fix), and OK.
"""

import importlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"


def bold(s):
    return f"\033[1m{s}\033[0m" if sys.platform != "win32" else s


def green(s):
    return f"\033[92m{s}\033[0m" if sys.platform != "win32" else s


def red(s):
    return f"\033[91m{s}\033[0m" if sys.platform != "win32" else s


def yellow(s):
    return f"\033[93m{s}\033[0m" if sys.platform != "win32" else s


CRITICAL = []
USEFUL = []
PASSED = []


def critical(msg, fix=""):
    CRITICAL.append((msg, fix))


def useful(msg, fix=""):
    USEFUL.append((msg, fix))


def passed(msg):
    PASSED.append(msg)


def check_import(name, pip_name=None):
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False


def check_env_key(key):
    from dotenv import load_dotenv
    load_dotenv()
    val = os.getenv(key)
    if val and len(val) > 8:
        return val
    return None


print()
print(bold("=" * 60))
print(bold("  Pillar AI — Environment Validator"))
print(bold("=" * 60))
print()

# ── 1. Python ──────────────────────────────────────────────────────
print(bold("[1/7] Python"))
py_ver = sys.version_info
if py_ver >= (3, 10):
    passed(f"Python {py_ver[0]}.{py_ver[1]}.{py_ver[2]} (>=3.10)")
else:
    critical(f"Python {py_ver[0]}.{py_ver[1]} detected — need >=3.10", "Install Python 3.10+ from python.org")
print()

# ── 2. pip packages ────────────────────────────────────────────────
print(bold("[2/7] Core pip packages"))
project_root = Path(__file__).resolve().parent.parent
req_file = project_root / "requirements.txt"
if not req_file.exists():
    critical("requirements.txt not found", f"Expected at {req_file}")
else:
    passed("requirements.txt found")
    pip_frozen = {}
    try:
        result = subprocess.run([sys.executable, "-m", "pip", "freeze"],
                                capture_output=True, timeout=30)
        stdout = result.stdout.decode("utf-8", errors="replace")
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        for line in stdout.strip().split("\n"):
            clean = ansi_escape.sub('', line)
            if "==" in clean:
                name, ver = clean.split("==", 1)
                pip_frozen[name.lower().strip().replace("-", "_")] = ver
    except Exception:
        pass

    with open(req_file) as f:
        required_packages = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    missing = []
    for pkg_line in required_packages:
        pkg_name = re.split(r'[><=!~]+', pkg_line)[0].strip().lower().replace("-", "_")
        if pkg_name not in pip_frozen:
            missing.append(pkg_line)

    if missing:
        critical(f"Missing pip packages ({len(missing)}): {', '.join(missing[:8])}",
                 f"Run: pip install -r requirements.txt")
    else:
        passed(f"All {len(required_packages)} required packages installed")

print()

# ── 3. API keys ────────────────────────────────────────────────────
print(bold("[3/7] API keys (from .env)"))
dotenv_path = project_root / ".env"
if not dotenv_path.exists():
    critical(".env file not found", f"Create .env at {dotenv_path} with your API keys")
else:
    from dotenv import load_dotenv
    load_dotenv(str(dotenv_path))
    passed(".env file found")

    key_checks = [
        ("DASHSCOPE_API_KEY", "Alibaba DashScope (primary LLM)", "https://bailian.console.aliyun.com/"),
        ("OPENROUTER_API_KEY", "OpenRouter (fallback LLM)", "https://openrouter.ai/keys"),
        ("GEMINI_API_KEY", "Google Gemini (fallback LLM)", "https://aistudio.google.com/app/apikey"),
    ]

    for key, label, fix_url in key_checks:
        val = os.getenv(key)
        if val and len(val) > 8:
            passed(f"{label} configured")
        elif val:
            critical(f"{label}: key too short ({len(val)} chars)", f"Get a valid key at {fix_url}")
        else:
            critical(f"{label}: not set (key is empty)", f"Set in .env: {key}=your_key_here")

    ollama_key = os.getenv("OLLAMA_API_KEY")
    if ollama_key and len(ollama_key) > 8:
        passed("Ollama Cloud configured")
    elif ollama_key:
        useful("Ollama Cloud key too short", "Set a valid OLLAMA_API_KEY in .env")
    else:
        useful("Ollama Cloud not configured (optional fallback)", "Only needed if Alibaba/Gemini fail")

    laws_sg_token = os.getenv("LAWS_SG_MCP_TOKEN")
    if laws_sg_token and len(laws_sg_token) > 8:
        useful("laws.sg MCP token present but NOT YET USED by pipeline", "Will be used in future MCP client implementation")
    else:
        useful("laws.sg MCP token not set (optional)", "Get one at https://laws.sg/account/settings for future use")

print()

# ── 4. External tools (Tesseract, Playwright) ──────────────────────
print(bold("[4/7] External tools"))
tesseract = shutil.which("tesseract")
if tesseract:
    passed(f"Tesseract OCR found at: {tesseract}")
else:
    useful("Tesseract OCR not installed (needed for scanned PDFs)",
           "Install from https://github.com/UB-Mannheim/tesseract/wiki then add to PATH")

playwright_installed = check_import("playwright")
if playwright_installed:
    passed("Playwright Python package installed")
    try:
        result = subprocess.run([sys.executable, "-m", "playwright", "install", "--dry-run"],
                               capture_output=True, timeout=15)
        if result.returncode == 0:
            passed("Playwright browsers available")
        else:
            useful("Playwright browsers may not be installed",
                   "Run: python -m playwright install chromium")
    except FileNotFoundError:
        useful("Cannot verify Playwright browsers",
               "Run: python -m playwright install chromium")
else:
    useful("Playwright not installed (gracefully skipped)",
           "pip install playwright && playwright install chromium")
print()

# ── 5. Module imports ──────────────────────────────────────────────
print(bold("[5/7] Pipeline module imports"))
sys.path.insert(0, str(project_root))
imports_to_check = [
    ("src.zone2.config", "config"),
    ("src.zone2.client", "LLM client"),
    ("src.zone2.scraper", "Scraper"),
    ("src.zone2.embedding", "Embedding pre-filter"),
    ("src.zone2.extraction", "Extraction logic"),
    ("src.zone2.sg_legislation_api", "laws.sg integration"),
    ("src.zone1.seeds", "Seed URLs"),
    ("src.prompts", "Prompt templates"),
]
all_imports_ok = True
for mod_name, label in imports_to_check:
    try:
        importlib.import_module(mod_name)
        passed(f"{label} imports OK")
    except Exception as e:
        critical(f"{label} import failed: {e}", f"Check {mod_name} for syntax errors")
        all_imports_ok = False
print()

# ── 6. Network connectivity ────────────────────────────────────────
print(bold("[6/7] Network connectivity"))
import requests

urls_to_check = [
    ("Alibaba DashScope", "https://ws-qi5wh5fl237ivx9r.ap-northeast-1.maas.aliyuncs.com/compatible-mode/v1"),
    ("OpenRouter", "https://openrouter.ai/api/v1"),
    ("laws.sg", "https://laws.sg/legislation/personal-data-protection-act-2012"),
    ("SSO Singapore", "https://sso.agc.gov.sg"),
    ("Legislation.gov.au", "https://www.legislation.gov.au"),
    ("AustLII", "https://www.austlii.edu.au"),
    ("LOM Malaysia", "https://lom.agc.gov.my"),
    ("PDP Malaysia", "https://www.pdp.gov.my"),
    ("OAIC Australia", "https://www.oaic.gov.au"),
]

timeout = 10
for label, url in urls_to_check:
    try:
        r = requests.get(url, timeout=timeout,
                         headers={"User-Agent": "Mozilla/5.0"},
                         allow_redirects=True)
        if r.status_code < 400:
            passed(f"{label} reachable (HTTP {r.status_code})")
        else:
            useful(f"{label}: HTTP {r.status_code}", f"Check if {url} is accessible from this network")
    except requests.exceptions.ConnectTimeout:
        useful(f"{label}: connection timeout (>={timeout}s)", f"Check network/firewall — {url}")
    except requests.exceptions.ConnectionError as e:
        useful(f"{label}: connection failed", f"Check network/firewall — {e}")
    except Exception as e:
        useful(f"{label}: {type(e).__name__}", str(e)[:120])
print()

# ── 7. LLM API key test (quick) ────────────────────────────────────
print(bold("[7/7] Quick API key validation (pings endpoint)"))
alibaba_key = os.getenv("DASHSCOPE_API_KEY")
if alibaba_key and len(alibaba_key) > 8:
    try:
        r = requests.get(
            "https://ws-qi5wh5fl237ivx9r.ap-northeast-1.maas.aliyuncs.com/compatible-mode/v1/models",
            headers={"Authorization": f"Bearer {alibaba_key}"},
            timeout=15,
        )
        if r.status_code == 200:
            passed("Alibaba DashScope key validated — models returned")
        elif r.status_code == 401:
            critical("Alibaba DashScope key rejected (HTTP 401)", "Check DASHSCOPE_API_KEY in .env")
        else:
            useful(f"Alibaba DashScope: HTTP {r.status_code}", "Key format OK but unexpected response")
    except Exception as e:
        useful(f"Alibaba DashScope ping failed: {e}", "Network issue or invalid endpoint")

openrouter_key = os.getenv("OPENROUTER_API_KEY")
if openrouter_key and len(openrouter_key) > 8:
    try:
        r = requests.get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {openrouter_key}"},
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("data", {}).get("credit"):
                passed(f"OpenRouter key validated — credits remaining")
            else:
                passed("OpenRouter key validated")
        elif r.status_code == 401:
            critical("OpenRouter key rejected (HTTP 401)", "Check OPENROUTER_API_KEY in .env")
        elif r.status_code == 403:
            critical("OpenRouter key forbidden (HTTP 403)", "Top up at https://openrouter.ai/")
    except Exception as e:
        useful(f"OpenRouter ping failed: {e}", "Network issue")

gemini_key = os.getenv("GEMINI_API_KEY")
if gemini_key and len(gemini_key) > 8:
    try:
        r = requests.get(
            f"https://generativelanguage.googleapis.com/v1/models?key={gemini_key}",
            timeout=15,
        )
        if r.status_code == 200:
            passed("Gemini key validated")
        elif r.status_code == 403:
            critical("Gemini key rejected (HTTP 403)", "Check GEMINI_API_KEY in .env")
    except Exception as e:
        useful(f"Gemini ping failed: {e}", "Network issue")
print()

# ── Summary ─────────────────────────────────────────────────────────
print(bold("=" * 60))
print(bold("  RESULTS"))
print(bold("=" * 60))

if PASSED:
    print(green(f"\n  [{len(PASSED)} checks passed]"))
    for m in PASSED:
        print(green(f"    [OK] {m}"))

if USEFUL:
    print(yellow(f"\n  [{len(USEFUL)} USEFUL items — optional improvements]"))
    for msg, fix in USEFUL:
        print(yellow(f"    {msg}"))
        if fix:
            print(f"      {yellow('i')} {fix}")

if CRITICAL:
    print(red(f"\n  [{len(CRITICAL)} CRITICAL items — must fix before running]"))
    for msg, fix in CRITICAL:
        print(red(f"    [!!] {msg}"))
        if fix:
            print(f"      {red('>')} {fix}")

print()
if not CRITICAL:
    print(green(bold("  [OK] EVERYTHING LOOKS GOOD — you are all set to use the pipeline!")))
    print(green("  Run: python run.py --country sg"))
    print(green("  Run: python run.py --all"))
else:
    print(red(bold("  [!!] FIX THE CRITICAL ITEMS ABOVE before running the pipeline.")))

print()
print(bold("=" * 60))
print()

if __name__ == "__main__":
    pass
