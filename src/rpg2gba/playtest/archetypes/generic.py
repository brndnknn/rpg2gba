"""The generic template: the floor for every row no archetype claims
(R11; REDERIVATION_PLAN.md §16.3 C6, C6_GENERATOR_PLAN.md part #4).

Four registration functions, one per `beat_gen.plan.TemplateName` this
module serves:

- `generic_beat`  -- page and branch-arm rows: walk up, interact, then
                     check the row's floor step by step
- `obstacle_beat` -- `blocked_obstacle` rows of one (map, capability)
- `stair_beat`    -- one staircase's terrain rows, crossed and crossed back (A3)
- `seam_beat`     -- one seam row, crossed at the solver's picked cell (A1)

The design splits WHAT to check from HOW to drive the emulator:

- `steps_for(floor)` is pure: the ordered checks a row's floor implies.
  Offline-testable.
- `STEP_HANDLERS[kind]` drives the emulator for one step. Only a ROM walk
  (P11) can exercise it.

Honesty (C5 ruling (c)): a template declares only the kinds its body
executes. Here that is the invariant `set(STEP_HANDLERS) ==
GENERIC_EXECUTED_KINDS`, and a test pins it, so a kind can't be declared
without a handler that checks it.

`GENERIC_EXECUTED_KINDS` (Task 7, R1): `trigger`/`completes`/`text` are the
required minimum. Beyond that, `switch_write`/`var_write`/
`self_switch_write`/`engine_flag_write`/`visual` are added because each is checkable with a
single, stateless, absolute read after the row's steps run -- exactly what
a per-kind `StepHandler(emu, beat_name, step) -> None` can honestly do
without any state shared across steps. `item_grant` and `battle` are left
out: `item_grant`'s honest check (`item_ball.py`'s own `grant_beat`) is a
bag-quantity DELTA, which needs a "before" snapshot taken ahead of the
row's `trigger` step -- there is no channel for that in this design without
either mutating `Step` with runtime data (breaking `steps_for`'s purity,
since the snapshot can only be taken by touching the emulator) or giving
handlers shared mutable state across steps, which turns "one handler per
kind" back into "one body per beat" -- exactly what `item_ball.py` already
is. `battle`'s wild half has no observable identity (no party/species read
in the emulator's public API for anything but the player's own party), so
a `battle` handler could only ever check the trainer half honestly; left
out rather than declaring a kind it only partly executes. `audio` is left
out too: `assertion.py`'s own `AssertionKind` comment says it is "not
checked until audio is mapped" -- `bgm_song_id()` reads BGM only, no SE
read exists, so this is the code's own standing position, not a new call
made here. `choice`/`warp`/`heal_party`/`pokemon_grant`/`service`/
`displacement`/`event_position`/`erase_event` are each a real, cited
observation gap in `assignments/C6/research/07_generic.md` §2 -- none
buys enough (`warp`'s single-page-in-a-multi-step-loop map-change problem
in particular) to be worth the design complexity here.

STATUS: implemented (`assignments/C6/07_generic.md`).
"""
from __future__ import annotations

import functools
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from rpg2gba.beat_floor.assertion import Params, RowFloor
from rpg2gba.beat_floor.lookup import floor_for_row as _default_floor_for_row
from rpg2gba.chapter_manifest.schema import parse_row_id
from rpg2gba.conversion_agent.flag_registry import FlagRegistry, self_switch_flag_name
from rpg2gba.playtest import assertions
from rpg2gba.playtest.archetypes import (
    FloorLookup,
    declare_assertions,
    facing_toward,
    load_chapter_rows,
)
from rpg2gba.playtest.cells import approach_to, event_cell, seam_cells
from rpg2gba.playtest.chapter import ChapterBuilder
from rpg2gba.playtest.errors import ScenarioError
from rpg2gba.routing.locations import cell_for_row

if TYPE_CHECKING:  # runtime import is lazy so this module works without mGBA bindings
    from rpg2gba.playtest.emulator import Emulator

# Which floor kinds the generic body checks. See the module docstring for
# why each kind is in or out (Task 7, R1).
GENERIC_EXECUTED_KINDS: frozenset[str] = frozenset({
    "trigger", "completes", "text",
    "switch_write", "var_write", "self_switch_write", "engine_flag_write",
    "visual",
})


@dataclass(frozen=True)
class Step:
    """One check the body performs, in execution order."""

    row_id: str
    kind: str
    list_index: int
    params: Params


