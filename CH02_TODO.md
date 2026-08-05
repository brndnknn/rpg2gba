# CH02 TODO — Route 1 (maps 33, 81)

Live work checklist for chapter CH02 (Route 1), the current build frontier.
The chapter's spec, story beats and coverage targets live in
`reference/chapters/02-route-1.md`; the corpus-wide plan is
`reference/chapters/00-atlas.md`. This file tracks only *work items*, not
design. Same conventions as `reference/archive/SLICE1_TODO.md`: commit
updates as items close; move an item to **Done** with a one-line result
rather than deleting it. Facts here are pointers — the cited code/docs stay
authoritative.

History: seeded 2026-07-13 as `SLICE2_TODO.md`; renamed 2026-08-05 when
planning reoriented from slices to chapters (same unit of work, per atlas
§1).

## Open

### 1. Auto-derive ledge jump directions from RMXP passage bits

Slice-1 analysis (2026-07-13) proved ledge directionality is fully recoverable
from data we already deserialize — the old hand-map-by-eye plan (ex-SLICE1 #4)
is obsolete. Essentials v17 (Uranium's ledge chain is stock, no monkey-patches)
never stores a jump direction: `move_down/left/right/up` run the ordinary
`passable?` check first, and only a *legal* step onto a tag-1 tile becomes a
2-tile `pbJumpToward` in the player's current movement direction. Evidence:
`reference/scripts_dump/023__Game_Player_v17.rb` (move_* → pbLedge),
`101__PField_Field.rb` (pbLedge / pbJumpToward), `025__Game_Map_v17.rb`
(`playerPassable?` — no ledge special-case for the player; NPCs are barred
from tag-1 tiles outright). So the tile's 4-dir passage bits are the whole
story: the sole open entry side IS the jump direction, and 0x0F (fully
impassable) never reaches the jump code = pure wall.

**Derivation rule** (blocked bits: 0x01 down, 0x02 left, 0x04 right, 0x08 up;
entering a tile while moving direction d checks the tile's bit for 10-d):

| sole clear bit | movement allowed | emit |
|---|---|---|
| 0x08 (up) | south | MB_JUMP_SOUTH |
| 0x01 (down) | north | MB_JUMP_NORTH |
| 0x02 (left) | east | MB_JUMP_EAST |
| 0x04 (right) | west | MB_JUMP_WEST |

- 0 clear bits (0x0F) → MB_NORMAL, no warning (intentional blocker).
- ≥2 clear bits → warn + MB_NORMAL fallback (genuinely ambiguous; none in ts22).
- The existing `ledge_directions` hand-override in
  `reference/terrain_tag_map.json` (already wired in `terrain_tags.py`, ships
  empty) stays and wins over the derivation — escape hatch only, per user
  don't grow it.

ts22 inventory (from `output/uranium-build/tilesets.json` passages):
557/565/572 = 0x07 → SOUTH; 558/566/574 = 0x0B → WEST; 559/567/575 = 0x0D →
EAST; 840/841/842 = 0x0E → north-entry-only = the Moki pond-dock front
(Map032 cells 37–39,53), open only toward the water — from land it's a wall,
so MB_NORMAL (the current fallback) and MB_JUMP_NORTH behave identically on
GBA; pick during implementation (MB_NORMAL = least surprise).

**Where:** `tileset_converter/terrain_tags.py` `column_behavior` — derive when
the override table misses; passages come from tilesets.json (already loaded by
`build_slice_tilesets`). Tests in `tests/test_terrain_tags.py`: one per
direction + blocker + ambiguous + override-wins.
**Verify:** Route 01's six warning tiles resolve without hand entries; re-walk
Map032's ~30 south-ledge over-block cells (the SLICE1 #4 residual) — they
should become jumpable in-game. Until this lands, slice-1 builds keep firing 3
benign warnings for 840/841/842.

### 2. Inherited CH02 frontier deferrals (pointers — details live where cited)

- **Route 01 waterfall/transparency animated autotile** — first
  animated+transparent autotile in the frontier; stipple/alpha classify ×
  frame quantization untested (`reference/archive/SLICE1_TODO.md` #10).
- **Secondary-tileset animation support** — animated tiles currently must fit
  the primary block; needs a secondary-callback variant if Route 01 overflows
  (`reference/archive/SLICE1_TODO.md` #10).
- **Moki Town E ↔ Route 03 seam** — moved to `PROJECT_TODO.md` #27, see item 3
  below.

### 3. Moki Town east seam → Route 03 — MOVED OUT 2026-08-05

Moved to `PROJECT_TODO.md` #27: Route 03 is CH09 (Act 2), not CH02, so under
the chapter model the seam is off-frontier (seven chapters past CH02). Full
detail copied verbatim there. Stays prerequisite-chained on item 4 (per-map
tileset packing).

### 4. Promote per-map tileset packing into the slice/assembler path (BLOCKING — must land before Route 01)

From `reference/findings/corpus_scaling_audit_2026-07-14.md` §1/§6 item 1,
2026-08-04. **Blocking finding:** the current slice scheme unions tiles
*per RMXP tileset*, and that scheme is dead the moment Route 01 (Map033)
joins Map032 on ts22 — union = 1607 metatiles / 1611 prequant tiles, over
both GBA 1024 caps. It doesn't fail gradually; it fails on the very next
slice. Per-map packing (already proven on the walker path) fits 171/194
non-empty maps individually and is the documented fallback.

**Code landed 2026-08-05 — build verification still outstanding.** What's in:
- `map_set.py` now owns the scheme: `synth_tileset_id(map_id)` = `1000 +
  map_id` (single source of truth). `phase5.py` dropped its private
  `_synth_id` and imports it, so walker and slice paths share one numbering.
- `scripts/assemble_pathfinder.py` S8a (`run_graphics_pass`) rewrites each
  map's top-level `tileset_id` to its synthetic id (shallow copy — the
  on-disk `MapNNN.json` is never mutated) and passes
  `source_tileset_of=` so `build_slice_tilesets`' group-by-`tileset_id`
  loop yields one physical tileset per map. S8b (`run_layout_pass`) passes
  the matching `tileset_key=` to `convert_layout`.
- Staging hygiene (the audit's "shared-mutable-staging wart"): `run_layout_pass`
  now *returns* this batch's layout entries and `run_fork_pass` takes them via
  `batch_layouts=`. The old code appended the **cumulative**
  `staging/layouts/layouts.json` wholesale, which under per-map synth ids is a
  link-time bomb — a prior run with a different `SLICE_MAP_IDS` leaves entries
  referencing `gTileset_Uranium<synth>` symbols this run never emits.
  `_resolve_batch_layout_entries` now filters the cumulative file down to the
  current map set on the `--skip-layout` path, and fails loud when an entry is
  missing.
- Tests: `tests/test_assemble_pathfinder_tileset_packing.py` (new) +
  `synth_tileset_id` cases in `tests/test_map_set.py`. Full suite green
  (1654 passed / 16 skipped). These cover the **wiring**; they cannot prove
  the tile budget holds.

**Remaining before Route 01:** `SLICE_MAP_IDS` is still the 8-map slice-1 set
(`map_set.py:30`) — Map033 has never been through this path, so the exact
overflow the change exists to prevent is unexercised end-to-end. Add 33 and do
a full assemble+build to close the item.

**Done looks like:** `assemble_pathfinder.py` S8a packs Map032 and Map033
(and any other Route 01 maps) as independent per-map tilesets; a full
assemble+build with both maps in `SLICE_MAP_IDS` passes the 1024 tile/
metatile budget guards without a WALKER_OVERFLOW-style manual exclusion.

## Done

(nothing yet)
