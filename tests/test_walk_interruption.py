"""Tests for `Emulator.walk_to`'s interruption handling (`WalkInterrupted`,
`resolve_interruption`, `resolve_interruptions=True`).

Same style as the `walk_to` pathing tests in `test_playtest.py`: a bare fake
implementing only what the code under test reads
(`run`/`player_pos`/`field_locked`/`map_location`/`screenshot`), with
`Emulator`'s own methods borrowed unbound (`Emulator.walk_to(fake, ...)`) so
no mGBA bindings or ROM are needed. `Emulator` itself still requires the mgba
python bindings to *import* (see emulator.py's module docstring), so these
tests are gated on mgba being importable, same as `test_playtest.py`.
"""
import importlib.util

import pytest

needs_mgba = pytest.mark.skipif(
    importlib.util.find_spec("mgba") is None,
    reason="needs the mgba python bindings to import emulator.py",
)

_WALK_DIR_DELTA = {"LEFT": (-1, 0), "RIGHT": (1, 0), "UP": (0, -1), "DOWN": (0, 1)}


class _FakeInterruptEmu:
    """`_FakeWalkEmu`-shaped grid walker (see `test_playtest.py`), extended
    with a settable field-lock and battle flag so an ambush mid-walk can be
    simulated without mgba or a ROM.

    `lock_at`/`battle_at` are tiles that trip the lock/battle flags the
    instant the player steps onto them -- standing in for a sight trainer's
    trigger tile. `wild_battle_at` is the 2026-08-11 route1 B4 regression's
    own shape: it sets ONLY the battle flag, no lock at all -- a wild
    encounter has no accompanying script, so `field_locked()` never trips.
    `unlock_after_polls`, if set, counts down once per no-keys `run()` call
    made while locked (exactly the shape of `_walk_greedy`'s "wait 30
    frames, recheck" loop) and clears the lock when it hits zero --
    simulating a scene that runs for a while and then releases the player
    on its own, the same shape ch01.py's B5-hands-B6 a running autorun
    beats need `walk_to` to tolerate.

    `grid_settle_polls` models the post-interruption map-grid transition
    `_wait_for_overworld_return` waits on (2026-08-11 route1 B4 regression:
    a battle-end fade leaves `gBackupMapLayout` on the battle's own stub
    grid for a few frames after the field itself unlocks). `0` (default) is
    "already settled" -- `map_grid_loaded()` reads True from the start, so
    tests that don't care about this transition see no behaviour change.
    A positive int counts down once per `run(10)` call (the cadence
    `_wait_for_overworld_return` polls at, distinct from the 30-frame
    lock-wait/grace cadence) before `map_grid_loaded()` starts reading True.
    `None` means it never settles.
    """

    def __init__(self, start, blocked=frozenset(), lock_at=None,
                 battle_at=None, wild_battle_at=None, locked_at_start=False,
                 unlock_after_polls=None, grid_settle_polls: int | None = 0,
                 battle_type_flags: int = 0, battle_after_polls=None,
                 lock_on_settle_at=None):
        self._pos = start
        self._blocked = set(blocked)
        self._map = (1, 1)
        self.screenshots: list[str] = []
        self._locked = locked_at_start
        self._in_battle_flag = False
        self._lock_at = lock_at
        self._battle_at = battle_at
        self._wild_battle_at = wild_battle_at
        self._unlock_after_polls = unlock_after_polls
        self._grid_settle_remaining = grid_settle_polls
        # A tile that locks the field on the NO-KEYS settle run(16)
        # `_walk_greedy`'s arrival branch makes right after the coord
        # already reads as arrived -- NOT on the keyed step that lands on
        # it (that's `lock_at`/`wild_battle_at` above). Models the
        # 2026-08-11 route1 B15 regression: a wild encounter rolled by the
        # very last step declares itself a few frames into the settle, not
        # on the step itself -- `field_locked()` was still False at the top
        # of that iteration (that's how the arrival branch was even
        # reached), so nothing upstream saw an interruption at all.
        self._lock_on_settle_at = lock_on_settle_at
        self._settle_lock_armed = lock_on_settle_at is not None
        # Counts down once per no-keys run() call made while locked, same
        # cadence as `_unlock_after_polls` -- but flips `_in_battle_flag`
        # True WITHOUT clearing the lock, instead of unlocking. Models the
        # 2026-08-11 route1 B4 regression: a trainer's notice sequence was
        # already mid-flight (locked, not yet battling) when a resumed
        # `walk_to` began, and its own dialogue eventually turned into a
        # real battle nobody was pressing buttons for -- `_walk_greedy`'s
        # `start_locked` branch used to just keep waiting forever (bounded
        # only by `frame_budget`) because it never re-checked `_in_battle()`
        # once already inside that branch.
        self._battle_after_polls = battle_after_polls
        self.dialogue_advances = 0
        # `is_trainer_battle()` reads -- late-bound the same way the real
        # `Emulator` does (symbols dict + resolve_constant), just faked.
        self.symbols = {"gBattleTypeFlags": 0x1000}
        self._battle_type_flags = battle_type_flags
        # Counts no-keys run() calls made while locked -- exactly the
        # `_walk_greedy` "wait 30 frames, recheck" / grace-period polling
        # shape -- so a test can assert the grace was (or wasn't) spent.
        self.lock_poll_calls = 0
        # Counts `run(10)` calls specifically -- the cadence
        # `_wait_for_overworld_return` polls at, and (in this harness)
        # nothing else does -- so a test can assert the grid-settle wait
        # was (or wasn't) spent, distinctly from `lock_poll_calls`.
        self.grid_poll_calls = 0

    # -- what walk_to/_walk_greedy read --------------------------------

    def run(self, frames, keys=None, on_frame=None) -> None:
        if not keys:
            if (self._settle_lock_armed
                    and self._pos == self._lock_on_settle_at):
                self._locked = True
                self._settle_lock_armed = False
            if frames == 10:
                self.grid_poll_calls += 1
                if (isinstance(self._grid_settle_remaining, int)
                        and self._grid_settle_remaining > 0):
                    self._grid_settle_remaining -= 1
            if self._locked:
                self.lock_poll_calls += 1
                if self._unlock_after_polls is not None:
                    self._unlock_after_polls -= 1
                    if self._unlock_after_polls <= 0:
                        self._locked = False
                if self._battle_after_polls is not None:
                    self._battle_after_polls -= 1
                    if self._battle_after_polls <= 0:
                        self._in_battle_flag = True
                        self._battle_after_polls = None
            if on_frame is not None:
                for _ in range(frames):
                    on_frame()
            return
        ddx, ddy = _WALK_DIR_DELTA[keys[0]]
        nx, ny = self._pos[0] + ddx, self._pos[1] + ddy
        if (nx, ny) in self._blocked:
            return
        self._pos = (nx, ny)
        if self._pos == self._lock_at:
            self._locked = True
        if self._pos == self._battle_at:
            self._locked = True
            self._in_battle_flag = True
        if self._pos == self._wild_battle_at:
            self._in_battle_flag = True  # no lock -- see the class docstring

    def player_pos(self):
        return self._pos

    def field_locked(self) -> bool:
        return self._locked

    def map_location(self):
        return self._map

    def map_grid_loaded(self) -> bool:
        if self._grid_settle_remaining is None:
            return False
        return self._grid_settle_remaining <= 0

    def screenshot(self, name: str):
        self.screenshots.append(name)
        return None

    def _in_battle(self) -> bool:
        return self._in_battle_flag

    # -- is_trainer_battle() reads --------------------------------------

    def u32(self, addr: int) -> int:
        if addr == self.symbols["gBattleTypeFlags"]:
            return self._battle_type_flags
        raise AssertionError(f"unexpected u32 read at 0x{addr:x}")

    def resolve_constant(self, name: str) -> int:
        if name == "BATTLE_TYPE_TRAINER":
            return 0x08  # arbitrary bit -- only its identity matters here
        raise AssertionError(f"unexpected resolve_constant({name!r})")

    # -- dialogue-resolution stand-in ------------------------------------
    # resolve_interruption()'s non-battle branch calls self.advance_dialog();
    # a minimal fake is enough here -- release the lock, as if the scene had
    # just been mashed to its end.

    def advance_dialog(self, key="A", max_taps=1500, stop=None) -> int:
        self.dialogue_advances += 1
        self._locked = False
        return 1

    # -- borrow the real, under-test logic unbound (same pattern as
    # `_FakeWalkEmu` in test_playtest.py for `_walk_greedy`/`_require_same_map`)

    def _walk_step(self, direction, x, y):
        for frames in range(1, 41):
            self.run(1, [direction])
            if self.player_pos() != (x, y):
                return True, frames
        return False, 40

    def _route_waypoints(self, tx, ty):
        return [(tx, ty)]

    def wait_for_map_grid(self, frame_budget: int = 300) -> int:
        return 0

    def _walk_greedy(self, *args, **kwargs):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._walk_greedy(self, *args, **kwargs)

    def _require_same_map(self, *args, **kwargs):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._require_same_map(self, *args, **kwargs)

    def resolve_interruption(self, *args, **kwargs):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator.resolve_interruption(self, *args, **kwargs)

    def _wait_for_overworld_return(self, *args, **kwargs):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._wait_for_overworld_return(self, *args, **kwargs)

    # `ch02.py`'s `_walk_absorbing` calls these as ordinary BOUND methods
    # (`emu.walk_to(...)`, `emu.is_trainer_battle()`), not unbound against
    # `Emulator` the way this file's own tests do -- so the fake needs them
    # as real attributes, delegating to the real (under-test) logic.
    def walk_to(self, tx, ty, *args, **kwargs):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator.walk_to(self, tx, ty, *args, **kwargs)

    def is_trainer_battle(self):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator.is_trainer_battle(self)


