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

from rpg2gba.playtest.battle import (
    OPPONENT_BATTLER,
    PLAYER_BATTLER,
    decrypt_species,
    in_battle,
    read_enemy_party,
    substruct0_offset,
    zero_enemy_hp,
)
from rpg2gba.playtest.errors import ScenarioError
from rpg2gba.playtest.offsets import probe_constants, probe_offsets
from rpg2gba.playtest.stamp import build_blob
from rpg2gba.playtest.symbols import DEVKITARM_BIN, SymbolMap

ENGINE = Path(__file__).resolve().parents[1] / "engine"


class _FakeMemory:
    """Sparse little-endian byte store standing in for `core.memory`."""

    def __init__(self) -> None:
        self._bytes: dict[int, int] = {}

    def get(self, addr: int, width: int) -> int:
        value = 0
        for i in range(width):
            value |= self._bytes.get(addr + i, 0) << (8 * i)
        return value

    def set(self, addr: int, width: int, value: int) -> None:
        for i in range(width):
            self._bytes[addr + i] = (value >> (8 * i)) & 0xFF


class _FakeEmu:
    """Minimal stand-in for Emulator exposing just what battle.py's
    pure-logic functions read: symbols/offsets/resolve_constant and
    u8/u16/u32/write_u16 over an in-memory byte store. No mgba dependency,
    so these tests run everywhere."""

    def __init__(self, symbols=None, offsets=None, constants=None) -> None:
        self.symbols = symbols or {}
        self.offsets = offsets or {}
        self._constants = constants or {}
        self._mem = _FakeMemory()

    def u8(self, addr: int) -> int:
        return self._mem.get(addr, 1)

    def u16(self, addr: int) -> int:
        return self._mem.get(addr, 2)

    def u32(self, addr: int) -> int:
        return self._mem.get(addr, 4)

    def write_u16(self, addr: int, value: int) -> None:
        self._mem.set(addr, 2, value)

    def write_u32(self, addr: int, value: int) -> None:
        self._mem.set(addr, 4, value)

    def resolve_constant(self, name: str) -> int:
        return self._constants[name]


_BOX_OFFSETS = {
    "off_boxpkmn_personality": 0,
    "off_boxpkmn_otid": 4,
    "off_boxpkmn_secure": 32,
    "val_num_substruct_bytes": 12,
}
_PKMN_OFFSETS = {
    "off_pkmn_box": 0,
    "off_pkmn_hp": 86,
    "off_pkmn_maxhp": 88,
    "off_pkmn_level": 84,
    "sizeof_pkmn": 100,
}
_BATTLEMON_OFFSETS = {
    "off_battlepkmn_hp": 42,
    "sizeof_battlepkmn": 136,
}


def _write_fake_box_species(emu: _FakeEmu, offsets: dict, box_addr: int,
                             personality: int, ot_id: int, species: int,
                             junk: int = 0) -> None:
    """Write an encrypted BoxPokemon at `box_addr` whose substruct-0 species
    field decrypts to `species` (0 <= species < 2048). `junk` ORs extra bits
    into the plaintext word outside the low 11 (teraType/heldItem noise) to
    prove decrypt_species masks them off."""
    key = personality ^ ot_id
    sub_off = substruct0_offset(personality, offsets["val_num_substruct_bytes"])
    word_addr = box_addr + offsets["off_boxpkmn_secure"] + sub_off
    plaintext = (species & 0x7FF) | (junk & ~0x7FF)
    emu.write_u32(box_addr + offsets["off_boxpkmn_personality"], personality)
    emu.write_u32(box_addr + offsets["off_boxpkmn_otid"], ot_id)
    emu.write_u32(word_addr, (plaintext ^ key) & 0xFFFFFFFF)


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


# -- dump_save_blocks / _verify_player_object_alive: save-mirror sync fix ----
#
# The bug (2026-08-07): SaveBlock1's playerParty/objectEvents mirrors are only
# populated by the engine's own save routine (CopyPartyAndObjectsToSave), so
# a straight RAM read mid-scenario captured a stale/zeroed player object --
# the stamped ROM booted into the right map/pos but with no player sprite and
# dead input. `dump_save_blocks` now forces a real in-game save first (behind
# a snapshot/restore so the caller's emulator is untouched), and
# `verify_stamped_rom` now checks the player object actually came back alive,
# not just that SaveBlock1's map/pos are right (which is exactly what let the
# original bug ship). These fakes model the same u8/u16/u32 memory access
# `_FakeEmu` already stands in for elsewhere in this file, plus the extra
# snapshot/restore/field_locked surface `dump_save_blocks` needs.

class _FakeDumpEmu(_FakeEmu):
    """_FakeEmu plus dump_save_blocks's snapshot/restore/field_locked/
    read_bytes/rom surface, so its save-sync-then-rewind sequence can be
    exercised without mgba."""

    def __init__(self, locked: bool = False, rom: Path | None = None) -> None:
        super().__init__(
            symbols={"gSaveBlock1Ptr": 0x100, "gSaveBlock2Ptr": 0x104,
                     "gSaveBlock3Ptr": 0x108, "gPokemonStoragePtr": 0x10C},
            offsets={"sizeof_sb1": 4, "sizeof_sb2": 4, "sizeof_sb3": 4,
                     "sizeof_storage": 4},
        )
        self._locked = locked
        # dump_save_blocks only stats/unlinks this path (had_sav/cleanup); a
        # path that need not exist is fine -- nothing here writes through it.
        self.rom = rom if rom is not None else Path("/nonexistent/fake.gba")
        self.snapshot_calls = 0
        self.restore_calls: list[bytes] = []
        self.write_u32(0x100, 0x2000)
        self.write_u32(0x104, 0x2010)
        self.write_u32(0x108, 0x2020)
        self.write_u32(0x10C, 0x2030)

    def field_locked(self) -> bool:
        return self._locked

    def read_bytes(self, addr: int, size: int) -> bytes:
        return bytes([addr & 0xFF]) * size

    def snapshot_state(self) -> bytes:
        self.snapshot_calls += 1
        return b"SNAPSHOT"

    def restore_state(self, state: bytes) -> None:
        self.restore_calls.append(state)


def test_dump_save_blocks_saves_then_restores_the_snapshot(monkeypatch) -> None:
    from rpg2gba.playtest import stamp

    emu = _FakeDumpEmu()
    save_calls = []
    monkeypatch.setattr("rpg2gba.playtest.scenarios.save_in_game",
                         lambda e: save_calls.append(e))

    blocks = stamp.dump_save_blocks(emu)

    assert save_calls == [emu]  # the real save ran
    assert emu.snapshot_calls == 1
    assert emu.restore_calls == [b"SNAPSHOT"]  # and the caller's emu was rewound
    assert set(blocks) == {"sb1", "sb2", "sb3", "storage"}
    assert all(len(v) == 4 for v in blocks.values())


def test_dump_save_blocks_restores_the_snapshot_even_if_the_save_fails(monkeypatch) -> None:
    from rpg2gba.playtest import stamp

    emu = _FakeDumpEmu()

    def boom(e: object) -> None:
        raise ScenarioError("save failed")

    monkeypatch.setattr("rpg2gba.playtest.scenarios.save_in_game", boom)

    with pytest.raises(ScenarioError, match="save failed"):
        stamp.dump_save_blocks(emu)
    assert emu.restore_calls == [b"SNAPSHOT"]  # rewound despite the failure


def test_dump_save_blocks_raises_when_field_locked(monkeypatch) -> None:
    from rpg2gba.playtest import stamp

    emu = _FakeDumpEmu(locked=True)
    save_calls = []
    monkeypatch.setattr("rpg2gba.playtest.scenarios.save_in_game",
                         lambda e: save_calls.append(e))

    with pytest.raises(ValueError, match="field controls are locked"):
        stamp.dump_save_blocks(emu)
    assert save_calls == []          # never attempted a save mid-script
    assert emu.snapshot_calls == 0   # never even took a snapshot


_OBJEVENT_TEST_OFFSETS = {
    "off_playeravatar_flags": 0,
    "off_playeravatar_objecteventid": 5,
    "sizeof_objevent": 0x24,
    "off_objevent_currentcoords": 0x10,
    "val_map_offset": 7,
}


def _obj_alive_emu() -> _FakeEmu:
    return _FakeEmu(symbols={"gPlayerAvatar": 0x1000, "gObjectEvents": 0x2000},
                    offsets=dict(_OBJEVENT_TEST_OFFSETS))


def test_verify_player_object_alive_passes_on_a_real_spawn() -> None:
    from rpg2gba.playtest.stamp import _verify_player_object_alive

    emu = _obj_alive_emu()
    emu._mem.set(0x1000 + 0, 1, 0x21)  # gPlayerAvatar.flags != 0
    emu._mem.set(0x1000 + 5, 1, 0)     # gPlayerAvatar.objectEventId == 0
    emu._mem.set(0x2000 + 0, 1, 0xC1)  # gObjectEvents[0].active bit set
    emu.write_u16(0x2000 + 0x10, 11)   # currentCoords == expected_pos + MAP_OFFSET
    emu.write_u16(0x2000 + 0x12, 12)

    _verify_player_object_alive(emu, expected_pos=(4, 5))  # must not raise


def test_verify_player_object_alive_raises_when_avatar_flags_zero() -> None:
    """The exact shape of the original bug: SaveBlock1's mirror was never
    synced, so gPlayerAvatar never got initialized on boot."""
    from rpg2gba.playtest.stamp import _verify_player_object_alive

    emu = _obj_alive_emu()  # all-zero memory: flags == 0
    with pytest.raises(ValueError, match="never spawned"):
        _verify_player_object_alive(emu, expected_pos=(4, 5))


