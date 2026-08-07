"""Scripted playthrough scenarios. One function per scenario; each drives an
Emulator from power-on, asserts the outcomes it exists to test, and finishes
with an in-game save so the resulting state is a legitimate saved game
(required for embedded-save stamping).
"""
from __future__ import annotations

import logging
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from .errors import ScenarioError
from .symbols import DEVKITARM_BIN

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


# -- START-menu introspection ------------------------------------------------
#
# The START menu's row order is built at runtime (start_menu.c:
# BuildNormalStartMenu) into a live array -- a POKEMON row appears above BAG
# once the player has a party, shifting every row below it. Hardcoded cursor
# taps assume one fixed layout and silently land on the wrong row once the
# game state changes (2026-08 bug: DOWN x2 landed on BAG instead of SAVE with
# a party in hand). So the menu is read back from the engine's own state
# instead of assumed.
#
# `sCurrentStartMenuActions` / `sNumStartMenuActions` / `sStartMenuCursorPos`
# are `static` (start_menu.c) and therefore absent from the link map
# `Emulator.symbols` reads -- but confirmed present as local symbols in the
# ELF's own symbol table (`nm pokeemerald.elf`), so they're read directly from
# there rather than reached for the literal-pool-accessor tricks `symbols.py`
# uses for statics with no such entry.
#
# `MENU_ACTION_SAVE` is a plain (non-macro) enumerator local to start_menu.c's
# anonymous "Menu actions" enum -- there is no header symbol to probe via
# `resolve_constant`. Its value is recovered by parsing that enum straight out
# of the vendored source, so a reordering of the engine's own enum is picked
# up automatically instead of silently going stale.

_START_MENU_OPEN_BUDGET = 180   # frames: generous margin over InitStartMenuStep's few-frame build
_START_MENU_SETTLE_STEP = 4
_FIELD_RETURN_BUDGET = 1800     # frames: generous margin over the save flow's own SE/message timers

_MENU_ACTION_ENUM_RE = re.compile(r"enum\s*\{([^}]*?)\}", re.DOTALL)


def _nm_static_addr(elf: Path, name: str) -> int:
    """Address of a `static` data symbol, read straight out of `nm`'s output.

    Distinct from `symbols.static_addr_via_accessor`: that recovers a static
    with *no* symbol-table entry at all, by disassembling an accessor. This
    one is simpler and more direct for the case where `nm` on the ELF still
    carries the local symbol -- verified empirically for the start-menu
    statics this module needs (`nm pokeemerald.elf` lists them as local `b`
    symbols even though they never make it into the link map).
    """
    nm = DEVKITARM_BIN / "arm-none-eabi-nm"
    out = subprocess.run(
        [str(nm), str(elf)], capture_output=True, text=True, check=True,
    ).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] == name:
            return int(parts[0], 16)
    raise ScenarioError(
        f"static symbol {name!r} not found in `nm {elf}` output -- engine "
        "change, or a build that stripped local symbols?"
    )


def _start_menu_state_addrs(emu: Emulator) -> tuple[int, int, int]:
    """(actions array base, action count, cursor pos) addresses."""
    elf = emu.engine / "pokeemerald.elf"
    return (
        _nm_static_addr(elf, "sCurrentStartMenuActions"),
        _nm_static_addr(elf, "sNumStartMenuActions"),
        _nm_static_addr(elf, "sStartMenuCursorPos"),
    )


def _menu_action_save_index(engine: Path) -> int:
    """Index of `MENU_ACTION_SAVE` in start_menu.c's "Menu actions" enum.

    Parsed from the vendored source rather than hardcoded: it is a plain
    enumerator with no macro, so there is nothing for `resolve_constant`'s
    gcc-probe machinery to compile against.
    """
    src = engine / "src" / "start_menu.c"
    text = src.read_text(encoding="utf-8")
    for match in _MENU_ACTION_ENUM_RE.finditer(text):
        body = match.group(1)
        names = [
            re.split(r"//|/\*", entry, maxsplit=1)[0].strip()
            for entry in body.split(",")
        ]
        names = [n for n in names if n]
        if "MENU_ACTION_POKEDEX" not in names:
            continue  # some other anonymous enum in the same file
        if "MENU_ACTION_SAVE" not in names:
            raise ScenarioError(
                f"{src}: found the menu-action enum but it has no "
                f"MENU_ACTION_SAVE entry (parsed: {names})"
            )
        return names.index("MENU_ACTION_SAVE")
    raise ScenarioError(f"{src}: could not locate the start menu action enum")


