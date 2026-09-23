"""Tests for `rpg2gba.story_state.extract` (REDERIVATION_PLAN.md §16.3 C2a).

Synthetic fixtures follow `test_chapter_manifest_generator.py`'s `_page`/
`_cmd` style (reused directly -- one page/command-builder implementation,
CLAUDE.md §4.3). The real-data test walks every CH01-CH05 map and skips when
`output/uranium-build/` is absent, matching the pattern used throughout this
test suite.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from rpg2gba.chapter_manifest.generator import generate_chapter_manifest
from rpg2gba.chapter_manifest.schema import branch_row_id, page_row_id
from rpg2gba.conversion_agent.flag_registry import load_label_tables
from rpg2gba.story_state.extract import (
    ArmGuard,
    RowState,
    extract_map,
    extract_triggered_common_events,
)
from rpg2gba.story_state.state import (
    RESPAWN_MAP,
    Adjust,
    Assign,
    SelfSwitch,
    Switch,
    TempSwitch,
    Test,
    Variable,
)
from tests.test_chapter_manifest_generator import _cmd, _page

OUT_DIR = Path("output/uranium-build")
CHAPTERS_PATH = Path("reference/chapters.json")


def _event(event_id: int, pages: list[dict], *, x: int = 0, y: int = 0, name: str | None = None) -> dict:
    return {"id": event_id, "name": name, "x": x, "y": y, "pages": pages}


def _map(events: list[dict]) -> dict:
    return {"map_id": 999, "tileset_id": 1, "width": 10, "height": 10, "events": events}


def _common_event(ce_id: int, commands: list[dict]) -> dict:
    return {"id": ce_id, "name": "", "trigger": 0, "switch_id": 1, "list": commands}


# --- page-condition reads -------------------------------------------------


def test_switch_page_condition_is_a_switch_test() -> None:
    page = _page([_cmd(101, ["hi"])], condition={"switch1_valid": True, "switch1_id": 5})
    events = [_event(1, [page])]
    rows = extract_map(999, _map(events), common_events=[], switch_labels={5: "Got Item"})

    row = rows[page_row_id(999, 1, 0)]
    assert row.page_tests == (Test(Switch(5), "==", True),)
    assert row.page_refusals == ()


def test_variable_page_condition_is_a_ge_test() -> None:
    page = _page([_cmd(101, ["hi"])], condition={
        "variable_valid": True, "variable_id": 7, "variable_value": 3})
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={})

    row = rows[page_row_id(999, 1, 0)]
    assert row.page_tests == (Test(Variable(7), ">=", 3),)


def test_self_switch_page_condition() -> None:
    page = _page([_cmd(101, ["hi"])], condition={"self_switch_valid": True, "self_switch_ch": "A"})
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={})

    row = rows[page_row_id(999, 1, 0)]
    assert row.page_tests == (Test(SelfSwitch(999, 1, "A"), "==", True),)


def test_runtime_predicate_switch_refuses_unless_temp_switch() -> None:
    page = _page([_cmd(101, ["hi"])], condition={"switch1_valid": True, "switch1_id": 5})
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={5: "s:someWeirdPredicate"})

    row = rows[page_row_id(999, 1, 0)]
    assert row.page_tests == ()
    assert row.page_refusals == (
        ("unmodelled_predicate",
         "page condition switch1 (switch 5): runtime predicate 's:someWeirdPredicate' "
         "is not tsOn?/tsOff? -- not modelled"),
    ) or row.page_refusals[0].code == "unmodelled_predicate"


def test_runtime_predicate_temp_switch_on() -> None:
    page = _page([_cmd(101, ["hi"])], condition={"switch1_valid": True, "switch1_id": 9})
    rows = extract_map(999, _map([_event(2, [page])]), common_events=[], switch_labels={9: 's:tsOn?("A")'})

    row = rows[page_row_id(999, 2, 0)]
    assert row.page_tests == (Test(TempSwitch(999, 2, "A"), "==", True),)
    assert row.page_refusals == ()


# --- arm guards: 111 switch/variable/self-switch/facing -------------------


def test_arm_guard_switch_then_else() -> None:
    page = _page([
        _cmd(111, [0, 12, 0], indent=0),  # switch 12 ON
        _cmd(101, ["then"], indent=1),
        _cmd(411, [], indent=0),
        _cmd(101, ["else"], indent=1),
        _cmd(412, [], indent=0),
    ])
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={})
    page_id = page_row_id(999, 1, 0)
    then_row = rows[branch_row_id(page_id, 0)]
    else_row = rows[branch_row_id(page_id, 1)]

    assert then_row.arm_guard == ArmGuard(
        tests=(Test(Switch(12), "==", True),), negated=False, opener_index=0)
    assert else_row.arm_guard == ArmGuard(
        tests=(Test(Switch(12), "==", False),), negated=True, opener_index=0)


def test_arm_guard_variable_cmp_negates_on_else() -> None:
    page = _page([
        _cmd(111, [1, 3, 0, 5, 1], indent=0),  # var 3 >= 5
        _cmd(101, ["then"], indent=1),
        _cmd(412, [], indent=0),
    ])
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={})
    page_id = page_row_id(999, 1, 0)
    then_row = rows[branch_row_id(page_id, 0)]
    else_row = rows[branch_row_id(page_id, 1)]

    assert then_row.arm_guard.tests == (Test(Variable(3), ">=", 5),)
    assert else_row.arm_guard.tests == (Test(Variable(3), "<", 5),)
    assert else_row.arm_guard.negated is True


def test_arm_guard_self_switch() -> None:
    page = _page([
        _cmd(111, [2, "B", 0], indent=0),
        _cmd(101, ["then"], indent=1),
        _cmd(412, [], indent=0),
    ])
    rows = extract_map(999, _map([_event(4, [page])]), common_events=[], switch_labels={})
    page_id = page_row_id(999, 4, 0)
    then_row = rows[branch_row_id(page_id, 0)]
    assert then_row.arm_guard.tests == (Test(SelfSwitch(999, 4, "B"), "==", True),)


def test_arm_guard_facing_is_input() -> None:
    page = _page([
        _cmd(111, [6, -1, 2], indent=0),
        _cmd(101, ["then"], indent=1),
        _cmd(412, [], indent=0),
    ])
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={})
    page_id = page_row_id(999, 1, 0)
    then_row = rows[branch_row_id(page_id, 0)]
    assert then_row.arm_guard.tests == ()
    assert then_row.arm_guard.outcome.kind == "input"


def test_nonconstant_variable_condition_refuses() -> None:
    page = _page([
        _cmd(111, [1, 3, 1, 4, 1], indent=0),  # operand_kind 1 -- another variable
        _cmd(101, ["then"], indent=1),
        _cmd(412, [], indent=0),
    ])
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={})
    page_id = page_row_id(999, 1, 0)
    then_row = rows[branch_row_id(page_id, 0)]
    assert then_row.arm_guard is None
    assert then_row.refusals[0].code == "nonconstant_variable_condition"


def test_unclassified_script_condition_refuses() -> None:
    page = _page([
        _cmd(111, [12, "some_totally_unknown_call(1,2)"], indent=0),
        _cmd(101, ["then"], indent=1),
        _cmd(412, [], indent=0),
    ])
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={})
    page_id = page_row_id(999, 1, 0)
    then_row = rows[branch_row_id(page_id, 0)]
    assert then_row.arm_guard is None
    assert then_row.refusals[0].code == "unclassified_condition"


def test_game_variables_cmp_family_parses_a_concrete_test() -> None:
    page = _page([
        _cmd(111, [12, "$game_variables[9]==2"], indent=0),
        _cmd(101, ["then"], indent=1),
        _cmd(412, [], indent=0),
    ])
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={})
    page_id = page_row_id(999, 1, 0)
    then_row = rows[branch_row_id(page_id, 0)]
    else_row = rows[branch_row_id(page_id, 1)]
    assert then_row.arm_guard.tests == (Test(Variable(9), "==", 2),)
    assert else_row.arm_guard.tests == (Test(Variable(9), "!=", 2),)


def test_is_temp_switch_off_family_uses_running_event() -> None:
    page = _page([
        _cmd(111, [12, 'isTempSwitchOff?("Z")'], indent=0),
        _cmd(101, ["then"], indent=1),
        _cmd(412, [], indent=0),
    ])
    rows = extract_map(999, _map([_event(7, [page])]), common_events=[], switch_labels={})
    page_id = page_row_id(999, 7, 0)
    then_row = rows[branch_row_id(page_id, 0)]
    else_row = rows[branch_row_id(page_id, 1)]
    assert then_row.arm_guard.tests == (Test(TempSwitch(999, 7, "Z"), "==", False),)
    assert else_row.arm_guard.tests == (Test(TempSwitch(999, 7, "Z"), "==", True),)


def test_choice_arm_guard_is_input_with_choice_index() -> None:
    page = _page([
        _cmd(102, [["A", "B"], 0], indent=0),
        _cmd(402, [0, "A"], indent=0),
        _cmd(101, ["a text"], indent=1),
        _cmd(402, [1, "B"], indent=0),
        _cmd(101, ["b text"], indent=1),
        _cmd(404, [], indent=0),
    ])
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={})
    page_id = page_row_id(999, 1, 0)
    arm0 = rows[branch_row_id(page_id, 0)]
    assert arm0.arm_guard.outcome.kind == "input"
    assert arm0.arm_guard.choice_index == 0


# --- writes: 121/122/123 ---------------------------------------------------


def test_switch_write_range() -> None:
    page = _page([_cmd(121, [10, 12, 0])])
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={})
    row = rows[page_row_id(999, 1, 0)]
    assert row.writes == (
        Assign(Switch(10), frozenset({True}), False, "code 121 @list[0]", 0),
        Assign(Switch(11), frozenset({True}), False, "code 121 @list[0]", 0),
        Assign(Switch(12), frozenset({True}), False, "code 121 @list[0]", 0),
    )


def test_switch_write_off() -> None:
    page = _page([_cmd(121, [3, 3, 1])])
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={})
    row = rows[page_row_id(999, 1, 0)]
    assert row.writes == (Assign(Switch(3), frozenset({False}), False, "code 121 @list[0]", 0),)


def test_variable_write_constant() -> None:
    page = _page([_cmd(122, [4, 4, 0, 0, 7])])
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={})
    row = rows[page_row_id(999, 1, 0)]
    assert row.writes == (Assign(Variable(4), frozenset({7}), False, "code 122 @list[0]", 0),)


def test_variable_write_random_range() -> None:
    page = _page([_cmd(122, [4, 4, 0, 2, 1, 3])])
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={})
    row = rows[page_row_id(999, 1, 0)]
    assert row.writes == (Assign(Variable(4), frozenset({1, 2, 3}), False, "code 122 @list[0]", 0),)


def test_variable_write_adjust() -> None:
    page = _page([_cmd(122, [4, 4, 1, 0, 2])])  # add 2
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={})
    row = rows[page_row_id(999, 1, 0)]
    assert row.writes == (Adjust(Variable(4), "+", 2, False, "code 122 @list[0]", 0),)


def test_variable_write_nonconstant_refuses() -> None:
    page = _page([_cmd(122, [4, 4, 0, 1, 5])])  # operand_kind 1 -- another variable
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={})
    row = rows[page_row_id(999, 1, 0)]
    assert row.writes == ()
    assert row.refusals[0].code == "nonconstant_variable_write"


def test_self_switch_write() -> None:
    page = _page([_cmd(123, ["A", 0])])
    rows = extract_map(999, _map([_event(5, [page])]), common_events=[], switch_labels={})
    row = rows[page_row_id(999, 5, 0)]
    assert row.writes == (
        Assign(SelfSwitch(999, 5, "A"), frozenset({True}), False, "code 123 @list[0]", 0),)


# --- writes: scripts --------------------------------------------------


def test_script_writes_every_recognized_shape() -> None:
    script_text = "\n".join([
        'pbSetSelfSwitch(9, "A", true)',
        'setTempSwitchOn("Q")',
        'setTempSwitchOff("R")',
        "$game_switches[20] = true",
        "$game_variables[21] = 4",
        "pbSet(22, 5)",
    ])
    page = _page([_cmd(355, [script_text.splitlines()[0]])] + [
        _cmd(655, [line]) for line in script_text.splitlines()[1:]
    ])
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={})
    row = rows[page_row_id(999, 1, 0)]
    keys_values = {(type(w.key).__name__, getattr(w.key, "id", getattr(w.key, "letter", None)), w.values) for w in row.writes}
    assert ("SelfSwitch", "A", frozenset({True})) in keys_values
    assert ("TempSwitch", "Q", frozenset({True})) in keys_values
    assert ("TempSwitch", "R", frozenset({False})) in keys_values
    assert ("Switch", 20, frozenset({True})) in keys_values
    assert ("Variable", 21, frozenset({4})) in keys_values
    assert ("Variable", 22, frozenset({5})) in keys_values
    assert row.refusals == ()


# --- writes: pbSetPokemonCenter (REDERIVATION_PLAN.md §16.3 C3) -----------


def test_pokemon_center_bare_call_writes_the_calling_map() -> None:
    page = _page([_cmd(355, ["pbSetPokemonCenter"])])
    rows = extract_map(68, _map([_event(1, [page])]), common_events=[], switch_labels={})
    row = rows[page_row_id(68, 1, 0)]
    assert len(row.writes) == 1
    w = row.writes[0]
    assert (w.key, w.values, w.conditional, w.list_index) == (RESPAWN_MAP, frozenset({68}), False, 0)
    assert row.refusals == ()
    assert row.computed is None


def test_pokemon_center_explicit_call_writes_its_first_argument() -> None:
    page = _page([_cmd(355, ["Kernel.pbSetPokemonCenter(49, 7, 7, 2)"])])
    rows = extract_map(68, _map([_event(1, [page])]), common_events=[], switch_labels={})
    row = rows[page_row_id(68, 1, 0)]
    assert len(row.writes) == 1
    w = row.writes[0]
    assert (w.key, w.values, w.conditional, w.list_index) == (RESPAWN_MAP, frozenset({49}), False, 0)
    assert row.refusals == ()


def test_pokemon_center_unparseable_arguments_refuses_by_name() -> None:
    """`someVariable` is an undefined bareword -- Ruby (and this
    interpreter) reads that as a zero-arg method call, so the real refusal
    is `ruby_unknown_call:someVariable`, not the old regex reader's own
    invented `unparseable_pokemon_center_call` code (REDERIVATION_PLAN.md
    §16.3 C8 stage 4: "pass the interpreter's own code through unchanged")."""
    page = _page([_cmd(355, ["pbSetPokemonCenter(someVariable, 7, 7, 2)"])])
    rows = extract_map(68, _map([_event(1, [page])]), common_events=[], switch_labels={})
    row = rows[page_row_id(68, 1, 0)]
    assert row.writes == ()
    assert row.refusals[0].code == "ruby_unknown_call:someVariable"
    assert row.havoc_global is True


def test_unparsed_state_write_becomes_a_computed_row() -> None:
    """`$game_variables[3] += 1` reads `Variable(3)` before writing it --
    an out-of-scope read at extraction time (`read_domain` always returns
    `None`), so this row DEFERS instead of refusing outright
    (REDERIVATION_PLAN.md §16.3 C8 stage 4: "a script-bearing row whose run
    reads out-of-scope state ... becomes computed"). Until the resolver
    half lands, it still surfaces `unparsed_state_write`/`havoc_global` so
    every EXISTING consumer stays sound in the interim."""
    page = _page([_cmd(355, ["$game_variables[3] += 1"])])
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={})
    row = rows[page_row_id(999, 1, 0)]
    assert row.writes == ()
    assert row.refusals[0].code == "unparsed_state_write"
    assert row.havoc_global is True
    assert row.computed is not None
    assert row.computed.first_unknown_read == "Variable(id=3)"
    assert row.computed.row_id == page_row_id(999, 1, 0)


def test_compound_assignment_to_a_ruby_local_is_not_state() -> None:
    """map050/ev019's starter script does `x=pbGet(151)` / `x-=2`: the local
    is scratch. `pbGet(151)` reads `Variable(151)` before anything in this
    scope writes it, so the WHOLE row (not just the third line) defers as
    computed -- the interpreter runs the full scope together, unlike the
    old line-by-line regex reader."""
    page = _page([_cmd(355, ["x=pbGet(151)"]), _cmd(655, ["x-=2"]),
                  _cmd(355, ["pbGet(151)[pbGet(2)] += 1"])])
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={})
    row = rows[page_row_id(999, 1, 0)]
    assert row.writes == ()
    assert row.computed is not None
    assert row.computed.first_unknown_read == "Variable(id=151)"


def test_non_state_script_call_with_no_reads_or_writes_is_not_a_refusal() -> None:
    """`pbSave` is a registered no-state-effect call (`ruby_subset.
    builtins.EFFECT_CALLS`) -- a script that only calls it writes nothing
    and refuses nothing, same disposition the old regex reader gave any
    line it didn't recognize as a state write. (`Kernel.pbMessage(_INTL(...))`,
    the old fixture here, is NOT actually modelled by the interpreter --
    neither `pbMessage` nor `_INTL` is a registered builtin, so it refuses
    `ruby_unknown_call:_INTL` for real; see
    `test_unmodelled_message_call_refuses_by_name` below, a real gap the
    old regex reader silently missed.)"""
    page = _page([_cmd(355, ["Kernel.pbSave"])])
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={})
    row = rows[page_row_id(999, 1, 0)]
    assert row.writes == ()
    assert row.refusals == ()


def test_unmodelled_message_call_refuses_by_name() -> None:
    page = _page([_cmd(355, ["Kernel.pbMessage(_INTL(\"hi\"))"])])
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={})
    row = rows[page_row_id(999, 1, 0)]
    assert row.writes == ()
    assert row.refusals[0].code == "ruby_unknown_call:_INTL"


def test_inline_choice_text_produces_a_variable_write() -> None:
    """A bare `\\ch[...]` text choice used to produce NOTHING under the old
    regex readers (`story_state` never modelled it). The interpreter path
    now resolves it to a real variable write over the choice's domain."""
    page = _page([_cmd(101, ["Pick one\\ch[5,0,Yes,No]"])])
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={})
    row = rows[page_row_id(999, 1, 0)]
    assert row.refusals == ()
    assert len(row.writes) == 1
    w = row.writes[0]
    assert w.key == Variable(5)
    assert w.values == frozenset({0, 1})


