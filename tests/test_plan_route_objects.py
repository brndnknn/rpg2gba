"""Tests for `_plan_route` treating active object-event tiles as blocked
(ROM_TEST_DEV.md C6 — Route 1's 44 reachable events, including a 6-boulder
cluster, made the terrain-only BFS route the player straight into a solid
NPC/Rock event).

Same fake-memory-store style as `tests/test_playtest.py` and
`tests/test_object_events.py`: no mgba dependency for the pure logic, an
importability guard (`needs_mgba`) because importing `emulator.py` itself
requires the mgba python bindings to be installed (it imports them at module
scope). `Emulator`'s route-planning methods are called unbound against
`_FakeRouteEmu`, which fakes just what they read: the map grid
(`gBackupMapLayout`/`gMapHeader`), the object-event table (`gObjectEvents`),
and the player's own object slot (`gPlayerAvatar.objectEventId`).
"""
import importlib.util
import struct

import pytest

needs_mgba = pytest.mark.skipif(
    importlib.util.find_spec("mgba") is None,
    reason="needs the mgba python bindings to import emulator.py",
)

_MAP_OFFSET = 1  # arbitrary small bias -- only its role as MAP_OFFSET matters here

_OFFSETS = {
    "off_backup_width": 0, "off_backup_height": 4, "off_backup_map": 8,
    "off_mapheader_maplayout": 0, "off_mapheader_events": 4,
    "off_maplayout_width": 0, "off_maplayout_height": 4,
    "val_map_offset": _MAP_OFFSET,
    "off_playeravatar_objecteventid": 0,
    "sizeof_objevent": 36,
    "off_objevent_localid": 8,
    "off_objevent_movementtype": 6,
    "off_objevent_graphicsid": 4,
    "off_objevent_currentcoords": 16,
    "val_object_events_count": 8,
    "val_dir_south": 1, "val_dir_north": 2, "val_dir_west": 3, "val_dir_east": 4,
}

_COLLISION_BLOCKED = 0x0400  # bits 10-11 nonzero -> (block >> 10) & 0x3 != 0

_GMAPHEADER = 0x4000
_GBACKUP = 0x3000
_GOBJEVENTS = 0x5000
_GPLAYERAVATAR = 0x6000
_LAYOUT_ADDR = 0x7000
_BACKUP_PTR = 0x9000


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


class _FakeRouteEmu:
    """Stands up a small rectangular map with no warps and an empty object
    table by default; tests add walls/objects on top.

    `_plan_route`/`_occupied_object_tiles`/`_player_object_slot`/`_map_grid`/
    `_grid_dims_for_current_map`/`_warp_tiles` are borrowed unbound from the
    real `Emulator` (same pattern `_FakeGridEmu`/`_FakeWalkEmu` use in
    `tests/test_playtest.py`) so the code under test is the real
    implementation, not a reimplementation of it.
    """

    def __init__(self, map_w: int, map_h: int,
                 walls: set[tuple[int, int]] = frozenset()) -> None:
        self.symbols = {
            "gBackupMapLayout": _GBACKUP, "gMapHeader": _GMAPHEADER,
            "gObjectEvents": _GOBJEVENTS, "gPlayerAvatar": _GPLAYERAVATAR,
        }
        self.offsets = dict(_OFFSETS)
        self._mem = _FakeMemory()
        self._walls = set(walls)
        off = _MAP_OFFSET
        self._backup_w = map_w + (off * 2 + 1)
        self._backup_h = map_h + off * 2

        self.write_u32(_GMAPHEADER, _LAYOUT_ADDR)          # off_mapheader_maplayout
        self.write_u32(_LAYOUT_ADDR, map_w)                # off_maplayout_width
        self.write_u32(_LAYOUT_ADDR + 4, map_h)             # off_maplayout_height
        # off_mapheader_events stays 0 -> _warp_tiles() sees no events table.
        self.write_u32(_GBACKUP, self._backup_w)            # off_backup_width
        self.write_u32(_GBACKUP + 4, self._backup_h)        # off_backup_height
        self.write_u32(_GBACKUP + 8, _BACKUP_PTR)           # off_backup_map

    # -- raw access, matching Emulator's u8/u16/u32/write_* signatures ------

    def u8(self, addr: int) -> int:
        return self._mem.get(addr, 1)

    def u16(self, addr: int) -> int:
        return self._mem.get(addr, 2)

    def u32(self, addr: int) -> int:
        return self._mem.get(addr, 4)

    def write_u8(self, addr: int, value: int) -> None:
        self._mem.set(addr, 1, value)

    def write_u16(self, addr: int, value: int) -> None:
        self._mem.set(addr, 2, value)

    def write_u32(self, addr: int, value: int) -> None:
        self._mem.set(addr, 4, value)

    def map_location(self) -> tuple[int, int]:
        return (1, 1)  # arbitrary; only surfaced in error messages here

    def read_bytes(self, addr: int, size: int) -> bytes:
        """Synthesize the collision buffer from `self._walls` rather than
        the byte store -- the buffer is bigger than is convenient to poke
        byte-by-byte, and the wall set is the thing each test wants to say
        directly."""
        w, h = self._backup_w, self._backup_h
        off = _MAP_OFFSET
        blocks = [0] * (w * h)
        for wx, wy in self._walls:
            blocks[(wx + off) + w * (wy + off)] = _COLLISION_BLOCKED
        return struct.pack(f"<{w * h}H", *blocks)

    # -- object-event / player-avatar helpers used by the fixtures ----------

    def add_object(self, slot: int, *, x: int, y: int, active: bool = True,
                    local_id: int = 1, facing: int = 1, graphics_id: int = 0,
                    movement_type: int = 0) -> None:
        o = self.offsets
        base = self.symbols["gObjectEvents"] + slot * o["sizeof_objevent"]
        self.write_u8(base + 0, 1 if active else 0)  # OBJEVENT_ACTIVE_*
        self.write_u8(base + o["off_objevent_localid"], local_id)
        self.write_u8(base + o["off_objevent_movementtype"], movement_type)
        self.write_u16(base + o["off_objevent_graphicsid"], graphics_id)
        coords = base + o["off_objevent_currentcoords"]
        self.write_u16(coords, x + _MAP_OFFSET)
        self.write_u16(coords + 2, y + _MAP_OFFSET)
        self.write_u8(base + 0x18, facing & 0x0F)  # OBJEVENT_FACING_*

    def set_player_slot(self, slot: int) -> None:
        self.write_u8(self.symbols["gPlayerAvatar"]
                       + self.offsets["off_playeravatar_objecteventid"], slot)

    # -- code under test, borrowed unbound from the real class --------------

    def _grid_dims_for_current_map(self):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._grid_dims_for_current_map(self)

    def _map_grid(self):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._map_grid(self)

    def _warp_tiles(self):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._warp_tiles(self)

    def _player_object_slot(self):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._player_object_slot(self)

    def _occupied_object_tiles(self, goal):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._occupied_object_tiles(self, goal)

    def _plan_route(self, start, goal):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._plan_route(self, start, goal)


