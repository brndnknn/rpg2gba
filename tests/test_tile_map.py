"""Tests for synthetic tileset id resolution in load_tile_map / _load_oracle, and
for the per-column warp metatile resolution (fix #1,
walker_checkpoint2_findings.md)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.tileset_converter.tile_map import (
    Bucket,
    Metatile,
    TileMap,
    TilesetChoice,
    WarpInfo,
    load_tile_map,
)


def _write_synth_fixtures(tmp_path: Path, synth_id: int, real_id: int) -> tuple[Path, Path]:
    """Write a tileset_map.json with a synthetic tileset id and a source_tilesets
    mapping to the real id, plus a tilesets.json oracle keyed by the REAL id."""
    n = 600
    passages = [0] * n
    passages[48] = 15  # autotile 1 blocks

    table = {
        "tilesets": {
            str(synth_id): {"primary": "gTileset_Building", "secondary": "gTileset_Synth"},
        },
        "buckets": {
            str(synth_id): {"passable": 10, "blocked": 11, "void": 7},
        },
        "warps": {
            str(synth_id): {"metatile": 99, "collision": 0, "elevation": 0},
        },
        "tiles": {str(synth_id): {}},
        "source_tilesets": {str(synth_id): real_id},
    }
    oracle = {
        str(real_id): {
            "passages": passages,
            "priorities": [0] * n,
            "terrain_tags": [0] * n,
        },
    }
    tpath = tmp_path / "tileset_map.json"
    opath = tmp_path / "tilesets.json"
    tpath.write_text(json.dumps(table), encoding="utf-8")
    opath.write_text(json.dumps(oracle), encoding="utf-8")
    return tpath, opath


def test_load_tile_map_synthetic_id_resolves_oracle(tmp_path: Path) -> None:
    """load_tile_map with source_tilesets: passages and priorities are stored under
    the SYNTHETIC key (not the real id) — no KeyError on missing synth in oracle."""
    synth_id = 1019
    real_id = 19
    tpath, opath = _write_synth_fixtures(tmp_path, synth_id, real_id)

    tm = load_tile_map(tpath, opath)

    # passages/priorities stored under the synthetic key, not the real id
    assert tm.passage(synth_id, 0) == 0        # passable
    assert tm.passage(synth_id, 48) == 15       # blocked (set in oracle under real_id=19)
    assert tm.priority(synth_id, 0) == 0

    # bucket lookups still work via synth key
    assert tm.has_bucket(synth_id)
    assert tm.void(synth_id).metatile_id == 7

    # real id is NOT present (oracle was read for it but stored under synth)
    assert not tm.has_bucket(real_id)


def test_terrain_tag_loaded_from_oracle_under_synthetic_key(tmp_path: Path) -> None:
    """terrain_tag() reads the oracle's terrain_tags array the same way passage()/
    priority() do — stored under the synthetic key, not the real id."""
    synth_id = 1019
    real_id = 19
    tpath, opath = _write_synth_fixtures(tmp_path, synth_id, real_id)
    # tag a tile in the oracle written by _write_synth_fixtures (real_id=19)
    oracle = json.loads(opath.read_text(encoding="utf-8"))
    oracle[str(real_id)]["terrain_tags"][20] = 20  # Shadow
    opath.write_text(json.dumps(oracle), encoding="utf-8")

    tm = load_tile_map(tpath, opath)
    assert tm.terrain_tag(synth_id, 20) == 20
    assert tm.terrain_tag(synth_id, 0) == 0  # untagged tile -> Neutral


def test_terrain_tag_defaults_to_zero_without_oracle() -> None:
    """A TileMap built without a terrain_tags oracle (legacy construction, most
    unit-test fixtures) resolves every terrain_tag() to 0 (Neutral) rather than
    raising — matches priority()'s soft-fallback style."""
    tm = TileMap(
        tiles={7: {}},
        tilesets={7: TilesetChoice("gP", "gS")},
        buckets={7: Bucket(5, 6, 7)},
        passages={7: [0] * 10},
        priorities={7: [0] * 10},
        # no terrain_tags passed at all
    )
    assert tm.terrain_tag(7, 0) == 0
    assert tm.terrain_tag(7, 9999) == 0  # out of range -> also 0, not IndexError
    assert tm.terrain_tag(99, 0) == 0  # unknown tileset -> also 0, not KeyError


