# CH02 TODO — Route 1 (maps 33, 81)

**RETIRED 2026-08-12 — CH02 passed its §9 boot-walk gate.** Still-open items
migrated to `PROJECT_TODO.md` #32–#36 (#1→#33, #2→#34, #11→#35, #12→#36, plus the
new #32 priority-1 refinement). Kept for the Done ledger and the detail the
migrated entries point back to.

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

- ~~**Route 01 waterfall/transparency animated autotile**~~ — **RESOLVED
  2026-08-05, see item 5.** ts1033 emits 4 effects (12x4f, 39x5f, 72x19f,
  8x95f), 131 animated tiles, 74.1 KiB frame art. The transparent waterfall
  quantized without a stipple/alpha incident; no eye-gate anomaly *yet* — it
  has still never been looked at in motion on hardware (§9 walk owes it).
- **Secondary-tileset animation support** — still open, but NOT a CH02 blocker:
  ts1033's 131 animated tiles sit well inside the 512-tile PRIMARY partition.
  The secondary-callback variant is only forced when ts28's maps enter the
  frontier (543 animated tiles) (`reference/archive/SLICE1_TODO.md` #10).
- **Moki Town E ↔ Route 03 seam** — moved to `PROJECT_TODO.md` #27, see item 3
  below.

### 3. Moki Town east seam → Route 03 — MOVED OUT 2026-08-05

Moved to `PROJECT_TODO.md` #27: Route 03 is CH09 (Act 2), not CH02, so under
the chapter model the seam is off-frontier (seven chapters past CH02). Full
detail copied verbatim there. Stays prerequisite-chained on item 4 (per-map
tileset packing).

### 11. Uranium-original moves silently absent from staged learnsets

`species_converter.stage.emit_learnsets` now gates every level-up move against
the fork's real `MOVE_*` constants and DROPS the entry when the fork has no
such move (loud warning + a `dropped_learnset_moves` record in
`species_manifest.json`). This chapter dropped 3 entries, all `MOVE_METAL_WHIP`
(Uranium move id 562): BAREWL @29, DEAREWL @29, GARAREWL @31. Nothing is
invented and nothing is silent, but those three Pokémon are missing a
level-up move until Uranium's move set is staged into the engine — a much
larger unit than any chapter needs.

### 12. Map033 EV028 "Luz" stripped — revisit if an additive-glow path exists

User-ruled 2026-08-05 (strip, with a reference to revisit). An RMXP ambient
lighting event: one page, trigger 0, empty command list, graphic `light` = a
soft alpha-gradient yellow glow circle. GBA 4bpp has no additive blend and a
smooth gradient bands badly at 15 colours. Recorded in
`reference/strip_list.json`'s `map_events` (with an `expect_name` renumbering
guard); `build_object_events` now honours that list and drops the event before
any graphics lookup, so its sheet needs no `npc_gfx_map.json` entry.

This is the FIRST live entry in `map_events` — the deterministic path never read
that array before (only the retired LLM orchestrator did), so the plumbing
landed with it.

## Done

### 16. Player walked OVER Route 01's tree tops — FIXED 2026-08-12

Boot-walk feedback (`reference/map_feedback/Map033.json`, 4 cells: (63,8),
(15,12), (17,15), (18,19)) — all four are RMXP tile **556**, a small-tree canopy
at priority 1 over a passable grass base. The player drew on top of it.

Not a collision or art bug. `graphics/build_slice_tilesets._render_column`'s
priority tier sent every p==1 column to `LAYER_COVERED` (both tile layers under
sprites). That rule came from `0fd3a2c5` (Map032 boot gate) and fixed the
opposite failure — a flat `p>0 -> LAYER_NORMAL` rule let cliff/hedge-lip tiles
cover the head of a player standing one row south. Both are real: **RMXP p==1 is
row-relative** (draws over a character in its own row, under one a row south) and
the GBA has no row-relative slot, so a metatile must pick one case.

