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
        tiles: dict[int, dict[int, Metatile]],
        tilesets: dict[int, TilesetChoice],
        buckets: dict[int, Bucket] | None = None,
        passages: dict[int, list[int]] | None = None,
        priorities: dict[int, list[int]] | None = None,
        warps: dict[int, Metatile] | None = None,
    ) -> None:
        self._tiles = tiles
        self._tilesets = tilesets
        self._buckets = buckets or {}
        self._passages = passages or {}
        self._priorities = priorities or {}
        self._warps = warps or {}

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
        if explicit and nid in explicit:
            return explicit[nid]

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
        """The warp metatile stamped at a warp/door/stairs cell for this tileset.

        A pokeemerald warp_event is inert unless the metatile under it carries a
        warp metatile-behavior (see field_control_avatar.c). The generic passable
        bucket has MB_NORMAL, so the layout converter overlays this metatile (a
        step-on MB_NON_ANIMATED_DOOR, collision 0) at every warp coord. Fails loud
        if the tileset has no `warps` entry — a warp on an unconfigured tileset
        would silently never fire."""
        warp = self._warps.get(tileset_id)
        if warp is None:
            raise KeyError(
                f"no warp metatile for tileset {tileset_id}; add a 'warps' entry to "
                f"{DEFAULT_TILE_MAP_PATH} or the warp_event will never fire (its "
                f"metatile would be MB_NORMAL)"
            )
        return warp

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


def load_tile_map(
    path: Path = DEFAULT_TILE_MAP_PATH,
    passages_path: Path | None = DEFAULT_PASSAGES_PATH,
) -> TileMap:
    """Read + validate `reference/tileset_map.json` into a `TileMap`.

    Also loads the per-tileset `passages`/`priorities` arrays from the Phase-5-prep
    oracle (`passages_path`) for the bucket fallback. Pass `passages_path=None` to
    skip the oracle (explicit-`tiles`-only tables, e.g. unit tests)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    _validate(raw)

    tilesets = {
        int(k): TilesetChoice(v["primary"], v["secondary"])
        for k, v in raw["tilesets"].items()
    }
    tiles: dict[int, dict[int, Metatile]] = {}
    for ts_k, entries in raw["tiles"].items():
        tiles[int(ts_k)] = {
            int(tid): Metatile(
                e["metatile"], e.get("collision", 0), e.get("elevation", 3)
            )
            for tid, e in entries.items()
        }
    buckets = {
        int(k): Bucket(b["passable"], b["blocked"], b["void"])
        for k, b in raw.get("buckets", {}).items()
    }
    warps = {
        int(k): Metatile(w["metatile"], w.get("collision", 0), w.get("elevation", 0))
        for k, w in raw.get("warps", {}).items()
    }

    passages: dict[int, list[int]] = {}
    priorities: dict[int, list[int]] = {}
    if passages_path is not None and buckets:
        passages, priorities = _load_oracle(Path(passages_path), tilesets.keys())

    return TileMap(tiles, tilesets, buckets, passages, priorities, warps)


def _load_oracle(path: Path, tileset_ids) -> tuple[dict[int, list[int]], dict[int, list[int]]]:
    """Read `passages`/`priorities` for the needed tilesets from tilesets.json."""
    if not path.exists():
        raise FileNotFoundError(
            f"passages oracle {path} missing; run "
            f"`deserialize.rb tilesets <data_dir> output/uranium-build`"
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    passages: dict[int, list[int]] = {}
    priorities: dict[int, list[int]] = {}
    for ts in tileset_ids:
        entry = raw.get(str(ts))
        if entry is None:
            raise KeyError(f"tileset {ts} absent from {path}")
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
        _validate_metatile_entry(f"warps[{ts_k}]", w)


def _validate_metatile_entry(where: str, e: dict) -> None:
    if "metatile" not in e:
        raise ValueError(f"{where}: missing 'metatile'")
    _check_metatile_id(where, e["metatile"])
    if "collision" in e and e["collision"] not in _VALID_COLLISION:
        raise ValueError(f"{where}: collision {e['collision']} not in {_VALID_COLLISION}")
    if "elevation" in e and not 0 <= e["elevation"] <= _MAX_ELEVATION:
        raise ValueError(f"{where}: elevation {e['elevation']} out of 0..{_MAX_ELEVATION}")


def _check_metatile_id(where: str, mt) -> None:
    if not isinstance(mt, int) or mt < 0 or mt > _MAX_METATILE:
        raise ValueError(
            f"{where}: metatile id {mt!r} must be an int in 0..0x{_MAX_METATILE:X} "
            f"(larger truncates in to_block)"
        )
