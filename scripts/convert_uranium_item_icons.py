"""Convert Uranium item icon art to GBA-format pokeemerald-expansion assets.

Source -> target mapping:

    Uranium Graphics/Icons/item500.png (48x48 RGBA)  -> Acai Berry
    Uranium Graphics/Icons/item501.png (48x48 RGBA)  -> Bacu Berry
    Uranium Graphics/Icons/item502.png (48x48 RGBA)  -> Cupu Berry
    Uranium Graphics/Icons/item503.png (48x48 RGBA)  -> Guara Berry
    Uranium Graphics/Icons/item596.png (48x48 8-bit colormap) -> Sprinklotad (key item)

For each item this produces:
  - a 24x24, 4bpp indexed "bag icon" PNG + JASC-PAL 16-colour palette, under
    engine/graphics/items/icons/ and engine/graphics/items/icon_palettes/,
    matching the format of the vanilla oran_berry.png/.pal pair exactly:
    16-colour indexed palette, index 0 reserved as the transparent colour
    (tRNS index 0), unused palette slots zero-padded.
  - for the four berries only (not the key item), a 48x48 4bpp indexed
    "berry pouch" pic under engine/graphics/berries/, matching the format of
    the vanilla oran.png (no scaling needed -- source is already 48x48).

Resampling: bag icons are downscaled 48x48 -> 24x24 with PIL's NEAREST
filter, chosen over BOX and LANCZOS after a by-eye comparison on the busiest
source (Guara Berry, item503.png): LANCZOS produced a visible ringing halo
(a dark teal fringe bleeding around the berry's edge) from its negative
lobes, which is out of place on already-low-res pixel art; BOX and NEAREST
both avoided that artifact and looked nearly identical, so NEAREST was kept
since it preserves crisp, un-blurred pixel boundaries consistent with the
existing vanilla 4bpp icon art (oran_berry.png etc. are hard-edged pixel
art, not anti-aliased). Quantization to <=16 colours (including the
reserved transparent index 0) is done with PIL's MEDIANCUT palette
quantizer over the
alpha-composited (transparent pixels flattened to a placeholder background
colour, then remapped so index 0 is transparent) image.

Idempotent / re-runnable: this script always re-derives its outputs from
the read-only Uranium source tree; it never reads or mutates its own
previous output.

Usage:
    .venv/bin/python scripts/convert_uranium_item_icons.py
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
URANIUM_ICONS = Path("/home/b/repos/uranium-src/_unpacked/Graphics/Icons")

ICONS_OUT = REPO_ROOT / "engine" / "graphics" / "items" / "icons"
PALETTES_OUT = REPO_ROOT / "engine" / "graphics" / "items" / "icon_palettes"
BERRIES_OUT = REPO_ROOT / "engine" / "graphics" / "berries"

MAX_COLOURS = 16
TRANSPARENT_PLACEHOLDER = (180, 180, 180)  # matches oran_berry.png's index-0 colour


@dataclass(frozen=True)
class ItemSpec:
    source_name: str  # e.g. "item500.png"
    icon_stem: str  # bag icon / palette basename, no extension
    berry_stem: str | None  # berry pouch pic basename, or None if not a berry


ITEMS: list[ItemSpec] = [
    ItemSpec("item500.png", "acai_berry", "acai"),
    ItemSpec("item501.png", "bacu_berry", "bacu"),
    ItemSpec("item502.png", "cupu_berry", "cupu"),
    ItemSpec("item503.png", "guara_berry", "guara"),
    ItemSpec("item596.png", "sprinklotad", None),
]


def load_rgba(path: Path) -> Image.Image:
    im = Image.open(path)
    return im.convert("RGBA")


def quantize_to_indexed(rgba: Image.Image) -> Image.Image:
    """Quantize an RGBA image to a <=16-colour P-mode image with index 0
    reserved as fully transparent, matching the oran_berry.png convention.
    """
    w, h = rgba.size

    # Flatten transparent pixels onto the placeholder background colour so
    # quantization doesn't waste palette slots on invisible colour data,
    # then quantize the remaining <=15 opaque colours.
    flat = Image.new("RGB", (w, h), TRANSPARENT_PLACEHOLDER)
    flat.paste(rgba, (0, 0), mask=rgba.split()[3])

    alpha = rgba.split()[3]
    is_transparent = [a < 128 for a in alpha.getdata()]

    quantized = flat.quantize(colors=MAX_COLOURS - 1, method=Image.MEDIANCUT)
    q_palette = quantized.getpalette()  # flat RGB list

    # Build final palette: index 0 = transparent placeholder colour,
    # indices 1..N = quantized opaque colours, remainder zero-padded to 16.
    n_used = len(q_palette) // 3
    final_palette: list[int] = list(TRANSPARENT_PLACEHOLDER)
    for i in range(n_used):
        final_palette.extend(q_palette[i * 3 : i * 3 + 3])
    while len(final_palette) < MAX_COLOURS * 3:
        final_palette.extend((0, 0, 0))
    final_palette = final_palette[: MAX_COLOURS * 3]

    q_indices = list(quantized.getdata())
    out = Image.new("P", (w, h))
    out.putpalette(final_palette)
    out_data = [
        0 if is_transparent[i] else q_indices[i] + 1 for i in range(w * h)
    ]
    out.putdata(out_data)
    out.info["transparency"] = 0
    return out


def count_colours(rgba: Image.Image) -> int:
    colours = set()
    w, h = rgba.size
    for px in rgba.getdata():
        r, g, b, a = px
        if a < 128:
            colours.add(("transparent",))
        else:
            colours.add((r, g, b))
    return len(colours)


def write_jasc_pal(image: Image.Image, out_path: Path) -> None:
    palette = image.getpalette()
    assert palette is not None
    lines = ["JASC-PAL", "0100", str(MAX_COLOURS)]
    for i in range(MAX_COLOURS):
        r, g, b = palette[i * 3], palette[i * 3 + 1], palette[i * 3 + 2]
        lines.append(f"{r} {g} {b}")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def convert_item(spec: ItemSpec) -> None:
    src_path = URANIUM_ICONS / spec.source_name
    rgba = load_rgba(src_path)
    assert rgba.size == (48, 48), f"{src_path} is not 48x48"

    before_colours = count_colours(rgba)

    # --- Bag icon: downscale 48x48 -> 24x24 with LANCZOS, then quantize ---
    icon_rgba = rgba.resize((24, 24), Image.NEAREST)
    icon_indexed = quantize_to_indexed(icon_rgba)

    icon_png_path = ICONS_OUT / f"{spec.icon_stem}.png"
    icon_indexed.save(icon_png_path)
    logger.info(
        "wrote %s (%dx%d, %d colours incl. transparent, source had %d)",
        icon_png_path,
        *icon_indexed.size,
        len(set(icon_indexed.getdata())),
        before_colours,
    )

    pal_path = PALETTES_OUT / f"{spec.icon_stem}.pal"
    write_jasc_pal(icon_indexed, pal_path)
    logger.info("wrote %s", pal_path)

    # --- Berry pouch pic: no scaling, just quantize at native 48x48 ---
    if spec.berry_stem is not None:
        berry_indexed = quantize_to_indexed(rgba)
        berry_png_path = BERRIES_OUT / f"{spec.berry_stem}.png"
        berry_indexed.save(berry_png_path)
        logger.info(
            "wrote %s (%dx%d, %d colours incl. transparent, source had %d)",
            berry_png_path,
            *berry_indexed.size,
            len(set(berry_indexed.getdata())),
            before_colours,
        )


def main() -> None:
    ICONS_OUT.mkdir(parents=True, exist_ok=True)
    PALETTES_OUT.mkdir(parents=True, exist_ok=True)
    BERRIES_OUT.mkdir(parents=True, exist_ok=True)

    for spec in ITEMS:
        convert_item(spec)


if __name__ == "__main__":
    main()
