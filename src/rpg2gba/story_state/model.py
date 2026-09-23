"""C2b: liveness, saturation, ordering edges, chapter chaining, ownership
verdicts (REDERIVATION_PLAN.md §16.3 C2, "C2 shape"/"Design" paragraphs).

C2a (`extract.py`/`state.py`) derives what each row reads and writes; this
module decides, for a chain of chapters, which rows are ever live, at what
stage of saturation, and who owns them. C6 (later) turns the partial order
this module emits into a route -- nothing here picks an order.
"""
from __future__ import annotations

import functools
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from rpg2gba.chapter_atlas.binding import ChapterBinding, load_binding
from rpg2gba.chapter_manifest.generator import generate_chapter_manifest
from rpg2gba.chapter_manifest.schema import parse_row_id, row_id_sort_key
from rpg2gba.conversion_agent.flag_registry import load_label_tables
from rpg2gba.pbs_converter.heal_locations import initial_anchor
from rpg2gba.story_state.extract import (
    RowState,
    extract_map,
    extract_triggered_common_events,
)
from rpg2gba.story_state.state import (
    RESPAWN_MAP,
    Adjust,
    Assign,
    EngineKey,
    Key,
    SelfSwitch,
    Switch,
    TempSwitch,
    Test,
    Variable,
    Write,
)
from rpg2gba.story_state.transitions import TRANSITIONS

logger = logging.getLogger(__name__)

MAX_VARIABLE_VALUES = 32

# --- abstract state -------------------------------------------------------

State = dict[Key, frozenset]


class _VariableTop:
    """Sentinel: an unparsed/havoc'd write made this Variable's value TOP --
    every comparison is `possible`, none is `certain` (REDERIVATION_PLAN.md
    §16.3 C2b handback FIX 2b). A switch-like key (Switch/SelfSwitch) never
    needs this -- its domain is just {False, True}, already fully expressive
    as havoc -- so TOP exists only for `Variable`, whose domain is
    unbounded. Absorbing: once a variable is TOP it stays TOP (see
    `_union_values`), so a TOP value set is always the singleton
    `frozenset({VARIABLE_TOP})`, never mixed with concrete ints -- callers
    that need "is this key havoc'd" can just check `VARIABLE_TOP in values`.
    """

    def __repr__(self) -> str:
        return "TOP"


VARIABLE_TOP = _VariableTop()


def _default_value(key: Key) -> frozenset:
    if isinstance(key, TempSwitch):
        # Per-visit, reset on map entry -- never persisted, always both.
        return frozenset({False, True})
    if isinstance(key, (Variable, EngineKey)):
        # `EngineKey` (RESPAWN_MAP) is int-valued like a Variable
        # (REDERIVATION_PLAN.md §16.3 C3). `0` here is a bug-detection floor
        # only -- the real value is always explicitly seeded into INTRO's
        # state before saturation ever runs (`model_intro`'s
        # `initial_anchor().map_id` seed), so this fallback should never be
        # what a real chapter run actually observes.
        return frozenset({0})
    return frozenset({False})


def _get(state: State, key: Key) -> frozenset:
    if isinstance(key, TempSwitch):
        return frozenset({False, True})
    return state.get(key, _default_value(key))


def _union_values(a: frozenset, b: frozenset) -> frozenset:
    """`a | b`, except TOP absorbs: if either side is (or contains) the
    `VARIABLE_TOP` sentinel, the result is TOP, never a mixed
    {VARIABLE_TOP, 5, ...} set (REDERIVATION_PLAN.md §16.3 C2b handback
    FIX 2b) -- keeps a havoc'd variable's value set always a clean
    singleton and never trips the 32-value cap."""
    if VARIABLE_TOP in a or VARIABLE_TOP in b:
        return frozenset({VARIABLE_TOP})
    return a | b


def _apply_havoc(state: State, key: Key) -> None:
    """A possibly-live row's unparsed write named `key` -- its value becomes
    TOP (REDERIVATION_PLAN.md §16.3 C2b handback FIX 2b): {False, True} for
    a switch-like key (a small enough domain that "havoc" already IS its
    full domain), or the `VARIABLE_TOP` sentinel for a Variable."""
    if isinstance(key, (Variable, EngineKey)):
        state[key] = frozenset({VARIABLE_TOP})
    else:
        state[key] = _get(state, key) | frozenset({False, True})


def _cmp(op: str, a: Any, b: Any) -> bool:
    if op == "==":
        return a == b
    if op == "!=":
        return a != b
    if op == ">=":
        return a >= b
    if op == "<=":
        return a <= b
    if op == ">":
        return a > b
    if op == "<":
        return a < b
    raise ValueError(f"unknown comparison op {op!r}")


def possible(test: Test, state: State) -> bool:
    """True when SOME value of `test.key` in `state` satisfies `test`.

    TOP is possible against every test -- havoc means "could be anything"
    (REDERIVATION_PLAN.md §16.3 C2b handback FIX 2b).
    """
    values = _get(state, test.key)
    if VARIABLE_TOP in values:
        return True
    return any(_cmp(test.op, v, test.value) for v in values)


def certain(test: Test, state: State) -> bool:
    """True when EVERY value of `test.key` in `state` satisfies `test`.

    TOP is never certain -- "could be anything" rules out "definitely
    this."""
    values = _get(state, test.key)
    if VARIABLE_TOP in values:
        return False
    return bool(values) and all(_cmp(test.op, v, test.value) for v in values)


def _apply_op(op: str, v: int, amount: int) -> int:
    if op == "+":
        return v + amount
    if op == "-":
        return v - amount
    if op == "*":
        return v * amount
    if op == "/":
        return v // amount if amount != 0 else v
    if op == "%":
        return v % amount if amount != 0 else v
    raise ValueError(f"unknown adjust op {op!r}")


def _apply_write(state: State, write: Write) -> None:
    if isinstance(write.key, TempSwitch):
        return  # never persisted (state.py docstring)
    if isinstance(write, Assign):
        state[write.key] = _union_values(_get(state, write.key), write.values)
    elif isinstance(write, Adjust):
        cur = _get(state, write.key)
        if VARIABLE_TOP in cur:
            return  # already TOP; adjusting TOP is still TOP (no-op)
        state[write.key] = cur | frozenset(_apply_op(write.op, v, write.amount) for v in cur)
    else:
        raise TypeError(f"unknown write shape {write!r}")


def _check_no_blowup(state: State, culprits_by_key: dict[Key, list[str]]) -> None:
    for key, values in state.items():
        if VARIABLE_TOP in values:
            continue  # TOP is not a blow-up (FIX 2b) -- always a singleton anyway
        if isinstance(key, Variable) and len(values) > MAX_VARIABLE_VALUES:
            rows = culprits_by_key.get(key, [])
            raise ValueError(
                f"story_state: Variable({key.id}) exceeded {MAX_VARIABLE_VALUES} values "
                f"({len(values)}) -- rows adjusting it: {sorted(set(rows))}"
            )


# --- output shapes ---------------------------------------------------------

# "undetermined" (REDERIVATION_PLAN.md §16.3 C2b handback FIX 2c) is a row
# that never became live, BUT whose non-liveness cannot be claimed with
# confidence: either some possibly-live row in scope has `havoc_global`
# (could be touching anything, including this row's own gate), or one of
# THIS row's own unsatisfied tests names a key that some possibly-live row
# havoc's (FIX 2b). `unreachable` is reserved for rows whose non-liveness no
# refusal or havoc could explain -- a real negative claim, not a shrug.
RowStatus = Literal["live", "later", "unreachable", "refused", "undetermined"]


@dataclass(frozen=True)
class RowVerdict:
    row_id: str
    status: RowStatus
    owner: str | None
    stage: int | None
    enabled_by: tuple[tuple[str, ...], ...]
    killed_by: tuple[str, ...]
    blockers: tuple[str, ...]
    forced: bool
    refusals: tuple[str, ...]
    detail: str | None


