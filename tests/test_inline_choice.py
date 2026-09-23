"""Tests for `rpg2gba.conversion_agent.inline_choice` (REDERIVATION_PLAN.md
C8 stage 3, part A)."""
from __future__ import annotations

import pytest

from rpg2gba.conversion_agent.inline_choice import (
    InlineChoice,
    InlineChoiceError,
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
