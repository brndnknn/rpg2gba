"""Tests for `_plan_route` consuming the offline `MapGraph`
(`rpg2gba.traversal`) as the source of static walkability, instead of
re-deriving it from the live `gBackupMapLayout` snapshot
(PLAYTEST_AUTHORING_IMPROVEMENT_V2.md Q13, slice 1, decision 2).

Same fake-memory-store style as `tests/test_plan_route_objects.py` (do not
modify that file; this is a new one) and `tests/test_plan_route_grass.py`:
no mgba dependency for the pure logic, gated on `needs_mgba` because
importing `emulator.py` itself requires the mgba python bindings (it
imports them at module scope).

`_FakeGraphRouteEmu` extends the established `_FakeRouteEmu` shape
(map grid + object events + warps) with the two new injection points
`Emulator.__init__` wires for a real run: `_map_graph_source` (a callable
`map_id -> MapGraph`) and `_map_id_bridge` (an object with
`resolve(group, num) -> map_id`). Both are simple test doubles here --
never touching disk, never invoking gcc -- confirming injectability is real
and does not require decoded map files or a MapConstantRegistry state file
on disk to exercise `_plan_route`'s graph-consuming logic.
"""
import importlib.util
import struct

import pytest

from rpg2gba.traversal.direction import Direction
from rpg2gba.traversal.graph import MapGraph

needs_mgba = pytest.mark.skipif(
    importlib.util.find_spec("mgba") is None,
    reason="needs the mgba python bindings to import emulator.py",
)

_MAP_OFFSET = 1

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


class _FakeGraphRouteEmu:
    """`_FakeRouteEmu`-shaped fake (map grid, no warps, empty object table
    by default) that ALSO defines `_current_map_graph`'s dependencies
    (`_map_graph_source`, `_map_id_bridge`) so `_plan_route`'s graph-
    consuming path is exercised rather than degraded.

    Pass `with_graph=False` to get the pre-existing degrade behaviour by
    defining neither `_current_map_graph` nor its dependencies at all -- covers the "fakes that predate this primitive"
    path with a fake that is otherwise identical, so the two behaviours are
    compared apples-to-apples in the same test file.
    """

    def __init__(self, map_w: int, map_h: int,
                 walls: set[tuple[int, int]] = frozenset(),
                 graph: MapGraph | None = None,
                 with_graph: bool = True,
                 map_id_error: Exception | None = None) -> None:
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

        self.write_u32(_GMAPHEADER, _LAYOUT_ADDR)
        self.write_u32(_LAYOUT_ADDR, map_w)
        self.write_u32(_LAYOUT_ADDR + 4, map_h)
        self.write_u32(_GBACKUP, self._backup_w)
        self.write_u32(_GBACKUP + 4, self._backup_h)
        self.write_u32(_GBACKUP + 8, 0x9000)

        if with_graph:
            if map_id_error is not None:
                class _RaisingBridge:
                    def resolve(self_, group, num):
                        raise map_id_error
                self._map_id_bridge = _RaisingBridge()
            else:
                self._map_id_bridge = _StubBridge(37)
            self._map_graph_source = _StubGraphSource({37: graph} if graph else {})
            # Bound per-instance, not on the class: with `with_graph=False`
            # this fake must genuinely NOT HAVE `_current_map_graph`, the way
            # the fakes that predate the primitive (`_FakeRouteEmu`) don't.
            # Defining it on the class would make the no-graph case degrade
            # via an AttributeError raised INSIDE the call instead of from
            # the attribute lookup -- which is exactly the swallow
            # `test_attribute_error_from_inside_graph_resolution_is_not_
            # swallowed` exists to forbid.
            def _current_map_graph() -> MapGraph:
                from rpg2gba.playtest.emulator import Emulator
                return Emulator._current_map_graph(self)

            self._current_map_graph = _current_map_graph

    # -- raw access -----------------------------------------------------

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
        return (1, 1)

    def read_bytes(self, addr: int, size: int) -> bytes:
        w, h = self._backup_w, self._backup_h
        off = _MAP_OFFSET
        blocks = [0] * (w * h)
        for wx, wy in self._walls:
            blocks[(wx + off) + w * (wy + off)] = _COLLISION_BLOCKED
        return struct.pack(f"<{w * h}H", *blocks)

    # -- object events (none by default; unused by these tests) ---------

    def _player_object_slot(self):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._player_object_slot(self)

    def _occupied_object_tiles(self, goal):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._occupied_object_tiles(self, goal)

    # -- code under test, borrowed unbound from the real class -----------

    def _grid_dims_for_current_map(self):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._grid_dims_for_current_map(self)

    def _map_grid(self):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._map_grid(self)

    def _warp_tiles(self):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._warp_tiles(self)

    def _plan_route(self, start, goal):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._plan_route(self, start, goal)


