"""Tests for the optional usage-weighted Ward per-palette reduction (quantize.py)."""
from __future__ import annotations

import numpy as np
import pytest

from rpg2gba.tileset_converter.graphics import quantize as Q
from rpg2gba.tileset_converter.graphics.quantize import (
    FamilyParams,
    _ward_reduce,
    build_quantized_tileset,
    build_quantized_tileset_family,
    to_5bit,
)


def _cols(*rows: tuple[int, int, int]) -> np.ndarray:
    return to_5bit(np.array(rows, dtype=np.uint8))


def _has(arr: np.ndarray, rgb: tuple[int, int, int]) -> bool:
    return bool((arr == np.array(to_5bit(np.array([rgb], np.uint8))[0])).all(1).any())


def _forcing_tiles(n: int = 24) -> list[np.ndarray]:
    """Tiles whose combined colour set (n distinct) exceeds 15 so a 1-palette pack reduces."""
    rng = np.random.default_rng(7)
    tiles = []
    for i in range(n):
        t = np.zeros((8, 8, 4), np.uint8)
        t[..., 3] = 255
        t[..., :3] = rng.integers(0, 256, size=3, dtype=np.uint8)
        # a second colour on a few pixels, so usage weights are uneven
        t[:2, :2, :3] = rng.integers(0, 256, size=3, dtype=np.uint8)
        tiles.append(t)
    return tiles


def _green_tiles(n: int = 24) -> list[np.ndarray]:
    """Single-family (green) tiles with >15 distinct colours and uneven pixel usage."""
    tiles = []
    for i in range(n):
        t = np.zeros((8, 8, 4), np.uint8)
        t[..., 3] = 255
        t[..., :3] = (0, 120 + 5 * i, 0)
        t[:2, :2, :3] = (16 + 8 * (i % 7), 255 - 4 * i, 8 * (i % 5))
        tiles.append(t)
    return tiles


def _same(a, b) -> None:
    assert a.tile_palette == b.tile_palette
    assert len(a.palettes) == len(b.palettes)
    for pa, pb in zip(a.palettes, b.palettes):
        assert np.array_equal(pa, pb)
    for qa, qb in zip(a.quantized, b.quantized):
        assert np.array_equal(qa, qb)


def test_default_matches_explicit_median_cut() -> None:
    tiles = _forcing_tiles()
    default = build_quantized_tileset(tiles, max_palettes=1)
    explicit = build_quantized_tileset(tiles, max_palettes=1, reduction="median_cut")
    assert len(default.palettes[0]) == 15  # reduction was actually forced
    _same(default, explicit)


def test_ward_reduce_count_and_5bit_expanded() -> None:
    rng = np.random.default_rng(1)
    colors = np.unique(to_5bit(rng.integers(0, 256, size=(60, 3), dtype=np.uint8)), axis=0)
    out = _ward_reduce(colors, rng.integers(1, 50, len(colors)).astype(float), 15)
    assert out.dtype == np.uint8 and out.shape[1] == 3
    assert 1 <= len(out) <= 15
    assert np.array_equal(to_5bit(out), out)


def test_ward_reduce_noop_when_under_k() -> None:
    colors = _cols((0, 0, 0), (248, 0, 0), (0, 248, 0))
    out = _ward_reduce(colors, np.ones(3), 5)
    assert np.array_equal(out, np.unique(colors, axis=0))


def test_weight_keeps_heavy_colour_exact() -> None:
    a, b = (0, 0, 0), (16, 0, 0)
    heavy, far = (32, 0, 0), (248, 248, 248)
    colors = _cols(a, b, heavy, far)
    out = _ward_reduce(colors, np.array([1.0, 1.0, 1000.0, 1000.0]), 3)
    assert len(out) == 3
    assert _has(out, heavy)
    assert _has(out, far)
    assert _has(out, (8, 0, 0))  # the two rare near colours merged to their midpoint
    assert not _has(out, a) and not _has(out, b)


def test_heavy_grey_not_merged_into_green_pair() -> None:
    grey = (128, 128, 128)
    g1, g2 = (112, 160, 112), (112, 176, 112)
    colors = _cols(grey, g1, g2)
    out = _ward_reduce(colors, np.array([5000.0, 1.0, 1.0]), 2)
    assert len(out) == 2
    assert _has(out, grey)
    assert not _has(out, g1) and not _has(out, g2)


def test_family_params_ward_reaches_reduction(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    real = Q._ward_reduce

    def spy(colors, weights, k):
        calls.append(len(colors))
        return real(colors, weights, k)

    monkeypatch.setattr(Q, "_ward_reduce", spy)
    tiles = _green_tiles()
    stock = build_quantized_tileset_family(tiles, max_palettes=1)
    assert calls == []
    ward = build_quantized_tileset_family(
        tiles, max_palettes=1, params=FamilyParams(reduction="ward")
    )
    assert calls
    assert len(ward.palettes[0]) <= 15
    assert any(
        not np.array_equal(a, b) for a, b in zip(stock.quantized, ward.quantized)
    )


def test_unknown_reduction_raises() -> None:
    with pytest.raises(ValueError):
        build_quantized_tileset(_forcing_tiles(4), max_palettes=1, reduction="bogus")
    with pytest.raises(ValueError):
        build_quantized_tileset_family(
            _forcing_tiles(4), max_palettes=1, params=FamilyParams(reduction="bogus")
        )
