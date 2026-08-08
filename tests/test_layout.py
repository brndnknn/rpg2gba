"""Tests for the tileset_key override in convert_layout."""
from __future__ import annotations

from rpg2gba.tileset_converter.layout import TileGrid, column_key, convert_layout
from rpg2gba.tileset_converter.tile_map import (
    METATILE_ID_MASK,
    Bucket,
    Metatile,
    TileMap,
    TilesetChoice,
    WarpInfo,
    serialize_column_key,
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
        warps={_SYNTH: WarpInfo(tiles={}, fallback=Metatile(99, 0, 0))},
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


def test_tileset_key_warp_override_prefers_per_column_metatile() -> None:
    """convert_layout picks the warp metatile matching the cell's OWN column key
    (fix #1) over the fallback, when the tileset's WarpInfo has one."""
    g = _grid(2, 1, [384, 500])  # cell (1,0) column key is ((0, 500),)
    door_key = column_key(g, 1, 0)
    passages = [0] * 600
    passages[500] = 15
    tm = TileMap(
        tiles={_SYNTH: {}},
        tilesets={_SYNTH: TilesetChoice("gTileset_P", "gTileset_S")},
        buckets={_SYNTH: Bucket(passable=10, blocked=11, void=7)},
        passages={_SYNTH: passages},
        priorities={_SYNTH: [0] * 600},
        warps={
            _SYNTH: WarpInfo(
                tiles={serialize_column_key(door_key): Metatile(42, 0, 0)},
                fallback=Metatile(99, 0, 0),
            )
        },
    )

    layout = convert_layout(
        _map_json(g, tileset_id=_REAL),
        tm,
        name="T",
        layout_const="LAYOUT_T",
        warp_overrides={(1, 0)},
        tileset_key=_SYNTH,
    )

    # cell (1,0)'s own column key ((0,500),) has a per-column entry (42), not the
    # generic fallback (99).
    assert layout.blocks[1] & METATILE_ID_MASK == 42
    assert (layout.blocks[1] >> 10) & 0x3 == 0  # collision forced to 0


def test_tileset_key_warp_override_falls_back_for_unmapped_column() -> None:
    """A warp coord whose column key has no per-column entry resolves to the
    tileset's fallback warp metatile."""
    g = _grid(2, 1, [384, 500])
    other_key = column_key(g, 0, 0)  # column ((0,384),) — NOT the warp cell's own
    tm = TileMap(
        tiles={_SYNTH: {}},
        tilesets={_SYNTH: TilesetChoice("gTileset_P", "gTileset_S")},
        buckets={_SYNTH: Bucket(passable=10, blocked=11, void=7)},
        passages={_SYNTH: [0] * 600},
        priorities={_SYNTH: [0] * 600},
        warps={
            _SYNTH: WarpInfo(
                tiles={serialize_column_key(other_key): Metatile(42, 0, 0)},
                fallback=Metatile(99, 0, 0),
            )
        },
    )

    layout = convert_layout(
        _map_json(g, tileset_id=_REAL),
        tm,
        name="T",
        layout_const="LAYOUT_T",
        warp_overrides={(1, 0)},  # column ((0,500),), not registered under "tiles"
        tileset_key=_SYNTH,
    )

    assert layout.blocks[1] & METATILE_ID_MASK == 99


# --- unblocked_cells (walkable overrides, map_set.WALKABLE_OVERRIDES) ----------

def test_unblocked_cells_force_passable_keep_art() -> None:
    """An unblocked cell keeps its own (blocked-bucket) art but its collision/
    elevation are force-stamped PASSABLE — the Map032 (38,43) tree-crown case."""
    tm = _synth_tile_map()
    g = _grid(2, 1, [384, 500])  # tile 500 reads blocked from its passage

    layout = convert_layout(
        _map_json(g, tileset_id=_REAL),
        tm,
        name="T",
        layout_const="LAYOUT_T",
        tileset_key=_SYNTH,
        unblocked_cells={(1, 0)},
    )

    assert layout.blocks[1] & METATILE_ID_MASK == 11  # blocked-bucket art kept
    assert (layout.blocks[1] >> 10) & 0x3 == 0  # collision forced passable
    assert (layout.blocks[1] >> 12) & 0xF == 3  # walkable elevation
    # the neighbouring cell is untouched
    assert (layout.blocks[0] >> 10) & 0x3 == 0


def test_unblocked_cells_conflict_with_blocked_fails_loud() -> None:
    tm = _synth_tile_map()
    g = _grid(2, 1, [384, 500])
    import pytest
    with pytest.raises(ValueError, match="contradictory"):
        convert_layout(
            _map_json(g, tileset_id=_REAL), tm, name="T", layout_const="LAYOUT_T",
            tileset_key=_SYNTH, blocked_cells={(1, 0)}, unblocked_cells={(1, 0)},
        )


def test_unblocked_cells_conflict_with_warp_fails_loud() -> None:
    tm = _synth_tile_map()
    g = _grid(2, 1, [384, 500])
    import pytest
    with pytest.raises(ValueError, match="contradictory"):
        convert_layout(
            _map_json(g, tileset_id=_REAL), tm, name="T", layout_const="LAYOUT_T",
            tileset_key=_SYNTH, warp_overrides={(1, 0)}, unblocked_cells={(1, 0)},
        )


# --- behavior_overrides (native sideways-stairs fix) ---------------------------


def _stair_tile_map() -> TileMap:
    """Like _synth_tile_map but with a stairs_left behavior_override whose
    per-column entry matches column key ((0, 500),) (tile 500, blocked bucket)."""
    n = 600
    passages = [0] * n
    passages[500] = 15  # tile 500 blocked (mirrors the RMXP solid-stair-event tile)
    stair_key = serialize_column_key(((0, 500),))
    return TileMap(
        tiles={_SYNTH: {}},
        tilesets={_SYNTH: TilesetChoice("gTileset_P", "gTileset_S")},
        buckets={_SYNTH: Bucket(passable=10, blocked=11, void=7)},
        passages={_SYNTH: passages},
        priorities={_SYNTH: [0] * n},
        behavior_overrides={
            _SYNTH: {
                "stairs_left": WarpInfo(
                    tiles={stair_key: Metatile(30, 0, 0)}, fallback=Metatile(77, 0, 0)
                )
            }
        },
    )


def test_behavior_override_stamps_metatile_and_forces_passable() -> None:
    """A behavior-override cell resolves to its own column's stair metatile and is
    ALWAYS emitted passable, even though the source column (tile 500) reads blocked
    — the invariant whose absence let the original solid-stairs bug ship."""
    tm = _stair_tile_map()
    g = _grid(2, 1, [384, 500])  # cell (1,0) column key ((0,500),), source-blocked

    layout = convert_layout(
        _map_json(g, tileset_id=_REAL),
        tm,
        name="T",
        layout_const="LAYOUT_T",
        tileset_key=_SYNTH,
        behavior_overrides={(1, 0): "stairs_left"},
    )

    assert layout.blocks[1] & METATILE_ID_MASK == 30  # its own column's stair art
    assert (layout.blocks[1] >> 10) & 0x3 == 0  # PASSABLE_COLLISION
    assert (layout.blocks[1] >> 12) & 0xF == 3  # PASSABLE_ELEVATION
    # untouched neighbour cell still resolves normally (passable bucket, tile 384)
    assert layout.blocks[0] & METATILE_ID_MASK == 10


def test_behavior_override_falls_back_for_unmapped_column() -> None:
    """A behavior-override cell whose column key has no per-column entry resolves
    to the kind's fallback metatile, still forced passable."""
    tm = _stair_tile_map()
    g = _grid(2, 1, [384, 384])  # cell (1,0) column key ((0,384),) — not registered

    layout = convert_layout(
        _map_json(g, tileset_id=_REAL),
        tm,
        name="T",
        layout_const="LAYOUT_T",
        tileset_key=_SYNTH,
        behavior_overrides={(1, 0): "stairs_left"},
    )

    assert layout.blocks[1] & METATILE_ID_MASK == 77  # fallback
    assert (layout.blocks[1] >> 10) & 0x3 == 0


def test_behavior_override_conflict_with_warp_fails_loud() -> None:
    tm = _stair_tile_map()
    g = _grid(2, 1, [384, 500])
    import pytest
    with pytest.raises(ValueError, match="warp_override"):
        convert_layout(
            _map_json(g, tileset_id=_REAL), tm, name="T", layout_const="LAYOUT_T",
            tileset_key=_SYNTH, warp_overrides={(1, 0)},
            behavior_overrides={(1, 0): "stairs_left"},
        )


def test_behavior_override_conflict_with_blocked_cells_fails_loud() -> None:
    """This is the backstop for the regression case: metadata_wiring's
    through-block collection must exclude stair cells, but if it doesn't, this
    must fail loud rather than silently re-blocking the stairs."""
    tm = _stair_tile_map()
    g = _grid(2, 1, [384, 500])
    import pytest
    with pytest.raises(ValueError, match="through-blocked"):
        convert_layout(
            _map_json(g, tileset_id=_REAL), tm, name="T", layout_const="LAYOUT_T",
            tileset_key=_SYNTH, blocked_cells={(1, 0)},
            behavior_overrides={(1, 0): "stairs_left"},
        )


def test_behavior_override_wins_over_unblocked_cells_overlap() -> None:
    """Overlap between behavior_overrides and unblocked_cells is redundant (both
    force passable), not contradictory, and is allowed — the behavior stamp's own
    metatile (not the plain collapse_column art) must still win."""
    tm = _stair_tile_map()
    g = _grid(2, 1, [384, 500])

    layout = convert_layout(
        _map_json(g, tileset_id=_REAL),
        tm,
        name="T",
        layout_const="LAYOUT_T",
        tileset_key=_SYNTH,
        behavior_overrides={(1, 0): "stairs_left"},
        unblocked_cells={(1, 0)},
    )

    assert layout.blocks[1] & METATILE_ID_MASK == 30  # behavior metatile, not bucket art
    assert (layout.blocks[1] >> 10) & 0x3 == 0