# --- common event inlining --------------------------------------------


def test_common_event_inline_unconditional_write() -> None:
    ce = _common_event(1, [_cmd(121, [6, 6, 0])])
    page = _page([_cmd(117, [1])])
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[ce], switch_labels={})
    row = rows[page_row_id(999, 1, 0)]
    assert row.writes == (Assign(Switch(6), frozenset({True}), False, "code 121 @list[0]", 0),)


def test_common_event_inline_conditional_write() -> None:
    ce = _common_event(2, [
        _cmd(111, [0, 8, 0], indent=0),
        _cmd(121, [6, 6, 0], indent=1),
        _cmd(412, [], indent=0),
    ])
    page = _page([_cmd(117, [2])])
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[ce], switch_labels={})
    row = rows[page_row_id(999, 1, 0)]
    assert len(row.writes) == 1
    assert row.writes[0].key == Switch(6)
    assert row.writes[0].conditional is True


def test_common_event_cycle_refuses() -> None:
    # ids kept away from reference/strip_list.json's real CE 4/5/6
    # (GTS/VT/LOBBY) -- those are now honestly honored as no-ops
    # (REDERIVATION_PLAN.md §16.3 C8 stage 4), and this fixture wants a
    # genuine 117->117 cycle, not a strip-listed no-op.
    ce_a = _common_event(30, [_cmd(117, [31])])
    ce_b = _common_event(31, [_cmd(117, [30])])
    page = _page([_cmd(117, [30])])
    rows = extract_map(
        999, _map([_event(1, [page])]), common_events=[ce_a, ce_b], switch_labels={})
    row = rows[page_row_id(999, 1, 0)]
    assert any(r.code == "common_event_cycle" for r in row.refusals)


