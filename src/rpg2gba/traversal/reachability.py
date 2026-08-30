"""Capability-tagged reachability over the offline traversal graph.

`graph.MapGraph` derives walkability purely from tile collision (module
docstring of `graph.py`); it has no notion of obstacle *events* (rocks,
boulders) at all. `capabilities.CapabilityMap` separately classifies obstacle
cells by the two routes those obstacles enter the corpus through
(`capabilities.py` module docstring):

    (a) event obstacles (`Obstacle.source == "event"`, rock-smash rocks and
        strength boulders) -- the cell is WALKABLE in `MapGraph` (nothing
        about tile collision knows a solid event object stands there), but
        the real game blocks it because a non-`through` event with a graphic
        occupies the tile. Held capability makes it passable; the absence of
        one must FLIP a graph-walkable cell to blocked.

    (b) terrain obstacles (`Obstacle.source == "terrain"`, surf water and
        waterfall tiles) -- the cell is already BLOCKED in `MapGraph` (water
        reads as collision), and a held capability FLIPS it back to passable.

The two routes invert each other. This module's BFS must apply both
corrections uniformly to every stepped-to cell, not just to `is_walkable`
call sites the graph itself makes internally -- reusing `MapGraph.neighbors`
directly would be wrong in both directions (it would still refuse a
water crossing under SURF, and it would still offer a walk onto an
un-cleared obstacle cell). So the stepping logic below re-derives edges
using an effective-walkable predicate that layers the capability corrections
on top of `MapGraph`'s stair/ledge/bounds rules, mirroring the structure of
`MapGraph.neighbors` (CLAUDE.md §4.3 -- collision/stair/ledge rules are
reused from their one source of truth, never reimplemented; only the
walkability predicate itself is swapped)."""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass

from .capabilities import (
    VERIFIED_CAPABILITIES,
    Capability,
    CapabilityMap,
    UnverifiedCapabilityError,
)
from .direction import CARDINALS, Direction
from .graph import Cell, MapGraph

logger = logging.getLogger(__name__)


def _validate_candidates(candidates: frozenset[Capability] | None) -> frozenset[Capability]:
    """Resolve `candidates` to its default and reject any unverified
    capability (CUT/FLASH/DIVE) up front -- fail loud, CLAUDE.md §4.5."""
    resolved = VERIFIED_CAPABILITIES if candidates is None else frozenset(candidates)
    unverified = resolved - VERIFIED_CAPABILITIES
    if unverified:
        names = ", ".join(sorted(c.value for c in unverified))
        raise UnverifiedCapabilityError(
            f"cannot derive reachability for unverified capability(ies) {names}: "
            "no grant site or obstacle surface exists anywhere in the corpus "
            "for them; detection must not be invented (CLAUDE.md §4.5)"
        )
    return resolved


def _effective_walkable(
    graph: MapGraph,
    capability_map: CapabilityMap,
    held: frozenset[Capability],
    cell: Cell,
) -> bool:
    """`MapGraph.is_walkable(cell)`, corrected for both obstacle routes.

    No obstacle at `cell`: defer entirely to the graph (collision/stair/ledge
    rules, unchanged). An obstacle present: event-source cells are blocked
    unless held, regardless of the graph's own (always-True) collision read;
    terrain-source cells are passable only if held, regardless of the
    graph's own (always-False) collision read."""
    if not graph.in_bounds(cell):
        return False
    if graph.is_ledge(cell):
        # A ledge is never a resting cell in this model either (module
        # docstring of graph.py) -- no known obstacle ever sits on one in
        # the corpus, but keep the graph's own rule authoritative here too.
        return False

    obstacle = capability_map.obstacles.get(cell)
    if obstacle is None:
        return graph.is_walkable(cell)

    unlocked = obstacle.capability in held
    if obstacle.source == "terrain":
        return unlocked
    # obstacle.source == "event"
    if not unlocked:
        return False
    return graph.is_walkable(cell)


