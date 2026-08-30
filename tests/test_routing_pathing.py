"""Tests for `rpg2gba.routing.pathing`."""
from __future__ import annotations

import pytest

from rpg2gba.tileset_converter.stairs import StairSide
from rpg2gba.traversal.direction import Direction
from rpg2gba.traversal.graph import MapGraph
from rpg2gba.traversal.triggers import Certainty, TriggerKind, TriggerOverlay, TriggerRef
from rpg2gba.traversal.world import WorldEdge, WorldGraph

from rpg2gba.routing.pathing import RoutePlanningError, path_avoiding, plan_segment


def _open_grid(width: int, height: int) -> dict[tuple[int, int], bool]:
    return {(x, y): False for x in range(width) for y in range(height)}


def _walled_grid(
    width: int, height: int, walls: set[tuple[int, int]],
) -> dict[tuple[int, int], bool]:
    return {(x, y): (x, y) in walls for x in range(width) for y in range(height)}


def _coord_ref(script: str, certainty: Certainty = Certainty.CERTAIN) -> TriggerRef:
    return TriggerRef(
        kind=TriggerKind.COORD_EVENT, script=script, certainty=certainty,
        owner_xy=None, detail="unconditional",
    )


def _empty_overlay(map_id: int) -> TriggerOverlay:
    return TriggerOverlay(map_id=map_id, tiles={})


def _world(edges: list[WorldEdge]) -> WorldGraph:
    map_ids = frozenset({e.src_map for e in edges} | {e.dst_map for e in edges})
    return WorldGraph(
        edges=edges,
        names={m: f"Map{m:03d}" for m in map_ids},
        map_ids=map_ids,
        maps_without_info=frozenset(),
        infos_without_map=frozenset(),
        variable_warp_count=0,
        variable_warp_maps={},
    )


# ---------------------------------------------------------------------------
# path_avoiding
# ---------------------------------------------------------------------------


def test_path_avoiding_detours_around_an_avoided_cell():
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    avoid = frozenset({(1, 1)})

    path = path_avoiding(graph, (0, 1), (2, 1), avoid)

    assert path is not None
    assert (1, 1) not in path
    assert path[0] == (0, 1)
    assert path[-1] == (2, 1)
    assert len(path) > 3  # detour is longer than the direct 3-cell route


def test_path_avoiding_permits_start_and_goal_even_if_in_avoid_set():
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    avoid = frozenset({(0, 0), (2, 2)})

    path = path_avoiding(graph, (0, 0), (2, 2), avoid)

    assert path is not None
    assert path[0] == (0, 0)
    assert path[-1] == (2, 2)


def test_path_avoiding_raises_when_start_not_walkable():
    walls = {(0, 0)}
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_walled_grid(3, 3, walls))
    with pytest.raises(ValueError, match="not walkable"):
        path_avoiding(graph, (0, 0), (2, 2), frozenset())


def test_path_avoiding_returns_none_when_truly_unreachable():
    walls = {(x, 1) for x in range(3)}
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_walled_grid(3, 3, walls))
    assert path_avoiding(graph, (0, 0), (0, 2), frozenset()) is None


def test_path_avoiding_honors_stair_diagonal_edge():
    # A single stair cell at (1,1), RIGHT side (NW/SE axis). Pressing EAST
    # from the stair lands SE at (2,2). Wall off the ordinary N/S neighbours
    # of the stair so the only way to (2,2) is through the diagonal.
    walls = {(1, 0), (1, 2)}
    graph = MapGraph(
        map_id=1, width=3, height=3, tileset_id=0,
        blocked=_walled_grid(3, 3, walls),
        stair_sides={(1, 1): StairSide.RIGHT},
    )
    path = path_avoiding(graph, (0, 1), (2, 2), frozenset())
    # `graph.neighbors()` presents the stair as a single displacement edge
    # straight from the approach cell to the landing cell -- the stair cell
    # itself never appears as a distinct step (see graph.py's module
    # docstring on why this is a displacement, not an 8-neighbour edge).
    assert path == [(0, 1), (2, 2)]


def test_path_avoiding_honors_ledge_jump_edge():
    # A ledge at (1,1) facing SOUTH: approach from (1,0), jump lands at (1,2).
    # No other route exists (side columns walled).
    walls = {(0, 0), (2, 0), (0, 1), (2, 1), (0, 2), (2, 2)}
    graph = MapGraph(
        map_id=1, width=3, height=3, tileset_id=0,
        blocked=_walled_grid(3, 3, walls),
        ledge_directions={(1, 1): Direction.SOUTH},
    )
    path = path_avoiding(graph, (1, 0), (1, 2), frozenset())
    assert path == [(1, 0), (1, 2)]


# ---------------------------------------------------------------------------
# plan_segment -- same map
# ---------------------------------------------------------------------------


