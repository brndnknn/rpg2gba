"""Tests for `rpg2gba.traversal.capabilities`.

Synthetic tests exercise the classification rules in isolation (the code-111
trap, boulder-vs-rock disambiguation, terrain-tag mapping, the unverified-
capability guard). Golden tests replay real corpus maps and assert exact
obstacle sets — CLAUDE.md §4.5/§4.6: a corpus mismatch here is a real finding,
not something to paper over by editing the expectation.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.traversal.capabilities import (
    Capability,
    CapabilityMap,
    Obstacle,
    UnverifiedCapabilityError,
    VERIFIED_CAPABILITIES,
    _effective_terrain_tag,
    _event_capability,
    _find_event_obstacles,
    _find_terrain_obstacles,
    build_capability_map,
)
from rpg2gba.traversal.collision import TilesetArrays
from rpg2gba.tileset_converter.layout import TileGrid

MAPS_DIR = Path("output/uranium-build/maps")
TILESETS_JSON = Path("output/uranium-build/tilesets.json")
CORPUS_PRESENT = MAPS_DIR.is_dir() and TILESETS_JSON.is_file()

requires_corpus = pytest.mark.skipif(
    not CORPUS_PRESENT,
    reason="requires the decoded corpus under output/uranium-build/ (run the pipeline first)",
)


def _script_page(*commands: dict) -> dict:
    return {"list": list(commands)}


def _event(event_id: int, x: int, y: int, *pages: dict) -> dict:
    return {"id": event_id, "name": "Rock", "x": x, "y": y, "pages": list(pages)}


# --- Event-head detection ----------------------------------------------------


def test_code_111_conditional_branch_rock_smash_detected():
    """The known trap: a bare code-355 `pbRockSmash` head does not exist in the
    corpus — every rock is gated via a code-111 branch instead."""
    page = _script_page({"code": 111, "parameters": [12, "Kernel.pbRockSmash"]})
    event = _event(1, 5, 5, page)
    assert _event_capability(event) is Capability.ROCK_SMASH


def test_code_355_random_encounter_variant_detected():
    page = _script_page({"code": 355, "parameters": ["Kernel.pbRockSmashRandomEncounter"]})
    event = _event(2, 5, 5, page)
    assert _event_capability(event) is Capability.ROCK_SMASH


def test_boulder_classifies_as_strength_not_rock_smash():
    page = _script_page({"code": 355, "parameters": ["pbPushThisBoulder"]})
    event = _event(3, 5, 5, page)
    assert _event_capability(event) is Capability.STRENGTH


def test_boulder_via_code_111_also_detected():
    """map 96's regression case: pbPushThisBoulder appears only inside a
    code-111 branch, with no "Kernel." prefix."""
    page = _script_page({"code": 111, "parameters": [12, "pbPushThisBoulder"]})
    event = _event(4, 5, 6, page)
    assert _event_capability(event) is Capability.STRENGTH


def test_event_counts_once_across_multiple_matching_pages():
    page_a = _script_page({"code": 355, "parameters": ["Kernel.pbRockSmash"]})
    page_b = _script_page({"code": 355, "parameters": ["Kernel.pbRockSmashRandomEncounter"]})
    event = _event(5, 5, 5, page_a, page_b)
    obstacles = _find_event_obstacles({"events": [event]})
    assert len(obstacles) == 1
    assert obstacles[0].capability is Capability.ROCK_SMASH
    assert obstacles[0].event_id == 5


def test_unrecognized_plausible_head_is_not_classified():
    """A head that *looks* like a hidden-move call (pbSurf/pbCut/pbFlash are
    all real Essentials methods, per reference/scripts_dump/103__
    PField_HiddenMoves.rb) but has no verified obstacle-detection method must
    not be silently guessed at."""
    page = _script_page({"code": 355, "parameters": ["Kernel.pbSurf(true)"]})
    event = _event(6, 5, 5, page)
    assert _event_capability(event) is None


def test_non_script_conditional_branch_ignored():
    """A code-111 branch whose parameters[0] isn't the script-condition type
    (12) carries no Ruby text and must not be scanned as if it did."""
    page = _script_page({"code": 111, "parameters": [6, -1, 8]})
    event = _event(7, 5, 5, page)
    assert _event_capability(event) is None


# --- Terrain-tag detection ----------------------------------------------------


def _flat_grid(tile_id: int) -> TileGrid:
    """A 1x1, 3-layer grid whose bottom layer is `tile_id` and whose other
    two layers are empty (RMXP tile id 0)."""
    return TileGrid(xsize=1, ysize=1, zsize=3, data=[tile_id, 0, 0])


def _arrays_with_tag(tile_id: int, tag: int) -> TilesetArrays:
    size = tile_id + 1
    passages = [0] * size
    priorities = [0] * size
    terrain_tags = [0] * size
    terrain_tags[tile_id] = tag
    return TilesetArrays(passages=passages, priorities=priorities, terrain_tags=terrain_tags)


@pytest.mark.parametrize("tag", [5, 7, 17])
def test_terrain_tag_surf_tags_classify_as_surf(tag: int):
    grid = _flat_grid(tile_id=10)
    arrays = _arrays_with_tag(tile_id=10, tag=tag)
    obstacles = _find_terrain_obstacles(grid, arrays)
    assert len(obstacles) == 1
    assert obstacles[0].capability is Capability.SURF
    assert obstacles[0].cell == (0, 0)
    assert obstacles[0].detail == str(tag)


@pytest.mark.parametrize("tag", [8, 9])
def test_terrain_tag_waterfall_tags_classify_as_waterfall(tag: int):
    grid = _flat_grid(tile_id=10)
    arrays = _arrays_with_tag(tile_id=10, tag=tag)
    obstacles = _find_terrain_obstacles(grid, arrays)
    assert len(obstacles) == 1
    assert obstacles[0].capability is Capability.WATERFALL


def test_terrain_tag_normal_yields_no_obstacle():
    grid = _flat_grid(tile_id=10)
    arrays = _arrays_with_tag(tile_id=10, tag=0)
    assert _find_terrain_obstacles(grid, arrays) == []


def test_effective_terrain_tag_topmost_nonzero_wins():
    # z ascending, bottom-first: bottom=water(tag7), middle=empty, top=grass(tag2)
    terrain_tags = [0, 7, 2]
    key = ((0, 1), (2, 2))  # (z, tile_id) pairs, non-empty only, bottom first
    assert _effective_terrain_tag(terrain_tags, key) == 2


# --- Unverified capability guard --------------------------------------------


def test_cut_flash_dive_excluded_from_verified_capabilities():
    assert Capability.CUT not in VERIFIED_CAPABILITIES
    assert Capability.FLASH not in VERIFIED_CAPABILITIES
    assert Capability.DIVE not in VERIFIED_CAPABILITIES


@requires_corpus
def test_deriving_cut_raises():
    with pytest.raises(UnverifiedCapabilityError):
        build_capability_map(33, capabilities=frozenset({Capability.CUT}))


@requires_corpus
def test_deriving_flash_and_dive_also_raises():
    with pytest.raises(UnverifiedCapabilityError):
        build_capability_map(33, capabilities=frozenset({Capability.FLASH}))
    with pytest.raises(UnverifiedCapabilityError):
        build_capability_map(33, capabilities=frozenset({Capability.DIVE}))


@requires_corpus
def test_mixed_verified_and_unverified_still_raises():
    with pytest.raises(UnverifiedCapabilityError):
        build_capability_map(
            33, capabilities=frozenset({Capability.ROCK_SMASH, Capability.CUT})
        )


# --- CapabilityMap API --------------------------------------------------------


def test_capability_map_query_methods():
    obstacle = Obstacle(
        cell=(3, 4), capability=Capability.ROCK_SMASH, source="event",
        detail="1:Rock", event_id=1,
    )
    cmap = CapabilityMap(map_id=1, obstacles={(3, 4): obstacle})
    assert cmap.capability_at((3, 4)) is Capability.ROCK_SMASH
    assert cmap.capability_at((0, 0)) is None
    assert cmap.cells_for(Capability.ROCK_SMASH) == {(3, 4)}
    assert cmap.cells_for(Capability.STRENGTH) == set()
    assert cmap.capabilities_present() == {Capability.ROCK_SMASH}


# --- Golden tests against the real corpus ------------------------------------


@requires_corpus
def test_golden_map33_rock_smash_events():
    cmap = build_capability_map(33)
    rock_events = {
        o.event_id for o in cmap.obstacles.values() if o.capability is Capability.ROCK_SMASH
    }
    assert rock_events == {29, 36, 38, 40, 42, 44}


@requires_corpus
def test_golden_map35_rock_smash_events_and_cells():
    cmap = build_capability_map(35)
    rock_obstacles = {
        o.event_id: o.cell for o in cmap.obstacles.values() if o.capability is Capability.ROCK_SMASH
    }
    assert rock_obstacles == {
        14: (20, 28),
        15: (21, 29),
        16: (22, 28),
        17: (19, 29),
        18: (21, 28),
    }


@requires_corpus
def test_golden_map96_strength_boulders_via_code_111():
    """Regression case for the code-111 trap: map 96's three boulders gate
    Strength purely through code-111 branches with no "Kernel." prefix."""
    cmap = build_capability_map(96)
    strength_obstacles = {
        o.event_id: o.cell for o in cmap.obstacles.values() if o.capability is Capability.STRENGTH
    }
    assert strength_obstacles == {
        8: (5, 6),
        9: (6, 5),
        10: (7, 5),
    }


@requires_corpus
def test_corpus_wide_rock_smash_and_strength_counts():
    """Whole-corpus counts, matched against the corrected census (map 96's
    code-111 boulders were the original undercount's cause)."""
    expected_rock_smash = {32: 3, 33: 6, 35: 5, 66: 15, 107: 6, 118: 30}
    expected_strength = {
        7: 1, 19: 3, 31: 2, 69: 7, 76: 1, 84: 11, 94: 1, 96: 3,
        137: 9, 150: 3, 184: 6, 190: 15, 192: 19, 212: 1, 216: 1,
    }

    rock_counts: dict[int, int] = {}
    strength_counts: dict[int, int] = {}
    for path in sorted(MAPS_DIR.glob("Map*.json")):
        map_id = int(path.stem[3:])
        map_json = json.loads(path.read_text(encoding="utf-8"))
        for obstacle in _find_event_obstacles(map_json):
            if obstacle.capability is Capability.ROCK_SMASH:
                rock_counts[map_id] = rock_counts.get(map_id, 0) + 1
            elif obstacle.capability is Capability.STRENGTH:
                strength_counts[map_id] = strength_counts.get(map_id, 0) + 1

    assert rock_counts == expected_rock_smash
    assert strength_counts == expected_strength
