"""Phase 4 deterministic pre-filter tests (PHASE4_DETERMINISTIC_PLAN §4).

Classifier-level unit tests are pure functions over synthetic event dicts and
always run. The compile-gate test (a representative Classifier-1 output must
transpile through real poryscript) is marked `phase4` and skips when the binary
is absent — same convention as `test_conversion_agent.py::test_compile_gate`.

Event/page shape mirrors the Phase-3 deserializer output: an event is
``{id, name, x, y, pages:[...]}`` and each page is ``{trigger, list, ...}`` with
``list`` a sequence of ``{code, indent, parameters}`` commands.
"""
from __future__ import annotations

import pytest

from rpg2gba.conversion_agent import deterministic as D
from rpg2gba.conversion_agent import poryscript

# ----------------------------------------------------------------------------
# event/page builders
# ----------------------------------------------------------------------------


def _cmd(code: int, *params: object) -> dict:
    return {"code": code, "indent": 0, "parameters": list(params)}


def _page(*cmds: dict, trigger: int = 0) -> dict:
    return {"trigger": trigger, "list": list(cmds)}


def _event(*pages: dict, id: int = 1, name: str = "npc") -> dict:
    return {"id": id, "name": name, "x": 0, "y": 0, "pages": list(pages)}


def _text(s: str) -> dict:
    return _cmd(D.SHOW_TEXT, s)


def _text_cont(s: str) -> dict:
    return _cmd(D.SHOW_TEXT_CONT, s)


# ----------------------------------------------------------------------------
# format_pory_string / labels
# ----------------------------------------------------------------------------


def test_format_pory_string_wraps_and_escapes_quotes() -> None:
    assert D.format_pory_string("Hi there") == '"Hi there"'
    assert D.format_pory_string('say "hi"') == '"say \\"hi\\""'


def test_label_name_sanitizes_non_identifiers() -> None:
    assert D._label_name("npc") == "npc"
    assert D._label_name("Trainer(4)") == "Trainer_4"
    assert D._label_name("") == "EV_"
    assert D._label_name("2cool") == "EV_2cool"


def test_page_label_format() -> None:
    ev = _event(_page(), name="Trainer(4)", id=7)
    assert D._page_label(31, ev, 2) == "Map031_Trainer_4_Page2"


# ----------------------------------------------------------------------------
# Classifier 1 — Pure Dialogue (plan §4)
# ----------------------------------------------------------------------------


def test_single_block_101_plus_401_continuations() -> None:
    """101 + 401 + 401 collapse into one msgbox (plan §4 test 1)."""
    ev = _event(
        _page(_text("Hello there!"), _text_cont(" How are"), _text_cont(" you?")),
        id=3,
    )
    out = D.classify_pure_dialogue(1, ev)
    assert out is not None
    assert out.count("msgbox(") == 1
    assert 'msgbox("Hello there! How are you?")' in out
    assert out.startswith("script Map001_npc_Page1 {")
    # trigger-0 NPC gets the lock/faceplayer/release wrapper
    assert "lock" in out and "faceplayer" in out and "release" in out and "end" in out


def test_multi_page_emits_one_block_per_page() -> None:
    """Two pages → two correctly-labeled script blocks (plan §4 test 2)."""
    ev = _event(
        _page(_text("First page.")),
        _page(_text("Second page.")),
        id=12,
        name="sign",
    )
    out = D.classify_pure_dialogue(5, ev)
    assert out is not None
    assert "script Map005_sign_Page1 {" in out
    assert "script Map005_sign_Page2 {" in out
    assert 'msgbox("First page.")' in out
    assert 'msgbox("Second page.")' in out
    # exactly two blocks
    assert out.count("script Map005_sign_Page") == 2


@pytest.mark.parametrize(
    "call",
    [
        "pbCallBub(2)",
        "Kernel.pbSetPokemonCenter",
        "pbRemoveDependency2",
        "Kernel.pbRemoveDependency2",
        "set_fog2(1)",
        "pbSEPlay(:DOOR)",
        "$game_map.need_refresh = true",
    ],
)
def test_strip_script_calls_dropped_text_preserved(call: str) -> None:
    """STRIP-classified 355 calls produce no output; text survives (plan §4 3-6)."""
    ev = _event(_page(_cmd(D.SCRIPT, call), _text("Welcome!")), id=4)
    out = D.classify_pure_dialogue(2, ev)
    assert out is not None
    assert 'msgbox("Welcome!")' in out
    # the script call left no trace
    assert call not in out
    assert out.count("msgbox(") == 1


def test_conditional_branch_falls_through() -> None:
    """Any code-111 branch is not pure dialogue → None (plan §4 test 7)."""
    ev = _event(_page(_text("Choose."), _cmd(D.CONDITIONAL_BRANCH, 12, "x")), id=4)
    assert D.classify_pure_dialogue(1, ev) is None


def test_non_strip_script_call_falls_through() -> None:
    """A 355 call outside the STRIP list → None (plan §4 test 8)."""
    ev = _event(_page(_text("Hi"), _cmd(D.SCRIPT, "pbItemBall(:POTION)")), id=4)
    assert D.classify_pure_dialogue(1, ev) is None


