"""Find the stipple-classified (shadow) tiles in Moki Town, report their alpha
profile, and locate where they sit on the map so we can crop a house+shadow region.

Usage: python scripts/shadow_locate.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from rpg2gba.tileset_converter.graphics.quantize import classify_tile
from rpg2gba.tileset_converter.graphics.raster import NATIVE_TILE_PX, TileRasterizer
from rpg2gba.tileset_converter.graphics.sources import load_tileset_sources

MAP_ID, TILESET_ID = 32, 22
TS = NATIVE_TILE_PX
SUB = TS // 2


def main():
    doc = json.loads(Path(f"output/uranium-build/maps/Map{MAP_ID:03d}.json").read_text("utf-8"))
    t = doc["tiles"]
    xs, ys, zs = t["xsize"], t["ysize"], t["zsize"]
    data = t["data"]
    used = sorted({x for x in data if x})
    raster = TileRasterizer(load_tileset_sources(TILESET_ID))

    # Which tile_ids contain at least one stipple-classified 8x8 quadrant?
    stipple_tids = {}
    for tid in used:
        arr = np.asarray(raster.render(tid).convert("RGBA"))
        modes = []
        for q in (arr[0:SUB, 0:SUB], arr[0:SUB, SUB:TS], arr[SUB:TS, 0:SUB], arr[SUB:TS, SUB:TS]):
            m = classify_tile(q[..., 3])
            modes.append(m)
            if m == "stipple":
                a = q[..., 3]
                part = a[(a > 0) & (a < 255)]
                stipple_tids.setdefault(tid, []).append(
                    (int(part.min()) if part.size else 0,
                     int(round(float(part.mean()))) if part.size else 0,
                     int(part.max()) if part.size else 0))
    print(f"{len(stipple_tids)} tile_ids have >=1 stipple quadrant.")
    print("tile_id : (partial-alpha min, mean, max) per stipple quadrant")
    for tid, profs in sorted(stipple_tids.items()):
        print(f"  {tid}: {profs}")

    # Locate stipple tiles on the map (any layer); report bounding cells.
    cells = []
    for z in range(zs):
        for y in range(ys):
            for x in range(xs):
                if data[z * (ys * xs) + y * xs + x] in stipple_tids:
                    cells.append((x, y))
    if cells:
        xsv = [c[0] for c in cells]
        ysv = [c[1] for c in cells]
        print(f"\nstipple tiles appear at {len(cells)} cells; "
              f"x {min(xsv)}..{max(xsv)}, y {min(ysv)}..{max(ysv)}")
        from collections import Counter
        common = Counter(cells).most_common(0)  # noqa
        # Print a few representative clusters (first 12 distinct cells)
        seen = []
        for c in cells:
            if c not in seen:
                seen.append(c)
            if len(seen) >= 16:
                break
        print("sample cells (x,y):", seen)


if __name__ == "__main__":
    main()
