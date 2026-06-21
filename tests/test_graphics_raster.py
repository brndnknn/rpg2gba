"""Step 3 — Uranium tile -> 16x16 GBA-native tile."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from rpg2gba.tileset_converter.graphics import autotile as at
from rpg2gba.tileset_converter.graphics.raster import TileRasterizer, downscale_2x
from rpg2gba.tileset_converter.graphics.sources import TilesetSources


def test_downscale_2x_takes_top_left_of_each_block() -> None:
    # 4x4 where each pixel's R encodes (x,y); /2 must keep the top-left of each
    # 2x2 block: outputs at (0,0),(2,0),(0,2),(2,2).
    img = Image.new("RGBA", (4, 4))
    px = img.load()
    for y in range(4):
        for x in range(4):
            px[x, y] = (x * 10 + y, 0, 0, 255)
    out = downscale_2x(img)
    assert out.size == (2, 2)
    assert out.getpixel((0, 0))[0] == 0   # src (0,0) -> 0*10+0
    assert out.getpixel((1, 0))[0] == 20  # src (2,0) -> 2*10+0
    assert out.getpixel((0, 1))[0] == 2   # src (0,2) -> 0*10+2
    assert out.getpixel((1, 1))[0] == 22  # src (2,2) -> 2*10+2


def test_downscale_lossless_on_2x_upscale() -> None:
    # A 2x nearest upscale (every 2x2 block uniform) must /2 back exactly.
    small = Image.new("RGBA", (8, 8))
    sp = small.load()
    for y in range(8):
        for x in range(8):
            sp[x, y] = (x * 8, y * 8, 100, 255)
    up = small.resize((16, 16), Image.NEAREST)
    assert downscale_2x(up).tobytes() == small.tobytes()


def _atlas(tmp_path: Path, cols: int = 8, rows: int = 2) -> Path:
    """Static atlas: cell (col,row) is solid (col*16, row*16, 200)."""
    img = Image.new("RGBA", (cols * 32, rows * 32), (0, 0, 0, 0))
    for row in range(rows):
        for col in range(cols):
            img.paste(Image.new("RGBA", (32, 32), (col * 16, row * 16, 200, 255)),
                      (col * 32, row * 32))
    p = tmp_path / "atlas.png"
    img.save(p)
    return p


def _sources(tmp_path: Path, autotiles=(None,) * 7) -> TilesetSources:
    return TilesetSources(
        tileset_id=19,
        name="test",
        tileset_name="atlas",
        tileset_png=_atlas(tmp_path),
        autotiles=tuple(autotiles),
    )


def test_static_tile_crops_correct_cell(tmp_path: Path) -> None:
    r = TileRasterizer(_sources(tmp_path))
    # id 384 -> cell (0,0); id 393 -> idx 9 -> cell (1,1).
    t0 = r.render(384)
    assert t0.size == (16, 16)
    assert t0.getpixel((8, 8)) == (0, 0, 200, 255)
    t9 = r.render(393)
    assert t9.getpixel((8, 8)) == (16, 16, 200, 255)


def test_empty_tile_is_transparent(tmp_path: Path) -> None:
    r = TileRasterizer(_sources(tmp_path))
    t = r.render(0)
    assert t.size == (16, 16)
    assert t.getpixel((8, 8)) == (0, 0, 0, 0)


def test_static_out_of_bounds_fails_loud(tmp_path: Path) -> None:
    r = TileRasterizer(_sources(tmp_path))  # atlas has 8x2 = 16 cells, ids 384..399
    with pytest.raises(ValueError, match="outside"):
        r.render(400)


def test_render_is_cached_and_idempotent(tmp_path: Path) -> None:
    r = TileRasterizer(_sources(tmp_path))
    a = r.render(384)
    b = r.render(384)
    assert a is b  # same cached object
    assert a.tobytes() == r.render(384).tobytes()


def _piece_template_png(tmp_path: Path) -> Path:
    img = Image.new("RGBA", (at.FRAME_WIDTH, at.TEMPLATE_ROWS * at.PIECE_PX), (0, 0, 0, 0))
    for row in range(at.TEMPLATE_ROWS):
        for col in range(at.TEMPLATE_COLS):
            p = row * at.TEMPLATE_COLS + col + 1
            img.paste(Image.new("RGBA", (16, 16), (p, p, p, 255)), (col * 16, row * 16))
    path = tmp_path / "autotile.png"
    img.save(path)
    return path


def test_autotile_tile_flattens_then_downscales(tmp_path: Path) -> None:
    tpl = _piece_template_png(tmp_path)
    r = TileRasterizer(_sources(tmp_path, autotiles=(tpl,) + (None,) * 6))
    variant = 5
    tile = r.render(48 + variant)  # slot 0, variant 5
    assert tile.size == (16, 16)
    # After /2 each 16x16 quadrant becomes 8x8; quadrant i top-left at (i%2*8, i//2*8).
    expected = at.quad_pieces(variant)
    got = tuple(tile.getpixel((i % 2 * 8, i // 2 * 8))[0] for i in range(4))
    assert got == expected


def test_autotile_empty_slot_is_transparent(tmp_path: Path) -> None:
    r = TileRasterizer(_sources(tmp_path, autotiles=(None,) * 7))
    tile = r.render(370)  # slot 6 (empty) -> Map048's decorative base-336 case
    assert tile.size == (16, 16)
    assert tile.getpixel((8, 8)) == (0, 0, 0, 0)
