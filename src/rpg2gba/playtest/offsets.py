"""Struct offsets and constants, probe-compiled from the engine's own headers.

The engine ELF carries no usable DWARF (only startup objects are built with
-g), so offsets are obtained by compiling a tiny probe against
$RPG2GBA_POKEEMERALD/include with the ROM's exact ABI flags (-mabi=apcs-gnu
changes struct layout — the flags below must track the engine Makefile) and
reading the values back as `nm -S` symbol sizes. This guarantees the numbers
come from the same struct definitions the ROM was built from.
"""
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

from .symbols import DEVKITARM_BIN

# Matches the engine Makefile's layout-relevant CFLAGS/CPPFLAGS (Makefile:159,170).
_CFLAGS = [
    "-mthumb", "-mthumb-interwork", "-mabi=apcs-gnu", "-mtune=arm7tdmi",
    "-march=armv4t", "-O0", "-Wno-trigraphs", "-std=gnu17",
    "-DMODERN=1", "-DTESTING=0", "-DEMERALD",
]

# name -> C expression. `off_`/`val_` prefix is only a reading convention;
# every entry is emitted as `const char name[(expr) + 1];` and read back as
# size - 1, so expressions that may legitimately be 0 stay representable.
_PROBE_ENTRIES: dict[str, str] = {
    "off_sb1_pos": "offsetof(struct SaveBlock1, pos)",
    "off_sb1_location": "offsetof(struct SaveBlock1, location)",
    "off_sb1_flags": "offsetof(struct SaveBlock1, flags)",
    "off_sb1_vars": "offsetof(struct SaveBlock1, vars)",
    "flag_sys_b_dash": "FLAG_SYS_B_DASH",
    "off_es_sb1": "offsetof(struct UraniumEmbeddedSave, sb1)",
    "off_es_sb2": "offsetof(struct UraniumEmbeddedSave, sb2)",
    "off_es_sb3": "offsetof(struct UraniumEmbeddedSave, sb3)",
    "off_es_storage": "offsetof(struct UraniumEmbeddedSave, storage)",
    "sizeof_es": "sizeof(struct UraniumEmbeddedSave)",
    "sizeof_sb1": "sizeof(struct SaveBlock1)",
    "sizeof_sb2": "sizeof(struct SaveBlock2)",
    "sizeof_sb3": "sizeof(struct SaveBlock3)",
    "sizeof_storage": "sizeof(struct PokemonStorage)",
    "embedded_save_magic": "URANIUM_EMBEDDED_SAVE_MAGIC",
    "vars_start": "VARS_START",
    # -- battle mini-driver (playtest/battle.py) -----------------------------
    # struct Pokemon (include/pokemon.h): unencrypted party-struct tail.
    "off_pkmn_box": "offsetof(struct Pokemon, box)",
    "off_pkmn_hp": "offsetof(struct Pokemon, hp)",
    "off_pkmn_maxhp": "offsetof(struct Pokemon, maxHP)",
    "off_pkmn_level": "offsetof(struct Pokemon, level)",
    "sizeof_pkmn": "sizeof(struct Pokemon)",
    # struct BoxPokemon (include/pokemon.h): encrypted substruct block.
    "off_boxpkmn_personality": "offsetof(struct BoxPokemon, personality)",
    "off_boxpkmn_otid": "offsetof(struct BoxPokemon, otId)",
    "off_boxpkmn_secure": "offsetof(struct BoxPokemon, secure)",
    "val_num_substruct_bytes": "NUM_SUBSTRUCT_BYTES",
    # struct BattlePokemon (include/pokemon.h): in-battle mon copy — hp here
    # is what turn resolution/faint checks actually read, not struct
    # Pokemon's hp. NOTE: the header's `/*0x29*/` comment for `hp` is stale;
    # the probed value differs (see battle.py's in-battle detection notes).
    "off_battlepkmn_hp": "offsetof(struct BattlePokemon, hp)",
    "sizeof_battlepkmn": "sizeof(struct BattlePokemon)",
    # struct Main (include/main.h): gMain.callback2, for in-battle detection.
    "off_main_callback2": "offsetof(struct Main, callback2)",
    # -- walk_to's route planner (emulator.py) -------------------------------
    # gBackupMapLayout is the grid the engine's own MapGridGetCollisionAt
    # reads, so planning over it plans over exactly what the player can walk
    # on -- including script-applied metatile changes a static map.bin read
    # would miss. Its coordinates carry MAP_OFFSET; SaveBlock1.pos does not.
    "off_backup_width": "offsetof(struct BackupMapLayout, width)",
    "off_backup_height": "offsetof(struct BackupMapLayout, height)",
    "off_backup_map": "offsetof(struct BackupMapLayout, map)",
    "val_map_offset": "MAP_OFFSET",
    # gMapHeader.mapLayout's own dimensions: the authority on which map the
    # backup grid *should* be describing. A warp writes SaveBlock1.location
    # (ApplyCurrentWarp, overworld.c:620) long before it rebuilds the grid
    # (InitMap inside LoadMapFromWarp, overworld.c:982), so "the map changed"
    # and "the grid changed" are separate events and must be checked apart.
    # struct Task (include/task.h): scanned exactly as FuncIsActiveTask scans
    # it, to answer "is a yes/no menu on screen right now?" -- the one piece
    # of menu state the harness could never observe.
    "off_task_func": "offsetof(struct Task, func)",
    "off_task_is_active": "offsetof(struct Task, isActive)",
    "sizeof_task": "sizeof(struct Task)",
    "val_num_tasks": "NUM_TASKS",
    "off_mapheader_maplayout": "offsetof(struct MapHeader, mapLayout)",
    "off_maplayout_width": "offsetof(struct MapLayout, width)",
    "off_maplayout_height": "offsetof(struct MapLayout, height)",
    # `_plan_route`'s grass-aware cost (emulator.py): the same pointer chain
    # `GetAttributeByMetatileIdAndMapLayout` (engine/src/fieldmap.c) walks to
    # turn a `gBackupMapLayout` block's packed metatile id into a behavior
    # byte -- primary/secondary `struct Tileset`, each tileset's
    # `metatileAttributes` array, and `isFrlg` (Uranium's converter emits the
    # non-FRLG/Emerald attribute format, but this is read live rather than
    # assumed, so it stays correct if that ever changes).
    "off_maplayout_primarytileset": "offsetof(struct MapLayout, primaryTileset)",
    "off_maplayout_secondarytileset": "offsetof(struct MapLayout, secondaryTileset)",
    "off_maplayout_isfrlg": "offsetof(struct MapLayout, isFrlg)",
    "off_tileset_metatileattributes": "offsetof(struct Tileset, metatileAttributes)",
    # gMapHeader.events -> warps: tiles a route must not step onto, or the
    # walk silently relocates the scenario to another map.
    "off_mapheader_events": "offsetof(struct MapHeader, events)",
    "off_mapevents_warpcount": "offsetof(struct MapEvents, warpCount)",
    "off_mapevents_warps": "offsetof(struct MapEvents, warps)",
    "off_warpevent_x": "offsetof(struct WarpEvent, x)",
    "off_warpevent_y": "offsetof(struct WarpEvent, y)",
    "sizeof_warpevent": "sizeof(struct WarpEvent)",
    # -- text printer state (emulator.text_printing) -------------------------
    # `sFirstTextPrinter`'s list, walked exactly as IsTextPrinterActiveOnWindow
    # walks it, to answer "is the message box still typing?" -- the difference
    # between photographing "See you later, R" and "See you later, RED!".
    # `state` is the render state machine: HANDLE_CHAR means glyphs are still
    # being drawn; the WAIT/CLEAR/SCROLL_START states are a fully-drawn page
    # sitting on the down-arrow waiting for the player. NB `active` is *not*
    # the signal -- it stays TRUE for a printer's whole life and only clears at
    # RENDER_FINISH, when the node is freed off the list anyway.
    "off_printer_type": "offsetof(struct TextPrinter, printerTemplate.type)",
    "off_printer_window_id": "offsetof(struct TextPrinter, printerTemplate.windowId)",
    "off_printer_state": "offsetof(struct TextPrinter, state)",
    "off_printer_next": "offsetof(struct TextPrinter, nextPrinter)",
    "val_window_text_printer": "WINDOW_TEXT_PRINTER",
    "val_render_state_handle_char": "RENDER_STATE_HANDLE_CHAR",
    "val_render_state_wait": "RENDER_STATE_WAIT",
    "val_render_state_clear": "RENDER_STATE_CLEAR",
    "val_render_state_scroll_start": "RENDER_STATE_SCROLL_START",
    # -- player-object liveness (stamp.verify_stamped_rom) -------------------
    # struct ObjectEvent (global.fieldmap.h): a stamped seed blob only counts
    # if the object event it revives is actually alive on boot -- see
    # dump_save_blocks's docstring for why the mirror can go stale. `active`
    # is the *first* bitfield in the struct (`u32 active:1; ...`, byte 0 of a
    # 4-byte little-endian bitfield unit) so GCC refuses `offsetof` on it
    # (bitfields aren't addressable); there's nothing to probe. It is not
    # hardcoded blind, though -- verified empirically against a pristine
    # new-game boot: gObjectEvents[0]'s first byte read 0xc1 (0b1100_0001),
    # bit 0 set, matching the engine's own `active` state for a spawned
    # player. If a future engine change ever reorders the bitfield, that
    # assertion (not this constant) is what will catch it.
    "off_objevent_currentcoords": "offsetof(struct ObjectEvent, currentCoords)",
    "off_objevent_graphicsid": "offsetof(struct ObjectEvent, graphicsId)",
    "off_objevent_spriteid": "offsetof(struct ObjectEvent, spriteId)",
    "sizeof_objevent": "sizeof(struct ObjectEvent)",
    "off_playeravatar_flags": "offsetof(struct PlayerAvatar, flags)",
    "off_playeravatar_objecteventid": "offsetof(struct PlayerAvatar, objectEventId)",
    "off_playeravatar_spriteid": "offsetof(struct PlayerAvatar, spriteId)",
    # -- object-event observability (emulator.object_events, ROM_TEST_DEV.md
    # "Harness cannot see NPCs") -------------------------------------------
    # struct ObjectEvent (global.fieldmap.h:249-312): non-bitfield fields are
    # probed directly. `localId` (0x08) is the object's *compiled* local id
    # (its 1-based position in the map JSON's object_events array after
    # tileset_converter/local_id_remap.py's remap), not necessarily the RMXP
    # event id.
    "off_objevent_localid": "offsetof(struct ObjectEvent, localId)",
    "off_objevent_movementtype": "offsetof(struct ObjectEvent, movementType)",
    # A sight trainer's own live sight range -- the exact `range` value
    # `GetTrainerApproachDistance`'s per-direction functions bound the
    # approach distance to (engine/src/trainer_see.c:636-660); route1.py's
    # `_sight_lane_tiles` reads this live rather than assuming a fixed scan
    # depth for every trainer.
    "off_objevent_trainerrange_berrytreeid":
        "offsetof(struct ObjectEvent, trainerRange_berryTreeId)",
    # Anchor used only to sanity-check OBJEVENT_FACING_BYTE_OFFSET below: the
    # header comments mark facingDirection/movementDirection/range as a single
    # 2-byte block at 0x18-0x19 (global.fieldmap.h:293-299), immediately
    # followed by fieldEffectSpriteId at 0x1A (global.fieldmap.h:300). If a
    # future engine change grows that block, this probed value moves and the
    # hardcoded facing offset below is what will look wrong.
    "off_objevent_fieldeffectspriteid": "offsetof(struct ObjectEvent, fieldEffectSpriteId)",
    # OBJECT_EVENTS_COUNT (constants/global.h:93): size of gObjectEvents[].
    "val_object_events_count": "OBJECT_EVENTS_COUNT",
    # Direction enum (constants/global.h:205-209) as stored in
    # ObjectEvent.facingDirection. Probed rather than hardcoded so a renumber
    # upstream fails loud instead of silently mis-decoding facing.
    "val_dir_south": "DIR_SOUTH",
    "val_dir_north": "DIR_NORTH",
    "val_dir_west": "DIR_WEST",
    "val_dir_east": "DIR_EAST",
}