def _wait_for_start_menu(emu: Emulator, actions_addr: int, count_addr: int,
                         cursor_addr: int) -> tuple[list[int], int]:
    """Poll until the START menu's action list and cursor have settled.

    `InitStartMenuStep` builds the row list in one shot (state 1) but only
    clamps/initialises the cursor a couple of states later (state 5), so a
    single read can catch it mid-build. Two consecutive identical reads,
    spaced apart, is the settled signal -- the same idiom `walk_to`'s replan
    loop and `_settle_frame` use elsewhere in this module for "wait for a
    transient engine process to finish" without frame-counting it.
    """
    spent = 0
    previous: tuple[tuple[int, ...], int] | None = None
    while spent < _START_MENU_OPEN_BUDGET:
        emu.run(_START_MENU_SETTLE_STEP)
        spent += _START_MENU_SETTLE_STEP
        count = emu.u8(count_addr)
        if count == 0 or not emu.field_locked():
            continue
        actions = tuple(emu.read_bytes(actions_addr, count))
        cursor = emu.u8(cursor_addr)
        current = (actions, cursor)
        if previous == current:
            return list(actions), cursor
        previous = current
    shot = emu.screenshot("save_menu_not_up")
    raise ScenarioError(
        f"START menu never settled within {_START_MENU_OPEN_BUDGET} frames "
        f"(last count={emu.u8(count_addr)}, field_locked={emu.field_locked()}) "
        f"({shot})"
    )


def _select_start_menu_row(emu: Emulator, actions: list[int], cursor: int,
                           cursor_addr: int, target_action: int) -> None:
    """Move the already-open START menu's cursor onto `target_action`'s row
    and confirm it landed there.

    `actions`/`cursor` are a settled snapshot from `_wait_for_start_menu`, so
    this is pure cursor arithmetic + taps + a verifying read -- split out from
    `save_in_game` so it is unit-testable against a fake without an ELF or a
    live ROM.
    """
    if target_action not in actions:
        shot = emu.screenshot("save_menu_no_save_row")
        raise ScenarioError(
            f"START menu has no SAVE row -- actions={actions}, "
            f"MENU_ACTION_SAVE={target_action} ({shot})"
        )
    target = actions.index(target_action)
    delta = target - cursor
    key = "DOWN" if delta > 0 else "UP"
    for _ in range(abs(delta)):
        emu.tap(key)
    landed = emu.u8(cursor_addr)
    if landed != target:
        shot = emu.screenshot("save_menu_cursor_mismatch")
        raise ScenarioError(
            f"START menu cursor at {landed} after navigating, expected "
            f"{target} for SAVE -- actions={actions} ({shot})"
        )


def save_in_game(emu: Emulator) -> None:
    """START-menu save, driven by the engine's own live menu state.

    Reads the actual row order and cursor position rather than assuming a
    fixed layout (see the block comment above) -- the row list shifts once
    the player has a party (a POKEMON row appears above BAG).

    Everything from selecting SAVE through the "already saved" overwrite
    confirmation, the "don't turn off the power" message, and the "Player
    saved the game!" payoff is engine-driven and self-paced: `ShowStartMenu`
    locks the field controls the moment START is pressed
    (`LockPlayerFieldControls`), and nothing unlocks them again until the
    save flow reaches SAVE_SUCCESS or SAVE_ERROR (`SaveCallback`,
    start_menu.c) and calls `UnlockPlayerFieldControls` itself. So mashing A
    through the whole thing with `advance_dialog` -- which stops exactly when
    the lock lifts -- both answers every YES/NO prompt (A commits whichever
    option is highlighted, and every one of them defaults to YES) and needs
    no fixed tap count for however many confirmations appear.
    """
    actions_addr, count_addr, cursor_addr = _start_menu_state_addrs(emu)
    save_action = _menu_action_save_index(emu.engine)

    emu.tap("START")
    actions, cursor = _wait_for_start_menu(emu, actions_addr, count_addr, cursor_addr)
    _select_start_menu_row(emu, actions, cursor, cursor_addr, save_action)
    emu.tap("A")  # select SAVE

    # Mash through every confirmation, the save itself, and the payoff
    # message -- the flow is self-paced and self-terminating (see docstring).
    taps = emu.advance_dialog(max_taps=600)
    logger.info("save flow ran %d taps before releasing field controls", taps)

    sav = emu.rom.with_suffix(".sav")
    for _ in range(40):     # flash write is asynchronous; poll the file
        emu.run(60)
        if sav.exists():
            break
    else:
        shot = emu.screenshot("save_failed")
        raise ScenarioError(f"in-game save produced no .sav ({shot})")

    # Belt-and-suspenders: advance_dialog already waited out the lock, but
    # confirm it (and stays confirmed) rather than trusting a single sample --
    # matches this module's poll-don't-frame-count rule for "control is truly
    # back with the player" rather than a blind trailing tap that can
    # re-trigger whatever the player happens to be standing next to.
    spent = 0
    while spent < _FIELD_RETURN_BUDGET:
        if not emu.field_locked():
            return
        emu.run(_START_MENU_SETTLE_STEP)
        spent += _START_MENU_SETTLE_STEP
    shot = emu.screenshot("save_field_still_locked")
    raise ScenarioError(
        f"field controls still locked {_FIELD_RETURN_BUDGET} frames after "
        f"the save flow released them once ({shot})"
    )


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
