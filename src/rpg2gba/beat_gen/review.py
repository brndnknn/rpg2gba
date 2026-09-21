"""Stage 8: `ChapterPlan` -> `output/beats/CHnn.review.md` (C6 Task 8; R7, C2).

The review doc is part of the §9 per-chapter boot gate (C6 plan C2): the
operator reads and approves it before the generated module replaces a hand
module. It is the ONLY human-visible record of the solver's picks, so it
must show every pick, every refusal and every order-dependent write.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from rpg2gba.beat_floor.assertion import FloorAssertion, RowFloor
from rpg2gba.beat_gen.plan import BLOCKERS, ChapterPlan, PlannedBeat

logger = logging.getLogger(__name__)

FloorLookup = Callable[[str], RowFloor]

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


def _order(plan: ChapterPlan) -> list[str]:
    lines = ["| beat | template | group | rows | pick |", "|---|---|---|---|---|"]
    for beat in plan.beats:
        lines.append(
            f"| {beat.name} | {beat.template} | {beat.group} | "
            f"{len(beat.rows)} | {_pick(beat)} |")
    return lines


def _assertions(plan: ChapterPlan, *, floor_lookup: FloorLookup) -> list[str]:
    lines: list[str] = []
    for beat in plan.beats:
        lines.append(f"### {beat.name}")
        for row_id in beat.rows:
            floor = floor_lookup(row_id)
            kinds = sorted({a.kind for a in floor.assertions})
            mode = "offline" if floor.offline_eligible else "ROM"
            lines.append(f"- {row_id}: kinds {', '.join(kinds) or 'none'} -- {mode}")
    return lines


def _refusals(plan: ChapterPlan) -> list[str]:
    if not plan.refusals:
        return ["none"]
    by_blocker: dict[str, list[str]] = {b: [] for b in _BLOCKER_ORDER}
    for r in plan.refusals:
        by_blocker[r.blocker].append(f"- {r.row_id}: {r.reason} -- {r.detail}")
    lines: list[str] = []
    for blocker in _BLOCKER_ORDER:
        entries = by_blocker[blocker]
        if not entries:
            continue
        lines.append(f"### {blocker}")
        lines.extend(sorted(entries))
    return lines


def _elsewhere(plan: ChapterPlan) -> list[str]:
    if not plan.elsewhere:
        return ["none"]
    lines: list[str] = []
    for e in plan.elsewhere:
        if e.status == "later":
            lines.append(f"- {e.row_id}: later -- owner {e.owner}")
        elif e.status == "blocked":
            lines.append(f"- {e.row_id}: blocked -- requires {', '.join(e.requires)}")
        else:
            lines.append(f"- {e.row_id}: {e.status}")
    return lines


def _order_dependent(plan: ChapterPlan, *, floor_lookup: FloorLookup) -> list[str]:
    if not plan.order_dependent:
        return ["none"]
    lines: list[str] = []
    for odk in sorted(plan.order_dependent, key=lambda k: k.key):
        assertion_kind, match = _parse_order_dependent_key(odk.key)
        ordered_writers = sorted(odk.writers, key=lambda rid: _beat_position(plan, rid))
        last_floor = floor_lookup(ordered_writers[-1])
        landing = _write_value(last_floor, assertion_kind, match)
        lines.append(
            f"- {odk.key}: order taken {' -> '.join(ordered_writers)} -- lands {landing!r}")
    return lines


def render_review(plan: ChapterPlan, *, floor_lookup: FloorLookup) -> str:
    """The review document as markdown, ending in exactly one newline.
    Deterministic: same plan and floors -> same bytes."""
    parts: list[str] = [f"# {plan.chapter_id} review", ""]

    parts.append("## Summary")
    parts.extend(_summary(plan, floor_lookup=floor_lookup))
    parts.append("")

    parts.append("## Order")
    parts.extend(_order(plan))
    parts.append("")

    parts.append("## Assertions")
    parts.extend(_assertions(plan, floor_lookup=floor_lookup))
    parts.append("")

    parts.append("## Refusals")
    parts.extend(_refusals(plan))
    parts.append("")

    parts.append("## Elsewhere")
    parts.extend(_elsewhere(plan))
    parts.append("")

    parts.append("## Order-dependent writes")
    parts.extend(_order_dependent(plan, floor_lookup=floor_lookup))

    return "\n".join(parts) + "\n"
