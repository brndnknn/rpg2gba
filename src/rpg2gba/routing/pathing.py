"""Tile-level pathfinding with an avoid-set, and cross-map stitching.

`MapGraph.shortest_path` (traversal/graph.py) has no avoid-set parameter --
this module is that missing piece, plus the glue that walks a `WorldGraph`
hop sequence and turns it into concrete per-map `RouteLeg`s a `RoutePlan`
segment can hold.

The "avoid" concept here is specifically a chapter's own foreign-trigger
tiles (`TriggerOverlay.foreign_tiles`) -- tiles that fire *someone else's*
script. `path_avoiding` itself is trigger-agnostic; it just BFSes around
whatever cell set it's handed.
"""
from __future__ import annotations

import logging
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass

from rpg2gba.traversal.graph import Cell, MapGraph
from rpg2gba.traversal.triggers import Certainty, TriggerOverlay
from rpg2gba.traversal.world import WorldEdge, WorldGraph

from .connections import MapConnection, connections_between, crossing_cells
from .connections import load_connections as _load_map_connections
from .plan import RouteLeg, RouteWarp, TriggerCrossing

logger = logging.getLogger(__name__)


class RoutePlanningError(ValueError):
    """A segment cannot be routed at the tile level."""


def path_avoiding(
    graph: MapGraph, start: Cell, goal: Cell, avoid: frozenset[Cell],
) -> list[Cell] | None:
    """BFS shortest cell sequence start->goal (inclusive), never entering a
    cell in `avoid` -- except `start` and `goal` themselves, which are always
    permitted even if listed in `avoid`.

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


def _path_on_map(
    map_id: int,
    start: Cell,
    goal: Cell,
    *,
    graph: MapGraph,
    overlay: TriggerOverlay,
    destination_scripts: frozenset[str],
) -> tuple[list[Cell], tuple[TriggerCrossing, ...]]:
    """The within-one-map routine shared by same-map segments and each leg of
    a cross-map stitch: try avoiding foreign triggers first, fall back to
    crossing them, raise if the goal is unreachable outright."""
    avoid = frozenset(overlay.foreign_tiles(set(destination_scripts)))

    path = path_avoiding(graph, start, goal, avoid)
    if path is not None:
        return path, ()

    fallback = path_avoiding(graph, start, goal, frozenset())
    if fallback is None:
        raise RoutePlanningError(
            f"map {map_id}: goal {goal} is unreachable from {start} even ignoring "
            "foreign triggers -- geography, not a trigger, blocks this segment"
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
    best: tuple[int, list[Cell], tuple[TriggerCrossing, ...], Cell] | None = None
    for exit_cell, entry_cell in sorted(candidates):
        try:
            path, crossings = _path_on_map(
                current_map, current_cell, exit_cell,
                graph=from_graph, overlay=overlay, destination_scripts=destination_scripts,
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
) -> SegmentResult:
    """Route from (`start_map`, `start_cell`) to (`goal_map`, `goal_cell`).

    Same-map: BFS avoiding this chapter's foreign triggers; falls back to
    crossing them (recording `TriggerCrossing`s) if that's the only way
    through; raises `RoutePlanningError` if the goal is unreachable even
    then.

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
    trigger). `connections` defaults to loading `connections.json` lazily the
    first time it's needed; pass it explicitly to inject test data or a
    scratch-build copy. Its `exit_warp.event_id` is `None` -- a connection
    crossing has no originating RMXP event.
    """
    if start_map == goal_map:
        graph = graphs[start_map]
        overlay = overlays[start_map]
        path, crossings = _path_on_map(
            start_map, start_cell, goal_cell,
            graph=graph, overlay=overlay, destination_scripts=destination_scripts,
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
        path, crossings = _path_on_map(
            current_map, current_cell, hop.src_cell,
            graph=graph, overlay=overlay, destination_scripts=destination_scripts,
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
    path, crossings = _path_on_map(
        current_map, current_cell, goal_cell,
        graph=graph, overlay=overlay, destination_scripts=destination_scripts,
    )
    legs.append(RouteLeg(map_id=current_map, tiles=tuple(path), exit_warp=None))
    all_crossings.extend(crossings)

    legs_tuple = tuple(legs)
    return SegmentResult(
        legs=legs_tuple,
        tile_count=_tile_count(legs_tuple),
        crossings=tuple(all_crossings),
    )
