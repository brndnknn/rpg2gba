"""Detector for RMXP diagonal-stair "player touch" events.

RPG Maker XP has no native diagonal-stair tile behavior. Uranium (like stock
Essentials) fakes it with a scripted event: the staircase cell is a solid
("through": false) player-touch (trigger 1) event. Its command list branches
on the player's facing direction (command 111, condition kind 6 = "character
direction", character id -1 = the player) and then force-moves the player one
tile diagonally via a "set move route" command (205 or 209) targeting the
player (parameters[0] == -1), whose embedded RPG::MoveRoute contains one or
more of RMXP's diagonal move codes: 5 = lower-left (SW), 6 = lower-right (SE),
7 = upper-left (NW), 8 = upper-right (NE).

Our pipeline never implemented that script idiom, so it converted to an empty
stub and the cell stayed solid -- stairs became walls in the ROM.

The approved fix drops the script entirely and uses pokeemerald-expansion's
NATIVE sideways-stairs metatile behaviors instead: putting
MB_SIDEWAYS_STAIRS_LEFT_SIDE or MB_SIDEWAYS_STAIRS_RIGHT_SIDE on a passable
tile makes the engine automatically redirect an east/west step into a
diagonal step, with no event or script involved
(engine/include/constants/metatile_behaviors.h:78-83,
engine/src/event_object_movement.c:6681).

Axis rule (derived from a complete census of all 228 diagonal-stair events
across the 28 maps that contain them -- this rule is total):

    MB_SIDEWAYS_STAIRS_RIGHT_SIDE moves the player northwest on a westward
    step onto the tile and southeast on an eastward step off it -> the
    NW/SE axis -> RMXP move codes {6, 7}.

    MB_SIDEWAYS_STAIRS_LEFT_SIDE is the NE/SW axis -> RMXP move codes
    {5, 8}.

This module only detects and classifies; it has no side effects and does not
touch the layout converter or any output. Consumers (the layout converter)
use it to know which cells get which behavior, and which events to skip
entirely since the script itself is no longer emitted.

Multi-step staircases (`lane_cells`): the engine moves one diagonal per
press, but a Uranium stair event moves the player k diagonals per touch
(k = 2 for 156 of the corpus's 228 events, 4 for Map216's four). A 2x2
staircase therefore has four events but needs six stair cells natively --
the two cells a crossing passes between event cells were never stamped, and
a crossing up the lower lane stopped halfway (CH06 walk, Map14002). Each
k-step route contributes, from its event cell S:

    up   (codes 7/8, entered pressing W/E): the cell pressed into at every
         step, S + i*(dx, -1), and every intermediate landing, the cell
         above each -- the last landing is left alone, the press off it is a
         plain step.
    down (codes 5/6, entered by a plain step onto S): every cell stood on
         before the next diagonal, S + i*(dx, +1).

For k = 1 this adds nothing beyond S, so single-step staircases are
unchanged (census 2026-10-13: zero extra cells on any k = 1 staircase).

Note: RPG Maker's editor stores code 509 entries as display duplicates of
move-route move commands, for showing the route in the event list UI. They
are not real commands and carry no independent payload; this module ignores
them entirely. The real move codes live inside the "list" of the 205/209
command's embedded move route.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

_CONDITION_KIND_CHARACTER_DIRECTION = 6
_CONDITION_CHARACTER_PLAYER = -1
_TRIGGER_PLAYER_TOUCH = 1
_CODE_CONDITIONAL_BRANCH = 111
_MOVE_ROUTE_CODES = (205, 209)
_MOVE_ROUTE_TARGET_PLAYER = -1

# RMXP diagonal move-route command codes.
_MOVE_CODE_SW = 5
_MOVE_CODE_SE = 6
_MOVE_CODE_NW = 7
_MOVE_CODE_NE = 8

_AXIS_NW_SE = frozenset({_MOVE_CODE_NW, _MOVE_CODE_SE})
_AXIS_NE_SW = frozenset({_MOVE_CODE_NE, _MOVE_CODE_SW})


class StairSide(Enum):
    """Which native sideways-stairs metatile behavior a stair cell needs."""

    LEFT = "left"  # MB_SIDEWAYS_STAIRS_LEFT_SIDE  -- NE/SW axis
    RIGHT = "right"  # MB_SIDEWAYS_STAIRS_RIGHT_SIDE -- NW/SE axis


BEHAVIOR_BY_SIDE: dict[StairSide, str] = {
    StairSide.LEFT: "MB_SIDEWAYS_STAIRS_LEFT_SIDE",
    StairSide.RIGHT: "MB_SIDEWAYS_STAIRS_RIGHT_SIDE",
}


@dataclass(frozen=True)
class StairCell:
    """A single diagonal-stair event, resolved to the engine behavior it needs."""

    x: int
    y: int
    side: StairSide
    event_id: int


def _page_qualifies(page: dict) -> bool:
    """True if `page` has the trigger + 111-branch shape of a stair script."""
    if page.get("trigger") != _TRIGGER_PLAYER_TOUCH:
        return False
    for command in page.get("list", []):
        if command.get("code") != _CODE_CONDITIONAL_BRANCH:
            continue
        params = command.get("parameters", [])
        if (
            len(params) >= 2
            and params[0] == _CONDITION_KIND_CHARACTER_DIRECTION
            and params[1] == _CONDITION_CHARACTER_PLAYER
        ):
            return True
    return False


def _page_routes(page: dict) -> list[list[int]]:
    """The diagonal move codes of each player-targeted move route on `page`,
    in order, one list per route that has any.

    Ignores code 509 (editor-display duplicates) and any move route not
    targeting the player (parameters[0] != -1).
    """
    routes: list[list[int]] = []
    for command in page.get("list", []):
        if command.get("code") not in _MOVE_ROUTE_CODES:
            continue
        params = command.get("parameters", [])
        if len(params) < 2 or params[0] != _MOVE_ROUTE_TARGET_PLAYER:
            continue
        move_route = params[1]
        diagonals = [
            move_command.get("code")
            for move_command in move_route.get("list", [])
            if move_command.get("code") in (_MOVE_CODE_SW, _MOVE_CODE_SE, _MOVE_CODE_NW, _MOVE_CODE_NE)
        ]
        if diagonals:
            routes.append(diagonals)
    return routes


def _page_move_codes(page: dict) -> set[int]:
    """Diagonal move codes from player-targeted move routes on `page`."""
    return {code for route in _page_routes(page) for code in route}


# (dx, rising) per diagonal code: rising routes are entered by the press that
# triggers the redirect; falling ones by a plain step onto the event cell.
_ROUTE_SHAPE: dict[int, tuple[int, bool]] = {
    _MOVE_CODE_NW: (-1, True),
    _MOVE_CODE_NE: (1, True),
    _MOVE_CODE_SW: (-1, False),
    _MOVE_CODE_SE: (1, False),
}


def lane_cells(x: int, y: int, route: list[int], *, map_id: object, event_id: int) -> set[tuple[int, int]]:
    """Every cell the native one-diagonal-per-press crossing of a k-step
    `route` from event cell (x, y) needs stair behavior on (module docstring).
    Fails loud on a route that changes diagonal direction mid-way."""
    if len(set(route)) != 1:
        raise ValueError(
            f"map {map_id!r} event {event_id}: stair move route changes diagonal "
            f"direction mid-way ({route}); only a straight k-step run is understood"
        )
    dx, rising = _ROUTE_SHAPE[route[0]]
    k = len(route)
    cells: set[tuple[int, int]] = set()
    for i in range(k):
        if rising:
            cells.add((x + i * dx, y - i))
            if i < k - 1:
                cells.add((x + i * dx, y - i - 1))
        else:
            cells.add((x + i * dx, y + i))
    return cells


def _classify(codes: set[int], *, map_id: object, event_id: int) -> StairSide | None:
    """Classify a merged move-code set into a StairSide, or None if not a stair."""
    if not codes:
        return None
    if codes <= _AXIS_NW_SE:
        return StairSide.RIGHT
    if codes <= _AXIS_NE_SW:
        return StairSide.LEFT
    raise ValueError(
        f"map {map_id!r} event {event_id}: diagonal move codes mix both stair "
        f"axes ({sorted(codes)}); a sideways-stairs event must use only "
        f"{{6,7}} (NW/SE) or {{5,8}} (NE/SW)"
    )


def detect_stair_cells(map_json: dict) -> list[StairCell]:
    """Every diagonal-stair event in `map_json`, sorted by (y, x) for determinism."""
    map_id = map_json.get("map_id")
    cells: list[StairCell] = []
    for event in map_json.get("events", []):
        if not event:
            continue
        codes: set[int] = set()
        for page in event.get("pages", []):
            if _page_qualifies(page):
                codes |= _page_move_codes(page)
        side = _classify(codes, map_id=map_id, event_id=event["id"])
        if side is None:
            continue
        cells.append(StairCell(x=event["x"], y=event["y"], side=side, event_id=event["id"]))
    cells.sort(key=lambda c: (c.y, c.x))
    return cells


def stair_event_ids(map_json: dict) -> set[int]:
    """Event ids of every diagonal-stair event in `map_json`."""
    return {cell.event_id for cell in detect_stair_cells(map_json)}


def stair_cell_sides(map_json: dict) -> dict[tuple[int, int], StairSide]:
    """{(x, y): side} for every cell that needs a sideways-stairs behavior --
    the layout converter's and traversal graph's input. That is every stair
    event's own cell plus, for multi-step routes, the `lane_cells` between
    them (which carry no event).

    Fails loud if two stair events claim the same cell with different sides.
    """
    map_id = map_json.get("map_id")
    sides: dict[tuple[int, int], StairSide] = {}
    events = {event["id"]: event for event in map_json.get("events", []) if event}
    for cell in detect_stair_cells(map_json):
        claimed = {(cell.x, cell.y)}
        for page in events[cell.event_id].get("pages", []):
            if not _page_qualifies(page):
                continue
            for route in _page_routes(page):
                claimed |= lane_cells(cell.x, cell.y, route, map_id=map_id, event_id=cell.event_id)
        for key in sorted(claimed):
            existing = sides.get(key)
            if existing is not None and existing != cell.side:
                raise ValueError(
                    f"map {map_id!r} cell {key}: conflicting stair "
                    f"sides ({existing} vs {cell.side}) from multiple events"
                )
            sides[key] = cell.side
    return sides
