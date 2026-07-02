"""Unit tests for the S8a graphics pre-pass (build_slice_tilesets).

Exercises column enumeration, two-layer priority split, overlay generation,
behaviour resolution, and engine fragment emission with a stub rasterizer +
synthetic maps + a fake fork tree — no real Uranium art or pokeemerald checkout
required.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np
from PIL import Image

from rpg2gba.tileset_converter.graphics.build_slice_tilesets import (
    _behavior_value,
    build_slice_tilesets,
    column_keys_for_maps,
)
from rpg2gba.tileset_converter.graphics.emit import MetatileImage, analyze_tileset_palettes


class _StubRasterizer:
    """Renders any tile_id to a solid 16x16 RGBA tile (id 0 -> transparent)."""

    def render(self, tile_id: int) -> Image.Image:
        if tile_id == 0:
            return Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        color = (tile_id % 256, (tile_id * 7) % 256, (tile_id * 13) % 256, 255)
        return Image.new("RGBA", (16, 16), color)


def _fake_fork(tmp_path: Path) -> Path:
    """A minimal fork tree: the dirs the pre-pass writes into + a behaviors enum."""
    fork = tmp_path / "fork"
    (fork / "src" / "data" / "tilesets").mkdir(parents=True)
    (fork / "include" / "constants").mkdir(parents=True)
    (fork / "include" / "constants" / "metatile_behaviors.h").write_text(
        "enum {\n    MB_NORMAL,\n    MB_FOO,\n    MB_NON_ANIMATED_DOOR,\n};\n",
        encoding="utf-8",
    )
    return fork


def _map(tileset_id: int) -> dict:
    """A 2x2, 3-layer map: four static tiles on layer 0, empty above."""
    return {
        "tileset_id": tileset_id,
        "width": 2,
        "height": 2,
        "tiles": {
            "xsize": 2,
            "ysize": 2,
            "zsize": 3,
            # layer-major: z0 = [400,401,402,403], z1/z2 empty
            "data": [400, 401, 402, 403, 0, 0, 0, 0, 0, 0, 0, 0],
        },
    }


def test_behavior_value(tmp_path: Path) -> None:
    fork = _fake_fork(tmp_path)
    assert _behavior_value(fork, "MB_NORMAL") == 0
    assert _behavior_value(fork, "MB_NON_ANIMATED_DOOR") == 2


class _BoundedRasterizer(_StubRasterizer):
    """Stub with an atlas bound, exercising the out-of-atlas garbage-tile filter."""

    def max_static_tile_id(self) -> int:
        return 500


def test_out_of_atlas_tiles_dropped(tmp_path: Path) -> None:
    """A column referencing a tile id past the atlas bound is dropped (resolves to
    void), not fatal — some Uranium maps carry garbage tile ids."""
    fork = _fake_fork(tmp_path)
    base = tmp_path / "tileset_map.json"
    base.write_text("{}", encoding="utf-8")
    overlay_out = tmp_path / "tileset_map.gen.json"
    # z0 = [400 (ok), 9999 (garbage > 500), 401 (ok), 402 (ok)].
    m = {
        "tileset_id": 5, "width": 2, "height": 2,
        "tiles": {"xsize": 2, "ysize": 2, "zsize": 3,
                  "data": [400, 9999, 401, 402, 0, 0, 0, 0, 0, 0, 0, 0]},
    }
    build_slice_tilesets(
        [(32, m)], {}, fork=fork, base_tile_map=base, overlay_out=overlay_out,
        rasterizer_for=lambda ts: _BoundedRasterizer(),
        priorities_for=lambda ts: [0] * 10000,
    )
    tiles = json.loads(overlay_out.read_text(encoding="utf-8"))["tiles"]["5"]
    keys = {json.dumps([[0, t]], separators=(",", ":")) for t in (400, 401, 402)}
    assert set(tiles) == keys  # the garbage (0,9999) column is absent
    assert json.dumps([[0, 9999]], separators=(",", ":")) not in tiles


def _run(tmp_path: Path) -> tuple[Path, Path, dict]:
    fork = _fake_fork(tmp_path)
    base = tmp_path / "tileset_map.json"
    base.write_text("{}", encoding="utf-8")
    overlay_out = tmp_path / "tileset_map.gen.json"

    # priorities: tile 401 has priority>0 -> rendered into the top layer only,
    # exercising the LAYER_NORMAL path; tiles 400/402/403 all stay on bottom.
    priors = [0] * 600
    priors[401] = 1

    results = build_slice_tilesets(
        [(32, _map(5))],
        {32: {(0, 0)}},  # warp at cell (0,0) -> column key ((0, 400),)
        fork=fork,
        base_tile_map=base,
        overlay_out=overlay_out,
        rasterizer_for=lambda ts: _StubRasterizer(),
        priorities_for=lambda ts: priors,
    )
    overlay = json.loads(overlay_out.read_text(encoding="utf-8"))
    return fork, overlay_out, {"results": results, "overlay": overlay}


def test_overlay_structure(tmp_path: Path) -> None:
    _, _, ctx = _run(tmp_path)
    overlay = ctx["overlay"]

    # tileset 5 registered with the deterministic Uranium names.
    assert overlay["tilesets"]["5"] == {
        "primary": "gTileset_Uranium5",
        "secondary": "gTileset_Uranium5B",
    }
    # Every column key has an explicit metatile entry; 4 distinct columns.
    tiles = overlay["tiles"]["5"]
    assert len(tiles) == 4
    # Keys are serialized column-key strings ([[z,t],...]), not plain tile ids.
    for k in tiles:
        parsed = json.loads(k)
        assert isinstance(parsed, list), f"expected list, got {parsed!r}"
        assert all(
            isinstance(pair, list) and len(pair) == 2 for pair in parsed
        ), f"each pair must be [z,t]; got {parsed!r}"
    # Metatile ids span 0..3 (ordered = sorted column keys -> 0-indexed).
    assert {e["metatile"] for e in tiles.values()} == {0, 1, 2, 3}
    # Void bucket points at metatile 4 (appended after the 4 column metatiles).
    assert overlay["buckets"]["5"]["void"] == 4
    assert overlay["buckets"]["5"]["passable"] == 4
    # Warp cell (0,0) -> column ((0,400),) gets a SEPARATE per-column door copy at
    # index 5 (after void), NOT the same entry as the plain column-key metatile for
    # (0,0); that entry (metatile 0) stays MB_NORMAL (behavior 0). Fallback is 6.
    col_400_key = json.dumps([[0, 400]], separators=(",", ":"))
    assert overlay["warps"]["5"] == {
        "tiles": {col_400_key: 5},
        "fallback": 6,
        "collision": 0,
        "elevation": 0,
    }
    # Confirm the column-key entry for cell (0,0) is metatile 0 (not the warp copy).
    assert tiles[col_400_key]["metatile"] == 0


def test_emitted_art_files(tmp_path: Path) -> None:
    fork, _, _ = _run(tmp_path)
    prim = fork / "data" / "tilesets" / "primary" / "uranium5"
    sec = fork / "data" / "tilesets" / "secondary" / "uranium5"
    for d in (prim, sec):
        assert (d / "tiles.png").is_file()
        assert (d / "metatiles.bin").is_file()
        assert (d / "metatile_attributes.bin").is_file()
        assert (d / "palettes" / "00.pal").is_file()
        assert (d / "palettes" / "15.pal").is_file()

    # 7 metatiles: 4 column + 1 void + 1 per-column door copy + 1 fallback door,
    # all in primary.
    # metatiles.bin:           7 metatiles * 8 u16 slots * 2 bytes = 112 bytes
    # metatile_attributes.bin: 7 metatiles * 1 u16 * 2 bytes       = 14 bytes
    assert (prim / "metatiles.bin").stat().st_size == 7 * 16
    assert (prim / "metatile_attributes.bin").stat().st_size == 7 * 2

    attrs = struct.unpack("<7H", (prim / "metatile_attributes.bin").read_bytes())

    # Metatile 5 (per-column door copy of column ((0,400),)) carries
    # MB_NON_ANIMATED_DOOR (=2); metatile 6 (fallback) does too.
    assert (attrs[5] & 0x00FF) == 2
    assert (attrs[6] & 0x00FF) == 2
    # Metatile 0 (column ((0,400),) normal entry) has behavior 0 (MB_NORMAL).
    assert (attrs[0] & 0x00FF) == 0

    # Metatile 1 maps to column ((0,401),), tile 401 has priority>0 -> top layer only.
    # layer_type = LAYER_NORMAL (0) -> bits 15-12 of attr = 0.
    assert (attrs[1] >> 12) & 0xF == 0  # LAYER_NORMAL
    # Metatile 0 maps to column ((0,400),), priority=0 -> bottom only.
    # layer_type = LAYER_COVERED (1) -> bits 15-12 = 1.
    assert (attrs[0] >> 12) & 0xF == 1  # LAYER_COVERED


def test_engine_fragments(tmp_path: Path) -> None:
    fork, _, _ = _run(tmp_path)
    graphics = (fork / "src" / "data" / "tilesets" / "uranium_graphics.gen.h").read_text(
        encoding="utf-8"
    )
    metatiles = (fork / "src" / "data" / "tilesets" / "uranium_metatiles.gen.h").read_text(
        encoding="utf-8"
    )
    structs = (fork / "src" / "data" / "tilesets" / "uranium_tilesets.gen.h").read_text(
        encoding="utf-8"
    )
    externs = (fork / "include" / "uranium_externs.gen.h").read_text(encoding="utf-8")

    assert (
        'gTilesetTiles_Uranium5[] = INCGFX_U32("data/tilesets/primary/uranium5/tiles.png"'
        ', ".4bpp")'
    ) in graphics
    assert "gTilesetPalettes_Uranium5B[][16]" in graphics
    assert (
        'gMetatiles_Uranium5[] = INCBIN_U16("data/tilesets/primary/uranium5/metatiles.bin")'
    ) in metatiles
    assert "const struct Tileset gTileset_Uranium5 =" in structs
    assert ".isSecondary = TRUE," in structs  # the secondary half
    assert "extern const struct Tileset gTileset_Uranium5;" in externs
    assert "extern const struct Tileset gTileset_Uranium5B;" in externs


# ---------------------------------------------------------------------------
# Fix #1 (walker_checkpoint2_findings.md): per-door-column warp metatiles.
# ---------------------------------------------------------------------------


def _read_metatile_entries(dir_: Path, n_metatiles: int) -> list[tuple[int, ...]]:
    """Unpack ``metatiles.bin`` into 8 raw u16 tile-entries per metatile."""
    raw = struct.unpack(f"<{n_metatiles * 8}H", (dir_ / "metatiles.bin").read_bytes())
    return [tuple(raw[i * 8 : i * 8 + 8]) for i in range(n_metatiles)]


def test_two_maps_two_door_columns_each_get_own_warp_art(tmp_path: Path) -> None:
    """Two maps sharing a tileset, each warping onto a DIFFERENT door column:
    build_slice_tilesets mints one door-behavior metatile PER column, and each
    door copy's tile-entries are byte-identical to the plain (MB_NORMAL) metatile
    for that same column — i.e. it carries that column's own real art, not some
    other column's or a generic canned tile."""
    fork = _fake_fork(tmp_path)
    base = tmp_path / "tileset_map.json"
    base.write_text("{}", encoding="utf-8")
    overlay_out = tmp_path / "tileset_map.gen.json"
    priors = [0] * 600

    map_a = _map(5)  # z0 = [400,401,402,403]; warp at (0,0) -> column ((0,400),)
    map_b = _map(5)  # same tiles; warp at (1,0) -> column ((0,401),)

    build_slice_tilesets(
        [(10, map_a), (20, map_b)],
        {10: {(0, 0)}, 20: {(1, 0)}},
        fork=fork,
        base_tile_map=base,
        overlay_out=overlay_out,
        rasterizer_for=lambda ts: _StubRasterizer(),
        priorities_for=lambda ts: priors,
    )

    overlay = json.loads(overlay_out.read_text(encoding="utf-8"))
    tiles = overlay["tiles"]["5"]
    warps = overlay["warps"]["5"]

    col_400 = json.dumps([[0, 400]], separators=(",", ":"))
    col_401 = json.dumps([[0, 401]], separators=(",", ":"))

    # Two distinct door metatiles, one per column, plus a fallback — none of them
    # collide with each other or with the plain column entries.
    assert set(warps["tiles"]) == {col_400, col_401}
    door_400_idx = warps["tiles"][col_400]
    door_401_idx = warps["tiles"][col_401]
    fallback_idx = warps["fallback"]
    plain_400_idx = tiles[col_400]["metatile"]
    plain_401_idx = tiles[col_401]["metatile"]
    assert len({door_400_idx, door_401_idx, fallback_idx, plain_400_idx, plain_401_idx}) == 5

    prim = fork / "data" / "tilesets" / "primary" / "uranium5"
    n_metatiles = max(door_400_idx, door_401_idx, fallback_idx, plain_400_idx, plain_401_idx) + 1
    entries = _read_metatile_entries(prim, n_metatiles)
    attrs = struct.unpack(
        f"<{n_metatiles}H", (prim / "metatile_attributes.bin").read_bytes()
    )

    # Each door copy's raw tile-entries (hence rendered art) match the PLAIN
    # metatile for the SAME column — not each other, not the fallback.
    assert entries[door_400_idx] == entries[plain_400_idx]
    assert entries[door_401_idx] == entries[plain_401_idx]
    assert entries[door_400_idx] != entries[door_401_idx]

    # Both door copies carry MB_NON_ANIMATED_DOOR (=2); the plain entries stay
    # MB_NORMAL (=0).
    assert (attrs[door_400_idx] & 0x00FF) == 2
    assert (attrs[door_401_idx] & 0x00FF) == 2
    assert (attrs[plain_400_idx] & 0x00FF) == 0
    assert (attrs[plain_401_idx] & 0x00FF) == 0


