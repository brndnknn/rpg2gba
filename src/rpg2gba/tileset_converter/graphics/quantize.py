"""Image pipeline step 4 — palette quantization to GBA 4bpp constraints.

Takes the step-3 16x16 RGBA tiles (their 8x8 quadrants) and reduces them to
GBA-legal sub-tiles: every 8x8 tile references ONE sub-palette of <=15 colours
(index 0 is transparent), a tileset uses <=N sub-palettes, and colours are 15-bit
(BGR555). Two lossy decisions, both locked with the user
(`reference/graphics_conversion_notes.md` §9/§10):

  - **binary alpha** (GBA 4bpp has no partial alpha): per-tile classify on the
    solid-opaque-body fraction (`classify_tile`). A tile with a real opaque body
    (tree canopy, fence) -> *threshold* (keep alpha>=128, drop the soft fringe). A
    bodyless semi-transparent wash (a shadow) -> *drop* (every partial pixel goes
    transparent, so the shadow falls away and the ground tile below shows through —
    the user rejected the earlier stipple checker, which shimmers when scrolling).
  - **colour reduction**: 15-bit, no dithering. This is a 15-colour palette-MERGING
    (bin-packing) problem, NOT k-means colour clustering — a census found 99% of 8x8
    tiles already have <=15 colours, so loss comes only from forcing tiles to SHARE a
    palette. `build_quantized_tileset` does it in two phases (global similarity-merge
    vocabulary, then agglomerative union-merge of tile colour-set bitmasks).

History (see §10): a Lloyd / greedy-FFD colour quantizer was tried first and snapped
minority colours to wrong nearests (paths->green, tree edges->white, tree shadow->
orange); the two-phase packer fixed it. Validate by EYE, not the mean-shift metric.
"""
from __future__ import annotations

import bisect
import colorsys
import logging
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)

COLORS_PER_PALETTE = 15          # index 0 is transparent -> 15 usable colours
DEFAULT_MAX_PALETTES = 13        # §7b: outdoor tilesets get ~13 of the 16 slots
ALPHA_OPAQUE_THRESHOLD = 128     # threshold-mode cutoff
# A tile with at least this fraction of fully-opaque pixels is an object-with-an-edge
# (tree canopy, fence) -> threshold; below it the tile is a semi-transparent shadow
# wash -> drop (the shadow falls away to transparent so the ground shows through,
# the same clean cutout as under the trees — no stipple). (Was a partial-alpha-
# FRACTION test, which mis-sent tree-canopy edges to a black fringe — see
# graphics_conversion_notes §10.)
SOLID_BODY_FRAC = 0.02


def to_5bit(rgb: np.ndarray) -> np.ndarray:
    """8-bit RGB -> GBA 5-bit-per-channel, expanded back to 8-bit for display.

    `c -> (c>>3<<3) | (c>>3>>2)`: drop the low 3 bits, replicate the top 2 into
    the tail so 31 maps to 255 (the standard GBA BGR555 display expansion)."""
    q = rgb.astype(np.uint16) >> 3
    return ((q << 3) | (q >> 2)).astype(np.uint8)


# --- binary alpha (per-tile classify) --------------------------------------


def classify_tile(alpha: np.ndarray) -> str:
    """'binary' (no partial alpha), 'threshold' (object edge), or 'drop' (shadow).

    Discriminator = does the tile have a solid opaque BODY. An object-with-an-edge
    (tree canopy, fence) is a solid region plus a soft partial-alpha fringe →
    threshold, which keeps the high-alpha true-colour edge and drops the low-alpha
    pixels (whose stored RGB is background-contaminated near-black in Uranium's art)
    = a clean cutout. A semi-transparent wash with little/no solid body is a shadow →
    drop: GBA 4bpp has no partial alpha, so rather than stipple it (a dithered checker
    that shimmers when scrolling — user-rejected) the shadow falls away to transparent
    and the ground tile below shows through, the same clean look as under the trees."""
    partial = (alpha > 0) & (alpha < 255)
    if not partial.any():
        return "binary"
    if (alpha == 255).mean() >= SOLID_BODY_FRAC:
        return "threshold"
    return "drop"


def resolve_alpha(tile: np.ndarray) -> np.ndarray:
    """RGBA uint8 (HxWx4) -> RGBA uint8 with alpha in {0,255} (per-tile classify).

    threshold: opaque where alpha >= 128 (keeps the body, drops the soft fringe).
    drop: only already-fully-opaque pixels stay; every partial-alpha pixel goes
    transparent, so a soft shadow wash disappears and the ground below shows."""
    out = tile.copy()
    alpha = tile[..., 3]
    mode = classify_tile(alpha)
    if mode == "binary":
        return out
    if mode == "threshold":
        keep = alpha >= ALPHA_OPAQUE_THRESHOLD
    else:  # drop
        keep = alpha == 255
    out[..., 3] = np.where(keep, 255, 0).astype(np.uint8)
    return out


