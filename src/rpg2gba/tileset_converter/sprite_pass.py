"""Task 4 shared pass: real Uranium NPC + player sheets -> engine object-event
gen files.

One entry point (`run_sprite_pass`) both assembler paths call before compiling
scripts / running `make`:

  1. read `reference/npc_gfx_map.json`, select every sheet whose target gfx is a
     minted ``OBJ_EVENT_GFX_URANIUM_*`` constant (the sheets the 2026-07-05 pivot
     decided to CONVERT; entries pointing at a plain vanilla constant carry no
     Uranium art and are skipped here),
  2. convert each NPC sheet from ``$RPG2GBA_URANIUM_SRC/Graphics/Characters/<sheet>.png``
     (filename resolved case-insensitively) via `sprites.convert_character_sheet`,
  2b. convert the player's walk (``HERO``) + run (``HERO-RUN``) sheets from the
      same directory via `sprites.convert_player_sheets` — this runs on EVERY
      sprite pass (not gated by the npc gfx map: the player isn't an
      OBJ_EVENT_GFX_* entry), so a missing HERO/HERO-RUN sheet fails loud here
      rather than producing a build with no player art,
  3. hand the `ConvertedSprite` list AND the `ConvertedPlayer` to
     `sprite_emit.emit_sprites`, which quantizes the NPC sheets onto <=4 shared
     palettes, quantizes the player onto its own dedicated palette, and writes
     the 7 `.gen.h` fragments + indexed PNGs (NPC strips + `hero.png`).

Deterministic and idempotent (`convert_character_sheet`, `convert_player_sheets`,
and `emit_sprites` all are), so the double execution — once in
`stage_slice_scripts.py` to populate the constants header the `npc_gfx`
validation reads, once in `assemble_pathfinder.run_graphics_pass` to guarantee
fresh gen files before `make` — is harmless by design (CLAUDE.md §4.2).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from .graphics.sprite_emit import SpriteEmitResult, emit_sprites
from .graphics.sprites import convert_character_sheet, convert_player_sheets
from .npc_gfx import DEFAULT_NPC_GFX_MAP, GFX_PREFIX, gfx_constant_for_sheet

logger = logging.getLogger(__name__)

#: Only sheets whose declared gfx is a minted Uranium constant get converted.
_URANIUM_GFX_PREFIX = f"{GFX_PREFIX}_"

#: The player's walk/run RMXP character sheet names under Graphics/Characters/
#: (resolved case-insensitively, same as NPC sheets — see `_resolve_sheet`).
PLAYER_WALK_SHEET = "HERO"
PLAYER_RUN_SHEET = "HERO-RUN"


def _characters_dir() -> Path:
    """``<RPG2GBA_URANIUM_SRC>/Graphics/Characters``, loading .env-paths if unset."""
    if "RPG2GBA_URANIUM_SRC" not in os.environ:
        from rpg2gba.pipeline import _load_dotenv  # lazy: only for the env default

        _load_dotenv()
    src = os.environ.get("RPG2GBA_URANIUM_SRC")
    if not src:
        raise RuntimeError(
            "RPG2GBA_URANIUM_SRC is not set (and .env-paths didn't provide it); "
            "point it at the unpacked Uranium tree"
        )
    return Path(src) / "Graphics" / "Characters"


def _resolve_sheet(characters_dir: Path, name: str) -> Path:
    """``<characters_dir>/<name>.png`` with a case-insensitive fallback. Fail loud."""
    exact = characters_dir / f"{name}.png"
    if exact.is_file():
        return exact
    target = name.lower()
    if characters_dir.is_dir():
        for p in sorted(characters_dir.iterdir()):
            if p.is_file() and p.suffix.lower() == ".png" and p.stem.lower() == target:
                return p
    raise FileNotFoundError(f"sheet {name!r} not found under {characters_dir}")


def sheets_to_convert(gfx_map_path: Path = DEFAULT_NPC_GFX_MAP) -> list[str]:
    """Sheet names in the npc gfx map whose target gfx is an ``OBJ_EVENT_GFX_URANIUM_*``
    (needs real sprite conversion), sorted. Fails loud if a declared constant
    disagrees with the deterministic `gfx_constant_for_sheet` — `sprite_emit`
    derives its constant from the sheet name, not the JSON, so any drift would
    silently emit a sprite under the wrong constant (CLAUDE.md §4.5)."""
    raw = json.loads(Path(gfx_map_path).read_text(encoding="utf-8"))
    names: list[str] = []
    for sheet_name, entry in raw.items():
        gfx = entry.get("gfx")
        if not gfx or not gfx.startswith(_URANIUM_GFX_PREFIX):
            continue
        expected = gfx_constant_for_sheet(sheet_name)
        if gfx != expected:
            raise ValueError(
                f"{gfx_map_path}: sheet {sheet_name!r} declares gfx {gfx!r} but "
                f"sprite_emit derives {expected!r} from the sheet name; they must "
                f"agree (fix the JSON key or its gfx value)"
            )
        names.append(sheet_name)
    return sorted(names)


def run_sprite_pass(
    engine_root: Path,
    *,
    gfx_map_path: Path = DEFAULT_NPC_GFX_MAP,
    characters_dir: Path | None = None,
) -> SpriteEmitResult:
    """Convert every Uranium NPC sheet in the gfx map plus the player's walk/run
    sheets, and emit the 7 engine `.gen.h` fragments + indexed PNGs (NPC strips
    + `hero.png`) under `engine_root`. Deterministic + idempotent; logs the
    shared-palette assignment so a build reader can see which sheets landed on
    which of the <=4 NPC palettes (the player always gets its own dedicated
    palette, never one of the four).

    The player conversion runs on every call — it isn't gated by the npc gfx
    map (the player carries no `OBJ_EVENT_GFX_*` id), so a missing HERO /
    HERO-RUN sheet fails loud here rather than silently shipping a build with
    no player art (CLAUDE.md §4.5)."""
    names = sheets_to_convert(gfx_map_path)
    if not names:
        raise ValueError(
            f"{gfx_map_path}: no OBJ_EVENT_GFX_URANIUM_* sheets to convert"
        )
    chars_dir = characters_dir or _characters_dir()

    sprites = [convert_character_sheet(_resolve_sheet(chars_dir, name)) for name in names]
    player = convert_player_sheets(
        _resolve_sheet(chars_dir, PLAYER_WALK_SHEET),
        _resolve_sheet(chars_dir, PLAYER_RUN_SHEET),
    )
    result = emit_sprites(sprites, Path(engine_root), player=player)

    by_palette: dict[int, list[str]] = {}
    for sheet_name, pal_idx in result.palette_index.items():
        by_palette.setdefault(pal_idx, []).append(sheet_name)
    logger.info(
        "sprite pass: %d NPC sheet(s) -> %d shared palette(s), player -> %s, "
        "%d file(s) written",
        len(sprites), len(result.palette_tags), result.player_palette_tag,
        len(result.files_written),
    )
    for pal_idx in sorted(by_palette):
        logger.info(
            "  palette %d (%s): %s",
            pal_idx,
            result.palette_tags[pal_idx],
            ", ".join(sorted(by_palette[pal_idx])),
        )
    return result
