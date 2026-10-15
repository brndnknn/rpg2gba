"""CH08 section 9: Rock Smash held by the walk. `coverage.graded_gaps`
(smashed twin), `select_rows` (held / held_obstacles / foreign_cleared),
`plan_beats(held_obstacles=)`, `_with_teach`, `_passage_enablers`, and
`seed.walked_rows`."""
from __future__ import annotations

import pytest

from rpg2gba.beat_floor.assertion import FloorAssertion, RowFloor, make_params
from rpg2gba.beat_floor.coverage import graded_gaps
from rpg2gba.beat_gen import __main__ as bg
from rpg2gba.beat_gen import group
from rpg2gba.beat_gen.plan import PlannedBeat
from rpg2gba.beat_gen.seed import walked_rows
from rpg2gba.beat_gen.select import select_rows
from rpg2gba.chapter_manifest.schema import ManifestRow
from rpg2gba.routing.locations import ApproachCandidate, BeatLocationRecord
from rpg2gba.story_state.model import RowVerdict

ROW = "map032/ev014/p0"


def _page(map_id: int, event_id: int, *, requires: tuple[str, ...] = ()) -> ManifestRow:
    return ManifestRow(row_id=f"map{map_id:03d}/ev{event_id:03d}/p0", kind="page",
                       map_id=map_id, content_hash="x", event_id=event_id, page_idx=0,
                       requires=requires)


def _assertion(row_id, kind, x=1, y=1, cap="rock_smash") -> FloorAssertion:
    return FloorAssertion(row_id=row_id, kind=kind, list_index=-1, code=None,
                          params=make_params(x=x, y=y, capability=cap), tag="position")


def _floor(row_id, *assertions) -> RowFloor:
    return RowFloor(row_id=row_id, trigger="action", assertions=frozenset(assertions),
                    refusals=())


def _rock(row_id, cap="rock_smash") -> RowFloor:
    return _floor(row_id, _assertion(row_id, "blocked_obstacle", cap=cap))


def _plain(row_id) -> RowFloor:
    return _floor(row_id)


def _verdict(row_id, status="live", owner="CH08") -> RowVerdict:
    return RowVerdict(row_id=row_id, status=status, owner=owner, stage=0, enabled_by=(),
                      killed_by=(), blockers=(), forced=False, refusals=(), detail=None)


# --- 1. graded_gaps ---------------------------------------------------------

def test_smashed_obstacle_covers_blocked_obstacle():
    floor = _rock(ROW)
    got = graded_gaps(floor, [_assertion(ROW, "smashed_obstacle")])
    assert got.missing == () and not got


def test_blocked_obstacle_declared_still_covers():
    floor = _rock(ROW)
    assert not graded_gaps(floor, [_assertion(ROW, "blocked_obstacle")])


def test_nothing_declared_leaves_obstacle_missing():
    floor = _rock(ROW)
    assert [a.kind for a in graded_gaps(floor, []).missing] == ["blocked_obstacle"]


@pytest.mark.parametrize("kw", [{"x": 2}, {"y": 2}, {"cap": "strength"}])
def test_smashed_obstacle_of_another_cell_or_capability_does_not_cover(kw):
    floor = _rock(ROW)
    got = graded_gaps(floor, [_assertion(ROW, "smashed_obstacle", **kw)])
    assert [a.kind for a in got.missing] == ["blocked_obstacle"]


def test_smashed_obstacle_of_another_row_does_not_cover():
    floor = _rock(ROW)
    got = graded_gaps(floor, [_assertion("map032/ev015/p0", "smashed_obstacle")])
    assert [a.kind for a in got.missing] == ["blocked_obstacle"]


def test_assertions_without_params_do_not_crash():
    bare = FloorAssertion(row_id=ROW, kind="blocked_obstacle", list_index=-1, code=None)
    floor = _floor(ROW, bare)
    declared = FloorAssertion(row_id=ROW, kind="smashed_obstacle", list_index=-1, code=None)
    assert not graded_gaps(floor, [declared])
    assert graded_gaps(floor, [])