@needs_mgba
def test_route_detours_around_an_occupied_tile() -> None:
    """A clear terrain path exists straight through (1,1); an active object
    event sits on it, so the route must go around, not through."""
    emu = _FakeRouteEmu(map_w=3, map_h=3)
    emu.set_player_slot(0)
    emu.add_object(1, x=1, y=1, local_id=5)

    route = emu._plan_route((0, 1), (2, 1))

    assert route is not None
    assert (1, 1) not in route
    assert route[0] == (0, 1) and route[-1] == (2, 1)


@needs_mgba
def test_goal_tile_occupied_is_still_routable_onto() -> None:
    """Approaching an NPC is a normal walk_to shape: the goal itself is the
    NPC's tile, and the route must still be planned exactly onto it."""
    emu = _FakeRouteEmu(map_w=3, map_h=3)
    emu.set_player_slot(0)
    emu.add_object(1, x=2, y=2, local_id=5)  # sits on the goal tile

    route = emu._plan_route((0, 0), (2, 2))

    assert route is not None
    assert route[-1] == (2, 2)


@needs_mgba
def test_players_own_object_event_never_blocks() -> None:
    """The player's object is identified by `gPlayerAvatar.objectEventId`,
    not by assuming slot 0. Put the player's object on slot 2, sitting on a
    tile the route must cross, and confirm it does not detour around it --
    while a genuine NPC on a different slot still forces a detour."""
    emu = _FakeRouteEmu(map_w=3, map_h=3)
    emu.set_player_slot(2)
    emu.add_object(2, x=1, y=1, local_id=9)   # the player's own object
    emu.add_object(3, x=1, y=0, local_id=5)   # a real NPC, off the direct line

    route = emu._plan_route((0, 1), (2, 1))

    assert route is not None
    assert (1, 1) in route          # player's own tile is never excluded
    assert (1, 0) not in route      # the other NPC's tile still is


@needs_mgba
def test_inactive_object_events_are_ignored() -> None:
    emu = _FakeRouteEmu(map_w=3, map_h=3)
    emu.set_player_slot(0)
    emu.add_object(1, x=1, y=1, local_id=5, active=False)

    route = emu._plan_route((0, 1), (2, 1))

    assert route == [(0, 1), (1, 1), (2, 1)]


@needs_mgba
def test_object_event_read_failure_degrades_to_terrain_only(caplog) -> None:
    """If reading the object-event table blows up, `_plan_route` must not
    raise -- it falls back to today's terrain-only behaviour and logs the
    degradation, per the harness rule that a planning heuristic never fails
    a scenario."""
    import logging

    emu = _FakeRouteEmu(map_w=3, map_h=3)
    # No gPlayerAvatar symbol at all -> _player_object_slot's self.symbols[...]
    # lookup raises KeyError, which _occupied_object_tiles must swallow.
    del emu.symbols["gPlayerAvatar"]
    emu.add_object(1, x=1, y=1, local_id=5)  # would block if reads worked

    with caplog.at_level(logging.INFO, logger="rpg2gba.playtest.emulator"):
        route = emu._plan_route((0, 1), (2, 1))

    assert route == [(0, 1), (1, 1), (2, 1)]  # object ignored, terrain only
    assert "degrading to terrain-only" in caplog.text


@needs_mgba
def test_occupied_object_tiles_excludes_player_slot_and_goal() -> None:
    """Direct unit coverage of the helper itself, independent of BFS."""
    emu = _FakeRouteEmu(map_w=5, map_h=5)
    emu.set_player_slot(0)
    emu.add_object(0, x=0, y=0, local_id=1)   # player -- excluded
    emu.add_object(1, x=2, y=2, local_id=2)   # goal tile -- excluded
    emu.add_object(2, x=3, y=1, local_id=3)   # a real obstacle

    occupied = emu._occupied_object_tiles(goal=(2, 2))

    assert occupied == {(3, 1)}
