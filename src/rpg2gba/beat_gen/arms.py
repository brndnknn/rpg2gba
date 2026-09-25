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


def _descendants(arm: str, rows: Collection[str], parent_of: Callable[[str], str | None]) -> list[str]:
    out = []
    for rid in rows:
        cur = parent_of(rid)
        while cur is not None:
            if cur == arm:
                out.append(rid)
                break
            cur = parent_of(cur)
    return out


def split_choice_arms(
    beats: tuple[PlannedBeat, ...],
    branch_of: Callable[[str], Any],
    parent_of: Callable[[str], str | None],
    killed_by: Callable[[str], Collection[str]],
    choice_openers: Callable[[str], Collection[int]],
) -> tuple[tuple[PlannedBeat, ...], tuple[Elsewhere, ...]]:
    """One beat per choice arm (ruling 19). `branch_of(row_id)` is a
    manifest row's `BranchRef` (None for a page), `parent_of` its enclosing
    arm or page, `killed_by(page_row_id)` the rows whose writes end the
    page, `choice_openers(row_id)` the list indexes of the `choice`
    assertions on a row's floor. Every generic beat also gets
    `choice_answers` for each choice it walks. Returns the new beats and the arms no walk can take."""
    out: list[PlannedBeat] = []
    unselected: list[Elsewhere] = []
    pending = list(beats)
    while pending:
        beat = pending.pop(0)
        if beat.template != "generic":
            out.append(beat)
            continue
        walked = beat.rows + tuple(dict(beat.kwargs).get("walk_rows", ()))
        groups: dict[int, list[str]] = {}
        for rid in beat.rows:
            b = branch_of(rid)
            if b is not None and b.arm_kind in ("choice", "cancel"):
                groups.setdefault(b.opener_index, []).append(rid)
        split = next((op for op, arms in sorted(groups.items()) if len(arms) > 1), None)
        if split is None:
            out.append(beat)
            continue

        arms = sorted(groups[split], key=lambda r: (branch_of(r).choice_index is None,
                                                    branch_of(r).choice_index or 0))
        subtree = {a: [a, *_descendants(a, beat.rows, parent_of)] for a in arms}
        in_arms = {r for rows in subtree.values() for r in rows}
        shared = tuple(r for r in beat.rows if r not in in_arms)
        page = parse_row_id(arms[0]).owning_page_row_id
        killers = set(killed_by(page))
        trunk_kills = bool(killers & set(shared))
        killing = [a for a in arms if trunk_kills or killers & set(subtree[a])]
        repeatable = [a for a in arms if a not in killing]
        last = killing[0] if killing else repeatable.pop()
        for a in killing[1:]:
            for rid in subtree[a]:
                unselected.append(Elsewhere(
                    rid, "unselected_arm",
                    detail=f"choice at list[{split}]: answering {branch_of(a).choice_index} "
                           "ends the page, and another answer is walked instead (ruling 19)"))

        kwargs = dict(beat.kwargs)
        extra_walk = tuple(kwargs.pop("walk_rows", ()))
        for i, a in enumerate(repeatable):
            idx = branch_of(a).choice_index
            pending.insert(i, dataclasses.replace(
                beat, name=f"{beat.name}_c{split}a{'x' if idx is None else idx}",
                rows=tuple(r for r in beat.rows if r in subtree[a]),
                kwargs=make_kwargs(**kwargs, walk_rows=shared + extra_walk)))
        pending.insert(len(repeatable), dataclasses.replace(
            beat, rows=tuple(r for r in beat.rows if r in set(shared) | set(subtree[last])),
            kwargs=make_kwargs(**kwargs, **({"walk_rows": extra_walk} if extra_walk else {}))))
    skip = {e.row_id for e in unselected}
    return (tuple(_with_answers(b, branch_of, choice_openers, skip) for b in out),
            tuple(unselected))


def _with_answers(beat: PlannedBeat, branch_of: Callable[[str], Any],
                  choice_openers: Callable[[str], Collection[int]],
                  unselected: Collection[str]) -> PlannedBeat:
    """Name, for every choice the beat walks, the answer that selects the
    arm it claims. A choice none of whose arms the beat claims is answered
    with its lowest arm that isn't `unselected` (0 if it has no arm rows)."""
    if beat.template != "generic":
        return beat
    walked = beat.rows + tuple(dict(beat.kwargs).get("walk_rows", ()))
    openers = {op for rid in walked for op in choice_openers(rid)}
    if not openers:
        return beat
    answers: dict[int, int] = {}
    fallback: dict[int, int] = {}
    for rid in walked:
        b = branch_of(rid)
        if b is None or b.arm_kind not in ("choice", "cancel"):
            continue
        idx = -1 if b.choice_index is None else b.choice_index
        if rid in beat.rows:
            answers[b.opener_index] = idx
        elif rid not in unselected:
            fallback[b.opener_index] = min(fallback.get(b.opener_index, idx), idx)
    answers = {op: answers.get(op, fallback.get(op, 0)) for op in openers}
    kwargs = dict(beat.kwargs)
    kwargs["choice_answers"] = tuple(sorted((op, answers.get(op, 0)) for op in openers))
    return dataclasses.replace(beat, kwargs=make_kwargs(**kwargs))
