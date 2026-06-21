"""Diagnostic for the step-4 quantizer: which Moki Town tiles are visibly wrong,
and why. Replicates quantize_moki_preview's tile gathering, then ranks tiles by
on-screen-weighted colour shift and prints each offender's true mean colour vs its
assigned sub-palette's mean colour — so we can see if the path/plaza tan is being
sacrificed into a green palette (mis-assignment) or no warm palette exists at all.

Usage: python scripts/quantize_diag.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from rpg2gba.tileset_converter.graphics.quantize import build_quantized_tileset, to_5bit
from rpg2gba.tileset_converter.graphics.raster import NATIVE_TILE_PX, TileRasterizer
from rpg2gba.tileset_converter.graphics.sources import load_tileset_sources

MAP_ID, TILESET_ID, MAX_PALETTES = 32, 22, 13
TS = NATIVE_TILE_PX
SUB = TS // 2


def quadrants(arr):
    return [arr[0:SUB, 0:SUB], arr[0:SUB, SUB:TS], arr[SUB:TS, 0:SUB], arr[SUB:TS, SUB:TS]]


def mean_opaque(tile):
    opq = tile[..., 3] == 255
    return to_5bit(tile[..., :3][opq]).mean(0) if opq.any() else np.array([0, 0, 0.0])


def main():
    doc = json.loads(Path(f"output/uranium-build/maps/Map{MAP_ID:03d}.json").read_text("utf-8"))
    used = sorted({t for t in doc["tiles"]["data"] if t})
    raster = TileRasterizer(load_tileset_sources(TILESET_ID))

    unique, index, tile_quads = [], {}, {}
    for tid in used:
        arr = np.asarray(raster.render(tid).convert("RGBA"))
        idxs = []
        for q in quadrants(arr):
            key = q.tobytes()
            if key not in index:
                index[key] = len(unique)
                unique.append(q.copy())
            idxs.append(index[key])
        tile_quads[tid] = idxs

    weights = [0] * len(unique)
    for tid in doc["tiles"]["data"]:
        if tid:
            for qi in tile_quads[tid]:
                weights[qi] += 1

    r = build_quantized_tileset(unique, max_palettes=MAX_PALETTES, weights=weights)

    # Per-palette: member count, total on-screen weight, mean colour.
    print("PALETTES (idx: tiles, screen-weight, ncolours, mean RGB):")
    for pi, pal in enumerate(r.palettes):
        members = [i for i in range(len(unique)) if r.tile_palette[i] == pi]
        wt = sum(weights[i] for i in members)
        mc = pal.astype(float).mean(0) if len(pal) else np.zeros(3)
        print(f"  {pi:2d}: {len(members):4d} tiles  wt={wt:6d}  n={len(pal):2d}  "
              f"mean=({mc[0]:3.0f},{mc[1]:3.0f},{mc[2]:3.0f})")

    # Worst offenders by on-screen weight * per-tile colour shift.
    rows = []
    for i, tile in enumerate(unique):
        opq = tile[..., 3] == 255
        if not opq.any():
            continue
        px = to_5bit(tile[..., :3][opq]).astype(np.int16)
        pi = r.tile_palette[i]
        pal = r.palettes[pi].astype(np.int16)
        idx = ((px[:, None, :] - pal[None, :, :]) ** 2).sum(2).argmin(1)
        shift = np.abs((px >> 3) - (pal[idx] >> 3)).mean()
        rows.append((weights[i] * shift, shift, weights[i], i, pi, px.mean(0), pal[idx].mean(0)))
    rows.sort(reverse=True)
    print("\nTOP 18 visibly-wrong tiles (weight*shift): "
          "shift  wt  pal  trueRGB -> mappedRGB  (palette meanRGB)")
    for score, shift, wt, i, pi, true_c, mapped_c in rows[:18]:
        pm = r.palettes[pi].astype(float).mean(0)
        print(f"  s={score:7.0f}  shift={shift:4.1f}  wt={wt:5d}  pal={pi:2d}  "
              f"({true_c[0]:3.0f},{true_c[1]:3.0f},{true_c[2]:3.0f}) -> "
              f"({mapped_c[0]:3.0f},{mapped_c[1]:3.0f},{mapped_c[2]:3.0f})  "
              f"palmean=({pm[0]:3.0f},{pm[1]:3.0f},{pm[2]:3.0f})")


if __name__ == "__main__":
    main()
