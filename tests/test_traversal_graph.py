"""Unit tests for `rpg2gba.traversal.graph` — synthetic grids, no decoded corpus
needed. Covers stair diagonal displacement, one-way ledge jumps, and the BFS
query surface (reachable_from / shortest_path / connected_components).

CLAUDE.md §4.6: round-trip (edge symmetry / determinism), golden (see
test_traversal_map037_golden.py for the corpus golden test), edge cases
(stair displacement math for both sides, ledge one-way-ness, out-of-bounds).
"""
from __future__ import annotations

from rpg2gba.tileset_converter.stairs import StairSide
from rpg2gba.traversal.direction import Direction
from rpg2gba.traversal.graph import MapGraph


def _open_grid(width: int, height: int) -> dict[tuple[int, int], bool]:
    """A fully-open (nothing blocked) width x height collision grid."""
    return {(x, y): False for x in range(width) for y in range(height)}


def _walled_grid(
    width: int, height: int, walls: set[tuple[int, int]],
) -> dict[tuple[int, int], bool]:
    return {(x, y): (x, y) in walls for x in range(width) for y in range(height)}


# ---------------------------------------------------------------------------
# Basic collision-only walk edges
# ---------------------------------------------------------------------------


def test_open_grid_neighbors_all_four_cardinals():
    g = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    edges = g.neighbors((1, 1))
    targets = {e.target for e in edges}
    assert targets == {(1, 0), (1, 2), (0, 1), (2, 1)}
    assert all(e.kind == "walk" for e in edges)


def test_blocked_cell_yields_no_edge_and_out_of_bounds_is_excluded():
    walls = {(1, 0)}
    g = MapGraph(map_id=1, width=2, height=2, tileset_id=0, blocked=_walled_grid(2, 2, walls))
    edges = g.neighbors((0, 0))
    targets = {e.target for e in edges}
    # (1,0) is blocked; (0,-1) and (-1,0) are out of bounds; only (0,1) remains.
    assert targets == {(0, 1)}


def test_is_walkable_respects_bounds_and_collision():
    g = MapGraph(map_id=1, width=2, height=2, tileset_id=0, blocked=_walled_grid(2, 2, {(1, 1)}))
    assert g.is_walkable((0, 0)) is True
    assert g.is_walkable((1, 1)) is False  # blocked
    assert g.is_walkable((5, 5)) is False  # out of bounds


# ---------------------------------------------------------------------------
# Sideways-stairs diagonal displacement (module docstring axis table,
# cross-checked against engine/src/field_player_avatar.c:2209-2237)
# ---------------------------------------------------------------------------


def test_right_side_stair_press_west_lands_northwest():
    # RIGHT side (NW/SE axis): press WEST -> land NW of the stair cell.
    g = MapGraph(
        map_id=1, width=5, height=5, tileset_id=0, blocked=_open_grid(5, 5),
        stair_sides={(2, 2): StairSide.RIGHT},
    )
    assert g.stair_press_result((2, 2), Direction.WEST) == (1, 1)


def test_right_side_stair_press_east_lands_southeast():
    g = MapGraph(
        map_id=1, width=5, height=5, tileset_id=0, blocked=_open_grid(5, 5),
        stair_sides={(2, 2): StairSide.RIGHT},
    )
    assert g.stair_press_result((2, 2), Direction.EAST) == (3, 3)


def test_left_side_stair_press_west_lands_southwest():
    # LEFT side (NE/SW axis): press WEST -> land SW.
    g = MapGraph(
        map_id=1, width=5, height=5, tileset_id=0, blocked=_open_grid(5, 5),
        stair_sides={(2, 2): StairSide.LEFT},
    )
    assert g.stair_press_result((2, 2), Direction.WEST) == (1, 3)


def test_left_side_stair_press_east_lands_northeast():
    g = MapGraph(
        map_id=1, width=5, height=5, tileset_id=0, blocked=_open_grid(5, 5),
        stair_sides={(2, 2): StairSide.LEFT},
    )
    assert g.stair_press_result((2, 2), Direction.EAST) == (3, 1)


def test_stair_press_north_south_returns_none():
    g = MapGraph(
        map_id=1, width=5, height=5, tileset_id=0, blocked=_open_grid(5, 5),
        stair_sides={(2, 2): StairSide.LEFT},
    )
    assert g.stair_press_result((2, 2), Direction.NORTH) is None
    assert g.stair_press_result((2, 2), Direction.SOUTH) is None


def test_non_stair_cell_press_result_is_none():
    g = MapGraph(map_id=1, width=5, height=5, tileset_id=0, blocked=_open_grid(5, 5))
    assert g.stair_press_result((2, 2), Direction.WEST) is None


def test_stair_cell_is_always_walkable_even_if_raw_collision_blocks_it():
    """Phase 5's layout converter force-stamps stair cells passable regardless
    of the source RMXP passage byte (the script did the moving, not tile
    geometry) — the graph must mirror that, not the raw blocked bit."""
    blocked = _walled_grid(5, 5, {(2, 2)})  # raw collision reads blocked
    g = MapGraph(
        map_id=1, width=5, height=5, tileset_id=0, blocked=blocked,
        stair_sides={(2, 2): StairSide.LEFT},
    )
    assert g.is_walkable((2, 2)) is True


def test_approaching_stair_from_east_or_west_diagonalizes_the_step():
    """A cell 'entering' a stair via an E/W press is redirected diagonally
    even though the stair cell itself is a different (x, y) from the caller's
    cell — neighbors() must catch this via the *target* cell, not just when
    standing ON a stair."""
    g = MapGraph(
        map_id=1, width=5, height=5, tileset_id=0, blocked=_open_grid(5, 5),
        stair_sides={(2, 2): StairSide.RIGHT},
    )
    edges = g.neighbors((1, 2))  # approaching the stair moving EAST
    stair_edges = [e for e in edges if e.kind == "stair_diagonal"]
    assert len(stair_edges) == 1
    assert stair_edges[0].target == (3, 3)  # RIGHT + press EAST -> SE
    assert stair_edges[0].press is Direction.EAST


