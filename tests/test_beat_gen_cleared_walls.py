"""Walls another claimed beat clears (`beat_gen.__main__._released_walls`,
`_released_killers`, `_passage_enablers`). CH07's rockslide: obstacle rocks
(events 14-18) blank on self-switch A, which a cutscene (event 19) sets. The
rocks are walls only when nothing but their own page clears them (the Moki
case, 2026-10-12)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from rpg2gba.beat_gen import __main__ as bg
from rpg2gba.beat_gen.plan import PlannedBeat
from rpg2gba.routing.locations import ApproachCandidate, BeatLocationRecord
from rpg2gba.story_state.state import Assign, SelfSwitch, Test

_ROCK = (35, 15)
_ROCK_PAGES = [{"graphic": {"character_name": "rock"}}, {"graphic": {"character_name": ""}}]
_SWITCH = SelfSwitch(35, 15, "A")


def _state(tests=(), writes=()):
    return SimpleNamespace(page_tests=tuple(tests), writes=tuple(writes))


def _states(*, cutscene_writes=True, own_writes=False):
    clear = Test(_SWITCH, "==", True)
    write = Assign(_SWITCH, frozenset({True}), False, "t", 0)
    return {
        "map035/ev015/p0": _state(),
        "map035/ev015/p1": _state(tests=[clear]),
        # the rock's own Kernel.pbRockSmash arm
        "map035/ev015/p0/b1": _state(writes=[write] if own_writes else []),
        "map035/ev019/p0": _state(writes=[write] if cutscene_writes else []),
    }


def _released(claimed, states):
    return bg._released_walls(
        {_ROCK}, claimed, row_states=lambda m: states, pages_of=lambda m, e: _ROCK_PAGES)


def test_wall_cleared_by_another_claimed_beat_is_released():
    out = _released(["map035/ev015/p0", "map035/ev019/p0"], _states())
    assert out == {_ROCK: ("map035/ev019/p0",)}


def test_wall_cleared_only_by_its_own_page_stays_a_wall():
    claimed = ["map035/ev015/p0", "map035/ev015/p0/b1"]
    assert _released(claimed, _states(cutscene_writes=False, own_writes=True)) == {}


def test_a_clearer_the_plan_does_not_claim_does_not_release():
    assert _released(["map035/ev015/p0"], _states()) == {}


def test_obstacle_beat_comes_before_the_clearer():
    obstacle = PlannedBeat(name="rock", template="obstacle", map_id=35,
                           rows=("map035/ev015/p0",), group="rock")
    other = PlannedBeat(name="x", template="generic", map_id=35,
                        rows=("map035/ev019/p0",), group="x")
    out = bg._released_killers([obstacle, other], {_ROCK: ("map035/ev019/p0",)})
    assert out == {"map035/ev015/p0": ("map035/ev019/p0",)}


@pytest.fixture(autouse=True)
def _map_ids(monkeypatch):
    monkeypatch.setattr(bg, "map_uranium_id", lambda constant: 35)


def _record(rows, x, y) -> BeatLocationRecord:
    cand = (ApproachCandidate(x=x, y=y, side="north", resolver="t"),)
    return BeatLocationRecord(beat_id=rows[0], map_constant="MAP_R2", x=x, y=y, resolver="t",
                              rows=rows, candidates=(), approach_candidates=cand)


_REL = {_ROCK: ("map035/ev019/p0",)}
_NORTH, _SOUTH = (35, (5, 5)), (35, (5, 40))


def test_record_reachable_only_through_the_actor_waits_on_its_clearers():
    out = bg._passage_enablers(
        [_record(("map035/ev030/p0",), 5, 40)], _REL,
        reach_blocked={_NORTH}, reach_open={_NORTH, _SOUTH}, exclude_rows=())
    assert out == {"map035/ev030/p0": ("map035/ev019/p0",)}


def test_record_reachable_without_it_gets_none():
    assert bg._passage_enablers(
        [_record(("map035/ev031/p0",), 5, 5)], _REL,
        reach_blocked={_NORTH}, reach_open={_NORTH, _SOUTH}, exclude_rows=()) == {}


def test_excluded_and_unreachable_records_get_none():
    south = _record(("map035/ev030/p0",), 5, 40)
    assert bg._passage_enablers([south], _REL, reach_blocked={_NORTH},
                                reach_open={_NORTH, _SOUTH},
                                exclude_rows={"map035/ev030/p0"}) == {}
    assert bg._passage_enablers([south], _REL, reach_blocked={_NORTH}, reach_open={_NORTH},
                                exclude_rows=()) == {}


def test_expand_to_pages_covers_every_group_of_the_clearer_page():
    claimed = ["map035/ev019/p0", "map035/ev019/p0/b1", "map035/ev019/p0/b2",
               "map035/ev019/p1", "map035/ev015/p0"]
    out = bg._expand_to_pages({_ROCK: ("map035/ev019/p0",)}, claimed)
    assert out == {_ROCK: ("map035/ev019/p0", "map035/ev019/p0/b1", "map035/ev019/p0/b2")}


_POR = """mapscripts Route02_MapScripts {
    MAP_SCRIPT_ON_TRANSITION {
        # EV020
        setflag(FLAG_TEMP_16)
        setflag(FLAG_TEMP_17)
        if (flag(FLAG_X)) {
            clearflag(FLAG_TEMP_17)
        }
    }
}
"""


def _stage(tmp_path, pory=_POR):
    import json
    (tmp_path / "porymap" / "maps" / "Route02").mkdir(parents=True)
    (tmp_path / "porymap" / "dispatch").mkdir()
    (tmp_path / "porymap" / "map_constants.json").write_text(
        json.dumps({"35": {"dir_name": "Route02"}}), encoding="utf-8")
    events = [{"script": "Map035_EV020_Dispatch", "flag": "FLAG_TEMP_16"},
              {"script": "Map035_EV021_Dispatch", "flag": "FLAG_TEMP_17"},
              {"script": "Map035_EV022_Dispatch", "flag": "0"}]
    (tmp_path / "porymap" / "maps" / "Route02" / "map.json").write_text(
        json.dumps({"object_events": events}), encoding="utf-8")
    if pory is not None:
        (tmp_path / "porymap" / "dispatch" / "Map035_dispatch.pory").write_text(
            pory, encoding="utf-8")


def test_object_hidden_by_top_level_on_transition_setflag_never_blocks(tmp_path):
    _stage(tmp_path)
    # EV021 is set at top level too, but a conditional clearflag can show it
    assert bg.transition_hidden_scripts(35, tmp_path) == {"Map035_EV020_Dispatch"}


def test_missing_dispatch_file_fails_loud(tmp_path):
    _stage(tmp_path, pory=None)
    with pytest.raises(FileNotFoundError):
        bg.transition_hidden_scripts(35, tmp_path)


def _rock_event(event_id):
    cmd = {"code": 111, "parameters": [12, "Kernel.pbRockSmash"]}
    return {"id": event_id, "pages": [{"list": [cmd]}]}


def test_walls_include_smashable_rocks_no_beat_claims():
    events = {35: [_rock_event(14), _rock_event(17), {"id": 19, "pages": [{"list": []}]}],
              36: [_rock_event(2)]}
    assert bg._smashable_rock_walls({35, 36}, events.__getitem__) == {
        (35, 14), (35, 17), (36, 2)}
    assert bg._smashable_rock_walls({35}, events.__getitem__) == {(35, 14), (35, 17)}


def test_passage_gated_when_two_of_three_wall_cells_are_unowned():
    # Only ev015 is claimed by an obstacle beat; 14 and 17 are every
    # smashable rock's walls too. All three clear on ev019's write.
    pages = lambda m, e: _ROCK_PAGES  # noqa: E731
    states = _states()
    for ev in (14, 17):
        sw = SelfSwitch(35, ev, "A")
        states[f"map035/ev0{ev}/p1"] = _state(tests=[Test(sw, "==", True)])
    states["map035/ev019/p0"] = _state(writes=[
        Assign(SelfSwitch(35, ev, "A"), frozenset({True}), False, "t", 0)
        for ev in (14, 15, 17)])
    released = bg._released_walls({(35, 14), (35, 15), (35, 17)},
                                  ["map035/ev015/p0", "map035/ev019/p0"],
                                  row_states=lambda m: states, pages_of=pages)
    assert set(released) == {(35, 14), (35, 15), (35, 17)}
    out = bg._passage_enablers(
        [_record(("map035/ev030/p0",), 5, 40)], released,
        reach_blocked={_NORTH}, reach_open={_NORTH, _SOUTH}, exclude_rows=())
    assert out == {"map035/ev030/p0": ("map035/ev019/p0",)}


_OBSTACLE = PlannedBeat(name="rock", template="obstacle", map_id=35,
                        rows=("map035/ev015/p0",), group="map035/ev015/p0")
_WIRE = frozenset({(25, 27), (25, 28)})


def _tripwire(reach, wires=lambda m, e: _WIRE if e == 19 else frozenset()):  # noqa: ANN001
    seen: list = []

    def reach_avoiding(extra):  # noqa: ANN001, ANN202
        seen.append(extra)
        return reach
    out = bg._tripwire_refusals([_OBSTACLE], [_record(("map035/ev015/p0",), 22, 29)], _REL,
                                tripwire_cells=wires, reach_avoiding=reach_avoiding)
    return out, seen


def test_obstacle_behind_its_clearers_tripwire_is_refused():
    # CH07: the rock faces lie past event 19's sight ray
    out, seen = _tripwire(frozenset({_NORTH}))
    assert [(r.row_id, r.reason) for r in out] == [("map035/ev015/p0", "clearer_tripwire")]
    assert seen == [{35: _WIRE}]


def test_obstacle_reachable_around_the_tripwire_is_kept():
    out, _ = _tripwire(frozenset({_NORTH, (35, (22, 29))}))
    assert out == []


def test_clearer_without_a_tripwire_refuses_nothing():
    out, seen = _tripwire(frozenset(), wires=lambda m, e: frozenset())
    assert out == [] and seen == []


def _unreachable_record(x, y, candidates):
    cands = tuple(ApproachCandidate(x=cx, y=cy, side="north", resolver="t")
                  for cx, cy in candidates)
    return BeatLocationRecord(beat_id="seam", map_constant="MAP_R2", x=x, y=y, resolver="t",
                              rows=("map035/seam/S/map031",), candidates=(),
                              approach_candidates=cands)


def _split(record, monkeypatch):
    monkeypatch.setattr(bg, "reachable_sites",
                        lambda *a, **k: frozenset({(35, (20, 56)), (35, (21, 56))}))
    kept, later = bg._split_unreachable([record], (35, (0, 0)), {}, None, frozenset({35}),
                                        None, "CH07", {}, None)
    return kept, later


def test_routing_cell_repointed_when_it_is_an_unreachable_candidate(monkeypatch):
    kept, later = _split(_unreachable_record(0, 56, [(0, 56), (20, 56), (21, 56)]), monkeypatch)
    assert (kept[0].x, kept[0].y) == (20, 56) and later == {}


def test_routing_cell_not_a_candidate_is_left_alone(monkeypatch):
    # an event cell with candidates on its sides: the player stands ON it
    kept, _ = _split(_unreachable_record(0, 55, [(20, 56), (21, 56)]), monkeypatch)
    assert (kept[0].x, kept[0].y) == (0, 55)


# --- barrier group: invisible walls + their host pillar (Burole Gym) ----------

_WALL_PAGES = [
    {"graphic": {"character_name": "pillar", "opacity": 0}, "through": False,
     "trigger": 0, "list": [{"code": 0}]},
    {"graphic": {"character_name": ""}, "list": [{"code": 0}]},
]
_HOST_PAGES = [{"graphic": {"character_name": "pillar", "opacity": 255}, "list": [{"code": 0}]},
               {"graphic": {"character_name": ""}, "list": [{"code": 0}]}]
_PILLAR_ROW = "map035/ev045/p0"


def _barrier_events():
    return [{"id": 45, "pages": _HOST_PAGES}, {"id": 46, "pages": _WALL_PAGES},
            {"id": 47, "pages": _WALL_PAGES}]


def _barrier_states(host_writes_ssa=True):
    def ssa(e):
        return SelfSwitch(35, e, "A")
    writes = [Assign(ssa(e), frozenset({True}), False, "t", 0) for e in (45, 46, 47)]
    return {
        "map035/ev045/p0": _state(writes=writes if host_writes_ssa else []),
        "map035/ev045/p1": _state(tests=[Test(ssa(45), "==", True)]),
        "map035/ev046/p0": _state(),
        "map035/ev046/p1": _state(tests=[Test(ssa(46), "==", True)]),
        "map035/ev047/p0": _state(),
        "map035/ev047/p1": _state(tests=[Test(ssa(47), "==", True)]),
    }


def _barrier(claimed, states, events=None):
    evs = events if events is not None else _barrier_events()
    return bg._barrier_walls({35}, lambda m: evs, claimed, row_states=lambda m: states)


def test_invisible_wall_cleared_by_another_event_is_released_with_its_clearer():
    out = _barrier([_PILLAR_ROW], _barrier_states())
    assert out[(35, 46)] == (_PILLAR_ROW,) and out[(35, 47)] == (_PILLAR_ROW,)


def test_host_pillar_joins_with_the_same_clearers():
    out = _barrier([_PILLAR_ROW], _barrier_states())
    assert out[(35, 45)] == (_PILLAR_ROW,)


def test_unclaimed_clearer_releases_nothing():
    assert _barrier([], _barrier_states()) == {}


def test_host_whose_row_does_not_lift_its_own_page_is_not_released():
    states = _barrier_states()
    # the row clears 46/47 only
    states[_PILLAR_ROW] = _state(writes=[
        Assign(SelfSwitch(35, e, "A"), frozenset({True}), False, "t", 0) for e in (46, 47)])
    out = _barrier([_PILLAR_ROW], states)
    assert (35, 45) not in out and (35, 46) in out


def test_smashable_rocks_own_clearer_still_excluded():
    # the rock is a wall of the default (visible-page) kind; its own arm never releases it
    claimed = ["map035/ev015/p0", "map035/ev015/p0/b1"]
    assert _released(claimed, _states(cutscene_writes=False, own_writes=True)) == {}


def test_record_behind_the_pillar_row_waits_on_the_pillar_row():
    released = _barrier([_PILLAR_ROW], _barrier_states())
    out = bg._passage_enablers(
        [_record(("map035/ev004/p0",), 5, 40)], released,
        reach_blocked={_NORTH}, reach_open={_NORTH, _SOUTH}, exclude_rows={_PILLAR_ROW})
    assert out == {"map035/ev004/p0": (_PILLAR_ROW,)}


def _multi_record(rows):
    cands = (ApproachCandidate(x=19, y=15, side="north", resolver="t"),
             ApproachCandidate(x=19, y=17, side="south", resolver="t"))
    return BeatLocationRecord(beat_id=rows[0], map_constant="MAP_G", x=19, y=16, resolver="t",
                              rows=rows, candidates=(), approach_candidates=cands)


def test_clearer_beat_keeps_only_sides_reachable_with_its_walls_standing():
    walls = {(35, 46): (_PILLAR_ROW,), (35, 45): (_PILLAR_ROW,)}
    seen = []

    def reach_with(own):
        seen.append(own)
        return {(35, (19, 17))}
    out = bg._clearer_sides_with_walls([_multi_record((_PILLAR_ROW,))], walls, reach_with)
    assert [c.side for c in out[0].approach_candidates] == ["south"]
    assert seen == [frozenset({(35, 46), (35, 45)})]


def test_non_clearer_beat_and_all_unreachable_sides_are_left_alone():
    walls = {(35, 46): (_PILLAR_ROW,)}
    other = _multi_record(("map035/ev004/p0",))
    assert bg._clearer_sides_with_walls([other], walls, lambda own: set()) == [other]
    pillar = _multi_record((_PILLAR_ROW,))
    assert bg._clearer_sides_with_walls([pillar], walls, lambda own: set()) == [pillar]
