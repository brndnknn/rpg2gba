"""Which events some page's script moves -- the "flag" half of the operator's
"flag + live" ruling (ROM run 24).

The flavour-NPC harness derives an approach cell from an NPC's TEMPLATE
position. An NPC that a scene walks (RMXP Set Move Route, code 209, or Set
Event Location, code 202) is elsewhere by the time a later talk page runs;
ROM run 24 failed on the professor (map050 ev5, walked one cell right by his
own earlier page) because the talk beat pressed A at a template-derived cell
and talked to nothing. Only events flagged here may follow the NPC's live
position; every unflagged beat stays strict and fails loud on a mismatch.

A page moves event E when it holds
  * code 209 whose target is E (0 = the page's own event) and whose move
    route has a position-changing move code (RMXP 1-14: the four steps, the
    four diagonals, random, toward, away, forward, backward, jump). Turn-only
    and other codes do not count;
  * code 202 whose target is E (0 = own event).
Target -1 (the player) is ignored.

Limitations, deliberately: common-event calls (code 117) are not followed,
so a move hidden inside a common event is not flagged. A move followed by a
transfer (the NPC never gets to matter afterwards) is still flagged --
over-inclusion only relaxes the strict check for that one NPC, which is the
safe direction.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from rpg2gba.chapter_manifest.schema import page_row_id

_SET_MOVE_ROUTE = 209
_SET_EVENT_LOCATION = 202
#: RMXP move commands that change position (1-4 steps, 5-8 diagonals, 9
#: random, 10 toward, 11 away, 12 forward, 13 backward, 14 jump).
_POSITION_MOVES = frozenset(range(1, 15))


def _target(params: object, own_event: int, row_id: str, code: int) -> int:
    if not isinstance(params, list) or not params or not isinstance(params[0], int):
        raise ValueError(f"moved_objects: {row_id}: malformed code {code} parameters {params!r}")
    return own_event if params[0] == 0 else params[0]


def _route_moves(params: list, row_id: str) -> bool:
    route = params[1] if len(params) > 1 else None
    steps = route.get("list") if isinstance(route, Mapping) else None
    if not isinstance(steps, list):
        raise ValueError(f"moved_objects: {row_id}: code 209 without a move route list")
    codes = []
    for step in steps:
        if not isinstance(step, Mapping) or not isinstance(step.get("code"), int):
            raise ValueError(f"moved_objects: {row_id}: malformed move command {step!r}")
        codes.append(step["code"])
    return any(c in _POSITION_MOVES for c in codes)


def scene_moved_events(
    map_id: int, events: Sequence[Mapping | None],
) -> dict[int, tuple[str, ...]]:
    """event id -> sorted row ids of the pages (on this map) whose script
    moves it. Events nobody moves are absent. `events` is the map JSON's
    `events` list (None holes allowed). Raises `ValueError` naming the row on
    a malformed 209/202 command."""
    moved: dict[int, set[str]] = {}
    for event in events:
        if not event:
            continue
        for page_idx, page in enumerate(event.get("pages") or []):
            row_id = page_row_id(map_id, event["id"], page_idx)
            for cmd in page.get("list") or []:
                code = cmd.get("code")
                if code == _SET_MOVE_ROUTE:
                    target = _target(cmd.get("parameters"), event["id"], row_id, code)
                    if target != -1 and _route_moves(cmd["parameters"], row_id):
                        moved.setdefault(target, set()).add(row_id)
                elif code == _SET_EVENT_LOCATION:
                    target = _target(cmd.get("parameters"), event["id"], row_id, code)
                    if target != -1:
                        moved.setdefault(target, set()).add(row_id)
    return {eid: tuple(sorted(rows)) for eid, rows in sorted(moved.items())}
