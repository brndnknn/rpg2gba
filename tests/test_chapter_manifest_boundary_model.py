"""`chapter_manifest.boundary_model` -- the concrete `checker.BoundaryModel`.

The adapter answers three questions for the `boundary` verdict
(PROJECT_TODO #72/#73): is a row really a forward crossing (derived from
`slice_growth`/`seam_growth`), does the successor chapter exist at all
(`chapter_atlas.binding.ChapterBinding.successor`), and does some beat it
registers actually claim the row.

`ChapterBoundaryModel` itself is tested directly, against fake chapter
modules installed into `sys.modules` (the same technique
`test_chapter_manifest_beat_model.py` uses), so the "successor claims it"
half doesn't need a real playtest chapter. `build_boundary_model` is tested
against the real repo state (real `reference/chapters.json`, real
`output/uranium-build/`), the same way `test_chapter_manifest_beat_model.py`
pins real `ch04.py`'s state -- there is no synthetic-fixture path for the
slice/seam growth detectors, which read the committed corpus by design.
"""
from __future__ import annotations

import sys
import types

from rpg2gba.chapter_manifest.boundary_model import (
    ChapterBoundaryModel,
    build_boundary_model,
)
from rpg2gba.playtest.chapter import ChapterBuilder

PKG = "rpg2gba.playtest.chapters_gen"  # the default suite since 2026-10-03


def _run(emu: object) -> None:  # pragma: no cover - never executed
    raise AssertionError("beat body must not run in this test")


def _install_chapter(name: str, rows_by_beat: dict[str, tuple[str, ...]]) -> None:
    """Fake a chapter module whose beats each claim the given `rows=`."""
    builder = ChapterBuilder(name, f"{name} test chapter")
    for beat_name, rows in rows_by_beat.items():
        builder.beat(beat_name, f"{beat_name} description", rows=rows)(_run)
    module = types.ModuleType(f"{PKG}.{name}")
    module.CHAPTER = builder.build()  # type: ignore[attr-defined]
    sys.modules[f"{PKG}.{name}"] = module


def _cleanup_chapter(name: str) -> None:
    sys.modules.pop(f"{PKG}.{name}", None)


# --- ChapterBoundaryModel: pure logic ---------------------------------------


def test_is_forward_crossing_reflects_the_supplied_row_set() -> None:
    model = ChapterBoundaryModel(
        "CHX", frozenset({"map001/ev001/p0"}), successor_id=None)
    assert model.is_forward_crossing("map001/ev001/p0") is True
    assert model.is_forward_crossing("map001/ev002/p0") is False


# --- is_forward_crossing: R3 event-level widening ---------------------------
#
# `map001/ev001/p0` is the only row the detectors ever actually tag as a
# crossing here; `p1` is a sibling page of the SAME event (the "arrival
# nudge autorun sitting next to the warp" shape), `map001/ev002/p0` is an
# unrelated event on the same map, and the seam/malformed cases probe the
# two row-id grammars `_event_key` must tell apart.


def test_is_forward_crossing_true_for_the_transfer_page_itself() -> None:
    model = ChapterBoundaryModel(
        "CHX", frozenset({"map001/ev001/p0"}), successor_id=None)
    assert model.is_forward_crossing("map001/ev001/p0") is True


def test_is_forward_crossing_true_for_a_sibling_page_of_the_same_event() -> None:
    model = ChapterBoundaryModel(
        "CHX", frozenset({"map001/ev001/p0"}), successor_id=None)
    assert model.is_forward_crossing("map001/ev001/p1") is True


def test_is_forward_crossing_false_for_an_unrelated_events_page() -> None:
    model = ChapterBoundaryModel(
        "CHX", frozenset({"map001/ev001/p0"}), successor_id=None)
    assert model.is_forward_crossing("map001/ev002/p0") is False


def test_is_forward_crossing_seam_row_still_matches_only_itself() -> None:
    model = ChapterBoundaryModel(
        "CHX", frozenset({"map001/seam/NORTH/map002"}), successor_id=None)
    assert model.is_forward_crossing("map001/seam/NORTH/map002") is True
    # A seam has no event to widen onto -- an unrelated page on the same map
    # must not be swept in just because the map number matches.
    assert model.is_forward_crossing("map001/ev001/p0") is False


