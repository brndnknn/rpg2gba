"""ON_FRAME re-arm pass: `metadata_wiring.insert_onframe_rearms` and its staging
wiring in `stage_slice_scripts._onframe_guard_symbols` / the staged-text
regression belt.

RMXP autorun (trigger=3) page conditions are re-evaluated every frame,
forever. Our `<Dir>_OnFrame` dispatcher approximates that but latches
`VAR_TEMP_C=1` once nothing matches, to stop per-frame dispatch for the rest
of the map visit. That latch goes stale when a NON-dispatched script later
writes a symbol one of the map's autorun guards reads — e.g. Map050's quiz
autorun is guarded on `!flag(FLAG_MAP050_EVENT005_SSD)`; the professor's
interactive retake script (`Map050_EV005_Page3`) clears that same flag,
expecting the autorun to reconsider itself, but nothing re-arms `VAR_TEMP_C`
so it never fires again. `insert_onframe_rearms` fixes this by inserting a
`setvar(VAR_TEMP_C, 0)` immediately after every guard-input write in a map's
page scripts (never inside the OnFrame dispatcher itself, and never inside
`movement`/`text`/`mapscripts` blocks).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# scripts/ is not a package — import stage_slice_scripts the same way
# test_map_scripts.py / test_conversion_agent.py do.
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from rpg2gba.tileset_converter import metadata_wiring as mw  # noqa: E402

import stage_slice_scripts as sss  # noqa: E402

_REARM = mw.ONFRAME_REARM_LINE


# --- insert_onframe_rearms: flag writes -------------------------------------


def test_insert_rearm_after_flag_write() -> None:
    text = """\
script Map099_EV001_Page3 {
    msgbox("hi")
    clearflag(FLAG_MAP099_EVENT001_SSD)
    release
}
"""
    out = mw.insert_onframe_rearms(text, {"FLAG_MAP099_EVENT001_SSD"}, set())
    lines = out.splitlines()
    idx = lines.index("    clearflag(FLAG_MAP099_EVENT001_SSD)")
    assert lines[idx + 1] == f"    {_REARM}"


def test_insert_rearm_after_setflag_write() -> None:
    text = """\
script Map099_EV001_Page3 {
    setflag(FLAG_MAP099_EVENT001_SSB)
}
"""
    out = mw.insert_onframe_rearms(text, {"FLAG_MAP099_EVENT001_SSB"}, set())
    lines = out.splitlines()
    idx = lines.index("    setflag(FLAG_MAP099_EVENT001_SSB)")
    assert lines[idx + 1] == f"    {_REARM}"


# --- insert_onframe_rearms: var writes --------------------------------------


def test_insert_rearm_after_setvar_write() -> None:
    text = """\
script Foo {
    setvar(VAR_QUEST_LOG, 2)
}
"""
    out = mw.insert_onframe_rearms(text, set(), {"VAR_QUEST_LOG"})
    lines = out.splitlines()
    idx = lines.index("    setvar(VAR_QUEST_LOG, 2)")
    assert lines[idx + 1] == f"    {_REARM}"


def test_insert_rearm_after_addvar_and_copyvar_writes() -> None:
    text = """\
script Foo {
    addvar(VAR_QUEST_LOG, 1)
    copyvar(VAR_QUEST_LOG, VAR_RESULT)
}
"""
    out = mw.insert_onframe_rearms(text, set(), {"VAR_QUEST_LOG"})
    lines = out.splitlines()
    assert lines[lines.index("    addvar(VAR_QUEST_LOG, 1)") + 1] == f"    {_REARM}"
    assert lines[lines.index("    copyvar(VAR_QUEST_LOG, VAR_RESULT)") + 1] == f"    {_REARM}"


# --- idempotence -------------------------------------------------------------


def test_insert_rearm_idempotent() -> None:
    text = """\
script Foo {
    clearflag(FLAG_X)
}
"""
    once = mw.insert_onframe_rearms(text, {"FLAG_X"}, set())
    twice = mw.insert_onframe_rearms(once, {"FLAG_X"}, set())
    assert once == twice
    assert once.count(_REARM) == 1


# --- non-guard writes untouched ----------------------------------------------


def test_unrelated_flag_write_untouched() -> None:
    text = """\
script Foo {
    setflag(FLAG_UNRELATED)
}
"""
    out = mw.insert_onframe_rearms(text, {"FLAG_SOMETHING_ELSE"}, set())
    assert out == text


def test_unrelated_var_write_untouched() -> None:
    text = """\
script Foo {
    setvar(VAR_UNRELATED, 1)
}
"""
    out = mw.insert_onframe_rearms(text, set(), {"VAR_SOMETHING_ELSE"})
    assert out == text


# --- movement/text blocks never mutated --------------------------------------


def test_movement_block_untouched() -> None:
    text = """\
script Foo {
    applymovement(1, Foo_Move1)
}

movement Foo_Move1 {
    setflag(FLAG_X)
}
"""
    out = mw.insert_onframe_rearms(text, {"FLAG_X"}, set())
    assert out == text


def test_text_block_untouched() -> None:
    text = """\
script Foo {
    msgbox(Foo_Text1)
}

text Foo_Text1 {
    "setflag(FLAG_X) is just words in a string here\\p"
}
"""
    out = mw.insert_onframe_rearms(text, {"FLAG_X"}, set())
    assert out == text


def test_mapscripts_block_untouched() -> None:
    text = """\
