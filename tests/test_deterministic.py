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

import json
import re
from pathlib import Path

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


# ----------------------------------------------------------------------------
# format_pory_dialogue
# ----------------------------------------------------------------------------


def test_format_pory_dialogue_plain_text() -> None:
    """Plain text with no layout breaks is just wrapped in format(...)."""
    assert D.format_pory_dialogue("plain text") == 'format("plain text")'


def test_format_pory_dialogue_flattens_layout_breaks_to_single_space() -> None:
    """A single \\n and a run of consecutive \\n both collapse to ONE space."""
    assert D.format_pory_dialogue("A.\\nB.") == 'format("A. B.")'
    assert D.format_pory_dialogue("A.\\n\\nB.") == 'format("A. B.")'
    assert D.format_pory_dialogue("A.\\n\\n\\nB.") == 'format("A. B.")'


def test_format_pory_dialogue_does_not_special_case_l_code() -> None:
    """The helper flattens \\n unconditionally; it has no \\l-preservation carve-out
    (that rule applies only to hand-override files, not this helper) — a \\l code
    anywhere in the text passes through untouched, same as any other character."""
    assert D.format_pory_dialogue("a\\lb") == 'format("a\\lb")'
    assert D.format_pory_dialogue("A.\\nB.\\lC.") == 'format("A. B.\\lC.")'


def test_format_pory_dialogue_escapes_embedded_quote() -> None:
    assert D.format_pory_dialogue('He said "hi"') == 'format("He said \\"hi\\"")'


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
    assert 'msgbox(format("Hello there! How are you?"))' in out
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
    assert 'msgbox(format("First page."))' in out
    assert 'msgbox(format("Second page."))' in out
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
    assert 'msgbox(format("Welcome!"))' in out
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
# Classifier 1 — Wait(106)/SE(250) plumbing tolerance (FABLES gate G2)
# ----------------------------------------------------------------------------


def test_wait_106_dropped_between_text_runs() -> None:
    """Family 1 (Map174 ev9 shape): a Wait between two Show-Text runs is dropped,
    each run becomes its own msgbox (frozen-Opus G2 evidence)."""
    ev = _event(
        _page(
            _text("Baitatao: the serpent."),
            _cmd(D.WAIT, 20),
            _text("It has not been seen since."),
            _text_cont(" Many wonder why."),
        ),
        id=9,
        name="Baitatao",
    )
    out = D.classify_pure_dialogue(174, ev)
    assert out is not None
    assert out.count("msgbox(") == 2
    assert 'msgbox(format("Baitatao: the serpent."))' in out
    assert 'msgbox(format("It has not been seen since. Many wonder why."))' in out
    assert "106" not in out  # Wait left no trace


def test_play_se_250_and_bubble_dropped_dialogue_preserved() -> None:
    """Family 2 (Map031 ev9 shape): leading SE(250) + pbCallBub 355 are both dropped,
    only the dialogue survives (frozen-Opus G2 evidence)."""
    ev = _event(
        _page(
            _cmd(D.PLAY_SE, {"name": "035Cry", "volume": 100}),
            _cmd(D.SCRIPT, "pbCallBub(1)"),
            _text("Owten!"),
        ),
        id=9,
        name="EV009",
    )
    out = D.classify_pure_dialogue(31, ev)
    assert out is not None
    assert out.count("msgbox(") == 1
    assert 'msgbox(format("Owten!"))' in out
    assert "pbCallBub" not in out


def test_wait_and_se_interleaved_with_dialogue() -> None:
    """Wait + SE mixed into a single dialogue run are both dropped (Tier-1 kin)."""
    ev = _event(
        _page(
            _text("Listen..."),
            _cmd(D.WAIT, 30),
            _cmd(D.PLAY_SE, {"name": "chime"}),
            _text_cont(" can you hear it?"),
        ),
        id=119,
    )
    out = D.classify_pure_dialogue(84, ev)
    assert out is not None
    assert out.count("msgbox(") == 1
    assert 'msgbox(format("Listen... can you hear it?"))' in out


@pytest.mark.parametrize(
    "page",
    [
        _page(_cmd(D.PLAY_SE, {"name": "boom"})),  # SE-only bridge
        _page(_cmd(D.WAIT, 60)),  # Wait-only
        # SE + strip call, no text:
        _page(_cmd(D.PLAY_SE, {"name": "boom"}), _cmd(D.SCRIPT, "pbCallBub(1)")),
    ],
)
def test_cosmetic_only_no_dialogue_falls_through(page: dict) -> None:
    """A page whose only content is stripped Wait/SE (no Show-Text) is the declined
    cosmetic-only class — defer to the LLM, do NOT emit an empty block (gate G2)."""
    assert D.classify_pure_dialogue(1, _event(page, id=4)) is None


