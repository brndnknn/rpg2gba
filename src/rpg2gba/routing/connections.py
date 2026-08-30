"""Map connections (`output/uranium-build/connections.json`, Phase 5 §5.4) as
a *routable* crossing, not just a world-graph edge.

`traversal.world.WorldGraph` already models a `connections.json` row as two
`WorldEdge`s of `kind == "connection"`, but deliberately leaves `src_cell`/
`dst_cell` as `None` -- a connection is a whole shared map edge, not a single
trigger cell, so there is no one cell to name at that layer. This module is
the missing piece: given a connection and the two maps' `MapGraph`s, it
derives every walkable `(exit_cell, entry_cell)` pair along the shared edge,
so `pathing.plan_segment` can stitch a tile-level path across a "connection"
hop the same way it already does for a "warp"/"seam_warp" one.

ROW SEMANTICS -- reusing the existing source of truth
======================================================
`tileset_converter.connections.load_connections` already parses and validates
`connections.json` rows (`[map_a, edge_a, offset_a, map_b, edge_b, offset_b]`)
-- edge-letter well-formedness, opposite-edge check, int typing. This module
reuses that loader rather than re-parsing the file (CLAUDE.md §4.3): it only
adds the routing-specific geometry on top.

THE OFFSET FORMULA -- derived and cross-checked against the vendored engine
============================================================================
Essentials' raw offsets (`offset_a`, `offset_b`) anchor a point on each map's
own edge in that map's own local grid (`tileset_converter.connections`'s
module docstring works this out in detail: N -> (offset, 0), S -> (offset,
height), W -> (0, offset), E -> (width, offset)). The two anchors name the
SAME point in world space -- that is what "connected" means -- so a cell at
distance `k` from one map's anchor, along the shared axis, corresponds to the
cell at the same distance `k` from the other map's anchor:

    shared_axis_to = shared_axis_from - offset_from + offset_to

This was cross-checked directly against the engine's own connection-filling
code, independent of (and consistent with) `tileset_converter.connections`'s
own pokeemerald-offset derivation:

    engine/src/fieldmap.c:292-331 FillNorthConnection: with the pokeemerald
    offset field `o = offset_from - offset_to` (per
    `tileset_converter.connections.build_connections`), the connected map's
    column `x2 = k` is drawn at this map's column `x = o + k` (mod the
    MAP_OFFSET screen-frame padding, which cancels out of the subtraction
    below since it's added identically to both sides). Inverting:
    `x2 = x - o = x - (offset_from - offset_to) = x - offset_from + offset_to`
    -- exactly the formula above. The same structure repeats verbatim in
    `FillSouthConnection` (253-290), `FillWestConnection` (333-369), and
    `FillEastConnection` (371-406): each one's `offset`-bearing axis reduces
    to the identical `connected_coord = this_coord - offset` relationship.

    Worked against the CH04 seam, `connections.json` row
    `[31, "N", 11, 35, "S", 0]`: shift = 11 - 0 = 11. Map031's local column
    `x` (its N edge, row 0) lines up with Map035's local column `x - 11` (its
    S edge, row `height - 1`) -- e.g. Map031 (11, 0) <-> Map035 (0, 56).

FAIL LOUD on: a connection whose two maps' declared edge geometry does not
overlap at all under this formula (no `k` in bounds on both sides) -- that is
a genuine data inconsistency, distinct from "the shared edge is real but every
cell along it happens to be walled," which `crossing_cells` reports instead as
an empty (not raised) result -- the caller (`pathing.plan_segment`) is the one
that turns "no walkable pair" into a `RoutePlanningError`, since only it knows
both map ids and the direction to name in a useful message.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from rpg2gba.tileset_converter.connections import load_connections as _load_connection_rows
from rpg2gba.traversal.direction import Direction
from rpg2gba.traversal.graph import Cell, MapGraph
from rpg2gba.traversal.world import DEFAULT_CONNECTIONS_JSON

logger = logging.getLogger(__name__)

# connections.json edge letter -> the traversal-graph cardinal direction of
# THAT map's own edge (not a pokeemerald up/down/left/right string -- this is
# a different mapping than `tileset_converter.connections.EDGE_TO_DIRECTION`,
# which targets the emitted C schema, not this module's `Direction` enum).
_EDGE_TO_DIRECTION: dict[str, Direction] = {
    "N": Direction.NORTH,
    "S": Direction.SOUTH,
    "E": Direction.EAST,
    "W": Direction.WEST,
}


@dataclass(frozen=True)
class MapConnection:
    """One directed map-connection crossing: `from_map`'s `direction` edge
    joins `to_map`'s (opposite) edge.

    `offset`/`to_offset` are BOTH sides' raw `connections.json` offsets (not
    the pokeemerald-schema offset `tileset_converter.connections` derives) --
    `crossing_cells` needs both to compute the shared-axis shift (module
    docstring). `to_offset` is carried here, rather than requiring a second
    lookup, because a `MapConnection` is meant to be usable on its own once
    handed to `crossing_cells`.
    """

    from_map: int
    direction: Direction
    offset: int
    to_map: int
    to_offset: int


def load_connections(path: Path = DEFAULT_CONNECTIONS_JSON) -> tuple[MapConnection, ...]:
    """Load `connections.json` and expand every row into its two directed
    `MapConnection`s (mirrors `traversal.world.build_world_graph`'s
    both-directions treatment of the same rows)."""
    connections: list[MapConnection] = []
    for row in _load_connection_rows(path):
        connections.append(MapConnection(
            from_map=row.map_a, direction=_EDGE_TO_DIRECTION[row.edge_a],
            offset=row.offset_a, to_map=row.map_b, to_offset=row.offset_b,
        ))
        connections.append(MapConnection(
            from_map=row.map_b, direction=_EDGE_TO_DIRECTION[row.edge_b],
            offset=row.offset_b, to_map=row.map_a, to_offset=row.offset_a,
        ))
    return tuple(connections)


def connections_between(
    connections: tuple[MapConnection, ...], from_map: int, to_map: int,
) -> tuple[MapConnection, ...]:
    """Every `MapConnection` going directly `from_map` -> `to_map`, sorted
    deterministically. Normally at most one (a map pair appears once in
    `connections.json`); returns all of them if the source ever declares
    more than one seam between the same pair."""
    return tuple(sorted(
        (c for c in connections if c.from_map == from_map and c.to_map == to_map),
        key=lambda c: (c.direction.value, c.offset, c.to_offset),
    ))


def crossing_cells(
    connection: MapConnection, *, from_graph: MapGraph, to_graph: MapGraph,
) -> tuple[tuple[Cell, Cell], ...]:
    """Every walkable `(exit_cell_on_from_map, entry_cell_on_to_map)` pair
    along `connection`'s shared edge, sorted deterministically.

    Walks every cell along `from_graph`'s edge, maps it to `to_graph`'s local
    grid via the offset formula (module docstring), and keeps only pairs
    where BOTH cells are walkable in their own graph. Raises `ValueError`
    (fail loud, CLAUDE.md §4.5) if the two maps' edges don't overlap at all
    under the formula -- a real data inconsistency, not "no walkable cells,"
    which this returns as an empty tuple instead (the caller decides what an
    empty result means for its purpose).
    """
    if from_graph.map_id != connection.from_map:
        raise ValueError(
            f"crossing_cells: from_graph is map {from_graph.map_id}, but connection "
            f"is from map {connection.from_map}"
        )
    if to_graph.map_id != connection.to_map:
        raise ValueError(
            f"crossing_cells: to_graph is map {to_graph.map_id}, but connection is "
            f"to map {connection.to_map}"
        )

    shift = connection.offset - connection.to_offset
    direction = connection.direction

    pairs: list[tuple[Cell, Cell]] = []
    any_overlap = False

    if direction in (Direction.NORTH, Direction.SOUTH):
        exit_y = 0 if direction is Direction.NORTH else from_graph.height - 1
        entry_y = to_graph.height - 1 if direction is Direction.NORTH else 0
        for x_from in range(from_graph.width):
            x_to = x_from - shift
            if not (0 <= x_to < to_graph.width):
                continue
            any_overlap = True
            exit_cell = (x_from, exit_y)
            entry_cell = (x_to, entry_y)
            if from_graph.is_walkable(exit_cell) and to_graph.is_walkable(entry_cell):
                pairs.append((exit_cell, entry_cell))
    else:
        exit_x = from_graph.width - 1 if direction is Direction.EAST else 0
        entry_x = 0 if direction is Direction.EAST else to_graph.width - 1
        for y_from in range(from_graph.height):
            y_to = y_from - shift
            if not (0 <= y_to < to_graph.height):
                continue
            any_overlap = True
            exit_cell = (exit_x, y_from)
            entry_cell = (entry_x, y_to)
            if from_graph.is_walkable(exit_cell) and to_graph.is_walkable(entry_cell):
                pairs.append((exit_cell, entry_cell))

    if not any_overlap:
        raise ValueError(
            f"map {connection.from_map} ({direction.name} edge, offset "
            f"{connection.offset}) and map {connection.to_map} (offset "
            f"{connection.to_offset}) do not share any overlapping edge cell "
            "under the derived connection formula -- these two maps do not "
            "actually share an edge"
        )

    pairs.sort()
    return tuple(pairs)
