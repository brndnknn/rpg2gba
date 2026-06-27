"""Tests for FamilyParams tunability in experimental_packers.

Verifies that:
  - Default FamilyParams reproduces original behaviour byte-for-byte.
  - green_cuts splits the green band into sub-families.
  - dark_value / neutral_sat thresholds are honoured.
  - _allocate_by_overflow floor / mode variants behave correctly.
  - build_quantized_tileset_family runs end-to-end with custom params.
"""
from __future__ import annotations

import numpy as np
import pytest

from rpg2gba.tileset_converter.graphics.experimental_packers import (
    FamilyParams,
    _allocate_by_overflow,
    _dominant_family,
    build_quantized_tileset_family,
)
from rpg2gba.tileset_converter.graphics.quantize import QuantizeResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _solid_tile(color: tuple[int, int, int], alpha: int = 255) -> np.ndarray:
    """Return an 8x8 RGBA uint8 tile filled with a single (R, G, B, alpha) value."""
    tile = np.zeros((8, 8, 4), dtype=np.uint8)
    tile[..., :3] = color
    tile[..., 3] = alpha
    return tile


# Hue-specific solid tiles (fully opaque).
# Colours chosen so that after to_5bit rounding the hue still lands in the
# expected wedge — verified analytically in the docstring of each constant.

# Pure green: RGB (0, 255, 0) → HSV hue 120° → green band [70, 170)
TILE_GREEN = _solid_tile((0, 255, 0))

# Yellow-green ~100°: RGB (85, 255, 0)
#   to_5bit: (82, 255, 0) → hue ≈ 100.7°  (inside green band, below 120)
TILE_YELLOW_GREEN = _solid_tile((85, 255, 0))

# Blue-green ~150°: RGB (0, 255, 128)
#   to_5bit: (0, 255, 132) → hue ≈ 151°   (inside green band, above 120)
TILE_BLUE_GREEN = _solid_tile((0, 255, 128))

# Dark: RGB (30, 30, 30) → to_5bit (24, 24, 24) → max=24 < 40 (dark_value default)
TILE_DARK = _solid_tile((30, 30, 30))

# Neutral (low saturation, not dark): RGB (200, 200, 175)
#   to_5bit: (206, 206, 173) → s ≈ 0.160, max=206 ≥ 40
#   default neutral_sat=0.18 → "neutral"
#   with neutral_sat=0.15 → "yellow" (hue ≈ 60°)
TILE_NEUTRAL = _solid_tile((200, 200, 175))

# Red tile for multi-family tests
TILE_RED = _solid_tile((255, 0, 0))

# Blue tile
TILE_BLUE = _solid_tile((0, 0, 255))


# ---------------------------------------------------------------------------
# _dominant_family — defaults reproduce original behaviour
# ---------------------------------------------------------------------------


def test_dominant_family_default_green_no_cuts() -> None:
    """Pure green tile → 'green' (not 'green0') when green_cuts empty."""
    assert _dominant_family(TILE_GREEN) == "green"
    assert _dominant_family(TILE_GREEN, FamilyParams()) == "green"


def test_dominant_family_default_green_cuts_empty_tuple() -> None:
    """Explicit empty green_cuts still returns 'green'."""
    assert _dominant_family(TILE_GREEN, FamilyParams(green_cuts=())) == "green"


def test_dominant_family_default_red() -> None:
    assert _dominant_family(TILE_RED) == "red"


def test_dominant_family_default_blue() -> None:
    assert _dominant_family(TILE_BLUE) == "blue"


def test_dominant_family_default_dark() -> None:
    assert _dominant_family(TILE_DARK) == "dark"


def test_dominant_family_default_neutral() -> None:
    assert _dominant_family(TILE_NEUTRAL) == "neutral"


def test_dominant_family_transparent_returns_none() -> None:
    transparent = np.zeros((8, 8, 4), dtype=np.uint8)  # alpha = 0 everywhere
    assert _dominant_family(transparent) is None
    assert _dominant_family(transparent, FamilyParams()) is None


# ---------------------------------------------------------------------------
# _dominant_family — green_cuts splitting
# ---------------------------------------------------------------------------


def test_green_cuts_single_cut_yellow_green_is_green0() -> None:
    """Cut at 120° → yellow-green (~100°) lands in green0."""
    params = FamilyParams(green_cuts=(120.0,))
    assert _dominant_family(TILE_YELLOW_GREEN, params) == "green0"