def test_wait_se_output_compiles() -> None:
    """The Wait/SE-tolerant dialogue output compiles through poryscript."""
    ev = _event(
        _page(
            _cmd(D.PLAY_SE, {"name": "035Cry"}),
            _cmd(D.SCRIPT, "pbCallBub(1)"),
            _text("Owten!"),
        ),
        id=9,
        name="EV009",
    )
    out = D.classify_pure_dialogue(31, ev)
    assert out is not None
    result = poryscript.compile_script(out)
    assert result.ok, result.stderr


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
        # \n is an RMXP layout break -> flattened to a single space by format_pory_dialogue
        ("\\PN, watch out!\\nBe careful.", "{PLAYER}, watch out! Be careful."),
    ],
)
def test_player_name_substituted(text: str, expected: str) -> None:
    """\\PN is a prescribed substitution → claimed, not dropped."""
    ev = _event(_page(_text(text)), id=4)
    out = D.classify_pure_dialogue(1, ev)
    assert out is not None
    assert f'msgbox(format("{expected}"))' in out


def test_player_name_with_unprescribed_code_still_falls_through() -> None:
    """\\PN is handled, but a co-occurring unprescribed code still bails the event."""
    ev = _event(_page(_text("Hi \\PN! \\sign[s]Look")), id=4)
    assert D.classify_pure_dialogue(1, ev) is None


@pytest.mark.parametrize(
    ("text", "expected_in_out"),
    [
        # \n is an RMXP layout break -> flattened to a single space by
        # format_pory_dialogue (format() re-wraps and recreates breaks itself).
        ("Line one.\\nLine two.", "Line one. Line two."),
        # \l / \p are pokeemerald-safe codes -> format() passes them through untouched.
        ("Wait.\\pNext.", "Wait.\\pNext."),
        ("a\\lb", "a\\lb"),
    ],
)
def test_layout_line_breaks_flattened_safe_codes_pass_through(
    text: str, expected_in_out: str
) -> None:
    """\\n is flattened to a space for format(); \\l / \\p still pass through verbatim."""
    ev = _event(_page(_text(text)), id=4)
    out = D.classify_pure_dialogue(1, ev)
    assert out is not None
    assert expected_in_out in out


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
    assert 'msgbox(format("Hi!"))' in out


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
    assert 'msgbox(format("Hi there."))' in out
    assert "call CommonEvent_012" in out
    assert out.index('msgbox(format("Hi there."))') < out.index("call CommonEvent_012")


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
    assert 'msgbox(format("Once only."))' in out
    assert "setflag(FLAG_MAP001_EVENT003_SSA)" in out
    assert out.index('msgbox(format("Once only."))') < out.index(
        "setflag(FLAG_MAP001_EVENT003_SSA)"
    )
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


# ----------------------------------------------------------------------------
# Classifier 5 — Trainer Battle (plan §8)
# ----------------------------------------------------------------------------

# Shared fixtures for trainer tests.
# Page 1: FISHERMAN "Matt" — one pbTrainerBattle branch, comment + script plumbing.
_FISHERMAN_BATTLE_ARG = (
    'pbTrainerBattle(PBTrainers::FISHERMAN,"Matt",'
    '_I("T-the ones you have are nice too..."),false,0,false,0)'
)

_FISHERMAN_PAGE1 = _page(
    _cmd(D.COMMENT, "Type: FISHERMAN"),
    _cmd(D.COMMENT, "Name: Matt"),
    _cmd(D.SCRIPT, "pbTrainerIntro(:FISHERMAN)"),
    _cmd(D.SCRIPT, "pbCallBub(2)"),
    _text("The ocean holds different species!"),
    _cmd(D.CONDITIONAL_BRANCH, 12, _FISHERMAN_BATTLE_ARG),
    _cmd(D.CONTROL_SELF_SWITCH, "A", 0),
    _cmd(D.SCRIPT, "pbTrainerEnd"),
)

_FISHERMAN_PAGE2 = _page(
    _cmd(D.SCRIPT, "pbCallBub(2)"),
    _text("Y'know, the Gym Leader is tough."),
)

_FISHERMAN_CTX = D.Context(trainers={("TRAINER_CLASS_FISHERMAN", "Matt", 0): "TRAINER_BRANDON_16"})