def test_missing_common_event_refuses() -> None:
    page = _page([_cmd(117, [999])])
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={})
    row = rows[page_row_id(999, 1, 0)]
    assert row.refusals[0].code == "missing_common_event"


# --- forced trigger / row-id parity with the generator ---------------------


def test_autorun_and_parallel_are_forced() -> None:
    autorun_page = _page([_cmd(101, ["x"])], trigger=3)
    parallel_page = _page([_cmd(101, ["y"])], trigger=4)
    action_page = _page([_cmd(101, ["z"])], trigger=0)
    rows = extract_map(
        999, _map([_event(1, [autorun_page, parallel_page, action_page])]),
        common_events=[], switch_labels={},
    )
    assert rows[page_row_id(999, 1, 0)].forced is True
    assert rows[page_row_id(999, 1, 1)].forced is True
    assert rows[page_row_id(999, 1, 2)].forced is False


def test_event_page_row_ids_cover_every_page() -> None:
    p0 = _page([_cmd(101, ["a"])])
    p1 = _page([_cmd(101, ["b"])])
    rows = extract_map(999, _map([_event(1, [p0, p1])]), common_events=[], switch_labels={})
    expected = (page_row_id(999, 1, 0), page_row_id(999, 1, 1))
    assert rows[page_row_id(999, 1, 0)].event_page_row_ids == expected
    assert rows[page_row_id(999, 1, 1)].event_page_row_ids == expected


