"""Pages the player cannot trigger while they are the live page (the lab
guard, `investigations/warp-round-trips-and-gated-doors.md`, 2026-09-28).

A touch page (`player_touch` / `event_touch`) that the converter widened into
coord triggers fires when the player steps onto one of those cells. It
`never_fires` when, for the whole span in which it is its event's live page,
the walk cannot step onto any of them. Two things stand in the way that plain
NPC occupancy (`reach.py`) doesn't model:

- **Coord-trigger guards.** Another event's coord cells, while that event's
  live page moves the player off the cell it fired on (a move route at the
  player -- "Hey, where are you going?" and a step back). Stepping onto such a
  cell ends on the cell the page moves the player to, not on the cell. Which
  pages displace, and by how much, is read from the page itself
  (`page_sim.run_page`'s `cell`), never named; a page that moves nobody is not
  a wall.
- **Arrival displacement.** An arrival autorun that moves the player leaves
  them somewhere other than the warp's landing cell, so the walk starts from
  the post-scene cell.

The proof is over abstract story states: every combination of the values the
relevant page conditions can tell apart. For each state in which the page is
live, the region the player can reach from the (displaced) arrival is flooded
under that state's guards. `None` is "not proven", never "reachable": the
prover answers `None` for anything it can't decide (a displacement that isn't
certain, a way out of the map, a page that writes a liveness key without
ending the span) and raises on a converted coord event it can't attribute.

Assumptions, stated so the review doc can be checked against them:

1. An arrival autorun runs on its FIRST firing (its own event's self switches
   still False); a state in which its event has moved on to a later page
   through a self switch only its own pages write is treated as the same
   confined player, starting from the same displaced cell (entering the map
   again would need a way out of it, which the flood rules out).
2. Move routes are relative and unobstructed (`page_sim`'s model).
3. Coord events' own `VAR_TEMP_F` gate is ignored: a guard is live whenever
   its event's live page is.
4. Parallel pages never move the player. `call common event` (117) inside a
   reachable live page is not proven safe, so it makes the answer `None`.
"""
from __future__ import annotations

import itertools
import logging
import re
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from rpg2gba.beat_gen.page_sim import Firing, run_page
from rpg2gba.chapter_manifest.schema import parse_row_id
from rpg2gba.conversion_agent.transpiler import TRANSFER_PLAYER
from rpg2gba.story_state.extract import RowState
from rpg2gba.story_state.model import VARIABLE_TOP, _cmp
from rpg2gba.story_state.state import (
    Assign,
    EngineKey,
    Key,
    SelfSwitch,
    Switch,
    TempSwitch,
    Test,
    Variable,
)
from rpg2gba.traversal.graph import MapGraph

logger = logging.getLogger(__name__)

Cell = tuple[int, int]

TOUCH_TRIGGERS = frozenset({"player_touch", "event_touch"})
_ORTHO = ((0, -1), (0, 1), (1, 0), (-1, 0))
_CALL_COMMON_EVENT = 117
_MAX_STATES = 50_000
_COORD_SCRIPT_RE = re.compile(r"^Map(\d+)_EV(\d+)_Dispatch$")
# Statuses the story model can't rule a page's condition out under: a page
# it calls live, or one it couldn't decide, may be the live page.
_CANDIDATE_STATUSES = frozenset({"live", "refused", "undetermined"})


def coord_cells_by_event(map_id: int, coord_events: list[Mapping]) -> dict[int, frozenset[Cell]]:
    """{RMXP event id: the coord-trigger cells the converter emitted for it},
    from a converted map's `coord_events`. An entry that isn't a `trigger`
    dispatching `Map<id>_EV<n>_Dispatch` on this map raises (§4.5): its
    event can't be attributed."""
    out: dict[int, set[Cell]] = {}
    for ce in coord_events:
        match = _COORD_SCRIPT_RE.match(str(ce.get("script", "")))
        if ce.get("type") != "trigger" or match is None or int(match.group(1)) != map_id:
            raise ValueError(f"map {map_id}: coord event {dict(ce)!r} is not a "
                             f"`Map{map_id:03d}_EV<n>_Dispatch` trigger")
        out.setdefault(int(match.group(2)), set()).add((int(ce["x"]), int(ce["y"])))
    return {e: frozenset(cells) for e, cells in out.items()}


