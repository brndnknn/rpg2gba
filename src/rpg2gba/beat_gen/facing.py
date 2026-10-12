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
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from rpg2gba.beat_gen.plan import Elsewhere, PlannedBeat, Refusal
from rpg2gba.chapter_manifest.generator import iter_page_scopes
from rpg2gba.chapter_manifest.schema import page_row_id, parse_row_id
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


@dataclasses.dataclass(frozen=True)
class OneShot:
    """A facing-gated arm whose page ends itself: `page` is conditioned on
    self switch `switch`, and `ender` (the page trunk or an enclosing arm, or
    the arm itself) turns that switch OFF at its own level. Only one such arm
    can ever run."""

    page: str
    switch: str
    ender: str


_SELF_SWITCH = 123
_SELF_SWITCH_OFF = 1
_SIDE_ORDER = ("north", "south", "east", "west")


def one_shot_arms(map_id: int, map_data: Mapping[str, Any],
                  gated: Iterable[str]) -> dict[str, OneShot]:
    """{row id: OneShot} for each row of `gated` (facing-gated branch rows)
    that is one-shot. The off-write must sit at the level of the arm itself,
    an enclosing arm, or the page trunk -- not inside a sibling arm, which
    this arm's firing never runs."""
    wanted = set(gated)
    events = {e["id"]: e for e in map_data.get("events", []) or []}
    pages: set[tuple[int, int]] = set()
    for row_id in wanted:
        parsed = parse_row_id(row_id)
        if parsed.map_id != map_id or parsed.event_id is None or parsed.page_idx is None:
            raise ValueError(f"{row_id}: not a branch row of map {map_id}")
        pages.add((parsed.event_id, parsed.page_idx))
    out: dict[str, OneShot] = {}
    for event_id, page_idx in sorted(pages):
        event = events.get(event_id)
        if event is None:
            raise ValueError(f"map{map_id:03d}/ev{event_id:03d}: event not in map data")
        page = event["pages"][page_idx]
        cond = page.get("condition") or {}
        if not cond.get("self_switch_valid"):
            continue
        switch = cond["self_switch_ch"]
        scopes = {s.row_id: s for s in iter_page_scopes(map_id, event, page_idx, page)}
        for row_id in sorted(wanted & scopes.keys()):
            chain: list[str] = []
            cur: str | None = row_id
            while cur is not None:
                chain.append(cur)
                cur = scopes[cur].parent_row_id
            for scope_id in chain:   # arm first, then outward to the trunk
                if any(c.get("code") == _SELF_SWITCH
                       and (c.get("parameters") or [None, None])[:2] == [switch, _SELF_SWITCH_OFF]
                       for c in scopes[scope_id].commands):
                    out[row_id] = OneShot(page=chain[-1], switch=switch, ender=scope_id)
                    break
    return out