def test_row_ids_match_the_generator_one_to_one() -> None:
    """Every row `extract_map` produces has exactly the id the generator's
    own `iter_page_scopes`-driven manifest would produce, and vice versa --
    both walk the same source function."""
    page = _page([
        _cmd(111, [0, 1, 0], indent=0),
        _cmd(101, ["then"], indent=1),
        _cmd(411, [], indent=0),
        _cmd(101, ["else"], indent=1),
        _cmd(412, [], indent=0),
    ])
    events = [_event(1, [page])]
    map_data = _map(events)
    extracted = extract_map(999, map_data, common_events=[], switch_labels={})

    from rpg2gba.chapter_manifest.generator import iter_page_scopes
    scopes = iter_page_scopes(999, events[0], 0, page)
    expected_ids = {s.row_id for s in scopes}
    assert set(extracted.keys()) == expected_ids


# --- real-data test ------------------------------------------------------


# --- triggered common events (pseudo-rows, REDERIVATION_PLAN.md §16.3 C2
# ruling (e)) ---------------------------------------------------------------


def _ce(ce_id: int, trigger: int, switch_id: int, list_: list[dict]) -> dict:
    return {"id": ce_id, "name": f"CE{ce_id}", "trigger": trigger, "switch_id": switch_id,
            "list": list_}


