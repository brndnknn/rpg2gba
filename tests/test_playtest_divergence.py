"""Tests for `rpg2gba.playtest.divergence`.

Pure-data tests only: no emulator, no ROM, no network. `PlanIndex` objects
are built by hand (or via `PlanIndex.from_plan` over a small hand-built
`RoutePlan`) so the comparison logic is exercised in isolation, per the
module's own design (see `divergence.py`'s docstring for why this had to be
possible at all).
"""
from __future__ import annotations

import json
from pathlib import Path

from rpg2gba.playtest.divergence import (
    Divergence,
    PlanIndex,
    TriggerFact,
    WalkedTile,
    compare_walk,
    load_plan_index,
)
from rpg2gba.routing.plan import (
    RouteLeg,
    RouteNode,
    RoutePlan,
    RouteSegment,
    TriggerCrossing,
)


def _tile(map_id: int | None, x: int, y: int) -> WalkedTile:
    return WalkedTile(map_id=map_id, map_group=0, map_num=map_id or 0, x=x, y=y)


def _fact(script: str = "map036/ev001") -> TriggerFact:
    return TriggerFact(script=script, kind="coord_event", certainty="certain", detail="unconditional")


def _plan_index(
    tiles: dict[int, set[tuple[int, int]]] | None = None,
    declared: dict[int, set[tuple[int, int]]] | None = None,
) -> PlanIndex:
    return PlanIndex(
        tiles={k: frozenset(v) for k, v in (tiles or {}).items()},
        declared_crossings={k: frozenset(v) for k, v in (declared or {}).items()},
        chapter_id="CH05",
    )


# --- no plan ---------------------------------------------------------------


def test_no_plan_means_not_compared_even_over_a_trigger_tile():
    walked = [_tile(36, 9, 9)]
    foreign = {36: {(9, 9): (_fact(),)}}
    result = compare_walk("B1", walked, plan=None, foreign_triggers=foreign)
    assert result.compared is False
    assert result.off_plan == ()
    assert result.trigger_violations == ()
    assert result.failed is False
    assert result.steps == 1
    assert result.note


# --- fully on-plan -----------------------------------------------------------


def test_fully_on_plan_walk_has_no_divergences():
    walked = [_tile(36, 7, 7), _tile(36, 8, 7), _tile(36, 8, 8)]
    plan = _plan_index(tiles={36: {(7, 7), (8, 7), (8, 8)}})
    result = compare_walk("B1", walked, plan=plan, foreign_triggers={})
    assert result.compared is True
    assert result.off_plan == ()
    assert result.trigger_violations == ()
    assert result.failed is False
    assert result.unresolved == 0


# --- off-plan, not a trigger -------------------------------------------------


def test_off_plan_non_trigger_tile_is_recorded_but_not_failing():
    walked = [_tile(36, 7, 7), _tile(36, 20, 20)]
    plan = _plan_index(tiles={36: {(7, 7)}})
    result = compare_walk("B1", walked, plan=plan, foreign_triggers={})
    assert len(result.off_plan) == 1
    assert result.off_plan[0] == Divergence(
        map_id=36, cell=(20, 20), step_index=1, kind="off_plan"
    )
    assert result.trigger_violations == ()
    assert result.failed is False


# --- off-plan foreign trigger -------------------------------------------------


def test_off_plan_foreign_trigger_tile_fails_the_beat():
    walked = [_tile(36, 7, 7), _tile(36, 9, 9)]
    plan = _plan_index(tiles={36: {(7, 7)}})
    fact = _fact("map036/timothy_battle")
    foreign = {36: {(9, 9): (fact,)}}
    result = compare_walk("B1", walked, plan=plan, foreign_triggers=foreign)
    assert result.off_plan == ()
    assert len(result.trigger_violations) == 1
    violation = result.trigger_violations[0]
    assert violation.map_id == 36
    assert violation.cell == (9, 9)
    assert violation.step_index == 1
    assert violation.kind == "trigger"
    assert violation.triggers == (fact,)
    assert result.failed is True


# --- plan-declared crossing --------------------------------------------------


def test_plan_declared_crossing_is_not_a_violation_or_off_plan():
    walked = [_tile(36, 9, 9)]
    plan = _plan_index(tiles={36: {(7, 7)}}, declared={36: {(9, 9)}})
    foreign = {36: {(9, 9): (_fact(),)}}
    result = compare_walk("B1", walked, plan=plan, foreign_triggers=foreign)
    assert result.off_plan == ()
    assert result.trigger_violations == ()
    assert result.failed is False


# --- on-plan tile that happens to carry a foreign trigger --------------------


def test_on_plan_tile_that_is_also_a_foreign_trigger_is_not_reported():
    walked = [_tile(36, 9, 9)]
    plan = _plan_index(tiles={36: {(9, 9)}})
    foreign = {36: {(9, 9): (_fact(),)}}
    result = compare_walk("B1", walked, plan=plan, foreign_triggers=foreign)
    assert result.off_plan == ()
    assert result.trigger_violations == ()
    assert result.failed is False


# --- unresolved map_id --------------------------------------------------------


def test_unresolved_map_id_counted_not_reported():
    walked = [_tile(None, 1, 1), _tile(36, 7, 7)]
    plan = _plan_index(tiles={36: {(7, 7)}})
    result = compare_walk("B1", walked, plan=plan, foreign_triggers={})
    assert result.unresolved == 1
    assert result.off_plan == ()
    assert result.trigger_violations == ()
    assert result.steps == 2


