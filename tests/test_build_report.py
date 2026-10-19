"""build_report: ROM usage and kept/dropped stock content."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba import build_report

MAP = """\
Memory Configuration
 .text          0x08000000      0x200 build/emerald/src/main.o
 .rodata        0x08000200      0x100 build/emerald/src/main.o
 .rodata
                0x08000300      0x400 build/emerald/src/pokemon.o
 .bss           0x02000000      0x999 build/emerald/src/main.o
                0x08000700                __rom_end = .
"""


def test_read_rom_usage(tmp_path: Path) -> None:
    path = tmp_path / "pokeemerald.map"
    path.write_text(MAP, encoding="utf-8")
    usage = build_report.read_rom_usage(path)
    assert usage.used == 0x700
    assert usage.by_object == {"src/main.o": 0x300, "src/pokemon.o": 0x400}  # EWRAM .bss ignored
    assert usage.free == 32 * 2**20 - 0x700


def test_missing_rom_end_fails_loud(tmp_path: Path) -> None:
    path = tmp_path / "pokeemerald.map"
    path.write_text(" .text 0x08000000 0x10 build/emerald/src/main.o\n", encoding="utf-8")
    with pytest.raises(ValueError, match="__rom_end"):
        build_report.read_rom_usage(path)


def test_count_stubbed_layouts(tmp_path: Path) -> None:
    path = tmp_path / "layouts.gen.json"
    path.write_text(json.dumps({"layouts": [
        {"blockdata_filepath": "data/layouts/UraniumWalkerStub/map.bin"},
        {"blockdata_filepath": "data/layouts/UraniumWalkerStub/map.bin"},
        {"blockdata_filepath": "data/layouts/MokiTown/map.bin"},
        {},  # a LAYOUT_ placeholder entry with no data
    ]}), encoding="utf-8")
    assert build_report.count_stubbed_layouts(path) == (2, 3)


def test_render_lists_profile_and_layouts() -> None:
    usage = build_report.RomUsage(12_744_356, {"src/pokemon.o": 795_284})
    text = build_report.render(
        usage,
        {"keep": ["P_FAMILY_EEVEE"], "drop": ["P_FAMILY_BULBASAUR"],
         "used_species": ["SPECIES_EEVEE"]},
        (785, 809),
    )
    assert "12,744,356 B (12.15 MiB)" in text
    assert "kept **1**, dropped **1**" in text
    assert "785 stock layouts stubbed, 24 shipped" in text
    assert "| `src/pokemon.o` | 795,284 |" in text
