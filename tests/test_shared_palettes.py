"""Shared fixed palettes (P2 preview): constants, fitting, reservation, cross-map identity."""
from __future__ import annotations

from functools import partial

import numpy as np
import pytest

from rpg2gba.tileset_converter.graphics import shared_palettes as sp
from rpg2gba.tileset_converter.graphics.quantize import (
    FamilyParams,
    QuantizeResult,
    build_quantized_tileset_family,
    to_5bit,
)


def _tile_from(palette: np.ndarray, seed: int, idxs: list[int] | None = None) -> np.ndarray:
    rng = np.random.default_rng(seed)
    pool = palette if idxs is None else palette[idxs]
    rgb = pool[rng.integers(0, len(pool), size=(8, 8))]
    return np.concatenate([rgb, np.full((8, 8, 1), 255, np.uint8)], axis=2)


def rock_tile(seed: int) -> np.ndarray:
    return _tile_from(sp.ROCK_V1, seed)


def green_tile(seed: int) -> np.ndarray:
    return _tile_from(sp.GREEN_G3T[0], seed, [2, 3, 5, 6])


def noise_tile(seed: int) -> np.ndarray:
    """Saturated blue/magenta tile: neither rock nor green."""
    rng = np.random.default_rng(seed)
    rgb = np.stack(
        [rng.integers(0, 256, (8, 8)), rng.integers(0, 40, (8, 8)), rng.integers(200, 256, (8, 8))],
        axis=2,
    ).astype(np.uint8)
    return np.concatenate([rgb, np.full((8, 8, 1), 255, np.uint8)], axis=2)


def empty_tile() -> np.ndarray:
    return np.zeros((8, 8, 4), np.uint8)


BASE = partial(build_quantized_tileset_family, params=FamilyParams())


def test_constants_are_15_colours_and_5bit_exact():
    for pal in (sp.ROCK_V1, *sp.GREEN_G3T):
        assert pal.shape == (15, 3) and pal.dtype == np.uint8
        assert np.array_equal(to_5bit(pal), pal)
    assert len(sp.GREEN_G3T) == 3


def test_fit_palette_pure_v1_tile_is_exact():
    assert sp.fit_palette(rock_tile(1), sp.ROCK_V1, None) == (0, 0)


def test_fit_palette_transparent_is_none():
    assert sp.fit_palette(empty_tile(), sp.ROCK_V1, None) is None


def test_fit_palette_extra_colours_count():
    far = np.array([[0, 0, 255]], np.uint8)
    mx, sse = sp.fit_palette(rock_tile(1), sp.ROCK_V1, far)
    assert mx > 0 and sse > 0


def test_tiles_are_classified_as_intended():
    q = sp.make_shared_quantizer(BASE)
    tiles = [green_tile(i) for i in range(8)]
    q(tiles, max_palettes=13)
    assert q.info["n_green"] == 8 and q.info["n_rock"] == 0


def test_rock_reserved_when_enough_tiles():
    q = sp.make_shared_quantizer(BASE)
    tiles = [rock_tile(i) for i in range(8)] + [noise_tile(100)]
    r = q(tiles, max_palettes=13)
    assert q.info["rock_reserved"] and not q.info["green_reserved"]
    assert q.info["reserved"] == 1 and q.info["packer_budget"] == 12
    assert np.array_equal(r.palettes[0], sp.ROCK_V1)
    for i in range(8):
        assert r.tile_palette[i] == 0
        rgb = r.quantized[i][..., :3].reshape(-1, 3)
        assert {tuple(c) for c in rgb} <= {tuple(c) for c in sp.ROCK_V1}
        assert np.array_equal(r.quantized[i][..., :3], tiles[i][..., :3])
    assert r.tile_palette[8] >= 1
    assert r.stats["n_palettes"] == len(r.palettes)


