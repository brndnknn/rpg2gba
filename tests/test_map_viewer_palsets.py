"""Palette-sets overlay: /api/palsets data (which 8x8 quadrants the P2 shared palettes pin)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import map_viewer_common as mvc  # noqa: E402
from rpg2gba.tileset_converter.graphics.shared_palettes import classify_tile  # noqa: E402

BIG, SMALL, BELOW = 35, 48, 19  # 19: both groups below the 8-tile threshold


@pytest.fixture(autouse=True)
def _restore_state():
    saved = (mvc._family_params, mvc._max_palettes, mvc._quant_generation, mvc._shared_palettes)
    yield
    mvc._family_params, mvc._max_palettes, mvc._quant_generation, mvc._shared_palettes = saved
    mvc._palsets_cache.clear()


def _sets(map_id: int) -> dict:
    try:
        return mvc.palette_sets(map_id)
    except (FileNotFoundError, KeyError, OSError) as exc:
        pytest.skip(f"map {map_id} build output absent: {exc}")


def test_grid_shapes_and_counts_sum():
    mvc.set_viewer_default_quantize()
    d = _sets(BIG)
    meta = mvc.build_map_data(BIG)["meta"]
    assert (d["width"], d["height"]) == (2 * meta["xsize"], 2 * meta["ysize"])
    n = d["width"] * d["height"]
    for layer in d["layers"]:
        assert len(d["codes"][layer]) == len(d["tiles"][layer]) == n
        assert sum(d["counts_quadrants"][layer].values()) == n
        assert set(d["codes"][layer]) <= {-1, 0, 1, 2, 3, 4}
    assert sum(d["counts_unique_tiles"].values()) == len(d["tile_info"])


def test_codes_consistent_with_tile_info_and_classify_tile():
    d = _sets(BIG)
    for layer in d["layers"]:
        for code, t in zip(d["codes"][layer], d["tiles"][layer]):
            if t < 0:
                assert code == -1
            else:
                assert d["tile_info"][t][0] == code
    # tile_info rows agree with classify_tile semantics: rock iff shift <= 1
    for code, rs, _sse, g, _gs, _gsse in d["tile_info"]:
        if code == -1:
            assert rs is None
        elif code == 1:
            assert rs <= 1
        else:
            assert rs > 1
            if code >= 2:
                assert g == code - 2
    assert classify_tile  # public API used by the endpoint


def test_reservation_matches_quantizer_info_when_on():
    mvc.set_viewer_default_quantize()
    mvc._shared_info.pop(BIG, None)
    mvc._tileset_analysis_cache.clear()
    mvc._map_cache.pop(BIG, None)
    d = _sets(BIG)
    mvc.build_map_data(BIG)
    info = mvc._shared_info[BIG]
    r = d["reservation"]
    assert d["shared_on"] is True
    assert (r["n_rock"], r["n_green"]) == (info["n_rock"], info["n_green"])
    assert (r["rock_reserved"], r["green_reserved"]) == (info["rock_reserved"], info["green_reserved"])


def test_works_with_shared_off_and_same_classification():
    mvc.set_viewer_default_quantize()
    on = _sets(SMALL)
    mvc.set_quantize_params(
        mvc.ROM_STOCK_PARAMS, mvc.ROM_STOCK_MAX_PALETTES, shared_palettes=False
    )
    off = _sets(SMALL)
    assert on["shared_on"] is True and off["shared_on"] is False
    # classification is still reported with the toggle off (label: "would be pinned")
    assert (off["width"], off["height"]) == (on["width"], on["height"])
    assert off["reservation"]["threshold"] == 8
    assert sum(off["counts_unique_tiles"].values()) == len(off["tile_info"])


def test_below_threshold_group_is_not_effective():
    d = _sets(BELOW)
    r = d["reservation"]
    assert r["n_rock"] < r["threshold"] and r["n_green"] < r["threshold"]
    assert not r["rock_reserved"] and not r["green_reserved"]
    assert d["effective"]["0"] is True
    for c in ("1", "2", "3", "4"):
        assert d["effective"][c] is False
    # tiles are still classified as set members even though not reserved
    assert any(c in (1, 2, 3, 4) for c in d["codes"]["bottom"] + d["codes"]["top"])


def test_mixed_reservation_flags():
    d = _sets(SMALL)  # green set reserved, rock set not
    assert d["effective"]["2"] is d["reservation"]["green_reserved"]
    assert d["effective"]["1"] is d["reservation"]["rock_reserved"]
