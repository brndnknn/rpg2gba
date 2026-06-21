"""Tests for tileset_converter.graphics.emit — GBA 4bpp binary artifact emission."""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from rpg2gba.tileset_converter.graphics.emit import (
    NUM_METATILES_IN_PRIMARY,
    NUM_PALS_IN_PRIMARY,
    NUM_PALS_TOTAL,
    NUM_TILES_TOTAL,
    EmittedTileset,
    emit_tileset,
)

# ---------------------------------------------------------------------------
# Stub rasterizer
# ---------------------------------------------------------------------------


class StubRasterizer:
    """Returns deterministic 16×16 RGBA PIL images for test tile ids.

    Tile 1  — solid red   (255, 0, 0, 255)
    Tile 2  — solid blue  (0, 0, 255, 255)
    Tile 3  — solid green (0, 255, 0, 255) except bottom-right quadrant transparent
    Tile 4  — 8 distinct colours (2×2 blocks of 8 hues, all fully opaque)
    Tile 5  — all transparent
    Any other id — all transparent (safe fallback)

    All opaque colours are chosen to be exact GBA 5-bit-expanded values so
    quantization is lossless and palette slot lookup is unambiguous.
    """

    _COLORS = {
        1: (255, 0, 0),
        2: (0, 0, 255),
        3: (0, 255, 0),
    }

    # Tile 4: 8 2×2 blocks of distinct hues (all 5-bit-safe, all opaque)
    _T4_COLORS = [
        (255, 0, 0),    # red
        (0, 255, 0),    # green
        (0, 0, 255),    # blue
        (255, 255, 0),  # yellow
        (255, 0, 255),  # magenta
        (0, 255, 255),  # cyan
        (255, 255, 255),  # white
        (136, 136, 136),  # grey (136 = 0x88, 5-bit: 136>>3=17, expand=(17<<3)|(17>>2)=136+4=140 ≠136)
    ]

    def render(self, tile_id: int) -> Image.Image:
        if tile_id in (1, 2, 3):
            color = self._COLORS[tile_id]
            img = Image.new("RGBA", (16, 16), (*color, 255))
            if tile_id == 3:
                # Bottom-right quadrant (x=8..15, y=8..15) transparent
                img.paste(Image.new("RGBA", (8, 8), (0, 0, 0, 0)), (8, 8))
            return img
        if tile_id == 4:
            arr = np.zeros((16, 16, 4), dtype=np.uint8)
            # Place 8 colours in 2×4 strips of height 2, width 16
            colors_8 = [
                (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
                (255, 0, 255), (0, 255, 255), (255, 255, 255), (248, 0, 0),
            ]
            for i, (r, g, b) in enumerate(colors_8):
                arr[i * 2 : i * 2 + 2, :] = [r, g, b, 255]
            return Image.fromarray(arr, "RGBA")
        # Tile 5 or unknown: all transparent
        return Image.new("RGBA", (16, 16), (0, 0, 0, 0))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(
    tmp_path: Path,
    tile_ids: list[int],
    **kwargs,
) -> tuple[EmittedTileset, Path, Path]:
    stub = StubRasterizer()
    pdir = tmp_path / "primary"
    sdir = tmp_path / "secondary"
    result = emit_tileset(
        tile_ids, stub, pdir, sdir, "gTileset_Primary", "gTileset_Secondary", **kwargs
    )
    return result, pdir, sdir


def _parse_pal(path: Path) -> list[tuple[int, int, int]]:
    """Parse a JASC-PAL file; return list of (R,G,B) tuples (all 16 entries)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "JASC-PAL", f"bad header in {path}"
    assert lines[1] == "0100"
    assert lines[2] == "16"
    assert len(lines) == 19, f"expected 19 lines (3 header + 16 colours), got {len(lines)}"
    result = []
    for line in lines[3:]:
        parts = line.split()
        assert len(parts) == 3, f"bad colour line {line!r}"
        result.append(tuple(int(p) for p in parts))
    return result


# ---------------------------------------------------------------------------
# 1. Binary sizes
# ---------------------------------------------------------------------------


def test_metatiles_bin_size(tmp_path):
    """metatiles.bin must be n_metatiles_primary × 16 bytes (8 u16 per metatile)."""
    result, pdir, sdir = _run(tmp_path, [1, 2, 3])
    n_primary = min(result.n_metatiles, NUM_METATILES_IN_PRIMARY)
    n_secondary = max(1, result.n_metatiles - NUM_METATILES_IN_PRIMARY)
    assert len((pdir / "metatiles.bin").read_bytes()) == n_primary * 16
    assert len((sdir / "metatiles.bin").read_bytes()) == n_secondary * 16


def test_metatile_attrs_size(tmp_path):
    """metatile_attributes.bin must be n_metatiles_primary × 2 bytes (1 u16 each)."""
    result, pdir, sdir = _run(tmp_path, [1, 2, 3])
    n_primary = min(result.n_metatiles, NUM_METATILES_IN_PRIMARY)
    n_secondary = max(1, result.n_metatiles - NUM_METATILES_IN_PRIMARY)
    assert len((pdir / "metatile_attributes.bin").read_bytes()) == n_primary * 2
    assert len((sdir / "metatile_attributes.bin").read_bytes()) == n_secondary * 2


# ---------------------------------------------------------------------------
# 2. tiles.png format
# ---------------------------------------------------------------------------


def test_tiles_png_mode_and_width(tmp_path):
    """Primary tiles.png must be mode 'P', width 128."""
    _, pdir, _ = _run(tmp_path, [1, 2])
    img = Image.open(pdir / "tiles.png")
    assert img.mode == "P"
    assert img.width == 128


def test_tiles_png_tile0_all_zero(tmp_path):
    """Global GBA tile 0 (transparent) occupies the top-left 8×8 region and is all-zero."""
    _, pdir, _ = _run(tmp_path, [1, 2])
    arr = np.array(Image.open(pdir / "tiles.png"))
    assert (arr[:8, :8] == 0).all(), "tile-0 region (top-left 8×8) should be all-zero"


def test_tiles_png_nonzero_for_opaque_tile(tmp_path):
    """A non-transparent tile should have at least one nonzero palette index in the PNG."""
    _, pdir, _ = _run(tmp_path, [1])
    arr = np.array(Image.open(pdir / "tiles.png"))
    # Global tile 1 is at local position 1 → pixel region arr[0:8, 8:16]
    assert (arr[:8, 8:16] > 0).any(), "expected nonzero indices for solid-red tile"


def test_secondary_tiles_png_valid(tmp_path):
    """Secondary tiles.png must be a valid mode-P PNG with width 128."""
    _, _, sdir = _run(tmp_path, [1])
    img = Image.open(sdir / "tiles.png")
    assert img.mode == "P"
    assert img.width == 128


# ---------------------------------------------------------------------------
# 3. JASC-PAL format and placement
# ---------------------------------------------------------------------------


def test_pal_format_primary(tmp_path):
    """Primary 00.pal must have the correct JASC header and exactly 16 colour lines."""
    _, pdir, _ = _run(tmp_path, [1, 2])
    entries = _parse_pal(pdir / "palettes" / "00.pal")
    assert len(entries) == 16
    for r, g, b in entries:
        assert 0 <= r <= 255
        assert 0 <= g <= 255
        assert 0 <= b <= 255


def test_pal_format_secondary(tmp_path):
    """Secondary 06.pal must have the correct JASC header and exactly 16 colour lines."""
    _, _, sdir = _run(tmp_path, [1, 2])
    entries = _parse_pal(sdir / "palettes" / "06.pal")
    assert len(entries) == 16


def test_pal_files_exist_in_both_dirs(tmp_path):
    """Both dirs must have all 16 palette files (00.pal..15.pal)."""
    _, pdir, sdir = _run(tmp_path, [1, 2])
    for g in range(16):
        fname = f"{g:02}.pal"
        assert (pdir / "palettes" / fname).exists(), f"primary/palettes/{fname} missing"
        assert (sdir / "palettes" / fname).exists(), f"secondary/palettes/{fname} missing"


def test_pal_real_colors_in_primary_slot(tmp_path):
    """Palette 0 colours must appear in primary/palettes/00.pal, not secondary."""
    result, pdir, sdir = _run(tmp_path, [1, 2, 3])
    if result.n_palettes == 0:
        pytest.skip("no palettes emitted")
    # Primary slot 0 should have at least one non-black colour
    p_entries = _parse_pal(pdir / "palettes" / "00.pal")
    has_real = any(e != (0, 0, 0) for e in p_entries)
    assert has_real, "expected real (non-black) colours in primary/palettes/00.pal"
    # Secondary slot 0 should be all-black (palette 0 lives in primary)
    s_entries = _parse_pal(sdir / "palettes" / "00.pal")
    assert all(e == (0, 0, 0) for e in s_entries), (
        "secondary/palettes/00.pal should be all-black (slot 0 belongs to primary)"
    )


def test_pal_secondary_slot_in_secondary(tmp_path):
    """A palette that spills into slot ≥6 must appear in secondary/palettes/{g:02}.pal."""
    # Force ≥6 palettes by using many distinct tiles
    stub = StubRasterizer()
    pdir = tmp_path / "primary"
    sdir = tmp_path / "secondary"
    # Build enough tiles to push quantizer to ≥6 palettes: use tile 4 (8-colour) +
    # several solid-colour tiles to force separate palette groups.
    tile_ids = [1, 2, 3, 4, 5]
    result = emit_tileset(tile_ids, stub, pdir, sdir, "p", "s")
    if result.n_palettes <= NUM_PALS_IN_PRIMARY:
        pytest.skip(f"only {result.n_palettes} palettes; need >6 to test secondary slot")
    # At least one secondary palette file should have a real colour
    any_real = False
    for g in range(NUM_PALS_IN_PRIMARY, result.n_palettes):
        entries = _parse_pal(sdir / "palettes" / f"{g:02}.pal")
        if any(e != (0, 0, 0) for e in entries):
            any_real = True
            break
    assert any_real, "expected a real-colour secondary palette file"


# ---------------------------------------------------------------------------
# 4. Metatile entry decode
# ---------------------------------------------------------------------------


def test_metatile_decode_bottom_slots(tmp_path):
    """Bottom layer slots (0-3) must encode valid tile indices and palette numbers."""
    result, pdir, _ = _run(tmp_path, [1, 2, 3])
    raw = (pdir / "metatiles.bin").read_bytes()
    n = min(result.n_metatiles, NUM_METATILES_IN_PRIMARY)
    for mt in range(n):
        vals = struct.unpack_from("<8H", raw, mt * 16)
        for v in vals[:4]:
            tile_idx = v & 0x3FF
            palnum = (v >> 12) & 0xF
            assert tile_idx < NUM_TILES_TOTAL, (
                f"metatile {mt}: tile index {tile_idx} exceeds NUM_TILES_TOTAL"
            )
            assert palnum < NUM_PALS_TOTAL, (
                f"metatile {mt}: palnum {palnum} exceeds NUM_PALS_TOTAL"
            )


def test_metatile_top_slots_zero(tmp_path):
    """Top layer slots (4-7) of every metatile entry must be 0x0000."""
    result, pdir, _ = _run(tmp_path, [1, 2, 3])
    raw = (pdir / "metatiles.bin").read_bytes()
    n = min(result.n_metatiles, NUM_METATILES_IN_PRIMARY)
    for mt in range(n):
        vals = struct.unpack_from("<8H", raw, mt * 16)
        for slot, v in enumerate(vals[4:], start=4):
            assert v == 0, f"metatile {mt} slot {slot} = {v:#06x}, expected 0x0000"


def test_transparent_quad_gets_tile0(tmp_path):
    """Tile 3's bottom-right quadrant is transparent and must encode GBA tile index 0."""
    _, pdir, _ = _run(tmp_path, [3])
    raw = (pdir / "metatiles.bin").read_bytes()
    # Metatile 0 = tile 3.  Slot order: TL=0, TR=1, BL=2, BR=3.
    # BR quadrant of tile 3 is all-transparent → gba_tile_index must be 0.
    vals = struct.unpack_from("<8H", raw, 0)
    br_tile_idx = vals[3] & 0x3FF
    assert br_tile_idx == 0, (
        f"transparent BR quad expected tile index 0, got {br_tile_idx}"
    )


# ---------------------------------------------------------------------------
# 5. behaviour_overrides
# ---------------------------------------------------------------------------


def test_behavior_override_low_byte(tmp_path):
    """The low byte of a metatile's attribute must equal its behavior_overrides value."""
    OVERRIDE_TILE = 2
    OVERRIDE_VALUE = 0x41   # arbitrary non-zero
    result, pdir, _ = _run(
        tmp_path, [1, 2, 3], behavior_overrides={OVERRIDE_TILE: OVERRIDE_VALUE}
    )
    raw = (pdir / "metatile_attributes.bin").read_bytes()
    n = min(result.n_metatiles, NUM_METATILES_IN_PRIMARY)
    attrs = struct.unpack_from(f"<{n}H", raw)
    # tile_ids=[1,2,3] → metatile 0=tile1, 1=tile2, 2=tile3
    assert (attrs[1] & 0x00FF) == OVERRIDE_VALUE, (
        f"expected behavior {OVERRIDE_VALUE:#04x} in attrs[1], got {attrs[1] & 0xFF:#04x}"
    )
    # Other tiles should have default behavior 0
    assert (attrs[0] & 0x00FF) == 0
    assert (attrs[2] & 0x00FF) == 0


def test_behavior_default_zero(tmp_path):
    """With no overrides, all attribute low bytes must be zero."""
    result, pdir, _ = _run(tmp_path, [1, 2])
    raw = (pdir / "metatile_attributes.bin").read_bytes()
    n = min(result.n_metatiles, NUM_METATILES_IN_PRIMARY)
    attrs = struct.unpack_from(f"<{n}H", raw)
    assert all((a & 0x00FF) == 0 for a in attrs), "expected all behaviors == 0"


def test_layer_type_in_attr_high_nibble(tmp_path):
    """The layer_type parameter must appear in bits 12-15 of every attribute."""
    MY_LAYER = 2  # METATILE_LAYER_TYPE_SPLIT
    result, pdir, _ = _run(tmp_path, [1, 2], layer_type=MY_LAYER)
    raw = (pdir / "metatile_attributes.bin").read_bytes()
    n = min(result.n_metatiles, NUM_METATILES_IN_PRIMARY)
    attrs = struct.unpack_from(f"<{n}H", raw)
    for a in attrs:
        assert (a >> 12) & 0xF == MY_LAYER, (
            f"expected layer_type {MY_LAYER} in bits 12-15, got {(a>>12)&0xF}"
        )


# ---------------------------------------------------------------------------
# 6. Determinism
# ---------------------------------------------------------------------------


def test_determinism(tmp_path):
    """Two independent runs with identical inputs must produce byte-identical outputs."""
    tile_ids = [1, 2, 3]

    def run(d: Path) -> tuple[Path, Path]:
        pdir = d / "primary"
        sdir = d / "secondary"
        emit_tileset(tile_ids, StubRasterizer(), pdir, sdir, "p", "s")
        return pdir, sdir

    pdir1, sdir1 = run(tmp_path / "run1")
    pdir2, sdir2 = run(tmp_path / "run2")

    for fname in ("metatiles.bin", "metatile_attributes.bin", "tiles.png"):
        assert (pdir1 / fname).read_bytes() == (pdir2 / fname).read_bytes(), (
            f"primary/{fname} is not deterministic"
        )
        assert (sdir1 / fname).read_bytes() == (sdir2 / fname).read_bytes(), (
            f"secondary/{fname} is not deterministic"
        )

    for g in range(16):
        fname = f"{g:02}.pal"
        assert (pdir1 / "palettes" / fname).read_bytes() == (
            pdir2 / "palettes" / fname
        ).read_bytes(), f"primary/palettes/{fname} is not deterministic"
        assert (sdir1 / "palettes" / fname).read_bytes() == (
            sdir2 / "palettes" / fname
        ).read_bytes(), f"secondary/palettes/{fname} is not deterministic"


# ---------------------------------------------------------------------------
# 7. tile_to_metatile mapping
# ---------------------------------------------------------------------------


def test_tile_to_metatile_dedup(tmp_path):
    """Duplicate tile_ids must be collapsed; the returned n_metatiles must match uniques."""
    result, _, _ = _run(tmp_path, [1, 2, 3, 1, 2])
    assert result.n_metatiles == 3
    assert set(result.tile_to_metatile.keys()) == {1, 2, 3}


def test_tile_to_metatile_distinct_ids(tmp_path):
    """tile_to_metatile values must be distinct and in range 0..n_metatiles-1."""
    result, _, _ = _run(tmp_path, [1, 2, 3])
    ids = list(result.tile_to_metatile.values())
    assert len(ids) == len(set(ids)), "metatile ids are not unique"
    assert all(0 <= i < result.n_metatiles for i in ids)


def test_tile_to_metatile_order(tmp_path):
    """Metatile id must equal the position of the tile_id in the first-seen order."""
    result, _, _ = _run(tmp_path, [2, 1, 3])
    assert result.tile_to_metatile[2] == 0
    assert result.tile_to_metatile[1] == 1
    assert result.tile_to_metatile[3] == 2


# ---------------------------------------------------------------------------
# 8. EmittedTileset fields
# ---------------------------------------------------------------------------


def test_emitted_tileset_fields(tmp_path):
    """EmittedTileset must carry the correct primary/secondary names and counts."""
    result, _, _ = _run(tmp_path, [1, 2])
    assert result.primary_name == "gTileset_Primary"
    assert result.secondary_name == "gTileset_Secondary"
    assert result.n_metatiles == 2
    assert result.n_tiles >= 2          # at least transparent + 1 real tile
    assert result.n_palettes >= 1
    assert isinstance(result.stats, dict)
    assert "n_metatiles" in result.stats
    assert "n_gba_tiles" in result.stats


def test_n_tiles_includes_transparent(tmp_path):
    """n_tiles must be at least 1 (transparent tile 0) even for all-transparent input."""
    result, _, _ = _run(tmp_path, [5])  # tile 5 is all-transparent
    assert result.n_tiles >= 1


# ---------------------------------------------------------------------------
# 9. Edge-cases
# ---------------------------------------------------------------------------


def test_all_transparent_tile(tmp_path):
    """An all-transparent input tile produces n_metatiles=1, n_tiles=1."""
    result, pdir, _ = _run(tmp_path, [5])
    assert result.n_metatiles == 1
    assert result.n_tiles == 1   # only the reserved transparent tile
    # Metatile entry: all four bottom slots should reference tile 0 (transparent)
    raw = (pdir / "metatiles.bin").read_bytes()
    vals = struct.unpack_from("<8H", raw, 0)
    for slot, v in enumerate(vals[:4]):
        assert (v & 0x3FF) == 0, f"slot {slot}: expected tile index 0 for transparent tile"


def test_identical_quads_dedup(tmp_path):
    """Identical quadrants across different metatiles share one GBA tile entry."""
    # Tiles 1 and 1 (same) → 1 unique metatile, 2 unique GBA tiles (0 + red)
    result, _, _ = _run(tmp_path, [1])
    # All 4 quads of solid-red tile are identical → should collapse to 1 unique quad
    assert result.n_tiles == 2   # transparent + 1 red quad


def test_large_dedup_input(tmp_path):
    """Many repeated tile_ids must not inflate metatile or tile counts."""
    result, _, _ = _run(tmp_path, [1, 1, 1, 2, 2, 3, 3, 3])
    assert result.n_metatiles == 3  # only 3 unique tile_ids
