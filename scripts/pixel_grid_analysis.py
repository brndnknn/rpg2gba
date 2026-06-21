"""Test the hypothesis that Uranium art is a 2x nearest-neighbour upscale.

If true, then at some (px,py) phase in {0,1}x{0,1} EVERY aligned 2x2 block is a
single solid colour, so downscaling by 2 (take one pixel per block) is lossless.

- block_constancy: fraction of aligned 2x2 blocks that are uniform, per phase.
- A genuine native sprite has lots of 1px edges -> low constancy. A 2x upscale ->
  ~100% at the correct phase.
- Also renders a pixel-grid zoom so the 2x2 blocks are visible by eye.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

POKE = Path("/home/b/repos/pokeemerald-expansion")
URANIUM = Path("/home/b/repos/uranium-src/_unpacked/Graphics")
OUT_DIR = Path("/home/b/repos/rpg2gba/output")


def trim_to_content(a: np.ndarray) -> np.ndarray:
    """Crop to the non-transparent bounding box (so transparent padding doesn't
    inflate uniformity)."""
    if a.shape[2] == 4 and (a[..., 3] < 255).any():
        ys, xs = np.where(a[..., 3] > 0)
        if len(ys):
            a = a[ys.min(): ys.max() + 1, xs.min(): xs.max() + 1]
    return a


def block_constancy(a: np.ndarray, py: int, px: int) -> float:
    h = (a.shape[0] - py) // 2 * 2
    w = (a.shape[1] - px) // 2 * 2
    if h == 0 or w == 0:
        return 0.0
    b = a[py:py + h, px:px + w].reshape(h // 2, 2, w // 2, 2, a.shape[2])
    tl = b[:, 0:1, :, 0:1, :]
    uniform = np.all(b == tl, axis=(1, 3, 4))
    return float(uniform.mean())


def analyze(path: Path, label: str, box=None):
    img = Image.open(path).convert("RGBA")
    if box:
        img = img.crop(box)
    a = np.asarray(img)
    a = trim_to_content(a)
    best_phase, best = (0, 0), 0.0
    for py in (0, 1):
        for px in (0, 1):
            c = block_constancy(a, py, px)
            if c > best:
                best, best_phase = c, (px, py)
    nblocks = (a.shape[0] // 2) * (a.shape[1] // 2)
    print(f"{label:38s} {a.shape[1]:4d}x{a.shape[0]:<4d} "
          f"best 2x2-uniform = {best*100:6.2f}%  phase{best_phase}  ({nblocks} blocks)")
    return best, best_phase


def grid_zoom(path: Path, out: Path, box=None, scale=14):
    img = Image.open(path).convert("RGBA")
    if box:
        img = img.crop(box)
    big = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    canvas = Image.new("RGBA", big.size, (255, 255, 255, 255))
    canvas.alpha_composite(big)
    d = ImageDraw.Draw(canvas)
    # light line at every native pixel boundary
    for x in range(0, img.width + 1):
        d.line([(x * scale, 0), (x * scale, big.height)], fill=(0, 0, 0, 60))
    for y in range(0, img.height + 1):
        d.line([(0, y * scale), (big.width, y * scale)], fill=(0, 0, 0, 60))
    # bold red line every 2 native pixels => outlines the 2x2 blocks
    for x in range(0, img.width + 1, 2):
        d.line([(x * scale, 0), (x * scale, big.height)], fill=(220, 0, 0, 200), width=2)
    for y in range(0, img.height + 1, 2):
        d.line([(0, y * scale), (big.width, y * scale)], fill=(220, 0, 0, 200), width=2)
    canvas.convert("RGB").save(out)
    print("wrote", out, canvas.size)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=== 2x2 block-uniformity test (≈100%% at one phase ⇒ 2x nearest upscale) ===")
    # Uranium candidates
    analyze(URANIUM / "Characters/HERO.png", "Uranium HERO (player, full sheet)")
    analyze(URANIUM / "Characters/HERO.png", "Uranium HERO frame (down,col0)", box=(0, 0, 64, 64))
    analyze(URANIUM / "Tilesets/PU-Nowtoch.png", "Uranium PU-Nowtoch tileset (full)")
    analyze(URANIUM / "Tilesets/PU-Nowtoch.png", "Uranium PC region", box=(0, 1569, 152, 1727))
    # Emerald controls (known native low-res)
    analyze(POKE / "graphics/object_events/pics/people/brendan/walking.png",
            "Emerald Brendan walking (control)")
    analyze(POKE / "data/tilesets/primary/general/tiles.png",
            "Emerald general tiles (control)")
    # visual grid of the Uranium player face/torso
    grid_zoom(URANIUM / "Characters/HERO.png", OUT_DIR / "_pixelgrid_uranium.png",
              box=(0, 0, 64, 64))


if __name__ == "__main__":
    main()
