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


def test_autotile_frame_count_strip_multi_frame(tmp_path) -> None:
    path = tmp_path / "strip4.png"
    Image.new("RGBA", (128, 32), (0, 0, 0, 0)).save(path)
    assert at.autotile_frame_count(path) == 4


def test_autotile_frame_count_quad_multi_frame(tmp_path) -> None:
    path = tmp_path / "quad8.png"
    Image.new("RGBA", (768, 128), (0, 0, 0, 0)).save(path)
    assert at.autotile_frame_count(path) == 8


def test_autotile_frame_count_static_quad(tmp_path) -> None:
    path = tmp_path / "quad1.png"
    Image.new("RGBA", (96, 128), (0, 0, 0, 0)).save(path)
    assert at.autotile_frame_count(path) == 1


def test_autotile_frame_count_odd_size_is_static(tmp_path) -> None:
    # Matches the real Uranium outlier "PU-Grassy Tiles.png" (48x64) — must not raise.
    path = tmp_path / "odd.png"
    Image.new("RGBA", (48, 64), (0, 0, 0, 0)).save(path)
    assert at.autotile_frame_count(path) == 1


# ---------------------------------------------------------------------------
# flatten_autotile(frame=...) — animated autotile support
# ---------------------------------------------------------------------------


def test_flatten_strip_frame_selects_correct_tile() -> None:
    """A 3-frame strip: frame N is the solid (N*10,N*10,N*10) tile at x=N*32."""
    strip = Image.new("RGBA", (96, 32), (0, 0, 0, 0))
    for f in range(3):
        v = f * 10 + 1  # avoid 0 so frame 0 isn't accidentally "background"
        strip.paste(Image.new("RGBA", (32, 32), (v, v, v, 255)), (f * 32, 0))
    for f in range(3):
        tile = at.flatten_autotile(strip, 0, frame=f)
        v = f * 10 + 1
        assert tile.getpixel((1, 1)) == (v, v, v, 255)


def test_flatten_strip_frame_out_of_range_fails_loud() -> None:
    import pytest

    strip = Image.new("RGBA", (96, 32), (0, 0, 0, 0))
    with pytest.raises(ValueError, match="out of range"):
        at.flatten_autotile(strip, 0, frame=3)


def test_flatten_quad_frame_offsets_piece_crops() -> None:
    """A 2-frame quad template: frame 1's pieces are offset by FRAME_WIDTH (96px);
    piece ids in frame 1 encode (p+100) so the readback proves the right frame's
    pixels were sampled, not frame 0's."""
    frames = 2
    img = Image.new(
        "RGBA", (at.FRAME_WIDTH * frames, at.TEMPLATE_ROWS * at.PIECE_PX), (0, 0, 0, 0)
    )
    for f in range(frames):
        for row in range(at.TEMPLATE_ROWS):
            for col in range(at.TEMPLATE_COLS):
                p = row * at.TEMPLATE_COLS + col + 1
                v = p + (100 if f == 1 else 0)
                block = Image.new("RGBA", (at.PIECE_PX, at.PIECE_PX), (v, v, v, 255))
                img.paste(block, (f * at.FRAME_WIDTH + col * at.PIECE_PX, row * at.PIECE_PX))

    variant = 5
    tile0 = at.flatten_autotile(img, variant, frame=0)
    tile1 = at.flatten_autotile(img, variant, frame=1)
    expected = at.quad_pieces(variant)
    got0 = tuple(tile0.getpixel((i % 2 * 16 + 1, i // 2 * 16 + 1))[0] for i in range(4))
    got1 = tuple(tile1.getpixel((i % 2 * 16 + 1, i // 2 * 16 + 1))[0] for i in range(4))
    assert got0 == expected
    assert got1 == tuple(p + 100 for p in expected)


def test_flatten_quad_frame_out_of_range_fails_loud() -> None:
    import pytest

    template = _piece_template()  # single frame, 96 wide
    with pytest.raises(ValueError, match="out of range"):
        at.flatten_autotile(template, 0, frame=1)