@dataclass(frozen=True)
class OrderDependentKey:
    """A key whose cross-page maximal writers disagreed with no precedence
    edge between them (REDERIVATION_PLAN.md §16.3 C2b handback, lead
    ruling 2026-09-16): a REAL order dependence, not a modelling failure --
    C2 must not fail on it, and C6's route is what actually decides which
    write lands. `key` is the same string form `ChapterStory.end_state`
    keys use (`_state_key_repr`); `writers` is every disagreeing maximal
    writer row id (sorted); `values` is the JOINED value set this key was
    recorded as in `end_state` -- a sound over-approximation of "whichever
    the route visits last", not a claim about which one actually wins.
    """
    key: str
    writers: tuple[str, ...]
    values: tuple


@dataclass(frozen=True)
class ForkReport:
    """One engine-transition fork that actually ran on a chapter
    (REDERIVATION_PLAN.md §16.3 C3, ruling R9): its precondition was possible
    at some point on the chapter's main path (its saturated state).
    `landing_maps` is every map id `transition.lands_on` possibly held at any
    point in the chapter (every map in cumulative
    scope, if that key was TOP); `owned_row_ids` is every row the fork itself
    newly owned (sorted) -- never rows already live on the main path or owned
    by an earlier chapter (`saturate`'s `already_owned` excludes those from
    the fork's own walk, same as any other saturation)."""

    transition: str
    landing_maps: tuple[int, ...]
    owned_row_ids: tuple[str, ...]


@dataclass(frozen=True)
class ChapterStory:
    chapter_id: str
    seed_from: str
    rows: tuple[RowVerdict, ...]
    end_state: tuple[tuple[str, tuple], ...]
    intro_maps: tuple[int, ...] | None = None
    # Engine-transition forks that ran on this chapter (REDERIVATION_PLAN.md
    # §16.3 C3) -- never contributes to `end_state`/`order_dependent` (R9:
    # never on the main path); a fork-owned row's OWN verdict still appears
    # in `rows`/`common_events` above, status "live", with a `fork:<name>`
    # blocker and an `engine:<name>` `enabled_by` group.
    forks: tuple[ForkReport, ...] = ()
    # Triggered-common-event pseudo-rows (REDERIVATION_PLAN.md §16.3 C2
    # ruling (e)) reported HERE, never in `rows`: a pseudo-row is global (not
    # owned by any map), so it is reported once -- under whichever
    # chapter/INTRO first makes it live (or, for a structurally-refused
    # pseudo-row, under INTRO, since refusal is state-independent) -- and
    # never appears as a `later:`/`unreachable:` entry on any chapter's own
    # map-row list.
    common_events: tuple[RowVerdict, ...] = ()
    # Every order-dependent key this chapter's saturation joined instead of
    # raising on -- sorted by key (`OrderDependentKey` docstring).
    order_dependent: tuple[OrderDependentKey, ...] = ()


# --- structural refusal (state-independent) --------------------------------
#
# REDERIVATION_PLAN.md §16.3 C2b handback FIX 2a: a refusal means "we cannot
# say", not "this never happens" -- treating every refusal as a hard stop
# starves everything downstream of it (CH01 measured: 160 rows falsely
# `unreachable`, entirely because SOMETHING upstream had an
# `unmodelled_outcome`/`unclassified_condition` refusal and got fully
# excluded from saturation instead of just kept out of the "confidently
# live" bucket). A refusal is SOFT -- the row still participates in
# saturation as possibly-live, sound-over-approximation, but its REPORTED
# status stays "refused" -- when it is purely a GUARD/outcome-level refusal
# (we don't know if/how this arm becomes live, but its own writes, if
# parseable, still apply whenever we get here) or the one WRITE-level soft
# code (`unparsed_state_write`, whose unknown effect becomes havoc -- FIX
# 2b -- rather than blocking the row). Every other code (malformed
# write/condition, a missing/cyclic common event, an invalid self-switch
# write in a common event, an unhandled condition type, a missing arm guard)
# is HARD: extraction could not make sense of the row's own SHAPE at all,
# not just its eventual value, and stays fully excluded.

_SOFT_GUARD_REFUSAL_PREFIXES = frozenset({
    "unmodelled_predicate",
    "nonconstant_variable_condition",
    "unclassified_condition",
    "unparsed_state_condition",
    "unmodelled_outcome",
})
_SOFT_WRITE_REFUSAL_CODES = frozenset({"unparsed_state_write"})


def _is_hard_refused(codes: tuple[str, ...] | None) -> bool:
    """True when `codes` (a `_structural_refusal` result) contains at least
    one HARD refusal code -- a soft-only (or empty/`None`) refusal set does
    NOT block saturation (FIX 2a/2b above)."""
    if codes is None:
        return False
    for code in codes:
        prefix = code.split(":", 1)[0]
        if prefix in _SOFT_GUARD_REFUSAL_PREFIXES or prefix in _SOFT_WRITE_REFUSAL_CODES:
            continue
        return True
    return False


def _structural_refusal(
    row_id: str, rows_by_id: dict[str, RowState], cache: dict[str, tuple[str, ...] | None],
) -> tuple[str, ...] | None:
    if row_id in cache:
        return cache[row_id]
    row = rows_by_id[row_id]
    if row.parent_row_id is None:
        codes = tuple(r.code for r in (row.page_refusals + row.refusals))
        result = codes or None
        cache[row_id] = result
        return result

    parent = _structural_refusal(row.parent_row_id, rows_by_id, cache)
    own = list(r.code for r in row.refusals)
    guard = row.arm_guard
    if guard is None:
        # Invariant: extract.py never returns arm_guard=None without a
        # refusal recorded alongside it.
        if not own:
            own = ["missing_arm_guard"]
    elif guard.outcome is not None:
        if guard.outcome.kind == "state" and not guard.tests:
            own.append("unparsed_state_condition")
        elif guard.outcome.kind == "unmodelled":
            own.append(f"unmodelled_outcome:{guard.outcome.detail}")

    combined = (parent or ()) + tuple(own)
    result = combined or None
    cache[row_id] = result
    return result


# --- state-dependent liveness -----------------------------------------------


def _live_status(
    row_id: str,
    rows_by_id: dict[str, RowState],
    state: State,
    cache: dict[str, tuple[bool, tuple[str, ...]]],
) -> tuple[bool, tuple[str, ...]]:
    if row_id in cache:
        return cache[row_id]
    row = rows_by_id[row_id]

    if row.parent_row_id is None:
        if not all(possible(t, state) for t in row.page_tests):
            result = (False, ())
        else:
            idx = row.event_page_row_ids.index(row.row_id)
            killed = False
            for higher_id in row.event_page_row_ids[idx + 1:]:
                higher = rows_by_id.get(higher_id)
                if higher is None or higher.page_refusals:
                    continue
                if all(certain(t, state) for t in higher.page_tests):
                    killed = True
                    break
            result = (not killed, ())
    else:
        parent_live, parent_blockers = _live_status(row.parent_row_id, rows_by_id, state, cache)
        if not parent_live:
            result = (False, ())
        else:
            guard = row.arm_guard
            # `guard is None` only reaches here for a SOFT-refused arm (e.g.
            # `unclassified_condition`/`nonconstant_variable_condition` --
            # `_arm_guard` returned no guard at all): a hard-refused arm is
            # excluded from saturation entirely by `_is_hard_refused`, so it
            # never calls `_live_status`. With no guard to evaluate, treat it
            # like an arm with no tests -- vacuously possible given a live
            # parent (FIX 2a: sound over-approximation, not a guess at which
            # way the unparsed guard actually goes).
            tests = guard.tests if guard is not None else ()
            if not all(possible(t, state) for t in tests):
                result = (False, ())
            else:
                blockers = parent_blockers
                if guard is not None and guard.outcome is not None:
                    kind = guard.outcome.kind
                    if kind in ("fork", "harness", "capability"):
                        blockers = blockers + (f"{kind}:{guard.outcome.detail}",)
                result = (True, blockers)

    cache[row_id] = result
    return result


