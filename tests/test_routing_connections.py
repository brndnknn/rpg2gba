"""Tests for `rpg2gba.routing.connections` and its integration into
`pathing.plan_segment` for "connection"-kind hops.

Mirrors `tests/test_routing_pathing.py`'s and
`tests/test_traversal_reachability.py`'s style: hand-built `MapGraph`s with
explicit `blocked` dicts, no dependency on `output/` or `engine/`.
"""
from __future__ import annotations

import pytest

from rpg2gba.traversal.direction import Direction
from rpg2gba.traversal.graph import MapGraph
from rpg2gba.traversal.triggers import Certainty, TriggerKind, TriggerOverlay, TriggerRef
from rpg2gba.traversal.world import WorldEdge, WorldGraph

from rpg2gba.routing.connections import MapConnection, connections_between, crossing_cells
from rpg2gba.routing.pathing import RoutePlanningError, plan_segment


def _open_grid(width: int, height: int) -> dict[tuple[int, int], bool]:
    return {(x, y): False for x in range(width) for y in range(height)}


def _walled_grid(
    width: int, height: int, walls: set[tuple[int, int]],
) -> dict[tuple[int, int], bool]:
    return {(x, y): (x, y) in walls for x in range(width) for y in range(height)}


def _empty_overlay(map_id: int) -> TriggerOverlay:
    return TriggerOverlay(map_id=map_id, tiles={})


def _coord_ref(script: str, certainty: Certainty = Certainty.CERTAIN) -> TriggerRef:
    return TriggerRef(
        kind=TriggerKind.COORD_EVENT, script=script, certainty=certainty,
        owner_xy=None, detail="unconditional",
    )


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
# crossing_cells -- one direction per test, hand-computed expected cells
# ---------------------------------------------------------------------------


def test_crossing_cells_north_zero_offset_full_overlap():
    # map1's N edge (row 0) meets map2's S edge (row height-1); both offsets
    # 0 -> shift 0 -> every column lines up 1:1.
    from_graph = MapGraph(map_id=1, width=3, height=2, tileset_id=0, blocked=_open_grid(3, 2))
    to_graph = MapGraph(map_id=2, width=3, height=2, tileset_id=0, blocked=_open_grid(3, 2))
    connection = MapConnection(from_map=1, direction=Direction.NORTH, offset=0, to_map=2, to_offset=0)

    pairs = crossing_cells(connection, from_graph=from_graph, to_graph=to_graph)

    assert pairs == (
        ((0, 0), (0, 1)),
        ((1, 0), (1, 1)),
        ((2, 0), (2, 1)),
    )


def test_crossing_cells_south_positive_offset_partial_overlap():
    # map1's S edge (row height-1=2) meets map2's N edge (row 0). offset=2,
    # to_offset=0 -> shift=2 -> x_to = x_from - 2, so only x_from in {2, 3}
    # land in map2's width-4 grid (x_to in {0, 1}).
    from_graph = MapGraph(map_id=1, width=4, height=3, tileset_id=0, blocked=_open_grid(4, 3))
    to_graph = MapGraph(map_id=2, width=4, height=3, tileset_id=0, blocked=_open_grid(4, 3))
    connection = MapConnection(from_map=1, direction=Direction.SOUTH, offset=2, to_map=2, to_offset=0)

    pairs = crossing_cells(connection, from_graph=from_graph, to_graph=to_graph)

    assert pairs == (
        ((2, 2), (0, 0)),
        ((3, 2), (1, 0)),
    )


def test_crossing_cells_east_negative_offset_partial_overlap():
    # map1's E edge (col width-1=2) meets map2's W edge (col 0). offset=0,
    # to_offset=3 -> shift=-3 -> y_to = y_from + 3, so only y_from=0 lands in
    # map2's height-4 grid (y_to=3).
    from_graph = MapGraph(map_id=1, width=3, height=4, tileset_id=0, blocked=_open_grid(3, 4))
    to_graph = MapGraph(map_id=2, width=3, height=4, tileset_id=0, blocked=_open_grid(3, 4))
    connection = MapConnection(from_map=1, direction=Direction.EAST, offset=0, to_map=2, to_offset=3)

    pairs = crossing_cells(connection, from_graph=from_graph, to_graph=to_graph)

    assert pairs == (((2, 0), (0, 3)),)


