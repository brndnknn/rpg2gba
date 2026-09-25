"""Mutually exclusive branch arms (REDERIVATION_PLAN.md §16.3 ruling 19).

One walk through a page takes one arm of each branch point, so a beat that
claims two exclusive arms declares assertions it can't all execute. This
stage runs between selection and grouping and decides, per arm, whether the
walk takes it, by what selects the arm:

- **blocked arms** (`blocked_arms`): the story model marks the arm
  `harness:` (a setup no walk makes, e.g. a full bag), `fork:` (a loss that
  whites out) or `capability:`. The walk takes its sibling; the arm and
  everything nested in it go to `elsewhere` as `unselected_arm`.
- **random arms** (`random_arm_guards`): the arm's guard, or an enclosing
  arm's, tests a variable its own page just wrote with a random operand
  (`122` operand type 2 -- Auntie's var-102 chatter). No walk picks the RNG,
  so the beat declares only the trunk; the body reads the variable back from
  the ROM and checks whichever arm fired (`generic_beat(random_arms=)`).
"""
from __future__ import annotations

import dataclasses
from collections.abc import Callable, Collection, Mapping
from typing import Any

from rpg2gba.beat_gen.plan import Elsewhere, PlannedBeat, Selection, make_kwargs
from rpg2gba.chapter_manifest.schema import parse_row_id
from rpg2gba.story_state.extract import RowState
from rpg2gba.story_state.model import RowVerdict
from rpg2gba.story_state.state import Variable

_CONTROL_VARIABLES = 122
_OPERAND_RANDOM = 2

#: One arm's guard as `generic_beat` evaluates it on the ROM: every
#: `(var_id, op, value)` on the path from the page to this arm.
RandomGuard = tuple[tuple[int, str, int], ...]


def _random_vars(page: Mapping[str, Any]) -> set[int]:
    """Variables a page writes with a random operand
    (`122 [start, end, op, 2, min, max]`)."""
    out: set[int] = set()
    for cmd in page.get("list") or []:
        params = cmd.get("parameters") or []
        if cmd.get("code") == _CONTROL_VARIABLES and len(params) >= 4 \
                and params[3] == _OPERAND_RANDOM:
            out.update(range(params[0], params[1] + 1))
    return out


def random_arm_guards(
    arm_ids: Collection[str],
    row_states: Mapping[str, RowState],
    page_for: Callable[[str], Mapping[str, Any]],
) -> dict[str, RandomGuard]:
    """The random arms among `arm_ids`, each with its full guard path.
    `page_for(page_row_id)` returns that page's raw RMXP page dict. An arm
    whose path mixes a random test with anything that isn't a plain variable
    test is left out (it isn't purely RNG-selected)."""
    out: dict[str, RandomGuard] = {}
    for arm_id in sorted(arm_ids):
        page_id = parse_row_id(arm_id).owning_page_row_id
        rand = _random_vars(page_for(page_id))
        if not rand:
            continue
        path: list[tuple[int, str, int]] = []
        pure, random_hit = True, False
        rid: str | None = arm_id
        while pure and rid is not None and rid != page_id:
            state = row_states[rid]
            guard = state.arm_guard
            if guard is None or not guard.tests \
                    or not all(isinstance(t.key, Variable) for t in guard.tests):
                pure = False
                break
            for t in guard.tests:
                path.append((t.key.id, t.op, int(t.value)))
                random_hit |= t.key.id in rand
            rid = state.parent_row_id
        if pure and random_hit:
            out[arm_id] = tuple(reversed(path))
    return out

_BLOCKING = ("harness", "fork", "capability")


def blocked_arms(
    selection: Selection, verdicts: Mapping[str, RowVerdict], fork_owned: Collection[str],
) -> Selection:
    """Move every owned branch arm whose story verdict carries a blocking
    `harness:`/`fork:`/`capability:` blocker to `elsewhere`. `fork_owned`
    rows (a white-out fork's landing pages) are left alone: they get their
    own beat (`beat_gen/whiteout.py`)."""
    owned = []
    moved = []
    for row in selection.owned:
        verdict = verdicts.get(row.row_id)
        blockers = [] if verdict is None else [
            b for b in verdict.blockers if b.split(":", 1)[0] in _BLOCKING]
        if row.kind == "branch" and blockers and row.row_id not in fork_owned:
            moved.append(Elsewhere(
                row.row_id, "unselected_arm",
                detail=f"blocked by {blockers[0]}; the walk takes the sibling arm (ruling 19)"))
        else:
            owned.append(row)
    return Selection(owned=tuple(owned), refusals=selection.refusals,
                     elsewhere=selection.elsewhere + tuple(moved))


def annotate_random_arms(
    beats: tuple[PlannedBeat, ...],
    row_states: Callable[[int], Mapping[str, RowState]],
    page_for: Callable[[str], Mapping[str, Any]],
) -> tuple[PlannedBeat, ...]:
    """Give each generic beat claiming random arms a `random_arms` kwarg
    (`generic_beat(random_arms=)`). `row_states(map_id)` returns that map's
    extracted row states."""
    out = []
    for beat in beats:
        arms = [r for r in beat.rows if parse_row_id(r).kind == "branch"]
        if beat.template != "generic" or not arms:
            out.append(beat)
            continue
        guards = random_arm_guards(arms, row_states(beat.map_id), page_for)
        if not guards:
            out.append(beat)
            continue
        kwargs = dict(beat.kwargs)
        kwargs["random_arms"] = tuple(sorted(guards.items()))
        out.append(dataclasses.replace(beat, kwargs=make_kwargs(**kwargs)))
    return tuple(out)


def walk_checked(beats: tuple[PlannedBeat, ...]) -> dict[str, str]:
    """Row id -> reason for every arm a beat claims but, by ruling 19,
    doesn't declare: the generated module's `WALK_CHECKED`."""
    out: dict[str, str] = {}
    for beat in beats:
        for row_id, guard in dict(beat.kwargs).get("random_arms", ()):
            tests = " and ".join(f"var {v} {op} {x}" for v, op, x in guard)
            out[row_id] = f"random arm ({tests}); the walk checks whichever the RNG picks"
    return out