The discriminator is the column's own passability, and Uranium's art is
consistent about it: two-cell-tall trees and hedges put a *passable* p1 canopy
cell over a *solid* p0 body cell (`Map032` (14,17) hedge 1108 p1/pass0 over 1116
p0/pass15; `Map033` (17,15) tree 556 over a blocked trunk). So:

- passable p==1 column → `LAYER_NORMAL` (player walks behind the canopy)
- blocked p==1 column → `LAYER_COVERED` (unchanged; protects the head of the row
  south, which is the only way that art is ever seen)

`layout._cell_blocked`'s rule moved into a new pure `layout.column_blocked(column,
*, passages, priorities, terrain_tags)` (`_cell_blocked` is now a thin wrapper),
so one implementation serves both the collision path and the renderer, and the
decision stays a function of the column key — **no per-cell metatile copies, no
budget change** (`top_min` is 1 in both p1 branches, so the bottom/top art split
is byte-identical; only the layer_type nibble moves). `build_slice_tilesets` grew
a `passages_for` hook beside `priorities_for`/`terrain_tags_for`.

Flips: Map033 10 of 30 max-p1 cells → NORMAL (incl. all four reported), Map032 52
of 105. Suite 2048 passed / 19 skipped. ROM `68ba5268`, EWRAM 86.79% / IWRAM
86.99% / ROM 27.13 MB — unmoved, as predicted. moki 17/17 and route1 29/29 green
first attempt on that build; walk ROM taildropped at the CH01-end seed.

**Known, accepted:** 5 cells in this build are wrong the other way — a passable
p1 cell whose south neighbour is *also* passable (Map033 (11,18)(13,18)(8,36)
(10,36), the big stump's shoulder tiles, + Map032 (14,41)) now occlude the head of
a player standing south. Corpus-wide that case is 6531 of 9554 flips, concentrated
in four crop-field maps → `PROJECT_TODO.md` #32, due before those maps enter a
chapter.

### 10. Phone/rematch trainers don't battle — Map033 EV039, EV053 — DONE 2026-08-10

Was user-ruled accepted debt 2026-08-05; closed instead by writing the
classifier and wiring the native rematch system. Essentials' phone-trainer
idiom buries `pbTrainerBattle(...)` in a code-111 conditional behind a
`pbTrainerIntro` / `Kernel.pbNoticePlayer` preamble, with rematch pages built
on `createPhoneTrainer` / `customTrainerBattle` / `pbPhoneRegisterBattle`.
**Classifier 10** (`conversion_agent/deterministic.py`) collapses it against
the verified real JSON of EV039 (Brandon) / EV053 (Richey): page 0 →
`trainerbattle_single` + `register_matchcall` (`asm/macros/event.inc`), page 1
→ an `IsTrainerReadyForRematch`-gated rematch. Page conditions were verified in
the corpus, not taken from the prose description handed to the classifier's
author — the rematch page keys off self-switch **B**, the idle page off **A**;
the classifier bails fail-loud on any structural deviation.

Engine side is native, no custom C: new assembler pass **S8b5**
(`assemble_pathfinder.run_rematch_pass`, `trainer_converter/rematch.py`) mints
`REMATCH_URANIUM_*` enum members + `gRematchTable` rows and installs them as
gitignored `.gen.h` fragments behind committed sentinel hooks. Rows are gated
against `trainer_manifest.json`, so a row can never name a `TRAINER_*` the fork
won't define, and all fork facts (`MAX_REMATCH_ENTRIES`,
`TRAINER_REGISTERED_FLAGS_START`, the vanilla member list) are read from the
fork at run time per §4.7.

**Two constraints worth carrying forward:**

1. **Capacity is 2, and CH02 consumed all of it.** `capacity =
   min(saveblock_headroom, registered_flag_headroom)` = `min(22, 2)` — the
   binding limit is free `FLAG_REGISTERED_*` numbers past the vanilla block,
   not `MAX_REMATCH_ENTRIES`. The next chapter with a phone trainer needs that
   flag block widened first; the pass fails loud rather than overrunning it.
2. **Generated enum members cannot be `#include`d inside an `enum { … }`.**
   The first build of this work died on every assembly unit with
   `data/mystery_gift.s:104: error: unterminated enum from included file
   include/constants/rematches.h:0`. Cause: `.s` files run through cpp *before*
   `tools/preproc`, and cpp's enter/leave-file line markers (`# 1 "…" 1`) carry
   trailing flags that `AsmFile::ParseLineSkipInEnum`
   (`engine/tools/preproc/asm_file.cpp:789`) cannot parse — it only handles a
   bare `# <n> "<file>"`. The error names the *including* header at line 0, so
   it points nowhere useful. Fix without touching the vendored tool: the
   `#include` moved **above** the enum and defines an object-like macro
   (`URANIUM_REMATCH_MEMBERS`, `rematch.MEMBERS_MACRO`) expanded on a single
   line inside the enum body — a macro expansion emits no line markers. C files
   were never affected (different preproc path), which is why `battle_setup.c`'s
   rows hook needed no change. **Any future generated-enum-member hook must use
   the macro shape.** `parse_rematch_members` skips the macro line so the
   vanilla-baseline index math stays idempotent across re-runs.

