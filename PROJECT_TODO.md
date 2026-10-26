# Project TODO — cross-cutting, cross-chapter loose ends

> **Topic reference, not a status document** (banner added 2026-09-07). This file
> owns the open-item backlog and nothing else. It does **not** state the frontier —
> `MEMORY.md` → Current Phase is the sole authority on what is done and what is
> next (`CLAUDE.md` §7). Items here may be stale about the wider project; the
> cited code and docs stay authoritative.

Working checklist for things that are **not** phase-plan items (→ `ROADMAP.md`)
and **not** scoped to the active chapter (→ the per-chapter doc under
`reference/chapters/`; the old `CH02_TODO.md` pointer here was stale — that file
was archived long ago), but keep getting deferred across sessions and need a
home so they don't get lost. Retired chapter checklists live in
`reference/archive/` (e.g. `reference/archive/SLICE1_TODO.md`). Commit
updates as items close; move to **Done** with a one-line result rather than
deleting. Facts here are pointers — the cited code/docs stay authoritative.

## Open

### 155. Uranium `battle_back` is never read: cave maps battle on the indoor background

Filed 2026-10-26 at CH10's gate (`10-burole-town.md` §7 item 11). Burole Gym (map 66) has
`battle_back: Cave`, but the converter emits it as `MAP_TYPE_INDOOR` with
`MAP_BATTLE_SCENE_NORMAL` (`metadata_wiring.py:710`), and nothing reads `battle_back` past the
PBS parse (`pbs_converter/metadata.py:124`). The engine already does cave natively:
`battle_setup.c:741-746` returns `BATTLE_ENVIRONMENT_CAVE` for `MAP_TYPE_UNDERGROUND` (and a cave
transition at :796). Work: census `battle_back` over all maps, then decide per value whether it
drives `map_type` or a battle-environment hook. Cosmetic; no gameplay effect.

### 154. Tandor region map and Fly: the region map is still Hoenn's

Filed 2026-10-21 with #140. The game's map sections exist now (`map_sections.py`), but their
region-map coordinates are zero, by operator ruling. Uranium has a position for every map
(`map_metadata.json` `map_position` = [region, x, y], e.g. Moki Town [0, 13, 18]). On Emerald's
Hoenn art those positions would point at the wrong places. The work:
- convert Tandor's region-map art;
- fill each section's x/y from `map_position`;
- check Fly, which also needs the heal locations (#96, done).

### 153. Carry the operator's own save across builds (intermission I6) — REVISIT AFTER EACH ACT

Filed 2026-10-21. **Operator decision: get more of the game built first.** At the end of
every act, raise this with the operator and ask whether it is time; record the answer here.
Until then, walk ROMs continue to start from the suite's state.

The goal is to start one real playthrough and keep that save and party on every walk
after it. Research and options: `reference/intermission_a1_a2.md` §1 I6.
- **Already done (2026-10-21, `reference/walk_qol_plan.md`):** within one walk ROM, an
  in-game save continues on the next boot. Walk ROMs also come with every species
  catchable so far, and party-wide EXP Share.
- **The blocker across builds is flag numbering.** `flag_registry.dump_header` numbers
  flags and vars by sorted position, so a later chapter that mints a lower-numbered switch
  shifts every flag above it, and any new self-switch shifts every hide flag. An old save
  then loads but points at the wrong flags. Fixing it (number by Uranium id, or by a
  persisted append-only order) is a flag-registry policy change, so it needs the
  operator's call (`CLAUDE.md` §10). It is also what forces seed blobs to be thrown away
  on every rebuild.
- **The three options from the research:**
  - A: keep one `.sav` across builds. Needs stable ids, a "play" build mode, and a
    save-format version stamped into the ROM.
  - B: transplant the party into each new walk ROM. Needs a `.sav` reader and a seed
    writer; story choices don't carry over.
  - C: migrate the whole save through a per-build id translation table.

  Stable ids make B small and C rarely needed.
- **Related:** #85 (the boot-walk seeding recipe in `BUILD_PLAN.md`), #21 (no
  freshness guard on the ROM under test).

### 151. Map viewer / oracle don't read the streamed tileset format or the windowed grid

Filed 2026-10-18 when I4 closed (operator: backlog it). Streamed tilesets (`reference/streamed_maps.json`:
40, 101, 122) emit `metatiles_wide.bin` and a merge-off tile pool. The viewer and oracle still
render from the stock per-tileset pool (see also the 10-04 viewer note: they pool by real
tileset id, and stitched mode can't show ROM seams). So the viewer is wrong for Nowtoch, and the
ROM is right (`playtest.screen_check` proves VRAM against the ROM data). Do it when the viewer is
next needed on a streamed map.

### 149. Tests tied to the engine's build state break on any rebuild or Walker build

`tests/test_playtest_teach_hm.py` boots `output/playtest-gen/walk/CH07-m035seamN14000_transit.gba`,
whose seed blob is keyed to one ROM build. Any engine rebuild breaks it until
`playtest run --chapter CH07` and `playtest walk --at-beat m035seamN14000_transit` are re-run
(found 2026-10-16, stage 1). Likewise about 50 tests read the engine tree's *generated* state
(flag header, map constants, NPC gfx) and fail whenever `engine/` holds a Map Walker build
instead of the chapter build (2026-10-17). Either skip with a clear reason when the engine state
doesn't match, or document "restore the chapter build before pytest".
*(2026-10-18: hit again by the windowed backup grid (`gBigMap` shifted EWRAM). The test now
boots `CH08-CH07:m035seamN040_transit.gba` (the split-era 14000 ROM is gone with the split),
and its `.sav` is optional because stamped walk ROMs embed the seed. Regenerate with
`playtest walk --chapter CH08 --at-beat CH07:m035seamN040_transit` after the next engine change.)*

### 145. Two Pokédex-reward rungs still queue: MINICORN unstaged, ITEM_OVAL_CHARM missing from `fork_index`

**2026-10-21: NARROWED to Minicorn.** Rung 9 emits now (`giveitem(ITEM_OVAL_CHARM)`; I3 S2
fixed the `fork_index` enum parse). Rung 4 still queues. Staging the Minicorn family
(173 → 174 KIRICORN / 175 OBLIVICORN, Fairy, no Nuclear) is blocked by the species stager
itself: `build_staged_species` accepts one evolution per species, and Minicorn branches by item.
The fix is multi-evolution support in the stager. Do it when a walk can reach 50 owned.

Found 2026-10-15 (CH08 §9). Map050 EV005's reward ladder emits natively except rung 4 (an Egg of
MINICORN: the species isn't staged, so there's no `SPECIES_*`) and rung 9 (`ITEM_OVAL_CHARM`:
defined at `engine/include/constants/items.h:848`, but the enum-segment split in
`conversion_agent/fork_index.py` swallows it because the `RECURSIVELY(...)` line before it has no
comma). Both rungs need ≥50/≥175 species owned, which no walk reaches before a dex-seeded harness
exists, so neither blocks CH08.

### 143. Boxing Gloves don't stand in for Rock Smash on the ROM

Uranium's Rock Smash gate is badge count ≥ 1 AND (a party member knows ROCKSMASH OR
BOXINGGLOVES is in the bag) (`scripts_dump/103__PField_HiddenMoves.rb:385-389`). The engine's
`checkfieldmove` (`engine/src/scrcmd.c:2319`) only checks known moves, with no item fallback.
The story model treats the gloves as granting the capability (CH08 §9 "held" rule), so the
model and the ROM disagree once the gloves are obtainable (Legen Town, Map167 EV28). The fix
is a fenced `RPG2GBA`/`URANIUM` edit in the field-move check. Due in the chapter that grants
the gloves.

### 142. Bambo's `pbPhoneRegisterNPC` is dropped (no NPC phone contact)

**2026-10-21: DEFERRED (operator).** Keep open for when phone calls matter.

Ruled 2026-10-15 (CH08 §9): Map050 EV005 p5's `pbPhoneRegisterNPC(35,"Professor Bamb'o",50)`
emits as a documented no-op, so the player gets no phone contact for him. A faithful port would
add an Emerald Match Call contact (engine data). Revisit alongside #141 if phone fidelity is
taken up.

### 139. `transpile-events run --maps full` dies in `heal_locations.py` (map 8, event 37)

Found 2026-10-14 (CH07 transpiler work): the full-corpus run aborts with `ValueError: staged
call site (map 8, event 37) could not be resolved: trigger 4 is not Action Button (0)` before any
map is emitted; `--maps slice` is unaffected. Consequence: the new `for i in A..B
pbSetSelfSwitch` loop idiom has not been seen on its two other corpus sites, Map066
(`48..53`) and Map193 (`15..32`). They emit the idiom only if their loop closes with an `end`
row; otherwise they stay queued, which is the safe failure. Check both when those chapters
open, or once this is fixed.

### 138. Map032 EV080's "!" spawns Theo's sprite visibly on invisible EV075

Split out of #136 at the CH06 close-out (2026-10-13). In Moki Town, EV080 plays an exclamation
on EV075, an actor with no visible page; our `hidden_actor_bracket` pass `addobject`s EV075 for the
emote with its sheet, so Theo's sprite shows there briefly. #136's skip doesn't apply (the block does
more than turn the actor). Needs a spawn-invisible step (add the object hidden, emote, remove), not
a skip. Visible in built CH01.

*(Corrected 2026-10-15, CH08 open: **postgame only, not live in CH01 or CH08.** "Visible in built
CH01" was inferred from the transpiled text, not seen on hardware. `Map032_EV080_Dispatch`
(`porymap/dispatch/Map032_dispatch.pory:164-172`) runs Page1 only if `FLAG_FINAL_EVENT` (sw125,
postgame) is set, and CH01 dispositions EV080 `unreachable`. The defect is real but first matters
when sw125 becomes reachable. The CH01 scene where EV075 does emote legitimately is EV074, which
removes the object afterwards.)*

### 123. `resolved_trigger_scripts` treats "the beat passed" as "the script ran"

Moved from `reference/archive/REDERIVATION_PLAN.md` §4 at P10 (2026-10-03) so it survives the plan's
archiving. `playtest/chapter.py` `resolved_trigger_scripts` (`a460e823`) marks a
trigger script resolved once its beat passes. That holds for latching shapes, but
not for a TEMP-switch page that re-arms on map re-entry: the walk oracle would
treat a live trigger as spent. Documented, never fixed. **To close:** model
re-arming (TEMP switches reset on map load) or fail loud when a resolved row's
page is TEMP-switch gated and the walk re-enters its map.

### 122. C10 deferred to CH06: offline verdict head, offline checker, ROM sample selection

**2026-10-21:** operator: waits. Not picked up in the A1→A2 intermission.

`reference/archive/REDERIVATION_PLAN.md` §16.3 C10 (rulings R2/R3). Operator ruled 2026-10-03:
defer past the `rederive-ch01-ch04` merge. Only the eligibility flag exists
(`beat_floor/assertion.py` `RowFloor.offline_eligible`, surfaced as the review
docs' `-- offline`/`-- ROM` labels). Not built: an `offline:<archetype>` verdict
head distinct from `beat:`, a checker that evaluates offline-eligible rows
without the emulator (a failure is an error), and ROM sample selection (one per
variant × map × emission shape, resampled on revisit). Deferral is safe for
CH01–CH05 because every generated beat there is walked on the ROM from boot,
which is stronger than C10's offline check plus sample. **To close:** build
before CH06's flavour-NPC count makes walking every row on hardware the
bottleneck. *(2026-10-13, CH06 close-out: not yet -- the whole CH06 run, CH01-CH06 replayed
from boot, takes about 6 minutes. Stays open; build it before a run gets long.)*

### 121. ~~HM field-move gates are still Emerald's per-badge flags, not Uranium's badge counts~~ DONE 2026-10-13

CH04 boot walk (2026-10-03): Flash outside battle was refused with Emerald's
"needs a badge" message. Uranium counts badges (`HIDDENMOVESCOUNTBADGES = true`,
`002__Settings.rb`) with thresholds Flash 0, Rock Smash 1, Cut 3, Strength 4,
Surf 5, Dive 7, Fly 8, Waterfall 8. Emerald gates each on one specific badge
(`engine/src/field_move.c` `IsFieldMoveUnlocked_*`). **Flash fixed** (fenced
`return TRUE`, pinned by `tests/test_field_move_gates.py`); operator ruled
Flash-only for now. **To close:** once the badge→flag mapping is decided
(`essentials_to_emerald_map.md` "Deferred — badges"), gate the rest on a badge
count. Rock Smash currently works only because the boot harness sets
`FLAG_BADGE03_GET` (`new_game.c`); Uranium needs just one badge.

**Done 2026-10-13 (operator: "match the HM gates to Uranium for all HMs"):**
every `IsFieldMoveUnlocked_*` now returns `HasAtLeastBadges(N)` with Uranium's
thresholds (fenced helper in `field_move.c`), and the badge-3 boot rig is gone
from `new_game.c` (the CH06 complete save showed badges 1 and 3). Pinned per
move by `tests/test_field_move_gates.py`.

### 120. Generated suites have no route plan, so their walks go uncompared

ROM run 76 (2026-10-02): generated CH05 failed at Hiker Nunes (map037/ev004)
because the runner graded its walk against `reference/routes/CH05.route.json`,
the HAND suite's approved route -- the gen beat approaches from the south over
the trainer's own event-touch tile, which the hand plan never walks. Operator
ruling: a gen suite loads no route plan (`runner._WalkOracle.for_chapter`), the
same as CH01-CH04 gen already had. The cost is that a gen walk crossing a
foreign trigger tile is no longer caught (CH04's B3 Larrie/Timothy shape).
**To close:** have `beat_gen` record each beat's planned walk tiles (and declared
crossings) in `CHnn.beats.json`, and load a `PlanIndex` from that for
`suite == "gen"`. Note the beat's own target pages must be exempt during its own
walk -- `mark_rows_resolved` only runs after a pass.

### 119. Surf work: re-check converter-dropped vehicle tiles against the native dismount

`metadata_wiring.blank_touch_drop` (`DROP_BLANK_TRIGGER1`) drops every
blank-graphic player-touch event that never transfers, corpus-wide, as inert.
Some aren't inert: Route 1's ev143-147 (Map033 (43..47,11)) run
`if $PokemonGlobal.surfing: pbCancelVehicles`. ROM run 53 (2026-09-30) failed
on them; the operator ruled they become `converter_dropped` rows in beat_gen
(`select.dropped_events`, detail quotes the script), not strip-listed, so they
stay visible. **When Surf (or Dive/bike) is converted:** list every
`converter_dropped` row whose script tests `$PokemonGlobal.surfing`/`diving`/
`bicycle` or calls `pbCancelVehicles`, and check each against Emerald's own
dismount (stepping onto land ends Surf). Route 1's five sit one row *inland*
of the pond's shore row, so native dismount should already cover them -- but
why Uranium placed them there is unverified. Any that isn't covered needs a
real coord event, which needs the transpiler's UNHANDLED `$PokemonGlobal.surfing`
branch handled first.

### 118. `emu.face()` steps the player when they already face that way

Pressing the direction the player already faces is a walk in pokeemerald, not
a turn. ROM run 24 (2026-09-29): `_start_talk` walked to (14,7) arriving facing
up, then `face("up")` stepped the player to (14,6), so A landed on the lab's
machine rather than the tile the beat meant. Harmless when the interaction
target is really in front (it blocks the step), which is the only reason to
face a direction; it only mislabels a failure that already happened.
**Operator call: defer until it actually causes a problem.** Fix when needed:
`face()` skips the press when the facing already matches.

### 116. The lab starter scene is refused, so var 101's `+1` is invisible to the walk

`map050/ev019/p0` (the starter scene, `addvar VAR_QUEST_LOG, 1` at
`engine/data/maps/MokiTownProfessorLab/scripts.inc:1231`) is a computed row: its
`pbTrainerBattle(... pbGet(151)+18 ...)` read of var 151 is unresolved, so the
extractor refuses it (`unparsed_state_write` / `search_unknown_read`) and sets
`havoc_global`. `beat_gen/page_sim` then widens var 101 to TOP for that firing,
and every page gated on `VAR_QUEST_LOG >= 1` between the starter and Theo's house
(`setvar 2`) reads as undecided. The liveness check (`beat_gen/state_arms.py`)
treats undecided conservatively, so nothing is wrongly demoted. But the killer and
enabler ordering around var 101 is approximate until this row extracts. Fix is in
`ruby_subset` / `story_state`: model `pbGet(151)` as a known-range read (the starter
species var) so the rest of the page's writes survive. Operator: deferred
2026-09-29.

### 115. Collapsed warp events still emit a dead Poryscript body

Found 2026-09-18 while inventorying script warps for the warp-facing design
(`reference/archive/WARP_RETAIN_FACING_PROPOSAL.md` §0). When `classify_event`
(`src/rpg2gba/tileset_converter/metadata_wiring.py`) collapses an event into a
native `warp_event`, it drops the `object_event` — but the transpiler still emits
that event's script body into `output/uranium-build/scripts/Map*.pory`, and no
dispatcher references it. Same for events skipped because their destination is
out of slice (e.g. `map037/ev002` → map 40).

**Measured over CH01–CH05's 18 maps:** 52 `warp(...)` call sites in the `.pory`
files, of which only **8** (7 event-pages) are live script warps. The rest are
dead labels shadowing a native warp at the same cell.

Harmless at runtime. The cost is misdirection: grepping `warp(` overstates
script warps roughly 6×, which nearly skewed the 2026-09-18 design discussion.
Fix: skip transpiling (or emit a one-line breadcrumb for) events the classifier
realized natively or skipped.

### 114. 20 maps reference tile ids past their tileset's `passages` array

Found 2026-09-17 while measuring warp arrival geometry: `column_blocked` raises a `KeyError` on
certain cells because the map's tile data names a `tile_id` >= `len(tileset["passages"])`. Any
passability question about those cells is unanswerable, which silently excluded 16 warp transfers
(all on map 97) from that measurement.

**Measured over all 199 decoded maps** (`output/uranium-build/maps/Map*.json` +
`tilesets.json`), counting distinct out-of-range tile ids and affected cells:

| map | tileset | len(passages) | max tile_id | distinct over | cells |
|---|---|---|---|---|---|
| 124 | 11 | 1880 | 3554 | 56 | **916** |
| 97 | 19 | 2072 | 2791 | 20 | 255 |
| 102 | 19 | 2072 | 3515 | 24 | 189 |
| 8 | 28 | 1488 | 5591 | 28 | 67 |
| 140 | 12 | 536 | 3462 | 7 | 68 |
| 104, 113, 126 | 19 | 2072 | 2791 | 20 | 51 each |
| 27 | 12 | 536 | 3105 | 11 | 36 |
| 1, 20 | 12 | 536 | 3462 | 7 | 34 each |
| 94 | 22 | 1184 | 8197 | 9 | 25 |
| 9, 88, 154, 160 | 12 | 536 | 3105 | 11 | 18 each |
| 183 | 25 | 1184 | 2396 | 13 | 13 |
| 29 | 19 | 2072 | 3288 | 9 | 10 |
| 98 | 19 | 2072 | 2829 | 7 | 7 |
| 87 | 27 | 1184 | 5535 | 2 | 2 |

20 maps across **7 tilesets** (12, 19, 28, 27, 22, 11, 25). Tileset 12 accounts for 8 maps and
tileset 19 for 7. The same out-of-range ids recur across maps sharing a tileset (e.g. maps 104,
113, 126 all hit the identical 20 ids), which points at a **tileset-side decode or truncation
defect**, not per-map corruption.

**Why it has not bitten yet:** the narrow 4-neighbour scans the warp code performs never land on
these cells — 0 of the 347 tier-3-eligible warps touch one. It surfaces only on whole-grid scans.
That is luck, not safety: `tile_map.TileMap.passage()` raises on the same condition, so any future
full-map passability pass (a router, a reachability check, a generated blocked-terrain oracle)
will hit it.

**Investigated 2026-09-17 — it is Uranium's own data, not a decode defect.** An independent
RGSSAD extractor + from-scratch Table decoder reproduced `_unpacked/Data` byte-for-byte and our
map JSON cell-for-cell (0 mismatches), and `Tilesets.rxdata` decodes identically. The ids are
stale tile references on ONE layer of a cell, past the bottom of the tileset PNG; RMXP draws that
layer as nothing and the other layers normally. (The player never stands on them — Uranium's own
`passable?` would crash on `nil & bit`.) Across the 18 live maps every affected cell keeps at
least one good layer. Maps 124 and 183 were the outliers — orphaned drafts painted against the
full `Outside.png` sheet — and are now STRIP-listed (`c8088f23`).

**Fixed (`15b31a03`):** tileset build, layout conversion and the map viewer mask the bad layer to
empty per layer (`layout.mask_out_of_atlas`), bound = the tileset PNG's height
(`TileRasterizer.max_static_tile_id`, recorded per synthetic tileset as `atlas_max`). Previously
the build voided the whole column.

**Still open — fix when the first chapter containing one of these maps is built** (no CH01–CH04
map is affected, so today nothing hits it): `traversal/collision.py` `build_tile_grid` (+
`graph.py`, `capabilities.py`) and `tests/test_warp_facing_invariant.py`'s `_blocked` build raw
unmasked grids *(2026-09-18: `metadata_wiring._derive_retain_facing` was the other listed site;
deleted in C5b, and its replacement invariant test inherited the same raw-grid shape)* and feed them to `column_blocked`. They will `KeyError` on ids past `passages`, or
— worse, silently — apply collision from a layer the ROM no longer has where `passages` is longer
than the image (tileset 19 `Indoor(1)`: table 2072, image bound 1824; maps 29, 97, 98, 102, 104,
113, 126). Fix = mask with the recorded `atlas_max` before `column_blocked`. A shared-loader
refactor was tried 2026-09-17 and discarded as premature: with no affected map built it added a
sentinel bound and strict/lenient modes to pass synthetic tests only. Build against a real map.

### 113. `_event_transfers` reads variable-designated warps as literal coordinates

Found 2026-09-17 while verifying the code-201 parameter layout (operator
challenged the reading; the layout held, these two defects did not).

`TRANSFER_CODE`'s own comment names the layout —
`params [method, dest_map, x, y, dir, fade]`
(`src/rpg2gba/tileset_converter/metadata_wiring.py:86`) — but
`_event_transfers` (same file, **line 661**) never reads `method`:

```python
out.append((p[1], p[2], p[3], p[4] if len(p) > 4 else None))
```

RMXP `method` is 0 = direct designation, 1 = **designation by variable**, in
which case `p[1..3]` are *variable ids*, not a map and coordinates.

**Measured over all 199 decoded maps** (`output/uranium-build/maps/Map*.json`):
1085 code-201 commands, all with exactly 6 parameters. `method` is 0 for 1076
and **1 for 9** — all nine on **map 212** (events 3, 4, 5, 7, 8), every one with
parameters `[1, 95, 93, 94, 8, 0]`, i.e. destination map = var 95, x = var 93,
y = var 94.

Today those nine are read as the literal destination "map 95, tile (93, 94)" — a
fabricated target. It also feeds the in-slice membership test at
`metadata_wiring.py:703`, so a bogus target can wrongly classify an event as
out-of-slice and skip it outright. This is a silent default of exactly the kind
§4.5 forbids.

**Latent, not live:** map 212 is in no CH01–CH05 slice. It goes live the moment a
chapter includes it. Fix is either fail loud on `method != 0`, or resolve the
variables through the story-state model (`story_state/`) when they are
statically known.

Re-derive rather than trusting this table: the scan is a plain walk over the
decoded map JSONs counting `code == 201` by `parameters[0]`.

### 112. A collapsed door bakes in page 0's destination and facing

Found 2026-09-17, same scan as #113.

`classify_event` collapses an event into a single `warp_event` when its first
page is player-touch and *every* player-touch page carries a transfer, then takes
**`transfers[0]`** — the first code-201 in page order — for the whole warp
(`src/rpg2gba/tileset_converter/metadata_wiring.py:712-713`). Later pages'
transfers are discarded, including their destinations.

**Measured over all 199 maps:** 25 events have pages that disagree on the
transfer *direction*; **4 of those would collapse** into one `warp_event`:

| map | ev | dirs across pages | taken | distinct destinations |
|---|---|---|---|---|
| 137 | 26 | 6, 8 | 8 | **4** |
| 156 | 4 | 4, 6 | 6 | 1 |
| 156 | 25 | 2, 6 | 6 | **2** |
| 213 | 3 | 0, 6 | 0 | **2** |

**The destination disagreement is the more serious half.** `map137/ev026` has
four distinct destinations across its pages and collapses to the first;
`map156/ev004` is the pure-facing case (one destination, two facings, coin flip).
A door whose target depends on story state is exactly the shape the gated-door
rule (`reference/findings/gated_door_collapse_2026-07-26.md`) exists to protect,
but that rule only fires when a touch page carries *no* transfer — it does not
notice pages that transfer *somewhere else*.

**Latent for CH01–CH05:** none of the four are in those chapters' maps (137, 156,
213). The other 21 disagreeing events stay multi-page objects, where the
dispatcher picks the live page and that page's own `warp()` runs — correct today.
`map049/ev021` is in CH01 but is one of the 21, so it is not affected.

Likely fix: fail loud when a collapsing event's transfers are not unanimous on
(dest, dir), and leave it as a multi-page object instead.

### 111. `_minimal_sets_for_predicate` blows up in full-suite runs, but not in isolation

Found 2026-09-17 closing C5. `pytest` (whole suite) stalled indefinitely at ~19%
on three separate runs, pegging one core with flat RSS — a genuine compute
blowup, not a deadlock and not swap. `SIGABRT` thread dumps put it in
`traversal/reachability.py::_minimal_sets_for_predicate` (line ~199) every time,
but reached from **two different callers** on different runs:

- `chapter_manifest/generator.py:479 _reachability_requires`, under
  `test_chapter_manifest_generator.py::test_map32_no_code_201_warp_to_59_but_seam_row_present`
- `chapter_manifest/checker.py:1110 _check_row_verdict_rules` →
  `approach_model.has_walkable_approach`, under C5's new
  `test_chapter_manifest_floor_rule.py::test_real_corpus_ch01_through_ch05_has_no_floor_missing_findings`

**In isolation both are fast and deterministic** — the floor-rule file runs in
12.5s, and 12.5s ± 0.2 across `PYTHONHASHSEED` 0-4, so set-iteration order is
*not* the trigger (that hypothesis was tested and is wrong). The whole suite also
completed cleanly once, in 159s. So the trigger is full-suite process state, and
the prime suspect is the process-lifetime caches `playtest/cells.py`
(`_MAP_CONST_INDEX`, `_GRAPH_CACHE`) — independently observed the same day to
leak across tests, making
`test_chapter_manifest_cli.py::test_generate_writes_default_path_and_reports_count`
fail when any archetype-template test runs first. A poisoned graph would make the
minimal-set search explore a far larger space.

**Not caused by C5**, but C5 raises exposure: the new real-corpus test drives the
expensive path once per chapter, five times. Workaround until fixed: run the
suite in two halves as separate processes (`ls tests/test_*.py`, split, one
`pytest` invocation each) — 1821 + 2040 tests, ~100s and ~60s, fully green.

Worth bounding the search itself regardless: an exponential subset enumeration
with no cap is a latent hazard at CH06's map count.

### 110. Five of eleven `toggling` flavour NPCs have no page at `page_idx + 1`

Same 2026-09-15 probe. `flavour_npc_beat`'s `toggling` variant registers a second
beat asserting the self-switch actually revealed a different line, and defaults
`toggled_page_idx=page_idx + 1`. For **5 of the 11** toggling instances in
CH01-CH03 that page has no messages in source, so the default is wrong for them
and the template will fail loud at registration telling the author to pass
`toggled_page_idx=`.

That is the designed behaviour, not a defect -- but it means the toggling
instances are **not** mechanically applicable the way the 83 plain ones are, and
whoever does the application pass should budget hand-inspection for those five
rather than discovering them one failed import at a time. Unknown as yet whether
the second page lives at a different index, or whether those five toggle
something that is not a second dialogue page at all.

### 108. Blank-graphic parallel pages are dropped whole, and nothing sets FLAG_STARTING_OVER

*Filed 2026-09-15 out of CH01's 2F stop (`ch01.py`, the comment block above `B3_up`).
Two conversion gaps found on one map; both leave rows no beat can claim.*

**Parallel pages.** `metadata_wiring` sends a blank-graphic trigger-4 event to
`DROP_PARALLEL`, and `compute_autorun_entries` only picks up trigger 3, so the page's body
is never emitted anywhere. The drop is not per-map, it is the rule. In CH01–CH05 it
bites twice, both "set a switch and my self-switch once" pages:
`map048/ev005/p0` (switches 49 JUKEBOX + 51 GAME RUNNING) and `map033/ev004/p0`
(switch 54 RIVAL MASTER). Measured: nothing in Uranium reads 49 or 51 — no page
condition, no conditional branch, no common event, nothing in `Scripts.rxdata` — so
Map048's page is inert either way. Switch 54's readers are unmeasured, and the
corpus-wide count of parallel pages with effects is too. Fix direction: a parallel page
whose body is only state writes and has no wait/loop is semantically a run-once autorun,
so `compute_autorun_entries` could admit it under the same guard logic; anything with
waits or loops stays a loud queue entry.

**Parallel half DONE 2026-09-15 for the run-once shape.** `compute_autorun_entries` now admits a
trigger-4 page whose body is only state writes/comments (`_is_state_write_only`) and that
turns ON a flag appearing as a bare `!flag(...)` conjunct of its own guard. Anything else still
isn't converted, now with a logged warning. Corpus census: 253 parallel pages, 4 of the admitted
shape (Map033 EV004 and Map048 EV005 in the slice, Map059 EV024, Map066 EV021). The other
**248 stay open**: waits, loops, pictures, scripts, all on maps not yet in the slice. They need
per-shape work when their chapters arrive. Switch 54 turned out write-only too. Beats: CH01
`B3_up` claims `map048/ev005/p0`; CH02 `B1` claims `map033/ev004/p0`.

**Starting Over (switch 5).** Only Essentials' `pbStartOver` sets it
(`PField_Field` ll. 1942/1966), on whiteout. The ROM whites out natively, so
`FLAG_STARTING_OVER` is never set and the three heal-on-return autoruns gated on it are
dead: `map048/ev013/p0`, `map049/ev022/p0`, `map068/ev001/p1`. Corpus-wide, **29 pages**
read switch 5 (most Center nurses, the two home HEAL pages, and special maps such as Map156's
`GameOver`), so this is a pattern, not three rows. Where the ROM's native
whiteout actually sends a Uranium player is the real question (CH02's B18 anchors the
initial one). Either set the flag on the native whiteout path, or disposition the three
rows `unreachable:` with this item as the citation.

**Starting Over half: engine side DONE 2026-09-15 (operator approved).** A fenced
`FlagSet(FLAG_STARTING_OVER)` in `DoWhiteOut` (`engine/src/overworld.c`,
`URANIUM PATHFINDER SLICE`; `overworld.o` compiles, full link waits for P11).
`whiteout_beat(starting_over_rows=...)` asserts the flag is set when control returns
and clear once the arrival scripts drain. CH02 B18 claims `map049/ev022/p0`;
CH04 B16 claims `map068/ev001/p1`. `map048/ev013/p0` is hand-dispositioned
`unreachable:`, since it is dead in Uranium too (a home white-out lands on 1F, whose
page clears the switch first). **Still open:** those two rows stay undispositioned
in CH01/CH03, because a beat in a *later* chapter cannot satisfy an earlier chapter's
check. The beat model sees only the chapter and its predecessors, and `boundary`
requires a forward crossing. Needs an operator ruling. Not done either: Uranium's
"scurried home / to a Center" message.

