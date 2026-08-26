"""Chapter 4 -- Route 2 (`reference/chapters/04-route-2.md`).

Predecessor-chained onto `kevlar` (CH03): `route2.build()` gets moki's 17 +
route1's 29 + kevlar's 33 beats prepended. Kevlar's own last beat (`B25`)
stands the player at `(28, 0)` on `MAP_KEVLAR_TOWN`, one tile short of the
north edge, and asserts that edge reads BLOCKED -- at the time that beat was
written (2026-08-19/20) `KevlarTown/map.json`'s `connections` was `null`
(CH03_TODO.md decision #3). **That has changed.** Map 35 (Route 2) was added
to `SLICE_MAP_IDS` on 2026-08-25 (`tileset_converter/map_set.py:35`, same day
as this chapter's manifest approval), and `output/uranium-build/
connections.json` now carries a real row for this seam:
`[31, 'N', 11, 35, 'S', 0]` -- Map031 (Kevlar Town) has a real north
connection to Map035 at offset 11. **`kevlar.py`'s B25 has not been updated
to reflect this and will very likely start failing once map 35 actually
stages** (it currently asserts the opposite of what the wired connection
should now do) -- flagged here because it's exactly the kind of cross-chapter
regression this predecessor chain would otherwise hide; not fixed in this
file, since B25 belongs to `kevlar.py`, not this module.

**B1's approach column is now VERIFIED against real collision data**
(2026-08-26). `engine/src/fieldmap.c`'s `SetPositionFromConnection`/
`IsPosInConnectingMap` give the real formula for a NORTH connection: crossing
map031's north edge at local x transfers to map035 local x = (map031 x) -
offset, with offset=11 from `connections.json`.

The originally derived column, x=29, was WRONG and the ROM said so: it
translates to map035 x=18, which falls inside the blocked collision run
(columns 14-19) on Route 02's southmost row (row 56, decoded from
`engine/data/layouts/Route02/map.bin`). pokeemerald fills Kevlar's north
border strip from those Route 02 rows, so the step north was refused and the
player never left map031 -- the first real build of this chapter failed B1
with `expected map MAP_ROUTE_02 but map_location() reads group=75 num=10`
(= MAP_KEVLAR_TOWN). The old note's guess that x=29 was "low-risk" because
B25 confirmed x=28 was exactly the unverified reasoning it warned about:
B25 only ever tested Kevlar's OWN edge, which was never the blocked side.

x=31 is the verified replacement: Kevlar row 0 x=31 is passable, and it
translates to map035 x=20, which is in Route 02 row 56's open run (20-25,
27, 30-41; blocked: 14-19, 26, 28-29). It also clears Kevlar's own blocked
cells at x=25/26. The downstream beats (B2/B3/B4 ...) address map035 in
absolute local coordinates and do NOT depend on the arrival column, so this
change is scoped to B1.

**`MAP_ROUTE_02` is the assigned constant** (resolved 2026-08-26). This module
was authored against the proposed name `MAP_ROUTE_2` (`04-route-2.md` §7,
before any naming pass had run); the assembler's real emission follows the
zero-padded `MAP_ROUTE_01` precedent, so the constant is `MAP_ROUTE_02`
(`engine/include/constants/map_groups.h`). The anticipated mechanical rename
is done -- B1's `probe_constants` failed loud on the placeholder, exactly as
this note predicted, rather than silently resolving to the wrong map.

**Local ids are unknown for map 35** -- `output/uranium-build/staging/
local_ids/Map035.json` does not exist yet (map 35 has never been through the
staging step that produces it, per `CH04_TODO.md`'s still-open trainer-
staging item). Every RMXP event id/coordinate/facing used below was read
directly from `output/uranium-build/maps/Map035.json` (fresh-run artifact,
checked 2026-08-25), not from the local-id-remapped space `object_event()`
addresses. None of this chapter's NPCs are `MOVEMENT_TYPE_URANIUM_CUSTOM_
ROUTE` patrols (every one checked below has `move_type: 0`, static), so no
beat here needs `object_event()`/local ids at all -- every approach is a
plain coordinate, unlike kevlar.py's Magikarp/Lou/Joe/Richard or route1.py's
brother/Flood/Lynette.

**Trainer battle triggers are RPG Maker "Event Touch" (trigger=2), not
"Action Button" (trigger=0), for the two live battle beats (Larrie's page 0,
Timothy's page 0) -- but their re-talk/defeated pages (Larrie's pages 1/2,
Timothy's page 1) ARE trigger=0.** Checked directly against `Map035.json`,
not assumed from the spec's "event-touch"/"talk to" prose. Since map 35 has
never been transpiled (`unhandled: null`, CH04_TODO.md), how the transpiler
actually converts a trigger=2 solid NPC is unconfirmed -- kevlar.py's finding
was that every trigger-driven NPC in ITS roster compiled to
`TRAINER_TYPE_NONE` (plain `interact()`), but that finding is chapter-local
and not assumed to generalize. `_trigger_trainer` below tries a bump first
(the literal reading of "event touch") and falls back to `interact()` if the
bump alone doesn't lock the field or start a battle, rather than betting the
whole beat on one guess.

**Hiker Larrie's own engine trainer constant is deliberately never asserted
by name.** `CH04_TODO.md`'s open item lists exactly two constants blocking
the transpiler's fork-index gate for map 35: `TRAINER_TIMOTHY_247` and
`TRAINER_CHUCK_279`, both cited as `trainerbattle_single`. Larrie's own
`pbTrainerBattle` call (`Map035.json` event id 3, page 0) is NOT among them,
and `TRAINER_LARRIE_4` (present in `reference/uranium_id_map.json` and the
Phase-2 `intermediate/trainers.json` roster) is absent from both
`trainer_converter/common.py`'s `SLICE_TRAINER_BATTLES` tuple and the
currently-generated `output/uranium-build/trainers/trainer_manifest.json` --
i.e. nothing today stages an engine-facing trainer id for Larrie's fight at
all. Larrie's own page structure (self-switch A/B gating pages 2/1) strongly
suggests his battle converts through the same phone-rematch/facility idiom
kevlar.py's Mawuli (`_emit_facility_trainer_battle_idiom`) used rather than a
literal `trainerbattle_single`, which is plausibly why he isn't in the
blocking-constants list -- but this is inference, not a confirmed fact, and
per the task brief ("check what actually gets emitted before asserting a
constant name") no beat below reads a `TRAINER_*` flag for Larrie. B2/B11's
end-state assertions are the self-switch (`FLAG_MAP035_EVENT003_SS{A,B}`,
the same RPG-Maker-self-switch convention every item ball/berry/one-time
grant in this corpus already uses, `assertions.flag_ssa`), which the raw
`Map035.json` script literally sets via `code 123` regardless of which
engine mechanism the transpiler ultimately picks.

**B7/B8: the cave-entrance event (Map035 id 1 "EV001") is dropped whole,
not just its warp.** Per the operator's live correction (2026-08-25): Map036
(Passage Cave's own map, the warp's destination) is not in `SLICE_MAP_IDS`,
and `metadata_wiring.classify_event` decides in/out-of-slice per EVENT, not
per page -- `_event_transfers` scans every page of an event, and a single
out-of-slice `code 201` anywhere in it returns `("skip", "out-of-slice
warp")` for the WHOLE event. EV001 therefore emits nothing at all this
chapter: not page 0 (the warp itself, `pbCaveEntrance` + `code 201` to
Map036), and not page 1 (the once-per-visit `s:tsOff?("A")` autorun,
gated on switch 22 and closed off by `setTempSwitchOn("A")`). The cave-mouth
tile at (20,33) therefore compiles as ordinary BLOCKED terrain -- ONE thing
is still testable (the player can reach the approach tile and the tile
itself refuses to be crossed) and it is registered as B7 below, in the exact
shape route1.py's B17 used for its own then-unstaged Route1->Kevlar seam:
reach the approach, assert the boundary itself does not move the player, and
say in plain language that the real crossing is deferred to whichever
chapter stages map 36 (CH05). B8 (the autorun) has NO live subject at all --
nothing compiles for it this chapter -- so it is written but never
registered, in the same unregistered-deferred-beat shape kevlar.py uses for
its Strength-gated cave content (`b19`-`b24`, `DEFERRED_BEATS`); see
`b8_autorun_deferred` near the end of this module.

**B10 (the phone-rematch offer) is also written but never registered, for a
different reason than B7/B8: it is reachable in the source data but not
drivable with any primitive this harness has.** Reaching it needs self-switch
B set AND self-switch A clear on Map035 event id 3 -- per `Map035.json`,
self-switch B is set only by the WIN branch of the rematch page itself
(`pbPhoneIncrement`+`code123 B,0`/`code123 A,1` inside page 1's own body,
i.e. the state is a *product* of already having taken this path once, not a
precondition anything else can produce), and the only way into page 1's body
at all in the first place is a genuine PokeNav/Match-Call phone call
(`createPhoneTrainer`/`customTrainerBattle`), which nothing in
`playtest/emulator.py` knows how to drive (no menu-navigation primitive for
PokeNav exists, unlike the mart menu `pokecenter.py`/kevlar.py's B11 already
covers). There is also no `Emulator.set_flag`/self-switch-setter primitive
to force the precondition directly the way `set_var` lets B17/N2 in
kevlar.py force `VAR_HA_MAGIKARP` -- `Emulator` exposes `flag`/`var`/
`set_var`, and nothing that writes a flag. Per the task brief ("encode it
the way kevlar.py encodes a conditionally-reachable beat rather than
inventing a mechanism"), this is written the same way kevlar.py's
`b15_bike_wheel_deferred`/`b18_cry_boy_accept_deferred` are: a real function,
never decorated, listed in `DEFERRED_BEATS` with the missing primitive named
explicitly so a future PokeNav-driving primitive (or a `set_flag`) can
resurrect it without re-deriving any of this.

**B15's grass-cell coordinates are an unverified best-effort guess, flagged
loudly.** Route 1's own `GRASS_CELL_A`/`GRASS_CELL_B` (route1.py) were
picked by decoding real metatile-attribute bytes
(`engine/data/tilesets/{primary,secondary}/uranium1033/
metatile_attributes.bin`) against the compiled `Route01/map.bin`. No
equivalent exists for map 35 yet: `output/uranium-build/tilesets.json` only
carries primary tileset ids 1-5, not RMXP tileset id 22 (the id this
chapter's spec's own §7 "NE-quadrant reachability" investigation used, via a
one-off script whose output was not persisted to any tracked file). The two
grass cells below are picked from the open span between Larrie (y=36) and
the item ball (y=42) -- inside the corridor the spec's §1/§4.3 describe as
"tall grass" for its whole length -- but this is an inference from prose,
not a decoded passage byte. Confirm against real tileset data (or just watch
the beat run) once map 35 boot-walks; if the corridor's actual grass tiles
sit elsewhere, only `GRASS_CELL_A`/`GRASS_CELL_B` need to move, nothing else
in the beat.

**No wild encounter precedent existed in kevlar.py** (module docstring: "No
wild encounters anywhere in this chapter's roster"). B15 below is adapted
from route1.py's B4 (`_walk_absorbing`-driven shuffle between two grass
cells until `in_battle()`), the only existing wild-encounter beat in the
corpus -- reusing its idiom, not inventing a new one, per the task brief.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .. import assertions
from ..battle import in_battle, read_enemy_party, win_battle
from ..chapter import BeatLocation, ChapterBuilder
from ..errors import ScenarioError

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # runtime import is lazy so the registry works without bindings
    from ..emulator import Emulator

route2 = ChapterBuilder("route2", doc="reference/chapters/04-route-2.md",
                        predecessor="kevlar")

MAP_CONST = "MAP_ROUTE_02"  # assigned; zero-padded per MAP_ROUTE_01 -- see docstring

# -- coordinates / ids (see module docstring for provenance) -----------------

# B1: Kevlar Town's north seam -> Route 2's south edge. Derived, not
# confirmed live -- see module docstring for the SetPositionFromConnection
# formula and why x=29 was picked.
KEVLAR_SEAM_APPROACH = (31, 0)  # verified 2026-08-26; -> map035 x=20 (see docstring)
KEVLAR_SEAM_DIRECTION = "UP"

# B2/B10/B11: Hiker Larrie, Map035 event id 3 "Trainer(5)", (18,36),
# graphic direction 2 (down, i.e. faces the player from the south) ->
# approach one tile south, facing UP. Page 0 (event-touch, the initial
# fight) has no self-switch condition; page 1 (self-switch B) is the phone
# rematch offer; page 2 (self-switch A) is the defeated re-talk. Both 1 and
# 2 are `trigger: 0` (Action button), unlike page 0's `trigger: 2`.
LARRIE_EVENT_ID = 3
LARRIE_XY = (18, 36)
LARRIE_APPROACH = (18, 37)
LARRIE_FACING = "UP"

# B3/B12: the Potion item ball, Map035 event id 9 "EV009", (16,42), graphic
# direction 2 (down) -> approach one tile south, facing UP, Action button.
ITEM_BALL_EVENT_ID = 9
ITEM_BALL_XY = (16, 42)
ITEM_BALL_APPROACH = (16, 43)
ITEM_BALL_FACING = "UP"
ITEM_BALL_ITEM = "ITEM_POTION"

# B4/B14: Youngster Timothy, Map035 event id 12 "Trainer(3)", (18,47),
# graphic direction 6 (right, faces the player from the east) -> approach
# one tile east, facing LEFT. Page 0 is `trigger: 2` (event-touch, the
# fight); page 1 (self-switch A) is `trigger: 0` (Action button, the
# defeated re-talk).
TIMOTHY_EVENT_ID = 12
TIMOTHY_XY = (18, 47)
TIMOTHY_APPROACH = (19, 47)
TIMOTHY_FACING = "LEFT"
# Confirmed real per CH04_TODO.md's open blocking-constants item and
# `reference/uranium_id_map.json:1976` -- NOT yet staged into
# `trainer_converter/common.py`'s `SLICE_TRAINER_BATTLES` tuple or the
# generated `trainer_manifest.json` (that's the open build-work item this
# beat is written ahead of, same posture as kevlar.py referencing
# TRAINER_MAWULI_90 before its own staging landed).
TRAINER_TIMOTHY_CONST = "TRAINER_TIMOTHY_247"

# B5: the roadblock hint sign, Map035 event id 13 "EV013", (10,30), graphic
# direction 2 (down) -> approach one tile south, facing UP, Action button.
SIGN_ROADBLOCK_XY = (10, 30)
SIGN_ROADBLOCK_APPROACH = (10, 31)
SIGN_ROADBLOCK_FACING = "UP"
SIGN_ROADBLOCK_TEXT = ("In the event of a roadblock, Nowtoch City\n"
                       "may be reached through Passage Cave.")

# B6: the two outer, visit-1-attemptable rocks (of the 5-rock rockslide;
# 04-route-2.md §3.1: "Rocks 14 (20,28) and 17 (19,29) are outer boulders
# with an open face... Rocks 15/16/18 are interior: ... unreachable:
# boxed_in_by_outer_rocks" -- the manifest itself scopes B6 to exactly these
# two rows). Both graphic direction 2 (down) -> approach one tile south,
# facing UP, Action button.
ROCK_14_XY = (20, 28)
ROCK_14_APPROACH = (20, 29)
ROCK_17_XY = (19, 29)
ROCK_17_APPROACH = (19, 30)

# B7: the cave-mouth tile, Map035 event id 1 "EV001", (20,33), graphic
# direction 2 (down) -> approach one tile south, facing UP. See module
# docstring: the whole event is dropped (out-of-slice warp), so this tile
# reads as ordinary blocked terrain this chapter.
CAVE_MOUTH_XY = (20, 33)
CAVE_MOUTH_APPROACH = (20, 34)

# B9: the "Old entrance to Nowtoch City" sign, Map035 event id 2 "EV002",
# (19,34), graphic direction 2 (down) -> approach one tile south, facing UP,
# Action button. Distinct from id 8 "Sign" @(19,33), which the manifest
# dispositions as reachable-and-cosmetic (empty command list, no graphic) --
# not this event, and not registered as a beat.
SIGN_OLD_ENTRANCE_EVENT_ID = 2
SIGN_OLD_ENTRANCE_XY = (19, 34)
SIGN_OLD_ENTRANCE_APPROACH = (19, 35)
SIGN_OLD_ENTRANCE_FACING = "UP"
SIGN_OLD_ENTRANCE_TEXT = "Old entrance to Nowtoch City."

# B13: the Barewl, Map035 event id 11 "Barewl", (17,36), graphic direction 2
# (down) -> approach one tile south, facing UP, Action button.
BAREWL_XY = (17, 36)
BAREWL_APPROACH = (17, 37)
BAREWL_FACING = "UP"
BAREWL_TEXT = "Bare! Bar!"

# B15: land_mons wild encounters -- UNVERIFIED cell choice, see module
# docstring. `wild_encounters.json` maps["35"]["land_mons"]: rate 25,
# 12-entry table (dedupes to 6 species), levels 3-5.
GRASS_CELL_A = (18, 40)
GRASS_CELL_B = (19, 40)
LAND_MONS_SPECIES = (
    "SPECIES_CHYINMUNK", "SPECIES_BIRBIE", "SPECIES_CUBBUG",
    "SPECIES_BAREWL", "SPECIES_MANKEY", "SPECIES_OWTEN",
)
LAND_MONS_MIN_LEVEL = 3
LAND_MONS_MAX_LEVEL = 5


# -- small local helpers, adapted from route1.py's absorption machinery -----
# route1.py's `_walk_absorbing`/`_step_absorbing` were deliberately NOT
# promoted to `assertions.py` (that module's own docstring: a map with no
# wild encounters has no use for the machinery, and a future outdoor route
# needs its own rate tuning). Route 2 is exactly that future outdoor route
# -- `land_mons` rate 25, whole-corridor grass per the spec -- so this
# module carries its own copy, tuned the same conservative way route1.py's
# was, rather than reaching across chapter modules for a private helper.

_at_map = assertions.at_map
_require_map = assertions.require_map
_try_step = assertions.try_step
_wait_for_map = assertions.wait_for_map
_cross_threshold = assertions.cross_threshold
_advance_to_battle = assertions.advance_to_battle
_flag_ssa = assertions.flag_ssa


#: Bound on `_walk_absorbing`'s incidental-battle retry loop. route1.py
#: derived 12 from a Binomial(n=15, p=0.25) tail bound for its own longest
#: plausible grass crossing; Route 2's `land_mons` rate (25) and corridor
#: length are comparable in kind (a whole-corridor grass field, not a few
#: isolated cells), so the same conservative bound is reused rather than
#: re-derived from map 35's own (currently unmeasured, see module
#: docstring) grass-cell count.
_MAX_ABSORBED_INTERRUPTIONS = 12
_WALK_ABSORBING_FRAME_BUDGET = 6000


def _walk_absorbing(emu: Emulator, beat: str, tx: int, ty: int, *,
                    absorb_wild: bool, absorb_trainer: bool,
                    max_absorbed: int = _MAX_ABSORBED_INTERRUPTIONS,
                    frame_budget: int = _WALK_ABSORBING_FRAME_BUDGET) -> None:
    """Walk to `(tx, ty)`, absorbing whichever kind(s) of incidental battle
    the caller declares, and handing control back the instant a battle of
    the OTHER kind is detected. Byte-adapted from route1.py's own
    `_walk_absorbing` (see its docstring for the full design rationale) --
    the only Route-2-specific change is the reused, not re-derived, retry
    bound (see `_MAX_ABSORBED_INTERRUPTIONS`)."""
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
                    continue
                trainer = emu.is_trainer_battle()
            if trainer and not absorb_trainer:
                return
            if not trainer and not absorb_wild:
                return
            emu.resolve_interruption()
    shot = emu.screenshot(f"{beat}_ambush_cap")
    raise ScenarioError(
        f"{beat}: absorbed {max_absorbed} incidental "
        f"battles walking toward {(tx, ty)} without reaching it ({shot})")


def _trigger_trainer(emu: Emulator, beat: str, approach: tuple[int, int],
                     facing: str) -> None:
    """Approach a static, solid trainer NPC and get its battle started,
    tolerating either compiled trigger mechanism -- see module docstring
    ("Trainer battle triggers are RPG Maker Event Touch..."). Tries a bump
    (the literal Event-Touch reading) first; if that alone doesn't lock the
    field or start a battle, falls back to `interact()` (kevlar.py's
    TRAINER_TYPE_NONE finding for its own roster). Only fails loud if
    NEITHER produces a battle."""
    _walk_absorbing(emu, beat, *approach, absorb_wild=True, absorb_trainer=False)
    emu.face(facing)
    _try_step(emu, facing)
    if not emu.field_locked() and not in_battle(emu):
        try:
            emu.interact()
        except ScenarioError:
            pass
    _advance_to_battle(emu)
    if not in_battle(emu):
        shot = emu.screenshot(f"{beat}_no_battle")
        raise ScenarioError(
            f"{beat}: neither a bump nor interact() at {approach} started a "
            f"battle ({shot})")
    if not emu.is_trainer_battle():
        shot = emu.screenshot(f"{beat}_wild_not_trainer")
        raise ScenarioError(
            f"{beat}: a battle started at {approach} but it isn't a trainer "
            f"battle -- an incidental wild encounter beat this beat to the "
            f"trigger ({shot})")


def _press_a(emu: Emulator, beat: str, approach: tuple[int, int],
             facing: str) -> None:
    """Approach and press A on an Action-button (trigger 0) event -- item
    balls, signs, the Barewl, the rock no-ops, and the two Larrie/Timothy
    re-talk pages."""
    _walk_absorbing(emu, beat, *approach, absorb_wild=True, absorb_trainer=True)
    emu.face(facing)
    emu.interact()


def _settle_post_battle_script(emu: Emulator, beat: str, flag: str,
                               budget: int = 1800) -> None:
    """Drain a trainer's POST-battle script to completion, then return.

    Route 1's trainer beats can check their end-state flag the instant
    `win_battle` returns, because the flag they read is the engine's own
    `TRAINER_FLAGS_*` bit -- set inside the battle, before any script runs.
    Route 2's beats read an RPG-Maker self-switch flag instead
    (`FLAG_MAP035_EVENT*_SS{A,B}`, this module's stated convention), and
    that flag is written by the *continue script* the `trainerbattle_single`
    hands off to, which does not begin until the battle's own teardown is
    finished. Checking straight after `win_battle` therefore samples the
    flag before the writer has run.

    `if emu.field_locked(): emu.advance_dialog()` -- what B2/B4 did before
    2026-08-26 -- is not enough either, and for a reason `kevlar.py` already
    recorded once (its B4 comment, 2026-08-14: "this used to only check
    field_locked(), which is exactly what missed the scene's dropped
    completion tail"). Immediately after a battle ends the field lock can
    still read False for the frames before the continue script asserts it,
    so the single guarded call can skip the drain entirely and fall through
    to the assertion with the script yet to run.

    So: loop. Win anything that re-enters battle, mash anything that locks
    the field, and otherwise let frames pass, until the flag appears or the
    budget is spent. Returning early on the flag keeps the common case fast;
    the caller still owns the assertion, so a genuinely unwritten flag fails
    exactly as loudly as before -- this only removes the race, it never
    weakens the check.
    """
    spent = 0
    while spent < budget:
        if emu.flag(flag):
            return
        if in_battle(emu):
            win_battle(emu)
        elif emu.field_locked():
            emu.advance_dialog()
        else:
            emu.run(10)
        spent += 10
    logger.info("%s: post-battle script did not set %s within %d frames",
                beat, flag, budget)


# -- B1 ------------------------------------------------------------------

@route2.beat("B1", "Crossing Kevlar Town's north seam lands on Route 2's "
                   "south edge",
             map_constant="MAP_KEVLAR_TOWN", at=KEVLAR_SEAM_APPROACH)
def b1(emu: Emulator) -> None:
    _cross_threshold(emu, "B1", KEVLAR_SEAM_APPROACH, KEVLAR_SEAM_DIRECTION,
                     MAP_CONST)


# -- B2 ------------------------------------------------------------------

@route2.beat("B2", "Hiker Larrie's event-touch battle fires and is won; "
                   "self-switch A latches the defeated state (spec §3 B2 / "
                   "manifest map035/ev003/p0)",
             map_constant=MAP_CONST, at=LARRIE_APPROACH)
def b2(emu: Emulator) -> None:
    ssa_a = _flag_ssa(35, LARRIE_EVENT_ID, "A")
    if emu.flag(ssa_a):
        raise ScenarioError(
            f"B2 precondition failed: {ssa_a} already set before the fight")
    _trigger_trainer(emu, "B2", LARRIE_APPROACH, LARRIE_FACING)
    win_battle(emu)
    _settle_post_battle_script(emu, "B2", ssa_a)
    if not emu.flag(ssa_a):
        shot = emu.screenshot("b2_no_ssa")
        raise ScenarioError(
            f"B2: {ssa_a} not set after the win -- Larrie's own script sets "
            f"this via `code 123 A,0` in the win branch of "
            f"`Map035_EV003_Page0` ({shot})")


# -- B3 ------------------------------------------------------------------

@route2.beat("B3", "The item ball at (16,42) grants one Potion, once "
                   "(spec §3 B3 / manifest map035/ev009/p0)",
             map_constant=MAP_CONST, at=ITEM_BALL_APPROACH)
def b3(emu: Emulator) -> None:
    ssa = _flag_ssa(35, ITEM_BALL_EVENT_ID, "A")
    if emu.flag(ssa):
        raise ScenarioError(
            f"B3 precondition failed: {ssa} already set before the pickup")
    bag_before = emu.bag_item_quantity(ITEM_BALL_ITEM)
    _press_a(emu, "B3", ITEM_BALL_APPROACH, ITEM_BALL_FACING)
    emu.advance_dialog()
    if not emu.flag(ssa):
        shot = emu.screenshot("b3_no_ssa")
        raise ScenarioError(f"B3: {ssa} not set after the pickup ({shot})")
    bag_after = emu.bag_item_quantity(ITEM_BALL_ITEM)
    if bag_after != bag_before + 1:
        shot = emu.screenshot("b3_bag_unchanged")
        raise ScenarioError(
            f"B3: {ITEM_BALL_ITEM} {bag_before}->{bag_after}, expected +1 "
            f"({shot})")


# -- B4 ------------------------------------------------------------------

@route2.beat("B4", "Youngster Timothy's event-touch battle fires and is "
                   "won; self-switch A latches the defeated state (spec §3 "
                   "B4 / manifest map035/ev012/p0)",
             map_constant=MAP_CONST, at=TIMOTHY_APPROACH)
def b4(emu: Emulator) -> None:
    ssa_a = _flag_ssa(35, TIMOTHY_EVENT_ID, "A")
    if emu.flag(ssa_a):
        raise ScenarioError(
            f"B4 precondition failed: {ssa_a} already set before the fight")
    _trigger_trainer(emu, "B4", TIMOTHY_APPROACH, TIMOTHY_FACING)
    party = win_battle(emu)
    _settle_post_battle_script(emu, "B4", ssa_a)
    if not emu.flag(ssa_a):
        shot = emu.screenshot("b4_no_ssa")
        raise ScenarioError(f"B4: {ssa_a} not set after the win ({shot})")
    timothy_const = emu.resolve_constant(TRAINER_TIMOTHY_CONST)
    # `resolve_constant` alone confirms the symbol exists in the built ROM
    # (the fork-index gate this chapter's own TODO says currently blocks
    # transpiling map 35 at all) -- logged, not asserted against the enemy
    # roster read at battle start, since this chapter has no independent
    # source for Timothy's actual mon roster to cross-check against.
    logger.info("B4: TRAINER_TIMOTHY_247 resolves to %d; enemy party at "
                "battle start: %s", timothy_const,
                [(m.species, m.level) for m in party])


# -- B5 ------------------------------------------------------------------

@route2.beat("B5", "Reading the roadblock hint sign shows the Passage Cave "
                   "detour text (spec §3 B5 / manifest map035/ev013/p0)",
             map_constant=MAP_CONST, at=SIGN_ROADBLOCK_APPROACH)
def b5(emu: Emulator) -> None:
    _press_a(emu, "B5", SIGN_ROADBLOCK_APPROACH, SIGN_ROADBLOCK_FACING)
    emu.assert_text_contains("Nowtoch City")
    emu.advance_dialog()
    if emu.field_locked():
        shot = emu.screenshot("b5_stuck")
        raise ScenarioError(f"B5: the sign's dialogue did not close cleanly ({shot})")


# -- B6 ------------------------------------------------------------------

@route2.beat("B6", "The rockslide gate: rocks 14 and 17 refuse to smash "
                   "(Rock Smash unobtainable this chapter) and stay solid "
                   "(spec §3 B6, §3.1 -- exactly these two rows, the only "
                   "attemptable rocks on visit 1)",
             locations=(
                 BeatLocation(MAP_CONST, ROCK_14_XY[0], ROCK_14_XY[1], "rock 14"),
                 BeatLocation(MAP_CONST, ROCK_17_XY[0], ROCK_17_XY[1], "rock 17"),
             ))
def b6(emu: Emulator) -> None:
    for label, xy, approach in (
        ("rock14", ROCK_14_XY, ROCK_14_APPROACH),
        ("rock17", ROCK_17_XY, ROCK_17_APPROACH),
    ):
        _walk_absorbing(emu, "B6", *approach, absorb_wild=True, absorb_trainer=True)
        emu.face("UP")
        before = emu.player_pos()
        if _try_step(emu, "UP"):
            shot = emu.screenshot(f"b6_{label}_not_blocking")
            raise ScenarioError(
                f"B6: stepping toward the rock at {xy} moved the player -- "
                f"the boulder is not blocking movement ({shot})")
        if emu.player_pos() != before:
            shot = emu.screenshot(f"b6_{label}_drifted")
            raise ScenarioError(f"B6: player position changed anyway ({shot})")
        emu.tap("A")
        emu.run(30)
        if emu.field_locked():
            emu.advance_dialog()
        if in_battle(emu):
            shot = emu.screenshot(f"b6_{label}_encounter_fired")
            raise ScenarioError(
                f"B6: a Rock Smash encounter battle started at {xy} despite "
                f"the move being unobtainable this chapter ({shot})")
        if emu.player_pos() != before:
            shot = emu.screenshot(f"b6_{label}_moved_after_a")
            raise ScenarioError(
                f"B6: player position changed after pressing A on the rock "
                f"at {xy} ({shot})")


# -- B7 ------------------------------------------------------------------

@route2.beat("B7", "The cave-mouth tile is reachable up to the approach, "
                   "but the whole event (id 1 'EV001', both pages) is "
                   "dropped this chapter -- its only code-201 warp targets "
                   "unstaged Map036, and `metadata_wiring.classify_event` "
                   "skips the WHOLE event on any out-of-slice warp, not "
                   "just that page. The tile reads as ordinary blocked "
                   "terrain; the real crossing into Passage Cave belongs "
                   "to whichever chapter stages map 36 (CH05) -- mirrors "
                   "route1.py's own B17 for its then-unstaged Kevlar seam",
             map_constant=MAP_CONST, at=CAVE_MOUTH_APPROACH)
def b7(emu: Emulator) -> None:
    _walk_absorbing(emu, "B7", *CAVE_MOUTH_APPROACH,
                    absorb_wild=True, absorb_trainer=True)
    before = emu.player_pos()
    emu.face("UP")
    if _try_step(emu, "UP"):
        shot = emu.screenshot("b7_crossed")
        raise ScenarioError(
            f"B7: stepping UP from {CAVE_MOUTH_APPROACH} toward "
            f"{CAVE_MOUTH_XY} moved the player -- this would cross into "
            f"unstaged Map036 data; the cave mouth should still read "
            f"BLOCKED on this build ({shot})")
    if emu.player_pos() != before:
        shot = emu.screenshot("b7_drifted")
        raise ScenarioError(f"B7: player position changed anyway ({shot})")
    _require_map(emu, "B7", MAP_CONST)


def b8_autorun_deferred(emu: Emulator) -> None:
    """The once-per-visit autorun on Map035 event id 1 page 1
    (`s:tsOff?("A")`, closed by `setTempSwitchOn("A")`).

    DEFERRED, not registered -- see module docstring's B7/B8 section. Event
    id 1 is dropped WHOLE by `metadata_wiring.classify_event` because page 0
    (a different page on the SAME event) carries a code-201 warp to unstaged
    Map036 -- `_event_transfers` scans every page before deciding, so page
    1's autorun has no live subject to test this chapter even though its
    own trigger (switch 22 + the temp-switch guard) has nothing to do with
    the warp. Nothing about the underlying RGSS data changed; restore this
    once CH05 stages map 36 and event id 1 starts compiling again.
    """
    _walk_absorbing(emu, "B8", *CAVE_MOUTH_APPROACH,
                    absorb_wild=True, absorb_trainer=True)
    emu.settle_field()
    if emu.field_locked():
        shot = emu.screenshot("b8_stuck_on_arrival")
        raise ScenarioError(
            f"B8: field still locked after settling on arrival ({shot})")
    before = emu.player_pos()
    _try_step(emu, "DOWN")
    emu.settle_field()
    if emu.field_locked():
        shot = emu.screenshot("b8_refired")
        raise ScenarioError(
            f"B8: the autorun appears to have refired on a second step "
            f"({shot})")
    if emu.player_pos() == before:
        # A refusal to move at all would also read as "still locked" above
        # having already returned -- this is a belt-and-suspenders check
        # that the second step was genuinely a plain, unremarkable move.
        pass


# -- B9 ------------------------------------------------------------------

@route2.beat("B9", "The 'Old entrance to Nowtoch City' sign at (19,34) "
                   "shows its sign-frame text (spec §3.1 B9 / manifest "
                   "map035/ev002/p0) -- not id 8 'Sign' @(19,33), which is "
                   "an empty, cosmetic page",
             map_constant=MAP_CONST, at=SIGN_OLD_ENTRANCE_APPROACH)
def b9(emu: Emulator) -> None:
    _press_a(emu, "B9", SIGN_OLD_ENTRANCE_APPROACH, SIGN_OLD_ENTRANCE_FACING)
    emu.assert_text_contains(SIGN_OLD_ENTRANCE_TEXT)
    emu.advance_dialog()
    if emu.field_locked():
        shot = emu.screenshot("b9_stuck")
        raise ScenarioError(f"B9: the sign's dialogue did not close cleanly ({shot})")


def b10_phone_rematch_deferred(emu: Emulator) -> None:
    """Larrie's phone-rematch offer, `Map035_EV003_Page1`
    ("So you have returned for a rematch?..."), self-switch B set / A clear.

    DEFERRED, not registered -- see module docstring's B10 section for the
    full reasoning. Two independent blockers, either of which alone would
    already defer this:

    1. Reaching the precondition (self-switch B set, A clear) needs a real
       PokeNav/Match-Call phone call (`createPhoneTrainer`/
       `customTrainerBattle` in the source script) -- `playtest/emulator.py`
       has no primitive that drives that menu system at all.
    2. Even granting (1), there is no `Emulator.set_flag`/self-switch-setter
       primitive to force the state directly (`Emulator` exposes `flag`/
       `var`/`set_var`, and nothing that writes a flag) -- unlike
       kevlar.py's B17/N2, which force `VAR_HA_MAGIKARP` via `set_var`
       because that primitive exists.

    Written in the expected shape anyway so a future PokeNav-driving
    primitive (or a `set_flag` addition) can pick this straight up: approach
    Larrie the same way B11 does, expect the rematch offer text rather than
    the plain defeated re-talk.
    """
    _press_a(emu, "B10", LARRIE_APPROACH, LARRIE_FACING)
    emu.assert_text_contains(
        "So you have returned for a rematch? Let me show you my moves!")
    if in_battle(emu):
        win_battle(emu)
    if emu.field_locked():
        emu.advance_dialog()


# -- B11 -----------------------------------------------------------------

@route2.beat("B11", "After B2, Larrie's defeated re-talk shows the caves "
                    "warning (spec §3.1 B11 / manifest map035/ev003/p2)",
             map_constant=MAP_CONST, at=LARRIE_APPROACH)
def b11(emu: Emulator) -> None:
    ssa_a = _flag_ssa(35, LARRIE_EVENT_ID, "A")
    if not emu.flag(ssa_a):
        raise ScenarioError(
            f"B11 precondition failed: {ssa_a} not set -- B2 must run first")
    _press_a(emu, "B11", LARRIE_APPROACH, LARRIE_FACING)
    emu.assert_text_contains(
        "Watch your step! In caves, Pokémon can jump out from anywhere!")
    emu.advance_dialog()
    if emu.field_locked():
        shot = emu.screenshot("b11_stuck")
        raise ScenarioError(f"B11: Larrie's re-talk did not close cleanly ({shot})")


# -- B12 -----------------------------------------------------------------

@route2.beat("B12", "After B3, re-touching the item ball grants no second "
                    "Potion (spec §3.1 B12 / manifest map035/ev009/p1, "
                    "the one-shot assertion for B3)",
             map_constant=MAP_CONST, at=ITEM_BALL_APPROACH)
def b12(emu: Emulator) -> None:
    ssa = _flag_ssa(35, ITEM_BALL_EVENT_ID, "A")
    if not emu.flag(ssa):
        raise ScenarioError(
            f"B12 precondition failed: {ssa} not set -- B3 must run first")
    bag_before = emu.bag_item_quantity(ITEM_BALL_ITEM)
    emu.walk_to(*ITEM_BALL_APPROACH)
    emu.face(ITEM_BALL_FACING)
    emu.tap("A")
    emu.run(30)
    if emu.field_locked():
        emu.advance_dialog()
    bag_after = emu.bag_item_quantity(ITEM_BALL_ITEM)
    if bag_after != bag_before:
        shot = emu.screenshot("b12_regranted")
        raise ScenarioError(
            f"B12: {ITEM_BALL_ITEM} {bag_before}->{bag_after} on a "
            f"re-touch -- the ball re-granted ({shot})")


# -- B13 -----------------------------------------------------------------

@route2.beat("B13", "The Barewl beside Larrie shows its text (spec §3.1 "
                    "B13 / manifest map035/ev011/p0). Only the text is "
                    "asserted -- the emote bubble (`pbCallBub(2)`) and the "
                    "cry SE ('015Cry') have no read primitive on `Emulator` "
                    "(no sprite-overlay or sound-channel getter exists), "
                    "so 2 of the 3 observables the spec names are currently "
                    "unverifiable with this harness",
             map_constant=MAP_CONST, at=BAREWL_APPROACH)
def b13(emu: Emulator) -> None:
    _press_a(emu, "B13", BAREWL_APPROACH, BAREWL_FACING)
    emu.assert_text_contains(BAREWL_TEXT)
    emu.advance_dialog()
    if emu.field_locked():
        shot = emu.screenshot("b13_stuck")
        raise ScenarioError(f"B13: the Barewl's dialogue did not close cleanly ({shot})")


# -- B14 -----------------------------------------------------------------

@route2.beat("B14", "After B4, Timothy's defeated re-talk shows the "
                    "'impossible' line (spec §3.1 B14 / manifest "
                    "map035/ev012/p1)",
             map_constant=MAP_CONST, at=TIMOTHY_APPROACH)
def b14(emu: Emulator) -> None:
    ssa_a = _flag_ssa(35, TIMOTHY_EVENT_ID, "A")
    if not emu.flag(ssa_a):
        raise ScenarioError(
            f"B14 precondition failed: {ssa_a} not set -- B4 must run first")
    _press_a(emu, "B14", TIMOTHY_APPROACH, TIMOTHY_FACING)
    emu.assert_text_contains("Someone tougher than me? Impossible!")
    emu.advance_dialog()
    if emu.field_locked():
        shot = emu.screenshot("b14_stuck")
        raise ScenarioError(f"B14: Timothy's re-talk did not close cleanly ({shot})")


# -- B15 -----------------------------------------------------------------

@route2.beat("B15", "Wild grass south of the rockslide produces a "
                    "land_mons encounter, species/level per "
                    "wild_encounters.json (spec §3.1 B15 -- no manifest "
                    "row; an encounter table is neither an event page nor "
                    "a seam, so the generated manifest can never represent "
                    "it, per the spec's own note)",
             locations=(
                 BeatLocation(MAP_CONST, GRASS_CELL_A[0], GRASS_CELL_A[1], "grass cell A"),
                 BeatLocation(MAP_CONST, GRASS_CELL_B[0], GRASS_CELL_B[1], "grass cell B"),
             ))
def b15(emu: Emulator) -> None:
    # Adapted from route1.py's B4, the corpus's only existing wild-encounter
    # beat -- see module docstring for why the two grass-cell coordinates
    # themselves are an unverified guess, not decoded tileset data.
    _walk_absorbing(emu, "B15", *GRASS_CELL_A,
                    absorb_wild=False, absorb_trainer=True)
    max_attempts = 80  # rate 25 -- P(80 misses) < 1e-8, same bound route1.py used
    for _ in range(max_attempts):
        if in_battle(emu):
            break
        target = GRASS_CELL_B if emu.player_pos() == GRASS_CELL_A else GRASS_CELL_A
        _walk_absorbing(emu, "B15", *target,
                        absorb_wild=False, absorb_trainer=True)
    if not in_battle(emu):
        shot = emu.screenshot("b15_no_encounter")
        raise ScenarioError(
            f"B15: no wild encounter after {max_attempts} grass steps at "
            f"{GRASS_CELL_A}/{GRASS_CELL_B} -- either land_mons is not "
            f"wired, or (see module docstring) these coordinates are not "
            f"actually tall grass on the real map ({shot})")
    if emu.is_trainer_battle():
        shot = emu.screenshot("b15_unexpected_trainer_battle")
        raise ScenarioError(
            f"B15: in a trainer battle after the grass walk -- expected "
            f"the wild-encounter objective, not incidental trainer traffic "
            f"({shot})")

    species_ids = {emu.resolve_constant(name) for name in LAND_MONS_SPECIES}
    party = read_enemy_party(emu)
    mon = party[0]
    if mon.species not in species_ids:
        shot = emu.screenshot("b15_wrong_species")
        raise ScenarioError(
            f"B15: encountered species id {mon.species}, expected one of "
            f"{sorted(species_ids)} ({', '.join(LAND_MONS_SPECIES)}) "
            f"({shot})")
    if not (LAND_MONS_MIN_LEVEL <= mon.level <= LAND_MONS_MAX_LEVEL):
        shot = emu.screenshot("b15_wrong_level")
        raise ScenarioError(
            f"B15: encountered level {mon.level}, expected "
            f"{LAND_MONS_MIN_LEVEL}-{LAND_MONS_MAX_LEVEL} per land_mons "
            f"({shot})")

    win_battle(emu)
    if in_battle(emu):
        shot = emu.screenshot("b15_still_in_battle")
        raise ScenarioError(f"B15: still in battle after win_battle() ({shot})")


# -- deferred beats -----------------------------------------------------------
#
# Written, reviewed, deliberately NOT registered. Same convention as
# kevlar.py's `DEFERRED_BEATS`: kept as ready-made regression tests for
# whichever future chapter/patch closes the gap.

DEFERRED_BEATS = (
    ("B8", "Map035 EV001 page 1's once-per-visit autorun -- dropped whole "
          "because EV001's OTHER page carries an out-of-slice warp; "
          "restore once CH05 stages Map036", b8_autorun_deferred),
    ("B10", "Larrie's phone-rematch offer -- needs a PokeNav-driving "
           "primitive (none exists) or an Emulator.set_flag primitive "
           "(none exists) to reach the self-switch B/A precondition",
     b10_phone_rematch_deferred),
)

# -- symbol lint surface ------------------------------------------------------
MAP_CONSTANTS: tuple[str, ...] = ("MAP_KEVLAR_TOWN", MAP_CONST)

FLAG_CONSTANTS: tuple[str, ...] = (
    _flag_ssa(35, LARRIE_EVENT_ID, "A"),
    _flag_ssa(35, LARRIE_EVENT_ID, "B"),
    _flag_ssa(35, ITEM_BALL_EVENT_ID, "A"),
    _flag_ssa(35, TIMOTHY_EVENT_ID, "A"),
)

SPECIES_CONSTANTS: tuple[str, ...] = LAND_MONS_SPECIES

ITEM_CONSTANTS: tuple[str, ...] = (ITEM_BALL_ITEM,)

TRAINER_CONSTANTS: tuple[str, ...] = (TRAINER_TIMOTHY_CONST,)

ALL_CONSTANTS: tuple[str, ...] = (
    MAP_CONSTANTS + FLAG_CONSTANTS + SPECIES_CONSTANTS + ITEM_CONSTANTS
    + TRAINER_CONSTANTS
)

CHAPTER = route2.build()
