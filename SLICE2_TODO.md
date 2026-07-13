# Slice 2 TODO — Route 01 frontier (map set TBD)

Working checklist for slice 2, seeded 2026-07-13 before the slice's map set is
finalized (frontier per slice-1 deferrals: Route 01, plus the Moki Town E ↔
Route 03 seam). Same conventions as `SLICE1_TODO.md`: commit updates as items
close; move an item to **Done** with a one-line result rather than deleting
it. Facts here are pointers — the cited code/docs stay authoritative.

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

### 2. Inherited slice-2 frontier deferrals (pointers — details live where cited)

- **Route 01 waterfall/transparency animated autotile** — first
  animated+transparent autotile in the frontier; stipple/alpha classify ×
  frame quantization untested (`SLICE1_TODO.md` #10).
- **Secondary-tileset animation support** — animated tiles currently must fit
  the primary block; needs a secondary-callback variant if Route 01 overflows
  (`SLICE1_TODO.md` #10).
- **Moki Town E ↔ Route 03 seam** — `connections.dat` seams unconverted; slice
  1 only verifies the east edge fails cleanly (`SLICE1_TODO.md` #9;
  `reference/walker_checkpoint2_findings.md`).

## Done

(nothing yet)
