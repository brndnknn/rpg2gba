"""Tests for `rpg2gba.beat_gen.reach.reachable_sites` (C6 part two)."""
from __future__ import annotations

from rpg2gba.beat_gen.reach import reachable_sites
from rpg2gba.routing.occupancy import MapOccupancy, OccupiedTile
from rpg2gba.traversal.graph import MapGraph
from rpg2gba.traversal.warps import WarpExit
from rpg2gba.traversal.world import WorldEdge, WorldGraph


def _open_grid(
    width: int, height: int, walls: frozenset[tuple[int, int]] = frozenset(),
) -> dict[tuple[int, int], bool]:
    return {(x, y): (x, y) in walls for x in range(width) for y in range(height)}


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


def _warp(cell: tuple[int, int], dest_map: int, dest_cell: tuple[int, int]) -> WarpExit:
    return WarpExit(
        cell=cell, event_id=1, dest_map=dest_map,
        dest_x=dest_cell[0], dest_y=dest_cell[1], dest_facing=0,
    )


def test_walking_within_a_map_reaches_every_open_cell():
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))

    sites = reachable_sites((1, (0, 0)), {1: graph}, _world([]), frozenset({1}))

    assert sites == frozenset({(1, (x, y)) for x in range(3) for y in range(3)})


def test_crossing_a_walkable_warp_tile_opens_the_destination_map():
    graph1 = MapGraph(
        map_id=1, width=3, height=3, tileset_id=0,
        blocked=_open_grid(3, 3),
        warp_exits={(2, 1): [_warp((2, 1), 2, (0, 0))]},
    )
    graph2 = MapGraph(map_id=2, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))

    sites = reachable_sites(
        (1, (0, 1)), {1: graph1, 2: graph2}, _world([]), frozenset({1, 2}),
    )

    assert (2, (0, 0)) in sites
    # From the landing cell, the rest of map 2 opens up too.
    assert (2, (2, 2)) in sites


def test_pressing_into_a_solid_warp_tile_opens_the_destination_map():
    graph1 = MapGraph(
        map_id=1, width=3, height=3, tileset_id=0,
        blocked=_open_grid(3, 3, walls=frozenset({(2, 2)})),
        warp_exits={(2, 2): [_warp((2, 2), 2, (1, 1))]},
    )
    graph2 = MapGraph(map_id=2, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))

    sites = reachable_sites(
        (1, (0, 0)), {1: graph1, 2: graph2}, _world([]), frozenset({1, 2}),
    )

    assert (2, (1, 1)) in sites
    assert (1, (2, 2)) not in sites  # the solid tile itself is never stood on


def test_map_outside_maps_is_never_entered():
    graph1 = MapGraph(
        map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3),
        warp_exits={(2, 1): [_warp((2, 1), 4, (0, 0))]},
    )

    sites = reachable_sites((1, (0, 1)), {1: graph1}, _world([]), frozenset({1}))

    assert not any(site[0] == 4 for site in sites)


def test_stationary_npc_tile_in_occupancy_is_a_wall():
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    occupancy = MapOccupancy(
        map_id=1,
        tiles=(OccupiedTile(cell=(1, 1), script="map001/npc",
                             movement_type="MOVEMENT_TYPE_FACE_DOWN"),),
    )

    sites = reachable_sites(
        (1, (0, 1)), {1: graph}, _world([]), frozenset({1}), occupancy={1: occupancy},
    )

    assert (1, (1, 1)) not in sites
    assert (1, (2, 1)) in sites  # geography still open around it


def test_seam_warp_edge_crosses_to_the_other_map():
    graph1 = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    graph2 = MapGraph(map_id=2, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    world = _world([
        WorldEdge(src_map=1, dst_map=2, kind="seam_warp",
                  src_cell=(2, 1), dst_cell=(0, 1), event_id=None),
    ])

    sites = reachable_sites(
        (1, (0, 1)), {1: graph1, 2: graph2}, world, frozenset({1, 2}),
    )

    assert (2, (0, 1)) in sites
