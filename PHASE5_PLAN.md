# Phase 5 — Map Layout & Tileset Conversion: Assignment Brief

> Authoritative companions: `ROADMAP.md §Phase 5`, `CLAUDE.md`, `MEMORY.md`.
> If those conflict with this file, the roadmap wins for *what*, this file wins
> for *how/sequence*. Update this plan in-place as sections land (strike through
> completed items with a one-line note) so the next agent can resume after a
> context cut.

---

## How to read this document

This is written as a **problem set**, not a finished spec. The build agent (you)
is the student; the repo is the lab. Each section below states a *learning
objective*, the *inputs/outputs*, the *constraints that bite*, and an
*acceptance checklist*. The stub modules under `src/rpg2gba/tileset_converter/`
carry the same structure in their docstrings, with the function signatures you
must fill in. Everything currently `raise NotImplementedError`s on purpose.

The **Open Design Questions** section near the end is the part to bring back to
the operator before writing much code — those are the judgment calls where a
wrong default is expensive to unwind five phases later (CLAUDE.md §10).

---

## Context: where Phase 5 sits

Phase 3 deserialized every Uranium map to `output/uranium-build/maps/MapNNN.json`
(199 maps). Phase 4 is converting each map's *events* to Poryscript right now (an
ongoing, budget-gated bulk run). Phase 5 converts the other half of a map — its
**geometry**: the tile grid, the tilesets that draw it, where events sit, how
maps warp and connect — into the format the pokeemerald-expansion fork (and
Porymap) understands.

Phase 5 is **deterministic Python**. It spends no LLM budget and touches none of
the frozen Phase 4 conversion-agent artifacts (`prompts/`, the model). That is
exactly why it is safe to build *in parallel* with the conversion run, and why it
is the right next thing: it produces the real `MAP_*` constants that the Phase 4
warp queue is currently emitting as `MAP_URANIUM_<N>` placeholders.

```
Phase 3 maps/MapNNN.json ─┐
Phase 2 wild_encounters    ├─► Phase 5 ─► output/uranium-build/porymap/{layouts,maps,map_groups.json}
Phase 2 map_metadata       │              (+ MAP_*/LAYOUT_*/MAPSEC_* constants)
Phase 4 *.pory (scripts) ──┘
                                              │ (Phase 7 drops these into the fork)
                                              ▼
                                       data/maps, data/layouts in $RPG2GBA_POKEEMERALD
```

**Output goes under `output/` (CLAUDE.md §4.4), never into the fork directly.**
Phase 7 (§7.1) is the step that copies artifacts into `$RPG2GBA_POKEEMERALD`.
During Phase 5 the fork is *read-only reference material*: you read its map.json
/ layouts.json format and its available tilesets/metatiles, you do not write to
it.

---

## The two tile models you are translating between

This is the crux of the whole phase. Internalize it before section 5.1.

### RPG Maker XP (source)

- A map is `width × height × 3` **layers** of logical **32×32-pixel** tiles.
  In the Phase 3 JSON this is `tiles = {xsize, ysize, zsize: 3, data: [...]}`,
  a single flat row-major array. The index of cell `(x, y, z)` is
  `z * (ysize * xsize) + y * xsize + x`.
- A tile value is an id into the map's tileset (`tileset_id` in the JSON):
  - `0` = empty / transparent.
  - `48 … 383` = **autotiles** (48 ids per autotile — the engine picks one of 48
    auto-bordering variants at runtime; `48 * n` is the base tile of autotile `n`).
  - `≥ 384` = **static tiles**, indexed into the tileset bitmap. The tileset
    graphic is 8 tiles wide, so `id - 384` gives a `(row, col)` = `divmod(id-384, 8)`.
- **Passability is NOT in the map array.** RMXP stores it as per-tile passage /
  priority / terrain-tag flags on the *tileset*, parallel arrays you would have
  to deserialize separately if you want true collision. (See Open Question Q3.)

### pokeemerald-expansion / GBA (target)

- Hardware tiles are **8×8 pixels**, **16 colors** each, **≤16 palettes** per
  tileset. You cannot resize a 32×32 RGB tile onto this; you *substitute*.
