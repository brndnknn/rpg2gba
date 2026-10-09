"""Tests for `rpg2gba.conversion_agent.inline_choice` (REDERIVATION_PLAN.md
C8 stage 3, part A)."""
from __future__ import annotations

import pytest

from rpg2gba.conversion_agent.inline_choice import (
    CANCEL_SENTINEL,
    InlineChoice,
    InlineChoiceError,
    cancel_sentinel_read_problem,
    has_inline_choice,
    parse_inline_choice,
)


def test_has_inline_choice():
    assert has_inline_choice("hello \\ch[2,0,A,B]")
    assert not has_inline_choice("hello world")


def test_parses_bambo_shape():
    text = (
        "When you encounter a new\\nkind of Pokémon in the wild,\\n"
        "what is your first reaction?\\ch[2,0,<c2=043c3aff>Attack it right "
        "away!,\\c[4]Wait and see what it does.,<c2=65467b14>Throw a "
        "Poké Ball at it!]"
    )
    choice = parse_inline_choice(text)
    assert choice.var_id == 2
    assert choice.if_cancel == 0
    assert choice.options == (
        "Attack it right away!",
        "Wait and see what it does.",
        "Throw a Poké Ball at it!",
    )
    assert not choice.prompt_text.startswith("\\ch")
    assert choice.prompt_text.endswith("?")


def test_domain_no_cancel_is_option_indices():
    choice = InlineChoice(prompt_text="p", var_id=2, if_cancel=0, options=("A", "B", "C"))
    assert choice.domain() == (0, 1, 2)


def test_domain_cancel_in_range_adds_nothing():
    # ifCancel=2 -> cancel writes ifCancel-1=1, already option index 1.
    choice = InlineChoice(prompt_text="p", var_id=2, if_cancel=2, options=("A", "B", "C"))
    assert choice.domain() == (0, 1, 2)


def test_domain_cancel_out_of_range_appends():
    # ifCancel=9 -> cancel writes 8, outside 0..1 (2 options).
    choice = InlineChoice(prompt_text="p", var_id=2, if_cancel=9, options=("A", "B"))
    assert choice.domain() == (0, 1, 8)


def test_multiple_markers_refuses():
    with pytest.raises(InlineChoiceError, match=r"expected exactly one"):
        parse_inline_choice("a\\ch[1,0,A,B] b\\ch[1,0,C,D]")


def test_no_closing_bracket_refuses():
    with pytest.raises(InlineChoiceError, match=r"no closing"):
        parse_inline_choice("a\\ch[1,0,A,B")


def test_trailing_text_refuses():
    with pytest.raises(InlineChoiceError, match=r"trailing text"):
        parse_inline_choice("a\\ch[1,0,A,B] trailing")


def test_too_few_fields_refuses():
    with pytest.raises(InlineChoiceError, match=r"too few"):
        parse_inline_choice("a\\ch[1,0]")


def test_non_integer_var_refuses():
    with pytest.raises(InlineChoiceError, match=r"non-integer"):
        parse_inline_choice("a\\ch[x,0,A,B]")


def test_negative_if_cancel_refuses():
    with pytest.raises(InlineChoiceError, match=r"negative ifCancel"):
        parse_inline_choice("a\\ch[1,-1,A,B]")


def test_residual_tag_refuses():
    with pytest.raises(InlineChoiceError, match=r"residual unknown tag"):
        parse_inline_choice("a\\ch[1,0,A,B\\weird]")


def test_color_tags_stripped_not_refused():
    choice = parse_inline_choice("a\\ch[1,0,<c2=043c3aff>A,\\c[4]B]")
    assert choice.options == ("A", "B")


# -- ifCancel == -1 (cancel sentinel) ------------------------------------------


def _cmd(code: int, params: list, indent: int = 0) -> dict:
    return {"code": code, "indent": indent, "parameters": params}


def test_minus_one_if_cancel_needs_opt_in():
    # default still refuses (beat walker / ruby_subset search rely on this)
    with pytest.raises(InlineChoiceError, match=r"negative ifCancel"):
        parse_inline_choice("a\\ch[1,-1,A,B]")
    choice = parse_inline_choice("a\\ch[1,-1,A,B]", allow_cancel_sentinel=True)
    assert choice.if_cancel == -1


def test_other_negative_if_cancel_refuses_even_with_opt_in():
    with pytest.raises(InlineChoiceError, match=r"negative ifCancel"):
        parse_inline_choice("a\\ch[1,-2,A,B]", allow_cancel_sentinel=True)


def test_domain_minus_one_appends_sentinel():
    choice = parse_inline_choice("a\\ch[1,-1,A,B]", allow_cancel_sentinel=True)
    assert CANCEL_SENTINEL == 0x7FFF
    assert choice.domain() == (0, 1, CANCEL_SENTINEL)


def test_sentinel_reads_equality_and_reset_are_fine():
    page = [
        _cmd(111, [1, 2, 0, 0, 0]),  # var2 == 0
        _cmd(111, [1, 2, 0, 3, 5]),  # var2 != 3
        _cmd(122, [2, 2, 0, 0, 0]),  # var2 = 0 (reset)
        _cmd(111, [1, 9, 0, 3, 3]),  # ordered, but a different var
    ]
    assert cancel_sentinel_read_problem(page, 2) is None


@pytest.mark.parametrize("op", [1, 2, 3, 4])
def test_sentinel_ordered_comparison_refuses(op):
    page = [_cmd(111, [1, 2, 0, 0, op])]
    assert "ordered comparison" in cancel_sentinel_read_problem(page, 2)


def test_sentinel_var_vs_var_and_arithmetic_refuse():
    assert cancel_sentinel_read_problem([_cmd(111, [1, 2, 1, 7, 0])], 2)  # lhs
    assert cancel_sentinel_read_problem([_cmd(111, [1, 7, 1, 2, 0])], 2)  # rhs
    assert cancel_sentinel_read_problem([_cmd(122, [2, 2, 1, 0, 1])], 2)  # add
    assert cancel_sentinel_read_problem([_cmd(122, [7, 7, 0, 1, 2])], 2)  # copy out


def test_sentinel_textual_reads_refuse():
    assert cancel_sentinel_read_problem([_cmd(101, ["you chose \\v[2]"])], 2)
    assert cancel_sentinel_read_problem([_cmd(355, ["x = pbGet(2)"])], 2)
    assert cancel_sentinel_read_problem(
        [_cmd(111, [12, "$game_variables[2] > 3"])], 2)
    # the \ch row itself is not a read
    assert cancel_sentinel_read_problem([_cmd(101, ["Q?\\ch[2,-1,A,B]"])], 2) is None
