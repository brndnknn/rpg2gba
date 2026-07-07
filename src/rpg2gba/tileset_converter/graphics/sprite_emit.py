"""Task 4 wave 2 — `ConvertedSprite` list -> GBA object-event engine artifacts.

Takes the `sprites.py` output (one `ConvertedSprite` per RMXP character sheet: 9x
(32,32,4) uint8 RGBA GBA-order frames) and emits everything the vendored
pokeemerald-expansion fork (`engine/`) needs to compile them as object events:

  1. **Shared-palette quantization** — unit = SHEET (all 9 frames of one sheet
     share one palette), reusing `quantize.build_quantized_tileset` (the
     pipeline's two-phase palette packer) rather than a bespoke one. Every
     opaque pixel is RGB555-snapped first (`quantize.to_5bit`); a sheet whose own
     snapped colour set exceeds 15 (index 0 is always transparent) is median-cut
     reduced to 15 (`_reduce_sprite_to_budget`) — a single GBA 4bpp sprite
     carries exactly one 16-colour palette, so >15 colours is physically
     un-representable and reduction is mandatory (logged loudly). The reduced
     sheets are then packed into at most 4 shared 16-colour palettes. This
     packing is **lossy by design**, exactly as vanilla Emerald shares ~196 NPCs
     across only 4 OBJ palette banks: the real slice's ~18 sheets carry ~137
     distinct colours (far past 4x15 = 60 slots), so the packer merges *similar*
     colours into a shared vocabulary and clusters colour-sharing sheets. The
     module fails loud only on a packer-contract violation (>4 palettes or a
     palette >15 colours — a bug, not a data condition).
  2. **Indexed PNGs** at ``engine/graphics/object_events/pics/uranium/<stem>.png``
     — 288x32 (9 frames of 32x32, left to right in `ConvertedSprite.frames`
     order), embedding the sheet's full assigned 16-colour palette (index 0 =
     transparent placeholder) so the file previews correctly; pixel values are
     raw palette indices (gbagfx converts using the PNG's own indices, not its
     RGB values).
  3. **Seven gitignored `.gen.h` fragments** under `engine/`, textually spliced
     into the committed sentinel hooks a prior session wired up (see
     `reference/task4_npc_gfx_notes.md` "BUILD STATUS checkpoint" and the hook
     comments in each target file). Every fork symbol/macro shape used below
     was verified against the vendored fork on disk (CLAUDE.md §4.7); see the
     per-section comments for citations.

Fork facts this module depends on (grep/read citations, engine/ HEAD 21c24202):

  - ``INCGFX_U16(source, ext, args)`` is a real preproc-recognized directive
    (`tools/preproc/c_file.cpp:463-565`, `tools/scaninc/scaninc.cpp:124-159`),
    NOT the ``INCGFX_U32`` the design notes speculated — every existing
    ``const u16 gObjectEventPic_*[]`` in `object_event_graphics.h` (e.g. the
    Deoxys pics, `object_event_graphics.h:606-608`) uses ``INCGFX_U16`` with
    ``"-mwidth 4 -mheight 4"`` for a 32x32 (4x4-tile) sprite. `INCGFX_U32` is
    only ever `{0}`-stubbed under `#if defined(__APPLE__) || __CYGWIN__ |
    __INTELLISENSE__` in `include/global.h` (IDE fooling, not the real build
    path) — so this module emits `INCGFX_U16`, matching real usage, not the
    notes' guess.
  - ``gObjectEventBaseOam_32x32`` exists verbatim
    (`src/data/object_events/base_oam.h:43`; referenced by e.g.
    `object_event_graphics_info.h:31`).
  - ``sAnimTable_Standard`` exists verbatim (`object_event_anims.h:1223`).
  - ``overworld_ascending_frames(ptr, width, height)`` is a real macro
    (`include/sprite.h:36`): a ONE-element `SpriteFrameImage[]` initializer
    with `relativeFrames = TRUE`, used verbatim by every follower pic table
    (`object_event_pic_tables_followers.h:7-9` etc) for exactly our case (N
    ascending same-size frames in one strip) — the notes' pinned
    ``sPicTable_UraniumX[] = overworld_ascending_frames(ptr, 4, 4)`` shape is
    confirmed correct once wrapped in the one-element array literal.
  - A full field-for-field 32x32 `ObjectEventGraphicsInfo` template was copied
    from `gObjectEventGraphicsInfo_DeoxysD` (`object_event_graphics_info.h:
    6828-6845`; struct layout confirmed at `include/global.fieldmap.h:314-332`):
    tileTag=TAG_NONE, reflectionPaletteTag=OBJ_EVENT_PAL_TAG_NONE, size=512,
    width=height=32, shadowSize=SHADOW_SIZE_M, inanimate=FALSE,
    compressed=FALSE, tracks=TRACKS_FOOT, oam=&gObjectEventBaseOam_32x32,
    subspriteTables=sOamTables_32x32, anims=sAnimTable_Standard,
    affineAnims=gDummySpriteAffineAnimTable. Only paletteTag/paletteSlot/images
    vary per sheet (see `_PALETTE_SLOT` below for why `PALSLOT_NPC_SPECIAL`).
  - ``OBJ_EVENT_PAL_TAG_*`` values occupy 0x1100-0x1133 then jump to
    0x1150-0x116A (Poké Ball tags), then 0x11FF (`OBJ_EVENT_PAL_TAG_NONE`);
    0x7611/0x8001-0x8004 are used far above that
    (`include/constants/event_objects.h:525-621`, confirmed no other header
    defines `OBJ_EVENT_PAL_TAG_*`). 0x1134-0x1137 (right after the last used
    tag `OBJ_EVENT_PAL_TAG_SS_ANNE = 0x1133`, well before the ball block at
    0x1150) is free and used for `OBJ_EVENT_PAL_TAG_URANIUM_0..3`.
  - `NUM_OBJ_EVENT_GFX` is already wired to
    `(388 + NUM_URANIUM_OBJ_EVENT_GFX)` (`include/constants/event_objects.h:
    426-432`), so `OBJ_EVENT_GFX_URANIUM_*` ids start at 388.
  - `gObjectEventGraphicsInfoPointers[]` uses designated initializers
    (`[OBJ_EVENT_GFX_X] = &gObjectEventGraphicsInfo_X,`,
    `object_event_graphics_info_pointers.h:409+`); `sObjectEventSpritePalettes[]`
    uses positional `{data, tag},` entries
    (`src/event_object_movement.c:491+`). Both are matched below.
  - Include order in `event_object_movement.c` (verified 255-490): line 262
    `#include ".../object_event_graphics.h"` (hosts our pics + **palette DATA
    arrays**, hence that's the gen file spliced there) runs well before line
    481 `object_event_graphics_info_pointers.h` (hosts the pointer-entries
    hook, which needs the extern decls hook spliced ABOVE its array — done by
    a separate decls gen file included earlier in that same header) and line
    487 `object_event_graphics_info.h` (hosts the struct defs) and line 490
    `sObjectEventSpritePalettes[]` (hosts the palette *registrations*, which
    only reference the tag + the array symbol already defined via graphics.h).
  - `.paletteSlot` (a bitfield on `ObjectEventGraphicsInfo`) has no runtime
    reader anywhere in `engine/src/*.c` — grepped exhaustively; the design
    notes' claim that the slot-reservation system is dead in this fork
    (`InitObjectEventPalettes` has no callers) matches. `PALSLOT_NPC_SPECIAL`
    is used by 39 existing one-off-palette entries (e.g. `QuintyPlump`,
    `object_event_graphics_info.h:98`) — the closest existing convention for
    "custom dedicated palette tag, not one of the shared NPC_1..4 rotation" —
    so that's what this module fills in, even though nothing reads it.

Deviations from the wave-1 design notes (both intentional, both citation-backed
above): `INCGFX_U16` not `INCGFX_U32`; palette DATA arrays are plain literal
``const u16 name[16] = {0x..., ...};`` initializers (no `.pal`/`.gbapal`
indirection) rather than routed through `INCGFX_U16` + a JASC-PAL file — this
was the pinned brief for *this* module (a code generator has no reason to
round-trip through an external asset file when it already knows the 16 BGR555
words), and it needs no new gitignore entry (unlike the pics, which land under
the already-ignored `engine/graphics/object_events/pics/uranium/`).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from PIL import Image

from rpg2gba.tileset_converter.graphics.quantize import (
    COLORS_PER_PALETTE,
    QuantizeResult,
    _median_cut,
    _nearest,
    build_quantized_tileset,
    to_5bit,
)
from rpg2gba.tileset_converter.graphics.sprites import (
    GBA_FRAME_PX,
    NUM_BREAK_PROP_FRAMES,
    NUM_OUTPUT_FRAMES,
    NUM_PLAYER_OUTPUT_FRAMES,
    ConvertedPlayer,
    ConvertedSprite,
)
from rpg2gba.tileset_converter.npc_gfx import GFX_PREFIX, gfx_constant_for_sheet

logger = logging.getLogger(__name__)

# --- Budgets (CLAUDE.md §4.3 -- these numbers are the one source of truth for
# the sprite-emit budget; nothing else should hardcode 4 or 15). -------------
MAX_PALETTES = 4
MAX_COLORS_PER_SHEET = COLORS_PER_PALETTE  # 15; index 0 is always transparent

# --- Fork facts (verified -- see module docstring for citations). -----------
FIRST_GFX_ID = 388
_PAL_TAG_BASE = 0x1134  # first free OBJ_EVENT_PAL_TAG_* value; see docstring
_PALETTE_SLOT = "PALSLOT_NPC_SPECIAL"  # convention for a one-off custom tag
_FRAME_BYTES = GBA_FRAME_PX * GBA_FRAME_PX // 2  # 512: one 4bpp 32x32 frame

# --- Player sprite (dedicated palette bank, no OBJ_EVENT_GFX_* id) -----------
# The player gets ONE dedicated 16-colour palette bank of its own — never packed
# into the shared NPC palettes — so its tag sits right after the NPC reservation
# block. `_PAL_TAG_BASE..+MAX_PALETTES-1` (0x1134-0x1137) is reserved for
# OBJ_EVENT_PAL_TAG_URANIUM_0..3 regardless of how many the current run actually
# uses (see module docstring), so the player's tag at `+MAX_PALETTES` (0x1138)
# can never collide with an NPC tag even on a run that used fewer NPC palettes.
_PLAYER_PAL_TAG = "OBJ_EVENT_PAL_TAG_URANIUM_PLAYER"
_PLAYER_PAL_TAG_VALUE = _PAL_TAG_BASE + MAX_PALETTES
_PLAYER_IDENT = "UraniumPlayerNormal"  # matches the symbol the lead's pointers-file
                                       # entry already references verbatim
_PLAYER_PALETTE_SLOT = "PALSLOT_PLAYER"
_PLAYER_ANIM_TABLE = "sAnimTable_BrendanMayNormal"
_PLAYER_PICS_STEM = "hero"
# The vanilla Brendan struct the stub #define falls back to on a fresh clone
# (no sprites staged yet) so the tracked pointers file's unconditional reference
# to gObjectEventGraphicsInfo_UraniumPlayerNormal still compiles.
_PLAYER_STUB_FALLBACK = "gObjectEventGraphicsInfo_BrendanNormal"

# --- Player FIELD-MOVE variant (rock smash pose) -----------------------------
# The engine's rock-smash flow swaps the player's gfx to
# OBJ_EVENT_GFX_BRENDAN_FIELD_MOVE and starts anim index 0, then a held
# movement waits until SpriteAnimEnded() (engine/src/fldeff_rocksmash.c:53-79).
# Uranium/RMXP has no field-move pose to show, so this variant is
# field-for-field identical to UraniumPlayerNormal (same pic table, same
# palette tag/slot, same oam/subsprites/size) EXCEPT its `.anims` points at a
# dedicated ONE-tick TERMINATING anim table: pointing it at
# sAnimTable_BrendanMayNormal (or anything else that loops via ANIMCMD_JUMP)
# would leave SpriteAnimEnded() permanently false and softlock the smash.
_PLAYER_FIELD_MOVE_IDENT = "UraniumPlayerFieldMove"
_PLAYER_FIELD_MOVE_ANIM_TABLE = "sUraniumAnimTable_PlayerFieldMove"
# The vanilla field-move struct the stub #define falls back to on a fresh
# clone, mirroring _PLAYER_STUB_FALLBACK's rationale above.
_PLAYER_FIELD_MOVE_STUB_FALLBACK = "gObjectEventGraphicsInfo_BrendanFieldMove"

_PICS_RELDIR = Path("graphics/object_events/pics/uranium")

_GEN_RELPATHS: dict[str, Path] = {
    "constants": Path("include/constants/uranium_event_objects.gen.h"),
    "graphics": Path("src/data/object_events/uranium_object_event_graphics.gen.h"),
    "pic_tables": Path("src/data/object_events/uranium_object_event_pic_tables.gen.h"),
    "graphics_info": Path("src/data/object_events/uranium_object_event_graphics_info.gen.h"),
    "graphics_info_decls": Path(
        "src/data/object_events/uranium_object_event_graphics_info_decls.gen.h"
    ),
    "graphics_info_pointers": Path(
        "src/data/object_events/uranium_object_event_graphics_info_pointers.gen.h"
    ),
    "palettes": Path("src/data/object_events/uranium_object_event_palettes.gen.h"),
}

_GENERATED_HEADER = "// GENERATED by rpg2gba — do not edit; regenerate via emit_sprites().\n"
_STUB_HEADER = (
    "// GENERATED by rpg2gba (stub) — do not edit; the sprite emitter overwrites this file.\n"
)
_CONSTANTS_GUARD = "GUARD_URANIUM_EVENT_OBJECTS_GEN_H"

# Shared verbatim between the stub and the real renderer so the two can never
# drift apart character-for-character (both must match the on-disk hook
# comments in object_event_graphics_info_pointers.h / event_object_movement.c).
_DECLS_COMMENT = (
    "// Included ABOVE gObjectEventGraphicsInfoPointers[] — extern declarations only.\n"
)
_POINTERS_COMMENT = (
    "// Included INSIDE gObjectEventGraphicsInfoPointers[] — entries only, no declarations.\n"
)
_PALETTES_COMMENT = (
    "// Included INSIDE sObjectEventSpritePalettes[] BEFORE the OBJ_EVENT_PAL_TAG_NONE "
    "terminator — entries only.\n"
)


@dataclass
class SpriteEmitResult:
    """What one `emit_sprites` run produced, keyed by sheet name (`ConvertedSprite.name`)
    unless noted otherwise."""

    gfx_constants: dict[str, str]  # sheet name -> OBJ_EVENT_GFX_URANIUM_* constant
    gfx_ids: dict[str, int]  # sheet name -> numeric id (388 + i, sorted-by-constant-name)
    stems: dict[str, str]  # sheet name -> filesystem-safe PNG stem (see `_stem_for_sheet`)
    palette_index: dict[str, int]  # sheet name -> assigned shared-palette index (0-based)
    palette_tags: list[str]  # OBJ_EVENT_PAL_TAG_URANIUM_* names, index-aligned to palettes
    palettes: list[list[tuple[int, int, int]]]  # the shared palettes (<=15 RGB8 colours each)
    files_written: list[Path]
    # OBJ_EVENT_PAL_TAG_URANIUM_PLAYER, if a player was emitted this run.
    player_palette_tag: str | None = None
    # The player's own dedicated <=15-colour palette (never shared with NPCs).
    player_palette: list[tuple[int, int, int]] | None = None


# --- naming --------------------------------------------------------------


def _symbol_suffix(sheet_name: str) -> str:
    """The part of `gfx_constant_for_sheet` after the shared prefix, e.g.
    ``"HGSS_000"`` or ``"PU_CHYINMUNK"`` — already unique (mirrors the
    constant 1:1) and already a valid C identifier fragment (`_naming.to_constant`
    only ever emits `[A-Z0-9_]`)."""
    constant = gfx_constant_for_sheet(sheet_name)
    prefix = f"{GFX_PREFIX}_"
    assert constant.startswith(prefix), f"{constant!r} missing expected prefix {prefix!r}"
    return constant[len(prefix):]


def _stem_for_sheet(sheet_name: str) -> str:
    """Filesystem-safe PNG stem for a sheet: the lowercased constant suffix.

    Deterministic and derived from the SAME string as the gfx constant (so a
    sheet's PNG filename and its `OBJ_EVENT_GFX_URANIUM_*` name are always
    trivially cross-referenceable), and filesystem-safe on every OS since
    `_naming.to_constant` only ever produces `[A-Z0-9_]`."""
    return _symbol_suffix(sheet_name).lower()


def _c_ident(sheet_name: str) -> str:
    """The `Uranium_<SUFFIX>` fragment shared by every per-sheet C symbol
    (`gObjectEventPic_Uranium_X`, `sPicTable_Uranium_X`,
    `gObjectEventGraphicsInfo_Uranium_X`)."""
    return f"Uranium_{_symbol_suffix(sheet_name)}"


# --- colour / palette packing --------------------------------------------


def _validate_sprite_shape(sprite: ConvertedSprite) -> None:
    expected = (
        NUM_BREAK_PROP_FRAMES if sprite.cycle == "break_prop" else NUM_OUTPUT_FRAMES
    )
    if len(sprite.frames) != expected:
        raise ValueError(
            f"{sprite.name}: expected {expected} frames, got {len(sprite.frames)}"
        )
    for i, frame in enumerate(sprite.frames):
        if frame.shape != (GBA_FRAME_PX, GBA_FRAME_PX, 4):
            raise ValueError(
                f"{sprite.name}: frame {i} has shape {frame.shape}, expected "
                f"({GBA_FRAME_PX}, {GBA_FRAME_PX}, 4)"
            )


def _validate_player_shape(player: ConvertedPlayer) -> None:
    if len(player.frames) != NUM_PLAYER_OUTPUT_FRAMES:
        raise ValueError(
            f"player sprite: expected {NUM_PLAYER_OUTPUT_FRAMES} frames, "
            f"got {len(player.frames)}"
        )
    for i, frame in enumerate(player.frames):
        if frame.shape != (GBA_FRAME_PX, GBA_FRAME_PX, 4):
            raise ValueError(
                f"player sprite: frame {i} has shape {frame.shape}, expected "
                f"({GBA_FRAME_PX}, {GBA_FRAME_PX}, 4)"
            )


def _sheet_opaque_colors(sprite: ConvertedSprite) -> np.ndarray:
    """Union of RGB555-snapped opaque colours across all 9 frames of one sheet,
    as an (M,3) uint8 array of distinct display-8-bit colours (`quantize.to_5bit`
    round-trips through 5-bit precision, same convention as the tileset packer)."""
    stack = np.stack(sprite.frames, axis=0)  # (9, 32, 32, 4)
    opaque = stack[..., 3] == 255
    if not opaque.any():
        raise ValueError(f"{sprite.name}: sheet has no opaque pixels in any of its 9 frames")
    return np.unique(to_5bit(stack[..., :3][opaque]), axis=0)


def _reduce_sprite_to_budget(sprite: ConvertedSprite) -> ConvertedSprite:
    """Reduce a sheet to at most `MAX_COLORS_PER_SHEET` distinct colours if it
    exceeds that budget, remapping every opaque pixel to the nearest colour of a
    median-cut palette (reusing `quantize._median_cut`/`_nearest`, the tested
    packer internals — CLAUDE.md §4.3). A single GBA 4bpp sprite carries exactly
    one 16-colour palette (index 0 transparent), so a sheet with more colours is
    physically un-representable and MUST be reduced — there is no lossless
    alternative and no separate palette to spill into (unlike the shared-palette
    packing, where >`MAX_PALETTES` still fails loud). Logs the reduction loudly
    (CLAUDE.md §4.5 — a lossy step is never silent) and is a no-op (returns the
    same object) for a sheet already within budget."""
    colors = _sheet_opaque_colors(sprite)
    if len(colors) <= MAX_COLORS_PER_SHEET:
        return sprite

    stack = np.stack(sprite.frames, axis=0)
    opaque = stack[..., 3] == 255
    palette = _median_cut(stack[..., :3][opaque], MAX_COLORS_PER_SHEET)
    new_frames: list[np.ndarray] = []
    for frame in sprite.frames:
        out = frame.copy()
        fmask = frame[..., 3] == 255
        snapped = to_5bit(frame[..., :3][fmask])
        out[..., :3][fmask] = palette[_nearest(snapped, palette)]
        new_frames.append(out)
    logger.warning(
        "%s: %d distinct colours exceeds the %d-colour single-sprite budget; "
        "median-cut reduced to %d (a GBA 4bpp sprite carries one 16-colour palette)",
        sprite.name, len(colors), MAX_COLORS_PER_SHEET, len(palette),
    )
    return replace(sprite, frames=new_frames)


def _pack_sheet_palettes(
    sprites: list[ConvertedSprite], sheet_colors: list[np.ndarray]
) -> QuantizeResult:
    """Pack `sprites` (unit = whole sheet, all 9 frames sharing one palette) into
    at most `MAX_PALETTES` shared 15-colour palettes with the pipeline's two-phase
    packer (`quantize.build_quantized_tileset` -- CLAUDE.md §4.3, one packer, not a
    bespoke one).

    NPC sprites genuinely cannot pack losslessly, and this is by design: the real
    slice's ~18 sheets carry ~137 distinct colours, far past the 4x15 = 60 slots,
    so -- exactly as vanilla Emerald shares ~196 NPCs across only 4 OBJ palettes --
    the packing is lossy. Phase 1 sheds the excess by merging only *similar*
    colours (dark green -> slightly-different dark green) down to a shared
    vocabulary of `MAX_PALETTES * MAX_COLORS_PER_SHEET`; phase 2 clusters sheets
    that share colours and locally reduces any palette still over 15. Every
    per-sheet input is already <=15 colours (`_reduce_sprite_to_budget` ran
    upstream), and the packer's contract guarantees <=`MAX_PALETTES` palettes of
    <=`MAX_COLORS_PER_SHEET` colours each -- asserted below (a violation would be a
    packer bug, not a data condition; a genuinely-too-many-colours case can't
    arise because median-cut always fits k palettes)."""
    for sprite, colors in zip(sprites, sheet_colors, strict=True):
        if len(colors) > MAX_COLORS_PER_SHEET:  # invariant: _reduce_sprite_to_budget ran
            raise ValueError(
                f"{sprite.name}: {len(colors)} colours after the per-sheet reduction "
                f"still exceeds {MAX_COLORS_PER_SHEET} -- internal invariant violated"
            )

    stacks = [np.stack(s.frames, axis=0) for s in sprites]
    result = build_quantized_tileset(
        stacks,
        max_palettes=MAX_PALETTES,
        colors_per_palette=MAX_COLORS_PER_SHEET,
    )

    if len(result.palettes) > MAX_PALETTES:
        raise ValueError(
            f"packer returned {len(result.palettes)} palettes, exceeds MAX_PALETTES "
            f"{MAX_PALETTES} -- packer contract violated"
        )
    for pi, pal in enumerate(result.palettes):
        if len(pal) > MAX_COLORS_PER_SHEET:
            raise ValueError(
                f"packer palette {pi} has {len(pal)} colours, exceeds "
                f"{MAX_COLORS_PER_SHEET} -- packer contract violated"
            )
    return result


def _quantize_player(player: ConvertedPlayer) -> QuantizeResult:
    """Quantize all 18 player frames (walk+run) onto ONE dedicated 16-colour
    palette (index 0 transparent), reusing the exact same tested packer as the
    shared NPC path (`quantize.build_quantized_tileset` -- CLAUDE.md §4.3) with
    `max_palettes=1` forced: the packer's phase-2 agglomerative merge collapses
    every frame's colour-set bitmask down to a single palette regardless of how
    many distinct colour-sets the 18 frames start with, and phase-1's global
    vocabulary cut plus the per-palette local reduction already handle a union
    over `MAX_COLORS_PER_SHEET`. Fails loud only on a packer-contract violation
    (a bug, not a data condition -- the packer's contract guarantees exactly 1
    palette of <=`MAX_COLORS_PER_SHEET` colours when forced to `max_palettes=1`
    and at least one frame has an opaque pixel, which `_validate_player_shape`
    plus `_anchor`'s all-transparent guard upstream already ensure)."""
    result = build_quantized_tileset(
        list(player.frames), max_palettes=1, colors_per_palette=MAX_COLORS_PER_SHEET
    )
    if len(result.palettes) != 1:
        raise ValueError(
            f"player sprite: packer produced {len(result.palettes)} palettes with "
            f"max_palettes=1 forced -- packer contract violated"
        )
    if len(result.palettes[0]) > MAX_COLORS_PER_SHEET:
        raise ValueError(
            f"player sprite: packer palette has {len(result.palettes[0])} colours, "
            f"exceeds {MAX_COLORS_PER_SHEET} -- packer contract violated"
        )
    return result


# --- PNG emission ----------------------------------------------------------


def _write_sheet_png(path: Path, frames: list[np.ndarray], palette: np.ndarray) -> None:
    """Write one sheet's quantized (32,32,4) RGBA frames (9 for characters, 4 for
    break props) as a `32*len(frames)`x32 indexed PNG at `path`: frames laid out
    left to right, pixels stored as palette indices (index 0 reserved/transparent,
    1..len(palette) the sheet's actual colours in `palette` order) -- gbagfx's
    `.4bpp` conversion reads the PNG's raw indices, not its RGB values, but the
    embedded palette is the real 16-colour assignment so the file also previews
    correctly."""
    width = GBA_FRAME_PX * len(frames)
    indices = np.zeros((GBA_FRAME_PX, width), dtype=np.uint8)
    for i, frame in enumerate(frames):
        opaque = frame[..., 3] == 255
        rgb = frame[..., :3]
        frame_idx = np.zeros((GBA_FRAME_PX, GBA_FRAME_PX), dtype=np.uint8)
        for slot, color in enumerate(palette):
            frame_idx[np.all(rgb == color, axis=-1) & opaque] = slot + 1
        indices[:, i * GBA_FRAME_PX:(i + 1) * GBA_FRAME_PX] = frame_idx

    img = Image.fromarray(indices, mode="P")
    pal_bytes: list[int] = [0, 0, 0]  # index 0: transparent placeholder (black)
    for color in palette:
        pal_bytes += [int(color[0]), int(color[1]), int(color[2])]
    pal_bytes += [0, 0, 0] * (16 - 1 - len(palette))  # pad unused slots to 16 entries
    img.putpalette(pal_bytes)

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(path))


