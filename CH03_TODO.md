# CH03 TODO — Kevlar Town (maps 31, 67, 68, 73, 19)

Live work checklist for chapter CH03 (Kevlar Town), the current build
frontier. The chapter's spec, story beats and coverage targets live in
`reference/chapters/03-kevlar-town.md`; the corpus-wide plan is
`reference/chapters/00-atlas.md`. This file tracks only *work items*, not
design. Same conventions as `reference/archive/CH02_TODO.md`: commit updates
as items close; move an item to **Done** with a one-line result rather than
deleting it. Facts here are pointers — the cited code/docs stay authoritative.

Seeded 2026-08-12, immediately after CH02 passed its §9 gate.

**Approach for this chapter (user directive, 2026-08-12):** drive the build
from the **playtest dev path** — the headless chapter suite is the primary
iteration loop, not a final gate. Target is a ROM as close to "complete" as
the data allows before it is handed over for the §9 walk. Standing rule from
`ROM_TEST_DEV.md` F1 still binds: no ROM is taildropped for §9 review unless
the chapter suite is green on that exact build.

## Approved scope

The **beat list was approved by the user 2026-08-12, before any build work**
(that approval order was the user's explicit ask). It is reproduced in
`src/rpg2gba/playtest/chapters/kevlar.py` as the scenario itself; the source
of truth for what the chapter *is* remains the spec doc. Shape:

- **25 positive beats B1–B25** — arrival from Route 1; NurseTut walkthrough;
  Pokémon Center (heal, respawn point, PC-tour Oran Berries, Antidote ball,
  Mawuli's repeatable battle); Poké Mart (purchase, Deliveryman); Map031
  berry plants; Berry Boutique (berries + Sprinklotad, second shop list);
  Bike Repair refusal branch; 2 flavor houses; Magikarp gift; Cry Boy idle
  page; the map19 cave (3 boulder pushes, Bikers Lou/Joe, Richard →
  `FLAG_SIDEQUEST_CRYBOY_END`); cave exit; north frontier.
- **6 negative beats N1–N6** — no second Antidote, no second Magikarp,
  NurseTut re-talk is the no-op page, purchase refused when broke, boulder
  will not push into a wall, no reachable warp targets an unbuilt map.
- **4 deferred beats, written but not registered** (same convention as CH02's
  `DEFERRED_ROCK_GATED`): Bike Wheel → Bicycle (wheel's source is Route 4,
  CH11), Cry Boy accept (sw86 never set true corpus-wide), Compensation Man's
  Luxi (sw130 reads as a dev save-recovery flag), Richard's post-Gym-5 team
  (sw94).

## Decisions taken at scope time (user, 2026-08-12)

1. **Map 73 identity** = `Kevlar Town Buildings` / `KevlarTownBuildings` /
   `MAP_KEVLAR_TOWN_BUILDINGS` — needs a `reference/map_name_overrides.json`
   entry (item #1).
2. **Map 19 identity** = `PassageCaveGrottHole` /
   `MAP_PASSAGE_CAVE_GROTT_HOLE`, **overwriting** the existing *reviewed*
   override entry, which describes map 19 as the through-cave. The warp trace
   (spec §2: map19's only `code-201` returns to map31) and the wiki's own
   Grott-Hole subsection (spec §5 #2) both contradict that entry.
3. **North frontier** = clean impassable wall. The Kevlar↔Route 2 boundary is
   a `connections.dat` seam, and seams are unconverted engine-wide; no
   blocker NPC is authored. B25 asserts the edge is sane, not that it warps.
4. **Pokérus check and Mystery Gift** = no-op analogs. Dialogue survives, the
   mechanic does not exist.
   - **Update 2026-08-14:** the `Map068_EV001_Page1` healing counter's YES
     branch drops its whole `pbPokerus?` conditional (`UNHANDLED code 111`),
     and that conditional turns out to wrap the *entire* rest of the scene --
     not just Pokérus-specific dialogue, but the nurse's return-facing
     movement and the two closing messages ("healed to perfect health" /
     "we hope you excel") that both branches presumably share. Dropping the
     branch entirely (not just no-opping the Pokérus check inside it) is a
     stopgap: it silently truncates the healing scene, which real playthrough
     testing caught (playtest's B4 beat did not -- it has no assertion on
     final message text, the return movement, or `FLAG_STARTING_OVER`, so a
     script that releases control early reads as a clean pass). Pokérus
     itself is deferred to CH18 (Nuclear Plant Epsilon, its home chapter --
     see `reference/chapters.json`); when it's implemented there, come back
     and re-emit Page1's full completion sequence with a proper no-op stand-in
     for the Pokérus branch instead of dropping the conditional wholesale.

## Current status (2026-08-13, end of the first build session)

**ROM `4a9dc830` builds clean** (27.36/32 MB, EWRAM 86.8%, IWRAM 87.0%);
**2068 tests pass**, 19 skipped. Nothing is committed yet — the whole session is
in the working tree.

**Chapter suite `kevlar`:** predecessors green — moki 17/17 and route1 29/29 on
this build, so none of the six converter fixes below regressed CH01/CH02. Of
CH03's own beats, **B1 and B2 pass**; the run halts at **N3**, whose walk into
the Center is interrupted by a locked-field autorun (`OnFrame` dispatches
Map068 EV012 page 2 while `FLAG_MAP068_EVENT012_TSA` is unset). That is
probably beat authoring — the scene needs absorbing, the way route1's
`_walk_absorbing` does — **but it carries a fidelity question first**: the
guard is a *temp* switch, so the scene re-fires on every entry to the Pokémon
Center. Check the RMXP page before deciding whether that is faithful.

**The chapter is NOT converted yet.** The 81-entry unhandled queue is
untouched (#4 below): no trainer battles (verified — zero `trainerbattle` in
any CH03 `scripts.inc`), no boulder pushing, no `givemon` for the Magikarp, no
`giveitem` for the PC tour or Berry Boutique. Beats covering those are written
against the real designed behaviour and will legitimately fail until the queue
is worked. A green build is not a converted chapter.

**Six converter bugs fixed this session** (#7, #10, #11, #12, #13, #15) plus a
build-set wiring miss (#16). Every one was found by the build or the harness,
not by a boot walk.

## Open

### 15. Everything after a `warp` was dead code — FIXED 2026-08-13

RMXP's interpreter keeps running an event page after a `code-201` Transfer
Player; pokeemerald's does not (`ScrCmd_warp` → `DoWarp()` + `return TRUE`,
`engine/src/scrcmd.c:969`, and the context dies with the map change). Every
command the transpiler emitted after a warp was therefore silently dropped on
the floor.

Caught by beat B2: NurseTut walks the player into the Center and Uranium sets
switch 126 *after* the transfer, so `FLAG_NURSE_TUTORIAL` never got set.

**Corpus scope: 981 pages continue after a Transfer Player** — 584 with state
writes (2 pure, 582 alongside benign screen-tint/no-op tails) and 397 with
genuinely destination-side content. The transpiler now hoists *unconditional*
`code-121/122/123` state writes above the warp (with a comment in the emitted
Poryscript saying why the order differs from the RMXP page), never lifts a
write out of a conditional, and routes every other post-warp command to the
unhandled queue — **176 such entries across the build set**, previously
invisible. Not a hard error: 397 pages corpus-wide hit it, several in chapters
that already passed their gates.

**CH01 and CH02 both passed §9 with this bug live.** Their beats simply never
asserted a post-warp state write. Worth a targeted re-check of those chapters'
post-warp tails now that the queue makes them visible.

### 16. Route 01's half of the seam was never wired — FIXED 2026-08-13

I added map31's south doors to `WARP_OVERRIDES` and missed Route 01's own
north pair, EV045/EV046 at (15,5)/(16,5). Without an entry the layout never
stamps a door metatile, so the warp is inert — the documented failure mode for
that table. Beat B1 caught it immediately: the player walked the seam and
stayed on Route 01.

`route1:B17` was revised in the same breath. It asserted the north boundary was
an impassable wall *because Kevlar was unbuilt*, and its own comment predicted
this: "A future chapter extending the frontier to Kevlar Town should revisit
this beat." It now stops one tile short and leaves the crossing to `kevlar:B1`,
which keeps the chain's end-state contract (CH03 starts from Route 01, not from
inside Kevlar). The retired wall assertion is kept in the file, unregistered,
as a record.

### 1. Map identity overrides for maps 73 and 19

Add both entries to `reference/map_name_overrides.json` per the decisions
above. Map 19's is an **overwrite of a "reviewed" row**, so it needs the
correction reason recorded in the entry, not a silent replacement.

### 2. Add the 5 maps to the build set

Per `reference/guides/slice_expansion_runbook.md`, in order, and note that
these are three *separate* literals that must not drift apart:

- `src/rpg2gba/tileset_converter/map_set.py` — `SLICE_MAP_IDS` (cumulative:
  CH01 8 + CH02 2 + CH03 5 = 15 maps)
- `scripts/stage_slice_scripts.py` — `ALLOWED_MAPS` (miss it → the new maps'
  warps get pruned as out-of-slice and the doors go inert)
- `scripts/assemble_pathfinder.py` — `WARP_OVERRIDES` for each new door
  source coord (miss it → the cell never gets a door metatile)

Blocked on nothing, but do it *after* the recon in #3 so we don't add a map
we then have to pull back out.

### 3. Recon: event-conversion load and art budget

Two read-only recon passes commissioned 2026-08-12 (transpiler dry run over
maps 31/67/68/73/19; per-map tile/metatile/palette budget + NPC sheet
coverage). The spec's §6.3 flagged conversion-readiness as **unmeasured** for
all five maps and the tileset/art budget as never assessed.

**Transpiler dry run — done 2026-08-12.** No hard errors, no fork-capability
gate failures on any of the five maps. **81 unhandled entries over 29 of 85
events; 56 events (66%) transpile clean as-is.** Per map, clean/total events:
31 → 35/40, 67 → 6/9, 68 → 11/18, 73 → 4/11, **19 → 0/7**. Map19 (the cave)
is the concentrated risk — every event queues something (boulder push, the
three Biker fights). Map73 is second (shop item-lists + bag-quantity gates,
documented and low-risk).

*Counting note that will otherwise be re-learned:* the raw CLI prints
**169** queued, but 88 of those carry `map_id=None` — `common_events.json` is
recomputed corpus-wide every run regardless of `--maps`. Do not budget CH03
against 169.

Unhandled, bucketed:

- **Expected per spec §4.1/§4.2/§6.2/§6.3** — `pbPushThisBoulder` ×5,
  `get_character`/`pbNoticePlayer` ×3, `pbNextMysteryGiftID`, `pbPokerus?`,
  `pbPokemonMart` + its item-list continuation lines (~20, two shops),
  berry `pbReceiveItem` continuations ×4, `SPRINKLOTAD`/`BIKEWHEEL` bag-qty
  gates ×4, and the 5 `pbTrainerBattle` calls wrapped in `code-111` (the
  corpus-wide trap the spec already called).
- **Classifier near-misses** (mechanic is native, only the script form is
  uncaught) — `pbTrainerIntro(:BIKER)`/`pbTrainerEnd` ×3 each,
  `pbAddPokemon` ×2, `$game_variables[43]=party.length` ×2, and
  **`pbPokeCenterPC`**, which still queues raw even though §6.1 records PC
  access as already-native since CH01. That contradiction is worth resolving
  before #4 is worked.
- **Novel, not in the spec at all** — 8 Transfer-Player placeholder warps
  (unresolved `MAP_*`, expected to clear once #1/#2 land),
  `$PokemonGlobal.seenStorageCreator`, 2 character-facing conditionals on
  map31, an untranslated `\b` dialogue control code on map67,
  `$PokemonGlobal.nuzlocke` on map68, and a **choice menu listing the three
  starters inside the Pokémon Center (map68)** — unexpected there; eyeball it
  before writing a beat around it, it may be dead script text.

**Art / budget recon — done 2026-08-12.** No map is near a hard cap, and none
is in `WALKER_OVERFLOW_MAP_IDS`/`WALKER_EMPTY_MAP_IDS`. Per-map synth tilesets
mean sibling map sharing is irrelevant to budget.

| map | ts | dims | metatiles* | 8×8 tiles | palettes | max anim frames |
|---|---|---|---|---|---|---|
| 31 | 22 | 50×50 | 257 | **779 / 1024 (76%)** | 13/13 | 19 |
| 67 | 4 | 20×15 | 57 | 147 | 13/13 | 4 |
| 68 | 42 | 20×20 | 118 | 275 | 13/13 | 4 |
| 73 | 19 | 70×15 | 112 | 305 | 13/13 | 4 |
| 19 | 32 | 30×34 | 75 | 214 | 13/13 | 1 (static) |

\* **proxy, lower bound only** — a topmost-visual-tile count, not the
column-key/layer-composite count `build_slice_tilesets` actually produces.
The real number arrives at first emit; do not treat these as cleared.

- **13/13 palettes everywhere is the packer filling its allowance, not
  overflow** (map31's uncapped natural need is 417). Quality cost is color
  shift: p95 5-bit shift 2.33 / 2.00 / 1.33 / 2.33 / 0.00 — under the 3.0
  accept threshold but above Moki's validated 0.95 baseline. Eye-check the
  quantized art before the walk (§9 by-eye category anyway).
- **Map031 is the map to build first**: 76% tile usage *and* the only real
  animation load (31 autotile ids, a 19-frame water column). Frame count is
  far under the 128 `MAX_COLUMN_FRAMES` guard and no 19×5 stacking was found
  (that would be lcm 95), but the `MAX_ANIM_ROM_BYTES` 128 KiB/tileset cost
  was **not** measured — it needs a real `emit_tileset` pass.

### 6. 22 missing NPC sheet entries in `reference/npc_gfx_map.json`

Only HGSS_001/007/008/009 of the chapter's sheets are registered. Missing:
HGSS_016, 023, 024, 027, 028, 033, 038, 039, 045, 056, 126, 134, 135, 179,
185, 267, PU-Owten, PU-doorsdew, berrytreePECHABERRY, door2, light,
"pokeballs on left", "pokeballs on right".

Sub-question before minting all 22 the same way: the trailing group
(`door2`, `light`, `pokeballs on *`, `berrytree*`) look like object/prop
graphics rather than walking NPCs, and may not want walk-sprite treatment.
Their event bodies weren't inspected — check before deciding.

**Watch the sprite-palette union while adding these.** All converted NPC
sheets share ≤4 sprite palette banks (the player owns a 5th); overflow is
*silent* color garbage on hardware, not a fail-loud. 22 sheets in one chapter
is by far the largest single addition so far — re-check the union after the
batch, and expect this to be the item that forces the per-map packed-bank /
dynamic-tag scheme the corpus audit already prescribed (finding #4).

### 4. New mechanics this chapter introduces

- **Poké Mart** (`pbPokemonMart`) — first appearance; native `pokemart`,
  classifier 9. Two distinct shops (map67 Mart, map73 Boutique) share it.
- **Boulder pushing** (`pbPushThisBoulder`) — first appearance;
  **object-driven** `OBJ_EVENT_GFX_PUSHABLE_BOULDER`, **not**
  `MB_PUSHABLE_BOULDER`. The ledger corrected this once already — do not
  re-invert it.
- **`pbSetPokemonCenter`** — healing-location metadata; verify the native
  analog in the fork before writing anything custom (§4.7).

### 5. Chapter scenario module

New `src/rpg2gba/playtest/chapters/kevlar.py`, `ChapterBuilder("kevlar",
doc="reference/chapters/03-kevlar-town.md", predecessor="route1")`. No
registration anywhere else — `chapter_names()` auto-discovers the module.
Full suite on green = moki 17 + route1 29 + kevlar's own.

## Done

### 1. Map identity overrides for maps 73 and 19 — DONE 2026-08-12

`map_name_overrides.json` gained `Kevlar Town Buildings` (73) and
`Passage Cave Grott-Hole` (19, overwriting the stale *reviewed* through-cave
verdict, original text preserved in the entry), plus paren-normalization for
67/68. Engine dirs now `KevlarTownBuildings/` + `PassageCaveGrottHole/`.

**This uncovered a real converter bug — see #7.**

### 2. The 5 maps are in the build set — DONE 2026-08-12

`SLICE_MAP_IDS` (15 maps cumulative) + `WARP_OVERRIDES` (9 doors on map31,
plus the interior exits on 67/68/73/19 — map31 EV049 "NurseTut" carries a
`code-201` but is a PERSON, deliberately not listed or her tile grows a
door). `ALLOWED_MAPS` is now **derived** from `SLICE_MAP_IDS` rather than
hand-listed — that duplicate literal was the documented hazard of every map
addition. `chapters.json` CH03 status `planned` → `in_progress`, and
`test_chapter_atlas`'s build-set assertion now derives from status instead of
a hardcoded `CH01 + CH02` pair.

### 6. The 22 missing NPC sheets — DONE 2026-08-12

All registered in `npc_gfx_map.json` with fork-verified fallbacks. Findings:
`PU-doorsdew` needed no entry (door-family prefix, stripped before gfx
lookup); `HGSS_267` is the pushable boulder prop; no sheet needed a `states`
map. `light` was deliberately NOT registered — see #8.

### 8. The seven "Luz" ambient lights — STRIPPED 2026-08-12

Map031 EV011/017/028/029/030/032/033, byte-identical in shape to Route 01's
Map033 EV028, which the user ruled no-port on 2026-08-05 (additive
alpha-gradient glow, no GBA analog). Applied that ruling to all seven in
`strip_list.json`. The sprite pass fails loud on the sheet
(`light: content bbox 46x45 exceeds the 32x32 GBA object frame`), which is
the same 800×800 sheet the original ruling describes.

### 9. The Center's Antidote — ONE-TIME, user-ruled 2026-08-12

Map068 EV018 is malformed against every other item ball in the corpus: one
page, no ball graphic, no self-switch gate. It sets self-switch A and nothing
reads it, and `Kernel.pbItemBall` (`101__PField_Field.rb:2303`) sets no
switch itself — so on PC it is an invisible, **infinitely repeatable**
Antidote on a passable, reachable Center floor tile.

Census settling how unusual that is: 279 `pbItemBall` events corpus-wide, 242
standard two-page, 37 not — and 36 of those 37 are the visible `PU-Coral`
harvest nodes on the underwater maps 107/118, which are repeatable by design.
Map068 EV018 is the only invisible one, the only one in a Pokémon Center, and
the only ball of any kind in any Pokémon Center.

User ruled **one-time**: the native `STD_FIND_ITEM` template has no
repeatable mode, so "faithful" would mean forcing it off the native path into
bespoke script machinery for one shipped bug. New
`metadata_wiring._ungated_item_ball_flag` reuses the self-switch flag the
event already sets — deliberately scoped to events already classified as
item-ball templates, because "sets a self switch nothing reads" is ordinary
NPC bookkeeping and widening the general rule would despawn NPCs after one
conversation.

### 10. Door animations targeting warp-converted doors — DONE 2026-08-12

In RMXP a door is an event that animates itself before transferring; we
convert such events to **warps**, so they have no local id and any
`applymovement` at them cannot be remapped. This never surfaced before
because those calls only ever appeared inside the door's own script block,
which `prune_orphan_blocks` deletes. CH03 is the first chapter where an
outside event animates a door: map31 EV049 walks the player to the Center and
opens it.

New `local_id_remap.strip_unemitted_door_movements` drops such
`applymovement` + paired `waitmovement(0)` (identified from map data —
a `code-201` in the event's pages — never from the sheet name, since map31's
doors use `door2`, which does not match `is_door_sheet`'s `PU-doors`/`FKdoors`
prefixes). Anything else absent from the remap table still fails loud. Real
run: 4 drops, all on Map031; every other map 0.

**Known upgrade path:** the fork ships native door animation (`opendoor` /
`closedoor` / `waitdooranim`, `engine/asm/macros/event.inc:1549-1563`), but it
is driven by per-tileset door-animation graphics keyed to an *animated* door
metatile, while our warp cells are stamped `MB_NON_ANIMATED_DOOR`. Wiring it
is an art/tileset job, not a script substitution.

### 11. The PC storage-creator flag — CONVERTED, not stripped 2026-08-12

Map031 EV049's third page is an autorun whose whole body is
`$PokemonGlobal.seenStorageCreator = true`. I proposed stripping it as
Essentials-only bookkeeping; **the user identified the real analog** — a PC is
"SOMEONE'S PC" until you meet its creator. The fork has exactly this:
`FLAG_SYS_PC_LANETTE` (`flags.h:1438`) switches `script_menu.c:751` between
"LANETTE'S PC" and "SOMEONE'S PC". So it converts to
`setflag(FLAG_SYS_PC_LANETTE)`. Corpus census: 3 occurrences, 2 maps (map31
EV49 pages 0 and 2, map42 EV3), all `= true`, no `false` anywhere — so no
`clearflag` path was guessed.

Second half: the page still had to stop re-firing. `compute_autorun_entries`
now negates into an autorun page's guard the flags its own body writes, when
none of them already appear there — so the page runs once and deactivates.
The dispatcher now reads
`if (flag(FLAG_DEFEATED_GYM1_LEADER) && !flag(FLAG_SYS_PC_LANETTE))`. The
`check_onframe_deactivation` gate is untouched and still fails hard for pages
that write nothing at all.

### 12. `call CommonEvent_NNN` never assembled — FIXED 2026-08-12

Poryscript has a bare `goto Label` keyword but **no bare `call Label`**. Written
that way it parses as two separate bare commands and passes both through, so the
assembler received `call` with no operand followed by a stray `CommonEvent_004`
instruction:

```
Error: Missing value for required parameter `destination' of macro `call'
Error: bad instruction `commonevent_004'
```

Both emit sites (`deterministic.py` CALL_COMMON_EVENT, `transpiler.py`
CALL_COMMON_EVENT) now emit `call(CommonEvent_NNN)`, and the sibling detector in
`deterministic.py` matches the new prefix.

**This means common-event calls have never assembled in any chapter.** MEMORY's
note that "the current slice calls no CEs" was true for CH01/CH02, so the bug sat
unexposed until map68 became the first map to call one (CEs 4/5/6). Five tests had
pinned the broken form; they asserted output that cannot assemble and were
corrected rather than the code.

### 13. The alias header desynced from the map registry — FIXED 2026-08-12

`uranium_map_aliases.h` (`#define MAP_URANIUM_<N> MAP_<NAME>`) is **derived** from
the mint state, but only the *Map Walker* path ever regenerated it. The real
pipeline minted into the state and left the header alone, so after #7's re-mint
`MAP_URANIUM_19` still resolved to `MAP_PASSAGE_CAVE` while `map_groups.h` defined
only `MAP_PASSAGE_CAVE_GROTT_HOLE` — build death with a bare
`asm/macros/map.inc:9: Error: undefined map (check for typos)`, no mention of
which map or which script. `stage_slice_scripts` now rewrites the header
immediately after `build_map_constants`, so it cannot outlive a re-mint.

### 14. Orphaned engine map dirs from past renames — CLEANED 2026-08-12

`engine/data/{maps,layouts}/MokiTownTheo{,172}/` were walker-era directories for
maps 172/89, left behind when those maps were renamed to
`MokiTownTheosHouse1F/2F`. Their `map.json` named layout constants that no longer
exist, so `mapjson` refused them, never wrote their `connections.inc`, and make
died with `No rule to make target 'data/maps/MokiTownTheo/connections.inc'`.

I first read those `mapjson` complaints as harmless noise — they are fatal. A
sweep found exactly 2 such orphans corpus-wide, both gitignored; removed.

**Follow-up (not done):** #7 stops NEW drift, but nothing sweeps debris left by
PAST renames — the assembler should detect engine map dirs whose layout constant
is absent from the generated manifest and fail loud or clean them. Belongs in
`PROJECT_TODO.md`.

### 7. Stale minted map identities silently ignored overrides — FIXED 2026-08-12

Found because #1's overrides had no effect: the assembler happily emitted
`PassageCave/` and `KevlarTown73/`. `MapConstantRegistry.mint()` returned
early for any id already in its persisted state without ever comparing the
identity it was handed, so **`map_name_overrides.json` — the §4.3 source of
truth for map identity — was dead for every already-minted map.** Maps 19 and
73 had been minted long ago by the *Map Walker* corpus build, which runs with
`auto_disambiguate=True` and had suffixed them.

`mint()` now recomputes the candidate identity every call, re-mints on drift
with a WARNING naming old → new, collision-checks a re-mint exactly like a
fresh one (failing loud), and stays a silent no-op when nothing changed.
Walker suffixing is not itself drift.

Stale generated artifacts from the rename were cleaned: `engine/data/maps/`
and `engine/data/layouts/` dirs for both old names, the orphaned
`porymap/maps/` dirs, and 2 stale rows in the upsert-only
`staging/layouts/layouts.json`. The build-consumed manifests regenerate from
the registry each assemble, so only the staging intermediate had rot.
