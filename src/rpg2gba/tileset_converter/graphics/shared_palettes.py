"""Shared fixed palettes (design piece P2) -- viewer preview only.

The ROM build does NOT use this module.  Every map normally quantizes its tiles into
<=13 sub-palettes on its own, so identical tree/rock art lands on different colours on
different maps.  P2 pins a fixed game-wide rock palette plus three fixed green palettes
into every map that uses at least ``min_tiles`` tiles of that group, so shared art is
pixel-identical across maps.  The rest of the tiles go to the ordinary packer with the
palette budget reduced by the number of reserved slots.

The palette values below are PROVISIONAL research values (2026-10-05), not approved:
see ``reference/chapters/06-tileset-plan.md`` -> "Candidate palette design".

``make_shared_quantizer`` returns a callable with the same ``quantizer=`` hook shape as
``palette_families.make_pinned_quantizer``:
``(tiles, *, max_palettes, extra_tile_colors=None) -> QuantizeResult``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

import numpy as np

from rpg2gba.tileset_converter.graphics.quantize import (
    DEFAULT_MAX_PALETTES,
    FamilyParams,
    QuantizeResult,
    _dominant_family,
    quantize_tile_to_palette,
    resolve_alpha,
    to_5bit,
)

logger = logging.getLogger(__name__)


def _hex_palette(spec: str) -> np.ndarray:
    """Space-separated RRGGBB hex -> (n,3) uint8, asserted already 5-bit-expanded."""
    arr = np.array(
        [[int(h[i:i + 2], 16) for i in (0, 2, 4)] for h in spec.split()], dtype=np.uint8
    )
    assert arr.shape == (15, 3), arr.shape
    assert np.array_equal(to_5bit(arr), arr), "palette colour is not 5-bit-expanded"
    return arr


ROCK_V1: np.ndarray = _hex_palette(
    "392929 735242 73635a 845a4a 946b4a ad7b63 ad845a bd8463 "
    "c6946b d6a573 e7b57b 63b563 73d673 528cad 5a94b5"
)

GREEN_G3T: tuple[np.ndarray, ...] = (
    _hex_palette(
        "104229 106331 4a8c42 31ad63 6b9c6b 63ce63 73d66b 73d673 "
        "7bd673 7bde6b 9ce79c 5a4a31 846b39 bd8c63 c6bdc6"
    ),
    _hex_palette(
        "295231 317342 109452 4a8c52 18bd6b 42b55a 4ad673 9cad6b "
        "73d673 94c673 b5d684 efa5a5 a5ada5 e7e7e7 ffde73"
    ),
    _hex_palette(
        "084a29 106331 314231 106b42 109442 425a4a 39734a 318c52 "
        "4a8c4a 21ad52 42a563 31d65a 4abd6b 5ace84 73d673"
    ),
)


def fit_palette(
    tile: np.ndarray, palette: np.ndarray, extra: np.ndarray | Sequence | None
) -> tuple[int, int] | None:
    """``(max per-channel 5-bit shift, SSE in 5-bit units)`` of *tile* against *palette*.

    Later animation frames' 5-bit colours (*extra*) are fitted too.  None for a fully
    transparent tile."""
    res = resolve_alpha(tile)
    op = res[..., 3] == 255
    if not op.any():
        return None
    q = quantize_tile_to_palette(tile, palette)
    px = (res[..., :3][op] >> 3).astype(np.int32)
    qp = (q[..., :3][op] >> 3).astype(np.int32)
    d = np.abs(px - qp)
    mx = int(d.max())
    sse = int((d ** 2).sum())
    if extra is not None and len(extra):
        e = np.asarray(extra, np.int32) >> 3
        p5 = np.asarray(palette, np.int32) >> 3
        nearest = ((e[:, None, :] - p5[None]) ** 2).sum(2).argmin(1)
        ee = np.abs(e - p5[nearest])
        mx = max(mx, int(ee.max()))
        sse += int((ee ** 2).sum())
    return mx, sse


def _pin(
    tile: np.ndarray,
    palette: np.ndarray,
    i: int,
    pidx: int,
    tile_palette: list[int],
    quantized: list[np.ndarray | None],
    color_map: list[list],
) -> None:
    out = quantize_tile_to_palette(tile, palette)
    tile_palette[i] = pidx
    quantized[i] = out
    res = resolve_alpha(tile)
    op = res[..., 3] == 255
    orig8 = res[..., :3][op]
    uniq, idx = np.unique(orig8, axis=0, return_index=True)
    finals = out[..., :3][op][idx]
    color_map[i] = [
        (tuple(int(v) for v in o), tuple(int(v) for v in f)) for o, f in zip(uniq, finals)
    ]


def make_shared_quantizer(
    base: Callable[..., QuantizeResult],
    *,
    min_tiles: int = 8,
    rock_max_shift: int = 1,
    family_params: FamilyParams | None = None,
) -> Callable[..., QuantizeResult]:
    """Wrap *base* so fixed rock / green palettes are reserved when a map uses enough
    of that art.  ``.info`` on the returned callable holds the latest call's counts."""
    fparams = family_params or FamilyParams()
    info: dict = {}

    def quantizer(
        tiles: Sequence[np.ndarray],
        *,
        max_palettes: int = DEFAULT_MAX_PALETTES,
        extra_tile_colors: dict[int, np.ndarray] | None = None,
    ) -> QuantizeResult:
        n = len(tiles)
        tile_palette = [-1] * n
        quantized: list[np.ndarray | None] = [None] * n
        color_map: list[list] = [[] for _ in range(n)]

        def extra_of(i: int):
            return extra_tile_colors.get(i) if extra_tile_colors else None

        rock = [False] * n
        green = [False] * n
        empty = [False] * n
        for i, t in enumerate(tiles):
            f = fit_palette(t, ROCK_V1, extra_of(i))
            if f is None:
                empty[i] = True
                continue
            if f[0] <= rock_max_shift:
                rock[i] = True
            elif _dominant_family(t, fparams) == "green":
                green[i] = True
        n_rock, n_green = sum(rock), sum(green)
        rock_reserved = n_rock >= min_tiles
        green_reserved = n_green >= min_tiles

        palettes: list[np.ndarray] = []
        rock_idx = -1
        if rock_reserved:
            rock_idx = len(palettes)
            palettes.append(ROCK_V1.copy())
        green_off = -1
        if green_reserved:
            green_off = len(palettes)
            palettes.extend(g.copy() for g in GREEN_G3T)
        reserved = len(palettes)

        rest: list[int] = []
        for i, t in enumerate(tiles):
            if empty[i]:
                continue
            if rock[i] and rock_reserved:
                _pin(t, ROCK_V1, i, rock_idx, tile_palette, quantized, color_map)
            elif green[i] and green_reserved:
                # Research used a hand-refined tile->palette table with an adjacency
                # penalty; this preview takes best-fit, so mixed-palette grass cells
                # may come out higher than in the research numbers.
                fits = [fit_palette(t, g, extra_of(i)) for g in GREEN_G3T]
                best = min(range(len(GREEN_G3T)), key=lambda k: (fits[k][1], k))
                _pin(t, GREEN_G3T[best], i, green_off + best, tile_palette, quantized, color_map)
            else:
                rest.append(i)

        budget = max_palettes - reserved
        if rest:
            if budget <= 0:
                raise ValueError(
                    f"shared palettes reserve {reserved} of max_palettes={max_palettes}, "
                    f"leaving none for {len(rest)} remaining tile(s)"
                )
            local_extra = {
                li: extra_tile_colors[gi] for li, gi in enumerate(rest)
                if extra_tile_colors and gi in extra_tile_colors
            } or None
            r = base(
                [tiles[i] for i in rest], max_palettes=budget, extra_tile_colors=local_extra
            )
            off = len(palettes)
            for li, gi in enumerate(rest):
                lp = r.tile_palette[li]
                tile_palette[gi] = -1 if lp < 0 else off + lp
                quantized[gi] = r.quantized[li]
                color_map[gi] = r.color_map[li]
            palettes.extend(r.palettes)
        for i in range(n):
            if quantized[i] is None:
                quantized[i] = resolve_alpha(tiles[i])
        if len(palettes) > max_palettes:
            raise ValueError(
                f"shared palettes produced {len(palettes)} palettes, over max {max_palettes}"
            )

        info.clear()
        info.update(
            n_rock=n_rock, n_green=n_green, rock_reserved=rock_reserved,
            green_reserved=green_reserved, reserved=reserved,
            packer_budget=budget,
        )
        logger.debug("shared palettes: %s", info)
        return QuantizeResult(
            palettes=palettes, tile_palette=tile_palette, quantized=quantized,  # type: ignore[arg-type]
            stats={"n_palettes": len(palettes), **info}, color_map=color_map,
        )

    quantizer.info = info  # type: ignore[attr-defined]
    return quantizer
