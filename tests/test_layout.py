"""Tests for the tileset_key override in convert_layout."""
from __future__ import annotations

from rpg2gba.tileset_converter.layout import TileGrid, convert_layout
from rpg2gba.tileset_converter.tile_map import (
    METATILE_ID_MASK,
    Bucket,
    Metatile,
    TileMap,
    TilesetChoice,
)

# Synthetic and real tileset ids for the per-map-packing scenario.
_SYNTH = 1007
_REAL = 7


def _synth_tile_map() -> TileMap:
    """TileMap keyed by the SYNTHETIC id (_SYNTH), not the real id (_REAL).

    Bucket mode (empty tiles dict) with passages so collapse_column can resolve
    passable/blocked/void. Using synth id as the sole key means any caller that
    uses the real id will get a KeyError — that's the scenario tileset_key fixes."""
    n = 600
    passages = [0] * n
    passages[500] = 15  # tile 500 is blocked
    return TileMap(
        tiles={_SYNTH: {}},  # empty -> bucket mode
        tilesets={_SYNTH: TilesetChoice("gTileset_P", "gTileset_S")},
        buckets={_SYNTH: Bucket(passable=10, blocked=11, void=7)},
        passages={_SYNTH: passages},
        priorities={_SYNTH: [0] * n},
        warps={_SYNTH: Metatile(99, 0, 0)},
    )


def _grid(width: int, height: int, layer0, layer1=None, layer2=None) -> TileGrid:
    """Build a 3-layer TileGrid from row-major per-layer lists."""
    cells = width * height
    z1 = list(layer1) if layer1 is not None else [0] * cells
    z2 = list(layer2) if layer2 is not None else [0] * cells
    return TileGrid(width, height, 3, list(layer0) + z1 + z2)


def _map_json(grid: TileGrid, tileset_id: int = _REAL) -> dict:
    """Map JSON with `tileset_id` set to the REAL id (as it comes from Phase 3)."""
    return {
        "tiles": {"xsize": grid.xsize, "ysize": grid.ysize, "zsize": grid.zsize, "data": grid.data},
        "width": grid.xsize,
        "height": grid.ysize,
        "tileset_id": tileset_id,
    }


def test_tileset_key_overrides_map_json_tileset_id() -> None:
    """convert_layout(..., tileset_key=SYNTH) uses the synthetic key for all TileMap
    lookups, even though map_json["tileset_id"] is the real id (_REAL).

    Without tileset_key the call would KeyError because the TileMap has no entry
    for the real id. With it, the synth key resolves correctly."""
    tm = _synth_tile_map()
    g = _grid(2, 1, [384, 500])  # cell (0,0) passable, cell (1,0) tile 500 (blocked)

    layout = convert_layout(
        _map_json(g, tileset_id=_REAL),
        tm,
        name="T",
        layout_const="LAYOUT_T",
        tileset_key=_SYNTH,
    )

    assert len(layout.blocks) == 2
    assert layout.blocks[0] & METATILE_ID_MASK == 10  # passable bucket
    assert layout.blocks[1] & METATILE_ID_MASK == 11  # blocked bucket
    # tileset choice comes from the synth key
    assert layout.primary_tileset == "gTileset_P"
    assert layout.secondary_tileset == "gTileset_S"


def test_tileset_key_none_uses_map_json_tileset_id() -> None:
    """tileset_key=None (default) falls back to map_json["tileset_id"] — backward compat."""
    tm = _synth_tile_map()
    g = _grid(1, 1, [384])

    # map_json["tileset_id"] == _REAL, which is not in the TileMap -> KeyError
    import pytest
    with pytest.raises(KeyError):
        convert_layout(_map_json(g, tileset_id=_REAL), tm, name="T", layout_const="LAYOUT_T")

    # Explicit None is the same as default
    with pytest.raises(KeyError):
        convert_layout(
            _map_json(g, tileset_id=_REAL),
            tm,
            name="T",
            layout_const="LAYOUT_T",
            tileset_key=None,
        )


def test_tileset_key_warp_override_uses_synth_key(tmp_path) -> None:
    """warp_overrides still work correctly when tileset_key is active."""
    tm = _synth_tile_map()
    g = _grid(2, 1, [384, 500])

    layout = convert_layout(
        _map_json(g, tileset_id=_REAL),
        tm,
        name="T",
        layout_const="LAYOUT_T",
        warp_overrides={(1, 0)},
        tileset_key=_SYNTH,
    )

    # cell (1,0) overridden by warp metatile (99, collision 0)
    assert layout.blocks[1] & METATILE_ID_MASK == 99
    assert (layout.blocks[1] >> 10) & 0x3 == 0
