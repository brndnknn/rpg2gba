"""Build a lossless 2x downscaler for Uranium art and show original vs output.

Uranium art is a 2x nearest-neighbour upscale (verified: every visible 2x2 block
is uniform). So the native image is one pixel per 2x2 block. We downscale, then
put the original beside it. Both sides get the SAME readability upscale, so the
original stays twice the size of the downscaled version (equal pixels-per-source).

Usage:
  python scripts/downscale_compare.py pc    [SCALE]
  python scripts/downscale_compare.py hero  [SCALE]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

URANIUM = Path("/home/b/repos/uranium-src/_unpacked/Graphics")
HERO = URANIUM / "Characters/HERO.png"
NOWTOCH = URANIUM / "Tilesets/PU-Nowtoch.png"
OUT_DIR = Path("/home/b/repos/rpg2gba/output")
BG = (245, 245, 245, 255)

# even-aligned source crops (must start on even coords to match the 2x grid)
PC_BOX = (2, 1568, 152, 160)      # x, y, w, h  -> Pokémon Center on the atlas
HERO_BOX = (0, 0, 64, 64)         # down/col0 charset cell


def downscale_2x(img: Image.Image, phase: tuple[int, int] = (0, 0)) -> Image.Image:
    """One pixel per aligned 2x2 block (top-left). Lossless when blocks are
    uniform, which holds for all visible Uranium pixels."""
    a = np.asarray(img.convert("RGBA"))
    px, py = phase
    return Image.fromarray(a[py::2, px::2].copy(), "RGBA")


def trim_alpha(img: Image.Image) -> Image.Image:
    """Crop to visible (alpha>0) content. Note: PIL's getbbox would keep
    transparent-white pixels, so trim on alpha explicitly."""
    a = np.asarray(img.convert("RGBA"))
    if (a[..., 3] == 255).all():
        return img
    ys, xs = np.where(a[..., 3] > 0)
    if len(xs) == 0:
        return img
    return img.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))


def upscale(img: Image.Image, factor: int) -> Image.Image:
    return img.resize((img.width * factor, img.height * factor), Image.NEAREST)


def compose(orig: Image.Image, down: Image.Image, scale: int, out: Path,
            left_label: str, right_label: str):
    o = upscale(orig, scale)
    d = upscale(down, scale)

    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24
        )
        small = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18
        )
    except OSError:
        font = small = ImageFont.load_default()

    pad, gutter, label_h = 30, 80, 64
    meas = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lw = lambda s, f: meas.textlength(s, font=f)
    col_l = max(o.width, lw(left_label, font))
    col_r = max(d.width, lw(right_label, font))
    panel_h = max(o.height, d.height)
    W = int(pad * 2 + col_l + gutter + col_r)
    H = int(pad + label_h + panel_h + pad)
    canvas = Image.new("RGBA", (W, H), BG)
    dr = ImageDraw.Draw(canvas)

    lx, rx = pad, pad + col_l + gutter
    base_y = pad + label_h
    canvas.alpha_composite(o, (int(lx + (col_l - o.width) / 2), base_y + (panel_h - o.height) // 2))
    canvas.alpha_composite(d, (int(rx + (col_r - d.width) / 2), base_y + (panel_h - d.height) // 2))
    dr.text((lx + (col_l - lw(left_label, font)) / 2, pad), left_label, fill=(20, 20, 20, 255), font=font)
    dr.text((rx + (col_r - lw(right_label, font)) / 2, pad), right_label, fill=(20, 20, 20, 255), font=font)
    sub_l = f"{orig.width}×{orig.height}px"
    sub_r = f"{down.width}×{down.height}px"
    dr.text((lx + (col_l - lw(sub_l, small)) / 2, pad + 30), sub_l, fill=(110, 110, 110, 255), font=small)
    dr.text((rx + (col_r - lw(sub_r, small)) / 2, pad + 30), sub_r, fill=(110, 110, 110, 255), font=small)
    canvas.convert("RGB").save(out)
    print("wrote", out, canvas.size, "| scale", scale, "| orig", orig.size, "down", down.size)


def run_pc(scale: int):
    x, y, w, h = PC_BOX
    region = Image.open(NOWTOCH).convert("RGBA").crop((x, y, x + w, y + h))
    orig = trim_alpha(region)
    down = trim_alpha(downscale_2x(region))
    compose(orig, down, scale, OUT_DIR / "pc_downscale_compare.png",
            "Original (2× art)", "Downscaled ÷2 (native)")


def run_hero(scale: int):
    x, y, w, h = HERO_BOX
    region = Image.open(HERO).convert("RGBA").crop((x, y, x + w, y + h))
    orig = trim_alpha(region)
    down = trim_alpha(downscale_2x(region))
    compose(orig, down, scale, OUT_DIR / "hero_downscale_compare.png",
            "Original (2× art)", "Downscaled ÷2 (native)")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "pc"
    scale = int(sys.argv[2]) if len(sys.argv) > 2 else (4 if cmd == "pc" else 8)
    if cmd == "pc":
        run_pc(scale)
    elif cmd == "hero":
        run_hero(scale)
    else:
        print("unknown command", cmd)


if __name__ == "__main__":
    main()
