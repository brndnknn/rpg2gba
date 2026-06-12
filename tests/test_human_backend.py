"""Tests for the interactive HumanBackend (hand-conversion pass)."""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.conversion_agent import orchestrator as orch
from rpg2gba.conversion_agent import poryscript
from rpg2gba.conversion_agent.backends import EventDeferred
from rpg2gba.conversion_agent.backends.human import HumanBackend
from rpg2gba.conversion_agent.flag_registry import FlagRegistry

_REFERENCE = Path(__file__).resolve().parent.parent / "reference"


def _backend(lines, sink=None, quickref=""):
    """A HumanBackend whose input() yields `lines` in order and output() appends to `sink`."""
    it = iter(lines)

    def _input(prompt: str = "") -> str:
        try:
            return next(it)
        except StopIteration:  # ran out of scripted input → behave like Ctrl-D
            raise EOFError from None

    out = sink.append if sink is not None else (lambda _s: None)
    return HumanBackend("SYS", quickref=quickref, input_fn=_input, output_fn=out)


_EVENT = {
    "map_id": 190,
    "id": 28,
    "name": "EV028",
    "pages": [
        {
            "trigger": 3,
            "condition": {},
            "list": [
                {"code": 101, "indent": 0, "parameters": ["Hello"]},
                {"code": 123, "indent": 0, "parameters": ["A", 0]},
                {"code": 0, "indent": 0, "parameters": []},
            ],
        }
    ],
}


def test_typed_script_is_returned():
    be = _backend([
        "script Map190_EV028_Page1 {",
        "    msgbox(\"Hello\")",
        "    setflag(FLAG_MAP190_EVENT028_SSA)",
        "    end",
        "}",
        "EOF",
    ])
    result = be.convert_event(_EVENT, {}, "user prompt")
    assert "script Map190_EV028_Page1" in result.script
    assert "setflag(FLAG_MAP190_EVENT028_SSA)" in result.script
    assert result.new_flags == [] and result.new_vars == []
    assert result.unhandled == []


def test_opus_punts_with_event_deferred():
    be = _backend(["opus"])
    with pytest.raises(EventDeferred):
        be.convert_event(_EVENT, {}, "prompt")


def test_quit_and_eof_end_session():
    with pytest.raises(KeyboardInterrupt):
        _backend(["quit"]).convert_event(_EVENT, {}, "prompt")
    with pytest.raises(KeyboardInterrupt):
        _backend([]).convert_event(_EVENT, {}, "prompt")  # immediate EOF


def test_question_mark_shows_quickref_not_event_or_system():
    # `?` shows the compact quickref — NOT the per-event user prompt (event JSON) and
    # NOT the giant system prompt.
    sink: list[str] = []
    qr = "## Codes\n111 if branch -> if (...) {"
    be = _backend(["?", "x", "EOF"], sink=sink, quickref=qr)
    result = be.convert_event(_EVENT, {}, "USER-PROMPT-WITH-JSON")
    blob = "\n".join(sink)
    assert "111 if branch" in blob  # quickref shown
    assert "USER-PROMPT-WITH-JSON" not in blob  # not the event JSON
    assert "SYS" not in blob  # not the system prompt
    assert result.script == "x"


def test_question_mark_term_filters_quickref():
    sink: list[str] = []
    qr = "101 show text -> msgbox\n111 if branch -> if\n123 selfswitch -> setflag"
    be = _backend(["?111", "EOF"], sink=sink, quickref=qr)
    be.convert_event(_EVENT, {}, "p")
    blob = "\n".join(sink)
    assert "111 if branch" in blob  # matching line kept
    assert "101 show text" not in blob  # non-matching line filtered out


def test_question_mark_no_match_reports_it():
    sink: list[str] = []
    be = _backend(["?zzz", "EOF"], sink=sink, quickref="101 show text -> msgbox")
    be.convert_event(_EVENT, {}, "p")
    assert any("no quickref line matches" in s for s in sink)


def test_ref_lookup_midscript_preserves_typed_lines():
    # A `?` lookup partway through typing must NOT discard the script or become part of it.
    be = _backend(
        ["script S {", "?item", "  end", "}", "EOF"], quickref="giveitem(ITEM_X, 1)"
    )
    result = be.convert_event(_EVENT, {}, "p")
    assert "script S {" in result.script and "end" in result.script
    assert "?item" not in result.script


