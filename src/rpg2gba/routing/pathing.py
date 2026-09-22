"""Tile-level pathfinding with an avoid-set and a blocked-set, and cross-map
stitching.

`MapGraph.shortest_path` (traversal/graph.py) has no avoid-set parameter --
this module is that missing piece, plus the glue that walks a `WorldGraph`
hop sequence and turns it into concrete per-map `RouteLeg`s a `RoutePlan`
segment can hold.

Two different cell sets, two different disciplines:

  - `avoid` is specifically a chapter's own foreign-trigger tiles
    (`TriggerOverlay.foreign_tiles`) -- tiles that fire *someone else's*
    script. It is a SOFT preference: `_path_on_map` tries a path avoiding
    them first, but falls back to a path that crosses them (recording the
    crossing) if that's the only way through. `path_avoiding` itself is
    trigger-agnostic; it just BFSes around whatever cell set it's handed.

  - `blocked` is stationary-NPC occupancy (`routing.occupancy.MapOccupancy`)
    -- tiles the player physically cannot enter because an object event is
    standing there. It is a HARD block honored on both the preferred path
    AND the fallback: a fallback that walks through an NPC would just trade
    one bug (routing through a foreign trigger) for a worse one (routing
    through a wall of flesh). See `_path_on_map`.
"""
from __future__ import annotations

import logging
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass

from rpg2gba.traversal.graph import Cell, MapGraph
from rpg2gba.traversal.triggers import TriggerOverlay
from rpg2gba.traversal.world import WorldEdge, WorldGraph

from .connections import MapConnection, connections_between, crossing_cells
from .connections import load_connections as _load_map_connections
from .occupancy import MapOccupancy
from .plan import RouteLeg, RouteWarp, TriggerCrossing

logger = logging.getLogger(__name__)


class RoutePlanningError(ValueError):
    """A segment cannot be routed at the tile level."""


def path_avoiding(
    graph: MapGraph, start: Cell, goal: Cell, avoid: frozenset[Cell],
    *, blocked: frozenset[Cell] = frozenset(),
) -> list[Cell] | None:
    """BFS shortest cell sequence start->goal (inclusive).

    `avoid` is soft: a cell in it is never entered EXCEPT `start`/`goal`
    themselves, which are always permitted even if listed in `avoid`.

    `blocked` is hard: a cell in it is never entered, full stop -- no
    start/goal carve-out. Callers that need a friendlier error than a bare
    `None` return when `start`/`goal` themselves are blocked (naming the
    occupying event) must check that themselves before calling; see
    `_path_on_map`.

    Honors every edge rule `MapGraph.neighbors()` knows about (stair
    diagonals, one-way ledge jumps), not a hand-rolled 4-neighbour walk.
    Deterministic: `neighbors()` returns edges in a fixed order and BFS
    explores/ties-break in that same insertion order, so identical inputs
    always yield an identical path.
    """
    if not graph.is_walkable(start):
        raise ValueError(f"map {graph.map_id}: start cell {start} is not walkable")

    if start == goal:
        return [start]

    came_from: dict[Cell, Cell] = {}
    seen = {start}
    queue: deque[Cell] = deque([start])
    while queue:
        cur = queue.popleft()
        for edge in graph.neighbors(cur):
            target = edge.target
            if target in seen:
                continue
            if target in blocked:
                continue
            if target in avoid and target not in (start, goal):
                continue
            seen.add(target)
            came_from[target] = cur
            if target == goal:
                path = [goal]
                node = goal
                while node != start:
                    node = came_from[node]
                    path.append(node)
                path.reverse()
                return path
            queue.append(target)
    return None


def _crossings_on_path(
    map_id: int, path: list[Cell], avoid: frozenset[Cell], overlay: TriggerOverlay,
) -> tuple[TriggerCrossing, ...]:
    """One `TriggerCrossing` for every `avoid`-set cell the path actually
    steps on, deterministically -- the first ref after sorting refs by
    `(kind.name, script)` supplies the script/certainty."""
    crossings: list[TriggerCrossing] = []
    for cell in path:
        if cell not in avoid:
            continue
        refs = sorted(overlay.refs_at(cell), key=lambda r: (r.kind.name, r.script))
        if not refs:
            raise RoutePlanningError(
                f"map {map_id}: cell {cell} is in the avoid set but the trigger "
                "overlay has no refs at it -- avoid set and overlay have diverged"
            )
        ref = refs[0]
        crossings.append(
            TriggerCrossing(
                map_id=map_id,
                cell=cell,
                script=ref.script,
                certainty=ref.certainty.name.lower(),
            )
        )
    return tuple(crossings)


