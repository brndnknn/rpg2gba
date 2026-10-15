"""Tests for `rpg2gba.slice_growth` -- the newly-live out-of-slice-warp
detector (`REDERIVATION_PLAN.md` step P2 / A5).

`metadata_wiring.classify_event` skips an event wholesale on any code-201
transfer to a then-out-of-slice map. This module answers, per gated chapter,
which of its own events had such a transfer whose target has since joined
`SLICE_MAP_IDS` -- CH03's B25 and CH04's B7 are the two real bugs this
would have caught.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba import slice_growth
from rpg2gba.slice_growth import (
    ChapterSlice,
    SliceGrowthError,
    find_slice_growth_events,
    gated_chapter_slices,
)

BUILD_MAPS = Path("output/uranium-build/maps")


def _write_chapters_json(tmp_path: Path, chapters: list[dict]) -> Path:
    path = tmp_path / "chapters.json"
    path.write_text(json.dumps({"chapters": chapters}), encoding="utf-8")
    return path


def _chapter(chapter_id: str, maps: list[int], status: str = "built") -> dict:
    return {"id": chapter_id, "maps": maps, "status": status}


def _event(event_id: int, name: str, transfers: list[tuple[int, int, int]]) -> dict:
    """One event, one page, with a code-201 transfer per entry in `transfers`
    (each `(dest_map, x, y)`)."""
    cmds = [
        {"code": 201, "parameters": [0, dest, x, y, 0]} for dest, x, y in transfers
    ]
    return {
        "id": event_id,
        "name": name,
        "x": 0,
        "y": 0,
        "pages": [{"trigger": 2, "list": cmds}],
    }


# --- gated_chapter_slices: cumulative union + fail-loud reconciliation -------


def test_cumulative_slice_is_union_in_build_order(tmp_path: Path) -> None:
    path = _write_chapters_json(
        tmp_path,
        [_chapter("CH01", [1, 2]), _chapter("CH02", [3])],
    )
    slices = gated_chapter_slices(path, current_slice_ids=[1, 2, 3])
    assert [s.chapter_id for s in slices] == ["CH01", "CH02"]
    assert slices[0].authoring_slice == frozenset({1, 2})
    assert slices[1].authoring_slice == frozenset({1, 2, 3})


def test_planned_chapters_are_excluded(tmp_path: Path) -> None:
    path = _write_chapters_json(
        tmp_path,
        [_chapter("CH01", [1]), _chapter("CH02", [2], status="planned")],
    )
    slices = gated_chapter_slices(path, current_slice_ids=[1])
    assert [s.chapter_id for s in slices] == ["CH01"]


def test_in_progress_chapter_reconciles_but_is_not_gated(tmp_path: Path) -> None:
    """An `in_progress` chapter's maps are in SLICE_MAP_IDS (it must build
    before its §9 gate -- CH05's lifecycle, CH06 now), so they count toward
    reconciliation; but no ChapterSlice is produced for it, so the detector
    never scans warps still being authored."""
    path = _write_chapters_json(
        tmp_path,
        [_chapter("CH01", [1]), _chapter("CH02", [2, 3], status="in_progress")],
    )
    slices = gated_chapter_slices(path, current_slice_ids=[1, 2, 3])
    assert [s.chapter_id for s in slices] == ["CH01"]
    with pytest.raises(SliceGrowthError, match="does not equal"):
        gated_chapter_slices(path, current_slice_ids=[1])  # in-progress maps missing


def test_in_progress_overlapping_a_built_chapter_fails_loud(tmp_path: Path) -> None:
    path = _write_chapters_json(
        tmp_path,
        [_chapter("CH01", [1, 2]), _chapter("CH02", [2, 3], status="in_progress")],
    )
    with pytest.raises(SliceGrowthError, match="already claimed"):
        gated_chapter_slices(path, current_slice_ids=[1, 2, 3])


def test_revisit_chapter_introduces_no_maps(tmp_path: Path) -> None:
    """A revisit (`visit` > 1) re-enters a map an earlier chapter introduced;
    it is not part of the cumulative union, built or in_progress (CH07)."""
    revisit = {**_chapter("CH02", [1], status="in_progress"), "visit": 2}
    path = _write_chapters_json(tmp_path, [_chapter("CH01", [1]), revisit])
    slices = gated_chapter_slices(path, current_slice_ids=[1])
    assert [s.chapter_id for s in slices] == ["CH01"]
    built = {**revisit, "status": "built"}
    path = _write_chapters_json(tmp_path, [_chapter("CH01", [1]), built])
    assert [s.chapter_id for s in gated_chapter_slices(path, current_slice_ids=[1])] == ["CH01"]


def test_duplicate_chapter_id_uses_only_first_occurrence(tmp_path: Path) -> None:
    """CH07/CH08-style reruns of an earlier map roster later in the corpus
    must not be double-counted into the cumulative union."""
    path = _write_chapters_json(
        tmp_path,
        [_chapter("CH01", [1]), _chapter("CH02", [2]), _chapter("CH01", [1])],
    )
    slices = gated_chapter_slices(path, current_slice_ids=[1, 2])
    assert [s.chapter_id for s in slices] == ["CH01", "CH02"]


def test_mismatched_current_slice_fails_loud(tmp_path: Path) -> None:
    path = _write_chapters_json(tmp_path, [_chapter("CH01", [1, 2])])
    with pytest.raises(SliceGrowthError, match="does not equal"):
        gated_chapter_slices(path, current_slice_ids=[1, 2, 99])


def test_overlapping_chapter_maps_fail_loud(tmp_path: Path) -> None:
    path = _write_chapters_json(
        tmp_path, [_chapter("CH01", [1, 2]), _chapter("CH02", [2, 3])]
    )
    with pytest.raises(SliceGrowthError, match="already claimed"):
        gated_chapter_slices(path, current_slice_ids=[1, 2, 3])


def test_milestone_check_is_scoped_to_the_real_tracked_file(tmp_path: Path) -> None:
    """The CH01=8/CH02=10/.../CH05=18 milestones (`map_set.py` comments,
    REDERIVATION_PLAN.md) are properties of *this repo's* real
    `reference/chapters.json`, not a general rule -- a synthetic fixture with
    a differently-shaped CH01 must not be rejected just because its id
    happens to collide with a real chapter id."""
    path = _write_chapters_json(tmp_path, [_chapter("CH01", [1, 2, 3])])
    slices = gated_chapter_slices(path, current_slice_ids=[1, 2, 3])
    assert slices[0].authoring_slice == frozenset({1, 2, 3})


@pytest.mark.skipif(
    not slice_growth.DEFAULT_CHAPTERS_JSON.is_file(),
    reason="reference/chapters.json absent",
)
def test_real_chapters_json_reconciles_with_documented_milestones() -> None:
    """The actual claim in REDERIVATION_PLAN.md / map_set.py's comments:
    cumulative maps after CH01..CH05 are 8, 10, 15, 16, 18; CH06 adds maps
    41-43, 46, 47 and map 40's seven split pieces (14000-14006) -> 30. This is the
    fail-loud check `gated_chapter_slices` runs by default; here it is
    asserted directly so a drift is attributed to the milestone check, not
    buried inside some other test's failure."""
    from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS

    slices = gated_chapter_slices(current_slice_ids=SLICE_MAP_IDS)
    sizes = {s.chapter_id: len(s.authoring_slice) for s in slices}
    assert sizes == {"CH01": 8, "CH02": 10, "CH03": 15, "CH04": 16, "CH05": 18, "CH06": 30}