### 99. `_resolve_threshold` cannot fold increment writes, so reachable thresholds read as undetermined

*Filed 2026-09-12 out of `reference/archive/REDERIVATION_PLAN.md` §14.11. Not P8b work — P8b hand-annotates
around it.*

*(2026-10-04: still open. P8b closed 2026-10-03 without it; `_resolve_threshold` in `capability_sites.py` still reads only constant writes and returns undetermined when computed writes exist. CH06's gym (`Map042 ev3/p0`) is one of the incrementing writers, so this bites at CH06.)*

`capability_sites._resolve_threshold` answers a `<variable>_<threshold>` token from **constant**
`code 122` writes only. When no constant write reaches the threshold but the variable also has
computed writes, it returns `None` (undetermined) and refuses to guess. That refusal is correct
and must stay — but it means a threshold that *is* reachable purely by increments looks
identical to one nothing grants.

Worked case: Quest Log (var 101) has four writers corpus-wide — `Map032 ev9/p2` sets 4,
`Map172 ev4/p0` sets 2, and `Map042 ev3/p0` (CH06 gym) and `Map050 ev19/p0` each add 1. So
`quest_log_5` is reachable, but only via increments, so it resolves undetermined and
`map050/ev005/p5`/`p6` need a hand-annotated requirement group instead.

Fix direction: fold op-1 (add) writes into the reachability computation — a variable's maximum
attainable value is the max over constant writes plus the sum of increments that can follow it,
which is derivable from the chapter order the atlas already provides. Keep the refusal for
genuinely computed writes (operand types that are not literal constants).

**Why it matters beyond this row pair:** every Uranium story gate of the form "variable >= N
reached by incrementing" has this shape, so this is the difference between a derived and a
hand-annotated capability across the whole corpus — directly relevant to the cross-game goal,
where hand annotation does not transfer.

### 2. Locate the Nuclear type's 1/8-HP-per-turn out-of-battle effect

Not in `217_Nuclear_Forms_Moves.rb`; likely a field/step hook or
`PokeBattle_Pokemon` patch. Needed before Phase 6 (custom engine work for the
Nuclear type) can start in earnest.

### 3. GBA charmap handling for accented characters

Sidecars are correct UTF-8 (`Pok\xE9mon`); `tileset_converter.assembly.normalize_pory`
owns charmap legality at staging (normalizes or fails loud) and the quantize
pipeline owns glyph rendering — but full correctness for é/♀/♂ across the
whole corpus (not just the slice) is unverified. Phase 5/6 integration
concern.

### 4. TMPBS field semantics

`tmpbs.dat` is confirmed a Uranium-custom extra move list per species, but
whether it's a move-reminder list or a broader compatibility list is still
open. Needed to decide the Phase 2 JSON representation before a full-corpus
PBS re-run.

### 5. Verify pre-seeded `VAR_GYM8_*` / `VAR_TANDOR_CHAMPIONSHIP_*` names

Proposed in Flag Registry Notes (MEMORY.md); may need renaming once the full
flag-registry policy is exercised outside the slice.

### 6. F3 — yesnobox two-step → native `msgbox(text, MSGBOX_YESNO)`

From the 2026-07-07 native-reuse audit (`reference/native_reuse_audit_2026-07-07.md`):
small transpiler fidelity win, not yet built. F1/F2 (the critical ones) are
done; F4 was no-action.

### 7. HEROINE player sprite

Slice boots MALE hardcoded. HEROINE sheets are exact-2× and convert cleanly
with the existing `sprites.convert_player_sheets` path whenever wanted —
mechanical, not blocked on anything.

**2026-10-21:** operator: wait on this; not needed now.

### 8. Player sprites for bike / Surf / surfboard / Dive — convert in the chapter that unlocks each

**Updated 2026-10-23.** Fishing is DONE (`9a88b039`, CH09): `HERO-FISH` → 12
frames of 64×64 with its own palette, swapped in through the
`Rpg2gbaPlayerFishing` alias on `OBJ_EVENT_GFX_BRENDAN_FISHING`. That is the
pattern to copy (`sprites.convert_player_fish_sheet`, the fishing block in
`sprite_emit.py`, the pointers-table fence). Every other mode still shows stock
Brendan. Nothing fails or warns, so this has to be remembered. The chapter
template's §6.1 rule now points here.

| Mode | Uranium sheet | Fits | Engine slot to repoint | Converts in |
|---|---|---|---|---|
| Bike | `HERO-BIKE` (66×72 cells) | 32×32 once halved (~24×28) | `OBJ_EVENT_GFX_BRENDAN_MACH_BIKE` (and `_ACRO_BIKE` if both bikes exist) | the chapter that grants the Bicycle (atlas: "bike" at CH03, Bike Wheel at CH11; confirm at that chapter's open) |
| Surf | `HERO-SURF` (66×72) | ~30×35, a few px over 32 tall | `OBJ_EVENT_GFX_BRENDAN_SURFING` | CH30 (HM03; #125 has the real grant map) |
| Surfboard | `HERO_SURFBOARD` | not measured | not mapped yet | CH38 |
| Dive | `HERO_SCUBAGEAR` | not measured | `OBJ_EVENT_GFX_BRENDAN_UNDERWATER` | CH45 (HM08) |

Known wrinkles:
- **Surf is a model mismatch, not just art.** Uranium draws the player and the
  mount as one sheet; Emerald draws the player sprite plus a separate surf-blob
  field effect. Decide whether to blank the blob or split the sheet. That is a
  fidelity call, so ask the operator.
- **Fishing while surfing:** `fishing.c` passes the player's `y2` to the surf
  blob. The fishing fence zeroes the nudges for the 64×64 frame. Check it by
  eye the first time Surf and a rod are both held.
- **Field-move pose** already reuses the walk art (rock smash fix).
- **HEROINE** sheets are #7 (operator: wait).

### 9. `displayNinjaLetter` card UI

Currently converts as a scrolling msgbox (hand override, Map049 EV021). A
bespoke letter-card scene is a Phase-8 custom-C candidate if the flattened
version reads poorly in-game.

### 10. Full-corpus art walk is sampled only

Checkpoint-2 certification (2026-07-02) covered the 8-map walker batch by
sample, not exhaustively. Follow-up open: a systematic pass over all 199 maps'
converted art once more slices exist to make it worth doing in bulk.

### 11. 88 CommonEvent queue entries

Zero are called by slice 1, so they're out of scope there, but they're real
unconverted transpiler queue residue that blocks any slice that does call a
CE. Will need the CE-context idiom/native/hand triage (same shape as the
slice-1 event triage) once a slice pulls one in.

### 13. Map viewer: launch-stale quantized colors (browser-cache bug) — FIX APPLIED, verify

Root-caused 2026-07-13 (Brandon: flowers wrong colors on server launch, Apply
& re-render fixes them): all `/api/tile|metatile` PNGs are served
`Cache-Control: immutable, max-age=1y` with `?g=<_quant_generation>` as the
only cache-buster, and the generation was a module global reset to 0 on every
process start — including the hot-reload `os.execv` self-restarts — so bytes
the browser cached under a low `g` in an earlier process lifetime re-serve
forever on relaunch. (Packer itself proven deterministic; per-group URL
independence explains the mixed-vintage colors.) **Fix applied** in
`map_viewer_common.py`: `_quant_generation` seeded from the millisecond
clock, so a generation never repeats across lifetimes. Verify on the next
viewer walk (colors correct on first launch, no hard-reload needed), then
move to Done.

### 14. Map viewer + oracle: animated frames missing from quantization census

Found during the #13 trace; identical in both viewer render paths (so it does
NOT explain #13's symptom), but it's a real viewer↔ROM parity gap of exactly
the class the 2026-07-12 pool-scope fix was meant to close. The viewer never
threads animation frames into quantization: the analysis-pool build calls
`_render_column(ck, raster, priorities)` with no `n_frames`
(`map_viewer_common.py:474`), unlike the real pipeline
(`build_slice_tilesets.py:373`/`:396` passes
`n_frames=column_n_frames(...)`), so `MetatileImage.frames` is always `None`
and `emit.py`'s `extra_tile_colors` union stays empty — animated tiles'
frame-1+ colors never widen their assigned palette in the viewer preview,
while the ROM's do. `scripts/verify_viewer_rom_match.py` Mode B has no
frame handling either, so the oracle can't catch this divergence.

**Fix guide:** pass `n_frames=column_n_frames(ck, raster)` in the
`map_viewer_common.py:474` pool build (import `column_n_frames` from
`build_slice_tilesets`); the `:610` pre-quant renders serve the RPG Maker
reference view and shouldn't need frames — verify when building. Teach the
oracle's viewer mode the same, then re-run Mode B on the slice to prove
parity including animated columns.

### 15. Source→emitted dialogue census as a build-time gate

Nothing compares source event text (code-101/401) to emitted script text
(`msgbox` + text blocks). Need a corpus-wide count-and-ratio check that fails
loud past a threshold, modeling code-401 continuation lines merging into one
`msgbox` (not a strict 1:1 demand). Measured baselines from the audit: Map032
EV009 38→37 (complete), Map049 EV021 18→16 (fine, 401 merges), Map050 EV005
102→60 (unexplained, see #19), Map050 EV019 37→18 (the loss that triggered
the whole audit, since fixed). Must also cover hand-conversion files —
`hand_overrides.py:63` splices them in verbatim and skips every existing
coverage mechanism; its `_validate` only checks label-collision namespace
hygiene, not content. Migrated from SLICE1_TODO #28 §5.3 / hand-conversion
audit §5.3, 2026-08-04.

### 16. Close the `legacy_unaudited` escape hatch — still only warns

`load_queue_jsonl` raises on a `hand` queue entry with a blank evidence box,
but only **warns** when `legacy_unaudited: true` — verified still true at
`queue_evidence.py:241`. That flag was meant to mark an audit backlog and
became a permanent exemption; it let an unjustified hand conversion
(Map050 EV019) ship three real defects into the ROM before anyone caught it
(see `reference/findings/hand_conversion_audit_2026-07-31.md`). Fix: make
`legacy_unaudited` raise like a blank evidence box, then audit or retire
every remaining user of the flag (see #19 for the one still outstanding).
Also still undone: document the "hand conversion never amortizes" rule in
CLAUDE.md §4.1 and in a `hand_conversions/` README. Migrated from
SLICE1_TODO #28 §5.4 / hand-conversion audit §5.4, 2026-08-04.

### 17. Model scripted-route collision stalls for cutscene (`applymovement`) routes

RMXP stalls a move route when its destination tile is blocked/occupied and
Uranium leans on that idiom ("walk N tiles, stop when you bump into
someone") — e.g. Map050 EV005 page 0 marches the player `move_up`×10. On
GBA, `route_sim.py` and `MovementType_Rpg2gbaCustomRoute_Callback` only
model this for page-level ambient routes (`move_type == 3`); embedded
cutscene routes compile to vanilla `applymovement`, whose `walk_*` actions
never check collision (`InitNpcForMovement`,
`engine/src/event_object_movement.c:7287-7305`, path verified present).
Consequence: any such scripted route can land a different tile on GBA than
in RMXP, corpus-wide, silently. Extending `route_sim` to cutscene routes
also enables a build-time, no-emulator diff of RMXP-simulated vs
Emerald-simulated actor endpoints — see #26 for the specific instance this
would have caught. Migrated from SLICE1_TODO #28 §5.5 / hand-conversion
audit §5.5 / `reference/findings/lab_starter_scene_positioning_2026-07-27.md`
§6.1, 2026-08-04.

### 18. Emit `MB_COUNTER` for RMXP counter-passage tiles

`tileset_converter/tile_map.py:50-53` masks RMXP passages with `0x0F` and
discards the high bits as "non-collision flags" (path/lines verified
current). The counter bit is `0x80`; nothing emits `MB_COUNTER` anywhere in
the corpus, so counter-reach (talking over a counter to the tile beyond it)
is lost everywhere it appears. The engine supports it natively, zero custom
C: `MetatileBehavior_IsCounter` (`engine/src/metatile_behavior.c:490`,
verified present) is consumed by `GetInteractedObjectEventScript`
(`engine/src/field_control_avatar.c:400-409`, verified present), which looks
one tile beyond a counter for the object event to interact with. Note
collision is not derived from the behavior — a counter metatile must also
carry a non-zero collision bit to actually block. Migrated from
SLICE1_TODO #28 §5.6 / hand-conversion audit §5.6, 2026-08-04.

### 19. Hand-conversion audit backlog — three unresolved items (non-harness)

From `reference/findings/hand_conversion_audit_2026-07-31.md` §6 "Still
open" (harness items excluded — another agent tracks those):

- **Map049 EV020** is the other `legacy_unaudited: true, greps: []` ledger
  entry in `hand_bucket_queue.jsonl`. It has a ledger line but **no file**
  under `src/rpg2gba/conversion_agent/hand_conversions/` (verified absent
  2026-08-04). Never discussed or audited the way EV019 was. Needs the same
  audit treatment, or retirement if it turns out moot (SLICE1_TODO #28 notes
  it may be absent from the 2026-07-24 slice dry-run).
- **Map050 EV005 text ratio is unexplained.** 102 source strings → 60
  emitted. The hand-bucket retirement of EV005 (#23-era work) is otherwise
  justified, but this ratio was never accounted for — multi-page branching
  may explain it, or may not. Strongest existing argument for #15's build
  gate.
- **`pbStarterSelector` cutscene never read.** The EV019 header calls it
  "presentation-only" and substitutes a text box; nobody has opened the
  Uranium source for it. A PC playthrough reported an unconverted cutscene
  at this point in the lab scene. Read it in `RPG2GBA_URANIUM_SRC` and
  confirm or correct the substitution.

Migrated from hand-conversion audit §6, 2026-08-04.

### 21. No freshness guard: ROM under test vs currently staged source

**2026-10-21:** operator: waits. It rides with I6 (#153).

The playtest runner enforces ROM-vs-seed-blob provenance (sha256) but has no
check that the ROM binary is newer than staged source. Has bitten twice: a
2026-07-25 harness run against a 45-minute-stale binary, and 2026-07-30 three
days of runs against a build (`1d1dde30`) the user had already rejected.
Same hazard class as the `.sav` residue bug and `BOOT_WALK_CHECKLIST.md` §8.
Guard: refuse to run if anything under `engine/data` or `engine/src` is
newer than the built ROM. Migrated from SLICE1_TODO #30 / also flagged in
`reference/findings/gated_door_collapse_2026-07-26.md` §6, 2026-08-04.

### 22. Audio — open user decision, ROM currently plays stock Emerald music — REVISIT AFTER EACH ACT

**2026-10-21, operator: deferred; ask again at the end of every act** (like #153).
The re-examination found that file format is the real blocker. 80 of the 84 BGM files are OGG
recordings, and the engine plays only sequences. Converting a track therefore means
re-sequencing it by ear. ROM size only rules out streaming the OGGs, and the engine
has no PCM streaming. The ROM is now about 12 MiB after I3, so a streamed signature subset of
about 10 tracks might fit, but it would need a new C mixer and would sound lo-fi. Options stay:
A, a substitution table (recommended); B, as is; C, hand-sequence a few signature tracks
on top of A.

The transpiler comments out every RMXP audio command; no Uranium BGM/SFX
convert. The ROM currently plays whatever stock Emerald default falls out
of `map.json` (e.g. Littleroot's theme). Architecture already sketched in
`reference/findings/audio_decision_2026-07-14.md`: a fork-index-validated
substitution table `reference/audio_map.json`, wired into `metadata_wiring`
per-map BGM plus transpiler `playbgm`/`playfanfare`/`playse` — real
conversion/streaming was rejected by arithmetic (ROM budget). What's
outstanding is the user's call on the bar: accept stock audio as-is,
silence, or build the ~15-row substitution table (recommended). Not
slice-specific — applies to every future slice until decided. Migrated from
SLICE1_TODO #7, 2026-08-04.

**2026-09-18:** the P8c BGM extractor is deferred to this item (`reference/archive/REDERIVATION_PLAN.md`
§16.3 residue rulings). Every built map header is `MUS_LITTLEROOT`, so the hand BGM beats
are vacuous until this lands; when it does, add the floor extractor (header music =
`audio_map.json`[RMXP BGM]) in the same change. Operator: this item may stay open
indefinitely — nothing in P8c blocks on it.

### 23. Tile-animation follow-ups — untested beyond the slice's 2 effects

Core animation feature is done and user-verified (2026-07-12 build), but
three follow-ups were never checked:

- **Cadence fidelity.** 16 ticks/frame (~267 ms) is vanilla Emerald's water
  cadence, adopted as a first guess and approved by eye. RMXP's actual
  autotile speed in Uranium was never measured against it. Adjustable via
  the `% 16` divisor in `_write_anim_fragment` if a side-by-side ever shows
  a mismatch.
- **Corpus generalization untested.** Slice 1 exercises 2 effects on 1
  tileset; the corpus has 69 multi-frame autotiles (up to 64 frames,
  `seatest.png`). Untested: animated tiles landing in the SECONDARY tileset
  (current code packs into the primary block, fails loud past 512 — fine
  for the slice, needs a secondary-callback variant eventually), many
  effects per tileset (DMA queue caps at 20 entries/frame), and columns
  hitting the 64-frame lcm guard.
- **Waterfall / transparency untested.** ts22 slot 1 (`PU-Waterfall(transp)`,
  5 frames) is unused by the slice's Map032 cells — the first
  animated+transparent autotile arrives with Route 01 (slice 2). Stipple/
  alpha classify interaction with frame quantization is unverified.

Migrated from SLICE1_TODO #10, 2026-08-04.

### 24. PU-POKEBALL content-fidelity sign-off outstanding

`PU-POKEBALL` (the thrown-ball sprite in the capture-tutorial ball-throw
scene, Map032 EV009 P3/EV76) currently reuses the vanilla
`OBJ_EVENT_GFX_POKE_BALL` graphic rather than staging Uranium's own
still-pose sheet. This is a CLAUDE.md §10 content-fidelity substitution
call, not a bug — the scene itself boot-walked and passed 2026-08-02
(ROM `e0f6d30f`). The user's explicit sign-off on the substitution (accept
vanilla ball vs. convert Uranium's sheet) is still outstanding. Migrated
from SLICE1_TODO #23, 2026-08-04.

**2026-10-21: SIGNED OFF.** The operator accepts the stock Poké Ball sprite. Move to Done.

### 26. Lab starter scene: what puts Uranium's own player on (14,7)? — unresolved, plus a fidelity call riding on the answer

`reference/findings/lab_starter_scene_positioning_2026-07-27.md` §4 poses an
open mechanism question, subsequently shown to rest on a retracted
argument (`reference/findings/hand_conversion_audit_2026-07-31.md` §3.3 —
the doc's own Through-ON evidence, read correctly, proves Theo ends at
(14,6), not (14,7); the "Uranium's anchor is (14,7)" claim doesn't survive).
What's left genuinely unresolved even after the retraction: nothing in the
reachable data (map collision, tileset counter bits, nearby events) explains
what mechanism would put Uranium's own player somewhere other than our
computed (14,6) anchor at the machine — the doc ruled out a counter tile
and a proxy event and found Bambo (EV005) vacates the spot, but never
identified a positive mechanism. Separately, and regardless of how the
mechanism question resolves: if a device playthrough of *original* Uranium
shows the same tile relationship, then whichever positioning our current
conversion produces should be a deliberate CLAUDE.md §10 content-fidelity
decision ("does our version look better than the original, and is that
okay") rather than an accident of which bug got fixed first. Needs a PC (or
emulator) playthrough of stock Uranium's lab scene to settle. Migrated from
`reference/findings/lab_starter_scene_positioning_2026-07-27.md` §4,
2026-08-04.

### 27. Moki Town east seam → Route 03: the first remapped E/W seam (CH09) — DONE 2026-10-23

**DONE 2026-10-23:** built and walked with CH09 (gate passed). The in-ROM probe crossed both
directions onto the right cells with 0 flash frames. The #150 E/W residual was a probe false
positive (an off-screen column). Belongs under Done; the plan below is kept as the record.

*Replanned 2026-10-22 at CH09 open. The pre-2026-10 text (per-map packing, pinned palette
families, border-strip import, an unconverted seams feature) is superseded: CH04/CH06 and I4
built that machinery (`connections.py`, `connection_remap.py` design R, the seam swap), and it is
live on 31<->35 (shared tileset) and 40<->35 (remapped). History: `git log -S "### 27." --
PROJECT_TODO.md`.*

**Measured 2026-10-22** (`output/scratch/ch09_seam_budget.py`, `ch09_seam_align.py`):
- **Gating.** The row `[32,E,26,59,W,0]` goes live as soon as 59 is in `SLICE_MAP_IDS`
  (`map_set.py:31`); `connections.emitted_rows` only drops rows with a map outside the set. No
  other switch. The same rows feed `tileset_groups` and `load_slice_remap_directions`.
- **Kind.** 32 (ts22) and 59 (ts24) are a two-map component on different tilesets, so a
  remapped seam: `RemapDirection(32→59, right, +26)` and `(59→32, left, −26)`.
- **Fit.** 59 alone 745 metatiles / 673 tiles; 59 plus Moki's W strip (depth 7) 749 / 680;
  32 plus Route 3's E strip (depth 8) 724 / 697. All under 1024/1024, 13 palettes. **Route 3 is
  not streamed.**
- **Offset.** Route 3 y = Moki y − 26 (Moki E rows 26–63 meet Route 3 rows 0–37); 31 of 32
  walkable Moki edge rows meet walkable Route 3 rows. The same convention picks the live
  offsets on 31<->35 and 40<->35.
- **Oversize.** 59's backup grid is 145×80 = 11600 > 10240, so it loads through the windowed
  grid (#148): 2 source rectangles (layout + W connection), limit 8.

**Plan:**
1. Add 59, 1, 54 to `SLICE_MAP_IDS`. The seam, both remap tables and the strip imports follow
   with no new code expected.
2. Build the chain (transpile → stage → assemble → `make modern`) and `build_report` (ROM size,
   EWRAM).
3. In-ROM checks, each a probe with numbers, not a look:
   a. `playtest.screen_check` on 59 and on 32's E edge, VRAM vs layout. This is the first
      oversized map with a **remapped** connection; the Walker run behind #148 had no seam.
   b. #150's E/W residual: adapt `seam_rows_probe.py` to columns/HOFS and cross both ways. If
      the west side shows a border-block column mid-step, decide then (engine copy of an 8th
      west column vs accept).
   c. Seam swap on a stock↔stock crossing: scanlines used (40↔35 measured 21 of 67).
   d. Collision: cross on a few aligned rows both ways.
4. Earlier suites: the `map032/seam/E/map059` row is `later` in CH01 and `later: CH09` in
   CH08. Regenerate the CH01/CH08 manifests and suites after the seam is live; operator
   approves the deltas (§9). CH09's own suite claims the crossing (arriving chapter owns it).

**Not needed any more:** per-map packing (done), a pinned palette-family SoT (seam colours
come from each map's own quantize; judged by eye on 40↔35, judge again on the walk), the
streaming opt-in, and the fork read of `fieldmap.c` (done in CH04).

**Done looks like:** CH09's gen suite crosses Moki E ↔ Route 3 W both ways green from boot;
the probes in step 3 report 0 mismatches / no empty band / swap inside VBlank; the operator's
walk shows continuous art across the seam.

### 28. Time-of-day encounter tables are dropped corpus-wide (Cave half RESOLVED 2026-09-02)

*(2026-10-04: the day/night flags themselves are #126.)*

The encounter emitter (`tileset_converter/wild_encounters.py`, landed 2026-08-09,
CH02_TODO #15) fills the fork's four native fields and drops everything else
into `uranium_extra`, unemitted. Uranium's 13 `EncounterType` slots include
four the fork has no host for at all (Cave, HeadbuttLow/High, BugContest) and
three that it *does* support but we don't wire: LandMorning / LandDay /
LandNight.

The time-of-day three are the tractable half. The fork already supports them —
`OW_TIME_OF_DAY_ENCOUNTERS` (`engine/include/config/overworld.h:95`, currently
FALSE) plus time-suffixed `base_label`s, with `OW_TIME_OF_DAY_FALLBACK`
(`:97`) and `OW_TIME_OF_DAY_DISABLE_FALLBACK` (`:96`) governing what happens
when a slot is empty. Today every map emits only the `TIME_MORNING` fallback
slot, which is also what vanilla does, so nothing is *broken* — it's fidelity
loss, silent unless you know to look.

Not frontier-urgent but not free either: `_LAND_SOURCES`
(`pbs_converter/encounters.py:57`) already prefers a plain `land` table when
one exists, so a map with BOTH plain and time-split tables (Route 1 is one —
densities `[25,10,10,0,0,0,0,0,0,25,25,25,25]`) silently uses the plain one and
the variants never surface. Turning the config on without auditing that
precedence would change behavior on maps nobody has walked.

**Care about it when:** a chapter's spec calls out a mon that only appears at
one time of day, or a cave chapter lands (Cave has no fork host at all and is
currently folded into `land_mons` as a fallback source).

**Done looks like:** a decision on whether Uranium's time-split tables are
worth `OW_TIME_OF_DAY_ENCOUNTERS = TRUE` corpus-wide; if yes, emitter support
for suffixed base_labels + a documented precedence rule between plain and
split tables. Also cross-referenced by `00-atlas.md:175`.

#### RESOLVED 2026-09-02 — the Cave half is closed; only the time-of-day half remains

Investigated when CH05 (Passage Cave) made this item's own "care about it when: a
cave chapter lands" trigger fire. Both sides were checked — what the engine does
with cave encounters, and whether Uranium's data actually loses anything.

**Engine side: there is no cave encounter concept to lose fidelity against.**
`struct WildEncounterTypes` (`engine/include/wild_encounter.h:29-36`) has exactly
five pools — land, water, rock smash, fishing, and the DexNav hidden pool. There is
no `cave_mons` field and no `WILD_AREA_CAVE` in `enum WildPokemonArea` (`:9-15`).
Encounter rolls are triggered purely by metatile behavior
(`MetatileBehavior_IsLandWildEncounter`); `StandardWildEncounter`
(`engine/src/wild_encounter.c:648`) branches on area type only and never inspects
`gMapHeader.mapType` or `.cave`. The slot pickers `ChooseWildMonIndex_Land` (`:185`)
and friends take no map-type argument at all. `WildEncounterCheck` (`:590-620`) is
the sole place `encounterRate` is modified — bike, Flute, Cleanse Tag, Lure, and
player-mon abilities — with **no cave or map-type term**. All 11 `gMapHeader.cave` /
`MAP_TYPE_UNDERGROUND` use sites in the engine are lighting/Flash
(`fldeff_flash.c:45-60,83`, `overworld.c:1108`), object shadows
(`overworld.c:1734`), battle backdrop and transition (`battle_setup.c:741,796`),
Dusk Ball catch rate (`battle_script_commands.c:10674`), DexNav cosmetics
(`dexnav.c:636,708,1115`), and the region map (`region_map.c:1253`). None touches
table or rate selection. **In Emerald a cave is a land tile with the lights off.**

**Data side: the fold is lossless across the whole corpus, not just CH05.**
`Data/encounters.dat` has 52 map entries. **23 carry a `Cave` slot** — maps 7, 8,
17, 36, 37, 71, 74, 80, 83, 96, 106, 123, 150, 184, 189, 190, 191, 192, 193, 202,
209, 214, 216. Of those 23, **zero** also carry a populated `Land`-family table
(`Land` / `LandMorning` / `LandDay` / `LandNight`). On every Cave map, `Cave` is the
sole land-type table with real slot data, so the `_LAND_SOURCES` precedence at
`pbs_converter/encounters.py:123` never actually has to choose. Watch out for the
false positive: several Cave maps carry a nonzero `Land` *density* value with a
null slot list — a leftover default field, not a table. Checking densities alone
makes these look like conflicts.

Maps 036 and 037 (Passage Cave 1F/2F) have byte-identical Cave tables — Tonemy,
Barewl, Grozard, Dunsparce, all Lv 4-6 across twelve slots, densities 15 and 20 —
and nothing else populated on either map.

**Correction to this item's original framing:** the drop is *not* silent.
`tileset_converter/wild_encounters.py:259-264` logs it at info level per map, naming
the dropped tables. It logs at Phase 5 emission rather than Phase 2 conversion,
which is why it reads as invisible from where you would naturally look.

**Conclusion:** folding `Cave` into `land_mons` is correct behavior, not a
compromise, and needs no code change now or later. HeadbuttLow/High and BugContest
remain genuinely hostless, but they are not encounter-table fidelity in the same
sense and no chapter has needed them yet.

**Still open — the time-of-day half, which is the real item.** `OW_TIME_OF_DAY_ENCOUNTERS`
(`engine/include/config/overworld.h:95`, FALSE) is one flag away from working: the
schema field `WildPokemonHeader.encounterTypes[TIMES_OF_DAY_COUNT]`
(`include/wild_encounter.h:39-43`) exists, and every selection function already calls
`GetTimeOfDayForEncounters` (`wild_encounter.c:410-444`) before indexing
`gWildMonHeaders`. The blocker is unchanged and is on our side, not the engine's:
`_LAND_SOURCES` (`pbs_converter/encounters.py:57`) ranks plain `Land` ahead of the
time-split tables, so a map carrying both silently uses the plain one. Flipping the
flag without auditing that precedence changes behavior on maps nobody has walked.

### 30. `text_validator` never scans generated C data headers

`extraction.py:95` `_CORPUS_GLOBS` covers only `scripts/*.pory`,
`staging/scripts/*.pory` and `porymap/dispatch/*.pory`. Generated data headers
— `species/rpg2gba_species_info.h`, `src/data/items.h`, `src/data/moves_info.h`
— are never read, so the whole `.description` overlong/unwrapped class went
undetected until it was seen on a device (2026-08-11 boot walk). The module
already owns the right primitive (`measure_line_width_px`) and a line-width
rule; only the corpus is too narrow.

Note the rule needs a per-field budget to be useful here, not the single
`MSGBOX_WIDTH_PX`: a Pokédex entry is 224px × 4 lines (see
`DEX_DESCRIPTION_WIDTH_PX`), a bag item description is a much narrower window,
and dialogue is the message box. Wrapping itself is solved for staged species
(`wrap_to_width`); this item is about *detection* across every emitter, so an
unwired header can't ship broken the day it gets hooked up.

**Done looks like:** the validator reads generated headers with a field →
budget table, and a deliberately overlong description in any emitter fails the
suite rather than reaching a ROM.

### 32. Priority-1 layer rule needs a south-neighbour refinement before the crop-field maps

**Shipped 2026-08-12 (CH02 tree-tops fix, see CH02_TODO #16): a p==1 column now
gets `LAYER_NORMAL` when the column is passable, `LAYER_COVERED` when blocked.**
That honours the stand-on half of RMXP's row-relative p==1 (walk behind the tree
canopy) and keeps the stand-south half (head not covered by a cliff/hedge lip)
wherever the art is solid. It is a pure function of the column key, so metatile
budgets are untouched.

**Where it is knowingly wrong:** a *passable* p==1 cell whose SOUTH neighbour is
also passable. The player can stand south of it, and their head is then occluded
by art RMXP would have drawn under them. Corpus census (all 199 maps,
`layout.column_blocked` rule):

```
flipped to LAYER_NORMAL   9554 cells over 142 maps
of which south-passable   6531 (68.4%)
Map187 1961 · Map117 1868 · Map163 1366 · Map121 815 · Map028 273 · rest <60 each
worst tiles: ts30/ts50 463 + 471 = 11 902 of the 6531 cells' p1 tiles
```

Tiles 463/471 are **tall wheat/crop field** art — big walkable fields where every
cell is passable, so the south neighbour always is too, and the art is full-tile
height. Under the shipped rule the player's head is buried in wheat on every step
through those four maps. In CH01+CH02 the same defect touches only 5 cells (the
Map033 stump shoulders + one Map032 bush) and was accepted for the CH02 gate.

**The refinement** is "flip only if the south neighbour is blocked" — exact RMXP
for every reachable state. That is *cell* context, not column context, so a column
used both ways in one map needs a per-cell metatile copy. Budget matters: ts1033
ships with 2 spare metatiles. Do the copy-cost census before committing to it.

**Due:** before Map117 / Map187 / Map163 / Map121 / Map028 enter a chapter (all
Act 2+). Not urgent for the current frontier.

### 34. Secondary-tileset animation support

*Migrated from `CH02_TODO.md` #2 on the CH02 gate pass 2026-08-12.*

Still open, still not blocking: animated tiles currently must fit the 512-tile
PRIMARY partition. ts1033 (Route 01) sits well inside it at 131 animated tiles.
The secondary-callback variant is only forced when ts28's maps reach the
frontier (543 animated tiles). Detail: `reference/archive/SLICE1_TODO.md` #10.

Related, and owed to a §9 walk rather than a code change: Route 01's transparent
waterfall autotile quantized cleanly and has passed a still-frame eye gate, but
has **never been looked at in motion on hardware**.

### 35. Uranium-original moves silently absent from staged learnsets

**2026-10-21: NARROWED.** All that is left is the 14 blocked moves (12 Nuclear-type moves, Thunderstorm, Sticky Terrain). Everything else is generated by `battle_converter`.

*Migrated from `CH02_TODO.md` #11 on the CH02 gate pass 2026-08-12; user-ruled
accepted debt, not a defect.*

`species_converter.stage.emit_learnsets` gates every level-up move against the
fork's real `MOVE_*` constants and DROPS the entry when the fork has no such
move (loud warning + a `dropped_learnset_moves` record in
`species_manifest.json`). CH02 dropped 3 entries, all `MOVE_METAL_WHIP` (Uranium
move id 562): BAREWL @29, DEAREWL @29, GARAREWL @31. Nothing invented, nothing
silent — those three Pokémon are simply missing a level-up move until Uranium's
move set is staged into the engine, a much larger unit than any chapter needs.

**2026-10-19: resolved by I3 S3 on `intermission-engine-layers`, apart from the
blocked moves** (`reference/engine_layers_i3_i5.md` §8, `reference/battle_rulings.json`).
- `battle_converter` generates 17 of Uranium's 32 own moves, Smoke Screen as an
  alias of Smokescreen, all 19 of its abilities (13 with behaviour), and the
  game's TM/HM list (stock's stopped at TM50, so TM51-TM100 taught nothing).
- The CH02 drops are gone: the staged learnsets now drop nothing. Flame Impact
  is the real move again (it was substituted with Fire Fang), and Lazy no longer
  stands in as Truant.
- **Still open:** the 14 blocked moves (12 Nuclear-type, Thunderstorm, Sticky
  Terrain) drop loudly from any learnset that names them; a trainer party naming
  one fails staging.

### 36. Map033 EV028 "Luz" stripped — revisit if an additive-glow path exists

*Migrated from `CH02_TODO.md` #12 on the CH02 gate pass 2026-08-12; user-ruled
strip 2026-08-05, recorded here so the reference survives.*

An RMXP ambient-lighting event: one page, trigger 0, empty command list, graphic
`light` = a soft alpha-gradient yellow glow circle. GBA 4bpp has no additive
blend and a smooth gradient bands badly at 15 colours. Recorded in
`reference/strip_list.json`'s `map_events` (with an `expect_name` renumbering
guard); `build_object_events` honours that list and drops the event before any
graphics lookup, so its sheet needs no `npc_gfx_map.json` entry. This is the
first live entry in `map_events` — the deterministic path never read that array
before (only the retired LLM orchestrator did), so the plumbing landed with it.

### 37. No sweep for engine map dirs orphaned by a past rename

*Found 2026-08-12 during the CH03 build; the drift half is fixed, the debris half
is not — see `CH03_TODO.md` #7/#14.*

`MapConstantRegistry.mint()` now re-mints on identity drift, so a
`map_name_overrides.json` edit is no longer silently ignored. Nothing, however,
cleans up what a rename leaves behind: `engine/data/maps/<OldName>/` and
`engine/data/layouts/<OldName>/` survive with a `map.json` naming a layout
constant that no longer exists.

That is **fatal, not cosmetic**. `mapjson` refuses such a dir ("Failed to find
matching layout for LAYOUT_X"), therefore never writes its `connections.inc`, and
make then dies with `No rule to make target
'data/maps/<OldName>/connections.inc'` — an error naming neither the rename nor
the stale directory. Two orphans (`MokiTownTheo`, `MokiTownTheo172`, from maps
172/89's rename to `MokiTownTheosHouse1F/2F`) had been sitting in the tree
undetected until a full mapjson pass finally touched them.

Wanted: the assembler compares engine map dirs against the layout manifest it
just generated and fails loud (or cleans) on any whose layout constant is
absent. Cheap — a scratch version of exactly this check found both orphans in
one pass, and confirmed there are no others today.

### 38. Common-event calls had never assembled (fixed) — but nothing gates the syntax

*Fixed 2026-08-12 (`CH03_TODO.md` #12); logged here because the class of bug is
corpus-wide, not CH03-specific.*

The transpiler emitted `call CommonEvent_004`. Poryscript has a bare `goto Label`
keyword but no bare `call Label`, so that parsed as two bare commands and
assembled into `call` (no operand) plus a stray `CommonEvent_004` instruction.
Every common-event call the pipeline has ever emitted was broken; it went
unnoticed only because CH01/CH02 call no common events, and map68 is the first
map that does.

The fix is one character class at two emit sites. What is still missing is a
**gate**: the fork-capability index validates specials/macros/constants the
pipeline emits, but nothing validates that emitted *Poryscript* is syntactically
what we think it is — a command that silently degrades into two bare commands
passes every check we have until the assembler chokes 20 minutes into a build.
Worth a cheap post-transpile lint over emitted `.pory` (known command names,
parenthesised argument forms).

### 47. `kevlar.py` B25 asserts the Kevlar↔Route 2 seam is BLOCKED — now stale

Migrated from `CH04_TODO.md` on the CH04 §9 gate pass (2026-08-27).
`src/rpg2gba/playtest/chapters/kevlar.py` B25 was written when Route 2 had no
entrance; `connections.py` landed in CH04 and the seam now crosses live (CH04
B1 walks it). B25 still passes only because it asserts the *south row 56*
collision run, not the seam itself — confirm that reading, then flip the beat
to assert a working crossing. It is CH03's file, so this is a deliberate
cross-chapter edit, not drift.

### 48. CH04 residual harness gaps — B10 and B15

Migrated from `CH04_TODO.md`. `route2.py` registers 13 of 15 beats.
- **B10** (Larrie's rematch *offer*) needs a PokeNav/Match-Call driver and a
  self-switch setter the emulator harness does not have; recorded in
  `DEFERRED_BEATS`, not dropped. Same driver would unblock the wider
  match-call rematch surface.
- **B15's two grass cells** are inferred coordinates, not decoded from the map;
  flagged in `route2.py`'s docstring. Settle on the next Route 2 build.
  (B1's Kevlar-side approach column was decoded to x=31 during the 2026-08-26
  run — that half is closed.)

### 49. Playtest checker: capability model (Q3) and rule-set versioning (Q7) still absent

Migrated from `CH04_TODO.md` "Carried, not blocking".
- **Q3 capability model** is unbuilt, so `checker.py` rule 7
  (`deferred_no_granting_chapter`) cannot enforce CH04's 5 `rock_smash`
  deferrals — they pass on a `capability_model_unenforced` warning. Operator
  decision 2026-08-22: accept warnings for now. CH06 is the grant chapter per
  `reference/chapters.json`; enforcement matters most once CH06/CH07 land.
- **Q7 rule-set versioning** is designed but absent from `checker.py` — no
  rule-set version field, so no gate stamp records one and no lag report can
  be generated. (`reference/playtest_rule_versions.json`, added 2026-08-27,
  versions the *playtest harness* beats, not the manifest checker.)

### 52. Route 2 Poké Radar catch-table entries missing from `wild_encounters.json`

Migrated from `CH04_TODO.md` (`reference/chapters/04-route-2.md` §5, item 3).
The Route 2 wiki page lists a Poké Radar division (Dunsparce, Tofurang) that is
absent from `wild_encounters.json`. Data gap, unresolved — Poké Radar is not an
engine feature the pipeline models yet, so this is a "when Radar lands" note,
not a CH04 miss.

### 57. 12 unmodelled walked legs still owed a per-chapter re-check

*Filed 2026-08-29 out of the corpus-wide world-graph audit
(`src/rpg2gba/traversal/world.py`, `python -m rpg2gba.traversal world`) that
closed Q13 slice 1 (`reference/archive/PLAYTEST_AUTHORING_IMPROVEMENT_V2.md`) — 199 maps, 1108
edges (1076 warp, 28 connection, 4 seam_warp) against the 14 overland rows
`connections.json` was originally authored with. The audit walks each
chapter's predecessor chain (shortest path, predecessor `outdoor` map →
chapter `outdoor` map) and reports transit maps belonging to neither chapter.
It found 14 unmodelled legs; CH07→CH08 is fixed today (new chapter `CH07A`
"Route 1 (revisit)" in `reference/chapters.json`). The remaining 12 all cross
maps some *earlier* chapter already covers — e.g. CH25→CH26 crosses Rochfale
Town (12) and Route 6 (22); CH37→CH38 and CH38→CH39 cross Route 07 (8),
Route 08 (117) and Route 11 (140); CH58→CH59 crosses 10 maps including both
Burole and Bealbeach metro pairs. Whether any of them strand content depends
on whether the leg newly unblocks rows dispositioned `blocked:` there, which
needs per-chapter dispositions — `reference/manifests/` only covers CH04
today (§43a). So the re-check is owed once a chapter acquires a manifest, not
now, and it's mechanical: re-run the audit, and for each transit map ask
whether the capabilities held at that leg unblock any `blocked:` row on it.
The audit script lives only in a scratchpad today; promote it into
`src/rpg2gba/chapter_atlas/` as a real subcommand (e.g. `chapter_atlas legs`)
so it's re-runnable rather than re-derived each time.

### 59. Map 999 sits outside the coverage identity entirely

Filed 2026-08-29, same world-graph audit as §57.
`output/uranium-build/maps/Map999.json` exists but has no `map_infos.json`
entry, so it's invisible to the "187 bound + 11 unbound = 198" coverage
assertion and has no graph edges. Decide whether it's a decoder artifact, an
editor leftover, or real content, then either give it an `unbound_maps` entry
or stop emitting it.

### 60. Four `unbound_maps` entries have live edges into the playable graph

Filed 2026-08-29, same world-graph audit as §57. 51 (Intro) → 48, 57; 57
(Nuclear Plant) → 48; 94 (Mapa intro) → 14, 95; 95 (Intro 2) → 14. "Declared
unbound" and "disconnected from the playable graph" are currently the same
claim in `unbound_maps`, but these four show they aren't. The bindings are
probably still correct (pre-title/cutscene maps), but the reason strings
should say so explicitly, and `chapter_atlas coverage` could assert the
distinction instead of leaving it implicit.

### 61. Kevlar Town (31) + Passage Cave (19): 10 deferrals held past CH25, one mis-triaged

Filed 2026-08-29, same world-graph audit as §57. No leg in the 59-chapter
chain re-crosses Kevlar Town at or after CH25 — it's Fly-only from there. Its
10 deferrals are Strength ×7 (HM04, granted at CH25 Route 11), Bike Wheel ×1
(CH11), a post-Gym-5 story flag ×1, and B26, whose dev-only flag `sw130` /
`FLAG_FILE_RECOVERY` is never set anywhere in the corpus — a mis-disposition
owed a re-triage from `deferred` to `unreachable`. Operator decision
2026-08-29: record this as a countable hold and settle it when CH25 actually
reaches the frontier, rather than minting a revisit chapter now. B26's
re-triage is the one piece actionable immediately, independent of CH25.

*(Corrected 2026-10-15, CH08 open, reconciled against the manifests. The breakdown above mixes
events with rows and double-counts. The real hold is in CH03, which owns both Kevlar (31/67/68/73)
and map 19 (the cave behind Kevlar's boulders; CH05's Passage Cave is maps 36/37, whose 4 holds are
`blocked:surf`):*
- *10 `blocked:strength` rows over **7 events** (`CH03.dispositions.json`): map031 ev001/ev037
  (boulders, N7); map019 ev001/002/003 p0, ev005 p0-p2, ev006 p0-p1.*
- *"Post-Gym-5" is the sw94 branch inside map019 ev006, already counted as Strength, not a
  separate hold.*
- *Bike Wheel → Bicycle (map073 ev001 p0/b0) is real, but is a derived `unreachable` row
  (`CH03.derived.json`), not a disposition; source item at CH11.*
- *"B26" re-triage: **already done**. ev050 (the sw130 gift) is `unreachable:beat_gen` in
  `CH03.derived.json`, and the live B26 is the Center-PC beat. The collision was a
  hand-suite-era label that died with the hand suites.*

*So the hold is 10 Strength rows (7 events) plus 1 Bike Wheel arm, settled at CH25/CH11.)*

### 64. `CapabilityModel.grants_capability` is the wrong signature — 28 warnings standing

`check --chapter CH04` emits 28 `capability_model_unenforced` warnings because no
capability model is supplied, and none can honestly be written against the current
Protocol. `grants_capability(name) -> chapter_id | None` assumes a capability is a
boolean granted by exactly one chapter. The Part 4c census
(`reference/archive/PLAYTEST_AUTHORING_IMPROVEMENT_V2.md`, "AMENDED 2026-08-27") found otherwise:
capabilities are **predicates over player state**, and Uranium grants every field
move by **two disjoint routes** — `rock_smash` is `numbadges >= 1 AND (knows
ROCKSMASH OR holds BOXINGGLOVES)`, and the same move-or-gadget shape holds for
strength/`POWERGLOVE`, surf/`SURFBOARD`, dive/`SCUBAGEAR`, waterfall/`CLIMBINGPICK`,
with all five gadgets granted from one event (Map167/ev28) on a badge-count ladder
at a different point in the game than the HMs.

Some gates are also not derivable at all: `old_rod` sits behind `var[103] >= 5`,
and variable 103 is named "Battle Var01" — the only artifact stating what it means
is the dialogue text, so a name-keyed classifier misses it *confidently*. The
redesigned model must therefore accept hand annotation.

Deliberately left standing rather than papered over with a model that would answer
confidently and wrongly. The sibling rule `approach_model_unenforced` is now down
to 1 row (the seam, which has no event cell) because that half **was** derivable —
see `chapter_manifest/approach_model.py`.

### 67. No chapter routed so far carries a route plan, and CH01-CH03 have none committed

Slice 3's `RULE_ROUTE_ORDER` only enforces anything when
`reference/routes/<chapter>.route.json` exists; with no plan on disk
`build_route_model` returns None and the rule degrades to its
`route_model_unenforced` warning. **No route plan is committed for CH01-CH04**,
so the rule is unenforced for every chapter gated to date. Two separate
reasons, and only the second is a defect:

1. **CH01-CH03 cannot be solved at all.** Their manifests predate slice 2 and
   are missing `reachability_consulted`, so `load_manifest` refuses them
   ("regenerate the manifest rather than patching it") before the solver
   sees a single beat. Regenerating a gate-closed chapter's manifest is
   itself #65, so this is blocked behind that, not behind routing.

   **Corrected 2026-09-15:** this blocker is gone. #65 closed — the
   CH01–CH05 manifests were regenerated in commit `eb0f064a`, and
   `python -m rpg2gba.chapter_manifest check` loads and checks all five
   chapters cleanly (CH01 118 / CH02 16 / CH03 48 / CH04 0 / CH05 0 errors,
   all ordinary `undispositioned` findings, no load failure). CH01–CH03
   dispositions files now exist too
   (`reference/manifests/CH0{1,2,3}.dispositions.json`). So CH01–CH03 CAN
   now be solved; what remains is purely that no route plan has been
   generated and committed for them. Verified 2026-09-15: `reference/routes/`
   contains only `CH05.route.json` and `CH05.locations.json`, so
   `RULE_ROUTE_ORDER` is still unenforced on CH01–CH04 and a
   `route_model_unenforced` warning still fires on all four.

2. **CH04 solves, but its plan disagrees with its registered order.** The
   solver walks `B1 B15 B4 B9 B7 B3 B12 B5 B6 B13 B11 B2 B14` for 112 tiles;
   `route2.py` registers `B1 B4 B14 B2 B3 B5 B6 B7 B9 B11 B12 B13 B15`,
   which the solver's own cost model scores at 130 tiles. **Both orders are
   entirely free of foreign-trigger crossings and neither has an unroutable
   segment** -- measured 2026-08-30, not assumed. So the 18-tile gap is pure
   walk distance: the registered order is suboptimal, not wrong, and nothing
   about CH04's passed gate is invalidated by it.

   Committing `CH04.route.json` as-is would therefore turn `check --chapter
   CH04` red over a cosmetic reorder of a closed chapter. Not done.

**Consequence: slice 3 is validated forward, from CH05, not retroactively.**
This is the one place slice 3 differs from slice 2, whose retroactive
re-derivation over CH01-CH04 was an explicit part of its build
(`reference/archive/PLAYTEST_AUTHORING_IMPROVEMENT_V2.md`, "Validation -- CH05 is not
sufficient evidence"). Slice 3 has no equivalent, and the reason is
structural: slice 2 re-derived a *fact about the world* that a gated chapter
already recorded the right answer to, whereas slice 3 proposes an *ordering
the operator has to approve* -- there is no pre-existing approved route to
re-derive, because ordering was convention until now.

What slice 3 does get instead is the CH04 B2/B3 incident as a worked case:
the plan puts B3 at position 5 and B2 at position 11, while the chapter
registers B2 at 3 ahead of B3 at 4. That is exactly the inversion whose
un-checked walk crossed Timothy's event-touch tile and fought the wrong
trainer, and `RULE_ROUTE_ORDER` reports it as an error. The rule would have
caught the original incident.

**Remediation:** solve and commit CH05's plan as part of CH05's authoring
loop, where the operator approves the route before the chapter module is
written and the two agree by construction. Revisit CH04 only if #65 reopens
it for another reason -- do not reorder a gated chapter's beats to satisfy
this rule on its own.

**2026-09-06 — CH05 was the forward validation this item called for.** CH05
carries a committed `reference/routes/CH05.route.json`, solved and approved
before the chapter module was authored (13 nodes, 165 tiles, no `CROSSING`
lines, re-verified at the §9 gate to still agree exactly with the committed
module). Slice 3 is now validated forward from CH05 as planned. The
remaining work is the retroactive re-derivation for CH01-CH04, which stays
gated behind #65 (CH01-CH03) and the suboptimal-but-not-wrong CH04 order
noted above (not reopened by this).

*Found 2026-08-30 finishing slice 3.*

**Widened 2026-08-30 by slice 4.** The same absence now leaves a second rule
unenforced. `compare_walk` reports `compared: false` for every chapter, so the
trigger-divergence check that would have caught CH04's B2/B3 incident cannot
fail anything either. Same remediation, same chapter: committing CH05's
approved plan turns on `RULE_ROUTE_ORDER` *and* runtime divergence enforcement
together, and neither one is on before that. Slice 4's non-enforcing halves —
the walked path, Q8's ledger, the frame rule, the conformance report — do not
wait on a plan and are live now.

### 68. Nothing pins slice 4's frame-rule phrase list to the harness's own text

`playtest/frame_rule.py` classifies a beat's failure message as a negative
claim by regex over an explicit phrase list, several entries of which were
derived by grepping the harness's current `ScenarioError` strings. Nothing
keeps the two in step: a future beat that phrases a negative claim a new way
("the flag was never set", say) is silently not covered, and the rule's
conservative bias means that failure mode is quiet by design — it prefers
missing a negative claim over refusing an unrelated failure.

This is accepted, not a defect: the escape hatch is that any author can
satisfy the rule with one `mark_frame()` call, and a false refusal is more
expensive than a miss. Worth a re-grep of `src/rpg2gba/playtest/` for new
negative-claim phrasings whenever a chapter adds a batch of beats.

*Found 2026-08-30 building slice 4.*

### 71. `BUILD_PLAN.md:94`'s ART step has no owning command

`BUILD_PLAN.md`'s canonical per-chapter loop lists step 3 as `ART — quantize
the chapter's real tilesets + sprites to GBA 4bpp` (`BUILD_PLAN.md:94`) with
no command under it, the same defect `CH05_TODO.md` step 3 carried before it
was corrected on 2026-09-04. The fix is already known and was worked out
while building CH05: ART has no standalone entry point because it isn't a
separate stage — it is discharged by two other steps. Tilesets come from step
4's `phase5` (`src/rpg2gba/tileset_converter/phase5.py:232`, `phase5.convert_all`
→ `build_slice_tilesets`, its own internal "per-map graphics: synth tilesets +
overlay" step, budget-guarded at `graphics/emit.py:537-548`). Sprites come from
BUILD's assembler chain (`sprite_pass.run_sprite_pass`, called from
`scripts/stage_slice_scripts.py:429` and `scripts/assemble_pathfinder.py:214`);
step 4 itself only writes empty-conversion stubs
(`sprite_emit.write_stub_gen_files`, `phase5.py:350`). Fix: add a line under
step 3 in `BUILD_PLAN.md` saying so, so CH06 doesn't rediscover it the same
way CH05 did.

### 73. `build_beat_model` cannot see a boundary row claimed by the arriving chapter

`chapter_manifest`'s `build_beat_model` loads a chapter's own playtest module
plus its predecessors, but never its successors. Consequence: CH04's
`DEFERRED_BEATS` entry for `map035/ev001/p1`, whose reason was updated
2026-09-04 to record that the arrival nudge fires on the CH05 side of the
crossing (see #72) and is permanently CH04's to skip, cannot be satisfied by
a CH05 beat that claims the same manifest row — `chapter_manifest check
--chapter CH04` reports it today as `unregistered_beat`. It is a warning, not
an error, because CH04 is not the live chapter, so it does not fail the gate;
it is counted debt. The real fix is letting `BeatModel` see a boundary row
claimed by the chapter that is arriving, not just the ones that came before
it. This is the tooling half of #72's convention.

**MECHANISM LANDED 2026-09-10** (`14aa6f43`); the symptom is still open, on
purpose. Rather than teach `BeatModel` to look forward, the answer is a new
argument-free `boundary` disposition verdict plus `chapter_manifest/
boundary_model.py`, which checks both halves of the claim: that the row really
is a forward crossing (`slice_growth` for `code 201`, `seam_growth` for map
connections — either alone is blind to half the corpus's boundaries), and that
the successor chapter's registered `Beat.rows` actually claim it. See
`ChapterBinding.successor` for the forward accessor `chapters.json` never had.

**Still open:** `map035/ev001/p1` continues to report `unregistered_beat`,
because nothing has switched CH04's disposition to `boundary` — those
dispositions are re-derived under `reference/archive/REDERIVATION_PLAN.md`'s P7 freeze and
editing them early would corrupt it. Two further facts for whoever does:
only **`p0`** is a valid `boundary` candidate (`p1` is an arrival-nudge autorun,
not a transfer, and `is_forward_crossing` rejects it), and **CH04 and CH05
currently contradict each other in writing** about who owns the event — CH04's
`DEFERRED_BEATS` reason says CH05 claims the row, `ch05.py`'s docstring says
twice that it does not, and no CH05 beat lists it.

### 75. A vacuous trigger overlay reads identically to a genuinely clean route

Directly caused by #74: zero `CROSSING` lines out of `build_trigger_overlay`
currently means either "the route is clean" or "the overlay had no trainer
data to check against," and nothing distinguishes the two. The project
already has the right idiom for this class of problem —
`route_model_unenforced` (`chapter_manifest/checker.py`) refuses to let an
absent route plan read as a passing `RULE_ROUTE_ORDER`. The same discipline
belongs on the trigger overlay: if a chapter's dispositions carry trainer
rows but the overlay yields no `TRAINER_SIGHT` tiles on the maps those rows
live on, the rule should fail loud rather than silently reporting zero
crossings (`CLAUDE.md` §4.5).

### 77. No automated check that the authored chapter module matches its locations plan

Step 6a of the per-chapter loop derives `reference/routes/CH05.locations.json`
from the manifest + dispositions + decoded map JSON; step 6b hand-authors
`src/rpg2gba/playtest/chapters/ch05.py` from it. They are two independent
statements of the same coordinates, and nothing fails if they drift apart —
6b's instruction to "re-solve and confirm it agrees" is a manual eyeball,
not an assertion. Wants a `routing locations --check` subcommand that diffs
the authored beats' resolved cells against the approved `.locations.json`
file and fails loud on any disagreement.

### 78. `RULE_ROUTE_APPROACH` only checks nodes carrying a `chosen_approach`

`RULE_ROUTE_APPROACH` (`src/rpg2gba/chapter_manifest/checker.py:49`, enforced
at `:924-982`) compares a plan node's committed approach cell against what
the chapter module actually declared — but only for nodes that carry a
`chosen_approach` in the first place. A group whose declared cell differs
from the plan's chosen one goes entirely unchecked if the plan node never
recorded a `chosen_approach`. CH05's B8 is exactly this case (the round-trip
warp beat), on a different map than the corpus's next opportunity to hit it.
Needs either a `chosen_approach` guaranteed on every multi-candidate node, or
the rule widened to flag a node with no recorded approach as unenforced
rather than silently skipped.

### 80. `find_match` keys a claim to one `(map_id, event_id)` pair

`src/rpg2gba/playtest/archetypes/__init__.py:101` `find_match` takes
`(map_id, event_id, archetype)` plus an optional `row_id=` to disambiguate
multiple pages of the same event matching the same archetype. It has no way
to claim two separate warp *events* (i.e. two `(map_id, event_id)` pairs) as
one beat. CH05's B8 needs exactly that — the 1F→2F and 2F→1F warp events are
two different manifest rows under the operator's warp round-trip idiom ("a
warp is tested by crossing it, crossing back, and crossing again, so the beat
ends on the far side") — and the workaround is two separate `find_match`
calls inside one beat body rather than one call that claims both rows.

### 81. A warp beat has no map-based proof it actually crossed

A warp beat whose destination map is the same map the player started on has
no way to prove, from map identity alone, that the warp fired.
`cross_threshold`'s `wait_for_map` step and the following `require_map`
assertion both pass trivially in that case, because the player never had to
leave the origin map — which is the same map they are being asked to assert
arrival on. This is a live-caught defect, not hypothetical: only
`assert_near`'s coordinate check caught CH05's B1 problem, and only because
the coordinates happened to disagree; the map-identity half of the assertion
was silently satisfied throughout. A warp beat should additionally assert
that the player LEFT the origin map at some point during the crossing, not
merely that they are on the destination map at the end.

### 82. Route review in the map viewer is better than the CLI-text approval gate

`BUILD_PLAN.md`'s ROUTE step specifies its approval gate as "read the
summary" — a CLI text output. CH05's STOP 3 instead reviewed the solved
route visually in the map viewer (Events mode, the `Beats`/`Planned` overlay
drawing the solver's ordered polyline plus derived beat markers) before
authoring, and it was the better gate: order and approach-cell choices read
as a picture much faster and more reliably than as a tile count. Wants the
`BUILD_PLAN.md` ROUTE-step wording changed to point at the viewer review instead
of (or in addition to) the CLI summary.

### 84. `ITEM_TM76` needs a sanity check before it's ever reachable

The transpiler resolved CH05's B6 (Map036 EV008, the item ball at the room
sealed behind Surf) to `ITEM_TM76` via `reference/uranium_id_map.json:1383`,
which passes the fork-index gate cleanly. But this expansion's normal TM
naming convention is `ITEM_TM_<MOVE>`, not a bare numbered `ITEM_TM<N>` —
worth confirming `ITEM_TM76` actually exists as a real, correctly-numbered
constant and isn't a coincidental id collision.
`reference/chapters/05-passage-cave.md:134` says Uranium's TM76 is Stealth
Rock; that should be cross-checked against whatever move `ITEM_TM76` actually
teaches in the fork. It cannot bite in CH05 itself — the item sits in the
Surf-sealed room, `blocked:surf`, not reachable until Act 5 — which is
exactly why a wrong mapping would otherwise go unnoticed until then.

### 85. `BUILD_PLAN.md`'s boot-walk seeding recipe is broken for every chapter

**2026-10-21:** operator: waits. It rides with I6 (#153).

`BUILD_PLAN.md`'s step 8 (BOOT) instructs seeding the walk from the
predecessor chapter's `--at-end` blob (`playtest seeds --chapter <prev>` then
`walk --at-end`). That recipe cannot work for any chapter, not just CH05:
seed blobs are keyed by the ROM's sha256 and invalidated by any rebuild, and
the arriving chapter's own BUILD always rebuilds the ROM before BOOT runs
— so by the time a chapter reaches BOOT, the predecessor's blobs from its own
green run no longer match the current ROM hash, and `playtest seeds` reports
"no seeds for this ROM build — run the chapter green from the start first."
Found and worked around on CH05, 2026-09-06 (commit `be66391a`): the
arriving chapter's own green run at BOOT already writes a seed blob for
its first beat, and that state is identical to the predecessor's end state by
construction (CH05's B1 blob boots to Route 02 (19,50), exactly where CH04
leaves the player). The correct recipe is `playtest walk --chapter <this> --at-beat
<first beat> --engine engine` — seed from the arriving chapter's own
first-beat blob, never the predecessor's `--at-end`. `BUILD_PLAN.md` should
say this instead of the current recipe.

### 89. Three Map019 trainers have battle events that never fire — in slice since CH03

Surfaced 2026-09-08 by #88's census, which is the first thing that could see it.
`TRAINER_LOU_136` (Map019 EV004), `TRAINER_JOE_135` (EV005) and
`TRAINER_RICHARD_137` (EV006) — all `TRAINER_CLASS_BIKER` — sit on Map019, in
`SLICE_MAP_IDS` since CH03, and each is `queued-not-pinned`: their
`pbTrainerBattle` calls are still `# UNHANDLED code 111` in `Map019.pory`, so
nothing is emitted and nothing aborts. The NPCs deliver their dialogue and never
battle.

**Not a build risk, and deliberately not fixed by pinning them.** Staging a
battle nothing references would be dead data. The real work is the transpiler
emitting the conditional-branch shape those three use, at which point #88's gate
turns red and the pins follow. Two things are known already: `TRAINER_CLASS_BIKER`
is **not** a constant the fork defines (checked 2026-09-08 against
`include/constants/trainers.h`), so a class decision is owed before these can
stage at all (§4.7 — check for a native analog before concluding new C is
needed); and their parties pull in species not currently staged.

Whether Map019's gang battles are worth replicating is a §10 content call, not a
mechanical one. Filed so the census's finding does not evaporate.

### 91. Map-connection seams went live the same way `code 201` warps did, and nothing detects it

`rpg2gba slice-growth` (`src/rpg2gba/slice_growth.py`, landed 2026-09-09) answers
the `code 201` half of this: per gated chapter, which events carry a transfer to
a map that was out-of-slice at authoring time and is in-slice now.
`metadata_wiring.classify_event` had skipped those events entirely, so they were
invisible to both the manifest generator and the beat author. It found six, all
forward boundaries: CH01 Map032 EV023/EV036/EV037 -> Map033, CH02 Map033
EV045/EV046 -> Map031, CH04 Map035 EV001 -> Map036.

**It reports CH03 clean, and that is a scope artifact, not a verdict.** CH03's
forward boundary is the Kevlar <-> Route 2 seam (`connections.json` 31 N<->S 35),
a map connection rather than a `code 201` warp, and the detector structurally
cannot see connection edges. CH03's B25 -- which asserted the north edge toward
then-unbuilt Route 2 was "a clean impassable wall", and needed reconciling by
hand in 2026-08-26 when Route 2 was built -- is the known instance of exactly
this class going undetected.

Wanted: the same enumeration over `connections.json` /
`tileset_converter/connections.py`. Per gated chapter, every connection edge that
became crossable after that chapter was authored. Until it exists, no gated
chapter's seam boundary has been audited and "slice-growth is clean" must not be
quoted as though it covered them.

Tracked as **P2b** in `reference/archive/REDERIVATION_PLAN.md`; a prerequisite for that document's
freeze step for the same reason the `code 201` half was.


*(2026-10-04: the former "Parked until the CH05 branch is cut" section was dissolved. Its trigger passed; #51 and #62 now sit here, followed by items moved back from the Done section and newly filed items.)*

### 51. Q5.1 citation-verification experiment — run across CH04 + CH05

*(2026-10-04: the CH05 branch was cut and merged long ago, so the trigger that parked this has passed. Whether CH05's pass was ever run is not recorded here; check before treating the experiment as done or dropped.)*

Migrated from `CH04_TODO.md`. A blind second-agent pass over citation-triggered
disposition rows only, scoped to run on CH04 and CH05; kept as standing
practice if it catches at least one silent pass across both chapters. CH04's
pass is done; **CH05's pass, and the decision it feeds, wait on the CH05
branch being cut.**

### 62. CH05-scoped items scattered across `reference/archive/PLAYTEST_AUTHORING_IMPROVEMENT_V2.md` Part 5 with no tracked home

*(2026-10-04: unparked. CH05 is built and merged; the bullets below are historical except the parts already marked DONE or folded into #65/#67. The re-disposition it asked for is covered by the re-derivation, which closed 2026-10-03.)*

Filed 2026-08-29 out of an audit of `reference/archive/PLAYTEST_AUTHORING_IMPROVEMENT_V2.md` Part 5
(the CH05 dry run) that found several concrete findings never landed in either
this file or `reference/chapters/05-passage-cave.md` §7. Parked here as CH05-build
work, not open questions:

- **The arrival-nudge autorun archetype is missing from Q0's Tier-1 template
  build set entirely** (§5.6). **DONE 2026-09-01 by `CH05_DECISIONS.md` D4** —
  this bullet was filed 2026-08-29 and the work landed two days later; verified in
  code 2026-09-02. Template: `src/rpg2gba/playtest/archetypes/arrival_nudge.py`
  (one of the four shipped). Classifier: `_match_arrival_nudge`
  (`chapter_manifest/archetypes.py:159`), registered at `:43`, fingerprint
  predicates `_NUDGE_HEADS` / `_NUDGE_EFFECTS_REQUIRED` at `:62-65`. The module
  docstring (`:19-26`) records the design point worth keeping: `warp` and
  `arrival_nudge` stay *separate* archetypes because the two pages routinely share
  one event — the cave entrance is p0's warp, p1's nudge — so such an event yields
  two `ArchetypeMatch` objects rather than one blended verdict. Map036 EV002 has
  exactly that shape.

  **Residue, carried into `CH05_TODO.md`: the template is written but has never run
  in a ROM.** CH04's `map035/ev001/p1` (`beat:B8`) was authored and deliberately
  *never registered* — its sibling warp page was out of slice, so nothing compiled
  for it (`playtest/chapters/ch04.py:121-129`). Map036 EV002 p1 is the first live
  exercise of `arrival_nudge`, against the corpus's second-largest idiom (324
  instances across 73 maps — larger than item ball at 243, staircase at 222 and
  cave-exit at 102 combined, behind only the door/warp event at 996). Of the four
  Tier-1 templates this is the one most likely to surprise us in CH05.

  Why it needs a beat at all, since the name misleads: the page *moves the player
  and writes state* (`move_route` + `temp_switch_write` in its effects), so
  `may_be_cosmetic` is false by the checker's own honest test — unlike the
  staircase case in §5.2, where the vocabulary genuinely has no correct verdict.
  It is also the thing that steps the player off the warp's own trigger tile.
  Broken, it yields either a locked field on arrival (a freeze) or a refiring
  autorun on that tile (a warp loop) — the latter being the class already
  boot-observed in `WARP_FACING_HANDOFF.md` / `b7c5b8d7`, where a down-stairs warp
  re-fired `TryArrowWarp` and bounced the player back upstairs.
- **TM76 and Sableyeite sit in a Surf-sealed 30-tile room** (§5.7): Map036 has 513
  walkable tiles in 7 connected components, 450 reachable on foot from the
  entrance, but the room at bbox x 31-36/y 11-16 opens only into a water pocket
  disconnected from the walkable region. Both pickups are `blocked:surf`, and
  Surf is granted at Map143 (Act 5) — the longest capability deferral found in the
  corpus so far. `05-passage-cave.md` B6/B7 must be authored as deferred beats
  (the CH02/CH04 `DEFERRED_BEATS` idiom), not live beats: a second, much longer
  arm on the stranded-revisit backlog alongside the Rock Smash one (§39/§57).
- **The standing guardrail that a green CH05 §9 gate is NOT evidence** that
  slice 2, the capability model, or the mart/Poké Center/PC templates are correct
  (§5.8, restating Q13). CH05 exercises zero seam rows, zero populated
  `requires[]`, zero mart/Center/PC instances, and its only `blocked:` rows are
  terrain-derived Surf, not switch/variable-derived — the least-representative
  possible confirmation. Their real validation is the retroactive re-derivation
  of CH01-CH04.
- **The decided-but-unbuilt re-disposition of the whole built corpus during
  CH05's build**, with its ordering safeguard: freeze the expected answers,
  derive, diff, then write — do not derive-and-write in one pass, or a
  regression in the derivation logic reads as a correct re-disposition. Cross-
  referenced by `reference/archive/PLAYTEST_AUTHORING_IMPROVEMENT_V2.md` §5.6, §5.7, §5.8, Q3 and
  Q13.

  **2026-09-06 — parts 3-4 (the corpus re-disposition) were folded into #65
  and deferred to "after CH05"; that is now due.** CH05 has passed its §9
  gate. The re-disposition work should proceed under #65/#67 rather than
  here. **The ordering safeguard carries forward verbatim and must not be
  lost in that move:** freeze the expected answers, derive, diff, then
  write — never derive-and-write in one pass, or a regression in the
  derivation logic reads as a correct re-disposition.

### 39. `pbPushThisBoulder` is unconverted — due in CH25, the chapter that grants Strength

*(2026-10-04: still open; due CH25 as scoped. Moved back from the Done section, where it had been filed by position only.)*

*Reclassified out of `CH03_TODO.md` #20 on 2026-08-17, where it had been logged
as Kevlar Town's biggest blocker. It never blocked CH03.*

`pbPushThisBoulder` (`reference/scripts_dump/101__PField_Field.rb:2850`) pushes
only `if $PokemonMap.strengthUsed`, and returns false otherwise — the standard
series mechanic. So an unpushable boulder in a pre-Strength chapter is the
design working, and converting this function would not have changed any beat's
outcome in CH03.

**Due in CH25 (Route 11)** — the chapter that *grants* HM04 (`00-atlas.md`
line 116), not the chapter before it. It should land alongside the mechanic it
enables, where a beat can actually exercise a push; shipping it earlier means
committing an unverifiable conversion.

**Scope when it comes up** — 5 queue entries, plus the content they gate:

| Map | Entries | What |
|---|---|---|
| 19 (Passage Cave Grott-Hole) | 17 (all of them) | 3 boulders + the Biker encounters: 3 `pbTrainerIntro(:BIKER)`, 3 `Kernel.pbNoticePlayer`, 3 `pbTrainerEnd`, 4 `pbTrainerBattle` conditionals (Lou/Joe/Richard), 1 warp back to map31 |
| 31 (Kevlar Town) | 2 of 17 | the two outdoor boulders, `EV001` (10,16) and `EV037` (12,16) |

Map019 **stays in `SLICE_MAP_IDS` now** (user call, 2026-08-17) so the cave is
built and art-checked well before Strength arrives — only its beats are
deferred.

**Implementation note already settled:** the push is **object-driven** —
`OBJ_EVENT_GFX_PUSHABLE_BOULDER`, **not** `MB_PUSHABLE_BOULDER`
(`reference/chapters/03-kevlar-town.md` §6.1 — "corrected in the ledger, do not
re-invert").

The same CH25 work unblocks the **Cry Boy sidequest** in Kevlar Town, which is
the same return trip: *"After getting HM04 in Legen Town, come back and speak to
the boy crying just outside of the entrance of the Poké Mart"*
(`Kevlar_Town.wiki:30`). CH03's B18 correctly observes only the pre-Strength
idle page today.

### 40. Commands stranded after a `Transfer Player` warp — 176 rows, two unrelated classes

*(2026-10-04: still open (40a cosmetic tail, 40b Theo cutscene due CH58). Moved back from the Done section, where it sat by position only.)*

*Filed 2026-08-17 after CH03's queue triage. The single queue signature —
"command follows a Transfer Player warp: pokeemerald halts the script at the
warp (ScrCmd_warp/DoWarp), unlike RMXP which keeps running the page" — covers
two problems with nothing in common. Do not size them as one job.*

RMXP keeps executing an event page after code 201; pokeemerald halts the script
at the warp. Anything after the transfer is therefore unreachable in the port,
and the transpiler queues it instead of dropping it silently (correct — §4.5).

**Distribution:** map172 **132**, map32 13, map31 12, map33 11, map49 3, map81 2,
map48/50/89 1 each. 176 total, over 9 maps. That shape is the whole story: one
map is a real problem, the rest are choreography.

#### 40a. The cosmetic tail — 44 rows, everything except map172's cutscene

31× code 223 `CHANGE_TONE`, 11× code 204 `CHANGE_MAP_SETTINGS`, 2× code 241
`PLAY_BGM`.

**The 223s cost nothing.** Every one observed is `Tone rgba [0,0,0,0]` over ~6
frames — *neutral*, i.e. the fade back **in** that closes a fade-out/fade-in pair
around the transfer. The transpiler already strips the opening half as subsumed
by the native warp (`transpiler.py:242-249`, the `pbCaveEntrance` note: "the GBA
warp performs its own map-transition fade"). This is the same argument from the
other side. Stripping them is a no-op that quiets ~2/3 of this signature.

The 204s are fog (subtype 1 — e.g. `"004-Shade02"`, opacity 60, zoom 250): a
real but minor visual loss with precedent for accepting it (the Map033 "Luz"
ambient-light strip, `CH02_TODO` #11/#12). The 241s are destination BGM, largely
moot while audio is still substitution-based with slice maps on `MUS_LITTLEROOT`
(the per-map `reference/audio_map.json` wiring from
`audio_decision_2026-07-14.md` was never built).

**Action:** strip 223-to-neutral after a warp as a recognized breadcrumb, and
rule on fog/BGM as accepted debt. Cheap, and it stops this signature from
looking like 176 rows of lost logic.

#### 40b. Map172's Theo cutscene — 131 rows, genuinely dropped, due CH58

**131 of map172's 132 rows belong to one event: `EV4 'Theo'` page 3.** The codes
are real content, not choreography: 40× 101 `SHOW_TEXT`, 19× 106 `WAIT`, 14× 355
`SCRIPT`, 9× 209 `MOVE_ROUTE`, 4× 223, 2× 202 `SET_EVENT_LOCATION`, 2× 207, 1×
111 `COND_BRANCH`, and 1 nested 201 `TRANSFER`. (The 34× 509 rows are the
editor's per-step display duplicates of the 209s — `transpiler.py:95` — not
independent logic.) A whole cutscene sits after the page's warp.

**Not near-term.** Page 3's condition is `switch1_id 125, switch1_valid true` —
switch 125 is the "FINAL EVENT" **postgame** gate. `chapters.json` already names
this exact case: CH58 (Moki Town postgame, A9) is "where the postgame pages on
slice-1 maps finally fire ... the switch-125 'FINAL EVENT' grants that
01-moki.md §4.2 rules out of CH01 (Lava Cookie on 49, Poke Radar on 50, **HM07
Waterfall on 172**)". So this is CH58 work, and **CH08's visit-2 return to
map172 is unaffected** — page 3 cannot fire there.

**This one needs a structural fix, not a strip.** The content has to run at the
destination, since the source page cannot continue past its own warp: split the
tail into a script that fires on arrival (a map-script `ON_TRANSITION`/
`ON_FRAME` on the destination, gated so it runs once), rather than trying to
keep executing at the source. Worth designing when CH58 is written — and worth
checking then whether any other page-3-style postgame page hides the same shape.

### 41. 106 items the id map names and the fork does not define — plus Phase 2's item output is a dead end

**2026-10-21: NARROWED.** All that is left is the 5 blocked items (Hafli Berry, Atom Ball, Nuclear Ball, which wait on the Nuclear type; Air Mail; the Uranium Core form toggle) and the inert behaviours listed below. Everything else is generated by `item_converter`.

*(2026-10-04: still open. Moved back from the Done section, where it sat by position only.)*

**2026-10-19: resolved by I3 S2 on `intermission-engine-layers`, apart from 5
blocked items** (`reference/engine_layers_i3_i5.md` §8).
- **How:** `item_converter` generates every missing item into gitignored engine
  headers.
  - Berries continue the berry run.
  - Everything else follows the last stock item.
  - Behaviour comes from `reference/item_rulings.json`.
- **Hand edits removed:** the hand-typed berries and key items are gone from the
  tracked engine, along with their 14 Uranium-art files.
- **Still blocked:** Hafli Berry, Atom Ball, Nuclear Ball (all need the Nuclear
  type), Air Mail (the mail id run) and Uranium Core (the form toggle).
- **Behaviour deferred:** the field-use gadgets (#143, Boxing Gloves and the
  others), mega forms and the Royal Jelly evolution block are inert for now.

*Filed 2026-08-19 out of `CH03_TODO.md` #27, where it was surfaced by CH03's
item-grant fix. Not chapter-blocking; it will keep surfacing one chapter at a
time until it is done properly.*

`reference/uranium_id_map.json` maps 607 Uranium items to `ITEM_*` constants and
already precomputes the shortfall in its own `needs_engine.items`: **111 of them
do not exist in `engine/include/constants/items.h`.** Five were added by hand for
CH03 (the four Uranium berries + Sprinklotad, `67fd0435`); **106 remain**,
including Uranium-original held items, mega stones, key items and mail.

Every one is an item grant, mart entry or held item that will fail the §4.7
forward gate and queue when its map is converted.

**The compounding half is the real finding: Phase 2's item converter output never
reaches the engine.** `pbs_converter/items.py` emits both
`include/constants/items.h` and a `gItemsInfo[]` table into
`output/uranium-build/`, and **nothing includes or copies them into `engine/`**.
Compare the flags and map-alias hooks (`engine/data/event_scripts.s:1743`,
`map_events.s:27`) — there is no items equivalent, so that output is currently
written and discarded.

**Scope it as a Phase-2→engine integration, not 106 hand edits.** It also needs a
decision the five berries dodged: those were vanilla-equivalent, so their data
could be copied from a twin. An original held item or mega stone has no twin and
needs real hold-effect data from Uranium's `item_field_codes` worklist
(`items.py:308-321`, already generated and never read).

### 42. Shape-C item grants with a non-empty then-body — 60 of 150 sites still queue

*(2026-10-04: still open. Moved back from the Done section, where it sat by position only.)*

*Filed 2026-08-19 out of `CH03_TODO.md` #25 item 2, which is otherwise closed.*

Uranium grants items three ways. Shape C is the awkward one: a `code-111`
type-12 conditional whose **test expression is the grant itself**, because
`Kernel.pbReceiveItem` returns whether the item was accepted, and the then-body
is the success path. 152 sites / 56 maps corpus-wide.

`43aa482e` handles the common case — an **empty** then-body, i.e. a pure
side-effect wrapper — by emitting `giveitem`. **60 sites with a non-empty
then-body still queue**, most of them on items the fork does not define (#41),
which is why the two want planning together. *(2026-10-19: #41's items now exist
in the engine, generated, so this count should drop at the next corpus
transpile. Re-measure before planning.)*

Do **not** approximate the success path. Emerald's `giveitem` already sets
`VAR_RESULT`, so the faithful mapping is plausible and cheap to verify against
`engine/` (§4.7) — but the bag-full / refusal semantics have to be checked
before a then-body is wired to it, not assumed.

Worth remembering why this class was invisible for so long: **the queue entry
names the conditional, not the grant hiding inside its test expression** — the
same lesson as `CH03_TODO.md` #26(b).

### 43. Beat classes the manifest cannot see, and the `cosmetic` rule

*(2026-10-04: still open (part (a) undecided; part (b) encoded as `is_player_observable`). Moved back from the Done section, where it sat by position only.)*

*Filed 2026-08-25 out of the operator's read of CH04's beat list, which found
four gaps in a chapter that had already been fully dispositioned.*

Two findings, both corpus-wide, both structural rather than CH04-specific.

**(a) The manifest enumerates event pages and overland seams — nothing else.**
An encounter table is neither, so no generated row can ever represent one.
CH04 had no beat covering "walk in the tall grass, get a wild battle" because
nothing in the approval object could prompt for it. The same hole applies to
any beat class that is not an event page: encounter tables, tileset behaviour
(counters, ledges, water), connection-only seams, field-move surfaces. Either
the generator grows non-page row kinds, or every chapter doc needs a
hand-authored "beats with no manifest row" section that a reviewer is
required to fill. Decide which before the next chapter is authored — CH04 got
its B15 by hand (`04-route-2.md` §3.1).

**(b) `cosmetic` was being decided on state writes, not observability.**
The rule actually applied was *does this page write state?* That made Larrie's
defeated re-talk a beat (it rides on `pbPhoneRegisterBattle`) while Timothy's
identical-in-kind re-talk was `cosmetic`, and it dropped a talk-triggered NPC
with an emote bubble, a cry SE and a line of dialogue. None of those write
state; all three break independently. The rule is now *is there anything a
player can press A on and observe?* — `cosmetic` means decoration with no
trigger.

CH04 was re-swept under (b): `ev009/p1`, `ev011/p0`, `ev012/p1` became
`beat:B12`/`B13`/`B14`. **CH01–CH03 have not been re-swept** and passed their
§9 gates under the old rule, so each may be carrying interactive rows filed as
cosmetic. The sweep is mechanical — cross-reference trigger against
disposition, flag action-trigger rows dispositioned `cosmetic` — and the
checker cannot catch it, since `cosmetic` on a state-free row is legal by
construction.

**The sweep was run 2026-08-25; results and remediation are §44.** It could not
be mechanical after all — CH01–CH03 have no manifest to cross-reference.

*(2026-09-15: the rule never reached the generator — P8b's derived `cosmetic` used
"no state-writing tag" and waved through 100 CH01–CH03 talk rows. Now encoded as
`ManifestRow.is_player_observable`; `reference/archive/REDERIVATION_PLAN.md` §15.8.)*

### 92. The capability model cannot see field capabilities, because their grants are not switch/var writes

**2026-10-21: NARROWED.** Rock Smash is modelled: held iff badge count ≥ 1 AND (`HM06` OR `BOXINGGLOVES`) is in the bag (`capability_sites.FIELD_CAPABILITY_ITEMS`), with a teach-HM setup beat (CH08 §9). What remains:
- each other field capability (Surf, Strength, …) joins `FIELD_CAPABILITY_ITEMS` once its HM and gadget item are verified against the corpus, in the chapter that first needs it;
- the engine has no item fallback for a gadget standing in for a known move. That needs fenced C when Legen Town grants the gloves (#143).

*(2026-10-14: **retargeted to CH07A** (operator) — CH07's rockslide is cleared by the ev19
cutscene with no capability; Route 1's six rocks are the first unavoidable smash.
2026-10-15: CH07A folded into **CH08**, so this is now CH08's, which also has Moki's three rocks.)*
*(2026-10-14, CH07: **premise corrected — Uranium does have HMs.** Rock Smash's is internal `HM06`
(wiki "HM01"), `pbReceiveItem` at the CH06 Theo rematch (Map040 ev20/21/79), and each HM move has a
Tinkerer key-item counterpart (Rock Smash → Boxing Gloves, Legen Town, Map167). Point 1's "grant
source" is therefore identified: badge count ≥ N AND (party member knows the move — taught from the HM
or learned by level-up — OR the key item in the bag); `103__PField_HiddenMoves.rb:385-389`. The
"knows the move" half needs a party model, so it now depends on #127. See MEMORY.md →
Uranium-Specific Discoveries.)*

*(2026-10-13, CH06 close-out: the CH06 remainder moves to CH07 -- CH06 grants Rock Smash but
no CH06 row needs it; CH07 (Route 2 rockslide) and CH07A (CH02's rock-gated rows) are the first
consumers.)* *(2026-10-04: still open (point 1 and the CH06 remainder). Moved back from the Done section, where it sat by position only. #128 cross-links the `blocked:` revisit that waits on its requirement groups.)*

*Filed 2026-09-10, out of building `src/rpg2gba/capability_sites.py` (`714d8832`).*

`capability_sites.py` derives a capability's grant sites by scanning every map
for `code 121` (Control Switches) and `code 122` (Control Variables) writes.
That resolves story gates cleanly — `final_event` → `map199/ev001/p0` (CH57),
`gym_1_defeated` → `map042/ev003/p0` (CH06), `quest_log_4` → `map032/ev009/p2`
(CH01). It resolves **`rock_smash` and `surf` to nothing at all**, so CH04's 28
`blocked:rock_smash` rows and CH05's 4 `blocked:surf` rows still report
`capability_model_unenforced` — now for a computed reason rather than for want
of a model, but unenforced either way.

**Why (operator, 2026-09-10): there are no HMs in this game.** Completing a gym
unlocks the move, and the badge is what permits using it in the field. For at
least some capabilities there is **also an item** granting the same ability. The
real gate on a Rock Smash boulder is therefore **the badge AND (the move OR the
item)**.

Two things follow, and the second is the harder one:

1. **The grant source is not a switch/variable write**, so no amount of
   extending the `code 121`/`122` scan will find it. It needs a different
   source — badge state, move/item possession, or whatever Uranium actually
   records — identified before anything is built.
2. **`blocked:<token>` cannot express a conjunction.** The verdict's argument is
   a flat set of capability tokens (`blocked:a|b`, meaning all of them), so
   `badge AND (move OR item)` has no representation: the `|` separator already
   means AND-of-a-set, and there is no OR. Modelling this honestly means either
   a compound grammar or a decision that the disjunction collapses (e.g. treat
   "can rock smash" as one derived capability whose grant sites are the union of
   the move-unlock and the item, gated on the badge). **That is a vocabulary
   decision and belongs to the operator**, not to whoever implements it.

Until then `blocked:rock_smash`/`blocked:surf` staying *unenforced* is the
correct state — it is an honest "not checked", not a silent pass. Do not make it
green by inventing a grant site.

**POINT 2 RULED 2026-09-12 (`reference/archive/REDERIVATION_PLAN.md` §14.9): collapse the token, structure the
model.** No compound grammar. `rock_smash` stays one token meaning "can rock smash in the
field"; the conjunction becomes **requirement groups** on `CapabilityDerivation` — one group
per conjunct, alternatives within a group (`{badge_1}` AND `{move_unlock, boxinggloves}`), with
the route-order grant point being `max` over groups of `min` over alternatives. A compound
verdict string was rejected because it churns every committed `blocked:rock_smash`, gives the
checker a parser to maintain, and encodes a distinction no beat can assert — a negative beat
observes a refusal, never which conjunct caused it. Every disposition authored to date is
already correct under this reading.

`CapabilitySite` (`capability_sites.py:238-248`) needs one addition: the flat
`(token, row_id, map_id, chapter_id, detail)` tuple can only express a union of sites, i.e.
OR-semantics, so it cannot say "the badge is also required." Requirement groups are derived
where possible and **hand-annotated where not** — #64's `old_rod` (`var[103] >= 5`, variable
named "Battle Var01", meaning stated only in dialogue) is why the annotation path is mandatory.

Point 1 (identifying the non-switch grant source) remains open. The prohibition above stands
unchanged.

**PARTIAL 2026-09-13 — badge half only (`reference/archive/REDERIVATION_PLAN.md` §15.2 item 4).** The badge
conjunct is a count ladder (`numbadges >= BADGEFOR<X>`), sourced from `$Trainer.badges[N]=true`
script writes; modelled as necessary-not-sufficient (met ⇒ undetermined, never granted). This
settles CH01–CH05, where no badge is held. **Remaining, filed against CH06** (first chapter with
a badge in its chain): the move alternative (`pbCheckMove` scans live party movesets; Gym 1's
TM27 is Return, so "the gym unlocks the move" does not hold for Rock Smash and the source is
still unidentified), the Map167 gadget items (script branches on `numbadges >= BADGEFOR<X>+1`),
requirement groups proper, route-order granularity, and the annotation path.

See `MEMORY.md` → Uranium-Specific Discoveries for the mechanic itself.

### 126. Day/night flags 105/106 are unimplemented; the first real reader must implement CE 51 from the RTC

Flags 105/106 (Uranium's day/night state, written by common event 51) have no implementation.
All CH01-CH05 readers are no-port `Luz` lamps (map032's 11 are strip-listed), so nothing has needed
them. The first chapter with a real reader implements CE 51 from the RTC (day = 6 <= hour < 20).
CH06 may already carry two or more night/clock-gated `Luz` rows. Related: #28 (time-of-day encounter
tables dropped corpus-wide) and #36 (Luz strip). Source: `reference/archive/REDERIVATION_PLAN.md` §16.3 "C3 closed".

### 127. No real party/dex model: the `party_model` refusal blocks 68+ CH01 rows

**2026-10-21: NARROWED.** The model was built in CH08: party-move and dex-count reads, the HM-teach setup beat, the display-only-variable exemption and the CH01 lab rows. What remains:
- 3 rows still refused `story-state: party_model`: `map046/ev002/p0/b7`–`b9` (CH06);
- the lab's live dex-count dialogue (#144);
- the higher reward rungs (#145).

*(2026-10-15: **built in CH08** (operator). It is needed for Rock Smash's party-knows-move
check, the lab's Poké Ball scene (Map050 EV027) and the Pokédex reward NPC (Map050 EV005
p5–p7). See `reference/chapters/08-route-1-moki-revisit.md` §7 rulings.)*

The generator refuses rows that read party or Pokedex state with a `party_model` blocker. CH01 has
68+ such refused rows. C8 ruling (b) deferred the model to "the first chapter that needs those rows
green". Graphics-only vars 43 and 131 are already exempt via `story_state/graphics_vars.py`; the rest
still refuse. Source: `reference/archive/REDERIVATION_PLAN.md` §16.3 "C8 shape".

### 128. `blocked:` is held back from clerical derivation; revisit at CH08 (was CH06, then CH07, then CH07A)

**2026-10-21: NARROWED.** The capability model is real for `rock_smash` (#92), but `blocked:` is still a proposal. Only the arms of a hand-`blocked:` page derive clerically (#124). The remaining decision, the operator's, is whether a `blocked:` that a held-capability model confirms may derive clerically. Take it when a chapter next proposes one.

*(2026-10-14: moved to CH07A with #92 — CH07 smashes no rock. 2026-10-15: CH07A folded into CH08.)*

`blocked:<spec>` is a proposal only and never dispositions a row until a human copies it into the
dispositions file (the one negative claim, with a false-positive history on obstacle rows, #95). The
operator ruling says to revisit when requirement groups make the capability model real, at CH06.
That work is #92's remaining half (move alternative, Map167 gadget items, requirement groups proper),
so this item closes or moves with it. *(Retargeted to CH07 at the CH06 close-out, 2026-10-13, with #92:
CH06 grants Rock Smash but uses it nowhere; CH07 is the first chapter that needs a rock smashed.)* Source: `reference/archive/REDERIVATION_PLAN.md` §15.7.

### 129. `map033/ev024/p0` `pbCaveExit` leaves three `# UNHANDLED` lines

A transpiler gap: `pbCaveExit` on this page queues three `# UNHANDLED` commands. Once the
transpiler handles it, the row becomes an ordinary `warp` beat. T11/X3 in the plan count it as
"partially handled" (CH05's B1 crosses one). Source: `reference/archive/REDERIVATION_PLAN.md` §16.4, §13.3 T11/X3.

### 130. `^` in `map207/ev011/p0` has no staging substitution; possible real ROM text defect

Staging substitutes the charmap characters it knows (`assembly._CHARMAP_SUBS`) and has no entry for
`^`. This may be a genuine ROM text defect rather than only an oracle gap. Check what the compiled
text actually shows before assuming either. Source: `reference/archive/REDERIVATION_PLAN.md` §16.4.

### 131. Five untranslatable control codes in flavour dialogue

Five flavour-dialogue strings carry control codes the text path cannot translate; `map052/ev003/p1`
is one example. The generator refuses those rows until the codes are handled or ruled strippable
(a content-fidelity call under CLAUDE.md §10 if any is dropped). The other four are not listed in
the plan. Source: `reference/archive/REDERIVATION_PLAN.md` §16.4.

### 132. `stage_slice_scripts.py --write` skips all staging when the existence check fails

Residue of #29. The `--write` block (`scripts/stage_slice_scripts.py`, after the existence check's
`return 1`) is only reached when the check passes, so a genuine dangling-reference failure writes no
`.pory` and `assemble_pathfinder` then builds from a previous run's scripts (a mixed build, ROM
`5d4a7622` vs `360e8506`). #29 fixed the false alarm only. Fix: make the write unconditional or the
failure an exception so a red gate never leaves a half-staged tree.

### 133. `CH02:m033e053p0` fails its first attempt on every replay, then passes the F3 rerun

**RESOLVED 2026-10-11.** Route 1 ev053 is a ROM sight trainer with
`MOVEMENT_TYPE_FACE_DOWN_AND_LEFT`: when the walk arrived while it faced west, the
touch bump started nothing (sight only checks on a finished step, along the
trainer's facing). `generic_beat` now presses A on a sight trainer whose touch
starts nothing (`_handle_trigger(talk_if_unseen=)`); CH06 gen 465/465 with it.

Seen in both CH05 gen replays on 2026-10-09/10 (ROMs `31b375bc`, `51fc4687`): "map033/ev053/p0:
stepping into the event (trigger='event_touch') started no script", then green on the rerun, so the
tally reads 306/306. Twice in a row is not a flake: something about the first approach (state left by
the beat before, or the step timing) differs from the retry. Find what, and fix the beat or the
walk -- a rerun that always rescues it hides a real ordering or timing bug.

### 134. DONE 2026-10-13 -- Multi-step sideways staircases only half-crossed on ROM

**DONE 2026-10-13** (operator retest on the CH06 walk: good). CH06 walk: on Nowtoch Park's 2-wide
staircase (Map14002 (24..25, 17..20)) only the north lane climbed; the south lane stopped halfway.
The engine moves one diagonal per press, but Uranium stair events push k diagonals per touch (k = 2
for 156 of 228 corpus events, 4 for Map216's four), so a 2x2 staircase lacked the two cells
between its event cells (92 cells across 19 maps). `stairs.lane_cells` now fills them in via
`stair_cell_sides`; `stair_beat` presses k + 1 times; both stair-approach resolvers skip stair
neighbours. Why nothing caught it: beat_gen *refused* the staircase (cell_error, in `REFUSED`) in
CH06 and in CH02 (Route 1 (52..53, 41..44)), so no beat ever crossed it, and both reviews were
approved with that row listed. Pinned: `tests/test_stairs.py` simulates the engine's press rule
over every RMXP crossing; `tests/test_chapters_gen_stairs.py` forbids refused stair rows.

### 135. DONE 2026-10-13 -- NPCs that RMXP blanks later stayed visible forever (Fufufu blocks the gym door)

**DONE 2026-10-13** (operator retest on the CH06 walk: good). CH06 walk: after the Maria key scene,
Fufufu (Map040 EV018, Gym Plaza piece 14001) stood beside the path, then reappeared mute in the
gym doorway on every reload. The scene ends `pbSetSelfSwitch(18,"B",true)`; EV018's selfB page is
blank, so in RMXP he vanishes. Ours emitted him with flag `0`: no hide rule covered "visible at
boot, blanked later by another event's write". `metadata_wiring._can_vanish` (brute force over
page-condition atoms; self switches only vary if a code-123 or `pbSetSelfSwitch` on the map writes
them) now routes such NPCs into the hidden-actor visibility machinery (pool flag, ON_TRANSITION
clause, refresh after guard writes). Slice census: 11 NPCs, incl. Map14000's seven Metro-gated
crowd NPCs, Map019 EV004/005, Map073 EV006. Not caught by the gen suite because it entered the gym
in the same visit, before any reload; a reload-and-check beat would pin it on ROM (not built).

### 136. DONE 2026-10-13 -- Opacity-0 scene host spawned as a mute trainer sprite (Maria scene)

**DONE 2026-10-13** (operator retest on the CH06 walk: good). Map040 EV141 (Gym Plaza, the opacity-0
"Trainer(4)" tripwire that hosts the Maria scene) appeared at (11,10) after the scene, scriptless,
until reload. Uranium's scene runs the door-animation turn routes on "this event" (an authoring
slip, invisible in RMXP); our `hidden_actor_bracket` pass `addobject`ed it with its HGSS_014 sheet.
The pass now skips the spawn for an actor with no visible page whose block only turns it
(`face_*`/`delay_*`, no `set_visible`). Census: only EV141 changes; the seven fade-in actors
(Map032 EV075/076/077, Map035 EV020/021/022, Map14000 EV078) still spawn. **Remainder moved to #138:**
Map032 EV080 plays a "!" on invisible EV075, which spawns Theo's sprite visibly there too -- needs
a spawn-invisible step, not a skip.

### 137. DONE 2026-10-13 -- Playtests can't see whether an object is present -- add an "absent" ROM assertion

**Done as a runner invariant, not a floor kind (operator choice 2026-10-13).** A floor kind would
have needed wiring into five templates plus CH01-CH06 review re-approval, and still only checked
rows the route visits. Instead `playtest/visibility.py` runs after every beat: each spawned object
is mapped back to its RMXP event (staged local-id table, the object's own mapGroup/mapNum), its page
conditions are read from ROM flags/vars via the registry, and a blank or absent live page fails the
beat with a screenshot. Skips: field locked (mid-scene), native berry trees (plant script draws over
a blank page), events with an unreadable condition (script/unminted switch or var; logged). Proven
live: flipping Fufufu's SSB in RAM without the refresh is reported. First runs caught Map068 EV018,
an Essentials hidden item (blank-page `pbItemBall`) emitted as a visible ball -- now the native
`hidden_item` bg event (9 corpus-wide, 1 in slice). CH06 gen 466/466 with the check on.

Original framing:


The suite never grades object presence, so #135 and #136 passed 466/466. A blank-graphic page
(or no active page) means "not on the map" in RMXP, but the beats covering such rows grade only
`trigger`/`completes` -- an empty page passes whether the object is gone or standing there as a
mute sprite (CH06 #144/#160 on Fufufu, the latter right after the reload that put him back in the
doorway). The converter rules that fixed #135/#136 encode our model of RMXP visibility; this would
check the ROM instead, catching detection misses, refresh/local-id wiring slips, stray `addobject`s
and regressions alike. Shape: a floor assertion kind for blank-graphic pages, emitted by beat_gen,
checked in playtest by confirming no spawned object carries that local id once the beat's state is
reached (the beat stands beside the cell, so the camera-range limit on `gObjectEvents` doesn't
bite). Limit: only checked where the route visits after the state flips.
Context: 2026-10-13 also widened `writable_self_switches` to `@event_id` and loop-variable
`pbSetSelfSwitch` calls (no slice change; those forms are outside CH01-CH06).

## Accepted deferrals (not currently planned — listed so they aren't re-litigated)

- **Reflection narrow-scan** — tried and reverted 2026-07-07 (user: "not
  actually a fix"). Do not re-apply; if pond reflections get revisited it
  needs a different approach than narrowing the engine scan box.
- **new_game.c test harness** — `SLICE1_TODO.md` #5 decision landed (`4b8ca7ce`):
  **keep `FlagSet(FLAG_BADGE03_GET)` indefinitely** (user decision, standing rig,
  not a to-remove obligation). *(Superseded 2026-10-13: the badge-3 set was removed when
  the HM gates took Uranium's badge counts, #121.)* Its Rock-Smash-Geodude companion lines were
  separately disabled 2026-07-21 (rock smash not walkable on current builds) and
  are dead code alongside 3 other DISABLED harness blocks in the same function —
  see Group C cleanup, `reference/guides/engine_gotchas.md` is not the home for
  this, `ROM_TEST_DEV.md`'s "new_game.c debug-harness re-arm technique" section is.

### 125. `chapters.json` credits CH30 with the HM03 Surf grant; the corpus says map 143 (was mis-numbered #69)

*(2026-10-04: renumbered from a second `### 69`, which collided with "A green test run writes synthetic chapter names..." above. References to "#69" meaning this item now read #125; MEMORY.md's 2026-09-01c entry still says #69.)*

Found while building B2 (2026-09-01). `reference/chapters.json`'s CH30 (Amatree
Town, maps 151/170/171/69) carries the note *"the HM03 Surf grant -- the single
largest traversal unlock in the game."* The decoded corpus does not support it:
scanning all **199** decoded maps, `Kernel.pbReceiveItem(::PBItems::HM03)` occurs
on **map 143 only** — events 22 (`'the event'`, 27,46) and 24 (`'theo event2'`,
27,47). Map 143 is not in CH30; it belongs to **CH29** (Route 10 / Anthell, act
A5, visit 1) and **CH31** (Route 10 revisit, act A6, visit 2).

This matters beyond tidiness: it decides which chapter owns the Surf revisit debt
CH05 just acquired (its four `blocked:surf` rows on map 036). Owed to a Route 10
chapter, not to Amatree Town.

**Not fixed here on purpose.** Correcting the factual claim is one thing; deciding
*which* chapter owns a capability grant is a chapter-assignment call (CLAUDE.md
§10, "any decision about Uranium content fidelity"), and CH29-vs-CH31 is a real
choice — the grant sits on a map both chapters contain. Needs the atlas
maintainer. Evidence is recorded in
`reference/frozen/ch05_surf_expectations.json`'s `granting_chapter` block.

## Done

### 150. DONE 2026-10-22 — Remapped seams import one row too few: a black band while the camera is mid-step

Found 2026-10-17 (streaming stage 3, Nowtoch ↔ Route 2). A remapped seam imported the
neighbour's edge `STRIP_DEPTH_NS = 5` rows deep (`EW = 7` columns). Five metatile rows is what a
resting camera shows beyond the player; while the camera is mid-step after a crossing a sixth
row is partly on screen, and it had no art (tilemap word 0, so the backdrop showed). Measured on
the 40→35 crossing: BG3 rows 0–5 of the ring buffer empty, VOFS 41–47 putting up to 7 px of
them at the top of the screen (`output/scratch/seam_rows_probe.py`).

**Fix (2026-10-22, before CH09's Moki E seam, operator-ordered):** the import depth is now
everything the engine copies — `fieldmap.c` `Fill{North,South,West}Connection` copy
`MAP_OFFSET` (7), `FillEastConnection` 8 — so `connection_remap.strip_depth` is N/S/W 7, E 8.
`map_split.derive`'s camera extent (7/5) no longer borrows the strip constants. Evidence: ROM
`bb72ff62` → `91f797fb`; the 40→35 probe now leaves only BG3 rows 0–1 empty, which VOFS
41–48 never shows; tileset 1031 (Route 2) 705 metatiles / 772 tiles after the deeper import
(58 strip metatiles from 40), 40 streamed so free; CH08 gen 500/500 from boot.
**Residual (E/W):** a west neighbour is only copied 7 columns by the engine, so if the camera
shows part of an 8th column mid-step on a west-side crossing it reads the border block, not
black. No remapped E/W seam exists yet; probe it on the first one (CH09, Moki E ↔ Route 3 W).

### 140. DONE 2026-10-22 — Every built map's name popup reads "LITTLEROOT TOWN"

**2026-10-21, operator rulings:**
- **One section per location:** a map takes the section of its nearest self-or-ancestor
  (MapInfos tree) that Uranium flags `ShowArea`.
- **The popup shows only on `ShowArea` maps**, which is Uranium's own rule.
- **Names are what Uranium displays**, in caps.
- **Region-map/Fly coordinates stay zero** until Tandor's region map is converted.
- **`OW_HIDE_REPEAT_MAP_POPUP` stays off.**

Built in `tileset_converter/map_sections.py`.

Seen by the operator on the CH07 walk (2026-10-15). `metadata_wiring.DEFAULT_MAPSEC =
"MAPSEC_LITTLEROOT_TOWN"` is written as `region_map_section` for every slice map. It was a
placeholder from slice S4 and was never replaced, because `map_constants.py` mints a
`MAPSEC_<NAME>` per map but nothing adds those to the engine's
`src/data/region_map/region_map_sections.json`. That file is the build source for
`include/constants/region_map_sections.h` and `region_map_entries.h` (`json_data_rules.mk`).
The popup only shows where `show_map_name` is true, which `MapFile.to_json_dict` sets to
`map_type == MAP_TYPE_TOWN`. That is why it appears "most of the time" rather than always.
`OW_HIDE_REPEAT_MAP_POPUP` is `FALSE`, so connection crossings re-show it even within one
section. Not yet decided:
- one section per Uranium map, or one per location (a town's split pieces and interiors
  sharing one)
- display names from `MapInfos` vs `map_name_overrides.json` (§4.3)
- whether region-map/Fly coordinates are filled now or left zero
- whether to flip `OW_HIDE_REPEAT_MAP_POPUP` (that changes baseline engine behaviour, so ask
  first)

This is the same kind of placeholder as `MUS_LITTLEROOT` on every map (#22).

### 141. DONE 2026-10-22 — Phone-rematch trainers drop their `RegSpeech` line and register without asking

**2026-10-21: BUILT** (operator: yes/no prompt, built from what Emerald uses). `classify_phone_rematch_trainer_battle` now:
- gates on the Pokégear (`FLAG_SYS_POKENAV_GET`), as Uranium does;
- asks the trainer's own question as a `MSGBOX_YESNO` and runs `register_matchcall` only on yes;
- re-offers on a later talk through `IsTrainerRegistered`, as Emerald's Calvin does.

The phone is called POKéPOD in the start menu and the registration line (generated by `game_profile.header` from the game's own message).

Seen by the operator on the CH07 walk (2026-10-15, Map035 EV023 Brent; CH04's Larrie behaves
the same). Uranium's `pbPhoneRegisterBattle(message, …)` (`scripts_dump/133_PScreen_Phone.rb:91`)
shows `message` as a **yes/no** prompt ("Want to trade PokéPod numbers?") and registers only on
yes, then says "Registered {class} {name} in the Poképod." If the player declines, the idle page
(page 2) re-offers registration on every talk. Our phone-rematch classifier
(`conversion_agent/deterministic.py` ~1286–1394) matches the `_I("…")` literal but never captures
it, and its `_RegisterMatchCall` continue script calls `register_matchcall` without asking, so
the player sees only the engine's "Registered … in the POKéNAV" fanfare. Auto-registering was
deliberate (no `FLAG_HAS_MATCH_CALL` gate); losing the line was not. Fixes, smallest first:
- Minimal: emit the line as a `msgbox` before `register_matchcall`, as vanilla does
  (`engine/data/maps/Route102/scripts.inc:38-42`, Calvin).
- Faithful: a `MSGBOX_YESNO` prompt, plus a re-offer on the idle page that checks
  `IsTrainerRegistered` (`Route102/scripts.inc:24-26`). This touches the rematch beats'
  oracle.

Also: the stock text says "POKéNAV", where Uranium's word is "Poképod".

### 31. DONE 2026-10-22 — Give the Pokédex Uranium's real Tandor regional dex

**2026-10-21: BUILT** (`f59d2b43`). Awaiting the walk.

**2026-10-21, operator rulings (they settle the open questions below):**
- **Tandor only.** Stop unlocking National mode. A build check fails loud if a species the
  game hands out has no Tandor number.
- **All 200 Tandor slots are listed.** A species not built yet shows as an unseen slot.
- **The dex UI says TANDOR, not HOENN.** Palettes stay stock.

**User decision 2026-08-11: wanted, not deferred.** The current dex is
National mode with the staged Uranium species grafted onto the end of the
vanilla national list, past `NATIONAL_DEX_PECHARUNT`. That was the minimum fix
to stop caught species being invisible (#see 2026-08-11b, `f3af5820`) and was
taken as an explicit stopgap. Uranium's own dex is the **Tandor regional dex**,
and that's what the ROM should show: Tandor numbering, Tandor ordering, no
vanilla species interleaved.

**The source data is already parsed.** `pbs_converter/pokemon.py:259
parse_regionals` reads `Data/regionals.dat` and returns
`out[0][species_id]` = the Tandor dex number for that species (0 = no entry);
Uranium has exactly one regional dex, 202 species-slots including the ID-0
placeholder. Nothing currently consumes it.

**The engine lever** is `RegionalToNationalOrder` (`src/pokemon.c:5261`), which
indexes `sHoennToNationalOrder` (`src/pokemon.c:392`, sized
`HOENN_DEX_COUNT - 1`); `CreatePokedexList` walks `i < REGIONAL_DEX_COUNT` and
maps through it (`src/pokedex.c:2194-2218`), and `NationalToRegionalOrder`
(`:5222`) is the inverse. So a Tandor dex means generating a
Tandor→national order table plus its count, in place of the Hoenn one, behind
the usual sentinel-fenced generated-header hook.

**Open questions to settle before building it:**
- Whether to keep National mode available at all as a second dex mode (vanilla
  species are still in the ROM and catchable in principle), or make Tandor the
  only dex and revert the `special(EnableNationalPokedex)` from the grant at
  `transpiler.py:2634`. Reverting it is only safe once regional covers every
  staged species — otherwise this bug returns.
- The dex UI names the mode "HOENN" in several strings and uses
  `gPokedexBgHoenn_Pal` vs `gPokedexBgNational_Pal` (`src/pokedex.c:2154`);
  decide whether to retheme or leave the vanilla labels.
- Only 24 species are staged today, so a full Tandor table will have holes
  until the species set grows. Needs a rule for unstaged entries — most likely
  the same fail-loud-or-omit choice the rest of the pipeline makes, not a
  silent gap.

**Done looks like:** the in-game dex lists Tandor species in Tandor order with
Tandor numbers, generated from `regionals.dat` rather than hand-authored, and
a caught species appears at its real Uranium dex number.

### 144. DONE 2026-10-22 — `var_text` can't predict dex-count dialogue (`\r\v[2]\c[0]`, two `\v` per line)

**2026-10-21: BUILT** (awaiting suite regeneration). A new floor kind, `count_text`, covers lines whose `\v[N]` are dex counts or a reward-ladder threshold (`beat_floor.var_text.count_text_source`). A branch arm also sees its enclosing scopes' scripts (`walk._ancestor_scripts`), but only for this rule. The harness predicts each number on its own:
- the dex counts from `Emulator.pokedex_counts`;
- the threshold from the parsed `PROFREWARDS` table at the ROM's var 22.

Map050 EV027 p0 and EV005 p5 b0/b2/b30 are no longer refused.

Found 2026-10-15 (CH08). The transpiler now emits the lab's "seen \v[2] / caught \v[3]" lines with
`ScriptGetPokedexInfo` + `buffernumberstring`, but the floor's `beat_floor/var_text.py` only
handles ONE `\v[N]` per line written by a script that reads game variables. These lines have
two, read `$Trainer.pokedexSeen/Owned`, and wrap the count in the `\r…\c[0]` tint. So
Map050 EV027 p0 and EV005 p5 b0/b2/b30 are refused `#109: text_unnormalizable`; the scene still
runs on the ROM through its claimed arm. The fix is a dex-count pseudo-input (read via
`Emulator.pokedex_counts`), multi-`\v` lines, and the transpiler's `\r` stripping mirrored.

### 146. DONE 2026-10-22 — `_emit_give_item_idiom` branches on `VAR_RESULT` after `giveitem`, which is the pocket id

**2026-10-21: FIXED.** The give-item idiom branches on `VAR_0x8007 == TRUE` (`f59d2b43`).

Found 2026-10-15 by the CH08 transpiler work: `giveitem` (`engine/asm/macros/event.inc:2122`)
runs `Std_ObtainItem` (`engine/data/scripts/obtain_item.inc:4-9`), which leaves the success flag in
`VAR_0x8007` and the pocket in `VAR_RESULT`. The existing item-grant idiom tests
`VAR_RESULT != 0`, which is true for any pocket, so a full-bag arm can never be taken on the ROM.
Harmless while full-bag arms are `harness:full_bag` (never walked); wrong once one is. Fix the
idiom to read `VAR_0x8007`, as the reward-ladder code does.

### 147. DONE 2026-10-22 — One-shot page arms are recorded as `unselected_arm` though they ran

**2026-10-21: BUILT** (awaiting suite regeneration). New status `walked_with_page` (`chapter_manifest.schema.ELSEWHERE_STATUSES`, `beat_gen.plan.Elsewhere`); `facing.fold_one_shot_arms` uses it. Only CH08's Moki EV078 arms change.

Ruled 2026-10-15 (CH08): `beat_gen` folds the arms of a one-shot page whose trunk another beat
fires (`facing.fold_one_shot_arms`; Moki EV078's position loops, walked by `m032e078_warp`) into
ELSEWHERE as `unselected_arm`, with a detail saying they ran inside that single firing. The status
word is wrong for them; it was reused because adding one is a `chapter_manifest` vocabulary change
(`schema.ELSEWHERE_STATUSES`). Add a dedicated status (e.g. `walked_with_page`) when that file is
next touched.

### 63. DONE 2026-10-22 — CH04 owes two negative beats — `map035/ev014/p1` and `map035/ev017/p1`

**2026-10-21: RETIRED (operator).** The p1 rows are each rock's empty post-smash page. `beat_gen.select.cleared_obstacle_pages` files them `empty_page`, not `blocked`; the rock's own page keeps the negative beat. Awaiting suite regeneration.

Surfaced by slice 2's new `blocked_missed_assertion` checker rule, which is the
first thing in the repo able to see this class at all. Both rows are the
*cleared* pages of the two Route 2 boulders whose approach the player can already
reach unaided, so a negative beat is writable today: walk up, press A, assert the
refusal. `ev014/p0` and `ev017/p0` already carry `negative_beat: "B6"`; their p1
siblings carry none.

Not urgent and not a defect — CH04 passed its §9 gate and the rule is explicitly a
missed-opportunity warning, not an error. Right time to spend it is CH07A, the
Rock Smash revisit that walks map 35 again. *(2026-10-15: CH07 was the chapter that walked map
35 again, and it smashed no rock. CH07A is now folded into CH08, the first chapter with a
real smash.)* Until then `check --chapter CH04`
reports 2 warnings of this kind by design; do not silence them.

### 152. DONE 2026-10-21 — Two small Uranium leftovers in tracked engine code (I3 S7 audit)

**DONE 2026-10-21 (intermission).**
- `opponents.h` falls back to stock's 855/864, and the stale comment is gone.
- The pointers file names `gObjectEventGraphicsInfo_Rpg2gbaPlayerNormal` / `...FieldMove`. `sprite_emit` `#define`s them in the generated decls header: to the game's structs when the player is staged, and to stock Brendan in the stub.
- The rebuilt ROM is byte-identical (`a593c317`).

Filed 2026-10-21 at the I3 gate. The S7 audit of `git diff 80cdfce2 HEAD -- engine/` found
nothing hand-typed that the build actually uses, apart from S3's ruled ability-behaviour C.
Two tidy-ups remain, neither of which changes the Uranium build:
- `include/constants/opponents.h`: the `#else` fallback for `TRAINERS_COUNT_EMERALD` (1189 /
  1280) is stock + Uranium's 331 trainers. The generated `rpg2gba_sizes.gen.h` always
  overrides it, but a stock build should fall back to stock values. Its stale
  "854 + 331 = 1185" comment goes too.
- `src/data/object_events/object_event_graphics_info_pointers.h`: the Brendan rows name
  `gObjectEventGraphicsInfo_UraniumPlayerNormal` / `...FieldMove` directly. A neutral
  `Rpg2gba*` alias defined in the generated decls header would keep game names out of
  the engine.

### 96. DONE 2026-10-21 — Pokémon Centers heal but never become the respawn point

**DONE 2026-10-21 (intermission close-out).** Built by `6df46066`:
- `pbs_converter/heal_locations.py` generates `HEAL_LOCATION_*`;
- `pbSetPokemonCenter` emits `setrespawn`;
- `new_game.c` sets the initial anchor (`HEAL_LOCATION_URANIUM_START`).
The white-out beats in the generated suites (`whiteout_fork_beat` in ch01/ch03/ch06) assert each anchor, and every CH08 run from boot replays them green.

**Found 2026-09-11 while walking `reference/archive/REDERIVATION_PLAN.md` §14's Q1. Found ONCE BEFORE and
never filed** — `src/rpg2gba/playtest/chapters/ch03.py:83-88` finding #7 recorded it at
chapter scope (*"No healing-location/respawn metadata write anywhere — `grep -i respawn`
over the Center's whole compiled output: zero hits"*) and it never left that file. This
entry exists so it cannot happen a third time.

The `heal` effect converts, so the nurse heals the party. What does **not** convert is the
respawn anchor:

- `src/rpg2gba/conversion_agent/deterministic.py:91` classifies `Kernel.pbSetPokemonCenter`
  as **STRIP**, justified by *"respawn is wired from metadata, not events."*
  **That wiring does not exist.**
- `src/rpg2gba/pbs_converter/metadata.py:13` parses Uranium's `HealingSpot` field into
  `map_metadata.json` and stops there.
- `grep -rn "HEAL_LOCATION" src/` → **zero hits**. Nothing in the pipeline touches
  `engine/src/data/heal_locations.json`, which is still 100% stock Hoenn/Kanto — so no
  `HEAL_LOCATION_*` constant exists for any Uranium Center even if a script emitted one.
- Uranium side: `reference/scripts_dump/101__PField_Field.rb:1666-1676` stamps
  map/x/y/direction into one global "last Center wins" slot.

**Full native analog exists — no custom C** (§4.7 reverse gate, verified):
`setrespawn <HEAL_LOCATION_*>` (`engine/asm/macros/event.inc:1455-1459`) →
`ScrCmd_setrespawn` → `SetLastHealLocationWarp` with `SCREFF_SAVE`
(`engine/src/scrcmd.c:2699-2706`). Struct and accessors at `engine/include/heal_location.h`.

Work: mint a `HEAL_LOCATION_*` entry per Uranium Center into
`engine/src/data/heal_locations.json` (it generates `include/constants/heal_locations.h`),
and emit `setrespawn` from the nurse idiom instead of stripping the call. Currently blocks
manifest row `map068/ev001/p0` (CH03, Kevlar's Center) and is item 3 of
`reference/archive/REDERIVATION_PLAN.md` §14.1's ten.

**Why a §9 boot walk never caught it:** a missing respawn anchor is only observable if the
walk white-outs, and no beat does. Gate-passed chapters ship this.

**RULED IN 2026-09-12 (`reference/archive/REDERIVATION_PLAN.md` §14.7): build the generic emitter, not two
hand-minted constants.** The derivation source is already parsed and unconsumed — measured 22
maps carry `HealingSpot`, all Center interiors pointing at outdoor coords (maps 49/50 →
`[32,28,32]` Moki, 68 → `[31,20,13]` Kevlar), a 1:1 fit for a `heal_locations.json` entry.
66 `pbSetPokemonCenter` call sites collapse onto those 22 locations; this branch touches two.
`reference/recon/uranium_script_calls.md:71`'s STRIP ruling is corrected in place — its premise
("the agent can't derive the constant from the event JSON") was true of the LLM and false of
the transpiler.

**SECOND BUG, same anchor, worse blast radius (found 2026-09-12):** the *initial* anchor is
never set either, so a white-out today lands in **vanilla Petalburg City**. The spawn override
(`engine/src/new_game.c:172-208`) sets a warp destination and no heal location; our boot path
skips the intro, so no script runs `setrespawn`; `ClearSav1` zeroes `lastHealLocation`, and
`SetWarpDestinationToLastHealLocation` (`overworld.c:758-763`) reads zero as mapGroup 0 /
mapNum 0 = `MAP_PETALBURG_CITY` (`constants/map_groups.h:15`). Fix belongs in the same fenced
`new_game.c` block as the spawn override.

**Standing precedent set by the same ruling:** a white-out beat goes in the chapter AFTER the
one that establishes or changes an anchor — initial Moki anchor (CH01) is asserted in **CH02**,
the Kevlar Center anchor (CH03) in **CH04**, and every future chapter with a Center owes its
successor the same. CH02's beat doubles as the regression test for the Petalburg bug and is
expected to FAIL until the `new_game.c` fix lands.

### 20. DONE 2026-10-21 — Map050 EV026 — dead lab PC, one-line fix, never boot-walked

**DONE 2026-10-21 (intermission close-out).** The transpiler now emits the lab PC: `goto(EventScript_PC)` under the facing-north check (`Map050.pory`). CH01's beats `m050e026p0` and `m050e026p0_face_north_east_west` exercise it on every run from boot.

Real, unreported bug found while compiling `SLICE1_EVENTS.md` (§11.11), not
from a device walk. The lab PC's `pbPokeCenterPC` call sits inside an
unhandled code-111 character-facing conditional, so it was never emitted —
the event compiles to a bg event whose body is just `lock`/`release`/`end`.
Interacting with the PC does nothing. Map048 EV004's PC works because its
call isn't wrapped in a conditional. Fix: emit `goto(EventScript_PC)` for
this event, same as Map048 EV004 (`data/scripts/pc.inc`, vanilla). One line,
needs a build and a boot-walk to confirm. Migrated from
`SLICE1_EVENTS.md` §11.11, 2026-08-04.

### 148. DONE 2026-10-18 — 15 maps exceed the engine's map-data buffer and load as border only

Found 2026-10-17 (streaming stage 2, `reference/streaming_prototype_plan.md` "Stage 2 progress").
`InitMapLayoutData` (`engine/src/fieldmap.c:184`) silently skips loading a map whose backup grid
`(w+15)*(h+14)` exceeds `MAX_MAP_DATA_SIZE` (10240); the player sees only the border pattern.
Over: 094 (27060), 187, 143, 117, 106, 184, 133, 008, 132, 193, 074, 059, 213, 127, 121, 022
(`output/scratch/map_data_size.py`). `map_split.derive` already respects the limit for split
pieces, and `streaming.check_streamed_layout` now fails loud for streamed maps. Nothing guards
the Map Walker `full` corpus or a future chapter map. The fixes are splitting, or raising the
buffer (2 bytes/cell of EWRAM; 094 needs about 33 KB more, which isn't free). Due before the
first chapter that reaches one of these maps. A general fail-loud check at layout emit should
come first.

**Resolved 2026-10-18** (operator: no splitting): the engine keeps a 128x64 window of an
oversized map's grid and rebuilds cells outside it on demand (`fieldmap.h` "windowed backup
grid"; `reference/streaming_prototype_plan.md` "Stage 4: maps over the map-data buffer"). Route 3
(59): 0 screen-check mismatches, 0 window-vs-layout mismatches. The `streaming` check that
rejected oversized maps is gone.

### 44. DONE 2026-10-16 — CH01/CH03 flavor interiors shipped untested — DEFERRED to the end of Act 1

*(2026-10-04: still deferred. `moki.py` / `kevlar.py` were deleted with the hand suites 2026-10-03 and the suites are now generated by `beat_gen`, so the remediation described below is stale in form; re-check whether the generated CH01/CH03 suites cover the listed flavour-interior rows before actioning. Not verified here. Moved back from the Done section.)*

*(2026-10-15, CH08 open: **verified: superseded by the generated suites; move to Done on CH08's
gate.**
- `chapters_gen/ch01.py` has talk/arm beats for every listed row on maps 64, 65 and 89 (89's EV002
  touch got a warp beat). The leftovers are the sw125 p1 twins, which are `unreachable`.
- `ch03.py` covers Map073's NPCs. The residuals are dispositioned: EV001 p0/b1 `refused:#109`;
  EV005 p1/p2 `NEVER_FIRES` (sw100 is never written on the route, which is the reachability ruling
  asked for below); the rest are `unreachable`.

No CH08 work is owed.)*

*Filed 2026-08-25 from the §43(b) re-sweep of CH01–CH03 under the new
observability rule. **Deferred by the operator until the first chapter group
(Act 1, CH01–CH06) is complete** — do not action before CH06's §9 gate passes.*

**Deferral rationale.** Neither chapter is the frontier, both already hold a
passed §9 gate, and Act 2 opens with revisit chapters that re-enter this exact
content — CH08 is Moki Town (revisit), the first test of the revisit model, and
is the natural place CH01's interiors get walked again. Doing the remediation
then folds it into work already scheduled instead of reopening two closed gates
mid-Act-1.

**The sweep could not be mechanical.** §43(b) assumed a trigger-vs-disposition
cross-reference. There is nothing to cross-reference: `reference/manifests/`
holds only `CH04.*` — CH01–CH03 predate the manifest system and have **no
manifest and no dispositions file**. The assessment was made against the prose
specs and the playtest scenarios instead. Corollary worth carrying: the checker
is structurally blind to every pre-CH04 chapter, so any future corpus-wide
disposition rule change has the same hole.

**Findings — 12 rows would flip to `beat:`, 3 need a human ruling, 0 are
incidentally covered by the existing scenarios.**

- **CH02 is clean.** Its beat table already treats flavor NPCs as first-class
  beats regardless of state writes (B3 Chyinmunk sprite, B4 hint NPC, B34
  brother NPC, B35 sign) — exactly the rows the old rule would have discarded.
  Nothing to do. Not a coincidence worth ignoring: the author's instinct was
  the new rule two chapters early.
- **CH01 — 8 flips.** `01-moki.md` labels Map064, Map065 and Map089 "Flavor
  interior, no chain beats", and `moki.py` never enters any of them. Map064:
  ev001/p0 and ev002/p0 (talk-trigger dialogue NPCs), plus the Chyinmunk
  (`pbCallBub` emote + cry SE + line — literally the Barewl pattern §43(b)
  flipped). Map065: ev001/p0, ev002/p0. Map089: EV003, EV004, EV005, EV006,
  EV007 (all talk-trigger flavor lines). The `p1` twins of the Map064/065 NPCs
  stay cosmetic — switch-125-gated postgame, unreachable in-chapter.
- **CH03 — 4 flips.** `kevlar.py`'s B16 does door-in/door-out warp checks on
  Maury's apartment and the couple's house and never talks to anyone inside.
  Map073: EV005/p0 (Maury, "have you gotten my wallet back?"), EV010 and EV011
  (the couple), and **EV008, a boutique-interior NPC absent from the beat table
  entirely**.
- **Needs a human ruling before beats are written, because it sets the count:**
  Map089 EV002 (touch-trigger, `code 209/509` picture display, no text — cannot
  tell from codes whether the player observes anything) and Maury's EV005 pages
  1 and 2 (self-switch-gated variants whose in-chapter reachability is unclear).

**Remediation when it comes due:** ~5 new beats in `moki.py` (three interiors,
collapsing the postgame-gated twins) and ~3–5 in `kevlar.py` (Map073's
interiors), same shape as CH04's B12–B14 — enter, talk, assert the box opens and
closes. Update `01-moki.md` / `03-kevlar-town.md` beat tables to match; the
"flavor interior, no chain beats" labels are what caused this and should go.

**Caveat on provenance:** the row list is a sub-agent's judgment read of the
deserialized event data, not a row-by-row human verification. Re-confirm each
row against `output/uranium-build/maps/Map0{64,65,73,89}.json` when the work is
picked up.

*Closed 2026-10-16 (A1→A2 intermission): CH08's §9 gate passed; the generated suites cover these interiors, as verified 2026-10-15.*

### 50. DONE 2026-10-16 — `isRockSmashSoftlocked` is an unrecognized script head on map 32

Migrated from `CH04_TODO.md`. Last unrecognized head in CH01's map-32 fixture;
out of CH04's scope but filed so it is not rediscovered. Rule it (or its
containing page) when CH01's interiors or the Rock Smash grant chapter is next
touched.

*(2026-10-15, CH08 open: **effectively resolved; move to Done on CH08's gate.**
Uranium's helper (`scripts_dump/221_Extra_Scripts.rb:796-812`) returns false unless
Nuzlocke **and** randomizer are both on, so its self-smash arm can never fire here. The
rock idiom (`transpiler.py` ~3600-3640) emits `goto(EventScript_RockSmash)` and drops
both arms, deliberately and with a comment, on all 14 built rocks (maps 32/33/35). The
standalone strip `_emit_rock_smash_softlocked_strip` (`transpiler.py:419-432`, 3546-3578)
covers any non-rock site. No `strip_list.json` entry is needed: that file holds
whole-artifact strips, and this is an unreachable branch.)*

*Closed 2026-10-16 (A1→A2 intermission): CH08's §9 gate passed (walk 2026-10-16), which was the stated trigger.*

### 69. DONE 2026-10-16 — A green test run writes synthetic chapter names into a tracked reference file

`run_chapter` records the rule-set version of every chapter that passes into
`reference/playtest_rule_versions.json`, and the runner's unit tests pass with
synthetic chapters (`t1`, `t2`, `t9`, and now slice 4's `v4path`, `v4noplan`,
...). Those names are already committed in that file from earlier runs, and
every `pytest tests/test_runner*.py` adds any new ones, so the file shows up
dirty after a plain test run and `rules-lag` reports chapters that do not
exist.

Cosmetic, but it makes `git status` lie after a test run, which is the kind of
noise that trains an operator to ignore a dirty tree. The fix is for the tests
to point the recorder at a `tmp_path` (the runner would need to accept the
state path, or the tests would need to monkeypatch `rules._STATE_PATH`), plus a
one-time cleanup of the synthetic names already committed.

*Found 2026-08-30 building slice 4; the leak itself predates it.*

*Closed 2026-10-16 with #70: same fix.*

### 70. DONE 2026-10-16 — The test suite writes into tracked `reference/playtest_rule_versions.json`

Running `pytest` mutates a committed §4.3-adjacent reference file. Observed
2026-09-01: a full suite run added a `"CH03": 2` key to the working tree with no
test asking for it, and the file already carries `kevlar3`, `t1`, `t2`, `t4`,
`t5`, `t9`, `t10`, `t12`, `t13`, `v4conformance`, `v4noplan`, `v4offplan`,
`v4path`, `v4perbeat`, `v4v1fields` — every one of them a test fixture's chapter
name that leaked in the same way and was then committed.

Some test calls `rules.record_chapter_version` (or drives a runner that does)
against the real default path instead of a `tmp_path`; `tests/test_observed_beats.py`'s
`run_chapter` fixture is the confirmed one. It used to be merely untidy, because
fixture names like `t1` and `v4path` could never collide with a real chapter.
**The #66 rename made it worse:** fixtures now name themselves `CH03` to match
the production convention, so a leaked write lands *on a real chapter's key* and
silently overwrites its recorded rule version instead of sitting beside it as
obvious junk. That turns a cosmetic leak into a data-corruption path, and it is
the reason this is filed rather than tolerated further. The file cannot be
trusted as a record of which chapters were gated under which rule version, which
is the one thing it is for.

**Remediation:** find the writer that misses the `tmp_path` fixture, pin the
default path behind a fixture that fails if a test touches it, and delete the 15
leaked fixture keys in the same commit.

*Found 2026-09-01 while migrating the file's keys for #66.*

*Closed 2026-10-16 (A1→A2 intermission): `run_chapter` now resolves its default `rule_versions_path` at call time; `tests/conftest.py` points `rules.DEFAULT_RECORDED_VERSIONS_PATH` at a per-test temp file and fails any test that still writes the tracked file. The 15 leaked fixture keys were deleted.*

### 124. DONE 2026-10-04 — The manifest layer is still keyed to the deleted hand suites — re-key before CH06

The hand suites were deleted 2026-10-03 (operator: remove now, re-key later).
Everything built around their beat names still is. Measured that day with the
loaders pointed at the generated suites, `chapter_manifest check` (already red
on the generator backlog) gains:

- **`derived_verdict_mismatch`** CH01 79 / CH02 38 / CH03 63 / CH05 3 — the
  `CHnn.derived.json` sidecars record hand names (`beat:B5`), the checker now
  derives generated ones (`beat:m032e003`). Clerical: regenerate the sidecars.
- **`unregistered_beat`** CH04 11 / CH05 21 (warnings) — ~32 hand-affirmed
  `beat:Bn` verdicts in `CHnn.dispositions.json` name beats that no longer
  exist. Needs a ruling on rewriting affirmed entries.
- **`floor_uncovered`** CH01 96 / CH02 16 / CH03 39 / CH04 6 / CH05 7 — the
  checker's ⊇-floor rule disagrees with the C9 grader. Part is the grader's
  ruling 7 (audio/visual/displacement ungraded); part is rows the generated
  suites don't claim in that chapter (random talk arms, stacked exits,
  boundary warps). Not root-caused.
- **`route_order`** CH05 27 — generated CH05 checked against the hand route
  plan `reference/routes/CH05.route.json` (#120's other face).

Runtime face of the same gap: `playtest.chapter.resolved_trigger_scripts`
matches inherited beat names against the predecessor's `beat:Bn`
dispositions, so for a generated chapter it resolves **nothing** (it already
did on the ROM-green gen walks; the flip changed nothing). The route solver
and the walk oracle therefore get no inherited-trigger exemption. Keying it
on inherited beats' `rows=` instead is the fix, but it changes the solver's
input and so the generated modules — regenerate and re-review on the diff.
Its CH05 test was deleted with the hand suites. **To close:** all of the
above, before CH06's `chapter_manifest check` is relied on.

*(2026-10-04, re-measured on the `ch06-nowtoch-city` branch — `check` also
carried `undispositioned` 261/42/88/6/4 and `derived_unaffirmed` 12/34/8/30/4,
which this item had not counted. Operator rulings the same day:* **(R1) residue
— emit + derive:** `beat_gen` emits committed per-row `ELSEWHERE`/`REFUSED`
dicts into each generated module, derivation turns them into clerical sidecar
verdicts (no hand entries). **(R2) a generator refusal is a WARNING with a
count** in `check`, not an error. **(R3) the floor rule applies the grader's
rulings 7/9/10/19 through one shared function**, still linting every claimed
row; graded gaps error, generator-only partials warn. **(R4) the CH04/CH05
affirmed `beat:Bn` entries are deleted**; the sidecar derives the generated
verdict. *Done so far: sidecars regenerated (`derived_verdict_mismatch` → 0,
`undispositioned` → 136/28/33/3/0, manifests byte-identical); `beat:Bn` entries
dropped (CH04 40→29, CH05 25→4); `route_model` returns None for a gen suite
(CH05 `route_order` → unenforced warning); `resolved_trigger_scripts` keyed on
inherited beats' `rows=`. Open: R1, R2, R3, then regenerate CH01–CH05 (the
trigger-script change moves solver input) and re-review the diff.)*

*(2026-10-04, later — R1–R4 BUILT.* `beat_gen/emit.py` emits `ELSEWHERE`/
`REFUSED`; new verdict heads `elsewhere:`/`refused:` (`schema.py`), loaded by
`chapter_manifest/generator_status.py`, derived at lowest precedence (0 existing
sidecar entries changed, only added) and rejected if hand-authored
(`dispositions.GENERATOR_ONLY_VERDICTS`); `generator_refused` warning + per-chapter
count. Floor rule: `coverage.graded_gaps`/`is_boundary_claim` shared by checker
and grader, plus `inherited_page_trigger` (an arm inherits its page beat's
declared trigger — fixed CH02 `map033/ev023/p1/b0`). CH01–CH05 regenerated:
**pure additions** (the two dicts), no beat moved, so the trigger-script re-key
changed no walk. `check` now: `floor_uncovered`, `derived_verdict_mismatch`,
`route_order`, `unregistered_beat` all **0**; `generator_refused` warnings
46/10/5/4/0. **Left (operator): `derived_unaffirmed` 12/34/8/30/4** (`blocked:`
proposals — `python -m rpg2gba.chapter_manifest affirm`, review in
`output/manifests/CHnn.blocked_review.md`) **and 19 CH01 `needs_citation` rows**
(derivation rule 1; e.g. the rival battle `map050/ev019/p0`, claimed by a
generated beat). Suite two halves 2315 + 2498 passed / 17 skipped.)*

*(CLOSED 2026-10-04 on `ch06-nowtoch-city`, commits `aa836e9f`, `ac9292dd` and the
arms-inherit commit.) Two further operator rulings the same day: **(R5)** on a row
owing a citation, the generator's verdict (its beat claim or ELSEWHERE/REFUSED
record) is the citation (`derivation._generator_cited_entry`); **(R6)** a
branch arm's `blocked:` proposal identical to its parent page's HAND-affirmed
verdict is clerical (narrow §15.7 carve-out) — accepted all 88. **`chapter_manifest
check` reports 0 errors on CH01–CH05** (warnings only: `generator_refused`
61/10/5/4/0, `approach_model_unenforced`, `archetype_conformance`,
`boundary_unclaimed`, the two `*_unenforced` chapter notes).*


- **#58 — Map 183 "Rochfale Town" STRIP-listed** (2026-09-17, `c8088f23`). Verified
  unreachable (no incoming warps/connections/script transfers; map 212's variable warps
  only target 212). An orphaned duplicate of map 12, painted against `Outside.png`;
  removed from CH14 and moved to `unbound_maps`, along with map 124 "Gym3" (CH19).

- **#1 — the old external pokeemerald-expansion clone is DELETED** (2026-09-07,
  operator-run `rm -rf`, closing repo audit Q5). Q5's recorded answer was
  "keep, rename" on the rationale that *upstream stays available for reference
  and diffing* — **that rationale did not survive checking, and the operator
  overrode it.** Nothing unique lived in the clone: the pristine baseline is
  already commit `80cdfce2` in this repo (verified by blob hash, 29,958 of
  29,961 files identical to upstream `21c24202`); upstream history and the
  `rh-hideout` remote are one `git clone` away; the three dirty C files were
  already carried into `engine/` at import; and the three dirty data files were
  pre-cutover *in-place assembler edits* (`.include` hooks, a `gMapGroup_Uranium`
  registration for a 3-map slice) — fossils of the practice the 2026-06-19
  include-hooks change abolished. 589 MB reclaimed, and the decoy at the path
  that caused the 2026-08-17 fabricated-blocker session is gone.
  **Fallout fixed in the same change:** `render_player_compare.py`,
  `pixel_grid_analysis.py` and `render_pc_exterior_compare.py` hardcoded that
  path and are repointed at `engine/`; `CLAUDE.md` §3, `MEMORY.md` and
  `reference/guides/pokeemerald_struct_shapes.md` updated.
  **Found while verifying:** `80cdfce2` is *not* a pristine baseline — the
  import came from a dirty tree and three files (`intro.c`, `new_game.c`,
  `new_game.h`, 33 lines) carry custom edits below it, invisible to
  `git diff 80cdfce2 HEAD`. They are sentinel-fenced, so grep finds them.
  Recorded in `CLAUDE.md` §3 and `engine/RPG2GBA_VENDOR.md`.

- **#66 — an atlas chapter id now names its own playtest module** (2026-09-01,
  `CH05_DECISIONS.md` E1). The proposed fix was a `playtest_module` field in
  `reference/chapters.json`; the operator's answer dissolved the field instead
  of adding it — *"should they be named by place? why aren't they named by the
  chapters"*. The four modules were renamed to their chapter ids
  (`moki.py`->`ch01.py`, `route1.py`->`ch02.py`, `kevlar.py`->`ch03.py`,
  `route2.py`->`ch04.py`), so the mapping is the name and there is nothing left
  to record. The old names were an accident of order: CH01-CH03 were written
  before `chapters.json` and the atlas ids existed.

  **`ChapterBuilder`'s name string moved with the filename** (`"moki"` ->
  `"CH01"`), because renaming only the file would have left
  `load_chapter("ch01").name == "moki"` — the same mapping problem one layer
  down rather than gone. That changed the beat-qualification prefixes
  (`moki:B1` -> `CH01:B1`), the observed-beats filenames
  (`observed_beats/kevlar.json` -> `CH03.json`), the contact-sheet stems, and
  the keys of `reference/playtest_rule_versions.json` (migrated in the same
  commit; the four real chapters keep their recorded versions).
  `load_chapter` lowercases its argument, so an atlas id passes through
  verbatim from `chapters.json` and the filesystem still gets a conventional
  lowercase module name.

  **`--module` survives as an override, not a requirement.**
  `routing/__main__.py` defaults it to the chapter id. It is still a separate
  option, and `RoutePlan.chapter_module` is still recorded on every plan,
  because `divergence.load_plan_index_for_module` deliberately joins on the
  recorded value rather than on the naming convention — a convention that holds
  today is not the same as a binding the artifact carries, and the revisit
  chapters (CH07A) are the case where the two will part company.


- **B2 — `blocked:surf` is derived, not asked for** (2026-09-01, CH05
  prerequisite — `CH05_DECISIONS.md` B2, "option 1, but derived from the route
  finder not from you asking a question").

  **The engine already worked; the entry point was switched off.** `surf` has
  been a first-class capability since slice 2 —
  `traversal/capabilities.py`'s `_TERRAIN_TAG_CAPABILITY` maps terrain tags 5,
  7 and 17 to `Capability.SURF` — and the terrain-obstacle route inverts the
  event route correctly (water reads as collision; holding Surf flips it
  passable). What was missing was one table entry:
  `_CHAPTER_MAP_START_CELLS` held CH04 only, so
  `_build_reachability_context` returned `None` for CH05 and **no** row on
  either map could carry a terrain-gated capability.

  **The start cells are derived, not typed.** Each CH05 map is entered by
  exactly one code-201 transfer, so its arrival cell is a fact about the data:
  `Map035` ev001 (20,33) → map 36 **(17,39)**; `Map036` ev002 (17,4) → map 37
  **(16,26)**. Both reproduced with `extract_warp_exits`, and both agree with
  the cell the CH05 dry run used independently. The comment says plainly that
  CH05 has no boot-walk harness yet, so these are stronger than a guess and
  weaker than an observed post-load position.

  **Result, measured:** CH05 generates `requires: ["surf"]` on exactly
  `map036/ev008/p0`, `ev008/p1`, `ev009/p0`, `ev009/p1` — the TM76 and
  Sableyeite item balls in the sealed room at x31-36/y11-16 — and on **no other
  row**; the other 11 map036 page rows and all of map 37 stay clear;
  `reachability_consulted` is now true for every CH05 row. CH04 regenerates
  byte-identical.

  **Guarded by `reference/frozen/ch05_surf_expectations.json` +
  `tests/test_ch05_surf_oracle.py` (5 tests).** The oracle records honestly that
  it is **not** a blind freeze — the derivation predates it and was spot-checked
  during investigation — and names what *is* independent: the sealed-room
  analysis written up in the CH05 dry run before any surf derivation ran. Its
  negative arm is the load-bearing half, since a bug marking the whole map
  surf-gated would satisfy the positive arm alone. Mutation-tested: moving the
  CH05 start cell inside the sealed room turns the end-to-end test red.

  **Still owed, and not in scope here:** authoring the four `blocked:surf`
  dispositions and their deferred beats. The generator only ever populates
  `requires[]`; it never writes a disposition, and `dispositions.py` says that
  separation is the point. Authoring lands in CH05's own build at the new READ
  step, with the derived answer already sitting on the rows. Also unenforced by
  design: `blocked:surf` will raise `capability_model_unenforced` exactly as
  CH04's 28 `blocked:rock_smash` rows do — no `CapabilityModel` implementation
  exists and `chapters.json` has no structured grants field (see #125).

  Suite **2792 passed, 19 skipped** (was 2787/19).

- **D1 + D3 — the coordinate literal ban, and the read-through gets a written
  home** (2026-09-01, CH05 prerequisites — `CH05_DECISIONS.md` D1 and D3, both
  "option 1").

  **D1.** `src/rpg2gba/playtest/cells.py` is the resolver vocabulary a chapter
  author uses instead of typing coordinates: `event_cell`, `approach_to`
  (walkable neighbour in deterministic N/S/E/W order, `prefer=` to pick a side),
  `warp_cell` / `arrival_cell` (both sides of a warp, from
  `MapGraph.warp_exits`), `entry_cell` (reads
  `generator._CHAPTER_MAP_START_CELLS` — one table, not two), and the counted
  escape hatch `raw_cell(x, y, why=...)` which refuses an empty `why`. Ambiguity
  never resolves silently: more than one matching warp fails loud listing every
  candidate. The decision named four resolvers; `event_cell` and `arrival_cell`
  were added because without them the two commonest literal patterns (an
  event's own cell, and post-warp arrival cells) would all have become
  `raw_cell` escapes, which defeats the ban. Per-map graphs are cached keyed on
  the map id, so the resolvers stay idempotent (§4.2).

  **The lint** is `tests/test_chapter_coordinate_literals.py`, AST-walking
  `chapters/*.py` as a pytest test — the shape `tests/test_moki_chapter.py`
  already established for "no hardcoded flag/var ids". It flags four things: a
  bare two-int tuple anywhere, an inline `at=(x, y)`, a `raw_cell` with no
  `why=`, and a `raw_cell` with an empty one. **Grandfathering is a ratchet, not
  an exemption:** `_PRE_BAN_BUDGET` freezes the four pre-ban chapters at their
  measured counts (moki 13, route1 45, kevlar 42, route2 25) and fails if a
  count rises — *and* fails if one drops without the budget being lowered to
  match. Any chapter file not in the budget, CH05 onward, must be at zero. The
  four existing chapters are deliberately NOT retrofitted: that would mean
  editing three gate-passed chapters for no functional gain, and it would give
  them an import-time dependency on decoded output they do not have today.

  **D3.** `BUILD_PLAN.md`'s per-chapter loop gains **READ at position 5**,
  pushing ROUTE to 6 and the loop to 10 steps. It sits there because it needs
  step 4's generated manifest and authored dispositions, and must precede
  ROUTE's operator sign-off — which *is* the approve-before-build gate the
  decision names. Until now the ordering was inverted: the route plan was
  approved on its own, ahead of a read-through with no written home. The
  verdict-correctness checklist and its decaying blind-spot appendix are
  `reference/guides/read_through_checklist.md`, grounded entirely in what CH04's
  informal read-through actually caught (the page-vs-event `cosmetic` definition
  error behind B14, the "Sign" name-vs-content confusion, the B15 encounter
  table). The appendix ships with one worked decay already recorded — diagonal
  staircases came off it the same day B1 landed — and one correction: `dark_map`
  is **still** a live blind spot, because 2026-08-31 wired it into the emitted
  map header, not into the manifest, so no verdict is ever authored about
  darkness.

  Suite **2787 passed, 19 skipped** (was 2767/19). `ruff check` clean on both new
  files; the repo's pre-existing 201 ruff findings are unchanged and untouched.

- **54. `unhandled: 0` was indistinguishable from "map never transpiled"; and
  the four Map037 staircases disposed as `cosmetic`** (2026-09-01, CH05
  prerequisites — `CH05_DECISIONS.md` C1 and B1, both "build the fix").

  **C1.** `ManifestRow.unhandled` is now three-valued: a positive int is that
  many queue entries, `0` means the map *was* staged and this page produced
  none (a measured clean result), and `None` means the map was never staged so
  the queue says nothing at all. `may_be_cosmetic` returns False on `None` —
  unmeasured must not read as clean. The staged set comes from
  `_load_staged_map_ids(build_dir / "scripts")`, i.e. the transpiler's own
  `Map###.pory` output, **not** from the queue's contents: a cleanly-transpiled
  map produces zero queue rows, which is exactly what an unstaged map produces,
  so inferring staged-ness from the queue is the bug rather than the fix. A
  missing `scripts/` dir warns and returns the empty set — nothing can then be
  `cosmetic`, which fails safe. `RULE_ILLEGAL_COSMETIC` gained a third arm
  checked *first* (`None` is falsy and would otherwise fall into the
  state-writing-tags message and misreport the cause); `render.py` prints
  `unhandled: null (map never staged)`.

  **B1.** Diagonal-stair events are absorbed into `kind="terrain"` rows and no
  longer emit a page row at all. Detection reuses
  `tileset_converter.stairs.detect_stair_cells` — no second detector, since the
  layout converter is the single source of truth for which cell gets which
  native metatile behaviour (§4.3). New `TerrainRef(x, y, behavior,
  source_event_id)` beside `SeamRef`, new `terrain` field, new
  `terrain_row_id(map_id, subkind, x, y)` with a `subkind` slot so later terrain
  kinds don't collide with stairs at the same cell. Terrain rows can never be
  `cosmetic`, same as seams.

  Measured on the real corpus: CH05 generates **21 page + 4 terrain = 25 rows**
  (the same 25 the dry run projected — absorbed, not double-counted), all four
  staircases carrying the right side (`map037/terrain/stairs/11,9` and `11,10`
  LEFT, `20,9` and `20,10` RIGHT), no leftover page rows on events 3/6/7/8, and
  **0 of 25 rows `may_be_cosmetic`** where previously every one of them was.
  CH04 still checks 0 errors / 42 rows.

  Adding the `terrain` field broke `row_from_dict`'s strict field-set equality —
  the same mechanism that broke CH01–CH03 when `reachability_consulted` landed
  (#65) — so `reference/manifests/CH04.manifest.json` was regenerated in the
  same change. Diff is exactly 42 `"terrain": null` additions plus the two seam
  rows' `unhandled` moving `0` → `null` (seams never set the field, so they took
  the new default; correct, and they can't be cosmetic anyway). No
  `content_hash` moved, no row added or removed, and a second regeneration is a
  no-op. Suite **2767 passed, 19 skipped**.

- **56. `requires_flash` was a hardcoded `False`; `dark_map` was parsed and never
  read** (2026-08-31, operator ruling, CH05 branch opening) — the content call
  this entry was waiting on came back as "just render it": in Uranium, **Flash is
  not an HM** (level-up move + **TM70**), so the "HM05 has no grant site in 199
  maps" objection was not describing a gate, and a `DarkMap` cave is not pitch
  black in either engine — both light a radius around the player. So the fix is
  the honest wiring, and the fail-loud stub this entry proposed is unnecessary:
  `dark_map` now flows straight to `requires_flash`. `MapFile` gained a
  `requires_flash: bool = False` field serialized in `to_json_dict()`; new
  `_dark_map_for(uid, metadata_path)` reads the parsed metadata beside
  `_map_type_for` (their shared lookup factored into `_metadata_entry_for`,
  behaviour-preserving); both `MapFile(...)` sites in `metadata_wiring.py`
  (`build_slice_maps`, `build_warps_only_maps`) pass it. In the fork
  `requires_flash` becomes `gMapHeader.cave`, and `overworld.c:1106
  SetDefaultFlashLevel()` gives a cave a small lit radius with
  `FLAG_SYS_USE_FLASH` unset, a large one with it set — native Emerald, no
  engine change. Retro-applies to all **25** dark maps in the decoded corpus
  (`{7,10,17,19,36,37,72,74,80,83,96,105,106,118,123,150,162,189,191,192,193,202,
  205,208,213}`), so **CH03's map 19 becomes dark on its next regeneration** —
  the class-P instance that shipped lit through CH03's §9 gate. Tests
  `test_map_json_requires_flash_follows_field` + `test_dark_map_for` in
  `tests/test_tileset_converter.py`; full suite 2758 passed, 19 skipped.
  `05-passage-cave.md` §7.1 item 1 updated. CH05 dry run §5.3.

- **53. Maps 36 and 37 shared the display name "Passage Cave"** (2026-08-31,
  operator ruling, CH05 branch opening) — `map_infos.json` named both floors
  "Passage Cave" and `map_name_overrides.json` recorded both as `"CORRECT — no
  override"`, so the strict (non-walker) path raised `map 37 ('Passage Cave') ->
  MAP_PASSAGE_CAVE collides with already-minted map 36`. The fail-loud was
  working as designed; only the data was missing. Operator named them **Passage
  Cave 1F** (36) and **Passage Cave 2F** (37) — floor labels, the shape map 19's
  "Passage Cave Grott-Hole" set — rejecting the doc's `PassageCave` /
  `PassageCave2` proposal because the bare `2` carries no meaning. Two
  `overrides` entries written with evidence; the superseded `reviewed` verdicts
  keep their original text. `build_map_constants` over {19,31,35,36,37} now
  mints `MAP_PASSAGE_CAVE_1F`/`PassageCave1F` and
  `MAP_PASSAGE_CAVE_2F`/`PassageCave2F` clean. `05-passage-cave.md` §2 table and
  §7.1 item 2 updated. `reference/archive/PLAYTEST_AUTHORING_IMPROVEMENT_V2.md` §5.5.

- **55. Command code 408 (Comment continuation) missing from `_CODE_IGNORED`**
  (fixed `511ef4af`, 2026-08-28) — `generator.py:107` ignored 108 (Comment) but
  not 408 (Comment continuation), so a two-line RMXP comment put a code in
  `other_codes` and made `is_dispositionable` False; the only reason
  `map037/ev004/p0` was CH05's one undispositionable row. `_CODE_IGNORED` now
  reads `frozenset({0, 509, 106, 108, 408, 413})` — verified current at
  `src/rpg2gba/chapter_manifest/generator.py:107`, with 408 treated as a
  structural rider on 108, same as 413 is on 412. `PROJECT_TODO` #55;
  `reference/archive/PLAYTEST_AUTHORING_IMPROVEMENT_V2.md` §5.10. Landed before the CH01-CH03
  manifests are generated, since it changes what they say; `pytest -k
  manifest`: 109 passed. The CH05 dry-run doc and this file's own record of
  the finding were not updated at the time the fix landed.

- **12. Map viewer hot-reload** (2026-07-13) — built as scoped, both halves:
  tileset source PNGs joined the request-time stat fingerprint (eager
  `sources.tileset_source_paths` + memoized per-map derivation in
  `map_viewer_common`), and `map_viewer_server.py` self-restarts via
  `os.execv` when any imported repo source changes (watch set derived from
  `sys.modules` each 1 s poll, so converter modules are covered; `--no-watch`
  opt-out). Browser still needs a manual F5 after restart, as scoped.
  Live-verified end-to-end; +33 tests.

### 87. DONE 2026-09-15 — `CommonEvents.pory` harvested against the oracle; 0 transpiler bugs, and the oracle archive is now inert

**Prerequisite for CH06.** *(2026-10-04: satisfied, DONE 2026-09-15 as the heading says.)* Filed 2026-09-08 out of the post-CH05 review walkthrough,
splitting off the one obligation #86's harvest deliberately left open.
`reference/findings/oracle_harvest_2026-07-02.md` retired the frozen-Opus oracle for
maps, with one explicit exception:

> **Not harvested** — CommonEvents: the driver has no CE pass yet (maps only). Harvest
> the oracle's `CommonEvents.pory` when the CE pass lands, before retiring that file's
> oracle status.

**The CE pass has since landed** (`convert-common-events` is a registered pipeline
stage and `output/uranium-build/scripts/CommonEvents.pory` exists), so the condition
is met and nothing has been done. Current transpiler output is **401 lines / 23
blocks** against the archived Opus version's **263 lines / 22 blocks**
(`reference/archive/oracle_pory/CommonEvents.pory`), so there is real divergence to
disposition. The first harvest found three genuine transpiler bugs across seven maps;
this is the same exercise on the one file it skipped. Tool exists:
`scripts/oracle_harvest.py`. Both sides need `normalize_pory` applied first — the
archive is pre-normalization by design (raw `\"` escapes and `healparty` present).

**Why it is scoped to CH06 rather than left unscheduled.** Measured across all 199
decoded maps, common events are called from only **73 sites on 22 maps, 6 distinct
CEs**. CH06's **Map043** calls CE 4, 5 and 6 (one each; the only `code 117` calls
anywhere in maps 40–47).

**Correction 2026-09-10 — the "zero in-slice" claim in this item was wrong.** It read
*"**zero** of those maps are in the current 18-map `SLICE_MAP_IDS`, which is why five
chapters shipped without touching one,"* and that is false: **`Map068` is CH03's, in
slice since 2026-08-19, and has three `code 117` sites** — `ev009` "Receptionist TRADE"
→ CE 4, `ev011` "Receptionist PVP" → CE 5, `ev013` "Receptionist TRADE" → CE 6. So
CH06's Map043 is not the corpus's first in-slice CE call site; CH03's Map068 was, and
five chapters did not ship without touching one.

**The conclusion survives the correction, which is why this stays deferred.** Verified
end to end 2026-09-10: the transpiler emits `call(CommonEvent_004/005/006)` at each
receptionist, and `CommonEvents.pory` defines all three as
`msgbox("The Tandor Network is unavailable.") / return` under a `# STRIPPED:`
provenance comment. Map068's own events are **not** stripped — the NPCs remain and
deliver the stub, which is the intended substitute for an online feature. So the
in-slice exposure is real but already discharged, and it is to the strip path exactly
as the next paragraph says.

Two things this turned up for whoever does the harvest. `CommonEvents.pory` is **not a
harvest from zero** — `CommonEvent_010` (RACING_Main) is already transpiled and carries
its own `# UNHANDLED` comments. And CH03's three receptionist rows
(`map068/ev009|ev011|ev013/p0`) each carry `effects: ['common_event']` and nothing
else: `common_event` is in `STATE_WRITING_TAGS`, so the tag rule forbids `cosmetic`,
yet these provably only show a box and return. They are cheap `beat:` rows, and a clean
example of a state-writing *tag* on a row that writes no state.

**Mitigating, and worth confirming rather than assuming:** all three are already in
`reference/strip_list.json` → `common_events`, tagged `"online (phase0: scripts
233/235/236)"` with stub message *"The Tandor Network is unavailable."* and
`expect_name` guards. So CH06's exposure is to the strip path, not to the converted
text. The harvest is still the cheaper time to find a CE-pass bug than the first
chapter that calls an unstripped one.

After this lands, `reference/archive/oracle_pory/` is fully inert history and its
README should say so.


**CLOSED 2026-09-15.** Ran `scripts/oracle_harvest.py --common-events`. Census:
oracle **22 blocks / 263 lines**, ours **23 / 402** — 0 identical, 22 divergent,
1 only-in-ours (`CommonEvent_010_Move1`, a movement block Opus never produced).
The 0-identical count is the pre-normalization archive, not a signal.

**No transpiler bugs.** All 22 divergences disposition as Opus error, strip-path
stub, cosmetic text normalization, or a loud queued `# UNHANDLED` — full write-up
in `reference/findings/oracle_harvest_commonevents_2026-09-15.md`. The sharpest
findings: Opus terminated **11 of 22** common events with `end` instead of
`return`, which would strand every `call(...)` caller mid-script; it invented five
variable names where ours derives them from `uranium_variables.json` (var 4 really
is "Temp Move Name", reused by Uranium as CE 035's dex-milestone index — the
prettier Opus name described the wrong variable); and for CE 086/087 it fabricated
a whole `multichoice` body including a `MULTI_DREAM_VISUALIZER` constant the fork
does not define, plus warp coordinates and five `FLAG_DREAM_*` clearflags, where
ours emits `# UNHANDLED code 102` and queues it.

Ours carries **88 `# UNHANDLED` markers across 13 codes in 9 of 23 blocks** — all
visible, all queued. That contrast is the §4.1 thesis on one artifact.

Corroborated in passing: **#6** (`yesnobox` two-step) is live in CE 035, and
**#5**'s `VAR_GYM8_*` worry gains a data point — our `VAR_BLACK_TILES` is the
faithful derivation of Uranium's var 88 "Black Tiles"; the inconsistency with its
`VAR_GYM8_*` siblings is upstream in Uranium. A prefix-normalizing rename is a
registry-policy change (§10 gate), not a passing fix.

`reference/archive/oracle_pory/README.md` now states the directory is inert.

### 25. DONE 2026-09-08 — `WARP_OVERRIDES` is derived, not hand-maintained

`scripts/assemble_pathfinder.py:58` defines a hand-written `WARP_OVERRIDES:
dict[int, set[tuple[int, int]]]` that must agree with what
`metadata_wiring.build_slice_maps` (`src/rpg2gba/tileset_converter/
metadata_wiring.py:2257`) computes for gated-door and warp-override cells —
a source-of-truth duplication that violates CLAUDE.md §4.3 ("one source of
truth per concept"). They happen to agree today (the gated-door fix's item
(4), `ObjectBuildResult.gated_door_cells`, is what keeps them agreeing) but
nothing enforces it, so a future reconciliation could silently re-diverge
and quietly re-break doors. Fix: derive `WARP_OVERRIDES` from
`build_slice_maps`'s computed set instead of hand-listing it. Migrated from
`reference/findings/gated_door_collapse_2026-07-26.md` §7, 2026-08-04.

**Fixed 2026-09-08** (`reference/archive/POST_CH05_REVIEW.md` G2), by persistence rather than
reimplementation. `build_slice_maps` already computed the authoritative set;
the problem was that `assemble_pathfinder.py` runs in a separate process one
runbook step later and could not see it. So runbook step 4
(`scripts/stage_slice_scripts.py --write`) now writes
`output/uranium-build/warp_overrides.gen.json` via
`metadata_wiring.write_warp_overrides`, and step 5 reads it via
`load_warp_overrides`. The hand-written dict is gone from
`assemble_pathfinder.py`, and `scripts/verify_viewer_rom_match.py` reads the
same file so it really is checking the build's input.

Re-deriving the rule in the assembler was considered and rejected: the
gated-door and boot-page-selection logic is subtle, and a second
implementation of it is precisely the silent re-divergence this entry warned
about. One derivation, one writer, one reader.

`load_warp_overrides` **fails loud** when the file is absent rather than
defaulting to an empty set — "no doors anywhere" must never be a silent
default (§4.5).

Guarded by `tests/test_warp_overrides_derivation.py` against
`tests/fixtures/warp_overrides_ch01_ch05.json`, a frozen copy of the
hand-maintained table exactly as it stood at `78152b75`. Every one of its 45
cells was verified by a human against a booted ROM across CH01–CH05's five §9
gates, which makes it the strongest available oracle for "did the derivation
stay correct". The comparison is scoped to those 18 maps, so a new chapter
growing the set does not fail the test for the wrong reason.

### 33. Auto-derive ledge jump directions from RMXP passage bits — DONE 2026-08-24

*Migrated from `CH02_TODO.md` #1 on the CH02 gate pass 2026-08-12. **Closed
2026-08-24** during CH04's approval wait. Full derivation table + ts22
inventory: `reference/archive/CH02_TODO.md` #1.*

**Resolution.** `terrain_tags.column_behavior` derives the direction from the
passage byte's low nibble; `ledge_directions` stays empty and is now purely an
escape hatch. Sole clear bit -> `MB_JUMP_*` (0x08 south / 0x01 north / 0x02
east / 0x04 west); 0x0F is a plain wall, silent; >=2 clear bits warns once and
falls back to `MB_NORMAL`. The four `MB_JUMP_*` values resolve once at
construction and fail loud if the fork lacks one. Suite 2358 passed / 19
skipped. Derived directions reproduce the archive's hand-verified ts22
inventory exactly (0x07/0x0B/0x0D/0x0E -> S/W/E/N), and map 35's 16 tag-1
cells all derive `MB_JUMP_SOUTH` with zero ambiguity. **Caveat:** no ROM has
been built with this yet, **and CH04 will not clear it** (user, 2026-08-25):
map 35's 16 tag-1 cells all sit on the far side of the rockslide, which is
geometrically impassable until Rock Smash arrives, so CH04 *builds* the derived
ledges but cannot reach them — the boot-walk gate will pass without any ledge
ever being jumped. First real hardware proof therefore waits on the chapter that
opens the rockslide; do not read CH04's green gate as validating this item, and
do not register a CH04 beat for it. `reference/archive/PATHFINDER_FINDINGS.md:106` mislabels tiles 840-842
(0x0E) as a south ledge; it is north. Left unedited as archived history.

Ledge directionality is fully recoverable from data already deserialized —
Essentials never stores a jump direction, so the tile's 4-dir passage bits are
the whole story (sole clear bit = the jump direction; 0x0F = pure wall). Rule:
0x08→`MB_JUMP_SOUTH`, 0x01→`MB_JUMP_NORTH`, 0x02→`MB_JUMP_EAST`,
0x04→`MB_JUMP_WEST`; 0 clear bits → `MB_NORMAL` silently; ≥2 → warn +
`MB_NORMAL`. The empty `ledge_directions` override in
`reference/terrain_tag_map.json` stays as an escape hatch and wins over the
derivation — do not grow it.

**Where:** `tileset_converter/terrain_tags.py` `column_behavior`, deriving when
the override table misses. Tests in `tests/test_terrain_tags.py`: one per
direction + blocker + ambiguous + override-wins. **Verify:** Route 01's six
warning tiles resolve without hand entries, and Map032's ~30 south-ledge
over-block cells become jumpable in-game. Until it lands, builds keep firing 3
benign warnings for ts22 tiles 840/841/842 (the Moki pond-dock front, where
`MB_NORMAL` and `MB_JUMP_NORTH` behave identically anyway).

### 65. DONE 2026-09-15 — CH01–CH03 manifests load again; `reachability_consulted` was the break

Slice 2 added `ManifestRow.reachability_consulted: bool` (`chapter_manifest/schema.py`),
and `row_from_dict` does a strict field-set equality check by design — a missing key
fails loud with "regenerate the manifest rather than patching it". CH04 was regenerated
as part of the slice; `CH01.manifest.json`, `CH02.manifest.json` and `CH03.manifest.json`
were not, so any `chapter_manifest` command pointed at those three (`check`, `render`,
load) now hard-fails on the first row.

The same break applies on the disposition side: the `deferred:` verdict and the
geography-flavoured `unreachable:<reason>` arguments were removed from `_VERDICTS` in
favour of `blocked:<set>`, so an un-migrated dispositions file fails `Disposition.parse`.
Only CH04 has a dispositions file today, and it was hand-migrated.

This is the intended fail-loud shape, not a defect — but it is an unacknowledged schema
break on three gate-closed chapters, and a bystander running `check --chapter CH02` gets
a crash with no other clue. **Remediation:** regenerate CH01–CH03 manifests once the
per-(chapter,map) verified start cells exist for their maps (`_CHAPTER_MAP_START_CELLS`
in `generator.py` currently covers CH04 only), and diff the result before committing —
regenerating a gate-closed chapter's manifest is not a no-op edit.

*Found 2026-08-30 during the slice-2 commit review.*

**2026-09-06 — unblocked, CH05 has now passed its §9 gate.** The deferral
condition ("immediately after CH05") is satisfied as of the CH05 boot-walk
gate pass. Regenerating CH01-CH03's manifests and re-migrating their
dispositions files is now due; see #62's note below for the ordering
safeguard that must govern the re-derivation.

**DONE 2026-09-15.** Closed by commit `eb0f064a`, which regenerated the
CH01–CH05 manifests. Verified the same day: `python -m rpg2gba.chapter_manifest
check` loads and checks all five chapters successfully (CH01 118 errors / CH02
16 / CH03 48 / CH04 0 / CH05 0 — every one an ordinary `undispositioned`
finding, no load failure, no crash). The dispositions side is also settled:
CH01–CH03 dispositions files now exist
(`reference/manifests/CH0{1,2,3}.dispositions.json`).

### 72. DONE 2026-09-09 — Boundary-crossing convention needs to be written into `BUILD_PLAN.md`

Operator ruling, 2026-09-04, made during CH05's READ step: *a boundary
crossing belongs to the chapter being opened, not the one shipping.* An
outgoing chapter's contract is to deliver the player to the edge; the
crossing itself is asserted by the chapter whose maps make it true.
Rationale: an edge beat written against an unstaged neighbour is a test
authored to decay, and it fails in the wrong chapter — this is exactly what
happened to CH04's B7 when CH05 staged `SLICE_MAP_IDS` 36/37 and
`metadata_wiring.classify_event` stopped skipping Map035 EV001 as an
out-of-slice warp, silently invalidating B7's "no warp fires" assertion and
six downstream CH04 beats. `BUILD_PLAN.md` has no statement of this
convention anywhere; it should, so a future chapter author doesn't have to
rediscover it by breaking a closed chapter's beats. See also #73, the tooling
half of the same gap.

**RESOLVED 2026-09-09** (`2b6a3b6e`). Written into `BUILD_PLAN.md` §2 alongside
the ROUTE/BUILD reorder, with CH04's B7 as the worked example of the cost.

### 74. DONE 2026-09-09 — ROUTE runs before object events exist, so its crossing check is vacuous

The per-chapter loop's step 6 (ROUTE) runs before step 7 (BUILD) stages
object events, so `RULE_ROUTE_ORDER`'s crossing check has nothing to check
against. Step 4's `phase5` regenerates the engine maps as a warps-only Map
Walker corpus with no Poryscript, events, or NPCs — "only warp_events
survive" (`src/rpg2gba/tileset_converter/phase5.py:8-11`); trainer objects
and their sight cones are only restored at step 7 by `build_object_events`
and the assembler's copy into `engine/data/maps`. But
`build_trigger_overlay` reads `engine/data/maps`, so a route solved at step 6
sees zero trainers on the map and reports zero `CROSSING` lines regardless of
whether the order is actually safe. CH05's first solve did exactly that,
reporting a clean 155-tile order; after running step 7's first two commands
to stage real objects and re-checking, the same order was found to enter
trainer sight cones on five separate legs. All five turned out benign (each
leg either walks into the cone of the trainer that leg is walking *to*, or
past a trainer already defeated), but that was verified by hand, not caught
by the check — the check itself had nothing to say either way. Fix is a
`BUILD_PLAN.md` ordering change: run ROUTE after object staging. Affects
every chapter, not just CH05.

**RESOLVED 2026-09-09.** ROUTE and BUILD swapped in `BUILD_PLAN.md` §2's
checklist — BUILD is now step 6, ROUTE step 7. Both of ROUTE's constraints
hold at once: it still runs before the chapter module's beats are registered
(step 8), and BUILD never reads the route plan, so there is no cycle. The
step-4 bullet was corrected in the same change; it had claimed WIRE stages
object events, which `phase5` has never done, and that misreading is what put
ROUTE at 6 in the first place. #75's `RULE_TRIGGER_OVERLAY_VACUOUS` is the
enforcement that the ordering stays put: with trainers unstaged, the solve
now fails loud instead of reporting a clean route.

### 76. DONE 2026-09-10 — `destination_scripts` is per-solve, not per-destination-segment

Partial fix landed in CH05 — record this accurately, since the earlier
framing (`reference/archive/CH05_TODO.md` §Deferred, written before the fix)
claimed the field was simply never populated, which is no longer true. Commits `bc8e569f` and
`a460e823` added `effective_destination_scripts`
(`src/rpg2gba/routing/solver.py:551-553`): it unions in the triggers a
predecessor chapter's beats already resolved
(`playtest.chapter.resolved_trigger_scripts`), so a trigger CH04 already
cleared (Timothy's event-touch tile, which CH05's B1 must cross to reach the
cave) is no longer treated as foreign on CH05's walk. What remains unfixed is
the original defect: the resulting set is still a single `frozenset`
parameter (`solver.py:420`) forwarded unchanged to every `plan_segment` call
(`solver.py:660`), so it structurally cannot express "crossing X's sight cone
is fine specifically on the segment whose destination is X." A trainer's own
cone is still treated as a foreign hazard on the very segment walking up to
that trainer — re-solving CH05 with real per-map cone data but no per-segment
exemption went from 155 to 233 tiles and produced an incoherent order before
the resolved-trigger union was added. Verify these line numbers against the
current file before relying on them; the file is under active routing work.

**RESOLVED 2026-09-10** (`18869baf`). The set is now a chapter-wide base
unioned, per segment, with the destination group's own trigger scripts, keyed
on the segment's destination point only (which the site cache key already
includes). Derived through `page_row_script`, the same row-id-to-script join
`resolved_trigger_scripts` uses, so a row maps to a script name once in this
codebase (§4.3).

### 79. DONE 2026-09-08 — `cells.py` has `stair_approach`, and it is not the port this entry predicted

The resolver vocabulary in `cells.py` (`event_cell`, `approach_to`,
`warp_cell`, `arrival_cell`, `entry_cell`, plus the counted `raw_cell`
escape hatch) has nothing for staircase rows. CH05's B13 and B14 are its only
two `raw_cell()` uses (`src/rpg2gba/playtest/chapters/ch05.py:548` and
`:586`), purely because of this gap — both `why=` strings say so explicitly.
Not a discovery problem: `src/rpg2gba/routing/locations.py`'s
`_stair_approach` (`:196-263`) already implements the correct logic — a
stair row resolves to the E/W neighbour that owns the `stair_diagonal` edge
in `traversal.graph.build_map_graph`'s real edges — for the routing side. A
`stair_approach` resolver in `cells.py` would be a port of that function into
the beat-authoring vocabulary, not new derivation work.

**Built 2026-09-08** (`reference/archive/POST_CH05_REVIEW.md` G4) — but **"a port, not new
derivation work" was wrong**, and measuring that was the useful part.

`_stair_approach`'s rule (the E/W neighbour owning a `stair_diagonal` edge)
holds in the middle of a staircase run and breaks at its ends: the flat cell
you walk in from owns no such edge, while an unwalkable cell partway along a
diagonal run does. Measured against the six independently ROM-verified stair
approaches in the corpus — CH02's four `STAIR*_APPROACH` constants, gate-passed
with B2/B3 asserting the displacement on a booted ROM, plus CH05's two
`raw_cell` values — **ownership reproduces 4 and returns an unstandable cell
for the other 2. Plain walkability of the named side reproduces all 6.** That
is the rule `stair_approach` uses, and
`tests/test_cells_stair_approach.py::test_walkability_rule_beats_edge_ownership_on_every_known_value`
pins the comparison so the choice does not get "simplified" back later.

**`side` is required, not inferred.** Which end a staircase is entered from is
an authoring claim: CH02's B2 and B3 walk each of Route 01's two staircases in
*both* directions, and that is the point of those beats. An unwalkable named
side fails loud and names the other one, mirroring `approach_to`'s `prefer=`
contract rather than silently substituting.

**Keyed by event id, not coordinates.** A `stair=(20, 9)` argument would itself
be a bare coordinate literal — the lint caught exactly that on the first
attempt. A stair *is* an event, so `stair_event=` matches `event_cell` and
`approach_to` and keeps the call inside the ban.

CH05's two `raw_cell` escapes are discharged; **CH05 is back to zero coordinate
literals**, the budget it was born with. `reference/routes/CH05.locations.json`
was regenerated: every derived cell is byte-identical, only the `resolver` hint
strings changed (they used to read "no cells.py side param exists", which is no
longer true).

The underlying defect is filed separately as **#90** — it is a bug in shipped
code, not just a missing feature.

### 83. DONE 2026-09-08 — trainer battle staging failures are fatal

`trainer_converter.stage.stage_slice` (`src/rpg2gba/trainer_converter/stage.py`)
calls `stage_battles`, which wraps `build_staged_battles` in
`try/except (ValueError, FileNotFoundError, KeyError)` and on any failure
logs a WARNING and leaves `staged_battles` empty (`stage.py:619-625`) rather
than propagating — `stage_slice` then exits 0 with zero battles staged. One
unstageable trainer therefore discards every battle in the manifest,
including chapters that staged fine on a previous run. CH05's Keichi
(`TRAINER_KEICHI_248`, `BLACK_BELT` class) took CH04's 17 previously-staged
battles down to 0 during the debugging loop that resolved his trainer-class
mapping, and the damage surfaced as an apparent *CH01* failure
(`TRAINER_THEO_9/10/11` undefined on Map050), because the transpiler walks
`SLICE_MAP_IDS` in tuple order and aborts at the first map whose trainer
constants don't resolve — CH01's maps sort before CH05's. A partial failure
silently discarded good work while reporting overall success, which is
exactly the class `CLAUDE.md` §4.5 calls out. The trainer-pic half of
`stage_slice` legitimately stands alone from the battle half (a pic staging
failure shouldn't block battles and vice versa); the battle half specifically
should either stage per-trainer (skip only the failing one, loudly) or abort
the whole run rather than silently zeroing it.

**Fixed 2026-09-08** (`reference/archive/POST_CH05_REVIEW.md` G3): abort, not skip-per-trainer.
`stage_slice` still runs the pic half first and still writes the manifest —
the pics genuinely stand alone and there is no reason to throw that work away
— but it then raises `TrainerStagingError` carrying every offending trainer.
`build_staged_battles` already collected them all rather than stopping at the
first, so the complete list was available the whole time; nothing was
propagating it. `require_battles=False` is the explicit opt-out for a
pics-only caller.

`scripts/stage_trainers.py`'s "CHECK THE BATTLE COUNT, not just the exit code"
banner is retired — the exit code is trustworthy now. Tests in
`tests/test_trainer_stage.py`.

### 86. DONE 2026-09-08 — the two frozen-Opus differential tests were removed, not refreshed

**The diagnosis this entry originally carried was wrong.** It read: "the frozen-Opus
oracle predates Map036 … refreshing it is an operator content call." Investigated
2026-09-08 in the post-CH05 review walkthrough; what was actually true:

- `_differential` (`tests/test_deterministic.py:1313`) read its "oracle" from
  `output/uranium-build/scripts/` and iterated `output/uranium-build/checkpoints/*.done`.
  Both are gitignored and were wiped by a `pipeline --clean` at some point; `scripts/`
  is now written by the **deterministic transpiler**, and `checkpoints/` held exactly
  two files (`Map036.done`, `Map037.done`) from CH05's transpile.
- So the tests were comparing the classifiers against **the transpiler's own output**.
  Had Map036 happened to match, they would have gone green by comparing the pipeline
  to itself — a silent pass, the §4.5 shape.
- The real oracle was never lost. It is committed at `reference/archive/oracle_pory/`
  (20 `.pory` files), archived 2026-07-02 under grill decision **D6** *specifically so
  that `pipeline --clean` could not destroy it*. The archive did its job; nobody
  repointed the tests.
- And it did not need repointing, because **the oracle was formally retired the same
  day**. `reference/findings/oracle_harvest_2026-07-02.md` is the one-time D6 harvest
  (maps 001–007, every divergence cluster dispositioned: 3 transpiler bugs found and
  fixed, 5 clusters ruled Opus errors): *"with these dispositions recorded, the oracle
  is retired (the archive stays for provenance, it gates nothing)."* Per D6, permanent
  goldens come from reviewed transpiler output, never Opus text — which is exactly what
  a permanent pytest against Opus text was.

**Resolution:** both tests and the now-dead `_differential` / `_norm_items` /
`_blocks_by_label` helpers deleted; a comment at the removal site records why.
`test_emitted_item_constants_are_real` stays (it validates against the Phase-2 source
of truth, not against Opus). Module green at 123 passed. The one obligation the July
harvest deliberately held open is now filed separately as **#87**.

### 88. DONE 2026-09-08 — the four pinned lists have a completeness check (`rpg2gba slice-pins`)

`reference/archive/POST_CH05_REVIEW.md` G1. Four lists must move together when a chapter joins
`SLICE_MAP_IDS`; exactly one was guarded (`test_chapter_atlas.py` pins
`SLICE_MAP_IDS` itself against the atlas). `test_trainer_battles.py` and
`test_species_gate.py` checked that present entries are *valid*, never that the
lists are *complete*, so an omission surfaced later as a transpile abort — and
CH05 hit three of them one at a time, "each omission failed separately and
looked unrelated to the last, costing a full loop".

`src/rpg2gba/slice_pins.py`, run as `rpg2gba slice-pins` (or
`python -m rpg2gba.slice_pins`). Two layers, because they answer different
questions:

- **The gate** — every `TRAINER_*` the transpiler actually *emits* into
  `scripts/Map###.pory` must be in `SLICE_TRAINER_BATTLES`. Exact, and the
  thing that fails a build: an unpinned emitted constant IS the transpile abort.
- **The census** — every trainer-battle *event* on an in-slice map with its
  status, whether or not it was emitted. Advisory, never an error.

Pics, species and trainer-class mappings are not re-derived: the check runs the
real `stage_battles` over the union of pinned + newly-required keys and
re-groups its collected errors into per-list buckets. `build_staged_battles`
already reports every offending trainer rather than the first, so one run yields
the whole picture — which is also the Tier 2 class-mapping batching (D5).

The reverse direction is deliberately never reported: `SLICE_TRAINER_BATTLES`
may hold keys no map event resolves to. `TRAINER_THEO_9/10/11` are the standing
case — which rival battle fires depends on the starter, so Map050's event names
none of them.

Preconditions fail loud rather than reporting clean: an absent `maps/` or an
absent species manifest would otherwise read as "no gaps" / "every species
missing". Tests: `tests/test_slice_pins.py` (19).

### 90. DONE 2026-09-08 — `_stair_approach` returned cells the player cannot stand on

Found while scoping #79/G4, by checking the resolver's output against CH02's
four ROM-verified stair approaches rather than against its own docstring.

`routing.locations._stair_approach` selected "the E/W neighbour of the stair
cell that owns a `stair_diagonal` edge" and **never checked that neighbour was
walkable**. Owning the edge does not make a cell standable — the edge describes
the redirect the staircase performs, not somewhere the player may stand — so on
a diagonal run the unwalkable cells partway along it satisfied the test. Its
sibling twenty lines below, `_approach_side_candidates`, had always filtered on
`is_walkable`; the stair path simply never did.

Measured on Map033 (Route 01, in slice since CH02), it returned an unstandable
cell for **3 of the map's 7 stair cells**, including both of the approaches
CH02's B2/B3 verify against a booted ROM:

    stair (52,41) -> (53,41)  walkable=False    ch02 says (51,41)
    stair (53,43) -> (52,43)  walkable=False
    stair (53,44) -> (52,44)  walkable=False    ch02 says (54,44)

**Latent, not live.** CH01–CH04 carry no route plans, so nothing consumed it
outside CH05 — where all four of Map037's approaches happen to be walkable, so
CH05's derived cells and `reference/routes/CH05.locations.json` are unchanged
by the fix. It would have fired the moment CH01–CH03 were re-derived (#65) or
CH02 got a route plan, and **#62's freeze-derive-diff safeguard could not have
caught it**: the frozen expectation and the derivation come from the same rule,
so they would have agreed with each other and disagreed with the ROM.

**Fix:** walkability filter added to both `_stair_approach` and
`_stair_side_candidates`. Silent-wrong became loud-can't — an all-unwalkable
stair cell now raises, saying it is probably mid-run and pointing at
`playtest.cells.stair_approach` for the side-aware resolver. `(53,43)` now
correctly resolves east to `(54,43)` instead of returning unwalkable `(52,43)`.

**Why this mattered for sequencing:** it is the concrete reason G4 belonged
before the CH01–CH03 re-derivation rather than during it.

### 29. `stage_slice_scripts` existence check is blind to engine-defined labels -- FIXED 2026-08-09

*(2026-10-04: the label check is fixed; the write-ordering trap described at the end is still live and is filed as #132.)*

Found 2026-08-09 while rebuilding CH02. `stage_slice_scripts.py --write` exits
1 with `FAIL: 2 undefined script reference(s): BerryTreeScript,
Common_EventScript_FindItem`. Both labels are real and vanilla —
`engine/data/scripts/berry_tree.inc:1` and
`engine/data/scripts/item_ball_scripts.inc:1` — but the dangling-reference check
(`stage_slice_scripts.py:560-585`, `asm.find_dangling_references`) builds its
defined-set from staged `.pory` text plus the dispatchers and CommonEvents only.
Any map.json object script pointing at an engine-provided label therefore reads
as dangling by construction.

Pre-existing, not caused by the trainer-pacing change: the already-shipped
`engine/data/maps/Route01/map.json` carries 10 such references, so every CH02
build since berry trees and item balls landed has exited 1 here. Not a build
blocker — `assemble_pathfinder` and `make modern` are separate steps with their
own fork-index gate — but it is a **loud check that is now routinely ignored**,
which is exactly how a real dangling reference gets waved through.

Fix: feed the check an engine-defined label set (scan `engine/data/scripts/*.inc`
for `^Label::`, the same way the fork-capability index is built per CLAUDE.md
§4.7) and only report labels defined in neither place. Do not special-case these
two by name.

**FIXED 2026-08-09.** New `assembly.engine_defined_labels(engine_root)` harvests
`^Label::` (double-colon only — a scan of every script reference in the vendored
tree found zero targeting a single-colon label, which the engine uses for text
and movement bodies) and `find_dangling_references` grew an `engine_defined`
parameter unioned into the defined-set, defaulting to `None` so no other caller
moved. `stage_slice_scripts` passes it using the engine root it already had.
4924 labels; fail-loud floor at 100, because a silently-empty scan would restore
the exact false-negative the function exists to kill. Exits 0 now.

**The scan scope is the load-bearing part.** The obvious glob `data/**/*.inc`
also matches `engine/data/maps/<Map>/scripts.inc` — per-map output assembled from
*our own* staged `.pory`, blanket-gitignored at `.gitignore:124`. Trusting that
would let a stale artifact from a previous build vouch for a label the current
staging no longer emits, which is a worse failure than the one being fixed: a
dropped script would pass the gate. Scope is therefore `data/scripts/**/*.inc`
plus top-level `data/*.s` / `data/*.inc`, excluding `data/maps/**` and
`data/layouts/**`. Including the generated trees inflated the count from 4924 to
23290 — a useful smell if anyone re-widens it.
`test_engine_defined_labels_excludes_generated_per_map_scripts_inc` pins it.

**The false alarm was not harmless — it silently skipped staging.** `main()`'s
`--write` block (`stage_slice_scripts.py:602-606`) sits *after* the existence
check's `return 1` (`:592`), so a failing check writes **no** `.pory` to
`output/uranium-build/staging/scripts/` at all. `assemble_pathfinder` then runs
off whatever `.pory` a previous run left there while happily picking up fresh
map.json/layout data from its own path. Every CH02 build since berry trees
landed was therefore a mixed build: current map data, stale scripts. Caught
2026-08-09 when ROM `5d4a7622` (built through the failing gate) and `360e8506`
(built after the fix) differed by 160 bytes from a change that touches no
emitted content; `360e8506` reproduces byte-identically across repeat runs, so
the pipeline is idempotent and `5d4a7622` was the anomaly. Fixing the check
closed this by making the gate pass, but the ordering is still a trap — a
genuine future failure would skip the writes the same way. Worth making the
write unconditional (or the failure an exception) so a red gate can never leave
a half-staged tree behind; not done here.

### 45. Defeated Larrie faces you and says nothing — ROOT-CAUSED, FIXED, AND CONFIRMED IN PLAY 2026-08-27

**CLOSED (2026-08-27).** Confirmed in play by CH04's §9 boot walk: route2
chapter suite GREEN 74/74 on ROM `5953e98f`, the first run in which a defeated
phone trainer speaks its idle line — B11 (Larrie) and `route1:N5` (Richey)
both pass. The cause is the engine's re-talk resume address, and it makes the
symptom exact.

On a re-talk the engine runs its own scaffolding,
`EventScript_TryDoNormalTrainerBattle` (`engine/data/scripts/trainer_battle.inc:9-21`):
`lock`, `faceplayer` — *this is the turn-to-face the operator sees* — then
`GetTrainerFlag`, already set, so it falls to `EventScript_NoNormalTrainerBattle`'s
`gotopostbattlescript`. That resolves through `BattleSetup_GetScriptAddrAfterBattle`
(`engine/src/battle_setup.c:1574`) to `sTrainerBattleEndScript`, which
`TrainerBattleLoadArgs` (`battle_setup.c:1058`) sets to
`(u8 *)data + sizeof(TrainerBattleParameter)` — **the byte immediately after
the packed trainerbattle command, i.e. the next line of the calling script.**

§46 put the route to `Page2` in `trainerbattle_single`'s FOUR-ARGUMENT
continue-script instead. That is a different pointer, `battleScriptRetAddrA`,
consumed only by `gotobeatenscript` / `BattleSetup_GetTrainerPostBattleScript`
(`scrcmd.c:2478`, `battle_setup.c:1582`), which fires **exactly once**, on the
return from a won battle. So the branch ran once, with the self-switch still
clear, and never again — `Page2` was unreachable in every state, and Page1's
next line was `release`/`end`. Lock, faceplayer, silence. Permanently, on any
tile, for both trainers.

Vanilla puts the re-talk continuation in the fall-through, not the 4th
argument (`Route102_EventScript_Calvin`: `trainerbattle_single`, then
`specialvar ShouldTryRematchBattle`, then the post-battle msgbox). The
classifier now does the same: Page1 is `trainerbattle_single(...)` followed by
`goto(Page2)`, and the 4th argument keeps only the one-shot registration (its
now-dead self-switch check is dropped; the `setflag` stays, because
`metadata_wiring` reads that self-switch for page conditions).

**Fix:** `deterministic.classify_phone_rematch_trainer_battle`. Regression
tests: `tests/test_phone_rematch_classifier.py::test_larrie_page1_falls_through_to_page2_after_trainerbattle`
and the ev039 golden. In-play guard: `route1:N5`, now registered (below).

**The two-datum key.** The operator supplied both: position is irrelevant
(sight-approach or direct interaction, same result), and **Richey exhibits it
too**, on a save the harness never touched, beaten by a different playthrough.
That killed the harness explanation and the tile explanation together, and
left the one thing Larrie and Richey share and Timothy doesn't — the phone
shape. The engine read followed in minutes.

*The original filing and its refuted claims are kept below, unedited.*

---

*Original filing — superseded by the resolution above:*

*Filed 2026-08-27 from CH04's suite run on ROM `b07a02f8`; **substantially
corrected the same day by the operator's own boot walk of that ROM**, which
refuted the original diagnosis. The corrected version is below; the refuted
claims are kept explicitly, because two of them were confidently wrong and
the next reader should not re-derive them from the same evidence.*

**This is the live blocker for CH04's §9 gate**: B11 fails on it, and
B12-B15 are gated behind B11.

**What actually happens in game (operator boot walk, ROM `b07a02f8`).**
Re-talking defeated Larrie: he **turns to face the player, and NO text box
appears at all.** The script starts — the `faceplayer` is visible — and then
produces nothing. (The match-call registration message DOES appear, correctly,
immediately after the battle itself; an earlier revision of this item
mis-recorded that as happening on re-talk. It does not.)

**Youngster Timothy, same map, re-talks correctly** and shows his line. He is
the plain vanilla shape — `trainerbattle_single` with a trailing msgbox, no
phone registration and no rematch branch. **No PHONE trainer is verified in
play**, so §46's fix is unproven for its whole class; Route 1's Richey was
not walked.

**Leading hypothesis: the branch works and the defect is one level deeper.**
`Page2` runs `specialvar(VAR_RESULT, IsTrainerReadyForRematch)` and takes the
idle-line msgbox ONLY on `VAR_RESULT == FALSE`; otherwise it falls into
`trainerbattle_rematch`. If that special returns anything but FALSE and no
rematch is actually available, the rematch command does nothing visible and
the script ends — which is precisely "faces you, no text". That would mean
the `goto_if_set ...SSA -> Page2` fix from §46 IS working and the bug is the
rematch arm. Under investigation; if it holds, the fix is to gate or drop the
rematch arm rather than to touch the dispatch again.

**The harness is NOT the primary defect, and the operator's argument is the
reason.** A mispositioned harness cannot explain a human standing in the
correct tile, facing the trainer, and getting no box. The harness's
coordinate discrepancy (below) may still be real and may still be why
`interact()` reported "no script started", but it is a SECOND, lesser
problem — do not let it absorb this item.

**REFUTED — do not carry these forward.** Both came from harness
observations and both are wrong:

1. ~~"A defeated trainer cannot be re-talked anywhere in this build; pressing
   A starts no script at all."~~ False. A script demonstrably runs — the
   trainer faces the player and prints a message. The harness's
   `interact()` reporting "did not start a script", reproduced by driving
   the emulator directly from `pre_beat.gba`, is a **harness** failure to
   reach or detect the interaction, not the game's behavior.
2. ~~"The trainer is not rendered."~~ False. Larrie is plainly visible in the
   B11 contact-sheet frame (`route2-sheet-6.png`, the yellow-hatted Hiker,
   same sprite as the B2 frame) and in play. That claim came from
   misidentifying a distant sprite in a probe screenshot as the Barewl.

**Still open, secondary: the harness's object-coordinate read.** It places
Larrie at `(18,39)` against a template of `(18,36)`, and Richey at `(17,11)`
against `(17,9)`, while static objects on the same maps (the Barewl at
(17,36), the item balls, the rocks) report their templates exactly. Since the
trainers are rendered and DO respond in play, these coordinates look wrong or
stale, which would explain `interact()`'s "no script started" report from a
seeded state. That is an `emulator.py` object-decode question —
`off_objevent_currentcoords`, and whether a trainer that has run an approach
sequence keeps its live position in the field the harness reads. **Elevation
remains ruled out** (object elevation 3; staged terrain elevation 3 at the
template, at the reported tile, and at the player's tile; the only z-check is
`ObjectEventDoesElevationMatch` and 0 is a wildcard), as does
`TryOverrideTemplateCoordsForObjectEvent` moving them (it assigns only
`movementType`, never coordinates, despite its name).

**Eliminated 2026-08-27 (checked, do not re-check).**

- **The emission is correct.** The assembled chain in
  `engine/data/maps/Route02/scripts.inc` is complete and well-formed:
  `goto_if_set FLAG_MAP035_EVENT003_SSA` -> a label that `goto`s
  `Map035_EV003_Page2`; `Page2` itself has the `specialvar VAR_RESULT,
  IsTrainerReadyForRematch`, the `compare`/`goto_if_eq`, the msgbox arm and
  the `trainerbattle_rematch` arm, all present. Not a dropped command, not a
  mis-wired label, not a bad goto.
- **`IsTrainerReadyForRematch` is a real special** (`data/specials.inc:81`)
  and is FALSE-safe for a trainer absent from the rematch table
  (`TrainerIdToRematchTableId` -> -1 -> FALSE). Larrie IS in the table
  (`rpg2gba_rematch_table.gen.h`, `REMATCH_URANIUM_LARRIE_4`, five identical
  stages — the generator emitted no real rematch variants). Richey likewise.
- **Neither `Page2` arm is silent by design.** FALSE prints the idle msgbox;
  TRUE runs `PlayTrainerEncounterMusic` / `ShowTrainerIntroSpeech` /
  `waitmessage` / `waitbuttonpress` / `BattleSetup_StartRematchBattle`, i.e.
  visible text and a battle. "Faces you, then nothing" matches neither arm,
  so the original rematch-arm hypothesis is **REFUTED**.
- **In the harness's seeded state the script does not start at all from the
  beat's authored tile.** Pressing A at (18,37) facing UP leaves the field
  unlocked and `gSpecialVar_Result` untouched across 120 frames. That
  corroborates the coordinate discrepancy (Larrie is not at his template
  (18,36) in that state) but does NOT explain the in-play symptom, where the
  script demonstrably starts.

**The open contradiction.** In real play the script starts (the trainer
faces the player) and then prints nothing. In every seeded state reachable
from the harness, the script does not start at all. Both observations are
solid; they cannot both be explained by "the harness stands in the wrong
tile" alone, because in play the human stands in the right one. The next
datum needed is **where Larrie is standing when the player talks to him** —
his own tile relative to where he stood before the battle — and whether a
second consecutive talk behaves differently. Asked of the operator
2026-08-27; do not guess it.

**Next steps, in order.**
1. Confirm or refute the `IsTrainerReadyForRematch` hypothesis above — read
   what the special returns for a trainer with no available rematch, and
   whether `trainerbattle_rematch` is silently inert in that case.
2. If confirmed, decide what the idle path should be. The rematch arm is
   currently unreachable content anyway: nothing in this pipeline makes a
   rematch "ready", and B10 (the rematch offer) is already deferred for want
   of a Match Call driver.
3. Separately, fix the harness object-coordinate read and re-point B11 at the
   live position. B11 asserting the idle line stays the correct assertion.

**Resolved 2026-08-27:** the trainer that re-talked correctly on the walk was
**Timothy**, not Richey — confirmed by the operator. So no phone trainer's
re-talk has been observed working, and §46's fix remains unverified in play
for its class.

**Blast radius.** CH01-CH03 all passed their §9 gates without this being
visible, because CH04's B11 is the first beat in the corpus that re-talks a
defeated trainer at all.

### 46. Phone-rematch trainers' `Page2` was dead code — FIXED 2026-08-27, then RE-FIXED the same day (see §45); CLOSED, confirmed in play by CH04's §9 walk (ROM `5953e98f`)

*Filed and fixed the same day. **The fix recorded below was half right and did
not work**: the collapsed-pages dead end it diagnosed was real, but it moved
the branch into `trainerbattle_single`'s four-argument continue-script, which
the engine runs exactly once — on the return from a won battle — and never on
a re-talk. `Page2` stayed unreachable, and §45's silent NPC is what that looks
like in play. §45 carries the engine citations and the corrected fix
(the branch belongs in Page1's fall-through, where vanilla puts it). Read §45
first; the text below is the superseded reasoning, kept because it was
confidently argued and the next reader deserves to know where it went wrong.*

`deterministic`'s phone-rematch classifier emits three blocks per phone
trainer: the `trainerbattle_single` page, a `_RegisterMatchCall`
continue-script, and a `Page2` steady state carrying the
`IsTrainerReadyForRematch` branch and the post-defeat idle line. Nothing ever
referenced `Page2`: `transpile_driver._record_collapsed_pages` marked the
event `collapsed_pages`, and `metadata_wiring._resolve_script` read that
trait as "resolve to the page-1 label, build no dispatcher". Re-talking a
defeated phone trainer therefore re-ran the headless match-call registrar and
the NPC said nothing.

Four events corpus-wide: map33/ev39 (Brandon), map33/ev53 (Richey),
map35/ev3 (Larrie), map35/ev23 (Brent). **Two are Route 1's, so CH02 passed
its §9 gate on 2026-08-12 with two silent NPCs in it.** Map050/ev19 (Theo)
was unaffected — it gets a real `_Dispatch` — which is what localises the
bug to the `collapsed_pages` rematch-trainer shape rather than to multi-page
trainers generally.

**Fix:** the `_RegisterMatchCall` block now leads with a check on the SSA
flag it already sets and jumps to `Page2` when set. That is where vanilla
puts it (`Route102_EventScript_Calvin`'s 4th `trainerbattle_single`
argument runs both after the battle and on every later re-talk via
`gotopostbattlescript`).

**A dispatcher wrapping the trainer script is NOT an option — do not retry
it.** It was tried first and broke sight-trainer detection outright:
`GetTrainerFlagFromScriptPointer` (`engine/src/battle_setup.c:1232`) casts
the object event's RAW SCRIPT BYTES at a fixed offset to read the opponent
id, so the object's script must have `trainerbattle_*` as its literal first
command. Wrapping it made the engine read garbage as a trainer id;
`route1:B13` (Richey's first battle, previously green) failed immediately on
the live suite. The comment recording this now lives at the classifier's
post-battle-script construction.

### 94. DONE 2026-09-10 — the archetype classifier is not open for extension

*Filed 2026-09-10. Prerequisite for `reference/archive/REDERIVATION_PLAN.md` §13.3's template program.*

`classify_event` (`chapter_manifest/archetypes.py`) dispatched through a
hand-written `if`/`elif` sequence, and `ARCHETYPE_NAMES` is a literal set. Adding
an archetype means editing both by hand plus writing the template module — three
edits in two files, none of which a new archetype can register itself into.

That is fine at four archetypes. §13.3 lists **eleven** candidates, and the two
cheapest (`arrival_nudge`'s `graphic` requirement, `item_ball`'s page-1
requirement) are *loosenings of existing predicates* rather than additions — they
touch the same hard-coded chain. Convert the dispatch to a registry before the
fifth lands, or the chain becomes the thing every template change has to
negotiate.

Note the constraint this must preserve: the `playtest/archetypes/` templates are
**author-called, not a generator** (`MEMORY.md` → Key File Notes) — the chapter
file stays a linear approvable document with hand-controlled registration order.
A registry changes how a *classifier* finds its matchers, not how a chapter
registers its beats.

**DONE 2026-09-10** (`c91f70d3`). `classify_event`'s hand-written sequence is now
a walk over `_ARCHETYPE_REGISTRY`, a tuple of frozen `_ArchetypeEntry(name, level,
matcher)` records; `ARCHETYPE_NAMES` is derived from that registry instead of
restated beside it, so the set and the dispatch can no longer drift.
`_build_registry` raises on a duplicate name or an unknown level rather than
tolerating either (§4.5). Adding a fifth archetype is now one matcher plus one
registry line. The constraint this entry named is preserved untouched: the
`playtest/archetypes/` templates remain author-called, and registration order in
the chapter file is still hand-controlled.

Pure refactor, verified rather than assumed — the committed module and the
working tree were both loaded and run over all five chapters' manifests, giving
identical `ArchetypeMatch` output (111 matches, 30/29/31/9/12).

**One sharp edge survives the refactor deliberately, and the next archetype has
to know about it.** Event-level entries run in registry order and **once any
event-level entry claims rows, no later event-level entry gets a turn** — so a
third event-level archetype would be silently skipped on every event a trainer
already matched. Today's four entries hide this (only `trainer` and `item_ball`
are event-level and they do not overlap). `reference/archive/REDERIVATION_PLAN.md` §13.3's T1 third
item — `pbReceiveItem` NPC gifts — is the first candidate that would be
event-level and make this load-bearing.

### 95. DONE 2026-09-11 — `derive_blocked_verdict` asks the wrong question about obstacle rows

*Filed 2026-09-10, measured while ruling `reference/archive/REDERIVATION_PLAN.md` §13.*

It asks whether a tile **adjacent to the event** is reachable. For an obstacle
event — a Rock Smash rock, a Strength boulder — that is the wrong question: you
can nearly always stand next to the rock. It never asks whether the obstacle can
be **cleared**, so the verdict comes back `reachable_now=True` and
`as_disposition()` returns `""`.

Measured consequence: **5 of CH04's committed `blocked:rock_smash` rows do not
reproduce** when derived (`map035/ev014/p0`, `ev014/p1`, `ev017/p0`, `ev017/p1`,
`map035/seam/N/map040`). The hand-authored answers are the correct ones.

This is independent of any disposition generator — it means a derived `blocked:`
is unreliable on precisely the class #92 already flagged, and #92's finding (no
`code 121`/`122` grant site exists for `rock_smash`/`surf` at all) is the reason
it has never been caught by a disagreement.

**DONE 2026-09-11.** The diagnosis was right and the fix is smaller than the
entry implies: the two event-goal derivations were answering *one* question when
there are *two*, so `derive_blocked_verdict_for_event` and
`derive_blocked_verdict_for_event_from_starts` now take a keyword-only
`require_clearing: bool` **with no default**.

- `require_clearing=False` — the APPROACH question, today's behaviour byte for
  byte: is any orthogonally-adjacent cell reachable.
- `require_clearing=True` — the CLEARING question: that, **and** if
  `capability_map.obstacles` carries an entry for the event's own cell, that
  obstacle's capability must be held too. An event with no obstacle entry
  collapses to the approach answer, so a plain NPC gains no invented gate.

The conjunct goes inside the predicate handed to `_minimal_sets_for_predicate`,
so the existing subset search surfaces the obstacle's own capability in
`minimal_sets` for free — no second code path, and `BlockedVerdict` /
`as_disposition()` are untouched.

**No default is the load-bearing part** (§4.5). The two questions have different
right answers and only the caller knows which it means, so each of the three call
sites now says so out loud: `generator._reachability_requires` asks
`require_clearing=True` (`requires[]` means *what do I need to get past this*),
`approach_model.GraphApproachModel` asks `False` (it models walking up and
pressing A — an uncleared rock still takes the interaction, which is what raises
the prompt), and `traversal blocked` gained a `--require-clearing` flag rather
than picking for the operator. Two tests pin the `TypeError` so a future edit
cannot quietly reintroduce a default.

**Verified on the real data, not just a fixture.** `map035/ev014` (20,28) and
`map035/ev017` (19,29) each carry `Obstacle(source="event",
capability=ROCK_SMASH)` on their own cell and now derive `blocked:rock_smash`
under the clearing question while still deriving `""` under the approach
question — reproducing CH04's hand-authored disposition for all four of their
rows. `tests/test_traversal_frozen_oracle.py` pins that against the real map;
`tests/test_traversal_reachability.py` pins the shape on a synthetic 3×3. Suite
green at 3290 passed / 17 skipped.

**Scope correction: this entry's list of five rows conflated two bugs.** The
fifth, `map035/seam/N/map040`, is not an event, has no obstacle cell of its own,
and derives **identically under both questions** — 6 of map 35's 38 walkable
row-0 cells come back `blocked:rock_smash` either way, which the frozen-oracle
test already asserted before this change. Whatever kept the seam row from
reproducing in §13's measurement is a **disposition-generator** concern, not this
derivation's, and is still open going into P8b.

### 93. Five capability base tokens name both a switch and a variable -- RESOLVED 2026-09-10

*Filed 2026-09-10, same commit as #92.*

`capability_sites.token_for_label` slugs a Uranium switch or variable label into
a `blocked:` token. A switch's token is the bare slug; a variable's embeds the
threshold (`Quest Log`, 4 → `quest_log_4`). Five labels collide at the base:

| base | switch | variable |
|---|---|---|
| `final_event` | 125 | 127 |
| `first_strike` | 73 | 120 |
| `gym_2_gempuzzle` | 67 | 108 |
| `gym_4_puzzle` | 79 | 112 |
| `dream_palace_grotto` | 207 | 207 |

So `blocked:final_event` is **switch 125** (granted at `map199/ev001/p0`, CH57)
while `blocked:final_event_2` is **variable 127** (CH56) — two unrelated game
objects that read as one capability at two thresholds.

**This is deliberately not an `AmbiguousTokenError`.** No two token *strings*
collide, each resolves deterministically, and raising would break a derivation
that is otherwise correct across all 268 tokens. It is surfaced on
`CapabilityDerivation.colliding_bases` and logged, and pinned by
`test_switch_and_variable_bases_that_collide_are_reported`. What is missing is
the fix, which is a naming decision:

- **Prefix variable tokens** (`var_quest_log_4`, switches stay bare) —
  unambiguous, and makes the *kind* of gate visible at review time, which is
  useful in its own right. Changes every threshold token.
- **Prefix both** (`sw_final_event` / `var_final_event_2`) — symmetric, but
  touches all 97 switch tokens for the sake of 5 collisions.
- **Disambiguate only the 5** via an override table — least churn, but a
  token's spelling would then depend on unrelated data, which is its own trap.

Worth settling before CH01–CH03's dispositions are authored, since that is the
first work to write `blocked:` tokens at volume.

**RESOLVED 2026-09-10** (operator ruling; full argument in `reference/archive/REDERIVATION_PLAN.md`
§10 R1). **Prefix variable-derived tokens with `var_`; switch-derived tokens keep
the bare slug** — `blocked:got_pokemon` is a switch, `blocked:var_quest_log_4` is
variable 101 at threshold 4. The five bases stop colliding by construction, and the
*kind* of gate becomes readable in the disposition itself.

The "changes every threshold token" cost this entry weighed turned out to be
prospective only: **the migration cost on committed artifacts is zero.** The only
`blocked:` tokens anywhere in the corpus are `blocked:rock_smash` ×28 (CH04) and
`blocked:surf` ×4 (CH05), and per #92 neither is switch- or variable-derived. Every
token the decision touches is one nobody has written yet — which is also why
prefixing both (all 97 switch tokens) bought nothing the asymmetric form doesn't.

The override table was rejected on the trap this entry already named: a token's
spelling would depend on unrelated data, so adding a Uranium *variable* could
silently rename an existing *switch*'s token.

**Carries one obligation into the implementation:** a switch label that itself slugs
to a leading `var_` re-opens the collision, so `token_for_label` must fail loud on
that rather than mint it (CLAUDE.md §4.5). Nothing in the current label set does,
which is why this is a guard and not a rename.

### 109. `text_source` rejects the straight quote that staging normalizes, so 12 T2 rows have no oracle -- DONE 2026-09-24

Fixed by extracting `assembly.apply_dialogue_char_substitutions` (the open/close
quote toggle + `*`/`[`/`]` subs) out of `_normalize_string_content` as the one
shared implementation, and having `text_source.page_messages` call it
(`quote_escaped=False`) before `_canonicalize_chars`; `normalize_pory` is
byte-identical. All previously-refusing rows now resolve.

Surfaced 2026-09-15 while probing whether T2's `flavour_npc_beat` could be
applied mechanically to the CH01-CH03 residue. Of 96 candidate rows, 84 resolve
a source oracle and **12 fail loud** with:

> `text_source: character U+0022 '"' has no engine/charmap.txt entry -- unrepresentable on the ROM's font`

**This is an oracle gap, not a ROM bug, and the distinction is the whole item.**
`engine/charmap.txt` genuinely has no `U+0022` entry -- it has `“` (B1) and `”`
(B2) only. But `tileset_converter.assembly.normalize_pory` already converts `\"`
to typographic `“`/`”` on an open/close toggle at staging (`assembly.py:475-476`,
and its docstring at :549), so **the ROM text is correct**. It is
`playtest.text_source._canonicalize_chars` -- the path a beat uses to derive
expected text -- that does not apply the same substitution and therefore cannot
read a page the pipeline converts fine.

Rows affected (all `flavour_npc`, all otherwise mechanical): `map032/ev001/p0`,
`map049/ev006/p0`, `map049/ev015/p0`, `map049/ev016/p0`, `map050/ev010/p0`, and
7 more -- re-derive with the probe rather than trusting this list to stay current.

**Fix shape, and the constraint on it:** `text_source` should apply the same
open/close toggle, **reusing `assembly`'s implementation rather than
re-implementing it** (§4.3 -- two independent quote-toggling state machines that
must agree is exactly the drift this repo consolidated five `*_constant` helpers
to avoid). The toggle is stateful across a string, so a naive `replace('"', '“')`
is wrong and would silently mis-render every closing quote.

Worth doing before T2's application pass: it is 12 of 96 rows, and every one of
them is otherwise ready.

### 117. Two-visit events: a route walks only one of two page-ending choice arms -- DONE 2026-09-29

**Resolved the same day** (operator re-ruled: walk the hand's round trip).
`beat_gen/round_trip.py::find_round_trip` derives it: for an autorun page with exactly two
page-ending arms, answer the losing arm X, find the live page Q, and find a claimed arm of
Q that makes the page live again and re-fires into Y. `split_choice_arms` then walks X and
moves Y's rows into Q's beat. CH01 now runs p0 No (#41), p2 re-offer (#48), p2 Yes riding
the quiz (#49), then p1 (#50). Grade is clean. Only ev005 matches in CH01–CH05. Left open:
p2's facing arms b1–b4 are `unselected_arm` (new `self_ended` verdict), none frozen. The
original entry follows.

The professor (`map050/ev005`) asks "ready for the Trainer Aptitude Test?". "Yes"
(`p0/b2`) runs the quiz and starter selector and sets self switch C, which makes p1
live. "No" (`p0/b3`) sets D, which makes p2 live, and p2 re-asks the question;
`p2/b0` then re-opens p0's "Yes" path. Both arms end the page, so ruling 19 walks
one. Since `\ch` parsing (2026-09-29) CH01 walks "Yes", the story path, and p2's
7 rows are `arm_gated` (reachable on the ROM through the unwalked arm, not walked).
Covering both needs the solver and ruling 19 to express a revisit: No → p2 → p2/b0
→ Yes → p1. This is the same shape as the one story edge `_acyclic_story_edges`
skips corpus-wide. Operator: deferred 2026-09-29 (walk Yes, relabel p2).

### 107. Warp retain-facing tier 3 should test second-order reachability -- CLOSED 2026-09-18

**CLOSED 2026-09-18 — C5b landed.** Tier 3 is deleted (retain-facing and departure-side
direction moved into the engine — `reference/archive/WARP_RETAIN_FACING_PROPOSAL.md` §0, `reference/archive/REDERIVATION_PLAN.md`
§16.3 C5b). The rule below was never implemented in `metadata_wiring`; its idea survives as
the approach model of `tests/test_warp_facing_invariant.py`, which floods `traversal.graph`
reachability from every way into a map (warp cells as barriers, door landings seeded to a fixed
point) — and under that model all three former hand overrides follow from the source data
(`test_former_hand_overrides_now_follow_from_retain`).

`metadata_wiring.compute_arrival_facings` tier 3 derives a `dest_dir=0`
("retain facing") arrival by finding the source warp's single open,
non-sibling, unblocked neighbour (`metadata_wiring.py:3025-3040`). It looks
only one tile out, so it counts a neighbour as a candidate approach even when
nothing can reach that neighbour except the warp tile itself. Two vertically
opposed open tiles then read as ambiguous and it raises, pushing the case to
`reference/warp_facing_overrides.json` as a hand decision.

**The rule it is missing** (operator's, 2026-09-04): a tier-3 survivor is a
genuine approach tile only if *it* has an open neighbour other than the warp
tile — otherwise you could never have stood there to walk in.

**Measured against the current slice**, applying that second-order check to
every ambiguous retain-facing warp:

| warp | tier 3 survivors | second-order |
|---|---|---|
| map35 (20,33) -> `36:17:39` | (20,32), (20,34) | **unique** -> `DIR_NORTH` |
| map36 (17,4) -> `37:16:26` | (17,3), (17,5) | **unique** -> `DIR_NORTH` |
| map33 (70,12) -> `32:8:43` | (69,12), (71,12) | still ambiguous |
| map33 (70,11) -> `32:8:43` | (70,10), (69,11), (71,11) | still ambiguous |

So it resolves both CH05 cases and neither CH03 one — a real reduction in hand
overrides, **not** a complete replacement for the file. Both CH05 rows were
hand-entered during CH05 (`DIR_NORTH` each) and agree with what the rule
derives, so implementing this must reproduce them exactly; that agreement is
the regression test.

**Do not** delete `warp_facing_overrides.json` when this lands — the map33 pair
still needs it, and per its own `_comment` the file remains the source of truth
for a corrected facing. Prototype scan lives in this item's history; re-derive
rather than trusting a pasted table.

### 97. Recognition and emission are two unlinked layers, so rows are flagged for work already done -- DONE 2026-09-12

*(2026-10-04: closed. The manifest-vs-transpiler drift guard is `tests/test_manifest_transpiler_divergence.py` (`ea7e6eef`, 2026-09-12); the page-condition script text is now classified in `chapter_manifest/generator.py` (`script_condition_texts`, P8b ruling 2, P8b closed 2026-10-03); the `pbRockSmash` duplicate key is gone. Verified in code, not by a fresh run. The increment half of that family is #99, still open.)*

**Root-caused 2026-09-11** (`reference/archive/REDERIVATION_PLAN.md` §14.1). A manifest row's
`unrecognized_heads` / `other_codes` — and therefore `ManifestRow.is_dispositionable`
(`chapter_manifest/schema.py:407-414`) — are judged **only** against two small,
hand-maintained tables local to the manifest tool:

- `_CODE_EFFECT` (`src/rpg2gba/chapter_manifest/generator.py:82-107`) for RMXP command codes
- `MECHANIC_BY_HEAD` (`src/rpg2gba/chapter_atlas/census.py:78-135`) for Ruby script heads

Neither is ever checked against `src/rpg2gba/conversion_agent/transpiler.py`, which is the
actual conversion spine. `generator.py:600-604` documents the gap in passing. So a
code/head the transpiler handles perfectly still reads as un-dispositionable until someone
remembers to add it to a second table in a different package.

**Measured blast radius on CH01+CH03 alone: 6 of the 28 undispositionable rows, plus part
of 2 more, were flagged for work already done** — codes 104 (`_STRIP_CODES`,
`transpiler.py:114`), 116 (`removeobject`, `:1898-1900`), 221/222 (`fadescreen`,
`:1945-1950`), and the heads `pbPokerus` (predicate hard-folded at `:567-577`) and
`pbNextMysteryGiftID` (`_emit_mystery_gift_id_strip`, `:2338-2358`, a user-approved strip
dated 2026-08-19). Adding a head today takes four edits across two packages and step four
is the one that gets forgotten.

Fix direction: derive the recognition vocabulary from the transpiler, or make divergence
fail loud — a test that asserts every head/code the transpiler handles is present in the
manifest tables, and vice versa. §14.1 item 1 does the minimum (adds the missing entries);
this item is the structural fix so the drift cannot silently return.

**The corpus's largest instance of this item is in page CONDITIONS, not command bodies
(measured 2026-09-12, `reference/archive/REDERIVATION_PLAN.md` §14.6).** 110 of the 128 citation-owing rows owe
their citation *solely* to `script_typed_conditions > 0`, and the heads inside those
conditions — `get_character`, `pbItemBall`, `pbTrainerBattle`, `pbRockSmash`, `pbPickBerry`,
`pbHasSpecies`, `pbPhoneBattleCount` — are **already in the transpiler's recognized set**.
`generator.py:575-580` counts a code-111 / `COND_TYPE_SCRIPT` condition and discards
`params[1]`, so the recognition that exists is never applied to the text. The 147 instances
collapse to 14 idiom families, 10 of them judgment-free. P8b's ruling-2 classifier
(§14.6) is the fix for this half; this item remains the structural fix for the tables
themselves.

Also found while inventorying: `MECHANIC_BY_HEAD` declares `"pbRockSmash"` twice
(`census.py:90` and `:109`), the second silently shadowing the first — same value, so no
behaviour change, but a duplicate-key guard belongs in this item's fail-loud test.

### 98. The transpile queue is 1-based on `page`; manifest row ids are 0-based -- DONE 2026-09-12

**DONE 2026-09-12** (`7e2e2668`; was in scope for P8b, `reference/archive/REDERIVATION_PLAN.md` §14.8 ruling 2). *(2026-10-04: verified — the queue writer now emits 0-based pages; `chapter_manifest/generator.py::_load_unhandled_counts` documents the fix.)*

`output/uranium-build/transpile_unhandled.jsonl` writes `page` **1-based**; a manifest
`row_id`'s `pN` suffix is **0-based**. Verified against page counts: `map050/ev004` has 3
pages and the queue reports page 3 (= manifest `p2`); `map050/ev005` has 8 pages and the queue
reports 6 and 7 (= `p5`, `p6`).

Two failure modes, both silent:

- a queue entry is attributed to the page *before* the one it came from;
- **manifest `p0` can never match a queue entry at all**, so a genuinely-queued first page
  reads as clean.

This is how three rows were attributed to a label bug they do not have (§14.8 table). Fix:
normalize the **queue writer** to 0-based — manifest `row_id`s are load-bearing inside
committed `.dispositions.json` files and must not move, while the queue is regenerated output.

Third instance of the standing lesson that a measurement taken through a generator attributes
its own bugs to whatever it was measuring (cf. #95, #97).
