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
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from rpg2gba.tileset_converter.graphics.quantize import (
    QuantizeResult,
    build_quantized_tileset,
    frame_opaque_colors,
    quantize_tile_to_palette,
)

logger = logging.getLogger(__name__)

# GBA partition constants (verified from engine/include/fieldmap.h HEAD 21c24202)
NUM_TILES_IN_PRIMARY: int = 512
NUM_METATILES_IN_PRIMARY: int = 512
NUM_PALS_IN_PRIMARY: int = 6
NUM_PALS_TOTAL: int = 13
NUM_TILES_TOTAL: int = 1024
NUM_METATILES_TOTAL: int = 1024

# Fail-loud ceiling on a single tileset's animation frame art, in ROM bytes.
# Animated tiles cost VRAM once (n_tiles) but ROM per frame: an effect stores
# n_tiles * n_frames * TILE_SIZE_4BPP(32) bytes of .4bpp art. The frame-count
# guard in build_slice_tilesets.py bounds the *period*; this bounds the thing
# that actually runs out. 128 KiB per tileset is deliberately generous next to
# the ~7 MB of ROM headroom the corpus-scaling audit measured (2026-07-14 §5
# item 5 asked for exactly this per-column ROM-cost accounting); Route 01's
# 95-frame pond+waterfall effect is the first case that needs the room.
MAX_ANIM_ROM_BYTES: int = 128 * 1024
TILE_SIZE_4BPP: int = 32

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
    # Animation frames 1..N-1 (frame 0 IS bottom/top above); None/[] = static.
    # Each entry is a (bottom, top) pair, same shape/dtype as bottom/top.
    frames: list[tuple[np.ndarray, np.ndarray]] | None = None


@dataclass
class TilesetAnimEffect:
    """One animated-tile effect emitted alongside a tileset's PRIMARY art.

    ``first_tile_index``/``n_tiles`` describe a CONTIGUOUS block of GBA tile
    indices (always < NUM_TILES_IN_PRIMARY) that the engine DMA-swaps every frame;
    ``rel_dir`` (relative to the primary output dir) holds the per-frame PNGs
    (``{rel_dir}/f{NN}.png``), one per ``n_frames``, atlas-ordered 16 tiles/row —
    frame 0's PNG is byte-identical to the corresponding region of ``tiles.png``."""

    name: str
    first_tile_index: int
    n_tiles: int
    n_frames: int
    rel_dir: str


@dataclass
class EmittedTileset:
    """Return value of ``emit_tileset``; describes the written artifacts."""

    primary_name: str
    secondary_name: str
    n_metatiles: int
    n_tiles: int        # total GBA tiles incl. the transparent tile 0
    n_palettes: int
    stats: dict = field(default_factory=dict)
    effects: list[TilesetAnimEffect] = field(default_factory=list)


@dataclass
class QuadrantPalette:
    """Palette info for one 8×8 quadrant slot within a metatile."""

    palette_index: int  # index into PaletteAnalysis.palettes; -1 if fully transparent
    # each entry is (orig_rgb8, final_rgb8) for a distinct opaque source colour
    color_changes: list[tuple[tuple[int, int, int], tuple[int, int, int]]]


@dataclass
class MetatilePalette:
    """Per-metatile palette summary: 8 quadrant slots (0-3 = bottom, 4-7 = top),
    plus the reassembled quantized layer images for the post-quant preview."""

    quadrants: list[QuadrantPalette]  # length 8
    quant_bottom: np.ndarray          # (16,16,4) uint8 RGBA, alpha-resolved + colour-snapped
    quant_top: np.ndarray             # (16,16,4) uint8 RGBA (all-transparent if no overlay)


@dataclass
class PaletteAnalysis:
    """Read-only palette analysis for a list of metatiles; written by no files."""

    palettes: list[list[tuple[int, int, int]]]  # sub-palettes as (r,g,b) 8-bit display colours
    metatiles: list[MetatilePalette]             # same order and length as the input metatiles