def test_common_event_51_day_night_shape() -> None:
    """The exact shape of common event 51 ("Only Day people"), verbatim from
    REDERIVATION_PLAN.md §16.3 C2 ruling (e)."""
    ce51 = _ce(51, trigger=2, switch_id=51, list_=[
        _cmd(111, [12, "Time.now.hour<6||Time.now.hour>=20"], indent=0),
        _cmd(121, [105, 105, 1], indent=1),
        _cmd(121, [106, 106, 0], indent=1),
        _cmd(411, [], indent=0),
        _cmd(121, [105, 105, 0], indent=1),
        _cmd(121, [106, 106, 1], indent=1),
        _cmd(412, [], indent=0),
        _cmd(106, [200], indent=0),
    ])
    rows = extract_triggered_common_events([ce51], switch_labels={})

    trunk = rows["common/ce051"]
    assert trunk.page_tests == (Test(Switch(51), "==", True),)
    assert trunk.forced is True
    assert trunk.parent_row_id is None
    assert trunk.event_page_row_ids == ("common/ce051",)

    then_arm = rows["common/ce051/b0"]
    else_arm = rows["common/ce051/b1"]
    assert then_arm.parent_row_id == "common/ce051"
    assert else_arm.parent_row_id == "common/ce051"
    assert then_arm.arm_guard.outcome.kind == "input"
    assert then_arm.arm_guard.outcome.detail == "clock"

    then_values = {w.key: w.values for w in then_arm.writes}
    else_values = {w.key: w.values for w in else_arm.writes}
    assert then_values[Switch(105)] == frozenset({False})
    assert then_values[Switch(106)] == frozenset({True})
    assert else_values[Switch(105)] == frozenset({True})
    assert else_values[Switch(106)] == frozenset({False})


