"""Tests for `rpg2gba.playtest.archetypes.generic` (C6 Task 7).

What these can check offline: which kinds the body claims to execute, the
pure step list, and what each registration function REGISTERS (rows,
declared assertions, location). What they can't: whether a step handler
drives the emulator correctly. That is P11's boot gate.

STATUS: implemented, skipped. DELETE the `pytestmark` line to start Task 7.
"""
from __future__ import annotations

import typing

import pytest

from rpg2gba.beat_floor.assertion import (
    AssertionKind,
    FloorAssertion,
    FloorRefusal,
    RowFloor,
    make_params,
)
from rpg2gba.beat_floor.lookup import floor_for_row
from rpg2gba.playtest.archetypes import declare_assertions, generic
from rpg2gba.playtest.chapter import ChapterBuilder

NPC = "map037/ev005/p0"                  # CH05's Revive NPC: no archetype claims it
NPC_ARMS = (f"{NPC}/b0", f"{NPC}/b1")
ROW_LEVEL = {"seam_crossing", "stair_crossing", "blocked_obstacle"}


def _builder() -> ChapterBuilder:
    return ChapterBuilder("TEST", doc="generic template test")


def _a(akind: str, list_index: int, row: str = NPC, **params) -> FloorAssertion:
    return FloorAssertion(row_id=row, kind=akind, list_index=list_index,
                          code=None if list_index < 0 else 101, params=make_params(**params))


def _floor(*assertions: FloorAssertion, refused: bool = False, row: str = NPC) -> RowFloor:
    refusals = (FloorRefusal(row, "text_unnormalizable", 0, 101, "x"),) if refused else ()
    return RowFloor(row_id=row, trigger="action", assertions=frozenset(assertions),
                    refusals=refusals)


# --- the honesty contract -------------------------------------------------------

def test_executed_kinds_cover_the_minimum():
    assert {"trigger", "completes", "text"} <= generic.GENERIC_EXECUTED_KINDS


def test_every_executed_kind_has_a_handler_and_nothing_else_does():
    assert set(generic.STEP_HANDLERS) == generic.GENERIC_EXECUTED_KINDS


def test_executed_kinds_are_real_floor_kinds_and_not_row_level():
    assert generic.GENERIC_EXECUTED_KINDS <= set(typing.get_args(AssertionKind))
    assert not (generic.GENERIC_EXECUTED_KINDS & ROW_LEVEL)


# --- steps_for ------------------------------------------------------------------

def test_steps_trigger_first_completes_last_rest_by_list_index():
    floor = _floor(_a("completes", -1), _a("text", 5, index=1, text="b"),
                   _a("trigger", -1, trigger="action"), _a("text", 2, index=0, text="a"))
    kinds = [(s.kind, s.list_index) for s in generic.steps_for(floor)]
    assert kinds == [("trigger", -1), ("text", 2), ("text", 5), ("completes", -1)]


def test_steps_drop_kinds_the_body_does_not_execute():
    floor = _floor(_a("trigger", -1, trigger="action"), _a("completes", -1),
                   _a("battle", 3, kind="trainer"))
    if "battle" in generic.GENERIC_EXECUTED_KINDS:
        pytest.skip("your generic body executes battles; this case doesn't apply")
    assert "battle" not in {s.kind for s in generic.steps_for(floor)}


def test_steps_refuse_a_refused_floor():
    with pytest.raises(ValueError, match=NPC):
        generic.steps_for(_floor(refused=True))


def test_steps_are_deterministic():
    floor = _floor(_a("trigger", -1, trigger="action"), _a("text", 2, index=0, text="a"),
                   _a("completes", -1))
    assert generic.steps_for(floor) == generic.steps_for(floor)


# --- ChapterBuilder.claimed_rows (you add it) --------------------------------------

def test_builder_reports_claimed_rows():
    b = _builder()
    b.beat("X", "x", map_constant="MAP_PASSAGE_CAVE_2F", at=(1, 1), rows=(NPC,))(lambda emu: None)
    assert b.claimed_rows() == frozenset({NPC})


# --- generic_beat ---------------------------------------------------------------

def test_generic_beat_registers_rows_and_honest_assertions():
    rows = (NPC, *NPC_ARMS)
    b = _builder()
    generic.generic_beat(b, chapter_id="CH05", beat_name="m037e005p0", rows=rows)
    (beat,) = b.build().beats
    assert beat.name == "m037e005p0"
    assert beat.rows == rows
    assert beat.archetype is None
    assert beat.assertions == declare_assertions(
        rows, executed_kinds=generic.GENERIC_EXECUTED_KINDS, template="generic")
    assert beat.locations[0].map_constant == "MAP_PASSAGE_CAVE_2F"


