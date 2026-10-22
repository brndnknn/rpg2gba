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
without any state shared across steps. `battle` is checked for its trainer
half only (below); a wild battle has no observable identity, so its
assertion stays undeclared. `audio` is left
out too: `assertion.py`'s own `AssertionKind` comment says it is "not
checked until audio is mapped" -- `bgm_song_id()` reads BGM only, no SE
read exists, so this is the code's own standing position, not a new call
made here. `choice`/`warp`/`pokemon_grant`/`service`/ (the first and
last two since wired, below)
`displacement`/`event_position` are each a real, cited
observation gap in `assignments/C6/research/07_generic.md` §2 -- none
buys enough (`warp`'s single-page-in-a-multi-step-loop map-change problem
in particular) to be worth the design complexity here.

`erase_event` joined 2026-10-15 (CH08): `pbEraseThisEvent` is `removeobject`,
so the check is one stateless read -- the event's object is no longer an active
slot in `gObjectEvents`. On an arrival page, erasing its OWN event is also the
proof the page fired (it re-admits `trigger`, like a self-switch write).

`heal_party` joined 2026-09-25 (REDERIVATION_PLAN.md §16.3 ruling 17): the
party is usually full when a heal plays, so a full-HP read proves nothing.
The body sets the lead to 1 HP before firing a page that heals (the one
"before" action this design allows, taken in the body, not a handler), and
the handler reads it back at full. An arrival page has already run by the
time the beat acts, so there it stays undeclared, like `trigger`/`text`.

`item_grant` joined the same day on the same pattern: its honest check is a
bag-quantity delta, so the body reads the bag before the walk and, once the
page completes, hands the handler a step carrying the expected total (the
before quantity plus every grant of that item in the beat). Checked after
`completes`, not mid-page: `giveitem` adds the item and then shows its own
message, so a mid-page read races it. On an arrival page it is read from
the drain log instead (below).

`var_text` (ruling 18) is a `\\v[N]` line: the handler reads the ROM's values
of the input variables the floor recorded, runs the page's own script through
the Ruby-subset evaluator (`beat_floor.var_text`) and checks the resulting
line exactly as `text` does. Undeclared on arrival pages: the ROM's input
values may have moved on by the time the beat reads them.

Arrival pages (autorun/parallel) are drained by the crossing that lands on
them, so their beat checks after the fact. `Emulator.settle_field` logs
every script it drains (`Drain`: map, messages shown, bag before/after);
the beat finds the drain on its map that showed the page's text in order,
which proves `trigger` and `text`, and checks `item_grant` as that drain's
bag delta. A page's menus are answered by the drain itself, from the
answers the beat plans (`Beat.drain_answers`, handed to the emulator by
the runner), and `choice` is checked from what the drain recorded. A
page with no text proves `trigger` by its own self-switch
write. Text is compared as words (`text_matches`): the ROM re-wraps lines
and expands `{...}` codes.

Trainer battles joined 2026-09-25. The floor names the trainer by class
and display name; the registration resolves that to every trainers.json
const with both (a rival's party is picked from a variable at run time, so
any of them is the right trainer). The handler drives the script into the
battle, checks it is a trainer battle against one of those consts, wins it,
and reads the engine's defeat flag for the trainer actually fought. For an
early-rival battle the engine sets that flag on a loss too, so there the
won arm's own writes are what prove the win. A page that heals after its
battle has its lead damaged after the battle, not before the walk.

