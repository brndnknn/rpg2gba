"""Quick sizing for Moki Town packing cost: count distinct 8x8 tiles + distinct
<=15-colour color-sets (the n that drives the O(n^3) agglomerative packer)."""
from __future__ import annotations

import json
from pathlib import Path

from rpg2gba.tileset_converter.graphics.raster import TileRasterizer
from rpg2gba.tileset_converter.graphics.sources import load_tileset_sources

doc = json.loads(Path("output/uranium-build/maps/Map032.json").read_text(encoding="utf-8"))
data = doc["tiles"]["data"]
distinct_ids = sorted({x for x in data if x != 0})
r = TileRasterizer(load_tileset_sources(22))


def to555(p):
    return (p[0] >> 3, p[1] >> 3, p[2] >> 3)


sets = set()
n_8x8 = set()
colors = set()
for tid in distinct_ids:
    t16 = r.render(tid).convert("RGBA")
    for qy in (0, 8):
        for qx in (0, 8):
            sub = t16.crop((qx, qy, qx + 8, qy + 8))
            px = list(sub.getdata())
            key = bytes(v for p in px for v in (to555(p) if p[3] == 255 else (255, 255, 255)))
            n_8x8.add(key)
            cs = frozenset(to555(p) for p in px if p[3] == 255)
            colors |= cs
            if 0 < len(cs) <= 15:
                sets.add(cs)
print(f"distinct RMXP tiles: {len(distinct_ids)}")
print(f"distinct 8x8 tiles: {len(n_8x8)}")
print(f"distinct <=15-colour color-sets (n for packer): {len(sets)}")
print(f"total distinct 555 colours: {len(colors)}")
