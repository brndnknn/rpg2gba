"""Tests for `rpg2gba.routing.pathing`'s solid-warp-tile handling
(`_path_on_map` / `_path_into_solid_warp`) -- C6 part two (2), CH01.

A goal that is a SOLID (non-walkable) tile carrying a warp exit (a
building's exit mat) must be reached by pressing into it from a walkable
orthogonal neighbour, since the tile itself can never be stepped on.
"""
from __future__ import annotations

import pytest

from rpg2gba.routing.pathing import RoutePlanningError, _path_into_solid_warp, _path_on_map
from rpg2gba.traversal.graph import MapGraph
from rpg2gba.traversal.triggers import TriggerOverlay
from rpg2gba.traversal.warps import WarpExit


def _empty_overlay(map_id: int) -> TriggerOverlay:
    return TriggerOverlay(map_id=map_id, tiles={})


def _warp_exit(cell: tuple[int, int]) -> WarpExit:
    return WarpExit(cell=cell, event_id=1, dest_map=99, dest_x=0, dest_y=0, dest_facing=0)


def _grid(width: int, height: int, open_cells: set[tuple[int, int]]) -> dict[tuple[int, int], bool]:
    """blocked=True everywhere except `open_cells`."""
    return {
        (x, y): (x, y) not in open_cells
        for x in range(width) for y in range(height)
    }


def test_solid_warp_goal_reached_via_walkable_neighbour_and_path_ends_on_warp_cell():
    # 3x3 grid; (1,1) is solid but carries a warp exit. Only its north
    # neighbour (1,0) is open, and it's also the start -- so the whole path
    # is the direct press onto the warp cell.
    goal = (1, 1)
    graph = MapGraph(
        map_id=1, width=3, height=3, tileset_id=0,
        blocked=_grid(3, 3, {(1, 0), goal}),
        warp_exits={goal: [_warp_exit(goal)]},
    )
    overlay = _empty_overlay(1)

    path, crossings = _path_on_map(
        1, (1, 0), goal, graph=graph, overlay=overlay,
        destination_scripts=frozenset(), occupancy=None,
    )

    assert path == [(1, 0), goal]
    assert crossings == ()


def test_solid_warp_goal_with_two_open_sides_shorter_path_wins():
    # 5x5 grid; (2,2) is solid+warp. Its north neighbour (2,1) is the start
    # (0 extra steps); its south neighbour (2,3) is reachable only via a
    # 6-step detour around the east side. East/west neighbours are blocked
    # outright (not walkable), so only north and south are candidates, and
    # north -- the shorter one -- must win.
    goal = (2, 2)
    open_cells = {
        (2, 1),                     # start / north side
        (3, 1), (4, 1), (4, 2), (4, 3), (3, 3),
        (2, 3),                     # south side, via the detour above
        goal,
    }
    graph = MapGraph(
        map_id=1, width=5, height=5, tileset_id=0,
        blocked=_grid(5, 5, open_cells),
        warp_exits={goal: [_warp_exit(goal)]},
    )
    overlay = _empty_overlay(1)

    path, crossings = _path_into_solid_warp(
        1, (2, 1), goal, graph=graph, overlay=overlay,
        destination_scripts=frozenset(), occupancy=None,
    )

    assert path == [(2, 1), goal]
    assert crossings == ()


def test_solid_warp_goal_with_no_reachable_side_raises():
    goal = (1, 1)
    graph = MapGraph(
        map_id=1, width=3, height=3, tileset_id=0,
        blocked=_grid(3, 3, {(0, 0), goal}),  # only the goal itself is open besides start
        warp_exits={goal: [_warp_exit(goal)]},
    )
    overlay = _empty_overlay(1)

    with pytest.raises(RoutePlanningError, match="no reachable walkable side"):
        _path_into_solid_warp(
            1, (0, 0), goal, graph=graph, overlay=overlay,
            destination_scripts=frozenset(), occupancy=None,
        )


def test_path_on_map_delegates_to_solid_warp_helper():
    # Sanity: `_path_on_map` itself (not just the helper) recognizes a solid
    # warp-exit goal and routes through it, rather than treating it as a
    # plain unreachable cell.
    goal = (1, 1)
    graph = MapGraph(
        map_id=1, width=3, height=3, tileset_id=0,
        blocked=_grid(3, 3, {(1, 0), goal}),
        warp_exits={goal: [_warp_exit(goal)]},
    )
    overlay = _empty_overlay(1)

    path, crossings = _path_on_map(
        1, (1, 0), goal, graph=graph, overlay=overlay,
        destination_scripts=frozenset(), occupancy=None,
    )

    assert path[-1] == goal
    assert crossings == ()