def _quadrants(img: np.ndarray) -> list[np.ndarray]:
    """Split a (16,16,4) tile into its four 8×8 quadrants [TL, TR, BL, BR]."""
    return [
        img[0:8, 0:8], img[0:8, 8:16], img[8:16, 0:8], img[8:16, 8:16],
    ]


def _flip_canonical_multi(
    frames: list[np.ndarray],
) -> tuple[bytes, list[np.ndarray], int, int]:
    """Pick the canonical (smallest-bytes) flip orientation of a quadrant's WHOLE
    frame sequence (frame 0 first), applying the SAME flip to every frame.

    Returns ``(key, canon_frames, hflip, vflip)``: ``key`` is the concatenation of
    every canonical frame's bytes (dedup identity — two quadrants merge into one
    pool entry only if their entire animation matches); ``canon_frames[0]`` is what
    a single-frame (static) quad's `_flip_canonical` returned before this function
    existed, so a length-1 ``frames`` list reproduces that exactly."""
    orients = (
        (0, 0, lambda q: q),
        (1, 0, lambda q: q[:, ::-1]),
        (0, 1, lambda q: q[::-1, :]),
        (1, 1, lambda q: q[::-1, ::-1]),
    )
    best: tuple[bytes, list[np.ndarray], int, int] | None = None
    for h, v, fn in orients:
        transformed = [np.ascontiguousarray(fn(f)) for f in frames]
        key = b"".join(t.tobytes() for t in transformed)
        if best is None or key < best[0]:
            best = (key, transformed, h, v)
    assert best is not None
    return best


def _effective_frames(frames: list[np.ndarray]) -> list[np.ndarray]:
    """Drop redundant animation frames: if every later frame is byte-identical to
    frame 0, the quadrant is really STATIC (an animated tile buried under opaque
    art, or a template whose frames happen to coincide) — collapse to ``[frame0]``
    so it dedups/merges/indexes exactly like a genuinely static quadrant."""
    if len(frames) <= 1:
        return frames
    f0 = frames[0]
    if all(np.array_equal(f, f0) for f in frames[1:]):
        return [f0]
    return frames


def _slot_frames_for_metatile(mt: MetatileImage) -> list[list[np.ndarray]]:
    """8 quadrant slots (0-3 bottom, 4-7 top), each a frame-ordered (frame 0 first)
    list of that quadrant's 8x8 uint8 arrays across ``mt.frames``."""
    base = _quadrants(mt.bottom) + _quadrants(mt.top)
    per_slot: list[list[np.ndarray]] = [
        [np.asarray(base[s], dtype=np.uint8)] for s in range(8)
    ]
    for fb, ft in mt.frames or []:
        fq = _quadrants(fb) + _quadrants(ft)
        for s in range(8):
            per_slot[s].append(np.asarray(fq[s], dtype=np.uint8))
    return per_slot


