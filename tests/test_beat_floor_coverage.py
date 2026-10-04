"""Tests for `rpg2gba.beat_floor.coverage` (REDERIVATION_PLAN.md §16.3 C5,
the ⊇-floor relation)."""
from __future__ import annotations

from rpg2gba.beat_floor.assertion import FloorAssertion, FloorRefusal, RowFloor, make_params
from rpg2gba.beat_floor.coverage import (
    contradicts,
    covers,
    graded_gaps,
    inherited_page_trigger,
    is_boundary_claim,
    uncovered,
)

ROW_ID = "map050/ev001/p0"


def _assertion(**overrides) -> FloorAssertion:
    kwargs = dict(
        row_id=ROW_ID, kind="warp", list_index=0, code=201,
        params=make_params(map_id=51, x=3, y=4, direction=2), tag="position",
    )
    kwargs.update(overrides)
    return FloorAssertion(**kwargs)


def test_covers_equal_params():
    floor_a = _assertion()
    declared_a = _assertion()
    assert covers(declared_a, floor_a)


def test_covers_with_extra_declared_params():
    # A declared assertion may carry MORE params than the floor demands (a
    # stronger oracle on top of the floor) and still cover it.
    floor_a = _assertion()
    declared_a = _assertion(params=make_params(map_id=51, x=3, y=4, direction=2, facing="up"))
    assert covers(declared_a, floor_a)


def test_not_covered_differing_value():
    floor_a = _assertion()
    declared_a = _assertion(params=make_params(map_id=51, x=3, y=4, direction=6))
    assert not covers(declared_a, floor_a)


def test_not_covered_different_key():
    # Different kind -> different assertion_key -> never covers, regardless
    # of params content.
    floor_a = _assertion(kind="warp")
    declared_a = _assertion(kind="heal_party", params=())
    assert not covers(declared_a, floor_a)


def test_not_covered_missing_param_name():
    # The floor names a param the declared assertion simply doesn't carry.
    floor_a = _assertion(params=make_params(map_id=51, x=3, y=4, direction=2))
    declared_a = _assertion(params=make_params(map_id=51, x=3, y=4))
    assert not covers(declared_a, floor_a)


def test_uncovered_empty_when_fully_covered():
    a1 = _assertion(list_index=0, code=201)
    a2 = _assertion(list_index=1, code=314, kind="heal_party", params=())
    floor = RowFloor(row_id=ROW_ID, trigger="action", assertions=frozenset({a1, a2}), refusals=())
    declared = [a1, a2]
    assert uncovered(floor, declared) == ()


def test_uncovered_reports_missing_assertions():
    a1 = _assertion(list_index=0, code=201)
    a2 = _assertion(list_index=1, code=314, kind="heal_party", params=())
    floor = RowFloor(row_id=ROW_ID, trigger="action", assertions=frozenset({a1, a2}), refusals=())
    # Only a1 is declared -- a2 (heal_party) is missing.
    declared = [a1]
    missing = uncovered(floor, declared)
    assert missing == (a2,)


def test_uncovered_ignores_declared_assertions_for_other_rows():
    a1 = _assertion(list_index=0, code=201)
    floor = RowFloor(row_id=ROW_ID, trigger="action", assertions=frozenset({a1}), refusals=())
    other_row_declared = _assertion(row_id="map050/ev002/p0", list_index=0, code=201)
    assert uncovered(floor, [other_row_declared]) == (a1,)


def test_uncovered_refused_floor_returns_empty():
    refusal = FloorRefusal(row_id=ROW_ID, reason="no_extractor", list_index=0, code=999, detail="x")
    floor = RowFloor(row_id=ROW_ID, trigger="action", assertions=frozenset(), refusals=(refusal,))
    assert floor.refused
    assert uncovered(floor, []) == ()


def test_contradicts_true_on_differing_value():
    floor_a = _assertion()
    declared_a = _assertion(params=make_params(map_id=51, x=3, y=4, direction=6))
    assert contradicts(declared_a, floor_a)


def test_contradicts_false_on_matching_value():
    floor_a = _assertion()
    declared_a = _assertion()
    assert not contradicts(declared_a, floor_a)


def test_contradicts_false_on_different_key():
    floor_a = _assertion(kind="warp")
    declared_a = _assertion(kind="heal_party", params=())
    assert not contradicts(declared_a, floor_a)


def test_contradicts_false_when_param_name_absent_from_declared():
    # Same key, but the declared assertion doesn't even mention the param
    # the floor cares about -- that's `uncovered`'s concern, not a
    # contradiction.
    floor_a = _assertion(params=make_params(map_id=51, x=3, y=4, direction=2))
    declared_a = _assertion(params=make_params(map_id=51))
    assert not contradicts(declared_a, floor_a)


def _kind(kind, **params):
    return _assertion(kind=kind, list_index=3, code=None, params=make_params(**params))


def _floor(*assertions):
    return RowFloor(row_id=ROW_ID, trigger="action", assertions=frozenset(assertions), refusals=())


def test_graded_gaps_drops_walk_checked_kinds():
    floor = _floor(_kind("audio"), _kind("visual"), _kind("displacement"),
                   _assertion())
    gaps = graded_gaps(floor, [])
    assert [a.kind for a in gaps.missing] == ["warp"]
    assert gaps.contradicted == ()


def test_graded_gaps_still_reports_contradicted_walk_checked_kind():
    floor = _floor(_kind("audio", bgm=1))
    gaps = graded_gaps(floor, [_kind("audio", bgm=2)])
    assert [a.kind for a in gaps.contradicted] == ["audio"]
    assert gaps.missing == ()


def test_graded_gaps_blocked_obstacle_is_whole_floor():
    block = _kind("blocked_obstacle")
    floor = _floor(block, _assertion())
    assert graded_gaps(floor, []).missing == (block,)
    assert not graded_gaps(floor, [block])


def test_graded_gaps_empty_when_covered():
    assert not graded_gaps(_floor(_assertion()), [_assertion()])


class _B:
    def __init__(self, archetype, assertions):
        self.archetype = archetype
        self.assertions = assertions


def test_is_boundary_claim():
    assert is_boundary_claim(ROW_ID, [_B("warp", ())])
    assert is_boundary_claim(ROW_ID, [_B("warp", None)])
    assert not is_boundary_claim(ROW_ID, [_B("warp", (_assertion(),))])
    assert not is_boundary_claim(ROW_ID, [_B("event", ())])


def test_inherited_page_trigger_covers_an_arm_from_its_page_beat():
    """#124: an arm's floor repeats its page's trigger, so the page's beat
    declaring it covers the arm -- re-keyed to the arm, trigger kind only."""
    trigger = _assertion(kind="trigger", list_index=-1, code=None,
                         params=make_params(trigger="autorun"), tag="flow")
    other = _assertion()  # a warp on the page: not inherited
    page_beat = _B("arrival_nudge", (trigger, other))
    arm = f"{ROW_ID}/b0"

    inherited = inherited_page_trigger(arm, [page_beat])
    assert {(a.row_id, a.kind) for a in inherited} == {(arm, "trigger")}
    floor_trigger = _assertion(row_id=arm, kind="trigger", list_index=-1, code=None,
                               params=make_params(trigger="autorun"), tag="flow")
    assert any(covers(d, floor_trigger) for d in inherited)

    assert inherited_page_trigger(ROW_ID, [page_beat]) == frozenset()  # not an arm
    assert inherited_page_trigger(arm, [_B("x", None)]) == frozenset()  # undeclared page