def test_plan_segment_same_map_no_crossings_when_avoid_route_exists():
    # (1, 1) carries a script foreign to this chapter's destination_scripts,
    # so it lands in the avoid set -- but an open grid has a detour, so the
    # segment succeeds with no crossings at all.
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    overlay = TriggerOverlay(
        map_id=1, tiles={(1, 1): [_coord_ref("map099/someone_elses_event")]},
    )
    result = plan_segment(
        1, (0, 1), 1, (2, 1),
        graphs={1: graph}, overlays={1: overlay},
        destination_scripts=frozenset({"map001/ev001"}),
    )
    assert len(result.legs) == 1
    assert result.legs[0].map_id == 1
    assert (1, 1) not in result.legs[0].tiles
    assert result.crossings == ()
    assert result.tile_count == len(result.legs[0].tiles) - 1


def test_plan_segment_same_map_permits_own_script_tile_directly():
    # Same trigger tile, but its script IS one of this chapter's own
    # destination scripts -- `foreign_tiles` excludes it, so it's not
    # avoided at all and the direct route through it is fine.
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    overlay = TriggerOverlay(
        map_id=1, tiles={(1, 1): [_coord_ref("map001/ev001")]},
    )
    result = plan_segment(
        1, (0, 1), 1, (2, 1),
        graphs={1: graph}, overlays={1: overlay},
        destination_scripts=frozenset({"map001/ev001"}),
    )
    assert result.legs[0].tiles == ((0, 1), (1, 1), (2, 1))
    assert result.crossings == ()


def test_plan_segment_fallback_records_crossing_when_only_route_is_foreign():
    # Single-file corridor: (0,1)-(1,1)-(2,1). The middle cell is a foreign
    # trigger tile, and it's the only path through.
    walls = {(0, 0), (1, 0), (2, 0), (0, 2), (1, 2), (2, 2)}
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_walled_grid(3, 3, walls))
    overlay = TriggerOverlay(
        map_id=1,
        tiles={(1, 1): [_coord_ref("map099/ev005", Certainty.CERTAIN)]},
    )
    result = plan_segment(
        1, (0, 1), 1, (2, 1),
        graphs={1: graph}, overlays={1: overlay},
        destination_scripts=frozenset({"map001/ev_mine"}),  # doesn't match the foreign script
    )
    assert len(result.legs) == 1
    assert result.legs[0].tiles == ((0, 1), (1, 1), (2, 1))
    assert len(result.crossings) == 1
    crossing = result.crossings[0]
    assert crossing.map_id == 1
    assert crossing.cell == (1, 1)
    assert crossing.script == "map099/ev005"
    assert crossing.certainty == "certain"


def test_plan_segment_raises_when_goal_truly_unreachable():
    walls = {(x, 1) for x in range(3)}
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_walled_grid(3, 3, walls))
    overlay = _empty_overlay(1)
    with pytest.raises(RoutePlanningError, match="unreachable"):
        plan_segment(
            1, (0, 0), 1, (0, 2),
            graphs={1: graph}, overlays={1: overlay},
            destination_scripts=frozenset(),
        )


# ---------------------------------------------------------------------------
# plan_segment -- cross map
# ---------------------------------------------------------------------------


def test_plan_segment_missing_world_raises():
    graph1 = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    graph2 = MapGraph(map_id=2, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    with pytest.raises(RoutePlanningError, match="WorldGraph"):
        plan_segment(
            1, (0, 0), 2, (2, 2),
            graphs={1: graph1, 2: graph2},
            overlays={1: _empty_overlay(1), 2: _empty_overlay(2)},
            destination_scripts=frozenset(),
            world=None,
        )


def test_plan_segment_warp_stitch_produces_two_legs_with_exit_warp():
    graph1 = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    graph2 = MapGraph(map_id=2, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    world = _world([
        WorldEdge(src_map=1, dst_map=2, kind="warp", src_cell=(2, 2), dst_cell=(0, 0), event_id=7),
    ])

    result = plan_segment(
        1, (0, 0), 2, (2, 2),
        graphs={1: graph1, 2: graph2},
        overlays={1: _empty_overlay(1), 2: _empty_overlay(2)},
        destination_scripts=frozenset(),
        world=world,
    )

    assert len(result.legs) == 2
    first, second = result.legs
    assert first.map_id == 1
    assert first.tiles[0] == (0, 0)
    assert first.tiles[-1] == (2, 2)
    assert first.exit_warp is not None
    assert first.exit_warp.event_id == 7
    assert first.exit_warp.dest_map == 2
    assert first.exit_warp.dest_cell == (0, 0)

    assert second.map_id == 2
    assert second.tiles[0] == (0, 0)
    assert second.tiles[-1] == (2, 2)
    assert second.exit_warp is None


def test_plan_segment_connection_hop_raises():
    graph1 = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    graph2 = MapGraph(map_id=2, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    world = _world([
        WorldEdge(src_map=1, dst_map=2, kind="connection", src_cell=None, dst_cell=None),
    ])

    with pytest.raises(RoutePlanningError, match="connection"):
        plan_segment(
            1, (0, 0), 2, (2, 2),
            graphs={1: graph1, 2: graph2},
            overlays={1: _empty_overlay(1), 2: _empty_overlay(2)},
            destination_scripts=frozenset(),
            world=world,
        )
