"""`beat_gen/guard_reach.py`: approach cells the player can't reach while a
coord guard is live (the lab's signs, 2026-09-29).

Fixture, the lab guard in miniature: a guard (ev002) whose coord row y=5
pushes the player up until variable 1 flips it to page 1; an arrival autorun
(ev003, off once variable 1 is set) carrying the player from the landing
(2,7) to (2,4), north of the row; a talkable event (ev004, at (2,3)) that
writes variable 1 -- the starter. Rows come from `story_state.extract`.
"""
from __future__ import annotations

import logging

import pytest

from rpg2gba.beat_gen.guard_reach import (
    GuardOrderError,
    GuardReach,
    GuardWait,
    apply_guard_reach,
    check_guard_order,
    guard_enabled_by,
    guard_reaches,
)
from rpg2gba.beat_gen.never_fires import MapFacts
from rpg2gba.chapter_manifest.schema import parse_row_id
from rpg2gba.routing.locations import ApproachCandidate, BeatLocationRecord
from rpg2gba.routing.solver import _derive_story_precedence
from rpg2gba.story_state.extract import extract_map
from rpg2gba.story_state.state import Variable
from rpg2gba.traversal.graph import MapGraph

MAP = 7
_NONE = {"switch1_valid": False, "switch2_valid": False, "variable_valid": False,
         "self_switch_valid": False}
_VAR1 = {**_NONE, "variable_valid": True, "variable_id": 1, "variable_value": 1}
_BLANK = {"code": 0, "indent": 0, "parameters": []}
_UP = 4
GUARD = f"map{MAP:03d}/ev002/p0"
WRITER = f"map{MAP:03d}/ev004/p0"
SIGN = f"map{MAP:03d}/ev005/p0"


def _route(steps: list[int]) -> list[dict]:
    moves = [{"code": c, "parameters": []} for c in steps]
    return [
        {"code": 209, "indent": 0, "parameters": [-1, {"list": moves + [{"code": 0}]}]},
        *({"code": 509, "indent": 0, "parameters": [m]} for m in moves),
        {"code": 210, "indent": 0, "parameters": []},
    ]


def _page(trigger: int, condition: dict, commands: list[dict]) -> dict:
    return {"trigger": trigger, "condition": condition, "list": [*commands, _BLANK]}


def _facts(*, gap: bool = False, writer: bool = True) -> MapFacts:
    set_var1 = [{"code": 122, "indent": 0, "parameters": [1, 1, 0, 0, 1]}]
    events = [
        {"id": 2, "pages": [_page(2, _NONE, _route([_UP])), _page(0, _VAR1, [])]},
        {"id": 3, "pages": [_page(3, _NONE, _route([_UP, _UP, _UP])), _page(0, _VAR1, [])]},
        {"id": 4, "pages": [_page(0, _NONE, set_var1 if writer else [])]},
        {"id": 5, "pages": [_page(0, _NONE, [])]},
    ]
    data = {"events": events}
    states = extract_map(MAP, data, common_events=[], switch_labels={})
    pages = {f"map{MAP:03d}/ev{e['id']:03d}/p{i}": p
             for e in events for i, p in enumerate(e["pages"])}
    wall = {(x, 5) for x in range(4 if gap else 5)}
    cells = {2: frozenset(wall)}
    at = {4: (2, 3), 5: (2, 8)}
    graph = MapGraph(map_id=MAP, width=5, height=10, tileset_id=0,
                     blocked={(x, y): False for x in range(5) for y in range(10)})
    return MapFacts(
        map_id=MAP, coord_cells=cells, states=states, page_for=pages.__getitem__,
        event_cell=lambda rid: at.get(parse_row_id(rid).event_id), graph=graph,
        blocked=frozenset(at.values()), arrivals=((2, 7),))


def _record(*cells: tuple[int, int], rows: tuple[str, ...] = (SIGN,), beat_id: str = "sign"
            ) -> BeatLocationRecord:
    ap = tuple(ApproachCandidate(x=x, y=y, side=f"s{i}", resolver="") for i, (x, y) in enumerate(cells))
    return BeatLocationRecord(beat_id=beat_id, map_constant="MAP_X", x=2, y=9, resolver="approach_to",
                              rows=rows, candidates=(), approach_candidates=ap)


def _apply(records, facts: MapFacts, *, extra=None, claimed=None):
    """`extra`: {row id: RowState} of claimed rows on other maps."""
    claimed = {WRITER: "starter", SIGN: "sign"} if claimed is None else claimed
    reaches = guard_reaches(facts)
    states = {**facts.states, **(extra or {})}
    return apply_guard_reach(
        records, reaches_for=lambda _m: reaches, map_of=lambda _r: MAP,
        row_state=states.get, group_of_row=claimed)


