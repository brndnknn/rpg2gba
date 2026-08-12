"""Chapter 2 -- Route 1 (`reference/chapters/02-route-1.md`).

Predecessor-chained onto `moki` (CH01): `route1.build()` gets CH01's 17 beats
prepended (renamed `moki:B1` etc.) via `ChapterBuilder(..., predecessor="moki")`.
Moki's own last beat (`B15`) is a terminal checkpoint that does not move the
player -- the run leaves off wherever B14's re-cross of the ceremony tiles
put them: Map032 (Moki Town), standing on/near the `(16, 43..45)` trigger
column (see `chapters/moki.py`'s `CEREMONY_APPROACH`/`CEREMONY_ROWS`). This
chapter's B1 owns walking from there to the real Route-1 passage (a
different, further-west column at `x=8`) and crossing it -- the same
"doc jumps location without its own row, so the next beat owns the crossing"
convention moki.py itself uses (see its B4/B13).

**Local ids are not RMXP event ids.** `ObjectEventState`/`object_event`/
`observe_object_event` (added to `Emulator` alongside this chapter) address
NPCs by their *compiled* 1-based position in the emitted map JSON's
`object_events` array, which is a remap of the RMXP event id
(`src/rpg2gba/tileset_converter/local_id_remap.py`, `load_local_id_table`).
The mapping used below was read directly from
`output/uranium-build/staging/local_ids/Map033.json` (fresh-run artifact,
checked 2026-08-10) -- not guessed:

    RMXP EV030 "Flood"              -> local id  8
    RMXP EV035 "Brandon" (triathlete) -> local id 11
    RMXP EV103 "Lynette"            -> local id 27
    RMXP EV029 "Rock"               -> local id  7
    RMXP EV036 "Rock"               -> local id 12

Map081 (the old rod house) has its own, separate local-id table --
`output/uranium-build/staging/local_ids/Map081.json` -- checked 2026-08-16:

    RMXP EV001 "fisherman" -> local id 1
    RMXP EV002 "brother"   -> local id 2

Every other `FLAG_*`/`VAR_*`/`MAP_*` symbol is resolved by name through
`Emulator.resolve_constant`/`Emulator.flag`/`Emulator.var` -- never a
hardcoded id (CLAUDE.md Section 6). Coordinates are plain ints (not symbols,
no name to late-bind to) and were cross-checked against the live converted
data, not copied blind from the chapter doc -- see "Doc vs. data" below.

**Doc vs. data.** Every event id/coordinate in `reference/chapters/
02-route-1.md` section 3.1 was checked against `output/uranium-build/maps/
Map033.json` and `Map081.json` directly. All 51 Map033 events and all 4
Map081 events match the doc's coordinates exactly -- no discrepancy found on
ids or (x, y). One thing the doc's beat table does NOT capture: every item
ball (`EV002/003/008/025/032/037/050`) has RMXP `trigger: 0` (action button)
and `through: false` (solid), *not* a step-on trigger -- the doc's "walk onto
EV002 item tile" phrasing is imprecise. The player must approach an adjacent
tile, face the item, and press A, exactly like the moki/Bambo NPC-interact
convention, not walk onto it. Beats below do that, not a walk-onto.

**Rock-Smash-gated reachability -- resolved from real collision data, not
assumed.** Rock Smash is not obtainable until CH06, so every boulder on
Route 1 stands for the whole of this chapter. BFS over the compiled collision
grid (`engine/data/layouts/Route01/map.bin`, the same 2-bit field
`Emulator._plan_route` walks), from this chapter's arrival tile (70,11) with
the 6 boulder tiles blocked, reaches **732 tiles**; removing a boulder from
the block set is what a smash would do. A leave-one-out sweep finds a single
chokepoint -- smashing `EV036 (14,16)` *or* `EV038 (15,17)` opens the region
to 974 tiles (956 if you ignore the staircase diagonals -- see below); the
other four (EV029/040/042/044) gate nothing and in fact sit inside the pocket
themselves.

That chokepoint is load-bearing for a large share of the route. Behind it:
5 of the 9 battle trainers (EV009 Marko, EV010 Bob, EV035 Brandon/triathlete,
EV039 Brandon/phone, EV041 Gertha), the EV008 Repel, EV037 Super Potion and
EV032 Rare Candy balls, and the entire second MB_SIDEWAYS_STAIRS run at
(52,41)-(53,44). This chapter therefore tests **4 trainers, not 9**: EV030
Flood, EV034 Tath, EV053 Richey, EV103 Lynette. The gated beats are written
and kept but not registered -- see `DEFERRED_ROCK_GATED` at the end of this
module, which also states exactly what coverage that costs.

**Reachability analysis must model sideways stairs, and `_plan_route` does
not.** EV032 Rare Candy (55,41) sits in a 13-tile pocket whose only link to
the rest of the route is the (52,41)-(53,44) staircase, and that link is a
*diagonal* step: `GetRightSideStairsDirection` (`field_player_avatar.c`) maps
EAST to SOUTHEAST and WEST to NORTHWEST on an MB_SIDEWAYS_STAIRS_RIGHT_SIDE
tile, so (52,42) --EAST--> (53,43) crosses a blocked (53,42) that is never
entered (`GetSidewaysStairsCollision` returns COLLISION_NONE without
re-checking the diagonal target). A plain 4-neighbour BFS reports that pocket
as unreachable in every rock configuration, which is wrong. `walk_to` inherits
the same blind spot: `Emulator._plan_route` is 4-neighbour, so it cannot plan a
route that needs a staircase. Any future beat that must cross one has to step
it manually, the way B2 does -- do not hand the far side to `walk_to`.

**Out of scope, not tested here (see module-level rationale per item):**
- All 6 Rock-Smash boulders as *positive* beats (smashing one) -- the move
  is unobtainable until CH06; only negative-tested (`N2`).
- `water_mons` and the EV143-147 shoreline vehicle-cancel events -- need
  Surf, not obtainable until much later (act A5).
- All three `fishing_mons` tables -- the Old Rod itself is gated (`N1`);
  Good/Super Rod are chapters away.
- EV028 "Luz" ambient glow -- deliberately stripped (CH02_TODO #12), must
  NOT be expected in the ROM.
- Berry plants (EV100/101/102) -- EV101 has no `pbPickBerry` call at all
  (faithful to the source, not a bug); EV100/EV102 are skipped here as
  optional/low-value per the brief -- picking one is a plain interact + a
  bag-state check the harness has no read for anyway (no item/bag surface
  is exposed on `Emulator`), so there is nothing this harness can assert
  beyond what the item-ball beats below already cover.
- The 3 dropped learnset moves (CH02_TODO #11) -- accepted debt, not a
  chapter-2 playtest concern.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..battle import in_battle, read_enemy_party, win_battle
from ..chapter import ChapterBuilder
from ..errors import ScenarioError

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # runtime import is lazy so the registry works without bindings
    from ..emulator import Emulator

route1 = ChapterBuilder("route1", doc="reference/chapters/02-route-1.md", predecessor="moki")

# -- coordinates (see module docstring for provenance) -----------------------

# B1: the real Moki Town -> Route 1 passage. Distinct from moki.py's
# CEREMONY_APPROACH column (x=16-17) -- this is further west, at the map's
# edge (Map032.json EV037/EV023/EV036, (8,43)/(8,44)/(8,45), each
# pbCaveEntrance + code 201 -> Map033(70,11)). Crossing from (9,44).
ROUTE1_ENTRY_APPROACH = (9, 44)
ROUTE1_ENTRY_DIRECTION = "LEFT"
ROUTE1_ARRIVAL = (70, 11)

# B2/B3: the two sideways-staircase runs (CH02_TODO #14). Both are native
# MB_SIDEWAYS_STAIRS_* redirects: pressing a *horizontal* direction toward
# the column produces a diagonal step. `walk_to`'s planner treats the column
# as ordinary flat terrain (it is, post-fix), so beats step directly rather
# than routing through `walk_to`, to actually exercise the redirect instead
# of whatever route the planner happens to prefer.
STAIR1_EAST_APPROACH = (58, 10)
STAIR1_WEST_APPROACH = (56, 9)
STAIR2_WEST_APPROACH = (51, 41)
STAIR2_EAST_APPROACH = (54, 44)

# B4: a confirmed MB_TALL_GRASS cell (behavior byte read directly from
# `engine/data/tilesets/{primary,secondary}/uranium1033/metatile_attributes.bin`
# against `Route01/map.bin`'s per-cell metatile ids -- 137 grass cells total
# across the map, matching CH02_TODO #15's own count exactly). Two adjacent
# grass tiles to shuffle between for repeated encounter rolls.
GRASS_CELL_A = (30, 7)
GRASS_CELL_B = (31, 7)

# The route's 9 battle trainers. Facing is read from each event's page-0
# `graphic.direction` (RMXP: 2=down, 4=left, 6=right, 8=up) -- the direction
# the sight cone extends *from* the trainer, so the approach lane runs along
# that vector back toward the trainer.
#
# Only 4 of the 9 are reachable this chapter; the other 5 sit behind the
# EV036/EV038 rock chokepoint (see module docstring). Beat names are NOT
# renumbered to close the gaps -- B5/B6/B9/B10/B12 stay deregistered under
# their original names so they keep lining up with the chapter doc's rows.
#
# A plain sight trainer's "defeated" state is NOT a `FLAG_MAP033_EVENT*_SSA`
# self-switch -- that convention is for ITEM balls and berries only (see
# `_flag_ssa`). Sight trainers are emitted as native `trainerbattle_single`
# (`engine/data/maps/Route01/scripts.inc`), so their defeat state lives in
# the standard Emerald trainer flag table: `TRAINER_FLAGS_START +
# <trainer_const>`. `trainer_const` below is read from that same
# scripts.inc, cross-checked against `engine/include/constants/
# uranium_trainer_ids.h` via `probe_constants` (see
# tests/test_route1_constants.py).
@dataclass(frozen=True)
class TrainerBeat:
    event_id: int          # RMXP event id, for traceability/comments only
    xy: tuple[int, int]
    facing: str
    trainer_const: str     # native TRAINER_* id, e.g. "TRAINER_FLOOD_2"


TRAINER_FLOOD = TrainerBeat(30, (21, 23), "RIGHT", "TRAINER_FLOOD_2")
TRAINER_TATH = TrainerBeat(34, (36, 8), "DOWN", "TRAINER_TATH_1")
TRAINER_LYNETTE = TrainerBeat(103, (51, 25), "RIGHT", "TRAINER_LYNETTE_246")
TRAINER_RICHEY = TrainerBeat(53, (17, 9), "DOWN", "TRAINER_RICHEY_3")

# Rock-gated trainers -- constants kept for the deferred beats below.
TRAINER_MARKO = TrainerBeat(9, (30, 41), "DOWN", "TRAINER_MARKO_19")
TRAINER_BOB = TrainerBeat(10, (48, 42), "UP", "TRAINER_BOB_20")
TRAINER_BRANDON_TRIATHLETE = TrainerBeat(35, (15, 23), "DOWN", "TRAINER_BRANDON_18")
TRAINER_GERTHA = TrainerBeat(41, (25, 37), "DOWN", "TRAINER_GERTHA_17")
TRAINER_BRANDON_PHONE = TrainerBeat(39, (13, 36), "DOWN", "TRAINER_BRANDON_16")

ALL_TRAINERS: tuple[TrainerBeat, ...] = (
    TRAINER_FLOOD, TRAINER_TATH, TRAINER_LYNETTE, TRAINER_RICHEY,
    TRAINER_MARKO, TRAINER_BOB, TRAINER_BRANDON_TRIATHLETE, TRAINER_GERTHA,
    TRAINER_BRANDON_PHONE,
)

# `TRAINER_REGISTERED_FLAGS_START + REMATCH_URANIUM_*` -- resolvable as a
# constant *expression* (mirrors moki.py's `MAP_GROUP({map_const})` pattern);
# there is no standalone `FLAG_REGISTERED_URANIUM_*` #define, only a comment
# recording its numeric value in the generated
# `engine/include/constants/uranium_rematches.gen.h`.
BRANDON_PHONE_REGISTERED_FLAG = "TRAINER_REGISTERED_FLAGS_START + REMATCH_URANIUM_BRANDON_16"
RICHEY_REGISTERED_FLAG = "TRAINER_REGISTERED_FLAGS_START + REMATCH_URANIUM_RICHEY_3"

# B14: pacing regression (CH02_TODO #9). Local ids, NOT RMXP event ids --
# see module docstring.
FLOOD_LOCAL_ID = 8            # RMXP EV030, LOOK_AROUND
LYNETTE_LOCAL_ID = 27         # RMXP EV103, LOOK_AROUND
# RMXP EV035, WALK_UP_AND_DOWN range 2 -- rock-gated, so the only
# WALK_UP_AND_DOWN trainer on the route is unobservable this chapter (an
# object event that far outside the player's region is not even loaded into
# `gObjectEvents`). See DEFERRED_ROCK_GATED.
BRANDON_TRIATHLETE_LOCAL_ID = 11

# B15/B15b/B15c: item balls. `(event_id, item_xy, approach_xy, facing)`.
# Approach tiles were checked walkable against the live collision grid.
ITEM_POTION_A = (2, (50, 7), (50, 8), "UP")
ITEM_POTION_B = (3, (31, 30), (31, 29), "DOWN")
ITEM_ANTIDOTE_A = (25, (12, 9), (12, 10), "UP")
ITEM_ANTIDOTE_B = (50, (29, 7), (29, 8), "UP")
# Rock-gated (see module docstring): approach tiles sit inside the pocket
# that is unreachable while every rock is intact.
ITEM_REPEL = (8, (13, 19), (14, 19), "LEFT")
ITEM_SUPER_POTION = (37, (9, 38), (10, 38), "LEFT")
# EV032 Rare Candy is rock-gated too, but reached *through* the (52,41)-(53,44)
# staircase rather than around it -- see the module docstring's note on why
# plain 4-neighbour reachability is not enough to see that.
ITEM_RARE_CANDY = (32, (55, 41), (55, 42), "UP")

# B16/N1: the old rod house.
OLD_ROD_DOOR = (39, 18)          # Map033 side
FISHERMAN_INTERACT = (7, 9)      # Map081, south of EV001 (7,8) -- EV001 is
                                  # move_type 0 (fixed, compiled
                                  # MOVEMENT_TYPE_FACE_DOWN, `Route01OldRodHouse/
                                  # events.inc`), so a static approach is correct.
SIGN_INTERACT = (9, 6)           # Map081, south of EV004 (9,5)
OLD_ROD_HOUSE_EXIT_APPROACH = (9, 13)
OLD_ROD_ARRIVAL = (9, 12)
# EV002 "brother", by contrast, is NOT static -- Map081.json's move_type is 3
# (custom route), the compiled route is codes 3,3,2,2 repeat (RMXP: 3=move
# right, 2=move left), and `Route01OldRodHouse/events.inc` confirms it:
# `object_event 2, ..., 12, 8, 3, MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE, ...` --
# spawns at (12,8) and paces right,right,left,left, oscillating x across
# {12,13,14} at a fixed y=8 (~100-130 frames per step, observed live).
#
# 2026-08-16 B16 regression: the beat used to walk to a hardcoded
# `BROTHER_INTERACT = (12, 9)` and face UP, which only worked if the brother
# happened to be sitting at his spawn tile at that exact moment. Live probe
# (seeded from the B16 blob, `_enter_door` + walking to (12,9)): by the time
# the player's walk to (12,9) completes, the brother has already paced to
# (14,8) -- up and to the RIGHT of the player, matching the failure
# screenshot exactly -- so `emu.face("UP"); emu.interact()` presses A at
# empty (12,8) and `interact()` fails loud ("interaction did not start a
# script"). Source data, compiled engine data, and this live read all agree
# on the same custom route -- the ROM is correct, the harness's assumed
# static tile was stale. Fixed by `_approach_moving_npc` below, which
# re-reads the NPC's LIVE position from `gObjectEvents` each attempt instead
# of a fixed tile -- the same "trust the live read over the documented
# spawn-time snapshot" fix `_effective_trainer_facing` already applies to
# LOOK_AROUND trainers, just for position instead of facing.
BROTHER_LOCAL_ID = 2  # Map081 EV002 -- see local-id table in the module docstring.
BROTHER_FACING = "UP"  # player always approaches from the south, the only
                        # walkable row adjacent to the patrol's fixed y=8.
# EV001 the fisherman lives on Map081, so his self-switch carries the Map081
# prefix -- `_flag_ssa` builds Map033 names and must not be used for him.
FISHERMAN_SSA_FLAG = "FLAG_MAP081_EVENT001_SSA"

# N2: (event local id, xy, approach, facing). Only EV036 and EV038 have a
# reachable approach tile with the cluster intact -- and they are exactly the
# two boulders that gate the pocket, so they are also the only two whose
# refusal-to-smash is load-bearing. The other four (EV029/040/042/044) sit
# inside the gated pocket themselves and cannot be walked up to at all.
ROCK_EV036 = (12, (14, 16), (14, 15), "DOWN")
ROCK_EV038 = (14, (15, 17), (15, 16), "DOWN")

# B17: the north boundary, currently blocked terrain (see B17's own comment).
NORTH_EXIT_APPROACH_A = (15, 6)
NORTH_EXIT_APPROACH_B = (16, 6)
NORTH_EXIT_TILE_B = (16, 5)  # for B17's failure message only; never stepped on


# -- small local helpers, copied+adapted from chapters/moki.py --------------
# (moki.py's own docstring: "deliberately not yet factored into a shared
# module" -- do not import from it, copy the idiom.)

def _at_map(emu: Emulator, map_const: str) -> bool:
    group, num = emu.map_location()
    return (group, num) == (
        emu.resolve_constant(f"MAP_GROUP({map_const})"),
        emu.resolve_constant(f"MAP_NUM({map_const})"),
    )


def _require_map(emu: Emulator, beat: str, map_const: str) -> None:
    if _at_map(emu, map_const):
        return
    group, num = emu.map_location()
    shot = emu.screenshot(f"{beat}_wrong_map")
    raise ScenarioError(
        f"{beat}: expected map {map_const} but map_location() reads "
        f"group={group} num={num} ({shot})"
    )


def _try_step(emu: Emulator, direction: str) -> bool:
    """Attempt exactly one step without `walk_to`'s retry-until-arrived loop
    -- see moki.py's identical helper for the full rationale."""
    before = emu.player_pos()
    moved = False
    for _ in range(40):
        emu.run(1, [direction])
        if emu.player_pos() != before:
            moved = True
            break
    emu.run(16)
    return moved


