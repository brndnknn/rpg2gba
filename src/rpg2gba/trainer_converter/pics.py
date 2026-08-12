"""Uranium trainer art -> pokeemerald-expansion GBA trainer pic converter.

Converts Uranium's `Graphics/Characters/trainer<NNN>.png` NPC front pics and
`trback<NNN>.png` player back-pic strips into the 64x64 (front) / 64x256
(back, 4 stacked 64x64 frames) 4bpp indexed art the vendored engine expects.
Architecturally this mirrors `species_converter/battlers.py` (crop-to-bbox,
uniform scale, joint quantization, JASC-PAL output) but the source geometry
differs enough that the pipeline itself is new, not reused:

  - NPC front pics are NOT filmstrips and are not uniformly sized (98 files
    160x160, 28 files 128x128, three one-offs up to 240x270) -- there is no
    native-2x relationship to a 64x64 canvas, so this module scales with
    `Image.LANCZOS` rather than the battler converter's integer
    majority-vote downscale.
  - Player back pics ARE filmstrips, but horizontal 4-frame strips that must
    land on a VERTICAL 64x256 engine sheet -- a transpose the battler
    converter has no analog for. The four frames are a ball-throw animation
    (idle / raise ball / windup / throw), so cropping/scaling must use one
    SHARED window across all four frames (never each frame's own bbox) or
    the inter-frame motion is destroyed.

Pipeline, front (`convert_front_pic`):
  1. load + `.convert("RGBA")`, binarize alpha (GBA has no partial alpha)
  2. crop to the tight opaque bounding box
  3. scale uniformly (LANCZOS, aspect preserved) so the bbox fits in 64x64
  4. re-binarize alpha (LANCZOS produces fractional alpha)
  5. paste onto a transparent 64x64 canvas, horizontally centered, bottom-anchored
  6. quantize to <=`TRAINER_MAX_COLORS` opaque colours (`build_quantized_tileset`,
     `max_palettes=1` -- one palette for the whole sprite)

Pipeline, back (`convert_back_pic`):
  1. load, binarize alpha, split into `BACK_PIC_FRAMES` frames by
     `width // BACK_PIC_FRAMES` (floor division; any width remainder is
     dropped -- e.g. 662 -> 4 frames of 165, 2px unused)
  2. compute the UNION opaque bbox across all 4 frames in frame-local
     coordinates
  3. apply that ONE shared crop window to every frame (never per-frame crop
     -- that would re-center each frame independently and destroy the
     throw-animation motion)
  4. compute ONE uniform scale factor from the union bbox and apply it to
     all 4 frames identically
  5. bottom-anchor + horizontally center using the shared (scaled) window
     size -- since every frame shares that size, this is a single constant
     offset applied to all four, preserving their relative positions
  6. stack the four 64x64 canvases VERTICALLY into 64x256
  7. quantize the whole sheet jointly to <=`TRAINER_MAX_COLORS` (one shared
     palette for all four frames)
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from rpg2gba.tileset_converter.graphics.quantize import build_quantized_tileset
from rpg2gba.tileset_converter.graphics.sprites import _binarize_alpha
from rpg2gba.trainer_converter.common import (
    BACK_PIC_FRAMES,
    PLAYER_BACK_PIC_NAMES,
    SLICE_TRAINER_PICS,
    TRAINER_MAX_COLORS,
    TRAINER_PIC_SIZE,
    TrainerPicSpec,
    resolve_case,
    uranium_trainer_back,
    uranium_trainer_front,
)

logger = logging.getLogger(__name__)

FRONT_PNG = "front.png"
FRONT_PAL = "front.pal"
BACK_PNG = "back.png"
BACK_PAL = "back.pal"
SIDECAR_NAME = "trainer_pics.json"

_JASC_HEADER = "JASC-PAL\n0100\n16\n"
_PALETTE_ENTRIES = 16  # index 0 (transparent placeholder) + up to 15 colours


# --- Shared helpers ----------------------------------------------------------


def _load_rgba(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGBA"))


def _opaque_bbox(arr: np.ndarray, label: str) -> tuple[int, int, int, int]:
    ys, xs = np.where(arr[..., 3] > 0)
    if xs.size == 0:
        raise ValueError(f"{label}: source art is fully transparent")
    return int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())


def _resize_lanczos_rebinarize(arr: np.ndarray, new_w: int, new_h: int) -> np.ndarray:
    """Resize an RGBA array with `Image.LANCZOS` and re-binarize alpha
    (LANCZOS produces fractional alpha at edges; GBA has no partial alpha)."""
    img = Image.fromarray(arr, mode="RGBA").resize((new_w, new_h), Image.LANCZOS)
    return _binarize_alpha(np.asarray(img))


def _to_tiles(canvas: np.ndarray, width: int, height: int) -> list[np.ndarray]:
    return [
        canvas[ty : ty + 8, tx : tx + 8]
        for ty in range(0, height, 8)
        for tx in range(0, width, 8)
    ]


def _tiles_to_canvas(tiles: list[np.ndarray], width: int, height: int) -> np.ndarray:
    canvas = np.zeros((height, width, 4), dtype=np.uint8)
    i = 0
    for ty in range(0, height, 8):
        for tx in range(0, width, 8):
            canvas[ty : ty + 8, tx : tx + 8] = tiles[i]
            i += 1
    return canvas


def _quantize_solo(canvas: np.ndarray, width: int, height: int, label: str) -> tuple[np.ndarray, np.ndarray]:
    """Quantize one canvas (front's 64x64, or back's whole 64x256 sheet) to
    a single <=`TRAINER_MAX_COLORS` palette. Returns `(quantized_canvas,
    palette)`."""
    tiles = _to_tiles(canvas, width, height)
    result = build_quantized_tileset(tiles, max_palettes=1, colors_per_palette=TRAINER_MAX_COLORS)
    if len(result.palettes) > 1:
        raise ValueError(
            f"{label}: quantizer produced {len(result.palettes)} palettes -- "
            f"contract requires exactly one shared palette"
        )
    palette = result.palettes[0] if result.palettes else np.empty((0, 3), np.uint8)
    if len(palette) > TRAINER_MAX_COLORS:
        raise ValueError(
            f"{label}: quantized palette has {len(palette)} colours, exceeds "
            f"TRAINER_MAX_COLORS ({TRAINER_MAX_COLORS})"
        )
    quantized = _tiles_to_canvas(result.quantized, width, height)
    return quantized, palette


def _rgba_to_indices(canvas: np.ndarray, palette: np.ndarray) -> np.ndarray:
    """RGBA canvas (pixels already snapped to `palette`) -> uint8 indices:
    0 = transparent, 1..len(palette) = palette row + 1."""
    opaque = canvas[..., 3] == 255
    idx = np.zeros(canvas.shape[:2], dtype=np.uint8)
    rgb = canvas[..., :3]
    for slot, color in enumerate(palette):
        idx[np.all(rgb == color, axis=-1) & opaque] = slot + 1
    return idx


def _indices_to_rgba(indices: np.ndarray, palette: np.ndarray) -> np.ndarray:
    """Inverse of `_rgba_to_indices`, for contact-sheet rendering."""
    h, w = indices.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    for slot in range(len(palette)):
        rgba[indices == slot + 1, :3] = palette[slot]
    rgba[..., 3] = np.where(indices > 0, 255, 0)
    return rgba


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
    trailing padding rows)."""
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


