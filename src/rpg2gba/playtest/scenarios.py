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


SCENARIOS: dict[str, Callable[[Emulator], None]] = {
    "moki-running-shoes": moki_running_shoes,
}


def run_scenario(name: str, rom: Path, engine: Path,
                 screenshot_dir: Path | None = None) -> Emulator:
    """Run a registered scenario from power-on; returns the live emulator."""
    from .emulator import Emulator

    emu = Emulator(rom, engine, screenshot_dir=screenshot_dir)
    SCENARIOS[name](emu)
    return emu
