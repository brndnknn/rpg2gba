"""Phase 5 graphics pre-pass — Essentials terrain tag -> pokeemerald MB_* behavior.

Uranium's tileset data carries a per-tile "terrain tag" (0-22, RMXP/Essentials
`PBTerrain`) that encodes wild-encounter grass, water, ice, ledges, etc. This
module maps that tag to a metatile behavior byte at tileset-emit time, using
the effective-terrain-tag rule: the TOPMOST non-empty-tag tile in a column's
z-stack wins (RMXP/Essentials semantics), with autotile variants (ids
48..383) falling back to their base id's tag when the variant's own tag is 0.

Ledge (tag 1) is special: Essentials decides jump direction from player facing
at runtime, but never stores a direction of its own — the tile's RMXP passage
byte low nibble (`tile_map.PASSAGE_BLOCK_MASK`) is the whole story. RMXP
checks the DESTINATION tile with the opposite direction (`10 - d`), so the
sole CLEAR bit in the low nibble names the jump direction: 0x08 clear ->
MB_JUMP_SOUTH, 0x01 clear -> MB_JUMP_NORTH, 0x02 clear -> MB_JUMP_EAST,
0x04 clear -> MB_JUMP_WEST. 0x0F (all four blocked) is a pure wall, not a
ledge -> MB_NORMAL, silently. Two or more clear bits is genuinely ambiguous
-> warn once per distinct (tileset, tile_id) and fall back to MB_NORMAL. The
hand-filled `ledge_directions` override table ships empty and, when it does
have an entry for a (tileset_id, tile_id), wins over derivation
unconditionally — it stays as an escape hatch; do not grow it.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

from rpg2gba.tileset_converter.tile_map import PASSAGE_BLOCK_MASK

logger = logging.getLogger(__name__)

DEFAULT_TERRAIN_TAG_MAP = Path("reference/terrain_tag_map.json")

AUTOTILE_BASE_STEP = 48  # RMXP: autotile variants are grouped in blocks of 48
STATIC_BASE = 384  # ids >= 384 are static tiles (no autotile base fallback)

LEDGE_TAG = 1

#: RMXP tileset-editor "Counter" checkbox -- high bit of the passage byte,
#: independent of the low-nibble collision bits `tile_map.PASSAGE_BLOCK_MASK`
#: reads. Marks a tile (a shop/service desk) whose blocked cell still lets the
#: player interact with whatever object stands one tile further past it --
#: pokeemerald's native analog is MB_COUNTER (see
#: engine/src/field_control_avatar.c's counter reach-over check). Only applies
#: to tag-0 columns: a counter desk carries no wild-encounter/ledge/water
#: terrain of its own, so it never competes with an explicit terrain tag.
COUNTER_PASSAGE_BIT = 0x80

_LEDGE_DIR_TO_MB = {
    "north": "MB_JUMP_NORTH",
    "south": "MB_JUMP_SOUTH",
    "east": "MB_JUMP_EAST",
    "west": "MB_JUMP_WEST",
}

#: Sole CLEAR bit (within the low-nibble block mask) -> the MB_JUMP_* name for
#: that direction. RMXP checks the DESTINATION tile with the opposite
#: direction (`10 - d`), so the one open (unblocked) side is the direction the
#: player may jump INTO the tile from — see the module docstring.
_LEDGE_CLEAR_BIT_TO_MB = {
    0x08: "MB_JUMP_SOUTH",
    0x01: "MB_JUMP_NORTH",
    0x02: "MB_JUMP_EAST",
    0x04: "MB_JUMP_WEST",
}


def _behavior_value(fork: Path, name: str) -> int:
    """Resolve a ``MB_*`` metatile-behavior to its numeric enum value from the fork.

    Duplicated (not imported) from build_slice_tilesets._behavior_value per the
    task boundary (that module is not to be touched beyond its own wiring); kept
    logic-identical. Parses the first ``enum { ... }`` in
    ``include/constants/metatile_behaviors.h`` (CLAUDE.md §4.7 forward gate)."""
    path = fork / "include" / "constants" / "metatile_behaviors.h"
    val = 0
    in_enum = False
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.split("//")[0].strip()
        if not in_enum:
            if s.startswith("enum") and "{" in s:
                in_enum = True
            continue
        if "}" in s:
            break
        s = s.rstrip(",").strip()
        if not s:
            continue
        if "=" in s:
            ident, _, num = s.partition("=")
            ident, val = ident.strip(), int(num.strip(), 0)
        else:
            ident = s
        if ident == name:
            return val
        val += 1
    raise KeyError(f"{name} not found in {path}")


class TerrainTagTable:
    """Validated tag->behavior table + ledge direction overrides for one build.

    Load once per pipeline run via `load_terrain_tag_map`, then call
    `column_behavior` per emitted metatile column."""

    def __init__(
        self,
        tag_to_behavior_value: dict[int, int],
        ledge_directions: dict[tuple[int, int], int],
        normal_value: int,
        counter_value: int,
        clear_bit_to_jump_value: dict[int, int],
    ) -> None:
        self._tag_to_value = tag_to_behavior_value
        self._ledge_directions = ledge_directions
        self._normal_value = normal_value
        self._counter_value = counter_value
        self._clear_bit_to_jump_value = clear_bit_to_jump_value
        self._warned_ledges: set[tuple[int, int]] = set()

    def _warn_ledge_once(
        self, tileset_id: int, tile_id: int, msg: str, *extra_args: object
    ) -> None:
        """Log `msg` once per distinct (tileset_id, tile_id) ledge fallback."""
        warn_key = (tileset_id, tile_id)
        if warn_key in self._warned_ledges:
            return
        self._warned_ledges.add(warn_key)
        logger.warning(msg, tileset_id, tile_id, *extra_args)

    def effective_tag(
        self,
        tags_for_tileset: list[int],
        key: tuple[tuple[int, int], ...],
        is_opaque: Callable[[int], bool] | None = None,
    ) -> int:
        """The cell's effective terrain tag: topmost (highest z) tile in `key` whose
        tag is nonzero wins; autotile variants fall back to their base id's tag when
        the variant's own tag is 0; 0 if every layer's tag is 0.

        `is_opaque` (tile_id -> fully-opaque?) stops the fall-through at a covering
        tile: RMXP maps routinely flood-fill a water layer under solid land tiles
        (tag 0), and without the stop the water tag beneath leaks up — grass and
        hedges got reflective MB_POND_WATER (boot gate 2026-07-06). A partial/
        decorative overlay (flowers on grass) is not opaque and still falls
        through to the base terrain's tag."""
        # key is bottom-first (z ascending); iterate top-down for "topmost wins".
        for _z, tile_id in reversed(key):
            tag = _tag_for_tile(tags_for_tileset, tile_id)
            if tag != 0:
                return tag
            if is_opaque is not None and is_opaque(tile_id):
                return 0  # solid tag-0 tile fully covers whatever lies beneath
        return 0

    def column_behavior(
        self,
        tileset_id: int,
        key: tuple[tuple[int, int], ...],
        tags_for_tileset: list[int],
        is_opaque: Callable[[int], bool] | None = None,
        passages_for_tileset: list[int] | None = None,
    ) -> int:
        """The MB_* numeric value for a column: apply the topmost-nonzero-tag rule
        (with the opaque-cover stop, see `effective_tag`), then map through the
        terrain table. Ledge (tag 1) resolution order: (1) a `ledge_directions`
        hand override for (tileset_id, tile_id) always wins; (2) otherwise the
        tile's passage byte low nibble is derived per the module docstring —
        a sole clear bit gives the MB_JUMP_* direction, all four bits blocked
        (0x0F) is a pure wall and silently falls back to MB_NORMAL, and two or
        more clear bits is ambiguous and warns once before falling back; (3) no
        `passages_for_tileset` (or the tile id is out of range) also warns once
        and falls back — derivation is impossible without passage data. A tag-0
        column whose topmost tile carries the RMXP Counter passage bit
        (`COUNTER_PASSAGE_BIT`, requires `passages_for_tileset`) maps to
        MB_COUNTER instead of MB_NORMAL."""
        tag = self.effective_tag(tags_for_tileset, key, is_opaque=is_opaque)
        if tag == 0 and passages_for_tileset is not None:
            tile_id = _topmost_nonempty(key)
            if (0 <= tile_id < len(passages_for_tileset)
                    and passages_for_tileset[tile_id] & COUNTER_PASSAGE_BIT):
                return self._counter_value
        if tag == LEDGE_TAG:
            # Visual tile id for the ledge lookup: the topmost non-empty tile,
            # matching how `effective_tag` found the tag in the first place.
            tile_id = _topmost_nonempty(key)
            override = self._ledge_directions.get((tileset_id, tile_id))
            if override is not None:
                return override

            if passages_for_tileset is None or not (
                0 <= tile_id < len(passages_for_tileset)
            ):
                self._warn_ledge_once(
                    tileset_id, tile_id,
                    "terrain tag 1 (ledge) at tileset %d tile %d has no "
                    "ledge_directions entry and no passage data to derive "
                    "from -> MB_NORMAL",
                )
                return self._normal_value

            passage_low = passages_for_tileset[tile_id] & PASSAGE_BLOCK_MASK
            clear_bits = ~passage_low & PASSAGE_BLOCK_MASK
            if clear_bits == 0:
                # 0x0F: fully blocked on all four sides -> a pure wall, not a
                # ledge. Silent by design (section 33) -- this is the intended,
                # expected shape of most ordinary blocking tiles.
                return self._normal_value
            if clear_bits.bit_count() == 1:
                return self._clear_bit_to_jump_value[clear_bits]

            self._warn_ledge_once(
                tileset_id, tile_id,
                "terrain tag 1 (ledge) at tileset %d tile %d has an ambiguous "
                "passage byte (0x%02X, low nibble 0x%X, >=2 clear bits) -> "
                "MB_NORMAL",
                passages_for_tileset[tile_id], passage_low,
            )
            return self._normal_value
        try:
            return self._tag_to_value[tag]
        except KeyError:
            raise ValueError(
                f"terrain tag {tag} (tileset {tileset_id}) has no entry in "
                f"the terrain tag map — new tag, needs a mapping decision"
            ) from None