def test_trainer_clean_single_match() -> None:
    """FISHERMAN event + injected ctx → claimed; output has trainerbattle_single, intro, defeat."""
    ev = _event(_FISHERMAN_PAGE1, _FISHERMAN_PAGE2, id=5, name="Fisherman_Matt")
    out = D.classify_trainer_battle(8, ev, _FISHERMAN_CTX)
    assert out is not None
    assert "trainerbattle_single(TRAINER_BRANDON_16," in out
    assert '"The ocean holds different species!"' in out
    assert '"T-the ones you have are nice too..."' in out
    assert "script Map008_Fisherman_Matt_Page1 {" in out
    assert "release" in out
    assert "end" in out


def test_trainer_postbattle_msgbox() -> None:
    """Page-2 post-battle text appears as msgbox AFTER the trainerbattle line."""
    ev = _event(_FISHERMAN_PAGE1, _FISHERMAN_PAGE2, id=5, name="Fisherman_Matt")
    out = D.classify_trainer_battle(8, ev, _FISHERMAN_CTX)
    assert out is not None
    postbattle = 'msgbox(format("Y\'know, the Gym Leader is tough."))'
    assert postbattle in out
    assert out.index("trainerbattle_single(") < out.index(postbattle)


def test_trainer_unknown_returns_none() -> None:
    """Empty ctx (lookup miss) → None."""
    ev = _event(_FISHERMAN_PAGE1, _FISHERMAN_PAGE2, id=5, name="Fisherman_Matt")
    assert D.classify_trainer_battle(8, ev, D.Context()) is None


def test_trainer_party_id_nonzero() -> None:
    """party_id 7 is parsed correctly; output contains the right TRAINER_ constant."""
    page1 = _page(
        _cmd(D.SCRIPT, "pbTrainerIntro(:RIVAL)"),
        _text("Let's go, rival!"),
        _cmd(
            D.CONDITIONAL_BRANCH,
            12,
            'pbTrainerBattle(PBTrainers::RIVAL,"Theo",_I("Gyaaah!"),false,7)',
        ),
        _cmd(D.CONTROL_SELF_SWITCH, "A", 0),
        _cmd(D.SCRIPT, "pbTrainerEnd"),
    )
    page2 = _page(_text("You're not bad."))
    ctx = D.Context(trainers={("TRAINER_CLASS_RIVAL", "Theo", 7): "TRAINER_THEO_42"})
    ev = _event(page1, page2, id=10, name="Rival_Theo")
    out = D.classify_trainer_battle(3, ev, ctx)
    assert out is not None
    assert "trainerbattle_single(TRAINER_THEO_42," in out


def test_trainer_double_returns_none() -> None:
    """pbDoubleTrainerBattle in the branch → None."""
    page1 = _page(
        _cmd(D.SCRIPT, "pbTrainerIntro(:FISHERMAN)"),
        _text("Two vs two!"),
        _cmd(
            D.CONDITIONAL_BRANCH,
            12,
            'pbDoubleTrainerBattle(PBTrainers::FISHERMAN,"Matt",_I("Ugh!"),false,0)',
        ),
        _cmd(D.CONTROL_SELF_SWITCH, "A", 0),
        _cmd(D.SCRIPT, "pbTrainerEnd"),
    )
    page2 = _page(_text("Good match."))
    ev = _event(page1, page2, id=5, name="Fisherman_Matt")
    assert D.classify_trainer_battle(8, ev, _FISHERMAN_CTX) is None


def test_trainer_extra_branch_returns_none() -> None:
    """Second code-111 on page 1 → None."""
    page1 = _page(
        _cmd(D.SCRIPT, "pbTrainerIntro(:FISHERMAN)"),
        _text("Two branches!"),
        _cmd(D.CONDITIONAL_BRANCH, 12, _FISHERMAN_BATTLE_ARG),
        _cmd(D.CONDITIONAL_BRANCH, 12, "$Trainer.ablePokemonCount<=1"),
        _cmd(D.CONTROL_SELF_SWITCH, "A", 0),
        _cmd(D.SCRIPT, "pbTrainerEnd"),
    )
    page2 = _page(_text("Post battle."))
    ev = _event(page1, page2, id=5, name="Fisherman_Matt")
    assert D.classify_trainer_battle(8, ev, _FISHERMAN_CTX) is None


def test_trainer_three_pages_returns_none() -> None:
    """More than 2 pages → None."""
    page3 = _page(_text("Extra page."))
    ev = _event(_FISHERMAN_PAGE1, _FISHERMAN_PAGE2, page3, id=5, name="Fisherman_Matt")
    assert D.classify_trainer_battle(8, ev, _FISHERMAN_CTX) is None