- The map-author unit is a **metatile**: 16×16 pixels = a 2×2 arrangement of
  8×8 tiles, on **two internal layers** (bottom + top), i.e. 8 hardware tiles +
  attributes (behavior, layer type). Metatiles live in **tilesets**: a shared
  **primary** (`gTileset_General`, ids `0x000–0x1FF`) plus a per-area
  **secondary** (ids `0x200+`).
- A map *layout* is `width × height` **blocks**, serialized as little-endian
  `u16` in `data/layouts/<Name>/map.bin`. Each block packs:
  `metatile_id = block & 0x03FF`, `collision = (block & 0x0C00) >> 10`,
  `elevation = (block & 0xF000) >> 12`.
- A `border.bin` (the 2×2 metatiles shown past the map edge) plus a
  `layouts.json` entry (dimensions + primary/secondary tileset + bin paths)
  complete a layout. A `data/maps/<Name>/map.json` then references the layout and
  carries the header, object/warp/bg events, and connections. `map_groups.json`
  lists which maps exist and in what group; the build derives the `MAP_*`
  constant from each map.json `id` field.

**The lossy step is unavoidable:** three RMXP layers of arbitrary 32×32 art must
become one GBA metatile per cell drawn from a fixed palette of pokeemerald
metatiles (Approach A). 5.1 is where that loss is decided and recorded.

---

## Strategy: Approach A (reuse pokeemerald tilesets)

Per ROADMAP §Phase 5 we take **Approach A** for the first pass: map Uranium tiles
onto the *existing* pokeemerald-expansion metatiles (grass, path, water, building
exterior, generic interior, …). Maps will look Hoenn-styled, not Uranium-styled.
That is acceptable for a playable proof-of-concept; faithful tileset reauthoring
(Approach B) is deferred to Phase 8.

Consequence: **we author no new tileset graphics in Phase 5.** Every Uranium
`(tileset_id, tile_id)` resolves to an existing pokeemerald `metatile_id`. The
art-identity loss is the price of getting maps walkable quickly.

---

## Sections (the assignment)

Build in this order — each consumes the previous. One module per section under
`src/rpg2gba/tileset_converter/`, one commit per section, tests alongside.

### 5.1 — Tile mapping table  ·  `tile_map.py`

**Objective.** Establish and validate the single source of truth that maps an
Uranium `(tileset_id, tile_id)` to a pokeemerald `metatile_id` (+ collision /
elevation). This is the `reference/tileset_map.json` named in CLAUDE.md §4.3.

**You build:** the *loader, schema validator, and lookup* — not the table data
itself (that is hand-authored grunt work, seeded incrementally). `lookup()` must
**fail loud** (CLAUDE.md §4.5) on an unmapped tile so a map full of holes can't
slip to Phase 7.

**Inputs:** `reference/tileset_map.json` (hand-authored), the fork's tileset
metatile inventory (read-only, to know which `metatile_id`s are legal).
**Output:** an in-memory `TileMap` other sections call.

**Acceptance:**
- [ ] Round-trips: load → serialize → load is stable.
- [ ] Unmapped `(tileset_id, tile_id)` raises with the exact ids in the message.
- [ ] Autotile base ids (`48*n`) and static ids (`≥384`) both resolvable.
- [ ] A golden test on a tiny hand-built table.

### 5.2 — Map layout converter  ·  `layout.py`

**Objective.** Turn one Phase 3 `MapNNN.json` tile grid into a pokeemerald
**layout**: `map.bin` blockdata + `border.bin` + a `layouts.json` entry.

**You build:** the 3-layer → 1-metatile collapse (see Open Question Q1), the
`(tileset_id, tile_id) → metatile_id` application via 5.1, the `u16` block
packing (`metatile | collision<<10 | elevation<<12`), and the little-endian
binary writer. Must be **idempotent** (CLAUDE.md §4.2): same input → byte-
identical `.bin`.

**Inputs:** `MapNNN.json`, the `TileMap` from 5.1.
**Outputs:** `output/uranium-build/porymap/layouts/<Name>/{map.bin,border.bin}`
and an appended entry in `layouts.json`.

