"""Stage 3: the seam resolver (C6 Task 3; C6_GENERATOR_PLAN.md A1).

A seam row names a whole shared map edge, not a cell, which is why
`routing.locations.cell_for_row` refuses it. This module returns the LEGAL
crossing set; the route solver picks the cheapest, and the review doc shows
the pick (A1's answer: "resolver + solver picks, inside C6").

The edge geometry already exists: `routing.connections.crossing_cells` maps
one map's edge onto the other's with the engine-verified offset formula.
Reuse it (§4.3); this module adds only the SeamRef adapter and the
"landing is open" filter.

STATUS: implemented (`assignments/C6/03_seam.md`, Task 3).
"""
from __future__ import annotations

from dataclasses import dataclass

from rpg2gba.chapter_manifest.schema import ManifestRow
from rpg2gba.playtest.cells import seam_warp_cells
from rpg2gba.routing.connections import MapConnection, _EDGE_TO_DIRECTION, crossing_cells
from rpg2gba.traversal.direction import Direction
from rpg2gba.traversal.graph import Cell, MapGraph

# Direction -> the D-pad press held to cross a seam in that direction. No
# existing table maps `traversal.direction.Direction` to these four strings
# (research/03_seam.md §3b); the nearest analogues key on RMXP's int facing
# codes, a different domain. Task 5 (`adapt.py`) needs the same side->press
# mapping and can reuse this one (research doc, lead note).
_PRESS: dict[Direction, str] = {
    Direction.NORTH: "UP",
    Direction.SOUTH: "DOWN",
    Direction.EAST: "RIGHT",
    Direction.WEST: "LEFT",
}


@dataclass(frozen=True, order=True)
class SeamCrossing:
    """One legal way across: stand on `exit_cell` (this row's map), press
    `press` ("UP"/"DOWN"/"LEFT"/"RIGHT"), arrive on `entry_cell` (the
    other map)."""

    exit_cell: Cell
    entry_cell: Cell
    press: str


def connection_for(row: ManifestRow) -> MapConnection:
    """The directed `MapConnection` for a seam row (this map -> other map).
    Raises `ValueError` if `row.kind != "seam"` or `row.seam` is None."""
    if row.kind != "seam" or row.seam is None:
        raise ValueError(f"{row.row_id}: not a seam row (kind={row.kind!r})")
    ref = row.seam
    return MapConnection(
        from_map=ref.map_id,
        direction=_EDGE_TO_DIRECTION[ref.direction],
        offset=ref.offset,
        to_map=ref.other_map_id,
        to_offset=ref.other_offset,
    )


def seam_crossings(
    row: ManifestRow, *, from_graph: MapGraph, to_graph: MapGraph,
) -> tuple[SeamCrossing, ...]:
    """Every legal crossing for one seam row, sorted.

    Legal = `crossing_cells` keeps the pair (both ends walkable) AND the
    landing is open: the cell one further step into `to_graph`, continuing
    in the press direction, is walkable. A pair joined by a seam_warps.json
    arrow-warp substitution also requires the exit to be one of its arrow
    cells (the rest of the edge does not warp on the ROM) with the cell
    behind it walkable -- the crossing is a held press from that cell
    (ROM run 74: Route 2 (20,56) sits under a wall). An empty result is
    returned, not raised; the caller turns it into a
    `Refusal(blocker="cell")`."""
    connection = connection_for(row)
    press = _PRESS[connection.direction]
    dx, dy = connection.direction.delta
    arrows = seam_warp_cells(connection.from_map, connection.to_map)

    crossings: list[SeamCrossing] = []
    for exit_cell, entry_cell in crossing_cells(
        connection, from_graph=from_graph, to_graph=to_graph
    ):
        landing = (entry_cell[0] + dx, entry_cell[1] + dy)
        if not to_graph.is_walkable(landing):
            continue
        if arrows:
            approach = (exit_cell[0] - dx, exit_cell[1] - dy)
            if exit_cell not in arrows or not from_graph.is_walkable(approach):
                continue
        crossings.append(SeamCrossing(exit_cell, entry_cell, press))

    return tuple(sorted(crossings))