def test_trainer_no_self_switch_returns_none() -> None:
    """Missing code-123 on page 1 → None."""
    page1_no_ss = _page(
        _cmd(D.SCRIPT, "pbTrainerIntro(:FISHERMAN)"),
        _cmd(D.SCRIPT, "pbCallBub(2)"),
        _text("The ocean holds different species!"),
        _cmd(D.CONDITIONAL_BRANCH, 12, _FISHERMAN_BATTLE_ARG),
        _cmd(D.SCRIPT, "pbTrainerEnd"),
    )
    ev = _event(page1_no_ss, _FISHERMAN_PAGE2, id=5, name="Fisherman_Matt")
    assert D.classify_trainer_battle(8, ev, _FISHERMAN_CTX) is None


@pytest.mark.phase4
@pytest.mark.skipif(not poryscript.is_available(), reason="poryscript binary not installed")
def test_trainer_output_compiles() -> None:
    """A representative trainer-battle output compiles through poryscript."""
    ev = _event(_FISHERMAN_PAGE1, _FISHERMAN_PAGE2, id=5, name="Fisherman_Matt")
    out = D.classify_trainer_battle(8, ev, _FISHERMAN_CTX)
    assert out is not None
    result = poryscript.compile_script(out)
    assert result.ok, result.stderr


# ----------------------------------------------------------------------------
# load_context
# ----------------------------------------------------------------------------


def test_load_context_reads_trainers(tmp_path: Path) -> None:
    """trainers.json → ctx.trainers keyed by (trainer_class, name, party_id)."""
    trainers_data = {
        "trainers": {
            "TRAINER_BRANDON_16": {
                "trainer_class": "TRAINER_CLASS_FISHERMAN",
                "name": "Matt",
                "party_id": 0,
            }
        }
    }
    (tmp_path / "trainers.json").write_text(json.dumps(trainers_data), encoding="utf-8")
    ctx = D.load_context(reference_dir=tmp_path, intermediate_dir=tmp_path)
    assert ctx.trainers[("TRAINER_CLASS_FISHERMAN", "Matt", 0)] == "TRAINER_BRANDON_16"


def test_load_context_empty_dir_yields_empty_trainers(tmp_path: Path) -> None:
    """Missing trainers.json → empty trainers dict (tolerant, no crash)."""
    ctx = D.load_context(reference_dir=tmp_path, intermediate_dir=tmp_path)
    assert ctx.trainers == {}


# ----------------------------------------------------------------------------
# Classifier 7 — Sign Dialogue (plan §12)
# ----------------------------------------------------------------------------


def test_sign_basic() -> None:
    """Single page with \\sign prefix → lock/msgbox/release/end, no faceplayer, no MSGBOX_SIGN."""
    ev = _event(
        _page(_cmd(D.SHOW_TEXT, r"\sign[sign1]Tunnel to Lanthanite Cave.")),
        id=1,
        name="Sign",
    )
    out = D.classify_sign_dialogue(132, ev)
    assert out is not None
    assert 'msgbox(format("Tunnel to Lanthanite Cave."))' in out
    assert "lock" in out
    assert "release" in out
    assert "end" in out
    assert "faceplayer" not in out
    assert "MSGBOX_SIGN" not in out
    assert "script Map132_Sign_Page1 {" in out


def test_sign_layout_break_flattened_for_format() -> None:
    """\\n inside sign text is an RMXP layout break -> flattened to a single space
    by format_pory_dialogue, not passed through verbatim."""
    ev = _event(
        _page(_cmd(D.SHOW_TEXT, r"\sign[s]Top\nBottom")),
        id=2,
        name="Sign",
    )
    out = D.classify_sign_dialogue(1, ev)
    assert out is not None
    assert 'msgbox(format("Top Bottom"))' in out
    assert r"Top\nBottom" not in out


def test_sign_multi_page() -> None:
    """Two action-button pages both with \\sign → two script blocks."""
    ev = _event(
        _page(_cmd(D.SHOW_TEXT, r"\sign[s1]First line.")),
        _page(_cmd(D.SHOW_TEXT, r"\sign[s2]Second line.")),
        id=3,
        name="DualSign",
    )
    out = D.classify_sign_dialogue(10, ev)
    assert out is not None
    assert "script Map010_DualSign_Page1 {" in out
    assert "script Map010_DualSign_Page2 {" in out
    assert out.count("script Map010_DualSign_Page") == 2
    assert 'msgbox(format("First line."))' in out
    assert 'msgbox(format("Second line."))' in out


