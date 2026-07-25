"""Chapter 1 -- Moki Town (`reference/chapters/01-moki.md`).

One `@moki.beat` per row of the doc's beat tables (3.1 positive, 3.2
negative), in the doc's order, with the negative beats interleaved at the
point in the run where they are actually testable (ROM_TEST_DEV Branch B2):
N1 before B3, N3 before B7's Yes answer, N2 after B8 (once the player is
back out in Map032 -- physically, that means after B10, not right after B8;
see the module docstring note on N2 below) and before B12.

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

from ..battle import decrypt_species, win_battle
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

FENCE_TRIP_APPROACH = (26, 11)
FENCE_TRIP_DIRECTION = "DOWN"

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

LAB_EXIT_TRIGGER = (14, 19)
THEO_HOUSE_DOOR = (56, 42)

CEREMONY_APPROACH = (17, 42)
CEREMONY_DIRECTION = "LEFT"


# -- small local helpers (chapter.py/emulator.py/battle.py are frozen for
# this task -- everything below is built only from their public surface) ----

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


def _advance_dialog(emu: Emulator, key: str, max_taps: int = 1500) -> int:
    """`Emulator.advance_dialog`, parameterized on which button to press.

    Needed because a couple of beats must make a specific yes/no choice
    partway through an otherwise-uninterrupted locked script, and the
    harness can't peek at "is a yesnobox showing right now" without a new
    memory probe (out of scope -- `emulator.py`/`offsets.py` are frozen for
    this task). Two engine facts make button choice a reliable substitute
    for that peek, so this is still poll-driven, not frame-counted:

    - Ordinary dialogue boxes advance on A or B identically throughout
      pokeemerald (the `JOY_NEW(A_BUTTON | B_BUTTON)` pattern used pervasively
      for text advance), so holding one button for an entire stretch of
      plain msgboxes is safe.
    - `yesnobox` (asm/macros/event.inc): "Pressing B is equivalent to
      answering NO", and every yesnobox this chapter reaches is opened via
      `ScriptMenu_YesNo` -> `DisplayYesNoMenuDefaultYes`
      (engine/src/script_menu.c:584-594), so A commits whatever is
      highlighted, which is always YES for these prompts.

    So "hold A through this stretch" deterministically answers YES at
    whichever yesnobox appears in it, and "hold B through this stretch"
    deterministically answers NO, regardless of exactly how many plain
    messages precede it.
    """
    taps = 0
    while emu.field_locked():
        if taps >= max_taps:
            shot = emu.screenshot("dialog_stuck")
            raise ScenarioError(
                f"dialogue never released field controls ({shot})")
        emu.tap(key)
        taps += 1
    return taps


def _player_starter_species(emu: Emulator) -> int:
    """Decode slot 0 of `gPlayerParty` the same way `battle.py` decodes
    `gEnemyParty` -- both are `struct Pokemon`, and the offsets battle.py
    already probes (`off_pkmn_box`, box-substruct fields) are struct-generic,
    not enemy-party-specific."""
    o = emu.offsets
    box_addr = emu.symbols["gPlayerParty"] + o["off_pkmn_box"]
    return decrypt_species(emu, box_addr)


def _assert_house1f_exit_blocked(emu: Emulator, beat: str) -> None:
    """Shared body for B2 and N1 (doc: N1 is B2's formal negative-beat
    companion, same gate, same assertion)."""
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
    _advance_dialog(emu, "A")
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


# -- N1 (companion to B2; interleaved here per ROM_TEST_DEV Branch B2) ------

@moki.beat("N1", "Repeat of B2's gate: refusal fires, Auntie's flags stay unset")
def n1(emu: Emulator) -> None:
    _assert_house1f_exit_blocked(emu, "N1")


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
    emu.walk_to(*FENCE_TRIP_APPROACH)
    _try_step(emu, FENCE_TRIP_DIRECTION)
    if not emu.field_locked():
        shot = emu.screenshot("b4_no_scene")
        raise ScenarioError(
            f"B4: crossing the fence-row tile did not fire Theo's cameo "
            f"scene ({shot})")
    _advance_dialog(emu, "A")
    if not emu.flag("FLAG_MAP032_EVENT074_SSA"):
        shot = emu.screenshot("b4_ssa_unset")
        raise ScenarioError(
            f"B4: FLAG_MAP032_EVENT074_SSA not set after the cameo scene "
            f"({shot})")


# -- B5 ------------------------------------------------------------------

@moki.beat("B5", "Entering the lab autoruns Bambo's intro scene")
def b5(emu: Emulator) -> None:
    emu.walk_to(*LAB_DOOR_MOKI_TOWN)
    _require_map(emu, "B5", "MAP_MOKI_TOWN_PROFESSOR_LAB")
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
    # resolve. The prompt itself isn't independently observable through
    # the harness's exposed primitives (see `_advance_dialog`'s docstring),
    # so its appearance is confirmed structurally by N3/B7's own asserts.
    if not emu.field_locked():
        shot = emu.screenshot("b6_scene_ended_early")
        raise ScenarioError(
            f"B6: Bambo's intro scene ended before reaching the aptitude "
            f"test offer ({shot})")


# -- N3 (before B7's Yes answer, per interleaving instructions) -------------

@moki.beat("N3", "Answering No at the aptitude-test offer re-offers cleanly")
def n3(emu: Emulator) -> None:
    quest_log_before = emu.var("VAR_QUEST_LOG")
    _advance_dialog(emu, "B")  # B always answers a yesnobox NO (see helper)
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
    _advance_dialog(emu, "A")  # commits YES at the re-offer's yesnobox
    # SSB set -> SSD cleared by the re-offer's Yes branch re-arms the
    # OnFrame autorun gate, which immediately re-fires straight into the
    # quiz body (Map050_EV005_TestBody) without a further interact.
    if not emu.field_locked():
        shot = emu.screenshot("b7_quiz_did_not_start")
        raise ScenarioError(
            f"B7: answering Yes did not lead into the quiz ({shot})")
    _advance_dialog(emu, "A")
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
    _advance_dialog(emu, "A")
    quest_log = emu.var("VAR_QUEST_LOG")
    if quest_log != 1:
        shot = emu.screenshot("b8_quest_log_not_1")
        raise ScenarioError(
            f"B8: VAR_QUEST_LOG reads {quest_log} after the Machine "
            f"scene, expected 1 ({shot})")
    species = _player_starter_species(emu)
    species_none = emu.resolve_constant("SPECIES_NONE")
    if species == species_none:
        shot = emu.screenshot("b8_no_starter")
        raise ScenarioError(
            f"B8: gPlayerParty slot 0 reads SPECIES_NONE after the "
            f"Machine scene -- starter not placed in party ({shot})")


# -- B9 ------------------------------------------------------------------

@moki.beat("B9", "Talking to Theo starts the tutorial trainer battle")
def b9(emu: Emulator) -> None:
    emu.walk_to(*THEO_LAB_INTERACT)
    emu.face(THEO_LAB_DIRECTION)
    emu.interact()
    win_battle(emu)
    if emu.field_locked():
        # win_battle already rides out the post-battle script via its own
        # advance_dialog(), but Theo's own leaving-the-lab line can follow
        # immediately after -- clear it the same way.
        emu.advance_dialog()


# -- B10 -----------------------------------------------------------------

@moki.beat("B10", "The lab exit warp unlocks once VAR_QUEST_LOG >= 1")
def b10(emu: Emulator) -> None:
    quest_log = emu.var("VAR_QUEST_LOG")
    if quest_log < 1:
        raise ScenarioError(
            f"B10 precondition failed: VAR_QUEST_LOG reads {quest_log}, "
            f"expected >= 1")
    emu.walk_to(*LAB_EXIT_TRIGGER)
    _require_map(emu, "B10", "MAP_MOKI_TOWN")


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
    _advance_dialog(emu, "A")
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
    emu.walk_to(*THEO_HOUSE_DOOR)
    _require_map(emu, "B11", "MAP_MOKI_TOWN_THEO_172")


# -- B12 -----------------------------------------------------------------

@moki.beat("B12", "Entering Theo's 1F autoruns the PokePod scene")
def b12(emu: Emulator) -> None:
    if not emu.field_locked():
        shot = emu.screenshot("b12_no_autorun")
        raise ScenarioError(
            f"B12: entering Theo's 1F did not autorun the PokePod scene "
            f"({shot})")
    _advance_dialog(emu, "A")
    quest_log = emu.var("VAR_QUEST_LOG")
    if quest_log != 2:
        shot = emu.screenshot("b12_quest_log_not_2")
        raise ScenarioError(
            f"B12: VAR_QUEST_LOG reads {quest_log} after the PokePod "
            f"scene, expected 2 ({shot})")
    if not emu.flag("FLAG_MAP172_EVENT004_SSA"):
        shot = emu.screenshot("b12_no_ssa")
        raise ScenarioError(
            f"B12: FLAG_MAP172_EVENT004_SSA not set after the PokePod "
            f"scene ({shot})")


# -- B13 -----------------------------------------------------------------

@moki.beat("B13", "Crossing the west-exit tiles plays the catch ceremony")
def b13(emu: Emulator) -> None:
    quest_log_before = emu.var("VAR_QUEST_LOG")
    if quest_log_before < 2:
        raise ScenarioError(
            f"B13 precondition failed: VAR_QUEST_LOG reads "
            f"{quest_log_before}, expected >= 2")
    emu.walk_to(*CEREMONY_APPROACH)
    _try_step(emu, CEREMONY_DIRECTION)
    if not emu.field_locked():
        shot = emu.screenshot("b13_no_ceremony")
        raise ScenarioError(
            f"B13: crossing the west-exit tiles did not start the catch "
            f"ceremony ({shot})")
    _advance_dialog(emu, "A")
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
    emu.walk_to(*CEREMONY_APPROACH)
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
