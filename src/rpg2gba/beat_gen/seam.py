"""Stage 3: the seam resolver (C6 Task 3; C6_GENERATOR_PLAN.md A1).

A seam row names a whole shared map edge, not a cell, which is why
`routing.locations.cell_for_row` refuses it. This module returns the LEGAL
crossing set; the route solver picks the cheapest, and the review doc shows
the pick (A1's answer: "resolver + solver picks, inside C6").

The edge geometry already exists: `routing.connections.crossing_cells` maps
one map's edge onto the other's with the engine-verified offset formula.
Reuse it (§4.3); this module adds only the SeamRef adapter and the
"landing is open" filter.

STATUS: stub (`assignments/C6/03_seam.md`).
"""
from __future__ import annotations

from dataclasses import dataclass

from rpg2gba.chapter_manifest.schema import ManifestRow
from rpg2gba.routing.connections import MapConnection
from rpg2gba.traversal.graph import Cell, MapGraph


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
    raise NotImplementedError


def seam_crossings(
    row: ManifestRow, *, from_graph: MapGraph, to_graph: MapGraph,
) -> tuple[SeamCrossing, ...]:
    """Every legal crossing for one seam row, sorted.

    Legal = `crossing_cells` keeps the pair (both ends walkable) AND the
    landing is open: the cell one further step into `to_graph`, continuing
    in the press direction, is walkable. An empty result is returned, not
    raised; the caller turns it into a `Refusal(blocker="cell")`."""
    raise NotImplementedError
