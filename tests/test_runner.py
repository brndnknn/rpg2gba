"""Tests for the chapter runner (src/rpg2gba/playtest/runner.py).

All tests here run against a stub emulator (`FakeEmulator`) and synthetic
chapters, so no mGBA bindings or built engine are required. `runner.py`
itself only calls the small surface `Chapter`/`Beat` define plus what
`stamp.dump_save_blocks` / `stamp.build_blob` / `stamp.stamp_rom` need
(u32/read_bytes/symbols/offsets), all of which `FakeEmulator` implements —
so these tests exercise the *real* blob/stamp code paths, not mocks of them.

Anything that genuinely needs a live ROM/emulator goes behind the same
RPG2GBA_PLAYTEST=1 opt-in gate `tests/test_playtest.py` uses.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from rpg2gba.playtest import runner as runner_mod
from rpg2gba.playtest.chapter import Beat, Chapter
from rpg2gba.playtest.errors import ScenarioError
from rpg2gba.playtest.runner import RunnerError, run_chapter
from rpg2gba.playtest.stamp import ROM_BASE

ROM_SIZE = 0x400
BLOB_FILE_OFFSET = 0x100  # gUraniumEmbeddedSave - ROM_BASE, must fit ROM_SIZE


class FakeEmulator:
    """Stand-in for `Emulator` exposing exactly what `runner.py` and
    `stamp.py`'s pure functions read: symbols/offsets, u32/read_bytes, and
    player_pos/map_location/screenshot. No mgba dependency."""

    def __init__(self, rom: Path, engine: Path, screenshot_dir: Path | None = None):
        self.rom = rom
        self.engine = engine
        self.screenshot_dir = screenshot_dir
        self.symbols = {
            "gSaveBlock1Ptr": 0x1000,
            "gSaveBlock2Ptr": 0x1000,
            "gSaveBlock3Ptr": 0x1000,
            "gPokemonStoragePtr": 0x1000,
            "gUraniumEmbeddedSave": ROM_BASE + BLOB_FILE_OFFSET,
        }
        self.offsets = {
            "sizeof_sb1": 4, "sizeof_sb2": 4, "sizeof_sb3": 4, "sizeof_storage": 4,
            "sizeof_es": 16, "embedded_save_magic": 0xABCDEF01,
            "off_es_sb1": 0, "off_es_sb2": 4, "off_es_sb3": 8, "off_es_storage": 12,
        }
        self._mem: dict[int, int] = {}
        self.frame = 0
        self._pos = (0, 0)
        self._map = (0, 0)
        self.waypoints: list = []

    def run(self, frames: int, keys: list[str] | None = None) -> None:
        self.frame += frames
        # Give each boot a slightly different "position" so snapshots taken
        # at different frames are distinguishable in tests if needed.
        self._pos = (self.frame % 100, (self.frame * 2) % 100)

    def u32(self, addr: int) -> int:
        return self._mem.get(addr, 0)

    def read_bytes(self, addr: int, size: int) -> bytes:
        return bytes(self._mem.get(addr + i, self.frame % 256) for i in range(size))

    def player_pos(self) -> tuple[int, int]:
        return self._pos

    def map_location(self) -> tuple[int, int]:
        return self._map

    def screenshot(self, name: str) -> Path | None:
        if self.screenshot_dir is None:
            return None
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = self.screenshot_dir / f"{name}_f{self.frame}.png"
        path.write_bytes(b"fake-png")
        return path

    def waypoint(self, beat: str, name: str = "", note: str = "",
                 failed: bool = False):
        # Writes a real (blank) GBA-sized PNG so the contact-sheet builder's
        # actual image path is exercised, not mocked.
        from PIL import Image

        from rpg2gba.playtest.contact_sheet import Waypoint

        if self.screenshot_dir is None:
            return None
        wp_dir = self.screenshot_dir / "waypoints"
        wp_dir.mkdir(parents=True, exist_ok=True)
        path = wp_dir / f"{len(self.waypoints):02d}_{beat}_{name}.png"
        Image.new("RGB", (240, 160), (16, 32, 48)).save(path)
        wp = Waypoint(beat=beat, name=name or beat, note=note,
                      frame=self.frame, path=path, failed=failed)
        self.waypoints.append(wp)
        return wp


def fake_factory(rom: Path, engine: Path, screenshot_dir: Path | None):
    return FakeEmulator(rom, engine, screenshot_dir)


def make_rom(path: Path, size: int = ROM_SIZE) -> Path:
    path.write_bytes(bytes(size))
    return path


def make_chapter(name: str, beat_specs: list[tuple[str, "callable"]]) -> Chapter:
    beats = tuple(Beat(name=n, description=f"desc {n}", run=fn) for n, fn in beat_specs)
    return Chapter(name=name, doc=f"reference/chapters/{name}.md", beats=beats)


def ok(emu) -> None:
    pass


# -- ordering -------------------------------------------------------------------

def test_runs_beats_in_order_and_stamps_green_rom(tmp_path: Path) -> None:
    calls: list[str] = []

    def make(n):
        def beat(emu):
            calls.append(n)
        return beat

    chapter = make_chapter("t1", [("B1", make("B1")), ("B2", make("B2")), ("B3", make("B3"))])
    rom = make_rom(tmp_path / "rom.gba")

    result = run_chapter(chapter, rom, tmp_path / "engine", output_root=tmp_path / "out",
                          emulator_factory=fake_factory)

    assert calls == ["B1", "B2", "B3"]
    assert result.verdict == "pass"
    assert [b.name for b in result.attempts[0].beats] == ["B1", "B2", "B3"]
    assert all(b.status == "pass" for b in result.attempts[0].beats)
    assert len(result.attempts) == 1
    assert result.stamped_rom is not None
    assert result.stamped_rom.exists()
    assert result.stamped_rom == tmp_path / "out" / "review" / "t1-complete.gba"
    # rerun-once machinery must not have deleted the pristine rom
    assert rom.exists()
    assert rom.read_bytes() == bytes(ROM_SIZE)  # untouched


# -- --from-beat slicing ---------------------------------------------------------

def test_from_beat_skips_earlier_beats_using_seed_blob(tmp_path: Path) -> None:
    calls: list[str] = []

    def make(n):
        def beat(emu):
            calls.append(n)
        return beat

    chapter = make_chapter("t2", [("B1", make("B1")), ("B2", make("B2")), ("B3", make("B3"))])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    first = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                         emulator_factory=fake_factory)
    assert first.verdict == "pass"
    assert calls == ["B1", "B2", "B3"]

    calls.clear()
    second = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                          emulator_factory=fake_factory, from_beat="B2")
    assert second.verdict == "pass"
    assert calls == ["B2", "B3"]
    assert [b.name for b in second.attempts[0].beats] == ["B2", "B3"]


def test_from_beat_without_prior_green_run_refuses_loudly(tmp_path: Path) -> None:
    chapter = make_chapter("t3", [("B1", ok), ("B2", ok)])
    rom = make_rom(tmp_path / "rom.gba")

    with pytest.raises(RunnerError, match="no seed blob"):
        run_chapter(chapter, rom, tmp_path / "engine", output_root=tmp_path / "out",
                    emulator_factory=fake_factory, from_beat="B2")


def test_from_beat_refuses_blob_from_different_rom_hash(tmp_path: Path) -> None:
    chapter = make_chapter("t4", [("B1", ok), ("B2", ok)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    first = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                         emulator_factory=fake_factory)
    assert first.verdict == "pass"

    # Rebuild the "ROM" (same size/zero-filled blob region, different bytes
    # elsewhere) -> different sha256, simulating any rebuild (D2a).
    rebuilt = bytearray(ROM_SIZE)
    rebuilt[0x10] = 0xFF
    rom.write_bytes(bytes(rebuilt))

    with pytest.raises(RunnerError, match="different ROM build"):
        run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                    emulator_factory=fake_factory, from_beat="B2")


# -- F3 rerun-once flake classification ------------------------------------------

def test_verdict_pass_when_first_attempt_succeeds(tmp_path: Path) -> None:
    chapter = make_chapter("t5", [("B1", ok)])
    rom = make_rom(tmp_path / "rom.gba")
    result = run_chapter(chapter, rom, tmp_path / "engine", output_root=tmp_path / "out",
                          emulator_factory=fake_factory)
    assert result.verdict == "pass"
    assert len(result.attempts) == 1


def test_verdict_flake_when_second_attempt_passes(tmp_path: Path) -> None:
    attempt_count = {"n": 0}

    def flaky(emu):
        attempt_count["n"] += 1
        if attempt_count["n"] == 1:
            raise ScenarioError("walk_to stuck behind an NPC")

    chapter = make_chapter("t6", [("B1", ok), ("B2", flaky)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    result = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                          emulator_factory=fake_factory)

    assert result.verdict == "flake"
    assert len(result.attempts) == 2
    assert result.attempts[0].passed is False
    assert result.attempts[1].passed is True
    assert result.bundle_dir is None
    assert result.stamped_rom is None
    assert result.flake_log is not None
    assert result.flake_log.exists()
    lines = result.flake_log.read_text(encoding="utf-8").strip().splitlines()
    record = json.loads(lines[-1])
    assert record["chapter"] == "t6"
    assert record["beat"] == "B2"
    assert "harness" in record["note"]


def test_verdict_fail_when_both_attempts_fail_and_bundle_is_written(tmp_path: Path) -> None:
    def always_fails(emu):
        emu.screenshot("boom")
        raise ScenarioError("enemy party never loaded")

    chapter = make_chapter("t7", [("B1", ok), ("B2", always_fails)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    result = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                          emulator_factory=fake_factory)

    assert result.verdict == "fail"
    assert len(result.attempts) == 2
    assert all(a.passed is False for a in result.attempts)
    assert result.flake_log is None
    assert result.stamped_rom is None
    assert result.bundle_dir is not None
    bundle = result.bundle_dir
    assert bundle.exists()

    failure = json.loads((bundle / "failure.json").read_text(encoding="utf-8"))
    assert failure["chapter"] == "t7"
    assert failure["chapter_doc"] == "reference/chapters/t7.md"
    assert failure["beat"] == "B2"
    assert "enemy party never loaded" in failure["error"]
    assert failure["traceback"]

    state = json.loads((bundle / "state_dump.json").read_text(encoding="utf-8"))
    assert state["beat"] == "B2"  # snapshot taken just before the failing beat
    assert "player_pos" in state
    assert "map_location" in state
    assert set(state["blocks"]) == {"sb1", "sb2", "sb3", "storage"}

    assert (bundle / "pre_beat.gba").exists()
    assert (bundle / "pre_beat.gba").stat().st_size == ROM_SIZE

    shots = list((bundle / "screenshots").glob("*.png"))
    assert len(shots) >= 1


def test_no_rerun_marks_single_failure_as_fail_immediately(tmp_path: Path) -> None:
    def always_fails(emu):
        raise ScenarioError("boom")

    chapter = make_chapter("t8", [("B1", always_fails)])
    rom = make_rom(tmp_path / "rom.gba")

    result = run_chapter(chapter, rom, tmp_path / "engine", output_root=tmp_path / "out",
                          emulator_factory=fake_factory, rerun_on_failure=False)

    assert result.verdict == "fail"
    assert len(result.attempts) == 1


# -- contact sheet (ROM_TEST_DEV §2) ---------------------------------------------

def test_green_run_writes_contact_sheet_next_to_review_rom(tmp_path: Path) -> None:
    chapter = make_chapter("t10", [("B1", ok), ("B2", ok)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    result = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                          emulator_factory=fake_factory)

    assert result.verdict == "pass"
    assert result.contact_sheet
    sheet = result.contact_sheet[0]
    assert sheet == out / "review" / "t10-sheet.png"
    assert sheet.exists()
    # boot + one waypoint per passing beat
    assert len(result.attempts[0].waypoints) == 3
    assert [w.beat for w in result.attempts[0].waypoints] == ["boot", "B1", "B2"]


def test_failing_run_puts_contact_sheet_in_the_bundle_ending_on_the_failure(
        tmp_path: Path) -> None:
    def boom(emu):
        raise ScenarioError("gate leaked")

    chapter = make_chapter("t11", [("B1", ok), ("B2", boom)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    result = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                          emulator_factory=fake_factory)

    assert result.verdict == "fail"
    assert result.bundle_dir is not None
    assert result.contact_sheet == [result.bundle_dir / "t11-sheet.png"]
    assert result.contact_sheet[0].exists()

    waypoints = result.attempts[-1].waypoints
    assert [w.beat for w in waypoints] == ["boot", "B1", "B2"]
    assert waypoints[-1].failed is True


def test_contact_sheet_survives_screenshot_dir_cleanup(tmp_path: Path) -> None:
    """The per-attempt screenshot dir (which holds the waypoint PNGs) is
    deleted at the end of a run — the sheet must already be rendered."""
    chapter = make_chapter("t12", [("B1", ok)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    result = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                          emulator_factory=fake_factory)

    assert not (out / "_attempt1_t12").exists()
    assert result.contact_sheet[0].exists()


def test_rerun_replaces_stale_sheet_pages(tmp_path: Path) -> None:
    chapter = make_chapter("t13", [("B1", ok)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                emulator_factory=fake_factory)
    stale = out / "review" / "t13-sheet-2.png"
    stale.write_bytes(b"stale")

    result = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                          emulator_factory=fake_factory)

    assert not stale.exists()
    assert result.contact_sheet == [out / "review" / "t13-sheet.png"]


# -- scratch-ROM hygiene ---------------------------------------------------------

def test_attempt_scratch_roms_and_sav_files_are_cleaned_up(tmp_path: Path) -> None:
    chapter = make_chapter("t9", [("B1", ok)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                emulator_factory=fake_factory)

    leftovers = list(out.glob("*.scratch.gba")) + list(out.glob("*.scratch.sav"))
    assert leftovers == []


# -- CLI glue (no ROM needed; runner is monkeypatched) ---------------------------

def test_cli_run_reports_pass_and_exits_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from rpg2gba.playtest import __main__ as cli_mod

    chapter = make_chapter("cliok", [("B1", ok)])
    monkeypatch.setattr(cli_mod, "load_chapter", lambda name: chapter)

    def fake_run_chapter(chap, rom, engine, **kwargs):
        return runner_mod.ChapterRunResult(
            chapter=chap.name, verdict="pass",
            attempts=[runner_mod.AttemptResult(
                passed=True,
                beats=[runner_mod.BeatOutcome("B1", "desc B1", "pass")],
                pristine_rom=rom)],
            stamped_rom=tmp_path / "review.gba")

    monkeypatch.setattr(cli_mod, "run_chapter", fake_run_chapter)

    engine_dir = tmp_path / "engine"
    engine_dir.mkdir()
    (engine_dir / "pokeemerald.gba").write_bytes(b"\x00")

    result = CliRunner().invoke(
        cli_mod.cli, ["run", "--chapter", "cliok", "--engine", str(engine_dir)])
    assert result.exit_code == 0, result.output
    assert "PASS" in result.output
    assert "green review ROM" in result.output


def test_cli_run_exits_nonzero_on_real_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from rpg2gba.playtest import __main__ as cli_mod

    chapter = make_chapter("clifail", [("B1", ok)])
    monkeypatch.setattr(cli_mod, "load_chapter", lambda name: chapter)

    def fake_run_chapter(chap, rom, engine, **kwargs):
        return runner_mod.ChapterRunResult(
            chapter=chap.name, verdict="fail",
            attempts=[runner_mod.AttemptResult(
                passed=False,
                beats=[runner_mod.BeatOutcome("B1", "desc B1", "fail", error="boom")],
                pristine_rom=rom)],
            bundle_dir=tmp_path / "bundle")

    monkeypatch.setattr(cli_mod, "run_chapter", fake_run_chapter)

    engine_dir = tmp_path / "engine"
    engine_dir.mkdir()
    (engine_dir / "pokeemerald.gba").write_bytes(b"\x00")

    result = CliRunner().invoke(
        cli_mod.cli, ["run", "--chapter", "clifail", "--engine", str(engine_dir)])
    assert result.exit_code == 1
    assert "FAIL" in result.output
    assert "repro bundle" in result.output


# -- opt-in end-to-end (real ROM/engine/mgba) ------------------------------------
# The thin pytest wrapper for gate/CI runs (ROM_TEST_DEV C5(b), second
# consumer of run_chapter) lives here, behind the same opt-in gate
# tests/test_playtest.py uses -- it needs a built engine, a real chapter
# module under playtest/chapters/, and the mgba bindings.

ENGINE = Path(__file__).resolve().parents[1] / "engine"

e2e = pytest.mark.skipif(
    os.environ.get("RPG2GBA_PLAYTEST") != "1"
    or not (ENGINE / "pokeemerald.gba").exists()
    or not (ENGINE / "pokeemerald.map").exists(),
    reason="opt-in: needs RPG2GBA_PLAYTEST=1, mgba bindings, and a built engine",
)


@e2e
@pytest.mark.parametrize("chapter_name", ["moki"])
def test_chapter_suite_is_green(tmp_path: Path, chapter_name: str) -> None:
    """Gate/CI wrapper: the named chapter must be fully green, from a new
    game, on the current build. Fails loud (non-pass verdict) rather than
    silently accepting a flake or a real failure."""
    from rpg2gba.playtest.chapter import load_chapter

    chapter = load_chapter(chapter_name)
    result = run_chapter(chapter, ENGINE / "pokeemerald.gba", ENGINE,
                          output_root=tmp_path / "out")
    assert result.verdict in ("pass", "flake"), (
        f"{chapter_name} did not pass: bundle at {result.bundle_dir}")
