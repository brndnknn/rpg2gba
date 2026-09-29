"""Which cells the player can stand on while a coord-trigger guard is live, and
the ordering that follows (the lab guard, 2026-09-29 ROM run 19).

`never_fires.py` proves which touch pages can't fire. The same guard walls
also decide where an ORDINARY beat can be approached from: the Professor's lab
guard (`map050/ev002` page 0) pushes the player back up whenever they step onto
row y=16, and the arrival scene leaves them north of it, so the strip south of
that row -- where two signs stand -- can't be reached before the starter turns
the guard's page off. The route solver ignored that and ordered the signs
first; the ROM run stopped at "walk_to(11, 18) interrupted by a locked-field
scene at (11, 16)".

This module reuses `never_fires._Walk` (non-strict: what it can't decide is
passed through as reachable, so a constraint is only ever raised on a cell the
walk positively can't reach) to answer, per guard page P of a map: from a
story state in which P is the live page, which cells can the player stand on
while P is still live (`GuardReach.live_cells`), and which in any state the
walk reaches (`any_cells`). A guard page P is "live" only while it is the
highest page of its event whose conditions hold; the walk never returns to a
P-live state once it has left one (story progress is monotone).

`apply_guard_reach` then reads each located beat's approach cells against
that:

- some cells reachable while P is live, some not -> the approach candidates
  are RESTRICTED to the reachable ones (no ordering needed: the beat can be
  walked from a cell that works now);
- none reachable while P is live, but reachable once it stops -> the beat is
  ordered after a claimed row that stops P being live (`killed_by` of P's row:
  a write satisfying a higher page of P's event, or failing P's own
  condition). Several claimed writers become an any-of at the solver;
- none reachable at all -> not constrained (the walk is not proof the beat is
  unreachable), logged at WARNING;
- an ordering that can't exist (no claimed writer, only the beat's own group
  writes it, or the solved route puts the beat first) -> `GuardOrderError`.

A beat of any guard event on the map is left alone: it fires by stepping onto
the wall, so its cells are the wall's own.
"""
from __future__ import annotations

import dataclasses
import itertools
import logging
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field

from rpg2gba.beat_gen.never_fires import (
    _MAX_STATES,
    Cell,
    MapFacts,
    _displaced,
    _domain,
    _live_page,
    _pages,
    _Unproven,
    _Walk,
    _holds,
)
from rpg2gba.chapter_manifest.schema import parse_row_id
from rpg2gba.routing.locations import BeatLocationRecord
from rpg2gba.story_state.extract import RowState
from rpg2gba.story_state.model import VARIABLE_TOP
from rpg2gba.story_state.state import Assign, Key, SelfSwitch, TempSwitch, Test

logger = logging.getLogger(__name__)


class GuardOrderError(ValueError):
    """A beat behind a live guard can't be ordered after anything that ends it."""


@dataclass(frozen=True)
class GuardReach:
    """One guard page's reach: see the module docstring."""

    page: str                        # the guard page row id
    event_id: int
    wall_cells: frozenset[Cell]      # cells whose step is pushed off while it is live
    live_cells: frozenset[Cell]      # standable while the page is live
    any_cells: frozenset[Cell]       # standable in any state the walk reaches
    # Can firing this row leave the page's live states? Read from the row's
    # writes against the same abstract states the walk runs over.
    ends: Callable[[RowState], bool] = field(default=lambda _rs: False, compare=False, repr=False)


@dataclass(frozen=True)
class GuardWait:
    """`group` can only be walked after one of `writers` (row ids) has stopped
    `guard_page` being live; none of `cells` is reachable before."""

    group: str
    guard_page: str
    cells: tuple[Cell, ...]
    wall_cells: frozenset[Cell]
    writers: tuple[str, ...]

    def describe(self) -> str:
        return (f"{self.group}: cells {list(self.cells)} unreachable while {self.guard_page} is "
                f"live (walls {_span(self.wall_cells)}); after one of {list(self.writers)}")


def _span(cells: Collection[Cell]) -> str:
    ordered = sorted(cells)
    ys = {y for _, y in ordered}
    if len(ordered) > 4 and len(ys) == 1:
        return f"row y={next(iter(ys))} x={ordered[0][0]}..{ordered[-1][0]}"
    return str(ordered)


def _may_push(page: str, cell: Cell, facts: MapFacts) -> bool:
    """Can firing `page` on `cell` displace the player? An undecidable
    displacement counts as yes (the walk then decides per state)."""
    try:
        return _displaced(page, facts, {}, cell) != {cell}
    except _Unproven:
        return True


