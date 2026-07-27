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


def _disassemble(elf: Path, func_addr: int, span: int) -> str:
    objdump = DEVKITARM_BIN / "arm-none-eabi-objdump"
    return subprocess.run(
        [str(objdump), "-d",
         f"--start-address={func_addr:#x}",
         f"--stop-address={func_addr + span:#x}", str(elf)],
        capture_output=True, text=True, check=True,
    ).stdout


def static_addr_via_accessor(elf: Path, func_addr: int, *, span: int = 0x20) -> int:
    """Recover a static's address from a tiny global accessor's disassembly."""
    out = _disassemble(elf, func_addr, span)
    ldrb = re.search(r"ldrb\s+r\d+,\s*\[r\d+,\s*#(\d+)\]", out)
    word = re.search(r"^\s*[0-9a-f]+:\s*([0-9a-f]{8})\s+\.word", out, re.MULTILINE)
    if not ldrb or not word:
        raise ValueError(
            f"accessor at {func_addr:#x} does not match the expected "
            f"ldr-literal + ldrb shape:\n{out}"
        )
    return int(word.group(1), 16) + int(ldrb.group(1))


def static_ptr_via_accessor(elf: Path, func_addr: int, *, span: int = 0x30) -> int:
    """Address of a static *pointer* read by a global accessor.

    `static_addr_via_accessor`'s sibling, for the case where the accessor
    dereferences the static rather than indexing into it — a list walk opens
    `ldr rN, [pc, #imm]` (the variable's address, from the literal pool) then
    `ldr rM, [rN, #0]` (its value), so the wanted address is the literal
    itself, with no field offset added.

    Everything else about the walk (field offsets, enum values) comes from
    `offsets.probe_offsets` against the real headers; only the link-time
    address has to be recovered this way.
    """
    out = _disassemble(elf, func_addr, span)
    word = re.search(r"^\s*[0-9a-f]+:\s*([0-9a-f]{8})\s+\.word", out, re.MULTILINE)
    deref = re.search(r"ldr\s+r(\d+),\s*\[r\d+,\s*#0\]", out)
    if not word or not deref:
        raise ValueError(
            f"accessor at {func_addr:#x} does not match the expected "
            f"ldr-literal + deref shape:\n{out}"
        )
    return int(word.group(1), 16)
