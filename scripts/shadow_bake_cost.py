"""Measure the real cost of baking hue-matched (darkened-colour) shadows into the
ground, vs the reusable-stipple approach, on the actual Moki Town map.

For every cell we build two 16x16 composites (15-bit):
  no-shadow : composite layers with semi-transparent (shadow) px DROPPED
  baked     : composite layers with shadow px KEPT (= darkened-colour shadow)
Split into 8x8, dedup. Then:
  Q1 (palette cost): are the darkened colours baking introduces already present in
      the tileset's existing colours? (exact + near, in 15-bit units)
  Q2 (tile cost): how many EXTRA distinct 8x8 tiles does baking add vs no-shadow,
      and how many distinct shadow-only shapes the stipple approach would add instead.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from rpg2gba.tileset_converter.graphics.raster import TileRasterizer
from rpg2gba.tileset_converter.graphics.sources import load_tileset_sources

MAP_ID, TILESET_ID = 32, 22


def to555(p):
    return (p[0] >> 3, p[1] >> 3, p[2] >> 3)


def drop_semi(img: Image.Image) -> Image.Image:
    """Zero (make transparent) the semi-transparent pixels of a tile."""
    img = img.convert("RGBA").copy()
    px = img.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = px[x, y]
            if 0 < a < 255:
                px[x, y] = (0, 0, 0, 0)
    return img


def tiles_8x8(cell: Image.Image) -> list[bytes]:
    """Four 8x8 tiles of a 16x16 cell, each as a 555 byte-key."""
    out = []
    for qy in (0, 8):
        for qx in (0, 8):
            sub = cell.crop((qx, qy, qx + 8, qy + 8)).convert("RGBA")
            out.append(bytes(v for p in sub.getdata()
                             for v in (to555(p[:3]) if p[3] == 255 else (255, 255, 255))))
    return out


def colors_of(cell: Image.Image) -> set:
    return {to555(p[:3]) for p in cell.convert("RGBA").getdata() if p[3] == 255}


def main() -> None:
    doc = json.loads(Path(f"output/uranium-build/maps/Map{MAP_ID:03d}.json").read_text())
    t = doc["tiles"]
    xs, ys, zs = t["xsize"], t["ysize"], t["zsize"]
    data = t["data"]
    r = TileRasterizer(load_tileset_sources(TILESET_ID))

    def at(x, y, z):
        return data[z * (ys * xs) + y * xs + x]

    # existing tileset colours (opaque px of every distinct rendered tile)
    distinct_ids = sorted({v for v in data if v != 0})
    existing = set()
    for tid in distinct_ids:
        existing |= colors_of(r.render(tid))

    noshadow_8, baked_8, shadow_shapes = set(), set(), set()
    baked_colors, noshadow_colors = set(), set()
    shadow_cells = 0

    for y in range(ys):
        for x in range(xs):
            col = [at(x, y, z) for z in range(zs)]
            if all(c == 0 for c in col):
                continue
            has_semi = False
            baked = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
            nosh = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
            shadow_only = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
            for tid in col:
                if tid == 0:
                    continue
                tile = r.render(tid).convert("RGBA")
                baked.alpha_composite(tile)
                nosh.alpha_composite(drop_semi(tile))
                # shadow-only = just the semi-transparent contribution (for stipple count)
                sp = tile.load()
                if any(0 < sp[i % 16, i // 16][3] < 255 for i in range(256)):
                    has_semi = True
                    sm = tile.copy()
                    mp = sm.load()
                    for yy in range(16):
                        for xx in range(16):
                            rr, gg, bb, aa = mp[xx, yy]
                            mp[xx, yy] = (rr, gg, bb, aa) if 0 < aa < 255 else (0, 0, 0, 0)
                    shadow_only.alpha_composite(sm)
            if has_semi:
                shadow_cells += 1
                shadow_shapes.update(tiles_8x8(shadow_only))
            noshadow_8.update(tiles_8x8(nosh))
            baked_8.update(tiles_8x8(baked))
            noshadow_colors |= colors_of(nosh)
            baked_colors |= colors_of(baked)

    darkened = baked_colors - noshadow_colors  # colours baking introduces

    def nearest(c, pool):
        return min(sum((a - b) ** 2 for a, b in zip(c, p)) ** 0.5 for p in pool)

    exact = sum(1 for c in darkened if c in existing)
    near2 = sum(1 for c in darkened if nearest(c, existing) <= 2)

    print(f"=== Shadow-bake cost — Moki Town ({xs}x{ys}) ===")
    print(f"cells with a shadow (semi-transparent) contribution: {shadow_cells}")
    print()
    print("Q2  TILE COST")
    print(f"  distinct 8x8 tiles, no-shadow (ground only): {len(noshadow_8)}")
    print(f"  distinct 8x8 tiles, baked (darkened shadows): {len(baked_8)}")
    print(f"  EXTRA tiles from baking: {len(baked_8) - len(noshadow_8)}")
    print(f"  (stipple approach instead adds {len(shadow_shapes)} distinct shadow-only 8x8 shapes)")
    print()
    print("Q1  PALETTE COST")
    print(f"  existing tileset colours (15-bit): {len(existing)}")
    print(f"  darkened colours baking introduces: {len(darkened)}")
    print(f"    already in tileset exactly: {exact} ({100*exact/max(len(darkened),1):.0f}%)")
    print(f"    within 1 step (<=2 in 555): {near2} ({100*near2/max(len(darkened),1):.0f}%)")
    print(f"    genuinely new (far) colours: {len(darkened) - near2}")


if __name__ == "__main__":
    main()
