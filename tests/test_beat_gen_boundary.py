"""`beat_gen.boundary` (C6 part two; REDERIVATION_PLAN.md §10 R2/R3): which
rows a chapter hands to its successor, and which it claims from its
predecessor."""
import pytest

from rpg2gba.beat_floor.assertion import FloorAssertion, RowFloor, make_params
from rpg2gba.beat_gen.boundary import inbound_rows, split_outbound, warp_destinations
from rpg2gba.beat_gen.plan import Elsewhere, Selection
from rpg2gba.chapter_manifest.schema import ManifestRow

WARP = "map001/ev001/p0"        # warps to map 9
NUDGE = "map001/ev001/p1"       # same event: the arrival autorun
ARM = "map001/ev001/p1/b0"
OTHER = "map001/ev002/p0"       # unrelated event, warps to map 2


def _row(row_id: str, kind: str = "page") -> ManifestRow:
    event = int(row_id.split("/ev")[1][:3])
    if kind == "branch":
        return ManifestRow(row_id=row_id, kind="branch", map_id=1, content_hash="x",
                           parent_row_id=row_id.rsplit("/", 1)[0])
    return ManifestRow(row_id=row_id, kind="page", map_id=1, content_hash="x",
                       event_id=event, page_idx=int(row_id[-1]))


def _floor(row_id: str, *warp_maps: int) -> RowFloor:
    return RowFloor(row_id=row_id, trigger="player_touch", refusals=(), assertions=frozenset(
        FloorAssertion(row_id=row_id, kind="warp", list_index=i, code=201,
                       params=make_params(map_id=m, x=0, y=0), tag="position")
        for i, m in enumerate(warp_maps)))


ROWS = (_row(WARP), _row(NUDGE), _row(ARM, "branch"), _row(OTHER))
FLOORS = {WARP: _floor(WARP, 9), NUDGE: _floor(NUDGE), ARM: _floor(ARM),
          OTHER: _floor(OTHER, 2)}


def test_warp_destinations_reads_page_floors():
    assert warp_destinations(ROWS, FLOORS) == {WARP: 9, OTHER: 2}


def test_a_page_with_two_destinations_fails_loud():
    with pytest.raises(ValueError, match="expected one destination"):
        warp_destinations((_row(WARP),), {WARP: _floor(WARP, 2, 3)})


def test_outbound_keeps_the_crossing_page_and_hands_its_event_to_the_successor():
    sel = split_outbound(Selection(owned=ROWS, refusals=(), elsewhere=()), FLOORS,
                         chain_maps=frozenset({1, 2}), successor_id="CHNEXT")
    assert [r.row_id for r in sel.owned] == [WARP, OTHER]
    assert sel.elsewhere == (Elsewhere(NUDGE, "boundary", "CHNEXT"),
                             Elsewhere(ARM, "boundary", "CHNEXT"))


def test_no_boundary_event_leaves_the_selection_untouched():
    sel = Selection(owned=ROWS, refusals=(), elsewhere=())
    assert split_outbound(sel, FLOORS, frozenset({1, 2, 9}), "CHNEXT") is sel


def test_inbound_claims_every_page_and_arm_of_a_crossing_into_this_chapter():
    got = inbound_rows(ROWS, FLOORS, chapter_maps=frozenset({9}),
                       pred_chain_maps=frozenset({1, 2}))
    assert [r.row_id for r in got] == [WARP, NUDGE, ARM]


def test_inbound_ignores_warps_inside_the_predecessor_chain():
    assert inbound_rows(ROWS, FLOORS, chapter_maps=frozenset({2}),
                        pred_chain_maps=frozenset({1, 2})) == ()
