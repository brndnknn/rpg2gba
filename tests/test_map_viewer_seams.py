"""Viewer seam features (scripts/map_viewer_common.py): the opt-in "Seam palettes"
view (cache key, toggle, component lookup, off == plain per-map) and the "ROM seam
check" computation. Synthetic data / monkeypatching only; no quantization of real maps.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import map_viewer_common as mvc  # noqa: E402

from rpg2gba.tileset_converter.connections import ConnectionRow  # noqa: E402
from rpg2gba.tileset_converter.graphics.emit import MetatileImage  # noqa: E402
from rpg2gba.tileset_converter.layout import TileGrid  # noqa: E402


def _mt(v: int) -> MetatileImage:
    b = np.full((16, 16, 4), v, dtype=np.uint8)
    return MetatileImage(b, np.zeros((16, 16, 4), dtype=np.uint8), 0, 0)


# ---------------------------------------------------------------------------
# metatile image hash / strip geometry / seam entry
# ---------------------------------------------------------------------------


def test_image_hash_is_by_pixels_not_identity() -> None:
    assert mvc.metatile_image_hash(_mt(5)) == mvc.metatile_image_hash(_mt(5))
    assert mvc.metatile_image_hash(_mt(5)) != mvc.metatile_image_hash(_mt(6))
    assert mvc.metatile_image_hash(None) is None
    # bottom vs top matters: same bytes swapped between layers must not collide
    a = _mt(5)
    swapped = MetatileImage(a.top, a.bottom, 0, 0)
    assert mvc.metatile_image_hash(a) != mvc.metatile_image_hash(swapped)


@pytest.mark.parametrize(
    "edge, origin, a, b, expect",
    [
        # B above A (N edge), same width: B's bottom 2 rows (depth 2), all columns
        ("N", (0, -4), (3, 4), (3, 4), [(x, y) for y in (2, 3) for x in range(3)]),
        # B below A (S edge): B's top rows, offset 1 -> overlap A x in [1,3) -> B x 0..1
        ("S", (1, 4), (3, 4), (3, 4), [(x, y) for y in (0, 1) for x in (0, 1)]),
        # B left of A (W edge): B's right columns, rows clamped to overlap
        ("W", (-4, 1), (4, 3), (4, 3), [(x, y) for y in (0, 1) for x in (2, 3)]),
        # B right of A (E edge): B's left columns, B shorter than A and offset down
        ("E", (4, 2), (4, 6), (4, 2), [(x, y) for y in (0, 1) for x in (0, 1)]),
    ],
)
def test_strip_cells_geometry(edge, origin, a, b, expect) -> None:
    assert mvc.seam_strip_cells(edge, origin, a, b, depth=2) == expect


def test_strip_depth_clamped_to_small_neighbour() -> None:
    cells = mvc.seam_strip_cells("S", (0, 4), (2, 4), (2, 1))  # default depth 7, B 1 row tall
    assert cells == [(0, 0), (1, 0)]


def test_seam_entry_counts_by_unique_image_and_skips_empty() -> None:
    conn = {"id": 9, "name": "Nine", "edge": "S", "origin": [0, 4]}
    # B is 4 wide, 1 tall: cells (0..3, 0). hashes: x0 'p' (in A), x1 'q', x2 'q', x3 None
    grid = {(0, 0): "p", (1, 0): "q", (2, 0): "q", (3, 0): None}
    entry = mvc.compute_seam_entry(conn, (4, 4), (4, 1), {"p"}, lambda x, y: grid[(x, y)])
    assert entry["neighbor"] == 9
    assert entry["direction"] == "down"
    assert entry["strip"] == [[0, 0], [1, 0], [2, 0]]          # empty cell is not strip
    assert entry["missing"] == [[1, 0], [2, 0]]                # q absent from A's pool
    assert entry["strip_unique"] == 2
    assert entry["missing_unique"] == 1                        # two cells, one metatile


def test_seam_check_compares_images_across_different_colkeys(monkeypatch) -> None:
    """A's pool holds image X under column key kA; B's strip cell uses a DIFFERENT
    column key kB that renders the same image -> present (not missing)."""
    kA, kB, kC = ((0, 1),), ((0, 2),), ((0, 3),)
    a = SimpleNamespace(
        grid=TileGrid(1, 1, 1, [1]), colkey_to_idx={kA: 0}, metatile_imgs=[_mt(7)],
    )
    # B: 2 cells wide, 1 tall; cell0 tile 2 (kB, image 7), cell1 tile 3 (kC, image 9)
    b = SimpleNamespace(
        grid=TileGrid(2, 1, 1, [2, 3]), colkey_to_idx={kB: 0, kC: 1},
        metatile_imgs=[_mt(7), _mt(9)],
    )
    monkeypatch.setattr(mvc, "_ensure_loaded", lambda mid: None)
    monkeypatch.setitem(mvc._map_cache, 1001, a)
    monkeypatch.setitem(mvc._map_cache, 1002, b)
    import map_graph

    monkeypatch.setattr(
        map_graph, "connections_for",
        lambda mid: [{"id": 1002, "name": "B", "edge": "S", "origin": [0, 1], "band": [0, 1]}],
    )
    out = mvc.seam_check(1001)
    (seam,) = out["seams"]
    assert seam["strip"] == [[0, 0]]          # B is 2 wide but A's edge is 1 wide: clamped
    assert seam["missing"] == []              # same image under a different column key
    assert out["pool_unique"] == 1

    a.metatile_imgs = [_mt(8)]                # now A lacks image 7
    seam = mvc.seam_check(1001)["seams"][0]
    assert seam["missing"] == [[0, 0]] and seam["missing_unique"] == 1


# ---------------------------------------------------------------------------
# seam-palette key / toggle
# ---------------------------------------------------------------------------


@pytest.fixture
def seam_env(monkeypatch):
    """Component (31, 35, 40) from synthetic rows; fingerprints and generation controllable."""
    rows = [
        ConnectionRow(31, "N", 0, 35, "S", 0),
        ConnectionRow(35, "N", 0, 40, "S", 0),
        ConnectionRow(50, "N", 0, 51, "S", 0),
    ]
    monkeypatch.setattr(mvc, "_connection_rows", lambda: rows)
    fps = {"v": 1}
    monkeypatch.setattr(mvc, "_slice_aware_fingerprint", lambda m: ((m, fps["v"]),))
    monkeypatch.setattr(mvc, "_quant_generation", 100)
    monkeypatch.setattr(mvc, "_shared_palettes", False)  # seam palettes need shared off (viewer default is on)
    mvc._seam_palette_cache.clear()
    mvc._seam_view_cache.clear()
    mvc._tileset_analysis_cache.clear()
    yield fps
    mvc._seam_palette_cache.clear()
    mvc._seam_view_cache.clear()
    mvc._tileset_analysis_cache.clear()


def test_component_uses_all_rows_not_only_slice_ids(seam_env) -> None:
    assert 40 not in mvc.SLICE_MAP_IDS
    assert mvc._seam_component(40) == (31, 35, 40)
    assert mvc._seam_component(31) == (31, 35, 40)
    assert mvc._seam_component(7) is None


def test_seam_key_off_or_no_component_is_none(seam_env) -> None:
    assert mvc._seam_key(31, False) is None
    assert mvc._seam_key(7, True) is None


def test_seam_key_tracks_members_and_knobs(seam_env, monkeypatch) -> None:
    k0 = mvc._seam_key(31, True)
    assert k0[0] == (31, 35, 40)
    assert mvc._seam_key(40, True) == k0                 # same for every member
    assert mvc._seam_key(50, True) != k0                 # other component
    seam_env["v"] = 2                                    # a member's inputs changed
    k1 = mvc._seam_key(31, True)
    assert k1 != k0
    monkeypatch.setattr(mvc, "_quant_generation", 101)   # knob Apply / reload
    assert mvc._seam_key(31, True) != k1
    monkeypatch.setattr(mvc, "_max_palettes", 7)
    assert mvc._seam_key(31, True) != k1


def _fake_state(analysis, p2i, post):
    return SimpleNamespace(
        tileset_id=22, raster=object(), priorities=[], passages=[], terrain_tags=[],
        analysis=analysis, pool_key_to_idx=p2i, metatile_imgs_postquant=post,
    )


def test_off_and_no_component_views_are_the_plain_per_map_state(seam_env, monkeypatch) -> None:
    analysis, p2i, post = object(), {("k",): 0}, ["pq"]
    monkeypatch.setattr(mvc, "_ensure_loaded", lambda mid: None)
    monkeypatch.setitem(mvc._map_cache, 31, _fake_state(analysis, p2i, post))
    monkeypatch.setitem(mvc._map_cache, 7, _fake_state(analysis, p2i, post))
    monkeypatch.setattr(mvc, "_component_palettes", lambda key: pytest.fail("must not compute"))

    for mid, seam in ((31, False), (7, True), (7, False)):
        v = mvc._quant_view(mid, seam)
        assert v.analysis is analysis and v.pool_key_to_idx is p2i and v.postquant is post


def test_seam_view_pins_component_palettes_and_caches(seam_env, monkeypatch) -> None:
    plain = (object(), {}, [])
    st = _fake_state(*plain)
    monkeypatch.setattr(mvc, "_ensure_loaded", lambda mid: None)
    monkeypatch.setitem(mvc._map_cache, 31, st)
    pals = [np.zeros((3, 3), dtype=np.uint8)]
    calls = {"pal": 0, "ana": []}

    def fake_pals(key):
        calls["pal"] += 1
        return pals

    seam_analysis = SimpleNamespace(metatiles=[SimpleNamespace(quant_bottom="b", quant_top="t")])

    def fake_analysis(*args, seam_key=None, quantizer=None):
        calls["ana"].append((seam_key, quantizer))
        return seam_analysis, {(): 0}

    monkeypatch.setattr(mvc, "_component_palettes", fake_pals)
    monkeypatch.setattr(mvc, "_ensure_tileset_analysis", fake_analysis)
    monkeypatch.setattr(mvc, "_postquant_for", lambda *a: ["seam-pq"])

    v = mvc._quant_view(31, True)
    assert v.analysis is seam_analysis and v.postquant == ["seam-pq"]
    seam_key, quantizer = calls["ana"][0]
    assert seam_key == mvc._seam_key(31, True) and callable(quantizer)
    # the quantizer is a pinned one: assigns tiles to the given palettes, ignoring max_palettes
    res = quantizer([np.zeros((8, 8, 4), dtype=np.uint8)], max_palettes=13)
    assert res.stats["pinned"] is True

    assert mvc._quant_view(31, True) is v                # cached
    assert calls["pal"] == 1
    # toggling off returns the plain view, untouched by the seam view
    assert mvc._quant_view(31, False).analysis is plain[0]
    # a changed member fingerprint invalidates the seam view
    seam_env["v"] = 2
    mvc._quant_view(31, True)
    assert calls["pal"] == 2


def test_component_palettes_sorted_lists_skip_missing_members(seam_env, monkeypatch) -> None:
    lists = {31: [_mt(1)], 35: None, 40: [_mt(2), _mt(3)]}
    monkeypatch.setattr(mvc, "_member_metatiles", lambda m: lists[m])
    seen = {}

    def fake_compute(ls, *, max_palettes, quantizer):
        seen["ls"] = ls
        seen["mp"] = max_palettes
        return ["P"]

    monkeypatch.setattr(mvc, "compute_component_palettes", fake_compute)
    key = mvc._seam_key(31, True)
    assert mvc._component_palettes(key) == ["P"]
    assert [len(x) for x in seen["ls"]] == [1, 2]        # sorted by map id, 35 skipped
    seen.clear()
    assert mvc._component_palettes(key) == ["P"] and not seen   # cached by key


def test_metatile_png_cache_key_separates_seam_views(seam_env, monkeypatch) -> None:
    """Post-quant PNGs are cached under the seam key, so on/off never alias; raw layers share."""
    st = _fake_state(object(), {}, [(np.zeros((16, 16, 4), np.uint8),) * 2])
    st.metatile_imgs = [_mt(1)]
    monkeypatch.setattr(mvc, "_ensure_loaded", lambda mid: None)
    monkeypatch.setitem(mvc._map_cache, 31, st)
    seam_pq = (np.full((16, 16, 4), 200, np.uint8),) * 2
    monkeypatch.setattr(mvc, "_quant_view", lambda mid, seam: SimpleNamespace(
        postquant=[seam_pq] if seam else st.metatile_imgs_postquant))
    mvc._metatile_png_cache.clear()
    try:
        off = mvc.render_metatile_png(31, 0, "post_bottom", False)
        on = mvc.render_metatile_png(31, 0, "post_bottom", True)
        assert off != on
        assert mvc.render_metatile_png(31, 0, "post_bottom", False) is off
        assert mvc.render_metatile_png(31, 0, "bottom", True) is mvc.render_metatile_png(31, 0, "bottom", False)
    finally:
        mvc._metatile_png_cache.clear()
