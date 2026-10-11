"""PROJECT_TODO #133: a touch page on a turning sight trainer."""
from types import SimpleNamespace

import pytest

from rpg2gba.playtest import assertions
from rpg2gba.playtest.archetypes import generic
from rpg2gba.playtest.archetypes.generic import Step
from rpg2gba.playtest.errors import ScenarioError


class _Emu:
    """Trainer faces away: the bump starts nothing; only A does."""

    def __init__(self, a_locks: bool) -> None:
        self.a_locks = a_locks
        self.locked = False
        self.talked = 0

    def object_event(self, _lid):
        return SimpleNamespace(facing="north")

    def resolve_constant(self, name):
        return 0

    def field_locked(self):
        return self.locked

    def interact(self, **_kw):
        self.talked += 1
        self.locked = self.a_locks
        return self.locked

    def screenshot(self, name):
        return name


def _step():
    return Step("map033/ev053/p0", "trigger", 0, (("trigger", "event_touch"),))


@pytest.fixture(autouse=True)
def _no_walk(monkeypatch):
    monkeypatch.setattr(assertions, "try_step", lambda emu, d: False)


def test_unseen_sight_trainer_falls_back_to_talking():
    emu = _Emu(a_locks=True)
    generic._handle_trigger(emu, "b", _step(), talk_if_unseen=True)
    assert emu.talked == 1


def test_non_trainer_touch_still_fails_loud():
    emu = _Emu(a_locks=True)
    with pytest.raises(ScenarioError, match="started no script"):
        generic._handle_trigger(emu, "b", _step())
    assert emu.talked == 0


def test_trainer_that_never_starts_still_fails_loud():
    emu = _Emu(a_locks=False)
    with pytest.raises(ScenarioError, match="started no script"):
        generic._handle_trigger(emu, "b", _step(), talk_if_unseen=True)
