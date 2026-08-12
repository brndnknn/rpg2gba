"""Uranium species battler art -> pokeemerald-expansion GBA battler converter (W2).

Converts each starter species' Uranium `Graphics/Battlers/*.png` art into the
64x64, 4bpp (15 opaque colours + transparent) front/back battler PNGs and
JASC-PAL palettes the vendored engine expects, per `STARTER_SPECIES_PLAN.md`
§4 "W2 — Battler converter".

Source quirks (all verified against `$RPG2GBA_URANIUM_SRC`, not re-derived
here -- see the plan doc):

  - Front battlers `NNN[s].png` are horizontal filmstrips, 80x80 per frame.
    Uranium's own starter-select UI treats the LAST frame as the static
    resting pose -- that's the frame this module extracts.
  - Back battlers `NNN[s]b.png` are a single 160x160 image (natively 2x the
    64x64 target -- the clean case for the majority-vote downscale below).
  - Shiny variants are separate PNG files, not palette swaps of the normal
    art, and are geometrically independent sources -- METALYNX's front strip
    is 80 frames vs. its shiny's 77, so "same frame index" is not a safe
    correspondence; "each art's own last frame" is (see
    `_check_shiny_geometry`).
  - Some files ship with an uppercase `.PNG` extension; every source path
    below is resolved through `common.resolve_case`.

Pipeline per species, ORCHYNX-first per the plan's sequencing (see
`convert_species_battler`):

  1. Extract normal + shiny raw art (front last frame, back single image).
  2. Fail loud if shiny's opaque geometry has diverged too far from normal's
     (`_check_shiny_geometry`) -- a wrong shiny palette from bad
     correspondence is exactly the silent-wrong CLAUDE.md §4.5 exists to
     prevent.
  3. Fit the NORMAL art onto the shared 64x64 canvas (crop-to-bbox + center,
     integer 2x-majority-vote downscale first if the bbox doesn't fit) and
     record the placement as a `FitPlan`.
  4. Jointly quantize normal front+back (union of their opaque pixels) to
     ONE shared <=15-colour palette -- the engine shares one `gMonPalette_X`
     between a species' front and back sprite, so they must be quantized
     together, not independently (`_joint_quantize`, reusing
     `tileset_converter.graphics.quantize.build_quantized_tileset`, the
     pipeline's production palette-merging packer).
  5. Replay the SAME `FitPlan` on the shiny source art (`_apply_fit_plan`),
     so shiny pixels land at identical canvas coordinates to their normal
     counterparts, then build an index-compatible shiny palette by sampling
     the modal shiny colour at each normal-palette slot's pixel positions
     (`_build_shiny_palette`) -- shiny is a palette, not an image; the
     engine swaps it under the SAME indices at render time.
  6. Write `anim_front.png` / `back.png` (indexed against the normal
     palette) and `normal.pal` / `shiny.pal` (JASC-PAL) under
     `output_dir/<asset_dir_name>/`, plus a `battlers.json` sidecar carrying
     the computed Y offsets for the staging emitter (W1) to consume.

Y offsets: `frontPicYOffset`/`backPicYOffset` are, per
`engine/include/pokemon.h`, "the number of pixels between the drawn pixel
area and the bottom edge" -- i.e. exactly the empty margin below the
centered opaque bbox on the 64x64 canvas (`_y_offset`). Uranium's
`metrics.dat` holds the game's own values but is unparsed; bbox-derived
offsets plus later eye-tuning is the accepted approach for six species
(STARTER_SPECIES_PLAN.md §4, out-of-scope list).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from rpg2gba.species_converter.common import (
    BACK_PNG,
    BATTLER_MAX_COLORS,
    BATTLER_SIZE,
    FRONT_PNG,
    NORMAL_PAL,
    SHINY_PAL,
    STARTER_SPECIES,
    SpeciesSpec,
    asset_dir_name,
    resolve_case,
    uranium_battler_back,
    uranium_battler_front,
)
from rpg2gba.tileset_converter.graphics.quantize import build_quantized_tileset
from rpg2gba.tileset_converter.graphics.sprites import (
    _binarize_alpha,
    _downscale_2x_majority,
)

logger = logging.getLogger(__name__)

FRONT_FRAME_SIZE = 80  # one filmstrip frame, front battlers
BACK_NATIVE_SIZE = 160  # back battlers ship at exactly 2x the 64x64 target

SIDECAR_NAME = "battlers.json"

# Max fraction of the union-opaque pixels that may differ between the normal
# and shiny extraction before this module refuses to build a shiny palette
# from it. Measured 2026-07-18 across all 6 starters' real assets: worst
# case is METALYNX's front (species 002, 80 vs 77 filmstrip frames) at
# ~0.23% -- an antialiasing/rounding-level discrepancy from each art taking
# its OWN last frame, not a real pose mismatch. A genuine correspondence
# failure (e.g. sampling the wrong frame index) produces a wholly different
# silhouette -- tens of percent, not fractions of one. 5% leaves >20x
# headroom over the worst real case while still catching a real mismatch by
# a wide margin.
SHINY_GEOMETRY_MAX_DIVERGENCE = 0.05

_JASC_HEADER = "JASC-PAL\n0100\n16\n"
_PALETTE_ENTRIES = 16  # index 0 (transparent placeholder) + up to 15 colours


@dataclass(frozen=True)
class FitPlan:
    """Recipe used to place one extracted battler frame onto the shared
    BATTLER_SIZE canvas -- recorded so the IDENTICAL placement can be
    replayed on the shiny source art (`_apply_fit_plan`). That replay is
    what makes palette-slot pixel-position sampling for shiny valid: without
    it, normal and shiny would each get their own (possibly different)
    crop/center offsets and slot N's pixels wouldn't line up between them.
    """

    downscale_rounds: int
    bbox: tuple[int, int, int, int]  # x0, x1, y0, y1 (inclusive), post-downscale space
    top: int
    left: int


@dataclass(frozen=True)
class BattlerConversionResult:
    """Per-species record of a battler conversion, also the sidecar JSON schema."""

    internal_name: str
    uranium_id: int
    front_path: Path
    back_path: Path
    normal_pal_path: Path
    shiny_pal_path: Path
    front_y_offset: int
    back_y_offset: int
    opaque_color_count: int
    front_shiny_divergence: float
    back_shiny_divergence: float

    def to_json_dict(self) -> dict[str, object]:
        d = asdict(self)
        for key in ("front_path", "back_path", "normal_pal_path", "shiny_pal_path"):
            d[key] = str(d[key])
        return d


# --- Extraction ------------------------------------------------------------


def _load_rgba(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGBA"))


def _extract_front_last_frame(path: Path, label: str) -> np.ndarray:
    """Extract the last frame of a `NNN[s].png` horizontal filmstrip (80x80
    cells; Uranium's starter-select UI treats the last frame as the static
    resting pose -- see module docstring)."""
    arr = _load_rgba(path)
    h, w = arr.shape[:2]
    if h != FRONT_FRAME_SIZE or w % FRONT_FRAME_SIZE:
        raise ValueError(
            f"{label}: filmstrip {path} is {w}x{h}, expected height "
            f"{FRONT_FRAME_SIZE} and a width divisible by it"
        )
    return _binarize_alpha(arr[:, w - FRONT_FRAME_SIZE :])


def _extract_back(path: Path, label: str) -> np.ndarray:
    """Extract a `NNN[s]b.png` single-image back battler (160x160)."""
    arr = _load_rgba(path)
    h, w = arr.shape[:2]
    if (w, h) != (BACK_NATIVE_SIZE, BACK_NATIVE_SIZE):
        raise ValueError(
            f"{label}: back battler {path} is {w}x{h}, expected "
            f"{BACK_NATIVE_SIZE}x{BACK_NATIVE_SIZE}"
        )
    return _binarize_alpha(arr)


# --- Shiny geometry gate -----------------------------------------------------


def _opaque_mask(arr: np.ndarray) -> np.ndarray:
    return arr[..., 3] > 0


def _geometry_divergence(a: np.ndarray, b: np.ndarray) -> float:
    """Fraction of the union-opaque pixels where `a`/`b` disagree on
    opacity. 0.0 = identical silhouettes. `a`/`b` must be same-shaped."""
    if a.shape[:2] != b.shape[:2]:
        # Different native shapes are as good as maximally divergent --
        # there is no shared coordinate space to compare pixel-for-pixel.
        return 1.0
    oa, ob = _opaque_mask(a), _opaque_mask(b)
    union = oa | ob
    if not union.any():
        return 0.0
    mismatch = oa != ob
    return float(np.count_nonzero(mismatch & union)) / float(np.count_nonzero(union))


def _check_shiny_geometry(normal: np.ndarray, shiny: np.ndarray, label: str) -> float:
    """Fail loud if shiny's opaque silhouette has diverged too far from
    normal's to safely sample a shiny palette by pixel position (see module
    docstring and `SHINY_GEOMETRY_MAX_DIVERGENCE`)."""
    divergence = _geometry_divergence(normal, shiny)
    if divergence > SHINY_GEOMETRY_MAX_DIVERGENCE:
        raise ValueError(
            f"{label}: shiny art geometry diverges {divergence:.1%} from the "
            f"normal art (threshold {SHINY_GEOMETRY_MAX_DIVERGENCE:.0%}) -- "
            f"refusing to build a shiny palette by pixel-position sampling "
            f"against mismatched silhouettes. This usually means the "
            f"extracted frames aren't the same pose (e.g. a filmstrip "
            f"frame-count mismatch was sampled at the same index instead of "
            f"each art's own last frame)."
        )
    return divergence


# --- Shiny registration (rigid-translation correction) -----------------------

#: Bounded search radius (pixels, each axis) for `_register_shiny`'s integer
#: translation search. Cheap at these sizes (80x80 / 160x160): (2*8+1)^2 =
#: 289 candidate offsets, each one `_geometry_divergence` call over a small
#: boolean array.
SHINY_REGISTRATION_MAX_SHIFT = 8


def _translate(arr: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """Shift `arr` by `dx` columns and `dy` rows (positive = right/down),
    zero-filling whatever shifts in from outside the frame. Shape-preserving
    -- unlike `np.roll`, content that shifts past an edge is dropped, not
    wrapped, which is the correct behaviour for image content."""
    out = np.zeros_like(arr)
    h, w = arr.shape[:2]
    src_x0, src_x1 = max(0, -dx), min(w, w - dx)
    src_y0, src_y1 = max(0, -dy), min(h, h - dy)
    if src_x1 <= src_x0 or src_y1 <= src_y0:
        return out
    dst_x0, dst_x1 = max(0, dx), min(w, w + dx)
    dst_y0, dst_y1 = max(0, dy), min(h, h + dy)
    out[dst_y0:dst_y1, dst_x0:dst_x1] = arr[src_y0:src_y1, src_x0:src_x1]
    return out


def _register_shiny(
    normal: np.ndarray,
    shiny: np.ndarray,
    label: str,
    *,
    max_shift: int = SHINY_REGISTRATION_MAX_SHIFT,
) -> tuple[np.ndarray, float, tuple[int, int]]:
    """Align `shiny` to `normal` by integer pixel translation before running
    the geometry gate, so a shiny source that's merely shifted a few pixels
    from its normal counterpart (first found on OWTEN: `035s.png` vs
    `035.png` -- identical opaque pixel count, 1505 both, offset by exactly
    (+2, +2)) registers and passes instead of being rejected as a mismatched
    pose. This does NOT weaken `SHINY_GEOMETRY_MAX_DIVERGENCE` -- a
    genuinely different shiny (wrong pose, wrong species) still fails loud,
    now reporting the best offset the search found and its residual
    divergence, so the two failure cases (real mismatch vs. an
    out-of-range shift) are distinguishable.

    The identity offset (0, 0) is checked FIRST and is the fast path: an
    already-registered pair is returned as the SAME array object with zero
    extra work, so this is a pure no-op add for every species that doesn't
    need it (verified: byte-identical emitted art for the six starters
    before/after this function existed).

    Search is a small bounded grid over `dx, dy` in
    `[-max_shift, max_shift]` (289 candidates at the default radius) --
    deliberately simple per the brief, no cross-correlation or subpixel
    fitting.

    Returns `(aligned_shiny, divergence, (dx, dy))` where `(dx, dy)` is the
    offset FROM normal TO shiny (i.e. shiny's silhouette sits at normal's
    position + `(dx, dy)`; aligning means translating shiny by `(-dx, -dy)`).
    """
    base_divergence = _geometry_divergence(normal, shiny)
    if base_divergence <= SHINY_GEOMETRY_MAX_DIVERGENCE:
        return shiny, base_divergence, (0, 0)

    best_offset = (0, 0)
    best_divergence = base_divergence
    best_shifted = shiny
    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            if dx == 0 and dy == 0:
                continue
            shifted = _translate(shiny, -dx, -dy)
            divergence = _geometry_divergence(normal, shifted)
            if divergence < best_divergence:
                best_divergence = divergence
                best_offset = (dx, dy)
                best_shifted = shifted

    if best_divergence > SHINY_GEOMETRY_MAX_DIVERGENCE:
        raise ValueError(
            f"{label}: shiny art geometry diverges {base_divergence:.1%} from the "
            f"normal art at zero offset (threshold {SHINY_GEOMETRY_MAX_DIVERGENCE:.0%}). "
            f"Best integer translation found within +/-{max_shift}px is {best_offset} "
            f"with residual divergence {best_divergence:.1%}, still over threshold -- "
            f"this isn't a simple registration offset, refusing to build a shiny "
            f"palette by pixel-position sampling against mismatched silhouettes."
        )

    logger.info(
        "%s: shiny art required registration offset %s to pass the geometry gate "
        "(divergence %.1f%% -> %.1f%%)",
        label,
        best_offset,
        base_divergence * 100,
        best_divergence * 100,
    )
    return best_shifted, best_divergence, best_offset


# --- Fit to the 64x64 canvas -------------------------------------------------


def _opaque_bbox(arr: np.ndarray, label: str) -> tuple[int, int, int, int]:
    ys, xs = np.where(_opaque_mask(arr))
    if xs.size == 0:
        raise ValueError(f"{label}: art is fully transparent")
    return int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())


def _fit_to_canvas(arr: np.ndarray, size: int, label: str) -> tuple[np.ndarray, FitPlan]:
    """Crop to the opaque bbox and center it on a `size`x`size` canvas.

    If the bbox exceeds `size` in either dimension, integer 2x-majority-vote
    downscale (`sprites._downscale_2x_majority` -- the repo's existing
    precedent for this, reused rather than reimplemented) and retry; fails
    loud if the art isn't evenly 2x-downscalable at that point. Returns the
    canvas and the `FitPlan` recipe so the identical placement can be
    replayed on shiny source art (`_apply_fit_plan`).
    """
    rounds = 0
    while True:
        x0, x1, y0, y1 = _opaque_bbox(arr, label)
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        if bw <= size and bh <= size:
            break
        h, w = arr.shape[:2]
        if h % 2 or w % 2:
            raise ValueError(
                f"{label}: opaque bbox {bw}x{bh} exceeds the {size}x{size} "
                f"canvas and the {w}x{h} source isn't evenly 2x-downscalable"
            )
        arr = _downscale_2x_majority(arr)
        rounds += 1

    left = (size - bw) // 2
    top = (size - bh) // 2
    canvas = np.zeros((size, size, 4), dtype=np.uint8)
    canvas[top : top + bh, left : left + bw] = arr[y0 : y1 + 1, x0 : x1 + 1]
    plan = FitPlan(downscale_rounds=rounds, bbox=(x0, x1, y0, y1), top=top, left=left)
    return canvas, plan


def _apply_fit_plan(arr: np.ndarray, plan: FitPlan, size: int, label: str) -> np.ndarray:
    """Replay a `FitPlan` derived from the normal art onto shiny source art
    of the same native shape, so shiny pixels land at IDENTICAL canvas
    coordinates to their normal counterparts -- required for palette-slot
    pixel-position sampling (`_build_shiny_palette`)."""
    for _ in range(plan.downscale_rounds):
        h, w = arr.shape[:2]
        if h % 2 or w % 2:
            raise ValueError(
                f"{label}: shiny source isn't evenly 2x-downscalable to "
                f"replay the normal art's fit plan"
            )
        arr = _downscale_2x_majority(arr)
    x0, x1, y0, y1 = plan.bbox
    h, w = arr.shape[:2]
    if x1 >= w or y1 >= h:
        raise ValueError(
            f"{label}: shiny source too small ({w}x{h}) to sample at the "
            f"normal art's bbox {plan.bbox}"
        )
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    canvas = np.zeros((size, size, 4), dtype=np.uint8)
    canvas[plan.top : plan.top + bh, plan.left : plan.left + bw] = arr[
        y0 : y1 + 1, x0 : x1 + 1
    ]
    return canvas


def _y_offset(plan: FitPlan, size: int) -> int:
    """Pixels between the drawn content's bottom edge and the canvas's
    bottom edge -- exactly what `frontPicYOffset`/`backPicYOffset` encode
    (`engine/include/pokemon.h`: "the number of pixels between the drawn
    pixel area and the bottom edge")."""
    _x0, _x1, y0, y1 = plan.bbox
    bh = y1 - y0 + 1
    return size - (plan.top + bh)


# --- Joint front+back quantization ------------------------------------------


def _to_tiles(canvas: np.ndarray, size: int) -> list[np.ndarray]:
    return [canvas[ty : ty + 8, tx : tx + 8] for ty in range(0, size, 8) for tx in range(0, size, 8)]


def _tiles_to_canvas(tiles: list[np.ndarray], size: int) -> np.ndarray:
    canvas = np.zeros((size, size, 4), dtype=np.uint8)
    i = 0
    for ty in range(0, size, 8):
        for tx in range(0, size, 8):
            canvas[ty : ty + 8, tx : tx + 8] = tiles[i]
            i += 1
    return canvas


def _joint_quantize(
    front: np.ndarray, back: np.ndarray, label: str
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Quantize front+back's UNION of opaque pixels to one shared
    <=BATTLER_MAX_COLORS palette -- the engine shares one `gMonPalette_X`
    between a species' front and back sprite, so they must be packed
    together, not independently. Reuses
    `quantize.build_quantized_tileset` (the pipeline's production
    palette-merging packer) over the 128 8x8 tiles spanning both 64x64
    canvases, with `max_palettes=1` forcing a single shared palette.

    Returns `(quantized_front, quantized_back, palette)`; `palette` is
    `(<=BATTLER_MAX_COLORS, 3)` uint8.
    """
    n_tiles_per_side = (BATTLER_SIZE // 8) ** 2
    tiles = _to_tiles(front, BATTLER_SIZE) + _to_tiles(back, BATTLER_SIZE)
    result = build_quantized_tileset(
        tiles, max_palettes=1, colors_per_palette=BATTLER_MAX_COLORS
    )
    if len(result.palettes) > 1:
        raise ValueError(
            f"{label}: joint quantizer produced {len(result.palettes)} "
            f"palettes -- contract requires exactly one shared palette"
        )
    palette = result.palettes[0] if result.palettes else np.empty((0, 3), np.uint8)
    if len(palette) > BATTLER_MAX_COLORS:
        raise ValueError(
            f"{label}: joint palette has {len(palette)} colours, exceeds "
            f"BATTLER_MAX_COLORS ({BATTLER_MAX_COLORS})"
        )
    q_front = _tiles_to_canvas(result.quantized[:n_tiles_per_side], BATTLER_SIZE)
    q_back = _tiles_to_canvas(result.quantized[n_tiles_per_side:], BATTLER_SIZE)
    return q_front, q_back, palette


def _rgba_to_indices(canvas: np.ndarray, palette: np.ndarray) -> np.ndarray:
    """`size`x`size` RGBA canvas (pixels already snapped to `palette`) ->
    uint8 indices: 0 = transparent, 1..len(palette) = palette row + 1."""
    opaque = canvas[..., 3] == 255
    idx = np.zeros(canvas.shape[:2], dtype=np.uint8)
    rgb = canvas[..., :3]
    for slot, color in enumerate(palette):
        idx[np.all(rgb == color, axis=-1) & opaque] = slot + 1
    return idx


def _indices_to_rgba(indices: np.ndarray, palette: np.ndarray) -> np.ndarray:
    """Inverse of `_rgba_to_indices`, for preview rendering."""
    h, w = indices.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    for slot in range(len(palette)):
        rgba[indices == slot + 1, :3] = palette[slot]
    rgba[..., 3] = np.where(indices > 0, 255, 0)
    return rgba


# --- Shiny-as-palette --------------------------------------------------------


def _modal_color(colors: np.ndarray) -> np.ndarray:
    """Most common RGB row; ties broken by `np.unique`'s lexicographic
    ordering -- deterministic, not an arbitrary set/hash order (matters for
    golden-test reproducibility)."""
    uniq, counts = np.unique(colors, axis=0, return_counts=True)
    return uniq[int(np.argmax(counts))]


def _build_shiny_palette(
    normal_front_idx: np.ndarray,
    normal_back_idx: np.ndarray,
    shiny_front_canvas: np.ndarray,
    shiny_back_canvas: np.ndarray,
    normal_palette: np.ndarray,
    label: str,
) -> np.ndarray:
    """For each normal-palette slot, sample the shiny art's colour at the
    SAME pixel positions that slot occupies in the normal art (modal colour
    across all such positions), producing an index-compatible shiny
    palette. Only valid because `shiny_front_canvas`/`shiny_back_canvas`
    were built by replaying the normal art's exact `FitPlan`
    (`_apply_fit_plan`) -- guaranteeing pixel positions correspond -- and
    because `_check_shiny_geometry` already confirmed the silhouettes are
    near-identical."""
    front_opaque = shiny_front_canvas[..., 3] == 255
    back_opaque = shiny_back_canvas[..., 3] == 255
    shiny_colors: list[np.ndarray] = []
    for slot in range(len(normal_palette)):
        front_sel = (normal_front_idx == slot + 1) & front_opaque
        back_sel = (normal_back_idx == slot + 1) & back_opaque
        colors = np.concatenate(
            [shiny_front_canvas[front_sel][:, :3], shiny_back_canvas[back_sel][:, :3]]
        )
        if colors.size == 0:
            raise ValueError(
                f"{label}: normal-palette slot {slot} has no corresponding "
                f"opaque shiny pixel -- shiny/normal art don't correspond "
                f"closely enough at this slot to sample a shiny colour"
            )
        shiny_colors.append(_modal_color(colors))
    return np.stack(shiny_colors).astype(np.uint8) if shiny_colors else np.empty((0, 3), np.uint8)


# --- File I/O ----------------------------------------------------------------


def _pal_text(colors: np.ndarray) -> str:
    """JASC-PAL text: 16 entries, index 0 the transparent placeholder --
    matches `tileset_converter.graphics.emit`'s convention (the engine's
    `INCGFX_U16 ... .gbapal` build rule reads it)."""
    lines = [_JASC_HEADER, "0 0 0\n"]
    for row in colors:
        lines.append(f"{int(row[0])} {int(row[1])} {int(row[2])}\n")
    lines += ["0 0 0\n"] * (_PALETTE_ENTRIES - 1 - len(colors))
    return "".join(lines)


def _read_pal(path: Path, n_colors: int) -> np.ndarray:
    """Parse a JASC-PAL file written by `_pal_text` back into an `(n_colors,
    3)` uint8 array (excluding the index-0 transparent placeholder and any
    trailing padding rows). `n_colors` must come from the conversion result
    (`opaque_color_count`), not inferred from padding -- a legitimate colour
    can itself be (0, 0, 0)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    rows = [tuple(int(v) for v in line.split()) for line in lines[3 : 3 + 1 + n_colors]]
    colors = rows[1:]
    return np.array(colors, dtype=np.uint8) if colors else np.empty((0, 3), np.uint8)


def _write_indexed_png(indices: np.ndarray, path: Path) -> None:
    """Write a `(H, W)` uint8 index array as a mode-P PNG with a 16-entry
    grey-ramp palette -- gbagfx reads only the raw 4-bit indices, not the
    embedded RGB, matching
    `tileset_converter.graphics.emit._tiles_to_indexed_image`'s convention."""
    img = Image.fromarray(indices, mode="P")
    grey = list(range(0, 256, 17))[:16]
    pal_bytes: list[int] = []
    for vv in grey:
        pal_bytes += [vv, vv, vv]
    img.putpalette(pal_bytes)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(path))


