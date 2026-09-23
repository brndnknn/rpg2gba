"""Tests for `rpg2gba.ruby_subset` (REDERIVATION_PLAN.md C8 stage 1).

The real-corpus test at the bottom is the important gate: every 355/655
script block and every 111 type-12 condition script on every event page of
every CH01-CH05 map (plus common events those maps call via 117) must parse
without a `RubyParseError`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.ruby_subset import ast, parse_expression, parse_program, RubyParseError
from rpg2gba.ruby_subset.parser import script_block_source

REPO = Path(__file__).resolve().parents[1]
MAPS_DIR = REPO / "output" / "uranium-build" / "maps"
COMMON_EVENTS_PATH = REPO / "output" / "uranium-build" / "common_events.json"
CHAPTERS_PATH = REPO / "reference" / "chapters.json"


# --- AST shape tests for the known-hard corpus shapes ---------------------


def test_add_pokemon_postfix_if_scoped_const():
    prog = parse_program(
        "pbAddPokemon(PBSpecies::ORCHYNX,5) if $game_variables[151]==1"
    )
    assert len(prog.statements) == 1
    stmt = prog.statements[0]
    assert isinstance(stmt, ast.If)
    assert stmt.postfix is True
    assert stmt.elifs == ()
    assert stmt.else_body is None

    cond = stmt.cond
    assert isinstance(cond, ast.BinOp) and cond.op == "=="
    assert isinstance(cond.left, ast.Index)
    assert isinstance(cond.left.receiver, ast.GlobalVar)
    assert cond.left.receiver.name == "$game_variables"
    assert cond.left.args == (ast.Int(span=cond.left.args[0].span, value=151),)
    assert isinstance(cond.right, ast.Int) and cond.right.value == 1

    assert len(stmt.then_body) == 1
    call = stmt.then_body[0]
    assert isinstance(call, ast.Call)
    assert call.receiver is None
    assert call.name == "pbAddPokemon"
    assert len(call.args) == 2
    species_arg = call.args[0]
    assert isinstance(species_arg, ast.ScopedConst)
    assert species_arg.name == "ORCHYNX"
    assert isinstance(species_arg.scope, ast.Const)
    assert species_arg.scope.name == "PBSpecies"
    assert isinstance(call.args[1], ast.Int) and call.args[1].value == 5


def test_game_switch_index_assign_postfix_if():
    prog = parse_program('$game_switches[61] = true if $game_variables[151]==1')
    stmt = prog.statements[0]
    assert isinstance(stmt, ast.If) and stmt.postfix
    assign = stmt.then_body[0]
    assert isinstance(assign, ast.Assign)
    assert isinstance(assign.target, ast.Index)
    assert isinstance(assign.target.receiver, ast.GlobalVar)
    assert assign.target.receiver.name == "$game_switches"
    assert assign.target.args[0].value == 61
    assert isinstance(assign.value, ast.Bool) and assign.value.value is True


def test_index_op_assign():
    prog = parse_program("pbGet(151)[pbGet(2)]+=1")
    stmt = prog.statements[0]
    assert isinstance(stmt, ast.OpAssign)
    assert stmt.op == "+"
    assert isinstance(stmt.target, ast.Index)
    receiver = stmt.target.receiver
    assert isinstance(receiver, ast.Call) and receiver.name == "pbGet"
    assert receiver.args[0].value == 151
    inner_index_arg = stmt.target.args[0]
    assert isinstance(inner_index_arg, ast.Call) and inner_index_arg.name == "pbGet"
    assert inner_index_arg.args[0].value == 2
    assert isinstance(stmt.value, ast.Int) and stmt.value.value == 1


def test_index_assign_array_literal():
    prog = parse_program("$game_variables[151]=[0,0,0]")
    stmt = prog.statements[0]
    assert isinstance(stmt, ast.Assign)
    assert isinstance(stmt.target, ast.Index)
    assert isinstance(stmt.value, ast.ArrayLit)
    assert [e.value for e in stmt.value.elements] == [0, 0, 0]


def test_argmax_remap_if_elsif_program():
    text = (
        "x=pbGet(151).index(pbGet(151).max)\n"
        "if x==1\n"
        "x=0\n"
        "elsif x==0\n"
        "x=1\n"
        "end\n"
        "$game_variables[151]=x\n"
        "pbStarterSelector(pbGet(151))"
    )
    prog = parse_program(text)
    assert len(prog.statements) == 4

    assign0 = prog.statements[0]
    assert isinstance(assign0, ast.Assign)
    assert isinstance(assign0.target, ast.Local) and assign0.target.name == "x"
    index_call = assign0.value
    assert isinstance(index_call, ast.Call) and index_call.name == "index"
    assert isinstance(index_call.receiver, ast.Call) and index_call.receiver.name == "pbGet"
    max_call = index_call.args[0]
    assert isinstance(max_call, ast.Call) and max_call.name == "max"
    assert isinstance(max_call.receiver, ast.Call) and max_call.receiver.name == "pbGet"

    if_stmt = prog.statements[1]
    assert isinstance(if_stmt, ast.If) and not if_stmt.postfix
    assert isinstance(if_stmt.cond, ast.BinOp) and if_stmt.cond.op == "=="
    assert isinstance(if_stmt.cond.left, ast.Local) and if_stmt.cond.left.name == "x"
    assert len(if_stmt.then_body) == 1
    then_assign = if_stmt.then_body[0]
    assert isinstance(then_assign, ast.Assign) and then_assign.value.value == 0
    assert len(if_stmt.elifs) == 1
    elif_cond, elif_body = if_stmt.elifs[0]
    assert isinstance(elif_cond, ast.BinOp) and elif_cond.right.value == 0
    assert len(elif_body) == 1 and elif_body[0].value.value == 1
    assert if_stmt.else_body is None

    assign_var = prog.statements[2]
    assert isinstance(assign_var, ast.Assign)
    assert isinstance(assign_var.target, ast.Index)
    assert isinstance(assign_var.value, ast.Local) and assign_var.value.name == "x"

    final_call = prog.statements[3]
    assert isinstance(final_call, ast.Call) and final_call.name == "pbStarterSelector"


def test_decrement_local_postfix_if_reset():
    text = 'x=pbGet(151)\nx-=2\nx=2 if x==-1\npbStarterSelector(x,true)'
    prog = parse_program(text)
    assert len(prog.statements) == 4
    assert isinstance(prog.statements[0], ast.Assign)
    op_assign = prog.statements[1]
    assert isinstance(op_assign, ast.OpAssign) and op_assign.op == "-"
    assert isinstance(op_assign.target, ast.Local) and op_assign.target.name == "x"

    postfix_if = prog.statements[2]
    assert isinstance(postfix_if, ast.If) and postfix_if.postfix
    assert isinstance(postfix_if.cond, ast.BinOp) and postfix_if.cond.op == "=="
    neg_one = postfix_if.cond.right
    assert isinstance(neg_one, ast.UnaryOp) and neg_one.op == "-"
    assert neg_one.operand.value == 1

    call = prog.statements[3]
    assert isinstance(call, ast.Call) and call.name == "pbStarterSelector"
    assert isinstance(call.args[0], ast.Local) and call.args[0].name == "x"
    assert isinstance(call.args[1], ast.Bool) and call.args[1].value is True


def test_ternary_call_arg():
    prog = parse_program("pbSet(1, result == BR_WIN ? 0 : 1)")
    call = prog.statements[0]
    assert isinstance(call, ast.Call) and call.name == "pbSet"
    ternary = call.args[1]
    assert isinstance(ternary, ast.Ternary)
    assert isinstance(ternary.cond, ast.BinOp) and ternary.cond.op == "=="
    assert isinstance(ternary.cond.right, ast.Const) and ternary.cond.right.name == "BR_WIN"
    assert ternary.then.value == 0
    assert ternary.else_.value == 1


def test_for_loop_range_self_switch():
    prog = parse_program('for i in 14..18\n   pbSetSelfSwitch(i,"A",true)\nend')
    stmt = prog.statements[0]
    assert isinstance(stmt, ast.For)
    assert stmt.var == "i"
    assert isinstance(stmt.iterable, ast.RangeLit)
    assert stmt.iterable.lo.value == 14
    assert stmt.iterable.hi.value == 18
    assert stmt.iterable.exclusive is False
    assert len(stmt.body) == 1
    call = stmt.body[0]
    assert isinstance(call, ast.Call) and call.name == "pbSetSelfSwitch"
    assert isinstance(call.args[0], ast.Local) and call.args[0].name == "i"


def test_for_loop_over_party_attribute_call():
    prog = parse_program('for i in $Trainer.party\n  i.nuzlocke_heal\nend')
    stmt = prog.statements[0]
    assert isinstance(stmt, ast.For)
    assert stmt.var == "i"
    iterable = stmt.iterable
    assert isinstance(iterable, ast.Call) and iterable.name == "party"
    assert isinstance(iterable.receiver, ast.GlobalVar)
    assert iterable.receiver.name == "$Trainer"
    body_call = stmt.body[0]
    assert isinstance(body_call, ast.Call) and body_call.name == "nuzlocke_heal"
    assert isinstance(body_call.receiver, ast.Local) and body_call.receiver.name == "i"
    assert body_call.args == ()


def test_indexed_attribute_assignment():
    stmt = parse_program('$Trainer.party[i].nuzlocke_heal=true').statements[0]
    assert isinstance(stmt, ast.Assign)
    target = stmt.target
    assert isinstance(target, ast.Call) and target.name == "nuzlocke_heal"
    assert target.args == ()
    index_recv = target.receiver
    assert isinstance(index_recv, ast.Index)
    party_call = index_recv.receiver
    assert isinstance(party_call, ast.Call) and party_call.name == "party"
    assert isinstance(stmt.value, ast.Bool) and stmt.value.value is True


def test_runningshoes_attribute_assignment():
    stmt = parse_program('$PokemonGlobal.runningShoes=true').statements[0]
    assert isinstance(stmt, ast.Assign)
    assert isinstance(stmt.target, ast.Call)
    assert stmt.target.name == "runningShoes"
    assert isinstance(stmt.target.receiver, ast.GlobalVar)
    assert stmt.target.receiver.name == "$PokemonGlobal"


def test_system_call():
    prog = parse_program('system("start http://example.com")')
    call = prog.statements[0]
    assert isinstance(call, ast.Call)
    assert call.receiver is None
    assert call.name == "system"
    assert len(call.args) == 1
    assert isinstance(call.args[0], ast.Str)
    assert call.args[0].value == "start http://example.com"


def test_profrewards_nested_index():
    prog = parse_program("pbSet(1,PROFREWARDS[pbGet(22)+1][0])")
    call = prog.statements[0]
    assert isinstance(call, ast.Call) and call.name == "pbSet"
    outer_index = call.args[1]
    assert isinstance(outer_index, ast.Index)
    assert outer_index.args[0].value == 0
    inner_index = outer_index.receiver
    assert isinstance(inner_index, ast.Index)
    assert isinstance(inner_index.receiver, ast.Const) and inner_index.receiver.name == "PROFREWARDS"
    add = inner_index.args[0]
    assert isinstance(add, ast.BinOp) and add.op == "+"
    assert isinstance(add.left, ast.Call) and add.left.name == "pbGet"
    assert add.right.value == 1


def test_party_length_assignment():
    stmt = parse_program("$game_variables[43]=$Trainer.party.length").statements[0]
    assert isinstance(stmt, ast.Assign)
    length_call = stmt.value
    assert isinstance(length_call, ast.Call) and length_call.name == "length"
    party_call = length_call.receiver
    assert isinstance(party_call, ast.Call) and party_call.name == "party"
    assert isinstance(party_call.receiver, ast.GlobalVar)


def test_pokemon_bag_delete_item_scoped_const():
    prog = parse_program("$PokemonBag.pbDeleteItem(PBItems::BIKEWHEEL)")
    call = prog.statements[0]
    assert isinstance(call, ast.Call) and call.name == "pbDeleteItem"
    assert isinstance(call.receiver, ast.GlobalVar) and call.receiver.name == "$PokemonBag"
    arg = call.args[0]
    assert isinstance(arg, ast.ScopedConst) and arg.name == "BIKEWHEEL"
    assert arg.scope.name == "PBItems"


def test_trainer_battle_condition_expression():
    text = (
        'pbTrainerBattle(PBTrainers::RIVAL,"Theo",_I("..."),false,'
        'pbGet(151)+18,true,7)'
    )
    expr = parse_expression(text)
    assert isinstance(expr, ast.Call) and expr.name == "pbTrainerBattle"
    assert len(expr.args) == 7
    assert isinstance(expr.args[0], ast.ScopedConst) and expr.args[0].name == "RIVAL"
    assert isinstance(expr.args[1], ast.Str) and expr.args[1].value == "Theo"
    i_call = expr.args[2]
    assert isinstance(i_call, ast.Call) and i_call.name == "_I"
    assert isinstance(expr.args[3], ast.Bool) and expr.args[3].value is False
    plus = expr.args[4]
    assert isinstance(plus, ast.BinOp) and plus.op == "+"
    assert plus.left.name == "pbGet"
    assert plus.right.value == 18
    assert isinstance(expr.args[5], ast.Bool) and expr.args[5].value is True
    assert isinstance(expr.args[6], ast.Int) and expr.args[6].value == 7


# --- error handling / determinism -----------------------------------------


def test_malformed_input_raises():
    with pytest.raises(RubyParseError):
        parse_program("x = = =")
    with pytest.raises(RubyParseError):
        parse_program("if x==1\n x=2\n")  # missing `end`
    with pytest.raises(RubyParseError):
        parse_expression("1 +")


def test_constant_assignment_refuses():
    with pytest.raises(RubyParseError) as exc:
        parse_program("PROFREWARDS=[0]")
    assert exc.value.reason == "unsupported_syntax:constant_assignment"


def test_parsing_twice_is_deterministic():
    samples = [
        "pbAddPokemon(PBSpecies::ORCHYNX,5) if $game_variables[151]==1",
        "x=pbGet(151)\nx-=2\nx=2 if x==-1\npbStarterSelector(x,true)",
        "pbSet(1, result == BR_WIN ? 0 : 1)",
    ]
    for s in samples:
        assert parse_program(s) == parse_program(s)


def test_script_block_source_joins_355_and_655_only():
    commands = [
        {"code": 355, "parameters": ["pbPokemonMart(["]},
        {"code": 655, "parameters": ["PBItems::POKeBALL,"]},
        {"code": 655, "parameters": ["PBItems::POTION])"]},
        {"code": 122, "parameters": [1, 1, 0, 0, 1]},  # not part of the block
    ]
    text, next_idx = script_block_source(commands, 0)
    assert text == "pbPokemonMart([\nPBItems::POKeBALL,\nPBItems::POTION])"
    assert next_idx == 3
    parse_program(text)  # sanity: reconstructed block parses


# --- real-corpus coverage (CH01-CH05, skipped if the staged build isn't
# present) ------------------------------------------------------------------

pytestmark_corpus = pytest.mark.skipif(
    not MAPS_DIR.is_dir(), reason="output/uranium-build/maps not staged",
)


def _load_common_events_by_id() -> dict[int, dict]:
    if not COMMON_EVENTS_PATH.exists():
        return {}
    data = json.loads(COMMON_EVENTS_PATH.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {ce["id"]: ce for ce in data if ce}
    return {int(k): v for k, v in data.items()}


def _ch01_ch05_map_ids() -> list[int]:
    chapters = json.loads(CHAPTERS_PATH.read_text(encoding="utf-8"))
    ids: list[int] = []
    for c in chapters["chapters"]:
        if c.get("id") in ("CH01", "CH02", "CH03", "CH04", "CH05"):
            ids.extend(c.get("maps", []))
    return sorted(set(ids))


def _iter_ruby_sources(commands, ce_by_id, visited_ce):
    """Yields (kind, text) for every 355/655 block, every 111 type-12
    condition, and every 122 type-4 operand in `commands`, inlining 117
    common-event calls once each (same discipline as
    `test_beat_floor_script_condition.py`'s corpus walk)."""
    i, n = 0, len(commands)
    while i < n:
        cmd = commands[i]
        code = cmd.get("code")
        if code == 355:
            text, j = script_block_source(commands, i)
            yield ("script", text)
            i = j
            continue
        if code == 111:
            params = cmd.get("parameters") or []
            if len(params) >= 2 and params[0] == 12:
                yield ("condition", params[1])
        if code == 122:
            params = cmd.get("parameters") or []
            if len(params) >= 5 and params[3] == 4:
                yield ("operand", params[4])
        if code == 117:
            params = cmd.get("parameters") or []
            if params and params[0] in ce_by_id and params[0] not in visited_ce:
                visited_ce.add(params[0])
                yield from _iter_ruby_sources(
                    ce_by_id[params[0]].get("list") or [], ce_by_id, visited_ce)
        i += 1


def _collect_ch01_ch05_sources() -> tuple[set[str], set[str], set[str]]:
    ce_by_id = _load_common_events_by_id()
    scripts: set[str] = set()
    conditions: set[str] = set()
    operands: set[str] = set()
    for map_id in _ch01_ch05_map_ids():
        path = MAPS_DIR / f"Map{map_id:03d}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for event in data.get("events") or []:
            if event is None:
                continue
            for page in event.get("pages") or []:
                visited_ce: set[int] = set()
                for kind, text in _iter_ruby_sources(
                    page.get("list") or [], ce_by_id, visited_ce,
                ):
                    if kind == "script":
                        scripts.add(text)
                    elif kind == "condition":
                        conditions.add(text)
                    elif kind == "operand":
                        operands.add(text)
    return scripts, conditions, operands


@pytestmark_corpus
def test_ch01_ch05_script_blocks_parse():
    scripts, _, _ = _collect_ch01_ch05_sources()
    assert scripts, "expected at least one 355/655 block in CH01-CH05"
    failures = []
    for text in scripts:
        try:
            parse_program(text)
        except RubyParseError as e:
            failures.append((text[:120], e.reason))
    assert not failures, f"{len(failures)} script blocks failed to parse: {failures[:10]}"


@pytestmark_corpus
def test_ch01_ch05_conditions_parse():
    _, conditions, _ = _collect_ch01_ch05_sources()
    assert conditions, "expected at least one 111 type-12 condition in CH01-CH05"
    failures = []
    for text in conditions:
        try:
            parse_expression(text)
        except RubyParseError as e:
            failures.append((text[:120], e.reason))
    assert not failures, f"{len(failures)} conditions failed to parse: {failures[:10]}"


@pytestmark_corpus
def test_ch01_ch05_operands_parse():
    _, _, operands = _collect_ch01_ch05_sources()
    # Measured 2026-09-23: CH01-CH05 (and the whole staged corpus) has zero
    # code-122 operands with operand type 4 (script). This test still
    # exercises the path so a future corpus refresh that introduces one is
    # covered without a new test.
    failures = []
    for text in operands:
        try:
            parse_expression(text)
        except RubyParseError as e:
            failures.append((text[:120], e.reason))
    assert not failures, f"{len(failures)} operands failed to parse: {failures[:10]}"
