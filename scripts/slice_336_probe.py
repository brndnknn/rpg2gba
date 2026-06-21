"""Throwaway: investigate Map048's autotile base-336 tiles (ts19 slot 6 is an
EMPTY autotile) + report the two slice tileset PNG dimensions / 2x-grid fit."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from PIL import Image, ImageChops

SRC = Path("/home/b/repos/uranium-src/_unpacked/Graphics/Tilesets")
MAPS = Path("output/uranium-build/maps")
TS = json.loads(Path("output/uranium-build/tilesets.json").read_text(encoding="utf-8"))

# --- 1. Map048 base-336 tiles: how many, which layer, what passage? ---
doc = json.loads((MAPS / "Map048.json").read_text(encoding="utf-8"))
t = doc["tiles"]
xs, ys, zs = t["xsize"], t["ysize"], t["zsize"]
data = t["data"]
passages = TS["19"]["passages"]


def at(x, y, z):
    return data[z * (ys * xs) + y * xs + x]


hits = []
for z in range(zs):
    for y in range(ys):
        for x in range(xs):
            tid = at(x, y, z)
            if 336 <= tid < 384:
                hits.append((x, y, z, tid))

print(f"Map048 base-336 tiles: {len(hits)} cells")
print(f"  layers used: {Counter(h[2] for h in hits)}")
print(f"  distinct tile ids: {sorted(set(h[3] for h in hits))}")
print(f"  passage byte for those ids: {[(tid, passages[tid]) for tid in sorted(set(h[3] for h in hits))]}")
# Is there a non-empty tile under/over each base-336 cell on another layer?
covered = 0
for x, y, z, tid in hits:
    col = [at(x, y, zz) for zz in range(zs)]
    others = [c for zz, c in enumerate(col) if zz != z and c != 0]
    if others:
        covered += 1
print(f"  of {len(hits)} cells, {covered} have a non-empty tile on another layer")

# --- 2. tileset PNG dims + 2x-grid check ---
for tid, fname in (("19", "Indoor(1).png"), ("22", "PU-Route01-02-Moki-Kevlar.png")):
    img = Image.open(SRC / fname).convert("RGBA")
    w, h = img.size
    print(f"\ntileset {tid} {fname}: {w}x{h}  (cols={w/32:.2f} tiles wide, rows={h/32:.2f})")
    # 2x2-uniformity proxy (pure PIL): box-average /2 vs nearest /2; uniform
    # blocks agree exactly. Fraction of agreeing pixels ~ uniformity.
    nn = img.resize((w // 2, h // 2), Image.NEAREST).convert("RGB")
    bx = img.reduce(2).convert("RGB")
    diff = ImageChops.difference(nn, bx)
    bbox = diff.getbbox()
    if bbox is None:
        print("  2x2-uniform: 100.00% (box==nearest everywhere => 2x upscale, /2 lossless)")
    else:
        # count non-zero pixels
        gray = diff.convert("L")
        hist = gray.histogram()
        nonzero = sum(hist[1:])
        total = (w // 2) * (h // 2)
        print(f"  2x2-uniform: {100*(1-nonzero/total):.2f}% (box==nearest) => 2x upscale, /2 ~lossless")