# --- Per-species / batch entry points ---------------------------------------


def convert_species_battler(
    uranium_src: Path, spec: SpeciesSpec, output_dir: Path
) -> BattlerConversionResult:
    """Convert one species' battler art and write it under
    `output_dir/<asset_dir_name>/` (see module docstring for the pipeline)."""
    label = spec.internal_name

    front_path = resolve_case(uranium_battler_front(uranium_src, spec, shiny=False))
    back_path = resolve_case(uranium_battler_back(uranium_src, spec, shiny=False))
    shiny_front_path = resolve_case(uranium_battler_front(uranium_src, spec, shiny=True))
    shiny_back_path = resolve_case(uranium_battler_back(uranium_src, spec, shiny=True))

    normal_front_raw = _extract_front_last_frame(front_path, f"{label} front")
    normal_back_raw = _extract_back(back_path, f"{label} back")
    shiny_front_raw = _extract_front_last_frame(shiny_front_path, f"{label} shiny front")
    shiny_back_raw = _extract_back(shiny_back_path, f"{label} shiny back")

    shiny_front_raw, front_divergence, _front_offset = _register_shiny(
        normal_front_raw, shiny_front_raw, f"{label} front"
    )
    shiny_back_raw, back_divergence, _back_offset = _register_shiny(
        normal_back_raw, shiny_back_raw, f"{label} back"
    )

    front_canvas, front_plan = _fit_to_canvas(normal_front_raw, BATTLER_SIZE, f"{label} front")
    back_canvas, back_plan = _fit_to_canvas(normal_back_raw, BATTLER_SIZE, f"{label} back")

    q_front, q_back, palette = _joint_quantize(front_canvas, back_canvas, label)
    front_idx = _rgba_to_indices(q_front, palette)
    back_idx = _rgba_to_indices(q_back, palette)

    shiny_front_canvas = _apply_fit_plan(
        shiny_front_raw, front_plan, BATTLER_SIZE, f"{label} shiny front"
    )
    shiny_back_canvas = _apply_fit_plan(
        shiny_back_raw, back_plan, BATTLER_SIZE, f"{label} shiny back"
    )
    shiny_palette = _build_shiny_palette(
        front_idx, back_idx, shiny_front_canvas, shiny_back_canvas, palette, label
    )

    species_dir = output_dir / asset_dir_name(spec)
    front_out = species_dir / FRONT_PNG
    back_out = species_dir / BACK_PNG
    normal_pal_out = species_dir / NORMAL_PAL
    shiny_pal_out = species_dir / SHINY_PAL

    _write_indexed_png(front_idx, front_out)
    _write_indexed_png(back_idx, back_out)
    species_dir.mkdir(parents=True, exist_ok=True)
    normal_pal_out.write_text(_pal_text(palette), encoding="utf-8")
    shiny_pal_out.write_text(_pal_text(shiny_palette), encoding="utf-8")

    front_offset = _y_offset(front_plan, BATTLER_SIZE)
    back_offset = _y_offset(back_plan, BATTLER_SIZE)

    logger.info(
        "%s: %d colours, frontYOffset=%d backYOffset=%d, shiny divergence "
        "front=%.3f%% back=%.3f%%",
        label,
        len(palette),
        front_offset,
        back_offset,
        front_divergence * 100,
        back_divergence * 100,
    )

    return BattlerConversionResult(
        internal_name=label,
        uranium_id=spec.uranium_id,
        front_path=front_out,
        back_path=back_out,
        normal_pal_path=normal_pal_out,
        shiny_pal_path=shiny_pal_out,
        front_y_offset=front_offset,
        back_y_offset=back_offset,
        opaque_color_count=len(palette),
        front_shiny_divergence=front_divergence,
        back_shiny_divergence=back_divergence,
    )