def test_sign_bail_on_embedded_quote() -> None:
    """Embedded quote in sign text → None (Opus quote-drop rule unconfirmed)."""
    ev = _event(
        _page(_cmd(D.SHOW_TEXT, r'\sign[s]He said "hi"')),
        id=4,
        name="Sign",
    )
    assert D.classify_sign_dialogue(1, ev) is None


def test_sign_bail_on_extra_essentials_code() -> None:
    """Extra \\. code after sign prefix → None (unsafe code detected)."""
    ev = _event(
        _page(_cmd(D.SHOW_TEXT, r"\sign[s]Wait\. here")),
        id=5,
        name="Sign",
    )
    assert D.classify_sign_dialogue(1, ev) is None


def test_sign_bail_no_sign_prefix() -> None:
    """Plain-dialogue event without \\sign prefix → classify_sign_dialogue returns None."""
    ev = _event(
        _page(_cmd(D.SHOW_TEXT, "Just a plain NPC.")),
        id=6,
        name="npc",
    )
    assert D.classify_sign_dialogue(1, ev) is None


def test_sign_bail_non_action_button_trigger() -> None:
    """Autorun page (trigger=3) carrying a sign → None."""
    ev = _event(
        _page(_cmd(D.SHOW_TEXT, r"\sign[s]Autorun sign."), trigger=3),
        id=7,
        name="Sign",
    )
    assert D.classify_sign_dialogue(1, ev) is None


def test_sign_no_regression_pure_dialogue() -> None:
    """Pure-dialogue event still classified by classify_pure_dialogue unchanged."""
    ev = _event(
        _page(_cmd(D.SHOW_TEXT, "Hello there!")),
        id=8,
        name="npc",
    )
    out = D.classify_pure_dialogue(1, ev)
    assert out is not None
    assert 'msgbox(format("Hello there!"))' in out
    assert "faceplayer" in out
    assert "lock" in out
    assert "release" in out


def test_sign_dispatch_no_faceplayer() -> None:
    """try_deterministic on a sign event → DetResult with no faceplayer in script."""
    ev = _event(
        _page(_cmd(D.SHOW_TEXT, r"\sign[s]Cave entrance ahead.")),
        id=9,
        name="Sign",
    )
    result = D.try_deterministic(1, ev)
    assert result is not None
    assert "faceplayer" not in result.script


@pytest.mark.phase4
@pytest.mark.skipif(not poryscript.is_available(), reason="poryscript binary not installed")
def test_sign_output_compiles() -> None:
    """A representative sign-dialogue output compiles through poryscript."""
    ev = _event(
        _page(_cmd(D.SHOW_TEXT, r"\sign[sign1]Comet Cave, Rochfale City right ahead.")),
        id=1,
        name="Sign",
    )
    out = D.classify_sign_dialogue(132, ev)
    assert out is not None
    result = poryscript.compile_script(out)
    assert result.ok, result.stderr


# ----------------------------------------------------------------------------
# Classifier 8 — Ground Item / pbItemBall (iterative roadmap Group 1)
# ----------------------------------------------------------------------------

_ITEM_CTX = D.Context(items={"HPUP": "ITEM_HP_UP", "FULLHEAL": "ITEM_FULL_HEAL"})


def _itemball_event(symbol: str = "HPUP", *, letter: str = "A", value: int = 0,
                    id: int = 6, name: str = "EV006", gate_pages: int = 1) -> dict:
    """A ground-item event: page 1 = if pbItemBall(symbol) { self-switch }, plus
    `gate_pages` empty post-pickup pages."""
    page1 = _page(
        _cmd(D.CONDITIONAL_BRANCH, 12, f"Kernel.pbItemBall(::PBItems::{symbol})"),
        _cmd(D.CONTROL_SELF_SWITCH, letter, value),
        _cmd(D.ELSE_BRANCH),
        _cmd(D.BRANCH_END),
    )
    return _event(page1, *([_page()] * gate_pages), id=id, name=name)


def test_ground_item_golden_output() -> None:
    """Matches frozen-Opus byte-for-byte (Map007 EV006): lock/giveitem/setflag/release/end."""
    out = D.classify_ground_item(7, _itemball_event(), _ITEM_CTX)
    expected = (
        "script Map007_EV006_Page1 {\n"
        "    lock\n"
        "    giveitem(ITEM_HP_UP, 1)\n"
        f"    setflag({self_switch_flag_name(7, 6, 'A')})\n"
        "    release\n"
        "    end\n"
        "}\n\n"
        "script Map007_EV006_Page2 {\n"
        "    end\n"
        "}"
    )
    assert out == expected


