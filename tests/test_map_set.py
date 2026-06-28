"""Tests for the single map-set source of truth (tileset_converter.map_set)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.tileset_converter.map_set import (
    SLICE_MAP_IDS,
    discover_all_map_ids,
    parse_map_ids,
    resolve_map_ids,
)


def _make_maps(tmp_path: Path, ids: list[int]) -> Path:
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    for i in ids:
        (maps_dir / f"Map{i:03d}.json").write_text("{}", encoding="utf-8")
    return maps_dir


def _make_strip(tmp_path: Path, ids: list[int]) -> Path:
    strip = tmp_path / "strip_list.json"
    strip.write_text(json.dumps({"maps": [{"id": i} for i in ids]}), encoding="utf-8")
    return strip


def test_discover_sorted_noncontiguous(tmp_path: Path) -> None:
    maps_dir = _make_maps(tmp_path, [32, 5, 199, 48])
    assert discover_all_map_ids(maps_dir) == [5, 32, 48, 199]


def test_discover_empty_fails_loud(tmp_path: Path) -> None:
    (tmp_path / "maps").mkdir()
    with pytest.raises(FileNotFoundError):
        discover_all_map_ids(tmp_path / "maps")


def test_discover_applies_strip_list(tmp_path: Path) -> None:
    maps_dir = _make_maps(tmp_path, [1, 2, 999])
    strip = _make_strip(tmp_path, [999])
    assert discover_all_map_ids(maps_dir, strip_list=strip) == [1, 2]


def test_parse_slice_profile(tmp_path: Path) -> None:
    maps_dir = _make_maps(tmp_path, [49, 48, 32])
    assert parse_map_ids("slice", maps_dir) == SLICE_MAP_IDS
    # slice returns a copy, not the module list
    assert parse_map_ids("slice", maps_dir) is not SLICE_MAP_IDS


def test_parse_full_profile(tmp_path: Path) -> None:
    maps_dir = _make_maps(tmp_path, [49, 48, 32, 7])
    assert parse_map_ids("full", maps_dir) == [7, 32, 48, 49]


def test_parse_explicit_ids_preserve_order(tmp_path: Path) -> None:
    maps_dir = _make_maps(tmp_path, [49, 48, 32, 7])
    assert parse_map_ids("49,48,7", maps_dir) == [49, 48, 7]


def test_parse_explicit_missing_id_fails_loud(tmp_path: Path) -> None:
    maps_dir = _make_maps(tmp_path, [49, 48, 32])
    with pytest.raises(ValueError, match="not present on disk"):
        parse_map_ids("49,777", maps_dir)


def test_parse_garbage_fails_loud(tmp_path: Path) -> None:
    maps_dir = _make_maps(tmp_path, [49])
    with pytest.raises(ValueError):
        parse_map_ids("not-a-number", maps_dir)


def test_resolve_alias_matches_parse(tmp_path: Path) -> None:
    maps_dir = _make_maps(tmp_path, [49, 48, 32])
    assert resolve_map_ids("full", maps_dir) == parse_map_ids("full", maps_dir)
