"""Throwaway census: distinct tiles + autotile usage for the pathfinder slice
(Maps 49/48/32). Sizes the GBA tileset-budget + autotile decisions before we
build the image pipeline. Read-only; prints to stdout."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

MAPS = {49: "Player's House 1F", 48: "Player's House 2F", 32: "Moki Town"}
OUT = Path("output/uranium-build/maps")

AUTOTILE_BASE = 48
STATIC_BASE = 384


def classify(tid: int) -> str:
    if tid == 0:
        return "empty"
    if tid < STATIC_BASE:
        return "autotile"
    return "static"


for mid, label in MAPS.items():
    doc = json.loads((OUT / f"Map{mid:03d}.json").read_text(encoding="utf-8"))
    t = doc["tiles"]
    ts_id = doc["tileset_id"]
    data = t["data"]
    distinct = set(x for x in data if x != 0)
    kinds = Counter(classify(x) for x in distinct)
    autotiles = sorted({(x // AUTOTILE_BASE) * AUTOTILE_BASE for x in distinct if x < STATIC_BASE and x != 0})
    print(f"Map{mid:03d} {label!r}  tileset_id={ts_id}  {t['xsize']}x{t['ysize']}x{t['zsize']}")
    print(f"  distinct non-empty tiles: {len(distinct)}")
    print(f"    static={kinds.get('static',0)}  autotile-variants={kinds.get('autotile',0)}")
    print(f"  distinct autotile bases: {len(autotiles)} -> {autotiles}")
    # 4 GBA 8x8 tiles per RMXP tile (16x16 after /2), pre-dedup upper bound:
    print(f"  naive 8x8 tile count (x4, pre-dedup): {len(distinct) * 4}")
    print()
