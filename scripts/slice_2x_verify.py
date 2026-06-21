"""Throwaway: EXACT 2x2-uniformity per tileset (pure-Python pixel walk, no numpy)
+ render a busy tile ÷2-vs-native so we can SEE if downscaling loses detail.
Settles whether PU-Route01-02-Moki-Kevlar is a 2x upscale or native 32x32 art."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

SRC = Path("/home/b/repos/uranium-src/_unpacked/Graphics/Tilesets")
OUT = Path("output")
OUT.mkdir(exist_ok=True)


def uniformity(img: Image.Image) -> tuple[float, float]:
    """Return (all-blocks, opaque-only-blocks) fraction of uniform 2x2 blocks."""
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()
    total = opaque = uni_all = uni_op = 0
    for by in range(0, h - 1, 2):
        for bx in range(0, w - 1, 2):
            a = px[bx, by]
            b = px[bx + 1, by]
            c = px[bx, by + 1]
            d = px[bx + 1, by + 1]
            total += 1
            same = a == b == c == d
            if same:
                uni_all += 1
            fully_opaque = a[3] == b[3] == c[3] == d[3] == 255
            if fully_opaque:
                opaque += 1
                if same:
                    uni_op += 1
    return uni_all / total, (uni_op / opaque if opaque else float("nan"))


def render_compare(img: Image.Image, box: tuple[int, int, int, int], out: Path, label: str):
    """Crop a tile region; show native (no resize) vs ÷2-then-×2 side by side at 8x."""
    x, y, w, h = box
    region = img.convert("RGBA").crop((x, y, x + w, y + h))
    half = region.resize((w // 2, h // 2), Image.NEAREST)
    rt = half.resize((w, h), Image.NEAREST)  # ÷2 then ×2 back -> what detail survives
    scale = 8
    pad = 20
    a = region.resize((w * scale, h * scale), Image.NEAREST)
    b = rt.resize((w * scale, h * scale), Image.NEAREST)
    canvas = Image.new("RGB", (a.width + b.width + pad * 3, a.height + pad * 2), (240, 240, 240))
    canvas.paste(a.convert("RGB"), (pad, pad))
    canvas.paste(b.convert("RGB"), (a.width + pad * 2, pad))
    canvas.save(out)
    print(f"  wrote {out} ({label}: left=native 32px detail, right=÷2 then ×2)")


for tid, fname, busy_box in (
    ("19", "Indoor(1).png", (0, 0, 64, 64)),
    ("22", "PU-Route01-02-Moki-Kevlar.png", (0, 0, 64, 64)),
):
    img = Image.open(SRC / fname)
    ua, uo = uniformity(img)
    print(f"tileset {tid} {fname}: 2x2-uniform all={ua*100:.2f}%  opaque-only={uo*100:.2f}%")
    render_compare(img, busy_box, OUT / f"ts{tid}_downscale_detail.png", f"ts{tid}")
