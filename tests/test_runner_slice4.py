"""Tests for Q13 slice 4 of the playtest runner
(`PLAYTEST_AUTHORING_IMPROVEMENT_V2.md`): the walked-tile path record, the
divergence-vs-approved-route check, the enforced frame rule, and the
carried-contradiction ledger, all as they land in `runner.py` and the
`observed_beats/<chapter>.json` artifact (schema version 2).

Companion to `tests/test_runner.py` — same no-ROM/no-mGBA/no-network style,
same synthetic-chapter approach, and the same `FakeEmulator` as its base.
This file only *adds* the slice-4 surface (`walk_path`/`clear_walk_path`/
`frames_marked`/`contradictions`) that `tests/test_runner.py`'s own
`FakeEmulator` deliberately does NOT have (its docstring says stub
emulators there predate the walked path, and `runner.py`'s `_close_walk`/
`_apply_frame_rule` are written to degrade gracefully against exactly that
stub — see their `except AttributeError` branches). A fake that DOES carry
the new surface is what actually exercises slice 4's logic, so it lives
here rather than being bolted onto the shared fake and changing what the
existing suite covers.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from rpg2gba.playtest import runner as runner_mod
from rpg2gba.playtest.contradictions import KIND_WALKABILITY, Contradiction
from rpg2gba.playtest.divergence import PlanIndex, TriggerFact, WalkedTile
from rpg2gba.playtest.errors import ScenarioError
from rpg2gba.playtest.runner import run_chapter

from tests.test_runner import FakeEmulator, make_chapter, make_rom

ROM_SIZE = 0x400


class FakeEmulatorV4(FakeEmulator):
    """`tests/test_runner.py`'s `FakeEmulator`, plus the slice-4 surface
    `runner.py` reads through an `except AttributeError` degrade path:
    `walk_path`/`clear_walk_path` (Q13.2's per-beat tile record) and
    `frames_marked` (Q7's frame rule). `contradictions` (Q8's ledger) is
    just a plain `ContradictionLedger` a beat body can record into directly,
    exactly like the real `Emulator` exposes it (`emulator.py:694`).

    `record_walk` is this test file's hand for a beat body: the real
    `Emulator` appends to `_walk_path` itself as the walker steps (see
    `emulator.py` around line 1780); nothing here reimplements walking, it
    just lets a synthetic beat assert "the walk touched these tiles" the
    same way a real beat's `walk_to` would end up having done.
    """

    def __init__(self, rom: Path, engine: Path, screenshot_dir: Path | None = None):
        super().__init__(rom, engine, screenshot_dir)
        self._walk_path: list[WalkedTile] = []
        self._frames_marked = 0
        # Q8's ledger -- a beat body records into this directly, matching
        # the real `Emulator.contradictions` surface (emulator.py:694).
        from rpg2gba.playtest.contradictions import ContradictionLedger

        self.contradictions = ContradictionLedger()

    def record_walk(self, x: int, y: int, *, map_id: int | None = 1,
                     map_group: int = 0, map_num: int = 7) -> None:
        self._walk_path.append(
            WalkedTile(map_id=map_id, map_group=map_group, map_num=map_num, x=x, y=y))

    def walk_path(self) -> tuple[WalkedTile, ...]:
        return tuple(self._walk_path)

    def clear_walk_path(self) -> None:
        self._walk_path.clear()

    def frames_marked(self) -> int:
        return self._frames_marked

    def mark_frame(self) -> bool:
        self._frames_marked += 1
        return True

    def waypoint(self, beat: str, name: str = "", note: str = "",
                 failed: bool = False):
        # Real `Emulator.waypoint` is the beat boundary that clears the
        # frame-rule pin count (emulator.py:914) -- `_apply_frame_rule`
        # reads `frames_marked()` BEFORE this is called on a failure
        # (runner.py's ordering comment), so resetting here rather than in
        # `frames_marked()` itself matches the real object's contract.
        wp = super().waypoint(beat, name, note, failed)
        self._frames_marked = 0
        return wp


def fake_factory_v4(rom: Path, engine: Path, screenshot_dir: Path | None):
    return FakeEmulatorV4(rom, engine, screenshot_dir)


def fake_factory_v4_no_screenshots(rom: Path, engine: Path, screenshot_dir: Path | None):
    """Forces `emu.screenshot_dir is None` regardless of what the runner
    passes -- the harness always passes a per-attempt shots dir
    (`_run_attempt`'s `shots` local), so the only way to exercise "this run
    captures no frames at all" (test 9) is to have the emulator itself
    ignore it, the way a headless/no-screenshot `Emulator` build would."""
    return FakeEmulatorV4(rom, engine, None)


@pytest.fixture(autouse=True)
def _stub_save_in_game(monkeypatch):
    """Same stub `tests/test_runner.py` uses (see that module's docstring
    on `FakeEmulator` for why) -- pytest fixtures aren't shared across test
    files just by importing the module they're defined in, so this is
    re-declared here rather than reused."""
    from rpg2gba.playtest import scenarios

    monkeypatch.setattr(scenarios, "save_in_game", lambda emu: emu.tap("A"))


def _patch_plan(monkeypatch: pytest.MonkeyPatch, plan: PlanIndex | None) -> None:
    """Stand in for `_WalkOracle.for_chapter`'s call to
    `load_plan_index_for_module` (imported into `runner.py`'s own
    namespace, so that's the name to patch -- patching
    `divergence.load_plan_index_for_module` would miss it).

    Every test here patches this explicitly, even the "no plan" tests --
    the *real* lookup falls back to `reference/routes/` in this actual repo
    checkout, and leaving that live would make "no plan" tests depend on
    whatever route-plan files other concurrent work happens to have on disk
    at test time. Patching keeps every test hermetic."""
    monkeypatch.setattr(runner_mod, "load_plan_index_for_module", lambda name: plan)


def _patch_overlay(monkeypatch: pytest.MonkeyPatch,
                    overlays: dict[int, dict[tuple[int, int], tuple[TriggerFact, ...]]],
                    ) -> None:
    """Stand in for `_WalkOracle._overlay_for`, which normally derives a
    map's foreign-trigger index from the real decoded map graph
    (`build_trigger_overlay`, `..traversal.triggers`). Building a real graph
    for a synthetic map is out of scope for a runner unit test -- what
    `runner.py`'s own logic needs exercised is what `compare_walk` does
    with whatever overlay `_WalkOracle.compare` is handed, not how that
    overlay gets built, so this replaces the derivation with a fixed table
    while leaving `compare_walk`/`DivergenceError` genuinely exercised."""

    def _overlay_for(self, map_id: int, emu) -> dict:  # noqa: ANN001
        return overlays.get(map_id, {})

    monkeypatch.setattr(runner_mod._WalkOracle, "_overlay_for", _overlay_for)


def _observed(out: Path, chapter_name: str) -> dict:
    path = out / "observed_beats" / f"{chapter_name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _beat(name: str, obs: dict) -> dict:
    for b in obs["beats"]:
        if b["beat"] == name:
            return b
    raise AssertionError(f"beat {name!r} not in observed-beats record: {obs['beats']}")


# -- 1. walked path reaches the artifact -----------------------------------------

def test_walked_path_reaches_the_artifact(tmp_path: Path, monkeypatch) -> None:
    """A beat that records a few walked tiles gets them back out of
    `observed_beats/<chapter>.json`, in order, each shaped with
    map_id/map_group/map_num/x/y -- the whole point of Q13.2."""
    _patch_plan(monkeypatch, None)

    def walk_beat(emu):
        emu.record_walk(10, 10)
        emu.record_walk(11, 10)
        emu.record_walk(12, 10)

    chapter = make_chapter("v4path", [("B1", walk_beat)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    result = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                          emulator_factory=fake_factory_v4)

    assert result.verdict == "pass"
    obs = _observed(out, "v4path")
    assert obs["version"] == 2
    b1 = _beat("B1", obs)
    assert b1["path"] == [
        {"map_id": 1, "map_group": 0, "map_num": 7, "x": 10, "y": 10},
        {"map_id": 1, "map_group": 0, "map_num": 7, "x": 11, "y": 10},
        {"map_id": 1, "map_group": 0, "map_num": 7, "x": 12, "y": 10},
    ]


# -- 2. the path survives a failing/hung beat, which is the point -----------------

def test_walked_path_recorded_for_a_failing_beat(tmp_path: Path, monkeypatch) -> None:
    """The beat you most want to inspect is the one that broke -- the old
    two-point (enter/exit) record went blank exactly there, because `exit`
    is `None` for a beat that raised. `path` must not go blank with it."""
    _patch_plan(monkeypatch, None)

    def fails(emu):
        emu.record_walk(1, 1)
        emu.record_walk(2, 1)
        raise ScenarioError("enemy party never loaded")

    chapter = make_chapter("v4fail", [("B1", fails)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    result = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                          emulator_factory=fake_factory_v4, rerun_on_failure=False)

    assert result.verdict == "fail"
    obs = _observed(out, "v4fail")
    b1 = _beat("B1", obs)
    assert b1["status"] == "fail"
    assert b1["exit"] is None
    assert [(t["x"], t["y"]) for t in b1["path"]] == [(1, 1), (2, 1)]


def test_walked_path_recorded_for_a_hung_beat(tmp_path: Path, monkeypatch) -> None:
    """Same as the failing case, for Q10's hang path (`BeatHangError`) --
    a hung beat's `status` is `"hang"`, `exit` is `None`, and `path` must
    still carry whatever the walk did before the wall-clock backstop fired."""
    _patch_plan(monkeypatch, None)

    def hangs(emu):
        emu.record_walk(3, 3)
        emu.record_walk(4, 3)
        time.sleep(1.3)

    chapter = make_chapter("v4hang", [("B1", hangs)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    result = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                          emulator_factory=fake_factory_v4, rerun_on_failure=False,
                          beat_timeout_s=1)

    assert result.verdict == "fail"
    assert result.attempts[0].beats[0].status == "hang"
    obs = _observed(out, "v4hang")
    b1 = _beat("B1", obs)
    assert b1["status"] == "hang"
    assert b1["exit"] is None
    assert [(t["x"], t["y"]) for t in b1["path"]] == [(3, 3), (4, 3)]


# -- 3. the path is per beat -------------------------------------------------------

def test_walked_path_is_cleared_at_each_beat_boundary(tmp_path: Path, monkeypatch) -> None:
    """Beat 2's recorded path must not carry beat 1's tiles -- the runner
    calls `emu.clear_walk_path()` at every beat boundary specifically so a
    later beat's path can't leak into an earlier (or later) one's record."""
    _patch_plan(monkeypatch, None)

    def b1(emu):
        emu.record_walk(0, 0)
        emu.record_walk(1, 0)

    def b2(emu):
        emu.record_walk(9, 9)

    chapter = make_chapter("v4perbeat", [("B1", b1), ("B2", b2)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    result = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                          emulator_factory=fake_factory_v4)

    assert result.verdict == "pass"
    obs = _observed(out, "v4perbeat")
    p1 = [(t["x"], t["y"]) for t in _beat("B1", obs)["path"]]
    p2 = [(t["x"], t["y"]) for t in _beat("B2", obs)["path"]]
    assert p1 == [(0, 0), (1, 0)]
    assert p2 == [(9, 9)]
    assert set(p1).isdisjoint(p2)


# -- 4. no route plan -> no enforcement, ever ---------------------------------------

def test_no_route_plan_means_walk_is_never_enforced(tmp_path: Path, monkeypatch) -> None:
    """Route plans are enforced forward from CH05 (PROJECT_TODO #67); every
    chapter before that has no plan artifact and never will. A walk that
    stomps all over the map must still pass, and `divergence` must report
    `compared: false` (or be absent) rather than a violation -- this is the
    ordinary case and must never fail a run."""
    _patch_plan(monkeypatch, None)

    def stomps(emu):
        for x in range(50):
            emu.record_walk(x, x % 3)

    chapter = make_chapter("v4noplan", [("B1", stomps)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    result = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                          emulator_factory=fake_factory_v4)

    assert result.verdict == "pass"
    obs = _observed(out, "v4noplan")
    b1 = _beat("B1", obs)
    div = b1["divergence"]
    assert div is None or div.get("compared") is False


# -- 5. trigger divergence fails the beat, even with clean own assertions ---------

def test_trigger_divergence_fails_the_beat_even_when_its_own_asserts_pass(
        tmp_path: Path, monkeypatch) -> None:
    """The CH04 B3 shape: a walk crosses a tile off the approved route that
    fires someone else's script, and the beat's own assertions never see
    it -- both guards go green and the wrong thing happened anyway. This is
    the one divergence class that must fail the beat, with a message naming
    both the offending tile and the script it fires."""
    plan = PlanIndex(
        tiles={1: frozenset({(0, 0), (1, 0), (2, 0)})},
        declared_crossings={},
        chapter_id="CH99",
    )
    _patch_plan(monkeypatch, plan)
    _patch_overlay(monkeypatch, {
        1: {(5, 5): (TriggerFact(script="Map001_EventScript_Timothy",
                                  kind="touch", certainty="certain",
                                  detail="fires on contact"),)},
    })

    def walks_off_onto_a_trigger(emu):
        emu.record_walk(0, 0)
        emu.record_walk(1, 0)
        emu.record_walk(5, 5)  # off-plan AND a trigger tile -> must fail

    chapter = make_chapter("v4trigger", [("B1", walks_off_onto_a_trigger)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    result = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                          emulator_factory=fake_factory_v4, rerun_on_failure=False)

    assert result.verdict == "fail"
    outcome = result.attempts[0].beats[0]
    assert outcome.status == "fail"
    assert "Map001_EventScript_Timothy" in outcome.error
    assert "5, 5" in outcome.error


# -- 6. non-trigger divergence is carried, not blocking ----------------------------

def test_non_trigger_divergence_is_carried_not_blocking(
        tmp_path: Path, monkeypatch) -> None:
    """Same off-plan tile, firing nothing this time: the beat must pass,
    and the run artifact must carry a `walk_off_plan` contradiction with
    status "carried" -- `route1:B14` is exactly why this must not block:
    blocking on ambiguous evidence truncates real work."""
    plan = PlanIndex(
        tiles={1: frozenset({(0, 0), (1, 0), (2, 0)})},
        declared_crossings={},
        chapter_id="CH99",
    )
    _patch_plan(monkeypatch, plan)
    _patch_overlay(monkeypatch, {1: {}})  # (5, 5) fires nothing

    def walks_off_but_harmless(emu):
        emu.record_walk(0, 0)
        emu.record_walk(5, 5)

    chapter = make_chapter("v4offplan", [("B1", walks_off_but_harmless)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    result = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                          emulator_factory=fake_factory_v4)

    assert result.verdict == "pass"
    outcome = result.attempts[0].beats[0]
    assert outcome.status == "pass"

    obs = _observed(out, "v4offplan")
    contradictions = obs["contradictions"]
    off_plan = [c for c in contradictions if c["kind"] == "walk_off_plan"]
    assert len(off_plan) == 1
    assert off_plan[0]["status"] == "carried"
    assert off_plan[0]["beat"] == "B1"


# -- 7/8. the enforced frame rule ---------------------------------------------------

def test_frame_rule_refuses_unevidenced_negative_claim(tmp_path: Path, monkeypatch) -> None:
    """A beat that fails with a negative claim ("the object is not
    rendered") and never called `mark_frame()` gets its recorded `error`
    replaced by the refusal; the original text survives in
    `refused_claim`; and the beat still fails -- refusing the claim does
    not un-fail the beat, it just stops an unevidenced negative from being
    taken at face value (both of CH04's wrong write-ups were exactly that)."""
    _patch_plan(monkeypatch, None)
    claim = "the object is not rendered"

    def fails_unevidenced(emu):
        raise ScenarioError(claim)

    chapter = make_chapter("v4framerefuse", [("B1", fails_unevidenced)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    result = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                          emulator_factory=fake_factory_v4, rerun_on_failure=False)

    assert result.verdict == "fail"
    outcome = result.attempts[0].beats[0]
    assert outcome.status == "fail"
    assert outcome.frame_rule is not None
    assert outcome.frame_rule["refused"] is True
    assert outcome.refused_claim == claim
    assert "refused" in outcome.error
    assert "mark_frame" in outcome.error


def test_frame_rule_passes_when_a_frame_was_marked(tmp_path: Path, monkeypatch) -> None:
    """The same negative claim, this time backed by an explicit
    `mark_frame()` call -- the rule must not refuse it, and the recorded
    error stays the beat's own message."""
    _patch_plan(monkeypatch, None)
    claim = "the object is not rendered"

    def fails_evidenced(emu):
        emu.mark_frame()
        raise ScenarioError(claim)

    chapter = make_chapter("v4framepass", [("B1", fails_evidenced)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    result = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                          emulator_factory=fake_factory_v4, rerun_on_failure=False)

    assert result.verdict == "fail"
    outcome = result.attempts[0].beats[0]
    assert outcome.frame_rule is not None
    assert outcome.frame_rule["refused"] is False
    assert outcome.refused_claim is None
    assert outcome.error == claim


def test_frame_rule_does_not_fire_on_a_positive_claim(tmp_path: Path, monkeypatch) -> None:
    """A positive failure ("expected species 25, got 133") is not a
    negative claim at all -- the rule must not touch it, with or without a
    marked frame. Misfiring here would force authors to bolt on a
    `mark_frame()` call that has nothing to do with their actual bug."""
    _patch_plan(monkeypatch, None)
    claim = "expected species 25, got 133"

    def fails_positive(emu):
        raise ScenarioError(claim)

    chapter = make_chapter("v4framepositive", [("B1", fails_positive)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    result = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                          emulator_factory=fake_factory_v4, rerun_on_failure=False)

    assert result.verdict == "fail"
    outcome = result.attempts[0].beats[0]
    assert outcome.frame_rule is not None
    assert outcome.frame_rule["refused"] is False
    assert outcome.refused_claim is None
    assert outcome.error == claim


def test_frame_rule_not_enforced_when_run_captures_no_frames(
        tmp_path: Path, monkeypatch) -> None:
    """A headless/no-screenshot run (`screenshot_dir is None`) cannot
    possibly satisfy the rule, so it is an explicit skip, not a silent
    refusal of every negative-claim failure: `frame_rule["enforced"]` must
    be `False` and nothing gets refused."""
    _patch_plan(monkeypatch, None)
    claim = "the object is not rendered"

    def fails_unevidenced(emu):
        raise ScenarioError(claim)

    chapter = make_chapter("v4framenoshots", [("B1", fails_unevidenced)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    result = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                          emulator_factory=fake_factory_v4_no_screenshots,
                          rerun_on_failure=False)

    assert result.verdict == "fail"
    outcome = result.attempts[0].beats[0]
    assert outcome.frame_rule is not None
    assert outcome.frame_rule["enforced"] is False
    assert outcome.frame_rule["refused"] is False
    assert outcome.refused_claim is None
    assert outcome.error == claim


# -- 10. conformance summary --------------------------------------------------------

def test_conformance_summary_from_walkability_contradictions(
        tmp_path: Path, monkeypatch) -> None:
    """A run whose emulator recorded `graph_vs_live_collision` contradictions
    (Q8, `_plan_route`'s own finding, always recorded with no beat name)
    must produce a top-level `conformance` summary with the right counts,
    and the per-beat attribution must land on whichever beat was actually
    running when the ledger is drained (`ContradictionLedger.rebeat`)."""
    _patch_plan(monkeypatch, None)

    def records_disagreements(emu):
        emu.contradictions.record(Contradiction(
            kind=KIND_WALKABILITY, beat="",
            detail="cell (3,3) on map 5: graph says blocked, live says walkable",
            model="blocked", measurement="walkable",
            assumption="the live collision grid is right",
            map_id=5, cell=(3, 3)))
        emu.contradictions.record(Contradiction(
            kind=KIND_WALKABILITY, beat="",
            detail="cell (4,4) on map 5: graph says blocked, live says walkable",
            model="blocked", measurement="walkable",
            assumption="the live collision grid is right",
            map_id=5, cell=(4, 4)))

    chapter = make_chapter("v4conformance", [("B1", records_disagreements)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    result = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                          emulator_factory=fake_factory_v4)

    assert result.verdict == "pass"
    obs = _observed(out, "v4conformance")
    conformance = obs["conformance"]
    assert conformance["walkability_disagreements"] == 2
    assert conformance["distinct_cells"] == 2
    assert conformance["by_map"] == {"5": 2}

    walkability_entries = [c for c in obs["contradictions"]
                            if c["kind"] == "graph_vs_live_collision"]
    assert len(walkability_entries) == 2
    assert all(c["beat"] == "B1" for c in walkability_entries)


# -- 11. the whole artifact round-trips through JSON --------------------------------

def test_observed_beats_artifact_is_json_round_trippable(
        tmp_path: Path, monkeypatch) -> None:
    """Everything slice 4 adds (`path`, `divergence`, `frame_rule`,
    `refused_claim`, `contradictions`, `conformance`) must be plain JSON --
    no tuples/dataclasses/enums leaking through -- so
    `build_observed_beats_record`'s dict round-trips through
    `json.loads(json.dumps(...))` unchanged."""
    plan = PlanIndex(
        tiles={1: frozenset({(0, 0)})}, declared_crossings={}, chapter_id="CH99")
    _patch_plan(monkeypatch, plan)
    _patch_overlay(monkeypatch, {
        1: {(9, 9): (TriggerFact(script="Map001_EventScript_Foo", kind="touch",
                                  certainty="certain", detail="d"),)},
    })

    def b1(emu):
        emu.record_walk(0, 0)
        emu.contradictions.record(Contradiction(
            kind=KIND_WALKABILITY, beat="", detail="d", map_id=2, cell=(1, 1)))

    def b2(emu):
        emu.record_walk(9, 9)  # off-plan trigger -> fails

    chapter = make_chapter("v4roundtrip", [("B1", b1), ("B2", b2)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                emulator_factory=fake_factory_v4, rerun_on_failure=False)

    record = runner_mod.build_observed_beats_record(
        chapter,
        _rerun_for_record(chapter, rom, tmp_path / "engine", out),
        "fail", None, "deadbeef")
    dumped = json.dumps(record)
    round_tripped = json.loads(dumped)
    assert round_tripped == json.loads(json.dumps(round_tripped))
    # Sanity: the fields slice 4 added really are in there.
    assert "path" in round_tripped["beats"][0]
    assert "divergence" in round_tripped["beats"][0]
    assert "contradictions" in round_tripped
    assert "conformance" in round_tripped


def _rerun_for_record(chapter, rom, engine, out):
    """Helper for the round-trip test: re-run to get a fresh `AttemptResult`
    list to feed `build_observed_beats_record` directly (the same object
    `_write_observed_beats` already builds and writes -- this just calls
    the pure builder a second time to assert on the dict itself rather than
    re-parsing the file, so the round-trip assertion is about the object
    `runner.py` actually produces)."""
    from rpg2gba.playtest.runner import _run_attempt

    return [_run_attempt(
        chapter, rom, engine, attempt_no=1, from_beat=None,
        output_root=out, emulator_factory=fake_factory_v4,
        blobs_dir=out / "blobs")]


# -- 12. v1 fields are unchanged -----------------------------------------------------

def test_v1_fields_unchanged_including_skipped_beats(tmp_path: Path, monkeypatch) -> None:
    """A v1 consumer only ever looked at `chapter`, `rom_sha256`,
    `generated_at`, `from_beat`, and each beat's `beat`/`status`/`enter`/
    `exit` -- schema 2 must not have changed what any of those mean, and a
    `--from-beat` run's skipped (pre-seed) beats must still report
    `status: "skipped"` with null `enter`/`exit`."""
    _patch_plan(monkeypatch, None)

    chapter = make_chapter(
        "v4v1fields", [("B1", lambda emu: None), ("B2", lambda emu: None),
                        ("B3", lambda emu: None)])
    rom = make_rom(tmp_path / "rom.gba")
    out = tmp_path / "out"

    first = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                         emulator_factory=fake_factory_v4)
    assert first.verdict == "pass"

    second = run_chapter(chapter, rom, tmp_path / "engine", output_root=out,
                          emulator_factory=fake_factory_v4, from_beat="B2")
    assert second.verdict == "pass"

    obs = _observed(out, "v4v1fields")
    assert obs["chapter"] == "v4v1fields"
    assert isinstance(obs["rom_sha256"], str) and len(obs["rom_sha256"]) == 64
    assert isinstance(obs["generated_at"], str) and obs["generated_at"]
    assert obs["from_beat"] == "B2"

    b1 = _beat("B1", obs)
    assert b1["status"] == "skipped"
    assert b1["enter"] is None
    assert b1["exit"] is None

    b2 = _beat("B2", obs)
    assert b2["status"] == "pass"
    assert b2["enter"] is not None and b2["exit"] is not None
    assert set(b2["enter"]) == {"map_group", "map_num", "player_pos"}

    b3 = _beat("B3", obs)
    assert b3["status"] == "pass"
