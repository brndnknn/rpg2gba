"""Tests for `rpg2gba.beat_gen.beats_sidecar` (the CHnn.beats.json sidecar)."""
from __future__ import annotations

import json

from rpg2gba.beat_floor.assertion import FloorAssertion, RowFloor, make_params
from rpg2gba.beat_gen import beats_sidecar, review
from rpg2gba.beat_gen.plan import ChapterPlan, PlannedBeat, Refusal, make_kwargs
from rpg2gba.story_state.model import OrderDependentKey

WARP = "map033/ev027/p0"
LAB = "map049/ev001/p2"
AUNT = "map050/ev001/p1"


def _a(row: str, kind: str, i: int, **params) -> FloorAssertion:
    return FloorAssertion(row_id=row, kind=kind, list_index=i, code=None if i < 0 else 121,
                          params=make_params(**params))


FLOORS = {
    WARP: RowFloor(WARP, "touch", frozenset({_a(WARP, "warp", 0, map_id=34)}), ()),
    LAB: RowFloor(LAB, "action", frozenset({
        _a(LAB, "trigger", -1, trigger="action"),
        _a(LAB, "switch_write", 3, switch_id=104, value=False)}), ()),
    AUNT: RowFloor(AUNT, "action", frozenset({
        _a(AUNT, "switch_write", 7, switch_id=104, value=True)}), ()),
}

PLAN = ChapterPlan(
    chapter_id="CH02", predecessor="CH01",
    beats=(
        PlannedBeat(name="m033e027_warp", template="warp", map_id=33, rows=(WARP,),
                    group="m033e027_warp",
                    kwargs=make_kwargs(direction="UP", path=(1, 2), flag=None)),
        PlannedBeat(name="m050e001p1", template="generic", map_id=50, rows=(AUNT,),
                    group="g1", kwargs=make_kwargs(approach_prefer="west")),
        PlannedBeat(name="m049e001p2", template="item_ball", map_id=49, rows=(LAB,),
                    group="g2"),
        PlannedBeat(name="t1", template="transit", map_id=49, rows=(), group="t1"),
    ),
    refusals=(Refusal("map032/ev020/p0", "#109", "text_unnormalizable", "saw a quote"),),
    order_dependent=(OrderDependentKey(key="switch:104", writers=(LAB, AUNT),
                                       values=(False, True)),),
)


def _side() -> dict:
    return beats_sidecar.build_sidecar(PLAN, floor_lookup=FLOORS.__getitem__)


def test_golden_first_beat():
    first = _side()["beats"][0]
    assert first == {
        "name": "m033e027_warp", "group": "m033e027_warp", "template": "warp_beat",
        "call": {"direction": "UP", "flag": None, "path": [1, 2]},
        "map_id": 33, "map_name": None, "cell": None, "pick": "UP", "description": None,
        "rows": [WARP],
        "assertions": [{"row": WARP, "kind": "warp", "offline": True}],
    }


def test_top_level_shape():
    side = _side()
    assert side["schema"] == 1 and side["chapter"] == "CH02"
    assert [b["name"] for b in side["beats"]] == ["m033e027_warp", "m050e001p1", "m049e001p2", "t1"]
    assert side["beats"][2]["template"] == "item_ball_beats"
    assert side["beats"][1]["pick"] == "west"
    assert side["beats"][3]["rows"] == [] and side["beats"][3]["pick"] is None
    assert side["refusals"] == [
        {"row": "map032/ev020/p0",
         "text": "map032/ev020/p0: text_unnormalizable -- saw a quote"}]


def test_order_dependent_matches_review_line():
    side = _side()
    (entry,) = side["order_dependent_writes"]
    assert entry["rows"] == [AUNT, LAB]
    doc = review.render_review(PLAN, floor_lookup=FLOORS.__getitem__)
    assert f"- {entry['text']}" in doc.splitlines()


def test_render_is_deterministic_json():
    text = beats_sidecar.render_sidecar(PLAN, floor_lookup=FLOORS.__getitem__)
    assert text == beats_sidecar.render_sidecar(PLAN, floor_lookup=FLOORS.__getitem__)
    assert text.endswith("}\n") and not text.endswith("\n\n")
    assert json.loads(text) == _side()
