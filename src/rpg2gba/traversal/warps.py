"""Intra-map warp-event extraction (RPG Maker XP command 201 "Transfer Player").

Mirrors `scripts/map_graph.py`'s `extract_warp_targets` shape (command code
201, parameters `[mode, dest_map, dest_x, dest_y, dest_facing, fade]`) but
keeps the full per-event record (source cell, destination cell) rather than
collapsing to a set of destination map ids — the graph needs the trigger
*cell*, not just "this map leads somewhere".

Only literal transfers (`mode == 0`) are represented; a variable-driven
transfer (`mode != 0`, destination chosen at runtime) has no fixed target to
graph and is logged, not silently dropped and not fabricated — this is the
one place decoded data cannot supply what an offline graph wants (see the
module docstring's "gap" note), so it is recorded rather than guessed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_CODE_TRANSFER_PLAYER = 201
_MODE_LITERAL = 0


@dataclass(frozen=True)
class WarpExit:
    """One literal warp trigger: standing on `cell` and firing this event
    sends the player to (`dest_map`, `dest_x`, `dest_y`)."""

    cell: tuple[int, int]
    event_id: int
    dest_map: int
    dest_x: int
    dest_y: int
    dest_facing: int  # raw RPG Maker facing code (2/4/6/8), or 0 = unchanged


def extract_warp_exits(map_json: dict) -> list[WarpExit]:
    """Every literal (mode==0) command-201 warp event in `map_json`, sorted by
    (y, x, event_id) for determinism. Variable-driven (mode!=0) transfers are
    logged at INFO and excluded — see module docstring."""
    map_id = map_json.get("map_id")
    exits: list[WarpExit] = []
    for event in map_json.get("events", []):
        if not event:
            continue
        for page in event.get("pages", []):
            for command in page.get("list", []):
                if command.get("code") != _CODE_TRANSFER_PLAYER:
                    continue
                params = command.get("parameters", [])
                if len(params) < 4:
                    continue
                mode = params[0]
                if mode != _MODE_LITERAL:
                    logger.info(
                        "map %r event %s: variable-driven warp (mode=%r) has no "
                        "fixed destination — not represented in the graph",
                        map_id, event.get("id"), mode,
                    )
                    continue
                dest_map, dest_x, dest_y = params[1], params[2], params[3]
                dest_facing = params[4] if len(params) > 4 else 0
                exits.append(
                    WarpExit(
                        cell=(event["x"], event["y"]),
                        event_id=event["id"],
                        dest_map=dest_map,
                        dest_x=dest_x,
                        dest_y=dest_y,
                        dest_facing=dest_facing,
                    )
                )
    exits.sort(key=lambda w: (w.cell[1], w.cell[0], w.event_id))
    return exits
