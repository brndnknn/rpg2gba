"""Tests for `rpg2gba.traversal.reachability`.

Synthetic `MapGraph`/`CapabilityMap` fixtures exercise the two inverted
obstacle routes (CLAUDE.md §4.6: edge cases for both directions), the
subset-search minimality/determinism guarantees, and the unverified-
capability guard. One golden test replays real corpus map 35 (Route 2) to
confirm the known rock-obstacle cells classify correctly and the derivation
runs end to end without raising — it deliberately does not assert an
expected verdict for the northern region (that validation belongs to the
lead's own frozen-oracle check, per the task brief)."""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.traversal.capabilities import (
    Capability,
    CapabilityMap,
    Obstacle,
    UnverifiedCapabilityError,
    build_capability_map,
)
from rpg2gba.traversal.graph import MapGraph, build_map_graph
from rpg2gba.traversal.reachability import (
    BlockedVerdict,
    PermanentlyUnstandableGoalError,
    adjacent_approach_cells,
    derive_blocked_verdict,
    derive_blocked_verdict_for_event,
    is_reachable_with,
    minimal_capability_sets,
    reachable_with,
)

MAPS_DIR = Path("output/uranium-build/maps")
TILESETS_JSON = Path("output/uranium-build/tilesets.json")
CORPUS_PRESENT = MAPS_DIR.is_dir() and TILESETS_JSON.is_file()

requires_corpus = pytest.mark.skipif(
    not CORPUS_PRESENT,
    reason="requires the decoded corpus under output/uranium-build/ (run the pipeline first)",
)


def _open_grid(width: int, height: int) -> dict[tuple[int, int], bool]:
    return {(x, y): False for x in range(width) for y in range(height)}


def _walled_grid(
    width: int, height: int, walls: set[tuple[int, int]],
) -> dict[tuple[int, int], bool]:
    return {(x, y): (x, y) in walls for x in range(width) for y in range(height)}


def _cap_map(map_id: int, obstacles: dict[tuple[int, int], Obstacle]) -> CapabilityMap:
    return CapabilityMap(map_id=map_id, obstacles=obstacles)


def _event_obstacle(cell: tuple[int, int], capability: Capability) -> Obstacle:
    return Obstacle(cell=cell, capability=capability, source="event", detail="1:Rock", event_id=1)


def _terrain_obstacle(cell: tuple[int, int], capability: Capability) -> Obstacle:
    return Obstacle(cell=cell, capability=capability, source="terrain", detail="7", event_id=None)


# ---------------------------------------------------------------------------
# Event obstacle: graph-walkable cell must be treated as blocked without S
# ---------------------------------------------------------------------------


def test_event_obstacle_blocks_a_graph_walkable_corridor():
    """A rock sits on a tile plain collision reports walkable. Without
    ROCK_SMASH the corridor is blocked; with it, open."""
    # 3-wide corridor, single-file column x=1 is the only path, blocked by a
    # rock at (1,1) that collision alone does not know about.
    walls = {(0, 1), (2, 1)}
    graph = MapGraph(
        map_id=1, width=3, height=3, tileset_id=0, blocked=_walled_grid(3, 3, walls),
    )
    cap_map = _cap_map(1, {(1, 1): _event_obstacle((1, 1), Capability.ROCK_SMASH)})

    assert (1, 2) not in reachable_with(graph, cap_map, (1, 0))
    assert (1, 2) in reachable_with(graph, cap_map, (1, 0), frozenset({Capability.ROCK_SMASH}))


# ---------------------------------------------------------------------------
# Terrain obstacle: graph-blocked cell must open up with S
# ---------------------------------------------------------------------------


def test_terrain_obstacle_blocks_until_surf_held():
    """Water at (1,1) is already blocked in raw collision (mirrors real
    terrain-tag-derived collision). SURF opens the crossing."""
    walls = {(0, 1), (1, 1), (2, 1)}
    graph = MapGraph(
        map_id=1, width=3, height=3, tileset_id=0, blocked=_walled_grid(3, 3, walls),
    )
    cap_map = _cap_map(1, {(1, 1): _terrain_obstacle((1, 1), Capability.SURF)})

    assert (1, 2) not in reachable_with(graph, cap_map, (1, 0))
    assert (1, 2) in reachable_with(graph, cap_map, (1, 0), frozenset({Capability.SURF}))


