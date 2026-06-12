"""Tests for the conversion tutor's pure helpers (no output/ dependency)."""
from __future__ import annotations

from scripts.run_tutor import LESSONS, _extract_blocks

_PORY = """\
script Map007_EV004_Page1 {
    lock
    msgbox("hi")
    end
}

script Map007_EV006_Page1 {
    lock
    giveitem(ITEM_HP_UP, 1)
    end
}

mart Map007_EV006_Page1_Mart {
    ITEM_POTION
}

script Map007_EV010_Page1 {
    end
}
"""


def test_extract_single_block_by_prefix():
    out = _extract_blocks(_PORY, "Map007_EV004_")
    assert out.startswith("script Map007_EV004_Page1 {")
    assert out.rstrip().endswith("}")
    assert "EV006" not in out  # did not bleed into the next block


def test_extract_includes_sibling_blocks_with_prefix():
    # An event's script AND its mart/movement sub-block share the prefix → both returned.
    out = _extract_blocks(_PORY, "Map007_EV006_")
    assert "script Map007_EV006_Page1" in out
    assert "mart Map007_EV006_Page1_Mart" in out
    assert "EV004" not in out and "EV010" not in out


def test_extract_returns_empty_when_no_match():
    assert _extract_blocks(_PORY, "Map099_EV001_") == ""


def test_lessons_are_well_formed():
    for lesson in LESSONS:
        assert {"title", "map", "event", "answer_prefix", "teach", "notes"} <= lesson.keys()
        assert lesson["answer_prefix"].startswith(f"Map{lesson['map']:03d}_EV{lesson['event']:03d}")
