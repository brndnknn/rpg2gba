"""Tests for `rpg2gba.routing.plan`."""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.routing.plan import (
    PrecedenceEdge,
    RouteLeg,
    RouteNode,
    RoutePlan,
    RoutePlanError,
    RouteSegment,
    RouteWarp,
    TriggerCrossing,
    load_plan,
    plan_from_dict,
    plan_to_dict,
    route_path,
    write_plan,
)


def _sample_plan() -> RoutePlan:
    nodes = (
        RouteNode(index=0, kind="entry", map_id=36, cell=(7, 7)),
        RouteNode(
            index=1, kind="group", map_id=36, cell=(9, 9),
            group="g1", beats=("B1", "B2"), rows=("map036/ev001/p0",),
        ),
        RouteNode(index=2, kind="exit", map_id=36, cell=(10, 10)),
    )
    segments = (
        RouteSegment(
            from_index=0, to_index=1,
            legs=(RouteLeg(map_id=36, tiles=((7, 7), (8, 8), (9, 9))),),
            tile_count=2,
        ),
        RouteSegment(
            from_index=1, to_index=2,
            legs=(
                RouteLeg(
                    map_id=36, tiles=((9, 9), (10, 10)),
                    exit_warp=RouteWarp(event_id=5, dest_map=36, dest_cell=(10, 10)),
                ),
            ),
            tile_count=1,
            crossed_foreign_triggers=(
                TriggerCrossing(
                    map_id=36, cell=(9, 9), script="map035/ev002",
                    certainty="possible", declared=True,
                ),
            ),
        ),
    )
    precedence = (PrecedenceEdge(before="g1", after="g1", reason="self_switch:A map035/ev014"),)
    return RoutePlan(
        chapter_id="CH05",
        chapter_module="passage_cave",
        nodes=nodes,
        segments=segments,
        precedence=precedence,
        tile_cost=3,
        solver_method="greedy+2opt",
    )


# --- round trip ----------------------------------------------------------


def test_round_trip_to_dict_and_back():
    plan = _sample_plan()
    data = plan_to_dict(plan)
    rebuilt = plan_from_dict(data)
    assert rebuilt == plan


def test_to_dict_json_shape():
    plan = _sample_plan()
    data = plan_to_dict(plan)
    assert data["schema"] == 1
    assert data["chapter"] == "CH05"
    assert data["chapter_module"] == "passage_cave"
    assert data["cost"] == {"tiles": 3}
    assert data["solver"] == {"method": "greedy+2opt"}
    assert data["nodes"][0]["cell"] == [7, 7]
    assert data["segments"][0]["from"] == 0
    assert data["segments"][0]["to"] == 1
    assert data["segments"][1]["legs"][0]["exit_warp"]["dest_cell"] == [10, 10]
    assert isinstance(data["_comment"], list)


# --- write_plan / load_plan ------------------------------------------------


def test_write_plan_is_byte_identical_on_repeated_calls(tmp_path: Path):
    plan = _sample_plan()
    path = tmp_path / "CH05.route.json"
    write_plan(plan, path)
    first = path.read_bytes()
    write_plan(plan, path)
    second = path.read_bytes()
    assert first == second


def test_write_plan_then_load_plan_round_trips(tmp_path: Path):
    plan = _sample_plan()
    path = tmp_path / "CH05.route.json"
    write_plan(plan, path)
    loaded = load_plan(path)
    assert loaded == plan


def test_write_plan_ends_with_trailing_newline(tmp_path: Path):
    plan = _sample_plan()
    path = tmp_path / "CH05.route.json"
    write_plan(plan, path)
    assert path.read_text(encoding="utf-8").endswith("\n")


# --- route_path -------------------------------------------------------


def test_route_path_default_convention():
    assert route_path("CH05") == Path("reference/routes/CH05.route.json")


def test_route_path_with_root(tmp_path: Path):
    assert route_path("CH05", root=tmp_path) == tmp_path / "CH05.route.json"


# --- RouteLeg validation ------------------------------------------------


def test_route_leg_empty_tiles_rejected():
    with pytest.raises(RoutePlanError, match="non-empty"):
        RouteLeg(map_id=1, tiles=())


# --- TriggerCrossing validation ------------------------------------------


def test_trigger_crossing_bad_certainty_rejected():
    with pytest.raises(RoutePlanError, match="certainty"):
        TriggerCrossing(map_id=1, cell=(0, 0), script="s", certainty="maybe")


# --- RouteNode validation ------------------------------------------------


def test_route_node_bad_kind_rejected():
    with pytest.raises(RoutePlanError, match="unknown kind"):
        RouteNode(index=0, kind="waypoint", map_id=1, cell=(0, 0))


def test_route_node_group_requires_group_id():
    with pytest.raises(RoutePlanError, match="requires a non-None 'group'"):
        RouteNode(index=0, kind="group", map_id=1, cell=(0, 0), beats=("B1",))


def test_route_node_group_requires_nonempty_beats():
    with pytest.raises(RoutePlanError, match="requires a non-empty 'beats'"):
        RouteNode(index=0, kind="group", map_id=1, cell=(0, 0), group="g1")


def test_route_node_entry_forbids_group():
    with pytest.raises(RoutePlanError, match="must have group=None"):
        RouteNode(index=0, kind="entry", map_id=1, cell=(0, 0), group="g1")


