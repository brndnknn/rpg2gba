"""Hot-reload fingerprint coverage for tileset source PNGs (PROJECT_TODO.md #12a).

Two things under test:

1. ``rpg2gba.tileset_converter.graphics.sources.tileset_source_paths`` — the
   eager, never-raising path-enumeration helper new source PNGs get resolved
   through for fingerprinting (contrast with the lazy, fail-loud
   ``load_tileset_sources`` the renderer uses).
2. ``scripts/map_viewer_common.py``'s ``_derive_png_paths_for_map`` and the
   extended ``_slice_aware_fingerprint`` that folds those PNG paths' stats in
   alongside the pre-existing JSON-only fingerprint, plus the derivation memo
   cache (``_png_paths_cache``) that keeps steady-state per-request cost to
   stats only.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from PIL import Image

from rpg2gba.tileset_converter.graphics import sources as src

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import map_viewer_common as mvc  # noqa: E402

# ---------------------------------------------------------------------------
# fixture helpers
# ---------------------------------------------------------------------------


def _png(path: Path, size: tuple[int, int] = (8, 8)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, (1, 2, 3, 255)).save(path)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_map_json(path: Path, *, tileset_id: int) -> None:
    _write_json(path, {"map_id": 0, "tileset_id": tileset_id})


@pytest.fixture(autouse=True)
def _clear_png_paths_cache() -> None:
    """`_png_paths_cache` is module-level global state keyed by bare map_id
    ints; clear it around every test so fixtures in one test can't be served
    stale by a same-numbered map_id fixture in another."""
    mvc._png_paths_cache.clear()
    yield
    mvc._png_paths_cache.clear()


# ---------------------------------------------------------------------------
# 1. tileset_source_paths (sources.py)
# ---------------------------------------------------------------------------


def test_tileset_source_paths_sheet_and_nonempty_autotiles(tmp_path: Path) -> None:
    gfx = tmp_path / "Graphics"
    _png(gfx / "Tilesets" / "Foo.png")
    _png(gfx / "Autotiles" / "Land.png")
    _png(gfx / "Autotiles" / "Sea.png")
    tj = tmp_path / "tilesets.json"
    _write_json(
        tj,
        {
            "5": {
                "id": 5,
                "tileset_name": "Foo",
                "autotile_names": ["Land", "", "Sea", "", "", "", ""],
            }
        },
    )

    paths = src.tileset_source_paths(5, tilesets_json=tj, graphics_dir=gfx)

    # Sheet first, then non-empty autotiles in stored slot order; empty slots skipped.
    assert paths == [
        gfx / "Tilesets" / "Foo.png",
        gfx / "Autotiles" / "Land.png",
        gfx / "Autotiles" / "Sea.png",
    ]


def test_tileset_source_paths_missing_entry_returns_empty(tmp_path: Path) -> None:
    tj = tmp_path / "tilesets.json"
    _write_json(tj, {"5": {"id": 5, "tileset_name": "Foo", "autotile_names": [""] * 7}})

    assert src.tileset_source_paths(999, tilesets_json=tj, graphics_dir=tmp_path / "Graphics") == []


def test_tileset_source_paths_missing_file_yields_nominal_path(tmp_path: Path) -> None:
    gfx = tmp_path / "Graphics"  # no PNGs written at all
    tj = tmp_path / "tilesets.json"
    _write_json(
        tj,
        {
            "5": {
                "id": 5,
                "tileset_name": "Foo",
                "autotile_names": ["Ghost", "", "", "", "", "", ""],
            }
        },
    )

    paths = src.tileset_source_paths(5, tilesets_json=tj, graphics_dir=gfx)

    assert paths == [gfx / "Tilesets" / "Foo.png", gfx / "Autotiles" / "Ghost.png"]
    assert not paths[0].exists()
    assert not paths[1].exists()
    # A nominal path stats as (-1, -1) via _file_fingerprint (map_viewer_common's helper).
    assert mvc._file_fingerprint(paths[0]) == (-1, -1)


def test_tileset_source_paths_unreadable_json_returns_empty(tmp_path: Path) -> None:
    tj = tmp_path / "tilesets.json"
    tj.write_text("not valid json {{{", encoding="utf-8")

    assert src.tileset_source_paths(5, tilesets_json=tj, graphics_dir=tmp_path / "Graphics") == []


def test_tileset_source_paths_missing_graphics_dir_env_degrades(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RPG2GBA_URANIUM_SRC unset (and no .env-paths) -> default_graphics_dir()
    raises RuntimeError; tileset_source_paths must absorb that, not propagate."""
    tj = tmp_path / "tilesets.json"
    _write_json(tj, {"5": {"id": 5, "tileset_name": "Foo", "autotile_names": [""] * 7}})

    def _boom() -> Path:
        raise RuntimeError("RPG2GBA_URANIUM_SRC is not set")

    monkeypatch.setattr(src, "default_graphics_dir", _boom)

    assert src.tileset_source_paths(5, tilesets_json=tj) == []


