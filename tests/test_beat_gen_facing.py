"""Tests for `rpg2gba.beat_gen.facing` (C6 plan A4: a direction-gated arm
pins the approach side)."""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.beat_gen.facing import (
    ALL_SIDES,
    facing_sides,
    pin_records,
    split_facing_arms,
)
from rpg2gba.beat_gen.plan import PlannedBeat
from rpg2gba.routing.locations import ApproachCandidate, BeatLocationRecord
from rpg2gba.traversal.collision import load_map_json

MAPS = Path("output/uranium-build/maps")


def _page(*commands: dict) -> dict:
    return {"trigger": 0, "list": [*commands, {"code": 0, "indent": 0, "parameters": []}]}


def _if(indent: int, params: list) -> dict:
    return {"code": 111, "indent": indent, "parameters": params}


def _else(indent: int) -> dict:
    return {"code": 411, "indent": indent, "parameters": []}


def _end(indent: int) -> dict:
    return {"code": 412, "indent": indent, "parameters": []}


def _text(indent: int, s: str) -> dict:
    return {"code": 101, "indent": indent, "parameters": [s]}


def test_then_arm_pins_the_opposite_side_else_arm_the_rest():
    page = _page(_if(0, [6, -1, 6]), _text(1, "right"), {"code": 0, "indent": 1, "parameters": []},
                 _else(0), _text(1, "not right"), {"code": 0, "indent": 1, "parameters": []},
                 _end(0))
    got = facing_sides(9, {"events": [{"id": 1, "pages": [page]}]})
    assert got == {"map009/ev001/p0/b0": frozenset({"west"}),
                   "map009/ev001/p0/b1": ALL_SIDES - {"west"}}


def test_npc_facing_pins_nothing():
    page = _page(_if(0, [6, 0, 6]), _text(1, "x"), {"code": 0, "indent": 1, "parameters": []},
                 _end(0))
    assert facing_sides(9, {"events": [{"id": 1, "pages": [page]}]}) == {}


def test_bad_direction_fails_loud():
    page = _page(_if(0, [6, -1, 5]), _text(1, "x"), {"code": 0, "indent": 1, "parameters": []},
                 _end(0))
    with pytest.raises(ValueError, match="expected 2/4/6/8"):
        facing_sides(9, {"events": [{"id": 1, "pages": [page]}]})


def test_bambo_nested_arms_intersect():
    # map050 ev5 p2: b0 an outer condition; inside it facing RIGHT (b1) /
    # else (b2), and inside b2 facing LEFT (b3) / else (b4).
    got = facing_sides(50, load_map_json(50, MAPS), [5])
    assert "map050/ev005/p2/b0" not in got
    assert got["map050/ev005/p2/b1"] == {"west"}
    assert got["map050/ev005/p2/b2"] == {"north", "south", "east"}
    assert got["map050/ev005/p2/b3"] == {"east"}
    assert got["map050/ev005/p2/b4"] == {"north", "south"}


def test_split_moves_gated_arms_into_their_own_groups():
    beat = PlannedBeat(name="m050e005p2", template="generic", map_id=50, group="m050e005p2",
                       rows=("map050/ev005/p2", "map050/ev005/p2/b0", "map050/ev005/p2/b1",
                             "map050/ev005/p2/b3"))
    sides = {"map050/ev005/p2/b1": frozenset({"west"}),
             "map050/ev005/p2/b3": frozenset({"east"})}
    beats, pins = split_facing_arms([beat], sides)
    assert [(b.name, b.group, b.rows) for b in beats] == [
        ("m050e005p2", "m050e005p2", ("map050/ev005/p2", "map050/ev005/p2/b0")),
        ("m050e005p2_face_east", "m050e005p2_face_east", ("map050/ev005/p2/b3",)),
        ("m050e005p2_face_west", "m050e005p2_face_west", ("map050/ev005/p2/b1",)),
    ]
    assert pins == {"m050e005p2_face_east": {"east"}, "m050e005p2_face_west": {"west"}}


def test_split_leaves_non_generic_beats_alone():
    beat = PlannedBeat(name="t", template="trainer", map_id=1, group="t", rows=("map001/ev001/p0",))
    assert split_facing_arms([beat], {"map001/ev001/p0": frozenset({"west"})}) == ((beat,), {})


def _record(group: str, sides: tuple[str, ...]) -> BeatLocationRecord:
    return BeatLocationRecord(
        beat_id=group, map_constant="MAP_X", x=1, y=1, resolver="r", rows=(f"{group}/row",),
        candidates=(),
        approach_candidates=tuple(ApproachCandidate(x=i, y=0, side=s, resolver=s)
                                  for i, s in enumerate(sides)))


def test_pin_narrows_candidates_and_refuses_an_unwalkable_side():
    kept, refused = pin_records(
        [_record("a", ("north", "west")), _record("b", ("north",)), _record("c", ("east",))],
        {"a": frozenset({"west"}), "b": frozenset({"south"})})
    assert [(r.beat_id, [c.side for c in r.approach_candidates]) for r in kept] == [
        ("a", ["west"]), ("c", ["east"])]
    assert [(f.row_id, f.reason) for f in refused] == [("b/row", "no_facing_side")]
