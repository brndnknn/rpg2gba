#!/usr/bin/env python3
"""S4 sanity check + artifact generator — mint the slice map constants.

Mints MAP_/LAYOUT_/MAPSEC_ for the slice (Map032 Moki Town, Map049 1F/spawn,
Map048 2F) from the real map_infos.json + reference/map_name_overrides.json,
checks every name against the FORK's vanilla MAP_* set (fail-loud on collision),
writes the alias header + map_groups.json + persisted state under
output/uranium-build/porymap/, and prints the table so it can be eyeballed before
S8 assembly.

Run:  PYTHONPATH=src python3 scripts/pathfinder_map_constants_preview.py
"""
from __future__ import annotations

from pathlib import Path

from rpg2gba.pipeline import _load_dotenv
from rpg2gba.tileset_converter import map_constants as mc

SLICE_IDS = [32, 48, 49]
MAP_INFOS = Path("output/uranium-build/map_infos.json")
OVERRIDES = Path("reference/map_name_overrides.json")
PORYMAP = Path("output/uranium-build/porymap")


def main() -> None:
    _load_dotenv()  # populate RPG2GBA_POKEEMERALD from .env-paths
    vanilla = mc.load_vanilla_map_consts()
    print(f"loaded {len(vanilla)} vanilla MAP_* constants from the fork")

    reg = mc.build_map_constants(
        SLICE_IDS,
        map_infos_path=MAP_INFOS,
        overrides_path=OVERRIDES,
        state_path=PORYMAP / "map_constants.json",
        alias_header_path=PORYMAP / "uranium_map_aliases.h",
        map_groups_path=PORYMAP / "map_groups.json",
    )

    print(f"\n{'id':>4}  {'MAP_*':<34} {'dir':<26} display")
    for uid in SLICE_IDS:
        c = reg.get(uid)
        collide = " !! VANILLA COLLISION" if c.map_const in vanilla else ""
        print(f"{uid:>4}  {c.map_const:<34} {c.dir_name:<26} {c.display_name}{collide}")

    print("\nalias header:")
    print((PORYMAP / "uranium_map_aliases.h").read_text(encoding="utf-8"))

    collisions = [reg.get(u).map_const for u in SLICE_IDS if reg.get(u).map_const in vanilla]
    print("RESULT:", "COLLISION-FREE" if not collisions else f"COLLIDES: {collisions}")


if __name__ == "__main__":
    main()