def _effective_neighbors(
    graph: MapGraph,
    capability_map: CapabilityMap,
    held: frozenset[Capability],
    cell: Cell,
) -> list[Cell]:
    """Outgoing step targets from `cell`, mirroring `MapGraph.neighbors`'s
    stair-diagonal / one-way-ledge structure but gated by
    `_effective_walkable` instead of `MapGraph.is_walkable` at every target
    check."""
    if not graph.in_bounds(cell):
        return []

    def walkable(c: Cell) -> bool:
        return _effective_walkable(graph, capability_map, held, c)

    targets: list[Cell] = []

    if graph.is_stair(cell):
        for press in (Direction.EAST, Direction.WEST):
            result = graph.stair_press_result(cell, press)
            if result is not None and walkable(result):
                targets.append(result)
        for d in (Direction.NORTH, Direction.SOUTH):
            target = (cell[0] + d.delta[0], cell[1] + d.delta[1])
            if walkable(target):
                targets.append(target)
        return targets

    for d in CARDINALS:
        step = (cell[0] + d.delta[0], cell[1] + d.delta[1])
        if not graph.in_bounds(step):
            continue

        if graph.is_ledge(step):
            if graph.ledge_directions[step] is d:
                landing = (step[0] + d.delta[0], step[1] + d.delta[1])
                if walkable(landing):
                    targets.append(landing)
            continue

        if graph.is_stair(step) and d in (Direction.EAST, Direction.WEST):
            result = graph.stair_press_result(step, d)
            if result is not None and walkable(result):
                targets.append(result)
            continue

        if walkable(step):
            targets.append(step)

    return targets


def reachable_with(
    graph: MapGraph,
    capability_map: CapabilityMap,
    start: Cell,
    held: frozenset[Capability] = frozenset(),
) -> set[Cell]:
    """BFS from `start`, applying both obstacle-route corrections above."""
    if not _effective_walkable(graph, capability_map, held, start):
        raise ValueError(
            f"start cell {start} is not walkable on map {graph.map_id} "
            f"with held capabilities {sorted(c.value for c in held)}"
        )
    seen = {start}
    queue: deque[Cell] = deque([start])
    while queue:
        cur = queue.popleft()
        for target in _effective_neighbors(graph, capability_map, held, cur):
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return seen


def is_reachable_with(
    graph: MapGraph,
    capability_map: CapabilityMap,
    start: Cell,
    goal: Cell,
    held: frozenset[Capability] = frozenset(),
) -> bool:
    return goal in reachable_with(graph, capability_map, start, held)


def _minimal_sets_for_predicate(
    candidates: frozenset[Capability],
    predicate,
) -> list[frozenset[Capability]]:
    """Exhaustive subset search: every held-set drawn from `candidates` for
    which `predicate(held)` holds, reduced to the minimal ones (no proper
    subset also holds). With 4 verified capabilities there are only 16
    subsets, so exhaustive beats any heuristic on both correctness and
    simplicity. Deterministic order: by size, then by sorted capability
    value."""
    ordered = sorted(candidates, key=lambda c: c.value)
    n = len(ordered)
    working: list[frozenset[Capability]] = []
    for mask in range(1 << n):
        subset = frozenset(ordered[i] for i in range(n) if mask & (1 << i))
        if predicate(subset):
            working.append(subset)

    minimal = [s for s in working if not any(other < s for other in working)]
    minimal.sort(key=lambda s: (len(s), tuple(sorted(c.value for c in s))))
    return minimal


def minimal_capability_sets(
    graph: MapGraph,
    capability_map: CapabilityMap,
    start: Cell,
    goal: Cell,
    *,
    candidates: frozenset[Capability] | None = None,
) -> list[frozenset[Capability]]:
    """Every MINIMAL held-set that makes `goal` reachable from `start`.

    Empty list if unreachable even with every candidate capability (true
    geography, not a gate). `[frozenset()]` if already reachable with
    nothing."""
    resolved = _validate_candidates(candidates)

    def predicate(held: frozenset[Capability]) -> bool:
        return is_reachable_with(graph, capability_map, start, goal, held)

    return _minimal_sets_for_predicate(resolved, predicate)


