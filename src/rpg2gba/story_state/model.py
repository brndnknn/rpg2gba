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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
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
from rpg2gba.story_state.scope_search import (
    ComputedScope,
    named_write_targets,
    writes_exhaustively_named,
    run_scope,
    self_contained_counters,
    witness_citations,
    writes_from_result,
)
from rpg2gba.story_state.state import (
    RESPAWN_MAP,
    Adjust,
    Assign,
    BagHas,
    EngineKey,
    Key,
    Refusal,
    SelfSwitch,
    Switch,
    TempSwitch,
    Test,
    Variable,
    Write,
)
from rpg2gba.story_state.losable import losable_battle_evidence
from rpg2gba.story_state.transitions import TRANSITIONS, EngineTransition

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
    # C8 stage 4: for a row whose writes the interpreter resolved, one
    # citation per (key, value) -- `(key_repr, value_repr, choice labels)`,
    # the input vector that produced it. Empty for a row extraction folded
    # to static writes without ever running a search.
    witnesses: tuple[tuple[str, str, tuple[str, ...]], ...] = ()


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
_SOFT_WRITE_REFUSAL_CODES = frozenset({
    "unparsed_state_write",
    # C8 stage 4: the interpreter's write-level refusals. Every one of these
    # means "this row writes SOMETHING we cannot put a value to" -- the same
    # claim `unparsed_state_write` made, now said precisely -- and every one
    # is raised with `havoc_global`, so the row's effect is still carried.
    # They are soft for FIX 2a's reason: a row excluded from saturation
    # starves everything downstream of it, which is a far worse answer than
    # carrying it as possibly-live. The interpreter's STRUCTURAL failures
    # (`search_ce_cycle`, `search_missing_common_event`,
    # `search_malformed_write`) are deliberately absent -- they are the
    # exact analogues of the hard codes above and stay hard.
    "computed_row_top_read",
    "computed_row_self_reference",
    "ruby_parse_error",
    "ruby_unknown_call",
    "ruby_unknown_attribute",
    "ruby_type_error",
    "ruby_unsupported_node",
    "party_model",
    "no_port",
    "search_cap",
    "search_loop",
    "search_ce_branches",
    "search_type_error",
    "search_inline_choice",
    "search_nonscalar_value",
    "search_empty_domain",
    "search_unknown_read",
})


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
            if guard is not None and guard.outcome is not None and guard.outcome.kind == "dead":
                result = (False, ())  # contradicts a static predicate (ruling 14)
            elif not all(possible(t, state) for t in tests):
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


# --- the resolver fixpoint around saturation ------------------------------

# A computed row's writes are re-derived once per pass against the previous
# pass's saturated value sets. Value sets only ever grow (saturation is a
# flow-insensitive union) and are capped by `MAX_VARIABLE_VALUES`, so this
# terminates well inside the bound; the bound exists to fail loud
# (CLAUDE.md §4.5) if some future non-monotone resolution starts oscillating
# instead of quietly spinning.
MAX_RESOLVER_PASSES = 8

#: The read domain handed to a self-contained counter (C9 ruling 13): one
#: arbitrary value, because its value reaches nothing but itself.
_COUNTER_PLACEHOLDER = frozenset({0})


_ADJUST_OPS = {1: "+", 2: "-", 3: "*", 4: "/", 5: "%"}


