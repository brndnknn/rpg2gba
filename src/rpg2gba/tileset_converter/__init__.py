"""Phase 5 — Map Layout & Tileset Conversion.

Deterministic conversion of Uranium map *geometry* (tile grid, tilesets, event
placement, warps, connections) from the Phase 3 JSON into the
Porymap/pokeemerald-expansion format. No LLM, no budget; output lands under
`output/uranium-build/porymap/` and is dropped into the fork only in Phase 7.

See `PHASE5_PLAN.md` (repo root) for the assignment brief and this package's
`README.md` for the module map. Sections:

  tile_map.py        5.1  tile substitution table (source of truth)
  layout.py          5.2  tile grid -> map.bin / border.bin / layouts.json
  map_constants.py        MAP_*/LAYOUT_*/MAPSEC_* registry + map_groups.json
  metadata_wiring.py 5.3  map.json header + object/warp events + encounters
  connections.py     5.4  map adjacency
  phase5.py               orchestrator over all 199 maps
"""
from __future__ import annotations