# --- BGR555 packing for the literal palette-data arrays ---------------------


def _pack_bgr555(color: tuple[int, int, int]) -> int:
    """8-bit (r,g,b) (already RGB555-snapped, so `c >> 3` recovers the exact
    5-bit magnitude -- see `quantize.to_5bit`) -> a GBA hardware BGR555 u16."""
    r, g, b = (c >> 3 for c in color)
    return r | (g << 5) | (b << 10)


# --- gen-file content builders ----------------------------------------------


def _render_constants(
    gfx_defines: dict[str, str],
    num_sheets: int,
    palette_tags: list[str],
    *,
    include_player: bool = False,
) -> str:
    """`gfx_defines`: sheet name -> its fully-rendered `#define OBJ_EVENT_GFX_...`
    line, already in constant-name-sorted order (insertion order of the dict).
    `include_player` appends the player's dedicated palette tag define -- no
    `OBJ_EVENT_GFX_*` id or NUM bump, the player is never a selectable gfx id."""
    lines = [
        _GENERATED_HEADER,
        f"#ifndef {_CONSTANTS_GUARD}\n",
        f"#define {_CONSTANTS_GUARD}\n",
        "\n",
    ]
    for define in gfx_defines.values():
        lines.append(f"{define}\n")
    lines.append("\n")
    lines.append(f"#define NUM_URANIUM_OBJ_EVENT_GFX {num_sheets}\n")
    lines.append("\n")
    for i, tag in enumerate(palette_tags):
        lines.append(f"#define {tag} {_PAL_TAG_BASE + i:#06x}\n")
    if include_player:
        lines.append(f"#define {_PLAYER_PAL_TAG} {_PLAYER_PAL_TAG_VALUE:#06x}\n")
    lines.append("\n")
    lines.append(f"#endif // {_CONSTANTS_GUARD}\n")
    return "".join(lines)


