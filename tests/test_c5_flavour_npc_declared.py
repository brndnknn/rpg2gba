"""Tests for the `flavour_npc` template's C5 refactor
(REDERIVATION_PLAN.md §16.3 C5): every registered beat declares
`assertions=` in the generic beat floor's vocabulary, and the beat BODY
actually checks every kind it declares.

Two kinds of coverage:

- Registration-level (skipped without staged `output/uranium-build/`,
  same convention as `tests/test_playtest_archetype_templates.py`): real
  plain / toggling / randomized instances from CH01/CH03's committed
  manifests, checking the declared kinds and that
  `beat_floor.coverage.uncovered` is empty (or exactly the documented
  intentionally-undeclared set).
- Body-level, with a duck-typed fake emulator (no `mgba` import, mirroring
  `tests/test_playtest_assertions.py::_FakeEmu`): proves `_walk_text_boxes`
  -- the helper every non-randomized beat body calls -- actually fails when
  the live text disagrees with a declared value, for both the first and a
  SECOND message box.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.beat_floor.coverage import uncovered
from rpg2gba.beat_floor.lookup import floor_for_row
from rpg2gba.chapter_manifest.schema import ManifestRow, row_from_dict
from rpg2gba.playtest.archetypes.flavour_npc import (
    _assert_one_of,
    _walk_text_boxes,
    flavour_npc_beat,
)
from rpg2gba.playtest.chapter import ChapterBuilder
from rpg2gba.playtest.errors import ScenarioError

_BUILD_OK = Path("output/uranium-build/porymap/map_constants.json").exists()
pytestmark_registration = pytest.mark.skipif(
    not _BUILD_OK,
    reason="requires staged pipeline output (output/uranium-build/) to "
           "resolve coordinates via playtest.cells and floors via beat_floor",
)


def _builder(name: str = "CHZZ_TEST") -> ChapterBuilder:
    return ChapterBuilder(name, doc="test-only, not a real chapter doc")


def _manifest_rows(chapter_id: str) -> tuple[ManifestRow, ...]:
    path = Path(f"reference/manifests/{chapter_id}.manifest.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return tuple(row_from_dict(e) for e in raw)


# -- registration-level: real instances -------------------------------------


@pytestmark_registration
def test_plain_multibox_instance_declares_and_covers_every_text_box() -> None:
    """`map050/ev005/p7` (CH01, MAP_MOKI_TOWN_PROFESSOR_LAB) is a plain
    flavour NPC whose floor has TWO trunk-level `text` assertions -- the
    old template only ever checked `expected_lines[0]`."""
    rows = _manifest_rows("CH01")
    b = _builder()
    flavour_npc_beat(
        b, chapter_id="CH01", map_constant="MAP_MOKI_TOWN_PROFESSOR_LAB",
        map_id=50, event_id=5, beat_name="T2_test_plain_multibox",
        page_idx=7, manifest_rows=rows,
    )
    chapter = b.build()
    assert [beat.name for beat in chapter.beats] == ["T2_test_plain_multibox"]
    beat = chapter.beats[0]
    assert beat.rows == ("map050/ev005/p7",)
    assert beat.assertions is not None
    kinds = {a.kind for a in beat.assertions}
    assert kinds == {"trigger", "completes", "text", "visual"}
    text_assertions = sorted(
        (a for a in beat.assertions if a.kind == "text"),
        key=lambda a: a.param("index"))
    assert [a.param("index") for a in text_assertions] == [0, 1]

    floor = floor_for_row("map050/ev005/p7")
    assert uncovered(floor, beat.assertions) == ()


@pytestmark_registration
def test_toggling_trunk_instance_declares_self_switch_and_claims_second_row() -> None:
    """`map031/ev048` (CH03, MAP_KEVLAR_TOWN) is the textbook trunk-level
    toggling instance (no branch arms on either page): p0 sets self-switch
    A true, p1 -- its own manifest row -- sets it back false. Both should
    now be claimed and declared, where the old template left the second
    beat with `rows=()`."""
    rows = _manifest_rows("CH03")
    b = _builder()
    flavour_npc_beat(
        b, chapter_id="CH03", map_constant="MAP_KEVLAR_TOWN",
        map_id=31, event_id=48, beat_name="T2_test_toggle",
    )
    chapter = b.build()
    names = [beat.name for beat in chapter.beats]
    assert names == ["T2_test_toggle", "T2_test_toggle_again"]
    talk, again = chapter.beats

    assert talk.rows == ("map031/ev048/p0",)
    talk_kinds = {a.kind for a in talk.assertions}
    assert talk_kinds == {"trigger", "completes", "text", "self_switch_write", "visual"}
    floor0 = floor_for_row("map031/ev048/p0")
    assert uncovered(floor0, talk.assertions) == ()

    # The second row is now claimed -- this is the item-3 behaviour change.
    assert again.rows == ("map031/ev048/p1",)
    again_kinds = {a.kind for a in again.assertions}
    assert again_kinds == {"trigger", "completes", "text", "self_switch_write", "visual"}
    floor1 = floor_for_row("map031/ev048/p1")
    assert uncovered(floor1, again.assertions) == ()


@pytestmark_registration
def test_randomized_instance_leaves_arm_text_undeclared() -> None:
    """`map032/ev012` (CH01, MAP_MOKI_TOWN) is randomized: a trunk `var_write`
    picks an index into three branch-arm candidates. Only one arm's text is
    ever observed per run, so none of them can be honestly declared as
    individually covered -- the beat declares nothing for `text` at all,
    matching the row's floor having no trunk-level text either."""
    rows = _manifest_rows("CH01")
    b = _builder()
    flavour_npc_beat(
        b, chapter_id="CH01", map_constant="MAP_MOKI_TOWN",
        map_id=32, event_id=12, beat_name="T2_test_random",
        manifest_rows=rows,
    )
    chapter = b.build()
    beat = chapter.beats[0]
    assert beat.rows == ("map032/ev012/p0",)
    kinds = {a.kind for a in beat.assertions}
    # var_write is intentionally never declared (task item 1: ROM-only,
    # and the value it picks isn't checked by this template's body).
    assert kinds == {"trigger", "completes", "visual"}
    floor = floor_for_row("map032/ev012/p0")
    # The trunk floor's own var_write is the only assertion this row has
    # beyond trigger/completes/visual, so it is the one documented gap.
    missing_kinds = {a.kind for a in uncovered(floor, beat.assertions)}
    assert missing_kinds == {"var_write"}