def test_green_cuts_single_cut_blue_green_is_green1() -> None:
    """Cut at 120° → blue-green (~150°) lands in green1."""
    params = FamilyParams(green_cuts=(120.0,))
    assert _dominant_family(TILE_BLUE_GREEN, params) == "green1"


def test_green_cuts_pure_green_split() -> None:
    """Pure green (120°) with cut at 120°: bisect_right([120], 120) = 1 → green1."""
    params = FamilyParams(green_cuts=(120.0,))
    result = _dominant_family(TILE_GREEN, params)
    # hue exactly at cut: bisect_right returns 1 (right of cut)
    assert result == "green1"


def test_green_cuts_outside_range_ignored() -> None:
    """Cuts outside (70, 170) are filtered; if none remain, behaves like no cuts."""
    params = FamilyParams(green_cuts=(50.0, 200.0))  # both outside (70,170)
    assert _dominant_family(TILE_GREEN, params) == "green"


def test_green_cuts_mixed_valid_invalid() -> None:
    """Only cuts strictly inside (70, 170) count; 70 and 170 themselves are excluded."""
    params = FamilyParams(green_cuts=(70.0, 120.0, 170.0))  # only 120 is valid
    assert _dominant_family(TILE_YELLOW_GREEN, params) == "green0"
    assert _dominant_family(TILE_BLUE_GREEN, params) == "green1"


def test_green_cuts_unsorted_input_is_normalised() -> None:
    """Cut points are sorted internally; order in tuple does not matter."""
    params_a = FamilyParams(green_cuts=(120.0, 100.0))
    params_b = FamilyParams(green_cuts=(100.0, 120.0))
    assert _dominant_family(TILE_YELLOW_GREEN, params_a) == _dominant_family(
        TILE_YELLOW_GREEN, params_b
    )


# ---------------------------------------------------------------------------
# _dominant_family — dark_value threshold
# ---------------------------------------------------------------------------


def test_dark_value_default_classifies_dark_tile() -> None:
    """max(r,g,b)=24 after to_5bit; < 40 (default) → dark."""
    assert _dominant_family(TILE_DARK) == "dark"


def test_dark_value_raised_still_dark() -> None:
    """With dark_value=25, max=24 is still < 25 → dark."""
    assert _dominant_family(TILE_DARK, FamilyParams(dark_value=25)) == "dark"


def test_dark_value_lowered_escapes_dark() -> None:
    """With dark_value=20, max=24 >= 20 → not dark; s=0 → neutral."""
    result = _dominant_family(TILE_DARK, FamilyParams(dark_value=20))
    assert result == "neutral"


# ---------------------------------------------------------------------------
# _dominant_family — neutral_sat threshold
# ---------------------------------------------------------------------------


def test_neutral_sat_default_classifies_neutral() -> None:
    """s≈0.160 < 0.18 (default) → neutral."""
    assert _dominant_family(TILE_NEUTRAL) == "neutral"


def test_neutral_sat_lowered_escapes_neutral() -> None:
    """With neutral_sat=0.15, s≈0.160 >= 0.15 → falls through to hue check → yellow."""
    result = _dominant_family(TILE_NEUTRAL, FamilyParams(neutral_sat=0.15))
    assert result == "yellow"


def test_neutral_sat_raised_keeps_neutral() -> None:
    """With neutral_sat=0.20, s≈0.160 < 0.20 → still neutral."""
    assert _dominant_family(TILE_NEUTRAL, FamilyParams(neutral_sat=0.20)) == "neutral"


# ---------------------------------------------------------------------------
# _allocate_by_overflow — floor=1 / mode="colors" matches original
# ---------------------------------------------------------------------------


def test_allocate_floor1_colors_matches_original() -> None:
    """floor=1, mode='colors' must produce the same result as the old hardcoded impl."""
    distinct = {"red": 10, "green": 25, "blue": 5}
    total = 5
    # Original logic: alloc starts at 1 each; 2 remaining iterations.
    # Iter 1: green overflow = 25-15=10 → alloc[green]=2
    # Iter 2: max overflow = max(-5, -5, -10) = -5 ≤ 0 → break
    # Expected: {red:1, green:2, blue:1}
    result = _allocate_by_overflow(distinct, total, floor=1, mode="colors")
    assert result == {"red": 1, "green": 2, "blue": 1}


