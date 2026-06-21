"""Image pipeline step 5 — emit GBA 4bpp binary artifacts for a tileset pair.

Turns rendered Uranium tiles (step-3 16×16 RGBA) into the four GBA binary artifacts
pokeemerald-expansion INCBINs per tileset — ``tiles.png`` (4bpp palette-indexed),
``metatiles.bin`` (8 little-endian u16 per metatile: 4 bottom-layer tile-entries +
4 zeroed top-layer slots), ``metatile_attributes.bin`` (1 u16 per metatile: behaviour +
layer-type), and ``palettes/NN.pal`` (JASC-PAL) — producing a PRIMARY + SECONDARY pair
for one Uranium tileset, and returns the Uranium tile_id → GBA metatile_id mapping.

GBA 4bpp layout (verified against engine/include/fieldmap.h HEAD 21c24202):
  - Each 8×8 "tile" references ONE sub-palette of ≤15 display colours; local index 0 is
    transparent.
  - Each 16×16 "metatile" is four 8×8 quadrants (bottom layer) plus four transparent
    slots (top layer), stored as 8 u16.
  - Primary holds global tile-indices / metatile-ids / palette-slots 0..511/512/5;
    secondary holds the rest up to 1024/1024/13.  Both dirs receive all 16 palette files
    (00.pal..15.pal); a palette lives in its home dir (primary if g<6, secondary if g≥6),
    all other files are all-black.

Pipeline position:
    sources → autotile → raster → quantize → **emit**  (this module)
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

# Both dirs receive files 00.pal..15.pal; slots 13-15 are always black (engine ignores)
_NUM_PAL_FILES: int = 16
_PALETTE_ENTRIES: int = 16   # 1 transparent slot + 15 display colours
_JASC_HEADER: str = "JASC-PAL\n0100\n16\n"
_TILES_PNG_WIDTH: int = 128  # 16 tiles across × 8 px each


@dataclass
class EmittedTileset:
    """Return value of ``emit_tileset``; describes the written artifacts."""

    primary_name: str
    secondary_name: str
    tile_to_metatile: dict[int, int]  # Uranium tile_id → global GBA metatile id
    n_metatiles: int                   # total metatiles (primary + secondary combined)
    n_tiles: int                       # total GBA tiles including transparent tile 0
    n_palettes: int                    # number of sub-palettes actually allocated
    stats: dict = field(default_factory=dict)


def emit_tileset(
    tile_ids: list[int],
    rasterizer: object,
    primary_dir: Path,
    secondary_dir: Path,
    primary_name: str,
    secondary_name: str,
    behavior_overrides: dict[int, int] | None = None,
    layer_type: int = 1,
    max_palettes: int = NUM_PALS_TOTAL,
) -> EmittedTileset:
    """Emit GBA binary artifacts for a PRIMARY + SECONDARY tileset pair.

    Parameters
    ----------
    tile_ids:
        Uranium tile_ids to include.  Each unique id becomes one GBA metatile;
        duplicates are dropped (first-seen wins).  ``metatile_id = position in the
        de-duplicated list``.
    rasterizer:
        Any object exposing ``.render(tile_id: int) -> PIL.Image`` (mode RGBA,
        16×16).  The real class is
        ``rpg2gba.tileset_converter.graphics.raster.TileRasterizer``; emit.py does
        not import or construct it so tests can inject stubs.
    primary_dir, secondary_dir:
        Destination directories for the two tileset halves.  Created (with a
        ``palettes/`` subdirectory) if they do not already exist.
    primary_name, secondary_name:
        ``gTileset_*`` symbol names chosen by the caller; stored verbatim in the
        return value (no C emission here).
    behavior_overrides:
        Maps a Uranium ``tile_id`` to the numeric metatile-behaviour value (e.g.
        ``MB_NON_ANIMATED_DOOR = 101``) to encode in that metatile's attribute instead
        of the default ``MB_NORMAL`` (0).  ``None`` → no overrides.
    layer_type:
        ``METATILE_LAYER_TYPE_*`` constant (0 = NORMAL, 1 = COVERED, 2 = SPLIT) to
        encode in every metatile attribute's bits 12-15.  Default 1 = COVERED.
    max_palettes:
        Maximum number of GBA sub-palettes the quantizer may allocate (≤13).
    """
    if behavior_overrides is None:
        behavior_overrides = {}

    # ------------------------------------------------------------------
    # Step 1 — de-duplicate tile_ids preserving first-seen order.
    #           metatile_id = index in the de-duped list.
    # ------------------------------------------------------------------
    seen: set[int] = set()
    deduped: list[int] = []
    for tid in tile_ids:
        if tid not in seen:
            seen.add(tid)
            deduped.append(tid)

    if not deduped:
        raise ValueError("tile_ids must not be empty (or all-duplicate with no unique id)")

    # Render and split each unique tile into four 8×8 quadrants.
    # Slot order: TL=(left=0,top=0), TR=(8,0), BL=(0,8), BR=(8,8)
    metatile_quads: list[list[np.ndarray]] = []
    for tid in deduped:
        img = rasterizer.render(tid)  # PIL RGBA 16×16
        quads: list[np.ndarray] = []
        for left, top in ((0, 0), (8, 0), (0, 8), (8, 8)):
            crop = img.crop((left, top, left + 8, top + 8))
            arr = np.asarray(crop, dtype=np.uint8)  # (8,8,4)
            quads.append(arr)
        metatile_quads.append(quads)

    # ------------------------------------------------------------------
    # Step 2 — de-duplicate 8×8 quadrants by raw bytes, preserving order.
    #           metatile_quad_indices[m][s] = index into unique_quads.
    # ------------------------------------------------------------------
    quad_bytes_to_idx: dict[bytes, int] = {}
    unique_quads: list[np.ndarray] = []
    metatile_quad_indices: list[list[int]] = []

    for quads in metatile_quads:
        slot_idxs: list[int] = []
        for quad in quads:
            key = quad.tobytes()
            if key not in quad_bytes_to_idx:
                quad_bytes_to_idx[key] = len(unique_quads)
                unique_quads.append(quad)
            slot_idxs.append(quad_bytes_to_idx[key])
        metatile_quad_indices.append(slot_idxs)

    # ------------------------------------------------------------------
    # Step 3 — palette quantization.
    #           Pass raw RGBA quadrants; the quantizer resolves alpha internally.
    # ------------------------------------------------------------------
    res = build_quantized_tileset(unique_quads, max_palettes=max_palettes)

    # ------------------------------------------------------------------
    # Step 4 — assign global GBA tile indices.
    #           Index 0 is reserved for the all-transparent tile.
    #           Indices 1..M are non-transparent unique quads in first-seen order.
    # ------------------------------------------------------------------
    unique_quad_to_gba: list[int] = []
    next_gba_idx = 1
    for i in range(len(unique_quads)):
        if res.tile_palette[i] == -1:
            unique_quad_to_gba.append(0)   # fully transparent → tile 0
        else:
            unique_quad_to_gba.append(next_gba_idx)
            next_gba_idx += 1
    n_gba_tiles = next_gba_idx  # includes the reserved transparent tile

    # ------------------------------------------------------------------
    # Step 5 — build 4-bit palette-index arrays (8×8 uint8, values 0-15) per
    #           non-transparent GBA tile.
    #
    #   Local palette slot 0 = transparent (never stored as a colour in the
    #   palette arrays).  For each opaque pixel, find which row of the assigned
    #   res.palettes[pi] matches its resolved RGB and store row_index + 1.
    # ------------------------------------------------------------------
    tile_pixels: dict[int, np.ndarray] = {0: np.zeros((8, 8), dtype=np.uint8)}

    for uq_i, gba_idx in enumerate(unique_quad_to_gba):
        if gba_idx == 0:
            continue  # transparent → already covered by tile_pixels[0]
        pi = res.tile_palette[uq_i]
        pal = res.palettes[pi]           # (N,3) uint8 display colours
        quad_rgba = res.quantized[uq_i]  # (8,8,4) uint8, alpha in {0,255}
        opaque = quad_rgba[..., 3] == 255
        rgb = quad_rgba[..., :3]
        indices = np.zeros((8, 8), dtype=np.uint8)
        # Assign each palette row to matching pixels; stored as row_index+1.
        for slot, color in enumerate(pal):
            matches = np.all(rgb == color, axis=-1) & opaque
            indices[matches] = np.uint8(slot + 1)
        tile_pixels[gba_idx] = indices

    # ------------------------------------------------------------------
    # Step 6 — build metatile tile-entries (8 u16 per metatile, LE).
    #   Bottom layer slots 0-3: (gba_tile_index & 0x3FF) | ((palnum & 0xF) << 12)
    #   Top layer slots 4-7: 0x0000 (transparent)
    # ------------------------------------------------------------------
    metatile_entries: list[list[int]] = []
    for quad_indices in metatile_quad_indices:
        entries: list[int] = []
        for uq_i in quad_indices:
            gba_tile = unique_quad_to_gba[uq_i]
            palnum = res.tile_palette[uq_i]
            if palnum < 0:
                palnum = 0  # transparent quad → palette 0 (arbitrary; tile index is 0)
            entries.append((gba_tile & 0x3FF) | ((palnum & 0xF) << 12))
        entries += [0x0000] * 4   # top layer: all transparent
        metatile_entries.append(entries)

    # ------------------------------------------------------------------
    # Step 7 — metatile attributes (1 u16 per metatile).
    #   u16 = (behaviour & 0x00FF) | ((layer_type & 0xF) << 12)
    # ------------------------------------------------------------------
    metatile_attrs: list[int] = []
    for tid in deduped:
        behavior = behavior_overrides.get(tid, 0)
        metatile_attrs.append((behavior & 0x00FF) | ((layer_type & 0xF) << 12))

    n_metatiles = len(deduped)

    # ------------------------------------------------------------------
    # Step 8 — write binary artifacts.
    # ------------------------------------------------------------------
    primary_dir = Path(primary_dir)
    secondary_dir = Path(secondary_dir)
    (primary_dir / "palettes").mkdir(parents=True, exist_ok=True)
    (secondary_dir / "palettes").mkdir(parents=True, exist_ok=True)

    # ── tiles.png (mode P, width=128, 8×8 tiles left-to-right) ─────────────
    def _write_tiles_png(path: Path, gba_indices: list[int]) -> None:
        """Write *gba_indices* as an indexed-colour PNG at their LOCAL positions.

        *gba_indices* is ordered by local tile position (0, 1, 2, …).  For the
        secondary half pass ``[512, 513, …]``; the enumerate loop places global
        tile 512 at local position 0, etc."""
        ntiles = max(1, len(gba_indices))
        nrows = (ntiles + 15) // 16
        arr = np.zeros((nrows * 8, _TILES_PNG_WIDTH), dtype=np.uint8)
        for local_t, gba_idx in enumerate(gba_indices):
            row = local_t // 16
            col = local_t % 16
            pix = tile_pixels.get(gba_idx, np.zeros((8, 8), dtype=np.uint8))
            arr[row * 8 : row * 8 + 8, col * 8 : col * 8 + 8] = pix
        img = Image.fromarray(arr, mode="P")
        # Exactly 16 palette entries (a grey ramp). gbagfx reads only the 4-bit
        # indices, not these display colours, but a .4bpp source PNG must declare
        # <=16 palette colours — a 256-entry palette makes gbagfx count 256 colours
        # and reject it, so the palette is capped at 16.
        grey = list(range(0, 256, 17))[:16]   # 0, 17, 34, …, 255
        pal_bytes: list[int] = []
        for v in grey:
            pal_bytes += [v, v, v]
        img.putpalette(pal_bytes)
        img.save(str(path))

    primary_gba = list(range(min(n_gba_tiles, NUM_TILES_IN_PRIMARY)))
    if not primary_gba:
        primary_gba = [0]
    _write_tiles_png(primary_dir / "tiles.png", primary_gba)

    secondary_gba = list(range(NUM_TILES_IN_PRIMARY, n_gba_tiles))
    if not secondary_gba:
        secondary_gba = [0]   # at least one all-transparent tile
    _write_tiles_png(secondary_dir / "tiles.png", secondary_gba)

    # ── metatiles.bin / metatile_attributes.bin ──────────────────────────────
    def _pack_metatiles(entries_list: list[list[int]]) -> bytes:
        buf = bytearray()
        for entries in entries_list:
            for e in entries:
                buf += struct.pack("<H", e)
        return bytes(buf)

    def _pack_attrs(attrs: list[int]) -> bytes:
        buf = bytearray()
        for a in attrs:
            buf += struct.pack("<H", a)
        return bytes(buf)

    prim_mt = metatile_entries[:NUM_METATILES_IN_PRIMARY] or [[0] * 8]
    prim_at = metatile_attrs[:NUM_METATILES_IN_PRIMARY] or [0]
    sec_mt = metatile_entries[NUM_METATILES_IN_PRIMARY:] or [[0] * 8]
    sec_at = metatile_attrs[NUM_METATILES_IN_PRIMARY:] or [0]

    (primary_dir / "metatiles.bin").write_bytes(_pack_metatiles(prim_mt))
    (primary_dir / "metatile_attributes.bin").write_bytes(_pack_attrs(prim_at))
    (secondary_dir / "metatiles.bin").write_bytes(_pack_metatiles(sec_mt))
    (secondary_dir / "metatile_attributes.bin").write_bytes(_pack_attrs(sec_at))

    # ── JASC-PAL files (00.pal..15.pal in BOTH dirs) ─────────────────────────
    #
    # Each dir gets all 16 files.  A palette g lives in its home dir:
    #   primary  if g < NUM_PALS_IN_PRIMARY (6)
    #   secondary if g ≥ NUM_PALS_IN_PRIMARY
    # The same file in the "away" dir is written as all-black so the engine
    # never reads stale data if it happens to open it.

    def _pal_text(colors: np.ndarray | None) -> str:
        """Render a 16-entry JASC-PAL file.

        Entry 0 is ``0 0 0`` (transparency placeholder).
        Entries 1..N come from *colors* (already 5-bit-expanded 8-bit display
        RGB, the quantizer's native output — gbagfx will >>3 them back to BGR555).
        Entries N+1..15 are padded with ``0 0 0``."""
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
        # Primary gets real colours for slots 0-5; secondary for 6-15.
        p_colors = colors if g < NUM_PALS_IN_PRIMARY else None
        s_colors = colors if g >= NUM_PALS_IN_PRIMARY else None
        (primary_dir / "palettes" / f"{g:02}.pal").write_text(
            _pal_text(p_colors), encoding="utf-8"
        )
        (secondary_dir / "palettes" / f"{g:02}.pal").write_text(
            _pal_text(s_colors), encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # Build and return the result.
    # ------------------------------------------------------------------
    tile_to_metatile: dict[int, int] = {tid: idx for idx, tid in enumerate(deduped)}
    stats: dict = dict(res.stats)
    stats["n_metatiles"] = n_metatiles
    stats["n_gba_tiles"] = n_gba_tiles

    logger.debug(
        "emit_tileset: %d input ids → %d metatiles, %d GBA tiles, %d palettes",
        len(tile_ids),
        n_metatiles,
        n_gba_tiles,
        n_palettes,
    )

    return EmittedTileset(
        primary_name=primary_name,
        secondary_name=secondary_name,
        tile_to_metatile=tile_to_metatile,
        n_metatiles=n_metatiles,
        n_tiles=n_gba_tiles,
        n_palettes=n_palettes,
        stats=stats,
    )
