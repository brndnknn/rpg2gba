"""Tests for the versioned rule-set (`rules.py`, Q7.3) and the runner
changes it feeds (Q10: `not_run`/`hang` beat statuses and the generated
tally).

`tests/test_playtest.py` (owned by another agent working concurrently) does
not exercise `runner.run_chapter`/`_run_attempt` at all -- its coverage is
the mgba-adjacent primitives (battle decode, blob layout, walk_to, ...).
Runner-level tests belong here rather than there, per the task brief.

These are all pure-Python / stub-emulator tests -- no mgba, no real ROM, no
`RPG2GBA_POKEEMERALD` build required.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.playtest import rules
from rpg2gba.playtest import runner
from rpg2gba.playtest.chapter import Beat, Chapter
from rpg2gba.playtest.runner import (
    AttemptResult,
    BeatOutcome,
    BeatTally,
    RunnerError,
    Snapshot,
    _assert_no_false_pass,
    _run_attempt,
    compute_tally,
)


# -- rules.py: the rule set itself -------------------------------------------

def test_current_version_matches_rule_count() -> None:
    assert rules.CURRENT_VERSION == len(rules.RULES)


def test_rules_as_of_zero_is_the_pre_versioning_baseline() -> None:
    assert rules.rules_as_of(0) == ()


def test_rules_as_of_current_version_is_the_full_set() -> None:
    assert rules.rules_as_of(rules.CURRENT_VERSION) == rules.RULES


def test_rules_as_of_rejects_an_out_of_range_version() -> None:
    with pytest.raises(ValueError):
        rules.rules_as_of(rules.CURRENT_VERSION + 1)
    with pytest.raises(ValueError):
        rules.rules_as_of(-1)


def test_text_content_rule_records_that_its_primitive_does_not_exist_yet() -> None:
    # Q7.3: "record honestly" -- another agent is building the text-content
    # primitive concurrently; this rule must not claim it already exists.
    text_rule = next(r for r in rules.RULES if r.id == "text-content")
    assert text_rule.primitive_exists is False


def test_warp_facing_rule_claims_its_primitive_exists() -> None:
    warp_rule = next(r for r in rules.RULES if r.id == "warp-arrival-facing")
    assert warp_rule.primitive_exists is True


# -- owning_chapter / effective_rule_version (the ancestor-pinning detail) --

def test_owning_chapter_is_the_running_chapter_for_a_bare_beat_name() -> None:
    assert rules.owning_chapter("CH03", "B5") == "CH03"


def test_owning_chapter_recovers_the_prefix_for_a_replayed_ancestor_beat() -> None:
    # ChapterBuilder._prefix_beat (chapter.py:115-124) renames predecessor
    # beats <owner>:<name>, and never double-prefixes -- so a beat that
    # arrived at kevlar via route1's own predecessor (moki) is still named
    # "CH01:B1", not "CH02:CH01:B1".
    assert rules.owning_chapter("CH03", "CH01:B1") == "CH01"
    assert rules.owning_chapter("CH03", "CH02:B4") == "CH02"


def test_effective_rule_version_uses_running_version_for_the_chapters_own_beat() -> None:
    version = rules.effective_rule_version(
        "CH03", "B5", running_version=7, recorded_versions={"CH01": 1, "CH02": 2})
    assert version == 7


def test_effective_rule_version_pins_an_ancestor_beat_to_its_own_recorded_version() -> None:
    # The critical mechanical detail (Q7.3): a replayed ancestor beat is
    # evaluated at ITS OWN chapter's last recorded version, never the
    # running chapter's -- otherwise bumping CURRENT_VERSION for a new rule
    # would fail every descendant chapter's gate at once.
    recorded = {"CH01": 1, "CH02": 2}
    assert rules.effective_rule_version(
        "CH03", "CH01:B1", running_version=99, recorded_versions=recorded) == 1
    assert rules.effective_rule_version(
        "CH03", "CH02:B4", running_version=99, recorded_versions=recorded) == 2
    # kevlar's own beat, in the same call batch, still tracks the running
    # (current) version -- proving the pin is per-beat, not per-chapter-run.
    assert rules.effective_rule_version(
        "CH03", "B1", running_version=99, recorded_versions=recorded) == 99


def test_effective_rule_version_fails_loud_when_the_ancestor_was_never_recorded() -> None:
    with pytest.raises(ValueError, match="no recorded rule-set"):
        rules.effective_rule_version(
            "CH03", "CH01:B1", running_version=5, recorded_versions={})


# -- recorded-versions persistence (runner-only writer) ----------------------

def test_load_recorded_versions_returns_empty_dict_for_a_missing_file(tmp_path: Path) -> None:
    assert rules.load_recorded_versions(tmp_path / "nope.json") == {}


def test_record_chapter_version_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "playtest_rule_versions.json"
    rules.record_chapter_version(path, "CH01", 1)
    rules.record_chapter_version(path, "CH02", 2)
    assert rules.load_recorded_versions(path) == {"CH01": 1, "CH02": 2}


def test_record_chapter_version_only_overwrites_its_own_chapter(tmp_path: Path) -> None:
    path = tmp_path / "playtest_rule_versions.json"
    rules.record_chapter_version(path, "CH01", 1)
    rules.record_chapter_version(path, "CH02", 1)
    rules.record_chapter_version(path, "CH01", 2)  # moki re-gated under v2
    versions = rules.load_recorded_versions(path)
    assert versions["CH01"] == 2
    assert versions["CH02"] == 1  # untouched -- route1 has not been re-run


# -- lag report: generated, not maintained -----------------------------------

def test_lag_report_names_every_rule_a_chapter_lags() -> None:
    report = rules.lag_report("CH01", recorded_version=0, current_version=2)
    assert report.lagging == rules.RULES
    text = report.render()
    assert "CH01" in text
    assert "warp-arrival-facing" in text
    assert "text-content" in text


def test_lag_report_is_empty_when_a_chapter_is_fully_current() -> None:
    report = rules.lag_report("CH03", recorded_version=2, current_version=2)
    assert report.lagging == ()
    assert "up to date" in report.render()


def test_lag_report_partial_lag_names_only_the_missing_rules() -> None:
    report = rules.lag_report("CH03", recorded_version=1, current_version=2)
    assert [r.id for r in report.lagging] == ["text-content"]


def test_lag_reports_reads_every_recorded_chapter_sorted_by_name(tmp_path: Path) -> None:
    path = tmp_path / "versions.json"
    rules.record_chapter_version(path, "CH02", 0)
    rules.record_chapter_version(path, "CH03", 1)
    reports = rules.lag_reports(path, current_version=2)
    assert [r.chapter for r in reports] == ["CH02", "CH03"]
    assert reports[0].recorded_version == 0
    assert reports[1].recorded_version == 1


# -- runner.py: BeatTally (Q10's generated tally) -----------------------------

def test_compute_tally_all_pass() -> None:
    beats = [BeatOutcome("B1", "d", "pass"), BeatOutcome("B2", "d", "pass")]
    tally = compute_tally(beats)
    assert tally == BeatTally(total=2, run=2, passed=2, failed=0, hung=0, not_run=0)


def test_compute_tally_counts_not_run_beats_behind_a_stop() -> None:
    # This is the exact CH03 B11 shape: a beat fails/hangs and everything
    # behind it is still "not_run", not silently absent.
    beats = [
        BeatOutcome("B1", "d", "pass"),
        BeatOutcome("B2", "d", "fail", error="boom"),
        BeatOutcome("B3", "d", "not_run"),
        BeatOutcome("B4", "d", "not_run"),
    ]
    tally = compute_tally(beats)
    assert tally == BeatTally(total=4, run=2, passed=1, failed=1, hung=0, not_run=2)


def test_compute_tally_distinguishes_hang_from_fail() -> None:
    beats = [
        BeatOutcome("B1", "d", "pass"),
        BeatOutcome("B2", "d", "hang", error="hung"),
        BeatOutcome("B3", "d", "not_run"),
    ]
    tally = compute_tally(beats)
    assert tally.failed == 0
    assert tally.hung == 1
    assert tally.not_run == 1


def test_tally_render_matches_the_documented_shape() -> None:
    tally = BeatTally(total=60, run=53, passed=53, failed=0, hung=0, not_run=7)
    assert tally.render() == "53/60 run, 53 passed, 0 failed, 0 hung, 7 not run"


# -- runner.py: the no-false-pass guard ---------------------------------------

def test_assert_no_false_pass_allows_a_clean_pass() -> None:
    tally = BeatTally(total=3, run=3, passed=3, failed=0, hung=0, not_run=0)
    _assert_no_false_pass("CH01", "pass", tally)  # must not raise


def test_assert_no_false_pass_rejects_a_pass_verdict_with_a_not_run_beat() -> None:
    tally = BeatTally(total=3, run=2, passed=2, failed=0, hung=0, not_run=1)
    with pytest.raises(RunnerError, match="not_run"):
        _assert_no_false_pass("CH01", "pass", tally)


def test_assert_no_false_pass_allows_not_run_beats_on_a_fail_verdict() -> None:
    tally = BeatTally(total=3, run=1, passed=0, failed=1, hung=0, not_run=2)
    _assert_no_false_pass("CH01", "fail", tally)  # must not raise


# -- runner.py: _run_attempt with a stub emulator -----------------------------

class _StubEmu:
    """Just enough of `Emulator`'s surface for `_run_attempt` to drive a
    chapter without mgba: `run`/`waypoint`/`field_locked`/`player_pos`/
    `map_location`. `field_locked` always returns True so `_run_attempt`
    takes its documented "no seed at a mid-scene boundary" branch and never
    needs the real `dump_save_blocks`/`build_blob` machinery."""

    def __init__(self) -> None:
        self.waypoints: list[object] = []
        self._pos = (0, 0)
        self._loc = (0, 0)

    def run(self, frames: int) -> None:
        pass

    def player_pos(self) -> tuple[int, int]:
        return self._pos

    def map_location(self) -> tuple[int, int]:
        return self._loc

    def field_locked(self) -> bool:
        return True

    def waypoint(self, name, status=None, note=None, failed=False) -> None:
        self.waypoints.append((name, status, note, failed))


def _stub_snapshot(emu, beat_name: str) -> Snapshot:
    """Stands in for `runner._snapshot`: a real one drives
    `stamp.dump_save_blocks`, which needs a real save-block memory layout
    these tests have no reason to fake."""
    return Snapshot(beat=beat_name, player_pos=(0, 0), map_location=(0, 0), blocks={})


def _make_chapter(name: str, beat_specs: list[tuple[str, object]]) -> Chapter:
    beats = tuple(Beat(name=n, description=f"beat {n}", run=fn) for n, fn in beat_specs)
    return Chapter(name=name, doc=f"reference/chapters/{name}.md", beats=beats)


def _run_attempt_kwargs(tmp_path: Path, rom: Path, emu: _StubEmu, **overrides):
    kwargs = dict(
        attempt_no=1, from_beat=None, output_root=tmp_path / "output",
        emulator_factory=lambda scratch, engine, shots: emu,
        blobs_dir=tmp_path / "output" / "blobs",
    )
    kwargs.update(overrides)
    return kwargs


@pytest.fixture
def _pristine_rom(tmp_path: Path) -> Path:
    rom = tmp_path / "pristine.gba"
    rom.write_bytes(b"\x00" * 64)
    return rom


def test_run_attempt_marks_every_beat_not_run_up_front(monkeypatch, tmp_path, _pristine_rom) -> None:
    monkeypatch.setattr(runner, "_snapshot", _stub_snapshot)
    emu = _StubEmu()
    chapter = _make_chapter("t", [("B1", lambda e: None), ("B2", lambda e: None)])

    result = _run_attempt(
        chapter, _pristine_rom, tmp_path / "engine",
        **_run_attempt_kwargs(tmp_path, _pristine_rom, emu))

    assert [b.status for b in result.beats] == ["pass", "pass"]
    assert result.passed is True


def test_run_attempt_stops_on_failure_and_leaves_downstream_beats_not_run(
        monkeypatch, tmp_path, _pristine_rom) -> None:
    monkeypatch.setattr(runner, "_snapshot", _stub_snapshot)
    emu = _StubEmu()

    def _boom(e):
        raise ValueError("boom")

    chapter = _make_chapter("t", [
        ("B1", lambda e: None),
        ("B2", _boom),
        ("B3", lambda e: None),
        ("B4", lambda e: None),
    ])

    result = _run_attempt(
        chapter, _pristine_rom, tmp_path / "engine",
        **_run_attempt_kwargs(tmp_path, _pristine_rom, emu))

    assert [b.status for b in result.beats] == ["pass", "fail", "not_run", "not_run"]
    assert result.passed is False
    assert result.beats[1].error == "boom"
    tally = compute_tally(result.beats)
    assert tally == BeatTally(total=4, run=2, passed=1, failed=1, hung=0, not_run=2)


def test_run_attempt_reports_a_hang_distinct_from_a_failure_and_stops(
        monkeypatch, tmp_path, _pristine_rom) -> None:
    monkeypatch.setattr(runner, "_snapshot", _stub_snapshot)
    emu = _StubEmu()

    def _hangs(e):
        import time
        time.sleep(2)  # exceeds the 1s test budget below

    chapter = _make_chapter("t", [
        ("B1", lambda e: None),
        ("B2", _hangs),
        ("B3", lambda e: None),
    ])

    result = _run_attempt(
        chapter, _pristine_rom, tmp_path / "engine",
        **_run_attempt_kwargs(tmp_path, _pristine_rom, emu, beat_timeout_s=1))

    assert [b.status for b in result.beats] == ["pass", "hang", "not_run"]
    assert result.passed is False
    assert "hang budget" in result.beats[1].error
    assert result.failed_beat is result.beats[1]


def test_run_attempt_pins_rule_version_per_beat_owner(monkeypatch, tmp_path, _pristine_rom) -> None:
    monkeypatch.setattr(runner, "_snapshot", _stub_snapshot)
    emu = _StubEmu()
    chapter = _make_chapter("CH03", [
        ("CH01:B1", lambda e: None),
        ("CH02:B4", lambda e: None),
        ("B1", lambda e: None),
    ])

    result = _run_attempt(
        chapter, _pristine_rom, tmp_path / "engine",
        **_run_attempt_kwargs(
            tmp_path, _pristine_rom, emu,
            running_rule_version=99,
            recorded_rule_versions={"CH01": 1, "CH02": 2}))

    by_name = {b.name: b.rule_version for b in result.beats}
    assert by_name["CH01:B1"] == 1
    assert by_name["CH02:B4"] == 2
    assert by_name["B1"] == 99
