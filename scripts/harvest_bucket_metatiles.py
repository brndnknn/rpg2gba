#!/usr/bin/env python3
"""S2 (pathfinder) — harvest bucket metatile ids from vanilla pokeemerald maps.

Read-only. Decodes a vanilla layout's map.bin + border.bin (inverse of the
block packing: metatile = b & 0x3FF, collision = (b>>10)&3, elevation = (b>>12)&0xF)
and reports candidate metatiles for the passability buckets:
  - passable bucket  = a common collision-0 metatile (floor / ground)
  - blocked bucket   = a common collision-1 metatile (wall / obstacle)
  - void bucket      = the metatile that fills border.bin

Pick from the printed candidates and write them into reference/tileset_map.json
"buckets". Run:  python3 scripts/harvest_bucket_metatiles.py
"""
from __future__ import annotations

import struct
from collections import Counter
from pathlib import Path

FORK = Path("/home/b/repos/pokeemerald-expansion")

# (label, layout dir, primary, secondary, the Uranium tileset it sources)
SOURCES = [
    ("INTERIOR (Uranium tileset 19)", "LittlerootTown_BrendansHouse_1F",
     "gTileset_Building", "gTileset_BrendansMaysHouse"),
    ("TOWN (Uranium tileset 22)", "LittlerootTown",
     "gTileset_General", "gTileset_Petalburg"),
]


def decode(path: Path) -> list[tuple[int, int, int]]:
    raw = path.read_bytes()
    blocks = struct.unpack(f"<{len(raw) // 2}H", raw)
    return [(b & 0x3FF, (b >> 10) & 3, (b >> 12) & 0xF) for b in blocks]


def top_by_collision(blocks: list[tuple[int, int, int]], collision: int) -> list:
    # count metatile ids at this collision class, keep a representative elevation
    c: Counter[int] = Counter()
    elev: dict[int, int] = {}
    for mt, col, el in blocks:
        if col == collision:
            c[mt] += 1
            elev.setdefault(mt, el)
    return [(mt, n, elev[mt]) for mt, n in c.most_common(8)]


def main() -> None:
    for label, dirname, primary, secondary in SOURCES:
        ld = FORK / "data" / "layouts" / dirname
        blocks = decode(ld / "map.bin")
        border = decode(ld / "border.bin")
        print(f"\n=== {label} ===")
        print(f"  source: {dirname}  ({primary} + {secondary})  {len(blocks)} cells")
        print("  PASSABLE candidates (collision 0)  [metatile xCount elev]:")
        for mt, n, el in top_by_collision(blocks, 0):
            print(f"     0x{mt:03X} ({mt:4d})  x{n:<4} elev={el}")
        print("  BLOCKED candidates (collision 1)  [metatile xCount elev]:")
        for mt, n, el in top_by_collision(blocks, 1):
            print(f"     0x{mt:03X} ({mt:4d})  x{n:<4} elev={el}")
        bc = Counter(mt for mt, _, _ in border)
        print(f"  BORDER (void) metatiles: "
              + ", ".join(f"0x{mt:03X}({mt}) x{n}" for mt, n in bc.most_common()))


if __name__ == "__main__":
    main()
