"""One-off: render the Pokémon Center *exterior* from Emerald and Uranium side
by side for a visual art comparison. Throwaway dev utility (not pipeline output).

Emerald: composite the OldaleTown map from pokeemerald-expansion tileset assets
(tiles.png + JASC palettes + metatiles.bin + map.bin) and crop the PC building,
located via the PokeCenter-door metatile 0x061.

Uranium: the PC exterior is pre-drawn in the RMXP town atlas PU-Nowtoch.png, so we
just crop it directly.

Usage (iterative):
  python scripts/render_pc_exterior_compare.py emerald-full
  python scripts/render_pc_exterior_compare.py emerald-crop COL ROW WCOLS HROWS
  python scripts/render_pc_exterior_compare.py uranium-crop X Y W H
  python scripts/render_pc_exterior_compare.py compose
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

POKE = Path("/home/b/repos/pokeemerald-expansion")
URANIUM_ATLAS = Path(
    "/home/b/repos/uranium-src/_unpacked/Graphics/Tilesets/PU-Nowtoch.png"
)
OUT_DIR = Path("/home/b/repos/rpg2gba/output")
EMERALD_CROP = OUT_DIR / "_emerald_pc.png"
URANIUM_CROP = OUT_DIR / "_uranium_pc.png"
FINAL = OUT_DIR / "pc_exterior_compare.png"

NUM_TILES_IN_PRIMARY = 512
NUM_PALS_IN_PRIMARY = 6
NUM_METATILES_IN_PRIMARY = 512
POKECENTER_DOOR = 0x061  # METATILE_General_Door_PokeCenter

OLDALE_PRIMARY = POKE / "data/tilesets/primary/general"
OLDALE_SECONDARY = POKE / "data/tilesets/secondary/petalburg"
OLDALE_MAPBIN = POKE / "data/layouts/OldaleTown/map.bin"
OLDALE_W, OLDALE_H = 20, 20


def load_pal(path: Path) -> list[tuple[int, int, int]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    n = int(lines[2])
    return tuple(
        tuple(int(c) for c in lines[3 + i].split()[:3]) for i in range(n)
    )


class Tileset:
    def __init__(self, dirpath: Path):
        self.dir = Path(dirpath)
        img = Image.open(self.dir / "tiles.png")
        if img.mode != "P":
            img = img.convert("P")
        self.img = img
        self.px = img.load()
        self.cols = img.width // 8
        self.ntiles = (img.width // 8) * (img.height // 8)
        self.metatiles = (self.dir / "metatiles.bin").read_bytes()
        self._pals: dict[int, tuple] = {}

    def pal(self, slot: int):
        if slot not in self._pals:
            self._pals[slot] = load_pal(self.dir / "palettes" / f"{slot:02d}.pal")
        return self._pals[slot]

    def index_at(self, tid: int, x: int, y: int) -> int:
        col = tid % self.cols
        row = tid // self.cols
        return self.px[col * 8 + x, row * 8 + y]


def draw_tile(out, primary, secondary, tid, pal_slot, ox, oy, flipx, flipy, is_top):
    if tid < NUM_TILES_IN_PRIMARY:
        src, local = primary, tid
    else:
        src, local = secondary, tid - NUM_TILES_IN_PRIMARY
    if local >= src.ntiles:
        return
    pal = primary.pal(pal_slot) if pal_slot < NUM_PALS_IN_PRIMARY else secondary.pal(pal_slot)
    put = out.putpixel
    for y in range(8):
        sy = 7 - y if flipy else y
        for x in range(8):
            sx = 7 - x if flipx else x
            idx = src.index_at(local, sx, sy)
            if is_top and idx == 0:
                continue
            r, g, b = pal[idx]
            put((ox + x, oy + y), (r, g, b, 255))


def render_metatile(primary, secondary, mid: int) -> Image.Image:
    if mid < NUM_METATILES_IN_PRIMARY:
        ts, local = primary, mid
    else:
        ts, local = secondary, mid - NUM_METATILES_IN_PRIMARY
    out = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    base = local * 16
    entries = struct.unpack_from("<8H", ts.metatiles, base)
    quad = [(0, 0), (8, 0), (0, 8), (8, 8)]
    for layer in range(2):
        for q in range(4):
            v = entries[layer * 4 + q]
            draw_tile(
                out, primary, secondary,
                v & 0x3FF, (v >> 12) & 0xF,
                quad[q][0], quad[q][1],
                bool(v & 0x400), bool(v & 0x800),
                is_top=(layer == 1),
            )
    return out


def render_oldale():
    primary = Tileset(OLDALE_PRIMARY)
    secondary = Tileset(OLDALE_SECONDARY)
    data = OLDALE_MAPBIN.read_bytes()
    n = OLDALE_W * OLDALE_H
    blocks = struct.unpack(f"<{n}H", data[: n * 2])
    img = Image.new("RGBA", (OLDALE_W * 16, OLDALE_H * 16), (0, 0, 0, 0))
    cache: dict[int, Image.Image] = {}
    for i, b in enumerate(blocks):
        mid = b & 0x3FF
        if mid not in cache:
            cache[mid] = render_metatile(primary, secondary, mid)
        img.paste(cache[mid], ((i % OLDALE_W) * 16, (i // OLDALE_W) * 16))
    doors = [
        (i % OLDALE_W, i // OLDALE_W)
        for i, b in enumerate(blocks)
        if (b & 0x3FF) == POKECENTER_DOOR
    ]
    return img, doors


def upscale(img: Image.Image, factor: int) -> Image.Image:
    return img.resize((img.width * factor, img.height * factor), Image.NEAREST)


def autotrim(img: Image.Image) -> Image.Image:
    bbox = img.getbbox()
    return img.crop(bbox) if bbox else img


def compose(scale: int = 4):
    em = Image.open(EMERALD_CROP).convert("RGBA")
    ur = Image.open(URANIUM_CROP).convert("RGBA")
    # equal pixel scale: same integer factor for both, so one source pixel maps to
    # the same on-screen size in each (reveals the real native-resolution gap).
    em = upscale(em, scale)
    ur = upscale(ur, scale)

    pad, gutter, label_h = 30, 40, 46
    panel_h = max(em.height, ur.height)
    W = pad * 2 + em.width + gutter + ur.width
    H = pad + label_h + panel_h + pad
    canvas = Image.new("RGBA", (W, H), (245, 245, 245, 255))
    d = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26
        )
    except OSError:
        font = ImageFont.load_default()

    ex = pad
    ux = pad + em.width + gutter
    canvas.paste(em, (ex, pad + label_h + (panel_h - em.height) // 2), em)
    canvas.paste(ur, (ux, pad + label_h + (panel_h - ur.height) // 2), ur)
    d.text((ex, pad + 6), "Pokémon Emerald", fill=(20, 20, 20, 255), font=font)
    d.text((ux, pad + 6), "Pokémon Uranium", fill=(20, 20, 20, 255), font=font)
    canvas.convert("RGB").save(FINAL)
    print("wrote", FINAL, canvas.size)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "emerald-full"
    if cmd == "emerald-full":
        img, doors = render_oldale()
        p = OUT_DIR / "_oldale_full.png"
        upscale(img, 3).save(p)
        print("doors (col,row):", doors)
        print("wrote", p, img.size)
    elif cmd == "emerald-crop":
        col, row, wc, hc = (int(a) for a in sys.argv[2:6])
        img, _ = render_oldale()
        crop = img.crop((col * 16, row * 16, (col + wc) * 16, (row + hc) * 16))
        crop = autotrim(crop)
        crop.save(EMERALD_CROP)
        upscale(crop, 4).save(OUT_DIR / "_emerald_pc_preview.png")
        print("wrote", EMERALD_CROP, crop.size)
    elif cmd == "uranium-crop":
        x, y, w, h = (int(a) for a in sys.argv[2:6])
        atlas = Image.open(URANIUM_ATLAS).convert("RGBA")
        crop = autotrim(atlas.crop((x, y, x + w, y + h)))
        crop.save(URANIUM_CROP)
        upscale(crop, 4).save(OUT_DIR / "_uranium_pc_preview.png")
        print("wrote", URANIUM_CROP, crop.size)
    elif cmd == "uranium-region":
        # dump a labeled wide region of the atlas to locate the PC
        x, y, w, h = (int(a) for a in sys.argv[2:6])
        atlas = Image.open(URANIUM_ATLAS).convert("RGBA")
        crop = atlas.crop((x, y, x + w, y + h))
        crop.save(OUT_DIR / "_uranium_region.png")
        print("wrote region", crop.size, "from", (x, y))
    elif cmd == "compose":
        scale = int(sys.argv[2]) if len(sys.argv) > 2 else 4
        compose(scale)
    else:
        print("unknown command", cmd)


if __name__ == "__main__":
    main()