def _wait_for_map(emu: Emulator, beat: str, map_const: str,
                  frame_budget: int = 900) -> None:
    spent = 0
    while spent < frame_budget and not _at_map(emu, map_const):
        emu.run(10)
        spent += 10
    _require_map(emu, beat, map_const)


def _cross_threshold(emu: Emulator, beat: str, approach: tuple[int, int],
                     direction: str, dest_map: str) -> None:
    # Pure navigation, no battle is the objective here -- absorb either
    # kind of incidental traffic (see `_walk_absorbing`'s docstring).
    _walk_absorbing(emu, beat, *approach, absorb_wild=True, absorb_trainer=True)
    _try_step(emu, direction)
    _wait_for_map(emu, beat, dest_map)


def _enter_door(emu: Emulator, beat: str, door: tuple[int, int],
                dest_map: str, hold: int = 48) -> None:
    dx, dy = door
    _walk_absorbing(emu, beat, dx, dy + 1, absorb_wild=True, absorb_trainer=True)
    emu.run(hold, ["UP"])
    _wait_for_map(emu, beat, dest_map)


def _advance_to_battle(emu: Emulator, max_taps: int = 1500) -> int:
    """`emu.advance_dialog()`, but stopping if a battle starts (see moki.py)."""
    return emu.advance_dialog(max_taps=max_taps, stop=lambda: in_battle(emu))


def _assert_near(emu: Emulator, beat: str, expected: tuple[int, int],
                 tolerance: int = 1) -> None:
    x, y = emu.player_pos()
    ex, ey = expected
    if abs(x - ex) > tolerance or abs(y - ey) > tolerance:
        shot = emu.screenshot(f"{beat}_wrong_landing")
        raise ScenarioError(
            f"{beat}: landed at ({x},{y}), expected near {expected} "
            f"(tolerance {tolerance}) ({shot})")


# -- new local helpers, specific to Route 1's mechanics ----------------------

_DIR_VECTOR: dict[str, tuple[int, int]] = {
    "DOWN": (0, 1), "UP": (0, -1), "LEFT": (-1, 0), "RIGHT": (1, 0),
}

# Stepping TOWARD a trainer along its own facing lane means walking in the
# opposite direction to that facing (the lane extends FROM the trainer
# outward, per `_DIR_VECTOR` above) -- used by `_approach_sight_trainer`/
# `_assert_no_second_battle`'s single-tile inward steps (`_step_absorbing`).
_OPPOSITE_DIR: dict[str, str] = {
    "DOWN": "UP", "UP": "DOWN", "LEFT": "RIGHT", "RIGHT": "LEFT",
}