def split_facing_arms(
    beats: Sequence[PlannedBeat], sides_by_row: Mapping[str, frozenset[str]],
    one_shot: Mapping[str, OneShot] | None = None,
) -> tuple[tuple[PlannedBeat, ...], dict[str, frozenset[str]], tuple[Elsewhere, ...]]:
    """(beats with every direction-gated arm moved into its own group, {group:
    legal sides}, arms that leave the plan). Rows sharing one legal-side set
    share a beat, named `<beat>_face_<sides>` and grouped under that name,
    placed right after the beat it came from. A beat left with no rows is
    dropped. Non-generic templates are left alone: only generic beats carry
    arms.

    A *one-shot* gated arm (`one_shot`, see `one_shot_arms`) is not split: its
    page ends itself on the first firing, so one side is chosen for the beat
    -- most one-shot rows legal there, then the widest common side set, then
    north/south/east/west -- and the chosen rows stay in the original beat,
    pinned to their common sides. The other one-shot rows are returned as
    `unselected_arm` elsewhere entries."""
    one_shot = one_shot or {}
    out: list[PlannedBeat] = []
    pins: dict[str, frozenset[str]] = {}
    elsewhere: list[Elsewhere] = []
    for beat in beats:
        gated = [r for r in beat.rows if r in sides_by_row]
        if beat.template != "generic" or not gated:
            out.append(beat)
            continue
        for r in gated:
            if not sides_by_row[r]:
                raise ValueError(f"{beat.name}: arms {[r]} can run from no side "
                                 "(contradictory facing conditions)")
        shots = [r for r in gated if r in one_shot]
        chosen: list[str] = []
        pin: frozenset[str] = frozenset()
        if shots:
            best: tuple[int, int, int] | None = None
            side = ""
            for rank, cand in enumerate(_SIDE_ORDER):
                rows_here = [r for r in shots if cand in sides_by_row[r]]
                if not rows_here:
                    continue
                common = frozenset.intersection(*(sides_by_row[r] for r in rows_here))
                score = (len(rows_here), len(common), -rank)
                if best is None or score > best:
                    best, side, chosen, pin = score, cand, rows_here, common
            if best is None:
                raise ValueError(f"{beat.name}: one-shot arms {shots} share no side")
            for r in shots:
                if r not in chosen:
                    info = one_shot[r]
                    elsewhere.append(Elsewhere(
                        r, "unselected_arm",
                        detail=(f"facing arm of {info.page}, which turns self switch "
                                f"{info.switch} off after one firing ({info.ender}): the "
                                f"walk fires it once, from {side}, and takes the facing "
                                f"arms legal there (2026-10-12)")))
        split = [r for r in gated if r not in one_shot]
        free = tuple(r for r in beat.rows if r not in sides_by_row)
        keep = tuple(r for r in beat.rows if r in free or r in chosen)
        if keep:
            out.append(dataclasses.replace(beat, rows=keep))
            if chosen:
                pins[beat.group] = pin
        by_sides: dict[frozenset[str], list[str]] = {}
        for row_id in split:
            by_sides.setdefault(sides_by_row[row_id], []).append(row_id)
        for sides, row_ids in sorted(by_sides.items(), key=lambda kv: _side_key(kv[0])):
            name = f"{beat.name}_face_{_side_key(sides)}"
            out.append(dataclasses.replace(beat, name=name, group=name, rows=tuple(row_ids)))
            pins[name] = sides
    return tuple(out), pins, tuple(elsewhere)


def check_title_pages(
    beats: Sequence[PlannedBeat], trigger_of: Callable[[str], str],
) -> None:
    """A generic beat is named for the page of its first row
    (`m050e005p2`); the solver located its group from that page. When arm
    selection (`state_arms`) leaves rows of a different page, the name, group
    and approach are stale: with a different kind of trigger (autorun vs
    action) the template can't be built. The route is already solved by
    then, so re-keying is impossible -- fail loud, naming the beat."""
    for beat in beats:
        m = _TITLE.match(beat.name)
        if beat.template != "generic" or m is None or beat.group != beat.name or not beat.rows:
            continue
        title = page_row_id(int(m["map"]), int(m["event"]), int(m["page"]))
        owners = {parse_row_id(r).owning_page_row_id or r for r in beat.rows}
        if title in owners:
            continue
        triggers = {trigger_of(o) for o in owners} | {trigger_of(title)}
        if len({t in _ARRIVAL_TRIGGERS for t in triggers}) > 1:
            raise ValueError(
                f"{beat.name}: its page {title} left the beat (arms selected away) and "
                f"the surviving rows {list(beat.rows)} belong to {sorted(owners)}, a "
                f"differently-triggered page; the group was located for {title} and "
                "can't be re-keyed after the route is solved")


_TITLE = re.compile(r"^m(?P<map>\d{3})e(?P<event>\d{3})p(?P<page>\d+)$")
_ARRIVAL_TRIGGERS = frozenset({"autorun", "parallel"})


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
