"""Looping custom-route walkers are intercepted on their path, not chased
(ROM run 36: Moki Town's Chyinmunk laps a rectangle at the fastest
frequency and `talk_to_moving_npc`'s chase lost every race)."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from rpg2gba.playtest import assertions
from rpg2gba.playtest.cells import RouteStep, custom_route_loop, emitted_movement_type
from rpg2gba.playtest.errors import ScenarioError


def test_chyinmunk_route_is_a_closed_rectangle_with_a_through_gap():
    steps = custom_route_loop("MAP_MOKI_TOWN", 8)
    assert steps is not None and len(steps) == 24
    assert steps[0] == RouteStep((35, 44), (35, 45), "DOWN", False)
    assert steps[-1].target == (35, 44)
    assert [s.origin for s in steps if s.through] == [(39, 43), (38, 43)]


def test_a_wandering_npc_has_no_route():
    assert custom_route_loop("MAP_MOKI_TOWN", 10) is None


def test_a_route_the_converter_froze_has_no_route():
    # ROM run 40: ev073's RMXP route stalls on its first step, so the
    # converter emits it static (FACE_LEFT); the compiled object decides.
    assert emitted_movement_type("MAP_MOKI_TOWN", 73) == "MOVEMENT_TYPE_FACE_LEFT"
    assert custom_route_loop("MAP_MOKI_TOWN", 73) is None


def test_a_back_and_forth_walker_keeps_its_route():
    steps = custom_route_loop("MAP_MOKI_TOWN", 27)
    assert steps is not None
    assert [s.target for s in steps] == [
        (46, 34), (47, 34), (48, 34), (47, 34), (46, 34), (45, 34)]


# --- the intercept, against a fake walker ---------------------------------

SQUARE = (
    RouteStep((0, 0), (1, 0), "RIGHT", False),
    RouteStep((1, 0), (1, 1), "DOWN", False),
    RouteStep((1, 1), (0, 1), "LEFT", True),
    RouteStep((0, 1), (0, 0), "UP", False),
)


@dataclass
class _Obj:
    x: int
    y: int


class _Emu:
    """A walker lapping SQUARE one step per `run` call; a non-through step
    into the player's cell holds it in place (the engine's non-skippable
    behaviour). Interact succeeds only when the player faces the walker."""

    def __init__(self, player, start_step=0):
        self.player = player
        self.step = start_step
        self.npc = SQUARE[start_step].origin
        self.facing = None
        self.talked = False

    def player_pos(self):
        return self.player

    def object_event(self, local_id):
        return _Obj(*self.npc)

    def run(self, frames):
        s = SQUARE[self.step]
        if s.target == self.player and not s.through:
            return
        self.npc = s.target
        self.step = (self.step + 1) % len(SQUARE)

    def face(self, direction):
        self.facing = direction

    def interact(self, require_script=False):
        dx, dy = {"UP": (0, -1), "DOWN": (0, 1), "LEFT": (-1, 0), "RIGHT": (1, 0)}[self.facing]
        self.talked = (self.player[0] + dx, self.player[1] + dy) == self.npc
        return self.talked

    def screenshot(self, name):
        return f"{name}.png"


def test_intercept_waits_on_the_path_and_talks_when_the_walker_is_held():
    emu = _Emu(player=(5, 5), start_step=1)
    walked = []

    def walk(x, y):
        walked.append((x, y))
        emu.player = (x, y)

    assertions.talk_to_moving_npc(emu, "B", 1, walk=walk, route=SQUARE)
    assert emu.talked
    # (1,1) is the nearest non-through target; the DOWN step from (1,0)
    # into it is where the walker is held.
    assert walked == [(1, 1)]
    assert emu.npc == (1, 0) and emu.facing == "UP"


def test_intercept_skips_a_cell_only_a_through_step_enters():
    # (0,1) is entered only by the through LEFT step -- the walker would walk
    # through the player -- so it is never a candidate.
    emu = _Emu(player=(-3, 1))
    walked = []

    def walk(x, y):
        walked.append((x, y))
        emu.player = (x, y)

    assertions.talk_to_moving_npc(emu, "B", 1, walk=walk, route=SQUARE)
    assert (0, 1) not in walked and emu.talked


def test_intercept_walks_to_the_path_when_the_walker_is_off_camera():
    # ROM run 37: from a seeded start the walker isn't loaded yet.
    emu = _Emu(player=(5, 5), start_step=1)
    loaded = {"yes": False}
    real = emu.object_event

    def object_event(local_id):
        if not loaded["yes"]:
            raise ScenarioError("no active object event with local id 1")
        return real(local_id)

    def walk(x, y):
        emu.player = (x, y)
        loaded["yes"] = True

    emu.object_event = object_event
    assertions.talk_to_moving_npc(emu, "B", 1, walk=walk, route=SQUARE)
    assert emu.talked


def test_intercept_fails_loud_when_no_path_cell_is_reachable():
    emu = _Emu(player=(5, 5))

    def walk(x, y):
        raise ScenarioError("blocked")

    with pytest.raises(ScenarioError, match="could be reached"):
        assertions.talk_to_moving_npc(emu, "B", 1, walk=walk, route=SQUARE)
