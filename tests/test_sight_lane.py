"""Tests for `route1.py`'s `_sight_lane_tiles` (and its two callers picking
the farthest tile it returns) -- the 2026-08-14 B7 regression: `_approach_
sight_trainer` used to walk a hardcoded standoff distance without checking
it was walkable at all. Verified against the compiled collision grid, EVERY
reachable trainer's sight lane hits a wall well inside that assumed
distance (Lynette's is only one tile deep), so `walk_to` planned onto solid
terrain and the greedy stepper ground out after 8 step-aside attempts.

Same style as `tests/test_walk_interruption.py`: a bare fake implementing
only what the code under test reads (`object_events`/`tile_walkable`/
`screenshot`), gated on `needs_mgba` because `route1.py` imports
`WalkInterrupted` from `emulator.py` (lazily, at call time) and constructing
a real `ObjectEventState` requires importing `emulator.py`, which needs the
mgba python bindings at module scope.
"""
import importlib.util

import pytest

needs_mgba = pytest.mark.skipif(
    importlib.util.find_spec("mgba") is None,
    reason="needs the mgba python bindings to import emulator.py",
)


class _FakeSightLaneEmu:
    """Exposes exactly what `_sight_lane_tiles` reads: `object_events()`
    (to locate the trainer's own `ObjectEventState`, for its live
    `trainer_range`) and `tile_walkable(x, y)` (a plain lookup against a
    fixed walkable-tile set -- no grid/collision simulation needed at this
    level, that's `test_plan_route_grass.py`'s/`Emulator.tile_walkable`'s
    own concern)."""

    def __init__(self, walkable: set[tuple[int, int]], trainer_ev=None) -> None:
        self._walkable = set(walkable)
        self._trainer_ev = trainer_ev
        self.screenshots: list[str] = []

    def object_events(self):
        return [self._trainer_ev] if self._trainer_ev is not None else []

    def tile_walkable(self, x: int, y: int) -> bool:
        return (x, y) in self._walkable

    def screenshot(self, name: str):
        self.screenshots.append(name)
        return None


def _trainer_event(x: int, y: int, trainer_range: int, facing: str = "RIGHT"):
    from rpg2gba.playtest.emulator import ObjectEventState
    return ObjectEventState(
        local_id=1, active=True, x=x, y=y, facing=facing,
        graphics_id=0, movement_type=0, trainer_range=trainer_range,
    )


# -- _sight_lane_tiles: lane scan, farthest selection, range bound ----------

@needs_mgba
def test_lane_scan_stops_at_the_first_wall() -> None:
    from rpg2gba.playtest.chapters.route1 import _sight_lane_tiles

    # Trainer at (0,0) facing RIGHT, sight range 10; walkable up to (3,0),
    # (4,0) is a wall. The scan must stop there, not continue to the range.
    emu = _FakeSightLaneEmu(
        walkable={(1, 0), (2, 0), (3, 0)},
        trainer_ev=_trainer_event(0, 0, trainer_range=10),
    )
    tiles = _sight_lane_tiles(emu, "TEST", (0, 0), "RIGHT")
    assert tiles == [(1, 0), (2, 0), (3, 0)]


@needs_mgba
def test_farthest_walkable_tile_is_last_in_the_list() -> None:
    """Both callers (`_approach_sight_trainer`/`_assert_no_second_battle`)
    use `tiles[-1]` as the approach target -- confirm the list is ordered
    closest-to-farthest so that's actually the farthest one."""
    from rpg2gba.playtest.chapters.route1 import _sight_lane_tiles

    emu = _FakeSightLaneEmu(
        walkable={(0, 1), (0, 2), (0, 3), (0, 4)},
        trainer_ev=_trainer_event(0, 0, trainer_range=10, facing="DOWN"),
    )
    tiles = _sight_lane_tiles(emu, "TEST", (0, 0), "DOWN")
    assert tiles[-1] == (0, 4)
    assert tiles == [(0, 1), (0, 2), (0, 3), (0, 4)]


@needs_mgba
def test_one_tile_deep_lane_the_lynette_shape() -> None:
    """The real regression's sharpest case: a lane only one tile deep
    before the wall (Lynette's cone on the real ROM). Must return exactly
    that one tile, not fail and not fabricate a deeper approach."""
    from rpg2gba.playtest.chapters.route1 import _sight_lane_tiles

    emu = _FakeSightLaneEmu(
        walkable={(1, 0)},
        trainer_ev=_trainer_event(0, 0, trainer_range=10),
    )
    tiles = _sight_lane_tiles(emu, "TEST", (0, 0), "RIGHT")
    assert tiles == [(1, 0)]