def test_crossing_cells_west_zero_offset_full_overlap():
    # map1's W edge (col 0) meets map2's E edge (col width-1=1).
    from_graph = MapGraph(map_id=1, width=2, height=3, tileset_id=0, blocked=_open_grid(2, 3))
    to_graph = MapGraph(map_id=2, width=2, height=3, tileset_id=0, blocked=_open_grid(2, 3))
    connection = MapConnection(from_map=1, direction=Direction.WEST, offset=0, to_map=2, to_offset=0)

    pairs = crossing_cells(connection, from_graph=from_graph, to_graph=to_graph)

    assert pairs == (
        ((0, 0), (1, 0)),
        ((0, 1), (1, 1)),
        ((0, 2), (1, 2)),
    )


def test_crossing_cells_filters_out_walled_cells_on_either_side():
    from_graph = MapGraph(
        map_id=1, width=3, height=2, tileset_id=0,
        blocked=_walled_grid(3, 2, {(1, 0)}),  # x_from=1 walled on the FROM side
    )
    to_graph = MapGraph(
        map_id=2, width=3, height=2, tileset_id=0,
        blocked=_walled_grid(3, 2, {(2, 1)}),  # x_to=2 (x_from=2) walled on the TO side
    )
    connection = MapConnection(from_map=1, direction=Direction.NORTH, offset=0, to_map=2, to_offset=0)

    pairs = crossing_cells(connection, from_graph=from_graph, to_graph=to_graph)

    assert pairs == (((0, 0), (0, 1)),)


def test_crossing_cells_all_walled_returns_empty_not_raise():
    # The edge genuinely overlaps (shift=0), but every cell along it is
    # walled on the FROM side -- that's "no walkable pair," not a geometry
    # mismatch, so crossing_cells reports it as an empty result, not a raise.
    from_graph = MapGraph(
        map_id=1, width=2, height=2, tileset_id=0,
        blocked=_walled_grid(2, 2, {(0, 0), (1, 0)}),
    )
    to_graph = MapGraph(map_id=2, width=2, height=2, tileset_id=0, blocked=_open_grid(2, 2))
    connection = MapConnection(from_map=1, direction=Direction.NORTH, offset=0, to_map=2, to_offset=0)

    assert crossing_cells(connection, from_graph=from_graph, to_graph=to_graph) == ()


def test_crossing_cells_raises_when_edges_do_not_overlap_at_all():
    # shift so large no x_from ever maps into to_graph's width -- a genuine
    # geometry mismatch (bad data), distinct from "no walkable pair."
    from_graph = MapGraph(map_id=1, width=2, height=2, tileset_id=0, blocked=_open_grid(2, 2))
    to_graph = MapGraph(map_id=2, width=2, height=2, tileset_id=0, blocked=_open_grid(2, 2))
    connection = MapConnection(from_map=1, direction=Direction.NORTH, offset=100, to_map=2, to_offset=0)

    with pytest.raises(ValueError, match="do not share any overlapping edge cell"):
        crossing_cells(connection, from_graph=from_graph, to_graph=to_graph)


def test_crossing_cells_rejects_mismatched_graphs():
    from_graph = MapGraph(map_id=1, width=2, height=2, tileset_id=0, blocked=_open_grid(2, 2))
    to_graph = MapGraph(map_id=2, width=2, height=2, tileset_id=0, blocked=_open_grid(2, 2))
    connection = MapConnection(from_map=9, direction=Direction.NORTH, offset=0, to_map=2, to_offset=0)

    with pytest.raises(ValueError, match="from_graph is map 1"):
        crossing_cells(connection, from_graph=from_graph, to_graph=to_graph)


