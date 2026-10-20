"""Tests for id-remapped connections (design R): geometry, art keys, tables, gen header,
and the strip import inside build_slice_tilesets."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from rpg2gba.tileset_converter.connection_remap import (
    GEN_RELPATH,
    NUM_METATILES_TOTAL,
    RemapDirection,
    RemapTable,
    build_remap_table,
    check_both_directions,
    composite_key,
    remap_directions,
    render_remap_header,
    source_key,
    strip_cells,
    strip_depth,
    write_remap_header,
    write_stub,
)
from rpg2gba.tileset_converter.connections import parse_connections
from rpg2gba.tileset_converter.graphics.build_slice_tilesets import build_slice_tilesets
from rpg2gba.tileset_converter.graphics.emit import LAYER_COVERED, MetatileImage

from tests.test_build_slice_tilesets import _ZERO_TERRAIN_TAGS, _fake_fork, _StubRasterizer


# --- directions ------------------------------------------------------------------

def test_remap_directions_both_sides_pokeemerald_offsets() -> None:
    rows = parse_connections([[35, "N", 0, 40, "S", 15]])
    assert remap_directions(rows) == [
        RemapDirection(35, 40, "up", -15),
        RemapDirection(40, 35, "down", 15),
    ]


def test_check_both_directions_fails_loud_on_one_sided_seam() -> None:
    check_both_directions([RemapDirection(1, 2, "up", 0), RemapDirection(2, 1, "down", 0)])
    with pytest.raises(ValueError, match="reverse"):
        check_both_directions([RemapDirection(1, 2, "up", 0)])


# --- strip geometry (mirrors fieldmap.c Fill*Connection) --------------------------

def test_strip_north_route2_sees_nowtoch_bottom_rows_clipped() -> None:
    # 35 (42x57) sees 40 (79x74) above at offset -15: 40-cols 8..64 (cur x -7..49);
    # default N/S depth 5 -> 40's bottom 5 rows.
    cells = strip_cells(42, 57, 79, 74, "up", -15)
    xs = sorted({x for x, _ in cells})
    ys = sorted({y for _, y in cells})
    assert xs == list(range(8, 65))
    assert ys == list(range(69, 74))


def test_strip_south_nowtoch_sees_route2_top_rows() -> None:
    cells = strip_cells(79, 74, 42, 57, "down", 15)
    assert sorted({x for x, _ in cells}) == list(range(0, 42))
    assert sorted({y for _, y in cells}) == list(range(0, 5))


def test_strip_depth_is_per_axis() -> None:
    # field_camera.c: 5 cells visible up/down, 7 left/right.
    assert [strip_depth(d) for d in ("up", "down", "left", "right")] == [5, 5, 7, 7]
    with pytest.raises(ValueError):
        strip_depth("north")


def test_strip_depth_limits_rows() -> None:
    assert sorted({y for _, y in strip_cells(10, 10, 10, 10, "down", 0, depth=1)}) == [0]
    assert sorted({y for _, y in strip_cells(10, 10, 10, 10, "up", 0, depth=7)}) == list(range(3, 10))


def test_strip_west_and_east_columns() -> None:
    west = strip_cells(10, 10, 20, 30, "left", 0)  # default E/W depth 7
    assert sorted({x for x, _ in west}) == list(range(13, 20))
    # backup height 10+15=25, offset 0 -> pos 7, 7+30 >= 25 -> 18 rows
    assert sorted({y for _, y in west}) == list(range(0, 18))
    east = strip_cells(10, 10, 20, 30, "right", -10)
    assert sorted({x for x, _ in east}) == list(range(0, 7))
    # pos -3 -> start 3, count min(27, 25) = 25 -> rows 3..27
    assert sorted({y for _, y in east}) == list(range(3, 28))


def test_strip_no_overlap_is_empty_and_bad_args_fail() -> None:
    assert strip_cells(10, 10, 5, 5, "down", 40, depth=6) == []
    with pytest.raises(ValueError):
        strip_cells(10, 10, 5, 5, "north", 0)
    with pytest.raises(ValueError):
        strip_cells(10, 10, 5, 5, "down", 0, depth=8)


# --- art keys ----------------------------------------------------------------------

def _mt(bottom: np.ndarray, top: np.ndarray, behavior: int = 0) -> MetatileImage:
    return MetatileImage(bottom, top, LAYER_COVERED, behavior)


def test_source_key_ignores_rgb_under_transparent_pixels_and_behavior() -> None:
    a = np.zeros((16, 16, 4), np.uint8)
    b = a.copy()
    b[..., :3] = 77  # alpha still 0
    solid = np.full((16, 16, 4), 200, np.uint8)
    assert source_key(_mt(solid, a, 0)) == source_key(_mt(solid, b, 5))


def test_composite_key_matches_same_picture_split_across_layers() -> None:
    solid = np.full((16, 16, 4), 255, np.uint8)
    solid[..., 0] = 10
    empty = np.zeros((16, 16, 4), np.uint8)
    assert source_key(_mt(solid, empty)) != source_key(_mt(empty, solid))
    assert composite_key(_mt(solid, empty)) == composite_key(_mt(empty, solid))


# --- tables and header -------------------------------------------------------------

def test_build_remap_table_maps_given_ids_and_voids_the_rest() -> None:
    t = build_remap_table([3, 7], {3: 10, 7: 11, 900: 12}, void_id=99)
    assert len(t) == NUM_METATILES_TOTAL
    assert (t[3], t[7], t[900]) == (10, 11, 12)
    assert t[0] == t[8] == t[1023] == 99
    with pytest.raises(KeyError):
        build_remap_table([5], {3: 10}, void_id=0)


def test_stub_header_text(tmp_path: Path) -> None:
    path = write_stub(tmp_path)
    assert path == tmp_path / GEN_RELPATH
    assert path.read_text(encoding="utf-8") == (
        "// generated by rpg2gba — do not edit\n"
        "#define RPG2GBA_CONNECTION_REMAP_COUNT 0\n"
        "static const struct Rpg2gbaConnectionRemap sRpg2gbaConnectionRemaps[] = { {0} };\n"
    )


def test_real_header_text_and_idempotence(tmp_path: Path) -> None:
    table = list(range(NUM_METATILES_TOTAL))
    tables = [RemapTable(40, 35, table), RemapTable(35, 40, [0] * NUM_METATILES_TOTAL)]
    consts = {35: "MAP_ROUTE_02", 40: "MAP_NOWTOCH_CITY"}
    text = render_remap_header(tables, consts.__getitem__)
    assert text.startswith("// generated by rpg2gba — do not edit\n#define RPG2GBA_CONNECTION_REMAP_COUNT 2\n")
    assert "static const u16 sUraniumConnRemap_035_040[NUM_METATILES_TOTAL] = {" in text
    assert "    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,\n" in text
    assert text.index("sUraniumConnRemap_035_040[") < text.index("sUraniumConnRemap_040_035[")
    assert (
        "    { .mapGroup = MAP_GROUP(MAP_NOWTOCH_CITY), .mapNum = MAP_NUM(MAP_NOWTOCH_CITY), "
        ".connGroup = MAP_GROUP(MAP_ROUTE_02), .connNum = MAP_NUM(MAP_ROUTE_02), "
        ".table = sUraniumConnRemap_040_035 },\n"
    ) in text
    p1 = write_remap_header(tmp_path, tables, consts.__getitem__).read_text(encoding="utf-8")
    p2 = write_remap_header(tmp_path, tables, consts.__getitem__).read_text(encoding="utf-8")
    assert p1 == p2 == text
    with pytest.raises(ValueError):
        render_remap_header(tables, None)


# --- strip import inside build_slice_tilesets -------------------------------------

def _two_maps():
    # A (tileset 5): z0 = 400 401 / 402 403 ; B (tileset 6): z0 = 400 500 / 501 502.
    def m(ts, data):
        return {"tileset_id": ts, "width": 2, "height": 2,
                "tiles": {"xsize": 2, "ysize": 2, "zsize": 3, "data": data + [0] * 8}}
    return [(1, m(5, [400, 401, 402, 403])), (2, m(6, [400, 500, 501, 502]))]


def _build(tmp_path: Path):
    fork = _fake_fork(tmp_path)
    base = tmp_path / "tileset_map.json"
    base.write_text("{}", encoding="utf-8")
    overlay_out = tmp_path / "tileset_map.gen.json"
    captured: dict[str, list] = {}
    import rpg2gba.tileset_converter.graphics.build_slice_tilesets as bst

    real_emit = bst.emit_tileset

    def spy(mts, *a, **k):
        captured[a[2]] = list(mts)
        return real_emit(mts, *a, **k)

    bst.emit_tileset = spy
    try:
        # A's north edge meets B's south edge: B is above A.
        rows = parse_connections([[1, "N", 0, 2, "S", 0]])
        build_slice_tilesets(
            _two_maps(), {}, fork=fork, base_tile_map=base, overlay_out=overlay_out,
            rasterizer_for=lambda ts: _StubRasterizer(),
            priorities_for=lambda ts: [0] * 1000,
            passages_for=lambda ts: [0] * 1000,
            terrain_tags_for=lambda ts: _ZERO_TERRAIN_TAGS,
            tile_merge=False,
            remap_directions=remap_directions(rows),
            map_const_of={1: "MAP_A", 2: "MAP_B"}.__getitem__,
        )
    finally:
        bst.emit_tileset = real_emit
    overlay = json.loads(overlay_out.read_text(encoding="utf-8"))
    return fork, overlay, captured


def _id(overlay: dict, ts: int, tile: int) -> int:
    return overlay["tiles"][str(ts)][json.dumps([[0, tile]], separators=(",", ":"))]["metatile"]


def _tables(fork: Path) -> dict[str, list[int]]:
    text = (fork / GEN_RELPATH).read_text(encoding="utf-8")
    out = {}
    for name in ("sUraniumConnRemap_001_002", "sUraniumConnRemap_002_001"):
        body = text.split(f"{name}[NUM_METATILES_TOTAL] = {{\n", 1)[1].split("};", 1)[0]
        out[name] = [int(v) for v in body.replace("\n", " ").split(",") if v.strip()]
    return out


def test_strip_import_existing_match_import_and_void_default(tmp_path: Path) -> None:
    fork, ov, cap = _build(tmp_path)
    a, b = cap["gTileset_Uranium5"], cap["gTileset_Uranium6"]
    # A: 4 columns + void, then B's 500/501/502 imported (400 already source-identical).
    assert len(a) == 5 + 3
    assert len(b) == 5 + 3
    t = _tables(fork)
    ta, tb = t["sUraniumConnRemap_001_002"], t["sUraniumConnRemap_002_001"]
    assert len(ta) == len(tb) == NUM_METATILES_TOTAL
    # existing match: B's 400 -> A's own 400
    assert ta[_id(ov, 6, 400)] == _id(ov, 5, 400)
    # imported: B's 500 -> an appended id in A holding identical source art
    i500 = ta[_id(ov, 6, 500)]
    assert i500 >= 5 and source_key(a[i500]) == source_key(b[_id(ov, 6, 500)])
    # void default for an id B never uses
    void_a = ov["buckets"]["5"]["void"]
    assert ta[1000] == void_a


def test_strip_import_over_metatile_cap_fails_loud_with_numbers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rpg2gba.tileset_converter.graphics.build_slice_tilesets as bst

    # Each tileset is 5 metatiles + 3 imported = 8; a cap of 7 must trip the check.
    monkeypatch.setattr(bst, "NUM_METATILES_TOTAL", 7)
    with pytest.raises(
        ValueError,
        match=r"tileset [56]: 5 metatiles \+ 3 imported from map [12]'s strip = 8 > 7 cap",
    ):
        _build(tmp_path)