def test_only_autorun_and_parallel_common_events_are_extracted() -> None:
    ce_none = _ce(1, trigger=0, switch_id=1, list_=[_cmd(101, ["x"])])
    ce_action = _ce(2, trigger=None, switch_id=2, list_=[_cmd(101, ["x"])])
    ce_autorun = _ce(3, trigger=1, switch_id=3, list_=[_cmd(101, ["x"])])
    ce_parallel = _ce(4, trigger=2, switch_id=4, list_=[_cmd(101, ["x"])])
    ce_no_switch = _ce(5, trigger=1, switch_id=0, list_=[_cmd(101, ["x"])])

    rows = extract_triggered_common_events(
        [ce_none, ce_action, ce_autorun, ce_parallel, ce_no_switch], switch_labels={})

    row_ces = {rid.split("/")[1] for rid in rows}
    assert row_ces == {"ce003", "ce004"}


def test_self_switch_write_in_common_event_is_refused() -> None:
    ce = _ce(80, trigger=1, switch_id=90, list_=[_cmd(123, ["A", 0], indent=0)])
    rows = extract_triggered_common_events([ce], switch_labels={})
    trunk = rows["common/ce080"]
    assert trunk.writes == ()
    assert any(r.code == "invalid_self_switch_write_in_common_event" for r in trunk.refusals)


