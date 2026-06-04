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
from rpg2gba.conversion_agent.flag_registry import self_switch_flag_name

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
# Classifier 2 — Call Common Event (plan §5)
# ----------------------------------------------------------------------------


def test_cc_single_call_no_dialogue() -> None:
    """One page with only a CE call → claimed; block has lock/faceplayer/release/end."""
    ev = _event(_page(_cmd(D.CALL_COMMON_EVENT, 5)), id=1, name="npc")
    out = D.classify_call_common_event(1, ev)
    assert out is not None
    assert out.count("call CommonEvent_005") == 1
    assert "msgbox(" not in out
    assert "lock" in out
    assert "faceplayer" in out
    assert "release" in out
    assert "end" in out
    assert "script Map001_npc_Page1 {" in out


def test_cc_dialogue_before_call() -> None:
    """Text before a CE call → msgbox appears before call in output."""
    ev = _event(_page(_text("Hi there."), _cmd(D.CALL_COMMON_EVENT, 12)), id=1)
    out = D.classify_call_common_event(1, ev)
    assert out is not None
    assert 'msgbox("Hi there.")' in out
    assert "call CommonEvent_012" in out
    assert out.index('msgbox("Hi there.")') < out.index("call CommonEvent_012")


def test_cc_multiple_calls_in_order() -> None:
    """Multiple CE calls on one page preserve source order."""
    ev = _event(
        _page(_cmd(D.CALL_COMMON_EVENT, 3), _cmd(D.CALL_COMMON_EVENT, 7)), id=1
    )
    out = D.classify_call_common_event(1, ev)
    assert out is not None
    assert "call CommonEvent_003" in out
    assert "call CommonEvent_007" in out
    assert out.index("call CommonEvent_003") < out.index("call CommonEvent_007")


def test_cc_call_id_zero_returns_none() -> None:
    """CE id of 0 is invalid → None."""
    ev = _event(_page(_cmd(D.CALL_COMMON_EVENT, 0)), id=1)
    assert D.classify_call_common_event(1, ev) is None


def test_cc_branch_returns_none() -> None:
    """A conditional branch alongside a call → None."""
    ev = _event(
        _page(_cmd(D.CALL_COMMON_EVENT, 5), _cmd(D.CONDITIONAL_BRANCH, 12, "x")), id=1
    )
    assert D.classify_call_common_event(1, ev) is None


def test_cc_self_switch_returns_none() -> None:
    """A self-switch alongside a call → None (belongs to Classifier 3)."""
    ev = _event(
        _page(_cmd(D.CALL_COMMON_EVENT, 5), _cmd(D.CONTROL_SELF_SWITCH, "A", 0)), id=1
    )
    assert D.classify_call_common_event(1, ev) is None


def test_cc_pure_dialogue_no_call_returns_none() -> None:
    """Page with only text and no CE call → Classifier 2 declines."""
    ev = _event(_page(_text("Just talking.")), id=1)
    assert D.classify_call_common_event(1, ev) is None


def test_cc_strip_script_call_preserved() -> None:
    """STRIP script call is silently dropped; CE call survives in output."""
    ev = _event(
        _page(_cmd(D.SCRIPT, "pbCallBub(2)"), _cmd(D.CALL_COMMON_EVENT, 9)), id=1
    )
    out = D.classify_call_common_event(1, ev)
    assert out is not None
    assert "call CommonEvent_009" in out
    assert "pbCallBub" not in out


def test_cc_multi_page_one_block_each() -> None:
    """Two pages each with a CE call → two labeled script blocks."""
    ev = _event(
        _page(_cmd(D.CALL_COMMON_EVENT, 1)),
        _page(_cmd(D.CALL_COMMON_EVENT, 2)),
        id=3,
        name="helper",
    )
    out = D.classify_call_common_event(5, ev)
    assert out is not None
    assert "script Map005_helper_Page1 {" in out
    assert "script Map005_helper_Page2 {" in out
    assert out.count("script Map005_helper_Page") == 2


@pytest.mark.phase4
@pytest.mark.skipif(not poryscript.is_available(), reason="poryscript binary not installed")
def test_cc_output_compiles() -> None:
    """A representative CE-call event output compiles through poryscript."""
    ev = _event(
        _page(
            _cmd(D.SCRIPT, "pbCallBub(2)"),
            _text("Off we go!"),
            _cmd(D.CALL_COMMON_EVENT, 7),
        ),
        id=2,
        name="guide",
    )
    out = D.classify_call_common_event(4, ev)
    assert out is not None
    result = poryscript.compile_script(out)
    assert result.ok, result.stderr


# ----------------------------------------------------------------------------
# Classifier 3 — Self-Switch Dialogue (plan §6)
# ----------------------------------------------------------------------------