def _topmost_nonempty(key: tuple[tuple[int, int], ...]) -> int:
    if not key:
        return 0
    return key[-1][1]


def _tag_for_tile(tags_for_tileset: list[int], tile_id: int) -> int:
    """The tag for one tile id, with the autotile-base fallback (variant ids
    48..383 whose own tag is 0 inherit the tag at their autotile base id,
    `(tile_id // 48) * 48`). Static ids (>= 384) never fall back."""
    tag = tags_for_tileset[tile_id] if 0 <= tile_id < len(tags_for_tileset) else 0
    if tag != 0:
        return tag
    if tile_id < STATIC_BASE:
        base = (tile_id // AUTOTILE_BASE_STEP) * AUTOTILE_BASE_STEP
        if base != tile_id and 0 <= base < len(tags_for_tileset):
            return tags_for_tileset[base]
    return 0


def load_terrain_tag_map(
    fork: Path, path: Path = DEFAULT_TERRAIN_TAG_MAP
) -> TerrainTagTable:
    """Load + validate `reference/terrain_tag_map.json` against the fork's real
    MB_* enum (fail loud on a name the fork doesn't define — CLAUDE.md §4.7)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    tag_to_value: dict[int, int] = {}
    for tag_str, entry in raw["tags"].items():
        name = entry["behavior"]
        tag_to_value[int(tag_str)] = _behavior_value(fork, name)

    ledge_directions: dict[tuple[int, int], int] = {}
    for ts_str, per_tile in raw.get("ledge_directions", {}).items():
        for tile_str, direction in per_tile.items():
            if direction not in _LEDGE_DIR_TO_MB:
                raise ValueError(
                    f"ledge_directions[{ts_str}][{tile_str}]: unknown direction "
                    f"{direction!r} (expected one of {sorted(_LEDGE_DIR_TO_MB)})"
                )
            mb_name = _LEDGE_DIR_TO_MB[direction]
            ledge_directions[(int(ts_str), int(tile_str))] = _behavior_value(fork, mb_name)

    normal_value = _behavior_value(fork, "MB_NORMAL")
    counter_value = _behavior_value(fork, "MB_COUNTER")
    clear_bit_to_jump_value = {
        bit: _behavior_value(fork, name)
        for bit, name in _LEDGE_CLEAR_BIT_TO_MB.items()
    }
    return TerrainTagTable(
        tag_to_value, ledge_directions, normal_value, counter_value,
        clear_bit_to_jump_value,
    )


def load_terrain_tags_json(tilesets_json: Path, ts: int) -> list[int]:
    """Load the `terrain_tags` array for tileset `ts` from the Phase-3 tilesets
    oracle. Mirrors `build_slice_tilesets._load_priorities`."""
    raw = json.loads(Path(tilesets_json).read_text(encoding="utf-8"))
    entry = raw.get(str(ts))
    if entry is None:
        raise KeyError(f"tileset {ts} absent from {tilesets_json}")
    return entry["terrain_tags"]
