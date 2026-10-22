"""The escort template: talk to an NPC whose page transfers the player, and
ride the script to where it lands (REDERIVATION_PLAN.md §16.3, C9 grading
ruling 11).

An action-button page that contains a Transfer Player is not a warp tile:
nothing happens when the player steps on it. The player walks to a side of
the NPC, faces it, presses A, reads the text, and the script walks them off
and warps them. So the body:

1. walks to the approach cell on the origin map and presses A;
2. checks the page's text as it plays;
3. mashes through the rest of the script until the map changes, and checks
   the landing map and cell at once -- before `settle_field`, because the
   destination's arrival autoruns may move the player (NurseTut's Center
   tour does);
4. drains the arrival autoruns, then checks the page's state writes and
   that the field is released.

There is no rewind (ruling 11): the escort's state writes are what later
rows depend on (NurseTut's flag gates the Center's tour), so the player is
left where the ride leaves them and the route plans on from there. The page
fires once, so only the arms that one firing takes are claimed; the
generator drops the rest as `unselected_arm`.

The transpiler hoists writes the RMXP page makes after its transfer above
the warp (pokeemerald halts the script at `warp`), so every state write has
happened by the time the player lands.

Declared kinds are the ones the body checks: `trigger`, `text`, `var_text`,
`warp` (landing map and cell), the persistent state writes, and
`completes`. Any other floor kind (an item grant, a choice) is left
undeclared and stays reported.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from rpg2gba.beat_floor.assertion import RowFloor
from rpg2gba.beat_floor.lookup import floor_for_row as _default_floor_for_row
from rpg2gba.chapter_manifest.schema import parse_row_id
from rpg2gba.playtest import assertions
from rpg2gba.playtest.archetypes import (
    FloorLookup,
    declare_assertions,
    facing_toward,
    map_uranium_id,
)
from rpg2gba.playtest.archetypes.generic import STEP_HANDLERS, Step, steps_for
from rpg2gba.playtest.cells import approach_to, event_cell
from rpg2gba.playtest.chapter import BeatLocation, ChapterBuilder

if TYPE_CHECKING:  # runtime import is lazy so this module works without mGBA bindings
    from rpg2gba.playtest.emulator import Emulator

#: Checked while the script plays, before the transfer.
_RIDE_KINDS: frozenset[str] = frozenset({"text", "var_text", "count_text"})
#: Checked once the player has landed and the arrival has settled.
_STATE_KINDS: frozenset[str] = frozenset(
    {"switch_write", "var_write", "self_switch_write", "engine_flag_write"})

ESCORT_EXECUTED_KINDS: frozenset[str] = frozenset(
    {"trigger", "completes", "warp"} | _RIDE_KINDS | _STATE_KINDS)


def _landing(floor: RowFloor, dest_map_constant: str, *, beat_name: str) -> tuple[int, int]:
    """The cell the ride lands on, from the page's one `warp` assertion.
    Fails loud when the destination disagrees with `dest_map_constant`, or
    when the landing is a door tile whose exit step depends on a facing the
    ride leaves undetermined (a retained-facing transfer)."""
    warps = [a for a in floor.assertions if a.kind == "warp"]
    if len(warps) != 1:
        raise ValueError(f"escort_beat: {beat_name}: {floor.row_id} carries {len(warps)} "
                         "'warp' assertions (expected exactly 1)")
    params = dict(warps[0].params)
    if params["map_id"] != map_uranium_id(dest_map_constant):
        raise ValueError(
            f"escort_beat: {beat_name}: {floor.row_id} transfers to map {params['map_id']}, "
            f"not {dest_map_constant}")
    arrival = (params["x"], params["y"])
    if not params["arrives_on_door"]:
        return arrival
    if params["direction"] in (0, None):
        raise ValueError(
            f"escort_beat: {beat_name}: {floor.row_id} lands on a door tile with the "
            "player's facing retained; the ride's final facing isn't known, so neither "
            "is the cell the door exit steps onto")
    facing = assertions.facing_for_direction(params["direction"], "UP")
    return assertions.arrival_landing_cell(arrival, facing, True)


def escort_beat(
    builder: ChapterBuilder,
    *,
    chapter_id: str,
    beat_name: str,
    rows: Sequence[str],
    map_constant: str,
    map_id: int,
    event_id: int,
    dest_map_constant: str,
    group: str | None = None,
    approach_prefer: str | None = None,
    manifest_chapter_id: str | None = None,
    floor_lookup: FloorLookup | None = None,
) -> None:
    """Register one escort beat claiming `rows`: the escort page first, then
    the arms its one firing takes. Fails loud (`ValueError`) on a refused
    floor, rows from more than one page, or a page that isn't `event_id` on
    `map_id`. `manifest_chapter_id` is accepted for symmetry with the other
    templates (a successor boundary claim); the rows' floors are read
    through `floor_lookup` either way."""
    del chapter_id, manifest_chapter_id
    lookup: FloorLookup = floor_lookup if floor_lookup is not None else _default_floor_for_row
    rows = tuple(rows)
    if not rows:
        raise ValueError(f"escort_beat: {beat_name}: no rows")
    page_row_id = rows[0]
    parsed = parse_row_id(page_row_id)
    if parsed.kind != "page" or (parsed.map_id, parsed.event_id) != (map_id, event_id):
        raise ValueError(
            f"escort_beat: {beat_name}: first row {page_row_id!r} is not a page of "
            f"map {map_id} event {event_id}")
    stray = [r for r in rows[1:] if parse_row_id(r).owning_page_row_id != page_row_id]
    if stray:
        raise ValueError(f"escort_beat: {beat_name}: rows {stray} are not arms of {page_row_id}")

    floors: dict[str, RowFloor] = {}
    for row_id in rows:
        floor = lookup(row_id)
        if floor.refused:
            raise ValueError(
                f"escort_beat: {beat_name}: row {row_id!r} floor is refused "
                f"({floor.refusals}) -- fix the refusal before registering this beat")
        floors[row_id] = floor
    landing = _landing(floors[page_row_id], dest_map_constant, beat_name=beat_name)

    # The page fires once, so its (and each arm's repeated) `trigger` and
    # `completes` run once; everything else in source order.
    all_steps = [s for row_id in rows for s in steps_for(floors[row_id])]
    trigger_step = next((s for s in all_steps if s.kind == "trigger"), None)
    completes_step = next((s for s in all_steps if s.kind == "completes"), None)
    if trigger_step is None or dict(trigger_step.params).get("trigger") != "action":
        raise ValueError(
            f"escort_beat: {beat_name}: {page_row_id} is not an action-button page -- "
            "an escort is talked to; a step-on transfer is a warp")
    ordered = sorted(all_steps, key=lambda s: (s.list_index, s.kind, s.row_id, repr(s.params)))
    ride_steps: list[Step] = [s for s in ordered if s.kind in _RIDE_KINDS]
    state_steps: list[Step] = [s for s in ordered if s.kind in _STATE_KINDS]

    target = event_cell(map_constant, event_id)
    x, y = approach_to(map_constant, event_id, prefer=approach_prefer)
    face = facing_toward((x, y), target, caller="escort_beat")
    declared = declare_assertions(rows, executed_kinds=ESCORT_EXECUTED_KINDS,
                                  template="escort", floor_lookup=lookup)

    @builder.beat(
        beat_name,
        f"Talk to {map_constant} event {event_id} and ride its escort to "
        f"{dest_map_constant} {landing} ({', '.join(rows)})",
        locations=(BeatLocation(map_constant, x, y, "escort approach"),
                   BeatLocation(dest_map_constant, landing[0], landing[1], "escort landing")),
        group=group, rows=rows, archetype="warp", assertions=declared,
    )
    def body(emu: "Emulator") -> None:
        assertions.require_map(emu, beat_name, map_constant)
        emu.walk_to(x, y, absorb_wild=True)
        emu.face(face)
        STEP_HANDLERS["trigger"](emu, beat_name, trigger_step)
        for step in ride_steps:
            STEP_HANDLERS[step.kind](emu, beat_name, step)
        # The rest of the script walks the player off and warps; the
        # destination's arrival autoruns can start moving them at once, so
        # the landing is read the moment the map changes.
        emu.advance_dialog(stop=lambda: assertions.at_map(emu, dest_map_constant))
        assertions.wait_for_map(emu, beat_name, dest_map_constant)
        assertions.assert_position_exact(emu, beat_name, landing)
        emu.settle_field()
        for step in state_steps:
            STEP_HANDLERS[step.kind](emu, beat_name, step)
        if completes_step is not None:
            STEP_HANDLERS["completes"](emu, beat_name, completes_step)

    del body