def test_ground_item_no_faceplayer() -> None:
    """A pickup, not an NPC talk — never emits faceplayer."""
    out = D.classify_ground_item(7, _itemball_event(), _ITEM_CTX)
    assert out is not None and "faceplayer" not in out


def test_ground_item_self_switch_b() -> None:
    """The self-switch letter is read from the 123 command (not hardcoded to A)."""
    out = D.classify_ground_item(7, _itemball_event(letter="B"), _ITEM_CTX)
    assert out is not None
    assert f"setflag({self_switch_flag_name(7, 6, 'B')})" in out


def test_ground_item_single_page() -> None:
    """A pickup with no gate page emits only the page-1 block."""
    out = D.classify_ground_item(7, _itemball_event(gate_pages=0), _ITEM_CTX)
    assert out is not None
    assert "Page1" in out and "Page2" not in out


def test_ground_item_no_context_falls_through() -> None:
    """Without an item map the symbol can't be resolved → defer to the LLM."""
    assert D.classify_ground_item(7, _itemball_event(), None) is None
    assert D.classify_ground_item(7, _itemball_event(), D.Context()) is None


def test_ground_item_unknown_symbol_falls_through() -> None:
    """An item symbol absent from the map → fall through, never a bad constant."""
    assert D.classify_ground_item(7, _itemball_event(symbol="NUCLEARGEM"), _ITEM_CTX) is None


def test_ground_item_non_itemball_script_falls_through() -> None:
    """A script-type 111 that isn't pbItemBall (e.g. a trainer battle) → None."""
    ev = _event(
        _page(
            _cmd(D.CONDITIONAL_BRANCH, 12, "pbTrainerBattle(PBTrainers::YOUNGSTER, \"Joey\")"),
            _cmd(D.CONTROL_SELF_SWITCH, "A", 0),
        ),
        id=6,
    )
    assert D.classify_ground_item(7, ev, _ITEM_CTX) is None


def test_ground_item_non_action_button_falls_through() -> None:
    """A non-talk trigger (autorun/parallel) is not the pickup idiom → None."""
    page1 = _page(
        _cmd(D.CONDITIONAL_BRANCH, 12, "Kernel.pbItemBall(::PBItems::HPUP)"),
        _cmd(D.CONTROL_SELF_SWITCH, "A", 0),
        trigger=3,
    )
    assert D.classify_ground_item(7, _event(page1, _page(), id=6), _ITEM_CTX) is None


def test_ground_item_extra_command_falls_through() -> None:
    """Dialogue or any non-scaffolding command alongside the pickup → defer to LLM."""
    ev = _event(
        _page(
            _cmd(D.CONDITIONAL_BRANCH, 12, "Kernel.pbItemBall(::PBItems::HPUP)"),
            _text("You found something!"),
            _cmd(D.CONTROL_SELF_SWITCH, "A", 0),
        ),
        _page(),
        id=6,
    )
    assert D.classify_ground_item(7, ev, _ITEM_CTX) is None


def test_ground_item_nonempty_gate_page_falls_through() -> None:
    """A gate page that carries real commands is not the empty post-pickup page → None."""
    ev = _event(
        _page(
            _cmd(D.CONDITIONAL_BRANCH, 12, "Kernel.pbItemBall(::PBItems::HPUP)"),
            _cmd(D.CONTROL_SELF_SWITCH, "A", 0),
        ),
        _page(_text("Still here.")),
        id=6,
    )
    assert D.classify_ground_item(7, ev, _ITEM_CTX) is None


def test_ground_item_dispatch() -> None:
    """try_deterministic routes a pickup to the ground-item classifier (ctx required)."""
    result = D.try_deterministic(7, _itemball_event(), _ITEM_CTX)
    assert result is not None
    assert "giveitem(ITEM_HP_UP, 1)" in result.script
    assert result.unhandled == []


@pytest.mark.phase4
@pytest.mark.skipif(not poryscript.is_available(), reason="poryscript binary not installed")
def test_ground_item_output_compiles() -> None:
    """A representative ground-item output compiles through poryscript."""
    out = D.classify_ground_item(7, _itemball_event(), _ITEM_CTX)
    assert out is not None
    result = poryscript.compile_script(out)
    assert result.ok, result.stderr


# -- differential validation vs the frozen-Opus oracle (invariant 4) ----------