def test_green_reserved_uses_three_palettes():
    q = sp.make_shared_quantizer(BASE)
    tiles = [green_tile(i) for i in range(9)]
    r = q(tiles, max_palettes=13)
    assert q.info["green_reserved"] and q.info["reserved"] == 3
    assert all(0 <= p < 3 for p in r.tile_palette)
    assert len(r.palettes) == 3


def test_below_threshold_equals_base():
    tiles = [rock_tile(i) for i in range(7)] + [noise_tile(i) for i in range(5)]
    q = sp.make_shared_quantizer(BASE)
    r = q(tiles, max_palettes=13)
    ref = BASE(tiles, max_palettes=13)
    assert q.info["reserved"] == 0
    assert r.tile_palette == ref.tile_palette
    assert len(r.palettes) == len(ref.palettes)
    for a, b in zip(r.quantized, ref.quantized):
        assert np.array_equal(a, b)


def test_same_art_identical_across_different_maps():
    """The point of P2: shared tiles quantize identically whatever surrounds them."""
    rock, green = rock_tile(7), green_tile(7)
    q = sp.make_shared_quantizer(BASE)
    map_a = [rock, green] + [rock_tile(i) for i in range(10, 18)] + [green_tile(i) for i in range(10, 18)]
    map_b = [noise_tile(i) for i in range(6)] + [green, rock] + [green_tile(i) for i in range(30, 40)] \
        + [rock_tile(i) for i in range(30, 40)]
    ra = q(map_a, max_palettes=13)
    rb = q(map_b, max_palettes=13)
    assert np.array_equal(ra.quantized[0], rb.quantized[7])
    assert np.array_equal(ra.quantized[1], rb.quantized[6])
    assert ra.tile_palette[0] == rb.tile_palette[7]
    assert ra.tile_palette[1] == rb.tile_palette[6]


def test_base_gets_reduced_budget_and_remapped_extras():
    calls: list[tuple[int, int, dict | None]] = []

    def spy(tiles, *, max_palettes=13, extra_tile_colors=None):
        calls.append((len(tiles), max_palettes, extra_tile_colors))
        return BASE(tiles, max_palettes=max_palettes, extra_tile_colors=extra_tile_colors)

    q = sp.make_shared_quantizer(spy)
    # idx 0..7 rock (reserved), 8 noise, 9 rock-ish, 10 noise
    tiles = [rock_tile(i) for i in range(8)] + [noise_tile(1), rock_tile(50), noise_tile(2)]
    e8 = np.array([[255, 0, 255]], np.uint8)
    e10 = np.array([[0, 0, 255]], np.uint8)
    q(tiles, max_palettes=13, extra_tile_colors={8: e8, 10: e10, 0: e8})
    n, mp, extra = calls[0]
    # tile 0 carries a far extra colour, so it falls out of the rock set: rest = [0, 8, 10]
    assert (n, mp) == (3, 12)
    assert set(extra) == {0, 1, 2}
    assert np.array_equal(extra[0], e8) and np.array_equal(extra[1], e8) and np.array_equal(extra[2], e10)


def test_reserved_too_many_raises():
    q = sp.make_shared_quantizer(BASE)
    tiles = [green_tile(i) for i in range(9)] + [noise_tile(1)]
    with pytest.raises(ValueError):
        q(tiles, max_palettes=3)


def test_reserved_exactly_fills_without_rest_is_ok():
    q = sp.make_shared_quantizer(BASE)
    r = q([green_tile(i) for i in range(9)], max_palettes=3)
    assert isinstance(r, QuantizeResult) and len(r.palettes) == 3


def test_transparent_tiles_get_minus_one():
    q = sp.make_shared_quantizer(BASE)
    tiles = [empty_tile()] + [rock_tile(i) for i in range(8)]
    r = q(tiles, max_palettes=13)
    assert r.tile_palette[0] == -1 and r.color_map[0] == []
    assert r.quantized[0].shape == (8, 8, 4)
