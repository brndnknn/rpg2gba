"""Step 2 — RMXP autotile flattener."""
from __future__ import annotations

from PIL import Image

from rpg2gba.tileset_converter.graphics import autotile as at


def _piece_template() -> Image.Image:
    """A 96x128 template where each 16x16 piece is solid (p, p, p) for its 1-based
    piece id p = row*6 + col + 1 — so a quadrant's colour reveals which piece filled it."""
    img = Image.new("RGBA", (at.FRAME_WIDTH, at.TEMPLATE_ROWS * at.PIECE_PX), (0, 0, 0, 0))
    for row in range(at.TEMPLATE_ROWS):
        for col in range(at.TEMPLATE_COLS):
            p = row * at.TEMPLATE_COLS + col + 1
            block = Image.new("RGBA", (at.PIECE_PX, at.PIECE_PX), (p, p, p, 255))
            img.paste(block, (col * at.PIECE_PX, row * at.PIECE_PX))
    return img


def _quadrant_piece_ids(tile: Image.Image) -> tuple[int, int, int, int]:
    """Read back the piece id encoded in each quadrant's colour (R channel)."""
    return tuple(  # type: ignore[return-value]
        tile.getpixel((ox + 1, oy + 1))[0] for ox, oy in at._QUADRANT_OFFSETS
    )


def test_table_shape() -> None:
    assert len(at.AUTOTILE_TABLE) == 6
    assert all(len(row) == 8 for row in at.AUTOTILE_TABLE)
    flat = [q for row in at.AUTOTILE_TABLE for q in row]
    assert len(flat) == 48
    assert all(len(q) == 4 and all(1 <= p <= 48 for p in q) for q in flat)


def test_quad_pieces_endpoints() -> None:
    assert at.quad_pieces(0) == (27, 28, 33, 34)
    assert at.quad_pieces(47) == (1, 2, 7, 8)


def test_flatten_picks_table_pieces() -> None:
    template = _piece_template()
    for variant in (0, 1, 20, 34, 47):
        tile = at.flatten_autotile(template, variant)
        assert tile.size == (at.RMXP_TILE_PX, at.RMXP_TILE_PX)
        assert _quadrant_piece_ids(tile) == at.quad_pieces(variant)


def test_strip_autotile_ignores_variant() -> None:
    # height-32 animation strip: 3 frames; frame 0 is solid (50,50,50).
    strip = Image.new("RGBA", (96, 32), (9, 9, 9, 255))
    strip.paste(Image.new("RGBA", (32, 32), (50, 50, 50, 255)), (0, 0))
    for variant in (0, 17, 47):
        tile = at.flatten_autotile(strip, variant)
        assert tile.size == (32, 32)
        assert tile.getpixel((1, 1)) == (50, 50, 50, 255)
        assert tile.getpixel((30, 30)) == (50, 50, 50, 255)  # whole frame-0 tile


def test_too_small_template_fails_loud() -> None:
    import pytest

    tiny = Image.new("RGBA", (48, 64), (0, 0, 0, 0))
    with pytest.raises(ValueError, match="too small"):
        at.flatten_autotile(tiny, 0)