def test_load_tile_map_oracle_missing_terrain_tags_fails_loud(tmp_path: Path) -> None:
    """A tilesets.json oracle entry missing 'terrain_tags' aborts load_tile_map —
    same fail-loud style as a missing 'passages'/'priorities' key (CLAUDE.md §4.5),
    not a silent 0-fill."""
    real_id = 19
    n = 600
    table = {
        "tilesets": {str(real_id): {"primary": "gTileset_A", "secondary": "gTileset_B"}},
        "buckets": {str(real_id): {"passable": 1, "blocked": 2, "void": 3}},
        "tiles": {str(real_id): {}},
    }
    oracle = {str(real_id): {"passages": [0] * n, "priorities": [0] * n}}  # no terrain_tags
    tpath = tmp_path / "tileset_map.json"
    opath = tmp_path / "tilesets.json"
    tpath.write_text(json.dumps(table), encoding="utf-8")
    opath.write_text(json.dumps(oracle), encoding="utf-8")

    with pytest.raises(KeyError):
        load_tile_map(tpath, opath)


def test_load_tile_map_no_source_tilesets_identity(tmp_path: Path) -> None:
    """Without source_tilesets, behavior is identical to legacy: oracle is read by
    the tileset id directly (backward-compat)."""
    real_id = 22
    n = 600
    passages = [0] * n
    passages[60] = 15

    table = {
        "tilesets": {
            str(real_id): {"primary": "gTileset_General", "secondary": "gTileset_Petalburg"},
        },
        "buckets": {
            str(real_id): {"passable": 1, "blocked": 468, "void": 468},
        },
        "warps": {
            str(real_id): {"metatile": 167, "collision": 0, "elevation": 0},
        },
        "tiles": {str(real_id): {}},
        # no source_tilesets key
    }
    oracle = {
        str(real_id): {"passages": passages, "priorities": [0] * n, "terrain_tags": [0] * n},
    }
    tpath = tmp_path / "tileset_map.json"
    opath = tmp_path / "tilesets.json"
    tpath.write_text(json.dumps(table), encoding="utf-8")
    opath.write_text(json.dumps(oracle), encoding="utf-8")

    tm = load_tile_map(tpath, opath)
    assert tm.passage(real_id, 60) == 15
    assert tm.passage(real_id, 0) == 0


def test_load_tile_map_synth_missing_from_oracle_raises(tmp_path: Path) -> None:
    """If source_tilesets is absent and the synth id is not in the oracle, KeyError."""
    synth_id = 1099
    n = 600
    table = {
        "tilesets": {
            str(synth_id): {"primary": "gTileset_A", "secondary": "gTileset_B"},
        },
        "buckets": {
            str(synth_id): {"passable": 1, "blocked": 2, "void": 3},
        },
        "tiles": {str(synth_id): {}},
        # no source_tilesets -> oracle is keyed by synth_id directly, which won't exist
    }
    oracle = {
        "19": {"passages": [0] * n, "priorities": [0] * n},  # real id, not synth
    }
    tpath = tmp_path / "tileset_map.json"
    opath = tmp_path / "tilesets.json"
    tpath.write_text(json.dumps(table), encoding="utf-8")
    opath.write_text(json.dumps(oracle), encoding="utf-8")

    with pytest.raises(KeyError):
        load_tile_map(tpath, opath)


# ---------------------------------------------------------------------------
# Tests for warp_for_column / WarpInfo (fix #1, walker_checkpoint2_findings.md)
# ---------------------------------------------------------------------------


def _door_key() -> tuple[tuple[int, int], ...]:
    return ((0, 400),)


def _other_key() -> tuple[tuple[int, int], ...]:
    return ((0, 401),)


def test_warp_for_column_exact_match_wins() -> None:
    """An exact column-key match returns the per-column door copy, not the
    fallback."""
    tm = TileMap(
        tiles={5: {}},
        tilesets={5: TilesetChoice("gTileset_P", "gTileset_S")},
        warps={5: WarpInfo(tiles={'[[0,400]]': Metatile(10, 0, 0)}, fallback=Metatile(99, 0, 0))},
    )
    assert tm.warp_for_column(5, _door_key()) == Metatile(10, 0, 0)


