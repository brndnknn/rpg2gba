"""W3 — Uranium party icon -> pokeemerald-expansion mon icon.

Source: `Graphics/Icons/iconNNN.png` (`common.uranium_icon`) is 128x64 = two
horizontally-adjacent 64x64 frames (the party-icon bounce animation, binary
alpha, verified <=13 opaque colours per starter on the real assets).

Target: the engine's mon icons (`graphics/pokemon/<name>/icon.png`, verified
against `engine/graphics/pokemon/bulbasaur/icon.png`) are 32x64 = two
VERTICALLY-stacked 32x32 frames, top frame first. That ordering is load-
bearing, not a guess: `pokemon_icon.c`'s `sMonIconAnims` step
`ANIMCMD_FRAME(0, ...)` then `ANIMCMD_FRAME(1, ...)` over a single-column
INCGFX strip, so tile/frame 0 is the top 32x32 and frame 1 is the bottom
32x32. We preserve animation order by putting the source LEFT frame (RMXP's
first bounce pose) on top and the RIGHT frame on the bottom.

Engine mon icons carry no palette of their own; every species indexes one of
six SHARED palettes at `graphics/pokemon/icon_palettes/pal0.pal`..`pal5.pal`
via a 3-bit `.iconPalIndex`. Read those six palettes (JASC-PAL, 16 RGB8
entries) and pick, per species, whichever minimizes total remap error; index
0 is IDENTICAL (98, 156, 131) across all six files -- it's the engine's fixed
icon-box background colour, not a spare slot -- so every transparent source
pixel maps there directly rather than through the colour-distance search.

Never touches the engine tree: palettes are read-only inputs, nothing here
writes under `engine/`.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from rpg2gba.species_converter.common import (
    ICON_HEIGHT,
    ICON_PALETTE_COUNT,
    ICON_PNG,
    ICON_WIDTH,
    STARTER_SPECIES,
    SpeciesSpec,
    asset_dir_name,
    resolve_case,
    uranium_icon,
)
from rpg2gba.tileset_converter.graphics.sprites import _downscale_2x_majority

logger = logging.getLogger(__name__)

_SOURCE_WIDTH = 128
_SOURCE_HEIGHT = 64
_FRAME_SIZE = 64  # one source frame is 64x64 (half of the 128x64 strip)

_ICON_PALETTES_RELDIR = Path("graphics/pokemon/icon_palettes")
_PALETTE_COLORS = 16

# Perceptually-weighted (ITU-R BT.601 luma) squared-distance weights. Human
# vision is far more sensitive to green than red, and to red more than blue;
# naive unweighted Euclidean RGB distance snaps colours to the wrong nearest
# (the same lesson `tileset_converter/graphics/quantize.py`'s history section
# documents for the tile quantizer -- an unweighted metric there sent tree
# edges to white and shadows to orange). Weighting by luma keeps the "same
# perceived brightness family" colours closer together than the distance
# alone would suggest, which is what a human eyeballing the icon actually
# judges as "close enough" or not.
_LUMA_WEIGHTS = np.array([0.299, 0.587, 0.114], dtype=np.float64)

_CONTACT_SHEET_ZOOM = 4  # matches the plan's "comfortable magnification"
_CONTACT_SHEET_BG = (40, 40, 40)
_CONTACT_SHEET_MARGIN = 8
_CONTACT_SHEET_LABEL_W = 200

MANIFEST_NAME = "icon_manifest.json"
CONTACT_SHEET_NAME = "icon_contact_sheet.png"


@dataclass(frozen=True)
class IconPalette:
    """One shared icon palette, loaded from `graphics/pokemon/icon_palettes/palN.pal`."""

    index: int
    colors: np.ndarray  # (16, 3) uint8, index-aligned with the engine .pal file


@dataclass
class SpeciesIconResult:
    """One species' converted icon plus enough of the pipeline's intermediate
    state to render the eye-gate contact sheet."""

    spec: SpeciesSpec
    icon_pal_index: int
    remap_error: float  # mean weighted-perceptual distance per opaque pixel
    indices: np.ndarray  # (64, 32) uint8, values 0-15 into the chosen palette
    source_frames: tuple[np.ndarray, np.ndarray]  # two (64, 64, 4) RGBA source frames
    downscaled_frames: tuple[np.ndarray, np.ndarray]  # two (32, 32, 4) RGBA, pre-remap


@dataclass
class IconConversionResult:
    """What one `convert_starter_icons` run produced."""

    species: list[SpeciesIconResult]
    manifest_path: Path
    contact_sheet_path: Path
    icon_paths: dict[str, Path]  # internal_name -> written icon.png path


# --- palette loading ---------------------------------------------------------


def _read_jasc_pal(path: Path) -> np.ndarray:
    """Parse a JASC-PAL file into an (N, 3) uint8 RGB8 array. Fails loud on a
    malformed header or a row that doesn't parse as three ints -- a bad shared
    palette is a fork/vendoring problem, never something to silently patch
    around."""
    text = path.read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3 or lines[0] != "JASC-PAL":
        raise ValueError(f"{path}: not a JASC-PAL file (missing 'JASC-PAL' header)")
    try:
        count = int(lines[2])
    except ValueError as exc:
        raise ValueError(f"{path}: malformed JASC-PAL colour count {lines[2]!r}") from exc
    if len(lines) < 3 + count:
        raise ValueError(
            f"{path}: header declares {count} colours but only "
            f"{len(lines) - 3} rows follow"
        )
    colors = []
    for row in lines[3 : 3 + count]:
        parts = row.split()
        if len(parts) != 3:
            raise ValueError(f"{path}: malformed colour row {row!r}")
        colors.append(tuple(int(p) for p in parts))
    return np.array(colors, dtype=np.uint8)


def load_icon_palettes(engine_root: Path) -> list[IconPalette]:
    """Load the six shared icon palettes from `engine_root`. Read-only --
    nothing here writes under `engine/`. Fails loud if a palette file is
    missing or doesn't have exactly 16 colours (the fixed size a 3-bit
    `.iconPalIndex` + 4bpp icon graphic both assume)."""
    pal_dir = Path(engine_root) / _ICON_PALETTES_RELDIR
    palettes: list[IconPalette] = []
    for i in range(ICON_PALETTE_COUNT):
        path = pal_dir / f"pal{i}.pal"
        if not path.exists():
            raise FileNotFoundError(f"missing shared icon palette: {path}")
        colors = _read_jasc_pal(path)
        if colors.shape != (_PALETTE_COLORS, 3):
            raise ValueError(
                f"{path}: expected {_PALETTE_COLORS} colours, got {colors.shape[0]}"
            )
        palettes.append(IconPalette(index=i, colors=colors))
    return palettes


# --- frame restack + downscale -----------------------------------------------


def stack_icon_frames(icon: np.ndarray) -> np.ndarray:
    """Pure transform: a 128x64 two-horizontal-frame RGBA array ->
    32x64 two-VERTICALLY-stacked-frame RGBA array (source left frame on top,
    source right frame on bottom -- see module docstring for why that order
    matters). Exposed standalone (no file I/O) so the frame-restack round-trip
    is directly unit-testable against a synthetic array.

    Fails loud on any shape other than exactly (64, 128, 4)."""
    if icon.shape != (_SOURCE_HEIGHT, _SOURCE_WIDTH, 4):
        raise ValueError(
            f"expected a {_SOURCE_WIDTH}x{_SOURCE_HEIGHT} two-frame RGBA icon, "
            f"got array shape {icon.shape}"
        )
    left = icon[:, :_FRAME_SIZE]
    right = icon[:, _FRAME_SIZE:]
    top = _downscale_2x_majority(left)
    bottom = _downscale_2x_majority(right)
    return np.concatenate([top, bottom], axis=0)


def _load_icon_array(path: Path) -> np.ndarray:
    img = Image.open(path).convert("RGBA")
    if img.size != (_SOURCE_WIDTH, _SOURCE_HEIGHT):
        raise ValueError(
            f"{path}: expected a {_SOURCE_WIDTH}x{_SOURCE_HEIGHT} icon, got "
            f"{img.size[0]}x{img.size[1]}"
        )
    return np.asarray(img)


# --- palette selection + remap -----------------------------------------------


def _weighted_sq_dist(colors: np.ndarray, palette: np.ndarray) -> np.ndarray:
    """(N,3) uint8 colours x (16,3) uint8 palette -> (N, 16) luma-weighted
    squared distance."""
    diff = colors[:, None, :].astype(np.float64) - palette[None, :, :].astype(np.float64)
    return (diff * diff * _LUMA_WEIGHTS).sum(axis=-1)


def choose_palette(
    stacked: np.ndarray, palettes: list[IconPalette]
) -> tuple[int, float]:
    """Pick the shared palette (0-5) minimizing total weighted remap error
    over `stacked`'s opaque pixels, weighted by how many pixels share each
    colour (CLAUDE.md brief: "a large flat region matters more than a stray
    outline pixel"). Returns `(chosen_index, mean_error)` where `mean_error`
    is the weighted-average perceptual distance per opaque pixel under the
    chosen palette (0.0 == every opaque colour is an exact palette hit).

    Transparent pixels are excluded from the search entirely: they always map
    to index 0 (the engine's fixed icon-box background colour, identical
    across all six palettes -- see `remap_to_palette`), so they contribute no
    error under ANY palette and would only dilute the comparison.

    Ties broken by lowest palette index (stable iteration order 0..5)."""
    opaque = stacked[..., 3] == 255
    if not opaque.any():
        raise ValueError("icon has no opaque pixels in either frame")
    distinct, counts = np.unique(stacked[opaque][:, :3], axis=0, return_counts=True)
    counts = counts.astype(np.float64)

    best_index = -1
    best_error = np.inf
    for pal in palettes:
        sq = _weighted_sq_dist(distinct, pal.colors)
        min_dist = np.sqrt(sq.min(axis=1))
        mean_error = float((min_dist * counts).sum() / counts.sum())
        if mean_error < best_error:
            best_error = mean_error
            best_index = pal.index
    return best_index, best_error


def remap_to_palette(stacked: np.ndarray, palette: IconPalette) -> np.ndarray:
    """Remap `stacked`'s pixels to indices (0-15) into `palette`. Opaque
    pixels snap to their nearest palette entry (same weighted metric as
    `choose_palette`); transparent pixels go to index 0, the engine's fixed
    icon-box background colour (identical across all six palettes -- this is
    a defined mapping, not a lossy colour match, so it contributes nothing to
    the reported remap error)."""
    indices = np.zeros(stacked.shape[:2], dtype=np.uint8)
    opaque = stacked[..., 3] == 255
    if opaque.any():
        sq = _weighted_sq_dist(stacked[opaque][:, :3], palette.colors)
        indices[opaque] = sq.argmin(axis=1).astype(np.uint8)
    return indices


# --- per-species conversion ---------------------------------------------------


def convert_species_icon(
    uranium_src: Path, spec: SpeciesSpec, palettes: list[IconPalette]
) -> SpeciesIconResult:
    """Convert one species' Uranium party icon into a `SpeciesIconResult`."""
    path = resolve_case(uranium_icon(uranium_src, spec))
    icon = _load_icon_array(path)
    left = icon[:, :_FRAME_SIZE]
    right = icon[:, _FRAME_SIZE:]
    top = _downscale_2x_majority(left)
    bottom = _downscale_2x_majority(right)
    stacked = np.concatenate([top, bottom], axis=0)

    pal_index, error = choose_palette(stacked, palettes)
    chosen = palettes[pal_index]
    indices = remap_to_palette(stacked, chosen)

    if error > 0:
        logger.info(
            "%s: chose icon palette %d, mean remap error %.3f",
            spec.internal_name, pal_index, error,
        )
    return SpeciesIconResult(
        spec=spec,
        icon_pal_index=pal_index,
        remap_error=error,
        indices=indices,
        source_frames=(left, right),
        downscaled_frames=(top, bottom),
    )


def _write_icon_png(path: Path, result: SpeciesIconResult, palette: IconPalette) -> None:
    if result.indices.shape != (ICON_HEIGHT, ICON_WIDTH):
        raise ValueError(
            f"{result.spec.internal_name}: indices shape {result.indices.shape}, "
            f"expected ({ICON_HEIGHT}, {ICON_WIDTH})"
        )
    img = Image.fromarray(result.indices, mode="P")
    pal_bytes: list[int] = []
    for color in palette.colors:
        pal_bytes += [int(color[0]), int(color[1]), int(color[2])]
    img.putpalette(pal_bytes)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(path))


