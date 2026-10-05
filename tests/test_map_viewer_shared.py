"""Shared-tiles helpers: pair matrix, by-id vs by-image, flip canonicalisation, null ROM."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import map_viewer_common as mvc  # noqa: E402


def _tile(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = rng.integers(0, 255, (8, 8, 4), dtype=np.uint8)
    t[..., 3] = 255
    return t


def test_canon_tile_hash_flip_equal_and_distinct():
    t = _tile(1)
    h = mvc.canon_tile_hash(t)
    assert h == mvc.canon_tile_hash(t[:, ::-1])
    assert h == mvc.canon_tile_hash(t[::-1, :])
    assert h == mvc.canon_tile_hash(t[::-1, ::-1])
    assert h != mvc.canon_tile_hash(_tile(2))
    # a transpose is NOT a flip
    assert h != mvc.canon_tile_hash(np.ascontiguousarray(t.transpose(1, 0, 2)))


def test_canon_tile_hash_transparent_is_none():
    assert mvc.canon_tile_hash(np.zeros((8, 8, 4), dtype=np.uint8)) is None


def test_rom_metatile_hashes_mirrored_quadrant_same_tile_different_metatile():
    t = _tile(3)
    z = np.zeros((16, 16, 4), dtype=np.uint8)
    a, b = z.copy(), z.copy()
    a[:8, :8] = t
    b[:8, :8] = t[:, ::-1]
    ha, ta = mvc.rom_metatile_hashes(a, z)
    hb, tb = mvc.rom_metatile_hashes(b, z)
    assert ta == tb and len(ta) == 1      # same ROM tile under flip canonicalisation
    assert ha != hb                        # but different decoded metatile
    assert mvc.rom_metatile_hashes(z, z) == (None, [])


def test_pair_stats_and_null():
    assert mvc.pair_stats({1, 2, 3}, {3, 4}) == {"shared": 1, "only_a": 2, "only_b": 1}
    assert mvc.pair_stats({1}, None) is None
    assert mvc.pair_stats(None, None) is None


def test_shared_cells_skips_empty_and_null():
    assert mvc.shared_cells(["a", None, "b", "a"], {"a"}) == [0, 3]
    assert mvc.shared_cells(None, {"a"}) is None
    assert mvc.shared_cells(["a"], None) is None


def _profile(w, h, ids, imgs, roms=None, tiles=None, ts=22):
    rom = roms is not None
    return {
        "w": w, "h": h, "tileset": ts,
        "rom": {"synth_tileset": 1000, "n_metatiles": 9} if rom else None,
        "sets": {
            "rmxp_id": {k for k in ids if k}, "rmxp_image": {k for k in imgs if k},
            "rom_mt": {k for k in roms if k} if rom else None,
            "rom_tile": set(tiles) if rom else None,
        },
        "cells": {"rmxp_id": ids, "rmxp_image": imgs, "rom_mt": roms},
    }


def test_build_shared_by_id_vs_by_image_and_missing_rom():
    # 31/35 same tileset: id "x" shared. 40 other tileset: no id overlap but image "i1" shared.
    p31 = _profile(2, 1, ["x", "y"], ["i1", "i2"], ["r1", "r2"], ["t1", "t2"])
    p35 = _profile(2, 1, ["x", "z"], ["i1", "i3"], ["r9", "r2"], ["t2", "t3"])
    p40 = _profile(2, 1, ["q", None], ["i1", None], None, None, ts=23)
    r = mvc.build_shared({40: p40, 31: p31, 35: p35})
    assert r["maps"] == [31, 35, 40]
    pairs = {(p["a"], p["b"]): p for p in r["pairs"]}
    assert len(pairs) == 3
    assert pairs[(31, 35)]["rmxp_id"] == {"shared": 1, "only_a": 1, "only_b": 1}
    assert pairs[(31, 35)]["rom_mt"] == {"shared": 1, "only_a": 1, "only_b": 1}
    assert pairs[(31, 35)]["rom_tile"]["shared"] == 1
    assert pairs[(31, 40)]["rmxp_id"]["shared"] == 0
    assert pairs[(31, 40)]["rmxp_image"] == {"shared": 1, "only_a": 1, "only_b": 0}
    assert pairs[(31, 40)]["rom_mt"] is None and pairs[(31, 40)]["rom_tile"] is None
    assert r["info"]["40"]["rom"] is None
    assert r["info"]["40"]["counts"]["rom_mt"] is None
    assert r["info"]["31"]["counts"] == {"rmxp_id": 2, "rmxp_image": 2, "rom_mt": 2, "rom_tile": 2}
    # per-cell: 31's cell 0 shares id with 35; 40 has no ROM cells
    assert r["cells"]["31"]["35"]["rmxp_id"] == [0]
    assert r["cells"]["31"]["35"]["rom_mt"] == [1]
    assert r["cells"]["31"]["40"]["rmxp_image"] == [0]
    assert r["cells"]["31"]["40"]["rom_mt"] is None
    assert r["cells"]["40"]["31"]["rom_mt"] is None
    assert r["cells"]["40"]["31"]["rmxp_image"] == [0]
