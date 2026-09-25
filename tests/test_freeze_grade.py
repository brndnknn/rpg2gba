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
#: A frozen CH01 beat claiming ROW, so rule (b) grades it (C9 ruling 6).
FROZEN = [FrozenBeat(chapter="CH01", name="B1", order=0, group=None,
                     map_constant=None, rows=(ROW,))]


def _frozen(chapter: str, name: str, rows: tuple[str, ...]) -> FrozenBeat:
    return FrozenBeat(chapter=chapter, name=name, order=0, group=None,
                       map_constant=None, rows=rows)


def _beat(name: str, rows: tuple[str, ...] = (),
          assertions: frozenset[FloorAssertion] | None = None,
          archetype: str | None = None) -> Beat:
    return Beat(name=name, description="", run=lambda emu: None,
                rows=rows, assertions=assertions, archetype=archetype)


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


def _grade_full(chapter_id, frozen, residue, gen_chapter, never_fires=(), successor=None,
                owners=()):
    return freeze_grade.grade_chapter(
        chapter_id,
        frozen_beats=frozen,
        residue_entries=residue,
        gen_chapter=gen_chapter,
        never_fires=dict.fromkeys(never_fires, "proof") if not isinstance(never_fires, dict)
        else never_fires,
        build_dir=BUILD_DIR,
        successor=successor,
        owners=owners,
    )


def _owner(name: str, beats: tuple[Beat, ...], manifest_rows: tuple[str, ...]):
    return freeze_grade.OwnerSuite(
        name=name, claims=freeze_grade._claimed_by_own(beats),
        manifest_rows=frozenset(manifest_rows))


def _grade(chapter_id, frozen, residue, gen_chapter, never_fires=()):
    """The failing problems only -- most tests grade pass/fail."""
    return _grade_full(chapter_id, frozen, residue, gen_chapter, never_fires).problems


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
    problems = _grade("CH01", FROZEN, {}, gen)
    assert len(problems) == 1
    assert "none of them declares" in problems[0]


def test_undercovering_declared_assertion_is_a_problem(monkeypatch):
    floor_assertion = _warp_assertion(direction=2)
    _patch_floor(monkeypatch, {ROW: _floor(assertions=(floor_assertion,))})
    # Declared assertion has a different key entirely, so covers() can never
    # match it against the floor's warp assertion.
    other_kind = FloorAssertion(row_id=ROW, kind="heal_party", list_index=1, code=105)
    gen = _chapter("CH01", (_beat("B1", rows=(ROW,), assertions=frozenset({other_kind})),))
    problems = _grade("CH01", FROZEN, {}, gen)
    assert len(problems) == 1
    assert "not declared at all" in problems[0]


def test_contradicting_declared_assertion_is_reported_as_contradiction(monkeypatch):
    floor_assertion = _warp_assertion(direction=2)
    contradicting = _warp_assertion(direction=9)  # same key, wrong value
    _patch_floor(monkeypatch, {ROW: _floor(assertions=(floor_assertion,))})
    gen = _chapter("CH01", (_beat("B1", rows=(ROW,), assertions=frozenset({contradicting})),))
    problems = _grade("CH01", FROZEN, {}, gen)
    assert len(problems) == 1
    assert "contradict" in problems[0]


def test_refused_floor_on_claimed_row_is_reported_distinctly(monkeypatch):
    refusal = FloorRefusal(row_id=ROW, reason="no_extractor", list_index=0, code=999,
                            detail="unhandled command")
    _patch_floor(monkeypatch, {ROW: _floor(refusals=(refusal,))})
    gen = _chapter("CH01", (_beat("B1", rows=(ROW,), assertions=frozenset()),))
    problems = _grade("CH01", FROZEN, {}, gen)
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
    assert _grade("CH01", FROZEN, {}, gen) == []


# --- C9 grading rulings 6-10 (2026-09-24) ------------------------------------

def _text_assertion(row_id: str = ROW) -> FloorAssertion:
    return FloorAssertion(row_id=row_id, kind="text", list_index=0, code=101,
                           params=make_params(text="Hello"), tag="text")


def _kind_assertion(kind: str, list_index: int, row_id: str = ROW, **params) -> FloorAssertion:
    return FloorAssertion(row_id=row_id, kind=kind, list_index=list_index, code=None,
                           params=make_params(**params))