Ordering guarantee is unchanged and still load-bearing: members must land above
`REMATCH_WALLY_VR` or `IsRematchForbidden` rejects every id
>= `REMATCH_ELITE_FOUR_ENTRIES` and the rematch silently never fires.
`test_committed_engine_hooks_are_present_and_correctly_placed` pins
include < enum < macro < WALLY.

Shipped in ROM `fe4c75e2` (`output/uranium-build/uranium-ch02-fe4c75e2-phone-rematch.gba`,
taildropped 2026-08-10) — **§9 boot-walk pending**: both trainers should battle
on sight, offer Match Call registration on defeat, and be rematchable.
Suite 1934 passed / 19 skipped; `make modern` clean (EWRAM 86.79%, IWRAM 86.99%,
ROM 27.13/32 MB).

### 9. Trainer pacing lost — 5 of Route 01's 9 trainers stand still — FIXED 2026-08-09

The 2026-08-05 framing was over-broad. Only `MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE`
actually collides with `trainer_sight_or_berry_tree_id`; every *vanilla*
autonomous movement type reads the independent `movementRangeX/movementRangeY`
template fields (`engine/src/event_object_movement.c:1627-1628` range copy vs
`:1631` trainer-range copy), and `GetTrainerApproachDistance`
(`engine/src/trainer_see.c:643-655`) reads the trainer's LIVE
`facingDirection`/`currentCoords` every frame — nothing in the engine assumes a
trainer is static. So a battle trainer can pace *and* see; it just can't run the
bytecode interpreter. Path (b) (engine side table) was not needed.

Two changes. `npc_gfx.movement_spec_for(page, *, allow_custom_route=True)`
threads into `_spec_for_custom_route`; `False` skips the INTERPRETER-FIRST
`encode_route` attempt entirely and falls straight to the native classifiers
(`_spec_for_axis` / `_spec_for_loop_route` / `_look_spec_for`), exactly the path
already taken when `encode_route` returns `None`. Default is unchanged, so no
existing caller moved. `metadata_wiring.build_object_events`' battle-trainer
branch then calls `movement_spec_for(page, allow_custom_route=False)` instead of
going straight to `static_face_spec`, and vets the result against a new
default-deny allow-list (`_TRAINER_MOVEMENT_ALLOWED_EXACT` /
`_TRAINER_MOVEMENT_ALLOWED_PREFIXES`, `_trainer_movement_allowed`).

**The `allow_custom_route=False` skip is the whole fix.** Without it the branch
still demotes: plain cardinal-step and face-direction routes encode cleanly, so
they reach `MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE` — the one denied type — and
never touch the native classifiers at all. A first pass that only added the
allow-list looked green on contrived test pages and changed nothing on the real
data.

`MOVEMENT_TYPE_WANDER_*` is denied for trainers by **policy, not engine limit**
(a random walk can drift a sight trainer into a chokepoint or off its
sightline); the reason string says so. `ObjectEvent.__post_init__`'s collision
guard stays as the last line of defence.

