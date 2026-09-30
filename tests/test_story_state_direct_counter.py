"""A counter a computed row touches only through constant `122`s is those
writes, not TOP (ROM run 34: the rival scene's `var 101 += 1` as TOP put
CH06's Pokédex-evaluation page into CH01)."""
from __future__ import annotations

from rpg2gba.story_state.model import _direct_counter_writes
from rpg2gba.story_state.scope_search import ComputedScope
from rpg2gba.story_state.state import Adjust, Assign, Variable


def _scope(commands, common_events=None):
    return ComputedScope(
        row_id="map050/ev019/p0", map_id=50, event_id=19, commands=commands,
        index_of={id(c): i for i, c in enumerate(commands)},
        common_events_by_id=common_events or {}, stripped_ce_ids=frozenset(),
        conditional=False, first_unknown_read="Variable(id=151)")


def _cmd(code, params, indent=0):
    return {"code": code, "indent": indent, "parameters": params}


def test_constant_add_is_an_adjust():
    commands = [
        _cmd(355, ["$game_switches[60] = true if $game_variables[151]==3"]),
        _cmd(122, [101, 101, 1, 0, 1]),
    ]
    assert _direct_counter_writes(_scope(commands), Variable(101)) == [
        Adjust(Variable(101), "+", 1, False, "code 122 @list[1]", 1)]


def test_constant_set_is_an_assign():
    commands = [_cmd(122, [101, 101, 0, 0, 4])]
    assert _direct_counter_writes(_scope(commands), Variable(101)) == [
        Assign(Variable(101), frozenset({4}), False, "code 122 @list[0]", 0)]


def test_a_script_naming_the_var_is_not_the_whole_story():
    commands = [_cmd(355, ["pbSet(101, pbGet(101) * 2)"]), _cmd(122, [101, 101, 1, 0, 1])]
    assert _direct_counter_writes(_scope(commands), Variable(101)) is None


def test_a_branch_testing_the_var_is_not_the_whole_story():
    commands = [_cmd(111, [1, 101, 0, 2, 0]), _cmd(122, [101, 101, 1, 0, 1], indent=1)]
    assert _direct_counter_writes(_scope(commands), Variable(101)) is None


def test_a_write_under_a_branch_is_not_unconditional():
    commands = [_cmd(111, [0, 5, 0]), _cmd(122, [101, 101, 1, 0, 1], indent=1)]
    assert _direct_counter_writes(_scope(commands), Variable(101)) is None


def test_a_variable_operand_is_unknown():
    commands = [_cmd(122, [101, 101, 1, 1, 7])]
    assert _direct_counter_writes(_scope(commands), Variable(101)) is None


def _row(row_id, *, pages, page_tests=(), writes=(), computed=None):
    import dataclasses

    from rpg2gba.story_state.extract import RowState

    values = {}
    for f in dataclasses.fields(RowState):
        if f.default is not dataclasses.MISSING:
            values[f.name] = f.default
        elif f.default_factory is not dataclasses.MISSING:
            values[f.name] = f.default_factory()
        else:
            values[f.name] = None
    values.update(row_id=row_id, parent_row_id=None, page_tests=page_tests, writes=writes,
                  refusals=(), event_page_row_ids=pages, computed=computed)
    return RowState(**values)


def test_a_counter_that_hands_its_event_to_a_higher_page_is_exact():
    from rpg2gba.story_state.model import _self_retiring_counters
    from rpg2gba.story_state.state import Test

    pages = ("map050/ev019/p0", "map050/ev019/p1")
    scope = _scope([_cmd(122, [101, 101, 1, 0, 1])])
    rival = _row(pages[0], pages=pages, computed=scope)
    rows = {
        pages[0]: rival,
        pages[1]: _row(pages[1], pages=pages, page_tests=(Test(Variable(101), ">=", 1),)),
        "map172/ev004/p0": _row("map172/ev004/p0", pages=("map172/ev004/p0",), writes=(
            Assign(Variable(101), frozenset({2}), False, "x", 0),)),
    }
    seed = {Variable(101): frozenset({0})}
    assert _self_retiring_counters(rival, rows, seed) == frozenset({Variable(101)})

    # A writer that resets the counter below the threshold re-opens the page.
    rows["map172/ev004/p0"] = _row("map172/ev004/p0", pages=("map172/ev004/p0",), writes=(
        Assign(Variable(101), frozenset({0}), False, "x", 0),))
    assert _self_retiring_counters(rival, rows, seed) == frozenset()


def test_a_repeatable_counter_is_not_exact():
    from rpg2gba.story_state.model import _self_retiring_counters

    pages = ("map031/ev014/p0",)
    npc = _row(pages[0], pages=pages, computed=_scope([_cmd(122, [200, 200, 1, 0, 1])]))
    assert _self_retiring_counters(npc, {pages[0]: npc}, {}) == frozenset()


def test_a_common_event_writing_the_var_is_not_the_whole_story():
    ce = {"list": [_cmd(122, [100, 102, 0, 0, 0])]}
    commands = [_cmd(117, [9]), _cmd(122, [101, 101, 1, 0, 1])]
    assert _direct_counter_writes(_scope(commands, {9: ce}), Variable(101)) is None
