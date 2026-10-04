"""`_route_waypoints` fails loud instead of degrading to a greedy walk.

The planner used to log a warning on a planning failure and return the BARE
TARGET, handing the leg to `_walk_greedy` with none of the planner's
avoid-set. Its docstring justified that as costing "a slower failure rather
than a wrong answer". CH04's B3 is the counterexample: the unprotected greedy
walk crossed Timothy's event-touch tile, the wrong trainer was fought, and
both guards passed -- a wrong answer that every guard waved through.

Two properties are pinned here, and they pull in opposite directions, which
is the whole design:

  * a planning failure must never silently become a bare-target greedy walk;
  * a planning failure must still RECOVER from a transient obstacle, because
    an NPC standing in the only corridor is the common case and `walk_to`'s
    re-plan loop exists to absorb exactly that.

So the failure is raised, and the re-plan loop treats it as a stuck
iteration rather than an instant abort.
"""
from __future__ import annotations

import importlib.util

import pytest

from rpg2gba.playtest.errors import RoutePlanningError, ScenarioError
from rpg2gba.traversal.graph import MapGraph

needs_mgba = pytest.mark.skipif(
    importlib.util.find_spec("mgba") is None,
    reason="importing emulator.py requires the mGBA python bindings")


def _grid_graph(w: int, h: int, blocked: set[tuple[int, int]] = frozenset()) -> MapGraph:
    """A plain walkable rectangle minus `blocked`, built through the real
    `MapGraph` so edge derivation is the production one, not a copy."""
    return MapGraph(
        map_id=37, width=w, height=h, tileset_id=32,
        blocked={(x, y): ((x, y) in blocked)
                 for x in range(w) for y in range(h)},
    )


class _Unroutable:
    """Minimal stand-in: planning always fails, everything else is inert."""

    def __init__(self, graph: MapGraph | None, pos: tuple[int, int] = (0, 0),
                 occupied: set[tuple[int, int]] = frozenset()) -> None:
        self._graph = graph
        self._pos = pos
        self._occupied = set(occupied)

    def player_pos(self) -> tuple[int, int]:
        return self._pos

    def map_location(self) -> tuple[int, int]:
        return (3, 7)

    def _plan_route(self, start, goal):
        return None

    def _occupied_object_tiles(self, goal):
        return self._occupied

    def _current_map_graph(self) -> MapGraph:
        if self._graph is None:
            raise ScenarioError("no graph for this map")
        return self._graph

    def _diagnose_unroutable(self, start, goal):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._diagnose_unroutable(self, start, goal)

    def _route_waypoints(self, tx, ty):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._route_waypoints(self, tx, ty)


@needs_mgba
def test_planning_failure_raises_instead_of_returning_the_bare_target() -> None:
    """The regression that matters: no bare-target degrade, ever.

    A returned `[(tx, ty)]` here is B3 waiting to happen again.
    """
    emu = _Unroutable(_grid_graph(4, 4))
    with pytest.raises(RoutePlanningError):
        emu._route_waypoints(3, 3)


@needs_mgba
def test_unreachable_goal_is_diagnosed_as_permanent() -> None:
    """A goal in a different component: waiting can never help, and the
    message says so rather than leaving the reader to find out by retrying.
    """
    # A full-height wall at x=2 seals (3, y) off from (0, 0).
    graph = _grid_graph(4, 4, blocked={(2, y) for y in range(4)})
    emu = _Unroutable(graph)
    with pytest.raises(RoutePlanningError) as exc:
        emu._route_waypoints(3, 3)
    assert "PERMANENT" in str(exc.value)
    assert "NOT reachable" in str(exc.value)


@needs_mgba
def test_blocked_goal_cell_is_diagnosed_as_permanent() -> None:
    """A goal that is not a walkable cell at all -- the v1 finding-E shape,
    a declared coordinate sitting inside terrain."""
    emu = _Unroutable(_grid_graph(4, 4, blocked={(3, 3)}))
    with pytest.raises(RoutePlanningError) as exc:
        emu._route_waypoints(3, 3)
    assert "PERMANENT" in str(exc.value)
    assert "not a walkable cell" in str(exc.value)


@needs_mgba
def test_reachable_goal_is_diagnosed_as_transient() -> None:
    """Static terrain reaches the goal, so something dynamic blocked
    planning -- the case the re-plan loop is meant to absorb. Naming it
    TRANSIENT is what tells a reader to look for an NPC, not a bad
    coordinate."""
    emu = _Unroutable(_grid_graph(4, 4), occupied={(1, 0), (2, 0)})
    with pytest.raises(RoutePlanningError) as exc:
        emu._route_waypoints(3, 3)
    msg = str(exc.value)
    assert "TRANSIENT" in msg
    assert "(1, 0)" in msg  # the object-held tiles are named


