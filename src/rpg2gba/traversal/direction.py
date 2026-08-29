"""Cardinal direction primitive shared by the traversal graph.

Not RMXP's own direction encoding (which uses 2/4/6/8 numpad codes — see
`tileset_converter.stairs`) and not the engine's `enum Direction` (which also
carries diagonals) — just the four presses a player can make, since that is
all the offline graph reasons about (diagonal *results* are a consequence of
a stair/ledge cell, never a press of their own).
"""
from __future__ import annotations

from enum import Enum


class Direction(Enum):
    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"

    @property
    def delta(self) -> tuple[int, int]:
        """(dx, dy) for one step in this direction. y grows downward (RMXP/GBA
        screen convention — matches `layout.TileGrid`'s row-major y)."""
        return _DELTAS[self]

    @property
    def opposite(self) -> Direction:
        return _OPPOSITE[self]


_DELTAS: dict[Direction, tuple[int, int]] = {
    Direction.NORTH: (0, -1),
    Direction.SOUTH: (0, 1),
    Direction.EAST: (1, 0),
    Direction.WEST: (-1, 0),
}

_OPPOSITE: dict[Direction, Direction] = {
    Direction.NORTH: Direction.SOUTH,
    Direction.SOUTH: Direction.NORTH,
    Direction.EAST: Direction.WEST,
    Direction.WEST: Direction.EAST,
}

CARDINALS: tuple[Direction, ...] = (
    Direction.NORTH,
    Direction.SOUTH,
    Direction.EAST,
    Direction.WEST,
)
