"""Phase 5 §5.2 — Map layout converter.

ASSIGNMENT
==========
Objective
    Turn one Phase 3 `MapNNN.json` tile grid into a pokeemerald *layout*:
    `map.bin` blockdata + `border.bin` + a `layouts.json` entry.

The collapse (the heart of 5.2 — see Open Question Q1)
    RMXP gives 3 stacked tile layers (`tiles.zsize == 3`); a GBA metatile has
    only 2 internal layers. So for each (x, y) you must collapse the 3 RMXP tile
    ids into ONE pokeemerald metatile. Pathfinder policy (Q1 hybrid, v1):
    topmost-non-empty layer supplies the *visual* metatile; collision comes from
    the combined source-passage rule (see `_cell_blocked`), so the two can differ
    (an invisible-wall cell — passable-looking floor under a blocking treetop — is
    correct, not a bug). Composite-stack overrides are deferred (the v1 `TileMap`
    carries no `stacks` map).

    The Phase 3 tile array is flat, row-major, layer-major:
        index(x, y, z) = z * (ysize * xsize) + y * xsize + x
    Use the `tile_at` helper below rather than recomputing the index inline.

Inputs
    MapNNN.json (dict; uses `tiles{xsize,ysize,zsize,data}`, `width`, `height`,
        `tileset_id`), the `TileMap` from 5.1, the map's `LAYOUT_*` name from
        map_constants, and (S5) the warp-source coords to force walkable.
Outputs
    output/uranium-build/porymap/layouts/<Name>/map.bin   (width*height u16, LE)
    output/uranium-build/porymap/layouts/<Name>/border.bin (Q5)
    an appended entry in   .../layouts/layouts.json

Constraints
    - Idempotent (CLAUDE.md §4.2): same input -> byte-identical .bin.
    - Fail loud: any tile that 5.1 can't resolve aborts THIS map with its ids.
    - len(map.bin) must equal width * height * 2 bytes.
"""
from __future__ import annotations

import json
import logging
import struct
from dataclasses import dataclass, field
from pathlib import Path

from .tile_map import (
    BLOCKED_COLLISION,
    BLOCKED_ELEVATION,
    PASSABLE_COLLISION,
    PASSABLE_ELEVATION,
    PASSAGE_BLOCK_MASK,
    Metatile,
    TileMap,
)

logger = logging.getLogger(__name__)

# RMXP layer count we expect from Phase 3 (E5: tiles kept flat, zsize == 3).
RMXP_LAYERS = 3
EMPTY_TILE = 0  # RMXP: 0 means "no tile on this layer"

# Standard Emerald border is 2x2 metatiles (Q5) = 4 blocks = 8 bytes.
BORDER_BLOCKS = 4

# layouts.json paths are fork-relative; the bytes physically stage under
# output/uranium-build/porymap/layouts/<Name>/ but the entry records the
# destination the Phase-7 assembly copies them to (PHASE5_PLAN: output never
# goes into the fork; Phase 7 copies).
FORK_LAYOUTS_BASE = "data/layouts"