# ---------------------------------------------------------------------------
# Minimal-set combinations
# ---------------------------------------------------------------------------


def test_needing_both_a_rock_and_water_crossing_yields_one_minimal_set():
    # Column x=1 is the only path: (1,1) is a rock (event, graph-walkable),
    # (1,2) is water (terrain, graph-blocked). Both must be held.
    walls = {(0, 1), (2, 1), (0, 2), (1, 2), (2, 2)}
    graph = MapGraph(
        map_id=1, width=3, height=4, tileset_id=0, blocked=_walled_grid(3, 4, walls),
    )
    cap_map = _cap_map(1, {
        (1, 1): _event_obstacle((1, 1), Capability.ROCK_SMASH),
        (1, 2): _terrain_obstacle((1, 2), Capability.SURF),
    })

    sets = minimal_capability_sets(graph, cap_map, (1, 0), (1, 3))
    assert sets == [frozenset({Capability.ROCK_SMASH, Capability.SURF})]


def test_two_independent_alternative_routes_yield_two_minimal_sets():
    # Open top row (y=0) and open bottom row (y=2), joined only through a
    # middle row (y=1) that is walled everywhere except two gated cells: a
    # rock at x=1 and water at x=3. Each gate independently opens a route
    # from the shared top row down to the shared bottom row and the goal.
    #   x: 0 1 2 3 4
    # y0:  .  .  .  .  .
    # y1:  #  R  #  W  #
    # y2:  .  .  .  .  .
    walls = {(0, 1), (2, 1), (3, 1), (4, 1)}  # (3,1) is the water cell itself
    graph = MapGraph(
        map_id=1, width=5, height=3, tileset_id=0, blocked=_walled_grid(5, 3, walls),
    )
    cap_map = _cap_map(1, {
        (1, 1): _event_obstacle((1, 1), Capability.ROCK_SMASH),
        (3, 1): _terrain_obstacle((3, 1), Capability.SURF),
    })

    sets = minimal_capability_sets(graph, cap_map, (0, 0), (2, 2))
    assert sets == [frozenset({Capability.ROCK_SMASH}), frozenset({Capability.SURF})]


def test_minimality_a_working_superset_is_not_returned():
    walls = {(0, 1), (2, 1)}
    graph = MapGraph(
        map_id=1, width=3, height=3, tileset_id=0, blocked=_walled_grid(3, 3, walls),
    )
    cap_map = _cap_map(1, {(1, 1): _event_obstacle((1, 1), Capability.ROCK_SMASH)})

    sets = minimal_capability_sets(graph, cap_map, (1, 0), (1, 2))
    assert sets == [frozenset({Capability.ROCK_SMASH})]
    assert frozenset({Capability.ROCK_SMASH, Capability.STRENGTH}) not in sets


# ---------------------------------------------------------------------------
# Already-reachable / truly unreachable
# ---------------------------------------------------------------------------


def test_already_reachable_goal_returns_empty_frozenset_and_empty_disposition():
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    cap_map = _cap_map(1, {})

    sets = minimal_capability_sets(graph, cap_map, (0, 0), (2, 2))
    assert sets == [frozenset()]

    verdict = derive_blocked_verdict(graph, cap_map, (0, 0), (2, 2))
    assert verdict.reachable_now is True
    assert verdict.minimal_sets == [frozenset()]
    assert verdict.as_disposition() == ""


def test_truly_walled_off_goal_is_unreachable_geography():
    walls = {(x, 1) for x in range(3)}  # a solid wall row, no obstacle involved
    graph = MapGraph(
        map_id=1, width=3, height=3, tileset_id=0, blocked=_walled_grid(3, 3, walls),
    )
    cap_map = _cap_map(1, {})

    sets = minimal_capability_sets(graph, cap_map, (0, 0), (0, 2))
    assert sets == []

    verdict = derive_blocked_verdict(graph, cap_map, (0, 0), (0, 2))
    assert verdict.reachable_now is False
    assert verdict.minimal_sets == []
    assert verdict.as_disposition() == "unreachable:geography"