def test_warp_for_column_falls_back_on_miss() -> None:
    """A column key with no per-column entry resolves to the fallback."""
    tm = TileMap(
        tiles={5: {}},
        tilesets={5: TilesetChoice("gTileset_P", "gTileset_S")},
        warps={5: WarpInfo(tiles={'[[0,400]]': Metatile(10, 0, 0)}, fallback=Metatile(99, 0, 0))},
    )
    assert tm.warp_for_column(5, _other_key()) == Metatile(99, 0, 0)


def test_warp_for_column_none_key_uses_fallback() -> None:
    """key=None (empty/garbage warp cell) always resolves to the fallback."""
    tm = TileMap(
        tiles={5: {}},
        tilesets={5: TilesetChoice("gTileset_P", "gTileset_S")},
        warps={5: WarpInfo(tiles={'[[0,400]]': Metatile(10, 0, 0)}, fallback=Metatile(99, 0, 0))},
    )
    assert tm.warp_for_column(5, None) == Metatile(99, 0, 0)


def test_warp_for_column_legacy_shape_resolves_any_column(tmp_path: Path) -> None:
    """Loading the OLD warps shape (a single canned metatile) via load_tile_map
    still resolves warp_for_column for an arbitrary column key — full backward
    compat with reference/tileset_map.json and old *.gen.json overlays."""
    table = {
        "tilesets": {"5": {"primary": "gTileset_P", "secondary": "gTileset_S"}},
        "tiles": {"5": {}},
        "warps": {"5": {"metatile": 55, "collision": 0, "elevation": 0}},
    }
    tpath = tmp_path / "tileset_map.json"
    tpath.write_text(json.dumps(table), encoding="utf-8")

    tm = load_tile_map(tpath, passages_path=None)

    # Any column key — or None — resolves to the single legacy metatile.
    assert tm.warp_for_column(5, _door_key()) == Metatile(55, 0, 0)
    assert tm.warp_for_column(5, _other_key()) == Metatile(55, 0, 0)
    assert tm.warp_for_column(5, None) == Metatile(55, 0, 0)
    # Legacy `warp()` still works too.
    assert tm.warp(5) == Metatile(55, 0, 0)


def test_warp_for_column_no_warps_entry_raises() -> None:
    """No `warps` entry at all for the tileset -> KeyError (never a silent
    MB_NORMAL warp tile)."""
    tm = TileMap(
        tiles={5: {}},
        tilesets={5: TilesetChoice("gTileset_P", "gTileset_S")},
    )
    with pytest.raises(KeyError):
        tm.warp_for_column(5, _door_key())


# ---------------------------------------------------------------------------
# Tests for behavior_overrides / behavior_for_column (native sideways-stairs fix)
# ---------------------------------------------------------------------------


def _stair_key() -> tuple[tuple[int, int], ...]:
    return ((0, 700),)


def test_behavior_for_column_exact_match_wins() -> None:
    tm = TileMap(
        tiles={5: {}},
        tilesets={5: TilesetChoice("gTileset_P", "gTileset_S")},
        behavior_overrides={
            5: {
                "stairs_left": WarpInfo(
                    tiles={'[[0,700]]': Metatile(20, 1, 0)}, fallback=Metatile(88, 1, 0)
                )
            }
        },
    )
    result = tm.behavior_for_column(5, "stairs_left", _stair_key())
    assert result.metatile_id == 20
    # Always forced passable regardless of the source entry's own collision/elevation.
    assert result.collision == 0
    assert result.elevation == 3


def test_behavior_for_column_falls_back_on_miss() -> None:
    tm = TileMap(
        tiles={5: {}},
        tilesets={5: TilesetChoice("gTileset_P", "gTileset_S")},
        behavior_overrides={
            5: {
                "stairs_right": WarpInfo(
                    tiles={'[[0,700]]': Metatile(20, 1, 0)}, fallback=Metatile(88, 1, 0)
                )
            }
        },
    )
    result = tm.behavior_for_column(5, "stairs_right", _other_key())
    assert result.metatile_id == 88
    assert result.collision == 0
    assert result.elevation == 3


def test_behavior_for_column_none_key_uses_fallback() -> None:
    tm = TileMap(
        tiles={5: {}},
        tilesets={5: TilesetChoice("gTileset_P", "gTileset_S")},
        behavior_overrides={
            5: {"stairs_left": WarpInfo(tiles={}, fallback=Metatile(88, 1, 0))}
        },
    )
    result = tm.behavior_for_column(5, "stairs_left", None)
    assert result.metatile_id == 88
    assert result.collision == 0