# --- colour quantization ----------------------------------------------------


def _opaque_colors(tile: np.ndarray) -> np.ndarray:
    """Distinct 15-bit display colours of a resolved tile's opaque pixels, (M,3)."""
    opaque = tile[..., 3] == 255
    if not opaque.any():
        return np.empty((0, 3), np.uint8)
    return np.unique(to_5bit(tile[..., :3][opaque]), axis=0)


def _split_boxes(pixels: np.ndarray, k: int) -> list[np.ndarray]:
    """Median-cut (N,3) uint8 pixels into <=k boxes (population-balanced splits)."""
    pixels = to_5bit(pixels)
    boxes = [pixels]
    while len(boxes) < k:
        splittable = [b for b in boxes if len(np.unique(b, axis=0)) > 1]
        if not splittable:
            break
        box = max(splittable, key=lambda b: int((b.max(0) - b.min(0)).max()))
        boxes = [b for b in boxes if b is not box]
        axis = int((box.max(0) - box.min(0)).argmax())
        order = box[box[:, axis].argsort(kind="stable")]
        mid = len(order) // 2
        boxes.extend((order[:mid], order[mid:]))
    return boxes


def _median_cut(pixels: np.ndarray, k: int) -> np.ndarray:
    """Reduce (N,3) uint8 pixels to <=k representative 15-bit colours."""
    reps = [
        to_5bit(b.mean(0).round().astype(np.uint8)[None])[0]
        for b in _split_boxes(pixels, k)
        if len(b)
    ]
    return np.unique(np.array(reps, np.uint8), axis=0)


@dataclass
class QuantizeResult:
    """Per-input-tile quantization outcome plus the shared sub-palettes."""

    palettes: list[np.ndarray]   # each (<=15,3) uint8 display colours; idx 0 transparent
    tile_palette: list[int]      # sub-palette index per input tile (-1 = empty tile)
    quantized: list[np.ndarray]  # rgba uint8, alpha-resolved + colour-remapped
    stats: dict = field(default_factory=dict)
    # One entry per input tile (index-aligned with quantized/tile_palette).  For tile i,
    # a list of (orig_rgb8, final_rgb8) pairs over that tile's DISTINCT original 8-bit
    # opaque colours.  orig_rgb8 is the 8-bit RGB from the resolved tile BEFORE any
    # to_5bit reduction; final_rgb8 is the 8-bit palette colour it snapped to (capturing
    # both the 8→5-bit truncation and the palette snap in a single arrow).
    # Empty / fully-transparent tiles get [].
    color_map: list[list[tuple[tuple[int, int, int], tuple[int, int, int]]]] = field(
        default_factory=list
    )


def _nearest(colors: np.ndarray, vocab: np.ndarray) -> np.ndarray:
    """Index of the nearest `vocab` colour for each row of `colors` (squared dist)."""
    return ((colors[:, None, :].astype(np.int32) - vocab[None, :, :]) ** 2).sum(2).argmin(1)


