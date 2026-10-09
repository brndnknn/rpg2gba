"""The ROM build's palette quantizer — the one definition of how shipped tilesets quantize.

``build_slice_tilesets`` emits with :func:`make_rom_quantizer`; the map viewer's
``ROM_STOCK_*`` configuration and the viewer↔ROM oracle read the same constants, so
changing the ROM's quantization here moves all three together (tileset plan open
item 6).

History: the family packer with stock median cut until 2026-10-06; since then Ward
reduction (P1) plus the P2 shared rock/green palettes, operator-approved in the viewer
2026-10-05 (``reference/chapters/06-tileset-plan.md``).  The shared palettes are
frozen constants (plan open item 5): later chapters add palettes, they do not refit
these, so shipped chapters keep their colours.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from functools import partial

from .quantize import FamilyParams, QuantizeResult, build_quantized_tileset_family
from .shared_palettes import make_shared_quantizer

ROM_FAMILY_PARAMS: FamilyParams = FamilyParams(reduction="ward")
ROM_SHARED_PALETTES: bool = True
# Game-wide near-duplicate tile merge (graphics/tile_merge.py, K 16 rock/green / 4 other)
# + lossless metatile dedup, applied by build_slice_tilesets to every metatile of every
# map. Operator-approved 2026-10-06 for all maps, to put Kevlar (31) +
# Route 2 (35) on one shared tileset so their seam is a real connection.
ROM_TILE_MERGE: bool = True


def tile_merge_exempt(map_ids: Iterable[int]) -> bool:
    """A tileset holding a split piece (`rpg2gba.map_split`) never gets the tile
    merge: splitting a map is how it fits WITHOUT the merge's visual loss
    (operator decision 2026-10-09, reference/guides/map_split_stage.md)."""
    from rpg2gba.map_split.ids import is_piece

    return any(is_piece(m) for m in map_ids)


def rom_tile_merge_for(map_ids: Iterable[int]) -> bool:
    """Whether the ROM applies the tile merge to a tileset holding `map_ids`."""
    return ROM_TILE_MERGE and not tile_merge_exempt(map_ids)


def make_rom_quantizer() -> Callable[..., QuantizeResult]:
    """A fresh ``quantizer=`` hook for ``emit_tileset`` matching the ROM build.

    Fresh per call because the shared wrapper records per-call ``.info``."""
    base = partial(build_quantized_tileset_family, params=ROM_FAMILY_PARAMS)
    if ROM_SHARED_PALETTES:
        return make_shared_quantizer(base, family_params=ROM_FAMILY_PARAMS)
    return base
