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


def test_alias_const_format_is_valid_identifier() -> None:
    """The Q2 alias spelling yields a valid C identifier (no skip — pure)."""
    name = mc.ALIAS_CONST_FMT.format(n=42)
    assert name.replace("_", "").isalnum() and name[0].isalpha()
    assert name == "MAP_URANIUM_42"


# --- 5.3 metadata_wiring -----------------------------------------------------

def _page(trigger: int = 0, cond: dict | None = None, cmds: list | None = None) -> dict:
    return {
        "trigger": trigger,
        "condition": cond or {},
        "graphic": {"character_name": ""},
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
    """Each non-warp event -> one object_event at its (x, y) with the default gfx;
    single-page -> a page label, self-switch multi-page -> a dispatcher label."""
    consts = mc.MapConstantRegistry(Path("x")).mint(49, "Moki Town Player's House 1F")
    map_json = {
        "map_id": 49,
        "events": [
            _event(1, 4, 4, [_page()]),  # single page
            _event(7, 9, 3, [_page(), _page(cond=_self_cond("A"))]),  # self-switch -> dispatcher
            _event(2, 10, 11, [_page(trigger=1, cmds=[_transfer(32, 28, 31)])]),  # warp, excluded
        ],
    }
    objs, dispatchers = mw.build_object_events(map_json, consts, _SLICE)
    assert len(objs) == 2  # the warp door is not an object_event
    by_xy = {(o.x, o.y): o for o in objs}
    assert by_xy[(4, 4)].script == "Map049_EV001_Page1"
    assert by_xy[(4, 4)].graphics_id == mw.DEFAULT_GFX
    assert by_xy[(9, 3)].script == "Map049_EV007_Dispatch"
    assert len(dispatchers) == 1


def test_build_object_events_stubs_bodyless_event() -> None:
    """With pory_labels (post-S6), an event S6 left bodyless — a command-less
    standing NPC — is wired as a static object (script "0x0"), not a dangling page
    label; an event with a converted body keeps its page label."""
    consts = mc.MapConstantRegistry(Path("x")).mint(49, "Moki Town Player's House 1F")
    map_json = {
        "map_id": 49,
        "events": [
            _event(1, 4, 4, [_page()]),   # converted -> has a body
            _event(19, 6, 6, [_page()]),  # command-less NPC -> no body
        ],
    }
    labels = {"Map049_EV001_Page1"}  # only EV001 was converted
    objs, dispatchers = mw.build_object_events(map_json, consts, _SLICE, pory_labels=labels)
    by_xy = {(o.x, o.y): o for o in objs}
    assert by_xy[(4, 4)].script == "Map049_EV001_Page1"
    assert by_xy[(6, 6)].script == mw.NO_SCRIPT  # static object, no dangling ref
    assert dispatchers == []


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


def test_warp_pairing() -> None:
    """dest_warp_id points at the destination's return warp; warp-source coords are
    returned as walkable overrides."""
    reg = mc.MapConstantRegistry(Path("x"))
    reg.mint(49, "Moki Town Player's House 1F")
    reg.mint(48, "Moki Town Player's House 2F")
    map49 = {"map_id": 49, "events": [_event(3, 12, 3, [_page(1, cmds=[_transfer(48, 4, 3)])])]}
    map48 = {"map_id": 48, "events": [_event(2, 3, 3, [_page(1, cmds=[_transfer(49, 11, 3)])])]}
    warp_lists = {
        49: [mw.classify_map_events(map49, {48, 49})[1][0][1]],
        48: [mw.classify_map_events(map48, {48, 49})[1][0][1]],
    }
    warps49, overrides49 = mw.build_warp_events(map49, 49, {48, 49}, reg, warp_lists)
    assert warps49[0].dest_map == "MAP_MOKI_TOWN_PLAYERS_HOUSE_2F"
    assert warps49[0].dest_warp_id == 0  # 48's only warp returns to 49
    assert overrides49 == {(12, 3)}


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