class _StubBridge:
    """`_map_id_bridge`-shaped double: constant `(group, num) -> map_id`,
    no gcc probe, no MapConstantRegistry state file."""

    def __init__(self, map_id: int) -> None:
        self._map_id = map_id

    def resolve(self, group: int, num: int) -> int:
        return self._map_id


class _StubGraphSource:
    """`_map_graph_source`-shaped double: a plain dict lookup, no
    `build_map_graph` disk read."""

    def __init__(self, graphs: dict[int, MapGraph]) -> None:
        self._graphs = graphs

    def __call__(self, map_id: int) -> MapGraph:
        return self._graphs[map_id]


def _open_graph(width: int, height: int, **overrides) -> MapGraph:
    """A `MapGraph` with every cell walkable (blocked=False everywhere)
    unless overridden -- the test's baseline before poking in graph-only
    blocks/stairs/ledges."""
    blocked = {(x, y): False for y in range(height) for x in range(width)}
    blocked.update(overrides.pop("blocked", {}))
    return MapGraph(
        map_id=37, width=width, height=height, tileset_id=1,
        blocked=blocked, **overrides,
    )


# -- graph is actually consulted for static walkability ----------------------

@needs_mgba
def test_graph_blocked_cell_forces_a_detour_the_live_grid_would_not() -> None:
    """The live grid has NO walls at all -- a straight line through (1,1)
    is open. The offline graph marks (1,1) blocked. The chosen route must
    detour around it, proving static walkability came from the graph, not
    the live snapshot (which would have gone straight through)."""
    graph = _open_graph(3, 3, blocked={(1, 1): True})
    emu = _FakeGraphRouteEmu(map_w=3, map_h=3, walls=set(), graph=graph)

    route = emu._plan_route((0, 1), (2, 1))

    assert route is not None
    assert (1, 1) not in route
    assert route[0] == (0, 1) and route[-1] == (2, 1)


@needs_mgba
def test_without_a_graph_the_live_grid_alone_decides_walkability() -> None:
    """Sanity check / control for the test above: the SAME live grid (no
    walls), but no graph injected (`with_graph=False`, mirroring
    `_FakeRouteEmu`'s pre-existing shape) -- degrades to the old
    live-grid-only planner, which has no reason to avoid (1,1)."""
    emu = _FakeGraphRouteEmu(map_w=3, map_h=3, walls=set(), with_graph=False)

    route = emu._plan_route((0, 1), (2, 1))

    assert route == [(0, 1), (1, 1), (2, 1)]


# -- stair-crossing routes are now plannable ----------------------------------

@needs_mgba
def test_stair_diagonal_makes_a_route_plannable_the_old_planner_could_not() -> None:
    """A 3x3 grid where every cell is blocked in the LIVE grid except the
    start and the goal -- the old 4-neighbour, live-grid-only planner has no
    route at all. The offline graph puts a sideways staircase at (1,1):
    from (0,1), pressing EAST is redirected by the engine's own diagonal
    rule (RIGHT side, NW/SE axis: EAST -> (x+1, y+1)) straight to (2,2),
    the goal. A stair cell is also always graph-walkable regardless of its
    raw collision (`MapGraph.is_walkable` docstring), so the live grid
    blocking (1,1) does not matter to the graph-driven search.
    """
    all_but_start_and_goal = {
        (x, y) for y in range(3) for x in range(3)
    } - {(0, 1), (2, 2)}
    emu_no_graph = _FakeGraphRouteEmu(
        map_w=3, map_h=3, walls=all_but_start_and_goal, with_graph=False)
    assert emu_no_graph._plan_route((0, 1), (2, 2)) is None  # old planner: unroutable

    from rpg2gba.tileset_converter.stairs import StairSide
    graph = _open_graph(3, 3, stair_sides={(1, 1): StairSide.RIGHT})
    emu = _FakeGraphRouteEmu(map_w=3, map_h=3, walls=all_but_start_and_goal, graph=graph)

    route = emu._plan_route((0, 1), (2, 2))

    assert route is not None
    assert route[0] == (0, 1) and route[-1] == (2, 2)


