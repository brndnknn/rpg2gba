"""Tests for `_plan_route`'s grass-aware cost (Dijkstra/uniform-cost search
over `gBackupMapLayout`, pricing `MB_TALL_GRASS` tiles higher than ordinary
ground -- 2026-08-14 route1 B7 regression: Flood stands inside a large
grass field, so the straight-line approach crosses far more grass than a
plain shortest-hop-count BFS would ever need to, and `_walk_absorbing`'s
retry budget/cap alone couldn't keep up with the resulting encounter rate).

Same fake-memory-store style as `tests/test_plan_route_objects.py` (do not
modify that file; this is a new one, per the task) and
`tests/test_playtest.py`: no mgba dependency for the pure logic, gated on
`needs_mgba` because importing `emulator.py` itself requires the mgba python
bindings (it imports them at module scope). `Emulator`'s route-planning
methods are called unbound against `_FakeGrassRouteEmu`, which extends the
established fake shape with the pointer chain `_grass_cost_context` reads:
`gMapHeader -> mapLayout -> primary/secondaryTileset -> metatileAttributes`,
plus a fake `resolve_constants` standing in for the probe-compiled
MB_TALL_GRASS/NUM_METATILES_IN_PRIMARY/mask constants.
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
    "off_maplayout_primarytileset": 0x10, "off_maplayout_secondarytileset": 0x14,
    "off_maplayout_isfrlg": 0x18,
    "off_tileset_metatileattributes": 0x10,
    "val_map_offset": _MAP_OFFSET,
    "off_playeravatar_objecteventid": 0,
    "sizeof_objevent": 36,
    "off_objevent_localid": 8,
    "off_objevent_movementtype": 6,
    "off_objevent_graphicsid": 4,
    "off_objevent_currentcoords": 16,
    "val_object_events_count": 8,
    "val_dir_south": 1, "val_dir_north": 2, "val_dir_west": 3, "val_dir_east": 4,
    "off_mapevents_warpcount": 0, "off_mapevents_warps": 4,
    "off_warpevent_x": 0, "off_warpevent_y": 2, "sizeof_warpevent": 8,
}

# Non-FRLG (Emerald-format) constants, matching the real values probed
# against the vendored engine (see offsets.py's _CONSTANT_PROBE_TEMPLATE).
_CONSTANTS = {
    "MB_TALL_GRASS": 2,
    "NUM_METATILES_IN_PRIMARY": 512,
    "METATILE_ATTR_BEHAVIOR_MASK": 0x00FF,
    "METATILE_ATTR_BEHAVIOR_MASK_FRLG": 0x01FF,
    "MAPGRID_METATILE_ID_MASK": 0x03FF,
}

# Synthetic metatile ids used by these fixtures (arbitrary, within primary
# range so the secondary-tileset branch is never exercised here -- that
# pointer chain is still wired up on the fake for realism/completeness).
_METATILE_NORMAL = 1
_METATILE_GRASS = 2

_COLLISION_BLOCKED = 0x0400  # bits 10-11 nonzero -> (block >> 10) & 0x3 != 0

_GMAPHEADER = 0x4000
_GBACKUP = 0x3000
_GOBJEVENTS = 0x5000
_GPLAYERAVATAR = 0x6000
_LAYOUT_ADDR = 0x7000
_BACKUP_PTR = 0x9000
_PRIMARY_TILESET_ADDR = 0xA000
_SECONDARY_TILESET_ADDR = 0xB000
_PRIMARY_ATTRS_ADDR = 0xC000
_SECONDARY_ATTRS_ADDR = 0xD000
_MAPEVENTS_ADDR = 0xE000
_WARPS_ADDR = 0xE100


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


class _FakeGrassRouteEmu:
    """`_FakeRouteEmu`-shaped (`test_plan_route_objects.py`) fake, extended
    with the tileset/metatile-attribute pointer chain `_grass_cost_context`
    reads. `grass` is a set of (x, y) tiles that carry `_METATILE_GRASS`
    (behavior `MB_TALL_GRASS`) instead of `_METATILE_NORMAL`.
    """

    def __init__(self, map_w: int, map_h: int,
                 walls: set[tuple[int, int]] = frozenset(),
                 grass: set[tuple[int, int]] = frozenset()) -> None:
        self.symbols = {
            "gBackupMapLayout": _GBACKUP, "gMapHeader": _GMAPHEADER,
            "gObjectEvents": _GOBJEVENTS, "gPlayerAvatar": _GPLAYERAVATAR,
        }
        self.offsets = dict(_OFFSETS)
        self._mem = _FakeMemory()
        self._walls = set(walls)
        self._grass = set(grass)
        off = _MAP_OFFSET
        self._backup_w = map_w + (off * 2 + 1)
        self._backup_h = map_h + off * 2

        self.write_u32(_GMAPHEADER, _LAYOUT_ADDR)          # off_mapheader_maplayout
        self.write_u32(_LAYOUT_ADDR, map_w)                # off_maplayout_width
        self.write_u32(_LAYOUT_ADDR + 4, map_h)             # off_maplayout_height
        self.write_u32(_LAYOUT_ADDR + 0x10, _PRIMARY_TILESET_ADDR)
        self.write_u32(_LAYOUT_ADDR + 0x14, _SECONDARY_TILESET_ADDR)
        self.write_u8(_LAYOUT_ADDR + 0x18, 0)                # isFrlg = False
        self.write_u32(_PRIMARY_TILESET_ADDR + 0x10, _PRIMARY_ATTRS_ADDR)
        self.write_u32(_SECONDARY_TILESET_ADDR + 0x10, _SECONDARY_ATTRS_ADDR)
        # metatileAttributes[id] -- packed behavior byte, low bits.
        self.write_u16(_PRIMARY_ATTRS_ADDR + _METATILE_NORMAL * 2, 0)  # MB_NORMAL
        self.write_u16(_PRIMARY_ATTRS_ADDR + _METATILE_GRASS * 2,
                       _CONSTANTS["MB_TALL_GRASS"])
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

    def resolve_constants(self, names):
        return {name: _CONSTANTS[name] for name in names}

    def read_bytes(self, addr: int, size: int) -> bytes:
        """Synthesize the collision/metatile-id buffer from `self._walls`/
        `self._grass` rather than the byte store: each block packs a
        metatile id in the low 10 bits (`_METATILE_GRASS` where the tile is
        grass, `_METATILE_NORMAL` otherwise) and the collision bits (10-11)
        set for walls -- the same layout `UNPACK_METATILE`/`UNPACK_COLLISION`
        read in the real engine.
        """
        w, h = self._backup_w, self._backup_h
        off = _MAP_OFFSET
        blocks = [_METATILE_NORMAL] * (w * h)
        for gx, gy in self._grass:
            blocks[(gx + off) + w * (gy + off)] = _METATILE_GRASS
        for wx, wy in self._walls:
            blocks[(wx + off) + w * (wy + off)] |= _COLLISION_BLOCKED
        return struct.pack(f"<{w * h}H", *blocks)

    # -- object-event / player-avatar helpers, mirrored from
    # test_plan_route_objects.py for the exclusion-still-works tests -------

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

    def add_warp(self, x: int, y: int) -> None:
        """Wire a single warp event, matching `_warp_tiles`'s own reads
        (`gMapHeader.events -> warpCount`/`warps[i].x/y`). Only ever called
        by the one test that needs a hard-excluded (not merely costed)
        tile to contrast against grass's cost-only treatment.
        """
        o = self.offsets
        self.write_u32(self.symbols["gMapHeader"] + o["off_mapheader_events"],
                       _MAPEVENTS_ADDR)
        self.write_u8(_MAPEVENTS_ADDR + o["off_mapevents_warpcount"], 1)
        self.write_u32(_MAPEVENTS_ADDR + o["off_mapevents_warps"], _WARPS_ADDR)
        self.write_u16(_WARPS_ADDR + o["off_warpevent_x"], x)
        self.write_u16(_WARPS_ADDR + o["off_warpevent_y"], y)

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

    def _grass_cost_context(self):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._grass_cost_context(self)

    def _plan_route(self, start, goal):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._plan_route(self, start, goal)


class _FakeGrassRouteEmuNoContext(_FakeGrassRouteEmu):
    """Same fake, but WITHOUT `_grass_cost_context` -- the
    AttributeError-degrade shape `_plan_route` falls back to for fakes that
    predate the grass primitive (`test_plan_route_objects.py`'s
    `_FakeRouteEmu`). Overriding `__getattribute__` to raise makes the
    attribute lookup itself fail, the same shape a fake that never defined
    the method at all would produce -- a plain `del` can't remove an
    inherited method from an instance.
    """

    def __getattribute__(self, name):
        if name == "_grass_cost_context":
            raise AttributeError(name)
        return object.__getattribute__(self, name)


@needs_mgba
def test_route_detours_around_grass_when_clear_alternative_exists() -> None:
    """Straight line (0,1)->(4,1) crosses one grass tile at (2,1) (cost:
    3*1 + 1*5 = 8 for the direct 4-step path). A same-shape detour along
    the clear top row is 6 plain steps (cost 6) -- cheaper -- so the
    planner must prefer it and never enter the grass tile at all."""
    emu = _FakeGrassRouteEmu(map_w=5, map_h=3, grass={(2, 1)})

    route = emu._plan_route((0, 1), (4, 1))

    assert route is not None
    assert (2, 1) not in route
    assert route[0] == (0, 1) and route[-1] == (4, 1)


@needs_mgba
def test_route_still_crosses_grass_when_it_is_the_only_option() -> None:
    """A single-row corridor: no alternative row exists, so the only route
    from (0,0) to (4,0) passes through the grass tile at (2,0). Cost bias
    must never make an otherwise-walkable grass tile impassable."""
    emu = _FakeGrassRouteEmu(map_w=5, map_h=1, grass={(2, 0)})

    route = emu._plan_route((0, 0), (4, 0))

    assert route is not None
    assert (2, 0) in route
    assert route[0] == (0, 0) and route[-1] == (4, 0)


@needs_mgba
def test_grass_goal_tile_is_still_reachable() -> None:
    """The GOAL itself being grass (B4's cells, Flood standing in a field)
    must never make it unroutable -- cost only ever biases path
    *selection*, never reachability."""
    emu = _FakeGrassRouteEmu(map_w=3, map_h=3, grass={(2, 2)})

    route = emu._plan_route((0, 0), (2, 2))

    assert route is not None
    assert route[-1] == (2, 2)


@needs_mgba
def test_grass_cost_does_not_break_object_event_exclusion() -> None:
    """An active object event still forces a detour around its tile even
    when a grass tile sits elsewhere on the map -- the two exclusion/cost
    mechanisms must compose, not interfere."""
    emu = _FakeGrassRouteEmu(map_w=3, map_h=3, grass={(0, 2)})
    emu.set_player_slot(0)
    emu.add_object(1, x=1, y=1, local_id=5)  # sits on the direct (0,1)->(2,1) line

    route = emu._plan_route((0, 1), (2, 1))

    assert route is not None
    assert (1, 1) not in route  # still detours around the NPC
    assert route[0] == (0, 1) and route[-1] == (2, 1)


@needs_mgba
def test_grass_cost_does_not_break_warp_exclusion() -> None:
    """A warp tile is hard-excluded (never routable except as the goal),
    which is a different mechanism from grass's soft cost bias -- the two
    must compose correctly rather than one masking the other.

    Layout (2 rows, 3 cols): direct line (0,0)->(1,0)[grass]->(2,0) costs
    1+5=6. The only alternative, via row 1, would normally be cheaper (4)
    -- see the detour test above -- but (1,1) on that detour is a warp
    tile, which `walkable()` must refuse regardless of cost. With that
    detour cut off entirely, the route has no choice but to cross the
    grass: proof that warp exclusion is checked ahead of (and independent
    of) grass cost, not merely a higher cost itself.
    """
    emu = _FakeGrassRouteEmu(map_w=3, map_h=2, grass={(1, 0)})
    emu.add_warp(1, 1)

    route = emu._plan_route((0, 0), (2, 0))

    assert route is not None
    assert (1, 1) not in route  # the warp tile is never entered
    assert (1, 0) in route      # forced through grass instead
    assert route[0] == (0, 0) and route[-1] == (2, 0)


@needs_mgba
def test_missing_grass_context_degrades_to_flat_cost(caplog) -> None:
    """If the tileset/metatile-attribute pointer chain can't be resolved
    (or, as here, `_grass_cost_context` is entirely absent -- a fake that
    predates this primitive), routing must degrade to flat per-tile costs,
    i.e. today's plain-BFS shortest-hop-count behaviour: the direct route
    through grass, not the longer detour a cost-aware planner would take."""
    emu = _FakeGrassRouteEmuNoContext(map_w=5, map_h=3, grass={(2, 1)})

    route = emu._plan_route((0, 1), (4, 1))

    assert route is not None
    assert route == [(0, 1), (1, 1), (2, 1), (3, 1), (4, 1)]
