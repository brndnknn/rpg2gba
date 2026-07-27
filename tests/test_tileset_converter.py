"""Phase 5 acceptance scaffold — the tests the assignment must make pass.

These are written against the stub APIs in `rpg2gba.tileset_converter` and are
SKIPPED until each section is implemented (the stubs `raise NotImplementedError`).
As you implement a section, delete its `pytest.skip(...)` line and flesh the test
out into a real round-trip / golden / edge-case check (CLAUDE.md §8). They encode
the acceptance checklists from PHASE5_PLAN.md so the target is concrete.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from rpg2gba.conversion_agent import poryscript
from rpg2gba.conversion_agent.flag_registry import FlagRegistry, temp_switch_flag_name
from rpg2gba.tileset_converter import layout as layout_mod
from rpg2gba.tileset_converter import map_constants as mc
from rpg2gba.tileset_converter import metadata_wiring as mw
from rpg2gba.tileset_converter import npc_gfx as npc_gfx_mod
from rpg2gba.tileset_converter.layout import TileGrid, column_key
from rpg2gba.tileset_converter.npc_gfx import DEFAULT_NPC_GFX_MAP, load_npc_gfx_map
from rpg2gba.tileset_converter.route_bytecode import RouteRegistry
from rpg2gba.tileset_converter.tile_map import (
    METATILE_ID_MASK,
    Bucket,
    Metatile,
    TileMap,
    TilesetChoice,
    load_tile_map,
    normalize_tile_id,
    serialize_column_key,
)

_TODO = "Phase 5: implement this section, then un-skip and flesh out the test"

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PRESEED = _REPO_ROOT / "reference" / "guides" / "essentials_to_emerald_map.md"
_SWITCHES = _REPO_ROOT / "reference" / "uranium_switches.json"
_VARIABLES = _REPO_ROOT / "reference" / "uranium_variables.json"


# --- helpers that are real already (no skip needed) ---------------------------

def test_metatile_block_packing() -> None:
    """Metatile.to_block packs metatile|collision<<10|elevation<<12 (no skip — pure)."""
    block = Metatile(metatile_id=0x123, collision=2, elevation=3).to_block()
    assert block & METATILE_ID_MASK == 0x123
    assert (block >> 10) & 0x3 == 2
    assert (block >> 12) & 0xF == 3


def test_tilegrid_indexing() -> None:
    """TileGrid.tile_at uses the Phase 3 flat layout index (no skip — pure)."""
    # 2x2x2: layer 0 = [1,2,3,4], layer 1 = [5,6,7,8]
    grid = TileGrid(xsize=2, ysize=2, zsize=2, data=[1, 2, 3, 4, 5, 6, 7, 8])
    assert grid.tile_at(0, 0, 0) == 1
    assert grid.tile_at(1, 1, 0) == 4
    assert grid.tile_at(0, 0, 1) == 5
    assert grid.column(1, 0) == [2, 6]


def test_blockdata_round_trip_reader() -> None:
    """read_blockdata is the inverse of the LE u16 packing (no skip — pure)."""
    blocks = [0x0001, 0x0FFF, 0x3C04]
    raw = struct.pack(f"<{len(blocks)}H", *blocks)
    assert layout_mod.read_blockdata.__doc__  # exists
    # round-trip via a temp file is exercised in test_layout_round_trip below.
    assert list(struct.unpack(f"<{len(raw) // 2}H", raw)) == blocks


# --- 5.1 tile_map ------------------------------------------------------------

def _passages(blocked_ranges: list[tuple[int, int]], n: int = 600) -> list[int]:
    """A passages array (length n) with the given [lo,hi) ranges set blocked (15)."""
    arr = [0] * n
    for lo, hi in blocked_ranges:
        for i in range(lo, hi):
            arr[i] = 15
    return arr


def _write_slice_table(tmp_path: Path) -> tuple[Path, Path]:
    """Self-contained tileset_map.json + passages oracle for the two slice tilesets."""
    table = {
        "tilesets": {
            "19": {"primary": "gTileset_Building", "secondary": "gTileset_BrendansMaysHouse"},
            "22": {"primary": "gTileset_General", "secondary": "gTileset_Petalburg"},
        },
        "buckets": {
            "19": {"passable": 513, "blocked": 622, "void": 1},
            "22": {"passable": 1, "blocked": 468, "void": 468},
        },
        "warps": {
            "19": {"metatile": 529, "collision": 0, "elevation": 0},
            "22": {"metatile": 167, "collision": 0, "elevation": 0},
        },
        # one explicit override at autotile-2 base 96 (tests normalization + precedence)
        "tiles": {"19": {"96": {"metatile": 50, "collision": 0, "elevation": 3}}, "22": {}},
        "stacks": {},
    }
    oracle = {  # autotile 1 (ids 48..95) blocked; everything else passable
        "19": {
            "passages": _passages([(48, 96)]),
            "priorities": _passages([]),
            "terrain_tags": _passages([]),
        },
        "22": {
            "passages": _passages([(48, 96)]),
            "priorities": _passages([]),
            "terrain_tags": _passages([]),
        },
    }
    tpath, opath = tmp_path / "tileset_map.json", tmp_path / "tilesets.json"
    tpath.write_text(json.dumps(table), encoding="utf-8")
    opath.write_text(json.dumps(oracle), encoding="utf-8")
    return tpath, opath


def test_tile_map_loads_and_explicit_precedence(tmp_path: Path) -> None:
    tpath, opath = _write_slice_table(tmp_path)
    tm = load_tile_map(tpath, opath)
    assert tm.tileset_for(19) == TilesetChoice("gTileset_Building", "gTileset_BrendansMaysHouse")
    # explicit entry wins; autotile variant 100 normalizes to base 96
    assert normalize_tile_id(100) == 96
    assert tm.lookup(19, 100) == Metatile(50, 0, 3)
    assert tm.lookup(19, 96) == Metatile(50, 0, 3)
    assert tm.void(22) == Metatile(468, 1, 0)
    # warp metatiles (step-on door behavior, collision 0) are loaded per tileset
    assert tm.warp(19) == Metatile(529, 0, 0)
    assert tm.warp(22) == Metatile(167, 0, 0)
    assert tm.has_warp(19) and not tm.has_warp(99)
    with pytest.raises(KeyError):  # no warp metatile -> fail loud, not a dead warp
        tm.warp(99)


def test_tile_map_bucket_fallback(tmp_path: Path) -> None:
    tpath, opath = _write_slice_table(tmp_path)
    tm = load_tile_map(tpath, opath)
    # autotile 1 variant (passage 15, no explicit entry) -> blocked bucket
    assert tm.lookup(19, 52) == Metatile(622, 1, 0)
    # passable tiles (passage 0) -> passable bucket
    assert tm.lookup(19, 400) == Metatile(513, 0, 3)
    assert tm.lookup(22, 200) == Metatile(1, 0, 3)
    # blocked autotile in the town -> blocked bucket
    assert tm.lookup(22, 60) == Metatile(468, 1, 0)


def test_tile_map_unmapped_fails_loud(tmp_path: Path) -> None:
    """lookup() on an unmapped tileset raises with the ids; tile_id 0 is rejected."""
    tpath, opath = _write_slice_table(tmp_path)
    tm = load_tile_map(tpath, opath)
    with pytest.raises(KeyError) as exc:
        tm.lookup(99, 384)
    assert "99" in str(exc.value) and "384" in str(exc.value)
    with pytest.raises(ValueError):
        tm.lookup(19, 0)


def test_tile_map_validate_rejects(tmp_path: Path) -> None:
    base = {
        "tilesets": {
            "19": {"primary": "gTileset_Building", "secondary": "gTileset_BrendansMaysHouse"},
        },
        "buckets": {"19": {"passable": 1, "blocked": 2, "void": 3}},
        "tiles": {"19": {}},
    }

    def _load(mutate) -> None:
        d = json.loads(json.dumps(base))
        mutate(d)
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(d), encoding="utf-8")
        load_tile_map(p, None)

    with pytest.raises(ValueError):  # metatile beyond the 10-bit field
        _load(lambda d: d["tiles"]["19"].update({"384": {"metatile": 0x400}}))
    with pytest.raises(ValueError):  # bad collision
        _load(lambda d: d["tiles"]["19"].update({"384": {"metatile": 5, "collision": 4}}))
    with pytest.raises(ValueError):  # tiles references an unknown tileset
        _load(lambda d: d["tiles"].update({"77": {}}))
    with pytest.raises(ValueError):  # bucket missing a role
        _load(lambda d: d["buckets"]["19"].pop("void"))
    with pytest.raises(ValueError):  # missing secondary
        _load(lambda d: d["tilesets"]["19"].pop("secondary"))
    with pytest.raises(ValueError):  # warp metatile beyond the 10-bit field
        _load(lambda d: d.update({"warps": {"19": {"metatile": 0x400}}}))
    with pytest.raises(ValueError):  # warp references an unknown tileset
        _load(lambda d: d.update({"warps": {"77": {"metatile": 5}}}))


# --- column contract ---------------------------------------------------------

def test_serialize_column_key_format_and_determinism() -> None:
    """serialize_column_key returns canonical [[z,t],...] JSON, same value every call."""
    key: tuple[tuple[int, int], ...] = ((0, 384), (2, 400))
    s = serialize_column_key(key)
    assert json.loads(s) == [[0, 384], [2, 400]]
    assert serialize_column_key(key) == s  # deterministic


def test_has_columns_true_false() -> None:
    """has_columns is True iff the tileset's tiles dict is non-empty."""
    k = ((0, 384),)
    tm_col = TileMap(
        tiles={7: {serialize_column_key(k): Metatile(10, 0, 3)}},
        tilesets={7: TilesetChoice("gP", "gS")},
        buckets={7: Bucket(5, 6, 7)},
    )
    assert tm_col.has_columns(7) is True
    assert tm_col.has_columns(99) is False  # absent tileset -> False

    tm_bkt = TileMap(
        tiles={7: {}},  # explicitly empty -> False
        tilesets={7: TilesetChoice("gP", "gS")},
        buckets={7: Bucket(5, 6, 7)},
    )
    assert tm_bkt.has_columns(7) is False


def test_lookup_column_hit_and_miss() -> None:
    """lookup_column returns the Metatile on hit; raises KeyError (with ids) on miss."""
    k = ((0, 384), (2, 400))
    tm = TileMap(
        tiles={7: {serialize_column_key(k): Metatile(42, 0, 3)}},
        tilesets={7: TilesetChoice("gP", "gS")},
        buckets={7: Bucket(5, 6, 7)},
    )
    assert tm.lookup_column(7, k) == Metatile(42, 0, 3)
    with pytest.raises(KeyError) as exc:
        tm.lookup_column(7, ((0, 999),))
    assert "999" in str(exc.value)


def test_column_key_z_ascending_skips_empty_no_normalization() -> None:
    """column_key returns non-empty layers as (z, tile_id) z-ascending; empty layers
    are skipped; autotile ids are NOT normalized (variants stay distinct)."""
    g = _grid(1, 1, [384], [0], [400])  # z0=384, z1=0 (empty), z2=400
    assert column_key(g, 0, 0) == ((0, 384), (2, 400))
    # z1 is skipped; autotile 400 is NOT normalized to its base

    g_empty = _grid(1, 1, [0])  # all-empty column
    assert column_key(g_empty, 0, 0) == ()

    # Autotile variant kept distinct from base: 49 != 48
    g_auto = _grid(1, 1, [49])
    assert column_key(g_auto, 0, 0) == ((0, 49),)


def test_collapse_column_uses_column_path() -> None:
    """collapse_column takes the lookup_column path when has_columns is True;
    different column keys yield different metatile ids even if the topmost tile
    in bucket mode would map to the same bucket."""
    n = 600
    passages = [0] * n
    prio = [0] * n
    k1 = ((0, 384),)
    k2 = ((0, 385),)
    tm = TileMap(
        tiles={7: {
            serialize_column_key(k1): Metatile(42, 0, 3),
            serialize_column_key(k2): Metatile(43, 0, 3),
        }},
        tilesets={7: TilesetChoice("gP", "gS")},
        buckets={7: Bucket(5, 6, 7)},
        passages={7: passages},
        priorities={7: prio},
        warps={7: Metatile(99, 0, 0)},
    )
    assert tm.has_columns(7) is True

    g1 = _grid(1, 1, [384])
    assert layout_mod.collapse_column(g1, 0, 0, tm, 7).metatile_id == 42

    g2 = _grid(1, 1, [385])
    assert layout_mod.collapse_column(g2, 0, 0, tm, 7).metatile_id == 43

    # empty column in column mode -> void metatile
    g_empty = _grid(1, 1, [0])
    assert layout_mod.collapse_column(g_empty, 0, 0, tm, 7) == Metatile(7, 1, 0)


# --- 5.2 layout --------------------------------------------------------------

# _layout_tilemap uses empty tiles -> has_columns(7)=False -> bucket mode.
# Bucket ids: passable=10, blocked=11, void=7 (all distinct for legibility).
def _layout_tilemap(priorities: dict[int, int] | None = None) -> TileMap:
    """A small TileMap in BUCKET MODE (empty tiles) with a passages oracle so layout
    tests can exercise passable/blocked/void/warp/collision behavior."""
    n = 600
    passages = [0] * n
    passages[500] = 15  # tile 500 blocks (low nibble != 0)
    prio = [0] * n
    for tid, p in (priorities or {}).items():
        prio[tid] = p
    return TileMap(
        tiles={7: {}},  # empty -> has_columns(7) = False -> bucket mode
        tilesets={7: TilesetChoice("gTileset_P", "gTileset_S")},
        buckets={7: Bucket(passable=10, blocked=11, void=7)},
        passages={7: passages},
        priorities={7: prio},
        warps={7: Metatile(99, 0, 0)},
    )


def _grid(width: int, height: int, layer0, layer1=None, layer2=None) -> TileGrid:
    """Build a 3-layer TileGrid from row-major (y*width+x) per-layer lists."""
    cells = width * height
    z1 = list(layer1) if layer1 is not None else [0] * cells
    z2 = list(layer2) if layer2 is not None else [0] * cells
    return TileGrid(width, height, 3, list(layer0) + z1 + z2)


def _map_json(grid: TileGrid, tileset_id: int = 7) -> dict:
    return {
        "tiles": {"xsize": grid.xsize, "ysize": grid.ysize, "zsize": grid.zsize, "data": grid.data},
        "width": grid.xsize,
        "height": grid.ysize,
        "tileset_id": tileset_id,
    }


def test_collapse_precedence() -> None:
    """In bucket mode the topmost-non-empty layer wins for passability; all-empty -> void."""
    tm = _layout_tilemap()
    # Two layers (384 on z0, 385 on z2): topmost=385, passable -> passable bucket.
    g = _grid(1, 1, [384], [0], [385])
    assert layout_mod.collapse_column(g, 0, 0, tm, 7).metatile_id == 10  # passable bucket
    # Single layer (384 on z0): passable -> passable bucket.
    g = _grid(1, 1, [384])
    assert layout_mod.collapse_column(g, 0, 0, tm, 7).metatile_id == 10
    # All-empty column -> the tileset's void metatile (impassable).
    g = _grid(1, 1, [0])
    assert layout_mod.collapse_column(g, 0, 0, tm, 7) == Metatile(7, 1, 0)


def test_collapse_collision_is_layer_combined() -> None:
    """A passable over-the-player tile (priority>0) above a blocking trunk reads
    blocked — collision comes from the combined rule, not the topmost tile alone.
    The visual metatile is the topmost one resolved through the bucket."""
    tm = _layout_tilemap(priorities={387: 1})  # tile 387 drawn over the player
    # trunk(500, blocks) under treetop(387, passable over-player)
    g = _grid(1, 1, [500], [0], [387])
    mt = layout_mod.collapse_column(g, 0, 0, tm, 7)
    # Visual: topmost=387 is passable -> passable bucket (10).
    assert mt.metatile_id == 10
    # Collision: _cell_blocked scans top-down, skips priority>0 tile 387, finds tile 500
    # (blocked) -> collision=1.
    assert mt.collision == 1


def _terrain_tag_tilemap(
    tags: dict[int, int],
    priorities: dict[int, int] | None = None,
    extra_blocked: tuple[int, ...] = (),
) -> TileMap:
    """Bucket-mode TileMap (same shape as `_layout_tilemap`) plus a `terrain_tags`
    oracle — tile 500 is a blocker (passage 0x0F, tag 0/Neutral unless overridden
    by `tags`), everything else is passable ground (passage 0, tag 0). Any tile id
    in `extra_blocked` also gets a blocking passage (0x0F), independent of `tags`."""
    n = 600
    passages = [0] * n
    passages[500] = 15  # tile 500 blocks
    for tid in extra_blocked:
        passages[tid] = 15
    prio = [0] * n
    for tid, p in (priorities or {}).items():
        prio[tid] = p
    tag_arr = [0] * n
    for tid, tag in tags.items():
        tag_arr[tid] = tag
    return TileMap(
        tiles={7: {}},  # empty -> bucket mode
        tilesets={7: TilesetChoice("gTileset_P", "gTileset_S")},
        buckets={7: Bucket(passable=10, blocked=11, void=7)},
        passages={7: passages},
        priorities={7: prio},
        terrain_tags={7: tag_arr},
        warps={7: Metatile(99, 0, 0)},
    )


def test_cell_blocked_shadow_over_blocker_reads_blocked() -> None:
    """A shadow decal (tag 20, passage 0x00, priority 0) sitting above a
    passage-0x0F blocker above ground: the shadow is skipped entirely, so the
    blocker underneath decides -> BLOCKED. Pre-fix, the shadow's own
    passage=0/priority=0 would have early-accepted the cell as passable before
    the blocker was ever examined (the Moki Town 8-cell bug)."""
    tm = _terrain_tag_tilemap({590: layout_mod.TERRAIN_TAG_SHADOW})
    # z0=ground(400), z1=blocker(500), z2=shadow(590, drawn on top)
    g = _grid(1, 1, [400], [500], [590])
    assert layout_mod._cell_blocked(g, 0, 0, tm, 7) is True


def test_cell_blocked_shadow_over_plain_ground_reads_passable() -> None:
    """A shadow decal above plain (non-blocking) ground: skipped, ground decides
    -> PASSABLE."""
    tm = _terrain_tag_tilemap({590: layout_mod.TERRAIN_TAG_SHADOW})
    g = _grid(1, 1, [400], [0], [590])  # ground, empty, shadow on top
    assert layout_mod._cell_blocked(g, 0, 0, tm, 7) is False


def test_cell_blocked_bridge_tile_skipped_same_as_shadow() -> None:
    """A Bridge-tagged tile (tag 15) is skipped the same way as Shadow — even
    though its own passage would block, off-bridge (always true here) it's
    ignored and the tile beneath decides."""
    tm = _terrain_tag_tilemap({595: layout_mod.TERRAIN_TAG_BRIDGE})
    g = _grid(1, 1, [400], [0], [595])  # ground, empty, bridge deck on top
    assert layout_mod._cell_blocked(g, 0, 0, tm, 7) is False
    # Now make the bridge tile's OWN passage block, to prove it's really SKIPPED
    # (ignored) and not just incidentally passable.
    tm2 = _terrain_tag_tilemap({595: layout_mod.TERRAIN_TAG_BRIDGE}, extra_blocked=(595,))
    assert layout_mod._cell_blocked(g, 0, 0, tm2, 7) is False