class _LiveWalk(_Walk):
    """A non-strict walk that never re-enters the guard page's live states
    once it has left them."""

    live: frozenset[int] = frozenset()

    def next_states(self, idx: int, page_row_id: str) -> set[int]:
        nxt = super().next_states(idx, page_row_id)
        return nxt if idx in self.live else nxt - self.live


def _consistent(assignment: Mapping[Key, bool | int], seed: Mapping[Key, frozenset] | None,
                tests_by_key: Mapping[Key, list[Test]],
                default: Callable[[Key], frozenset]) -> bool:
    """Could the chapter's seed state be told apart from `assignment` by no
    modelled test? (`seed` None: anything goes.)"""
    if seed is None:
        return True
    for key, value in assignment.items():
        if isinstance(key, TempSwitch):
            continue
        values = seed.get(key, default(key))
        if VARIABLE_TOP in values:
            continue
        tests = tests_by_key.get(key, [])
        if not any(all(_holds(t, s) == _holds(t, value) for t in tests) for s in values):
            return False
    return True


def guard_reaches(facts: MapFacts, *, seed: Mapping[Key, frozenset] | None = None,
                  default: Callable[[Key], frozenset] = lambda _k: frozenset()
                  ) -> tuple[GuardReach, ...]:
    """One `GuardReach` per guard page of the map that may push the player and
    is live in some state the chapter can start the map in (`seed`, the
    chapter's start state; `default` gives an unmentioned key's value set).
    `()` when the map has none, or when the walk can't be decided (logged)."""
    if not facts.coord_cells or not facts.arrivals:
        return ()
    pages = _pages(facts)
    pushers = [
        (event, page)
        for event, cells in sorted(facts.coord_cells.items()) if event in pages
        for page in pages[event]
        if facts.candidate(page) and _may_push(page, min(cells), facts)]
    if not pushers:
        return ()
    scenes = [e for e, ps in pages.items()
              if any(facts.states[p].trigger == "autorun" and facts.candidate(p) for p in ps)]
    guards = dict(facts.coord_cells)
    tests_by_key: dict[Key, list[Test]] = {}
    for event in {*guards, *scenes}:
        for rid in pages[event]:
            if facts.candidate(rid):
                for t in facts.states[rid].page_tests:
                    tests_by_key.setdefault(t.key, []).append(t)
    try:
        domains = {k: _domain(k, ts) for k, ts in tests_by_key.items()}
        keys = sorted(domains, key=repr)
        size = 1
        for k in keys:
            size *= len(domains[k])
        if size > _MAX_STATES:
            raise _Unproven(f"{size} abstract states")
        states = list(itertools.product(*(domains[k] for k in keys)))
        out: list[GuardReach] = []
        for event, page in pushers:
            reach = _reach_for(event, page, facts, pages, keys, domains, tests_by_key, states,
                               guards, scenes, seed, default)
            if reach is not None:
                out.append(reach)
        return tuple(out)
    except _Unproven as exc:
        logger.warning("guard_reach map %d: not decided (%s); no guard constraints", facts.map_id,
                       exc)
        return ()


def _reach_for(event: int, page: str, facts: MapFacts, pages: Mapping[int, tuple[str, ...]],
               keys: list[Key], domains: Mapping[Key, tuple[bool | int, ...]],
               tests_by_key: Mapping[Key, list[Test]], states: list[tuple],
               guards: Mapping[int, frozenset[Cell]], scenes: list[int],
               seed: Mapping[Key, frozenset] | None, default: Callable[[Key], frozenset]
               ) -> GuardReach | None:
    live = frozenset(
        i for i, combo in enumerate(states)
        if _live_page(pages[event], facts, dict(zip(keys, combo))) == page)
    starts = [
        i for i in sorted(live)
        if not any(v for k, v in zip(keys, states[i]) if isinstance(k, (SelfSwitch, TempSwitch)))
        and _consistent(dict(zip(keys, states[i])), seed, tests_by_key, default)]
    if not starts:
        return None
    walk = _LiveWalk(None, facts, pages, keys, domains, tests_by_key, states, frozenset(),
                     guards, scenes, strict=False)
    walk.live = live
    walk.run([(i, a) for i in starts for a in facts.arrivals])
    pos = {k: i for i, k in enumerate(keys)}
    live_combos = {states[i] for i in live}

    def ends(rs: RowState) -> bool:
        for i in sorted(live):
            combo = states[i]
            moves: list[tuple[Key, Collection[bool | int]]] = []
            for w in rs.writes:
                if w.key not in pos or isinstance(w.key, TempSwitch):
                    continue
                if isinstance(w, Assign):
                    try:
                        moves.append((w.key, {walk._snap(w.key, v) for v in w.values}))
                    except _Unproven:
                        return True
                else:                                  # an Adjust: any value it can reach
                    moves.append((w.key, domains[w.key]))
            moves.extend((k, domains[k]) for k in rs.havoc_keys if k in pos)
            for key, values in moves:
                p = pos[key]
                if any(combo[:p] + (v,) + combo[p + 1:] not in live_combos for v in values):
                    return True
        return False

    return GuardReach(
        page=page, event_id=event, wall_cells=frozenset(walk.used.guard_cells.get(event, ())),
        live_cells=frozenset(c for i, c in walk.reach if i in live),
        any_cells=frozenset(c for _, c in walk.reach), ends=ends)


