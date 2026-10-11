"""`beat_gen.__main__._clearing_enablers` (operator ruling 2026-10-11, "order
after the clear"): a beat worked only from a clearing actor's tile waits on
the writes that clear the actor. CH06's gym door page 0 is touched only from
Fufufu's tile; her clearing pages are enabled by the plaza scene or the
leader battle."""
from __future__ import annotations

import pytest

from rpg2gba.beat_gen import __main__ as bg
from rpg2gba.routing.locations import ApproachCandidate, BeatLocationRecord
from rpg2gba.traversal.graph import MapGraph

_FUFUFU = (13, 6)
_HELD = {_FUFUFU: ("map14001/ev018/p2", "map14001/ev018/p3")}
_ENABLED_BY = {"map14001/ev018/p2": (("map14001/ev141/p0",),),
               "map14001/ev018/p3": (("map042/ev003/p0/b1",),)}


def _graph() -> MapGraph:
    # Open 20x20 except the door's other sides.
    blocked = {(x, y): False for x in range(20) for y in range(20)}
    for cell in ((12, 5), (14, 5), (13, 4)):
        blocked[cell] = True
    return MapGraph(map_id=14001, width=20, height=20, tileset_id=0, blocked=blocked)


def _record(rows, x, y, candidates=()) -> BeatLocationRecord:
    return BeatLocationRecord(beat_id="b", map_constant="MAP_PLAZA", x=x, y=y, resolver="t",
                              rows=rows, candidates=(), approach_candidates=candidates)


@pytest.fixture(autouse=True)
def _map_ids(monkeypatch):
    monkeypatch.setattr(bg, "map_uranium_id", lambda constant: 14001)


def test_touch_page_behind_the_actor_waits_on_its_clearing_writers():
    out = bg._clearing_enablers([_record(("map14001/ev014/p0",), 13, 5)],
                                lambda m: _HELD, {14001: _graph()}, _ENABLED_BY)
    assert out == {"map14001/ev014/p0": ("map042/ev003/p0/b1", "map14001/ev141/p0")}


def test_a_beat_with_another_free_side_is_untouched():
    free = ApproachCandidate(x=12, y=6, side="west", resolver="t")
    held = ApproachCandidate(x=13, y=6, side="north", resolver="t")
    assert bg._clearing_enablers([_record(("map14001/ev020/p0",), 12, 7, (free, held))],
                                 lambda m: _HELD, {14001: _graph()}, _ENABLED_BY) == {}


def test_the_actor_itself_is_untouched():
    south = ApproachCandidate(x=13, y=7, side="south", resolver="t")
    assert bg._clearing_enablers([_record(("map14001/ev018/p0",), 13, 6, (south,))],
                                 lambda m: _HELD, {14001: _graph()}, _ENABLED_BY) == {}


def test_no_clearing_actor_on_the_map_is_a_no_op():
    assert bg._clearing_enablers([_record(("map14001/ev014/p0",), 13, 5)],
                                 lambda m: {}, {14001: _graph()}, _ENABLED_BY) == {}


def _beat(name, rows):
    from rpg2gba.beat_gen.plan import PlannedBeat

    return PlannedBeat(name=name, template="generic", map_id=14001, rows=rows, group=name)


def test_a_page_the_route_keeps_before_its_clear_never_fires():
    door = _beat("door_p0", ("map14001/ev014/p0",))
    scene = _beat("scene", ("map14001/ev141/p0",))
    beats, gone = bg._drop_dead_before_clear(
        [door, scene], {"map14001/ev014/p0": ("map14001/ev141/p0",)},
        ["door_p0", "scene"], {"map14001/ev014/p0": "door_p0", "map14001/ev141/p0": "scene"})
    assert [b.name for b in beats] == ["scene"]
    assert [(e.row_id, e.status) for e in gone] == [("map14001/ev014/p0", "never_fires")]


def test_a_page_after_its_clear_stays():
    door = _beat("door_p1", ("map14001/ev014/p1",))
    scene = _beat("scene", ("map14001/ev141/p0",))
    beats, gone = bg._drop_dead_before_clear(
        [scene, door], {"map14001/ev014/p1": ("map14001/ev141/p0",)},
        ["scene", "door_p1"], {"map14001/ev014/p1": "door_p1", "map14001/ev141/p0": "scene"})
    assert [b.name for b in beats] == ["scene", "door_p1"] and gone == ()
