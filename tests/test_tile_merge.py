"""Synthetic tests for the corpus-wide tile merge (tile_merge.py). No Uranium data."""
from __future__ import annotations

import numpy as np
import pytest

from rpg2gba.tileset_converter.graphics import tile_merge as tm
from rpg2gba.tileset_converter.graphics.emit import (
    LAYER_COVERED,
    LAYER_NORMAL,
    MetatileImage,
    _flip_canonical_multi,
)
from rpg2gba.tileset_converter.graphics.rom_quantize import ROM_FAMILY_PARAMS
from rpg2gba.tileset_converter.graphics.shared_palettes import (
    GREEN_G3T,
    ROCK_V1,
    classify_tile,
)

PARAMS = tm.MergeParams()  # k_nature=16, k_other=4, d=24


def _textured(palette: np.ndarray, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    q = np.zeros((8, 8, 4), dtype=np.uint8)
    idx = rng.integers(0, len(palette), size=(8, 8))
    q[..., :3] = palette[idx]
    q[..., 3] = 255
    return q


def _rock(seed: int = 1) -> np.ndarray:
    return _textured(np.asarray(ROCK_V1, dtype=np.uint8), seed)


def _green(seed: int = 1) -> np.ndarray:
    return _textured(np.asarray(GREEN_G3T[0], dtype=np.uint8), seed)


def _other(seed: int = 1) -> np.ndarray:
    pal = np.array([[200, 30, 30], [30, 30, 200], [250, 250, 20], [20, 20, 20]], np.uint8)
    return _textured(pal, seed)


def _group(q: np.ndarray) -> str:
    return classify_tile(q, family_params=ROM_FAMILY_PARAMS).group or "other"


def _bump(q: np.ndarray, n: int, palette: np.ndarray | None = None) -> np.ndarray:
    """Copy of q with the first n pixels moved by more than d in some channel.  With a
    palette, the replacement is another palette colour (keeps rock/green classification)."""
    out = q.copy()
    flat = out.reshape(-1, 4)
    for i in range(n):
        cur = flat[i, :3].astype(int)
        if palette is None:
            flat[i, 0] = np.uint8(cur[0] + 60 if cur[0] < 150 else cur[0] - 60)
        else:
            far = [c for c in np.asarray(palette, dtype=int)
                   if int(np.abs(c - cur).max()) > PARAMS.d + 5]
            flat[i, :3] = np.asarray(far[0], dtype=np.uint8)
    return out


def _mt(bottom_quads: list[np.ndarray], top_quads: list[np.ndarray] | None = None,
        *, behavior: int = 0, layer_type: int = LAYER_COVERED,
        frames=None) -> MetatileImage:
    def lay(quads):
        img = np.zeros((16, 16, 4), dtype=np.uint8)
        for q, (r, c) in zip(quads, tm._POSITIONS):
            img[r:r + 8, c:c + 8] = q
        return img
    top = lay(top_quads) if top_quads else np.zeros((16, 16, 4), np.uint8)
    return MetatileImage(lay(bottom_quads), top, layer_type, behavior, frames)


def _table_for(mts: list[MetatileImage], params: tm.MergeParams = PARAMS) -> tm.MergeTable:
    return tm.build_merge_table(tm.collect_quads((m, 1) for m in mts), params)


def _canon(q: np.ndarray) -> tuple[bytes, np.ndarray]:
    k, tr, _h, _v = _flip_canonical_multi([q])
    return k, tr[0]


def test_synthetic_colours_classify_as_intended():
    assert _group(_rock()) == "rock"
    assert _group(_green()) == "green"
    assert _group(_other()) == "other"


def test_hflip_near_duplicate_merges_with_orientation_and_pixels():
    base = _other(3)
    near = _bump(base, 2)[:, ::-1]            # 2 pixels differ, mirrored
    heavy = tm.collect_quads([(_mt([base] * 4), 100), (_mt([near] * 4), 1)])
    table = tm.build_merge_table(heavy, PARAMS)
    bk, _ = _canon(base)
    nk, _ = _canon(near)
    rk, o = table.rep_for(nk)
    assert rk == table.rep_for(bk)[0]
    assert rk == bk or rk == nk
    out = table.apply_metatile(_mt([near, near, near, near]))
    # the output quadrant is the representative expressed in the near tile's own orientation:
    # it must be within K of `near` (the replacement is a mirror-aware approximation)
    got = out.bottom[0:8, 0:8]
    diff = np.abs(got[..., :3].astype(int) - near[..., :3].astype(int)).max(-1)
    assert int((diff > PARAMS.d).sum()) <= PARAMS.k_other
    # and exactly equal to the base tile when base is the representative
    if rk == bk:
        assert np.array_equal(got, base[:, ::-1]) or np.array_equal(got, base)
        assert np.array_equal(got, base[:, ::-1])  # mirrored placement preserved


def test_alpha_shape_mismatch_never_merges():
    a = _other(4)
    b = a.copy()
    b[0, 0, 3] = 0
    table = _table_for([_mt([a, a, a, a]), _mt([b, b, b, b])])
    assert table.rep_for(_canon(a)[0])[0] != table.rep_for(_canon(b)[0])[0]
    assert tm.build_merge_table(tm.collect_quads([(_mt([a] * 4), 1), (_mt([b] * 4), 1)]),
                                tm.MergeParams(16, 255, 255)).stats()["reps"] == 2


@pytest.mark.parametrize("maker,k_field,pal", [
    (_other, "k_other", None),
    (_green, "k_nature", GREEN_G3T[0]),
    (_rock, "k_nature", ROCK_V1)])
def test_k_boundary_per_group(maker, k_field, pal):
    params = tm.MergeParams(k_nature=5, k_other=2, d=24)
    k = getattr(params, k_field)
    base = maker(7)
    for n_diff, should_merge in ((k, True), (k + 1, False)):
        near = _bump(base, n_diff, pal)
        assert _group(near) == _group(base)
        weighted = [(_mt([base] * 4), 50), (_mt([near] * 4), 1)]
        table = tm.build_merge_table(tm.collect_quads(weighted), params)
        merged = table.rep_for(_canon(near)[0])[0] == table.rep_for(_canon(base)[0])[0]
        assert merged is should_merge, (maker.__name__, n_diff)


def test_cross_group_never_merges():
    g = _green(2)
    # a tile the classifier calls rock but identical alpha: make it differ little from g
    r = _rock(2)
    assert _group(g) != _group(r)
    huge = tm.MergeParams(k_nature=64, k_other=64, d=255)
    table = tm.build_merge_table(tm.collect_quads([(_mt([g] * 4), 5), (_mt([r] * 4), 1)]), huge)
    assert table.rep_for(_canon(g)[0])[0] != table.rep_for(_canon(r)[0])[0]


def test_animated_and_empty_quadrants_untouched():
    base, near = _other(5), _bump(_other(5), 1)
    anim_f1 = _other(9)
    frames = [(np.zeros((16, 16, 4), np.uint8), np.zeros((16, 16, 4), np.uint8))]
    mt = _mt([near, base, base, base])
    mt.frames = [(mt.bottom.copy(), mt.top.copy())]
    mt.frames[0][0][0:8, 0:8] = anim_f1   # quadrant 0 animates
    table = _table_for([_mt([base] * 4), _mt([near] * 4), mt])
    out = table.apply_metatile(mt)
    assert np.array_equal(out.bottom[0:8, 0:8], mt.bottom[0:8, 0:8])   # animated: untouched
    assert out.frames is mt.frames
    assert np.array_equal(out.top, mt.top)                              # empty top untouched
    del frames


def test_same_quad_gets_identical_output_across_metatiles():
    base, near = _other(6), _bump(_other(6), 2)
    m1 = _mt([near, base, base, base])
    m2 = _mt([base, base, base, near], layer_type=LAYER_NORMAL, behavior=3)
    table = _table_for([_mt([base] * 4), _mt([near] * 4), m1, m2])
    o1, o2 = table.apply_metatile(m1), table.apply_metatile(m2)
    assert np.array_equal(o1.bottom[0:8, 0:8], o2.bottom[8:16, 8:16])
    assert (o2.layer_type, o2.behavior) == (LAYER_NORMAL, 3)
    assert m1.bottom[0, 0, 0] == near[0, 0, 0]   # input not mutated


def test_determinism_and_order_independence():
    mts = [_mt([_other(s), _green(s), _rock(s), _other(s + 50)]) for s in range(30)]
    t1, t2 = _table_for(mts), _table_for(list(reversed(mts)))
    assert t1._assign == t2._assign
    assert t1.stats() == t2.stats()


def test_bucketed_equals_bruteforce_on_random_quads():
    rng = np.random.default_rng(1234)
    base = [_other(s) for s in range(12)] + [_green(s) for s in range(6)]
    quads: dict[bytes, tuple[np.ndarray, int]] = {}
    while len(quads) < 400:
        q = base[int(rng.integers(len(base)))].copy()
        for _ in range(int(rng.integers(0, 12))):
            y, x = rng.integers(0, 8, size=2)
            q[y, x, :3] = np.clip(q[y, x, :3].astype(int) + rng.integers(-70, 70, 3), 0, 255)
        if rng.random() < 0.25:
            q[int(rng.integers(0, 8)), int(rng.integers(0, 8)), 3] = 0
        if rng.random() < 0.3:
            q = q[::-1, :] if rng.random() < 0.5 else q[:, ::-1]
        if int(q[..., 3].max()) == 0:
            continue
        k, c = _canon(np.ascontiguousarray(q))
        quads[k] = (c, int(rng.integers(1, 100)))
    for params in (PARAMS, tm.MergeParams(16, 16, 24), tm.MergeParams(8, 8, 60),
                   tm.MergeParams(30, 30, 10)):
        a = tm.build_merge_table(quads, params)
        b = tm.build_merge_table(quads, params, _bucketed=False)
        assert a._assign == b._assign
        assert a.stats()["reps"] < len(quads)   # the test actually exercises merging


def test_dedup_metatiles_remap_and_distinctness():
    q = _other(8)
    a = _mt([q] * 4)
    b = _mt([q] * 4)
    c = _mt([q] * 4, behavior=2)
    d = _mt([q] * 4, layer_type=LAYER_NORMAL)
    e = _mt([_other(9)] * 4)
    f = _mt([q] * 4)
    f.frames = [(f.bottom.copy(), f.top.copy())]
    uniq, remap = tm.dedup_metatiles([a, b, c, d, e, a, f])
    assert remap == [0, 0, 1, 2, 3, 0, 4]
    assert uniq == [a, c, d, e, f]


def test_save_load_round_trip(tmp_path):
    mts = [_mt([_other(s), _green(s), _rock(s), _other(s + 7)]) for s in range(10)]
    t = _table_for(mts)
    t.fingerprint = "abc"
    p = tmp_path / "t.npz"
    t.save(p)
    u = tm.MergeTable.load(p)
    assert u._assign == t._assign and u.params == t.params and u.fingerprint == "abc"
    assert u.stats() == t.stats()
    for m in mts:
        assert np.array_equal(u.apply_metatile(m).bottom, t.apply_metatile(m).bottom)


def test_rep_for_unknown_key_raises():
    t = _table_for([_mt([_other(1)] * 4)])
    with pytest.raises(KeyError, match="stale"):
        t.rep_for(b"\x00" * 256)
    with pytest.raises(KeyError, match="stale"):
        t.apply_metatile(_mt([_other(99)] * 4))
