"""State- and position-selected branch arms (REDERIVATION_PLAN.md §16.3
ruling 19, steps 4-5).

A generic beat claims arms of its page, but a walk fires the page once from
one cell with the story state the route has built up by then, and takes one
arm of every then/else. This stage runs after the route is ordered, when
both are known. Starting from the chapter's seed state (its predecessor's
end state) it fires, in walk order, the page of every beat that fires one,
through `page_sim.run_page`, and for each generic or escort beat:

- an arm the firing certainly takes stays claimed;
- an arm it certainly skips is re-fired for: when firing the page again from
  the state the first firing left takes it (an NPC whose page flips its own
  self switch, `map064/ev001/p0`), a beat `<name>_r<n>` in the same group
  claims it, walking the rest of that firing unclaimed (`walk_rows`) --
  never for an escort, which fires once and doesn't come back (ruling 11);
- an arm no firing takes goes to `elsewhere` as `unselected_arm`, with what
  selected its sibling (the state, or the cell the page fired from);
- an arm the simulation can't decide stays claimed, as before.

The walk's state is an approximation. Pages the walk never fires can still
run on the ROM (a refused autorun, a parallel page), so every write of such a
page is folded in as a possibility after each firing (`taint`), and a test on
what it writes is left undecided. A wrong decision here is still caught: the
beat declares the arm's assertions and the P11 walk checks them.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Callable, Collection, Mapping, Sequence
from typing import Any

from rpg2gba.beat_gen.page_sim import Firing, PageRun, run_page
from rpg2gba.beat_gen.plan import Elsewhere, PlannedBeat, make_kwargs
from rpg2gba.chapter_manifest.generator import iter_page_scopes
from rpg2gba.chapter_manifest.schema import parse_row_id
from rpg2gba.story_state.extract import RowState
from rpg2gba.story_state.model import VARIABLE_TOP, _get, _union_values
from rpg2gba.story_state.state import (
    Adjust,
    Assign,
    EngineKey,
    Key,
    SelfSwitch,
    Switch,
    TempSwitch,
    Variable,
)

#: Templates whose beat fires its rows' pages. The rest walk terrain,
#: travel, or stand in front of an obstacle without firing it.
FIRING_TEMPLATES: frozenset[str] = frozenset(
    {"generic", "warp", "arrival_nudge", "item_ball", "trainer", "flavour_npc", "escort"})
#: Templates whose claimed arms this stage settles. An escort fires once and
#: never comes back (ruling 11), so it is never re-fired.
_ARM_TEMPLATES = frozenset({"generic", "escort"})

_ARRIVAL = frozenset({"autorun", "parallel"})
_FACING_NAMES = {2: "down", 4: "left", 6: "right", 8: "up"}
_REFIRES = 3

Taint = Assign | Adjust | Key


def apply_taint(state: dict, taint: Collection[Taint]) -> dict:
    """`state` with every write in `taint` folded in as a possibility: an
    `Assign` adds its values, an `Adjust` or a bare key (havoc) makes the key
    anything. Returns a new dict."""
    out = dict(state)
    for t in taint:
        key = t.key if isinstance(t, (Assign, Adjust)) else t
        if isinstance(key, TempSwitch):
            continue
        if isinstance(t, Assign):
            out[key] = _union_values(_get(out, key), t.values)
        elif isinstance(key, (Variable, EngineKey)):
            out[key] = frozenset({VARIABLE_TOP})
        else:
            out[key] = frozenset({False, True})
    return out


def fired_pages(beat: PlannedBeat) -> list[str]:
    walked = beat.rows + tuple(dict(beat.kwargs).get("walk_rows", ()))
    out: list[str] = []
    for rid in walked:
        page = parse_row_id(rid).owning_page_row_id or rid
        if page not in out:
            out.append(page)
    return out


def _why(arm: str, states: Mapping[str, RowState], page: Mapping[str, Any],
         state: Mapping, firing: Firing) -> str:
    guard = states[arm].arm_guard
    if guard is None or guard.opener_index is None:
        return "its enclosing arm doesn't run"
    if guard.tests:
        held = "; ".join(
            f"{_key(t.key)} is {sorted(_get(state, t.key), key=repr)}" for t in guard.tests)
        want = " and ".join(f"{_key(t.key)} {t.op} {t.value}" for t in guard.tests)
        return f"needs {want}, and here {held}"
    params = page["list"][guard.opener_index]["parameters"]
    kind = guard.outcome.kind if guard.outcome is not None else "?"
    if kind == "input" and params and params[0] == 12:
        side = "else of " if guard.negated else ""
        return f"{side}`{params[1]}` from cell {firing.cell} (event at {firing.event_cell})"
    if kind == "input" and params and params[0] == 6 and params[1] == -1:
        parsed = parse_row_id(arm)
        scope = next(s for s in iter_page_scopes(
            parsed.map_id, {"id": parsed.event_id}, parsed.page_idx, page) if s.row_id == arm)
        side = "else of " if scope.branch.arm_kind == "else" else ""
        facing = _FACING_NAMES.get(params[2], params[2])
        return (f"{side}the player facing {facing}, fired from cell {firing.cell} "
                f"(event at {firing.event_cell})")
    detail = f":{guard.outcome.detail}" if guard.outcome is not None and guard.outcome.detail else ""
    return f"its guard is `{kind}{detail}`, which the walk doesn't take"


def _key(key: Key) -> str:
    if isinstance(key, Variable):
        return f"var {key.id}"
    if isinstance(key, Switch):
        return f"switch {key.id}"
    if isinstance(key, SelfSwitch):
        return f"self switch {key.letter}"
    return repr(key)


def select_state_arms(
    beats: Sequence[PlannedBeat],
    seed: Mapping[Key, frozenset],
    *,
    row_states: Callable[[int], Mapping[str, RowState]],
    page_for: Callable[[str], Mapping[str, Any]],
    firing_for: Callable[[PlannedBeat, str], Firing],
    taint: Collection[Taint] = (),
    walkable: Callable[[str], bool] = lambda _rid: True,
    choice_openers: Callable[[str], Collection[int]] = lambda _rid: (),
) -> tuple[tuple[PlannedBeat, ...], tuple[Elsewhere, ...]]:
    """(the beats with state/position-selected arms settled, the arms no
    walk takes). `beats` are in walk order. `firing_for(beat, page_row_id)`
    is where and how the beat fires that page; `walkable(row_id)` is False
    for a row whose floor is refused (a re-fire can't walk it);
    `choice_openers(row_id)` the list indexes of a row's choice commands (a
    re-fire must answer each). Module docstring for the rest."""
    state = apply_taint(dict(seed), taint)
    arrival_runs: dict[tuple[str, str], PageRun] = {}
    out: list[PlannedBeat] = []
    elsewhere: list[Elsewhere] = []

    for beat in beats:
        if beat.template not in FIRING_TEMPLATES:
            out.append(beat)
            continue
        random = {r for r, _ in dict(beat.kwargs).get("random_arms", ())}
        dropped: set[str] = set()
        refires: list[PlannedBeat] = []
        for page_id in fired_pages(beat):
            states = row_states(parse_row_id(page_id).map_id)
            page = page_for(page_id)
            firing = firing_for(beat, page_id)
            arrival = states[page_id].trigger in _ARRIVAL
            before = state
            if arrival and (beat.group, page_id) in arrival_runs:
                # An arrival page fired once, on the crossing into the map;
                # the group's other beats observe that same firing.
                run = arrival_runs[(beat.group, page_id)]
            else:
                run = run_page(page_id, page, states, state, firing)
                state = apply_taint(run.state, taint)
                if arrival:
                    arrival_runs[(beat.group, page_id)] = run
            if beat.template not in _ARM_TEMPLATES:
                continue

            claimed = [r for r in beat.rows if r != page_id and r not in random
                       and parse_row_id(r).owning_page_row_id == page_id]
            skipped = [r for r in claimed if r in run.not_taken]
            if not skipped:
                continue
            dropped.update(skipped)
            reasons = {
                r: (f"it sits inside {states[r].parent_row_id}, which the walk doesn't take"
                    if states[r].parent_row_id in run.not_taken
                    else _why(r, states, page, before, firing))
                for r in skipped}
            remaining = list(skipped)
            answers = dict(dict(beat.kwargs).get("choice_answers", ()))
            for n in range(1, _REFIRES + 1):
                if arrival or not remaining or beat.template == "escort":
                    break
                again = run_page(page_id, page, states, state, firing)
                got = [r for r in remaining if r in again.taken]
                walk = (page_id, *sorted(r for r in again.taken if r not in got))
                if not got or not all(walkable(r) for r in (*got, *walk)) or any(
                        op not in answers for r in (*got, *walk) for op in choice_openers(r)):
                    break
                kwargs = {k: v for k, v in beat.kwargs if k not in ("walk_rows", "random_arms")}
                refires.append(dataclasses.replace(
                    beat, name=f"{beat.name}_r{n}", rows=tuple(r for r in beat.rows if r in got),
                    kwargs=make_kwargs(**kwargs, walk_rows=walk)))
                state = apply_taint(again.state, taint)
                remaining = [r for r in remaining if r not in got]
            for rid in remaining:
                elsewhere.append(Elsewhere(
                    rid, "unselected_arm",
                    detail=f"not taken on the walk: {reasons[rid]} (ruling 19)"))

        if dropped:
            kept = tuple(r for r in beat.rows if r not in dropped)
            if kept:
                out.append(dataclasses.replace(beat, rows=kept))
        else:
            out.append(beat)
        out.extend(refires)
    return tuple(out), tuple(elsewhere)
