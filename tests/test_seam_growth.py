"""Tests for `rpg2gba.seam_growth` -- the newly-crossable out-of-slice
map-connection-seam detector (`REDERIVATION_PLAN.md` step P2b / PROJECT_TODO
#91, the seam counterpart to `slice_growth`'s code-201 detector).

`connections.build_connections`'s frontier rule omits a `connections.json`
row until BOTH its endpoint maps are staged. This module answers, per gated
chapter, which rows naming one of its own maps had a target that has since
joined `SLICE_MAP_IDS` -- CH03's Kevlar Town <-> Route 2 seam (B25) is the
real bug this would have caught.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba import seam_growth
from rpg2gba.slice_growth import ChapterSlice
from rpg2gba.tileset_converter.connections import parse_connections


def _write_chapters_json(tmp_path: Path, chapters: list[dict]) -> Path:
    path = tmp_path / "chapters.json"
    path.write_text(json.dumps({"chapters": chapters}), encoding="utf-8")
    return path


def _chapter(chapter_id: str, maps: list[int], status: str = "built") -> dict:
    return {"id": chapter_id, "maps": maps, "status": status}


def _write_connections_json(tmp_path: Path, rows: list[list]) -> Path:
    path = tmp_path / "connections.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def _write_seam_warps_json(tmp_path: Path, seams: list[dict]) -> Path:
    path = tmp_path / "seam_warps.json"
    path.write_text(json.dumps({"seams": seams}), encoding="utf-8")
    return path


def _seam(seam_id: str, map_a: int, map_b: int) -> dict:
    return {
        "id": seam_id,
        "map_a": map_a,
        "map_b": map_b,
        "cells_a": [[0, 0]],
        "cells_b": [[0, 0]],
        "direction_a": "up",
        "direction_b": "down",
    }


# --- find_seam_growth_edges ---------------------------------------------------


def test_finds_a_seam_that_was_out_of_slice_then_and_in_slice_now() -> None:
    rows = parse_connections([[31, "N", 11, 35, "S", 0]])
    chapter = ChapterSlice(chapter_id="CH03", own_map_ids=(31,), authoring_slice=frozenset({31}))
    found = seam_growth.find_seam_growth_edges(chapter, rows, current_slice_ids=frozenset({31, 35}))
    assert len(found) == 1
    edge = found[0]
    assert edge.own_map_id == 31
    assert edge.own_edge == "N"
    assert edge.own_offset == 11
    assert edge.target_map_id == 35
    assert edge.target_edge == "S"
    assert edge.target_offset == 0
    assert edge.realized_as == "connection"


def test_ignores_a_seam_still_out_of_slice() -> None:
    """A target that has not joined the current slice yet is not "growth" --
    it is still exactly as invisible as it was at authoring time."""
    rows = parse_connections([[31, "N", 11, 35, "S", 0]])
    chapter = ChapterSlice(chapter_id="CH03", own_map_ids=(31,), authoring_slice=frozenset({31}))
    found = seam_growth.find_seam_growth_edges(chapter, rows, current_slice_ids=frozenset({31}))
    assert found == []


def test_ignores_a_seam_that_was_already_in_slice_at_authoring_time() -> None:
    rows = parse_connections([[31, "N", 11, 35, "S", 0]])
    chapter = ChapterSlice(chapter_id="CH03", own_map_ids=(31,), authoring_slice=frozenset({31, 35}))
    found = seam_growth.find_seam_growth_edges(chapter, rows, current_slice_ids=frozenset({31, 35}))
    assert found == []


def test_ignores_a_seam_introduced_entirely_within_the_same_chapter() -> None:
    """Both endpoints belonging to this chapter's own maps is not growth --
    `own_map_ids` is a subset of `authoring_slice` by construction."""
    rows = parse_connections([[31, "N", 11, 35, "S", 0]])
    chapter = ChapterSlice(
        chapter_id="CH03", own_map_ids=(31, 35), authoring_slice=frozenset({31, 35})
    )
    found = seam_growth.find_seam_growth_edges(chapter, rows, current_slice_ids=frozenset({31, 35}))
    assert found == []


def test_ignores_a_row_naming_neither_of_the_chapters_own_maps() -> None:
    rows = parse_connections([[142, "S", 52, 76, "N", 0]])
    chapter = ChapterSlice(chapter_id="CH03", own_map_ids=(31,), authoring_slice=frozenset({31}))
    found = seam_growth.find_seam_growth_edges(chapter, rows, current_slice_ids=frozenset({31, 142, 76}))
    assert found == []


def test_reports_realized_as_arrow_warp_when_declared() -> None:
    rows = parse_connections([[31, "N", 11, 35, "S", 0]])
    chapter = ChapterSlice(chapter_id="CH03", own_map_ids=(31,), authoring_slice=frozenset({31}))
    found = seam_growth.find_seam_growth_edges(
        chapter, rows, current_slice_ids=frozenset({31, 35}),
        realized_as={frozenset({31, 35}): "arrow_warp"},
    )
    assert len(found) == 1
    assert found[0].realized_as == "arrow_warp"


def test_own_map_can_be_the_b_side_of_the_row() -> None:
    """The row's own/target orientation must not depend on which side of the
    row (`map_a`/`map_b`) happens to be the reporting chapter's map."""
    rows = parse_connections([[35, "S", 0, 31, "N", 11]])
    chapter = ChapterSlice(chapter_id="CH03", own_map_ids=(31,), authoring_slice=frozenset({31}))
    found = seam_growth.find_seam_growth_edges(chapter, rows, current_slice_ids=frozenset({31, 35}))
    assert len(found) == 1
    assert found[0].own_map_id == 31
    assert found[0].own_edge == "N"
    assert found[0].target_map_id == 35
    assert found[0].target_edge == "S"


