"""Shared playtest assertion helpers, promoted out of chapter modules.

**Why this module exists.** `PLAYTEST_AUTHORING_IMPROVEMENT.md` finding H:
every good assertion helper used to live as a private function inside
whichever chapter invented it (`_expected_arrival_facing`,
`_assert_player_facing`, `_assert_bgm` were all `kevlar.py`-only;
`_assert_near`/`_advance_to_battle`/`_flag_ssa` each existed as two
independent copies). A helper invented in `kevlar.py` (CH03) is structurally
unreachable from `route1.py` (CH02) -- which is exactly why CH01/CH02 stayed
stale against the warp-arrival-facing defect class while CH03 alone caught
it. The rule that fixes the cause: an assertion helper that generalizes is
promoted here, once, so a future chapter -- or a future *pass* over a prior
chapter -- can just import it.

**This is a behaviour-preserving move**, not a redesign. Every function below
is the same code that used to live in `chapters/{moki,route1,kevlar}.py`,
with duplicate copies collapsed and generalized only where the duplicates
were already identical or trivially parameterizable. See each function's
docstring for its origin and, where two copies differed, which behaviour was
kept and why.

**What deliberately stayed chapter-local** (not promoted, see
`chapters/route1.py`/`chapters/kevlar.py` for the originals):

- `route1.py`'s `_walk_absorbing`/`_step_absorbing`/the whole sight-trainer
  approach machinery (`_approach_sight_trainer`, `_sight_lane_tiles`,
  `_effective_trainer_facing`, `_ride_into_trainer_battle`,
  `_assert_no_second_battle`, `_battle_trainer`, `_rock_smash_refused`) --
  genuinely Route-1-specific (wild-grass/sight-cone battle absorption), and
  the test for promotion ("would a future chapter want this as-is") fails:
  a map with no wild encounters (Kevlar) has no use for battle-absorbing
  navigation, and a future outdoor route would need its own encounter-rate
  tuning (`_MAX_ABSORBED_INTERRUPTIONS`'s binomial-tail comment is Route-1
  specific), not this exact constant.
- `route1.py`'s/`kevlar.py`'s `_approach_moving_npc`/`_approach_patrol_npc`
  -- near-duplicates of each other, but the route1 version routes through
  `_walk_absorbing` (battle-absorbing) while kevlar's uses a plain
  `emu.walk_to` (Kevlar's roster has no wild encounters at all, module
  docstring). Promoting either one would either silently drop battle
  absorption or add dead machinery to a chapter with nothing to absorb.
  Both stay local; a future chapter with patrolling NPCs and wild
  encounters should look at both before writing a third copy.
- `kevlar.py`'s `_refuse_joke`, `_b17_retired_wall_assertion` (route1),
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
from pathlib import Path
from typing import TYPE_CHECKING

from .battle import decrypt_species
from .errors import ScenarioError

if TYPE_CHECKING:  # runtime import is lazy so this module is importable without bindings
    from .emulator import Emulator


# -- navigation primitives ----------------------------------------------------
#
# Byte-identical across `moki.py`, `route1.py`, and `kevlar.py` at the time
# of promotion (2026-08-20) for `at_map`/`require_map`/`try_step`/
# `wait_for_map`. `cross_threshold`/`enter_door` are identical between
# `moki.py` and `kevlar.py`; `route1.py` keeps its own local override (see
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
    emu.walk_to(*approach)
    try_step(emu, direction)
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
    emu.walk_to(dx, dy + 1)
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
    emu.walk_to(tx + dx, ty + dy)
    emu.run(hold, [direction])
    wait_for_map(emu, beat, dest_map)


def assert_near(emu: Emulator, beat: str, expected: tuple[int, int],
                 tolerance: int = 1) -> None:
    """Byte-identical in `route1.py` and `kevlar.py` at promotion time."""
    x, y = emu.player_pos()
    ex, ey = expected
    if abs(x - ex) > tolerance or abs(y - ey) > tolerance:
        shot = emu.screenshot(f"{beat}_wrong_landing")
        raise ScenarioError(
            f"{beat}: landed at ({x},{y}), expected near {expected} "
            f"(tolerance {tolerance}) ({shot})")


def advance_to_battle(emu: Emulator, max_taps: int = 1500) -> int:
    """`emu.advance_dialog()`, but stopping if a battle starts.

    Byte-identical in `moki.py` and `route1.py` at promotion time. A script
    that ends in a battle gives no field-control release to stop on -- an
    A-mash would keep pressing straight through the battle's own menus and
    resolve it by accident. A beat that owns the battle needs it handed over
    still running, so this stops on either boundary."""
    from .battle import in_battle
    return emu.advance_dialog(max_taps=max_taps, stop=lambda: in_battle(emu))


def flag_ssa(map_num: int, event_id: int, letter: str = "A") -> str:
    """The self-switch flag name for an item ball / berry / one-time-grant
    event: `FLAG_MAP<map>_EVENT<id>_SS<letter>`.

    Promoted from `kevlar.py`'s general two-argument-plus-map form.
    `route1.py` carried a near-duplicate hardcoded to Map033
    (`_flag_ssa(event_id, letter="A")`); it is now a thin wrapper over this
    function (`flag_ssa(33, event_id, letter)`), not a second
    implementation -- same behaviour, one source."""
    return f"FLAG_MAP{map_num:03d}_EVENT{event_id:03d}_SS{letter}"


# -- warp-arrival facing (finding H's flagship case) --------------------------
#
# Promoted verbatim from `kevlar.py` (2026-08-19 task). CH01/CH02 never
# asserted arrival facing at all -- this is the fix for that staleness
# (`PLAYTEST_AUTHORING_IMPROVEMENT.md` Part 4.5, Backlog 1).

#: engine DIR_* -> the harness's own facing-string convention
#: (`_decode_facing`/`ObjectEventState.facing`, `emulator.py`), same mapping
#: `_FACING_OFFSET_KEYS` there encodes in the other direction.
_DIR_CONST_TO_FACING: dict[str, str] = {
    "DIR_NORTH": "UP", "DIR_SOUTH": "DOWN", "DIR_EAST": "RIGHT", "DIR_WEST": "LEFT",
}


def expected_arrival_facing(dest_uid: int, x: int, y: int) -> str:
    """The harness facing string this build's OWN pipeline assigns to a real
    warp arrival -- runs `compute_arrival_facings` over the staged slice
    (`output/uranium-build/maps/*.json` + `tilesets.json` +
    `reference/warp_facing_overrides.json`, the exact inputs `build_slice_
    maps` feeds it), not a literal `"UP"` -- so a future registry/converter
    change that shifts the derived direction fails a beat that uses this
    instead of leaving it silently green. This property is load-bearing;
    do not replace the live `compute_arrival_facings` call with a cached or
    hardcoded table."""
    from ..tileset_converter import metadata_wiring as mw
    from ..tileset_converter.map_set import SLICE_MAP_IDS

    out = Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build"
    maps_dir = out / "maps"
    slice_set = set(SLICE_MAP_IDS)
    maps = {
        uid: json.loads((maps_dir / f"Map{uid:03d}.json").read_text(encoding="utf-8"))
        for uid in SLICE_MAP_IDS
    }
    warp_lists = {
        uid: [spec for _event, spec in mw.classify_map_events(maps[uid], slice_set)[1]]
        for uid in SLICE_MAP_IDS
    }
    tilesets = json.loads((out / "tilesets.json").read_text(encoding="utf-8"))
    facings = mw.compute_arrival_facings(warp_lists, maps, tilesets=tilesets)

    for f in facings.get(dest_uid, []):
        if (f.x, f.y) == (x, y):
            return _DIR_CONST_TO_FACING[f.dir_const]
    raise ScenarioError(
        f"expected_arrival_facing: map {dest_uid} arrival ({x},{y}) has no "
        f"row in compute_arrival_facings' own output -- nothing to compare "
        f"the live ROM facing against")


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
            f"live from compute_arrival_facings over this build's own "
            f"staged output) ({shot})")


# -- post-warp BGM (kevlar.py's companion to the facing class) ---------------

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
# `moki.py`'s `_player_starter_species` (slot 0 only, no scan) and
# `kevlar.py`'s `_party_has_magikarp` (scans every slot for one species,
# stopping at the first SPECIES_NONE) read the same underlying struct via
# `battle.decrypt_species` but were never unified. Both behaviours are kept
# exactly, expressed as two thin functions over one shared scan
# (`read_party_species`) plus the original single-slot read.

def player_starter_species(emu: Emulator) -> int:
    """Decode slot 0 of `gPlayerParty` the same way `battle.py` decodes
    `gEnemyParty` -- both are `struct Pokemon`, and the offsets battle.py
    already probes (`off_pkmn_box`, box-substruct fields) are struct-generic,
    not enemy-party-specific. Promoted verbatim from `moki.py`: this is a
    direct slot-0 read (no SPECIES_NONE early-out), so it can return
    SPECIES_NONE itself if the party is empty -- exactly what B8's "no
    starter placed yet" check in `moki.py` relies on."""
    o = emu.offsets
    box_addr = emu.symbols["gPlayerParty"] + o["off_pkmn_box"]
    return decrypt_species(emu, box_addr)


def read_party_species(emu: Emulator) -> list[int]:
    """Every non-empty party slot's species, in slot order, stopping at the
    first `SPECIES_NONE` (mirrors `GetPartyCount`'s data-driven counting
    rather than assuming all `PARTY_SIZE` slots are populated). Promoted
    from `kevlar.py`'s `_party_has_magikarp` scan loop, generalized to
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


def party_has_species(emu: Emulator, species_id: int) -> bool:
    """Whether `species_id` occupies any party slot. Promoted from
    `kevlar.py`'s `_party_has_magikarp`, generalized from a hardcoded
    SPECIES_MAGIKARP lookup to an explicit parameter -- same scan, same
    early-out at the first empty slot."""
    return species_id in read_party_species(emu)
