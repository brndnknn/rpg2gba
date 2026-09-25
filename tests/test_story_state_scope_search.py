"""Tests for `rpg2gba.story_state.scope_search` (REDERIVATION_PLAN.md §16.3
C8 stage 4, "half" owned by `story_state/extract.py`).

Covers the three functions `story_state/extract.py` and the lead's resolver
(`story_state/model.py`) both depend on: `scope_needs_interpreter` (does a
row's flattened command list need `ruby_subset.search` at all), `writes_
from_result` (turn a refusal-free `SearchResult` into `state.Assign`
writes, including the non-scalar-value and conditional/`always_written`
rules), and `run_scope` (re-running a frozen `ComputedScope` against a
different `read_domain`, the resolver's own fixpoint primitive).
"""
from __future__ import annotations

from rpg2gba.ruby_subset.search import Choice, SearchResult, search_scope
from rpg2gba.story_state.scope_search import (
    ComputedScope,
    run_scope,
    scope_needs_interpreter,
    self_contained_counters,
    stripped_ce_ids_for,
    witness_citations,
    writes_from_result,
)
from rpg2gba.story_state.state import Refusal, Switch, Variable

from tests.test_chapter_manifest_generator import _cmd


def _empty_result(**overrides: object) -> SearchResult:
    base = dict(
        runs=1, values={}, always_written=frozenset(), write_index={},
        witnesses={}, effects=(), reads=frozenset(), inputs=False, refusal=None,
    )
    base.update(overrides)
    return SearchResult(**base)  # type: ignore[arg-type]


# --- scope_needs_interpreter ------------------------------------------


def test_plain_structural_commands_do_not_need_interpreter() -> None:
    commands = [_cmd(121, [6, 6, 0]), _cmd(117, [1]), _cmd(123, ["A", 0])]
    assert scope_needs_interpreter(commands) is False


def test_script_command_needs_interpreter() -> None:
    commands = [_cmd(121, [6, 6, 0]), _cmd(355, ["pbSet(1, 2)"])]
    assert scope_needs_interpreter(commands) is True


def test_plain_text_without_inline_choice_does_not_need_interpreter() -> None:
    commands = [_cmd(101, ["Hello there"]), _cmd(401, ["how are you"])]
    assert scope_needs_interpreter(commands) is False


def test_inline_choice_text_needs_interpreter() -> None:
    commands = [_cmd(101, ["Pick"]), _cmd(401, ["\\ch[5,0,Yes,No]"])]
    assert scope_needs_interpreter(commands) is True


# --- writes_from_result -------------------------------------------------


def test_writes_from_result_emits_one_assign_per_key() -> None:
    result = _empty_result(
        runs=3,
        values={Switch(6): frozenset({True}), Variable(2): frozenset({1, 2})},
        always_written=frozenset({Switch(6), Variable(2)}),
        write_index={Switch(6): 4, Variable(2): 7},
    )
    writes, havoc = writes_from_result(result, conditional=False, source_prefix="row/x")
    assert havoc == ()
    by_key = {w.key: w for w in writes}
    assert by_key[Switch(6)].values == frozenset({True})
    assert by_key[Switch(6)].conditional is False
    assert by_key[Switch(6)].list_index == 4
    assert by_key[Switch(6)].source == "row/x: search over 3 runs"
    assert by_key[Variable(2)].values == frozenset({1, 2})
    assert by_key[Variable(2)].list_index == 7


def test_writes_from_result_key_not_always_written_is_conditional() -> None:
    result = _empty_result(
        values={Switch(6): frozenset({True})},
        always_written=frozenset(),  # only written on SOME runs
        write_index={Switch(6): 0},
    )
    writes, havoc = writes_from_result(result, conditional=False, source_prefix="row/x")
    assert havoc == ()
    assert writes[0].conditional is True


def test_writes_from_result_caller_conditional_forces_conditional_even_if_always_written() -> None:
    result = _empty_result(
        values={Switch(6): frozenset({True})},
        always_written=frozenset({Switch(6)}),
        write_index={Switch(6): 0},
    )
    writes, havoc = writes_from_result(result, conditional=True, source_prefix="row/x")
    assert writes[0].conditional is True


def test_writes_from_result_nonscalar_value_havocs_only_that_key() -> None:
    """C9 ruling 13: a non-scalar value (e.g. a species name stored in a
    variable) makes that key "could be anything"; the row's other writes
    stand and nothing is refused."""
    class _Opaque:
        def __repr__(self) -> str:
            return "<opaque>"

    result = _empty_result(
        values={
            Switch(6): frozenset({True}),
            Variable(9): frozenset({_Opaque()}),
            Variable(3): frozenset({"Orchynx"}),
        },
        always_written=frozenset({Switch(6), Variable(9), Variable(3)}),
        write_index={Switch(6): 0, Variable(9): 1, Variable(3): 2},
    )
    writes, havoc = writes_from_result(result, conditional=False, source_prefix="row/x")
    assert {w.key for w in writes} == {Switch(6)}
    assert set(havoc) == {Variable(9), Variable(3)}


def test_writes_from_result_bool_and_int_are_both_scalar() -> None:
    # bool is a subclass of int in Python -- both must pass, not just one.
    result = _empty_result(
        values={Switch(1): frozenset({True}), Variable(1): frozenset({0})},
        always_written=frozenset({Switch(1), Variable(1)}),
        write_index={Switch(1): 0, Variable(1): 0},
    )
    writes, havoc = writes_from_result(result, conditional=False, source_prefix="row/x")
    assert havoc == ()
    assert {w.key for w in writes} == {Switch(1), Variable(1)}


