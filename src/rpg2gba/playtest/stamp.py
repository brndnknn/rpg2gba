"""Embedded-save ROM stamping: turn a played scenario into a single-file
review artifact.

The engine reserves a zero-filled const blob (`gUraniumEmbeddedSave`,
engine/src/uranium_embedded_save.c). This module dumps the live save blocks
out of a post-scenario emulator, packs them into the blob format, and writes
them into a copy of the .gba at the blob's ROM offset. The stamped ROM boots
by continuing straight into that state on any emulator/device — no .sav to
pair. The pristine ROM is untouched and still boots a new game.

CLI:
    python -m rpg2gba.playtest.stamp --scenario moki-running-shoes \\
        --out output/uranium-build/review.gba
"""
from __future__ import annotations

import logging
import shutil
import struct
from pathlib import Path
from typing import TYPE_CHECKING

import click

from .scenarios import SCENARIOS

if TYPE_CHECKING:  # runtime import is lazy so blob utils work without bindings
    from .emulator import Emulator

logger = logging.getLogger(__name__)

ROM_BASE = 0x08000000
_BLOCKS = ("sb1", "sb2", "sb3", "storage")


def dump_save_blocks(emu: Emulator) -> dict[str, bytes]:
    """Read the four live save blocks out of emulator RAM."""
    ptrs = {
        "sb1": emu.u32(emu.symbols["gSaveBlock1Ptr"]),
        "sb2": emu.u32(emu.symbols["gSaveBlock2Ptr"]),
        "sb3": emu.u32(emu.symbols["gSaveBlock3Ptr"]),
        "storage": emu.u32(emu.symbols["gPokemonStoragePtr"]),
    }
    return {name: emu.read_bytes(ptrs[name], emu.offsets[f"sizeof_{name}"])
            for name in _BLOCKS}


def build_blob(offsets: dict[str, int], blocks: dict[str, bytes]) -> bytes:
    blob = bytearray(offsets["sizeof_es"])
    blob[0:4] = struct.pack("<I", offsets["embedded_save_magic"])
    blob[4:20] = struct.pack(
        "<4I", *(offsets[f"sizeof_{name}"] for name in _BLOCKS))
    for name in _BLOCKS:
        off = offsets[f"off_es_{name}"]
        data = blocks[name]
        assert len(data) == offsets[f"sizeof_{name}"]
        blob[off : off + len(data)] = data
    return bytes(blob)


def stamp_rom(rom: Path, out: Path, emu: Emulator) -> None:
    """Write `emu`'s dumped state into a copy of `rom` at the blob offset."""
    file_off = emu.symbols["gUraniumEmbeddedSave"] - ROM_BASE
    blob = build_blob(emu.offsets, dump_save_blocks(emu))
    data = bytearray(rom.read_bytes())
    if data[file_off : file_off + len(blob)] != bytes(len(blob)):
        raise ValueError(
            f"blob region at {file_off:#x} in {rom} is not zero-filled — "
            "already stamped, or symbol/ROM mismatch")
    data[file_off : file_off + len(blob)] = blob
    out.write_bytes(data)
    logger.info("stamped %s -> %s (blob at %#x, %d bytes)",
                rom, out, file_off, len(blob))


@click.command()
@click.option("--rom", type=click.Path(exists=True, path_type=Path),
              default=None, help="Pristine ROM (default: <engine>/pokeemerald.gba)")
@click.option("--engine", type=click.Path(exists=True, path_type=Path),
              envvar="RPG2GBA_POKEEMERALD", required=True,
              help="Engine build dir (map/elf must match the ROM)")
@click.option("--scenario", type=click.Choice(sorted(SCENARIOS)), required=True)
@click.option("--out", type=click.Path(path_type=Path), required=True,
              help="Stamped ROM to write")
@click.option("--screenshots", type=click.Path(path_type=Path), default=None,
              help="Directory for scenario screenshots")
def main(rom: Path | None, engine: Path, scenario: str, out: Path,
         screenshots: Path | None) -> None:
    """Play SCENARIO headlessly on a scratch copy of the ROM, then write a
    stamped review ROM to OUT."""
    from .scenarios import run_scenario

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rom = rom or engine / "pokeemerald.gba"
    out.parent.mkdir(parents=True, exist_ok=True)
    # Scenario runs on a scratch copy so its .sav never pollutes the source dir.
    scratch = out.parent / f".{out.stem}.scratch.gba"
    scratch_sav = scratch.with_suffix(".sav")
    shutil.copy(rom, scratch)
    scratch_sav.unlink(missing_ok=True)
    try:
        emu = run_scenario(scenario, scratch, engine, screenshot_dir=screenshots)
        stamp_rom(rom, out, emu)
    finally:
        scratch.unlink(missing_ok=True)
        scratch_sav.unlink(missing_ok=True)
    click.echo(f"stamped ROM: {out}")


if __name__ == "__main__":
    main()
