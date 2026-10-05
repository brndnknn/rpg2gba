"""Viewer knob bar: the viewer-only `shared_palettes` (P2 preview) toggle."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import map_viewer_common as mvc  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_state():
    saved = (mvc._family_params, mvc._max_palettes, mvc._quant_generation, mvc._shared_palettes)
    yield
    mvc._family_params, mvc._max_palettes, mvc._quant_generation, mvc._shared_palettes = saved


def _apply(d: dict) -> int:
    params, mp = mvc.params_from_dict(d)
    return mvc.set_quantize_params(params, mp, shared_palettes=mvc.shared_palettes_from_dict(d))


@pytest.mark.parametrize("val,want", [(True, True), (False, False), (None, False),
                                      ("true", False), (1, False)])
def test_parse_is_strict_boolean(val, want):
    assert mvc.shared_palettes_from_dict({"shared_palettes": val}) is want


def test_missing_key_is_viewer_default():
    assert mvc.shared_palettes_from_dict({}) is True


def test_round_trip_non_stock_and_generation():
    mvc.set_rom_stock_quantize()
    st = mvc.get_quantize_params()
    assert st["shared_palettes"] is False and st["non_stock"] is False
    gen = st["generation"]
    _apply({"shared_palettes": True})
    st = mvc.get_quantize_params()
    assert st["shared_palettes"] is True and st["non_stock"] is True
    assert st["generation"] > gen
    assert mvc.current_shared_palettes() is True


def test_rollback_snapshot_restores_toggle():
    _apply({"shared_palettes": True})
    prev = (*mvc.current_quantize_state(), mvc.current_shared_palettes())
    _apply({"shared_palettes": False})
    assert mvc.current_shared_palettes() is False
    mvc.set_quantize_params(prev[0], prev[1], shared_palettes=prev[2])
    assert mvc.current_shared_palettes() is True


def test_composes_with_ward():
    _apply({"shared_palettes": True, "reduction": "ward"})
    st = mvc.get_quantize_params()
    assert st["reduction"] == "ward" and st["shared_palettes"] is True


def test_wrap_applied_only_when_on(monkeypatch):
    calls: list[dict] = []
    real = mvc.make_shared_quantizer

    def spy(base, **kw):
        calls.append(kw)
        return real(base, **kw)

    monkeypatch.setattr(mvc, "make_shared_quantizer", spy)
    mvc.set_rom_stock_quantize()
    q_off = mvc._make_quantizer(shared=mvc._shared_palettes)
    assert calls == [] and not hasattr(q_off, "info")
    _apply({"shared_palettes": True, "reduction": "ward"})
    q_on = mvc._make_quantizer(shared=mvc._shared_palettes)
    assert len(calls) == 1 and calls[0]["family_params"] == mvc._family_params
    assert calls[0]["family_params"].reduction == "ward"
    assert hasattr(q_on, "info")


def test_set_params_without_toggle_keeps_it():
    mvc.set_quantize_params(*mvc.current_quantize_state(), shared_palettes=True)
    mvc.set_quantize_params(*mvc.current_quantize_state())
    assert mvc.current_shared_palettes() is True
    mvc.set_quantize_params(*mvc.current_quantize_state(), shared_palettes=False)
    mvc.set_quantize_params(*mvc.current_quantize_state())
    assert mvc.current_shared_palettes() is False


def test_seam_plus_shared_fails_loud():
    _apply({"shared_palettes": True})
    with pytest.raises(mvc.SeamSharedConflict, match="untick"):
        mvc._seam_key(31, True)
    assert mvc._seam_key(31, False) is None
    assert issubclass(mvc.SeamSharedConflict, ValueError)


def test_seam_works_with_shared_off():
    mvc.set_rom_stock_quantize()
    mvc._seam_key(31, True)  # must not raise
