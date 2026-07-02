"""Tests for synthetic tileset id resolution in load_tile_map / _load_oracle."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.tileset_converter.tile_map import load_tile_map


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
        str(real_id): {"passages": passages, "priorities": [0] * n},
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
