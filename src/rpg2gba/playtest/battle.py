"""Battle mini-driver for the playtest harness (ROM_TEST_DEV.md branch C1(b)).

Same poll-state design rule as `emulator.py`: never frame-count, poll a real
engine signal and act on it, with bounded frame budgets that fail loud with a
screenshot (`ScenarioError`).

C1(b): read + assert `gEnemyParty` at battle start, RAM-write enemy HP to 0,
then let the engine's own battle-end path run (real victory path, defeat
flag, post-battle script) instead of A-mashing through a real fight or
force-exiting the battle via RAM.

All engine facts below were verified against the vendored engine at
`engine/` (pinned per `engine/RPG2GBA_VENDOR.md`), not recalled from memory —
file:line citations are given at each claim.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .errors import ScenarioError

if TYPE_CHECKING:  # runtime import is lazy so the module works without bindings
    from .emulator import Emulator

logger = logging.getLogger(__name__)

# Singles-only assumption. B_POSITION_PLAYER_LEFT == 0 and
# B_POSITION_OPPONENT_LEFT == 1 (include/constants/battle.h:30-31); in a
# non-double battle only battlers 0 and 1 are ever wired up (battlers 2/3
# are the BATTLE_TYPE_DOUBLE partner slots). No slice-1 trainer battle is a
# double battle today. If one shows up, this needs generalizing via
# gBattlerPositions[]/GetBattlerAtPosition instead of hardcoded indices.
PLAYER_BATTLER = 0
OPPONENT_BATTLER = 1

# All code in this build is compiled -mthumb (offsets.py _CFLAGS), and ARM
# ELF's convention for Thumb code symbols is to set bit 0 of the symbol
# value ("BX"-style interworking address). Verified directly against the
# linked ELF:
#   $ arm-none-eabi-readelf -s engine/pokeemerald.elf | grep -w BattleMainCB2
#   333824: 08083b69   116 FUNC GLOBAL DEFAULT 5 BattleMainCB2
# vs. the .map file's 0x08083b68 (bit 0 stripped for display). Any function
# pointer read out of RAM (gMain.callback2, gBattlerControllerFuncs[]) will
# carry that low bit; any bare `pokeemerald.map` address used for comparison
# against one must be OR'd with THUMB_BIT first, or the comparison silently
# never matches.
THUMB_BIT = 1


def _thumb_fn(symbol_addr: int) -> int:
    return symbol_addr | THUMB_BIT


# Mirrors sSubstructOffsets in engine/src/pokemon.c:2380-2386. That table is
# `static`, so it doesn't survive to the link map and can't be read out of
# the ROM directly -- it is transcribed here by value and must be kept in
# sync if the engine's substruct-shuffle table ever changes. Indexed
# [substruct type][personality % 24]; SUBSTRUCT_TYPE_GROWTH (engine's
# SUBSTRUCT_TYPE_0, include/pokemon.h:238-244) is the substruct holding
# species (struct PokemonSubstruct0.species, include/pokemon.h:131).
SUBSTRUCT_TYPE_GROWTH = 0
_SUBSTRUCT_OFFSETS: tuple[tuple[int, ...], ...] = (
    (0, 0, 0, 0, 0, 0, 1, 1, 2, 3, 2, 3, 1, 1, 2, 3, 2, 3, 1, 1, 2, 3, 2, 3),
    (1, 1, 2, 3, 2, 3, 0, 0, 0, 0, 0, 0, 2, 3, 1, 1, 3, 2, 2, 3, 1, 1, 3, 2),
    (2, 3, 1, 1, 3, 2, 2, 3, 1, 1, 3, 2, 0, 0, 0, 0, 0, 0, 3, 2, 3, 2, 1, 1),
    (3, 2, 3, 2, 1, 1, 3, 2, 3, 2, 1, 1, 3, 2, 3, 2, 1, 1, 0, 0, 0, 0, 0, 0),
)


@dataclass(frozen=True)
class EnemyMon:
    """One decoded `gEnemyParty` slot."""

    slot: int
    species: int
    level: int
    hp: int
    max_hp: int


def substruct0_offset(personality: int, num_substruct_bytes: int) -> int:
    """Byte offset (from `BoxPokemon.secure`) of substruct 0's growth/species
    block for a given personality, per `GetSubstruct`
    (engine/src/pokemon.c:2390-2393): `secure.substructs[sSubstructOffsets
    [type][personality % 24]]`. Substructs are contiguous and equal-sized
    (`NUM_SUBSTRUCT_BYTES` each, include/pokemon.h:233-236), so substruct
    index * that size is the byte offset."""
    index = _SUBSTRUCT_OFFSETS[SUBSTRUCT_TYPE_GROWTH][personality % 24]
    return index * num_substruct_bytes


def decrypt_species(emu: Emulator, box_addr: int) -> int:
    """Decrypt and return the species stored in the BoxPokemon at `box_addr`.

    Mirrors `GetBoxMonData`'s `MON_DATA_SPECIES` path
    (engine/src/pokemon.c:2587-2589: `GetSubstruct0(boxMon)->species`) and
    the decryption it depends on, `DecryptBoxMon`
    (engine/src/pokemon.c:2371-2378):

        for (i = 0; i < ARRAY_COUNT(boxMon->secure.raw); i++) {
            boxMon->secure.raw[i] ^= boxMon->otId;
            boxMon->secure.raw[i] ^= boxMon->personality;
        }

    i.e. every u32 word of `secure.raw` is XORed with `personality ^ otId`
    (order doesn't matter, XOR is commutative/self-inverse) -- there is no
    per-word alternation, unlike vanilla pokeemerald's classic
    personality/otId-alternating scheme. `species` is the low 11 bits of
    substruct0's first u16 (`u16 species:11; enum Type teraType:5;`,
    include/pokemon.h:131-132 -- little-endian ARM/GCC packs bitfields
    LSB-first, so `species` occupies bits [0:11) of the containing u16,
    which is itself the low 16 bits of the first u32 word of the
    substruct). We read that whole first u32, decrypt it, and mask.
    """
    o = emu.offsets
    personality = emu.u32(box_addr + o["off_boxpkmn_personality"])
    ot_id = emu.u32(box_addr + o["off_boxpkmn_otid"])
    key = personality ^ ot_id
    substruct0_addr = (
        box_addr + o["off_boxpkmn_secure"]
        + substruct0_offset(personality, o["val_num_substruct_bytes"])
    )
    encrypted = emu.u32(substruct0_addr)
    decrypted = encrypted ^ key
    return decrypted & 0x7FF  # species:11


def in_battle(emu: Emulator) -> bool:
    """True while the battle callback owns the main loop.

    Checks `gMain.callback2 == BattleMainCB2` -- the same signal the engine
    itself uses to know a battle is still running
    (engine/src/battle_main.c:5752-5756, `WaitForEvoSceneToFinish`):

        static void WaitForEvoSceneToFinish(void)
        {
            if (gMain.callback2 == BattleMainCB2)
                gBattleMainFunc = TryEvolvePokemon;
        }

    Rejected alternative: `gBattleTypeFlags`. It's asserted when a battle is
    *set up*, but on the ordinary single-trainer win path this driver
    exercises, nothing clears it back to 0 at battle *end* -- every
    `gBattleTypeFlags = 0` in the engine is in link-battle teardown
    (cable_club.c), contest teardown (contest.c:1407), or wild-encounter
    setup/reset paths (battle_setup.c), none of which fire here. So it can't
    distinguish "no battle running" from "just finished a battle, flags
    happen to still read nonzero" as cleanly as the callback pointer can.
    """
    o = emu.offsets
    callback2 = emu.u32(emu.symbols["gMain"] + o["off_main_callback2"])
    return callback2 == _thumb_fn(emu.symbols["BattleMainCB2"])


def read_enemy_party(emu: Emulator) -> list[EnemyMon]:
    """Read `gEnemyParty` (engine/include/pokemon.h:706-707) as structured
    data: species (decrypted), level, current/max HP, for every slot up to
    `gEnemyPartyCount`. `level`/`hp`/`maxHP` live in the unencrypted tail of
    `struct Pokemon` (include/pokemon.h:283-296) and need no decryption."""
    o = emu.offsets
    count = emu.u8(emu.symbols["gEnemyPartyCount"])
    party_size = emu.resolve_constant("PARTY_SIZE")
    species_none = emu.resolve_constant("SPECIES_NONE")
    if count > party_size:
        raise ScenarioError(
            f"gEnemyPartyCount reads {count}, exceeds PARTY_SIZE "
            f"({party_size}) -- stale offsets or garbage RAM?"
        )
    base = emu.symbols["gEnemyParty"]
    mon_size = o["sizeof_pkmn"]
    mons: list[EnemyMon] = []
    for slot in range(count):
        mon_addr = base + slot * mon_size
        box_addr = mon_addr + o["off_pkmn_box"]
        species = decrypt_species(emu, box_addr)
        if species == species_none:
            raise ScenarioError(
                f"gEnemyParty slot {slot} is SPECIES_NONE within "
                f"gEnemyPartyCount ({count}) -- decode or offset bug"
            )
        mons.append(EnemyMon(
            slot=slot,
            species=species,
            level=emu.u8(mon_addr + o["off_pkmn_level"]),
            hp=emu.u16(mon_addr + o["off_pkmn_hp"]),
            max_hp=emu.u16(mon_addr + o["off_pkmn_maxhp"]),
        ))
    return mons


def zero_enemy_hp(emu: Emulator, party: list[EnemyMon]) -> None:
    """Zero every live enemy party slot's HP, and mirror it into the
    *in-battle* copy the engine actually reads turn-to-turn.

    `struct Pokemon.hp` (the party struct) is not what turn resolution
    reads. At send-out, `PokemonToBattleMon`
    (engine/src/pokemon.c:3822-3848) snapshots `MON_DATA_HP` into a
    separate `struct BattlePokemon` in `gBattleMons[battler]`
    (engine/include/battle.h:975), and it's *that* copy the damage/faint
    checks read during the battle (e.g. `gBattleMons[battler].hp == 0`,
    engine/include/battle.h:1068). The party struct is what
    `CalculatePlayerPartyCount`/post-battle housekeeping read back from
    afterwards, not what's checked mid-battle. So both copies need zeroing:

    - Every remaining party slot, so if the current battler faints and the
      engine sends out the next slot, `PokemonToBattleMon` copies in an
      already-zero HP and that mon is fainted on arrival too (no extra
      per-mon turn needed to sweep a multi-mon trainer).
    - `gBattleMons[OPPONENT_BATTLER].hp` directly, so the very next faint
      check the engine runs (after whatever move we submit) sees HP 0
      without requiring real damage to have been dealt this turn.
    """
    o = emu.offsets
    base = emu.symbols["gEnemyParty"]
    mon_size = o["sizeof_pkmn"]
    for mon in party:
        emu.write_u16(base + mon.slot * mon_size + o["off_pkmn_hp"], 0)
    battle_hp_addr = (
        emu.symbols["gBattleMons"]
        + OPPONENT_BATTLER * o["sizeof_battlepkmn"]
        + o["off_battlepkmn_hp"]
    )
    emu.write_u16(battle_hp_addr, 0)


def _submit_first_move(emu: Emulator, frame_budget: int) -> None:
    """Drive the player controller from wherever it currently is (intro
    text, trainer-sends-out messages, the FIGHT/BAG/POKEMON/RUN grid, ...)
    up through submitting move slot 0.

    The FIGHT/BAG/POKEMON/RUN state itself, `HandleInputChooseAction`
    (engine/src/battle_controller_player.c:232), is declared `static` and
    doesn't survive to the link map (confirmed: absent from
    `pokeemerald.map`, unlike its non-static sibling
    `HandleInputChooseMove` at battle_controller_player.c:690, which is
    resolvable), so it can't be polled directly by address the way
    `in_battle()` polls `BattleMainCB2`.

    Instead this relies on a property of both menus: A always either
    advances a text box, or commits whichever cursor position is currently
    selected -- and the *default* cursor position is 0 (top-left) in both
    the action grid (`gActionSelectionCursor[battler] == 0` ==
    `B_ACTION_USE_MOVE`, battle_controller_player.c:308-312) and the move
    grid (`gMoveSelectionCursor[battler] == 0` == move slot 1,
    battle_controller_player.c:705). So "tap A on every settle until the
    controller function becomes `HandleInputChooseMove`, then tap A once
    more" reaches "FIGHT, then move slot 0" without ever needing to poll
    the unresolvable intermediate state -- as long as nothing has ever
    moved either cursor off 0, which is true for a driver that only ever
    taps A.

    Non-double-battle move submission is confirmed direct-complete, no
    target-select sub-menu: `HandleInputChooseMove`'s default case
    (`canSelectTarget == 0`, battle_controller_player.c:764-775) calls
    `BtlController_Complete` immediately; the target-select branches are
    gated on `gBattleResources->bufferA[battler][1]` being true, which only
    happens in a double battle.
    """
    controller_addr = emu.symbols["gBattlerControllerFuncs"] + PLAYER_BATTLER * 4
    choose_move = _thumb_fn(emu.symbols["HandleInputChooseMove"])
    spent = 0
    while emu.u32(controller_addr) != choose_move:
        if not in_battle(emu):
            shot = emu.screenshot("battle_ended_before_move_select")
            raise ScenarioError(f"battle ended before move selection ({shot})")
        if spent >= frame_budget:
            shot = emu.screenshot("battle_menu_stuck")
            raise ScenarioError(
                f"never reached move selection within {frame_budget} frames ({shot})"
            )
        emu.tap("A")
        emu.run(20)
        spent += 26
    emu.tap("A")  # commit move slot 0
    emu.run(20)


def win_battle(
    emu: Emulator,
    *,
    start_budget: int = 1800,
    menu_budget: int = 1500,
    end_budget: int = 3000,
) -> list[EnemyMon]:
    """Wait for a battle to start, read + zero the enemy party, submit one
    move, then ride the engine's real battle-end path out to the overworld.

    Returns the `gEnemyParty` snapshot read at battle start (for scenario
    assertions against the converter-owned party contents). Fails loud with
    a screenshot on any budget exhaustion, matching `walk_to`/
    `advance_dialog`.
    """
    spent = 0
    while not in_battle(emu):
        if spent >= start_budget:
            shot = emu.screenshot("battle_never_started")
            raise ScenarioError(
                f"battle did not start within {start_budget} frames ({shot})"
            )
        emu.run(30)
        spent += 30
    # Settle: gEnemyParty/gBattlerControllerFuncs finish initializing over a
    # few frames after BattleMainCB2 first takes the main callback.
    emu.run(60)

    party = read_enemy_party(emu)
    if not party:
        shot = emu.screenshot("battle_no_enemies")
        raise ScenarioError(f"gEnemyParty has no live mons at battle start ({shot})")
    logger.info(
        "enemy party at battle start: %s",
        [(m.species, m.level, m.hp, m.max_hp) for m in party],
    )
    zero_enemy_hp(emu, party)

    _submit_first_move(emu, menu_budget)

    spent = 0
    while in_battle(emu):
        if spent >= end_budget:
            shot = emu.screenshot("battle_never_ended")
            raise ScenarioError(
                f"battle did not end within {end_budget} frames after "
                f"zeroing enemy HP ({shot})"
            )
        emu.tap("A")
        emu.run(20)
        spent += 26

    if emu.field_locked():
        # Post-battle script (defeat flag, trainer dialogue) still holds
        # the overworld -- clear it the same way any other dialogue is
        # cleared.
        emu.advance_dialog()

    return party