def _render_graphics(
    sprites: list[ConvertedSprite],
    stems: dict[str, str],
    pal_words: list[list[int]],
    *,
    player_pal_words: list[int] | None = None,
) -> str:
    lines = [_GENERATED_HEADER, "\n"]
    for i, words in enumerate(pal_words):
        values = ", ".join(f"0x{w:04X}" for w in words)
        lines.append(f"const u16 gUraniumObjEventPal_{i}[16] = {{{values}}};\n")
    if player_pal_words is not None:
        values = ", ".join(f"0x{w:04X}" for w in player_pal_words)
        lines.append(f"const u16 gUraniumObjEventPal_Player[16] = {{{values}}};\n")
    lines.append("\n")
    for sprite in sprites:
        ident = _c_ident(sprite.name)
        stem = stems[sprite.name]
        lines.append(
            f'const u16 gObjectEventPic_{ident}[] = '
            f'INCGFX_U16("{_PICS_RELDIR / stem}.png", ".4bpp", "-mwidth 4 -mheight 4");\n'
        )
    if player_pal_words is not None:
        lines.append(
            f'const u16 gObjectEventPic_{_PLAYER_IDENT}[] = '
            f'INCGFX_U16("{_PICS_RELDIR / _PLAYER_PICS_STEM}.png", ".4bpp", '
            f'"-mwidth 4 -mheight 4");\n'
        )
    return "".join(lines)


