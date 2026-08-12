"""Trainer-pic + trainer-battle staging emitter -- C/`.party`-DSL emitter
counterpart to `pics.py` (pics) and `battles.py` (battle data).

Consumes `pics.convert_slice_trainer_pics` output (a `FrontPicResult` per
`common.SLICE_TRAINER_PICS` entry, a `BackPicResult` for each player back-pic
identity) and `battles.build_staged_battles` output (a `StagedTrainerBattle`
per `common.SLICE_TRAINER_BATTLES` entry), and emits a set of *generated
overlay* C fragments + a `.party`-DSL fragment plus a machine-readable
manifest under `<out>/uranium-build/trainers/`.

This module does not touch anything under `engine/`. A later unit stages
these files into the vendored fork behind committed
`URANIUM PATHFINDER SLICE`-style fenced include-hooks, mirroring
`species_converter.stage`'s split.

Generated files (all under the trainer staging dir, see `write_all`):

  uranium_trainer_front_pic_ids.h  -- `#define TRAINER_PIC_FRONT_URANIUM_<NAME>
                                       (TRAINER_PIC_COUNT + n)` chains, NOT
                                       enum members. `data/event_scripts.s`
                                       pulls `include/constants/trainers.h`
                                       through `tools/preproc`, whose enum
                                       scanner cannot follow an `#include`
                                       inside an enum body ("unterminated
                                       enum") -- see
                                       `engine/include/constants/pokedex.h`
                                       L1083-1096 and
                                       `engine/include/constants/species.h`
                                       L1691-1698 for the established
                                       precedent. So this file is `#include`d
                                       AFTER `enum TrainerPicID`'s closing
                                       brace, chained off `TRAINER_PIC_COUNT`.
                                       Always ends with a trailing
                                       `URANIUM_TRAINER_PIC_AFTER_FRONT`
                                       define for the back-pic header to
                                       chain off.
  uranium_trainer_back_pic_ids.h   -- same `#define` pattern, chained off
                                       `URANIUM_TRAINER_PIC_AFTER_FRONT`
                                       (with a defensive `#ifndef` fallback
                                       to `TRAINER_PIC_COUNT`). Ends with
                                       `URANIUM_TRAINER_PIC_TOTAL` and, when
                                       staged, `URANIUM_HAVE_PLAYER_BACK_PIC`
                                       / `URANIUM_HAVE_PLAYER_FEMALE_BACK_PIC`
                                       feature-test guards the engine uses to
                                       decide whether to repoint the vanilla
                                       player back-pic macros.
  uranium_trainer_graphics.h       -- `INCGFX_*` declarations for every
                                       staged front pic, back pic, and
                                       palette, pointing at engine-relative
                                       paths under
                                       `graphics/trainers/uranium/<asset_dir>/`.
                                       Every declared symbol is namespaced
                                       `gTrainerFrontPic_Uranium<Ident>` /
                                       `gTrainerPalette_Uranium<Ident>` /
                                       `gTrainerBackPic_Uranium<Ident>` /
                                       `gTrainerBackPicPalette_Uranium<Ident>`
                                       (see `StagedFrontPic.ident` /
                                       `StagedBackPic.ident`) -- vanilla
                                       Emerald already defines
                                       `gTrainerFrontPic_Fisherman`,
                                       `_Youngster`, `_Lass`, etc. for its own
                                       trainer classes, and Uranium stages
                                       trainer-CLASS sprites under the same
                                       bare class names, so an unprefixed
                                       ident collides head-on. The `Uranium`
                                       infix matches this codebase's existing
                                       collision-namespacing convention
                                       (`OBJ_EVENT_GFX_URANIUM_*`,
                                       `TRAINER_PIC_FRONT_URANIUM_*` /
                                       `TRAINER_PIC_BACK_URANIUM_*` in
                                       `common.py`). Also emits the dedicated
                                       `sBackAnims_Uranium` animation table
                                       (plus its two `AnimCmd` tables)
                                       whenever at least one back pic is
                                       staged -- see `BACK_SPRITE_ANIM_TABLE`.
                                       Destined for `#include` at the end of
                                       `src/data/graphics/trainers.h`.
  uranium_trainer_sprites.h        -- `TRAINER_SPRITE(...)` rows. Destined
                                       for injection inside the
                                       `gTrainerSprites[]` array body.
  uranium_trainer_backsprites.h    -- `TRAINER_BACK_SPRITE(...)` rows.
                                       Destined for injection inside the
                                       `gTrainerBacksprites[]` array body.
  uranium_trainer_ids.h            -- `TRAINER_*` id `#define` chain off
                                       `TRAINER_MAY_PLACEHOLDER` (see
                                       `battles.emit_trainer_ids`). Destined
                                       for `#include` in
                                       `include/constants/opponents.h` right
                                       after the `TRAINER_MAY_PLACEHOLDER`
                                       line.
  uranium_trainer_party.inc        -- `.party`-DSL trainer battle blocks
                                       (`tools/trainerproc` input, NOT C --
                                       see `battles.emit_party_fragment`).
                                       Destined for `#include` at the end of
                                       `src/data/trainers.party`.
  trainer_manifest.json            -- flat per-pic/per-battle record tying
                                       constants to asset paths and emitted C
                                       symbol names; consumed by the
                                       fork-capability gate and by other
                                       converter units.

**Verified indexing invariant (CLAUDE.md §4.7):** `gTrainerBacksprites[]` and
`gTrainerSprites[]` are BOTH designated-initializer arrays keyed by the
symbolic enum constant itself (`[trainerPic] = {...}` inside the
`TRAINER_SPRITE`/`TRAINER_BACK_SPRITE` macros --
`engine/src/data/graphics/trainers.h` lines 490-497 and 726-733), and every
consumer (`engine/src/trainer_pokemon_sprites.c` L365/367,
`engine/src/battle_controller_player.c` L1927/1947/1953/2306,
`engine/src/battle_gfx_sfx_util.c` L704) indexes `gTrainerBacksprites[]` by a
runtime `trainerPicId`/`backPicId`/`paletteIndex` value that is itself one of
these same enum constants -- never a hand-computed offset. `TRAINER_PIC_BACK_*`
members are declared as `TRAINER_PIC_BACK_BRENDAN = TRAINER_PIC_FRONT_COUNT`
then implicitly incrementing (`include/constants/trainers.h` L176-186), so
appending new `TRAINER_PIC_FRONT_URANIUM_*` members before
`TRAINER_PIC_FRONT_COUNT` shifts every `TRAINER_PIC_BACK_*` numeric value
upward -- but since both the array initializers and every reader use the
symbolic name (never a literal), the shift is self-consistent and safe. The
designated-initializer form also means `gTrainerBacksprites[]`'s effective
length auto-grows to `max(index)+1` to cover the appended back constants; no
manual resize is needed.

**Critical invariant (CLAUDE.md §4.2 + the species-stage empty-overlay
rule):** every generated file is always emitted, and is a semantic no-op when
there are zero staged front/back pics. `write_all(..., fronts=(), backs=())`
produces a pristine-equivalent overlay set. Emitting twice with the same
inputs produces byte-identical output -- no timestamps in generated content.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from rpg2gba.pbs_converter._c_emit import generated_banner
from rpg2gba.pbs_converter._naming import load_fork_constants
from rpg2gba.trainer_converter import battles as battles_mod
from rpg2gba.trainer_converter import common, pics
from rpg2gba.trainer_converter.battles import StagedTrainerBattle
from rpg2gba.trainer_converter.common import TrainerPicSpec

logger = logging.getLogger(__name__)

GENERATOR = "rpg2gba.trainer_converter.stage"
MANIFEST_VERSION = 1
MANIFEST_NAME = "trainer_manifest.json"

#: Engine-relative directory root all staged trainer art is hooked under.
ENGINE_GFX_ROOT = Path("graphics/trainers/uranium")

#: `pics.convert_slice_trainer_pics` writes the whole slice's front+back art
#: into one flat output directory (see `pics.py`'s `out_dir` docstring); this
#: is that directory's name once staged into the engine tree.
DEFAULT_ASSET_DIR = "slice1"

#: Back pics are always a 4-frame ball-throw sheet (`common.BACK_PIC_FRAMES`)
#: -- 4 frames matches the vanilla 4-frame Hoenn-style back pics
#: (`sAnimCmd_Kanto`/`sBackAnims_Kanto` is a 5-frame table reserved for
#: FRLG-style back pics). yOffset 4 matches the vanilla 4-frame back pics
#: (Brendan/May) in `engine/src/data/graphics/trainers.h`.
#:
#: We do NOT reference the stock `sBackAnims_Hoenn` table, though. Vanilla's
#: Hoenn back-pic sheets are throw-pose-first: `sBackAnims_Hoenn[0]` (the
#: default/idle slot) is `sAnim_GeneralFrame3`, because frame 3 on *those*
#: sheets is the idle standing pose. Our converted Uranium back sheets are
#: idle-FIRST (frame 0 = idle, 1 = raise ball, 2 = windup, 3 = throw), so
#: parking on `sBackAnims_Hoenn[0]` displayed our frame 3 -- the throw pose --
#: as a static "idle" image instead of animating into it. `sBackAnims_Uranium`
#: (emitted into `uranium_trainer_graphics.h`, see `emit_graphics`) is a
#: dedicated table built for our frame order; do not swap this back to
#: `sBackAnims_Hoenn`.
BACK_SPRITE_Y_OFFSET = 4
BACK_SPRITE_ANIM_TABLE = "sBackAnims_Uranium"

#: The dedicated animation table block emitted into `uranium_trainer_graphics.h`
#: whenever at least one back pic is staged. Self-contained (defines its own
#: idle command rather than reusing the stock `sAnim_GeneralFrame0`) so this
#: header has no dependency on symbols declared later in
#: `engine/src/data/graphics/trainers.h` or elsewhere -- it is `#include`d at
#: file scope partway through that file. See the `BACK_SPRITE_ANIM_TABLE`
#: comment above for why a dedicated table exists at all.
_BACK_ANIM_TABLE_BLOCK = """\
// Dedicated back-pic animation table for Uranium's back sheets -- do NOT
// reuse the stock sBackAnims_Hoenn here. sBackAnims_Hoenn[0] (the
// default/idle slot) is sAnim_GeneralFrame3 because vanilla's Hoenn back
// sheets put the idle pose at frame index 3. Our converted Uranium sheets
// are idle-FIRST (0 = idle, 1 = raise ball, 2 = windup, 3 = throw), so
// sBackAnims_Hoenn[0] would statically display our throw frame (index 3)
// instead of the idle pose -- the reported "static throw pose" bug.
// Self-contained: defines its own idle command rather than referencing
// sAnim_GeneralFrame0, since this header is #include'd before those stock
// tables are declared.
static const union AnimCmd sAnim_UraniumBackIdle[] =
{
    ANIMCMD_FRAME(0, 1),
    ANIMCMD_END,
};

