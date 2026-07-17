"""Tests for the headless playtest harness (src/rpg2gba/playtest/).

Unit tests run everywhere. The end-to-end test boots the real slice ROM
headless and takes ~a minute, so it is opt-in: RPG2GBA_PLAYTEST=1 pytest
tests/test_playtest.py (also auto-skips if the engine build artifacts or the
mGBA bindings are missing).
"""
import importlib.util
import os
import shutil
import struct
from pathlib import Path

import pytest

from rpg2gba.playtest.stamp import build_blob
from rpg2gba.playtest.symbols import SymbolMap

ENGINE = Path(__file__).resolve().parents[1] / "engine"


# -- unit ---------------------------------------------------------------------

def test_symbol_map_parses_ld_map(tmp_path: Path) -> None:
    map_file = tmp_path / "test.map"
    map_file.write_text(
        " .text          0x081f5840        0x4 src/script.o\n"
        "                0x081f5840                ArePlayerFieldControlsLocked\n"
        "                0x030051d0                gSaveBlock1Ptr\n"
        "junk line\n",
        encoding="utf-8",
    )
    syms = SymbolMap(map_file)
    assert syms["gSaveBlock1Ptr"] == 0x030051D0
    assert "ArePlayerFieldControlsLocked" in syms
    with pytest.raises(KeyError, match="not in linker map"):
        syms["gDoesNotExist"]


def test_build_blob_layout() -> None:
    offsets = {
        "sizeof_es": 64,
        "embedded_save_magic": 0x534E5255,
        "off_es_sb1": 20, "sizeof_sb1": 8,
        "off_es_sb2": 28, "sizeof_sb2": 4,
        "off_es_sb3": 32, "sizeof_sb3": 2,
        "off_es_storage": 34, "sizeof_storage": 6,
    }
    blocks = {"sb1": b"A" * 8, "sb2": b"B" * 4, "sb3": b"C" * 2,
              "storage": b"D" * 6}
    blob = build_blob(offsets, blocks)
    assert len(blob) == 64
    assert struct.unpack_from("<I", blob, 0)[0] == 0x534E5255
    assert struct.unpack_from("<4I", blob, 4) == (8, 4, 2, 6)
    assert blob[20:28] == b"A" * 8
    assert blob[34:40] == b"D" * 6
    assert blob[40:] == bytes(24)


def test_build_blob_rejects_wrong_size() -> None:
    offsets = {"sizeof_es": 32, "embedded_save_magic": 1,
               "off_es_sb1": 20, "sizeof_sb1": 8,
               "off_es_sb2": 28, "sizeof_sb2": 0,
               "off_es_sb3": 28, "sizeof_sb3": 0,
               "off_es_storage": 28, "sizeof_storage": 0}
    blocks = {"sb1": b"A" * 7, "sb2": b"", "sb3": b"", "storage": b""}
    with pytest.raises(AssertionError):
        build_blob(offsets, blocks)


# -- end-to-end (opt-in) ------------------------------------------------------

e2e = pytest.mark.skipif(
    os.environ.get("RPG2GBA_PLAYTEST") != "1"
    or importlib.util.find_spec("mgba") is None
    or not (ENGINE / "pokeemerald.gba").exists()
    or not (ENGINE / "pokeemerald.map").exists(),
    reason="opt-in: needs RPG2GBA_PLAYTEST=1, mgba bindings, and a built engine",
)


@e2e
def test_moki_running_shoes_scenario_and_stamp(tmp_path: Path) -> None:
    from rpg2gba.playtest.emulator import Emulator
    from rpg2gba.playtest.scenarios import run_scenario
    from rpg2gba.playtest.stamp import stamp_rom

    rom = tmp_path / "slice.gba"
    shutil.copy(ENGINE / "pokeemerald.gba", rom)

    emu = run_scenario("moki-running-shoes", rom, ENGINE,
                       screenshot_dir=tmp_path / "shots")
    b_dash = emu.offsets["flag_sys_b_dash"]
    assert emu.flag(b_dash)
    assert rom.with_suffix(".sav").exists()

    stamped = tmp_path / "stamped.gba"
    stamp_rom(rom, stamped, emu)

    # stamped ROM, no .sav: boots CONTINUE into the tested state
    boot = Emulator(stamped, ENGINE)
    boot.run(900)
    assert boot.flag(b_dash)
    assert boot.player_pos() == emu.player_pos()

    # pristine ROM, no .sav: still boots a new game (regression path)
    pristine = tmp_path / "pristine.gba"
    shutil.copy(ENGINE / "pokeemerald.gba", pristine)
    fresh = Emulator(pristine, ENGINE)
    fresh.run(900)
    assert not fresh.flag(b_dash)

    # pristine ROM + the scenario's .sav: boots CONTINUE from flash
    shutil.copy(rom.with_suffix(".sav"), pristine.with_suffix(".sav"))
    cont = Emulator(pristine, ENGINE)
    cont.run(900)
    assert cont.flag(b_dash)