def _render_pic_tables(sprites: list[ConvertedSprite], *, include_player: bool = False) -> str:
    lines = [_GENERATED_HEADER]
    for sprite in sprites:
        ident = _c_ident(sprite.name)
        lines.append("\n")
        lines.append(f"static const struct SpriteFrameImage sPicTable_{ident}[] = {{\n")
        lines.append(f"    overworld_ascending_frames(gObjectEventPic_{ident}, 4, 4),\n")
        lines.append("};\n")
    if include_player:
        lines.append("\n")
        lines.append(f"static const struct SpriteFrameImage sPicTable_{_PLAYER_IDENT}[] = {{\n")
        lines.append(
            f"    overworld_ascending_frames(gObjectEventPic_{_PLAYER_IDENT}, 4, 4),\n"
        )
        lines.append("};\n")
    return "".join(lines)


def _render_player_struct(ident: str, anims: str) -> str:
    """One player-variant `ObjectEventGraphicsInfo` struct -- same 32x32
    template as the NPC struct except `.paletteTag`/`.paletteSlot`/`.anims`
    (see module docstring's field-for-field citation) point at the player's
    own dedicated palette, the `PALSLOT_PLAYER` slot, and `anims`. `.images`
    always points at Normal's pic table (`sPicTable_{_PLAYER_IDENT}`) -- every
    player variant shares the one staged hero strip, only the anim table
    differs."""
    lines = [
        f"const struct ObjectEventGraphicsInfo gObjectEventGraphicsInfo_{ident} = {{\n",
        "    .tileTag = TAG_NONE,\n",
        f"    .paletteTag = {_PLAYER_PAL_TAG},\n",
        "    .reflectionPaletteTag = OBJ_EVENT_PAL_TAG_NONE,\n",
        f"    .size = {_FRAME_BYTES},\n",
        f"    .width = {GBA_FRAME_PX},\n",
        f"    .height = {GBA_FRAME_PX},\n",
        f"    .paletteSlot = {_PLAYER_PALETTE_SLOT},\n",
        "    .shadowSize = SHADOW_SIZE_M,\n",
        "    .inanimate = FALSE,\n",
        "    .compressed = FALSE,\n",
        "    .tracks = TRACKS_FOOT,\n",
        "    .oam = &gObjectEventBaseOam_32x32,\n",
        "    .subspriteTables = sOamTables_32x32,\n",
        f"    .anims = {anims},\n",
        f"    .images = sPicTable_{_PLAYER_IDENT},\n",
        "    .affineAnims = gDummySpriteAffineAnimTable,\n",
        "};\n",
    ]
    return "".join(lines)


