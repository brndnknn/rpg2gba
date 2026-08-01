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


def _foreign_sav(engine: Path, workdir: Path) -> Path:
    """A real, *different* saved game, for the shadowing check below.

    Boots the pristine ROM to its new-game spawn (the player's house) and saves
    there, so the resulting .sav is a legitimate flash save that disagrees with
    any stamped scenario state.
    """
    from .emulator import Emulator
    from .scenarios import BOOT_FRAMES, save_in_game

    rom = workdir / ".foreign.gba"
    shutil.copy(engine / "pokeemerald.gba", rom)
    rom.with_suffix(".sav").unlink(missing_ok=True)
    emu = Emulator(rom, engine)
    emu.run(BOOT_FRAMES)
    save_in_game(emu)
    sav = workdir / ".foreign.sav"
    shutil.move(rom.with_suffix(".sav"), sav)
    rom.unlink(missing_ok=True)
    return sav


def verify_stamped_rom(stamped: Path, engine: Path, expected: tuple[int, int],
                       expected_pos: tuple[int, int], boot_frames: int = 600) -> None:
    """Assert the stamped ROM boots into its stamped state *despite* a .sav.

    The invariant this pins is the one that broke on 2026-08-01: the engine's
    boot branch preferred the flash save over the embedded blob, so any save
    residue on the test device silently shadowed the stamped state and the ROM
    booted somewhere else entirely. Booting with a deliberately foreign .sav
    paired is the only way to catch that — a fresh-flash boot passes either
    way.
    """
    from .emulator import Emulator

    workdir = stamped.parent
    sav = _foreign_sav(engine, workdir)
    rom = workdir / f".{stamped.stem}.verify.gba"
    try:
        shutil.copy(stamped, rom)
        shutil.copy(sav, rom.with_suffix(".sav"))
        emu = Emulator(rom, engine)
        emu.run(boot_frames)
        got, got_pos = emu.map_location(), emu.player_pos()
        if got != expected or got_pos != expected_pos:
            raise ValueError(
                f"stamped ROM did not boot into its stamped state: expected "
                f"map {expected} pos {expected_pos}, got map {got} pos "
                f"{got_pos}. A flash save is shadowing the embedded blob "
                "(see CB2_StartUraniumSlice in engine/src/new_game.c).")
        if emu.field_locked():
            raise ValueError(
                "stamped ROM booted into its state but the field is locked — "
                "the state was captured mid-script and is not playable.")
    finally:
        rom.unlink(missing_ok=True)
        rom.with_suffix(".sav").unlink(missing_ok=True)
        sav.unlink(missing_ok=True)
    logger.info("verified: %s boots to map %s pos %s with a foreign .sav paired",
                stamped, expected, expected_pos)


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
@click.option("--verify/--no-verify", default=True,
              help="Re-boot the stamped ROM with a foreign .sav paired and "
                   "assert it still lands in the stamped state")
def main(rom: Path | None, engine: Path, scenario: str, out: Path,
         screenshots: Path | None, verify: bool) -> None:
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
        expected, expected_pos = emu.map_location(), emu.player_pos()
        stamp_rom(rom, out, emu)
        del emu
    finally:
        scratch.unlink(missing_ok=True)
        scratch_sav.unlink(missing_ok=True)
    if verify:
        verify_stamped_rom(out, engine, expected, expected_pos)
    click.echo(f"stamped ROM: {out}")


if __name__ == "__main__":
    main()
