"""The screen check's pure parts: ring-buffer geometry and expected tilemap words."""
from rpg2gba.playtest.screen_check import (
    LAYER_COVERED,
    LAYER_NORMAL,
    LAYER_SPLIT,
    STOCK_NORMAL_BG3_WORD,
    cell_metatile,
    expected_layer_words,
    serpentine,
    word_tile,
)


def test_cell_metatile_origin_is_camera_offset():
    # The cell at the camera tile offset is the top-left quadrant of metatile pos.
    assert cell_metatile(6, 10, 6, 10, 20, 30) == (20, 30, 0)
    assert cell_metatile(7, 11, 6, 10, 20, 30) == (20, 30, 3)


def test_cell_metatile_wraps_the_ring_buffer():
    # Cell 0 sits 32 - 30 = 2 tiles past an offset of 30: the next metatile over.
    assert cell_metatile(0, 0, 30, 30, 5, 5) == (6, 6, 0)
    assert cell_metatile(27, 0, 30, 0, 5, 5) == (5 + 14, 5, 1)


def test_cell_metatile_skips_the_unmaintained_strip():
    # Buffer tiles 30-31 past the camera offset are never redrawn while walking.
    assert cell_metatile(28, 0, 30, 0, 5, 5) is None
    assert cell_metatile(0, 30, 0, 0, 5, 5) is None


def test_expected_words_per_layer_type():
    words = [10, 11, 12, 13, 20, 21, 22, 23]
    assert expected_layer_words(LAYER_SPLIT, words, 1, False) == {3: 11, 2: 0, 1: 21}
    assert expected_layer_words(LAYER_COVERED, words, 2, False) == {3: 12, 2: 22, 1: 0}
    assert expected_layer_words(LAYER_NORMAL, words, 3, False) == {3: STOCK_NORMAL_BG3_WORD, 2: 13, 1: 23}
    # Streamed maps draw tile 0 under NORMAL metatiles (slot 0x14 is a streamed slot).
    assert expected_layer_words(LAYER_NORMAL, words, 0, True)[3] == 0
    assert expected_layer_words(7, words, 0, False) is None


def test_word_tile():
    assert word_tile((1500 << 16) | 0x5C00, True) == 1500
    assert word_tile(0x5C00 | 700, False) == 700


def test_serpentine_covers_first_and_last_rows():
    pts = serpentine(5, 4, 2)
    assert pts == [(0, 0), (4, 0), (4, 2), (0, 2), (0, 3), (4, 3)]