def _render_player_graphics_info() -> str:
    """The player's normal-pose `ObjectEventGraphicsInfo`, walk+run anims
    (`sAnimTable_BrendanMayNormal`, the walk+run table, not the NPC-only
    `sAnimTable_Standard`)."""
    return "\n" + _render_player_struct(_PLAYER_IDENT, _PLAYER_ANIM_TABLE)


def _render_player_field_move_graphics_info() -> str:
    """The player's FIELD-MOVE variant: rock smash swaps the player's gfx to
    this struct and starts anim index 0, then waits on `SpriteAnimEnded()`
    (`engine/src/fldeff_rocksmash.c:53-79`). Uranium/RMXP has no field-move
    pose, so the anim is a 1-tick terminating table -- an invisible blip
    rather than a hang -- emitted here (anim data before the struct that
    references it) rather than reusing Normal's looping walk table, which
    would never satisfy `SpriteAnimEnded()` and softlock the held movement."""
    lines = [
        "\n",
        "// FieldMove: a 1-tick terminating anim (Uranium/RMXP has no field-move\n",
        "// pose) so the rock-smash pose is an invisible blip; Normal's looping\n",
        "// sAnimTable_BrendanMayNormal would never satisfy SpriteAnimEnded() and\n",
        "// would softlock the held movement (engine/src/fldeff_rocksmash.c:53-79).\n",
        "static const union AnimCmd sUraniumAnim_PlayerFieldMove[] = {\n",
        "    ANIMCMD_FRAME(0, 1),\n",
        "    ANIMCMD_END,\n",
        "};\n",
        "static const union AnimCmd *const sUraniumAnimTable_PlayerFieldMove[] = {\n",
        "    sUraniumAnim_PlayerFieldMove,\n",
        "};\n",
        "\n",
        _render_player_struct(_PLAYER_FIELD_MOVE_IDENT, _PLAYER_FIELD_MOVE_ANIM_TABLE),
    ]
    return "".join(lines)