# --- saturation --------------------------------------------------------


@dataclass
class _SaturationResult:
    end_state: State
    newly_owned: dict[str, int]  # row_id -> stage, this call's new owners only
    blockers: dict[str, tuple[str, ...]]  # row_id -> blockers, newly-owned rows only


def saturate(
    seed: State,
    rows_by_id: dict[str, RowState],
    order: list[str],
    *,
    already_owned: dict[str, tuple[str, ...]],
    structural_refusal: dict[str, tuple[str, ...] | None],
) -> _SaturationResult:
    """Iterates rows not yet owned (by an earlier chapter) to a fixpoint.

    `already_owned` (row_id -> its recorded blockers) short-circuits
    `_live_status` for rows an earlier chapter already claimed -- their
    writes are already folded into `seed`, so they are never re-walked
    (REDERIVATION_PLAN.md §16.3 C2, chaining paragraph).
    """
    state: State = dict(seed)
    newly_owned: dict[str, int] = {}
    blockers_out: dict[str, tuple[str, ...]] = {}
    stage = 0

    while True:
        cache: dict[str, tuple[bool, tuple[str, ...]]] = {
            rid: (True, b) for rid, b in already_owned.items()
        }
        this_stage: list[str] = []
        for row_id in order:
            if row_id in already_owned or row_id in newly_owned:
                continue
            if _is_hard_refused(structural_refusal.get(row_id)):
                continue
            live, blockers = _live_status(row_id, rows_by_id, state, cache)
            if live:
                this_stage.append(row_id)
                blockers_out[row_id] = blockers

        if not this_stage:
            break

        culprits: dict[Key, list[str]] = {}
        for row_id in this_stage:
            newly_owned[row_id] = stage
            row = rows_by_id[row_id]
            for w in row.writes:
                _apply_write(state, w)
                if isinstance(w.key, Variable):
                    culprits.setdefault(w.key, []).append(row_id)
            # FIX 2b: a possibly-live row's unparsed writes still touch
            # SOMETHING -- fold them into state as TOP rather than silently
            # dropping them (a sound over-approximation, not a guess).
            for key in row.havoc_keys:
                _apply_havoc(state, key)
                if isinstance(key, Variable):
                    culprits.setdefault(key, []).append(row_id)
        _check_no_blowup(state, culprits)
        stage += 1

    return _SaturationResult(end_state=state, newly_owned=newly_owned, blockers=blockers_out)


# --- enablers / killers ------------------------------------------------


def _ancestor_tests(row_id: str, rows_by_id: dict[str, RowState]) -> tuple[Test, ...]:
    """Every test gating `row_id`: its own page_tests, its own arm guard's
    tests (if a branch row), and every ancestor arm's guard tests."""
    row = rows_by_id[row_id]
    tests: list[Test] = list(row.page_tests)
    cur: RowState | None = row
    while cur is not None:
        if cur.arm_guard is not None:
            tests.extend(cur.arm_guard.tests)
        cur = rows_by_id[cur.parent_row_id] if cur.parent_row_id is not None else None
    return tuple(tests)


def _cap_detail(label: str, row_ids: list[str]) -> str:
    capped = row_ids[:5]
    suffix = f" (+{len(row_ids) - 5} more)" if len(row_ids) > 5 else ""
    return f"{label}: {', '.join(capped)}{suffix}"


def _undetermined_detail(
    row_id: str, rows_by_id: dict[str, RowState], owned_ids: set[str],
) -> str | None:
    """REDERIVATION_PLAN.md §16.3 C2b handback FIX 2c: why a row that never
    became live cannot be confidently called `unreachable` -- or `None` if
    it genuinely can be. Two triggers, either sufficient: (a) some
    possibly-live row IN SCOPE has `havoc_global` (could be touching
    literally anything, including this row's own gate); (b) one of THIS
    row's own tests names a key some possibly-live row's `havoc_keys`
    names specifically. `unreachable` is reserved for rows neither trigger
    explains -- a row whose non-liveness no refusal or havoc anywhere in
    scope could account for."""
    global_rows = sorted(rid for rid in owned_ids if rows_by_id[rid].havoc_global)
    if global_rows:
        return _cap_detail("havoc_global", global_rows)

    test_keys = {t.key for t in _ancestor_tests(row_id, rows_by_id)}
    matches = sorted({
        rid for rid in owned_ids
        for key in rows_by_id[rid].havoc_keys
        if key in test_keys
    })
    if matches:
        return _cap_detail("havoc_key", matches)
    return None


def _write_satisfies(write: Write, test: Test) -> bool:
    """Best-effort: does `write` add a value making `test` true?

    For `Assign` this is exact (`write.values` is the concrete value set
    added). For `Adjust` the resulting values depend on the pre-write state,
    which this helper does not have -- it conservatively treats any `Adjust`
    on the same key as a candidate enabler. Documented deviation from a
    fully exact per-value check (REDERIVATION_PLAN.md §16.3 C2b handback).
    """
    if write.key != test.key:
        return False
    if isinstance(write, Assign):
        return any(_cmp(test.op, v, test.value) for v in write.values)
    return True  # Adjust: key matches, treated as a candidate


def compute_enabled_by(
    row_id: str,
    rows_by_id: dict[str, RowState],
    seed: State,
    live_rows: dict[str, tuple[str, int]],  # row_id -> (owner_chapter, stage)
) -> tuple[tuple[str, ...], ...]:
    groups: list[tuple[str, ...]] = []
    for test in _ancestor_tests(row_id, rows_by_id):
        if possible(test, seed):
            continue
        candidates = sorted(
            r for r in live_rows
            if any(_write_satisfies(w, test) for w in rows_by_id[r].writes)
            # A havoc'd key (FIX 2b) satisfies every test on it by
            # definition (TOP == "could be anything") -- a possibly-live
            # row with `test.key` in its `havoc_keys` is as valid an
            # enabler as an exact matching write.
            or test.key in rows_by_id[r].havoc_keys
        )
        if not candidates:
            raise ValueError(
                f"story_state: row {row_id!r} became live only after the seed, "
                f"but no in-scope live row writes a value satisfying {test!r} "
                "-- enabler search found nothing (bug)"
            )
        groups.append(tuple(candidates))
    return tuple(groups)


def compute_killed_by(
    row_id: str,
    rows_by_id: dict[str, RowState],
    in_scope_ids: set[str],
    seed: State,
) -> tuple[str, ...]:
    row = rows_by_id[row_id]
    own_tests = list(row.page_tests)
    if row.arm_guard is not None:
        own_tests.extend(row.arm_guard.tests)

    killers: set[str] = set()

    for other_id in in_scope_ids:
        if other_id == row_id:
            continue
        other = rows_by_id[other_id]
        for w in other.writes:
            if not isinstance(w, Assign):
                continue
            # (a) assigns a value making one of row's own tests false.
            for t in own_tests:
                if w.key == t.key and any(not _cmp(t.op, v, t.value) for v in w.values):
                    killers.add(other_id)

            # (b) assigns a value satisfying a test of a HIGHER page of
            # row's own event, where that higher page has no OTHER tests
            # (or every other test is already certain under the seed).
            if row.parent_row_id is None:
                idx = row.event_page_row_ids.index(row.row_id)
                for higher_id in row.event_page_row_ids[idx + 1:]:
                    higher = rows_by_id.get(higher_id)
                    if higher is None or higher.page_refusals:
                        continue
                    for t in higher.page_tests:
                        if w.key != t.key or not any(_cmp(t.op, v, t.value) for v in w.values):
                            continue
                        others = [ot for ot in higher.page_tests if ot != t]
                        if all(certain(ot, seed) for ot in others):
                            killers.add(other_id)

    return tuple(sorted(killers))


