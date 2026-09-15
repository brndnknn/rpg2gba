"""Chapter 1 -- Moki Town (`reference/chapters/01-moki.md`).

One `@moki.beat` per row of the doc's beat tables (3.1 positive, 3.2
negative), in the doc's order, with the negative beats interleaved at the
point in the run where they are actually testable (ROM_TEST_DEV Branch B2):
N3 before B7's Yes answer, N2 after B8 (once the player is back out in
Map032 -- physically, that means after B10, not right after B8; see the
module docstring note on N2 below) and before B12.

**Dropped beat (2026-07-27): N1.** The doc's §3.2 row defines it as B2's
"companion" over the same gate, and it was implemented as a second identical
call to `_assert_house1f_exit_blocked` — same tile, same step, same three
assertions. It could not fail unless B2 failed first, so it cost a run's
worth of frames and a contact-sheet tile to restate B2's result. The chapter
doc's N1 row is superseded by this note.

Every `FLAG_*`/`VAR_*`/`MAP_*` symbol is resolved by name through
`Emulator.resolve_constant` / `Emulator.flag` / `Emulator.var` -- never a
hardcoded id (ROM_TEST_DEV E3c). Coordinates are plain ints; those aren't
symbols and walk targets have no name to late-bind to.

Coordinate provenance (so a future re-walk can tell a documented reading
apart from a guess):

- `AUNTIE_INTERACT`, `HOUSE1F_EXIT_APPROACH` -- established pattern already
  used by `scenarios.moki_running_shoes` / read directly from Map049's
  EV002 coordinate-event tile (`output/uranium-build/maps/Map049.json`).
- `FENCE_TRIP_TRIGGER` -- Map032 EV074's own event tile, exact match to the
  doc's `(26,12)`.
- `LAB_DOOR_MOKI_TOWN`, `LAB_EXIT_TRIGGER`, `THEO_HOUSE_DOOR` -- warp/event
  tiles read directly from `engine/data/maps/*/map.json`.
- `BAMBO_INTERACT`, `MACHINE_INTERACT` -- derived, not doc-given. Bambo's
  own script (`Map050_EV005_TestBody`, `output/uranium-build/scripts/
  Map050.pory`) walks him from (14,6) to (15,6) right before "Go ahead and
  take it, {PLAYER}", vacating (14,6) as the approach tile for the Machine
  at (14,5); (14,7) as Bambo's own approach mirrors the same
  south-of-NPC/face-UP convention already established for Auntie. Both
  NPCs also call `faceplayer`, so the approach side doesn't have to match
  their idle facing.
- `THEO_LAB_INTERACT` -- **TODO(coords)**, see below.
- `CEREMONY_APPROACH` -- the doc gives `(17,42)/(16,43)` for the relocated
  B13 trigger; the live map data (`Map032.json` event id 9, "Trainer(6)")
  places the actual coordinate-touch tile at `(16,42)`. Both readings agree
  the crossing is a westward step off `(17,42)`, so that's what's used;
  the one-tile discrepancy against the doc's second coordinate is flagged
  in the chapter test's report, not silently resolved here.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .. import assertions, cells
from ..battle import in_battle, win_battle
from ..chapter import BeatLocation, ChapterBuilder
from ..errors import ScenarioError
from ..scenarios import BOOT_FRAMES

if TYPE_CHECKING:  # runtime import is lazy so the registry works without bindings
    from ..emulator import Emulator

ch01 = ChapterBuilder("CH01", doc="reference/chapters/01-moki.md")

# -- coordinates (see module docstring for provenance) -----------------------

AUNTIE_INTERACT = (4, 5)
HOUSE1F_EXIT_APPROACH = (10, 10)
HOUSE1F_EXIT_DIRECTION = "DOWN"

# The doc's trip tile (26,12) is a WALL in the converted map, and (26,11) —
# its northern approach — is sealed off behind that wall (no route to it from
# anywhere the player can reach; the harness's route planner reports exactly
# that). EV074's RMXP touch trigger is impassable, so the converter relocates
# it to the standable neighbours below: `engine/data/maps/MokiTown/map.json`
# carries `Map032_EV074_Dispatch` on the (26,13)..(26,17) column. Row 17 is
# where the walk up from the house arrives, so the crossing is a westward
# step off (27,17).
FENCE_TRIP_APPROACH = (27, 17)
FENCE_TRIP_DIRECTION = "LEFT"

LAB_DOOR_MOKI_TOWN = (17, 11)
BAMBO_INTERACT = (14, 7)
MACHINE_INTERACT = (14, 6)

# TODO(coords): Theo's own object faces UP (`MOVEMENT_TYPE_FACE_UP`,
# engine/data/maps/MokiTownProfessorLab/map.json), unlike Auntie/Bambo
# (both FACE_DOWN), so the "approach from the south, face UP" convention
# used everywhere else in this chapter isn't backed by the same kind of
# direct script evidence for him. His script does call `faceplayer`
# (Map050_EV020_Page1), so any walkable adjacent tile works mechanically --
# but (13, 9)'s passability was not checked against collision data this
# pass. Confirm on the next live boot-walk; adjust here if wrong.
THEO_LAB_INTERACT = (13, 9)
THEO_LAB_DIRECTION = "UP"

# The lab exit is the gated `coord_event` at (14,19) (`Map050_EV001_Dispatch`,
# VAR_QUEST_LOG >= 1); (14,18) directly above it is the arrival warp you land
# on coming in from town, and it is a door-behaviour tile, so standing there
# is safe — only a held northward walk into it would warp.
LAB_EXIT_TRIGGER = (14, 19)
LAB_EXIT_APPROACH = (14, 18)
LAB_EXIT_DIRECTION = "DOWN"
THEO_HOUSE_DOOR = (56, 42)
# Inside Theo's 1F the doorway column carries BOTH warps back to town — the
# door at (10,11) and the arrival tile at (10,10) directly above it (the
# faithful Uranium "exit below / arrival above" pattern). (10,9) is the
# nearest tile that is not itself a warp, so that's where the walk stops
# before stepping out. Layout: row 11 is solid except (10,11).
THEO_HOUSE_EXIT_APPROACH = (10, 9)

# Same relocation story as the fence trip tile: EV009's RMXP touch tile
# (16,42) is impassable in the converted map, so the coord events land on the
# standable column below it — `MokiTown/map.json` has `Map032_EV009_Dispatch`
# at (16,43), (16,44), (16,45). The crossing is a westward step off (17,43).
CEREMONY_APPROACH = (17, 43)
CEREMONY_DIRECTION = "LEFT"
CEREMONY_ROWS = (43, 45)  # the trigger column's extent, for B14's re-cross

# N4: the three Rock Smash boulders east of the ceremony area, RMXP EV014
# (65,45), EV015 (66,46), EV033 (66,44) -- `Map032.json` events, coordinates
# 1:1 with the converted GBA layout (verified against `Map033.json`'s EV036/
# EV038, whose RMXP xy match the converted map's xy exactly -- the map
# converter does not translate coordinates). Compiled local ids read from
# `engine/data/maps/MokiTown/map.json`'s `object_events` array (1-indexed,
# array position + 1, matching the convention `emulator.object_events()`
# reads `localId` under): EV014 is array index 4 -> local id 5, EV015 is
# index 5 -> local id 6, EV033 is index 10 -> local id 11.
#
# Approach tiles verified with `rpg2gba.traversal.collision`
# (`build_blocked_grid` against `output/uranium-build/maps/Map032.json` +
# `tilesets.json` tileset 22) plus a BFS from `THEO_HOUSE_DOOR` treating all
# three rock cells as solid (object collision, not carried by the terrain
# grid): the three rocks form an L against each other -- EV014 (65,45) west
# of EV033 (66,44) and north of EV015 (66,46) -- and (66,45), the cell
# between all three, is enclosed on 3 sides by rock and unreachable without
# smashing one, the same "target inside the gated pocket" trap
# `ch04.py`'s `ROCK_14_APPROACH` comment documents. Two reachable tiles
# cover all three rocks instead:
#   - (65,44), immediately north of EV014 and west of EV033 -- approach both
#     from the same standing tile, facing DOWN for EV014 and RIGHT for EV033.
#   - (65,46), immediately west of EV015 -- facing RIGHT.
# Both tiles are terrain-unblocked and carry no object event of their own.
_ROCK_NORTH_STAND = cells.raw_cell(
    65, 44, why="BFS-chosen standing tile covering EV014 and EV033 (see above)")
_ROCK_WEST_STAND = cells.raw_cell(
    65, 46, why="BFS-chosen standing tile west of EV015 (see above)")
ROCK_EV014 = (cells.local_id("MAP_MOKI_TOWN", 14),
              cells.event_cell("MAP_MOKI_TOWN", 14), _ROCK_NORTH_STAND, "DOWN")
ROCK_EV033 = (cells.local_id("MAP_MOKI_TOWN", 33),
              cells.event_cell("MAP_MOKI_TOWN", 33), _ROCK_NORTH_STAND, "RIGHT")
ROCK_EV015 = (cells.local_id("MAP_MOKI_TOWN", 15),
              cells.event_cell("MAP_MOKI_TOWN", 15), _ROCK_WEST_STAND, "RIGHT")


# -- small local helpers, built only from the emulator's public surface ------
#
# `_at_map`/`_require_map`/`_try_step`/`_wait_for_map`/`_cross_threshold`/
# `_enter_door` used to be defined here (byte-identical to `ch03.py`'s
# copies, and `ch02.py`'s except for its own `_walk_absorbing` navigation)
# -- promoted to `assertions.py` 2026-08-20 (finding H). Aliased under their
# original names so every call site below is unchanged.
_at_map = assertions.at_map
_require_map = assertions.require_map
_try_step = assertions.try_step
_wait_for_map = assertions.wait_for_map
_cross_threshold = assertions.cross_threshold
_enter_door = assertions.enter_door


def _leave_theo_house(emu: Emulator, beat: str) -> None:
    """Walk out of Theo's 1F into Map032.

    Two warp tiles sit stacked in the doorway (see
    `THEO_HOUSE_EXIT_APPROACH`), and which of them takes the step depends on
    where the PokePod scene left the player, so this steps south until the
    map actually changes rather than naming one of them.
    """
    emu.walk_to(*THEO_HOUSE_EXIT_APPROACH)
    for _ in range(3):
        _try_step(emu, "DOWN")
        if _at_map(emu, "MAP_MOKI_TOWN"):
            break
        emu.run(20)
    _wait_for_map(emu, beat, "MAP_MOKI_TOWN")


def _leave_house1f(emu: Emulator, beat: str) -> None:
    """Walk out Map049's front door into Map032.

    The door at `HOUSE1F_EXIT_APPROACH` + one step DOWN is a gated
    `coord_event` (`Map049_EV002_Dispatch`), not a plain warp: with
    `FLAG_MUM` set by B3 it falls to the transferring page, which fades,
    warps to Map032 (28,31) and fades back. Before B3 the same tile refuses
    — that is what B2 asserts.
    """
    _cross_threshold(emu, beat, HOUSE1F_EXIT_APPROACH,
                     HOUSE1F_EXIT_DIRECTION, "MAP_MOKI_TOWN")


# Promoted to `assertions.py` 2026-08-20 (byte-identical to `ch02.py`'s
# own copy at the time).
_advance_to_battle = assertions.advance_to_battle


def _settle_scenes(emu: Emulator, settle: int = 120,
                   frame_budget: int = 12000) -> None:
    """Advance dialogue until the field controls stay free for `settle` frames.

    `advance_dialog` returns at the *first* release, which is ambiguous right
    after a warp: the arrival fade holds the lock too, so "locked" can mean
    "the fade is still up" and the release can land before the map's
    ON_FRAME autorun has fired at all. Waiting for a quiet stretch instead
    means a beat asserts against the state a scene left behind rather than
    against a gap between two scenes.
    """
    spent = 0
    while spent < frame_budget:
        if emu.field_locked():
            emu.tap("A")  # samples text frames on every frame it runs
            spent += 12
            continue
        quiet = 0
        while quiet < settle and not emu.field_locked():
            emu.run(10)
            quiet += 10
            spent += 10
        if quiet >= settle:
            return
    shot = emu.screenshot("scenes_never_settled")
    raise ScenarioError(
        f"field controls never stayed free for {settle} frames within "
        f"{frame_budget} ({shot})")


# Promoted to `assertions.py` 2026-08-20, unified with `ch03.py`'s
# `_party_has_magikarp` under `assertions.read_party_species` /
# `assertions.party_has_species` -- this slot-0-only read (no SPECIES_NONE
# early return) is kept as its own function there since B8 below relies on
# it being able to return SPECIES_NONE itself.
_player_starter_species = assertions.player_starter_species


def _assert_house1f_exit_blocked(emu: Emulator, beat: str) -> None:
    """B2's body: the exit refuses, and refusing writes nothing.

    Was shared with N1, which the doc defined as B2's "formal negative-beat
    companion, same gate, same assertion" — it called this with identical
    arguments and so proved nothing B2 had not already proved. N1 was dropped
    2026-07-27; the doc's §3.2 row is superseded (see the module docstring).
    """
    if emu.flag("FLAG_SYS_B_DASH") or emu.flag("FLAG_MAP049_EVENT001_SSA"):
        raise ScenarioError(
            f"{beat} precondition failed: Auntie's flags are already set "
            "before the exit attempt")
    emu.walk_to(*HOUSE1F_EXIT_APPROACH)
    _try_step(emu, HOUSE1F_EXIT_DIRECTION)
    if not emu.field_locked():
        shot = emu.screenshot(f"{beat}_no_redirect")
        raise ScenarioError(
            f"{beat}: leaving Map049 before talking to Auntie did not "
            f"trigger the redirect ({shot})")
    emu.advance_dialog("A")
    _require_map(emu, beat, "MAP_MOKI_TOWN_PLAYERS_HOUSE_1F")
    if emu.flag("FLAG_SYS_B_DASH") or emu.flag("FLAG_MAP049_EVENT001_SSA"):
        shot = emu.screenshot(f"{beat}_flags_leaked")
        raise ScenarioError(
            f"{beat}: Auntie's flags became set from the blocked exit "
            f"attempt ({shot})")


# -- B1 ------------------------------------------------------------------

@ch01.beat("B1", "Fresh save spawns in Map049 (Player's House 1F), not Map048")
def b1(emu: Emulator) -> None:
    emu.run(BOOT_FRAMES)
    _require_map(emu, "B1", "MAP_MOKI_TOWN_PLAYERS_HOUSE_1F")
    if emu.flag("FLAG_SYS_B_DASH"):
        raise ScenarioError(
            "B1: FLAG_SYS_B_DASH already set at boot -- stale save state?")


# -- B2 --------------------------------------------------------------------

# `rows=` on the beats below (P8a, REDERIVATION_PLAN.md 13.1) records which
# chapter-manifest rows each beat actually exercises, so the disposition
# generator can join `beat:` instead of a human hand-writing it. Every mapping
# was confirmed against the COMPILED scripts (`engine/data/maps/*/scripts.inc`)
# and each row's page condition in the manifest, not inferred from a beat's
# prose. 17 rows across 12 beats (B13 claims three); RMXP "Page1" is manifest
# `p0`.
#
# B13 also claims `map172/ev002/p0` (2026-09-14 archetype-conformance pass):
# `_leave_theo_house` steps DOWN under directed control through Theo's 1F
# doorway, which is that row's own warp tile (`Map172.json` EV002 @ (10,11),
# the door half of the stacked exit/arrival pair the module docstring
# documents at `THEO_HOUSE_EXIT_APPROACH`) -- a controlled crossing, not an
# incidental arrival, so it meets the warp-page claim bar.
#
# 2026-09-15 pass: per-row `archetype=` mappings (the `{row_id: archetype}`
# form `ChapterBuilder.beat` grew alongside `assertions.assert_arrival_settled`)
# let a mixed-archetype beat tag its rows individually instead of declaring
# none. B4, B10 and B13 each pick up a second row this pass -- the
# `arrival_nudge` autorun tile the warp they perform lands on
# (`map032/ev005/p1`, `map032/ev003/p1`, `map032/ev017/p1` respectively) --
# with a landing assertion (`assertions.assert_arrival_settled(...,
# nudged=True)`, arrival derived via `cells.arrival_cell`) added right after
# each crossing. B13's story row (`map032/ev009/p2`) and B4's other
# row (`map032/ev074/p0`) stay unclaimed by any archetype, same as before.
#
# FIVE BEATS CLAIM NOTHING, and each is a different reason:
#   B1  -- asserts the fresh save spawns in Map049. A boot state is not an
#          event page, a seam or terrain, so no manifest row can represent it.
#   B15 -- the terminal end-of-chapter checkpoint, same category.
#   B6  -- "B5's scene reaches the Yes/No prompt" happens INSIDE
#          `map050/ev005/p0`. RMXP has one page there carrying the intro, the
#          choice and both branches; there is no separate page for "reached
#          the prompt". N3 runs that branch to completion with flag and var
#          assertions, so N3 takes the row and B6 declares nothing rather than
#          double-claiming it.
#   B9  -- same shape. The starter grant and Theo's battle are one script:
#          `map050/ev019/p0` is the only page of that event with any commands
#          (p1 and p2 are command-less, gated on VAR_QUEST_LOG >= 1 and >= 4).
#          B8 claims it; B9 fights the battle the same page runs into.
#   B14 -- re-crossing the ceremony tiles at VAR_QUEST_LOG >= 4. What it
#          proves is that the event-touch DISPATCHER falls through to `end`,
#          which is not the same as exercising a page: `map032/ev009/p3` is
#          the page active at that quest-log value, but it is action-trigger
#          and B14 never presses A, so its text is never reached. The page
#          B14 shows does not re-fire is p2, and B13 already claims that.
#
# Where two beats touch one page, the row goes to the beat that asserts the
# most about it -- the same rule used in ch02.py, and the one `oracle=` will
# want when it lands.


@ch01.beat("B2", "Leaving 1F before talking to Auntie is blocked",
           map_constant="MAP_MOKI_TOWN_PLAYERS_HOUSE_1F",
           at=HOUSE1F_EXIT_APPROACH,
           rows=("map049/ev002/p0",))
def b2(emu: Emulator) -> None:
    _assert_house1f_exit_blocked(emu, "B2")


# -- B3 ----------------------------------------------------------------------

@ch01.beat("B3", "Auntie grants FLAG_SYS_B_DASH; her gift-once flag is set",
           map_constant="MAP_MOKI_TOWN_PLAYERS_HOUSE_1F", at=AUNTIE_INTERACT,
           rows=("map049/ev001/p0",))
def b3(emu: Emulator) -> None:
    emu.walk_to(*AUNTIE_INTERACT)
    emu.face("UP")
    emu.interact()
    emu.advance_dialog()
    if not emu.flag("FLAG_SYS_B_DASH"):
        shot = emu.screenshot("b3_no_dash")
        raise ScenarioError(
            f"B3: FLAG_SYS_B_DASH not set after Auntie's dialogue ({shot})")
    if not emu.flag("FLAG_MAP049_EVENT001_SSA"):
        shot = emu.screenshot("b3_no_ssa")
        raise ScenarioError(
            f"B3: FLAG_MAP049_EVENT001_SSA (gift-once flag) not set ({shot})")


# -- B4 ------------------------------------------------------------------

#: The front door's landing tile in Map032, shared with `map032/ev005`'s
#: arrival-nudge page. Map049 EV002's p1 and p3 both land here, which
#: `arrival_cell` accepts as one answer.
B4_ARRIVAL = cells.arrival_cell(
    "MAP_MOKI_TOWN", from_map="MAP_MOKI_TOWN_PLAYERS_HOUSE_1F", event_id=2)


@ch01.beat("B4", "Crossing Map032's fence-row tile fires Theo's cameo, once",
           map_constant="MAP_MOKI_TOWN", at=FENCE_TRIP_APPROACH,
           rows=("map049/ev002/p1", "map032/ev074/p0", "map032/ev005/p1"),
           archetype={"map049/ev002/p1": "warp", "map032/ev005/p1": "arrival_nudge"})
def b4(emu: Emulator) -> None:
    if emu.flag("FLAG_MAP032_EVENT074_SSA"):
        raise ScenarioError(
            "B4 precondition failed: the trip tile's self-switch is "
            "already set before the walk")
    # The doc's beat table jumps map 49 -> 32 between B3 and B4 without a
    # row of its own for the doorway; B3 leaves the player standing next to
    # Auntie, so B4 owns the crossing.
    _leave_house1f(emu, "B4")
    assertions.assert_arrival_settled(emu, "B4", B4_ARRIVAL, nudged=True)
    emu.walk_to(*FENCE_TRIP_APPROACH)
    _try_step(emu, FENCE_TRIP_DIRECTION)
    if not emu.field_locked():
        shot = emu.screenshot("b4_no_scene")
        raise ScenarioError(
            f"B4: crossing the fence-row tile did not fire Theo's cameo "
            f"scene ({shot})")
    emu.advance_dialog("A")
    if not emu.flag("FLAG_MAP032_EVENT074_SSA"):
        shot = emu.screenshot("b4_ssa_unset")
        raise ScenarioError(
            f"B4: FLAG_MAP032_EVENT074_SSA not set after the cameo scene "
            f"({shot})")


# -- B5 ------------------------------------------------------------------

@ch01.beat("B5", "Entering the lab autoruns Bambo's intro scene",
           map_constant="MAP_MOKI_TOWN", at=LAB_DOOR_MOKI_TOWN,
           rows=("map032/ev003/p0",), archetype="warp")
def b5(emu: Emulator) -> None:
    _enter_door(emu, "B5", LAB_DOOR_MOKI_TOWN, "MAP_MOKI_TOWN_PROFESSOR_LAB")
    if not emu.field_locked():
        shot = emu.screenshot("b5_no_autorun")
        raise ScenarioError(
            f"B5: entering the lab did not autorun Bambo's intro scene "
            f"({shot})")


# -- B6 ------------------------------------------------------------------

@ch01.beat("B6", "B5's scene reaches the aptitude-test Yes/No prompt")
def b6(emu: Emulator) -> None:
    """Drive B5's autorun forward until the offer is actually on screen.

    Until 2026-07-30 this beat ran *zero* frames -- it only asserted the
    field was still locked -- so it proved nothing B5 hadn't, and its contact
    sheet tile was a duplicate of B5's (the prompt is only reached later,
    inside N3's mash). `yesno_prompt_up` makes the prompt observable, so the
    beat can now assert its own description: mash Bambo's dialogue forward
    and stop the moment the yes/no task exists.

    Stopping there is what leaves the choice to N3/B7 -- the answer is still
    made by button, since which option is *highlighted* remains unobservable
    and A always commits the default YES.
    """
    if not emu.field_locked():
        shot = emu.screenshot("b6_scene_ended_early")
        raise ScenarioError(
            f"B6: Bambo's intro scene ended before reaching the aptitude "
            f"test offer ({shot})")
    emu.advance_dialog("A", stop=emu.yesno_prompt_up)
    if not emu.yesno_prompt_up():
        shot = emu.screenshot("b6_no_prompt")
        raise ScenarioError(
            f"B6: Bambo's intro scene released the field controls without "
            f"ever opening the aptitude-test Yes/No prompt ({shot})")
    # The reviewable moment is the prompt itself, which neither automatic
    # rule picks: the beat ends with the box up, so nothing "completed" after
    # it, and the live boundary frame is this same instant only by accident.
    emu.mark_frame()


# -- N3 (before B7's Yes answer, per interleaving instructions) -------------

@ch01.beat("N3", "Answering No at the aptitude-test offer re-offers cleanly",
           rows=("map050/ev005/p0",))
def n3(emu: Emulator) -> None:
    quest_log_before = emu.var("VAR_QUEST_LOG")
    emu.advance_dialog("B")  # B always answers a yesnobox NO (see helper)
    if emu.field_locked():
        shot = emu.screenshot("n3_still_locked")
        raise ScenarioError(
            f"N3: field controls still locked after declining the "
            f"aptitude test ({shot})")
    if not emu.flag("FLAG_MAP050_EVENT005_SSD"):
        shot = emu.screenshot("n3_no_ssd")
        raise ScenarioError(
            f"N3: FLAG_MAP050_EVENT005_SSD not set after declining -- the "
            f"re-offer gate never armed ({shot})")
    quest_log_after = emu.var("VAR_QUEST_LOG")
    if quest_log_after != quest_log_before:
        shot = emu.screenshot("n3_var_leaked")
        raise ScenarioError(
            f"N3: VAR_QUEST_LOG changed from {quest_log_before} to "
            f"{quest_log_after} after declining the test ({shot})")


# -- B7 ------------------------------------------------------------------

@ch01.beat("B7", "Re-offer + Yes answer plays the 4-question quiz",
           map_constant="MAP_MOKI_TOWN_PROFESSOR_LAB", at=BAMBO_INTERACT,
           rows=("map050/ev005/p2",))
def b7(emu: Emulator) -> None:
    emu.walk_to(*BAMBO_INTERACT)
    emu.face("UP")
    emu.interact()
    emu.advance_dialog("A")  # commits YES, then rides the quiz out
    # The Yes arm sets SSB and clears SSD, which re-arms the OnFrame gate;
    # it re-fires into Map050_EV005_TestBody *without releasing the field
    # controls in between*, so the single advance_dialog above carries the
    # player through the offer AND the four questions (A commits the
    # highlighted option at each dynmultichoice). There is therefore no
    # moment where "the quiz is running" is observable as a lock — the
    # evidence that it ran is the latch the quiz sets on its way out.
    if not emu.flag("FLAG_MAP050_EVENT005_SSB"):
        shot = emu.screenshot("b7_quiz_did_not_start")
        raise ScenarioError(
            f"B7: answering Yes did not arm the quiz -- "
            f"FLAG_MAP050_EVENT005_SSB is unset ({shot})")
    if emu.field_locked():
        emu.advance_dialog("A")
    if not emu.flag("FLAG_MAP050_EVENT005_SSC"):
        shot = emu.screenshot("b7_quiz_incomplete")
        raise ScenarioError(
            f"B7: FLAG_MAP050_EVENT005_SSC not set after the quiz "
            f"resolved ({shot})")
    quest_log = emu.var("VAR_QUEST_LOG")
    if quest_log != 0:
        shot = emu.screenshot("b7_unexpected_quest_log")
        raise ScenarioError(
            f"B7: VAR_QUEST_LOG reads {quest_log} after the quiz, expected "
            f"0 -- the starter grant (B8) belongs to the Machine event, "
            f"not the quiz ({shot})")


# -- B8 ------------------------------------------------------------------

@ch01.beat("B8", "Interacting with the Machine grants the starter",
           map_constant="MAP_MOKI_TOWN_PROFESSOR_LAB", at=MACHINE_INTERACT,
           rows=("map050/ev019/p0",), archetype="trainer")
def b8(emu: Emulator) -> None:
    emu.walk_to(*MACHINE_INTERACT)
    emu.face("UP")
    emu.interact()
    _advance_to_battle(emu)
    # The doc's B8 row credits this beat with `VAR_QUEST_LOG` 0->1. The write
    # is real but lands *after* the battle, in the scene's tail
    # (`addvar VAR_QUEST_LOG, 1`, `MokiTownProfessorLab/scripts.inc:740`,
    # reached only from the post-battle path), so B9 asserts it. What is true
    # here is the grant itself: `givemon` runs before the battle (:948).
    species = _player_starter_species(emu)
    species_none = emu.resolve_constant("SPECIES_NONE")
    if species == species_none:
        shot = emu.screenshot("b8_no_starter")
        raise ScenarioError(
            f"B8: gPlayerParty slot 0 reads SPECIES_NONE after the "
            f"Machine scene -- starter not placed in party ({shot})")


# -- B9 ------------------------------------------------------------------

@ch01.beat("B9", "The Machine scene runs straight into Theo's trainer battle")
def b9(emu: Emulator) -> None:
    # DOC CORRECTION (2026-07-27): the chapter doc's B9 row says the battle
    # fires when you *talk to Theo* (Map050 event 20). It doesn't, in
    # Uranium's own data or in the conversion: the `pbTrainerBattle` call
    # lives in event **19** ("Machine") — the same script B8 triggers — and
    # runs immediately after the starter grant, with no release of the field
    # controls in between (`trainerbattle_earlyrival` at
    # `MokiTownProfessorLab/scripts.inc:990`, after `givemon` at :948).
    # Event 20's page for `VAR_QUEST_LOG >= 1` is a bare `end`, so an
    # interact there correctly does nothing. B8 therefore stops at the
    # battle boundary and B9 fights it.
    if not in_battle(emu):
        shot = emu.screenshot("b9_no_battle")
        raise ScenarioError(
            f"B9: the Machine scene did not run into Theo's battle ({shot})")
    win_battle(emu)
    if emu.field_locked():
        # win_battle already rides out the post-battle script via its own
        # advance_dialog(), but Theo's own leaving-the-lab line can follow
        # immediately after -- clear it the same way.
        emu.advance_dialog()
    quest_log = emu.var("VAR_QUEST_LOG")
    if quest_log != 1:
        shot = emu.screenshot("b9_quest_log_not_1")
        raise ScenarioError(
            f"B9: VAR_QUEST_LOG reads {quest_log} after the battle and its "
            f"tail, expected 1 ({shot})")
    if not emu.flag("FLAG_RECEIVED_STARTER"):
        shot = emu.screenshot("b9_no_received_starter")
        raise ScenarioError(
            f"B9: FLAG_RECEIVED_STARTER not set after the Machine scene's "
            f"post-battle tail ({shot})")


# -- B10 -----------------------------------------------------------------

#: The lab-exit warp's landing tile in Map032, shared with `map032/ev003`'s
#: arrival-nudge page (the door itself, `map032/ev003/p0`, is B5's row).
B10_ARRIVAL = cells.arrival_cell(
    "MAP_MOKI_TOWN", from_map="MAP_MOKI_TOWN_PROFESSOR_LAB", event_id=1)


@ch01.beat("B10", "The lab exit warp unlocks once VAR_QUEST_LOG >= 1",
           map_constant="MAP_MOKI_TOWN_PROFESSOR_LAB", at=LAB_EXIT_APPROACH,
           rows=("map050/ev001/p1", "map032/ev003/p1"),
           archetype={"map050/ev001/p1": "warp", "map032/ev003/p1": "arrival_nudge"})
def b10(emu: Emulator) -> None:
    quest_log = emu.var("VAR_QUEST_LOG")
    if quest_log < 1:
        raise ScenarioError(
            f"B10 precondition failed: VAR_QUEST_LOG reads {quest_log}, "
            f"expected >= 1")
    _cross_threshold(emu, "B10", LAB_EXIT_APPROACH, LAB_EXIT_DIRECTION,
                     "MAP_MOKI_TOWN")
    assertions.assert_arrival_settled(emu, "B10", B10_ARRIVAL, nudged=True)


# -- N2 (after B8/B10, before B11/B12, per interleaving instructions --
# physically requires being back out in Map032, which only B10 provides) --

@ch01.beat("N2", "Skipping Theo's house: the pre-Theo redirect writes no state",
           map_constant="MAP_MOKI_TOWN", at=CEREMONY_APPROACH,
           rows=("map032/ev009/p1",))
def n2(emu: Emulator) -> None:
    quest_log_before = emu.var("VAR_QUEST_LOG")
    if quest_log_before != 1:
        raise ScenarioError(
            f"N2 precondition failed: VAR_QUEST_LOG reads {quest_log_before}, "
            f"expected exactly 1 (post-B8, pre-B12)")
    emu.walk_to(*CEREMONY_APPROACH)
    _try_step(emu, CEREMONY_DIRECTION)
    if not emu.field_locked():
        shot = emu.screenshot("n2_no_redirect")
        raise ScenarioError(
            f"N2: walking to the ceremony trigger before visiting Theo's "
            f"house did not trigger the professor's redirect ({shot})")
    emu.advance_dialog("A")
    if _at_map(emu, "MAP_MOKI_TOWN_THEOS_HOUSE_1F"):
        shot = emu.screenshot("n2_warped")
        raise ScenarioError(
            f"N2: the redirect should not warp into Theo's house, but "
            f"map_location() now reads Theo's 1F ({shot})")
    quest_log_after = emu.var("VAR_QUEST_LOG")
    if quest_log_after != quest_log_before:
        shot = emu.screenshot("n2_var_leaked")
        raise ScenarioError(
            f"N2: VAR_QUEST_LOG changed from {quest_log_before} to "
            f"{quest_log_after} during the pre-Theo redirect -- the "
            f"redirect page must not write any variable ({shot})")


# -- N4 (after N2, before B11 -- the player is free in Map032 here: N2 ends
# at CEREMONY_APPROACH with no claim on where it leaves the player, and B11
# opens with its own `walk_to(*THEO_HOUSE_DOOR)` from wherever the player
# stands, so nothing downstream inherits this beat's ending position. No
# state this beat touches (VAR_QUEST_LOG, party, flags) overlaps N2's or
# B11's preconditions.) ---------------------------------------------------

@ch01.beat("N4", "Rock Smash is unobtainable this chapter: all three of "
                   "Moki Town's boulders refuse to erase and keep blocking "
                   "movement",
             locations=(
                 BeatLocation("MAP_MOKI_TOWN", ROCK_EV014[1][0], ROCK_EV014[1][1], "boulder EV014"),
                 BeatLocation("MAP_MOKI_TOWN", ROCK_EV033[1][0], ROCK_EV033[1][1], "boulder EV033"),
                 BeatLocation("MAP_MOKI_TOWN", ROCK_EV015[1][0], ROCK_EV015[1][1], "boulder EV015"),
             ))
def n4(emu: Emulator) -> None:
    for label, local_id, rock_xy, approach, facing in (
        ("ev014", *ROCK_EV014),
        ("ev033", *ROCK_EV033),
        ("ev015", *ROCK_EV015),
    ):
        emu.walk_to(*approach)
        before = emu.object_event(local_id)
        if not before.active:
            raise ScenarioError(
                f"N4 precondition failed: rock {label} (local id {local_id}) "
                f"already erased before the attempt")
        emu.face(facing)
        before_pos = emu.player_pos()
        if _try_step(emu, facing):
            shot = emu.screenshot(f"n4_{label}_not_blocking")
            raise ScenarioError(
                f"N4: stepping toward rock {label} at {rock_xy} moved the "
                f"player -- the boulder is not blocking movement ({shot})")
        if emu.player_pos() != before_pos:
            shot = emu.screenshot(f"n4_{label}_position_drifted")
            raise ScenarioError(
                f"N4: player position changed anyway ({shot})")
        emu.tap("A")
        emu.run(30)
        if emu.field_locked():
            emu.advance_dialog()
        if in_battle(emu):
            shot = emu.screenshot(f"n4_{label}_encounter_fired")
            raise ScenarioError(
                f"N4: a Rock Smash encounter battle started at {rock_xy} "
                f"despite the move being unobtainable this chapter ({shot})")
        if emu.player_pos() != before_pos:
            shot = emu.screenshot(f"n4_{label}_moved_after_a")
            raise ScenarioError(
                f"N4: player position changed after pressing A on rock "
                f"{label} at {rock_xy} ({shot})")
        after = emu.object_event(local_id)
        if not after.active:
            shot = emu.screenshot(f"n4_{label}_rock_erased")
            raise ScenarioError(
                f"N4: rock {label} (local id {local_id}) was erased despite "
                f"no Rock Smash in the party ({shot})")


# -- B11 -----------------------------------------------------------------

@ch01.beat("B11", "Theo's house door is always open (the gate is inside)",
           map_constant="MAP_MOKI_TOWN", at=THEO_HOUSE_DOOR,
           rows=("map032/ev017/p0",), archetype="warp")
def b11(emu: Emulator) -> None:
    _enter_door(emu, "B11", THEO_HOUSE_DOOR, "MAP_MOKI_TOWN_THEOS_HOUSE_1F")


# -- B12 -----------------------------------------------------------------

@ch01.beat("B12", "Entering Theo's 1F autoruns the PokePod scene",
           rows=("map172/ev004/p0",))
def b12(emu: Emulator) -> None:
    if not emu.field_locked():
        shot = emu.screenshot("b12_no_autorun")
        raise ScenarioError(
            f"B12: entering Theo's 1F did not autorun the PokePod scene "
            f"({shot})")
    # Not `emu.advance_dialog`: on arrival the lock above may still be B11's
    # warp fade, and the PokePod autorun fires a few frames later — the
    # first release is not the end of the scene. See `_settle_scenes`.
    _settle_scenes(emu)
    quest_log = emu.var("VAR_QUEST_LOG")
    if quest_log != 2:
        shot = emu.screenshot("b12_quest_log_not_2")
        raise ScenarioError(
            f"B12: VAR_QUEST_LOG reads {quest_log} after the PokePod "
            f"scene, expected 2 ({shot})")
    # DOC CORRECTION (2026-07-27): the doc's B12 row also expects
    # `FLAG_MAP172_EVENT004_SSA`. That self-switch is not part of this path.
    # In Uranium's own data (`output/uranium-build/maps/Map172.json`, event 4)
    # page 0 — the path taken after *winning* the rival battle — ends with a
    # single control-variable command (`code 122`, var 101 -> 2) and no
    # control-self-switch; the `code 123` A-write lives on page 2, the
    # lost-the-battle variant that ends in a warp. The conversion mirrors
    # that exactly (`MokiTownTheo172/scripts.inc:238` vs `:735`), so the
    # once-only guard on this path is `VAR_QUEST_LOG >= 2` (the dispatcher's
    # own gate), asserted above.


# -- B13 -----------------------------------------------------------------

#: Where `_leave_theo_house`'s crossing lands in Map032 -- the same tile as
#: `THEO_HOUSE_DOOR`, shared with `map032/ev017`'s arrival-nudge page (the
#: door itself, `map032/ev017/p0`, is B11's row).
B13_ARRIVAL = cells.arrival_cell(
    "MAP_MOKI_TOWN", from_map="MAP_MOKI_TOWN_THEOS_HOUSE_1F", event_id=2)


@ch01.beat("B13", "Crossing the west-exit tiles plays the catch ceremony",
           map_constant="MAP_MOKI_TOWN", at=CEREMONY_APPROACH,
           rows=("map032/ev009/p2", "map172/ev002/p0", "map032/ev017/p1"),
           archetype={"map172/ev002/p0": "warp", "map032/ev017/p1": "arrival_nudge"})
def b13(emu: Emulator) -> None:
    quest_log_before = emu.var("VAR_QUEST_LOG")
    if quest_log_before < 2:
        raise ScenarioError(
            f"B13 precondition failed: VAR_QUEST_LOG reads "
            f"{quest_log_before}, expected >= 2")
    # B12 ends inside Theo's 1F; the ceremony trigger is out in Map032, and
    # the doc's beat table changes map between the rows without a row of its
    # own, so B13 owns the crossing (same shape as B4's).
    _leave_theo_house(emu, "B13")
    assertions.assert_arrival_settled(emu, "B13", B13_ARRIVAL, nudged=True)
    emu.walk_to(*CEREMONY_APPROACH)
    _try_step(emu, CEREMONY_DIRECTION)
    if not emu.field_locked():
        shot = emu.screenshot("b13_no_ceremony")
        raise ScenarioError(
            f"B13: crossing the west-exit tiles did not start the catch "
            f"ceremony ({shot})")
    emu.advance_dialog("A")
    quest_log_after = emu.var("VAR_QUEST_LOG")
    if quest_log_after != 4:
        shot = emu.screenshot("b13_quest_log_not_4")
        raise ScenarioError(
            f"B13: VAR_QUEST_LOG reads {quest_log_after} after the "
            f"ceremony, expected 4 ({shot})")


# -- B14 -----------------------------------------------------------------

@ch01.beat("B14", "Re-crossing the ceremony tiles does not refire the scene",
           map_constant="MAP_MOKI_TOWN", at=CEREMONY_APPROACH)
def b14(emu: Emulator) -> None:
    quest_log_before = emu.var("VAR_QUEST_LOG")
    if quest_log_before != 4:
        raise ScenarioError(
            f"B14 precondition failed: VAR_QUEST_LOG reads "
            f"{quest_log_before}, expected exactly 4")
    # B13's ceremony leaves the player standing *on* the trigger column
    # ((16,43)-(16,45)), so "re-cross" is a step off it and straight back —
    # walking to the fixed approach tile would path through the column on
    # the way there and test the crossing from the wrong side.
    _, py = emu.player_pos()
    row = py if CEREMONY_ROWS[0] <= py <= CEREMONY_ROWS[1] else CEREMONY_APPROACH[1]
    emu.walk_to(CEREMONY_APPROACH[0], row)
    _try_step(emu, CEREMONY_DIRECTION)
    if emu.field_locked():
        shot = emu.screenshot("b14_refired")
        raise ScenarioError(
            f"B14: re-crossing the ceremony tiles re-locked field controls "
            f"-- the post-ceremony page should be a no-op ({shot})")
    quest_log_after = emu.var("VAR_QUEST_LOG")
    if quest_log_after != quest_log_before:
        shot = emu.screenshot("b14_var_changed")
        raise ScenarioError(
            f"B14: VAR_QUEST_LOG changed from {quest_log_before} to "
            f"{quest_log_after} on re-crossing ({shot})")


# -- B15 -----------------------------------------------------------------

@ch01.beat("B15", "End of chapter 1: terminal state persists (Route 01 is out of scope)")
def b15(emu: Emulator) -> None:
    # The doc scopes the actual walk out west as out of chapter bounds, and
    # MokiTown's `connections` are unset in the live map data (`engine/data/
    # maps/MokiTown/map.json`) -- there's no built westward destination to
    # walk to yet. This beat is a deliberate terminal checkpoint instead of
    # a real walk: it confirms the chapter's final story-chain state (set by
    # B13) is still intact at the boundary this chapter's coverage ends at.
    quest_log = emu.var("VAR_QUEST_LOG")
    if quest_log != 4:
        shot = emu.screenshot("b15_quest_log_drifted")
        raise ScenarioError(
            f"B15: VAR_QUEST_LOG reads {quest_log} at chapter end, "
            f"expected 4 to still hold from B13 ({shot})")


CHAPTER = ch01.build()
