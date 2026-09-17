"""Tests for the ⊇-floor rule (REDERIVATION_PLAN.md §16.3 C5, R11):
`checker.FloorCoverageModel`, `_check_floor_coverage`,
`RULE_FLOOR_UNCOVERED`/`RULE_FLOOR_UNDECLARED`/`RULE_FLOOR_MISSING`/
`RULE_FLOOR_MODEL_UNENFORCED`.

Fixture idiom matches `test_chapter_manifest_checker.py`: build `ManifestRow`
objects directly and a small fake `FloorCoverageModel`, not the real
`floor_model.py` adapter (which needs a live playtest module and converted
map data) -- except the real-corpus smoke test at the bottom, which does go
through the CLI end to end.
"""
from __future__ import annotations

from click.testing import CliRunner

from rpg2gba.beat_floor.assertion import FloorAssertion, FloorRefusal, RowFloor, make_params
from rpg2gba.chapter_manifest.__main__ import cli
from rpg2gba.chapter_manifest.checker import (
    RULE_FLOOR_MISSING,
    RULE_FLOOR_MODEL_UNENFORCED,
    RULE_FLOOR_UNCOVERED,
    RULE_FLOOR_UNDECLARED,
    check_chapter,
)
from rpg2gba.chapter_manifest.schema import ManifestRow

ROW_ID = "map001/ev001/p0"


def _row(row_id: str = ROW_ID, **overrides) -> ManifestRow:
    defaults = dict(
        row_id=row_id,
        kind="page",
        map_id=1,
        content_hash="deadbeef00000000",
        effects=(),
        reachability_consulted=True,
    )
    defaults.update(overrides)
    return ManifestRow(**defaults)


def _warp_assertion(row_id: str = ROW_ID, **param_overrides) -> FloorAssertion:
    params = dict(map_id=51, x=3, y=4, direction=2)
    params.update(param_overrides)
    return FloorAssertion(
        row_id=row_id, kind="warp", list_index=0, code=201,
        params=make_params(**params), tag="position")


def _floor(row_id: str = ROW_ID, assertions=(), refusals=()) -> RowFloor:
    return RowFloor(
        row_id=row_id, trigger="action",
        assertions=frozenset(assertions), refusals=tuple(refusals))


class _FakeFloorCoverageModel:
    """A minimal `checker.FloorCoverageModel`: fixed per-row floors and
    declarations, supplied directly by each test."""

    def __init__(self, *, floors=None, declared=None, claimed=(), generated=False):
        self._floors = floors or {}
        self._declared = declared or {}
        self._claimed = set(claimed)
        self._generated = generated

    def floor(self, row_id: str) -> RowFloor:
        return self._floors[row_id]

    def declared(self, row_id: str):
        return self._declared.get(row_id)

    def claims(self, row_id: str) -> bool:
        return row_id in self._claimed

    def is_generated(self) -> bool:
        return self._generated


# --- no model supplied: unenforced --------------------------------------


def test_no_model_is_chapter_scale_unenforced_warning():
    row = _row()
    findings = check_chapter([row], {}, floor_coverage=None)
    floor_findings = [f for f in findings if f.rule == RULE_FLOOR_MODEL_UNENFORCED]
    assert len(floor_findings) == 1
    assert floor_findings[0].row_id == "chapter"
    assert floor_findings[0].severity == "warning"


# --- unclaimed row: rule does not apply ----------------------------------


def test_unclaimed_row_is_ignored():
    row = _row()
    model = _FakeFloorCoverageModel(claimed=())  # nothing claims it
    findings = check_chapter([row], {}, floor_coverage=model)
    assert all(f.rule not in (
        RULE_FLOOR_UNCOVERED, RULE_FLOOR_UNDECLARED, RULE_FLOOR_MISSING,
    ) for f in findings)


# --- floor missing (KeyError from floor()) --------------------------------


class _RaisingFloorModel(_FakeFloorCoverageModel):
    def floor(self, row_id: str) -> RowFloor:
        raise KeyError(f"no floor for {row_id!r}")


def test_missing_floor_is_error():
    row = _row()
    model = _RaisingFloorModel(claimed=(ROW_ID,))
    findings = check_chapter([row], {}, floor_coverage=model)
    matches = [f for f in findings if f.rule == RULE_FLOOR_MISSING]
    assert len(matches) == 1
    assert matches[0].row_id == ROW_ID
    assert matches[0].severity == "error"


# --- refused floor: rule skipped silently ---------------------------------


def test_refused_floor_skips_the_rule_entirely():
    row = _row()
    floor = _floor(refusals=(FloorRefusal(
        row_id=ROW_ID, reason="no_extractor", list_index=3, code=999, detail="unknown"),))
    model = _FakeFloorCoverageModel(
        floors={ROW_ID: floor}, declared={}, claimed=(ROW_ID,))
    findings = check_chapter([row], {}, floor_coverage=model)
    assert all(f.rule not in (
        RULE_FLOOR_UNCOVERED, RULE_FLOOR_UNDECLARED, RULE_FLOOR_MISSING,
    ) for f in findings)


# --- undeclared: no claiming beat declares --------------------------------


def test_undeclared_hand_written_beat_is_warning():
    row = _row()
    floor = _floor(assertions=(_warp_assertion(),))
    model = _FakeFloorCoverageModel(
        floors={ROW_ID: floor}, declared={}, claimed=(ROW_ID,), generated=False)
    findings = check_chapter([row], {}, floor_coverage=model)
    matches = [f for f in findings if f.rule == RULE_FLOOR_UNDECLARED]
    assert len(matches) == 1
    assert matches[0].row_id == ROW_ID
    assert matches[0].severity == "warning"


