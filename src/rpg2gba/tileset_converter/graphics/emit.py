"""Image pipeline step 5 — emit GBA 4bpp binary artifacts for a tileset pair.

Packs a list of 2-layer metatiles (each a bottom + top 16×16 RGBA image) into the
four GBA artifacts pokeemerald-expansion INCBINs per tileset — ``tiles.png`` (4bpp
palette-indexed), ``metatiles.bin`` (8 little-endian u16/metatile = 4 bottom-layer +
4 top-layer tile-entries), ``metatile_attributes.bin`` (1 u16/metatile: behaviour +
layer-type), and ``palettes/NN.pal`` (JASC-PAL) — across a PRIMARY + SECONDARY pair.

Two-layer metatiles let a transparent overlay (tree, fence) reveal the ground tile
beneath it: ``bottom`` is the composited ground, ``top`` the overlay. The caller
(the S8a pre-pass) renders/composites; emit only packs.

8×8 dedup is **flip-aware** (a tile and its mirror share one stored tile, referenced
via the GBA tile-entry's h/v-flip bits) and runs again **after quantization** (two
raw tiles that snap to the same palette+pixels merge) — both needed to fit the
1024-tile budget once ground+overlay column combinations multiply.

GBA layout (verified vs engine/include/fieldmap.h HEAD 21c24202): 8 tiles/16 B per
metatile, 2 B/attr (Emerald); tile-entry = tile(0-9) | hflip(10) | vflip(11) |
palette(12-15); primary holds tiles/metatiles/palettes 0..511/512/5, secondary the rest.
"""
from __future__ import annotations

import logging
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from rpg2gba.tileset_converter.graphics.quantize import build_quantized_tileset

logger = logging.getLogger(__name__)

# GBA partition constants (verified from engine/include/fieldmap.h HEAD 21c24202)
NUM_TILES_IN_PRIMARY: int = 512
NUM_METATILES_IN_PRIMARY: int = 512
NUM_PALS_IN_PRIMARY: int = 6
NUM_PALS_TOTAL: int = 13
NUM_TILES_TOTAL: int = 1024
NUM_METATILES_TOTAL: int = 1024

# METATILE_LAYER_TYPE_* (engine/include/global.fieldmap.h)
LAYER_NORMAL: int = 0   # tile-layers -> middle + top BG (top above the player)
LAYER_COVERED: int = 1  # tile-layers -> bottom + middle BG (both below the player)

_NUM_PAL_FILES: int = 16
_PALETTE_ENTRIES: int = 16
_JASC_HEADER: str = "JASC-PAL\n0100\n16\n"
_TILES_PNG_WIDTH: int = 128  # 16 tiles across × 8 px


@dataclass
class MetatileImage:
    """One metatile as its two BG tile-layers (16×16 RGBA) plus attributes.

    ``bottom`` draws under ``top``; ``top`` is all-transparent for a single-layer
    metatile. ``layer_type`` is a ``METATILE_LAYER_TYPE_*`` value (whether ``top``
    sits above the player), ``behavior`` a ``MB_*`` value (0 = MB_NORMAL)."""

    bottom: np.ndarray            # (16,16,4) uint8 RGBA
    top: np.ndarray               # (16,16,4) uint8 RGBA (all-transparent if none)
    layer_type: int = LAYER_COVERED
    behavior: int = 0


@dataclass
class EmittedTileset:
    """Return value of ``emit_tileset``; describes the written artifacts."""

    primary_name: str
    secondary_name: str
    n_metatiles: int
    n_tiles: int        # total GBA tiles incl. the transparent tile 0
    n_palettes: int
    stats: dict = field(default_factory=dict)


def _quadrants(img: np.ndarray) -> list[np.ndarray]:
    """Split a (16,16,4) tile into its four 8×8 quadrants [TL, TR, BL, BR]."""
    return [
        img[0:8, 0:8], img[0:8, 8:16], img[8:16, 0:8], img[8:16, 8:16],
    ]


def _flip_canonical(quad: np.ndarray) -> tuple[bytes, np.ndarray, int, int]:
    """Pick the canonical (smallest-bytes) flip orientation of an 8×8 quad.

    Returns ``(key, canon_array, hflip, vflip)``: the stored tile is ``canon_array``;
    applying the (hflip, vflip) flip to it reproduces ``quad`` (flips are involutions,
    so the orientation that maps quad→canon is the same that maps canon→quad)."""
    orients = [
        ((0, 0), quad),
        ((1, 0), quad[:, ::-1]),
        ((0, 1), quad[::-1, :]),
        ((1, 1), quad[::-1, ::-1]),
    ]
    (h, v), canon = min(orients, key=lambda kv: kv[1].tobytes())
    canon = np.ascontiguousarray(canon)
    return canon.tobytes(), canon, h, v