def _exclusivity_groups(
    row_id: str, rows_by_id: dict[str, RowState],
) -> dict[tuple[str | None, int], str]:
    """Every branch-construct gate `row_id` sits under (including `row_id`
    itself, if it is such an arm), keyed by `(parent_row_id, opener_index)`
    -> the SPECIFIC arm row_id chosen at that gate (REDERIVATION_PLAN.md
    §16.3 C2b handback, sibling-arm join rule; broadened by FIX 1 to every
    branch construct, not just input/random -- ANY two distinct arms of the
    SAME 111/102 are mutually exclusive at runtime by construction,
    regardless of why the branch exists).

    `(parent_row_id, opener_index)` identifies one branch CONSTRUCT (every
    arm of one 111/102 shares both), so two rows sharing a key but disagreeing
    on which arm they descend from are mutually-exclusive alternatives --
    never simultaneous, so their writes should JOIN at end state rather than
    be treated as an unordered conflict.
    """
    groups: dict[tuple[str | None, int], str] = {}
    cur: RowState | None = rows_by_id[row_id]
    while cur is not None:
        guard = cur.arm_guard
        if guard is not None and guard.opener_index is not None:
            key = (cur.parent_row_id, guard.opener_index)
            groups.setdefault(key, cur.row_id)
        cur = rows_by_id[cur.parent_row_id] if cur.parent_row_id is not None else None
    return groups


def _mutually_exclusive_sibling_arms(
    row_id_a: str, row_id_b: str, rows_by_id: dict[str, RowState],
) -> bool:
    """True when `row_id_a`/`row_id_b` are (or descend from) two DISTINCT
    arms of the same branch construct -- see `_exclusivity_groups`."""
    if row_id_a == row_id_b:
        return False
    groups_a = _exclusivity_groups(row_id_a, rows_by_id)
    groups_b = _exclusivity_groups(row_id_b, rows_by_id)
    for key, arm_a in groups_a.items():
        arm_b = groups_b.get(key)
        if arm_b is not None and arm_b != arm_a:
            return True
    return False


def _page_key(row_id: str) -> str:
    """The page (event page, or triggered-common-event trunk) `row_id`
    belongs to -- its own id if it already IS a page/pseudo-trunk row, else
    its owning page's id (REDERIVATION_PLAN.md §16.3 C2b handback FIX 1)."""
    if _is_pseudo_row_id(row_id):
        return _pseudo_trunk_row_id(row_id)
    return parse_row_id(row_id).owning_page_row_id


def _shadowed_within_page(
    items: list[tuple[str, Write]], rows_by_id: dict[str, RowState],
) -> list[tuple[str, Write]]:
    """Of `items` (writer rows all writing the SAME key, already known to
    share one page), drop any write shadowed by a LATER write (by
    `Write.list_index`) to the same key -- UNLESS the two writes' own rows
    are mutually-exclusive sibling arms of the same branch construct, in
    which case both survive as alternative final values (REDERIVATION_PLAN.md
    §16.3 C2b handback FIX 1: a page trunk and its descendant arms are ONE
    execution ordered by list position, not unordered sibling rows -- the
    worked example is map081's Switch(185): a page trunk sets it ON at
    list[0], and every one of its live arms sets it OFF later, so the
    trunk's ON is shadowed and only the (agreeing) arm OFFs survive)."""
    ordered = sorted(items, key=lambda t: t[1].list_index)
    survivors: list[tuple[str, Write]] = []
    for i, (rid_i, w_i) in enumerate(ordered):
        shadowed = any(
            not _mutually_exclusive_sibling_arms(rid_i, rid_j, rows_by_id)
            for rid_j, _ in ordered[i + 1:]
        )
        if not shadowed:
            survivors.append((rid_i, w_i))
    return survivors


class OrderDependentEndState(ValueError):
    """A precedence CYCLE among a key's writers -- no writer is maximal, so
    there is no well-founded "last write wins" at all (REDERIVATION_PLAN.md
    §16.3 C2b "End state" rule, design paragraph: "a cycle among mandatory
    edges" fails loud alongside itself). This is the one genuinely
    impossible case left in `compute_end_state`: a plain writer
    DISAGREEMENT with no precedence edge between them is NOT impossible --
    it is order-dependent, and C2 records it (`OrderDependentKey`) rather
    than raising (lead ruling 2026-09-16, superseding the original "raise on
    disagreement" rule). A genuine cycle is still a bug-shaped input (mutual
    `enabled_by` edges pointing at each other), so it still fails loud."""


