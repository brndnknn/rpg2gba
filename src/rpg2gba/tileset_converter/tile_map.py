"""Phase 5 §5.1 — Tile mapping table (the source of truth).

ASSIGNMENT (see PATHFINDER_STEP2_TILE_MAP_PLAN.md + PHASE5_PLAN.md §5.1)
==========
Resolve an Uranium `(tileset_id, tile_id)` to a pokeemerald `metatile_id`
(+ collision / elevation), plus the `tileset_id -> (primary, secondary)` choice.

PATHFINDER v1 = PURE PASSABILITY BUCKETS (user decision 2026-06-15)
    The P2 census found 433 distinct tiles — too many to hand-author for throwaway
    Approach-A art. So `reference/tileset_map.json` carries an empty `tiles` table
    and a per-tileset `buckets` = {passable, blocked, void} metatile triple; every
    tile resolves by its *source passability* (`output/uranium-build/tilesets.json`
    `passages`, low nibble 0 => passable). Hand-mapping high-frequency tiles into
    `tiles` (each overrides its bucket) is a later fidelity pass.

The two id spaces
    RMXP tile_id:  0 = empty;  48..383 = autotiles (48 ids each, base = 48*n);
                   >=384 = static tiles.
    GBA metatile_id: 0x000..0x1FF primary tileset, 0x200+ secondary.

Constraints
    - FAIL LOUD (CLAUDE.md §4.5): an unresolvable tile (no explicit entry AND no
      bucket for the tileset) raises with the exact ids — never silent metatile 0.
    - The bucket fallback is explicit + logged, not a silent default.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Default locations (CLAUDE.md §4.3 + the Phase-5-prep passages oracle).
DEFAULT_TILE_MAP_PATH = Path("reference/tileset_map.json")
DEFAULT_PASSAGES_PATH = Path("output/uranium-build/tilesets.json")

# pokeemerald block-packing (shared with layout.py). block u16 =
# metatile | collision<<10 | elevation<<12.
METATILE_ID_MASK = 0x03FF
COLLISION_SHIFT = 10
ELEVATION_SHIFT = 12
NUM_METATILES_IN_PRIMARY = 0x200  # secondary tileset metatiles start here

# RMXP tile-id ranges.
AUTOTILE_BASE = 48   # ids 48..383 are autotiles, 48 per autotile
STATIC_BASE = 384    # ids >= 384 are static tiles

# Bucket fallback (PATHFINDER v1): the low nibble of an RMXP passage byte is the
# directional-block mask (down/left/right/up); 0 => fully passable. Higher bits
# (e.g. 0x40) are non-collision flags and are ignored here.
PASSAGE_BLOCK_MASK = 0x0F
PASSABLE_COLLISION = 0
BLOCKED_COLLISION = 1
PASSABLE_ELEVATION = 3
BLOCKED_ELEVATION = 0

# Required top-level keys in reference/tileset_map.json. "buckets"/"stacks" are
# optional in the schema, but a tile with no explicit entry needs a bucket.
_SCHEMA = ("tilesets", "tiles")

_MAX_METATILE = METATILE_ID_MASK  # 0x3FF — anything larger truncates in to_block
_VALID_COLLISION = {0, 1, 2, 3}
_MAX_ELEVATION = 0xF


@dataclass(frozen=True)
class Metatile:
    """One resolved target block: a pokeemerald metatile id plus its movement bits."""

    metatile_id: int
    collision: int = 0
    elevation: int = 3

    def to_block(self) -> int:
        """Pack into the little-endian u16 stored in map.bin."""
        return (
            (self.metatile_id & METATILE_ID_MASK)
            | (self.collision << COLLISION_SHIFT)
            | (self.elevation << ELEVATION_SHIFT)
        )


@dataclass(frozen=True)
class TilesetChoice:
    """Which pokeemerald primary+secondary tileset draws an Uranium tileset (Q4)."""

    primary: str
    secondary: str


@dataclass(frozen=True)
class Bucket:
    """Per-tileset passability-bucket metatiles (PATHFINDER v1): a generic passable
    (floor/ground), blocked (wall/obstacle), and void (border/empty) metatile."""

    passable: int
    blocked: int
    void: int


@dataclass(frozen=True)
class WarpInfo:
    """Per-tileset warp metatiles (fix #1, walker_checkpoint2_findings.md).

    ``tiles`` maps a serialized door column key (``serialize_column_key``) to the
    MB_NON_ANIMATED_DOOR metatile that preserves that column's real art. ``fallback``
    is the transparent door metatile used for warp coords whose column is empty or
    out-of-atlas (or, in the legacy single-metatile table shape, for EVERY column —
    see ``load_tile_map``)."""

    tiles: dict[str, "Metatile"]
    fallback: "Metatile | None" = None


def serialize_column_key(key: tuple[tuple[int, int], ...]) -> str:
    """Canonical, deterministic serialization of a column key, shared by the overlay
    writer (build_slice_tilesets) and the reader (lookup_column) so keys always match.
    `key` is the cell's non-empty stacked tiles as (z, tile_id) pairs, bottom-first
    (z ascending)."""
    return json.dumps([[z, t] for z, t in key], separators=(",", ":"))


def normalize_tile_id(tile_id: int) -> int:
    """Fold an autotile variant (48..383) to its base 48*n; pass 0 and statics through.

    All 48 variants of an autotile are the same terrain (Approach A maps them to one
    metatile), so the explicit `tiles` table is keyed by base id only."""
    if AUTOTILE_BASE <= tile_id < STATIC_BASE:
        return (tile_id // AUTOTILE_BASE) * AUTOTILE_BASE
    return tile_id


class TileMap:
    """Loaded substitution table. Geometry sections resolve every Uranium tile
    through `lookup()`; an unresolvable tile fails loud."""

    def __init__(
        self,
        tiles: dict[int, dict[str, Metatile]],
        tilesets: dict[int, TilesetChoice],
        buckets: dict[int, Bucket] | None = None,
        passages: dict[int, list[int]] | None = None,
        priorities: dict[int, list[int]] | None = None,
        warps: dict[int, WarpInfo] | None = None,
        atlas_max: dict[int, int] | None = None,
    ) -> None:
        self._tiles = tiles
        self._tilesets = tilesets
        self._buckets = buckets or {}
        self._passages = passages or {}
        self._priorities = priorities or {}
        # Accept a bare Metatile as shorthand for a fallback-only WarpInfo (legacy
        # single-canned-metatile callers, e.g. older test fixtures) — same
        # normalization load_tile_map applies when reading the old JSON shape.
        self._warps = {
            ts: (v if isinstance(v, WarpInfo) else WarpInfo({}, v))
            for ts, v in (warps or {}).items()
        }
        self._atlas_max = atlas_max or {}

    # --- resolution ---------------------------------------------------------

    def lookup(self, tileset_id: int, tile_id: int) -> Metatile:
        """Resolve one Uranium tile to a pokeemerald Metatile.

        Order: explicit `tiles[tileset_id][normalize(tile_id)]`, else the
        passability-bucket fallback. `tile_id == 0` is the empty marker and is the
        caller's concern (layout.collapse handles empty columns via `void()`), so it
        raises here. Fails loud (KeyError) with the ids when nothing resolves."""
        if tile_id == 0:
            raise ValueError(
                "lookup() called with empty tile_id 0; the layout collapse handles "
                "empty columns via void(tileset_id), not lookup()"
            )
        nid = normalize_tile_id(tile_id)
        explicit = self._tiles.get(tileset_id)
        if explicit:
            # Exact tile_id wins (real-art mode keys each autotile VARIANT
            # separately so its rendered edge/corner is faithful); fall back to the
            # autotile-base id (bucket / Approach-A mode folds all 48 variants to base).
            if str(tile_id) in explicit:
                return explicit[str(tile_id)]
            if str(nid) in explicit:
                return explicit[str(nid)]

        bucket = self._buckets.get(tileset_id)
        if bucket is None:
            raise KeyError(
                f"unmapped tile: tileset={tileset_id} tile_id={tile_id} "
                f"(normalized {nid}); no explicit entry and no bucket — add it to "
                f"{DEFAULT_TILE_MAP_PATH}"
            )
        if self.is_passable(tileset_id, tile_id):
            return Metatile(bucket.passable, PASSABLE_COLLISION, PASSABLE_ELEVATION)
        return Metatile(bucket.blocked, BLOCKED_COLLISION, BLOCKED_ELEVATION)

    def void(self, tileset_id: int) -> Metatile:
        """The border / empty-column metatile for a tileset (impassable)."""
        bucket = self._buckets.get(tileset_id)
        if bucket is None:
            raise KeyError(f"no bucket (hence no void metatile) for tileset {tileset_id}")
        return Metatile(bucket.void, BLOCKED_COLLISION, BLOCKED_ELEVATION)

    def warp(self, tileset_id: int) -> Metatile:
        """Legacy single-metatile warp lookup — returns the tileset's fallback warp
        metatile. Kept for callers that don't have a column key handy; prefer
        `warp_for_column`. Fails loud if the tileset has no `warps` entry, or if it
        has only per-column door copies and no fallback (that shape requires a
        column key — a bare `warp()` call would silently pick the wrong door art)."""
        info = self._warps.get(tileset_id)
        if info is None:
            raise KeyError(
                f"no warp metatile for tileset {tileset_id}; add a 'warps' entry to "
                f"{DEFAULT_TILE_MAP_PATH} or the warp_event will never fire (its "
                f"metatile would be MB_NORMAL)"
            )
        if info.fallback is None:
            raise KeyError(
                f"tileset {tileset_id} has only per-column warp metatiles (no "
                f"fallback); use warp_for_column(tileset_id, key) instead"
            )
        return info.fallback

    def warp_for_column(
        self, tileset_id: int, key: tuple[tuple[int, int], ...] | None
    ) -> Metatile:
        """The warp metatile for a specific column key (fix #1): an exact match on
        ``key`` keeps that cell's real art with MB_NON_ANIMATED_DOOR behavior;
        otherwise the tileset's transparent fallback door metatile is used (`key`
        None covers empty/out-of-atlas warp cells). Fails loud (KeyError) if the
        tileset has no `warps` entry, or if neither the column nor a fallback
        resolves — a silent MB_NORMAL warp tile is the failure mode this must never
        produce."""
        info = self._warps.get(tileset_id)
        if info is None:
            raise KeyError(
                f"no warp metatile(s) for tileset {tileset_id}; add a 'warps' entry "
                f"to {DEFAULT_TILE_MAP_PATH} or the warp_event will never fire (its "
                f"metatile would be MB_NORMAL)"
            )
        if key is not None:
            k = serialize_column_key(key)
            if k in info.tiles:
                return info.tiles[k]
        if info.fallback is not None:
            return info.fallback
        k_repr = serialize_column_key(key) if key is not None else "None"
        raise KeyError(
            f"no warp metatile for tileset {tileset_id} column {key!r} "
            f"(serialized {k_repr!r}) and no fallback configured"
        )

    def has_warp(self, tileset_id: int) -> bool:
        return tileset_id in self._warps

    def tileset_for(self, tileset_id: int) -> TilesetChoice:
        """The primary/secondary pokeemerald tileset for an Uranium tileset id (Q4)."""
        try:
            return self._tilesets[tileset_id]
        except KeyError:
            raise KeyError(
                f"no (primary, secondary) assigned for Uranium tileset {tileset_id}"
            ) from None

    # --- source-passability accessors (used by lookup + layout.collapse) ----

    def passage(self, tileset_id: int, tile_id: int) -> int:
        """Raw RMXP passage byte for a tile (the layout converter combines these
        across layers, masking out priority>0 over-the-player tiles)."""
        passages = self._passages.get(tileset_id)
        if passages is None:
            raise KeyError(
                f"no passages array for tileset {tileset_id}; generate "
                f"{DEFAULT_PASSAGES_PATH} (deserialize.rb tilesets)"
            )
        if not 0 <= tile_id < len(passages):
            raise KeyError(
                f"tile_id {tile_id} out of range for tileset {tileset_id} passages "
                f"(len {len(passages)})"
            )
        return passages[tile_id]

    def priority(self, tileset_id: int, tile_id: int) -> int:
        """RMXP priority for a tile (>0 = drawn over the player; does not block)."""
        priorities = self._priorities.get(tileset_id)
        if priorities is None or not 0 <= tile_id < len(priorities):
            return 0
        return priorities[tile_id]

    def is_passable(self, tileset_id: int, tile_id: int) -> bool:
        """True if the tile's source passage permits walking (low nibble == 0)."""
        return (self.passage(tileset_id, tile_id) & PASSAGE_BLOCK_MASK) == 0

    def has_bucket(self, tileset_id: int) -> bool:
        return tileset_id in self._buckets

    def has_columns(self, tileset_id: int) -> bool:
        """True iff this tileset has a non-empty explicit tiles table (real-art column mode)."""
        return bool(self._tiles.get(tileset_id))

    def column_in_atlas(self, tileset_id: int, key: tuple[tuple[int, int], ...]) -> bool:
        """False iff the column references a static tile id past the tileset's atlas
        bound (garbage tile). build_slice_tilesets drops such columns from the
        tileset, so the layout converter must void them here instead of failing loud.
        No recorded bound (legacy/bucket mode) => always in-atlas."""
        max_tid = self._atlas_max.get(tileset_id)
        if max_tid is None:
            return True
        return all(tid < STATIC_BASE or tid <= max_tid for _, tid in key)

    def lookup_column(self, tileset_id: int, key: tuple[tuple[int, int], ...]) -> Metatile:
        """Resolve a full column key to its pre-rendered metatile (real-art mode). Fails
        loud (KeyError) on a miss — every column the layout walks was enumerated by the
        S8a pre-pass, so a miss is a real bug. Empty columns are the caller's concern
        (handled via void())."""
        k = serialize_column_key(key)
        table = self._tiles.get(tileset_id, {})
        if k in table:
            return table[k]
        raise KeyError(
            f"unmapped column: tileset={tileset_id} key={key!r} (serialized {k!r})"
        )


def load_tile_map(
    path: Path = DEFAULT_TILE_MAP_PATH,
    passages_path: Path | None = DEFAULT_PASSAGES_PATH,
) -> TileMap:
    """Read + validate `reference/tileset_map.json` into a `TileMap`.

    Also loads the per-tileset `passages`/`priorities` arrays from the Phase-5-prep
    oracle (`passages_path`) for the bucket fallback. Pass `passages_path=None` to
    skip the oracle (explicit-`tiles`-only tables, e.g. unit tests).

    Generated-overlay precedence (mirrors the engine's `*.gen.json` hooks): if a
    sibling `<name>.gen.json` exists next to `path` (e.g. `tileset_map.gen.json`
    written by the graphics pre-pass), it is loaded INSTEAD — that's the real-art
    table (Uranium tilesets + per-tile metatiles). The committed `tileset_map.json`
    is the Hoenn-bucket fallback used when no overlay is present."""
    path = Path(path)
    overlay = path.with_name(f"{path.stem}.gen{path.suffix}")
    if overlay.is_file():
        logger.info("tile map: using generated overlay %s (real-art tilesets)", overlay)
        path = overlay
    raw = json.loads(path.read_text(encoding="utf-8"))
    _validate(raw)
    source_tilesets = {int(k): int(v) for k, v in raw.get("source_tilesets", {}).items()}

    tilesets = {
        int(k): TilesetChoice(v["primary"], v["secondary"])
        for k, v in raw["tilesets"].items()
    }
    tiles: dict[int, dict[str, Metatile]] = {}
    for ts_k, entries in raw["tiles"].items():
        tiles[int(ts_k)] = {
            tid: Metatile(e["metatile"], e.get("collision", 0), e.get("elevation", 3))
            for tid, e in entries.items()
        }
    buckets = {
        int(k): Bucket(b["passable"], b["blocked"], b["void"])
        for k, b in raw.get("buckets", {}).items()
    }
    warps = {int(k): _parse_warp_entry(w) for k, w in raw.get("warps", {}).items()}
    atlas_max = {int(k): int(v) for k, v in raw.get("atlas_max", {}).items()}

    passages: dict[int, list[int]] = {}
    priorities: dict[int, list[int]] = {}
    if passages_path is not None and buckets:
        passages, priorities = _load_oracle(Path(passages_path), tilesets.keys(), source_tilesets)

    return TileMap(tiles, tilesets, buckets, passages, priorities, warps, atlas_max)


def _parse_warp_entry(w: dict) -> WarpInfo:
    """Parse one `warps[ts]` entry into a `WarpInfo`, handling both shapes.

    New shape (per-column, fix #1): ``{"tiles": {colkey: metatile_idx, ...},
    "fallback": idx_or_None, "collision": c, "elevation": e}``. Legacy shape
    (single canned metatile, `reference/tileset_map.json` + old overlays):
    ``{"metatile": N, "collision": c, "elevation": e}`` — treated as a
    fallback-only WarpInfo so `warp_for_column` returns it for ANY column,
    matching the old behavior exactly."""
    collision = w.get("collision", 0)
    elevation = w.get("elevation", 0)
    if "tiles" in w:
        tiles = {
            colkey: Metatile(idx, collision, elevation) for colkey, idx in w["tiles"].items()
        }
        fallback_idx = w.get("fallback")
        fallback = (
            Metatile(fallback_idx, collision, elevation) if fallback_idx is not None else None
        )
        return WarpInfo(tiles, fallback)
    return WarpInfo({}, Metatile(w["metatile"], collision, elevation))


def _load_oracle(
    path: Path, tileset_ids, source_tilesets: dict[int, int] | None = None
) -> tuple[dict[int, list[int]], dict[int, list[int]]]:
    """Read `passages`/`priorities` for the needed tilesets from tilesets.json.

    `source_tilesets` maps a synthetic per-map tileset id to its real RMXP id; when a
    requested id is synthetic, the oracle is read for the REAL id but stored under the
    synthetic key. Empty/None => identity (legacy)."""
    if not path.exists():
        raise FileNotFoundError(
            f"passages oracle {path} missing; run "
            f"`deserialize.rb tilesets <data_dir> output/uranium-build`"
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    passages: dict[int, list[int]] = {}
    priorities: dict[int, list[int]] = {}
    src = source_tilesets or {}
    for ts in tileset_ids:
        real = src.get(ts, ts)
        entry = raw.get(str(real))
        if entry is None:
            raise KeyError(f"tileset {real} absent from {path}")
        passages[ts] = entry["passages"]
        priorities[ts] = entry["priorities"]
    return passages, priorities


def _validate(raw: dict) -> None:
    """Fail loud if the table is missing top-level keys or has malformed entries."""
    for key in _SCHEMA:
        if key not in raw:
            raise ValueError(f"tileset_map.json missing required key {key!r}")

    tileset_ids = set()
    for ts_k, choice in raw["tilesets"].items():
        tileset_ids.add(ts_k)
        if not isinstance(choice, dict) or not choice.get("primary") or not choice.get("secondary"):
            raise ValueError(f"tileset {ts_k}: needs non-empty 'primary' and 'secondary'")

    for ts_k, entries in raw["tiles"].items():
        if ts_k not in tileset_ids:
            raise ValueError(f"tiles references tileset {ts_k} absent from 'tilesets'")
        for tid, e in entries.items():
            _validate_metatile_entry(f"tiles[{ts_k}][{tid}]", e)

    for ts_k, b in raw.get("buckets", {}).items():
        if ts_k not in tileset_ids:
            raise ValueError(f"buckets references tileset {ts_k} absent from 'tilesets'")
        for role in ("passable", "blocked", "void"):
            if role not in b:
                raise ValueError(f"bucket[{ts_k}] missing role {role!r}")
            _check_metatile_id(f"bucket[{ts_k}].{role}", b[role])

    for ts_k, w in raw.get("warps", {}).items():
        if ts_k not in tileset_ids:
            raise ValueError(f"warps references tileset {ts_k} absent from 'tilesets'")
        _validate_warp_entry(f"warps[{ts_k}]", w)


def _validate_metatile_entry(where: str, e: dict) -> None:
    if "metatile" not in e:
        raise ValueError(f"{where}: missing 'metatile'")
    _check_metatile_id(where, e["metatile"])
    if "collision" in e and e["collision"] not in _VALID_COLLISION:
        raise ValueError(f"{where}: collision {e['collision']} not in {_VALID_COLLISION}")
    if "elevation" in e and not 0 <= e["elevation"] <= _MAX_ELEVATION:
        raise ValueError(f"{where}: elevation {e['elevation']} out of 0..{_MAX_ELEVATION}")


def _validate_warp_entry(where: str, w: dict) -> None:
    """Validate one `warps[ts]` entry — new per-column shape (has 'tiles') or the
    legacy single-metatile shape."""
    if "tiles" in w:
        if not isinstance(w["tiles"], dict):
            raise ValueError(f"{where}.tiles: must be an object")
        for colkey, idx in w["tiles"].items():
            _check_metatile_id(f"{where}.tiles[{colkey}]", idx)
        fallback = w.get("fallback")
        if fallback is not None:
            _check_metatile_id(f"{where}.fallback", fallback)
        if "collision" in w and w["collision"] not in _VALID_COLLISION:
            raise ValueError(f"{where}: collision {w['collision']} not in {_VALID_COLLISION}")
        if "elevation" in w and not 0 <= w["elevation"] <= _MAX_ELEVATION:
            raise ValueError(f"{where}: elevation {w['elevation']} out of 0..{_MAX_ELEVATION}")
    else:
        _validate_metatile_entry(where, w)


def _check_metatile_id(where: str, mt) -> None:
    if not isinstance(mt, int) or mt < 0 or mt > _MAX_METATILE:
        raise ValueError(
            f"{where}: metatile id {mt!r} must be an int in 0..0x{_MAX_METATILE:X} "
            f"(larger truncates in to_block)"
        )
