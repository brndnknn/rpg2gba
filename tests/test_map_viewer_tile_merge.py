"""Viewer knob bar: the `tile_merge` toggle, its application in the per-map render path,
and `emit_tileset(enforce_caps=False)` (the budget probe's enabler)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import map_viewer_common as mvc  # noqa: E402
from rpg2gba.tileset_converter.graphics import emit as emit_mod  # noqa: E402
from rpg2gba.tileset_converter.graphics import rom_quantize  # noqa: E402
from rpg2gba.tileset_converter.graphics.emit import (  # noqa: E402
    LAYER_COVERED,
    MetatileImage,
    PaletteAnalysis,
    emit_tileset,
)


@pytest.fixture(autouse=True)
def _restore_state():
    saved = (mvc._family_params, mvc._max_palettes, mvc._quant_generation,
             mvc._shared_palettes, mvc._tile_merge)
    yield
    (mvc._family_params, mvc._max_palettes, mvc._quant_generation,
     mvc._shared_palettes, mvc._tile_merge) = saved
    mvc._tileset_analysis_cache.clear()
    mvc._budget_cache.clear()


def _apply(d: dict) -> int:
    params, mp = mvc.params_from_dict(d)
    return mvc.set_quantize_params(
        params, mp, shared_palettes=mvc.shared_palettes_from_dict(d),
        tile_merge=mvc.tile_merge_from_dict(d),
    )


@pytest.mark.parametrize("val,want", [(True, True), (False, False), (None, False),
                                      ("true", False), (1, False)])
def test_parse_is_strict_boolean(val, want):
    assert mvc.tile_merge_from_dict({"tile_merge": val}) is want


def test_missing_key_is_viewer_default_on():
    assert mvc.tile_merge_from_dict({}) is True
    assert mvc.VIEWER_DEFAULT_TILE_MERGE is True


def test_rom_stock_is_rom_build_config():
    assert mvc.ROM_STOCK_TILE_MERGE is rom_quantize.ROM_TILE_MERGE


def test_round_trip_non_stock_viewer_default_and_generation():
    mvc.set_rom_stock_quantize()
    st = mvc.get_quantize_params()
    assert st["tile_merge"] is rom_quantize.ROM_TILE_MERGE and st["non_stock"] is False
    gen = st["generation"]
    _apply({"tile_merge": True})
    st = mvc.get_quantize_params()
    assert st["tile_merge"] is True and st["generation"] > gen
    assert st["non_stock"] is (not rom_quantize.ROM_TILE_MERGE)
    assert mvc.current_tile_merge() is True
    mvc.set_viewer_default_quantize()
    assert mvc.get_quantize_params()["viewer_default"] is True
    _apply({"tile_merge": False})
    st = mvc.get_quantize_params()
    assert st["viewer_default"] is False and st["tile_merge"] is False


def test_apply_invalidates_caches():
    mvc._tileset_analysis_cache[("x",)] = ("a", {})  # type: ignore[index]
    mvc._budget_cache[(1, 1)] = {}
    _apply({"tile_merge": False})
    assert not mvc._tileset_analysis_cache and not mvc._budget_cache


def test_set_params_without_toggle_keeps_it():
    mvc.set_quantize_params(*mvc.current_quantize_state(), tile_merge=True)
    mvc.set_quantize_params(*mvc.current_quantize_state())
    assert mvc.current_tile_merge() is True
    mvc.set_quantize_params(*mvc.current_quantize_state(), tile_merge=False)
    mvc.set_quantize_params(*mvc.current_quantize_state())
    assert mvc.current_tile_merge() is False


def test_rom_stock_resets_viewer_toggle():
    mvc.set_quantize_params(*mvc.current_quantize_state(), tile_merge=True)
    mvc.set_rom_stock_quantize()
    assert mvc.current_tile_merge() is rom_quantize.ROM_TILE_MERGE


def test_seam_plus_tile_merge_fails_loud():
    _apply({"shared_palettes": False, "tile_merge": True})
    with pytest.raises(mvc.SeamSharedConflict, match="tile merge"):
        mvc._seam_key(31, True)
    assert mvc._seam_key(31, False) is None


# ---- pool application ------------------------------------------------------

def _mt(v: int) -> MetatileImage:
    return MetatileImage(np.full((16, 16, 4), [v, 0, 0, 255], np.uint8),
                         np.zeros((16, 16, 4), np.uint8), LAYER_COVERED, 0)


class _FakeTable:
    def __init__(self) -> None:
        self.applied = 0

    def apply_metatile(self, mt: MetatileImage) -> MetatileImage:
        self.applied += 1
        # collapse every metatile onto value 7 -> a dedup would shrink the pool
        return _mt(7)


class _Raster:
    def max_static_tile_id(self) -> int:
        return 10**6


def _run_analysis(monkeypatch, tmp_path, *, merge: bool):
    (tmp_path / "Map001.json").write_text("{}", encoding="utf-8")
    keys = [("a",), ("b",), ("c",)]
    table = _FakeTable()
    seen: list[list[MetatileImage]] = []

    def fake_analyze(mts, *, max_palettes, quantizer):
        seen.append(list(mts))
        return PaletteAnalysis(palettes=[], metatiles=[])

    monkeypatch.setattr(mvc, "_maps_dir", lambda: tmp_path)
    monkeypatch.setattr(mvc, "column_keys_for_maps", lambda ml, max_static_tile_id: keys)
    monkeypatch.setattr(mvc, "column_in_atlas", lambda r, k: True)
    monkeypatch.setattr(mvc, "_render_pool_column",
                        lambda ck, *a: _mt(keys.index(ck)))
    monkeypatch.setattr(mvc, "analyze_tileset_palettes", fake_analyze)
    monkeypatch.setattr(mvc, "_get_merge_table", lambda: table)
    mvc._tileset_analysis_cache.clear()
    mvc.set_quantize_params(*mvc.current_quantize_state(), shared_palettes=False,
                            tile_merge=merge)
    _, p2i = mvc._ensure_tileset_analysis(1, _Raster(), [], 1, [], [])
    return table, seen, p2i


def test_merge_applied_only_when_on_and_pool_index_preserved(monkeypatch, tmp_path):
    table, seen, p2i = _run_analysis(monkeypatch, tmp_path, merge=True)
    assert table.applied == 3
    assert len(seen[0]) == 3, "no dedup/reorder: pool index i must stay pool key i"
    assert p2i == {("a",): 0, ("b",): 1, ("c",): 2}
    assert all(int(m.bottom[0, 0, 0]) == 7 for m in seen[0])  # substituted in place


def test_merge_not_applied_when_off(monkeypatch, tmp_path):
    table, seen, p2i = _run_analysis(monkeypatch, tmp_path, merge=False)
    assert table.applied == 0
    assert [int(m.bottom[0, 0, 0]) for m in seen[0]] == [0, 1, 2]
    assert p2i == {("a",): 0, ("b",): 1, ("c",): 2}


# ---- emit_tileset(enforce_caps=False) --------------------------------------

def _over_cap_metatiles() -> list[MetatileImage]:
    return [
        MetatileImage(np.full((16, 16, 4), c, np.uint8), np.zeros((16, 16, 4), np.uint8),
                      LAYER_COVERED, 0)
        for c in ([248, 0, 0, 255], [0, 248, 0, 255], [0, 0, 248, 255])
    ]


def test_enforce_caps_false_returns_counts_default_still_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(emit_mod, "NUM_TILES_TOTAL", 2)
    monkeypatch.setattr(emit_mod, "NUM_METATILES_TOTAL", 2)
    mts = _over_cap_metatiles()
    with pytest.raises(ValueError, match="exceeds"):
        emit_tileset(mts, tmp_path / "p0", tmp_path / "s0", "p", "s")
    em = emit_tileset(mts, tmp_path / "p1", tmp_path / "s1", "p", "s", enforce_caps=False)
    assert em.n_metatiles == 3 and em.n_tiles == 4