# Bound on how many incidental battles `_walk_absorbing` will fight off /
# clear in one call before giving up -- same bounded-retry shape as
# `walk_to(resolve_interruptions=True)`'s own cap, but sized for what a
# grass crossing actually needs, not guessed. Route 1 has 137 grass cells
# at a 25% per-step encounter rate, and a route through a grass field (B7's
# regression: Flood stands inside one, so the whole approach lane crosses
# it) can plausibly be 10-15 tiles of grass. Modelling that as Binomial(n,
# p) with n=15 (the longer end of that range) and p=0.25 -- the tail
# probability of needing MORE than k encounters absorbed:
#
#     k=3  (the old cap): P(X>3)  ~= 4.7e-1   -- routinely exceeded, hence
#                                                the observed failures
#     k=8:                P(X>8)  ~= 4.2e-3
#     k=10:                P(X>10) ~= 1.2e-4
#     k=12:                P(X>12) ~= 9.2e-7
#
# 12 keeps the false-failure rate astronomically small (under 1e-6 for the
# single longest plausible crossing on this route) while still failing loud
# on a genuinely pathological loop (an unwinnable battle that instantly
# re-triggers hits this cap in 12 iterations, not never).
_MAX_ABSORBED_INTERRUPTIONS = 12

# Per-attempt frame budget passed to each `emu.walk_to(...)` call inside the
# retry loop below -- explicit, not `walk_to`'s own 3000 default, so a
# resumed walk's budget is unambiguously a fresh, generous allowance rather
# than something that could be read as "the original call's leftover
# budget" (it never is: each retry is a brand-new `walk_to()` call, but a
# grass-heavy leg can burn through the default 3000 via `_MAX_REPLANS`
# replans and `_INTERRUPT_GRACE` waits before ever cleanly resolving to
# `WalkInterrupted` or arrival -- see the 2026-08-14 B7 budget-exhaustion
# failure). Doubling it removes the per-attempt budget as the limiting
# factor; `_MAX_ABSORBED_INTERRUPTIONS` above is what actually bounds the
# overall retry loop.
_WALK_ABSORBING_FRAME_BUDGET = 6000


def _walk_absorbing(emu: Emulator, beat: str, tx: int, ty: int, *,
                    absorb_wild: bool, absorb_trainer: bool,
                    max_absorbed: int = _MAX_ABSORBED_INTERRUPTIONS,
                    frame_budget: int = _WALK_ABSORBING_FRAME_BUDGET) -> None:
    """Walk to `(tx, ty)`, absorbing whichever kind(s) of battle the caller
    declares as incidental traffic, and handing control straight back --
    `WalkInterrupted` still uncaught -- the instant a battle of the OTHER
    kind is detected, so the beat can handle it as the thing it's actually
    testing.

    The map has 137 grass cells at a 25% encounter rate and up to 9 trainer
    sight cones, so essentially any walk on this route can cross either
    kind of incidental battle traffic -- this is the one navigation
    primitive every `walk_to` call in this module should go through, with
    an explicit policy per caller:

    - A beat whose objective IS a wild encounter (B4): `absorb_wild=False,
      absorb_trainer=True` -- fight off an ambushing trainer, but hand a
      wild battle back untouched.
    - A beat whose objective IS a trainer's own battle (`_approach_sight_
      trainer`/`_assert_no_second_battle`, used by every `_battle_trainer`
      beat): `absorb_wild=True, absorb_trainer=False` -- clear incidental
      wild traffic, but hand the trainer's own battle back untouched (and
      never accidentally auto-win/auto-clear a *different* trainer's
      ambush either -- that would just show up as an already-defeated
      flag the way `_battle_trainer` already tolerates).
    - Pure navigation with no battle as its objective (item pickups, door/
      threshold crossings, rock approaches, the north boundary):
      `absorb_wild=True, absorb_trainer=True` -- neither kind should ever
      fail a beat that is testing something else.

    Each retry is a brand-new `emu.walk_to(tx, ty, frame_budget)` call with
    the SAME explicit `frame_budget` every time -- never a value carried
    over or decremented from a previous attempt, so a long grass crossing
    that needs several absorbed battles isn't also fighting a shrinking
    budget on top of the bounded retry count.

    `walk_to` is called with `resolve_interruptions` left at its default
    (off) deliberately: that resolver can't distinguish trainer from wild,
    and unconditionally auto-winning would destroy whichever kind of
    battle the caller declared as its objective. So this catches
    `WalkInterrupted` itself and branches on `Emulator.is_trainer_battle()`.

    A `WalkInterrupted` with `battle=False` means the field is locked but
    no battle has actually started yet -- a sight trainer's pre-battle
    msgbox, still waiting on a button `walk_to` isn't pressing (the
    original 2026-08-11 route1 B4 failure: "Oh! Hey! RED! ..." sitting on
    screen while `walk_to` burned its frame budget). `_advance_to_battle`
    mashes past exactly that, stopping the instant a battle actually
    starts -- covering both "this becomes the trainer's own battle" (the
    common case for `_approach_sight_trainer`) and "this becomes a wild
    battle instead" (unlikely mid-dialogue, but not assumed away) -- so
    this never blind-mashes through real combat trying to clear dialogue
    the way a generic `resolve_interruption()` call by itself would.
    """
    # Lazy, same discipline as the module's other emulator-internals import
    # (see the TYPE_CHECKING block at the top of this file): keeps this
    # registry importable without the mgba bindings installed.
    from ..emulator import WalkInterrupted

    for _ in range(max_absorbed):
        try:
            emu.walk_to(tx, ty, frame_budget)
            return
        except WalkInterrupted as exc:
            if exc.battle:
                trainer = emu.is_trainer_battle()
            else:
                _advance_to_battle(emu)
                if not in_battle(emu):
                    continue  # nothing left to absorb; retry toward target
                trainer = emu.is_trainer_battle()
            if trainer and not absorb_trainer:
                return  # the trainer's own battle -- hand it back untouched
            if not trainer and not absorb_wild:
                return  # a wild battle -- hand it back untouched
            # Incidental, and this caller's policy says absorb it.
            # resolve_interruption() wins/clears it via the existing battle
            # helper AND settles the overworld (map grid reload) before
            # handing back -- reuse it rather than duplicating that settle
            # here.
            emu.resolve_interruption()
    shot = emu.screenshot(f"{beat}_ambush_cap")
    raise ScenarioError(
        f"{beat}: absorbed {max_absorbed} incidental "
        f"battles walking toward {(tx, ty)} without reaching it ({shot})")


def _step_absorbing(emu: Emulator, beat: str, direction: str, *,
                    absorb_wild: bool, absorb_trainer: bool,
                    max_absorbed: int = _MAX_ABSORBED_INTERRUPTIONS) -> bool:
    """`_walk_absorbing`'s single-grid-step analogue: press `direction` for
    exactly one tile (`_try_step`), absorbing whichever kind(s) of
    incidental battle the caller declares, without ever going through
    `walk_to`/`_plan_route`. Returns whether the step ultimately moved the
    player (mirrors `_try_step`; false only means genuinely blocked
    terrain/an NPC, never an absorbed battle -- those are retried).

    2026-08-11 route1 B7 regression: `_approach_sight_trainer`'s tile-by-
    tile inward approach used to route each already-known, already-adjacent
    1-tile hop through `_walk_absorbing` (the full Dijkstra planner).
    `_plan_route`'s grass-cost weighting (`_GRASS_TRAVERSAL_COST`) biases
    AWAY from grass when a clear detour exists, but Flood's own
    surroundings are almost solid grass -- there is no clear detour, so the
    "detour" the planner picks instead is a multi-tile loop through OTHER
    nearby grass cells before finally landing on the 1-tile target, and a
    freshly re-planned detour after every absorbed battle can bounce
    between the same 2-3 tiles indefinitely (traced live: (22,22)/(23,22)/
    (24,22), 12+ absorbed battles, without ever landing on the adjacent
    goal) -- verified via `_plan_route` directly: only ~10 grass cells sit
    on the direct route from a B4-ending position to Flood's vicinity, an
    order of magnitude short of what actually got absorbed, so the cap
    wasn't undersized for the real crossing -- the detour was manufacturing
    extra grass crossings a plain cardinal step never needed to take. A
    known-adjacent hop has nothing to plan; pressing the one direction is
    both correct and immune to the detour.
    """
    for _ in range(max_absorbed):
        if _try_step(emu, direction):
            return True
        if not in_battle(emu):
            return False  # genuinely blocked, not an absorbed battle
        trainer = emu.is_trainer_battle()
        if trainer and not absorb_trainer:
            return False  # the trainer's own battle -- hand it back untouched
        if not trainer and not absorb_wild:
            return False  # a wild battle -- hand it back untouched
        emu.resolve_interruption()
    shot = emu.screenshot(f"{beat}_step_ambush_cap")
    raise ScenarioError(
        f"{beat}: absorbed {max_absorbed} incidental battles taking one "
        f"step {direction} without moving ({shot})")


#: Bound on how many times `_approach_moving_npc` re-reads the NPC's live
#: position and retries the approach + interact before giving up. Observed
#: live (see `BROTHER_LOCAL_ID`'s comment): the brother's patrol steps land
#: roughly every 100-130 frames, and a fresh `_walk_absorbing` + `face` +
#: `interact` for an already-adjacent tile takes far less than that, so one
#: attempt almost always suffices; a few retries absorb the rare case where
#: the NPC's step lands in the handful of frames between this reading its
#: position and the interact press actually landing.
_MAX_PATROL_APPROACH_ATTEMPTS = 5


def _approach_moving_npc(emu: Emulator, beat: str, local_id: int,
                         facing: str,
                         max_attempts: int = _MAX_PATROL_APPROACH_ATTEMPTS) -> None:
    """Approach and interact with an NPC that patrols under a custom move
    route (`MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE` and friends), by re-reading
    its LIVE `gObjectEvents` position each attempt rather than trusting a
    single hardcoded approach tile.

    2026-08-16 B16 regression: a patrolling NPC's spawn tile is only where
    it starts, not where it stays -- see `BROTHER_LOCAL_ID`'s comment for the
    live trace that caught this. `facing` is the direction the PLAYER faces
    toward the NPC (mirrors every other `facing` parameter in this module),
    so the approach tile is one step behind the NPC along that vector:
    `_DIR_VECTOR[facing]` points from player to NPC, so subtracting it from
    the NPC's own live position gives the tile the player must stand on.

    Retries on `interact()`'s own failure (not a bespoke position check):
    the NPC can step again in the gap between this reading its position and
    the button press landing, and `interact()` already fails loud
    ("interaction did not start a script") in exactly that case -- catching
    that and re-reading fresh is simpler and more honest than trying to
    predict the patrol's timing.
    """
    dx, dy = _DIR_VECTOR[facing]
    for _ in range(max_attempts):
        ev = emu.object_event(local_id)
        approach = (ev.x - dx, ev.y - dy)
        _walk_absorbing(emu, beat, *approach, absorb_wild=True, absorb_trainer=True)
        emu.face(facing)
        try:
            emu.interact()
            return
        except ScenarioError:
            continue  # the NPC stepped out from under the approach -- retry fresh
    shot = emu.screenshot(f"{beat}_patrol_no_interact")
    raise ScenarioError(
        f"{beat}: could not interact with the patrolling NPC (local id "
        f"{local_id}) after {max_attempts} attempts -- it kept stepping out "
        f"from under the approach ({shot})")


