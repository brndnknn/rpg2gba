"""Tests for the extended Essentials text-code translator.

Covers ``translate_text_codes`` (the transpiler-spine contract, approved
mapping 2026-07-05 — reference/slice1_queue_readthrough.md "Idiom" bucket,
item 1) and pins down the LEGACY ``_translate_text`` path (frozen-Opus
classifier output) is unchanged by the extension.

Event/page shape conventions mirror ``tests/test_deterministic.py``, though
this module only needs the bare ``translate_text_codes(raw) -> TextTranslation
| None`` contract — no event/page scaffolding required.
"""
from __future__ import annotations

from rpg2gba.conversion_agent import deterministic as D

# ----------------------------------------------------------------------------
# plain text / \PN passthrough
# ----------------------------------------------------------------------------


def test_plain_text_passthrough() -> None:
    out = D.translate_text_codes("Hello there!")
    assert out == D.TextTranslation(text="Hello there!")


def test_player_name_code_still_works() -> None:
    out = D.translate_text_codes("Hi \\PN, welcome!")
    assert out is not None
    assert out.text == "Hi {PLAYER}, welcome!"
    assert out.autoclose is False
    assert out.sign is False


def test_line_breaks_pass_through_verbatim() -> None:
    out = D.translate_text_codes("First line\\nSecond\\lThird\\pFourth")
    assert out is not None
    assert out.text == "First line\\nSecond\\lThird\\pFourth"


# ----------------------------------------------------------------------------
# \sign[..] (item 1)
# ----------------------------------------------------------------------------


def test_sign_prefix_stripped_and_flagged() -> None:
    out = D.translate_text_codes("\\sign[Route 1]Welcome to Route 1!")
    assert out is not None
    assert out.text == "Welcome to Route 1!"
    assert out.sign is True
    assert out.autoclose is False


def test_sign_not_at_start_queues() -> None:
    """A \\sign anywhere but the leading position is an unknown shape."""
    assert D.translate_text_codes("Welcome, \\sign[Route 1] traveler!") is None


# ----------------------------------------------------------------------------
# \wtnp[n] (item 2) — trailing-only
# ----------------------------------------------------------------------------


def test_trailing_wtnp_stripped_and_flagged() -> None:
    out = D.translate_text_codes("Bye for now!\\wtnp[24]")
    assert out is not None
    assert out.text == "Bye for now!"
    assert out.autoclose is True
    assert out.sign is False


def test_trailing_wtnp_with_trailing_whitespace_stripped() -> None:
    """Whitespace after the trailing \\wtnp[n] is tolerated (spec: 'possibly
    followed only by whitespace')."""
    out = D.translate_text_codes("Bye for now!\\wtnp[24]   ")
    assert out is not None
    assert out.text == "Bye for now!"
    assert out.autoclose is True


def test_non_trailing_wtnp_queues() -> None:
    """Corpus census says \\wtnp[n] is 100% trailing; a non-trailing instance
    is an unhandled shape — fail loud rather than guess."""
    assert D.translate_text_codes("Bye for now!\\wtnp[24] more text") is None


def test_repeated_wtnp_queues() -> None:
    assert D.translate_text_codes("\\wtnp[1]\\wtnp[2]") is None


# ----------------------------------------------------------------------------
# \wt[n], \., \| pause codes (item 3)
# ----------------------------------------------------------------------------


def test_wt_pause_code_maps_to_hex_pause() -> None:
    # 10 * 3 = 30 = 0x1E
    out = D.translate_text_codes("Hold on\\wt[10] okay?")
    assert out is not None
    assert out.text == "Hold on{PAUSE 0x1E} okay?"


def test_wt_pause_code_caps_at_0xfe() -> None:
    # 1000 * 3 = 3000, capped to 0xFE
    out = D.translate_text_codes("Long wait\\wt[1000] done")
    assert out is not None
    assert out.text == "Long wait{PAUSE 0xFE} done"


def test_dot_pause_code() -> None:
    out = D.translate_text_codes("Wait\\. for it")
    assert out is not None
    assert out.text == "Wait{PAUSE 0x0F} for it"


def test_bar_pause_code() -> None:
    out = D.translate_text_codes("Hold\\| on")
    assert out is not None
    assert out.text == "Hold{PAUSE 0x3C} on"


# ----------------------------------------------------------------------------
# \c[n] and <fs=n>/</fs> stripping (item 4)
# ----------------------------------------------------------------------------


def test_color_code_dropped_text_preserved() -> None:
    out = D.translate_text_codes("\\c[3]Red text\\c[0] normal")
    assert out is not None
    assert out.text == "Red text normal"


def test_font_size_tags_dropped_text_preserved() -> None:
    out = D.translate_text_codes("<fs=24>Big</fs> and normal")
    assert out is not None
    assert out.text == "Big and normal"


# ----------------------------------------------------------------------------
# combinations
# ----------------------------------------------------------------------------


def test_sign_plus_pause_combination() -> None:
    out = D.translate_text_codes("\\sign[Sign]Open now\\wt[5]!")
    assert out is not None
    assert out.text == "Open now{PAUSE 0x0F}!"
    assert out.sign is True
    assert out.autoclose is False


def test_autoclose_plus_pause_combination() -> None:
    out = D.translate_text_codes("Bye\\wt[5]\\wtnp[24]")
    assert out is not None
    assert out.text == "Bye{PAUSE 0x0F}"
    assert out.autoclose is True
    assert out.sign is False


def test_sign_plus_autoclose_plus_pn_combination() -> None:
    out = D.translate_text_codes("\\sign[S]Bye \\PN\\wtnp[10]")
    assert out is not None
    assert out.text == "Bye {PLAYER}"
    assert out.sign is True
    assert out.autoclose is True


# ----------------------------------------------------------------------------
# unknown codes -> None (item 6, fail loud)
# ----------------------------------------------------------------------------


def test_gender_branch_code_queues() -> None:
    assert D.translate_text_codes("Hello \\g[m,f]!") is None


def test_variable_code_queues() -> None:
    assert D.translate_text_codes("You got \\v[3] items!") is None


def test_bare_r_code_queues() -> None:
    assert D.translate_text_codes("Reset\\r now") is None


def test_stray_brace_in_source_queues() -> None:
    assert D.translate_text_codes("Weird {brace} here") is None


# ----------------------------------------------------------------------------
# legacy _translate_text path unchanged (pin-down)
# ----------------------------------------------------------------------------


def test_legacy_translate_text_player_name_unchanged() -> None:
    assert D._translate_text("Hi \\PN!") == "Hi {PLAYER}!"


def test_legacy_translate_text_dot_code_still_queues() -> None:
    """The legacy path has no \\. mapping — classifier output is frozen and
    must keep falling through to the LLM for this code."""
    assert D._translate_text("Wait\\. for it") is None
