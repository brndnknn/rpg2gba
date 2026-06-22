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

from PIL import Image

from rpg2gba.tileset_converter.graphics.build_slice_tilesets import (
    _behavior_value,
    build_slice_tilesets,
)


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
    # Warp metatile is a SEPARATE copy at index 5 (after void), NOT the same entry
    # as the column-key metatile for (0,0); that entry stays MB_NORMAL (behavior 0).
    assert overlay["warps"]["5"] == {"metatile": 5, "collision": 0, "elevation": 0}
    # Confirm the column-key entry for cell (0,0) is metatile 0 (not the warp copy).
    col_400_key = json.dumps([[0, 400]], separators=(",", ":"))
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

    # 6 metatiles: 4 column + 1 void + 1 warp copy, all in primary.
    # metatiles.bin:           6 metatiles * 8 u16 slots * 2 bytes = 96 bytes
    # metatile_attributes.bin: 6 metatiles * 1 u16 * 2 bytes       = 12 bytes
    assert (prim / "metatiles.bin").stat().st_size == 6 * 16
    assert (prim / "metatile_attributes.bin").stat().st_size == 6 * 2

    attrs = struct.unpack("<6H", (prim / "metatile_attributes.bin").read_bytes())

    # Metatile 5 (warp copy of column ((0,400),)) carries MB_NON_ANIMATED_DOOR (=2).
    assert (attrs[5] & 0x00FF) == 2
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
