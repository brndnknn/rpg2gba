"""Write every generated battle file, mirrored under `out_dir/engine/`.

The assembler (`scripts/assemble_pathfinder.py`, S8b10) installs the mirror into
the engine; every destination is gitignored (engine/.gitignore).
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from rpg2gba.species_converter.stage import load_charmap_chars
from rpg2gba.text_validator.engine_metrics import load_charmap

from . import emit
from .catalog import Catalog, build_catalog

logger = logging.getLogger(__name__)

BATTLE_OUT_SUBDIR = Path("battle")
MIRROR = "engine"

MOVES_H = Path("include/constants/rpg2gba_moves.gen.h")
ABILITIES_H = Path("include/constants/rpg2gba_abilities.gen.h")
MACHINES_H = Path("include/constants/rpg2gba_machines.gen.h")
GEN_SRC = Path("src/data/rpg2gba_battle")
#: Every engine path this pass owns; install clears them first, so a file the
#: pass stops writing cannot linger.
OWNED = (MOVES_H, ABILITIES_H, MACHINES_H, GEN_SRC)


def _write(root: Path, rel: Path, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_all(uranium_src: Path, fork: Path, out_dir: Path) -> Catalog:
    """Build the catalog and write the headers into `out_dir/engine/`.

    `fork` must be the engine without this pass installed (or with it -- the
    stock constants are read through the enum, which the hooks leave intact)."""
    cat = build_catalog(uranium_src, fork)
    root = Path(out_dir) / MIRROR
    if root.exists():
        shutil.rmtree(root)
    fork = Path(fork)
    charmap = load_charmap(fork / "charmap.txt")
    chars = load_charmap_chars(fork)
    stock_moves_info = (fork / "src/data/moves_info.h").read_text(encoding="utf-8")

    _write(root, MOVES_H, emit.render_move_constants(cat))
    _write(root, ABILITIES_H, emit.render_ability_constants(cat))
    stock_tms, stock_hms = emit.stock_machines(
        (fork / "include/constants/tms_hms.h").read_text(encoding="utf-8"))
    _write(root, MACHINES_H, emit.render_machines(cat, stock_tms, stock_hms))
    _write(root, GEN_SRC / "moves_info.gen.h",
           emit.render_moves_info(cat, charmap, chars, stock_moves_info))
    _write(root, GEN_SRC / "abilities_info.gen.h",
           emit.render_abilities_info(cat, charmap, chars))

    manifest = {
        "moves": [g.constant for g in cat.moves],
        "aliases": {g.constant: g.alias_of for g in cat.aliases},
        "blocked": {g.constant: g.reason for g in cat.blocked},
        "abilities": {g.constant: g.kind for g in cat.abilities},
        "inert_abilities": {g.constant: g.reason for g in cat.abilities if g.kind == "inert"},
        "tms": list(cat.tms),
        "hms": list(cat.hms),
        "rewritten_descriptions": {
            g.constant: {"shown": g.description, "uranium": g.uranium_description}
            for g in (*cat.moves, *cat.abilities) if g.description != g.uranium_description
        },
    }
    (Path(out_dir) / "battle_manifest.json").write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("  battle: %d moves + %d aliases generated, %d blocked; %d abilities "
                "(%d implemented); %d TMs, %d HMs",
                len(cat.moves), len(cat.aliases), len(cat.blocked), len(cat.abilities),
                sum(g.kind == "implemented" for g in cat.abilities), len(cat.tms), len(cat.hms))
    return cat


def install(out_dir: Path, fork: Path) -> list[Path]:
    """Replace the engine's generated battle files with the mirror; returns the
    engine-relative paths written."""
    root = Path(out_dir) / MIRROR
    fork = Path(fork)
    for rel in OWNED:
        dest = fork / rel
        if dest.is_dir():
            shutil.rmtree(dest)
        elif dest.exists():
            dest.unlink()
    written: list[Path] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root)
        dest = fork / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        written.append(rel)
    return written