@dataclass(frozen=True)
class MapFacts:
    """Everything the prover reads about one map."""

    map_id: int
    coord_cells: Mapping[int, frozenset[Cell]]          # event id -> widened cells
    states: Mapping[str, RowState]                      # every row of the map
    page_for: Callable[[str], Mapping]                  # page row id -> raw RMXP page
    event_cell: Callable[[str], Cell | None]            # page row id -> its event's cell
    graph: MapGraph
    blocked: frozenset[Cell]                            # stationary-NPC tiles
    arrivals: tuple[Cell, ...]                          # warp landings into the map
    candidate: Callable[[str], bool] = lambda _rid: True  # can this page be live at all


class _Unproven(Exception):
    """The prover can't decide; the caller answers `None`."""


def _event_of(page_row_id: str) -> int:
    return parse_row_id(page_row_id).event_id


def _pages(facts: MapFacts) -> dict[int, tuple[str, ...]]:
    """event id -> its page row ids, for every event with a page row."""
    out: dict[int, tuple[str, ...]] = {}
    for rid, rs in facts.states.items():
        if parse_row_id(rid).kind == "page":
            out[_event_of(rid)] = rs.event_page_row_ids
    return out


def _holds(test: Test, value: bool | int) -> bool:
    return _cmp(test.op, value, test.value)


def _live_page(pages: tuple[str, ...], facts: MapFacts, assignment: Mapping[Key, bool | int]
               ) -> str | None:
    """RMXP's rule: the highest page whose conditions all hold. A page the
    story model rules out everywhere (`candidate` False) never holds."""
    for rid in reversed(pages):
        if not facts.candidate(rid):
            continue
        rs = facts.states[rid]
        if rs.page_refusals:
            raise _Unproven(f"{rid}: page condition not modelled ({rs.page_refusals[0].code})")
        if all(_holds(t, assignment[t.key]) for t in rs.page_tests):
            return rid
    return None


def _domain(key: Key, tests: list[Test]) -> tuple[bool | int, ...]:
    if isinstance(key, (Switch, SelfSwitch, TempSwitch)):
        return (False, True)
    if isinstance(key, Variable):
        values = {0}
        for t in tests:
            v = int(t.value)
            values.update((v - 1, v, v + 1))
        return tuple(sorted(values))
    raise _Unproven(f"no value domain for state key {key!r}")


def _own_view(assignment: Mapping[Key, bool | int], own: tuple[int, int] | None,
              extra_keys: set[Key]) -> dict[Key, frozenset]:
    """`assignment` as `page_sim` value sets. Keys it doesn't name are havoc'd,
    except the event's own self switches: a first firing sees them False."""
    out: dict[Key, frozenset] = {k: frozenset({v}) for k, v in assignment.items()}
    for key in extra_keys - set(out):
        if own is not None and isinstance(key, SelfSwitch) and (key.map_id, key.event_id) == own:
            out[key] = frozenset({False})
        elif isinstance(key, (Variable, EngineKey)):
            out[key] = frozenset({VARIABLE_TOP})
        else:
            out[key] = frozenset({False, True})
    return out


def _guard_keys(page_row_id: str, facts: MapFacts) -> set[Key]:
    keys: set[Key] = set()
    for rid, rs in facts.states.items():
        if parse_row_id(rid).owning_page_row_id == page_row_id and rs.arm_guard is not None:
            keys.update(t.key for t in rs.arm_guard.tests)
    return keys


def _run(page_row_id: str, facts: MapFacts, view: Mapping[Key, frozenset], cell: Cell):  # noqa: ANN202
    return run_page(page_row_id, facts.page_for(page_row_id), facts.states, view,
                    Firing(cell=cell, event_cell=facts.event_cell(page_row_id)))


def _displaced(page_row_id: str, facts: MapFacts, assignment: Mapping[Key, bool | int],
               cell: Cell) -> frozenset[Cell]:
    """The cells firing `page_row_id` from `cell` can leave the player on: the
    one it certainly ends on, or -- when that isn't standable (a route the
    terrain stops short) -- `cell` and every standable cell along the route.
    Raises `_Unproven` when the end isn't certain."""
    event_id = _event_of(page_row_id)
    view = _own_view(assignment, (facts.map_id, event_id), _guard_keys(page_row_id, facts))
    run = _run(page_row_id, facts, view, cell)
    if run.cell is None or not run.cell_exact:
        raise _Unproven(f"{page_row_id} from {cell}: the player's end cell isn't certain")
    if _standable(facts, run.cell):
        return frozenset({run.cell})
    stops = {c for c in (cell, *run.path) if _standable(facts, c)}
    if not stops:
        raise _Unproven(f"{page_row_id} from {cell}: the route leaves the map")
    return frozenset(stops)