def test_a_goal_no_capability_can_make_standable_raises_rather_than_answering():
    """CLAUDE.md §4.5. The goal is a wall (or, in the corpus, a solid event's
    own tile): unwalkable, and carrying no capability-tagged obstacle, so no
    capability set makes it standable. The old return value for this shape was
    `unreachable:geography`, which reads as a surveyed map fact while actually
    dropping whatever gate governs the approach -- the CH02 B10 shape."""
    walls = {(1, 1)}
    graph = MapGraph(
        map_id=1, width=3, height=3, tileset_id=0, blocked=_walled_grid(3, 3, walls),
    )
    cap_map = _cap_map(1, {})

    with pytest.raises(PermanentlyUnstandableGoalError, match="derive_blocked_verdict_for_event"):
        derive_blocked_verdict(graph, cap_map, (0, 0), (1, 1))

    # The same cell answers fine as an *event* goal, which is the question a
    # caller looking at a solid event actually has.
    verdict = derive_blocked_verdict_for_event(graph, cap_map, (0, 0), (1, 1))
    assert verdict.reachable_now is True


def test_an_unwalkable_but_capability_tagged_goal_still_answers():
    """Terrain obstacles (water) are unwalkable in the graph by design and are
    the whole point of the capability model -- the guard must not swallow them."""
    graph = MapGraph(
        map_id=1, width=3, height=3, tileset_id=0, blocked=_walled_grid(3, 3, {(1, 1)}),
    )
    cap_map = _cap_map(1, {(1, 1): _terrain_obstacle((1, 1), Capability.SURF)})

    verdict = derive_blocked_verdict(graph, cap_map, (0, 0), (1, 1))
    assert verdict.as_disposition() == "blocked:surf"


def test_blocked_disposition_single_capability():
    walls = {(0, 1), (2, 1)}
    graph = MapGraph(
        map_id=1, width=3, height=3, tileset_id=0, blocked=_walled_grid(3, 3, walls),
    )
    cap_map = _cap_map(1, {(1, 1): _event_obstacle((1, 1), Capability.ROCK_SMASH)})
    verdict = derive_blocked_verdict(graph, cap_map, (1, 0), (1, 2))
    assert verdict.as_disposition() == "blocked:rock_smash"


def test_blocked_disposition_multi_capability():
    # Re-pinned for the "+"-is-AND / "|"-is-OR grammar (2026-09-10): this
    # goal needs BOTH rock_smash and surf (single corridor, one rock then
    # one water crossing), which is an AND within one minimal set --
    # spelled with "+", not "|" (that separates ALTERNATIVE sets now).
    walls = {(0, 1), (2, 1), (0, 2), (1, 2), (2, 2)}
    graph = MapGraph(
        map_id=1, width=3, height=4, tileset_id=0, blocked=_walled_grid(3, 4, walls),
    )
    cap_map = _cap_map(1, {
        (1, 1): _event_obstacle((1, 1), Capability.ROCK_SMASH),
        (1, 2): _terrain_obstacle((1, 2), Capability.SURF),
    })
    verdict = derive_blocked_verdict(graph, cap_map, (1, 0), (1, 3))
    assert verdict.as_disposition() == "blocked:rock_smash+surf"


def test_blocked_disposition_two_alternative_sets():
    # Two independent single-capability routes (the same geometry as
    # `test_two_independent_alternative_routes_yield_two_minimal_sets`):
    # either rock_smash alone or surf alone opens the goal, so the
    # disposition is an OR ("|") of two singleton sets, not an AND.
    walls = {(0, 1), (2, 1), (3, 1), (4, 1)}
    graph = MapGraph(
        map_id=1, width=5, height=3, tileset_id=0, blocked=_walled_grid(5, 3, walls),
    )
    cap_map = _cap_map(1, {
        (1, 1): _event_obstacle((1, 1), Capability.ROCK_SMASH),
        (3, 1): _terrain_obstacle((3, 1), Capability.SURF),
    })
    verdict = derive_blocked_verdict(graph, cap_map, (0, 0), (2, 2))
    assert verdict.as_disposition() == "blocked:rock_smash|surf"