# --- Results ------------------------------------------------------------------


@dataclass(frozen=True)
class FrontPicResult:
    trainer_id: int
    internal_name: str
    front_path: Path
    pal_path: Path
    source_bbox: tuple[int, int]  # (w, h) of the cropped opaque bbox, source pixels
    scaled_size: tuple[int, int]  # (w, h) after uniform scale, pre-canvas-paste
    scale_factor: float
    opaque_color_count: int

    def to_json_dict(self) -> dict[str, object]:
        d = asdict(self)
        d["front_path"] = str(d["front_path"])
        d["pal_path"] = str(d["pal_path"])
        return d


@dataclass(frozen=True)
class BackPicResult:
    trainer_id: int
    internal_name: str
    back_path: Path
    pal_path: Path
    frame_count: int
    per_frame_bbox: tuple[tuple[int, int, int, int] | None, ...]  # frame-local, pre-crop
    union_bbox: tuple[int, int, int, int]  # frame-local, pre-crop
    scaled_size: tuple[int, int]  # (w, h) of each scaled frame, pre-canvas-paste
    scale_factor: float
    opaque_color_count: int

    def to_json_dict(self) -> dict[str, object]:
        d = asdict(self)
        d["back_path"] = str(d["back_path"])
        d["pal_path"] = str(d["pal_path"])
        return d