**Acceptance:**
- [ ] `len(map.bin) == width * height * 2` bytes.
- [ ] Round-trip: read blocks back, every metatile id is one 5.1 emitted.
- [ ] Re-running produces byte-identical output.
- [ ] A golden test on a 2×2 synthetic map.

### MAP_* / LAYOUT_* / MAPSEC_* constants  ·  `map_constants.py`

**Objective.** Be the **source of truth for map names**, the geometry analogue of
Phase 4's `flag_registry`. Mint a stable, idempotent constant for every Uranium
map id and resolve the `MAP_URANIUM_<N>` placeholders the Phase 4 warp queue is
emitting.

**You build:** deterministic minting keyed on Uranium map id → `MAP_*`,
`LAYOUT_*`, `MAPSEC_*`; a persisted state file; a header/`map_groups.json`
emitter. See Open Question Q2 — the cheap correct first pass is to *keep
`MAP_URANIUM_<N>` as the literal constant name* so no `.pory` rewrite is needed.

**Inputs:** the list of Uranium map ids, `map_infos.json` (names).
**Outputs:** the constant registry state + `map_groups.json` membership; the
resolution map that lets a warp's `MAP_URANIUM_<N>` assemble.

**Acceptance:**
- [ ] Same map id → same constant across runs (idempotent, persisted).
- [ ] Every `MAP_URANIUM_<N>` the Phase 4 queue emitted resolves to a real id.
- [ ] Names are valid C identifiers; no collisions with vanilla `MAP_*`.

### 5.3 — Map metadata wiring  ·  `metadata_wiring.py`

**Objective.** Assemble the `data/maps/<Name>/map.json`: header fields, the
**object events** (each Uranium event → an object_event at its `(x, y)` whose
`script` points at the Phase 4-generated dispatcher label), **warp events**, and
the **wild-encounter** hookup.

**You build:** event→object_event placement (coords come straight from the Phase
3 event `x`/`y`); the **per-page dispatcher** that selects which page runs from
the page `condition` (switch/variable/self-switch gates) — this is deterministic
and was prototyped by hand in the rung-3 spike (see MEMORY); the warp_events from
code-201 transfers; encounter wiring from `intermediate/wild_encounters.json`
(keyed by Uranium map id); header (music/weather/map_type) from
`intermediate/map_metadata.json`.

**Inputs:** `MapNNN.json`, `map_constants` registry, the per-map `.pory` labels
from Phase 4, `wild_encounters.json`, `map_metadata.json`.
**Output:** `output/uranium-build/porymap/maps/<Name>/map.json`.

**Acceptance:**
- [ ] Each event appears once at its correct `(x, y)`.
- [ ] `script` labels match the Phase 4 `.pory` block names exactly.
- [ ] Encounter table present iff the map has wild slots.
- [ ] Page dispatch reflects the Phase 3 page conditions (golden test).

> **Two-agent note (CLAUDE.md §1/§11):** the per-page dispatcher is *deterministic
> control flow* derived from structured page conditions — it is **your** job, not
> the conversion agent's. The agent already produced each page's body; you wire
> the page-selection skeleton around them.

### 5.4 — Connections  ·  `connections.py`

**Objective.** Produce pokeemerald map **connections** (which map borders which,
and at what offset) for the overworld maps.

**The trap:** `map_infos.json`'s `parent_id` is only the RMXP *editor tree*, **not
spatial adjacency**. RMXP has no first-class "connections" concept the way
pokeemerald does — map-to-map movement is via warp/transfer events, and the
overworld is a set of separate maps. Deriving true adjacency requires either the
region-map layout (`map_metadata` MapPosition) or manual wiring against Uranium's
overworld map. Treat full automation as a stretch goal; a correct first pass may
wire only the obvious route↔town adjacencies and leave the rest for manual
Porymap work (ROADMAP §5.4 explicitly allows manual wiring).

**Inputs:** `map_infos.json`, `map_metadata.json` (MapPosition), warp targets.
**Output:** the `connections` arrays merged into each `map.json` + group order in
`map_groups.json`.

