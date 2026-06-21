"""Measure the per-8x8-tile distinct-colour distribution for Moki Town, to pick the
right step-4 algorithm. If most tiles have <=15 distinct 15-bit colours, each tile
fits one palette losslessly and the problem is 15-colour BIN-PACKING (partition tiles
into <=13 palettes minimising colours lost to merging), not k-means colour clustering.

Usage: python scripts/tile_color_census.py
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np

from rpg2gba.tileset_converter.graphics.quantize import resolve_alpha, to_5bit
from rpg2gba.tileset_converter.graphics.raster import NATIVE_TILE_PX, TileRasterizer
from rpg2gba.tileset_converter.graphics.sources import load_tileset_sources

MAP_ID, TILESET_ID = 32, 22
TS = NATIVE_TILE_PX
SUB = TS // 2


def main():
    doc = json.loads(Path(f"output/uranium-build/maps/Map{MAP_ID:03d}.json").read_text("utf-8"))
    used = sorted({t for t in doc["tiles"]["data"] if t})
    raster = TileRasterizer(load_tileset_sources(TILESET_ID))

    seen, ncolors = set(), []
    all_colors = set()
    for tid in used:
        arr = np.asarray(raster.render(tid).convert("RGBA"))
        for q in (arr[0:SUB, 0:SUB], arr[0:SUB, SUB:TS], arr[SUB:TS, 0:SUB], arr[SUB:TS, SUB:TS]):
            key = q.tobytes()
            if key in seen:
                continue
            seen.add(key)
            r = resolve_alpha(q)
            opq = r[..., 3] == 255
            if not opq.any():
                continue
            cols = np.unique(to_5bit(r[..., :3][opq]), axis=0)
            ncolors.append(len(cols))
            for c in cols:
                all_colors.add(tuple(int(v) for v in c))

    n = np.array(ncolors)
    hist = Counter(n.tolist())
    print(f"unique non-empty 8x8 tiles: {len(n)}")
    print(f"distinct 15-bit colours across the whole tileset: {len(all_colors)}")
    print(f"per-tile distinct colours: min {n.min()}, median {int(np.median(n))}, "
          f"mean {n.mean():.1f}, p90 {int(np.percentile(n,90))}, max {n.max()}")
    print(f"tiles with <=15 colours: {(n <= 15).sum()} / {len(n)} "
          f"({100 * (n <= 15).mean():.1f}%)")
    print(f"tiles with >15 colours (need internal reduction): {(n > 15).sum()}")
    print("histogram (ncolours: count):")
    for k in sorted(hist):
        print(f"  {k:2d}: {hist[k]}")
    budget = 13 * 15
    print(f"\n13 palettes x 15 = {budget} colour slots; tileset needs {len(all_colors)} "
          f"distinct -> must shed {max(0, len(all_colors) - budget)} via merging.")


if __name__ == "__main__":
    main()
