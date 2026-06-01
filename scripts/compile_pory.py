"""Compile a .pory to a real .inc file (the compile-gate wrapper discards it).

Usage: python scripts/compile_pory.py IN.pory OUT.inc
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from rpg2gba import pipeline
from rpg2gba.conversion_agent import poryscript

pipeline._load_dotenv()
binary = poryscript.binary_path()
src, out = Path(sys.argv[1]), Path(sys.argv[2])
cmd = [str(binary), "-i", str(src), "-o", str(out), *poryscript._config_args(binary)]
proc = subprocess.run(cmd, capture_output=True, text=True)
print("returncode:", proc.returncode)
if proc.stderr.strip():
    print("stderr:", proc.stderr.strip())
print("wrote:", out if proc.returncode == 0 else "(failed)")
