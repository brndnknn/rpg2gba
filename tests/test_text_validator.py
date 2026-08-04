"""Text-corpus validator (ROM_TEST_DEV.md §3 "text" / design ref C3).

Golden cases for each rule (TEXT_MARKUP, TEXT_HTML_TAG, TEXT_LINE_WIDTH,
TEXT_CHARMAP) plus edge cases: empty strings, a long-but-legitimately-wrapping
string, an accented charmap-legal character, and a corpus-shaped extraction
smoke test over synthetic ``.pory`` text (no emulator, no ROM).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.text_validator import extraction, rules
from rpg2gba.text_validator.engine_metrics import (
    Charmap,
    load_charmap,
    measure_line_width_px,
)
from rpg2gba.text_validator.extraction import ExtractedString, SourceLocation, extract_strings
from rpg2gba.text_validator.rules import (
    RULE_CHARMAP,
    RULE_HTML_TAG,
    RULE_LINE_WIDTH,
    RULE_MARKUP,
    check_charmap,
    check_html_tag,
    check_line_width,
    check_markup,
    validate_text,
)

_REAL_CHARMAP_PATH = Path(__file__).resolve().parents[1] / "engine" / "charmap.txt"

# A small representable set sufficient for the rule unit tests below (mirrors
# tests/test_assembly.py's _ALLOWED convention): letters/digits/space, basic
# punctuation, and 'é' so the "accented charmap-legal character" edge case has
# something real to assert against.
_ALLOWED = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 '.!?,:~()“”é"
)


def _loc(label: str = "TestBlock") -> SourceLocation:
    return SourceLocation(file=Path("Map001.pory"), line=1, label=label)


def _s(content: str, *, wrapped: bool = True, raw: str | None = None) -> ExtractedString:
    return ExtractedString(
        content=content,
        wrapped_in_format=wrapped,
        location=_loc(),
        raw_literal=raw if raw is not None else content,
    )


# --- fixture: the real engine charmap, if present -----------------------

@pytest.fixture(scope="module")
def real_charmap() -> Charmap:
    if not _REAL_CHARMAP_PATH.is_file():
        pytest.skip("engine/charmap.txt not present")
    return load_charmap(_REAL_CHARMAP_PATH)


# --- Rule 1: TEXT_MARKUP ------------------------------------------------

def test_markup_flags_color_code():
    issues = check_markup(_s("Hello \\c[0]world\\c[0]"))
    assert len(issues) == 2
    assert all(i.rule_id == RULE_MARKUP for i in issues)


def test_markup_flags_var_and_wait_codes():
    issues = check_markup(_s("You've caught \\v[3] of them\\wt[8]."))
    assert len(issues) == 2
    snippets = {m.group(0) for m in rules._UNSAFE_BACKSLASH_RE.finditer(
        "You've caught \\v[3] of them\\wt[8]."
    )}
    assert "\\v[3]" in snippets
    assert "\\wt[8]." in snippets  # \S* greedily includes the trailing period


def test_markup_allows_safe_breaks():
    assert check_markup(_s("Line one\\nLine two\\lscrolled")) == []


def test_markup_flags_bare_paragraph_code():
    """\\p is no longer treated as an automatically-safe break: a corpus
    census (output/uranium-build/maps/*.json, 2026-08-04) found every
    backslash-p occurrence in the corpus was the player-name code (\\PN/\\pn);
    a bare \\p that isn't that code is unhandled and must be flagged, not
    silently allowed through -- this is the same regression class as the
    \\pn player-name bug this rule exists to catch."""
    issues = check_markup(_s("Line one\\pnew page"))
    assert len(issues) == 1
    assert issues[0].rule_id == RULE_MARKUP


def test_markup_flags_untranslated_lowercase_player_name_code():
    """A stray untranslated \\pn reaching an emitted string (e.g. a
    hand-authored msgbox that bypassed translate_text_codes) is exactly the
    corpus bug this rule exists to catch."""
    issues = check_markup(_s("Oh, \\pn, you're leaving home..."))
    assert len(issues) == 1
    assert issues[0].rule_id == RULE_MARKUP


def test_markup_empty_string_no_issues():
    assert check_markup(_s("")) == []


# --- Rule 2: TEXT_HTML_TAG (DrawTextEx <br>/<b>/<c2=...> family) --------

def test_html_tag_flags_br():
    issues = check_html_tag(_s("Some text<br>more text"))
    assert len(issues) == 1
    assert issues[0].rule_id == RULE_HTML_TAG
    assert "<br>" in issues[0].message


def test_html_tag_flags_bold_and_color_pair():
    # The real Map050 corpus shape: <b>...</b> and <c2=X>...</c2>.
    issues = check_html_tag(
        _s("Take the <b>Aptitude Test</b>, <c2=043c3aff>Offensive</c2> trainer.")
    )
    tags = {i.message.split("tag ")[1].split(" in")[0] for i in issues}
    assert "'<b>'" in tags
    assert "'</b>'" in tags
    assert "'<c2=043c3aff>'" in tags
    assert "'</c2>'" in tags


def test_html_tag_no_false_positive_on_placeholder_braces():
    # {PLAYER}/{PAUSE ...} use curly braces, not angle brackets -- must not trip this rule.
    assert check_html_tag(_s("Hi {PLAYER}, wait{PAUSE 0x3C}...")) == []


def test_html_tag_empty_string_no_issues():
    assert check_html_tag(_s("")) == []


# --- Rule 3: TEXT_LINE_WIDTH ---------------------------------------------

def test_line_width_flags_overflow_on_unwrapped_string(real_charmap):
    long_line = "The Tandor Network is currently unavailable."  # real corpus example, 232px
    issues = check_line_width(_s(long_line, wrapped=False), real_charmap)
    assert len(issues) == 1
    assert issues[0].rule_id == RULE_LINE_WIDTH


def test_line_width_format_wrapped_long_string_does_not_flag_whole_segment(real_charmap):
    # A long string IS expected in format(...) -- poryscript re-wraps it at
    # compile time. Only an unbreakable single token should ever fire here.
    long_but_wrappable = (
        "This is a perfectly ordinary sentence with plenty of spaces to wrap on."
    )
    issues = check_line_width(_s(long_but_wrappable, wrapped=True), real_charmap)
    assert issues == []


def test_line_width_flags_unbreakable_token_even_when_wrapped(real_charmap):
    unbreakable = "x" * 80  # no spaces -- format() cannot wrap this
    issues = check_line_width(_s(unbreakable, wrapped=True), real_charmap)
    assert len(issues) == 1
    assert "cannot be fixed by poryscript's format()" in issues[0].message


def test_line_width_short_string_no_issue(real_charmap):
    assert check_line_width(_s("Hi!", wrapped=False), real_charmap) == []


def test_line_width_empty_string_no_issue(real_charmap):
    assert check_line_width(_s(""), real_charmap) == []


def test_line_width_pause_token_is_zero_width(real_charmap):
    # {PAUSE 0x3C} must not itself count toward the pixel budget.
    only_pause = "{PAUSE 0x3C}"
    assert measure_line_width_px(only_pause, real_charmap) == 0


def test_line_width_player_placeholder_uses_documented_approximation(real_charmap):
    from rpg2gba.text_validator.engine_metrics import PLACEHOLDER_WIDTH_PX

    assert measure_line_width_px("{PLAYER}", real_charmap) == PLACEHOLDER_WIDTH_PX


# --- Rule 4: TEXT_CHARMAP -------------------------------------------------

def test_charmap_accepts_legal_accented_character():
    # 'é' is charmap-legal (engine/charmap.txt: 'é' = 1B) -- no issue.
    issues = check_charmap(_s("Pokémon", raw="Pokémon"), _ALLOWED)
    assert issues == []


def test_charmap_flags_unrepresentable_character():
    issues = check_charmap(_s("a|b", raw="a|b"), _ALLOWED)
    assert len(issues) == 1
    assert issues[0].rule_id == RULE_CHARMAP


def test_charmap_substitution_targets_are_not_flagged():
    # '*', '[', ']' have downstream substitutions (normalize_pory) -- not a
    # corpus-validator failure by themselves.
    issues = check_charmap(_s("*note* [ok]", raw="*note* [ok]"), _ALLOWED)
    assert issues == []


def test_charmap_empty_string_no_issue():
    assert check_charmap(_s("", raw=""), _ALLOWED) == []


# --- validate_text: end-to-end over a small synthetic list ---------------

def test_validate_text_combines_all_rules(real_charmap):
    strings = [
        _s("Clean dialogue with no issues.", wrapped=True),
        _s("Bad code \\c[0]here", wrapped=False, raw="Bad code \\c[0]here"),
        _s("Rich <br>text", wrapped=False, raw="Rich <br>text"),
    ]
    issues = validate_text(strings, charmap=real_charmap, allowed_chars=_ALLOWED)
    rule_ids = {i.rule_id for i in issues}
    assert RULE_MARKUP in rule_ids
    assert RULE_HTML_TAG in rule_ids


# --- extraction: corpus-shaped .pory parsing ------------------------------

SAMPLE_PORY = """\
script Map048_EV001_Page1 {
    lockall
    msgbox(format("{PLAYER} come downstairs, you are late!"))
    releaseall
    end
}

# UNHANDLED code 101: dialogue with untranslated control code: "Hmmm\\wt[8]."
text Map048_EV002_Choice_Opt0 {
    format("Attack it right away!")
}

script CommonEvent_004 {
    msgbox("The Tandor Network is currently unavailable.")
    end
}
"""


def test_extract_strings_finds_all_literals_with_labels():
    strings = extract_strings(SAMPLE_PORY, Path("Map048.pory"))
    contents = [s.content for s in strings]
    assert "{PLAYER} come downstairs, you are late!" in contents
    assert "Attack it right away!" in contents
    assert "The Tandor Network is currently unavailable." in contents

    labels = {s.location.label for s in strings}
    assert "Map048_EV001_Page1" in labels
    assert "Map048_EV002_Choice_Opt0" in labels
    assert "CommonEvent_004" in labels


def test_extract_strings_skips_comment_lines():
    # The UNHANDLED comment's raw \wt[8] control code must not surface as a
    # finding -- comments never reach the ROM (poryscript strips them).
    strings = extract_strings(SAMPLE_PORY, Path("Map048.pory"))
    assert not any("wt[8]" in s.content for s in strings)


def test_extract_strings_tracks_format_wrapping():
    strings = extract_strings(SAMPLE_PORY, Path("Map048.pory"))
    by_content = {s.content: s for s in strings}
    assert by_content["{PLAYER} come downstairs, you are late!"].wrapped_in_format is True
    assert by_content["The Tandor Network is currently unavailable."].wrapped_in_format is False


def test_extract_strings_unescapes_quotes_in_content_but_not_raw():
    pory = 'script S {\n    msgbox("say \\"hi\\" now")\n    end\n}\n'
    strings = extract_strings(pory, Path("Map001.pory"))
    assert len(strings) == 1
    assert strings[0].content == 'say "hi" now'
    assert strings[0].raw_literal == 'say \\"hi\\" now'


def test_iter_corpus_files_deduplicates_and_globs(tmp_path: Path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "staging" / "scripts").mkdir(parents=True)
    (tmp_path / "porymap" / "dispatch").mkdir(parents=True)
    (tmp_path / "scripts" / "Map001.pory").write_text("script S { end }\n", encoding="utf-8")
    (tmp_path / "staging" / "scripts" / "Map001.pory").write_text(
        "script S { end }\n", encoding="utf-8"
    )
    files = extraction.iter_corpus_files(tmp_path)
    assert len(files) == 2  # one per directory, not deduplicated across different dirs
    assert len(set(files)) == 2


# --- TextGate: the staging-time fail-loud wiring (ROM_TEST_DEV C3) ----------
#
# `scan_output_dir` is the after-the-fact corpus report; `TextGate` is the
# same rules applied per script as it is staged into the engine, where a
# violation must abort the build (scripts/assemble_pathfinder.py).

_ENGINE = Path(__file__).resolve().parents[1] / "engine"

needs_engine = pytest.mark.skipif(
    not (_ENGINE / "charmap.txt").is_file(), reason="engine/charmap.txt not present"
)


@pytest.fixture()
def gate():
    from rpg2gba.text_validator import TextGate

    return TextGate(_ENGINE)


@needs_engine
def test_gate_passes_clean_text(gate):
    gate.check('script S {\n    msgbox(format("Hello there."))\n    end\n}\n', "Map001")


@needs_engine
def test_gate_raises_on_drawtextex_tag(gate):
    from rpg2gba.text_validator import TextGateViolation

    pory = 'script S {\n    msgbox(format("take the <b>Aptitude Test</b>."))\n    end\n}\n'
    with pytest.raises(TextGateViolation) as exc:
        gate.check(pory, "Map050")
    assert "Map050" in str(exc.value)
    assert "<b>" in str(exc.value)


@needs_engine
def test_gate_raises_on_unwrapped_overflow(gate):
    from rpg2gba.text_validator import TextGateViolation

    long_line = "The Tandor Network is currently unavailable."
    pory = f'script S {{\n    msgbox("{long_line}")\n    end\n}}\n'
    with pytest.raises(TextGateViolation, match="TEXT_LINE_WIDTH"):
        gate.check(pory, "CommonEvents")


@needs_engine
def test_gate_reports_every_error_not_just_the_first(gate):
    from rpg2gba.text_validator import TextGateViolation

    pory = (
        'script S {\n'
        '    msgbox(format("<b>one</b>"))\n'
        '    msgbox(format("<c2=ff00ff>two</c2>"))\n'
        '    end\n}\n'
    )
    with pytest.raises(TextGateViolation) as exc:
        gate.check(pory, "Map050")
    assert str(exc.value).count("TEXT_HTML_TAG") == 4  # two tags per string


@needs_engine
def test_gate_issues_is_non_raising(gate):
    pory = 'script S {\n    msgbox(format("<b>x</b>"))\n    end\n}\n'
    issues = gate.issues(pory, "Map050")
    assert [i.rule_id for i in issues] == ["TEXT_HTML_TAG", "TEXT_HTML_TAG"]