# --- witness_citations ---------------------------------------------------


def test_witness_citations_are_sorted_and_json_serialisable_shape() -> None:
    result = _empty_result(
        witnesses={
            (Variable(2), 1): (Choice("read Variable(1)", 5), Choice("\\ch var 2 @list[0]", 1)),
            (Switch(6), True): (Choice("code 121 @list[3]", True),),
        },
    )
    citations = witness_citations(result)
    assert citations == tuple(sorted(citations))
    for key_repr, value_repr, labels in citations:
        assert isinstance(key_repr, str)
        assert isinstance(value_repr, str)
        assert all(isinstance(l, str) for l in labels)
    keys = {c[0] for c in citations}
    assert "Variable(id=2)" in keys
    assert "Switch(id=6)" in keys


# --- run_scope / ComputedScope round-trip --------------------------------


def _computed_scope(commands: list[dict], *, conditional: bool = False) -> ComputedScope:
    index_of = {id(c): i for i, c in enumerate(commands)}
    return ComputedScope(
        row_id="page/999/1/0", map_id=999, event_id=1, commands=commands,
        index_of=index_of, common_events_by_id={}, stripped_ce_ids=frozenset(),
        conditional=conditional, first_unknown_read="Variable(id=151)",
    )


def test_run_scope_round_trips_against_two_different_read_domains() -> None:
    # A 122 op=0 (plain assign) constant-copies Variable(151) into
    # Variable(6) -- Variable(6)'s written value set is exactly whatever
    # `read_domain` says Variable(151) can be, so re-running against a
    # wider domain grows the result, same as a real saturation iteration.
    commands = [_cmd(122, [6, 6, 0, 1, 151])]
    scope = _computed_scope(commands)

    narrow = run_scope(scope, read_domain=lambda key: frozenset({1, 2}) if key == Variable(151) else None)
    assert narrow.refusal is None
    assert narrow.values[Variable(6)] == frozenset({1, 2})

    wide = run_scope(scope, read_domain=lambda key: frozenset({1, 2, 3}) if key == Variable(151) else None)
    assert wide.refusal is None
    assert wide.values[Variable(6)] == frozenset({1, 2, 3})

    # Confirms this is genuinely the same wrapper `search_scope` itself
    # would produce -- not a parallel/duplicated code path.
    direct = search_scope(
        commands, map_id=999, event_id=1, common_events_by_id={},
        stripped_ce_ids=frozenset(),
        read_domain=lambda key: frozenset({1, 2}) if key == Variable(151) else None,
        index_of=scope.index_of,
    )
    assert direct.values == narrow.values


def test_run_scope_still_refuses_when_the_new_domain_is_also_none() -> None:
    commands = [_cmd(122, [6, 6, 0, 1, 151])]
    scope = _computed_scope(commands)
    result = run_scope(scope, read_domain=lambda key: None)
    assert result.refusal is not None
    assert result.refusal.code == "search_unknown_read"


# --- stripped_ce_ids_for ---------------------------------------------------


def test_stripped_ce_ids_for_matches_load_stripped_ce_ids_for_real_reference_dir() -> None:
    from pathlib import Path

    from rpg2gba.ruby_subset.search import load_stripped_ce_ids

    reference_dir = Path(__file__).resolve().parents[1] / "reference"
    if not (reference_dir / "strip_list.json").exists():
        return
    assert stripped_ce_ids_for(reference_dir) == load_stripped_ce_ids(reference_dir)


# --- self_contained_counters (C9 ruling 13) -----------------------------


def test_counter_updated_in_place_and_read_nowhere_else_is_self_contained() -> None:
    commands = [_cmd(121, [6, 6, 0]), _cmd(122, [101, 101, 1, 0, 1])]
    assert self_contained_counters(commands, {}) == frozenset({Variable(101)})


def test_plain_set_is_not_a_counter() -> None:
    commands = [_cmd(122, [101, 101, 0, 0, 4])]
    assert self_contained_counters(commands, {}) == frozenset()


def test_counter_read_by_a_branch_is_not_self_contained() -> None:
    commands = [_cmd(122, [101, 101, 1, 0, 1]), _cmd(111, [1, 101, 0, 3, 1])]
    assert self_contained_counters(commands, {}) == frozenset()


def test_counter_used_as_another_variables_operand_is_not_self_contained() -> None:
    commands = [_cmd(122, [101, 101, 1, 0, 1]), _cmd(122, [5, 5, 0, 1, 101])]
    assert self_contained_counters(commands, {}) == frozenset()


def test_counter_mentioned_in_a_script_is_not_self_contained() -> None:
    commands = [_cmd(122, [101, 101, 1, 0, 1]), _cmd(355, ["x = pbGet(101)"])]
    assert self_contained_counters(commands, {}) == frozenset()


def test_counter_read_inside_a_called_common_event_is_not_self_contained() -> None:
    ces = {7: {"list": [_cmd(111, [1, 101, 0, 2, 1])]}}
    commands = [_cmd(122, [101, 101, 1, 0, 1]), _cmd(117, [7])]
    assert self_contained_counters(commands, ces) == frozenset()


def test_unknown_common_event_makes_nothing_self_contained() -> None:
    commands = [_cmd(122, [101, 101, 1, 0, 1]), _cmd(117, [99])]
    assert self_contained_counters(commands, {}) == frozenset()


def test_variable_designated_transfer_counts_as_a_read() -> None:
    commands = [_cmd(122, [101, 101, 1, 0, 1]), _cmd(201, [1, 101, 102, 103, 0])]
    assert self_contained_counters(commands, {}) == frozenset()