# `facingDirection`/`movementDirection` (global.fieldmap.h:293-294) are a
# packed `u16 facingDirection:4; u16 movementDirection:4;` bitfield, so (like
# `active` above) GCC refuses `offsetof` on the field itself. The header's own
# byte-offset comments pin the containing byte at 0x18, with
# facingDirection declared first -- and ARM/GCC little-endian bitfield
# allocation packs the first-declared field into the low bits of the unit --
# so facingDirection is the low nibble of byte 0x18, movementDirection the
# high nibble. This is the same offset the wider pokeemerald-devtools/RAM-watch
# community has used against this struct for years. Cross-checked here via
# `off_objevent_fieldeffectspriteid`: that field is explicitly commented
# 0x1A, two bytes after 0x18, exactly matching "facingDirection +
# movementDirection + rangeX/rangeY all fit in bytes 0x18-0x19" -- if a future
# engine change disagrees, `probe_offsets`'s anchor value will no longer be
# `OBJEVENT_FACING_BYTE_OFFSET + 2` and callers should treat that as a sign
# this constant needs re-deriving.
OBJEVENT_FACING_BYTE_OFFSET = 0x18
OBJEVENT_FACING_MASK = 0x0F

# `active`'s containing byte and bit, within a `struct ObjectEvent` -- see the
# comment on the probe table above for why this can't come from `offsetof`.
# Empirically verified (2026-08-07) against a pristine new-game boot.
OBJEVENT_ACTIVE_BYTE_OFFSET = 0
OBJEVENT_ACTIVE_BIT_MASK = 0x1