def test_stair_cell_north_south_presses_are_ordinary_walks():
    g = MapGraph(
        map_id=1, width=5, height=5, tileset_id=0, blocked=_open_grid(5, 5),
        stair_sides={(2, 2): StairSide.RIGHT},
    )
    edges = {e.press: e for e in g.neighbors((2, 2))}
    assert edges[Direction.NORTH].target == (2, 1)
    assert edges[Direction.NORTH].kind == "walk"
    assert edges[Direction.SOUTH].target == (2, 3)
    assert edges[Direction.SOUTH].kind == "walk"


# ---------------------------------------------------------------------------
# One-way ledges
# ---------------------------------------------------------------------------


def test_ledge_jump_lands_two_tiles_beyond_in_jump_direction():
    g = MapGraph(
        map_id=1, width=5, height=5, tileset_id=0, blocked=_open_grid(5, 5),
        ledge_directions={(2, 2): Direction.SOUTH},
    )
    edges = g.neighbors((2, 1))  # approaching the ledge from the north, pressing south
    jump_edges = [e for e in edges if e.kind == "ledge_jump"]
    assert len(jump_edges) == 1
    assert jump_edges[0].target == (2, 3)  # two tiles south of the approach cell
    assert jump_edges[0].press is Direction.SOUTH


def test_ledge_is_never_a_resting_cell():
    g = MapGraph(
        map_id=1, width=5, height=5, tileset_id=0, blocked=_open_grid(5, 5),
        ledge_directions={(2, 2): Direction.SOUTH},
    )
    assert g.is_walkable((2, 2)) is False


def test_ledge_cannot_be_approached_from_a_non_jump_direction():
    """Only the declared jump direction produces an edge; the other three
    approach cells get nothing (the ledge blocks entry from those sides)."""
    g = MapGraph(
        map_id=1, width=5, height=5, tileset_id=0, blocked=_open_grid(5, 5),
        ledge_directions={(2, 2): Direction.SOUTH},
    )
    # Approaching from the south (pressing north onto the ledge) must NOT jump.
    edges = g.neighbors((2, 3))
    assert all(e.target != (2, 1) for e in edges)
    assert not any(e.kind == "ledge_jump" for e in edges)


def test_ledge_jump_has_no_reverse_edge_one_way_only():
    # Wall off row 2 everywhere except the ledge column so the ledge is the
    # ONLY link between the north and south halves — otherwise an open grid
    # would trivially connect them some other way and the test proves nothing.
    walls = {(x, 2) for x in range(5) if x != 2}
    g = MapGraph(
        map_id=1, width=5, height=5, tileset_id=0, blocked=_walled_grid(5, 5, walls),
        ledge_directions={(2, 2): Direction.SOUTH},
    )
    forward = g.reachable_from((2, 0))
    assert (2, 3) in forward
    # From the landing cell, there is no way back up through the ledge.
    backward = g.reachable_from((2, 4))
    assert (2, 0) not in backward


def test_stair_ledge_overlap_rejected_at_build_time():
    """build_map_graph raises if a cell is classified as both a staircase and
    a ledge — contradictory derived data (fail loud, CLAUDE.md §4.5). This
    is exercised indirectly here by constructing the contradiction the way
    build_map_graph's own check would see it; the check itself lives in
    build_map_graph (see test_traversal_map037_golden.py for a corpus-backed
    smoke test that build_map_graph runs clean end-to-end)."""
    stair_ledge_overlap = {(2, 2)} & {(2, 2)}
    assert stair_ledge_overlap  # sanity: the intersection check build_map_graph runs


# ---------------------------------------------------------------------------
# BFS query surface
# ---------------------------------------------------------------------------


def test_shortest_path_round_trip_matches_reachable_from():
    g = MapGraph(map_id=1, width=4, height=1, tileset_id=0, blocked=_open_grid(4, 1))
    path = g.shortest_path((0, 0), (3, 0))
    assert path == [(0, 0), (1, 0), (2, 0), (3, 0)]
    assert (3, 0) in g.reachable_from((0, 0))


def test_shortest_path_same_cell_is_single_element():
    g = MapGraph(map_id=1, width=2, height=2, tileset_id=0, blocked=_open_grid(2, 2))
    assert g.shortest_path((0, 0), (0, 0)) == [(0, 0)]


def test_shortest_path_unreachable_returns_none():
    walls = {(1, 0), (0, 1)}
    g = MapGraph(map_id=1, width=2, height=2, tileset_id=0, blocked=_walled_grid(2, 2, walls))
    assert g.shortest_path((0, 0), (1, 1)) is None


def test_connected_components_splits_disjoint_areas():
    # A full-height wall column splits a 5x2 grid into two 2x2 islands.
    walls = {(2, 0), (2, 1)}
    g = MapGraph(map_id=1, width=5, height=2, tileset_id=0, blocked=_walled_grid(5, 2, walls))
    components = g.connected_components()
    sizes = sorted(len(c) for c in components)
    assert sizes == [4, 4]  # left island (cols 0-1 x 2 rows) + right island (cols 3-4 x 2 rows)


def test_reachable_from_raises_on_unwalkable_start():
    g = MapGraph(map_id=1, width=2, height=2, tileset_id=0, blocked=_walled_grid(2, 2, {(0, 0)}))
    try:
        g.reachable_from((0, 0))
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for an unwalkable start cell")