@pytest.mark.skipif(not (OUT_DIR / "maps").is_dir(), reason="no converted corpus on disk")
def test_extract_map_covers_every_ch01_ch05_manifest_row() -> None:
    chapters = json.loads(CHAPTERS_PATH.read_text(encoding="utf-8"))
    chapter_ids = ["CH01", "CH02", "CH03", "CH04", "CH05"]
    switch_labels, _var_labels = load_label_tables(
        Path("reference/uranium_switches.json"), Path("reference/uranium_variables.json"))
    common_events = json.loads((OUT_DIR / "common_events.json").read_text(encoding="utf-8"))

    refusal_tally: Counter[str] = Counter()
    total_rows = 0
    for chapter_id in chapter_ids:
        chapter = next(c for c in chapters["chapters"] if c["id"] == chapter_id)
        manifest_rows = generate_chapter_manifest(
            chapter_id, build_dir=OUT_DIR, chapters_path=CHAPTERS_PATH)
        manifest_row_ids = {r.row_id for r in manifest_rows if r.kind in ("page", "branch")}

        extracted_ids: set[str] = set()
        for map_id in chapter["maps"]:
            map_path = OUT_DIR / "maps" / f"Map{map_id:03d}.json"
            map_data = json.loads(map_path.read_text(encoding="utf-8"))
            rows = extract_map(
                map_id, map_data, common_events=common_events, switch_labels=switch_labels)
            extracted_ids.update(rows.keys())
            for row in rows.values():
                for refusal in row.refusals + row.page_refusals:
                    refusal_tally[refusal.code] += 1
            total_rows += len(rows)

        # `iter_page_scopes` includes diagonal-stair-absorbed events on the
        # manifest side (they get NO page row at all, per generator.py) --
        # extract_map, working straight off map_data, has no such absorption
        # concept, so it may produce a few EXTRA row ids the manifest omits
        # for absorbed stair events. What must never happen is the reverse:
        # every manifest page/branch row must have exactly one RowState.
        missing = manifest_row_ids - extracted_ids
        assert not missing, f"{chapter_id}: manifest rows with no RowState: {sorted(missing)[:10]}"

    assert total_rows > 0
    print("refusal tally:", dict(refusal_tally))