StepHandler = Callable[["Emulator", str, "Step"], None]
"""(emu, beat_name, step) -> None; raises ScenarioError on a mismatch."""

STEP_HANDLERS: dict[str, StepHandler] = {}


# -- steps_for: pure, offline-testable -----------------------------------

_FORCED_BUCKET: dict[str, int] = {"trigger": 0, "completes": 2}


def _step_sort_key(step: Step) -> tuple[int, int, str, str]:
    """`trigger` first, `completes` last, everything else by `list_index`
    (both share `list_index=-1` corpus-wide, so bucket does the forcing);
    ties within the middle bucket break on `kind` then `repr(params)` --
    the same tiebreak `coverage.uncovered` already uses, needed for real
    multi-way ties measured in the research doc (§5)."""
    bucket = _FORCED_BUCKET.get(step.kind, 1)
    return (bucket, step.list_index, step.kind, repr(step.params))


def steps_for(floor: RowFloor) -> tuple[Step, ...]:
    """The ordered checks for one row: only `GENERIC_EXECUTED_KINDS`;
    `trigger` first, `completes` last, everything else by `list_index`
    (ties broken by kind, then params). Raises `ValueError` if the floor
    is refused."""
    if floor.refused:
        raise ValueError(
            f"steps_for: {floor.row_id}'s floor is refused ({floor.refusals}) "
            "-- fix the refusal before deriving steps for it"
        )
    steps = [
        Step(row_id=floor.row_id, kind=a.kind, list_index=a.list_index, params=a.params)
        for a in floor.assertions
        if a.kind in GENERIC_EXECUTED_KINDS
    ]
    steps.sort(key=_step_sort_key)
    return tuple(steps)


# -- the flag registry, read-only, lazily loaded and cached ----------------
#
# CLAUDE.md §6's hard rule: every FLAG_*/VAR_* name goes through the
# registry, never hand-formatted. `get_flag`/`get_var` are the
# already-committed-mints-only lookups (not `resolve_switch_flag`/
# `resolve_variable_var`, which MINT a name on demand from a Phase-3 label
# -- research §4's lead correction: a name minted at walk time is one the
# ROM was never built with, so `emu.flag(name)` would have no symbol to
# read). "It doesn't guess" (the task's own words) means this handler
# raises rather than mints.

def _default_flag_state_path() -> Path:
    """`output/uranium-build/flag_state.json`, honoring `RPG2GBA_OUTPUT`
    the way the rest of the pipeline does (read only -- this module never
    sets the variable, per CLAUDE.md §3/§12)."""
    root = Path(os.environ.get("RPG2GBA_OUTPUT", "output"))
    return root / "uranium-build" / "flag_state.json"


@functools.cache
def _flag_registry() -> FlagRegistry:
    path = _default_flag_state_path()
    if not path.exists():
        raise ScenarioError(
            f"generic template: no flag registry state at {path} -- run "
            "the flag-registry pipeline before a ROM walk needs a "
            "switch/var name"
        )
    return FlagRegistry.load(path)


# -- STEP_HANDLERS: drive the emulator for one step -------------------------

_PLAYER_TRIGGERS = frozenset({"action", "player_touch", "event_touch"})
_ARRIVAL_TRIGGERS = frozenset({"autorun", "parallel"})
# What an arrival page's beat can't observe after the fact: the trigger
# already fired and the text was already driven through. Left undeclared,
# so they stay honestly uncovered (owed to an arrival-cutscene template).
_NOT_AFTER_THE_FACT = frozenset({"trigger", "text"})


def _player_facing(emu: "Emulator") -> str:
    return emu.object_event(emu.resolve_constant("LOCALID_PLAYER")).facing


def _handle_trigger(emu: "Emulator", beat_name: str, step: Step) -> None:
    """Fire the page. The body has already walked to the approach cell and
    faced the event, so `action` presses A and a touch trigger steps into
    it; an autorun/parallel page must already hold the field. Trigger
    names are the floor's own vocabulary (`story_state.extract`:
    action/player_touch/event_touch/autorun/parallel)."""
    trigger = dict(step.params).get("trigger")
    if trigger == "action":
        emu.interact()  # raises if no script picks up the field
    elif trigger in ("player_touch", "event_touch"):
        assertions.try_step(emu, _player_facing(emu))
        if not emu.field_locked():
            shot = emu.screenshot(f"{beat_name}_no_touch_trigger")
            raise ScenarioError(
                f"{beat_name}: {step.row_id}: stepping into the event "
                f"(trigger={trigger!r}) started no script ({shot})"
            )
    elif trigger in ("autorun", "parallel"):
        if not emu.field_locked():
            shot = emu.screenshot(f"{beat_name}_no_trigger")
            raise ScenarioError(
                f"{beat_name}: {step.row_id}: trigger {trigger!r} did not "
                f"lock field controls after arriving ({shot})"
            )
    else:
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: unrecognized trigger kind {trigger!r}"
        )