def test_generator_only_row_is_reported_not_failed(monkeypatch):
    """Ruling 6: rule (b) grades required rows only; a generator-only row
    that undercovers its floor is counted as info."""
    _patch_floor(monkeypatch, {ROW: _floor(assertions=(_text_assertion(),))})
    gen = _chapter("CH01", (_beat("B1", rows=(ROW,), assertions=frozenset()),))
    grade = _grade_full("CH01", [], {}, gen)
    assert grade.problems == []
    assert len(grade.generator_only_partial) == 1
    assert ROW in grade.generator_only_partial[0]


def test_walk_checked_kinds_are_not_graded(monkeypatch):
    """Ruling 7: audio/visual/displacement are left to the boot walk."""
    text = _text_assertion()
    walk_checked = (
        _kind_assertion("audio", 1, name="bgm"),
        _kind_assertion("visual", 2, detail="emote"),
        _kind_assertion("displacement", 3, target=0, dx=1, dy=0),
    )
    _patch_floor(monkeypatch, {ROW: _floor(assertions=(text, *walk_checked))})
    gen = _chapter("CH01", (_beat("B1", rows=(ROW,), assertions=frozenset({text})),))
    assert _grade("CH01", FROZEN, {}, gen) == []


def test_walk_checked_kind_still_fails_when_contradicted(monkeypatch):
    """Ruling 7 exempts a MISSING walk-checked assertion, never a wrong one."""
    floor_audio = _kind_assertion("audio", 1, name="bgm_a")
    wrong_audio = _kind_assertion("audio", 1, name="bgm_b")
    _patch_floor(monkeypatch, {ROW: _floor(assertions=(floor_audio,))})
    gen = _chapter("CH01", (_beat("B1", rows=(ROW,), assertions=frozenset({wrong_audio})),))
    problems = _grade("CH01", FROZEN, {}, gen)
    assert len(problems) == 1
    assert "contradict" in problems[0]


def test_blocked_obstacle_floor_owes_only_the_block(monkeypatch):
    """Ruling 10: a capability-blocked row can't trigger or complete."""
    block = _kind_assertion("blocked_obstacle", 0, x=3, y=4, capability="rock_smash")
    flow = (_kind_assertion("trigger", -1, trigger="action"), _kind_assertion("completes", -1))
    _patch_floor(monkeypatch, {ROW: _floor(assertions=(block, *flow))})
    gen = _chapter("CH01", (_beat("B1", rows=(ROW,), assertions=frozenset({block})),))
    assert _grade("CH01", FROZEN, {}, gen) == []


def test_blocked_obstacle_floor_still_owes_the_block(monkeypatch):
    block = _kind_assertion("blocked_obstacle", 0, x=3, y=4, capability="rock_smash")
    _patch_floor(monkeypatch, {ROW: _floor(assertions=(block,))})
    gen = _chapter("CH01", (_beat("B1", rows=(ROW,), assertions=frozenset()),))
    problems = _grade("CH01", FROZEN, {}, gen)
    assert len(problems) == 1
    assert "blocked_obstacle" in problems[0]


def test_boundary_row_covered_by_successor_crossing(monkeypatch):
    """Ruling 9: a boundary warp declares nothing; the successor crosses."""
    warp = _warp_assertion()
    _patch_floor(monkeypatch, {ROW: _floor(assertions=(warp,))})
    gen = _chapter("CH01", (_beat("B1", rows=(ROW,), assertions=frozenset(), archetype="warp"),))
    succ = _chapter("CH02", (_beat("m1_warp", rows=(ROW,), assertions=frozenset({warp}),
                                   archetype="warp"),))
    assert _grade_full("CH01", FROZEN, {}, gen, successor=succ).problems == []


def test_boundary_row_fails_when_successor_crossing_undercovers(monkeypatch):
    warp = _warp_assertion()
    _patch_floor(monkeypatch, {ROW: _floor(assertions=(warp,))})
    gen = _chapter("CH01", (_beat("B1", rows=(ROW,), assertions=frozenset(), archetype="warp"),))
    succ = _chapter("CH02", (_beat("m1_warp", rows=(ROW,), assertions=frozenset(),
                                   archetype="warp"),))
    problems = _grade_full("CH01", FROZEN, {}, gen, successor=succ).problems
    assert len(problems) == 1
    assert problems[0].startswith(ROW)


