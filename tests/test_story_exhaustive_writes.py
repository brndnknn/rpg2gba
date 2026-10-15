"""`story_state.scope_search.writes_exhaustively_named` / `named_write_targets`
(CH08, 2026-10-15) and `model._self_switch_retired_counters`."""
from __future__ import annotations

from types import SimpleNamespace

from rpg2gba.story_state.model import _self_switch_retired_counters
from rpg2gba.story_state.scope_search import named_write_targets, writes_exhaustively_named
from rpg2gba.story_state.state import SelfSwitch, Switch, Test, Variable

M, E = 46, 2


def _script(*lines: str, indent: int = 0) -> list[dict]:
    out = [{"code": 355, "indent": indent, "parameters": [lines[0]]}]
    out += [{"code": 655, "indent": indent, "parameters": [ln]} for ln in lines[1:]]
    return out


def _named(cmds):
    return named_write_targets(cmds, map_id=M, event_id=E)


def _exhaustive(cmds):
    return writes_exhaustively_named(cmds, map_id=M, event_id=E)


# --- the real Map046 EV002 nickname shape ---------------------------------

NICKNAME = _script("pkmn=$Trainer.party[", "pbGet(1)]", "pkmn.name=pbGet(5)")


def test_nickname_block_is_exhaustive_and_names_nothing():
    assert _exhaustive(NICKNAME) is True
    assert _named(NICKNAME) == ()


# --- plain write commands ---------------------------------------------------

def test_plain_commands_named_when_all_blocks_parse():
    cmds = NICKNAME + [
        {"code": 121, "indent": 0, "parameters": [10, 12, 0]},
        {"code": 122, "indent": 0, "parameters": [100, 101, 1, 0, 1]},
        {"code": 123, "indent": 0, "parameters": ["A", 0]},
    ]
    assert set(_named(cmds)) == {
        Switch(10), Switch(11), Switch(12), Variable(100), Variable(101),
        SelfSwitch(M, E, "A")}
    assert _exhaustive(cmds) is True


def test_plain_commands_alone_without_scripts_are_named():
    cmds = [{"code": 121, "indent": 0, "parameters": [5, 5, 0]}]
    assert _named(cmds) == (Switch(5),)


def test_unparseable_block_keeps_commands_unnamed():
    cmds = _script("if if if ((") + [{"code": 121, "indent": 0, "parameters": [10, 10, 0]}]
    assert _named(cmds) == ()
    assert _exhaustive(cmds) is False


def test_unparseable_block_still_names_its_literal_keys_not_commands():
    cmds = _script("$game_switches[7] = true; if if ((") + [
        {"code": 121, "indent": 0, "parameters": [10, 10, 0]}]
    assert Switch(10) not in _named(cmds)


# --- exhaustiveness negatives ----------------------------------------------

def test_unknown_call_is_not_exhaustive():
    assert _exhaustive(_script("fooBar(1)")) is False


def test_common_event_call_is_not_exhaustive():
    assert _exhaustive([{"code": 117, "indent": 0, "parameters": [3]}]) is False


def test_no_script_no_ce_is_exhaustive():
    assert _exhaustive([{"code": 121, "indent": 0, "parameters": [1, 1, 0]}]) is True
    assert _exhaustive([]) is True


def test_assignment_to_unnameable_global_is_not_exhaustive():
    assert _exhaustive(_script("$game_switches[i] = true")) is False


def test_assignment_to_nameable_key_is_exhaustive():
    cmds = _script("$game_switches[12] = true")
    assert _exhaustive(cmds) is True
    assert _named(cmds) == (Switch(12),)


def test_naming_calls_pbset_and_textentry():
    assert Variable(4) in _named(_script("pbSet(4,1)"))
    cmds = _script("pbTextEntry(\"Name?\",0,10,7,pkmn)")
    assert _named(cmds) == (Variable(7),)


def test_trainer_party_read_is_ok_but_other_trainer_call_is_not():
    assert _exhaustive(_script("x=$Trainer.party")) is True
    assert _exhaustive(_script("$Trainer.fooBar")) is False


# --- pbChoosePokemon with a filter proc -------------------------------------

CHOOSE = "pbChoosePokemon(1,2,proc {|p| p.species==5 })"


def test_choose_with_filter_names_both_vars_and_is_exhaustive():
    cmds = _script(CHOOSE)
    assert _named(cmds) == (Variable(1), Variable(2))
    assert _exhaustive(cmds) is True


def test_choose_with_filter_rejects_assignment_in_proc():
    cmds = _script("pbChoosePokemon(1,2,proc {|p| p.hp=0 })")
    assert _named(cmds) == ()
    assert _exhaustive(cmds) is False


def test_choose_with_filter_allows_comparisons():
    cmds = _script("pbChoosePokemon(1,2,proc {|p| p.level>=5 && p.hp!=0 })")
    assert _named(cmds) == (Variable(1), Variable(2))


# --- _self_switch_retired_counters -----------------------------------------

def _row(commands, row_id="map042/ev003/p0/b1"):
    computed = SimpleNamespace(commands=commands, common_events_by_id={}, conditional=False,
                               index_of={id(c): i for i, c in enumerate(commands)})
    return SimpleNamespace(row_id=row_id, computed=computed)


def _page(map_id=42, event_id=3, letter="A", value=True):
    return SimpleNamespace(page_tests=(Test(SelfSwitch(map_id, event_id, letter), "==", value),))


def _cmds(switch_indent=0, add_indent=0, letter="A"):
    return [
        {"code": 123, "indent": switch_indent, "parameters": [letter, 0]},
        {"code": 122, "indent": add_indent, "parameters": [101, 101, 1, 0, 1]},
    ]


def _retired(commands, pages, higher=("map042/ev003/p1",)):
    return _self_switch_retired_counters(_row(commands), pages, list(higher), {})


def test_counter_retired_by_self_switch_is_exact():
    assert _retired(_cmds(), {"map042/ev003/p1": _page()}) == frozenset({Variable(101)})


def test_counter_not_exact_when_higher_page_gated_on_other_letter():
    assert _retired(_cmds(), {"map042/ev003/p1": _page(letter="B")}) == frozenset()


def test_counter_not_exact_when_switch_set_deeper_than_add():
    assert _retired(_cmds(switch_indent=1, add_indent=0),
                    {"map042/ev003/p1": _page()}) == frozenset()


def test_counter_not_exact_for_other_event_page_or_assign():
    assert _retired(_cmds(), {"map042/ev003/p1": _page(event_id=9)}) == frozenset()
    sets = [{"code": 123, "indent": 0, "parameters": ["A", 0]},
            {"code": 122, "indent": 0, "parameters": [101, 101, 0, 0, 1]}]
    assert _retired(sets, {"map042/ev003/p1": _page()}) == frozenset()