class _AlwaysInterruptedEmu:
    """Minimal fake for the resolution-cap test: `resolve_interruption`
    never actually clears anything, so `walk_to`'s `resolve_interruptions=
    True` loop keeps retrying -- it must give up after
    `_MAX_INTERRUPTION_RESOLUTIONS` calls, not loop forever. Paired with a
    monkeypatched module-level `_walk_to_once` (see the test) that always
    raises `WalkInterrupted`, so this is isolated from the walking geometry
    entirely."""

    def __init__(self):
        self.resolve_calls = 0

    def resolve_interruption(self):
        self.resolve_calls += 1
        return "dialogue"


# -- WalkInterrupted: raised on an unlocked->locked transition mid-walk ------

@needs_mgba
def test_walk_interrupted_when_field_locks_mid_walk() -> None:
    from rpg2gba.playtest.emulator import Emulator, WalkInterrupted

    # Field starts unlocked; (2, 0) sits directly on the straight-line route
    # from (0, 0) to (4, 0) and trips the lock the instant it's stepped on --
    # the ambush shape from the B4/Tath failure this fix targets.
    emu = _FakeInterruptEmu(start=(0, 0), lock_at=(2, 0))
    with pytest.raises(WalkInterrupted) as excinfo:
        Emulator.walk_to(emu, 4, 0, frame_budget=500)
    exc = excinfo.value
    assert exc.target == (4, 0)
    assert exc.stopped_at == (2, 0)
    assert exc.battle is False


