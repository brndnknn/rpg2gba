"""The map-viewer and palette-inspector pages are assembled at import from real
files under scripts/map_viewer/ (viewer.{html,css,js}, palette.{html,css,js},
knobbar.js). Guard the assembly: no placeholder tokens left unsubstituted, the
server's per-request config token survives, and known markup is present.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import map_viewer_common as mvc  # noqa: E402

_PAGES = [mvc.MAP_VIEWER_HTML, mvc.PALETTE_VIEWER_HTML]


def test_pages_non_empty() -> None:
    for page in _PAGES:
        assert len(page) > 5000


def test_config_token_survives_assembly() -> None:
    for page in _PAGES:
        assert "__VIEWER_CONFIG__" in page


def test_no_unsubstituted_placeholders() -> None:
    for page in _PAGES:
        for token in ("/*VIEWER_CSS*/", "/*VIEWER_JS*/", "/*KNOBBAR_JS*/"):
            assert token not in page


def test_knobbar_js_spliced_in() -> None:
    for page in _PAGES:
        assert "id('knobbar')" in page or "getElementById('knobbar')" in page


def test_known_markup_present() -> None:
    assert "#graphics-chrome" in mvc.MAP_VIEWER_HTML
    assert 'id="knobbar"' in mvc.MAP_VIEWER_HTML
    assert 'id="mapCanvas"' in mvc.MAP_VIEWER_HTML
    assert "Palette Inspector" in mvc.PALETTE_VIEWER_HTML


def test_no_static_mode_branches_remain() -> None:
    # The static delivery path was removed; V.mode must be gone entirely.
    for page in _PAGES:
        assert "V.mode" not in page