`pokemon_grant` joined 2026-09-29 (ROM run 27): a loud `pbAddPokemon` is
the transpiler's gift flow, an "obtained" line then a nickname yes/no. The
handler gets through it where the page gives, answering NO (A would open the
naming screen), and reads the species in the party. A refused gift arm that
still runs inside a claimed page (the starter's var-selected give) gets the
same walk-through with no check (`gift_ceremonies=`).

STATUS: implemented (`assignments/C6/07_generic.md`).
"""
from __future__ import annotations

import functools
import json
import logging
import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from rpg2gba.beat_floor.assertion import FloorAssertion, Params, RowFloor, make_params
from rpg2gba.beat_floor.lookup import floor_for_row as _default_floor_for_row
from rpg2gba.chapter_manifest.schema import parse_row_id
from rpg2gba.conversion_agent.flag_registry import FlagRegistry, self_switch_flag_name
from rpg2gba.playtest import assertions
from rpg2gba.playtest.archetypes.item_ball import _uranium_item_constants
from rpg2gba.playtest.archetypes import (
    FloorLookup,
    declare_assertions,
    facing_toward,
    load_chapter_rows,
)
from rpg2gba.playtest.cells import (
    approach_to,
    custom_route_loop,
    event_cell,
    event_page_empty,
    event_is_sight_trainer,
    event_page_moves,
    native_berry_tree_id,
    connection_arrival_cell,
    connection_exit_cells,
    is_seam_crossing,
    real_connection,
    local_id,
    seam_cells,
    trainer_sight_lanes,
)
from rpg2gba.playtest.chapter import ChapterBuilder
from rpg2gba.playtest.errors import ScenarioError
from rpg2gba.routing.locations import cell_for_row
from rpg2gba.story_state.state import SelfSwitch, Switch, Variable

if TYPE_CHECKING:  # runtime import is lazy so this module works without mGBA bindings
    from rpg2gba.playtest.emulator import Emulator

logger = logging.getLogger(__name__)

# Which floor kinds the generic body checks. See the module docstring for
# why each kind is in or out (Task 7, R1).
GENERIC_EXECUTED_KINDS: frozenset[str] = frozenset({
    "trigger", "completes", "text",
    "switch_write", "var_write", "self_switch_write", "engine_flag_write",
    "visual", "heal_party", "var_text", "count_text", "item_grant", "item_remove", "choice",
    "service", "battle", "pokemon_grant", "erase_event",
})

#: Services `_handle_service` can prove opened (ruling 20). Any other service
#: assertion is left undeclared and its step skipped, so it stays reported.
SUPPORTED_SERVICES: frozenset[str] = frozenset(
    {"pc", "region_map", "berry_plant", "mart", "starter_select", "phone_register"})


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
# What an arrival page's beat can't observe live: the crossing that brought
# the player here already drained the page. `text`, `item_grant`, `trigger`
# and `choice` come back through the emulator's drain log (`_arrival_drain`)
# when the page shows text; the rest stay undeclared, so they stay honestly
# uncovered: a heal or a `\\v[N]` line can't be read back afterwards.
_NOT_AFTER_THE_FACT = frozenset(
    {"trigger", "text", "var_text", "count_text", "heal_party", "item_grant", "choice",
     "service", "battle", "pokemon_grant"})
# `item_remove` is not among them: the bag still shows it afterwards. On an
# arrival page the pre-page count is gone, so only a KEY item's removal is
# checked there -- one held at most once ends at 0 (CH06: Maria's key, taken
# by the leader house's autorun).
#: Not a floor kind: an unclaimed gift arm's ceremony the body gets through
#: without checking (`generic_beat(gift_ceremonies=)`).
_GIFT_CEREMONY = "gift_ceremony"
#: Not a floor kind: where an `item_grant` sits in the page, the ROM shows
#: its obtain boxes (`_item_boxes`); the bag check itself stays after the page.
_ITEM_BOXES = "item_boxes"
#: Re-admitted on an arrival page that shows text: its drain is found by
#: that text, which proves it fired, and carries the bag delta.
_FROM_THE_DRAIN = frozenset({"trigger", "text", "item_grant", "choice"})
#: State writes, read back once the page has finished (see the body).
_STATE_WRITE_KINDS = frozenset(
    {"switch_write", "var_write", "self_switch_write", "engine_flag_write"})

# -- text matching ---------------------------------------------------------
#
# The floor holds the source's text; the ROM shows what `format()` re-wrapped
# and `StringExpandPlaceholders` expanded, decoded with its line breaks as
# `\n`/`\l`/`\p` tokens (`emulator.decode_text_bytes`). So both sides are
# compared as words: breaks and runs of spaces are one space, and a `{...}`
# code in the expected text (a placeholder the ROM expanded, a pause it
# consumed) matches anything.
# One RUN of breaks and spaces is one space: a source break followed by a
# space (Moki Town's sign, `Moki Town\n “Town...`, ROM run 41) is one gap.
_BREAKS = re.compile(r"(?:\\[nlp]|\s)+")
_CODE = re.compile(r"\{[^}]*\}")


def _words(text: str) -> str:
    return _BREAKS.sub(" ", text).strip()


def text_matches(expected: str, actual: str) -> bool:
    """Does the ROM's decoded `actual` show the floor's `expected` line?"""
    pieces = [re.escape(_words(p)) for p in _CODE.split(expected)]
    pattern = r".*?".join(p for p in pieces if p) or r""
    return re.search(pattern, _words(actual)) is not None


def shows_in_order(expected: Sequence[str], messages: Sequence[str]) -> bool:
    """Every `expected` line matches a message, in order (one message per
    line; the same line twice in a row counts once, as the emulator's
    transcript logs it)."""
    wanted = [t for i, t in enumerate(expected) if i == 0 or t != expected[i - 1]]
    i = 0
    for message in messages:
        if i < len(wanted) and text_matches(wanted[i], message):
            i += 1
    return i == len(wanted)


def _player_facing(emu: "Emulator") -> str:
    return emu.object_event(emu.resolve_constant("LOCALID_PLAYER")).facing


def _handle_trigger(emu: "Emulator", beat_name: str, step: Step, *,
                    talk_if_unseen: bool = False) -> None:
    """Fire the page. The body has already walked to the approach cell and
    faced the event, so `action` presses A and a touch trigger steps into
    it; an autorun/parallel page must already hold the field. Trigger
    names are the floor's own vocabulary (`story_state.extract`:
    action/player_touch/event_touch/autorun/parallel).

    `talk_if_unseen`: the event is a ROM sight trainer. Its "touch" is the
    engine's line-of-sight check, which runs only as the player finishes a
    step and only along the trainer's current facing; a trainer with a
    turning movement type (Route 1 ev053, FACE_DOWN_AND_LEFT) may face
    away when the player arrives, and bumping into it then starts nothing
    (PROJECT_TODO #133). Pressing A on it runs the same trainerbattle
    script, so that is the fallback."""
    trigger = dict(step.params).get("trigger")
    if trigger == "action":
        emu.interact()  # raises if no script picks up the field
    elif trigger in ("player_touch", "event_touch"):
        assertions.try_step(emu, _player_facing(emu))
        if not emu.field_locked() and talk_if_unseen:
            emu.interact(require_script=False)
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


_TEXT_WAIT_FRAMES = 900


def _handle_text(emu: "Emulator", beat_name: str, step: Step) -> None:
    params = dict(step.params)
    expected = params["text"]
    # The script can walk NPCs around between two lines (ROM run 32: Theo's
    # eight-tile exit before the professor's next line), so the default
    # 180-frame wait is too short.
    text = emu.wait_for_field_message(frame_budget=_TEXT_WAIT_FRAMES)
    if text is None or not text_matches(expected, text):
        shot = emu.screenshot(f"{beat_name}_text_{params.get('index')}")
        raise ScenarioError(
            f"{beat_name}: {step.row_id} message {params.get('index')} "
            f"expected to contain {expected!r}, got {text!r} ({shot})"
        )
    emu.clear_field_message()
    emu.dismiss_message()


def _menu_result_ok(emu: "Emulator", answer: int, result: int, yesno: bool) -> bool:
    """Did the script receive what answering arm `answer` should give it
    (the same expectations `_handle_choice` checks live)?"""
    if yesno:
        return result == (1 if answer == 0 else 0)
    if answer < 0:
        return result == emu.resolve_constant("MULTI_B_PRESSED")
    return result == answer


def _arrival_drain(emu: "Emulator", beat_name: str, map_constant: str,
                   texts: Sequence[Step],
                   answers: Sequence[int] = ()):  # noqa: ANN202 -- emulator.Drain
    """The latest script drained on `map_constant` that showed `texts` in
    order and answered its menus with `answers` (each read back as the
    script got it): the arrival page's own firing, whichever beat's
    crossing drove it. Raises when there is none -- the page never fired
    this way on this walk."""
    loc = (emu.resolve_constant(f"MAP_GROUP({map_constant})"),
           emu.resolve_constant(f"MAP_NUM({map_constant})"))
    expected = [str(dict(s.params)["text"]) for s in texts]
    shown = [d for d in reversed(emu.drains)
             if tuple(d.map_location) == loc and shows_in_order(expected, d.messages)]
    for drain in shown:
        menus = drain.menus[:len(answers)]
        if [m[0] for m in menus] == list(answers) and all(
                _menu_result_ok(emu, *m) for m in menus):
            return drain
    rows = sorted({s.row_id for s in texts})
    if shown:
        raise ScenarioError(
            f"{beat_name}: {rows}'s text showed on {map_constant}, but no such drain "
            f"answered its menus {list(answers)} as planned (menus seen: "
            f"{[d.menus for d in shown]})")
    raise ScenarioError(
        f"{beat_name}: no script drained on {map_constant} showed {rows}'s "
        f"{len(expected)} line(s) in order -- the arrival page didn't fire on "
        f"this walk (last drains: {[d.messages[:1] for d in emu.drains[-3:]]})")


def _check_arrival_drain(emu: "Emulator", beat_name: str, map_constant: str,
                         texts: Sequence[Step], grants: Sequence[Step],
                         grant_const: dict[str, str], answers: Sequence[int] = ()) -> None:
    """An arrival page's `text`/`trigger`/`choice`/`item_grant`, read back
    from the script drained on its map that showed its text and answered
    its menus as planned: each granted item's bag delta across that drain
    is the sum of the page's grants of it."""
    drain = _arrival_drain(emu, beat_name, map_constant, texts, answers)
    totals: dict[str, int] = {}
    rows: dict[str, str] = {}
    for step in grants:
        params = dict(step.params)
        const = grant_const[str(params["item"])]
        totals[const] = totals.get(const, 0) + int(params["quantity"])
        rows[const] = step.row_id
    for const, total in sorted(totals.items()):
        item_id = emu.resolve_constant(const)
        got = drain.bag_after.get(item_id, 0) - drain.bag_before.get(item_id, 0)
        if got != total:
            raise ScenarioError(
                f"{beat_name}: {rows[const]}: the drain that showed its text added "
                f"{got} {const}, expected {total}")


def _handle_var_text(emu: "Emulator", beat_name: str, step: Step) -> None:
    """A `\\v[N]` line (ruling 18): the expected text is the page's own
    script evaluated on the ROM's current values of its input variables."""
    from rpg2gba.beat_floor.var_text import expected_var_text

    params = dict(step.params)
    inputs: dict[int, int] = {}
    for var_id in params["input_vars"]:
        name = _flag_registry().get_var(var_id)
        if name is None:
            raise ScenarioError(
                f"{beat_name}: {step.row_id}: var {var_id} has no minted VAR_* "
                "name in the persisted flag registry -- not guessing one")
        inputs[var_id] = emu.var(name)
    expected = expected_var_text(params["raw"], params["var_id"], params["script"], inputs)
    _handle_text(emu, beat_name, Step(step.row_id, "text", step.list_index,
                                      (("index", params["index"]), ("text", expected))))


def _handle_count_text(emu: "Emulator", beat_name: str, step: Step) -> None:
    """A dex-count line (#144): each number is predicted from ROM state the
    script under test does not compute -- the seen/caught flags, or the
    `PROFREWARDS` threshold at the ROM's rung variable -- and the line checked
    like any other text."""
    from rpg2gba.beat_floor.reward_ladder import load_profrewards
    from rpg2gba.beat_floor.var_text import expected_count_text

    params = dict(step.params)
    seen, caught = emu.pokedex_counts()
    values: dict[int, int] = {}
    for var_id, kind, arg in params["sources"]:
        if kind == "dex_seen":
            values[var_id] = seen
        elif kind == "dex_owned":
            values[var_id] = caught
        elif kind == "rung_threshold":
            name = _flag_registry().get_var(arg)
            if name is None:
                raise ScenarioError(
                    f"{beat_name}: {step.row_id}: rung var {arg} has no minted VAR_* name "
                    "in the persisted flag registry -- not guessing one")
            values[var_id] = load_profrewards()[emu.var(name) + 1].threshold
        else:
            raise ScenarioError(f"{beat_name}: {step.row_id}: unknown count source {kind!r}")
    expected = expected_count_text(params["raw"], values)
    _handle_text(emu, beat_name, Step(step.row_id, "text", step.list_index,
                                      (("index", params["index"]), ("text", expected))))


def _written(value: object) -> tuple:
    """The values a write can leave: the floor renders a write that has more
    than one possible value (a random roll, a branch-dependent assign) as a
    tuple of them, and a single value bare (`beat_floor.walk`)."""
    return value if isinstance(value, tuple) else (value,)


def _conditional_selected(
    emu: "Emulator", beat_name: str, step: Step, key: object,
) -> tuple | None:
    """For a conditional write (`beat_floor.cond_write`): the value the
    page's script writes to `key` on the ROM's own input values, as a
    one-tuple, or None when those inputs leave `key` alone (nothing to
    check). An unconditional write returns its floor value unchanged."""
    from rpg2gba.beat_floor.cond_write import evaluated_writes

    params = dict(step.params)
    if "script" not in params:
        return _written(params["value"])
    inputs: dict[int, int] = {}
    for var_id in params["input_vars"]:
        name = _flag_registry().get_var(var_id)
        if name is None:
            raise ScenarioError(
                f"{beat_name}: {step.row_id}: var {var_id} has no minted VAR_* "
                "name in the persisted flag registry -- not guessing one")
        inputs[var_id] = emu.var(name)
    writes = evaluated_writes(params["script"], inputs)
    if key not in writes:
        return None
    return (writes[key],)


def _handle_switch_write(emu: "Emulator", beat_name: str, step: Step) -> None:
    params = dict(step.params)
    switch_id = params["switch_id"]
    name = _flag_registry().get_flag(switch_id)
    if name is None:
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: switch {switch_id} has no minted "
            "FLAG_* name in the persisted flag registry -- not guessing one"
        )
    selected = _conditional_selected(emu, beat_name, step, Switch(switch_id))
    if selected is None:
        return
    expected = tuple(bool(v) for v in selected)
    actual = emu.flag(name)
    if actual not in expected:
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
    if params.get("op") == "=":
        expected = _conditional_selected(emu, beat_name, step, Variable(var_id))
        if expected is None:
            return
        if actual not in expected:
            shot = emu.screenshot(f"{beat_name}_var_{var_id}")
            raise ScenarioError(
                f"{beat_name}: {step.row_id}: {name} reads {actual!r}, "
                f"expected one of {expected!r} after an assign ({shot})"
            )
    # An "Adjust" op is a relative change; this step has no "before" value
    # to diff against (steps_for is pure, no emulator access), so the
    # honest check here is that the var resolves and reads at all -- a
    # missing/unresolvable name still raises above.


def _handle_self_switch_write(emu: "Emulator", beat_name: str, step: Step) -> None:
    params = dict(step.params)
    map_id = parse_row_id(step.row_id).map_id
    name = self_switch_flag_name(map_id, params["event_id"], str(params["letter"]))
    selected = _conditional_selected(
        emu, beat_name, step, SelfSwitch(map_id, params["event_id"], str(params["letter"])))
    if selected is None:
        return
    expected = tuple(bool(v) for v in selected)
    tree_id = native_berry_tree_id(map_id, params["event_id"])
    if tree_id is not None:
        # Emitted as a native berry tree: the pick blanks the tree's own
        # saved state, and that IS this write (operator ruling 2026-10-01,
        # the bfee6641 shape); the RMXP self-switch flag is never set.
        name = f"berry tree {tree_id} picked"
        actual = emu.berry_tree_picked(tree_id)
    else:
        actual = emu.flag(name)
    if actual not in expected:
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


_OPS: dict[str, Callable[[int, int], bool]] = {
    "==": lambda a, b: a == b, "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b, "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b, ">=": lambda a, b: a >= b,
}