@needs_mgba
def test_walk_interrupted_reports_battle_in_progress() -> None:
    from rpg2gba.playtest.emulator import Emulator, WalkInterrupted

    emu = _FakeInterruptEmu(start=(0, 0), battle_at=(2, 0))
    with pytest.raises(WalkInterrupted) as excinfo:
        Emulator.walk_to(emu, 4, 0, frame_budget=500)
    assert excinfo.value.battle is True
    assert excinfo.value.stopped_at == (2, 0)
    # A battle never gets the grace period -- waiting is pointless.
    assert emu.lock_poll_calls == 0


@needs_mgba
def test_walk_interrupted_by_battle_with_no_field_lock_at_all() -> None:
    """The exact case every fake before this round missed, and the exact
    shape of the 2026-08-11 route1 B4 regression: a wild encounter sets NO
    script lock -- `field_locked()` stays False for the whole battle -- so
    detection must poll `in_battle` independently of the lock branch, not
    only inside it."""
    from rpg2gba.playtest.emulator import Emulator, WalkInterrupted

    emu = _FakeInterruptEmu(start=(0, 0), wild_battle_at=(2, 0))
    with pytest.raises(WalkInterrupted) as excinfo:
        Emulator.walk_to(emu, 4, 0, frame_budget=500)
    assert excinfo.value.battle is True
    assert excinfo.value.stopped_at == (2, 0)
    # Confirms the fake really did model "no lock, ever" -- if this were
    # False, the old lock-gated detection would have been enough and this
    # test wouldn't be exercising the new code path at all.
    assert emu.field_locked() is False


@needs_mgba
def test_walk_interrupted_by_lock_appearing_during_arrival_settle() -> None:
    """2026-08-11 route1 B15 regression: a wild encounter rolled by the very
    LAST step of the walk can declare itself (lock the field) during the
    16-frame settle `_walk_greedy`'s arrival branch runs after the coord
    already reads as arrived -- not on the step itself. `field_locked()`
    was still False at the top of that iteration (that's how the arrival
    branch got reached at all), so the old code returned success
    unconditionally and the caller's next action (`face()`/`interact()`)
    walked straight into an already-arriving battle it never saw. This
    must now raise `WalkInterrupted`, same as any other lock/battle this
    function detects, rather than silently reporting the walk as clean."""
    from rpg2gba.playtest.emulator import Emulator, WalkInterrupted

    emu = _FakeInterruptEmu(start=(0, 0), lock_on_settle_at=(4, 0))
    with pytest.raises(WalkInterrupted) as excinfo:
        Emulator.walk_to(emu, 4, 0, frame_budget=500)
    exc = excinfo.value
    assert exc.target == (4, 0)
    assert exc.stopped_at == (4, 0)
    assert exc.battle is False


# -- is_trainer_battle: telling a trainer battle from a wild encounter ------

@needs_mgba
def test_is_trainer_battle_raises_when_no_battle_is_running() -> None:
    from rpg2gba.playtest.emulator import Emulator
    from rpg2gba.playtest.errors import ScenarioError

    emu = _FakeInterruptEmu(start=(0, 0))
    with pytest.raises(ScenarioError, match="no battle is in progress"):
        Emulator.is_trainer_battle(emu)


@needs_mgba
def test_is_trainer_battle_true_when_the_trainer_bit_is_set() -> None:
    from rpg2gba.playtest.emulator import Emulator

    emu = _FakeInterruptEmu(start=(0, 0), battle_type_flags=0x08)
    emu._in_battle_flag = True
    assert Emulator.is_trainer_battle(emu) is True


