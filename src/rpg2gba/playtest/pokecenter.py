"""Shared Pokemon Center beat helpers: heal counter + PC.

Extracted 2026-08-14 after Kevlar Town (CH03) became the first chapter with a
Center -- B4's beat previously reimplemented the heal-counter interact/assert
sequence inline and only checked that the field released, which is exactly
the check that missed the healing scene's dropped completion tail (see
CH03_TODO.md's 2026-08-14 update and Map068_EV001_Page1's `Kernel.pbPokerus?`
conditional in `conversion_agent/transpiler.py`).

Every future chapter with a Center should call `heal_at_counter`/`use_pc`
from its own beat rather than reimplementing this -- the chapter still
declares the beat's name/description/location (`chapter.py`'s plain-Python
authoring model, ROM_TEST_DEV.md C4), this module only owns the shared
verification, same split as `battle.py`'s helpers.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import assertions
from .errors import ScenarioError

if TYPE_CHECKING:  # runtime import is lazy so the module works without bindings
    from .emulator import Emulator


def heal_at_counter(emu: Emulator, approach: tuple[int, int], facing: str, *,
                     counter_local_id: int, beat: str) -> None:
    """Walk to a Center's healing counter, accept the heal, and verify the
    whole scene completed -- not just that the field released.

    The heal itself (ruling 17, 2026-09-25): the lead is set to 1 HP before
    talking and must be back at full after -- the party is usually full when
    a test walk reaches a Center, so a full-HP read alone proves nothing.
    The scene's completion is checked separately, by the mechanism the
    pokerus-drop bug actually broke: the counter
    NPC's return-facing movement after the "restored to full health" /
    "we hope to see you again" close (`applymovement(..., face_down)` in the
    fork script), by reading `counter_local_id`'s facing off
    `gObjectEvents` once the field releases. A script that dropped that tail
    still releases the field cleanly, which is exactly why the field-lock
    check alone didn't catch it.
    """
    emu.walk_to(*approach, absorb_wild=True)
    emu.face(facing)
    assertions.damage_lead(emu, beat)
    emu.interact()
    emu.advance_dialog("A")  # commits YES at the yesnobox, mashes through the rest
    if emu.field_locked():
        shot = emu.screenshot(f"{beat}_heal_stuck")
        raise ScenarioError(
            f"{beat}: the healing counter's scene never released control "
            f"({shot})")
    assertions.require_lead_healed(emu, beat, "healing counter")
    ev = emu.object_event(counter_local_id)
    if ev.facing != "DOWN":
        shot = emu.screenshot(f"{beat}_heal_facing")
        raise ScenarioError(
            f"{beat}: the healing counter NPC (local id {counter_local_id}) "
            f"ended facing {ev.facing}, expected DOWN -- the return-facing "
            f"movement after the healing-machine animation never ran "
            f"({shot})")


def use_pc(emu: Emulator, approach: tuple[int, int], facing: str, *,
           beat: str) -> None:
    """Walk to a Center's PC, boot it through the native `EventScript_PC`
    chain, and back out via the "turn off" arm.

    `EventScript_PC` (engine/data/scripts/pc.inc) opens onto
    `ScriptMenu_CreatePCMultichoice`, a cursor-driven native menu, then (on
    the Pokemon Storage arm) `ShowPokemonStorageSystemPC` -- a full box-UI
    subsystem the harness has no spatial-navigation primitive for (same
    acknowledged gap as `ch03.py` B11's mart flow, which has "no money/bag
    primitive on Emulator"). Holding B instead of A answers every plain
    msgbox identically (per `Emulator.advance_dialog`'s own docstring) and
    then hits `MULTI_B_PRESSED` at the multichoice
    (`case MULTI_B_PRESSED, EventScript_TurnOffPC`), so this verifies the PC
    boots through the real native chain and returns control cleanly, not a
    box deposit/withdraw round-trip.
    """
    emu.walk_to(*approach, absorb_wild=True)
    emu.face(facing)
    emu.interact()
    emu.advance_dialog("B")
    if emu.field_locked():
        shot = emu.screenshot(f"{beat}_pc_stuck")
        raise ScenarioError(
            f"{beat}: the PC's native menu never returned control ({shot})")
