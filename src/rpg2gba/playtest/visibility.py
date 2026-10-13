"""The on-ROM object visibility invariant (PROJECT_TODO #137).

RMXP shows an event only while its live page -- the highest-index page whose
condition holds -- has a graphic; a blank live page, or no live page at all,
means the event is not on the map. The converter turns that into hide flags,
`ON_TRANSITION` lines and refresh calls (`metadata_wiring`), and the staging
pass adds `addobject`/`removeobject` brackets. None of it was graded: a beat
checks a row's commands, never whether an object is standing there, so the
CH06 walk's mute Fufufu in the gym doorway (#135) and the stray EV141 trainer
sprite (#136) both passed 466/466.

`object_visibility_violations` is checked by the runner after every beat:
for each spawned object it reads the page conditions of the RMXP event the
object came from against the ROM's own flags and vars, and reports the object
if RMXP would not show it there. It reads the ROM, not the converter's model
of RMXP, so a detection miss, a wiring slip and a stray `addobject` all fail
the same way, at the first beat that ends with the object in view.

One direction only: an object RMXP would show but the ROM has hidden is not
reported (an erased event, a native berry tree or item ball whose hiding
state is not the RMXP self switch). An event whose live page can't be read
-- a script switch, a switch or variable nothing minted -- is skipped and
logged once. A native berry tree is skipped too: Uranium's plant script draws
it over a blank page, so a blank page there doesn't mean "not shown". Objects exist only near the camera (`TrySpawnObjectEvents`), so
this checks what the player could see, which is what matters.
"""
from __future__ import annotations

import functools
import json
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from rpg2gba.traversal.collision import load_map_json

if TYPE_CHECKING:
    from rpg2gba.conversion_agent.flag_registry import FlagRegistry
    from rpg2gba.playtest.emulator import Emulator, ObjectEventState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Unreadable:
    """A page condition this check can't evaluate on the ROM."""

    reason: str


def page_shows(page: Mapping[str, Any]) -> bool:
    """RMXP draws the page: a character sheet or a tile, at non-zero opacity."""
    graphic = page.get("graphic") or {}
    drawn = bool(graphic.get("character_name")) or graphic.get("tile_id", 0) > 0
    return drawn and graphic.get("opacity", 255) > 0


def _condition_holds(
    condition: Mapping[str, Any],
    switch: Callable[[int], bool | Unreadable],
    variable: Callable[[int], int | Unreadable],
    self_switch: Callable[[str], bool],
) -> bool | Unreadable:
    """One page's condition: True, False, or Unreadable when no atom is
    False and at least one can't be read."""
    atoms: list[bool | Unreadable] = []
    for slot in ("switch1", "switch2"):
        if condition.get(f"{slot}_valid"):
            atoms.append(switch(int(condition[f"{slot}_id"])))
    if condition.get("variable_valid"):
        value = variable(int(condition["variable_id"]))
        atoms.append(value if isinstance(value, Unreadable)
                     else value >= int(condition["variable_value"]))
    if condition.get("self_switch_valid"):
        atoms.append(self_switch(str(condition["self_switch_ch"])))
    if any(a is False for a in atoms):
        return False
    return next((a for a in atoms if isinstance(a, Unreadable)), True)


def live_page(
    pages: Sequence[Mapping[str, Any]],
    switch: Callable[[int], bool | Unreadable],
    variable: Callable[[int], int | Unreadable],
    self_switch: Callable[[str], bool],
) -> int | None | Unreadable:
    """RMXP's page pick: the highest-index page whose condition holds, None
    if none does, Unreadable if an unreadable page sits above the winner."""
    for idx in range(len(pages) - 1, -1, -1):
        verdict = _condition_holds(pages[idx].get("condition") or {},
                                   switch, variable, self_switch)
        if verdict is True:
            return idx
        if isinstance(verdict, Unreadable):
            return verdict
    return None


@dataclass(frozen=True)
class Violation:
    map_id: int
    event_id: int
    local_id: int
    x: int
    y: int
    page: int | None        # the live page (blank), or None: no page is live
    invisible: bool

    def describe(self) -> str:
        why = ("no page is live" if self.page is None
               else f"live page p{self.page} has no graphic")
        drawn = "spawned invisible (still blocks)" if self.invisible else "drawn"
        return (f"map{self.map_id:03d}/ev{self.event_id:03d} (local id {self.local_id}) "
                f"is {drawn} at ({self.x},{self.y}), but {why} -- RMXP shows nothing there")


@functools.cache
def _map_events(map_id: int) -> dict[int, dict[str, Any]]:
    return {e["id"]: e for e in load_map_json(map_id).get("events", []) or [] if e}


@functools.cache
def _event_for_local_id(map_id: int) -> dict[int, int]:
    """local id -> RMXP event id, from the staged table (`cells.local_id`'s
    source). A spawned object on a map with no table is stale staging."""
    from rpg2gba.playtest.cells import _local_id_table_path

    path = _local_id_table_path(map_id)
    if not path.exists():
        raise FileNotFoundError(
            f"visibility check: map {map_id} has spawned objects but no local-id "
            f"table at {path} -- re-run scripts/stage_slice_scripts.py")
    table = json.loads(path.read_text(encoding="utf-8"))
    return {int(lid): int(eid) for eid, lid in table.items()}