def _guard_holds(emu: "Emulator", beat_name: str,
                 guard: tuple[tuple[int, str, int], ...]) -> bool:
    """A random arm's guard path, read from the ROM's variables (ruling 19)."""
    for var_id, op, value in guard:
        name = _flag_registry().get_var(var_id)
        if name is None:
            raise ScenarioError(
                f"{beat_name}: var {var_id} has no minted VAR_* name in the "
                "persisted flag registry -- not guessing one")
        if not _OPS[op](emu.var(name), value):
            return False
    return True


#: `gSpecialVar_Result` while a multichoice waits for input.
_MENU_WAITING = 0xFF


def _handle_choice(emu: "Emulator", beat_name: str, step: Step) -> None:
    """Answer a choice menu and read back what the script received (ruling
    19). The transpiler emits a two-option choice as `yesnobox` (YES=1,
    NO/B=0 in `gSpecialVar_Result`) and a longer one as a multichoice (the
    picked index). `answer` is the arm's choice index, added by the body
    from `choice_answers`; -1 is the cancel arm, i.e. B."""
    params = dict(step.params)
    if "answer" not in params:
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: choice at list[{step.list_index}] has no "
            "answer -- generic_beat(choice_answers=) must name one")
    options, answer = tuple(params["options"]), int(params["answer"])
    result_addr = emu.symbols["gSpecialVar_Result"]
    # An inline `\\ch[...]` menu is always a `dynmultichoice` (never
    # `yesnobox`), even with two options; its pick is then copied to a game var.
    inline = bool(params.get("inline"))
    yesno = len(options) == 2 and not inline
    if inline and answer < 0 and int(params["if_cancel"]) == 0:
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: inline choice at list[{step.list_index}] "
            "ignores B (ifCancel 0) -- no cancel arm to answer")

    for _ in range(600):
        if emu.yesno_prompt_up() if yesno else emu.u16(result_addr) == _MENU_WAITING:
            break
        emu.run(1)
    else:
        shot = emu.screenshot(f"{beat_name}_no_menu")
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: no {'yes/no' if yesno else 'choice'} menu "
            f"came up for {options!r} ({shot})")

    if yesno:
        emu.tap("A" if answer == 0 else "B")
        expected = 1 if answer == 0 else 0
    elif answer < 0:
        emu.tap("B")
        expected = emu.resolve_constant("MULTI_B_PRESSED")
    else:
        for _ in range(answer):
            emu.tap("DOWN")
        emu.tap("A")
        expected = answer
    got = emu.u16(result_addr)
    if got != expected:
        shot = emu.screenshot(f"{beat_name}_choice")
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: answered {answer} to {options!r} but the "
            f"script received {got}, expected {expected} ({shot})")
    if inline:
        _check_inline_choice_var(emu, beat_name, step, params, answer)


def _check_inline_choice_var(emu: "Emulator", beat_name: str, step: Step,
                             params: dict, answer: int) -> None:
    """The transpiled inline choice copies `VAR_RESULT` into the `\\ch`'s own
    game variable (`if_cancel - 1` on B): read that variable back once the
    script has run the copy."""
    name = _flag_registry().get_var(int(params["var_id"]))
    if name is None:
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: inline choice variable {params['var_id']} has "
            "no minted VAR_* name in the persisted flag registry -- not guessing one")
    expected = int(params["if_cancel"]) - 1 if answer < 0 else answer
    if not _wait_for(emu, lambda: emu.var(name) == expected, frames=120):
        shot = emu.screenshot(f"{beat_name}_choice_var")
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: answered {answer} to inline choice "
            f"{tuple(params['options'])!r} but {name} reads {emu.var(name)}, "
            f"expected {expected} ({shot})")


def _phone_trainer(row_id: str, beat_name: str, lookup: FloorLookup, manifest_id: str) -> str:
    """The trainer a `phone_register` row registers: the one trainer battled
    on any page of the same event (the register call often sits on the
    rematch page, the battle on the first). Fails loud on none or several."""
    from rpg2gba.beat_gen.adapt import _trainer_const_for
    from rpg2gba.pbs_converter._naming import to_constant

    parsed = parse_row_id(row_id)
    event_rows = [r.row_id for r in load_chapter_rows(manifest_id)
                  if r.map_id == parsed.map_id and r.event_id == parsed.event_id]
    trainers = {
        (a.param("name"), a.param("trainer_type"))
        for rid in event_rows for a in lookup(rid).assertions
        if a.kind == "battle" and a.param("kind") == "trainer"}
    if len(trainers) != 1:
        raise ValueError(
            f"generic_beat: {beat_name}: {row_id} registers a phone contact, but its "
            f"event battles {sorted(trainers) or 'no trainer'} -- need exactly one")
    (name, trainer_type), = trainers
    return _trainer_const_for(name, to_constant("TRAINER_CLASS", trainer_type), row_id=row_id)


@functools.cache
def _staged_trainer_consts() -> frozenset[str]:
    """The `TRAINER_*` consts the ROM is built with: the trainer staging
    manifest's battles (`trainer_converter.stage.write_all`), honoring
    `RPG2GBA_OUTPUT` like the rest of the pipeline."""
    root = Path(os.environ.get("RPG2GBA_OUTPUT", "output"))
    path = root / "uranium-build" / "trainers" / "trainer_manifest.json"
    if not path.exists():
        raise ScenarioError(f"generic template: no trainer staging manifest at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return frozenset(t["trainer_constant"] for t in data["trainers"] if t["kind"] == "battle")


def _battle_consts(step: Step, beat_name: str) -> tuple[str, ...]:
    """The trainers.json consts a trainer `battle` step can be against,
    among those staged into the ROM. trainers.json holds the whole corpus
    (every later Theo party too, 2026-09-29 ROM run 28: TRAINER_THEO_12 is
    not in the build), and a party the ROM lacks can't be the one fought.
    Fails loud when none is staged."""
    from rpg2gba.beat_gen.adapt import trainer_consts_for
    from rpg2gba.pbs_converter._naming import to_constant

    params = dict(step.params)
    candidates = trainer_consts_for(
        str(params["name"]), to_constant("TRAINER_CLASS", str(params["trainer_type"])),
        row_id=f"{beat_name}: {step.row_id}")
    staged = tuple(c for c in candidates if c in _staged_trainer_consts())
    if not staged:
        raise ValueError(
            f"generic_beat: {beat_name}: {step.row_id} battles {params['name']!r}, but "
            f"none of {candidates} is staged into the ROM build")
    return staged


def _wait_for(emu: "Emulator", cond: Callable[[], bool], frames: int = 600) -> bool:
    for _ in range(frames):
        if cond():
            return True
        emu.run(1)
    return cond()


@functools.lru_cache(maxsize=1)
def _starter_reveal_lines() -> tuple[str, ...]:
    """Each starter's reveal line, read and translated exactly as the
    transpiler emits it (`reference/starter_selector_scene.json`, §4.3)."""
    from rpg2gba.conversion_agent.transpiler import (
        _load_starter_selector_scene, translate_text_codes)
    starters = _load_starter_selector_scene(Path("reference")).get("starters") or []
    lines: list[str] = []
    for starter in starters:
        result = translate_text_codes(starter["reveal"])
        if result is None:
            raise ScenarioError(f"starter reveal {starter['reveal']!r} has an untranslatable code")
        lines.append(result.text)
    if not lines:
        raise ScenarioError("reference/starter_selector_scene.json has no starters")
    return tuple(lines)


def _service_failed(emu: "Emulator", beat_name: str, step: Step, what: str) -> ScenarioError:
    shot = emu.screenshot(f"{beat_name}_{dict(step.params)['name']}")
    return ScenarioError(f"{beat_name}: {step.row_id}: {what} ({shot})")


def _handle_service(emu: "Emulator", beat_name: str, step: Step) -> None:
    """Ruling 20: the native UI opened, the walk backed out, and control came
    back to the script, plus the service's one fact where the engine leaves
    one. `phone_register` is checked after the page instead (its step carries
    `trainer` then, added by the body)."""
    params = dict(step.params)
    name = params["name"]
    result_addr = emu.symbols["gSpecialVar_Result"]
    if name == "pc":
        # EventScript_PC: boot text, then a multichoice (0xFF while waiting);
        # B answers MULTI_B_PRESSED -> EventScript_TurnOffPC.
        emu.write_u16(result_addr, 0)
        emu.advance_dialog("B", stop=lambda: emu.u16(result_addr) == _MENU_WAITING)
        if emu.u16(result_addr) != _MENU_WAITING:
            raise _service_failed(emu, beat_name, step, "the PC menu never came up")
        emu.tap("B")
        if emu.u16(result_addr) != emu.resolve_constant("MULTI_B_PRESSED"):
            raise _service_failed(emu, beat_name, step, "B at the PC menu did not reach it")
    elif name == "region_map":
        main_cb2 = emu.symbols["gMain"] + emu.offsets["off_main_callback2"]
        overworld = emu.symbols["CB2_Overworld"] | 1
        if not _wait_for(emu, lambda: emu.u32(main_cb2) != overworld):
            raise _service_failed(emu, beat_name, step, "the region map never opened")
        for _ in range(40):
            if emu.u32(main_cb2) == overworld:
                break
            emu.tap("B")
        else:
            raise _service_failed(emu, beat_name, step, "the region map never handed back")
    elif name == "berry_plant":
        if emu.wait_for_field_message() is None:
            raise _service_failed(emu, beat_name, step, "the berry tree showed nothing")
        emu.advance_dialog("B")
    elif name == "mart":
        # The body cleared sMartInfo's list before the walk: set again = opened.
        emu.advance_dialog("B", stop=lambda: bool(emu.mart_items()))
        got = emu.mart_items()
        if not got:
            raise _service_failed(emu, beat_name, step, "the mart never opened")
        expected = [emu.resolve_constant(c) for c in params["consts"]]
        if got != expected:
            raise _service_failed(emu, beat_name, step,
                                  f"the mart sells {got}, expected {expected}")
        emu.tap("B")  # Quit
    elif name == "starter_select":
        # The transpiled reveal is speech only (transpiler
        # `_emit_starter_selector`, user call 2026-08-01: the sprite is the
        # gift ceremony's job), so the fact is one of the scene's reveal lines
        # on screen -- not a mon pic, which this scene never draws. Stop on
        # it, dismiss it as a text step would, and leave the rest of the page
        # to the steps after this one.
        # The hit is latched inside the stop check: `advance_dialog` wipes
        # `gStringVar4` on exit (`clear_field_message`), so re-reading the
        # text afterwards always sees nothing (ROM run 22).
        reveals = _starter_reveal_lines()
        seen: list[str] = []

        def revealed() -> bool:
            text = emu.current_field_message_text()
            if text is not None and any(text_matches(r, text) for r in reveals):
                seen.append(text)
            return bool(seen)

        emu.advance_dialog("A", stop=revealed)
        if not seen:
            raise _service_failed(emu, beat_name, step,
                                  f"no starter reveal line ({reveals}) showed")
        # The reveal box is still up, but its buffer is gone; dismiss it so
        # the next text step reads the line after it (ROM run 23).
        emu.dismiss_message()
    elif name == "phone_register":
        if "trainer" not in params:
            raise _service_failed(emu, beat_name, step,
                                  "phone_register is checked after the page completes")
        if not emu.match_call_registered(params["trainer"]):
            raise _service_failed(emu, beat_name, step,
                                  f"{params['trainer']} is not registered for match call")
    else:
        raise _service_failed(emu, beat_name, step, f"no check for service {name!r}")


def _handle_item_grant(emu: "Emulator", beat_name: str, step: Step) -> None:
    # Called by `generic_beat`'s body after `completes`, with `const` and
    # `expected_total` added to the floor params (module docstring).
    params = dict(step.params)
    if "expected_total" not in params:
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: item_grant is checked by generic_beat "
            "after the page completes, not as a mid-page step")
    actual = emu.bag_item_quantity(params["const"])
    if actual != params["expected_total"]:
        shot = emu.screenshot(f"{beat_name}_item_{params['const'].lower()}")
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: bag holds {actual} {params['const']}, "
            f"expected {params['expected_total']} after the grant ({shot})")


