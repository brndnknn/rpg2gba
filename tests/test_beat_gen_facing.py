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
    beats, pins, gone = split_facing_arms([beat], sides)
    assert gone == ()
    assert [(b.name, b.group, b.rows) for b in beats] == [
        ("m050e005p2", "m050e005p2", ("map050/ev005/p2", "map050/ev005/p2/b0")),
        ("m050e005p2_face_east", "m050e005p2_face_east", ("map050/ev005/p2/b3",)),
        ("m050e005p2_face_west", "m050e005p2_face_west", ("map050/ev005/p2/b1",)),
    ]
    assert pins == {"m050e005p2_face_east": {"east"}, "m050e005p2_face_west": {"west"}}


def test_split_leaves_non_generic_beats_alone():
    beat = PlannedBeat(name="t", template="trainer", map_id=1, group="t", rows=("map001/ev001/p0",))
    assert split_facing_arms([beat], {"map001/ev001/p0": frozenset({"west"})}) == ((beat,), {}, ())


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


# --- one-shot facing arms (2026-10-12 "no split + re-key") ------------------

from rpg2gba.beat_gen.facing import (  # noqa: E402
    OneShot,
    check_title_pages,
    one_shot_arms,
)

_END0 = {"code": 0, "indent": 1, "parameters": []}


def _off(indent: int, ch: str = "D") -> dict:
    return {"code": 123, "indent": indent, "parameters": [ch, 1]}


def _on(indent: int, ch: str = "D") -> dict:
    return {"code": 123, "indent": indent, "parameters": [ch, 0]}


def _choice_page(inner: list[dict], *, self_switch: str | None = "D",
                 sibling_off: bool = False) -> dict:
    """Choice 0 holds a facing branch (b1 then / b2 else) and, at the arm's
    own level after it, `inner`; choice 1 optionally holds the off-write."""
    cmds = [
        {"code": 102, "indent": 0, "parameters": [["Yes", "Wait"], 2]},
        {"code": 402, "indent": 0, "parameters": [0, "Yes"]},
        _if(1, [6, -1, 6]), _text(2, "r"), {"code": 0, "indent": 2, "parameters": []},
        _else(1), _text(2, "n"), {"code": 0, "indent": 2, "parameters": []}, _end(1),
        *inner,
        {"code": 402, "indent": 0, "parameters": [1, "Wait"]},
        *([_off(1)] if sibling_off else []),
        {"code": 404, "indent": 0, "parameters": []},
    ]
    page = _page(*cmds)
    page["condition"] = ({"self_switch_valid": True, "self_switch_ch": self_switch}
                         if self_switch else {})
    return page


def _arms(page: dict) -> dict:
    return {"events": [{"id": 1, "pages": [page]}]}


def test_one_shot_off_write_in_enclosing_arm():
    page = _choice_page([_off(1)])
    sides = facing_sides(9, _arms(page))
    got = one_shot_arms(9, _arms(page), sides)
    assert set(got) == set(sides) == {"map009/ev001/p0/b1", "map009/ev001/p0/b2"}
    assert got["map009/ev001/p0/b1"] == OneShot("map009/ev001/p0", "D", "map009/ev001/p0/b0")


def test_one_shot_off_write_in_sibling_arm_does_not_count():
    page = _choice_page([], sibling_off=True)
    assert one_shot_arms(9, _arms(page), facing_sides(9, _arms(page))) == {}


def test_one_shot_needs_matching_off_write_and_self_switch_page():
    sides = facing_sides(9, _arms(_choice_page([_on(1)])))
    assert one_shot_arms(9, _arms(_choice_page([_on(1)])), sides) == {}       # ON write
    assert one_shot_arms(9, _arms(_choice_page([_off(1, "C")])), sides) == {}  # other switch
    plain = _choice_page([_off(1)], self_switch=None)                          # no self-switch page
    assert one_shot_arms(9, _arms(plain), sides) == {}


