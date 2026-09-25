"""Tests for `rpg2gba.story_state.engine_audit` (REDERIVATION_PLAN.md §16
ruling R9, "C2 shape" (d)/(e); §16.3 C3).

Synthetic fixtures build tiny fenced C trees under `tmp_path` to exercise
fence-form/nesting/function-detection quirks without touching the real
vendored engine. A separate real-tree test asserts the two known fenced
writes (`overworld.c:410` in `DoWhiteOut`, `new_game.c:404` in
`CB2_StartUraniumSlice`) are found -- `engine/` is committed, so it never
skips.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.story_state.engine_audit import (
    AuditReport,
    audit,
    chapter_read_keys,
    fenced_state_writes,
    format_report,
    run_real_audit,
    scan_fenced_regions,
)
from rpg2gba.story_state.transitions import EngineWrite

OUT_DIR = Path("output/uranium-build")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --- fence scanning: both forms, nesting, function detection ---------------


def test_begin_end_form_is_found_with_enclosing_function(tmp_path: Path) -> None:
    src = tmp_path / "src" / "foo.c"
    _write(src, """\
void MyFunc(void)
{
    // BEGIN URANIUM PATHFINDER SLICE -- reason
    FlagSet(FLAG_FOO);
    // END URANIUM PATHFINDER SLICE
}
""")
    regions = scan_fenced_regions(tmp_path)
    assert len(regions) == 1
    assert regions[0].sentinel == "URANIUM PATHFINDER SLICE"
    assert regions[0].function == "MyFunc"
    writes = fenced_state_writes(regions)
    assert len(writes) == 1
    assert writes[0].call == "FlagSet"
    assert writes[0].constant == "FLAG_FOO"
    assert writes[0].function == "MyFunc"


def test_bare_form_is_found(tmp_path: Path) -> None:
    src = tmp_path / "src" / "bar.c"
    _write(src, """\
void OtherFunc(void)
{
    // URANIUM MAP WALKER: old-style opener
    VarSet(VAR_BAR, 1);
    // END URANIUM MAP WALKER
}
""")
    regions = scan_fenced_regions(tmp_path)
    assert len(regions) == 1
    writes = fenced_state_writes(regions)
    assert writes[0].call == "VarSet"
    assert writes[0].constant == "VAR_BAR"
    assert writes[0].value == "1"
    assert writes[0].function == "OtherFunc"


def test_write_outside_any_fence_is_ignored(tmp_path: Path) -> None:
    src = tmp_path / "src" / "baz.c"
    _write(src, """\
void F(void)
{
    FlagSet(FLAG_STOCK);
    // BEGIN URANIUM PATHFINDER SLICE -- reason
    FlagSet(FLAG_FENCED);
    // END URANIUM PATHFINDER SLICE
}
""")
    writes = fenced_state_writes(scan_fenced_regions(tmp_path))
    assert [w.constant for w in writes] == ["FLAG_FENCED"]


def test_bare_marker_skipped_over_by_a_different_sentinels_end(tmp_path: Path) -> None:
    """Mirrors the real-tree quirk at engine/src/overworld.c:1920: a bare
    one-line mention of a sentinel's name, never given its own `// END`,
    sitting inside an OUTER fence of a different sentinel. It must not
    swallow everything up to that sentinel's own later `// END`."""
    src = tmp_path / "src" / "quirk.c"
    _write(src, """\
void F(void)
{
    // BEGIN URANIUM PATHFINDER SLICE -- outer
    // URANIUM MAP WALKER: just a mention, not a real fence
    FlagSet(FLAG_INSIDE_OUTER);
    // END URANIUM PATHFINDER SLICE
    // BEGIN URANIUM MAP WALKER -- a REAL, later, properly paired fence
    FlagSet(FLAG_INSIDE_WALKER);
    // END URANIUM MAP WALKER
}
""")
    regions = scan_fenced_regions(tmp_path)
    # Exactly two real regions: the outer SLICE, and the later real WALKER.
    assert len(regions) == 2
    sentinels = sorted(r.sentinel for r in regions)
    assert sentinels == ["URANIUM MAP WALKER", "URANIUM PATHFINDER SLICE"]
    writes = fenced_state_writes(regions)
    by_constant = {w.constant: w.sentinel for w in writes}
    assert by_constant["FLAG_INSIDE_OUTER"] == "URANIUM PATHFINDER SLICE"
    assert by_constant["FLAG_INSIDE_WALKER"] == "URANIUM MAP WALKER"