# --- dedup ---------------------------------------------------------------


def test_repeated_visits_to_same_bad_cell_dedup_to_one_row_at_first_index():
    walked = [_tile(36, 20, 20), _tile(36, 7, 7), _tile(36, 20, 20), _tile(36, 20, 20)]
    plan = _plan_index(tiles={36: {(7, 7)}})
    result = compare_walk("B1", walked, plan=plan, foreign_triggers={})
    assert len(result.off_plan) == 1
    assert result.off_plan[0].step_index == 0
    assert "3" in result.note or "raw" in result.note  # raw step count surfaced


def test_repeated_visits_to_same_trigger_cell_dedup_to_one_row():
    walked = [_tile(36, 9, 9), _tile(36, 9, 9), _tile(36, 9, 9)]
    plan = _plan_index()
    fact = _fact()
    foreign = {36: {(9, 9): (fact,)}}
    result = compare_walk("B1", walked, plan=plan, foreign_triggers=foreign)
    assert len(result.trigger_violations) == 1
    assert result.trigger_violations[0].step_index == 0


# --- PlanIndex.from_plan --------------------------------------------------


def _sample_route_plan() -> RoutePlan:
    nodes = (
        RouteNode(index=0, kind="entry", map_id=36, cell=(7, 7)),
        RouteNode(
            index=1, kind="group", map_id=37, cell=(3, 3),
            group="g1", beats=("B1",), rows=("map036/ev001/p0",),
        ),
        RouteNode(index=2, kind="exit", map_id=37, cell=(5, 5)),
    )
    segments = (
        RouteSegment(
            from_index=0, to_index=1,
            legs=(
                RouteLeg(map_id=36, tiles=((7, 7), (8, 7))),
                RouteLeg(map_id=37, tiles=((0, 0), (1, 0), (3, 3))),
            ),
            tile_count=4,
        ),
        RouteSegment(
            from_index=1, to_index=2,
            legs=(RouteLeg(map_id=37, tiles=((3, 3), (4, 4), (5, 5))),),
            tile_count=2,
            crossed_foreign_triggers=(
                TriggerCrossing(
                    map_id=37, cell=(4, 4), script="map037/patrol_guard",
                    certainty="possible", declared=True,
                ),
                TriggerCrossing(
                    map_id=37, cell=(9, 9), script="map037/undeclared",
                    certainty="possible", declared=False,
                ),
            ),
        ),
    )
    return RoutePlan(
        chapter_id="CH05",
        chapter_module="passage_cave",
        nodes=nodes,
        segments=segments,
        precedence=(),
        tile_cost=6,
        solver_method="greedy+2opt",
    )


def test_plan_index_from_plan_unions_tiles_across_legs_and_segments():
    index = PlanIndex.from_plan(_sample_route_plan())
    assert index.chapter_id == "CH05"
    assert index.tiles[36] == frozenset({(7, 7), (8, 7)})
    # map 37 appears in legs from both segments -- union, not overwrite.
    assert index.tiles[37] == frozenset({(0, 0), (1, 0), (3, 3), (4, 4), (5, 5)})


def test_plan_index_from_plan_only_keeps_declared_crossings():
    index = PlanIndex.from_plan(_sample_route_plan())
    assert index.declared_crossings[37] == frozenset({(4, 4)})
    # the undeclared crossing at (9, 9) must not appear as an approved crossing.
    assert (9, 9) not in index.declared_crossings[37]


# --- load_plan_index -------------------------------------------------------


def test_load_plan_index_returns_none_for_missing_chapter_file(tmp_path: Path):
    result = load_plan_index("CH99", root=tmp_path)
    assert result is None


def test_load_plan_index_loads_an_existing_plan(tmp_path: Path):
    from rpg2gba.routing.plan import route_path, write_plan

    plan = _sample_route_plan()
    write_plan(plan, route_path("CH05", root=tmp_path))
    index = load_plan_index("CH05", root=tmp_path)
    assert index is not None
    assert index.chapter_id == "CH05"
    assert index.tiles[36] == frozenset({(7, 7), (8, 7)})


# --- to_dict JSON round trip -------------------------------------------------


def test_walk_comparison_to_dict_is_json_serialisable():
    walked = [_tile(36, 7, 7), _tile(36, 9, 9)]
    plan = _plan_index(tiles={36: {(7, 7)}})
    fact = _fact("map036/timothy_battle")
    foreign = {36: {(9, 9): (fact,)}}
    result = compare_walk("B1", walked, plan=plan, foreign_triggers=foreign)
    encoded = json.dumps(result.to_dict())
    decoded = json.loads(encoded)
    assert decoded["beat"] == "B1"
    assert decoded["failed"] is True
    assert decoded["trigger_violations"][0]["cell"] == [9, 9]
    assert decoded["trigger_violations"][0]["triggers"][0]["script"] == "map036/timothy_battle"


def test_divergence_to_dict_is_json_serialisable():
    d = Divergence(map_id=36, cell=(1, 2), step_index=0, kind="off_plan")
    encoded = json.dumps(d.to_dict())
    decoded = json.loads(encoded)
    assert decoded == {"map_id": 36, "cell": [1, 2], "step": 0, "kind": "off_plan", "triggers": []}


def test_no_plan_comparison_to_dict_round_trips():
    result = compare_walk("B1", [_tile(36, 1, 1)], plan=None, foreign_triggers={})
    encoded = json.dumps(result.to_dict())
    decoded = json.loads(encoded)
    assert decoded["compared"] is False