def test_warp_on_empty_cell_resolves_to_transparent_fallback(tmp_path: Path) -> None:
    """A warp sitting on an empty (all-layers-zero) cell has no door column to
    copy — build_slice_tilesets records no per-column entry for it, and
    convert_layout must fall back to the tileset's transparent door metatile."""
    fork = _fake_fork(tmp_path)
    base = tmp_path / "tileset_map.json"
    base.write_text("{}", encoding="utf-8")
    overlay_out = tmp_path / "tileset_map.gen.json"
    priors = [0] * 600

    m = _map(5)
    # Warp coord (1,1) is on cell (1,1); layer 0 has tile 403 there — replace the
    # map so (1,1) is genuinely empty across all layers.
    m["tiles"]["data"] = [400, 401, 402, 0, 0, 0, 0, 0, 0, 0, 0, 0]

    build_slice_tilesets(
        [(10, m)],
        {10: {(1, 1)}},  # empty cell
        fork=fork,
        base_tile_map=base,
        overlay_out=overlay_out,
        rasterizer_for=lambda ts: _StubRasterizer(),
        priorities_for=lambda ts: priors,
    )

    overlay = json.loads(overlay_out.read_text(encoding="utf-8"))
    warps = overlay["warps"]["5"]

    # No column key was collected for the empty warp cell.
    assert warps["tiles"] == {}
    # A fallback metatile was still minted so the warp_event fires.
    assert warps["fallback"] is not None

    prim = fork / "data" / "tilesets" / "primary" / "uranium5"
    attrs = struct.unpack(
        f"<{warps['fallback'] + 1}H", (prim / "metatile_attributes.bin").read_bytes()
    )
    assert (attrs[warps["fallback"]] & 0x00FF) == 2  # MB_NON_ANIMATED_DOOR