def adjacent_approach_cells(graph: MapGraph, cell: Cell) -> list[Cell]:
    """The in-bounds orthogonal neighbours of `cell` -- the tiles an event
    (obstacle or NPC) at `cell` would actually be interacted from, since the
    event's own tile is never a resting cell for the player. Order is
    deterministic (`direction.CARDINALS` order: N, S, E, W)."""
    x, y = cell
    result: list[Cell] = []
    for d in CARDINALS:
        c = (x + d.delta[0], y + d.delta[1])
        if graph.in_bounds(c):
            result.append(c)
    return result


class PermanentlyUnstandableGoalError(ValueError):
    """`derive_blocked_verdict` was asked about a cell no capability can make
    standable -- a wall, or a solid event's own tile. See its docstring."""


@dataclass(frozen=True)
class BlockedVerdict:
    goal: Cell
    reachable_now: bool
    minimal_sets: list[frozenset[Capability]]

    def as_disposition(self) -> str:
        """"" when reachable now; "blocked:<cap>[|<cap>...]" using the
        smallest minimal set (ties broken by sorted capability value, per
        `_minimal_sets_for_predicate`'s ordering) when at least one
        capability combination opens it; "unreachable:geography" when no
        candidate combination does."""
        if self.reachable_now:
            return ""
        if not self.minimal_sets:
            return "unreachable:geography"
        best = self.minimal_sets[0]
        return "blocked:" + "|".join(sorted(c.value for c in best))


def derive_blocked_verdict(
    graph: MapGraph,
    capability_map: CapabilityMap,
    start: Cell,
    goal: Cell,
    *,
    candidates: frozenset[Capability] | None = None,
) -> BlockedVerdict:
    """The blocked/open verdict for a bare cell goal (use
    `derive_blocked_verdict_for_event` instead for an obstacle/NPC event,
    which is interacted with from an adjacent tile, not by standing on it).

    Fails loud (CLAUDE.md §4.5) when `goal` is a cell the player can never
    stand on and no capability could change that -- a solid event's own tile,
    or a wall. Asking "can the player reach this cell" about such a tile is a
    malformed question, and the honest-looking answer it used to return
    (`unreachable:geography`) is wrong in the way that matters: it reports a
    plain geography dead end and silently drops whatever capability gate
    actually governs the approach. That is exactly how CH02's beat B10
    (Gertha, cell (25,37), an NPC standing solid) derived as geography-locked
    instead of `blocked:rock_smash`."""
    resolved = _validate_candidates(candidates)
    if not graph.is_walkable(goal) and capability_map.capability_at(goal) is None:
        raise PermanentlyUnstandableGoalError(
            f"cell {goal} on this map is not walkable and carries no capability-tagged "
            "obstacle, so the player can never stand on it under any capability set: "
            "a verdict about *standing on* it is meaningless. If this is an event's "
            "own tile (an obstacle, an NPC), call derive_blocked_verdict_for_event() "
            "instead -- it derives the verdict from the adjacent tiles the event is "
            "actually interacted from."
        )
    if is_reachable_with(graph, capability_map, start, goal, frozenset()):
        return BlockedVerdict(goal=goal, reachable_now=True, minimal_sets=[frozenset()])
    minimal_sets = minimal_capability_sets(
        graph, capability_map, start, goal, candidates=resolved
    )
    return BlockedVerdict(goal=goal, reachable_now=False, minimal_sets=minimal_sets)


def derive_blocked_verdict_for_event(
    graph: MapGraph,
    capability_map: CapabilityMap,
    start: Cell,
    event_cell: Cell,
    *,
    candidates: frozenset[Capability] | None = None,
) -> BlockedVerdict:
    """The blocked/open verdict for an event at `event_cell`: reachable if
    ANY orthogonally-adjacent walkable cell is reachable from `start`."""
    resolved = _validate_candidates(candidates)
    approach_cells = adjacent_approach_cells(graph, event_cell)

    def predicate(held: frozenset[Capability]) -> bool:
        return any(
            is_reachable_with(graph, capability_map, start, cell, held)
            for cell in approach_cells
        )

    if predicate(frozenset()):
        return BlockedVerdict(goal=event_cell, reachable_now=True, minimal_sets=[frozenset()])
    minimal_sets = _minimal_sets_for_predicate(resolved, predicate)
    return BlockedVerdict(goal=event_cell, reachable_now=False, minimal_sets=minimal_sets)
