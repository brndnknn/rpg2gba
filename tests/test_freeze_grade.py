"""Tests for `rpg2gba.playtest.freeze_grade` (REDERIVATION_PLAN.md §16.3 C9).

Synthetic unit tests exercise `grade_chapter` directly with hand-built
`FrozenBeat`/`Beat`/`Chapter`/`RowFloor` fixtures and a monkeypatched
`floor_for_row`, so nothing here touches the real build corpus. The one
real-data test at the bottom parametrizes over `gen_chapter_names()` and
is skipped when `output/uranium-build` is absent, matching the pattern in
`test_beat_floor_walk.py`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.beat_floor.assertion import FloorAssertion, FloorRefusal, RowFloor, make_params
from rpg2gba.playtest import freeze_grade
from rpg2gba.playtest.chapter import Beat, Chapter, gen_chapter_names
from rpg2gba.playtest.hand_freeze import FrozenBeat

ROW = "map001/ev001/p0"
BUILD_DIR = Path("output/uranium-build")


def _frozen(chapter: str, name: str, rows: tuple[str, ...]) -> FrozenBeat:
    return FrozenBeat(chapter=chapter, name=name, order=0, group=None,
                       map_constant=None, rows=rows)


def _beat(name: str, rows: tuple[str, ...] = (),
          assertions: frozenset[FloorAssertion] | None = None) -> Beat:
    return Beat(name=name, description="", run=lambda emu: None,
                rows=rows, assertions=assertions)


def _chapter(name: str, beats: tuple[Beat, ...]) -> Chapter:
    return Chapter(name=name, doc="reference/chapters/x.md", beats=beats)


def _warp_assertion(row_id: str = ROW, **overrides) -> FloorAssertion:
    params = dict(map_id=51, x=3, y=4, direction=2)
    params.update(overrides)
    return FloorAssertion(row_id=row_id, kind="warp", list_index=0, code=201,
                           params=make_params(**params), tag="position")


def _floor(row_id: str = ROW, assertions=(), refusals=()) -> RowFloor:
    return RowFloor(row_id=row_id, trigger="action",
                     assertions=frozenset(assertions), refusals=tuple(refusals))


def _patch_floor(monkeypatch, floors: dict[str, RowFloor]) -> None:
    def fake(row_id: str, *, build_dir=None, stripped_ce_ids=None) -> RowFloor:
        return floors[row_id]
    monkeypatch.setattr(freeze_grade, "floor_for_row", fake)


def _grade(chapter_id, frozen, residue, gen_chapter, never_fires=()):
    return freeze_grade.grade_chapter(
        chapter_id,
        frozen_beats=frozen,
        residue_entries=residue,
        gen_chapter=gen_chapter,
        never_fires=dict.fromkeys(never_fires, "proof") if not isinstance(never_fires, dict)
        else never_fires,
        build_dir=BUILD_DIR,
    )


# --- rule (a): row coverage ------------------------------------------------

def test_covered_row_passes(monkeypatch):
    assertion = _warp_assertion()
    _patch_floor(monkeypatch, {ROW: _floor(assertions=(assertion,))})
    gen = _chapter("CH01", (_beat("B1", rows=(ROW,), assertions=frozenset({assertion})),))
    frozen = [_frozen("CH01", "B1", (ROW,))]
    assert _grade("CH01", frozen, {}, gen) == []


def test_missing_row_reported(monkeypatch):
    _patch_floor(monkeypatch, {})
    gen = _chapter("CH01", (_beat("B1", rows=(), assertions=None),))
    frozen = [_frozen("CH01", "B1", (ROW,))]
    problems = _grade("CH01", frozen, {}, gen)
    assert len(problems) == 1
    assert ROW in problems[0]
    assert "CH01:B1" in problems[0]


def test_never_fires_row_satisfies_coverage(monkeypatch):
    _patch_floor(monkeypatch, {})
    gen = _chapter("CH01", (_beat("B1", rows=(), assertions=None),))
    frozen = [_frozen("CH01", "B1", (ROW,))]
    assert _grade("CH01", frozen, {}, gen, never_fires={ROW: "arrival-nudge, no warp lands here"}) == []


def test_row_both_claimed_and_never_fires_is_a_contradiction(monkeypatch):
    assertion = _warp_assertion()
    _patch_floor(monkeypatch, {ROW: _floor(assertions=(assertion,))})
    gen = _chapter("CH01", (_beat("B1", rows=(ROW,), assertions=frozenset({assertion})),))
    frozen = [_frozen("CH01", "B1", (ROW,))]
    problems = _grade("CH01", frozen, {}, gen, never_fires={ROW: "proof"})
    assert len(problems) == 1
    assert "NEVER_FIRES" in problems[0] and ROW in problems[0]


def test_residue_cited_row_is_graded(monkeypatch):
    _patch_floor(monkeypatch, {})
    gen = _chapter("CH01", (_beat("B1", rows=(), assertions=None),))
    residue = {
        "CH01:B6": {"ruling": "covered_elsewhere", "rows": [ROW], "note": "x"},
    }
    problems = _grade("CH01", [], residue, gen)
    assert len(problems) == 1
    assert ROW in problems[0]


def test_residue_ruling_without_rows_needs_nothing(monkeypatch):
    _patch_floor(monkeypatch, {})
    gen = _chapter("CH01", (_beat("B1", rows=(), assertions=None),))
    residue = {"CH01:B31": {"ruling": "bgm_debt", "note": "vacuous until BGM mapped"}}
    assert _grade("CH01", [], residue, gen) == []


def test_residue_row_covered_by_own_beat_passes(monkeypatch):
    assertion = _warp_assertion()
    _patch_floor(monkeypatch, {ROW: _floor(assertions=(assertion,))})
    gen = _chapter("CH01", (_beat("B1", rows=(ROW,), assertions=frozenset({assertion})),))
    residue = {"CH01:B6": {"ruling": "covered_elsewhere", "rows": [ROW], "note": "x"}}
    assert _grade("CH01", [], residue, gen) == []


def test_other_chapter_frozen_rows_ignored(monkeypatch):
    """A frozen beat belonging to a different chapter never constrains this
    chapter's grade (each chapter is graded against its own frozen rows)."""
    _patch_floor(monkeypatch, {})
    gen = _chapter("CH01", (_beat("B1", rows=(), assertions=None),))
    frozen = [_frozen("CH02", "B1", (ROW,))]
    assert _grade("CH01", frozen, {}, gen) == []


