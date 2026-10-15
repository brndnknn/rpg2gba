"""Synthetic-byte tests for the party-move decode and the pokedex popcount
(no ROM, no mgba needed except for the unbound `Emulator.pokedex_counts`)."""
from __future__ import annotations

import importlib.util
import struct

import pytest

from rpg2gba.playtest.assertions import (
    decode_box_moves,
    party_knows_move,
    read_party_moves,
)
from rpg2gba.playtest.battle import _SUBSTRUCT_OFFSETS
from rpg2gba.playtest.errors import ScenarioError

NSUB = 12
SIZEOF_PKMN = 100


def _build_secure(personality: int, ot_id: int, moves: tuple[int, int, int, int],
                  species: int) -> bytes:
    """Encrypted 48-byte `secure` block with Growth/Attacks placed per
    personality % 24."""
    key = personality ^ ot_id
    raw = bytearray(48)
    g = _SUBSTRUCT_OFFSETS[0][personality % 24] * NSUB
    a = _SUBSTRUCT_OFFSETS[1][personality % 24] * NSUB
    struct.pack_into("<I", raw, g, species & 0x7FF)
    w0 = (moves[0] & 0x7FF) | ((moves[1] & 0x7FF) << 16)
    w1 = (moves[2] & 0x7FF) | ((moves[3] & 0x7FF) << 16)
    struct.pack_into("<II", raw, a, w0, w1)
    out = bytearray()
    for i in range(0, 48, 4):
        (word,) = struct.unpack_from("<I", raw, i)
        out += struct.pack("<I", word ^ key)
    return bytes(out)


@pytest.mark.parametrize("personality", [0, 5, 6, 12, 18, 23, 24, 0xDEADBEEF])
def test_decode_box_moves_every_substruct_order(personality: int) -> None:
    moves = (10, 249, 2047, 0)
    secure = _build_secure(personality, 0x12345678, moves, 25)
    assert decode_box_moves(personality, 0x12345678, secure, NSUB) == moves


def test_decode_box_moves_short_block_fails_loud() -> None:
    with pytest.raises(ScenarioError):
        decode_box_moves(0, 0, b"\x00" * 4, NSUB)


class FakeEmu:
    """Just enough of Emulator for read_party_moves / party_knows_move."""

    def __init__(self, mons: list[tuple[int, int, int, tuple[int, int, int, int], int]]):
        self.mem: dict[int, bytes] = {}
        self.offsets = {
            "off_pkmn_box": 0, "sizeof_pkmn": SIZEOF_PKMN,
            "off_boxpkmn_personality": 0, "off_boxpkmn_otid": 4,
            "off_boxpkmn_secure": 32, "val_num_substruct_bytes": NSUB,
        }
        self.symbols = {"gPlayerParty": 0x1000}
        self.consts = {"SPECIES_NONE": 0, "PARTY_SIZE": 6, "MOVE_ROCK_SMASH": 249,
                       "MOVE_TACKLE": 33}
        for slot, (pers, ot, species, moves, _x) in enumerate(mons):
            base = 0x1000 + slot * SIZEOF_PKMN
            self.mem[base] = struct.pack("<II", pers, ot)
            self.mem[base + 32] = _build_secure(pers, ot, moves, species)
        # empty slots read as zero personality/otId/secure -> key 0 -> species 0

    def resolve_constant(self, name: str) -> int:
        if name not in self.consts:
            raise RuntimeError(f"unknown constant {name}")
        return self.consts[name]

    def _byte_at(self, addr: int) -> int:
        for base, blob in self.mem.items():
            if base <= addr < base + len(blob):
                return blob[addr - base]
        return 0

    def read_bytes(self, addr: int, size: int) -> bytes:
        return bytes(self._byte_at(addr + i) for i in range(size))

    def u32(self, addr: int) -> int:
        return int.from_bytes(self.read_bytes(addr, 4), "little")


def _two_mon_party() -> FakeEmu:
    return FakeEmu([
        (7, 99, 1575, (10, 45, 52, 249), 0),
        (30, 5, 25, (33, 0, 0, 0), 0),
    ])


def test_read_party_moves_slot_order_and_stops_at_empty() -> None:
    emu = _two_mon_party()
    assert read_party_moves(emu) == [(10, 45, 52, 249), (33, 0, 0, 0)]  # type: ignore[arg-type]


def test_party_knows_move() -> None:
    emu = _two_mon_party()
    assert party_knows_move(emu, "MOVE_ROCK_SMASH")  # type: ignore[arg-type]
    emu.consts["MOVE_SURF"] = 57
    assert not party_knows_move(emu, "MOVE_SURF")  # type: ignore[arg-type]


def test_party_knows_move_unknown_name_fails_loud() -> None:
    emu = _two_mon_party()
    with pytest.raises(RuntimeError):
        party_knows_move(emu, "MOVE_NOT_A_MOVE")  # type: ignore[arg-type]
    with pytest.raises(ScenarioError):
        party_knows_move(emu, "ITEM_HM06")  # type: ignore[arg-type]


@pytest.mark.skipif(importlib.util.find_spec("mgba") is None,
                    reason="needs the mgba python bindings to import emulator.py")
def test_pokedex_counts_popcount_over_national_range() -> None:
    from rpg2gba.playtest.emulator import Emulator

    class Fake:
        sb1 = 0x2000
        offsets = {"val_national_dex_count": 12, "off_sb1_dexseen": 0,
                   "off_sb1_dexcaught": 2}

        def read_bytes(self, addr: int, size: int) -> bytes:
            blob = bytes([0xFF, 0xFF, 0b00000101, 0xFF])  # seen: all 16 bits; caught: 0b101 + junk
            return blob[addr - 0x2000:addr - 0x2000 + size]

    # seen bytes 0xFF 0xFF -> 16 bits but only the first 12 count; caught
    # 0x05 0xFF -> bits 0,2 + bits 8..11 -> 6 (bits 12+ are beyond the range).
    assert Emulator.pokedex_counts(Fake(), True) == (12, 6)  # type: ignore[arg-type]
    with pytest.raises(NotImplementedError):
        Emulator.pokedex_counts(Fake(), False)  # type: ignore[arg-type]
