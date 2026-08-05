"""Map viewer pixel-equivalence classes (`_pixel_classes`) — the grouping behind
"Expand similar" (SLICE1_TODO #10 over-split fix).

Exercised with a stub rasterizer and synthetic single-tile columns; standing up a
full `_ensure_loaded` fixture is disproportionate for this pure helper (same
rationale as test_map_viewer_animated_overlay.py). The fixture builds
`metatile_imgs` exactly as `_ensure_loaded` does: frame-0 renders via
`_render_column` with no `n_frames`.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from map_viewer_common import _pixel_classes  # noqa: E402

from rpg2gba.tileset_converter.graphics.build_slice_tilesets import (  # noqa: E402
    _render_column,
)

RED = (255, 0, 0, 255)
BLUE = (0, 0, 255, 255)
GREEN = (0, 255, 0, 255)
YELLOW = (255, 255, 0, 255)
CYAN = (0, 255, 255, 255)


class _StubRaster:
    """render(tid[, frame]) -> solid 16x16 RGBA; per-tile frame colors given up
    front, so frame_count_for_tile is just the color-list length."""

    def __init__(self, colors: dict[int, list[tuple[int, int, int, int]]]):
        self._colors = colors

    def frame_count_for_tile(self, tile_id: int) -> int:
        return len(self._colors[tile_id])

    def render(self, tile_id: int, frame: int = 0) -> Image.Image:
        return Image.new("RGBA", (16, 16), self._colors[tile_id][frame])


def _fixture() -> tuple[list[tuple], list, _StubRaster, list[int]]:
    raster = _StubRaster({
        10: [RED],            # static
        11: [RED],            # static, pixel-identical to 10
        12: [BLUE],           # static, distinct pixels
        13: [RED],            # static, same pixels as 10 but priority 2 (top layer)
        20: [GREEN],          # static
        21: [GREEN, YELLOW],  # animated; frame 0 == tile 20's pixels
        22: [GREEN, CYAN],    # animated; frame 0 matches 21, frame 1 differs
        23: [GREEN, YELLOW],  # animated; every frame matches 21
        30: [RED] * 129,      # frame-count lcm past the fail-loud guard (128)
    })
    priorities = [0] * 400
    priorities[13] = 2
    colkeys: list[tuple] = sorted([
        (), ((0, 10),), ((0, 11),), ((0, 12),), ((0, 13),),
        ((0, 20),), ((0, 21),), ((0, 22),), ((0, 23),), ((0, 30),),
    ])
    metatile_imgs = [
        None if not ck else _render_column(ck, raster, priorities) for ck in colkeys
    ]
    return colkeys, metatile_imgs, raster, priorities


def test_pixel_identical_statics_merge() -> None:
    colkeys, imgs, raster, priorities = _fixture()
    pc = _pixel_classes(colkeys, imgs, raster, priorities)
    i10, i11 = colkeys.index(((0, 10),)), colkeys.index(((0, 11),))
    assert pc[i11] == pc[i10] == i10  # representative = smallest colkey idx


def test_distinct_pixels_stay_split() -> None:
    colkeys, imgs, raster, priorities = _fixture()
    pc = _pixel_classes(colkeys, imgs, raster, priorities)
    i10, i12 = colkeys.index(((0, 10),)), colkeys.index(((0, 12),))
    assert pc[i12] != pc[i10]


def test_layer_split_stays_distinct() -> None:
    # Same pixels, but priority 2 puts them on the TOP layer: not the same metatile.
    colkeys, imgs, raster, priorities = _fixture()
    pc = _pixel_classes(colkeys, imgs, raster, priorities)
    i10, i13 = colkeys.index(((0, 10),)), colkeys.index(((0, 13),))
    assert pc[i13] != pc[i10]


def test_animated_never_merges_with_static_lookalike() -> None:
    colkeys, imgs, raster, priorities = _fixture()
    pc = _pixel_classes(colkeys, imgs, raster, priorities)
    i20, i21 = colkeys.index(((0, 20),)), colkeys.index(((0, 21),))
    assert pc[i21] != pc[i20]


def test_animated_merge_requires_every_frame() -> None:
    colkeys, imgs, raster, priorities = _fixture()
    pc = _pixel_classes(colkeys, imgs, raster, priorities)
    i21 = colkeys.index(((0, 21),))
    i22 = colkeys.index(((0, 22),))
    i23 = colkeys.index(((0, 23),))
    assert pc[i22] != pc[i21]  # frame 1 differs -> split
    assert pc[i23] == pc[i21]  # all frames match -> merge


def test_empty_column_is_alone() -> None:
    colkeys, imgs, raster, priorities = _fixture()
    pc = _pixel_classes(colkeys, imgs, raster, priorities)
    i_empty = colkeys.index(())
    assert pc[i_empty] == i_empty
    assert pc.count(i_empty) == 1


def test_frame_guard_column_stays_ungrouped() -> None:
    # lcm 129 > MAX_COLUMN_FRAMES: unhashable, must NOT fold into the static RED
    # class off its frame-0 pixels.
    colkeys, imgs, raster, priorities = _fixture()
    pc = _pixel_classes(colkeys, imgs, raster, priorities)
    i30 = colkeys.index(((0, 30),))
    assert pc[i30] == i30
    assert pc.count(i30) == 1