def compute_end_state(
    seed: State,
    owned_row_ids: set[str],
    rows_by_id: dict[str, RowState],
    enabled_by_of: dict[str, tuple[tuple[str, ...], ...]],
    pick_winner: Callable[[tuple[str, ...]], str | None] | None = None,
) -> tuple[State, tuple["OrderDependentKey", ...]]:
    """The chapter's end state: `seed` plus, for every key any OWNED row of
    this chapter writes, the value(s) its maximal writers agree on -- plus
    the list of keys where they didn't.

    A writer is "maximal" among the writers of one key when no other writer
    of that same key is its (transitive, singleton-enabled_by-edge) successor.
    All-agreeing single-valued maximal writers collapse to one concrete
    value (an ordered toggle ends deterministic); any Adjust or multi-valued
    (random) maximal write instead joins every maximal contribution.
    Disagreeing single values are one of two things: mutually-exclusive
    sibling arms of the SAME branch construct (`_mutually_exclusive_sibling_
    arms`) -- alternatives, not a conflict at all, joined silently (worked
    example: common event 51's day/night guard writes switch 105/106 to
    both True and False across its two `time_of_day`-gated arms; the joined
    end state is `{False, True}` for each) -- or a genuine cross-page order
    dependence (worked example: map049/map050, two unrelated events, each
    unconditionally setting the same switch to a different value with no
    route between them yet) -- joined too, but RECORDED as an
    `OrderDependentKey` (lead ruling 2026-09-16, REDERIVATION_PLAN.md §16.3
    C2 design paragraph as amended): C2's job is to prove what's POSSIBLE,
    not to pick a winner -- `seed`/`end_state` are therefore a SOUND
    OVER-APPROXIMATION for C2's purposes (every value either side could
    concretely leave the key at), not the one true answer. C6 owns "the one
    true answer": it recomputes each chapter's seed from its own concrete
    route order once that route is chosen, at which point a route that
    actually visits both writers has a real, unambiguous last write.

    BEFORE any of that, REDERIVATION_PLAN.md §16.3 C2b handback FIX 1
    collapses each PAGE's own writes to a key down to its net contribution:
    a page trunk and its descendant arm rows are ONE execution, ordered by
    each write's `list_index`, not unordered sibling rows -- a write
    shadowed by a later write to the same key ON THE SAME PAGE (unless the
    two are mutually-exclusive sibling arms) is dropped before the
    cross-page comparison below even runs (worked example: map081's
    Switch(185) -- a page trunk sets it ON at list[0] and every live arm
    sets it OFF later; the trunk's ON is shadowed, the arms' agreeing OFFs
    survive, end state is a clean `{False}`, no join needed). What remains
    after that per-page collapse is compared across DIFFERENT pages using
    the precedence machinery below, exactly as before.

    FIX 2b: a key any OWNED row `havoc`'d (an unparsed write whose value
    could not be determined) skips ALL of the above -- TOP always joins,
    never becomes an `OrderDependentKey` (`_apply_havoc`/`VARIABLE_TOP`).

    A true precedence CYCLE (no writer of a key is maximal at all) is the
    one case still genuinely impossible to resolve here and still raises
    `OrderDependentEndState`.

    `pick_winner` (C6 seed recompute): given an order-dependent key's sorted
    maximal writers, the one the chapter's concrete route visits last, or
    None when no route is known. A pick lands that writer's value in the end
    state -- the next chapter's seed -- instead of the join; the key is still
    recorded (with the joined values) so the review doc shows the choice.
    """
    order_dependent: list[OrderDependentKey] = []
    havoc_keys_owned: set[Key] = {
        key for r in owned_row_ids for key in rows_by_id[r].havoc_keys
        if not isinstance(key, TempSwitch)
    }

    preds: dict[str, set[str]] = {r: set() for r in owned_row_ids}
    for r in owned_row_ids:
        for group in enabled_by_of.get(r, ()):
            if len(group) == 1 and group[0] in owned_row_ids:
                preds[r].add(group[0])

    def _is_predecessor(candidate: str, of: str) -> bool:
        seen: set[str] = set()
        stack = list(preds.get(of, ()))
        while stack:
            p = stack.pop()
            if p == candidate:
                return True
            if p in seen:
                continue
            seen.add(p)
            stack.extend(preds.get(p, ()))
        return False

    writers_by_key: dict[Key, list[tuple[str, Write]]] = {}
    for r in owned_row_ids:
        for w in rows_by_id[r].writes:
            if isinstance(w.key, TempSwitch):
                continue
            writers_by_key.setdefault(w.key, []).append((r, w))

    # FIX 1: collapse each page's own writers of a key to their net
    # (non-shadowed) survivors before the cross-page comparison below.
    for key, items in list(writers_by_key.items()):
        by_page: dict[str, list[tuple[str, Write]]] = {}
        for rid, w in items:
            by_page.setdefault(_page_key(rid), []).append((rid, w))
        survivors: list[tuple[str, Write]] = []
        for page_items in by_page.values():
            survivors.extend(_shadowed_within_page(page_items, rows_by_id))
        writers_by_key[key] = survivors

    end: State = dict(seed)
    for key, writers in writers_by_key.items():
        if key in havoc_keys_owned:
            continue  # FIX 2b: havoc dominates -- handled in the pass below
        writer_rows = [r for r, _ in writers]
        maximal = [
            (r, w) for r, w in writers
            if not any(_is_predecessor(r, r2) for r2 in writer_rows if r2 != r)
        ]
        if not maximal:
            raise OrderDependentEndState(
                f"story_state: key {key!r} has a precedence cycle among its "
                f"writers {sorted(writer_rows)!r} -- no maximal writer"
            )

        # A conditional write (only guaranteed on one arm of the writing
        # row's own branches -- `Assign.conditional`, state.py) cannot be
        # collapsed to a single deterministic value, nor can more than one
        # write from the SAME row (mutually exclusive branches of one row
        # inlined by extract.py all land on that row's `writes`, per
        # `_extract_ce_writes`) -- both join instead of "disagreeing".
        maximal_rows = [r for r, _ in maximal]
        ambiguous = (
            len(set(maximal_rows)) < len(maximal_rows)
            or any(
                isinstance(w, Adjust)
                or (isinstance(w, Assign) and (len(w.values) > 1 or w.conditional))
                for _, w in maximal
            )
        )
        if ambiguous:
            joined = _get(end, key)
            for _, w in maximal:
                if isinstance(w, Assign):
                    joined = _union_values(joined, w.values)
                else:
                    cur = _get(end, key)
                    joined = _union_values(
                        joined, frozenset(_apply_op(w.op, v, w.amount) for v in cur))
            end[key] = joined
            continue

        single_values = {next(iter(w.values)) for _, w in maximal if isinstance(w, Assign)}
        if len(single_values) > 1:
            maximal_rows_only = [r for r, _ in maximal]
            all_sibling_pairs = all(
                _mutually_exclusive_sibling_arms(r1, r2, rows_by_id)
                for i, r1 in enumerate(maximal_rows_only)
                for r2 in maximal_rows_only[i + 1:]
            )
            if all_sibling_pairs:
                joined = _get(end, key)
                for _, w in maximal:
                    joined = _union_values(joined, w.values)  # all Assign (single_values built from it)
                end[key] = joined
                continue
            # Lead ruling 2026-09-16: a genuine cross-page order dependence
            # -- no precedence edge, no sibling-arm exclusivity, disagreeing
            # maximal writers. Not a raise: join (sound over-approximation)
            # and record it for C6's route to actually resolve.
            joined = _get(end, key)
            for _, w in maximal:
                joined = _union_values(joined, w.values)
            writers = tuple(sorted(r for r, _ in maximal))
            winner = pick_winner(writers) if pick_winner is not None else None
            if winner is None:
                end[key] = joined
            else:
                won = [w for r, w in maximal if r == winner]
                if not won:
                    raise ValueError(f"story_state: key {key!r}: picked winner {winner!r} "
                                     f"is not one of its writers {list(writers)}")
                end[key] = frozenset(won[0].values)
            order_dependent.append(OrderDependentKey(
                key=_state_key_repr(key),
                writers=writers,
                values=_freeze_values(joined),
            ))
            continue
        if single_values:
            end[key] = frozenset(single_values)

    # FIX 2b: havoc dominates -- every key ANY owned row havoc'd ends TOP
    # (or the switch-like full domain), joined onto whatever the normal
    # writers above would otherwise have said, never raising.
    for key in havoc_keys_owned:
        if isinstance(key, (Variable, EngineKey)):
            end[key] = frozenset({VARIABLE_TOP})
        else:
            end[key] = _get(end, key) | frozenset({False, True})

    return end, tuple(sorted(order_dependent, key=lambda o: o.key))


# --- engine-transition forks (R9/C3) ---------------------------------------


def _apply_transition_forks(
    end_state: State,
    rows_by_id: dict[str, RowState],
    map_ids_in_scope: set[int],
    *,
    already_owned: dict[str, tuple[str, ...]],
    owner_of: dict[str, tuple[str, int]],
    structural_refusal: dict[str, tuple[str, ...] | None],
    enabled_by_of: dict[str, tuple[tuple[str, ...], ...]],
    owner_label: str,
) -> tuple[ForkReport, ...]:
    """Runs every `TRANSITIONS` entry whose precondition is possible in
    `end_state` (REDERIVATION_PLAN.md §16.3 C3, ruling R9): snapshot -> apply
    the transition's writes as OVERWRITES -> walk what it unlocks -> nothing
    is restored explicitly, because the fork's own `saturate` call is a
    throwaway walk over a COPY of `end_state`, never `end_state` itself, and
    a fork-owned row's writes never flow back into it (the caller must not
    fold the fork's `_SaturationResult.end_state` into anything -- only
    `newly_owned`/`blockers` matter here).

    Mutates `already_owned`/`owner_of`/`enabled_by_of` IN PLACE for every row
    the fork newly owns -- exactly the bookkeeping an ordinary chapter-chain
    `saturate` call's caller already does, so a later chapter's own
    saturation (main path or a later fork) sees these rows as already owned
    and never re-walks them. `owner_label` is the chapter id (or `"INTRO"`)
    these rows are attributed to.
    """
    reports: list[ForkReport] = []
    for transition in TRANSITIONS:
        if not all(possible(t, end_state) for t in transition.precondition):
            continue

        fork_state: State = dict(end_state)
        for w in transition.writes:
            fork_state[w.key] = w.values  # OVERWRITE, not join -- R9/C3 spec.

        landing_values = _get(fork_state, transition.lands_on)
        if VARIABLE_TOP in landing_values:
            landing_maps = sorted(map_ids_in_scope)
        else:
            landing_maps = sorted(v for v in landing_values if isinstance(v, int))
        landing_set = set(landing_maps)

        order = sorted(
            (
                rid for rid in rows_by_id
                if _is_pseudo_row_id(rid) or parse_row_id(rid).map_id in landing_set
            ),
            key=row_id_sort_key,
        )

        fork_result = saturate(
            fork_state, rows_by_id, order,
            already_owned=already_owned, structural_refusal=structural_refusal,
        )

        for rid, stage in fork_result.newly_owned.items():
            owner_of[rid] = (owner_label, stage)
            already_owned[rid] = (f"fork:{transition.name}",) + fork_result.blockers[rid]
            enabled_by_of[rid] = ((f"engine:{transition.name}",),)

        reports.append(ForkReport(
            transition=transition.name,
            landing_maps=tuple(landing_maps),
            owned_row_ids=tuple(sorted(fork_result.newly_owned)),
        ))
    return tuple(reports)