# ---------------------------------------------------------------------------
# 2. _derive_png_paths_for_map (map_viewer_common.py) — explicit params, no
#    monkeypatching of module env state.
# ---------------------------------------------------------------------------


def test_derive_png_paths_resolves_own_tileset(tmp_path: Path) -> None:
    maps_dir = tmp_path / "maps"
    gfx = tmp_path / "Graphics"
    tj = tmp_path / "tilesets.json"

    _write_map_json(maps_dir / "Map007.json", tileset_id=5)
    _write_json(tj, {"5": {"id": 5, "tileset_name": "Foo", "autotile_names": ["Land"] + [""] * 6}})
    _png(gfx / "Tilesets" / "Foo.png")
    _png(gfx / "Autotiles" / "Land.png")

    paths = mvc._derive_png_paths_for_map(
        7, maps_dir=maps_dir, tilesets_json_path=tj, graphics_dir=gfx
    )

    assert paths == (gfx / "Tilesets" / "Foo.png", gfx / "Autotiles" / "Land.png")


def test_derive_png_paths_missing_map_json_degrades_to_empty(tmp_path: Path) -> None:
    maps_dir = tmp_path / "maps"  # Map007.json never written
    tj = tmp_path / "tilesets.json"
    _write_json(tj, {})

    paths = mvc._derive_png_paths_for_map(
        7, maps_dir=maps_dir, tilesets_json_path=tj, graphics_dir=tmp_path / "Graphics"
    )

    assert paths == ()


def test_derive_png_paths_malformed_map_json_degrades_to_empty(tmp_path: Path) -> None:
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    (maps_dir / "Map007.json").write_text("{not json", encoding="utf-8")
    tj = tmp_path / "tilesets.json"
    _write_json(tj, {})

    paths = mvc._derive_png_paths_for_map(
        7, maps_dir=maps_dir, tilesets_json_path=tj, graphics_dir=tmp_path / "Graphics"
    )

    assert paths == ()


def test_derive_png_paths_missing_tileset_id_key_degrades_to_empty(tmp_path: Path) -> None:
    maps_dir = tmp_path / "maps"
    _write_json(maps_dir / "Map007.json", {"map_id": 7})  # no tileset_id key
    tj = tmp_path / "tilesets.json"
    _write_json(tj, {})

    paths = mvc._derive_png_paths_for_map(
        7, maps_dir=maps_dir, tilesets_json_path=tj, graphics_dir=tmp_path / "Graphics"
    )

    assert paths == ()


# ---------------------------------------------------------------------------
# 3. _slice_aware_fingerprint / _json_fingerprint — full integration, module
#    env seams (_maps_dir / _tilesets_json) pointed at tmp_path.
# ---------------------------------------------------------------------------


def _point_module_at(
    monkeypatch: pytest.MonkeyPatch, *, maps_dir: Path, tilesets_json: Path
) -> None:
    monkeypatch.setattr(mvc, "_maps_dir", lambda: maps_dir)
    monkeypatch.setattr(mvc, "_tilesets_json", lambda: tilesets_json)