# --- Front pic -----------------------------------------------------------------


def convert_front_pic(uranium_src: Path, spec: TrainerPicSpec, out_dir: Path) -> FrontPicResult:
    label = f"trainer{spec.trainer_id:03d} front ({spec.internal_name})"
    path = resolve_case(uranium_trainer_front(uranium_src, spec.trainer_id))

    arr = _binarize_alpha(_load_rgba(path))
    x0, x1, y0, y1 = _opaque_bbox(arr, label)
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    cropped = arr[y0 : y1 + 1, x0 : x1 + 1]

    scale = min(TRAINER_PIC_SIZE / bw, TRAINER_PIC_SIZE / bh)
    new_w = max(1, min(TRAINER_PIC_SIZE, round(bw * scale)))
    new_h = max(1, min(TRAINER_PIC_SIZE, round(bh * scale)))
    scaled = _resize_lanczos_rebinarize(cropped, new_w, new_h)

    left = (TRAINER_PIC_SIZE - new_w) // 2
    top = TRAINER_PIC_SIZE - new_h  # bottom-anchored
    canvas = np.zeros((TRAINER_PIC_SIZE, TRAINER_PIC_SIZE, 4), dtype=np.uint8)
    canvas[top : top + new_h, left : left + new_w] = scaled

    quantized, palette = _quantize_solo(canvas, TRAINER_PIC_SIZE, TRAINER_PIC_SIZE, label)
    indices = _rgba_to_indices(quantized, palette)

    out_subdir = out_dir
    front_out = out_subdir / FRONT_PNG
    pal_out = out_subdir / FRONT_PAL
    _write_indexed_png(indices, front_out)
    out_subdir.mkdir(parents=True, exist_ok=True)
    pal_out.write_text(_pal_text(palette), encoding="utf-8")

    logger.info(
        "%s: source bbox %dx%d -> scaled %dx%d (factor %.4f), %d colours",
        label, bw, bh, new_w, new_h, scale, len(palette),
    )

    return FrontPicResult(
        trainer_id=spec.trainer_id,
        internal_name=spec.internal_name,
        front_path=front_out,
        pal_path=pal_out,
        source_bbox=(bw, bh),
        scaled_size=(new_w, new_h),
        scale_factor=scale,
        opaque_color_count=len(palette),
    )


# --- Back pic --------------------------------------------------------------------


