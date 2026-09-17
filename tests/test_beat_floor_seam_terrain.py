"""Tests for `rpg2gba.beat_floor.terrain` (REDERIVATION_PLAN.md §16.3 C5):
row-level floors for `seam` and `terrain` (diagonal-stair) manifest rows.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.beat_floor import terrain

_BUILD_DIR = Path("output/uranium-build")


# --- synthetic: seam ---------------------------------------------------------


def test_seam_crossing_synthetic():
    connections = [[50, "S", 0, 51, "N", 3]]
    floors = terrain.seam_floors_for_map(50, connections)
    row_id = "map050/seam/S/map051"
    assert set(floors) == {row_id}
    row = floors[row_id]
    assert not row.refused
    assert len(row.assertions) == 1
    a = next(iter(row.assertions))
    assert a.kind == "seam_crossing"
    assert a.list_index == -1
    assert a.code is None
    assert a.tag == "position"
    assert dict(a.params) == {
        "map_id": 50, "direction": "S", "offset": 0,
        "other_map_id": 51, "other_direction": "N", "other_offset": 3,
    }


def test_seam_crossing_synthetic_other_side_not_included():
    # A connection is emitted from each map's OWN side (generator.
    # `_generate_seam_rows`); asking for map 50's floor must not also
    # produce map 51's row.
    connections = [[50, "S", 0, 51, "N", 3]]
    floors = terrain.seam_floors_for_map(50, connections)
    assert "map051/seam/N/map050" not in floors


# --- synthetic: stairs -------------------------------------------------------


def _move_route(*codes: int) -> dict:
    return {"list": [{"code": c, "parameters": []} for c in codes] + [{"code": 0, "parameters": []}]}


def _stair_commands(direction: int, then_code: int, else_code: int) -> list[dict]:
    return [
        {"code": 111, "indent": 0, "parameters": [6, -1, direction]},
        {"code": 209, "indent": 1, "parameters": [-1, _move_route(then_code)]},
        {"code": 411, "indent": 0, "parameters": []},
        {"code": 209, "indent": 1, "parameters": [-1, _move_route(else_code)]},
        {"code": 412, "indent": 0, "parameters": []},
    ]


def _stair_map(map_id: int, event_id: int, x: int, y: int, commands: list[dict]) -> dict:
    return {
        "map_id": map_id,
        "events": [
            {"id": event_id, "x": x, "y": y, "name": "Stairs",
             "pages": [{"trigger": 1, "list": commands}]},
        ],
    }


def test_stair_crossing_synthetic_right_side():
    commands = _stair_commands(direction=6, then_code=6, else_code=7)
    map_data = _stair_map(99, 1, 5, 5, commands)
    floors = terrain.stair_floors_for_map(99, map_data)
    row_id = "map099/terrain/stairs/5,5"
    assert set(floors) == {row_id}
    row = floors[row_id]
    assert not row.refused
    a = next(iter(row.assertions))
    assert a.kind == "stair_crossing"
    assert a.list_index == -1
    assert a.code is None
    assert a.tag == "position"
    params = dict(a.params)
    assert params["x"] == 5
    assert params["y"] == 5
    assert params["side"] == "right"
    assert params["steps"] == (("LEFT", -1, -1), ("RIGHT", 1, 1))


def test_stair_crossing_synthetic_left_side():
    commands = _stair_commands(direction=4, then_code=5, else_code=8)
    map_data = _stair_map(99, 1, 5, 5, commands)
    floors = terrain.stair_floors_for_map(99, map_data)
    row = floors["map099/terrain/stairs/5,5"]
    a = next(iter(row.assertions))
    params = dict(a.params)
    assert params["side"] == "left"
    assert params["steps"] == (("LEFT", -1, 1), ("RIGHT", 1, -1))


def test_stair_crossing_synthetic_empty_arm_yields_zero_displacement():
    # Map033 ev026's own shape: the "facing into the stair" arm has no
    # diagonal move at all -- net (0, 0), not a refusal.
    commands = [
        {"code": 111, "indent": 0, "parameters": [6, -1, 6]},
        {"code": 0, "indent": 1, "parameters": []},
        {"code": 411, "indent": 0, "parameters": []},
        {"code": 209, "indent": 1, "parameters": [-1, _move_route(7)]},
        {"code": 412, "indent": 0, "parameters": []},
    ]
    map_data = _stair_map(99, 1, 5, 5, commands)
    row = terrain.stair_floors_for_map(99, map_data)["map099/terrain/stairs/5,5"]
    assert not row.refused
    params = dict(next(iter(row.assertions)).params)
    assert params["steps"] == (("LEFT", -1, -1), ("RIGHT", 0, 0))


def test_stair_crossing_refusal_unknown_facing_direction():
    # Condition tests a facing value RMXP never uses for this idiom (not one
    # of 2/4/6/8) -- refused, not guessed (CLAUDE.md §4.5).
    commands = _stair_commands(direction=1, then_code=6, else_code=7)
    map_data = _stair_map(99, 1, 5, 5, commands)
    row = terrain.stair_floors_for_map(99, map_data)["map099/terrain/stairs/5,5"]
    assert row.refused
    assert row.assertions == frozenset()
    assert len(row.refusals) == 1
    assert row.refusals[0].reason == "stair_unknown_facing_direction"


def test_stair_crossing_refusal_branch_not_singular():
    # Two qualifying player-facing branches on the same page: which one is
    # THE stair branch is ambiguous, so this refuses rather than picking one.
    commands = (
        _stair_commands(direction=6, then_code=6, else_code=7)
        + _stair_commands(direction=6, then_code=6, else_code=7)
    )
    map_data = _stair_map(99, 1, 5, 5, commands)
    row = terrain.stair_floors_for_map(99, map_data)["map099/terrain/stairs/5,5"]
    assert row.refused
    assert row.refusals[0].reason == "stair_branch_not_singular"


def test_derive_stair_steps_direct():
    event = {
        "id": 1, "x": 5, "y": 5, "name": "Stairs",
        "pages": [{"trigger": 1, "list": _stair_commands(6, 6, 7)}],
    }
    steps, reason = terrain.derive_stair_steps(event)
    assert reason is None
    assert steps == (("LEFT", -1, -1), ("RIGHT", 1, 1))


# --- real-corpus spot checks -------------------------------------------------


def _skip_if_no_corpus():
    if not (_BUILD_DIR / "maps").exists():
        pytest.skip("no converted map corpus at output/uranium-build/maps")


def _load_map(map_id: int) -> dict:
    return json.loads(
        (_BUILD_DIR / "maps" / f"Map{map_id:03d}.json").read_text(encoding="utf-8"))


def test_ch05_map037_east_staircase_nw_se_axis():
    _skip_if_no_corpus()
    map_data = _load_map(37)
    floors = terrain.stair_floors_for_map(37, map_data)
    for row_id, expected in (
        ("map037/terrain/stairs/20,9", (("LEFT", -1, -1), ("RIGHT", 1, 1))),
    ):
        row = floors[row_id]
        assert not row.refused, row.refusals
        params = dict(next(iter(row.assertions)).params)
        assert params["side"] == "right"
        assert params["steps"] == expected


def test_ch05_map037_west_staircase_ne_sw_axis():
    _skip_if_no_corpus()
    map_data = _load_map(37)
    floors = terrain.stair_floors_for_map(37, map_data)
    row = floors["map037/terrain/stairs/11,9"]
    assert not row.refused, row.refusals
    params = dict(next(iter(row.assertions)).params)
    assert params["side"] == "left"
    assert params["steps"] == (("LEFT", -1, 1), ("RIGHT", 1, -1))


def test_ch02_map033_stairs_57_10():
    _skip_if_no_corpus()
    map_data = _load_map(33)
    floors = terrain.stair_floors_for_map(33, map_data)
    row = floors["map033/terrain/stairs/57,10"]
    assert not row.refused, row.refusals
    params = dict(next(iter(row.assertions)).params)
    assert params["side"] == "right"
    assert params["steps"] == (("LEFT", -1, -1), ("RIGHT", 1, 1))


def test_ch04_map035_seam_south_to_map031():
    _skip_if_no_corpus()
    conn_path = _BUILD_DIR / "connections.json"
    if not conn_path.exists():
        pytest.skip("no connections.json in the build corpus")
    connections = json.loads(conn_path.read_text(encoding="utf-8"))
    floors = terrain.seam_floors_for_map(35, connections)
    row_id = "map035/seam/S/map031"
    assert row_id in floors
    row = floors[row_id]
    assert not row.refused
    params = dict(next(iter(row.assertions)).params)
    assert params["map_id"] == 35
    assert params["direction"] == "S"
    assert params["other_map_id"] == 31
    assert params["other_direction"] == "N"
