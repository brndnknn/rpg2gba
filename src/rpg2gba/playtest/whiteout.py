"""White-out harness capability + reusable white-out beat helper.

Background: `REDERIVATION_PLAN.md` §14.7/§15.2 item 3/§15.6. Commit
6df46066 made `pbSetPokemonCenter` emit `setrespawn`, added the generated
`HEAL_LOCATION_*` table, and set the initial respawn anchor in
`engine/src/new_game.c` (`SetLastHealLocationWarp(HEAL_LOCATION_URANIUM_START)`).
Standing rule (§14.7, reaffirmed §15.6): a white-out beat goes in the
chapter AFTER the one that sets the anchor it proves -- CH02 proves the
initial anchor (`MetadataHome`, map 49 "Player's House 1F" at (7,7)); CH04
proves the Kevlar Town Pokemon Center anchor CH03 sets via `setrespawn
HEAL_LOCATION_KEVLAR_TOWN_POKEMON_CENTER`.

This module is a shared helper module (like `pokecenter.py`), not a
manifest archetype -- a white-out has no RPG Maker event/page behind it, so
it does not belong under `playtest/archetypes/`, which is tied to manifest
archetype classification (trainer/item_ball/warp/arrival_nudge).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from . import assertions
from .errors import ScenarioError

if TYPE_CHECKING:  # runtime import is lazy so this module works without bindings
    from .chapter import ChapterBuilder
    from .emulator import Emulator

logger = logging.getLogger(__name__)

# Staging artifact `rpg2gba.pbs_converter.heal_locations.write_entries`
# writes -- never `engine/src/data/heal_locations.gen.json`, which is the
# assembler's output, one step further downstream (see that module's own
# `DEFAULT_OUTPUT_JSON`/`write_entries` docstrings).
DEFAULT_HEAL_LOCATIONS_JSON = Path("output/uranium-build/heal_locations.json")

# Same THUMB_BIT convention as `battle.py`'s `_thumb_fn`/`THUMB_BIT` and
# `emulator.py`'s own `overworld_input_ready` (`self.symbols["CB2_Overworld"]
# | 1`) -- not imported from `battle.py` since `_thumb_fn` is private to
# that module; this is the same one-line OR every caller in this package
# does locally.
_THUMB_BIT = 1


@dataclass(frozen=True)
class HealLocationExpectation:
    """One `HEAL_LOCATION_*` entry's expected respawn (map, x, y)."""

    id: str
    map_const: str
    x: int
    y: int


def load_heal_location(
    heal_location_id: str,
    heal_locations_json: Path = DEFAULT_HEAL_LOCATIONS_JSON,
) -> HealLocationExpectation:
    """The expected respawn (map, x, y) for `heal_location_id`, read from the
    pbs_converter's staging artifact (never a coordinate literal in a
    chapter file -- CLAUDE.md §4.3).

    Fails loud if the file is missing (the emitter has not run) or the id
    is absent from it.
    """
    if not heal_locations_json.exists():
        raise ScenarioError(
            f"heal_locations.json not found at {heal_locations_json} -- "
            "run rpg2gba.pbs_converter.heal_locations.generate_entries/"
            "write_entries first"
        )
    payload = json.loads(heal_locations_json.read_text(encoding="utf-8"))
    for entry in payload.get("heal_locations", []):
        if entry["id"] == heal_location_id:
            return HealLocationExpectation(
                id=entry["id"], map_const=entry["map"],
                x=entry["x"], y=entry["y"],
            )
    raise ScenarioError(
        f"heal location id {heal_location_id!r} not found in "
        f"{heal_locations_json}"
    )


def read_last_heal_location(emu: Emulator) -> tuple[int, int]:
    """Diagnostic read of `SaveBlock1.lastHealLocation` as (mapGroup,
    mapNum) -- the raw bytes `struct WarpData`'s first two `s8` fields
    occupy (`include/global.h:672-679`). Exposed standalone so a caller can
    inspect the anchor without triggering a white-out."""
    addr = emu.sb1 + emu.offsets["off_sb1_lastheallocation"]
    return emu.u8(addr), emu.u8(addr + 1)


#: Uranium's "Starting Over" switch (switch 5), set by the fenced line in
#: `DoWhiteOut` (engine/src/overworld.c, PROJECT_TODO #108) and cleared by
#: the respawn map's converted heal autorun.
STARTING_OVER_FLAG = "FLAG_STARTING_OVER"