def _canonicalize_and_quantize(
    metatiles: list[MetatileImage],
    *,
    max_palettes: int = NUM_PALS_TOTAL,
    quantizer: Callable[..., QuantizeResult] = build_quantized_tileset,
) -> tuple[list[np.ndarray], list[list[tuple[int, int, int]]], QuantizeResult, list[list[np.ndarray]]]:
    """Steps 1+2 shared core: build flip-canonical tile pool, per-metatile slot
    mapping, and quantize the pool.

    Dedup identity (Step 1) is now the quadrant's WHOLE animation trajectory
    (`_flip_canonical_multi`, frame 0 first) — a quadrant whose later frames all
    equal frame 0 is demoted to static first (`_effective_frames`), so this
    automatically folds an animated tile buried under opaque land back to one
    static pool entry. Quantization (Step 2) still runs on frame-0 arrays only
    (``unique_canon`` is unchanged shape/meaning for the quantizer); the extra
    frames ride along in ``canon_frames`` and their colours are unioned into
    `extra_tile_colors` so the quantizer widens each animated tile's palette to
    cover every frame (emit_tileset then quantizes the extra frames themselves
    against that palette in Step 2.4).

    Returns ``(unique_canon, metatile_slots, quant, canon_frames)`` where:
    - ``unique_canon``: deduplicated flip-canonical 8×8 frame-0 tile arrays.
    - ``metatile_slots``: for each metatile, 8 ``(canon_idx, hflip, vflip)`` entries.
    - ``quant``: the ``QuantizeResult`` keyed to ``unique_canon``.
    - ``canon_frames``: per canon idx, its full (post-flip, post-demotion) frame
      list (frame 0 first); length 1 for a static quadrant."""
    if not metatiles:
        raise ValueError("metatiles must not be empty")
    canon_to_idx: dict[bytes, int] = {}
    unique_canon: list[np.ndarray] = []
    canon_frames: list[list[np.ndarray]] = []
    metatile_slots: list[list[tuple[int, int, int]]] = []

    for mt in metatiles:
        per_slot_frames = _slot_frames_for_metatile(mt)
        if len(per_slot_frames) != 8:
            raise AssertionError("expected 8 quadrants per metatile")
        slots: list[tuple[int, int, int]] = []
        for frame_list in per_slot_frames:
            frame_list = _effective_frames(frame_list)
            key, transformed, h, v = _flip_canonical_multi(frame_list)
            idx = canon_to_idx.get(key)
            if idx is None:
                idx = len(unique_canon)
                canon_to_idx[key] = idx
                unique_canon.append(transformed[0])
                canon_frames.append(transformed)
            slots.append((idx, h, v))
        metatile_slots.append(slots)

    extra_tile_colors: dict[int, np.ndarray] = {}
    for i, frames in enumerate(canon_frames):
        if len(frames) > 1:
            cols = [frame_opaque_colors(f) for f in frames[1:]]
            cols = [c for c in cols if len(c)]
            if cols:
                extra_tile_colors[i] = np.unique(np.concatenate(cols), axis=0)

    quant = quantizer(
        unique_canon, max_palettes=max_palettes,
        extra_tile_colors=extra_tile_colors or None,
    )
    return unique_canon, metatile_slots, quant, canon_frames


def _quant_to_indices(quad_rgba: np.ndarray, pal: list[tuple[int, int, int]]) -> np.ndarray:
    """Quantized (8,8,4) RGBA -> (8,8) uint8 GBA 4bpp local palette indices
    (0 = transparent, 1-15 = ``pal`` row+1)."""
    opaque = quad_rgba[..., 3] == 255
    rgb = quad_rgba[..., :3]
    indices = np.zeros((8, 8), dtype=np.uint8)
    for slot, color in enumerate(pal):
        indices[np.all(rgb == color, axis=-1) & opaque] = np.uint8(slot + 1)
    return indices


def _tiles_to_indexed_image(tiles_px: list[np.ndarray]) -> Image.Image:
    """Pack a list of (8,8) uint8 index arrays into a 16-tiles/row mode-P PNG
    (grey ramp palette — gbagfx reads only the 4-bit indices, not the RGB)."""
    ntiles = max(1, len(tiles_px))
    nrows = (ntiles + 15) // 16
    arr = np.zeros((nrows * 8, _TILES_PNG_WIDTH), dtype=np.uint8)
    for local_t, pix in enumerate(tiles_px):
        row, col = local_t // 16, local_t % 16
        arr[row * 8 : row * 8 + 8, col * 8 : col * 8 + 8] = pix
    img = Image.fromarray(arr, mode="P")
    # Exactly 16 palette entries (gbagfx reads only the 4-bit indices; a 256-
    # entry palette makes it count 256 colours and reject the .4bpp).
    grey = list(range(0, 256, 17))[:16]
    pal_bytes: list[int] = []
    for vv in grey:
        pal_bytes += [vv, vv, vv]
    img.putpalette(pal_bytes)
    return img


def _apply_flip(arr: np.ndarray, h: int, v: int) -> np.ndarray:
    """Reproduce the original quad from its flip-canonical form (flips are involutions).

    Mirrors the orientation encoding in ``_flip_canonical``: h flips columns, v rows."""
    if h:
        arr = arr[:, ::-1]
    if v:
        arr = arr[::-1, :]
    return np.ascontiguousarray(arr)