def test_unclosed_bare_opener_at_eof_is_a_one_line_marker(tmp_path: Path) -> None:
    src = tmp_path / "include" / "config" / "rpg2gba.h"
    _write(src, """\
#define X 1
// URANIUM PATHFINDER SLICE: just a one-line note, never closed
#define Y 2
""")
    regions = scan_fenced_regions(tmp_path)
    assert regions == []


def test_unclosed_begin_is_malformed_and_raises(tmp_path: Path) -> None:
    src = tmp_path / "src" / "broken.c"
    _write(src, """\
void F(void)
{
    // BEGIN URANIUM PATHFINDER SLICE -- never closed
    FlagSet(FLAG_X);
}
""")
    with pytest.raises(ValueError, match="no matching '// END"):
        scan_fenced_regions(tmp_path)


def test_real_begin_skipped_over_by_mismatched_end_raises(tmp_path: Path) -> None:
    src = tmp_path / "src" / "broken2.c"
    _write(src, """\
void F(void)
{
    // BEGIN URANIUM MAP WALKER -- real fence A
    // BEGIN URANIUM PATHFINDER SLICE -- real fence B, nested
    FlagSet(FLAG_X);
    // END URANIUM MAP WALKER
}
""")
    with pytest.raises(ValueError, match="is never closed by its own"):
        scan_fenced_regions(tmp_path)


# --- audit: undeclared / missing / owed / intro gaps ------------------------


def test_undeclared_write_is_flagged(tmp_path: Path) -> None:
    src = tmp_path / "src" / "u.c"
    _write(src, """\
void F(void)
{
    // BEGIN URANIUM PATHFINDER SLICE -- reason
    FlagSet(FLAG_SURPRISE);
    // END URANIUM PATHFINDER SLICE
}
""")
    report = audit(tmp_path, flag_state={"switches": {}, "variables": {}}, intro_end_state=(), chapter_read_keys=set())
    assert len(report.undeclared_writes) == 1
    assert "FLAG_SURPRISE" in report.undeclared_writes[0].detail
    assert not report.ok


