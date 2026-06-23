"""Per-layer debug view for one region of a Uranium map (Idea 1).

For a rectangular cell range of a Phase-3 map, render the region assembled from
ONE layer at a time, so the 3->2 layer collapse is eyeballable:

  RMXP L0 / L1 / L2  (the 3 stacked source layers, bottom-first)
  RMXP composite     (all 3 RMXP layers alpha-composited = what RPG Maker draws)
  GBA bottom / top   (the two pokeemerald metatile layers, pre-quantization, via
                      the same priority split build_slice_tilesets uses)
  GBA composite      (bottom+top composited = what the ROM intends to draw)

The GBA columns are the *pre-quantization* art (clean `_render_column` output),
not the palette-reduced bytes in the ROM — this isolates the collapse/priority
logic from quantization drift.

Each panel is a coordinate-labelled grid so a cell can be read off by (x, y).
Also dumps a per-cell text table of layer tile_ids + RMXP priority.

Usage:
    python scripts/tree_debug.py --x0 33 --y0 40 --x1 43 --y1 48 --zoom 7
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from rpg2gba.tileset_converter.graphics.build_slice_tilesets import _render_column
from rpg2gba.tileset_converter.graphics.raster import NATIVE_TILE_PX, TileRasterizer
from rpg2gba.tileset_converter.graphics.sources import load_tileset_sources
from rpg2gba.tileset_converter.layout import TileGrid, column_key

MAPS_DIR = Path("output/uranium-build/maps")
TILESETS_JSON = Path("output/uranium-build/tilesets.json")
OUT = Path("output")
TS = NATIVE_TILE_PX  # 16
VOID = (40, 40, 60, 255)
MARGIN = 22  # px for the coordinate label gutters (pre-zoom space is separate)


def _transparent() -> Image.Image:
    return Image.new("RGBA", (TS, TS), (0, 0, 0, 0))


def _composite(layers: list[Image.Image]) -> Image.Image:
    cell = Image.new("RGBA", (TS, TS), (0, 0, 0, 0))
    for img in layers:
        cell.alpha_composite(img)
    return cell


def _pil(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(arr, "RGBA")


def assemble(getter, x0, y0, x1, y1) -> Image.Image:
    """Tile `getter(x, y)` -> 16x16 RGBA across the bbox into one image (VOID bg)."""
    w, h = (x1 - x0 + 1), (y1 - y0 + 1)
    canvas = Image.new("RGBA", (w * TS, h * TS), VOID)
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            canvas.alpha_composite(getter(x, y), ((x - x0) * TS, (y - y0) * TS))
    return canvas


def label_panel(img: Image.Image, title: str, x0, y0, x1, y1, zoom: int) -> Image.Image:
    """Upscale NEAREST, draw a cell grid + x/y coordinate gutters + a title bar."""
    w, h = img.size
    big = img.resize((w * zoom, h * zoom), Image.NEAREST).convert("RGB")
    panel = Image.new("RGB", (big.width + MARGIN, big.height + 2 * MARGIN), (15, 15, 20))
    panel.paste(big, (MARGIN, 2 * MARGIN))
    d = ImageDraw.Draw(panel)
    d.text((4, 6), title, fill=(255, 230, 120))
    cell = TS * zoom
    cols, rows = (x1 - x0 + 1), (y1 - y0 + 1)
    for c in range(cols + 1):  # vertical grid lines
        gx = MARGIN + c * cell
        d.line([(gx, 2 * MARGIN), (gx, panel.height)], fill=(70, 70, 80))
        if c < cols:
            d.text((gx + 3, 2 * MARGIN - 11), str(x0 + c), fill=(150, 200, 255))
    for r in range(rows + 1):  # horizontal grid lines
        gy = 2 * MARGIN + r * cell
        d.line([(MARGIN, gy), (panel.width, gy)], fill=(70, 70, 80))
        if r < rows:
            d.text((3, gy + 3), str(y0 + r), fill=(150, 200, 255))
    return panel


def dump_text(grid: TileGrid, priorities, x0, y0, x1, y1) -> None:
    print(f"\nper-cell layer tile_ids (priority in parens) for "
          f"x[{x0}..{x1}] y[{y0}..{y1}]:")
    print("  y\\x " + " ".join(f"{x:>14}" for x in range(x0, x1 + 1)))
    for y in range(y0, y1 + 1):
        cells = []
        for x in range(x0, x1 + 1):
            parts = []
            for z in range(grid.zsize):
                tid = grid.tile_at(x, y, z)
                if tid:
                    pr = priorities[tid] if 0 <= tid < len(priorities) else 0
                    parts.append(f"{tid}{'^' if pr else ''}")
                else:
                    parts.append("·")
            cells.append("/".join(parts))
        print(f"  {y:>3} " + " ".join(f"{c:>14}" for c in cells))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", type=int, default=32)
    ap.add_argument("--tileset", type=int, default=22)
    ap.add_argument("--x0", type=int, default=33)
    ap.add_argument("--y0", type=int, default=40)
    ap.add_argument("--x1", type=int, default=43)
    ap.add_argument("--y1", type=int, default=48)
    ap.add_argument("--zoom", type=int, default=7)
    ap.add_argument("--out", default="output/tree_debug.png")
    args = ap.parse_args()

    doc = json.loads((MAPS_DIR / f"Map{args.map:03d}.json").read_text(encoding="utf-8"))
    t = doc["tiles"]
    grid = TileGrid(t["xsize"], t["ysize"], t["zsize"], t["data"])
    priorities = json.loads(TILESETS_JSON.read_text(encoding="utf-8"))[
        str(args.tileset)]["priorities"]
    raster = TileRasterizer(load_tileset_sources(args.tileset))

    def rmxp_layer(z):
        def g(x, y):
            tid = grid.tile_at(x, y, z)
            return raster.render(tid) if tid else _transparent()
        return g

    def rmxp_comp(x, y):
        return _composite([raster.render(grid.tile_at(x, y, z)) if grid.tile_at(x, y, z)
                           else _transparent() for z in range(grid.zsize)])

    def gba(which):
        def g(x, y):
            mt = _render_column(column_key(grid, x, y), raster, priorities)
            return _pil(mt.bottom if which == "bottom" else mt.top)
        return g

    def gba_comp(x, y):
        mt = _render_column(column_key(grid, x, y), raster, priorities)
        return _composite([_pil(mt.bottom), _pil(mt.top)])

    bbox = (args.x0, args.y0, args.x1, args.y1)
    panels = [
        ("RMXP L0 (bottom)", rmxp_layer(0)),
        ("RMXP L1 (middle)", rmxp_layer(1)),
        ("RMXP L2 (top)", rmxp_layer(2)),
        ("RMXP composite (what RPG Maker draws)", rmxp_comp),
        ("GBA bottom layer (below player)", gba("bottom")),
        ("GBA top layer (over player)", gba("top")),
        ("GBA composite (what the ROM draws)", gba_comp),
    ]

    images = [label_panel(assemble(g, *bbox), title, *bbox, args.zoom)
              for title, g in panels]
    pad = 10
    width = max(im.width for im in images)
    height = sum(im.height for im in images) + pad * (len(images) - 1)
    sheet = Image.new("RGB", (width, height), (8, 8, 10))
    yoff = 0
    for im in images:
        sheet.paste(im, (0, yoff))
        yoff += im.height + pad

    OUT.mkdir(exist_ok=True)
    sheet.save(args.out)
    dump_text(grid, priorities, *bbox)
    print(f"\nwrote {args.out}  ({sheet.width}x{sheet.height})")


if __name__ == "__main__":
    main()
