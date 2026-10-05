"""Palette families pinned per seam component.

Design: ``reference/guides/connections_and_palette_families.md`` part 2.

Maps joined by seams form connected components.  Every map in a component keeps its
OWN tileset (own tiles / metatiles) but they are all quantized against ONE shared set
of <=13 palettes computed over the component's tile union, so a colour that crosses a
seam looks the same on both sides.

This module is library-only: nothing here is wired into the build or the viewer.
Typical use::

    comps = seam_components(rows, map_ids)
    for members in sorted(set(comps.values())):
        pals = compute_component_palettes([metatiles_of[m] for m in members])
        pinned = make_pinned_quantizer(pals)
        emit_tileset(metatiles_of[m], ..., quantizer=pinned)   # per member map
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Sequence

import numpy as np

# `_canonicalize_and_quantize` is private to emit.py, but it IS the emitter's own dedup
# + extra-frame-colour logic; reusing it (rather than re-implementing) guarantees the
# component palettes are fitted over exactly the tile pool each member's emission will
# later produce.  Unlike `emit_tileset` it enforces no 1024-tile cap, so a component's
# tile union may exceed the hardware budget here (this is palette fitting only).
from rpg2gba.tileset_converter.connections import ConnectionRow
from rpg2gba.tileset_converter.graphics.emit import (
    MetatileImage,
    _canonicalize_and_quantize,
)
from rpg2gba.tileset_converter.graphics.quantize import (
    DEFAULT_MAX_PALETTES,
    QuantizeResult,
    build_quantized_tileset_family,
    quantize_tile_to_palette,
    resolve_alpha,
    to_5bit,
)

logger = logging.getLogger(__name__)


def seam_components(
    rows: Iterable[ConnectionRow],
    map_ids: Iterable[int] | None = None,
) -> dict[int, tuple[int, ...]]:
    """Connected components of the seam graph.

    Returns ``map id -> its component`` (a sorted tuple of map ids, identical for all
    members).  Maps with no neighbour are ABSENT (they keep ordinary per-map packing).

    ``map_ids``, when given, restricts the graph: only rows with BOTH endpoints in the
    set count.

    Every connection row counts, including rows that ``seam_warps.json`` turns into
    arrow warps: the component is geographic, and colours should still match across
    an arrow-warp crossing."""
    allowed = None if map_ids is None else set(map_ids)
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for row in rows:
        a, b = row.map_a, row.map_b
        if allowed is not None and (a not in allowed or b not in allowed):
            continue
        if a == b:
            continue
        parent.setdefault(a, a)
        parent.setdefault(b, b)
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    groups: dict[int, list[int]] = {}
    for m in parent:
        groups.setdefault(find(m), []).append(m)
    out: dict[int, tuple[int, ...]] = {}
    for members in groups.values():
        comp = tuple(sorted(members))
        for m in comp:
            out[m] = comp
    return out


def compute_component_palettes(
    metatile_lists: Sequence[Sequence[MetatileImage]],
    *,
    max_palettes: int = DEFAULT_MAX_PALETTES,
    quantizer: Callable[..., QuantizeResult] = build_quantized_tileset_family,
) -> list[np.ndarray]:
    """Fit ONE shared palette set over the tile union of several maps.

    ``metatile_lists`` are concatenated IN THE GIVEN ORDER (callers pass them sorted
    by map id; the packer is order-sensitive, so this keeps results deterministic),
    flip-canonically deduplicated exactly as the emitter does, and packed by
    ``quantizer``.  Returns the resulting palettes (each (<=15,3) uint8)."""
    union: list[MetatileImage] = [mt for lst in metatile_lists for mt in lst]
    if not union:
        return []
    _, _, quant, _ = _canonicalize_and_quantize(
        union, max_palettes=max_palettes, quantizer=quantizer
    )
    if len(quant.palettes) > max_palettes:
        raise ValueError(
            f"quantizer returned {len(quant.palettes)} palettes, over max {max_palettes}"
        )
    return [np.asarray(p, dtype=np.uint8) for p in quant.palettes]


def make_pinned_quantizer(
    palettes: Sequence[np.ndarray],
) -> Callable[..., QuantizeResult]:
    """Build a quantizer hook that assigns tiles to FIXED ``palettes``.

    The returned callable has the emitter's hook signature
    ``(tiles, *, max_palettes, extra_tile_colors=None) -> QuantizeResult`` and the
    result is index-aligned with ``tiles``.  Each non-empty tile takes the pinned
    palette with the lowest summed squared RGB error over its opaque (5-bit) pixels,
    plus -- when ``extra_tile_colors[i]`` (later animation frames' 5-bit colours) is
    given -- those colours, so the chosen palette also serves the animation.  Ties go
    to the lowest palette index.  Empty / fully-transparent tiles get -1.

    Raises ValueError (at construction, and again at call time if the call's
    ``max_palettes`` is smaller) when there are more palettes than ``max_palettes``."""
    pinned = [np.asarray(p, dtype=np.uint8).reshape(-1, 3) for p in palettes]
    pinned_i32 = [p.astype(np.int32) for p in pinned]

    def _check(limit: int) -> None:
        if len(pinned) > limit:
            raise ValueError(
                f"{len(pinned)} pinned palettes exceed max_palettes={limit}"
            )

    _check(DEFAULT_MAX_PALETTES)

    def quantizer(
        tiles: Sequence[np.ndarray],
        *,
        max_palettes: int = DEFAULT_MAX_PALETTES,
        extra_tile_colors: dict[int, np.ndarray] | None = None,
    ) -> QuantizeResult:
        _check(max_palettes)
        n = len(tiles)
        tile_palette = [-1] * n
        quantized: list[np.ndarray] = []
        color_map: list[list[tuple[tuple[int, int, int], tuple[int, int, int]]]] = []
        shifts: list[np.ndarray] = []
        for i, tile in enumerate(tiles):
            resolved = resolve_alpha(tile)
            opaque = resolved[..., 3] == 255
            if not opaque.any() or not pinned:
                quantized.append(resolved)
                color_map.append([])
                continue
            px = to_5bit(resolved[..., :3][opaque]).astype(np.int32)
            extra = extra_tile_colors.get(i) if extra_tile_colors else None
            probe = (
                px if extra is None or len(extra) == 0
                else np.concatenate([px, np.asarray(extra, dtype=np.int32)])
            )
            best_pi, best_err = -1, None
            for pi, pal in enumerate(pinned_i32):
                if len(pal) == 0:
                    continue
                d = ((probe[:, None, :] - pal[None, :, :]) ** 2).sum(2).min(1)
                err = int(d.sum())
                if best_err is None or err < best_err:
                    best_pi, best_err = pi, err
            if best_pi < 0:
                quantized.append(resolved)
                color_map.append([])
                continue
            tile_palette[i] = best_pi
            out = quantize_tile_to_palette(tile, pinned[best_pi])
            quantized.append(out)
            new = out[..., :3][opaque]
            orig8 = resolved[..., :3][opaque]
            uniq8, idx = np.unique(orig8, axis=0, return_index=True)
            finals = new[idx]
            color_map.append([
                ((int(o[0]), int(o[1]), int(o[2])), (int(f[0]), int(f[1]), int(f[2])))
                for o, f in zip(uniq8, finals)
            ])
            shifts.append(np.abs((px >> 3) - (new.astype(np.int32) >> 3)).mean(1))

        all_shift = np.concatenate(shifts) if shifts else np.zeros(1)
        stats = {
            "n_tiles": n,
            "n_palettes": len(pinned),
            "max_colors": max((len(p) for p in pinned), default=0),
            "mean_shift_5bit": float(all_shift.mean()),
            "max_shift_5bit": float(all_shift.max()),
            "p95_shift_5bit": float(np.percentile(all_shift, 95)),
            "pinned": True,
        }
        return QuantizeResult(
            palettes=[p.copy() for p in pinned],
            tile_palette=tile_palette,
            quantized=quantized,
            stats=stats,
            color_map=color_map,
        )

    return quantizer