def force_white_out(emu: Emulator, *, beat: str, frame_budget: int = 300,
                    on_arrival: Callable[[], None] | None = None) -> None:
    """Force a white-out via `CB2_WhiteOut`, then wait for control back.

    **What this exercises, precisely stated:** `CB2_WhiteOut` ->
    `DoWhiteOut` -> `HealPlayerParty` / `SetWarpDestinationToLastHealLocation`
    / `WarpIntoMap` (`engine/src/overworld.c:395-402,1927-1951`). It does
    **not** exercise the battle-loss route into a white-out -- no "you don't
    have any more usable POKEMON" loss message, no money-penalty script,
    none of `HandleBattleLowHpMusicChange`/the battle-end white-out branch.
    This drives the shared tail directly, the same way a battle loss, a
    Dig/Escape Rope failure, or any other whiteout trigger eventually would.

    Precondition: `emu.overworld_input_ready()` -- the trigger writes
    `gMain.callback2` directly, which only makes sense from the ordinary
    field-input state (mirrors `battle.py`'s `off_main_callback2` pattern,
    `emulator.py:1281-1310`'s `overworld_input_ready`).

    Before triggering, reads `SaveBlock1.lastHealLocation` (`read_last_heal_
    location`) and fails loud if it is all zeros -- map group 0/num 0 is
    vanilla Petalburg City, and a zeroed anchor means either the seed save
    predates commit 6df46066 (the `setrespawn`/initial-anchor fix) or
    `new_game.c`'s `SetLastHealLocationWarp(HEAL_LOCATION_URANIUM_START)`
    call is missing/broken. Better to fail here, at the cause, than after
    landing on a false "correct" Petalburg coincidence.

    Triggers by writing `gMain.state = 0` then `gMain.callback2 =
    CB2_WhiteOut | THUMB_BIT` -- the same "state=0, callback2=<thumb addr>"
    handoff `battle.py`/`emulator.py` use elsewhere to hand control to a
    specific main callback. `CB2_WhiteOut` (`overworld.c:1927-1951`) counts
    `gMain.state` up to 120 (one increment per call, i.e. one per frame)
    before running `DoWhiteOut` and handing back to `CB2_Overworld` --
    `DoMapLoadLoop` (`overworld.c:2455-2458`, `while (!LoadMapInStepsLocal(
    state, FALSE));`) completes synchronously within that single call, so no
    extra frames are needed once the 120-frame counter fires.

    Polls `overworld_input_ready()` (not a fixed frame count, per this
    module's poll-state design rule) up to `frame_budget` frames, then runs
    `emu.wait_for_map_grid()` and `emu.settle_field()` to drain the arrival
    autorun chain, mirroring `archetypes/warp.py`'s own crossing convention.
    Fails loud with a screenshot on timeout.

    `on_arrival`, if given, runs after control returns and before the drain:
    the one window where the respawn map's autoruns have not run yet,
    because the arrival fade still holds the field lock.
    """
    if not emu.overworld_input_ready():
        raise ScenarioError(
            f"{beat}: force_white_out requires the overworld to be "
            "input-ready (gMain.callback2 == CB2_Overworld) before "
            "triggering CB2_WhiteOut"
        )
    map_group, map_num = read_last_heal_location(emu)
    if (map_group, map_num) == (0, 0):
        raise ScenarioError(
            f"{beat}: SaveBlock1.lastHealLocation reads (mapGroup=0, "
            "mapNum=0) -- respawn anchor never set. The seed save may "
            "predate 6df46066 (setrespawn/initial-anchor fix), or "
            "new_game.c's SetLastHealLocationWarp(HEAL_LOCATION_URANIUM_"
            "START) call is missing. (0,0) is vanilla Petalburg City, not "
            "a real Uranium anchor."
        )

    o = emu.offsets
    main_addr = emu.symbols["gMain"]
    emu.write_u8(main_addr + o["off_main_state"], 0)
    emu.write_u32(
        main_addr + o["off_main_callback2"],
        emu.symbols["CB2_WhiteOut"] | _THUMB_BIT,
    )

    spent = 0
    step = 4
    while spent < frame_budget:
        emu.run(step)
        spent += step
        if emu.overworld_input_ready():
            break
    else:
        shot = emu.screenshot(f"{beat}_whiteout_timeout")
        raise ScenarioError(
            f"{beat}: CB2_WhiteOut never handed control back to "
            f"CB2_Overworld within {frame_budget} frames ({shot})"
        )

    if on_arrival is not None:
        on_arrival()
    emu.wait_for_map_grid()
    emu.settle_field()


