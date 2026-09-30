"""Tests for the arrival-page path of `rpg2gba.playtest.archetypes.generic`
(ruling 17/18, 2026-09-25): `text_matches`/`shows_in_order`, the drain
lookup (`_arrival_drain`/`_check_arrival_drain`), and what `generic_beat`
declares for an arrival (autorun/parallel) page versus a normal one.
"""
from __future__ import annotations

import importlib.util

import pytest

from rpg2gba.beat_floor.assertion import FloorAssertion, FloorRefusal, RowFloor, make_params
from rpg2gba.playtest.archetypes import declare_assertions, generic
from rpg2gba.playtest.archetypes.generic import (
    Step,
    _arrival_drain,
    _check_arrival_drain,
    shows_in_order,
    text_matches,
)
from rpg2gba.playtest.chapter import ChapterBuilder
from rpg2gba.playtest.errors import ScenarioError

needs_mgba = pytest.mark.skipif(
    importlib.util.find_spec("mgba") is None,
    reason="needs the mgba python bindings to import emulator.py",
)

# A real arrival page from CH02's manifest: map033/ev004/p0, trigger=parallel,
# event_id=4 -- used by the generated module with approach_prefer='arrive@(70,11)'.
ARRIVAL_ROW = "map033/ev004/p0"
ARRIVAL_CHAPTER = "CH02"
ARRIVAL_APPROACH = "arrive@(70,11)"


def _a(kind: str, list_index: int, row: str = ARRIVAL_ROW, **params) -> FloorAssertion:
    return FloorAssertion(row_id=row, kind=kind, list_index=list_index,
                          code=None if list_index < 0 else 101, params=make_params(**params))


def _floor(*assertions: FloorAssertion, refused: bool = False,
          row: str = ARRIVAL_ROW) -> RowFloor:
    refusals = (FloorRefusal(row, "text_unnormalizable", 0, 101, "x"),) if refused else ()
    return RowFloor(row_id=row, trigger="parallel", assertions=frozenset(assertions),
                    refusals=refusals)


def _builder() -> ChapterBuilder:
    return ChapterBuilder("TEST", doc="generic arrival test")


# --- text_matches -----------------------------------------------------------

def test_text_matches_reflowed_line_breaks():
    expected = "Hello there.\\nHow are you?"
    actual = "Hello there. How\\nare you?"
    assert text_matches(expected, actual)


def test_text_matches_a_break_followed_by_a_space_as_one_gap():
    # ROM run 41: Moki Town's sign.
    expected = "Moki Town\\n “Town of Fresh Beginnings”"
    actual = "Moki Town “Town of Fresh Beginnings”"
    assert text_matches(expected, actual)


def test_text_matches_player_wildcard():
    expected = "Hi, {PLAYER}!"
    actual = "Hi, Ash!"
    assert text_matches(expected, actual)


def test_text_matches_pause_code_removed_in_actual():
    expected = "Wait{PAUSE 0x18}for it."
    actual = "Waitfor it."
    assert text_matches(expected, actual)


def test_text_matches_rejects_a_different_line():
    assert not text_matches("Hello there.", "Goodbye now.")


# --- shows_in_order ----------------------------------------------------------

def test_shows_in_order_true_when_lines_appear_in_order():
    assert shows_in_order(["Line one.", "Line two."], ["Line one.", "Line two."])


def test_shows_in_order_false_when_out_of_order():
    assert not shows_in_order(["Line one.", "Line two."], ["Line two.", "Line one."])


def test_shows_in_order_consecutive_duplicate_collapses_to_one_message():
    assert shows_in_order(["Same.", "Same.", "Next."], ["Same.", "Next."])


def test_shows_in_order_false_when_a_line_is_missing():
    assert not shows_in_order(["Line one.", "Line two."], ["Line one."])


# --- _arrival_drain / _check_arrival_drain -----------------------------------

class _FakeConstEmu:
    def __init__(self, drains, consts: dict[str, int]) -> None:
        self.drains = drains
        self._consts = consts

    def resolve_constant(self, name: str) -> int:
        return self._consts[name]


def _text_step(text: str, row: str = ARRIVAL_ROW, index: int = 0) -> Step:
    return Step(row, "text", index, (("index", index), ("text", text)))


def _grant_step(item: str, quantity: int, row: str = ARRIVAL_ROW, index: int = 1) -> Step:
    return Step(row, "item_grant", index, (("item", item), ("quantity", quantity)))


@needs_mgba
def test_arrival_drain_picks_the_newest_matching_drain_on_the_map():
    from rpg2gba.playtest.emulator import Drain

    older = Drain(map_location=(1, 2), messages=("Hi there.",), bag_before={}, bag_after={})
    newer = Drain(map_location=(1, 2), messages=("Hi there.",), bag_before={}, bag_after={})
    emu = _FakeConstEmu([older, newer], {
        "MAP_GROUP(MAP_ROUTE_01)": 1, "MAP_NUM(MAP_ROUTE_01)": 2})
    texts = (_text_step("Hi there."),)
    got = _arrival_drain(emu, "B1", "MAP_ROUTE_01", texts)
    assert got is newer


@needs_mgba
def test_arrival_drain_ignores_a_drain_on_another_map():
    from rpg2gba.playtest.emulator import Drain

    wrong_map = Drain(map_location=(9, 9), messages=("Hi there.",), bag_before={}, bag_after={})
    emu = _FakeConstEmu([wrong_map], {
        "MAP_GROUP(MAP_ROUTE_01)": 1, "MAP_NUM(MAP_ROUTE_01)": 2})
    texts = (_text_step("Hi there."),)
    with pytest.raises(ScenarioError, match="didn't fire"):
        _arrival_drain(emu, "B1", "MAP_ROUTE_01", texts)