def _flag_ssa(event_id: int, letter: str = "A") -> str:
    return f"FLAG_MAP033_EVENT{event_id:03d}_SS{letter}"


def _trainer_defeat_flag(trainer_const: str) -> str:
    """The standard Emerald trainer-defeat flag for a native
    `trainerbattle_single` trainer -- NOT a `FLAG_MAP033_EVENT*_SSA`
    self-switch (see `TrainerBeat`'s docstring comment above)."""
    return f"TRAINER_FLAGS_START + {trainer_const}"


def _collect_item(emu: Emulator, beat: str, event_id: int,
                  approach: tuple[int, int], facing: str) -> None:
    """Approach + press A on an action-button item ball, then confirm a
    re-touch is a documented no-op (RMXP page 1 is a single `code 0`).

    Not `emu.interact()` for the re-touch: a genuinely empty script may never
    lock the field at all, and `interact()` raises loud on exactly that --
    which would be asserting the wrong thing for a beat whose whole point is
    "nothing happens twice".
    """
    ssa = _flag_ssa(event_id)
    if emu.flag(ssa):
        raise ScenarioError(
            f"{beat} precondition failed: {ssa} already set before the pickup")
    # Pure navigation, no battle is the objective -- absorb either kind of
    # incidental traffic (see `_walk_absorbing`'s docstring).
    _walk_absorbing(emu, beat, *approach, absorb_wild=True, absorb_trainer=True)
    emu.face(facing)
    emu.interact()
    emu.advance_dialog()
    if not emu.flag(ssa):
        shot = emu.screenshot(f"{beat}_not_granted")
        raise ScenarioError(f"{beat}: {ssa} not set after the pickup ({shot})")

    emu.face(facing)
    emu.tap("A")
    emu.run(30)
    if emu.field_locked():
        emu.advance_dialog()
    if not emu.flag(ssa):
        shot = emu.screenshot(f"{beat}_flag_lost")
        raise ScenarioError(
            f"{beat}: {ssa} cleared after a re-touch -- the no-op page must "
            f"not undo the grant ({shot})")


#: `TrySpawnObjectEvents` (`engine/src/event_object_movement.c:2909-2951`)
#: only spawns a map's object-event templates into the 16-slot
#: `gObjectEvents` table (`OBJECT_EVENTS_COUNT`, `engine/include/constants/
#: global.h:93`) when the template's tile falls inside a window around the
#: player's own position: `[pos.x-2, pos.x+MAP_OFFSET_W+2]` x
#: `[pos.y, pos.y+MAP_OFFSET_H+2]` (`MAP_OFFSET_W`=15, `MAP_OFFSET_H`=14,
#: `engine/include/fieldmap.h:23-25`). A trainer whose beat runs right after
#: an earlier beat left the player elsewhere on the route (2026-08-11 route1
#: B7 regression: B7 Flood at (21,23), reached straight from B4's grass
#: cells at (30,7)/(31,7) -- dx=9..10, well outside the window on x) is not
#: in `gObjectEvents` AT ALL yet -- `object_events()` doesn't list it,
#: that's not "misplaced", it just hasn't spawned. `_sight_lane_tiles` used
#: to require the live object up front and failed loud on exactly this.
#: `MAP_OFFSET_W` itself is a safe scan cap when the live object isn't
#: available yet: walking to the farthest walkable tile within this many
#: tiles of the trainer, along its own facing axis, is guaranteed to land
#: the player inside the spawn window above (the other axis is untouched by
#: the scan, so it already matches the trainer's row/column exactly).
_SIGHT_SCAN_CAP = 15  # MAP_OFFSET_W


def _sight_lane_tiles(emu: Emulator, beat: str, trainer_xy: tuple[int, int],
                      facing: str) -> list[tuple[int, int]]:
    """The walkable tiles along `trainer_xy`'s facing-`facing` sight lane,
    closest-to-farthest, stopping at the first unwalkable tile and never
    scanning past the trainer's own live sight range when that's known.

    2026-08-14 route1 B7 regression: `_approach_sight_trainer` used to walk
    a hardcoded `standoff` distance without checking it was even walkable --
    verified against the compiled collision grid, EVERY reachable trainer's
    sight lane hits a wall well inside that assumed distance (Lynette's is
    only one tile deep), so `walk_to` planned onto solid terrain and the
    greedy stepper ground out after 8 step-aside attempts. This computes
    the approach from the live grid instead.

    When the trainer's object event IS already live (re-approaching a
    defeated trainer, or a trainer whose predecessor beat left the player
    nearby), the scan is bounded by its own `ObjectEvent.trainerRange_
    berryTreeId` (`ObjectEventState.trainer_range`) -- the exact `range`
    value `GetTrainerApproachDistance`'s per-direction functions
    (`GetTrainerApproachDistanceSouth`/`North`/`West`/`East`,
    `engine/src/trainer_see.c:665-705`) bound the approach distance to
    (`x <= trainerObj->currentCoords.x + range`, etc.) -- reading it live
    means this never wastes a walkability check the engine itself would
    never look at either.

    2026-08-11 route1 B7 regression: the trainer's object event is NOT
    guaranteed to be live at all -- see `_SIGHT_SCAN_CAP`'s comment on
    `TrySpawnObjectEvents`'s spawn window. When `object_events()` doesn't
    list it yet, the scan falls back to `_SIGHT_SCAN_CAP`, using pure
    terrain walkability (`tile_walkable`, which reads the map-wide collision
    grid regardless of what has or hasn't spawned into view). This scans
    farther than the trainer's real sight range would need, but that's
    harmless -- it only changes how far out the caller's step-by-step
    approach starts, and each step still polls for the sight trigger firing
    (see `_approach_sight_trainer`) -- walking to the farthest tile this
    finds is exactly what gets the player inside the spawn window too, so
    the object is live and readable well before the approach reaches it.

    The trainer is located by matching `trainer_xy` against the live
    `gObjectEvents` table (not a hardcoded local id -- route1.py doesn't
    track trainer local ids, only Flood/Lynette's for B14's pacing check).

    Fails loud if the lane has no walkable tile at all: a trainer facing
    straight into a wall can never trigger by sight, and that's a genuine
    conversion finding worth surfacing, not something to silently skip.
    """
    dx, dy = _DIR_VECTOR[facing]
    tx, ty = trainer_xy
    trainer_ev = next(
        (ev for ev in emu.object_events() if (ev.x, ev.y) == trainer_xy), None)
    max_dist = trainer_ev.trainer_range if trainer_ev is not None else _SIGHT_SCAN_CAP
    tiles: list[tuple[int, int]] = []
    for dist in range(1, max_dist + 1):
        cand = (tx + dx * dist, ty + dy * dist)
        if not emu.tile_walkable(*cand):
            break
        tiles.append(cand)
    if not tiles:
        shot = emu.screenshot(f"{beat}_no_approach_tile")
        raise ScenarioError(
            f"{beat}: no walkable tile along {trainer_xy}'s facing-{facing} "
            f"sight lane (scanned {max_dist}, "
            f"{'live trainer_range' if trainer_ev is not None else 'not yet spawned, using ' + str(_SIGHT_SCAN_CAP) + '-tile scan cap'}) "
            f"-- the trainer faces straight into a wall and can never "
            f"trigger by sight ({shot})")
    return tiles


def _effective_trainer_facing(emu: Emulator, trainer_xy: tuple[int, int],
                              documented_facing: str) -> str:
    """The direction to approach `trainer_xy` from: its LIVE facing if the
    object event has spawned, else `documented_facing` (the RMXP page-0
    `graphic.direction` route1.py's `TrainerBeat` records) as a best guess
    for locating it before it has.

    2026-08-11 route1 B7 regression: Flood (and Lynette) are
    `MOVEMENT_TYPE_LOOK_AROUND` (`engine/data/maps/Route01/events.inc`
    confirms the compiled template is correct), which cycles their facing
    continuously (DOWN -> RIGHT -> UP -> LEFT -> repeat, from EV030's own
    RMXP move_route) -- so `documented_facing` is only ever their SPAWN-time
    facing, not their current one, and `GetTrainerApproachDistance`
    (`engine/src/trainer_see.c:643-655`) always reads the trainer's LIVE
    `facingDirection`. Compounding this: the instant `CheckTrainer`'s sight
    scan notices the player (even from a partial/interrupted approach), it
    freezes the trainer's movement to a static `MOVEMENT_TYPE_FACE_<dir>`
    matching whatever it happened to be facing at that moment
    (`SetTrainerMovementType`, `trainer_see.c:858,980`) -- observed live: a
    B4/B7 repro run that crossed near Flood left him permanently
    `MOVEMENT_TYPE_FACE_UP`, not his documented RIGHT. Approaching along the
    stale documented facing after that point can never trigger a sight
    battle at all, no matter how long the walk -- reading the live facing
    fresh each time this is called is what actually fixes it.
    """
    ev = next(
        (e for e in emu.object_events() if (e.x, e.y) == trainer_xy), None)
    return ev.facing if ev is not None else documented_facing


# `GetTrainerApproachDistance` re-checks every frame, so a LOOK_AROUND
# trainer that hasn't been noticed yet will eventually face back toward an
# adjacent player as it cycles -- this is how long to wait for that before
# concluding the lane genuinely never triggers. Uranium's move_frequency=3
# custom route idle-gates each of the 4 turn commands behind
# `(40-2f)(6-f)` RMXP-frame ticks (021_Game_Character_v17.rb) -- f=3 ->
# 34*3=102 frames/turn, ~408 frames for a full DOWN/RIGHT/UP/LEFT cycle.
# Split across `_MAX_FACING_ATTEMPTS` attempts below, so each attempt still
# covers more than one full cycle.
_TRAINER_NOTICE_GRACE = 900

# How many times `_approach_sight_trainer` re-reads the trainer's live
# facing and re-approaches before giving up. More than one attempt matters
# because the FIRST live read can itself be stale: if the trainer hadn't
# spawned yet when this beat started (see `_effective_trainer_facing`), the
# whole first approach walks the DOCUMENTED (possibly wrong) lane, and a
# LOOK_AROUND trainer noticed-and-frozen mid-walk by an unrelated brush with
# its cone (2026-08-11 regression: observed live, a full approach + the
# entire notice grace both came up empty because the trainer had already
# been frozen facing away from the lane this run picked) never rotates
# again -- only re-reading its NOW-frozen facing and re-walking to the lane
# that actually matches can still recover.
_MAX_FACING_ATTEMPTS = 3


