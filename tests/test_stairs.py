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


def test_stair_event_ids_and_stair_cell_sides() -> None:
    ev1 = _event(1, 5, 5, [[_branch_command(), _move_route_command([6, 7])]])
    ev2 = _event(2, 3, 4, [[_branch_command(), _move_route_command([5, 8])]])
    m = _map([ev1, ev2])

    assert stair_event_ids(m) == {1, 2}
    assert stair_cell_sides(m) == {
        (5, 5): StairSide.RIGHT,
        (3, 4): StairSide.LEFT,
    }


def test_stair_cell_sides_conflicting_side_same_cell_raises() -> None:
    ev1 = _event(1, 5, 5, [[_branch_command(), _move_route_command([6, 7])]])  # RIGHT
    ev2 = _event(2, 5, 5, [[_branch_command(), _move_route_command([5, 8])]])  # LEFT, same cell
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