@needs_mgba
def test_arrival_drain_raises_when_nothing_matches():
    emu = _FakeConstEmu([], {
        "MAP_GROUP(MAP_ROUTE_01)": 1, "MAP_NUM(MAP_ROUTE_01)": 2})
    with pytest.raises(ScenarioError, match="didn't fire"):
        _arrival_drain(emu, "B1", "MAP_ROUTE_01", (_text_step("Hi there."),))


@needs_mgba
def test_check_arrival_drain_passes_on_correct_bag_delta():
    from rpg2gba.playtest.emulator import Drain

    drain = Drain(map_location=(1, 2), messages=("Here you go!",),
                  bag_before={4: 0}, bag_after={4: 3})
    emu = _FakeConstEmu([drain], {
        "MAP_GROUP(MAP_ROUTE_01)": 1, "MAP_NUM(MAP_ROUTE_01)": 2, "ITEM_POKE_BALL": 4})
    texts = (_text_step("Here you go!"),)
    grants = (_grant_step("POKeBALL", 3),)
    _check_arrival_drain(emu, "B1", "MAP_ROUTE_01", texts, grants, {"POKeBALL": "ITEM_POKE_BALL"})


@needs_mgba
def test_check_arrival_drain_raises_on_a_wrong_delta():
    from rpg2gba.playtest.emulator import Drain

    drain = Drain(map_location=(1, 2), messages=("Here you go!",),
                  bag_before={4: 0}, bag_after={4: 1})
    emu = _FakeConstEmu([drain], {
        "MAP_GROUP(MAP_ROUTE_01)": 1, "MAP_NUM(MAP_ROUTE_01)": 2, "ITEM_POKE_BALL": 4})
    texts = (_text_step("Here you go!"),)
    grants = (_grant_step("POKeBALL", 3),)
    with pytest.raises(ScenarioError, match="added 1 ITEM_POKE_BALL, expected 3"):
        _check_arrival_drain(
            emu, "B1", "MAP_ROUTE_01", texts, grants, {"POKeBALL": "ITEM_POKE_BALL"})


# --- generic_beat registration on an arrival page ---------------------------

def test_arrival_page_with_text_and_item_grant_declares_text_trigger_item_grant():
    floor = _floor(
        _a("trigger", -1, trigger="parallel"),
        _a("text", 0, index=0, text="Here you go!"),
        _a("item_grant", 1, item="POKeBALL", quantity=1),
        _a("completes", -1),
    )
    b = _builder()
    generic.generic_beat(
        b, chapter_id=ARRIVAL_CHAPTER, beat_name="arr1", rows=(ARRIVAL_ROW,),
        floor_lookup=lambda row_id: floor, approach_prefer=ARRIVAL_APPROACH,
    )
    (beat,) = b.build().beats
    assert {a.kind for a in beat.assertions} == {"trigger", "text", "item_grant", "completes"}


def test_arrival_page_with_own_self_switch_write_declares_trigger_only():
    floor = _floor(
        _a("trigger", -1, trigger="parallel"),
        _a("self_switch_write", 0, event_id=4, letter="A", value=True),
        _a("completes", -1),
    )
    b = _builder()
    generic.generic_beat(
        b, chapter_id=ARRIVAL_CHAPTER, beat_name="arr2", rows=(ARRIVAL_ROW,),
        floor_lookup=lambda row_id: floor, approach_prefer=ARRIVAL_APPROACH,
    )
    (beat,) = b.build().beats
    assert {a.kind for a in beat.assertions} == {"trigger", "self_switch_write", "completes"}


def test_arrival_page_with_no_text_and_no_own_self_switch_declares_no_trigger():
    floor = _floor(
        _a("trigger", -1, trigger="parallel"),
        # A self-switch write, but not to the page's OWN event -- doesn't count.
        _a("self_switch_write", 0, event_id=99, letter="A", value=True),
        _a("switch_write", 1, switch_id=12, value=True),
        _a("completes", -1),
    )
    b = _builder()
    generic.generic_beat(
        b, chapter_id=ARRIVAL_CHAPTER, beat_name="arr3", rows=(ARRIVAL_ROW,),
        floor_lookup=lambda row_id: floor, approach_prefer=ARRIVAL_APPROACH,
    )
    (beat,) = b.build().beats
    kinds = {a.kind for a in beat.assertions}
    assert "trigger" not in kinds
    assert kinds == {"self_switch_write", "switch_write", "completes"}


def test_choice_on_an_arrival_page_is_declared_and_its_answers_planned():
    floor = _floor(
        _a("trigger", -1, trigger="parallel"),
        _a("text", 0, index=0, text="Here you go!"),
        _a("choice", 1, options=("Yes", "No")),
        _a("completes", -1),
    )
    b = _builder()
    generic.generic_beat(
        b, chapter_id=ARRIVAL_CHAPTER, beat_name="arr4", rows=(ARRIVAL_ROW,),
        floor_lookup=lambda row_id: floor, approach_prefer=ARRIVAL_APPROACH,
        choice_answers=((1, 0),),
    )
    (beat,) = b.build().beats
    # The crossing that lands here drains the page; it answers the menu with
    # the planned answer (the runner hands `drain_answers` to the emulator).
    assert "choice" in {a.kind for a in beat.assertions}
    assert beat.drain_answers == (beat.locations[0].map_constant, (0,))
