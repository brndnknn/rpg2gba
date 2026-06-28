#!/usr/bin/env python3
"""S5 sanity check + artifact generator — assemble the slice map.json files.

Mints the slice map constants, then runs the S5 wiring (object/warp events, header,
self-switch dispatchers) for Map032/048/049, writing map.json + dispatcher .pory
under output/uranium-build/porymap/ and printing a per-map summary (event split,
warp wiring, walkable overrides, dispatchers) for eyeballing before S8 assembly.

Run:  PYTHONPATH=src python3 scripts/pathfinder_map_wiring_preview.py
"""
from __future__ import annotations

import json
from pathlib import Path

from rpg2gba.pipeline import _load_dotenv
from rpg2gba.tileset_converter import map_constants as mc
from rpg2gba.tileset_converter import metadata_wiring as mw
from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS

SLICE_IDS = sorted(SLICE_MAP_IDS)
MAPS = Path("output/uranium-build/maps")
META = Path("output/uranium-build/intermediate/map_metadata.json")
MAP_INFOS = Path("output/uranium-build/map_infos.json")
OVERRIDES = Path("reference/map_name_overrides.json")
PORYMAP = Path("output/uranium-build/porymap")


def main() -> None:
    _load_dotenv()
    reg = mc.build_map_constants(
        SLICE_IDS, map_infos_path=MAP_INFOS, overrides_path=OVERRIDES,
        state_path=PORYMAP / "map_constants.json",
    )
    overrides = mw.build_slice_maps(
        SLICE_IDS, maps_dir=MAPS, registry=reg, metadata_path=META,
        out_dir=PORYMAP / "maps", dispatcher_dir=PORYMAP / "dispatch",
    )

    for uid in SLICE_IDS:
        consts = reg.get(uid)
        mj = json.loads((PORYMAP / "maps" / consts.dir_name / "map.json").read_text("utf-8"))
        print(f"\n=== Map{uid:03d} {consts.map_const} ({mj['map_type']}) ===")
        print(f"  objects: {len(mj['object_events'])}  warps: {len(mj['warp_events'])}")
        for w in mj["warp_events"]:
            print(f"    warp ({w['x']},{w['y']}) -> {w['dest_map']} #{w['dest_warp_id']}")
        print(f"  walkable overrides (force collision 0): {sorted(overrides[uid])}")
        disp = PORYMAP / "dispatch" / f"Map{uid:03d}_dispatch.pory"
        if disp.exists():
            print("  dispatchers:")
            for line in disp.read_text(encoding="utf-8").splitlines():
                print(f"    {line}")


if __name__ == "__main__":
    main()
