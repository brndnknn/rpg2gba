"""Tests for palette families pinned per seam component (synthetic data)."""

from __future__ import annotations

import numpy as np
import pytest

from rpg2gba.tileset_converter.connections import ConnectionRow
from rpg2gba.tileset_converter.graphics.emit import (
    LAYER_COVERED,
    MetatileImage,
    analyze_tileset_palettes,
)
from rpg2gba.tileset_converter.graphics.palette_families import (
    compute_component_palettes,
    make_pinned_quantizer,
    seam_components,
)
from rpg2gba.tileset_converter.graphics.quantize import to_5bit


def row(a: int, b: int) -> ConnectionRow:
    return ConnectionRow(a, "east", 0, b, "west", 0)


def c5(r: int, g: int, b: int) -> tuple[int, int, int]:
    out = to_5bit(np.array([[r, g, b]], np.uint8))[0]
    return int(out[0]), int(out[1]), int(out[2])


def pal(*colors: tuple[int, int, int]) -> np.ndarray:
    return np.array([c5(*c) for c in colors], np.uint8)


def tile(*colors: tuple[int, int, int]) -> np.ndarray:
    """8x8 RGBA tile striped with the given colours."""
    t = np.zeros((8, 8, 4), np.uint8)
    for k, c in enumerate(colors):
        t[k::len(colors), :, :3] = c
    t[..., 3] = 255
    return t


def mt(*quads: tuple[int, int, int]) -> MetatileImage:
    """Metatile whose 4 bottom quadrants are solid colours (cycled)."""
    bottom = np.zeros((16, 16, 4), np.uint8)
    for q in range(4):
        r, c = divmod(q, 2)
        bottom[r * 8:r * 8 + 8, c * 8:c * 8 + 8, :3] = quads[q % len(quads)]
        bottom[r * 8:r * 8 + 8, c * 8:c * 8 + 8, 3] = 255
    return MetatileImage(bottom, np.zeros((16, 16, 4), np.uint8), LAYER_COVERED, 0)


RED, RED2 = (200, 20, 20), (180, 40, 40)
GREEN, GREEN2 = (20, 200, 20), (40, 180, 40)
BLUE, BLUE2 = (20, 20, 200), (40, 40, 180)


# --- seam_components -------------------------------------------------------


def test_chain_is_one_component():
    comps = seam_components([row(3, 1), row(2, 3)])
    assert comps == {1: (1, 2, 3), 2: (1, 2, 3), 3: (1, 2, 3)}


def test_two_components_and_isolated_absent():
    comps = seam_components([row(1, 2), row(10, 11)], map_ids=[1, 2, 10, 11, 99])
    assert comps[1] == comps[2] == (1, 2)
    assert comps[10] == comps[11] == (10, 11)
    assert 99 not in comps


def test_map_ids_filter_drops_outside_endpoint():
    comps = seam_components([row(1, 2), row(2, 3)], map_ids=[1, 2])
    assert comps == {1: (1, 2), 2: (1, 2)}
    assert seam_components([row(1, 2)], map_ids=[1]) == {}


def test_component_tuple_sorted_and_order_independent():
    a = seam_components([row(5, 9), row(9, 2), row(2, 7)])
    b = seam_components([row(2, 7), row(9, 2), row(5, 9)])
    assert a == b
    assert a[9] == (2, 5, 7, 9)


# --- make_pinned_quantizer --------------------------------------------------


def test_pinned_picks_matching_palette():
    pals = [pal(RED, RED2), pal(GREEN, GREEN2), pal(BLUE, BLUE2)]
    q = make_pinned_quantizer(pals)
    res = q([tile(BLUE, BLUE2), tile(RED), tile(GREEN2, GREEN)], max_palettes=13)
    assert res.tile_palette == [2, 0, 1]
    assert len(res.palettes) == 3
    assert len(res.quantized) == len(res.color_map) == 3
    assert res.stats["n_palettes"] == 3
    # quantized pixels lie within the chosen palette
    used = {tuple(p) for p in res.quantized[0][..., :3].reshape(-1, 3)}
    assert used <= {tuple(int(v) for v in r) for r in pals[2]}
    assert res.color_map[0]


def test_pinned_empty_tile_is_minus_one():
    q = make_pinned_quantizer([pal(RED)])
    empty = np.zeros((8, 8, 4), np.uint8)
    res = q([empty, tile(RED)], max_palettes=13)
    assert res.tile_palette == [-1, 0]
    assert res.color_map[0] == []
    assert res.quantized[0][..., 3].max() == 0


def test_pinned_tie_goes_to_lowest_index():
    p = pal(RED)
    res = make_pinned_quantizer([p, p.copy()])([tile(RED)], max_palettes=13)
    assert res.tile_palette == [0]


def test_pinned_extra_colors_steer_choice():
    # Frame 0 fits palette 0 slightly better; the animation colour only fits palette 1.
    p0 = pal(RED, RED2)
    p1 = pal(RED, BLUE)
    t = tile(RED)
    q = make_pinned_quantizer([p0, p1])
    assert q([t], max_palettes=13).tile_palette == [0]
    extra = {0: to_5bit(np.array([BLUE], np.uint8))}
    assert q([t], max_palettes=13, extra_tile_colors=extra).tile_palette == [1]


def test_pinned_too_many_palettes_raises():
    many = [pal((i * 10, 0, 0)) for i in range(14)]
    with pytest.raises(ValueError):
        make_pinned_quantizer(many)
    q = make_pinned_quantizer(many[:5])
    with pytest.raises(ValueError):
        q([tile(RED)], max_palettes=4)


def test_pinned_through_emit_analysis():
    pals = [pal(RED, RED2), pal(GREEN, GREEN2), pal(BLUE, BLUE2)]
    metatiles = [mt(RED), mt(GREEN2), mt(BLUE, BLUE2)]
    analysis = analyze_tileset_palettes(metatiles, quantizer=make_pinned_quantizer(pals))
    assert len(analysis.palettes) == 3
    for got, want in zip(analysis.palettes, pals):
        assert got == [tuple(int(v) for v in r) for r in want]
    assert [m.quadrants[0].palette_index for m in analysis.metatiles] == [0, 1, 2]


# --- compute_component_palettes --------------------------------------------


def _lists() -> list[list[MetatileImage]]:
    return [
        [mt(RED), mt(RED2), mt(GREEN)],
        [mt(GREEN2), mt(BLUE), mt(BLUE2, RED)],
    ]


def test_compute_component_palettes_deterministic_and_bounded():
    a = compute_component_palettes(_lists(), max_palettes=4)
    b = compute_component_palettes(_lists(), max_palettes=4)
    assert 1 <= len(a) <= 4
    assert len(a) == len(b)
    for x, y in zip(a, b):
        assert np.array_equal(x, y)
        assert len(x) <= 15


def test_compute_component_palettes_empty():
    assert compute_component_palettes([[], []]) == []


def test_component_palettes_pin_both_maps_consistently():
    lists = _lists()
    pals = compute_component_palettes(lists, max_palettes=4)
    q = make_pinned_quantizer(pals)
    ana = [analyze_tileset_palettes(m, max_palettes=4, quantizer=q) for m in lists]
    # every map reports the shared palette set verbatim
    for a in ana:
        assert len(a.palettes) == len(pals)
        for got, want in zip(a.palettes, pals):
            assert got == [tuple(int(v) for v in r) for r in want]
