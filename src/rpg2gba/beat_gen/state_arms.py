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

Page liveness (ROM run 20, 2026-09-29). The same walk decides, the first time
it fires a claimed page, whether that page is its event's highest live page at
that point, from the state the claimed writers built (never the story model's
`enabled_by`). Pages of one beat are judged in the beat's own firing order, so
a template that fires p0 and then p1 (a trainer's re-talk, an item ball's
negative check) applies p0's writes before judging p1. A page a definite state
rules out -- one of its conditions certainly fails, or a higher page's
conditions certainly hold -- is one of three kinds:

- `never`: no claimed writer makes it live at any earlier position (its
  enabler is unclaimed or refused). Demoted: its claimed rows become
  `never_fires` entries whose detail names the page, the failing condition,
  the live page and the missing enabler, and its writes never enter the state.
- `killer_first`: it was (or, in an undecided state, may have been) live earlier in the walk, and a write that lifted a
  higher page came first. Kept, and reported as a `LivenessProblem`.
- `enabler_later`: a beat later on the route claims the write that would make
  it live. Kept, and reported.

The last two are solver work (killer edges; `Adjust` writers that never reach a
`>=` threshold), not this stage's to fix. A state the walk can't pin down (a
tainted key, a refused page condition) keeps the beat and logs it. One pass in
walk order is the fixpoint: a demotion only affects beats after it.
"""
from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable, Collection, Mapping, Sequence
from typing import Any

from rpg2gba.beat_gen.page_sim import Firing, PageRun, run_page
from rpg2gba.beat_gen.plan import Elsewhere, LivenessProblem, PlannedBeat, make_kwargs
from rpg2gba.chapter_manifest.generator import iter_page_scopes
from rpg2gba.chapter_manifest.schema import parse_row_id
from rpg2gba.story_state.extract import RowState
from rpg2gba.story_state.model import VARIABLE_TOP, _cmp, _get, _union_values
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

logger = logging.getLogger(__name__)


# Verdict kinds that drop the page's rows from the walk -> their Elsewhere status.
_DEAD = {"never": "never_fires", "arm_gated": "arm_gated", "self_ended": "unselected_arm"}


@dataclasses.dataclass(frozen=True)
class _Verdict:
    kind: str        # "never"/"arm_gated"/"self_ended" (bucket a), "killer_first" (b), "enabler_later" (c)
    detail: str


def _test_result(test: Any, state: Mapping) -> bool | None:
    """True/False when every value the key can hold agrees on `test`; None
    when the state doesn't pin it down (a mix, or the havoc'd top)."""
    values = _get(state, test.key)
    if VARIABLE_TOP in values:
        return None
    results = {_cmp(test.op, v, test.value) for v in values}
    return results.pop() if len(results) == 1 else None


def _page_result(page: str, states: Mapping[str, RowState], state: Mapping) -> bool | None:
    """Do all of `page`'s conditions hold in `state`: True, False, or None
    (undecided, including a condition the story model refused)."""
    rs = states[page]
    if rs.page_refusals:
        return None
    results = [_test_result(t, state) for t in rs.page_tests]
    if any(r is False for r in results):
        return False
    return None if any(r is None for r in results) else True


def _tests_text(page: str, states: Mapping[str, RowState]) -> str:
    tests = states[page].page_tests
    return " and ".join(f"{_key(t.key)} {t.op} {t.value}" for t in tests) or "no condition"


def _claimed_pages(beat: PlannedBeat) -> list[str]:
    out: list[str] = []
    for rid in beat.rows:
        parsed = parse_row_id(rid)
        page = parsed.owning_page_row_id or rid
        if parse_row_id(page).kind != "page":
            raise ValueError(f"{beat.name}: row {rid!r} of a firing beat sits on no page")
        if page not in out:
            out.append(page)
    return out


def _holds_test(t: Any, values: Collection) -> bool:
    return any(_cmp(t.op, v, t.value) for v in values)


def _dead_verdict(page: str, states: Mapping[str, RowState], state: Mapping,
                  writers: Mapping[Key, tuple[str, str, int]], history: Sequence[Mapping],
                  later: Sequence[tuple[str, str, int]],
                  fired_pages: Collection[str] = ()) -> _Verdict | None:
    """None when `page` isn't provably dead in `state` (module docstring);
    otherwise how: `enabler_later` when a later beat's claimed `Assign` row
    would satisfy a failing condition; `killer_first` when the page was live
    in an earlier state of the walk (`history`); `arm_gated` when a row that
    would enable it is an unwalked arm of a page the route fires (in
    `fired_pages`) -- reachable on the ROM by answering the other way; else
    `never` -- no claimed writer makes it live. `later` is (row id, beat
    name, beat index)."""
    own = states[page]
    pages = own.event_page_row_ids
    result = _page_result(page, states, state)
    higher = list(pages[pages.index(page) + 1:])
    winner = next((p for p in reversed(higher) if _page_result(p, states, state) is True), None)
    failing = [t for t in own.page_tests if _test_result(t, state) is False]
    if result is False and failing:
        pass
    elif winner is not None:
        failing = []
    else:
        if result is not True or any(_page_result(p, states, state) is None for p in higher):
            logger.info("liveness: %s indeterminate at its route position, kept", page)
        return None
    live = winner
    if live is None:
        live = next((p for p in reversed(pages[:pages.index(page)])
                     if _page_result(p, states, state) is True), None)
    enabler: tuple[str, str, int] | None = None
    self_ended = bool(failing)
    gating_arms: list[str] = []
    reasons = []
    for t in failing:
        enabler = enabler or next(
            ((rid, name, idx) for rid, name, idx in later
             if any(isinstance(w, Assign) and w.key == t.key and _holds_test(t, w.values)
                    for w in states[rid].writes)), None)
        killer = writers.get(t.key)
        self_ended &= killer is not None and killer[0] == page
        unclaimed = sorted(
            rid for rid, rs in states.items() if rs is not own and any(
                isinstance(w, Assign) and w.key == t.key and _holds_test(t, w.values)
                for w in rs.writes))
        gating_arms.extend(
            rid for rid in unclaimed
            if (parse_row_id(rid).owning_page_row_id or rid) != rid
            and parse_row_id(rid).owning_page_row_id in fired_pages)
        now = sorted(_get(state, t.key), key=repr)
        why = (f"{_key(t.key)} was set to {now} by {killer[0]} (beat {killer[1]}, #{killer[2]})"
               if killer else f"{_key(t.key)} is {now} (seed state), never written on the route")
        reasons.append(f"{_key(t.key)} {t.op} {t.value} fails: {why}; the rows that could "
                       f"write it {unclaimed or 'none'} are not walked before it")
    if not failing:
        cause = f"the higher page {winner} (needs {_tests_text(winner, states)}) holds"
    else:
        cause = "; ".join(reasons)
    live_text = (f"{live} (needs {_tests_text(live, states)})" if live is not None
                 else "no page is certainly live")
    detail = (f"{page} (needs {_tests_text(page, states)}) is not its event's live page at this "
              f"route position: {cause}; live page: {live_text}")
    if enabler is not None:
        return _Verdict("enabler_later", f"{detail}; row {enabler[0]} of beat {enabler[1]} "
                                         f"(#{enabler[2]}), later on the route, would enable it")
    if self_ended:
        # Its own firing cleared the condition (an arm that ends the page) and
        # no claimed writer restores it: a later walk of the page's other arms
        # would find it dead, and the walk that took the ending arm can't also
        # take the rest of that firing's arms (the round-trip beat's facing
        # arms, `beat_gen/round_trip.py`).
        return _Verdict("self_ended", f"{detail}; the page ended itself at an earlier firing "
                                      "and no claimed row brings it back, so the walk that "
                                      "took its ending arm doesn't return to it")
    # Conservative: an earlier state where liveness is True OR undecided
    # keeps the page (an indeterminate earlier state is never proof of `never`).
    was_live = next((i for i, h in enumerate(history)
                     if _page_result(page, states, h) is not False
                     and not any(_page_result(p, states, h) is True for p in higher)), None)
    if was_live is not None:
        certain_ = _page_result(page, states, history[was_live]) is True
        return _Verdict("killer_first", f"{detail}; it was {'live' if certain_ else 'possibly live'} "
                                        f"at route position {was_live} (before that beat's write)")
    if gating_arms:
        return _Verdict("arm_gated", f"{detail}; reachable on the ROM through the unwalked "
                                     f"arm(s) {sorted(set(gating_arms))} of a page the route fires")
    return _Verdict("never", detail)


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
    order_problems: list[LivenessProblem] | None = None,
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
    writers: dict[Key, tuple[str, str, int]] = {}
    decided: dict[str, _Verdict | None] = {}
    history: list[Mapping] = [state]
    problems: list[LivenessProblem] = []
    # Every page some firing beat claims: an unwalked arm of one of these is
    # a path the ROM offers that this route answers the other way.
    route_pages = frozenset(page for b in beats if b.template in FIRING_TEMPLATES
                            for page in _claimed_pages(b))

    for at, beat in enumerate(beats):
        if beat.template not in FIRING_TEMPLATES:
            out.append(beat)
            history.append(state)
            continue
        claimed_pages = _claimed_pages(beat)
        gone: dict[str, tuple[str, str]] = {}   # page -> (Elsewhere status, detail)
        random = {r for r, _ in dict(beat.kwargs).get("random_arms", ())}
        dropped: set[str] = set()
        refires: list[PlannedBeat] = []
        for page_id in fired_pages(beat):
            states = row_states(parse_row_id(page_id).map_id)
            page = page_for(page_id)
            firing = firing_for(beat, page_id)
            arrival = states[page_id].trigger in _ARRIVAL
            before = state
            if page_id in claimed_pages:
                # Liveness, at the walk's first firing of the page and in the
                # beat's own firing order (a template that fires p0 then p1
                # applies p0's writes before p1 is judged); a later firing
                # is a re-fire the arm model below owns.
                seen_before = page_id in decided
                if not seen_before:
                    later = [(r, b.name, i) for i, b in enumerate(beats[at + 1:], at + 1)
                             if b.template in FIRING_TEMPLATES for r in b.rows
                             if parse_row_id(r).map_id == parse_row_id(page_id).map_id
                             and r in states and (parse_row_id(r).owning_page_row_id or r) != page_id]
                    verdict = _dead_verdict(page_id, states, state, writers, history, later,
                                            fired_pages=route_pages)
                    decided[page_id] = verdict
                    if verdict is not None and verdict.kind not in _DEAD:
                        problems.append(LivenessProblem(
                            beat.name, page_id, verdict.kind, verdict.detail, at))
                        logger.warning("liveness order problem (%s) in %s: %s",
                                       verdict.kind, beat.name, verdict.detail)
                verdict = decided[page_id]
                if seen_before and (verdict is None or verdict.kind not in _DEAD):
                    # A later firing (another group of the same page: choice
                    # or facing arms) is judged only for the page having ended
                    # itself; every other order question is the solver's.
                    again = _dead_verdict(page_id, states, state, writers, history, [],
                                          fired_pages=route_pages)
                    verdict = again if again is not None and again.kind == "self_ended" else verdict
                if verdict is not None and verdict.kind in _DEAD:
                    gone[page_id] = (_DEAD[verdict.kind], verdict.detail)
                    continue
            if arrival and (beat.group, page_id) in arrival_runs:
                # An arrival page fired once, on the crossing into the map;
                # the group's other beats observe that same firing.
                run = arrival_runs[(beat.group, page_id)]
            else:
                run = run_page(page_id, page, states, state, firing)
                state = apply_taint(run.state, taint)
                for k, v in run.state.items():
                    if before.get(k, _get(before, k)) != v:
                        writers[k] = (page_id, beat.name, at)
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

        for rid in beat.rows:
            if (parse_row_id(rid).owning_page_row_id or rid) in gone:
                status, why = gone[parse_row_id(rid).owning_page_row_id or rid]
                elsewhere.append(Elsewhere(rid, status, detail=why))
        if dropped or gone:
            kept = tuple(r for r in beat.rows if r not in dropped
                         and (parse_row_id(r).owning_page_row_id or r) not in gone)
            if kept:
                out.append(dataclasses.replace(beat, rows=kept))
        else:
            out.append(beat)
        out.extend(refires)
        history.append(state)
    if order_problems is not None:
        order_problems.extend(problems)
    return tuple(out), tuple(elsewhere)