def _reassemble_quantized(
    slots: list[tuple[int, int, int]], quant: QuantizeResult
) -> tuple[np.ndarray, np.ndarray]:
    """Rebuild a metatile's quantized 16×16 bottom/top from its 8 canonical quadrant
    slots, un-flipping each quantized 8×8 back to the metatile's own orientation.

    These are the exact pixels emit packs into ``tiles.png`` for this metatile."""
    bottom = np.zeros((16, 16, 4), dtype=np.uint8)
    top = np.zeros((16, 16, 4), dtype=np.uint8)
    positions = [(0, 0), (0, 8), (8, 0), (8, 8)]  # [TL, TR, BL, BR]
    for layer, base in ((bottom, 0), (top, 4)):
        for q, (r, c) in enumerate(positions):
            canon_idx, h, v = slots[base + q]
            quad = _apply_flip(np.asarray(quant.quantized[canon_idx], dtype=np.uint8), h, v)
            layer[r : r + 8, c : c + 8] = quad
    return bottom, top


def analyze_tileset_palettes(
    metatiles: list[MetatileImage],
    *,
    max_palettes: int = NUM_PALS_TOTAL,
    quantizer: Callable[..., QuantizeResult] = build_quantized_tileset,
) -> PaletteAnalysis:
    """Return a read-only palette analysis for ``metatiles``; writes no files.

    For each metatile, reports the sub-palette index and colour-change pairs for
    each of the 8 quadrant slots (0-3 = bottom layer, 4-7 = top layer).  A fully-
    transparent quadrant gets ``palette_index=-1`` and ``color_changes=[]``.

    ``max_palettes`` and ``quantizer`` are forwarded to the packer so callers (e.g.
    the live map viewer) can swap in the family packer with tuned parameters.

    The void metatile (all-transparent) and any warp-copy duplicate a caller may
    append do not affect palette assignment, so callers may omit them — the
    returned palette indices and colours are identical either way."""
    _, metatile_slots, quant, _canon_frames = _canonicalize_and_quantize(
        metatiles, max_palettes=max_palettes, quantizer=quantizer
    )

    # Convert quant.palettes (list of (<=15,3) uint8 arrays) to list[list[tuple]].
    palettes: list[list[tuple[int, int, int]]] = [
        [(int(row[0]), int(row[1]), int(row[2])) for row in pal]
        for pal in quant.palettes
    ]

    mt_palettes: list[MetatilePalette] = []
    for slots in metatile_slots:
        quadrant_pals: list[QuadrantPalette] = []
        for canon_idx, _h, _v in slots:
            pi = quant.tile_palette[canon_idx]
            cmap = quant.color_map[canon_idx]
            quadrant_pals.append(QuadrantPalette(palette_index=pi, color_changes=cmap))
        quant_bottom, quant_top = _reassemble_quantized(slots, quant)
        mt_palettes.append(
            MetatilePalette(
                quadrants=quadrant_pals, quant_bottom=quant_bottom, quant_top=quant_top
            )
        )

    return PaletteAnalysis(palettes=palettes, metatiles=mt_palettes)