@needs_mgba
def test_is_trainer_battle_false_for_a_wild_encounter() -> None:
    from rpg2gba.playtest.emulator import Emulator

    emu = _FakeInterruptEmu(start=(0, 0), battle_type_flags=0)
    emu._in_battle_flag = True
    assert Emulator.is_trainer_battle(emu) is False


# -- grace period: self-resolving scenes vs. genuinely input-blocked ones ---
#
# The ch01.py B4 regression: crossing the fence-row tile fires Theo's cameo,
# a scene that locks the field, plays out with no input, and releases on its
# own. That must keep working -- walk_to must wait it out, not raise, same as
# the pre-fix behaviour. What must still raise is a lock that *doesn't*
# clear on its own (a msgbox waiting on a button the walk isn't pressing, a
# sight trainer's approach-and-battle) -- but only after `_INTERRUPT_GRACE`,
# not instantly.

@needs_mgba
def test_walk_self_resolving_lock_waits_it_out_and_reaches_target() -> None:
    """A cameo-shaped lock (clears itself well within the grace) must NOT
    raise `WalkInterrupted` -- the walk waits, then continues to the
    target, exactly like a pre-fix `walk_to` did for ch01.py B4."""
    from rpg2gba.playtest.emulator import Emulator

    emu = _FakeInterruptEmu(start=(0, 0), lock_at=(2, 0),
                            unlock_after_polls=2)
    Emulator.walk_to(emu, 4, 0, frame_budget=500)
    assert emu.player_pos() == (4, 0)
    assert emu.lock_poll_calls == 2


@needs_mgba
def test_walk_lock_that_never_clears_raises_after_the_grace_not_instantly() -> None:
    """A lock that never releases on its own must still raise
    `WalkInterrupted` -- but only after burning `_INTERRUPT_GRACE`, not on
    the first frame it's seen (that would make a genuine cameo
    indistinguishable from an ambush)."""
    from rpg2gba.playtest.emulator import _INTERRUPT_GRACE, Emulator, WalkInterrupted

    emu = _FakeInterruptEmu(start=(0, 0), lock_at=(2, 0))
    with pytest.raises(WalkInterrupted) as excinfo:
        Emulator.walk_to(emu, 4, 0, frame_budget=2000)
    assert excinfo.value.battle is False
    assert excinfo.value.stopped_at == (2, 0)
    # Exactly the grace period's worth of 30-frame polls, not zero and not
    # unbounded.
    assert emu.lock_poll_calls == _INTERRUPT_GRACE // 30


@needs_mgba
def test_walk_battle_flagged_lock_raises_without_spending_the_grace() -> None:
    """A battle is never worth waiting out -- it must raise on the very
    first frame the lock (and the battle flag) is seen, not after burning
    `_INTERRUPT_GRACE` polling a script that was never going to release the
    field on its own."""
    from rpg2gba.playtest.emulator import Emulator, WalkInterrupted

    emu = _FakeInterruptEmu(start=(0, 0), battle_at=(2, 0))
    with pytest.raises(WalkInterrupted) as excinfo:
        Emulator.walk_to(emu, 4, 0, frame_budget=2000)
    assert excinfo.value.battle is True
    assert emu.lock_poll_calls == 0


# -- compatibility: a walk that begins already locked is unchanged ----------

@needs_mgba
def test_walk_already_locked_at_start_does_not_raise_walk_interrupted() -> None:
    """The CH01 ch01.py B5-hands-B6 shape: field is already locked when the
    walk begins, and later releases on its own. `walk_to` must wait it out
    exactly as before -- no `WalkInterrupted`."""
    from rpg2gba.playtest.emulator import Emulator

    emu = _FakeInterruptEmu(start=(0, 0), locked_at_start=True,
                            unlock_after_polls=2)
    Emulator.walk_to(emu, 3, 0, frame_budget=500)
    assert emu.player_pos() == (3, 0)


@needs_mgba
def test_walk_already_locked_that_never_releases_still_times_out_plainly() -> None:
    """If the field never releases, the old behaviour (a plain budget-
    exhausted `ScenarioError`, not `WalkInterrupted`) must still hold."""
    from rpg2gba.playtest.emulator import Emulator, WalkInterrupted
    from rpg2gba.playtest.errors import ScenarioError

    emu = _FakeInterruptEmu(start=(0, 0), locked_at_start=True)
    with pytest.raises(ScenarioError, match="frame budget exhausted") as excinfo:
        Emulator.walk_to(emu, 3, 0, frame_budget=200)
    assert not isinstance(excinfo.value, WalkInterrupted)


