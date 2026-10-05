"""Per-map metatile atlas: every cell is pixel-identical to the per-metatile PNG."""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import map_viewer_common as mvc  # noqa: E402

MAP_ID = 33
LAYERS = ("bottom", "top", "post_bottom", "post_top")


@pytest.fixture(scope="module")
def data() -> dict:
    try:
        return mvc.build_map_data(MAP_ID)
    except (FileNotFoundError, KeyError, OSError) as exc:
        pytest.skip(f"map {MAP_ID} build output absent: {exc}")


def _open(png: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png)).convert("RGBA")


def test_geometry_consistent(data: dict) -> None:
    a = data["meta"]["atlas"]
    assert a == {"cols": mvc.ATLAS_COLS, "cell": mvc.ATLAS_CELL_PX, "count": a["count"]}
    assert a["count"] == len(data["colkeys_list"])
    rows = max(1, -(-a["count"] // a["cols"]))
    for layer in LAYERS:
        img = _open(mvc.render_atlas_png(MAP_ID, layer))
        assert img.size == (a["cols"] * a["cell"], rows * a["cell"])


@pytest.mark.parametrize("layer", LAYERS)
def test_atlas_cells_match_metatile_pngs(data: dict, layer: str) -> None:
    a = data["meta"]["atlas"]
    n, cols, cp = a["count"], a["cols"], a["cell"]
    atlas = _open(mvc.render_atlas_png(MAP_ID, layer))
    for idx in sorted({0, n // 2, n - 1}):
        x, y = (idx % cols) * cp, (idx // cols) * cp
        got = atlas.crop((x, y, x + cp, y + cp))
        want = _open(mvc.render_metatile_png(MAP_ID, idx, layer))
        assert got.tobytes() == want.tobytes(), f"{layer} idx {idx}"


def test_atlas_memoized_and_cleared_by_quantize_setter(data: dict) -> None:
    first = mvc.render_atlas_png(MAP_ID, "bottom")
    assert mvc.render_atlas_png(MAP_ID, "bottom") is first
    assert mvc._atlas_png_cache
    params, max_pals = mvc.current_quantize_state()
    mvc.set_quantize_params(params, max_pals)
    assert not mvc._atlas_png_cache
    assert mvc.render_atlas_png(MAP_ID, "bottom") == first  # raw layer unaffected by knobs