def emit_tileset(
    metatiles: list[MetatileImage],
    primary_dir: Path,
    secondary_dir: Path,
    primary_name: str,
    secondary_name: str,
    *,
    max_palettes: int = NUM_PALS_TOTAL,
) -> EmittedTileset:
    """Pack ``metatiles`` (metatile id = list index) into a PRIMARY+SECONDARY pair.

    Writes ``tiles.png`` / ``palettes/NN.pal`` / ``metatiles.bin`` /
    ``metatile_attributes.bin`` under ``primary_dir`` and ``secondary_dir``."""
    if not metatiles:
        raise ValueError("metatiles must not be empty")

    # --- Step 1: per-metatile 8 quadrants (bottom slots 0-3, top slots 4-7),
    #     flip-canonicalised + deduped into a shared tile pool. ----------------
    canon_to_idx: dict[bytes, int] = {}
    unique_canon: list[np.ndarray] = []
    # per metatile: list of 8 (canon_index, hflip, vflip)
    metatile_slots: list[list[tuple[int, int, int]]] = []

    for mt in metatiles:
        quads = _quadrants(mt.bottom) + _quadrants(mt.top)
        if len(quads) != 8:
            raise AssertionError("expected 8 quadrants per metatile")
        slots: list[tuple[int, int, int]] = []
        for quad in quads:
            quad = np.asarray(quad, dtype=np.uint8)
            key, canon, h, v = _flip_canonical(quad)
            idx = canon_to_idx.get(key)
            if idx is None:
                idx = len(unique_canon)
                canon_to_idx[key] = idx
                unique_canon.append(canon)
            slots.append((idx, h, v))
        metatile_slots.append(slots)

    # --- Step 2: quantize the shared tile pool. -------------------------------
    res = build_quantized_tileset(unique_canon, max_palettes=max_palettes)

    # --- Step 2.5: post-quantization merge. ----------------------------------
    # Flip-canonical dedup (Step 1) ran on RAW RGBA, before colours were snapped
    # to 5-bit palettes.  Two distinct raw tiles can quantize to the SAME palette
    # AND the SAME pixels — they then write byte-identical entries to tiles.png and
    # carry the same palette field, so they can share one stored GBA tile.  This is
    # a no-loss merge (the colours are already the quantizer's own output) and is
    # what keeps a column-keyed tileset under the 1024-tile hardware budget once
    # ground+overlay combinations multiply.  Fully-transparent tiles (palette -1)
    # collapse to the reserved transparent tile 0.
    merged_of: list[int] = [0] * len(unique_canon)  # canon idx -> merged idx (-1 = tile 0)
    merge_key_to_idx: dict[tuple[int, bytes], int] = {}
    merged_palette: list[int] = []           # merged idx -> palette num
    merged_quantized: list[np.ndarray] = []  # merged idx -> (8,8,4) quantized RGBA
    for i in range(len(unique_canon)):
        pal = res.tile_palette[i]
        if pal == -1:
            merged_of[i] = -1
            continue
        key = (pal, res.quantized[i].tobytes())
        m = merge_key_to_idx.get(key)
        if m is None:
            m = len(merged_palette)
            merge_key_to_idx[key] = m
            merged_palette.append(pal)
            merged_quantized.append(res.quantized[i])
        merged_of[i] = m

    # --- Step 3: assign global GBA tile indices (0 = transparent tile). -------
    merged_gba: list[int] = list(range(1, len(merged_palette) + 1))
    n_gba_tiles = len(merged_palette) + 1

    # --- Step 4: 4bpp pixel arrays per GBA tile (local palette indices). ------
    tile_pixels: dict[int, np.ndarray] = {0: np.zeros((8, 8), dtype=np.uint8)}
    for m, gba_idx in enumerate(merged_gba):
        pal = res.palettes[merged_palette[m]]
        quad_rgba = merged_quantized[m]
        opaque = quad_rgba[..., 3] == 255
        rgb = quad_rgba[..., :3]
        indices = np.zeros((8, 8), dtype=np.uint8)
        for slot, color in enumerate(pal):
            indices[np.all(rgb == color, axis=-1) & opaque] = np.uint8(slot + 1)
        tile_pixels[gba_idx] = indices

    # --- Step 5: metatile tile-entries (8 u16/metatile). ----------------------
    metatile_entries: list[list[int]] = []
    for slots in metatile_slots:
        entries: list[int] = []
        for canon_idx, h, v in slots:
            m = merged_of[canon_idx]
            if m == -1:
                gba_tile, palnum = 0, 0
            else:
                gba_tile, palnum = merged_gba[m], merged_palette[m]
            entries.append(
                (gba_tile & 0x3FF) | (h << 10) | (v << 11) | ((palnum & 0xF) << 12)
            )
        metatile_entries.append(entries)

    # --- Step 6: metatile attributes (1 u16/metatile). ------------------------
    metatile_attrs = [
        (mt.behavior & 0x00FF) | ((mt.layer_type & 0xF) << 12) for mt in metatiles
    ]
    n_metatiles = len(metatiles)

    # Fail loud on a budget overrun BEFORE writing any artifact (column-keying can
    # multiply tiles/metatiles past the hardware limits — don't leave a malformed
    # tiles.png in the fork on the way to raising).
    if n_gba_tiles > NUM_TILES_TOTAL:
        raise ValueError(
            f"{primary_name}: {n_gba_tiles} GBA tiles exceeds the {NUM_TILES_TOTAL} "
            f"hardware limit (primary+secondary)"
        )
    if n_metatiles > NUM_METATILES_TOTAL:
        raise ValueError(
            f"{primary_name}: {n_metatiles} metatiles exceeds {NUM_METATILES_TOTAL}"
        )

    # --- Step 7: write artifacts. ---------------------------------------------
    primary_dir = Path(primary_dir)
    secondary_dir = Path(secondary_dir)
    (primary_dir / "palettes").mkdir(parents=True, exist_ok=True)
    (secondary_dir / "palettes").mkdir(parents=True, exist_ok=True)

    def _write_tiles_png(path: Path, gba_indices: list[int]) -> None:
        ntiles = max(1, len(gba_indices))
        nrows = (ntiles + 15) // 16
        arr = np.zeros((nrows * 8, _TILES_PNG_WIDTH), dtype=np.uint8)
        for local_t, gba_idx in enumerate(gba_indices):
            row, col = local_t // 16, local_t % 16
            pix = tile_pixels.get(gba_idx, np.zeros((8, 8), dtype=np.uint8))
            arr[row * 8 : row * 8 + 8, col * 8 : col * 8 + 8] = pix
        img = Image.fromarray(arr, mode="P")
        # Exactly 16 palette entries (gbagfx reads only the 4-bit indices; a 256-
        # entry palette makes it count 256 colours and reject the .4bpp).
        grey = list(range(0, 256, 17))[:16]
        pal_bytes: list[int] = []
        for vv in grey:
            pal_bytes += [vv, vv, vv]
        img.putpalette(pal_bytes)
        img.save(str(path))

    primary_gba = list(range(min(n_gba_tiles, NUM_TILES_IN_PRIMARY))) or [0]
    _write_tiles_png(primary_dir / "tiles.png", primary_gba)
    secondary_gba = list(range(NUM_TILES_IN_PRIMARY, n_gba_tiles)) or [0]
    _write_tiles_png(secondary_dir / "tiles.png", secondary_gba)

    def _pack(rows: list[list[int]] | list[int]) -> bytes:
        buf = bytearray()
        for r in rows:
            for e in (r if isinstance(r, list) else [r]):
                buf += struct.pack("<H", e)
        return bytes(buf)

    prim_mt = metatile_entries[:NUM_METATILES_IN_PRIMARY] or [[0] * 8]
    prim_at = metatile_attrs[:NUM_METATILES_IN_PRIMARY] or [0]
    sec_mt = metatile_entries[NUM_METATILES_IN_PRIMARY:] or [[0] * 8]
    sec_at = metatile_attrs[NUM_METATILES_IN_PRIMARY:] or [0]
    (primary_dir / "metatiles.bin").write_bytes(_pack(prim_mt))
    (primary_dir / "metatile_attributes.bin").write_bytes(_pack(prim_at))
    (secondary_dir / "metatiles.bin").write_bytes(_pack(sec_mt))
    (secondary_dir / "metatile_attributes.bin").write_bytes(_pack(sec_at))

    def _pal_text(colors: np.ndarray | None) -> str:
        lines = [_JASC_HEADER, "0 0 0\n"]
        if colors is not None and len(colors):
            for row in colors:
                lines.append(f"{int(row[0])} {int(row[1])} {int(row[2])}\n")
            remaining = _PALETTE_ENTRIES - 1 - len(colors)
        else:
            remaining = _PALETTE_ENTRIES - 1
        lines += ["0 0 0\n"] * remaining
        return "".join(lines)

    n_palettes = len(res.palettes)
    for g in range(_NUM_PAL_FILES):
        colors = res.palettes[g] if g < n_palettes else None
        p_colors = colors if g < NUM_PALS_IN_PRIMARY else None
        s_colors = colors if g >= NUM_PALS_IN_PRIMARY else None
        (primary_dir / "palettes" / f"{g:02}.pal").write_text(
            _pal_text(p_colors), encoding="utf-8"
        )
        (secondary_dir / "palettes" / f"{g:02}.pal").write_text(
            _pal_text(s_colors), encoding="utf-8"
        )

    stats = dict(res.stats)
    stats["n_metatiles"] = n_metatiles
    stats["n_gba_tiles"] = n_gba_tiles
    logger.debug(
        "emit_tileset %s: %d metatiles, %d GBA tiles, %d palettes",
        primary_name, n_metatiles, n_gba_tiles, n_palettes,
    )
    return EmittedTileset(
        primary_name=primary_name,
        secondary_name=secondary_name,
        n_metatiles=n_metatiles,
        n_tiles=n_gba_tiles,
        n_palettes=n_palettes,
        stats=stats,
    )
