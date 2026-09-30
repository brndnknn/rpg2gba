"""Conditional state writes (`beat_floor.cond_write`, ROM run 33): a write
story_state marks `conditional` is checked on the ROM's own inputs, never
asserted as certain."""
from __future__ import annotations

import dataclasses

import pytest

from rpg2gba.beat_floor import walk
from rpg2gba.beat_floor.cond_write import cond_write_inputs, evaluated_writes
from rpg2gba.playtest.archetypes import generic
from rpg2gba.story_state.state import Assign, Switch

STARTER_FLAGS = (
    "$game_switches[61] = true if $game_variables[151]==1\n"
    "$game_switches[59] = true if $game_variables[151]==2\n"
    "$game_switches[60] = true if $game_variables[151]==3"
)


def test_inputs_are_the_variables_read():
    assert cond_write_inputs(STARTER_FLAGS) == (151,)


def test_inputs_refuse_a_non_variable_read():
    assert cond_write_inputs("$game_switches[5] = true if $Trainer.money > 10") is None


@pytest.mark.parametrize(("pick", "switch"), [(1, 61), (2, 59), (3, 60)])
def test_evaluation_selects_one_starter_flag(pick, switch):
    assert evaluated_writes(STARTER_FLAGS, {151: pick}) == {Switch(switch): True}


# --- floor ---------------------------------------------------------------


def _row_state(*writes):
    fields = {f.name for f in dataclasses.fields(walk.RowState)}
    kwargs = {name: None for name in fields}
    kwargs.update(row_id="map050/ev019/p0", writes=tuple(writes), refusals=())
    # Remaining fields keep their dataclass defaults where they have one.
    for f in dataclasses.fields(walk.RowState):
        if kwargs[f.name] is None and f.default is not dataclasses.MISSING:
            kwargs[f.name] = f.default
        elif kwargs[f.name] is None and f.default_factory is not dataclasses.MISSING:
            kwargs[f.name] = f.default_factory()
    return walk.RowState(**kwargs)


def test_conditional_write_carries_its_script():
    write = Assign(Switch(60), frozenset({True}), True, "script @list[14]", 14)
    assertions, refusals = walk._state_assertions_for_row(
        "map050/ev019/p0", _row_state(write), {14: STARTER_FLAGS})
    assert refusals == ()
    (sw,) = assertions
    params = dict(sw.params)
    assert params["switch_id"] == 60
    assert params["script"] == STARTER_FLAGS
    assert params["input_vars"] == (151,)
    assert list(sw.params) == sorted(sw.params)  # make_params stays canonical


def test_unconditional_write_has_no_script():
    write = Assign(Switch(2), frozenset({True}), False, "code 121 @list[255]", 255)
    (sw,), _ = walk._state_assertions_for_row(
        "map050/ev019/p0", _row_state(write), {14: STARTER_FLAGS})
    assert "script" not in dict(sw.params)


def test_unevaluable_conditional_write_refuses_by_name():
    write = Assign(Switch(60), frozenset({True}), True, "interpreter CE 5", 7)
    assertions, refusals = walk._state_assertions_for_row(
        "map050/ev019/p0", _row_state(write), {})
    assert assertions == ()
    assert [r.reason for r in refusals] == ["conditional_state_write"]


# --- ROM check -------------------------------------------------------------


class _Emu:
    def __init__(self, pick: int, flags: dict[str, bool]):
        self.pick = pick
        self.flags = flags

    def var(self, name):
        return self.pick

    def flag(self, name):
        return self.flags[name]

    def screenshot(self, name):
        return f"{name}.png"


class _Registry:
    def get_var(self, var_id):
        return f"VAR_{var_id}"

    def get_flag(self, switch_id):
        return f"FLAG_{switch_id}"


def _step(switch_id):
    return generic.Step("map050/ev019/p0", "switch_write", 14, (
        ("input_vars", (151,)), ("script", STARTER_FLAGS),
        ("switch_id", switch_id), ("value", True)))


def test_rom_checks_only_the_selected_flag(monkeypatch):
    monkeypatch.setattr(generic, "_flag_registry", lambda: _Registry())
    emu = _Emu(2, {"FLAG_59": True, "FLAG_60": False, "FLAG_61": False})
    for switch_id in (59, 60, 61):
        generic.STEP_HANDLERS["switch_write"](emu, "B", _step(switch_id))


def test_rom_fails_when_the_selected_flag_is_unset(monkeypatch):
    from rpg2gba.playtest.errors import ScenarioError

    monkeypatch.setattr(generic, "_flag_registry", lambda: _Registry())
    emu = _Emu(3, {"FLAG_59": True, "FLAG_60": False, "FLAG_61": False})
    with pytest.raises(ScenarioError, match="FLAG_60 reads False"):
        generic.STEP_HANDLERS["switch_write"](emu, "B", _step(60))