static const union AnimCmd sAnimCmd_UraniumBackThrow[] =
{
    ANIMCMD_FRAME(0, 24),
    ANIMCMD_FRAME(1, 9),
    ANIMCMD_FRAME(2, 24),
    ANIMCMD_FRAME(3, 50),
    ANIMCMD_END,
};

static const union AnimCmd *const sBackAnims_Uranium[] =
{
    sAnim_UraniumBackIdle,
    sAnimCmd_UraniumBackThrow,
    sAnim_UraniumBackIdle,
};
"""


def _pascal_ident(internal_name: str) -> str:
    """`RIVAL` -> `Rival`, `PLAYER_MALE` -> `PlayerMale`.

    Matches the vanilla fork's `gTrainerFrontPic_<Ident>` naming convention
    (e.g. `gTrainerFrontPic_AquaGruntM`) -- PascalCase, no separators.

    Callers use this to build the *unprefixed* PascalCase suffix; see
    `StagedFrontPic.ident` / `StagedBackPic.ident` for the `Uranium`-prefixed
    form actually used in emitted symbol names (namespacing against vanilla
    trainer-class collisions -- `gTrainerFrontPic_Fisherman` etc. already
    exist in the fork).
    """
    parts = [p for p in internal_name.replace("'", "").split("_") if p]
    return "".join(p[:1].upper() + p[1:].lower() for p in parts) or "Trainer"


@dataclass(frozen=True)
class StagedFrontPic:
    """One front pic ready to emit.

    `asset_dir` is the engine-relative art subdirectory under
    `ENGINE_GFX_ROOT` this pic's files live in; `None` falls back to
    `DEFAULT_ASSET_DIR` (slice-1's original flat single-directory layout, kept
    as the default so existing single-pic callers are unaffected).
    """

    spec: TrainerPicSpec
    result: pics.FrontPicResult
    asset_dir: str | None = None

    @property
    def ident(self) -> str:
        return f"Uranium{_pascal_ident(self.spec.internal_name)}"

    @property
    def front_symbol(self) -> str:
        return f"gTrainerFrontPic_{self.ident}"

    @property
    def palette_symbol(self) -> str:
        return f"gTrainerPalette_{self.ident}"

    @property
    def effective_asset_dir(self) -> str:
        return self.asset_dir if self.asset_dir is not None else DEFAULT_ASSET_DIR


@dataclass(frozen=True)
class StagedBackPic:
    """One back pic ready to emit. See `StagedFrontPic.asset_dir`."""

    spec: TrainerPicSpec
    result: pics.BackPicResult
    asset_dir: str | None = None

    @property
    def ident(self) -> str:
        return f"Uranium{_pascal_ident(self.spec.internal_name)}"

    @property
    def back_symbol(self) -> str:
        return f"gTrainerBackPic_{self.ident}"

    @property
    def palette_symbol(self) -> str:
        return f"gTrainerBackPicPalette_{self.ident}"

    @property
    def effective_asset_dir(self) -> str:
        return self.asset_dir if self.asset_dir is not None else DEFAULT_ASSET_DIR


# ===========================================================================
# C emit helpers
# ===========================================================================


def _no_op_note() -> str:
    return "// (no Uranium trainer pics selected -- this overlay is a no-op)\n"


#: Why `#defines`, not enum members: `data/event_scripts.s` pulls
#: `include/constants/trainers.h` through `tools/preproc`, whose enum scanner
#: cannot follow an `#include` inside an enum body ("unterminated enum" --
#: see `engine/include/constants/pokedex.h` L1083-1096 and
#: `engine/include/constants/species.h` L1691-1698 for the established
#: precedent with national-dex/species ids). DO NOT "tidy" these back into
#: bare enumerators spliced into `enum TrainerPicID` -- that breaks the
#: preproc build. These files are `#include`d AFTER the enum's closing brace.
_DEFINE_NOT_ENUM_NOTE = (
    "// #define chain, NOT enum members -- see module docstring / stage.py:\n"
    "// tools/preproc's enum scanner can't follow an #include inside an enum\n"
    "// body (\"unterminated enum\"). Do not move this into enum TrainerPicID.\n"
)

#: internal_name -> feature-test guard `#define` emitted when that back pic
#: is staged. The engine uses these to decide whether to repoint the vanilla
#: player back-pic macros (`TRAINER_BACK_PIC_PLAYER_MALE` etc.) at the staged
#: Uranium sprite, or leave them on the vanilla fallback.
_PLAYER_BACK_PIC_GUARDS = {
    "PLAYER_MALE": "URANIUM_HAVE_PLAYER_BACK_PIC",
    "PLAYER_FEMALE": "URANIUM_HAVE_PLAYER_FEMALE_BACK_PIC",
}

_AFTER_FRONT = "URANIUM_TRAINER_PIC_AFTER_FRONT"
_BACK_TOTAL = "URANIUM_TRAINER_PIC_TOTAL"


def _define_line(name: str, value: str, width: int) -> str:
    return f"#define {name.ljust(width)}{value}"


def emit_front_pic_ids(fronts: list[StagedFrontPic]) -> str:
    """`uranium_trainer_front_pic_ids.h`: `#define`s chained off
    `TRAINER_PIC_COUNT`, destined for `#include` AFTER `enum TrainerPicID`'s
    closing brace (never inside it -- see `_DEFINE_NOT_ENUM_NOTE`).

    Always emits a trailing `URANIUM_TRAINER_PIC_AFTER_FRONT` define -- even
    with zero staged front pics -- so the back-pic header always has
    something valid to chain off.
    """
    banner = generated_banner("SLICE_TRAINER_PICS (common.py)", GENERATOR, timestamp=False)
    names = [f.spec.pic_constant for f in fronts] + [_AFTER_FRONT]
    width = max(len(n) for n in names) + 3
    lines = [
        _define_line(f.spec.pic_constant, f"(TRAINER_PIC_COUNT + {n})", width)
        for n, f in enumerate(fronts)
    ]
    lines.append(_define_line(_AFTER_FRONT, f"(TRAINER_PIC_COUNT + {len(fronts)})", width))
    body = banner + _DEFINE_NOT_ENUM_NOTE
    if not fronts:
        body += _no_op_note()
    return body + "\n" + "\n".join(lines) + "\n"


def emit_back_pic_ids(backs: list[StagedBackPic]) -> str:
    """`uranium_trainer_back_pic_ids.h`: `#define`s chained off
    `URANIUM_TRAINER_PIC_AFTER_FRONT` (with a defensive `#ifndef` fallback to
    `TRAINER_PIC_COUNT`), destined for `#include` AFTER `enum TrainerPicID`'s
    closing brace, after the front-pic header (never inside the enum -- see
    `_DEFINE_NOT_ENUM_NOTE`).

    Always emits a trailing `URANIUM_TRAINER_PIC_TOTAL` define. Emits a
    per-name feature-test guard (`_PLAYER_BACK_PIC_GUARDS`) for any staged
    back pic whose internal name is a recognized player identity.
    """
    banner = generated_banner("SLICE_TRAINER_PICS (common.py)", GENERATOR, timestamp=False)
    fallback = (
        f"#ifndef {_AFTER_FRONT}\n"
        f"#define {_AFTER_FRONT.ljust(len(_AFTER_FRONT) + 3)}TRAINER_PIC_COUNT\n"
        "#endif\n"
    )
    names = [b.spec.back_pic_constant for b in backs] + [_BACK_TOTAL]
    width = max(len(n) for n in names) + 3
    lines = [
        _define_line(b.spec.back_pic_constant, f"({_AFTER_FRONT} + {n})", width)
        for n, b in enumerate(backs)
    ]
    lines.append(_define_line(_BACK_TOTAL, f"({_AFTER_FRONT} + {len(backs)})", width))
    guards = [
        f"#define {_PLAYER_BACK_PIC_GUARDS[b.spec.internal_name]}"
        for b in backs
        if b.spec.internal_name in _PLAYER_BACK_PIC_GUARDS
    ]
    body = banner + _DEFINE_NOT_ENUM_NOTE
    if not backs:
        body += _no_op_note()
    body += "\n" + fallback + "\n" + "\n".join(lines) + "\n"
    if guards:
        body += "\n" + "\n".join(guards) + "\n"
    return body


def emit_graphics(fronts: list[StagedFrontPic], backs: list[StagedBackPic]) -> str:
    """`uranium_trainer_graphics.h`: `INCGFX_*` declarations.

    Front pics are 64x64 compressed 4bpp (`INCGFX_U32(...) .4bpp.smol`,
    matching every vanilla `gTrainerFrontPic_*`). Back pics are the
    uncompressed vertical 64x256 4-frame sheet (`INCGFX_U8(...) .4bpp`,
    matching every vanilla `gTrainerBackPic_*`). Both palettes are plain
    `.gbapal` (`INCGFX_U16`). Each entry's `effective_asset_dir` gives its own
    art subdirectory -- multiple staged pics never share one flat directory.
    """
    banner = generated_banner(
        "SLICE_TRAINER_PICS asset layout (common.py)", GENERATOR, timestamp=False
    )
    if not fronts and not backs:
        return banner + _no_op_note()
    lines: list[str] = []
    for f in fronts:
        d = f"{ENGINE_GFX_ROOT.as_posix()}/{f.effective_asset_dir}"
        lines.append(
            f'const u32 {f.front_symbol}[] = INCGFX_U32("{d}/{pics.FRONT_PNG}", ".4bpp.smol");'
        )
        lines.append(
            f'const u16 {f.palette_symbol}[] = INCGFX_U16("{d}/{pics.FRONT_PAL}", ".gbapal");'
        )
        lines.append("")
    for b in backs:
        d = f"{ENGINE_GFX_ROOT.as_posix()}/{b.effective_asset_dir}"
        lines.append(f'const u8 {b.back_symbol}[] = INCGFX_U8("{d}/{pics.BACK_PNG}", ".4bpp");')
        lines.append(
            f'const u16 {b.palette_symbol}[] = INCGFX_U16("{d}/{pics.BACK_PAL}", ".gbapal");'
        )
        lines.append("")
    if backs:
        lines.append(_BACK_ANIM_TABLE_BLOCK)
    return banner + "\n" + "\n".join(lines).rstrip() + "\n"


def emit_sprites(fronts: list[StagedFrontPic]) -> str:
    """`uranium_trainer_sprites.h`: `TRAINER_SPRITE(...)` rows, destined for
    injection inside the `gTrainerSprites[]` array body."""
    banner = generated_banner("SLICE_TRAINER_PICS (common.py)", GENERATOR, timestamp=False)
    if not fronts:
        return banner + _no_op_note()
    lines = [
        f"    TRAINER_SPRITE({f.spec.pic_constant}, {f.front_symbol}, {f.palette_symbol}),"
        for f in fronts
    ]
    return banner + "\n" + "\n".join(lines) + "\n"


def emit_backsprites(backs: list[StagedBackPic]) -> str:
    """`uranium_trainer_backsprites.h`: `TRAINER_BACK_SPRITE(...)` rows,
    destined for injection inside the `gTrainerBacksprites[]` array body.
    yOffset is always `BACK_SPRITE_Y_OFFSET` (4) and the animation table is
    always `BACK_SPRITE_ANIM_TABLE` (`sBackAnims_Uranium`, emitted into
    `uranium_trainer_graphics.h` by `emit_graphics`) -- NOT the stock
    `sBackAnims_Hoenn`, whose idle slot is frame index 3 while our sheets are
    idle-first (frame 0). See `BACK_SPRITE_ANIM_TABLE`'s comment for detail."""
    banner = generated_banner("SLICE_TRAINER_PICS (common.py)", GENERATOR, timestamp=False)
    if not backs:
        return banner + _no_op_note()
    lines = [
        f"    TRAINER_BACK_SPRITE({b.spec.back_pic_constant}, {BACK_SPRITE_Y_OFFSET}, "
        f"{b.back_symbol}, {b.palette_symbol}, {BACK_SPRITE_ANIM_TABLE}),"
        for b in backs
    ]
    return banner + "\n" + "\n".join(lines) + "\n"