def test_is_forward_crossing_malformed_row_id_fails_loud() -> None:
    model = ChapterBoundaryModel(
        "CHX", frozenset({"map001/ev001/p0"}), successor_id=None)
    try:
        model.is_forward_crossing("not-a-real-row-id")
    except ValueError as exc:
        assert "not-a-real-row-id" in str(exc)
    else:
        raise AssertionError("expected ValueError for a malformed row_id")


def test_successor_chapter_id_passes_through_unchanged() -> None:
    model = ChapterBoundaryModel("CHX", frozenset(), successor_id="CHY")
    assert model.successor_chapter_id() == "CHY"


def test_terminal_chapter_has_no_successor_module_and_claims_nothing() -> None:
    model = ChapterBoundaryModel("CHX", frozenset(), successor_id=None)
    assert model.successor_has_module() is False
    assert model.successor_claims("map001/ev001/p0") is False


def test_successor_naming_a_module_that_does_not_exist_is_unenforced() -> None:
    """A successor id with no playtest module at all is the ordinary state
    of a boundary row authored before its successor's beats exist -- not an
    error."""
    model = ChapterBoundaryModel(
        "CHX", frozenset(), successor_id="CH_NO_SUCH_CHAPTER")
    assert model.successor_has_module() is False
    assert model.successor_claims("map001/ev001/p0") is False


def test_successor_claims_come_from_its_registered_beats_rows() -> None:
    _install_chapter("boundaryplace1", {"B1": ("map010/ev001/p0",)})
    try:
        model = ChapterBoundaryModel(
            "CHX", frozenset(), successor_id="boundaryplace1")
        assert model.successor_has_module() is True
        assert model.successor_claims("map010/ev001/p0") is True
        assert model.successor_claims("map010/ev002/p0") is False
    finally:
        _cleanup_chapter("boundaryplace1")


def test_successor_claims_are_pooled_across_every_registered_beat() -> None:
    _install_chapter("boundaryplace2", {
        "B1": ("map010/ev001/p0",),
        "B2": ("map010/seam/NORTH/map011",),
    })
    try:
        model = ChapterBoundaryModel(
            "CHX", frozenset(), successor_id="boundaryplace2")
        assert model.successor_claims("map010/ev001/p0") is True
        assert model.successor_claims("map010/seam/NORTH/map011") is True
    finally:
        _cleanup_chapter("boundaryplace2")


# --- build_boundary_model: against the real, committed repo state ----------


def test_returns_none_for_a_chapter_with_no_gated_slice() -> None:
    """CH59 is `status: "planned"` in the real `reference/chapters.json` --
    no gated slice exists for it yet, so the crossing detectors have nothing
    to scan. CH59 is the last chapter in the chain, so this stays true until
    the corpus is finished. (Was the next-unbuilt chapter, bumped at every
    gate pass: CH06 → CH07 → CH07A → CH09; moved to the chain's end
    2026-10-23 when CH09's gate broke it.)"""
    assert build_boundary_model("CH59") is None


def test_real_ch04_forward_crossing_and_claim_state() -> None:
    """Pinned against real corpus state as of the #72/#73 investigation, and
    re-pinned for the R3 event-level widening: Map035 EV001's page 0
    (`map035/ev001/p0`) is the actual code-201 warp into CH05's cave, and
    page 1 (`map035/ev001/p1`) is the arrival-nudge autorun that fires
    alongside it -- not itself a transfer command, but a page of the SAME
    EVENT as the one that is, so `is_forward_crossing` now reports both
    (REDERIVATION_PLAN.md §10 R3: boundary-ness is a property of the event,
    not the individual page). CH04's successor is CH05, whose playtest
    module exists. Re-pinned 2026-09-14 when R2/R3 were implemented: CH05's
    `B1_in` claims p0 and `B1_nudge` claims p1, closing the #72/#73
    contradiction this test was first written to surface."""
    model = build_boundary_model("CH04")
    assert model is not None
    assert model.successor_chapter_id() == "CH05"
    assert model.is_forward_crossing("map035/ev001/p0") is True
    assert model.is_forward_crossing("map035/ev001/p1") is True
    assert model.successor_has_module() is True
    assert model.successor_claims("map035/ev001/p0") is True
    assert model.successor_claims("map035/ev001/p1") is True