def convert_starter_battlers(
    uranium_src: Path,
    output_dir: Path,
    species: Sequence[SpeciesSpec] = STARTER_SPECIES,
) -> list[BattlerConversionResult]:
    """Convert every species in `species` and write the JSON sidecar.

    The sidecar (`<output_dir>/battlers.json`) carries the computed Y
    offsets (and other per-species metadata) for the staging emitter (W1) to
    consume; this module only ever writes it, never the emitter's own
    `species_manifest.json`.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    results = [convert_species_battler(uranium_src, spec, output_dir) for spec in species]

    sidecar_path = output_dir / SIDECAR_NAME
    sidecar_path.write_text(
        json.dumps([r.to_json_dict() for r in results], indent=2) + "\n",
        encoding="utf-8",
    )
    return results


# --- Contact sheet (human eye-gate) ------------------------------------------

CONTACT_SHEET_SCALE = 4
_LABEL_W = 110
_ROW_PAD = 6
_HEADER_H = 20


def build_contact_sheet(
    results: Sequence[BattlerConversionResult],
    output_path: Path,
    *,
    scale: int = CONTACT_SHEET_SCALE,
) -> Path:
    """Render all `results` (front+back, normal+shiny, one row per variant)
    into one labeled grid PNG for the user's eye-gate. Per CLAUDE.md and the
    repo's graphics-validation norm, this is for a HUMAN to eyeball -- there
    is deliberately no pixel-averaged pass/fail metric here."""
    cell_w = BATTLER_SIZE * scale
    cell_h = BATTLER_SIZE * scale
    row_h = cell_h + _ROW_PAD
    width = _LABEL_W + 2 * cell_w
    height = _HEADER_H + len(results) * 2 * row_h

    sheet = Image.new("RGB", (width, height), (40, 40, 40))
    draw = ImageDraw.Draw(sheet)
    draw.text((_LABEL_W + cell_w // 2 - 18, 4), "FRONT", fill=(255, 255, 255))
    draw.text((_LABEL_W + cell_w + cell_w // 2 - 16, 4), "BACK", fill=(255, 255, 255))

    y = _HEADER_H
    for result in results:
        front_idx = np.asarray(Image.open(result.front_path))
        back_idx = np.asarray(Image.open(result.back_path))
        normal_pal = _read_pal(result.normal_pal_path, result.opaque_color_count)
        shiny_pal = _read_pal(result.shiny_pal_path, result.opaque_color_count)

        for variant_name, palette in (("normal", normal_pal), ("shiny", shiny_pal)):
            bg = np.full((BATTLER_SIZE, BATTLER_SIZE, 3), 60, dtype=np.uint8)

            def _composite(indices: np.ndarray) -> np.ndarray:
                rgba = _indices_to_rgba(indices, palette)
                out = bg.copy()
                opaque = rgba[..., 3] == 255
                out[opaque] = rgba[..., :3][opaque]
                return out

            front_img = Image.fromarray(_composite(front_idx)).resize(
                (cell_w, cell_h), Image.NEAREST
            )
            back_img = Image.fromarray(_composite(back_idx)).resize(
                (cell_w, cell_h), Image.NEAREST
            )
            sheet.paste(front_img, (_LABEL_W, y))
            sheet.paste(back_img, (_LABEL_W + cell_w, y))
            draw.text(
                (4, y + cell_h // 2 - 6),
                f"{result.internal_name} ({variant_name})",
                fill=(255, 255, 255),
            )
            y += row_h

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(str(output_path))
    return output_path


__all__ = [
    "BattlerConversionResult",
    "FitPlan",
    "SIDECAR_NAME",
    "SHINY_GEOMETRY_MAX_DIVERGENCE",
    "SHINY_REGISTRATION_MAX_SHIFT",
    "CONTACT_SHEET_SCALE",
    "convert_species_battler",
    "convert_starter_battlers",
    "build_contact_sheet",
]
