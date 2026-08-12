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
import pytest
from PIL import Image

from rpg2gba.tileset_converter.graphics.build_slice_tilesets import (
    MAX_COLUMN_FRAMES,
    _behavior_value,
    _render_column,
    build_slice_tilesets,
    column_keys_for_maps,
    column_n_frames,
)
from rpg2gba.tileset_converter.graphics.emit import (
    LAYER_COVERED,
    LAYER_NORMAL,
    MetatileImage,
    analyze_tileset_palettes,
)


class _StubRasterizer:
    """Renders any tile_id to a solid 16x16 RGBA tile (id 0 -> transparent)."""

    def render(self, tile_id: int) -> Image.Image:
        if tile_id == 0:
            return Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        color = (tile_id % 256, (tile_id * 7) % 256, (tile_id * 13) % 256, 255)
        return Image.new("RGBA", (16, 16), color)


def _fake_fork(tmp_path: Path) -> Path:
    """A minimal fork tree: the dirs the pre-pass writes into + a behaviors enum.

    Includes every MB_* name referenced by reference/terrain_tag_map.json (plus the
    original MB_FOO/MB_NON_ANIMATED_DOOR pair, kept first so test_behavior_value's
    numeric assertions stay unchanged) so the default terrain_tag_table load in
    build_slice_tilesets succeeds against this fake fork."""
    fork = tmp_path / "fork"
    (fork / "src" / "data" / "tilesets").mkdir(parents=True)
    (fork / "include" / "constants").mkdir(parents=True)
    (fork / "include" / "constants" / "metatile_behaviors.h").write_text(
        "enum {\n"
        "    MB_NORMAL,\n"
        "    MB_FOO,\n"
        "    MB_NON_ANIMATED_DOOR,\n"
        "    MB_TALL_GRASS,\n"
        "    MB_SAND,\n"
        "    MB_DEEP_WATER,\n"
        "    MB_POND_WATER,\n"
        "    MB_OCEAN_WATER,\n"
        "    MB_WATERFALL,\n"
        "    MB_LONG_GRASS,\n"
        "    MB_SEAWEED,\n"
        "    MB_ICE,\n"
        "    MB_ASHGRASS,\n"
        "    MB_JUMP_NORTH,\n"
        "    MB_JUMP_SOUTH,\n"
        "    MB_JUMP_EAST,\n"
        "    MB_JUMP_WEST,\n"
        "    MB_SIDEWAYS_STAIRS_RIGHT_SIDE,\n"
        "    MB_SIDEWAYS_STAIRS_LEFT_SIDE,\n"
        "};\n",
        encoding="utf-8",
    )
    return fork