# --- 2. select_rows ---------------------------------------------------------

def _select(rows, verdicts, floors, **kw):
    return select_rows(rows, {v.row_id: v for v in verdicts}, {f.row_id: f for f in floors},
                       **kw)


def test_rule5_later_obstacle_in_held_obstacles_is_owned():
    row = _page(32, 14, requires=("rock_smash",))
    args = ([row], [_verdict(row.row_id, "later", "CH09")], [_rock(row.row_id)])
    sel = _select(*args, held={"rock_smash"}, held_obstacles={(32, 14)})
    assert [r.row_id for r in sel.owned] == [row.row_id]
    assert sel.elsewhere == ()


def test_rule5_later_obstacle_not_held_goes_elsewhere():
    row = _page(32, 14)
    args = ([row], [_verdict(row.row_id, "later", "CH09")], [_rock(row.row_id)])
    for kw in ({}, {"held_obstacles": {(32, 15)}}):
        sel = _select(*args, **kw)
        assert sel.owned == ()
        assert [(e.row_id, e.status) for e in sel.elsewhere] == [(row.row_id, "later")]


def test_rule5_later_non_obstacle_in_held_obstacles_still_goes_elsewhere():
    row = _page(32, 14)
    sel = _select([row], [_verdict(row.row_id, "later", "CH09")], [_plain(row.row_id)],
                  held_obstacles={(32, 14)})
    assert sel.owned == () and sel.elsewhere[0].status == "later"


def test_rule6_requires_all_held_is_owned():
    row = _page(32, 20, requires=("rock_smash",))
    sel = _select([row], [_verdict(row.row_id)], [_plain(row.row_id)], held={"rock_smash"})
    assert [r.row_id for r in sel.owned] == [row.row_id]


def test_rule6_blocked_by_default_and_when_requirement_not_held():
    row = _page(32, 20, requires=("rock_smash", "strength"))
    for kw in ({}, {"held": {"rock_smash"}}):
        sel = _select([row], [_verdict(row.row_id)], [_plain(row.row_id)], **kw)
        assert sel.owned == ()
        assert [(e.row_id, e.status) for e in sel.elsewhere] == [(row.row_id, "blocked")]


def test_rule6_blocked_when_event_foreign_cleared():
    row = _page(32, 20, requires=("rock_smash",))
    sel = _select([row], [_verdict(row.row_id)], [_plain(row.row_id)], held={"rock_smash"},
                  foreign_cleared={(32, 20)})
    assert sel.owned == () and sel.elsewhere[0].status == "blocked"


# --- 3. plan_beats ----------------------------------------------------------

def _beats(rows, held_obstacles=None):
    floors = {r.row_id: _rock(r.row_id) for r in rows}
    kw = {} if held_obstacles is None else {"held_obstacles": held_obstacles}
    return {b.name: b for b in group.plan_beats(rows, [], floors, **kw)}


def test_held_obstacle_becomes_smash_beat():
    r = _page(32, 14)
    beats = _beats([r], {(32, 14)})
    assert set(beats) == {"m032smash_rock_smash"}
    b = beats["m032smash_rock_smash"]
    assert b.template == "smash" and b.rows == (r.row_id,)
    assert b.kwarg("capability") == "rock_smash"


def test_smash_and_obstacle_coexist_on_one_map():
    r1, r2 = _page(32, 14), _page(32, 15)
    beats = _beats([r1, r2], {(32, 14)})
    assert beats["m032smash_rock_smash"].rows == (r1.row_id,)
    assert beats["m032obstacle_rock_smash"].rows == (r2.row_id,)
    assert beats["m032obstacle_rock_smash"].template == "obstacle"


def test_default_keeps_obstacle_beat():
    beats = _beats([_page(32, 14)])
    assert set(beats) == {"m032obstacle_rock_smash"}
    assert beats["m032obstacle_rock_smash"].template == "obstacle"


# --- 4a. _with_teach --------------------------------------------------------

