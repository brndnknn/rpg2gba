"""Fit Uranium overworld sprites (÷2 downscaled) into the GBA 16x32 object frame.

For each character: downscale 2x (lossless native art), take the standing
front-facing frame, trim to content, then fit into 16x32 (center-crop width if
>16, bottom-align feet). Draws the 16x32 frame boundary so the fit/overhang is
visible. All sprites share one readability upscale.

Usage: python scripts/fit_npc_frames.py [SCALE]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

C = Path("/home/b/repos/uranium-src/_unpacked/Graphics/Characters")
OUT = Path("/home/b/repos/rpg2gba/output/npc_frames.png")
CELL = 64  # source charset cell (64x64); native after ÷2 = 32x32
FRAME_W, FRAME_H = 16, 32

# (file, label, col, row) — row 0 = facing down; col 0 = standing frame
CHARS = [
    ("HERO.png", "Hero", 0, 0),
    ("HEROINE.png", "Heroine", 0, 0),
    ("Gillian.png", "Gillian", 0, 0),
    ("HGSS_000.png", "NPC 000", 0, 0),
    ("HGSS_010.png", "NPC 010", 0, 0),
    ("HGSS_025.png", "NPC 025", 0, 0),
]


def downscale_2x(img: Image.Image) -> Image.Image:
    a = np.asarray(img.convert("RGBA"))
    return Image.fromarray(a[0::2, 0::2].copy(), "RGBA")


def trim_alpha(img: Image.Image) -> Image.Image:
    a = np.asarray(img.convert("RGBA"))
    ys, xs = np.where(a[..., 3] > 0)
    if len(xs) == 0:
        return img
    return img.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))


def native_frame(file: str, col: int, row: int) -> Image.Image:
    full = downscale_2x(Image.open(C / file))  # 128x128 native
    cell = full.crop((col * CELL // 2, row * CELL // 2,
                      (col + 1) * CELL // 2, (row + 1) * CELL // 2))  # 32x32
    return trim_alpha(cell)


def fit_16x32(sprite: Image.Image) -> tuple[Image.Image, int, int]:
    s = sprite
    overflow_w = max(0, s.width - FRAME_W)
    overflow_h = max(0, s.height - FRAME_H)
    if s.width > FRAME_W:  # center-crop width
        left = (s.width - FRAME_W) // 2
        s = s.crop((left, 0, left + FRAME_W, s.height))
    if s.height > FRAME_H:  # crop top, keep feet
        s = s.crop((0, s.height - FRAME_H, s.width, s.height))
    frame = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
    frame.alpha_composite(s, ((FRAME_W - s.width) // 2, FRAME_H - s.height))
    return frame, overflow_w, overflow_h


def upscale(img, f):
    return img.resize((img.width * f, img.height * f), Image.NEAREST)


def main():
    scale = int(sys.argv[1]) if len(sys.argv) > 1 else 9
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except OSError:
        font = sub = ImageFont.load_default()

    cells = []
    for file, label, col, row in CHARS:
        native = native_frame(file, col, row)
        framed, ow, oh = fit_16x32(native)
        cells.append((label, native, framed, ow))

    fw, fh = FRAME_W * scale, FRAME_H * scale
    pad, gutter, top_label, bot_label = 30, 36, 40, 50
    W = pad * 2 + len(cells) * fw + (len(cells) - 1) * gutter
    H = pad + top_label + fh + bot_label + pad
    canvas = Image.new("RGBA", (W, H), (245, 245, 245, 255))
    d = ImageDraw.Draw(canvas)
    meas = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    x = pad
    fy = pad + top_label
    for label, native, framed, ow in cells:
        big = upscale(framed, scale)
        # subtle checker-free frame: white box + border so the 16x32 bounds show
        d.rectangle([x, fy, x + fw - 1, fy + fh - 1], fill=(255, 255, 255, 255))
        canvas.alpha_composite(big, (x, fy))
        d.rectangle([x, fy, x + fw - 1, fy + fh - 1], outline=(150, 150, 150, 255), width=2)
        # labels
        lw = meas.textlength(label, font=font)
        d.text((x + (fw - lw) / 2, pad + 6), label, fill=(20, 20, 20, 255), font=font)
        note = f"{native.width}×{native.height}" + (f"  −{ow}w" if ow else "")
        nw = meas.textlength(note, font=sub)
        d.text((x + (fw - nw) / 2, fy + fh + 8), note, fill=(110, 110, 110, 255), font=sub)
        x += fw + gutter
    canvas.convert("RGB").save(OUT)
    print("wrote", OUT, canvas.size, "| frame", (FRAME_W, FRAME_H), "x", scale)


if __name__ == "__main__":
    main()
