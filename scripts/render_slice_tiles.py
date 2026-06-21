"""Validate image-pipeline steps 1-3 on REAL slice data: reconstruct each map by
rendering every cell's stacked tiles (steps 1-3) and alpha-compositing the 3 RMXP
layers bottom->top, exactly as RMXP draws them. Output is pre-quantization (true
colour) — it shows whether the tiles/autotiles/downscale are correct, which is
what steps 1-3 own. Writes PNGs to output/ for eyeballing.

Usage: python scripts/render_slice_tiles.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from rpg2gba.tileset_converter.graphics.raster import NATIVE_TILE_PX, TileRasterizer
from rpg2gba.tileset_converter.graphics.sources import load_tileset_sources

MAPS = {49: 19, 48: 19, 32: 22}  # map_id -> tileset_id
MAPS_DIR = Path("output/uranium-build/maps")
OUT = Path("output")
TS = NATIVE_TILE_PX  # 16


def reconstruct(map_id: int, tileset_id: int) -> Image.Image:
    doc = json.loads((MAPS_DIR / f"Map{map_id:03d}.json").read_text(encoding="utf-8"))
    t = doc["tiles"]
    xs, ys, zs = t["xsize"], t["ysize"], t["zsize"]
    data = t["data"]
    r = TileRasterizer(load_tileset_sources(tileset_id))

    def at(x, y, z):
        return data[z * (ys * xs) + y * xs + x]

    canvas = Image.new("RGBA", (xs * TS, ys * TS), (40, 40, 60, 255))
    for y in range(ys):
        for x in range(xs):
            cell = Image.new("RGBA", (TS, TS), (0, 0, 0, 0))
            for z in range(zs):  # bottom -> top
                tid = at(x, y, z)
                if tid == 0:
                    continue
                cell.alpha_composite(r.render(tid))
            canvas.alpha_composite(cell, (x * TS, y * TS))
    return canvas


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for map_id, tileset_id in MAPS.items():
        img = reconstruct(map_id, tileset_id)
        out = OUT / f"slice_map{map_id:03d}_reconstruct.png"
        # also write a 2x zoom for readability
        img.convert("RGB").save(out)
        img.resize((img.width * 2, img.height * 2), Image.NEAREST).convert("RGB").save(
            OUT / f"slice_map{map_id:03d}_reconstruct_2x.png"
        )
        print(f"Map{map_id:03d} (ts{tileset_id}): {img.width}x{img.height} -> {out}")


if __name__ == "__main__":
    main()
