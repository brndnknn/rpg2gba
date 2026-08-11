"""Tests for `route1.py`'s `_approach_moving_npc` -- the 2026-08-16 B16
regression: the brother NPC in the old rod house (Map081 EV002) patrols
under a custom move route (right,right,left,left, repeat --
`MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE`, `Route01OldRodHouse/events.inc`), so a
single hardcoded approach tile (its spawn position) goes stale the instant
it paces off it. Live probe (seeded from the B16 blob): by the time a walk
to the documented spawn-adjacent tile completes, the NPC has already moved
to (14,8) -- up and to the RIGHT of the player, exactly matching the
original failure screenshot -- so `interact()` presses A at empty space and
fails loud ("interaction did not start a script"). Source data (Map081.json
EV002, move_type 3, move_route right,right,left,left), the compiled engine
data (`object_event 2, ..., 12, 8, 3, MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE`),
and this live read all agree -- the ROM is correct, the harness's fixed
approach tile was the bug. `_approach_moving_npc` fixes this by re-reading
the NPC's LIVE position from `gObjectEvents` on every attempt instead of a
fixed tile, retrying if `interact()` itself reports the NPC stepped away in
the gap between the read and the button press.

Same style as `test_sight_lane.py`: a bare fake implementing only what
`_approach_moving_npc` reads/calls (`object_event`, `walk_to` via
`_walk_absorbing`, `face`, `interact`, `screenshot`), gated on `needs_mgba`
because `route1.py`'s `_walk_absorbing` lazily imports `WalkInterrupted`
from `emulator.py`, which needs the mgba python bindings at module scope.
"""
import importlib.util

import pytest

needs_mgba = pytest.mark.skipif(
    importlib.util.find_spec("mgba") is None,
    reason="needs the mgba python bindings to import emulator.py",
)


class _FakePatrolEmu:
    """`object_event(local_id)` returns the next position in a scripted
    sequence (one call per `_approach_moving_npc` attempt, mirroring how the
    real NPC has moved on by the time a later attempt re-reads it).
    `walk_to` always succeeds instantly (`_walk_absorbing`'s own retry/
    absorb logic is `test_walk_interruption.py`'s concern, not this file's).
    `interact()` fails for the first `interact_fail_times` calls, then
    succeeds -- simulating the NPC having stepped out from under a stale
    approach.
    """

    def __init__(self, positions: list[tuple[int, int]],
                interact_fail_times: int = 0) -> None:
        self._positions = iter(positions)
        self._interact_fail_times = interact_fail_times
        self.walk_targets: list[tuple[int, int]] = []
        self.face_calls: list[str] = []
        self.interact_calls = 0
        self.screenshots: list[str] = []

    def object_event(self, local_id: int):
        from rpg2gba.playtest.emulator import ObjectEventState
        x, y = next(self._positions)
        return ObjectEventState(
            local_id=local_id, active=True, x=x, y=y, facing="RIGHT",
            graphics_id=0, movement_type=83,
        )

    def walk_to(self, tx: int, ty: int, *args, **kwargs) -> None:
        self.walk_targets.append((tx, ty))

    def face(self, direction: str) -> None:
        self.face_calls.append(direction)

    def interact(self) -> None:
        from rpg2gba.playtest.errors import ScenarioError
        self.interact_calls += 1
        if self.interact_calls <= self._interact_fail_times:
            raise ScenarioError("interaction did not start a script")

    def screenshot(self, name: str):
        self.screenshots.append(name)
        return None


@needs_mgba
def test_approaches_the_tile_behind_the_npcs_live_position() -> None:
    """`facing="UP"` means the player stands south of the NPC and faces
    north toward it -- the approach tile is one step behind the NPC along
    that vector, i.e. `(npc.x, npc.y + 1)`, exactly like the real brother
    NPC's south-facing approach in `route1.py`."""
    from rpg2gba.playtest.chapters.route1 import _approach_moving_npc

    emu = _FakePatrolEmu(positions=[(12, 8)])
    _approach_moving_npc(emu, "TEST", local_id=2, facing="UP")

    assert emu.walk_targets == [(12, 9)]
    assert emu.face_calls == ["UP"]
    assert emu.interact_calls == 1


@needs_mgba
def test_retries_with_a_fresh_read_when_the_npc_steps_away() -> None:
    """The 2026-08-16 regression's exact shape: the NPC has moved from
    (12,8) to (14,8) between the first approach and the interact press.
    `_approach_moving_npc` must re-read its position and re-approach, not
    fail on the first `interact()` error."""
    from rpg2gba.playtest.chapters.route1 import _approach_moving_npc

    emu = _FakePatrolEmu(positions=[(12, 8), (14, 8)], interact_fail_times=1)
    _approach_moving_npc(emu, "TEST", local_id=2, facing="UP")

    assert emu.walk_targets == [(12, 9), (14, 9)]
    assert emu.face_calls == ["UP", "UP"]
    assert emu.interact_calls == 2


@needs_mgba
def test_fails_loud_after_max_attempts_exhausted() -> None:
    """If the NPC keeps stepping out from under every attempt (or the
    interact is genuinely broken), this must fail loud with a screenshot
    rather than retry forever or silently pass."""
    from rpg2gba.playtest.chapters.route1 import (
        _MAX_PATROL_APPROACH_ATTEMPTS, _approach_moving_npc,
    )
    from rpg2gba.playtest.errors import ScenarioError

    positions = [(12, 8)] * _MAX_PATROL_APPROACH_ATTEMPTS
    emu = _FakePatrolEmu(
        positions=positions, interact_fail_times=_MAX_PATROL_APPROACH_ATTEMPTS)

    with pytest.raises(ScenarioError, match="could not interact with the patrolling NPC"):
        _approach_moving_npc(emu, "TEST", local_id=2, facing="UP")

    assert emu.interact_calls == _MAX_PATROL_APPROACH_ATTEMPTS
    assert emu.screenshots  # a screenshot was taken on the failure path


@needs_mgba
def test_approach_tile_follows_facing_direction() -> None:
    """Same NPC position, different `facing` -- the approach tile must move
    with it (one step opposite the direction the player faces), not stay
    pinned to a UP-only assumption."""
    from rpg2gba.playtest.chapters.route1 import _approach_moving_npc

    emu = _FakePatrolEmu(positions=[(5, 5)])
    _approach_moving_npc(emu, "TEST", local_id=2, facing="LEFT")

    # facing LEFT means the NPC is to the player's left (west); the player
    # stands one tile east of it.
    assert emu.walk_targets == [(6, 5)]
    assert emu.face_calls == ["LEFT"]