def test_verify_player_object_alive_raises_when_object_event_inactive() -> None:
    from rpg2gba.playtest.stamp import _verify_player_object_alive

    emu = _obj_alive_emu()
    emu._mem.set(0x1000 + 0, 1, 0x21)  # avatar looks initialized...
    # ...but gObjectEvents[0].active is left unset.
    with pytest.raises(ValueError, match="not active"):
        _verify_player_object_alive(emu, expected_pos=(4, 5))


def test_verify_player_object_alive_raises_on_coord_mismatch() -> None:
    from rpg2gba.playtest.stamp import _verify_player_object_alive

    emu = _obj_alive_emu()
    emu._mem.set(0x1000 + 0, 1, 0x21)
    emu._mem.set(0x2000 + 0, 1, 0xC1)
    emu.write_u16(0x2000 + 0x10, 99)  # wildly wrong coords
    emu.write_u16(0x2000 + 0x12, 99)
    with pytest.raises(ValueError, match="coords"):
        _verify_player_object_alive(emu, expected_pos=(4, 5))


# -- battle mini-driver: pure logic, no ROM needed -----------------------------

def test_substruct0_offset_matches_engine_permutation_table() -> None:
    # Transcribed from engine/src/pokemon.c's sSubstructOffsets[SUBSTRUCT_TYPE_0]
    # row: personality % 24 -> substruct index. Spot-check a few landmarks
    # rather than the whole 24-entry row.
    assert substruct0_offset(personality=0, num_substruct_bytes=12) == 0 * 12
    assert substruct0_offset(personality=6, num_substruct_bytes=12) == 1 * 12
    assert substruct0_offset(personality=8, num_substruct_bytes=12) == 2 * 12
    assert substruct0_offset(personality=9, num_substruct_bytes=12) == 3 * 12
    # personality wraps mod 24: 24 + 6 behaves like 6.
    assert substruct0_offset(personality=30, num_substruct_bytes=12) == 1 * 12


def test_decrypt_species_roundtrip() -> None:
    emu = _FakeEmu(offsets=_BOX_OFFSETS)
    box_addr = 0x02020000
    _write_fake_box_species(emu, _BOX_OFFSETS, box_addr,
                             personality=0xDEADBEEF, ot_id=0x12345678,
                             species=387)
    assert decrypt_species(emu, box_addr) == 387


def test_decrypt_species_masks_to_11_bits() -> None:
    # species is an 11-bit bitfield sharing its u16 with teraType; junk in
    # the high bits (simulating a nonzero teraType/heldItem) must not leak
    # into the returned species value.
    emu = _FakeEmu(offsets=_BOX_OFFSETS)
    box_addr = 0x02020000
    _write_fake_box_species(emu, _BOX_OFFSETS, box_addr,
                             personality=1, ot_id=0, species=2047,
                             junk=0xFFFF0000)
    assert decrypt_species(emu, box_addr) == 2047


def test_decrypt_species_different_personality_different_substruct_slot() -> None:
    # personality % 24 == 0 puts substruct0 at slot 0; personality % 24 == 9
    # puts it at slot 3 (36 bytes further in). Both must still decode.
    emu = _FakeEmu(offsets=_BOX_OFFSETS)
    for personality, species in ((0, 1), (9, 500)):
        box_addr = 0x02020000 + personality * 0x100  # distinct regions
        _write_fake_box_species(emu, _BOX_OFFSETS, box_addr,
                                 personality=personality, ot_id=0xCAFEBABE,
                                 species=species)
        assert decrypt_species(emu, box_addr) == species


def test_in_battle_requires_thumb_bit() -> None:
    symbols = {"gMain": 0x030066CC, "BattleMainCB2": 0x08083B68}  # map-style (even)
    offsets = {"off_main_callback2": 4}
    emu = _FakeEmu(symbols=symbols, offsets=offsets)

    emu.write_u32(symbols["gMain"] + 4, 0x08000001)  # some other callback
    assert in_battle(emu) is False

    # The bare map address (thumb bit stripped) must NOT match -- this is
    # exactly the bug class _thumb_fn exists to prevent.
    emu.write_u32(symbols["gMain"] + 4, symbols["BattleMainCB2"])
    assert in_battle(emu) is False

    # The real runtime pointer value carries bit 0 set.
    emu.write_u32(symbols["gMain"] + 4, symbols["BattleMainCB2"] | 1)
    assert in_battle(emu) is True


def _fake_battle_symbols() -> tuple[dict, dict]:
    symbols = {
        "gEnemyPartyCount": 0x02031B16,
        "gEnemyParty": 0x02031B1C,
        "gBattleMons": 0x02000420,
    }
    offsets = {**_BOX_OFFSETS, **_PKMN_OFFSETS, **_BATTLEMON_OFFSETS}
    return symbols, offsets


def test_read_enemy_party_decodes_species_level_hp() -> None:
    symbols, offsets = _fake_battle_symbols()
    constants = {"PARTY_SIZE": 6, "SPECIES_NONE": 0}
    emu = _FakeEmu(symbols=symbols, offsets=offsets, constants=constants)
    emu.write_u16(symbols["gEnemyPartyCount"], 1)

    mon_addr = symbols["gEnemyParty"]
    _write_fake_box_species(emu, offsets, mon_addr + offsets["off_pkmn_box"],
                             personality=42, ot_id=99, species=155)
    emu.write_u16(mon_addr + offsets["off_pkmn_hp"], 30)
    emu.write_u16(mon_addr + offsets["off_pkmn_maxhp"], 45)
    emu._mem.set(mon_addr + offsets["off_pkmn_level"], 1, 12)

    party = read_enemy_party(emu)
    assert len(party) == 1
    mon = party[0]
    assert mon.slot == 0
    assert mon.species == 155
    assert mon.level == 12
    assert mon.hp == 30
    assert mon.max_hp == 45


def test_read_enemy_party_rejects_count_over_party_size() -> None:
    symbols, offsets = _fake_battle_symbols()
    constants = {"PARTY_SIZE": 6, "SPECIES_NONE": 0}
    emu = _FakeEmu(symbols=symbols, offsets=offsets, constants=constants)
    emu.write_u16(symbols["gEnemyPartyCount"], 7)
    with pytest.raises(ScenarioError, match="exceeds PARTY_SIZE"):
        read_enemy_party(emu)


def test_read_enemy_party_rejects_species_none_within_count() -> None:
    symbols, offsets = _fake_battle_symbols()
    constants = {"PARTY_SIZE": 6, "SPECIES_NONE": 0}
    emu = _FakeEmu(symbols=symbols, offsets=offsets, constants=constants)
    emu.write_u16(symbols["gEnemyPartyCount"], 1)
    # slot 0 left as all-zero memory -> decrypts to species 0 (SPECIES_NONE)
    with pytest.raises(ScenarioError, match="SPECIES_NONE"):
        read_enemy_party(emu)


def test_zero_enemy_hp_zeroes_party_and_opponent_battle_mon() -> None:
    symbols, offsets = _fake_battle_symbols()
    emu = _FakeEmu(symbols=symbols, offsets=offsets)
    mon_addr = symbols["gEnemyParty"] + 1 * offsets["sizeof_pkmn"]
    emu.write_u16(mon_addr + offsets["off_pkmn_hp"], 77)
    battle_hp_addr = (symbols["gBattleMons"]
                       + OPPONENT_BATTLER * offsets["sizeof_battlepkmn"]
                       + offsets["off_battlepkmn_hp"])
    emu.write_u16(battle_hp_addr, 77)
    player_battle_hp_addr = (symbols["gBattleMons"]
                              + PLAYER_BATTLER * offsets["sizeof_battlepkmn"]
                              + offsets["off_battlepkmn_hp"])
    emu.write_u16(player_battle_hp_addr, 200)

    from rpg2gba.playtest.battle import EnemyMon
    zero_enemy_hp(emu, [EnemyMon(slot=1, species=1, level=5, hp=77, max_hp=77)])

    assert emu.u16(mon_addr + offsets["off_pkmn_hp"]) == 0
    assert emu.u16(battle_hp_addr) == 0
    # the player's own in-battle HP must be untouched
    assert emu.u16(player_battle_hp_addr) == 200


# -- walk_to step-aside pathing: pure logic, no ROM needed -------------------
#
# walk_to needs a live core to actually move a player sprite, but its
# pathing decisions (which direction to try, when to sidestep, when to give
# up) only touch player_pos()/field_locked()/map_location()/run() -- the
# same primitives _FakeEmu-style fakes already stand in for elsewhere in
# this file. `_FakeWalkEmu` simulates a 4-directional grid with optional
# blocked tiles (walls, or a parked NPC -- indistinguishable to walk_to,
# which is the point) and an optional warp tile that flips the simulated
# map id, so the map-identity-changed guard can be exercised without mgba.
#
# Instantiating `Emulator` itself still requires the mgba python bindings
# (the module raises ModuleNotFoundError on import otherwise -- see
# emulator.py's module docstring), so these tests call the unbound
# `Emulator.walk_to`/`Emulator._walk_step` against the fake and are gated on
# mgba being importable, same as `needs_probe` gates on devkitARM. They do
# NOT need RPG2GBA_PLAYTEST=1, a built engine, or a ROM.

_WALK_DIR_DELTA = {"LEFT": (-1, 0), "RIGHT": (1, 0), "UP": (0, -1), "DOWN": (0, 1)}