@needs_mgba
def test_walk_already_locked_that_turns_into_a_battle_raises_walk_interrupted() -> None:
    """2026-08-11 route1 B4 regression: the walk begins already locked (a
    trainer's notice sequence already mid-flight from an earlier
    interruption), and that lock turns into a real battle nobody is
    pressing buttons for. The old `start_locked` branch never re-checked
    `_in_battle()`, so it just kept waiting -- a battle with no player
    input never ends on its own, and the walk burned its whole
    `frame_budget` before failing with a bare "frame budget exhausted"
    instead of `WalkInterrupted`, which is what `_walk_absorbing`'s retry
    loop actually needs to catch and win the battle.

    Must now raise `WalkInterrupted(battle=True)` the moment the battle
    starts, not spend the rest of the budget waiting."""
    from rpg2gba.playtest.emulator import Emulator, WalkInterrupted

    emu = _FakeInterruptEmu(start=(0, 0), locked_at_start=True,
                            battle_after_polls=2)
    with pytest.raises(WalkInterrupted) as excinfo:
        Emulator.walk_to(emu, 3, 0, frame_budget=5000)
    assert excinfo.value.battle is True
    # Caught quickly (a couple of 30-frame polls), not after burning
    # anywhere near the full budget.
    assert emu.lock_poll_calls <= 3


# -- resolve_interruption ------------------------------------------------

@needs_mgba
def test_resolve_interruption_wins_a_battle_in_progress() -> None:
    from rpg2gba.playtest.emulator import Emulator

    emu = _FakeInterruptEmu(start=(0, 0), locked_at_start=True)
    emu._in_battle_flag = True

    win_calls = []

    def _fake_win_battle(passed_emu, **kwargs):
        win_calls.append(passed_emu)
        passed_emu._in_battle_flag = False
        passed_emu._locked = False
        return []

    import rpg2gba.playtest.battle as battle_module
    orig = battle_module.win_battle
    battle_module.win_battle = _fake_win_battle
    try:
        result = Emulator.resolve_interruption(emu)
    finally:
        battle_module.win_battle = orig

    assert result == "battle"
    assert win_calls == [emu]
    assert emu.field_locked() is False


@needs_mgba
def test_resolve_interruption_advances_dialogue_until_unlocked() -> None:
    from rpg2gba.playtest.emulator import Emulator

    emu = _FakeInterruptEmu(start=(0, 0), locked_at_start=True)
    result = Emulator.resolve_interruption(emu)
    assert result == "dialogue"
    assert emu.dialogue_advances == 1
    assert emu.field_locked() is False


@needs_mgba
def test_resolve_interruption_reports_none_when_nothing_is_interrupted() -> None:
    from rpg2gba.playtest.emulator import Emulator

    emu = _FakeInterruptEmu(start=(0, 0))
    result = Emulator.resolve_interruption(emu)
    assert result == "none"
    assert emu.dialogue_advances == 0


@needs_mgba
def test_resolve_interruption_fails_loud_if_still_locked_after_dialogue() -> None:
    from rpg2gba.playtest.emulator import Emulator
    from rpg2gba.playtest.errors import ScenarioError

    emu = _FakeInterruptEmu(start=(0, 0), locked_at_start=True)
    # advance_dialog is a no-op that never clears the lock.
    emu.advance_dialog = lambda key="A", max_taps=1500, stop=None: 1

    with pytest.raises(ScenarioError, match="still locked"):
        Emulator.resolve_interruption(emu)


# -- resolve_interruption: waiting for the overworld to actually be back ----
#
# 2026-08-11 route1 B4 regression: the ambush was detected and the battle
# correctly won, but the resumed walk landed a frame into the still-settling
# battle-end transition -- `gBackupMapLayout` still held the battle's own
# 30x30 stub grid and `map_location()` still read (0,0) -- so `_plan_route`
# refused the target with a "wrong map" error that pointed at the wrong
# layer. `resolve_interruption` must now wait out that settle itself.

@needs_mgba
def test_resolve_interruption_battle_waits_for_the_map_grid_to_settle() -> None:
    from rpg2gba.playtest.emulator import Emulator

    emu = _FakeInterruptEmu(start=(0, 0), locked_at_start=True,
                            grid_settle_polls=3)
    emu._in_battle_flag = True

    def _fake_win_battle(passed_emu, **kwargs):
        passed_emu._in_battle_flag = False
        passed_emu._locked = False
        return []

    import rpg2gba.playtest.battle as battle_module
    orig = battle_module.win_battle
    battle_module.win_battle = _fake_win_battle
    try:
        result = Emulator.resolve_interruption(emu)
    finally:
        battle_module.win_battle = orig

    assert result == "battle"
    # The battle itself clears the lock instantly (in this fake); the grid
    # settle is what actually took the 3 polls.
    assert emu.grid_poll_calls == 3


@needs_mgba
def test_resolve_interruption_dialogue_waits_for_the_map_grid_to_settle() -> None:
    from rpg2gba.playtest.emulator import Emulator

    emu = _FakeInterruptEmu(start=(0, 0), locked_at_start=True,
                            grid_settle_polls=2)
    result = Emulator.resolve_interruption(emu)
    assert result == "dialogue"
    assert emu.grid_poll_calls == 2