def test_boundary_row_fails_when_successor_does_not_claim_it(monkeypatch):
    _patch_floor(monkeypatch, {ROW: _floor(assertions=(_warp_assertion(),))})
    gen = _chapter("CH01", (_beat("B1", rows=(ROW,), assertions=frozenset(), archetype="warp"),))
    succ = _chapter("CH02", ())
    problems = _grade_full("CH01", FROZEN, {}, gen, successor=succ).problems
    assert len(problems) == 1
    assert "does not claim its crossing" in problems[0]


def test_boundary_row_without_generated_successor_is_deferred(monkeypatch):
    _patch_floor(monkeypatch, {ROW: _floor(assertions=(_warp_assertion(),))})
    gen = _chapter("CH01", (_beat("B1", rows=(ROW,), assertions=frozenset(), archetype="warp"),))
    grade = _grade_full("CH01", FROZEN, {}, gen, successor=None)
    assert grade.problems == []
    assert len(grade.deferred) == 1 and ROW in grade.deferred[0]


def test_non_warp_beat_declaring_nothing_is_not_a_boundary_claim(monkeypatch):
    """Only a warp beat's empty declaration reads as a boundary stop."""
    _patch_floor(monkeypatch, {ROW: _floor(assertions=(_text_assertion(),))})
    gen = _chapter("CH01", (_beat("B1", rows=(ROW,), assertions=frozenset(), archetype="generic"),))
    grade = _grade_full("CH01", FROZEN, {}, gen, successor=None)
    assert grade.deferred == []
    assert len(grade.problems) == 1


# --- C9 ruling 12: the owning chapter's claim counts ---------------------------

FROZEN_CH02 = [FrozenBeat(chapter="CH02", name="B18", order=0, group=None,
                          map_constant=None, rows=(ROW,))]


def test_row_claimed_by_owning_chapter_satisfies_coverage(monkeypatch):
    warp = _warp_assertion()
    _patch_floor(monkeypatch, {ROW: _floor(assertions=(warp,))})
    gen = _chapter("CH02", ())
    owner = _owner("CH01", (_beat("m1", rows=(ROW,), assertions=frozenset({warp})),), (ROW,))
    assert _grade_full("CH02", FROZEN_CH02, {}, gen, owners=[owner]).problems == []


def test_claim_by_a_chapter_that_does_not_own_the_row_does_not_count(monkeypatch):
    warp = _warp_assertion()
    _patch_floor(monkeypatch, {ROW: _floor(assertions=(warp,))})
    gen = _chapter("CH02", ())
    other = _owner("CH01", (_beat("m1", rows=(ROW,), assertions=frozenset({warp})),), ())
    problems = _grade_full("CH02", FROZEN_CH02, {}, gen, owners=[other]).problems
    assert len(problems) == 1 and "not claimed" in problems[0]


def test_owning_chapter_claim_is_graded_for_floor(monkeypatch):
    _patch_floor(monkeypatch, {ROW: _floor(assertions=(_warp_assertion(),))})
    gen = _chapter("CH02", ())
    owner = _owner("CH01", (_beat("m1", rows=(ROW,), assertions=frozenset()),), (ROW,))
    problems = _grade_full("CH02", FROZEN_CH02, {}, gen, owners=[owner]).problems
    assert len(problems) == 1
    assert "does not cover its floor" in problems[0]


def test_owner_suite_for_the_graded_chapter_itself_is_ignored(monkeypatch):
    _patch_floor(monkeypatch, {})
    gen = _chapter("CH02", ())
    self_owner = _owner("CH02", (_beat("m1", rows=(ROW,), assertions=frozenset()),), (ROW,))
    problems = _grade_full("CH02", FROZEN_CH02, {}, gen, owners=[self_owner]).problems
    assert len(problems) == 1 and "not claimed" in problems[0]


# --- real-data smoke test ----------------------------------------------------

@pytest.mark.parametrize("chapter", gen_chapter_names())
def test_real_generated_chapters_are_green(chapter):
    # Collects zero test cases while chapters_gen/ is empty (the ordinary
    # state before C9 lands a chapter) -- that is a pass with nothing to
    # run, not a failure. Once modules land here, each one is its own case.
    if not (BUILD_DIR / "maps").exists():
        pytest.skip("no converted map corpus at output/uranium-build/maps")
    problems = freeze_grade.grade_chapter_from_disk(chapter.upper()).problems
    assert problems == []
