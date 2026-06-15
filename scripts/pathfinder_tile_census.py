#!/usr/bin/env python3
"""S2 prerequisite P2 (pathfinder) — distinct-tile-id census for the slice maps.

Read-only. For maps 49/48/32, walks the Phase-3 tile grid and reports, per Uranium
tileset, the distinct *normalized* tile ids actually used (autotile variants folded
to their base id, per the step-2 plan's Fact 1), each with:
  - kind: autotile N (ids 48..383) or static (row,col)=divmod(id-384, 8)
  - occurrence count across the slice
  - the source-side `passages` value from tilesets.json (collision hint:
    low nibble bits 1/2/4/8 = down/left/right/up blocked; 0 = fully passable)

The output is the exact hand-authoring worklist for reference/tileset_map.json.
Run:  PYTHONPATH=src python3 scripts/pathfinder_tile_census.py
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from rpg2gba.tileset_converter.layout import TileGrid

MAPS_DIR = Path("output/uranium-build/maps")
TILESETS_JSON = Path("output/uranium-build/tilesets.json")
SLICE = [49, 48, 32]


def normalize(tile_id: int) -> int:
    """Fold an autotile variant (48..383) to its base 48*n; pass others through."""
    if 48 <= tile_id < 384:
        return (tile_id // 48) * 48
    return tile_id


def kind(tile_id: int) -> str:
    if tile_id == 0:
        return "empty"
    if tile_id < 384:
        return f"autotile {tile_id // 48}"
    row, col = divmod(tile_id - 384, 8)
    return f"static (r{row},c{col})"


def passage_hint(passages: list[int], tile_id: int) -> str:
    if tile_id >= len(passages):
        return "passage=?? (out of range)"
    v = passages[tile_id]
    blocked = v & 0x0F
    if blocked == 0:
        return f"passage={v} PASSABLE"
    if blocked == 0x0F:
        return f"passage={v} BLOCKED(all)"
    dirs = "".join(d for bit, d in ((1, "D"), (2, "L"), (4, "R"), (8, "U")) if v & bit)
    return f"passage={v} blocked[{dirs}]"


def main() -> None:
    tilesets = json.loads(TILESETS_JSON.read_text(encoding="utf-8"))
    # counts[tileset_id][normalized_tile_id] = occurrences across the slice
    counts: dict[int, Counter[int]] = {}
    per_map: dict[int, int] = {}

    for mid in SLICE:
        data = json.loads((MAPS_DIR / f"Map{mid:03d}.json").read_text(encoding="utf-8"))
        ts_id = data["tileset_id"]
        t = data["tiles"]
        grid = TileGrid(t["xsize"], t["ysize"], t["zsize"], t["data"])
        per_map[mid] = grid.xsize * grid.ysize
        bucket = counts.setdefault(ts_id, Counter())
        for y in range(grid.ysize):
            for x in range(grid.xsize):
                for z in range(grid.zsize):
                    tid = grid.tile_at(x, y, z)
                    if tid != 0:
                        bucket[normalize(tid)] += 1

    print("slice cell counts:", {f"Map{m:03d}": n for m, n in per_map.items()})
    for ts_id in sorted(counts):
        passages = tilesets.get(str(ts_id), {}).get("passages", [])
        rows = counts[ts_id]
        print(f"\n=== Uranium tileset {ts_id} — {len(rows)} distinct (normalized) tiles "
              f"to author ===")
        for tid, n in rows.most_common():
            print(f"  id {tid:>5}  x{n:<5}  {kind(tid):<16}  {passage_hint(passages, tid)}")
        n_auto = sum(1 for t in rows if t < 384)
        n_static = sum(1 for t in rows if t >= 384)
        print(f"  -- {n_auto} autotiles + {n_static} statics = {len(rows)} entries")


if __name__ == "__main__":
    main()
