"""`smash_beat` clears obstacles in a live, reachable order (CH08 ROM runs 2-3)."""
import pytest

from rpg2gba.playtest.archetypes import generic
from rpg2gba.playtest.errors import ScenarioError

# event id -> {side: approach cell}
_APPROACHES = {
    29: {"east": (14, 21), "north": (13, 20)},
    36: {"east": (15, 16), "south": (14, 17)},
    38: {"east": (16, 17), "north": (15, 16)},
}


class _FakeEmu:
    def __init__(self, pos, reachable, lane_routes=None):
        self._pos = pos
        self._reachable = reachable  # goal cell -> route length, absent = unroutable
        # goal cell -> route length when the sight lanes are avoided (absent = unroutable)
        self._lane_routes = lane_routes if lane_routes is not None else reachable

    def player_pos(self):
        return self._pos

    def _plan_route(self, start, goal, extra_avoid=frozenset()):
        table = self._lane_routes if extra_avoid else self._reachable
        n = table.get(goal)
        return None if n is None else [start] * n

    def screenshot(self, name):
        return f"{name}.png"


@pytest.fixture(autouse=True)
def _fake_approach(monkeypatch):
    def approach_to(map_constant, event_id, *, prefer=None):
        cells = _APPROACHES[event_id]
        if prefer not in cells:
            raise ValueError("side not walkable")
        return cells[prefer]

    monkeypatch.setattr(generic, "approach_to", approach_to)


def _pick(emu, rows, prefer="east", sight=frozenset()):
    return generic._next_reachable_obstacle(emu, "b", "MAP_ROUTE_01", rows, prefer, sight)


def test_skips_an_unreachable_first_row_for_a_reachable_one():
    emu = _FakeEmu((15, 15), {(16, 17): 3, (15, 16): 1})
    rows = ["map033/ev029/p0", "map033/ev036/p0", "map033/ev038/p0"]
    # ev029 is walled in; ev036's east cell (15,16) is reachable in 1 and on the reviewed side
    assert _pick(emu, rows)[:2] == ("map033/ev036/p0", (15, 16))


def test_reviewed_side_beats_a_shorter_other_side():
    emu = _FakeEmu((0, 0), {(14, 21): 9, (13, 20): 2})
    assert _pick(emu, ["map033/ev029/p0"])[1] == (14, 21)


def test_falls_back_to_another_side_when_the_reviewed_one_is_unroutable():
    emu = _FakeEmu((0, 0), {(13, 20): 2})
    assert _pick(emu, ["map033/ev029/p0"])[1] == (13, 20)


def test_standing_on_the_approach_counts_as_reachable():
    emu = _FakeEmu((14, 21), {})
    assert _pick(emu, ["map033/ev029/p0"])[1] == (14, 21)


def test_no_reachable_obstacle_fails_loud():
    emu = _FakeEmu((0, 0), {})
    with pytest.raises(ScenarioError, match="no remaining obstacle has a plannable approach"):
        _pick(emu, ["map033/ev029/p0", "map033/ev036/p0"])


def test_an_approach_inside_a_sight_lane_loses_to_a_lane_free_side():
    # ev029's reviewed east side (14,21) sits in a trainer's lane; north is clear
    emu = _FakeEmu((0, 0), {(14, 21): 2, (13, 20): 5})
    row, cell, avoid = _pick(emu, ["map033/ev029/p0"], sight=frozenset({(14, 21)}))
    assert (cell, avoid) == ((13, 20), frozenset({(14, 21)}))


def test_a_route_only_through_a_lane_loses_to_a_lane_free_obstacle():
    sight = frozenset({(9, 9)})
    emu = _FakeEmu((0, 0), {(14, 21): 2, (15, 16): 8}, lane_routes={(15, 16): 8})
    row, cell, avoid = _pick(emu, ["map033/ev029/p0", "map033/ev036/p0"], sight=sight)
    assert (row, avoid) == ("map033/ev036/p0", sight)


def test_lanes_are_dropped_only_when_nothing_lane_free_remains():
    emu = _FakeEmu((0, 0), {(14, 21): 2}, lane_routes={})
    row, cell, avoid = _pick(emu, ["map033/ev029/p0"], sight=frozenset({(9, 9)}))
    assert (cell, avoid) == ((14, 21), frozenset())