def test_render_never_exceeds_45_columns():
    long_event = {
        "map_id": 5,
        "id": 9,
        "name": "A very long event name that would overflow a phone screen for sure",
        "pages": [{
            "trigger": 0,
            "condition": {},
            "list": [
                {"code": 101, "indent": 0, "parameters": [
                    "This is a very long line of dialogue that absolutely must be "
                    "wrapped so it does not spill onto a second physical line."]},
                {"code": 0, "indent": 0, "parameters": []},
            ],
        }],
    }
    sink: list[str] = []
    _backend(["EOF"], sink=sink).convert_event(long_event, {}, "p")
    rendered = next(s for s in sink if "PAGE 1" in s)
    assert all(len(line) <= 45 for line in rendered.split("\n"))


def test_render_shows_minted_flag_and_label_prefix():
    sink: list[str] = []
    be = _backend(["EOF"], sink=sink)
    be.convert_event(_EVENT, {}, "prompt")
    blob = "\n".join(sink)
    assert "FLAG_MAP190_EVENT028_SSA" in blob  # self-switch handed to the operator
    assert "Map190_EV028_Page<n>" in blob  # label prefix handed to the operator


def test_unhandled_breadcrumb_is_scraped():
    be = _backend([
        "script S {",
        "    # UNHANDLED: weird Uranium call here",
        "    end",
        "}",
        "EOF",
    ])
    result = be.convert_event(_EVENT, {}, "prompt")
    assert len(result.unhandled) == 1
    assert "weird Uranium call" in result.unhandled[0]["description"]


def test_retry_surfaces_compiler_error():
    sink: list[str] = []
    be = _backend(["EOF"], sink=sink)
    retry_prompt = "base\n\n# Previous attempt failed to compile\n\nsome stderr text"
    be.convert_event(_EVENT, {}, retry_prompt)
    assert any("did not compile" in s and "some stderr text" in s for s in sink)


def test_control_words_work_midscript():
    # `opus`/`q` now work at ANY point (the old "only before the first line" gate is gone),
    # so you can bail out partway through typing a script.
    with pytest.raises(EventDeferred):
        _backend(["script S {", "opus"]).convert_event(_EVENT, {}, "p")
    with pytest.raises(KeyboardInterrupt):
        _backend(["script S {", "q"]).convert_event(_EVENT, {}, "p")


def test_undo_drops_last_line():
    be = _backend(["good line", "OOPS typo", ":undo", "second good", "EOF"])
    result = be.convert_event(_EVENT, {}, "p")
    assert result.script == "good line\nsecond good"  # the typo line was dropped


def test_undo_with_nothing_typed_is_safe():
    sink: list[str] = []
    be = _backend([":undo", "x", "EOF"], sink=sink)
    result = be.convert_event(_EVENT, {}, "p")
    assert result.script == "x"
    assert any("nothing to undo" in s for s in sink)


def test_clear_restarts_the_script():
    be = _backend(["line one", "line two", ":clear", "fresh", "EOF"])
    result = be.convert_event(_EVENT, {}, "p")
    assert result.script == "fresh"


def test_colon_done_submits_like_eof():
    be = _backend(["only line", ":done"])
    result = be.convert_event(_EVENT, {}, "p")
    assert result.script == "only line"


def _ok_compile(script: str) -> poryscript.CompileResult:
    return poryscript.CompileResult(ok=True, stdout="", stderr="")


def test_punt_propagates_and_is_not_queued(tmp_path):
    """convert_single must re-raise a human punt (EventDeferred) and write NOTHING to the
    unhandled queue, the memo, or a checkpoint — the bulk run owns the event instead."""
    out = tmp_path / "out"
    o = orch.Orchestrator(
        _backend(["opus"]), FlagRegistry(), out, reference_dir=_REFERENCE, compile_fn=_ok_compile
    )
    with pytest.raises(EventDeferred):
        o.convert_single(190, _EVENT)
    assert not (out / "unhandled.jsonl").exists()  # punt is never a queue entry
    assert o._memo == {}  # nothing memoized


def test_accepted_conversion_seeds_memo(tmp_path):
    """An accepted hand conversion lands in the memo so the bulk run reuses it for free."""
    out = tmp_path / "out"
    lines = ["script Map190_EV028_Page1 {", "  end", "}", "EOF"]
    o = orch.Orchestrator(
        _backend(lines), FlagRegistry(), out, reference_dir=_REFERENCE, compile_fn=_ok_compile
    )
    script = o.convert_single(190, _EVENT)
    assert script is not None and "Map190_EV028_Page1" in script
    assert o._memo  # memoized for twin reuse