**Acceptance:**
- [ ] No connection references a non-existent `MAP_*`.
- [ ] Offsets are consistent both directions (A→B up ⇒ B→A down).
- [ ] Documented list of maps left for manual wiring (fail-loud, not silent).

---

## Open Design Questions — RESOLVED 2026-06-06 (with the operator)

| # | Question | **Decision** |
|---|---|---|
| Q1 | **Layer collapse.** RMXP stacks 3 tile layers; a GBA metatile has only 2 internal layers. How do we collapse? | **Hybrid.** Default: topmost-non-empty layer per cell. Plus an opt-in composite-key (`"z0,z1,z2"`) table in `tileset_map.json` for combos worth preserving; `lookup` checks the composite table first, falls back to the single-tile table. |
| Q2 | **Map constant naming.** Keep `MAP_URANIUM_<N>` literal, or rename to `MAP_<REGION_NAME>`? | **Readable `MAP_<REGION_NAME>`** derived from `map_infos.json` (sanitized to valid C identifiers, collisions de-duplicated, fail loud if not unique). Reached via an **alias header** (`#define MAP_URANIUM_<N> MAP_<NAME>`) so the frozen Phase 4 `.pory` warps resolve without mutating generated output. Canonical name everywhere new = the readable one. |
| Q3 | **Collision/elevation source.** RMXP passage flags vs inherit from the target metatile? | **Inherit now, override later.** Use the chosen metatile's baseline collision/elevation; allow per-cell overrides in `tileset_map.json` for invisible-barrier / walkable-decor mismatches. (Mirrors Q1.) |
| Q4 | **Tileset assignment.** Which pokeemerald primary+secondary draws each Uranium `tileset_id`? | **One universal `(primary, secondary)` pair for ALL maps first** — get the whole corpus building + walkable, then refine per-tileset. NOTE: this caps the metatile vocabulary, so Q1's composite overrides stay mostly unused until real per-area tilesets are added. |
| Q5 | **Border tiles.** What fills `border.bin`? | **Single neutral (void/impassable) metatile now**, with an optional per-map override later. (Mirrors Q1/Q3.) |

---

## Module layout (additions)

```
src/rpg2gba/tileset_converter/        # the Phase 5 package (was an empty stub)
├── __init__.py
├── tile_map.py            # 5.1  tile substitution table: load/validate/lookup
├── layout.py              # 5.2  tile grid → map.bin/border.bin + layouts.json
├── map_constants.py       #      MAP_*/LAYOUT_*/MAPSEC_* registry + map_groups
├── metadata_wiring.py     # 5.3  map.json header + object/warp events + encounters
├── connections.py         # 5.4  map adjacency
├── phase5.py              #      orchestrator tying the sections together (CLI later)
└── README.md              #      lab manual / table of contents

reference/tileset_map.json # 5.1 source of truth (hand-authored, seeded)
tests/test_tileset_converter.py  # acceptance scaffold (skipped until implemented)
```

Pipeline wiring (`pipeline.py phase5`) is the **final** integration step — do it
last, once the sections work standalone, to avoid touching shared pipeline code
while the Phase 4 bulk run is active.

---

## Phase 5 Exit Criteria (ROADMAP, restated)

- [ ] All 199 maps produce a layout (`map.bin`/`border.bin` + `layouts.json`).
- [ ] All maps produce a `map.json` with events at correct coordinates.
- [ ] Every `MAP_URANIUM_<N>` warp placeholder resolves to a real constant.
- [ ] Encounter tables wired to maps; warps connect; (most) connections wired.
- [ ] Output is idempotent (re-run → byte-identical) and fails loud on any
      unmapped tile / unknown tileset / dangling map reference.
- [ ] Maps render in Porymap (the human spot-check; not a §9 hard gate, but the
      practical proof the geometry is right before Phase 7).

---

## Conventions reminder (CLAUDE.md §5)

Python 3.11+, built-in generics (`list[str]`, `str | None`), `dataclasses`,
`pathlib.Path`, `logging` (no `print` in non-script code), explicit
`encoding="utf-8"`, fail loud, idempotent, one source of truth per concept. Every
module gets round-trip + golden + edge-case tests before it merges (CLAUDE.md §8).