@needs_mgba
def test_resolve_interruption_raises_explicit_error_if_grid_never_settles() -> None:
    """A grid that never comes back must raise `resolve_interruption`'s own
    explicit diagnosis -- not silently return and let the caller's next
    `_plan_route` produce the confusing "wrong map" message instead."""
    from rpg2gba.playtest.emulator import Emulator
    from rpg2gba.playtest.errors import ScenarioError

    emu = _FakeInterruptEmu(start=(0, 0), locked_at_start=True,
                            grid_settle_polls=None)
    emu._in_battle_flag = True

    def _fake_win_battle(passed_emu, **kwargs):
        passed_emu._in_battle_flag = False
        passed_emu._locked = False
        return []

    import rpg2gba.playtest.battle as battle_module
    orig = battle_module.win_battle
    battle_module.win_battle = _fake_win_battle
    try:
        with pytest.raises(ScenarioError, match="overworld did not return") as excinfo:
            Emulator.resolve_interruption(emu, battle_settle_budget=100)
    finally:
        battle_module.win_battle = orig
    # Not the route-planner's "wrong map"/"outside the loaded map grid"
    # message -- that would point the reader at the wrong layer.
    assert "outside the loaded map grid" not in str(excinfo.value)
    assert "map_grid_loaded=False" in str(excinfo.value)


# -- resolve_interruptions=True: resume and reach the original target -------

@needs_mgba
def test_walk_to_resolve_interruptions_resumes_and_reaches_target() -> None:
    from rpg2gba.playtest.emulator import Emulator

    # The ambush tile (2, 0) sits on the straight-line route; once resolved
    # (dialogue branch clears the lock), the walk must resume and reach the
    # original target rather than stopping at the ambush point.
    emu = _FakeInterruptEmu(start=(0, 0), lock_at=(2, 0))
    Emulator.walk_to(emu, 4, 0, frame_budget=500, resolve_interruptions=True)
    assert emu.player_pos() == (4, 0)
    assert emu.dialogue_advances == 1


@needs_mgba
def test_walk_to_resolve_interruptions_wins_an_ambush_battle_then_arrives() -> None:
    from rpg2gba.playtest.emulator import Emulator

    emu = _FakeInterruptEmu(start=(0, 0), battle_at=(2, 0))

    def _fake_win_battle(passed_emu, **kwargs):
        passed_emu._in_battle_flag = False
        passed_emu._locked = False
        return []

    import rpg2gba.playtest.battle as battle_module
    orig = battle_module.win_battle
    battle_module.win_battle = _fake_win_battle
    try:
        Emulator.walk_to(emu, 4, 0, frame_budget=500, resolve_interruptions=True)
    finally:
        battle_module.win_battle = orig

    assert emu.player_pos() == (4, 0)


@needs_mgba
def test_walk_to_resolve_interruptions_waits_for_grid_settle_before_resuming() -> None:
    """The full 2026-08-11 route1 B4 shape end to end: an ambush battle is
    fought, the map grid takes a few polls to settle afterward, and only
    then does the walk resume -- reaching the original target rather than
    a `_plan_route` "wrong map" failure from resuming too early."""
    from rpg2gba.playtest.emulator import Emulator

    emu = _FakeInterruptEmu(start=(0, 0), battle_at=(2, 0),
                            grid_settle_polls=3)

    def _fake_win_battle(passed_emu, **kwargs):
        passed_emu._in_battle_flag = False
        passed_emu._locked = False
        return []

    import rpg2gba.playtest.battle as battle_module
    orig = battle_module.win_battle
    battle_module.win_battle = _fake_win_battle
    try:
        Emulator.walk_to(emu, 4, 0, frame_budget=500, resolve_interruptions=True)
    finally:
        battle_module.win_battle = orig

    assert emu.player_pos() == (4, 0)
    assert emu.grid_poll_calls == 3


# -- bounded resolutions: fails loud instead of looping forever -------------

@needs_mgba
def test_walk_to_resolve_interruptions_gives_up_after_the_cap() -> None:
    from rpg2gba.playtest.emulator import (
        Emulator,
        _MAX_INTERRUPTION_RESOLUTIONS,
    )
    from rpg2gba.playtest.errors import ScenarioError

    import rpg2gba.playtest.emulator as emulator_module
    from rpg2gba.playtest.emulator import WalkInterrupted

    def _always_interrupted(passed_emu, tx, ty, frame_budget, max_sidesteps):
        raise WalkInterrupted((tx, ty), (0, 0), False)

    emu = _AlwaysInterruptedEmu()
    orig = emulator_module._walk_to_once
    emulator_module._walk_to_once = _always_interrupted
    try:
        with pytest.raises(ScenarioError, match="still getting interrupted"):
            Emulator.walk_to(emu, 5, 5, resolve_interruptions=True)
    finally:
        emulator_module._walk_to_once = orig
    assert emu.resolve_calls == _MAX_INTERRUPTION_RESOLUTIONS


# -- 2026-08-14 B7 regression: raised cap + fresh per-attempt budget --------
#
# Route 1's 137 grass cells at a 25% per-step rate meant a ~10-15 tile grass
# crossing (Flood stands inside a field) plausibly needs several absorbed
# battles -- the old cap of 3 was routinely exceeded on the real ROM. These
# tests are isolated from real walking geometry (a minimal stand-in `_Emu`
# stubbing exactly `walk_to`/`is_trainer_battle`/`resolve_interruption`/
# `player_pos`/`screenshot`, not `_FakeInterruptEmu`'s fuller grid
# simulation) so they're about the retry loop's bound and budget-per-call