def _berry_tree(map_id: int, event_id: int) -> bool:
    from rpg2gba.playtest.cells import native_berry_tree_id

    return native_berry_tree_id(map_id, event_id) is not None


_LOGGED_UNREADABLE: set[tuple[int, int]] = set()


def _readers(registry: "FlagRegistry", map_id: int, event_id: int,
             flag: Callable[[str], bool], var: Callable[[str], int]):  # noqa: ANN202
    def switch(switch_id: int) -> bool | Unreadable:
        if registry.is_script_switch(switch_id):
            return Unreadable(f"switch {switch_id} is a script switch")
        name = registry.get_flag(switch_id)
        return Unreadable(f"switch {switch_id} has no minted flag") if name is None else flag(name)

    def variable(var_id: int) -> int | Unreadable:
        name = registry.get_var(var_id)
        return Unreadable(f"variable {var_id} has no minted var") if name is None else var(name)

    def self_switch(letter: str) -> bool:
        # Unminted: nothing on the ROM writes it, so it reads OFF.
        name = registry.get_self_switch(map_id, event_id, letter)
        return False if name is None else flag(name)

    return switch, variable, self_switch


def _names_for(registry: "FlagRegistry", map_id: int, event: Mapping[str, Any]) -> set[str]:
    """Every FLAG_/VAR_ name `event`'s page conditions read, so one probe
    compile resolves them all."""
    names: set[str | None] = set()
    for page in event.get("pages", []) or []:
        cond = page.get("condition") or {}
        for slot in ("switch1", "switch2"):
            if cond.get(f"{slot}_valid"):
                names.add(registry.get_flag(int(cond[f"{slot}_id"])))
        if cond.get("variable_valid"):
            names.add(registry.get_var(int(cond["variable_id"])))
        if cond.get("self_switch_valid"):
            names.add(registry.get_self_switch(map_id, event["id"], str(cond["self_switch_ch"])))
    return {n for n in names if n is not None}


def object_visibility_violations(
    emu: "Emulator", registry: "FlagRegistry",
) -> list[Violation]:
    """Spawned objects RMXP would not show, given the ROM's flags and vars."""
    candidates: list[tuple[ObjectEventState, int, dict[str, Any]]] = []
    for obj in emu.object_events():
        if obj.map_group is None or obj.map_num is None:
            raise ValueError("visibility check: the offsets table has no mapGroup/mapNum")
        map_id = emu.uranium_map_id(obj.map_group, obj.map_num)
        event_id = _event_for_local_id(map_id).get(obj.local_id)
        if event_id is None:
            continue  # the player, the camera: no RMXP event behind it
        event = _map_events(map_id).get(event_id)
        if event is None:
            raise ValueError(
                f"visibility check: map {map_id} local id {obj.local_id} names "
                f"event {event_id}, which Map{map_id:03d}.json does not have")
        if _berry_tree(map_id, event_id):
            # Uranium's plant script draws the soil/plant at run time over a
            # blank page; the ROM runs it as a native berry tree, which must
            # be spawned to show its soil (Map033 EV101).
            continue
        candidates.append((obj, map_id, event))
    names = sorted(set().union(*(_names_for(registry, m, e) for _, m, e in candidates)))
    if names:
        emu.resolve_constants(names)

    found: list[Violation] = []
    for obj, map_id, event in candidates:
        pages = event.get("pages", []) or []
        live = live_page(pages, *_readers(registry, map_id, event["id"], emu.flag, emu.var))
        if isinstance(live, Unreadable):
            if (map_id, event["id"]) not in _LOGGED_UNREADABLE:
                _LOGGED_UNREADABLE.add((map_id, event["id"]))
                logger.info("visibility check skips map%03d/ev%03d: %s",
                            map_id, event["id"], live.reason)
            continue
        if live is not None and page_shows(pages[live]):
            continue
        found.append(Violation(map_id=map_id, event_id=event["id"], local_id=obj.local_id,
                               x=obj.x, y=obj.y, page=live, invisible=obj.invisible))
    return found


def check_object_visibility(emu: "Emulator", beat_name: str) -> None:
    """Raise `ScenarioError` naming every violation, with a screenshot. A
    beat that ends mid-scene (field locked) is skipped: a hidden actor is
    spawned for its choreography until the script removes it."""
    from rpg2gba.playtest.archetypes.generic import _flag_registry
    from rpg2gba.playtest.errors import ScenarioError

    if emu.field_locked():
        logger.info("visibility check skipped after %s: field still locked", beat_name)
        return
    found = object_visibility_violations(emu, _flag_registry())
    if not found:
        return
    shot = emu.screenshot(f"{beat_name}_visibility")
    raise ScenarioError(
        f"{beat_name}: {len(found)} object(s) on the map that RMXP would not show "
        f"({shot}): " + "; ".join(v.describe() for v in found))