# -- loud error when the current map can't be resolved ------------------------

@needs_mgba
def test_unresolvable_map_id_raises_instead_of_falling_back(caplog) -> None:
    """`_map_id_bridge.resolve` raising (the real bridge's shape when a
    live map has no minted MapConstantRegistry entry) must propagate out of
    `_plan_route`, not be swallowed into a live-grid-only degrade -- that
    degrade is reserved for `AttributeError` (a fake that predates the
    primitive entirely), never for a real resolution failure."""
    from rpg2gba.playtest.errors import ScenarioError

    emu = _FakeGraphRouteEmu(
        map_w=3, map_h=3, walls=set(),
        map_id_error=ScenarioError("no minted map for this map_location"),
    )

    with pytest.raises(ScenarioError, match="no minted map"):
        emu._plan_route((0, 1), (2, 1))


# -- divergence is recorded, never acted on, never blocking -------------------

@needs_mgba
def test_divergence_is_logged_but_does_not_change_the_route_or_fail(caplog) -> None:
    """(1, 0) is BLOCKED in the live grid but WALKABLE per the offline
    graph -- an opposite-direction disagreement from the "graph is
    consulted" test above. It sits beside (1, 1), which the shortest route
    from (0, 1) to (2, 1) passes through, so the search touches it and the
    divergence check fires. The chosen route is unaffected (it never needed
    to enter (1, 0) at all) and no exception is raised -- a carried,
    non-blocking contradiction (Q13.1), not a gate.
    """
    import logging

    graph = _open_graph(3, 3)  # graph: (1,0) walkable (default)
    emu = _FakeGraphRouteEmu(map_w=3, map_h=3, walls={(1, 0)}, graph=graph)

    with caplog.at_level(logging.WARNING, logger="rpg2gba.playtest.emulator"):
        route = emu._plan_route((0, 1), (2, 1))

    assert route == [(0, 1), (1, 1), (2, 1)]
    divergence_lines = [r for r in caplog.records if "divergence" in r.message]
    assert divergence_lines, caplog.text
    msg = divergence_lines[0].message
    assert "(1, 0)" in msg
    assert "walkable=True" in msg  # graph's verdict
    assert "walkable=False" in msg  # live grid's verdict


@needs_mgba
def test_attribute_error_from_inside_graph_resolution_is_not_swallowed() -> None:
    """The degrade exists for fakes that never define `_current_map_graph`
    at all -- NOT for an `AttributeError` raised while a real one runs.

    `_plan_route` binds the method inside its `try` and calls it outside, so
    a bug deep in map-id resolution or graph building surfaces loud instead
    of silently reverting this planner to live-grid walkability. That revert
    is the two-implementations bug the offline graph exists to remove, and it
    would present as a wrong route rather than an error -- the silent-degrade
    shape CLAUDE.md §4.5/§11 forbid. Guards against re-widening the `except`
    to wrap the call.
    """
    graph = _open_graph(3, 3)
    emu = _FakeGraphRouteEmu(map_w=3, map_h=3, walls=set(), graph=graph)

    def _boom() -> MapGraph:
        raise AttributeError("simulated bug inside graph resolution")

    emu._current_map_graph = _boom  # type: ignore[method-assign]

    with pytest.raises(AttributeError, match="simulated bug inside graph resolution"):
        emu._plan_route((0, 1), (2, 1))
