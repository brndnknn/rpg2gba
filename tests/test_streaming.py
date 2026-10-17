"""tileset_converter.streaming: the streamed-map set and the build-time window budget."""
import json
import struct

import pytest

from rpg2gba.tileset_converter.layout import Layout
from rpg2gba.tileset_converter.streaming import (
    STREAM_FIRST_DOOR_SLOT,
    check_streamed_layout,
    is_streamed_tileset,
    streamed_map_ids,
    worst_window,
    write_stream_info,
)


def _wide(metatile_tiles: list[list[int]]) -> list[int]:
    """u32 wide words, 8 per metatile, tile id in the high half."""
    out: list[int] = []
    for tiles in metatile_tiles:
        out += [t << 16 for t in (tiles + [0] * 8)[:8]]
    return out


def test_streamed_set_reads_the_reference(tmp_path):
    path = tmp_path / "streamed.json"
    path.write_text(json.dumps({"maps": [40, 101]}), encoding="utf-8")
    assert streamed_map_ids(path) == {40, 101}
    assert is_streamed_tileset([7, 101], path)
    assert not is_streamed_tileset([7, 8], path)


def test_worst_window_counts_only_unpinned_tiles():
    # Metatile 0: pinned tiles only. Metatiles 1..: two private tiles each.
    n_pinned = 3
    metatiles = [[1, 2]] + [[10 + 2 * i, 11 + 2 * i] for i in range(40)]
    width, height = 20, 1
    blocks = [1 + x for x in range(width)]  # every cell a different metatile
    budget = worst_window(blocks, width, height, [0, 0, 0, 0], _wide(metatiles), n_pinned)
    # The view is 16 metatiles wide: at most 16 distinct cells, 2 tiles each.
    assert budget.worst == 32
    assert budget.slots == STREAM_FIRST_DOOR_SLOT - n_pinned


def test_worst_window_shares_repeated_tiles():
    metatiles = [[0], [5, 6, 7]]
    blocks = [1] * 9
    budget = worst_window(blocks, 3, 3, [0, 0, 0, 0], _wide(metatiles), 1)
    assert budget.worst == 3


def test_check_streamed_layout_fails_loud_over_budget(tmp_path):
    tdir = tmp_path / "data" / "tilesets" / "primary" / "uranium1999"
    tdir.mkdir(parents=True)
    # 16 cells, each metatile with 8 private tiles = 128 tiles; pin all but 100 slots.
    metatiles = [[0]] + [[1000 + 8 * i + k for k in range(8)] for i in range(16)]
    wide = _wide(metatiles)
    (tdir / "metatiles_wide.bin").write_bytes(struct.pack(f"<{len(wide)}I", *wide))
    write_stream_info(tdir, 2000, STREAM_FIRST_DOOR_SLOT - 100)
    layout = Layout("Big", "LAYOUT_BIG", 16, 1, "gTileset_Uranium1999", "gTileset_Uranium1999B",
                    blocks=list(range(1, 17)), border=[0, 0, 0, 0])
    with pytest.raises(ValueError, match="worst 16x16 window"):
        check_streamed_layout(layout, tmp_path)


def test_check_streamed_layout_ignores_stock_tilesets(tmp_path):
    layout = Layout("Small", "LAYOUT_SMALL", 1, 1, "gTileset_Uranium7", "gTileset_Uranium7B",
                    blocks=[0], border=[0, 0, 0, 0])
    assert check_streamed_layout(layout, tmp_path) is None
