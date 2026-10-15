"""The ⊇-floor relation (REDERIVATION_PLAN.md §16.3 C5, R11).

A beat's declared assertions cover a row's floor when every floor assertion
has a declared assertion with the same key -- `(row_id, kind, list_index,
code)` -- whose params include the floor's params with equal values. A
declared assertion may carry *extra* params (a warp's arrival facing, a BGM
id): that is how an archetype adds a stronger oracle on top of the floor
without a second vocabulary. Extra declared assertions with no floor key are
allowed and ignored here.

Pure functions over `FloorAssertion`; the checker and the templates both call
them, so "covered" has exactly one definition.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Any

from .assertion import FloorAssertion, RowFloor

AssertionKey = tuple[str, str, int, int | None]


def assertion_key(a: FloorAssertion) -> AssertionKey:
    return (a.row_id, a.kind, a.list_index, a.code)


def covers(declared: FloorAssertion, floor: FloorAssertion) -> bool:
    """True iff `declared` is at least as strong as `floor`."""
    if assertion_key(declared) != assertion_key(floor):
        return False
    declared_params = dict(declared.params)
    return all(
        name in declared_params and declared_params[name] == value
        for name, value in floor.params)


def uncovered(
    floor: RowFloor, declared: Iterable[FloorAssertion],
) -> tuple[FloorAssertion, ...]:
    """Floor assertions of `floor` no declared assertion covers, in a stable
    order. Empty means the row satisfies the ⊇ rule. A refused floor has no
    defined floor, so it returns `()`; the refusal is the row's blocker."""
    if floor.refused:
        return ()
    by_key: dict[AssertionKey, list[FloorAssertion]] = {}
    for a in declared:
        if a.row_id == floor.row_id:
            by_key.setdefault(assertion_key(a), []).append(a)
    missing = [
        f for f in floor.assertions
        if not any(covers(d, f) for d in by_key.get(assertion_key(f), ()))
    ]
    return tuple(sorted(missing, key=lambda a: (a.list_index, a.kind, repr(a.params))))


def contradicts(declared: FloorAssertion, floor: FloorAssertion) -> bool:
    """True iff `declared` shares `floor`'s key and a param name but disagrees
    on its value -- a template literal that the RMXP source refutes."""
    if assertion_key(declared) != assertion_key(floor):
        return False
    declared_params = dict(declared.params)
    return any(
        name in declared_params and declared_params[name] != value
        for name, value in floor.params)


#: Floor kinds the section-9 boot walk checks by eye instead of the ⊇ rule
#: (C9 ruling 7): the hand suite never asserted them either.
WALK_CHECKED_KINDS = frozenset({"audio", "visual", "displacement"})


@dataclass(frozen=True)
class GradedGaps:
    """What the graded ⊇ rule holds against a row: `contradicted` (declared
    with the floor's key but a different param value) and `missing` (not
    declared at all, after the walk-checked / blocked_obstacle scoping)."""

    contradicted: tuple[FloorAssertion, ...] = ()
    missing: tuple[FloorAssertion, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.contradicted or self.missing)


def graded_gaps(floor: RowFloor, declared: Iterable[FloorAssertion]) -> GradedGaps:
    """The ONE definition of "does not cover its floor", shared by the C9
    grader and the manifest checker. Every contradiction counts; a
    merely-missing assertion counts unless it is walk-checked (C9 ruling 7)
    or the floor is a capability block, which owes only its
    `blocked_obstacle` (C9 ruling 10) -- or, once the capability is held,
    that obstacle's positive twin: a declared `smashed_obstacle` for the same
    row and cell covers it (CH08 §9)."""
    declared = tuple(declared)
    missing = uncovered(floor, declared)
    contradicted = [f for f in missing if any(contradicts(d, f) for d in declared)]
    if any(a.kind == "blocked_obstacle" for a in floor.assertions):
        def cell(a: FloorAssertion) -> tuple:
            p = dict(a.params)
            return (a.row_id, p.get("x"), p.get("y"), p.get("capability"))

        smashed = {cell(d) for d in declared if d.kind == "smashed_obstacle"}
        owed = [f for f in missing if f.kind == "blocked_obstacle" and cell(f) not in smashed]
    else:
        owed = [f for f in missing if f.kind not in WALK_CHECKED_KINDS]
    return GradedGaps(
        contradicted=tuple(contradicted),
        missing=tuple(f for f in owed if f not in contradicted))


def is_boundary_claim(row_id: str, beats: Sequence[Any]) -> bool:
    """True iff every claiming beat is a warp declaring nothing for `row_id`
    -- the shape of `warp_beat(boundary=True)`, which stops on the approach
    cell and leaves the crossing to the successor chapter (C9 ruling 9).
    `beats` are `playtest.chapter.Beat`s (duck-typed: `.archetype`,
    `.assertions`) so this leaf module stays free of playtest imports."""
    return all(b.archetype == "warp" for b in beats) and not any(
        a.row_id == row_id for b in beats for a in (b.assertions or ()))


def inherited_page_trigger(row_id: str, page_beats: Sequence[Any]) -> frozenset[FloorAssertion]:
    """The `trigger` assertions a branch row inherits from its owning page.

    An arm's floor repeats its page's `trigger` by construction -- the arm
    runs only inside that one firing of the page -- so a beat that claims the
    PAGE and declares its trigger has proved the arm's trigger too, even when
    the arm is claimed by a different beat (an arrival nudge's arms beat rides
    in the nudge's group and observes after the fact, so it cannot declare
    the trigger itself; CH02 `map033/ev023/p1/b0`, PROJECT_TODO #124).
    Returned re-keyed to `row_id`, ready to union into its declared set.
    Empty for a non-branch row. `page_beats` are the beats claiming the
    owning page row (duck-typed `.assertions`)."""
    page_row_id, _, leaf = row_id.rpartition("/")
    if not (leaf.startswith("b") and leaf[1:].isdigit()):
        return frozenset()
    return frozenset(
        replace(a, row_id=row_id)
        for b in page_beats for a in (b.assertions or ())
        if a.row_id == page_row_id and a.kind == "trigger")