# ---------------------------------------------------------------------------
# Tests for source_tileset_of (synthetic per-map tileset ids)
# ---------------------------------------------------------------------------


def test_source_tileset_of_per_map_tilesets(tmp_path: Path) -> None:
    """Two maps share real tileset 5 but get distinct synthetic ids 1005/1006.

    build_slice_tilesets must:
      (a) emit two separate physical tilesets (one per synthetic id), and
      (b) record a top-level 'source_tilesets' mapping synth->real in the overlay.
    """
    fork = _fake_fork(tmp_path)
    base = tmp_path / "tileset_map.json"
    base.write_text("{}", encoding="utf-8")
    overlay_out = tmp_path / "tileset_map.gen.json"

    priors = [0] * 600

    # Two maps, both backed by real tileset 5, assigned synthetic ids 1005 and 1006.
    map_a = _map(1005)
    map_b = _map(1006)

    results = build_slice_tilesets(
        [(10, map_a), (20, map_b)],
        {},
        fork=fork,
        base_tile_map=base,
        overlay_out=overlay_out,
        rasterizer_for=lambda ts: _StubRasterizer(),
        priorities_for=lambda ts: priors,
        source_tileset_of=lambda synth: 5,
    )

    # (a) Two separate physical tilesets emitted — one per synthetic id.
    assert set(results.keys()) == {1005, 1006}

    overlay = json.loads(overlay_out.read_text(encoding="utf-8"))

    # (b) source_tilesets maps each synth id (string key) back to real id 5.
    assert "source_tilesets" in overlay
    assert overlay["source_tilesets"]["1005"] == 5
    assert overlay["source_tilesets"]["1006"] == 5


