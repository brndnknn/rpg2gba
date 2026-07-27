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

from ..battle import decrypt_species, in_battle, win_battle
from ..chapter import ChapterBuilder
from ..errors import ScenarioError
from ..scenarios import BOOT_FRAMES

if TYPE_CHECKING:  # runtime import is lazy so the registry works without bindings
    from ..emulator import Emulator

moki = ChapterBuilder("moki", doc="reference/chapters/01-moki.md")

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


# -- small local helpers, built only from the emulator's public surface ------

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
    """Attempt exactly one step, without `walk_to`'s retry-until-arrived
    loop -- for beats where a *successful* step should trigger a
    redirect/refusal (the player gets pushed back) rather than actually
    settling on the target tile. Mirrors `walk_to`'s own per-step budget
    (40 frames to detect a coord change, then a 16-frame settle) so the
    two primitives behave consistently."""
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
    """Wait out a warp (script-driven or door), then assert where we landed.

    `walk_to` is map-blind — it chases coordinates on whatever map the
    player happens to be on — so any beat whose target lives on a different
    map than the previous beat left the player on has to cross the seam
    explicitly and confirm the crossing before it starts pathing again.
    Deliberately does *not* drain the arrival's field lock: several beats
    assert an autorun scene is running the instant they arrive.
    """
    spent = 0
    while spent < frame_budget and not _at_map(emu, map_const):
        emu.run(10)
        spent += 10
    _require_map(emu, beat, map_const)


def _cross_threshold(emu: Emulator, beat: str, approach: tuple[int, int],
                     direction: str, dest_map: str) -> None:
    """Step onto a transition tile from the tile beside it, then confirm the
    map change.

    Never `walk_to` a transition tile directly: `walk_to` aborts loud when a
    step changes the map (that guard is what catches an accidental warp), so
    a deliberate crossing has to be the step *after* the walk, not part of
    it.
    """
    emu.walk_to(*approach)
    _try_step(emu, direction)
    _wait_for_map(emu, beat, dest_map)


def _enter_door(emu: Emulator, beat: str, door: tuple[int, int],
                dest_map: str, hold: int = 48) -> None:
    """Walk into a door warp from the south, holding the D-pad.

    Door warps are not step-on warps. `TryDoorWarp`
    (`engine/src/field_control_avatar.c:1098-1112`) fires only for
    `DIR_NORTH`, and only from the held-direction branch at :227-231 — so
    the player must step onto the door tile *and keep holding UP*. A
    `_try_step`-style tap arrives on the tile and stands there.
    """
    dx, dy = door
    emu.walk_to(dx, dy + 1)
    emu.run(hold, ["UP"])
    _wait_for_map(emu, beat, dest_map)


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


def _advance_to_battle(emu: Emulator, max_taps: int = 1500) -> int:
    """`emu.advance_dialog()`, but stopping if a battle starts.

    A script that ends in a battle gives no field-control release to stop on
    — the A-mash would keep pressing straight through the battle's own menus
    and resolve it by accident. Beats that own a battle need it handed over
    still running, so this stops on either boundary.
    """
    return emu.advance_dialog(max_taps=max_taps, stop=lambda: in_battle(emu))


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


def _player_starter_species(emu: Emulator) -> int:
    """Decode slot 0 of `gPlayerParty` the same way `battle.py` decodes
    `gEnemyParty` -- both are `struct Pokemon`, and the offsets battle.py
    already probes (`off_pkmn_box`, box-substruct fields) are struct-generic,
    not enemy-party-specific."""
    o = emu.offsets
    box_addr = emu.symbols["gPlayerParty"] + o["off_pkmn_box"]
    return decrypt_species(emu, box_addr)


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

@moki.beat("B1", "Fresh save spawns in Map049 (Player's House 1F), not Map048")
def b1(emu: Emulator) -> None:
    emu.run(BOOT_FRAMES)
    _require_map(emu, "B1", "MAP_MOKI_TOWN_PLAYERS_HOUSE_1F")
    if emu.flag("FLAG_SYS_B_DASH"):
        raise ScenarioError(
            "B1: FLAG_SYS_B_DASH already set at boot -- stale save state?")


# -- B2 --------------------------------------------------------------------

@moki.beat("B2", "Leaving 1F before talking to Auntie is blocked")
def b2(emu: Emulator) -> None:
    _assert_house1f_exit_blocked(emu, "B2")


