"""Tests for `rpg2gba.story_state.graphics_vars` (operator ruling 2026-09-25):
a variable is graphics-only when every read of it anywhere is a page condition
of an empty page."""
from __future__ import annotations

from rpg2gba.ruby_subset.search import SearchResult
from rpg2gba.story_state.graphics_vars import scan_graphics_only_variables
from rpg2gba.story_state.scope_search import writes_from_result
from rpg2gba.story_state.state import Switch, Variable

_END = {"code": 0, "indent": 0, "parameters": []}


def _page(var_id=None, commands=()):
    cond = {"variable_valid": var_id is not None, "variable_id": var_id or 1}
    return {"condition": cond, "list": [*commands, _END]}


def _cmd(code, params):
    return {"code": code, "indent": 0, "parameters": params}


def _map(*pages):
    return {"events": [{"id": 1, "pages": list(pages)}]}


def test_only_empty_page_conditions_make_a_variable_graphics_only():
    maps = [_map(
        _page(43), _page(7), _page(9), _page(10), _page(11), _page(12),
        _page(None, [
            _cmd(355, ["$game_variables[43]=$Trainer.party.length"]),  # a write
            _cmd(111, [1, 7, 0, 1, 0]),                                # reads 7
            _cmd(355, ["pbMessage(pbGet(9).to_s)"]),                   # reads 9
            _cmd(122, [10, 10, 1, 0, 1]),                              # += reads 10
            _cmd(101, ["You have \\v[11] badges"]),                  # reads 11
        ]),
        _page(13, [_cmd(101, ["not empty"])]),                         # reads 13
    )]
    ruby = ["x = $game_variables[12] + 1"]                             # reads 12
    assert scan_graphics_only_variables(maps, [], ruby) == frozenset({43})


def test_a_common_event_read_disqualifies_a_variable():
    maps = [_map(_page(43))]
    ce = {"id": 1, "list": [_cmd(111, [1, 2, 1, 43, 0]), _END]}  # var 2 vs var 43
    assert scan_graphics_only_variables(maps, [ce]) == frozenset()


def test_a_havoc_key_gets_no_assign_even_when_the_row_also_wrote_it():
    result = SearchResult(
        runs=1, values={Variable(43): frozenset({0}), Switch(5): frozenset({False})},
        always_written=frozenset({Variable(43), Switch(5)}),
        write_index={Variable(43): 11, Switch(5): 17}, witnesses={}, effects=(),
        reads=frozenset(), inputs=False, refusal=None, havoc=frozenset({Variable(43)}))
    writes, havoc = writes_from_result(result, conditional=False, source_prefix="t")
    assert [w.key for w in writes] == [Switch(5)]
    assert havoc == (Variable(43),)
