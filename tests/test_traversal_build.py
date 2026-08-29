"""End-to-end `build_map_graph` smoke tests against the real decoded corpus
(Map037 / tileset 32). Skips if the corpus isn't present.

Complements test_traversal_map037_golden.py (which reimplements the doc's
plain-BFS methodology directly against `layout.column_blocked`) by checking
that `build_map_graph` — the actual library entry point — produces the same
stair/warp facts and a graph that plans a route to the cave exit at all
(round-trip: build -> query -> sane result, CLAUDE.md §4.6).
"""
from __future__ import annotations

import pytest

from rpg2gba.tileset_converter.stairs import StairSide
from rpg2gba.traversal import build_map_graph
from rpg2gba.traversal.collision import DEFAULT_MAPS_DIR, DEFAULT_TILESETS_JSON

pytestmark = pytest.mark.skipif(
    not (DEFAULT_MAPS_DIR / "Map037.json").is_file() or not DEFAULT_TILESETS_JSON.is_file(),
    reason="requires the decoded corpus under output/uranium-build/ (run the pipeline first)",
)


@pytest.fixture(scope="module")
def map037():
    return build_map_graph(37)


def test_dimensions_and_tileset(map037):
    assert (map037.width, map037.height) == (34, 30)
    assert map037.tileset_id == 32


def test_stair_cells_match_the_detector(map037):
    assert map037.stair_sides == {
        (11, 9): StairSide.LEFT,
        (11, 10): StairSide.LEFT,
        (20, 9): StairSide.RIGHT,
        (20, 10): StairSide.RIGHT,
    }


def test_warp_exits_include_south_entrance_and_cave_exit(map037):
    assert (16, 27) in map037.warp_exits  # -> Map036 (south)
    assert (16, 5) in map037.warp_exits  # -> Map040 (Nowtoch, north)
    south = map037.warp_exits[(16, 27)][0]
    assert south.dest_map == 36
    north = map037.warp_exits[(16, 5)][0]
    assert north.dest_map == 40


def test_elevation_is_explicitly_unmodelled(map037):
    assert map037.elevation_modelled is False
    assert "not modelled" in map037.elevation_note


def test_stair_cells_are_walkable_via_the_built_graph(map037):
    for cell in map037.stair_sides:
        assert map037.is_walkable(cell) is True


def test_cave_exit_reachable_via_the_built_graph_including_diagonal_shortcuts(map037):
    """With the real diagonal-stair model (not the doc's plain-BFS
    simplification — see the golden test), the cave exit must still be
    reachable at all from the entry; the diagonal model can only ever be
    equal-or-shorter than the plain model, never longer."""
    path = map037.shortest_path((16, 26), (16, 5))
    assert path is not None
    assert path[0] == (16, 26)
    assert path[-1] == (16, 5)
    # Diagonal shortcuts can only shorten the plain-BFS distance (35), never
    # lengthen it.
    assert len(path) - 1 <= 35


def test_gift_and_trainer_approach_unaffected_by_stair_model_choice(map037):
    """These two never need a stair press in either model — the graph's
    diagonal shortcuts must not change their distance from the plain-BFS
    golden numbers (23 / 26)."""
    trainer_path = map037.shortest_path((16, 26), (23, 10))
    gift_path = map037.shortest_path((16, 26), (9, 7))
    assert len(trainer_path) - 1 == 23
    assert len(gift_path) - 1 == 26