# -- B3 ----------------------------------------------------------------------

@moki.beat("B3", "Auntie grants FLAG_SYS_B_DASH; her gift-once flag is set")
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

@moki.beat("B4", "Crossing Map032's fence-row tile fires Theo's cameo, once")
def b4(emu: Emulator) -> None:
    if emu.flag("FLAG_MAP032_EVENT074_SSA"):
        raise ScenarioError(
            "B4 precondition failed: the trip tile's self-switch is "
            "already set before the walk")
    # The doc's beat table jumps map 49 -> 32 between B3 and B4 without a
    # row of its own for the doorway; B3 leaves the player standing next to
    # Auntie, so B4 owns the crossing.
    _leave_house1f(emu, "B4")
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

@moki.beat("B5", "Entering the lab autoruns Bambo's intro scene")
def b5(emu: Emulator) -> None:
    _enter_door(emu, "B5", LAB_DOOR_MOKI_TOWN, "MAP_MOKI_TOWN_PROFESSOR_LAB")
    if not emu.field_locked():
        shot = emu.screenshot("b5_no_autorun")
        raise ScenarioError(
            f"B5: entering the lab did not autorun Bambo's intro scene "
            f"({shot})")


# -- B6 ------------------------------------------------------------------

@moki.beat("B6", "B5's scene reaches the aptitude-test Yes/No prompt")
def b6(emu: Emulator) -> None:
    # No player action of its own (doc: "none (scripted)") -- this beat
    # just confirms B5's autorun is still in progress (hasn't errored out
    # or released early) on its way into the yes/no prompt that N3/B7
    # resolve. Which *specific* option is highlighted still isn't observable,
    # so the prompt's identity stays confirmed structurally by N3/B7's own
    # asserts. `emu.text_showing()` (added 2026-07-27) could tighten this to
    # "a message box is up right now", but the lock is the safer gate: this
    # beat can land in the gap between two of Bambo's messages, where the
    # scene is healthy and no box is drawn.
    if not emu.field_locked():
        shot = emu.screenshot("b6_scene_ended_early")
        raise ScenarioError(
            f"B6: Bambo's intro scene ended before reaching the aptitude "
            f"test offer ({shot})")


# -- N3 (before B7's Yes answer, per interleaving instructions) -------------

@moki.beat("N3", "Answering No at the aptitude-test offer re-offers cleanly")
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

@moki.beat("B7", "Re-offer + Yes answer plays the 4-question quiz")
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

@moki.beat("B8", "Interacting with the Machine grants the starter")
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

@moki.beat("B9", "The Machine scene runs straight into Theo's trainer battle")
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

@moki.beat("B10", "The lab exit warp unlocks once VAR_QUEST_LOG >= 1")
def b10(emu: Emulator) -> None:
    quest_log = emu.var("VAR_QUEST_LOG")
    if quest_log < 1:
        raise ScenarioError(
            f"B10 precondition failed: VAR_QUEST_LOG reads {quest_log}, "
            f"expected >= 1")
    _cross_threshold(emu, "B10", LAB_EXIT_APPROACH, LAB_EXIT_DIRECTION,
                     "MAP_MOKI_TOWN")


# -- N2 (after B8/B10, before B11/B12, per interleaving instructions --
# physically requires being back out in Map032, which only B10 provides) --

@moki.beat("N2", "Skipping Theo's house: the pre-Theo redirect writes no state")
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
    if _at_map(emu, "MAP_MOKI_TOWN_THEO_172"):
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


# -- B11 -----------------------------------------------------------------

@moki.beat("B11", "Theo's house door is always open (the gate is inside)")
def b11(emu: Emulator) -> None:
    _enter_door(emu, "B11", THEO_HOUSE_DOOR, "MAP_MOKI_TOWN_THEO_172")


# -- B12 -----------------------------------------------------------------

@moki.beat("B12", "Entering Theo's 1F autoruns the PokePod scene")
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

@moki.beat("B13", "Crossing the west-exit tiles plays the catch ceremony")
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

@moki.beat("B14", "Re-crossing the ceremony tiles does not refire the scene")
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

@moki.beat("B15", "End of chapter 1: terminal state persists (Route 01 is out of scope)")
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


CHAPTER = moki.build()