Shipped in ROM `5d4a7622` (Map033): EV030 + EV103 (turn-cycle D,R,U,L) →
`MOVEMENT_TYPE_LOOK_AROUND`; EV035 (4×down, 4×up) →
`MOVEMENT_TYPE_WALK_UP_AND_DOWN` with `movement_range_y=2` (net drift 0, span 4,
`ceil(4/2)`). EV039/EV053 were never on this path — they are #10's phone
trainers, not battle trainers, so they already kept full-fidelity
`URANIUM_CUSTOM_ROUTE` routes. Fidelity accepted as lossy for trainers: waits,
speed/frequency pacing and exact throw distance do not survive the native
approximation. Awaiting its §9 boot-walk.

### 15. Wild encounters never reached the ROM — DONE 2026-08-09

Encounter tables were fully converted since Phase 2 but nothing emitted them
into the engine, so `GetCurrentMapWildMonHeaderId` (`engine/src/wild_encounter.c:379-404`)
found no row and returned `HEADER_NONE` — every grass step a silent no-op.
Grass tiles were never the problem: Map033 already carried **MB_TALL_GRASS on
34 columns / 137 cells** (verified by running the real `terrain_tags.column_behavior`
over the map's live column set; behavior packed at `graphics/emit.py:532-534`).
MB_LONG_GRASS is 0 cells and that is correct — ts22 puts tag 10 on exactly one
tile (860) and Uranium never places it on Route 1.

What landed:

- `tileset_converter/wild_encounters.py` (new) — intermediate → fork-shaped
  entries + `upsert_encounters`. Slot counts are read live from the fork's own
  `fields[].encounter_rates` lengths, never hardcoded; short *and* long lists
  fail loud (no padding — padding a table is a silent lie). Species gate: every
  slot's `SPECIES_*` must be in the known set, else fail loud.
- Fishing needed real reshaping: our intermediate carries three rod lists,
  the fork wants one flat 10-slot array with rod membership declared once in
  the group's `groups` block. Flattened at the fork's declared indices.
- `assemble_pathfinder.py` pass **S8b4** (`:507-597`), `--skip-encounters`,
  after species staging (needs `species_manifest.json`). Named S8b4 because
  S8b3 was already the trainer-pic pass.
- Dead `metadata_wiring.wire_encounters()` retired — it had sat uncalled since
  it was written, which is why the gap survived this long.

**Overlay, not in-place** (user call 2026-08-09): the pass writes a gitignored
`engine/src/data/wild_encounters.gen.json` and `engine/Makefile` picks it via
`URANIUM_WILD_ENCOUNTERS := $(or $(wildcard …gen.json),…json)`, mirroring the
existing `layouts.gen.json` / `map_groups.gen.json` hooks. The fork's generator
tool took an optional `sys.argv[1]` input path to make this possible. Both
engine edits are `URANIUM PATHFINDER SLICE`-fenced; with no overlay on disk the
build is bit-for-bit pristine. The committed `wild_encounters.json` is never
touched — asserted in tests and confirmed by `git status` after a live run.

Shipped: assembler wrote **2 entries** (map 33 Route 1, map 32 Moki Town —
Moki had a table all along and was never wired). `make modern` clean, EWRAM
86.79% / IWRAM 86.99% / ROM 27.13 MB. Generated header carries
`gRoute01_{Land,Water,Fishing}Mons` + both `gWildMonHeaders` rows ahead of the
sentinel. Suite **1880 passed / 19 skipped**. moki chapter green 17/17, walk
ROM `79811361` taildropped — **§9 boot-walk retest pending**.

Two accepted limits, both recorded rather than papered over:

- **Fishing `encounter_rate` = 20, a policy default.** The fork wants a scalar;
  Uranium's rod densities are `0` on all 52 maps because Essentials doesn't
  gate fishing by density, so there is no fact to recover and a faithful 0
  would mean "never bites". 20 is the fork's own modal value.
- **Time-of-day tables dropped.** Map 33 really does have morning/day/night
  land tables (densities 25 each) plus cave 10 and bug-contest 25; they go to
  `uranium_extra` because the plain `land` table exists and wins. Matches the
  atlas's known day/night gap (`00-atlas.md:175`) — see PROJECT_TODO #28.

### 4. Promote per-map tileset packing into the slice/assembler path — DONE 2026-08-05

Code landed 2026-08-05; **budget verified end-to-end the same day** with 33 and
81 in `SLICE_MAP_IDS`. Real emit numbers, per-map tilesets, all under the two
1024 caps:

| tileset | columns | metatiles | GBA tiles | palettes |
|---|---|---|---|---|
| 1032 (Moki Town) | 839 | 845 | 997 | 13 |
| 1033 (Route 01) | 1016 | **1017** | 795 | 13 |

Against the 1607 metatiles / 1611 tiles the old per-RMXP-tileset union produced
for the same two maps. **Map033 clears the metatile cap by 7** — the next map
that shares ts22 art at this density will not fit, so intra-map splitting is a
live corpus concern, not a distant one. S8b wrote all 10 layouts (Route01 =
4187 blocks, Route01OldRodHouse = 300).

### 5. Route 01's trainer battles have no engine-side trainers — DONE 2026-08-05

A real trainer-emission stage now exists; no engine file is hand-edited any
more. What landed:

- `trainer_converter/battles.py` (new) reads the Phase-2 intermediate JSON
  (`intermediate/trainers.json` + `trainer_types.json`) — never Phase 2's
  emitter — and emits a `TRAINER_*` id chain off the pristine fork anchor
  `TRAINER_MAY_PLACEHOLDER` plus a `.party`-DSL fragment for `trainerproc`.
  Class / gender / music / pic all resolve through the LIVE fork headers and
  fail loud rather than inventing a constant (§4.7): Uranium's own minted
  `TRAINER_CLASS_BUGCATCHER` is not the fork's `TRAINER_CLASS_BUG_CATCHER`,
  so the candidate is derived from the display name via the same transform
  `trainerproc`'s `fprint_constant` uses.
- `common.SLICE_TRAINER_BATTLES` pins 12 trainers (Route 1's 9 + Theo's 3
  counter-picks), append-only — fork ids are positional.
- The 3 hand-written `TRAINER_THEO_9/10/11` blocks in
  `engine/include/constants/opponents.h` and `engine/src/data/trainers.party`
  are RETIRED; both files now carry committed, stable `#include` hooks at
  gitignored generated files. Theo comes out of the generator like everyone
  else — and the generated parties are NOT byte-identical to the hand ones:
  they carry Uranium's real IVs (10) and happiness (70) where the hand blocks
  silently took trainerproc's IV-31 default. A deliberate difficulty change.
- **Capacity bump (user-authorized):** `TRAINERS_COUNT_EMERALD` 858 → 1189 and
  `MAX_TRAINERS_COUNT_EMERALD` 864 → 1280, sized for the whole corpus (854
  vanilla + Uranium's 331) rather than per chapter, in a sentinel fence that
  writes down the saveblock consequence — **existing saves do not survive
  this**, and that cost is the same for +9 as for +400, which is why it is
  paid once.
- The fork-index gate learned the manifest's new `kind: "battle"` entries
  (`fork_index.registry_extra_symbols`), and `transpile_driver.transpile_corpus`
  now actually PASSES the trainer manifest to that gate — it never did, which
  is why Map033 kept failing the gate after the trainers were staged.
- Trainer OBJECTS: `metadata_wiring` gained the native trainer-object path
  (`trainer_type` + sight radius). See Open items 9 and 10 for the two
  fidelity limits it carries.

Result: Map033 clears the fork-index gate, 7 of its 9 trainers battle on
sight, and the CH02 ROM builds.

### 6. `WARP_OVERRIDES` has no entries for maps 33 / 81 — DONE 2026-08-05

Entries added to `scripts/assemble_pathfinder.py`: Map033 gets its west-edge
triad back to Moki Town (EV023/024/022 at (70,11)/(70,12)/(70,13)) plus the
old-rod-house door EV027 (39,18); Map081 gets its house exit EV003 (9,14).
Map032's Route-01 triad EV023/036/037 at (8,43)/(8,44)/(8,45) went live in the
same edit — they were deliberately blocked cells while Route 01 was out of
scope, and they are the ONLY way out of Moki Town onto the route.

The hand-maintained duplication itself is NOT resolved — `WARP_OVERRIDES` is
still a copy of what `build_slice_maps` already returns as `src_coords`, and a
missing entry still fails silent (inert door, no error). Killing the duplicate
stays open as `PROJECT_TODO.md` #25.

### 7. Animated-column frame guard blocked Route 01 — FIXED 2026-08-05

S8a died on Map033 with `column ((0, 384), (1, 68), (2, 124)): frame-count lcm
95 exceeds the 64 guard` — ts22's 19-frame `PU-Pond(route1-2)` composited over
the 5-frame `PU-Waterfall(transp)`, 3 such columns in the map (exactly the
"ts22×3" the corpus-scaling audit predicted 2026-07-14 §3).

The lcm is **genuine, not a garbage pairing**: both autotiles animate inside the
same 8x8 quadrants once composited, so no per-tile split avoids it — rendering
the column at 95 frames is the correct answer. Fix, per the audit's own
recommendation (§5 item 5):

- `MAX_COLUMN_FRAMES` 64 → **128** (`graphics/build_slice_tilesets.py:132`).
- New **`MAX_ANIM_ROM_BYTES` = 128 KiB per tileset** (`graphics/emit.py`) — the
  guard that actually binds, since frame count costs ROM (`n_tiles * n_frames *
  32 B`) while VRAM is already bounded by the PRIMARY-partition check. Emits an
  INFO line per tileset with the effect breakdown and KiB.
- Measured: ts1032 = 61 animated tiles / 2 effects / 34.3 KiB; ts1033 = 131
  animated tiles / 4 effects / 74.1 KiB. Both far under the ceiling.
- Tests: guard-failure case re-pinned to lcm 143, plus a new test asserting the
  real pond-over-waterfall column resolves to 95.

**Not verified:** the 95-frame cadence has never been seen running. Engine
`counterMax = 16 * lcm(effect frame counts)`, so ts1033 cycles over
`16 * lcm(4,5,19,95) = 6080` ticks — watch the pond/waterfall in the §9 walk
for a visible period beat or DMA-queue starvation (the 20-entry buffer now
carries 4 effects for this tileset).

### 14. Route 01's diagonal staircases were solid walls — FIXED 2026-08-07

**Symptom** (boot-walk of ROM `9a868d8d`, `reference/map_feedback/Map033.json`):
Map033 cells (57,9)/(57,10)/(57,11) blocked; they render as stairs.

**Root cause — not a collision bug; the cells are solid in RMXP too.** Uranium
builds diagonal staircases from stacked `trigger=1` (player-touch), `through=false`
events: the player bumps the solid tile and the event's script reads the player's
facing and force-moves them one tile diagonally (Through ON → diagonal move →
Through OFF). We never implemented that: the transpiler has no handler for the
code-111 character-facing conditional, so all three events became empty stubs and
queued as unhandled, while `collect_through_block_cells` (correctly, given what it
could see) stamped the cells BLOCKED as invisible obstacles. Net: a wall.

**Fix — native engine feature, no script and no custom C** (user decision; the
alternative was transpiling the facing-conditional into a coord event). The fork
ships sideways stairs: `MB_SIDEWAYS_STAIRS_{LEFT,RIGHT}_SIDE`
(`engine/include/constants/metatile_behaviors.h:78-83`, implemented in
`GetSidewaysStairsCollision`, `engine/src/event_object_movement.c:6681`). On a
passable tile the engine redirects the player's east/west step into a diagonal
step by itself. Mapping, derived from a full census of all **228 stair events
across 28 maps** (total — 9 combos, no leftovers): diagonal axis NW/SE →
`RIGHT_SIDE` (123 events), NE/SW → `LEFT_SIDE` (105). We emit only the two plain
variants; the `_TOP`/`_BOTTOM` variants seal the ends of an Emerald-style diagonal
run, and Uranium seals its runs with real wall tiles instead.

New `tileset_converter/stairs.py` detects the shape and classifies the axis
(fail-loud on a mixed-axis event; the 7 corpus events that look similar but carry
no diagonal move are deliberately excluded and still transpile as before).
`metadata_wiring` excludes stair events from through-blocking and from object-event
emission (local ids unaffected — a skipped event never takes a slot) and exposes
`collect_stair_behavior_cells`. `tile_map`/`layout` generalize the warp override
into a per-kind **behavior override** (`behavior_overrides` overlay section,
`behavior_for_column`, `convert_layout(behavior_overrides=…)`), always emitted
PASSABLE — the engine's redirect never fires on a blocked tile. The transpiler
skips these events with reason `native-sideways-stairs`, counted in the run
summary rather than dropped silently.

**Metatile budget, the one real snag.** Minting a behavior-stamped copy per stair
column pushed tileset 1033 to 1029, past the hard 1024 cap. Two honest savings,
no cap raise: the per-kind transparent fallback is now emitted only when a stair
cell actually sits on an empty/out-of-atlas column, and — the real win — a column
used *only* by stair cells of one kind carries the stairs behavior on its **own**
metatile instead of a copy. All 7 of Map033's stair columns are single-use, so
they cost zero. **ts1033 = 1022/1024.** Note the margin: 2 metatiles. Map033 was
already the tightest tileset in the corpus, and the durable fix is the audit's
pixel-identity collapse / intra-map split (`corpus_scaling_audit_2026-07-14.md`
§7), not more shaving.

Suite 1805 pass / 19 skipped. ROM `42d1a4b4` built clean and taildropped
2026-08-07; **§9 retest pending** — walk the x=57 staircase both ways, and the
second Map033 run at (52,41)/(52,42)/(53,43)/(53,44).

### 13. Three emitter bugs the first CH02 build surfaced — FIXED 2026-08-05

None of these could appear before CH02 widened the staged sets; all three are
converter fixes, not engine edits.

- **Trainer pic C symbols collided with vanilla.** `stage.py` named them
  `gTrainerFrontPic_<PascalIdent>`, which is fine for `RIVAL`/`PLAYER_MALE` and
  fatal for `FISHERMAN`/`YOUNGSTER`/`LASS` — vanilla owns those exact symbols.
  Now namespaced `gTrainerFrontPic_Uranium<Ident>` (and the palette / back-pic
  counterparts), matching the existing `TRAINER_PIC_FRONT_URANIUM_*` /
  `OBJ_EVENT_GFX_URANIUM_*` infix convention.
- **Learnsets emitted moves the fork doesn't define** — see Open item 11 for
  the policy and the 3 dropped entries.
- **Non-ASCII species text emitted `\xE9` escapes.** `escape_c_string` hex-
  escapes every non-ASCII codepoint, which is right for other Phase-2 tables
  and wrong here: pokeemerald's `tools/preproc` re-encodes string literals
  against `charmap.txt` and expects the literal UTF-8 character in source
  (vanilla `species_info/gen_3_families.h` embeds a raw `é`; `charmap.txt:26`
  maps it to byte `1B`). `stage.py` now passes charmap-defined characters
  through raw and fails loud, naming species and codepoint, on one the charmap
  has no entry for. Affected: CUBBUG, DEAREWL, FARTOG — all `é` in "Pokémon".

### 8. `--dry-run` transpile clobbered the corpus queue file — FIXED 2026-08-05

`transpile_driver.transpile_corpus` wrote `transpile_unhandled.jsonl` outside
the `if write:` gate, and a run rewrites that file wholesale from only the maps
it was given. A `--dry-run --maps 81` therefore erased every other map's queue
history, which the chapter census reads to distinguish "transpiles clean" (0)
from "never transpiled" (None) — `tests/test_chapter_atlas.py` caught it. The
write now sits inside the gate with the `.pory` and the registry.
