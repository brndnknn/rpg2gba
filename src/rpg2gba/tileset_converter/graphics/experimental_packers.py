"""Experimental palette-packing strategies (debug / A-B comparison only).

The production packer is :func:`quantize.build_quantized_tileset` (one global
agglomerative merge). These two alternates were prototyped while investigating
Moki Town's foliage colour-collapse; both proved within ~2% of the production
packer (the loss is a hard 13-palette budget ceiling, not the packing strategy —
see ``reference/graphics_conversion_notes.md``). They are kept ONLY to drive the
in-ROM palette-variant comparison (``scripts/build_palette_compare.py``); they are
NOT wired into the slice assembly. Each shares ``build_quantized_tileset``'s
signature ``(tiles, *, max_palettes) -> QuantizeResult`` so ``emit_tileset`` can
take either via its ``quantizer`` parameter.
"""
from __future__ import annotations

import bisect
import colorsys
import logging
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from .quantize import (
    QuantizeResult,
    _opaque_colors,
    build_quantized_tileset,
    resolve_alpha,
    to_5bit,
)

logger = logging.getLogger(__name__)

CPP = 15            # usable colours per sub-palette (index 0 transparent)
_NO_VOCAB_CUT = 10**9  # global_colors high enough to disable phase-1 vocab merge


@dataclass(frozen=True)
class FamilyParams:
    dark_value: int = 40          # max(r,g,b) < dark_value  → "dark"
    neutral_sat: float = 0.18     # HSV saturation < neutral_sat → "neutral"
    green_cuts: tuple[float, ...] = ()  # interior hue° in (70,170) splitting green into sub-bands
    palette_floor: int = 1        # minimum palettes guaranteed to each family
    overflow_weight: str = "colors"  # "colors"=distinct overflow; "coverage"=tile-weighted


def _dominant_family(tile: np.ndarray, params: FamilyParams = FamilyParams()) -> str | None:
    """Hue family of a tile's DOMINANT (most-pixels) opaque 5-bit colour.

    ``None`` for a fully-transparent tile. Coarse bins: low-value -> ``dark``,
    low-saturation -> ``neutral``, else a hue wedge (red/brown/yellow/green/cyan/
    blue/purple). With non-empty ``params.green_cuts``, the green band [70,170) is
    split into sub-families ``green0``, ``green1``, …"""
    res = resolve_alpha(tile)
    opaque = res[..., 3] == 255
    if not opaque.any():
        return None
    px = to_5bit(res[..., :3][opaque])
    colors, counts = np.unique(px, axis=0, return_counts=True)
    r, g, b = (int(v) for v in colors[counts.argmax()])
    if max(r, g, b) < params.dark_value:
        return "dark"
    h, s, _v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    if s < params.neutral_sat:
        return "neutral"
    deg = h * 360
    if deg < 15 or deg >= 345:
        return "red"
    if deg < 45:
        return "brown"
    if deg < 70:
        return "yellow"
    if deg < 170:
        if not params.green_cuts:
            return "green"
        cuts = sorted(c for c in params.green_cuts if 70 < c < 170)
        if not cuts:
            return "green"
        idx = bisect.bisect_right(cuts, deg)
        return f"green{idx}"
    if deg < 200:
        return "cyan"
    if deg < 255:
        return "blue"
    return "purple"


def _pack_subset(
    tiles: list[np.ndarray],
    idxs: list[int],
    budget: int,
    offset: int,
    palettes: list[np.ndarray],
    tile_palette: list[int],
    quantized: list[np.ndarray | None],
    color_map: list,
) -> int:
    """Quantize ``tiles[idxs]`` into <=``budget`` palettes (no phase-1 vocab cut, so
    the merge stays within the subset) and splice the result into the global lists at
    palette ``offset``. Returns the next free palette offset."""
    if not idxs or budget <= 0:
        return offset
    r = build_quantized_tileset(
        [tiles[i] for i in idxs], max_palettes=budget, global_colors=_NO_VOCAB_CUT
    )
    for local_i, gi in enumerate(idxs):
        lp = r.tile_palette[local_i]
        tile_palette[gi] = -1 if lp < 0 else offset + lp
        quantized[gi] = r.quantized[local_i]
        color_map[gi] = r.color_map[local_i]
    palettes.extend(r.palettes)
    return offset + len(r.palettes)


