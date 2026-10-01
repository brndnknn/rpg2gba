"""Tests for `rpg2gba.beat_gen.select` (C6 Task 1).

Synthetic rows/verdicts/floors pin the rule table; two real-data tests pin
CH05 (the chapter that must come out green) and the CH01 partition.

STATUS: implemented, skipped. DELETE the `pytestmark` line to start Task 1.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.beat_floor.assertion import FloorAssertion, FloorRefusal, RowFloor, make_params
from rpg2gba.beat_gen import select
from rpg2gba.beat_gen.plan import Elsewhere, Refusal
from rpg2gba.chapter_manifest.schema import ManifestRow
from rpg2gba.story_state.model import RowVerdict


def _row(row_id: str, kind: str = "page", *, requires: tuple[str, ...] = ()) -> ManifestRow:
    return ManifestRow(row_id=row_id, kind=kind, map_id=int(row_id[3:6]), content_hash="x",
                       requires=requires)


def _obstacle_floor(row_id: str) -> RowFloor:
    rock = FloorAssertion(row_id=row_id, kind="blocked_obstacle", list_index=-1, code=None,
                          params=make_params(x=1, y=1, capability="rock_smash"),
                          tag="position")
    return RowFloor(row_id=row_id, trigger="action", assertions=frozenset({rock}),
                    refusals=())


def _verdict(row_id: str, status: str = "live", *, owner: str | None = "CH09",
             refusals: tuple[str, ...] = ()) -> RowVerdict:
    return RowVerdict(row_id=row_id, status=status, owner=owner, stage=0, enabled_by=(),
                      killed_by=(), blockers=(), forced=False, refusals=refusals, detail=None)


def _floor(row_id: str, *reasons: str) -> RowFloor:
    refusals = tuple(FloorRefusal(row_id=row_id, reason=r, list_index=0, code=None,
                                  detail=f"saw {r}") for r in reasons)
    return RowFloor(row_id=row_id, trigger="action", assertions=frozenset(), refusals=refusals)


PAGE = "map001/ev001/p0"
ARM = "map001/ev001/p0/b0"
SEAM = "map001/seam/N/map002"
STAIR = "map001/terrain/stairs/3,4"


# --- blocker_for ------------------------------------------------------------

@pytest.mark.parametrize("reason, blocker", [
    ("text_unnormalizable", "#109"),
    ("unknown_script_head", "C8"),
    ("non_literal_args", "C8"),
    ("unparsed_state_write", "C8"),
    ("unmodelled_outcome", "story-state"),
    ("unmodelled_predicate", "story-state"),
    ("unclassified_condition", "story-state"),
    ("story_state_refusal", "story-state"),
    ("stair_no_qualifying_page", "floor"),
    ("obstacle_missing_cell", "floor"),
])
def test_blocker_table(reason, blocker):
    assert select.blocker_for(reason) == blocker


def test_blocker_unknown_reason_fails_loud():
    with pytest.raises(ValueError, match="brand_new_reason"):
        select.blocker_for("brand_new_reason")


# --- the rule table ---------------------------------------------------------

def _select(rows, verdicts, floors):
    return select.select_rows(rows, {v.row_id: v for v in verdicts},
                              {f.row_id: f for f in floors})


def test_live_clean_row_is_owned():
    sel = _select([_row(PAGE)], [_verdict(PAGE)], [_floor(PAGE)])
    assert [r.row_id for r in sel.owned] == [PAGE]
    assert sel.refusals == () and sel.elsewhere == ()


def test_live_row_with_refused_floor_is_refused_by_floor_reason():
    sel = _select([_row(PAGE)], [_verdict(PAGE)], [_floor(PAGE, "text_unnormalizable")])
    assert sel.owned == ()
    assert sel.refusals == (Refusal(PAGE, "#109", "text_unnormalizable",
                                    "saw text_unnormalizable"),)


def test_story_refusal_uses_the_head_and_keeps_the_whole_string():
    v = _verdict(PAGE, "refused", refusals=("unmodelled_outcome:phone_battle_count(trainer)",))
    sel = _select([_row(PAGE)], [v], [_floor(PAGE)])
    (ref,) = sel.refusals
    assert ref.blocker == "story-state"
    assert ref.reason == "unmodelled_outcome"
    assert "phone_battle_count" in ref.detail


def test_story_refusal_wins_over_floor_refusal():
    v = _verdict(PAGE, "refused", refusals=("unparsed_state_write",))
    sel = _select([_row(PAGE)], [v], [_floor(PAGE, "text_unnormalizable")])
    (ref,) = sel.refusals
    assert (ref.blocker, ref.reason) == ("C8", "unparsed_state_write")


def test_undetermined_is_a_story_state_refusal():
    sel = _select([_row(PAGE)], [_verdict(PAGE, "undetermined")], [_floor(PAGE)])
    (ref,) = sel.refusals
    assert (ref.blocker, ref.reason) == ("story-state", "undetermined")


def test_later_goes_elsewhere_with_its_owner():
    sel = _select([_row(PAGE)], [_verdict(PAGE, "later", owner="CH25")], [_floor(PAGE)])
    assert sel.elsewhere == (Elsewhere(PAGE, "later", "CH25"),)
    assert sel.owned == () and sel.refusals == ()


def test_unreachable_goes_elsewhere_without_owner():
    sel = _select([_row(PAGE)], [_verdict(PAGE, "unreachable", owner=None)], [_floor(PAGE)])
    assert sel.elsewhere == (Elsewhere(PAGE, "unreachable", None),)


def test_event_row_without_verdict_is_refused_not_dropped():
    sel = _select([_row(ARM, "branch")], [], [_floor(ARM)])
    (ref,) = sel.refusals
    assert (ref.row_id, ref.blocker, ref.reason) == (ARM, "story-state", "no_story_verdict")


@pytest.mark.parametrize("row_id, kind", [(SEAM, "seam"), (STAIR, "terrain")])
def test_row_level_kinds_need_no_verdict(row_id, kind):
    sel = _select([_row(row_id, kind)], [], [_floor(row_id)])
    assert [r.row_id for r in sel.owned] == [row_id]


def test_row_level_kind_with_refused_floor():
    sel = _select([_row(STAIR, "terrain")], [], [_floor(STAIR, "stair_no_qualifying_page")])
    (ref,) = sel.refusals
    assert (ref.blocker, ref.reason) == ("floor", "stair_no_qualifying_page")


def test_row_behind_an_obstacle_is_blocked_elsewhere():
    # Live in the story model, but it needs a capability and is NOT the obstacle.
    row = _row(PAGE, requires=("surf",))
    sel = _select([row], [_verdict(PAGE)], [_floor(PAGE)])
    assert sel.elsewhere == (Elsewhere(PAGE, "blocked", None, ("surf",)),)
    assert sel.owned == ()


def test_the_obstacle_itself_is_owned():
    row = _row(PAGE, requires=("rock_smash",))
    sel = _select([row], [_verdict(PAGE)], [_obstacle_floor(PAGE)])
    assert [r.row_id for r in sel.owned] == [PAGE]


def test_story_refusal_wins_over_blocked():
    row = _row(PAGE, requires=("surf",))
    v = _verdict(PAGE, "refused", refusals=("unparsed_state_write",))
    sel = _select([row], [v], [_floor(PAGE)])
    assert [r.reason for r in sel.refusals] == ["unparsed_state_write"]


def test_blocked_wins_over_floor_refusal():
    # We will not walk it this chapter, so its floor gap is not this chapter's red.
    row = _row(PAGE, requires=("surf",))
    sel = _select([row], [_verdict(PAGE)], [_floor(PAGE, "text_unnormalizable")])
    assert [e.status for e in sel.elsewhere] == ["blocked"]
    assert sel.refusals == ()


def test_missing_floor_fails_loud():
    with pytest.raises(ValueError, match=PAGE):
        _select([_row(PAGE)], [_verdict(PAGE)], [])


def test_partition_keeps_manifest_order():
    ids = ["map001/ev003/p0", "map001/ev001/p0", "map001/ev002/p0", "map001/ev004/p0"]
    verdicts = [_verdict(ids[0]), _verdict(ids[1], "later"), _verdict(ids[2]),
                _verdict(ids[3], "undetermined")]
    sel = _select([_row(i) for i in ids], verdicts, [_floor(i) for i in ids])
    assert [r.row_id for r in sel.owned] == [ids[0], ids[2]]   # manifest order, not sorted
    assert [e.row_id for e in sel.elsewhere] == [ids[1]]
    assert [r.row_id for r in sel.refusals] == [ids[3]]


# --- real data --------------------------------------------------------------

BUILD = Path("output/uranium-build")


@pytest.fixture(scope="module")
def stories():
    from rpg2gba.story_state.model import build_chapter_stories
    return build_chapter_stories(["CH01", "CH02", "CH03", "CH04", "CH05"], build_dir=BUILD,
                                 chapters_path=Path("reference/chapters.json"))


def _real(chapter: str, stories):
    from rpg2gba.beat_floor.walk import floor_for_chapter
    from rpg2gba.playtest.archetypes import load_chapter_rows
    rows = load_chapter_rows(chapter)
    verdicts = {v.row_id: v for v in stories[chapter].rows}
    return rows, select.select_rows(rows, verdicts, floor_for_chapter(chapter, build_dir=BUILD))


def test_real_ch05_owns_all_but_the_surf_items(stories):
    rows, sel = _real("CH05", stories)
    assert len(rows) == 43
    assert sel.refusals == ()
    # ev8/ev9 are item balls across water: live in the story model, blocked by surf.
    assert {e.row_id[:13] for e in sel.elsewhere} == {"map036/ev008/", "map036/ev009/"}
    assert {e.status for e in sel.elsewhere} == {"blocked"}
    assert len(sel.elsewhere) == 8
    assert len(sel.owned) == 35


def test_real_ch01_partitions_and_classifies_every_refusal(stories):
    rows, sel = _real("CH01", stories)
    buckets = ([r.row_id for r in sel.owned] + [r.row_id for r in sel.refusals]
               + [e.row_id for e in sel.elsewhere])
    assert sorted(buckets) == sorted(r.row_id for r in rows)   # each row exactly once
    assert sel.refusals, "CH01 is expected to carry refusals (C6 plan B2)"


# --- Elsewhere validation (C9 ruling 3) -----------------------------------------

def test_elsewhere_never_fires_requires_nonempty_detail():
    with pytest.raises(ValueError, match="never_fires"):
        Elsewhere("map068/ev012/p1", "never_fires")


def test_elsewhere_never_fires_with_detail_is_fine():
    e = Elsewhere("map068/ev012/p1", "never_fires", detail="no warp lands on this cell")
    assert e.detail == "no warp lands on this cell"


def test_strip_listed_event_rows_are_stripped_not_owned():
    """2026-09-27 ROM run: CH01 walked Moki Town's no-port `Luz` lamps
    (strip_list.json map_events) and found no script to talk to."""
    from rpg2gba.beat_floor.assertion import RowFloor
    from rpg2gba.chapter_manifest.schema import ManifestRow

    row = ManifestRow(row_id="map032/ev052/p0", kind="page", map_id=32, content_hash="x",
                      event_id=52)
    floor = RowFloor(row_id=row.row_id, trigger="action", assertions=(), refusals=())
    sel = select.select_rows([row], {}, {row.row_id: floor}, stripped={(32, 52): "Luz"})
    assert sel.owned == () and sel.refusals == ()
    assert [(e.row_id, e.status) for e in sel.elsewhere] == [("map032/ev052/p0", "stripped")]
    assert "Luz" in sel.elsewhere[0].detail


def _page(*codes: int) -> dict:
    return {"list": [{"code": c} for c in codes]}


def test_empty_events_only_when_every_page_is_empty():
    """ROM run 26: the lab's invisible machine-side cells (one empty page)
    are empty; an empty page superseding a real one (NurseTut p1, hand
    CH03 N3) is not -- its beat proves the scene doesn't replay."""
    map_json = {"events": [
        None,
        {"id": 17, "pages": [_page(0)]},
        {"id": 16, "pages": [_page(101, 0), _page(0)]},
        {"id": 3, "pages": [_page(0), _page(0)]},
        {"id": 4, "pages": []},
    ]}
    assert select.empty_events(50, map_json) == {(50, 17), (50, 3)}