# ---------------------------------------------------------------------------
# Unverified capability guard
# ---------------------------------------------------------------------------


def test_unverified_candidate_raises():
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    cap_map = _cap_map(1, {})
    with pytest.raises(UnverifiedCapabilityError):
        minimal_capability_sets(
            graph, cap_map, (0, 0), (2, 2), candidates=frozenset({Capability.CUT}),
        )
    with pytest.raises(UnverifiedCapabilityError):
        derive_blocked_verdict(
            graph, cap_map, (0, 0), (2, 2), candidates=frozenset({Capability.FLASH}),
        )
    with pytest.raises(UnverifiedCapabilityError):
        derive_blocked_verdict_for_event(
            graph, cap_map, (0, 0), (2, 2), candidates=frozenset({Capability.DIVE}),
        )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_minimal_sets_are_deterministically_ordered_across_repeated_calls():
    walls = {(0, 1), (2, 1), (3, 1), (4, 1)}
    graph = MapGraph(
        map_id=1, width=5, height=3, tileset_id=0, blocked=_walled_grid(5, 3, walls),
    )
    cap_map = _cap_map(1, {
        (1, 1): _event_obstacle((1, 1), Capability.ROCK_SMASH),
        (3, 1): _terrain_obstacle((3, 1), Capability.SURF),
    })

    first = minimal_capability_sets(graph, cap_map, (0, 0), (2, 2))
    for _ in range(5):
        again = minimal_capability_sets(graph, cap_map, (0, 0), (2, 2))
        assert again == first


# ---------------------------------------------------------------------------
# is_reachable_with / adjacent_approach_cells / event verdicts
# ---------------------------------------------------------------------------


def test_is_reachable_with_matches_reachable_with_membership():
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    cap_map = _cap_map(1, {})
    assert is_reachable_with(graph, cap_map, (0, 0), (2, 2)) is True


def test_adjacent_approach_cells_are_the_four_in_bounds_orthogonal_neighbours():
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    cells = adjacent_approach_cells(graph, (0, 0))
    # (0,-1) and (-1,0) are out of bounds; only south and east remain.
    assert set(cells) == {(0, 1), (1, 0)}


def test_derive_blocked_verdict_for_event_reachable_via_any_adjacent_cell():
    """An obstacle event sits at (1,1); the player can only ever reach it
    from the west approach cell (0,1) -- the event tile itself is never a
    resting cell, and the other three approaches are walled off."""
    walls = {(1, 0), (2, 0), (2, 1), (1, 2), (2, 2)}
    graph = MapGraph(
        map_id=1, width=3, height=3, tileset_id=0, blocked=_walled_grid(3, 3, walls),
    )
    cap_map = _cap_map(1, {(1, 1): _event_obstacle((1, 1), Capability.ROCK_SMASH)})

    verdict = derive_blocked_verdict_for_event(graph, cap_map, (0, 0), (1, 1))
    assert verdict.reachable_now is True
    assert verdict.as_disposition() == ""


# ---------------------------------------------------------------------------
# Golden: real map 35 (Route 2)
# ---------------------------------------------------------------------------


@requires_corpus
def test_map35_rock_obstacles_classify_as_event_source_and_derivation_runs_clean():
    graph = build_map_graph(35)
    cap_map = build_capability_map(35)

    expected_rock_cells = {(20, 28), (21, 29), (22, 28), (19, 29), (21, 28)}
    for cell in expected_rock_cells:
        obstacle = cap_map.obstacles.get(cell)
        assert obstacle is not None, f"expected a rock obstacle at {cell}"
        assert obstacle.capability is Capability.ROCK_SMASH
        assert obstacle.source == "event"

    # End-to-end smoke: the derivation must run to completion without
    # raising for a start cell (some walkable cell on the map) and every
    # rock cell as a goal-adjacent event. Do not assert the resulting
    # verdicts here -- that belongs to the lead's own frozen-oracle check.
    start = next(cell for cell in graph.blocked if graph.is_walkable(cell))
    for cell in expected_rock_cells:
        derive_blocked_verdict_for_event(graph, cap_map, start, cell)