# --- intro pseudo-chapter (R6/R8 CH01 seed) --------------------------------

_TRANSFER_CODE = 201


def _direct_transfer_targets(map_data: dict[str, Any]) -> tuple[set[int], list[str]]:
    """Every map id a 201 transfer in `map_data` names with designation 0,
    plus a refusal string per designation-1 (variable-designated) transfer
    met (not fatal -- listed per C2's intro-chain paragraph)."""
    targets: set[int] = set()
    refusals: list[str] = []
    for event in map_data.get("events", []):
        for page in event.get("pages", []):
            for cmd in page.get("list") or []:
                if cmd.get("code") != _TRANSFER_CODE:
                    continue
                params = cmd.get("parameters") or []
                if len(params) < 2:
                    continue
                designation, target_map = params[0], params[1]
                if designation == 0 and isinstance(target_map, int):
                    targets.add(target_map)
                else:
                    refusals.append(
                        f"map{map_data.get('map_id')}/ev{event['id']}: designation "
                        f"{designation!r} transfer not modelled (variable-designated)"
                    )
    return targets, refusals


def model_intro(
    build_dir: Path,
    common_events: list[dict[str, Any]],
    switch_labels: dict[int, str],
    bound_map_ids: set[int],
    pseudo_rows: dict[str, RowState] | None = None,
    metadata_header: Path | None = None,
) -> tuple[ChapterStory, State, list[int], list[str], dict[str, tuple[int, tuple[str, ...]]]]:
    """The unbound Intro chain (R6/§16.3 "CH01 seed" paragraph, operator
    ruling (d)): start map plus every map reached from it by a direct (201,
    designation 0) transfer into another UNBOUND map.

    `pseudo_rows` (REDERIVATION_PLAN.md §16.3 C2 ruling (e)) -- the
    triggered-common-event rows from `extract.extract_triggered_common_events`
    -- are global, so they participate in INTRO's own saturation too (a
    pseudo-row's gate could in principle already be possible True before
    CH01 even starts). The 5th return value is `{row_id: (stage, blockers)}`
    for every pseudo-row INTRO itself owned, so `build_chapter_stories` can
    seed the chain's `already_owned`/`owner_of` without re-deriving them.

    `metadata_header` (default `build_dir/"include/constants/metadata.h"`)
    seeds `RESPAWN_MAP` (REDERIVATION_PLAN.md §16.3 C3): every chapter
    inherits INTRO's `initial_anchor().map_id` as the pre-any-Pokémon-Center
    respawn, exactly `heal_locations.initial_anchor`'s own MetadataHome
    fallback (`pbStartOver`, module docstring) -- reused here rather than
    re-derived, per CLAUDE.md §4.3 one-source-of-truth.
    """
    if metadata_header is None:
        metadata_header = build_dir / "include" / "constants" / "metadata.h"
    initial_respawn_map_id = initial_anchor(metadata_header).map_id

    system_path = build_dir / "system.json"
    system = json.loads(system_path.read_text(encoding="utf-8"))
    start_map_id = system["start_map_id"]

    maps_dir = build_dir / "maps"
    intro_maps: list[int] = []
    seen = {start_map_id}
    frontier = [start_map_id]
    refusals: list[str] = []
    while frontier:
        map_id = frontier.pop()
        intro_maps.append(map_id)
        map_path = maps_dir / f"Map{map_id:03d}.json"
        if not map_path.exists():
            continue
        map_data = json.loads(map_path.read_text(encoding="utf-8"))
        targets, map_refusals = _direct_transfer_targets(map_data)
        refusals.extend(map_refusals)
        for target in sorted(targets):
            if target in seen:
                continue
            if target in bound_map_ids:
                continue  # stop at the boundary of the chapter chain
            seen.add(target)
            frontier.append(target)

    intro_maps.sort()
    rows_by_id: dict[str, RowState] = {}
    for map_id in intro_maps:
        map_path = maps_dir / f"Map{map_id:03d}.json"
        if not map_path.exists():
            continue
        map_data = json.loads(map_path.read_text(encoding="utf-8"))
        rows_by_id.update(extract_map(
            map_id, map_data, common_events=common_events, switch_labels=switch_labels))

    pseudo_rows = pseudo_rows or {}
    rows_by_id.update(pseudo_rows)

    order = sorted(rows_by_id, key=row_id_sort_key)
    refusal_cache: dict[str, tuple[str, ...] | None] = {}
    structural_refusal = {rid: _structural_refusal(rid, rows_by_id, refusal_cache) for rid in order}
    seed: State = {RESPAWN_MAP: frozenset({initial_respawn_map_id})}
    result = saturate(
        seed, rows_by_id, order, already_owned={}, structural_refusal=structural_refusal)
    owned = set(result.newly_owned)
    enabled_by_of = {
        rid: () if result.newly_owned[rid] == 0
        else compute_enabled_by(rid, rows_by_id, seed, {r: None for r in owned})
        for rid in owned
    }
    end_state, order_dependent = compute_end_state(seed, owned, rows_by_id, enabled_by_of)

    _check_refused_pseudo_rows(pseudo_rows, structural_refusal, "INTRO", end_state)

    # R9/C3, for consistency with the chapter chain -- a no-op in practice
    # today (WHITEOUT's precondition, Switch(2) "Got Pokemon", is never
    # possible True this early: the starter choice is CH01 content). Uses
    # throwaway `owner_of`/`already_owned` dicts: INTRO's own row verdicts
    # below are built from `result.newly_owned`/`owned`, not from these, so a
    # fork that actually fired here would show up in `intro_forks`' own
    # `owned_row_ids` but not (yet) in `story.rows` -- not exercised by the
    # CH01-CH05 corpus (R13).
    intro_forks = _apply_transition_forks(
        end_state, rows_by_id, set(intro_maps),
        already_owned={}, owner_of={}, structural_refusal=structural_refusal,
        enabled_by_of=enabled_by_of, owner_label="INTRO",
    )

    map_order = [rid for rid in order if not _is_pseudo_row_id(rid)]
    pseudo_order = [rid for rid in order if _is_pseudo_row_id(rid)]

    verdicts = []
    for row_id in map_order:
        sref = structural_refusal[row_id]
        if sref is not None:
            verdicts.append(RowVerdict(
                row_id=row_id, status="refused", owner=None, stage=None,
                enabled_by=(), killed_by=(), blockers=(),
                forced=rows_by_id[row_id].forced, refusals=sref, detail=None,
            ))
        elif row_id in result.newly_owned:
            verdicts.append(RowVerdict(
                row_id=row_id, status="live", owner="INTRO",
                stage=result.newly_owned[row_id],
                enabled_by=enabled_by_of.get(row_id, ()),
                killed_by=compute_killed_by(row_id, rows_by_id, owned, seed),
                blockers=result.blockers.get(row_id, ()),
                forced=rows_by_id[row_id].forced, refusals=(), detail=None,
            ))
        else:
            undetermined = _undetermined_detail(row_id, rows_by_id, owned)
            verdicts.append(RowVerdict(
                row_id=row_id,
                status="undetermined" if undetermined is not None else "unreachable",
                owner=None, stage=None, enabled_by=(), killed_by=(), blockers=(),
                forced=rows_by_id[row_id].forced, refusals=(),
                detail=undetermined if undetermined is not None else "not live through INTRO",
            ))

    pseudo_owned: dict[str, tuple[int, tuple[str, ...]]] = {}
    common_event_verdicts = []
    for row_id in pseudo_order:
        sref = structural_refusal[row_id]
        if sref is not None:
            common_event_verdicts.append(RowVerdict(
                row_id=row_id, status="refused", owner=None, stage=None,
                enabled_by=(), killed_by=(), blockers=(),
                forced=rows_by_id[row_id].forced, refusals=sref, detail=None,
            ))
        elif row_id in result.newly_owned:
            stage = result.newly_owned[row_id]
            blockers = result.blockers.get(row_id, ())
            pseudo_owned[row_id] = (stage, blockers)
            common_event_verdicts.append(RowVerdict(
                row_id=row_id, status="live", owner="INTRO", stage=stage,
                enabled_by=enabled_by_of.get(row_id, ()),
                killed_by=compute_killed_by(row_id, rows_by_id, owned, seed),
                blockers=blockers,
                forced=rows_by_id[row_id].forced, refusals=(), detail=None,
            ))
        # Not-yet-live pseudo-rows are omitted here entirely -- they may
        # become live in a later chapter and are reported there instead
        # (ChapterStory.common_events docstring); INTRO never records them
        # as "unreachable".

    story = ChapterStory(
        chapter_id="INTRO", seed_from="<defaults>", rows=tuple(verdicts),
        end_state=_freeze_state(end_state), intro_maps=tuple(intro_maps),
        common_events=tuple(common_event_verdicts),
        order_dependent=order_dependent,
        forks=intro_forks,
    )
    return story, end_state, intro_maps, refusals, pseudo_owned