def _sight_triggered(emu: Emulator) -> bool:
    """True once a trainer's OWN sight trigger has actually fired: a script
    has locked the field (the notice sequence, `trainer_see.c`'s
    `TrainerExclamationMark` and on), or a TRAINER battle is already
    running. An in-progress WILD battle is explicitly NOT a trigger --
    see `_absorb_stray_wild`'s docstring for the regression this guards
    against: a bare `in_battle()` check can't tell an incidental wild
    encounter from the trainer's own battle, and treating one as the other
    silently `win_battle()`'s the wrong fight (2026-08-11 route1 B7
    regression: `_approach_sight_trainer` returned believing it had
    triggered Flood, `is_trainer_battle()` was actually False, and Flood's
    defeat flag was never set).

    `in_battle()` is checked FIRST, ahead of `field_locked()` -- a second,
    narrower cut of the same regression: a wild encounter's own battle-
    intro transition can briefly assert the field lock too (contrary to
    this module's usual "wild sets no lock at all" cases, that's only true
    before the transition begins), so checking `field_locked()` first, as
    an earlier cut of this function did, still let a wild encounter through
    as a false trigger on the frames where both happened to read true at
    once.
    """
    if in_battle(emu):
        return emu.is_trainer_battle()
    return emu.field_locked()


def _absorb_stray_wild(emu: Emulator) -> None:
    """Win and clear a WILD battle if one is currently running, so a
    caller's very next `_sight_triggered` check is never fooled by it.

    2026-08-11 route1 B7 regression: `_step_absorbing`'s single-tile hop
    only checks for a battle if the step itself failed to move the player
    (`_try_step` returning `False`) -- but a wild encounter's RNG roll
    happens as movement completes, so a step that DOES succeed can still
    leave a wild battle running immediately afterward, one level up from
    where `_step_absorbing` was looking. Every loop in this function that
    treats `_sight_triggered` as "stop, something happened" calls this
    first, so that "something" is never a wild encounter this beat's own
    step just walked into.
    """
    if in_battle(emu) and not emu.is_trainer_battle():
        emu.resolve_interruption()


def _ride_into_trainer_battle(emu: Emulator, beat: str,
                              max_taps: int = 1500) -> None:
    """Mash A through whatever currently holds the field (the trainer's
    notice dialogue) until ITS OWN battle actually starts, absorbing and
    waiting past any WILD battle that starts instead along the way.

    Replaces a plain `advance_dialog(stop=lambda: in_battle(emu))`
    (`_advance_to_battle`) at the one call site that cannot tolerate the
    ambiguity: `in_battle()` alone can't distinguish the trainer's battle
    from an incidental wild encounter starting mid-mash, and the old code
    took whichever came first as done (2026-08-11 route1 B7 regression --
    same class of bug as `_sight_triggered`'s, one step later in the flow).
    Gives up (returns without having reached a trainer battle) once neither
    a lock nor any battle remains, or `max_taps` is exhausted -- the caller
    is the one that turns "still not there" into a failure.
    """
    taps = 0
    while not (in_battle(emu) and emu.is_trainer_battle()):
        _absorb_stray_wild(emu)
        if in_battle(emu) and emu.is_trainer_battle():
            return
        if not emu.field_locked() and not in_battle(emu):
            return  # nothing left running -- the trigger fizzled out
        if taps >= max_taps:
            return
        emu.tap("A")
        taps += 1


def _approach_sight_trainer(emu: Emulator, beat: str,
                            trainer_xy: tuple[int, int], facing: str) -> None:
    """Walk the trainer's sight lane from its farthest walkable tile down to
    adjacent, stopping the instant a script takes the field (sight trigger)
    or a battle starts outright, then ride the trigger into battle.

    The approach tile is the FARTHEST walkable tile `_sight_lane_tiles`
    finds, not a fixed standoff -- entering the cone from its outer edge is
    closer to how a real player triggers a sight battle than materialising
    partway inside it, and it's also the only choice guaranteed walkable
    (see that function's docstring for the regression this fixes).

    `GetTrainerApproachDistance` reads the trainer's *live* facing/position
    every frame (trainer_see.c), so `facing` is re-resolved through
    `_effective_trainer_facing` (live when spawned, `facing`'s documented
    value otherwise) at the START OF EVERY ATTEMPT below, not just once --
    see `_MAX_FACING_ATTEMPTS` and `_effective_trainer_facing`'s docstrings
    for the LOOK_AROUND regression this fixes. If a patrol trainer has
    wandered off every lane this tries, the sight trigger may still not
    fire and this fails loud with a screenshot, which is itself a real,
    reportable result (not a harness bug).

    This trainer's OWN battle is the objective (that's what `_battle_
    trainer`'s caller wins explicitly, below), so the approach walk absorbs
    incidental WILD traffic only -- `absorb_wild=True, absorb_trainer=
    False` -- and hands back untouched the instant *any* trainer battle
    starts (this one, or, in principle, a different trainer's ambush along
    the same lane -- that would just surface as an unexpected battle here
    rather than being silently won).
    """
    for _ in range(_MAX_FACING_ATTEMPTS):
        live_facing = _effective_trainer_facing(emu, trainer_xy, facing)
        dx, dy = _DIR_VECTOR[live_facing]
        step_dir = _OPPOSITE_DIR[live_facing]
        tiles = _sight_lane_tiles(emu, beat, trainer_xy, live_facing)
        pos = tiles[-1]
        _walk_absorbing(emu, beat, *pos, absorb_wild=True, absorb_trainer=False)
        while pos != trainer_xy:
            _absorb_stray_wild(emu)
            if _sight_triggered(emu):
                break
            target = (pos[0] - dx, pos[1] - dy)
            # Single cardinal step, not `_walk_absorbing`/`walk_to` -- see
            # `_step_absorbing`'s docstring for the detour regression a
            # full Dijkstra re-plan of an already-known adjacent hop caused
            # here.
            if not _step_absorbing(emu, beat, step_dir,
                                   absorb_wild=True, absorb_trainer=False):
                break  # genuinely blocked (likely the trainer's own
                       # occupied tile) -- as close as collision allows
            pos = target
        if not _sight_triggered(emu):
            # Reached the end of this lane without triggering. For a
            # dynamically-facing (LOOK_AROUND) trainer this can simply mean
            # it isn't currently pointed this way -- give it up to one full
            # rotation to turn back before concluding this attempt's lane
            # never fires. Standing this close is itself still inside
            # grass (Flood's own field), so a WILD encounter can fire
            # during the wait too -- absorbed and waited past, not
            # mistaken for the sight trigger.
            spent = 0
            while spent < _TRAINER_NOTICE_GRACE // _MAX_FACING_ATTEMPTS:
                _absorb_stray_wild(emu)
                if _sight_triggered(emu):
                    break
                emu.run(30)
                spent += 30
        if _sight_triggered(emu):
            # `field_locked()` firing is usually the trainer's own notice
            # sequence, but not provably so from this side (2026-08-11
            # regression -- observed live: `_sight_triggered` returned True
            # here, yet mashing through it with the old plain
            # `advance_dialog(stop=lambda: in_battle(emu))` landed in nothing
            # at all, i.e. this was a false alarm, not the trigger).
            # `_ride_into_trainer_battle` mashes through it, absorbing any
            # stray wild battle, and reports back whether it actually
            # reached Flood's own battle rather than just "a" battle.
            _ride_into_trainer_battle(emu, beat)
            if in_battle(emu) and emu.is_trainer_battle():
                return
        # Nothing panned out this attempt -- re-read the live facing on the
        # next one: it may have rotated (still cycling), or if a notice
        # froze it elsewhere without this beat ever seeing the lock (a race
        # with an absorbed wild encounter), the fresh read will finally
        # pick that up instead of repeating the same now-permanently-wrong
        # lane. A `field_locked()` false alarm that fizzled out with no
        # battle at all also just falls through to retrying here, rather
        # than being trusted as a terminal "done".
    shot = emu.screenshot(f"{beat}_no_sight_trigger")
    raise ScenarioError(
        f"{beat}: walking the sight lane toward {trainer_xy} never "
        f"triggered the trainer's own battle after {_MAX_FACING_ATTEMPTS} "
        f"attempts ({shot})")


def _assert_no_second_battle(emu: Emulator, beat: str,
                             trainer_xy: tuple[int, int], facing: str) -> None:
    """N3, folded into every trainer beat: re-approaching a defeated trainer
    must not start a second battle.

    Same walkable-lane computation as `_approach_sight_trainer` (the
    trainer is already defeated, so the exact standoff distance doesn't
    matter for triggering anything -- it matters for not walking into a
    wall, which is what actually broke here). Same `absorb_wild=True,
    absorb_trainer=False` policy too: incidental wild traffic on the way
    back in is not this check's concern, but a trainer battle starting
    here is exactly the regression being asserted against, so it must
    surface as `in_battle()` being true below -- never get silently won on
    the way in.

    Also resolves `facing` through `_effective_trainer_facing` like
    `_approach_sight_trainer` does -- a defeated LOOK_AROUND trainer has
    already been frozen to a static facing by `SetTrainerMovementType`
    (`trainer_see.c:858,980`, see that helper's docstring), which is very
    likely NOT the documented spawn-time facing, so re-approaching along
    the documented lane risks walking into a wall or simply the wrong side
    of the trainer rather than testing anything.
    """
    facing = _effective_trainer_facing(emu, trainer_xy, facing)
    dx, dy = _DIR_VECTOR[facing]
    step_dir = _OPPOSITE_DIR[facing]
    tiles = _sight_lane_tiles(emu, beat, trainer_xy, facing)
    pos = tiles[-1]
    _walk_absorbing(emu, beat, *pos, absorb_wild=True, absorb_trainer=False)
    while pos != trainer_xy:
        # A stray WILD encounter left running by a step that just
        # succeeded is absorbed here too, same as `_approach_sight_trainer`
        # -- otherwise it would misreport as "refought" below just as
        # easily as it misreported as a false trigger there (2026-08-11
        # regression; see `_absorb_stray_wild`'s docstring).
        _absorb_stray_wild(emu)
        if in_battle(emu):
            break  # a real trainer battle -- exactly what this asserts against
        target = (pos[0] - dx, pos[1] - dy)
        # Single cardinal step, not `_walk_absorbing`/`walk_to` -- see
        # `_step_absorbing`'s docstring for the detour regression a full
        # Dijkstra re-plan of an already-known adjacent hop caused here.
        if not _step_absorbing(emu, beat, step_dir,
                               absorb_wild=True, absorb_trainer=False):
            break  # genuinely blocked or the (refused) trainer battle itself
        pos = target
        if emu.field_locked():
            emu.advance_dialog()
    _absorb_stray_wild(emu)
    if in_battle(emu):
        shot = emu.screenshot(f"{beat}_refought")
        raise ScenarioError(
            f"{beat}: re-approaching a defeated trainer at {trainer_xy} "
            f"started a second battle ({shot})")


