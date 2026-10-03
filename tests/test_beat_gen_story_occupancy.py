"""`beat_gen.__main__._StoryOccupancy`: an object whose event can never be
visible in the chapter blocks nothing (2026-10-02: the converter began
placing late NPCs as flag-hidden actors, and map050's FINAL_EVENT-gated
EV024/EV025 took EV007's only approach cell away in CH01)."""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.beat_gen.__main__ import _StoryOccupancy
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