# ---------------------------------------------------------------------------
# Tests for column_keys_for_maps
# ---------------------------------------------------------------------------


def test_column_keys_for_maps_sorted_unique_nonempty() -> None:
    """column_keys_for_maps returns sorted, deduplicated, non-empty column keys."""
    # Two maps with identical tile data: 4 unique column keys from 8 total cells.
    map1 = _map(5)
    map2 = _map(5)
    ordered = column_keys_for_maps([(1, map1), (2, map2)])

    # Exactly 4 distinct keys (tiles 400-403 on z=0, one per cell).
    assert len(ordered) == 4

    # Sorted
    assert ordered == sorted(ordered)

    # All entries non-empty
    assert all(k for k in ordered)

    # Each key is a tuple of (z, tile_id) pairs
    for k in ordered:
        assert isinstance(k, tuple)
        assert all(isinstance(pair, tuple) and len(pair) == 2 for pair in k)


# ---------------------------------------------------------------------------
# Tests for analyze_tileset_palettes
# ---------------------------------------------------------------------------


def _solid_rgba(r: int, g: int, b: int) -> np.ndarray:
    """Return a 16×16 RGBA uint8 array filled with a single opaque colour."""
    arr = np.zeros((16, 16, 4), dtype=np.uint8)
    arr[..., 0] = r
    arr[..., 1] = g
    arr[..., 2] = b
    arr[..., 3] = 255
    return arr


