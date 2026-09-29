"""Solver precedence from page liveness (2026-09-29, operator ruling after the
plan-time liveness check of `state_arms.py`).

Two derived kinds, both static (no walk: they run before the route is solved)
and both read from the extracted row states, nothing hardcoded:

**Killer edges** (`killed_before`, solver reason `killer:<writer>-><row>`).
RMXP runs an event's highest live page, so a claimed write that makes a HIGHER
page of P's event live ends P for good (`killer_first`). For each claimed page
P, every claimed row on ANOTHER page that writes a value satisfying a test of
a higher page H of P's event -- H's other tests being implied by P's own tests
or certain in the seed -- is a killer, and P's beat must come before it: one
hard `before` edge per killer, so P precedes ALL of them (the opposite polarity
of an any-of enabler). A killer in P's own group is no edge (a template firing
p0 then p1 in one group is fine), and a write on P's own page never is one.
The re-fire beats (`_again`, `_r<n>`) don't exist yet at solve time; they are
made after the write on purpose. An `Adjust` counts only when it flips H's
test from a value P's tests allow (see `_flips`); a havoc'd key (an unparsed
write, value unknown) is not a killer, matching the walk, which leaves a TOP
state undecided.

**Havoc'd keys.** A row the extractor refused carries `havoc_keys` (a write
of unknown value). When the key is a variable and the row's page writes it
only by direct constant `122` commands (no script text names it), those
commands are read back as `Assign`/`Adjust` writes (`WriteModel`) -- the lab
starter's `+1` on var 101 is the case. A havoc left unresolved counts as an
enabler of any test (the story model's rule); a havoc, resolved or not, is
never a killer (the walk leaves a TOP state undecided, and the extractor
refused the row).

**Threshold-aware enablers** (`threshold_enabled_by`, reasons
`threshold:`/`threshold_any:`). The story model's `enabled_by` names every
writer of a key as a candidate enabler of `var >= N`, an `Adjust` or havoc
always included. A candidate that cannot satisfy the test drops out: an
`Assign` must write a satisfying value, an `Adjust` must take some reachable
value that fails the test to one that passes it, a havoc'd key never counts
(unless nothing else qualifies, then the group is left untouched). A group
that shrank moves to `threshold_enabled_by`, so the route plan shows which
edges the filter produced; an unchanged group stays in `enabled_by`.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence

from rpg2gba.beat_gen.plan import PlannedBeat
from rpg2gba.beat_gen.state_arms import FIRING_TEMPLATES
from rpg2gba.chapter_manifest.schema import parse_row_id
from rpg2gba.story_state.extract import RowState
from rpg2gba.story_state.model import VARIABLE_TOP, _apply_op, _cmp, _get, _write_satisfies
from rpg2gba.story_state.state import Adjust, Assign, Key, Test, Variable

logger = logging.getLogger(__name__)

StateOf = Callable[[str], RowState | None]
PageFor = Callable[[str], Mapping]

_OPS = {1: "+", 2: "-", 3: "*", 4: "/", 5: "%"}


class WriteModel:
    """A row's writes as the liveness edges see them: the extracted writes,
    plus each havoc'd variable read back from the page's direct `122`
    commands when that is unambiguous (module docstring)."""

    def __init__(self, state_of: StateOf, page_for: PageFor) -> None:
        self.state_of = state_of
        self._page_for = page_for
        self._cache: dict[str, tuple[tuple[Assign | Adjust, ...], frozenset[Key]]] = {}

    def _resolve(self, row_id: str) -> tuple[tuple[Assign | Adjust, ...], frozenset[Key]]:
        rs = self.state_of(row_id)
        if rs is None:
            return (), frozenset()
        writes: list[Assign | Adjust] = list(rs.writes)
        open_keys: set[Key] = set()
        for key in rs.havoc_keys:
            found = self._direct_writes(row_id, key) if isinstance(key, Variable) else None
            if found:
                writes.extend(found)
            else:
                open_keys.add(key)
        return tuple(writes), frozenset(open_keys)

    def _direct_writes(self, row_id: str, key: Variable) -> list[Assign | Adjust] | None:
        commands = self._page_for(_page_of(row_id)).get("list", ())
        found: list[Assign | Adjust] = []
        for i, cmd in enumerate(commands):
            code, params = cmd.get("code"), cmd.get("parameters", ())
            if code in (355, 655, 111) and any(
                    f"variables[{key.id}]" in str(p) or f"pbSet({key.id}" in str(p)
                    for p in params):
                return None      # a script names it: can't call the 122s the whole story
            if code != 122 or not params[0] <= key.id <= params[1]:
                continue
            if params[3] != 0:
                return None      # a variable / random operand: value unknown
            if params[2] == 0:
                found.append(Assign(key, frozenset({params[4]}), False, f"code 122 @list[{i}]", i))
            elif params[2] in _OPS:
                found.append(Adjust(key, _OPS[params[2]], params[4], False,
                                    f"code 122 @list[{i}]", i))
            else:
                return None
        return found or None

    def writes(self, row_id: str) -> tuple[Assign | Adjust, ...]:
        if row_id not in self._cache:
            self._cache[row_id] = self._resolve(row_id)
        return self._cache[row_id][0]

    def open_havoc(self, row_id: str) -> frozenset[Key]:
        if row_id not in self._cache:
            self._cache[row_id] = self._resolve(row_id)
        return self._cache[row_id][1]


def _page_of(row_id: str) -> str:
    return parse_row_id(row_id).owning_page_row_id or row_id


def base_values(key: Key, seed: Mapping, claimed: Iterable[Iterable[Assign | Adjust]]
                ) -> frozenset | None:
    """The values `key` can hold before any `Adjust` of it: the seed's, plus
    every value a claimed row `Assign`s. None when the seed is TOP."""
    values = set(_get(seed, key))
    if VARIABLE_TOP in values:
        return None
    for writes in claimed:
        for w in writes:
            if isinstance(w, Assign) and w.key == key:
                values |= w.values
    return frozenset(values)


def _flips(write: Assign | Adjust, test: Test, base: frozenset | None,
           allowed: Collection[Test] = ()) -> bool:
    """Can `write` take `test.key` from a value failing `test` to one passing
    it? `Assign`: any written value passes. `Adjust`: some `base` value that
    fails `test` (and satisfies `allowed`, the tests holding on the key at the
    time -- a killed page's own) is adjusted into a passing one; an unknown
    `base` (TOP seed) can't rule it out."""
    if write.key != test.key:
        return False
    if isinstance(write, Assign):
        return any(_cmp(test.op, v, test.value) for v in write.values)
    if base is None:
        return True
    return any(not _cmp(test.op, b, test.value)
               and all(_cmp(t.op, b, t.value) for t in allowed if t.key == test.key)
               and _cmp(test.op, _apply_op(write.op, b, write.amount), test.value)
               for b in base)


def _ancestor_tests(row_id: str, state_of: StateOf) -> list[Test]:
    """Every test gating `row_id` (`model._ancestor_tests`, over `state_of`)."""
    row = state_of(row_id)
    if row is None:
        return []
    tests = list(row.page_tests)
    cur: RowState | None = row
    while cur is not None:
        if cur.arm_guard is not None:
            tests.extend(cur.arm_guard.tests)
        cur = state_of(cur.parent_row_id) if cur.parent_row_id is not None else None
    return tests


def _qualifies(writes: Iterable[Assign | Adjust], test: Test, base: frozenset | None) -> bool:
    return any(_flips(w, test, base) for w in writes)


def split_threshold_enablers(
    enabled_by: Mapping[str, tuple[tuple[str, ...], ...]], *, wm: WriteModel,
    seed: Mapping, claimed_rows: Collection[str],
) -> tuple[dict[str, tuple[tuple[str, ...], ...]], dict[str, tuple[tuple[str, ...], ...]]]:
    """(the `enabled_by` groups left as they were, the groups that shrank --
    already filtered). A group belongs to the row's test its every candidate
    can satisfy (`model._write_satisfies` or a havoc on the key); it is
    filtered by the candidates that really can (module docstring)."""
    state_of = wm.state_of
    claimed = [wm.writes(rid) for rid in sorted(claimed_rows)]
    kept: dict[str, tuple[tuple[str, ...], ...]] = {}
    shrunk: dict[str, tuple[tuple[str, ...], ...]] = {}
    for row_id, groups in enabled_by.items():
        tests = _ancestor_tests(row_id, state_of)
        keep_groups: list[tuple[str, ...]] = []
        shrunk_groups: list[tuple[str, ...]] = []
        for group in groups:
            states = {w: state_of(w) for w in group}
            matching = [t for t in tests if all(
                states[w] is not None and (
                    t.key in wm.open_havoc(w) or any(_write_satisfies(x, t) for x in wm.writes(w)))
                for w in group)]
            if not matching or any(rs is None for rs in states.values()):
                keep_groups.append(group)
                continue
            bases = {t.key: base_values(t.key, seed, claimed) for t in matching}
            real = tuple(w for w in group
                         if any(t.key in wm.open_havoc(w) or _qualifies(wm.writes(w), t, bases[t.key])
                                for t in matching))
            if real == group:
                keep_groups.append(group)
            elif not real:
                logger.warning("threshold: no candidate of %s's enabler group %s can satisfy "
                               "its test; group left as it was", row_id, group)
                keep_groups.append(group)
            else:
                shrunk_groups.append(real)
        if keep_groups:
            kept[row_id] = tuple(keep_groups)
        if shrunk_groups:
            shrunk[row_id] = tuple(shrunk_groups)
    return kept, shrunk


def _implied(test: Test, given: Sequence[Test]) -> bool:
    """`test` holds whenever every `given` test on its key does (checked over
    the values either names and their neighbours; False when none is given)."""
    same = [g for g in given if g.key == test.key]
    if not same:
        return False
    if isinstance(test.value, bool):
        witnesses: set = {False, True}
    else:
        witnesses = {t.value + d for t in (*same, test) for d in (-1, 0, 1)}
    live = [v for v in witnesses if all(_cmp(g.op, v, g.value) for g in same)]
    return bool(live) and all(_cmp(test.op, v, test.value) for v in live)


def killed_before(
    beats: Sequence[PlannedBeat], *, wm: WriteModel, seed: Mapping,
    claimed_rows: Collection[str] | None = None,
) -> dict[str, tuple[str, ...]]:
    """claimed page row -> the claimed rows whose write makes a higher page of
    its event live and so must come after it (module docstring). One
    representative row per (beat, page) so a page walked in several groups
    (choice arms, facing arms) is held in each. Rows of `PlannedBeat`s whose
    template doesn't fire pages have none."""
    claimed_rows = (claimed_rows if claimed_rows is not None
                    else {r for b in beats for r in b.rows})
    state_of = wm.state_of
    # Only the writes the walk itself sees (`RowState.writes`): a havoc read
    # back from the page's commands is enabler evidence, not a killer.
    claimed = [(rid, rs.writes) for rid in sorted(claimed_rows)
               if (rs := state_of(rid)) is not None]
    claimed_writes = [ws for _rid, ws in claimed]
    group_of = {r: b.group for b in beats for r in b.rows}
    out: dict[str, tuple[str, ...]] = {}
    for beat in beats:
        if beat.template not in FIRING_TEMPLATES:
            continue
        seen: set[str] = set()
        for rid in beat.rows:
            page = _page_of(rid)
            if page in seen:
                continue
            seen.add(page)
            page_state = state_of(page)
            if page_state is None or page_state.page_refusals:
                continue
            pages = page_state.event_page_row_ids
            if page not in pages:
                continue
            killers: set[str] = set()
            for higher in pages[pages.index(page) + 1:]:
                hs = state_of(higher)
                if hs is None or hs.page_refusals:
                    continue
                for t in hs.page_tests:
                    others = [o for o in hs.page_tests if o != t]
                    if not all(_implied(o, page_state.page_tests)
                               or _holds_in_seed(o, seed) for o in others):
                        continue
                    base = base_values(t.key, seed, claimed_writes)
                    for wid, ws in claimed:
                        if (_page_of(wid) == page or group_of.get(wid) == beat.group
                                or wid.startswith(f"{page}/")):
                            continue
                        if any(_flips(w, t, base, page_state.page_tests) for w in ws):
                            killers.add(wid)
            if killers:
                out[rid] = tuple(sorted(killers))
    return out


def _holds_in_seed(test: Test, seed: Mapping) -> bool:
    values = _get(seed, test.key)
    return VARIABLE_TOP not in values and bool(values) and all(
        _cmp(test.op, v, test.value) for v in values)