def _handle_item_remove(emu: "Emulator", beat_name: str, step: Step) -> None:
    # `removeitem` is silent (no box), so like item_grant this is checked by
    # `generic_beat`'s body after the page, with `const` and `expected_total`.
    params = dict(step.params)
    if "expected_total" not in params:
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: item_remove is checked by generic_beat "
            "after the page completes, not as a mid-page step")
    actual = emu.bag_item_quantity(params["const"])
    if actual != params["expected_total"]:
        shot = emu.screenshot(f"{beat_name}_item_{params['const'].lower()}")
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: bag holds {actual} {params['const']}, "
            f"expected {params['expected_total']} after the removal ({shot})")


def _gift_ceremony(emu: "Emulator", beat_name: str, row_id: str) -> None:
    """Get through the transpiler's `pbAddPokemon` flow
    (`transpiler._emit_give_pokemon`): the "{PLAYER} obtained {species}!"
    line over its fanfare, then the nickname yes/no, answered NO -- A would
    commit YES and open the naming screen. B advances plain boxes too, and
    answers NO if it meets the prompt first."""
    text = emu.wait_for_field_message(frame_budget=600)
    if text is None or not text_matches("{PLAYER} obtained", text):
        shot = emu.screenshot(f"{beat_name}_no_gift")
        raise ScenarioError(
            f"{beat_name}: {row_id}: expected the gift's \"obtained\" line, got "
            f"{text!r} ({shot})")
    emu.advance_dialog("B", stop=emu.yesno_prompt_up)
    if emu.yesno_prompt_up():
        emu.tap("B")
    if not _wait_for(emu, lambda: not emu.yesno_prompt_up(), frames=120):
        shot = emu.screenshot(f"{beat_name}_nickname_stuck")
        raise ScenarioError(
            f"{beat_name}: {row_id}: the nickname prompt stayed up after B ({shot})")
    emu.clear_field_message()


#: `giveitem`/`finditem`'s own boxes (engine/data/scripts/obtain_item.inc,
#: engine/data/text/obtain_item.inc): "Obtained the X!" / "Obtained N Xs!" /
#: "{PLAYER} found one X!", then "{PLAYER} put away the X in the ... POCKET."
_ITEM_BOX_OPENERS = ("Obtained", "{PLAYER} found")
_ITEM_BOX_CLOSER = "{PLAYER} put away the"
#: Boxes read before the pocket line must have come. The native berry tree
#: is the longest flow (engine/data/scripts/berry_tree.inc): "You found ...
#: pick them?", "{PLAYER} picked the ...", then the pocket line -- the
#: pick prompt can be read twice while its yes/no is up (ROM run 56).
_ITEM_BOX_LIMIT = 5


def _item_boxes(emu: "Emulator", beat_name: str, row_id: str) -> None:
    """Get through an item grant's obtain boxes where the page gives it
    (ROM run 48: the Professor's `pbReceiveItem(POKeBALL,5)` opens an arm
    whose first line came after "Obtained 5 Poké Balls!", and the arm's text
    step read the obtain box instead). The first box is the obtain line, the
    last the pocket line; the fanfare plays between them."""
    text = emu.wait_for_field_message(frame_budget=600)
    if text is None or not any(text_matches(o, text) for o in _ITEM_BOX_OPENERS):
        shot = emu.screenshot(f"{beat_name}_no_item_box")
        raise ScenarioError(
            f"{beat_name}: {row_id}: expected the item grant's obtain line, got "
            f"{text!r} ({shot})")
    read = 1
    while text is None or not text_matches(_ITEM_BOX_CLOSER, text):
        if read == _ITEM_BOX_LIMIT:
            shot = emu.screenshot(f"{beat_name}_no_pocket_box")
            raise ScenarioError(
                f"{beat_name}: {row_id}: the item grant's \"put away\" line never "
                f"came in {read} boxes, last box {text!r} ({shot})")
        emu.clear_field_message()
        emu.dismiss_message()
        text = emu.wait_for_field_message(frame_budget=600)
        read += 1
    emu.clear_field_message()
    emu.dismiss_message()


def _handle_pokemon_grant(emu: "Emulator", beat_name: str, step: Step) -> None:
    """A loud `pbAddPokemon`: its ceremony comes up where the page gives,
    and the party then holds the species. `const` is added to the floor
    params by `generic_beat`."""
    params = dict(step.params)
    if "const" not in params:
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: pokemon_grant at list[{step.list_index}] has "
            "no resolved species const")
    _gift_ceremony(emu, beat_name, step.row_id)
    if not assertions.party_has_species(emu, emu.resolve_constant(params["const"])):
        shot = emu.screenshot(f"{beat_name}_no_{params['const'].lower()}")
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: {params['const']} is not in the party after "
            f"the gift ({shot})")


@functools.cache
def _uranium_species_constants() -> dict[str, str]:
    data = json.loads(Path("reference/uranium_id_map.json").read_text(encoding="utf-8"))
    return dict(data["species"])


def _handle_heal_party(emu: "Emulator", beat_name: str, step: Step) -> None:
    # The body set the lead to 1 HP before firing the page (module docstring).
    # The heal can sit behind fades the script runs after the step before it
    # (ROM run 31: the professor's fade-out/fade-in around the rival heal), so
    # give it time to land before reading.
    _wait_for(emu, lambda: _lead_full(emu), frames=600)
    assertions.require_lead_healed(emu, beat_name, step.row_id)


def _lead_full(emu: "Emulator") -> bool:
    hp, max_hp = assertions.read_lead_hp(emu)
    return hp == max_hp


def _handle_battle(emu: "Emulator", beat_name: str, step: Step) -> None:
    """Drive the script into its trainer battle, check who it is against,
    win it, and read the defeat flag for that trainer (module docstring).
    `consts` is added to the floor params by `generic_beat`."""
    from rpg2gba.playtest.battle import in_battle, win_battle

    params = dict(step.params)
    if "consts" not in params:
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: battle at list[{step.list_index}] has no "
            "resolved trainer consts -- only a trainer battle is checked")
    if not in_battle(emu):
        assertions.advance_to_battle(emu)
    if not in_battle(emu):
        shot = emu.screenshot(f"{beat_name}_no_battle")
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: no battle started for {params['name']} "
            f"({shot})")
    if not emu.is_trainer_battle():
        shot = emu.screenshot(f"{beat_name}_wild_not_trainer")
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: a battle started, but not a trainer "
            f"battle ({shot})")
    expected = {emu.resolve_constant(c): c for c in params["consts"]}
    actual = emu.opponent_trainer_id()
    if actual not in expected:
        shot = emu.screenshot(f"{beat_name}_wrong_trainer")
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: fought trainer id {actual}, not one of "
            f"{sorted(params['consts'])} ({shot})")
    # Stop at the overworld: the rest of the page is this beat's to check.
    # The battle leaves its own defeat line in the field message buffer
    # (ROM run 30: "What? B-but I was s'posed to win!"), so clear it before
    # the next text step reads.
    win_battle(emu, finish_script=False)
    emu.clear_field_message()
    flag_id = emu.resolve_constant("TRAINER_FLAGS_START") + actual
    if not _wait_for(emu, lambda: emu.flag(flag_id), frames=120):
        shot = emu.screenshot(f"{beat_name}_not_defeated")
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: {expected[actual]}'s defeat flag is not "
            f"set after the win ({shot})")


def _handle_erase_event(emu: "Emulator", beat_name: str, step: Step) -> None:
    """`pbEraseThisEvent` / code 116 is `removeobject`: once the page has run
    the event's object is no longer an ACTIVE slot in `gObjectEvents`
    (`Emulator.object_events`). The event is on the row's own map and is
    addressed by its compiled local id (`cells.local_id`)."""
    from rpg2gba.routing.locations import _map_constant_for  # the only resolver

    event_id = int(dict(step.params)["event_id"])
    map_constant = _map_constant_for(parse_row_id(step.row_id).map_id)
    lid = local_id(map_constant, event_id)
    if any(ev.local_id == lid for ev in emu.object_events()):
        shot = emu.screenshot(f"{beat_name}_erase_{event_id}")
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: event {event_id} (local id {lid}) is still an "
            f"active object after its page erased it ({shot})")


