"""Diagnose the black tree-tops. Hypothesis: resolve_alpha keeps partial-alpha
edge pixels whose STORED rgb is ~black (Uranium stores (0,0,0) under transparent /
anti-aliased pixels), so kept canopy-edge pixels become an opaque black fringe.

For every used tile_id in Moki Town: render true 16x16 (raw alpha), run resolve_alpha,
and count pixels that go partial-alpha -> opaque AND are near-black (the bug
signature). Rank tiles by that count, and dump a 12x before/resolved/quantized strip
over a magenta backdrop (so transparent vs black is unambiguous) for the worst ones.

Usage: python scripts/tree_alpha_diag.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from rpg2gba.tileset_converter.graphics.quantize import (
    build_quantized_tileset,
    classify_tile,
    resolve_alpha,
)
from rpg2gba.tileset_converter.graphics.raster import NATIVE_TILE_PX, TileRasterizer
from rpg2gba.tileset_converter.graphics.sources import load_tileset_sources

MAP_ID, TILESET_ID = 32, 22
TS = NATIVE_TILE_PX
SUB = TS // 2
MAGENTA = (255, 0, 255, 255)
NEAR_BLACK = 48


def near_black(rgb):
    return (rgb[..., 0] < NEAR_BLACK) & (rgb[..., 1] < NEAR_BLACK) & (rgb[..., 2] < NEAR_BLACK)


def on_magenta(tile, scale=12):
    bg = Image.new("RGBA", (tile.shape[1], tile.shape[0]), MAGENTA)
    bg.alpha_composite(Image.fromarray(tile, "RGBA"))
    return bg.resize((tile.shape[1] * scale, tile.shape[0] * scale), Image.NEAREST)


def main():
    doc = json.loads(Path(f"output/uranium-build/maps/Map{MAP_ID:03d}.json").read_text("utf-8"))
    used = sorted({t for t in doc["tiles"]["data"] if t})
    raster = TileRasterizer(load_tileset_sources(TILESET_ID))

    rows = []
    for tid in used:
        true = np.asarray(raster.render(tid).convert("RGBA"))
        a = true[..., 3]
        partial = (a > 0) & (a < 255)
        if not partial.any():
            continue
        resolved = resolve_alpha(true)
        ra = resolved[..., 3]
        newly_opaque = (ra == 255) & (a < 255)
        newly_black = int((newly_opaque & near_black(resolved[..., :3])).sum())
        opq_frac = float((a == 255).mean())
        rows.append((newly_black, int(partial.sum()), opq_frac, classify_tile(a), tid))

    rows.sort(reverse=True)
    print(f"{len(rows)} tile_ids have partial alpha. "
          f"Top by 'partial->opaque AND near-black' (the black-fringe signature):")
    print("  newly_black  partial  opaque%  mode      tile_id")
    for nb, npart, opq, mode, tid in rows[:24]:
        print(f"  {nb:9d}  {npart:7d}  {opq * 100:6.1f}  {mode:9s} {tid}")

    # Build the quantizer once so we can show the final colour too.
    sub_index, sub_list, tile_quads = {}, [], {}
    for tid in used:
        arr = np.asarray(raster.render(tid).convert("RGBA"))
        idxs = []
        for q in (arr[0:SUB, 0:SUB], arr[0:SUB, SUB:TS], arr[SUB:TS, 0:SUB], arr[SUB:TS, SUB:TS]):
            key = q.tobytes()
            if key not in sub_index:
                sub_index[key] = len(sub_list)
                sub_list.append(q.copy())
            idxs.append(sub_index[key])
        tile_quads[tid] = idxs
    weights = [0] * len(sub_list)
    for tid in doc["tiles"]["data"]:
        if tid:
            for qi in tile_quads[tid]:
                weights[qi] += 1
    result = build_quantized_tileset(sub_list, max_palettes=13, weights=weights)

    def quant_tile(tid):
        out = np.zeros((TS, TS, 4), np.uint8)
        q = [result.quantized[i] for i in tile_quads[tid]]
        out[0:SUB, 0:SUB], out[0:SUB, SUB:TS] = q[0], q[1]
        out[SUB:TS, 0:SUB], out[SUB:TS, SUB:TS] = q[2], q[3]
        return out

    worst = [tid for nb, *_ , tid in rows[:8] if nb > 0]
    panels = []
    for tid in worst:
        true = np.asarray(raster.render(tid).convert("RGBA"))
        strip = Image.new("RGBA", (TS * 12 * 3 + 24, TS * 12), (30, 30, 30, 255))
        strip.alpha_composite(on_magenta(true), (0, 0))
        strip.alpha_composite(on_magenta(resolve_alpha(true)), (TS * 12 + 12, 0))
        strip.alpha_composite(on_magenta(quant_tile(tid)), (TS * 12 * 2 + 24, 0))
        panels.append((tid, strip))

    if panels:
        w = panels[0][1].width
        sheet = Image.new("RGBA", (w, sum(p.height + 8 for _, p in panels)), (0, 0, 0, 255))
        y = 0
        for tid, strip in panels:
            sheet.alpha_composite(strip, (0, y))
            y += strip.height + 8
        out = Path("output/tree_alpha_diag.png")
        sheet.convert("RGB").save(out)
        print(f"\nwrote {out}: rows = worst tiles {worst}; "
              f"columns = TRUE | resolve_alpha | quantized (magenta = transparent)")


if __name__ == "__main__":
    main()
