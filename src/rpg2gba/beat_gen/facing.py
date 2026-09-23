"""Direction-conditioned arms pin the approach side (C6 plan A4).

An RMXP conditional branch of type 6 on the player (`[6, -1, dir]`) runs its
`then` arm only when the player faces `dir` -- i.e. only when the page is
fired from the side opposite that direction -- and its `else` arm from every
other side. Such arms are mutually exclusive, so no single interaction can
cover them all: each distinct set of legal sides becomes its own group,
walked from a side that selects it (ruling 2026-09-18: "the arm pins the
side ... Bambo walks both the right and left arms"). Where no arm is
direction-gated the solver picks freely, as before.

Nested arms intersect: `else` of facing-RIGHT, then `then` of facing-LEFT,
is east only. A condition on another character (`params[1] != -1`) is an
NPC's facing, not the player's, and pins nothing.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from rpg2gba.beat_gen.plan import PlannedBeat, Refusal
from rpg2gba.chapter_manifest.generator import iter_page_scopes
from rpg2gba.chapter_manifest.schema import parse_row_id
from rpg2gba.routing.locations import BeatLocationRecord

_CHARACTER_DIRECTION = 6
_PLAYER = -1

ALL_SIDES: frozenset[str] = frozenset({"north", "south", "east", "west"})

# RMXP facing (2 down, 4 left, 6 right, 8 up) -> the side of the event the
# player stands on to face it that way: facing RIGHT means standing WEST.
_SIDE_FOR_FACING: dict[int, str] = {2: "north", 4: "east", 6: "west", 8: "south"}


def facing_sides(map_id: int, map_data: Mapping[str, Any],
                 event_ids: Iterable[int] | None = None) -> dict[str, frozenset[str]]:
    """{branch row id: the sides it can run from} for every arm on the map
    that sits under at least one player-facing condition. Arms under none
    are absent (unconstrained). Fails loud on a facing value outside 2/4/6/8."""
    wanted = None if event_ids is None else set(event_ids)
    out: dict[str, frozenset[str]] = {}
    for event in map_data.get("events", []) or []:
        if wanted is not None and event["id"] not in wanted:
            continue
        for page_idx, page in enumerate(event.get("pages", []) or []):
            commands = page.get("list") or []
            allowed: dict[str, frozenset[str] | None] = {}
            for scope in iter_page_scopes(map_id, event, page_idx, page):
                inherited = allowed.get(scope.parent_row_id) if scope.parent_row_id else None
                own = _own_sides(scope, commands)
                if own is None:
                    sides = inherited
                elif inherited is None:
                    sides = own
                else:
                    sides = inherited & own
                allowed[scope.row_id] = sides
                if sides is not None:
                    out[scope.row_id] = sides
    return out


def _own_sides(scope: Any, commands: Sequence[Mapping[str, Any]]) -> frozenset[str] | None:
    branch = scope.branch
    if branch is None or branch.condition_type != _CHARACTER_DIRECTION:
        return None
    params = commands[branch.opener_index]["parameters"]
    if params[1] != _PLAYER:
        return None
    side = _SIDE_FOR_FACING.get(params[2])
    if side is None:
        raise ValueError(f"{scope.row_id}: player-facing branch on direction "
                         f"{params[2]!r} (expected 2/4/6/8)")
    return frozenset({side}) if branch.arm_kind == "then" else ALL_SIDES - {side}


def _side_key(sides: frozenset[str]) -> str:
    return "_".join(s for s in ("north", "south", "east", "west") if s in sides)


def split_facing_arms(
    beats: Sequence[PlannedBeat], sides_by_row: Mapping[str, frozenset[str]],
) -> tuple[tuple[PlannedBeat, ...], dict[str, frozenset[str]]]:
    """(beats with every direction-gated arm moved into its own group, {group:
    legal sides}). Rows sharing one legal-side set share a beat, named
    `<beat>_face_<sides>` and grouped under that name, placed right after the
    beat it came from. A beat left with no rows is dropped. Non-generic
    templates are left alone: only generic beats carry arms."""
    out: list[PlannedBeat] = []
    pins: dict[str, frozenset[str]] = {}
    for beat in beats:
        gated = [r for r in beat.rows if r in sides_by_row]
        if beat.template != "generic" or not gated:
            out.append(beat)
            continue
        free = tuple(r for r in beat.rows if r not in sides_by_row)
        if free:
            out.append(dataclasses.replace(beat, rows=free))
        by_sides: dict[frozenset[str], list[str]] = {}
        for row_id in gated:
            by_sides.setdefault(sides_by_row[row_id], []).append(row_id)
        for sides, row_ids in sorted(by_sides.items(), key=lambda kv: _side_key(kv[0])):
            if not sides:
                raise ValueError(f"{beat.name}: arms {row_ids} can run from no side "
                                 "(contradictory facing conditions)")
            name = f"{beat.name}_face_{_side_key(sides)}"
            out.append(dataclasses.replace(beat, name=name, group=name, rows=tuple(row_ids)))
            pins[name] = sides
    return tuple(out), pins


def pin_records(
    records: Sequence[BeatLocationRecord], pins: Mapping[str, frozenset[str]],
) -> tuple[list[BeatLocationRecord], list[Refusal]]:
    """Each pinned group's record with its approach candidates narrowed to
    the legal sides. A pinned group none of whose candidates is legal is
    refused by name (its arm cannot be walked at all), not re-sided."""
    kept: list[BeatLocationRecord] = []
    refusals: list[Refusal] = []
    for record in records:
        sides = pins.get(record.beat_id)
        if sides is None:
            kept.append(record)
            continue
        legal = tuple(c for c in record.approach_candidates if c.side in sides)
        if not legal:
            offered = sorted(c.side for c in record.approach_candidates)
            refusals.extend(Refusal(
                row_id=row_id, blocker="cell", reason="no_facing_side",
                detail=(f"group {record.beat_id!r} runs only from {sorted(sides)}; "
                        f"the event offers {offered}"))
                for row_id in record.rows)
            continue
        kept.append(dataclasses.replace(record, approach_candidates=legal))
    return kept, refusals


def event_ids_by_map(row_ids: Iterable[str]) -> dict[int, set[int]]:
    """{map: event ids} over the branch rows in `row_ids` -- the events
    `facing_sides` needs to read."""
    out: dict[int, set[int]] = {}
    for row_id in row_ids:
        parsed = parse_row_id(row_id)
        if parsed.kind == "branch" and parsed.map_id is not None and parsed.event_id is not None:
            out.setdefault(parsed.map_id, set()).add(parsed.event_id)
    return out