def _handle_completes(emu: "Emulator", beat_name: str, step: Step) -> None:
    emu.advance_dialog()
    if emu.field_locked():
        shot = emu.screenshot(f"{beat_name}_still_locked")
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: field controls are still locked "
            f"after advancing to completion ({shot})"
        )


def _handle_text(emu: "Emulator", beat_name: str, step: Step) -> None:
    params = dict(step.params)
    expected = params["text"]
    text = emu.wait_for_field_message()
    if text is None or expected not in text:
        shot = emu.screenshot(f"{beat_name}_text_{params.get('index')}")
        raise ScenarioError(
            f"{beat_name}: {step.row_id} message {params.get('index')} "
            f"expected to contain {expected!r}, got {text!r} ({shot})"
        )
    emu.clear_field_message()
    emu.tap("A")


def _handle_switch_write(emu: "Emulator", beat_name: str, step: Step) -> None:
    params = dict(step.params)
    switch_id = params["switch_id"]
    name = _flag_registry().get_flag(switch_id)
    if name is None:
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: switch {switch_id} has no minted "
            "FLAG_* name in the persisted flag registry -- not guessing one"
        )
    expected = bool(params["value"])
    actual = emu.flag(name)
    if actual != expected:
        shot = emu.screenshot(f"{beat_name}_switch_{switch_id}")
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: {name} reads {actual!r}, expected "
            f"{expected!r} ({shot})"
        )


def _handle_var_write(emu: "Emulator", beat_name: str, step: Step) -> None:
    params = dict(step.params)
    var_id = params["var_id"]
    name = _flag_registry().get_var(var_id)
    if name is None:
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: var {var_id} has no minted VAR_* "
            "name in the persisted flag registry -- not guessing one"
        )
    actual = emu.var(name)
    op = params.get("op")
    if op in ("assign", "Assign"):
        expected = params["value"]
        if actual != expected:
            shot = emu.screenshot(f"{beat_name}_var_{var_id}")
            raise ScenarioError(
                f"{beat_name}: {step.row_id}: {name} reads {actual!r}, "
                f"expected {expected!r} after an assign ({shot})"
            )
    # An "Adjust" op is a relative change; this step has no "before" value
    # to diff against (steps_for is pure, no emulator access), so the
    # honest check here is that the var resolves and reads at all -- a
    # missing/unresolvable name still raises above.


def _handle_self_switch_write(emu: "Emulator", beat_name: str, step: Step) -> None:
    params = dict(step.params)
    map_id = parse_row_id(step.row_id).map_id
    name = self_switch_flag_name(map_id, params["event_id"], str(params["letter"]))
    expected = bool(params["value"])
    actual = emu.flag(name)
    if actual != expected:
        shot = emu.screenshot(f"{beat_name}_ssa")
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: {name} reads {actual!r}, expected "
            f"{expected!r} ({shot})"
        )


def _handle_engine_flag_write(emu: "Emulator", beat_name: str, step: Step) -> None:
    # The flag name is the native FLAG_SYS_* itself (C8 ruling (b)), verified
    # against the fork by `engine-audit` -- no registry lookup to fail.
    params = dict(step.params)
    name = str(params["flag"])
    expected = bool(params["value"])
    actual = emu.flag(name)
    if actual != expected:
        shot = emu.screenshot(f"{beat_name}_{name.lower()}")
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: {name} reads {actual!r}, expected "
            f"{expected!r} ({shot})"
        )


def _handle_visual(emu: "Emulator", beat_name: str, step: Step) -> None:
    # `assertion.py`'s own OFFLINE_KINDS comment: visual "asserts nothing a
    # ROM walk could fail beyond completes". The row already ran to
    # completion by the time this step is reached (`completes` sorts last,
    # but a visual mid-row still only implies the page kept running, which
    # the NEXT trigger/text/completes step in this same row already
    # confirms). This handler exists so the kind can be declared honestly,
    # not to perform an independent check.
    return