def emit_tileset(
    metatiles: list[MetatileImage],
    primary_dir: Path,
    secondary_dir: Path,
    primary_name: str,
    secondary_name: str,
    *,
    max_palettes: int = NUM_PALS_TOTAL,
    quantizer: Callable[..., QuantizeResult] = build_quantized_tileset,
) -> EmittedTileset:
    """Pack ``metatiles`` (metatile id = list index) into a PRIMARY+SECONDARY pair.

    Writes ``tiles.png`` / ``palettes/NN.pal`` / ``metatiles.bin`` /
    ``metatile_attributes.bin`` under ``primary_dir`` and ``secondary_dir``.

    ``quantizer`` selects the palette-packing strategy (default
    ``build_quantized_tileset``); alternate packers must share its signature and
    return a :class:`QuantizeResult`.  The metatile *ordering* is independent of the
    quantizer, so two emissions of the same ``metatiles`` with different packers
    produce interchangeable ``metatiles.bin`` (same ids) over different tile/palette
    data — which is what lets a single layout drive several palette variants."""
    # --- Steps 1+2: flip-canonical dedup + quantize (shared with analyzer). ---
    unique_canon, metatile_slots, res, canon_frames = _canonicalize_and_quantize(
        metatiles, max_palettes=max_palettes, quantizer=quantizer
    )

    # --- Step 2.4: quantize each animated tile's EXTRA frames against the ONE
    # palette its frame-0 (unique_canon[i]) was assigned. `extra_tile_colors`
    # (built in _canonicalize_and_quantize) already widened that palette to cover
    # every frame's colours, so this is a lossless remap, not a fresh quantize.
    canon_frame_quant: list[list[np.ndarray]] = []
    for i, frames in enumerate(canon_frames):
        pal_num = res.tile_palette[i]
        if pal_num == -1 or len(frames) <= 1:
            canon_frame_quant.append([res.quantized[i]])
            continue
        pal = res.palettes[pal_num]
        canon_frame_quant.append(
            [res.quantized[i]] + [quantize_tile_to_palette(f, pal) for f in frames[1:]]
        )

    # --- Step 2.5: post-quantization merge. ----------------------------------
    # Flip-canonical dedup (Step 1) ran on RAW RGBA, before colours were snapped
    # to 5-bit palettes.  Two distinct raw tiles can quantize to the SAME palette
    # AND THE SAME PIXELS ACROSS EVERY FRAME — they then write byte-identical
    # entries to tiles.png (and every anim frame PNG) and carry the same palette
    # field, so they can share one stored GBA tile.  This is a no-loss merge (the
    # colours are already the quantizer's own output) and is what keeps a
    # column-keyed tileset under the 1024-tile hardware budget once ground+overlay
    # combinations multiply.  A static tile only merges with another static tile
    # (frame-count-1 key); an animated tile only merges with one sharing its exact
    # frame count AND every frame's bytes.  Fully-transparent tiles (palette -1)
    # collapse to the reserved transparent tile 0.
    merged_of: list[int] = [0] * len(unique_canon)  # canon idx -> merged idx (-1 = tile 0)
    merge_key_to_idx: dict[tuple[int, tuple[bytes, ...]], int] = {}
    merged_palette: list[int] = []                      # merged idx -> palette num
    merged_quant_frames: list[list[np.ndarray]] = []    # merged idx -> [frame0, frame1, ...]
    for i in range(len(unique_canon)):
        pal = res.tile_palette[i]
        if pal == -1:
            merged_of[i] = -1
            continue
        key = (pal, tuple(f.tobytes() for f in canon_frame_quant[i]))
        m = merge_key_to_idx.get(key)
        if m is None:
            m = len(merged_palette)
            merge_key_to_idx[key] = m
            merged_palette.append(pal)
            merged_quant_frames.append(canon_frame_quant[i])
        merged_of[i] = m

    # --- Step 3: assign global GBA tile indices (0 = transparent tile). -------
    # Animated tiles (merged frame count > 1) get a CONTIGUOUS block per distinct
    # frame count ("effect"), right after reserved tile 0, entirely inside the
    # PRIMARY partition (indices < NUM_TILES_IN_PRIMARY) — the engine DMA-copies
    # one effect's whole block per frame tick, which requires contiguity. Static
    # tiles fill the remaining indices afterward, in first-merged order (unchanged
    # from the pre-animation behaviour).
    animated_groups: dict[int, list[int]] = {}  # n_frames -> [merged idx, ...]
    static_merged: list[int] = []
    for m, frames in enumerate(merged_quant_frames):
        if len(frames) > 1:
            animated_groups.setdefault(len(frames), []).append(m)
        else:
            static_merged.append(m)

    merged_gba_list: list[int] = [0] * len(merged_palette)
    effects: list[TilesetAnimEffect] = []
    next_idx = 1
    for n_frames in sorted(animated_groups):
        group = animated_groups[n_frames]
        first = next_idx
        for m in group:
            merged_gba_list[m] = next_idx
            next_idx += 1
        name = f"anim{n_frames}"
        effects.append(TilesetAnimEffect(name, first, len(group), n_frames, f"anim/{name}"))
    if next_idx > NUM_TILES_IN_PRIMARY:
        raise ValueError(
            f"{primary_name}: {next_idx - 1} animated tiles (indices 1.."
            f"{next_idx - 1}) exceed the {NUM_TILES_IN_PRIMARY}-tile PRIMARY "
            "partition — an animated effect must stay entirely in PRIMARY for "
            "the engine's DMA block copy"
        )

    # ROM-cost accounting for the frame art (see MAX_ANIM_ROM_BYTES). VRAM cost is
    # already bounded by the PRIMARY check above — this is the per-frame ROM the
    # INCGFX_U16 frame tables pull in, which is what a long-period effect actually
    # spends.
    anim_rom_bytes = sum(eff.n_tiles * eff.n_frames * TILE_SIZE_4BPP for eff in effects)
    if effects:
        logger.info(
            "%s: %d animated tile(s) in %d effect(s) [%s] -> %.1f KiB frame art",
            primary_name,
            next_idx - 1,
            len(effects),
            ", ".join(f"{eff.n_tiles}x{eff.n_frames}f" for eff in effects),
            anim_rom_bytes / 1024,
        )
    if anim_rom_bytes > MAX_ANIM_ROM_BYTES:
        raise ValueError(
            f"{primary_name}: animation frame art is {anim_rom_bytes} bytes "
            f"({anim_rom_bytes / 1024:.1f} KiB), over the {MAX_ANIM_ROM_BYTES}-byte "
            f"per-tileset budget — effects: "
            + ", ".join(f"{eff.name}={eff.n_tiles} tiles x {eff.n_frames} frames"
                        for eff in effects)
        )
    for m in static_merged:
        merged_gba_list[m] = next_idx
        next_idx += 1
    n_gba_tiles = next_idx

    # --- Step 4: 4bpp pixel arrays per GBA tile (local palette indices). ------
    # tiles.png (and any static-tile atlas region) always holds FRAME 0 — the
    # resting frame everything but the anim-frame DMA callback ever sees.
    tile_pixels: dict[int, np.ndarray] = {0: np.zeros((8, 8), dtype=np.uint8)}
    for m, gba_idx in enumerate(merged_gba_list):
        pal = res.palettes[merged_palette[m]]
        tile_pixels[gba_idx] = _quant_to_indices(merged_quant_frames[m][0], pal)

    # --- Step 5: metatile tile-entries (8 u16/metatile). ----------------------
    metatile_entries: list[list[int]] = []
    for slots in metatile_slots:
        entries: list[int] = []
        for canon_idx, h, v in slots:
            m = merged_of[canon_idx]
            if m == -1:
                gba_tile, palnum = 0, 0
            else:
                gba_tile, palnum = merged_gba_list[m], merged_palette[m]
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
        pix_list = [tile_pixels.get(g, np.zeros((8, 8), dtype=np.uint8)) for g in gba_indices]
        _tiles_to_indexed_image(pix_list).save(str(path))

    primary_gba = list(range(min(n_gba_tiles, NUM_TILES_IN_PRIMARY))) or [0]
    _write_tiles_png(primary_dir / "tiles.png", primary_gba)
    secondary_gba = list(range(NUM_TILES_IN_PRIMARY, n_gba_tiles)) or [0]
    _write_tiles_png(secondary_dir / "tiles.png", secondary_gba)

    # --- Step 7.5: animated-effect frame PNGs (frame 0's PNG == the tiles.png
    # region above, by construction — same tile_pixels/_quant_to_indices source).
    # merged_gba_list maps a merged tile to its GBA index; invert per effect block.
    gba_to_merged = {gba: m for m, gba in enumerate(merged_gba_list)}
    for eff in effects:
        eff_dir = primary_dir / eff.rel_dir
        eff_dir.mkdir(parents=True, exist_ok=True)
        block = [gba_to_merged[i] for i in range(eff.first_tile_index,
                                                   eff.first_tile_index + eff.n_tiles)]
        for f in range(eff.n_frames):
            pix_list = [
                _quant_to_indices(merged_quant_frames[m][f], res.palettes[merged_palette[m]])
                for m in block
            ]
            _tiles_to_indexed_image(pix_list).save(str(eff_dir / f"f{f:02}.png"))

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
        effects=effects,
    )
