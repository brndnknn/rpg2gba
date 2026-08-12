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


def _page_move_codes(page: dict) -> set[int]:
    """Diagonal move codes from player-targeted move routes on `page`.

    Ignores code 509 (editor-display duplicates) and any move route not
    targeting the player (parameters[0] != -1).
    """
    codes: set[int] = set()
    for command in page.get("list", []):
        if command.get("code") not in _MOVE_ROUTE_CODES:
            continue
        params = command.get("parameters", [])
        if len(params) < 2 or params[0] != _MOVE_ROUTE_TARGET_PLAYER:
            continue
        move_route = params[1]
        for move_command in move_route.get("list", []):
            code = move_command.get("code")
            if code in (_MOVE_CODE_SW, _MOVE_CODE_SE, _MOVE_CODE_NW, _MOVE_CODE_NE):
                codes.add(code)
    return codes


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
    """{(x, y): side} for every diagonal-stair cell -- the layout converter's input.

    Fails loud if two stair events occupy the same cell with different sides.
    """
    sides: dict[tuple[int, int], StairSide] = {}
    for cell in detect_stair_cells(map_json):
        key = (cell.x, cell.y)
        existing = sides.get(key)
        if existing is not None and existing != cell.side:
            raise ValueError(
                f"map {map_json.get('map_id')!r} cell {key}: conflicting stair "
                f"sides ({existing} vs {cell.side}) from multiple events"
            )
        sides[key] = cell.side
    return sides