def test_behavior_for_column_missing_tileset_raises() -> None:
    tm = TileMap(
        tiles={5: {}},
        tilesets={5: TilesetChoice("gTileset_P", "gTileset_S")},
    )
    with pytest.raises(KeyError):
        tm.behavior_for_column(5, "stairs_left", _stair_key())


def test_behavior_for_column_missing_kind_raises() -> None:
    tm = TileMap(
        tiles={5: {}},
        tilesets={5: TilesetChoice("gTileset_P", "gTileset_S")},
        behavior_overrides={5: {"stairs_left": WarpInfo(tiles={}, fallback=Metatile(88))}},
    )
    with pytest.raises(KeyError):
        tm.behavior_for_column(5, "stairs_right", _stair_key())


def test_behavior_for_column_no_column_no_fallback_raises() -> None:
    tm = TileMap(
        tiles={5: {}},
        tilesets={5: TilesetChoice("gTileset_P", "gTileset_S")},
        behavior_overrides={
            5: {"stairs_left": WarpInfo(tiles={'[[0,700]]': Metatile(20, 0, 0)}, fallback=None)}
        },
    )
    with pytest.raises(KeyError):
        tm.behavior_for_column(5, "stairs_left", _other_key())


def test_has_behavior_override() -> None:
    tm = TileMap(
        tiles={5: {}},
        tilesets={5: TilesetChoice("gTileset_P", "gTileset_S")},
        behavior_overrides={5: {"stairs_left": WarpInfo(tiles={}, fallback=Metatile(88))}},
    )
    assert tm.has_behavior_override(5, "stairs_left")
    assert not tm.has_behavior_override(5, "stairs_right")
    assert not tm.has_behavior_override(6, "stairs_left")


def test_load_tile_map_behavior_overrides_section(tmp_path: Path) -> None:
    """load_tile_map parses a 'behavior_overrides' section additively — 'warps'
    keeps working unchanged alongside it."""
    table = {
        "tilesets": {"5": {"primary": "gTileset_P", "secondary": "gTileset_S"}},
        "tiles": {"5": {}},
        "warps": {"5": {"metatile": 55, "collision": 0, "elevation": 0}},
        "behavior_overrides": {
            "5": {
                "stairs_left": {
                    "tiles": {"[[0,700]]": 20},
                    "fallback": 88,
                },
                "stairs_right": {"metatile": 89, "collision": 0, "elevation": 0},
            }
        },
    }
    tpath = tmp_path / "tileset_map.json"
    tpath.write_text(json.dumps(table), encoding="utf-8")

    tm = load_tile_map(tpath, passages_path=None)

    assert tm.behavior_for_column(5, "stairs_left", _stair_key()).metatile_id == 20
    assert tm.behavior_for_column(5, "stairs_left", _other_key()).metatile_id == 88
    # legacy single-metatile shape for stairs_right resolves for any column too
    assert tm.behavior_for_column(5, "stairs_right", _stair_key()).metatile_id == 89
    # warps untouched
    assert tm.warp(5) == Metatile(55, 0, 0)


def test_load_tile_map_behavior_overrides_unknown_tileset_raises(tmp_path: Path) -> None:
    table = {
        "tilesets": {"5": {"primary": "gTileset_P", "secondary": "gTileset_S"}},
        "tiles": {"5": {}},
        "behavior_overrides": {
            "6": {"stairs_left": {"metatile": 20, "collision": 0, "elevation": 0}}
        },
    }
    tpath = tmp_path / "tileset_map.json"
    tpath.write_text(json.dumps(table), encoding="utf-8")

    with pytest.raises(ValueError, match="behavior_overrides"):
        load_tile_map(tpath, passages_path=None)


def test_load_tile_map_behavior_overrides_unknown_kind_raises(tmp_path: Path) -> None:
    table = {
        "tilesets": {"5": {"primary": "gTileset_P", "secondary": "gTileset_S"}},
        "tiles": {"5": {}},
        "behavior_overrides": {
            "5": {"waterfall": {"metatile": 20, "collision": 0, "elevation": 0}}
        },
    }
    tpath = tmp_path / "tileset_map.json"
    tpath.write_text(json.dumps(table), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown kind"):
        load_tile_map(tpath, passages_path=None)
