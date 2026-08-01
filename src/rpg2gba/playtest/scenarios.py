"""Scripted playthrough scenarios. One function per scenario; each drives an
Emulator from power-on, asserts the outcomes it exists to test, and finishes
with an in-game save so the resulting state is a legitimate saved game
(required for embedded-save stamping).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from .errors import ScenarioError

if TYPE_CHECKING:  # runtime import is lazy so the registry works without bindings
    from .emulator import Emulator

logger = logging.getLogger(__name__)

BOOT_FRAMES = 600


def moki_running_shoes(emu: Emulator) -> None:
    """Slice-1 story chain step 2: Auntie's Running Shoes (Map049).

    Boot (intro-skip) -> walk to Auntie -> full dialogue -> FLAG_SYS_B_DASH
    set -> in-game save.
    """
    b_dash = emu.offsets["flag_sys_b_dash"]
    emu.run(BOOT_FRAMES)
    if emu.flag(b_dash):
        raise ScenarioError("B_DASH already set at boot — stale save state?")
    emu.walk_to(4, 5)
    emu.face("UP")
    emu.interact()
    taps = emu.advance_dialog()
    logger.info("Auntie dialogue done in %d taps", taps)
    emu.screenshot("auntie_done")
    if not emu.flag(b_dash):
        raise ScenarioError("FLAG_SYS_B_DASH not set after Auntie dialogue")
    save_in_game(emu)


def save_in_game(emu: Emulator) -> None:
    """START-menu save (menu rows: BAG / player / SAVE / OPTION / EXIT)."""
    emu.tap("START")
    emu.run(30)
    emu.tap("DOWN")
    emu.tap("DOWN")
    emu.tap("A")            # select SAVE
    emu.run(90)
    emu.tap("A")            # finish printing the prompt; YES/NO appears
    emu.run(60)
    emu.tap("A")            # YES
    sav = emu.rom.with_suffix(".sav")
    for _ in range(40):     # flash write is asynchronous; poll the file
        emu.run(60)
        if sav.exists():
            break
    else:
        shot = emu.screenshot("save_failed")
        raise ScenarioError(f"in-game save produced no .sav ({shot})")
    emu.run(300)            # let "saved the game" finish
    emu.tap("A")
    emu.run(60)
    emu.tap("B")            # ensure the menu is closed
    emu.run(30)


def lab_doorstep(emu: Emulator) -> None:
    """Park the player outside the Professor's Lab, ready to walk in.

    A *hand-off* scenario, not an assertion run: it drives past the setup the
    lab scene depends on and then stops, so a human can play the whole scene
    themselves. Stamped into a ROM, booting it drops you on the doorstep.

    Chain (mirrors the moki chapter's B1-B4, minus the assertions):
    boot -> Auntie's Running Shoes (the 1F exit is gated on her) -> out of the
    house -> west across Map032's fence row to fire Theo's cameo -> walk to the
    lab door tile -> in-game save.

    Coordinates are the moki chapter's, imported rather than re-derived so
    there is one place to fix if a re-walk moves them.
    """
    from .chapters.moki import (
        AUNTIE_INTERACT,
        FENCE_TRIP_APPROACH,
        FENCE_TRIP_DIRECTION,
        HOUSE1F_EXIT_APPROACH,
        HOUSE1F_EXIT_DIRECTION,
        LAB_DOOR_MOKI_TOWN,
        _try_step,
        _wait_for_map,
    )

    emu.run(BOOT_FRAMES)

    # Auntie — the 1F exit stays blocked until she's talked to.
    emu.walk_to(*AUNTIE_INTERACT)
    emu.face("UP")
    emu.interact()
    emu.advance_dialog()
    if not emu.flag(emu.offsets["flag_sys_b_dash"]):
        raise ScenarioError("FLAG_SYS_B_DASH not set — Auntie's scene didn't run")

    # Out of the house into Map032.
    emu.walk_to(*HOUSE1F_EXIT_APPROACH)
    _try_step(emu, HOUSE1F_EXIT_DIRECTION)
    _wait_for_map(emu, "lab-doorstep", "MAP_MOKI_TOWN")
    emu.wait_for_map_grid()

    # Theo's cameo fires on a westward step off the fence row; it's an autorun
    # conversation, so let it play out before moving on.
    emu.walk_to(*FENCE_TRIP_APPROACH)
    _try_step(emu, FENCE_TRIP_DIRECTION)
    emu.advance_dialog()
    emu.run(60)

    # Stop one tile SOUTH of the lab door. Door warps need a held UP from the
    # tile below (TryDoorWarp only fires for DIR_NORTH), so parking here means
    # the ROM boots with the doorway one step away and nothing pre-triggered —
    # walking in is the player's job.
    emu.walk_to(LAB_DOOR_MOKI_TOWN[0], LAB_DOOR_MOKI_TOWN[1] + 1)
    emu.face("UP")
    emu.screenshot("lab_doorstep")
    save_in_game(emu)


SCENARIOS: dict[str, Callable[[Emulator], None]] = {
    "moki-running-shoes": moki_running_shoes,
    "lab-doorstep": lab_doorstep,
}


def run_scenario(name: str, rom: Path, engine: Path,
                 screenshot_dir: Path | None = None) -> Emulator:
    """Run a registered scenario from power-on; returns the live emulator."""
    from .emulator import Emulator

    emu = Emulator(rom, engine, screenshot_dir=screenshot_dir)
    SCENARIOS[name](emu)
    return emu