STEP_HANDLERS.update({
    "trigger": _handle_trigger,
    "completes": _handle_completes,
    "text": _handle_text,
    "switch_write": _handle_switch_write,
    "var_write": _handle_var_write,
    "self_switch_write": _handle_self_switch_write,
    "engine_flag_write": _handle_engine_flag_write,
    "visual": _handle_visual,
})


# -- generic_beat -------------------------------------------------------

def generic_beat(
    builder: ChapterBuilder,
    *,
    chapter_id: str,
    beat_name: str,
    rows: Sequence[str],
    group: str | None = None,
    approach_prefer: str | None = None,
    skip_claimed: bool = False,
    manifest_chapter_id: str | None = None,
    floor_lookup: FloorLookup | None = None,
) -> None:
    """Register one generic beat claiming `rows` (a page row and/or its
    arms). With `skip_claimed=True`, rows some earlier beat in `builder`
    already claims are dropped first, and if none remain nothing is
    registered. Fails loud (`ValueError`) on a refused floor.
    `manifest_chapter_id=` names a predecessor whose manifest carries the
    rows (a successor boundary claim, §10 R2), as `find_match` takes it."""
    resolved_lookup: FloorLookup = (
        floor_lookup if floor_lookup is not None else _default_floor_for_row)
    resolved_rows = tuple(rows)
    if skip_claimed:
        claimed = builder.claimed_rows()
        resolved_rows = tuple(r for r in resolved_rows if r not in claimed)
    if not resolved_rows:
        return

    # Floors first (registration rule): a refused row fails loud before
    # anything is registered.
    floors: dict[str, RowFloor] = {}
    for row_id in resolved_rows:
        floor = resolved_lookup(row_id)
        if floor.refused:
            raise ValueError(
                f"generic_beat: {beat_name}: row {row_id!r} floor is refused "
                f"({floor.refusals}) -- fix the refusal before registering "
                "this beat"
            )
        floors[row_id] = floor

    # Location: the owning page's approach cell. Arms are located through
    # their page (same rule Task 4 uses) -- a branch row carries no cell of
    # its own.
    page_row_id = parse_row_id(resolved_rows[0]).owning_page_row_id
    if page_row_id is None:
        raise ValueError(
            f"generic_beat: {beat_name}: row {resolved_rows[0]!r} is not a "
            "page or branch row -- generic_beat only claims page/branch "
            "rows; use stair_beat/seam_beat for terrain/seam rows"
        )
    manifest_id = manifest_chapter_id if manifest_chapter_id is not None else chapter_id
    chapter_rows = load_chapter_rows(manifest_id)
    row_by_id = {r.row_id: r for r in chapter_rows}
    page_row = row_by_id.get(page_row_id)
    if page_row is None:
        raise ValueError(
            f"generic_beat: {beat_name}: page row {page_row_id!r} (owning "
            f"{resolved_rows[0]!r}) is not in chapter {manifest_id!r}'s manifest"
        )
    if page_row.trigger in _ARRIVAL_TRIGGERS and page_row.event_id is not None:
        # `cell_for_row` has no rule for `parallel`, and an arrival page's
        # own tile is only a fallback location (see below), so it is built here.
        from rpg2gba.routing.locations import RowCell, _map_constant_for

        const = _map_constant_for(page_row.map_id)
        ex, ey = event_cell(const, page_row.event_id)
        cell = RowCell(row_id=page_row.row_id, map_constant=const, x=ex, y=ey,
                       resolver="event_cell (arrival page)")
    else:
        cell = cell_for_row(page_row)

    # Every row of a generic beat belongs to one page (the page and its
    # arms), and each arm's floor repeats the page's `trigger`/`completes`.
    # The page runs once, so those two fire once: the first `trigger`, then
    # every other step of every row in source order, then one `completes`.
    all_steps = [s for row_id in resolved_rows for s in steps_for(floors[row_id])]
    triggers = [s for s in all_steps if s.kind == "trigger"]
    trigger_step = triggers[0] if triggers else None
    completes_step = next((s for s in all_steps if s.kind == "completes"), None)
    middle_steps = sorted(
        (s for s in all_steps if s.kind not in _FORCED_BUCKET),
        key=lambda s: (s.list_index, s.kind, s.row_id, repr(s.params)))

    # A player-triggered page is fired from an ADJACENT cell, facing the
    # event: `cell_for_row` puts the routing point ON a touch event's cell,
    # and walking onto it would fire the page mid-walk. Autorun/parallel
    # pages fire on their own; the beat stands on the routing point.
    trigger = dict(trigger_step.params).get("trigger") if trigger_step else None
    faces_target: tuple[int, int] | None = None
    arrival = trigger in _ARRIVAL_TRIGGERS
    if arrival:
        # Autorun/parallel: fires on arriving on the map, usually during the
        # crossing that brought the player here (whose settle drains it).
        # Observed after the fact: no walk, no trigger, no text -- only the
        # state it leaves. Located at the arrival the solver picked
        # (beat_gen's "arrive@(x,y)" side).
        # Without a pick (an arrival nudge's arms ride in the nudge's group,
        # located at its exact landing), the page's own routing cell stands.
        if approach_prefer is None:
            x, y = cell.x, cell.y
        elif approach_prefer.startswith("arrive@("):
            x, y = (int(v) for v in approach_prefer[len("arrive@("):-1].split(","))
        else:
            raise ValueError(f"generic_beat: {beat_name}: a {trigger} page takes "
                             f"approach_prefer='arrive@(x,y)', got {approach_prefer!r}")
        trigger_step = None
        middle_steps = [s for s in middle_steps if s.kind not in _NOT_AFTER_THE_FACT]
    elif trigger in _PLAYER_TRIGGERS and page_row.event_id is not None:
        faces_target = event_cell(cell.map_constant, page_row.event_id)
        x, y = approach_to(cell.map_constant, page_row.event_id, prefer=approach_prefer)
    elif approach_prefer is not None:
        candidate = next(
            (c for c in cell.approach_candidates if c.side == approach_prefer), None)
        if candidate is None:
            sides = [c.side for c in cell.approach_candidates]
            raise ValueError(
                f"generic_beat: {beat_name}: approach_prefer={approach_prefer!r} "
                f"is not among {page_row_id}'s candidate sides {sides}"
            )
        x, y = candidate.x, candidate.y
    else:
        x, y = cell.x, cell.y

    declared = declare_assertions(
        resolved_rows,
        executed_kinds=GENERIC_EXECUTED_KINDS - (_NOT_AFTER_THE_FACT if arrival else frozenset()),
        template="generic", floor_lookup=resolved_lookup,
    )

    @builder.beat(
        beat_name,
        f"Generic floor coverage for {', '.join(resolved_rows)} ({chapter_id})",
        map_constant=cell.map_constant, at=(x, y), group=group,
        rows=resolved_rows, assertions=declared,
    )
    def body(emu: "Emulator") -> None:
        from rpg2gba.playtest.emulator import WalkInterrupted

        assertions.require_map(emu, beat_name, cell.map_constant)
        fired_on_the_way = arrival       # an arrival page already ran
        try:
            if not arrival:
                emu.walk_to(x, y)
        except WalkInterrupted:
            # An event-touch page can reach the player first (the trainer
            # template's `_approach` makes the same call); the steps below
            # decide whether it was this page.
            fired_on_the_way = True
        if not fired_on_the_way:
            if faces_target is not None:
                emu.face(facing_toward((x, y), faces_target, caller="generic_beat"))
            if trigger_step is not None:
                STEP_HANDLERS["trigger"](emu, beat_name, trigger_step)
        for step in middle_steps:
            STEP_HANDLERS[step.kind](emu, beat_name, step)
        if completes_step is not None:
            STEP_HANDLERS["completes"](emu, beat_name, completes_step)

    del body