def test_route_node_exit_forbids_beats():
    with pytest.raises(RoutePlanError, match="must have beats=\\(\\)"):
        RouteNode(index=0, kind="exit", map_id=1, cell=(0, 0), beats=("B1",))


# --- RoutePlan validation ------------------------------------------------


def _minimal_nodes() -> tuple[RouteNode, ...]:
    return (
        RouteNode(index=0, kind="entry", map_id=1, cell=(0, 0)),
        RouteNode(index=1, kind="exit", map_id=1, cell=(1, 1)),
    )


def _minimal_segment(from_index: int = 0, to_index: int = 1, tile_count: int = 1) -> RouteSegment:
    return RouteSegment(
        from_index=from_index, to_index=to_index,
        legs=(RouteLeg(map_id=1, tiles=((0, 0), (1, 1))),),
        tile_count=tile_count,
    )


def test_route_plan_node_indices_must_be_sequential():
    nodes = (
        RouteNode(index=0, kind="entry", map_id=1, cell=(0, 0)),
        RouteNode(index=5, kind="exit", map_id=1, cell=(1, 1)),
    )
    with pytest.raises(RoutePlanError, match="node indices must be exactly"):
        RoutePlan(
            chapter_id="CH01", chapter_module="mod", nodes=nodes,
            segments=(_minimal_segment(),), precedence=(), tile_cost=1,
            solver_method="greedy",
        )


def test_route_plan_first_node_must_be_entry():
    nodes = (
        RouteNode(index=0, kind="exit", map_id=1, cell=(0, 0)),
        RouteNode(index=1, kind="exit", map_id=1, cell=(1, 1)),
    )
    with pytest.raises(RoutePlanError, match="first node must have kind 'entry'"):
        RoutePlan(
            chapter_id="CH01", chapter_module="mod", nodes=nodes,
            segments=(_minimal_segment(),), precedence=(), tile_cost=1,
            solver_method="greedy",
        )


def test_route_plan_last_node_must_be_exit():
    nodes = (
        RouteNode(index=0, kind="entry", map_id=1, cell=(0, 0)),
        RouteNode(index=1, kind="entry", map_id=1, cell=(1, 1)),
    )
    with pytest.raises(RoutePlanError, match="last node must have kind 'exit'"):
        RoutePlan(
            chapter_id="CH01", chapter_module="mod", nodes=nodes,
            segments=(_minimal_segment(),), precedence=(), tile_cost=1,
            solver_method="greedy",
        )


def test_route_plan_segment_count_must_match_nodes():
    with pytest.raises(RoutePlanError, match="expected 1 segment"):
        RoutePlan(
            chapter_id="CH01", chapter_module="mod", nodes=_minimal_nodes(),
            segments=(), precedence=(), tile_cost=0, solver_method="greedy",
        )


def test_route_plan_segments_must_chain_consecutively():
    bad_segment = RouteSegment(
        from_index=0, to_index=2,
        legs=(RouteLeg(map_id=1, tiles=((0, 0), (1, 1))),),
        tile_count=1,
    )
    with pytest.raises(RoutePlanError, match="chain consecutively"):
        RoutePlan(
            chapter_id="CH01", chapter_module="mod", nodes=_minimal_nodes(),
            segments=(bad_segment,), precedence=(), tile_cost=1,
            solver_method="greedy",
        )


def test_route_plan_precedence_must_name_a_present_group():
    nodes = (
        RouteNode(index=0, kind="entry", map_id=1, cell=(0, 0)),
        RouteNode(
            index=1, kind="group", map_id=1, cell=(1, 1),
            group="g1", beats=("B1",),
        ),
        RouteNode(index=2, kind="exit", map_id=1, cell=(2, 2)),
    )
    segments = (
        _minimal_segment(0, 1, 1),
        _minimal_segment(1, 2, 1),
    )
    bad_precedence = (PrecedenceEdge(before="g1", after="ghost", reason="because"),)
    with pytest.raises(RoutePlanError, match="does not name a group present in nodes"):
        RoutePlan(
            chapter_id="CH01", chapter_module="mod", nodes=nodes,
            segments=segments, precedence=bad_precedence, tile_cost=2,
            solver_method="greedy",
        )


def test_route_plan_tile_cost_must_match_segment_sum():
    with pytest.raises(RoutePlanError, match="does not match the sum of segment tile_counts"):
        RoutePlan(
            chapter_id="CH01", chapter_module="mod", nodes=_minimal_nodes(),
            segments=(_minimal_segment(),), precedence=(), tile_cost=99,
            solver_method="greedy",
        )


# --- plan_from_dict strictness -------------------------------------------


def test_plan_from_dict_rejects_unknown_top_level_key():
    data = plan_to_dict(_sample_plan())
    data["bogus"] = True
    with pytest.raises(RoutePlanError, match="unknown keys"):
        plan_from_dict(data)


def test_plan_from_dict_rejects_missing_top_level_key():
    data = plan_to_dict(_sample_plan())
    del data["nodes"]
    with pytest.raises(RoutePlanError, match="missing"):
        plan_from_dict(data)


def test_plan_from_dict_rejects_wrong_schema():
    data = plan_to_dict(_sample_plan())
    data["schema"] = 2
    with pytest.raises(RoutePlanError, match="schema"):
        plan_from_dict(data)


def test_load_plan_rejects_invalid_json(tmp_path: Path):
    path = tmp_path / "bad.route.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(RoutePlanError, match="invalid JSON"):
        load_plan(path)
