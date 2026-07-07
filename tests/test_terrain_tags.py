"""Unit tests for terrain_tags.py — Essentials terrain-tag -> MB_* mapping.

Uses a fake fork tree (behaviors enum only) + reference/terrain_tag_map.json
(the real file — validated against the fake fork's enum, which carries every
name the real map references)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from rpg2gba.tileset_converter.terrain_tags import (
    load_terrain_tag_map,
    load_terrain_tags_json,
)


def _fake_fork(tmp_path: Path) -> Path:
    """Minimal fork with every MB_* name reference/terrain_tag_map.json uses."""
    fork = tmp_path / "fork"
    (fork / "include" / "constants").mkdir(parents=True)
    (fork / "include" / "constants" / "metatile_behaviors.h").write_text(
        "enum {\n"
        "    MB_NORMAL,\n"
        "    MB_TALL_GRASS,\n"
        "    MB_SAND,\n"
        "    MB_DEEP_WATER,\n"
        "    MB_POND_WATER,\n"
        "    MB_WATERFALL,\n"
        "    MB_LONG_GRASS,\n"
        "    MB_SEAWEED,\n"
        "    MB_ICE,\n"
        "    MB_ASHGRASS,\n"
        "    MB_NON_ANIMATED_DOOR,\n"
        "    MB_JUMP_NORTH,\n"
        "    MB_JUMP_SOUTH,\n"
        "    MB_JUMP_EAST,\n"
        "    MB_JUMP_WEST,\n"
        "};\n",
        encoding="utf-8",
    )
    return fork


REAL_TERRAIN_TAG_MAP = Path("reference/terrain_tag_map.json")


def test_load_real_terrain_tag_map(tmp_path: Path) -> None:
    """The real reference/terrain_tag_map.json loads and validates cleanly."""
    fork = _fake_fork(tmp_path)
    table = load_terrain_tag_map(fork, REAL_TERRAIN_TAG_MAP)
    assert table is not None


def test_topmost_nonzero_tag_wins(tmp_path: Path) -> None:
    """A tag on the z=2 layer beats a (different) tag on z=0; all-zero -> MB_NORMAL."""
    fork = _fake_fork(tmp_path)
    table = load_terrain_tag_map(fork, REAL_TERRAIN_TAG_MAP)

    tags = [0] * 500
    tags[400] = 3  # sand, on z=0
    tags[401] = 2  # grass, on z=2 -> should win (topmost)

    key_grass_on_top = ((0, 400), (2, 401))
    behavior = table.column_behavior(5, key_grass_on_top, tags)
    assert behavior == table._tag_to_value[2]  # MB_TALL_GRASS numeric value

    # All-zero tags -> MB_NORMAL.
    tags_zero = [0] * 500
    key = ((0, 400), (2, 401))
    behavior_zero = table.column_behavior(5, key, tags_zero)
    assert behavior_zero == table._tag_to_value[0]


def test_opaque_cover_stops_tag_fallthrough(tmp_path: Path) -> None:
    """RMXP maps flood-fill a water layer under solid land: a fully-opaque tag-0
    tile on top must STOP the fall-through (else grass/hedges next to the pond
    inherit reflective MB_POND_WATER — boot gate 2026-07-06). A transparent
    overlay (flowers) still falls through to the terrain beneath."""
    fork = _fake_fork(tmp_path)
    table = load_terrain_tag_map(fork, REAL_TERRAIN_TAG_MAP)

    tags = [0] * 500
    tags[400] = 7  # water, on z=0
    key = ((0, 400), (1, 401))  # tag-0 tile 401 covers the water

    # Opaque cover -> MB_NORMAL, the water tag beneath must not leak up.
    opaque = table.column_behavior(5, key, tags, is_opaque=lambda tid: tid == 401)
    assert opaque == table._tag_to_value[0]

    # Transparent overlay -> falls through to the water tag (legacy behavior).
    transparent = table.column_behavior(5, key, tags, is_opaque=lambda tid: False)
    assert transparent == table._tag_to_value[7]

    # No predicate (legacy callers) -> unchanged fall-through.
    legacy = table.column_behavior(5, key, tags)
    assert legacy == table._tag_to_value[7]


def test_autotile_variant_fallback(tmp_path: Path) -> None:
    """Variant id 50 with no own tag inherits base 48's tag."""
    fork = _fake_fork(tmp_path)
    table = load_terrain_tag_map(fork, REAL_TERRAIN_TAG_MAP)

    tags = [0] * 500
    tags[48] = 2  # grass at autotile base
    # tags[50] left at 0 -> should fall back to base 48's tag.

    key = ((0, 50),)
    behavior = table.column_behavior(5, key, tags)
    assert behavior == table._tag_to_value[2]