class _FakeWalkEmu:
    """Grid-walking stand-in for Emulator exposing only what walk_to reads:
    run()/player_pos()/field_locked()/map_location()/screenshot(). `blocked`
    is a set of (x, y) tiles that can never be entered -- a wall or a
    randomly-walking NPC look identical from here. `warp_at`, if given,
    flips the simulated map id the instant the player steps onto it, so a
    sidestep landing on a warp/trigger tile can be exercised."""

    def __init__(self, start: tuple[int, int],
                 blocked: set[tuple[int, int]] = frozenset(),
                 warp_at: tuple[int, int] | None = None) -> None:
        self._pos = start
        self._blocked = set(blocked)
        self._warp_at = warp_at
        self._map = (1, 1)
        self.screenshots: list[str] = []

    def run(self, frames: int, keys: list[str] | None = None) -> None:
        if not keys:
            return
        ddx, ddy = _WALK_DIR_DELTA[keys[0]]
        nx, ny = self._pos[0] + ddx, self._pos[1] + ddy
        if (nx, ny) in self._blocked:
            return
        self._pos = (nx, ny)
        if self._warp_at is not None and self._pos == self._warp_at:
            self._map = (1, 2)

    def player_pos(self) -> tuple[int, int]:
        return self._pos

    def field_locked(self) -> bool:
        return False

    def map_location(self) -> tuple[int, int]:
        return self._map

    def screenshot(self, name: str) -> None:
        self.screenshots.append(name)
        return None

    # `Emulator.walk_to` is exercised unbound (`Emulator.walk_to(emu, ...)`)
    # against this fake, so `self._walk_step` inside it resolves here, not
    # on the real class -- give the fake the same one-step primitive,
    # implemented in terms of its own run()/player_pos().
    def _walk_step(self, direction: str, x: int, y: int) -> tuple[bool, int]:
        for frames in range(1, 41):
            self.run(1, [direction])
            if self.player_pos() != (x, y):
                return True, frames
        return False, 40

    # The fake has no map grid to plan over, so it exercises exactly the
    # degraded path a real run takes when `_plan_route` finds nothing: the
    # bare target, walked greedily. That keeps these tests about the
    # step-aside/oscillation/warp behaviour they were written for.
    def _route_waypoints(self, tx: int, ty: int) -> list[tuple[int, int]]:
        return [(tx, ty)]

    # walk_to waits for the destination map's grid before it plans anything
    # (see the mid-warp tests below). The fake has no grid to load, so it is
    # always ready; the wait itself is pinned separately.
    def wait_for_map_grid(self, frame_budget: int = 300) -> int:
        return 0

    # walk_to's own helpers are the code under test, so they're borrowed from
    # the real class rather than reimplemented here (unbound, same as the
    # walk_to call in each test).
    def _walk_greedy(self, *args, **kwargs):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._walk_greedy(self, *args, **kwargs)

    def _require_same_map(self, *args, **kwargs):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._require_same_map(self, *args, **kwargs)


needs_mgba = pytest.mark.skipif(
    importlib.util.find_spec("mgba") is None,
    reason="needs the mgba python bindings to import emulator.py",
)


@needs_mgba
def test_walk_to_clear_path_walks_straight() -> None:
    from rpg2gba.playtest.emulator import Emulator

    emu = _FakeWalkEmu(start=(0, 0))
    Emulator.walk_to(emu, 3, 0, frame_budget=200)
    assert emu.player_pos() == (3, 0)


@needs_mgba
def test_walk_to_routes_around_one_tile_obstacle() -> None:
    from rpg2gba.playtest.emulator import Emulator

    # (1, 0) sits directly on the line from (0, 0) to (2, 0) -- both
    # greedy attempts (RIGHT, the only axis) fail there, forcing a
    # perpendicular sidestep before the walk can resume.
    emu = _FakeWalkEmu(start=(0, 0), blocked={(1, 0)})
    Emulator.walk_to(emu, 2, 0, frame_budget=500)
    assert emu.player_pos() == (2, 0)
    assert emu.screenshots == []


@needs_mgba
def test_walk_to_fully_walled_target_fails_loud_with_step_aside_message() -> None:
    from rpg2gba.playtest.emulator import Emulator
    from rpg2gba.playtest.errors import ScenarioError

    # All four neighbors of the start tile are blocked, so both greedy
    # axes AND both sidestep candidates fail on the very first stuck event
    # -- a genuine wall, not a flake, and the message must say so.
    emu = _FakeWalkEmu(start=(0, 0),
                        blocked={(1, 0), (-1, 0), (0, 1), (0, -1)})
    with pytest.raises(ScenarioError, match="step-aside attempts"):
        Emulator.walk_to(emu, 5, 5, frame_budget=500)


@needs_mgba
def test_walk_to_oscillation_guard_terminates() -> None:
    from rpg2gba.playtest.emulator import Emulator
    from rpg2gba.playtest.errors import ScenarioError

    # A full wall at x=1 (all three neighboring rows) means every
    # perpendicular sidestep still dead-ends at the same column: the walk
    # keeps bouncing between the tiles either side of the wall. Without the
    # sidestep-attempt bound this would spin forever; with it, it must give
    # up after exactly max_sidesteps attempts rather than exhaust the
    # (generous) frame budget or loop indefinitely.
    emu = _FakeWalkEmu(start=(0, 0), blocked={(1, -1), (1, 0), (1, 1)})
    with pytest.raises(ScenarioError, match="stuck after 4 step-aside attempts"):
        Emulator.walk_to(emu, 2, 0, frame_budget=5000, max_sidesteps=4)


@needs_mgba
def test_walk_to_sidestep_onto_warp_fails_loud() -> None:
    from rpg2gba.playtest.emulator import Emulator
    from rpg2gba.playtest.errors import ScenarioError

    # The only sidestep tried first (UP, since the perpendicular-preference
    # toggle starts at 0) happens to be a warp tile. walk_to must notice
    # the map identity changed and fail loud rather than silently continue
    # the scenario on the wrong map.
    emu = _FakeWalkEmu(start=(0, 0), blocked={(1, 0)}, warp_at=(0, -1))
    with pytest.raises(ScenarioError, match="changed map"):
        Emulator.walk_to(emu, 2, 0, frame_budget=500)


@needs_mgba
def test_walk_to_frame_budget_still_authoritative_on_clear_path() -> None:
    from rpg2gba.playtest.emulator import Emulator
    from rpg2gba.playtest.errors import ScenarioError

    # Nothing is ever blocked here, so this must fail with the plain
    # budget-exhausted message, not a step-aside message -- the two
    # failure modes must stay distinguishable.
    emu = _FakeWalkEmu(start=(0, 0))
    with pytest.raises(ScenarioError, match="frame budget exhausted"):
        Emulator.walk_to(emu, 100, 0, frame_budget=5)


# -- mid-warp map grid: the window where location lies about the grid --------
#
# A warp writes SaveBlock1.location (ApplyCurrentWarp, overworld.c:620) long
# before it rebuilds gBackupMapLayout (InitMap inside LoadMapFromWarp,
# overworld.c:982). Between the two, map_location() already reports the
# destination while the grid still holds the map just left -- and the field
# lock is no signal either, since CB2_LoadMap unlocks controls on the way in.
#
# That window cost the moki chapter beat B4 (2026-07-30): _wait_for_map
# returned inside it, the planner read the 30x15 house grid while the player
# stood on Moki Town's (28,31), the goal (27,17) fell outside those bounds so
# BFS returned None, and the "harmless" greedy fallback stepped off the
# arrival tile -- which is itself the warp back into the house. Nothing pinned
# that the grid must belong to the map the game says it is on, so these do.

_GRID_SYMBOLS = {"gBackupMapLayout": 0x3000, "gMapHeader": 0x4000}
_GRID_OFFSETS = {
    "off_backup_width": 0, "off_backup_height": 4, "off_backup_map": 8,
    "off_mapheader_maplayout": 0,
    "off_maplayout_width": 0, "off_maplayout_height": 4,
    "val_map_offset": 7,
}
_LAYOUT_ADDR = 0x5000


class _FakeGridEmu(_FakeEmu):
    """_FakeEmu plus the handful of reads the grid-load guard makes, and a
    `run()` that finishes the pending map load after `loads_after` frames."""

    def __init__(self, layout_wh, backup_wh, loads_after: int = 0) -> None:
        super().__init__(symbols=dict(_GRID_SYMBOLS), offsets=dict(_GRID_OFFSETS))
        self._layout_wh = layout_wh
        self._loads_after = loads_after
        self.frames = 0
        self.write_u32(_GRID_SYMBOLS["gMapHeader"], _LAYOUT_ADDR)
        self.write_u32(_LAYOUT_ADDR, layout_wh[0])
        self.write_u32(_LAYOUT_ADDR + 4, layout_wh[1])
        self._set_backup(*backup_wh)

    def _set_backup(self, width: int, height: int) -> None:
        base = _GRID_SYMBOLS["gBackupMapLayout"]
        self.write_u32(base, width)
        self.write_u32(base + 4, height)
        self.write_u32(base + 8, 0x2000)

    def run(self, frames: int, keys=None, on_frame=None) -> None:
        self.frames += frames
        if self._loads_after and self.frames >= self._loads_after:
            self._set_backup(self._layout_wh[0] + 15, self._layout_wh[1] + 14)

    def map_location(self) -> tuple[int, int]:
        return (75, 2)

    def read_bytes(self, addr: int, size: int) -> bytes:
        return b"\x00" * size

    def _warp_tiles(self) -> set[tuple[int, int]]:
        return set()

    # The guard's own helpers are the code under test, so they're borrowed
    # from the real class rather than reimplemented (unbound, same pattern as
    # _FakeWalkEmu above).
    def _grid_dims_for_current_map(self):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._grid_dims_for_current_map(self)

    def map_grid_loaded(self) -> bool:
        from rpg2gba.playtest.emulator import Emulator
        return Emulator.map_grid_loaded(self)

    def _map_grid(self):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._map_grid(self)