# --- eye-gate contact sheet ---------------------------------------------------


def _zoom_nn(rgba: np.ndarray, factor: int) -> np.ndarray:
    return np.repeat(np.repeat(rgba, factor, axis=0), factor, axis=1)


def _composite_over(rgba: np.ndarray, bg: tuple[int, int, int]) -> np.ndarray:
    """RGBA -> opaque RGB, alpha-composited over a flat background colour (so
    transparent source regions read clearly against the contact sheet's
    neutral background rather than as PNG-viewer-dependent checkerboard)."""
    out = np.empty(rgba.shape[:2] + (3,), dtype=np.uint8)
    alpha = rgba[..., 3:4].astype(np.float64) / 255.0
    fg = rgba[..., :3].astype(np.float64)
    bg_arr = np.array(bg, dtype=np.float64)
    out[:] = (fg * alpha + bg_arr * (1 - alpha)).round().astype(np.uint8)
    return out


def write_contact_sheet(results: list[SpeciesIconResult], palettes: list[IconPalette], path: Path) -> None:
    """Render the eye-gate contact sheet: one row per species, showing the two
    64x64 source frames next to the two converted 32x32 result frames (both
    at the same on-screen size via zoom) so a human can judge what the
    downscale + palette remap cost, per CLAUDE.md's "validate by eye" rule.
    """
    zoom = _CONTACT_SHEET_ZOOM
    src_cell = _FRAME_SIZE * (zoom // 2)  # 64x64 source at 2x = same on-screen size as...
    conv_cell = ICON_WIDTH * zoom  # ...32x32 result at 4x
    assert src_cell == conv_cell, "source/result cells must render at the same on-screen size"
    cell = src_cell
    gap = _CONTACT_SHEET_MARGIN
    row_h = cell + gap
    n_cols = 4  # src frame0, src frame1, converted frame0, converted frame1
    width = _CONTACT_SHEET_LABEL_W + n_cols * cell + (n_cols + 1) * gap
    height = len(results) * row_h + gap

    canvas = Image.new("RGB", (width, height), _CONTACT_SHEET_BG)
    draw = ImageDraw.Draw(canvas)

    for row, result in enumerate(results):
        y = gap + row * row_h
        pal = palettes[result.icon_pal_index]
        label = (
            f"{result.spec.internal_name}\n"
            f"pal {result.icon_pal_index}  err {result.remap_error:.2f}"
        )
        draw.multiline_text((gap, y + cell // 2 - 12), label, fill=(230, 230, 230))

        src0, src1 = result.source_frames
        x = _CONTACT_SHEET_LABEL_W
        for src_frame in (src0, src1):
            tile = _composite_over(_zoom_nn(src_frame, zoom // 2), _CONTACT_SHEET_BG)
            canvas.paste(Image.fromarray(tile), (x, y))
            x += cell + gap

        top = result.indices[:ICON_WIDTH]
        bottom = result.indices[ICON_WIDTH:]
        for frame_idx in (top, bottom):
            rgb = pal.colors[frame_idx]  # (32, 32, 3) via fancy indexing
            tile = _zoom_nn(rgb, zoom)
            canvas.paste(Image.fromarray(tile), (x, y))
            x += cell + gap

    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(str(path))


# --- manifest -----------------------------------------------------------------


def _write_manifest(results: list[SpeciesIconResult], icon_paths: dict[str, Path], path: Path) -> None:
    payload = {
        "schema_version": 1,
        "species": {
            r.spec.internal_name: {
                "uranium_id": r.spec.uranium_id,
                "icon_pal_index": r.icon_pal_index,
                "remap_error": r.remap_error,
                "icon_png": str(icon_paths[r.spec.internal_name]),
            }
            for r in results
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


# --- main entry point ----------------------------------------------------------


def convert_starter_icons(
    uranium_src: Path, engine_root: Path, output_dir: Path
) -> IconConversionResult:
    """Convert all six `STARTER_SPECIES` icons, writing each species' indexed
    `icon.png` under `output_dir/<asset_dir_name>/icon.png`, a JSON manifest
    of chosen `iconPalIndex`/remap-error per species, and an eye-gate contact
    sheet -- all under `output_dir`. Never touches `engine/` (palettes are
    read-only inputs). Deterministic: identical inputs always produce
    byte-identical outputs (CLAUDE.md §4.2)."""
    output_dir = Path(output_dir)
    palettes = load_icon_palettes(engine_root)

    results: list[SpeciesIconResult] = []
    icon_paths: dict[str, Path] = {}
    for spec in STARTER_SPECIES:
        result = convert_species_icon(uranium_src, spec, palettes)
        results.append(result)
        icon_path = output_dir / asset_dir_name(spec) / ICON_PNG
        _write_icon_png(icon_path, result, palettes[result.icon_pal_index])
        icon_paths[spec.internal_name] = icon_path

    manifest_path = output_dir / MANIFEST_NAME
    _write_manifest(results, icon_paths, manifest_path)

    contact_sheet_path = output_dir / CONTACT_SHEET_NAME
    write_contact_sheet(results, palettes, contact_sheet_path)

    return IconConversionResult(
        species=results,
        manifest_path=manifest_path,
        contact_sheet_path=contact_sheet_path,
        icon_paths=icon_paths,
    )
