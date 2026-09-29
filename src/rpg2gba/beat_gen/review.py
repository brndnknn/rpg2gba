"""Stage 8: `ChapterPlan` -> `output/beats/CHnn.review.md` (C6 Task 8; R7, C2).

The review doc is part of the §9 per-chapter boot gate (C6 plan C2): the
operator reads and approves it before the generated module replaces a hand
module. It is the ONLY human-visible record of the solver's picks, so it
must show every pick, every refusal and every order-dependent write.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from rpg2gba.beat_floor.assertion import FloorAssertion, RowFloor
from rpg2gba.beat_gen.plan import BLOCKERS, ChapterPlan, PlannedBeat

logger = logging.getLogger(__name__)

FloorLookup = Callable[[str], RowFloor]


@dataclass(frozen=True)
class RowLocation:
    """Where a row lives, in the map viewer's terms: `Map032 Name (x,y)`.
    `cell` is the event's tile (None when the row has no single tile, e.g. a
    seam); `note` carries the rest (a seam's edge and neighbour)."""

    map_id: int
    map_name: str
    cell: tuple[int, int] | None = None
    note: str = ""


class Locator(Protocol):
    """Row id / map id -> viewer-facing location. Optional: without one the
    doc still renders, just without coordinates (unit fixtures)."""

    def row(self, row_id: str) -> RowLocation: ...

    def map_name(self, map_id: int) -> str: ...


def _map_label(map_id: int, map_name: str) -> str:
    return f"Map{map_id:03d} {map_name}".rstrip()


def _cell_label(loc: RowLocation) -> str:
    parts = [f"({loc.cell[0]},{loc.cell[1]})"] if loc.cell is not None else []
    if loc.note:
        parts.append(loc.note)
    return " ".join(parts)


def _at(row_id: str, locate: Locator | None) -> str:
    """` @ Map032 Name (x,y)` suffix for a row line; empty without a locator."""
    if locate is None:
        return ""
    loc = locate.row(row_id)
    cell = _cell_label(loc)
    return f" @ {_map_label(loc.map_id, loc.map_name)}{' ' + cell if cell else ''}"

# Fixed display order for the Refusals section (assignments/C6/08_review.md).
_BLOCKER_ORDER: tuple[str, ...] = ("#109", "C8", "story-state", "floor", "cell")
assert set(_BLOCKER_ORDER) == BLOCKERS


def _pick(beat: PlannedBeat) -> str:
    """The solver's pick for one beat's Order-section line: a warp's press
    `direction`, else `approach_prefer` -- whichever the template call took
    (`adapt.route_kwargs`). `-` when the beat has neither (e.g. a beat with
    only one candidate approach never needed a preference)."""
    kwargs = dict(beat.kwargs)
    if beat.template == "warp":
        return str(kwargs.get("direction", "-"))
    return str(kwargs.get("approach_prefer", "-"))


def _sorted_assertions(floor: RowFloor) -> tuple[FloorAssertion, ...]:
    return tuple(sorted(floor.assertions, key=lambda a: (a.kind, a.list_index)))


def _parse_order_dependent_key(key: str) -> tuple[str, dict[str, Any]]:
    """`OrderDependentKey.key` -> (the `FloorAssertion.kind` that writes it,
    the params identifying which write on a row's floor matches). Mirrors
    every shape `story_state.model._state_key_repr` can produce; raises on
    a shape this doc doesn't (yet) know how to show a write for --
    `temp_switch` never reaches an `OrderDependentKey` at all
    (`compute_end_state` skips `TempSwitch` writers entirely), and `engine`
    keys are never row-written, so both are unsupported here on purpose."""
    kind, _, rest = key.partition(":")
    if kind == "switch":
        return "switch_write", {"switch_id": int(rest)}
    if kind == "var":
        return "var_write", {"var_id": int(rest)}
    if kind == "self_switch":
        _map_id, event_id, letter = rest.split("/")
        return "self_switch_write", {"event_id": int(event_id), "letter": letter}
    raise ValueError(f"review: unsupported order-dependent key shape {key!r}")


def _write_value(floor: RowFloor, assertion_kind: str, match: dict[str, Any]) -> Any:
    """The value the row leaves the key at: its LAST matching write (highest
    `list_index`), since a page that writes a switch twice ends on the
    second write."""
    for a in reversed(_sorted_assertions(floor)):
        if a.kind != assertion_kind:
            continue
        params = dict(a.params)
        if all(params.get(k) == v for k, v in match.items()):
            return params["value"]
    raise ValueError(
        f"review: {floor.row_id} has no {assertion_kind} assertion matching {match}")


def _beat_position(plan: ChapterPlan, row_id: str) -> int:
    for i, beat in enumerate(plan.beats):
        if row_id in beat.rows:
            return i
    raise ValueError(f"review: row {row_id!r} is claimed by no beat in {plan.chapter_id}")


def _summary(plan: ChapterPlan, *, floor_lookup: FloorLookup) -> list[str]:
    rows_claimed = [rid for beat in plan.beats for rid in beat.rows]
    groups = sorted({beat.group for beat in plan.beats})
    offline = sum(1 for rid in rows_claimed if floor_lookup(rid).offline_eligible)
    return [
        f"- beats: {len(plan.beats)}",
        f"- groups: {len(groups)}",
        f"- rows claimed: {len(rows_claimed)}",
        f"- refusals: {len(plan.refusals)}",
        f"- elsewhere: {len(plan.elsewhere)}",
        f"- offline-eligible rows: {offline} / {len(rows_claimed)}",
    ]


def _beat_map(beat: PlannedBeat, locate: Locator | None) -> str:
    if locate is None:
        return f"Map{beat.map_id:03d}"
    if beat.rows:
        loc = locate.row(beat.rows[0])
        return _map_label(loc.map_id, loc.map_name)
    # A transit beat claims no rows; name its map without a cell.
    return _map_label(beat.map_id, locate.map_name(beat.map_id))


def _beat_cells(beat: PlannedBeat, locate: Locator | None) -> str:
    """Every distinct tile the beat's rows sit on, in row order (an obstacle
    beat claims several rocks)."""
    if locate is None or not beat.rows:
        return "-"
    seen: list[str] = []
    for row_id in beat.rows:
        label = _cell_label(locate.row(row_id))
        if label and label not in seen:
            seen.append(label)
    return " ".join(seen) or "-"


def _order(plan: ChapterPlan, *, locate: Locator | None) -> list[str]:
    lines = ["| # | beat | map | x,y | template | rows | pick |",
             "|---|---|---|---|---|---|---|"]
    for i, beat in enumerate(plan.beats, start=1):
        lines.append(
            f"| {i} | {beat.name} | {_beat_map(beat, locate)} | {_beat_cells(beat, locate)} | "
            f"{beat.template} | {len(beat.rows)} | {_pick(beat)} |")
    return lines


def _assertions(plan: ChapterPlan, *, floor_lookup: FloorLookup,
                locate: Locator | None) -> list[str]:
    lines: list[str] = []
    for i, beat in enumerate(plan.beats, start=1):
        where = ""
        if locate is not None:
            cells = _beat_cells(beat, locate)
            where = f" -- {_beat_map(beat, locate)}" + (f" {cells}" if cells != "-" else "")
        lines.append(f"### #{i} {beat.name}{where}")
        for row_id in beat.rows:
            floor = floor_lookup(row_id)
            kinds = sorted({a.kind for a in floor.assertions})
            mode = "offline" if floor.offline_eligible else "ROM"
            lines.append(f"- {row_id}: kinds {', '.join(kinds) or 'none'} -- {mode}")
    return lines


def _refusals(plan: ChapterPlan, *, locate: Locator | None) -> list[str]:
    if not plan.refusals:
        return ["none"]
    by_blocker: dict[str, list[str]] = {b: [] for b in _BLOCKER_ORDER}
    for r in plan.refusals:
        by_blocker[r.blocker].append(f"- {r.row_id}{_at(r.row_id, locate)}: {r.reason} -- {r.detail}")
    lines: list[str] = []
    for blocker in _BLOCKER_ORDER:
        entries = by_blocker[blocker]
        if not entries:
            continue
        lines.append(f"### {blocker}")
        lines.extend(sorted(entries))
    return lines


def _elsewhere(plan: ChapterPlan, *, locate: Locator | None) -> list[str]:
    if not plan.elsewhere:
        return ["none"]
    lines: list[str] = []
    for e in plan.elsewhere:
        at = _at(e.row_id, locate)
        if e.status in ("later", "boundary"):
            lines.append(f"- {e.row_id}{at}: {e.status} -- owner {e.owner}")
        elif e.status == "blocked":
            lines.append(f"- {e.row_id}{at}: blocked -- requires {', '.join(e.requires)}")
        elif e.status in ("never_fires", "unselected_arm", "stripped", "arm_gated"):
            lines.append(f"- {e.row_id}{at}: {e.status} -- {e.detail}")
        else:
            lines.append(f"- {e.row_id}{at}: {e.status}")
    return lines


def _order_dependent(plan: ChapterPlan, *, floor_lookup: FloorLookup,
                     locate: Locator | None) -> list[str]:
    if not plan.order_dependent:
        return ["none"]
    lines: list[str] = []
    for odk in sorted(plan.order_dependent, key=lambda k: k.key):
        assertion_kind, match = _parse_order_dependent_key(odk.key)
        ordered_writers = sorted(odk.writers, key=lambda rid: _beat_position(plan, rid))
        last_floor = floor_lookup(ordered_writers[-1])
        landing = _write_value(last_floor, assertion_kind, match)
        lines.append(
            f"- {odk.key}: order taken {' -> '.join(rid + _at(rid, locate) for rid in ordered_writers)} -- lands {landing!r}")
    return lines


def _liveness_problems(plan: ChapterPlan) -> list[str]:
    """Pages kept in the plan that are not their event's live page at their
    route position (`state_arms`): solver work, not demoted."""
    if not plan.liveness_problems:
        return ["none"]
    return [f"- {p.beat} (#{p.position}) page {p.page}: {p.kind} -- {p.detail}"
            for p in sorted(plan.liveness_problems, key=lambda p: (p.position, p.page))]


def _scene_moved(plan: ChapterPlan, *, locate: Locator | None) -> list[str]:
    """Flavour beats whose NPC a script moves (`moved_objects`): the harness
    follows the live position for these; every other beat is strict."""
    lines = []
    for beat in plan.beats:
        moved_by = dict(beat.kwargs).get("moved_by")
        if moved_by:
            lines.append(
                f"- {beat.name}{_at(beat.rows[0], locate)}: event "
                f"{dict(beat.kwargs)['event_id']} moved by {', '.join(moved_by)}"
                " -- harness follows the live position")
    return lines or ["none"]


def render_review(plan: ChapterPlan, *, floor_lookup: FloorLookup,
                  locate: Locator | None = None) -> str:
    """The review document as markdown, ending in exactly one newline.
    Deterministic: same plan and floors -> same bytes. With `locate`, every
    beat and row carries its map name and tile, so the doc can be checked
    against the map viewer."""
    parts: list[str] = [f"# {plan.chapter_id} review", ""]

    parts.append("## Summary")
    parts.extend(_summary(plan, floor_lookup=floor_lookup))
    parts.append("")

    parts.append("## Order")
    parts.extend(_order(plan, locate=locate))
    parts.append("")

    parts.append("## Assertions")
    parts.extend(_assertions(plan, floor_lookup=floor_lookup, locate=locate))
    parts.append("")

    parts.append("## Refusals")
    parts.extend(_refusals(plan, locate=locate))
    parts.append("")

    parts.append("## Elsewhere")
    parts.extend(_elsewhere(plan, locate=locate))
    parts.append("")

    parts.append("## Order-dependent writes")
    parts.extend(_order_dependent(plan, floor_lookup=floor_lookup, locate=locate))
    parts.append("")

    parts.append("## Liveness order problems")
    parts.extend(_liveness_problems(plan))
    parts.append("")

    parts.append("## Scene-moved NPCs")
    parts.extend(_scene_moved(plan, locate=locate))

    return "\n".join(parts) + "\n"
