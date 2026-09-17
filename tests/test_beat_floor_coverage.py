"""Tests for `rpg2gba.beat_floor.coverage` (REDERIVATION_PLAN.md §16.3 C5,
the ⊇-floor relation)."""
from __future__ import annotations

from rpg2gba.beat_floor.assertion import FloorAssertion, FloorRefusal, RowFloor, make_params
from rpg2gba.beat_floor.coverage import contradicts, covers, uncovered

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
