"""Step-4 validation (§9): push the FULL Moki Town (Map032, tileset 22) through the
joint per-8x8 quantizer with ONE fixed 13-palette set, and render the result so the
whole-map look can be eyeballed before the GBA binary emitter is wired up.

Pipeline: render every used tile_id (steps 1-3) -> split to 8x8 quadrants -> dedup
-> build_quantized_tileset(max_palettes=13) -> reassemble quantized 16x16 tiles ->
recomposite the 3 RMXP layers. Writes a true-vs-quantized side-by-side, the quantized
town alone, and the resolved sub-palette swatch to output/.

Usage: python scripts/quantize_moki_preview.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from rpg2gba.tileset_converter.graphics.quantize import build_quantized_tileset
from rpg2gba.tileset_converter.graphics.raster import NATIVE_TILE_PX, TileRasterizer
from rpg2gba.tileset_converter.graphics.sources import load_tileset_sources

MAP_ID, TILESET_ID = 32, 22
MAX_PALETTES = 13
MAPS_DIR = Path("output/uranium-build/maps")
OUT = Path("output")
TS = NATIVE_TILE_PX          # 16
SUB = TS // 2                # 8 (GBA tile)
VOID = (40, 40, 60, 255)


def _quadrants(arr: np.ndarray) -> list[np.ndarray]:
    """16x16 RGBA -> 4 8x8 quadrants [TL, TR, BL, BR]."""
    return [arr[0:SUB, 0:SUB], arr[0:SUB, SUB:TS], arr[SUB:TS, 0:SUB], arr[SUB:TS, SUB:TS]]


def _assemble(quads: list[np.ndarray]) -> Image.Image:
    """4 8x8 RGBA quadrants -> a 16x16 PIL image."""
    out = np.zeros((TS, TS, 4), np.uint8)
    out[0:SUB, 0:SUB], out[0:SUB, SUB:TS] = quads[0], quads[1]
    out[SUB:TS, 0:SUB], out[SUB:TS, SUB:TS] = quads[2], quads[3]
    return Image.fromarray(out, "RGBA")


def _composite(doc, tile_imgs: dict[int, Image.Image]) -> Image.Image:
    t = doc["tiles"]
    xs, ys, zs = t["xsize"], t["ysize"], t["zsize"]
    data = t["data"]
    canvas = Image.new("RGBA", (xs * TS, ys * TS), VOID)
    for y in range(ys):
        for x in range(xs):
            cell = Image.new("RGBA", (TS, TS), (0, 0, 0, 0))
            for z in range(zs):
                tid = data[z * (ys * xs) + y * xs + x]
                if tid:
                    cell.alpha_composite(tile_imgs[tid])
            canvas.alpha_composite(cell, (x * TS, y * TS))
    return canvas


def _swatch(palettes: list[np.ndarray]) -> Image.Image:
    cell = 18
    img = Image.new("RGB", (16 * cell, len(palettes) * cell), (20, 20, 20))
    px = img.load()
    for row, pal in enumerate(palettes):
        # slot 0 = transparent (shown as checker), 1.. = colours
        for col in range(16):
            if col == 0:
                color = (90, 90, 90)
            elif col - 1 < len(pal):
                color = tuple(int(v) for v in pal[col - 1])
            else:
                color = (20, 20, 20)
            for dy in range(cell - 1):
                for dx in range(cell - 1):
                    px[col * cell + dx, row * cell + dy] = color
    return img


def main() -> None:
    OUT.mkdir(exist_ok=True)
    doc = json.loads((MAPS_DIR / f"Map{MAP_ID:03d}.json").read_text(encoding="utf-8"))
    used = sorted({tid for tid in doc["tiles"]["data"] if tid})

    raster = TileRasterizer(load_tileset_sources(TILESET_ID))
    truecolor: dict[int, Image.Image] = {}
    tile_quads: dict[int, list[int]] = {}     # tile_id -> 4 unique-tile indices
    unique: list[np.ndarray] = []
    index: dict[bytes, int] = {}
    for tid in used:
        img = raster.render(tid)
        truecolor[tid] = img
        arr = np.asarray(img.convert("RGBA"))
        idxs = []
        for q in _quadrants(arr):
            key = q.tobytes()
            if key not in index:
                index[key] = len(unique)
                unique.append(q.copy())
            idxs.append(index[key])
        tile_quads[tid] = idxs

    # On-screen frequency of each unique 8x8 (every map cell-layer contributes its
    # 4 quadrants), so the joint quantizer fits common tiles (grass/path) best.
    weights = [0] * len(unique)
    for tid in doc["tiles"]["data"]:
        if tid:
            for qi in tile_quads[tid]:
                weights[qi] += 1

    result = build_quantized_tileset(unique, max_palettes=MAX_PALETTES, weights=weights)
    s = result.stats
    print(
        f"Map{MAP_ID:03d} (ts{TILESET_ID}): {len(used)} tile_ids, "
        f"{s['n_tiles']} unique 8x8 -> {s['n_palettes']} palettes "
        f"(<= {MAX_PALETTES}), max {s['max_colors']} colours/pal, "
        f"colour shift mean {s['mean_shift_5bit']:.2f} / p95 {s['p95_shift_5bit']:.1f} / "
        f"max {s['max_shift_5bit']:.1f} (of 31)"
    )

    quant_imgs = {
        tid: _assemble([result.quantized[i] for i in tile_quads[tid]]) for tid in used
    }

    true_town = _composite(doc, truecolor)
    quant_town = _composite(doc, quant_imgs)

    # Honest perceptual metric: mean 5-bit shift over every on-screen pixel (so
    # common tiles dominate, as they do visually) — includes the alpha-edge change.
    ta = np.asarray(true_town.convert("RGB")).astype(np.int16) >> 3
    qa = np.asarray(quant_town.convert("RGB")).astype(np.int16) >> 3
    print(f"on-screen mean 5-bit shift (per visible pixel): {np.abs(ta - qa).mean():.2f} (of 31)")

    pair = Image.new("RGBA", (true_town.width, true_town.height * 2 + 8), VOID)
    pair.alpha_composite(true_town, (0, 0))
    pair.alpha_composite(quant_town, (0, true_town.height + 8))
    z = 2
    pair.resize((pair.width * z, pair.height * z), Image.NEAREST).convert("RGB").save(
        OUT / "quantize_moki_compare.png"
    )
    quant_town.resize(
        (quant_town.width * z, quant_town.height * z), Image.NEAREST
    ).convert("RGB").save(OUT / "quantize_moki_quantized.png")
    _swatch(result.palettes).resize(
        (16 * 18 * 2, len(result.palettes) * 18 * 2), Image.NEAREST
    ).save(OUT / "quantize_moki_palettes.png")
    print(
        "wrote output/quantize_moki_compare.png (top=true colour, bottom=GBA 4bpp), "
        "quantize_moki_quantized.png, quantize_moki_palettes.png"
    )


if __name__ == "__main__":
    main()
