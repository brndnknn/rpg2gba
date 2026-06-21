"""Throwaway recon: for slice tilesets 19 + 22, print tileset_name +
autotile_names from the (re-dumped) tilesets.json and resolve them against the
actual files under RPG2GBA_URANIUM_SRC/Graphics/{Tilesets,Autotiles}. Grounds
the source-resolution module. Read-only."""
from __future__ import annotations

import json
import os
from pathlib import Path

SRC = Path(os.environ.get("RPG2GBA_URANIUM_SRC", "/home/b/repos/uranium-src/_unpacked"))
TS = json.loads(Path("output/uranium-build/tilesets.json").read_text(encoding="utf-8"))

TILESET_DIR = SRC / "Graphics" / "Tilesets"
AUTOTILE_DIR = SRC / "Graphics" / "Autotiles"

tileset_files = {p.name for p in TILESET_DIR.iterdir()} if TILESET_DIR.exists() else set()
autotile_files = {p.name for p in AUTOTILE_DIR.iterdir()} if AUTOTILE_DIR.exists() else set()


def resolve(name: str, files: set[str]) -> str:
    """RMXP stores base names without extension; the file is <name>.png. Report
    exact / case-insensitive / missing."""
    if not name:
        return "(empty slot)"
    cand = f"{name}.png"
    if cand in files:
        return f"OK -> {cand}"
    low = {f.lower(): f for f in files}
    if cand.lower() in low:
        return f"case-fold -> {low[cand.lower()]}"
    return f"MISSING ({cand!r})"


for tid in ("19", "22"):
    e = TS[tid]
    print(f"\n=== tileset {tid}: {e['name']!r} ===")
    print(f"  tileset_name = {e['tileset_name']!r}")
    print(f"    {resolve(e['tileset_name'], tileset_files)}")
    print("  autotile_names (slot: name -> resolution):")
    for slot, an in enumerate(e.get("autotile_names") or []):
        base = 48 * (slot + 1)
        print(f"    slot {slot} (tile base {base}): {an!r}  {resolve(an, autotile_files)}")
