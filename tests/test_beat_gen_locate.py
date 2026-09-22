"""Tests for `rpg2gba.beat_gen.locate` (C6 Task 4).

Most tests pass a fake `cell_fn`/`seam_fn`, so they pin the adapter logic
without touching map data. The real-data tests use CH05, and the committed
`reference/routes/CH05.route.json`.

STATUS: implemented, skipped. DELETE the `pytestmark` line to start Task 4.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.beat_gen import locate
from rpg2gba.beat_gen.plan import PlannedBeat, make_kwargs
from rpg2gba.beat_gen.seam import SeamCrossing
from rpg2gba.chapter_manifest.schema import ManifestRow
from rpg2gba.routing.locations import ApproachCandidate, RowCell
from rpg2gba.routing.plan import ChosenApproach, RouteNode

PAGE = "map001/ev001/p0"
ARM = "map001/ev001/p0/b0"
PAGE2 = "map001/ev002/p0"
SEAM = "map001/seam/N/map002"

ROWS = {
    PAGE: ManifestRow(row_id=PAGE, kind="page", map_id=1, content_hash="x", event_id=1,
                      page_idx=0),
    ARM: ManifestRow(row_id=ARM, kind="branch", map_id=1, content_hash="x",
                     parent_row_id=PAGE),
    PAGE2: ManifestRow(row_id=PAGE2, kind="page", map_id=1, content_hash="x", event_id=2,
                       page_idx=0),
    SEAM: ManifestRow(row_id=SEAM, kind="seam", map_id=1, content_hash="x"),
}

CELLS = {
    PAGE: RowCell(PAGE, "MAP_ONE", 4, 5, "approach_to(MAP_ONE, ev1)",
                  (ApproachCandidate(4, 5, "south", "s"), ApproachCandidate(3, 4, "west", "w"))),
    PAGE2: RowCell(PAGE2, "MAP_ONE", 9, 9, "event_cell(MAP_ONE, ev2)"),
}


def _cell_fn(row: ManifestRow) -> RowCell:
    if row.row_id not in CELLS:
        raise ValueError(f"{row.row_id}: no walkable adjacent cell")
    return CELLS[row.row_id]


def _seam_fn(row: ManifestRow) -> tuple[SeamCrossing, ...]:
    return (SeamCrossing((5, 0), (5, 9), "UP"), SeamCrossing((6, 0), (6, 9), "UP"))


def _locate(beats, **overrides):
    kwargs = {"cell_fn": _cell_fn, "seam_fn": _seam_fn, "map_constant_fn": lambda m: "MAP_ONE"}
    kwargs.update(overrides)
    return locate.locate_beats(beats, ROWS, **kwargs)


def _beat(name: str, rows: tuple[str, ...], group: str | None = None, **kw) -> PlannedBeat:
    return PlannedBeat(name=name, template="generic", map_id=1, rows=rows,
                       group=group or name, kwargs=make_kwargs(**kw))


# --- locate_beats -------------------------------------------------------------

def test_one_record_per_group_carrying_every_row():
    beats = [_beat("a", (PAGE,)), _beat("a_arms", (ARM,), group="a", skip_claimed=True)]
    records, refusals = _locate(beats)
    assert refusals == []
    (rec,) = records
    assert rec.beat_id == "a"
    assert rec.rows == (PAGE, ARM)
    assert (rec.map_constant, rec.x, rec.y) == ("MAP_ONE", 4, 5)
    assert rec.approach_candidates == CELLS[PAGE].approach_candidates


def test_arm_is_located_through_its_page_under_its_own_id():
    records, _ = _locate([_beat("arms", (ARM,))])
    (cand,) = records[0].candidates
    assert cand.row_id == ARM
    assert (cand.map_constant, cand.x, cand.y) == ("MAP_ONE", 4, 5)


def test_nested_arm_is_located_through_its_page_not_its_parent_arm():
    # Added by the lead (2026-09-22): a nested arm's parent_row_id is another
    # arm, which cell_fn refuses; it must resolve through the owning page.
    nested = "map001/ev001/p0/b1"
    rows = dict(ROWS)
    rows[nested] = ManifestRow(row_id=nested, kind="branch", map_id=1, content_hash="x",
                               parent_row_id=ARM)
    records, refusals = locate.locate_beats(
        [_beat("arms", (ARM, nested))], rows, cell_fn=_cell_fn, seam_fn=_seam_fn,
        map_constant_fn=lambda m: "MAP_ONE")
    assert refusals == []
    assert {c.row_id for c in records[0].candidates} == {ARM, nested}


def test_seam_row_offers_every_crossing_as_a_candidate():
    records, _ = _locate([PlannedBeat(name="s", template="seam", map_id=1, rows=(SEAM,),
                                      group="s")])
    (rec,) = records
    assert (rec.map_constant, rec.x, rec.y) == ("MAP_ONE", 5, 0)   # first crossing
    assert [(a.x, a.y) for a in rec.approach_candidates] == [(5, 0), (6, 0)]
    assert len({a.side for a in rec.approach_candidates}) == 2    # distinguishable picks


def test_seam_with_no_crossing_is_refused():
    beat = PlannedBeat(name="s", template="seam", map_id=1, rows=(SEAM,), group="s")
    records, refusals = _locate([beat], seam_fn=lambda row: ())
    assert records == []
    assert [(r.row_id, r.blocker) for r in refusals] == [(SEAM, "cell")]


def test_one_unlocatable_row_refuses_its_whole_group():
    bad = "map001/ev003/p0"
    rows = dict(ROWS)
    rows[bad] = ManifestRow(row_id=bad, kind="page", map_id=1, content_hash="x")
    beats = [_beat("a", (PAGE, bad)), _beat("b", (PAGE2,))]
    records, refusals = locate.locate_beats(beats, rows, cell_fn=_cell_fn, seam_fn=_seam_fn,
                                            map_constant_fn=lambda m: "MAP_ONE")
    assert [r.beat_id for r in records] == ["b"]
    assert sorted(r.row_id for r in refusals) == sorted([PAGE, bad])
    assert {r.blocker for r in refusals} == {"cell"}
    by_row = {r.row_id: r for r in refusals}
    assert "no walkable adjacent cell" in by_row[bad].detail


def test_records_in_first_appearance_order():
    records, _ = _locate([_beat("b", (PAGE2,)), _beat("a", (PAGE,))])
    assert [r.beat_id for r in records] == ["b", "a"]


# --- route_order ----------------------------------------------------------------

def _node(i, kind, group=None, side=None):
    return RouteNode(index=i, kind=kind, map_id=1, cell=(0, 0), group=group,
                     beats=(group,) if group else (),
                     chosen_approach=ChosenApproach(side, f"r:{side}") if side else None)


def test_route_order_skips_entry_and_exit_and_collects_picks():
    nodes = [_node(0, "entry"), _node(1, "group", "b", "west"), _node(2, "group", "a"),
             _node(3, "exit")]
    assert locate.route_order(nodes) == (("b", "a"), {"b": "west"})


def test_route_order_real_ch05_file():
    from rpg2gba.routing.plan import load_plan
    plan = load_plan(Path("reference/routes/CH05.route.json"))
    order, picks = locate.route_order(plan.nodes)
    assert order == ("B1", "B2", "B3", "B5", "B4", "B8", "B9", "B14", "B13", "B10", "B11")
    assert picks == {}


# --- order_beats ----------------------------------------------------------------

def test_order_beats_moves_whole_groups_and_applies_picks():
    beats = [_beat("a", (PAGE,)), _beat("a_arms", (ARM,), group="a", skip_claimed=True),
             _beat("b", (PAGE2,))]
    out = locate.order_beats(beats, ["b", "a"], {"a": "west"})
    assert [b.name for b in out] == ["b", "a", "a_arms"]
    assert out[1].kwarg("approach_prefer") == "west"
    assert out[2].kwarg("approach_prefer") == "west"
    assert out[2].kwarg("skip_claimed") is True        # existing kwargs kept, still sorted
    assert "approach_prefer" not in dict(out[0].kwargs)


def test_order_beats_rejects_a_missing_group():
    with pytest.raises(ValueError, match="a"):
        locate.order_beats([_beat("a", (PAGE,)), _beat("b", (PAGE2,))], ["b"], {})


def test_order_beats_rejects_an_unknown_group():
    with pytest.raises(ValueError, match="zzz"):
        locate.order_beats([_beat("a", (PAGE,))], ["a", "zzz"], {})


# --- real data ----------------------------------------------------------------

def test_real_ch05_every_group_locates():
    from rpg2gba.beat_floor.walk import floor_for_chapter
    from rpg2gba.beat_gen.group import plan_beats
    from rpg2gba.beat_gen.select import select_rows
    from rpg2gba.chapter_manifest.archetypes import classify_manifest
    from rpg2gba.playtest.archetypes import load_chapter_rows
    from rpg2gba.routing.locations import cell_for_row
    from rpg2gba.story_state.model import build_chapter_stories

    build = Path("output/uranium-build")
    rows = load_chapter_rows("CH05")
    story = build_chapter_stories(["CH01", "CH02", "CH03", "CH04", "CH05"], build_dir=build,
                                  chapters_path=Path("reference/chapters.json"))["CH05"]
    floors = floor_for_chapter("CH05", build_dir=build)
    sel = select_rows(rows, {v.row_id: v for v in story.rows}, floors)
    beats = plan_beats(sel.owned, classify_manifest(rows), floors)

    def no_seams(row):
        raise AssertionError("CH05 has no seam rows")

    records, refusals = locate.locate_beats(
        beats, {r.row_id: r for r in rows}, cell_fn=cell_for_row, seam_fn=no_seams,
        map_constant_fn=lambda m: {36: "MAP_PASSAGE_CAVE_1F", 37: "MAP_PASSAGE_CAVE_2F"}[m])
    assert refusals == []
    assert len(records) == len({b.group for b in beats}) == 14