def test_cell_blocked_shadow_only_column_is_passable_not_void() -> None:
    """A column made up ENTIRELY of skipped (shadow) tiles must NOT fall into the
    'all-empty = void = blocked' catch-all -> Uranium's scan falls through the
    loop and returns passable (true), so ours must too."""
    tm = _terrain_tag_tilemap({590: layout_mod.TERRAIN_TAG_SHADOW})
    g = _grid(1, 1, [590])  # single shadow tile, nothing else
    assert layout_mod._cell_blocked(g, 0, 0, tm, 7) is False
    # Contrast: a genuinely all-empty column IS void = blocked.
    g_empty = _grid(1, 1, [0])
    assert layout_mod._cell_blocked(g_empty, 0, 0, tm, 7) is True


def test_index_order_row_major() -> None:
    """convert_layout emits blocks in row-major y*width+x order (guards the
    layer-major -> row-major transposition)."""
    tm = _layout_tilemap()
    g = _grid(3, 2, [384, 385, 386, 387, 388, 389])  # all passable
    layout = layout_mod.convert_layout(_map_json(g), tm, name="T", layout_const="LAYOUT_T")
    # All 6 cells passable -> all passable bucket (metatile 10), in row-major order.
    for i in range(6):
        assert layout.blocks[i] & METATILE_ID_MASK == 10
    assert len(layout.blocks) == 6


def test_layout_round_trip(tmp_path: Path) -> None:
    """convert_layout on a 2x2 map -> map.bin of width*height*2 bytes, re-readable
    to the same metatile ids."""
    tm = _layout_tilemap()
    g = _grid(2, 2, [384, 385, 386, 387])  # all passable
    layout = layout_mod.convert_layout(_map_json(g), tm, name="T", layout_const="LAYOUT_T")
    layout.write(tmp_path)
    map_bin = tmp_path / "layouts" / "T" / "map.bin"
    assert map_bin.stat().st_size == 2 * 2 * 2  # width*height*2 bytes
    blocks = layout_mod.read_blockdata(map_bin)
    assert [b & METATILE_ID_MASK for b in blocks] == [10, 10, 10, 10]  # all passable
    assert (tmp_path / "layouts" / "T" / "border.bin").stat().st_size == 8


def test_warp_override_stamps_warp_metatile() -> None:
    """warp_overrides overwrite the cell with the tileset's warp metatile (the
    door/stairs that carries a warp behavior, collision 0) — REQUIRED for the
    warp_event to fire, not just to make the cell walkable."""
    tm = _layout_tilemap()
    g = _grid(2, 1, [384, 500])  # cell (0,0) passable; cell (1,0) tile 500 (blocked)
    plain = layout_mod.convert_layout(_map_json(g), tm, name="T", layout_const="LAYOUT_T")
    assert plain.blocks[1] & METATILE_ID_MASK == 11  # blocked bucket (tile 500 blocks)
    assert (plain.blocks[1] >> 10) & 0x3 == 1        # blocked collision without override
    forced = layout_mod.convert_layout(
        _map_json(g), tm, name="T", layout_const="LAYOUT_T", warp_overrides={(1, 0)}
    )
    assert forced.blocks[1] & METATILE_ID_MASK == 99  # the warp metatile (door behavior)
    assert (forced.blocks[1] >> 10) & 0x3 == 0        # collision 0 -> steppable
    assert (forced.blocks[1] >> 12) & 0xF == 0        # elevation 0 (door transition)


def test_warp_override_fails_loud_without_warp_metatile() -> None:
    """A warp cell on a tileset with no `warps` entry aborts the map — silently
    leaving an MB_NORMAL floor there means the warp_event would never fire."""
    tm = TileMap(
        tiles={},  # empty -> bucket mode; has_columns(7) = False
        tilesets={7: TilesetChoice("gP", "gS")},
        buckets={7: Bucket(passable=5, blocked=6, void=7)},
        passages={7: [0] * 600},
        priorities={7: [0] * 600},
    )  # no warps
    g = _grid(1, 1, [384])
    with pytest.raises(KeyError) as exc:
        layout_mod.convert_layout(
            _map_json(g), tm, name="T", layout_const="LAYOUT_T", warp_overrides={(0, 0)}
        )
    assert "warp metatile" in str(exc.value)


def test_blocked_cells_stamps_collision_keeps_visual_metatile() -> None:
    """blocked_cells (fix #3) force BLOCKED_COLLISION + BLOCKED_ELEVATION but keep
    the cell's own visual metatile id — unlike warp_overrides, which also swaps
    the metatile id to the door art."""
    tm = _layout_tilemap()
    g = _grid(2, 1, [384, 384])  # both passable ground -> both bucket id 10
    plain = layout_mod.convert_layout(_map_json(g), tm, name="T", layout_const="LAYOUT_T")
    assert plain.blocks[1] & METATILE_ID_MASK == 10
    assert (plain.blocks[1] >> 10) & 0x3 == 0  # passable collision

    forced = layout_mod.convert_layout(
        _map_json(g), tm, name="T", layout_const="LAYOUT_T", blocked_cells={(1, 0)}
    )
    assert forced.blocks[1] & METATILE_ID_MASK == 10  # same visual metatile
    assert (forced.blocks[1] >> 10) & 0x3 == 1  # forced blocked collision
    assert (forced.blocks[1] >> 12) & 0xF == 0  # forced blocked elevation
    assert forced.blocks[0] == plain.blocks[0]  # untouched cell unaffected


def test_blocked_cells_raises_on_warp_override_collision() -> None:
    """A cell in BOTH warp_overrides and blocked_cells is a converter bug — a warp
    must stay enterable — fail loud with the coords rather than picking a winner."""
    tm = _layout_tilemap()
    g = _grid(1, 1, [384])
    with pytest.raises(ValueError) as exc:
        layout_mod.convert_layout(
            _map_json(g), tm, name="T", layout_const="LAYOUT_T",
            warp_overrides={(0, 0)}, blocked_cells={(0, 0)},
        )
    assert "(0, 0)" in str(exc.value)


def test_layout_fail_loud_on_unmapped_tile() -> None:
    """A tile with no explicit entry and no bucket aborts the map with its ids."""
    tm = TileMap(
        tiles={},  # empty outer dict -> bucket mode
        tilesets={7: TilesetChoice("gP", "gS")},
        buckets={},  # no bucket -> nothing falls back
    )
    g = _grid(1, 1, [999])
    with pytest.raises(KeyError) as exc:
        layout_mod.convert_layout(_map_json(g), tm, name="T", layout_const="LAYOUT_T")
    assert "999" in str(exc.value)


def test_layout_idempotent(tmp_path: Path) -> None:
    """Re-running convert_layout + write yields byte-identical .bin; append_layouts
    twice yields identical json."""
    tm = _layout_tilemap()
    g = _grid(3, 2, [384, 385, 386, 387, 388, 389])  # all passable
    a = layout_mod.convert_layout(_map_json(g), tm, name="T", layout_const="LAYOUT_T")
    b = layout_mod.convert_layout(_map_json(g), tm, name="T", layout_const="LAYOUT_T")
    assert a.blocks == b.blocks and a.border == b.border
    a.write(tmp_path / "one")
    b.write(tmp_path / "two")
    assert (tmp_path / "one" / "layouts" / "T" / "map.bin").read_bytes() == (
        tmp_path / "two" / "layouts" / "T" / "map.bin"
    ).read_bytes()


