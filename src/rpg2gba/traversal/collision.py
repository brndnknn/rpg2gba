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

from rpg2gba.tileset_converter.layout import (
    RMXP_LAYERS,
    TileGrid,
    column_blocked,
    column_key,
    mask_out_of_atlas,
)

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


def _masked(grid: TileGrid, arrays: TilesetArrays) -> TileGrid:
    """`layout.mask_out_of_atlas` against this tileset's last static id, so the
    offline graph sees the same grid the ROM layout was built from: stale ids
    past the tileset image are drawn as nothing by RMXP and masked by the layout
    converter (CH09's gatehouse, map 1, has 34). RMXP sizes `passages` from the
    image (384 autotile ids + 8 per row), so its last index is the atlas bound."""
    masked, cells = mask_out_of_atlas(grid, len(arrays.passages) - 1)
    if cells:
        logger.debug("masked %d out-of-atlas cell-layer(s)", len(cells))
    return masked


def build_blocked_grid(
    grid: TileGrid, arrays: TilesetArrays
) -> dict[tuple[int, int], bool]:
    """{(x, y): blocked} for every cell, via `layout.column_blocked` — no
    stair/ledge/warp overrides applied (those are the graph layer's job, not
    the raw collision layer's). Out-of-atlas ids are masked first (`_masked`)."""
    grid = _masked(grid, arrays)
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


# The RMXP passage byte's high bit ("*" in the RPG Maker editor's passage
# grid) marks a counter: a piece of furniture the player cannot stand on, but
# can interact *across* — the engine checks one tile further along the facing
# direction when the immediately-faced tile is a counter. See
# `Game_Player#front_map_x`/`front_map_y`+`check_event_trigger_touch`
# (`reference/scripts_dump/023__Game_Player_v17.rb:196-215,343-356`), which
# calls `Game_Map#counter?` (`reference/scripts_dump/025__Game_Map_v17.rb:343-354`).
COUNTER_PASSAGE_BIT = 0x80


def build_counter_grid(
    grid: TileGrid, arrays: TilesetArrays
) -> dict[tuple[int, int], bool]:
    """{(x, y): is-counter} for every cell — a faithful port of
    `Game_Map#counter?` (`reference/scripts_dump/025__Game_Map_v17.rb:343-354`):

        for i in [2, 1, 0]
          tile_id = data[x, y, i]
          if tile_id == nil
            return false
          elsif @passages[tile_id] && @passages[tile_id] & 0x80 == 0x80
            return true
          end
        end
        return false

    Layers are scanned top down (RMXP z-index 2, then 1, then 0 for the
    standard 3-layer map — `TileGrid.tile_at`'s z is ascending, bottom
    first, so this walks `z` from `grid.zsize - 1` down to `0`); the first
    layer whose tile's passage byte has the counter bit (`0x80`) set wins.
    The `tile_id == nil` branch is RMXP's out-of-bounds guard on `(x, y)`
    itself, not on the tile id — this function is only ever called with
    in-grid `(x, y)` (the caller's own `range(grid.ysize)`/`range(grid.xsize)`
    loop), so that branch never fires here and is not reproduced.

    Unlike `build_blocked_grid`'s `column_blocked` (which drops EMPTY tiles
    from the scan before considering them), this does NOT skip empty
    (id-0) tiles — `Game_Map#counter?` indexes `data[x, y, i]` and
    `@passages[tile_id]` directly with no empty-tile special case, so tile id
    0's own `passages[0]` entry is consulted exactly like any other id.

    Stale out-of-atlas ids are masked first (`_masked`, the layout converter's
    rule). Any other out-of-range tile id for `arrays.passages` fails loud
    (`KeyError`), mirroring `layout._passage_lookup`'s fail-loud convention for
    passage lookups (CLAUDE.md §4.3/§4.5) — a passage byte decides real
    interaction behavior, so a silent default here would be exactly the kind of
    "300 maps later" bug that convention exists to prevent.
    """
    grid = _masked(grid, arrays)
    counters: dict[tuple[int, int], bool] = {}
    for y in range(grid.ysize):
        for x in range(grid.xsize):
            is_counter = False
            for z in range(grid.zsize - 1, -1, -1):
                tile_id = grid.tile_at(x, y, z)
                if not 0 <= tile_id < len(arrays.passages):
                    raise KeyError(
                        f"tile_id {tile_id} at ({x},{y},z={z}) out of range for "
                        f"passages array (len {len(arrays.passages)})"
                    )
                if arrays.passages[tile_id] & COUNTER_PASSAGE_BIT:
                    is_counter = True
                    break
            counters[(x, y)] = is_counter
    return counters
