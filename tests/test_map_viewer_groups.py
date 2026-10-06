"""The viewer pools quantization by ROM tileset group (map_set.tileset_groups), not per map."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import map_viewer_common as mvc  # noqa: E402
from rpg2gba.tileset_converter import map_set  # noqa: E402


@pytest.fixture(autouse=True)
def _clear():
    mvc._tileset_analysis_cache.clear()
    yield
    mvc._tileset_analysis_cache.clear()


def _setup(monkeypatch, tmp_path, groups):
    maps = tmp_path / "maps"
    maps.mkdir()
    for m in (31, 32, 35, 9999):
        (maps / f"Map{m:03d}.json").write_text("{}", encoding="utf-8")
    (tmp_path / "connections.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(mvc, "_maps_dir", lambda: maps)
    monkeypatch.setattr(mvc, "_tilesets_json", lambda: tmp_path / "ts.json")
    monkeypatch.setattr(map_set, "load_slice_tileset_groups", lambda out, ids, **k: groups)
    monkeypatch.setattr(map_set, "SLICE_MAP_IDS", [31, 32, 35])


def test_pool_members(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, {31: 1031, 35: 1031, 32: 1032})
    assert mvc._pool_members(35) == [31, 35]
    assert mvc._pool_members(31) == [31, 35]
    assert mvc._pool_members(32) == [32]
    assert mvc._pool_members(9999) == [9999]  # outside the slice


def test_group_pool_is_union_and_cached_once(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, {31: 1031, 35: 1031, 32: 1032})
    calls: list[list[int]] = []

    class _R:
        def max_static_tile_id(self) -> int:
            return 10**6

    def keys(maplist, max_static_tile_id):
        calls.append([m for m, _ in maplist])
        return []

    monkeypatch.setattr(mvc, "column_keys_for_maps", keys)
    a31 = mvc._ensure_tileset_analysis(1031, _R(), [], 31, [], [])
    a35 = mvc._ensure_tileset_analysis(1031, _R(), [], 35, [], [])
    assert len(mvc._tileset_analysis_cache) == 1 and a31[1] == a35[1]
    assert calls == [[31, 35]]  # computed once, over the whole group
    mvc._ensure_tileset_analysis(1032, _R(), [], 32, [], [])
    assert calls == [[31, 35], [32]]
