"""findings §3.3/§5 plumbing: `stage_slice_scripts._scan_required_actor_ids`.

Unit tests for the pre-prune `.pory` scanner that feeds `required_actor_ids`
into `metadata_wiring.build_object_events` (hidden cutscene actors). See
`reference/findings/moki_slice_story_chain_2026-07-16.md` §3.3/§5 and
`tests/test_tileset_converter.py` for the `build_object_events`-side unit
tests of the hidden-actor feature itself.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# scripts/ is not a package — import stage_slice_scripts the same way
# test_conversion_agent.py imports assemble_pathfinder.
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import stage_slice_scripts as sss  # noqa: E402


def _map_json(event_ids: list[int]) -> dict:
    return {"events": [{"id": eid} for eid in event_ids]}


def test_scan_required_actor_ids_finds_all_remap_commands() -> None:
    text = """
    script Map032_EV009_Page3 {
        applymovement(16, Map032_EV009_Page3_Move8)
        waitmovement(0)
        applymovement(2, Map032_EV009_Page3_Move9)
        setobjectxy(76, 12, 44)
        addobject(77)
        removeobject(76)
        turnobject(16, DIR_SOUTH)
    }
    """
    ids = sss._scan_required_actor_ids(text, _map_json([16, 2, 76, 77]))
    assert ids == {16, 2, 76, 77}


def test_scan_required_actor_ids_ignores_identifiers_and_strings() -> None:
    """Only bare integer literals count — OBJ_EVENT_ID_PLAYER/LOCALID_* and
    integers that merely appear inside a msgbox string or a comment must
    never register as a required actor id."""
    text = """
    script Foo {
        applymovement(OBJ_EVENT_ID_PLAYER, Foo_Move)
        msgbox("applymovement(99, x) is not a real command")
        # applymovement(50, Foo_Move) is a comment
        applymovement(16, Foo_Move)
    }
    """
    ids = sss._scan_required_actor_ids(text, _map_json([16]))
    assert ids == {16}


def test_scan_required_actor_ids_no_commands_is_empty() -> None:
    assert sss._scan_required_actor_ids("script Foo { end }", _map_json([1, 2])) == set()


def test_scan_required_actor_ids_garbage_reference_fails_loud() -> None:
    """An id targeted by applymovement/etc. that doesn't correspond to any
    event on the map at all is a garbage reference — fail loud rather than
    silently letting it through to build_object_events."""
    text = "script Foo { applymovement(999, Foo_Move) }"
    with pytest.raises(ValueError):
        sss._scan_required_actor_ids(text, _map_json([1, 2]))


def test_scan_required_actor_ids_dedups_repeated_targets() -> None:
    text = """
    script Foo {
        applymovement(16, Foo_Move)
        applymovement(16, Foo_Move2)
        turnobject(16, DIR_SOUTH)
    }
    """
    ids = sss._scan_required_actor_ids(text, _map_json([16]))
    assert ids == {16}


# --- check_onframe_deactivation -------------------------------------------
#
# ON_FRAME re-fire guard: a page an OnFrame dispatcher `goto`s must, in its
# body, write at least one FLAG_*/VAR_* symbol that also appears in the
# OnFrame guard conditions — otherwise the guard never flips and the
# dispatcher re-fires the page every frame (the Map050_EV005_Page1 bug this
# check exists to catch; see stage_slice_scripts.check_onframe_deactivation).

_DISPATCH_ONE_GOTO = """\
script SomeMap_OnFrame {
    if (var(VAR_QUEST_LOG) >= 1 && !flag(FLAG_DID_THING)) {
        goto(Map099_EV001_Page1)
    }
    setvar(VAR_TEMP_C, 1)
}
"""


def test_check_onframe_deactivation_body_writes_guard_var_passes() -> None:
    map_pory = """\
script Map099_EV001_Page1 {
    msgbox("Hello")
    setvar(VAR_QUEST_LOG, 2)
}
"""
    violations = sss.check_onframe_deactivation(
        _DISPATCH_ONE_GOTO, map_pory, source_name="Map099.pory"
    )
    assert violations == []


def test_check_onframe_deactivation_body_writes_nothing_fails() -> None:
    map_pory = """\
script Map099_EV001_Page1 {
    msgbox("Hello")
}
"""
    violations = sss.check_onframe_deactivation(
        _DISPATCH_ONE_GOTO, map_pory, source_name="Map099.pory"
    )
    assert len(violations) == 1
    assert "Map099_EV001_Page1" in violations[0]


def test_check_onframe_deactivation_body_writes_unrelated_flag_fails() -> None:
    map_pory = """\
script Map099_EV001_Page1 {
    msgbox("Hello")
    setflag(FLAG_SOME_UNRELATED_THING)
}
"""
    violations = sss.check_onframe_deactivation(
        _DISPATCH_ONE_GOTO, map_pory, source_name="Map099.pory"
    )
    assert len(violations) == 1
    assert "Map099_EV001_Page1" in violations[0]


def test_check_onframe_deactivation_body_sets_guard_flag_passes() -> None:
    map_pory = """\
script Map099_EV001_Page1 {
    msgbox("Hello")
    setflag(FLAG_DID_THING)
}
"""
    violations = sss.check_onframe_deactivation(
        _DISPATCH_ONE_GOTO, map_pory, source_name="Map099.pory"
    )
    assert violations == []


def test_check_onframe_deactivation_missing_body_fails() -> None:
    map_pory = "script Map099_EV002_Page1 {\n    msgbox(\"unrelated\")\n}\n"
    violations = sss.check_onframe_deactivation(
        _DISPATCH_ONE_GOTO, map_pory, source_name="Map099.pory"
    )
    assert len(violations) == 1
    assert "Map099_EV001_Page1" in violations[0]


def test_check_onframe_deactivation_no_onframe_block_is_empty() -> None:
    dispatch = """\
script Map099_EV001_Dispatch {
    if (flag(FLAG_DID_THING)) {
        goto(Map099_EV001_Page2)
    }
    goto(Map099_EV001_Page1)
}
"""
    violations = sss.check_onframe_deactivation(
        dispatch, "script Map099_EV001_Page1 { msgbox(\"x\") }", source_name="Map099.pory"
    )
    assert violations == []