mapscripts Foo_MapScripts {
    MAP_SCRIPT_ON_FRAME_TABLE {
        setvar(VAR_X, 0)
    }
}
"""
    out = mw.insert_onframe_rearms(text, set(), {"VAR_X"})
    assert out == text


# --- _OnFrame dispatcher itself never re-arms its own body -------------------


def test_onframe_script_skipped() -> None:
    text = """\
script Foo_OnFrame {
    if (flag(FLAG_X)) {
        goto(Map099_EV001_Page1)
    }
    setvar(VAR_TEMP_C, 1)
}
"""
    out = mw.insert_onframe_rearms(text, {"FLAG_X"}, set())
    assert out == text


# --- indentation preserved inside nested if/switch blocks --------------------


def test_indentation_preserved_in_nested_if() -> None:
    text = """\
script Map050_EV005_Page3 {
    lock
    if (var(VAR_RESULT) == 1) {
        setflag(FLAG_MAP050_EVENT005_SSB)
        clearflag(FLAG_MAP050_EVENT005_SSD)
    } else {
        msgbox("no")
    }
    release
    end
}
"""
    out = mw.insert_onframe_rearms(
        text, {"FLAG_MAP050_EVENT005_SSB", "FLAG_MAP050_EVENT005_SSD"}, set()
    )
    lines = out.splitlines()
    b_idx = lines.index("        setflag(FLAG_MAP050_EVENT005_SSB)")
    assert lines[b_idx + 1] == f"        {_REARM}"
    d_idx = lines.index("        clearflag(FLAG_MAP050_EVENT005_SSD)")
    assert lines[d_idx + 1] == f"        {_REARM}"
    # else-branch and everything outside the if is untouched
    assert '        msgbox("no")' in lines
    assert "    release" in lines


# --- stage_slice_scripts._onframe_guard_symbols ------------------------------


def test_onframe_guard_symbols_extracts_flags_and_vars() -> None:
    dispatch = """\
script Map050_OnFrame {
    if (!flag(FLAG_MAP050_EVENT005_SSC) && !flag(FLAG_MAP050_EVENT005_SSD) \
&& var(VAR_QUEST_LOG) >= 1) {
        goto(Map050_EV005_Page1)
    }
    setvar(VAR_TEMP_C, 1)
}
"""
    flags, variables = sss._onframe_guard_symbols(dispatch)
    assert flags == {"FLAG_MAP050_EVENT005_SSC", "FLAG_MAP050_EVENT005_SSD"}
    assert variables == {"VAR_QUEST_LOG"}


def test_onframe_guard_symbols_excludes_quiescence_var() -> None:
    dispatch = """\
script Map050_OnFrame {
    if (var(VAR_TEMP_C) >= 0) {
        goto(Map050_EV005_Page1)
    }
    setvar(VAR_TEMP_C, 1)
}
"""
    flags, variables = sss._onframe_guard_symbols(dispatch)
    assert "VAR_TEMP_C" not in variables


def test_onframe_guard_symbols_no_onframe_block_is_empty() -> None:
    dispatch = """\
script Map050_EV001_Dispatch {
    if (flag(FLAG_X)) {
        goto(Map050_EV001_Page2)
    }
    goto(Map050_EV001_Page1)
}
"""
    flags, variables = sss._onframe_guard_symbols(dispatch)
    assert flags == set()
    assert variables == set()


# --- integration-flavored: Map050 quiz/retake fixture ------------------------


def test_map050_retake_script_gets_rearm_after_ssd_clear() -> None:
    """Fixture mimicking the real Map050_EV005 quiz/retake shape (see
    output/uranium-build/scripts/Map050.pory): the quiz autorun's OnFrame
    guard reads FLAG_MAP050_EVENT005_SSD (among others); the professor's
    interactive retake script (Page3) clears that flag expecting the autorun
    to reconsider itself. Verifies the full staging-path plumbing —
    `_onframe_guard_symbols` deriving the guard set from the dispatcher text,
    then `insert_onframe_rearms` applying it to the map's page scripts —
    reproduces the fix end to end."""
    dispatch = """\
script Map050_OnFrame {
    if (!flag(FLAG_MAP050_EVENT005_SSC) && !flag(FLAG_MAP050_EVENT005_SSD)) {
        goto(Map050_EV005_Page1)
    }
    setvar(VAR_TEMP_C, 1)
}
"""
    map_pory = """\
script Map050_EV005_Page3 {
    lock
    faceplayer
    msgbox(format("ready?"))
    yesnobox(0, 0)
    if (var(VAR_RESULT) == 1) {
        delay(8)
        applymovement(OBJ_EVENT_ID_PLAYER, Map050_EV005_Page3_Move1)
        waitmovement(0)
        delay(8)
        setflag(FLAG_MAP050_EVENT005_SSB)
        clearflag(FLAG_MAP050_EVENT005_SSD)
    } else {
        msgbox(format("later"))
    }
    release
    end
}
"""
    guard_flags, guard_vars = sss._onframe_guard_symbols(dispatch)
    out = mw.insert_onframe_rearms(map_pory, guard_flags, guard_vars)
    lines = out.splitlines()
    d_idx = lines.index("        clearflag(FLAG_MAP050_EVENT005_SSD)")
    assert lines[d_idx + 1] == f"        {_REARM}"
    # regression belt: re-applying must be a no-op
    assert mw.insert_onframe_rearms(out, guard_flags, guard_vars) == out