@needs_mgba
def test_walk_to_resolve_interruptions_passes_the_same_fresh_budget_every_retry() -> None:
    """Same fresh-budget guarantee, at the `Emulator.walk_to(
    resolve_interruptions=True)` layer: `_walk_to_once` must see the exact
    same `frame_budget` the caller passed to `walk_to`, on every retry."""
    from rpg2gba.playtest.emulator import Emulator, WalkInterrupted
    import rpg2gba.playtest.emulator as emulator_module

    budgets_seen: list[int] = []

    def _spy_walk_to_once(emu, tx, ty, frame_budget, max_sidesteps):
        budgets_seen.append(frame_budget)
        if len(budgets_seen) <= 2:
            raise WalkInterrupted((tx, ty), (0, 0), True)
        return None

    class _Emu:
        def resolve_interruption(self) -> str:
            return "battle"

    orig = emulator_module._walk_to_once
    emulator_module._walk_to_once = _spy_walk_to_once
    try:
        Emulator.walk_to(_Emu(), 5, 5, frame_budget=1234, resolve_interruptions=True)
    finally:
        emulator_module._walk_to_once = orig
    assert budgets_seen == [1234, 1234, 1234]


# -- walk_to(absorb_wild=True): the generated templates' policy (ROM run 55,
# two attempts each stopped by a random grass encounter) --------------------

class _AbsorbWildEmu:
    """Fake for `Emulator.walk_to(absorb_wild=True)`. `script` lists what
    each `_walk_to_once` call does: None arrives, else the interruption --
    ("wild"|"trainer", battle_flag, frames_until_battle)."""

    def __init__(self, script) -> None:
        from rpg2gba.playtest.emulator import Emulator
        self._absorb_wild_battle = Emulator._absorb_wild_battle.__get__(self)
        self.script = list(script)
        self.kind: str | None = None
        self.battle_in = 0
        self.locked = False
        self.shots: list[str] = []
        self.taps = 0
        self.settled = 0

    def _in_battle(self) -> bool:
        return self.kind is not None and self.battle_in <= 0

    def field_locked(self) -> bool:
        return self.locked

    def run(self, frames: int) -> None:
        self.battle_in -= frames

    def tap(self, _button: str) -> None:
        self.taps += 1

    def is_trainer_battle(self) -> bool:
        return self.kind == "trainer"

    def screenshot(self, name: str) -> str:
        self.shots.append(name)
        return name

    def player_pos(self) -> tuple[int, int]:
        return (0, 0)

    def _wait_for_overworld_return(self, _budget: int) -> None:
        self.settled += 1


def _run_absorb_wild(monkeypatch, emu: _AbsorbWildEmu) -> list[str]:
    from rpg2gba.playtest import battle
    from rpg2gba.playtest.emulator import Emulator, WalkInterrupted
    import rpg2gba.playtest.emulator as emulator_module

    won: list[str] = []

    def _win(e) -> None:
        won.append(e.kind)
        e.kind = None
        e.locked = False

    def _once(e, tx, ty, frame_budget, max_sidesteps) -> None:
        step = e.script.pop(0)
        if step is None:
            return
        kind, flag, frames = step
        e.kind, e.battle_in, e.locked = kind, frames, True
        raise WalkInterrupted((tx, ty), (0, 0), flag)

    monkeypatch.setattr(battle, "win_battle", _win)
    monkeypatch.setattr(emulator_module, "_walk_to_once", _once)
    Emulator.walk_to(emu, 5, 5, absorb_wild=True)
    return won


@needs_mgba
def test_walk_to_absorb_wild_wins_wild_battles_and_arrives(monkeypatch) -> None:
    emu = _AbsorbWildEmu([("wild", True, 0), ("wild", True, 0), None])
    assert _run_absorb_wild(monkeypatch, emu) == ["wild", "wild"]
    assert emu.settled == 2 and not emu.script


@needs_mgba
def test_walk_to_absorb_wild_hands_a_trainer_battle_back(monkeypatch) -> None:
    from rpg2gba.playtest.emulator import WalkInterrupted

    emu = _AbsorbWildEmu([("trainer", True, 0), None])
    with pytest.raises(WalkInterrupted):
        _run_absorb_wild(monkeypatch, emu)
    assert emu.kind == "trainer" and emu.settled == 0


@needs_mgba
def test_walk_to_absorb_wild_waits_for_a_lock_to_become_a_wild_battle(monkeypatch) -> None:
    """The encounter transition locks the field before `BattleMainCB2`
    owns the loop; the wait is input-free."""
    emu = _AbsorbWildEmu([("wild", False, 240), None])
    assert _run_absorb_wild(monkeypatch, emu) == ["wild"]
    assert emu.taps == 0