@needs_mgba
def test_map_grid_loaded_true_only_when_dims_match_the_map_header() -> None:
    from rpg2gba.playtest.emulator import Emulator

    # Moki Town is 72x64, so a loaded grid is 87x78 (+MAP_OFFSET_W/_H).
    loaded = _FakeGridEmu(layout_wh=(72, 64), backup_wh=(87, 78))
    assert Emulator.map_grid_loaded(loaded) is True

    # The house it warped out of is 30x15 -> 45x29: still the old grid.
    mid_warp = _FakeGridEmu(layout_wh=(72, 64), backup_wh=(45, 29))
    assert Emulator.map_grid_loaded(mid_warp) is False


@needs_mgba
def test_map_grid_refuses_a_grid_belonging_to_another_map() -> None:
    from rpg2gba.playtest.emulator import Emulator

    emu = _FakeGridEmu(layout_wh=(72, 64), backup_wh=(45, 29))
    with pytest.raises(ScenarioError, match="still loading"):
        Emulator._map_grid(emu)


@needs_mgba
def test_wait_for_map_grid_returns_once_the_load_completes() -> None:
    from rpg2gba.playtest.emulator import Emulator

    emu = _FakeGridEmu(layout_wh=(72, 64), backup_wh=(45, 29), loads_after=30)
    spent = Emulator.wait_for_map_grid(emu, frame_budget=300)
    assert spent >= 30
    assert Emulator.map_grid_loaded(emu) is True


@needs_mgba
def test_wait_for_map_grid_fails_loud_if_the_load_never_completes() -> None:
    from rpg2gba.playtest.emulator import Emulator

    emu = _FakeGridEmu(layout_wh=(72, 64), backup_wh=(45, 29))
    with pytest.raises(ScenarioError, match="never finished loading"):
        Emulator.wait_for_map_grid(emu, frame_budget=60)


@needs_mgba
def test_plan_route_rejects_a_goal_outside_the_grid_instead_of_degrading() -> None:
    """B4's exact shape: the goal is off the (stale) grid entirely.

    This must raise, not return None -- returning None sends
    `_route_waypoints` down the greedy fallback, which is what walked the
    player back through the arrival warp.
    """
    from rpg2gba.playtest.emulator import Emulator

    # A loaded 30x15 grid; (27,17) is past its southern edge.
    emu = _FakeGridEmu(layout_wh=(30, 15), backup_wh=(45, 29))
    with pytest.raises(ScenarioError, match="outside the loaded map grid"):
        Emulator._plan_route(emu, (28, 12), (27, 17))


# -- waypoint frame settling: pure logic, no ROM needed ----------------------
#
# Beat boundaries land on warps and battle transitions, so the frame at that
# instant is often mid-fade and solid black -- 5 of 19 tiles in the 2026-07-27
# moki contact sheet were blank. `_FakeScreenEmu` stands in for the parts of
# Emulator that `waypoint`/`_settle_frame` touch, with a scripted sequence of
# frames, so the settling rule can be exercised without mgba running a ROM.


class _FakeScreenEmu:
    """Emulator stand-in whose screen becomes reviewable after `blank_for`
    settle steps. `run()` is the only thing that advances it, exactly as a
    real fade only progresses while the core runs."""

    def __init__(self, tmp_path, blank_for: int) -> None:
        from PIL import Image

        self._blank_for = blank_for
        self._advanced = 0
        self.frame = 0
        self.screenshot_dir = tmp_path
        self.waypoints: list = []
        self._text_frame = None
        self._text_was_drawing = False
        self._frame_pinned = False
        self._blank = Image.new("RGB", (240, 160), (0, 0, 0))
        self._scene = Image.effect_noise((240, 160), 64).convert("RGB")
        # Scripted text state, for the note_text_frame-vs-mark_frame tests.
        self.text_drawing = False
        self.text_is_ready = True

    class _Screen:
        def __init__(self, owner) -> None:
            self._owner = owner

        def to_pil(self):
            o = self._owner
            return o._blank if o._advanced < o._blank_for else o._scene

    @property
    def screen(self):
        return self._Screen(self)

    def run(self, frames: int, keys=None) -> None:
        self._advanced += frames
        self.frame += frames

    # Borrowed from the real class (unbound), same pattern as _FakeWalkEmu:
    # these are the code under test, not part of the stand-in.
    def _settle_frame(self, *args, **kwargs):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._settle_frame(self, *args, **kwargs)

    def _frame_unreviewable(self, *args, **kwargs):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._frame_unreviewable(self, *args, **kwargs)

    def mark_frame(self, *args, **kwargs):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator.mark_frame(self, *args, **kwargs)

    def note_text_frame(self, *args, **kwargs):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator.note_text_frame(self, *args, **kwargs)

    def text_showing(self) -> bool:
        return self.text_drawing

    def text_ready(self) -> bool:
        return self.text_is_ready


def _waypoint(emu, **kwargs):
    from rpg2gba.playtest.emulator import Emulator

    return Emulator.waypoint(emu, **kwargs)


@needs_mgba
def test_waypoint_waits_out_a_fade_before_capturing(tmp_path) -> None:
    """A blank frame at the beat boundary must not become a blank sheet tile:
    the capture advances the core until the screen has something on it."""
    from rpg2gba.playtest.emulator import Emulator

    emu = _FakeScreenEmu(tmp_path, blank_for=32)
    wp = _waypoint(emu, beat="B5", note="entered the lab")
    assert emu._advanced >= 32  # waited the fade out
    assert not Emulator._frame_unreviewable(emu)
    assert wp.note == "entered the lab"  # no blank annotation
    from PIL import Image

    assert Image.open(wp.path).getcolors(maxcolors=8) is None  # a real frame


@needs_mgba
def test_waypoint_does_not_wait_when_the_frame_is_already_good(tmp_path) -> None:
    emu = _FakeScreenEmu(tmp_path, blank_for=0)
    _waypoint(emu, beat="B3")
    assert emu._advanced == 0


@needs_mgba
def test_waypoint_gives_up_and_says_so_on_a_permanently_blank_screen(tmp_path) -> None:
    """A genuinely black screen (or a hung transition) still gets captured --
    a waypoint is documentation, not an assertion -- but the note has to say
    the screen really was blank, so a blank tile is never ambiguous."""
    emu = _FakeScreenEmu(tmp_path, blank_for=10_000)
    wp = _waypoint(emu, beat="B9", note="battle")
    assert "screen still blank" in wp.note
    assert emu._advanced <= 300  # bounded, not a hang


@needs_mgba
def test_failure_waypoint_captures_the_exact_frame(tmp_path) -> None:
    """A failure frame is evidence: it must be the frame the beat failed on,
    so the settling must not run the core forward past it."""
    emu = _FakeScreenEmu(tmp_path, blank_for=32)
    _waypoint(emu, beat="B4", name="FAILED", failed=True)
    assert emu._advanced == 0


# -- mark_frame: a beat choosing its own tile ---------------------------------
#
# The automatic rules serve beats that play dialogue and end when it does.
# They cannot serve a beat whose moment is a menu being up, or one that ends
# without advancing the core at all -- moki B6 asserts only that the field is
# still locked, runs zero frames, and so photographed B5's tile over again.


@needs_mgba
def test_mark_frame_pins_that_frame_as_the_tile(tmp_path) -> None:
    from PIL import Image

    emu = _FakeScreenEmu(tmp_path, blank_for=0)
    assert emu.mark_frame() is True
    wp = _waypoint(emu, beat="B6", note="yes/no prompt")
    assert wp.at_text is True          # a stored frame, not the live one
    assert emu._advanced == 0          # and no settling ran past it
    assert Image.open(wp.path).getcolors(maxcolors=8) is None


@needs_mgba
def test_mark_frame_refuses_a_blank_frame_unless_forced(tmp_path) -> None:
    """Pinning skips settling, so pinning a mid-fade frame would produce
    exactly the black tile `_settle_frame` exists to prevent -- silently."""
    emu = _FakeScreenEmu(tmp_path, blank_for=10_000)
    assert emu.mark_frame() is False
    assert emu._text_frame is None     # nothing pinned; waypoint still settles
    assert emu.mark_frame(force=True) is True
    assert emu._text_frame is not None


@needs_mgba
def test_mark_frame_is_sticky_against_later_dialogue(tmp_path) -> None:
    """Otherwise an explicit choice would survive or not depending on whether
    more text happened to follow it, which is not a rule anyone can reason
    about at the call site."""
    emu = _FakeScreenEmu(tmp_path, blank_for=0)
    emu.mark_frame()
    pinned = emu._text_frame

    # A message completes afterwards: the falling edge of text_showing.
    emu.text_drawing = True
    emu.note_text_frame()
    emu.text_drawing = False
    emu.note_text_frame()

    assert emu._text_frame is pinned


