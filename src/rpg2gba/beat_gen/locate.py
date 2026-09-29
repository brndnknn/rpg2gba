"""Stage 4: planned beats -> location records -> solved route -> order
(C6 Task 4).

Almost all of this exists for DISPOSITION-named beats:
`routing.locations.derive_locations` (rows -> `BeatLocationRecord`s via
`cell_for_row` + `choose_routing_point`), `chapter_from_locations` (records
-> a body-less `Chapter` the solver accepts) and `routing.solver.solve_route`
(with `candidates=`). This stage feeds them PLANNED beats instead, and fills
the two gaps: branch rows (located through their page) and seam rows
(located through `seam.seam_crossings`).
"""
from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence

from rpg2gba.beat_gen.group import owning_page
from rpg2gba.beat_gen.plan import PlannedBeat, Refusal, make_kwargs
from rpg2gba.beat_gen.seam import SeamCrossing
from rpg2gba.chapter_manifest.schema import ManifestRow
from rpg2gba.routing.locations import (
    ApproachCandidate,
    BeatLocationRecord,
    RowCell,
    choose_routing_point,
)
from rpg2gba.routing.plan import RouteNode

_ARRIVAL_TRIGGERS = frozenset({"autorun", "parallel"})

CellFn = Callable[[ManifestRow], RowCell]
SeamFn = Callable[[ManifestRow], tuple[SeamCrossing, ...]]
MapConstantFn = Callable[[int], str]


