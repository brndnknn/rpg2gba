"""Tests for the screenshot contact sheet (ROM_TEST_DEV.md §2).

Pure image assembly — no emulator, no ROM — so these run always, not behind
the RPG2GBA_PLAYTEST opt-in.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from rpg2gba.playtest.contact_sheet import Waypoint, build_contact_sheet


def make_frame(path: Path, color: tuple[int, int, int] = (10, 20, 30)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (240, 160), color).save(path)
    return path


def make_waypoints(tmp_path: Path, n: int) -> list[Waypoint]:
    return [
        Waypoint(beat=f"B{i}", name=f"B{i}", note=f"beat {i} description",
                 frame=i * 100, path=make_frame(tmp_path / "shots" / f"{i}.png"))
        for i in range(n)
    ]


def test_builds_single_page_with_expected_geometry(tmp_path: Path) -> None:
    waypoints = make_waypoints(tmp_path, 3)

    pages = build_contact_sheet(waypoints, tmp_path / "out",
                                chapter="moki", verdict="pass")

    assert len(pages) == 1
    assert pages[0] == tmp_path / "out" / "moki-sheet.png"
    sheet = Image.open(pages[0])
    # 3 waypoints at COLUMNS=3 -> one row; width covers 3 scaled cells.
    assert sheet.width >= 3 * 240 * 2
    assert sheet.height < 2 * (160 * 2 + 40)  # single row, not two


def test_paginates_beyond_per_page(tmp_path: Path) -> None:
    waypoints = make_waypoints(tmp_path, 14)

    pages = build_contact_sheet(waypoints, tmp_path / "out",
                                chapter="moki", verdict="pass")

    assert [p.name for p in pages] == ["moki-sheet.png", "moki-sheet-2.png"]
    assert all(p.exists() for p in pages)


def test_no_waypoints_produces_no_pages(tmp_path: Path) -> None:
    assert build_contact_sheet([], tmp_path / "out",
                                chapter="moki", verdict="fail") == []


def test_missing_frame_file_does_not_sink_the_sheet(tmp_path: Path) -> None:
    """A truncated/absent PNG is placeheld, not raised: the sheet is review
    material, and losing the other 17 frames to one bad file is worse."""
    good = make_frame(tmp_path / "shots" / "ok.png")
    waypoints = [
        Waypoint("B1", "B1", "fine", 100, good),
        Waypoint("B2", "B2", "gone", 200, tmp_path / "shots" / "missing.png"),
    ]

    pages = build_contact_sheet(waypoints, tmp_path / "out",
                                chapter="moki", verdict="pass")

    assert len(pages) == 1
    assert pages[0].exists()


def test_failed_waypoint_is_rendered(tmp_path: Path) -> None:
    """The failing frame gets a distinct caption color; assert it renders at
    all (color choice itself is cosmetic and not pinned by a test)."""
    frame = make_frame(tmp_path / "shots" / "f.png")
    waypoints = [Waypoint("B7", "FAILED", "walk_to budget exhausted", 900,
                          frame, failed=True)]

    pages = build_contact_sheet(waypoints, tmp_path / "out",
                                chapter="moki", verdict="fail")

    assert len(pages) == 1
    assert Image.open(pages[0]).size[0] > 0
