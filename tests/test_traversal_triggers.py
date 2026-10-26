"""Tests for the per-map trigger overlay (src/rpg2gba/traversal/triggers.py).

Uses small synthetic fixtures written to `tmp_path` (a fake
`map_constants.json` + a fake `engine/data/maps/<dir>/map.json`) so the tests
don't depend on which slice of the corpus happens to be emitted, plus one
golden test against the real, already-emitted Route01 map (Uranium map id 33)
for a sanity check against production data.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.traversal.triggers import (
    Certainty,
    TriggerKind,
    build_trigger_overlay,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_MAP_CONSTANTS = REPO_ROOT / "output" / "uranium-build" / "porymap" / "map_constants.json"
REAL_ENGINE_MAPS_DIR = REPO_ROOT / "engine" / "data" / "maps"


class FakeGraph:
    """Minimal stand-in for MapGraph: only `is_walkable` is used by
    triggers.py, so this duck-types just that one method."""

    def __init__(self, blocked: set[tuple[int, int]]):
        self.blocked = blocked

    def is_walkable(self, cell: tuple[int, int]) -> bool:
        return cell not in self.blocked


def _write_fixture(
    tmp_path: Path,
    map_id: int,
    dir_name: str,
    object_events: list[dict],
    coord_events: list[dict] | None = None,
) -> tuple[Path, Path]:
    constants_path = tmp_path / "map_constants.json"
    constants_path.write_text(
        json.dumps({str(map_id): {"dir_name": dir_name}}), encoding="utf-8"
    )
    maps_dir = tmp_path / "maps"
    map_dir = maps_dir / dir_name
    map_dir.mkdir(parents=True)
    (map_dir / "map.json").write_text(
        json.dumps(
            {
                "object_events": object_events,
                "coord_events": coord_events or [],
            }
        ),
        encoding="utf-8",
    )
    return constants_path, maps_dir


def _trainer(
    x: int,
    y: int,
    movement_type: str,
    sight_range: int,
    script: str,
    trainer_type: str = "TRAINER_TYPE_NORMAL",
) -> dict:
    return {
        "graphics_id": "OBJ_EVENT_GFX_TEST",
        "x": x,
        "y": y,
        "elevation": 3,
        "movement_type": movement_type,
        "movement_range_x": 0,
        "movement_range_y": 0,
        "trainer_type": trainer_type,
        "trainer_sight_or_berry_tree_id": str(sight_range),
        "script": script,
        "flag": "0",
    }


def test_range_exclusive_of_own_tile_inclusive_of_far_tile(tmp_path):
    constants_path, maps_dir = _write_fixture(
        tmp_path,
        1,
        "TestMap",
        [_trainer(10, 10, "MOVEMENT_TYPE_FACE_DOWN", 3, "Script1")],
    )
    overlay = build_trigger_overlay(
        1, graph=FakeGraph(set()), map_constants_json=constants_path, engine_maps_dir=maps_dir
    )
    # facing south from (10, 10), range 3 -> (10,11) (10,12) (10,13); NOT (10,10)
    assert (10, 10) not in overlay.tiles
    assert (10, 11) in overlay.tiles
    assert (10, 12) in overlay.tiles
    assert (10, 13) in overlay.tiles
    assert (10, 14) not in overlay.tiles


def test_cone_is_one_tile_wide(tmp_path):
    constants_path, maps_dir = _write_fixture(
        tmp_path,
        1,
        "TestMap",
        [_trainer(10, 10, "MOVEMENT_TYPE_FACE_DOWN", 3, "Script1")],
    )
    overlay = build_trigger_overlay(
        1, graph=FakeGraph(set()), map_constants_json=constants_path, engine_maps_dir=maps_dir
    )
    # a tile diagonally adjacent to the line (e.g. (11, 11)) is never in the cone
    assert (11, 11) not in overlay.tiles
    assert (9, 11) not in overlay.tiles


def test_occlusion_truncates_at_blocked_tile(tmp_path):
    constants_path, maps_dir = _write_fixture(
        tmp_path,
        1,
        "TestMap",
        [_trainer(10, 10, "MOVEMENT_TYPE_FACE_DOWN", 5, "Script1")],
    )
    graph = FakeGraph(blocked={(10, 12)})
    overlay = build_trigger_overlay(
        1, graph=graph, map_constants_json=constants_path, engine_maps_dir=maps_dir
    )
    assert (10, 11) in overlay.tiles
    assert (10, 12) not in overlay.tiles  # the blocker itself
    assert (10, 13) not in overlay.tiles  # truncated, never reached
    assert (10, 14) not in overlay.tiles


def test_multi_facing_movement_type_is_union_and_possible(tmp_path):
    constants_path, maps_dir = _write_fixture(
        tmp_path,
        1,
        "TestMap",
        [_trainer(10, 10, "MOVEMENT_TYPE_LOOK_AROUND", 2, "Script1")],
    )
    overlay = build_trigger_overlay(
        1, graph=FakeGraph(set()), map_constants_json=constants_path, engine_maps_dir=maps_dir
    )
    expected_cells = {
        (10, 8), (10, 9),   # north
        (10, 11), (10, 12), # south
        (8, 10), (9, 10),   # west
        (11, 10), (12, 10), # east
    }
    assert set(overlay.tiles.keys()) == expected_cells
    for cell in expected_cells:
        refs = overlay.refs_at(cell)
        assert len(refs) == 1
        assert refs[0].certainty is Certainty.POSSIBLE


def test_fixed_facing_stationary_trainer_is_certain(tmp_path):
    constants_path, maps_dir = _write_fixture(
        tmp_path,
        1,
        "TestMap",
        [_trainer(10, 10, "MOVEMENT_TYPE_FACE_DOWN", 2, "Script1")],
    )
    overlay = build_trigger_overlay(
        1, graph=FakeGraph(set()), map_constants_json=constants_path, engine_maps_dir=maps_dir
    )
    refs = overlay.refs_at((10, 11))
    assert len(refs) == 1
    assert refs[0].certainty is Certainty.CERTAIN
    assert refs[0].kind is TriggerKind.TRAINER_SIGHT
    assert refs[0].owner_xy == (10, 10)


def test_no_graph_forces_possible_even_for_fixed_facing(tmp_path):
    constants_path, maps_dir = _write_fixture(
        tmp_path,
        1,
        "TestMap",
        [_trainer(10, 10, "MOVEMENT_TYPE_FACE_DOWN", 2, "Script1")],
    )
    overlay = build_trigger_overlay(
        1, graph=None, map_constants_json=constants_path, engine_maps_dir=maps_dir
    )
    refs = overlay.refs_at((10, 11))
    assert len(refs) == 1
    assert refs[0].certainty is Certainty.POSSIBLE


def test_see_all_directions_covers_four_directions(tmp_path):
    constants_path, maps_dir = _write_fixture(
        tmp_path,
        1,
        "TestMap",
        [
            _trainer(
                10,
                10,
                "MOVEMENT_TYPE_FACE_DOWN",
                2,
                "Script1",
                trainer_type="TRAINER_TYPE_SEE_ALL_DIRECTIONS",
            )
        ],
    )
    overlay = build_trigger_overlay(
        1, graph=FakeGraph(set()), map_constants_json=constants_path, engine_maps_dir=maps_dir
    )
    expected_cells = {
        (10, 8), (10, 9),
        (10, 11), (10, 12),
        (8, 10), (9, 10),
        (11, 10), (12, 10),
    }
    assert set(overlay.tiles.keys()) == expected_cells
    for cell in expected_cells:
        assert overlay.refs_at(cell)[0].certainty is Certainty.POSSIBLE


def test_coord_events_land_on_exact_tiles(tmp_path):
    constants_path, maps_dir = _write_fixture(
        tmp_path,
        1,
        "TestMap",
        [],
        coord_events=[
            {"x": 5, "y": 5, "elevation": 3, "var": "VAR_TEMP_F", "var_value": "0", "script": "DispatchScript"}
        ],
    )
    overlay = build_trigger_overlay(
        1, graph=FakeGraph(set()), map_constants_json=constants_path, engine_maps_dir=maps_dir
    )
    refs = overlay.refs_at((5, 5))
    assert len(refs) == 1
    assert refs[0].kind is TriggerKind.COORD_EVENT
    assert refs[0].certainty is Certainty.CERTAIN
    assert refs[0].script == "DispatchScript"
    assert refs[0].owner_xy is None
    assert "VAR_TEMP_F" in refs[0].detail


def test_foreign_tiles_excludes_destination_script(tmp_path):
    constants_path, maps_dir = _write_fixture(
        tmp_path,
        1,
        "TestMap",
        [_trainer(10, 10, "MOVEMENT_TYPE_FACE_DOWN", 2, "OwnScript")],
        coord_events=[
            {"x": 20, "y": 20, "elevation": 3, "var": None, "var_value": None, "script": "OtherScript"}
        ],
    )
    overlay = build_trigger_overlay(
        1, graph=FakeGraph(set()), map_constants_json=constants_path, engine_maps_dir=maps_dir
    )
    foreign = overlay.foreign_tiles({"OwnScript"})
    assert (20, 20) in foreign
    assert (10, 11) not in foreign  # this tile's only ref IS the destination script


def test_missing_emitted_map_raises(tmp_path):
    constants_path = tmp_path / "map_constants.json"
    constants_path.write_text(
        json.dumps({"1": {"dir_name": "NeverEmitted"}}), encoding="utf-8"
    )
    maps_dir = tmp_path / "maps"  # deliberately empty -- no NeverEmitted/map.json
    maps_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        build_trigger_overlay(1, map_constants_json=constants_path, engine_maps_dir=maps_dir)


def test_unknown_map_id_raises(tmp_path):
    constants_path = tmp_path / "map_constants.json"
    constants_path.write_text(json.dumps({"1": {"dir_name": "Foo"}}), encoding="utf-8")
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    with pytest.raises(KeyError):
        build_trigger_overlay(999, map_constants_json=constants_path, engine_maps_dir=maps_dir)


def test_unknown_movement_type_on_trainer_fails_loud(tmp_path):
    constants_path, maps_dir = _write_fixture(
        tmp_path,
        1,
        "TestMap",
        [_trainer(10, 10, "MOVEMENT_TYPE_ROTATE_CLOCKWISE", 2, "Script1")],
    )
    with pytest.raises(ValueError, match="movement_type"):
        build_trigger_overlay(
            1, graph=FakeGraph(set()), map_constants_json=constants_path, engine_maps_dir=maps_dir
        )


@pytest.mark.skipif(
    not (REAL_MAP_CONSTANTS.exists() and (REAL_ENGINE_MAPS_DIR / "Route01" / "map.json").exists()),
    reason="Route01 not emitted in this checkout",
)
def test_golden_route01_trainer_sight():
    overlay = build_trigger_overlay(
        33,
        map_constants_json=REAL_MAP_CONSTANTS,
        engine_maps_dir=REAL_ENGINE_MAPS_DIR,
    )
    # Map033_EV009_Page1: FACE_DOWN trainer at (30, 41), sight range 3 -> south
    refs = overlay.refs_at((30, 44))
    scripts = {r.script for r in refs}
    assert "Map033_EV009_Page1" in scripts
    for r in refs:
        if r.script == "Map033_EV009_Page1":
            assert r.owner_xy == (30, 41)
            assert r.kind is TriggerKind.TRAINER_SIGHT

    # Map033_EV010_Page1: FACE_UP trainer at (48, 42), sight range 4 -> north
    refs_up = overlay.refs_at((48, 38))
    assert any(r.script == "Map033_EV010_Page1" for r in refs_up)


@pytest.mark.skipif(
    not (REAL_MAP_CONSTANTS.exists() and (REAL_ENGINE_MAPS_DIR / "Route02" / "map.json").exists()),
    reason="Route02 not emitted in this checkout",
)
def test_golden_route02_coord_events():
    overlay = build_trigger_overlay(
        35,
        map_constants_json=REAL_MAP_CONSTANTS,
        engine_maps_dir=REAL_ENGINE_MAPS_DIR,
    )
    for cell in [(25, 27), (25, 28), (25, 29)]:
        refs = overlay.refs_at(cell)
        assert any(
            r.kind is TriggerKind.COORD_EVENT and r.script == "Map035_EV019_Dispatch"
            for r in refs
        )


def test_patrolling_trainer_sees_from_every_cell_of_its_movement_box(tmp_path):
    # CH11 Route 4, Sr. Goldkorn: WALK_SEQUENCE, range +-2 x +-4, sight 4. From
    # (40,56) he sees (40,60), which the spawn-only cone (40,56..59) missed.
    goldkorn = _trainer(40, 55, "MOVEMENT_TYPE_WALK_SEQUENCE_DOWN_LEFT_UP_RIGHT", 4, "Gold")
    goldkorn["movement_range_x"], goldkorn["movement_range_y"] = 2, 4
    constants_path, maps_dir = _write_fixture(tmp_path, 1, "TestMap", [goldkorn])
    overlay = build_trigger_overlay(
        1, graph=FakeGraph(set()), map_constants_json=constants_path, engine_maps_dir=maps_dir
    )
    assert (40, 60) in overlay.tiles
    assert (40, 63) in overlay.tiles  # from (40,59), the box's south edge
    assert (40, 64) not in overlay.tiles
    assert all(r.certainty is Certainty.POSSIBLE for r in overlay.tiles[(40, 60)])


def test_stationary_trainer_ignores_movement_range(tmp_path):
    t = _trainer(10, 10, "MOVEMENT_TYPE_FACE_DOWN", 2, "S")
    t["movement_range_x"], t["movement_range_y"] = 3, 3
    constants_path, maps_dir = _write_fixture(tmp_path, 1, "TestMap", [t])
    overlay = build_trigger_overlay(
        1, graph=FakeGraph(set()), map_constants_json=constants_path, engine_maps_dir=maps_dir
    )
    assert set(overlay.tiles) == {(10, 11), (10, 12)}
