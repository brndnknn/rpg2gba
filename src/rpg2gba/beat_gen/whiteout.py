"""White-out fork beats (REDERIVATION_PLAN.md §16.3 rulings 15-16).

A row the story model's white-out fork owns (a respawn map's "Starting
Over" page) has no tile to walk to: `whiteout_fork_beat` forces the
white-out by a RAM write and restores the snapshot after. So these rows skip
the route solver. Once the chapter's beats are ordered, each landing map's
rows become one beat, inserted directly after the last beat that claims one
of their `enabled_by` rows (the starter choice for Got Pokemon, the Center
for a landing it moved the anchor to) and riding in that beat's group, after
the rest of that group's run. With no enabler claimed in this chapter, it
rides at the end of the chapter's first group.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from rpg2gba.beat_gen.plan import PlannedBeat, make_kwargs
from rpg2gba.chapter_manifest.schema import parse_row_id


def heal_location_for(map_constant: str, entries: Sequence[Mapping[str, object]]) -> str:
    """The one `HEAL_LOCATION_*` id whose respawn is on `map_constant`.
    Fails loud on none or several: the landing must be unambiguous."""
    ids = sorted(str(e["id"]) for e in entries if e["map"] == map_constant)
    if len(ids) != 1:
        raise ValueError(
            f"white-out landing {map_constant}: expected exactly one heal "
            f"location, found {ids or 'none'}")
    return ids[0]


def place_whiteout_beats(
    beats: Sequence[PlannedBeat],
    fork_rows: Sequence[str],
    enabled_by: Mapping[str, tuple[tuple[str, ...], ...]],
    *,
    map_constant_for: Callable[[int], str],
    heal_entries: Sequence[Mapping[str, object]],
) -> tuple[PlannedBeat, ...]:
    """`beats` in final order plus one white-out beat per landing map of
    `fork_rows`, placed as the module docstring says."""
    if not fork_rows:
        return tuple(beats)
    if not beats:
        raise ValueError("white-out rows but no other beat to ride with")

    by_map: dict[int, list[str]] = {}
    for row_id in sorted(fork_rows):
        by_map.setdefault(parse_row_id(row_id).map_id, []).append(row_id)

    position_of_row = {r: i for i, b in enumerate(beats) for r in b.rows}
    inserts: dict[int, list[PlannedBeat]] = {}
    for map_id, rows in sorted(by_map.items()):
        enablers = {
            w for r in rows for group in enabled_by.get(r, ())
            for w in group if not w.startswith("engine:")}
        after = max((position_of_row[w] for w in enablers if w in position_of_row), default=-1)
        anchor = beats[max(after, 0)]
        const = map_constant_for(map_id)
        beat = PlannedBeat(
            name=f"m{map_id:03d}_whiteout",
            template="whiteout",
            map_id=map_id,
            rows=tuple(rows),
            group=anchor.group,
            kwargs=make_kwargs(heal_location_id=heal_location_for(const, heal_entries)),
        )
        inserts.setdefault(after, []).append(beat)

    out: list[PlannedBeat] = list(inserts.get(-1, []))
    for i, b in enumerate(beats):
        out.append(b)
        out.extend(inserts.get(i, []))
    return _contiguous(out)


def _contiguous(beats: list[PlannedBeat]) -> tuple[PlannedBeat, ...]:
    """A beat inserted after its anchor must not split the anchor's group:
    move it past the rest of that group's run."""
    out: list[PlannedBeat] = []
    pending: list[PlannedBeat] = []
    for b in beats:
        if b.template == "whiteout":
            pending.append(b)
            continue
        if pending and b.group != pending[0].group:
            out.extend(pending)
            pending = []
        out.append(b)
    out.extend(pending)
    return tuple(out)
