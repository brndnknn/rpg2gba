"""Visual explainer for the binary-alpha rule. GBA 4bpp has no partial alpha:
every pixel is a palette colour (opaque) or index 0 (transparent). Uranium art
has two kinds of partial-alpha pixel, which want DIFFERENT rules:

  (1) thin AA EDGES on objects (a few px per tile) -> a threshold; low stakes.
  (2) semi-transparent FILL tiles = SHADOWS / overlays (most/all px partial) ->
      keep-opaque makes a black blob, drop deletes the shadow; STIPPLE (50%
      checker of opaque px) approximates the translucency, the usual GBA trick.

Shows representative tiles of each kind over a realistic grass background, at high
zoom, under: RAW | 50% (a>=128) | keep-opaque (a>=1) | drop (a>=200) | stipple.
Also prints how many distinct tiles are edge-type vs shadow-type.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from rpg2gba.tileset_converter.graphics.raster import TileRasterizer
from rpg2gba.tileset_converter.graphics.sources import load_tileset_sources

OUT = Path("output")
MAP_ID, TILESET_ID = 32, 22
GRASS = (112, 176, 96, 255)  # realistic stand-in for the layer a shadow/edge sits on


def apply_rule(img: Image.Image, rule: str) -> Image.Image:
    """rule in {raw,50,keep,drop,stipple}. Returns RGBA with binary (or stipple) alpha."""
    img = img.convert("RGBA")
    if rule == "raw":
        return img
    px = img.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = px[x, y]
            if a == 0 or a == 255:
                continue
            if rule == "50":
                keep = a >= 128
            elif rule == "keep":
                keep = a >= 1
            elif rule == "drop":
                keep = a >= 200
            elif rule == "stipple":
                keep = (x + y) % 2 == 0  # 50% checker dither of the translucent px
            px[x, y] = (r, g, b, 255) if keep else (0, 0, 0, 0)
    return img


def semi_count(img: Image.Image) -> int:
    return sum(1 for px in img.convert("RGBA").getdata() if 0 < px[3] < 255)


def _font(sz):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", sz)
    except OSError:
        return ImageFont.load_default()


def main() -> None:
    doc = json.loads(Path(f"output/uranium-build/maps/Map{MAP_ID:03d}.json").read_text())
    data = doc["tiles"]["data"]
    distinct = sorted({x for x in data if x != 0})
    r = TileRasterizer(load_tileset_sources(TILESET_ID))

    counts = {t: semi_count(r.render(t)) for t in distinct}
    edge = sorted((c, t) for t, c in counts.items() if 4 <= c <= 64)
    shadow = sorted((c, t) for t, c in counts.items() if c >= 180)
    print(f"distinct tiles: {len(distinct)} | edge-type (4-64 AA px): {len(edge)} | "
          f"shadow-type (>=180 AA px): {len(shadow)}")

    picks = [("edge", t) for _, t in edge[-2:]] + [("shadow", t) for _, t in shadow[-2:]]

    rules = [("RAW", "raw"), ("50% (a>=128)", "50"), ("keep-opaque", "keep"),
             ("drop (a>=200)", "drop"), ("stipple", "stipple")]
    zoom = 16
    pw = 16 * zoom
    tf, lf, cf = _font(30), _font(21), _font(19)
    bg = Image.new("RGBA", (16, 16), GRASS)

    rows = []
    for kind, tid in picks:
        base = r.render(tid).convert("RGBA")
        panels = [(cap, Image.alpha_composite(bg, apply_rule(base, rl)).convert("RGB")
                   .resize((pw, pw), Image.NEAREST)) for cap, rl in rules]
        rows.append((f"{kind}  tile {tid}\n{counts[tid]} AA px", panels))

    pad, gap, vgap, title_h, lab_w, cap_h = 24, 18, 30, 50, 170, 30
    W = pad * 2 + lab_w + len(rules) * pw + (len(rules) - 1) * gap
    rowh = cap_h + pw
    H = pad + title_h + len(rows) * (rowh + vgap) + pad
    canvas = Image.new("RGB", (W, H), (250, 250, 250))
    dr = ImageDraw.Draw(canvas)
    dr.text((pad, pad), "Binary-alpha rule — edge tiles vs shadow tiles, over grass",
            fill=(15, 15, 15), font=tf)
    y = pad + title_h
    for ri, (label, panels) in enumerate(rows):
        x = pad + lab_w
        for cap, im in panels:
            if ri == 0:
                dr.text((x + (pw - dr.textlength(cap, font=cf)) / 2, y), cap,
                        fill=(40, 40, 40), font=cf)
            canvas.paste(im, (x, y + cap_h))
            x += pw + gap
        dr.multiline_text((pad, y + cap_h + pw // 2 - 20), label, fill=(20, 20, 20), font=lf)
        y += rowh + vgap
    out = OUT / "explainer_alpha_rule.png"
    canvas.save(out)
    print("wrote", out, canvas.size, "| picks:", [t for _, t in picks])


if __name__ == "__main__":
    main()