# ---------------------------------------------------------------------------
# connections_between
# ---------------------------------------------------------------------------


def test_connections_between_filters_by_direction_and_sorts():
    connections = (
        MapConnection(from_map=1, direction=Direction.NORTH, offset=5, to_map=2, to_offset=0),
        MapConnection(from_map=2, direction=Direction.SOUTH, offset=0, to_map=1, to_offset=5),
        MapConnection(from_map=1, direction=Direction.EAST, offset=0, to_map=3, to_offset=0),
    )

    result = connections_between(connections, 1, 2)

    assert result == (connections[0],)
    assert connections_between(connections, 2, 1) == (connections[1],)
    assert connections_between(connections, 1, 3) == (connections[2],)
    assert connections_between(connections, 3, 1) == ()


# ---------------------------------------------------------------------------
# plan_segment integration
# ---------------------------------------------------------------------------


def test_plan_segment_connection_hop_produces_two_legs_with_crossing_recorded():
    graph1 = MapGraph(map_id=1, width=3, height=2, tileset_id=0, blocked=_open_grid(3, 2))
    graph2 = MapGraph(map_id=2, width=3, height=2, tileset_id=0, blocked=_open_grid(3, 2))
    world = _world([
        WorldEdge(src_map=1, dst_map=2, kind="connection", src_cell=None, dst_cell=None),
    ])
    connections = (
        MapConnection(from_map=1, direction=Direction.NORTH, offset=0, to_map=2, to_offset=0),
        MapConnection(from_map=2, direction=Direction.SOUTH, offset=0, to_map=1, to_offset=0),
    )

    result = plan_segment(
        1, (0, 1), 2, (0, 0),
        graphs={1: graph1, 2: graph2},
        overlays={1: _empty_overlay(1), 2: _empty_overlay(2)},
        destination_scripts=frozenset(),
        world=world, connections=connections,
    )

    assert len(result.legs) == 2
    first, second = result.legs
    assert first.map_id == 1
    assert first.tiles[0] == (0, 1)
    assert first.tiles[-1] == (0, 0)  # nearest walkable exit cell to (0, 0)
    assert first.exit_warp is not None
    assert first.exit_warp.event_id is None  # a connection has no originating event
    assert first.exit_warp.dest_map == 2
    assert first.exit_warp.dest_cell == (0, 1)  # entry cell on map2's S edge (height-1=1)

    assert second.map_id == 2
    assert second.tiles[0] == (0, 1)
    assert second.tiles[-1] == (0, 0)
    assert second.exit_warp is None
    assert result.crossings == ()


def test_plan_segment_connection_hop_raises_when_no_connection_data():
    graph1 = MapGraph(map_id=1, width=3, height=2, tileset_id=0, blocked=_open_grid(3, 2))
    graph2 = MapGraph(map_id=2, width=3, height=2, tileset_id=0, blocked=_open_grid(3, 2))
    world = _world([
        WorldEdge(src_map=1, dst_map=2, kind="connection", src_cell=None, dst_cell=None),
    ])

    with pytest.raises(RoutePlanningError, match="no connections.json row"):
        plan_segment(
            1, (0, 1), 2, (0, 0),
            graphs={1: graph1, 2: graph2},
            overlays={1: _empty_overlay(1), 2: _empty_overlay(2)},
            destination_scripts=frozenset(),
            world=world, connections=(),
        )