_PROBE_TEMPLATE = """\
#include <stddef.h>
#include "global.h"
#include "constants/flags.h"
#include "uranium_embedded_save.h"
#include "pokemon.h"
#include "main.h"
#include "fieldmap.h"
#include "text.h"
#include "task.h"
{entries}
"""


def probe_offsets(engine: Path) -> dict[str, int]:
    """Compile the probe against `engine`'s headers; return name -> value."""
    gcc = DEVKITARM_BIN / "arm-none-eabi-gcc"
    nm = DEVKITARM_BIN / "arm-none-eabi-nm"
    src = _PROBE_TEMPLATE.format(entries="\n".join(
        f"const char {name}[({expr}) + 1];"
        for name, expr in _PROBE_ENTRIES.items()
    ))
    with tempfile.TemporaryDirectory() as tmp:
        c_path = Path(tmp) / "probe.c"
        o_path = Path(tmp) / "probe.o"
        c_path.write_text(src, encoding="utf-8")
        subprocess.run(
            [str(gcc), "-c", *_CFLAGS, "-iquote", str(engine / "include"),
             "-o", str(o_path), str(c_path)],
            capture_output=True, text=True, check=True,
        )
        out = subprocess.run(
            [str(nm), "-S", str(o_path)],
            capture_output=True, text=True, check=True,
        ).stdout
    values: dict[str, int] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[3] in _PROBE_ENTRIES:
            values[parts[3]] = int(parts[1], 16) - 1
    missing = _PROBE_ENTRIES.keys() - values.keys()
    if missing:
        raise RuntimeError(f"probe compiled but symbols missing from nm: {missing}")
    return values


