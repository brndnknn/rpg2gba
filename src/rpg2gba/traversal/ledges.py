"""Ledge (one-way jump) derivation — reuses the Phase 5 terrain-tag rule.

Ledges are one-way: a cell tagged terrain tag 1 (`terrain_tags.LEDGE_TAG`)
blocks entry from three sides and permits a *jump* from the fourth, landing
two tiles past the ledge (confirmed against the engine:
`engine/src/event_object_movement.c:10221` `GetLedgeJumpDirection` checks the
tile the player is moving *onto* for a matching `MB_JUMP_<dir>` behavior, and
`event_object_movement.c:5981-5984` fires `GetJump2MovementAction` — a 2-tile
jump — when it matches).

We reuse `terrain_tags.TerrainTagTable.effective_tag` (the topmost-nonzero-tag
rule, including the opaque-cover stop) verbatim — that is the one place the
"which tile's tag wins in a column" rule lives (CLAUDE.md §4.3). We do NOT
reuse `TerrainTagTable.column_behavior`'s ledge branch, because that method
resolves to a numeric `MB_*` enum value read from the vendored fork's C
header (`_behavior_value`) — machinery this library has no need for (no ROM,
no build, per the task's premise). `effective_tag` itself touches no fork
data (it only reads `tags_for_tileset`/`key`/`is_opaque`), so constructing a
placeholder `TerrainTagTable` purely to call it is safe reuse, not a
workaround.

The clear-bit -> direction mapping below mirrors
`terrain_tags._LEDGE_CLEAR_BIT_TO_MB` exactly (same four constants), just
target a plain `Direction` instead of an `MB_JUMP_*` name — that table is
fork-enum-gated and not reusable standalone, so this is a intentional,
documented restatement of a 4-entry physical constant, not a second
implementation of the derivation algorithm.

Also applies the hand-filled `reference/terrain_tag_map.json` `ledge_directions`
override table (same override-wins-unconditionally rule as
`terrain_tags.column_behavior`), and carries the same hardware-unverified
caveat: the sole-clear-bit derivation has not been confirmed against a real
ROM walk for every tileset (flagged until CH07 per repo convention).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from rpg2gba.tileset_converter.terrain_tags import LEDGE_TAG, TerrainTagTable
from rpg2gba.tileset_converter.tile_map import PASSAGE_BLOCK_MASK

from .direction import Direction

logger = logging.getLogger(__name__)

DEFAULT_TERRAIN_TAG_MAP = Path("reference/terrain_tag_map.json")

# Sole CLEAR bit (within the low-nibble passage block mask) -> jump direction.
# Mirrors terrain_tags._LEDGE_CLEAR_BIT_TO_MB's keys; see module docstring for
# why we don't import that table directly (it maps to fork-resolved ints).
_CLEAR_BIT_TO_DIRECTION: dict[int, Direction] = {
    0x08: Direction.SOUTH,
    0x01: Direction.NORTH,
    0x02: Direction.EAST,
    0x04: Direction.WEST,
}

_DIRECTION_BY_NAME: dict[str, Direction] = {d.value: d for d in Direction}

# Placeholder instance used only for its (fork-independent) effective_tag().
_EFFECTIVE_TAG_ONLY = TerrainTagTable({}, {}, 0, 0, {})


def load_ledge_direction_overrides(
    path: Path = DEFAULT_TERRAIN_TAG_MAP,
) -> dict[tuple[int, int], Direction]:
    """Load the hand-filled `ledge_directions` override table: {(tileset_id,
    tile_id): Direction}. Ships empty; wins over derivation unconditionally
    when present (matches `terrain_tags.column_behavior`'s rule)."""
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    overrides: dict[tuple[int, int], Direction] = {}
    for ts_str, per_tile in raw.get("ledge_directions", {}).items():
        for tile_str, direction_name in per_tile.items():
            direction = _DIRECTION_BY_NAME.get(direction_name)
            if direction is None:
                raise ValueError(
                    f"ledge_directions[{ts_str}][{tile_str}]: unknown direction "
                    f"{direction_name!r} (expected one of {sorted(_DIRECTION_BY_NAME)})"
                )
            overrides[(int(ts_str), int(tile_str))] = direction
    return overrides


def _topmost_nonempty(key: tuple[tuple[int, int], ...]) -> int:
    return key[-1][1] if key else 0


def derive_ledge_direction(
    tileset_id: int,
    key: tuple[tuple[int, int], ...],
    *,
    terrain_tags: list[int],
    passages: list[int],
    overrides: dict[tuple[int, int], Direction] | None = None,
) -> Direction | None:
    """The jump direction for one cell's column key, or None if it isn't a
    ledge (effective tag != LEDGE_TAG). Mirrors
    `terrain_tags.column_behavior`'s ledge branch: an override wins
    unconditionally; otherwise the passage byte's sole clear bit names the
    direction; all-four-blocked (0x0F) is a pure wall (None, silent, matches
    the Phase 5 rule); two-or-more clear bits is ambiguous and warns once,
    falling back to None (not a jumpable ledge, treated as an ordinary wall
    for this graph, same as the Phase 5 fallback to MB_NORMAL)."""
    tag = _EFFECTIVE_TAG_ONLY.effective_tag(terrain_tags, key)
    if tag != LEDGE_TAG:
        return None
    tile_id = _topmost_nonempty(key)

    override = (overrides or {}).get((tileset_id, tile_id))
    if override is not None:
        return override

    if not 0 <= tile_id < len(passages):
        logger.warning(
            "ledge at tileset %d tile %d has no passage data to derive a "
            "direction from -> treated as a wall",
            tileset_id, tile_id,
        )
        return None

    passage_low = passages[tile_id] & PASSAGE_BLOCK_MASK
    clear_bits = ~passage_low & PASSAGE_BLOCK_MASK
    if clear_bits == 0:
        return None  # 0x0F: fully blocked, a pure wall, not a ledge (silent by design)
    if clear_bits.bit_count() == 1:
        return _CLEAR_BIT_TO_DIRECTION[clear_bits]

    logger.warning(
        "ledge at tileset %d tile %d has an ambiguous passage byte (low "
        "nibble 0x%X, >=2 clear bits) -> treated as a wall",
        tileset_id, tile_id, passage_low,
    )
    return None
