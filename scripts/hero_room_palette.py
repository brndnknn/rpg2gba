"""Inventory the hero's room (Map048, Player's House 2F) tiles and report the
palette situation against real GBA constraints, to gauge how much *lossy*
quantization step 4 actually needs.

GBA facts that decide it:
  - colour is 15-bit BGR555 (truecolor -> 555 is depth reduction, ~lossless visually).
  - a 4bpp tile = one 16-colour sub-palette (index 0 = transparent => 15 usable opaque).
  - a tileset has <= 13 sub-palettes (primary 6 + secondary 7, dedicated pair).

So lossy quantization is only forced when (a) a single 8x8 tile needs > 15 opaque
colours, or (b) the room's tiles can't be grouped into <= 13 palettes of <= 15.
We measure both. Unit of analysis = the 8x8 tile (GBA's real tile + palette unit).
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

from PIL import Image

from rpg2gba.tileset_converter.graphics.raster import TileRasterizer
from rpg2gba.tileset_converter.graphics.sources import load_tileset_sources

# args: map_id tileset_id [label]   (default = hero's room)
MAP_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 48
TILESET_ID = int(sys.argv[2]) if len(sys.argv) > 2 else 19
LABEL = sys.argv[3] if len(sys.argv) > 3 else "Hero's room"
MAPS_DIR = Path("output/uranium-build/maps")
PAL_LIMIT, USABLE = 16, 15      # colours per 4bpp tile (index 0 transparent)
PAL_BUDGET = 13                 # sub-palettes available (primary 6 + secondary 7)


def to555(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    return (rgb[0] >> 3, rgb[1] >> 3, rgb[2] >> 3)


def tile_colors(img: Image.Image) -> tuple[set, int, int]:
    """Distinct opaque 555 colours in an 8x8 tile; + counts of transparent &
    semi-transparent pixels."""
    colors, transp, semi = set(), 0, 0
    for r, g, b, a in img.getdata():
        if a == 0:
            transp += 1
        elif a == 255:
            colors.add(to555((r, g, b)))
        else:
            semi += 1
    return colors, transp, semi


def pack_palettes(color_sets: list[set]) -> tuple[list[set], int]:
    """Cluster <=15-colour tile color-sets into <=15-colour palettes by bottom-up
    AGGLOMERATIVE merging: start one cluster per distinct color-set, repeatedly
    merge the pair with the smallest union (<=15) until none can merge. Returns
    (palettes, num_distinct_color_sets). Honest per-tile constraint (a tile lives
    wholly in one palette); heuristic, not provably optimal."""
    clusters = list({frozenset(s) for s in color_sets if s})
    n_distinct = len(clusters)
    clusters = [set(c) for c in clusters]
    while True:
        best, best_union = None, USABLE + 1
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                u = len(clusters[i] | clusters[j])
                if u <= USABLE and u < best_union:
                    best, best_union = (i, j), u
        if best is None:
            break
        i, j = best
        clusters[i] |= clusters[j]
        clusters.pop(j)
    return clusters, n_distinct


def main() -> None:
    doc = json.loads((MAPS_DIR / f"Map{MAP_ID:03d}.json").read_text(encoding="utf-8"))
    t = doc["tiles"]
    data = t["data"]
    distinct_ids = sorted({x for x in data if x != 0})

    r = TileRasterizer(load_tileset_sources(TILESET_ID))

    # Render each distinct RMXP tile -> 16x16, split into four 8x8 tiles, dedup
    # 8x8 by content (555). Each distinct 8x8 is what the GBA tileset stores.
    distinct_8x8: dict[bytes, Image.Image] = {}
    all_room_colors: set = set()
    semi_total = 0
    for tid in distinct_ids:
        tile16 = r.render(tid).convert("RGBA")
        for qy in (0, 8):
            for qx in (0, 8):
                sub = tile16.crop((qx, qy, qx + 8, qy + 8))
                cols, _, semi = tile_colors(sub)
                semi_total += semi
                all_room_colors |= cols
                # dedup key from 555-quantized bytes so depth reduction merges twins
                key = bytes(
                    v
                    for px in sub.getdata()
                    for v in (to555(px[:3]) if px[3] == 255 else (255, 255, 255))
                )
                distinct_8x8.setdefault(key, sub)

    # Per-8x8 colour analysis.
    per_tile = []
    over_15 = []
    for key, sub in distinct_8x8.items():
        cols, _, _ = tile_colors(sub)
        per_tile.append(len(cols))
        if len(cols) > USABLE:
            over_15.append(len(cols))

    fit_sets = [tile_colors(s)[0] for s in distinct_8x8.values() if len(tile_colors(s)[0]) <= USABLE]
    palettes, n_distinct_sets = pack_palettes(fit_sets)

    # Truecolor vs 555: how much the mandatory 15-bit reduction already merges.
    truecolor: set = set()
    for tid in distinct_ids:
        for px in r.render(tid).convert("RGBA").getdata():
            if px[3] == 255:
                truecolor.add(px[:3])

    # Whole-tileset colour count for context.
    print(f"=== {LABEL} — Map{MAP_ID:03d}, tileset {TILESET_ID} ===")
    print(f"map cells: {t['xsize']}x{t['ysize']} (x{t['zsize']} layers)")
    print(f"distinct RMXP tiles used: {len(distinct_ids)}")
    print(f"distinct 8x8 GBA tiles (after 555 dedup): {len(distinct_8x8)}")
    print(f"semi-transparent pixels (0<a<255): {semi_total}")
    print()
    print(f"distinct opaque colours: truecolor={len(truecolor)} -> 15-bit={len(all_room_colors)} "
          f"(15-bit reduction merges {len(truecolor)-len(all_room_colors)})")
    print(f"  palette budget = {PAL_BUDGET} subpals x {USABLE} = {PAL_BUDGET*USABLE} usable slots; "
          f"theoretical min palettes = ceil({len(all_room_colors)}/{USABLE}) = "
          f"{-(-len(all_room_colors)//USABLE)}")
    print()
    hist = Counter(per_tile)
    print("per-8x8-tile opaque colour counts:")
    print(f"  min={min(per_tile)} max={max(per_tile)} mean={sum(per_tile)/len(per_tile):.1f}")
    print(f"  8x8 tiles needing >15 colours (FORCED lossy intra-tile quant): {len(over_15)}"
          + (f" -> {sorted(over_15, reverse=True)}" if over_15 else ""))
    print(f"  distribution: {dict(sorted(hist.items()))}")
    print()
    print(f"distinct color-sets among the <=15-colour 8x8 tiles: {n_distinct_sets}")
    print(f"palette packing (agglomerative min-union) -> {len(palettes)} sub-palettes "
          f"at ZERO colour loss (budget {PAL_BUDGET})")
    print()

    # Fidelity sweep: globally median-cut the room to K colours, re-derive per-tile
    # color sets against that reduced palette, re-pack. Shows how much colour
    # merging it takes to reach the 13-palette budget, and how lossy that is.
    all_px = [px[:3] for s in distinct_8x8.values() for px in s.getdata() if px[3] == 255]
    flat = Image.new("RGB", (len(all_px), 1))
    flat.putdata(all_px)
    print("fidelity sweep (global median-cut to K colours -> palettes needed):")
    print(f"  {'K':>5} {'mean px err':>11} {'palettes':>9}")
    for k in (256, 195, 160, 128, 96, 72, 48, 32, 24, 16):
        if k >= len(all_room_colors):
            kpal = sorted(all_room_colors)  # no loss
            remap = {c: c for c in all_room_colors}
        else:
            pimg = flat.quantize(colors=k, method=Image.Quantize.MEDIANCUT)
            pal_flat = pimg.getpalette()
            kpal = [tuple(c >> 3 for c in pal_flat[i * 3:i * 3 + 3]) for i in range(k)]
            remap = {c: min(kpal, key=lambda p: sum((a - b) ** 2 for a, b in zip(p, c)))
                     for c in all_room_colors}
        # mean per-pixel error (in 555 units) and re-packed palette count
        err = sum(sum((a - b) ** 2 for a, b in zip(c, remap[c])) ** 0.5
                  for c in all_room_colors) / len(all_room_colors)
        remapped_sets = []
        for s in distinct_8x8.values():
            cs = {remap[to555(px[:3])] for px in s.getdata() if px[3] == 255}
            if 0 < len(cs) <= USABLE:
                remapped_sets.append(cs)
        pk, _ = pack_palettes(remapped_sets)
        print(f"  {k:>5} {err:>11.2f} {len(pk):>9}")


if __name__ == "__main__":
    main()
