"""Write every generated item file, mirrored under `out_dir/engine/`.

The assembler (`scripts/assemble_pathfinder.py`, S8b9) copies the mirror into
the engine; every destination is gitignored (engine/.gitignore).
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from rpg2gba.species_converter.stage import load_charmap_chars
from rpg2gba.text_validator.engine_metrics import load_charmap

from . import art, bag, emit
from .catalog import Catalog, build_catalog

logger = logging.getLogger(__name__)

ITEMS_OUT_SUBDIR = Path("items")
MIRROR = "engine"

#: Engine-relative paths of the generated headers.
CONSTANTS_H = Path("include/constants/rpg2gba_items.gen.h")
EXTERNS_H = Path("include/rpg2gba/item_graphics_externs.gen.h")
GEN_SRC = Path("src/data/rpg2gba")
ICON_DIR = Path("graphics/items/rpg2gba")
BERRY_PIC_DIR = Path("graphics/berries/rpg2gba")


def _write(root: Path, rel: Path, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_all(uranium_src: Path, fork: Path, out_dir: Path) -> Catalog:
    """Build the catalog and write headers + art into `out_dir/engine/`.

    The mirror is rebuilt from scratch each run, so an item that stops being
    generated leaves nothing behind (CLAUDE.md §4.2)."""
    cat = build_catalog(uranium_src)
    root = Path(out_dir) / MIRROR
    if root.exists():
        shutil.rmtree(root)
    charmap = load_charmap(Path(fork) / "charmap.txt")
    chars = load_charmap_chars(Path(fork))
    stock = emit.stock_sources(fork)

    has_icon: dict[str, bool] = {}
    for item in cat.generated:
        src = art.source_icon(uranium_src, item.uranium_id)
        has_icon[item.constant] = src is not None
        if src is not None:
            s = emit.stem(item)
            art.convert_icon(src, root / ICON_DIR / f"{s}.png", root / ICON_DIR / f"{s}.pal")
    for item in cat.berries:
        src = art.source_icon(uranium_src, item.uranium_id)
        if src is None:
            raise FileNotFoundError(f"{item.constant}: a berry needs its icon for the berry pic")
        art.convert_berry_pic(src, root / BERRY_PIC_DIR / f"{emit.stem(item)}.png")

    externs, definitions = emit.render_graphics(cat, has_icon)
    _write(root, CONSTANTS_H, emit.render_constants(cat))
    _write(root, bag.BAG_H, bag.render_for_game(uranium_src))
    _write(root, EXTERNS_H, externs)
    _write(root, GEN_SRC / "item_graphics.gen.h", definitions)
    _write(root, GEN_SRC / "items_info.gen.h",
           emit.render_items_info(cat, charmap, chars, has_icon, stock["items"]))
    _write(root, GEN_SRC / "item_effects.gen.h", emit.render_item_effects(cat))
    _write(root, GEN_SRC / "berries.gen.h",
           emit.render_berries(cat, charmap, chars, stock["berry_c"]))
    _write(root, GEN_SRC / "berry_crush.gen.h", emit.render_berry_rows(
        cat, stock["berry_c"], "gBerryCrush_BerryData", "src/berry.c"))
    _write(root, GEN_SRC / "berry_pics.gen.h", emit.render_berry_pics(cat))
    _write(root, GEN_SRC / "berry_tree_pics.gen.h", emit.render_berry_rows(
        cat, stock["trees"], "gBerryTreePicTablePointers",
        "src/data/object_events/berry_tree_graphics_tables.h"))
    _write(root, GEN_SRC / "berry_tree_palettes.gen.h", emit.render_berry_rows(
        cat, stock["trees"], "gBerryTreePaletteSlotTablePointers",
        "src/data/object_events/berry_tree_graphics_tables.h"))

    manifest = {
        "berries": [g.constant for g in cat.berries],
        "tail": [g.constant for g in cat.tail],
        "blocked": {g.constant: g.internal for g in cat.blocked},
        "no_icon": sorted(c for c, ok in has_icon.items() if not ok),
    }
    (Path(out_dir) / "items_manifest.json").write_text(
        json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    logger.info("  items: %d berries + %d others generated, %d blocked, %d without icon",
                len(cat.berries), len(cat.tail), len(cat.blocked), len(manifest["no_icon"]))
    return cat


def install(out_dir: Path, fork: Path) -> list[Path]:
    """Replace the engine's generated item files with the mirror; returns the
    engine-relative paths written. Generated directories are cleared first so a
    dropped item's asset can't linger."""
    root = Path(out_dir) / MIRROR
    fork = Path(fork)
    for rel in (EXTERNS_H.parent, GEN_SRC, ICON_DIR, BERRY_PIC_DIR):
        if (fork / rel).exists():
            shutil.rmtree(fork / rel)
    written: list[Path] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root)
        dest = fork / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        written.append(rel)
    return written