def _direct_counter_writes(scope: ComputedScope, key: Key) -> list[Write] | None:
    """`key`'s writes read straight off the scope's `122` commands, or None
    unless that is the whole story: `key` is a Variable, every touch of it is
    a constant-operand `122` at the scope's top indent (unconditional), no
    `111` tests it, and no script, conditional or inlined common event names
    it."""
    if not isinstance(key, Variable) or not scope.commands:
        return None
    needles = (f"variables[{key.id}]", f"pbGet({key.id})", f"pbSet({key.id}")
    top = scope.commands[0].get("indent", 0)
    found: list[Write] = []
    for cmd in scope.commands:
        code, params = cmd.get("code"), cmd.get("parameters") or []
        if any(n in str(p) for p in params for n in needles):
            return None
        if code == 111 and params and params[0] == 1 and len(params) > 1 and params[1] == key.id:
            return None
        if code == 117 and params:
            body = scope.common_events_by_id.get(params[0], {})
            if any(n in json.dumps(body) for n in needles) or _ce_writes_var(body, key.id):
                return None
        if code != 122 or not params[0] <= key.id <= params[1]:
            continue
        if cmd.get("indent", 0) != top or params[3] != 0:
            return None
        list_index = scope.index_of.get(id(cmd), -1)
        source = f"code 122 @list[{list_index}]"
        if params[2] == 0:
            found.append(Assign(key, frozenset({params[4]}), scope.conditional, source, list_index))
        elif params[2] in _ADJUST_OPS:
            found.append(Adjust(key, _ADJUST_OPS[params[2]], params[4], scope.conditional,
                                source, list_index))
        else:
            return None
    return found or None


def _self_retiring_counters(
    row: RowState, rows_by_id: Mapping[str, RowState], seed: State,
) -> frozenset[Key]:
    """Counters whose `122` writes are this row's exact story because the row
    can fire only once (ROM run 34): its only touch of K is a constant add
    `K += c`, a higher page of its own event is gated on nothing but
    `K >= t`, every value K starts from reaches `t` after `+c`, and every
    other writer of K in the chain assigns a value `>= t`. The firing then
    hands the event to that page for good -- the rival scene's `var 101 += 1`
    with page 1 on `var101 >= 1`. A repeatable counter (map031/ev014's
    99-talks Magikarp, one page) fails the test and stays TOP."""
    if row.computed is None:
        return frozenset()
    page_row_id = parse_row_id(row.row_id).owning_page_row_id or row.row_id
    if page_row_id not in row.event_page_row_ids:
        return frozenset()
    higher = row.event_page_row_ids[row.event_page_row_ids.index(page_row_id) + 1:]
    exact: set[Key] = set()
    for page_id in higher:
        page = rows_by_id.get(page_id)
        if page is None or len(page.page_tests) != 1:
            continue
        (test,) = page.page_tests
        if not isinstance(test.key, Variable) or test.op != ">=":
            continue
        key, threshold = test.key, test.value
        direct = _direct_counter_writes(row.computed, key)
        if not direct or any(not (isinstance(w, Adjust) and w.op == "+") for w in direct):
            continue
        step = sum(w.amount for w in direct)
        start = _get(seed, key)
        if VARIABLE_TOP in start or any(v + step < threshold for v in start):
            continue
        others_ok = all(
            isinstance(w, Assign) and all(v >= threshold for v in w.values)
            for other in rows_by_id.values() if other.row_id != row.row_id
            for w in other.writes if w.key == key
        ) and not any(
            key in other.havoc_keys
            # an unparsed row could write anything; a computed row's
            # placeholder havoc is re-derived every resolver pass
            or (other.havoc_global and other.computed is None)
            for other in rows_by_id.values() if other.row_id != row.row_id
        )
        if others_ok:
            exact.add(key)
    exact |= _self_switch_retired_counters(row, rows_by_id, higher, seed)
    return frozenset(exact)


