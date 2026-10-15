"""Lane-gated rocks and the smash beat's `sight_trainers` (CH08, Route 1).

A rock whose EVERY walkable approach cell lies in the sight lanes of trainers
this chapter still has to fight cannot be smashed without the walk being
spotted mid-smash. Such a rock leaves the main `smash` group for a second one
(`m033smash2_rock_smash`) that the solver places after every gating trainer's
beat (`wait_edges`). Rocks with at least one lane-free approach stay put; the
runtime picks that approach.

Pure: the geometry arrives as callables so tests need no map data.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from rpg2gba.beat_gen.plan import PlannedBeat
from rpg2gba.chapter_manifest.schema import parse_row_id

Cell = tuple[int, int]


@dataclass(frozen=True)
class LaneSplit:
    """`beats` with lane-gated rocks moved into second smash groups.
    `gates` maps a second group's name to the gating trainers' event ids;
    `waits` maps that group to the trainer GROUPS it must follow."""

    beats: tuple[PlannedBeat, ...]
    gates: Mapping[str, tuple[int, ...]]
    waits: Mapping[str, tuple[str, ...]]


def _event_of(row_id: str) -> int:
    event_id = parse_row_id(row_id).event_id
    if event_id is None:
        raise ValueError(f"{row_id}: a smash/trainer row has an event id")
    return event_id


def this_chapter_trainers(
    beats: Sequence[PlannedBeat], lane_of: Callable[[int, int], frozenset[Cell] | None],
) -> dict[tuple[int, int], PlannedBeat]:
    """(map, event) -> the beat that fights a sight trainer in THIS chapter:
    the beat claiming the event's lowest page (its battle page; the trainer
    archetype or a generic beat -- CH08's ev039 is the latter). An event with
    no sight lane is no trainer; an inbound beat (`manifest_chapter_id`, the
    predecessor's row) was fought earlier."""
    first: dict[tuple[int, int], tuple[int, PlannedBeat]] = {}
    for b in beats:
        if b.template in ("smash", "obstacle", "transit") \
                or "manifest_chapter_id" in dict(b.kwargs):
            continue
        for rid in b.rows:
            parsed = parse_row_id(rid)
            if parsed.event_id is None:
                continue
            key = (b.map_id, parsed.event_id)
            if key not in first or parsed.page_idx < first[key][0]:
                first[key] = (parsed.page_idx, b)
    return {k: b for k, (_, b) in sorted(first.items()) if lane_of(*k) is not None}


def split_lane_gated(
    beats: Sequence[PlannedBeat], *,
    approach_cells: Callable[[int, int], frozenset[Cell]],
    lane_of: Callable[[int, int], frozenset[Cell] | None],
) -> LaneSplit:
    """Partition each smash beat's rocks into lane-free and lane-gated.

    `approach_cells(map, event)` is every walkable approach cell of a rock;
    `lane_of(map, event)` a trainer's sight lane (None when it has no object
    on the ROM). A rock is gated when it has approach cells and none lies
    outside the union of the lanes of this chapter's trainers on its map; its
    gates are the trainers whose lane covers at least one approach cell."""
    trainers = this_chapter_trainers(beats, lane_of)
    out: list[PlannedBeat] = []
    gates: dict[str, tuple[int, ...]] = {}
    waits: dict[str, tuple[str, ...]] = {}
    for b in beats:
        if b.template != "smash":
            out.append(b)
            continue
        rock_rows: dict[int, list[str]] = {}
        for rid in b.rows:
            rock_rows.setdefault(_event_of(rid), []).append(rid)
        gated: dict[int, tuple[int, ...]] = {}
        for event_id in sorted(rock_rows):
            cells = approach_cells(b.map_id, event_id)
            if not cells:
                continue
            lanes = {t: lane for (m, t) in sorted(trainers) if m == b.map_id
                     for lane in [lane_of(m, t)] if lane}
            union = frozenset().union(*lanes.values()) if lanes else frozenset()
            if cells <= union:
                gated[event_id] = tuple(t for t, lane in lanes.items() if lane & cells)
        if not gated:
            out.append(b)
            continue
        free_rows = tuple(r for r in b.rows if _event_of(r) not in gated)
        gated_rows = tuple(r for r in b.rows if _event_of(r) in gated)
        gating = tuple(sorted({t for ts in gated.values() for t in ts}))
        if free_rows:
            _, _, tail = b.name.partition("_")
            name = f"m{b.map_id:03d}smash2_{tail}"
            out.append(dataclasses.replace(b, rows=free_rows))
            out.append(dataclasses.replace(b, name=name, rows=gated_rows, group=name))
        else:
            name = b.name
            out.append(b)
        gates[name] = gating
        waits[name] = tuple(trainers[(b.map_id, t)].group for t in gating)
    return LaneSplit(tuple(out), gates, waits)


def wait_edges(split: LaneSplit, beats: Sequence[PlannedBeat]
               ) -> dict[str, tuple[tuple[str, ...], ...]]:
    """`enabled_by` entries (first row of the gated group -> one single-row
    group per gating trainer), the solver's precedence input: the smash group
    comes after every gating trainer's beat group."""
    by_group = {b.group: b for b in beats}
    trainer_row = {b.group: b.rows[0] for b in beats}
    out: dict[str, tuple[tuple[str, ...], ...]] = {}
    for name, trainer_groups in split.waits.items():
        out[by_group[name].rows[0]] = tuple((trainer_row[g],) for g in trainer_groups)
    return out


def sight_trainers_for(
    ordered: Sequence[PlannedBeat], lane_of: Callable[[int, int], frozenset[Cell] | None],
) -> dict[str, tuple[int, ...]]:
    """smash beat name -> event ids (sorted) of this chapter's trainers on its
    map whose battle beat comes LATER in the solved order."""
    trainers = this_chapter_trainers(ordered, lane_of)
    index = {b.name: i for i, b in enumerate(ordered)}
    out: dict[str, tuple[int, ...]] = {}
    for b in ordered:
        if b.template != "smash":
            continue
        out[b.name] = tuple(sorted(
            e for (m, e), t in trainers.items()
            if m == b.map_id and index[t.name] > index[b.name]))
    return out