def _beat(name, template="smash", cap="rock_smash", **kw):
    kwargs = {"capability": cap, **kw} if cap else {}
    return PlannedBeat(name=name, template=template, map_id=32, rows=(name,), group=name,
                       kwargs=tuple(sorted(kwargs.items())))


def test_with_teach_marks_first_smash_per_capability_only():
    a, b = _beat("a"), _beat("b")
    s = _beat("s", cap="strength")
    out = bg._with_teach([a, b, s], taught=())
    assert dict(out[0].kwargs)["teach"] == "teach_rock_smash"
    assert "teach" not in dict(out[1].kwargs)
    assert dict(out[2].kwargs)["teach"] == "teach_strength"


def test_with_teach_skips_taught_capabilities():
    out = bg._with_teach([_beat("a"), _beat("s", cap="strength")], taught={"rock_smash"})
    assert "teach" not in dict(out[0].kwargs)
    assert dict(out[1].kwargs)["teach"] == "teach_strength"


def test_with_teach_leaves_non_smash_beats_alone():
    ob = _beat("o", template="obstacle")
    other = _beat("g", template="generic", cap=None)
    assert bg._with_teach([ob, other], taught=()) == (ob, other)


# --- 4b. _passage_enablers --------------------------------------------------

def _record(row, map_id, x=5, y=5) -> BeatLocationRecord:
    cand = (ApproachCandidate(x=x, y=y, side="north", resolver="t"),)
    return BeatLocationRecord(beat_id=row, map_constant=f"MAP_{map_id}", x=x, y=y, resolver="t",
                              rows=(row,), candidates=(), approach_candidates=cand)


@pytest.fixture
def _ids(monkeypatch):
    monkeypatch.setattr(bg, "map_uranium_id", lambda c: int(c.split("_")[1]))


def _enablers(records, released):
    sites = {(r.x, r.y) for r in records}
    open_ = {(int(r.map_constant.split("_")[1]), s) for r in records for s in sites}
    return bg._passage_enablers(records, released, reach_blocked=set(), reach_open=open_,
                                exclude_rows=())


def test_record_on_map_with_released_walls_gets_only_that_maps_clearers(_ids):
    released = {(1, 7): ("map001/smash",), (2, 8): ("map002/smash",)}
    out = _enablers([_record("map001/ev030/p0", 1)], released)
    assert out == {"map001/ev030/p0": ("map001/smash",)}


def test_record_on_map_without_released_walls_gets_all_writers(_ids):
    released = {(1, 7): ("map001/smash",), (2, 8): ("map002/smash",)}
    out = _enablers([_record("map003/ev030/p0", 3)], released)
    assert out == {"map003/ev030/p0": ("map001/smash", "map002/smash")}


# --- 7. walked_rows ---------------------------------------------------------

def test_walked_rows_collects_claims_and_status_dicts(tmp_path):
    (tmp_path / "cha.py").write_text(
        "from types import SimpleNamespace as NS\n"
        "CHAPTER = NS(beats=[NS(rows=['map1/a', 'map1/b']), NS(rows=['map2/c'])])\n"
        "ELSEWHERE = {'map3/d': 'later'}\n"
        "REFUSED = {'map4/e': 'x'}\n"
        "NEVER_FIRES = {'map5/f': 'x'}\n"
        "EMPTY_PAGES = {'map6/g': 'x'}\n"
        "WALK_CHECKED = {'map7/h': 'x'}\n"
        "OTHER = {'map8/i': 'x'}\n", encoding="utf-8")
    assert walked_rows("CHA", tmp_path) == frozenset(
        {"map1/a", "map1/b", "map2/c", "map3/d", "map4/e", "map5/f", "map6/g", "map7/h"})


def test_walked_rows_tolerates_missing_status_dicts(tmp_path):
    (tmp_path / "chb.py").write_text(
        "from types import SimpleNamespace as NS\nCHAPTER = NS(beats=[])\n", encoding="utf-8")
    assert walked_rows("CHB", tmp_path) == frozenset()


def test_walked_rows_fails_loud_without_module(tmp_path):
    with pytest.raises(ValueError, match="no generated module"):
        walked_rows("CHZ", tmp_path)