def _shot(page: str = "map050/ev005/p2") -> OneShot:
    return OneShot(page, "D", f"{page}/b0")


def _beat(rows: tuple[str, ...]) -> PlannedBeat:
    return PlannedBeat(name="m050e005p2", template="generic", map_id=50,
                       group="m050e005p2", rows=rows)


P = "map050/ev005/p2"
NS = frozenset({"north", "south"})
NSE = frozenset({"north", "south", "east"})


def test_one_shot_side_choice_keeps_most_rows_then_widest_then_order():
    rows = (P, f"{P}/b1", f"{P}/b2", f"{P}/b3", f"{P}/b4")
    sides = {f"{P}/b1": frozenset({"west"}), f"{P}/b2": NSE,
             f"{P}/b3": frozenset({"east"}), f"{P}/b4": NS}
    shots = {r: _shot() for r in sides}
    beats, pins, gone = split_facing_arms([_beat(rows)], sides, shots)
    # north and south tie (b2+b4, common {N,S}); north is first.
    assert [(b.name, b.rows) for b in beats] == [("m050e005p2", (P, f"{P}/b2", f"{P}/b4"))]
    assert pins == {"m050e005p2": NS}
    assert [(e.row_id, e.status) for e in gone] == [(f"{P}/b1", "unselected_arm"),
                                                    (f"{P}/b3", "unselected_arm")]
    assert all(P in e.detail and "D" in e.detail and "north" in e.detail for e in gone)


def test_one_shot_tiebreak_on_common_set_size_then_side_order():
    # Two rows, each alone on one side: counts tie at 1; widest set wins.
    rows = (P, f"{P}/b1", f"{P}/b2")
    sides = {f"{P}/b1": frozenset({"west"}), f"{P}/b2": NSE}
    beats, pins, gone = split_facing_arms(
        [_beat(rows)], sides, {r: _shot() for r in sides})
    assert beats[0].rows == (P, f"{P}/b2") and pins == {"m050e005p2": NSE}
    assert [e.row_id for e in gone] == [f"{P}/b1"]
    # Equal counts and equal sizes: north before south before east before west.
    sides = {f"{P}/b1": frozenset({"west"}), f"{P}/b2": frozenset({"east"})}
    beats, pins, gone = split_facing_arms(
        [_beat(rows)], sides, {r: _shot() for r in sides})
    assert beats[0].rows == (P, f"{P}/b2") and pins == {"m050e005p2": frozenset({"east"})}


def test_non_one_shot_arms_still_split_when_mixed_with_one_shot():
    rows = (P, f"{P}/b1", f"{P}/b3")
    sides = {f"{P}/b1": frozenset({"west"}), f"{P}/b3": frozenset({"east"})}
    beats, pins, gone = split_facing_arms([_beat(rows)], sides, {f"{P}/b1": _shot()})
    assert [(b.name, b.rows) for b in beats] == [
        ("m050e005p2", (P, f"{P}/b1")), ("m050e005p2_face_east", (f"{P}/b3",))]
    assert pins == {"m050e005p2": frozenset({"west"}),
                    "m050e005p2_face_east": frozenset({"east"})}
    assert gone == ()


def test_check_title_pages_fails_loud_on_orphaned_autorun_residue():
    trig = {"map050/ev005/p0": "autorun", P: "action"}.__getitem__
    orphan = _beat(("map050/ev005/p0/b2",))
    with pytest.raises(ValueError, match="m050e005p2.*can't be re-keyed"):
        check_title_pages([orphan], trig)
    check_title_pages([_beat((P, "map050/ev005/p0/b2"))], trig)          # title present
    check_title_pages([_beat(("map050/ev005/p2/b5",))], trig)            # same trigger kind
    check_title_pages([dataclasses_replace_name(orphan, "m050e005p2_c2a1")], trig)  # not a title


def dataclasses_replace_name(beat: PlannedBeat, name: str) -> PlannedBeat:
    import dataclasses
    return dataclasses.replace(beat, name=name, group=name)