def _setup_map007(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A non-slice map (007, tileset 5) with a real sheet + one autotile PNG."""
    maps_dir = tmp_path / "maps"
    gfx = tmp_path / "Graphics"
    tj = tmp_path / "tilesets.json"

    _write_map_json(maps_dir / "Map007.json", tileset_id=5)
    _write_json(tj, {"5": {"id": 5, "tileset_name": "Foo", "autotile_names": ["Land"] + [""] * 6}})
    _png(gfx / "Tilesets" / "Foo.png")
    _png(gfx / "Autotiles" / "Land.png")
    return maps_dir, gfx, tj


def test_fingerprint_changes_when_png_mtime_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    maps_dir, gfx, tj = _setup_map007(tmp_path)
    monkeypatch.setattr(src, "default_graphics_dir", lambda: gfx)
    _point_module_at(monkeypatch, maps_dir=maps_dir, tilesets_json=tj)

    before = mvc._slice_aware_fingerprint(7)

    sheet = gfx / "Tilesets" / "Foo.png"
    st = sheet.stat()
    os.utime(sheet, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))

    after = mvc._slice_aware_fingerprint(7)

    assert before != after


def test_fingerprint_changes_when_png_size_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    maps_dir, gfx, tj = _setup_map007(tmp_path)
    monkeypatch.setattr(src, "default_graphics_dir", lambda: gfx)
    _point_module_at(monkeypatch, maps_dir=maps_dir, tilesets_json=tj)

    before = mvc._slice_aware_fingerprint(7)

    _png(gfx / "Autotiles" / "Land.png", size=(16, 16))  # rewrite bigger

    after = mvc._slice_aware_fingerprint(7)

    assert before != after


def test_fingerprint_stable_when_nothing_changed_and_derivation_cached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    maps_dir, gfx, tj = _setup_map007(tmp_path)
    monkeypatch.setattr(src, "default_graphics_dir", lambda: gfx)
    _point_module_at(monkeypatch, maps_dir=maps_dir, tilesets_json=tj)

    first = mvc._slice_aware_fingerprint(7)
    cached_after_first = mvc._png_paths_cache[7][1]
    second = mvc._slice_aware_fingerprint(7)
    cached_after_second = mvc._png_paths_cache[7][1]

    assert first == second
    # Derivation cache actually hit on the second call: the same tuple object
    # is reused, not rebuilt (rebuilding would parse map JSON + tilesets.json
    # again, which the memo exists specifically to avoid).
    assert cached_after_first is cached_after_second


def test_derivation_reruns_when_tilesets_json_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    maps_dir, gfx, tj = _setup_map007(tmp_path)
    _png(gfx / "Autotiles" / "Sea.png")
    monkeypatch.setattr(src, "default_graphics_dir", lambda: gfx)
    _point_module_at(monkeypatch, maps_dir=maps_dir, tilesets_json=tj)

    before = mvc._slice_aware_fingerprint(7)
    paths_before = mvc._png_paths_cache[7][1]
    assert gfx / "Autotiles" / "Sea.png" not in paths_before

    # Autotile list changes (adds a slot) -> tilesets.json mtime/size changes ->
    # _json_fingerprint changes -> memo key mismatch -> re-derivation, picking
    # up the new PNG path set.
    _write_json(
        tj,
        {
            "5": {
                "id": 5,
                "tileset_name": "Foo",
                "autotile_names": ["Land", "Sea", "", "", "", "", ""],
            }
        },
    )

    after = mvc._slice_aware_fingerprint(7)
    paths_after = mvc._png_paths_cache[7][1]

    assert before != after
    assert gfx / "Autotiles" / "Sea.png" in paths_after


def test_missing_graphics_dir_env_still_returns_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RPG2GBA_URANIUM_SRC unset -> default_graphics_dir() raises -> the PNG
    half of the fingerprint degrades to empty, but the call must not crash:
    the JSON-only half still comes through, so the viewer still starts for
    JSON-only use."""
    maps_dir, _gfx, tj = _setup_map007(tmp_path)
    _point_module_at(monkeypatch, maps_dir=maps_dir, tilesets_json=tj)

    def _boom() -> Path:
        raise RuntimeError("RPG2GBA_URANIUM_SRC is not set")

    monkeypatch.setattr(src, "default_graphics_dir", _boom)

    fp = mvc._slice_aware_fingerprint(7)

    assert fp == mvc._json_fingerprint(7)  # no PNG entries appended
    assert mvc._png_paths_cache[7][1] == ()


def test_slice_map_fingerprint_covers_json_of_sibling_maps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Slice maps (SLICE_MAP_IDS) still fold every sibling's json stat into the
    fingerprint (pre-existing behavior, unchanged by this feature): editing a
    sibling's json (which can shift the shared quantization pool -- see
    _ensure_tileset_analysis) must flip Map048's fingerprint even though
    Map048's own json never changed."""
    maps_dir = tmp_path / "maps"
    gfx = tmp_path / "Graphics"
    tj = tmp_path / "tilesets.json"

    _write_map_json(maps_dir / "Map048.json", tileset_id=19)
    _write_map_json(maps_dir / "Map049.json", tileset_id=19)
    _write_map_json(maps_dir / "Map032.json", tileset_id=22)
    _write_json(
        tj,
        {
            "19": {"id": 19, "tileset_name": "Indoor", "autotile_names": [""] * 7},
            "22": {"id": 22, "tileset_name": "Outdoor", "autotile_names": [""] * 7},
        },
    )
    _png(gfx / "Tilesets" / "Indoor.png")
    _png(gfx / "Tilesets" / "Outdoor.png")
    monkeypatch.setattr(src, "default_graphics_dir", lambda: gfx)
    _point_module_at(monkeypatch, maps_dir=maps_dir, tilesets_json=tj)
    monkeypatch.setattr(mvc, "SLICE_MAP_IDS", [48, 49, 32])

    before = mvc._slice_aware_fingerprint(48)

    # Rewrite Map049.json (sibling) -- Map048's own json is untouched.
    _write_map_json(maps_dir / "Map049.json", tileset_id=19)
    st = (maps_dir / "Map049.json").stat()
    os.utime(
        maps_dir / "Map049.json", ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000)
    )

    after = mvc._slice_aware_fingerprint(48)

    assert before != after
    # And Map048's own PNG derivation only ever resolved tileset 19 (its own),
    # never tileset 22 (Map032's, a different tileset -- not in the pool).
    assert (gfx / "Tilesets" / "Outdoor.png") not in mvc._png_paths_cache[48][1]
    assert (gfx / "Tilesets" / "Indoor.png") in mvc._png_paths_cache[48][1]