def test_ss_text_then_setflag() -> None:
    """Text followed by self-switch set → claimed; msgbox before setflag."""
    ev = _event(
        _page(_text("Once only."), _cmd(D.CONTROL_SELF_SWITCH, "A", 0)),
        id=3,
        name="npc",
    )
    out = D.classify_self_switch_dialogue(1, ev)
    assert out is not None
    assert 'msgbox("Once only.")' in out
    assert "setflag(FLAG_MAP001_EVENT003_SSA)" in out
    assert out.index('msgbox("Once only.")') < out.index("setflag(FLAG_MAP001_EVENT003_SSA)")
    assert "script Map001_npc_Page1 {" in out


def test_ss_turn_off_is_clearflag() -> None:
    """Self-switch value 1 → clearflag, not setflag."""
    ev = _event(
        _page(_text("Cleared."), _cmd(D.CONTROL_SELF_SWITCH, "A", 1)),
        id=3,
    )
    out = D.classify_self_switch_dialogue(1, ev)
    assert out is not None
    assert "clearflag(" in out
    assert "setflag(" not in out


def test_ss_letter_b() -> None:
    """Letter B → flag name ends with _SSB."""
    ev = _event(
        _page(_text("B switch."), _cmd(D.CONTROL_SELF_SWITCH, "B", 0)),
        id=3,
    )
    out = D.classify_self_switch_dialogue(1, ev)
    assert out is not None
    assert "_SSB)" in out


def test_ss_switch_only_no_text() -> None:
    """Page with only a self-switch (no text) → setflag present; no msgbox; talk wrapper emitted."""
    ev = _event(
        _page(_cmd(D.CONTROL_SELF_SWITCH, "A", 0)),
        id=3,
    )
    out = D.classify_self_switch_dialogue(1, ev)
    assert out is not None
    assert "setflag(" in out
    assert "msgbox(" not in out
    assert "lock" in out
    assert "faceplayer" in out
    assert "release" in out
    assert "end" in out


def test_ss_branch_returns_none() -> None:
    """Conditional branch alongside a self-switch → None."""
    ev = _event(
        _page(
            _text("Choose."),
            _cmd(D.CONTROL_SELF_SWITCH, "A", 0),
            _cmd(D.CONDITIONAL_BRANCH, 12, "x"),
        ),
        id=3,
    )
    assert D.classify_self_switch_dialogue(1, ev) is None


def test_ss_call_returns_none() -> None:
    """Call Common Event alongside a self-switch → None (Classifier 3 does not allow calls)."""
    ev = _event(
        _page(_cmd(D.CONTROL_SELF_SWITCH, "A", 0), _cmd(D.CALL_COMMON_EVENT, 5)),
        id=3,
    )
    assert D.classify_self_switch_dialogue(1, ev) is None


def test_ss_pure_dialogue_no_switch_returns_none() -> None:
    """Page with only text and no self-switch → Classifier 3 declines."""
    ev = _event(_page(_text("Just talking.")), id=3)
    assert D.classify_self_switch_dialogue(1, ev) is None


def test_ss_flag_name_agreement() -> None:
    """Emitted flag name matches what the flag_registry produces for (map, event, letter)."""
    ev = _event(
        _page(_text("Hello."), _cmd(D.CONTROL_SELF_SWITCH, "A", 0)),
        id=4,
        name="npc",
    )
    out = D.classify_self_switch_dialogue(7, ev)
    assert out is not None
    expected = f"setflag({self_switch_flag_name(7, 4, 'A')})"
    assert expected in out


def test_ss_multi_page() -> None:
    """Two pages each emits its own labeled script block."""
    ev = _event(
        _page(_text("First visit."), _cmd(D.CONTROL_SELF_SWITCH, "A", 0)),
        _page(_text("Already done.")),
        id=1,
        name="guard",
    )
    out = D.classify_self_switch_dialogue(5, ev)
    assert out is not None
    assert "script Map005_guard_Page1 {" in out
    assert "script Map005_guard_Page2 {" in out
    assert out.count("script Map005_guard_Page") == 2


@pytest.mark.phase4
@pytest.mark.skipif(not poryscript.is_available(), reason="poryscript binary not installed")
def test_ss_output_compiles() -> None:
    """A representative self-switch event output compiles through poryscript."""
    ev = _event(
        _page(
            _cmd(D.SCRIPT, "pbCallBub(2)"),
            _text("First time only!"),
            _cmd(D.CONTROL_SELF_SWITCH, "A", 0),
        ),
        id=2,
        name="giver",
    )
    out = D.classify_self_switch_dialogue(4, ev)
    assert out is not None
    result = poryscript.compile_script(out)
    assert result.ok, result.stderr


# ----------------------------------------------------------------------------
# Classifier 4 — Simple Warp (plan §7)
# ----------------------------------------------------------------------------