def _path_into_solid_warp(
    map_id: int, start: Cell, warp: Cell, *, graph: MapGraph, overlay: TriggerOverlay,
    destination_scripts: frozenset[str], occupancy: MapOccupancy | None,
) -> tuple[list[Cell], tuple[TriggerCrossing, ...]]:
    """`_path_on_map` to the best walkable orthogonal neighbour of a solid
    warp tile, plus the press step onto it. Neighbours are tried in N, S,
    E, W order; the shortest path wins, ties to the earlier side."""
    x, y = warp
    best: tuple[list[Cell], tuple[TriggerCrossing, ...]] | None = None
    errors: list[str] = []
    for side in ((x, y - 1), (x, y + 1), (x + 1, y), (x - 1, y)):
        if not graph.is_walkable(side):
            continue
        try:
            path, crossings = _path_on_map(
                map_id, start, side, graph=graph, overlay=overlay,
                destination_scripts=destination_scripts, occupancy=occupancy)
        except RoutePlanningError as exc:
            errors.append(str(exc))
            continue
        if best is None or len(path) < len(best[0]):
            best = (path, crossings)
    if best is None:
        raise RoutePlanningError(
            f"map {map_id}: solid warp tile {warp} has no reachable walkable side from "
            f"{start}" + (f" ({'; '.join(errors)})" if errors else ""))
    return best[0] + [warp], best[1]


def _path_on_map(
    map_id: int,
    start: Cell,
    goal: Cell,
    *,
    graph: MapGraph,
    overlay: TriggerOverlay,
    destination_scripts: frozenset[str],
    occupancy: MapOccupancy | None = None,
) -> tuple[list[Cell], tuple[TriggerCrossing, ...]]:
    """The within-one-map routine shared by same-map segments and each leg of
    a cross-map stitch: try avoiding foreign triggers first, fall back to
    crossing them, raise if the goal is unreachable outright.

    `occupancy`, when supplied, contributes a HARD block (stationary-NPC
    tiles, see `pathing` module docstring) honored on both the preferred
    path and the fallback -- never bypassed the way a foreign-trigger
    crossing can be. `start`/`goal` being blocked is checked explicitly up
    front (naming the occupying event) rather than left to fall out of
    `path_avoiding` as a bare "no path" -- a beat that asks the player to
    stand on an NPC is a real authoring bug, not something to route around.

    A goal that is a SOLID warp tile (a building's exit mat: map 65's (9,14)
    is impassable with only its north side open) is reached the way the
    engine fires it: walk to a walkable orthogonal neighbour, then press
    into the tile. The path ends with that press step onto the warp cell.
    Without this, no segment could ever leave such a building (C6 part two,
    CH01).
    """
    if not graph.is_walkable(goal) and goal in graph.warp_exits:
        return _path_into_solid_warp(map_id, start, goal, graph=graph, overlay=overlay,
                                     destination_scripts=destination_scripts,
                                     occupancy=occupancy)

    blocked = occupancy.blocked_cells() if occupancy is not None else frozenset()

    if goal in blocked:
        npc = occupancy.at(goal)
        raise RoutePlanningError(
            f"map {map_id}: goal cell {goal} is occupied by stationary NPC "
            f"{npc.script!r} ({npc.movement_type}) -- a beat cannot ask the "
            "player to stand on an object event's tile"
        )
    if start in blocked:
        npc = occupancy.at(start)
        raise RoutePlanningError(
            f"map {map_id}: start cell {start} is occupied by stationary NPC "
            f"{npc.script!r} ({npc.movement_type}) -- cannot route from here"
        )

    avoid = frozenset(overlay.foreign_tiles(set(destination_scripts)))

    path = path_avoiding(graph, start, goal, avoid, blocked=blocked)
    if path is not None:
        return path, ()

    fallback = path_avoiding(graph, start, goal, frozenset(), blocked=blocked)
    if fallback is None:
        unblocked = path_avoiding(graph, start, goal, frozenset(), blocked=frozenset())
        if unblocked is None:
            raise RoutePlanningError(
                f"map {map_id}: goal {goal} is unreachable from {start} even "
                "ignoring foreign triggers -- geography, not a trigger, blocks "
                "this segment"
            )
        culprits = sorted(cell for cell in unblocked if cell in blocked)
        detail = ", ".join(
            f"{cell} ({occupancy.at(cell).script!r})" for cell in culprits
        ) if culprits else "an occupied tile on the only otherwise-available route"
        raise RoutePlanningError(
            f"map {map_id}: goal {goal} is reachable from {start} ignoring NPC "
            f"occupancy, but every such route is blocked by stationary-NPC "
            f"tile(s): {detail} -- this segment is unroutable without walking "
            "through an NPC (not a foreign-trigger-only problem)"
        )
    crossings = _crossings_on_path(map_id, fallback, avoid, overlay)
    return fallback, crossings