def test_generic_beat_location_is_the_page_approach_cell():
    from rpg2gba.playtest.archetypes import load_chapter_rows
    from rpg2gba.routing.locations import cell_for_row
    (page,) = [r for r in load_chapter_rows("CH05") if r.row_id == NPC]
    cell = cell_for_row(page)
    b = _builder()
    generic.generic_beat(b, chapter_id="CH05", beat_name="n", rows=NPC_ARMS)  # arms only
    (beat,) = b.build().beats
    loc = beat.locations[0]
    assert (loc.x, loc.y) == (cell.x, cell.y)


def test_generic_beat_skip_claimed():
    b = _builder()
    b.beat("X", "x", map_constant="MAP_PASSAGE_CAVE_2F", at=(1, 1),
           rows=(NPC_ARMS[0],))(lambda emu: None)
    generic.generic_beat(b, chapter_id="CH05", beat_name="n", rows=(NPC, *NPC_ARMS),
                         skip_claimed=True)
    beats = b.build().beats
    assert [x.name for x in beats] == ["X", "n"]
    assert beats[1].rows == (NPC, NPC_ARMS[1])


def test_generic_beat_skip_claimed_with_nothing_left_registers_nothing():
    b = _builder()
    b.beat("X", "x", map_constant="MAP_PASSAGE_CAVE_2F", at=(1, 1),
           rows=NPC_ARMS)(lambda emu: None)
    generic.generic_beat(b, chapter_id="CH05", beat_name="n", rows=NPC_ARMS, skip_claimed=True)
    assert [x.name for x in b.build().beats] == ["X"]


def test_generic_beat_refused_floor_fails_loud():
    def lookup(row_id: str) -> RowFloor:
        return _floor(refused=True, row=row_id)

    with pytest.raises(ValueError, match=NPC):
        generic.generic_beat(_builder(), chapter_id="CH05", beat_name="n", rows=(NPC,),
                             floor_lookup=lookup)


# --- obstacle_beat --------------------------------------------------------------

ROCKS = ("map032/ev014/p0", "map032/ev015/p0")


def _rock_lookup(capability: str = "rock_smash"):
    def lookup(row_id: str) -> RowFloor:
        x = 65 if row_id == ROCKS[0] else 66
        return _floor(_a("trigger", -1, row=row_id, trigger="action"),
                      _a("blocked_obstacle", -1, row=row_id, x=x, y=45, capability=capability),
                      row=row_id)
    return lookup


def test_obstacle_beat_declares_every_obstacle():
    b = _builder()
    generic.obstacle_beat(b, chapter_id="CH01", beat_name="m032obstacle_rock_smash",
                          rows=ROCKS, capability="rock_smash", floor_lookup=_rock_lookup())
    (beat,) = b.build().beats
    assert beat.rows == ROCKS
    assert {a.kind for a in beat.assertions} == {"blocked_obstacle"}
    assert {a.row_id for a in beat.assertions} == set(ROCKS)
    assert beat.locations[0].map_constant == "MAP_MOKI_TOWN"


def test_obstacle_beat_capability_mismatch_fails_loud():
    with pytest.raises(ValueError, match="strength"):
        generic.obstacle_beat(_builder(), chapter_id="CH01", beat_name="o", rows=ROCKS,
                              capability="strength", floor_lookup=_rock_lookup())


def test_obstacle_beat_row_without_obstacle_fails_loud():
    def lookup(row_id: str) -> RowFloor:
        return _floor(_a("trigger", -1, row=row_id, trigger="action"), row=row_id)

    with pytest.raises(ValueError, match="map032/ev014/p0"):
        generic.obstacle_beat(_builder(), chapter_id="CH01", beat_name="o", rows=ROCKS,
                              capability="rock_smash", floor_lookup=lookup)


# --- stair_beat / seam_beat (real floors) -----------------------------------------

STAIRS = ("map037/terrain/stairs/11,9", "map037/terrain/stairs/11,10")


def test_stair_beat_declares_stair_crossings():
    b = _builder()
    generic.stair_beat(b, chapter_id="CH05", beat_name="m037stair11x9", rows=STAIRS)
    (beat,) = b.build().beats
    expected = {a for r in STAIRS for a in floor_for_row(r).assertions
                if a.kind == "stair_crossing"}
    assert expected and beat.assertions == frozenset(expected)
    assert beat.locations[0].map_constant == "MAP_PASSAGE_CAVE_2F"