# --- chapter chain ------------------------------------------------------


def _state_key_repr(key: Key) -> str:
    if isinstance(key, Switch):
        return f"switch:{key.id}"
    if isinstance(key, Variable):
        return f"var:{key.id}"
    if isinstance(key, SelfSwitch):
        return f"self_switch:{key.map_id}/{key.event_id}/{key.letter}"
    if isinstance(key, TempSwitch):
        return f"temp_switch:{key.map_id}/{key.event_id}/{key.letter}"
    if isinstance(key, EngineKey):
        return f"engine:{key.name}"
    raise TypeError(f"unknown key {key!r}")


def _freeze_values(values: frozenset) -> tuple:
    """`VARIABLE_TOP` (FIX 2b) is not JSON-serializable and is always a
    singleton (`_union_values`'s absorbing rule) -- represent it as the
    literal string `"TOP"` rather than sorting it in among real values."""
    if VARIABLE_TOP in values:
        return ("TOP",)
    return tuple(sorted(values, key=lambda x: (isinstance(x, int), x)))


def _freeze_state(state: State) -> tuple[tuple[str, tuple], ...]:
    return tuple(sorted(
        (_state_key_repr(k), _freeze_values(v))
        for k, v in state.items()
        if not isinstance(k, TempSwitch)
    ))


def _load_common_events(build_dir: Path) -> list[dict[str, Any]]:
    return json.loads((build_dir / "common_events.json").read_text(encoding="utf-8"))


def _is_pseudo_row_id(row_id: str) -> bool:
    """True for a `common/ceNNN[/bM]` triggered-common-event pseudo-row id
    (`story_state.extract`'s module docstring) -- these never go through
    `chapter_manifest.schema.parse_row_id`, so every place that would
    otherwise call it on a row id from a mixed (map + pseudo) collection
    must check this first."""
    return row_id.startswith("common/ce")


def _pseudo_trunk_row_id(row_id: str) -> str:
    return row_id.split("/b", 1)[0]


def _check_refused_pseudo_rows(
    pseudo_rows: dict[str, RowState],
    structural_refusal: dict[str, tuple[str, ...] | None],
    chapter_id: str,
    state: State,
) -> None:
    """Triggered common events are MODELLED now (REDERIVATION_PLAN.md §16.3
    C2 ruling (e)) -- this replaces the old blanket "any triggered CE gated
    on a possible-True switch is unmodelled" guard. What remains unmodelled
    is a pseudo-row extraction refused (e.g. an unclassified condition, an
    invalid self-switch write): if ITS gating switch is possible True in
    this chapter's state, that refusal is unmodelled behaviour that is
    actually running, and stays fail-loud (CLAUDE.md §4.5) rather than
    silently skipped."""
    for row_id, row in pseudo_rows.items():
        sref = structural_refusal.get(row_id)
        if sref is None:
            continue
        trunk = pseudo_rows[_pseudo_trunk_row_id(row_id)]
        if not trunk.page_tests:
            continue  # trunk itself refused (e.g. an "s:" gating switch) -- nothing to test
        gate_test = trunk.page_tests[0]
        if possible(gate_test, state):
            raise ValueError(
                f"story_state: pseudo-row {row_id!r} (triggered common "
                f"event) is refused ({sref!r}) but its gating switch "
                f"{gate_test.key!r} is possible True in {chapter_id} -- "
                "unmodelled behaviour that is actually running (R6/C2b "
                "real-data guard)"
            )


