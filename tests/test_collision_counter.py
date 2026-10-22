"""Tests for `traversal.collision.build_counter_grid` (`Game_Map#counter?`
port, `reference/scripts_dump/025__Game_Map_v17.rb:343-354`).

Real-corpus test is gated on `output/uranium-build/` existing, matching the
pattern in `tests/test_traversal_map037_golden.py` / `tests/test_heal_locations.py`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.traversal.collision import (
    TilesetArrays,
    build_counter_grid,
    load_map_json,
    load_tileset_arrays,
)
from rpg2gba.tileset_converter.layout import TileGrid

MAPS_DIR = Path("output/uranium-build/maps")
TILESETS_JSON = Path("output/uranium-build/tilesets.json")
MAP068 = MAPS_DIR / "Map068.json"


def _grid(xsize: int, ysize: int, layers: list[list[list[int]]]) -> TileGrid:
    """Build a `TileGrid` from `layers[z][y][x]` (z ascending, bottom first)."""
    zsize = len(layers)
    data = [0] * (xsize * ysize * zsize)
    for z, plane in enumerate(layers):
        for y, row in enumerate(plane):
            for x, tid in enumerate(row):
                data[z * ysize * xsize + y * xsize + x] = tid
    return TileGrid(xsize, ysize, zsize, data)


def test_synthetic_top_layer_counter_wins() -> None:
    """Tile id 2 on the top layer (z=2) has the counter bit; the scan finds
    it before ever looking at the lower layers."""
    grid = _grid(
        1,
        1,
        [
            [[1]],  # z=0
            [[0]],  # z=1
            [[2]],  # z=2 (top)
        ],
    )
    # passages index 1: plain block bit only; index 2: counter bit.
    arrays = TilesetArrays(passages=[0, 0x10, 0x80], priorities=[0, 0, 0], terrain_tags=[0, 0, 0])
    counters = build_counter_grid(grid, arrays)
    assert counters[(0, 0)] is True


def test_synthetic_falls_through_to_lower_layer() -> None:
    """Top layer's tile has no counter bit; the scan falls through to a
    lower layer that does."""
    grid = _grid(
        1,
        1,
        [
            [[2]],  # z=0: counter tile
            [[0]],  # z=1
            [[1]],  # z=2 (top): not a counter
        ],
    )
    arrays = TilesetArrays(passages=[0, 0x00, 0x80], priorities=[0, 0, 0], terrain_tags=[0, 0, 0])
    counters = build_counter_grid(grid, arrays)
    assert counters[(0, 0)] is True


def test_synthetic_no_counter_anywhere_in_column() -> None:
    grid = _grid(1, 1, [[[1]], [[0]], [[0]]])
    arrays = TilesetArrays(passages=[0, 0x10], priorities=[0, 0], terrain_tags=[0, 0])
    counters = build_counter_grid(grid, arrays)
    assert counters[(0, 0)] is False


def test_synthetic_empty_tile_id_zero_is_consulted_like_any_other() -> None:
    """Unlike `column_blocked`, empty (id-0) tiles are NOT skipped — if
    passages[0] itself carries the counter bit, an all-empty column counts."""
    grid = _grid(1, 1, [[[0]], [[0]], [[0]]])
    arrays = TilesetArrays(passages=[0x80], priorities=[0], terrain_tags=[0])
    counters = build_counter_grid(grid, arrays)
    assert counters[(0, 0)] is True


def test_synthetic_out_of_range_tile_id_fails_loud() -> None:
    grid = _grid(1, 1, [[[5]], [[0]], [[0]]])
    arrays = TilesetArrays(passages=[0], priorities=[0], terrain_tags=[0])
    with pytest.raises(KeyError):
        build_counter_grid(grid, arrays)


def test_out_of_atlas_static_id_is_masked_like_the_layout() -> None:
    """A static id past the tileset image (CH09's gatehouse, map 1) is drawn as
    nothing by RMXP and masked by the layout converter; the offline grids mask
    it too instead of failing on the passage lookup."""
    from rpg2gba.traversal.collision import build_blocked_grid

    passages = [0] * 392  # 384 autotile ids + one row of 8 static tiles
    passages[384] = 0x80  # a counter tile under the stale id
    arrays = TilesetArrays(passages=passages, priorities=[0] * 392, terrain_tags=[0] * 392)
    grid = _grid(1, 1, [[[384]], [[0]], [[3453]]])
    assert build_counter_grid(grid, arrays)[(0, 0)] is True  # stale top layer skipped
    assert build_blocked_grid(grid, arrays)[(0, 0)] is False


@pytest.mark.skipif(
    not MAP068.is_file() or not TILESETS_JSON.is_file(),
    reason="requires the decoded corpus under output/uranium-build/ (run the pipeline first)",
)
def test_real_map068_counter_rows() -> None:
    """Map068 (Kevlar Town Pokémon Center): rows 9-14 contain exactly three
    counter cells, spanning behind/beside the nurse — verified against the
    real passages array (2026-09-12): (6,12), (7,12), (8,12)."""
    from rpg2gba.traversal.collision import build_tile_grid

    map_json = load_map_json(68, MAPS_DIR)
    grid = build_tile_grid(map_json)
    arrays = load_tileset_arrays(map_json["tileset_id"], TILESETS_JSON)
    counters = build_counter_grid(grid, arrays)
    found = {c for c, is_counter in counters.items() if is_counter and 9 <= c[1] <= 14}
    assert found == {(6, 12), (7, 12), (8, 12)}
