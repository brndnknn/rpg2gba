"""One-off: compare the player-character overworld sprite (front-facing, standing)
from Emerald vs Uranium, side by side at equal pixel scale. Throwaway dev utility.

Emerald: brendan/walking.png is a 144x32 sheet of nine 16x32 frames; frame 0 is
standing facing down. The PNG stores palette index 0 as the (runtime) transparent
color, so we punch that out manually.

Uranium: HERO.png is a 256x256 RMXP charset = 4x4 grid of 64x64 frames; row 0 =
facing down. Already RGBA with real alpha, so just crop + trim.

Usage:
  python scripts/render_player_compare.py uranium-row   # dump down row to choose frame
  python scripts/render_player_compare.py build [URANIUM_COL] [SCALE]
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

POKE = Path("/home/b/repos/pokeemerald-expansion")
EMERALD_SHEET = POKE / "graphics/object_events/pics/people/brendan/walking.png"
URANIUM_SHEET = Path(
    "/home/b/repos/uranium-src/_unpacked/Graphics/Characters/HERO.png"
)
OUT_DIR = Path("/home/b/repos/rpg2gba/output")
FINAL = OUT_DIR / "player_compare.png"

EM_FRAME_W, EM_FRAME_H = 16, 32  # frame 0 = standing, facing down
UR_CELL = 64  # 256 / 4


def autotrim(img: Image.Image) -> Image.Image:
    bbox = img.getbbox()
    return img.crop(bbox) if bbox else img


def upscale(img: Image.Image, factor: int) -> Image.Image:
    return img.resize((img.width * factor, img.height * factor), Image.NEAREST)


def emerald_sprite() -> Image.Image:
    p = Image.open(EMERALD_SHEET)
    if p.mode != "P":
        p = p.convert("P")
    pal = p.getpalette()
    px = p.load()
    out = Image.new("RGBA", (EM_FRAME_W, EM_FRAME_H), (0, 0, 0, 0))
    for y in range(EM_FRAME_H):
        for x in range(EM_FRAME_W):
            i = px[x, y]
            if i == 0:  # index 0 = transparent for object-event sprites
                continue
            out.putpixel((x, y), (pal[i * 3], pal[i * 3 + 1], pal[i * 3 + 2], 255))
    return autotrim(out)


def uranium_frame(col: int, row: int = 0) -> Image.Image:
    atlas = Image.open(URANIUM_SHEET).convert("RGBA")
    box = (col * UR_CELL, row * UR_CELL, (col + 1) * UR_CELL, (row + 1) * UR_CELL)
    return autotrim(atlas.crop(box))


def build(ur_col: int = 0, scale: int = 6):
    em = upscale(emerald_sprite(), scale)
    ur = upscale(uranium_frame(ur_col), scale)

    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26
        )
    except OSError:
        font = ImageFont.load_default()

    pad, gutter, label_h = 30, 70, 46
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    em_label, ur_label = "Pokémon Emerald", "Pokémon Uranium"
    em_lw = measure.textlength(em_label, font=font)
    ur_lw = measure.textlength(ur_label, font=font)
    # each column is as wide as its widest element (sprite or label)
    col_em = max(em.width, em_lw)
    col_ur = max(ur.width, ur_lw)
    panel_h = max(em.height, ur.height)
    W = int(pad * 2 + col_em + gutter + col_ur)
    H = int(pad + label_h + panel_h + pad)
    canvas = Image.new("RGBA", (W, H), (245, 245, 245, 255))
    d = ImageDraw.Draw(canvas)

    ex0, ux0 = pad, pad + col_em + gutter
    base_y = pad + label_h
    # center label + sprite within each column; bottom-align sprites (feet on a line)
    canvas.alpha_composite(em, (int(ex0 + (col_em - em.width) / 2), base_y + (panel_h - em.height)))
    canvas.alpha_composite(ur, (int(ux0 + (col_ur - ur.width) / 2), base_y + (panel_h - ur.height)))
    d.text((ex0 + (col_em - em_lw) / 2, pad + 6), em_label, fill=(20, 20, 20, 255), font=font)
    d.text((ux0 + (col_ur - ur_lw) / 2, pad + 6), ur_label, fill=(20, 20, 20, 255), font=font)
    canvas.convert("RGB").save(FINAL)
    print("wrote", FINAL, canvas.size, "| em", em.size, "ur", ur.size)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "uranium-row":
        atlas = Image.open(URANIUM_SHEET).convert("RGBA")
        row = atlas.crop((0, 0, 4 * UR_CELL, UR_CELL))
        upscale(row, 4).save(OUT_DIR / "_uranium_player_row.png")
        print("wrote down-row preview")
    elif cmd == "build":
        ur_col = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        scale = int(sys.argv[3]) if len(sys.argv) > 3 else 6
        build(ur_col, scale)
    else:
        print("unknown command", cmd)


if __name__ == "__main__":
    main()
