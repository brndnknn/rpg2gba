"""Phase 5 orchestrator — run the sections over the whole corpus.

ASSIGNMENT
==========
Objective
    Tie 5.1 -> 5.4 together into one idempotent pass over the 199 Phase 3 maps,
    writing the Porymap tree under output/uranium-build/porymap/.

    Build this LAST, after each section works standalone. Wiring this into
    `pipeline.py` (a `phase5` subcommand) is the final integration step — keep it
    out of the shared pipeline module while the Phase 4 bulk run is active, then
    add it the same way phase3/phase4 are registered.

Per-map flow (the loop you implement)
    for each MapNNN.json:
        consts  = registry.mint(map_id, display_name)            # map_constants
        layout  = convert_layout(map_json, tile_map, ...)        # 5.2
        write_blockdata(layout.blocks, .../layouts/<dir>/map.bin)
        append layout.to_layouts_entry(...) to layouts.json
        mapfile = assemble map.json (header + object/warp events + encounters) # 5.3
        write .../maps/<dir>/map.json
    then, across all maps:
        connections pass (5.4) + registry.write_map_groups(...)
        registry.save()

Constraints
    - Idempotent: a clean re-run reproduces byte-identical output (CLAUDE.md §4.2).
    - Fail loud per map with the map id in context; one bad map aborts with a
      precise message rather than silently skipping (CLAUDE.md §4.5).
    - Output ONLY under output/ (CLAUDE.md §4.4). Phase 7 drops it into the fork.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Output tree (under output/uranium-build/, set by the caller / pipeline).
PORYMAP_SUBDIR = "porymap"


def convert_all(maps_dir: Path, out_dir: Path, *, clean: bool = False) -> None:
    """Convert every MapNNN.json under `maps_dir` into the Porymap tree under
    `out_dir/PORYMAP_SUBDIR`. See the module docstring for the per-map flow.

    `clean` wipes the porymap output first (for a from-scratch idempotent run)."""
    raise NotImplementedError("phase5: drive 5.1->5.4 over all maps, idempotent + fail-loud")


def convert_one(map_path: Path, out_dir: Path) -> None:
    """Convert a single MapNNN.json — the debug entry point (analogous to
    `pipeline convert-map`). Useful while iterating on one map."""
    raise NotImplementedError("phase5: single-map debug conversion")