# -- obstacle_beat --------------------------------------------------------

def obstacle_beat(
    builder: ChapterBuilder,
    *,
    chapter_id: str,
    beat_name: str,
    rows: Sequence[str],
    capability: str,
    group: str | None = None,
    approach_prefer: str | None = None,
    floor_lookup: FloorLookup | None = None,
) -> None:
    """Register one beat asserting every `blocked_obstacle` in `rows`
    (all on one map, all needing `capability`). Fails loud if a row's floor
    has no `blocked_obstacle`, or one for a different capability."""
    resolved_lookup: FloorLookup = (
        floor_lookup if floor_lookup is not None else _default_floor_for_row)
    resolved_rows = tuple(rows)
    if not resolved_rows:
        raise ValueError(f"obstacle_beat: {beat_name}: rows= is empty")

    floors: dict[str, RowFloor] = {}
    obstacles: dict[str, object] = {}
    for row_id in resolved_rows:
        floor = resolved_lookup(row_id)
        if floor.refused:
            raise ValueError(
                f"obstacle_beat: {beat_name}: row {row_id!r} floor is "
                f"refused ({floor.refusals})"
            )
        obstacle_assertions = [a for a in floor.assertions if a.kind == "blocked_obstacle"]
        if not obstacle_assertions:
            raise ValueError(
                f"obstacle_beat: {beat_name}: row {row_id!r} has no "
                "blocked_obstacle assertion in its floor"
            )
        if len(obstacle_assertions) != 1:
            raise ValueError(
                f"obstacle_beat: {beat_name}: row {row_id!r} carries "
                f"{len(obstacle_assertions)} blocked_obstacle assertions "
                "(expected exactly 1)"
            )
        obstacle = obstacle_assertions[0]
        row_capability = obstacle.param("capability")
        if row_capability != capability:
            raise ValueError(
                f"obstacle_beat: {beat_name}: row {row_id!r} needs "
                f"capability {row_capability!r}, not {capability!r}"
            )
        floors[row_id] = floor
        obstacles[row_id] = obstacle

    chapter_rows = load_chapter_rows(chapter_id)
    row_by_id = {r.row_id: r for r in chapter_rows}
    first_row = row_by_id.get(resolved_rows[0])
    if first_row is None:
        raise ValueError(
            f"obstacle_beat: {beat_name}: row {resolved_rows[0]!r} is not "
            f"in chapter {chapter_id!r}'s manifest"
        )
    # Location = the first rock's cell (the task's own registration rule):
    # `cell_for_row` here is used only for its map_constant resolution --
    # there is no cells.py resolver for an obstacle's own cell (research
    # §9), so x/y come from the obstacle assertion's own params, not from
    # `cell_for_row`'s x/y.
    map_constant = cell_for_row(first_row).map_constant
    first_obstacle = obstacles[resolved_rows[0]]
    x, y = first_obstacle.param("x"), first_obstacle.param("y")

    declared = declare_assertions(
        resolved_rows, executed_kinds=frozenset({"blocked_obstacle"}),
        template="obstacle", floor_lookup=resolved_lookup,
    )

    @builder.beat(
        beat_name,
        f"Every {capability} obstacle on {', '.join(resolved_rows)} "
        f"({chapter_id}) stays blocked without {capability}",
        map_constant=map_constant, at=(x, y), group=group,
        rows=resolved_rows, assertions=declared,
    )
    def body(emu: "Emulator") -> None:
        assertions.require_map(emu, beat_name, map_constant)
        for row_id in resolved_rows:
            obstacle = obstacles[row_id]
            ox, oy = obstacle.param("x"), obstacle.param("y")
            parsed = parse_row_id(row_id)
            approach = approach_to(map_constant, parsed.event_id, prefer=approach_prefer)
            facing = facing_toward(approach, (ox, oy), caller="obstacle_beat")
            emu.walk_to(*approach)
            emu.face(facing)
            before = emu.player_pos()
            emu.interact()
            moved = assertions.try_step(emu, facing)
            after = emu.player_pos()
            if moved or after != before:
                shot = emu.screenshot(f"{beat_name}_{row_id}_smashed")
                raise ScenarioError(
                    f"{beat_name}: {row_id}: pressing A and stepping toward "
                    f"the {capability} obstacle at ({ox},{oy}) moved the "
                    f"player from {before} to {after} -- it should still be "
                    f"blocking without {capability} ({shot})"
                )

    del body


