"""`beat_gen/never_fires.py`: touch pages the walk can't step on while they
are live (guard rows that push the player off, arrival-scene displacement).

The fixture is the lab guard in miniature: an exit mat (2,8) whose page 0 is
its refusal until variable 1 flips it to page 1; a guard event whose coord
row y=5 pushes the player up; an arrival autorun that carries the player from
the door-side landing (2,7) up past that row. Rows come from
`story_state.extract.extract_map`, the production extraction.
"""
from __future__ import annotations

import pytest

from rpg2gba.beat_gen.never_fires import (
    MapFacts,
    coord_cells_by_event,
    never_fires_proof,
)
from rpg2gba.beat_gen.page_sim import Firing, run_page
from rpg2gba.story_state.extract import extract_map
from rpg2gba.traversal.graph import MapGraph

MAP = 7
_NONE = {"switch1_valid": False, "switch2_valid": False, "variable_valid": False,
         "self_switch_valid": False}
_VAR1 = {**_NONE, "variable_valid": True, "variable_id": 1, "variable_value": 1}
_BLANK = {"code": 0, "indent": 0, "parameters": []}


def _route(steps: list[int], target: int = -1) -> list[dict]:
    """A Set Move Route (with its 509 continuation lines) and a wait."""
    moves = [{"code": c, "parameters": []} for c in steps]
    return [
        {"code": 209, "indent": 0, "parameters": [target, {"list": moves + [{"code": 0}]}]},
        *({"code": 509, "indent": 0, "parameters": [m]} for m in moves),
        {"code": 210, "indent": 0, "parameters": []},
    ]


def _page(trigger: int, condition: dict, commands: list[dict]) -> dict:
    return {"trigger": trigger, "condition": condition, "list": [*commands, _BLANK]}


_TEXT = [{"code": 101, "indent": 0, "parameters": ["hey"]}]
_UP = 4                                                    # RMXP move code: one tile up


def _facts(*, pushes: bool = True, scene: bool = True, wide: int = 5) -> MapFacts:
    guard_cmds = _route([_UP]) if pushes else list(_TEXT)
    events = [
        {"id": 1, "pages": [_page(1, _NONE, list(_TEXT)), _page(1, _VAR1, [])]},
        {"id": 2, "pages": [_page(2, _NONE, guard_cmds), _page(0, _VAR1, [])]},
    ]
    if scene:
        events.append({"id": 3, "pages": [_page(3, _NONE, _route([_UP, _UP, _UP]))]})
    data = {"events": events}
    states = extract_map(MAP, data, common_events=[], switch_labels={})
    pages = {f"map{MAP:03d}/ev{e['id']:03d}/p{i}": p
             for e in events for i, p in enumerate(e["pages"])}
    cells = {1: frozenset({(2, 8)}), 2: frozenset({(x, 5) for x in range(wide)})}
    graph = MapGraph(map_id=MAP, width=5, height=10, tileset_id=0,
                     blocked={(x, y): False for x in range(5) for y in range(10)})
    return MapFacts(
        map_id=MAP, coord_cells=cells, states=states, page_for=pages.__getitem__,
        event_cell=lambda rid: (2, 8), graph=graph, blocked=frozenset(),
        arrivals=((2, 7),))


REFUSAL = f"map{MAP:03d}/ev001/p0"


def test_guard_row_and_arrival_scene_make_the_refusal_never_fire():
    proof = never_fires_proof(REFUSAL, _facts())
    assert proof is not None
    # The proof names the tile, the arrival and where the scene leaves the player,
    # the guard row, and the page that supersedes it.
    assert "(2, 8)" in proof
    assert "arrival (2, 7) -> start (2, 4)" in proof
    assert "ev002 pushes the player off row y=5" in proof
    assert "map007/ev001/p1 supersedes it once variable 1 >= 1" in proof


def test_tile_reachable_when_the_guard_does_not_push():
    # The guard row only talks: the player walks through it to the exit.
    assert never_fires_proof(REFUSAL, _facts(pushes=False)) is None


def test_tile_reachable_without_an_arrival_scene():
    # No autorun: the player lands beside the exit and can step onto it.
    assert never_fires_proof(REFUSAL, _facts(scene=False)) is None


def test_tile_reachable_around_a_guard_row_with_a_gap():
    # Row y=5 stops short of x=4: the player walks around the guard.
    assert never_fires_proof(REFUSAL, _facts(wide=4)) is None


def test_a_page_that_is_not_a_touch_page_is_not_judged():
    assert never_fires_proof(f"map{MAP:03d}/ev002/p1", _facts()) is None


def test_the_guard_itself_fires():
    # Its own trigger row is stepped on from the arrival side of the map.
    assert never_fires_proof(f"map{MAP:03d}/ev002/p0", _facts()) is None


def test_scene_displacement_is_read_from_the_page():
    facts = _facts()
    page = facts.page_for(f"map{MAP:03d}/ev003/p0")
    run = run_page(f"map{MAP:03d}/ev003/p0", page, facts.states, {},
                   Firing(cell=(2, 7), event_cell=(0, 0)))
    assert run.cell == (2, 4)
    assert run.cell_exact is True
    assert run.path == ((2, 6), (2, 5), (2, 4))


def test_an_undecided_branch_holding_a_player_move_makes_the_cell_inexact():
    page = _page(3, _NONE, [
        {"code": 102, "indent": 0, "parameters": [["Yes", "No"], 1]},
        {"code": 402, "indent": 0, "parameters": [0, "Yes"]},
        *(dict(c, indent=1) for c in _route([_UP])),
        _BLANK,
        {"code": 402, "indent": 0, "parameters": [1, "No"]},
        _BLANK,
        {"code": 404, "indent": 0, "parameters": []},
    ])
    data = {"events": [{"id": 1, "pages": [page]}]}
    states = extract_map(MAP, data, common_events=[], switch_labels={})
    run = run_page(f"map{MAP:03d}/ev001/p0", page, states, {}, Firing(cell=(2, 7), event_cell=None))
    assert run.cell_exact is False


def test_coord_events_are_attributed_by_their_dispatch_script():
    cells = coord_cells_by_event(50, [
        {"type": "trigger", "x": 11, "y": 16, "script": "Map050_EV002_Dispatch"},
        {"type": "trigger", "x": 12, "y": 16, "script": "Map050_EV002_Dispatch"},
        {"type": "trigger", "x": 14, "y": 19, "script": "Map050_EV001_Dispatch"},
    ])
    assert cells == {2: frozenset({(11, 16), (12, 16)}), 1: frozenset({(14, 19)})}


def test_a_coord_event_it_cannot_attribute_fails_loud():
    with pytest.raises(ValueError, match="not a"):
        coord_cells_by_event(50, [{"type": "trigger", "x": 1, "y": 1, "script": "Custom"}])
    with pytest.raises(ValueError, match="not a"):
        coord_cells_by_event(50, [{"type": "trigger", "x": 1, "y": 1,
                                   "script": "Map051_EV002_Dispatch"}])