def _transparent_rgba() -> np.ndarray:
    """Return an all-transparent 16×16 RGBA uint8 array."""
    return np.zeros((16, 16, 4), dtype=np.uint8)


def test_analyze_tileset_palettes_structure() -> None:
    """analyze_tileset_palettes returns correct structure without writing files."""
    # mt1: opaque bottom and top with distinct colours.
    mt1 = MetatileImage(
        bottom=_solid_rgba(200, 50, 50),
        top=_solid_rgba(50, 200, 50),
    )
    # mt2: opaque bottom, fully-transparent top.
    mt2 = MetatileImage(
        bottom=_solid_rgba(50, 50, 200),
        top=_transparent_rgba(),
    )

    result = analyze_tileset_palettes([mt1, mt2])

    # Output length matches input.
    assert len(result.metatiles) == 2

    # Each MetatilePalette has exactly 8 quadrant slots.
    for mt_pal in result.metatiles:
        assert len(mt_pal.quadrants) == 8

    # Every palette_index is either -1 or a valid index into result.palettes.
    for mt_pal in result.metatiles:
        for qp in mt_pal.quadrants:
            assert qp.palette_index == -1 or 0 <= qp.palette_index < len(result.palettes)

    # color_changes entries are ((int,int,int), (int,int,int)).
    for mt_pal in result.metatiles:
        for qp in mt_pal.quadrants:
            for orig, final in qp.color_changes:
                assert len(orig) == 3 and all(isinstance(c, int) for c in orig)
                assert len(final) == 3 and all(isinstance(c, int) for c in final)

    # mt2 top layer (slots 4-7) is all-transparent -> palette_index=-1, color_changes=[].
    for slot_idx in range(4, 8):
        qp = result.metatiles[1].quadrants[slot_idx]
        assert qp.palette_index == -1, f"slot {slot_idx} should be transparent"
        assert qp.color_changes == [], f"slot {slot_idx} should have no color changes"

    # palettes entries are lists of (int, int, int) tuples.
    for pal in result.palettes:
        assert isinstance(pal, list)
        for color in pal:
            assert len(color) == 3 and all(isinstance(c, int) for c in color)