def test_no_built_chapters_fails_loud(tmp_path: Path) -> None:
    path = _write_chapters_json(tmp_path, [_chapter("CH01", [1], status="planned")])
    with pytest.raises(SliceGrowthError, match="no chapters"):
        gated_chapter_slices(path, current_slice_ids=[])


# --- find_slice_growth_events -------------------------------------------------


def test_finds_a_transfer_that_was_out_of_slice_then_and_in_slice_now(
    tmp_path: Path,
) -> None:
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    event = _event(4, "CaveMouth", [(999, 5, 5)])
    (maps_dir / "Map001.json").write_text(
        json.dumps({"events": [event]}), encoding="utf-8"
    )
    chapter = ChapterSlice(
        chapter_id="CH01", own_map_ids=(1,), authoring_slice=frozenset({1})
    )
    found = find_slice_growth_events(chapter, maps_dir, current_slice_ids=frozenset({1, 999}))
    assert len(found) == 1
    ref = found[0]
    assert ref.map_id == 1
    assert ref.event_id == 4
    assert ref.event_name == "CaveMouth"
    assert ref.target_map_id == 999
    assert ref.page_indices == (0,)
    assert ref.authored_status == "skip"


def test_ignores_a_transfer_still_out_of_slice(tmp_path: Path) -> None:
    """A target that has not joined the current slice yet is not "growth" --
    it is still exactly as invisible as it was at authoring time."""
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    event = _event(4, "CaveMouth", [(999, 5, 5)])
    (maps_dir / "Map001.json").write_text(
        json.dumps({"events": [event]}), encoding="utf-8"
    )
    chapter = ChapterSlice(
        chapter_id="CH01", own_map_ids=(1,), authoring_slice=frozenset({1})
    )
    found = find_slice_growth_events(chapter, maps_dir, current_slice_ids=frozenset({1}))
    assert found == []