@needs_mgba
def test_waypoint_clears_the_pin_so_it_is_per_beat(tmp_path) -> None:
    emu = _FakeScreenEmu(tmp_path, blank_for=0)
    emu.mark_frame()
    _waypoint(emu, beat="B6")
    assert emu._frame_pinned is False
    assert emu._text_frame is None

    # The next beat's dialogue capture works normally again.
    emu.text_drawing = True
    emu.note_text_frame()
    emu.text_drawing = False
    emu.note_text_frame()
    assert emu._text_frame is not None


# -- text-frame capture -------------------------------------------------------
#
# A beat only returns once its scene has been mashed to the end, so the live
# frame at the beat boundary always shows the world *after* the event. These
# cover the fix: the frame the sheet gets is the last one that had dialogue on
# it (see `Emulator.note_text_frame` / `waypoint`).

class _FakeTextEmu:
    """Emulator stand-in for the dialogue path.

    `script` is one `(field_locked, text_drawing, tag)` triple per sample, and
    `tap` consumes exactly one -- the real `tap` samples every frame it runs,
    which for these tests collapses to one sample per tap. `text_drawing` is
    what `text_showing` reports, so a True→False pair in the script *is* the
    falling edge `note_text_frame` captures on.

    Frames are noise (so `_frame_unreviewable` passes them) carrying `tag` in
    pixel (0,0), which is how a test says *which* frame survived to the
    waypoint; `tag=None` is a blank frame. A 4th element sets `text_ready`,
    defaulting to True.
    """

    def __init__(self, tmp_path, script) -> None:
        self._script = list(script)
        self._step = 0
        self.frame = 0
        self.screenshot_dir = tmp_path
        self.waypoints: list = []
        self._text_frame = None
        self._text_was_drawing = False
        self._frame_pinned = False
        self.taps = 0
        self._advanced = 0

    @property
    def _now(self):
        return self._script[min(self._step, len(self._script) - 1)]

    def field_locked(self) -> bool:
        return self._now[0]

    def text_showing(self) -> bool:
        return self._now[1]

    def text_ready(self) -> bool:
        now = self._now
        return now[3] if len(now) > 3 else True

    class _Screen:
        def __init__(self, owner) -> None:
            self._owner = owner

        def to_pil(self):
            from PIL import Image

            tag = self._owner._now[2]
            if tag is None:
                return Image.new("RGB", (240, 160), (0, 0, 0))
            img = Image.effect_noise((240, 160), 64).convert("RGB")
            img.putpixel((0, 0), (tag, 0, 0))
            return img

    @property
    def screen(self):
        return self._Screen(self)

    def run(self, frames: int, keys=None, on_frame=None) -> None:
        self._advanced += frames
        self.frame += frames
        for _ in range(frames if on_frame else 0):
            on_frame()

    def tap(self, key: str, hold: int = 6, release: int = 6) -> None:
        self.note_text_frame()  # the real tap samples every frame it runs
        self.taps += 1
        self._step += 1

    def screenshot(self, name: str):
        return None

    # Borrowed from the real class (unbound) -- the code under test.
    def _settle_frame(self, *a, **kw):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._settle_frame(self, *a, **kw)

    def _frame_unreviewable(self, *a, **kw):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator._frame_unreviewable(self, *a, **kw)

    def note_text_frame(self, *a, **kw):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator.note_text_frame(self, *a, **kw)


def _advance(emu, **kwargs) -> int:
    from rpg2gba.playtest.emulator import Emulator

    return Emulator.advance_dialog(emu, **kwargs)


def _tag_of(path) -> int:
    from PIL import Image

    return Image.open(path).getpixel((0, 0))[0]


@needs_mgba
def test_waypoint_captures_the_last_completed_message_not_the_aftermath(tmp_path) -> None:
    """The payoff line, not the greeting and not the empty room afterwards."""
    emu = _FakeTextEmu(tmp_path, [
        (True, True, 11),    # "Oh, you're up!" -- still appearing
        (True, False, 22),   # ...finished: an edge, captured
        (True, True, 33),    # next message appearing
        (True, False, 44),   # "You got the Running Shoes!"  <- the one to keep
        (False, False, 99),  # scene over, beat asserts and returns
    ])
    assert _advance(emu) == 4
    wp = _waypoint(emu, beat="B3", note="Auntie grants FLAG_SYS_B_DASH")
    assert _tag_of(wp.path) == 44
    assert wp.at_text
    assert emu._advanced == 0  # a stored frame never advances the core


@needs_mgba
def test_note_text_frame_never_captures_a_half_typed_message(tmp_path) -> None:
    """The whole point of the edge. A frame taken while the message is still
    appearing reads "See you later, R"; only the frame the last glyph lands on
    is worth keeping."""
    emu = _FakeTextEmu(tmp_path, [
        (True, True, 11),   # "See you later, R"    -- still appearing
        (True, True, 22),   # "See you later, RE"   -- still appearing
        (True, False, 33),  # "See you later, RED!" -- done
        (False, False, 99),
    ])
    _advance(emu)
    wp = _waypoint(emu, beat="B9")
    assert _tag_of(wp.path) == 33


@needs_mgba
def test_note_text_frame_ignores_a_locked_stretch_with_no_dialogue(tmp_path) -> None:
    """`field_locked` is also true through fades and scripted walk routes. No
    message drawn means no edge, so nothing is captured and the waypoint falls
    back to the live frame."""
    emu = _FakeTextEmu(tmp_path, [
        (True, False, 11),   # locked, but it's Theo's walk-on move route
        (True, False, 22),
        (False, False, 99),
    ])
    _advance(emu)
    wp = _waypoint(emu, beat="B4")
    assert _tag_of(wp.path) == 99
    assert not wp.at_text


@needs_mgba
def test_note_text_frame_skips_a_message_that_finished_over_a_fade(tmp_path) -> None:
    """A black tile with a textbox on it is no more reviewable than a plain
    black one, so the last *usable* completed message wins."""
    emu = _FakeTextEmu(tmp_path, [
        (True, True, 11),
        (True, False, 22),    # finished and reviewable -- kept
        (True, True, 33),
        (True, False, None),  # finished, but the screen is mid-fade
        (False, False, 99),
    ])
    _advance(emu)
    wp = _waypoint(emu, beat="B13")
    assert _tag_of(wp.path) == 22


@needs_mgba
def test_note_text_frame_requires_the_page_to_be_drawn(tmp_path) -> None:
    """`text_ready` guards the edge: a box torn down mid-draw (a script-driven
    close rather than a message running out of characters) is not a message
    worth showing."""
    emu = _FakeTextEmu(tmp_path, [
        (True, True, 11, False),
        (True, False, 22, False),  # an edge, but nothing finished drawing
        (False, False, 99, True),
    ])
    _advance(emu)
    wp = _waypoint(emu, beat="B12")
    assert _tag_of(wp.path) == 99
    assert not wp.at_text


@needs_mgba
def test_waypoint_falls_back_to_the_live_frame_when_no_dialogue_ran(tmp_path) -> None:
    """B14 re-crosses the ceremony tiles and must *not* fire a scene; there is
    no text moment to catch, so the beat-boundary frame is still the right one."""
    emu = _FakeTextEmu(tmp_path, [(False, False, 99)])
    _advance(emu)
    wp = _waypoint(emu, beat="B14")
    assert _tag_of(wp.path) == 99
    assert not wp.at_text


@needs_mgba
def test_failure_waypoint_ignores_a_stored_text_frame(tmp_path) -> None:
    """A failure frame is evidence of the moment it failed -- never a nicer
    frame salvaged from earlier in the beat."""
    emu = _FakeTextEmu(tmp_path, [
        (True, True, 11), (True, False, 22), (False, False, 99)])
    _advance(emu)
    wp = _waypoint(emu, beat="B9", name="FAILED", failed=True)
    assert _tag_of(wp.path) == 99
    assert not wp.at_text
    assert emu._advanced == 0


@needs_mgba
def test_text_frame_does_not_carry_over_to_the_next_beat(tmp_path) -> None:
    """Otherwise a silent beat would inherit the previous beat's dialogue and
    the sheet would show the same tile twice."""
    emu = _FakeTextEmu(tmp_path, [
        (True, True, 11), (True, False, 22), (False, False, 99)])
    _advance(emu)
    first = _waypoint(emu, beat="B3")
    second = _waypoint(emu, beat="B4")
    assert _tag_of(first.path) == 22
    assert first.at_text
    assert _tag_of(second.path) == 99
    assert not second.at_text


@needs_mgba
def test_advance_dialog_stops_on_the_stop_condition(tmp_path) -> None:
    """A script ending in a battle never releases the field controls; without
    the stop hook the A-mash would play the battle by accident."""
    emu = _FakeTextEmu(tmp_path, [
        (True, True, 11),
        (True, True, 22),
        (True, True, 33),  # battle has started; still locked
    ])
    taps = _advance(emu, stop=lambda: emu.taps >= 2)
    assert taps == 2


@needs_mgba
def test_advance_dialog_fails_loud_when_the_script_never_releases(tmp_path) -> None:
    emu = _FakeTextEmu(tmp_path, [(True, True, 11)])
    with pytest.raises(ScenarioError, match="never released field controls"):
        _advance(emu, max_taps=5)


def test_caption_marks_a_text_frame() -> None:
    """The marker matters for its absence: a beat whose doc row promises a
    message but whose tile has no `+` never showed that message."""
    from rpg2gba.playtest.contact_sheet import Waypoint

    at_text = Waypoint(beat="B3", name="B3", note="", frame=0,
                       path=Path("x.png"), at_text=True)
    silent = Waypoint(beat="B14", name="B14", note="", frame=0,
                      path=Path("x.png"))
    assert at_text.caption == "B3 +"
    assert silent.caption == "B14"


