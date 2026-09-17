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

from collections.abc import Iterable

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