def _render_graphics_info(
    sprites: list[ConvertedSprite],
    palette_tags: dict[str, str],
    *,
    include_player: bool = False,
) -> str:
    lines = [_GENERATED_HEADER]
    for sprite in sprites:
        ident = _c_ident(sprite.name)
        lines.append("\n")
        lines.append(
            f"const struct ObjectEventGraphicsInfo gObjectEventGraphicsInfo_{ident} = {{\n"
        )
        lines.append("    .tileTag = TAG_NONE,\n")
        lines.append(f"    .paletteTag = {palette_tags[sprite.name]},\n")
        lines.append("    .reflectionPaletteTag = OBJ_EVENT_PAL_TAG_NONE,\n")
        lines.append(f"    .size = {_FRAME_BYTES},\n")
        lines.append(f"    .width = {GBA_FRAME_PX},\n")
        lines.append(f"    .height = {GBA_FRAME_PX},\n")
        lines.append(f"    .paletteSlot = {_PALETTE_SLOT},\n")
        if sprite.cycle == "break_prop":
            # Vanilla BreakableRock semantics: rock_smash_break plays
            # ANIM_REMOVE_OBSTACLE and waits for SpriteAnimEnded — the table's
            # index 1 must be the finite sAnim_RockBreak, not Standard's
            # looping walk anim (which stalls the smash forever).
            lines.append("    .shadowSize = SHADOW_SIZE_S,\n")
            lines.append("    .inanimate = TRUE,\n")
            lines.append("    .compressed = FALSE,\n")
            lines.append("    .tracks = TRACKS_NONE,\n")
            lines.append("    .oam = &gObjectEventBaseOam_32x32,\n")
            lines.append("    .subspriteTables = sOamTables_32x32,\n")
            lines.append("    .anims = sAnimTable_BreakableRock,\n")
        else:
            lines.append("    .shadowSize = SHADOW_SIZE_M,\n")
            lines.append("    .inanimate = FALSE,\n")
            lines.append("    .compressed = FALSE,\n")
            lines.append("    .tracks = TRACKS_FOOT,\n")
            lines.append("    .oam = &gObjectEventBaseOam_32x32,\n")
            lines.append("    .subspriteTables = sOamTables_32x32,\n")
            lines.append("    .anims = sAnimTable_Standard,\n")
        lines.append(f"    .images = sPicTable_{ident},\n")
        lines.append("    .affineAnims = gDummySpriteAffineAnimTable,\n")
        lines.append("};\n")
    if include_player:
        lines.append(_render_player_graphics_info())
        lines.append(_render_player_field_move_graphics_info())
    return "".join(lines)