def _self_switch_retired_counters(
    row: RowState, rows_by_id: Mapping[str, RowState], higher: Sequence[str], seed: State,
) -> frozenset[Key]:
    """Constant `K += c` counters on a row that retires its own page by self
    switch (2026-10-15, CH08): the row turns self switch L ON at or above the
    indent of every `122` add to K, and a higher page of its event is gated on
    nothing but L, so the page -- and the add -- fires once. CH06's gym-leader
    reward arm (map042/ev003/p0/b1: `123 A`, `var 101 += 1`, page 1 on A) was
    widening the quest log to TOP for every later chapter."""
    assert row.computed is not None
    commands = row.computed.commands
    parsed = parse_row_id(row.row_id)
    retiring: set[str] = set()
    for page_id in higher:
        page = rows_by_id.get(page_id)
        if page is None or len(page.page_tests) != 1:
            continue
        (test,) = page.page_tests
        if (isinstance(test.key, SelfSwitch) and test.op == "==" and test.value is True
                and (test.key.map_id, test.key.event_id) == (parsed.map_id, parsed.event_id)):
            retiring.add(test.key.letter)
    if not retiring:
        return frozenset()
    set_at = [c.get("indent", 0) for c in commands
              if c.get("code") == 123 and (c.get("parameters") or [None, 1])[0] in retiring
              and (c.get("parameters") or [None, 1])[1] == 0]
    if not set_at:
        return frozenset()
    exact: set[Key] = set()
    for key in {Variable(c["parameters"][0]) for c in commands
                if c.get("code") == 122 and c.get("parameters")
                and c["parameters"][0] == c["parameters"][1]}:
        direct = _direct_counter_writes(row.computed, key)
        if not direct or any(not (isinstance(w, Adjust) and w.op == "+") for w in direct):
            continue
        add_indents = [c.get("indent", 0) for c in commands if c.get("code") == 122
                       and (c.get("parameters") or [None])[0] == key.id]
        if VARIABLE_TOP in _get(seed, key) or min(set_at) > min(add_indents):
            continue
        exact.add(key)
    return frozenset(exact)


def _ce_writes_var(body: Mapping[str, Any], var_id: int) -> bool:
    return any(
        cmd.get("code") == 122 and (cmd.get("parameters") or [0, -1])[0] <= var_id
        <= (cmd.get("parameters") or [0, -1])[1]
        for cmd in body.get("list", ()))


def _bag_carry(row: RowState) -> tuple[tuple[Write, ...], tuple[Key, ...]]:
    """The key-item bag writes/havocs extraction attached to `row` (they come
    from script TEXT, not from the interpreter run a computed row defers, so
    re-resolution must not drop them)."""
    return (
        tuple(w for w in row.writes if isinstance(w.key, BagHas)),
        tuple(k for k in row.havoc_keys if isinstance(k, BagHas)),
    )


