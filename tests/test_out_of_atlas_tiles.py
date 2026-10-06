"""Out-of-atlas static tile ids (stale RMXP data) — the shared `in_atlas` /
`column_in_atlas` predicate (raster.py), `layout.mask_out_of_atlas` (the single
masking function), and the map viewer's use of both.

~18 of 199 Uranium maps carry a handful of stale static tile ids, each on ONE
layer of a cell, that point past the bottom of their tileset image; RMXP draws
that one layer as nothing while the cell's other layers draw normally (each
RMXP layer composites independently). The correct fix is therefore to zero
just the bad layer (`layout.mask_out_of_atlas`), not drop the whole cell — the
build pipeline (`build_slice_tilesets.py`) and the layout converter
(`layout.convert_layout`) both mask before any column key is computed, so a
column key can never carry an out-of-atlas id past that point; the leftover
`column_in_atlas` checks downstream of masking are fail-loud backstops (a hit
means a masking site was missed), not a real filter any more. This file covers
the mask function itself, that build/layout agreement, and the map viewer's
parallel handling (`_ensure_loaded` / `build_map_data` / `render_tile_png` in
`scripts/map_viewer_common.py`), which must reach the same masked-not-dropped
outcome without ever calling the fail-loud `TileRasterizer.render` on an
out-of-atlas id.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import map_viewer_common as mvc  # noqa: E402

from rpg2gba.tileset_converter.graphics import sources as src  # noqa: E402
from rpg2gba.tileset_converter.graphics.build_slice_tilesets import (  # noqa: E402
    column_keys_for_maps,
)
from rpg2gba.tileset_converter.graphics.raster import (  # noqa: E402
    TileRasterizer,
    column_in_atlas,
)
from rpg2gba.tileset_converter.graphics.sources import TilesetSources  # noqa: E402
from rpg2gba.tileset_converter.layout import (  # noqa: E402
    TileGrid,
    column_key,
    convert_layout,
    mask_out_of_atlas,
)
from rpg2gba.tileset_converter.tile_map import (  # noqa: E402
    METATILE_ID_MASK,
    Bucket,
    TileMap,
    TilesetChoice,
)

# ---------------------------------------------------------------------------
# 1. TileRasterizer.in_atlas / column_in_atlas — synthetic 8x2 atlas (same
#    shape as test_graphics_raster.py's `_atlas`: static ids 384..399 valid).
# ---------------------------------------------------------------------------


def _atlas(tmp_path: Path, cols: int = 8, rows: int = 2) -> Path:
    """Static atlas: cell (col,row) is solid (col*16, row*16, 200) — opaque, so
    the quantizer (a full build_map_data run needs it) has real colors to work
    with (matches tests/test_graphics_raster.py's `_atlas`)."""
    img = Image.new("RGBA", (cols * 32, rows * 32), (0, 0, 0, 0))
    for row in range(rows):
        for col in range(cols):
            img.paste(Image.new("RGBA", (32, 32), (col * 16, row * 16, 200, 255)),
                      (col * 32, row * 32))
    p = tmp_path / "atlas.png"
    img.save(p)
    return p


def _sources(tmp_path: Path) -> TilesetSources:
    return TilesetSources(
        tileset_id=19,
        name="test",
        tileset_name="atlas",
        tileset_png=_atlas(tmp_path),
        autotiles=(None,) * 7,
    )


def test_in_atlas_true_for_empty_and_autotile_ids(tmp_path: Path) -> None:
    r = TileRasterizer(_sources(tmp_path))
    assert r.in_atlas(0)
    assert r.in_atlas(48)     # autotile, always < STATIC_BASE
    assert r.in_atlas(383)    # top of autotile range


def test_in_atlas_true_for_in_range_static_id(tmp_path: Path) -> None:
    r = TileRasterizer(_sources(tmp_path))
    assert r.in_atlas(384)          # first static cell
    assert r.in_atlas(399)          # last valid cell (8x2 atlas)


def test_in_atlas_false_past_atlas_bounds(tmp_path: Path) -> None:
    r = TileRasterizer(_sources(tmp_path))
    assert not r.in_atlas(400)      # one past the last valid cell
    assert not r.in_atlas(5000)     # far past, like the real Uranium garbage ids


def test_in_atlas_never_calls_render(tmp_path: Path) -> None:
    """in_atlas must be a pure bounds check: calling it on an out-of-range id
    must not raise the fail-loud ValueError `render`/`_render_static` would."""
    r = TileRasterizer(_sources(tmp_path))
    assert r.in_atlas(9999) is False
    with pytest.raises(ValueError, match="outside"):
        r.render(9999)  # the renderer itself is untouched: still fails loud


def test_column_in_atlas_true_when_every_tile_in_range(tmp_path: Path) -> None:
    r = TileRasterizer(_sources(tmp_path))
    key = ((0, 48), (1, 384))
    assert column_in_atlas(r, key)


def test_column_in_atlas_false_when_any_tile_out_of_range(tmp_path: Path) -> None:
    r = TileRasterizer(_sources(tmp_path))
    key = ((0, 48), (1, 5000))
    assert not column_in_atlas(r, key)


def test_column_in_atlas_defaults_true_for_rasterizer_without_in_atlas() -> None:
    """A synthetic test rasterizer with no real atlas bounds (e.g. a bare stub
    used elsewhere in the test suite) has nothing to drop."""

    class _Stub:
        pass

    assert column_in_atlas(_Stub(), ((0, 99999),))


# ---------------------------------------------------------------------------
# 1b. `layout.mask_out_of_atlas` — the single masking function.
# ---------------------------------------------------------------------------


def test_mask_out_of_atlas_zeroes_only_the_bad_layer() -> None:
    """A cell with a good z0 and an out-of-atlas z1: only z1 is zeroed."""
    grid = TileGrid(1, 1, 2, [384, 5000])
    masked, changes = mask_out_of_atlas(grid, max_static_tile_id=399)
    assert masked.tile_at(0, 0, 0) == 384
    assert masked.tile_at(0, 0, 1) == 0
    assert changes == [(0, 0, 1, 5000)]


def test_mask_out_of_atlas_does_not_mutate_input() -> None:
    grid = TileGrid(1, 1, 2, [384, 5000])
    mask_out_of_atlas(grid, max_static_tile_id=399)
    assert grid.tile_at(0, 0, 1) == 5000  # caller's grid is untouched


def test_mask_out_of_atlas_idempotent() -> None:
    grid = TileGrid(1, 1, 2, [384, 5000])
    once, _ = mask_out_of_atlas(grid, max_static_tile_id=399)
    twice, changes2 = mask_out_of_atlas(once, max_static_tile_id=399)
    assert twice.data == once.data
    assert changes2 == []


def test_mask_out_of_atlas_leaves_autotiles_and_empty_alone() -> None:
    """Autotile ids (< STATIC_BASE) and 0 (already empty) are never in the
    static range this check concerns itself with."""
    grid = TileGrid(1, 1, 2, [48, 0])
    masked, changes = mask_out_of_atlas(grid, max_static_tile_id=399)
    assert masked.data == [48, 0]
    assert changes == []


def test_mask_out_of_atlas_in_range_static_id_untouched() -> None:
    grid = TileGrid(1, 1, 1, [399])
    masked, changes = mask_out_of_atlas(grid, max_static_tile_id=399)
    assert masked.data == [399]
    assert changes == []


# ---------------------------------------------------------------------------
# 1c. Build (`column_keys_for_maps`) and layout (`convert_layout`) must agree
#     on the column key a masked mixed cell resolves to.
# ---------------------------------------------------------------------------


def test_column_keys_for_maps_masks_before_computing_keys() -> None:
    """The tileset-build path: a cell with a good z0 (10) and an out-of-atlas
    z1 (5000, past bound 399) must contribute only the good layer's key —
    never the whole cell dropped, never the garbage id leaking into a key."""
    map_json = {
        "tiles": {"xsize": 1, "ysize": 1, "zsize": 3, "data": [10, 5000, 0]},
    }
    keys = column_keys_for_maps([(1, map_json)], max_static_tile_id=399)
    assert keys == [((0, 10),)]


_LSYNTH = 1008


def _layout_grid(width: int, height: int, layer0, layer1=None, layer2=None) -> TileGrid:
    cells = width * height
    z1 = list(layer1) if layer1 is not None else [0] * cells
    z2 = list(layer2) if layer2 is not None else [0] * cells
    return TileGrid(width, height, 3, list(layer0) + z1 + z2)


def test_convert_layout_masks_out_of_atlas_layer_before_collision_and_visual() -> None:
    """The layout path: same mixed cell as the build-path test above must
    resolve using ONLY the good z0 layer (10, passable) — not crash on the
    garbage z1 id (5000, far past both the atlas bound and this tiny passages
    array), and not fall back to the void metatile (the old whole-column-drop
    behaviour)."""
    n = 20
    tm = TileMap(
        tiles={_LSYNTH: {}},  # bucket mode
        tilesets={_LSYNTH: TilesetChoice("gTileset_P", "gTileset_S")},
        buckets={_LSYNTH: Bucket(passable=10, blocked=11, void=7)},
        passages={_LSYNTH: [0] * n},  # tile 10 passable; too short to cover 5000
        priorities={_LSYNTH: [0] * n},
        atlas_max={_LSYNTH: 399},
    )
    grid = _layout_grid(1, 1, [10], [5000])  # z0 good ground, z1 garbage

    layout = convert_layout(
        {
            "tiles": {
                "xsize": grid.xsize, "ysize": grid.ysize, "zsize": grid.zsize,
                "data": grid.data,
            },
            "width": grid.xsize, "height": grid.ysize, "tileset_id": _LSYNTH,
        },
        tm,
        name="T",
        layout_const="LAYOUT_T",
    )

    assert len(layout.blocks) == 1
    assert layout.blocks[0] & METATILE_ID_MASK == 10  # passable bucket, from z0 alone

    # Both paths agree: the column key a masked grid produces for this exact
    # cell is the same one column_keys_for_maps returned above.
    masked, _ = mask_out_of_atlas(grid, max_static_tile_id=399)
    assert column_key(masked, 0, 0) == ((0, 10),)


# ---------------------------------------------------------------------------
# 2. Map-viewer level: a synthetic map with one out-of-atlas static cell must
#    load via build_map_data without raising, and the cell must be reported.
# ---------------------------------------------------------------------------

_MAP_ID = 9401  # arbitrary, not a real corpus id and not in SLICE_MAP_IDS


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _setup_synthetic_map(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A 2x1 map (3 RMXP layers, per the real corpus's fixed zsize) whose two
    cells are: (0,0) a valid static tile (384), (1,0) an out-of-atlas static
    tile (5000, past this tileset's 8x2 = 16-cell atlas -> max valid id 399)."""
    maps_dir = tmp_path / "maps"
    gfx = tmp_path / "Graphics"
    tj = tmp_path / "tilesets.json"

    xsize, ysize, zsize = 2, 1, 3
    data = [0] * (xsize * ysize * zsize)
    data[0 * ysize * xsize + 0 * xsize + 0] = 384   # (x=0,y=0,z=0): valid
    data[0 * ysize * xsize + 0 * xsize + 1] = 5000  # (x=1,y=0,z=0): out-of-atlas

    _write_json(
        maps_dir / f"Map{_MAP_ID:03d}.json",
        {
            "map_id": _MAP_ID,
            "tileset_id": 19,
            "width": xsize,
            "height": ysize,
            "events": [],
            "tiles": {"xsize": xsize, "ysize": ysize, "zsize": zsize, "data": data},
        },
    )
    # Sized generously past the garbage id so compare_collision's raw index
    # lookups (unrelated to this fix) never go out of range.
    n = 8192
    _write_json(
        tj,
        {
            "19": {
                "id": 19,
                "name": "Test",
                "tileset_name": "Atlas",
                "autotile_names": [""] * 7,
                "passages": [0] * n,
                "priorities": [0] * n,
                "terrain_tags": [0] * n,
            }
        },
    )
    (gfx / "Tilesets").mkdir(parents=True, exist_ok=True)
    _atlas(gfx / "Tilesets", cols=8, rows=2).rename(gfx / "Tilesets" / "Atlas.png")
    return maps_dir, gfx, tj


@pytest.fixture(autouse=True)
def _clean_viewer_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Module-level viewer caches must not leak between tests (or a stale
    entry from a differently-shaped fixture under the same map_id would be
    served)."""
    mvc._map_cache.clear()
    mvc._tile_png_cache.clear()
    mvc._metatile_png_cache.clear()
    mvc._tileset_analysis_cache.clear()
    mvc._png_paths_cache.clear()
    monkeypatch.setattr(mvc, "SLICE_MAP_IDS", [])
    # Synthetic quads are not in the corpus merge table (and nothing here is about it).
    monkeypatch.setattr(mvc, "_tile_merge", False)
    yield
    mvc._map_cache.clear()
    mvc._tile_png_cache.clear()
    mvc._metatile_png_cache.clear()
    mvc._tileset_analysis_cache.clear()
    mvc._png_paths_cache.clear()


def _point_module_at(monkeypatch: pytest.MonkeyPatch, *, maps_dir: Path, tj: Path, gfx: Path) -> None:
    monkeypatch.setattr(mvc, "_maps_dir", lambda: maps_dir)
    monkeypatch.setattr(mvc, "_tilesets_json", lambda: tj)
    monkeypatch.setattr(src, "default_graphics_dir", lambda: gfx)


def test_build_map_data_survives_out_of_atlas_cell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    maps_dir, gfx, tj = _setup_synthetic_map(tmp_path)
    _point_module_at(monkeypatch, maps_dir=maps_dir, tj=tj, gfx=gfx)

    data = mvc.build_map_data(_MAP_ID)  # must not raise

    assert data["out_of_atlas"] == [{"x": 1, "y": 0, "layer": 0, "tile_id": 5000}]

    cell_good = next(c for c in data["cells"] if c["x"] == 0 and c["y"] == 0)
    cell_bad = next(c for c in data["cells"] if c["x"] == 1 and c["y"] == 0)
    assert "out_of_atlas" not in cell_good
    assert cell_bad["out_of_atlas"] is True
    assert cell_bad["layer_detail"][0]["out_of_atlas"] is True


def test_build_map_data_survives_short_passages_array(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real Uranium tilesets.json passages/priorities/terrain_tags arrays are
    NOT padded out to cover garbage tile ids (unlike the other fixtures in this
    file, which pad generously) — e.g. Map087's passages array has length 1184
    but its garbage id is 5534. `our_blocked`/`uranium_blocked`
    (compare_collision.py) index straight into those arrays with no bounds
    guard (layout._passage_lookup fails loud by design), so this garbage id
    must never reach them at all — `state.grid` is masked (zeroed) before
    build_map_data ever calls them, not merely skipped around.

    This fixture's bad cell (1, 0) has NO other non-empty layer, so masking
    its one tile leaves the cell entirely empty. Collision then runs for real
    (not skipped) on that empty column: our own convention treats an all-empty
    column as void = blocked (`column_blocked`'s `not seen_tile` rule, same as
    the border/void metatile everywhere else); Uranium's own
    `playerPassable?` reads raw tile 0 at every layer and finds it passable
    (passage 0, priority 0) — a real, pre-existing void-vs-Uranium divergence
    the `mismatch` field exists to surface, not something this masking fix
    introduces or should paper over."""
    maps_dir, gfx, tj = _setup_synthetic_map(tmp_path)
    doc = json.loads(tj.read_text(encoding="utf-8"))
    short = 600  # shorter than the garbage id (5000)
    doc["19"]["passages"] = [0] * short
    doc["19"]["priorities"] = [0] * short
    doc["19"]["terrain_tags"] = [0] * short
    tj.write_text(json.dumps(doc), encoding="utf-8")
    _point_module_at(monkeypatch, maps_dir=maps_dir, tj=tj, gfx=gfx)

    data = mvc.build_map_data(_MAP_ID)  # must not raise KeyError

    cell_bad = next(c for c in data["cells"] if c["x"] == 1 and c["y"] == 0)
    assert cell_bad["out_of_atlas"] is True
    assert cell_bad["collision_ours"] is True   # void convention: blocked
    assert cell_bad["collision_uranium"] is False  # raw tile 0 reads passable
    assert cell_bad["mismatch"] is True


def test_build_map_data_clean_map_reports_no_out_of_atlas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    maps_dir, gfx, tj = _setup_synthetic_map(tmp_path)
    # Overwrite the out-of-atlas cell with another valid static id.
    doc_path = maps_dir / f"Map{_MAP_ID:03d}.json"
    doc = json.loads(doc_path.read_text(encoding="utf-8"))
    doc["tiles"]["data"][1] = 385
    doc_path.write_text(json.dumps(doc), encoding="utf-8")
    _point_module_at(monkeypatch, maps_dir=maps_dir, tj=tj, gfx=gfx)

    data = mvc.build_map_data(_MAP_ID)

    assert data["out_of_atlas"] == []
    assert all("out_of_atlas" not in c for c in data["cells"])


def test_render_tile_png_out_of_atlas_raises_file_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The server's top-level handler maps FileNotFoundError -> a clean 404;
    an out-of-atlas tile id must raise that, not the fail-loud ValueError
    `_render_static` would (which the server would turn into a 500)."""
    maps_dir, gfx, tj = _setup_synthetic_map(tmp_path)
    _point_module_at(monkeypatch, maps_dir=maps_dir, tj=tj, gfx=gfx)

    with pytest.raises(FileNotFoundError):
        mvc.render_tile_png(_MAP_ID, 5000)

    # A valid tile still renders fine.
    png = mvc.render_tile_png(_MAP_ID, 384)
    assert png.startswith(b"\x89PNG")


_MIXED_MAP_ID = 9402  # arbitrary, distinct from _MAP_ID, not in SLICE_MAP_IDS


def _setup_synthetic_map_mixed(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A 2x1 map whose cell (1, 0) has BOTH a good layer (z1=385) and an
    out-of-atlas layer (z0=5000) — the case the whole-column-drop bug lost
    entirely: the good layer must still render and decide collision."""
    maps_dir = tmp_path / "maps"
    gfx = tmp_path / "Graphics"
    tj = tmp_path / "tilesets.json"

    xsize, ysize, zsize = 2, 1, 3
    data = [0] * (xsize * ysize * zsize)
    data[0 * ysize * xsize + 0 * xsize + 0] = 384   # (0,0,z0): valid, alone
    data[0 * ysize * xsize + 0 * xsize + 1] = 5000  # (1,0,z0): out-of-atlas
    data[1 * ysize * xsize + 0 * xsize + 1] = 385   # (1,0,z1): valid — survives masking

    _write_json(
        maps_dir / f"Map{_MIXED_MAP_ID:03d}.json",
        {
            "map_id": _MIXED_MAP_ID,
            "tileset_id": 19,
            "width": xsize,
            "height": ysize,
            "events": [],
            "tiles": {"xsize": xsize, "ysize": ysize, "zsize": zsize, "data": data},
        },
    )
    n = 8192
    _write_json(
        tj,
        {
            "19": {
                "id": 19,
                "name": "Test",
                "tileset_name": "Atlas",
                "autotile_names": [""] * 7,
                "passages": [0] * n,
                "priorities": [0] * n,
                "terrain_tags": [0] * n,
            }
        },
    )
    (gfx / "Tilesets").mkdir(parents=True, exist_ok=True)
    _atlas(gfx / "Tilesets", cols=8, rows=2).rename(gfx / "Tilesets" / "Atlas.png")
    return maps_dir, gfx, tj


def test_build_map_data_renders_good_layer_of_a_mixed_cell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bug this whole file is about: a cell with one out-of-atlas layer and
    one good layer must keep the good layer's art and collision, not go void.
    `metatile_attrs`/`colkey_idx` prove the cell got a REAL (non-void) metatile,
    not the empty-column placeholder."""
    maps_dir, gfx, tj = _setup_synthetic_map_mixed(tmp_path)
    _point_module_at(monkeypatch, maps_dir=maps_dir, tj=tj, gfx=gfx)

    data = mvc.build_map_data(_MIXED_MAP_ID)  # must not raise

    assert data["out_of_atlas"] == [{"x": 1, "y": 0, "layer": 0, "tile_id": 5000}]

    cell_mixed = next(c for c in data["cells"] if c["x"] == 1 and c["y"] == 0)
    assert cell_mixed["out_of_atlas"] is True
    # The good z1 layer is still reported, alongside the masked z0 layer.
    good_layers = [ld for ld in cell_mixed["layer_detail"] if not ld.get("out_of_atlas")]
    assert good_layers == [
        {"z": 1, "tile_id": 385, "passage": 0, "priority": 0, "terrain": 0, "autotile_name": None}
    ]
    # colkey_idx must point at a REAL (non-empty) column, not the void/empty one.
    state = mvc._map_cache[_MIXED_MAP_ID]
    assert state.colkeys_sorted[cell_mixed["colkey_idx"]] == ((1, 385),)
    mt = state.metatile_imgs[cell_mixed["colkey_idx"]]
    assert mt is not None  # a real metatile was rendered, not voided

    # render_metatile_png must actually produce image bytes for it (bottom layer,
    # priority 0 -> the good tile 385 composites onto the bottom slot).
    png = mvc.render_metatile_png(_MIXED_MAP_ID, cell_mixed["colkey_idx"], "bottom")
    assert png.startswith(b"\x89PNG")