def convert_back_pic(uranium_src: Path, spec: TrainerPicSpec, out_dir: Path) -> BackPicResult:
    label = f"trainer{spec.trainer_id:03d} back ({spec.internal_name})"
    path = resolve_case(uranium_trainer_back(uranium_src, spec.trainer_id))

    arr = _binarize_alpha(_load_rgba(path))
    h, w = arr.shape[:2]
    if w < BACK_PIC_FRAMES:
        raise ValueError(
            f"{label}: strip is {w}px wide, narrower than {BACK_PIC_FRAMES} frames"
        )
    fw = w // BACK_PIC_FRAMES  # floor division; any remainder columns are dropped
    frames = [arr[:, i * fw : (i + 1) * fw] for i in range(BACK_PIC_FRAMES)]

    per_frame_bbox: list[tuple[int, int, int, int] | None] = []
    for frame in frames:
        ys, xs = np.where(frame[..., 3] > 0)
        per_frame_bbox.append(
            (int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())) if xs.size else None
        )
    valid = [b for b in per_frame_bbox if b is not None]
    if not valid:
        raise ValueError(f"{label}: all {BACK_PIC_FRAMES} frames are fully transparent")

    x0 = min(b[0] for b in valid)
    x1 = max(b[1] for b in valid)
    y0 = min(b[2] for b in valid)
    y1 = max(b[3] for b in valid)
    bw, bh = x1 - x0 + 1, y1 - y0 + 1

    # Apply the SAME crop window to every frame -- never crop independently,
    # that would destroy the inter-frame throw-animation motion.
    cropped_frames = [frame[y0 : y1 + 1, x0 : x1 + 1] for frame in frames]

    scale = min(TRAINER_PIC_SIZE / bw, TRAINER_PIC_SIZE / bh)
    new_w = max(1, min(TRAINER_PIC_SIZE, round(bw * scale)))
    new_h = max(1, min(TRAINER_PIC_SIZE, round(bh * scale)))
    scaled_frames = [_resize_lanczos_rebinarize(f, new_w, new_h) for f in cropped_frames]

    # One constant offset (shared window -> shared scaled size) applied to
    # every frame -- preserves their relative positions.
    left = (TRAINER_PIC_SIZE - new_w) // 2
    top = TRAINER_PIC_SIZE - new_h
    canvases = []
    for sf in scaled_frames:
        canvas = np.zeros((TRAINER_PIC_SIZE, TRAINER_PIC_SIZE, 4), dtype=np.uint8)
        canvas[top : top + new_h, left : left + new_w] = sf
        canvases.append(canvas)

    sheet_h = TRAINER_PIC_SIZE * BACK_PIC_FRAMES
    sheet = np.concatenate(canvases, axis=0)  # vertical stack -> 64x256

    quantized, palette = _quantize_solo(sheet, TRAINER_PIC_SIZE, sheet_h, label)
    indices = _rgba_to_indices(quantized, palette)

    back_out = out_dir / BACK_PNG
    pal_out = out_dir / BACK_PAL
    _write_indexed_png(indices, back_out)
    out_dir.mkdir(parents=True, exist_ok=True)
    pal_out.write_text(_pal_text(palette), encoding="utf-8")

    logger.info(
        "%s: union bbox %dx%d -> scaled %dx%d (factor %.4f), %d colours",
        label, bw, bh, new_w, new_h, scale, len(palette),
    )

    return BackPicResult(
        trainer_id=spec.trainer_id,
        internal_name=spec.internal_name,
        back_path=back_out,
        pal_path=pal_out,
        frame_count=BACK_PIC_FRAMES,
        per_frame_bbox=tuple(per_frame_bbox),
        union_bbox=(x0, x1, y0, y1),
        scaled_size=(new_w, new_h),
        scale_factor=scale,
        opaque_color_count=len(palette),
    )


# --- Contact sheet (human eye-gate) ---------------------------------------------

CONTACT_SHEET_SCALE = 4
_GUTTER = 8
_BG = (110, 110, 110)


def build_contact_sheet(
    front: FrontPicResult, back: BackPicResult, output_path: Path, *, scale: int = CONTACT_SHEET_SCALE
) -> Path:
    """Render the front pic and the 4 back frames, at `scale`x nearest-
    neighbour, in a single row on a mid-grey background, for human eye
    review (CLAUDE.md graphics-validation norm -- no pixel-averaged metric)."""
    cell = TRAINER_PIC_SIZE * scale
    n_cells = 1 + back.frame_count
    width = n_cells * cell + (n_cells + 1) * _GUTTER
    height = cell + 2 * _GUTTER

    sheet = Image.new("RGB", (width, height), _BG)

    front_idx = np.asarray(Image.open(front.front_path))
    front_pal = _read_pal(front.pal_path, front.opaque_color_count)
    front_rgba = _indices_to_rgba(front_idx, front_pal)
    front_bg = np.full((TRAINER_PIC_SIZE, TRAINER_PIC_SIZE, 3), _BG, dtype=np.uint8)
    opaque = front_rgba[..., 3] == 255
    front_bg[opaque] = front_rgba[..., :3][opaque]
    front_img = Image.fromarray(front_bg).resize((cell, cell), Image.NEAREST)
    sheet.paste(front_img, (_GUTTER, _GUTTER))

    back_idx_full = np.asarray(Image.open(back.back_path))
    back_pal = _read_pal(back.pal_path, back.opaque_color_count)
    x = _GUTTER + cell + _GUTTER
    for i in range(back.frame_count):
        frame_idx = back_idx_full[i * TRAINER_PIC_SIZE : (i + 1) * TRAINER_PIC_SIZE, :]
        frame_rgba = _indices_to_rgba(frame_idx, back_pal)
        frame_bg = np.full((TRAINER_PIC_SIZE, TRAINER_PIC_SIZE, 3), _BG, dtype=np.uint8)
        opaque = frame_rgba[..., 3] == 255
        frame_bg[opaque] = frame_rgba[..., :3][opaque]
        frame_img = Image.fromarray(frame_bg).resize((cell, cell), Image.NEAREST)
        sheet.paste(frame_img, (x, _GUTTER))
        x += cell + _GUTTER

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(str(output_path))
    return output_path