def _standable(facts: MapFacts, cell: Cell) -> bool:
    return facts.graph.is_walkable(cell) and cell not in facts.blocked


def _has_code(page_row_id: str, facts: MapFacts, codes: frozenset[int]) -> bool:
    return any(c.get("code") in codes for c in facts.page_for(page_row_id).get("list") or [])


def _page_rows(page_row_id: str, facts: MapFacts) -> list[RowState]:
    return [rs for rid, rs in facts.states.items()
            if rid == page_row_id or parse_row_id(rid).owning_page_row_id == page_row_id]




@dataclass
class _Used:
    """What the walk touched, gathered for the proof text."""

    guard_cells: dict[int, set[Cell]] = field(default_factory=dict)
    starts: set[tuple[Cell, Cell, str]] = field(default_factory=set)
    scene_pages: set[str] = field(default_factory=set)
    reached: int = 0
    states: int = 0


class _Walk:
    """The product walk: (abstract story state, player cell) nodes, moving
    within a state under its guards and changing state through the writes of
    the pages the player can fire. Only states in which the page is live are
    nodes; a write that ends the span drops the node."""

    def __init__(self, page_row_id: str, facts: MapFacts, pages: Mapping[int, tuple[str, ...]],
                 keys: list[Key], domains: Mapping[Key, tuple[bool | int, ...]],
                 tests_by_key: Mapping[Key, list[Test]], live_states: list[tuple],
                 targets: frozenset[Cell], guards: Mapping[int, frozenset[Cell]],
                 scenes: list[int]) -> None:
        self.page = page_row_id
        self.facts = facts
        self.pages = pages
        self.keys = keys
        self.domains = domains
        self.tests_by_key = tests_by_key
        self.states = live_states
        self.index = {combo: i for i, combo in enumerate(live_states)}
        self.targets = targets
        self.guards = guards
        self.enumerated = {_event_of(page_row_id), *guards, *scenes}
        self.scenes = scenes
        self.coord_owner = {c: e for e, cells in facts.coord_cells.items() for c in cells}
        self.used = _Used(states=len(live_states))
        self.reach: set[tuple[int, Cell]] = set()
        self.touched: set[tuple[int, Cell]] = set()
        self.queue: deque[tuple[int, Cell]] = deque()
        self._info: dict[int, _Info] = {}

    # -- per-state facts ------------------------------------------------------

    def assignment(self, idx: int) -> dict[Key, bool | int]:
        return dict(zip(self.keys, self.states[idx]))

    def info(self, idx: int) -> _Info:
        if idx not in self._info:
            self._info[idx] = self._build_info(idx)
        return self._info[idx]

    def _build_info(self, idx: int) -> _Info:
        facts = self.facts
        assignment = self.assignment(idx)
        info = _Info()
        for event, cells in self.guards.items():
            live = _live_page(self.pages[event], facts, assignment)
            if live is None:
                continue
            info.guard_page[event] = live
            if _has_code(live, facts, frozenset({TRANSFER_PLAYER})):
                for c in cells:
                    info.inexact[c] = f"{live} transfers the player"
                continue
            for c in cells:
                try:
                    ends = _displaced(live, facts, assignment, c)
                except _Unproven as exc:
                    info.inexact[c] = str(exc)
                    continue
                if ends != {c}:
                    info.push[c] = ends
                    self.used.guard_cells.setdefault(event, set()).add(c)
        for event, ps in self.pages.items():
            if event == _event_of(self.page) or event in self.guards:
                continue
            live = ([p] if (p := _live_page(ps, facts, assignment)) is not None else []) \
                if event in self.enumerated else [p for p in ps if facts.candidate(p)]
            for pid in live:
                trigger = facts.states[pid].trigger
                if trigger == "autorun":
                    info.autoruns.append(pid)
                elif trigger == "parallel":
                    info.parallels.append(pid)
                else:
                    info.talkable.append(pid)
        if len(info.autoruns) > 1:
            raise _Unproven(f"{len(info.autoruns)} autoruns live together: {info.autoruns}")
        return info

    # -- state transitions ----------------------------------------------------

    def _snap(self, key: Key, value: bool | int) -> bool | int:
        tests = self.tests_by_key.get(key, [])
        for d in self.domains[key]:
            if all(_holds(t, d) == _holds(t, value) for t in tests):
                return d
        raise _Unproven(f"{key!r}: value {value!r} not told apart by any modelled value")

    def next_states(self, idx: int, page_row_id: str) -> set[int]:
        """The states firing `page_row_id` can leave the walk in, other than
        `idx` itself; a state where the page isn't live any more is dropped."""
        out: set[int] = set()
        combo = self.states[idx]
        pos = {k: i for i, k in enumerate(self.keys)}

        def move(key: Key, values) -> None:  # noqa: ANN001
            if key not in pos:
                return          # nothing on this map's liveness reads it
            for v in values:
                new = combo[:pos[key]] + (v,) + combo[pos[key] + 1:]
                if new in self.index and self.index[new] != idx:
                    out.add(self.index[new])

        for rs in _page_rows(page_row_id, self.facts):
            if rs.havoc_global:
                out.update(i for i in range(len(self.states)) if i != idx)
            for k in rs.havoc_keys:
                if k in pos:
                    move(k, self.domains[k])
            for w in rs.writes:
                if isinstance(w.key, TempSwitch) or w.key not in pos:
                    continue
                if isinstance(w, Assign):
                    move(w.key, {self._snap(w.key, v) for v in w.values})
                else:
                    move(w.key, self.domains[w.key])
        return out

    # -- the walk ---------------------------------------------------------------

    def add(self, idx: int, cell: Cell, *, fresh: bool = False) -> None:
        """The player is on `cell` in state `idx`. `fresh`: just arrived or
        just changed state, so this state's autorun (if any) fires now."""
        if cell in self.targets:
            raise _Unproven(f"{cell} can be stepped on in state {self.assignment(idx)}")
        node = (idx, cell)
        if node in self.reach:
            return
        self.reach.add(node)
        info = self.info(idx)
        if fresh and info.autoruns:
            scene = info.autoruns[0]
            self.used.scene_pages.add(scene)
            for end in sorted(_displaced(scene, self.facts, self.assignment(idx), cell)):
                self.used.starts.add((cell, end, scene))
                self.add(idx, end)
                self.transition(idx, end, scene)
            return
        self.queue.append(node)

    def transition(self, idx: int, cell: Cell, page_row_id: str) -> None:
        """The player is on `cell` and `page_row_id` runs: every state its
        writes can leave the walk in."""
        for nxt in self.next_states(idx, page_row_id):
            self.add(nxt, cell, fresh=True)

    def enter(self, idx: int, cell: Cell, chain: frozenset[Cell] = frozenset()) -> None:
        facts = self.facts
        if not _standable(facts, cell):
            return
        info = self.info(idx)
        event = self.coord_owner.get(cell)
        if event == _event_of(self.page):
            raise _Unproven(f"{cell} can be stepped on in state {self.assignment(idx)}")
        if event is not None and event in info.guard_page:
            self.touched.add((idx, cell))
            live = info.guard_page[event]
            if cell in info.inexact:
                raise _Unproven(f"{cell}: {info.inexact[cell]}")
            if _has_code(live, facts, frozenset({_CALL_COMMON_EVENT})):
                raise _Unproven(f"{live} runs a common event")
            ends = info.push.get(cell)
            if ends is not None:
                if cell not in chain:
                    for end in sorted(ends):
                        self.transition(idx, end, live)
                        self.enter(idx, end, chain | {cell})
                return
            self.transition(idx, cell, live)
        self.add(idx, cell)

    def run(self, starts: list[tuple[int, Cell]]) -> None:
        for idx, cell in starts:
            self.add(idx, cell, fresh=True)
        facts = self.facts
        while self.queue:
            idx, cell = self.queue.popleft()
            for edge in facts.graph.neighbors(cell):
                self.enter(idx, edge.target)
            info = self.info(idx)
            for tile in [cell] + [(cell[0] + dx, cell[1] + dy) for dx, dy in _ORTHO]:
                solid = tile != cell and not facts.graph.is_walkable(tile)
                if solid and tile in self.targets:
                    raise _Unproven(f"{tile} can be pressed into from {cell}")
                # A way out of the map would let the player come back another way.
                if (tile == cell or solid) and tile in facts.graph.warp_exits:
                    raise _Unproven(f"a warp at {tile} is reachable")
            for pid in info.parallels:
                self.fire_at(idx, cell, pid)
            for pid in info.talkable:
                ecell = facts.event_cell(pid)
                if ecell is None or abs(ecell[0] - cell[0]) + abs(ecell[1] - cell[1]) <= 1:
                    self.fire_at(idx, cell, pid)
        self.used.reached = len({c for _, c in self.reach})

    def fire_at(self, idx: int, cell: Cell, page_row_id: str) -> None:
        if _has_code(page_row_id, self.facts, frozenset({TRANSFER_PLAYER, _CALL_COMMON_EVENT})):
            raise _Unproven(f"{page_row_id} may transfer the player or run a common event")
        self.transition(idx, cell, page_row_id)