@needs_mgba
def test_diagnosis_never_masks_the_failure_when_the_graph_is_unavailable() -> None:
    """The diagnosis runs on the failure path, so it must not raise on top of
    the failure it describes. A missing graph degrades the MESSAGE, not the
    raise."""
    emu = _Unroutable(None)
    with pytest.raises(RoutePlanningError) as exc:
        emu._route_waypoints(3, 3)
    assert "offline graph: unavailable" in str(exc.value)


@needs_mgba
def test_replan_loop_recovers_when_a_transient_blocker_clears() -> None:
    """A planning failure is a stuck iteration, not an instant abort.

    This is the property that keeps the fail-loud from being too strict: the
    first plan fails (an NPC in the corridor), the loop waits, the second
    plan succeeds, and the walk completes. Without this, every patrolling NPC
    becomes a red beat.
    """
    from rpg2gba.playtest.emulator import _walk_to_once

    class _RecoveringEmu:
        def __init__(self) -> None:
            self.attempts = 0
            self.waited = 0
            self.arrived_at: tuple[int, int] | None = None

        def wait_for_map_grid(self, frame_budget: int = 300) -> int:
            return 0

        def map_location(self) -> tuple[int, int]:
            return (3, 7)

        def field_locked(self) -> bool:
            return False

        def run(self, frames: int, keys=None) -> None:
            self.waited += frames

        def _route_waypoints(self, tx: int, ty: int):
            self.attempts += 1
            if self.attempts == 1:
                raise RoutePlanningError("simulated transient blocker")
            return [(tx, ty)]

        def _walk_greedy(self, wx, wy, budget, sidesteps, start_map, *,
                         start_locked):
            self.arrived_at = (wx, wy)
            return True, 10, ""

        def screenshot(self, name: str) -> str:
            raise AssertionError("must not fail: the second plan succeeded")

    emu = _RecoveringEmu()
    _walk_to_once(emu, 3, 3, frame_budget=3000, max_sidesteps=8)

    assert emu.attempts == 2, "the loop must re-plan after a planning failure"
    assert emu.waited > 0, "it must actually wait before re-planning"
    assert emu.arrived_at == (3, 3)


@needs_mgba
def test_persistent_planning_failure_surfaces_the_diagnosis() -> None:
    """When re-planning never succeeds, the raised error carries the
    planner's own diagnosis -- not a generic 'made no progress'."""
    from rpg2gba.playtest.emulator import _walk_to_once

    class _NeverPlansEmu:
        def wait_for_map_grid(self, frame_budget: int = 300) -> int:
            return 0

        def map_location(self) -> tuple[int, int]:
            return (3, 7)

        def field_locked(self) -> bool:
            return False

        def run(self, frames: int, keys=None) -> None:
            pass

        def _route_waypoints(self, tx: int, ty: int):
            raise RoutePlanningError("PERMANENT: sealed room, distinctive text")

        def screenshot(self, name: str) -> str:
            return "shot.png"

    with pytest.raises(ScenarioError) as exc:
        _walk_to_once(_NeverPlansEmu(), 3, 3, frame_budget=3000, max_sidesteps=8)
    assert "sealed room, distinctive text" in str(exc.value)


# --- no replay fallback ---------------------------------------------------
#
# Inherited (`<owner>:<name>`) beats once got an unplanned greedy walk when
# the planner failed, because the hand CH01-CH04 coordinates predated the
# strict planner. That fallback was deleted with the hand suites
# (REDERIVATION_PLAN.md P10, 2026-10-03; it fired 0 times across all five
# generated walks). Every beat is now held to the planner.


@needs_mgba
def test_an_unplannable_leg_fails_loud_and_walks_nothing() -> None:
    from rpg2gba.playtest.contradictions import ContradictionLedger
    from rpg2gba.playtest.emulator import _walk_to_once

    class _NeverPlansEmu:
        def __init__(self) -> None:
            self.contradictions = ContradictionLedger()
            self.greedy_targets: list[tuple[int, int]] = []

        def wait_for_map_grid(self, frame_budget: int = 300) -> int:
            return 0

        def map_location(self) -> tuple[int, int]:
            return (3, 7)

        def field_locked(self) -> bool:
            return False

        def run(self, frames: int, keys=None) -> None:
            pass

        def _route_waypoints(self, tx: int, ty: int):
            raise RoutePlanningError("TRANSIENT: distinctive diagnosis text")

        def _walk_greedy(self, wx, wy, budget, sidesteps, start_map, *,
                         start_locked):
            self.greedy_targets.append((wx, wy))
            return True, 10, ""

        def screenshot(self, name: str) -> str:
            return "shot.png"

    emu = _NeverPlansEmu()
    with pytest.raises(ScenarioError) as exc:
        _walk_to_once(emu, 15, 6, frame_budget=3000, max_sidesteps=8)
    assert "distinctive diagnosis text" in str(exc.value)
    assert emu.greedy_targets == [], "nothing may be walked unplanned"
    assert emu.contradictions.entries == []
