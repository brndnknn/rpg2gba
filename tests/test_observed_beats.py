"""Tests for the observed-beats debug-viewer file (runner.py).

Follows tests/test_runner.py's pattern: a stub emulator and synthetic
chapters, no mGBA/ROM required. Exercises `build_observed_beats_record`
directly (the pure serialization function) plus `run_chapter` end to end
via the same `FakeEmulator`/`make_chapter` helpers `test_runner.py` uses,
to prove the file actually lands on disk with the right shape.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.playtest.errors import ScenarioError
from rpg2gba.playtest.runner import (
    AttemptResult,
    BeatOutcome,
    ObservedBeat,
    build_observed_beats_record,
    run_chapter,
)

from tests.test_runner import fake_factory, make_chapter, make_rom, ok  # noqa: E402


def loc(mg: int, mn: int, x: int, y: int) -> dict:
    return {"map_group": mg, "map_num": mn, "player_pos": [x, y]}


def _attempt(beats_observed: list[ObservedBeat], passed: bool, rom: Path) -> AttemptResult:
    # `failed_beat` (used by build_observed_beats_record for the flake case)
    # reads AttemptResult.beats, not observed_beats -- mirror it here so the
    # stub behaves like a real attempt.
    outcomes = [BeatOutcome(ob.beat, f"desc {ob.beat}", ob.status)
                for ob in beats_observed]
    return AttemptResult(passed=passed, beats=outcomes, pristine_rom=rom,
                          observed_beats=beats_observed)


# -- build_observed_beats_record (pure function) -------------------------------

def test_all_beats_present_in_order_on_a_clean_pass(tmp_path: Path) -> None:
    chapter = make_chapter("t1", [("B1", ok), ("B2", ok), ("B3", ok)])
    rom = make_rom(tmp_path / "rom.gba")
    observed = [
        ObservedBeat("B1", "pass", loc(1, 1, 0, 0), loc(1, 1, 1, 0)),
        ObservedBeat("B2", "pass", loc(1, 1, 1, 0), loc(1, 2, 5, 5)),
        ObservedBeat("B3", "pass", loc(1, 2, 5, 5), loc(1, 2, 6, 5)),
    ]
    attempts = [_attempt(observed, True, rom)]

    record = build_observed_beats_record(chapter, attempts, "pass", None,
                                          "deadbeef", generated_at="2026-08-13T00:00:00Z")

    # Schema 2 (Q13 slice 4) added the walked path, the divergence
    # verdict and the frame-rule record per beat, plus the carried
    # contradictions and conformance summary per file.
    assert record["version"] == 2
    assert record["chapter"] == "t1"
    assert record["rom_sha256"] == "deadbeef"
    assert record["from_beat"] is None
    assert [b["beat"] for b in record["beats"]] == ["B1", "B2", "B3"]
    assert all(b["status"] == "pass" for b in record["beats"])
    assert record["beats"][1]["enter"] == loc(1, 1, 1, 0)
    assert record["beats"][1]["exit"] == loc(1, 2, 5, 5)


def test_mid_chapter_failure_produces_fail_and_trailing_skipped(tmp_path: Path) -> None:
    chapter = make_chapter("t2", [("B1", ok), ("B2", ok), ("B3", ok), ("B4", ok)])
    rom = make_rom(tmp_path / "rom.gba")
    # Only B1/B2 ran; B2 failed, so B3/B4 never got an ObservedBeat entry.
    observed = [
        ObservedBeat("B1", "pass", loc(0, 0, 0, 0), loc(0, 0, 1, 0)),
        ObservedBeat("B2", "fail", loc(0, 0, 1, 0), None),
    ]
    attempts = [_attempt(observed, False, rom)]

    record = build_observed_beats_record(chapter, attempts, "fail", None, None)

    statuses = {b["beat"]: b["status"] for b in record["beats"]}
    assert statuses == {"B1": "pass", "B2": "fail", "B3": "skipped", "B4": "skipped"}
    for name in ("B3", "B4"):
        entry = next(b for b in record["beats"] if b["beat"] == name)
        assert entry["enter"] is None
        assert entry["exit"] is None


def test_exit_is_null_for_the_failing_beat(tmp_path: Path) -> None:
    chapter = make_chapter("t3", [("B1", ok)])
    rom = make_rom(tmp_path / "rom.gba")
    observed = [ObservedBeat("B1", "fail", loc(2, 2, 3, 3), None)]
    attempts = [_attempt(observed, False, rom)]

    record = build_observed_beats_record(chapter, attempts, "fail", None, None)

    assert record["beats"][0]["status"] == "fail"
    assert record["beats"][0]["enter"] == loc(2, 2, 3, 3)
    assert record["beats"][0]["exit"] is None


def test_flake_beat_tagged_flake_not_pass_using_final_attempt_locations(tmp_path: Path) -> None:
    chapter = make_chapter("t4", [("B1", ok), ("B2", ok)])
    rom = make_rom(tmp_path / "rom.gba")
    attempt1_observed = [
        ObservedBeat("B1", "pass", loc(0, 0, 0, 0), loc(0, 0, 1, 0)),
        ObservedBeat("B2", "fail", loc(0, 0, 1, 0), None),
    ]
    attempt2_observed = [
        ObservedBeat("B1", "pass", loc(0, 0, 0, 0), loc(0, 0, 1, 0)),
        ObservedBeat("B2", "pass", loc(0, 0, 1, 0), loc(0, 0, 2, 0)),
    ]
    attempts = [_attempt(attempt1_observed, False, rom),
                _attempt(attempt2_observed, True, rom)]

    record = build_observed_beats_record(chapter, attempts, "flake", None, None)

    b2 = next(b for b in record["beats"] if b["beat"] == "B2")
    assert b2["status"] == "flake"
    # location data comes from the final (passing) attempt, not attempt 1
    assert b2["exit"] == loc(0, 0, 2, 0)
    assert record["beats"][0]["status"] == "pass"  # B1 unaffected


def test_from_beat_skip_reflected_in_record(tmp_path: Path) -> None:
    chapter = make_chapter("t5", [("B1", ok), ("B2", ok), ("B3", ok)])
    rom = make_rom(tmp_path / "rom.gba")
    # from_beat="B2" -> B1 never ran this attempt.
    observed = [
        ObservedBeat("B2", "pass", loc(1, 0, 0, 0), loc(1, 0, 1, 0)),
        ObservedBeat("B3", "pass", loc(1, 0, 1, 0), loc(1, 0, 2, 0)),
    ]
    attempts = [_attempt(observed, True, rom)]

    record = build_observed_beats_record(chapter, attempts, "pass", "B2", None)

    assert record["from_beat"] == "B2"
    b1 = next(b for b in record["beats"] if b["beat"] == "B1")
    assert b1["status"] == "skipped"
    assert b1["enter"] is None and b1["exit"] is None


# -- end-to-end through run_chapter ---------------------------------------------

@pytest.fixture(autouse=True)
def _stub_save_in_game(monkeypatch):
    from rpg2gba.playtest import scenarios

    monkeypatch.setattr(scenarios, "save_in_game", lambda emu: emu.tap("A"))


def test_run_chapter_writes_observed_beats_file_on_pass(tmp_path: Path) -> None:
    chapter = make_chapter("CH03", [("B1", ok), ("B2", ok)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    result = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                          emulator_factory=fake_factory)

    assert result.verdict == "pass"
    path = out / "observed_beats" / "CH03.json"
    assert path.exists()
    record = json.loads(path.read_text(encoding="utf-8"))
    # Schema 2 (Q13 slice 4) added the walked path, the divergence
    # verdict and the frame-rule record per beat, plus the carried
    # contradictions and conformance summary per file.
    assert record["version"] == 2
    assert record["chapter"] == "CH03"
    assert [b["beat"] for b in record["beats"]] == ["B1", "B2"]
    assert all(b["status"] == "pass" for b in record["beats"])
    assert record["rom_sha256"] is not None


def test_run_chapter_writes_observed_beats_file_on_failure(tmp_path: Path) -> None:
    def boom(emu):
        raise ScenarioError("nope")

    chapter = make_chapter("kevlar2", [("B1", ok), ("B2", boom), ("B3", ok)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    result = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                          emulator_factory=fake_factory, rerun_on_failure=False)

    assert result.verdict == "fail"
    path = out / "observed_beats" / "kevlar2.json"
    assert path.exists()
    record = json.loads(path.read_text(encoding="utf-8"))
    statuses = {b["beat"]: b["status"] for b in record["beats"]}
    assert statuses == {"B1": "pass", "B2": "fail", "B3": "skipped"}
    b2 = next(b for b in record["beats"] if b["beat"] == "B2")
    assert b2["exit"] is None


def test_rerun_overwrites_file_deterministically(tmp_path: Path) -> None:
    chapter = make_chapter("kevlar3", [("B1", ok)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                emulator_factory=fake_factory)
    path = out / "observed_beats" / "kevlar3.json"
    first_text = path.read_text(encoding="utf-8")

    run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                emulator_factory=fake_factory)
    second_text = path.read_text(encoding="utf-8")

    first = json.loads(first_text)
    second = json.loads(second_text)
    # generated_at legitimately differs run to run; strip it before comparing.
    first.pop("generated_at")
    second.pop("generated_at")
    assert first == second