def test_warp_basic() -> None:
    """Single page with one TRANSFER_PLAYER → claimed; warp line + frame present."""
    ev = _event(_page(_cmd(D.TRANSFER_PLAYER, 0, 60, 21, 20, 0, 1)), id=2, name="EV002")
    out = D.classify_simple_warp(2, ev)
    assert out is not None
    assert "warp(MAP_URANIUM_60, 21, 20)" in out.script
    assert "lockall" in out.script
    assert "waitstate" in out.script
    assert "releaseall" in out.script
    assert "end" in out.script
    assert "script Map002_EV002_Page1 {" in out.script
    assert "fadescreen" not in out.script


def test_warp_queues_one_unhandled() -> None:
    """The single code-201 is queued as the one unhandled command."""
    ev = _event(_page(_cmd(D.TRANSFER_PLAYER, 0, 60, 21, 20, 0, 1)), id=2, name="EV002")
    out = D.classify_simple_warp(2, ev)
    assert out is not None
    assert len(out.unhandled) == 1
    assert out.unhandled[0]["command_code"] == 201
    assert "MAP_URANIUM_60" in out.unhandled[0]["description"]


def test_warp_strips_plumbing() -> None:
    """SE/fade/wait codes around the warp are stripped; exactly one warp emitted."""
    ev = _event(
        _page(
            _cmd(250, {}),
            _cmd(223, {}, 6),
            _cmd(106, 8),
            _cmd(D.TRANSFER_PLAYER, 0, 60, 21, 20, 0, 1),
            _cmd(223, {}, 6),
        ),
        id=2,
        name="EV002",
    )
    out = D.classify_simple_warp(2, ev)
    assert out is not None
    assert out.script.count("warp(") == 1
    assert "warp(MAP_URANIUM_60, 21, 20)" in out.script
    assert "223" not in out.script
    assert "playse" not in out.script.lower()


def test_warp_audio_script_call_stripped() -> None:
    """A STRIP-classified 355 call (pbSEPlay) is dropped; warp still emitted."""
    ev = _event(
        _page(
            _cmd(D.SCRIPT, "pbSEPlay(:EXIT_DOOR)"),
            _cmd(D.TRANSFER_PLAYER, 0, 60, 21, 20, 0, 1),
        ),
        id=2,
        name="EV002",
    )
    out = D.classify_simple_warp(2, ev)
    assert out is not None
    assert "warp(MAP_URANIUM_60, 21, 20)" in out.script
    assert "pbSEPlay" not in out.script


def test_warp_mode_nonzero_returns_none() -> None:
    """mode != 0 (variable warp) → classifier declines."""
    ev = _event(_page(_cmd(D.TRANSFER_PLAYER, 1, 60, 21, 20, 0, 1)), id=2, name="EV002")
    assert D.classify_simple_warp(2, ev) is None


def test_warp_two_warps_returns_none() -> None:
    """Two code-201 commands on one page → classifier declines."""
    ev = _event(
        _page(
            _cmd(D.TRANSFER_PLAYER, 0, 60, 21, 20, 0, 1),
            _cmd(D.TRANSFER_PLAYER, 0, 61, 5, 5, 0, 1),
        ),
        id=2,
        name="EV002",
    )
    assert D.classify_simple_warp(2, ev) is None


def test_warp_multipage_returns_none() -> None:
    """Multi-page event → classifier declines."""
    ev = _event(
        _page(_cmd(D.TRANSFER_PLAYER, 0, 60, 21, 20, 0, 1)),
        _page(_cmd(D.TRANSFER_PLAYER, 0, 61, 5, 5, 0, 1)),
        id=2,
        name="EV002",
    )
    assert D.classify_simple_warp(2, ev) is None


def test_warp_text_returns_none() -> None:
    """A SHOW_TEXT (101) alongside the warp is not in the safe set → None."""
    ev = _event(
        _page(
            _text("hi"),
            _cmd(D.TRANSFER_PLAYER, 0, 60, 21, 20, 0, 1),
        ),
        id=2,
        name="EV002",
    )
    assert D.classify_simple_warp(2, ev) is None


@pytest.mark.phase4
@pytest.mark.skipif(not poryscript.is_available(), reason="poryscript binary not installed")
def test_warp_output_compiles() -> None:
    """A representative simple-warp output compiles through poryscript."""
    ev = _event(_page(_cmd(D.TRANSFER_PLAYER, 0, 60, 21, 20, 0, 1)), id=2, name="EV002")
    out = D.classify_simple_warp(2, ev)
    assert out is not None
    result = poryscript.compile_script(out.script)
    assert result.ok, result.stderr


# ----------------------------------------------------------------------------
# dispatcher
# ----------------------------------------------------------------------------


def test_dispatcher_returns_classifier_1_match() -> None:
    ev = _event(_page(_text("Hello!")), id=4)
    # The dispatcher normalizes a classifier's bare-str return into a DetResult.
    assert D.try_deterministic(1, ev) == D.DetResult(D.classify_pure_dialogue(1, ev))


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
