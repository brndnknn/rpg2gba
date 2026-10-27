"""Scene funnels: blank player-touch events that push the player onto a scene.

Uranium flanks a few one-cell scene triggers with blank player-touch events
whose only job is a move route on the player that lands them on the trigger
(CH11 Route 4: EV032 @(38,44) and EV033 @(40,44) push onto the bridge
warning EV070 @(39,44); the same shape recurs on maps 141, 163, 175, 216).
In Essentials the push never fires the scene -- touch triggers are checked
only at the end of a player-driven step and never while an event runs
(`Game_Player#check_event_trigger_here`) -- so the flank skips it. Operator
ruling 2026-10-27: port the intent, not the slip. The funnel is kept, and its
pushing page ends by entering the scene's touch script.

Two layers read this module and must agree: the transpiler ends the funnel's
page with `goto(touch_entry_label(target))`, and `metadata_wiring` emits that
label as an alias of the target's resolved coord-event script.
"""

from __future__ import annotations

from rpg2gba.tileset_converter.npc_gfx import select_boot_page

# RMXP command codes that make a blank touch event a SCENE rather than a
# helper: Show Text, Control Switches / Variables, Battle Processing. What is
# left after them is presentation the port carries natively or not at all --
# player-only move routes (funnels, ledge pushes), fog/tone changes, the
# `pbBridgeOn/Off` layer toggles, `pbCancelVehicles`.
SCENE_CODES = frozenset({101, 121, 122, 301})

_TRIGGER_PLAYER_TOUCH = 1
_MOVE_ROUTE = 209
_PLAYER = -1
# RMXP move-command codes 1..8 (down, left, right, up, then the diagonals).
_STEP = {1: (0, 1), 2: (-1, 0), 3: (1, 0), 4: (0, -1),
         5: (-1, 1), 6: (1, 1), 7: (-1, -1), 8: (1, -1)}


def event_has_scene(event: dict) -> bool:
    """Does any page of `event` carry a scene command (`SCENE_CODES`)?"""
    return any(cmd["code"] in SCENE_CODES
               for page in event["pages"] for cmd in page.get("list", []))


def _blank_touch(event: dict) -> bool:
    # Hand-built fixtures omit page conditions; real decoded pages carry them.
    if any("condition" not in p for p in event.get("pages", [])):
        return False
    page = select_boot_page(event)
    return (page is not None
            and not page.get("graphic", {}).get("character_name")
            and page.get("trigger") == _TRIGGER_PLAYER_TOUCH)


def page_push_landing(page: dict, x: int, y: int) -> tuple[int, int] | None:
    """Where the page's first player move route leaves a player who stepped
    onto (x, y), or None when the page never moves the player."""
    for cmd in page.get("list", []):
        if cmd["code"] == _MOVE_ROUTE and cmd["parameters"][0] == _PLAYER:
            dx = dy = 0
            for move in cmd["parameters"][1].get("list", []):
                sx, sy = _STEP.get(move["code"], (0, 0))
                dx, dy = dx + sx, dy + sy
            return x + dx, y + dy
    return None


def funnel_targets(events: list[dict | None]) -> dict[int, int]:
    """funnel event id -> scene event id for one map's events.

    A funnel is a blank player-touch event with no scene of its own whose
    boot page pushes the player onto the cell of a blank player-touch scene
    event (`event_has_scene`)."""
    live = [e for e in events if e]
    if not any(page_push_landing(p, 0, 0) is not None
               for e in live for p in e.get("pages", [])):
        return {}
    scenes = {(e["x"], e["y"]): e["id"] for e in live
              if _blank_touch(e) and event_has_scene(e)}
    out: dict[int, int] = {}
    for event in live:
        if not _blank_touch(event) or event_has_scene(event):
            continue
        landing = page_push_landing(select_boot_page(event), event["x"], event["y"])
        if landing in scenes:
            out[event["id"]] = scenes[landing]
    return out


def touch_entry_label(map_id: int, event_id: int) -> str:
    """The alias label a funnel's page `goto`s to enter the scene's touch script."""
    return f"Map{map_id:03d}_EV{event_id:03d}_TouchEntry"
