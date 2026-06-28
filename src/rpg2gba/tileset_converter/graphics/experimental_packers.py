"""Experimental palette-packing alternate — the diversity strategy (debug / A-B only).

The pipeline's production packers live in :mod:`quantize`:
:func:`quantize.build_quantized_tileset` (one global merge) and
:func:`quantize.build_quantized_tileset_family` (per-hue-family budget — the current
default, validated by eye and used by ``build_slice_tilesets`` + the map viewer).

This module keeps the one genuinely experimental alternate,
:func:`build_quantized_tileset_diversity`, which is **NOT** wired into the slice — it
exists only to drive the in-ROM A/B/C comparison (``scripts/build_palette_compare.py``).
It shares ``build_quantized_tileset``'s ``(tiles, *, max_palettes) -> QuantizeResult``
signature so ``emit_tileset`` can take it via its ``quantizer`` parameter.

``FamilyParams`` and ``build_quantized_tileset_family`` are re-exported from
:mod:`quantize` for the callers that still import them from here (the map viewer, the
compare script, tests).
"""
from __future__ import annotations

import numpy as np

from .quantize import (
    FamilyParams,
    QuantizeResult,
    _assemble,
    _opaque_colors,
    _pack_subset,
    build_quantized_tileset_family,
    resolve_alpha,
)

__all__ = [
    "FamilyParams",
    "build_quantized_tileset_family",
    "build_quantized_tileset_diversity",
]


def build_quantized_tileset_diversity(
    tiles: list[np.ndarray], *, max_palettes: int = 13,
    dense_budget: int = 6, dense_threshold: int = 12,
) -> QuantizeResult:
    """Split tiles by per-tile colour DIVERSITY: tiles with >=``dense_threshold``
    distinct colours (dense foliage) reserve ``dense_budget`` palettes; the simpler
    rest share the remainder, so the dense tiles stop sharing with flat grass/paths."""
    n = len(tiles)
    src5 = [_opaque_colors(resolve_alpha(t)) for t in tiles]
    hero = [i for i in range(n) if len(src5[i]) >= dense_threshold]
    simple = [i for i in range(n) if 0 < len(src5[i]) < dense_threshold]

    palettes: list[np.ndarray] = []
    tile_palette = [-1] * n
    quantized: list[np.ndarray | None] = [None] * n
    color_map: list = [[] for _ in range(n)]
    offset = _pack_subset(tiles, hero, dense_budget, 0,
                          palettes, tile_palette, quantized, color_map)
    _pack_subset(tiles, simple, max_palettes - dense_budget, offset,
                 palettes, tile_palette, quantized, color_map)
    return _assemble(tiles, palettes, tile_palette, quantized, color_map)
