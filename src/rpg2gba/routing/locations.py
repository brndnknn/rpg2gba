"""Derive each dispositioned beat's routing point from data, before the
chapter's playtest module exists.

WHY THIS MODULE EXISTS
----------------------
`routing plan` imports the chapter's playtest module and reads every
routing coordinate out of the beats registered there (`solver.py`'s
`_resolve_group_point` takes `beat.locations[0]`). That makes the loop's
ROUTE step circular: `BUILD_PLAN.md` step 6 asks you to approve an ORDER
before authoring the beats, but the solver cannot produce an order without
the beats it is supposed to order. Every chapter gated to date resolved the
circle by authoring first, which demotes the solver to a grader of an order
nobody can still change -- exactly the state `PROJECT_TODO.md` #67 records
for CH01-CH04.

This module breaks it by deriving the coordinates from artifacts that
already exist at step 6 time: the chapter manifest, its dispositions, and
the decoded map JSON. The result is a small, reviewable JSON file -- the
thing you actually approve at STOP 3 -- which then materializes into an
in-memory `Chapter` so `solver.py` needs no change at all.

WHAT IT DOES NOT DO
-------------------
It derives WHERE, never WHAT HAPPENS THERE. Assertions, facing, self-switch
settling and beat prose stay hand-authored; the rejection of a beat
*generator* (`PLAYTEST_AUTHORING_IMPROVEMENT_V2.md:309-330`,
`playtest/archetypes/__init__.py:6-11`) is untouched. Locations are pure
lookups with no judgement in them, which is why they can be hoisted ahead
of authoring and behaviour cannot.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from ..chapter_manifest.dispositions import load_dispositions
from ..chapter_manifest.schema import ManifestRow
from ..playtest import chapter as _chapter
from ..playtest.cells import approach_to, event_cell
from ..traversal.graph import build_map_graph

log = logging.getLogger(__name__)

_BEAT_VERDICT = "beat"


@dataclass(frozen=True)
class ApproachCandidate:
    """One legal SIDE a beat's location could be approached/used from.

    Distinct from `RowCell`'s `candidates` (which lists candidate ROWS --
    which manifest row a multi-row beat routed on, an entirely different
    concept, CLAUDE.md §4.3): this is the set of walkable sides of a single
    chosen cell, so the offline route solver can pick the cheapest one
    itself instead of a resolver's fixed N/S/E/W (or west-then-east)
    tiebreak silently deciding it (see `solver.py`'s `candidates=` param).

    `resolver` is a call an author could paste into a chapter module to pin
    this exact side -- for an `approach_to`-derived beat this is a literal,
    valid `prefer=` call. For a `stair_approach`-derived beat there is no
    public `cells.py` function with a side parameter (this module may not
    add one -- see the derivation task brief), so `resolver` instead
    describes the side unambiguously in prose-as-code shape; it is NOT
    paste-able as-is.
    """

    x: int
    y: int
    side: str
    resolver: str


@dataclass(frozen=True)
class RowCell:
    """One manifest row's derived cell, with the provenance that produced it.

    `resolver` is the name of the `cells.py` function used (or "terrain" for
    a row that carries its own literal x/y). Recording it is the point: a
    reviewer can see that B11's cell came from `approach_to(map037, ev002)`
    rather than trusting prose, which is the class of conflation that put a
    wrong boundary cell in CH05_TODO's log.

    `approach_candidates` is empty for a row whose cell carries no side
    choice (an `event_cell`-derived row: the player stands ON the event's
    own cell, so there is no "which side" question). For an
    `approach_to`/`stair_approach`-derived row it holds every legal side, in
    the same deterministic order those resolvers themselves use.
    """

    row_id: str
    map_constant: str
    x: int
    y: int
    resolver: str
    approach_candidates: tuple[ApproachCandidate, ...] = ()


@dataclass(frozen=True)
class BeatLocationRecord:
    """The single routing point for one beat, plus the rows behind it."""

    beat_id: str
    map_constant: str
    x: int
    y: int
    resolver: str
    rows: tuple[str, ...]
    candidates: tuple[RowCell, ...]
    approach_candidates: tuple[ApproachCandidate, ...] = ()


# --------------------------------------------------------------------------
# map id -> MAP_* constant
# --------------------------------------------------------------------------

_CONST_BY_UID: dict[int, str] | None = None


def _map_constant_for(map_id: int) -> str:
    """The MAP_* constant for a Uranium map id.

    Inverts `chapter.py`'s loader rather than re-parsing
    `porymap/map_constants.json` a second time (CLAUDE.md §4.3).
    """
    global _CONST_BY_UID
    if _CONST_BY_UID is None:
        forward = _chapter._load_map_const_to_uranium_id(
            _chapter.default_map_constants_state_path()
        )
        inverted: dict[int, str] = {}
        for const, uid in forward.items():
            if uid in inverted:
                raise ValueError(
                    f"map id {uid} is claimed by two map constants "
                    f"({inverted[uid]!r} and {const!r}) -- the minted "
                    "constant table is not injective, which every cell "
                    "resolver here assumes"
                )
            inverted[uid] = const
        _CONST_BY_UID = inverted
    const = _CONST_BY_UID.get(map_id)
    if const is None:
        raise ValueError(
            f"Uranium map {map_id} has no minted MAP_* constant -- it is "
            "almost certainly not in SLICE_MAP_IDS, so run Phase 5 for this "
            "chapter's maps before deriving locations"
        )
    return const


# --------------------------------------------------------------------------
# row -> cell
# --------------------------------------------------------------------------

# A page row's trigger decides whether the player stands ON the event's own
# cell or ADJACENT to it. `player_touch` and `autorun` both fire with the
# player occupying the event tile (a warp you step onto; an arrival nudge
# that fires where the warp deposited you), so the event cell IS the
# routing point. `action` and `event_touch` are triggered from a neighbour,
# so the approach cell is.
_ON_EVENT_TRIGGERS = frozenset({"player_touch", "autorun"})
_ADJACENT_TRIGGERS = frozenset({"action", "event_touch"})


def _stair_side_candidates(map_id: int, map_constant: str,
                          x: int, y: int) -> tuple[ApproachCandidate, ...]:
    """Every walkable E/W neighbour of stair cell (x, y), west then east --
    the candidate set an author picks a side from.

    Since 2026-09-08 `resolver` is a real paste-able call:
    `playtest.cells.stair_approach` now takes a required `side`
    (`POST_CH05_REVIEW.md` G4), so this no longer has to describe the side in
    prose. It identifies the stair by EVENT ID, matching that resolver --
    a coordinate pair in the emitted call would itself be a bare literal
    under the coordinate ban.

    Candidates are filtered on walkability, not on `stair_diagonal` edge
    ownership. See `_stair_approach` for why the two differ and which one is
    right at the ends of a diagonal run.
    """
    graph = build_map_graph(map_id)
    event_id = _stair_event_id(map_id, x, y)
    candidates: list[ApproachCandidate] = []
    for side, (nx, ny) in (("west", (x - 1, y)), ("east", (x + 1, y))):
        if not graph.in_bounds((nx, ny)) or not graph.is_walkable((nx, ny)):
            continue
        ref = (
            f"stair_event={event_id}" if event_id is not None
            else f"stair_event=<no stair event at ({x},{y})>"
        )
        candidates.append(ApproachCandidate(
            x=nx, y=ny, side=side,
            resolver=f"stair_approach({map_constant}, {ref}, side={side!r})",
        ))
    return tuple(candidates)


def _stair_event_id(map_id: int, x: int, y: int) -> int | None:
    """The diagonal-stair event id at (x, y), or None if there isn't one.

    `playtest.cells.stair_approach` is keyed by event id, so the paste-able
    resolver string this module emits has to name one.
    """
    from ..tileset_converter.stairs import detect_stair_cells
    from ..traversal.collision import load_map_json

    for cell in detect_stair_cells(load_map_json(map_id)):
        if (cell.x, cell.y) == (x, y):
            return cell.event_id
    return None


def _stair_approach(map_id: int, map_constant: str, x: int, y: int,
                    *, row_id: str) -> tuple[int, int]:
    """The cell a player stands on to USE the sideways staircase at (x, y).

    A terrain/stairs row records the stair cell itself, and that cell can
    never be a routing point: an E/W press into a sideways staircase is
    redirected diagonally ACROSS it (`traversal/graph.py`'s `stair_diagonal`
    edge), so no edge in the graph ever *targets* a stair cell. A BFS
    confirms it -- on Map037, all four stair cells are absent from the 282
    cells reachable from anywhere in the walkable region, even though
    `is_walkable` returns True for each. Routing to the recorded cell asks
    the solver for a path that provably does not exist.

    So resolve to the cell the stair edge departs FROM: the E/W neighbour
    that owns a `stair_diagonal` edge AND is itself walkable. West is
    preferred over east purely for determinism among the *walkable*
    candidates -- both are legitimate, and which one a beat should really
    use depends on the direction of travel, which is an authoring decision
    this derivation deliberately does not make.

    **The walkability filter is not belt-and-braces** (added 2026-09-08,
    `PROJECT_TODO.md` #90). Owning a `stair_diagonal` edge does not make a
    cell standable: a diagonal staircase RUN has unwalkable cells partway
    along it that still carry the edge, because the edge describes the
    redirect the run performs, not somewhere the player may stand. Without
    this filter the function returned an unstandable cell for **3 of
    Map033's 7 stair cells** -- including both approaches CH02's B2/B3
    verified against a booted ROM. `_approach_side_candidates`, twenty lines
    below, has always filtered on `is_walkable`; the stair path simply never
    did.
    """
    graph = build_map_graph(map_id)
    unwalkable: list[tuple[int, int]] = []
    for nx, ny in ((x - 1, y), (x + 1, y)):
        if not graph.in_bounds((nx, ny)):
            continue
        if not any(edge.kind == "stair_diagonal"
                   for edge in graph.neighbors((nx, ny))):
            continue
        if not graph.is_walkable((nx, ny)):
            unwalkable.append((nx, ny))
            continue
        return (nx, ny)
    if unwalkable:
        raise ValueError(
            f"{row_id}: stair cell ({x},{y}) on {map_constant} has E/W "
            f"neighbour(s) {unwalkable} owning a stair_diagonal edge, but "
            "none of them is walkable -- the player cannot stand there to "
            "use the staircase. This is usually a cell partway along a "
            "DIAGONAL run: route to one of the run's ends instead, and see "
            "`playtest.cells.stair_approach` for the side-aware resolver a "
            "chapter author should use."
        )
    raise ValueError(
        f"{row_id}: stair cell ({x},{y}) on {map_constant} has no E/W "
        "neighbour owning a stair_diagonal edge -- either the terrain row "
        "is stale or this is not a sideways staircase, and a routing point "
        "must be supplied by hand"
    )


def _approach_side_candidates(map_id: int, map_constant: str,
                             event_id: int) -> tuple[ApproachCandidate, ...]:
    """Every walkable side of `event_id`'s own cell, in the same N/S/E/W
    order `approach_to`/`MapGraph.interaction_cells` use -- the full candidate
    set `approach_to(map_constant, event_id)` (no `prefer=`) itself picks
    the first of. `resolver` is the exact paste-able `prefer=` call an
    author would write to pin that side.
    """
    graph = build_map_graph(map_id)
    cell = event_cell(map_constant, event_id)
    candidates: list[ApproachCandidate] = []
    # Same sides `approach_to` offers, counter reach-over included.
    for direction, cand_cell in graph.interaction_cells(cell):
        candidates.append(ApproachCandidate(
            x=cand_cell[0], y=cand_cell[1], side=direction.value,
            resolver=(f'approach_to({map_constant}, ev{event_id}, '
                      f'prefer="{direction.value}")'),
        ))
    return tuple(candidates)


def _stair_resolver_string(map_id: int, map_constant: str, x: int, y: int) -> str:
    """The paste-able `playtest.cells.stair_approach` call for a stair row.

    `_stair_approach` prefers the first walkable side, so the emitted call
    names that same side rather than leaving the author to guess which one
    the derived cell came from.
    """
    graph = build_map_graph(map_id)
    event_id = _stair_event_id(map_id, x, y)
    side = "west" if graph.is_walkable((x - 1, y)) else "east"
    ref = f"stair_event={event_id}" if event_id is not None else f"stair_at=({x},{y})"
    return f"stair_approach({map_constant}, {ref}, side={side!r})"


def cell_for_row(row: ManifestRow) -> RowCell:
    """Derive one manifest row's cell, failing loud on a row kind that has
    no mechanical location (CLAUDE.md §4.5)."""
    if row.kind == "terrain":
        terrain = row.terrain
        if terrain is None:
            raise ValueError(f"{row.row_id}: kind=terrain but no terrain ref")
        map_constant = _map_constant_for(row.map_id)
        ax, ay = _stair_approach(row.map_id, map_constant, terrain.x, terrain.y,
                                 row_id=row.row_id)
        return RowCell(
            row_id=row.row_id,
            map_constant=map_constant,
            x=ax,
            y=ay,
            resolver=_stair_resolver_string(row.map_id, map_constant, terrain.x, terrain.y),
            approach_candidates=_stair_side_candidates(
                row.map_id, map_constant, terrain.x, terrain.y),
        )

    if row.kind == "seam":
        raise ValueError(
            f"{row.row_id}: seam rows carry a connection direction/offset, "
            "not a cell, and no resolver in playtest/cells.py converts one "
            "-- a seam beat's routing point must be supplied by hand. (CH05 "
            "has no seam rows; this fires for a later chapter.)"
        )

    if row.kind != "page":
        raise ValueError(f"{row.row_id}: unknown row kind {row.kind!r}")

    if row.event_id is None:
        raise ValueError(f"{row.row_id}: kind=page but no event_id")

    map_constant = _map_constant_for(row.map_id)
    if row.trigger in _ON_EVENT_TRIGGERS:
        return RowCell(row.row_id, map_constant,
                       *event_cell(map_constant, row.event_id),
                       resolver=f"event_cell({map_constant}, ev{row.event_id})")
    if row.trigger in _ADJACENT_TRIGGERS:
        return RowCell(row.row_id, map_constant,
                       *approach_to(map_constant, row.event_id),
                       resolver=f"approach_to({map_constant}, ev{row.event_id})",
                       approach_candidates=_approach_side_candidates(
                           row.map_id, map_constant, row.event_id))
    raise ValueError(
        f"{row.row_id}: trigger {row.trigger!r} has no cell rule -- add it "
        f"to _ON_EVENT_TRIGGERS or _ADJACENT_TRIGGERS once you know which "
        "side of the event the player stands on"
    )


# --------------------------------------------------------------------------
# beat -> the ONE routing point
# --------------------------------------------------------------------------

def choose_routing_point(beat_id: str,
                         candidates: tuple[RowCell, ...]) -> RowCell:
    """Pick the single cell that represents `beat_id` to the route solver.

    Most beats are unambiguous: their rows are several pages of one event
    and every candidate is the same cell. But some beats legitimately span
    two distinct cells, and the solver only ever consults ONE point per
    group (`solver.py:84-110` takes `beat.locations[0]`), so a rule is
    needed. In CH05 the multi-cell beats are:

      B8   map036/ev002/p0 (17,4) + map037/ev001/p0 (16,27)
           -- a warp PAIR, claimed by one beat under the round-trip idiom
      B13  map037 stairs (11,9) + (11,10)   -- one staircase, two cells
      B14  map037 stairs (20,9) + (20,10)   -- one staircase, two cells

    Context that bears on the choice: the round-trip idiom says a warp beat
    ENDS on the far side, and routing cost is really about where the NEXT
    beat starts from -- so the first-listed row is not obviously the right
    representative. Against that, `candidates` arrives in manifest row
    order, which is stable and reviewable, and any rule that is "clever"
    here is a rule someone has to re-derive later.

    `candidates` is non-empty and in manifest row order. Returns one of them.

    The rule, in two parts:

    1. **Collapse identical cells first.** Several pages of one event resolve
       to the same cell, so most beats never reach a policy decision at all.
    2. **A beat that spans genuinely different cells is a traversal, and a
       traversal is represented by where it ENDS** -- its last claimed row.
       Both idioms that create multi-cell beats are round trips: a warp beat
       crosses, comes back, and crosses again, ending on the far side, and a
       staircase beat likewise finishes across. Routing cost is a function of
       where the NEXT beat departs from, so the terminal row is the honest
       representative; taking the first would charge the solver for a
       position the player has already left.

    The choice is never silent: every candidate is written to the locations
    file's `candidates` array, and an auto-resolution is logged with all of
    them, so STOP 3 review can see what was collapsed and overrule it.
    """
    distinct: list[RowCell] = []
    seen: set[tuple[str, int, int]] = set()
    for cand in candidates:
        key = (cand.map_constant, cand.x, cand.y)
        if key not in seen:
            seen.add(key)
            distinct.append(cand)

    if len(distinct) == 1:
        return distinct[0]

    chosen = distinct[-1]
    log.info(
        "%s spans %d distinct cells (%s); routing on the terminal row %s at "
        "%s (%d,%d)",
        beat_id,
        len(distinct),
        ", ".join(f"{c.row_id}@{c.map_constant}({c.x},{c.y})" for c in distinct),
        chosen.row_id,
        chosen.map_constant,
        chosen.x,
        chosen.y,
    )
    return chosen


def derive_locations(chapter_id: str,
                     rows: list[ManifestRow],
                     dispositions_path: Path) -> list[BeatLocationRecord]:
    """Every `beat:` disposition in the chapter, resolved to one cell each.

    Iteration is over the MANIFEST, not the dispositions file, so both the
    beat order and each beat's candidate order are manifest order -- stable,
    reviewable, and independent of how the dispositions JSON happens to be
    keyed. That ordering is load-bearing for `choose_routing_point`, which
    reads the last candidate as the beat's terminal row.

    The emitted beat order is NOT a proposed playthrough order. Choosing the
    order is the solver's job, and approving it is yours at STOP 3; this file
    only says where things are.
    """
    dispositions = load_dispositions(dispositions_path)
    known_rows = {row.row_id for row in rows}
    for row_id, disp in dispositions.items():
        if disp.verdict == _BEAT_VERDICT and row_id not in known_rows:
            raise ValueError(
                f"disposition names row {row_id!r}, which is not in the "
                "manifest -- regenerate the manifest or fix the disposition"
            )

    claimed: dict[str, list[RowCell]] = {}
    order: list[str] = []
    for row in rows:
        disp = dispositions.get(row.row_id)
        if disp is None or disp.verdict != _BEAT_VERDICT:
            continue
        beat_id = disp.argument
        if not beat_id:
            raise ValueError(
                f"{row.row_id}: verdict 'beat' with no beat id -- "
                "Disposition.parse should have rejected this")
        if beat_id not in claimed:
            claimed[beat_id] = []
            order.append(beat_id)
        claimed[beat_id].append(cell_for_row(row))

    records: list[BeatLocationRecord] = []
    for beat_id in order:
        candidates = tuple(claimed[beat_id])
        chosen = choose_routing_point(beat_id, candidates)
        records.append(BeatLocationRecord(
            beat_id=beat_id,
            map_constant=chosen.map_constant,
            x=chosen.x,
            y=chosen.y,
            resolver=chosen.resolver,
            rows=tuple(c.row_id for c in candidates),
            candidates=candidates,
            approach_candidates=chosen.approach_candidates,
        ))
    return records


# --------------------------------------------------------------------------
# persistence + the synthetic Chapter
# --------------------------------------------------------------------------

def locations_path(chapter_id: str) -> Path:
    return Path("reference/routes") / f"{chapter_id}.locations.json"


def write_locations(chapter_id: str,
                    records: list[BeatLocationRecord],
                    path: Path) -> None:
    payload = {
        "chapter": chapter_id,
        "beats": [
            {
                "beat_id": r.beat_id,
                "map_constant": r.map_constant,
                "x": r.x,
                "y": r.y,
                "resolver": r.resolver,
                "rows": list(r.rows),
                "candidates": [
                    {"row_id": c.row_id, "map_constant": c.map_constant,
                     "x": c.x, "y": c.y, "resolver": c.resolver}
                    for c in r.candidates
                ],
                **(
                    {"approach_candidates": [
                        {"x": a.x, "y": a.y, "side": a.side, "resolver": a.resolver}
                        for a in r.approach_candidates
                    ]}
                    if r.approach_candidates else {}
                ),
            }
            for r in records
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


def load_locations(path: Path) -> tuple[str, list[BeatLocationRecord]]:
    with path.open(encoding="utf-8") as f:
        payload = json.load(f)
    records = [
        BeatLocationRecord(
            beat_id=b["beat_id"],
            map_constant=b["map_constant"],
            x=b["x"],
            y=b["y"],
            resolver=b["resolver"],
            rows=tuple(b["rows"]),
            candidates=tuple(
                RowCell(c["row_id"], c["map_constant"], c["x"], c["y"],
                        c["resolver"])
                for c in b.get("candidates", ())
            ),
            approach_candidates=tuple(
                ApproachCandidate(a["x"], a["y"], a["side"], a["resolver"])
                for a in b.get("approach_candidates", ())
            ),
        )
        for b in payload["beats"]
    ]
    return payload["chapter"], records


def chapter_from_locations(chapter_id: str,
                           records: list[BeatLocationRecord]) -> _chapter.Chapter:
    """Materialize the locations file as an in-memory `Chapter`.

    This is what keeps `solver.py` untouched: the solver wants a `Chapter`
    with located beats, so we hand it one built from the derived file
    instead of from `chapters/<id>.py`. The beat bodies raise -- this
    chapter is for the offline solve only and must never be run.
    """
    builder = _chapter.ChapterBuilder(
        chapter_id, doc=f"derived locations for {chapter_id}")

    def _never_run(beat_id: str):
        def _fn(emu) -> None:
            raise RuntimeError(
                f"{chapter_id} beat {beat_id} came from a derived locations "
                "file and has no body -- this Chapter exists only for the "
                "offline route solve, never for a run"
            )
        return _fn

    for record in records:
        builder.beat(
            record.beat_id,
            f"derived from {', '.join(record.rows)}",
            map_constant=record.map_constant,
            at=(record.x, record.y),
            rows=record.rows,
        )(_never_run(record.beat_id))
    return builder.build()