def _render_graphics_info_decls(
    sprites: list[ConvertedSprite], *, include_player: bool = False
) -> str:
    lines = [_GENERATED_HEADER, _DECLS_COMMENT]
    for sprite in sprites:
        ident = _c_ident(sprite.name)
        lines.append(
            f"extern const struct ObjectEventGraphicsInfo gObjectEventGraphicsInfo_{ident};\n"
        )
    if include_player:
        lines.append(
            f"extern const struct ObjectEventGraphicsInfo "
            f"gObjectEventGraphicsInfo_{_PLAYER_IDENT};\n"
        )
        lines.append(
            f"extern const struct ObjectEventGraphicsInfo "
            f"gObjectEventGraphicsInfo_{_PLAYER_FIELD_MOVE_IDENT};\n"
        )
    return "".join(lines)


def _render_graphics_info_pointers(
    sprites: list[ConvertedSprite], gfx_names: dict[str, str]
) -> str:
    # Deliberately no player branch here: the lead session repoints the vanilla
    # [OBJ_EVENT_GFX_BRENDAN_NORMAL] pointers-array entry at
    # gObjectEventGraphicsInfo_UraniumPlayerNormal directly in the tracked
    # pointers file, so this generated fragment never references the player.
    lines = [_GENERATED_HEADER, _POINTERS_COMMENT]
    for sprite in sprites:
        ident = _c_ident(sprite.name)
        gfx_name = gfx_names[sprite.name]
        lines.append(f"[{gfx_name}] = &gObjectEventGraphicsInfo_{ident},\n")
    return "".join(lines)


def _render_palettes(palette_tags: list[str], *, include_player: bool = False) -> str:
    lines = [_GENERATED_HEADER, _PALETTES_COMMENT]
    for i, tag in enumerate(palette_tags):
        lines.append(f"{{gUraniumObjEventPal_{i}, {tag}}},\n")
    if include_player:
        lines.append(f"{{gUraniumObjEventPal_Player, {_PLAYER_PAL_TAG}}},\n")
    return "".join(lines)


# --- stub writer -------------------------------------------------------------


def write_stub_gen_files(engine_root: Path) -> None:
    """Write all 7 `.gen.h` fragments in their empty-conversion form (NUM 0,
    empty bodies) so a fresh clone / no-sprites-staged build compiles cleanly
    against the committed sentinel hooks. Idempotent and byte-stable; does NOT
    require any sprites and never reads `emit_sprites` state."""
    engine_root = Path(engine_root)
    contents: dict[str, str] = {
        "constants": (
            _STUB_HEADER
            + f"#ifndef {_CONSTANTS_GUARD}\n"
            + f"#define {_CONSTANTS_GUARD}\n"
            + "\n"
            + "#define NUM_URANIUM_OBJ_EVENT_GFX 0\n"
            + "\n"
            + f"#endif // {_CONSTANTS_GUARD}\n"
        ),
        "graphics": _STUB_HEADER,
        "pic_tables": _STUB_HEADER,
        "graphics_info": _STUB_HEADER,
        # The tracked pointers file (owned by the lead session) references
        # gObjectEventGraphicsInfo_UraniumPlayerNormal unconditionally, and the
        # lead's field-move pointer entry references
        # gObjectEventGraphicsInfo_UraniumPlayerFieldMove unconditionally too, so a
        # fresh clone with no sprites staged needs SOMETHING both names resolve to;
        # alias each to its vanilla struct. The REAL decls output
        # (_render_graphics_info_decls) emits the true `extern` declarations instead
        # and never also emits these #defines.
        "graphics_info_decls": (
            _STUB_HEADER
            + f"#define gObjectEventGraphicsInfo_{_PLAYER_IDENT} {_PLAYER_STUB_FALLBACK}\n"
            + f"#define gObjectEventGraphicsInfo_{_PLAYER_FIELD_MOVE_IDENT} "
            + f"{_PLAYER_FIELD_MOVE_STUB_FALLBACK}\n"
        ),
        "graphics_info_pointers": _STUB_HEADER + _POINTERS_COMMENT,
        "palettes": _STUB_HEADER + _PALETTES_COMMENT,
    }
    for key, relpath in _GEN_RELPATHS.items():
        path = engine_root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents[key], encoding="utf-8")


# --- main entry point --------------------------------------------------------


