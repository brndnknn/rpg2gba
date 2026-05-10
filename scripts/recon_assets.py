#!/usr/bin/env python3
"""Phase 0.5 — Asset inventory.

Counts files by directory and type. Flags audio (not converted to GBA format)
and estimates sprite cleanup work.

Usage:
    RPG2GBA_URANIUM_SRC=/path/to/uranium python scripts/recon_assets.py
"""
import os
from collections import defaultdict
from pathlib import Path

URANIUM_SRC = Path(os.environ["RPG2GBA_URANIUM_SRC"])
OUT = Path("reference/asset_inventory.md")

DIRS = [
    ("Graphics/Battlers",    "Battle sprites (front/back)"),
    ("Graphics/Characters",  "Overworld / character sprites"),
    ("Graphics/Tilesets",    "Tileset graphics"),
    ("Graphics/Autotiles",   "Autotile graphics"),
    ("Graphics/Icons",       "Pokémon box icons"),
    ("Graphics/Pictures",    "UI / cutscene images"),
    ("Graphics/Animations",  "Battle animations"),
    ("Graphics/Windowskins", "UI window skins"),
    ("Audio/BGM",            "Background music"),
    ("Audio/SE",             "Sound effects"),
    ("Audio/ME",             "Music effects (fanfares, jingles)"),
    ("Audio/BGS",            "Background sounds (ambience)"),
]


def scan(path: Path) -> tuple[int, dict[str, int]]:
    exts: dict[str, int] = defaultdict(int)
    for f in path.rglob("*"):
        if f.is_file():
            exts[f.suffix.lower() or "(none)"] += 1
    return sum(exts.values()), dict(exts)


rows = []
for rel, description in DIRS:
    d = URANIUM_SRC / rel
    if not d.exists():
        rows.append((rel, description, None, None))
        continue
    total, exts = scan(d)
    ext_str = ", ".join(f"`{e}` ×{n}" for e, n in sorted(exts.items(), key=lambda x: -x[1]))
    rows.append((rel, description, total, ext_str))

lines = [
    "# Asset Inventory",
    "",
    "| Directory | Files | Types | Description |",
    "|---|---|---|---|",
]
for rel, desc, total, exts in rows:
    if total is None:
        lines.append(f"| `{rel}` | — | — | {desc} (not found) |")
    else:
        lines.append(f"| `{rel}` | {total} | {exts} | {desc} |")

lines += [
    "",
    "## Conversion notes",
    "",
    "- **Sprites:** GBA is 4bpp indexed, 16 colors per palette. All Uranium PNGs (full-color) will",
    "  visibly degrade. Budget manual cleanup for high-visibility sprites: player, starters, gym leaders.",
    "- **Tilesets:** RPG Maker uses 32×32 logical tiles with full-color art. GBA uses 8×8 tiles.",
    "  Phase 5 uses Approach A: substitute closest pokeemerald-expansion tiles rather than reconvert.",
    "- **Audio:** Not converted. GBA uses sappy/m4a sequences. Plan to substitute existing",
    "  pokeemerald music. Leave as Phase 8 polish.",
]

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"Written: {OUT}")
