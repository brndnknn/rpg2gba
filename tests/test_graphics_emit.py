"""Tests for tileset_converter.graphics.emit — GBA 4bpp binary artifact emission."""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from rpg2gba.tileset_converter.graphics.emit import (
    LAYER_COVERED,
    NUM_METATILES_IN_PRIMARY,
    NUM_PALS_IN_PRIMARY,
    NUM_PALS_TOTAL,
    NUM_TILES_TOTAL,
    EmittedTileset,
    MetatileImage,
    emit_tileset,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def solid(r: int, g: int, b: int, a: int = 255) -> np.ndarray:
    """Return a (16,16,4) uint8 array filled with (r,g,b,a)."""
    return np.full((16, 16, 4), [r, g, b, a], dtype=np.uint8)


def transparent() -> np.ndarray:
    """Return a (16,16,4) all-zero uint8 array."""
    return np.zeros((16, 16, 4), dtype=np.uint8)


def make_metatile(
    bottom: np.ndarray,
    top: np.ndarray | None = None,
    layer_type: int = LAYER_COVERED,
    behavior: int = 0,
) -> MetatileImage:
    return MetatileImage(
        bottom=bottom,
        top=top if top is not None else transparent(),
        layer_type=layer_type,
        behavior=behavior,
    )


def _run(
    tmp_path: Path,
    metatiles: list[MetatileImage],
    **kwargs,
) -> tuple[EmittedTileset, Path, Path]:
    pdir = tmp_path / "primary"
    sdir = tmp_path / "secondary"
    result = emit_tileset(
        metatiles, pdir, sdir, "gTileset_Primary", "gTileset_Secondary", **kwargs
    )
    return result, pdir, sdir


def _parse_pal(path: Path) -> list[tuple[int, ...]]:
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
    mts = [
        make_metatile(solid(255, 0, 0)),
        make_metatile(solid(0, 0, 255)),
        make_metatile(solid(0, 255, 0)),
    ]
    result, pdir, sdir = _run(tmp_path, mts)
    n_primary = min(result.n_metatiles, NUM_METATILES_IN_PRIMARY)
    n_secondary = max(1, result.n_metatiles - NUM_METATILES_IN_PRIMARY)
    assert len((pdir / "metatiles.bin").read_bytes()) == n_primary * 16
    assert len((sdir / "metatiles.bin").read_bytes()) == n_secondary * 16


def test_metatile_attrs_size(tmp_path):
    """metatile_attributes.bin must be n_metatiles_primary × 2 bytes (1 u16 each)."""
    mts = [
        make_metatile(solid(255, 0, 0)),
        make_metatile(solid(0, 0, 255)),
        make_metatile(solid(0, 255, 0)),
    ]
    result, pdir, sdir = _run(tmp_path, mts)
    n_primary = min(result.n_metatiles, NUM_METATILES_IN_PRIMARY)
    n_secondary = max(1, result.n_metatiles - NUM_METATILES_IN_PRIMARY)
    assert len((pdir / "metatile_attributes.bin").read_bytes()) == n_primary * 2
    assert len((sdir / "metatile_attributes.bin").read_bytes()) == n_secondary * 2


# ---------------------------------------------------------------------------
# 2. tiles.png format
# ---------------------------------------------------------------------------


def test_tiles_png_mode_and_width(tmp_path):
    """Primary tiles.png must be mode 'P', width 128."""
    _, pdir, _ = _run(tmp_path, [make_metatile(solid(255, 0, 0)), make_metatile(solid(0, 0, 255))])
    img = Image.open(pdir / "tiles.png")
    assert img.mode == "P"
    assert img.width == 128


def test_tiles_png_tile0_all_zero(tmp_path):
    """GBA tile 0 (transparent) occupies the top-left 8×8 region and is all-zero."""
    _, pdir, _ = _run(tmp_path, [make_metatile(solid(255, 0, 0)), make_metatile(solid(0, 0, 255))])
    arr = np.array(Image.open(pdir / "tiles.png"))
    assert (arr[:8, :8] == 0).all(), "tile-0 region (top-left 8×8) should be all-zero"


def test_tiles_png_nonzero_for_opaque_tile(tmp_path):
    """A non-transparent metatile should produce at least one nonzero palette index."""
    _, pdir, _ = _run(tmp_path, [make_metatile(solid(255, 0, 0))])
    arr = np.array(Image.open(pdir / "tiles.png"))
    # GBA tile 1 is the first non-transparent tile; it sits at pixels [0:8, 8:16]
    assert (arr[:8, 8:16] > 0).any(), "expected nonzero indices for solid-red tile"


def test_secondary_tiles_png_valid(tmp_path):
    """Secondary tiles.png must be a valid mode-P PNG with width 128."""
    _, _, sdir = _run(tmp_path, [make_metatile(solid(255, 0, 0))])
    img = Image.open(sdir / "tiles.png")
    assert img.mode == "P"
    assert img.width == 128


# ---------------------------------------------------------------------------
# 3. JASC-PAL format and placement
# ---------------------------------------------------------------------------


def test_pal_format_primary(tmp_path):
    """Primary 00.pal must have the correct JASC header and exactly 16 colour lines."""
    _, pdir, _ = _run(tmp_path, [make_metatile(solid(255, 0, 0)), make_metatile(solid(0, 0, 255))])
    entries = _parse_pal(pdir / "palettes" / "00.pal")
    assert len(entries) == 16
    for r, g, b in entries:
        assert 0 <= r <= 255
        assert 0 <= g <= 255
        assert 0 <= b <= 255


def test_pal_format_secondary(tmp_path):
    """Secondary 06.pal must have the correct JASC header and exactly 16 colour lines."""
    _, _, sdir = _run(tmp_path, [make_metatile(solid(255, 0, 0)), make_metatile(solid(0, 0, 255))])
    entries = _parse_pal(sdir / "palettes" / "06.pal")
    assert len(entries) == 16


def test_pal_files_exist_in_both_dirs(tmp_path):
    """Both dirs must have all 16 palette files (00.pal..15.pal)."""
    mts = [make_metatile(solid(255, 0, 0)), make_metatile(solid(0, 0, 255))]
    _, pdir, sdir = _run(tmp_path, mts)
    for g in range(16):
        fname = f"{g:02}.pal"
        assert (pdir / "palettes" / fname).exists(), f"primary/palettes/{fname} missing"
        assert (sdir / "palettes" / fname).exists(), f"secondary/palettes/{fname} missing"


def test_pal_real_colors_in_primary_slot(tmp_path):
    """Palette 0 colours must appear in primary/palettes/00.pal; secondary copy all-black."""
    mts = [
        make_metatile(solid(255, 0, 0)),
        make_metatile(solid(0, 0, 255)),
        make_metatile(solid(0, 255, 0)),
    ]
    result, pdir, sdir = _run(tmp_path, mts)
    if result.n_palettes == 0:
        pytest.skip("no palettes emitted")
    p_entries = _parse_pal(pdir / "palettes" / "00.pal")
    assert any(e != (0, 0, 0) for e in p_entries), (
        "expected real (non-black) colours in primary/palettes/00.pal"
    )
    s_entries = _parse_pal(sdir / "palettes" / "00.pal")
    assert all(e == (0, 0, 0) for e in s_entries), (
        "secondary/palettes/00.pal should be all-black (slot 0 belongs to primary)"
    )


def test_pal_secondary_slot_in_secondary(tmp_path):
    """A palette that spills into slot ≥6 must appear in the secondary palette directory."""
    distinct_colors = [
        (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
        (255, 0, 255), (0, 255, 255), (255, 255, 255),
    ]
    mts = [make_metatile(solid(r, g, b)) for r, g, b in distinct_colors]
    result, pdir, sdir = _run(tmp_path, mts)
    if result.n_palettes <= NUM_PALS_IN_PRIMARY:
        pytest.skip(f"only {result.n_palettes} palettes; need >6 to test secondary slot")
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
    mts = [
        make_metatile(solid(255, 0, 0)),
        make_metatile(solid(0, 0, 255)),
        make_metatile(solid(0, 255, 0)),
    ]
    result, pdir, _ = _run(tmp_path, mts)
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


def test_metatile_top_layer_nonzero(tmp_path):
    """A non-transparent top layer must encode at least one non-zero top slot."""
    mt = make_metatile(bottom=solid(255, 0, 0), top=solid(0, 255, 0))
    result, pdir, _ = _run(tmp_path, [mt])
    raw = (pdir / "metatiles.bin").read_bytes()
    vals = struct.unpack_from("<8H", raw, 0)
    top_tile_indices = [(v & 0x3FF) for v in vals[4:]]
    assert any(t != 0 for t in top_tile_indices), (
        "expected at least one non-zero top slot for a metatile with an opaque top layer"
    )


def test_metatile_top_layer_transparent_all_zero(tmp_path):
    """An all-transparent top layer must encode all four top slots as tile index 0."""
    mt = make_metatile(bottom=solid(255, 0, 0), top=transparent())
    result, pdir, _ = _run(tmp_path, [mt])
    raw = (pdir / "metatiles.bin").read_bytes()
    vals = struct.unpack_from("<8H", raw, 0)
    for slot, v in enumerate(vals[4:], start=4):
        assert (v & 0x3FF) == 0, (
            f"slot {slot}: expected tile index 0 for transparent top, got {v & 0x3FF}"
        )


# ---------------------------------------------------------------------------
# 5. Transparent quadrant → tile index 0
# ---------------------------------------------------------------------------


def test_transparent_quad_gets_tile0(tmp_path):
    """A transparent quadrant in the bottom layer must encode GBA tile index 0."""
    # Solid green bottom with the BR quadrant (rows 8:16, cols 8:16) made transparent.
    bottom = solid(0, 255, 0)
    bottom[8:16, 8:16] = 0   # BR quadrant: all channels = 0, alpha = 0
    mt = make_metatile(bottom=bottom)
    _, pdir, _ = _run(tmp_path, [mt])
    raw = (pdir / "metatiles.bin").read_bytes()
    vals = struct.unpack_from("<8H", raw, 0)
    br_tile_idx = vals[3] & 0x3FF   # slot 3 = BR of bottom layer
    assert br_tile_idx == 0, (
        f"transparent BR quad expected tile index 0, got {br_tile_idx}"
    )


# ---------------------------------------------------------------------------
# 6. behavior
# ---------------------------------------------------------------------------


def test_behavior_low_byte(tmp_path):
    """The low byte of a metatile's attribute must equal its behavior value."""
    OVERRIDE = 0x41
    mts = [
        make_metatile(solid(255, 0, 0), behavior=OVERRIDE),
        make_metatile(solid(0, 0, 255)),
    ]
    result, pdir, _ = _run(tmp_path, mts)
    raw = (pdir / "metatile_attributes.bin").read_bytes()
    n = min(result.n_metatiles, NUM_METATILES_IN_PRIMARY)
    attrs = struct.unpack_from(f"<{n}H", raw)
    assert (attrs[0] & 0x00FF) == OVERRIDE, (
        f"expected behavior {OVERRIDE:#04x} in attrs[0], got {attrs[0] & 0xFF:#04x}"
    )
    assert (attrs[1] & 0x00FF) == 0, "expected default behavior 0 in attrs[1]"


def test_behavior_default_zero(tmp_path):
    """With no behavior set, all attribute low bytes must be zero."""
    mts = [make_metatile(solid(255, 0, 0)), make_metatile(solid(0, 0, 255))]
    result, pdir, _ = _run(tmp_path, mts)
    raw = (pdir / "metatile_attributes.bin").read_bytes()
    n = min(result.n_metatiles, NUM_METATILES_IN_PRIMARY)
    attrs = struct.unpack_from(f"<{n}H", raw)
    assert all((a & 0x00FF) == 0 for a in attrs), "expected all behaviors == 0"


# ---------------------------------------------------------------------------
# 7. layer_type
# ---------------------------------------------------------------------------


def test_layer_type_in_attr(tmp_path):
    """A layer_type value must appear in bits 12-15 of every affected metatile attribute."""
    MY_LAYER = 2
    mts = [
        make_metatile(solid(255, 0, 0), layer_type=MY_LAYER),
        make_metatile(solid(0, 0, 255), layer_type=MY_LAYER),
    ]
    result, pdir, _ = _run(tmp_path, mts)
    raw = (pdir / "metatile_attributes.bin").read_bytes()
    n = min(result.n_metatiles, NUM_METATILES_IN_PRIMARY)
    attrs = struct.unpack_from(f"<{n}H", raw)
    for a in attrs:
        assert (a >> 12) & 0xF == MY_LAYER, (
            f"expected layer_type {MY_LAYER} in bits 12-15, got {(a >> 12) & 0xF}"
        )


def test_layer_type_default_covered(tmp_path):
    """Default layer_type=LAYER_COVERED (1) must appear in bits 12-15 when not overridden."""
    mts = [make_metatile(solid(255, 0, 0))]
    result, pdir, _ = _run(tmp_path, mts)
    raw = (pdir / "metatile_attributes.bin").read_bytes()
    (attr,) = struct.unpack_from("<1H", raw)
    assert (attr >> 12) & 0xF == LAYER_COVERED, (
        f"expected LAYER_COVERED={LAYER_COVERED} in bits 12-15, got {(attr >> 12) & 0xF}"
    )


# ---------------------------------------------------------------------------
# 8. Flip-aware dedup
# ---------------------------------------------------------------------------


def test_flip_aware_dedup(tmp_path):
    """A quadrant and its exact horizontal mirror share one GBA tile, differing only in hflip."""
    # Asymmetric TL quadrant: left 4 cols red, right 4 cols blue.  Its h-mirror has left
    # blue, right red.  Both should resolve to the same canonical GBA tile, referenced with
    # opposite hflip bits so the hardware reconstructs each orientation correctly.
    bottom_orig = transparent()
    bottom_orig[:8, :4] = [255, 0, 0, 255]   # TL quad left half: red
    bottom_orig[:8, 4:8] = [0, 0, 255, 255]  # TL quad right half: blue

    bottom_flip = transparent()
    bottom_flip[:8, :4] = [0, 0, 255, 255]   # TL quad left half: blue (h-mirror)
    bottom_flip[:8, 4:8] = [255, 0, 0, 255]  # TL quad right half: red

    mt0 = make_metatile(bottom=bottom_orig)
    mt1 = make_metatile(bottom=bottom_flip)

    _, pdir, _ = _run(tmp_path, [mt0, mt1])
    raw = (pdir / "metatiles.bin").read_bytes()

    vals0 = struct.unpack_from("<8H", raw, 0)   # metatile 0
    vals1 = struct.unpack_from("<8H", raw, 16)  # metatile 1

    # Slot 0 = TL quadrant of the bottom layer for each metatile
    tile0 = vals0[0] & 0x3FF
    tile1 = vals1[0] & 0x3FF
    hflip0 = (vals0[0] >> 10) & 1
    hflip1 = (vals1[0] >> 10) & 1

    assert tile0 == tile1, (
        f"expected same GBA tile index for a quad and its h-mirror, got {tile0} vs {tile1}"
    )
    assert hflip0 != hflip1, (
        f"expected opposite hflip bits for mirrored quads, got hflip0={hflip0} hflip1={hflip1}"
    )


def test_post_quantization_merge(tmp_path):
    """Two tiles distinct at full RGB but identical after 5-bit quantization merge
    into one stored GBA tile — the dedup that keeps a column-keyed tileset under the
    1024-tile budget once ground+overlay combinations multiply."""
    # (16,32,48) vs (18,34,50): each channel shares the same top 5 bits, so to_5bit
    # collapses them.  Their raw bytes differ, so the Step-1 (raw) flip-canon dedup
    # keeps them as separate canon tiles; only the post-quant merge folds them.
    mt0 = make_metatile(bottom=solid(16, 32, 48))
    mt1 = make_metatile(bottom=solid(18, 34, 50))

    result, pdir, _ = _run(tmp_path, [mt0, mt1])
    raw = (pdir / "metatiles.bin").read_bytes()
    tile0 = struct.unpack_from("<H", raw, 0)[0] & 0x3FF   # mt0 bottom slot 0
    tile1 = struct.unpack_from("<H", raw, 16)[0] & 0x3FF  # mt1 bottom slot 0

    assert tile0 == tile1, f"expected a merged GBA tile, got {tile0} vs {tile1}"
    # tile 0 (transparent) + exactly one shared opaque tile
    assert result.n_tiles == 2, f"expected 2 tiles after merge, got {result.n_tiles}"


def test_tile_budget_overrun_fails_loud(tmp_path, monkeypatch):
    """A tile pool over the hardware budget raises BEFORE any artifact is written —
    column-keying can multiply tiles, and a malformed tileset must not reach the fork."""
    import rpg2gba.tileset_converter.graphics.emit as emit_mod

    monkeypatch.setattr(emit_mod, "NUM_TILES_TOTAL", 2)
    # Three 5-bit-distinct solid colours -> 3 opaque tiles + transparent tile 0 = 4 > 2.
    mts = [
        make_metatile(bottom=solid(248, 0, 0)),
        make_metatile(bottom=solid(0, 248, 0)),
        make_metatile(bottom=solid(0, 0, 248)),
    ]
    with pytest.raises(ValueError, match="exceeds"):
        _run(tmp_path, mts)
    assert not (tmp_path / "primary" / "tiles.png").exists(), (
        "no artifact should be written on a budget overrun"
    )


# ---------------------------------------------------------------------------
# 9. Determinism
# ---------------------------------------------------------------------------


def test_determinism(tmp_path):
    """Two runs with identical MetatileImage inputs must produce byte-identical outputs."""
    mts = [
        make_metatile(solid(255, 0, 0)),
        make_metatile(solid(0, 0, 255)),
        make_metatile(solid(0, 255, 0)),
    ]

    def run(d: Path) -> tuple[Path, Path]:
        pdir = d / "primary"
        sdir = d / "secondary"
        emit_tileset(mts, pdir, sdir, "p", "s")
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
# 10. EmittedTileset fields
# ---------------------------------------------------------------------------


def test_emitted_tileset_fields(tmp_path):
    """EmittedTileset must carry the correct names, counts, and stats keys."""
    mts = [make_metatile(solid(255, 0, 0)), make_metatile(solid(0, 0, 255))]
    result, _, _ = _run(tmp_path, mts)
    assert result.primary_name == "gTileset_Primary"
    assert result.secondary_name == "gTileset_Secondary"
    assert result.n_metatiles == 2
    assert result.n_tiles >= 2           # transparent tile 0 + at least one real tile
    assert result.n_palettes >= 1
    assert isinstance(result.stats, dict)
    assert "n_metatiles" in result.stats
    assert "n_gba_tiles" in result.stats


# ---------------------------------------------------------------------------
# 11. Edge: all-transparent metatile
# ---------------------------------------------------------------------------


def test_all_transparent_metatile(tmp_path):
    """An all-transparent metatile (both layers) → n_metatiles=1, n_tiles=1, all 8 slots tile 0."""
    mt = make_metatile(bottom=transparent(), top=transparent())
    result, pdir, _ = _run(tmp_path, [mt])
    assert result.n_metatiles == 1
    assert result.n_tiles == 1   # only the reserved transparent tile
    raw = (pdir / "metatiles.bin").read_bytes()
    vals = struct.unpack_from("<8H", raw, 0)
    for slot, v in enumerate(vals):
        assert (v & 0x3FF) == 0, (
            f"slot {slot}: expected tile index 0 for all-transparent metatile, got {v & 0x3FF}"
        )