def test_append_layouts_upsert_and_sorted(tmp_path: Path) -> None:
    """append_layouts upserts by id (no dupes) and sorts; re-run is a no-op diff."""
    path = tmp_path / "layouts.json"
    e1 = {"id": "LAYOUT_B", "name": "B_Layout"}
    e2 = {"id": "LAYOUT_A", "name": "A_Layout"}
    layout_mod.append_layouts([e1, e2], path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["layouts_table_label"] == "gMapLayouts"
    assert [e["id"] for e in doc["layouts"]] == ["LAYOUT_A", "LAYOUT_B"]  # sorted
    first = path.read_text(encoding="utf-8")
    layout_mod.append_layouts([e1, e2], path)  # re-run
    assert path.read_text(encoding="utf-8") == first  # idempotent
    layout_mod.append_layouts([{"id": "LAYOUT_A", "name": "A2_Layout"}], path)  # replace
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert len(doc["layouts"]) == 2
    assert next(e for e in doc["layouts"] if e["id"] == "LAYOUT_A")["name"] == "A2_Layout"


def test_to_layouts_entry_schema() -> None:
    """The layouts.json entry matches the fork schema with fork-relative paths."""
    tm = _layout_tilemap()
    g = _grid(2, 2, [384, 385, 386, 387])
    layout = layout_mod.convert_layout(
        _map_json(g), tm, name="MokiTown_PlayersHouse_2F", layout_const="LAYOUT_MOKI_2F"
    )
    entry = layout.to_layouts_entry()
    assert entry["id"] == "LAYOUT_MOKI_2F"
    assert entry["name"] == "MokiTown_PlayersHouse_2F_Layout"
    assert entry["primary_tileset"] == "gTileset_P"
    assert entry["secondary_tileset"] == "gTileset_S"
    assert entry["blockdata_filepath"] == "data/layouts/MokiTown_PlayersHouse_2F/map.bin"
    assert entry["border_filepath"] == "data/layouts/MokiTown_PlayersHouse_2F/border.bin"
    assert entry["layout_version"] == "emerald"
    assert entry["width"] == 2 and entry["height"] == 2


_MAPS_DIR = Path("output/uranium-build/maps")
_SLICE_IDS = (49, 48, 32)  # bedroom 1F, upstairs 2F, Moki Town


def _gen_overlay_is_stale() -> bool:
    """True if tileset_map.gen.json exists but uses old single-layer tile-id keys
    (string integers like "384") rather than new column-key strings ("[[0,384]]").
    When stale, the overlay causes has_columns()=True + lookup_column() KeyError for
    every cell; skip the smoke test until S8a is re-run to regenerate it."""
    p = Path("reference/tileset_map.gen.json")
    if not p.exists():
        return False
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        for ts_tiles in d.get("tiles", {}).values():
            for k in ts_tiles:
                if not k.startswith("[["):
                    return True
    except Exception:
        pass
    return False


@pytest.mark.skipif(
    not all((_MAPS_DIR / f"Map{m:03d}.json").exists() for m in _SLICE_IDS),
    reason="slice map JSON not generated",
)
@pytest.mark.skipif(
    _gen_overlay_is_stale(),
    reason="tileset_map.gen.json is in old single-layer format; re-run S8a to regenerate",
)
@pytest.mark.parametrize("map_id", _SLICE_IDS)
def test_slice_smoke(map_id: int) -> None:
    """Each real slice map converts with zero unresolved tiles, correct byte
    length, and a sane (non-degenerate) void ratio."""
    tm = load_tile_map()
    data = json.loads((_MAPS_DIR / f"Map{map_id:03d}.json").read_text(encoding="utf-8"))
    layout = layout_mod.convert_layout(
        data, tm, name=f"Uranium_Map{map_id:03d}", layout_const=f"LAYOUT_URANIUM_MAP{map_id:03d}"
    )
    expected = data["width"] * data["height"]
    assert len(layout.blocks) == expected
    raw = struct.pack(f"<{len(layout.blocks)}H", *layout.blocks)
    assert len(raw) == expected * 2  # bytes
    void_id = tm.void(data["tileset_id"]).metatile_id
    voids = sum(1 for b in layout.blocks if b & METATILE_ID_MASK == void_id)
    assert voids / len(layout.blocks) < 0.60  # not a transposed/misread grid


_TILESETS_JSON = Path("output/uranium-build/tilesets.json")

# The 8 Moki Town cells where a shadow decal (terrain tag 20) sits above a
# passage-blocking tile — pre-fix these read PASSABLE (the shadow's own
# passage=0/priority=0 early-accepted the cell before _cell_blocked ever reached
# the blocker underneath); post-fix (the shadow/bridge terrain-tag skip) they
# correctly read BLOCKED. No prior test pinned the old (buggy) passable verdict
# for these cells — this is a new golden check, not a re-pin.
_MOKI_SHADOW_COLLISION_CELLS = [
    (33, 32), (42, 32), (45, 32), (48, 32), (51, 32), (52, 43), (55, 43), (61, 43),
]


@pytest.mark.skipif(
    not (_MAPS_DIR / "Map032.json").exists() or not _TILESETS_JSON.exists(),
    reason="Map032 slice data not generated",
)
@pytest.mark.skipif(
    _gen_overlay_is_stale(),
    reason="tileset_map.gen.json is in old single-layer format; re-run S8a to regenerate",
)
def test_real_moki_town_shadow_terrain_tag_cells_now_blocked() -> None:
    """The 8 Moki Town shadow-over-blocker cells now read BLOCKED with the real
    tilesets.json + Map032.json oracle (terrain-tag skip fix); the two control
    cells nearby are unaffected."""
    tm = load_tile_map()
    data = json.loads((_MAPS_DIR / "Map032.json").read_text(encoding="utf-8"))
    ts = data["tileset_id"]
    t = data["tiles"]
    grid = TileGrid(t["xsize"], t["ysize"], t["zsize"], t["data"])
    for x, y in _MOKI_SHADOW_COLLISION_CELLS:
        assert layout_mod._cell_blocked(grid, x, y, tm, ts), f"({x},{y}) expected BLOCKED"
    # control cells: unaffected by the terrain-tag fix
    assert layout_mod._cell_blocked(grid, 30, 32, tm, ts) is False  # passable
    assert layout_mod._cell_blocked(grid, 34, 32, tm, ts) is True  # blocked


@pytest.mark.skipif(
    not (_MAPS_DIR / "Map032.json").exists(),
    reason="Map032 slice data not generated",
)
def test_real_moki_town_through_block_cells() -> None:
    """collect_through_block_cells on the real Map032 finds exactly the 6 known
    blank-graphic/through=False obstacle cells: 3 in-field invisible obstacles
    plus 3 out-of-slice NO-EMIT door tiles that must stay walled off (nothing will
    ever warp there, so the tile must not read as open ground)."""
    data = json.loads((_MAPS_DIR / "Map032.json").read_text(encoding="utf-8"))
    cells = mw.collect_through_block_cells(data)
    assert cells == {(38, 47), (36, 18), (63, 44), (8, 43), (8, 44), (8, 45)}


# --- map_constants -----------------------------------------------------------

def test_sanitize_name() -> None:
    """Display name -> constant stem (after the MAP_ prefix), diacritics folded."""
    assert mc.sanitize_name("Rochfale Town") == "ROCHFALE_TOWN"
    assert mc.sanitize_name("Moki Town Player's House 1F") == "MOKI_TOWN_PLAYERS_HOUSE_1F"


def test_map_constants_idempotent_mint(tmp_path: Path) -> None:
    """mint(id) returns the same constants on repeat + across a save/load cycle."""
    state = tmp_path / "map_constants.json"
    reg = mc.MapConstantRegistry(state)
    a = reg.mint(92, "Rochfale Town")
    assert a is reg.mint(92, "Rochfale Town")  # repeat call is stable
    assert a.map_const == "MAP_ROCHFALE_TOWN"
    assert a.layout_const == "LAYOUT_ROCHFALE_TOWN"
    assert a.mapsec_const == "MAPSEC_ROCHFALE_TOWN"
    assert a.alias_const == "MAP_URANIUM_92"
    assert a.dir_name == "RochfaleTown"
    reg.save()
    reloaded = mc.MapConstantRegistry(state)
    reloaded.load()
    assert reloaded.get(92) == a  # persisted -> same across runs


def test_map_constants_resolve_placeholder(tmp_path: Path) -> None:
    """A MAP_URANIUM_<N> for a minted map resolves; an unknown N / non-placeholder
    fails loud."""
    reg = mc.MapConstantRegistry(tmp_path / "s.json")
    reg.mint(92, "Rochfale Town")
    assert reg.resolve_placeholder("MAP_URANIUM_92") == "MAP_ROCHFALE_TOWN"
    with pytest.raises(KeyError):
        reg.resolve_placeholder("MAP_URANIUM_999")  # not minted -> dangling warp
    with pytest.raises(ValueError):
        reg.resolve_placeholder("MAP_PETALBURG_CITY")  # not a Uranium placeholder


def test_mint_collision_fails_loud(tmp_path: Path) -> None:
    """A name clashing with vanilla or another Uranium map, or a blank name, fails
    loud (the signal to add a map_name_overrides.json entry)."""
    reg = mc.MapConstantRegistry(tmp_path / "s.json", vanilla_consts={"MAP_LITTLEROOT_TOWN"})
    with pytest.raises(ValueError):
        reg.mint(9, "Littleroot Town")  # collides with vanilla
    reg.mint(1, "Foo Town")
    with pytest.raises(ValueError):
        reg.mint(2, "Foo Town")  # collides with an already-minted Uranium map
    with pytest.raises(ValueError):
        reg.mint(3, "")  # empty stem


_ENGINE = Path("engine")


@pytest.mark.skipif(not (_ENGINE / "data" / "maps").is_dir(), reason="engine/ not vendored")
def test_load_vanilla_map_ids_pristine_matches_real_engine() -> None:
    """Reads git HEAD, not the working tree: sees a real vanilla map (never
    touched by the pipeline) but NOT a slice map that a prior real assemble
    may have injected into the working tree's generated map_groups.h (the
    2026-06-19 false-collision bug) -- data/maps/*/ is gitignored repo-root
    side, so pipeline-generated map dirs were never committed."""
    ids = mc._load_vanilla_map_ids_pristine(_ENGINE)
    assert ids is not None
    assert "MAP_LITTLEROOT_TOWN" in ids
    assert "MAP_MOKI_TOWN" not in ids


def test_load_vanilla_map_ids_pristine_none_outside_git(tmp_path: Path) -> None:
    """A fork_path with no enclosing git repo (git itself still installed) ->
    None, so `load_vanilla_map_consts` falls back to a working-tree read."""
    assert mc._load_vanilla_map_ids_pristine(tmp_path) is None


def test_load_vanilla_map_consts_falls_back_without_git(tmp_path: Path) -> None:
    """No git repo at fork_path -> `load_vanilla_map_consts` still returns the
    working-tree header's constants (`load_fork_constants` fallback), not an
    empty set."""
    header = tmp_path / mc.FORK_MAP_HEADER
    header.parent.mkdir(parents=True)
    header.write_text("#define MAP_FOO_TOWN 1\n", encoding="utf-8")
    assert mc.load_vanilla_map_consts(tmp_path) == {"MAP_FOO_TOWN"}


def test_mint_auto_disambiguate_suffixes_collisions(tmp_path: Path) -> None:
    """Walker mode: a duplicate name suffixes the INTERNAL constant/dir with the id
    (lowest id keeps the base name) while the display name is preserved."""
    reg = mc.MapConstantRegistry(tmp_path / "s.json", vanilla_consts={"MAP_LITTLEROOT_TOWN"})
    a = reg.mint(7, "Comet Cave", auto_disambiguate=True)
    b = reg.mint(10, "Comet Cave", auto_disambiguate=True)
    c = reg.mint(96, "Comet Cave", auto_disambiguate=True)
    assert a.map_const == "MAP_COMET_CAVE" and a.dir_name == "CometCave"
    assert b.map_const == "MAP_COMET_CAVE_10" and b.dir_name == "CometCave10"
    assert b.layout_const == "LAYOUT_COMET_CAVE_10"
    assert c.map_const == "MAP_COMET_CAVE_96"
    # display name is untouched (HUD/menu still read the real name)
    assert b.display_name == "Comet Cave"
    # a vanilla collision is disambiguated too, not fatal, under the flag
    v = reg.mint(9, "Littleroot Town", auto_disambiguate=True)
    assert v.map_const == "MAP_LITTLEROOT_TOWN_9"


def test_alias_header_sorted_and_complete(tmp_path: Path) -> None:
    """The alias header #defines every minted MAP_URANIUM_<N> to its canonical
    MAP_*, in id order."""
    reg = mc.MapConstantRegistry(tmp_path / "s.json")
    reg.mint(49, "Moki Town Player's House 1F")
    reg.mint(32, "Moki Town")
    reg.mint(48, "Moki Town Player's House 2F")
    header = tmp_path / "uranium_map_aliases.h"
    reg.write_alias_header(header)
    text = header.read_text(encoding="utf-8")
    assert "#define MAP_URANIUM_32 MAP_MOKI_TOWN" in text
    assert "#define MAP_URANIUM_48 MAP_MOKI_TOWN_PLAYERS_HOUSE_2F" in text
    assert "#define MAP_URANIUM_49 MAP_MOKI_TOWN_PLAYERS_HOUSE_1F" in text
    assert text.index("URANIUM_32") < text.index("URANIUM_48") < text.index("URANIUM_49")


_MAP_INFOS = Path("output/uranium-build/map_infos.json")
_OVERRIDES = Path("reference/map_name_overrides.json")


@pytest.mark.skipif(not _MAP_INFOS.exists(), reason="map_infos.json not generated")
def test_build_slice_constants(tmp_path: Path) -> None:
    """The three slice maps mint the planned readable constants from the real
    map_infos + overrides, and every slice warp placeholder resolves."""
    reg = mc.build_map_constants(
        [32, 48, 49],
        map_infos_path=_MAP_INFOS,
        overrides_path=_OVERRIDES,
        # None -> $RPG2GBA_POKEEMERALD; safe against a built engine tree
        # because load_vanilla_map_consts reads the vanilla MAP_* set from
        # git HEAD (map_constants._load_vanilla_map_ids_pristine), not the
        # working tree's generated (and possibly Uranium-contaminated)
        # map_groups.h.
        fork_path=None,
        state_path=tmp_path / "map_constants.json",
        alias_header_path=tmp_path / "aliases.h",
    )
    assert reg.get(32).map_const == "MAP_MOKI_TOWN"
    assert reg.get(49).map_const == "MAP_MOKI_TOWN_PLAYERS_HOUSE_1F"  # 1F = street door (S1)
    assert reg.get(48).map_const == "MAP_MOKI_TOWN_PLAYERS_HOUSE_2F"  # 2F = upstairs
    assert reg.get(49).dir_name == "MokiTownPlayersHouse1F"
    for n in (32, 48, 49):
        assert reg.resolve_placeholder(f"MAP_URANIUM_{n}") == reg.get(n).map_const
    # persisted state reloads identically (idempotent)
    again = mc.MapConstantRegistry(tmp_path / "map_constants.json")
    again.load()
    assert again.get(48) == reg.get(48)


def test_walker_maps_header_golden(tmp_path: Path) -> None:
    """write_walker_maps_header emits URANIUM_WALKER_MAP_COUNT + URANIUM_WALKER_MAP_LIST(X)
    with correct count, MAP_* constants in slice_map_ids order, \\-continuation on every
    X-line except the last, and id-prefixed labels that are unique (so the two
    player's-house floors don't collide), comma/quote-free, and window-sized."""
    import re

    reg = mc.MapConstantRegistry(tmp_path / "s.json")
    reg.mint(49, "Moki Town Player's House 1F")
    reg.mint(48, "Moki Town Player's House 2F")
    reg.mint(32, "Moki Town")
    out = tmp_path / "uranium_walker_maps.h"
    reg.write_walker_maps_header([49, 48, 32], out)
    text = out.read_text(encoding="utf-8")

    # count macro present
    assert "#define URANIUM_WALKER_MAP_COUNT 3" in text
    # list macro header line has continuation backslash
    assert "#define URANIUM_WALKER_MAP_LIST(X) \\" in text
    # generated header marker
    assert "GENERATED by rpg2gba assembler from SLICE_MAP_IDS" in text

    # three X-lines in SLICE_MAP_IDS order
    lines = text.splitlines()
    x_lines = [ln for ln in lines if "X(MAP_" in ln]
    assert len(x_lines) == 3
    assert "MAP_MOKI_TOWN_PLAYERS_HOUSE_1F" in x_lines[0]
    assert "MAP_MOKI_TOWN_PLAYERS_HOUSE_2F" in x_lines[1]
    # MAP_MOKI_TOWN without the 1F/2F suffix (the plain town entry is last)
    assert re.search(r"X\(MAP_MOKI_TOWN,", x_lines[2])

    # first two X-lines have backslash continuation; last does not
    assert x_lines[0].rstrip().endswith("\\")
    assert x_lines[1].rstrip().endswith("\\")
    assert not x_lines[2].rstrip().endswith("\\")

    # labels: id-prefixed, unique, comma/quote-free, window-sized
    labels = [m.group(1) for m in re.finditer(r'COMPOUND_STRING\("([^"]*)"\)', text)]
    assert len(labels) == 3
    assert len(set(labels)) == 3, f"labels collide: {labels!r}"
    for label, uid in zip(labels, [49, 48, 32]):
        assert label.startswith(f"{uid} "), f"label {label!r} not prefixed by id {uid}"
        assert len(label) <= 28, f"label {label!r} exceeds 28 chars"
        assert "," not in label
        assert '"' not in label

    # idempotent: a second write produces byte-identical output
    reg.write_walker_maps_header([49, 48, 32], out)
    assert out.read_text(encoding="utf-8") == text


def test_alias_const_format_is_valid_identifier() -> None:
    """The Q2 alias spelling yields a valid C identifier (no skip — pure)."""
    name = mc.ALIAS_CONST_FMT.format(n=42)
    assert name.replace("_", "").isalnum() and name[0].isalpha()
    assert name == "MAP_URANIUM_42"


# --- 5.3 metadata_wiring -----------------------------------------------------

def _page(
    trigger: int = 0,
    cond: dict | None = None,
    cmds: list | None = None,
    name: str = "",
    opacity: int = 255,
    direction: int = 2,
    move_type: int = 0,
    through: bool = False,
    direction_fix: bool = False,
) -> dict:
    return {
        "trigger": trigger,
        "condition": cond or {},
        "graphic": {"character_name": name, "opacity": opacity, "direction": direction},
        "move_type": move_type,
        "list": cmds or [],
        "through": through,
        "direction_fix": direction_fix,  # required by route_sim.simulate_route
    }


def _event(eid: int, x: int, y: int, pages: list[dict], name: str | None = None) -> dict:
    return {
        "id": eid, "name": name if name is not None else f"E{eid}",
        "x": x, "y": y, "pages": pages,
    }


def _self_cond(letter: str) -> dict:
    return {"self_switch_valid": True, "self_switch_ch": letter}


def _sw_cond(switch_id: int) -> dict:
    return {"switch1_valid": True, "switch1_id": switch_id}


def _transfer(dest_uid: int, x: int, y: int, direction: int | None = 2) -> dict:
    """A code-201 Transfer Player command. `direction=None` produces a
    too-short parameter list (no index 4) — the "malformed/legacy event" case
    `_event_transfers` must distinguish from an explicit dir=0."""
    params = [0, dest_uid, x, y]
    if direction is not None:
        params += [direction, 1]  # dir, fade
    return {"code": 201, "indent": 0, "parameters": params}


def _npc_gfx_fixture() -> dict[str, str]:
    """A minimal character_name -> OBJ_EVENT_GFX_* fixture (mirrors the shape
    `npc_gfx.load_npc_gfx_map` returns; see tests/test_npc_gfx.py for the loader
    itself)."""
    return {
        "HGSS_000": "OBJ_EVENT_GFX_URANIUM_HGSS_000",
        "HGSS_005": "OBJ_EVENT_GFX_URANIUM_HGSS_005",
        "HGSS_017": "OBJ_EVENT_GFX_URANIUM_HGSS_017",  # Map032 EV012, route_sim regression
        "PU-Chyinmunk": "OBJ_EVENT_GFX_URANIUM_PU_CHYINMUNK",  # Map032 EV008
        "PU-doors1": "OBJ_EVENT_GFX_URANIUM_PU_DOORS1",  # never looked up (door sheets drop)
    }


_SLICE = {32, 48, 49}


def test_classify_event() -> None:
    """The generic rule reproduces the S1 keep-list from trigger + target-in-slice."""
    # plain NPC -> object
    npc = _event(1, 4, 4, [_page()])
    assert mw.classify_event(npc, _SLICE)[0] == "object"
    # player-touch door to an in-slice map -> warp
    door = _event(2, 10, 11, [_page(trigger=1, cmds=[_transfer(32, 28, 31)])])
    kind, spec = mw.classify_event(door, _SLICE)
    assert kind == "warp" and spec.dest_uid == 32 and (spec.src_x, spec.src_y) == (10, 11)
    # door to an out-of-slice map -> skip (NO-EMIT)
    out = _event(3, 17, 11, [_page(trigger=1, cmds=[_transfer(50, 14, 18)])])
    assert mw.classify_event(out, _SLICE)[0] == "skip"
    # scripted story transfer (action trigger) to in-slice -> object (keeps its .pory warp)
    letter = _event(21, 5, 8, [_page(trigger=0, cmds=[_transfer(48, 4, 6)])])
    assert mw.classify_event(letter, _SLICE)[0] == "object"


def test_classify_event_gated_door_is_not_a_warp() -> None:
    """A player-touch door whose OTHER player-touch pages don't transfer is a
    GATED door and must stay an event — collapsing it into an unconditional
    warp_event silently discards the refusal pages.

    Uranium Map049 EV002's shape: page 0 (no condition) refuses with "I'd better
    say goodbye to Auntie first.", page 1 transfers once switch 52 (`Mum`) is
    set. Collapsing it let the player leave the starting house before the gate —
    playtest beat B2. See reference/findings/gated_door_collapse_2026-07-26.md.
    """
    gated = _event(2, 10, 11, [
        _page(trigger=1, cmds=[{"code": 101, "indent": 0, "parameters": ["nope"]}]),
        _page(trigger=1, cond=_sw_cond(52), cmds=[_transfer(32, 28, 31)]),
    ])
    assert mw.classify_event(gated, _SLICE) == ("object", None)


def test_classify_event_all_touch_pages_transfer_is_still_a_warp() -> None:
    """The narrow rule: when every player-touch page transfers, the collapse to
    a single warp_event is still correct (multi-page ungated door)."""
    door = _event(2, 10, 11, [
        _page(trigger=1, cmds=[_transfer(32, 28, 31)]),
        _page(trigger=1, cond=_sw_cond(52), cmds=[_transfer(32, 28, 31)]),
    ])
    kind, spec = mw.classify_event(door, _SLICE)
    assert kind == "warp" and (spec.src_x, spec.src_y) == (10, 11)


def test_classify_event_autorun_page_does_not_gate_the_door() -> None:
    """Only PLAYER-TOUCH pages compete for the step-on behavior. An autorun
    (trigger 3) page reaches the player through ON_FRAME_TABLE instead, so it
    must not turn a door into a gated door.

    This is Moki Town's five house doors (Map032 EV003/5/6/7/17): a
    touch-triggered transfer page plus a switch-22 autorun cutscene page. They
    stay plain warps."""
    door = _event(5, 28, 31, [
        _page(trigger=1, cmds=[_transfer(49, 10, 9)]),
        _page(trigger=3, cond=_sw_cond(22), cmds=[
            {"code": 111, "indent": 0, "parameters": []},
        ]),
    ])
    kind, spec = mw.classify_event(door, _SLICE)
    assert kind == "warp" and spec.dest_uid == 49


def test_event_transfers_dest_dir_carried_through() -> None:
    """_event_transfers / classify_event carry parameters[4] (dir) through into
    the resulting WarpSpec.dest_dir, for every non-default direction value."""
    for direction in (2, 4, 6, 8):
        door = _event(2, 10, 11, [_page(trigger=1, cmds=[_transfer(32, 28, 31, direction)])])
        assert mw._event_transfers(door) == [(32, 28, 31, direction)]
        kind, spec = mw.classify_event(door, _SLICE)
        assert kind == "warp"
        assert spec.dest_dir == direction


def test_event_transfers_short_param_list_dest_dir_none() -> None:
    """A code-201 command too short to carry index 4 (a malformed/legacy event)
    yields dest_dir is None — NOT 0 (0 is a real, distinct "retain facing" value)."""
    door = _event(2, 10, 11, [_page(trigger=1, cmds=[_transfer(32, 28, 31, direction=None)])])
    assert mw._event_transfers(door) == [(32, 28, 31, None)]
    kind, spec = mw.classify_event(door, _SLICE)
    assert kind == "warp"
    assert spec.dest_dir is None


# --- fix #3: through=False blank-graphic obstacle blocking --------------------

def test_collect_through_block_cells_blank_and_through_false_any_trigger() -> None:
    """A blank-graphic, through=False boot page is collected regardless of
    trigger (action/touch/autorun/parallel all qualify — an invisible solid
    obstacle blocks the tile no matter what its script does)."""
    map_json = {
        "map_id": 1,
        "events": [
            _event(1, 4, 4, [_page(trigger=0, through=False)]),  # action
            _event(2, 5, 5, [_page(trigger=1, through=False)]),  # player-touch
            _event(3, 6, 6, [_page(trigger=3, through=False)]),  # autorun
            _event(4, 7, 7, [_page(trigger=4, through=False)]),  # parallel
        ],
    }
    assert mw.collect_through_block_cells(map_json) == {(4, 4), (5, 5), (6, 6), (7, 7)}


def test_collect_through_block_cells_through_true_not_collected() -> None:
    """through=True (the event is a pass-through decal, e.g. a floor sign) is
    never a blocking cell, blank graphic or not."""
    map_json = {
        "map_id": 1,
        "events": [_event(1, 4, 4, [_page(trigger=0, through=True)])],
    }
    assert mw.collect_through_block_cells(map_json) == set()


def test_collect_through_block_cells_graphic_bearing_event_not_collected() -> None:
    """An event with a real graphic is excluded even if through=False — pokeemerald's
    native object_event collision already blocks that tile (it becomes a real
    object_event via build_object_events, not a phantom blocked_cells entry)."""
    map_json = {
        "map_id": 1,
        "events": [_event(1, 4, 4, [_page(trigger=0, through=False, name="HGSS_000")])],
    }
    assert mw.collect_through_block_cells(map_json) == set()


def test_collect_through_block_cells_no_boot_page_contributes_nothing() -> None:
    """An event with no boot-active page (every page gated off at boot) doesn't
    contribute a cell — same boot-page selection build_object_events uses."""
    map_json = {
        "map_id": 1,
        "events": [_event(1, 4, 4, [_page(cond=_sw_cond(1), through=False)])],
    }
    assert mw.collect_through_block_cells(map_json) == set()


def test_build_object_events_placed_at_coords() -> None:
    """Each visible non-warp event -> one object_event at its (x, y) with its
    npc_gfx-mapped graphic and boot-page movement type; single-page -> a page
    label, self-switch multi-page -> a dispatcher label; local_id_map is the
    1-based object_events position keyed by (string) RMXP event id."""
    consts = mc.MapConstantRegistry(Path("x")).mint(49, "Moki Town Player's House 1F")
    map_json = {
        "map_id": 49,
        "events": [
            _event(1, 4, 4, [_page(name="HGSS_000")]),  # single page
            _event(7, 9, 3, [  # self-switch -> dispatcher
                _page(name="HGSS_005"), _page(cond=_self_cond("A"), name="HGSS_005"),
            ]),
            _event(2, 10, 11, [_page(trigger=1, cmds=[_transfer(32, 28, 31)])]),  # warp, excluded
        ],
    }
    result = mw.build_object_events(map_json, consts, _SLICE, npc_gfx=_npc_gfx_fixture())
    assert len(result.object_events) == 2  # the warp door is not an object_event
    by_xy = {(o.x, o.y): o for o in result.object_events}
    assert by_xy[(4, 4)].script == "Map049_EV001_Page1"
    assert by_xy[(4, 4)].graphics_id == "OBJ_EVENT_GFX_URANIUM_HGSS_000"
    assert by_xy[(4, 4)].movement_type == "MOVEMENT_TYPE_FACE_DOWN"  # direction=2 default
    assert by_xy[(9, 3)].script == "Map049_EV007_Dispatch"
    assert len(result.dispatchers) == 1
    assert result.local_id_map == {"1": 1, "7": 2}
    assert result.drops == []


def test_build_object_events_stubs_bodyless_event() -> None:
    """With pory_labels (post-S6), an event S6 left bodyless — a command-less
    standing NPC — is wired as a static object (script "0x0"), not a dangling page
    label; an event with a converted body keeps its page label."""
    consts = mc.MapConstantRegistry(Path("x")).mint(49, "Moki Town Player's House 1F")
    map_json = {
        "map_id": 49,
        "events": [
            _event(1, 4, 4, [_page(name="HGSS_000")]),   # converted -> has a body
            _event(19, 6, 6, [_page(name="HGSS_000")]),  # command-less NPC -> no body
        ],
    }
    labels = {"Map049_EV001_Page1"}  # only EV001 was converted
    result = mw.build_object_events(
        map_json, consts, _SLICE, pory_labels=labels, npc_gfx=_npc_gfx_fixture()
    )
    by_xy = {(o.x, o.y): o for o in result.object_events}
    assert by_xy[(4, 4)].script == "Map049_EV001_Page1"
    assert by_xy[(6, 6)].script == mw.NO_SCRIPT  # static object, no dangling ref
    assert result.dispatchers == []


def test_build_object_events_blank_graphic_bg_and_coord() -> None:
    """A blank-graphic boot page becomes a bg sign (action trigger) or a coord
    trigger (event-touch trigger); both point at the same label an object_event
    for that event would have gotten. Neither shows up in object_events/
    local_id_map (they aren't objects)."""
    consts = mc.MapConstantRegistry(Path("x")).mint(49, "Moki Town Player's House 1F")
    map_json = {
        "map_id": 49,
        "events": [
            _event(1, 4, 4, [_page(trigger=0)]),  # blank + action -> sign
            _event(2, 5, 5, [_page(trigger=2)]),  # blank + event-touch -> coord trigger
        ],
    }
    result = mw.build_object_events(map_json, consts, _SLICE)
    assert result.object_events == [] and result.local_id_map == {}
    assert [b.to_dict()["type"] for b in result.bg_events] == ["sign"]
    assert (result.bg_events[0].x, result.bg_events[0].y) == (4, 4)
    assert result.bg_events[0].script == "Map049_EV001_Page1"
    assert [c.to_dict()["type"] for c in result.coord_events] == ["trigger"]
    assert (result.coord_events[0].x, result.coord_events[0].y) == (5, 5)
    assert result.coord_events[0].script == "Map049_EV002_Page1"


def test_build_object_events_opacity0_touch_keeps_coord_event() -> None:
    """A visible-named but opacity-0 boot page on an event-touch trigger (the
    Map032 EV9/EV74 invisible script-host pattern) becomes a coord trigger, not a
    dropped or placed object — its script MUST stay referenced."""
    consts = mc.MapConstantRegistry(Path("x")).mint(49, "Moki Town Player's House 1F")
    map_json = {
        "map_id": 49,
        "events": [_event(9, 16, 42, [_page(trigger=2, name="HGSS_014", opacity=0)])],
    }
    result = mw.build_object_events(map_json, consts, _SLICE)
    assert result.object_events == []
    assert len(result.coord_events) == 1
    assert result.coord_events[0].script == "Map049_EV009_Page1"
    assert result.drops == []


def test_coord_event_gate_is_var_temp_f_not_temp_0() -> None:
    """findings §3.1 BUG A: VAR_TEMP_0 is the transpiler's generic getplayerxy
    scratch register, so a second coord event on the same map would never
    fire once the first wrote to it. The gate must be a var the transpiler
    never writes (VAR_TEMP_F, reserved) — every CoordEvent this module
    produces shares that gate."""
    assert mw._COORD_GATE_VAR == "VAR_TEMP_F"
    ce = mw.CoordEvent(x=1, y=1, script="Some_Script")
    assert ce.var == "VAR_TEMP_F"
    assert ce.var_value == "0"
    assert ce.to_dict()["var"] == "VAR_TEMP_F"

    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    map_json = {
        "map_id": 32,
        "events": [
            _event(9, 16, 42, [_page(trigger=2)]),
            _event(74, 26, 12, [_page(trigger=2)]),
        ],
    }
    result = mw.build_object_events(map_json, consts, _SLICE)
    assert len(result.coord_events) == 2
    assert all(c.var == "VAR_TEMP_F" for c in result.coord_events)


def test_build_object_events_coord_standable_unchanged() -> None:
    """A touch-trigger event on a standable tile is unaffected by passing
    `passability` — one coord event at its own coords, same as with
    `passability=None` (regression: the relocation gate must be a no-op for
    the common case)."""
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    map_json = {"map_id": 32, "events": [_event(74, 1, 1, [_page(trigger=2)])]}
    passability = _passability_fixture(3, 3, blocked_cells=set())
    result = mw.build_object_events(
        map_json, consts, _SLICE, passability=passability,
    )
    assert len(result.coord_events) == 1
    assert (result.coord_events[0].x, result.coord_events[0].y) == (1, 1)
    assert result.coord_events[0].script == "Map032_EV074_Page1"


def test_build_object_events_coord_blocked_relocates_to_standable_neighbors() -> None:
    """CLAUDE-mandated fix: RMXP touch triggers fire on a BUMP (walking into a
    blocked tile), but pokeemerald coord_events only fire when the player
    STANDS on the tile. An event sitting on a blocked tile (the Map032 EV074
    shape: horizontal neighbors sealed, vertical neighbors open) must relocate
    its coord event to every standable orthogonal neighbor instead of emitting
    a dead trigger at its own (unreachable) coords."""
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    map_json = {"map_id": 32, "events": [_event(74, 1, 1, [_page(trigger=2)])]}
    passability = _passability_fixture(3, 3, blocked_cells={(1, 1), (0, 1), (2, 1)})
    result = mw.build_object_events(
        map_json, consts, _SLICE, passability=passability,
    )
    by_xy = {(c.x, c.y): c for c in result.coord_events}
    assert set(by_xy) == {(1, 0), (1, 2)}
    assert (1, 1) not in by_xy
    assert all(c.script == "Map032_EV074_Page1" for c in by_xy.values())


def test_build_object_events_coord_blocked_no_standable_neighbor_raises() -> None:
    """Zero standable orthogonal neighbors -> fail loud (CLAUDE.md §4.5), not a
    silently dropped trigger."""
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    map_json = {"map_id": 32, "events": [_event(74, 1, 1, [_page(trigger=2)])]}
    passability = _passability_fixture(
        3, 3, blocked_cells={(1, 1), (0, 1), (2, 1), (1, 0), (1, 2)}
    )
    with pytest.raises(ValueError, match="EV074"):
        mw.build_object_events(map_json, consts, _SLICE, passability=passability)


def test_build_object_events_coord_no_passability_keeps_legacy_behavior() -> None:
    """Legacy callers that don't pass `passability` (e.g. `passability=None`)
    keep today's behavior unchanged: one coord event at the event's own
    coords, even where the tile would in fact be blocked."""
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    map_json = {"map_id": 32, "events": [_event(74, 1, 1, [_page(trigger=2)])]}
    result = mw.build_object_events(map_json, consts, _SLICE)
    assert len(result.coord_events) == 1
    assert (result.coord_events[0].x, result.coord_events[0].y) == (1, 1)


# --- Trainer(N) sight-ray tripwires ------------------------------------------

def test_trainer_sight_ray_through_true_all_clear() -> None:
    """Trainer(3) facing down, through=True, all-clear map -> exactly the 3
    tiles below the event; the event's own tile is never included."""
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    map_json = {
        "map_id": 32,
        "events": [
            _event(74, 5, 5, [_page(trigger=2, through=True, direction=2)], name="Trainer(3)")
        ],
    }
    passability = _passability_fixture(20, 20, blocked_cells=set())
    result = mw.build_object_events(map_json, consts, _SLICE, passability=passability)
    by_xy = {(c.x, c.y) for c in result.coord_events}
    assert by_xy == {(5, 6), (5, 7), (5, 8)}
    assert (5, 5) not in by_xy


def test_trainer_sight_ray_ev074_fence_shape() -> None:
    """Map032 EV074 shape: Trainer(5) parked on a blocked fence tile, facing
    down, through=True, all 5 tiles below standable -> the full 5-tile ray
    below, nothing on the wrong (north) side of the fence, and no ValueError
    from the bump-trigger relocation path (the ray path bypasses it)."""
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    map_json = {
        "map_id": 32,
        "events": [
            _event(74, 26, 12, [_page(trigger=2, through=True, direction=2)], name="Trainer(5)")
        ],
    }
    passability = _passability_fixture(40, 40, blocked_cells={(26, 12)})
    result = mw.build_object_events(map_json, consts, _SLICE, passability=passability)
    by_xy = {(c.x, c.y) for c in result.coord_events}
    assert by_xy == {(26, 13), (26, 14), (26, 15), (26, 16), (26, 17)}
    assert (26, 11) not in by_xy  # wrong side of the fence
    assert (26, 12) not in by_xy  # the event's own (blocked) tile


def test_trainer_sight_ray_through_true_mid_ray_blocked_skipped() -> None:
    """through=True never clips the LOS walk -- a blocked tile mid-ray is
    simply filtered out by the standable check, and farther standable tiles
    past it are still emitted."""
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    map_json = {
        "map_id": 32,
        "events": [
            _event(74, 2, 2, [_page(trigger=2, through=True, direction=2)], name="Trainer(4)")
        ],
    }
    passability = _passability_fixture(20, 20, blocked_cells={(2, 4)})  # distance-2 tile
    result = mw.build_object_events(map_json, consts, _SLICE, passability=passability)
    by_xy = {(c.x, c.y) for c in result.coord_events}
    assert by_xy == {(2, 3), (2, 5), (2, 6)}
    assert (2, 4) not in by_xy


def test_trainer_sight_ray_through_false_sealed_exit_stops_at_distance_one() -> None:
    """through=False with the event's own tile sealed in its facing direction
    -> only the distance-1 tile is live (Essentials' pbEventCanReachPlayer?
    cumulative-step clip)."""
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    map_json = {
        "map_id": 32,
        "events": [
            _event(74, 4, 4, [_page(trigger=2, through=False, direction=2)], name="Trainer(3)")
        ],
    }
    passability = _passability_fixture(20, 20, blocked_cells={(4, 4)})  # event's own tile sealed
    result = mw.build_object_events(map_json, consts, _SLICE, passability=passability)
    by_xy = {(c.x, c.y) for c in result.coord_events}
    assert by_xy == {(4, 5)}


def test_trainer_sight_ray_visible_raises() -> None:
    """A visible (opacity 255, real graphic) Trainer(N) on a trigger-2 page is
    a battle trainer, not a tripwire -- fail loud naming the native
    trainer-object path rather than silently mis-converting it."""
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    map_json = {
        "map_id": 32,
        "events": [
            _event(
                9, 10, 10,
                [_page(trigger=2, name="HGSS_000", opacity=255, direction=2)],
                name="Trainer(4)",
            )
        ],
    }
    with pytest.raises(ValueError, match="native trainer-object"):
        mw.build_object_events(map_json, consts, _SLICE, npc_gfx=_npc_gfx_fixture())


def test_trainer_sight_ray_name_inert_when_trigger_not_touch() -> None:
    """Trainer(N) on a trigger-0 (action) page is inert -- Essentials' own
    check requires trigger==2 -- so it's classified as an ordinary object,
    no raise."""
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    map_json = {
        "map_id": 32,
        "events": [
            _event(
                9, 10, 10,
                [_page(trigger=0, name="HGSS_000", opacity=255, direction=2)],
                name="Trainer(4)",
            )
        ],
    }
    result = mw.build_object_events(map_json, consts, _SLICE, npc_gfx=_npc_gfx_fixture())
    assert len(result.object_events) == 1
    assert result.drops == []


def test_trainer_sight_ray_entirely_unstandable_raises() -> None:
    """Every ray tile blocked -> fail loud naming the event (a tripwire that
    can never fire is a conversion bug, not a silent drop)."""
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    map_json = {
        "map_id": 32,
        "events": [
            _event(74, 2, 2, [_page(trigger=2, through=True, direction=2)], name="Trainer(2)")
        ],
    }
    passability = _passability_fixture(20, 20, blocked_cells={(2, 3), (2, 4)})
    with pytest.raises(ValueError, match="EV074"):
        mw.build_object_events(map_json, consts, _SLICE, passability=passability)


def test_trainer_sight_ray_facing_left() -> None:
    """Facing variety: direction=4 (left) produces a westward ray."""
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    map_json = {
        "map_id": 32,
        "events": [
            _event(74, 10, 10, [_page(trigger=2, through=True, direction=4)], name="Trainer(3)")
        ],
    }
    passability = _passability_fixture(20, 20, blocked_cells=set())
    result = mw.build_object_events(map_json, consts, _SLICE, passability=passability)
    by_xy = {(c.x, c.y) for c in result.coord_events}
    assert by_xy == {(9, 10), (8, 10), (7, 10)}


def test_trainer_sight_ray_no_boot_page_still_emits() -> None:
    """A Trainer(N) trigger-2 invisible event whose only page is story-gated
    (switch-valid condition -> select_boot_page yields None, e.g. Map032
    EV078/EV080) still emits its ray: the tripwire is invisible and its
    dispatcher gates the body at runtime, so boot-inactivity doesn't matter."""
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    map_json = {
        "map_id": 32,
        "events": [
            _event(
                78, 27, 42,
                [_page(trigger=2, through=True, direction=2, cond=_sw_cond(55))],
                name="Trainer(6)",
            )
        ],
    }
    passability = _passability_fixture(50, 50, blocked_cells=set())
    result = mw.build_object_events(map_json, consts, _SLICE, passability=passability)
    by_xy = {(c.x, c.y) for c in result.coord_events}
    assert by_xy == {(27, 43), (27, 44), (27, 45), (27, 46), (27, 47), (27, 48)}
    assert result.drops == []


def test_no_boot_page_non_trainer_still_drops() -> None:
    """Regression guard: a NON-Trainer event with no boot-active page still
    drops with DROP_NO_BOOT_PAGE -- the tripwire carve-out is scoped to
    Trainer(N)-named events only."""
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    map_json = {
        "map_id": 32,
        "events": [
            _event(78, 27, 42, [_page(trigger=2, through=True, cond=_sw_cond(55))])
        ],
    }
    result = mw.build_object_events(map_json, consts, _SLICE)
    assert result.object_events == []
    assert result.coord_events == []
    assert result.drops == [(78, mw.DROP_NO_BOOT_PAGE)]


def _moving_page(route_codes: list[int], name: str = "HGSS_000", frequency: int = 3) -> dict:
    """A visible move_type-3 boot page with a repeating custom route."""
    page = _page(name=name, move_type=3)
    page["move_frequency"] = frequency
    page["move_route"] = {
        "repeat": True,
        "skippable": False,
        "list": [{"code": c, "parameters": []} for c in route_codes]
        + [{"code": 0, "parameters": []}],
    }
    return page


def _passability_fixture(
    width: int, height: int, blocked_cells: set[tuple[int, int]] = frozenset(),
    open_cells: set[tuple[int, int]] = frozenset(),
) -> "npc_gfx_mod.MapPassability":
    """All-clear ground with passage-15 z1 decorations at `blocked_cells`."""
    layer0 = [1] * (width * height)
    layer1 = [0] * (width * height)
    for (x, y) in blocked_cells:
        layer1[y * width + x] = 2
    map_json = {
        "tiles": {
            "xsize": width, "ysize": height, "zsize": 3,
            "data": layer0 + layer1 + [0] * (width * height),
        }
    }
    return npc_gfx_mod.MapPassability.from_map(
        map_json, {"passages": [0, 0, 15], "priorities": [0, 0, 0]},
        open_cells=open_cells,
    )


def test_build_object_events_spawn_locked_demotes_to_static() -> None:
    """A pacer spawned on a fully exit-blocked tile (Map032 EV012 on its
    passage-15 decoration) never moves on PC — interpreter-first sends its
    cardinal route through CUSTOM_ROUTE, but full spawn-lock STILL demotes it
    to a static facing (and drops the route: no route_id spent, no forced
    DIR_SOUTH from the interpreter) instead of letting it walk off and strand."""
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    map_json = {
        "map_id": 32,
        "events": [_event(12, 1, 0, [_moving_page([2, 2, 3, 3])])],
    }
    passability = _passability_fixture(4, 1, blocked_cells={(1, 0)})
    result = mw.build_object_events(
        map_json, consts, _SLICE, npc_gfx=_npc_gfx_fixture(), passability=passability,
        route_registry=RouteRegistry(),
    )
    (obj,) = result.object_events
    assert obj.movement_type.startswith("MOVEMENT_TYPE_FACE_")
    assert obj.route_id == "0"
    assert (obj.movement_range_x, obj.movement_range_y) == (0, 0)


def test_build_object_events_walk_sequence_blocked_path_demotes() -> None:
    """Map032 EV073's shape: spawn is open, but the route's FIRST move walks
    into a sealed cell. RMXP turns before it checks passability and a
    non-skippable route stalls on a blocked move forever, so this NPC never
    moves on PC — it is a statue facing west. Demote to FACE_LEFT and drop
    the route id.

    This test previously asserted the opposite (CUSTOM_ROUTE kept, route id
    assigned) on the rationale that "the engine interpreter skips blocked
    steps at runtime". That skip was itself the bug: the interpreter advanced
    its PC before checking collision, so a blocked step burned an opcode and
    desynced the route. Both halves are fixed now — the spawn-only
    `exit_blocked` gate became a real route simulation, and the interpreter
    checks collision before committing the PC — so the old expectation
    encoded behavior that no longer exists. Its real-data sibling,
    `test_real_moki_town_ev073_open_spawn_first_step_blocked_demotes`, pins
    the same NPC to the same verdict against the actual map."""
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    loop = [2, 4, 4, 1, 1, 3]  # left, up x2, down x2, right
    map_json = {"map_id": 32, "events": [_event(73, 1, 2, [_moving_page(loop)])]}
    blocked = _passability_fixture(4, 3, blocked_cells={(0, 2)})  # the left cell
    registry = RouteRegistry()
    result = mw.build_object_events(
        map_json, consts, _SLICE, npc_gfx=_npc_gfx_fixture(), passability=blocked,
        route_registry=registry,
    )
    obj = result.object_events[0]
    assert obj.movement_type == "MOVEMENT_TYPE_FACE_LEFT"
    assert obj.route_id == "0"
    assert len(registry) == 0


_MAP032_JSON = _MAPS_DIR / "Map032.json"


def _load_map032() -> dict:
    """The full real Map032 (Moki Town) map JSON — tiles + events — backing the
    route_sim regression pins below."""
    return json.loads(_MAP032_JSON.read_text(encoding="utf-8"))


def _real_map032_passability(data: dict) -> "npc_gfx_mod.MapPassability":
    """The real Moki Town tile-passability oracle: the actual tilesets.json
    passage/priority bytes for Map032's tileset, not a synthetic stand-in —
    this is what pins the tests below to real map data rather than a
    hand-picked scenario."""
    tilesets = json.loads(_TILESETS_JSON.read_text(encoding="utf-8"))
    tileset = tilesets[str(data["tileset_id"])]
    return npc_gfx_mod.MapPassability.from_map(data, tileset)


def _real_map032_event(data: dict, event_id: int) -> dict:
    return next(e for e in data["events"] if e["id"] == event_id)


_MAP032_SKIP = pytest.mark.skipif(
    not _MAP032_JSON.exists() or not _TILESETS_JSON.exists(),
    reason="Map032 slice data / tilesets.json not generated",
)


@_MAP032_SKIP
def test_real_moki_town_ev012_spawn_sealed_demotes_facing_west() -> None:
    """Map032 EV012 (31,44), sheet HGSS_017: the spawn tile carries a layer-1
    decoration (tile 413, passage 0x0F) sealed in all four directions. Its
    route [2,2,2,3,3,3,0] (move_left x3, move_right x3, skippable=false,
    direction_fix=false, boot facing DOWN) executes move_left first: per RMXP
    `Game_Character#move_left`, the character turns west BEFORE passability is
    checked, and — since the spawn tile itself blocks leaving in every
    direction — the destination is unreachable, so the very first step never
    completes and the NPC stalls facing west forever (the west-exit woman at
    Moki Town's edge). Expected MOVEMENT_TYPE_FACE_LEFT — NOT FACE_DOWN, which
    is what the pre-fix code emitted by reading `graphic.direction=2` off the
    boot page instead of simulating the route — and NOT a live route
    (route_id "0": she never moves on PC, so no route id should be spent)."""
    data = _load_map032()
    passability = _real_map032_passability(data)
    event = _real_map032_event(data, 12)
    map_json = {"map_id": 32, "events": [event]}
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    result = mw.build_object_events(
        map_json, consts, _SLICE, npc_gfx=_npc_gfx_fixture(), passability=passability,
        route_registry=RouteRegistry(),
    )
    (obj,) = result.object_events
    assert obj.movement_type == "MOVEMENT_TYPE_FACE_LEFT"
    assert obj.route_id == "0"


@_MAP032_SKIP
def test_real_moki_town_ev073_open_spawn_first_step_blocked_demotes() -> None:
    """Map032 EV073 (32,49), sheet HGSS_005: the spawn tile itself is OPEN, so
    the OLD gate (`MapPassability.exit_blocked` on the spawn tile alone) let
    her through as a live custom route and she walked on PC. Her first move
    is move_left onto (31,49), which carries hedge tiles (1119/1094, passage
    0x0F) — RMXP turns west, then finds the destination blocked, so the first
    route command never completes and she stalls immediately, having never
    moved. This is exactly the coverage gap `simulate_route` closes: the
    blocking cell is the route's first destination, not the spawn tile.
    Expected MOVEMENT_TYPE_FACE_LEFT and no route id spent (route_id "0")."""
    data = _load_map032()
    passability = _real_map032_passability(data)
    event = _real_map032_event(data, 73)
    map_json = {"map_id": 32, "events": [event]}
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    result = mw.build_object_events(
        map_json, consts, _SLICE, npc_gfx=_npc_gfx_fixture(), passability=passability,
        route_registry=RouteRegistry(),
    )
    (obj,) = result.object_events
    assert obj.movement_type == "MOVEMENT_TYPE_FACE_LEFT"
    assert obj.route_id == "0"


@_MAP032_SKIP
def test_real_moki_town_ev008_genuinely_mobile_keeps_custom_route() -> None:
    """Map032 EV008, the Chyinmunk: a long cardinal route
    ([1x5, 3x6, 4x6, 2, 2, 37, 2, 2, 38, 2, 2, 1, 0]) whose blocked legs are
    wrapped in through_on(37)/through_off(38) toggles, so per RMXP it is
    genuinely mobile end to end and never permanently stalls. `simulate_route`
    must NOT over-demote it just because it shares the cardinal-route shape
    with EV012/EV073 above — this guards against the fix regressing a real
    mover into a statue. Expected MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE with its
    route id intact (non-zero)."""
    data = _load_map032()
    passability = _real_map032_passability(data)
    event = _real_map032_event(data, 8)
    map_json = {"map_id": 32, "events": [event]}
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    registry = RouteRegistry()
    result = mw.build_object_events(
        map_json, consts, _SLICE, npc_gfx=_npc_gfx_fixture(), passability=passability,
        route_registry=registry,
    )
    (obj,) = result.object_events
    assert obj.movement_type == mw.MOVEMENT_TYPE_CUSTOM_ROUTE
    assert obj.route_id != "0"


def test_build_object_events_anchor_shift_applied_to_placement() -> None:
    """A cardinal move_route is interpreter-first (CUSTOM_ROUTE), so the old
    native WALK_SEQUENCE anchor-shift logic no longer applies: the object is
    placed at its raw spawn coords, unshifted, with an assigned route id."""
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    # 3x4 ring whose spawn sits one tile below the top-left corner (EV008 shape)
    ring = [1] * 2 + [3] * 2 + [4] * 3 + [2] * 2 + [1]
    map_json = {"map_id": 32, "events": [_event(8, 1, 2, [_moving_page(ring, frequency=6)])]}
    result = mw.build_object_events(
        map_json, consts, _SLICE, npc_gfx=_npc_gfx_fixture(), route_registry=RouteRegistry()
    )
    (obj,) = result.object_events
    assert obj.movement_type == mw.MOVEMENT_TYPE_CUSTOM_ROUTE
    assert (obj.x, obj.y) == (1, 2)  # raw spawn coords, no anchor shift
    assert obj.route_id != "0"


def test_build_object_events_custom_route_assigns_route_id() -> None:
    """A single encodable custom route gets route_id "1" and the shared
    registry has exactly one entry."""
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    map_json = {"map_id": 32, "events": [_event(1, 1, 1, [_moving_page([2, 2, 3, 3])])]}
    registry = RouteRegistry()
    result = mw.build_object_events(
        map_json, consts, _SLICE, npc_gfx=_npc_gfx_fixture(), route_registry=registry
    )
    (obj,) = result.object_events
    assert obj.movement_type == mw.MOVEMENT_TYPE_CUSTOM_ROUTE
    assert obj.route_id == "1"
    assert len(registry) == 1


def test_build_object_events_custom_route_dedups_identical_routes() -> None:
    """Two objects with the SAME encodable route share one route_id — the
    registry dedups by bytecode, not by event id."""
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    map_json = {
        "map_id": 32,
        "events": [
            _event(1, 1, 1, [_moving_page([2, 2, 3, 3])]),
            _event(2, 5, 5, [_moving_page([2, 2, 3, 3])]),
        ],
    }
    registry = RouteRegistry()
    result = mw.build_object_events(
        map_json, consts, _SLICE, npc_gfx=_npc_gfx_fixture(), route_registry=registry
    )
    ids = {obj.route_id for obj in result.object_events}
    assert ids == {"1"}
    assert len(registry) == 1


def test_build_object_events_no_custom_route_route_id_zero() -> None:
    """An event with no custom route (move_type 0, a static facing) gets the
    default route_id "0" — no registry entry, no registry needed at all."""
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    map_json = {"map_id": 32, "events": [_event(1, 1, 1, [_page(name="HGSS_000")])]}
    result = mw.build_object_events(map_json, consts, _SLICE, npc_gfx=_npc_gfx_fixture())
    (obj,) = result.object_events
    assert obj.route_id == "0"


def test_build_object_events_custom_route_without_registry_raises() -> None:
    """An encodable custom route with no route_registry given fails loud
    (CLAUDE.md §4.5) instead of silently dropping the route or crashing on a
    None deref."""
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    map_json = {"map_id": 32, "events": [_event(1, 1, 1, [_moving_page([2, 2, 3, 3])])]}
    with pytest.raises(ValueError):
        mw.build_object_events(map_json, consts, _SLICE, npc_gfx=_npc_gfx_fixture())


def test_build_object_events_drops_no_silent_defaults() -> None:
    """no_boot_page / blank_trigger1 / autorun / parallel / door_sheet / opacity0
    all land in the drop report, not silently in object_events."""
    consts = mc.MapConstantRegistry(Path("x")).mint(49, "Moki Town Player's House 1F")
    map_json = {
        "map_id": 49,
        "events": [
            _event(1, 0, 0, [_page(cond=_sw_cond(1))]),  # only page gated off at boot
            _event(2, 1, 0, [_page(trigger=1)]),  # blank graphic, player-touch (non-warp)
            _event(3, 2, 0, [_page(trigger=3)]),  # blank graphic, autorun
            _event(4, 3, 0, [_page(trigger=4)]),  # blank graphic, parallel
            _event(5, 4, 0, [_page(trigger=0, name="PU-doors1")]),  # door sheet
            _event(6, 5, 0, [_page(trigger=0, name="HGSS_000", opacity=0)]),  # invisible, non-touch
        ],
    }
    result = mw.build_object_events(map_json, consts, _SLICE, npc_gfx=_npc_gfx_fixture())
    assert result.object_events == [] and result.bg_events == [] and result.coord_events == []
    assert dict(result.drops) == {
        1: mw.DROP_NO_BOOT_PAGE,
        2: mw.DROP_BLANK_TRIGGER1,
        3: mw.DROP_AUTORUN,
        4: mw.DROP_PARALLEL,
        5: mw.DROP_DOOR_SHEET,
        6: mw.DROP_OPACITY0,
    }


def test_build_object_events_visible_graphic_requires_npc_gfx() -> None:
    """A visible (named, opacity != 0) graphic with no npc_gfx map, or a name
    absent from it, fails loud — no silent ninja-boy fallback (CLAUDE.md §4.5)."""
    consts = mc.MapConstantRegistry(Path("x")).mint(49, "Moki Town Player's House 1F")
    map_json = {"map_id": 49, "events": [_event(1, 4, 4, [_page(name="HGSS_000")])]}
    with pytest.raises(KeyError):
        mw.build_object_events(map_json, consts, _SLICE)  # npc_gfx=None
    with pytest.raises(KeyError):
        mw.build_object_events(map_json, consts, _SLICE, npc_gfx={})  # name unmapped


def test_build_object_events_rock_flags_assigned_ascending() -> None:
    """smashable_rock-traited events get FLAG_TEMP_11/12/13.. in ascending
    event-id order, independent of the events' list order or (x, y)."""
    consts = mc.MapConstantRegistry(Path("x")).mint(49, "Moki Town Player's House 1F")
    map_json = {
        "map_id": 49,
        "events": [
            _event(9, 1, 1, [_page(name="HGSS_000")]),
            _event(3, 2, 2, [_page(name="HGSS_005")]),
            _event(5, 3, 3, [_page(name="HGSS_000")]),  # untraited
        ],
    }
    result = mw.build_object_events(
        map_json, consts, _SLICE, npc_gfx=_npc_gfx_fixture(),
        event_traits={3: ["smashable_rock"], 9: ["smashable_rock"]},
    )
    by_xy = {(o.x, o.y): o for o in result.object_events}
    assert by_xy[(2, 2)].flag == "FLAG_TEMP_11"  # EV003 (lower id) assigned first
    assert by_xy[(1, 1)].flag == "FLAG_TEMP_12"  # EV009 second
    assert by_xy[(3, 3)].flag == "0"  # untraited event keeps the default


def test_build_object_events_no_traits_keeps_default_flag() -> None:
    """event_traits=None (legacy) leaves every ObjectEvent.flag at its "0"
    default — byte-identical to pre-trait behavior."""
    consts = mc.MapConstantRegistry(Path("x")).mint(49, "Moki Town Player's House 1F")
    map_json = {
        "map_id": 49,
        "events": [_event(1, 4, 4, [_page(name="HGSS_000")])],
    }
    result = mw.build_object_events(map_json, consts, _SLICE, npc_gfx=_npc_gfx_fixture())
    assert result.object_events[0].flag == "0"
    assert result.object_events[0].to_dict()["flag"] == "0"


# --- hidden cutscene actors (findings §3.3/§5) --------------------------------

def _actor_npc_gfx() -> dict[str, str]:
    return dict(
        _npc_gfx_fixture(),
        Rivaltheo="OBJ_EVENT_GFX_URANIUM_RIVALTHEO",
        **{"ZP- Professor": "OBJ_EVENT_GFX_URANIUM_ZP_PROFESSOR"},
        **{"PU-Chyinmunk": "OBJ_EVENT_GFX_URANIUM_PU_CHYINMUNK"},
    )


def test_build_object_events_hidden_actor_basic() -> None:
    """A required actor id with no boot-active page (Map032 EV002 'Rivaltheo'
    shape: var101 >= 2, opacity 255) gets placed — visible graphic, static
    facing, a visibility flag, a local id, and an ON_TRANSITION clause."""
    reg = FlagRegistry()
    reg.propose_var(101, "VAR_QUEST_LOG")
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    event = _event(
        2, 16, 45,
        [
            _page(cond=_var_cond(101, 2), name="Rivaltheo", direction=4),
            _page(cond=_var_cond(101, 4)),  # blank higher page
        ],
    )
    map_json = {"map_id": 32, "events": [event]}
    result = mw.build_object_events(
        map_json, consts, {32}, npc_gfx=_actor_npc_gfx(), flag_registry=reg,
        required_actor_ids={2},
    )
    assert len(result.object_events) == 1
    obj = result.object_events[0]
    assert (obj.x, obj.y) == (16, 45)
    assert obj.graphics_id == "OBJ_EVENT_GFX_URANIUM_RIVALTHEO"
    assert obj.movement_type == "MOVEMENT_TYPE_FACE_LEFT"  # direction 4
    assert obj.flag == "FLAG_TEMP_11"
    assert result.local_id_map["2"] == 1
    assert any(ln == "# EV002 E2" for ln in result.transition_lines)
    assert "setflag(FLAG_TEMP_11)" in result.transition_lines
    joined = "\n".join(result.transition_lines)
    assert "var(VAR_QUEST_LOG) >= 2" in joined
    assert "var(VAR_QUEST_LOG) < 4" in joined
    assert "clearflag(FLAG_TEMP_11)" in joined


def test_build_object_events_hidden_actor_opacity0_never_visible() -> None:
    """An actor whose only graphic-bearing page has opacity 0 (Map032
    EV076/EV077 shape) never gets a `clearflag` clause — it stays
    flag-hidden until a hand-authored script `addobject`s it."""
    reg = FlagRegistry()
    reg.propose_var(101, "VAR_QUEST_LOG")
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    event = _event(
        76, 12, 44,
        [
            _page(cond=_var_cond(101, 2), name="PU-Chyinmunk", opacity=0, direction=4),
            _page(cond=_var_cond(101, 4)),
        ],
    )
    map_json = {"map_id": 32, "events": [event]}
    result = mw.build_object_events(
        map_json, consts, {32}, npc_gfx=_actor_npc_gfx(), flag_registry=reg,
        required_actor_ids={76},
    )
    assert len(result.object_events) == 1
    assert result.object_events[0].flag == "FLAG_TEMP_11"
    assert result.transition_lines == ["# EV076 E76", "setflag(FLAG_TEMP_11)"]


def test_build_object_events_hidden_actor_shares_flag_pool_with_rocks() -> None:
    """Rocks and hidden actors share ONE sequential FLAG_TEMP_11.._1F pool,
    ascending event-id order across both kinds."""
    reg = FlagRegistry()
    reg.propose_var(101, "VAR_QUEST_LOG")
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    actor = _event(9, 1, 1, [_page(cond=_var_cond(101, 2), name="Rivaltheo")])
    rock = _event(5, 2, 2, [_page(name="HGSS_000")])
    map_json = {"map_id": 32, "events": [actor, rock]}
    result = mw.build_object_events(
        map_json, consts, {32}, npc_gfx=_actor_npc_gfx(), flag_registry=reg,
        required_actor_ids={9}, event_traits={5: ["smashable_rock"]},
    )
    by_x = {o.x: o for o in result.object_events}
    assert by_x[2].flag == "FLAG_TEMP_11"  # EV005 (lower id) assigned first
    assert by_x[1].flag == "FLAG_TEMP_12"  # EV009 second


def test_build_object_events_hidden_actor_already_emitted_skipped() -> None:
    """A required id that already has a boot-active page is left to the
    normal emission path — not duplicated, no visibility flag spent."""
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    event = _event(3, 1, 1, [_page(name="HGSS_000")])  # unconditional, boot-active
    map_json = {"map_id": 32, "events": [event]}
    result = mw.build_object_events(
        map_json, consts, {32}, npc_gfx=_npc_gfx_fixture(), required_actor_ids={3},
    )
    assert len(result.object_events) == 1
    assert result.object_events[0].flag == "0"
    assert result.transition_lines == []


def test_build_object_events_hidden_actor_garbage_reference_fails_loud() -> None:
    """A required actor id absent from the map's events entirely is a
    garbage reference — fail loud."""
    consts = mc.MapConstantRegistry(Path("x")).mint(32, "Moki Town")
    map_json = {"map_id": 32, "events": []}
    with pytest.raises(ValueError):
        mw.build_object_events(
            map_json, consts, {32}, npc_gfx=_npc_gfx_fixture(), required_actor_ids={999},
        )


def test_build_object_events_hidden_actor_warp_target_skipped() -> None:
    """A required actor id that resolves to a warp/skip event is left to the
    strict local_id_remap pass, not placed as an actor: an animated-door
    sprite's only object-command refs live in its own page block, which the
    prune pass removes, so the pre-prune scan legitimately picks it up. If a
    LIVE script still references it after pruning, remap fails loud."""
    consts = mc.MapConstantRegistry(Path("x")).mint(49, "House 1F")
    door = _event(2, 10, 11, [_page(trigger=1, cmds=[_transfer(32, 28, 31)])])
    map_json = {"map_id": 49, "events": [door]}
    result = mw.build_object_events(
        map_json, consts, {32, 49}, npc_gfx=_npc_gfx_fixture(),
        required_actor_ids={2},
    )
    assert result.object_events == []
    assert "2" not in result.local_id_map


def test_build_object_events_object_cap_exceeded_fails_loud() -> None:
    """More than 64 object_events on one map exceeds the fork's
    OBJECT_EVENT_TEMPLATES_COUNT budget — fail loud."""
    consts = mc.MapConstantRegistry(Path("x")).mint(49, "House 1F")
    map_json = {
        "map_id": 49,
        "events": [_event(i, i, 0, [_page(name="HGSS_000")]) for i in range(1, 66)],
    }
    with pytest.raises(ValueError):
        mw.build_object_events(map_json, consts, _SLICE, npc_gfx=_npc_gfx_fixture())


def test_build_object_events_rock_flags_capacity_exceeded() -> None:
    """More than 15 (FLAG_TEMP_11..FLAG_TEMP_1F) smashable_rock events on one map
    is a fail-loud error, not silent flag reuse/overflow."""
    consts = mc.MapConstantRegistry(Path("x")).mint(49, "Moki Town Player's House 1F")
    map_json = {
        "map_id": 49,
        "events": [_event(i, i, 0, [_page(name="HGSS_000")]) for i in range(1, 17)],
    }
    with pytest.raises(ValueError):
        mw.build_object_events(
            map_json, consts, _SLICE, npc_gfx=_npc_gfx_fixture(),
            event_traits={i: ["smashable_rock"] for i in range(1, 17)},
        )


def test_build_object_events_unknown_trait_fails_loud() -> None:
    """A trait string other than "smashable_rock" is forward-compat-unknown ->
    fail loud rather than silently ignored."""
    consts = mc.MapConstantRegistry(Path("x")).mint(49, "Moki Town Player's House 1F")
    map_json = {
        "map_id": 49,
        "events": [_event(1, 4, 4, [_page(name="HGSS_000")])],
    }
    with pytest.raises(ValueError):
        mw.build_object_events(
            map_json, consts, _SLICE, npc_gfx=_npc_gfx_fixture(),
            event_traits={1: ["some_future_trait"]},
        )


def test_build_object_events_stale_trait_fails_loud() -> None:
    """A traits sidecar entry for an event id that resolves to no emitted
    object_event (nonexistent id, or dropped by boot-page classification) is a
    stale-sidecar error, not a silent no-op."""
    consts = mc.MapConstantRegistry(Path("x")).mint(49, "Moki Town Player's House 1F")
    map_json = {
        "map_id": 49,
        "events": [_event(1, 4, 4, [_page(name="HGSS_000")])],
    }
    # id 999 doesn't correspond to any event on the map at all.
    with pytest.raises(ValueError):
        mw.build_object_events(
            map_json, consts, _SLICE, npc_gfx=_npc_gfx_fixture(),
            event_traits={999: ["smashable_rock"]},
        )
    # id 2 exists on the map but is dropped (no boot-active page) -> also an error.
    map_json_dropped = {
        "map_id": 49,
        "events": [
            _event(1, 4, 4, [_page(name="HGSS_000")]),
            _event(2, 5, 5, [_page(cond=_sw_cond(1))]),  # only page gated off at boot
        ],
    }
    with pytest.raises(ValueError):
        mw.build_object_events(
            map_json_dropped, consts, _SLICE, npc_gfx=_npc_gfx_fixture(),
            event_traits={2: ["smashable_rock"]},
        )


def test_write_local_id_tables_pinned_shape(tmp_path: Path) -> None:
    """write_local_id_tables emits one Map{id:03d}.json per map with exactly the
    pinned {decimal-string RMXP id: int local id} shape (the local_id_remap.py
    contract)."""
    out_dir = tmp_path / "local_ids"
    mw.write_local_id_tables(out_dir, {49: {"1": 1, "7": 2}, 32: {"9": 1}})
    assert json.loads((out_dir / "Map049.json").read_text(encoding="utf-8")) == {"1": 1, "7": 2}
    assert json.loads((out_dir / "Map032.json").read_text(encoding="utf-8")) == {"9": 1}


def test_build_object_events_page_gap_fails_loud() -> None:
    """An event with a converted later page but an empty base page (the resolved
    fallback label) is a real gap, not a command-less NPC -> fail loud."""
    consts = mc.MapConstants(49, "MAP_X", "MAP_URANIUM_49", "LAYOUT_X", "MAPSEC_X", "X", "X")
    # global-gated 2-page event: dispatch is deferred -> resolves to _Page1, but
    # only _Page2 was converted.
    ev = _event(5, 0, 0, [_page(), _page(cond=_sw_cond(125))])
    map_json = {"map_id": 49, "events": [ev]}
    with pytest.raises(KeyError):
        mw.build_object_events(map_json, consts, _SLICE, pory_labels={"Map049_EV005_Page2"})


def test_page_dispatcher_self_switch() -> None:
    """A self-switch 2-page event gets a dispatcher: goto page 2 if the flag is set,
    else fall back to page 1 (RMXP highest-satisfiable-page wins)."""
    consts = mc.MapConstants(48, "MAP_X", "MAP_URANIUM_48", "LAYOUT_X", "MAPSEC_X", "X", "X")
    event = _event(1, 2, 10, [_page(), _page(cond=_self_cond("A"))])
    disp = mw.build_page_dispatcher(event, consts)
    assert "if (flag(FLAG_MAP048_EVENT001_SSA))" in disp
    # parenthesized goto() — poryscript splits the bare `goto Label` form into two
    # invalid asm lines (`goto` with no arg + the label as a bad instruction).
    assert "goto(Map048_EV001_Page2)" in disp
    assert "goto(Map048_EV001_Page1)" in disp  # base-page fallback


def test_page_dispatcher_gated_base_page_guarded() -> None:
    """Map032 EV080 regression shape: the base page (index 0) is itself gated
    on switch 125 (FLAG_FINAL_EVENT, postgame). The fixed dispatcher must NOT
    treat page 0 as an unconditional fallback — it becomes a guard like any
    other page, and since no page is unconditional, the dispatcher ends inert
    (bare `end`), never an unguarded `goto` to the base page."""
    consts = mc.MapConstants(32, "MAP_X", "MAP_URANIUM_32", "LAYOUT_X", "MAPSEC_X", "X", "X")
    reg = FlagRegistry()
    reg.propose_flag(125, "FLAG_FINAL_EVENT")
    event = _event(80, 0, 0, [_page(cond=_sw_cond(125)), _page(cond=_self_cond("A"))])
    disp = mw.build_page_dispatcher(event, consts, flag_registry=reg)
    assert disp is not None
    assert "if (flag(FLAG_FINAL_EVENT))" in disp
    assert "goto(Map032_EV080_Page1)" in disp
    assert f"if (flag(FLAG_MAP032_EVENT080_SSA))" in disp
    assert "goto(Map032_EV080_Page2)" in disp
    # base-page goto is inside its own guard, not an unguarded fallback line.
    lines = disp.rstrip().splitlines()
    assert lines[-2].strip() == "end"
    assert lines[-1].strip() == "}"


def test_page_dispatcher_all_pages_gated_inert() -> None:
    """Same EV080 shape: every page carries a condition, none unconditional ->
    the dispatcher body's last statement before the closing brace is a bare
    `end` (RMXP "no active page" == inert event), not a fallback goto."""
    consts = mc.MapConstants(32, "MAP_X", "MAP_URANIUM_32", "LAYOUT_X", "MAPSEC_X", "X", "X")
    reg = FlagRegistry()
    reg.propose_flag(125, "FLAG_FINAL_EVENT")
    event = _event(80, 0, 0, [_page(cond=_sw_cond(125)), _page(cond=_self_cond("A"))])
    disp = mw.build_page_dispatcher(event, consts, flag_registry=reg)
    assert disp is not None
    assert disp.rstrip().splitlines()[-2].strip() == "end"


def test_page_dispatcher_single_gated_page() -> None:
    """A single-page event whose only page carries a resolvable condition now
    emits a guarded dispatcher (`if (...) { goto(Page1) }` then bare `end`)
    instead of deferring to None — the single-page-unconditional shortcut only
    applies when the lone page is unconditional."""
    consts = mc.MapConstants(49, "MAP_X", "MAP_URANIUM_49", "LAYOUT_X", "MAPSEC_X", "X", "X")
    reg = FlagRegistry()
    reg.propose_flag(125, "FLAG_FINAL_EVENT")
    event = _event(7, 0, 0, [_page(cond=_sw_cond(125))])
    disp = mw.build_page_dispatcher(event, consts, flag_registry=reg)
    assert disp is not None
    assert "if (flag(FLAG_FINAL_EVENT))" in disp
    assert "goto(Map049_EV007_Page1)" in disp
    assert disp.rstrip().splitlines()[-2].strip() == "end"

    # A single-page event with NO condition at all still returns None (no
    # dispatch needed).
    assert mw.build_page_dispatcher(_event(8, 0, 0, [_page()]), consts, flag_registry=reg) is None


def test_page_dispatcher_gated_base_page_defers_without_registry() -> None:
    """The EV080 shape with no registry (deferral unchanged): an unresolvable
    switch gate on the base page still defers the whole event to None, same
    as any other unresolvable gate."""
    consts = mc.MapConstants(32, "MAP_X", "MAP_URANIUM_32", "LAYOUT_X", "MAPSEC_X", "X", "X")
    event = _event(80, 0, 0, [_page(cond=_sw_cond(125)), _page(cond=_self_cond("A"))])
    assert mw.build_page_dispatcher(event, consts, flag_registry=None) is None
    assert mw.build_page_dispatcher(event, consts) is None


def test_page_dispatcher_touch_channel_ends_action_pages() -> None:
    """Map032 EV009 shape (chapter beat B14, 2026-07-27): pages 0-2 are
    event-touch, the top page is action-button. A `coord_event` fires by
    WALKING, so on CHANNEL_TOUCH the action page must become a bare `end` —
    dispatching it there printed its post-ceremony line on every crossing.
    The same event on CHANNEL_ACTION still reaches that page."""
    consts = mc.MapConstants(32, "MAP_X", "MAP_URANIUM_32", "LAYOUT_X", "MAPSEC_X", "X", "X")
    reg = FlagRegistry()
    reg.propose_flag(125, "FLAG_FINAL_EVENT")
    event = _event(9, 16, 42, [
        _page(trigger=mw.TRIGGER_EVENT_TOUCH),
        _page(trigger=mw.TRIGGER_ACTION, cond=_self_cond("A")),
    ])

    touch = mw.build_page_dispatcher(
        event, consts, flag_registry=reg, channel=mw.CHANNEL_TOUCH)
    assert "if (flag(FLAG_MAP032_EVENT009_SSA))" in touch
    assert "goto(Map032_EV009_Page2)" not in touch  # the action page is silenced
    assert "goto(Map032_EV009_Page1)" in touch  # touch fallback still fires

    action = mw.build_page_dispatcher(
        event, consts, flag_registry=reg, channel=mw.CHANNEL_ACTION)
    assert "goto(Map032_EV009_Page2)" in action


def test_page_dispatcher_touch_channel_keeps_both_touch_triggers() -> None:
    """Player-touch (1) and event-touch (2) are both walk-on triggers, so
    neither is silenced on CHANNEL_TOUCH — only action/autorun/parallel are."""
    consts = mc.MapConstants(49, "MAP_X", "MAP_URANIUM_49", "LAYOUT_X", "MAPSEC_X", "X", "X")
    reg = FlagRegistry()
    event = _event(2, 10, 11, [
        _page(trigger=mw.TRIGGER_PLAYER_TOUCH),
        _page(trigger=mw.TRIGGER_EVENT_TOUCH, cond=_self_cond("A")),
    ])
    disp = mw.build_page_dispatcher(
        event, consts, flag_registry=reg, channel=mw.CHANNEL_TOUCH)
    assert "goto(Map049_EV002_Page1)" in disp
    assert "goto(Map049_EV002_Page2)" in disp


def test_page_dispatcher_rejects_unknown_channel() -> None:
    consts = mc.MapConstants(49, "MAP_X", "MAP_URANIUM_49", "LAYOUT_X", "MAPSEC_X", "X", "X")
    with pytest.raises(ValueError, match="unknown dispatch channel"):
        mw.build_page_dispatcher(
            _event(1, 0, 0, [_page(), _page(cond=_self_cond("A"))]),
            consts, channel="bump")


def test_action_pages_get_an_a_press_host_beside_the_coord_event() -> None:
    """The other half of the B14 fix: silencing an action page on the walk-on
    channel must not make it unreachable, because in RMXP you CAN press A at
    the tile. An invisible touch host with an action page therefore emits both
    a coord_event (touch dispatcher) and a bg_event sign on the event's own
    tile (action dispatcher, distinct label)."""
    consts = mc.MapConstants(32, "MAP_X", "MAP_URANIUM_32", "LAYOUT_X", "MAPSEC_X", "X", "X")
    reg = FlagRegistry()
    event = _event(9, 16, 42, [
        _page(trigger=mw.TRIGGER_EVENT_TOUCH, opacity=0, name="Rivaltheo",
              cmds=[{"code": 101, "indent": 0, "parameters": ["hi"]}]),
        _page(trigger=mw.TRIGGER_ACTION, cond=_self_cond("A"), opacity=0,
              name="Rivaltheo", cmds=[{"code": 101, "indent": 0, "parameters": ["yo"]}]),
    ], name="Trainer(6)")
    res = mw.build_object_events({"map_id": 32, "events": [event]}, consts, _SLICE,
                                 flag_registry=reg)

    # Trainer(6) spreads its walk-on host down the sight ray; the A-press host
    # stays on the event's own tile, which is how a sign is read.
    assert res.coord_events
    assert {c.script for c in res.coord_events} == {"Map032_EV009_Dispatch"}
    assert [(b.x, b.y, b.script) for b in res.bg_events] == [
        (16, 42, "Map032_EV009_ActionDispatch")]
    bodies = "\n".join(res.dispatchers)
    assert "script Map032_EV009_Dispatch" in bodies
    assert "script Map032_EV009_ActionDispatch" in bodies
    # the walk-on side ends on the action page; the A-press side runs it
    touch_body = next(d for d in res.dispatchers if "_Dispatch {" in d.splitlines()[0])
    action_body = next(d for d in res.dispatchers if "_ActionDispatch" in d)
    assert "goto(Map032_EV009_Page2)" not in touch_body
    assert "goto(Map032_EV009_Page2)" in action_body
    # ...and the A-press host adds ONLY the action page: pressing A must not
    # become a second way to fire the walk-on page (CHANNEL_ACTION_ONLY).
    assert "goto(Map032_EV009_Page1)" in touch_body
    assert "goto(Map032_EV009_Page1)" not in action_body


def test_no_action_host_when_no_action_page() -> None:
    """A pure touch event (every page walk-on) gains nothing — no bg_event,
    no second dispatcher. Guards against the fix inflating every coord host."""
    consts = mc.MapConstants(32, "MAP_X", "MAP_URANIUM_32", "LAYOUT_X", "MAPSEC_X", "X", "X")
    reg = FlagRegistry()
    event = _event(74, 26, 12, [
        _page(trigger=mw.TRIGGER_EVENT_TOUCH, opacity=0, name="HGSS_014",
              cmds=[{"code": 101, "indent": 0, "parameters": ["hi"]}]),
        _page(trigger=mw.TRIGGER_EVENT_TOUCH, cond=_self_cond("A"), opacity=0,
              name="HGSS_014", cmds=[{"code": 101, "indent": 0, "parameters": ["yo"]}]),
    ])
    res = mw.build_object_events({"map_id": 32, "events": [event]}, consts, _SLICE,
                                 flag_registry=reg)
    assert res.coord_events and not res.bg_events
    assert all("_ActionDispatch" not in d for d in res.dispatchers)


def test_page_dispatcher_deferred_on_global() -> None:
    """A global switch/var page gate defers (None) when no registry is given
    (the default); single-page also None."""
    consts = mc.MapConstants(49, "MAP_X", "MAP_URANIUM_49", "LAYOUT_X", "MAPSEC_X", "X", "X")
    global_gated = _event(1, 0, 0, [_page(), _page(cond=_sw_cond(125))])
    assert mw.build_page_dispatcher(global_gated, consts) is None
    assert mw.build_page_dispatcher(_event(2, 0, 0, [_page()]), consts) is None


def _var_cond(variable_id: int, value: int = 1) -> dict:
    return {"variable_valid": True, "variable_id": variable_id, "variable_value": value}


def _sw_and_self_cond(switch_id: int, letter: str) -> dict:
    return {
        "switch1_valid": True, "switch1_id": switch_id,
        "self_switch_valid": True, "self_switch_ch": letter,
    }


def test_page_dispatcher_global_gate_resolves_through_registry() -> None:
    """The live defect this brief fixes: a global switch gate resolves through
    the registry into a real dispatcher instead of deferring to Page1 forever
    (Map049 EV1 'Auntie' / Map032 EV27 Rare Candy repeat-NPC bug). High->low
    order: the guard appears before the Page1 fallback goto."""
    consts = mc.MapConstants(49, "MAP_X", "MAP_URANIUM_49", "LAYOUT_X", "MAPSEC_X", "X", "X")
    reg = FlagRegistry()
    reg.propose_flag(125, "FLAG_FINAL_EVENT")
    event = _event(1, 0, 0, [_page(), _page(cond=_sw_cond(125))])
    disp = mw.build_page_dispatcher(event, consts, flag_registry=reg)
    assert disp is not None
    assert "if (flag(FLAG_FINAL_EVENT))" in disp
    assert "goto(Map049_EV001_Page2)" in disp
    assert "goto(Map049_EV001_Page1)" in disp  # base-page fallback
    assert disp.index("goto(Map049_EV001_Page2)") < disp.index("goto(Map049_EV001_Page1)")


def test_page_dispatcher_switch_and_self_switch_conjunction() -> None:
    """A page gated on BOTH a global switch and a self-switch emits a single
    `if` with a `&&` conjunction, not two separate guards."""
    consts = mc.MapConstants(49, "MAP_X", "MAP_URANIUM_49", "LAYOUT_X", "MAPSEC_X", "X", "X")
    reg = FlagRegistry()
    reg.propose_flag(125, "FLAG_FINAL_EVENT")
    event = _event(1, 0, 0, [_page(), _page(cond=_sw_and_self_cond(125, "A"))])
    disp = mw.build_page_dispatcher(event, consts, flag_registry=reg)
    assert disp is not None
    assert "if (flag(FLAG_FINAL_EVENT) && flag(FLAG_MAP049_EVENT001_SSA))" in disp
    assert disp.count("if (") == 1


def test_page_dispatcher_variable_gate() -> None:
    """A variable page gate emits `var(NAME) >= value` — RMXP's own semantics
    (`Game_Event#refresh`, reference/scripts_dump/022_Game_Event_v17.rb:151-154:
    `next if $game_variables[c.variable_id] < c.variable_value`, i.e. the page
    holds iff the variable is >= the threshold)."""
    consts = mc.MapConstants(49, "MAP_X", "MAP_URANIUM_49", "LAYOUT_X", "MAPSEC_X", "X", "X")
    reg = FlagRegistry()
    reg.propose_var(87, "VAR_GYM8_WHITE_TILES")
    event = _event(1, 0, 0, [_page(), _page(cond=_var_cond(87, 3))])
    disp = mw.build_page_dispatcher(event, consts, flag_registry=reg)
    assert disp is not None
    assert "if (var(VAR_GYM8_WHITE_TILES) >= 3)" in disp


def test_page_dispatcher_script_switch_defers_even_with_registry() -> None:
    """A page gated on an Essentials script-switch (`s:...`) can never resolve
    to a FLAG_* — the registry refuses to mint one for it — so dispatch still
    defers even when a live registry is supplied."""
    reg = FlagRegistry()
    reg.pre_seed(_PRESEED, _SWITCHES, _VARIABLES)
    assert reg.is_script_switch(1)  # switch 1 == "s:pbIsWeekday(...)" (fixture data)
    consts = mc.MapConstants(49, "MAP_X", "MAP_URANIUM_49", "LAYOUT_X", "MAPSEC_X", "X", "X")
    event = _event(1, 0, 0, [_page(), _page(cond=_sw_cond(1))])
    assert mw.build_page_dispatcher(event, consts, flag_registry=reg) is None


def test_page_dispatcher_temp_switch_on_gate() -> None:
    """Switch 12 = ``s:tsOn?("A")`` (Moki Town Map032 EV036 idiom, fixture data):
    the temp-switch carve-out resolves it to a per-event temp-switch flag
    instead of deferring the whole event to Page1."""
    reg = FlagRegistry()
    reg.pre_seed(_PRESEED, _SWITCHES, _VARIABLES)
    consts = mc.MapConstants(49, "MAP_X", "MAP_URANIUM_49", "LAYOUT_X", "MAPSEC_X", "X", "X")
    event = _event(1, 0, 0, [_page(), _page(cond=_sw_cond(12))])
    disp = mw.build_page_dispatcher(event, consts, flag_registry=reg)
    assert disp is not None
    assert "flag(FLAG_MAP049_EVENT001_TSA)" in disp
    assert "goto(Map049_EV001_Page2)" in disp
    assert reg.to_state()["temp_switches"]["49:1:A"] == "FLAG_MAP049_EVENT001_TSA"


def test_page_dispatcher_temp_switch_off_gate() -> None:
    """Switch 22 = ``s:tsOff?("A")`` (Moki Town Map032 EV003/005/006/007/017/
    023/037 idiom, fixture data): negated guard — ``tsOff?`` is true when the
    temp switch was never set OR was explicitly cleared, both covered by a
    cleared GBA flag."""
    reg = FlagRegistry()
    reg.pre_seed(_PRESEED, _SWITCHES, _VARIABLES)
    consts = mc.MapConstants(49, "MAP_X", "MAP_URANIUM_49", "LAYOUT_X", "MAPSEC_X", "X", "X")
    event = _event(3, 0, 0, [_page(), _page(cond=_sw_cond(22))])
    disp = mw.build_page_dispatcher(event, consts, flag_registry=reg)
    assert disp is not None
    assert "!flag(FLAG_MAP049_EVENT003_TSA)" in disp


def test_page_dispatcher_temp_switch_mint_converges_with_transpiler() -> None:
    """The dispatcher-minted name is exactly `temp_switch_flag_name(uid, eid,
    key)`, and re-minting the same key (the path the transpiler's
    setTempSwitchOn idiom uses) converges on the identical name — idempotent,
    not a second distinct flag."""
    reg = FlagRegistry()
    reg.pre_seed(_PRESEED, _SWITCHES, _VARIABLES)
    consts = mc.MapConstants(49, "MAP_X", "MAP_URANIUM_49", "LAYOUT_X", "MAPSEC_X", "X", "X")
    event = _event(1, 0, 0, [_page(), _page(cond=_sw_cond(12))])
    disp = mw.build_page_dispatcher(event, consts, flag_registry=reg)
    assert disp is not None
    expected = temp_switch_flag_name(49, 1, "A")
    assert f"flag({expected})" in disp
    assert reg.mint_temp_switch(49, 1, "A") == expected  # idempotent convergence


def test_page_dispatcher_labelless_registry_defers_then_seed_labels_fixes(
    tmp_path: Path,
) -> None:
    """Pins both the staging landmine and the seed_labels fix: a registry
    round-tripped through to_state()/save+load loses labels by design
    (is_script_switch survives — it IS persisted — but label_for_switch does
    not), so the temp-switch carve-out can't fire until seed_labels reloads
    the sidecars."""
    reg = FlagRegistry()
    reg.pre_seed(_PRESEED, _SWITCHES, _VARIABLES)
    state_path = tmp_path / "flag_state.json"
    reg.save(state_path)
    loaded = FlagRegistry.load(state_path)
    assert loaded.is_script_switch(12)
    assert loaded.label_for_switch(12) is None  # labels not persisted

    consts = mc.MapConstants(49, "MAP_X", "MAP_URANIUM_49", "LAYOUT_X", "MAPSEC_X", "X", "X")
    event = _event(1, 0, 0, [_page(), _page(cond=_sw_cond(12))])
    assert mw.build_page_dispatcher(event, consts, flag_registry=loaded) is None

    loaded.seed_labels(_SWITCHES, _VARIABLES)
    disp = mw.build_page_dispatcher(event, consts, flag_registry=loaded)
    assert disp is not None
    assert "flag(FLAG_MAP049_EVENT001_TSA)" in disp


def test_page_dispatcher_no_registry_global_gate_still_defers() -> None:
    """Pin: `flag_registry=None` + a global gate -> None, identical to today's
    behavior (both the explicit-None and default-param forms)."""
    consts = mc.MapConstants(49, "MAP_X", "MAP_URANIUM_49", "LAYOUT_X", "MAPSEC_X", "X", "X")
    event = _event(1, 0, 0, [_page(), _page(cond=_sw_cond(125))])
    assert mw.build_page_dispatcher(event, consts, flag_registry=None) is None
    assert mw.build_page_dispatcher(event, consts) is None


def test_page_dispatcher_mints_condition_only_self_switch() -> None:
    """A self-switch referenced ONLY in a page condition (never in that page's
    own command list) still gets minted into the registry by dispatch — else
    it's missing from the emitted flags header and the fork-capability gate
    rejects the dispatcher's own `flag(...)` reference."""
    consts = mc.MapConstants(49, "MAP_X", "MAP_URANIUM_49", "LAYOUT_X", "MAPSEC_X", "X", "X")
    reg = FlagRegistry()
    event = _event(9, 0, 0, [_page(), _page(cond=_self_cond("C"))])
    disp = mw.build_page_dispatcher(event, consts, flag_registry=reg)
    assert disp is not None
    # mint_self_switch is idempotent -> re-minting the same key returns the same
    # name dispatch already registered, proving it was minted during dispatch.
    assert reg.mint_self_switch(49, 9, "C") == "FLAG_MAP049_EVENT009_SSC"


def test_resolve_script_dispatcher_missing_page_label_fails_loud() -> None:
    """A dispatcher that would `goto()` a page label absent from the converted
    .pory is a genuine page-body gap — fail loud (mirrors the existing
    base-page-gap check in `_resolve_script`, `test_build_object_events_page_gap_fails_loud`)."""
    consts = mc.MapConstants(49, "MAP_X", "MAP_URANIUM_49", "LAYOUT_X", "MAPSEC_X", "X", "X")
    reg = FlagRegistry()
    reg.propose_flag(125, "FLAG_FINAL_EVENT")
    event = _event(1, 0, 0, [_page(), _page(cond=_sw_cond(125))])
    # Page1 is in pory_labels (so the event isn't classified bodyless), but the
    # dispatcher's guard target Page2 is missing from it.
    with pytest.raises(KeyError):
        mw._resolve_script(event, consts, {"Map049_EV001_Page1"}, reg)


def test_page_dispatcher_autorun_guard_target_emits_end() -> None:
    """findings §3.2 BUG B: a page whose OWN trigger is autorun (3) must never
    be a `goto()` target from the action-button dispatcher — `end` instead,
    even when it's a guarded (non-fallback) page."""
    consts = mc.MapConstants(49, "MAP_X", "MAP_URANIUM_49", "LAYOUT_X", "MAPSEC_X", "X", "X")
    event = _event(1, 0, 0, [_page(), _page(cond=_self_cond("A"), trigger=3)])
    disp = mw.build_page_dispatcher(event, consts)
    assert disp is not None
    assert "if (flag(FLAG_MAP049_EVENT001_SSA))" in disp
    assert "        end" in disp
    assert "goto(Map049_EV001_Page2)" not in disp
    assert "goto(Map049_EV001_Page1)" in disp  # base page (trigger 0) stays a real goto


def test_page_dispatcher_autorun_fallback_emits_end() -> None:
    """Same rule for the fallback (base) page: a trigger-3/4 base page's
    trailing goto becomes `end` too."""
    consts = mc.MapConstants(49, "MAP_X", "MAP_URANIUM_49", "LAYOUT_X", "MAPSEC_X", "X", "X")
    event = _event(1, 0, 0, [_page(trigger=3), _page(cond=_self_cond("A"))])
    disp = mw.build_page_dispatcher(event, consts)
    assert disp is not None
    assert "goto(Map049_EV001_Page2)" in disp  # the guarded (trigger 0) page
    assert disp.rstrip().splitlines()[-2].strip() == "end"
    assert "goto(Map049_EV001_Page1)" not in disp


def test_page_dispatcher_parallel_target_also_emits_end() -> None:
    """Trigger 4 (parallel) is treated identically to trigger 3 (autorun)."""
    consts = mc.MapConstants(49, "MAP_X", "MAP_URANIUM_49", "LAYOUT_X", "MAPSEC_X", "X", "X")
    event = _event(1, 0, 0, [_page(), _page(cond=_self_cond("A"), trigger=4)])
    disp = mw.build_page_dispatcher(event, consts)
    assert disp is not None
    assert "        end" in disp
    assert "goto(Map049_EV001_Page2)" not in disp


def test_build_object_events_autorun_base_page_falls_back_to_end() -> None:
    """findings §3.2 BUG B, the live defect shape: Map050 EV005 "Bambo" — a
    visible-graphic, ungated, trigger-3 BASE page with an interactable
    (trigger 0) higher page. The object still places (Bambo stands in the
    lab) and stays interactable via its higher page, but the fallback (base,
    autorun) is never itself a goto target — talking to him before the
    self-switch fires does nothing, not re-runs the intro."""
    consts = mc.MapConstantRegistry(Path("x")).mint(50, "Professor Lab")
    event = _event(
        5, 10, 10,
        [
            _page(trigger=3, name="ZP- Professor2"),  # ungated autorun boot page
            _page(cond=_self_cond("D"), name="ZP- Professor2"),  # trigger 0
        ],
    )
    map_json = {"map_id": 50, "events": [event]}
    npc_gfx = dict(_npc_gfx_fixture(), **{"ZP- Professor2": "OBJ_EVENT_GFX_URANIUM_ZP_PROFESSOR2"})
    result = mw.build_object_events(map_json, consts, {50}, npc_gfx=npc_gfx)
    assert len(result.object_events) == 1
    obj = result.object_events[0]
    assert (obj.x, obj.y) == (10, 10)
    assert obj.graphics_id == "OBJ_EVENT_GFX_URANIUM_ZP_PROFESSOR2"
    assert obj.script == "Map050_EV005_Dispatch"
    assert len(result.dispatchers) == 1
    disp = result.dispatchers[0]
    assert "goto(Map050_EV005_Page2)" in disp  # the higher, interactable page
    assert disp.rstrip().splitlines()[-2].strip() == "end"  # base (autorun) fallback


def test_build_object_events_all_pages_autorun_collapses_to_null_script() -> None:
    """When EVERY page a dispatcher could target is autorun/parallel, the
    whole dispatcher is dead weight (nothing but `end` branches) — the
    object gets the null script directly and no dispatcher is emitted at
    all, matching the single-page case."""
    consts = mc.MapConstantRegistry(Path("x")).mint(50, "Professor Lab")
    event = _event(
        7, 2, 2,
        [
            _page(trigger=3, name="HGSS_000"),  # ungated autorun base
            _page(cond=_self_cond("A"), name="HGSS_000", trigger=4),  # parallel guard
        ],
    )
    map_json = {"map_id": 50, "events": [event]}
    result = mw.build_object_events(map_json, consts, {50}, npc_gfx=_npc_gfx_fixture())
    assert len(result.object_events) == 1
    assert result.object_events[0].script == mw.NO_SCRIPT
    assert result.dispatchers == []


def test_build_object_events_single_page_autorun_visible_is_null_script() -> None:
    """A single-page trigger-3 event with a visible graphic (no dispatcher at
    all, since len(pages) == 1): also null-scripted, not page-1-scripted."""
    consts = mc.MapConstantRegistry(Path("x")).mint(50, "Professor Lab")
    map_json = {
        "map_id": 50,
        "events": [_event(9, 1, 1, [_page(trigger=3, name="HGSS_000")])],
    }
    result = mw.build_object_events(
        map_json, consts, {50}, npc_gfx=_npc_gfx_fixture(),
    )
    assert len(result.object_events) == 1
    assert result.object_events[0].script == mw.NO_SCRIPT


def test_build_object_events_interactive_page_still_goto_reachable() -> None:
    """A visible-graphic event whose HIGHEST guarded page is ordinary
    (trigger 0) still dispatches normally — BUG B's fix only neutralizes
    autorun/parallel targets, not the whole event."""
    consts = mc.MapConstantRegistry(Path("x")).mint(50, "Professor Lab")
    event = _event(
        5, 10, 10,
        [
            _page(name="HGSS_000"),  # base, trigger 0
            _page(cond=_self_cond("A"), name="HGSS_000"),  # trigger 0
        ],
    )
    map_json = {"map_id": 50, "events": [event]}
    result = mw.build_object_events(map_json, consts, {50}, npc_gfx=_npc_gfx_fixture())
    assert len(result.object_events) == 1
    assert result.object_events[0].script == "Map050_EV005_Dispatch"
    assert len(result.dispatchers) == 1
    assert "goto(Map050_EV005_Page2)" in result.dispatchers[0]
    assert "goto(Map050_EV005_Page1)" in result.dispatchers[0]


_OUTPUT_MAP032 = Path("output/uranium-build/maps/Map032.json")


@pytest.mark.skipif(not _OUTPUT_MAP032.is_file(), reason="Map032.json not generated")
def test_page_dispatcher_map032_ev27_real_data() -> None:
    """Real-corpus sanity check for the live defect: Map032 EV27 (repeat-handout
    NPC) dispatches Page4 (self-switch B + switch 125) before Page3 (switch 125)
    before Page2 (self-switch A), falling back to Page1."""
    map_json = json.loads(_OUTPUT_MAP032.read_text(encoding="utf-8"))
    event = next(e for e in map_json["events"] if e["id"] == 27)
    consts = mc.MapConstants(32, "MAP_X", "MAP_URANIUM_32", "LAYOUT_X", "MAPSEC_X", "X", "X")
    reg = FlagRegistry()
    reg.propose_flag(125, "FLAG_FINAL_EVENT")
    disp = mw.build_page_dispatcher(event, consts, flag_registry=reg)
    assert disp is not None
    p1 = disp.index("goto(Map032_EV027_Page1)")
    p2 = disp.index("goto(Map032_EV027_Page2)")
    p3 = disp.index("goto(Map032_EV027_Page3)")
    p4 = disp.index("goto(Map032_EV027_Page4)")
    assert p4 < p3 < p2 < p1
    assert "flag(FLAG_MAP032_EVENT027_SSB)" in disp
    assert "flag(FLAG_MAP032_EVENT027_SSA)" in disp
    assert "flag(FLAG_FINAL_EVENT)" in disp


def _mint_two_maps() -> mc.MapConstantRegistry:
    reg = mc.MapConstantRegistry(Path("x"))
    reg.mint(49, "Moki Town Player's House 1F")
    reg.mint(48, "Moki Town Player's House 2F")
    return reg


def test_warp_arrival_pairing_round_trip(tmp_path: Path) -> None:
    """Each source warp is paired to a plain-floor "arrival" warp_event emitted on
    the destination map at Uranium's true arrival coord (the vanilla-Emerald
    landing trick) — not the destination's own door tile. Source-warp indices are
    stable (0..n-1); arrivals are appended after. Override coord sets carry only
    the source-warp coords, never the arrival coords."""
    reg = _mint_two_maps()
    # A (49) has a door warp to B (48) landing at Uranium arrival (5, 6).
    map_a = {
        "map_id": 49, "width": 20, "height": 20,
        "events": [_event(3, 12, 3, [_page(1, cmds=[_transfer(48, 5, 6)])])],
    }
    # B (48) has a return warp to A (49) landing at Uranium arrival (2, 3).
    map_b = {
        "map_id": 48, "width": 20, "height": 20,
        "events": [_event(2, 3, 3, [_page(1, cmds=[_transfer(49, 2, 3)])])],
    }
    slice_set = {48, 49}
    maps = {49: map_a, 48: map_b}
    warp_lists = {
        49: [spec for _e, spec in mw.classify_map_events(map_a, slice_set)[1]],
        48: [spec for _e, spec in mw.classify_map_events(map_b, slice_set)[1]],
    }
    resolved = mw._resolve_all_warp_events(warp_lists, reg, maps)

    warps_a, warps_b = resolved[49], resolved[48]
    assert len(warps_a) == 2 and len(warps_b) == 2
    # B's list: [B's own source warp, arrival for A's door at (5, 6)]
    assert (warps_b[0].x, warps_b[0].y) == (3, 3)
    assert (warps_b[1].x, warps_b[1].y) == (5, 6)
    # A's source warp lands on B's arrival (index 1).
    assert warps_a[0].dest_warp_id == 1
    # A's list: [A's own source warp, arrival for B's return warp at (2, 3)]
    assert (warps_a[0].x, warps_a[0].y) == (12, 3)
    assert (warps_a[1].x, warps_a[1].y) == (2, 3)
    # B's source warp lands on A's arrival (index 1).
    assert warps_b[0].dest_warp_id == 1

    # End-to-end via the batch driver: override coord sets are source coords only.
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    (maps_dir / "Map049.json").write_text(json.dumps(map_a), encoding="utf-8")
    (maps_dir / "Map048.json").write_text(json.dumps(map_b), encoding="utf-8")
    metadata_path = tmp_path / "map_metadata.json"
    metadata_path.write_text(json.dumps({"maps": {}}), encoding="utf-8")
    out_dir = tmp_path / "out"
    overrides = mw.build_warps_only_maps(
        [49, 48], maps_dir=maps_dir, registry=reg, metadata_path=metadata_path, out_dir=out_dir,
    )
    assert overrides[49] == {(12, 3)}
    assert overrides[48] == {(3, 3)}


def test_warp_arrival_dedup() -> None:
    """Two adjacent door tiles in A targeting B at the same arrival coord share one
    arrival warp in B; both source warps' dest_warp_id point at it."""
    reg = _mint_two_maps()
    map_a = {
        "map_id": 49, "width": 20, "height": 20,
        "events": [
            _event(1, 10, 3, [_page(1, cmds=[_transfer(48, 5, 6)])]),
            _event(2, 11, 3, [_page(1, cmds=[_transfer(48, 5, 6)])]),
        ],
    }
    map_b = {"map_id": 48, "width": 20, "height": 20, "events": []}
    slice_set = {48, 49}
    maps = {49: map_a, 48: map_b}
    warp_lists = {
        49: [spec for _e, spec in mw.classify_map_events(map_a, slice_set)[1]],
        48: [],
    }
    resolved = mw._resolve_all_warp_events(warp_lists, reg, maps)

    assert len(resolved[48]) == 1  # one shared arrival, not two
    arrival = resolved[48][0]
    assert (arrival.x, arrival.y) == (5, 6)
    assert resolved[49][0].dest_warp_id == 0
    assert resolved[49][1].dest_warp_id == 0


def test_warp_arrival_out_of_bounds_falls_back(caplog: pytest.LogCaptureFixture) -> None:
    """Arrival coords outside the destination map's bounds -> no arrival emitted;
    the source warp falls back to the old return-warp pairing, and a warning is
    logged (fail loud, not silent)."""
    reg = _mint_two_maps()
    map_a = {
        "map_id": 49, "width": 20, "height": 20,
        "events": [_event(1, 10, 3, [_page(1, cmds=[_transfer(48, 99, 99)])])],
    }
    map_b = {
        "map_id": 48, "width": 10, "height": 10,
        "events": [_event(2, 3, 3, [_page(1, cmds=[_transfer(49, 5, 5)])])],
    }
    slice_set = {48, 49}
    maps = {49: map_a, 48: map_b}
    warp_lists = {
        49: [spec for _e, spec in mw.classify_map_events(map_a, slice_set)[1]],
        48: [spec for _e, spec in mw.classify_map_events(map_b, slice_set)[1]],
    }
    with caplog.at_level("WARNING"):
        resolved = mw._resolve_all_warp_events(warp_lists, reg, maps)

    assert len(resolved[48]) == 1  # no arrival for the out-of-bounds warp
    assert len(resolved[49]) == 2  # B's warp (in-bounds) still gets its arrival
    assert resolved[49][0].dest_warp_id == 0  # fallback: B's return warp (index 0)
    assert "out of bounds" in caplog.text


# --- post-warp arrival facing --------------------------------------------------

def _spec(dest_uid: int, x: int, y: int, direction: int | None) -> mw.WarpSpec:
    return mw.WarpSpec(src_x=0, src_y=0, dest_uid=dest_uid, dest_x=x, dest_y=y, dest_dir=direction)


def test_compute_arrival_facings_direction_mapping() -> None:
    """Each RMXP numpad Transfer Player direction maps to its engine DIR_*
    constant (see `_ARRIVAL_DIR_CONST`)."""
    maps = {48: {"width": 20, "height": 20}}
    for direction, dir_const in (
        (4, "DIR_WEST"), (6, "DIR_EAST"), (8, "DIR_NORTH"), (2, "DIR_SOUTH"),
    ):
        warp_lists = {49: [_spec(48, 5, 6, direction)]}
        out = mw.compute_arrival_facings(warp_lists, maps)
        assert out == {48: [mw.ArrivalFacing(5, 6, dir_const)]}


def test_compute_arrival_facings_skips_zero_and_none() -> None:
    """dest_dir 0 ("retain facing", engine default applies) and None
    (malformed/legacy event) produce no arrival entry at all for that map."""
    maps = {48: {"width": 20, "height": 20}}
    warp_lists = {49: [_spec(48, 5, 6, 0), _spec(49, 2, 3, None)]}
    assert mw.compute_arrival_facings(warp_lists, maps) == {}


def test_compute_arrival_facings_unknown_direction_fails_loud() -> None:
    """A direction outside {0, 2, 4, 6, 8} is an unrecognized RMXP transfer
    dir — fail loud rather than silently dropping it or guessing a facing."""
    maps = {48: {"width": 20, "height": 20}}
    warp_lists = {49: [_spec(48, 5, 6, 5)]}
    with pytest.raises(ValueError):
        mw.compute_arrival_facings(warp_lists, maps)


def test_compute_arrival_facings_same_coord_same_dir_dedups() -> None:
    """Two warps (from different source maps) landing on the identical
    (dest_uid, x, y) with the SAME facing collapse into exactly one table row."""
    maps = {48: {"width": 20, "height": 20}}
    warp_lists = {
        49: [_spec(48, 5, 6, 4)],
        50: [_spec(48, 5, 6, 4)],
    }
    out = mw.compute_arrival_facings(warp_lists, maps)
    assert out == {48: [mw.ArrivalFacing(5, 6, "DIR_WEST")]}


def test_compute_arrival_facings_same_coord_different_dir_fails_loud() -> None:
    """Two warps landing on the identical coord but wanting DIFFERENT facings
    can't be told apart by coordinate dispatch alone — fail loud rather than
    silently picking one (which would be wrong half the time)."""
    maps = {48: {"width": 20, "height": 20}}
    warp_lists = {
        49: [_spec(48, 5, 6, 4)],
        50: [_spec(48, 5, 6, 6)],
    }
    with pytest.raises(ValueError):
        mw.compute_arrival_facings(warp_lists, maps)


def test_compute_arrival_facings_out_of_bounds_skipped() -> None:
    """An arrival coord outside the destination map's bounds gets no arrival
    warp_event of its own (`_resolve_all_warp_events` falls back to
    return-warp pairing for it instead), so there's no distinct landing tile
    to key a facing override on — skipped, not an error."""
    maps = {48: {"width": 10, "height": 10}}
    warp_lists = {49: [_spec(48, 99, 99, 4)]}
    assert mw.compute_arrival_facings(warp_lists, maps) == {}


def test_render_arrival_facing_script_empty_is_none() -> None:
    """No facings for a map -> None (the caller leaves the empty `mapscripts`
    stub alone rather than injecting an empty script)."""
    consts = mc.MapConstants(48, "MAP_X", "MAP_URANIUM_48", "LAYOUT_X", "MAPSEC_X", "X", "X")
    assert mw.render_arrival_facing_script(consts, []) is None


def test_render_arrival_facing_script_two_arrivals_golden() -> None:
    """Golden-ish shape for a two-arrival map: the mapscripts block wired to
    ON_WARP_INTO_MAP_TABLE, the getplayerxy readback, and one guarded
    turnobject per arrival — the first branch is `if`, later ones `elif`."""
    consts = mc.MapConstants(
        48, "MAP_MOKI_TOWN_PLAYERS_HOUSE_2F", "MAP_URANIUM_48", "LAYOUT_X", "MAPSEC_X",
        "MokiTownPlayersHouse2F", "Moki Town Player's House 2F",
    )
    facings = [
        mw.ArrivalFacing(5, 6, "DIR_WEST"),
        mw.ArrivalFacing(2, 3, "DIR_NORTH"),
    ]
    text = mw.render_arrival_facing_script(consts, facings)
    assert text is not None
    assert "mapscripts MokiTownPlayersHouse2F_MapScripts {" in text
    assert "MAP_SCRIPT_ON_WARP_INTO_MAP_TABLE [" in text
    assert f"{mw._FACING_GUARD_VAR}, 0: MokiTownPlayersHouse2F_OnWarpFacing" in text
    assert f"getplayerxy({mw._FACING_X_VAR}, {mw._FACING_Y_VAR})" in text

    # one turnobject per arrival, with the right facing constant
    assert text.count("turnobject(LOCALID_PLAYER,") == 2
    assert "turnobject(LOCALID_PLAYER, DIR_NORTH)" in text
    assert "turnobject(LOCALID_PLAYER, DIR_WEST)" in text

    # sorted (y, x) ascending -> (2, 3)/NORTH first, (5, 6)/WEST second; the
    # first guard is `if`, the second `elif`, each with the matching coords.
    if_idx = text.index(
        f"if (var({mw._FACING_X_VAR}) == 2 && var({mw._FACING_Y_VAR}) == 3)"
    )
    elif_idx = text.index(
        f"elif (var({mw._FACING_X_VAR}) == 5 && var({mw._FACING_Y_VAR}) == 6)"
    )
    assert if_idx < elif_idx
    assert text.count("    if (") == 1
    assert text.count("elif (") == 1


# --- compute_autorun_entries / render_map_scripts (findings §3.2 BUG B') -----

def test_compute_autorun_entries_guard_negates_higher_page() -> None:
    """A trigger-3 base page with a higher self-switch-gated page: the
    autorun guard is own-terms (none) AND the negation of the higher page's
    condition — `!flag(...)`."""
    event = _event(1, 0, 0, [_page(trigger=3), _page(cond=_self_cond("A"))])
    entries = mw.compute_autorun_entries([event], 50, None)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.event_id == 1 and entry.page_index == 0
    assert entry.page_label == "Map050_EV001_Page1"
    assert entry.guard == "!flag(FLAG_MAP050_EVENT001_SSA)"


def test_compute_autorun_entries_unconditional_solo_page() -> None:
    """A single-page trigger-3 event with no higher pages and no own
    condition: guard is "" (always eligible)."""
    event = _event(1, 0, 0, [_page(trigger=3)])
    entries = mw.compute_autorun_entries([event], 50, None)
    assert len(entries) == 1
    assert entries[0].guard == ""


def test_compute_autorun_entries_ungated_higher_page_skips() -> None:
    """A higher page with NO condition at all always wins page-selection, so
    the lower autorun page can never be active — skipped entirely, not
    emitted with an always-false guard."""
    event = _event(1, 0, 0, [_page(trigger=3), _page()])  # page2 unconditional
    entries = mw.compute_autorun_entries([event], 50, None)
    assert entries == []


def test_compute_autorun_entries_own_condition_combines_with_negation() -> None:
    """A gated autorun page (own condition true) with a higher self-switch
    page: guard = own && !higher."""
    reg = FlagRegistry()
    reg.propose_var(101, "VAR_QUEST_LOG")
    event = _event(
        4, 10, 7,
        [
            _page(cond=_var_cond(101, 1), trigger=3),  # page0: var101 >= 1, autorun
            _page(cond=_var_cond(101, 2)),              # page1: var101 >= 2
            _page(cond=_self_cond("A"), trigger=3),      # page2: self-switch A, autorun
            _page(cond=_self_cond("A")),                 # page3: self-switch A
        ],
    )
    entries = mw.compute_autorun_entries([event], 172, reg)
    by_page = {e.page_index: e for e in entries}
    # page0 (idx0): own (var>=1) && !page1(var>=2) && !page2(switch125...) &&
    # !page3(self A) — but page2's own trigger is autorun too, still counted
    # as a higher-page negation target regardless of its trigger.
    assert 0 in by_page
    g0 = by_page[0].guard
    assert "var(VAR_QUEST_LOG) >= 1" in g0
    assert "var(VAR_QUEST_LOG) < 2" in g0
    assert "!flag(FLAG_MAP172_EVENT004_SSA)" in g0
    # page2 (idx2): own (self A) && !page3(self A) — a real self-contradiction
    # (page3 repeats the same self-switch), i.e. never active; still computed
    # mechanically per the spec (not our job to detect tautological deadness).
    assert 2 in by_page
    assert by_page[2].guard == "flag(FLAG_MAP172_EVENT004_SSA) && !flag(FLAG_MAP172_EVENT004_SSA)"


def test_compute_autorun_entries_unresolvable_own_condition_fails_loud() -> None:
    """An autorun page's own condition needs the registry (a variable gate)
    but none is given — fail loud, never a silently-dropped story beat."""
    event = _event(1, 0, 0, [_page(cond=_var_cond(101, 1), trigger=3), _page()])
    with pytest.raises(ValueError):
        mw.compute_autorun_entries([event], 172, None)


def test_compute_autorun_entries_sorted_by_event_then_page() -> None:
    """Deterministic ordering: ascending (event_id, page_index), independent
    of the caller's list order."""
    ev9 = _event(9, 0, 0, [_page(trigger=3)])
    ev3 = _event(3, 0, 0, [_page(trigger=3)])
    entries = mw.compute_autorun_entries([ev9, ev3], 50, None)
    assert [e.event_id for e in entries] == [3, 9]


def test_render_onframe_script_golden() -> None:
    """Guarded entries get an `if`/`goto`; the unconditional entry (guard
    "") gets a bare `goto`; the script always ends with setvar(VAR_TEMP_C, 1)."""
    entries = [
        mw.AutorunEntry(1, 0, "Map050_EV001_Page1", "flag(FLAG_X)"),
        mw.AutorunEntry(2, 0, "Map050_EV002_Page1", ""),
    ]
    text = mw._render_onframe_script("MokiTown_OnFrame", entries)
    assert text.startswith("script MokiTown_OnFrame {")
    assert "if (flag(FLAG_X)) {" in text
    assert "        goto(Map050_EV001_Page1)" in text
    assert "    goto(Map050_EV002_Page1)" in text  # unconditional, no if-wrap
    assert f"setvar({mw._ON_FRAME_GUARD_VAR}, 1)" in text
    assert text.rstrip().endswith("}")


@pytest.mark.skipif(
    not poryscript.is_available(), reason="poryscript binary not installed"
)
def test_render_map_scripts_all_sections_compile() -> None:
    """All three sections together (ON_TRANSITION, ON_FRAME_TABLE,
    ON_WARP_INTO_MAP_TABLE) render as ONE mapscripts block and compile
    through the real poryscript binary (findings §3.2/§5, single-block
    constraint)."""
    consts = mc.MapConstants(
        32, "MAP_MOKI_TOWN", "MAP_URANIUM_32", "LAYOUT_X", "MAPSEC_X",
        "MokiTown", "Moki Town",
    )
    facings = [mw.ArrivalFacing(5, 6, "DIR_WEST")]
    frame_entries = [mw.AutorunEntry(74, 0, "Map032_EV074_Page1", "flag(FLAG_X)")]
    transition_lines = [
        "# EV016 Bambo",
        "setflag(FLAG_TEMP_11)",
        "if (var(VAR_QUEST_LOG) >= 1) {",
        "    clearflag(FLAG_TEMP_11)",
        "}",
    ]
    text = mw.render_map_scripts(consts, facings, frame_entries, transition_lines)
    assert text is not None
    assert text.count("mapscripts MokiTown_MapScripts {") == 1
    assert "MAP_SCRIPT_ON_TRANSITION {" in text
    assert "MAP_SCRIPT_ON_FRAME_TABLE [" in text
    assert "MAP_SCRIPT_ON_WARP_INTO_MAP_TABLE [" in text
    assert "script MokiTown_OnFrame {" in text
    assert "script MokiTown_OnWarpFacing {" in text
    result = poryscript.compile_script(text)
    assert result.ok, result.stderr


def test_render_map_scripts_empty_is_none() -> None:
    consts = mc.MapConstants(32, "MAP_X", "MAP_URANIUM_32", "LAYOUT_X", "MAPSEC_X", "X", "X")
    assert mw.render_map_scripts(consts, [], [], []) is None


def test_render_map_scripts_only_transition() -> None:
    """A map with hidden actors but no warp facing / autorun still gets a
    real mapscripts block with just ON_TRANSITION."""
    consts = mc.MapConstants(32, "MAP_X", "MAP_URANIUM_32", "LAYOUT_X", "MAPSEC_X", "X", "X")
    text = mw.render_map_scripts(consts, [], [], ["setflag(FLAG_TEMP_11)"])
    assert text is not None
    assert "MAP_SCRIPT_ON_TRANSITION {" in text
    assert "        setflag(FLAG_TEMP_11)" in text
    assert "MAP_SCRIPT_ON_FRAME_TABLE" not in text
    assert "MAP_SCRIPT_ON_WARP_INTO_MAP_TABLE" not in text


def test_map_json_schema() -> None:
    """to_json_dict matches the fork schema; map_type drives town/indoor booleans."""
    consts = mc.MapConstants(32, "MAP_MOKI_TOWN", "MAP_URANIUM_32", "LAYOUT_MOKI_TOWN",
                             "MAPSEC_MOKI_TOWN", "MokiTown", "Moki Town")
    town = mw.MapFile(consts, map_type="MAP_TYPE_TOWN").to_json_dict()
    for key in ("id", "name", "layout", "music", "region_map_section", "map_type",
                "object_events", "warp_events", "coord_events", "bg_events", "connections"):
        assert key in town
    assert town["id"] == "MAP_MOKI_TOWN" and town["allow_running"] is True
    indoor = mw.MapFile(consts, map_type="MAP_TYPE_INDOOR").to_json_dict()
    assert indoor["allow_running"] is False and indoor["show_map_name"] is False


def test_wire_encounters_none(tmp_path: Path) -> None:
    """No entry / missing file -> None (no encounter table)."""
    assert mw.wire_encounters(32, tmp_path / "absent.json") is None
    p = tmp_path / "we.json"
    p.write_text(json.dumps({"76": {"land": []}}), encoding="utf-8")
    assert mw.wire_encounters(32, p) is None
    assert mw.wire_encounters(76, p) == {"land": []}


_MAPS = Path("output/uranium-build/maps")
_METADATA = Path("output/uranium-build/intermediate/map_metadata.json")


_URANIUM_EVENT_OBJECTS_GEN = Path("engine/include/constants/uranium_event_objects.gen.h")


@pytest.mark.skipif(
    not (_MAPS / "Map049.json").exists() or not _METADATA.exists() or not _MAP_INFOS.exists()
    or not DEFAULT_NPC_GFX_MAP.exists() or not _URANIUM_EVENT_OBJECTS_GEN.exists(),
    reason="slice map data / npc gfx map / built engine gen header not generated",
)
def test_build_slice_maps_smoke(tmp_path: Path) -> None:
    """Real slice maps assemble: events placed, in-slice warps wired, out-of-slice
    dropped, walkable overrides cover the warp sources."""
    npc_gfx = load_npc_gfx_map(
        DEFAULT_NPC_GFX_MAP,
        [Path("engine/include/constants/event_objects.h"), _URANIUM_EVENT_OBJECTS_GEN],
    )
    reg = mc.build_map_constants(
        [32, 48, 49], map_infos_path=_MAP_INFOS, overrides_path=_OVERRIDES,
        # See test_build_slice_constants: None is safe here (git-HEAD read).
        fork_path=None, state_path=tmp_path / "mc.json",
    )
    # A seeded registry, matching how stage_slice_scripts.py actually calls
    # build_slice_maps: real Moki Town corpus data has autorun (trigger=3)
    # pages gated on switches (including the s:tsOff?/s:tsOn? per-event
    # temp-switch idiom, e.g. Map032 EV003 page1), and compute_autorun_entries
    # needs a live registry to resolve those guards — flag_registry=None here
    # would fail loud (findings §3.2, by design: no silent autorun drop).
    flag_reg = FlagRegistry()
    flag_reg.pre_seed(_PRESEED, _SWITCHES, _VARIABLES)
    overrides = mw.build_slice_maps(
        [32, 48, 49], maps_dir=_MAPS, registry=reg, metadata_path=_METADATA,
        out_dir=tmp_path / "maps", dispatcher_dir=tmp_path / "disp",
        npc_gfx=npc_gfx, route_registry=RouteRegistry(), flag_registry=flag_reg,
    )
    # Map049: spawn floor, two override cells. The stairs (12,3) is a plain
    # warp; the street door at (10,11) is a GATED door (EV002: page 0 refuses
    # with "say goodbye to Auntie first", page 1 transfers once switch 52 `Mum`
    # is set) that warps from inside its own script instead of via a
    # warp_event -- but it still needs the override so the player can step into
    # the doorway and trip the gate. See classify_event and
    # reference/findings/gated_door_collapse_2026-07-26.md.
    assert overrides[49] == {(10, 11), (12, 3)}
    map49 = json.loads((tmp_path / "maps" / "MokiTownPlayersHouse1F" / "map.json").read_text())
    assert map49["map_type"] == "MAP_TYPE_INDOOR"
    # The gate is live: a coord_event sits on the door tile running EV002's
    # dispatcher. Without this the player walks straight out (playtest B2).
    door_coords = [
        ce for ce in map49["coord_events"] if (ce["x"], ce["y"]) == (10, 11)
    ]
    assert len(door_coords) == 1, map49["coord_events"]
    assert "Map049_EV002" in door_coords[0]["script"]
    assert (10, 11) not in {(w["x"], w["y"]) for w in map49["warp_events"]}
    dests = {w["dest_map"] for w in map49["warp_events"]}
    assert dests == {"MAP_MOKI_TOWN", "MAP_MOKI_TOWN_PLAYERS_HOUSE_2F"}
    # no object_event points outside the slice maps' scripts
    assert all(o["script"].startswith("Map049_") for o in map49["object_events"])
    # Moki Town is a town and drops its out-of-slice building doors
    map32 = json.loads((tmp_path / "maps" / "MokiTown" / "map.json").read_text())
    assert map32["map_type"] == "MAP_TYPE_TOWN"
    assert {w["dest_map"] for w in map32["warp_events"]} == {"MAP_MOKI_TOWN_PLAYERS_HOUSE_1F"}


# --- 5.4 connections ---------------------------------------------------------

def test_connections_bidirectional() -> None:
    """A->B up implies B->A down with negated offset."""
    pytest.skip(_TODO)


def test_connections_no_dangling_map() -> None:
    """No emitted connection references a non-existent MAP_*."""
    pytest.skip(_TODO)


# --- 5.5 move_routes ---------------------------------------------------------

def test_move_route_census_parses() -> None:
    """Census tool reports per-map event count and target-class breakdown (player/self/other)."""
    pytest.skip("Phase 5 §5.5 — not yet implemented")


def test_move_route_player_only_translation() -> None:
    """A player-only 209 route translates to applymovement(OBJ_EVENT_ID_PLAYER, …)
    and compile-gates clean."""
    pytest.skip("Phase 5 §5.5 — not yet implemented")


def test_move_route_timing_conversion() -> None:
    """A wait command of N frames at RMXP 40fps converts to the nearest GBA 60fps delay value."""
    pytest.skip("Phase 5 §5.5 — not yet implemented")


def test_move_route_injection_idempotent() -> None:
    """Re-running the move-route post-pass on already-processed .pory output is idempotent."""
    pytest.skip("Phase 5 §5.5 — not yet implemented")


# --- 5.6 reachability --------------------------------------------------------

def test_reachability_blocked_exit_is_defect() -> None:
    """BFS on a synthetic map where an exit cell is walled off classifies it as a defect."""
    pytest.skip("Phase 5 §5.6 — not yet implemented")


def test_reachability_ledge_one_way() -> None:
    """A ledge edge allows forward traversal (approach->landing) but the reverse
    direction is unreachable."""
    pytest.skip("Phase 5 §5.6 — not yet implemented")


def test_reachability_water_is_hm_gated() -> None:
    """An exit reachable only through water tiles is classified HM-gated, not a defect."""
    pytest.skip("Phase 5 §5.6 — not yet implemented")


def test_reachability_puzzle_gated_routes_to_wiki_review() -> None:
    """An exit passable in optimistic mode but not pessimistic is flagged for
    wiki review, not auto-failed."""
    pytest.skip("Phase 5 §5.6 — not yet implemented")


def test_passages_oracle_diff_reports_disagreements() -> None:
    """Passages oracle diff reports every cell where emitted GBA collision
    disagrees with the RMXP source passages value."""
    pytest.skip("Phase 5 §5.6 — not yet implemented")