needs_probe = pytest.mark.skipif(
    not (DEVKITARM_BIN / "arm-none-eabi-gcc").exists()
    or not (ENGINE / "include").exists(),
    reason="needs devkitARM toolchain and the vendored engine include tree",
)


needs_build = pytest.mark.skipif(
    not (ENGINE / "pokeemerald.elf").exists()
    or not (DEVKITARM_BIN / "arm-none-eabi-objdump").exists(),
    reason="needs a built engine ELF and the devkitARM toolchain",
)


class _FakePrinterEmu:
    """Emulator stand-in over a fake `sFirstTextPrinter` list, for `text_ready`.

    `nodes` is a list of `(type, window_id, state)`; they are laid out in a
    sparse memory at fixed addresses and chained through `off_printer_next`.
    An empty list means the head pointer is NULL.
    """

    HEAD = 0x02030000
    BASE = 0x02031000
    STRIDE = 0x100

    def __init__(self, offsets, nodes) -> None:
        self.offsets = offsets
        self._printer_list = self.HEAD
        self._mem: dict[int, int] = {}
        addr = self.BASE
        self._mem[self.HEAD] = addr if nodes else 0
        for i, (ptype, window_id, state) in enumerate(nodes):
            nxt = addr + self.STRIDE if i + 1 < len(nodes) else 0
            self._mem[addr + offsets["off_printer_type"]] = ptype
            self._mem[addr + offsets["off_printer_window_id"]] = window_id
            self._mem[addr + offsets["off_printer_state"]] = state
            self._mem[addr + offsets["off_printer_next"]] = nxt
            addr += self.STRIDE

    def u8(self, addr: int) -> int:
        return self._mem.get(addr, 0)

    def u32(self, addr: int) -> int:
        return self._mem.get(addr, 0)

    def text_ready(self, *a, **kw):
        from rpg2gba.playtest.emulator import Emulator
        return Emulator.text_ready(self, *a, **kw)


@needs_probe
@needs_mgba
def test_text_ready_is_true_when_the_printer_was_already_freed() -> None:
    """The regression that dropped B2's refusal line: a one-page message hits
    RENDER_FINISH as its last glyph lands, which frees the printer off the list
    while the box stays up waiting for A. That is the *most* reviewable frame,
    so an empty list must read as ready, not as busy."""
    emu = _FakePrinterEmu(probe_offsets(ENGINE), [])
    assert emu.text_ready() is True


@needs_probe
@needs_mgba
def test_text_ready_is_false_while_glyphs_are_still_drawing() -> None:
    o = probe_offsets(ENGINE)
    emu = _FakePrinterEmu(o, [
        (o["val_window_text_printer"], 0, o["val_render_state_handle_char"]),
    ])
    assert emu.text_ready() is False


@needs_probe
@needs_mgba
def test_text_ready_is_true_for_a_page_parked_on_the_down_arrow() -> None:
    o = probe_offsets(ENGINE)
    for parked in ("val_render_state_wait", "val_render_state_clear",
                   "val_render_state_scroll_start"):
        emu = _FakePrinterEmu(o, [
            (o["val_window_text_printer"], 0, o[parked]),
        ])
        assert emu.text_ready() is True, parked


@needs_probe
@needs_mgba
def test_text_ready_walks_past_printers_bound_elsewhere() -> None:
    """A sprite printer, or a window printer for a different window, must not
    answer for window 0 -- the walk has to keep going."""
    o = probe_offsets(ENGINE)
    emu = _FakePrinterEmu(o, [
        (o["val_window_text_printer"] + 1, 0, o["val_render_state_handle_char"]),
        (o["val_window_text_printer"], 7, o["val_render_state_handle_char"]),
        (o["val_window_text_printer"], 0, o["val_render_state_wait"]),
    ])
    assert emu.text_ready() is True


@needs_build
def test_static_ptr_recovery_lands_in_ewram() -> None:
    """`sFirstTextPrinter` is the one part of the printer walk that can't come
    from the headers -- it's a link-time address, so it comes out of the
    accessor's literal pool."""
    from rpg2gba.playtest.symbols import static_ptr_via_accessor

    syms = SymbolMap(ENGINE / "pokeemerald.map")
    addr = static_ptr_via_accessor(
        ENGINE / "pokeemerald.elf", syms["IsTextPrinterActiveOnWindow"])
    assert 0x02000000 <= addr < 0x02040000  # EWRAM_DATA


@needs_build
def test_static_ptr_recovery_fails_loud_on_the_wrong_shape() -> None:
    """Pointed at an accessor that indexes rather than dereferences, this must
    raise -- returning the literal would silently yield a wrong address."""
    from rpg2gba.playtest.symbols import static_ptr_via_accessor

    syms = SymbolMap(ENGINE / "pokeemerald.map")
    with pytest.raises(ValueError, match="ldr-literal \\+ deref shape"):
        static_ptr_via_accessor(
            ENGINE / "pokeemerald.elf", syms["ArePlayerFieldControlsLocked"])


@needs_build
def test_static_fn_recovery_finds_the_yesno_task_handler() -> None:
    """`Task_HandleYesNoInput` is static, so it never reaches the link map --
    but `ScriptMenu_YesNo` has to materialise its address to pass it to
    `CreateTask`, so it is in that function's literal pool. The recovered
    value must keep its Thumb bit: `gTasks[i].func` stores the odd address,
    and comparing against the even one silently never matches."""
    from rpg2gba.playtest.symbols import static_fn_via_literal_pool

    syms = SymbolMap(ENGINE / "pokeemerald.map")
    addr = static_fn_via_literal_pool(
        ENGINE / "pokeemerald.elf", syms["ScriptMenu_YesNo"])
    assert addr & 1                       # Thumb bit preserved
    assert 0x08000000 <= addr < 0x0A000000  # in the ROM image
    assert "Task_HandleYesNoInput" not in open(
        ENGINE / "pokeemerald.map", encoding="utf-8", errors="ignore").read()


@needs_build
def test_static_fn_recovery_fails_loud_when_no_pool_entry_qualifies() -> None:
    """Pointed at a function whose pool holds only data addresses, this must
    raise rather than hand back an even literal that would never match."""
    from rpg2gba.playtest.symbols import static_fn_via_literal_pool

    syms = SymbolMap(ENGINE / "pokeemerald.map")
    with pytest.raises(ValueError, match="no Thumb function pointer"):
        static_fn_via_literal_pool(
            ENGINE / "pokeemerald.elf", syms["ArePlayerFieldControlsLocked"])


_TASK_OFFSETS = {
    "off_task_func": 0,
    "off_task_is_active": 4,
    "sizeof_task": 40,
    "val_num_tasks": 16,
}
_YESNO_FN = 0x081F642D


def _task_emu(slots: list[tuple[int, int]]) -> _FakeEmu:
    """`slots` is [(isActive, func)] written into a fake gTasks array."""
    emu = _FakeEmu(symbols={"gTasks": 0x03006C30}, offsets=dict(_TASK_OFFSETS))
    emu._yesno_task_fn = _YESNO_FN
    for i, (active, func) in enumerate(slots):
        task = 0x03006C30 + i * _TASK_OFFSETS["sizeof_task"]
        emu.write_u32(task + _TASK_OFFSETS["off_task_func"], func)
        emu._mem.set(task + _TASK_OFFSETS["off_task_is_active"], 1, active)
    return emu


@needs_mgba
def test_yesno_prompt_up_finds_the_handler_task() -> None:
    from rpg2gba.playtest.emulator import Emulator

    emu = _task_emu([(1, 0x08001111), (1, _YESNO_FN)])
    assert Emulator.yesno_prompt_up(emu) is True


@needs_mgba
def test_yesno_prompt_up_ignores_an_inactive_slot() -> None:
    """A freed task keeps its `func` -- `FuncIsActiveTask` checks `isActive`
    first for exactly this reason, so a dismissed prompt must not read as up."""
    from rpg2gba.playtest.emulator import Emulator

    emu = _task_emu([(0, _YESNO_FN)])
    assert Emulator.yesno_prompt_up(emu) is False


@needs_mgba
def test_yesno_prompt_up_false_with_other_tasks_running() -> None:
    from rpg2gba.playtest.emulator import Emulator

    emu = _task_emu([(1, 0x08001111), (1, 0x08002222)])
    assert Emulator.yesno_prompt_up(emu) is False


@needs_probe
def test_probed_printer_offsets_match_the_compiled_accessor() -> None:
    """The offsets `text_ready` walks with come from the headers; the same
    numbers are visible as immediates in `IsTextPrinterActiveOnWindow`'s own
    code. Two independent derivations agreeing is what says the walk is
    reading real fields and not plausible-looking garbage."""
    import re

    from rpg2gba.playtest.symbols import _disassemble

    o = probe_offsets(ENGINE)
    syms = SymbolMap(ENGINE / "pokeemerald.map")
    asm = _disassemble(
        ENGINE / "pokeemerald.elf", syms["IsTextPrinterActiveOnWindow"], 0x30)

    # ldrb of printerTemplate.type, then of printerTemplate.windowId
    ldrb = [int(n) for n in re.findall(r"ldrb\s+r\d+,\s*\[r\d+,\s*#(\d+)\]", asm)]
    # ldr of nextPrinter (the #0 one is the list-head deref)
    ldr = [int(n) for n in re.findall(r"ldr\s+r\d+,\s*\[r\d+,\s*#(\d+)\]", asm)]
    assert o["off_printer_type"] in ldrb
    assert o["off_printer_window_id"] in ldrb
    assert o["off_printer_next"] in ldr
    assert o["val_window_text_printer"] == 0  # the `cmp r2, #0` in the walk
    # HANDLE_CHAR must be distinct from every parked state, or `text_ready`
    # cannot tell "still typing" from "waiting on the down arrow".
    assert o["val_render_state_handle_char"] not in (
        o["val_render_state_wait"], o["val_render_state_clear"],
        o["val_render_state_scroll_start"])
    assert o["off_printer_state"] != o["off_printer_type"]


