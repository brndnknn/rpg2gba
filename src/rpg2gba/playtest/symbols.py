"""Symbol addresses for the engine build under test.

Globals come straight from the GNU ld map file. Statics (absent from the map)
are recovered from the disassembly of a global accessor function: at this
codebase's optimization settings the accessor is `ldr rN, [pc, #imm]` (literal
pool holds an anchor address) followed by `ldrb rM, [rN, #off]`, so the
static's address is anchor + off. Both derivations read the artifacts of the
exact build being tested — never hardcode an address, it changes every link.
"""
import re
import subprocess
from pathlib import Path

DEVKITARM_BIN = Path("/opt/devkitpro/devkitARM/bin")


class SymbolMap:
    def __init__(self, map_file: Path):
        self._syms: dict[str, int] = {}
        for line in map_file.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0].startswith("0x"):
                try:
                    self._syms[parts[1]] = int(parts[0], 16)
                except ValueError:
                    continue

    def __getitem__(self, name: str) -> int:
        try:
            return self._syms[name]
        except KeyError:
            raise KeyError(
                f"symbol {name!r} not in linker map — engine change or stale build?"
            ) from None

    def __contains__(self, name: str) -> bool:
        return name in self._syms


def static_addr_via_accessor(elf: Path, func_addr: int, *, span: int = 0x20) -> int:
    """Recover a static's address from a tiny global accessor's disassembly."""
    objdump = DEVKITARM_BIN / "arm-none-eabi-objdump"
    out = subprocess.run(
        [str(objdump), "-d",
         f"--start-address={func_addr:#x}",
         f"--stop-address={func_addr + span:#x}", str(elf)],
        capture_output=True, text=True, check=True,
    ).stdout
    ldrb = re.search(r"ldrb\s+r\d+,\s*\[r\d+,\s*#(\d+)\]", out)
    word = re.search(r"^\s*[0-9a-f]+:\s*([0-9a-f]{8})\s+\.word", out, re.MULTILINE)
    if not ldrb or not word:
        raise ValueError(
            f"accessor at {func_addr:#x} does not match the expected "
            f"ldr-literal + ldrb shape:\n{out}"
        )
    return int(word.group(1), 16) + int(ldrb.group(1))
