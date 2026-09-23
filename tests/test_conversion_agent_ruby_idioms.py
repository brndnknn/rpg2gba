"""Tests for `rpg2gba.conversion_agent.ruby_idioms` (C8 stage 6).

Positive-case corpus strings are cited to the staged Uranium corpus rows
measured 2026-09-23 (map/event/page/index) -- these twelve shapes are the
whole idiom, and all of them live on map050 or map032:

  - match_local_from_var:      map050/ev019/p0/i45, map050/ev024/p0/i7
  - match_local_addsub:        map050/ev019/p0/i46
  - match_local_wrap:          map032/ev009/p2/i47, map050/ev019/p0/i47
  - match_array_literal:       map050/ev005/p0/i52
  - match_array_bump:          map050/ev005/p0/i58
  - match_array_argmax:        map050/ev005/p0/i101
  - match_remap_arm_open:      map050/ev005/p0/i102 (if), i104 (elsif)
  - match_local_const_assign:  map050/ev005/p0/i103, i105
  - is_block_end:               map050/ev005/p0/i106
  - match_var_from_local:      map032/ev009/p2/i48, map050/ev005/p0/i107
  - match_string_list:         map032/ev009/p2/i45
  - match_var_from_list_index: map032/ev009/p2/i49
"""
from __future__ import annotations

import pytest

from rpg2gba.conversion_agent import ruby_idioms as ri


# --- parse_statement ---------------------------------------------------


def test_parse_statement_out_of_subset_row_alone_is_none():
    assert ri.parse_statement("elsif x==0") is None


def test_parse_statement_def_is_none_if_out_of_subset():
    # ruby_subset only supports a restricted grammar; `def` is not in it.
    assert ri.parse_statement("def foo; end") is None


def test_parse_statement_multi_statement_source_is_none():
    assert ri.parse_statement("x=1\ny=2") is None


# --- match_local_from_var ------------------------------------------------


@pytest.mark.parametrize(
    "text,name,source_var",
    [
        ("x=pbGet(151)", "x", 151),  # map050/ev019/p0/i45
        ("i = pbGet(1)", "i", 1),  # map050/ev024/p0/i7
    ],
)
def test_match_local_from_var_positive(text, name, source_var):
    node = ri.parse_statement(text)
    result = ri.match_local_from_var(node)
    assert result == ri.LocalFromVar(name, source_var)


def test_match_local_from_var_rejects_game_variables_index():
    # _pbget_var is deliberately NOT widened to accept $game_variables[N]
    # (see the module docstring): widening changes which rows match, and
    # C8 stage 6 was gated on byte-identical output, so that's a separate
    # commit with its own measurement.
    node = ri.parse_statement("x=$game_variables[151]")
    assert ri.match_local_from_var(node) is None


def test_match_local_from_var_rejects_non_assign():
    node = ri.parse_statement("pbGet(151)")
    assert ri.match_local_from_var(node) is None


# --- match_local_addsub ---------------------------------------------------


def test_match_local_addsub_positive():
    node = ri.parse_statement("x-=2")  # map050/ev019/p0/i46
    result = ri.match_local_addsub(node)
    assert result == ri.LocalAddSub("x", -2)


def test_match_local_addsub_plus_positive():
    node = ri.parse_statement("x+=3")
    result = ri.match_local_addsub(node)
    assert result == ri.LocalAddSub("x", 3)


def test_match_local_addsub_rejects_mul_assign():
    node = ri.parse_statement("x*=2")
    assert ri.match_local_addsub(node) is None


def test_match_local_addsub_rejects_negative_literal_magnitude():
    # the regex this replaced was unsigned (`\d+`); `x -= -1` is not the idiom
    node = ri.parse_statement("x-=-1")
    assert ri.match_local_addsub(node) is None


# --- match_local_wrap ------------------------------------------------------


@pytest.mark.parametrize(
    "text,name,from_value,to_value",
    [
        ("x=0 if x==3", "x", 3, 0),  # map032/ev009/p2/i47
        ("x=2 if x==-1", "x", -1, 2),  # map050/ev019/p0/i47
    ],
)
def test_match_local_wrap_positive(text, name, from_value, to_value):
    node = ri.parse_statement(text)
    result = ri.match_local_wrap(node)
    assert result == ri.LocalWrap(name, from_value, to_value)


def test_match_local_wrap_rejects_mismatched_locals():
    # the two locals differ -- this was a regex backreference (\1)
    node = ri.parse_statement("y=0 if x==3")
    assert ri.match_local_wrap(node) is None


# --- match_array_literal ---------------------------------------------------


def test_match_array_literal_positive():
    node = ri.parse_statement("$game_variables[151]=[0,0,0]")  # map050/ev005/p0/i52
    result = ri.match_array_literal(node)
    assert result == ri.ArrayLiteral(151, (0, 0, 0))