def _battle_trainer(emu: Emulator, beat: str, trainer: TrainerBeat,
                    registered_flag: str | None = None) -> None:
    """Approach and fight `trainer`, then assert the end state: defeat flag
    set (and Match Call registered, if applicable), and a re-approach starts
    no second battle.

    A sight/patrol trainer's cone can cross a route `_walk_absorbing` walks
    for an earlier, unrelated beat (B4's wild-grass walk crosses Tath's
    cone -- see B4's comment; any other navigation beat with
    `absorb_trainer=True` can equally ambush any of B5-B13's trainers) --
    that ambush gets fought there and then, on the spot. By the time this
    trainer's own beat runs, the trainer may already be defeated. That is
    not a harness bug:
    the beat's job is to verify the trainer's *end state* is reached, and a
    trainer beaten en route has legitimately reached it already. So this
    checks the defeat flag FIRST and, if it's already set, skips the
    approach-and-fight (there is nothing left to fight -- the sight trigger
    would only refuse to re-battle him anyway) and goes straight to the
    same end-state assertions every other path also runs. The assertion
    that the flag IS set is never weakened either way.
    """
    defeat_flag = _trainer_defeat_flag(trainer.trainer_const)
    already_defeated = emu.flag(defeat_flag)
    if already_defeated:
        logger.info(
            "%s: %s already set before this beat ran -- %s was defeated "
            "ambushing an earlier walk, skipping the approach-and-fight",
            beat, defeat_flag, trainer.trainer_const)
    else:
        _approach_sight_trainer(emu, beat, trainer.xy, trainer.facing)
        win_battle(emu)
    if not emu.flag(defeat_flag):
        shot = emu.screenshot(f"{beat}_not_defeated")
        raise ScenarioError(
            f"{beat}: {defeat_flag} not set after the win ({shot})")
    if registered_flag is not None and not emu.flag(registered_flag):
        shot = emu.screenshot(f"{beat}_not_registered")
        raise ScenarioError(
            f"{beat}: {registered_flag} not set after the win -- Match Call "
            f"registration did not fire ({shot})")
    _assert_no_second_battle(emu, beat, trainer.xy, trainer.facing)


def _rock_smash_refused(emu: Emulator, beat: str, local_id: int,
                        rock_xy: tuple[int, int], approach: tuple[int, int],
                        facing: str) -> None:
    # Walk BEFORE the precondition read: `gObjectEvents` only holds events
    # spawned near the camera, so a boulder 25 tiles away isn't in the table
    # at all. Reading it from the old rod house door (where N1 leaves the
    # player) reports the rock as missing rather than as present-and-blocking
    # -- the 2026-08-11 N2 failure.
    # Pure navigation, no battle is the objective -- absorb either kind of
    # incidental traffic (see `_walk_absorbing`'s docstring).
    _walk_absorbing(emu, beat, *approach, absorb_wild=True, absorb_trainer=True)
    before = emu.object_event(local_id)
    if not before.active:
        raise ScenarioError(
            f"{beat} precondition failed: rock (local id {local_id}) "
            f"already erased before the attempt")
    emu.face(facing)
    before_pos = emu.player_pos()
    if _try_step(emu, facing):
        shot = emu.screenshot(f"{beat}_rock_not_blocking")
        raise ScenarioError(
            f"{beat}: stepping toward the rock at {rock_xy} moved the "
            f"player -- the boulder is not blocking movement ({shot})")
    if emu.player_pos() != before_pos:
        shot = emu.screenshot(f"{beat}_position_drifted")
        raise ScenarioError(f"{beat}: player position changed anyway ({shot})")
    emu.tap("A")
    emu.run(30)
    if emu.field_locked():
        emu.advance_dialog()
    if in_battle(emu):
        shot = emu.screenshot(f"{beat}_encounter_fired")
        raise ScenarioError(
            f"{beat}: a Rock Smash encounter battle started despite the "
            f"move being unobtainable this chapter ({shot})")
    after = emu.object_event(local_id)
    if not after.active:
        shot = emu.screenshot(f"{beat}_rock_erased")
        raise ScenarioError(
            f"{beat}: the rock (local id {local_id}) was erased despite no "
            f"Rock Smash in the party ({shot})")


# -- B1 ------------------------------------------------------------------

@route1.beat("B1", "Crossing Moki Town's east passage lands on Route 1 near (70,11)")
def b1(emu: Emulator) -> None:
    _cross_threshold(emu, "B1", ROUTE1_ENTRY_APPROACH, ROUTE1_ENTRY_DIRECTION,
                     "MAP_ROUTE_01")
    _assert_near(emu, "B1", ROUTE1_ARRIVAL)


# -- B2 ------------------------------------------------------------------

@route1.beat("B2", "The x=57 sideways staircase is walkable both directions (CH02_TODO #14 regression)")
def b2(emu: Emulator) -> None:
    # The approach walks are pure navigation (absorb both kinds of
    # incidental traffic); the staircase crossing itself uses `_try_step`,
    # not `walk_to`, so it doesn't go through `_walk_absorbing` at all --
    # a single grid step has nowhere for a battle to interrupt mid-way.
    _walk_absorbing(emu, "B2", *STAIR1_EAST_APPROACH,
                    absorb_wild=True, absorb_trainer=True)
    before = emu.player_pos()
    if not _try_step(emu, "LEFT"):
        shot = emu.screenshot("b2_east_bump")
        raise ScenarioError(
            f"B2: stepping LEFT from {STAIR1_EAST_APPROACH} onto the "
            f"staircase did not move the player -- wall bump ({shot})")
    if emu.player_pos() == before:
        shot = emu.screenshot("b2_east_no_move")
        raise ScenarioError(f"B2: player position did not change ({shot})")

    _walk_absorbing(emu, "B2", *STAIR1_WEST_APPROACH,
                    absorb_wild=True, absorb_trainer=True)
    before = emu.player_pos()
    if not _try_step(emu, "RIGHT"):
        shot = emu.screenshot("b2_west_bump")
        raise ScenarioError(
            f"B2: stepping RIGHT from {STAIR1_WEST_APPROACH} onto the "
            f"staircase did not move the player -- wall bump ({shot})")
    if emu.player_pos() == before:
        shot = emu.screenshot("b2_west_no_move")
        raise ScenarioError(f"B2: player position did not change ({shot})")


# -- B3 ------------------------------------------------------------------

# DEFERRED, not registered -- every cell of this staircase run ((52,41),
# (52,42), (53,43), (53,44)) is inside the rock-gated pocket. B2 still covers
# the MB_SIDEWAYS_STAIRS_* regression on the x=57 run, which is reachable.
# See DEFERRED_ROCK_GATED.
def b3(emu: Emulator) -> None:
    _walk_absorbing(emu, "B3", *STAIR2_WEST_APPROACH,
                    absorb_wild=True, absorb_trainer=True)
    before = emu.player_pos()
    if not _try_step(emu, "RIGHT"):
        shot = emu.screenshot("b3_west_bump")
        raise ScenarioError(
            f"B3: stepping RIGHT from {STAIR2_WEST_APPROACH} onto the "
            f"staircase did not move the player -- wall bump ({shot})")
    if emu.player_pos() == before:
        shot = emu.screenshot("b3_west_no_move")
        raise ScenarioError(f"B3: player position did not change ({shot})")

    _walk_absorbing(emu, "B3", *STAIR2_EAST_APPROACH,
                    absorb_wild=True, absorb_trainer=True)
    before = emu.player_pos()
    if not _try_step(emu, "LEFT"):
        shot = emu.screenshot("b3_east_bump")
        raise ScenarioError(
            f"B3: stepping LEFT from {STAIR2_EAST_APPROACH} onto the "
            f"staircase did not move the player -- wall bump ({shot})")
    if emu.player_pos() == before:
        shot = emu.screenshot("b3_east_no_move")
        raise ScenarioError(f"B3: player position did not change ({shot})")


# -- B4 ------------------------------------------------------------------

@route1.beat("B4", "Wild grass produces a Chyinmunk/Birbie/Cubbug encounter (CH02_TODO #15 regression)")
def b4(emu: Emulator) -> None:
    # This route (30,7)/(31,7) crosses Tath's (EV034) sight cone at (36,8)
    # (see this module's TRAINER_TATH) -- an ambush here is a real,
    # observed failure (2026-08-11 route1 run), not hypothetical.
    # `_walk_absorbing(..., absorb_wild=False, absorb_trainer=True)` fights
    # that ambush off (incidental traffic) but hands a wild encounter
    # straight back -- that's this beat's actual objective, not something
    # to auto-resolve. If Tath gets fought here, B8 (his own beat) finds
    # him already defeated -- see `_battle_trainer`'s already-defeated
    # tolerance for why that's fine, not a bug.
    _walk_absorbing(emu, "B4", *GRASS_CELL_A,
                    absorb_wild=False, absorb_trainer=True)
    max_attempts = 80  # 25% rate -- P(80 misses) < 1e-8
    for _ in range(max_attempts):
        if in_battle(emu):
            break
        target = GRASS_CELL_B if emu.player_pos() == GRASS_CELL_A else GRASS_CELL_A
        _walk_absorbing(emu, "B4", *target,
                        absorb_wild=False, absorb_trainer=True)
    if not in_battle(emu):
        shot = emu.screenshot("b4_no_encounter")
        raise ScenarioError(
            f"B4: no wild encounter after {max_attempts} grass steps -- "
            f"land_mons table not wired (CH02_TODO #15 regression) ({shot})")
    if emu.is_trainer_battle():
        shot = emu.screenshot("b4_unexpected_trainer_battle")
        raise ScenarioError(
            f"B4: in a trainer battle after the grass walk -- expected the "
            f"wild-encounter objective, not incidental trainer traffic "
            f"({shot})")

    species_ids = {
        emu.resolve_constant("SPECIES_CHYINMUNK"),
        emu.resolve_constant("SPECIES_BIRBIE"),
        emu.resolve_constant("SPECIES_CUBBUG"),
    }
    party = read_enemy_party(emu)
    mon = party[0]
    if mon.species not in species_ids:
        shot = emu.screenshot("b4_wrong_species")
        raise ScenarioError(
            f"B4: encountered species id {mon.species}, expected one of "
            f"{sorted(species_ids)} (Chyinmunk/Birbie/Cubbug) ({shot})")
    if not (2 <= mon.level <= 3):
        shot = emu.screenshot("b4_wrong_level")
        raise ScenarioError(
            f"B4: encountered level {mon.level}, expected 2-3 per "
            f"land_mons ({shot})")

    win_battle(emu)
    if in_battle(emu):
        shot = emu.screenshot("b4_still_in_battle")
        raise ScenarioError(f"B4: still in battle after win_battle() ({shot})")