@needs_mgba
def test_walk_to_absorb_wild_reraises_a_lock_that_is_no_battle(monkeypatch) -> None:
    """A scene waiting on a button is left as found: nothing pressed, the
    original interruption re-raised, a screenshot of what it was."""
    from rpg2gba.playtest.emulator import WalkInterrupted

    emu = _AbsorbWildEmu([("scene", False, 10**6), None])
    with pytest.raises(WalkInterrupted) as info:
        _run_absorb_wild(monkeypatch, emu)
    assert info.value.battle is False
    assert emu.taps == 0 and emu.locked
    assert emu.shots == ["walk_to_lock_not_a_battle"]


@needs_mgba
def test_walk_to_absorb_wild_gives_up_after_the_cap(monkeypatch) -> None:
    from rpg2gba.playtest.emulator import _MAX_ABSORBED_WILD
    from rpg2gba.playtest.errors import ScenarioError

    emu = _AbsorbWildEmu([("wild", True, 0)] * _MAX_ABSORBED_WILD + [None])
    with pytest.raises(ScenarioError, match="absorbed"):
        _run_absorb_wild(monkeypatch, emu)


class _InteractEmu(_AbsorbWildEmu):
    """`Emulator.interact` against an encounter already under way (ROM run
    60): locked, overworld not reading input, a battle `battle_in` frames
    off. After it, A starts the caller's script."""

    def __init__(self, kind: str | None, battle_in: int, overworld: bool) -> None:
        super().__init__([])
        self.kind, self.battle_in, self.locked = kind, battle_in, kind is not None
        self.overworld = overworld
        self.pressed: list[str] = []
        self.message: str | None = None

    def overworld_input_ready(self) -> bool:
        return self.overworld or not self.locked

    def tap(self, button: str) -> None:
        self.pressed.append(button)
        if not self.locked:
            self.message = "Found an ANTIDOTE!"

    def clear_field_message(self) -> None:
        self.message = None

    def current_field_message_text(self) -> str | None:
        return self.message


def _interact(monkeypatch, emu: _InteractEmu) -> bool:
    from rpg2gba.playtest import battle
    from rpg2gba.playtest.emulator import Emulator

    def _win(e) -> None:
        e.kind, e.locked = None, False

    monkeypatch.setattr(battle, "win_battle", _win)
    return Emulator.interact(emu)


@needs_mgba
def test_interact_wins_an_encounter_already_under_way_before_pressing_a(monkeypatch) -> None:
    emu = _InteractEmu("wild", battle_in=12, overworld=False)
    assert _interact(monkeypatch, emu)
    assert emu.settled == 1 and emu.pressed == ["A"] and emu.message


@needs_mgba
def test_interact_leaves_a_lock_under_a_message_box_alone(monkeypatch) -> None:
    """Overworld still reading input: a scene, not a transition -- no wait,
    no screenshot, A pressed as before."""
    emu = _InteractEmu("scene", battle_in=10**6, overworld=True)
    emu.locked = True
    assert _interact(monkeypatch, emu)
    assert emu.settled == 0 and emu.shots == [] and emu.pressed == ["A"]


class _PreferAvoidEmu:
    """Fake for `_walk_to_once(prefer_avoid=...)`: planning fails whenever the
    avoid set contains `lane`, and records what each plan was asked to avoid."""

    def __init__(self, lane_routable: bool) -> None:
        self.lane_routable = lane_routable
        self.plans: list[frozenset] = []

    def wait_for_map_grid(self) -> int:
        return 0

    def map_location(self) -> tuple[int, int]:
        return (0, 0)

    def field_locked(self) -> bool:
        return False

    def _route_waypoints(self, tx, ty, avoid=frozenset()):
        from rpg2gba.playtest.errors import RoutePlanningError
        self.plans.append(frozenset(avoid))
        if (1, 1) in avoid and not self.lane_routable:
            raise RoutePlanningError("no route around the lane")
        return [(tx, ty)]

    def _walk_greedy(self, wx, wy, budget, sidesteps, start_map, *, start_locked):
        return True, 1, ""


@needs_mgba
def test_walk_to_once_routes_around_live_trainer_lanes_when_it_can() -> None:
    """Live trainers' lanes are a soft avoid: planned around first (CH09:
    a look-around trainer ambushed a walk to a neighbouring event)."""
    from rpg2gba.playtest.emulator import _walk_to_once
    emu = _PreferAvoidEmu(lane_routable=True)
    _walk_to_once(emu, 5, 5, 3000, 8, prefer_avoid=frozenset({(1, 1)}))
    assert emu.plans == [frozenset({(1, 1)})]


@needs_mgba
def test_walk_to_once_crosses_lanes_when_no_route_avoids_them() -> None:
    """With no route around the lanes the walk still goes, without them --
    a soft preference never turns a reachable target into a failure."""
    from rpg2gba.playtest.emulator import _walk_to_once
    emu = _PreferAvoidEmu(lane_routable=False)
    _walk_to_once(emu, 5, 5, 3000, 8, prefer_avoid=frozenset({(1, 1)}))
    assert emu.plans == [frozenset({(1, 1)}), frozenset()]
