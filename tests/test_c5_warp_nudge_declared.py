"""Tests for the `warp`/`arrival_nudge` templates' C5 refactor
(REDERIVATION_PLAN.md §16.3 C5): every registered beat declares
`assertions=` in the generic beat floor's vocabulary, and the beat BODY
actually checks every kind it declares.

Mirrors `tests/test_c5_flavour_npc_declared.py`'s structure (not imported
from -- copied per the task brief):

- Registration-level (skipped without staged `output/uranium-build/`, same
  convention as `tests/test_playtest_archetype_templates.py`): real
  instances from CH05's manifest (generated in memory, same reason
  `test_playtest_archetype_templates.py`'s own `ch05_rows` fixture does --
  CH05 has no committed manifest yet), checking declared kinds and that
  `beat_floor.coverage.uncovered` is empty for every claimed row.
- Registration-time fail-loud: a `floor_lookup=` that disagrees with the
  derived cells, or carries an ambiguous displacement.
- Body-level, with a duck-typed fake emulator (no `mgba` import): proves the
  nudge body fails on the wrong `(dx, dy)` and the warp body fails on the
  wrong arrival.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.beat_floor.assertion import FloorAssertion, RowFloor, make_params
from rpg2gba.beat_floor.coverage import uncovered
from rpg2gba.beat_floor.lookup import floor_for_row
from rpg2gba.chapter_manifest.generator import generate_chapter_manifest
from rpg2gba.chapter_manifest.schema import ManifestRow
from rpg2gba.playtest import assertions as real_assertions
from rpg2gba.playtest.archetypes.arrival_nudge import arrival_nudge_beat
from rpg2gba.playtest.archetypes.warp import warp_beat
from rpg2gba.playtest.chapter import ChapterBuilder
from rpg2gba.playtest.errors import ScenarioError

_BUILD_DIR = Path("output/uranium-build")
_CHAPTERS_PATH = Path("reference/chapters.json")

pytestmark = pytest.mark.skipif(
    not Path("output/uranium-build/porymap/map_constants.json").exists(),
    reason="requires staged pipeline output (output/uranium-build/) to "
           "resolve coordinates via playtest.cells and floors via beat_floor",
)


@pytest.fixture(scope="module")
def ch05_rows() -> tuple[ManifestRow, ...]:
    return tuple(generate_chapter_manifest(
        "CH05", build_dir=_BUILD_DIR, chapters_path=_CHAPTERS_PATH))


def _builder(name: str = "CHZZ_TEST") -> ChapterBuilder:
    return ChapterBuilder(name, doc="test-only, not a real chapter doc")


def _noop(*args, **kwargs) -> None:
    return None


# -- registration-level: real instances --------------------------------------


def test_warp_beat_declares_and_covers_the_claimed_row(
    ch05_rows: tuple[ManifestRow, ...],
) -> None:
    b = _builder()
    warp_beat(
        b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F", map_id=36,
        event_id=1, dest_map_constant="MAP_ROUTE_02", mechanism="threshold",
        direction="DOWN", beat_name="W1", manifest_rows=ch05_rows,
    )
    beat = _builder_result_beat(b)
    assert beat.rows == ("map036/ev001/p0",)
    kinds = {a.kind for a in beat.assertions}
    assert kinds == {"trigger", "completes", "warp", "visual"}
    floor = floor_for_row("map036/ev001/p0")
    assert uncovered(floor, beat.assertions) == ()


def test_warp_beat_facing_and_bgm_extras_strengthen_the_warp_assertion(
    ch05_rows: tuple[ManifestRow, ...],
) -> None:
    b = _builder()
    warp_beat(
        b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F", map_id=36,
        event_id=1, dest_map_constant="MAP_ROUTE_02", mechanism="threshold",
        direction="DOWN", beat_name="W1", manifest_rows=ch05_rows,
        assert_facing=True, assert_bgm=True, dest_engine_map_dir="Route02",
    )
    beat = _builder_result_beat(b)
    warp_assertions = [a for a in beat.assertions if a.kind == "warp"]
    assert len(warp_assertions) == 1
    params = dict(warp_assertions[0].params)
    assert params["arrival_facing"] in ("UP", "DOWN", "LEFT", "RIGHT")
    assert params["bgm"] == "Route02"
    # Still covers the source floor's own (map_id, x, y, direction) --
    # extras strengthen, they never replace (coverage.py's own contract).
    floor = floor_for_row("map036/ev001/p0")
    assert uncovered(floor, beat.assertions) == ()


def test_arrival_nudge_beat_claims_walked_arm_and_covers_both_rows(
    ch05_rows: tuple[ManifestRow, ...],
) -> None:
    """`map036/ev002/p1`'s own floor is bare (trigger/completes only) --
    the move route lives on `p1/b0`, the arm a fresh arrival walks -- so the
    beat must claim BOTH rows and cover both, not just the page (task brief
    point 6)."""
    b = _builder()
    arrival_nudge_beat(
        b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F", map_id=36,
        event_id=2, from_map_constant="MAP_PASSAGE_CAVE_2F",
        beat_name="N1", manifest_rows=ch05_rows,
    )
    beat = _builder_result_beat(b)
    assert beat.rows == ("map036/ev002/p1", "map036/ev002/p1/b0")
    kinds = {a.kind for a in beat.assertions}
    assert kinds == {"trigger", "completes", "visual", "displacement"}
    for row in beat.rows:
        floor = floor_for_row(row)
        assert uncovered(floor, beat.assertions) == ()


def _builder_result_beat(builder: ChapterBuilder):
    chapter = builder.build()
    assert len(chapter.beats) == 1
    return chapter.beats[0]


# -- registration-time fail-loud: floor_lookup injection ---------------------


def test_warp_beat_fails_loud_when_floor_disagrees_with_derived_arrival(
    ch05_rows: tuple[ManifestRow, ...],
) -> None:
    real_floor = floor_for_row("map036/ev001/p0")

    def _bad_lookup(row_id: str) -> RowFloor:
        if row_id != "map036/ev001/p0":
            return floor_for_row(row_id)
        bad_assertions = set()
        for a in real_floor.assertions:
            if a.kind == "warp":
                params = dict(a.params)
                params["x"] = params["x"] + 1  # deliberately wrong
                a = FloorAssertion(
                    row_id=a.row_id, kind=a.kind, list_index=a.list_index,
                    code=a.code, params=make_params(**params), tag=a.tag,
                )
            bad_assertions.add(a)
        return RowFloor(
            row_id=real_floor.row_id, trigger=real_floor.trigger,
            assertions=frozenset(bad_assertions), refusals=real_floor.refusals,
        )

    b = _builder()
    with pytest.raises(ValueError, match="disagrees with"):
        warp_beat(
            b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F",
            map_id=36, event_id=1, dest_map_constant="MAP_ROUTE_02",
            mechanism="threshold", direction="DOWN", beat_name="W1",
            manifest_rows=ch05_rows, floor_lookup=_bad_lookup,
        )


def test_arrival_nudge_beat_fails_loud_on_ambiguous_player_displacement(
    ch05_rows: tuple[ManifestRow, ...],
) -> None:
    """A synthetic floor carrying TWO `target=-1` displacement assertions on
    the same walked arm -- this body checks exactly one player landing, so
    two candidates is a fingerprint match this archetype cannot honestly
    assert against (task brief point 5's own `_player_displacement`)."""
    real_arm = floor_for_row("map036/ev002/p1/b0")
    real_disp = next(a for a in real_arm.assertions if a.kind == "displacement")
    duplicate = FloorAssertion(
        row_id=real_disp.row_id, kind="displacement", list_index=99,
        code=real_disp.code, params=real_disp.params, tag=real_disp.tag,
    )
    bad_arm = RowFloor(
        row_id=real_arm.row_id, trigger=real_arm.trigger,
        assertions=frozenset(real_arm.assertions | {duplicate}),
        refusals=real_arm.refusals,
    )

    def _bad_lookup(row_id: str) -> RowFloor:
        if row_id == "map036/ev002/p1/b0":
            return bad_arm
        return floor_for_row(row_id)

    b = _builder()
    with pytest.raises(ValueError, match="player.*displacement assertions"):
        arrival_nudge_beat(
            b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F",
            map_id=36, event_id=2, from_map_constant="MAP_PASSAGE_CAVE_2F",
            beat_name="N1", manifest_rows=ch05_rows, floor_lookup=_bad_lookup,
        )


# -- body-level: fake emulator, no mgba import -------------------------------


class _FakeFacingObjectEvent:
    def __init__(self, facing: str) -> None:
        self.facing = facing


class _FakeEmu:
    """Minimal stand-in for the primitives the warp/nudge bodies read at
    the point this test exercises: `settle_field`, `player_pos`,
    `screenshot`, `resolve_constant`, `object_event`."""

    def __init__(self, pos: tuple[int, int], facing: str = "DOWN") -> None:
        self._pos = pos
        self._facing = facing
        self.screenshots: list[str] = []

    def settle_field(self, **kwargs) -> int:
        return 0

    def player_pos(self):
        return (0, 0)

    def player_pos(self) -> tuple[int, int]:
        return self._pos

    def screenshot(self, name: str) -> str:
        self.screenshots.append(name)
        return f"/tmp/{name}.png"

    def resolve_constant(self, name: str) -> str:
        return name

    def object_event(self, local_id) -> _FakeFacingObjectEvent:
        return _FakeFacingObjectEvent(self._facing)


def test_warp_beat_body_fails_on_wrong_arrival(
    ch05_rows: tuple[ManifestRow, ...], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves the exactness switch (task brief point 1): a landing that is
    only ONE tile off -- which `assert_near`'s old tolerance-1 check would
    have passed -- must now fail."""
    from rpg2gba.playtest.cells import arrival_cell

    b = _builder()
    warp_beat(
        b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F", map_id=36,
        event_id=1, dest_map_constant="MAP_ROUTE_02", mechanism="threshold",
        direction="DOWN", beat_name="W1", manifest_rows=ch05_rows,
    )
    beat = _builder_result_beat(b)

    true_arrival = arrival_cell(
        "MAP_ROUTE_02", from_map="MAP_PASSAGE_CAVE_1F", event_id=1)
    wrong_but_near = (true_arrival[0] + 1, true_arrival[1])

    monkeypatch.setattr(real_assertions, "cross_threshold", _noop)
    monkeypatch.setattr(real_assertions, "require_map", _noop)

    emu = _FakeEmu(wrong_but_near)
    with pytest.raises(ScenarioError, match="expected exactly"):
        beat.run(emu)


def test_arrival_nudge_beat_body_fails_on_wrong_displacement(
    ch05_rows: tuple[ManifestRow, ...], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The declared floor delta is `(dx=0, dy=1)` (task brief point 5) --
    landing at `(dx=1, dy=0)` instead is still Manhattan distance 1 off the
    arrival cell (what the old nudged=True check alone would have accepted)
    but is the WRONG tile, and must fail."""
    from rpg2gba.playtest.cells import arrival_cell

    b = _builder()
    arrival_nudge_beat(
        b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F", map_id=36,
        event_id=2, from_map_constant="MAP_PASSAGE_CAVE_2F",
        beat_name="N1", manifest_rows=ch05_rows,
    )
    beat = _builder_result_beat(b)

    arrival = arrival_cell(
        "MAP_PASSAGE_CAVE_1F", from_map="MAP_PASSAGE_CAVE_2F", event_id=None)
    wrong_but_manhattan_one = (arrival[0] + 1, arrival[1])

    monkeypatch.setattr(real_assertions, "require_map", _noop)
    monkeypatch.setattr(real_assertions, "assert_arrival_settled", _noop)

    emu = _FakeEmu(wrong_but_manhattan_one, facing="DOWN")
    with pytest.raises(ScenarioError, match="expected exactly"):
        beat.run(emu)


def test_arrival_nudge_beat_body_passes_on_the_correct_displacement(
    ch05_rows: tuple[ManifestRow, ...], monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rpg2gba.playtest.cells import arrival_cell

    b = _builder()
    arrival_nudge_beat(
        b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F", map_id=36,
        event_id=2, from_map_constant="MAP_PASSAGE_CAVE_2F",
        beat_name="N1", manifest_rows=ch05_rows,
    )
    beat = _builder_result_beat(b)

    arrival = arrival_cell(
        "MAP_PASSAGE_CAVE_1F", from_map="MAP_PASSAGE_CAVE_2F", event_id=None)
    correct = (arrival[0], arrival[1] + 1)  # floor's (dx=0, dy=1)

    monkeypatch.setattr(real_assertions, "require_map", _noop)
    monkeypatch.setattr(real_assertions, "assert_arrival_settled", _noop)

    emu = _FakeEmu(correct, facing="DOWN")
    beat.run(emu)  # must not raise


def test_warp_beat_checks_the_page_state_write_after_the_crossing(monkeypatch) -> None:
    """The lab exit (map050/ev001/p1) turns switch 104 on as it transfers:
    declared, and read with the generic handler once the player has landed."""
    from rpg2gba.playtest.archetypes import generic

    b = _builder()
    warp_beat(
        b, chapter_id="CH01", map_constant="MAP_MOKI_TOWN_PROFESSOR_LAB", map_id=50,
        event_id=1, page_idx=1, dest_map_constant="MAP_MOKI_TOWN",
        mechanism="threshold", direction="DOWN", beat_name="W1",
    )
    beat = _builder_result_beat(b)
    assert "switch_write" in {a.kind for a in beat.assertions}
    assert uncovered(floor_for_row("map050/ev001/p1"), beat.assertions) == ()

    seen: list[tuple[str, object]] = []
    monkeypatch.setitem(generic.STEP_HANDLERS, "switch_write",
                        lambda emu, name, step: seen.append(
                            (step.kind, dict(step.params)["switch_id"])))
    for helper in ("cross_threshold", "require_map", "assert_position_exact"):
        monkeypatch.setattr(real_assertions, helper, _noop)

    class _Emu:
        def settle_field(self):
            return 0

        def player_pos(self):
            return (0, 0)

    beat.run(_Emu())
    assert seen == [("switch_write", 104)]