# ===========================================================================
# Manifest
# ===========================================================================


def build_manifest(
    fronts: list[StagedFrontPic],
    backs: list[StagedBackPic],
    battles: list[StagedTrainerBattle] = (),
) -> dict:
    records: list[dict] = []
    for f in fronts:
        d = f"{ENGINE_GFX_ROOT.as_posix()}/{f.effective_asset_dir}"
        records.append(
            {
                "kind": "front",
                "trainer_id": f.spec.trainer_id,
                "internal_name": f.spec.internal_name,
                "pic_constant": f.spec.pic_constant,
                "gfx_ident": f.ident,
                "asset_dir": d,
                "art_files": {
                    "png": f"{d}/{pics.FRONT_PNG}",
                    "pal": f"{d}/{pics.FRONT_PAL}",
                },
                "frame_count": 1,
                "c_symbols": {
                    "front_pic": f.front_symbol,
                    "palette": f.palette_symbol,
                },
            }
        )
    for b in backs:
        d = f"{ENGINE_GFX_ROOT.as_posix()}/{b.effective_asset_dir}"
        records.append(
            {
                "kind": "back",
                "trainer_id": b.spec.trainer_id,
                "internal_name": b.spec.internal_name,
                "back_pic_constant": b.spec.back_pic_constant,
                "gfx_ident": b.ident,
                "asset_dir": d,
                "art_files": {
                    "png": f"{d}/{pics.BACK_PNG}",
                    "pal": f"{d}/{pics.BACK_PAL}",
                },
                "frame_count": b.result.frame_count,
                "c_symbols": {
                    "back_pic": b.back_symbol,
                    "palette": b.palette_symbol,
                    "anim_table": BACK_SPRITE_ANIM_TABLE,
                },
                "back_sprite_y_offset": BACK_SPRITE_Y_OFFSET,
            }
        )
    records.extend(battles_mod.build_battle_manifest_records(list(battles)))
    return {
        "version": MANIFEST_VERSION,
        "generator": GENERATOR,
        "trainers": records,
    }