def test_cells_south_of_the_guard_are_reachable_only_after_it_stops_being_live():
    (reach,) = guard_reaches(_facts())
    assert isinstance(reach, GuardReach) and reach.page == GUARD
    assert reach.wall_cells == {(x, 5) for x in range(5)}
    assert (0, 1) in reach.live_cells and (2, 4) in reach.live_cells   # north of the row
    assert (2, 9) not in reach.live_cells                              # south: cut off
    assert (2, 9) in reach.any_cells                                   # once var 1 is set


def test_a_beat_behind_the_live_guard_waits_for_the_writer():
    records, waits = _apply([_record((2, 9))], _facts())
    assert records[0].approach_candidates[0].y == 9
    assert waits == (GuardWait("sign", GUARD, ((2, 9),), waits[0].wall_cells, (WRITER,)),)
    enabled = guard_enabled_by(waits, {"sign": SIGN})
    assert enabled == {SIGN: ((WRITER,),)}
    edges, any_of = _derive_story_precedence(enabled, {WRITER: "starter", SIGN: "sign"}, kind="guard")
    assert [(e.before, e.after, e.reason) for e in edges] == [
        ("starter", "sign", f"guard:{WRITER}->{SIGN}")]
    assert any_of == ()


def _other_map_rows(var: int, code_params: list[int]) -> dict:
    page = _page(0, _NONE, [{"code": 122, "indent": 0, "parameters": [var, var, *code_params]}])
    return extract_map(9, {"events": [{"id": 1, "pages": [page]}]}, common_events=[],
                       switch_labels={})


def test_several_claimed_writers_become_an_any_of():
    # Another map's row that BUMPS variable 1 (an Adjust, which the story
    # model's killed_by skips) also ends the guard: an any-of.
    other = "map009/ev001/p0"
    claimed = {WRITER: "a", other: "b", SIGN: "sign"}
    _, waits = _apply([_record((2, 9))], _facts(), claimed=claimed,
                      extra=_other_map_rows(1, [1, 0, 1]))
    assert waits[0].writers == (WRITER, other)
    edges, any_of = _derive_story_precedence(
        guard_enabled_by(waits, {"sign": SIGN}), claimed, kind="guard")
    assert edges == () and [(a.after, a.befores, a.reason) for a in any_of] == [
        ("sign", ("a", "b"), f"guard_any:{SIGN}")]


def test_a_row_writing_an_unrelated_variable_is_not_a_writer():
    other = "map009/ev001/p0"
    _, waits = _apply([_record((2, 9))], _facts(),
                      claimed={WRITER: "a", other: "b", SIGN: "sign"},
                      extra=_other_map_rows(2, [0, 0, 1]))
    assert waits[0].writers == (WRITER,)


def test_a_beat_reachable_with_the_guard_live_gets_no_edge():
    records, waits = _apply([_record((0, 1))], _facts())
    assert waits == () and records[0].approach_candidates[0].y == 1


def test_a_gap_in_the_guard_row_leaves_the_south_reachable():
    records, waits = _apply([_record((2, 9))], _facts(gap=True))
    assert waits == ()


def test_some_cells_reachable_restricts_the_candidates_instead_of_an_edge():
    records, waits = _apply([_record((2, 9), (0, 1))], _facts())
    assert waits == ()
    assert [(c.x, c.y) for c in records[0].approach_candidates] == [(0, 1)]


def test_the_guards_own_beat_is_not_held_to_its_wall():
    rec = _record((2, 9), rows=(GUARD,), beat_id="guard")
    _, waits = _apply([rec], _facts(), claimed={WRITER: "starter", GUARD: "guard"})
    assert waits == ()


def test_no_claimed_writer_fails_loud():
    with pytest.raises(GuardOrderError, match=r"sign.*\(2, 9\).*map007/ev002/p0.*no other claimed"):
        _apply([_record((2, 9))], _facts(), claimed={SIGN: "sign"})


def test_the_beats_own_group_being_the_only_writer_fails_loud():
    with pytest.raises(GuardOrderError, match="no other claimed row"):
        _apply([_record((2, 9))], _facts(), claimed={WRITER: "sign", SIGN: "sign"})


def test_a_cell_the_walk_never_reaches_is_warned_not_constrained(caplog):
    # Nobody writes var 1: the south is reachable in no state.
    with caplog.at_level(logging.WARNING):
        _, waits = _apply([_record((2, 9))], _facts(writer=False))
    assert waits == () and "reached in no state" in caplog.text


def test_a_seed_past_the_guard_starts_no_walk():
    seed = {Variable(1): frozenset({1})}
    assert guard_reaches(_facts(), seed=seed) == ()


def test_the_order_check_raises_when_the_writer_comes_later():
    waits = (GuardWait("sign", GUARD, ((2, 9),), frozenset(), (WRITER,)),)
    check_guard_order(waits, ["starter", "sign"], {WRITER: "starter"})
    with pytest.raises(GuardOrderError, match="no ordering puts it after"):
        check_guard_order(waits, ["sign", "starter"], {WRITER: "starter"})