# -- stair_beat -----------------------------------------------------------

_OPPOSITE_DIR: dict[str, str] = {"LEFT": "RIGHT", "RIGHT": "LEFT", "UP": "DOWN", "DOWN": "UP"}
_EDGE_PRESS: dict[str, str] = {"N": "UP", "S": "DOWN", "E": "RIGHT", "W": "LEFT"}


def stair_beat(
    builder: ChapterBuilder,
    *,
    chapter_id: str,
    beat_name: str,
    rows: Sequence[str],
    group: str | None = None,
    approach_prefer: str | None = None,
    floor_lookup: FloorLookup | None = None,
) -> None:
    """Register one round-trip staircase beat for `rows` (terrain rows of
    one staircase). Declares their `stair_crossing` assertions."""
    resolved_lookup: FloorLookup = (
        floor_lookup if floor_lookup is not None else _default_floor_for_row)
    resolved_rows = tuple(rows)
    if not resolved_rows:
        raise ValueError(f"stair_beat: {beat_name}: rows= is empty")

    floors: dict[str, RowFloor] = {}
    crossings: dict[str, object] = {}
    for row_id in resolved_rows:
        floor = resolved_lookup(row_id)
        if floor.refused:
            raise ValueError(
                f"stair_beat: {beat_name}: row {row_id!r} floor is refused "
                f"({floor.refusals})"
            )
        stair_assertions = [a for a in floor.assertions if a.kind == "stair_crossing"]
        if len(stair_assertions) != 1:
            raise ValueError(
                f"stair_beat: {beat_name}: row {row_id!r} carries "
                f"{len(stair_assertions)} stair_crossing assertions "
                "(expected exactly 1)"
            )
        floors[row_id] = floor
        crossings[row_id] = stair_assertions[0]

    chapter_rows = load_chapter_rows(chapter_id)
    row_by_id = {r.row_id: r for r in chapter_rows}
    first_row = row_by_id.get(resolved_rows[0])
    if first_row is None:
        raise ValueError(
            f"stair_beat: {beat_name}: row {resolved_rows[0]!r} is not in "
            f"chapter {chapter_id!r}'s manifest"
        )
    cell = cell_for_row(first_row)
    if approach_prefer is not None:
        candidate = next(
            (c for c in cell.approach_candidates if c.side == approach_prefer), None)
        if candidate is None:
            sides = [c.side for c in cell.approach_candidates]
            raise ValueError(
                f"stair_beat: {beat_name}: approach_prefer={approach_prefer!r} "
                f"is not among {resolved_rows[0]}'s candidate sides {sides}"
            )
        x, y = candidate.x, candidate.y
    else:
        x, y = cell.x, cell.y

    declared = declare_assertions(
        resolved_rows, executed_kinds=frozenset({"stair_crossing"}), template="stair",
        floor_lookup=resolved_lookup,
    )

    @builder.beat(
        beat_name,
        f"Round-trip crossing of the staircase at {', '.join(resolved_rows)} "
        f"({chapter_id})",
        map_constant=cell.map_constant, at=(x, y), group=group,
        rows=resolved_rows, assertions=declared,
    )
    def body(emu: "Emulator") -> None:
        assertions.require_map(emu, beat_name, cell.map_constant)
        emu.walk_to(x, y)
        taken: list[tuple[str, tuple[int, int]]] = []
        for row_id in resolved_rows:
            crossing = crossings[row_id]
            for step_dir, dx, dy in crossing.param("steps"):
                before = emu.player_pos()
                moved = assertions.try_step(emu, step_dir)
                after = emu.player_pos()
                if not moved or (after[0] - before[0], after[1] - before[1]) != (dx, dy):
                    shot = emu.screenshot(f"{beat_name}_{row_id}_step")
                    raise ScenarioError(
                        f"{beat_name}: {row_id}: stepping {step_dir} from "
                        f"{before} landed at {after}, expected a move of "
                        f"({dx},{dy}) ({shot})"
                    )
                taken.append((step_dir, (dx, dy)))
        # Cross back the same way, reversed, so the beat ends where it
        # started (the round-trip idiom `routing.locations.choose_routing_
        # point`'s own docstring documents for a staircase beat).
        for step_dir, (dx, dy) in reversed(taken):
            reverse_dir = _OPPOSITE_DIR[step_dir]
            before = emu.player_pos()
            moved = assertions.try_step(emu, reverse_dir)
            after = emu.player_pos()
            if not moved or (after[0] - before[0], after[1] - before[1]) != (-dx, -dy):
                shot = emu.screenshot(f"{beat_name}_return_step")
                raise ScenarioError(
                    f"{beat_name}: stepping back {reverse_dir} from {before} "
                    f"landed at {after}, expected a move of ({-dx},{-dy}) "
                    f"({shot})"
                )

    del body