def test_undeclared_in_a_generated_module_is_error():
    row = _row()
    floor = _floor(assertions=(_warp_assertion(),))
    model = _FakeFloorCoverageModel(
        floors={ROW_ID: floor}, declared={}, claimed=(ROW_ID,), generated=True)
    findings = check_chapter([row], {}, floor_coverage=model)
    matches = [f for f in findings if f.rule == RULE_FLOOR_UNDECLARED]
    assert len(matches) == 1
    assert matches[0].severity == "error"


# --- uncovered: declares, but not enough ----------------------------------


def test_uncovered_when_declared_is_empty_but_not_none():
    row = _row()
    floor = _floor(assertions=(_warp_assertion(),))
    # declared[ROW_ID] = frozenset() -- some beat declared, but checked
    # nothing that matches the floor's key at all.
    model = _FakeFloorCoverageModel(
        floors={ROW_ID: floor}, declared={ROW_ID: frozenset()}, claimed=(ROW_ID,))
    findings = check_chapter([row], {}, floor_coverage=model)
    matches = [f for f in findings if f.rule == RULE_FLOOR_UNCOVERED]
    assert len(matches) == 1
    assert matches[0].row_id == ROW_ID
    assert matches[0].severity == "error"
    assert "warp@0" in matches[0].message


def test_uncovered_when_declared_disagrees_on_a_param():
    row = _row()
    floor = _floor(assertions=(_warp_assertion(),))
    declared = frozenset({_warp_assertion(direction=6)})  # wrong direction
    model = _FakeFloorCoverageModel(
        floors={ROW_ID: floor}, declared={ROW_ID: declared}, claimed=(ROW_ID,))
    findings = check_chapter([row], {}, floor_coverage=model)
    matches = [f for f in findings if f.rule == RULE_FLOOR_UNCOVERED]
    assert len(matches) == 1


# --- covered, with extras: no finding -------------------------------------


def test_covered_with_stronger_declared_params_is_clean():
    row = _row()
    floor = _floor(assertions=(_warp_assertion(),))
    # Extra param (facing) beyond what the floor demands -- still covers.
    declared = frozenset({FloorAssertion(
        row_id=ROW_ID, kind="warp", list_index=0, code=201,
        params=make_params(map_id=51, x=3, y=4, direction=2, facing="up"),
        tag="position")})
    model = _FakeFloorCoverageModel(
        floors={ROW_ID: floor}, declared={ROW_ID: declared}, claimed=(ROW_ID,))
    findings = check_chapter([row], {}, floor_coverage=model)
    assert all(f.rule not in (
        RULE_FLOOR_UNCOVERED, RULE_FLOOR_UNDECLARED, RULE_FLOOR_MISSING,
    ) for f in findings)


def test_exactly_covered_is_clean():
    row = _row()
    a = _warp_assertion()
    floor = _floor(assertions=(a,))
    declared = frozenset({a})
    model = _FakeFloorCoverageModel(
        floors={ROW_ID: floor}, declared={ROW_ID: declared}, claimed=(ROW_ID,))
    findings = check_chapter([row], {}, floor_coverage=model)
    assert all(f.rule not in (
        RULE_FLOOR_UNCOVERED, RULE_FLOOR_UNDECLARED, RULE_FLOOR_MISSING,
    ) for f in findings)


# --- message capping -------------------------------------------------------


def test_uncovered_message_caps_and_counts_when_many_are_missing():
    row = _row()
    many = tuple(
        FloorAssertion(
            row_id=ROW_ID, kind="visual", list_index=i, code=101,
            params=(), tag="visual")
        for i in range(12)
    )
    floor = _floor(assertions=many)
    model = _FakeFloorCoverageModel(
        floors={ROW_ID: floor}, declared={ROW_ID: frozenset()}, claimed=(ROW_ID,))
    findings = check_chapter([row], {}, floor_coverage=model)
    matches = [f for f in findings if f.rule == RULE_FLOOR_UNCOVERED]
    assert len(matches) == 1
    assert "12 missing" in matches[0].message
    assert "more" in matches[0].message


# --- real-corpus smoke: CH01-CH05 -----------------------------------------


def test_real_corpus_ch01_through_ch05_has_no_floor_missing_findings():
    """Runs the real CLI `check` against the committed CH01-CH05 manifests
    and dispositions with the real `floor_model.py` adapter wired in
    (`build_dir` defaults to `output/uranium-build`, which is committed
    build data used by other real-corpus tests in this package).

    Asserts only the hard invariant: no `floor_missing` (a claimed row the
    generic floor cannot see is always a bug, in the claim or in the floor).
    `floor_uncovered`/`floor_undeclared` counts are NOT asserted -- five
    other agents are concurrently changing the archetype templates
    (`playtest/archetypes/*.py`) to declare assertions, so those counts are
    in flux; they are recorded in this test's own report only.
    """
    runner = CliRunner()
    counts: dict[str, dict[str, int]] = {}
    for chapter in ("CH01", "CH02", "CH03", "CH04", "CH05"):
        result = runner.invoke(cli, ["check", "--chapter", chapter])
        missing_lines = [
            line for line in result.output.splitlines()
            if "(floor_missing)" in line
        ]
        assert missing_lines == [], (
            f"{chapter}: unexpected floor_missing finding(s): {missing_lines}")
        counts[chapter] = dict(
            floor_uncovered=sum(
                1 for line in result.output.splitlines()
                if "(floor_uncovered)" in line),
            floor_undeclared=sum(
                1 for line in result.output.splitlines()
                if "(floor_undeclared)" in line),
        )
    # Not asserted -- see docstring. Left here only so a failure's -s output
    # shows the counts this run observed.
    print(counts)