# Lazily loaded, process-wide: most `plan_segment` calls never touch a
# "connection"-kind hop, so this avoids the disk read (and the output/ build
# dependency) until one actually shows up.
_default_connections_cache: tuple[MapConnection, ...] | None = None


def _default_connections() -> tuple[MapConnection, ...]:
    global _default_connections_cache
    if _default_connections_cache is None:
        _default_connections_cache = _load_map_connections()
    return _default_connections_cache


def _connection_leg(
    current_map: int,
    current_cell: Cell,
    hop: WorldEdge,
    *,
    graphs: Mapping[int, MapGraph],
    overlays: Mapping[int, TriggerOverlay],
    destination_scripts: frozenset[str],
    connections: tuple[MapConnection, ...] | None,
    occupancy: Mapping[int, MapOccupancy] | None = None,
) -> tuple[RouteLeg, tuple[TriggerCrossing, ...], Cell]:
    """Route a "connection"-kind hop: it carries no fixed trigger cell (see
    `WorldEdge`'s docstring), so the crossing cell pair has to be derived
    from `connections.json` geometry (`.connections` module) instead of read
    straight off the hop the way a warp's `src_cell`/`dst_cell` are.

    Picks, among every walkable crossing cell pair, the one that minimizes
    the tile-level path cost from `current_cell` to the exit cell on
    `current_map` -- routed through `_path_on_map`, so it honors the exact
    same foreign-trigger avoid-set logic (and fallback-with-crossing
    recording) as every other leg: a connection crossing is not a back door
    around a foreign trigger.
    """
    conn_table = connections if connections is not None else _default_connections()
    matches = connections_between(conn_table, current_map, hop.dst_map)
    if not matches:
        raise RoutePlanningError(
            f"map {current_map} -> map {hop.dst_map}: no connections.json row "
            "describes this map-to-map connection -- cannot derive a crossing cell"
        )

    from_graph = graphs[current_map]
    to_graph = graphs[hop.dst_map]

    candidates: set[tuple[Cell, Cell]] = set()
    for conn in matches:
        candidates.update(crossing_cells(conn, from_graph=from_graph, to_graph=to_graph))

    if not candidates:
        direction = matches[0].direction
        raise RoutePlanningError(
            f"map {current_map} <-> map {hop.dst_map} ({direction.name} connection): "
            "no walkable crossing cell -- both sides are walled along the whole "
            "shared edge"
        )

    overlay = overlays[current_map]
    map_occupancy = occupancy.get(current_map) if occupancy is not None else None
    best: tuple[int, list[Cell], tuple[TriggerCrossing, ...], Cell] | None = None
    for exit_cell, entry_cell in sorted(candidates):
        try:
            path, crossings = _path_on_map(
                current_map, current_cell, exit_cell,
                graph=from_graph, overlay=overlay, destination_scripts=destination_scripts,
                occupancy=map_occupancy,
            )
        except RoutePlanningError:
            continue
        cost = len(path) - 1
        if best is None or cost < best[0]:
            best = (cost, path, crossings, entry_cell)

    if best is None:
        raise RoutePlanningError(
            f"map {current_map}: none of the {len(candidates)} walkable crossing "
            f"cell(s) into map {hop.dst_map} are reachable from {current_cell}"
        )

    _, path, crossings, entry_cell = best
    leg = RouteLeg(
        map_id=current_map, tiles=tuple(path),
        exit_warp=RouteWarp(event_id=None, dest_map=hop.dst_map, dest_cell=entry_cell),
    )
    return leg, crossings, entry_cell


def _tile_count(legs: tuple[RouteLeg, ...]) -> int:
    """Steps taken, not cells visited: total tiles across all legs minus the
    number of legs, so a zero-length (single-cell) segment costs 0."""
    return sum(len(leg.tiles) for leg in legs) - len(legs)


@dataclass(frozen=True)
class SegmentResult:
    legs: tuple[RouteLeg, ...]
    tile_count: int
    crossings: tuple[TriggerCrossing, ...]