# --- inherited beats: ignored on both sides ---------------------------------

def test_inherited_beat_claim_does_not_satisfy_row_coverage(monkeypatch):
    """A row only claimed by an inherited `<OWNER>:` beat is NOT covered --
    inherited beats are ignored on both sides of the grade (R12 amended)."""
    _patch_floor(monkeypatch, {})
    gen = _chapter("CH02", (_beat("CH01:B1", rows=(ROW,), assertions=frozenset()),))
    frozen = [_frozen("CH02", "B1", (ROW,))]
    problems = _grade("CH02", frozen, {}, gen)
    assert len(problems) == 1
    assert ROW in problems[0]


def test_inherited_beat_claim_is_not_checked_for_floor_ge(monkeypatch):
    """An inherited beat's own (possibly uncovering) claim on a row is not
    graded by rule (b) either -- only OWN beats' claims are."""
    def boom(row_id, *, build_dir=None, stripped_ce_ids=None):
        raise AssertionError("floor_for_row should not be called for an inherited-only row")
    monkeypatch.setattr(freeze_grade, "floor_for_row", boom)
    gen = _chapter("CH02", (_beat("CH01:B1", rows=(ROW,), assertions=None),))
    assert _grade("CH02", [], {}, gen) == []


# --- rule (b): floor ⊇ -------------------------------------------------------

def test_no_assertions_declared_is_a_problem(monkeypatch):
    _patch_floor(monkeypatch, {ROW: _floor(assertions=(_warp_assertion(),))})
    gen = _chapter("CH01", (_beat("B1", rows=(ROW,), assertions=None),))
    problems = _grade("CH01", [], {}, gen)
    assert len(problems) == 1
    assert "none of them declares" in problems[0]


def test_undercovering_declared_assertion_is_a_problem(monkeypatch):
    floor_assertion = _warp_assertion(direction=2)
    _patch_floor(monkeypatch, {ROW: _floor(assertions=(floor_assertion,))})
    # Declared assertion has a different key entirely, so covers() can never
    # match it against the floor's warp assertion.
    other_kind = FloorAssertion(row_id=ROW, kind="heal_party", list_index=1, code=105)
    gen = _chapter("CH01", (_beat("B1", rows=(ROW,), assertions=frozenset({other_kind})),))
    problems = _grade("CH01", [], {}, gen)
    assert len(problems) == 1
    assert "not declared at all" in problems[0]


def test_contradicting_declared_assertion_is_reported_as_contradiction(monkeypatch):
    floor_assertion = _warp_assertion(direction=2)
    contradicting = _warp_assertion(direction=9)  # same key, wrong value
    _patch_floor(monkeypatch, {ROW: _floor(assertions=(floor_assertion,))})
    gen = _chapter("CH01", (_beat("B1", rows=(ROW,), assertions=frozenset({contradicting})),))
    problems = _grade("CH01", [], {}, gen)
    assert len(problems) == 1
    assert "contradict" in problems[0]


def test_refused_floor_on_claimed_row_is_reported_distinctly(monkeypatch):
    refusal = FloorRefusal(row_id=ROW, reason="no_extractor", list_index=0, code=999,
                            detail="unhandled command")
    _patch_floor(monkeypatch, {ROW: _floor(refusals=(refusal,))})
    gen = _chapter("CH01", (_beat("B1", rows=(ROW,), assertions=frozenset()),))
    problems = _grade("CH01", [], {}, gen)
    assert len(problems) == 1
    assert "refuses" in problems[0]


def test_multiple_own_beats_claiming_same_row_union_their_assertions(monkeypatch):
    # Two beats each declare half of the floor's two assertions; together
    # they cover it, and the ⊇ rule only asks about the union.
    a1 = _warp_assertion()
    a2 = FloorAssertion(row_id=ROW, kind="heal_party", list_index=1, code=105)
    _patch_floor(monkeypatch, {ROW: _floor(assertions=(a1, a2))})
    gen = _chapter("CH01", (
        _beat("B1", rows=(ROW,), assertions=frozenset({a1})),
        _beat("B2", rows=(ROW,), assertions=frozenset({a2})),
    ))
    assert _grade("CH01", [], {}, gen) == []


# --- real-data smoke test ----------------------------------------------------

@pytest.mark.parametrize("chapter", gen_chapter_names())
def test_real_generated_chapters_are_green(chapter):
    # Collects zero test cases while chapters_gen/ is empty (the ordinary
    # state before C9 lands a chapter) -- that is a pass with nothing to
    # run, not a failure. Once modules land here, each one is its own case.
    if not (BUILD_DIR / "maps").exists():
        pytest.skip("no converted map corpus at output/uranium-build/maps")
    problems = freeze_grade.grade_chapter_from_disk(chapter.upper())
    assert problems == []
