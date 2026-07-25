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
}

_PROBE_TEMPLATE = """\
#include <stddef.h>
#include "global.h"
#include "constants/flags.h"
#include "uranium_embedded_save.h"
#include "pokemon.h"
#include "main.h"
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