# --- _check_seam_warps_reference_real_rows / _realized_as_map ----------------


def test_seam_warps_naming_an_undeclared_pair_fails_loud(tmp_path: Path) -> None:
    rows = parse_connections([[31, "N", 11, 35, "S", 0]])
    realized_as = {frozenset({99, 100}): "arrow_warp"}
    with pytest.raises(seam_growth.SeamGrowthError, match="nothing to suppress"):
        seam_growth._check_seam_warps_reference_real_rows(rows, realized_as)


def test_realized_as_map_is_empty_when_seam_warps_file_absent(tmp_path: Path) -> None:
    assert seam_growth._realized_as_map(tmp_path / "does_not_exist.json") == {}


def test_realized_as_map_reads_declared_seams(tmp_path: Path) -> None:
    path = _write_seam_warps_json(tmp_path, [_seam("kevlar_route02", 31, 35)])
    result = seam_growth._realized_as_map(path)
    assert result == {frozenset({31, 35}): "arrow_warp"}


# --- ChapterSeamGrowthReport.format ------------------------------------------


def test_report_format_is_clean_message_when_no_edges() -> None:
    report = seam_growth.ChapterSeamGrowthReport(
        chapter_id="CH01", own_map_ids=(1,), authored_slice_size=1, current_slice_size=1
    )
    assert report.ok
    assert "clean" in report.format()


def test_report_format_lists_findings() -> None:
    edge = seam_growth.SeamGrowthEdge(
        own_map_id=31, own_edge="N", own_offset=11,
        target_map_id=35, target_edge="S", target_offset=0,
        realized_as="arrow_warp",
    )
    report = seam_growth.ChapterSeamGrowthReport(
        chapter_id="CH03", own_map_ids=(31,), authored_slice_size=15, current_slice_size=18,
        edges=[edge],
    )
    assert not report.ok
    text = report.format()
    assert "Map031" in text
    assert "Map035" in text
    assert "arrow_warp" in text


# --- detect_seam_growth: end-to-end over synthetic fixtures -------------------


def test_detect_seam_growth_end_to_end(tmp_path: Path) -> None:
    chapters_json = _write_chapters_json(
        tmp_path,
        [_chapter("CH01", [31]), _chapter("CH02", [35])],
    )
    connections_json = _write_connections_json(tmp_path, [[31, "N", 11, 35, "S", 0]])
    seam_warps_json = _write_seam_warps_json(tmp_path, [_seam("kevlar_route02", 31, 35)])

    reports = seam_growth.detect_seam_growth(
        chapters_json=chapters_json,
        connections_json=connections_json,
        seam_warps_json=seam_warps_json,
        current_slice_ids=[31, 35],
    )
    assert [r.chapter_id for r in reports] == ["CH01", "CH02"]
    ch01, ch02 = reports
    assert not ch01.ok
    assert len(ch01.edges) == 1
    assert ch01.edges[0].target_map_id == 35
    assert ch01.edges[0].realized_as == "arrow_warp"
    assert ch02.ok  # CH02 already has both its own map and the seam's other side


def test_detect_seam_growth_only_chapters_filter(tmp_path: Path) -> None:
    chapters_json = _write_chapters_json(
        tmp_path,
        [_chapter("CH01", [31]), _chapter("CH02", [35])],
    )
    connections_json = _write_connections_json(tmp_path, [[31, "N", 11, 35, "S", 0]])
    seam_warps_json = tmp_path / "no_seam_warps.json"

    reports = seam_growth.detect_seam_growth(
        chapters_json=chapters_json,
        connections_json=connections_json,
        seam_warps_json=seam_warps_json,
        current_slice_ids=[31, 35],
        only_chapters={"CH02"},
    )
    assert [r.chapter_id for r in reports] == ["CH02"]


# --- integration against the real corpus (gitignored, so skipped in CI) ------


DEFAULT_CONNECTIONS = seam_growth.DEFAULT_CONNECTIONS_JSON


@pytest.mark.skipif(
    not DEFAULT_CONNECTIONS.is_file(), reason="on-disk connections.json absent (output/ is gitignored)"
)
def test_real_gated_chapters_reconcile_and_run() -> None:
    """The detector must at least run cleanly end-to-end over the real,
    currently-gated chapters (CH01-CH06) without raising -- the substantive
    findings are reported by hand, not asserted here."""
    reports = seam_growth.detect_seam_growth()
    assert [r.chapter_id for r in reports] == ["CH01", "CH02", "CH03", "CH04", "CH05", "CH06"]
