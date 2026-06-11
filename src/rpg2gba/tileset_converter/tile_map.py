"""Phase 5 §5.1 — Tile mapping table (the source of truth).

ASSIGNMENT
==========
Objective
    Establish and validate the single source of truth that maps an Uranium
    `(tileset_id, tile_id)` onto a pokeemerald `metatile_id` (+ collision /
    elevation), plus the `tileset_id -> (primary, secondary)` tileset choice.
    This is `reference/tileset_map.json`, named in CLAUDE.md §4.3.

    You build the *loader, schema validator, and lookup* — NOT the table data
    (that is hand-authored grunt work, seeded incrementally as maps are
    encountered). Approach A (ROADMAP §Phase 5): every Uranium tile resolves to
    an *existing* pokeemerald metatile, so we author no new tileset graphics.

The two id spaces (see PHASE5_PLAN.md "two tile models")
    RMXP tile_id:  0 = empty;  48..383 = autotiles (48 ids each, base = 48*n);
                   >=384 = static tiles, (row,col) = divmod(tile_id-384, 8).
    GBA metatile_id: 0x000..0x1FF primary tileset, 0x200+ secondary.

Inputs
    reference/tileset_map.json  (hand-authored; see _SCHEMA below)
    $RPG2GBA_POKEEMERALD tileset metatile inventory (read-only, to know which
        metatile_ids are legal targets — optional validation hook).
Output
    An in-memory `TileMap` the layout/wiring sections call.

Constraints
    - FAIL LOUD (CLAUDE.md §4.5): `lookup()` on an unmapped (tileset_id, tile_id)
      raises with the exact ids — a hole must never silently become metatile 0.
    - Idempotent: load -> serialize -> load is stable.

Acceptance
    [ ] round-trip load/serialize/load stable
    [ ] unmapped lookup raises with the offending ids in the message
    [ ] autotile base ids (48*n) and static ids (>=384) both resolvable
    [ ] golden test on a tiny hand-built table
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Default location of the hand-authored substitution table (CLAUDE.md §4.3).
DEFAULT_TILE_MAP_PATH = Path("reference/tileset_map.json")

# pokeemerald block-packing constants (PHASE5_PLAN.md "GBA model"). Shared with
# layout.py — keep one definition. A block u16 = metatile | collision<<10 | elev<<12.
METATILE_ID_MASK = 0x03FF
COLLISION_SHIFT = 10
ELEVATION_SHIFT = 12
NUM_METATILES_IN_PRIMARY = 0x200  # secondary tileset metatiles start here

# Shape of reference/tileset_map.json (informational; enforce in `_validate`):
#   {
#     "tilesets": { "<uranium_tileset_id>": {"primary": "gTileset_General",
#                                             "secondary": "gTileset_<Area>"} },
#     "tiles":    { "<uranium_tileset_id>": { "<tile_id>": {"metatile": <int>,
#                                             "collision": 0, "elevation": 3} } },
#     # Q1 hybrid: opt-in composite overrides keyed by the "z0,z1,z2" stack;
#     # `lookup` consults these FIRST, then falls back to per-tile "tiles".
#     "stacks":   { "<uranium_tileset_id>": { "<z0>,<z1>,<z2>": {"metatile": <int>} } }
#   }
# Q3: collision/elevation default to the target metatile's baseline; an entry may
# override them per cell. Q4 (first pass): every tileset maps to ONE universal pair.
_SCHEMA = ("tilesets", "tiles")  # "stacks" optional


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


class TileMap:
    """Loaded substitution table. The geometry sections resolve every Uranium tile
    through `lookup()`; unmapped tiles fail loud."""

    def __init__(
        self,
        tiles: dict[int, dict[int, Metatile]],
        tilesets: dict[int, TilesetChoice],
    ) -> None:
        self._tiles = tiles
        self._tilesets = tilesets

    def lookup(self, tileset_id: int, tile_id: int) -> Metatile:
        """Resolve one Uranium tile to a pokeemerald Metatile.

        Raises KeyError (fail loud) with both ids if the pair is unmapped. Empty
        RMXP tile_id 0 is the caller's concern (it usually means "no tile on this
        layer"), not an error here — decide that policy in layout.py (Q1)."""
        raise NotImplementedError("5.1: resolve (tileset_id, tile_id); fail loud on miss")

    def tileset_for(self, tileset_id: int) -> TilesetChoice:
        """The primary/secondary pokeemerald tileset for an Uranium tileset id (Q4)."""
        raise NotImplementedError("5.1: return the TilesetChoice for this Uranium tileset id")


def load_tile_map(path: Path = DEFAULT_TILE_MAP_PATH) -> TileMap:
    """Read + validate `reference/tileset_map.json` into a `TileMap`.

    Hints:
      - open with encoding="utf-8" (CLAUDE.md §5).
      - JSON object keys are strings; coerce tileset/tile ids to int.
      - call `_validate(raw)` before building; fail loud on a bad shape.
    """
    raise NotImplementedError("5.1: parse + validate tileset_map.json")


def _validate(raw: dict) -> None:
    """Fail loud if the table is missing top-level keys or has malformed entries."""
    raise NotImplementedError("5.1: enforce _SCHEMA, reject negative/None metatile ids, etc.")
