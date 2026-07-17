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
}

_PROBE_TEMPLATE = """\
#include <stddef.h>
#include "global.h"
#include "constants/flags.h"
#include "uranium_embedded_save.h"
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