def test_ignores_a_transfer_that_was_already_in_slice_at_authoring_time(
    tmp_path: Path,
) -> None:
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    event = _event(4, "InternalDoor", [(1, 5, 5)])
    (maps_dir / "Map001.json").write_text(
        json.dumps({"events": [event]}), encoding="utf-8"
    )
    chapter = ChapterSlice(
        chapter_id="CH01", own_map_ids=(1,), authoring_slice=frozenset({1})
    )
    found = find_slice_growth_events(chapter, maps_dir, current_slice_ids=frozenset({1}))
    assert found == []


def test_reports_only_the_pages_carrying_the_newly_live_target(tmp_path: Path) -> None:
    """A multi-page event where only some pages transfer to the newly-live
    target must report just those page indices, not every page."""
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    event = {
        "id": 7,
        "name": "GatedDoor",
        "x": 0,
        "y": 0,
        "pages": [
            {"trigger": 2, "list": [{"code": 201, "parameters": [0, 1, 1, 1, 0]}]},
            {"trigger": 2, "list": [{"code": 201, "parameters": [0, 999, 2, 2, 0]}]},
        ],
    }
    (maps_dir / "Map001.json").write_text(
        json.dumps({"events": [event]}), encoding="utf-8"
    )
    chapter = ChapterSlice(
        chapter_id="CH01", own_map_ids=(1,), authoring_slice=frozenset({1})
    )
    found = find_slice_growth_events(chapter, maps_dir, current_slice_ids=frozenset({1, 999}))
    assert len(found) == 1
    assert found[0].target_map_id == 999
    assert found[0].page_indices == (1,)


def test_missing_map_json_fails_loud(tmp_path: Path) -> None:
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    chapter = ChapterSlice(
        chapter_id="CH01", own_map_ids=(1,), authoring_slice=frozenset({1})
    )
    with pytest.raises(SliceGrowthError, match="does not exist"):
        find_slice_growth_events(chapter, maps_dir, current_slice_ids=frozenset({1}))


def test_event_with_no_transfers_is_ignored(tmp_path: Path) -> None:
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    event = {"id": 1, "name": "NPC", "x": 0, "y": 0, "pages": [{"trigger": None, "list": []}]}
    (maps_dir / "Map001.json").write_text(
        json.dumps({"events": [event]}), encoding="utf-8"
    )
    chapter = ChapterSlice(
        chapter_id="CH01", own_map_ids=(1,), authoring_slice=frozenset({1})
    )
    assert find_slice_growth_events(chapter, maps_dir, current_slice_ids=frozenset({1})) == []


# --- ChapterSliceGrowthReport.format ------------------------------------------


def test_report_format_is_clean_message_when_no_events() -> None:
    report = slice_growth.ChapterSliceGrowthReport(
        chapter_id="CH01", own_map_ids=(1,), authored_slice_size=1, current_slice_size=1
    )
    assert report.ok
    assert "clean" in report.format()


def test_report_format_lists_findings() -> None:
    ref = slice_growth.SliceGrowthEvent(
        map_id=35,
        event_id=7,
        event_name="CaveMouth",
        page_indices=(0,),
        target_map_id=36,
        authored_status="skip",
    )
    report = slice_growth.ChapterSliceGrowthReport(
        chapter_id="CH04",
        own_map_ids=(35,),
        authored_slice_size=16,
        current_slice_size=18,
        events=[ref],
    )
    assert not report.ok
    text = report.format()
    assert "Map035" in text
    assert "EV007" in text
    assert "Map036" in text


# --- integration against the real corpus (gitignored, so skipped in CI) ------


@pytest.mark.skipif(
    not BUILD_MAPS.is_dir(), reason="on-disk map corpus absent (output/ is gitignored)"
)
def test_real_gated_chapters_reconcile_and_run() -> None:
    """The detector must at least run cleanly end-to-end over the real,
    currently-gated chapters (CH01-CH06) without raising -- the substantive
    findings are reported by hand, not asserted here, since they are exactly
    what this task exists to discover."""
    reports = slice_growth.detect_slice_growth(maps_dir=BUILD_MAPS)
    assert [r.chapter_id for r in reports] == ["CH01", "CH02", "CH03", "CH04", "CH05", "CH06"]
