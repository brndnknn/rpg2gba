"""render_map_png: whole-map composite equals the per-cell bottom+top metatile composite."""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import map_viewer_common as mvc  # noqa: E402

MAP_ID = 33


@pytest.fixture(scope="module")
def data() -> dict:
    try:
        return mvc.build_map_data(MAP_ID)
    except (FileNotFoundError, KeyError, OSError) as exc:
        pytest.skip(f"map {MAP_ID} build output absent: {exc}")


def test_map_png_size_and_cells(data: dict) -> None:
    meta = data["meta"]
    w, h = meta["xsize"], meta["ysize"]
    png = mvc.render_map_png(MAP_ID)
    img = Image.open(io.BytesIO(png))
    img.load()
    assert img.size == (w * 16, h * 16)
    img = img.convert("RGBA")
    for x, y in [(0, 0), (w // 2, h // 2), (w - 1, h - 1)]:
        cell = data["cells"][y * w + x]
        idx = cell["colkey_idx"]
        bot = Image.open(io.BytesIO(mvc.render_metatile_png(MAP_ID, idx, "bottom"))).convert("RGBA")
        top = Image.open(io.BytesIO(mvc.render_metatile_png(MAP_ID, idx, "top"))).convert("RGBA")
        want = Image.alpha_composite(bot, top)
        got = img.crop((x * 16, y * 16, x * 16 + 16, y * 16 + 16))
        assert got.tobytes() == want.tobytes()


def test_map_png_memoized(data: dict) -> None:
    assert mvc.render_map_png(MAP_ID) is mvc.render_map_png(MAP_ID)
