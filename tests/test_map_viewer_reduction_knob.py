"""Viewer knob bar: the `reduction` knob (median_cut | ward) round-trips."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import map_viewer_common as mvc  # noqa: E402
from rpg2gba.tileset_converter.graphics import rom_quantize  # noqa: E402
from rpg2gba.tileset_converter.graphics.quantize import FamilyParams  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_state():
    saved = (mvc._family_params, mvc._max_palettes, mvc._quant_generation, mvc._shared_palettes)
    yield
    mvc._family_params, mvc._max_palettes, mvc._quant_generation, mvc._shared_palettes = saved


def test_ward_round_trips():
    params, _ = mvc.params_from_dict({"reduction": "ward"})
    assert params.reduction == "ward"


@pytest.mark.parametrize("bad", [None, "", "WARD", "median", 3, "ward "])
def test_garbage_falls_back_to_median_cut(bad):
    params, _ = mvc.params_from_dict({"reduction": bad})
    assert params.reduction == "median_cut"


def test_missing_key_is_viewer_default():
    params, mp = mvc.params_from_dict({})
    assert params == FamilyParams(reduction="ward") and mp == mvc._ENGINE_MAX_PALS
    assert params == mvc.VIEWER_DEFAULT_PARAMS


def test_module_boots_in_viewer_default():
    # The fixture saved the import-time state before any test mutated it.
    assert mvc.VIEWER_DEFAULT_PARAMS.reduction == "ward" and mvc.VIEWER_DEFAULT_SHARED is True


def test_rom_stock_is_the_rom_build_config():
    # The viewer's ROM view must be the build's config (rom_quantize), never a copy.
    assert mvc.ROM_STOCK_PARAMS == rom_quantize.ROM_FAMILY_PARAMS
    assert mvc.ROM_STOCK_SHARED is rom_quantize.ROM_SHARED_PALETTES
    assert mvc.ROM_STOCK_PARAMS.reduction == "ward" and mvc.ROM_STOCK_SHARED is True


def test_state_reports_reduction_and_non_stock():
    mvc.set_rom_stock_quantize()
    st = mvc.get_quantize_params()
    assert st["reduction"] == "ward" and st["non_stock"] is False
    gen = st["generation"]
    mvc.set_viewer_default_quantize()
    st = mvc.get_quantize_params()
    assert st["reduction"] == "ward" and st["viewer_default"] is True
    assert st["generation"] > gen
    # stock median cut: non-stock now, and not the viewer default
    mvc.set_quantize_params(*mvc.params_from_dict({"reduction": "median_cut"}))
    st = mvc.get_quantize_params()
    assert st["reduction"] == "median_cut"
    assert st["non_stock"] is True and st["viewer_default"] is False