def test_grass_tag_maps_to_real_mb_tall_grass_value(tmp_path: Path) -> None:
    """Tag 2 -> the numeric value of MB_TALL_GRASS parsed from the real engine header."""
    real_fork = Path("engine")
    table = load_terrain_tag_map(real_fork, REAL_TERRAIN_TAG_MAP)

    from rpg2gba.tileset_converter.terrain_tags import _behavior_value

    expected = _behavior_value(real_fork, "MB_TALL_GRASS")
    tags = [0] * 500
    tags[400] = 2
    behavior = table.column_behavior(5, ((0, 400),), tags)
    assert behavior == expected


def test_ledge_with_direction_entry(tmp_path: Path) -> None:
    """A ledge tile with a ledge_directions entry resolves to the matching MB_JUMP_*."""
    fork = _fake_fork(tmp_path)
    ledge_map = tmp_path / "terrain_tag_map.json"
    raw = json.loads(REAL_TERRAIN_TAG_MAP.read_text(encoding="utf-8"))
    raw["ledge_directions"] = {"5": {"400": "south"}}
    ledge_map.write_text(json.dumps(raw), encoding="utf-8")

    table = load_terrain_tag_map(fork, ledge_map)

    tags = [0] * 500
    tags[400] = 1  # ledge

    behavior = table.column_behavior(5, ((0, 400),), tags)

    from rpg2gba.tileset_converter.terrain_tags import _behavior_value

    assert behavior == _behavior_value(fork, "MB_JUMP_SOUTH")


def test_ledge_without_direction_entry_warns_once_and_falls_back(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A ledge with no ledge_directions entry logs a warning naming tileset+tile id
    (deduped across repeated cells with the same tile id) and returns MB_NORMAL."""
    fork = _fake_fork(tmp_path)
    table = load_terrain_tag_map(fork, REAL_TERRAIN_TAG_MAP)

    tags = [0] * 500
    tags[400] = 1  # ledge, no direction entry

    with caplog.at_level(logging.WARNING):
        b1 = table.column_behavior(5, ((0, 400),), tags)
        b2 = table.column_behavior(5, ((0, 400),), tags)  # same (tileset, tile) again

    assert b1 == table._normal_value
    assert b2 == table._normal_value

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "5" in warnings[0].getMessage()
    assert "400" in warnings[0].getMessage()


def test_unknown_tag_raises(tmp_path: Path) -> None:
    """A terrain tag present in the data but absent from the table raises."""
    fork = _fake_fork(tmp_path)
    table = load_terrain_tag_map(fork, REAL_TERRAIN_TAG_MAP)

    tags = [0] * 500
    tags[400] = 23  # not in the table

    with pytest.raises(ValueError, match="23"):
        table.column_behavior(5, ((0, 400),), tags)


def test_load_terrain_tags_json(tmp_path: Path) -> None:
    tilesets_json = tmp_path / "tilesets.json"
    tilesets_json.write_text(
        json.dumps({"5": {"terrain_tags": [0, 1, 2, 3]}}), encoding="utf-8"
    )
    assert load_terrain_tags_json(tilesets_json, 5) == [0, 1, 2, 3]


def test_load_terrain_tags_json_missing_tileset_raises(tmp_path: Path) -> None:
    tilesets_json = tmp_path / "tilesets.json"
    tilesets_json.write_text(json.dumps({}), encoding="utf-8")
    with pytest.raises(KeyError):
        load_terrain_tags_json(tilesets_json, 5)