_BUILD = Path("output/uranium-build")
_ITEM_TOK = re.compile(r"ITEM_[A-Z0-9_]+")


def _norm_items(block: str) -> str:
    """Collapse every ``ITEM_*`` constant to a placeholder.

    Frozen-Opus is an UNRELIABLE oracle for Uranium item names — it guesses the
    vanilla spelling (e.g. ``ITEM_PARALYZE_HEAL``) where Phase 2 emitted Uranium's
    own (``ITEM_PARLYZ_HEAL`` from display name "Parlyz Heal"). So the differential
    validates structure/labels/counts against Opus while item spellings are checked
    separately against the Phase-2 source of truth (`test_emitted_item_constants_are_real`)."""
    return _ITEM_TOK.sub("ITEM_*", block)


def _blocks_by_label(text: str) -> dict[str, str]:
    """Map each top-level ``<kw> <label> { ... }`` block (script/mart/movement/…)
    to its (line-rstripped) text."""
    out: dict[str, str] = {}
    label: str | None = None
    cur: list[str] = []
    for line in text.split("\n"):
        if label is None:
            m = re.match(r"^(?:script|mart|movement|text|raw)\s+(\S+)\s*\{", line)
            if m:
                label, cur = m.group(1), [line.rstrip()]
        else:
            cur.append(line.rstrip())
            if line.strip() == "}":
                out[label] = "\n".join(cur)
                label = None
    return out


def _differential(classify) -> int:
    """Run `classify` over every `.done` map and assert each block it claims
    reproduces the frozen-Opus .pory byte-for-byte (iterative roadmap invariant 4).

    The reliable oracle is the set of maps with a `.done` checkpoint (a `.partial`
    map — paused mid-conversion — has gaps that are absent, not divergent).
    `pytest.skip`s when the gitignored corpus/oracle isn't on disk; otherwise
    returns the number of blocks validated."""
    checkpoints, maps_dir, scripts_dir = _BUILD / "checkpoints", _BUILD / "maps", _BUILD / "scripts"
    if not (checkpoints.is_dir() and maps_dir.is_dir() and scripts_dir.is_dir()):
        pytest.skip("on-disk corpus/oracle absent (output/ is gitignored)")
    ctx = D.load_context(reference_dir=Path("reference"), intermediate_dir=_BUILD / "intermediate")
    if not ctx.items:
        pytest.skip("item sidecars absent — classifier inert")
    done = sorted(int(p.stem[3:]) for p in checkpoints.glob("Map*.done"))
    checked = 0
    for mid in done:
        mp, po = maps_dir / f"Map{mid:03d}.json", scripts_dir / f"Map{mid:03d}.pory"
        if not mp.is_file() or not po.is_file():
            continue
        oracle = _blocks_by_label(po.read_text(encoding="utf-8"))
        data = json.loads(mp.read_text(encoding="utf-8"))
        for ev in data.get("events", []):
            out = classify(mid, ev, ctx)
            if out is None:
                continue
            for label, block in _blocks_by_label(out).items():
                assert label in oracle, f"Map{mid:03d}: {label} not in frozen-Opus oracle"
                assert _norm_items(block) == _norm_items(oracle[label]), (
                    f"Map{mid:03d}: {label} diverges from frozen-Opus (structure)"
                )
                checked += 1
    return checked


def test_ground_item_differential_vs_frozen_opus() -> None:
    assert _differential(D.classify_ground_item) > 0, "no ground items validated"


# ----------------------------------------------------------------------------
# Classifier 9 — Poké Mart / pbPokemonMart (iterative roadmap Group 1 Step 2)
# ----------------------------------------------------------------------------

_MART_CTX = D.Context(items={"POKeBALL": "ITEM_POKE_BALL", "POTION": "ITEM_POTION",
                             "ANTIDOTE": "ITEM_ANTIDOTE"})


def _mart_event(*calls: str, id: int = 2, name: str = "EV002") -> dict:
    """A mart event whose page 1 is a 355 + 655-continuation pbPokemonMart run."""
    cmds = [_cmd(D.SCRIPT, calls[0])]
    cmds += [_cmd(D.SCRIPT_CONT, c) for c in calls[1:]]
    return _event(_page(*cmds), id=id, name=name)


