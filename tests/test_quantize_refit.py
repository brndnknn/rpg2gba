"""refit_tiles (intermission I2b): after packing, a tile moves to the palette that
draws the fewest of its pixels visibly off; palettes never change and no tile gets
more visibly-off pixels."""
from __future__ import annotations

from functools import partial

import numpy as np

from rpg2gba.tileset_converter.graphics import shared_palettes as sp
from rpg2gba.tileset_converter.graphics.quantize import (
    REFIT_MAX_SHIFT,
    FamilyParams,
    QuantizeResult,
    build_quantized_tileset_family,
    quantize_tile_to_palette,
    refit_tiles,
    to_5bit,
)

TAN = to_5bit(np.array([[192, 144, 104], [176, 128, 88], [160, 112, 80]], np.uint8))
PINK = to_5bit(np.array([[200, 128, 128], [232, 96, 96], [248, 160, 160]], np.uint8))


def _tile(colors: np.ndarray) -> np.ndarray:
    rgb = colors[np.arange(64) % len(colors)].reshape(8, 8, 3)
    return np.concatenate([rgb, np.full((8, 8, 1), 255, np.uint8)], axis=2)


def _result(tiles: list[np.ndarray], palettes: list[np.ndarray], assign: list[int]) -> QuantizeResult:
    return QuantizeResult(
        palettes=palettes,
        tile_palette=list(assign),
        quantized=[quantize_tile_to_palette(t, palettes[p]) for t, p in zip(tiles, assign)],
        color_map=[[] for _ in tiles],
    )


def test_misfiled_tile_moves_to_the_closer_palette():
    tiles = [_tile(TAN)]
    r = refit_tiles(tiles, _result(tiles, [PINK, TAN], [0]))
    assert r.tile_palette == [1]
    assert np.array_equal(r.quantized[0], tiles[0])
    assert r.palettes[0] is not None and np.array_equal(r.palettes[0], PINK)  # palettes untouched
    assert r.stats["refit_moved"] == 1
    assert r.color_map[0] and all(o == f for o, f in r.color_map[0])


def test_well_placed_tile_stays_and_ties_keep_the_original():
    tiles = [_tile(TAN), _tile(TAN)]
    r = refit_tiles(tiles, _result(tiles, [TAN, TAN.copy()], [0, 1]))
    assert r.tile_palette == [0, 1]
    assert r.stats["refit_moved"] == 0


def test_only_movable_tiles_move():
    tiles = [_tile(TAN), _tile(TAN)]
    r = refit_tiles(tiles, _result(tiles, [PINK, TAN], [0, 0]), movable=[1])
    assert r.tile_palette == [0, 1]


def test_animation_frames_count_against_a_move():
    """A palette that fits frame 0 better but loses the later frames' colours is not taken."""
    tiles = [_tile(TAN[:1])]
    both = np.concatenate([TAN[:1], PINK])
    extra = {0: PINK}
    r = refit_tiles(tiles, _result(tiles, [both, TAN], [0]), extra_tile_colors=extra)
    assert r.tile_palette == [0]


def test_empty_tiles_are_skipped():
    tiles = [np.zeros((8, 8, 4), np.uint8)]
    r = _result(tiles, [PINK, TAN], [0])
    r.tile_palette[0] = -1
    assert refit_tiles(tiles, r).tile_palette == [-1]


def test_main_colour_shift_loses_to_a_few_outliers():
    """Route 2's ledge: its packed palette draws the main brown one step off and a few
    outliers far off. Another palette has lower squared error but shifts every brown
    pixel two steps (grey). The ledge must stay put."""
    main = to_5bit(np.array([[132, 90, 74]], np.uint8))
    odd = to_5bit(np.array([[40, 200, 40]], np.uint8))
    tile = _tile(np.concatenate([np.repeat(main, 60, 0), np.repeat(odd, 4, 0)]))
    near_main = to_5bit(np.array([[132, 99, 74], [200, 60, 200]], np.uint8))   # 1 step off; outliers far
    greyer = to_5bit(np.array([[132, 107, 90], [40, 200, 40]], np.uint8))      # 2 steps off; outliers exact
    tiles = [tile]
    r = refit_tiles(tiles, _result(tiles, [near_main, greyer], [0]))
    assert r.tile_palette == [0]


def test_shared_quantizer_refit_never_adds_visibly_off_pixels():
    """End to end through the ROM-style wrapper: no tile has more visibly-off pixels
    after the refit, and pinned rock tiles keep the shared rock palette."""
    rng = np.random.default_rng(7)
    tiles = [_tile(sp.ROCK_V1[rng.choice(15, 4, replace=False)]) for _ in range(8)]
    tiles += [_tile(TAN), _tile(PINK), _tile(np.concatenate([TAN[:1], PINK[1:]]))]
    base = partial(build_quantized_tileset_family, params=FamilyParams(reduction="ward"))
    before = sp.make_shared_quantizer(base)(tiles, max_palettes=4)
    after = sp.make_shared_quantizer(base, refit=True)(tiles, max_palettes=4)

    def err(r: QuantizeResult, i: int) -> int:
        a = to_5bit(tiles[i][..., :3]).astype(np.int32) >> 3
        b = r.quantized[i][..., :3].astype(np.int32) >> 3
        return int((np.abs(a - b).max(2) > REFIT_MAX_SHIFT).sum())

    assert [len(p) for p in after.palettes] == [len(p) for p in before.palettes]
    for i in range(len(tiles)):
        assert err(after, i) <= err(before, i)
    assert after.tile_palette[:8] == [0] * 8


def test_stand_in_is_scored_against_the_art_it_replaced():
    """A merged stand-in a hue step off its original: drawn in its own best palette it
    would match itself and miss the original; the refit keeps the palette that draws
    the original right."""
    original = to_5bit(np.array([[132, 90, 74]], np.uint8))
    stand_in = to_5bit(np.array([[123, 107, 82]], np.uint8))
    tile, ref = _tile(stand_in), _tile(original)
    brown = to_5bit(np.array([[132, 99, 74]], np.uint8))   # 1 step off the original
    grey = to_5bit(np.array([[123, 107, 82]], np.uint8))   # exact for the stand-in
    tiles = [tile]
    kept = refit_tiles(tiles, _result(tiles, [brown, grey], [0]), reference_tiles={0: [ref]})
    assert kept.tile_palette == [0]
    moved = refit_tiles(tiles, _result(tiles, [brown, grey], [0]))
    assert moved.tile_palette == [1]  # without the reference, it would chase itself


def test_fewer_bad_pixels_but_more_error_stays():
    """Moki's fence: the other palette has fewer visibly-off pixels but more squared
    error. No move unless both improve (a bad-pixel count alone moved it to green)."""
    a = to_5bit(np.array([[99, 99, 99]], np.uint8))
    b = to_5bit(np.array([[222, 222, 214]], np.uint8))
    tile = _tile(np.concatenate([np.repeat(a, 10, 0), np.repeat(b, 54, 0)]))
    near = np.concatenate([to_5bit(np.array([[115, 99, 99]], np.uint8)), b])   # 10 px 2 steps off
    far = np.concatenate([a, to_5bit(np.array([[231, 231, 222]], np.uint8))])  # 54 px 1 step off
    tiles = [tile]
    r = refit_tiles(tiles, _result(tiles, [near, far], [0]))
    assert r.tile_palette == [0]