def emit_sprites(
    sprites: list[ConvertedSprite],
    engine_root: Path,
    *,
    player: ConvertedPlayer | None = None,
) -> SpriteEmitResult:
    """Quantize + emit `sprites` as GBA object-event engine artifacts under
    `engine_root` (the 7 `.gen.h` fragments + one indexed PNG per sheet).

    `player`, if given, is emitted alongside the NPC sheets into the SAME 7 gen
    files: its own dedicated 16-colour palette bank (never packed into the
    shared NPC palettes -- CLAUDE.md §4.3, one packer, applied once more with
    `max_palettes=1` forced, see `_quantize_player`), its own indexed strip PNG
    (`hero.png`), and its own `ObjectEventGraphicsInfo`/pic-table/palette-tag
    entries. It deliberately gets no `OBJ_EVENT_GFX_URANIUM_*` id and no
    `gObjectEventGraphicsInfoPointers[]` entry -- the lead session repoints the
    vanilla `[OBJ_EVENT_GFX_BRENDAN_NORMAL]` entry at
    `gObjectEventGraphicsInfo_UraniumPlayerNormal` directly. A second struct,
    `gObjectEventGraphicsInfo_UraniumPlayerFieldMove`, is always emitted
    alongside it (same pic table/palette tag, its own 1-tick terminating anim
    table -- see `_render_player_field_move_graphics_info`) so the lead's
    `[OBJ_EVENT_GFX_BRENDAN_FIELD_MOVE]` pointer entry has a non-softlocking
    target for the rock-smash pose.

    Deterministic: sheets are processed in `name`-sorted order for palette
    packing and PNG emission, and `OBJ_EVENT_GFX_URANIUM_*` ids are assigned in
    constant-name-sorted order (388 + i) -- same inputs always produce
    byte-identical files (CLAUDE.md §4.2). Fails loud (raises, writes nothing)
    on a duplicate sheet name, a duplicate minted constant, a malformed
    `ConvertedSprite`/`ConvertedPlayer`, a single sheet needing >15 colours, or
    the palette packer needing more than `MAX_PALETTES` shared palettes.
    """
    if not sprites and player is None:
        raise ValueError("emit_sprites requires at least one sprite or a player")

    for sprite in sprites:
        _validate_sprite_shape(sprite)
    if player is not None:
        _validate_player_shape(player)

    ordered = sorted(sprites, key=lambda s: s.name)
    seen_names: set[str] = set()
    gfx_constants: dict[str, str] = {}
    for sprite in ordered:
        if sprite.name in seen_names:
            raise ValueError(f"duplicate sheet name {sprite.name!r}")
        seen_names.add(sprite.name)
        constant = gfx_constant_for_sheet(sprite.name)
        collision = next((n for n, c in gfx_constants.items() if c == constant), None)
        if collision is not None:
            raise ValueError(
                f"{sprite.name!r} and {collision!r} both normalize to gfx constant "
                f"{constant!r}"
            )
        gfx_constants[sprite.name] = constant

    # A single 4bpp sprite can hold at most MAX_COLORS_PER_SHEET colours; reduce
    # any over-budget sheet (loudly) BEFORE packing so the per-sheet guard below
    # only ever sees representable sheets and the shared-palette overflow guard
    # stays the sole fail-loud (there IS an alternative there: fewer shared sheets).
    ordered = [_reduce_sprite_to_budget(s) for s in ordered]

    stems = {s.name: _stem_for_sheet(s.name) for s in ordered}

    sheet_colors = [_sheet_opaque_colors(s) for s in ordered]
    result = _pack_sheet_palettes(ordered, sheet_colors)
    n_palettes = len(result.palettes)
    palette_tags = [f"OBJ_EVENT_PAL_TAG_URANIUM_{i}" for i in range(n_palettes)]
    palette_index = {s.name: result.tile_palette[i] for i, s in enumerate(ordered)}
    palette_tag_of = {s.name: palette_tags[palette_index[s.name]] for s in ordered}
    palettes_out: list[list[tuple[int, int, int]]] = [
        [(int(c[0]), int(c[1]), int(c[2])) for c in pal] for pal in result.palettes
    ]
    # Slot 0 is the transparent placeholder: the PNGs index opaque colours at
    # 1..15 (_write_sheet_png), so the hardware palette must carry them at the
    # same positions — omitting the placeholder shifts every colour down one.
    pal_words = [[0x0000] + [_pack_bgr555(c) for c in pal] for pal in palettes_out]

    by_constant = sorted(ordered, key=lambda s: gfx_constants[s.name])
    gfx_ids = {s.name: FIRST_GFX_ID + i for i, s in enumerate(by_constant)}
    gfx_defines = {
        s.name: f"#define {gfx_constants[s.name]} {gfx_ids[s.name]}" for s in by_constant
    }

    engine_root = Path(engine_root)
    pics_dir = engine_root / _PICS_RELDIR
    files_written: list[Path] = []
    for i, sprite in enumerate(ordered):
        pal_idx = palette_index[sprite.name]
        palette = result.palettes[pal_idx]
        frames = list(result.quantized[i])
        png_path = pics_dir / f"{stems[sprite.name]}.png"
        _write_sheet_png(png_path, frames, palette)
        files_written.append(png_path)

    player_palette_out: list[tuple[int, int, int]] | None = None
    player_pal_words: list[int] | None = None
    if player is not None:
        player_result = _quantize_player(player)
        player_palette = player_result.palettes[0]
        player_palette_out = [(int(c[0]), int(c[1]), int(c[2])) for c in player_palette]
        # Same slot-0-transparent convention as the shared NPC palettes.
        player_pal_words = [0x0000] + [_pack_bgr555(c) for c in player_palette_out]
        player_png_path = pics_dir / f"{_PLAYER_PICS_STEM}.png"
        _write_sheet_png(player_png_path, list(player_result.quantized), player_palette)
        files_written.append(player_png_path)

    gen_contents = {
        "constants": _render_constants(
            gfx_defines, len(ordered), palette_tags, include_player=player is not None
        ),
        "graphics": _render_graphics(
            ordered, stems, pal_words, player_pal_words=player_pal_words
        ),
        "pic_tables": _render_pic_tables(ordered, include_player=player is not None),
        "graphics_info": _render_graphics_info(
            ordered, palette_tag_of, include_player=player is not None
        ),
        "graphics_info_decls": _render_graphics_info_decls(
            ordered, include_player=player is not None
        ),
        "graphics_info_pointers": _render_graphics_info_pointers(ordered, gfx_constants),
        "palettes": _render_palettes(palette_tags, include_player=player is not None),
    }
    for key, relpath in _GEN_RELPATHS.items():
        path = engine_root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(gen_contents[key], encoding="utf-8")
        files_written.append(path)

    logger.debug(
        "emit_sprites: %d sheets -> %d shared palettes, player=%s, %d files written",
        len(ordered), n_palettes, player is not None, len(files_written),
    )

    return SpriteEmitResult(
        gfx_constants=gfx_constants,
        gfx_ids=gfx_ids,
        stems=stems,
        palette_index=palette_index,
        palette_tags=palette_tags,
        palettes=palettes_out,
        files_written=files_written,
        player_palette_tag=_PLAYER_PAL_TAG if player is not None else None,
        player_palette=player_palette_out,
    )