# -- B5-B11: the 7 non-phone trainers --------------------------------------

# DEFERRED, not registered -- rock-gated. See DEFERRED_ROCK_GATED.
def b5(emu: Emulator) -> None:
    _battle_trainer(emu, "B5", TRAINER_MARKO)


# DEFERRED, not registered -- rock-gated. See DEFERRED_ROCK_GATED.
def b6(emu: Emulator) -> None:
    _battle_trainer(emu, "B6", TRAINER_BOB)


@route1.beat("B7", "Flood (BUGCATCHER, patrol) battles once, trainer flag latches")
def b7(emu: Emulator) -> None:
    _battle_trainer(emu, "B7", TRAINER_FLOOD)


@route1.beat("B8", "Tath (SCHOOLKID, sight) battles once, trainer flag latches")
def b8(emu: Emulator) -> None:
    _battle_trainer(emu, "B8", TRAINER_TATH)


# DEFERRED, not registered -- rock-gated. See DEFERRED_ROCK_GATED.
def b9(emu: Emulator) -> None:
    _battle_trainer(emu, "B9", TRAINER_BRANDON_TRIATHLETE)


# DEFERRED, not registered -- rock-gated. See DEFERRED_ROCK_GATED.
def b10(emu: Emulator) -> None:
    _battle_trainer(emu, "B10", TRAINER_GERTHA)


@route1.beat("B11", "Lynette (LASS, patrol) battles once, trainer flag latches")
def b11(emu: Emulator) -> None:
    _battle_trainer(emu, "B11", TRAINER_LYNETTE)


# -- B12/B13: the phone-rematch trainers -------------------------------------

# DEFERRED, not registered -- see DEFERRED_ROCK_GATED at the end of this
# module. (13,36) is inside the pocket the module docstring's BFS analysis
# shows is unreachable with every rock intact.
def b12(emu: Emulator) -> None:
    _battle_trainer(emu, "B12", TRAINER_BRANDON_PHONE,
                    registered_flag=BRANDON_PHONE_REGISTERED_FLAG)


@route1.beat("B13", "Richey the phone trainer battles and registers Match Call")
def b13(emu: Emulator) -> None:
    _battle_trainer(emu, "B13", TRAINER_RICHEY,
                    registered_flag=RICHEY_REGISTERED_FLAG)


# -- B14 -----------------------------------------------------------------

@route1.beat("B14", "Trainer pacing survives: Flood and Lynette turn in place "
                    "(CH02_TODO #9 LOOK_AROUND regression)")
def b14(emu: Emulator) -> None:
    # 2026-08-15 regression: B14 used to read `object_event(local_id)`
    # straight off wherever B13 (Richey) left the player. `TrySpawnObjectEvents`
    # (`engine/src/event_object_movement.c:2909-2951`, see `_SIGHT_SCAN_CAP`'s
    # docstring above) only keeps a template in `gObjectEvents` inside a
    # window around the player's OWN position -- at Richey's landing spot
    # neither Flood (21,23) nor Lynette (51,25) fall inside it, so local id 8
    # (Flood) simply isn't spawned yet: "no active object event with local id
    # 8 -- active local ids present: [...]" is that, not corruption.
    #
    # `_assert_no_second_battle` (already exercised by B7/B11's own
    # `_battle_trainer` call) is exactly the walk-to-adjacent-and-confirm-no-
    # rebattle primitive this needs: it routes through `_walk_absorbing`/
    # `_step_absorbing` (absorbing Route 1's 25%-rate wild grass on the way,
    # `absorb_wild=True`), lands the player adjacent to the trainer -- well
    # inside the spawn window, so the object event is live by the time this
    # reads it -- and re-resolves the trainer's LIVE (possibly rotated)
    # facing via `_effective_trainer_facing` rather than the stale documented
    # one. Confirmed from the engine, not assumed: `CheckTrainer`
    # (`engine/src/trainer_see.c:552-611`) reads the trainer's own
    # `TRAINER_FLAGS_START + <const>` flag at line 594 and returns 0 (no
    # sight trigger at all) once it's set, UNLESS a VS Seeker rematch is
    # charging (`I_VS_SEEKER_CHARGING && GetRematchFromScriptPointer(...)`,
    # line 597) -- Flood/Lynette are plain sight trainers with no
    # `registered_flag` passed to their `_battle_trainer` calls (B7/B11
    # above), so that branch never applies to them. Both were already
    # defeated in B7/B11 by the time B14 runs, so this approach cannot
    # re-trigger either battle -- reusing the primitive is safe, not just
    # convenient.
    #
    # That is NOT enough on its own, though (found live running this fix:
    # both attempts landed adjacent to Flood and still read him as static).
    # `PlayerFaceApproachingTrainer`, the same notice sequence that already
    # ran during B7/B11's own approach, permanently overwrites the trainer's
    # *template* movement type to a static `FACE_<dir>` the instant it
    # fires -- `SetTrainerMovementType(trainerObj,
    # GetTrainerFacingDirectionMovementType(...))` followed by
    # `TryOverrideTemplateCoordsForObjectEvent(trainerObj, ...)`
    # (`engine/src/trainer_see.c:858-859`, repeated at `:980-981` for the
    # buried-trainer path) writes straight into
    # `gSaveBlock1Ptr->objectEventTemplates[i].movementType`
    # (`TryOverrideTemplateCoordsForObjectEvent`,
    # `engine/src/event_object_movement.c:3880-3887`) -- so Flood and
    # Lynette are BOTH already permanently frozen out of LOOK_AROUND by the
    # time B14 runs, independent of anything this beat does; that's real,
    # faithful engine behaviour (defeated patrol/sight trainers stop
    # patrolling), not a spawn-window artifact.
    #
    # The fix is a map round-trip. `objectEventTemplates` is a per-map RAM
    # cache, and `LoadObjEventTemplatesFromHeader` (`engine/src/
    # overworld.c:533-556`) unconditionally `CpuFill32`s it and re-copies
    # straight from `gMapHeader.events->objectEvents` -- the pristine ROM
    # data, unaffected by the freeze -- every time a map loads
    # (`LoadMapFromCameraTransition`, `engine/src/overworld.c:876-886`,
    # which every warp goes through). Re-entering Route 1 therefore restores
    # both trainers' compiled LOOK_AROUND movement type fresh, which is
    # exactly what this beat needs to observe -- and it does NOT touch the
    # separate `TRAINER_FLAGS_START + <const>` defeat flag (a `FlagGet`
    # bit, not a template field, see `CheckTrainer`,
    # `engine/src/trainer_see.c:594`), so the battles still cannot
    # re-trigger even after the reload. The old rod house door is the
    # nearest round-trip already wired in this module (`_enter_door`/
    # `_cross_threshold`, used again by B16/N1 below) -- it works
    # regardless of run order or the Gym-1 precondition N1 checks, since
    # entering/exiting the house needs neither.
    _enter_door(emu, "B14", OLD_ROD_DOOR, "MAP_ROUTE_01_OLD_ROD_HOUSE")
    _cross_threshold(emu, "B14", OLD_ROD_HOUSE_EXIT_APPROACH, "DOWN",
                     "MAP_ROUTE_01")

    for trainer, local_id, label in (
        (TRAINER_FLOOD, FLOOD_LOCAL_ID, "Flood"),
        (TRAINER_LYNETTE, LYNETTE_LOCAL_ID, "Lynette"),
    ):
        _assert_no_second_battle(emu, "B14", trainer.xy, trainer.facing)
        samples = emu.observe_object_event(local_id, 240, sample_every=4)
        facings = {s.facing for s in samples}
        if len(facings) < 2:
            shot = emu.screenshot(f"b14_{label.lower()}_static")
            raise ScenarioError(
                f"B14: {label} (local id {local_id}) never changed facing "
                f"over the observation window -- LOOK_AROUND pacing lost "
                f"({shot})")

    # The WALK_UP_AND_DOWN half of CH02_TODO #9 is NOT covered this chapter:
    # its only subject on Route 1 is EV035 Brandon (triathlete), who is
    # rock-gated, and an object event outside the player's loaded region is
    # not present in `gObjectEvents` to observe. The range-2 assertion lives
    # in `b14_walk_up_and_down_deferred` below, registered when the pocket
    # opens. What B14 does cover here is LOOK_AROUND, on both its subjects.


# -- B15/B15b/B15c ---------------------------------------------------------

@route1.beat("B15", "The 4 reachable ground items grant on first pickup, "
                    "not on re-touch")
def b15(emu: Emulator) -> None:
    for event_id, _item_xy, approach, facing in (
        ITEM_POTION_A, ITEM_POTION_B, ITEM_ANTIDOTE_A, ITEM_ANTIDOTE_B,
    ):
        _collect_item(emu, "B15", event_id, approach, facing)


# DEFERRED, not registered -- rock-gated, behind the staircase.
# See DEFERRED_ROCK_GATED.
def b15d(emu: Emulator) -> None:
    event_id, _item_xy, approach, facing = ITEM_RARE_CANDY
    _collect_item(emu, "B15d", event_id, approach, facing)


# DEFERRED, not registered -- see DEFERRED_ROCK_GATED at the end of this module.
def b15b(emu: Emulator) -> None:
    event_id, _item_xy, approach, facing = ITEM_REPEL
    _collect_item(emu, "B15b", event_id, approach, facing)


# DEFERRED, not registered -- see DEFERRED_ROCK_GATED at the end of this module.
def b15c(emu: Emulator) -> None:
    event_id, _item_xy, approach, facing = ITEM_SUPER_POTION
    _collect_item(emu, "B15c", event_id, approach, facing)


# -- B16 -----------------------------------------------------------------

@route1.beat("B16", "The old rod house door opens; the brother NPC and sign both "
                    "open/close dialogue cleanly")
def b16(emu: Emulator) -> None:
    _enter_door(emu, "B16", OLD_ROD_DOOR, "MAP_ROUTE_01_OLD_ROD_HOUSE")
    _assert_near(emu, "B16", OLD_ROD_ARRIVAL)

    # Indoors (Map081) -- no grass, no trainers, but pure navigation gets
    # the same blanket policy as everywhere else for consistency.
    # The brother patrols (see `BROTHER_LOCAL_ID`'s comment above) -- a
    # fixed approach tile is stale the instant he's paced off his spawn, so
    # this tracks his live position instead of walking to a hardcoded tile.
    _approach_moving_npc(emu, "B16", BROTHER_LOCAL_ID, BROTHER_FACING)
    emu.advance_dialog()
    if emu.field_locked():
        shot = emu.screenshot("b16_brother_stuck")
        raise ScenarioError(
            f"B16: the brother NPC's dialogue did not close cleanly ({shot})")

    _walk_absorbing(emu, "B16", *SIGN_INTERACT,
                    absorb_wild=True, absorb_trainer=True)
    emu.face("UP")
    emu.interact()
    emu.advance_dialog()
    if emu.field_locked():
        shot = emu.screenshot("b16_sign_stuck")
        raise ScenarioError(f"B16: the sign's dialogue did not close cleanly ({shot})")


