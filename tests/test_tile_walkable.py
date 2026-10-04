"""Tests for `Emulator.tile_walkable`'s bounds/collision semantics.

This file used to test hand `ch02.py`'s `_sight_lane_tiles` as well; those
tests were deleted with the hand suites (2026-10-03). Gated on `needs_mgba`
because the fake borrows `Emulator`'s own methods, and importing
`emulator.py` needs the mgba python bindings at module scope.
"""
import importlib.util

import pytest

needs_mgba = pytest.mark.skipif(
    importlib.util.find_spec("mgba") is None,
    reason="needs the mgba python bindings to import emulator.py",
)


# -- Emulator.tile_walkable: bounds/collision semantics ---------------------
#
# Reuses test_plan_route_grass.py's `_FakeGrassRouteEmu` shape (same style,
# not imported from it -- that file is about `_plan_route`'s Dijkstra, this
# is the plain single-tile query `_plan_route` and `tile_walkable` now
# share via the module-level `_collision_walkable`).

_MAP_OFFSET = 1
_GMAPHEADER = 0x4000
_GBACKUP = 0x3000
_LAYOUT_ADDR = 0x7000
_BACKUP_PTR = 0x9000
_COLLISION_BLOCKED = 0x0400


class _FakeMemory:
    def __init__(self) -> None:
        self._bytes: dict[int, int] = {}

    def get(self, addr: int, width: int) -> int:
        value = 0
        for i in range(width):
            value |= self._bytes.get(addr + i, 0) << (8 * i)
        return value

    def set(self, addr: int, width: int, value: int) -> None:
        for i in range(width):
            self._bytes[addr + i] = (value >> (8 * i)) & 0xFF


class _FakeTileWalkableEmu:
    """Minimal fake for `Emulator.tile_walkable` alone: a small rectangular
    map, no object events/warps involved (those are `_plan_route`-specific
    exclusions `tile_walkable` deliberately doesn't apply -- see its
    docstring)."""

    def __init__(self, map_w: int, map_h: int,
                 walls: set[tuple[int, int]] = frozenset()) -> None:
        import struct
        self.symbols = {"gBackupMapLayout": _GBACKUP, "gMapHeader": _GMAPHEADER}
        self.offsets = {
            "off_backup_width": 0, "off_backup_height": 4, "off_backup_map": 8,
            "off_mapheader_maplayout": 0,
            "off_maplayout_width": 0, "off_maplayout_height": 4,
            "val_map_offset": _MAP_OFFSET,
        }
        self._mem = _FakeMemory()
        off = _MAP_OFFSET
        w, h = map_w + (off * 2 + 1), map_h + off * 2
        self._struct = struct
        blocks = [0] * (w * h)
        for wx, wy in walls:
            blocks[(wx + off) + w * (wy + off)] = _COLLISION_BLOCKED
        self._grid_bytes = struct.pack(f"<{w * h}H", *blocks)

        self.write_u32(_GMAPHEADER, _LAYOUT_ADDR)
        self.write_u32(_LAYOUT_ADDR, map_w)
        self.write_u32(_LAYOUT_ADDR + 4, map_h)
        self.write_u32(_GBACKUP, w)
        self.write_u32(_GBACKUP + 4, h)
        self.write_u32(_GBACKUP + 8, _BACKUP_PTR)

    def u8(self, addr: int) -> int:
        return self._mem.get(addr, 1)

    def u16(self, addr: int) -> int:
        return self._mem.get(addr, 2)

    def u32(self, addr: int) -> int:
        return self._mem.get(addr, 4)

    def write_u32(self, addr: int, value: int) -> None:
        self._mem.set(addr, 4, value)

    def map_location(self):
        return (1, 1)

    def read_bytes(self, addr: int, size: int) -> bytes:
        return self._grid_bytes

    def _grid_dims_for_current_map(self):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._grid_dims_for_current_map(self)

    def _map_grid(self):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._map_grid(self)

    def tile_walkable(self, x, y):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator.tile_walkable(self, x, y)


@needs_mgba
def test_tile_walkable_true_on_clear_terrain() -> None:
    emu = _FakeTileWalkableEmu(map_w=3, map_h=3)
    assert emu.tile_walkable(1, 1) is True


@needs_mgba
def test_tile_walkable_false_on_collision() -> None:
    emu = _FakeTileWalkableEmu(map_w=3, map_h=3, walls={(1, 1)})
    assert emu.tile_walkable(1, 1) is False
    assert emu.tile_walkable(0, 1) is True


@needs_mgba
def test_tile_walkable_false_out_of_bounds_never_raises() -> None:
    emu = _FakeTileWalkableEmu(map_w=3, map_h=3)
    assert emu.tile_walkable(-1, 0) is False
    assert emu.tile_walkable(3, 0) is False
    assert emu.tile_walkable(0, 3) is False
    assert emu.tile_walkable(100, 100) is False
