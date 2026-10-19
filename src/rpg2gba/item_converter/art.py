"""Item icon and berry pic conversion (Uranium Graphics/Icons/itemNNN.png).

Bag icons are 24x24 4bpp with a 16-colour JASC palette, index 0 transparent,
matching the stock icon/palette pairs; berry pics are the 48x48 source quantized
in place, matching `graphics/berries/*.png`. Downscaling is NEAREST: LANCZOS
rang a dark halo around the busiest berry, and the stock icons are hard-edged
pixel art (decided by eye, 2026-08-18; `67fd0435`).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

MAX_COLOURS = 16
TRANSPARENT_PLACEHOLDER = (180, 180, 180)  # the stock oran_berry.png index-0 colour
SOURCE_SIZE = (48, 48)
ICON_SIZE = (24, 24)


def source_icon(uranium_src: Path, uranium_id: int) -> Path | None:
    """The item's icon in the Uranium tree, or None if the game ships none."""
    icons = Path(uranium_src) / "Graphics" / "Icons"
    want = f"item{uranium_id:03d}.png"
    for path in icons.iterdir():
        if path.name.lower() == want:
            return path
    return None


def quantize_to_indexed(rgba: Image.Image) -> Image.Image:
    """<=16-colour P-mode image with index 0 reserved as fully transparent."""
    w, h = rgba.size
    flat = Image.new("RGB", (w, h), TRANSPARENT_PLACEHOLDER)
    flat.paste(rgba, (0, 0), mask=rgba.split()[3])
    transparent = [a < 128 for a in rgba.split()[3].getdata()]
    quantized = flat.quantize(colors=MAX_COLOURS - 1, method=Image.MEDIANCUT)
    q_palette = quantized.getpalette()
    palette: list[int] = list(TRANSPARENT_PLACEHOLDER)
    for i in range(len(q_palette) // 3):
        palette.extend(q_palette[i * 3:i * 3 + 3])
    palette = (palette + [0] * (MAX_COLOURS * 3))[:MAX_COLOURS * 3]
    indices = list(quantized.getdata())
    out = Image.new("P", (w, h))
    out.putpalette(palette)
    out.putdata([0 if transparent[i] else indices[i] + 1 for i in range(w * h)])
    out.info["transparency"] = 0
    return out


def write_jasc_pal(image: Image.Image, path: Path) -> None:
    palette = image.getpalette()
    lines = ["JASC-PAL", "0100", str(MAX_COLOURS)]
    lines += [f"{palette[i * 3]} {palette[i * 3 + 1]} {palette[i * 3 + 2]}"
              for i in range(MAX_COLOURS)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load(path: Path) -> Image.Image:
    rgba = Image.open(path).convert("RGBA")
    if rgba.size != SOURCE_SIZE:
        raise ValueError(f"{path}: expected a {SOURCE_SIZE} item icon, got {rgba.size}")
    return rgba


def convert_icon(source: Path, png_out: Path, pal_out: Path) -> None:
    indexed = quantize_to_indexed(_load(source).resize(ICON_SIZE, Image.NEAREST))
    png_out.parent.mkdir(parents=True, exist_ok=True)
    indexed.save(png_out)
    write_jasc_pal(indexed, pal_out)


def convert_berry_pic(source: Path, png_out: Path) -> None:
    png_out.parent.mkdir(parents=True, exist_ok=True)
    quantize_to_indexed(_load(source)).save(png_out)
