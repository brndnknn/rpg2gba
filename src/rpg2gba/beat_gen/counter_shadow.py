"""Counter-shadowed action pages: a third source of `never_fires`.

RPG Maker XP and pokeemerald disagree on what pressing A at a counter fires.
RMXP (`Game_Player#check_event_trigger_there`) runs the event ON the tile in
front first and reaches across the counter only if nothing fired there.
pokeemerald (`engine/src/field_control_avatar.c` `GetInteractionScript`) asks
for object events first -- including the reach across a counter to the object
one tile beyond -- and only then for a bg event on the front tile. So an
invisible RMXP event on a counter cell (emitted as a bg event) with an NPC
object directly behind it never fires on the ROM: the NPC behind answers.

2026-10-02, operator ruling (ROM run 66, Kevlar's Poke Mart, map067/ev003 --
the only such cell in the converted corpus): accept the ROM's order. The page
is `never_fires`, derived here from the emitted map, never named.
"""
from __future__ import annotations

from collections.abc import Collection

from rpg2gba.traversal.graph import MapGraph

Cell = tuple[int, int]

_DIRS: tuple[tuple[str, Cell], ...] = (
    ("north", (0, -1)), ("east", (1, 0)), ("south", (0, 1)), ("west", (-1, 0)))


def counter_shadow_proof(page_row_id: str, cell: Cell, *, graph: MapGraph,
                         object_cells: Collection[Cell]) -> str | None:
    """Why the action page `page_row_id`, whose event stands on `cell`, never
    fires on the ROM -- or None when it can. It never fires when `cell` is a
    counter, no emitted object stands on `cell` itself (the event is not an
    object, so pokeemerald reaches past it), and from every walkable side the
    player could press A from, an emitted object stands on the far side of
    the counter (a side the player can stand on: walkable, no object on it --
    the clerk's own floor behind a counter is walkable). No such side at all
    is not this rule's business (None)."""
    if cell not in graph.counters or cell in object_cells:
        return None
    x, y = cell
    sides: list[str] = []
    for side, (dx, dy) in _DIRS:
        stand = (x + dx, y + dy)
        if not graph.is_walkable(stand) or stand in object_cells:
            continue    # the player can't press A from a wall or an NPC's tile
        beyond = (x - dx, y - dy)
        if beyond not in object_cells:
            return None
        sides.append(f"{side} {stand} -> object at {beyond}")
    if not sides:
        return None
    return (f"{page_row_id}: its event on counter cell {cell} is no object event, and "
            f"pokeemerald reaches across the counter to an object first from every side "
            f"({'; '.join(sides)}) -- it never fires on the ROM")