SEAM = "map031/seam/N/map035"


def test_seam_beat_declares_the_crossing():
    b = _builder()
    generic.seam_beat(b, chapter_id="CH03", beat_name="m031seamN035", rows=(SEAM,))
    (beat,) = b.build().beats
    assert {a.kind for a in beat.assertions} == {"seam_crossing"}
    assert beat.rows == (SEAM,)


def test_seam_beat_takes_exactly_one_row():
    with pytest.raises(ValueError):
        generic.seam_beat(_builder(), chapter_id="CH04", beat_name="s",
                          rows=("map035/seam/N/map040", "map035/seam/S/map031"))


# --- item_grant (2026-09-25) ------------------------------------------------


class _BagEmu:
    def __init__(self, qty: int) -> None:
        self.qty = qty

    def bag_item_quantity(self, const: str) -> int:
        return self.qty

    def screenshot(self, name: str) -> str:
        return f"{name}.png"


def test_item_grant_handler_checks_the_bag_total():
    from rpg2gba.playtest.archetypes.generic import STEP_HANDLERS, Step
    from rpg2gba.playtest.errors import ScenarioError

    handler = STEP_HANDLERS["item_grant"]
    floor_params = (("item", "POKeBALL"), ("quantity", 5))
    # A bare floor step is a misuse: the body must add the before-quantity.
    with pytest.raises(ScenarioError, match="after the page completes"):
        handler(_BagEmu(5), "B1", Step("map032/ev009/p2", "item_grant", 160, floor_params))
    checked = Step("map032/ev009/p2", "item_grant", 160,
                   floor_params + (("const", "ITEM_POKE_BALL"), ("expected_total", 5)))
    handler(_BagEmu(5), "B1", checked)
    with pytest.raises(ScenarioError, match="bag holds 0 ITEM_POKE_BALL, expected 5"):
        handler(_BagEmu(0), "B1", checked)


# --- choice (ruling 19) -------------------------------------------------------


class _MenuEmu:
    """A menu already up; each tap decides what the script receives."""

    def __init__(self, *, yesno: bool, results: dict[str, int]) -> None:
        self.symbols = {"gSpecialVar_Result": 0x2000}
        self.result = 0xFF
        self._yesno, self._results, self.taps = yesno, results, []

    def yesno_prompt_up(self) -> bool:
        return self._yesno

    def u16(self, addr: int) -> int:
        return self.result

    def run(self, frames: int) -> None:
        pass

    def tap(self, key: str) -> None:
        self.taps.append(key)
        if key in self._results:
            self.result = self._results[key]

    def resolve_constant(self, name: str) -> int:
        return 127

    def screenshot(self, name: str) -> str:
        return f"{name}.png"


def _choice_step(options, answer):
    from rpg2gba.playtest.archetypes.generic import Step

    return Step("map031/ev014/p0", "choice", 3, (("options", options), ("answer", answer)))


def test_choice_handler_answers_a_yesno_and_reads_it_back():
    from rpg2gba.playtest.archetypes.generic import STEP_HANDLERS

    yes = _MenuEmu(yesno=True, results={"A": 1, "B": 0})
    STEP_HANDLERS["choice"](yes, "B1", _choice_step(("Yes", "No"), 0))
    assert yes.taps == ["A"]
    no = _MenuEmu(yesno=True, results={"A": 1, "B": 0})
    STEP_HANDLERS["choice"](no, "B1", _choice_step(("Yes", "No"), 1))
    assert no.taps == ["B"]


def test_choice_handler_moves_the_cursor_for_a_multichoice():
    from rpg2gba.playtest.archetypes.generic import STEP_HANDLERS

    emu = _MenuEmu(yesno=False, results={"A": 2})
    STEP_HANDLERS["choice"](emu, "B1", _choice_step(("Orchynx", "Raptorch", "Eletux"), 2))
    assert emu.taps == ["DOWN", "DOWN", "A"]


def test_choice_handler_catches_a_wrong_answer_reaching_the_script():
    from rpg2gba.playtest.archetypes.generic import STEP_HANDLERS
    from rpg2gba.playtest.errors import ScenarioError

    emu = _MenuEmu(yesno=True, results={"A": 0})  # YES pressed, script got NO
    with pytest.raises(ScenarioError, match="script received 0, expected 1"):
        STEP_HANDLERS["choice"](emu, "B1", _choice_step(("Yes", "No"), 0))
