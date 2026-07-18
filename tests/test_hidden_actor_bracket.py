"""Tests for SLICE1_TODO #16: auto-bracket flag-hidden cutscene actors.

See `src/rpg2gba/tileset_converter/hidden_actor_bracket.py`. Its original
exemplar was the hand file `Map032_EV074.pory`, deleted 2026-07-17 once this
pass reproduced its bracketing from raw transpiler output; the already-
bracketed no-op case is pinned by an inline fixture of the same shape below.
"""
from __future__ import annotations

from rpg2gba.tileset_converter.hidden_actor_bracket import bracket_hidden_actor_scripts


def test_basic_bracket_insertion_with_waitmovement_and_set_invisible() -> None:
    text = (
        "script Map999_EV001_Page1 {\n"
        "    lock\n"
        "    applymovement(1, Map999_EV001_Page1_Move1)\n"
        "    waitmovement(0)\n"
        "    release\n"
        "    end\n"
        "}\n"
        "\n"
        "movement Map999_EV001_Page1_Move1 {\n"
        "    walk_left\n"
        "    set_invisible\n"
        "}\n"
    )
    out = bracket_hidden_actor_scripts(text, {1}, source_name="test")
    expected = (
        "script Map999_EV001_Page1 {\n"
        "    lock\n"
        "    addobject(1)  # auto-bracket: flag-hidden actor\n"
        "    applymovement(1, Map999_EV001_Page1_Move1)\n"
        "    waitmovement(0)\n"
        "    removeobject(1)  # auto-bracket: flag-hidden actor\n"
        "    release\n"
        "    end\n"
        "}\n"
        "\n"
        "movement Map999_EV001_Page1_Move1 {\n"
        "    walk_left\n"
        "    set_invisible\n"
        "}\n"
    )
    assert out == expected


def test_no_set_invisible_means_no_removeobject() -> None:
    text = (
        "script Map999_EV002_Page1 {\n"
        "    applymovement(2, Map999_EV002_Page1_Move1)\n"
        "    waitmovement(0)\n"
        "    end\n"
        "}\n"
        "\n"
        "movement Map999_EV002_Page1_Move1 {\n"
        "    walk_left\n"
        "}\n"
    )
    out = bracket_hidden_actor_scripts(text, {2}, source_name="test")
    assert "addobject(2)" in out
    assert "removeobject(2)" not in out


def test_preexisting_addobject_is_skipped() -> None:
    text = (
        "script Map999_EV003_Page1 {\n"
        "    addobject(3)\n"
        "    applymovement(3, Map999_EV003_Page1_Move1)\n"
        "    waitmovement(0)\n"
        "    end\n"
        "}\n"
        "\n"
        "movement Map999_EV003_Page1_Move1 {\n"
        "    walk_left\n"
        "    set_invisible\n"
        "}\n"
    )
    out = bracket_hidden_actor_scripts(text, {3}, source_name="test")
    # exactly one addobject(3) — the pre-existing one, no duplicate inserted
    assert out.count("addobject(3)") == 1
    assert "addobject(3)  # auto-bracket" not in out
    # removeobject(3) is inserted (wasn't already present) since the route fades out
    assert out.count("removeobject(3)") == 1
    assert "removeobject(3)  # auto-bracket: flag-hidden actor" in out


def test_idempotence() -> None:
    text = (
        "script Map999_EV004_Page1 {\n"
        "    applymovement(4, Map999_EV004_Page1_Move1)\n"
        "    waitmovement(0)\n"
        "    end\n"
        "}\n"
        "\n"
        "movement Map999_EV004_Page1_Move1 {\n"
        "    walk_left\n"
        "    set_invisible\n"
        "}\n"
    )
    once = bracket_hidden_actor_scripts(text, {4}, source_name="test")
    twice = bracket_hidden_actor_scripts(once, {4}, source_name="test")
    assert once == twice


def test_multiple_hidden_actors_in_one_script() -> None:
    text = (
        "script Map999_EV005_Page1 {\n"
        "    applymovement(5, Map999_EV005_Page1_MoveA)\n"
        "    waitmovement(0)\n"
        "    applymovement(6, Map999_EV005_Page1_MoveB)\n"
        "    waitmovement(0)\n"
        "    end\n"
        "}\n"
        "\n"
        "movement Map999_EV005_Page1_MoveA {\n"
        "    walk_left\n"
        "    set_invisible\n"
        "}\n"
        "\n"
        "movement Map999_EV005_Page1_MoveB {\n"
        "    walk_right\n"
        "}\n"
    )
    out = bracket_hidden_actor_scripts(text, {5, 6}, source_name="test")
    assert "addobject(5)" in out
    assert "addobject(6)" in out
    # actor 5's route ends set_invisible -> removed; actor 6's does not
    assert "removeobject(5)" in out
    assert "removeobject(6)" not in out
    # ordering sane: addobject(5) precedes its applymovement, ditto addobject(6)
    idx_add5 = out.index("addobject(5)")
    idx_move5 = out.index("applymovement(5,")
    idx_add6 = out.index("addobject(6)")
    idx_move6 = out.index("applymovement(6,")
    assert idx_add5 < idx_move5 < idx_add6 < idx_move6


def test_reference_inside_string_or_comment_is_ignored() -> None:
    text = (
        "script Map999_EV007_Page1 {\n"
        '    msgbox(format("call applymovement(7, Foo) manually"))\n'
        "    # applymovement(7, Foo)\n"
        "    end\n"
        "}\n"
    )
    out = bracket_hidden_actor_scripts(text, {7}, source_name="test")
    assert out == text


def test_already_bracketed_ev074_shape_no_ops() -> None:
    """The deleted Map032_EV074.pory hand file's shape: addobject before the
    reveal, removeobject after the set_invisible fade-out — a script that
    already brackets its hidden actor must pass through unchanged."""
    text = (
        "script Map032_EV074_Page1 {\n"
        "    lock\n"
        "    addobject(75)\n"
        "    applymovement(75, Map032_EV074_Page1_Move4)\n"
        "    waitmovement(0)\n"
        "    applymovement(75, Map032_EV074_Page1_Move5)\n"
        "    waitmovement(0)\n"
        "    removeobject(75)\n"
        "    release\n"
        "    end\n"
        "}\n"
        "\n"
        "movement Map032_EV074_Page1_Move4 {\n"
        "    set_visible\n"
        "    walk_left\n"
        "}\n"
        "\n"
        "movement Map032_EV074_Page1_Move5 {\n"
        "    walk_up\n"
        "    set_invisible\n"
        "}\n"
    )
    out = bracket_hidden_actor_scripts(text, {75}, source_name="Map032_EV074.pory")
    assert out == text