@needs_probe
def test_probe_constants_resolves_known_good_name() -> None:
    # VAR_TEMP_POKEMON_CHOICE is defined in uranium_flags.h as
    # (RPG2GBA_VAR_BASE + 0), and RPG2GBA_VAR_BASE is RPG2GBA_VARS_START
    # (constants/vars.h). Resolve both through the same probe and check the
    # indirection chain the header encodes, rather than hardcoding a number.
    values = probe_constants(
        ENGINE, ["VAR_TEMP_POKEMON_CHOICE", "RPG2GBA_VARS_START"])
    assert values["VAR_TEMP_POKEMON_CHOICE"] == values["RPG2GBA_VARS_START"]


@needs_probe
def test_probe_constants_raises_on_unknown_name() -> None:
    with pytest.raises(RuntimeError, match="VAR_TOTALLY_MADE_UP_NAME"):
        probe_constants(ENGINE, ["VAR_TOTALLY_MADE_UP_NAME"])


def test_probe_constants_missing_header_raises_loud(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="uranium_flags.h"):
        probe_constants(tmp_path, ["VAR_TEMP_POKEMON_CHOICE"])


@needs_probe
def test_probe_offsets_resolves_battle_struct_fields() -> None:
    # Sanity-checks the battle.py-only probe entries against relationships
    # that must hold regardless of engine version/layout churn: struct
    # Pokemon's box field is first (offset 0), hp directly precedes maxHP,
    # and struct Main's callback2 is a 4-byte-wide field following callback1
    # (both function pointers).
    values = probe_offsets(ENGINE)
    assert values["off_pkmn_box"] == 0
    assert values["off_pkmn_maxhp"] == values["off_pkmn_hp"] + 2
    assert values["sizeof_pkmn"] > values["off_pkmn_hp"]
    assert values["off_main_callback2"] == 4
    assert values["val_num_substruct_bytes"] > 0
    assert values["sizeof_battlepkmn"] > values["off_battlepkmn_hp"]


# -- START-menu introspection: menu-position-driven save_in_game -------------
#
# 2026-08 bug: save_in_game drove the START menu with hardcoded DOWN x2 taps,
# a row offset only correct without a party (no POKEMON row). scenarios.py now
# reads the engine's own live menu-action array/cursor back out of memory
# instead of assuming a layout. `_wait_for_start_menu` and
# `_select_start_menu_row` are pure poll/tap/verify logic over addresses
# passed in directly, so they're testable against a fake with no ELF, no
# devkitARM, and no mgba -- `_start_menu_state_addrs` (nm) and
# `_menu_action_save_index` (source parse) are the only pieces that touch the
# real engine build, covered separately below (needs_build).

class _FakeMenuEmu:
    """Stand-in for the handful of primitives save_in_game's menu navigation
    touches: run()/u8()/read_bytes()/field_locked()/tap()/screenshot().

    `count_addr`/`cursor_addr`/`actions_addr` are arbitrary fake addresses
    sharing one sparse byte store. `tap("UP"/"DOWN")` mutates the cursor byte
    directly, mirroring `HandleStartMenuInput`'s `Menu_MoveCursor`.
    `settle_after` frames stalls the count going nonzero/locked, to model
    `InitStartMenuStep` mid-build.
    """

    def __init__(self, actions: list[int], initial_cursor: int = 0,
                 settle_after: int = 0) -> None:
        self.actions_addr = 0x1000
        self.count_addr = 0x2000
        self.cursor_addr = 0x3000
        self._mem: dict[int, int] = {}
        self._actions = list(actions)
        self._cursor = initial_cursor
        self._settle_after = settle_after
        self._frame = 0
        self._locked = True
        self.taps: list[str] = []
        self.screenshots: list[str] = []
        self._sync()

    def _sync(self) -> None:
        for i, a in enumerate(self._actions):
            self._mem[self.actions_addr + i] = a
        self._mem[self.count_addr] = len(self._actions)
        self._mem[self.cursor_addr] = self._cursor

    def run(self, frames: int, keys=None, on_frame=None) -> None:
        self._frame += frames
        if self._frame >= self._settle_after:
            self._sync()
        else:
            self._mem[self.count_addr] = 0

    def u8(self, addr: int) -> int:
        return self._mem.get(addr, 0)

    def read_bytes(self, addr: int, size: int) -> bytes:
        return bytes(self._mem.get(addr + i, 0) for i in range(size))

    def field_locked(self) -> bool:
        return self._locked

    def tap(self, key: str, hold: int = 6, release: int = 6) -> None:
        self.taps.append(key)
        n = len(self._actions)
        if n == 0:
            return
        if key == "DOWN":
            self._cursor = (self._cursor + 1) % n
        elif key == "UP":
            self._cursor = (self._cursor - 1) % n
        self._sync()

    def screenshot(self, name: str):
        self.screenshots.append(name)
        return None


# actions mirror BuildNormalStartMenu's order (see start_menu.c): POKEDEX is
# flag-gated so it's omitted here, matching a player with dex+party+navless.
_NO_PARTY_ACTIONS = [2, 4, 5, 6, 7]      # BAG PLAYER SAVE OPTION EXIT
_WITH_PARTY_ACTIONS = [1, 2, 4, 5, 6, 7]  # POKEMON BAG PLAYER SAVE OPTION EXIT
_MENU_ACTION_SAVE = 5


def _wait_for_start_menu(emu):
    from rpg2gba.playtest.scenarios import _wait_for_start_menu as fn
    return fn(emu, emu.actions_addr, emu.count_addr, emu.cursor_addr)


def _select_start_menu_row(emu, actions, cursor, target):
    from rpg2gba.playtest.scenarios import _select_start_menu_row as fn
    return fn(emu, actions, cursor, emu.cursor_addr, target)


def test_wait_for_start_menu_reads_the_settled_row_list_and_cursor() -> None:
    emu = _FakeMenuEmu(_WITH_PARTY_ACTIONS, initial_cursor=2)
    actions, cursor = _wait_for_start_menu(emu)
    assert actions == _WITH_PARTY_ACTIONS
    assert cursor == 2


def test_wait_for_start_menu_waits_out_a_mid_build_read() -> None:
    """A read while `sNumStartMenuActions` is still 0 (InitStartMenuStep
    hasn't reached BuildStartMenuActions yet) must not be mistaken for a
    settled empty menu."""
    emu = _FakeMenuEmu(_NO_PARTY_ACTIONS, settle_after=20)
    actions, _ = _wait_for_start_menu(emu)
    assert actions == _NO_PARTY_ACTIONS


def test_wait_for_start_menu_fails_loud_if_it_never_settles() -> None:
    from rpg2gba.playtest.scenarios import _wait_for_start_menu as fn

    emu = _FakeMenuEmu(_NO_PARTY_ACTIONS, settle_after=10**9)
    with pytest.raises(ScenarioError, match="never settled"):
        fn(emu, emu.actions_addr, emu.count_addr, emu.cursor_addr)
    assert emu.screenshots == ["save_menu_not_up"]


def test_select_start_menu_row_navigates_without_the_pokemon_row() -> None:
    """SAVE sits at index 2 in the no-party layout -- the pre-fix hardcoded
    DOWN x2 happened to be correct here, which is exactly why the bug hid."""
    emu = _FakeMenuEmu(_NO_PARTY_ACTIONS, initial_cursor=0)
    _select_start_menu_row(emu, _NO_PARTY_ACTIONS, 0, _MENU_ACTION_SAVE)
    assert emu.taps == ["DOWN", "DOWN"]
    assert emu.u8(emu.cursor_addr) == 2


def test_select_start_menu_row_navigates_with_the_pokemon_row() -> None:
    """SAVE shifts to index 3 once POKEMON is present -- DOWN x2 would land
    on BAG here, which is the exact regression this rewrite fixes."""
    emu = _FakeMenuEmu(_WITH_PARTY_ACTIONS, initial_cursor=0)
    _select_start_menu_row(emu, _WITH_PARTY_ACTIONS, 0, _MENU_ACTION_SAVE)
    assert emu.taps == ["DOWN", "DOWN", "DOWN"]
    assert emu.u8(emu.cursor_addr) == 3


def test_select_start_menu_row_moves_up_when_cursor_starts_past_the_target() -> None:
    emu = _FakeMenuEmu(_WITH_PARTY_ACTIONS, initial_cursor=5)  # starts on EXIT
    _select_start_menu_row(emu, _WITH_PARTY_ACTIONS, 5, _MENU_ACTION_SAVE)
    assert emu.taps == ["UP", "UP"]
    assert emu.u8(emu.cursor_addr) == 3


def test_select_start_menu_row_already_on_target_taps_nothing() -> None:
    emu = _FakeMenuEmu(_WITH_PARTY_ACTIONS, initial_cursor=3)
    _select_start_menu_row(emu, _WITH_PARTY_ACTIONS, 3, _MENU_ACTION_SAVE)
    assert emu.taps == []
    assert emu.u8(emu.cursor_addr) == 3


