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

from collections.abc import Callable
from functools import partial

from .quantize import FamilyParams, QuantizeResult, build_quantized_tileset_family
from .shared_palettes import make_shared_quantizer

ROM_FAMILY_PARAMS: FamilyParams = FamilyParams(reduction="ward")
ROM_SHARED_PALETTES: bool = True
# Game-wide near-duplicate tile merge (graphics/tile_merge.py, K 16 rock/green / 4 other)
# + lossless metatile merge. Viewer-preview only until the operator's eye check; the ROM
# build does not apply it while this is False.
ROM_TILE_MERGE: bool = False


def make_rom_quantizer() -> Callable[..., QuantizeResult]:
    """A fresh ``quantizer=`` hook for ``emit_tileset`` matching the ROM build.

    Fresh per call because the shared wrapper records per-call ``.info``."""
    base = partial(build_quantized_tileset_family, params=ROM_FAMILY_PARAMS)
    if ROM_SHARED_PALETTES:
        return make_shared_quantizer(base, family_params=ROM_FAMILY_PARAMS)
    return base