def test_declared_transition_write_is_not_undeclared(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import rpg2gba.story_state.engine_audit as ea
    from rpg2gba.story_state.transitions import EngineTransition
    from rpg2gba.story_state.state import RESPAWN_MAP, Switch, Test

    src = tmp_path / "src" / "u.c"
    _write(src, """\
void DoWhiteOut(void)
{
    // BEGIN URANIUM PATHFINDER SLICE -- reason
    FlagSet(FLAG_STARTING_OVER);
    // END URANIUM PATHFINDER SLICE
}
""")
    fake_transition = EngineTransition(
        name="whiteout", precondition=(Test(key=Switch(2), op="==", value=True),),
        writes=(), lands_on=RESPAWN_MAP,
        engine_writes=(EngineWrite("FlagSet", "FLAG_STARTING_OVER", "DoWhiteOut"),),
        source="test",
    )
    monkeypatch.setattr(ea, "TRANSITIONS", (fake_transition,))
    report = ea.audit(tmp_path, flag_state={"switches": {}, "variables": {}}, intro_end_state=(), chapter_read_keys=set())
    assert report.undeclared_writes == ()
    assert report.missing_transition_writes == ()


def test_missing_transition_write_is_flagged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import rpg2gba.story_state.engine_audit as ea
    from rpg2gba.story_state.transitions import EngineTransition
    from rpg2gba.story_state.state import RESPAWN_MAP, Switch, Test

    _write(tmp_path / "src" / "empty.c", "void F(void)\n{\n}\n")
    fake_transition = EngineTransition(
        name="whiteout", precondition=(Test(key=Switch(2), op="==", value=True),),
        writes=(), lands_on=RESPAWN_MAP,
        engine_writes=(EngineWrite("FlagSet", "FLAG_STARTING_OVER", "DoWhiteOut"),),
        source="test",
    )
    monkeypatch.setattr(ea, "TRANSITIONS", (fake_transition,))
    report = ea.audit(tmp_path, flag_state={"switches": {}, "variables": {}}, intro_end_state=(), chapter_read_keys=set())
    assert len(report.missing_transition_writes) == 1
    assert report.missing_transition_writes[0].transition == "whiteout"
    assert not report.ok


def test_owed_obligation_with_null_constant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import rpg2gba.story_state.engine_audit as ea
    from rpg2gba.story_state.transitions import EngineObligation

    _write(tmp_path / "src" / "empty.c", "void F(void)\n{\n}\n")
    fake_obligation = EngineObligation(
        name="day_night", pseudo_row_id="common/ce051", switch_ids=(105, 106), source="test")
    monkeypatch.setattr(ea, "OBLIGATIONS", (fake_obligation,))
    flag_state = {"switches": {"105": None, "106": None}, "variables": {}}
    report = ea.audit(
        tmp_path, flag_state=flag_state, intro_end_state=(), chapter_read_keys={"switch:106"})
    assert len(report.owed_obligations) == 2
    assert {o.switch_id for o in report.owed_obligations} == {105, 106}
    assert not report.ok


def test_owed_obligation_with_named_but_unwritten_constant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import rpg2gba.story_state.engine_audit as ea
    from rpg2gba.story_state.transitions import EngineObligation

    _write(tmp_path / "src" / "empty.c", "void F(void)\n{\n}\n")
    fake_obligation = EngineObligation(
        name="day_night", pseudo_row_id="common/ce051", switch_ids=(105,), source="test")
    monkeypatch.setattr(ea, "OBLIGATIONS", (fake_obligation,))
    flag_state = {"switches": {"105": "FLAG_DAY"}, "variables": {}}
    report = ea.audit(
        tmp_path, flag_state=flag_state, intro_end_state=(), chapter_read_keys={"switch:105"})
    assert len(report.owed_obligations) == 1
    assert "never written" in report.owed_obligations[0].detail


def test_obligation_nobody_reads_is_deferred_not_owed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import rpg2gba.story_state.engine_audit as ea
    from rpg2gba.story_state.transitions import EngineObligation

    _write(tmp_path / "src" / "empty.c", "void F(void)\n{\n}\n")
    fake_obligation = EngineObligation(
        name="day_night", pseudo_row_id="common/ce051", switch_ids=(105, 106), source="test")
    monkeypatch.setattr(ea, "OBLIGATIONS", (fake_obligation,))
    flag_state = {"switches": {}, "variables": {}}
    report = ea.audit(
        tmp_path, flag_state=flag_state, intro_end_state=(), chapter_read_keys={"switch:51"})
    assert report.owed_obligations == ()
    assert len(report.deferred_obligations) == 1


def test_chapter_read_keys_skips_stripped_events(tmp_path: Path) -> None:
    import json

    build_dir = tmp_path / "build"
    ref_dir = tmp_path / "reference"
    # A real chapter id is needed for the binding; take CH01's first map and
    # give it two lamp-shaped events on switch 106, one of them stripped.
    from rpg2gba.chapter_atlas.binding import load_binding

    map_id = load_binding().chapter("CH01").maps[0]
    for other in load_binding().chapter("CH01").maps[1:]:
        _write(build_dir / "maps" / f"Map{other:03d}.json", json.dumps({"events": []}))
    page = {
        "condition": {
            "switch1_valid": True, "switch1_id": 106, "switch2_valid": False, "switch2_id": 1,
            "variable_valid": False, "variable_id": 1, "variable_value": 0,
            "self_switch_valid": False, "self_switch_ch": "A",
        },
        "trigger": 0,
        "list": [{"code": 0, "indent": 0, "parameters": []}],
    }
    events = [
        {"id": 1, "name": "Luz", "x": 0, "y": 0, "pages": [page]},
        {"id": 2, "name": "Luz", "x": 1, "y": 0, "pages": [
            {**page, "condition": {**page["condition"], "switch1_id": 105}}]},
    ]
    _write(build_dir / "maps" / f"Map{map_id:03d}.json", json.dumps({"events": events}))
    _write(build_dir / "common_events.json", "[]")
    real_ref = Path("reference")
    for name in ("chapters.json", "uranium_switches.json", "uranium_variables.json"):
        _write(ref_dir / name, (real_ref / name).read_text(encoding="utf-8"))
    _write(ref_dir / "strip_list.json", json.dumps({
        "map_events": [{"map_id": map_id, "event_id": 1, "expect_name": "Luz"}]}))

    keys = chapter_read_keys(build_dir, ["CH01"], reference_dir=ref_dir)
    assert "switch:105" in keys
    assert "switch:106" not in keys


def test_intro_gap_vs_unread_vs_satisfied(tmp_path: Path) -> None:
    engine_dir = tmp_path
    _write(engine_dir / "src" / "new_game.c", """\
void CB2_StartUraniumSlice(void)
{
    // BEGIN URANIUM PATHFINDER SLICE -- reason
    FlagSet(FLAG_MUM);
    // END URANIUM PATHFINDER SLICE
}
""")
    flag_state = {
        "switches": {"52": "FLAG_MUM", "60": "FLAG_UNSEEDED", "70": None},
        "variables": {},
    }
    intro_end_state = (
        ("switch:52", (True,)),          # read, satisfied by new_game.c -> no gap
        ("switch:60", (True,)),          # read, NOT satisfied -> gap
        ("switch:70", (True,)),          # read, null constant -> gap (constant None)
        ("switch:80", (True,)),          # NOT read by any chapter row -> unread
        ("switch:90", (False,)),         # default value -> ignored entirely
        ("self_switch:51/1/A", (False,)),  # ignored kind
    )
    read_keys = {"switch:52", "switch:60", "switch:70"}
    report = audit(engine_dir, flag_state, intro_end_state, read_keys)
    gap_keys = {g.key for g in report.intro_seed_gaps}
    assert gap_keys == {"switch:60", "switch:70"}
    assert report.intro_seed_unread == ("switch:80",)
    # The FlagSet(FLAG_MUM) that satisfies the seed is declared by the seed
    # itself, so it is not an undeclared write.
    assert report.undeclared_writes == ()
    assert not report.ok


def test_format_report_smoke() -> None:
    report = AuditReport(
        undeclared_writes=(), missing_transition_writes=(), owed_obligations=(),
        intro_seed_gaps=(), intro_seed_unread=("switch:1",),
    )
    text = format_report(report)
    assert "OK" in text
    assert "switch:1" in text


# --- real-tree tests --------------------------------------------------


def test_real_engine_fenced_writes_found() -> None:
    regions = scan_fenced_regions(Path("engine"))
    writes = fenced_state_writes(regions)
    # Keyed by what the write IS, not its line number, so an unrelated engine
    # edit does not break the test.
    found = {
        (str(w.path).replace("\\", "/"), w.call, w.constant, w.function) for w in writes
    }
    assert ("engine/src/overworld.c", "FlagSet", "FLAG_STARTING_OVER", "DoWhiteOut") in found
    assert ("engine/src/new_game.c", "FlagSet", "FLAG_BADGE03_GET", "CB2_StartUraniumSlice") in found
    # Ruling 14 (2026-09-25) removed C3's FLAG_MUM seed: a fresh game takes
    # the full intro, where only Auntie sets switch 52.
    assert not [w for w in found if w[2] == "FLAG_MUM"]


@pytest.mark.skipif(not (OUT_DIR / "maps").is_dir(), reason="no converted corpus on disk")
def test_run_real_audit_is_clean() -> None:
    # Clean with no Intro seed at all since ruling 14 ($skipGameIntro is
    # statically false, so INTRO sets no in-scope key); day/night is deferred
    # because every CH01-CH05 reader of 105/106 is a stripped lamp.
    report = run_real_audit()
    assert report.ok, format_report(report)
    assert [d for d in report.deferred_obligations if "day_night" in d]