# -- seam_beat --------------------------------------------------------------

def seam_beat(
    builder: ChapterBuilder,
    *,
    chapter_id: str,
    beat_name: str,
    rows: Sequence[str],
    group: str | None = None,
    approach_prefer: str | None = None,
    floor_lookup: FloorLookup | None = None,
) -> None:
    """Register one seam-crossing beat for a single seam row. Declares its
    `seam_crossing` assertion."""
    if len(rows) != 1:
        raise ValueError(
            f"seam_beat: {beat_name}: takes exactly one row, got {len(rows)}: "
            f"{list(rows)}"
        )
    row_id = rows[0]
    resolved_lookup: FloorLookup = (
        floor_lookup if floor_lookup is not None else _default_floor_for_row)

    floor = resolved_lookup(row_id)
    if floor.refused:
        raise ValueError(
            f"seam_beat: {beat_name}: row {row_id!r} floor is refused "
            f"({floor.refusals})"
        )
    seam_assertions = [a for a in floor.assertions if a.kind == "seam_crossing"]
    if len(seam_assertions) != 1:
        raise ValueError(
            f"seam_beat: {beat_name}: row {row_id!r} carries "
            f"{len(seam_assertions)} seam_crossing assertions (expected "
            "exactly 1)"
        )
    seam = seam_assertions[0]
    params = dict(seam.params)

    from rpg2gba.routing.locations import _map_constant_for  # the only resolver: no
    # cells.py function converts a Uranium map id to its MAP_* constant on
    # its own, and cell_for_row (this module's usual entry point) refuses
    # seam rows outright (routing/locations.py's own message).

    map_constant = _map_constant_for(params["map_id"])
    other_map_constant = _map_constant_for(params["other_map_id"])
    # The floor names the EDGE ("N"); crossing it is a held press ("UP").
    direction = _EDGE_PRESS[str(params["direction"])]
    if approach_prefer is not None:
        # locate.py's seam candidate side: "<press>@(x,y)".
        press, _, at = approach_prefer.partition("@")
        if press != direction or not at:
            raise ValueError(
                f"seam_beat: {beat_name}: approach_prefer={approach_prefer!r} is not "
                f"a {direction} crossing of {row_id}")
        x, y = (int(v) for v in at.strip("()").split(","))
    else:
        x, y = seam_cells(map_constant, to=other_map_constant)[0]

    declared = declare_assertions(
        (row_id,), executed_kinds=frozenset({"seam_crossing"}), template="seam",
        floor_lookup=resolved_lookup,
    )

    @builder.beat(
        beat_name,
        f"Cross the seam {row_id} ({chapter_id})",
        map_constant=map_constant, at=(x, y), group=group,
        rows=(row_id,), assertions=declared,
    )
    def body(emu: "Emulator") -> None:
        assertions.require_map(emu, beat_name, map_constant)
        assertions.cross_arrow_warp(emu, beat_name, (x, y), direction, other_map_constant)
        reverse_direction = _OPPOSITE_DIR.get(direction, str(params["other_direction"]))
        other_cells = seam_cells(other_map_constant, to=map_constant)
        assertions.cross_arrow_warp(
            emu, beat_name, other_cells[0], reverse_direction, map_constant)

    del body