_CONSTANT_PROBE_TEMPLATE = """\
#include <stddef.h>
#include "global.h"
#include "constants/flags.h"
#include "constants/vars.h"
#include "data/scripts/uranium_flags.h"
#include "fieldmap.h"
#include "constants/metatile_behaviors.h"
{entries}
"""


def probe_constants(engine: Path, names: Sequence[str]) -> dict[str, int]:
    """Resolve `names` (FLAG_*/VAR_* macros) through the real preprocessor.

    Mirrors `probe_offsets`: same CFLAGS, same gcc/nm round-trip, same
    `size - 1` encoding. Unlike `_PROBE_ENTRIES`, `names` are real
    `FLAG_*`/`VAR_*` macros, so the declarator identifier can't be the macro
    itself (it would itself expand) — symbols are index-mangled (`c0`, `c1`,
    ...) and mapped back to `names` by position.
    """
    header = engine / "data" / "scripts" / "uranium_flags.h"
    if not header.exists():
        raise RuntimeError(
            f"{header} is missing. It is a generated file, produced by "
            "scripts/assemble_pathfinder.py (FlagRegistry.dump_header) — "
            "run the assembler against this engine build before probing "
            "flag/var constants."
        )
    gcc = DEVKITARM_BIN / "arm-none-eabi-gcc"
    nm = DEVKITARM_BIN / "arm-none-eabi-nm"
    mangled = [f"c{i}" for i in range(len(names))]
    src = _CONSTANT_PROBE_TEMPLATE.format(entries="\n".join(
        f"const char {sym}[({name}) + 1];"
        for sym, name in zip(mangled, names)
    ))
    with tempfile.TemporaryDirectory() as tmp:
        c_path = Path(tmp) / "probe.c"
        o_path = Path(tmp) / "probe.o"
        c_path.write_text(src, encoding="utf-8")
        result = subprocess.run(
            [str(gcc), "-c", *_CFLAGS,
             "-iquote", str(engine), "-iquote", str(engine / "include"),
             "-o", str(o_path), str(c_path)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"probe_constants: failed to compile probe for {list(names)}:\n"
                f"{result.stderr}"
            )
        out = subprocess.run(
            [str(nm), "-S", str(o_path)],
            capture_output=True, text=True, check=True,
        ).stdout
    by_symbol: dict[str, int] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[3] in mangled:
            by_symbol[parts[3]] = int(parts[1], 16) - 1
    values: dict[str, int] = {}
    missing: list[str] = []
    for sym, name in zip(mangled, names):
        if sym in by_symbol:
            values[name] = by_symbol[sym]
        else:
            missing.append(name)
    if missing:
        raise RuntimeError(
            f"probe_constants: compiled but symbols missing from nm output "
            f"for names: {missing}"
        )
    return values