def _resolve_computed_row(
    row: RowState, state: State, exact_counters: frozenset[Key] = frozenset(),
) -> RowState:
    """One computed row re-run against `state`, as an ordinary `RowState`.

    A row is *computed* when its own scope reads state it does not itself
    write, so extraction could not name its writes (REDERIVATION_PLAN.md
    §16.3, "Stages 3-4 refined"). Here the read domain is the saturated
    value set, so the same interpreter run yields concrete writes.

    Reading a TOP key refuses by name (`computed_row_top_read`): "could be
    anything" cannot be enumerated, so the row keeps its havoc rather than
    pretending to a value. The placeholder `unparsed_state_write` refusal
    and `havoc_global` that extraction attaches to every computed row are
    dropped here -- resolution is what they were standing in for.
    """
    assert row.computed is not None
    counters = self_contained_counters(
        row.computed.commands, row.computed.common_events_by_id)

    def read_domain(key: Key) -> frozenset | None:
        if key in counters:
            # Its value reaches nothing but itself, so any one value does.
            return _COUNTER_PLACEHOLDER
        values = _get(state, key)
        if VARIABLE_TOP in values:
            return None  # the only None this resolver ever returns
        return values

    result = run_scope(row.computed, read_domain)
    bag_writes, bag_havoc = _bag_carry(row)
    carried = tuple(r for r in row.refusals if r.code != "unparsed_state_write")

    if result.refusal is not None:
        code = result.refusal.code
        if code == "search_unknown_read":
            # `read_domain` answers every key except a TOP one.
            code = "computed_row_top_read"
        named = named_write_targets(
            row.computed.commands,
            map_id=row.computed.map_id, event_id=row.computed.event_id,
        )
        # 2026-10-15: same exhaustiveness test as extraction's refusal path
        # (`writes_exhaustively_named`) -- a row that provably writes only
        # what it names havocs only that, not everything.
        exhaustive = writes_exhaustively_named(
            row.computed.commands,
            map_id=row.computed.map_id, event_id=row.computed.event_id,
        )
        return replace(
            row,
            refusals=carried + (Refusal(code, f"{row.row_id}: {result.refusal.detail}"),),
            havoc_keys=tuple(named) + bag_havoc,
            havoc_global=not named and not exhaustive,
        )

    writes, nonscalar = writes_from_result(
        result, conditional=row.computed.conditional,
        source_prefix=f"resolved {row.row_id}",
    )
    # A self-contained counter's written values came from the placeholder,
    # not from the game: drop them and mark the counter "could be anything".
    # Unless the counter is nothing but constant `122`s: then those writes
    # are its exact story (`_direct_counter_writes`; ROM run 34 -- the rival
    # scene's `var 101 += 1` as TOP put a CH06 page into CH01).
    writes = tuple(w for w in writes if w.key not in counters)
    counter_havoc_keys: list[Key] = []
    for key in sorted((k for k in result.values if k in counters), key=repr):
        direct = _direct_counter_writes(row.computed, key) if key in exact_counters else None
        if direct is None:
            counter_havoc_keys.append(key)
        else:
            writes += tuple(direct)
    counter_havoc = tuple(counter_havoc_keys)

    # A key this row both READS and WRITES is a counter: its new value is a
    # function of its own old one. Re-running it against a saturated (union)
    # value set feeds last pass's values straight back in, so the set grows
    # every pass -- an ascending chain that ends at the blowup guard, never
    # at a fixpoint (measured: `map050/ev019/p0`'s Variable(101)). A
    # counter's true may-value is unbounded, i.e. TOP, and every other write
    # this row makes was derived from a now-TOP read, so none of them can be
    # trusted either: the whole row widens. This is exactly the standing it
    # had before C8 (an `unparsed_state_write` with havoc), now named.
    # A counter nothing else reads (`self_contained_counters`) is the
    # exception and was already handled above (C9 ruling 13).
    self_referential = sorted(
        (k for k in result.values if k in result.reads and k not in counters), key=repr)
    # Unless the counter is nothing but constant `122`s the row's own flow
    # never tests: then it IS those writes (an `Adjust` the saturation applies
    # once per row), and nothing else the row wrote depended on it. Measured:
    # `map050/ev019/p0`'s `var 101 += 1` -- widening it to TOP made every
    # `var 101 >= N` page possibly live in CH01 (ROM run 34, PROJECT_TODO #116).
    recovered: list[Write] = []
    for key in self_referential:
        direct = _direct_counter_writes(row.computed, key) if key in exact_counters else None
        if direct is None:
            break
        recovered.extend(direct)
    else:
        if self_referential:
            recovered_keys = set(self_referential)
            writes = tuple(w for w in writes if w.key not in recovered_keys) + tuple(recovered)
            self_referential = []
    if self_referential:
        return replace(
            row,
            writes=bag_writes,
            refusals=carried + (Refusal(
                "computed_row_self_reference",
                f"{row.row_id}: {', '.join(repr(k) for k in self_referential)} "
                f"read and written by this row -- a counter, widened to TOP",
            ),),
            havoc_keys=tuple(sorted(set(result.values) | set(bag_havoc), key=repr)),
            havoc_global=True,
        )

    return replace(
        row,
        writes=writes + tuple(w for w in bag_writes if w not in writes),
        refusals=carried,
        witnesses=witness_citations(result),
        havoc_global=False,
        havoc_keys=tuple(sorted(
            set(nonscalar) | set(counter_havoc) | set(bag_havoc), key=repr)),
    )


def _resolution_signature(row: RowState) -> tuple:
    """The part of a resolved row saturation actually reads -- the fixpoint's
    convergence test (witnesses and other citations are excluded)."""
    return (
        tuple(sorted(row.writes, key=repr)),
        tuple(sorted((r.code, r.detail) for r in row.refusals)),
        tuple(sorted(row.havoc_keys, key=repr)),
        row.havoc_global,
    )


def _attach_witnesses(
    verdicts: list[RowVerdict], rows_by_id: dict[str, RowState],
) -> list[RowVerdict]:
    """Copies each row's resolved-write citations onto its verdict, so the
    report carries the input vector behind every derived value (C8 stage 4).
    """
    out: list[RowVerdict] = []
    for verdict in verdicts:
        row = rows_by_id.get(verdict.row_id)
        witnesses = row.witnesses if row is not None else ()
        out.append(replace(verdict, witnesses=witnesses) if witnesses else verdict)
    return out