def _cell_for_row(
    row: ManifestRow,
    rows_by_id: Mapping[str, ManifestRow],
    cell_fn: CellFn,
    seam_fn: SeamFn,
    map_constant_fn: MapConstantFn,
) -> RowCell:
    """One row's `RowCell`, filling `cell_for_row`'s two refused kinds.

    A branch row is located through its OWNING PAGE (`rows_by_id` must be the
    whole manifest -- the page may have been refused upstream and still needs
    to resolve here, `research/04_locate.md` §3), but the returned cell keeps
    the arm's own `row_id` so the record still names which row it covers.

    A seam row has no single cell -- `seam_fn` returns every legal crossing,
    and ALL of them become `ApproachCandidate`s so the solver can pick among
    them (task file, "The two gaps you fill"). The record's own cell is the
    first crossing's exit cell, matching "the first crossing is the record's
    cell". Neither `press` alone nor cell alone distinguishes candidates in
    general, so `side` folds in both.
    """
    if row.kind == "branch":
        # The OWNING page, not `parent_row_id`: a nested arm's parent is
        # another arm, which `cell_fn` refuses.
        page_id = owning_page(row)
        if page_id not in rows_by_id:
            raise ValueError(
                f"{row.row_id}: branch row's owning page {page_id!r} is not "
                "in rows_by_id -- pass the whole manifest, not just owned rows"
            )
        page_cell = cell_fn(rows_by_id[page_id])
        return dataclasses.replace(page_cell, row_id=row.row_id)

    if row.kind == "seam":
        crossings = seam_fn(row)
        if not crossings:
            raise ValueError(f"{row.row_id}: seam row has no legal crossing")
        map_constant = map_constant_fn(row.map_id)
        candidates = tuple(
            ApproachCandidate(
                x=c.exit_cell[0],
                y=c.exit_cell[1],
                side=f"{c.press}@({c.exit_cell[0]},{c.exit_cell[1]})",
                resolver=(
                    f"seam crossing: exit=({c.exit_cell[0]},{c.exit_cell[1]}) "
                    f"press={c.press!r} entry=({c.entry_cell[0]},{c.entry_cell[1]})"
                ),
            )
            for c in crossings
        )
        first = crossings[0]
        return RowCell(
            row_id=row.row_id,
            map_constant=map_constant,
            x=first.exit_cell[0],
            y=first.exit_cell[1],
            resolver=(
                f"seam crossing: exit=({first.exit_cell[0]},{first.exit_cell[1]}) "
                f"press={first.press!r} entry=({first.entry_cell[0]},{first.entry_cell[1]})"
            ),
            approach_candidates=candidates,
        )

    return cell_fn(row)


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
    group_order: list[str] = []
    group_beats: dict[str, list[PlannedBeat]] = {}
    for beat in beats:
        if beat.group not in group_beats:
            group_beats[beat.group] = []
            group_order.append(beat.group)
        group_beats[beat.group].append(beat)

    records: list[BeatLocationRecord] = []
    refusals: list[Refusal] = []

    for group in group_order:
        group_rows = [row_id for beat in group_beats[group] for row_id in beat.rows]

        cells: list[RowCell] = []
        failure: tuple[str, ValueError] | None = None
        first = rows_by_id[group_rows[0]]
        for row_id in group_rows:
            row = rows_by_id[row_id]
            try:
                cell = _cell_for_row(row, rows_by_id, cell_fn, seam_fn, map_constant_fn)
            except ValueError as exc:
                failure = (row_id, exc)
                break
            # A choice round trip (`beat_gen/round_trip.py`) claims an autorun
            # page's arm in the beat of a player-triggered page of the same
            # event: the autorun re-fires inside that interaction, so the
            # player stands where the talk page is talked to.
            if (row.event_id == first.event_id and row.map_id == first.map_id
                    and row.trigger in _ARRIVAL_TRIGGERS
                    and first.trigger not in _ARRIVAL_TRIGGERS):
                continue
            cells.append(cell)

        if failure is not None:
            bad_row_id, exc = failure
            for row_id in group_rows:
                if row_id == bad_row_id:
                    refusals.append(Refusal(
                        row_id=row_id, blocker="cell", reason="cell_error", detail=str(exc)))
                else:
                    refusals.append(Refusal(
                        row_id=row_id, blocker="cell", reason="group_refused",
                        detail=(
                            f"group {group!r} refused: row {bad_row_id!r} could not "
                            f"be located ({exc})"
                        )))
            continue

        chosen = choose_routing_point(group, tuple(cells))
        records.append(BeatLocationRecord(
            beat_id=group,
            map_constant=chosen.map_constant,
            x=chosen.x,
            y=chosen.y,
            resolver=chosen.resolver,
            rows=tuple(group_rows),
            candidates=tuple(cells),
            approach_candidates=chosen.approach_candidates,
        ))

    return records, refusals


def route_order(nodes: Sequence[RouteNode]) -> tuple[tuple[str, ...], dict[str, str]]:
    """(group ids in route order, {group: chosen side}) from a solved
    route's nodes. Entry/exit nodes contribute nothing; a group node
    without a `chosen_approach` contributes no pick."""
    order: list[str] = []
    picks: dict[str, str] = {}
    for node in nodes:
        if node.kind != "group":
            continue
        order.append(node.group)  # RouteNode.__post_init__: never None here
        if node.chosen_approach is not None:
            picks[node.group] = node.chosen_approach.side
    return tuple(order), picks


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
    by_group: dict[str, list[PlannedBeat]] = {}
    for beat in beats:
        by_group.setdefault(beat.group, []).append(beat)

    beat_groups = set(by_group)
    order_groups = set(group_order)

    missing = sorted(beat_groups - order_groups)
    if missing:
        raise ValueError(f"group_order is missing group(s) {missing}")
    unknown = sorted(order_groups - beat_groups)
    if unknown:
        raise ValueError(f"group_order names unknown group(s) {unknown}")

    out: list[PlannedBeat] = []
    for group in group_order:
        pick = picks.get(group)
        for beat in by_group[group]:
            if pick is not None:
                out.append(dataclasses.replace(
                    beat, kwargs=make_kwargs(**{**dict(beat.kwargs), "approach_prefer": pick})))
            else:
                out.append(beat)
    return tuple(out)
