"""White-out fork beat placement (REDERIVATION_PLAN.md §16.3 rulings 15-16)."""
from __future__ import annotations

import pytest

from rpg2gba.beat_gen.plan import PlannedBeat
from rpg2gba.beat_gen.whiteout import heal_location_for, place_whiteout_beats

HEALS = [
    {"id": "HEAL_LOCATION_URANIUM_START", "map": "MAP_HOUSE", "x": 7, "y": 7},
    {"id": "HEAL_LOCATION_KEVLAR", "map": "MAP_CENTER", "x": 7, "y": 8},
]
CONSTS = {49: "MAP_HOUSE", 68: "MAP_CENTER", 50: "MAP_LAB"}


def _beat(name: str, group: str, rows: tuple[str, ...], map_id: int = 50) -> PlannedBeat:
    return PlannedBeat(name=name, template="generic", map_id=map_id, rows=rows, group=group)


def _place(beats, fork_rows, enabled_by):
    return place_whiteout_beats(beats, fork_rows, enabled_by,
                                map_constant_for=CONSTS.__getitem__, heal_entries=HEALS)


def test_rides_after_its_enabler_in_the_enablers_group() -> None:
    beats = [_beat("a", "g1", ("map050/ev001/p0",)),
             _beat("starter", "g2", ("map050/ev019/p0",)),
             _beat("starter_arm", "g2", ("map050/ev019/p0/b1",)),
             _beat("later", "g3", ("map050/ev030/p0",))]
    out = _place(beats, ["map049/ev022/p0"],
                 {"map049/ev022/p0": (("engine:whiteout",), ("map050/ev019/p0",))})
    assert [b.name for b in out] == ["a", "starter", "starter_arm", "m049_whiteout", "later"]
    wo = out[3]
    assert wo.template == "whiteout"
    assert wo.group == "g2"
    assert wo.rows == ("map049/ev022/p0",)
    assert wo.kwarg("heal_location_id") == "HEAL_LOCATION_URANIUM_START"


def test_follows_the_last_of_several_enablers() -> None:
    beats = [_beat("center", "g1", ("map068/ev010/p0",), 68),
             _beat("x", "g2", ("map050/ev001/p0",))]
    out = _place(beats, ["map068/ev001/p1"], {"map068/ev001/p1": (
        ("engine:whiteout",), ("map068/ev010/p0",), ("map050/ev001/p0",))})
    assert [b.name for b in out] == ["center", "x", "m068_whiteout"]
    assert out[-1].kwarg("heal_location_id") == "HEAL_LOCATION_KEVLAR"


def test_without_a_claimed_enabler_it_rides_with_the_first_group() -> None:
    beats = [_beat("a", "g1", ("map050/ev001/p0",)), _beat("a2", "g1", ("map050/ev002/p0",)),
             _beat("b", "g2", ("map050/ev003/p0",))]
    out = _place(beats, ["map049/ev022/p0"], {"map049/ev022/p0": (("engine:whiteout",),)})
    assert [b.name for b in out] == ["a", "a2", "m049_whiteout", "b"]
    assert out[2].group == "g1"


def test_no_fork_rows_is_a_no_op() -> None:
    beats = (_beat("a", "g1", ("map050/ev001/p0",)),)
    assert _place(beats, [], {}) == beats


def test_heal_location_must_be_unambiguous() -> None:
    with pytest.raises(ValueError, match="found none"):
        heal_location_for("MAP_LAB", HEALS)
    with pytest.raises(ValueError, match="found"):
        heal_location_for("MAP_HOUSE", HEALS + [{"id": "HEAL_X", "map": "MAP_HOUSE"}])
