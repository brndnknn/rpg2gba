#!/usr/bin/env python
"""Tileset budget census for the pathfinder slice.

For each distinct tileset_id used by Maps 049/048/032, measure:
  - how many distinct visual tile_ids (metatiles) are needed
  - how many distinct 8x8 tiles remain after dedup across all metatiles
  - palette fit at max_palettes=6 (primary-only) and max_palettes=13 (primary+secondary)

Run from the repo root so relative default paths resolve:
    /home/b/repos/rpg2gba/.venv/bin/python scripts/slice_tileset_budget.py
"""
from __future__ import annotations

import hashlib
import json
import logging
import sys
import traceback
from pathlib import Path

import numpy as np

# --- bootstrap logging so we can see what's happening -----------------------
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
# Suppress noisy sub-module debug chatter
for noisy in ("PIL", "rpg2gba"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

MAP_FILES = [
    Path("output/uranium-build/maps/Map049.json"),
    Path("output/uranium-build/maps/Map048.json"),
    Path("output/uranium-build/maps/Map032.json"),
]


def load_map(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def topmost_tiles(map_data: dict) -> list[int]:
    """Return the topmost-visual tile_id for every non-empty cell in the map.

    Scans layers z from (zsize-1) down to 0; first non-zero tile_id wins.
    Cells where ALL layers are 0 are skipped (fully empty).
    """
    tiles = map_data["tiles"]
    xs = tiles["xsize"]
    ys = tiles["ysize"]
    zs = tiles["zsize"]
    data = tiles["data"]
    visuals: list[int] = []
    for y in range(ys):
        for x in range(xs):
            for z in range(zs - 1, -1, -1):
                tid = data[z * (ys * xs) + y * xs + x]
                if tid != 0:
                    visuals.append(tid)
                    break
            # if all layers are 0, skip (fully empty cell)
    return visuals


def split_quadrants(img_16x16) -> list[np.ndarray]:
    """Split a 16x16 PIL RGBA image into four 8x8 numpy arrays."""
    quads = []
    for cy, cx in [(0, 0), (0, 8), (8, 0), (8, 8)]:
        q = img_16x16.crop((cx, cy, cx + 8, cy + 8))
        quads.append(np.asarray(q, dtype=np.uint8))
    return quads


def quad_hash(arr: np.ndarray) -> bytes:
    return hashlib.sha256(arr.tobytes()).digest()


def fmt_stats(stats: dict) -> str:
    return (
        f"n_palettes={stats['n_palettes']}, "
        f"max_colors={stats['max_colors']}, "
        f"mean_shift={stats['mean_shift_5bit']:.3f}, "
        f"p95_shift={stats['p95_shift_5bit']:.3f}"
    )


def main() -> None:
    # --- import graphics APIs ------------------------------------------------
    from rpg2gba.tileset_converter.graphics.sources import load_tileset_sources
    from rpg2gba.tileset_converter.graphics.raster import TileRasterizer
    from rpg2gba.tileset_converter.graphics.quantize import build_quantized_tileset

    # --- group maps by tileset_id --------------------------------------------
    tileset_maps: dict[int, list[dict]] = {}
    for p in MAP_FILES:
        md = load_map(p)
        ts_id = md["tileset_id"]
        tileset_maps.setdefault(ts_id, []).append(md)

    print(f"Found tileset_ids: {sorted(tileset_maps.keys())}")
    print()

    results: dict[int, dict] = {}

    for ts_id in sorted(tileset_maps.keys()):
        maps = tileset_maps[ts_id]
        map_ids = [m["map_id"] for m in maps]
        print(f"=== tileset_id={ts_id}  maps={map_ids} ===")

        # Step 1: collect distinct visual tile_ids across all maps for this tileset
        all_visual_tids: list[int] = []
        total_cells = 0
        for md in maps:
            vis = topmost_tiles(md)
            total_cells += len(vis)
            all_visual_tids.extend(vis)

        distinct_tids = sorted(set(all_visual_tids))
        n_metatiles = len(distinct_tids)
        print(f"  Maps: {len(maps)}, cells scanned: {total_cells}")
        print(f"  Distinct visual tile_ids (=metatiles): {n_metatiles}")
        print(f"  tile_id range: {distinct_tids[0]}..{distinct_tids[-1]}")

        # Step 2: render each distinct tile_id; split into 8x8 quadrants; dedup
        print(f"  Loading tileset sources ...")
        sources = load_tileset_sources(ts_id)
        rast = TileRasterizer(sources)

        seen_hashes: dict[bytes, np.ndarray] = {}
        failed_tids: list[int] = []

        print(f"  Rendering {n_metatiles} tile_ids ...")
        for tid in distinct_tids:
            try:
                img = rast.render(tid)  # 16x16 RGBA PIL Image
            except Exception as e:
                failed_tids.append(tid)
                print(f"    WARN: render({tid}) failed: {e}", file=sys.stderr)
                continue
            for quad in split_quadrants(img):
                h = quad_hash(quad)
                if h not in seen_hashes:
                    seen_hashes[h] = quad

        n_8x8_tiles = len(seen_hashes)
        print(f"  Distinct 8x8 tiles (after dedup): {n_8x8_tiles}")
        if failed_tids:
            print(f"  WARN: {len(failed_tids)} tile_ids failed to render: {failed_tids}")

        # Step 3: quantize at max_palettes=6 and max_palettes=13
        tile_arrays = list(seen_hashes.values())

        print(f"  Quantizing at max_palettes=6 ...")
        res6 = build_quantized_tileset(tile_arrays, max_palettes=6)
        stats6 = res6.stats
        print(f"    {fmt_stats(stats6)}")

        print(f"  Quantizing at max_palettes=13 ...")
        res13 = build_quantized_tileset(tile_arrays, max_palettes=13)
        stats13 = res13.stats
        print(f"    {fmt_stats(stats13)}")

        results[ts_id] = {
            "map_ids": map_ids,
            "n_maps": len(maps),
            "cells_scanned": total_cells,
            "n_metatiles": n_metatiles,
            "n_8x8_tiles": n_8x8_tiles,
            "failed_tids": failed_tids,
            "stats_6": stats6,
            "stats_13": stats13,
        }
        print()

    # --- Summary table -------------------------------------------------------
    print("=" * 72)
    print("SUMMARY TABLE")
    print("=" * 72)
    hdr = f"{'ts_id':>6} {'maps':>4} {'cells':>7} {'metatiles':>9} {'8x8tiles':>8}"
    print(hdr)
    print("-" * len(hdr))
    for ts_id, r in results.items():
        print(
            f"{ts_id:>6} {r['n_maps']:>4} {r['cells_scanned']:>7} "
            f"{r['n_metatiles']:>9} {r['n_8x8_tiles']:>8}"
        )
    print()

    # max_palettes=6 stats
    print(f"{'ts_id':>6}  max_palettes=6:  n_pal  max_col  mean_shift  p95_shift")
    print("-" * 64)
    for ts_id, r in results.items():
        s = r["stats_6"]
        print(
            f"{ts_id:>6}                   {s['n_palettes']:>5}    {s['max_colors']:>5}"
            f"      {s['mean_shift_5bit']:>6.3f}      {s['p95_shift_5bit']:>6.3f}"
        )
    print()

    # max_palettes=13 stats
    print(f"{'ts_id':>6}  max_palettes=13: n_pal  max_col  mean_shift  p95_shift")
    print("-" * 64)
    for ts_id, r in results.items():
        s = r["stats_13"]
        print(
            f"{ts_id:>6}                   {s['n_palettes']:>5}    {s['max_colors']:>5}"
            f"      {s['mean_shift_5bit']:>6.3f}      {s['p95_shift_5bit']:>6.3f}"
        )
    print()

    # --- Verdict -------------------------------------------------------------
    PRIMARY_MAX_TILES = 512
    PRIMARY_MAX_METATILES = 512
    PRIMARY_MAX_PALETTES = 6
    # "acceptable shift" heuristic: p95 <= 3.0/31 (roughly ±1 step in 5-bit)
    # (user validated 0.95/31 on Moki Town; set a generous threshold here)
    SHIFT_P95_OK = 3.0

    print("VERDICT")
    print("-" * 64)
    for ts_id, r in results.items():
        s6 = r["stats_6"]
        fits_tiles = r["n_8x8_tiles"] <= PRIMARY_MAX_TILES
        fits_meta = r["n_metatiles"] <= PRIMARY_MAX_METATILES
        fits_pal = s6["n_palettes"] <= PRIMARY_MAX_PALETTES
        fits_shift = s6["p95_shift_5bit"] <= SHIFT_P95_OK

        if fits_tiles and fits_meta and fits_pal and fits_shift:
            verdict = "FITS single PRIMARY"
        else:
            reasons = []
            if not fits_tiles:
                reasons.append(f"8x8 tiles {r['n_8x8_tiles']} > {PRIMARY_MAX_TILES}")
            if not fits_meta:
                reasons.append(f"metatiles {r['n_metatiles']} > {PRIMARY_MAX_METATILES}")
            if not fits_pal:
                reasons.append(f"palettes@max6 {s6['n_palettes']} > {PRIMARY_MAX_PALETTES}")
            if not fits_shift:
                reasons.append(f"p95_shift@max6 {s6['p95_shift_5bit']:.3f} > {SHIFT_P95_OK}")

            s13 = r["stats_13"]
            fits13 = (
                r["n_8x8_tiles"] <= 1024
                and r["n_metatiles"] <= 1024
                and s13["n_palettes"] <= 13
            )
            suffix = "-> FITS PRIMARY+SECONDARY" if fits13 else "-> NEEDS SPLIT OR PRUNING"
            verdict = f"NEEDS PRIMARY+SECONDARY  ({'; '.join(reasons)})  {suffix}"

        print(f"  ts{ts_id}: {verdict}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
