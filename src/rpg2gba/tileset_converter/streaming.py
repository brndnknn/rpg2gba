"""Which maps use the streaming tile engine, and its budget constants.

`reference/streamed_maps.json` is the one source of truth for the streamed set
(reference/streaming_prototype_plan.md §3.8). The constants mirror
`engine/include/field_stream.h`.
"""
from __future__ import annotations

import json
import logging
import struct
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rpg2gba.tileset_converter.layout import Layout

logger = logging.getLogger(__name__)

STREAMED_MAPS_PATH = Path(__file__).resolve().parents[3] / "reference" / "streamed_maps.json"

# field_stream.h FIELD_STREAM_MAX_TILES: the largest tile pool one streamed tileset may have.
STREAM_MAX_TILES: int = 3072
# field_stream.h FIELD_STREAM_FIRST_DOOR_SLOT: slots from here up hold door frames.
STREAM_FIRST_DOOR_SLOT: int = 1024 - 16
# fieldmap.h MAX_MAP_DATA_SIZE: the backup grid (map + a 7-cell margin, 15 wider and
# 14 taller) must fit, or InitMapLayoutData silently loads nothing but border.
MAX_MAP_DATA_SIZE: int = 10240


def streamed_map_ids(path: Path = STREAMED_MAPS_PATH) -> frozenset[int]:
    """The Uranium map ids that are streamed."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return frozenset(int(m) for m in data["maps"])


def is_streamed_tileset(map_ids: Iterable[int], path: Path = STREAMED_MAPS_PATH) -> bool:
    """Whether a tileset holding `map_ids` is emitted in the streamed format.

    One streamed map makes its whole tileset streamed (a shared group streams
    together; the plan prefers remapped seams, so in practice it is one map)."""
    streamed = streamed_map_ids(path)
    return any(int(m) in streamed for m in map_ids)


# -- build-time window budget (reference/streaming_prototype_plan.md §3.4) -----

# The engine's overworld ring buffer is 32x32 tiles = 16x16 metatiles, all resident.
WINDOW_METATILES: int = 16
# With the player at map x, the buffer spans map x-7 .. x+8 (MAP_OFFSET = 7).
_VIEW_BEFORE: int = 7
_VIEW_AFTER: int = WINDOW_METATILES - 1 - _VIEW_BEFORE
STREAM_INFO_NAME = "stream.json"
_METATILE_ID_MASK = 0x07FF


@dataclass
class WindowBudget:
    worst: int           # streamed (non-pinned) tiles in the worst 16x16 window
    at: tuple[int, int]  # player position (map-local) of that window
    n_pinned: int
    slots: int           # slots the cache can hand out: first door slot - pinned

    @property
    def slack(self) -> int:
        return self.slots - self.worst


def worst_window(blocks: list[int], width: int, height: int, border: list[int],
                 wide_words: list[int], n_pinned: int) -> WindowBudget:
    """The most streamed tiles any player position needs resident at once.

    The view outside the map is filled with the 2x2 border pattern, as
    `GetBorderBlockAt` does where no connection is. A connected neighbour's
    strip is NOT counted here (it is resolved at runtime); the emulator screen
    check measures it on the real backup layout."""
    def tiles_of(mid: int) -> list[int]:
        words = wide_words[mid * 8:(mid + 1) * 8]
        return [w >> 16 for w in words if (w >> 16) >= n_pinned]

    pw, ph = width + WINDOW_METATILES - 1, height + WINDOW_METATILES - 1
    cell_tiles: list[list[int]] = []
    for gy in range(ph):
        for gx in range(pw):
            x, y = gx - _VIEW_BEFORE, gy - _VIEW_BEFORE
            if 0 <= x < width and 0 <= y < height:
                block = blocks[x + width * y]
            else:
                # GetBorderBlockAt indexes with backup-grid coordinates (map + 7).
                bx, by = x + _VIEW_BEFORE, y + _VIEW_BEFORE
                block = border[((bx + 1) & 1) + ((by + 1) & 1) * 2]
            cell_tiles.append(tiles_of(block & _METATILE_ID_MASK))

    best, best_at = -1, (0, 0)
    for py in range(height):
        counts: Counter[int] = Counter()
        for gy in range(py, py + WINDOW_METATILES):
            for gx in range(WINDOW_METATILES):
                counts.update(cell_tiles[gx + pw * gy])
        for px in range(width):
            if px:
                for gy in range(py, py + WINDOW_METATILES):
                    counts.subtract(cell_tiles[(px - 1) + pw * gy])
                    counts.update(cell_tiles[(px + WINDOW_METATILES - 1) + pw * gy])
            live = sum(1 for c in counts.values() if c > 0)
            if live > best:
                best, best_at = live, (px, py)
    return WindowBudget(best, best_at, n_pinned, STREAM_FIRST_DOOR_SLOT - n_pinned)


def write_stream_info(primary_dir: Path, n_tiles: int, n_pinned: int) -> None:
    """Sidecar next to a streamed tileset's art, read by `check_streamed_layout`."""
    (Path(primary_dir) / STREAM_INFO_NAME).write_text(
        json.dumps({"n_tiles": n_tiles, "n_pinned": n_pinned}) + "\n", encoding="utf-8"
    )


def check_streamed_layout(layout: "Layout", fork: Path) -> WindowBudget | None:
    """Fail loud if a streamed layout's worst window cannot fit the tile cache.

    Returns None for a layout on a stock (non-streamed) tileset."""
    stem = layout.primary_tileset.removeprefix("gTileset_")
    tdir = Path(fork) / "data" / "tilesets" / "primary" / stem.lower()
    info_path = tdir / STREAM_INFO_NAME
    if not info_path.is_file():
        return None
    info = json.loads(info_path.read_text(encoding="utf-8"))
    cells = (layout.width + 15) * (layout.height + 14)
    if cells > MAX_MAP_DATA_SIZE:
        raise ValueError(
            f"{layout.name}: {layout.width}x{layout.height} needs {cells} backup-grid cells, "
            f"over MAX_MAP_DATA_SIZE {MAX_MAP_DATA_SIZE}; the engine would load only its "
            "border. Streaming does not lift this limit; split the map instead"
        )
    raw = (tdir / "metatiles_wide.bin").read_bytes()
    wide = list(struct.unpack(f"<{len(raw) // 4}I", raw))
    budget = worst_window(layout.blocks, layout.width, layout.height, layout.border,
                          wide, int(info["n_pinned"]))
    if budget.slack < 0:
        raise ValueError(
            f"{layout.name}: the worst 16x16 window (player at {budget.at}) needs "
            f"{budget.worst} streamed tiles, but the cache has {budget.slots} slots "
            f"({STREAM_FIRST_DOOR_SLOT} minus {budget.n_pinned} pinned)"
        )
    logger.info("  %s streamed: worst window %d of %d slots (slack %d, at %s)",
                layout.name, budget.worst, budget.slots, budget.slack, budget.at)
    return budget
