"""Integration test: teach HM06 (Rock Smash) through the real bag/party UI on
the CH07 walk ROM (party = one starter with 3 moves, HM06 in the bag).
Skips when mgba, the ROM, or the engine build artifacts are absent.

Build the fixture without walk extras, so the party stays the suite's:
`rpg2gba playtest walk --chapter CH08 --at-beat CH07:m035seamN040_transit
--output output/playtest-gen --no-grant --no-exp-share`."""
from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engine"
WALK_ROM = ROOT / "output/playtest-gen/walk/CH08-CH07:m035seamN040_transit.gba"

pytestmark = [
    pytest.mark.skipif(importlib.util.find_spec("mgba") is None,
                       reason="needs the mgba python bindings"),
    pytest.mark.skipif(not WALK_ROM.exists(), reason="walk ROM not built"),
    pytest.mark.skipif(not (ENGINE / "pokeemerald.elf").exists(),
                       reason="engine build (pokeemerald.elf) absent"),
]


def _boot(tmp_path: Path):
    from rpg2gba.playtest.emulator import Emulator

    rom = tmp_path / "walk.gba"
    shutil.copy(WALK_ROM, rom)
    # A stamped walk ROM boots its embedded seed save; an older one may ship a .sav.
    if WALK_ROM.with_suffix(".sav").exists():
        shutil.copy(WALK_ROM.with_suffix(".sav"), rom.with_suffix(".sav"))
    emu = Emulator(rom, ENGINE, screenshot_dir=tmp_path)
    emu.run(600)
    return emu


def test_teach_hm06_rock_smash_to_slot_0(tmp_path: Path) -> None:
    from rpg2gba.playtest.assertions import party_knows_move, read_party_moves
    from rpg2gba.playtest.scenarios import teach_hm_from_bag

    emu = _boot(tmp_path)
    assert not party_knows_move(emu, "MOVE_ROCK_SMASH")
    before = read_party_moves(emu)[0]
    assert sum(1 for m in before if m) < 4  # no forget flow needed here
    seen, caught = emu.pokedex_counts()
    assert seen >= caught >= 1

    teach_hm_from_bag(emu, "ITEM_HM06", "MOVE_ROCK_SMASH", party_slot=0)

    assert party_knows_move(emu, "MOVE_ROCK_SMASH")
    assert emu.overworld_input_ready() and not emu.field_locked()
    assert emu.bag_item_quantity("ITEM_HM06") == 1  # HMs are not consumed


def test_teach_requires_forget_slot_when_full(tmp_path: Path) -> None:
    from rpg2gba.playtest.errors import ScenarioError
    from rpg2gba.playtest.scenarios import teach_hm_from_bag

    emu = _boot(tmp_path)
    _forge_fourth_move(emu, 33)
    with pytest.raises(ScenarioError, match="forget_slot"):
        teach_hm_from_bag(emu, "ITEM_HM06", "MOVE_ROCK_SMASH", party_slot=0)


def test_teach_forget_flow_replaces_chosen_move(tmp_path: Path) -> None:
    from rpg2gba.playtest.assertions import read_party_moves
    from rpg2gba.playtest.scenarios import teach_hm_from_bag

    emu = _boot(tmp_path)
    _forge_fourth_move(emu, 33)
    before = read_party_moves(emu)[0]
    teach_hm_from_bag(emu, "ITEM_HM06", "MOVE_ROCK_SMASH", party_slot=0, forget_slot=1)
    after = read_party_moves(emu)[0]
    assert after[1] == emu.resolve_constant("MOVE_ROCK_SMASH")
    assert (after[0], after[2], after[3]) == (before[0], before[2], before[3])


def _forge_fourth_move(emu, move_id: int) -> None:
    """Fill slot 0's empty 4th move slot in RAM (fixing the box checksum so the
    mon is not a Bad Egg)."""
    from rpg2gba.playtest.battle import _SUBSTRUCT_OFFSETS

    o = emu.offsets
    box = emu.symbols["gPlayerParty"] + o["off_pkmn_box"]
    pers = emu.u32(box + o["off_boxpkmn_personality"])
    key = pers ^ emu.u32(box + o["off_boxpkmn_otid"])
    base = (box + o["off_boxpkmn_secure"]
            + _SUBSTRUCT_OFFSETS[1][pers % 24] * o["val_num_substruct_bytes"])
    w1 = emu.u32(base + 4) ^ key
    assert (w1 >> 16) & 0x7FF == 0, "slot 0 already has 4 moves"
    new_w1 = (w1 & 0xFFFF) | (move_id << 16)
    emu.write_u32(base + 4, new_w1 ^ key)

    def fold(w: int) -> int:
        return (w + (w >> 16)) & 0xFFFFFFFF

    ck = box + o["off_boxpkmn_checksum"]
    emu.write_u16(ck, (emu.u16(ck) + fold(new_w1) - fold(w1)) & 0xFFFF)