@needs_mgba
def test_scan_never_exceeds_the_trainers_own_live_sight_range() -> None:
    """Even if every tile out to (10,0) is walkable, the scan must stop at
    `trainer_range` -- the engine's own `GetTrainerApproachDistance` would
    never look further either (trainer_see.c's range-bounded per-direction
    functions)."""
    from rpg2gba.playtest.chapters.route1 import _sight_lane_tiles

    emu = _FakeSightLaneEmu(
        walkable={(x, 0) for x in range(1, 11)},
        trainer_ev=_trainer_event(0, 0, trainer_range=3),
    )
    tiles = _sight_lane_tiles(emu, "TEST", (0, 0), "RIGHT")
    assert tiles == [(1, 0), (2, 0), (3, 0)]


@needs_mgba
def test_fails_loud_when_the_lane_is_entirely_blocked() -> None:
    """A trainer facing straight into a wall (the very first tile of the
    lane is unwalkable) can never trigger by sight -- a genuine conversion
    finding, not something to silently skip."""
    from rpg2gba.playtest.chapters.route1 import _sight_lane_tiles
    from rpg2gba.playtest.errors import ScenarioError

    emu = _FakeSightLaneEmu(
        walkable=set(),  # nothing walkable at all
        trainer_ev=_trainer_event(0, 0, trainer_range=10),
    )
    with pytest.raises(ScenarioError, match="faces straight into a wall"):
        _sight_lane_tiles(emu, "TEST", (0, 0), "RIGHT")


@needs_mgba
def test_unspawned_trainer_falls_back_to_the_scan_cap_not_a_hard_error() -> None:
    """2026-08-11 route1 B7 regression: no active object event at the
    trainer's recorded spawn tile used to fail loud outright -- but
    `TrySpawnObjectEvents` (engine/src/event_object_movement.c:2909-2951)
    only populates `gObjectEvents` for templates near the PLAYER's current
    position, so a trainer whose beat runs right after an earlier beat left
    the player elsewhere on the route (B7's own case: Flood reached
    straight from B4's grass cells, dx~9-10, outside the spawn window) is
    simply not spawned yet -- not "misplaced," not a reason to fail. The
    scan must fall back to `_SIGHT_SCAN_CAP` (pure terrain, no live
    trainer_range needed) instead of raising."""
    from rpg2gba.playtest.chapters.route1 import _SIGHT_SCAN_CAP, _sight_lane_tiles

    emu = _FakeSightLaneEmu(
        walkable={(x, 0) for x in range(1, _SIGHT_SCAN_CAP + 5)},
        trainer_ev=None,
    )
    tiles = _sight_lane_tiles(emu, "TEST", (0, 0), "RIGHT")
    # Bounded by the scan cap, not the (nonexistent) live trainer_range, and
    # not scanning indefinitely just because every tile happens walkable.
    assert tiles == [(x, 0) for x in range(1, _SIGHT_SCAN_CAP + 1)]


@needs_mgba
def test_unspawned_trainer_scan_still_fails_loud_on_a_solid_wall() -> None:
    """The unspawned fallback still stops at the first unwalkable tile and
    still fails loud if there's nowhere to stand at all -- falling back to
    a wider cap doesn't relax the "faces a wall" diagnosis."""
    from rpg2gba.playtest.chapters.route1 import _sight_lane_tiles
    from rpg2gba.playtest.errors import ScenarioError

    emu = _FakeSightLaneEmu(walkable=set(), trainer_ev=None)
    with pytest.raises(ScenarioError, match="faces straight into a wall"):
        _sight_lane_tiles(emu, "TEST", (0, 0), "RIGHT")


@needs_mgba
def test_spawned_trainer_still_uses_its_own_live_range_not_the_cap() -> None:
    """Once the trainer HAS spawned (e.g. re-approaching a defeated one),
    the precise live `trainer_range` still wins over the wider unspawned
    fallback cap -- the fallback is only for when there's nothing live to
    read yet."""
    from rpg2gba.playtest.chapters.route1 import _SIGHT_SCAN_CAP, _sight_lane_tiles

    emu = _FakeSightLaneEmu(
        walkable={(x, 0) for x in range(1, _SIGHT_SCAN_CAP + 5)},
        trainer_ev=_trainer_event(0, 0, trainer_range=2),
    )
    tiles = _sight_lane_tiles(emu, "TEST", (0, 0), "RIGHT")
    assert tiles == [(1, 0), (2, 0)]


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
