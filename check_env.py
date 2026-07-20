#!/usr/bin/env python3
"""
Pillar AI — Environment & Configuration Validator stub.
Redirects to scripts/check_env.py. Run via: python check_env.py
"""
import subprocess
import sys
from pathlib import Path

script = Path(__file__).resolve().parent / "scripts" / "check_env.py"
sys.exit(subprocess.call([sys.executable, str(script)] + sys.argv[1:]))
