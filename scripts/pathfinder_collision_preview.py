#!/usr/bin/env python3
"""S2 sanity check — render the slice maps' collision from tile_map + passages.

Validates that the pure-bucket / source-passages collision rule yields a WALKABLE
map (the real point of S2) BEFORE step 3 builds on it. Approximates RMXP's
multi-layer passability: scanning top->bottom, a cell is blocked if the first
non-empty tile blocks (passage low nibble != 0); a priority-0 passable tile makes
it walkable; all-empty = void = blocked. Then BFS from the spawn to confirm the
map's warp tiles are reachable.

Run:  PYTHONPATH=src python3 scripts/pathfinder_collision_preview.py
"""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path

from rpg2gba.tileset_converter.layout import TileGrid, _cell_blocked
from rpg2gba.tileset_converter.tile_map import load_tile_map

MAPS_DIR = Path("output/uranium-build/maps")

# from S1 (PATHFINDER_FINDINGS.md): spawn + the warp tiles we care about per map
SLICE = {
    49: {"spawn": (7, 7), "warps": {"door->town": (10, 11), "stairs->2F": (12, 3)}},
    48: {"spawn": (4, 3), "warps": {"stairs->1F": (3, 3)}},       # arrival from 49 EV003
    32: {"spawn": (28, 31), "warps": {"house door": (28, 31)}},   # arrival from 49 door
}


def cell_blocked(grid: TileGrid, tm, ts: int, x: int, y: int) -> bool:
    """Delegates to layout._cell_blocked (single source of truth, CLAUDE.md §4.3) —
    also carries the terrain-tag skips (Shadow/Bridge, `layout.TERRAIN_TAG_*`)."""
    return _cell_blocked(grid, x, y, tm, ts)


def reachable(grid: TileGrid, blocked, start: tuple[int, int]) -> set[tuple[int, int]]:
    seen = {start}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < grid.xsize and 0 <= ny < grid.ysize and (nx, ny) not in seen:
                if not blocked[ny][nx]:
                    seen.add((nx, ny))
                    q.append((nx, ny))
    return seen


def main() -> None:
    tm = load_tile_map()
    for mid, info in SLICE.items():
        data = json.loads((MAPS_DIR / f"Map{mid:03d}.json").read_text(encoding="utf-8"))
        ts = data["tileset_id"]
        t = data["tiles"]
        grid = TileGrid(t["xsize"], t["ysize"], t["zsize"], t["data"])
        blocked = [[cell_blocked(grid, tm, ts, x, y) for x in range(grid.xsize)]
                   for y in range(grid.ysize)]
        n_pass = sum(not b for row in blocked for b in row)
        total = grid.xsize * grid.ysize
        spawn = info["spawn"]
        reach = reachable(grid, blocked, spawn)
        print(f"\n=== Map{mid:03d}  {grid.xsize}x{grid.ysize}  tileset {ts}  "
              f"passable {n_pass}/{total} ({100*n_pass//total}%) ===")
        sx, sy = spawn
        print(f"  spawn {spawn} blocked={blocked[sy][sx]}  reachable cells={len(reach)}")
        for label, (wx, wy) in info["warps"].items():
            ok = (wx, wy) in reach
            print(f"  warp '{label}' @ ({wx},{wy}): blocked={blocked[wy][wx]} "
                  f"reachable-from-spawn={'YES' if ok else 'NO'}")
        if grid.xsize <= 40:
            for y in range(grid.ysize):
                row = []
                for x in range(grid.xsize):
                    if (x, y) == spawn:
                        row.append("P")
                    elif (x, y) in (w for w in info["warps"].values()):
                        row.append("D")
                    else:
                        row.append("#" if blocked[y][x] else ".")
                print("    " + "".join(row))


if __name__ == "__main__":
    main()
