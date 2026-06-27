"""Image pipeline step 3 — Uranium tile -> GBA-native 16x16 tile.

Render any Uranium `tile_id` to a 16x16 RGBA image (the GBA metatile pixel
footprint), the unit the quantizer/packer (step 4) will consume:

  - id == 0                : empty marker -> transparent (the layout collapse,
                             not this module, decides empty columns; we just
                             return blank so an autotile-over-floor cell composes).
  - 48 <= id < 384         : autotile -> flatten the baked variant to 32x32
                             (autotile.py), then /2. An empty slot -> transparent.
  - id >= 384              : static tile -> crop 32x32 from the tileset atlas
                             (`bltSmallRegularTile`: ((id-384)%8, (id-384)//8)),
                             then /2.

The /2 is the validated lossless downscale (Uranium art is a 2x nearest upscale;
`reference/graphics_conversion_notes.md`): one pixel per aligned 2x2 block,
top-left phase — identical to `scripts/downscale_compare.py::downscale_2x`.

Fail loud (CLAUDE.md §4.5): a static id outside the atlas, or a malformed
template, aborts with the id — never a silent blank substitute (an *empty
autotile slot* is the one legitimate blank, and is logged).
"""
from __future__ import annotations

import logging

from PIL import Image

from .autotile import flatten_autotile
from .sources import (
    AUTOTILE_BASE,
    RMXP_TILE_PX,
    STATIC_BASE,
    TILESET_COLUMNS,
    TilesetSources,
)

logger = logging.getLogger(__name__)

NATIVE_TILE_PX = RMXP_TILE_PX // 2  # 16 -> one GBA metatile footprint
_TRANSPARENT = (0, 0, 0, 0)


def downscale_2x(img: Image.Image) -> Image.Image:
    """One pixel per aligned 2x2 block (top-left phase). Lossless on 2x-upscaled
    art; matches scripts/downscale_compare.py::downscale_2x (`a[0::2, 0::2]`)."""
    img = img.convert("RGBA")
    w, h = img.size
    src = img.load()
    out = Image.new("RGBA", (w // 2, h // 2))
    dst = out.load()
    for y in range(h // 2):
        for x in range(w // 2):
            dst[x, y] = src[2 * x, 2 * y]
    return out


class TileRasterizer:
    """Renders Uranium tile ids of one tileset to 16x16 GBA-native RGBA tiles.

    Holds the loaded source images and a per-tile-id cache, so rendering is
    idempotent (same id -> identical image) and the heavy PNGs open once."""

    def __init__(self, sources: TilesetSources) -> None:
        self._sources = sources
        self._tileset: Image.Image | None = None
        self._templates: dict[int, Image.Image | None] = {}  # slot -> template
        self._cache: dict[int, Image.Image] = {}

    # --- lazy source loaders ------------------------------------------------

    def _tileset_img(self) -> Image.Image:
        if self._tileset is None:
            self._tileset = Image.open(self._sources.tileset_png).convert("RGBA")
        return self._tileset

    def _template_img(self, slot: int) -> Image.Image | None:
        if slot not in self._templates:
            path = self._sources.autotiles[slot]
            self._templates[slot] = (
                Image.open(path).convert("RGBA") if path is not None else None
            )
        return self._templates[slot]

    def max_static_tile_id(self) -> int:
        """Maximum valid static tile_id given the loaded atlas height."""
        atlas = self._tileset_img()
        rows = atlas.height // RMXP_TILE_PX
        return STATIC_BASE + rows * TILESET_COLUMNS - 1

    # --- rendering ----------------------------------------------------------

    def render(self, tile_id: int) -> Image.Image:
        """Render one tile_id to a 16x16 RGBA tile (cached, idempotent)."""
        if tile_id in self._cache:
            return self._cache[tile_id]
        tile = self._render_uncached(tile_id)
        if tile.size != (NATIVE_TILE_PX, NATIVE_TILE_PX):
            raise AssertionError(
                f"tile {tile_id}: rendered {tile.size}, expected "
                f"{(NATIVE_TILE_PX, NATIVE_TILE_PX)}"
            )
        self._cache[tile_id] = tile
        return tile

    def _render_uncached(self, tile_id: int) -> Image.Image:
        if tile_id == 0:
            return Image.new("RGBA", (NATIVE_TILE_PX, NATIVE_TILE_PX), _TRANSPARENT)
        if tile_id < 0:
            raise ValueError(f"negative tile_id {tile_id}")
        if tile_id < STATIC_BASE:
            return self._render_autotile(tile_id)
        return self._render_static(tile_id)

    def _render_static(self, tile_id: int) -> Image.Image:
        idx = tile_id - STATIC_BASE
        col, row = idx % TILESET_COLUMNS, idx // TILESET_COLUMNS
        x, y = col * RMXP_TILE_PX, row * RMXP_TILE_PX
        atlas = self._tileset_img()
        if x + RMXP_TILE_PX > atlas.width or y + RMXP_TILE_PX > atlas.height:
            raise ValueError(
                f"static tile {tile_id} (atlas cell {col},{row}) is outside "
                f"{self._sources.tileset_png.name} ({atlas.width}x{atlas.height})"
            )
        cell = atlas.crop((x, y, x + RMXP_TILE_PX, y + RMXP_TILE_PX))
        return downscale_2x(cell)

    def _render_autotile(self, tile_id: int) -> Image.Image:
        slot = tile_id // AUTOTILE_BASE - 1
        variant = tile_id % AUTOTILE_BASE
        template = self._template_img(slot)
        if template is None:
            # Legitimate: a cell referencing an unused autotile slot draws nothing
            # (e.g. Map048's base-336 decorative cells over real floor).
            logger.debug(
                "tile %d -> empty autotile slot %d (transparent)", tile_id, slot
            )
            return Image.new("RGBA", (NATIVE_TILE_PX, NATIVE_TILE_PX), _TRANSPARENT)
        flat = flatten_autotile(template, variant)
        return downscale_2x(flat)