@dataclass
class _Info:
    guard_page: dict[int, str] = field(default_factory=dict)
    push: dict[Cell, frozenset[Cell]] = field(default_factory=dict)
    inexact: dict[Cell, str] = field(default_factory=dict)
    autoruns: list[str] = field(default_factory=list)
    parallels: list[str] = field(default_factory=list)
    talkable: list[str] = field(default_factory=list)


def never_fires_proof(page_row_id: str, facts: MapFacts) -> str | None:
    """The proof text that `page_row_id` can never fire on the ROM, or None
    when that isn't established (module docstring)."""
    parsed = parse_row_id(page_row_id)
    rs = facts.states.get(page_row_id)
    if parsed.kind != "page" or rs is None or rs.trigger not in TOUCH_TRIGGERS:
        return None
    targets = facts.coord_cells.get(parsed.event_id)
    if not targets or not facts.arrivals:
        return None
    pages = _pages(facts)
    own_pages = pages[parsed.event_id]
    guards = {e: cells for e, cells in facts.coord_cells.items() if e != parsed.event_id}
    scenes = [e for e, ps in pages.items()
              if any(facts.states[p].trigger == "autorun" and facts.candidate(p) for p in ps)]
    tests_by_key: dict[Key, list[Test]] = {}
    for event in {parsed.event_id, *guards, *scenes}:
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
        live_states = [combo for combo in itertools.product(*(domains[k] for k in keys))
                       if _live_page(own_pages, facts, dict(zip(keys, combo))) == page_row_id]
        if not live_states:
            return None
        walk = _Walk(page_row_id, facts, pages, keys, domains, tests_by_key, live_states,
                     targets, guards, scenes)
        # Assumption 1: the first entry sees this map's own self switches unset.
        first = [i for i, combo in enumerate(live_states)
                 if not any(v for k, v in zip(keys, combo)
                            if isinstance(k, (SelfSwitch, TempSwitch)))]
        if not first:
            raise _Unproven("no state with the map's self switches unset")
        walk.run([(i, a) for i in first for a in facts.arrivals])
    except _Unproven as exc:
        logger.debug("never_fires %s: not proven (%s)", page_row_id, exc)
        return None
    return _describe(page_row_id, targets, pages, facts, walk.used)


