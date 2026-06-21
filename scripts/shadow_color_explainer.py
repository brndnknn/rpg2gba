"""Shadow rendering: black stipple vs DARKENED-COLOUR stipple/solid.

A RMXP shadow is semi-transparent black over the ground, so the visible colour is
blend(ground, black, alpha) = a DARKER version of the ground. Reproducing that
means compositing the shadow into the ground in true colour -> the 'darkened
colour' the user wants is exactly the RAW composite. This shows, per shadow tile
over a real (textured) grass ground tile:

  RAW (RMXP)            = solid darkened colour (the faithful target)
  stipple black         = one reusable tile, harsh black dither (cheap)
  stipple dark colour   = checker of darkened-ground vs ground (soft, hue-matched)
  solid dark colour     = every shadow px darkened (== RAW)
  reusable dark-grey    = one fixed dark-grey stipple, background-agnostic (cheap-ish)
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from rpg2gba.tileset_converter.graphics.raster import TileRasterizer
from rpg2gba.tileset_converter.graphics.sources import load_tileset_sources

OUT = Path("output")
MAP_ID, TILESET_ID = 32, 22
GREY = (40, 40, 40)  # fixed reusable shadow colour (not black, not hue-matched)


def blend(bg, fg, a):
    return tuple(round(bg[i] * (255 - a) / 255 + fg[i] * a / 255) for i in range(3))


def render(tile: Image.Image, ground: Image.Image, rule: str) -> Image.Image:
    """Composite a shadow/edge tile over a ground tile under `rule`."""
    tile = tile.convert("RGBA")
    out = ground.convert("RGB").copy()
    tp, gp, op = tile.load(), ground.convert("RGB").load(), out.load()
    for y in range(16):
        for x in range(16):
            r, g, b, a = tp[x, y]
            if a == 0:
                continue
            if a == 255:
                op[x, y] = (r, g, b)            # the object itself
                continue
            dark = blend(gp[x, y], (r, g, b), a)  # RMXP's darkened-ground colour
            chk = (x + y) % 2 == 0
            if rule == "raw":
                op[x, y] = dark
            elif rule == "stipple_black":
                op[x, y] = (0, 0, 0) if chk else gp[x, y]
            elif rule == "stipple_dark":
                op[x, y] = dark if chk else gp[x, y]
            elif rule == "solid_dark":
                op[x, y] = dark
            elif rule == "stipple_grey":
                op[x, y] = GREY if chk else gp[x, y]
    return out


def _font(sz):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", sz)
    except OSError:
        return ImageFont.load_default()


def main() -> None:
    doc = json.loads(Path(f"output/uranium-build/maps/Map{MAP_ID:03d}.json").read_text())
    t = doc["tiles"]
    xs, ys = t["xsize"], t["ysize"]
    data = t["data"]
    r = TileRasterizer(load_tileset_sources(TILESET_ID))

    # dominant bottom-layer tile = the ground (grass) — used as a textured backdrop
    layer0 = data[: ys * xs]
    ground_id = Counter(v for v in layer0 if v != 0).most_common(1)[0][0]
    ground = r.render(ground_id).convert("RGB")

    rules = [("RAW (RMXP)", "raw"), ("stipple black", "stipple_black"),
             ("stipple dark colour", "stipple_dark"), ("solid dark colour (=RAW)", "solid_dark"),
             ("reusable dark-grey", "stipple_grey")]
    picks = [("shadow tile 1018", 1018), ("tree-base shadow 420", 420)]

    zoom = 16
    pw = 16 * zoom
    tf, lf, cf = _font(30), _font(21), _font(18)
    rows = []
    for label, tid in picks:
        base = r.render(tid)
        rows.append((label, [(cap, render(base, ground, rl).resize((pw, pw), Image.NEAREST))
                             for cap, rl in rules]))

    pad, gap, vgap, title_h, lab_w, cap_h = 24, 18, 30, 50, 200, 30
    W = pad * 2 + lab_w + len(rules) * pw + (len(rules) - 1) * gap
    H = pad + title_h + len(rows) * (cap_h + pw + vgap) + pad
    canvas = Image.new("RGB", (W, H), (250, 250, 250))
    dr = ImageDraw.Draw(canvas)
    dr.text((pad, pad), "Shadows: black stipple vs darkened-colour (over the real grass tile)",
            fill=(15, 15, 15), font=tf)
    y = pad + title_h
    for ri, (label, panels) in enumerate(rows):
        x = pad + lab_w
        for cap, im in panels:
            if ri == 0:
                dr.text((x + (pw - dr.textlength(cap, font=cf)) / 2, y), cap, fill=(40, 40, 40), font=cf)
            canvas.paste(im, (x, y + cap_h))
            x += pw + gap
        dr.text((pad, y + cap_h + pw // 2), label, fill=(20, 20, 20), font=lf)
        y += cap_h + pw + vgap
    out = OUT / "explainer_shadow_colour.png"
    canvas.save(out)
    print("wrote", out, canvas.size, "| ground tile:", ground_id)


if __name__ == "__main__":
    main()