def build_quantized_tileset(
    tiles: list[np.ndarray],
    *,
    max_palettes: int = DEFAULT_MAX_PALETTES,
    colors_per_palette: int = COLORS_PER_PALETTE,
    weights: list[int] | None = None,
    global_colors: int | None = None,
    iterations: int = 8,
) -> QuantizeResult:
    """Quantize a list of 8x8 RGBA tiles into <=`max_palettes` GBA sub-palettes.

    Input tiles are raw step-3 output (any alpha); binary-alpha resolution and 15-bit
    reduction happen inside. **This is a palette-MERGING (15-colour bin-packing)
    problem, not k-means colour clustering** — a census of Moki Town found 99% of 8x8
    tiles already have <=15 distinct colours (median 5), so each tile is losslessly
    representable by one palette; the only loss comes from forcing tiles to SHARE a
    palette when their combined colour set exceeds 15. Treating it as k-means (the old
    Lloyd-with-median-cut-refit) lossily reduced palettes that didn't need reducing and
    snapped minority colours to whatever was nearest in an incoherent palette (paths
    turned green, tree-edge green turned white, tree-shadow green turned orange).

    Two phases instead:
      1. **Global vocabulary** — median-cut the tileset's distinct colours down to
         `global_colors` (default `max_palettes*colors_per_palette`). This sheds the
         excess by merging *similar* colours only (dark green -> slightly-different
         dark green, invisible) — never across families. Every tile's colours are
         remapped to this shared vocabulary.
      2. **Agglomerative tile packing** — represent each tile's colour set as a bitmask
         over the vocabulary and greedily merge the two palettes with the smallest
         colour UNION until <=`max_palettes` remain (tiles that share colours cluster,
         so palettes stay coherent). Only a palette that still exceeds 15 colours is
         locally reduced (merge its nearest colours), so any residual loss is a
         within-palette near-merge, never a cross-family snap.

    `weights`/`iterations` are accepted for API stability but unused (the area bias
    `weights` carried was the original bug). Returns the sub-palettes, per-tile palette
    index (-1 = empty tile), the remapped RGBA tiles, and loss stats."""
    _ = (weights, iterations)  # retained for API compatibility
    resolved = [resolve_alpha(t) for t in tiles]
    n = len(tiles)

    # Per-tile opaque pixels (5-bit) and opaque mask; None == fully transparent tile.
    tile_px: list[np.ndarray | None] = []
    tile_mask: list[np.ndarray] = []
    for t in resolved:
        opaque = t[..., 3] == 255
        tile_mask.append(opaque)
        tile_px.append(to_5bit(t[..., :3][opaque]) if opaque.any() else None)
    nonempty = [i for i, p in enumerate(tile_px) if p is not None]

    tile_palette = [-1] * n
    palettes_u8: list[np.ndarray] = []

    if nonempty:
        # --- Phase 1: global colour vocabulary (similarity merge only) -------------
        distinct = np.unique(np.concatenate([tile_px[i] for i in nonempty]), axis=0)
        ng = global_colors if global_colors is not None else max_palettes * colors_per_palette
        vocab = _median_cut(distinct, ng).astype(np.int16) if len(distinct) > ng else distinct
        # Map every tile's pixels to vocabulary indices; the tile's colour SET = bitmask.
        tile_gidx: dict[int, np.ndarray] = {}
        tile_set: dict[int, int] = {}
        for i in nonempty:
            gidx = _nearest(tile_px[i], vocab)
            tile_gidx[i] = gidx
            mask = 0
            for g in np.unique(gidx):
                mask |= 1 << int(g)
            tile_set[i] = mask

        # --- Phase 2: agglomerative tile packing on colour-set bitmasks ------------
        # Start from unique colour-sets (many tiles share one); track their members.
        groups: dict[int, list[int]] = {}
        for i in nonempty:
            groups.setdefault(tile_set[i], []).append(i)
        masks = list(groups.keys())
        members = [list(groups[m]) for m in masks]

        def union_size(a: int, b: int) -> int:
            return (a | b).bit_count()

        # Greedy: repeatedly merge the pair with the smallest colour union.
        while len(masks) > max_palettes:
            best, bi, bj = None, -1, -1
            for x in range(len(masks)):
                mx = masks[x]
                for y in range(x + 1, len(masks)):
                    u = (mx | masks[y]).bit_count()
                    if best is None or u < best:
                        best, bi, bj = u, x, y
                        if u == mx.bit_count():  # y is a subset of x: can't beat this
                            break
            masks[bi] |= masks[bj]
            members[bi].extend(members[bj])
            del masks[bj]
            del members[bj]

        # Materialise palettes; locally reduce any that still exceed the colour budget.
        for pi, (mask, mem) in enumerate(zip(masks, members)):
            idxs = [b for b in range(vocab.shape[0]) if mask & (1 << b)]
            pal = vocab[idxs]
            if len(pal) > colors_per_palette:
                pal = _median_cut(pal.astype(np.uint8), colors_per_palette).astype(np.int16)
            palettes_u8.append(pal.astype(np.uint8))
            for i in mem:
                tile_palette[i] = pi

    # --- Remap each tile's pixels onto its assigned palette ------------------------
    quantized: list[np.ndarray] = []
    shift_acc: list[np.ndarray] = []
    color_map: list[list[tuple[tuple[int, int, int], tuple[int, int, int]]]] = []
    for i, t in enumerate(resolved):
        out = t.copy()
        pi = tile_palette[i]
        opaque = tile_mask[i]
        if pi >= 0 and tile_px[i] is not None and len(palettes_u8[pi]):
            px = tile_px[i].astype(np.int16)
            pal = palettes_u8[pi].astype(np.int16)
            new = pal[_nearest(px, pal)]
            rgb = out[..., :3].copy()
            rgb[opaque] = new.astype(np.uint8)
            out[..., :3] = rgb
            shift_acc.append(np.abs((px >> 3) - (new >> 3)).mean(1))
            # Capture per-tile mapping: distinct original 8-bit colours → final palette colours.
            # orig8 is aligned 1:1 with new (both ordered by the opaque pixel mask).
            orig8 = t[..., :3][opaque]                         # (M,3) uint8 pre-to_5bit
            uniq8, idx = np.unique(orig8, axis=0, return_index=True)
            finals = new[idx].astype(np.uint8)  # representative final per distinct orig
            color_map.append([
                (
                    (int(o[0]), int(o[1]), int(o[2])),
                    (int(f[0]), int(f[1]), int(f[2])),
                )
                for o, f in zip(uniq8, finals)
            ])
        else:
            color_map.append([])
        quantized.append(out)

    all_shift = np.concatenate(shift_acc) if shift_acc else np.zeros(1)
    stats = {
        "n_tiles": n,
        "n_palettes": len(palettes_u8),
        "max_colors": max((len(p) for p in palettes_u8), default=0),
        "mean_shift_5bit": float(all_shift.mean()),
        "max_shift_5bit": float(all_shift.max()),
        "p95_shift_5bit": float(np.percentile(all_shift, 95)),
    }
    return QuantizeResult(
        palettes=palettes_u8,
        tile_palette=tile_palette,
        quantized=quantized,
        stats=stats,
        color_map=color_map,
    )


