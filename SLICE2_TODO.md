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
  `reference/viewer/walker_checkpoint2_findings.md`).

### 3. Moki Town east seam → Route 03: connections + border-strip import

Migrated from SLICE1_TODO #9, 2026-08-04 (SLICE1_TODO.md retiring). Slice 1
only proved the seam fails *cleanly* (blocked, no walk-into-void); slice 2
must actually convert it — Moki Town↔Route 03 (`[32,E,26, 59,W,0]`) is the
first of 14 `connections.dat` seams and the one directly on the frontier.

Architecture decided in `reference/guides/connections_and_palette_families.md`
(2026-07-14, user-approved by eye) — three parts:

1. **Per-map tileset packing** must land first (see #4 below) — shared
   per-RMXP tilesets are arithmetically impossible for this seam (Map032 ∪
   Map033 on ts22 = 1607 metatiles / 1611 tiles, over both 1024 caps).
2. **Palette families pinned per seam component** — Moki+R03 is one of 8
   `connections.dat` components; quantize both maps' tile union against ONE
   pinned palette set (new SoT artifact `reference/palette_families.gen.json`
   or per-component files) so seam colors match exactly. Consumer:
   `build_slice_tilesets` (`src/rpg2gba/tileset_converter/graphics/build_slice_tilesets.py`)
   quantizes member maps against the pinned set instead of deriving per-pack.
3. **Border-strip import** — emit the neighbor's visible border strip (≤ ~8
   metatiles deep past the seam) into each map's own tileset as extra
   columns, so the engine's native `connections` renderer (porymap
   `map.json` direction/offset/map schema) draws real neighbor art instead of
   VRAM garbage ("tileset bleed"). Exact sampling mechanism (map.json border
   block vs neighbor's real map data) needs a fork read of `fieldmap.c`
   connection handling before coding (§4.7) — not yet done.

**Also open, not yet resolved:** RMXP offset-sign → GBA offset-convention
worked example (Kevlar N offset 11 vs Moki E offset 26) — verify in-ROM at
the boot gate, per the design doc's own open note.

**Done looks like:** Map032 emits a real `connections` entry to Map033 (and
vice versa) in map.json; crossing the seam in mGBA shows continuous art with
no palette snap and no garbage strip; collision at the boundary is sane.

### 4. Promote per-map tileset packing into the slice/assembler path (BLOCKING — must land before Route 01)

From `reference/findings/corpus_scaling_audit_2026-07-14.md` §1/§6 item 1,
2026-08-04. **Blocking finding:** the current slice scheme unions tiles
*per RMXP tileset*, and that scheme is dead the moment Route 01 (Map033)
joins Map032 on ts22 — union = 1607 metatiles / 1611 prequant tiles, over
both GBA 1024 caps. It doesn't fail gradually; it fails on the very next
slice. Per-map packing (already proven on the walker path) fits 171/194
non-empty maps individually and is the documented fallback.

**Verified current state (2026-08-04), still pending promotion:**
- `scripts/assemble_pathfinder.py` (`~line 186`, S8a) calls
  `build_slice_tilesets(maps, WARP_OVERRIDES, fork=fork, ...)` **without**
  `source_tileset_of` — so it uses the default identity mapping, i.e. still
  legacy per-RMXP-tileset union packing.
- `src/rpg2gba/tileset_converter/graphics/build_slice_tilesets.py`
  (`build_slice_tilesets`, ~line 240) already groups maps `by_ts` keyed on
  `map_json["tileset_id"]` (the RMXP id) — confirms the union scheme is
  still live there. The function does accept a `source_tileset_of` param
  ("maps a synthetic per-map tileset id back to its real RMXP tileset id...
  Identity when None — the default, legacy per-RMXP-tileset behavior"), so
  the machinery for per-map synthetic ids exists and is wired for callers
  that pass it — `assemble_pathfinder.py` is not one of them yet.
- `src/rpg2gba/tileset_converter/map_set.py` has no per-map-synthetic-id
  promotion logic visible at the module level beyond `SLICE_MAP_IDS` /
  `WALKER_OVERFLOW_MAP_IDS` — the walker path (`phase5.convert_all`) is the
  only place synthetic per-map ids are actually exercised today.

**Work:** promote per-map synthetic-id packing from the walker-only path
into `assemble_pathfinder.py`'s S8a call (pass `source_tileset_of`, wire the
synthetic ids the same way the walker does), including the warp/tile_map
overlay and staging hygiene (audit calls out "the known shared-mutable-staging
wart"). This gates Route 01 outright — do not attempt Route 01 conversion
before this lands.

**Done looks like:** `assemble_pathfinder.py` S8a packs Map032 and Map033
(and any other Route 01 maps) as independent per-map tilesets; a full
assemble+build with both maps in `SLICE_MAP_IDS` passes the 1024 tile/
metatile budget guards without a WALKER_OVERFLOW-style manual exclusion.

## Done

(nothing yet)
