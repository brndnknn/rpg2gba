"""Per-map collision grid — a thin loader around the validated Phase 5 rule.

Reuses `tileset_converter.layout.column_key`/`column_blocked` (the one place
the RMXP multi-layer passability rule lives, CLAUDE.md §4.3) directly against
the raw `passages`/`priorities`/`terrain_tags` arrays from
`output/uranium-build/tilesets.json` — the same shape
`scripts/compare_collision.py` reads, minus that script's `TileMap` shim
(`column_blocked` takes the raw arrays already, so no shim is needed here).

This module does not reimplement any passability rule; it only wires decoded
JSON on disk to the existing `column_blocked` call.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from rpg2gba.tileset_converter.layout import RMXP_LAYERS, TileGrid, column_blocked, column_key

logger = logging.getLogger(__name__)

DEFAULT_MAPS_DIR = Path("output/uranium-build/maps")
DEFAULT_TILESETS_JSON = Path("output/uranium-build/tilesets.json")


@dataclass(frozen=True)
class TilesetArrays:
    """Raw per-tile-id arrays for one tileset, straight from tilesets.json."""

    passages: list[int]
    priorities: list[int]
    terrain_tags: list[int]


def load_tileset_arrays(tileset_id: int, path: Path = DEFAULT_TILESETS_JSON) -> TilesetArrays:
    """Load tileset `tileset_id`'s passages/priorities/terrain_tags arrays.

    Fails loud (KeyError) if the tileset id isn't present — matches
    `terrain_tags.load_terrain_tags_json`'s fail-loud convention."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    entry = raw.get(str(tileset_id))
    if entry is None:
        raise KeyError(f"tileset {tileset_id} absent from {path}")
    return TilesetArrays(
        passages=entry["passages"],
        priorities=entry["priorities"],
        terrain_tags=entry["terrain_tags"],
    )


def load_map_json(map_id: int, maps_dir: Path = DEFAULT_MAPS_DIR) -> dict:
    """Load `Map{map_id:03d}.json` from *maps_dir*. Fails loud if missing."""
    path = maps_dir / f"Map{map_id:03d}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def build_tile_grid(map_json: dict) -> TileGrid:
    """The `TileGrid` for one decoded map (fails loud if not the expected 3
    RMXP layers — mirrors `layout.convert_layout`'s own check)."""
    tiles = map_json["tiles"]
    grid = TileGrid(tiles["xsize"], tiles["ysize"], tiles["zsize"], tiles["data"])
    if grid.zsize != RMXP_LAYERS:
        raise ValueError(f"expected {RMXP_LAYERS} RMXP layers, got zsize={grid.zsize}")
    width, height = map_json["width"], map_json["height"]
    if (width, height) != (grid.xsize, grid.ysize):
        raise ValueError(
            f"width/height {width}x{height} != tile grid {grid.xsize}x{grid.ysize}"
        )
    return grid


def build_blocked_grid(
    grid: TileGrid, arrays: TilesetArrays
) -> dict[tuple[int, int], bool]:
    """{(x, y): blocked} for every cell, via `layout.column_blocked` — no
    stair/ledge/warp overrides applied (those are the graph layer's job, not
    the raw collision layer's)."""
    blocked: dict[tuple[int, int], bool] = {}
    for y in range(grid.ysize):
        for x in range(grid.xsize):
            key = column_key(grid, x, y)
            blocked[(x, y)] = column_blocked(
                key,
                passages=arrays.passages,
                priorities=arrays.priorities,
                terrain_tags=arrays.terrain_tags,
            )
    return blocked