def plan_segment(
    start_map: int, start_cell: Cell,
    goal_map: int, goal_cell: Cell,
    *,
    graphs: Mapping[int, MapGraph],
    overlays: Mapping[int, TriggerOverlay],
    destination_scripts: frozenset[str],
    world: WorldGraph | None = None,
    connections: tuple[MapConnection, ...] | None = None,
    occupancy: Mapping[int, MapOccupancy] | None = None,
) -> SegmentResult:
    """Route from (`start_map`, `start_cell`) to (`goal_map`, `goal_cell`).

    Same-map: BFS avoiding this chapter's foreign triggers; falls back to
    crossing them (recording `TriggerCrossing`s) if that's the only way
    through; raises `RoutePlanningError` if the goal is unreachable even
    then. `occupancy` (per map id, `routing.occupancy.MapOccupancy`), when
    supplied, additionally hard-blocks every stationary-NPC tile on BOTH the
    preferred and fallback path -- unlike the foreign-trigger avoid-set,
    occupancy is never bypassed by the fallback. Defaults to `None`
    (no map has occupancy data, current behaviour unchanged).

    Cross-map: requires `world`, walks its shortest hop sequence
    (`WorldGraph.shortest_path`), and stitches one `RouteLeg` per map
    touched, each ending at the hop's crossing cell with `exit_warp`
    describing it, continuing from the corresponding cell on the next map.
    A "warp"/"seam_warp" hop uses its fixed `src_cell`/`dst_cell` directly. A
    "connection"-kind hop (no fixed trigger cell -- the whole shared map edge
    is crossable) is instead routed via `.connections`: `_connection_leg`
    derives the walkable crossing cell pairs from `connections.json` geometry
    and picks the cheapest one reachable from the current position, still
    honoring the avoid-set (a connection is not a back door around a foreign
    trigger) and occupancy. `connections` defaults to loading
    `connections.json` lazily the first time it's needed; pass it explicitly
    to inject test data or a scratch-build copy. Its `exit_warp.event_id` is
    `None` -- a connection crossing has no originating RMXP event.
    """
    if start_map == goal_map:
        graph = graphs[start_map]
        overlay = overlays[start_map]
        map_occupancy = occupancy.get(start_map) if occupancy is not None else None
        path, crossings = _path_on_map(
            start_map, start_cell, goal_cell,
            graph=graph, overlay=overlay, destination_scripts=destination_scripts,
            occupancy=map_occupancy,
        )
        leg = RouteLeg(map_id=start_map, tiles=tuple(path), exit_warp=None)
        legs = (leg,)
        return SegmentResult(legs=legs, tile_count=_tile_count(legs), crossings=crossings)

    if world is None:
        raise RoutePlanningError(
            f"segment from map {start_map} to map {goal_map}: crossing maps requires a "
            "WorldGraph, none was supplied"
        )

    hops = world.shortest_path(start_map, goal_map)
    if hops is None:
        raise RoutePlanningError(
            f"segment from map {start_map} to map {goal_map}: no route between these "
            "maps in the world graph"
        )

    legs: list[RouteLeg] = []
    all_crossings: list[TriggerCrossing] = []
    current_map = start_map
    current_cell = start_cell

    for hop in hops:
        if hop.kind == "connection":
            leg, hop_crossings, current_cell = _connection_leg(
                current_map, current_cell, hop,
                graphs=graphs, overlays=overlays,
                destination_scripts=destination_scripts, connections=connections,
                occupancy=occupancy,
            )
            legs.append(leg)
            all_crossings.extend(hop_crossings)
            current_map = hop.dst_map
            continue

        if hop.src_cell is None or hop.dst_cell is None:
            raise RoutePlanningError(
                f"segment from map {start_map} to map {goal_map}: hop {hop.src_map}->"
                f"{hop.dst_map} is kind {hop.kind!r} with no fixed trigger cell -- "
                "cannot be routed at tile level"
            )

        graph = graphs[current_map]
        overlay = overlays[current_map]
        map_occupancy = occupancy.get(current_map) if occupancy is not None else None
        path, crossings = _path_on_map(
            current_map, current_cell, hop.src_cell,
            graph=graph, overlay=overlay, destination_scripts=destination_scripts,
            occupancy=map_occupancy,
        )
        exit_warp = RouteWarp(
            event_id=hop.event_id, dest_map=hop.dst_map, dest_cell=hop.dst_cell,
        )
        legs.append(RouteLeg(map_id=current_map, tiles=tuple(path), exit_warp=exit_warp))
        all_crossings.extend(crossings)

        current_map = hop.dst_map
        current_cell = hop.dst_cell

    graph = graphs[current_map]
    overlay = overlays[current_map]
    map_occupancy = occupancy.get(current_map) if occupancy is not None else None
    path, crossings = _path_on_map(
        current_map, current_cell, goal_cell,
        graph=graph, overlay=overlay, destination_scripts=destination_scripts,
        occupancy=map_occupancy,
    )
    legs.append(RouteLeg(map_id=current_map, tiles=tuple(path), exit_warp=None))
    all_crossings.extend(crossings)

    legs_tuple = tuple(legs)
    return SegmentResult(
        legs=legs_tuple,
        tile_count=_tile_count(legs_tuple),
        crossings=tuple(all_crossings),
    )
