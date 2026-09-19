"""Stage 4: planned beats -> location records -> solved route -> order
(C6 Task 4).

Almost all of this exists for DISPOSITION-named beats:
`routing.locations.derive_locations` (rows -> `BeatLocationRecord`s via
`cell_for_row` + `choose_routing_point`), `chapter_from_locations` (records
-> a body-less `Chapter` the solver accepts) and `routing.solver.solve_route`
(with `candidates=`). This stage feeds them PLANNED beats instead, and fills
the two gaps: branch rows (located through their page) and seam rows
(located through `seam.seam_crossings`).

STATUS: stub (`assignments/C6/04_locate.md`).
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from rpg2gba.beat_gen.plan import PlannedBeat, Refusal
from rpg2gba.beat_gen.seam import SeamCrossing
from rpg2gba.chapter_manifest.schema import ManifestRow
from rpg2gba.routing.locations import BeatLocationRecord, RowCell
from rpg2gba.routing.plan import RouteNode

CellFn = Callable[[ManifestRow], RowCell]
SeamFn = Callable[[ManifestRow], tuple[SeamCrossing, ...]]
MapConstantFn = Callable[[int], str]


def locate_beats(
    beats: Sequence[PlannedBeat],
    rows_by_id: Mapping[str, ManifestRow],
    *,
    cell_fn: CellFn,
    seam_fn: SeamFn,
    map_constant_fn: MapConstantFn,
) -> tuple[list[BeatLocationRecord], list[Refusal]]:
    """One `BeatLocationRecord` per GROUP (not per beat), keyed
    `beat_id=<group>`, in first-appearance order, plus `Refusal`s
    (`blocker="cell"`) for every row of a group that could not be fully
    located (such a group gets no record).

    `rows_by_id` is the WHOLE manifest, not just owned rows: an arm whose
    page was refused is still located through that page. `cell_fn` is
    normally `routing.locations.cell_for_row`, `seam_fn` a closure over
    `seam.seam_crossings`, `map_constant_fn` the MAP_* lookup; they are
    parameters so tests can pass fakes."""
    raise NotImplementedError


def route_order(nodes: Sequence[RouteNode]) -> tuple[tuple[str, ...], dict[str, str]]:
    """(group ids in route order, {group: chosen side}) from a solved
    route's nodes. Entry/exit nodes contribute nothing; a group node
    without a `chosen_approach` contributes no pick."""
    raise NotImplementedError


def order_beats(
    beats: Sequence[PlannedBeat],
    group_order: Sequence[str],
    picks: Mapping[str, str],
) -> tuple[PlannedBeat, ...]:
    """`beats` reordered group by group in `group_order`, keeping their
    relative order inside a group, with each pick applied as an
    `approach_prefer` kwarg on the group's beats. Raises `ValueError` if a
    group is missing from `group_order` or `group_order` names an unknown
    group."""
    raise NotImplementedError