def resolve_computed_rows(
    seed: State,
    rows_by_id: dict[str, RowState],
    order: list[str],
    *,
    already_owned: dict[str, tuple[str, ...]],
    structural_refusal: dict[str, tuple[str, ...] | None],
) -> dict[str, RowState]:
    """`rows_by_id` with every live computed row resolved to real writes.

    The fixpoint the plan calls for (REDERIVATION_PLAN.md §16.3, "Stages 3-4
    refined"): saturate, re-resolve every computed row this chapter newly
    owns against the resulting end state, and repeat until the resolved
    writes stop changing. Sound because saturation's value sets are a
    flow-insensitive union that only grows, so each pass's read domain is a
    superset of the last's.

    Rows an earlier chapter already owns are left alone -- their writes are
    folded into `seed` and belong to that chapter's own report.
    """
    computed_ids = [
        rid for rid in order
        if rows_by_id[rid].computed is not None and rid not in already_owned
    ]
    if not computed_ids:
        return rows_by_id

    working = dict(rows_by_id)
    # A row that RESOLVED TO A REFUSAL is settled: a refusal is the top of
    # this lattice, and re-running it can only oscillate (widening a key to
    # TOP makes the next pass refuse on reading it, which drops the havoc,
    # which lets it resolve again -- measured on `map050/ev019/p0`). Only
    # rows that resolved to concrete writes are re-run as the state grows.
    settled: set[str] = set()
    for _ in range(MAX_RESOLVER_PASSES):
        result = saturate(
            seed, working, order,
            already_owned=already_owned, structural_refusal=structural_refusal)
        changed = False
        for rid in computed_ids:
            if rid not in result.newly_owned or rid in settled:
                continue  # not live at all, or already at the top
            resolved = _resolve_computed_row(
                rows_by_id[rid], result.end_state,
                _self_retiring_counters(rows_by_id[rid], working, seed))
            if any(r.code.startswith("computed_row_") for r in resolved.refusals):
                settled.add(rid)
            # Compare only what saturation consumes. A witness trace cites
            # the read values behind a write, so it keeps changing as the
            # read domain grows even after the writes themselves have
            # settled -- comparing whole rows would never converge.
            if _resolution_signature(resolved) != _resolution_signature(working[rid]):
                working[rid] = resolved
                changed = True
        if not changed:
            return working

    raise RuntimeError(
        f"resolver did not converge in {MAX_RESOLVER_PASSES} passes; "
        f"computed rows: {sorted(computed_ids)}"
    )


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


def _stripped_map_events() -> set[tuple[int, int]]:
    """`strip_list.json`'s map events (their battles never reach the ROM)."""
    from rpg2gba.conversion_agent.orchestrator import load_map_event_strips

    return set(load_map_event_strips(Path(__file__).resolve().parents[3] / "reference"))