def test_match_array_literal_rejects_string_elements():
    # match_array_literal and match_string_list must stay disjoint
    node = ri.parse_statement('$game_variables[151]=["a","b"]')
    assert ri.match_array_literal(node) is None


# --- match_array_bump -------------------------------------------------------


def test_match_array_bump_positive():
    node = ri.parse_statement("pbGet(151)[pbGet(2)]+=1")  # map050/ev005/p0/i58
    result = ri.match_array_bump(node)
    assert result == ri.ArrayBump(151, 2, 1)


def test_match_array_bump_rejects_minus_assign():
    # only += is the idiom
    node = ri.parse_statement("pbGet(151)[pbGet(2)]-=1")
    assert ri.match_array_bump(node) is None


# --- match_array_argmax ------------------------------------------------------


def test_match_array_argmax_positive():
    node = ri.parse_statement("x=pbGet(151).index(pbGet(151).max)")  # map050/ev005/p0/i101
    result = ri.match_array_argmax(node)
    assert result == ri.ArrayArgmax("x", 151)


def test_match_array_argmax_rejects_mismatched_var_ids():
    # the two pbGets must name the SAME variable
    node = ri.parse_statement("x=pbGet(151).index(pbGet(99).max)")
    assert ri.match_array_argmax(node) is None


# --- match_remap_arm_open ---------------------------------------------------


def test_match_remap_arm_open_if_positive():
    result = ri.match_remap_arm_open("if x==1")  # map050/ev005/p0/i102
    assert result == ri.RemapArmOpen("x", 1)


def test_match_remap_arm_open_elsif_positive():
    result = ri.match_remap_arm_open("elsif x==0")  # map050/ev005/p0/i104
    assert result == ri.RemapArmOpen("x", 0)


def test_match_remap_arm_open_rejects_compound_condition():
    assert ri.match_remap_arm_open("if x==1 && y==2") is None


def test_match_remap_arm_open_rejects_postfix_if():
    # a postfix if is a different idiom (match_local_wrap)
    assert ri.match_remap_arm_open("x=0 if x==3") is None


def test_match_remap_arm_open_rejects_body_on_same_line():
    assert ri.match_remap_arm_open("if x==1 then y=2 end") is None


# --- match_local_const_assign ------------------------------------------------


@pytest.mark.parametrize(
    "text,name,value",
    [
        ("x=0", "x", 0),  # map050/ev005/p0/i103
        ("x=1", "x", 1),  # map050/ev005/p0/i105
    ],
)
def test_match_local_const_assign_positive(text, name, value):
    node = ri.parse_statement(text)
    result = ri.match_local_const_assign(node)
    assert result == ri.LocalConstAssign(name, value)


def test_match_local_const_assign_rejects_var_valued_assign():
    node = ri.parse_statement("x=pbGet(1)")
    assert ri.match_local_const_assign(node) is None


# --- is_block_end -------------------------------------------------------


def test_is_block_end_positive():
    assert ri.is_block_end("end") is True  # map050/ev005/p0/i106


def test_is_block_end_rejects_non_end_text():
    assert ri.is_block_end("x=1") is False


def test_is_block_end_rejects_end_substring():
    assert ri.is_block_end("endpoint") is False


# --- match_var_from_local ---------------------------------------------------


@pytest.mark.parametrize(
    "text,var_id,name",
    [
        ("$game_variables[1]=x", 1, "x"),  # map032/ev009/p2/i48
        ("$game_variables[151]=x", 151, "x"),  # map050/ev005/p0/i107
    ],
)
def test_match_var_from_local_positive(text, var_id, name):
    node = ri.parse_statement(text)
    result = ri.match_var_from_local(node)
    assert result == ri.VarFromLocal(var_id, name)


def test_match_var_from_local_rejects_const_value():
    node = ri.parse_statement("$game_variables[1]=5")
    assert ri.match_var_from_local(node) is None


# --- match_string_list -------------------------------------------------------


def test_match_string_list_positive():
    node = ri.parse_statement('list=["Orchynx","Raptorch","Eletux"]')  # map032/ev009/p2/i45
    result = ri.match_string_list(node)
    assert result == ri.StringList("list", ("Orchynx", "Raptorch", "Eletux"))


def test_match_string_list_rejects_int_elements():
    # match_array_literal and match_string_list must stay disjoint
    node = ri.parse_statement("$game_variables[151]=[0,0,0]")
    assert ri.match_string_list(node) is None


# --- match_var_from_list_index -----------------------------------------------


def test_match_var_from_list_index_positive():
    node = ri.parse_statement("$game_variables[3]=list[x]")  # map032/ev009/p2/i49
    result = ri.match_var_from_list_index(node)
    assert result == ri.VarFromListIndex(3, "list", "x")


def test_match_var_from_list_index_rejects_const_index():
    node = ri.parse_statement("$game_variables[3]=list[1]")
    assert ri.match_var_from_list_index(node) is None
