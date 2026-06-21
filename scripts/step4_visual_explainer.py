"""Visual explainer for the step-4 (quantization) decisions. Renders the real
options side-by-side, always next to the RAW (true-colour) art, so the choices
can be made by eye instead of from colour counts.

Sources = the pre-quantization reconstructions (scripts/render_slice_tiles.py).
Outputs labelled comparison PNGs to output/.

Decisions visualised:
  A. colour DEPTH      — true-colour vs GBA 15-bit (the mandatory, ~free step).
  B. the FIDELITY DIAL — global colour reduction at several levels.
  C. DITHERING         — banding vs noise at an aggressive level.
  D. the REAL CONSTRAINT — GBA per-8x8-tile 16-colour sub-palettes, N palettes
       (a rough joint quantizer = what the ROM actually looks like).
  E. EASY vs HARD      — interior (room) vs outdoor (town) under the same constraint.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path("output")
ROOM = OUT / "slice_map048_reconstruct.png"      # 320x240
TOWN = OUT / "slice_map032_reconstruct.png"      # 1152x1024
DITHER_FS = Image.Dither.FLOYDSTEINBERG
DITHER_NONE = Image.Dither.NONE
MEDIAN = Image.Quantize.MEDIANCUT


# --- quantization primitives -------------------------------------------------

def to_555(img: Image.Image) -> Image.Image:
    """Snap RGB to GBA 15-bit (top 5 bits per channel)."""
    return Image.eval(img.convert("RGB"), lambda v: (v >> 3) << 3)


def global_quant(img: Image.Image, k: int, dither=DITHER_NONE) -> Image.Image:
    """Global K-colour median-cut (unconstrained palette), 555-snapped."""
    q = img.convert("RGB").quantize(colors=k, method=MEDIAN, dither=dither)
    return to_555(q.convert("RGB"))


def gba_faithful(img: Image.Image, n_pal: int = 13, cper: int = 16,
                 dither=DITHER_NONE) -> Image.Image:
    """Rough joint quantizer that honours the real GBA constraint: every 8x8 tile
    draws from ONE of `n_pal` sub-palettes of `cper` colours. Tiles are clustered
    by mean colour into n_pal groups; each group is median-cut to cper colours;
    each tile is remapped to its group's palette. (Preview quality, not optimal.)"""
    img = to_555(img)
    w, h = img.size
    w8, h8 = (w // 8) * 8, (h // 8) * 8
    img = img.crop((0, 0, w8, h8))

    tiles, means = [], []
    for ty in range(0, h8, 8):
        for tx in range(0, w8, 8):
            t = img.crop((tx, ty, tx + 8, ty + 8))
            tiles.append((tx, ty, t))
            means.append(t.resize((1, 1), Image.BOX).getpixel((0, 0)))

    mim = Image.new("RGB", (len(means), 1))
    mim.putdata(means)
    cluster_of = list(mim.quantize(colors=n_pal, method=MEDIAN).getdata())

    px_by_cluster: dict[int, list] = defaultdict(list)
    for (tx, ty, t), c in zip(tiles, cluster_of):
        px_by_cluster[c].extend(t.getdata())
    pal_imgs = {}
    for c, px in px_by_cluster.items():
        cim = Image.new("RGB", (len(px), 1))
        cim.putdata(px)
        pal_imgs[c] = cim.quantize(colors=cper, method=MEDIAN)

    out = Image.new("RGB", (w8, h8))
    for (tx, ty, t), c in zip(tiles, cluster_of):
        out.paste(t.quantize(palette=pal_imgs[c], dither=dither).convert("RGB"), (tx, ty))
    return out


# --- labelled composition ----------------------------------------------------

def _font(sz: int):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",):
        try:
            return ImageFont.truetype(p, sz)
        except OSError:
            pass
    return ImageFont.load_default()


def panel_row(title: str, panels: list[tuple[str, Image.Image]], zoom: int,
              out: Path) -> None:
    """One titled row of zoomed, captioned panels."""
    tf, cf = _font(30), _font(20)
    imgs = [(cap, p.resize((p.width * zoom, p.height * zoom), Image.NEAREST))
            for cap, p in panels]
    pad, gap, title_h, cap_h = 24, 22, 46, 30
    ph = max(im.height for _, im in imgs)
    meas = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    widths = [max(im.width, meas.textlength(cap, font=cf) + 8) for cap, im in imgs]
    W = pad * 2 + sum(widths) + gap * (len(imgs) - 1)
    H = pad + title_h + cap_h + ph + pad
    canvas = Image.new("RGB", (int(W), int(H)), (250, 250, 250))
    dr = ImageDraw.Draw(canvas)
    dr.text((pad, pad), title, fill=(15, 15, 15), font=tf)
    x = pad
    for (cap, im), cw in zip(imgs, widths):
        cx = x + (cw - im.width) / 2
        dr.text((x + (cw - meas.textlength(cap, font=cf)) / 2, pad + title_h),
                cap, fill=(40, 40, 40), font=cf)
        canvas.paste(im, (int(cx), pad + title_h + cap_h))
        x += cw + gap
    canvas.save(out)
    print("wrote", out, canvas.size)


def main() -> None:
    town = Image.open(TOWN).convert("RGB")
    room = Image.open(ROOM).convert("RGB")
    # content-rich town crop (houses + grass + path + water), 256x192 -> 32x24 cells
    crop = town.crop((300, 350, 556, 542))
    raw = ("RAW (true colour)", crop)

    # A + B: depth + fidelity dial
    panel_row(
        "B.  Fidelity dial — global colour reduction (Moki Town)",
        [raw,
         ("15-bit (free)", to_555(crop)),
         ("128 colours", global_quant(crop, 128)),
         ("64 colours", global_quant(crop, 64)),
         ("32 colours", global_quant(crop, 32))],
        zoom=2, out=OUT / "explainer_B_fidelity_dial.png")

    # C: dithering at an aggressive level
    panel_row(
        "C.  Dithering at 32 colours (banding vs noise)",
        [raw,
         ("32 colours, no dither", global_quant(crop, 32, DITHER_NONE)),
         ("32 colours, dithered", global_quant(crop, 32, DITHER_FS))],
        zoom=3, out=OUT / "explainer_C_dithering.png")

    # D: the real GBA per-tile palette constraint
    panel_row(
        "D.  What the ROM actually looks like — GBA per-8x8 sub-palettes (Moki Town)",
        [raw,
         ("13 palettes x16", gba_faithful(crop, 13, 16)),
         ("13 palettes x16, dithered", gba_faithful(crop, 13, 16, DITHER_FS)),
         ("6 palettes x16 (tight)", gba_faithful(crop, 6, 16))],
        zoom=2, out=OUT / "explainer_D_gba_constraint.png")

    # E: palette-budget sensitivity — interior tolerates a tight budget, outdoor
    # doesn't. Both at full 13x16 look like raw (decision D); the contrast only
    # appears when the budget is squeezed, so show a tight 4-palette budget.
    panel_row(
        "E.  How many palettes per tileset? At a TIGHT 4-palette budget:",
        [("Room RAW", room),
         ("Room 4 palettes (fine)", gba_faithful(room, 4, 16)),
         ("Town RAW", crop),
         ("Town 4 palettes (degrades)", gba_faithful(crop, 4, 16))],
        zoom=2, out=OUT / "explainer_E_palette_budget.png")


if __name__ == "__main__":
    main()
