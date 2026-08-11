"""Wrapping data-table description text into explicit engine line breaks.

Nothing in pokeemerald auto-wraps a `.description` string -- it renders exactly
as authored. An unbroken Pokedex entry does not merely overflow: the info
screen centres it on its widest line (`GetStringCenterAlignXOffset`, and
`GetStringWidth` reports the whole string when there are no breaks), so the
text starts far off the left edge and is unreadable.
"""
from pathlib import Path

import pytest

from rpg2gba.text_validator.engine_metrics import (
    DEX_DESCRIPTION_MAX_LINES,
    DEX_DESCRIPTION_WIDTH_PX,
    load_charmap,
    measure_line_width_px,
    wrap_to_width,
)

ENGINE = Path(__file__).resolve().parents[1] / "engine"


@pytest.fixture(scope="module")
def charmap():
    return load_charmap(ENGINE / "charmap.txt")


def test_wraps_within_budget(charmap) -> None:
    text = ("Metal plates underneath its fur protect it from harm. It "
            "replenishes its energy by basking in the sun's rays.")
    lines = wrap_to_width(text, charmap, width_px=DEX_DESCRIPTION_WIDTH_PX,
                          max_lines=DEX_DESCRIPTION_MAX_LINES)
    assert len(lines) > 1
    for line in lines:
        assert measure_line_width_px(line, charmap) <= DEX_DESCRIPTION_WIDTH_PX


def test_wrap_preserves_every_word(charmap) -> None:
    """Wrapping is a re-flow, not an edit -- no word may be dropped, added or
    reordered, or the dex entry would silently say something else."""
    text = ("Newbie trainers traveling through caves are advised to bring "
            "along antidotes against a TONEMY's venom.")
    lines = wrap_to_width(text, charmap, width_px=DEX_DESCRIPTION_WIDTH_PX,
                          max_lines=DEX_DESCRIPTION_MAX_LINES)
    assert " ".join(lines).split() == text.split()


def test_single_line_text_stays_one_line(charmap) -> None:
    lines = wrap_to_width("A short entry.", charmap,
                          width_px=DEX_DESCRIPTION_WIDTH_PX)
    assert lines == ["A short entry."]


def test_empty_text_yields_no_lines(charmap) -> None:
    assert wrap_to_width("   ", charmap, width_px=DEX_DESCRIPTION_WIDTH_PX) == []


def test_unbreakable_word_fails_loud(charmap) -> None:
    """A token wider than the budget has no wrap point -- silently emitting it
    would put an overflowing line on screen (CLAUDE.md §4.5)."""
    with pytest.raises(ValueError, match="no wrap point exists"):
        wrap_to_width("A" * 80, charmap, width_px=DEX_DESCRIPTION_WIDTH_PX,
                      label="TESTMON: description")


def test_too_many_lines_fails_loud(charmap) -> None:
    """The engine clips past the line budget, so overrunning it must raise
    rather than emit text the player can never read."""
    text = " ".join(["word"] * 200)
    with pytest.raises(ValueError, match="exceeds the 4-line budget"):
        wrap_to_width(text, charmap, width_px=DEX_DESCRIPTION_WIDTH_PX,
                      max_lines=DEX_DESCRIPTION_MAX_LINES,
                      label="TESTMON: description")


def test_error_names_the_offending_species(charmap) -> None:
    with pytest.raises(ValueError, match="TESTMON: description"):
        wrap_to_width("Q" * 80, charmap, width_px=DEX_DESCRIPTION_WIDTH_PX,
                      label="TESTMON: description")


def test_budget_matches_vanilla(charmap) -> None:
    """The budget is derived from vanilla rather than from window geometry, so
    it must keep matching vanilla: no shipped description exceeds it."""
    import re

    block = re.compile(
        r'\.description = COMPOUND_STRING\(\s*((?:"(?:[^"\\]|\\.)*"\s*)+)\)', re.S)
    lit = re.compile(r'"((?:[^"\\]|\\.)*)"')
    d = ENGINE / "src/data/pokemon/species_info"
    checked = 0
    for path in sorted(d.glob("*.h")):
        for m in block.finditer(path.read_text(encoding="utf-8")):
            joined = "".join(lit.findall(m.group(1)))
            lines = joined.split("\\n")
            assert len(lines) <= DEX_DESCRIPTION_MAX_LINES, path
            for line in lines:
                assert measure_line_width_px(line, charmap) <= DEX_DESCRIPTION_WIDTH_PX, line
            checked += 1
    assert checked > 1000, f"expected the full vanilla corpus, saw {checked}"
