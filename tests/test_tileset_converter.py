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

from rpg2gba.tileset_converter import layout as layout_mod
from rpg2gba.tileset_converter import map_constants as mc
from rpg2gba.tileset_converter import metadata_wiring as mw
from rpg2gba.tileset_converter.layout import TileGrid, column_key
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
        "19": {"passages": _passages([(48, 96)]), "priorities": _passages([])},
        "22": {"passages": _passages([(48, 96)]), "priorities": _passages([])},
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
) -> dict:
    return {
        "trigger": trigger,
        "condition": cond or {},
        "graphic": {"character_name": name, "opacity": opacity, "direction": direction},
        "move_type": move_type,
        "list": cmds or [],
    }


def _event(eid: int, x: int, y: int, pages: list[dict]) -> dict:
    return {"id": eid, "name": f"E{eid}", "x": x, "y": y, "pages": pages}


def _self_cond(letter: str) -> dict:
    return {"self_switch_valid": True, "self_switch_ch": letter}


def _sw_cond(switch_id: int) -> dict:
    return {"switch1_valid": True, "switch1_id": switch_id}


def _transfer(dest_uid: int, x: int, y: int) -> dict:
    return {"code": 201, "indent": 0, "parameters": [0, dest_uid, x, y, 2, 1]}


def _npc_gfx_fixture() -> dict[str, str]:
    """A minimal character_name -> OBJ_EVENT_GFX_* fixture (mirrors the shape
    `npc_gfx.load_npc_gfx_map` returns; see tests/test_npc_gfx.py for the loader
    itself)."""
    return {
        "HGSS_000": "OBJ_EVENT_GFX_URANIUM_HGSS_000",
        "HGSS_005": "OBJ_EVENT_GFX_URANIUM_HGSS_005",
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


def test_page_dispatcher_deferred_on_global() -> None:
    """A global switch/var page gate defers (None); single-page also None."""
    consts = mc.MapConstants(49, "MAP_X", "MAP_URANIUM_49", "LAYOUT_X", "MAPSEC_X", "X", "X")
    global_gated = _event(1, 0, 0, [_page(), _page(cond=_sw_cond(125))])
    assert mw.build_page_dispatcher(global_gated, consts) is None
    assert mw.build_page_dispatcher(_event(2, 0, 0, [_page()]), consts) is None


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


@pytest.mark.skipif(
    not (_MAPS / "Map049.json").exists() or not _METADATA.exists() or not _MAP_INFOS.exists(),
    reason="slice map data not generated",
)
def test_build_slice_maps_smoke(tmp_path: Path) -> None:
    """Real slice maps assemble: events placed, in-slice warps wired, out-of-slice
    dropped, walkable overrides cover the warp sources."""
    reg = mc.build_map_constants(
        [32, 48, 49], map_infos_path=_MAP_INFOS, overrides_path=_OVERRIDES,
        fork_path=None, state_path=tmp_path / "mc.json",
    )
    overrides = mw.build_slice_maps(
        [32, 48, 49], maps_dir=_MAPS, registry=reg, metadata_path=_METADATA,
        out_dir=tmp_path / "maps", dispatcher_dir=tmp_path / "disp",
    )
    # Map049: spawn floor, two in-slice warps (street door + stairs)
    assert overrides[49] == {(10, 11), (12, 3)}
    map49 = json.loads((tmp_path / "maps" / "MokiTownPlayersHouse1F" / "map.json").read_text())
    assert map49["map_type"] == "MAP_TYPE_INDOOR"
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