def _site_cells(rec: BeatLocationRecord) -> tuple[Cell, ...]:
    """The cells the player stands on to walk `rec`: its approach candidates,
    or its own cell."""
    if rec.approach_candidates:
        return tuple((c.x, c.y) for c in rec.approach_candidates)
    return ((rec.x, rec.y),)


def apply_guard_reach(
    records: Sequence[BeatLocationRecord], *,
    reaches_for: Callable[[int], Sequence[GuardReach]],
    map_of: Callable[[BeatLocationRecord], int],
    row_state: Callable[[str], RowState | None],
    group_of_row: Mapping[str, str],
) -> tuple[tuple[BeatLocationRecord, ...], tuple[GuardWait, ...]]:
    """Restrict approach candidates to cells reachable while each guard is live,
    or record the wait (module docstring). `reaches_for(map_id)` is
    `guard_reaches` of that map; `killed_by(page)` the story model's writers
    that end a page's liveness; `group_of_row` the claimed row -> group map."""
    out: list[BeatLocationRecord] = []
    waits: list[GuardWait] = []
    for rec in records:
        map_id = map_of(rec)
        reaches = reaches_for(map_id)
        guard_events = {reach.event_id for reach in reaches}
        if any(parse_row_id(r).map_id == map_id and parse_row_id(r).event_id in guard_events
               for r in rec.rows):
            out.append(rec)                   # a guard event's own beat: it fires ON the wall
            continue
        for reach in reaches:
            cells = _site_cells(rec)
            held = [c for c in cells if c not in reach.live_cells and c in reach.any_cells]
            if not held:
                if not any(c in reach.live_cells or c in reach.any_cells for c in cells):
                    logger.warning("guard_reach: %s cells %s reached in no state on map %d; "
                                   "not constrained", rec.beat_id, list(cells), map_id)
                continue
            if len(held) < len(cells):
                if rec.approach_candidates:
                    kept = tuple(c for c in rec.approach_candidates if (c.x, c.y) not in held)
                    logger.info("guard_reach: %s keeps approach %s (%s are cut off while %s is "
                                "live)", rec.beat_id, [(c.x, c.y) for c in kept], held, reach.page)
                    rec = dataclasses.replace(rec, approach_candidates=kept)
                continue
            writers = tuple(sorted(
                r for r, g in group_of_row.items()
                if g != rec.beat_id and (rs := row_state(r)) is not None and reach.ends(rs)))
            if not writers:
                raise GuardOrderError(
                    f"beat {rec.beat_id}: approach cells {list(cells)} are reachable only once "
                    f"guard {reach.page} (walls {_span(reach.wall_cells)}) stops being live, and "
                    f"no other claimed row ends it")
            waits.append(GuardWait(rec.beat_id, reach.page, cells, reach.wall_cells, writers))
        out.append(rec)
    return tuple(out), tuple(waits)


def guard_enabled_by(waits: Sequence[GuardWait], first_row: Mapping[str, str]
                     ) -> dict[str, tuple[tuple[str, ...], ...]]:
    """`solve_route(guard_enabled_by=)`: the wait as a story enabler on the
    beat's first row (one writer -> an edge, several -> an any-of)."""
    out: dict[str, list[tuple[str, ...]]] = {}
    for w in waits:
        out.setdefault(first_row[w.group], []).append(w.writers)
    return {r: tuple(g) for r, g in out.items()}


def check_guard_order(waits: Sequence[GuardWait], group_order: Sequence[str],
                      group_of_row: Mapping[str, str]) -> None:
    """The solved order must put a claimed writer before each waiting beat; the
    solver may have dropped an edge that closed a cycle. Raises otherwise."""
    position = {g: i for i, g in enumerate(group_order)}
    for w in waits:
        writer_groups = {group_of_row[r] for r in w.writers}
        here = position.get(w.group)
        if here is None or not any(position.get(g, len(position)) < here for g in writer_groups):
            raise GuardOrderError(
                f"beat {w.group}: no ordering puts it after a row that ends guard "
                f"{w.guard_page} ({w.describe()}); writers' groups {sorted(writer_groups)} "
                "cannot precede it (a precedence cycle?)")