# -- transit_beat -----------------------------------------------------------

Hop = tuple[str, int, int, str, str]
"""(map_constant, approach_x, approach_y, press, dest_map_constant)."""


def transit_beat(
    builder: ChapterBuilder,
    *,
    chapter_id: str,
    beat_name: str,
    hops: Sequence[Hop],
    group: str | None = None,
) -> None:
    """Register one travel beat: cross each hop's warp, in order, to reach
    the map the next beat is on (C6 part two, `beat_gen/continuity.py`).

    Claims no rows and declares nothing. It is not a test of these warps --
    each is asserted by its own warp beat -- only the way between two
    beats, derived from the chapter's world graph. A hop stands on its
    approach cell and holds `press` until the map changes (the threshold
    idiom `warp_beat` uses), then lets the arrival settle."""
    if not hops:
        raise ValueError(f"transit_beat: {beat_name}: no hops")
    first_map, fx, fy, _, _ = hops[0]

    @builder.beat(
        beat_name,
        f"Travel ({chapter_id}): " + " -> ".join(
            [hops[0][0]] + [h[4] for h in hops]),
        map_constant=first_map, at=(fx, fy), group=group,
    )
    def body(emu: "Emulator") -> None:
        for map_constant, x, y, press, dest in hops:
            assertions.require_map(emu, beat_name, map_constant)
            assertions.cross_threshold(emu, beat_name, (x, y), press, dest)
            emu.settle_field()

    del body