def test_empty_event_rows_are_empty_page_not_owned():
    from rpg2gba.beat_floor.assertion import RowFloor
    from rpg2gba.chapter_manifest.schema import ManifestRow

    row = ManifestRow(row_id="map050/ev018/p0", kind="page", map_id=50, content_hash="x",
                      event_id=18)
    floor = RowFloor(row_id=row.row_id, trigger="action", assertions=(), refusals=())
    sel = select.select_rows([row], {}, {row.row_id: floor}, empty={(50, 18)})
    assert sel.owned == () and sel.refusals == ()
    assert [(e.row_id, e.status) for e in sel.elsewhere] == [("map050/ev018/p0", "empty_page")]
    assert sel.elsewhere[0].detail


def _touch_event(eid: int, *commands: dict, character: str = "") -> dict:
    return {"id": eid, "x": eid, "y": 11, "name": f"EV{eid:03d}", "pages": [{
        "trigger": 1, "condition": {}, "graphic": {"character_name": character},
        "list": [*commands, {"code": 0, "parameters": []}],
    }]}


_SURF_CANCEL = (
    {"code": 111, "parameters": [12, "$PokemonGlobal.surfing"]},
    {"code": 355, "parameters": ["Kernel.pbCancelVehicles"]},
)


def test_dropped_events_follow_the_converter_rule():
    """ROM run 53: Route 1's surf-cancel tiles (blank, player touch, no
    transfer) never reach the ROM. A transferring one is a gated door and a
    visible one an object; both are kept, so neither is listed."""
    map_json = {"events": [
        None,
        _touch_event(147, *_SURF_CANCEL),
        _touch_event(5, {"code": 201, "parameters": [0, 32, 1, 1, 0, 0]}),
        _touch_event(6, *_SURF_CANCEL, character="trainer_POKEMONTRAINER_Brendan"),
    ]}
    got = select.dropped_events(33, map_json)
    assert list(got) == [(33, 147)]
    assert "blank_trigger1" in got[(33, 147)]
    assert "$PokemonGlobal.surfing / Kernel.pbCancelVehicles" in got[(33, 147)]


def test_dropped_event_rows_are_converter_dropped_not_owned():
    from rpg2gba.beat_floor.assertion import RowFloor
    from rpg2gba.chapter_manifest.schema import ManifestRow

    row = ManifestRow(row_id="map033/ev147/p0", kind="page", map_id=33, content_hash="x",
                      event_id=147)
    floor = RowFloor(row_id=row.row_id, trigger="player_touch", assertions=(), refusals=())
    sel = select.select_rows([row], {}, {row.row_id: floor},
                             dropped={(33, 147): "converter drops it"})
    assert sel.owned == () and sel.refusals == ()
    assert [(e.row_id, e.status) for e in sel.elsewhere] == [
        ("map033/ev147/p0", "converter_dropped")]
