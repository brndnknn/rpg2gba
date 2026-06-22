"""Tests for tileset_converter.graphics.quantize — GBA palette quantization."""
from __future__ import annotations

import numpy as np

from rpg2gba.tileset_converter.graphics.quantize import (
    ALPHA_OPAQUE_THRESHOLD,
    COLORS_PER_PALETTE,
    SOLID_BODY_FRAC,
    build_quantized_tileset,
    classify_tile,
    resolve_alpha,
    to_5bit,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _solid_tile(color: tuple[int, int, int], alpha: int = 255) -> np.ndarray:
    """Return an 8x8 RGBA uint8 tile filled with a single (R,G,B,alpha) value."""
    tile = np.zeros((8, 8, 4), dtype=np.uint8)
    tile[..., :3] = color
    tile[..., 3] = alpha
    return tile


def _partial_tile(n_partial: int, partial_alpha: int = 100) -> np.ndarray:
    """8x8 tile: first n_partial pixels have partial alpha, rest are fully opaque."""
    tile = np.full((8, 8, 4), 200, dtype=np.uint8)
    tile[..., 3] = 255
    tile.reshape(-1, 4)[:n_partial, 3] = partial_alpha
    return tile


# ---------------------------------------------------------------------------
# to_5bit
# ---------------------------------------------------------------------------


def test_to_5bit_zero_maps_to_zero() -> None:
    arr = np.array([[[0, 0, 0]]], dtype=np.uint8)
    np.testing.assert_array_equal(to_5bit(arr), arr)


def test_to_5bit_255_maps_to_255() -> None:
    arr = np.array([[[255, 255, 255]]], dtype=np.uint8)
    np.testing.assert_array_equal(to_5bit(arr), arr)


def test_to_5bit_below_8_collapses_to_zero() -> None:
    # Values 0..7 all have q = c>>3 = 0 -> output 0.
    for c in range(1, 8):
        arr = np.array([[[c]]], dtype=np.uint8)
        result = to_5bit(arr)
        assert result[0, 0, 0] == 0, f"to_5bit({c}) should be 0, got {result[0, 0, 0]}"


def test_to_5bit_idempotent() -> None:
    rng = np.random.default_rng(42)
    arr = rng.integers(0, 256, (8, 8, 3), dtype=np.uint8)
    once = to_5bit(arr)
    twice = to_5bit(once)
    np.testing.assert_array_equal(once, twice)


def test_to_5bit_expansion_formula_hand_values() -> None:
    # q=4 (c in 32..39): (4<<3)|(4>>2) = 32|1 = 33
    assert to_5bit(np.array([[[32]]], dtype=np.uint8))[0, 0, 0] == 33
    # q=8 (c in 64..71): (8<<3)|(8>>2) = 64|2 = 66
    assert to_5bit(np.array([[[64]]], dtype=np.uint8))[0, 0, 0] == 66
    # q=16 (c in 128..135): (16<<3)|(16>>2) = 128|4 = 132
    assert to_5bit(np.array([[[128]]], dtype=np.uint8))[0, 0, 0] == 132


def test_to_5bit_same_shape_and_dtype() -> None:
    arr = np.zeros((4, 4, 3), dtype=np.uint8)
    out = to_5bit(arr)
    assert out.shape == arr.shape
    assert out.dtype == np.uint8


# ---------------------------------------------------------------------------
# classify_tile
# ---------------------------------------------------------------------------


def test_classify_tile_all_opaque_is_binary() -> None:
    alpha = np.full((8, 8), 255, dtype=np.uint8)
    assert classify_tile(alpha) == "binary"


def test_classify_tile_all_transparent_is_binary() -> None:
    # No partial pixels -> binary regardless of opaque count.
    alpha = np.zeros((8, 8), dtype=np.uint8)
    assert classify_tile(alpha) == "binary"


def test_classify_tile_object_with_edge_is_threshold() -> None:
    # An object-with-an-edge: a solid body (63 opaque px) plus a soft fringe (1
    # partial). Opaque fraction 63/64 >> SOLID_BODY_FRAC -> threshold (clean cutout).
    alpha = np.full((8, 8), 255, dtype=np.uint8)
    alpha[0, 0] = 100
    assert classify_tile(alpha) == "threshold"


def test_classify_tile_boundary_solid_body_vs_shadow() -> None:
    # Discriminator = solid-opaque-body fraction (SOLID_BODY_FRAC = 0.02; 0.02*64 =
    # 1.28). The rest of the tile is partial alpha (so it's not "binary").
    # 2 opaque pixels: 2/64 = 0.03125 >= 0.02 -> threshold (a real, if tiny, body).
    alpha = np.full((8, 8), 60, dtype=np.uint8)  # partial everywhere by default
    alpha.ravel()[:2] = 255
    assert classify_tile(alpha) == "threshold"

    # 1 opaque pixel: 1/64 = 0.0156 < 0.02 -> drop (essentially bodyless shadow).
    alpha2 = np.full((8, 8), 60, dtype=np.uint8)
    alpha2.ravel()[:1] = 255
    assert classify_tile(alpha2) == "drop"


def test_classify_tile_all_partial_is_drop() -> None:
    # A bodyless semi-transparent wash (0 fully-opaque pixels) -> drop (shadow).
    alpha = np.full((8, 8), 128, dtype=np.uint8)
    assert classify_tile(alpha) == "drop"


def test_classify_tile_solid_body_frac_constant() -> None:
    # Confirm the constant governing the threshold/drop split.
    assert SOLID_BODY_FRAC == 0.02


# ---------------------------------------------------------------------------
# resolve_alpha
# ---------------------------------------------------------------------------


def test_resolve_alpha_binary_returns_unchanged() -> None:
    tile = _solid_tile((100, 50, 200), alpha=255)
    result = resolve_alpha(tile)
    np.testing.assert_array_equal(result, tile)


def test_resolve_alpha_output_alpha_only_zero_or_255() -> None:
    # Threshold mode (1 partial pixel).
    tile = _partial_tile(n_partial=1)
    result = resolve_alpha(tile)
    unique_vals = set(np.unique(result[..., 3]).tolist())
    assert unique_vals.issubset({0, 255})


def test_resolve_alpha_threshold_geq_128_survives() -> None:
    tile = _partial_tile(n_partial=1, partial_alpha=128)  # exactly at threshold
    result = resolve_alpha(tile)
    assert result[0, 0, 3] == 255  # alpha==128 >= ALPHA_OPAQUE_THRESHOLD -> opaque


def test_resolve_alpha_threshold_below_128_drops() -> None:
    tile = _partial_tile(n_partial=1, partial_alpha=127)  # just below threshold
    result = resolve_alpha(tile)
    assert result[0, 0, 3] == 0  # alpha==127 < ALPHA_OPAQUE_THRESHOLD -> transparent


def test_resolve_alpha_threshold_constant_is_128() -> None:
    assert ALPHA_OPAQUE_THRESHOLD == 128


def test_resolve_alpha_drop_makes_shadow_transparent() -> None:
    # A bodyless shadow wash (all partial) -> drop: every partial pixel goes fully
    # transparent so the ground tile below shows through (no stipple checker).
    tile = np.zeros((8, 8, 4), dtype=np.uint8)
    tile[..., :3] = 80
    tile[..., 3] = 128  # all partial: 0 fully-opaque -> drop
    result = resolve_alpha(tile)
    assert classify_tile(tile[..., 3]) == "drop"
    assert (result[..., 3] == 0).all()


def test_resolve_alpha_drop_keeps_fully_opaque_pixels() -> None:
    # Drop mode keeps already-fully-opaque pixels (alpha==255) and drops every partial
    # one. A near-bodyless wash with one solid pixel -> only that pixel survives.
    tile = np.zeros((8, 8, 4), dtype=np.uint8)
    tile[..., :3] = 60
    tile[..., 3] = 128  # partial everywhere
    tile[1, 0, 3] = 255  # one fully-opaque pixel (1/64 < SOLID_BODY_FRAC -> drop)
    assert classify_tile(tile[..., 3]) == "drop"

    result = resolve_alpha(tile)
    assert result[1, 0, 3] == 255  # fully-opaque pixel kept
    assert int((result[..., 3] == 255).sum()) == 1  # everything else dropped


# ---------------------------------------------------------------------------
# build_quantized_tileset — structural invariants
# ---------------------------------------------------------------------------


def test_build_quantized_n_palettes_within_max() -> None:
    tiles = [_solid_tile(c) for c in [(255, 0, 0), (0, 255, 0), (0, 0, 255)] * 10]
    result = build_quantized_tileset(tiles, max_palettes=3)
    assert result.stats["n_palettes"] <= 3


def test_build_quantized_each_palette_within_color_limit() -> None:
    tiles = [_solid_tile((i * 12, i * 8, i * 4)) for i in range(20)]
    result = build_quantized_tileset(tiles)
    for pal in result.palettes:
        assert len(pal) <= COLORS_PER_PALETTE


def test_build_quantized_opaque_colors_subset_of_assigned_palette() -> None:
    tiles = [
        _solid_tile((200, 50, 50)),
        _solid_tile((50, 200, 50)),
        _solid_tile((50, 50, 200)),
        _solid_tile((200, 200, 50)),
        _solid_tile((50, 200, 200)),
    ]
    result = build_quantized_tileset(tiles)

    for i, (qt, pi) in enumerate(zip(result.quantized, result.tile_palette)):
        if pi == -1:
            continue
        opaque_mask = qt[..., 3] == 255
        if not opaque_mask.any():
            continue
        opaque_colors = np.unique(qt[..., :3][opaque_mask], axis=0)
        pal = result.palettes[pi]
        pal_set = {tuple(row.tolist()) for row in pal}
        for c in opaque_colors:
            assert tuple(c.tolist()) in pal_set, (
                f"tile {i}: quantized color {c.tolist()} not in palette {pal.tolist()}"
            )


def test_build_quantized_transparent_tile_index_minus_one() -> None:
    transparent = np.zeros((8, 8, 4), dtype=np.uint8)  # alpha == 0 everywhere
    solid = _solid_tile((100, 200, 100))
    result = build_quantized_tileset([transparent, solid])
    assert result.tile_palette[0] == -1


def test_build_quantized_transparent_tile_stays_transparent() -> None:
    transparent = np.zeros((8, 8, 4), dtype=np.uint8)
    solid = _solid_tile((80, 160, 80))
    result = build_quantized_tileset([transparent, solid])
    assert (result.quantized[0][..., 3] == 0).all()


def test_build_quantized_stats_keys_present() -> None:
    tiles = [_solid_tile((100, 100, 100))]
    result = build_quantized_tileset(tiles)
    for key in ("n_tiles", "n_palettes", "max_colors", "mean_shift_5bit",
                "max_shift_5bit", "p95_shift_5bit"):
        assert key in result.stats, f"missing stats key: {key}"


def test_build_quantized_n_tiles_stat_matches_input() -> None:
    tiles = [_solid_tile((i * 20, 0, 0)) for i in range(7)]
    result = build_quantized_tileset(tiles)
    assert result.stats["n_tiles"] == 7


# ---------------------------------------------------------------------------
# build_quantized_tileset — lossless case
# ---------------------------------------------------------------------------


def test_build_quantized_lossless_aligned_colors() -> None:
    # Colors already on the 5-bit grid: to_5bit is identity on these values.
    # 0..3 all have q>>3 = 0; 8 has q=1, 8|(1>>2)=8. All are fixed points.
    # With <=15 distinct colors and max_palettes=1, every tile lands in the
    # single palette exactly — mean colour shift must be 0.
    colors = [(0, 0, 0), (8, 0, 0), (0, 8, 0), (0, 0, 8)]
    tiles = [_solid_tile(c) for c in colors]
    result = build_quantized_tileset(tiles, max_palettes=1)
    assert result.stats["mean_shift_5bit"] == 0.0
    assert result.stats["n_palettes"] == 1


def test_build_quantized_lossless_more_colors_still_zero_shift() -> None:
    # 8 distinct 5-bit-aligned colors; all fit in one palette (8 < 15).
    colors = [(0, 0, 0), (8, 0, 0), (16, 0, 0), (24, 0, 0),
              (0, 8, 0), (0, 16, 0), (0, 24, 0), (0, 0, 8)]
    tiles = [_solid_tile(c) for c in colors]
    result = build_quantized_tileset(tiles, max_palettes=1)
    assert result.stats["mean_shift_5bit"] == 0.0


# ---------------------------------------------------------------------------
# build_quantized_tileset — determinism
# ---------------------------------------------------------------------------


def test_build_quantized_deterministic_stats() -> None:
    rng = np.random.default_rng(7)
    tiles = [rng.integers(0, 256, (8, 8, 4), dtype=np.uint8) for _ in range(20)]
    for t in tiles:
        t[..., 3] = 255  # fully opaque to avoid alpha randomness
    r1 = build_quantized_tileset(tiles)
    r2 = build_quantized_tileset(tiles)
    assert r1.stats == r2.stats


def test_build_quantized_deterministic_palettes() -> None:
    rng = np.random.default_rng(13)
    tiles = [rng.integers(0, 256, (8, 8, 4), dtype=np.uint8) for _ in range(15)]
    for t in tiles:
        t[..., 3] = 255
    r1 = build_quantized_tileset(tiles)
    r2 = build_quantized_tileset(tiles)
    assert len(r1.palettes) == len(r2.palettes)
    for p1, p2 in zip(r1.palettes, r2.palettes):
        np.testing.assert_array_equal(p1, p2)


# ---------------------------------------------------------------------------
# build_quantized_tileset — color_map
# ---------------------------------------------------------------------------


def test_color_map_length_equals_n_tiles() -> None:
    tiles = [_solid_tile(c) for c in [(255, 0, 0), (0, 255, 0), (0, 0, 255)]]
    result = build_quantized_tileset(tiles)
    assert len(result.color_map) == len(tiles)


def test_color_map_deterministic() -> None:
    rng = np.random.default_rng(17)
    tiles = [rng.integers(0, 256, (8, 8, 4), dtype=np.uint8) for _ in range(10)]
    for t in tiles:
        t[..., 3] = 255
    r1 = build_quantized_tileset(tiles)
    r2 = build_quantized_tileset(tiles)
    assert r1.color_map == r2.color_map


def test_color_map_transparent_tile_is_empty() -> None:
    transparent = np.zeros((8, 8, 4), dtype=np.uint8)  # alpha == 0 everywhere
    solid = _solid_tile((100, 200, 100))
    result = build_quantized_tileset([transparent, solid])
    assert result.color_map[0] == []


def test_color_map_finals_in_assigned_palette() -> None:
    tiles = [
        _solid_tile((200, 50, 50)),
        _solid_tile((50, 200, 50)),
        _solid_tile((50, 50, 200)),
    ]
    result = build_quantized_tileset(tiles)
    for i, (entry, pi) in enumerate(zip(result.color_map, result.tile_palette)):
        if pi == -1:
            assert entry == []
            continue
        pal_set = {tuple(int(v) for v in row) for row in result.palettes[pi]}
        for orig, final in entry:
            assert final in pal_set, (
                f"tile {i}: final_rgb8 {final} not in palette {result.palettes[pi].tolist()}"
            )


def test_color_map_no_snap_truncation_only() -> None:
    # A single tile with one off-grid colour: with only one tile there is no
    # palette sharing, so the only transformation is 8->5-bit truncation.
    # Invariant: final_rgb8 == to_5bit(orig_rgb8).
    color = (100, 150, 200)
    tile = _solid_tile(color)
    result = build_quantized_tileset([tile])
    assert len(result.color_map) == 1
    entry = result.color_map[0]
    assert len(entry) == 1  # single distinct colour
    orig, final = entry[0]
    expected = tuple(int(v) for v in to_5bit(np.array([list(color)], dtype=np.uint8))[0])
    assert final == expected, f"expected to_5bit({color})={expected}, got {final}"
