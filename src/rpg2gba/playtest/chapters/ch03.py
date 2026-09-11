"""Chapter 3 -- Kevlar Town (`reference/chapters/03-kevlar-town.md`).

Predecessor-chained onto `route1` (CH02): `kevlar.build()` gets moki's 17 +
route1's 29 beats prepended. Route1's own last beat (B17) is a terminal
checkpoint standing just south of the Kevlar seam on Route 1 -- this
chapter's B1 owns the actual crossing.

**Beat list is user-approved (CH03_TODO.md, 2026-08-12); do not redesign.**
Coordinates/ids below were read directly from `output/uranium-build/maps/
Map0{31,67,68,73,19}.json`, `output/uranium-build/staging/local_ids/
Map0{31,67,68,73,19}.json`, and the compiled `engine/data/maps/{KevlarTown,
KevlarTownPokemart,KevlarTownPokemonCenter,KevlarTownBuildings,
PassageCaveGrottHole}/{scripts,events}.inc` + `map.json` -- not copied blind
from the spec doc or the approved beat list. Every coordinate/event id named
in the approved beat list checked out exactly against that data; no
transcription slips found. `FLAG_NURSE_TUTORIAL` / `FLAG_SIDEQUEST_CRY_BOY` /
`FLAG_SIDEQUEST_CRYBOY_END` / `VAR_HA_MAGIKARP` confirmed verbatim in
`engine/data/scripts/uranium_flags.h`.

**No wild encounters anywhere in this chapter's roster** (`encounter_list`
is `[]` on all 5 maps, spec doc 4.3) -- unlike ch01.py/ch02.py, beats below
use plain `emu.walk_to`, no grass/ambush-absorption machinery.

**No native sight trainers in this chapter.** Every "Trainer(4)"/"Richboy"
object event in `PassageCaveGrottHole/events.inc` compiles with
`TRAINER_TYPE_NONE` -- Uranium's own sight/notice logic (`pbNoticePlayer`/
`get_character`, CH03_TODO.md #4.1 "classifier near-misses") never got wired
to the engine's native `trainer_see.c` mechanism. Approaching these NPCs is
a plain `interact()`, not a sight-lane walk.

**Major real findings, not harness bugs -- read before touching these beats.**
Checked directly against the compiled `scripts.inc` for every map in the
roster (not assumed from the spec's `pbTrainerBattle`/`pbReceiveItem`/
`pbPushThisBoulder`/`pbAddPokemon` prose, which describes the *source*, not
what the transpiler actually emitted):

1. **None of the 4 chapter trainer battles exist in the ROM.** Mawuli
   (`Map068_EV014_Page1`), Lou/Joe (`Map019_EV004/005_Page1`), and Richard
   (`Map019_EV006_Page1`) all end in plain dialogue -- no `trainerbattle*`
   command anywhere in any of the 3 compiled map script files. This is the
   corpus-wide "`pbTrainerBattle` wrapped in `code-111`" gap CH03_TODO.md's
   dry run already flagged as unhandled (81 unhandled entries, 5 of them
   these calls) -- confirmed here as a hard miss, not a partial one.
2. **Boulder push does not exist.** `Map019_EV00{1,2,3}_Page1` (the 3
   boulders) are each a bare `lock`/`release` -- no movement, no
   `OBJ_EVENT_GFX_PUSHABLE_BOULDER` (`CH03_TODO.md #4` already flagged the
   *intended* graphic; the compiled events use plain
   `OBJ_EVENT_GFX_URANIUM_HGSS_267` with `MOVEMENT_TYPE_FACE_DOWN`, an
   ordinary static solid object, not the pushable one).
3. **UPDATE (2026-08-17): the earlier "never calls `givemon`" reading was
   of pre-fix output and is obsolete.** A transpiler fix landed and the
   compiled `Map031_EV014_Page1_Joke` (`output/uranium-build/scripts/
   Map031.pory` lines 646-688) now has the full vanilla gift flow. The real
   design: the "No" branch (`VAR_RESULT != 1`) normally just `addvar`s
   `VAR_HA_MAGIKARP` by 1 -- EXCEPT when the var already reads 99, in which
   case that same "No" branch instead runs the full gift (`bufferspeciesname`
   / `showmonpic` / `givemon(SPECIES_MAGIKARP, 100)` / fanfare / nickname
   prompt / PC-overflow branch) and does NOT increment the var further. So
   the gag is that the player must refuse the joke 100 times (0->99 via
   refusals, then the 100th refusal triggers the gift).
4. **The PC-tour "NPC" is not an NPC interaction at all.** `Map068_EV015_Page1`
   (the tour cutscene: `addobject 10`, dialogue, `setflag` on
   EVENT015/016/017_SSA) is invoked from
   `KevlarTownPokemonCenter_MapScripts_MAP_SCRIPT_ON_TRANSITION_2` -- an
   **autorun triggered by entering Map068 with `FLAG_NURSE_TUTORIAL` already
   set**, not by talking to anyone. `Map068_EV016_Page1` (EV016 being the
   NurseTut2 object at (8,17), local id 10, the sprite that *does* exist to
   talk to) is a bare `end`. So B5 is folded into B3's arrival, not a
   separate `talk` beat -- see B5's own comment.
5. **(Corrected 2026-08-19; was "no Oran Berry grant exists".)** The grant
   was missing because the transpiler dropped every `pbReceiveItem` shape;
   `43aa482e` fixed it, and `KevlarTownPokemonCenter/scripts.inc` now carries
   `giveitem ITEM_ORAN_BERRY, 5`. **B5 asserts the bag holds exactly 5**, not
   just the tour's self-switches.
6. **(Corrected 2026-08-19; was "no Boutique grant either".)** `Map073.pory:
   123-126` emits four separate unfused `giveitem` calls, and Sprinklotad's
   bag-quantity gate converted in `4da46a2e`. **B14 asserts +1 of each of the
   four berries.**
   *Still unasserted:* Sprinklotad itself. Both of its offers
   (`Map073_EV003_Page1`, `Map073_EV006_Page2`) sit behind a
   `checkitem`/not-held gate on a second interaction that no registered beat
   drives -- the item emits, nothing walks it.
7. **No healing-location/respawn metadata write anywhere** -- `grep
   -i respawn` over the Center's whole compiled output: zero hits. There is
   also no `Emulator` primitive for reading `SaveBlock1`'s last-heal-location
   fields (no offset is probed for it). B6 has no engine-side effect and no
   harness-side read to test it with -- folded into B4's comment, not
   registered as its own beat (same shape as ch01.py's dropped N1).
8. **(2026-08-17) The cave (Grott-Hole) is post-Strength return-trip
   content, not CH03 -- deferred, not a converter gap.** `pbPushThisBoulder`
   (`reference/scripts_dump/101__PField_Field.rb`) is gated on
   `$PokemonMap.strengthUsed`: it returns false and does nothing until the
   player has activated the Strength field move, so every boulder sealing
   this cave -- the 3 inside it (finding 2) and the 2 more on the OUTDOOR
   map (`Map031_EV001_Page1` at (10,16), `Map031_EV037_Page1` at (12,16),
   local ids 1 and 7, jointly sealing the only corridor south of the cave
   door at (13,7), decoded from `engine/data/layouts/KevlarTown/map.bin` and
   confirmed live via `walk_to`'s own planner reporting no route) -- is
   CORRECTLY immovable this chapter. That is the game's design working, not
   a defect. `output/uranium-build/wiki/Kevlar_Town.wiki` line 28 ("you will
   need HM04 (Strength) to move the boulder blocking your path") and line
   30 ("After getting HM04 in Legen Town, come back...") and
   `output/uranium-build/wiki/Passage_Cave.wiki` line 10 both confirm this
   cave is written as explicit return-trip content. HM04 Strength is
   granted in CH25 (Route 11, `reference/chapters/00-atlas.md` line 116) --
   22 chapters after this one. B19 through B24 (the door, the 3 boulders,
   Lou/Joe/Richard) are therefore DEFERRED, not registered on this chapter
   (see `DEFERRED_BEATS` below) -- their geometry was still checked
   statically and is not itself buggy; restore them once a chapter reaches
   this cave post-Strength. `pbPushThisBoulder` itself remains unconverted
   (5 queue entries, finding 2) -- but converting it would NOT unblock these
   beats; the gate is Strength possession, not the converter.
9. **WITHDRAWN 2026-08-17 -- the VAR_HA_MAGIKARP increment is the mechanism,
   not a missing repeat guard.** This finding read the unconditional increment
   as a converter gap, by analogy with B7/N1's one-time item ball. Wrong
   analogy: `Map031_EV014_Page1_Joke`'s NO branch increments *except* at
   `var(VAR_HA_MAGIKARP) == 99`, where it hands over a level-100 Magikarp
   instead. A hundred refusals earn the joke mon, so the counter has to
   accumulate -- a repeat guard would break the gift outright. Faithful to the
   original: code 111, variable 200, operand 99, comparison ==. N2 now asserts
   accumulation; see finding 3 for why the `givemon` was missing when this was
   written (`CH03_TODO.md` #21).

Every item/mon-grant/battle assertion below is still written and still
checked for real -- per the task brief, an honest RED beats a beat weakened
to pass. Where the compiled script has literally no code path that could
ever satisfy the assertion, that is stated in the beat's own comment so the
failure reads as a finding, not a mystery.

**Money/bag-quantity primitives now exist on `Emulator`**
(`money`/`set_money`/`bag_item_quantity`/`item_price`, all XOR-decrypted
against `gSaveBlock2Ptr->encryptionKey` exactly as `money.c`/`item.c` do --
see their docstrings). B11 (Mart purchase) grants enough money for
`MART_FIRST_ITEM` (confirmed via `item_price`, not assumed), drives a real
purchase through the native `pokemart` menu, and asserts money went down
by exactly the price and the bag quantity went up by one, then that
control returns to the overworld. N4 (insufficient-money refusal) is
registered too: with money forced below any stock item's price, it asserts
the purchase is refused and money/bag are unchanged, both immediately
after the refusal and after the mart is exited.

**Local ids are not RMXP event ids** (see ch02.py's module docstring for
the general rule). Tables read from `output/uranium-build/staging/
local_ids/Map0{31,67,68,73,19}.json`, fresh-run artifacts:

    Map031: RMXP  1(Boulder)->1  6->2  7(Cry Boy)->3  8->4  9->5
            14(Magikarp)->6  37(Boulder)->7  39->8  40->9
            42-46(BerryPlant)->10-14  48->15  49(NurseTut)->16
    Map067: RMXP  1->1  4->2   (EV003 mart counter and EV009 Deliveryman
            are `bg_events` type "sign", ANY-facing, not object events at
            all -- confirmed against `KevlarTownPokemart/map.json`)
    Map068: RMXP  1(healing counter)->1  3->2  4->3  9->4  10->5  11->6
            13->7  14(Mawuli)->8  18(item ball)->9  16(NurseTut2)->10
            (EV015, the tour scene, is not an object event -- see finding 4)
    Map073: RMXP  1(Bike Repair)->1  6(Boutique)->2  8->3  10->4  11->5
    Map019: RMXP  1-3(Boulders)->1-3  4(Lou)->4  5(Joe)->5  6(Richard)->6

Facings read from each object's compiled `MOVEMENT_TYPE_FACE_*`
(`events.inc`); a `MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE` object (Magikarp,
Lou, Joe, Richard) patrols, so its approach is computed from its LIVE
position each attempt via `_approach_patrol_npc`, mirroring ch02.py's
`_approach_moving_npc`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .. import assertions
from ..chapter import BeatLocation, ChapterBuilder
from ..errors import ScenarioError
from ..pokecenter import heal_at_counter, use_pc

if TYPE_CHECKING:  # runtime import is lazy so the registry works without bindings
    from ..emulator import Emulator

ch03 = ChapterBuilder("CH03", doc="reference/chapters/03-kevlar-town.md",
                        predecessor="CH02")

# -- coordinates / ids (see module docstring for provenance) -----------------

# B1: the real Route 1 -> Kevlar Town crossing. ch02.py's B17 stands just
# south of this seam without crossing it (Kevlar wasn't built yet when that
# beat was written) -- this beat owns the actual step across.
KEVLAR_ENTRY_APPROACH = (16, 6)
KEVLAR_ENTRY_DIRECTION = "UP"

# B2/N3: NurseTut, map31 local id 16, (21,13), FACE_DOWN.
NURSE_TUT_LOCAL = 16
NURSE_TUT_XY = (21, 13)
NURSE_TUT_APPROACH = (21, 14)
NURSE_TUT_FACING = "UP"

# B2: the walkthrough doesn't end at the Center's ordinary warp-in tile --
# NurseTut walks the player through healing/PC downstairs, then upstairs to
# explain the connection functions, and control is handed back there.
NURSE_TUT_WALKTHROUGH_END = (7, 5)

# B3: the physical Center door, independent of NurseTut's own auto-warp.
# EV008 (the door-warp trigger tile, `warp(MAP_URANIUM_31, 20, 12)`) sits at
# (8,19) -- the map's south edge on a 20x20 grid, so the approach has to be
# one tile north of it and the crossing step DOWN onto it, not off the grid.
CENTER_DOOR = (20, 12)
CENTER_ARRIVAL = (8, 18)
CENTER_EXIT_TILE = (8, 19)
CENTER_EXIT_APPROACH = (8, 18)

# B4: the healing counter, map68 local id 1, (8,11), FACE_DOWN. (8,12) is the
# counter tile itself -- collision-blocked (a reach-over interact tile, like
# a PC/mart counter), not a standing tile. The approach is one further south.
HEAL_COUNTER_LOCAL = 1
HEAL_COUNTER_APPROACH = (8, 13)
HEAL_COUNTER_FACING = "UP"

# B26: the PC, EV007 at (10,13) -- a bg_event sign (no character_name/tile_id,
# same "no object event" shape as the mart counter/deliveryman signs, see
# B10's docstring), not a compiled object; no local id, so no facing-based
# assertion is possible here the way heal_at_counter uses one. (10,13) is
# collision-blocked (the PC itself, decoded from
# engine/data/layouts/KevlarTownPokemonCenter/map.bin); the approach is one
# tile south.
PC_APPROACH = (10, 14)
PC_FACING = "UP"

# B7: item ball, map68 local id 9, (17,7), MOVEMENT_TYPE_NONE.
CENTER_ITEM_BALL_EVENT_ID = 18  # RMXP id, for the FLAG_MAP068_EVENT018_SSA name
CENTER_ITEM_BALL_APPROACH = (17, 8)
CENTER_ITEM_BALL_FACING = "UP"
# B7/N1: what the ball actually hands over. Item balls carry their item in
# the object event's template, not in any emitted `giveitem` -- read from
# `output/uranium-build/Map068.template_fields.json`, which is why a
# `grep giveitem` over the compiled script finds nothing here (finding 5's
# original mistake, CH03_TODO.md #25 shape A).
CENTER_ITEM_BALL_ITEM = "ITEM_ANTIDOTE"

# B5: the PC-tour autorun's grant, `KevlarTownPokemonCenter/scripts.inc`
# -> `giveitem ITEM_ORAN_BERRY, 5` (Map068.pory:283). Nothing else in the
# build set grants an Oran Berry, so the expected quantity is exact, not a
# floor.
CENTER_TOUR_ITEM = "ITEM_ORAN_BERRY"
CENTER_TOUR_ITEM_QUANTITY = 5

# B8: Mawuli, map68 local id 8, (2,16), FACE_RIGHT. (3,16), the tile
# immediately east of her, LOOKS like the natural approach (facing her own
# facing direction) but is collision-blocked -- decoded directly off
# engine/data/layouts/KevlarTownPokemonCenter/map.bin, and confirmed
# unreachable by the harness's own _plan_route (2026-08-14, see
# .claude/skills/boot-walk-harness/SKILL.md Phase 2 item 5). (2,15), the
# tile directly north of her, is clear; approaching from there is also the
# room's only real route in (the SW corner is walled off from the middle,
# reachable only via the north corridor then down the west wall -- verified
# by the same Dijkstra call, matches output/map_feedback/Map068_feedback.json's
# hand-drawn path exactly).
MAWULI_LOCAL = 8
MAWULI_APPROACH = (2, 15)
MAWULI_FACING = "DOWN"

# B10: Mart door + interior. The shop counter is a `bg_event` sign (ANY
# facing) at (10,8), not an object event -- `Map067_EV003_Page1` ->
# `pokemart Map067_EV003_Mart` (ITEM_POKE_BALL/POTION/ANTIDOTE/ICE_HEAL/
# REPEL/ESCAPE_ROPE). Deliveryman (EV9) is also a bg_event sign, (5,9).
MART_DOOR = (37, 14)
MART_ARRIVAL = (10, 10)
MART_COUNTER_APPROACH = (10, 9)
DELIVERYMAN_APPROACH = (5, 10)

# B11/N4: the mart's stock list (`engine/data/maps/KevlarTownPokemart/
# scripts.inc`, cross-checked against `output/uranium-build/scripts/
# Map067.pory`) puts ITEM_POKE_BALL first -- BuyMenu's ListMenu and the
# root ShopMenu both default their cursor to slot 0, so this is the item a
# plain A-commit buys with no cursor movement.
MART_FIRST_ITEM = "ITEM_POKE_BALL"

# B13: Map031 berry plants, native BerryTreeScript, local ids 10-14,
# (32,5)/(33,10)/(34,10)/(35,10)/(36,10).
BERRY_PLANT_LOCAL = 10  # (32,5); any one plant is enough to exercise the pick
BERRY_PLANT_APPROACH = (32, 6)
BERRY_PLANT_FACING = "UP"

# B14: Berry Boutique door + interior NPC, map73 local id 2, (46,8),
# FACE_DOWN.
BOUTIQUE_DOOR = (35, 6)
BOUTIQUE_ARRIVAL = (44, 12)
BOUTIQUE_NPC_APPROACH = (46, 9)
BOUTIQUE_NPC_FACING = "UP"
# B14: the free samples, one each, emitted as four separate unfused
# `giveitem` calls (`Map073.pory:123-126` -> `KevlarTownBuildings/
# scripts.inc`). Four distinct items rather than 4x one item -- the
# `_merge_script_call_rows` joiner must keep them apart, so asserting all
# four separately is also what pins that.
BOUTIQUE_SAMPLE_ITEMS = (
    "ITEM_BACU_BERRY",
    "ITEM_GUARA_BERRY",
    "ITEM_CUPU_BERRY",
    "ITEM_ACAI_BERRY",
)

# B15: Bike Repair Shop door + NPC, map73 local id 1, (5,7), FACE_DOWN.
# The NPC stands behind a solid counter run: decoding collision out of
# `data/layouts/KevlarTownBuildings/map.bin` (70x15, bits 10-11) shows
# y=8 and y=9 blocked across x=0..6, so the tile directly below the NPC
# cannot be stood on and an UP-facing approach is impossible -- and unlike
# the Mart, no MB_COUNTER reach-over helps, because the tile you would
# reach from is itself wall. The customer side is the corridor to the
# NPC's right, so talk from (6,7) facing LEFT.
BIKE_SHOP_DOOR = (23, 28)
BIKE_SHOP_ARRIVAL = (5, 11)
BIKE_SHOP_NPC_APPROACH = (6, 7)
BIKE_SHOP_NPC_FACING = "LEFT"

# B16: the two flavor houses.
MAURY_DOOR = (37, 28)
MAURY_ARRIVAL = (24, 12)
COUPLE_DOOR = (32, 28)
COUPLE_ARRIVAL = (64, 12)

# B17/N2: Magikarp, map31 local id 6, (29,20), CUSTOM_ROUTE (patrols).
MAGIKARP_LOCAL = 6
# B16 leaves the player at COUPLE_DOOR (32,28), well outside the camera's
# object-event spawn radius around (29,20) -- `emu.object_event(6)` raised
# "no active object event with local id 6" the first time B17 ran (2026-08-16
# finding; TrySpawnObjectEvents/RemoveObjectEventsOutsideView only keep an
# NPC's slot live within roughly one screen of the player,
# engine/src/event_object_movement.c:2909-2951, same mechanism B8's own
# comment cites). Column x=29 is open collision the whole way from y=20 to
# y=28 (decoded from `engine/data/layouts/KevlarTown/map.bin`, 50x50,
# collision bits 10-11) -- (29,23) is a plain walk_to waypoint straight up
# that column, close enough to Magikarp's spawn to force her object event to
# spawn before `_approach_patrol_npc` reads her live position.
MAGIKARP_STAGING = (29, 23)

# B18: Cry Boy, map31 local id 3, (39,16), FACE_RIGHT. The originally-written
# approach (40,16), east of him, is itself collision-blocked (decoded from
# `engine/data/layouts/KevlarTown/map.bin`, 50x50, bits 10-11) -- so is
# (39,15) north and (39,17) south. Only (38,16), one tile west, is open;
# his own facing direction doesn't gate interact() the way a sight trainer
# would (module docstring: no native sight trainers in this chapter), so
# approaching from his blind side is fine. 2026-08-16: B18 had never run
# before (dead code past the old-B11 hang) -- this beat's approach tile was
# never checked against real collision.
CRY_BOY_APPROACH = (38, 16)
CRY_BOY_FACING = "RIGHT"

# B19: the cave door, map31 (13,7) -> map19 (11,29).
CAVE_DOOR = (13, 7)
CAVE_ARRIVAL = (11, 29)
CAVE_EXIT_APPROACH = (11, 29)
CAVE_EXIT_TILE = (11, 30)

# B20: the 3 boulders, map19 local ids 1-3, FACE_DOWN, static (see finding 2
# -- pushing is a no-op in this build; this beat proves that honestly).
BOULDERS: tuple[tuple[int, tuple[int, int]], ...] = (
    (1, (10, 14)), (2, (8, 15)), (3, (10, 12)),
)

# B21/B22/B23: Lou, Joe, Richard -- map19 local ids 4/5/6, CUSTOM_ROUTE
# (patrol; approach via live position, see finding 1 for why no battle
# actually starts).
LOU_LOCAL = 4
JOE_LOCAL = 5
RICHARD_LOCAL = 6

# B25: the north edge. `KevlarTown/map.json`'s `connections` is `null` --
# no seam is wired (CH03_TODO.md decision #3: "clean impassable wall").
# Approach column chosen well clear of every other event on the north side
# of the map (the NurseTut/Center cluster sits at x=17-21). The originally
# written column, x=25, is itself collision-blocked terrain (a tree). x=24
# LOOKS open at y=0-2 (same `map.bin` decode) but is a red herring: a 4-way
# flood fill from it (`engine/data/layouts/KevlarTown/map.bin`, 50x50, bits
# 10-11) reaches only 39 tiles total, none of them anywhere near the couple's
# house/berry-plant area a real playthrough arrives from -- it's a sealed
# decorative pocket (walled off on every side), not part of the map's one
# connected walkable region (570 tiles). `walk_to`'s own A* planner agrees
# live ("no planned route from (32, 28)"), then its greedy fallback wanders
# into a building doorway trying anyway. x=27-29 at y=0-2 flood-fills into
# the SAME component as the couple's/Maury's doors and is equally clear of
# the door/berry clusters. y=0 -- not y=1 -- is the map's actual
# northernmost walkable row: from (28,1) a single step UP legitimately
# lands on (28,0) (still on-map, not a crossing) before the real boundary
# bites one step further; confirmed live -- stepping UP from (28,0) leaves
# the player at (28,0) unmoved, while the same probe from (28,1) reads as
# "crossed". The approach has to be the last walkable tile, same principle
# as every arrival/mat pair elsewhere in this chapter.
NORTH_EDGE_APPROACH = (28, 0)


# -- small local helpers, copied+adapted from ch02.py/ch01.py -------------
# `_at_map`/`_require_map`/`_try_step`/`_wait_for_map`/`_cross_threshold`/
# `_enter_door`/`_assert_near` used to be copied here (ch02.py's own
# docstring used to say "deliberately not yet factored into a shared module"
# -- that call is superseded) -- promoted to `assertions.py` 2026-08-20
# (finding H). Aliased under their original names so every call site below
# is unchanged.
_at_map = assertions.at_map
_require_map = assertions.require_map
_try_step = assertions.try_step
_wait_for_map = assertions.wait_for_map
_cross_threshold = assertions.cross_threshold
_enter_door = assertions.enter_door
_assert_near = assertions.assert_near


_DIR_VECTOR: dict[str, tuple[int, int]] = {
    "DOWN": (0, 1), "UP": (0, -1), "LEFT": (-1, 0), "RIGHT": (1, 0),
}

#: Bound on `_approach_patrol_npc`'s live-position re-read/retry loop --
#: mirrors ch02.py's `_MAX_PATROL_APPROACH_ATTEMPTS` (same
#: custom-route-patrol regression class: a fixed approach tile goes stale
#: the instant the NPC paces off its spawn).
_MAX_PATROL_APPROACH_ATTEMPTS = 5


def _approach_patrol_npc(emu: Emulator, beat: str, local_id: int,
                         facing: str,
                         max_attempts: int = _MAX_PATROL_APPROACH_ATTEMPTS
                         ) -> None:
    """Approach and `interact()` an NPC under `MOVEMENT_TYPE_URANIUM_
    CUSTOM_ROUTE`, re-reading its LIVE position each attempt rather than a
    fixed tile -- see ch02.py's `_approach_moving_npc` for the regression
    this mirrors."""
    dx, dy = _DIR_VECTOR[facing]
    for _ in range(max_attempts):
        ev = emu.object_event(local_id)
        approach = (ev.x - dx, ev.y - dy)
        emu.walk_to(*approach)
        emu.face(facing)
        try:
            emu.interact()
            return
        except ScenarioError:
            continue  # the NPC stepped out from under the approach -- retry fresh
    shot = emu.screenshot(f"{beat}_patrol_no_interact")
    raise ScenarioError(
        f"{beat}: could not interact with the patrolling NPC (local id "
        f"{local_id}) after {max_attempts} attempts ({shot})")


# Promoted to `assertions.py` 2026-08-20 (this was the general two-argument
# form; ch02.py's near-duplicate is now a thin wrapper over the same
# function -- see assertions.flag_ssa's docstring).
_flag_ssa = assertions.flag_ssa


# -- B27/B28/B30/B32 (warp-arrival facing) + B29/B31/B33 (post-warp BGM) --
# regression floor. Two defect classes that were reasoned about but never
# asserted in-ROM (2026-08-19 task): (1) `compute_arrival_facings`'s
# `_derive_retain_facing` fix (`tileset_converter/metadata_wiring.py`,
# `reference/warp_facing_overrides.json`) for the CH03 "RMXP retain-facing"
# bug -- tests/test_warp_facing_invariant.py pins the fix at the metadata
# layer, but nothing before this drove the real ON_WARP_INTO_MAP_TABLE
# script in the running ROM. (2) the transpiler's per-map dropped-command
# queue: every Transfer Player warp on Map031 strands the commands RMXP
# kept running across it (pokeemerald halts the script at the warp,
# ScrCmd_warp/DoWarp) -- 9 CHANGE_TONE (code 223) + 2 CHANGE_MAP_SETTINGS
# (204) + 1 PLAY_BGM (241), all destination-side presentation. The lead's
# call was that nothing is actually lost because pokeemerald derives
# destination BGM from the MAP HEADER natively rather than the event page --
# UNVERIFIED until now.
#
# Both are checked with facts read live off THIS build's own artifacts
# (`compute_arrival_facings` run over the staged slice for facing;
# `engine/data/maps/<Dir>/map.json`'s own "music" key for BGM), never a
# hardcoded DIR_*/MUS_* literal -- boot-walk-harness SKILL.md Phase 2 rule 3.
#
# Each of the 6 new beats below is placed physically right after the
# existing beat that already stands the player on the exact arrival tile
# being checked (B1/B10/B3/B14) -- no beat here re-navigates across the map.
# The first version of this work did (a `walk_to` clear across Kevlar Town
# to re-trigger the Route 1 seam), and in full-chapter order that landed the
# player one tile off the compiled ON_WARP_INTO_MAP_TABLE dispatch's exact
# coordinate match (a `_assert_near` tolerance of 1 let it slide through as
# "close enough" while the dispatch script itself does an exact compare and
# fell through with no `turnobject`, defaulting to the engine's own
# DIR_SOUTH) -- a harness navigation bug, not a converter defect (2026-08-19
# finding, confirmed by an isolated `--from-beat B27` run passing outright).
# Piggybacking on an already-standing position removes the failure mode
# entirely instead of tightening the tolerance around it.

# `_DIR_CONST_TO_FACING`/`_expected_arrival_facing`/`_assert_player_facing`/
# `_expected_bgm_song_id`/`_assert_bgm` used to be defined here -- promoted
# to `assertions.py` verbatim 2026-08-20 (finding H's flagship case: this is
# the class CH01/CH02 were stale against precisely because it lived only
# here). Aliased under their original names so every call site below is
# unchanged.
_DIR_CONST_TO_FACING = assertions._DIR_CONST_TO_FACING
_expected_arrival_facing = assertions.expected_arrival_facing
_assert_player_facing = assertions.assert_player_facing
_expected_bgm_song_id = assertions.expected_bgm_song_id
_assert_bgm = assertions.assert_bgm


# -- B1 ------------------------------------------------------------------

# `rows=` on the beats below (P8a, REDERIVATION_PLAN.md 13.1) records which
# chapter-manifest rows each beat actually exercises, so the disposition
# generator can join `beat:` instead of a human hand-writing it. 26 rows
# across 17 of this chapter's 30 beats, each mapping confirmed against the
# event's coordinates in the decoded map JSON and its page condition in the
# manifest. `archetype=` is set only where EVERY row of the beat is the same
# archetype: B13/B15 and B2 are deliberately left unset because they mix a
# warp (or a nudge) with rows the classifier does not recognize, and the
# declaration has to describe the whole beat.
#
# THIRTEEN BEATS CLAIM NOTHING, in four groups:
#
#   B27, B28, B29, B30, B31, B32, B33 -- warp-arrival FACING and map BGM.
#     These assert `compute_arrival_facings`' output and map-header music,
#     neither of which is an RGSS page. No manifest row kind can represent
#     them. (`map031/ev002/p1`, `ev003/p1` and `ev004/p1` are real
#     arrival_nudge rows, but nothing in these beats asserts anything about
#     those pages, so they stay unclaimed rather than guessed at.)
#
#   N1, N2, N4 -- each re-exercises the same single page an earlier beat
#     already claims: N1 the item ball's only page (B7 -- CH03_TODO #9, the
#     ball is a repurposed one-time self-switch, so there is no "spent" page
#     the way CH02's item balls have one), N2 the Magikarp NPC's page (B17),
#     N4 the mart counter's page (B11). One row, one claimant.
#
#   N6 -- a chapter-wide invariant ("no reachable warp lands on an unbuilt
#     map"), not a claim about any single row.
#
#   B1 and B25 -- both boundary crossings, and both are P8b's to flip, not
#     this pass's. B1 is NOT a map connection, despite the word "seam" in its
#     description: `connections.json` has no 33<->31 edge, and B1 stands on
#     (16,6) pressing UP onto (16,5), which is Map033's EV046 -- one of the
#     two `code 201` warps slice-growth reports for CH02 (EV045 is (15,5)).
#     So the row is `map033/ev046/p0` and it lives in CH02's manifest, the
#     departing chapter's. B25 is the mirror case on a real connection: the
#     `map031/seam/N/map035` row is in THIS chapter's manifest, but B25
#     deliberately stands at x=28, away from the seam cells, testing the wall
#     rather than the crossing -- and CH04's B1 is the beat that crosses it.
#     Per REDERIVATION_PLAN.md 10 R2/R3 the ARRIVING chapter claims a
#     boundary row, resolved through `boundary_model.successor_claims` off
#     the successor's `Beat.rows`. Nothing in the corpus makes such a claim
#     yet, so making one here alone would reintroduce the inconsistency 10
#     exists to remove. See ch02.py's B1 note for the same call.


@ch03.beat("B1", "Crossing Route 1's north seam lands in Kevlar Town",
             map_constant="MAP_ROUTE_01", at=KEVLAR_ENTRY_APPROACH)
def b1(emu: Emulator) -> None:
    _cross_threshold(emu, "B1", KEVLAR_ENTRY_APPROACH, KEVLAR_ENTRY_DIRECTION,
                     "MAP_KEVLAR_TOWN")


# -- B27 (placed right after B1 -- see the block comment above _flag_ssa) --

@ch03.beat("B27", "Crossing Route 1 -> Kevlar Town (B1's own warp) lands "
                    "the player facing away from the return warp "
                    "(warp-facing fix, task 2026-08-19) -- checked against "
                    "the live ROM, not just the unit-level metadata test",
             map_constant="MAP_KEVLAR_TOWN", at=(16, 42))
def b27(emu: Emulator) -> None:
    # No navigation of its own: B1's own crossing (KEVLAR_ENTRY_APPROACH,
    # direction UP -- warp src (16,5) on MAP_ROUTE_01) is the exact warp
    # being checked, and it just ran. Re-walking here to "re-trigger" it was
    # the earlier version's bug (see the block comment above _flag_ssa).
    _assert_near(emu, "B27", (16, 42), tolerance=0)
    expected = _expected_arrival_facing(31, 16, 42)
    _assert_player_facing(emu, "B27", expected)


# -- B2 ------------------------------------------------------------------

@ch03.beat("B2", "NurseTut's walkthrough runs and sets FLAG_NURSE_TUTORIAL "
                   "(warps the player straight into the Center)",
             map_constant="MAP_KEVLAR_TOWN", at=NURSE_TUT_APPROACH,
             rows=("map031/ev049/p0", "map068/ev012/p1"))
def b2(emu: Emulator) -> None:
    if emu.flag("FLAG_NURSE_TUTORIAL"):
        raise ScenarioError(
            "B2 precondition failed: FLAG_NURSE_TUTORIAL already set")
    emu.walk_to(*NURSE_TUT_APPROACH)
    emu.face(NURSE_TUT_FACING)
    emu.interact()
    # `Map031_EV049_Page1` ends with `warp MAP_URANIUM_68, 8, 18` BEFORE
    # setting FLAG_NURSE_TUTORIAL -- so this rides the warp out, not just a
    # dialogue release.
    emu.advance_dialog(stop=lambda: _at_map(emu, "MAP_KEVLAR_TOWN_POKEMON_CENTER"))
    _wait_for_map(emu, "B2", "MAP_KEVLAR_TOWN_POKEMON_CENTER")
    # Arriving in the Center arms a *chain* of dispatcher autoruns, not one
    # script: EV012 page 2 (a silent lockall/applymovement/setflag/releaseall,
    # no msgbox to advance) releases, and its own guard flag then lets the
    # dispatcher fall through to EV015 page 1 on the next frame. Draining once
    # left the tail of that chain for N3 to trip over. That chain is the
    # walkthrough itself: NurseTut walks the player through healing/the PC
    # downstairs (landing at the warp-in tile above is only the entry beat),
    # then upstairs to explain the connection functions, and control is
    # handed back there -- not at the warp-in tile.
    emu.settle_field()
    if not emu.flag("FLAG_NURSE_TUTORIAL"):
        shot = emu.screenshot("b2_no_tutorial_flag")
        raise ScenarioError(
            f"B2: FLAG_NURSE_TUTORIAL not set after the walkthrough ({shot})")
    _assert_near(emu, "B2", NURSE_TUT_WALKTHROUGH_END)


# -- N3 (NurseTut re-talk) --------------------------------------------------

@ch03.beat("N3", "Re-talking NurseTut (Map068's NurseTut2, local id 10) is "
                   "the no-op page",
             map_constant="MAP_KEVLAR_TOWN_POKEMON_CENTER", at=(8, 18),
             rows=("map068/ev016/p1",))
def n3(emu: Emulator) -> None:
    # NurseTut2 (Map068 local id 10, (8,17)) is the object that survives
    # into the Center; `Map068_EV016_Dispatch` with FLAG_NURSE_TUTORIAL set
    # and EVENT016_SSA set (B2's autorun tail, see B5 below) reads
    # `Map068_EV016_Page2`, a bare `end`. `interact()` would fail loud on a
    # true no-op (it requires the field to lock) -- this presses A and polls
    # briefly instead, same shape as ch01.py's N3/ch02.py's item re-touch.
    emu.walk_to(8, 18)
    emu.face("UP")
    emu.tap("A")
    emu.run(30)
    if emu.field_locked():
        shot = emu.screenshot("n3_unexpected_lock")
        raise ScenarioError(
            f"N3: re-talking NurseTut2 locked the field -- expected the "
            f"no-op page ({shot})")


# -- B3 ------------------------------------------------------------------

@ch03.beat("B3", "The physical Center door (independent of NurseTut's "
                   "auto-warp) opens and returns",
             locations=(
                 BeatLocation("MAP_KEVLAR_TOWN_POKEMON_CENTER", CENTER_EXIT_APPROACH[0], CENTER_EXIT_APPROACH[1], "center exit"),
                 BeatLocation("MAP_KEVLAR_TOWN", CENTER_DOOR[0], CENTER_DOOR[1], "center door"),
             ),
             rows=("map068/ev008/p0", "map031/ev003/p0"), archetype="warp")
def b3(emu: Emulator) -> None:
    # B2 already stands the player inside Map068 via NurseTut's own warp;
    # this beat exercises the ORDINARY door as its own mechanism -- exit
    # back to Map031 first, then re-enter via (20,12).
    _cross_threshold(emu, "B3", CENTER_EXIT_APPROACH, "DOWN", "MAP_KEVLAR_TOWN")
    _enter_door(emu, "B3", CENTER_DOOR, "MAP_KEVLAR_TOWN_POKEMON_CENTER")
    _assert_near(emu, "B3", CENTER_ARRIVAL)


# -- B30/B31 (placed right after B3 -- see the block comment above _flag_ssa) -

@ch03.beat("B30", "Entering the Poke Center via the physical door (B3's "
                    "own warp) lands the player facing away from the "
                    "return warp (warp-facing fix, task 2026-08-19)",
             map_constant="MAP_KEVLAR_TOWN_POKEMON_CENTER", at=CENTER_ARRIVAL)
def b30(emu: Emulator) -> None:
    # No navigation: B3 already stands the player at CENTER_ARRIVAL via the
    # exact warp under test.
    expected = _expected_arrival_facing(68, *CENTER_ARRIVAL)
    _assert_player_facing(emu, "B30", expected)


@ch03.beat("B31", "Arriving at the Poke Center plays the map's own BGM -- "
                    "this is the ONE literal dropped PLAY_BGM instance in "
                    "the chapter (Map031_EV049_NurseTut, code 241), so this "
                    "beat is the direct test of the lead's claim, not just "
                    "a structural analogy (task 2026-08-19)",
             map_constant="MAP_KEVLAR_TOWN_POKEMON_CENTER", at=CENTER_ARRIVAL)
def b31(emu: Emulator) -> None:
    _assert_bgm(emu, "B31", "KevlarTownPokemonCenter")


# -- B4 ------------------------------------------------------------------

@ch03.beat("B4", "The healing counter's Yes/No heal restores a damaged party "
                   "and the full scene plays out to its close (healing-"
                   "location metadata has no test surface -- see module "
                   "docstring finding 7, B6 folded in here)",
             map_constant="MAP_KEVLAR_TOWN_POKEMON_CENTER", at=HEAL_COUNTER_APPROACH,
             rows=("map068/ev001/p0",))
def b4(emu: Emulator) -> None:
    # `special HealPlayerParty` is a real, native call
    # (`Map068_EV001_Page1_2`) -- this only confirms the flow completes
    # cleanly and returns control; the harness has no party-HP read to
    # difference against (battle.py's HP reader is enemy-party-only), so a
    # "damaged party" precondition can't be set up or verified here either.
    # This is the mechanism check the spec's own §6.1 already treats as
    # native/pre-existing (HealPlayerParty existed since CH01).
    #
    # 2026-08-14: this used to only check field_locked(), which is exactly
    # what missed the scene's dropped completion tail (the `Kernel.
    # pbPokerus?` conditional ate the return-facing movement + closing
    # messages along with the Pokerus-only text -- CH03_TODO.md). Now via
    # heal_at_counter(), which also checks the counter NPC turned back.
    heal_at_counter(emu, HEAL_COUNTER_APPROACH, HEAL_COUNTER_FACING,
                     counter_local_id=HEAL_COUNTER_LOCAL, beat="B4")


# -- B26 -----------------------------------------------------------------

@ch03.beat("B26", "The Center's PC boots through the native EventScript_PC "
                    "chain and returns control cleanly (2026-08-14: this was "
                    "previously an UNHANDLED-code-355 queue entry -- "
                    "pbPokeCenterPC never converted at all, see "
                    "CH03_TODO.md's classifier-near-miss recon note)",
             map_constant="MAP_KEVLAR_TOWN_POKEMON_CENTER", at=PC_APPROACH,
             rows=("map068/ev007/p0",))
def b26(emu: Emulator) -> None:
    use_pc(emu, PC_APPROACH, PC_FACING, beat="B26")


# -- B7 ------------------------------------------------------------------

@ch03.beat("B7", "Item ball at (17,7) grants an Antidote once",
             map_constant="MAP_KEVLAR_TOWN_POKEMON_CENTER", at=CENTER_ITEM_BALL_APPROACH,
             rows=("map068/ev018/p0",), archetype="item_ball")
def b7(emu: Emulator) -> None:
    ssa = _flag_ssa(68, CENTER_ITEM_BALL_EVENT_ID)
    if emu.flag(ssa):
        raise ScenarioError(
            f"B7 precondition failed: {ssa} already set before the pickup")
    # Bag delta, not an absolute count: the Kevlar Mart stocks Antidotes
    # too (`KevlarTownPokemart/scripts.inc`), so a later beat could legally
    # change the total. Only this pickup's own +1 is under test here.
    bag_before = emu.bag_item_quantity(CENTER_ITEM_BALL_ITEM)
    emu.walk_to(*CENTER_ITEM_BALL_APPROACH)
    emu.face(CENTER_ITEM_BALL_FACING)
    emu.interact()
    emu.advance_dialog()
    if not emu.flag(ssa):
        shot = emu.screenshot("b7_not_granted")
        raise ScenarioError(f"B7: {ssa} not set after the pickup ({shot})")
    bag_after = emu.bag_item_quantity(CENTER_ITEM_BALL_ITEM)
    if bag_after != bag_before + 1:
        shot = emu.screenshot("b7_bag_unchanged")
        raise ScenarioError(
            f"B7: {CENTER_ITEM_BALL_ITEM} {bag_before}->{bag_after}, expected "
            f"+1 -- the self-switch is set but the item never reached the bag "
            f"({shot})")


# -- N1 ------------------------------------------------------------------

@ch03.beat("N1", "Re-touching the item ball does not re-grant the Antidote "
                   "(CH03_TODO.md #9: the ball is a deliberately one-time "
                   "repurposed self-switch, not the native repeatable "
                   "template)",
             map_constant="MAP_KEVLAR_TOWN_POKEMON_CENTER", at=CENTER_ITEM_BALL_APPROACH)
def n1(emu: Emulator) -> None:
    ssa = _flag_ssa(68, CENTER_ITEM_BALL_EVENT_ID)
    bag_before = emu.bag_item_quantity(CENTER_ITEM_BALL_ITEM)
    emu.face(CENTER_ITEM_BALL_FACING)
    emu.tap("A")
    emu.run(30)
    if emu.field_locked():
        emu.advance_dialog()
    if not emu.flag(ssa):
        shot = emu.screenshot("n1_flag_lost")
        raise ScenarioError(f"N1: {ssa} cleared after a re-touch ({shot})")
    # The point of the beat: "no second Antidote" is a claim about the bag.
    # A retained self-switch is only the mechanism we expect to enforce it.
    bag_after = emu.bag_item_quantity(CENTER_ITEM_BALL_ITEM)
    if bag_after != bag_before:
        shot = emu.screenshot("n1_regranted")
        raise ScenarioError(
            f"N1: {CENTER_ITEM_BALL_ITEM} {bag_before}->{bag_after} on a "
            f"re-touch -- the ball re-granted ({shot})")


# -- B5 --------------------------------------------------------------------

@ch03.beat("B5", "The PC-tour scene autoruns on Center arrival (NOT an NPC "
                   "talk -- see module docstring finding 4), sets its 3 "
                   "self-switches AND leaves 5 Oran Berries in the bag "
                   "(finding 5, corrected 2026-08-19)",
             rows=("map068/ev015/p0",))
def b5(emu: Emulator) -> None:
    # B2's own warp already carried this scene to completion (Map068's
    # MAP_SCRIPT_ON_TRANSITION fires `Map068_EV015_Page1` the instant the
    # map loads with FLAG_NURSE_TUTORIAL set, before this beat runs) -- so
    # this only asserts the end state, exactly like B9's "no VAR_QUEST_LOG
    # write" pattern in ch01.py checks a fact rather than driving an action.
    for letter, event_id in (("A", 15), ("A", 16), ("A", 17)):
        ssa = _flag_ssa(68, event_id, letter)
        if not emu.flag(ssa):
            shot = emu.screenshot(f"b5_missing_{ssa.lower()}")
            raise ScenarioError(
                f"B5: {ssa} not set after arrival -- the tour autorun did "
                f"not complete ({shot})")
    # The grant itself. Asserted as an exact total rather than a delta
    # because the scene already ran during B2's warp -- there is no
    # "before" to read from here -- and because nothing else in the build
    # set grants an Oran Berry, so any other number is a real defect and
    # should say so loudly.
    held = emu.bag_item_quantity(CENTER_TOUR_ITEM)
    if held != CENTER_TOUR_ITEM_QUANTITY:
        shot = emu.screenshot("b5_bag_wrong")
        raise ScenarioError(
            f"B5: bag holds {held}x {CENTER_TOUR_ITEM}, expected "
            f"{CENTER_TOUR_ITEM_QUANTITY} -- the tour's self-switches are "
            f"set but its `giveitem` did not land ({shot})")


# -- B8 ------------------------------------------------------------------

@ch03.beat("B8", "Mawuli's facility battle: win, and the offer repeats "
                   "(transpiler._emit_facility_trainer_battle_idiom, "
                   "2026-08-15 -- converts the code-111-wrapped "
                   "pbTrainerBattle to trainerbattle_no_intro + "
                   "cleartrainerflag so the facility stays repeatable)",
             map_constant="MAP_KEVLAR_TOWN_POKEMON_CENTER", at=MAWULI_APPROACH,
             rows=("map068/ev014/p0",), archetype="trainer")
def b8(emu: Emulator) -> None:
    from ..battle import in_battle, win_battle

    # Mawuli's compiled movement_type is MOVEMENT_TYPE_FACE_RIGHT (a static
    # NPC), not MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE -- she doesn't need
    # _approach_patrol_npc's live-position tracking, and using it was
    # actively wrong: that helper reads her gObjectEvents slot BEFORE
    # walking anywhere, but pokeemerald only keeps an NPC's slot active
    # while the player is within roughly one screen of it
    # (TrySpawnObjectEvents/RemoveObjectEventsOutsideView,
    # engine/src/event_object_movement.c:2909-2951) -- B8 runs right after
    # B5/N1/B7 leave the player across the room by the item ball, so
    # Mawuli's slot isn't spawned yet and the live read failed before a
    # single step was taken (2026-08-14 finding).
    emu.walk_to(*MAWULI_APPROACH)
    emu.face(MAWULI_FACING)
    emu.interact()
    # commits YES at "Wanna fight?"; must stop the mash the instant the
    # battle starts (ch02.py's `_advance_to_battle` pattern) -- without
    # `stop=`, advance_dialog keeps holding A THROUGH the whole battle
    # (yesnobox/msgbox both advance on A) and only returns once it resolves
    # on its own, so the in_battle() check below reads False even on a
    # genuine win (2026-08-15 finding).
    emu.advance_dialog("A", stop=lambda: in_battle(emu))
    if not in_battle(emu):
        shot = emu.screenshot("b8_no_battle")
        raise ScenarioError(
            f"B8: accepting Mawuli's offer did not start a battle "
            f"({shot})")
    win_battle(emu)
    # Re-offer: talk again, expect the SAME offer (no state latch anywhere
    # in the script -- it's a facility loop, not a one-time flag).
    emu.walk_to(*MAWULI_APPROACH)
    emu.face(MAWULI_FACING)
    emu.interact()
    if not emu.field_locked():
        shot = emu.screenshot("b8_no_reoffer")
        raise ScenarioError(f"B8: Mawuli did not re-offer after a win ({shot})")
    emu.advance_dialog("B")  # decline the rematch cleanly this time


# -- B10 -----------------------------------------------------------------

@ch03.beat("B10", "Mart door opens; the pokemart menu opens at the "
                    "counter sign",
             map_constant="MAP_KEVLAR_TOWN", at=MART_DOOR,
             rows=("map031/ev002/p0",), archetype="warp")
def b10(emu: Emulator) -> None:
    # B8 ends with the player still inside the Pokémon Center -- there is no
    # B9 in this scenario (renumbered away from the spec's raw sequence, see
    # module docstring), so this beat must leave the Center itself before
    # walking to MART_DOOR, exactly like B3's own entry/exit pair.
    _cross_threshold(emu, "B10", CENTER_EXIT_APPROACH, "DOWN", "MAP_KEVLAR_TOWN")
    _enter_door(emu, "B10", MART_DOOR, "MAP_KEVLAR_TOWN_POKEMART")
    _assert_near(emu, "B10", MART_ARRIVAL)


# -- B28/B29 (placed right after B10 -- see the block comment above _flag_ssa) -

@ch03.beat("B28", "Entering the Poke Mart (B10's own warp) lands the "
                    "player facing away from the return warp (warp-facing "
                    "fix, task 2026-08-19)",
             map_constant="MAP_KEVLAR_TOWN_POKEMART", at=MART_ARRIVAL)
def b28(emu: Emulator) -> None:
    # No navigation: B10 already stands the player at MART_ARRIVAL via the
    # exact warp under test.
    expected = _expected_arrival_facing(67, *MART_ARRIVAL)
    _assert_player_facing(emu, "B28", expected)


@ch03.beat("B29", "Arriving at the Poke Mart plays the map's own BGM -- "
                    "checks the lead's structural-coverage claim for the "
                    "dropped post-warp presentation commands (task "
                    "2026-08-19)",
             map_constant="MAP_KEVLAR_TOWN_POKEMART", at=MART_ARRIVAL)
def b29(emu: Emulator) -> None:
    _assert_bgm(emu, "B29", "KevlarTownPokemart")


# -- B11 -----------------------------------------------------------------

@ch03.beat("B11", "Buying an item at the counter drives the native "
                    "pokemart menu to a real purchase: money down, bag up "
                    "(Emulator.money/set_money/bag_item_quantity/"
                    "item_price)",
             map_constant="MAP_KEVLAR_TOWN_POKEMART", at=MART_COUNTER_APPROACH,
             rows=("map067/ev003/p0",))
def b11(emu: Emulator) -> None:
    price = emu.item_price(MART_FIRST_ITEM)
    emu.set_money(price + 1000)  # afford it with headroom, no clamp math needed
    money_before = emu.money()
    bag_before = emu.bag_item_quantity(MART_FIRST_ITEM)

    emu.walk_to(*MART_COUNTER_APPROACH)
    emu.face("UP")
    emu.interact()
    if not emu.field_locked():
        shot = emu.screenshot("b11_shop_did_not_open")
        raise ScenarioError(f"B11: the mart counter did not open a script ({shot})")

    # Root ShopMenu (BUY is slot 0) -> BuyMenu item list (POKE_BALL is
    # slot 0) -> "how many? " quantity dialog (default qty 1) -> "that'll
    # be <price>, right?" Yes/No (default YES) -- every one of these is an
    # A-commit-default, same reliability battle.py's move-select leans on
    # for its own default-cursor-0 menus. The stop condition is a real
    # engine signal (money actually debited, shop.c's BuyMenuSubtractMoney)
    # rather than a fixed tap count -- a fixed count is what left the
    # original version of this beat stuck bouncing on an insufficient-funds
    # refusal forever (see N4, which now exercises that refusal on
    # purpose).
    taps = 0
    while emu.money() == money_before:
        if taps >= 60:
            shot = emu.screenshot("b11_purchase_never_landed")
            raise ScenarioError(
                f"B11: money never decreased after {taps} A-taps -- the "
                f"purchase never landed ({shot})")
        emu.tap("A")
        taps += 1

    # Money moved, so the purchase itself is done -- but the item list, the
    # ListMenu underneath it, the "anything else?" message, and the root
    # ShopMenu all still hold the field. Every one of those treats B as
    # either an ordinary dismiss or a cancel/quit, never "buy again"
    # (unlike A, which would re-select BUY or re-attempt the purchase) --
    # advance_dialog's own docstring documents the same "hold one button
    # for a whole stretch" reliability for B, just answering NO at a
    # yesno instead of dismissing text; here there is no more yesno to
    # answer, so holding B all the way out is safe.
    emu.advance_dialog("B", max_taps=60)
    if emu.field_locked():
        shot = emu.screenshot("b11_shop_stuck")
        raise ScenarioError(
            f"B11: the mart flow never returned control after the "
            f"purchase completed ({shot})")

    money_after = emu.money()
    bag_after = emu.bag_item_quantity(MART_FIRST_ITEM)
    if money_after != money_before - price:
        shot = emu.screenshot("b11_money_mismatch")
        raise ScenarioError(
            f"B11: money after purchase is {money_after}, expected "
            f"{money_before - price} ({money_before} - price {price}) "
            f"({shot})")
    if bag_after != bag_before + 1:
        shot = emu.screenshot("b11_bag_mismatch")
        raise ScenarioError(
            f"B11: {MART_FIRST_ITEM} quantity is {bag_after}, expected "
            f"{bag_before + 1} ({shot})")


# -- N4 --------------------------------------------------------------------

@ch03.beat("N4", "Mart purchase refused with insufficient money -- money "
                    "and bag stay untouched, and the mart still returns "
                    "control cleanly",
             map_constant="MAP_KEVLAR_TOWN_POKEMART", at=MART_COUNTER_APPROACH)
def n4(emu: Emulator) -> None:
    emu.set_money(50)  # well under any stock item's price
    money_before = emu.money()
    bag_before = emu.bag_item_quantity(MART_FIRST_ITEM)

    emu.walk_to(*MART_COUNTER_APPROACH)
    emu.face("UP")
    emu.interact()
    if not emu.field_locked():
        shot = emu.screenshot("n4_shop_did_not_open")
        raise ScenarioError(f"N4: the mart counter did not open a script ({shot})")

    # Root ShopMenu (A -> BUY) -> item list (A -> select slot 0) ->
    # `!IsEnoughMoney` fires immediately (shop.c's Task_BuyMenu, before the
    # quantity dialog even opens) and bounces straight back to the item
    # list with nothing charged -- this IS B11's original bug, reproduced
    # here on purpose as the expected refusal. A handful of A-taps is
    # enough to reach and dismiss that one refusal message.
    for _ in range(6):
        emu.tap("A")
    if emu.money() != money_before or emu.bag_item_quantity(MART_FIRST_ITEM) != bag_before:
        shot = emu.screenshot("n4_charged_anyway")
        raise ScenarioError(
            f"N4: money/bag moved despite insufficient funds (money "
            f"{money_before}->{emu.money()}, bag "
            f"{bag_before}->{emu.bag_item_quantity(MART_FIRST_ITEM)}) "
            f"({shot})")

    # Same B-mash exit as B11 -- LIST_CANCEL, the "anything else?" message,
    # then MENU_B_PRESSED on the root ShopMenu.
    emu.advance_dialog("B", max_taps=60)
    if emu.field_locked():
        shot = emu.screenshot("n4_stuck")
        raise ScenarioError(
            f"N4: the mart never returned control after the refusal ({shot})")
    if emu.money() != money_before or emu.bag_item_quantity(MART_FIRST_ITEM) != bag_before:
        shot = emu.screenshot("n4_charged_on_exit")
        raise ScenarioError(
            f"N4: money/bag moved while exiting after a refusal ({shot})")


# -- B12 -----------------------------------------------------------------

@ch03.beat("B12", "Deliveryman's no-gift branch does not crash "
                    "(`Map067_EV009_Page1` is a bare `end` -- it is "
                    "literally inert, not just gift-less)",
             map_constant="MAP_KEVLAR_TOWN_POKEMART", at=DELIVERYMAN_APPROACH,
             rows=("map067/ev009/p0",))
def b12(emu: Emulator) -> None:
    emu.walk_to(*DELIVERYMAN_APPROACH)
    emu.face("UP")
    emu.tap("A")
    emu.run(30)
    if emu.field_locked():
        shot = emu.screenshot("b12_unexpected_lock")
        raise ScenarioError(
            f"B12: the Deliveryman's no-gift page locked the field -- "
            f"expected a total no-op ({shot})")


# -- B6 (renumbered B13 in the approved list -- berry plants) --------------

@ch03.beat("B13", "Picking a Map031 berry plant works (native "
                    "BerryTreeScript)",
             locations=(
                 BeatLocation("MAP_KEVLAR_TOWN_POKEMART", MART_ARRIVAL[0],
                              MART_ARRIVAL[1], "mart exit"),
                 BeatLocation("MAP_KEVLAR_TOWN", BERRY_PLANT_APPROACH[0], BERRY_PLANT_APPROACH[1], "berry plant"),
             ),
             rows=("map067/ev002/p0", "map031/ev042/p0"))
def b13(emu: Emulator) -> None:
    # Cross from MART_ARRIVAL, not MART_COUNTER_APPROACH: the mart's exit
    # mat is (10,11) and the arrival tile (10,10) sits between it and the
    # counter, so a single step DOWN from (10,9) only reaches the arrival
    # tile and no warp fires. Same shape as the Center, whose
    # CENTER_EXIT_APPROACH is likewise its arrival tile with the mats a row
    # below (`KevlarTownPokemonCenter/map.json`: arrival (8,18), mats
    # (7,19)/(8,19)). This beat had never run before 2026-08-16 -- the old
    # B11 hung ahead of it -- so the mistake was invisible.
    _cross_threshold(emu, "B13", MART_ARRIVAL, "DOWN", "MAP_KEVLAR_TOWN")
    emu.walk_to(*BERRY_PLANT_APPROACH)
    emu.face(BERRY_PLANT_FACING)
    emu.interact()
    emu.advance_dialog()
    if emu.field_locked():
        shot = emu.screenshot("b13_stuck")
        raise ScenarioError(f"B13: the berry plant's dialogue did not close cleanly ({shot})")


# -- B14 -----------------------------------------------------------------

@ch03.beat("B14", "Berry Boutique door opens; the NPC hands over one each "
                    "of the four Uranium berries and sets its self-switch "
                    "(module finding 6, corrected 2026-08-19)",
             locations=(
                 BeatLocation("MAP_KEVLAR_TOWN", BOUTIQUE_DOOR[0], BOUTIQUE_DOOR[1], "boutique door"),
                 BeatLocation("MAP_KEVLAR_TOWN_BUILDINGS", BOUTIQUE_NPC_APPROACH[0], BOUTIQUE_NPC_APPROACH[1], "boutique NPC"),
             ),
             rows=("map031/ev004/p0", "map073/ev007/p0"), archetype="warp")
def b14(emu: Emulator) -> None:
    _enter_door(emu, "B14", BOUTIQUE_DOOR, "MAP_KEVLAR_TOWN_BUILDINGS")
    _assert_near(emu, "B14", BOUTIQUE_ARRIVAL)
    ssa = _flag_ssa(73, 6)
    if emu.flag(ssa):
        raise ScenarioError(
            f"B14 precondition failed: {ssa} already set before talking")
    before = {item: emu.bag_item_quantity(item) for item in BOUTIQUE_SAMPLE_ITEMS}
    emu.walk_to(*BOUTIQUE_NPC_APPROACH)
    emu.face(BOUTIQUE_NPC_FACING)
    emu.interact()
    emu.advance_dialog()
    if not emu.flag(ssa):
        shot = emu.screenshot("b14_no_ssa")
        raise ScenarioError(f"B14: {ssa} not set after talking ({shot})")
    # Each berry checked separately, and all four reported at once rather
    # than failing on the first: a joiner regression that fuses the four
    # `giveitem` rows would drop three specific items, and which three is
    # the diagnostic.
    missing = [
        f"{item} {before[item]}->{emu.bag_item_quantity(item)}"
        for item in BOUTIQUE_SAMPLE_ITEMS
        if emu.bag_item_quantity(item) != before[item] + 1
    ]
    if missing:
        shot = emu.screenshot("b14_berries_missing")
        raise ScenarioError(
            f"B14: expected +1 of each free sample, got {', '.join(missing)} "
            f"({shot})")
    # Leave the Boutique: B15 walks straight to a door on MAP_KEVLAR_TOWN
    # and needs to start outdoors, and B16 already pairs its own entry with
    # an exit rather than leaning on the next beat. Cross from the arrival
    # tile (44,12) -- the exit mat is (44,13), one row below, the same
    # arrival-above/mat-below shape as the Mart and the Center
    # (`KevlarTownBuildings/map.json`).
    _cross_threshold(emu, "B14", BOUTIQUE_ARRIVAL, "DOWN", "MAP_KEVLAR_TOWN")


# -- B32/B33 (placed right after B14 -- see the block comment above _flag_ssa) -

@ch03.beat("B32", "Entering the Berry Boutique (the 'flower shop') lands "
                    "the player facing away from the return warp "
                    "(warp-facing fix, task 2026-08-19)",
             map_constant="MAP_KEVLAR_TOWN", at=BOUTIQUE_DOOR)
def b32(emu: Emulator) -> None:
    # B14 just crossed back out and left the player standing exactly on
    # BOUTIQUE_DOOR (its own arrival tile on this side) -- a trivial
    # re-entry, not a cross-map walk (see the block comment above
    # _flag_ssa for why that distinction matters).
    _enter_door(emu, "B32", BOUTIQUE_DOOR, "MAP_KEVLAR_TOWN_BUILDINGS")
    _assert_near(emu, "B32", BOUTIQUE_ARRIVAL)
    expected = _expected_arrival_facing(73, *BOUTIQUE_ARRIVAL)
    _assert_player_facing(emu, "B32", expected)


@ch03.beat("B33", "Arriving at the Berry Boutique plays the map's own "
                    "BGM (task 2026-08-19)",
             map_constant="MAP_KEVLAR_TOWN_BUILDINGS", at=BOUTIQUE_ARRIVAL)
def b33(emu: Emulator) -> None:
    _assert_bgm(emu, "B33", "KevlarTownBuildings")
    # Unlike B29/B31 (which hand off to a same-map beat next), B15 needs
    # MAP_KEVLAR_TOWN -- leave the same way B14 already does.
    _cross_threshold(emu, "B33", BOUTIQUE_ARRIVAL, "DOWN", "MAP_KEVLAR_TOWN")


# -- B15 -----------------------------------------------------------------

@ch03.beat("B15", "Bike Repair Shop refuses with no Bike Wheel held -- no "
                    "yes/no, no Bicycle grant exists in the compiled script "
                    "at all (the source of a Bike Wheel this chapter was "
                    "already flagged unresolved, spec §7)",
             locations=(
                 BeatLocation("MAP_KEVLAR_TOWN", BIKE_SHOP_DOOR[0], BIKE_SHOP_DOOR[1], "bike shop door"),
                 BeatLocation("MAP_KEVLAR_TOWN_BUILDINGS", BIKE_SHOP_NPC_APPROACH[0], BIKE_SHOP_NPC_APPROACH[1], "bike shop NPC"),
             ),
             rows=("map031/ev012/p0", "map073/ev001/p0", "map073/ev002/p0"))
def b15(emu: Emulator) -> None:
    _enter_door(emu, "B15", BIKE_SHOP_DOOR, "MAP_KEVLAR_TOWN_BUILDINGS")
    _assert_near(emu, "B15", BIKE_SHOP_ARRIVAL)
    emu.walk_to(*BIKE_SHOP_NPC_APPROACH)
    emu.face(BIKE_SHOP_NPC_FACING)
    emu.interact()
    emu.advance_dialog()
    if emu.field_locked():
        shot = emu.screenshot("b15_stuck")
        raise ScenarioError(f"B15: the Bike Shop dialogue did not close cleanly ({shot})")
    # Leave the shop, same reason B14 does: B16 starts by walking to a door
    # on MAP_KEVLAR_TOWN. Arrival (5,11), exit mat (5,12).
    _cross_threshold(emu, "B15", BIKE_SHOP_ARRIVAL, "DOWN", "MAP_KEVLAR_TOWN")


# -- B16 -----------------------------------------------------------------

@ch03.beat("B16", "Both flavor houses (Maury's apartment, the couple's "
                    "house) warp in and back out cleanly",
             locations=(
                 BeatLocation("MAP_KEVLAR_TOWN", MAURY_DOOR[0], MAURY_DOOR[1], "Maury door"),
                 BeatLocation("MAP_KEVLAR_TOWN_BUILDINGS", MAURY_ARRIVAL[0],
                              MAURY_ARRIVAL[1], "Maury exit approach"),
                 BeatLocation("MAP_KEVLAR_TOWN", COUPLE_DOOR[0], COUPLE_DOOR[1], "couple door"),
                 BeatLocation("MAP_KEVLAR_TOWN_BUILDINGS", COUPLE_ARRIVAL[0],
                              COUPLE_ARRIVAL[1], "couple exit approach"),
             ),
             rows=("map031/ev013/p0", "map073/ev004/p0",
                   "map031/ev041/p0", "map073/ev009/p0"), archetype="warp")
def b16(emu: Emulator) -> None:
    # Cross from the ARRIVAL tiles, not the exit mats one row below them
    # (24,13)/(64,13). `_cross_threshold` walks to its approach tile first,
    # and walking onto a mat trips the warp mid-route -- `walk_to` then
    # fails with "interrupted by a locked-field scene" on the very tile it
    # was heading for. The approach must be the tile you step FROM.
    _enter_door(emu, "B16", MAURY_DOOR, "MAP_KEVLAR_TOWN_BUILDINGS")
    _assert_near(emu, "B16", MAURY_ARRIVAL)
    _cross_threshold(emu, "B16", MAURY_ARRIVAL, "DOWN", "MAP_KEVLAR_TOWN")
    _assert_near(emu, "B16", MAURY_DOOR)

    _enter_door(emu, "B16", COUPLE_DOOR, "MAP_KEVLAR_TOWN_BUILDINGS")
    _assert_near(emu, "B16", COUPLE_ARRIVAL)
    _cross_threshold(emu, "B16", COUPLE_ARRIVAL, "DOWN", "MAP_KEVLAR_TOWN")
    _assert_near(emu, "B16", COUPLE_DOOR)


# -- B17 -----------------------------------------------------------------

# Promoted to `assertions.py` 2026-08-20, unified with `ch01.py`'s
# `_player_starter_species` under `assertions.read_party_species` /
# `assertions.party_has_species` -- generalized from a hardcoded
# SPECIES_MAGIKARP lookup to an explicit species-id parameter, same scan.
def _party_has_magikarp(emu: Emulator) -> bool:
    magikarp_id = emu.resolve_constant("SPECIES_MAGIKARP")
    return assertions.party_has_species(emu, magikarp_id)


def _refuse_joke(emu: Emulator, beat: str) -> None:
    emu.walk_to(*MAGIKARP_STAGING)  # get within camera range so her object event spawns
    _approach_patrol_npc(emu, beat, MAGIKARP_LOCAL, "UP")
    emu.advance_dialog("A", stop=emu.yesno_prompt_up)
    if not emu.yesno_prompt_up():
        shot = emu.screenshot(f"{beat.lower()}_no_prompt")
        raise ScenarioError(f"{beat}: no yes/no prompt appeared ({shot})")
    # `Map031_EV014_Page1_Joke`: VAR_RESULT != 1 (i.e. answering NO) is the
    # branch that either increments VAR_HA_MAGIKARP or, once it already
    # reads 99, runs the gift flow instead. B answers NO.
    emu.advance_dialog("B")
    if emu.field_locked():
        emu.advance_dialog()


@ch03.beat("B17", "Magikarp NPC seeded to 98 refusals: the 99th refusal "
                    "increments VAR_HA_MAGIKARP to 99 with no gift yet; the "
                    "100th refusal (var already 99) fires the full "
                    "givemon/fanfare/nickname gift flow -- module finding 3",
             rows=("map031/ev014/p0",))
def b17(emu: Emulator) -> None:
    emu.set_var("VAR_HA_MAGIKARP", 98)
    var_before = emu.var("VAR_HA_MAGIKARP")
    if var_before != 98:
        raise ScenarioError(
            f"B17 precondition failed: VAR_HA_MAGIKARP reads {var_before} "
            f"after seeding to 98")

    _refuse_joke(emu, "B17")
    var_after_first = emu.var("VAR_HA_MAGIKARP")
    if var_after_first != 99:
        shot = emu.screenshot("b17_var_not_99")
        raise ScenarioError(
            f"B17: VAR_HA_MAGIKARP reads {var_after_first} after the first "
            f"refusal, expected 99 ({shot})")
    if _party_has_magikarp(emu):
        shot = emu.screenshot("b17_magikarp_too_early")
        raise ScenarioError(
            f"B17: a Magikarp is already in gPlayerParty at "
            f"VAR_HA_MAGIKARP == 99, before the 100th refusal fires the "
            f"gift ({shot})")

    _refuse_joke(emu, "B17")
    if not _party_has_magikarp(emu):
        shot = emu.screenshot("b17_no_magikarp")
        raise ScenarioError(
            f"B17: no Magikarp found in gPlayerParty after refusing at "
            f"VAR_HA_MAGIKARP == 99 -- the gift branch of "
            f"Map031_EV014_Page1_Joke did not fire, see module docstring "
            f"finding 3 ({shot})")


# -- N2 (Magikarp not granted twice) ----------------------------------------

@ch03.beat("N2", "Repeated refusals DO accumulate VAR_HA_MAGIKARP -- the "
                   "increment on each 'No' answer is the mechanism (100 "
                   "refusals earn the joke Magikarp), not a bug. Seeds its "
                   "own baseline of 0 so it's independent of B17's seeded "
                   "state/ordering.")
def n2(emu: Emulator) -> None:
    emu.set_var("VAR_HA_MAGIKARP", 0)
    var_before = emu.var("VAR_HA_MAGIKARP")
    if var_before != 0:
        raise ScenarioError(
            f"N2 precondition failed: VAR_HA_MAGIKARP reads {var_before} "
            f"after seeding to 0")

    _refuse_joke(emu, "N2")
    var_after_first = emu.var("VAR_HA_MAGIKARP")
    if var_after_first != var_before + 1:
        shot = emu.screenshot("n2_var_not_incremented_1")
        raise ScenarioError(
            f"N2: VAR_HA_MAGIKARP reads {var_after_first} after the first "
            f"refusal, expected {var_before + 1} ({shot})")

    _refuse_joke(emu, "N2")
    var_after_second = emu.var("VAR_HA_MAGIKARP")
    if var_after_second != var_before + 2:
        shot = emu.screenshot("n2_var_not_incremented_2")
        raise ScenarioError(
            f"N2: VAR_HA_MAGIKARP reads {var_after_second} after the second "
            f"refusal, expected {var_before + 2} ({shot})")


# -- B18 -----------------------------------------------------------------

@ch03.beat("B18", "Cry Boy: idle page only (FLAG_HAS_STRENGTH is never "
                    "set corpus-wide); FLAG_SIDEQUEST_CRY_BOY stays unset",
             map_constant="MAP_KEVLAR_TOWN", at=CRY_BOY_APPROACH,
             rows=("map031/ev007/p0",))
def b18(emu: Emulator) -> None:
    if emu.flag("FLAG_SIDEQUEST_CRY_BOY"):
        raise ScenarioError(
            "B18 precondition failed: FLAG_SIDEQUEST_CRY_BOY already set")
    emu.walk_to(*CRY_BOY_APPROACH)
    emu.face(CRY_BOY_FACING)
    emu.interact()
    emu.advance_dialog()
    if emu.flag("FLAG_SIDEQUEST_CRY_BOY"):
        shot = emu.screenshot("b18_flag_leaked")
        raise ScenarioError(
            f"B18: FLAG_SIDEQUEST_CRY_BOY became set from the idle page -- "
            f"expected FLAG_HAS_STRENGTH to gate this off ({shot})")


# -- B19 (DEFERRED to CH25 -- see DEFERRED_BEATS) -------------------------

def b19(emu: Emulator) -> None:
    """The cave door; arrival near (11,29).

    DEFERRED, not a beat bug -- `KevlarTown/map.json` has two more
    `OBJ_EVENT_GFX_URANIUM_HGSS_267` boulder objects besides the 3 already
    known inside the cave (module finding 2): map31 local id 1 at (10,16)
    (`Map031_EV001_Page1`) and local id 7 at (12,16) (`Map031_EV037_Page1`),
    both bare `lock`/`release`/`end` -- no push movement, same as every
    other boulder in this corpus. They sit in the narrow corridor
    immediately south of the cave door: decoding
    `engine/data/layouts/KevlarTown/map.bin` (50x50, bits 10-11) and BFSing
    from anywhere on the map to (13,8) shows the route is open with EITHER
    boulder tile excluded alone, but closed with BOTH excluded together --
    i.e. the two of them jointly seal the only path through. This is
    CORRECT per module finding 8: `pbPushThisBoulder` is gated on
    `$PokemonMap.strengthUsed`, and HM04 Strength doesn't arrive until CH25
    -- the boulders are supposed to be immovable here. CAVE_DOOR is
    therefore unreachable on foot until then; B20 through B24/N6 are
    deferred alongside this beat for the same reason. Their own approach
    coordinates were still verified statically against the compiled cave
    map/collision data and check out (see their own comments) -- restore
    all of them together once Strength is obtainable.
    """
    _enter_door(emu, "B19", CAVE_DOOR, "MAP_PASSAGE_CAVE_GROTT_HOLE")
    _assert_near(emu, "B19", CAVE_ARRIVAL)


# -- B20 (DEFERRED to CH25 -- see DEFERRED_BEATS) -------------------------

def b20(emu: Emulator) -> None:
    """Pushing each boulder one tile.

    Module finding 2: none of the 3 boulders have push movement wired --
    every push is expected to fail as a bump, not a move -- a genuine
    converter gap, kept as a real assertion. Finding 8: this beat can never
    actually be reached until HM04 Strength is obtainable (CH25) -- B19's
    own door is sealed until then -- but its coordinates were verified
    statically and are correct.
    """
    for local_id, xy in BOULDERS:
        bx, by = xy
        # Approach from the north and push DOWN -- the boulders sit close
        # together (10,14)/(8,15)/(10,12); (bx, by-1) is walkable for all 3
        # per the live collision grid, checked at write time.
        emu.walk_to(bx, by - 1)
        emu.face("DOWN")
        moved = _try_step(emu, "DOWN")
        after = emu.object_event(local_id)
        if (after.x, after.y) == (bx, by) and not moved:
            shot = emu.screenshot(f"b20_boulder{local_id}_static")
            raise ScenarioError(
                f"B20: boulder (local id {local_id}) at {xy} did not move "
                f"when pushed -- no push movement is wired in "
                f"Map019_EV{local_id:03d}_Page1 (bare lock/release), see "
                f"module docstring finding 2 ({shot})")


# -- N5 (folded into B20 per the task brief's own instruction) --------------
#
# "boulder will not push into a wall" is untestable as a DISTINCT case from
# B20 here: since no boulder has push movement at all (finding 2), EVERY
# push attempt already produces "does not move" -- a wall-adjacent push and
# a plain push are indistinguishable outcomes in this build. Folded into
# B20, which already asserts non-movement for all 3; no separate N5 beat.


# -- B21/B22/B23 (DEFERRED to CH25 -- see DEFERRED_BEATS) ------------------

def b21(emu: Emulator) -> None:
    """Biker Lou (EV4): approach and interact.

    Module finding 1: no trainerbattle* command exists -- expected to
    produce dialogue only, no battle. Finding 8: also unreachable until
    HM04 Strength (CH25), same as B20.
    """
    from ..battle import in_battle

    _approach_patrol_npc(emu, "B21", LOU_LOCAL, "UP")
    emu.advance_dialog(stop=lambda: in_battle(emu))
    if not in_battle(emu):
        shot = emu.screenshot("b21_no_battle")
        raise ScenarioError(
            f"B21: talking to Lou did not start a battle -- no "
            f"trainerbattle* command exists in Map019_EV004_Page1, see "
            f"module docstring finding 1 ({shot})")
    from ..battle import win_battle
    win_battle(emu)


def b22(emu: Emulator) -> None:
    """Biker Joe (EV5): approach and interact.

    Module finding 1: same gap as Lou. Finding 8: also unreachable until
    HM04 Strength (CH25).
    """
    from ..battle import in_battle, win_battle

    _approach_patrol_npc(emu, "B22", JOE_LOCAL, "UP")
    emu.advance_dialog(stop=lambda: in_battle(emu))
    if not in_battle(emu):
        shot = emu.screenshot("b22_no_battle")
        raise ScenarioError(
            f"B22: talking to Joe did not start a battle -- no "
            f"trainerbattle* command exists in Map019_EV005_Page1, see "
            f"module docstring finding 1 ({shot})")
    win_battle(emu)


def b23(emu: Emulator) -> None:
    """Richard (EV6): approach and interact; expect
    FLAG_SIDEQUEST_CRYBOY_END to be set.

    Module finding 1: no trainerbattle* AND no setflag of this name exists
    in Map019_EV006_Page1 -- expected to fail on both. Finding 8: also
    unreachable until HM04 Strength (CH25). NOTE: static collision decode
    also shows (22,8), one tile south of Richard's (22,7) spawn, is itself
    blocked -- `_approach_patrol_npc` reads his LIVE position each attempt,
    so whether this ever bites depends on where his patrol route puts him;
    not verified live because the cave can't be reached pre-Strength, left
    as an open question, not silently assumed fine.
    """
    from ..battle import in_battle, win_battle

    if emu.flag("FLAG_SIDEQUEST_CRYBOY_END"):
        raise ScenarioError(
            "B23 precondition failed: FLAG_SIDEQUEST_CRYBOY_END already set")
    _approach_patrol_npc(emu, "B23", RICHARD_LOCAL, "UP")
    emu.advance_dialog(stop=lambda: in_battle(emu))
    if in_battle(emu):
        win_battle(emu)
    if emu.field_locked():
        emu.advance_dialog()
    if not emu.flag("FLAG_SIDEQUEST_CRYBOY_END"):
        shot = emu.screenshot("b23_flag_not_set")
        raise ScenarioError(
            f"B23: FLAG_SIDEQUEST_CRYBOY_END not set after talking to "
            f"Richard -- Map019_EV006_Page1 never sets this flag (it only "
            f"plays dialogue and walks him off), see module docstring "
            f"finding 1 ({shot})")


# -- B24 (DEFERRED to CH25 -- see DEFERRED_BEATS) --------------------------

def b24(emu: Emulator) -> None:
    """The cave exit warps back to Map031 (13,7).

    Finding 8: also unreachable until HM04 Strength (CH25) -- its own
    geometry is statically correct, matching the arrival/mat warp-pair
    shape already verified elsewhere in this chapter.
    """
    _cross_threshold(emu, "B24", CAVE_EXIT_APPROACH, "DOWN", "MAP_KEVLAR_TOWN")
    _assert_near(emu, "B24", CAVE_DOOR)


# -- N6 ------------------------------------------------------------------

@ch03.beat("N6", "No reachable warp in this chapter lands on an unbuilt "
                   "map -- every door used above resolved to a real "
                   "MAP_KEVLAR_TOWN_* / MAP_PASSAGE_CAVE_GROTT_HOLE / "
                   "MAP_ROUTE_01 constant with no error; this beat is the "
                   "explicit statement of that fact, not a new action")
def n6(emu: Emulator) -> None:
    _require_map(emu, "N6", "MAP_KEVLAR_TOWN")


# -- B25 -----------------------------------------------------------------

@ch03.beat("B25", "The north edge (toward unbuilt Route 2) is a clean "
                    "impassable wall -- no void, no crash",
             map_constant="MAP_KEVLAR_TOWN", at=NORTH_EDGE_APPROACH)
def b25(emu: Emulator) -> None:
    # `KevlarTown/map.json`'s `connections` is `null` -- but as of 2026-08-26
    # that is no longer because nothing is wired (the old CH03_TODO.md
    # decision #3 reason). Route 2 IS built and reachable; the seam is an
    # arrow-warp pair at (31,0)/(32,0) (`reference/seam_warps.json`), chosen
    # over a connection because the two maps cannot share a tileset. This
    # beat stands on x=28, which is NOT one of those two cells, so the north
    # edge is still a genuine wall here and the assertion below still holds
    # unchanged -- it is now "the edge is blocked EXCEPT at the two warp
    # cells", not "there is no way north at all". CH04_TODO.md #7 expected
    # this beat to need flipping when the seam landed; it does not, because
    # it never tested a seam column. Do NOT move it onto x=31/32.
    emu.walk_to(*NORTH_EDGE_APPROACH)
    before = emu.player_pos()
    if _try_step(emu, "UP"):
        shot = emu.screenshot("b25_crossed")
        raise ScenarioError(
            f"B25: stepping UP from {NORTH_EDGE_APPROACH} moved the player "
            f"-- this would walk off the north edge into unbuilt Route 2 "
            f"data; the boundary should read BLOCKED on this build ({shot})")
    if emu.player_pos() != before:
        shot = emu.screenshot("b25_drifted")
        raise ScenarioError(f"B25: player position changed anyway ({shot})")
    if not _at_map(emu, "MAP_KEVLAR_TOWN"):
        shot = emu.screenshot("b25_map_changed")
        raise ScenarioError(
            f"B25: map changed after the blocked step -- expected to stay "
            f"on MAP_KEVLAR_TOWN ({shot})")


# -- deferred beats ---------------------------------------------------------
#
# Written, reviewed, and deliberately NOT registered. Same convention as
# ch02.py's DEFERRED_ROCK_GATED: kept as ready-made regression tests for
# whichever future chapter/patch closes the gap, restore the
# `@ch03.beat(...)` decorator at that point.

# Bike Wheel -> Bicycle. The wheel's only source corpus-wide is Route 4
# (CH11, Act 3, per the wiki and spec §5 #3) -- unreachable from CH03. Kept
# for CH11 to pick up once Route 4's grant exists.
def b15_bike_wheel_deferred(emu: Emulator) -> None:
    emu.walk_to(*BIKE_SHOP_NPC_APPROACH)
    emu.face(BIKE_SHOP_NPC_FACING)
    emu.interact()
    emu.advance_dialog()
    # Would assert: Bike Wheel deleted, BICYCLE granted -- `Emulator.
    # bag_item_quantity` exists now (B11/N4, this module), so the only
    # thing still blocking this is reachability, not a missing primitive.


# Cry Boy sidequest accept (page2, FLAG_HAS_STRENGTH-gated). sw86 is written
# exactly once corpus-wide (Map140/Route11, CH25) -- and it is written ON.
# CORRECTED 2026-08-18: this comment used to read "to 0/off -- never true
# anywhere in the corpus". RGSS code-121's third parameter is 0 = ON, which
# is how our own transpiler reads it (transpiler.py:2558 emits setflag when
# value == 0). So this is a genuine return-trip sidequest that opens at the
# Strength chapter, not dead content -- deferred, not unreachable.
def b18_cry_boy_accept_deferred(emu: Emulator) -> None:
    emu.walk_to(*CRY_BOY_APPROACH)
    emu.face(CRY_BOY_FACING)
    emu.interact()
    emu.advance_dialog("A")
    if not emu.flag("FLAG_SIDEQUEST_CRY_BOY"):
        shot = emu.screenshot("b18_accept_no_flag")
        raise ScenarioError(
            f"Cry Boy accept: FLAG_SIDEQUEST_CRY_BOY not set ({shot})")


# Compensation Man's Luxi gift (map31 EV50, sw130/FLAG_FILE_RECOVERY-gated).
# Reads as a developer save-recovery flag (spec §7), never written anywhere
# in the corpus (on or off) -- not normal progression, not a testable beat.
def compensation_man_deferred(emu: Emulator) -> None:
    raise NotImplementedError(
        "Compensation Man's gift is gated on a dev-only flag never set "
        "anywhere in the corpus")


# Richard's post-Gym-5 team (sw94-gated second trainerbattle call on the
# same page). Even setting sw94 couldn't reach this: B23 already shows
# Map019_EV006_Page1 has no trainerbattle* call on EITHER branch in the
# compiled script (module finding 1) -- this is doubly unreachable, not
# just gated.
def b23_post_gym5_deferred(emu: Emulator) -> None:
    raise NotImplementedError(
        "Richard's harder team needs sw94 AND a trainerbattle* command "
        "that does not exist in the compiled script at all"
    )


# B19-B24: the Grott-Hole cave. Needs HM04 Strength, which does not arrive
# until CH25 (Route 11, `reference/chapters/00-atlas.md` line 116) --
# `pbPushThisBoulder` (`reference/scripts_dump/101__PField_Field.rb`) is
# gated on `$PokemonMap.strengthUsed` and does nothing until then, so every
# boulder sealing this cave is CORRECTLY immovable in CH03 -- this is the
# game's design working, not a converter gap (module docstring finding 8;
# confirmed against `output/uranium-build/wiki/Kevlar_Town.wiki` lines
# 28/30 and `Passage_Cave.wiki` line 10, both of which describe this as
# return-trip content reached only after fetching HM04 in Legen Town).
# Restore all 6 together once a chapter reaches this cave post-Strength.
DEFERRED_BEATS = (
    ("B15b", "Bike Wheel -> Bicycle grant", b15_bike_wheel_deferred),
    ("B18b", "Cry Boy sidequest accept", b18_cry_boy_accept_deferred),
    ("B26", "Compensation Man's Luxi gift", compensation_man_deferred),
    ("B23b", "Richard's post-Gym-5 team", b23_post_gym5_deferred),
    ("B19", "The cave door opens; arrival near (11,29) -- needs HM04 "
            "Strength (CH25) to reach past the boulder-sealed corridor",
     b19),
    ("B20", "Pushing each boulder one tile -- needs HM04 Strength (CH25); "
            "the boulders are correctly immovable without it", b20),
    ("B21", "Biker Lou battles -- needs HM04 Strength (CH25) to reach the "
            "cave at all", b21),
    ("B22", "Biker Joe battles -- needs HM04 Strength (CH25) to reach the "
            "cave at all", b22),
    ("B23", "Richard battles and sets FLAG_SIDEQUEST_CRYBOY_END -- needs "
            "HM04 Strength (CH25) to reach the cave at all", b23),
    ("B24", "The cave exit warps back to Map031 -- needs HM04 Strength "
            "(CH25) to reach the cave at all", b24),
)

# -- symbol lint surface ------------------------------------------------------
MAP_CONSTANTS: tuple[str, ...] = (
    "MAP_KEVLAR_TOWN", "MAP_KEVLAR_TOWN_POKEMART",
    "MAP_KEVLAR_TOWN_POKEMON_CENTER", "MAP_KEVLAR_TOWN_BUILDINGS",
    "MAP_PASSAGE_CAVE_GROTT_HOLE", "MAP_ROUTE_01",
)

FLAG_CONSTANTS: tuple[str, ...] = (
    "FLAG_NURSE_TUTORIAL", "FLAG_SIDEQUEST_CRY_BOY",
    "FLAG_SIDEQUEST_CRYBOY_END",
    _flag_ssa(68, CENTER_ITEM_BALL_EVENT_ID),
    _flag_ssa(68, 15), _flag_ssa(68, 16), _flag_ssa(68, 17),
    _flag_ssa(73, 6),
)

VAR_CONSTANTS: tuple[str, ...] = ("VAR_HA_MAGIKARP",)

SPECIES_CONSTANTS: tuple[str, ...] = ("SPECIES_NONE", "SPECIES_MAGIKARP")

ITEM_CONSTANTS: tuple[str, ...] = (MART_FIRST_ITEM,)

#: B27-B33 (warp-arrival facing / post-warp BGM regression floor, task
#: 2026-08-19): `LOCALID_PLAYER` for `_assert_player_facing`, "LAST_
#: PHONEME_SONG" for `Emulator.bgm_song_id`'s table bound, and every MUS_*
#: this build's own `engine/data/maps/*/map.json` currently declares for
#: the 3 checked buildings (all MUS_LITTLEROOT today -- a placeholder, not
#: assumed permanent, which is exactly why `_expected_bgm_song_id` reads it
#: fresh each run rather than hardcoding it here too).
MISC_CONSTANTS: tuple[str, ...] = ("LOCALID_PLAYER", "LAST_PHONEME_SONG", "MUS_LITTLEROOT")

ALL_CONSTANTS: tuple[str, ...] = (
    MAP_CONSTANTS + FLAG_CONSTANTS + VAR_CONSTANTS + SPECIES_CONSTANTS
    + ITEM_CONSTANTS + MISC_CONSTANTS + ("PARTY_SIZE",)
)

CHAPTER = ch03.build()