def build_chapter_stories(
    chapter_ids: list[str],
    *,
    build_dir: Path,
    chapters_path: Path,
    winner_for: Callable[[str, tuple[str, ...]], str | None] | None = None,
) -> dict[str, ChapterStory]:
    """Models `chapter_ids` (in chain order, e.g. CH01..CH05) cumulatively.

    Returns one `ChapterStory` per requested chapter id (plus `"INTRO"`),
    each reporting only the rows on THAT chapter's own maps (§16.3 C2b
    output spec).

    `winner_for(chapter_id, writers)` is C6's seed recompute: the writer of
    an order-dependent key that chapter's concrete route visits last, or
    None where no route is known yet. Each pick narrows that chapter's end
    state, so every successor is seeded (and its liveness checked) from
    the route rather than from the join. Omitted, the model is C2's pure
    over-approximation, as before.
    """
    binding = load_binding(path=chapters_path)
    common_events = _load_common_events(build_dir)
    ref_dir = Path(__file__).resolve().parents[3] / "reference"
    switch_labels, _var_labels = load_label_tables(
        ref_dir / "uranium_switches.json", ref_dir / "uranium_variables.json")

    # Triggered-common-event pseudo-rows (REDERIVATION_PLAN.md §16.3 C2
    # ruling (e)) are extracted ONCE and are global -- they join every
    # chapter's scope (and INTRO's), never a single map's.
    pseudo_rows = extract_triggered_common_events(
        common_events, switch_labels=switch_labels)

    intro_story, intro_end_state, intro_maps, intro_refusals, intro_pseudo_owned = model_intro(
        build_dir, common_events, switch_labels, bound_map_ids=set(binding.map_ids),
        pseudo_rows=pseudo_rows)
    if intro_refusals:
        logger.info("intro chain refusals: %s", intro_refusals)

    cumulative_rows: dict[str, RowState] = dict(pseudo_rows)
    already_owned: dict[str, tuple[str, ...]] = {}  # row_id -> blockers
    owner_of: dict[str, tuple[str, int]] = {}  # row_id -> (chapter_id, stage)
    structural_refusal: dict[str, tuple[str, ...] | None] = {}
    own_map_ids_by_chapter: dict[str, set[int]] = {}
    end_state_by_chapter: dict[str, State] = {}
    order_dependent_by_chapter: dict[str, tuple[OrderDependentKey, ...]] = {}
    seed_from_by_chapter: dict[str, str] = {}
    enabled_by_by_chapter: dict[str, dict[str, tuple[tuple[str, ...], ...]]] = {}
    forks_by_chapter: dict[str, tuple[ForkReport, ...]] = {}
    # Every map id modelled so far (INTRO plus every chapter's own maps up to
    # and including the current one) -- the R9/C3 "every map in cumulative
    # scope" fallback when an engine transition's landing key is TOP.
    cumulative_map_ids: set[int] = set(intro_maps)

    # Seed pseudo-row ownership/structural-refusal from INTRO -- a pseudo-row
    # INTRO already owned is never re-derived by the chain (§16.3 C2
    # chaining paragraph, same rule as any other row).
    refusal_cache_pseudo: dict[str, tuple[str, ...] | None] = {}
    for rid in pseudo_rows:
        structural_refusal[rid] = _structural_refusal(rid, cumulative_rows, refusal_cache_pseudo)
    for rid, (stage, blockers) in intro_pseudo_owned.items():
        owner_of[rid] = ("INTRO", stage)
        already_owned[rid] = blockers

    # Pass 1: walk the chain once, growing cumulative scope and ownership.
    seed = intro_end_state
    seed_from = "INTRO"
    for chapter_id in chapter_ids:
        maps = binding.chapter(chapter_id).maps
        own_map_ids_by_chapter[chapter_id] = set(maps)
        seed_from_by_chapter[chapter_id] = seed_from
        refusal_cache: dict[str, tuple[str, ...] | None] = {}
        for map_id in maps:
            map_path = build_dir / "maps" / f"Map{map_id:03d}.json"
            map_data = json.loads(map_path.read_text(encoding="utf-8"))
            new_rows = extract_map(
                map_id, map_data, common_events=common_events, switch_labels=switch_labels)
            for rid, rs in new_rows.items():
                cumulative_rows.setdefault(rid, rs)

        order = sorted(cumulative_rows, key=row_id_sort_key)
        for rid in order:
            if rid not in structural_refusal:
                structural_refusal[rid] = _structural_refusal(rid, cumulative_rows, refusal_cache)

        result = saturate(
            seed, cumulative_rows, order,
            already_owned=already_owned, structural_refusal=structural_refusal)

        _check_refused_pseudo_rows(pseudo_rows, structural_refusal, chapter_id, result.end_state)

        for rid, stage in result.newly_owned.items():
            owner_of[rid] = (chapter_id, stage)
            already_owned[rid] = result.blockers[rid]

        owned_this_chapter = set(result.newly_owned)
        enabled_by_of = {
            rid: () if result.newly_owned[rid] == 0
            else compute_enabled_by(rid, cumulative_rows, seed, owner_of)
            for rid in owned_this_chapter
        }
        enabled_by_by_chapter[chapter_id] = enabled_by_of
        pick = (None if winner_for is None
                else functools.partial(winner_for, chapter_id))
        refined_end_state, refined_order_dependent = compute_end_state(
            seed, owned_this_chapter, cumulative_rows, enabled_by_of, pick)

        end_state_by_chapter[chapter_id] = refined_end_state
        order_dependent_by_chapter[chapter_id] = refined_order_dependent
        cumulative_map_ids |= own_map_ids_by_chapter[chapter_id]

        # R9/C3: precondition-gated engine-transition forks, run over THIS
        # chapter's own main-path end state -- after it (never before: the
        # fork must see this chapter's own newly-owned main-path rows as
        # already owned, per `already_owned` above) and strictly separate
        # from it (never folded into `refined_end_state`/`seed` -- R9 "never
        # on the main path"). `already_owned`/`owner_of` already carry this
        # chapter's own main-path ownership at this point (set right after
        # `saturate` above), so a fork can never re-attribute a main-path row.
        # The fork reads the SATURATED state (every value a key held at any
        # point in the chapter), not `refined_end_state`: a white-out before
        # CH03's Pokémon Center visit lands on the seed's respawn map, which
        # the refined end state has already overwritten (lead, C3 review).
        forks_by_chapter[chapter_id] = _apply_transition_forks(
            result.end_state, cumulative_rows, cumulative_map_ids,
            already_owned=already_owned, owner_of=owner_of,
            structural_refusal=structural_refusal, enabled_by_of=enabled_by_of,
            owner_label=chapter_id,
        )

        seed = refined_end_state
        seed_from = chapter_id

    # Pass 2: build each chapter's own report (rows on its own maps only),
    # now that ownership across the whole chain is final.
    in_scope_ids = set(cumulative_rows)
    stories: dict[str, ChapterStory] = {"INTRO": intro_story}
    for chapter_id in chapter_ids:
        own_map_ids = own_map_ids_by_chapter[chapter_id]
        chapter_seed = intro_end_state if seed_from_by_chapter[chapter_id] == "INTRO" \
            else end_state_by_chapter[seed_from_by_chapter[chapter_id]]

        verdicts: list[RowVerdict] = []
        own_row_ids = sorted(
            (
                rid for rid in cumulative_rows
                if not _is_pseudo_row_id(rid) and parse_row_id(rid).map_id in own_map_ids
            ),
            key=row_id_sort_key,
        )
        for rid in own_row_ids:
            sref = structural_refusal[rid]
            if sref is not None:
                verdicts.append(RowVerdict(
                    row_id=rid, status="refused", owner=None, stage=None,
                    enabled_by=(), killed_by=(), blockers=(),
                    forced=cumulative_rows[rid].forced, refusals=sref, detail=None,
                ))
                continue
            if rid in owner_of:
                owner_chapter, stage = owner_of[rid]
                if owner_chapter != chapter_id:
                    verdicts.append(RowVerdict(
                        row_id=rid, status="later", owner=owner_chapter, stage=None,
                        enabled_by=(), killed_by=(), blockers=(),
                        forced=cumulative_rows[rid].forced, refusals=(),
                        detail=f"later:{owner_chapter}",
                    ))
                    continue
                enabled_by = enabled_by_by_chapter[owner_chapter].get(rid, ())
                killed_by = compute_killed_by(rid, cumulative_rows, in_scope_ids, chapter_seed)
                verdicts.append(RowVerdict(
                    row_id=rid, status="live", owner=owner_chapter, stage=stage,
                    enabled_by=enabled_by, killed_by=killed_by,
                    blockers=already_owned[rid],
                    forced=cumulative_rows[rid].forced, refusals=(), detail=None,
                ))
            else:
                undetermined = _undetermined_detail(rid, cumulative_rows, set(owner_of))
                verdicts.append(RowVerdict(
                    row_id=rid,
                    status="undetermined" if undetermined is not None else "unreachable",
                    owner=None, stage=None, enabled_by=(), killed_by=(), blockers=(),
                    forced=cumulative_rows[rid].forced, refusals=(),
                    detail=undetermined if undetermined is not None else
                    f"not live through {chapter_ids[-1]}",
                ))

        # Pseudo-rows (§16.3 C2 ruling (e)) owned FIRST by this chapter --
        # a structurally-refused pseudo-row was already reported by INTRO
        # (refusal is state-independent) and an INTRO-owned live one stays
        # in INTRO's own `common_events`; neither repeats here, and a
        # pseudo-row never gets a `later`/`unreachable` verdict at all.
        common_event_verdicts: list[RowVerdict] = []
        for rid in sorted(pseudo_rows, key=row_id_sort_key):
            if rid not in owner_of or owner_of[rid][0] != chapter_id:
                continue
            _, stage = owner_of[rid]
            enabled_by = enabled_by_by_chapter[chapter_id].get(rid, ())
            killed_by = compute_killed_by(rid, cumulative_rows, in_scope_ids, chapter_seed)
            common_event_verdicts.append(RowVerdict(
                row_id=rid, status="live", owner=chapter_id, stage=stage,
                enabled_by=enabled_by, killed_by=killed_by,
                blockers=already_owned[rid],
                forced=cumulative_rows[rid].forced, refusals=(), detail=None,
            ))

        stories[chapter_id] = ChapterStory(
            chapter_id=chapter_id, seed_from=seed_from_by_chapter[chapter_id],
            rows=tuple(verdicts),
            end_state=_freeze_state(end_state_by_chapter[chapter_id]), intro_maps=None,
            common_events=tuple(common_event_verdicts),
            order_dependent=order_dependent_by_chapter[chapter_id],
            forks=forks_by_chapter[chapter_id],
        )

    return stories