# --- Slice entry point -----------------------------------------------------------


def convert_slice_trainer_pics(
    uranium_src: Path, out_dir: Path
) -> tuple[list[FrontPicResult], list[BackPicResult]]:
    """Convert every `SLICE_TRAINER_PICS` entry's front pic, plus a back pic
    for entries named in `common.PLAYER_BACK_PIC_NAMES` (currently
    PLAYER_MALE), and write the `trainer_pics.json` sidecar.

    Originally slice-1 (RIVAL front + PLAYER_MALE back) only; generalized for
    W6 when the seven Route-1 trainer-class fronts were appended to
    `SLICE_TRAINER_PICS` -- vanilla pairs every player identity with both a
    front AND back pic (`TRAINER_PIC_FRONT_BRENDAN`/`_BACK_BRENDAN` etc, see
    `include/constants/trainers.h`), so PLAYER_MALE now gets a front
    conversion too, not just its historical back-only treatment.

    Key order in the JSON is stable (`sort_keys=True`) so re-runs are
    byte-identical. Each spec gets its own `out_dir/<internal_name lower>/`
    subdirectory -- with 9 pinned specs sharing one flat `out_dir`,
    `convert_front_pic`/`convert_back_pic` would otherwise all collide on the
    same `front.png`/`back.png` filenames.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    front_results: list[FrontPicResult] = []
    back_results: list[BackPicResult] = []
    sidecar_fronts: dict[str, object] = {}
    sidecar_backs: dict[str, object] = {}

    for spec in SLICE_TRAINER_PICS:
        spec_dir = out_dir / spec.internal_name.lower()
        front_result = convert_front_pic(uranium_src, spec, spec_dir)
        front_results.append(front_result)
        sidecar_fronts[spec.internal_name] = {
            "constant": spec.pic_constant,
            "trainer_id": front_result.trainer_id,
            "internal_name": front_result.internal_name,
            "output": front_result.to_json_dict(),
        }
        if spec.internal_name in PLAYER_BACK_PIC_NAMES:
            back_result = convert_back_pic(uranium_src, spec, spec_dir)
            back_results.append(back_result)
            sidecar_backs[spec.internal_name] = {
                "constant": spec.back_pic_constant,
                "trainer_id": back_result.trainer_id,
                "internal_name": back_result.internal_name,
                "output": back_result.to_json_dict(),
            }

    sidecar = {"fronts": sidecar_fronts, "backs": sidecar_backs}
    sidecar_path = out_dir / SIDECAR_NAME
    sidecar_path.write_text(
        json.dumps(sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    return front_results, back_results


__all__ = [
    "FRONT_PNG",
    "FRONT_PAL",
    "BACK_PNG",
    "BACK_PAL",
    "SIDECAR_NAME",
    "CONTACT_SHEET_SCALE",
    "FrontPicResult",
    "BackPicResult",
    "convert_front_pic",
    "convert_back_pic",
    "build_contact_sheet",
    "convert_slice_trainer_pics",
]
