"""Contact sheet of the HGSS NPC cast at GBA scale.

For every 256x256 HGSS_*.png: ÷2 downscale (native art), take the standing
front frame, trim, fit into 16x32. Frame border is RED if the native sprite is
wider than 16 (would lose pixels / want a 32x32 object), grey if it fits.
Prints aggregate fit stats.

Usage: python scripts/hgss_contact_sheet.py [SCALE] [COLS]
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

C = Path("/home/b/repos/uranium-src/_unpacked/Graphics/Characters")
OUT = Path("/home/b/repos/rpg2gba/output/hgss_contact_sheet.png")
FRAME_W, FRAME_H = 16, 32


def to_rgba_keyed(path: Path) -> np.ndarray:
    img = Image.open(path).convert("RGBA")
    a = np.asarray(img).copy()
    if (a[..., 3] == 255).all():  # no real alpha -> key out the corner colour
        key = a[0, 0, :3]
        a[np.all(a[..., :3] == key, axis=2), 3] = 0
    return a


def native_down_frame(path: Path) -> Image.Image | None:
    a = to_rgba_keyed(path)
    small = a[0::2, 0::2]  # ÷2 native
    cell = small[0:32, 0:32]  # down / col0 (32x32 native cell)
    ys, xs = np.where(cell[..., 3] > 0)
    if len(xs) == 0:
        return None
    return Image.fromarray(cell[ys.min():ys.max() + 1, xs.min():xs.max() + 1].copy(), "RGBA")


def fit_16x32(s: Image.Image):
    ow = max(0, s.width - FRAME_W)
    if s.width > FRAME_W:
        left = (s.width - FRAME_W) // 2
        s = s.crop((left, 0, left + FRAME_W, s.height))
    if s.height > FRAME_H:
        s = s.crop((0, s.height - FRAME_H, s.width, s.height))
    frame = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
    frame.alpha_composite(s, ((FRAME_W - s.width) // 2, FRAME_H - s.height))
    return frame, ow


def main():
    scale = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    cols = int(sys.argv[2]) if len(sys.argv) > 2 else 18

    files = sorted(C.glob("HGSS_*.png"))
    items = []
    widths = []
    for f in files:
        if Image.open(f).size != (256, 256):
            continue
        nf = native_down_frame(f)
        if nf is None:
            continue
        framed, ow = fit_16x32(nf)
        items.append((framed, ow, nf.width))
        widths.append(nf.width)

    widths = np.array(widths)
    n = len(widths)
    print(f"HGSS 256x256 sprites analysed: {n}")
    print(f"  native width: min {widths.min()}  median {int(np.median(widths))}  max {widths.max()}")
    print(f"  fit 16 wide (≤16):        {int((widths<=16).sum()):3d}  ({100*(widths<=16).mean():.0f}%)")
    print(f"  trim 1-3px (17-19):       {int(((widths>=17)&(widths<=19)).sum()):3d}  ({100*((widths>=17)&(widths<=19)).mean():.0f}%)")
    print(f"  want 32x32 (≥20 wide):    {int((widths>=20).sum()):3d}  ({100*(widths>=20).mean():.0f}%)")

    fw, fh = FRAME_W * scale, FRAME_H * scale
    gx, gy, pad, top = 8, 26, 16, 40
    rows = (len(items) + cols - 1) // cols
    W = pad * 2 + cols * fw + (cols - 1) * gx
    H = pad + top + rows * (fh + gy) + pad
    canvas = Image.new("RGBA", (W, H), (245, 245, 245, 255))
    d = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 17)
    except OSError:
        font = ImageFont.load_default()
    big = int((widths >= 20).sum())
    d.text((pad, pad + 6),
           f"HGSS NPC cast @ GBA 16×32  —  {n} sprites   "
           f"(grey ≤16 fit · amber 17-19 trim · red ≥20 wants 32×32: {big})",
           fill=(20, 20, 20, 255), font=font)

    for i, (framed, ow, w) in enumerate(items):
        r, c = divmod(i, cols)
        x = pad + c * (fw + gx)
        y = pad + top + r * (fh + gy)
        d.rectangle([x, y, x + fw - 1, y + fh - 1], fill=(255, 255, 255, 255))
        canvas.alpha_composite(framed.resize((fw, fh), Image.NEAREST), (x, y))
        if w >= 20:
            color = (210, 40, 40, 255)
        elif w >= 17:
            color = (230, 160, 30, 255)
        else:
            color = (150, 150, 150, 255)
        d.rectangle([x, y, x + fw - 1, y + fh - 1], outline=color, width=2)
    canvas.convert("RGB").save(OUT)
    print("wrote", OUT, canvas.size)


if __name__ == "__main__":
    main()
