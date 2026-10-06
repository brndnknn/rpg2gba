"""Real map-connection crossings (Kevlar Town 31 <-> Route 2 35, connections.json
row [31,"N",11,35,"S",0]): cells helpers, seam_beat/transit_beat connection
branch with a fake emulator, and beat_gen's crossing-cell selection."""
from __future__ import annotations

import pytest

from rpg2gba.beat_gen.seam import SeamCrossing, connection_crossings
from rpg2gba.playtest import assertions, cells
from rpg2gba.playtest.archetypes import generic
from rpg2gba.playtest.chapter import ChapterBuilder
from rpg2gba.playtest.errors import ScenarioError
from rpg2gba.routing.connections import MapConnection
from rpg2gba.traversal.direction import Direction

KEVLAR, ROUTE2 = "MAP_KEVLAR_TOWN", "MAP_ROUTE_02"


@pytest.fixture(autouse=True)
def _no_seam_warps(monkeypatch):
    monkeypatch.setattr(cells, "_SEAM_WARPS_CACHE", [])


class FakeEmu:
    """Crosses maps after `hold_needed` held frames of `press`."""

    def __init__(self, start: str, dest: str, *, press: str, hold_needed: int = 12) -> None:
        self.map = start
        self.dest = dest
        self.press = press
        self.hold_needed = hold_needed
        self.held = 0
        self.pos = (0, 0)
        self.log: list[tuple] = []
        self.arrive_at: tuple[int, int] = (0, 0)

    def resolve_constant(self, expr: str) -> int:
        return hash(expr.split("(")[1].rstrip(")")) % 1000 if expr.startswith("MAP_NUM") else 1

    def map_location(self) -> tuple[int, int]:
        return (1, hash(self.map) % 1000)

    def walk_to(self, x: int, y: int, **_kw) -> None:
        self.pos = (x, y)
        self.log.append(("walk", x, y))

    def run(self, frames: int, keys: list[str] | None = None) -> None:
        if keys and keys[0] == self.press and self.map != self.dest:
            self.held += frames
            if self.held >= self.hold_needed:
                self.map = self.dest
                self.pos = self.arrive_at
        self.log.append(("run", frames, tuple(keys or ())))

    def player_pos(self) -> tuple[int, int]:
        return self.pos

    def settle_field(self) -> None:
        pass

    def screenshot(self, name: str) -> str:
        return name


def test_real_connection_resolves_and_seam_pair_does_not(monkeypatch):
    conn = cells.real_connection(KEVLAR, ROUTE2)
    assert conn is not None and conn.direction is Direction.NORTH
    monkeypatch.setattr(cells, "_SEAM_WARPS_CACHE", [
        {"id": "s", "map_a": 31, "map_b": 35, "cells_a": [[31, 0]], "cells_b": [[20, 56]]}])
    assert cells.real_connection(KEVLAR, ROUTE2) is None


def test_arrival_cell_applies_offset_and_far_edge():
    # [31,N,11,35,S,0]: route2_x = kevlar_x - 11, arriving on Route 2's bottom row.
    arrival = cells.connection_arrival_cell(KEVLAR, to=ROUTE2, cell=(32, 0))
    _, route2 = cells._graph_for(ROUTE2, resolver="test")
    assert arrival == (21, route2.height - 1)
    back = cells.connection_arrival_cell(ROUTE2, to=KEVLAR, cell=arrival)
    assert back == (32, 0)


def test_arrival_cell_refuses_a_non_edge_cell():
    with pytest.raises(ValueError, match="not an edge cell"):
        cells.connection_arrival_cell(KEVLAR, to=ROUTE2, cell=(32, 1))


def test_exit_cells_are_walkable_both_sides():
    exits = cells.connection_exit_cells(KEVLAR, to=ROUTE2)
    assert exits
    _, kevlar = cells._graph_for(KEVLAR, resolver="test")
    for cell in exits:
        assert cell[1] == 0 and kevlar.is_walkable(cell)
        arrival = cells.connection_arrival_cell(KEVLAR, to=ROUTE2, cell=cell)
        assert cells._graph_for(ROUTE2, resolver="test")[1].is_walkable(arrival)


def test_cross_connection_holds_until_map_changes_then_stops():
    emu = FakeEmu(KEVLAR, ROUTE2, press="UP")
    assertions.cross_connection(emu, "b", (32, 0), "UP", ROUTE2)
    assert emu.log[0] == ("walk", 32, 0)
    held = sum(f for k, f, keys in emu.log if k == "run" and keys == ("UP",))
    assert 12 <= held < 24            # released as soon as the map flipped


def test_cross_connection_fails_loud_when_map_never_changes():
    emu = FakeEmu(KEVLAR, ROUTE2, press="DOWN")
    with pytest.raises(ScenarioError):
        assertions.cross_connection(emu, "b", (32, 0), "UP", ROUTE2, budget=16)


def test_seam_beat_connection_branch_crosses_and_returns():
    b = ChapterBuilder("TEST", doc="x")
    generic.seam_beat(b, chapter_id="CH04", beat_name="m031seamN035",
                      rows=("map031/seam/N/map035",), approach_prefer="UP@(32,0)")
    (beat,) = b.build().beats
    assert (beat.locations[0].x, beat.locations[0].y) == (32, 0)
    arrival = cells.connection_arrival_cell(KEVLAR, to=ROUTE2, cell=(32, 0))

    class Both(FakeEmu):
        def run(self, frames, keys=None):
            # forward press UP on Kevlar; return press DOWN on Route 2
            self.press = "UP" if self.map == KEVLAR else "DOWN"
            self.dest = ROUTE2 if self.map == KEVLAR else KEVLAR
            self.arrive_at = arrival if self.map == KEVLAR else (32, 0)
            self.held = self.held if keys else 0
            super().run(frames, keys)
            if self.map == self.dest:
                self.held = 0

    emu = Both(KEVLAR, ROUTE2, press="UP")
    beat.run(emu)
    assert emu.map == KEVLAR and emu.pos == (32, 0)
    assert ("walk", *arrival) in emu.log


def test_transit_beat_hop_over_a_connection_holds_the_edge_press():
    b = ChapterBuilder("TEST", doc="x")
    generic.transit_beat(b, chapter_id="CH04", beat_name="t",
                         hops=((KEVLAR, 32, 0, "UP", ROUTE2),))
    (beat,) = b.build().beats
    emu = FakeEmu(KEVLAR, ROUTE2, press="UP")
    beat.run(emu)
    assert emu.map == ROUTE2
    assert emu.log[0] == ("walk", 32, 0)    # stood ON the edge cell, not beside it


def _graphs():
    return (cells._graph_for(KEVLAR, resolver="t")[1], cells._graph_for(ROUTE2, resolver="t")[1])


def test_crossing_selection_is_walkable_both_sides_and_offset_consistent():
    kevlar, route2 = _graphs()
    conn = MapConnection(31, Direction.NORTH, 11, 35, 0)
    crossings = connection_crossings(conn, from_graph=kevlar, to_graph=route2)
    assert crossings
    for c in crossings:
        assert isinstance(c, SeamCrossing) and c.press == "UP"
        assert c.exit_cell[1] == 0 and c.entry_cell == (c.exit_cell[0] - 11, route2.height - 1)
        assert kevlar.is_walkable(c.exit_cell) and route2.is_walkable(c.entry_cell)
        assert route2.is_walkable((c.entry_cell[0], c.entry_cell[1] - 1))   # open landing