def test_pokemart_golden_output() -> None:
    """Matches frozen-Opus (Map004 EV002): pokemart(label) script + mart block."""
    ev = _mart_event(
        "pbPokemonMart([", "PBItems::POKeBALL,", "PBItems::POTION,", "PBItems::ANTIDOTE", "])",
    )
    out = D.classify_pokemart(4, ev, _MART_CTX)
    expected = (
        "script Map004_EV002_Page1 {\n"
        "    lock\n"
        "    faceplayer\n"
        "    pokemart(Map004_EV002_Mart)\n"
        "    release\n"
        "    end\n"
        "}\n\n"
        "mart Map004_EV002_Mart {\n"
        "    ITEM_POKE_BALL\n"
        "    ITEM_POTION\n"
        "    ITEM_ANTIDOTE\n"
        "}"
    )
    assert out == expected


def test_pokemart_accepts_double_colon_prefix() -> None:
    """Both ::PBItems::X and PBItems::X spellings resolve."""
    ev = _mart_event("pbPokemonMart([::PBItems::POTION])")
    out = D.classify_pokemart(4, ev, _MART_CTX)
    assert out is not None and "ITEM_POTION" in out


def test_pokemart_no_context_falls_through() -> None:
    ev = _mart_event("pbPokemonMart([PBItems::POTION])")
    assert D.classify_pokemart(4, ev, None) is None
    assert D.classify_pokemart(4, ev, D.Context()) is None


def test_pokemart_unresolved_item_falls_through() -> None:
    """An item absent from the map → fall through, never a bad constant."""
    ev = _mart_event("pbPokemonMart([PBItems::MYSTERYORB])")
    assert D.classify_pokemart(4, ev, _MART_CTX) is None


def test_pokemart_extra_command_falls_through() -> None:
    """Dialogue/choice alongside the mart call (the shopkeeper-prompt variant) → LLM."""
    ev = _event(
        _page(_text("Buy something?"), _cmd(D.SCRIPT, "pbPokemonMart([PBItems::POTION])")),
        id=2,
    )
    assert D.classify_pokemart(4, ev, _MART_CTX) is None


def test_pokemart_non_mart_script_falls_through() -> None:
    ev = _mart_event("pbPokeCenterPC")
    assert D.classify_pokemart(4, ev, _MART_CTX) is None


def test_pokemart_dispatch() -> None:
    ev = _mart_event("pbPokemonMart([PBItems::POTION])")
    result = D.try_deterministic(4, ev, _MART_CTX)
    assert result is not None
    assert "pokemart(Map004_EV002_Mart)" in result.script


@pytest.mark.phase4
@pytest.mark.skipif(not poryscript.is_available(), reason="poryscript binary not installed")
def test_pokemart_output_compiles() -> None:
    """A representative mart output compiles through poryscript."""
    ev = _mart_event("pbPokemonMart([", "PBItems::POKeBALL,", "PBItems::POTION", "])")
    out = D.classify_pokemart(4, ev, _MART_CTX)
    assert out is not None
    result = poryscript.compile_script(out)
    assert result.ok, result.stderr


def test_pokemart_differential_vs_frozen_opus() -> None:
    assert _differential(D.classify_pokemart) > 0, "no mart events validated"


def test_emitted_item_constants_are_real() -> None:
    """Every ITEM_* the item classifiers emit across `.done` maps must be a real
    Phase-2 constant (a key in item_field_codes.json) — the authoritative oracle
    for Uranium item names, vs frozen-Opus's vanilla guesses (invariant 4)."""
    checkpoints, maps_dir = _BUILD / "checkpoints", _BUILD / "maps"
    codes = _BUILD / "intermediate" / "item_field_codes.json"
    if not (checkpoints.is_dir() and maps_dir.is_dir() and codes.is_file()):
        pytest.skip("on-disk corpus/Phase-2 output absent (output/ is gitignored)")
    ctx = D.load_context(reference_dir=Path("reference"), intermediate_dir=_BUILD / "intermediate")
    if not ctx.items:
        pytest.skip("item sidecars absent — classifiers inert")
    real = set(json.loads(codes.read_text(encoding="utf-8")).keys())
    checked = 0
    for mid in sorted(int(p.stem[3:]) for p in checkpoints.glob("Map*.done")):
        mp = maps_dir / f"Map{mid:03d}.json"
        if not mp.is_file():
            continue
        for ev in json.loads(mp.read_text(encoding="utf-8")).get("events", []):
            for fn in (D.classify_ground_item, D.classify_pokemart):
                out = fn(mid, ev, ctx)
                if out is None:
                    continue
                for tok in _ITEM_TOK.findall(out):
                    assert tok in real, f"Map{mid:03d}: {tok} not a Phase-2 item constant"
                    checked += 1
    assert checked > 0, "no item constants validated — corpus out of sync?"