def test_select_start_menu_row_fails_loud_when_save_is_absent() -> None:
    """Menu with no SAVE row at all (shouldn't happen in practice, but the
    fail-loud path must name the row it wanted and what it actually saw)."""
    no_save_actions = [2, 4, 6, 7]  # BAG PLAYER OPTION EXIT, no SAVE
    emu = _FakeMenuEmu(no_save_actions, initial_cursor=0)
    with pytest.raises(ScenarioError, match="no SAVE row"):
        _select_start_menu_row(emu, no_save_actions, 0, _MENU_ACTION_SAVE)
    assert emu.taps == []  # never blindly navigated
    assert emu.screenshots == ["save_menu_no_save_row"]


def test_select_start_menu_row_fails_loud_on_cursor_mismatch() -> None:
    """If the engine's cursor doesn't land where arithmetic predicted (a
    wrap, or a real engine change), this must not silently press A on the
    wrong row."""
    from rpg2gba.playtest.scenarios import _select_start_menu_row as fn

    emu = _FakeMenuEmu(_WITH_PARTY_ACTIONS, initial_cursor=0)
    # Sabotage: DOWN taps land somewhere unexpected (simulate a menu that
    # wrapped instead of clamped).
    emu.tap = lambda key, hold=6, release=6: emu.taps.append(key)  # cursor never moves
    with pytest.raises(ScenarioError, match="cursor mismatch|expected"):
        fn(emu, _WITH_PARTY_ACTIONS, 0, emu.cursor_addr, _MENU_ACTION_SAVE)
    assert emu.screenshots == ["save_menu_cursor_mismatch"]


@needs_build
def test_menu_action_save_index_matches_the_vendored_enum() -> None:
    """The parsed index must be a real column in the enum, not a guess --
    cross-checked against the game's own `MENU_ACTION_*` ordinals rather than
    hardcoding "5" a second time in the test."""
    from rpg2gba.playtest.scenarios import _menu_action_save_index

    idx = _menu_action_save_index(ENGINE)
    assert isinstance(idx, int)
    assert idx >= 0
    # MENU_ACTION_POKEDEX=0 is always first; SAVE must come after the
    # identity/party rows and before OPTION/EXIT, matching BuildNormalStartMenu.
    assert 0 < idx < 8


@needs_build
def test_start_menu_state_addrs_resolve_from_the_real_elf() -> None:
    """The static symbols must actually be present in `nm`'s output on this
    build -- if a future build strips local symbols, this is where that
    shows up, not a mysterious KeyError deep in save_in_game."""
    from rpg2gba.playtest.scenarios import _nm_static_addr

    elf = ENGINE / "pokeemerald.elf"
    for name in ("sCurrentStartMenuActions", "sNumStartMenuActions",
                 "sStartMenuCursorPos"):
        addr = _nm_static_addr(elf, name)
        assert 0x02000000 <= addr < 0x02040000  # EWRAM_DATA


@needs_build
def test_nm_static_addr_fails_loud_on_unknown_symbol() -> None:
    from rpg2gba.playtest.scenarios import _nm_static_addr
    from rpg2gba.playtest.errors import ScenarioError as SE

    with pytest.raises(SE, match="not found"):
        _nm_static_addr(ENGINE / "pokeemerald.elf", "sTotallyMadeUpSymbol")


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
    from rpg2gba.playtest.stamp import _verify_player_object_alive, stamp_rom

    rom = tmp_path / "slice.gba"
    shutil.copy(ENGINE / "pokeemerald.gba", rom)

    emu = run_scenario("moki-running-shoes", rom, ENGINE,
                       screenshot_dir=tmp_path / "shots")
    b_dash = emu.offsets["flag_sys_b_dash"]
    assert emu.flag(b_dash)
    assert rom.with_suffix(".sav").exists()

    # save_in_game (2026-08 rewrite) no longer taps blindly after the save
    # completes -- it polls field_locked() itself and only returns once the
    # engine has genuinely released control, so there is nothing left here to
    # re-trigger Auntie's dialogue (the old trailing A/B taps did, since the
    # player never stepped away from her before saving).
    assert not emu.field_locked()

    stamped = tmp_path / "stamped.gba"
    stamp_rom(rom, stamped, emu)

    # stamped ROM, no .sav: boots CONTINUE into the tested state
    boot = Emulator(stamped, ENGINE)
    boot.run(900)
    assert boot.flag(b_dash)
    assert boot.player_pos() == emu.player_pos()
    # The 2026-08-07 bug: map/pos alone can't see a dead player object.
    _verify_player_object_alive(boot, expected_pos=boot.player_pos())

    # pristine ROM, no .sav: still boots a new game (regression path)
    pristine = tmp_path / "pristine.gba"
    shutil.copy(ENGINE / "pokeemerald.gba", pristine)
    fresh = Emulator(pristine, ENGINE)
    fresh.run(900)
    assert not fresh.flag(b_dash)
    # var() by name: sane u16 value on a freshly booted save.
    val = fresh.var("VAR_TEMP_POKEMON_CHOICE")
    assert 0 <= val <= 0xFFFF
    assert fresh.var("VAR_TEMP_POKEMON_CHOICE") == fresh.var(
        fresh.resolve_constant("VAR_TEMP_POKEMON_CHOICE"))
    with pytest.raises(ScenarioError):
        fresh.var("SPECIAL_VARS_START")  # out of the flat vars[] range

    # pristine ROM + the scenario's .sav: boots CONTINUE from flash
    shutil.copy(rom.with_suffix(".sav"), pristine.with_suffix(".sav"))
    cont = Emulator(pristine, ENGINE)
    cont.run(900)
    assert cont.flag(b_dash)


@e2e
def test_snapshot_state_round_trip_restores_player_position(tmp_path: Path) -> None:
    """The primitive dump_save_blocks is built on: a real emulator's state
    must actually rewind, not merely accept the call."""
    from rpg2gba.playtest.emulator import Emulator
    from rpg2gba.playtest.scenarios import BOOT_FRAMES

    rom = tmp_path / "snap.gba"
    shutil.copy(ENGINE / "pokeemerald.gba", rom)
    emu = Emulator(rom, ENGINE)
    emu.run(BOOT_FRAMES)
    emu.walk_to(9, 7)
    before = emu.player_pos(), emu.map_location()

    state = emu.snapshot_state()
    emu.walk_to(7, 9)
    assert emu.player_pos() != before[0]  # sanity: the walk really moved us

    emu.restore_state(state)
    assert (emu.player_pos(), emu.map_location()) == before


@e2e
def test_dump_save_blocks_raises_on_a_genuinely_locked_field(tmp_path: Path) -> None:
    """Mid-dialogue (not the post-save quirk worked around above): this must
    refuse rather than capture a mirror that can't legitimately be synced."""
    from rpg2gba.playtest.emulator import Emulator
    from rpg2gba.playtest.scenarios import BOOT_FRAMES
    from rpg2gba.playtest.stamp import dump_save_blocks

    rom = tmp_path / "locked.gba"
    shutil.copy(ENGINE / "pokeemerald.gba", rom)
    emu = Emulator(rom, ENGINE)
    emu.run(BOOT_FRAMES)
    emu.walk_to(4, 5)
    emu.face("UP")
    emu.interact()  # mid-dialogue: field is genuinely locked
    assert emu.field_locked()

    with pytest.raises(ValueError, match="field controls are locked"):
        dump_save_blocks(emu)


@e2e
def test_verify_stamped_rom_catches_an_unsynced_blob(tmp_path: Path) -> None:
    """Regression test for the bug itself: a blob built the *old* way (a
    straight RAM read, no save-sync) must fail verification now, where it
    used to silently pass -- map/pos matched; the dead player object did
    not get checked."""
    from rpg2gba.playtest.emulator import Emulator
    from rpg2gba.playtest.scenarios import BOOT_FRAMES
    from rpg2gba.playtest.stamp import ROM_BASE, _BLOCKS, build_blob, verify_stamped_rom

    rom = tmp_path / "oldbug.gba"
    shutil.copy(ENGINE / "pokeemerald.gba", rom)
    emu = Emulator(rom, ENGINE)
    emu.run(BOOT_FRAMES)
    emu.walk_to(4, 5)
    emu.face("UP")
    emu.interact()
    emu.advance_dialog()
    expected, expected_pos = emu.map_location(), emu.player_pos()

    # the pre-fix dump_save_blocks: raw RAM read, no save-sync at all.
    ptrs = {
        "sb1": emu.u32(emu.symbols["gSaveBlock1Ptr"]),
        "sb2": emu.u32(emu.symbols["gSaveBlock2Ptr"]),
        "sb3": emu.u32(emu.symbols["gSaveBlock3Ptr"]),
        "storage": emu.u32(emu.symbols["gPokemonStoragePtr"]),
    }
    blocks = {name: emu.read_bytes(ptrs[name], emu.offsets[f"sizeof_{name}"])
              for name in _BLOCKS}
    blob = build_blob(emu.offsets, blocks)

    pristine = ENGINE / "pokeemerald.gba"
    stamped = tmp_path / "oldbug_stamped.gba"
    file_off = emu.symbols["gUraniumEmbeddedSave"] - ROM_BASE
    data = bytearray(pristine.read_bytes())
    data[file_off : file_off + len(blob)] = blob
    stamped.write_bytes(data)

    with pytest.raises(ValueError, match="never spawned"):
        verify_stamped_rom(stamped, ENGINE, expected, expected_pos)
