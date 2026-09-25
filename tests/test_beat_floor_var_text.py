"""`\\v[N]` dialogue predicted from the page's own Ruby (ruling 18)."""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.beat_floor.var_text import expected_var_text, var_text_source

OUT_DIR = Path("output/uranium-build")

CEREMONY_SCRIPT = (
    'list=["Orchynx","Raptorch","Eletux"]\n'
    "x=pbGet(151)\n"
    "x=0 if x==3\n"
    "$game_variables[1]=x\n"
    "$game_variables[3]=list[x]"
)


def test_the_ceremony_line_names_the_third_starter() -> None:
    """Var 151 is the player's 1-based pick; the ceremony sends out the one
    after it in rotation -- neither the player's nor the rival's."""
    var_id, script, inputs = var_text_source(["Go! \\v[3]!"], [CEREMONY_SCRIPT])
    assert (var_id, inputs) == (3, (151,))
    got = {pick: expected_var_text(["Go! \\v[3]!"], var_id, script, {151: pick})
           for pick in (1, 2, 3)}
    assert got == {1: "Go! Raptorch!", 2: "Go! Eletux!", 3: "Go! Orchynx!"}


def test_uses_the_nearest_earlier_script_that_writes_the_var() -> None:
    older = '$game_variables[3]="Wrong"'
    assert var_text_source(["\\v[3]"], [older, CEREMONY_SCRIPT])[1] == CEREMONY_SCRIPT
    assert var_text_source(["\\v[3]"], [CEREMONY_SCRIPT, older])[1] == older


def test_unqualified_lines_stay_refused() -> None:
    # No script writes the var.
    assert var_text_source(["Go! \\v[3]!"], ["pbCallBub(2)"]) is None
    # Two substitutions in one line.
    assert var_text_source(["\\v[3] \\v[4]"], [CEREMONY_SCRIPT]) is None
    # The script reads a switch, not only variables.
    assert var_text_source(["\\v[3]"], ['$game_variables[3]="a" if $game_switches[5]']) is None
    # The written value is not a string.
    assert var_text_source(["\\v[3]"], ["$game_variables[3]=pbGet(151)+1"]) is None


@pytest.mark.skipif(not (OUT_DIR / "maps").is_dir(), reason="no converted corpus on disk")
def test_real_ceremony_row_floor_is_clean_and_carries_var_text() -> None:
    """Both halves of the fix on CH01's critical path: the floor reads the
    resolver's row state (no placeholder story_state refusal) and the
    ceremony line is a var_text assertion, not a text refusal."""
    from rpg2gba.beat_floor.lookup import floor_for_row

    ceremony = floor_for_row("map032/ev009/p2")
    assert not ceremony.refused, ceremony.refusals
    [vt] = [a for a in ceremony.assertions if a.kind == "var_text"]
    assert vt.param("var_id") == 3 and vt.param("input_vars") == (151,)
    assert not floor_for_row("map050/ev019/p0").refused
