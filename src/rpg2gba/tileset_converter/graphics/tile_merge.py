"""Corpus-wide near-duplicate merge of 8x8 tiles, plus lossless metatile dedup.

GBA tilesets cap at 1024 tiles / 1024 metatiles. A big city map (Uranium map 40)
needs more, so we merge near-identical 8x8 static quadrants on ORIGINAL (pre-
quantization) pixels. Continuity across the game is required: the same original
tile must become the same replacement on every map, so the table is built ONCE
from every map in the corpus (:func:`corpus_merge_table`) and applied everywhere
(:meth:`MergeTable.apply_metatile`).

Merge rule (per group, most-used quad first becomes a representative):

* groups: ``classify_tile(...).group`` -- "rock" / "green" use ``k_nature``,
  everything else ("other") uses ``k_other``; never merge across groups.
* a candidate merges into the (representative, orientation) with the fewest
  "differing" pixels if that count is <= K.  Alpha masks (alpha > 0) must be
  identical in the compared orientation; a pixel differs if any RGB channel
  differs by more than ``d``; only candidate-opaque pixels are counted.
* animated quadrants (effective frame count > 1) never merge.

Orientation ``o`` means ``ORIENTS[o](rep_array) ~= candidate canonical array``.
Representative lookup is bucketed by exact alpha mask and prefiltered on mean RGB
with a provably safe radius, so it returns exactly what brute force would.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np

from rpg2gba.tileset_converter.graphics.emit import (
    MetatileImage,
    _apply_flip,
    _effective_frames,
    _flip_canonical_multi,
    _slot_frames_for_metatile,
)
from rpg2gba.tileset_converter.graphics.rom_quantize import ROM_FAMILY_PARAMS
from rpg2gba.tileset_converter.graphics.shared_palettes import classify_tile

logger = logging.getLogger(__name__)

ORIENTS = (
    lambda q: q,
    lambda q: q[:, ::-1],
    lambda q: q[::-1, :],
    lambda q: q[::-1, ::-1],
)
_POSITIONS = [(0, 0), (0, 8), (8, 0), (8, 8)]
_GROUPS = ("rock", "green", "other")
_QUAD_BYTES = 8 * 8 * 4

CORPUS_UNRENDERABLE: dict[int, str] = {
    71: "Floatstone autotile asset missing from the Uranium source tree",
}

_REPO = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class MergeParams:
    k_nature: int = 16   # rock + green groups
    k_other: int = 4     # everything else
    d: int = 24          # per-pixel max-channel difference that counts as "differs"

    def k_for(self, group: str) -> int:
        return self.k_nature if group in ("rock", "green") else self.k_other


def _group_of(arr: np.ndarray) -> str:
    return classify_tile(arr, family_params=ROM_FAMILY_PARAMS).group or "other"


# --------------------------------------------------------------------------- merge core

class _Entries:
    """Growable store of representative orientations, in insertion order."""

    def __init__(self, sub_idx: np.ndarray | None = None) -> None:
        self.n = 0
        # Flat pixel indices (all opaque in this bucket's mask) for the cheap
        # lower-bound prefilter; None disables it.
        self.sub_idx = sub_idx
        self.subs = np.zeros((64, 0 if sub_idx is None else len(sub_idx), 3), dtype=np.int16)
        self.arrs = np.zeros((64, 8, 8, 4), dtype=np.uint8)
        self.means = np.zeros((64, 3), dtype=np.float64)
        self.owner = np.zeros(64, dtype=np.int64)
        self.orient = np.zeros(64, dtype=np.int8)

    def add(self, arr: np.ndarray, mean: np.ndarray, owner: int, orient: int) -> None:
        if self.n == len(self.arrs):
            cap = self.n * 2
            self.arrs = np.concatenate([self.arrs, np.zeros_like(self.arrs)])[:cap]
            self.subs = np.concatenate([self.subs, np.zeros_like(self.subs)])[:cap]
            self.means = np.concatenate([self.means, np.zeros_like(self.means)])[:cap]
            self.owner = np.concatenate([self.owner, np.zeros_like(self.owner)])[:cap]
            self.orient = np.concatenate([self.orient, np.zeros_like(self.orient)])[:cap]
        self.arrs[self.n] = arr
        if self.sub_idx is not None:
            self.subs[self.n] = arr.reshape(-1, 4)[self.sub_idx, :3]
        self.means[self.n] = mean
        self.owner[self.n] = owner
        self.orient[self.n] = orient
        self.n += 1


def _subset_for(mask: np.ndarray, k: int) -> np.ndarray | None:
    """Evenly spread k+9 opaque pixels of ``mask`` (None when the mask has <= k+9).

    The number of differing pixels inside any subset is <= the total count, so
    "more than K differ inside the subset" safely rules a representative out."""
    opaque = np.nonzero(mask.reshape(-1))[0]
    want = k + 9
    if len(opaque) <= want:
        return None
    return opaque[np.linspace(0, len(opaque) - 1, want).astype(int)]


def _mean_rgb(arr: np.ndarray) -> np.ndarray:
    opaque = arr[..., 3] > 0
    return arr[..., :3][opaque].mean(axis=0)


def _safe_radius(n_opaque: int, k: int, d: int) -> float:
    """Upper bound on |mean_c(cand) - mean_c(rep)| for any channel when at most
    ``k`` of the ``n_opaque`` shared-mask pixels differ by > d (<= 255) and the
    rest by <= d.  Padded so float rounding can never exclude a valid merge."""
    k = min(k, n_opaque)
    return ((n_opaque - k) * d + k * 255) / n_opaque + 1e-6


def _merge_group(
    order: list[bytes],
    arrays: dict[bytes, np.ndarray],
    k: int,
    d: int,
    *,
    bucketed: bool = True,
) -> dict[bytes, tuple[bytes, int]]:
    """Greedy merge of one group's quads (already in processing order).

    ``bucketed=False`` is the brute-force reference (every orientation compared,
    mask equality tested explicitly); both must return identical assignments."""
    assign: dict[bytes, tuple[bytes, int]] = {}
    reps: list[bytes] = []
    buckets: dict[bytes, _Entries] = {}
    t0 = time.monotonic()
    for i, q in enumerate(order):
        if i and i % 2000 == 0:
            logger.info("tile merge: %d/%d candidates, %d reps, %.0fs",
                        i, len(order), len(reps), time.monotonic() - t0)
        a = arrays[q]
        mask = a[..., 3] > 0
        n_opaque = int(mask.sum())
        mkey = np.packbits(mask).tobytes() if bucketed else b""
        ent = buckets.get(mkey)
        best: tuple[bytes, int] | None = None
        if ent is not None and ent.n:
            cand = a[..., :3].astype(np.int16)
            idx = np.arange(ent.n)
            if bucketed:
                if n_opaque == 0:
                    raise ValueError("fully transparent quad reached the merge")
                rad = _safe_radius(n_opaque, k, d)
                near = np.abs(ent.means[: ent.n] - _mean_rgb(a)).max(axis=1) <= rad
                idx = np.nonzero(near)[0]
                if ent.sub_idx is not None and len(idx):
                    cs = a.reshape(-1, 4)[ent.sub_idx, :3].astype(np.int16)
                    nd = (np.abs(ent.subs[idx] - cs[None]).max(axis=-1) > d).sum(axis=1)
                    idx = idx[nd <= k]
            if len(idx):
                sub = ent.arrs[idx]
                if not bucketed:
                    same = ((sub[..., 3] > 0) == mask).all(axis=(1, 2))
                diff = np.abs(sub[..., :3].astype(np.int16) - cand[None]).max(axis=-1)
                bad = ((diff > d) & mask).sum(axis=(1, 2))
                if not bucketed:
                    bad = np.where(same, bad, 999)
                j = int(bad.argmin())
                if bad[j] <= k:
                    e = int(idx[j])
                    best = (reps[int(ent.owner[e])], int(ent.orient[e]))
        if best is None:
            ri = len(reps)
            reps.append(q)
            assign[q] = (q, 0)
            if ent is None:
                ent = buckets[mkey] = _Entries(_subset_for(mask, k) if bucketed else None)
            for o, fn in enumerate(ORIENTS):
                oa = np.ascontiguousarray(fn(a))
                omask = oa[..., 3] > 0
                ok = np.packbits(omask).tobytes() if bucketed else b""
                oe = buckets.get(ok)
                if oe is None:
                    oe = buckets[ok] = _Entries(_subset_for(omask, k) if bucketed else None)
                oe.add(oa, _mean_rgb(oa) if bucketed else np.zeros(3), ri, o)
        else:
            assign[q] = best
    return assign


def _static_slot_mask(mt: MetatileImage) -> tuple[bool, ...]:
    """Per quadrant slot: True if it is static (one effective frame)."""
    return tuple(len(_effective_frames(fr)) == 1 for fr in _slot_frames_for_metatile(mt))


# --------------------------------------------------------------------------- table

class MergeTable:
    """key -> (representative key, orientation) for every corpus static quad."""

    def __init__(
        self,
        params: MergeParams,
        assign: dict[bytes, tuple[bytes, int]],
        groups: dict[bytes, str],
        weights: dict[bytes, int] | None = None,
        fingerprint: str = "",
    ) -> None:
        self.params = params
        self._assign = assign
        self._groups = groups
        self._weights = weights or {}
        self.fingerprint = fingerprint

    def rep_for(self, key: bytes) -> tuple[bytes, int]:
        try:
            return self._assign[key]
        except KeyError:
            raise KeyError(
                "merge table is stale / quad not in corpus: a static 8x8 quad "
                f"(key sha1 {hashlib.sha1(key).hexdigest()[:12]}) was never seen when "
                "the table was built; rebuild it with corpus_merge_table"
            ) from None

    def apply_metatile(self, mt: MetatileImage) -> MetatileImage:
        bot, top = mt.bottom.copy(), mt.top.copy()
        # A static quadrant of an ANIMATED metatile repeats in every frame; the
        # replacement must go into every frame too, or frame 0 alone changes and
        # emit sees a spurious animated slot (the I2a overhang glitch).
        frames = mt.frames  # copied on the first replacement only
        merged_from = {k: list(v) for k, v in (mt.merged_from or {}).items()}
        for si, fr in enumerate(_slot_frames_for_metatile(mt)):
            fr = _effective_frames(fr)
            if len(fr) > 1 or all(int(f[..., 3].max()) == 0 for f in fr):
                continue
            key, tr, h, v = _flip_canonical_multi(fr)
            rk, o = self.rep_for(key)
            if rk == key:
                continue
            rep = np.frombuffer(rk, dtype=np.uint8).reshape(8, 8, 4)
            q = _apply_flip(np.asarray(ORIENTS[o](rep), dtype=np.uint8), h, v)
            r, c = _POSITIONS[si % 4]
            merged_from.setdefault(si, []).append(np.array(fr[0], dtype=np.uint8))
            if frames and frames is mt.frames:
                frames = [(fb.copy(), ft.copy()) for fb, ft in mt.frames]
            for layer in [bot if si < 4 else top] + [f[0 if si < 4 else 1] for f in frames or []]:
                layer[r:r + 8, c:c + 8] = q
        out = MetatileImage(bot, top, mt.layer_type, mt.behavior, frames, merged_from or None)
        if _static_slot_mask(out) != _static_slot_mask(mt):
            raise AssertionError(
                "merge changed which quadrants are animated (static/animated slot "
                f"mask {_static_slot_mask(mt)} -> {_static_slot_mask(out)})"
            )
        return out

    def stats(self) -> dict:
        quads = Counter(self._groups[q] for q in self._assign)
        reps = Counter(self._groups[q] for q, (r, _o) in self._assign.items() if r == q)
        return {
            "params": asdict(self.params),
            "quads": sum(quads.values()),
            "quads_by_group": {g: quads.get(g, 0) for g in _GROUPS},
            "reps_by_group": {g: reps.get(g, 0) for g in _GROUPS},
            "reps": sum(reps.values()),
        }

    def save(self, path: Path) -> None:
        path = Path(path)
        keys = sorted(self._assign)
        index = {k: i for i, k in enumerate(keys)}
        key_arr = (np.frombuffer(b"".join(keys), dtype=np.uint8).reshape(len(keys), _QUAD_BYTES)
                   if keys else np.zeros((0, _QUAD_BYTES), dtype=np.uint8))
        meta = {"params": asdict(self.params), "fingerprint": self.fingerprint,
                "groups": list(_GROUPS)}
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            np.savez_compressed(
                f,
                keys=key_arr,
                rep_index=np.array([index[self._assign[k][0]] for k in keys], dtype=np.int64),
                orient=np.array([self._assign[k][1] for k in keys], dtype=np.int8),
                group=np.array([_GROUPS.index(self._groups[k]) for k in keys], dtype=np.int8),
                weight=np.array([self._weights.get(k, 0) for k in keys], dtype=np.int64),
                meta=np.frombuffer(json.dumps(meta, sort_keys=True).encode("utf-8"),
                                   dtype=np.uint8),
            )

    @classmethod
    def load(cls, path: Path) -> "MergeTable":
        with np.load(Path(path), allow_pickle=False) as z:
            meta = json.loads(z["meta"].tobytes().decode("utf-8"))
            key_arr, rep_index = z["keys"], z["rep_index"]
            orient, group, weight = z["orient"], z["group"], z["weight"]
        keys = [key_arr[i].tobytes() for i in range(len(key_arr))]
        names = meta["groups"]
        assign = {k: (keys[int(rep_index[i])], int(orient[i])) for i, k in enumerate(keys)}
        groups = {k: names[int(group[i])] for i, k in enumerate(keys)}
        weights = {k: int(weight[i]) for i, k in enumerate(keys)}
        return cls(MergeParams(**meta["params"]), assign, groups, weights, meta["fingerprint"])


# --------------------------------------------------------------------------- builders

def collect_quads(
    weighted: Iterable[tuple[MetatileImage, int]],
) -> dict[bytes, tuple[np.ndarray, int]]:
    """canonical static quad key -> (canonical 8x8x4 array, summed weight).

    Each distinct quad counts once per metatile (times that metatile's weight).
    Animated and fully transparent quadrants are skipped."""
    out: dict[bytes, tuple[np.ndarray, int]] = {}
    for mt, w in weighted:
        seen: set[bytes] = set()
        for fr in _slot_frames_for_metatile(mt):
            fr = _effective_frames(fr)
            if len(fr) > 1 or all(int(f[..., 3].max()) == 0 for f in fr):
                continue
            key, tr, _h, _v = _flip_canonical_multi(fr)
            if key in seen:
                continue
            seen.add(key)
            prev = out.get(key)
            out[key] = (prev[0] if prev else np.ascontiguousarray(tr[0]),
                        (prev[1] if prev else 0) + max(1, int(w)))
    return out


def build_merge_table(
    quads: dict[bytes, tuple[np.ndarray, int]], params: MergeParams = MergeParams(),
    *, _bucketed: bool = True,
) -> MergeTable:
    arrays = {k: np.ascontiguousarray(a, dtype=np.uint8) for k, (a, _w) in quads.items()}
    weights = {k: int(w) for k, (_a, w) in quads.items()}
    groups = {k: _group_of(a) for k, a in arrays.items()}
    assign: dict[bytes, tuple[bytes, int]] = {}
    for g in _GROUPS:
        order = sorted((k for k in arrays if groups[k] == g), key=lambda k: (-weights[k], k))
        if order:
            assign.update(_merge_group(order, arrays, params.k_for(g), params.d,
                                       bucketed=_bucketed))
    return MergeTable(params, assign, groups, weights)


def _mt_signature(mt: MetatileImage) -> tuple:
    return (
        mt.bottom.tobytes(), mt.top.tobytes(),
        tuple((b.tobytes(), t.tobytes()) for b, t in (mt.frames or [])),
        mt.behavior, mt.layer_type,
    )


def dedup_metatiles(mts: list[MetatileImage]) -> tuple[list[MetatileImage], list[int]]:
    """Lossless metatile merge: identical (bottom, top, all frames, behavior,
    layer_type) collapse to the first occurrence; ``remap[old] = new``.

    The survivor keeps every collapsed copy's ``merged_from`` originals (a slot a copy
    used as itself counts as its own original), so the palette refit still sees all
    the art each tile is drawn for."""
    seen: dict[tuple, int] = {}
    unique: list[MetatileImage] = []
    remap: list[int] = []
    for mt in mts:
        sig = _mt_signature(mt)
        idx = seen.get(sig)
        if idx is None:
            idx = seen[sig] = len(unique)
            unique.append(mt)
        elif mt.merged_from or unique[idx].merged_from:
            unique[idx] = _union_merged_from(unique[idx], mt)
        remap.append(idx)
    return unique, remap


def _slot_originals(mt: MetatileImage, slot: int) -> list[np.ndarray]:
    """The art a slot is drawn for: its merged originals, else its own quad."""
    if mt.merged_from and slot in mt.merged_from:
        return mt.merged_from[slot]
    return [np.asarray(_slot_frames_for_metatile(mt)[slot][0], dtype=np.uint8)]


def _union_merged_from(a: MetatileImage, b: MetatileImage) -> MetatileImage:
    slots = set(a.merged_from or {}) | set(b.merged_from or {})
    merged: dict[int, list[np.ndarray]] = {}
    for s in sorted(slots):
        seen: dict[bytes, np.ndarray] = {}
        for q in _slot_originals(a, s) + _slot_originals(b, s):
            seen.setdefault(q.tobytes(), q)
        merged[s] = list(seen.values())
    return replace(a, merged_from=merged)


def merge_and_dedup_metatiles(
    mts: list[MetatileImage], table: MergeTable,
) -> tuple[list[MetatileImage], list[int]]:
    """THE ROM transformation (viewer budget readout shares it): game-wide tile merge
    on every metatile, then the lossless metatile dedup. ``remap[old] = new`` index.

    Dedup keys on (art, frames, behavior, layer_type), so door / stair / terrain
    behavior copies and covered/normal layers never fold into one another."""
    return dedup_metatiles([table.apply_metatile(mt) for mt in mts])


def rom_merge_table(tilesets_json: Path) -> MergeTable:
    """The corpus table for the ROM build: ``<build dir>/tile_merge_table.npz`` where the
    build dir is ``tilesets_json``'s parent (holds ``maps/``). Cache hit is instant; a
    stale cache rebuilds from the whole corpus (minutes)."""
    build = Path(tilesets_json).parent
    return corpus_merge_table(
        MergeParams(), out_dir=build, tilesets_json=Path(tilesets_json),
        cache_path=build / "tile_merge_table.npz",
    )


# --------------------------------------------------------------------------- corpus

def _strip_map_ids() -> set[int]:
    data = json.loads((_REPO / "reference" / "strip_list.json").read_text(encoding="utf-8"))
    return {int(e["id"]) for e in data.get("maps", [])}


def _fingerprint(params: MergeParams, files: list[Path]) -> str:
    h = hashlib.sha256(json.dumps(asdict(params), sort_keys=True).encode("utf-8"))
    for p in sorted(files):
        st = p.stat()
        h.update(f"{p}|{st.st_size}|{st.st_mtime_ns}\n".encode("utf-8"))
    return h.hexdigest()


def _cached_fingerprint(path: Path) -> str | None:
    try:
        with np.load(path, allow_pickle=False) as z:
            return json.loads(z["meta"].tobytes().decode("utf-8")).get("fingerprint")
    except (OSError, ValueError, KeyError):
        return None


def corpus_merge_table(
    params: MergeParams = MergeParams(),
    *,
    out_dir: Path,
    tilesets_json: Path,
    cache_path: Path,
    map_ids: Iterable[int] | None = None,
) -> MergeTable:
    """Render every corpus map, collect weighted quads, build + cache the table."""
    # Imported here: build_slice_tilesets pulls in the whole tileset stack.
    from rpg2gba.tileset_converter.graphics import build_slice_tilesets as bst
    from rpg2gba.tileset_converter.layout import column_key
    from rpg2gba.tileset_converter.map_set import WALKER_EMPTY_MAP_IDS

    out_dir, tilesets_json, cache_path = Path(out_dir), Path(tilesets_json), Path(cache_path)
    maps_dir = out_dir / "maps"
    if map_ids is None:
        skip = _strip_map_ids() | set(WALKER_EMPTY_MAP_IDS) | set(CORPUS_UNRENDERABLE)
        files = [p for p in sorted(maps_dir.glob("Map*.json"))
                 if int(p.stem[3:]) not in skip]
    else:
        files = [maps_dir / f"Map{int(m):03d}.json" for m in map_ids]
    fp = _fingerprint(params, [*files, tilesets_json])
    if cache_path.exists() and _cached_fingerprint(cache_path) == fp:
        logger.info("tile merge table: cache hit %s", cache_path)
        return MergeTable.load(cache_path)

    t0 = time.monotonic()
    by_ts: dict[int, list[tuple[int, dict]]] = {}
    for p in files:
        mj = json.loads(p.read_text(encoding="utf-8"))
        by_ts.setdefault(int(mj["tileset_id"]), []).append((int(p.stem[3:]), mj))

    col_cache: dict[tuple[int, tuple], MetatileImage] = {}
    mt_weight: dict[int, list] = {}   # id(mt) -> [mt, weight]
    done = 0
    for ts in sorted(by_ts):
        rast = bst._default_rasterizer(ts, tilesets_json, None)
        priorities = bst._load_priorities(tilesets_json, ts)
        passages = bst._load_passages(tilesets_json, ts)
        tags = bst._load_terrain_tags(tilesets_json, ts)
        for map_id, mj in by_ts[ts]:
            grid = bst._masked_grid_of(mj, rast.max_static_tile_id(), map_id=map_id)
            cells: Counter = Counter()
            for y in range(grid.ysize):
                for x in range(grid.xsize):
                    key = column_key(grid, x, y)
                    if key:
                        cells[key] += 1
            for key, n in cells.items():
                mt = col_cache.get((ts, key))
                if mt is None:
                    mt = bst._render_column(key, rast, priorities, passages, tags,
                                            n_frames=bst.column_n_frames(key, rast))
                    col_cache[(ts, key)] = mt
                ent = mt_weight.setdefault(id(mt), [mt, 0])
                ent[1] += n
            done += 1
            logger.info("tile merge: rendered map %03d (ts %d) [%d/%d, %.0fs]",
                        map_id, ts, done, len(files), time.monotonic() - t0)

    quads = collect_quads((mt, w) for mt, w in mt_weight.values())
    logger.info("tile merge: %d distinct static quads from %d maps; merging", len(quads), done)
    table = build_merge_table(quads, params)
    table.fingerprint = fp
    table.save(cache_path)
    logger.info("tile merge: built in %.0fs, stats %s", time.monotonic() - t0, table.stats())
    return table
