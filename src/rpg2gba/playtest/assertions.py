"""Shared playtest assertion helpers, promoted out of chapter modules.

**Why this module exists.** `PLAYTEST_AUTHORING_IMPROVEMENT.md` finding H:
every good assertion helper used to live as a private function inside
whichever chapter invented it (`_expected_arrival_facing`,
`_assert_player_facing`, `_assert_bgm` were all `ch03.py`-only;
`_assert_near`/`_advance_to_battle`/`_flag_ssa` each existed as two
independent copies). A helper invented in `ch03.py` (CH03) is structurally
unreachable from `ch02.py` (CH02) -- which is exactly why CH01/CH02 stayed
stale against the warp-arrival-facing defect class while CH03 alone caught
it. The rule that fixes the cause: an assertion helper that generalizes is
promoted here, once, so a future chapter -- or a future *pass* over a prior
chapter -- can just import it.

**This is a behaviour-preserving move**, not a redesign. Every function below
is the same code that used to live in `chapters/{ch01,ch02,ch03}.py`,
with duplicate copies collapsed and generalized only where the duplicates
were already identical or trivially parameterizable. See each function's
docstring for its origin and, where two copies differed, which behaviour was
kept and why.

**What deliberately stayed chapter-local** (not promoted, see
`chapters/ch02.py`/`chapters/ch03.py` for the originals):

- `ch02.py`'s `_walk_absorbing`/`_step_absorbing`/the whole sight-trainer
  approach machinery (`_approach_sight_trainer`, `_sight_lane_tiles`,
  `_effective_trainer_facing`, `_ride_into_trainer_battle`,
  `_assert_no_second_battle`, `_battle_trainer`, `_rock_smash_refused`) --
  genuinely Route-1-specific (wild-grass/sight-cone battle absorption), and
  the test for promotion ("would a future chapter want this as-is") fails:
  a map with no wild encounters (Kevlar) has no use for battle-absorbing
  navigation, and a future outdoor route would need its own encounter-rate
  tuning (`_MAX_ABSORBED_INTERRUPTIONS`'s binomial-tail comment is Route-1
  specific), not this exact constant.
- `ch02.py`'s/`ch03.py`'s `_approach_moving_npc`/`_approach_patrol_npc`
  -- near-duplicates of each other, but the route1 version routes through
  `_walk_absorbing` (battle-absorbing) while kevlar's uses a plain
  `emu.walk_to` (Kevlar's roster has no wild encounters at all, module
  docstring). Promoting either one would either silently drop battle
  absorption or add dead machinery to a chapter with nothing to absorb.
  Both stay local; a future chapter with patrolling NPCs and wild
  encounters should look at both before writing a third copy.
- `ch03.py`'s `_refuse_joke`, `_b17_retired_wall_assertion` (route1),
  `_sight_lane_tiles` (route1) -- genuinely one-chapter content, not general
  primitives.

**Standing rule these helpers try to embody (see module docstring of the
authoring-improvement doc, "walk first, then look"):** `gObjectEvents` is
camera-bound -- `TrySpawnObjectEvents`/`RemoveObjectEventsOutsideView`
(`engine/src/event_object_movement.c:2909-2951`) only keep an NPC's slot
live while the player is within roughly one screen of it. Reading an object
event from across the map raises or lies. None of the helpers promoted here
read an NPC's object event blind -- `assert_player_facing` only reads the
player's own slot (`LOCALID_PLAYER`), which is always spawned; nothing else
here touches `gObjectEvents` at all. A future helper that does must make the
camera precondition explicit, per that rule.
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from .battle import decrypt_species
from .errors import ScenarioError

if TYPE_CHECKING:  # runtime import is lazy so this module is importable without bindings
    from .cells import RouteStep
    from .emulator import Emulator


# -- navigation primitives ----------------------------------------------------
#
# Byte-identical across `ch01.py`, `ch02.py`, and `ch03.py` at the time
# of promotion (2026-08-20) for `at_map`/`require_map`/`try_step`/
# `wait_for_map`. `cross_threshold`/`enter_door` are identical between
# `ch01.py` and `ch03.py`; `ch02.py` keeps its own local override (see
# module docstring) because it must route through `_walk_absorbing` instead
# of a plain `emu.walk_to` -- Route 1 has wild grass and roaming trainer
# sight cones that a bare `walk_to` has no way to fight past. That is the
# stricter behaviour for a route with incidental battle traffic; it was
# preserved in place rather than folded in here, since forcing it on Kevlar
# (zero wild encounters, module docstring) or Moki would add dead machinery
# for no benefit.


def at_map(emu: Emulator, map_const: str) -> bool:
    group, num = emu.map_location()
    return (group, num) == (
        emu.resolve_constant(f"MAP_GROUP({map_const})"),
        emu.resolve_constant(f"MAP_NUM({map_const})"),
    )


def require_map(emu: Emulator, beat: str, map_const: str) -> None:
    if at_map(emu, map_const):
        return
    group, num = emu.map_location()
    shot = emu.screenshot(f"{beat}_wrong_map")
    raise ScenarioError(
        f"{beat}: expected map {map_const} but map_location() reads "
        f"group={group} num={num} ({shot})"
    )


def try_step(emu: Emulator, direction: str) -> bool:
    """Attempt exactly one step, without `walk_to`'s retry-until-arrived
    loop -- for beats where a *successful* step should trigger a
    redirect/refusal (the player gets pushed back) rather than actually
    settling on the target tile, or where the crossing step itself needs to
    be isolated from a preceding `walk_to`. 40 frames to detect a coord
    change, then a 16-frame settle -- mirrors `walk_to`'s own per-step
    budget so the two primitives behave consistently."""
    before = emu.player_pos()
    moved = False
    for _ in range(40):
        emu.run(1, [direction])
        if emu.player_pos() != before:
            moved = True
            break
    emu.run(16)
    return moved


def wait_for_map(emu: Emulator, beat: str, map_const: str,
                  frame_budget: int = 900) -> None:
    """Wait out a warp (script-driven or door), then assert where we
    landed. Deliberately does *not* drain the arrival's field lock -- a
    caller may want to assert an autorun scene is running the instant it
    arrives."""
    spent = 0
    while spent < frame_budget and not at_map(emu, map_const):
        emu.run(10)
        spent += 10
    require_map(emu, beat, map_const)


def cross_threshold(emu: Emulator, beat: str, approach: tuple[int, int],
                     direction: str, dest_map: str) -> None:
    """Step onto a transition tile from the tile beside it, then confirm the
    map change. Never `walk_to` a transition tile directly: `walk_to` aborts
    loud when a step changes the map (that guard is what catches an
    accidental warp), so a deliberate crossing has to be the step *after*
    the walk, not part of it."""
    emu.walk_to(*approach, absorb_wild=True)
    try_step(emu, direction)
    wait_for_map(emu, beat, dest_map)


def cross_connection(emu: Emulator, beat: str, edge_cell: tuple[int, int],
                     direction: str, dest_map: str, budget: int = 240) -> None:
    """Cross a real pokeemerald map CONNECTION: stand on `edge_cell` (on the
    map's own edge) and hold `direction` until the map changes.

    No tile triggers a connection -- the engine swaps maps when the player
    walks off the edge -- so this is `cross_threshold` without the single
    step (one tap can be eaten by a turn-in-place) and without a trigger
    tile: hold in short chunks, stop the moment the map flips (holding on
    would walk the player further into the new map)."""
    if direction not in _ARROW_APPROACH_DELTA:
        raise ScenarioError(
            f"{beat}: cross_connection got direction {direction!r}, "
            f"expected one of {sorted(_ARROW_APPROACH_DELTA)}")
    emu.walk_to(*edge_cell, absorb_wild=True)
    spent = 0
    while spent < budget and not at_map(emu, dest_map):
        emu.run(4, [direction])
        spent += 4
    wait_for_map(emu, beat, dest_map)


def enter_door(emu: Emulator, beat: str, door: tuple[int, int],
                dest_map: str, hold: int = 48) -> None:
    """Walk into a door warp from the south, holding the D-pad.

    Door warps are not step-on warps. `TryDoorWarp`
    (`engine/src/field_control_avatar.c:1098-1112`) fires only for
    `DIR_NORTH`, and only from the held-direction branch -- so the player
    must step onto the door tile *and keep holding UP*. A `try_step`-style
    tap arrives on the tile and stands there."""
    dx, dy = door
    emu.walk_to(dx, dy + 1, absorb_wild=True)
    emu.run(hold, ["UP"])
    wait_for_map(emu, beat, dest_map)


_ARROW_APPROACH_DELTA = {"UP": (0, 1), "DOWN": (0, -1),
                         "LEFT": (1, 0), "RIGHT": (-1, 0)}


def cross_arrow_warp(emu: Emulator, beat: str, tile: tuple[int, int],
                     direction: str, dest_map: str, hold: int = 48) -> None:
    """Cross a map-edge ARROW warp (`MB_*_ARROW_WARP`), holding the D-pad.

    Arrow warps are not step-on warps and not door warps. `TryArrowWarp`
    (`engine/src/field_control_avatar.c`) fires only when the player is
    STANDING ON the arrow tile with `input->heldDirection` latched and
    `dpadDirection` equal to the arrow's direction -- and `heldDirection`
    only latches at `T_TILE_CENTER`/`T_NOT_MOVING`. So, exactly like
    `enter_door`, a `try_step`-style tap arrives on the tile, releases, and
    stands there forever. The player must step onto the tile and KEEP
    holding.

    Approach is computed from `direction` so the final held step is the one
    that lands on the arrow tile -- never `walk_to` the arrow tile itself,
    for `cross_threshold`'s reason (`walk_to` aborts loud when a step
    changes the map, which is the guard that catches accidental warps).
    """
    if direction not in _ARROW_APPROACH_DELTA:
        raise ScenarioError(
            f"{beat}: cross_arrow_warp got direction {direction!r}, "
            f"expected one of {sorted(_ARROW_APPROACH_DELTA)}")
    tx, ty = tile
    dx, dy = _ARROW_APPROACH_DELTA[direction]
    emu.walk_to(tx + dx, ty + dy, absorb_wild=True)
    emu.run(hold, [direction])
    wait_for_map(emu, beat, dest_map)


def assert_near(emu: Emulator, beat: str, expected: tuple[int, int],
                 tolerance: int = 1) -> None:
    """Byte-identical in `ch02.py` and `ch03.py` at promotion time."""
    x, y = emu.player_pos()
    ex, ey = expected
    if abs(x - ex) > tolerance or abs(y - ey) > tolerance:
        shot = emu.screenshot(f"{beat}_wrong_landing")
        raise ScenarioError(
            f"{beat}: landed at ({x},{y}), expected near {expected} "
            f"(tolerance {tolerance}) ({shot})")


def assert_arrival_settled(emu: Emulator, beat: str, arrival: tuple[int, int],
                           *, nudged: bool) -> None:
    """The landing check for a warp arrival that an RMXP arrival autorun
    (the `arrival_nudge` archetype) governs.

    Drains the destination's arrival scripts, fails if the field is still
    locked, then checks where the player ended up relative to `arrival`
    (derive it with `cells.arrival_cell`, never a literal):

    - `nudged=True`: the arrival lands on the nudging event's own tile, so
      the player must end exactly one tile off it.
    - `nudged=False`: the arrival lands elsewhere, so the map's nudge
      autoruns run but must move nobody -- the player stays on `arrival`.

    The assembler drops warp-event autorun pages as orphans, so in the ROM
    this checks the converted landing, which is what CH05's gate-passed
    `B8_nudge` observed (2026-09-14).
    """
    emu.settle_field()
    if emu.field_locked():
        shot = emu.screenshot(f"{beat}_stuck")
        raise ScenarioError(
            f"{beat}: field still locked after settling on arrival ({shot})")
    pos = emu.player_pos()
    if not nudged:
        if pos != arrival:
            shot = emu.screenshot(f"{beat}_moved_on_arrival")
            raise ScenarioError(
                f"{beat}: landed at {pos}, expected to stay on arrival cell "
                f"{arrival} -- no nudge applies to this landing ({shot})")
        return
    if pos == arrival:
        shot = emu.screenshot(f"{beat}_no_nudge")
        raise ScenarioError(
            f"{beat}: player still at arrival cell {arrival} after the "
            f"autorun settled -- expected the nudge move route to have "
            f"displaced them ({shot})")
    distance = abs(pos[0] - arrival[0]) + abs(pos[1] - arrival[1])
    if distance != 1:
        shot = emu.screenshot(f"{beat}_wrong_nudge_distance")
        raise ScenarioError(
            f"{beat}: nudged to {pos}, expected exactly one tile off arrival "
            f"cell {arrival} (got Manhattan distance {distance}) ({shot})")


def assert_position_exact(emu: Emulator, beat: str, expected: tuple[int, int]) -> None:
    """Exact player-position check, no tolerance -- unlike `assert_near`.

    For landings the engine sets precisely (a heal location's respawn tile,
    written verbatim by `WarpIntoMap` off `SetWarpDestinationToLastHealLocation`),
    where any drift at all is itself the finding, not noise to tolerate.
    """
    x, y = emu.player_pos()
    if (x, y) != expected:
        shot = emu.screenshot(f"{beat}_wrong_landing")
        raise ScenarioError(
            f"{beat}: landed at ({x},{y}), expected exactly {expected} ({shot})")


def advance_to_battle(emu: Emulator, max_taps: int = 1500) -> int:
    """`emu.advance_dialog()`, but stopping if a battle starts.

    Byte-identical in `ch01.py` and `ch02.py` at promotion time. A script
    that ends in a battle gives no field-control release to stop on -- an
    A-mash would keep pressing straight through the battle's own menus and
    resolve it by accident. A beat that owns the battle needs it handed over
    still running, so this stops on either boundary."""
    from .battle import in_battle
    return emu.advance_dialog(max_taps=max_taps, stop=lambda: in_battle(emu))


def flag_ssa(map_num: int, event_id: int, letter: str = "A") -> str:
    """The self-switch flag name for an item ball / berry / one-time-grant
    event: `FLAG_MAP<map>_EVENT<id>_SS<letter>`.

    Promoted from `ch03.py`'s general two-argument-plus-map form.
    `ch02.py` carried a near-duplicate hardcoded to Map033
    (`_flag_ssa(event_id, letter="A")`); it is now a thin wrapper over this
    function (`flag_ssa(33, event_id, letter)`), not a second
    implementation -- same behaviour, one source.

    Delegates to the registry's own namer, which names a split-map piece's
    flag after its origin map (CH06: map 14002's event 25 is
    `FLAG_MAP040_EVENT025_SSA`; the piece id compiled to nothing)."""
    from ..conversion_agent.flag_registry import self_switch_flag_name
    return self_switch_flag_name(map_num, event_id, letter)


# -- warp-arrival facing (finding H's flagship case) --------------------------
#
# Promoted verbatim from `ch03.py` (2026-08-19 task). CH01/CH02 never
# asserted arrival facing at all -- this is the fix for that staleness
# (`PLAYTEST_AUTHORING_IMPROVEMENT.md` Part 4.5, Backlog 1).

#: engine DIR_* -> the harness's own facing-string convention
#: (`_decode_facing`/`ObjectEventState.facing`, `emulator.py`), same mapping
#: `_FACING_OFFSET_KEYS` there encodes in the other direction.
_DIR_CONST_TO_FACING: dict[str, str] = {
    "DIR_NORTH": "UP", "DIR_SOUTH": "DOWN", "DIR_EAST": "RIGHT", "DIR_WEST": "LEFT",
}


#: harness facing string -> the (dx, dy) one step in that direction
_FACING_STEP: dict[str, tuple[int, int]] = {
    "UP": (0, -1), "DOWN": (0, 1), "LEFT": (-1, 0), "RIGHT": (1, 0),
}


def facing_for_direction(direction: int | None, approach: str) -> str:
    """The harness facing string a warp with RMXP transfer `direction` lands
    with, when the player crossed it facing `approach` (C5b,
    WARP_RETAIN_FACING_PROPOSAL.md §0): an explicit 2/4/6/8 is carried on the
    departure warp and wins; 0/None ("retain facing") keeps `approach`,
    because the engine keeps the facing the player walked in with
    (RPG2GBA_WARP_RETAIN_FACING). Pure -- `expected_arrival_facing` is the
    build-reading entry point."""
    from ..conversion_agent.deterministic import RMXP_DIRECTION_TO_DIR_CONST

    if approach not in _FACING_STEP:
        raise ValueError(f"facing_for_direction: approach {approach!r} is not one of "
                         f"{sorted(_FACING_STEP)}")
    if direction in (0, None):
        return approach
    try:
        return _DIR_CONST_TO_FACING[RMXP_DIRECTION_TO_DIR_CONST[direction]]
    except KeyError:
        raise ValueError(
            f"facing_for_direction: unknown RMXP transfer direction {direction!r}") from None


def arrival_landing_cell(arrival: tuple[int, int], facing: str,
                         arrives_on_door: bool) -> tuple[int, int]:
    """Where the player stands once a warp's arrival settles: the arrival
    cell itself, or -- when it is a door tile (the `warp` floor's
    `arrives_on_door`) -- one step further in the arrival `facing`, because
    the engine's door exit (`Task_ExitNonAnimDoor`, field_screen_effect.c)
    walks the player one tile in the direction they face."""
    if not arrives_on_door:
        return arrival
    dx, dy = _FACING_STEP[facing]
    return (arrival[0] + dx, arrival[1] + dy)


def expected_arrival_facing(src_map_id: int, src_cell: tuple[int, int], approach: str) -> str:
    """The harness facing string the player should arrive with after
    crossing the warp at `src_cell` on Uranium map `src_map_id` while facing
    `approach` -- read live off THIS build's own staged
    `output/uranium-build/maps/MapNNN.json` (the transfer direction the
    pipeline writes onto the departure warp_event's `"facing"`), never a
    literal, so a converter change that shifts the direction fails the beat
    instead of leaving it silently green. Fails loud when no kept warp sits
    on that cell or the warps there disagree on the direction."""
    from ..tileset_converter import metadata_wiring as mw
    from ..tileset_converter.map_set import SLICE_MAP_IDS

    out = Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build"
    map_json = json.loads(
        (out / "maps" / f"Map{src_map_id:03d}.json").read_text(encoding="utf-8"))
    directions = {
        spec.dest_dir
        for _event, spec in mw.classify_map_events(map_json, set(SLICE_MAP_IDS))[1]
        if (spec.src_x, spec.src_y) == tuple(src_cell)
    }
    if len(directions) != 1:
        raise ScenarioError(
            f"expected_arrival_facing: map {src_map_id} cell {tuple(src_cell)} yields "
            f"{len(directions)} distinct kept-warp directions {sorted(directions, key=str)} "
            f"-- expected exactly one (no kept warp there, or they disagree)")
    return facing_for_direction(directions.pop(), approach)


def assert_player_facing(emu: Emulator, beat: str, expected: str) -> None:
    """Reads only the player's own object event (`LOCALID_PLAYER`), which is
    always spawned -- unlike an NPC read, this needs no camera precondition
    (see module docstring, "walk first, then look")."""
    localid_player = emu.resolve_constant("LOCALID_PLAYER")
    actual = emu.object_event(localid_player).facing
    if actual != expected:
        shot = emu.screenshot(f"{beat.lower()}_wrong_facing")
        raise ScenarioError(
            f"{beat}: player facing {actual}, expected {expected} (derived "
            f"live from this build's own staged warp direction) ({shot})")


# -- post-warp BGM (ch03.py's companion to the facing class) ---------------

def expected_bgm_song_id(emu: Emulator, engine_map_dir: str) -> int:
    """The MUS_* id THIS build's own compiled map header
    (`engine/data/maps/<engine_map_dir>/map.json`'s `"music"` key -- the
    porymap source `make modern` actually compiles from) declares for this
    map, resolved through the same `resolve_constant` gcc probe every other
    symbol here goes through -- never a hardcoded MUS_* literal."""
    map_json = emu.engine / "data" / "maps" / engine_map_dir / "map.json"
    music = json.loads(map_json.read_text(encoding="utf-8"))["music"]
    return emu.resolve_constant(music)


def assert_bgm(emu: Emulator, beat: str, engine_map_dir: str) -> None:
    expected = expected_bgm_song_id(emu, engine_map_dir)
    actual = emu.bgm_song_id()
    if actual != expected:
        shot = emu.screenshot(f"{beat.lower()}_wrong_bgm")
        raise ScenarioError(
            f"{beat}: gMPlayInfo_BGM is playing song id {actual}, expected "
            f"{expected} (engine/data/maps/{engine_map_dir}/map.json's own "
            f"\"music\" key) -- the dropped post-warp PLAY_BGM/CHANGE_TONE "
            f"commands were NOT structurally covered by the map header "
            f"after all ({shot})")


# -- party species reads -------------------------------------------------------
#
# `ch01.py`'s `_player_starter_species` (slot 0 only, no scan) and
# `ch03.py`'s `_party_has_magikarp` (scans every slot for one species,
# stopping at the first SPECIES_NONE) read the same underlying struct via
# `battle.decrypt_species` but were never unified. Both behaviours are kept
# exactly, expressed as two thin functions over one shared scan
# (`read_party_species`) plus the original single-slot read.

def player_starter_species(emu: Emulator) -> int:
    """Decode slot 0 of `gPlayerParty` the same way `battle.py` decodes
    `gEnemyParty` -- both are `struct Pokemon`, and the offsets battle.py
    already probes (`off_pkmn_box`, box-substruct fields) are struct-generic,
    not enemy-party-specific. Promoted verbatim from `ch01.py`: this is a
    direct slot-0 read (no SPECIES_NONE early-out), so it can return
    SPECIES_NONE itself if the party is empty -- exactly what B8's "no
    starter placed yet" check in `ch01.py` relies on."""
    o = emu.offsets
    box_addr = emu.symbols["gPlayerParty"] + o["off_pkmn_box"]
    return decrypt_species(emu, box_addr)


def read_party_species(emu: Emulator) -> list[int]:
    """Every non-empty party slot's species, in slot order, stopping at the
    first `SPECIES_NONE` (mirrors `GetPartyCount`'s data-driven counting
    rather than assuming all `PARTY_SIZE` slots are populated). Promoted
    from `ch03.py`'s `_party_has_magikarp` scan loop, generalized to
    return the whole list rather than testing one species inline."""
    species_none = emu.resolve_constant("SPECIES_NONE")
    o = emu.offsets
    party_size = emu.resolve_constant("PARTY_SIZE")
    mon_size = o["sizeof_pkmn"]
    species_list: list[int] = []
    for slot in range(party_size):
        addr = emu.symbols["gPlayerParty"] + slot * mon_size + o["off_pkmn_box"]
        species = decrypt_species(emu, addr)
        if species == species_none:
            break
        species_list.append(species)
    return species_list


def read_lead_hp(emu: Emulator) -> tuple[int, int]:
    """`(hp, maxHP)` of party slot 0, from `struct Pokemon`'s unencrypted
    tail (`include/pokemon.h`)."""
    o = emu.offsets
    base = emu.symbols["gPlayerParty"]
    return emu.u16(base + o["off_pkmn_hp"]), emu.u16(base + o["off_pkmn_maxhp"])


def damage_lead(emu: Emulator, beat: str) -> None:
    """Set the lead's HP to 1, so a following heal is observable
    (REDERIVATION_PLAN.md §16.3 ruling 17: every heal the corpus plays
    happens when the party is usually full already). Fails loud on an empty
    party or a lead already at 1 max HP, where nothing could be observed."""
    hp, max_hp = read_lead_hp(emu)
    if max_hp <= 1:
        raise ScenarioError(
            f"{beat}: can't set up a heal check: lead maxHP is {max_hp} "
            "(empty party, or nothing to restore)")
    emu.write_u16(emu.symbols["gPlayerParty"] + emu.offsets["off_pkmn_hp"], 1)


def require_lead_healed(emu: Emulator, beat: str, row_id: str) -> None:
    """The heal after `damage_lead` restored the lead to max HP."""
    hp, max_hp = read_lead_hp(emu)
    if hp != max_hp:
        shot = emu.screenshot(f"{beat}_not_healed")
        raise ScenarioError(
            f"{beat}: {row_id}: lead HP is {hp}/{max_hp} after the heal, "
            f"expected full ({shot})")


def party_has_species(emu: Emulator, species_id: int) -> bool:
    """Whether `species_id` occupies any party slot. Promoted from
    `ch03.py`'s `_party_has_magikarp`, generalized from a hardcoded
    SPECIES_MAGIKARP lookup to an explicit parameter -- same scan, same
    early-out at the first empty slot."""
    return species_id in read_party_species(emu)


# Substruct type holding the four move ids (`struct PokemonSubstruct1`,
# include/pokemon.h: move1:11 + evolutionTracker1:5, move2:11 +
# evolutionTracker2:5 in the first u32; move3/move4 likewise in the second).
SUBSTRUCT_TYPE_ATTACKS = 1


def decode_box_moves(personality: int, ot_id: int, secure: bytes,
                     num_substruct_bytes: int) -> tuple[int, int, int, int]:
    """Decode the four move ids from a `BoxPokemon`'s raw encrypted `secure`
    block. Pure (no emulator): every u32 of `secure` is XORed with
    `personality ^ otId` (DecryptBoxMon), the Attacks substruct sits at
    `_SUBSTRUCT_OFFSETS[1][personality % 24]`, and its first two u32 words
    pack the moves as 11-bit fields at bit 0 and bit 16."""
    from .battle import _SUBSTRUCT_OFFSETS

    key = personality ^ ot_id
    base = _SUBSTRUCT_OFFSETS[SUBSTRUCT_TYPE_ATTACKS][personality % 24] * num_substruct_bytes
    if base + 8 > len(secure):
        raise ScenarioError(
            f"decode_box_moves: secure block of {len(secure)} bytes is too "
            f"short for the Attacks substruct at offset {base}")
    w0 = int.from_bytes(secure[base:base + 4], "little") ^ key
    w1 = int.from_bytes(secure[base + 4:base + 8], "little") ^ key
    return (w0 & 0x7FF, (w0 >> 16) & 0x7FF, w1 & 0x7FF, (w1 >> 16) & 0x7FF)


def read_party_moves(emu: Emulator) -> list[tuple[int, int, int, int]]:
    """The four move ids of each non-empty party slot, in slot order
    (stopping at the first `SPECIES_NONE`, like `read_party_species`)."""
    species_none = emu.resolve_constant("SPECIES_NONE")
    o = emu.offsets
    party_size = emu.resolve_constant("PARTY_SIZE")
    nsub = o["val_num_substruct_bytes"]
    out: list[tuple[int, int, int, int]] = []
    for slot in range(party_size):
        addr = emu.symbols["gPlayerParty"] + slot * o["sizeof_pkmn"] + o["off_pkmn_box"]
        if decrypt_species(emu, addr) == species_none:
            break
        personality = emu.u32(addr + o["off_boxpkmn_personality"])
        ot_id = emu.u32(addr + o["off_boxpkmn_otid"])
        secure = emu.read_bytes(addr + o["off_boxpkmn_secure"], nsub * 4)
        out.append(decode_box_moves(personality, ot_id, secure, nsub))
    return out


def party_knows_move(emu: Emulator, move: str) -> bool:
    """Whether any party mon knows `move` (a `MOVE_*` constant name).
    Fails loud on an unknown name (the gcc probe raises) or a non-MOVE_ name."""
    if not isinstance(move, str) or not move.startswith("MOVE_"):
        raise ScenarioError(f"party_knows_move: {move!r} is not a MOVE_* constant name")
    move_id = emu.resolve_constant(move)
    return any(move_id in moves for moves in read_party_moves(emu))


# The four cells a player can stand on to talk to an NPC, and the facing
# each one requires. Keyed by the offset FROM the NPC TO the player, so a
# live NPC position turns straight into candidate approaches.
_TALK_SIDES: tuple[tuple[tuple[int, int], str], ...] = (
    ((0, 1), "UP"),      # player south of the NPC, facing north
    ((0, -1), "DOWN"),   # player north of the NPC, facing south
    ((-1, 0), "RIGHT"),  # player west of the NPC, facing east
    ((1, 0), "LEFT"),    # player east of the NPC, facing west
)


_OPPOSITE = {"UP": "DOWN", "DOWN": "UP", "LEFT": "RIGHT", "RIGHT": "LEFT"}
_INTERCEPT_POLL_FRAMES = 4


def _intercept_route_walker(emu: Emulator, beat: str, local_id: int,
                            route: Sequence[RouteStep],
                            walk: Callable[[int, int], None]) -> None:
    """Stand on a looping custom-route walker's path and let it come to the
    player (ROM run 36: Moki Town's Chyinmunk laps a rectangle at the
    fastest frequency, and chasing its live position lost every race).

    The engine holds a non-skippable walker in place when its next step is
    blocked (`MovementType_UraniumCustomRoute_Callback`), so a player on a
    step's `target` stops it one tile away, on that step's `origin`, facing
    the player. Through steps are skipped: they walk through the player.
    Candidates are tried nearest first; a cell the walker currently holds
    or the walk cannot reach is skipped. Fails loud if no path cell can be
    reached, or if the walker does not arrive within two laps."""
    player = emu.player_pos()
    candidates = sorted(
        {s.target for s in route if not s.through},
        key=lambda c: (abs(c[0] - player[0]) + abs(c[1] - player[1]), c))
    arrivals_by_cell = {
        cell: {s.origin: _OPPOSITE[s.direction] for s in route
               if s.target == cell and not s.through}
        for cell in candidates}
    def live() -> tuple[int, int] | None:
        # `gObjectEvents` holds only what the camera can see (ROM run 37: a
        # seeded start off-screen of the loop): absent means "not here yet".
        try:
            npc = emu.object_event(local_id)
        except ScenarioError:
            return None
        return (npc.x, npc.y)

    last_seen: tuple[int, int] | None = None
    for cell in candidates:
        if live() == cell:
            continue
        try:
            walk(*cell)
        except ScenarioError:
            continue
        if emu.player_pos() != cell:
            continue
        arrivals = arrivals_by_cell[cell]
        budget = 2 * sum(s.frames for s in route)   # two laps at the route's own pace
        waited = 0
        while waited <= budget:
            pos = live()
            last_seen = pos or last_seen
            facing = arrivals.get(pos) if pos is not None else None
            if facing is not None:
                emu.face(facing)
                if emu.interact(require_script=False):
                    return
            emu.run(_INTERCEPT_POLL_FRAMES)
            waited += _INTERCEPT_POLL_FRAMES
        shot = emu.screenshot(f"{beat}_intercept_timeout")
        raise ScenarioError(
            f"{beat}: waited {budget} frames on {cell} for route walker local id "
            f"{local_id} to arrive at one of {sorted(arrivals)}; last seen at "
            f"{last_seen} ({shot})")
    if _ambush_route_walker(emu, local_id, route, candidates, walk, live):
        return
    shot = emu.screenshot(f"{beat}_intercept_unreachable")
    raise ScenarioError(
        f"{beat}: no cell of route walker local id {local_id}'s path "
        f"{candidates} could be reached to intercept it ({shot})")


def _ambush_route_walker(emu: Emulator, local_id: int, route: Sequence[RouteStep],
                         candidates: Sequence[tuple[int, int]],
                         walk: Callable[[int, int], None],
                         live: Callable[[], tuple[int, int] | None]) -> bool:
    """Fallback for `_intercept_route_walker`: stand BESIDE the path and talk
    when the walker steps onto the adjacent path cell (ROM run 68: Kevlar
    Center's map068/ev003 paces two cells, so the free one is always its
    next step and the walker wins every race onto it). Tries each path cell,
    nearest first, from each off-path side the walk can reach; waits two laps
    per side. True once an interaction starts."""
    path = {s.origin for s in route} | {s.target for s in route}
    budget = 2 * sum(s.frames for s in route)
    for cell in candidates:
        for (dx, dy), facing in _TALK_SIDES:
            side = (cell[0] + dx, cell[1] + dy)
            if side in path:
                continue
            try:
                walk(*side)
            except ScenarioError:
                continue
            if emu.player_pos() != side:
                continue
            waited = 0
            while waited <= budget:
                if live() == cell:
                    emu.face(facing)
                    if emu.interact(require_script=False):
                        return True
                emu.run(_INTERCEPT_POLL_FRAMES)
                waited += _INTERCEPT_POLL_FRAMES
    return False


def talk_to_moving_npc(emu: Emulator, beat: str, local_id: int, *,
                       walk: Callable[[int, int], None] | None = None,
                       attempts: int = 6,
                       route: Sequence[RouteStep] | None = None) -> None:
    """Interact with an NPC that does not stay where it spawned.

    A `MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE` walker invalidates a derived
    approach cell the moment it steps off its template position, and it
    invalidates it in the worst way: the NPC ends up standing ON the
    approach cell while the player stands on the NPC's vacated spawn tile.
    `walk_to` then burns its step-aside budget trying to reach a tile a
    solid object is occupying -- "B10 FAILED: stuck after 8 step-aside
    attempts at 8,7 heading for 8,8" (step-7 run 15, 2026-09-06), where
    (8,7) is the NPC's spawn cell and (8,8) the approach derived from it.

    So the approach is resolved from the NPC's LIVE `gObjectEvents` position
    on every attempt, not once up front, and the FACING is derived from
    whichever side the player actually reached -- unlike `ch04.py`/
    `archetypes/trainer.py`'s `_press_a_live`, which read a live position
    but keep a fixed facing (right for a trainer that walks to the player
    and stops, wrong for a walker that can be approached from any side).

    Retries because the NPC is still moving: it can step away between
    `walk_to` and `interact`, which is a race no single attempt can close.
    A side the player is ALREADY standing on is tried first and costs no
    walk at all, which is the common case right after the approach walk
    parked the player next to it.

    `walk` is how this helper moves one step of approach, defaulting to
    `emu.walk_to`. It is a parameter because `WalkInterrupted` is a
    `ScenarioError`, so the "that side is blocked, try another" handler
    below would otherwise swallow a wild encounter and loop with the player
    still in battle. A caller on a map with a live encounter table passes
    its own absorbing walker (CH05 passes `ch05._walk_absorbing`, Passage
    Cave being densities 15/20) so an ambush is resolved rather than
    mistaken for an unreachable tile.

    Fails loud, naming the NPC's last seen position, when every attempt is
    exhausted -- an NPC that can never be reached is a finding about the
    map or the route, not something to pass over quietly.

    `route` (`cells.custom_route_loop`) marks a looping custom-route walker:
    it never stops, so it is intercepted on its path instead of chased
    (`_intercept_route_walker`).
    """
    walk_to = walk if walk is not None else (
        lambda tx, ty: emu.walk_to(tx, ty, absorb_wild=True))
    if route:
        _intercept_route_walker(emu, beat, local_id, route, walk_to)
        return
    last_seen: tuple[int, int] | None = None
    for _ in range(attempts):
        npc = emu.object_event(local_id)
        last_seen = (npc.x, npc.y)
        player = emu.player_pos()
        sides = [((npc.x + dx, npc.y + dy), facing) for (dx, dy), facing in _TALK_SIDES]
        # Already adjacent? Use that side; no walk, no chance to lose the race.
        sides.sort(key=lambda side: side[0] != player)
        for cell, facing in sides:
            if cell != player:
                try:
                    walk_to(*cell)
                except ScenarioError:
                    continue  # blocked, or the NPC moved into it -- try the next side
                if emu.player_pos() != cell:
                    continue
            emu.face(facing)
            if emu.interact(require_script=False):
                return
            break  # reached a side but nothing fired: re-read and try again
    shot = emu.screenshot(f"{beat}_no_live_interact")
    raise ScenarioError(
        f"{beat}: could not interact with local id {local_id} after "
        f"{attempts} attempts reading its live position (last seen at "
        f"{last_seen}) ({shot})"
    )