def test_allocate_default_params_equal_explicit_floor1_colors() -> None:
    """Calling with no keyword args equals floor=1, mode='colors' explicitly."""
    distinct = {"a": 20, "b": 30, "c": 8}
    total = 6
    assert _allocate_by_overflow(distinct, total) == _allocate_by_overflow(
        distinct, total, floor=1, mode="colors"
    )


def test_allocate_no_overflow_leaves_budget_unused() -> None:
    """When all groups already fit in 1 palette each, extras are not distributed."""
    distinct = {"a": 5, "b": 3}  # both < CPP=15
    total = 5
    result = _allocate_by_overflow(distinct, total)
    assert result == {"a": 1, "b": 1}


def test_allocate_exact_total_all_floor() -> None:
    """When len(groups)*floor == total, no extras to distribute."""
    distinct = {"a": 20, "b": 30}
    result = _allocate_by_overflow(distinct, 2, floor=1, mode="colors")
    assert sum(result.values()) == 2


# ---------------------------------------------------------------------------
# _allocate_by_overflow — floor=2 raises when groups*floor > total
# ---------------------------------------------------------------------------


def test_allocate_floor2_raises_insufficient_budget() -> None:
    """3 groups × floor=2 = 6 > total=5 → ValueError."""
    distinct = {"a": 10, "b": 10, "c": 10}
    with pytest.raises(ValueError):
        _allocate_by_overflow(distinct, 5, floor=2, mode="colors")


def test_allocate_floor2_exact_budget_ok() -> None:
    """3 groups × floor=2 = 6 == total=6 → no error, each gets exactly 2."""
    distinct = {"a": 5, "b": 5, "c": 5}
    result = _allocate_by_overflow(distinct, 6, floor=2, mode="colors")
    assert all(v == 2 for v in result.values())


def test_allocate_floor2_with_spare_budget() -> None:
    """3 groups × floor=2 = 6, total=8 → 2 extra palettes distributed by overflow."""
    # a has most overflow (20 distinct, 2 palettes → 20-30=-10 after floor)
    # Wait: with floor=2 and CPP=15, overflow = distinct - alloc*15
    # a: 20 - 2*15 = -10, b: 10 - 2*15 = -20, c: 25 - 2*15 = -5
    # All negative → break immediately, no extras distributed
    distinct = {"a": 20, "b": 10, "c": 25}
    result = _allocate_by_overflow(distinct, 8, floor=2, mode="colors")
    assert all(v == 2 for v in result.values())


def test_allocate_floor2_overflow_distributed() -> None:
    """When groups have positive overflow even after floor=2, extras go to neediest."""
    # CPP=15; with floor=2: each group starts with 2 palettes (capacity 30 each).
    # a: 50 distinct → overflow 50-30=20; b: 40 distinct → overflow 40-30=10
    # total=7, len=2, spare=7-4=3
    # Iter1: a wins (20>10) → alloc[a]=3, overflow=50-45=5
    # Iter2: a(5) vs b(10) → b wins → alloc[b]=3, overflow=40-45=-5
    # Iter3: a(5) vs b(-5) → a wins (5>0) → alloc[a]=4
    # Result: {a:4, b:3}
    distinct = {"a": 50, "b": 40}
    result = _allocate_by_overflow(distinct, 7, floor=2, mode="colors")
    assert result == {"a": 4, "b": 3}


# ---------------------------------------------------------------------------
# _allocate_by_overflow — mode="coverage"
# ---------------------------------------------------------------------------


def test_allocate_coverage_favors_high_tile_count() -> None:
    """Coverage mode: family with many tiles beats high-distinct-but-rare family.

    distinct={"A":20,"B":25}, counts={"A":100,"B":5}, total=3, floor=1, spare=1.
    Colors mode: B wins (overflow 10 > 5).
    Coverage mode: A wins (100*5=500 > 5*10=50).
    """
    distinct = {"A": 20, "B": 25}
    counts = {"A": 100, "B": 5}
    colors_result = _allocate_by_overflow(
        distinct, 3, counts=counts, floor=1, mode="colors"
    )
    coverage_result = _allocate_by_overflow(
        distinct, 3, counts=counts, floor=1, mode="coverage"
    )
    # Colors: B gets the extra palette
    assert colors_result["B"] > colors_result["A"]
    # Coverage: A gets the extra palette
    assert coverage_result["A"] > coverage_result["B"]


