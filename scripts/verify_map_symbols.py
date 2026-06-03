"""Verify that every FLAG_*/VAR_* a converted map references is actually defined.

This is the narrow "rung-2" check for the Phase 4 calibration gate: poryscript
(rung 1) transpiles a .pory without checking that its constants exist, so a flag
the agent emits but nobody defines only fails later, at fork assembly. This script
closes that gap deterministically (no fork build): a referenced FLAG_/VAR_ token is
"defined" if it is in the registry header (the switches/vars/self-switches/
temp-switches in flag_state.json) or a pokeemerald-expansion built-in (flags.h /
vars.h). Anything else is an undefined-symbol bug we own.

Phase-5 placeholders (MAP_URANIUM_*, CommonEvent_*) are *not* FLAG_/VAR_ tokens, so
they are intentionally out of scope here — their resolution is deferred by design.

Usage:
    python scripts/verify_map_symbols.py Map002
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from rpg2gba.pbs_converter._naming import load_fork_constants
from rpg2gba.pipeline import _load_dotenv

_load_dotenv()  # populate RPG2GBA_POKEEMERALD etc. from .env-paths if unset
OUT = Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build"
_TOKEN_RE = re.compile(r"\b(?:FLAG|VAR)_[A-Z0-9_]+\b")


def _registry_names(state: dict) -> set[str]:
    names: set[str] = set()
    for block in ("switches", "variables", "self_switches", "temp_switches"):
        names |= set(state.get(block, {}).values())
    return names


def main(stem: str) -> int:
    pory = (OUT / "scripts" / f"{stem}.pory").read_text(encoding="utf-8")
    state = json.loads((OUT / "flag_state.json").read_text(encoding="utf-8"))

    defined = _registry_names(state)
    fork = os.environ.get("RPG2GBA_POKEEMERALD")
    if fork and Path(fork).is_dir():
        fork_path = Path(fork)
        defined |= load_fork_constants(fork_path / "include/constants/flags.h", "FLAG")
        defined |= load_fork_constants(fork_path / "include/constants/vars.h", "VAR")
    else:
        print("WARNING: fork not reachable — fork built-ins (e.g. VAR_RESULT) unchecked")

    referenced = set(_TOKEN_RE.findall(pory))
    undefined = sorted(referenced - defined)

    print(f"{stem}: {len(referenced)} distinct FLAG_/VAR_ tokens referenced")
    for tok in sorted(referenced):
        mark = "UNDEFINED" if tok in undefined else "ok"
        print(f"  [{mark:9}] {tok}")
    if undefined:
        print(f"\nFAIL: {len(undefined)} undefined symbol(s): {', '.join(undefined)}")
        return 1
    print("\nPASS: every FLAG_/VAR_ token resolves (registry header or fork built-in)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "Map002"))