STEP_HANDLERS.update({
    "erase_event": _handle_erase_event,
    "battle": _handle_battle,
    "choice": _handle_choice,
    "service": _handle_service,
    "heal_party": _handle_heal_party,
    "item_grant": _handle_item_grant,
    "item_remove": _handle_item_remove,
    "pokemon_grant": _handle_pokemon_grant,
    "var_text": _handle_var_text,
    "count_text": _handle_count_text,
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
    random_arms: Sequence[tuple[str, tuple[tuple[int, str, int], ...]]] = (),
    walk_rows: Sequence[str] = (),
    choice_answers: Sequence[tuple[int, int]] = (),
    gift_ceremonies: Sequence[int] = (),
    archetype: Sequence[tuple[str, str]] = (),
) -> None:
    """Register one generic beat claiming `rows` (a page row and/or its
    arms). `archetype` pairs rows with the archetype this beat claims for
    them: set when beat_gen hands an archetype match to the generic template
    because it checks the page more fully (`_generic_reads_it_better`), so
    the manifest's conformance rule still sees the archetype claimed. `random_arms` (ruling 19) pairs each RNG-selected arm among
    `rows` with its guard path `((var_id, op, value), ...)`: those arms are
    claimed but not declared, and the body checks only the one whose guard
    holds on the ROM's values once the page has rolled.

    `walk_rows` (ruling 19) are rows whose steps the body drives, in order,
    without claiming or declaring them: a beat split off for one choice arm
    still has to read the page's shared messages to stay in step with the
    screen. `choice_answers` pairs each choice command's list index with the
    arm index to answer (-1 for the cancel arm). With `skip_claimed=True`, rows some earlier beat in `builder`
    already claims are dropped first, and if none remain nothing is
    registered. Fails loud (`ValueError`) on a refused floor.
    `manifest_chapter_id=` names a predecessor whose manifest carries the
    rows (a successor boundary claim, §10 R2), as `find_match` takes it.
    `gift_ceremonies` are the owning page's list indexes where an unclaimed,
    refused gift arm runs its ceremony (`beat_gen/gift_ceremony.py`): the
    body answers NO there and checks nothing."""
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
    walked_rows = resolved_rows + tuple(r for r in walk_rows if r not in resolved_rows)
    floors: dict[str, RowFloor] = {}
    for row_id in walked_rows:
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
    all_steps = [s for row_id in walked_rows for s in steps_for(floors[row_id])]
    answers = dict(choice_answers)
    for i, step in enumerate(all_steps):
        if step.kind != "choice":
            continue
        if step.list_index not in answers:
            raise ValueError(
                f"generic_beat: {beat_name}: {step.row_id} has a choice at "
                f"list[{step.list_index}] and no choice_answers entry for it")
        all_steps[i] = Step(step.row_id, step.kind, step.list_index,
                            step.params + (("answer", answers[step.list_index]),))
    for i, step in enumerate(all_steps):
        if step.kind != "pokemon_grant":
            continue
        species = str(dict(step.params)["species"])
        const = _uranium_species_constants().get(species)
        if const is None:
            raise ValueError(
                f"generic_beat: {beat_name}: {step.row_id} gives {species!r}, which has "
                "no entry in reference/uranium_id_map.json's 'species' table")
        all_steps[i] = Step(step.row_id, step.kind, step.list_index,
                            step.params + (("const", const),))
    all_steps.extend(Step(page_row_id, _GIFT_CEREMONY, i, ()) for i in gift_ceremonies)
    triggers = [s for s in all_steps if s.kind == "trigger"]
    trigger_step = triggers[0] if triggers else None
    completes_step = next((s for s in all_steps if s.kind == "completes"), None)
    # A beat that rides a re-fire in one interaction (a choice round trip: the
    # page answered, then an autorun of the same event firing at once) walks
    # each page's steps in turn: list indexes only order steps within a page,
    # and pages rank by first appearance in `rows` then `walk_rows`.
    page_rank: dict[str, int] = {}
    for row_id in walked_rows:
        page_rank.setdefault(parse_row_id(row_id).owning_page_row_id or row_id, len(page_rank))
    middle_steps = sorted(
        (s for s in all_steps if s.kind not in _FORCED_BUCKET),
        key=lambda s: (page_rank[parse_row_id(s.row_id).owning_page_row_id or s.row_id],
                       s.list_index, s.kind, s.row_id, repr(s.params)))

    # A player-triggered page is fired from an ADJACENT cell, facing the
    # event: `cell_for_row` puts the routing point ON a touch event's cell,
    # and walking onto it would fire the page mid-walk. Autorun/parallel
    # pages fire on their own; the beat stands on the routing point.
    trigger = dict(trigger_step.params).get("trigger") if trigger_step else None
    faces_target: tuple[int, int] | None = None
    walks_off: int | None = None      # local id of an action NPC that walks on its own
    walker_route = None               # its looping custom route, if it has one
    touch_trainer = False             # a touch page on a ROM sight trainer
    sight_trainer = False             # walks_off is a sight trainer: no approach walk first
    empty_page = False                # an action page with no commands: A is a no-op
    arrival = trigger in _ARRIVAL_TRIGGERS
    random_rows = {r for r, _ in random_arms}
    arrival_texts: list[Step] = []
    arrival_grants: list[Step] = []
    arrival_answers: tuple[int, ...] = ()
    arrival_kinds: frozenset[str] = frozenset()
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
        # Read back from the drain that ran it (`_arrival_drain`): found by
        # the page's text, which proves it fired, with the bag delta its
        # grants made. With no text, a write to its own self switch is the
        # proof it fired (the handler checks it); nothing else is.
        arrival_texts = [s for s in middle_steps
                         if s.kind == "text" and s.row_id not in random_rows]
        if arrival_texts:
            arrival_kinds = _FROM_THE_DRAIN
            arrival_grants = [s for s in middle_steps
                              if s.kind == "item_grant" and s.row_id not in random_rows]
            # The drain meets the page's menus in source order; a random
            # arm's menu may not open, so none is planned past one.
            arrival_answers = tuple(int(dict(s.params)["answer"]) for s in middle_steps
                                    if s.kind == "choice" and s.row_id not in random_rows)
        elif page_row_id in resolved_rows and any(
                s.kind == "self_switch_write" and s.row_id == page_row_id
                and dict(s.params).get("event_id") == page_row.event_id
                and dict(s.params).get("value") is True
                for s in middle_steps):
            arrival_kinds = frozenset({"trigger"})
        elif page_row_id in resolved_rows and any(
                s.kind == "erase_event" and s.row_id == page_row_id
                and dict(s.params).get("event_id") == page_row.event_id
                for s in middle_steps):
            # Erasing ITS OWN event is the other proof the page fired: the
            # object is gone (`_handle_erase_event`) only if the page ran
            # (Kevlar's cleanup autorun, Map031 EV049 p2).
            arrival_kinds = frozenset({"trigger"})
        middle_steps = [s for s in middle_steps
                        if s.kind not in _NOT_AFTER_THE_FACT and s.kind != _GIFT_CEREMONY]
    elif trigger in _PLAYER_TRIGGERS and page_row.event_id is not None:
        faces_target = event_cell(cell.map_constant, page_row.event_id)
        x, y = approach_to(cell.map_constant, page_row.event_id, prefer=approach_prefer)
        page_idx = parse_row_id(page_row_id).page_idx
        touch_trainer = (trigger in ("player_touch", "event_touch")
                         and event_is_sight_trainer(cell.map_constant, page_row.event_id))
        if trigger == "action" and page_idx is not None:
            if event_page_empty(cell.map_constant, page_row.event_id, page_idx):
                empty_page = True
            elif event_page_moves(cell.map_constant, page_row.event_id, page_idx):
                walks_off = local_id(cell.map_constant, page_row.event_id)
                walker_route = custom_route_loop(cell.map_constant, page_row.event_id)
            elif (not any(s.kind == "battle" for s in middle_steps)
                  and event_is_sight_trainer(cell.map_constant, page_row.event_id)):
                # After its battle (a later page): it may have walked up to
                # the player and be standing on the approach cell, so talk
                # to it where it is, without first walking to the cell its
                # spawn derives. The battle page itself keeps the plain
                # walk, whose sight interruption is the trigger.
                walks_off = local_id(cell.map_constant, page_row.event_id)
                sight_trainer = True
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

    random_guard = dict(random_arms)
    declared = declare_assertions(
        tuple(r for r in resolved_rows if r not in random_guard),
        executed_kinds=GENERIC_EXECUTED_KINDS - (
            _NOT_AFTER_THE_FACT - arrival_kinds if arrival else frozenset()),
        template="generic", floor_lookup=resolved_lookup,
    )

    # service (ruling 20): only the services `_handle_service` can prove are
    # declared or driven; a mart's stock and a phone registration's trainer
    # are resolved now; phone_register is checked after `completes`.
    declared = frozenset(
        a for a in declared
        if (a.kind != "service" or a.param("name") in SUPPORTED_SERVICES)
        and (a.kind != "battle" or a.param("kind") == "trainer"))
    middle_steps = [
        s for s in middle_steps
        if (s.kind != "service" or dict(s.params)["name"] in SUPPORTED_SERVICES)
        and (s.kind != "battle" or dict(s.params).get("kind") == "trainer")]
    phone_steps: list[Step] = []
    resolved_steps: list[Step] = []
    for step in middle_steps:
        name = dict(step.params).get("name") if step.kind == "service" else None
        if name == "mart":
            consts = []
            for item in dict(step.params)["items"]:
                const = _uranium_item_constants().get(str(item))
                if const is None:
                    raise ValueError(
                        f"generic_beat: {beat_name}: {step.row_id} sells {item!r}, which "
                        "has no entry in reference/uranium_id_map.json's 'items' table")
                consts.append(const)
            step = Step(step.row_id, step.kind, step.list_index,
                        step.params + (("consts", tuple(consts)),))
        elif step.kind == "battle":
            step = Step(step.row_id, step.kind, step.list_index, step.params + (
                ("consts", _battle_consts(step, beat_name)),))
        elif name == "phone_register":
            phone_steps.append(Step(step.row_id, step.kind, step.list_index, step.params + (
                ("trainer", _phone_trainer(step.row_id, beat_name, resolved_lookup,
                                           manifest_chapter_id or chapter_id)),)))
            continue
        resolved_steps.append(step)
    middle_steps = resolved_steps
    has_mart = any(dict(s.params).get("name") == "mart" for s in middle_steps
                   if s.kind == "service")

    # item_grant: resolved now (an unmapped item fails at import, not
    # mid-walk) and checked after `completes` (module docstring).
    # A random arm's grant may not happen, so it isn't counted (ruling 19).
    grant_steps = arrival_grants if arrival else [
        s for s in middle_steps if s.kind == "item_grant" and s.row_id not in random_guard]
    # Its obtain boxes still come up where the page gives it, between the
    # lines around it: an `_ITEM_BOXES` marker holds that place.
    middle_steps = [Step(s.row_id, _ITEM_BOXES, s.list_index, ()) if s.kind == "item_grant"
                    else s for s in middle_steps]
    # item_remove: silent (`removeitem` shows no box), so no marker -- it
    # leaves the in-page steps and is only checked after the page.
    remove_steps = [
        s for s in middle_steps if s.kind == "item_remove" and s.row_id not in random_guard]
    middle_steps = [s for s in middle_steps if s.kind != "item_remove"]
    if arrival:
        from rpg2gba.story_state.bag import key_item_symbols

        loose = sorted(str(dict(s.params)["item"]) for s in remove_steps
                       if str(dict(s.params)["item"]) not in key_item_symbols())
        if loose:
            raise ValueError(
                f"generic_beat: {beat_name}: arrival page removes non-key item(s) {loose}; "
                "the count before the page is gone by the time the beat looks")

    # State writes: checked after `completes` too, once per key at its LAST
    # write. In source order the check could run while the script still had
    # movements and waits to go before the write (2026-09-27: Theo's Moki
    # Town intercept sets event 75's self switch after he walks off, and the
    # in-order check read it False); a key written twice is checked at the
    # value it ends on.
    last_write: dict[tuple, Step] = {}
    for step in middle_steps:
        if step.kind in _STATE_WRITE_KINDS:
            key = (step.kind,) + tuple(sorted(
                (k, v) for k, v in step.params if k != "value"))
            last_write[key] = step
    write_steps = sorted(last_write.values(), key=lambda s: (s.list_index, s.row_id))
    middle_steps = [s for s in middle_steps if s.kind not in _STATE_WRITE_KINDS]
    grant_const: dict[str, str] = {}
    for step in [*grant_steps, *remove_steps]:
        item = str(dict(step.params)["item"])
        const = _uranium_item_constants().get(item)
        if const is None:
            raise ValueError(
                f"generic_beat: {beat_name}: {step.row_id} grants or removes {item!r}, which has "
                "no entry in reference/uranium_id_map.json's 'items' table")
        grant_const[item] = const

    # heal_party after a battle: the lead is damaged once the battle is won
    # (`damage_after`), not before the walk.
    heal_at = next((i for i, s in enumerate(middle_steps)
                    if s.kind == "heal_party" and s.row_id not in random_guard), None)
    # An action arm with nothing observable (no message, write, grant or
    # call) cannot prove its script ran; "the field is unlocked after" is
    # all the ROM can show.
    silent = (trigger_step is not None
              and dict(trigger_step.params).get("trigger") == "action"
              and not (middle_steps or write_steps or grant_steps or phone_steps))
    heals = heal_at is not None
    damage_after = None if heal_at is None else next(
        (i for i in range(heal_at - 1, -1, -1) if middle_steps[i].kind == "battle"), None)

    @builder.beat(
        beat_name,
        f"Generic floor coverage for {', '.join(resolved_rows)} ({chapter_id})",
        map_constant=cell.map_constant, at=(x, y), group=group,
        rows=resolved_rows, assertions=declared,
        drain_answers=(cell.map_constant, arrival_answers) if arrival_answers else None,
        archetype={r: a for r, a in archetype if r in resolved_rows} or None,
    )
    def body(emu: "Emulator") -> None:
        from rpg2gba.playtest.emulator import WalkInterrupted

        assertions.require_map(emu, beat_name, cell.map_constant)
        fired_on_the_way = arrival       # an arrival page already ran
        if heals and damage_after is None:
            # Before the walk: a touch page can fire on the way (below).
            # Never on an arrival beat (heal_party is undeclared there).
            assertions.damage_lead(emu, beat_name)
        bag_before = {c: emu.bag_item_quantity(c) for c in sorted(set(grant_const.values()))}
        if has_mart:
            emu.clear_mart_items()
        try:
            if not arrival and not sight_trainer:
                try:
                    emu.walk_to(x, y, absorb_wild=True)
                except WalkInterrupted:
                    raise
                except ScenarioError:
                    # A walking NPC tends to stand on its own spawn-derived
                    # approach cell (ROM runs 76-77: Route 1 ev053 on
                    # (17,10), Passage Cave 2F ev005 on (8,8)). The walk
                    # still brings it on camera (object events exist only
                    # there -- skipping it lost Moki ev012, run 78); the
                    # live-position talk below takes over, and fails loud
                    # itself if the NPC is truly unreachable.
                    if walks_off is None:
                        raise
        except WalkInterrupted:
            # An event-touch page can reach the player first (the trainer
            # template's `_approach` makes the same call); the steps below
            # decide whether it was this page.
            fired_on_the_way = True
        if empty_page and not fired_on_the_way:
            # The page is empty: its dispatcher ends at once, so the check
            # is that pressing A changes nothing (hand CH03's N3 shape).
            emu.face(facing_toward((x, y), faces_target, caller="generic_beat"))
            emu.tap("A")
            emu.run(30)
            if emu.field_locked():
                shot = emu.screenshot(f"{beat_name}_unexpected_lock")
                raise ScenarioError(
                    f"{beat_name}: {page_row_id} is an empty page, but pressing A "
                    f"locked the field ({shot})")
            return
        if not fired_on_the_way:
            if walks_off is not None:
                # An NPC that walks on its own has left `faces_target`;
                # talk to it where it is now (`cells.event_page_moves`).
                assertions.talk_to_moving_npc(emu, beat_name, walks_off, route=walker_route)
            else:
                if faces_target is not None:
                    emu.face(facing_toward((x, y), faces_target, caller="generic_beat"))
                if silent:
                    # Nothing to see: the script can lock, run and release
                    # inside one frame, which no poll catches (ROM run 44:
                    # the lab PC's not-facing-up arm is lock/faceplayer/
                    # compare/release). The field unlocked after is the check.
                    emu.interact(require_script=False)
                elif trigger_step is not None:
                    if touch_trainer:
                        _handle_trigger(emu, beat_name, trigger_step,
                                        talk_if_unseen=True)
                    else:
                        STEP_HANDLERS["trigger"](emu, beat_name, trigger_step)
        for i, step in enumerate(middle_steps):
            guard = random_guard.get(step.row_id)
            if guard is not None and (step.kind == "heal_party"
                                      or not _guard_holds(emu, beat_name, guard)):
                continue  # the RNG picked a sibling arm (or: no damage to heal)
            if step.kind == _GIFT_CEREMONY:
                _gift_ceremony(emu, beat_name, step.row_id)
                continue
            if step.kind == _ITEM_BOXES:
                _item_boxes(emu, beat_name, step.row_id)
                continue
            STEP_HANDLERS[step.kind](emu, beat_name, step)
            if i == damage_after:
                # A heal after a battle: damaged now, so the lead fights at
                # full HP and the heal still has something to restore.
                assertions.damage_lead(emu, beat_name)
        if completes_step is not None:
            STEP_HANDLERS["completes"](emu, beat_name, completes_step)
        for step in write_steps:
            guard = random_guard.get(step.row_id)
            if guard is not None and not _guard_holds(emu, beat_name, guard):
                continue  # the RNG picked a sibling arm
            STEP_HANDLERS[step.kind](emu, beat_name, step)
        if arrival:
            if arrival_texts:
                _check_arrival_drain(emu, beat_name, cell.map_constant, arrival_texts,
                                     grant_steps, grant_const, arrival_answers)
            for step in remove_steps:     # key items only (checked above): now 0
                const = grant_const[str(dict(step.params)["item"])]
                STEP_HANDLERS[step.kind](emu, beat_name, Step(
                    step.row_id, step.kind, step.list_index,
                    step.params + (("const", const), ("expected_total", 0))))
            return
        # One check per item after the page: the bag only shows the sum of
        # that item's grants, so the last grant step carries the total.
        expected = dict(bag_before)
        last_step: dict[str, Step] = {}
        # Grants and removals apply in source order; a removal floors at 0.
        for step in sorted([*grant_steps, *remove_steps],
                           key=lambda s: (s.list_index, s.row_id)):
            params = dict(step.params)
            const = grant_const[str(params["item"])]
            qty = int(params["quantity"])
            if step.kind == "item_remove":
                expected[const] = max(0, expected[const] - qty)
            else:
                expected[const] += qty
            last_step[const] = step
        for const, step in sorted(last_step.items()):
            STEP_HANDLERS[step.kind](emu, beat_name, Step(
                step.row_id, step.kind, step.list_index,
                step.params + (("const", const), ("expected_total", expected[const]))))
        for step in phone_steps:
            STEP_HANDLERS["service"](emu, beat_name, step)

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
            emu.walk_to(*approach, absorb_wild=True)
            emu.face(facing)
            before = emu.player_pos()
            emu.interact()
            # Close the "rugged rock" box first (ROM run 43): left open, the
            # step below was a no-op that passed vacuously, and the walk to
            # the next obstacle stalled behind the message.
            emu.advance_dialog()
            if emu.field_locked():
                shot = emu.screenshot(f"{beat_name}_{row_id}_still_locked")
                raise ScenarioError(
                    f"{beat_name}: {row_id}: field controls are still locked "
                    f"after the {capability} obstacle's message ({shot})"
                )
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


# -- smash_beat -------------------------------------------------------------

#: Field capability -> (HM item, move) the walk teaches through the bag the
#: first time a chapter needs it (CH08 §9: "teach via the real UI, once").
#: What `smash_beat` proves of a rock page's YES arm. `trigger`: the A press
#: answered the prompt; `completes`: the field is released; `erase_event`: the
#: rock's object is gone (`_handle_erase_event`). `self_switch_write` is the
#: rock's own "smashed" page switch -- the native `EventScript_RockSmash` the
#: idiom collapses to never latches it (porymap's null flag; the rock respawns
#: on a map reload), so its observable effect IS the erase and the object-gone
#: check witnesses it. `audio`/`visual`/`displacement` are walk-checked kinds.
_SMASH_ARM_KINDS: frozenset[str] = frozenset(
    {"trigger", "completes", "erase_event", "self_switch_write"})

TEACHABLE_CAPABILITIES: dict[str, tuple[str, str]] = {
    "rock_smash": ("ITEM_HM06", "MOVE_ROCK_SMASH"),
}


def smash_beat(
    builder: ChapterBuilder,
    *,
    chapter_id: str,
    beat_name: str,
    rows: Sequence[str],
    capability: str,
    group: str | None = None,
    approach_prefer: str | None = None,
    teach: str | None = None,
    sight_trainers: Sequence[int] = (),
    floor_lookup: FloorLookup | None = None,
) -> None:
    """Register one beat that clears every `capability` obstacle in `rows`
    WITH the capability held (the positive twin of `obstacle_beat`, CH08 §9):
    interact, answer YES to the field-move prompt, then check the obstacle's
    object is gone and its cell is passable. Declares a `smashed_obstacle` per
    row, which covers that row's floor `blocked_obstacle`.

    `teach` (the capability's `capability_sites.teach_beat_name`) makes this
    the chapter's teaching beat: before the first obstacle, the party's slot-0
    member is taught the capability's HM through the bag UI unless some party
    member already knows the move. Obstacles respawn on a map reload, so this
    beat proves each one opens; nothing downstream may rely on it staying open
    across a map change.

    `sight_trainers` are the event ids of this map's trainers a later beat
    still fights: their sight lanes (`cells.trainer_sight_lanes`) are routed
    around, so a smash walk never starts a battle another beat owns. Trainers
    already beaten are not listed and not avoided."""
    resolved_lookup: FloorLookup = (
        floor_lookup if floor_lookup is not None else _default_floor_for_row)
    resolved_rows = tuple(rows)
    if not resolved_rows:
        raise ValueError(f"smash_beat: {beat_name}: rows= is empty")
    if capability not in TEACHABLE_CAPABILITIES:
        raise ValueError(
            f"smash_beat: {beat_name}: no HM/move known for capability {capability!r} "
            f"(TEACHABLE_CAPABILITIES has {sorted(TEACHABLE_CAPABILITIES)})")
    if teach is not None and teach != f"teach_{capability}":
        raise ValueError(f"smash_beat: {beat_name}: teach={teach!r} does not name "
                         f"capability {capability!r}")
    item, move = TEACHABLE_CAPABILITIES[capability]

    obstacles: dict[str, object] = {}
    arm_rows: list[str] = []
    for row_id in resolved_rows:
        floor = resolved_lookup(row_id)
        if floor.refused:
            raise ValueError(
                f"smash_beat: {beat_name}: row {row_id!r} floor is refused ({floor.refusals})")
        found = [a for a in floor.assertions if a.kind == "blocked_obstacle"]
        if not found and parse_row_id(row_id).kind == "branch":
            # The rock page's YES arm (sfx, move route, erase, encounter call):
            # claimed with its page; its floor is covered below.
            arm_rows.append(row_id)
            continue
        if len(found) != 1:
            raise ValueError(
                f"smash_beat: {beat_name}: row {row_id!r} carries {len(found)} "
                "blocked_obstacle assertions (expected exactly 1)")
        if found[0].param("capability") != capability:
            raise ValueError(
                f"smash_beat: {beat_name}: row {row_id!r} needs capability "
                f"{found[0].param('capability')!r}, not {capability!r}")
        obstacles[row_id] = found[0]

    obstacle_ids = tuple(r for r in resolved_rows if r in obstacles)
    for arm in arm_rows:
        if parse_row_id(arm).owning_page_row_id not in obstacles:
            raise ValueError(
                f"smash_beat: {beat_name}: arm {arm!r} has no blocked_obstacle page in rows=")
    chapter_rows = load_chapter_rows(chapter_id)
    row_by_id = {r.row_id: r for r in chapter_rows}
    first_row = row_by_id.get(obstacle_ids[0])
    if first_row is None:
        raise ValueError(
            f"smash_beat: {beat_name}: row {obstacle_ids[0]!r} is not in chapter "
            f"{chapter_id!r}'s manifest")
    map_constant = cell_for_row(first_row).map_constant
    first = obstacles[obstacle_ids[0]]
    x, y = first.param("x"), first.param("y")

    extras = tuple(
        FloorAssertion(
            row_id=row_id, kind="smashed_obstacle", list_index=-1, code=None,
            params=make_params(x=o.param("x"), y=o.param("y"), capability=capability),
            tag="position")
        for row_id, o in obstacles.items())
    declared = declare_assertions(
        resolved_rows, executed_kinds=_SMASH_ARM_KINDS if arm_rows else frozenset(),
        template="smash", extras=extras, floor_lookup=resolved_lookup)
    if arm_rows:
        # Only the arm rows' kinds are declared (the page rows keep their
        # floor's capability-block scoping).
        arm_set = set(arm_rows)
        declared = frozenset(
            a for a in declared
            if a.row_id in arm_set or a.kind == "smashed_obstacle")

    @builder.beat(
        beat_name,
        f"Every {capability} obstacle on {', '.join(resolved_rows)} ({chapter_id}) "
        f"clears with {capability}" + (" (teaches it first)" if teach else ""),
        map_constant=map_constant, at=(x, y), group=group,
        rows=resolved_rows, assertions=declared,
    )
    def body(emu: "Emulator") -> None:
        assertions.require_map(emu, beat_name, map_constant)
        if teach is not None and not assertions.party_knows_move(emu, move):
            from rpg2gba.playtest import scenarios  # lazy: scenarios is a heavy leaf

            scenarios.teach_hm_from_bag(emu, item, move, party_slot=0)
        if not assertions.party_knows_move(emu, move):
            raise ScenarioError(
                f"{beat_name}: no party member knows {move}; {capability} is not held "
                "(no earlier beat taught it)")
        remaining = list(obstacle_ids)
        all_lanes = trainer_sight_lanes(map_constant)
        lanes = {local_id(map_constant, ev): all_lanes[local_id(map_constant, ev)]
                 for ev in sight_trainers}
        while remaining:
            live = {ev.local_id for ev in emu.object_events() if ev.active}
            sight = frozenset().union(*(cells for lid_, cells in lanes.items() if lid_ in live))
            row_id, approach, avoid = _next_reachable_obstacle(
                emu, beat_name, map_constant, remaining, approach_prefer, sight)
            remaining.remove(row_id)
            obstacle = obstacles[row_id]
            ox, oy = obstacle.param("x"), obstacle.param("y")
            parsed = parse_row_id(row_id)
            lid = local_id(map_constant, parsed.event_id)
            facing = facing_toward(approach, (ox, oy), caller="smash_beat")
            emu.walk_to(*approach, absorb_wild=True, avoid=avoid)
            emu.face(facing)
            emu.interact()
            emu.advance_dialog(answers=[0])
            if not _wait_for(emu, lambda: not emu.field_locked()):
                shot = emu.screenshot(f"{beat_name}_{row_id}_locked")
                raise ScenarioError(
                    f"{beat_name}: {row_id}: field controls still locked after the "
                    f"{capability} prompt ({shot})")
            if any(ev.local_id == lid for ev in emu.object_events()):
                shot = emu.screenshot(f"{beat_name}_{row_id}_still_there")
                raise ScenarioError(
                    f"{beat_name}: {row_id}: obstacle (local id {lid}) at ({ox},{oy}) is "
                    f"still present after answering YES to {capability} ({shot})")
            for arm in arm_rows:
                if parse_row_id(arm).owning_page_row_id != row_id:
                    continue
                for a in resolved_lookup(arm).assertions:
                    if a.kind == "erase_event":
                        STEP_HANDLERS["erase_event"](emu, beat_name, Step(
                            arm, a.kind, a.list_index, a.params))
            before = emu.player_pos()
            if not assertions.try_step(emu, facing) or emu.player_pos() == before:
                shot = emu.screenshot(f"{beat_name}_{row_id}_impassable")
                raise ScenarioError(
                    f"{beat_name}: {row_id}: the obstacle's cell ({ox},{oy}) is still "
                    f"impassable after it was cleared ({shot})")

    del body


_SIDES: tuple[str, ...] = ("north", "south", "east", "west")


def _next_reachable_obstacle(
    emu: "Emulator",
    beat_name: str,
    map_constant: str,
    remaining: Sequence[str],
    approach_prefer: str | None,
    sight: frozenset[tuple[int, int]] = frozenset(),
) -> tuple[str, tuple[int, int], frozenset[tuple[int, int]]]:
    """The next obstacle to clear, the cell to approach it from, and the
    tiles the walk there must avoid.

    The order is chosen live, not from the rows' source order: an obstacle
    still standing is an object the planner routes around, so a fixed order
    can wall the player in behind the very rocks it clears later (CH08's first
    run: Route 1's EV036/EV038 boxed the player at (15,16) on the way to
    EV029). `sight` is the live trainers' sight lanes: an approach standing in
    one, or reachable only through one, starts a battle another beat owns
    (CH08's second run: EV040's east side sits in EV039's lane), so lane-free
    choices are tried first and the lanes are dropped only when nothing
    lane-free remains. Within a tier, the reviewed side (`approach_prefer`)
    wins, then the shortest route, then source order. Clearing only ever opens
    cells, so a greedy pick never strands the walk; no reachable approach at
    all fails loud."""
    start = emu.player_pos()
    tried: list[str] = []
    for avoid in ((sight, frozenset()) if sight else (frozenset(),)):
        best: tuple[tuple[int, int, int], str, tuple[int, int]] | None = None
        for order, row_id in enumerate(remaining):
            event_id = parse_row_id(row_id).event_id
            for side in _SIDES:
                try:
                    cell = approach_to(map_constant, event_id, prefer=side)
                except ValueError:
                    continue  # that side is not walkable on static terrain
                cell = (cell[0], cell[1])
                if cell in avoid:
                    continue
                if cell == start:
                    route = [start]
                elif avoid:
                    route = emu._plan_route(start, cell, avoid)
                else:
                    route = emu._plan_route(start, cell)
                if route is None:
                    tried.append(f"{row_id}@{side}{cell}")
                    continue
                key = (0 if side == approach_prefer else 1, len(route), order)
                if best is None or key < best[0]:
                    best = (key, row_id, cell)
        if best is not None:
            key, row_id, cell = best
            if key[0]:
                logger.info("%s: %s approached from %s, not the reviewed side %r (not "
                            "plannable from %s)", beat_name, row_id, cell, approach_prefer, start)
            if sight and not avoid:
                logger.warning("%s: no remaining obstacle is reachable outside the live "
                               "trainer sight lanes from %s; walking to %s for %s anyway",
                               beat_name, start, cell, row_id)
            return row_id, cell, avoid
    shot = emu.screenshot(f"{beat_name}_no_reachable_obstacle")
    raise ScenarioError(
        f"{beat_name}: from {start} no remaining obstacle has a plannable "
        f"approach (tried {', '.join(tried) or 'none'}) ({shot})")


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
    walk = order_stair_crossings(
        [
            StairCrossing(row_id, str(d), (int(ax), int(ay)), (int(ex), int(ey)),
                          (int(crossing.param("x")), int(crossing.param("y"))))
            for row_id, crossing in crossings.items()
            for d, ax, ay, ex, ey in crossing.param("crossings")
        ],
        prefer=approach_prefer, beat_name=beat_name,
    )
    x, y = walk[0].approach

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
        for step in walk:
            # Only a same-side hop is planned by `walk_to` (4-neighbour, so it
            # cannot route over a staircase); `order_stair_crossings` never
            # asks for any other kind.
            if emu.player_pos() != step.approach:
                emu.walk_to(*step.approach, absorb_wild=True)
            # RMXP: the bump that pushes k diagonals, then the plain step off
            # (`terrain.stair_crossings`). Natively each press moves one
            # column, so the crossing takes k + 1 presses -- the horizontal
            # span. Only the exit is asserted: the native metatiles can pass
            # different middle cells.
            for press in range(1, step.presses + 1):
                before = emu.player_pos()
                if not assertions.try_step(emu, step.direction):
                    shot = emu.screenshot(f"{beat_name}_{step.row_id}_press{press}")
                    raise ScenarioError(
                        f"{beat_name}: {step.row_id}: press {press} of "
                        f"{step.direction} from {before} did not move "
                        f"(crossing {step.approach} -> {step.exit}) ({shot})"
                    )
            after = emu.player_pos()
            if after != step.exit:
                shot = emu.screenshot(f"{beat_name}_{step.row_id}_exit")
                raise ScenarioError(
                    f"{beat_name}: {step.row_id}: crossing {step.direction} from "
                    f"{step.approach} ended at {after}, expected {step.exit} "
                    f"({shot})"
                )

    del body


@dataclass(frozen=True)
class StairCrossing:
    """One RMXP stair crossing (`terrain.stair_crossings`): from `approach`,
    `presses` presses of `direction` end on `exit`. `cell` is the stair cell
    the first press bumps; it fixes which side of the staircase a point is on."""

    row_id: str
    direction: str
    approach: tuple[int, int]
    exit: tuple[int, int]
    cell: tuple[int, int]

    @property
    def presses(self) -> int:
        """One per column crossed: 2 for a single-step stair event, k + 1
        for a k-step one."""
        return abs(self.exit[0] - self.approach[0])

    def side_of(self, point: tuple[int, int]) -> int:
        """-1/+1: which side of this crossing's cell `point` lies on, along
        the crossing's axis (0 when level with the cell)."""
        axis = 0 if self.direction in ("LEFT", "RIGHT") else 1
        delta = point[axis] - self.cell[axis]
        return (delta > 0) - (delta < 0)


_PREFER_SIGN: dict[str, tuple[int, int]] = {
    "east": (0, 1), "west": (0, -1), "south": (1, 1), "north": (1, -1)}


def order_stair_crossings(
    crossings: Sequence[StairCrossing], *, prefer: str | None, beat_name: str,
) -> tuple[StairCrossing, ...]:
    """Every crossing once, in an order the walker can play: start on the
    `prefer` side (the side the route reaches), chain into a crossing that
    starts where the last one ended, else hop to one starting on the side
    the player now stands on -- a hop `walk_to` can plan. Fails loud when
    no order covers them all, or when the walk would end across the
    staircase from where it began (the route's next beat expects the
    player back on the reached side)."""
    remaining = sorted(crossings, key=lambda c: (c.approach[1], c.approach[0], c.row_id))
    if not remaining:
        raise ValueError(f"stair_beat: {beat_name}: no crossings")
    if prefer is None:
        first = remaining[0]
    else:
        if prefer not in _PREFER_SIGN:
            raise ValueError(f"stair_beat: {beat_name}: unknown approach_prefer {prefer!r}")
        axis, sign = _PREFER_SIGN[prefer]
        first = next(
            (c for c in remaining
             if (c.approach[axis] - c.cell[axis]) * sign > 0), None)
        if first is None:
            raise ValueError(
                f"stair_beat: {beat_name}: no crossing starts on the "
                f"{prefer} side")
    order = [first]
    remaining.remove(first)
    start_side = first.side_of(first.approach)
    while remaining:
        pos = order[-1].exit
        nxt = next((c for c in remaining if c.approach == pos), None)
        if nxt is None:
            nxt = next(
                (c for c in remaining if c.side_of(pos) == c.side_of(c.approach)), None)
        if nxt is None:
            raise ValueError(
                f"stair_beat: {beat_name}: from {pos} no remaining crossing "
                f"starts on the player's side: {[c.row_id for c in remaining]}")
        order.append(nxt)
        remaining.remove(nxt)
    if first.side_of(order[-1].exit) != start_side:
        raise ValueError(
            f"stair_beat: {beat_name}: the crossings end across the staircase "
            f"at {order[-1].exit}, not back on the side they began")
    return tuple(order)


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
    # A pair joined by a REAL pokeemerald connection (not a seam_warps.json
    # arrow substitution) is crossed by walking off the edge, not by a warp.
    connection = real_connection(map_constant, other_map_constant) is not None
    if approach_prefer is not None:
        # locate.py's seam candidate side: "<press>@(x,y)".
        press, _, at = approach_prefer.partition("@")
        if press != direction or not at:
            raise ValueError(
                f"seam_beat: {beat_name}: approach_prefer={approach_prefer!r} is not "
                f"a {direction} crossing of {row_id}")
        x, y = (int(v) for v in at.strip("()").split(","))
    elif connection:
        x, y = connection_exit_cells(map_constant, to=other_map_constant)[0]
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
        if connection:
            # Arrival: other_axis = axis - (offset - to_offset), on the
            # other map's far edge row (`cells.connection_arrival_cell`).
            # The step that flips the map can land the player one tile
            # further in, hence tolerance 1; the return crossing re-walks to
            # the exact edge cell, so it is checked the same way.
            arrival = connection_arrival_cell(map_constant, to=other_map_constant, cell=(x, y))
            assertions.cross_connection(emu, beat_name, (x, y), direction, other_map_constant)
            emu.settle_field()
            assertions.assert_near(emu, beat_name, arrival)
            assertions.cross_connection(
                emu, beat_name, arrival, _OPPOSITE_DIR[direction], map_constant)
            emu.settle_field()
            assertions.assert_near(emu, beat_name, (x, y))
            return
        assertions.cross_arrow_warp(emu, beat_name, (x, y), direction, other_map_constant)
        # Let each arrival settle, as transit hops do: ROM run 72 ended the
        # chapter on the return crossing with the field still locked.
        emu.settle_field()
        reverse_direction = _OPPOSITE_DIR.get(direction, str(params["other_direction"]))
        # Come back over the cell PAIRED with the one crossed (seam_warps.json
        # pairs cells_a[i] with cells_b[i]); index 0 was a wall's arrow on
        # Route 2 (ROM run 71: forward over Kevlar (32,0), back from (20,55)).
        here_cells = seam_cells(map_constant, to=other_map_constant)
        other_cells = seam_cells(other_map_constant, to=map_constant)
        if (x, y) not in here_cells:
            raise ScenarioError(f"{beat_name}: crossed at {(x, y)}, not a seam cell "
                                f"of {row_id} ({here_cells})")
        paired = here_cells.index((x, y))
        assertions.cross_arrow_warp(
            emu, beat_name, other_cells[paired], reverse_direction, map_constant)
        emu.settle_field()

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
    idiom `warp_beat` uses), then lets the arrival settle. A hop whose
    pressed-into cell is an arrow-warp seam cell (seam_warps.json) is held
    on that tile instead: one step only lands on an arrow, it does not fire
    it (ROM run 74, Kevlar (31,1) UP stood on (31,0) forever)."""
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
            dx, dy = assertions._ARROW_APPROACH_DELTA[press]
            tile = (x - dx, y - dy)
            if real_connection(map_constant, dest) is not None:
                # (x, y) is the edge cell itself: hold the press off it.
                assertions.cross_connection(emu, beat_name, (x, y), press, dest)
            elif is_seam_crossing(map_constant, dest, tile):
                assertions.cross_arrow_warp(emu, beat_name, tile, press, dest)
            else:
                assertions.cross_threshold(emu, beat_name, (x, y), press, dest)
            emu.settle_field()

    del body