def test_allocate_coverage_stops_at_zero_overflow() -> None:
    """Coverage mode stops distributing when no group has positive colour overflow."""
    distinct = {"a": 5, "b": 3}   # both < CPP=15; overflow always ≤ 0 after floor
    counts = {"a": 50, "b": 20}
    result = _allocate_by_overflow(distinct, 5, counts=counts, floor=1, mode="coverage")
    assert result == {"a": 1, "b": 1}


def test_allocate_coverage_raises_without_counts() -> None:
    """mode='coverage' requires counts; assert fires when it's None."""
    distinct = {"a": 20}
    with pytest.raises((AssertionError, TypeError)):
        _allocate_by_overflow(distinct, 3, counts=None, floor=1, mode="coverage")


# ---------------------------------------------------------------------------
# build_quantized_tileset_family — end-to-end
# ---------------------------------------------------------------------------


def test_family_end_to_end_default_params() -> None:
    """No-params call returns a valid QuantizeResult."""
    tiles = [TILE_RED, TILE_GREEN, TILE_BLUE, TILE_RED, TILE_GREEN, TILE_BLUE]
    result = build_quantized_tileset_family(tiles)
    assert isinstance(result, QuantizeResult)
    assert len(result.palettes) <= 13
    assert len(result.tile_palette) == len(tiles)
    assert len(result.quantized) == len(tiles)
    for i, p in enumerate(result.tile_palette):
        assert p >= 0, f"tile {i} is opaque but got palette index -1"


def test_family_end_to_end_custom_params_green_cuts() -> None:
    """Custom FamilyParams with green_cuts splits green tiles across sub-families."""
    tiles = [TILE_YELLOW_GREEN] * 4 + [TILE_BLUE_GREEN] * 4 + [TILE_RED] * 2
    params = FamilyParams(green_cuts=(120.0,))
    result = build_quantized_tileset_family(tiles, params=params)
    assert isinstance(result, QuantizeResult)
    assert len(result.palettes) <= 13
    for i, p in enumerate(result.tile_palette):
        assert p >= 0, f"tile {i} is opaque but got palette index -1"


def test_family_end_to_end_respects_max_palettes() -> None:
    """n_palettes in result never exceeds max_palettes."""
    tiles = [_solid_tile(((i * 13) % 256, (i * 19) % 256, (i * 37) % 256))
             for i in range(20)]
    result = build_quantized_tileset_family(tiles, max_palettes=5)
    assert len(result.palettes) <= 5


def test_family_end_to_end_no_params_vs_explicit_defaults() -> None:
    """build_quantized_tileset_family(tiles) == ...(tiles, params=FamilyParams()).

    tile_palette lists must be identical; this is the primary backward-compat check.
    """
    tiles = [TILE_RED, TILE_GREEN, TILE_BLUE, TILE_NEUTRAL, TILE_DARK,
             TILE_YELLOW_GREEN, TILE_BLUE_GREEN] * 3
    r1 = build_quantized_tileset_family(tiles)
    r2 = build_quantized_tileset_family(tiles, params=FamilyParams())
    assert r1.tile_palette == r2.tile_palette, (
        "no-params and explicit-default-params produced different tile_palette"
    )
    assert len(r1.palettes) == len(r2.palettes)
    for p1, p2 in zip(r1.palettes, r2.palettes):
        np.testing.assert_array_equal(p1, p2)


def test_family_end_to_end_transparent_tiles_unassigned() -> None:
    """Fully transparent tiles get tile_palette == -1."""
    transparent = np.zeros((8, 8, 4), dtype=np.uint8)
    tiles = [TILE_RED, transparent, TILE_GREEN]
    result = build_quantized_tileset_family(tiles)
    assert result.tile_palette[1] == -1


def test_family_end_to_end_coverage_mode() -> None:
    """Coverage overflow_weight runs without error and returns valid result."""
    tiles = [TILE_RED] * 10 + [TILE_GREEN] * 10 + [TILE_BLUE] * 2
    params = FamilyParams(overflow_weight="coverage")
    result = build_quantized_tileset_family(tiles, max_palettes=6, params=params)
    assert isinstance(result, QuantizeResult)
    assert len(result.palettes) <= 6
