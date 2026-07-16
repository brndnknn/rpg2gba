"""Unit tests for route_sim.py — RMXP move-route execution simulator (the
blocked-move statue idiom: turn-first-then-check, non-skippable permanent
stall, direction_fix / through interactions, cycle-safe termination)."""
from __future__ import annotations

import pytest

from rpg2gba.tileset_converter.npc_gfx import MapPassability
from rpg2gba.tileset_converter.route_sim import RouteSim, simulate_route


def _page(direction: int = 2, direction_fix: bool = False, through: bool = False,
          route: dict | None = None) -> dict:
    return {
        "graphic": {"character_name": "X", "direction": direction},
        "direction_fix": direction_fix,
        "through": through,
        "move_route": route or _route([]),
    }


def _route(codes: list[int], repeat: bool = True, skippable: bool = False) -> dict:
    """A `move_route` dict for `codes` in order, with the RMXP-mandated
    trailing code-0 sentinel entry appended (mirrors `test_npc_gfx._route`)."""
    return {
        "repeat": repeat,
        "skippable": skippable,
        "list": [{"code": c, "parameters": []} for c in codes] + [{"code": 0, "parameters": []}],
    }


def _passability(
    layer0: list[int], layer1: list[int], passages: list[int],
    priorities: list[int] | None = None, width: int = 3,
) -> MapPassability:
    """Mirrors `test_npc_gfx._passability` — a tiny fake map_json/tileset pair
    fed through `MapPassability.from_map`."""
    height = len(layer0) // width
    map_json = {
        "tiles": {
            "xsize": width, "ysize": height, "zsize": 3,
            "data": layer0 + layer1 + [0] * len(layer0),
        }
    }
    tileset = {"passages": passages, "priorities": priorities or [0] * len(passages)}
    return MapPassability.from_map(map_json, tileset)


# --- blocked-first-move stall -------------------------------------------------

def test_blocked_first_move_stalls_facing_that_direction() -> None:
    """3-wide strip, spawn at x=1; tile 2 (west neighbor) is fully sealed
    (passage 0x0F). First command move_left walks straight into it -> turns
    LEFT, then finds the destination blocked -> stalls on the spot, having
    never moved. Real EV073/Map032 shape (move_left into a sealed hedge)."""
    mp = _passability(layer0=[2, 1, 1], layer1=[0, 0, 0], passages=[0, 0, 15])
    page = _page(direction=2, route=_route([2, 4, 4, 1, 1, 3]))  # EV073's own route
    result = simulate_route(page, x=1, y=0, passability=mp)
    assert result == RouteSim(stalled=True, moved=False, stall_facing="LEFT",
                               stall_pos=(1, 0), steps=0)


def test_direction_fix_suppresses_turn_on_block() -> None:
    """Same blocked-first-move shape, but `direction_fix=True` means the
    event never turns on the failed move — it stalls facing whatever
    `graphic.direction` already was (here DOWN), not LEFT."""
    mp = _passability(layer0=[2, 1, 1], layer1=[0, 0, 0], passages=[0, 0, 15])
    page = _page(direction=2, direction_fix=True, route=_route([2, 4, 4, 1, 1, 3]))
    result = simulate_route(page, x=1, y=0, passability=mp)
    assert result.stalled is True
    assert result.moved is False
    assert result.stall_facing == "DOWN"


def test_skippable_route_does_not_stall() -> None:
    """Same blocked move, but `skippable=True`: the blocked command is
    skipped (index advances) instead of stalling; a non-repeating route then
    runs off its only command and ends cleanly."""
    mp = _passability(layer0=[2, 1, 1], layer1=[0, 0, 0], passages=[0, 0, 15])
    page = _page(route=_route([2], repeat=False, skippable=True))
    result = simulate_route(page, x=1, y=0, passability=mp)
    assert result.stalled is False


def test_through_bypasses_collision() -> None:
    """Through-mode (codes 37 on / 38 off) wrapping a step into a sealed
    cell skips the collision test entirely -> no stall, and the character
    does end up displaced."""
    mp = _passability(layer0=[2, 1, 1], layer1=[0, 0, 0], passages=[0, 0, 15])
    page = _page(route=_route([37, 2, 38], repeat=False))
    result = simulate_route(page, x=1, y=0, passability=mp)
    assert result.stalled is False
    assert result.moved is True


def test_clean_loop_terminates_via_cycle_detection() -> None:
    """A repeating, fully-unobstructed square loop (right, down, left, up)
    around a 3x3 open map terminates via the visited-state cycle detector
    and reports no stall. Failure to terminate here is the bug this
    simulator exists to avoid (a naive infinite-retry replay)."""
    mp = _passability(
        layer0=[1, 1, 1, 1, 1, 1, 1, 1, 1],
        layer1=[0, 0, 0, 0, 0, 0, 0, 0, 0],
        passages=[0, 0],
        width=3,
    )
    page = _page(route=_route([3, 1, 2, 4], repeat=True))  # right, down, left, up
    result = simulate_route(page, x=1, y=1, passability=mp)
    assert result.stalled is False


def test_stall_after_moving_reports_moved_true() -> None:
    """First move (right, onto a clear tile) succeeds; second move (right
    again, into a sealed tile) stalls. `moved` must be True — the sim did
    displace before hitting the permanent block."""
    mp = _passability(layer0=[1, 1, 2], layer1=[0, 0, 0], passages=[0, 0, 15])
    page = _page(direction=6, route=_route([3, 3]))
    result = simulate_route(page, x=0, y=0, passability=mp)
    assert result.stalled is True
    assert result.moved is True
    assert result.stall_facing == "RIGHT"
    assert result.stall_pos == (1, 0)


# --- fail-loud plumbing --------------------------------------------------------

def test_unmodelable_code_returns_no_verdict() -> None:
    """A diagonal (code 5) is outside what this simulator can characterize
    -> immediate no-verdict, safe "keep the route" answer, not a guess."""
    mp = _passability(layer0=[1, 1, 1], layer1=[0, 0, 0], passages=[0, 0])
    page = _page(route=_route([5, 5, 5], repeat=True))
    result = simulate_route(page, x=1, y=0, passability=mp)
    assert result.stalled is False
    assert result.moved is False


def test_malformed_route_running_off_the_list_fails_loud() -> None:
    """A route list with no code-0 terminator at all is malformed input --
    fail loud (CLAUDE.md §4.5) rather than silently stopping. Use a bare
    wait (code 15, no motion) so the failure is unambiguously "ran off the
    end of the list", not a collision stall."""
    mp = _passability(layer0=[1, 1, 1], layer1=[0, 0, 0], passages=[0, 0])
    page = _page(route={"repeat": False, "skippable": False,
                         "list": [{"code": 15, "parameters": []}]})
    with pytest.raises(ValueError, match="ran off the end"):
        simulate_route(page, x=1, y=0, passability=mp)