# -- N1 (folded: fisherman refusal, then the exit back to Map033) -----------

@route1.beat("N1", "Before Gym 1 (VAR_BATTLE_VAR01 < 5), the fisherman only redirects "
                   "-- no Old Rod, no state written -- then exit the house")
def n1(emu: Emulator) -> None:
    battle_var = emu.var("VAR_BATTLE_VAR01")
    if battle_var >= 5:
        raise ScenarioError(
            f"N1 precondition failed: VAR_BATTLE_VAR01 reads {battle_var}, "
            f"expected < 5 (Gym 1/CH06 must not be cleared yet in this run)")

    # Indoors (Map081) -- same blanket navigation policy as B16.
    _walk_absorbing(emu, "N1", *FISHERMAN_INTERACT,
                    absorb_wild=True, absorb_trainer=True)
    emu.face("UP")
    emu.interact()
    emu.advance_dialog()
    if emu.field_locked():
        shot = emu.screenshot("n1_stuck")
        raise ScenarioError(
            f"N1: the fisherman's redirect dialogue did not close cleanly ({shot})")

    battle_var_after = emu.var("VAR_BATTLE_VAR01")
    if battle_var_after != battle_var:
        shot = emu.screenshot("n1_var_leaked")
        raise ScenarioError(
            f"N1: VAR_BATTLE_VAR01 changed from {battle_var} to "
            f"{battle_var_after} during the refusal ({shot})")
    # EV001's own self-switch A. EV001 is on Map081 (the Old Rod House), not
    # Map033 -- `_flag_ssa` bakes in the Map033 prefix, so this one is spelled
    # out rather than built from it.
    if emu.flag(FISHERMAN_SSA_FLAG):
        shot = emu.screenshot("n1_flag_leaked")
        raise ScenarioError(
            f"N1: EV001's self-switch A got set by the refusal path ({shot})")

    _cross_threshold(emu, "N1", OLD_ROD_HOUSE_EXIT_APPROACH, "DOWN", "MAP_ROUTE_01")


# -- N2 ------------------------------------------------------------------

@route1.beat("N2", "Rock Smash is unobtainable this chapter: 2 of the 6 boulders "
                   "refuse to erase and keep blocking movement")
def n2(emu: Emulator) -> None:
    _rock_smash_refused(emu, "N2", *ROCK_EV036)
    _rock_smash_refused(emu, "N2", *ROCK_EV038)


# -- B17 -----------------------------------------------------------------

@route1.beat("B17", "The north boundary is reachable up to the edge; do NOT cross "
                    "-- Kevlar Town (map 31) is not in SLICE_MAP_IDS")
def b17(emu: Emulator) -> None:
    # `reference/chapters/02-route-1.md` names (15,5)/(16,5) as the crossing
    # tiles into Kevlar Town (CH03). Kevlar Town is not in
    # `src/rpg2gba/tileset_converter/map_set.py`'s `SLICE_MAP_IDS`, so it is
    # not built in this ROM -- stepping onto (15,5)/(16,5) (RMXP trigger=1,
    # a step-on pbCaveExit) would attempt a warp into unbuilt map data.
    # Checked directly against the compiled collision grid
    # (`engine/data/layouts/Route01/map.bin`): (15,5) and (16,5) themselves
    # currently read as BLOCKED terrain (same "inert until wired" shape as
    # moki.py's leftover cave doors, M17) -- there is no live
    # `WARP_OVERRIDES` entry for this seam (CH02_TODO #6 only wired the west
    # triad + the old-rod-house door). So "assert the player can stand
    # there" is asserted at the approach tiles just south, and the boundary
    # tiles themselves are deliberately never stepped on. A future chapter
    # extending the frontier to Kevlar Town should revisit this beat.
    _walk_absorbing(emu, "B17", *NORTH_EXIT_APPROACH_A,
                    absorb_wild=True, absorb_trainer=True)
    _walk_absorbing(emu, "B17", *NORTH_EXIT_APPROACH_B,
                    absorb_wild=True, absorb_trainer=True)
    before = emu.player_pos()
    if _try_step(emu, "UP"):
        shot = emu.screenshot("b17_crossed")
        raise ScenarioError(
            f"B17: stepping UP from {NORTH_EXIT_APPROACH_B} toward "
            f"{NORTH_EXIT_TILE_B} moved the player -- this would cross into "
            f"unbuilt Kevlar Town data; the boundary should still read "
            f"BLOCKED on this build ({shot})")
    if emu.player_pos() != before:
        shot = emu.screenshot("b17_drifted")
        raise ScenarioError(f"B17: player position changed anyway ({shot})")


# DEFERRED, not registered -- EV035 Brandon (triathlete) is rock-gated, so the
# WALK_UP_AND_DOWN half of CH02_TODO #9 has no observable subject this
# chapter. Register alongside b9 when the pocket opens.
def b14_walk_up_and_down_deferred(emu: Emulator) -> None:
    samples = emu.observe_object_event(BRANDON_TRIATHLETE_LOCAL_ID, 240,
                                       sample_every=4)
    ys = {s.y for s in samples}
    span = max(ys) - min(ys)
    if span == 0:
        shot = emu.screenshot("b14_brandon_static")
        raise ScenarioError(
            f"B14: Brandon (triathlete, local id {BRANDON_TRIATHLETE_LOCAL_ID}) "
            f"never varied y over the observation window -- "
            f"WALK_UP_AND_DOWN pacing lost ({shot})")
    if span > 2:
        shot = emu.screenshot("b14_brandon_range")
        raise ScenarioError(
            f"B14: Brandon's y ranged {span} tiles, expected at most 2 "
            f"(movement_range_y=2) ({shot})")


# -- deferred beats ---------------------------------------------------------
#
# Written, reviewed, and deliberately NOT registered on the chapter. A chapter
# tests what its player can actually reach; registering these would hold CH02
# permanently red over content that is gated, not broken. They are kept rather
# than deleted because they are the ready-made regression tests for the
# chapter that opens the gate -- restore the `@route1.beat(...)` decorators
# (or move them into that chapter's module) at that point.
#
# Reachability was established by BFS over the compiled collision grid
# (`engine/data/layouts/Route01/map.bin`), from this chapter's own arrival
# tile (70,11), with the 6 boulder tiles treated as blocked, and with
# sideways-stairs diagonals modelled (see the module docstring -- a plain
# 4-neighbour BFS, which is all `Emulator._plan_route` does, gets this wrong).
# A leave-one-out sweep shows a single chokepoint: smashing EV036 (14,16) *or*
# EV038 (15,17) takes the reachable region from 732 to 974 tiles and opens all
# of the below at once. The other four boulders (EV029/040/042/044) gate
# nothing -- they sit inside the pocket themselves.
#
# Coverage this costs CH02, stated plainly:
#   - 5 of the route's 9 battle trainers are never fought.
#   - EV039 Brandon is one of the two phone-rematch trainers from
#     CH02_TODO #10. B13 (Richey) still exercises the rematch-registration
#     path, so the mechanism is covered; that trainer is not.
#   - The WALK_UP_AND_DOWN pacing assertion from CH02_TODO #9 has no subject.
#     B14 covers LOOK_AROUND only.
#   - The second MB_SIDEWAYS_STAIRS run is never walked. B2 covers the x=57
#     run, so the CH02_TODO #14 mechanism is covered; that run is not.
DEFERRED_ROCK_GATED = (
    ("B3", "The (52,41)-(53,44) staircase run is walkable both directions", b3),
    ("B5", "Marko (FISHERMAN, sight) battles once, trainer flag latches", b5),
    ("B6", "Bob (YOUNGSTER, sight) battles once, trainer flag latches", b6),
    ("B9", "Brandon the triathlete (patrol) battles once, trainer flag latches", b9),
    ("B10", "Gertha (EXPERT, sight) battles once, trainer flag latches", b10),
    ("B12", "Brandon the phone trainer battles and registers Match Call", b12),
    ("B14b", "Brandon (triathlete) walks a 2-tile range",
     b14_walk_up_and_down_deferred),
    ("B15b", "Repel ball at (13,19) grants on first pickup", b15b),
    ("B15c", "Super Potion ball at (9,38) grants on first pickup", b15c),
    ("B15d", "Rare Candy ball at (55,41) grants on first pickup", b15d),
)

# -- symbol lint surface ------------------------------------------------------
#
# Every FLAG_*/VAR_*/MAP_*/TRAINER_*/SPECIES_* name-or-expression this module
# resolves through `Emulator.resolve_constant`/`flag`/`var`, so a fast probe
# compile (tests/test_route1_constants.py, `offsets.probe_constants`) can
# catch a bad symbol before a long emulator run has to find it. Kept
# self-documenting: add a beat that references a new constant, add it here.
#
# N1's fisherman flag is `FISHERMAN_SSA_FLAG`, spelled out rather than built
# by `_flag_ssa`: EV001 is on Map081, and `_flag_ssa` bakes in Map033. It is
# included in the lint surface below like everything else.
MAP_CONSTANTS: tuple[str, ...] = ("MAP_ROUTE_01", "MAP_ROUTE_01_OLD_ROD_HOUSE")

SPECIES_CONSTANTS: tuple[str, ...] = (
    "SPECIES_CHYINMUNK", "SPECIES_BIRBIE", "SPECIES_CUBBUG",
)

VAR_CONSTANTS: tuple[str, ...] = ("VAR_BATTLE_VAR01",)

ITEM_SSA_FLAGS: tuple[str, ...] = tuple(
    _flag_ssa(event_id)
    for event_id, _item_xy, _approach, _facing in (
        ITEM_POTION_A, ITEM_POTION_B, ITEM_ANTIDOTE_A, ITEM_ANTIDOTE_B,
        ITEM_REPEL, ITEM_SUPER_POTION, ITEM_RARE_CANDY,
    )
)

TRAINER_DEFEAT_FLAGS: tuple[str, ...] = tuple(
    _trainer_defeat_flag(t.trainer_const) for t in ALL_TRAINERS
)

REGISTERED_FLAGS: tuple[str, ...] = (
    BRANDON_PHONE_REGISTERED_FLAG, RICHEY_REGISTERED_FLAG,
)

ALL_CONSTANTS: tuple[str, ...] = (
    MAP_CONSTANTS + SPECIES_CONSTANTS + VAR_CONSTANTS + ITEM_SSA_FLAGS
    + TRAINER_DEFEAT_FLAGS + REGISTERED_FLAGS + (FISHERMAN_SSA_FLAG,)
)

CHAPTER = route1.build()
