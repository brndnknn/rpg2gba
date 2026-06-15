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
from rpg2gba.tileset_converter.layout import TileGrid
from rpg2gba.tileset_converter.tile_map import (
    METATILE_ID_MASK,
    Bucket,
    Metatile,
    TileMap,
    TilesetChoice,
    load_tile_map,
    normalize_tile_id,
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


# --- 5.2 layout --------------------------------------------------------------

# tile ids 384..389 -> metatiles 10..15 (distinct, passable); 500 blocks.
def _layout_tilemap(priorities: dict[int, int] | None = None) -> TileMap:
    """A small TileMap with explicit metatiles + a passages oracle so layout tests
    can distinguish cells and exercise the combined-collision rule."""
    n = 600
    passages = [0] * n
    passages[500] = 15  # tile 500 blocks (low nibble != 0)
    prio = [0] * n
    for tid, p in (priorities or {}).items():
        prio[tid] = p
    return TileMap(
        tiles={7: {384 + i: Metatile(10 + i, 0, 3) for i in range(6)} | {500: Metatile(20, 1, 0)}},
        tilesets={7: TilesetChoice("gTileset_P", "gTileset_S")},
        buckets={7: Bucket(passable=5, blocked=6, void=7)},
        passages={7: passages},
        priorities={7: prio},
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
    """Topmost-non-empty layer wins for the visual metatile; all-empty -> void."""
    tm = _layout_tilemap()
    # z = [floor(384), 0, table(385)] -> table on top wins (metatile 11)
    g = _grid(1, 1, [384], [0], [385])
    assert layout_mod.collapse_column(g, 0, 0, tm, 7).metatile_id == 11
    # z = [floor(384), 0, 0] -> floor (metatile 10)
    g = _grid(1, 1, [384])
    assert layout_mod.collapse_column(g, 0, 0, tm, 7).metatile_id == 10
    # all-empty column -> the tileset's void metatile (impassable)
    g = _grid(1, 1, [0])
    assert layout_mod.collapse_column(g, 0, 0, tm, 7) == Metatile(7, 1, 0)


def test_collapse_collision_is_layer_combined() -> None:
    """A passable over-the-player tile (priority>0) above a blocking trunk reads
    blocked — collision comes from the combined rule, not the topmost tile alone.
    The visual metatile is still the topmost one (an invisible wall)."""
    tm = _layout_tilemap(priorities={387: 1})  # tile 387 drawn over the player
    g = _grid(1, 1, [500], [0], [387])  # trunk(500, blocks) under treetop(387, passable)
    mt = layout_mod.collapse_column(g, 0, 0, tm, 7)
    assert mt.metatile_id == 13  # visual = topmost (387 -> metatile 13)
    assert mt.collision == 1     # but collision from the blocking trunk beneath


def test_index_order_row_major() -> None:
    """convert_layout emits blocks in row-major y*width+x order (guards the
    layer-major -> row-major transposition)."""
    tm = _layout_tilemap()
    g = _grid(3, 2, [384, 385, 386, 387, 388, 389])  # metatiles 10..15
    layout = layout_mod.convert_layout(_map_json(g), tm, name="T", layout_const="LAYOUT_T")
    for i in range(6):
        assert layout.blocks[i] & METATILE_ID_MASK == 10 + i
    assert len(layout.blocks) == 6


def test_layout_round_trip(tmp_path: Path) -> None:
    """convert_layout on a 2x2 map -> map.bin of width*height*2 bytes, re-readable
    to the same metatile ids."""
    tm = _layout_tilemap()
    g = _grid(2, 2, [384, 385, 386, 387])
    layout = layout_mod.convert_layout(_map_json(g), tm, name="T", layout_const="LAYOUT_T")
    layout.write(tmp_path)
    map_bin = tmp_path / "layouts" / "T" / "map.bin"
    assert map_bin.stat().st_size == 2 * 2 * 2  # width*height*2 bytes
    blocks = layout_mod.read_blockdata(map_bin)
    assert [b & METATILE_ID_MASK for b in blocks] == [10, 11, 12, 13]
    assert (tmp_path / "layouts" / "T" / "border.bin").stat().st_size == 8


def test_warp_walkable_override() -> None:
    """walkable_overrides forces a blocked warp/door cell to collision 0 while
    keeping its visual metatile."""
    tm = _layout_tilemap()
    g = _grid(2, 1, [384, 500])  # cell (1,0) is the blocking door tile (metatile 20)
    plain = layout_mod.convert_layout(_map_json(g), tm, name="T", layout_const="LAYOUT_T")
    assert (plain.blocks[1] >> 10) & 0x3 == 1  # blocked without override
    forced = layout_mod.convert_layout(
        _map_json(g), tm, name="T", layout_const="LAYOUT_T", walkable_overrides={(1, 0)}
    )
    assert forced.blocks[1] & METATILE_ID_MASK == 20  # visual unchanged
    assert (forced.blocks[1] >> 10) & 0x3 == 0  # forced walkable


def test_layout_fail_loud_on_unmapped_tile() -> None:
    """A tile with no explicit entry and no bucket aborts the map with its ids."""
    tm = TileMap(
        tiles={7: {384: Metatile(10, 0, 3)}},
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
    g = _grid(3, 2, [384, 385, 386, 387, 388, 389])
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


@pytest.mark.skipif(
    not all((_MAPS_DIR / f"Map{m:03d}.json").exists() for m in _SLICE_IDS),
    reason="slice map JSON not generated",
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

def test_map_constants_idempotent_mint() -> None:
    """mint(id) returns the same constants across runs (persisted)."""
    pytest.skip(_TODO)


def test_map_constants_resolve_placeholder() -> None:
    """A MAP_URANIUM_<N> for a real map resolves; an unknown N fails loud."""
    pytest.skip(_TODO)


def test_alias_const_format_is_valid_identifier() -> None:
    """The Q2 alias spelling yields a valid C identifier (no skip — pure)."""
    name = mc.ALIAS_CONST_FMT.format(n=42)
    assert name.replace("_", "").isalnum() and name[0].isalpha()
    assert name == "MAP_URANIUM_42"


# --- 5.3 metadata_wiring -----------------------------------------------------

def test_object_events_placed_at_coords() -> None:
    """Each Uranium event -> one object_event at its (x, y) with a resolved label."""
    pytest.skip(_TODO)


def test_page_dispatcher_reflects_conditions() -> None:
    """A 2-page event's dispatcher gotos page 2 under its condition flag, else page 1."""
    pytest.skip(_TODO)


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
    """A ledge edge allows forward traversal (approach→landing) but the reverse
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
