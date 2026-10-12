"""`beat_gen.__main__._StoryOccupancy`: an object whose event can never be
visible in the chapter blocks nothing (2026-10-02: the converter began
placing late NPCs as flag-hidden actors, and map050's FINAL_EVENT-gated
EV024/EV025 took EV007's only approach cell away in CH01)."""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.beat_gen.__main__ import _StoryOccupancy, actor_never_blocks
from rpg2gba.routing.occupancy import MapOccupancy, OccupiedTile

BUILD = Path("output/uranium-build")
pytestmark = pytest.mark.skipif(not (BUILD / "maps" / "Map050.json").exists(),
                                reason="needs the deserialized maps")

_TILES = (
    OccupiedTile(cell=(12, 13), script="Map050_EV024_Dispatch",
                 movement_type="MOVEMENT_TYPE_FACE_DOWN"),
    OccupiedTile(cell=(18, 14), script="Map050_EV004_Dispatch",
                 movement_type="MOVEMENT_TYPE_FACE_DOWN"),
)


def _occ(candidate) -> _StoryOccupancy:  # noqa: ANN001
    inner = {50: MapOccupancy(map_id=50, tiles=_TILES)}
    return _StoryOccupancy(inner, build_dir=BUILD, candidate_for=lambda _m: candidate)


def test_a_never_visible_hidden_actor_blocks_nothing():
    # EV024's visible pages can't be live; EV004's can.
    occ = _occ(lambda rid: not rid.startswith("map050/ev024/"))
    assert occ[50].blocked_cells() == frozenset({(18, 14)})


def test_a_possibly_visible_object_still_blocks():
    occ = _occ(lambda rid: True)
    assert occ[50].blocked_cells() == frozenset({(12, 13), (18, 14)})


def test_an_obstacle_wall_blocks_whatever_the_story_says():
    # 2026-10-12: Moki's rocks looked "cleared" (story model explores both
    # arms of Kernel.pbRockSmash); an obstacle-claimed event never drops out.
    inner = {50: MapOccupancy(map_id=50, tiles=_TILES)}
    occ = _StoryOccupancy(inner, build_dir=BUILD, candidate_for=lambda _m: lambda rid: False,
                          walls=frozenset({(50, 24)}))
    assert occ[50].blocked_cells() == frozenset({(12, 13)})
    assert (12, 13) not in occ.clearing_rows(50)


# --- `actor_never_blocks`: the page rule, including actors that clear -----
# First "clears" user: Fufufu (map14001/ev018), visible on p0/p1 and
# graphic-less on p2 (self-switch B) and p3 (switch 55), standing on the gym
# door's only approach (operator call 2026-10-09).

_SEEN = {"graphic": {"character_name": "HGSS_130", "opacity": 255}}
_GONE = {"graphic": {"character_name": ""}}


def test_actor_that_clears_in_chapter_does_not_block():
    assert actor_never_blocks([_SEEN, _SEEN, _GONE, _GONE], lambda i: True)


def test_actor_whose_clearing_page_cannot_be_live_blocks():
    assert not actor_never_blocks([_SEEN, _SEEN, _GONE], lambda i: i < 2)


def test_invisible_page_below_a_visible_one_does_not_clear():
    # p0 graphic-less, p1 visible: p1 outranks p0 whenever both are live.
    assert not actor_never_blocks([_GONE, _SEEN], lambda i: True)


def test_actor_never_visible_in_chapter_does_not_block():
    assert actor_never_blocks([_SEEN, _GONE], lambda i: False)


def test_event_with_no_visible_page_is_not_an_actor():
    assert not actor_never_blocks([_GONE, _GONE], lambda i: True)


def test_zero_opacity_counts_as_invisible():
    faded = {"graphic": {"character_name": "HGSS_130", "opacity": 0}}
    assert actor_never_blocks([_SEEN, faded], lambda i: True)


def test_clearing_page_is_judged_by_can_clear():
    # CH06's Nowtoch crowd: page 1 (no graphic) is only undetermined, so the
    # crowd stays a wall even though its visible page can be live.
    assert not actor_never_blocks([_SEEN, _GONE], lambda i: True, lambda i: False)
    assert actor_never_blocks([_SEEN, _GONE], lambda i: True, lambda i: i == 1)


def test_page_candidate_definite_needs_positive_evidence():
    from types import SimpleNamespace

    from rpg2gba.beat_gen.__main__ import _page_candidate

    verdicts = {"live": SimpleNamespace(status="live"),
                "undet": SimpleNamespace(status="undetermined"),
                "later": SimpleNamespace(status="later")}
    loose = _page_candidate(verdicts, (), {})
    strict = _page_candidate(verdicts, (), {}, definite=True)
    assert [loose(r) for r in ("live", "undet", "none", "later")] == [True, True, True, False]
    assert [strict(r) for r in ("live", "undet", "none", "later")] == [True, False, False, False]