# ---------------------------------------------------------------------------
# Family packer — the pipeline's production palette packer (since 2026-06-26)
# ---------------------------------------------------------------------------
# `build_quantized_tileset` packs the whole tileset in one global merge.  The family
# packer instead partitions tiles by their dominant hue family, gives each family its
# own slice of the palette budget (so a foliage tile never shares a sub-palette with a
# wall tile), and packs each family with the global packer.  Validated by eye across
# the slice maps as the better-looking default, so `build_slice_tilesets` (and the map
# viewer) use it.  `build_quantized_tileset` is kept as the prior strategy / fallback.
# (`build_quantized_tileset_diversity`, the other A/B alternate, stays in
# experimental_packers.py.)

_NO_VOCAB_CUT = 10**9  # global_colors high enough to disable phase-1 vocab merge


@dataclass(frozen=True)
class FamilyParams:
    dark_value: int = 40          # max(r,g,b) < dark_value  → "dark"
    neutral_sat: float = 0.18     # HSV saturation < neutral_sat → "neutral"
    green_cuts: tuple[float, ...] = ()  # interior hue° in (70,170) splitting green into sub-bands
    palette_floor: int = 1        # minimum palettes guaranteed to each family
    overflow_weight: str = "colors"  # "colors"=distinct overflow; "coverage"=tile-weighted


def _dominant_family(tile: np.ndarray, params: FamilyParams = FamilyParams()) -> str | None:
    """Hue family of a tile's DOMINANT (most-pixels) opaque 5-bit colour.

    ``None`` for a fully-transparent tile. Coarse bins: low-value -> ``dark``,
    low-saturation -> ``neutral``, else a hue wedge (red/brown/yellow/green/cyan/
    blue/purple). With non-empty ``params.green_cuts``, the green band [70,170) is
    split into sub-families ``green0``, ``green1``, …"""
    res = resolve_alpha(tile)
    opaque = res[..., 3] == 255
    if not opaque.any():
        return None
    px = to_5bit(res[..., :3][opaque])
    colors, counts = np.unique(px, axis=0, return_counts=True)
    r, g, b = (int(v) for v in colors[counts.argmax()])
    if max(r, g, b) < params.dark_value:
        return "dark"
    h, s, _v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    if s < params.neutral_sat:
        return "neutral"
    deg = h * 360
    if deg < 15 or deg >= 345:
        return "red"
    if deg < 45:
        return "brown"
    if deg < 70:
        return "yellow"
    if deg < 170:
        if not params.green_cuts:
            return "green"
        cuts = sorted(c for c in params.green_cuts if 70 < c < 170)
        if not cuts:
            return "green"
        idx = bisect.bisect_right(cuts, deg)
        return f"green{idx}"
    if deg < 200:
        return "cyan"
    if deg < 255:
        return "blue"
    return "purple"


