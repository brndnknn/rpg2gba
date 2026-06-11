"""Phase 5 §5.2 — Map layout converter.

ASSIGNMENT
==========
Objective
    Turn one Phase 3 `MapNNN.json` tile grid into a pokeemerald *layout*:
    `map.bin` blockdata + `border.bin` + a `layouts.json` entry.

The collapse (the heart of 5.2 — see Open Question Q1)
    RMXP gives 3 stacked tile layers (`tiles.zsize == 3`); a GBA metatile has
    only 2 internal layers. So for each (x, y) you must collapse the 3 RMXP tile
    ids into ONE pokeemerald metatile. First-pass default: topmost-non-empty
    layer wins (tile_id 0 = empty). Record what you dropped so Q1 can be revisited.

    The Phase 3 tile array is flat, row-major, layer-major:
        index(x, y, z) = z * (ysize * xsize) + y * xsize + x
    Use the `tile_at` helper below rather than recomputing the index inline.

Inputs
    MapNNN.json (dict; uses `tiles{xsize,ysize,zsize,data}`, `width`, `height`,
        `tileset_id`), the `TileMap` from 5.1, the map's `LAYOUT_*` name from
        map_constants.
Outputs
    output/uranium-build/porymap/layouts/<Name>/map.bin   (width*height u16, LE)
    output/uranium-build/porymap/layouts/<Name>/border.bin (Q5)
    an appended entry in   .../layouts/layouts.json

Constraints
    - Idempotent (CLAUDE.md §4.2): same input -> byte-identical .bin.
    - Fail loud: any tile that 5.1 can't resolve aborts THIS map with its ids.
    - len(map.bin) must equal width * height * 2 bytes.

Acceptance
    [ ] len(map.bin) == width * height * 2
    [ ] read blocks back -> every metatile id is one 5.1 emitted
    [ ] re-run -> byte-identical output
    [ ] golden test on a 2x2 synthetic map
"""
from __future__ import annotations

import logging
import struct
from dataclasses import dataclass, field
from pathlib import Path

from .tile_map import Metatile, TileMap

logger = logging.getLogger(__name__)

# RMXP layer count we expect from Phase 3 (E5: tiles kept flat, zsize == 3).
RMXP_LAYERS = 3
EMPTY_TILE = 0  # RMXP: 0 means "no tile on this layer"


@dataclass
class TileGrid:
    """The Phase 3 `tiles` block, with indexing that hides the flat layout."""

    xsize: int
    ysize: int
    zsize: int
    data: list[int]

    def tile_at(self, x: int, y: int, z: int) -> int:
        """Tile id at (x, y, layer z). index = z*ysize*xsize + y*xsize + x (E5)."""
        return self.data[z * (self.ysize * self.xsize) + y * self.xsize + x]

    def column(self, x: int, y: int) -> list[int]:
        """The `zsize` stacked tile ids at (x, y), bottom layer first."""
        return [self.tile_at(x, y, z) for z in range(self.zsize)]


@dataclass
class Layout:
    """A converted layout: the in-memory blockdata + the layouts.json metadata.
    Serialize with `write()`. `border` defaults are decided by Q5."""

    name: str  # e.g. "Uranium_Map001"
    layout_const: str  # e.g. "LAYOUT_URANIUM_MAP001"
    width: int
    height: int
    primary_tileset: str
    secondary_tileset: str
    blocks: list[int] = field(default_factory=list)  # width*height packed u16s
    border: list[int] = field(default_factory=list)  # 2x2 packed u16s (Q5)

    def to_layouts_entry(self, layouts_dir: Path) -> dict:
        """The dict appended to layouts.json (matches the fork's schema:
        id/name/width/height/primary_tileset/secondary_tileset/border_filepath/
        blockdata_filepath/layout_version)."""
        raise NotImplementedError("5.2: build the layouts.json entry for this layout")


def collapse_column(grid: TileGrid, x: int, y: int, tile_map: TileMap, tileset_id: int) -> Metatile:
    """Collapse the 3 stacked RMXP tiles at (x, y) into one pokeemerald Metatile (Q1).

    Q1 hybrid policy:
      1. if the (z0,z1,z2) stack has a composite override in tile_map -> use it;
      2. else topmost-non-empty: take the highest non-empty layer (tile_id != 0)
         and resolve via `tile_map.lookup(tileset_id, tile_id)`.
    If every layer is empty, decide a sensible floor (e.g. a void metatile) — but
    fail loud rather than silently emitting metatile 0 if that would hide a gap."""
    raise NotImplementedError("5.2: implement the Q1 hybrid 3-layer -> 1-metatile collapse")


def convert_layout(map_json: dict, tile_map: TileMap, *, name: str, layout_const: str) -> Layout:
    """Convert one Phase 3 map dict into a `Layout` (blockdata + metadata).

    Steps:
      1. build a TileGrid from map_json["tiles"]; assert zsize == RMXP_LAYERS.
      2. choice = tile_map.tileset_for(map_json["tileset_id"]).
      3. for y in range(height): for x in range(width):
             blocks.append(collapse_column(...).to_block())
      4. fill border (Q5).
    """
    raise NotImplementedError("5.2: TileGrid -> collapsed blocks -> Layout")


def write_blockdata(blocks: list[int], path: Path) -> None:
    """Write packed u16 blocks to `path` as little-endian binary (idempotent).

    Hint: struct.pack(f"<{len(blocks)}H", *blocks); mkdir parents first."""
    raise NotImplementedError("5.2: serialize blocks to little-endian u16 .bin")


def read_blockdata(path: Path) -> list[int]:
    """Inverse of write_blockdata — for the round-trip test."""
    raw = path.read_bytes()
    return list(struct.unpack(f"<{len(raw) // 2}H", raw))