# A map that is mostly void usually means a transposed/misread grid, not real
# geometry — warn (not a hard fail; the boot makes it obvious either way).
_VOID_RATIO_WARN = 0.60


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

    `name` is the PascalCase base (and the staging/dir name), e.g.
    "MokiTown_PlayersHouse_2F"; the layouts.json `name` field is `name + "_Layout"`
    (fork convention). `layout_const` is the `LAYOUT_*` id (both minted by S4)."""

    name: str  # e.g. "MokiTown_PlayersHouse_2F"
    layout_const: str  # e.g. "LAYOUT_MOKI_TOWN_PLAYERS_HOUSE_2F"
    width: int
    height: int
    primary_tileset: str
    secondary_tileset: str
    blocks: list[int] = field(default_factory=list)  # width*height packed u16s
    border: list[int] = field(default_factory=list)  # 2x2 packed u16s (Q5)

    def to_layouts_entry(self, layouts_dir: Path | None = None) -> dict:
        """The dict appended to layouts.json (matches the fork's schema).

        `border_filepath`/`blockdata_filepath` are written **fork-relative**
        (`data/layouts/<name>/...`), the Phase-7 destination — `layouts_dir` (the
        staging path) is intentionally unused for them."""
        base = f"{FORK_LAYOUTS_BASE}/{self.name}"
        return {
            "id": self.layout_const,
            "name": f"{self.name}_Layout",
            "width": self.width,
            "height": self.height,
            "primary_tileset": self.primary_tileset,
            "secondary_tileset": self.secondary_tileset,
            "border_filepath": f"{base}/border.bin",
            "blockdata_filepath": f"{base}/map.bin",
            "layout_version": "emerald",
        }

    def write(self, staging_dir: Path) -> None:
        """Serialize map.bin + border.bin under `staging_dir/layouts/<name>/`."""
        out = staging_dir / "layouts" / self.name
        write_blockdata(self.blocks, out / "map.bin")
        write_blockdata(self.border, out / "border.bin")


def _cell_blocked(grid: TileGrid, x: int, y: int, tile_map: TileMap, tileset_id: int) -> bool:
    """RMXP multi-layer passability for one cell (validated rule, mirrors
    `scripts/pathfinder_collision_preview.cell_blocked`).

    Scan layers top->bottom: the first non-empty tile that blocks
    (`passage & 0x0F != 0`) -> blocked; a non-empty tile drawn at priority 0
    (normal layer) that does *not* block -> passable (stop, ignore tiles beneath);
    a passable tile at priority > 0 (drawn over the player, e.g. a treetop) does
    not decide — keep scanning down to the trunk. An all-empty column is void
    (blocked)."""
    seen_tile = False
    for z in range(grid.zsize - 1, -1, -1):  # top layer down
        tid = grid.tile_at(x, y, z)
        if tid == EMPTY_TILE:
            continue
        seen_tile = True
        if (tile_map.passage(tileset_id, tid) & PASSAGE_BLOCK_MASK) != 0:
            return True
        if tile_map.priority(tileset_id, tid) == 0:
            return False
    return not seen_tile  # all-empty = void = blocked


def collapse_column(grid: TileGrid, x: int, y: int, tile_map: TileMap, tileset_id: int) -> Metatile:
    """Collapse the 3 stacked RMXP tiles at (x, y) into one pokeemerald Metatile (Q1).

    v1 policy: the *visual* metatile is the topmost non-empty layer resolved via
    `tile_map.lookup`; the *collision/elevation* come from the combined
    source-passage rule (`_cell_blocked`) — these can differ. An all-empty column
    returns the tileset's void metatile. Fails loud (via `lookup`) on an unmapped
    tile rather than emitting metatile 0."""
    column = grid.column(x, y)  # [z0, z1, z2], bottom -> top
    visual: Metatile | None = None
    for tid in reversed(column):  # top layer first
        if tid != EMPTY_TILE:
            visual = tile_map.lookup(tileset_id, tid)
            break
    if visual is None:
        return tile_map.void(tileset_id)

    if _cell_blocked(grid, x, y, tile_map, tileset_id):
        return Metatile(visual.metatile_id, BLOCKED_COLLISION, BLOCKED_ELEVATION)
    return Metatile(visual.metatile_id, PASSABLE_COLLISION, PASSABLE_ELEVATION)


def convert_layout(
    map_json: dict,
    tile_map: TileMap,
    *,
    name: str,
    layout_const: str,
    warp_overrides: set[tuple[int, int]] | None = None,
) -> Layout:
    """Convert one Phase 3 map dict into a `Layout` (blockdata + metadata).

    `warp_overrides` (S5, from the S1 warp trace) are the warp/door/stairs cells.
    Each is overwritten with the tileset's warp metatile (`tile_map.warp`) — a
    step-on MB_NON_ANIMATED_DOOR at collision 0. This is REQUIRED for the warp to
    work, not just cosmetic: a pokeemerald warp_event is inert unless the metatile
    under it carries a warp metatile-behavior (the generic passable-floor bucket is
    MB_NORMAL, so the player walks onto the door tile and nothing happens). Forcing
    collision 0 also keeps the tile steppable (door tiles read BLOCKED from their
    source passage)."""
    overrides = warp_overrides or set()

    tiles = map_json["tiles"]
    grid = TileGrid(tiles["xsize"], tiles["ysize"], tiles["zsize"], tiles["data"])
    if grid.zsize != RMXP_LAYERS:
        raise ValueError(
            f"layout {name}: expected {RMXP_LAYERS} RMXP layers, got zsize={grid.zsize}"
        )
    width, height = map_json["width"], map_json["height"]
    if (width, height) != (grid.xsize, grid.ysize):
        raise ValueError(
            f"layout {name}: width/height {width}x{height} != tile grid "
            f"{grid.xsize}x{grid.ysize}"
        )

    tileset_id = map_json["tileset_id"]
    choice = tile_map.tileset_for(tileset_id)

    blocks: list[int] = []
    void_count = 0
    for y in range(height):  # row-major: y outer, x inner
        for x in range(width):
            if all(t == EMPTY_TILE for t in grid.column(x, y)):
                void_count += 1
            metatile = collapse_column(grid, x, y, tile_map, tileset_id)
            if (x, y) in overrides:
                metatile = tile_map.warp(tileset_id)
            blocks.append(metatile.to_block())

    if len(blocks) != width * height:
        raise AssertionError(
            f"layout {name}: emitted {len(blocks)} blocks, expected {width * height}"
        )

    ratio = void_count / (width * height) if width * height else 0.0
    logger.info(
        "layout %s: %d/%d void cells (%.0f%%)", name, void_count, width * height, 100 * ratio
    )
    if ratio > _VOID_RATIO_WARN:
        logger.warning(
            "layout %s: %.0f%% void — possible wrong index order or misread grid",
            name,
            100 * ratio,
        )

    void_block = tile_map.void(tileset_id).to_block()
    border = [void_block] * BORDER_BLOCKS

    return Layout(
        name=name,
        layout_const=layout_const,
        width=width,
        height=height,
        primary_tileset=choice.primary,
        secondary_tileset=choice.secondary,
        blocks=blocks,
        border=border,
    )


def append_layouts(entries: list[dict], path: Path) -> None:
    """Idempotent upsert of `entries` into a layouts.json at `path` (keyed by id,
    sorted by id for stable diffs). Seeds the fork's top-level shape if absent."""
    if path.exists():
        doc = json.loads(path.read_text(encoding="utf-8"))
    else:
        doc = {"layouts_table_label": "gMapLayouts", "layouts": []}
    by_id = {e["id"]: e for e in doc.get("layouts", [])}
    for entry in entries:
        by_id[entry["id"]] = entry
    doc["layouts"] = sorted(by_id.values(), key=lambda e: e["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def write_blockdata(blocks: list[int], path: Path) -> None:
    """Write packed u16 blocks to `path` as little-endian binary (idempotent)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack(f"<{len(blocks)}H", *blocks))


def read_blockdata(path: Path) -> list[int]:
    """Inverse of write_blockdata — for the round-trip test."""
    raw = path.read_bytes()
    return list(struct.unpack(f"<{len(raw) // 2}H", raw))