_ZERO_TERRAIN_TAGS = [0] * 10000


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
        terrain_tags_for=lambda ts: _ZERO_TERRAIN_TAGS,
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

    # priorities: tile 401 has priority==1 -> rendered into the top layer only,
    # exercising the p==1 tier; tiles 400/402/403 all stay on bottom. Column
    # ((0,401),) is tile 401 ALONE (no base tile beneath it — see `_map`), and
    # `passages` leaves it fully passable -> column_blocked reads passable ->
    # LAYER_NORMAL (re-pinned 2026-08-12: a passable p==1 column is the
    # stand-on-canopy case, see _render_column docstring).
    priors = [0] * 600
    priors[401] = 1
    passages = [0] * 600

    results = build_slice_tilesets(
        [(32, _map(5))],
        {32: {(0, 0)}},  # warp at cell (0,0) -> column key ((0, 400),)
        fork=fork,
        base_tile_map=base,
        overlay_out=overlay_out,
        rasterizer_for=lambda ts: _StubRasterizer(),
        priorities_for=lambda ts: priors,
        passages_for=lambda ts: passages,
        terrain_tags_for=lambda ts: _ZERO_TERRAIN_TAGS,
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

    # Metatile 1 maps to column ((0,401),), tile 401 alone (no base tile), priority
    # ==1, passages all-passable -> column_blocked reads passable -> LAYER_NORMAL
    # (the stand-on-canopy case; see _render_column docstring).
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
    assert ".callback = NULL," in structs  # no animated tiles in this fixture
    assert "extern const struct Tileset gTileset_Uranium5;" in externs
    assert "extern const struct Tileset gTileset_Uranium5B;" in externs

    # No animated tilesets staged -> uranium_anims.gen.h is the empty-body stub
    # (still written, so the engine's unconditional #include compiles).
    anims = (fork / "src" / "data" / "tilesets" / "uranium_anims.gen.h").read_text(
        encoding="utf-8"
    )
    assert "InitTilesetAnim_Uranium5" not in anims


def test_engine_fragments_with_animated_effect(tmp_path: Path) -> None:
    """A tileset whose column keys include a 3-frame animated autotile: the
    PRIMARY struct's .callback wires to InitTilesetAnim_Uranium5, forward-declared
    in uranium_tilesets.gen.h, and uranium_anims.gen.h carries the frame table,
    queue fn, dispatcher, and install fn."""
    fork = _fake_fork(tmp_path)
    base = tmp_path / "tileset_map.json"
    base.write_text("{}", encoding="utf-8")
    overlay_out = tmp_path / "tileset_map.gen.json"
    priors = [0] * 600

    # z0 = [400 (static), 48 (animated, 3 frames), 401 (static), 402 (static)].
    m = {
        "tileset_id": 5, "width": 2, "height": 2,
        "tiles": {"xsize": 2, "ysize": 2, "zsize": 3,
                  "data": [400, 48, 401, 402, 0, 0, 0, 0, 0, 0, 0, 0]},
    }

    build_slice_tilesets(
        [(32, m)], {}, fork=fork, base_tile_map=base, overlay_out=overlay_out,
        rasterizer_for=lambda ts: _AnimatedStubRasterizer({48: 3}),
        priorities_for=lambda ts: priors,
        terrain_tags_for=lambda ts: _ZERO_TERRAIN_TAGS,
    )

    structs = (fork / "src" / "data" / "tilesets" / "uranium_tilesets.gen.h").read_text(
        encoding="utf-8"
    )
    assert "void InitTilesetAnim_Uranium5(void);" in structs
    assert ".callback = InitTilesetAnim_Uranium5," in structs

    anims = (fork / "src" / "data" / "tilesets" / "uranium_anims.gen.h").read_text(
        encoding="utf-8"
    )
    assert 'INCGFX_U16("data/tilesets/primary/uranium5/anim/anim3/f00.png", ".4bpp")' in anims
    assert "static void QueueAnimTiles_Uranium5_Anim3(u16 f)" in anims
    assert "AppendTilesetAnimToBuffer(" in anims
    assert "static void TilesetAnim_Uranium5(u16 timer)" in anims
    assert "void InitTilesetAnim_Uranium5(void)" in anims
    assert "sPrimaryTilesetAnimCallback = TilesetAnim_Uranium5;" in anims


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
        terrain_tags_for=lambda ts: _ZERO_TERRAIN_TAGS,
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
        terrain_tags_for=lambda ts: _ZERO_TERRAIN_TAGS,
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
        terrain_tags_for=lambda ts: _ZERO_TERRAIN_TAGS,
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
# Tests for _render_column (tiered priority split)
# ---------------------------------------------------------------------------


def _stub_color(tile_id: int) -> tuple[int, int, int, int]:
    """The exact solid RGBA color _StubRasterizer.render() produces for tile_id."""
    return (tile_id % 256, (tile_id * 7) % 256, (tile_id * 13) % 256, 255)


def _priors(overrides: dict[int, int]) -> list[int]:
    p = [0] * 600
    for tid, val in overrides.items():
        p[tid] = val
    return p


def test_render_column_p0_only_stays_bottom_covered() -> None:
    """A column with only priority-0 tiles: unchanged behavior — everything on
    BOTTOM, TOP empty, LAYER_COVERED."""
    key = ((0, 400),)
    mt = _render_column(key, _StubRasterizer(), _priors({}))
    assert mt.layer_type == LAYER_COVERED
    assert tuple(mt.bottom[0, 0]) == _stub_color(400)
    assert mt.top[..., 3].max() == 0  # top fully transparent


def test_render_column_p1_over_passable_base_normal_top() -> None:
    """A p==1 overlay tile over a PASSABLE base tile (passage 0, priority 0) —
    the two-cell-tall tree/hedge canopy-over-trunk case: the player is meant to
    walk BEHIND the canopy -> LAYER_NORMAL (re-pinned 2026-08-12 from the old
    flat-tiered rule, which put every p==1 column in LAYER_COVERED regardless of
    passability and drew the player on top of tree canopies). p1 tile still
    lands in the TOP slot (`top_min` stays 1 in both p==1 cases)."""
    key = ((0, 400), (1, 401))
    priorities = _priors({401: 1})
    passages = _priors({})  # all passable, including 400 and 401
    mt = _render_column(key, _StubRasterizer(), priorities, passages)
    assert mt.layer_type == LAYER_NORMAL
    assert tuple(mt.top[0, 0]) == _stub_color(401)
    assert tuple(mt.bottom[0, 0]) == _stub_color(400)


def test_render_column_p1_over_blocking_base_covered_top() -> None:
    """A p==1 overlay tile over a BLOCKING base tile (passage 0x0F) — a solid
    cliff/hedge-lip only ever approached from the row south of it: stays
    LAYER_COVERED (protects that row's player's head — the fix this tier
    originally shipped for). p1 tile still lands in the TOP slot."""
    key = ((0, 400), (1, 401))
    priorities = _priors({401: 1})
    passages = _priors({400: 0x0F})
    mt = _render_column(key, _StubRasterizer(), priorities, passages)
    assert mt.layer_type == LAYER_COVERED
    assert tuple(mt.top[0, 0]) == _stub_color(401)
    assert tuple(mt.bottom[0, 0]) == _stub_color(400)


def test_render_column_p2_alone_normal_top() -> None:
    """A single p>=2 canopy tile: LAYER_NORMAL, overlay pixels in the TOP slot
    (BG1: always over sprites)."""
    key = ((0, 402),)
    mt = _render_column(key, _StubRasterizer(), _priors({402: 2}))
    assert mt.layer_type == LAYER_NORMAL
    assert tuple(mt.top[0, 0]) == _stub_color(402)
    assert mt.bottom[..., 3].max() == 0


def test_render_column_mixed_ground_lip_canopy() -> None:
    """Mixed column: ground (p0, z0) + lip (p1, z1) + canopy (p2, z2).

    p2 goes to TOP alone -> LAYER_NORMAL. p0 and p1 both go to BOTTOM,
    composited in z order (z1 last, so its opaque pixels are what's visible —
    proves the z-ascending iteration order routed both into the same slot and
    composited z1 over z0, not the reverse)."""
    key = ((0, 500), (1, 501), (2, 502))
    priorities = _priors({500: 0, 501: 1, 502: 2})
    mt = _render_column(key, _StubRasterizer(), priorities)
    assert mt.layer_type == LAYER_NORMAL
    assert tuple(mt.top[0, 0]) == _stub_color(502)
    assert tuple(mt.bottom[0, 0]) == _stub_color(501)  # z1 composited over z0


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


# ---------------------------------------------------------------------------
# Terrain tag -> metatile behavior wiring (terrain_tags.py integration)
# ---------------------------------------------------------------------------


def test_terrain_tag_behavior_wired_into_emitted_metatiles(tmp_path: Path) -> None:
    """A synthetic tileset where tile 401's terrain tag is grass (2): the emitted
    metatile for the column carrying tile 401 gets MB_TALL_GRASS's numeric value; a
    plain column (tile 400, tag 0) stays MB_NORMAL (0); and a warp on the grass
    column still gets MB_NON_ANIMATED_DOOR (door overrides terrain)."""
    fork = _fake_fork(tmp_path)
    base = tmp_path / "tileset_map.json"
    base.write_text("{}", encoding="utf-8")
    overlay_out = tmp_path / "tileset_map.gen.json"

    priors = [0] * 600
    tags = [0] * 600
    tags[401] = 2  # grass

    build_slice_tilesets(
        [(32, _map(5))],
        {32: {(1, 0)}},  # warp at cell (1,0) -> column ((0,401),) (grass tag)
        fork=fork,
        base_tile_map=base,
        overlay_out=overlay_out,
        rasterizer_for=lambda ts: _StubRasterizer(),
        priorities_for=lambda ts: priors,
        terrain_tags_for=lambda ts: tags,
    )

    overlay = json.loads(overlay_out.read_text(encoding="utf-8"))
    tiles = overlay["tiles"]["5"]
    warps = overlay["warps"]["5"]

    col_400 = json.dumps([[0, 400]], separators=(",", ":"))
    col_401 = json.dumps([[0, 401]], separators=(",", ":"))
    plain_400_idx = tiles[col_400]["metatile"]
    plain_401_idx = tiles[col_401]["metatile"]
    door_401_idx = warps["tiles"][col_401]
    fallback_idx = warps["fallback"]

    prim = fork / "data" / "tilesets" / "primary" / "uranium5"
    n_metatiles = max(plain_400_idx, plain_401_idx, door_401_idx, fallback_idx) + 1
    attrs = struct.unpack(
        f"<{n_metatiles}H", (prim / "metatile_attributes.bin").read_bytes()
    )

    mb_tall_grass = _behavior_value(fork, "MB_TALL_GRASS")
    mb_door = _behavior_value(fork, "MB_NON_ANIMATED_DOOR")

    assert (attrs[plain_400_idx] & 0x00FF) == 0  # MB_NORMAL
    assert (attrs[plain_401_idx] & 0x00FF) == mb_tall_grass
    # Door copy overrides the grass terrain behavior with the door behavior.
    assert (attrs[door_401_idx] & 0x00FF) == mb_door
    assert (attrs[fallback_idx] & 0x00FF) == mb_door


# ---------------------------------------------------------------------------
# Tests for analyze_tileset_palettes (continued from above)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Tests for column_n_frames / _render_column(n_frames=...) — animated autotiles
# ---------------------------------------------------------------------------


class _AnimatedStubRasterizer(_StubRasterizer):
    """Stub whose tiles have a per-tile-id frame count; render(tid, frame) shifts
    the stub's solid colour by `frame` so tests can tell frames apart."""

    def __init__(self, counts: dict[int, int]) -> None:
        self._counts = counts

    def frame_count_for_tile(self, tile_id: int) -> int:
        return self._counts.get(tile_id, 1)

    def render(self, tile_id: int, frame: int = 0) -> Image.Image:
        base = super().render(tile_id)
        if frame == 0:
            return base
        r, g, b, a = base.getpixel((0, 0))
        return Image.new("RGBA", (16, 16), ((r + frame) % 256, g, b, a))


def test_column_n_frames_defaults_to_1_without_frame_count_method() -> None:
    key = ((0, 400), (1, 401))
    assert column_n_frames(key, _StubRasterizer()) == 1


def test_column_n_frames_is_lcm_of_per_tile_counts() -> None:
    key = ((0, 48), (1, 400))  # pond-like (19 frames) + static (1 frame)
    rast = _AnimatedStubRasterizer({48: 19, 400: 1})
    assert column_n_frames(key, rast) == 19

    key2 = ((0, 48), (1, 52))  # 3-frame + 4-frame -> lcm 12 (distinct effects sharing
    rast2 = _AnimatedStubRasterizer({48: 3, 52: 4})  # a column, well under the guard)
    assert column_n_frames(key2, rast2) == 12


def test_column_n_frames_guard_fails_loud() -> None:
    key = ((0, 48), (1, 52))
    rast = _AnimatedStubRasterizer({48: 11, 52: 13})  # lcm 143 > MAX_COLUMN_FRAMES
    with pytest.raises(ValueError, match="exceeds"):
        column_n_frames(key, rast)
    assert 11 * 13 > MAX_COLUMN_FRAMES  # sanity: this really is over the guard


def test_column_n_frames_allows_the_route01_pond_over_waterfall_lcm() -> None:
    # CH02/Route 01: the 19-frame pond composited over the 5-frame transparent
    # waterfall needs lcm 95 real frames. Both animate inside the same 8x8
    # quadrants once composited, so the lcm is genuine, not a garbage pairing —
    # the guard was raised to 128 for exactly this column (ts22 tiles 68/124).
    key = ((0, 384), (1, 68), (2, 124))
    rast = _AnimatedStubRasterizer({384: 1, 68: 19, 124: 5})
    assert column_n_frames(key, rast) == 95


def test_render_column_multi_frame_populates_frames() -> None:
    # z-ascending compositing paints the LAST key entry on top; put the animated
    # tile (48, 3 frames) last so its colour is what's actually visible/checked.
    key = ((0, 401), (1, 48))  # static (below) + animated (3 frames, on top)
    rast = _AnimatedStubRasterizer({48: 3, 401: 1})
    mt = _render_column(key, rast, _priors({}), n_frames=3)

    assert mt.frames is not None
    assert len(mt.frames) == 2  # frames 1, 2 (frame 0 is .bottom/.top)

    # Frame 0 (mt.bottom) uses the stub's frame-0 colour for tile 48 (visible,
    # composited over static tile 401).
    assert tuple(mt.bottom[0, 0]) == _stub_color(48)
    # Frame 1 and frame 2 differ from frame 0 and from each other (tile 48 is
    # animated); tile 401 (static, count 1) contributes the same pixels every
    # frame, so only the tile-48 half of the composite should move.
    f1_bottom, _f1_top = mt.frames[0]
    f2_bottom, _f2_top = mt.frames[1]
    assert not (f1_bottom == mt.bottom).all()
    assert not (f1_bottom == f2_bottom).all()


def test_render_column_single_frame_leaves_frames_none() -> None:
    key = ((0, 400),)
    mt = _render_column(key, _StubRasterizer(), _priors({}), n_frames=1)
    assert mt.frames is None


def test_analyze_tileset_palettes_transparent_slots() -> None:
    """mt2 top layer (slots 4-7) is all-transparent -> palette_index=-1, color_changes=[]."""
    mt1 = MetatileImage(
        bottom=_solid_rgba(200, 50, 50),
        top=_solid_rgba(50, 200, 50),
    )
    mt2 = MetatileImage(
        bottom=_solid_rgba(50, 50, 200),
        top=_transparent_rgba(),
    )
    result = analyze_tileset_palettes([mt1, mt2])

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


# ---------------------------------------------------------------------------
# Stairs fix: native sideways-stairs behavior_overrides (stair_cells=)
# ---------------------------------------------------------------------------


def test_stair_cell_gets_extra_metatile_with_correct_behavior(tmp_path: Path) -> None:
    """A stair cell on a column that NO non-stair cell uses mints no extra metatile
    at all — the column's own metatile carries the sideways-stairs MB_* value, and
    the overlay points at that same index. Copying would waste a metatile, and
    tileset 1033 has none to waste."""
    fork = _fake_fork(tmp_path)
    base = tmp_path / "tileset_map.json"
    base.write_text("{}", encoding="utf-8")
    overlay_out = tmp_path / "tileset_map.gen.json"
    priors = [0] * 600

    build_slice_tilesets(
        [(32, _map(5))],
        {},
        fork=fork,
        base_tile_map=base,
        overlay_out=overlay_out,
        rasterizer_for=lambda ts: _StubRasterizer(),
        priorities_for=lambda ts: priors,
        terrain_tags_for=lambda ts: _ZERO_TERRAIN_TAGS,
        stair_cells={32: {(0, 0): "stairs_left"}},
    )

    overlay = json.loads(overlay_out.read_text(encoding="utf-8"))
    tiles = overlay["tiles"]["5"]
    bo = overlay["behavior_overrides"]["5"]["stairs_left"]

    col_400 = json.dumps([[0, 400]], separators=(",", ":"))
    assert set(bo["tiles"]) == {col_400}
    stair_idx = bo["tiles"][col_400]
    # inlined: the overlay entry IS the column's own metatile, no copy
    assert stair_idx == tiles[col_400]["metatile"]
    # Every stair cell here resolved to real column art, so no transparent fallback
    # metatile is minted — an unreferenced one is pure budget waste.
    assert bo["fallback"] is None

    prim = fork / "data" / "tilesets" / "primary" / "uranium5"
    raw = (prim / "metatile_attributes.bin").read_bytes()
    (attr,) = struct.unpack_from("<H", raw, stair_idx * 2)
    mb_left = _behavior_value(fork, "MB_SIDEWAYS_STAIRS_LEFT_SIDE")
    assert (attr & 0x00FF) == mb_left


def test_stair_column_shared_with_non_stair_cell_gets_a_copy(tmp_path: Path) -> None:
    """When a NON-stair cell uses the same column, that column's metatile must keep
    its terrain behavior, so the stair cell gets a behavior-stamped copy instead."""
    fork = _fake_fork(tmp_path)
    base = tmp_path / "tileset_map.json"
    base.write_text("{}", encoding="utf-8")
    overlay_out = tmp_path / "tileset_map.gen.json"
    priors = [0] * 600

    # 2x1 map: both cells carry tile 400, but only (0,0) is a stair cell.
    m = {
        "tileset_id": 5, "width": 2, "height": 1,
        "tiles": {"xsize": 2, "ysize": 1, "zsize": 3, "data": [400, 400, 0, 0, 0, 0]},
    }

    build_slice_tilesets(
        [(32, m)],
        {},
        fork=fork,
        base_tile_map=base,
        overlay_out=overlay_out,
        rasterizer_for=lambda ts: _StubRasterizer(),
        priorities_for=lambda ts: priors,
        terrain_tags_for=lambda ts: _ZERO_TERRAIN_TAGS,
        stair_cells={32: {(0, 0): "stairs_left"}},
    )

    overlay = json.loads(overlay_out.read_text(encoding="utf-8"))
    col_400 = json.dumps([[0, 400]], separators=(",", ":"))
    stair_idx = overlay["behavior_overrides"]["5"]["stairs_left"]["tiles"][col_400]
    plain_idx = overlay["tiles"]["5"][col_400]["metatile"]
    assert stair_idx != plain_idx

    prim = fork / "data" / "tilesets" / "primary" / "uranium5"
    n = max(stair_idx, plain_idx) + 1
    attrs = struct.unpack(f"<{n}H", (prim / "metatile_attributes.bin").read_bytes())
    assert (attrs[stair_idx] & 0x00FF) == _behavior_value(
        fork, "MB_SIDEWAYS_STAIRS_LEFT_SIDE"
    )
    assert (attrs[plain_idx] & 0x00FF) == 0  # MB_NORMAL, untouched


def test_stair_fallback_minted_only_for_empty_column(tmp_path: Path) -> None:
    """A stair cell whose column is empty has no art to copy, so it DOES mint the
    transparent fallback metatile for its kind — the case the unconditional
    fallback used to cover for everyone."""
    fork = _fake_fork(tmp_path)
    base = tmp_path / "tileset_map.json"
    base.write_text("{}", encoding="utf-8")
    overlay_out = tmp_path / "tileset_map.gen.json"
    priors = [0] * 600

    # 2x1 map: cell (0,0) carries tile 400, cell (1,0) is an empty column.
    m = {
        "tileset_id": 5, "width": 2, "height": 1,
        "tiles": {"xsize": 2, "ysize": 1, "zsize": 3, "data": [400, 0, 0, 0, 0, 0]},
    }

    build_slice_tilesets(
        [(32, m)],
        {},
        fork=fork,
        base_tile_map=base,
        overlay_out=overlay_out,
        rasterizer_for=lambda ts: _StubRasterizer(),
        priorities_for=lambda ts: priors,
        terrain_tags_for=lambda ts: _ZERO_TERRAIN_TAGS,
        stair_cells={32: {(1, 0): "stairs_left"}},
    )

    overlay = json.loads(overlay_out.read_text(encoding="utf-8"))
    bo = overlay["behavior_overrides"]["5"]["stairs_left"]
    assert bo["tiles"] == {}
    fallback_idx = bo["fallback"]
    assert fallback_idx is not None

    prim = fork / "data" / "tilesets" / "primary" / "uranium5"
    attrs = struct.unpack(
        f"<{fallback_idx + 1}H", (prim / "metatile_attributes.bin").read_bytes()
    )
    assert (attrs[fallback_idx] & 0x00FF) == _behavior_value(
        fork, "MB_SIDEWAYS_STAIRS_LEFT_SIDE"
    )


def test_stair_cells_sharing_column_and_kind_share_one_metatile(tmp_path: Path) -> None:
    """Two stair cells with the SAME column key and the SAME kind get exactly one
    shared metatile, not one each."""
    fork = _fake_fork(tmp_path)
    base = tmp_path / "tileset_map.json"
    base.write_text("{}", encoding="utf-8")
    overlay_out = tmp_path / "tileset_map.gen.json"
    priors = [0] * 600

    # 2x1 map: both cells carry tile 400 -> identical column key ((0, 400),).
    m = {
        "tileset_id": 5, "width": 2, "height": 1,
        "tiles": {"xsize": 2, "ysize": 1, "zsize": 3, "data": [400, 400, 0, 0, 0, 0]},
    }

    build_slice_tilesets(
        [(32, m)],
        {},
        fork=fork,
        base_tile_map=base,
        overlay_out=overlay_out,
        rasterizer_for=lambda ts: _StubRasterizer(),
        priorities_for=lambda ts: priors,
        terrain_tags_for=lambda ts: _ZERO_TERRAIN_TAGS,
        stair_cells={32: {(0, 0): "stairs_left", (1, 0): "stairs_left"}},
    )

    overlay = json.loads(overlay_out.read_text(encoding="utf-8"))
    bo = overlay["behavior_overrides"]["5"]["stairs_left"]
    assert len(bo["tiles"]) == 1


def test_stair_same_column_both_kinds_gets_two_distinct_metatiles(tmp_path: Path) -> None:
    """The SAME column key used by a "stairs_left" cell and a "stairs_right" cell
    gets TWO distinct metatiles — one per kind, since each kind needs its own
    engine behavior stamp."""
    fork = _fake_fork(tmp_path)
    base = tmp_path / "tileset_map.json"
    base.write_text("{}", encoding="utf-8")
    overlay_out = tmp_path / "tileset_map.gen.json"
    priors = [0] * 600

    m = {
        "tileset_id": 5, "width": 2, "height": 1,
        "tiles": {"xsize": 2, "ysize": 1, "zsize": 3, "data": [400, 400, 0, 0, 0, 0]},
    }

    build_slice_tilesets(
        [(32, m)],
        {},
        fork=fork,
        base_tile_map=base,
        overlay_out=overlay_out,
        rasterizer_for=lambda ts: _StubRasterizer(),
        priorities_for=lambda ts: priors,
        terrain_tags_for=lambda ts: _ZERO_TERRAIN_TAGS,
        stair_cells={32: {(0, 0): "stairs_left", (1, 0): "stairs_right"}},
    )

    overlay = json.loads(overlay_out.read_text(encoding="utf-8"))
    col_400 = json.dumps([[0, 400]], separators=(",", ":"))
    left_idx = overlay["behavior_overrides"]["5"]["stairs_left"]["tiles"][col_400]
    right_idx = overlay["behavior_overrides"]["5"]["stairs_right"]["tiles"][col_400]
    assert left_idx != right_idx

    prim = fork / "data" / "tilesets" / "primary" / "uranium5"
    raw = (prim / "metatile_attributes.bin").read_bytes()
    attrs = struct.unpack(f"<{len(raw) // 2}H", raw)
    mb_left = _behavior_value(fork, "MB_SIDEWAYS_STAIRS_LEFT_SIDE")
    mb_right = _behavior_value(fork, "MB_SIDEWAYS_STAIRS_RIGHT_SIDE")
    assert (attrs[left_idx] & 0x00FF) == mb_left
    assert (attrs[right_idx] & 0x00FF) == mb_right


def test_behavior_overrides_overlay_round_trips_through_load_tile_map(
    tmp_path: Path,
) -> None:
    """The overlay's "behavior_overrides" section round-trips through
    `tile_map.load_tile_map` + `TileMap.behavior_for_column` — the documented shape
    (`{"tiles": {colkey: idx}, "fallback": idx}` per tileset per kind)."""
    from rpg2gba.tileset_converter.tile_map import load_tile_map, serialize_column_key

    fork = _fake_fork(tmp_path)
    base = tmp_path / "tileset_map.json"
    base.write_text("{}", encoding="utf-8")
    overlay_out = tmp_path / "tileset_map.gen.json"
    priors = [0] * 600

    build_slice_tilesets(
        [(32, _map(5))],
        {},
        fork=fork,
        base_tile_map=base,
        overlay_out=overlay_out,
        rasterizer_for=lambda ts: _StubRasterizer(),
        priorities_for=lambda ts: priors,
        terrain_tags_for=lambda ts: _ZERO_TERRAIN_TAGS,
        stair_cells={32: {(0, 0): "stairs_left"}},
    )

    overlay = json.loads(overlay_out.read_text(encoding="utf-8"))
    key = ((0, 400),)
    expected_idx = overlay["behavior_overrides"]["5"]["stairs_left"]["tiles"][
        serialize_column_key(key)
    ]

    tile_map = load_tile_map(overlay_out, passages_path=None)
    assert tile_map.has_behavior_override(5, "stairs_left")
    mt = tile_map.behavior_for_column(5, "stairs_left", key)
    assert mt.metatile_id == expected_idx
    # behavior_for_column always forces passable, per its docstring.
    assert mt.collision == 0  # PASSABLE_COLLISION
    assert mt.elevation == 3  # PASSABLE_ELEVATION

    # No stair cell here needed a fallback, so none was minted — and an unmapped
    # column must then fail loud rather than silently render MB_NORMAL.
    assert overlay["behavior_overrides"]["5"]["stairs_left"]["fallback"] is None
    with pytest.raises(KeyError):
        tile_map.behavior_for_column(5, "stairs_left", None)


def test_no_stair_cells_emits_no_behavior_overrides_entry(tmp_path: Path) -> None:
    """`stair_cells` omitted (the default None): no "behavior_overrides" entry for
    the tileset, and the emitted art is unchanged from the pre-stairs-fix baseline
    (regression pin for the default path — reuses `_run`'s door/warp fixture, whose
    metatile count `test_emitted_art_files` already pins at 7)."""
    fork, _, ctx = _run(tmp_path)
    overlay = ctx["overlay"]
    assert overlay.get("behavior_overrides", {}) == {}

    prim = fork / "data" / "tilesets" / "primary" / "uranium5"
    assert (prim / "metatiles.bin").stat().st_size == 7 * 16
    assert (prim / "metatile_attributes.bin").stat().st_size == 7 * 2


def test_stair_cell_layout_block_passable_despite_blocked_source_passage(
    tmp_path: Path,
) -> None:
    """End-to-end-ish: a stair cell's emitted layout block reads PASSABLE collision
    even though its source column's passage bits read fully blocked — the whole
    point of the fix (RMXP's stair tile is solid on purpose; the native engine
    behavior only redirects a step on a passable tile)."""
    from rpg2gba.tileset_converter.layout import convert_layout
    from rpg2gba.tileset_converter.tile_map import (
        COLLISION_SHIFT,
        load_tile_map,
    )

    fork = _fake_fork(tmp_path)
    base = tmp_path / "tileset_map.json"
    base.write_text("{}", encoding="utf-8")
    overlay_out = tmp_path / "tileset_map.gen.json"
    priors = [0] * 600

    # 2x1 map: both cells carry tile 400. (0,0) gets the stair override; (1,0)
    # doesn't, so it stays subject to the plain source-passage blocked check.
    m = {
        "tileset_id": 5, "width": 2, "height": 1,
        "tiles": {"xsize": 2, "ysize": 1, "zsize": 3, "data": [400, 400, 0, 0, 0, 0]},
    }

    build_slice_tilesets(
        [(32, m)],
        {},
        fork=fork,
        base_tile_map=base,
        overlay_out=overlay_out,
        rasterizer_for=lambda ts: _StubRasterizer(),
        priorities_for=lambda ts: priors,
        terrain_tags_for=lambda ts: _ZERO_TERRAIN_TAGS,
        stair_cells={32: {(0, 0): "stairs_left"}},
    )

    # A tilesets.json oracle where tile 400's passage is fully blocked (all 4
    # directional bits set) — the source RMXP truth the stair fix must override.
    passages = [0] * 600
    passages[400] = 0x0F
    tilesets_json = tmp_path / "tilesets.json"
    tilesets_json.write_text(
        json.dumps({"5": {"passages": passages, "priorities": priors, "terrain_tags": [0] * 600}}),
        encoding="utf-8",
    )

    tile_map = load_tile_map(overlay_out, tilesets_json)

    layout = convert_layout(
        m,
        tile_map,
        name="Test",
        layout_const="LAYOUT_TEST",
        tileset_key=5,
        behavior_overrides={(0, 0): "stairs_left"},
    )

    def _collision_at(x: int, y: int) -> int:
        return (layout.blocks[y * m["width"] + x] >> COLLISION_SHIFT) & 0x3

    assert _collision_at(0, 0) == 0  # PASSABLE — stair override wins
    assert _collision_at(1, 0) == 1  # BLOCKED — plain cell, same tile, no override
