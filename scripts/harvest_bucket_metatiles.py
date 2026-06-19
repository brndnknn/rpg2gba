#!/usr/bin/env python3
"""S2 (pathfinder) — harvest bucket + warp metatile ids from vanilla maps.

Read-only. Decodes a vanilla layout's map.bin + border.bin (inverse of the
block packing: metatile = b & 0x3FF, collision = (b>>10)&3, elevation = (b>>12)&0xF)
and reports candidate metatiles for reference/tileset_map.json:
  - passable bucket  = a common collision-0 metatile (floor / ground)
  - blocked bucket   = a common collision-1 metatile (wall / obstacle)
  - void bucket      = the metatile that fills border.bin
  - warp metatile    = a metatile whose tileset behavior is a STEP-ON warp
                       (MB_NON_ANIMATED_DOOR / MB_LADDER / etc). A warp_event is
                       INERT unless its metatile carries a warp behavior, so the
                       layout converter stamps one of these at every warp coord.

Pick from the printed candidates and write them into reference/tileset_map.json
"buckets" / "warps". Run:  python3 scripts/harvest_bucket_metatiles.py
"""
from __future__ import annotations

import re
import struct
from collections import Counter
from pathlib import Path

FORK = Path("/home/b/repos/rpg2gba/engine")

# (label, layout dir, primary dir, secondary dir, the Uranium tileset it sources)
SOURCES = [
    ("INTERIOR (Uranium tileset 19)", "LittlerootTown_BrendansHouse_1F",
     "building", "brendans_mays_house"),
    ("TOWN (Uranium tileset 22)", "LittlerootTown",
     "general", "petalburg"),
]

# Metatile behaviors that fire a STEP-ON warp (field_control_avatar.c
# IsWarpMetatileBehavior). MB_ANIMATED_DOOR is excluded — it needs a walk-into +
# door animation; non-anim doors are simpler and direction-agnostic.
STEP_ON_WARP_BEHAVIORS = {
    "MB_WARP_DOOR", "MB_LADDER", "MB_ESCALATOR", "MB_NON_ANIMATED_DOOR",
}


def decode(path: Path) -> list[tuple[int, int, int]]:
    raw = path.read_bytes()
    blocks = struct.unpack(f"<{len(raw) // 2}H", raw)
    return [(b & 0x3FF, (b >> 10) & 3, (b >> 12) & 0xF) for b in blocks]


def behavior_names() -> list[str]:
    """The MB_* enum, in declaration order (index == behavior value)."""
    txt = (FORK / "include/constants/metatile_behaviors.h").read_text(encoding="utf-8")
    names: list[str] = []
    in_enum = False
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith("enum") or s == "{":
            in_enum = True
            continue
        if in_enum:
            if s.startswith("}"):
                break
            m = re.match(r"(MB_[A-Z0-9_]+)", s)
            if m:
                names.append(m.group(1))
    return names


def behaviors(secondary_or_primary_dir: str, base: int, kind: str) -> dict[int, int]:
    """metatile_id -> behavior value for one tileset's metatile_attributes.bin."""
    path = FORK / "data" / "tilesets" / kind / secondary_or_primary_dir / "metatile_attributes.bin"
    raw = path.read_bytes()
    vals = struct.unpack(f"<{len(raw) // 2}H", raw)
    return {base + i: (v & 0xFF) for i, v in enumerate(vals)}


def top_by_collision(blocks: list[tuple[int, int, int]], collision: int) -> list:
    c: Counter[int] = Counter()
    elev: dict[int, int] = {}
    for mt, col, el in blocks:
        if col == collision:
            c[mt] += 1
            elev.setdefault(mt, el)
    return [(mt, n, elev[mt]) for mt, n in c.most_common(8)]


def main() -> None:
    names = behavior_names()
    name_of = lambda v: names[v] if 0 <= v < len(names) else f"?{v}"
    for label, dirname, primary, secondary in SOURCES:
        ld = FORK / "data" / "layouts" / dirname
        blocks = decode(ld / "map.bin")
        border = decode(ld / "border.bin")
        print(f"\n=== {label} ===")
        print(f"  source: {dirname}  (gTileset {primary} + {secondary})  {len(blocks)} cells")
        print("  PASSABLE candidates (collision 0)  [metatile xCount elev]:")
        for mt, n, el in top_by_collision(blocks, 0):
            print(f"     0x{mt:03X} ({mt:4d})  x{n:<4} elev={el}")
        print("  BLOCKED candidates (collision 1)  [metatile xCount elev]:")
        for mt, n, el in top_by_collision(blocks, 1):
            print(f"     0x{mt:03X} ({mt:4d})  x{n:<4} elev={el}")
        bc = Counter(mt for mt, _, _ in border)
        print("  BORDER (void) metatiles: "
              + ", ".join(f"0x{mt:03X}({mt}) x{n}" for mt, n in bc.most_common()))
        # WARP candidates: scan both the primary (0..511) and secondary (512+) attrs
        beh = behaviors(primary, 0, "primary") | behaviors(secondary, 512, "secondary")
        warps = [(mt, name_of(b)) for mt, b in sorted(beh.items())
                 if name_of(b) in STEP_ON_WARP_BEHAVIORS]
        print("  WARP (step-on) candidates  [metatile behavior]:")
        for mt, nm in warps:
            print(f"     0x{mt:03X} ({mt:4d})  {nm}")


if __name__ == "__main__":
    main()