def _describe(page_row_id: str, targets: frozenset[Cell], pages: Mapping[int, tuple[str, ...]],
              facts: MapFacts, used: _Used) -> str:
    own = pages[_event_of(page_row_id)]
    later = [p for p in own[own.index(page_row_id) + 1:] if facts.candidate(p)]
    superseded = "nothing supersedes it"
    if later:
        conds = "; ".join(_describe_tests(facts.states[later[0]].page_tests) or ["always"])
        superseded = f"{later[0]} supersedes it once {conds}"
    guards = "; ".join(
        f"ev{e:03d} pushes the player off {_cells(sorted(c))}"
        for e, c in sorted(used.guard_cells.items())) or "no guard cell pushes the player"
    starts = "; ".join(
        f"arrival {a} -> start {s} (scene {p})" for a, s, p in sorted(used.starts, key=repr)
    ) or "no arrival scene moves the player"
    return (f"{page_row_id} fires only on {_cells(sorted(targets))}; while it is the live page "
            f"the walk can't step on them: {starts}; {guards}; over {used.states} story "
            f"state(s) the reachable region ({used.reached} cells) touches none of them and "
            f"has no way out of the map; {superseded}")


def _describe_tests(tests: tuple[Test, ...]) -> list[str]:
    return [f"{t.key.__class__.__name__.lower()} {getattr(t.key, 'id', getattr(t.key, 'letter', '?'))} "
            f"{t.op} {t.value}" for t in tests]


def _cells(cells: list[Cell]) -> str:
    if len(cells) <= 4:
        return ", ".join(map(str, cells))
    ys = {y for _, y in cells}
    xs = {x for x, _ in cells}
    if len(ys) == 1:
        return f"row y={ys.pop()} (x={min(xs)}..{max(xs)}, {len(cells)} cells)"
    return f"{len(cells)} cells from {cells[0]} to {cells[-1]}"