# ----------------------------------------------------------------------------
# Classifier 1 — design deviations (module docstring)
# ----------------------------------------------------------------------------


def test_non_action_button_trigger_falls_through() -> None:
    """The dialogue wrapper assumes trigger 0; any other trigger → None."""
    ev = _event(_page(_text("Auto-run text."), trigger=3), id=4)
    assert D.classify_pure_dialogue(1, ev) is None


def test_mixed_triggers_falls_through() -> None:
    """All pages must be trigger 0; one non-0 page fails the whole event."""
    ev = _event(_page(_text("A")), _page(_text("B"), trigger=2), id=4)
    assert D.classify_pure_dialogue(1, ev) is None


@pytest.mark.parametrize("text", ["\\g[boy,girl]", "a {placeholder}", "\\sign[s]Cave", "wait\\."])
def test_essentials_control_codes_fall_through(text: str) -> None:
    """Unprescribed Essentials codes need LLM translation → None (not poryscript-safe)."""
    ev = _event(_page(_text(text)), id=4)
    assert D.classify_pure_dialogue(1, ev) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hi \\PN!", "Hi {PLAYER}!"),  # system.md: \PN -> {PLAYER}
        ("It's \\PN's house.", "It's {PLAYER}'s house."),  # possessive
        ("\\PN, watch out!\\nBe careful.", "{PLAYER}, watch out!\\nBe careful."),  # + safe \n
    ],
)
def test_player_name_substituted(text: str, expected: str) -> None:
    """\\PN is a prescribed substitution → claimed, not dropped."""
    ev = _event(_page(_text(text)), id=4)
    out = D.classify_pure_dialogue(1, ev)
    assert out is not None
    assert f'msgbox("{expected}")' in out


def test_player_name_with_unprescribed_code_still_falls_through() -> None:
    """\\PN is handled, but a co-occurring unprescribed code still bails the event."""
    ev = _event(_page(_text("Hi \\PN! \\sign[s]Look")), id=4)
    assert D.classify_pure_dialogue(1, ev) is None


@pytest.mark.parametrize("text", ["Line one.\\nLine two.", "Wait.\\pNext.", "a\\lb"])
def test_safe_line_breaks_pass_through(text: str) -> None:
    """\\n / \\l / \\p line breaks are pokeemerald-safe → emitted verbatim."""
    ev = _event(_page(_text(text)), id=4)
    out = D.classify_pure_dialogue(1, ev)
    assert out is not None
    assert text in out


def test_empty_page_is_bare_end_block() -> None:
    """A content-less page emits `script { end }`, not lock/release (docstring)."""
    ev = _event(_page(_cmd(D.SCRIPT, "pbCallBub(2)")), id=11)
    out = D.classify_pure_dialogue(2, ev)
    assert out is not None
    assert "lock" not in out and "faceplayer" not in out
    assert "end" in out


def test_event_with_no_pages_falls_through() -> None:
    assert D.classify_pure_dialogue(1, _event(id=4)) is None


def test_decorative_page_then_text_page() -> None:
    """A blank decorative page 1 + a dialogue page 2 both emit (no page skipped)."""
    ev = _event(_page(_cmd(D.SCRIPT, "set_fog2(1)")), _page(_text("Hi!")), id=6)
    out = D.classify_pure_dialogue(3, ev)
    assert out is not None
    assert "script Map003_npc_Page1 {" in out  # bare end
    assert 'msgbox("Hi!")' in out


# ----------------------------------------------------------------------------
# dispatcher
# ----------------------------------------------------------------------------


def test_dispatcher_returns_classifier_1_match() -> None:
    ev = _event(_page(_text("Hello!")), id=4)
    assert D.try_deterministic(1, ev) == D.classify_pure_dialogue(1, ev)


def test_dispatcher_swallows_classifier_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """A classifier that raises must not abort the run — dispatcher falls through."""

    def boom(map_id: int, event: dict, ctx: object) -> str | None:
        raise ValueError("should be swallowed")

    monkeypatch.setattr(D, "_CLASSIFIERS", [boom])
    assert D.try_deterministic(1, _event(_page(_text("x")))) is None


# ----------------------------------------------------------------------------
# compile-gate (real poryscript)
# ----------------------------------------------------------------------------


@pytest.mark.phase4
@pytest.mark.skipif(not poryscript.is_available(), reason="poryscript binary not installed")
def test_classifier_1_output_compiles() -> None:
    """A representative pure-dialogue output transpiles through poryscript (§4 test 9)."""
    ev = _event(
        _page(
            _cmd(D.SCRIPT, "pbCallBub(2)"),
            _text("Welcome to the lab!"),
            _text_cont(" Take your time."),
        ),
        _page(_text("See you around.")),
        id=3,
        name="prof",
    )
    out = D.classify_pure_dialogue(7, ev)
    assert out is not None
    result = poryscript.compile_script(out)
    assert result.ok, result.stderr
