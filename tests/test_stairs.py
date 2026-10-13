"""Tests for the diagonal-stair event detector."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.tileset_converter.stairs import (
    StairSide,
    detect_stair_cells,
    stair_cell_sides,
    stair_event_ids,
)

_REAL_MAP033 = Path("/home/b/repos/rpg2gba/output/uranium-build/maps/Map033.json")


def _branch_command(indent: int = 0) -> dict:
    """The code-111 'character direction, player' conditional branch."""
    return {"code": 111, "indent": indent, "parameters": [6, -1, 6]}


def _move_route_command(
    codes: list[int], *, target: int = -1, code: int = 209, indent: int = 1
) -> dict:
    """A set-move-route command (205 or 209) targeting `target` with `codes`."""
    move_list = [{"code": c, "parameters": []} for c in codes]
    move_list.append({"code": 0, "parameters": []})
    return {
        "code": code,
        "indent": indent,
        "parameters": [
            target,
            {
                "list": move_list,
                "repeat": False,
                "skippable": False,
            },
        ],
    }


def _display_dup(code: int, indent: int = 1) -> dict:
    """A code-509 editor-display duplicate; must be ignored."""
    return {"code": 509, "indent": indent, "parameters": [{"code": code, "parameters": []}]}


def _event(event_id: int, x: int, y: int, page_lists: list[list[dict]]) -> dict:
    return {
        "id": event_id,
        "x": x,
        "y": y,
        "pages": [
            {"trigger": 1, "through": False, "list": commands} for commands in page_lists
        ],
    }


def _map(events: list[dict], map_id: object = "T") -> dict:
    return {"map_id": map_id, "events": events}


def test_right_axis_stair_classifies_right() -> None:
    ev = _event(
        1, 5, 5,
        [[_branch_command(), _move_route_command([6, 7])]],
    )
    cells = detect_stair_cells(_map([ev]))
    assert cells == [type(cells[0])(x=5, y=5, side=StairSide.RIGHT, event_id=1)]


def test_left_axis_stair_classifies_left() -> None:
    ev = _event(
        2, 3, 4,
        [[_branch_command(), _move_route_command([5, 8])]],
    )
    cells = detect_stair_cells(_map([ev]))
    assert len(cells) == 1
    assert cells[0].side == StairSide.LEFT


def test_mixed_axis_raises_value_error() -> None:
    ev = _event(
        3, 1, 1,
        [[_branch_command(), _move_route_command([5, 6])]],  # SW + SE: mixed axes
    )
    with pytest.raises(ValueError, match="mix both stair axes"):
        detect_stair_cells(_map([ev]))


def test_qualifying_event_without_diagonal_code_is_excluded_not_raised() -> None:
    # trigger==1 + 111-shape, but move route only has non-diagonal codes (e.g. jump=39, wait=15)
    ev = _event(
        4, 2, 2,
        [[_branch_command(), _move_route_command([39, 15])]],
    )
    cells = detect_stair_cells(_map([ev]))
    assert cells == []


def test_509_display_duplicates_are_ignored() -> None:
    ev = _event(
        5, 6, 6,
        [[
            _branch_command(),
            _move_route_command([6]),
            _display_dup(6),
            _display_dup(37),
        ]],
    )
    cells = detect_stair_cells(_map([ev]))
    assert len(cells) == 1
    assert cells[0].side == StairSide.RIGHT


def test_move_route_targeting_event_not_player_does_not_qualify() -> None:
    ev = _event(
        6, 7, 7,
        [[_branch_command(), _move_route_command([6, 7], target=0)]],  # targets event 0, not player
    )
    cells = detect_stair_cells(_map([ev]))
    assert cells == []


def _two_way(down: int, up: int) -> list[dict]:
    """A one-step stair page: one route per facing arm, as Uranium writes it."""
    return [_branch_command(), _move_route_command([down]), _move_route_command([up])]


def test_stair_event_ids_and_stair_cell_sides() -> None:
    ev1 = _event(1, 5, 5, [_two_way(6, 7)])
    ev2 = _event(2, 3, 4, [_two_way(5, 8)])
    m = _map([ev1, ev2])

    assert stair_event_ids(m) == {1, 2}
    assert stair_cell_sides(m) == {
        (5, 5): StairSide.RIGHT,
        (3, 4): StairSide.LEFT,
    }


def test_stair_cell_sides_conflicting_side_same_cell_raises() -> None:
    ev1 = _event(1, 5, 5, [_two_way(6, 7)])  # RIGHT
    ev2 = _event(2, 5, 5, [_two_way(5, 8)])  # LEFT, same cell
    with pytest.raises(ValueError, match="conflicting stair"):
        stair_cell_sides(_map([ev1, ev2]))


def test_multi_page_event_merges_move_codes_across_pages() -> None:
    ev = _event(
        7, 8, 8,
        [
            [_branch_command(), _move_route_command([6])],
            [_branch_command(), _move_route_command([7])],
        ],
    )
    cells = detect_stair_cells(_map([ev]))
    assert len(cells) == 1
    assert cells[0].side == StairSide.RIGHT


def test_map033_real_data_x57_run_and_full_event_set() -> None:
    if not _REAL_MAP033.exists():
        pytest.skip(f"{_REAL_MAP033} not found")
    with _REAL_MAP033.open(encoding="utf-8") as f:
        map_json = json.load(f)

    sides = stair_cell_sides(map_json)
    assert sides[(57, 9)] == StairSide.RIGHT  # event 33
    assert sides[(57, 10)] == StairSide.RIGHT  # event 31
    assert sides[(57, 11)] == StairSide.RIGHT  # event 26

    ids = stair_event_ids(map_json)
    assert ids == {26, 31, 33, 47, 48, 66, 69}


# -- multi-step staircases (CH06 walk, 2026-10-13) ---------------------------
#
# The engine redirects ONE diagonal per E/W press; a Uranium stair event pushes
# k. The invariant pinned here: every RMXP crossing (approach -> exit) is
# playable under the engine's own rule over the cells `stair_cell_sides` emits.
# Before `lane_cells`, a 2x2 staircase's lower lane stopped halfway.

_W, _E = (-1, 0), (1, 0)


def _engine_press(cur, press, sides, passable):
    """One E/W press under `GetCollisionAtCoords` + `GetSidewaysStairsCollision`
    (engine/src/event_object_movement.c), RIGHT/LEFT_SIDE behaviors only --
    the converter never emits the TOP/BOTTOM variants. Returns the new cell,
    or `cur` when the step is blocked."""
    nxt = (cur[0] + press[0], cur[1] + press[1])
    cb, nb = sides.get(cur), sides.get(nxt)
    west = press == _W
    diag = None
    if nb is StairSide.LEFT:
        if not (west and cb != nb):
            diag = (-1, 1) if west else (1, -1)
    elif nb is StairSide.RIGHT:
        if not (not west and cb != nb):
            diag = (-1, -1) if west else (1, 1)
    elif cb is StairSide.LEFT:
        if west:
            diag = (-1, 1)
    elif cb is StairSide.RIGHT:
        if not west:
            diag = (1, 1)
    if diag is not None:
        return (cur[0] + diag[0], cur[1] + diag[1])
    return nxt if (nxt in sides or nxt in passable) else cur


def _assert_crossings_playable(map_json, crossings):
    sides = stair_cell_sides(map_json)
    passable = {c for _, ax, ay, ex, ey in crossings for c in ((ax, ay), (ex, ey))}
    for direction, ax, ay, ex, ey in crossings:
        press = _W if direction == "LEFT" else _E
        pos = (ax, ay)
        for _ in range(abs(ex - ax)):
            pos = _engine_press(pos, press, sides, passable)
        assert pos == (ex, ey), f"{direction} from {(ax, ay)} ended at {pos}, RMXP exits at {(ex, ey)}"


def _staircase_2x2(right: bool) -> dict:
    """Map14002's shape: two lanes, each event pushing two diagonals. RIGHT
    rises to the west (NW/SE), LEFT is its mirror (NE/SW)."""
    if right:
        lower, upper, up, down = [(25, 19), (25, 20)], [(24, 17), (24, 18)], 7, 6
    else:
        lower, upper, up, down = [(24, 19), (24, 20)], [(25, 17), (25, 18)], 8, 5
    events = [
        _event(i, x, y, [[_branch_command(), _move_route_command([up, up])]])
        for i, (x, y) in enumerate(lower, start=1)
    ] + [
        _event(i, x, y, [[_branch_command(), _move_route_command([down, down])]])
        for i, (x, y) in enumerate(upper, start=3)
    ]
    return _map(events)


def test_two_step_staircase_fills_in_the_cells_between_lanes() -> None:
    assert set(stair_cell_sides(_staircase_2x2(right=True))) == {
        (25, 20), (25, 19), (24, 18), (24, 17),  # the four events
        (24, 19), (25, 18),                      # the lanes' middle cells
    }


@pytest.mark.parametrize("right", [True, False])
def test_two_step_staircase_every_lane_crosses_fully(right: bool) -> None:
    if right:
        crossings = [("LEFT", 26, 20, 23, 18), ("LEFT", 26, 19, 23, 17),
                     ("RIGHT", 23, 17, 26, 19), ("RIGHT", 23, 18, 26, 20)]
    else:
        crossings = [("RIGHT", 23, 20, 26, 18), ("RIGHT", 23, 19, 26, 17),
                     ("LEFT", 26, 17, 23, 19), ("LEFT", 26, 18, 23, 20)]
    _assert_crossings_playable(_staircase_2x2(right), crossings)


def test_single_step_staircase_gains_no_cells() -> None:
    column = _map([
        _event(1, 57, 9, [_two_way(6, 7)]),
        _event(2, 57, 10, [_two_way(6, 7)]),
        _event(3, 57, 11, [_two_way(6, 7)]),
    ])
    assert set(stair_cell_sides(column)) == {(57, 9), (57, 10), (57, 11)}


def test_route_changing_diagonal_direction_raises() -> None:
    ev = _event(1, 5, 5, [[_branch_command(), _move_route_command([7, 6])]])
    with pytest.raises(ValueError, match="changes diagonal direction"):
        stair_cell_sides(_map([ev]))


@pytest.mark.parametrize("map_id", [33, 37, 14002])
def test_real_staircases_every_rmxp_crossing_is_playable(map_id: int) -> None:
    from rpg2gba.beat_floor.terrain import stair_floors_for_map

    path = _REAL_MAP033.parent / f"Map{map_id:03d}.json"
    if not path.exists():
        pytest.skip(f"{path} not found")
    map_json = json.loads(path.read_text(encoding="utf-8"))
    crossings = [
        tuple(c)
        for floor in stair_floors_for_map(map_id, map_json).values()
        for a in floor.assertions if a.kind == "stair_crossing"
        for c in a.param("crossings")
    ]
    assert crossings
    _assert_crossings_playable(map_json, crossings)
