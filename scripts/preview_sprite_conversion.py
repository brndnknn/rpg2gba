"""Preview RMXP character sheet -> GBA object-event frame conversion.

Converts a fixed (overridable) list of Uranium `Graphics/Characters/*.png`
sheets with `rpg2gba.tileset_converter.graphics.sprites.convert_character_sheet`
and writes a contact sheet: one row per sheet, its 9 GBA-order frames (4x
nearest-neighbour, on a checkerboard so transparency is visible), labelled
with the sheet name, detected cycle, asymmetry metric, and content size.
Also prints a plain-text summary table to stdout.

Usage: python scripts/preview_sprite_conversion.py [--sheets NAME,NAME,...]

Reads sheets from `$RPG2GBA_URANIUM_SRC/Graphics/Characters/` (falls back to
`.env-paths` if the env var isn't already set — see `rpg2gba.pipeline`).
Writes to `$RPG2GBA_OUTPUT/sprite_conversion_preview.png` (default `./output`).
"""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from rpg2gba.tileset_converter.graphics.sprites import ConvertedSprite, convert_character_sheet

logger = logging.getLogger("preview_sprite_conversion")

DEFAULT_SHEETS: list[str] = [
    "HGSS_000",
    "HGSS_001",
    "HGSS_005",
    "HGSS_008",
    "HGSS_009",
    "HGSS_017",
    "HGSS_018",
    "HGSS_019",
    "HGSS_034",
    "HGSS_051",
    "HGSS_129",
    "Rivaltheo",
    "fk107-rocksmash",
    "PU-Chyinmunk",
    "PU-Orchynx",
    "PU-Raptorch",
    "PU-Eletux",
    "PU-Barewl",
]

FRAME_PX = 32
UPSCALE = 4
CELL_PX = FRAME_PX * UPSCALE  # 128
GAP = 6
PAD = 16
HEADER_H = 22
ROW_GAP = 10
CHECKER_SQUARE = 8


def _characters_dir() -> Path:
    """`<RPG2GBA_URANIUM_SRC>/Graphics/Characters`, loading .env-paths if unset."""
    if "RPG2GBA_URANIUM_SRC" not in os.environ:
        from rpg2gba.pipeline import _load_dotenv  # lazy: only needed for the env default

        _load_dotenv()
    src = os.environ.get("RPG2GBA_URANIUM_SRC")
    if not src:
        raise RuntimeError(
            "RPG2GBA_URANIUM_SRC is not set (and .env-paths didn't provide it); "
            "point it at the unpacked Uranium tree"
        )
    return Path(src) / "Graphics" / "Characters"


def _output_dir() -> Path:
    return Path(os.environ.get("RPG2GBA_OUTPUT", "output"))


def _resolve_sheet(characters_dir: Path, name: str) -> Path:
    """`<characters_dir>/<name>.png`, with a case-insensitive fallback. Fail loud."""
    exact = characters_dir / f"{name}.png"
    if exact.is_file():
        return exact
    target = name.lower()
    if characters_dir.is_dir():
        for p in characters_dir.iterdir():
            if p.is_file() and p.suffix.lower() == ".png" and p.stem.lower() == target:
                return p
    raise FileNotFoundError(f"sheet {name!r} not found under {characters_dir}")


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _checkerboard(size: int, square: int = CHECKER_SQUARE) -> Image.Image:
    xs, ys = np.meshgrid(np.arange(size), np.arange(size))
    light_tile = ((xs // square + ys // square) % 2) == 0
    gray = np.where(light_tile, 235, 210).astype(np.uint8)
    rgb = np.repeat(gray[:, :, None], 3, axis=2)
    return Image.fromarray(rgb, "RGB").convert("RGBA")


def _render_frame_cell(frame: np.ndarray) -> Image.Image:
    cell = _checkerboard(CELL_PX)
    up = Image.fromarray(frame, "RGBA").resize((CELL_PX, CELL_PX), Image.NEAREST)
    cell.alpha_composite(up)
    return cell


def build_contact_sheet(sprites: list[ConvertedSprite]) -> Image.Image:
    frames_per_row = len(sprites[0].frames) if sprites else 9
    width = PAD * 2 + frames_per_row * CELL_PX + (frames_per_row - 1) * GAP
    row_h = HEADER_H + CELL_PX
    height = PAD * 2 + max(len(sprites), 1) * row_h + max(len(sprites) - 1, 0) * ROW_GAP
    canvas = Image.new("RGBA", (width, height), (250, 250, 250, 255))
    draw = ImageDraw.Draw(canvas)
    font = _font(16)

    y = PAD
    for sprite in sprites:
        label = (
            f"{sprite.name}   cycle={sprite.cycle}   "
            f"asymmetry={sprite.asymmetry:.3f}   "
            f"content={sprite.content_size[0]}x{sprite.content_size[1]}"
        )
        draw.text((PAD, y), label, fill=(20, 20, 20, 255), font=font)
        fy = y + HEADER_H
        x = PAD
        for frame in sprite.frames:
            canvas.alpha_composite(_render_frame_cell(frame), (x, fy))
            x += CELL_PX + GAP
        y = fy + CELL_PX + ROW_GAP
    return canvas


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sheets",
        help="Comma-separated sheet names to convert (default: the built-in list).",
    )
    args = parser.parse_args()

    names = [s.strip() for s in args.sheets.split(",")] if args.sheets else list(DEFAULT_SHEETS)
    characters_dir = _characters_dir()

    rows: list[tuple[str, ConvertedSprite | None, str]] = []
    for name in names:
        try:
            path = _resolve_sheet(characters_dir, name)
            sprite = convert_character_sheet(path)
            rows.append((name, sprite, ""))
        except Exception as exc:  # noqa: BLE001 -- report per-sheet, keep converting the rest
            logger.error("%s: conversion failed: %s", name, exc)
            rows.append((name, None, str(exc)))

    ok_sprites = [sprite for _, sprite, _ in rows if sprite is not None]
    canvas = build_contact_sheet(ok_sprites)
    out_dir = _output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "sprite_conversion_preview.png"
    canvas.convert("RGB").save(out_path)

    print(f"wrote {out_path} ({canvas.width}x{canvas.height})")
    print()
    header = f"{'sheet':<18} {'cycle':<11} {'asymmetry':>9}  {'content':>9}  status"
    print(header)
    print("-" * len(header))
    for name, sprite, err in rows:
        if sprite is None:
            print(f"{name:<18} {'-':<11} {'-':>9}  {'-':>9}  FAILED: {err}")
        else:
            content = f"{sprite.content_size[0]}x{sprite.content_size[1]}"
            print(f"{name:<18} {sprite.cycle:<11} {sprite.asymmetry:>9.3f}  {content:>9}  ok")


if __name__ == "__main__":
    main()
