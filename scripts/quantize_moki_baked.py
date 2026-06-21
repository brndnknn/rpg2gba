"""Step-4 shadow option B: BAKED darkened-colour shadows (the user's pick over drop).

Instead of resolving each tileset tile's alpha in isolation and dropping shadows, this
composites each map cell's 3 RMXP layers in TRUE COLOUR with real alpha FIRST — so a
semi-transparent shadow darkens the ground tile beneath it (hue-preserving), tree
edges blend into the real grass below (no black fringe), and the result is fully
opaque. THEN it dedupes the composited 8x8 tiles and quantizes those. This is the
"extract GBA tiles from the rendered map" model, which also collapses 3 layers -> a
flat tile set (relevant to the 3->2 layer question).

Outputs a TRUE | DROP | BAKED house comparison + the baked town, and reports the
unique-8x8 cost (baking ground+shadow combos adds tiles).

Usage: python scripts/quantize_moki_baked.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from rpg2gba.tileset_converter.graphics.quantize import build_quantized_tileset
from rpg2gba.tileset_converter.graphics.raster import NATIVE_TILE_PX, TileRasterizer
from rpg2gba.tileset_converter.graphics.sources import load_tileset_sources

MAP_ID, TILESET_ID, MAX_PALETTES = 32, 22, 13
MAPS_DIR = Path("output/uranium-build/maps")
OUT = Path("output")
TS = NATIVE_TILE_PX           # 16
SUB = TS // 2                 # 8
VOID = (40, 40, 60, 255)


def composite_cells(doc, raster: TileRasterizer) -> tuple[np.ndarray, int, int]:
    """Return an (ys, xs, 16,16,4) array of true-colour composited cells (shadows
    baked, fully opaque where any layer is opaque)."""
    t = doc["tiles"]
    xs, ys, zs = t["xsize"], t["ysize"], t["zsize"]
    data = t["data"]
    cells = np.zeros((ys, xs, TS, TS, 4), np.uint8)
    for y in range(ys):
        for x in range(xs):
            cell = Image.new("RGBA", (TS, TS), (0, 0, 0, 0))
            for z in range(zs):  # bottom -> top, true colour + real alpha
                tid = data[z * (ys * xs) + y * xs + x]
                if tid:
                    cell.alpha_composite(raster.render(tid))  # bakes shadow over ground
            cells[y, x] = np.asarray(cell)
    return cells, xs, ys


def dedupe_8x8(cells: np.ndarray):
    """Split composited cells into 8x8 quadrants; return (unique list, per-cell idx)."""
    ys, xs = cells.shape[:2]
    unique, index = [], {}
    cell_quads = {}
    for y in range(ys):
        for x in range(xs):
            arr = cells[y, x]
            idxs = []
            for q in (arr[0:SUB, 0:SUB], arr[0:SUB, SUB:TS],
                      arr[SUB:TS, 0:SUB], arr[SUB:TS, SUB:TS]):
                key = q.tobytes()
                if key not in index:
                    index[key] = len(unique)
                    unique.append(q.copy())
                idxs.append(index[key])
            cell_quads[(x, y)] = idxs
    return unique, cell_quads


def recompose(cell_quads, quant, xs, ys) -> Image.Image:
    canvas = Image.new("RGBA", (xs * TS, ys * TS), VOID)
    for (x, y), idxs in cell_quads.items():
        out = np.zeros((TS, TS, 4), np.uint8)
        out[0:SUB, 0:SUB], out[0:SUB, SUB:TS] = quant[idxs[0]], quant[idxs[1]]
        out[SUB:TS, 0:SUB], out[SUB:TS, SUB:TS] = quant[idxs[2]], quant[idxs[3]]
        canvas.alpha_composite(Image.fromarray(out, "RGBA"), (x * TS, y * TS))
    return canvas


def main():
    doc = json.loads((MAPS_DIR / f"Map{MAP_ID:03d}.json").read_text("utf-8"))
    raster = TileRasterizer(load_tileset_sources(TILESET_ID))

    cells, xs, ys = composite_cells(doc, raster)
    unique, cell_quads = dedupe_8x8(cells)

    result = build_quantized_tileset(unique, max_palettes=MAX_PALETTES)
    s = result.stats
    print(f"BAKED Map{MAP_ID:03d}: {len(unique)} unique composited 8x8 -> "
          f"{s['n_palettes']} palettes, max {s['max_colors']} colours, "
          f"on-screen-ish mean shift {s['mean_shift_5bit']:.2f}/31")

    baked = recompose(cell_quads, result.quantized, xs, ys)

    # True-colour reference (same compositing, no quantization).
    true = Image.new("RGBA", (xs * TS, ys * TS), VOID)
    for y in range(ys):
        for x in range(xs):
            true.alpha_composite(Image.fromarray(cells[y, x], "RGBA"), (x * TS, y * TS))

    baked.convert("RGB").save(OUT / "quantize_moki_baked.png")

    # House crop: TRUE (top) | BAKED (bottom), 4x — same region as _house_shadow.png.
    box = (75, 115, 330, 235)  # native coords (1x)
    def up(im): return im.resize((im.width * 4, im.height * 4), Image.NEAREST)
    t4, b4 = up(true.crop(box)), up(baked.crop(box))
    strip = Image.new("RGBA", (t4.width, t4.height * 2 + 10), VOID)
    strip.alpha_composite(t4, (0, 0))
    strip.alpha_composite(b4, (0, t4.height + 10))
    strip.convert("RGB").save(OUT / "_house_shadow_baked.png")
    print("wrote output/quantize_moki_baked.png and "
          "output/_house_shadow_baked.png (top=true, bottom=baked, 4x)")


if __name__ == "__main__":
    main()