@pytestmark_registration
def test_arm_nested_toggling_instance_declares_nothing_extra_for_arms() -> None:
    """`map064/ev001` (CH01, MAP_MOKI_TOWN_HOUSE_2) is the arm-nested
    toggling instance: the trunk page carries no text/self_switch_write of
    its own (both live on `p0/b0`/`p0/b1`), so the template can only
    declare what the trunk floor actually has."""
    rows = _manifest_rows("CH01")
    b = _builder()
    flavour_npc_beat(
        b, chapter_id="CH01", map_constant="MAP_MOKI_TOWN_HOUSE_2",
        map_id=64, event_id=1, beat_name="T2_test_arm_toggle",
        manifest_rows=rows,
    )
    chapter = b.build()
    talk = chapter.beats[0]
    assert talk.rows == ("map064/ev001/p0",)
    kinds = {a.kind for a in talk.assertions}
    assert kinds == {"trigger", "completes", "visual"}
    floor0 = floor_for_row("map064/ev001/p0")
    # Nothing left uncovered on the TRUNK row -- the branch arms are simply
    # never claimed, by design (module docstring); this only proves the
    # trunk-only declaration is itself honest.
    assert uncovered(floor0, talk.assertions) == ()


# -- body-level: fake emulator, no mgba import -------------------------------


class _FakeEmu:
    """Minimal stand-in for the field-message primitives `_walk_text_boxes`
    and `_assert_one_of` read: `wait_for_field_message`, `clear_field_message`,
    `tap`, `advance_dialog`, `assert_text_contains`, `screenshot`. Mirrors a
    fixed script of message-box contents, advanced one box per `tap("A")`.
    """

    def __init__(self, boxes: list[str]) -> None:
        self._boxes = boxes
        self._index = 0
        self.screenshots: list[str] = []
        self.advance_calls = 0

    def wait_for_field_message(self, frame_budget: int = 180) -> str | None:
        if self._index >= len(self._boxes):
            return None
        return self._boxes[self._index]

    def clear_field_message(self) -> None:
        pass

    def tap(self, key: str = "A") -> None:
        self._index += 1

    def advance_dialog(self, key: str = "A", max_taps: int = 1500, stop=None) -> int:
        self.advance_calls += 1
        return 0

    def assert_text_contains(self, expected: str, *, exact: bool = False,
                              verbatim: bool = False) -> None:
        actual = self.wait_for_field_message()
        if actual is None or expected not in actual:
            raise ScenarioError(f"expected {expected!r}, got {actual!r}")

    def screenshot(self, name: str) -> str:
        self.screenshots.append(name)
        return f"/tmp/{name}.png"


def test_walk_text_boxes_passes_when_every_box_matches() -> None:
    emu = _FakeEmu(["Hello there.", "Second line."])
    _walk_text_boxes(emu, "beat", "row/p0", ("Hello there.", "Second line."))
    assert emu.advance_calls == 1


def test_walk_text_boxes_fails_on_first_box_mismatch() -> None:
    emu = _FakeEmu(["Something else entirely.", "Second line."])
    with pytest.raises(ScenarioError, match="message box 0"):
        _walk_text_boxes(emu, "beat", "row/p0", ("Hello there.", "Second line."))


def test_walk_text_boxes_fails_on_second_box_mismatch() -> None:
    """The first box matches; only the SECOND is wrong -- proves the body
    checks every declared box, not only the first, per task item 1."""
    emu = _FakeEmu(["Hello there.", "A different second line."])
    with pytest.raises(ScenarioError, match="message box 1"):
        _walk_text_boxes(emu, "beat", "row/p0", ("Hello there.", "Second line."))
    # Advancing past box 0 happened (tap called), but the failure on box 1
    # means advance_dialog (the final drain) never ran.
    assert emu.advance_calls == 0


def test_assert_one_of_passes_on_any_candidate() -> None:
    emu = _FakeEmu(["The second candidate."])
    _assert_one_of(emu, "beat", ("First.", "The second candidate.", "Third."), "row/p0")


def test_assert_one_of_fails_when_no_candidate_matches() -> None:
    emu = _FakeEmu(["Something unrelated."])
    with pytest.raises(ScenarioError, match="matches none of its"):
        _assert_one_of(emu, "beat", ("First.", "Second."), "row/p0")