def _pack_subset(
    tiles: list[np.ndarray],
    idxs: list[int],
    budget: int,
    offset: int,
    palettes: list[np.ndarray],
    tile_palette: list[int],
    quantized: list[np.ndarray | None],
    color_map: list,
) -> int:
    """Quantize ``tiles[idxs]`` into <=``budget`` palettes (no phase-1 vocab cut, so
    the merge stays within the subset) and splice the result into the global lists at
    palette ``offset``. Returns the next free palette offset."""
    if not idxs or budget <= 0:
        return offset
    r = build_quantized_tileset(
        [tiles[i] for i in idxs], max_palettes=budget, global_colors=_NO_VOCAB_CUT
    )
    for local_i, gi in enumerate(idxs):
        lp = r.tile_palette[local_i]
        tile_palette[gi] = -1 if lp < 0 else offset + lp
        quantized[gi] = r.quantized[local_i]
        color_map[gi] = r.color_map[local_i]
    palettes.extend(r.palettes)
    return offset + len(r.palettes)


def _assemble(
    tiles: list[np.ndarray],
    palettes: list[np.ndarray],
    tile_palette: list[int],
    quantized: list[np.ndarray | None],
    color_map: list,
) -> QuantizeResult:
    for i, q in enumerate(quantized):
        if q is None:
            quantized[i] = resolve_alpha(tiles[i])
    return QuantizeResult(
        palettes=palettes,
        tile_palette=tile_palette,
        quantized=quantized,  # type: ignore[arg-type]
        color_map=color_map,
        stats={"n_palettes": len(palettes)},
    )


def _allocate_by_overflow(
    distinct: dict[str, int],
    total: int,
    *,
    counts: dict[str, int] | None = None,
    floor: int = 1,
    mode: str = "colors",
) -> dict[str, int]:
    """Give every group ``floor`` palettes, then hand each remaining palette to the
    group with the most overflow.

    ``mode="colors"`` (default): overflow = ``distinct - alloc*COLORS_PER_PALETTE``;
    identical to the original hardcoded behaviour when ``floor=1``.
    ``mode="coverage"``: overflow = ``counts * (distinct - alloc*COLORS_PER_PALETTE)``;
    requires ``counts``; large-coverage families win ties against high-distinct-but-rare
    ones.
    """
    groups = list(distinct)
    if len(groups) * floor > total:
        raise ValueError(
            f"{len(groups)} groups × floor {floor} = {len(groups) * floor} exceed {total} palettes"
        )
    alloc = {g: floor for g in groups}
    for _ in range(total - len(groups) * floor):
        if mode == "coverage":
            assert counts is not None, "counts required for mode='coverage'"
            g = max(groups, key=lambda g: counts[g] * (distinct[g] - alloc[g] * COLORS_PER_PALETTE))
            if counts[g] * (distinct[g] - alloc[g] * COLORS_PER_PALETTE) <= 0:
                break
        else:  # "colors"
            g = max(groups, key=lambda g: distinct[g] - alloc[g] * COLORS_PER_PALETTE)
            if distinct[g] - alloc[g] * COLORS_PER_PALETTE <= 0:
                break
        alloc[g] += 1
    return alloc


def build_quantized_tileset_family(
    tiles: list[np.ndarray], *, max_palettes: int = DEFAULT_MAX_PALETTES,
    params: FamilyParams | None = None,
) -> QuantizeResult:
    """Partition tiles by their dominant hue family, pour the palette budget into the
    families that overflow most, pack each family with the global packer.

    The pipeline's production packer.  Pass a :class:`FamilyParams` to tune hue-bin
    boundaries, green-band splits, per-family palette floor, and overflow weighting;
    omitting ``params`` reproduces the stock behaviour exactly."""
    params = params or FamilyParams()
    n = len(tiles)
    fam_of = [_dominant_family(t, params) for t in tiles]
    fam_tiles: dict[str, list[int]] = defaultdict(list)
    for i, f in enumerate(fam_of):
        if f is not None:
            fam_tiles[f].append(i)

    fam_distinct = {
        f: len(np.unique(
            np.concatenate([_opaque_colors(resolve_alpha(tiles[i])) for i in idxs]), axis=0))
        for f, idxs in fam_tiles.items()
    }
    fam_counts = {f: len(idxs) for f, idxs in fam_tiles.items()}
    budget = _allocate_by_overflow(
        fam_distinct, max_palettes,
        counts=fam_counts,
        floor=params.palette_floor,
        mode=params.overflow_weight,
    )

    palettes: list[np.ndarray] = []
    tile_palette = [-1] * n
    quantized: list[np.ndarray | None] = [None] * n
    color_map: list = [[] for _ in range(n)]
    offset = 0
    for f, idxs in fam_tiles.items():
        offset = _pack_subset(tiles, idxs, budget[f], offset,
                              palettes, tile_palette, quantized, color_map)
    return _assemble(tiles, palettes, tile_palette, quantized, color_map)
