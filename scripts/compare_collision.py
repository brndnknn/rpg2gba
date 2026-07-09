"""Diff our collision collapse against Uranium's EXACT playerPassable? (ground truth).

Reimplements 025__Game_Map_v17.rb::playerPassable? for a normal walking player
(not surfing/cycling/on-bridge): scan layers top->bottom, skip bridge tiles
(off-bridge) and Shadow-terrain tiles, then per-direction passage + priority.
A cell is "blocked" (single-bit collision) if it is enterable from NO cardinal
direction. Compares to scripts.pathfinder_collision_preview.cell_blocked (== the
converter's layout._cell_blocked rule) and prints both maps + every discrepancy.

Usage: python scripts/compare_collision.py --x0 33 --y0 40 --x1 43 --y1 50
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from rpg2gba.tileset_converter.layout import TileGrid, _cell_blocked
from rpg2gba.tileset_converter.tile_map import TileMap

SHADOW = 20
BRIDGE = 15
_TS = 0
MAPS_DIR = Path("output/uranium-build/maps")
TILESETS_JSON = Path("output/uranium-build/tilesets.json")
DIR_BITS = {2: 1, 4: 2, 6: 4, 8: 8}  # down/left/right/up -> RMXP passage bit


def uranium_passable(grid, passages, priorities, terrain, x, y, d) -> bool:
    """Faithful playerPassable?(x,y,d) for a walking player (bridge==0, no surf)."""
    bit = DIR_BITS[d]
    for i in (2, 1, 0):  # top layer down
        tid = grid.tile_at(x, y, i)
        if tid and terrain[tid] == BRIDGE:   # off-bridge: ignore bridge tiles
            continue
        if terrain[tid] == SHADOW:           # shadow tiles never block
            continue
        if passages[tid] & bit != 0 or passages[tid] & 0x0F == 0x0F:
            return False
        if priorities[tid] == 0:
            return True
    return True


def uranium_blocked(grid, passages, priorities, terrain, x, y) -> bool:
    """Single-bit collapse: blocked iff enterable from no cardinal direction."""
    return not any(
        uranium_passable(grid, passages, priorities, terrain, x, y, d)
        for d in (2, 4, 6, 8)
    )


def our_blocked(grid, passages, priorities, terrain, x, y) -> bool:
    """Delegates to layout._cell_blocked (single source of truth, CLAUDE.md §4.3)
    via a minimal oracle-only TileMap; `_TS` is an arbitrary key."""
    tm = TileMap(
        {}, {}, passages={_TS: passages}, priorities={_TS: priorities}, terrain_tags={_TS: terrain}
    )
    return _cell_blocked(grid, x, y, tm, _TS)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", type=int, default=32)
    ap.add_argument("--tileset", type=int, default=22)
    ap.add_argument("--x0", type=int, default=33)
    ap.add_argument("--y0", type=int, default=40)
    ap.add_argument("--x1", type=int, default=43)
    ap.add_argument("--y1", type=int, default=50)
    args = ap.parse_args()

    doc = json.loads((MAPS_DIR / f"Map{args.map:03d}.json").read_text(encoding="utf-8"))
    t = doc["tiles"]
    grid = TileGrid(t["xsize"], t["ysize"], t["zsize"], t["data"])
    ts = json.loads(TILESETS_JSON.read_text(encoding="utf-8"))[str(args.tileset)]
    pas, pri, ter = ts["passages"], ts["priorities"], ts["terrain_tags"]

    print("legend: '.'=walkable  '#'=blocked   (left=OURS  right=URANIUM truth)")
    print("    x: " + "".join(str((args.x0 + i) % 10) for i in range(args.x1 - args.x0 + 1)))
    discreps = []
    for y in range(args.y0, args.y1 + 1):
        ours_row, uran_row = [], []
        for x in range(args.x0, args.x1 + 1):
            ob = our_blocked(grid, pas, pri, ter, x, y)
            ub = uranium_blocked(grid, pas, pri, ter, x, y)
            ours_row.append("#" if ob else ".")
            uran_row.append("#" if ub else ".")
            if ob != ub:
                discreps.append((x, y, ob, ub))
        print(f"  {y:>3}  {''.join(ours_row)}    {''.join(uran_row)}")

    print(f"\n{len(discreps)} discrepancy cell(s) (ours != Uranium):")
    for x, y, ob, ub in discreps:
        cols = "/".join(str(grid.tile_at(x, y, z)) for z in range(grid.zsize))
        print(f"  ({x},{y}) ours={'blocked' if ob else 'walk'} "
              f"uranium={'blocked' if ub else 'walk'}  tiles={cols}")


if __name__ == "__main__":
    main()
