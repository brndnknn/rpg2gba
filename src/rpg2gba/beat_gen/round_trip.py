"""Choice round trips (REDERIVATION_PLAN.md §16.3 ruling 19, operator ruling
2026-09-29).

A page's Show Choices can have two arms that both end the page. Ruling 19's
splitter walks one (`arms.split_choice_arms`) and sends the other to
`unselected_arm`. But arm X's writes can make another page Q of the same event
live, and Q's own choice can answer its way back: Q's arm writes make the
original page P live again, and P, an autorun, re-fires at once into the
sibling arm Y (the professor lab's "No" -> re-offer -> "Yes" -> quiz). The
hand suite walked that trip; this module derives it, never by matching an
event:

1. fire P answering X (`page_sim.run_page`, from the chapter's seed state);
2. the event's live page after X's writes is a page Q other than P;
3. some trunk-level choice arm A of Q, fired answering A, leaves P the live
   page again;
4. P's re-fire takes an arm that enters Y: Y itself, or a jump to a label that
   sits inside Y (`page_sim` cannot follow the jump, so the target is read off
   the page's scopes).

When all four hold the plan walks X, then Q answering A (one beat: Q's rows,
then Y's rows, all in one interaction because the autorun re-fires before the
field is released), and Y's rows are claimed by that re-fire.
"""
from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable, Collection, Mapping
from typing import Any

from rpg2gba.beat_gen.page_sim import Firing, PageRun, run_page
from rpg2gba.beat_gen.state_arms import _page_result
from rpg2gba.chapter_manifest.generator import PageScope, iter_page_scopes
from rpg2gba.chapter_manifest.schema import parse_row_id
from rpg2gba.conversion_agent.transpiler import JUMP_TO_LABEL, LABEL, Leaf
from rpg2gba.story_state.extract import RowState
from rpg2gba.story_state.state import Key

logger = logging.getLogger(__name__)

_ARRIVAL = frozenset({"autorun", "parallel"})


@dataclasses.dataclass(frozen=True)
class RoundTrip:
    """The trip `find_round_trip` derived: `page` fires answering `killed`
    (arm X), which makes `via` live; `via` answers `via_arm`, which re-fires
    `page` into `into` (arm Y, the arm the plan used to walk)."""

    page: str
    killed: str
    via: str
    via_arm: str
    into: str

    def describe(self) -> str:
        return (f"{self.page}/{self.killed.rsplit('/', 1)[-1]} -> {self.via} answering "
                f"{self.via_arm.rsplit('/', 1)[-1]} -> {self.page} re-fires into "
                f"{self.into.rsplit('/', 1)[-1]}")


def _live_page(page: str, states: Mapping[str, RowState], state: Mapping) -> str | None:
    """The event's highest page whose conditions certainly hold, when no
    higher page is undecided; None when the state doesn't pin it down."""
    for p in reversed(states[page].event_page_row_ids):
        result = _page_result(p, states, state)
        if result is True:
            return p
        if result is None:
            return None
    return None


def _own_leaves(scope: PageScope, code: int) -> list[str]:
    return [str((n.cmd.get("parameters") or [""])[0]) for n in scope.nodes
            if isinstance(n, Leaf) and n.cmd.get("code") == code]


def enters(run: PageRun, page_row_id: str, page: Mapping[str, Any], target: str) -> bool:
    """Does the firing `run` enter arm `target` (or an arm nested in it):
    `target` taken outright, or a taken arm jumps to a label that sits in
    `target`'s own commands or a nested arm's."""
    parsed = parse_row_id(page_row_id)
    scopes = iter_page_scopes(parsed.map_id, {"id": parsed.event_id}, parsed.page_idx, page)
    parent = {s.row_id: s.parent_row_id for s in scopes}

    def inside(rid: str | None) -> bool:
        while rid is not None:
            if rid == target:
                return True
            rid = parent.get(rid)
        return False

    if target in run.taken or any(inside(r) for r in run.taken):
        return True
    labels = {label for s in scopes if inside(s.row_id) for label in _own_leaves(s, LABEL)}
    return any(label in labels for s in scopes if s.row_id in run.taken
               for label in _own_leaves(s, JUMP_TO_LABEL))


def find_round_trip(
    page: str, killed: str, walked: str, *,
    seed: Mapping[Key, frozenset],
    row_states: Callable[[int], Mapping[str, RowState]],
    page_for: Callable[[str], Mapping[str, Any]],
    branch_of: Callable[[str], Any],
    arms_of: Callable[[str], Collection[str]],
    claimed: Collection[str],
    event_cell: Callable[[str], tuple[int, int] | None] = lambda _p: None,
) -> RoundTrip | None:
    """The round trip from arm `killed` of `page`'s choice back into arm
    `walked` (module docstring), or None. `arms_of(page)` lists a page's
    manifest arm rows; `claimed` is every row some beat claims (a trip through
    a page nobody claims can't be walked). Fires from `seed` with no known
    cell, so a test on the player's position is undecided, never assumed."""
    states = row_states(parse_row_id(page).map_id)
    if states[page].trigger not in _ARRIVAL:
        return None      # only an autorun re-fires into the sibling arm by itself

    def fire(p: str, state: Mapping, answers: Mapping[int, int]) -> PageRun:
        return run_page(p, page_for(p), states, state,
                        Firing(cell=None, event_cell=event_cell(p), choice_answers=answers))

    bx = branch_of(killed)
    if bx is None or bx.opener_index is None:
        return None
    run_x = fire(page, seed, {bx.opener_index: -1 if bx.choice_index is None else bx.choice_index})
    if killed not in run_x.taken:
        return None
    via = _live_page(page, states, run_x.state)
    if via is None or via == page:
        return None
    for arm in sorted(arms_of(via), key=lambda a: (branch_of(a).choice_index is None,
                                                   branch_of(a).choice_index or 0)):
        b = branch_of(arm)
        if b is None or b.arm_kind not in ("choice", "cancel") \
                or states[arm].parent_row_id != via or arm not in claimed:
            continue
        run_q = fire(via, run_x.state, {b.opener_index: -1 if b.choice_index is None
                                        else b.choice_index})
        if arm not in run_q.taken or _live_page(page, states, run_q.state) != page:
            continue
        run_p = fire(page, run_q.state, {})
        if enters(run_p, page, page_for(page), walked):
            trip = RoundTrip(page, killed, via, arm, walked)
            logger.info("round trip: %s", trip.describe())
            return trip
    return None
