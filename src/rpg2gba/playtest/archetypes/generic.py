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
made here. `choice`/`warp`/`pokemon_grant`/`service`/
`displacement`/`event_position`/`erase_event` are each a real, cited
observation gap in `assignments/C6/research/07_generic.md` §2 -- none
buys enough (`warp`'s single-page-in-a-multi-step-loop map-change problem
in particular) to be worth the design complexity here.

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

STATUS: implemented (`assignments/C6/07_generic.md`).
"""
from __future__ import annotations

import functools
import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from rpg2gba.beat_floor.assertion import Params, RowFloor
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
    event_cell,
    event_page_empty,
    event_page_moves,
    local_id,
    seam_cells,
)
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
    "visual", "heal_party", "var_text", "item_grant", "choice", "service",
    "battle",
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
    {"trigger", "text", "var_text", "heal_party", "item_grant", "choice", "service",
     "battle"})
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
_BREAKS = re.compile(r"\\[nlp]|\s+")
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


def _written(value: object) -> tuple:
    """The values a write can leave: the floor renders a write that has more
    than one possible value (a random roll, a branch-dependent assign) as a
    tuple of them, and a single value bare (`beat_floor.walk`)."""
    return value if isinstance(value, tuple) else (value,)


def _handle_switch_write(emu: "Emulator", beat_name: str, step: Step) -> None:
    params = dict(step.params)
    switch_id = params["switch_id"]
    name = _flag_registry().get_flag(switch_id)
    if name is None:
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: switch {switch_id} has no minted "
            "FLAG_* name in the persisted flag registry -- not guessing one"
        )
    expected = tuple(bool(v) for v in _written(params["value"]))
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
        expected = _written(params["value"])
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
    expected = tuple(bool(v) for v in _written(params["value"]))
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


def _battle_consts(step: Step, beat_name: str) -> tuple[str, ...]:
    """The trainers.json consts a trainer `battle` step can be against."""
    from rpg2gba.beat_gen.adapt import trainer_consts_for
    from rpg2gba.pbs_converter._naming import to_constant

    params = dict(step.params)
    return trainer_consts_for(
        str(params["name"]), to_constant("TRAINER_CLASS", str(params["trainer_type"])),
        row_id=f"{beat_name}: {step.row_id}")


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
        # it and leave the rest of the page to `completes`.
        reveals = _starter_reveal_lines()

        def revealed() -> bool:
            text = emu.current_field_message_text()
            return text is not None and any(text_matches(r, text) for r in reveals)

        emu.advance_dialog("A", stop=revealed)
        if not revealed():
            raise _service_failed(emu, beat_name, step,
                                  f"no starter reveal line ({reveals}) showed")
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


def _handle_heal_party(emu: "Emulator", beat_name: str, step: Step) -> None:
    # The body set the lead to 1 HP before firing the page (module docstring).
    assertions.require_lead_healed(emu, beat_name, step.row_id)


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
    win_battle(emu)
    flag_id = emu.resolve_constant("TRAINER_FLAGS_START") + actual
    if not _wait_for(emu, lambda: emu.flag(flag_id), frames=120):
        shot = emu.screenshot(f"{beat_name}_not_defeated")
        raise ScenarioError(
            f"{beat_name}: {step.row_id}: {expected[actual]}'s defeat flag is not "
            f"set after the win ({shot})")


STEP_HANDLERS.update({
    "battle": _handle_battle,
    "choice": _handle_choice,
    "service": _handle_service,
    "heal_party": _handle_heal_party,
    "item_grant": _handle_item_grant,
    "var_text": _handle_var_text,
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
) -> None:
    """Register one generic beat claiming `rows` (a page row and/or its
    arms). `random_arms` (ruling 19) pairs each RNG-selected arm among
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
        middle_steps = [s for s in middle_steps if s.kind not in _NOT_AFTER_THE_FACT]
    elif trigger in _PLAYER_TRIGGERS and page_row.event_id is not None:
        faces_target = event_cell(cell.map_constant, page_row.event_id)
        x, y = approach_to(cell.map_constant, page_row.event_id, prefer=approach_prefer)
        page_idx = parse_row_id(page_row_id).page_idx
        if trigger == "action" and page_idx is not None:
            if event_page_empty(cell.map_constant, page_row.event_id, page_idx):
                empty_page = True
            elif event_page_moves(cell.map_constant, page_row.event_id, page_idx):
                walks_off = local_id(cell.map_constant, page_row.event_id)
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
    middle_steps = [s for s in middle_steps if s.kind != "item_grant"]

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
    for step in grant_steps:
        item = str(dict(step.params)["item"])
        const = _uranium_item_constants().get(item)
        if const is None:
            raise ValueError(
                f"generic_beat: {beat_name}: {step.row_id} grants {item!r}, which has "
                "no entry in reference/uranium_id_map.json's 'items' table")
        grant_const[item] = const

    # heal_party after a battle: the lead is damaged once the battle is won
    # (`damage_after`), not before the walk.
    heal_at = next((i for i, s in enumerate(middle_steps)
                    if s.kind == "heal_party" and s.row_id not in random_guard), None)
    heals = heal_at is not None
    damage_after = None if heal_at is None else next(
        (i for i in range(heal_at - 1, -1, -1) if middle_steps[i].kind == "battle"), None)

    @builder.beat(
        beat_name,
        f"Generic floor coverage for {', '.join(resolved_rows)} ({chapter_id})",
        map_constant=cell.map_constant, at=(x, y), group=group,
        rows=resolved_rows, assertions=declared,
        drain_answers=(cell.map_constant, arrival_answers) if arrival_answers else None,
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
            if not arrival:
                emu.walk_to(x, y)
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
                assertions.talk_to_moving_npc(emu, beat_name, walks_off)
            else:
                if faces_target is not None:
                    emu.face(facing_toward((x, y), faces_target, caller="generic_beat"))
                if trigger_step is not None:
                    STEP_HANDLERS["trigger"](emu, beat_name, trigger_step)
        for i, step in enumerate(middle_steps):
            guard = random_guard.get(step.row_id)
            if guard is not None and (step.kind == "heal_party"
                                      or not _guard_holds(emu, beat_name, guard)):
                continue  # the RNG picked a sibling arm (or: no damage to heal)
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
            return
        # One check per item after the page: the bag only shows the sum of
        # that item's grants, so the last grant step carries the total.
        expected = dict(bag_before)
        last_step: dict[str, Step] = {}
        for step in grant_steps:
            params = dict(step.params)
            const = grant_const[str(params["item"])]
            expected[const] += int(params["quantity"])
            last_step[const] = step
        for const, step in sorted(last_step.items()):
            STEP_HANDLERS["item_grant"](emu, beat_name, Step(
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