# ===========================================================================
# Top-level entry points
# ===========================================================================


def write_all(
    *,
    out_dir: Path,
    fronts: list[StagedFrontPic] | tuple[StagedFrontPic, ...] = (),
    backs: list[StagedBackPic] | tuple[StagedBackPic, ...] = (),
    battles: list[StagedTrainerBattle] | tuple[StagedTrainerBattle, ...] = (),
    trainer_anchor: str = common.PRISTINE_TRAINER_ANCHOR,
) -> dict:
    """Emit the full overlay set + manifest for the given staged pics/battles.

    `out_dir` is the trainer staging directory itself (typically
    `$RPG2GBA_OUTPUT/uranium-build/trainers`); this function writes directly
    into it (creating it if needed). Never writes into `engine/`.

    Returns the manifest dict (also written to `trainer_manifest.json`).
    """
    fronts = list(fronts)
    backs = list(backs)
    battles = list(battles)
    out_dir.mkdir(parents=True, exist_ok=True)

    _write(out_dir / "uranium_trainer_front_pic_ids.h", emit_front_pic_ids(fronts))
    _write(out_dir / "uranium_trainer_back_pic_ids.h", emit_back_pic_ids(backs))
    _write(out_dir / "uranium_trainer_graphics.h", emit_graphics(fronts, backs))
    _write(out_dir / "uranium_trainer_sprites.h", emit_sprites(fronts))
    _write(out_dir / "uranium_trainer_backsprites.h", emit_backsprites(backs))
    _write(out_dir / "uranium_trainer_ids.h", battles_mod.emit_trainer_ids(battles, trainer_anchor))
    _write(out_dir / "uranium_trainer_party.inc", battles_mod.emit_party_fragment(battles))

    manifest = build_manifest(fronts, backs, battles)
    (out_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    logger.info(
        "staged %d Uranium trainer front pic(s), %d back pic(s), %d battle(s)",
        len(fronts), len(backs), len(battles),
    )
    return manifest


def stage_slice(
    uranium_src: Path, out_dir: Path | None = None, engine_dir: Path | None = None
) -> Path:
    """Convenience wrapper: convert `common.SLICE_TRAINER_PICS`' art via
    `pics.convert_slice_trainer_pics`, resolve `common.SLICE_TRAINER_BATTLES`
    via `battles.build_staged_battles`, then emit the overlay + manifest.

    Writes ONLY under `out_dir` (default
    `output/uranium-build/trainers/`) -- never into `engine/`. `engine_dir`
    defaults to `$RPG2GBA_POKEEMERALD` (mirrors
    `pbs_converter.trainers._build_resolver`'s own env-var convention) so
    this keeps its original 2-positional-argument call shape for existing
    callers (`scripts/assemble_pathfinder.py`). Returns the manifest path.

    If any of `SLICE_TRAINER_BATTLES` can't be staged (e.g. a party species
    hasn't been converted yet), battle staging is SKIPPED with a logged
    warning rather than aborting pic staging -- the pics half of this slice
    stands on its own. Callers that need battle failures to be fatal should
    call `battles.build_staged_battles` directly.
    """
    if out_dir is None:
        out_dir = Path("output") / "uranium-build" / "trainers"
    if engine_dir is None:
        env = os.environ.get("RPG2GBA_POKEEMERALD")
        engine_dir = Path(env) if env else None

    front_results, back_results = pics.convert_slice_trainer_pics(uranium_src, out_dir)
    front_by_name = {r.internal_name: r for r in front_results}
    back_by_name = {r.internal_name: r for r in back_results}
    fronts = [
        StagedFrontPic(
            spec=spec,
            result=front_by_name[spec.internal_name],
            asset_dir=spec.internal_name.lower(),
        )
        for spec in pics.SLICE_TRAINER_PICS
    ]
    backs = [
        StagedBackPic(
            spec=spec,
            result=back_by_name[spec.internal_name],
            asset_dir=spec.internal_name.lower(),
        )
        for spec in pics.SLICE_TRAINER_PICS
        if spec.internal_name in back_by_name
    ]

    staged_battles: list[StagedTrainerBattle] = []
    if engine_dir is not None:
        try:
            staged_battles = stage_battles(
                uranium_src=uranium_src, engine_dir=engine_dir, out_dir=out_dir
            )
        except (ValueError, FileNotFoundError, KeyError) as e:
            logger.warning("trainer battle staging skipped: %s", e)
    else:
        logger.warning(
            "trainer battle staging skipped: RPG2GBA_POKEEMERALD not set and no engine_dir given"
        )

    manifest = write_all(out_dir=out_dir, fronts=fronts, backs=backs, battles=staged_battles)
    manifest_path = out_dir / MANIFEST_NAME
    logger.info("trainer slice staged: %s", manifest_path)
    return manifest_path


def stage_battles(
    *,
    uranium_src: Path,
    engine_dir: Path,
    out_dir: Path,
    selected: tuple[str, ...] = common.SLICE_TRAINER_BATTLES,
) -> list[StagedTrainerBattle]:
    """Resolve `selected` trainer battle keys against the Phase-2 intermediate
    JSON + the live fork + the staged species/pic manifests. Raises
    `ValueError` (never silently drops a trainer) if any selected key can't
    be fully resolved -- see `battles.build_staged_battles`.

    `uranium_src` is unused directly (kept for signature symmetry with the
    rest of this module's staging entry points) -- all data comes from
    already-emitted Phase-2 intermediate JSON under `out_dir`'s sibling
    `intermediate/` directory, never re-parsed from Uranium's `.dat` files.
    """
    del uranium_src  # see docstring
    intermediate_dir = out_dir.parent / "intermediate"
    trainers = battles_mod.load_trainers_json(intermediate_dir)
    trainer_types = battles_mod.load_trainer_types_json(intermediate_dir)

    anchor_value = battles_mod.read_pristine_trainer_anchor(engine_dir)

    species_manifest_path = out_dir.parent / "species" / "species_manifest.json"
    staged_species = battles_mod.load_species_manifest_constants(species_manifest_path)
    staged_pic_names = {spec.internal_name for spec in pics.SLICE_TRAINER_PICS}

    trainers_h = engine_dir / "include" / "constants" / "trainers.h"
    return battles_mod.build_staged_battles(
        selected,
        trainers,
        trainer_types,
        anchor_value,
        fork_classes=load_fork_constants(trainers_h, "TRAINER_CLASS"),
        fork_genders=load_fork_constants(trainers_h, "TRAINER_GENDER"),
        fork_music=load_fork_constants(trainers_h, "TRAINER_ENCOUNTER_MUSIC"),
        fork_species=load_fork_constants(
            engine_dir / "include" / "constants" / "species.h", "SPECIES"
        ),
        fork_moves=load_fork_constants(engine_dir / "include" / "constants" / "moves.h", "MOVE"),
        fork_items=load_fork_constants(engine_dir / "include" / "constants" / "items.h", "ITEM"),
        staged_species=staged_species,
        staged_pic_internal_names=staged_pic_names,
    )


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


__all__ = [
    "GENERATOR",
    "MANIFEST_VERSION",
    "MANIFEST_NAME",
    "ENGINE_GFX_ROOT",
    "DEFAULT_ASSET_DIR",
    "BACK_SPRITE_Y_OFFSET",
    "BACK_SPRITE_ANIM_TABLE",
    "StagedFrontPic",
    "StagedBackPic",
    "emit_front_pic_ids",
    "emit_back_pic_ids",
    "emit_graphics",
    "emit_sprites",
    "emit_backsprites",
    "build_manifest",
    "write_all",
    "stage_slice",
    "stage_battles",
    "StagedTrainerBattle",
]
