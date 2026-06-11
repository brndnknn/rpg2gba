# `tileset_converter` — Phase 5 (Map Layout & Tileset Conversion)

> **Start here, then read `PHASE5_PLAN.md` at the repo root** (the full assignment
> brief: the RMXP↔GBA tile-model explainer, the open design questions, exit
> criteria). This file is the table of contents and the "where do I start" guide.

## What this package does

Converts Uranium map *geometry* (the tile grid, tilesets, event placement, warps,
connections) from the Phase 3 JSON into the Porymap/pokeemerald-expansion format.
Deterministic Python; no LLM, no budget. Output lands under
`output/uranium-build/porymap/` — **never** written into the fork (that is Phase 7).

## The modules, in build order

| File | Section | One-liner |
|---|---|---|
| `tile_map.py` | 5.1 | Load/validate/lookup the `(tileset_id, tile_id) → metatile_id` table. The source of truth. |
| `layout.py` | 5.2 | One map's tile grid → `map.bin` blockdata + `border.bin` + `layouts.json` entry. |
| `map_constants.py` | — | Mint stable `MAP_*`/`LAYOUT_*`/`MAPSEC_*`; resolve the Phase 4 `MAP_URANIUM_<N>` warp placeholders. |
| `metadata_wiring.py` | 5.3 | Assemble `map.json`: header, object/warp events, page dispatch, encounters. |
| `connections.py` | 5.4 | Map-to-map adjacency. |
| `phase5.py` | — | Orchestrator that runs the sections over all 199 maps. |

Each module's docstring is its own assignment card (objective, I/O, constraints,
acceptance checklist). Every public function currently `raise NotImplementedError`s
— that is the work.

## Inputs you read (all read-only)

- `output/uranium-build/maps/MapNNN.json` — Phase 3 tile grid + events (primary input).
- `output/uranium-build/map_infos.json` — map names + the RMXP editor tree (`parent_id`; *not* adjacency).
- `output/uranium-build/intermediate/wild_encounters.json` — encounter tables, keyed by Uranium map id (Phase 2).
- `output/uranium-build/intermediate/map_metadata.json` — music/weather/healing-spot per map (Phase 2).
- `output/uranium-build/scripts/*.pory` — Phase 4 script block labels to point object_events at.
- `$RPG2GBA_POKEEMERALD/data/{maps,layouts}/` — the *format* you are matching + the metatiles Approach A reuses.
- `reference/tileset_map.json` — the hand-authored substitution table (5.1).

## Outputs you write (under `output/`)

```
output/uranium-build/porymap/
├── layouts/<Name>/map.bin
├── layouts/<Name>/border.bin
├── layouts/layouts.json
├── maps/<Name>/map.json
└── maps/map_groups.json
```

## How to work this assignment

1. Read `PHASE5_PLAN.md`, especially the two-tile-model section and the Open
   Design Questions — bring Q1–Q5 to the operator before writing much code.
2. Implement `tile_map.py` (5.1) first; everything downstream needs `lookup()`.
3. Then `layout.py` (5.2) on a tiny synthetic map before the real corpus.
4. `map_constants.py`, then `metadata_wiring.py` (5.3), then `connections.py` (5.4).
5. Wire `pipeline.py phase5` **last** (avoid touching shared pipeline code while
   the Phase 4 bulk run is active).
6. Tests live in `tests/test_tileset_converter.py` — they are pre-written as
   skipped acceptance tests. Un-skip and make them pass as you implement.