def whiteout_beat(
    builder: ChapterBuilder,
    *,
    beat_name: str,
    heal_location_id: str,
    description: str | None = None,
    heal_locations_json: Path = DEFAULT_HEAL_LOCATIONS_JSON,
    starting_over_rows: tuple[str, ...] = (),
) -> None:
    """Register one white-out regression beat: force a white-out and assert
    the player lands at `heal_location_id`'s registered respawn.

    No `archetype=`/`at=`, and no `rows=` of its own: a white-out itself
    has no RPG Maker event behind it (module docstring), and `at=` names a
    trigger tile, which this beat doesn't have (it triggers via a RAM write,
    not by standing anywhere).

    `starting_over_rows` (2026-09-15, PROJECT_TODO #108) is the exception:
    the respawn map's converted "Starting Over" autorun page, the heal scene
    Uranium plays on arrival. Passing its row ids claims them, and the beat
    then also asserts `FLAG_STARTING_OVER` is set when control returns
    (the engine's white-out set it) and clear once the arrival scripts have
    drained (the page ran to its end). Both halves are needed: a cleared flag
    alone cannot tell "the page ran" from "nothing ever set it".

    Deliberately does NOT assert facing: pokeemerald heal location entries
    carry no facing field (`struct HealLocation`, unlike a warp event), and
    `WarpIntoMap` resets avatar state on arrival the same way any other
    warp does -- there is nothing derived to compare against.

    Validated against the loader at REGISTRATION time when
    `heal_locations_json` already exists (fails the build immediately on a
    typo'd id, rather than 20 minutes into a ROM run); if the file doesn't
    exist yet (a from-scratch pipeline run), registration is not blocked --
    the same lookup runs again at beat-run time and fails loud there
    instead, per `load_heal_location`'s own contract.

    Restores the emulator to its pre-white-out snapshot in a `finally`, so
    the chapter continues from wherever the previous beat left it --
    including when the assertion itself fails, so a caller inspecting a
    failed run's ROM state afterward isn't stuck at the white-out anchor
    instead of where the chapter actually was. No other Python-side
    bookkeeping (`walk_to`'s planner state, frame counters) needs anything
    beyond this: `snapshot_state`/`restore_state` are whole-core snapshots
    (`emulator.py`'s own docstring), so they already cover everything a
    later beat could read.
    """
    if heal_locations_json.exists():
        # Fail loud now, not 20 minutes into a ROM run (see docstring).
        load_heal_location(heal_location_id, heal_locations_json)

    resolved_description = description or (
        f"White-out respawns at {heal_location_id} "
        "(REDERIVATION_PLAN.md §14.7/§15.6)"
    )

    def _starting_over_set_on_arrival(emu: Emulator) -> None:
        if not emu.flag(STARTING_OVER_FLAG):
            shot = emu.screenshot(f"{beat_name}_starting_over_unset")
            raise ScenarioError(
                f"{beat_name}: {STARTING_OVER_FLAG} not set when control "
                "returned from the white-out -- DoWhiteOut's fenced FlagSet "
                f"is missing from this ROM ({shot})")

    @builder.beat(beat_name, resolved_description, rows=starting_over_rows)
    def run(emu: Emulator) -> None:
        expected = load_heal_location(heal_location_id, heal_locations_json)
        state = emu.snapshot_state()
        try:
            force_white_out(
                emu, beat=beat_name,
                on_arrival=((lambda: _starting_over_set_on_arrival(emu))
                            if starting_over_rows else None))
            assertions.require_map(emu, beat_name, expected.map_const)
            if starting_over_rows and emu.flag(STARTING_OVER_FLAG):
                shot = emu.screenshot(f"{beat_name}_starting_over_stuck")
                raise ScenarioError(
                    f"{beat_name}: {STARTING_OVER_FLAG} still set after the "
                    "arrival scripts drained -- the respawn map's heal page "
                    f"never ran ({', '.join(starting_over_rows)}) ({shot})")
            assertions.assert_position_exact(
                emu, beat_name, (expected.x, expected.y))
        finally:
            emu.restore_state(state)

    del run
