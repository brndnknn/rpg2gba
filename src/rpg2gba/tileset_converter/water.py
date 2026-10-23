"""Which emitted metatiles are surfable water (fishing/Surf from the shore).

`layout.convert_layout` stamps a passage-blocked cell whose metatile is surfable
with collision 0 / `tile_map.WATER_ELEVATION` instead of the generic blocked
encoding, because the engine only allows a rod or Surf when the faced cell is an
elevation mismatch, not a collision wall.

Both halves are read from the fork, never restated (CLAUDE.md §4.7): the surfable
behaviour set from `sTileBitAttributes` in `src/metatile_behavior.c`, and each
metatile's behaviour from the `metatile_attributes.bin` the graphics pass wrote.
"""

import re
import struct
from pathlib import Path

from rpg2gba.tileset_converter.terrain_tags import _behavior_value
from rpg2gba.tileset_converter.tile_map import NUM_METATILES_IN_PRIMARY

# engine/include/global.fieldmap.h METATILE_ATTR_BEHAVIOR_MASK (Emerald layout).
_BEHAVIOR_MASK = 0x00FF
_SURFABLE_ROW = re.compile(r"\[(MB_\w+)\]\s*=\s*([^,]*TILE_FLAG_SURFABLE[^,]*),")


def surfable_behaviors(fork: Path) -> frozenset[int]:
    """Numeric values of every MB_* the engine flags TILE_FLAG_SURFABLE. Fails loud
    if the table can't be found, so a fork refactor can't silently empty it."""
    path = fork / "src" / "metatile_behavior.c"
    names = _SURFABLE_ROW.findall(path.read_text(encoding="utf-8"))
    if not names:
        raise ValueError(f"no TILE_FLAG_SURFABLE rows found in {path}")
    return frozenset(_behavior_value(fork, name) for name, _ in names)


def _attributes(path: Path) -> tuple[int, ...]:
    data = path.read_bytes()
    return struct.unpack(f"<{len(data) // 2}H", data)


def surfable_metatile_ids(fork: Path, tileset_key: int, behaviors: frozenset[int]) -> frozenset[int]:
    """Metatile ids (primary 0.., secondary from NUM_METATILES_IN_PRIMARY) of
    tileset `uranium<tileset_key>` whose emitted behaviour is in `behaviors`."""
    base = fork / "data" / "tilesets"
    primary = _attributes(base / "primary" / f"uranium{tileset_key}" / "metatile_attributes.bin")
    secondary = _attributes(base / "secondary" / f"uranium{tileset_key}" / "metatile_attributes.bin")
    ids = {i for i, a in enumerate(primary) if a & _BEHAVIOR_MASK in behaviors}
    ids |= {NUM_METATILES_IN_PRIMARY + i for i, a in enumerate(secondary)
            if a & _BEHAVIOR_MASK in behaviors}
    return frozenset(ids)
