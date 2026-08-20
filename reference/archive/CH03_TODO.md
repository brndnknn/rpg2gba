# CH03 TODO — Kevlar Town (maps 31, 67, 68, 73, 19)

**RETIRED 2026-08-19 — CH03 passed its §9 boot-walk gate** (kevlar chapter
suite GREEN 60/60, ROM `c3e75d4f`). Carryovers were already migrated to
`PROJECT_TODO.md` #39-#42 ahead of the gate (see "Current status" below); the
one remaining loose end is Sprinklotad's own grant, unasserted because no
registered beat drives its second interaction (#25 item 3) — a scope call,
not a defect, left here rather than filed as its own item. Kept for the Done
ledger and the detail the migrated entries point back to.

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

## Current status (2026-08-19)

**ROM sha256 `c3e75d4f` is the chapter-complete build** — produced by the full
pipeline exiting 0 end to end on `engine/` (transpile → stage → assemble →
`make modern`), stamped at `output/playtest/review/kevlar-complete.json`
(2026-08-19T17:13Z) with the review ROM, six contact sheets and
`output/playtest/walk/kevlar-B1.gba` beside it.

**Chapter suite `kevlar`: 60 beats, 60 pass, 0 fail**, predecessors replayed
green, chapter-complete stamp green. Full `pytest -q`: 2190 passed, 19 skipped,
0 failed. B19–B24 remain **deferred, not failing** — the Grott-Hole is sealed by
Strength-gated boulders and Strength arrives in CH25 (#20 / `PROJECT_TODO.md`
#39). That is the game working, not a converter gap.

**The queue is 38 entries across the five maps** (map19 17, map31 14, map73 4,
map68 2, map67 1), down from 50 after the 2026-08-19 triage (`4da46a2e`).
Counted from `output/uranium-build/transpile_unhandled.jsonl`; the file's
map-less records are common-event scoped, not CH03.

**None of the 38 is CH03 work.** The triage found the 50 split three ways and
nine real items, all nine now converted:

- **19 → CH25** — all 17 of map19 (3 boulders + the Biker encounters) and 2 of
  map31 (the outdoor boulders). `PROJECT_TODO.md` #39.
- **7 placeholder-warp bookkeeping** — the Phase-5 alias header already resolves
  them (`uranium_map_aliases.h` defines `MAP_URANIUM_31`).
- **13 post-warp presentation commands** — stranded after a Transfer Player
  warp, and the compiled map header supplies what they would have set.
  `PROJECT_TODO.md` #40. B31 proves the BGM half in the running ROM (reads
  `gMPlayInfo_BGM.songHeader` through `gSongTable` and compares against the
  destination map's own `music` key); the 9 `CHANGE_TONE` fades are **still
  unasserted and deliberately not claimed**.
- **The nine real ones, converted 2026-08-19** — player-facing conditionals,
  bag-quantity conditionals, `pbDeleteItem`, party-length reads, the 3-option
  starter choice, `\b`/`\C[n]` colour codes, and the nuzlocke / Mystery Gift
  unsatisfiable guards (user-approved strips). Plus the Luxi family staged
  (fork ids 1597–1599) so Map031 EV050's gift converts.

**Item grants work end to end and the beats now assert the bag** (#25): shapes
B and C emit `giveitem`, the four Uranium berries and Sprinklotad exist as
engine items, Sprinklotad's bag-quantity gate converted in the same 2026-08-19
pass, and B5/B7/N1/B14 read `bag_item_quantity` rather than trusting a
self-switch. Sprinklotad's own grant is the one thing still unasserted — no
registered beat drives the second interaction it hides behind (#25 item 3).

**Warp-arrival facing is verified in the ROM, not just in metadata** (#22):
B27/B28/B30/B32 drive the real `ON_WARP_INTO_MAP_TABLE` script, with
expectations late-bound off this build's own staged slice.

**Nine converter bugs fixed** (#7, #10, #11, #12, #13, #15, #17, #25, plus
Mawuli's facility battle) and a build-set wiring miss (#16). Every one was found
by the build or the harness, not by a boot walk.

**Remaining before the §9 gate: the boot walk itself.** Nothing in this file is
a build-side blocker, and the chapter's coverage no longer has a
flag-instead-of-effect hole in it. Carryovers that CH03 surfaced but does not own are filed
in `PROJECT_TODO.md` (#39, #40, #41, #42); on gate pass this file archives to
`reference/archive/CH03_TODO.md`.

## Open

### 22. Warp-arrival facing landed everyone facing DOWN — FIXED + ROM-VERIFIED 2026-08-19

Reported for the Kevlar Town entry, Poké Mart, Poké Center and flower shop
(other Kevlar buildings were fine): warping in faced the player DOWN instead
of away from the return warp. Root cause: `GetAdjustedInitialDirection`
(`engine/src/overworld.c:1060-1087`) defaults to `DIR_SOUTH` unless the
landing tile's metatile behavior says otherwise, and arrival tiles are
deliberately plain floor. The existing correction mechanism
(`compute_arrival_facings`) had been skipping every RMXP `dest_dir` of 0/None
("retain current facing") since 2026-07-16 — all four broken destinations had
`dest_dir == 0`; the working buildings had `dest_dir == 8`. That 2026-07-16
call is now superseded.

Fix (committed as `61140331`, see below):
`compute_arrival_facings` now resolves dest_dir 0/None via a new
`_derive_retain_facing` — single non-blocked, non-warp-source neighbour of the
source warp cell ⇒ face away from it — behind a new hand-override tier,
`reference/warp_facing_overrides.json` (1 entry: Route 1's 3-tile warp stack
into Moki Town, a real corridor where derivation is genuinely ambiguous). All
6 broken warps now derive `DIR_NORTH`. Files: `metadata_wiring.py`, new
`reference/warp_facing_overrides.json`, `tests/test_tileset_converter.py`, new
`tests/test_warp_facing_invariant.py` (corpus-wide, chapter-agnostic, plus a
hard regression pin on the 5 Kevlar arrival coords). Full suite green: 2144
passed / 19 skipped / 0 failed.

Side finding, left as-is: maps 49/172 (Moki stairwell) have a Uranium-authored
arrival facing into a wall (`dest_dir=4`); reproduced faithfully, pinned in
`test_uranium_authored_wall_facers_are_pinned`, needs a user fidelity call
(reproduce vs override) — see MEMORY.md Open Questions.

Committed on `ch03-kevlar` (`61140331`). **Closed 2026-08-19:** the fix was
pinned only at the metadata layer, so B27/B28/B30/B32 now drive the real
`ON_WARP_INTO_MAP_TABLE` script in the running playtest ROM — the expectation is
computed by running `compute_arrival_facings` over this build's staged slice at
beat runtime, so a converter change that shifts a facing fails the beat instead
of leaving a stale literal green. Note for anyone re-checking this: it **cannot**
be exercised on the map-walker build — `InitObjectEventsLocal` guards
`TryRunOnWarpIntoMapScript()` behind `#if URANIUM_MAP_WALKER != TRUE`
(`overworld.c:2590-2597`).

The dispatch does an **exact** compare against `getplayerxy` with no tolerance,
falling through to the engine's `DIR_SOUTH` default on any miss — an
`_assert_near` tolerance of 1 masked landing one tile off while these beats were
being written. Keep the assertions exact.

**Still a user call:** maps 49/172's Uranium-authored wall-facer (below) is
reproduced faithfully and pinned; it is a fidelity decision, not a bug.

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

### 17. The Mart counter did nothing on A — FIXED 2026-08-16

Talking to the Poké Mart counter produced no dialogue and no menu. Two
independent things had to line up for it to look like a total no-op.

**The clerk's script was a stub.** `Map067_EV001_Page1` compiled to
`lock / faceplayer / setflag(FLAG_MENU_ON_EVENT) / clearflag / release / end`
— its `pbPokemonMart([...])` had become eight `# UNHANDLED code 355` comments.
RMXP stores a Script command as a code-355 row plus one code-655 row per
continuation line, and the transpiler matched every row independently, so a
call the script editor wrapped could never match an idiom. `classify_pokemart`
in `deterministic.py` does join rows correctly, but it bails on any command
that is not 355/655/comment, and this page carries two code-121 switch rows
(switch 185, the `FLAG_MENU_ON_EVENT` pair) — so the event fell through to the
transpiler. Map067 EV003 has no 121 rows, which is why the neighbouring sign
converted fine and the two sat side by side, one working, one not.

**`MB_COUNTER` then hid the damage.** The working `pokemart` lives on EV003, a
`bg_event` sign ON the counter tile (10,8). Standing at (10,9) facing up, that
tile has no object event, so the counter reach-over
(`field_control_avatar.c:400-409`) looks one tile further to (10,7) and finds
the clerk — the stub. `GetInteractionScript` tries object events before
background events, so the good script was permanently shadowed. #10's
`MB_COUNTER` work is correct and generic; the Mart's layout is simply inverted
from the Center's (working script near, broken stub far), so the same fix that
helped one exposed the other.

Fixed by `_merge_script_call_rows` in the transpiler, which fuses a run of 355
+ 655 leaves edge-to-edge and matches idioms against the joined text, plus a
transpiler-side `pbPokemonMart` idiom sharing `deterministic.py`'s regexes.
**The merge is conditional** — it only absorbs a continuation while the
accumulated text is still mid-expression (unbalanced bracket, or a bare
trailing `=`). That guard is load-bearing: consecutive script rows are usually
separate COMPLETE Ruby statements (the pbStarterSelector arithmetic chain is a
run of them) and joining those edge-to-edge concatenates working code into
garbage. Corpus queue 377→346, CH03 87→56.

The clerk's real stock is 7 items including Paralyze Heal; the sign's list has
only 6. Pointing the NPC at the sign's mart block would have shipped the wrong
stock — worth remembering if a similar shadowed-counter case turns up.

### 18. B11 cannot complete a Mart purchase — FIXED 2026-08-16

Not a converter bug — a harness gap. `Emulator` had no money or bag-quantity
primitive, so B11 granted itself nothing, hit "You don't have enough money" at
₽36, and its A-mash bounced around the item list until it gave up.

Added `money()`/`set_money()`/`bag_item_quantity()`/`item_price()`. Emerald
XOR-obfuscates both money and bag quantities against
`gSaveBlock2Ptr->encryptionKey`, so a raw read returns garbage; the primitives
mirror `money.c`'s Get/SetMoney and `item.c`'s `BagPocket_GetSlotDataGeneric`.
`bag_item_quantity` reads `gSaveBlock1Ptr->bag` directly rather than through
the `gBagPockets` runtime view, so it does not depend on
`SetBagItemsPointers` having run this boot, and scans all five pockets by item
id (`AddBagItem` only ever files an item in its one designated pocket).

B11 now grants money, buys, and asserts money down by exactly the price and
bag up by exactly 1. It stops mashing on the observed money delta rather than
a fixed tap count — a real engine signal, and precisely what the original
fixed-count mash got wrong. Exit is by B, not A: `shop.c`'s state machine
treats B as non-committal everywhere after the purchase, while A would
re-trigger BUY.

**N4 is now registered and passing** — it was only ever deferred for the
missing primitive, and it needs no money granted at all.

### 20. The cave is sealed — NOT A CH03 BLOCKER, reclassified 2026-08-17

**The seal is the game design working, not a conversion gap.** Reclassified
after the user pushed back on the obvious question — boulders are Strength-gated
in every Pokémon game, so why would Uranium differ? It doesn't.

`pbPushThisBoulder` (`reference/scripts_dump/101__PField_Field.rb:2850`) is:

```ruby
def pbPushThisBoulder #JV
  if $PokemonMap.strengthUsed
    pbPushThisEvent
    return true
  end
  return false
end
```

No Strength, no push. **HM04 is granted in CH25 (Route 11)** (`00-atlas.md`
line 116), so the player cannot move these boulders during CH03 under any
circumstances. Corroborated by the wiki: *"you will need HM04 (Strength) to
move the boulder blocking your path and to explore the cave"* and *"After
getting HM04 in Legen Town, come back and speak to the boy crying just outside
of the entrance of the Poké Mart"* (`Kevlar_Town.wiki:28,30`;
`Passage_Cave.wiki:10` agrees). The Grott-Hole and the Cry Boy sidequest are
one **return-trip** unit, not CH03 content.

The BFS and `walk_to` evidence in the original write-up was correct and is
still correct — it just measured the intended wall. Signal that was misread at
the time: sw86 `FLAG_HAS_STRENGTH` is written exactly once corpus-wide, on
**Map140/Route 11** — precisely where Strength is granted. That was the answer,
recorded in the spec as an anomaly.

**Consequences.** B19–B24 are deferred, not failing (CH02's rock-chokepoint
precedent). Map019 **stays in `SLICE_MAP_IDS`** (user call) so the cave is
already built and art-checked when Strength lands. B18 needs no change — it
observes the pre-Strength idle page and passes.

**The conversion work itself is still real** and moves to `PROJECT_TODO.md`:
`pbPushThisBoulder` is genuinely unconverted (5 queue entries, map31 EV001/EV037
and map19 EV001/EV002/EV003), and is due **in CH25**, the chapter that grants
Strength — not the chapter before it (user call: it should land with the
mechanic it enables, where a beat can actually exercise it).

Sibling misdiagnosis: #21, same session, same root shape — a beat written
against output and mistaken for a statement about the design.

Consequence: **B19–B24 are unreachable in a real playthrough** — the cave
door, all three boulder pushes, Bikers Lou and Joe, Richard, and the cave
exit. That is six beats and the whole Grott Hole section of the chapter
blocked behind one unconverted idiom. Converting `pbPushThisBoulder` is the
highest-value queue item left for CH03.

One open uncertainty inside the cave, untestable until it opens: Richard's
south-approach tile (22,8) is collision-blocked at his spawn, but he patrols
and `_approach_patrol_npc` reads his live position, so it may never bite.

### 21. The Magikarp joke has no repeat guard — NOT A DEFECT, closed 2026-08-17

Withdrawn: the increment *is* the mechanism, and a repeat guard would break the
gift outright. `Map031_EV014_Page1_Joke` gates its `givemon` behind
`VAR_HA_MAGIKARP == 99`, so the counter has to accumulate — the gag is that the
player refuses the joke 100 times, and the hundredth refusal pays out a level-100
Magikarp. Confirmed faithful against the raw event: **code 111, variable 200,
operand 99, comparison `==`**. Going 1→2 on a re-talk is the feature working.

This item and B17 were both written on 2026-08-16 against pre-fix output, where
the page really did emit no `givemon` — module finding 3 in `kevlar.py` said so.
That was a symptom of the staging gate, not of the page: `staged_species_constant`
demanded every `SPECIES_*` appear in `species_manifest.json`, but staging only
ever covers the ~166 custom/reworked `needs_engine` species, so a vanilla reuse
like Magikarp could never pass. Fixed in `b33a8449`; the full vanilla gift flow
now compiles.

Both beats were rewritten against the real design (user call, 2026-08-17): **B17**
seeds `VAR_HA_MAGIKARP` to 98 via a new `emulator.set_var`, refuses once to reach
99 with no gift, then refuses again and asserts the Magikarp lands in
`gPlayerParty`. **N2** is inverted — it now asserts repeated refusals *do*
accumulate the counter. The 100-refusal loop was considered and rejected as
suite-time cost for no added coverage; nothing in the page is state-dependent
past the compare.

### 19. B13's berry-plant approach never leaves the Mart — FIXED 2026-08-16

Widened once it was clear B13 was not alone: with B11 finally completing,
**every beat from B13 on was executing for the first time**, and seven of them
carried latent geometry bugs. All fixed (commits `e0d1a4cf`, `db586a92`); the
suite is now green through **B16** on a clean full run.

**The arrival/mat rule, which explains most of them.** Uranium interiors put
the arrival tile one row *above* the exit mat. `_cross_threshold` walks to its
approach tile before stepping, so the approach must be the tile you step
*from* — the arrival, never the mat. B13 crossed from the Mart's counter
approach (10,9), one tile too high, so its step landed on the arrival (10,10)
and fired no warp. B16 crossed from the mats themselves, so `walk_to` stepped
onto the warp mid-route and failed with "interrupted by a locked-field scene"
on the tile it was heading for.

**Missing exits.** B14 entered the Berry Boutique and never left, so B15 began
indoors while walking to an outdoor door; B15 had the same gap for B16. Both
now exit at their own end, matching B16's already self-contained shape.

**Impossible approaches.** B15 tried to talk to the Bike Shop NPC from
directly below, but the counter run blocks y=8 and y=9 across x=0..6 — and no
`MB_COUNTER` reach-over helps, because the tile it would reach from is itself
wall; talk from (6,7) facing LEFT. B18's approach tile and both of Cry Boy's
vertical neighbours are blocked; only the tile west of him is open. B25's
north-edge approach was a tree, and the obvious correction was worse — locally
open but inside a 39-tile pocket disconnected from the walkable region, which
`walk_to`'s planner rightly refused. The real northernmost walkable row is
y=0.

**B17** asked for the Magikarp NPC's live position from across the map;
`gObjectEvents` is camera-bound, so the lookup raised rather than returning a
stale position. It now stages into the NPC's neighbourhood first.

**Method worth reusing:** decode collision straight out of
`engine/data/layouts/<Map>/map.bin` (dimensions in `layouts.gen.json`,
little-endian u16 per cell, collision in bits 10-11) and print an ASCII map
before trusting any coordinate. Every one of these was found that way in
seconds. And note the seed trap: `--from-beat X` restores the blob captured at
X's entry, so after changing beat X-1 you must rerun from X-1 or earlier or
you replay the old behaviour.

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

### 25. Every item grant in the chapter compiles to nothing

Surfaced 2026-08-18 while reconciling the spec's numbering (#24). The spec's
§4.2 item-grant table lists five grants. Of the four that are in-chapter,
**three grant nothing** — the player finishes the Center tour, the Boutique
NPC's dialogue and the Sprinklotad offer with an unchanged bag. Found from a
map-viewer feedback export ("runs her dialogue but nothing is given"); the
Center tour's berries were not in the export and had never been noticed.

| Item | Map / event | Spec's claimed source |
|---|---|---|
| 5× Oran Berry | 68 / EV15 (PC-tour) | `pbReceiveItem(ORANBERRY,5)` in a code-111/type-12 conditional |
| ~~Antidote~~ | 68 / EV18 (item ball) | **NOT MISSING — see below** |
| Bacu/Guara/Cupu/Acai Berry | 73 / EV6 pg0 | `pbReceiveItem`, some on code-655 continuation lines |
| Sprinklotad | 73 / EV3 + EV6 pg1 | `pbReceiveItem`, gated on not-held |
| Bicycle | 73 / EV1 | `BIKEWHEEL` consumed → `BICYCLE` (out of chapter anyway, → CH11) |

**Diagnosed 2026-08-18. It is a transpiler gap, not a docs error, and the
Antidote was never part of it.** Three separate grant shapes exist in the
source data; only one of them works:

- **Shape A — item balls.** `code-111` type-12 wrapping `Kernel.pbItemBall`.
  **Already converted** via the object-event *template* path — `ITEM_ANTIDOTE`
  is present in `Map068.template_fields.json`, and #9 closed this in August.
  234 sites / 53 maps corpus-wide. **The `grep giveitem` that opened this item
  was the wrong instrument:** item balls never emit a Poryscript grant, so a
  `.pory` grep cannot see them. User confirmed the Antidote's oddities are an
  original-game bug already ruled on. Not a gap.
- **Shape B — bare script-call grant.** `code-355`/`655` whose text is a whole
  `Kernel.pbReceiveItem(...)` call. 40 sites / 10 maps. Map073 EV6 pg0 cmds
  5–8 are four of them, each a complete statement (so the `_merge_script_call_
  rows` joiner must keep leaving them separate). **Not handled.**
- **Shape C — grant as a conditional's test expression.** `code-111` type-12
  whose *condition* is the call, because `pbReceiveItem` returns whether the
  item was accepted; the then-body is the success path. 152 sites / 56 maps.
  The tour's berries are `Map068.json` EV15 pg0 cmd 83 with an **empty**
  then-body — a pure side-effect wrapper. **Not handled.**

**No §4.5 violation:** both broken shapes land in the queue as designed —
`transpile_unhandled.jsonl` carries map 68 / event 15 / line 83. The grant was
lost loudly, not silently. What made it invisible is that the queue entry
names the *conditional*, not the grant hiding in its test expression — the
same lesson as #26(b).

**Corpus-wide, this is ~192 lost item grants across 60-odd maps** — every NPC
that hands the player anything. Fixing it is a general transpiler change, not
a CH03 patch.

**DONE 2026-08-18 for the chapter's berries.** Shapes B and C both emit
`giveitem` now (`transpiler.py`, commit `43aa482e`); the four Uranium berries
and Sprinklotad were added to the engine as real items (commit `67fd0435`).
Verified through the whole chain, not just the transpiler:

- `Map073.pory:109-112` — four separate `giveitem` calls, unfused.
- `engine/data/maps/KevlarTownBuildings/scripts.inc:37-43` — assembled.
- `engine/data/maps/KevlarTownPokemonCenter/scripts.inc:407` —
  `giveitem ITEM_ORAN_BERRY, 5`, the tour grant that started this.
- ROM `6ec17ab3` builds clean (EWRAM 86.79%, IWRAM 86.99%, ROM 81.55%).
- CH03 unhandled queue **56 → 50**.

Remaining work:

1. ~~Sprinklotad's grant is still queued behind a different idiom.~~
   **DONE 2026-08-19** (`4da46a2e`): bag-quantity conditionals convert to
   `checkitem` + `VAR_RESULT` (verified against `engine/`, §4.7), with the
   `>0` / `==0` inversion handled explicitly. Both `Map073.pory` offers now
   emit, and their then-bodies with them.
2. **Shape C with a *non-empty* then-body** needs a faithful success-path
   mapping or an explicit queue — do not approximate it. 60 of 150 shape-C
   sites corpus-wide still queue, most on items the fork lacks (see #27).
   **Not CH03 work** — filed as `PROJECT_TODO.md` #42.
3. ~~Extend the beats to assert inventory, not just the self-switch.~~
   **DONE 2026-08-19.** Four beats now read the bag through
   `Emulator.bag_item_quantity` instead of trusting a flag:

   | Beat | Now asserts |
   |---|---|
   | B5 | bag holds **exactly** 5× `ITEM_ORAN_BERRY` (post-hoc — the tour ran during B2's warp, so there is no "before" to diff; nothing else in the build set grants one, so an exact total is the honest pin) |
   | B7 | `ITEM_ANTIDOTE` **+1** across the pickup (delta, because the Kevlar Mart also stocks Antidotes) |
   | N1 | `ITEM_ANTIDOTE` **unchanged** on a re-touch — the "no second Antidote" claim is about the bag; the retained self-switch is only the mechanism |
   | B14 | **+1 of each** of the four berries, checked separately and reported together (a joiner regression would drop three specific items, and *which* three is the diagnostic) |

   Verified on ROM `c3e75d4f` (the stamped chapter-complete build, unchanged —
   these are assertions, not conversion changes): PASS from B7 through B25,
   then a full clean chapter run.

   **Still unasserted: Sprinklotad.** Both offers (`Map073_EV003_Page1`,
   `Map073_EV006_Page2`) sit behind a `checkitem`/not-held gate on a *second*
   interaction that no registered beat drives. The item exists and the grant
   emits; nothing walks it. Adding that beat means extending the user-approved
   beat list, so it is a scope call, not a fix.

### 27. 111 items the id map names and the fork does not define

Surfaced by #25 and only partly addressed by it. `reference/uranium_id_map.json`
maps 607 Uranium items to `ITEM_*` constants; **111 of them do not exist in
`engine/include/constants/items.h`** — the id map already precomputed the list
in its own `needs_engine.items`. Five were fixed in #25 (the four berries plus
Sprinklotad); **106 remain**, including Uranium-original held items, mega
stones, key items and mail.

Every one of them is an item grant, mart entry or held item that will fail the
§4.7 forward gate and queue when its map is converted. They surface chapter by
chapter, which is the slow way to find 106 of anything.

Compounding it: **Phase 2's item converter output never reaches the engine.**
`pbs_converter/items.py` emits both `include/constants/items.h` and a
`gItemsInfo[]` table into `output/uranium-build/`, and nothing includes or
copies them into `engine/`. Compare the flags and map-alias hooks
(`engine/data/event_scripts.s:1743`, `map_events.s:27`) — there is no items
equivalent, so that output is currently a dead end.

Doing this properly is a Phase-2→engine integration, not 106 hand edits. It
also needs a decision the berries dodged: those five were vanilla-equivalent,
so their data could be copied from a twin. An original held item or mega stone
has no twin and needs real hold-effect data from Uranium's `item_field_codes`
worklist (`items.py:308-321`, already generated and unread).

Not chapter-blocking. Belongs in `PROJECT_TODO.md` when someone plans it.

### 26. The Cry Boy chain is live content, and one unemitted body breaks it

Two findings from tracing the chain 2026-08-18. They point in opposite
directions and both were previously recorded wrong.

**(a) The chain is not dead — the "sw86 is never true" reading was a bug in
our own notes.** §7 of the spec, and the comment on
`b18_cry_boy_accept_deferred` in `kevlar.py`, both claimed sw86 is written
"to 0/off" and concluded the sidequest is unreachable corpus-wide. RGSS
code-121's third parameter is `0 = ON, 1 = OFF` — which is how our transpiler
already reads it (`transpiler.py:2558` emits `setflag` when `value == 0`).
`Map140.json` EV16 page 0 carries `121 [86, 86, 0]`, so **sw86 is set ON**.
This is a real return-trip sidequest that opens at the Strength chapter.
Corrected in both files; `B18b` is now *deferred*, not *unreachable*.

**Worth auditing:** anywhere else we concluded "switch never set true" may
have made the same inversion. A corpus-wide re-read of code-121 writes under
the correct convention is cheap and would catch the rest.

**(b) `Map019.pory` EV6 emits an empty battle, so the chain cannot close.**
`Map019_EV006_Page1` (`output/uranium-build/scripts/Map019.pory:82-111`)
emits the intro dialogue and the sw94 if/else skeleton, but **both branch
bodies are empty except comments** — `pbTrainerIntro`, `pbNoticePlayer`, both
`pbTrainerBattle` calls and `pbTrainerEnd` are all `# UNHANDLED`, logged in
`transpile_unhandled.jsonl` for `map_id:19, event_id:6`.

The damage is downstream of the missing battle: the self-switch-A set and the
`121 [100,100,0]` write were **nested inside those branch bodies**, so
`FLAG_SIDEQUEST_CRYBOY_END` is never set by any emitted script. Consequences:

- `Map019_dispatch.pory` already gates EV4/EV5 (the two blocker trainers) on
  `FLAG_SIDEQUEST_CRYBOY_END` — those dispatch branches are **currently
  unreachable in the build**, so the blockers would never retire.
- `Map073` EV5 reads sw99 and sw100 across three pages; its later states are
  equally stranded.

Note the shape: sw94 gates only *which of two near-identical*
`pbTrainerBattle` calls fires (a battle-variant argument), and **both branches
converge** on the same self-switch + sw100 writes. So a fix does not need to
model the sw94 distinction to unblock the chain.

Not CH03-blocking (the cave is Strength-gated anyway, #20), but it is the
concrete example of why an unemitted conditional body is worse than an
unemitted leaf command: **state writes hide inside branch bodies, and the
queue entry names the branch, not the writes lost with it.**

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

### 24. Spec doc vs harness beat numbering reconciled — DONE 2026-08-18

The spec (`reference/chapters/03-kevlar-town.md`) and `kevlar.py` had drifted
onto different B-numbers for the same beats — e.g. the spec's B13/B14 meant
the cave-door beats, while `kevlar.py`'s registered B13 is the berry-plant
beat (`kevlar.py:844`, "renumbered B13 in the approved list"). This already
caused one wasted investigation reading "halts at B13" against the wrong
numbering. `kevlar.py` is the source of truth (its numbering is the
2026-08-12 user-approved list); the spec doc has been renumbered to match,
with the full old→new mapping recorded in a table near the top of the spec's
§3. One unresolved item surfaced by the reconciliation: `kevlar.py`'s
`DEFERRED_BEATS` tuple labels the Compensation Man Luxi gift "B26", colliding
with the active, registered Center-PC beat of the same name — flagged in the
mapping table, not silently resolved.

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