def _assemble(
    tiles: list[np.ndarray],
    palettes: list[np.ndarray],
    tile_palette: list[int],
    quantized: list[np.ndarray | None],
    color_map: list,
) -> QuantizeResult:
    for i, q in enumerate(quantized):
        if q is None:
            quantized[i] = resolve_alpha(tiles[i])
    return QuantizeResult(
        palettes=palettes,
        tile_palette=tile_palette,
        quantized=quantized,  # type: ignore[arg-type]
        color_map=color_map,
        stats={"n_palettes": len(palettes)},
    )


def build_quantized_tileset_family(
    tiles: list[np.ndarray], *, max_palettes: int = 13, params: FamilyParams | None = None
) -> QuantizeResult:
    """Partition tiles by their dominant hue family, pour the palette budget into the
    families that overflow most, pack each family with the production packer.

    Pass a :class:`FamilyParams` to tune hue-bin boundaries, green-band splits,
    per-family palette floor, and overflow weighting. Omitting ``params`` (or passing
    ``None``) reproduces the original fixed behaviour exactly."""
    params = params or FamilyParams()
    n = len(tiles)
    fam_of = [_dominant_family(t, params) for t in tiles]
    fam_tiles: dict[str, list[int]] = defaultdict(list)
    for i, f in enumerate(fam_of):
        if f is not None:
            fam_tiles[f].append(i)

    fam_distinct = {
        f: len(np.unique(
            np.concatenate([_opaque_colors(resolve_alpha(tiles[i])) for i in idxs]), axis=0))
        for f, idxs in fam_tiles.items()
    }
    fam_counts = {f: len(idxs) for f, idxs in fam_tiles.items()}
    budget = _allocate_by_overflow(
        fam_distinct, max_palettes,
        counts=fam_counts,
        floor=params.palette_floor,
        mode=params.overflow_weight,
    )

    palettes: list[np.ndarray] = []
    tile_palette = [-1] * n
    quantized: list[np.ndarray | None] = [None] * n
    color_map: list = [[] for _ in range(n)]
    offset = 0
    for f, idxs in fam_tiles.items():
        offset = _pack_subset(tiles, idxs, budget[f], offset,
                              palettes, tile_palette, quantized, color_map)
    return _assemble(tiles, palettes, tile_palette, quantized, color_map)


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


def _allocate_by_overflow(
    distinct: dict[str, int],
    total: int,
    *,
    counts: dict[str, int] | None = None,
    floor: int = 1,
    mode: str = "colors",
) -> dict[str, int]:
    """Give every group ``floor`` palettes, then hand each remaining palette to the
    group with the most overflow.

    ``mode="colors"`` (default): overflow = ``distinct - alloc*CPP``; identical to
    the original hardcoded behaviour when ``floor=1``.
    ``mode="coverage"``: overflow = ``counts * (distinct - alloc*CPP)``; requires
    ``counts``; large-coverage families win ties against high-distinct-but-rare ones.
    """
    groups = list(distinct)
    if len(groups) * floor > total:
        raise ValueError(
            f"{len(groups)} groups × floor {floor} = {len(groups) * floor} exceed {total} palettes"
        )
    alloc = {g: floor for g in groups}
    for _ in range(total - len(groups) * floor):
        if mode == "coverage":
            assert counts is not None, "counts required for mode='coverage'"
            g = max(groups, key=lambda g: counts[g] * (distinct[g] - alloc[g] * CPP))
            if counts[g] * (distinct[g] - alloc[g] * CPP) <= 0:
                break
        else:  # "colors"
            g = max(groups, key=lambda g: distinct[g] - alloc[g] * CPP)
            if distinct[g] - alloc[g] * CPP <= 0:
                break
        alloc[g] += 1
    return alloc