def test_plan_segment_connection_hop_raises_specific_message_when_all_walled():
    graph1 = MapGraph(
        map_id=1, width=2, height=2, tileset_id=0,
        blocked=_walled_grid(2, 2, {(0, 0), (1, 0)}),  # entire N edge walled
    )
    graph2 = MapGraph(map_id=2, width=2, height=2, tileset_id=0, blocked=_open_grid(2, 2))
    world = _world([
        WorldEdge(src_map=1, dst_map=2, kind="connection", src_cell=None, dst_cell=None),
    ])
    connections = (
        MapConnection(from_map=1, direction=Direction.NORTH, offset=0, to_map=2, to_offset=0),
        MapConnection(from_map=2, direction=Direction.SOUTH, offset=0, to_map=1, to_offset=0),
    )

    with pytest.raises(RoutePlanningError, match=r"map 1 <-> map 2 \(NORTH connection\)"):
        plan_segment(
            1, (0, 1), 2, (0, 0),
            graphs={1: graph1, 2: graph2},
            overlays={1: _empty_overlay(1), 2: _empty_overlay(2)},
            destination_scripts=frozenset(),
            world=world, connections=connections,
        )


def test_plan_segment_connection_crossing_does_not_bypass_foreign_trigger_avoid_set():
    # A single-file column x=1 is the only walkable crossing cell to map2 (x=0
    # and x=2 are walled off the top row, so `crossing_cells` never offers
    # them as candidates). The foreign trigger sits on an INTERMEDIATE cell of
    # that column, (1, 1) -- not the exit cell itself -- so the only way to
    # reach the connection at all is to step on it. Proves the connection
    # path doesn't get a free pass around the same avoid-set/fallback logic
    # every other leg goes through.
    walls = {(0, 0), (2, 0), (0, 1), (2, 1), (0, 2), (2, 2)}
    graph1 = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_walled_grid(3, 3, walls))
    graph2 = MapGraph(map_id=2, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    world = _world([
        WorldEdge(src_map=1, dst_map=2, kind="connection", src_cell=None, dst_cell=None),
    ])
    connections = (
        MapConnection(from_map=1, direction=Direction.NORTH, offset=0, to_map=2, to_offset=0),
        MapConnection(from_map=2, direction=Direction.SOUTH, offset=0, to_map=1, to_offset=0),
    )
    overlay1 = TriggerOverlay(
        map_id=1, tiles={(1, 1): [_coord_ref("map099/someone_elses_event")]},
    )

    result = plan_segment(
        1, (1, 2), 2, (1, 2),
        graphs={1: graph1, 2: graph2},
        overlays={1: overlay1, 2: _empty_overlay(2)},
        destination_scripts=frozenset({"map001/nothing_here"}),  # not the foreign script
        world=world, connections=connections,
    )

    assert result.legs[0].tiles == ((1, 2), (1, 1), (1, 0))
    assert len(result.crossings) == 1
    crossing = result.crossings[0]
    assert crossing.map_id == 1
    assert crossing.cell == (1, 1)
    assert crossing.script == "map099/someone_elses_event"


def test_plan_segment_connection_crossing_picks_cheapest_candidate():
    # Two walkable crossing cells, (0, 0) and (2, 0); (2, 0) is reachable in
    # one step from the start, (0, 0) only in two. The cheaper one must win.
    walls = {(1, 0)}  # keep the two candidates from being adjacent to each other
    graph1 = MapGraph(map_id=1, width=3, height=2, tileset_id=0, blocked=_walled_grid(3, 2, walls))
    graph2 = MapGraph(map_id=2, width=3, height=2, tileset_id=0, blocked=_open_grid(3, 2))
    world = _world([
        WorldEdge(src_map=1, dst_map=2, kind="connection", src_cell=None, dst_cell=None),
    ])
    connections = (
        MapConnection(from_map=1, direction=Direction.NORTH, offset=0, to_map=2, to_offset=0),
        MapConnection(from_map=2, direction=Direction.SOUTH, offset=0, to_map=1, to_offset=0),
    )

    result = plan_segment(
        1, (2, 1), 2, (2, 1),
        graphs={1: graph1, 2: graph2},
        overlays={1: _empty_overlay(1), 2: _empty_overlay(2)},
        destination_scripts=frozenset(),
        world=world, connections=connections,
    )

    assert result.legs[0].tiles == ((2, 1), (2, 0))
    assert result.legs[0].exit_warp.dest_cell == (2, 1)