def _fork_enabled_by(
    transition: EngineTransition,
    row_id: str,
    rows_by_id: dict[str, RowState],
    seed: State,
    owner_of: dict[str, tuple[str, int]],
) -> tuple[tuple[str, ...], ...]:
    """See `_apply_transition_forks`. Same group shape as
    `compute_enabled_by`: every group must hold, any row in a group will do."""
    tests = list(transition.precondition)
    if not _is_pseudo_row_id(row_id):
        tests.append(Test(key=transition.lands_on, op="==", value=parse_row_id(row_id).map_id))
    groups: list[tuple[str, ...]] = [(f"engine:{transition.name}",)]
    for test in tests:
        if certain(test, seed):
            continue
        writers = tuple(sorted(
            r for r in owner_of
            if r in rows_by_id and any(_write_satisfies(w, test) for w in rows_by_id[r].writes)))
        if writers:
            groups.append(writers)
    return tuple(groups)


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
    losable_battle: bool,
    seed: State,
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

    `losable_battle` says whether this chapter's own maps hold a battle that
    can white out (`losable.losable_battle_evidence`); a transition with
    `requires_losable_battle` is skipped without one (ruling 15).

    A fork-owned row's `enabled_by` is the `engine:<name>` marker group
    followed by the real enablers (ruling 16): for each precondition test,
    and for "the respawn anchor is this row's map", that `seed` (the
    chapter's start state) doesn't already satisfy, the group of owned rows
    whose writes do -- the starter choice for Got Pokemon, the Center's
    `pbSetPokemonCenter` for a landing it moved the anchor to.
    """
    reports: list[ForkReport] = []
    for transition in TRANSITIONS:
        if transition.requires_losable_battle and not losable_battle:
            continue
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
            enabled_by_of[rid] = _fork_enabled_by(
                transition, rid, rows_by_id, seed, owner_of)

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
    rows_by_id = resolve_computed_rows(
        seed, rows_by_id, order, already_owned={}, structural_refusal=structural_refusal)
    # Resolution replaces a computed row's placeholder refusal with whatever
    # the interpreter actually concluded, so the structural view has to be
    # taken again -- it is what the verdicts below report.
    refusal_cache = {}
    structural_refusal = {rid: _structural_refusal(rid, rows_by_id, refusal_cache) for rid in order}
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
        losable_battle=bool(losable_battle_evidence(
            {m for m in intro_maps if (maps_dir / f"Map{m:03d}.json").exists()},
            build_dir, _stripped_map_events())),
        seed=seed,
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

    verdicts = _attach_witnesses(verdicts, rows_by_id)
    common_event_verdicts = _attach_witnesses(common_event_verdicts, rows_by_id)
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
    if isinstance(key, BagHas):
        return f"bag:{key.item}"
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
    resolved_out: dict[str, RowState] | None = None,
    seed_out: dict[str, State] | None = None,
    deferred_for: Callable[[str], frozenset[str]] | None = None,
    walked_for: Callable[[str], frozenset[str] | None] | None = None,
) -> dict[str, ChapterStory]:
    """Models `chapter_ids` (in chain order, e.g. CH01..CH05) cumulatively.

    `resolved_out`, if given, is filled with every computed row on each
    chapter's own maps as resolved in that chapter's pass -- the row state
    the verdicts were built from. `beat_floor` needs it: extraction alone
    leaves a computed row's placeholder refusal in place. `seed_out`, if
    given, is filled with each chapter's seed state (its predecessor's
    refined end state, INTRO's for the first) -- where `beat_gen/state_arms.py`
    starts its walk-order simulation (ruling 19).

    Returns one `ChapterStory` per requested chapter id (plus `"INTRO"`),
    each reporting only the rows on THAT chapter's own maps (§16.3 C2b
    output spec).

    `winner_for(chapter_id, writers)` is C6's seed recompute: the writer of
    an order-dependent key that chapter's concrete route visits last, or
    None where no route is known yet. Each pick narrows that chapter's end
    state, so every successor is seeded (and its liveness checked) from
    the route rather than from the join. Omitted, the model is C2's pure
    over-approximation, as before.

    `deferred_for(chapter_id)` is the "re-offer deferred rows" ruling
    (2026-10-14): the row ids that chapter's generated suite did NOT walk
    (geographic `later`, or capability-blocked). Such a row is hidden from
    that chapter's saturation -- never owned by it, its writes never in its
    end state -- and stays hidden from every later chapter whose own maps
    lack its map, until the first chapter that has the map (and can make it
    live) owns it. Never consulted for the last chapter (the one being
    generated has no module). Omitted, ownership is first-live-chapter as
    before.

    `walked_for(chapter_id)` (2026-10-15, consulted only with `deferred_for`):
    every row id that chapter's suite claims or lists, or None. A not-yet-owned
    row on a map outside that chapter's own maps and outside this set is
    treated as deferred by it -- the chapter made it live but never walked it
    (CH06's gym makes the Moki lab scene live; CH08 walks it).
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

    stripped = _stripped_map_events()

    # Rows an earlier chapter's suite deferred and no chapter has yet picked up.
    pending_deferred: set[str] = set()

    # Pass 1: walk the chain once, growing cumulative scope and ownership.
    seed = intro_end_state
    seed_from = "INTRO"
    for chapter_id in chapter_ids:
        maps = binding.chapter(chapter_id).maps
        own_map_ids_by_chapter[chapter_id] = set(maps)
        seed_from_by_chapter[chapter_id] = seed_from
        if seed_out is not None:
            seed_out[chapter_id] = dict(seed)
        refusal_cache: dict[str, tuple[str, ...] | None] = {}
        for map_id in maps:
            map_path = build_dir / "maps" / f"Map{map_id:03d}.json"
            map_data = json.loads(map_path.read_text(encoding="utf-8"))
            new_rows = extract_map(
                map_id, map_data, common_events=common_events, switch_labels=switch_labels)
            for rid, rs in new_rows.items():
                cumulative_rows.setdefault(rid, rs)

        order = sorted(cumulative_rows, key=row_id_sort_key)
        deferred_here: frozenset[str] = frozenset()
        hidden: set[str] = set()
        if deferred_for is not None:
            if chapter_id != chapter_ids[-1]:
                deferred_here = frozenset(deferred_for(chapter_id))
            own_maps = own_map_ids_by_chapter[chapter_id]
            hidden = set(deferred_here) | {
                rid for rid in pending_deferred
                if rid in cumulative_rows and not _is_pseudo_row_id(rid)
                and parse_row_id(rid).map_id not in own_maps}
            # 2026-10-15 (CH08): a row on another chapter's map this chapter's
            # suite never mentions was not walked here, so it is not this
            # chapter's to own; it waits like a deferred row.
            walked = walked_for(chapter_id) if walked_for is not None else None
            if walked is not None:
                unwalked = {
                    rid for rid in cumulative_rows
                    if not _is_pseudo_row_id(rid) and rid not in already_owned
                    and parse_row_id(rid).map_id not in own_maps and rid not in walked}
                hidden |= unwalked
                deferred_here = deferred_here | frozenset(unwalked)
        for rid in order:
            if rid not in structural_refusal:
                structural_refusal[rid] = _structural_refusal(rid, cumulative_rows, refusal_cache)

        sat_order = [rid for rid in order if rid not in hidden] if hidden else order
        cumulative_rows.update(resolve_computed_rows(
            seed, cumulative_rows, sat_order,
            already_owned=already_owned, structural_refusal=structural_refusal))
        if resolved_out is not None:
            resolved_out.update({
                rid: rs for rid, rs in cumulative_rows.items()
                if rs.computed is not None and not _is_pseudo_row_id(rid)
                and parse_row_id(rid).map_id in own_map_ids_by_chapter[chapter_id]})
        # See `model_intro`: resolution changes what a computed row refuses,
        # and the verdicts below report the structural view, so retake it.
        refusal_cache = {}
        for rid in order:
            structural_refusal[rid] = _structural_refusal(rid, cumulative_rows, refusal_cache)
        result = saturate(
            seed, cumulative_rows, sat_order,
            already_owned=already_owned, structural_refusal=structural_refusal)
        if deferred_for is not None:
            pending_deferred = (pending_deferred | deferred_here) - set(result.newly_owned)

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
            losable_battle=bool(losable_battle_evidence(
                own_map_ids_by_chapter[chapter_id], build_dir, stripped)),
            seed=seed,
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

        verdicts = _attach_witnesses(verdicts, cumulative_rows)
        common_event_verdicts = _attach_witnesses(common_event_verdicts, cumulative_rows)
        stories[chapter_id] = ChapterStory(
            chapter_id=chapter_id, seed_from=seed_from_by_chapter[chapter_id],
            rows=tuple(verdicts),
            end_state=_freeze_state(end_state_by_chapter[chapter_id]), intro_maps=None,
            common_events=tuple(common_event_verdicts),
            order_dependent=order_dependent_by_chapter[chapter_id],
            forks=forks_by_chapter[chapter_id],
        )

    return stories
