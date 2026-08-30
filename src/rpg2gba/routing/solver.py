"""Offline route solver — turns a `Chapter` (beats/groups) into a `RoutePlan`.

Builds one route node per `BeatGroup` (plus a fixed entry and exit node),
derives `PrecedenceEdge`s from the chapter manifest's recorded self-switch
read/write pairs, and orders the group nodes to minimize tile cost subject to
those precedence constraints and a strong bias against crossing a foreign
trigger tile.

Algorithm, exactly as approved by the operator: **precedence-respecting
greedy nearest-neighbour seed, then 2-opt improvement over precedence-
feasible reversals**, deterministic throughout (fixed tie-break order, no
set/dict iteration leaking into a choice). See `solve_route`'s docstring for
the full contract.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..chapter_manifest.schema import ManifestRow
from ..playtest.chapter import Beat, BeatGroup, BeatLocation, Chapter
from ..tileset_converter.map_constants import DEFAULT_STATE_PATH, MapConstantRegistry
from ..traversal.graph import Cell, MapGraph
from ..traversal.triggers import TriggerOverlay
from ..traversal.world import WorldGraph

from .pathing import RoutePlanningError, SegmentResult, plan_segment
from .plan import PrecedenceEdge, RouteNode, RoutePlan, RouteSegment

logger = logging.getLogger(__name__)

# A search-time bias only: added to a candidate edge's score so the solver
# strictly prefers any crossing-free ordering over any ordering that forces a
# foreign-trigger crossing, while still being able to return *something* when
# a chapter's geography makes a crossing unavoidable. Never added to the
# `RoutePlan.tile_cost` that ships in the final artifact -- that field is the
# true sum of `RouteSegment.tile_count`.
_CROSSING_PENALTY = 10_000

# Hard cap on 2-opt improvement passes, so the solver always terminates even
# if (due to a bug) it were to oscillate. A real chapter's group count is
# small (single digits to low tens), so this is far beyond what a converging
# search would ever need.
_TWO_OPT_MAX_PASSES = 200


class RouteSolverError(ValueError):
    """The route solver could not produce a plan for a chapter."""


@dataclass(frozen=True)
class _GroupPoint:
    group_id: str
    beats: tuple[str, ...]
    rows: tuple[str, ...]
    map_id: int
    cell: Cell


def _default_map_ids() -> dict[str, int]:
    """Load the persisted `MAP_*` -> Uranium id table from its default state
    path (`output/uranium-build/porymap/map_constants.json`), the same
    registry `tileset_converter.map_constants` mints (CLAUDE.md §4.3 -- one
    source of truth for map names). Fails loud (via `MapConstantRegistry`) if
    the caller needs this and hasn't supplied `map_ids=` explicitly."""
    registry = MapConstantRegistry(state_path=DEFAULT_STATE_PATH)
    registry.load()
    return registry.map_const_to_uranium_id()


def _resolve_point(
    location: BeatLocation, *, map_ids: Mapping[str, int], context: str,
) -> tuple[int, Cell]:
    map_id = map_ids.get(location.map_constant)
    if map_id is None:
        raise RouteSolverError(
            f"{context}: map_constant {location.map_constant!r} does not resolve "
            "to any minted Uranium map id"
        )
    return map_id, (location.x, location.y)


def _resolve_group_point(
    group: BeatGroup, *, beat_by_name: Mapping[str, Beat], map_ids: Mapping[str, int],
) -> _GroupPoint:
    """The group's interaction cell: the FIRST `BeatLocation` of the first of
    its beats that declares one."""
    location: BeatLocation | None = None
    owning_beat: str | None = None
    for beat_name in group.beats:
        beat = beat_by_name[beat_name]
        if beat.locations:
            location = beat.locations[0]
            owning_beat = beat_name
            break
    if location is None:
        raise RouteSolverError(
            f"group {group.group_id!r} (beats {list(group.beats)}) declares no "
            "location on any of its beats -- cannot be routed"
        )
    map_id, cell = _resolve_point(
        location, map_ids=map_ids,
        context=f"group {group.group_id!r} (beat {owning_beat!r})",
    )
    rows = tuple(sorted({
        row for beat_name in group.beats for row in beat_by_name[beat_name].rows
    }))
    return _GroupPoint(group_id=group.group_id, beats=tuple(group.beats), rows=rows,
                        map_id=map_id, cell=cell)


def _own_beats(chapter: Chapter) -> list[Beat]:
    """`chapter.beats` filtered down to THIS chapter's own beats, excluding
    any prepended via predecessor chaining (`ChapterBuilder(predecessor=...)`
    -- `chapter.py`'s module docstring). An inherited beat's name is always
    `<owner>:<name>` (`_prefix_beat`), so a bare (`":"`-free) name is the
    established convention for "this chapter's own" -- see
    `scripts/map_viewer_events.py`'s `beat_markers()`, which skips the same
    way for the same reason: the owning chapter's own module already reports
    an inherited beat under its bare name, so counting it here too would
    double-count it. A route plan must route only THIS chapter's own beats:
    a predecessor's beats are replay-to-reach-the-state, live on the
    predecessor's own maps, and are already covered by the predecessor's own
    route plan."""
    return [b for b in chapter.beats if ":" not in b.name]


def _default_entry_location(chapter: Chapter, own_beats: Sequence[Beat]) -> BeatLocation:
    if not own_beats:
        raise RouteSolverError(
            f"chapter {chapter.name!r}: has no own beats (only inherited "
            "predecessor beats) -- cannot derive a route entry"
        )
    first = own_beats[0]
    if not first.locations:
        raise RouteSolverError(
            f"chapter {chapter.name!r}: first own beat {first.name!r} declares no "
            "location to use as the route entry; pass entry= explicitly"
        )
    return first.locations[0]


def _default_exit_location(chapter: Chapter, own_beats: Sequence[Beat]) -> BeatLocation:
    if not own_beats:
        raise RouteSolverError(
            f"chapter {chapter.name!r}: has no own beats (only inherited "
            "predecessor beats) -- cannot derive a route exit"
        )
    last = own_beats[-1]
    if not last.locations:
        raise RouteSolverError(
            f"chapter {chapter.name!r}: last own beat {last.name!r} declares no "
            "location to use as the route exit; pass exit_= explicitly"
        )
    return last.locations[-1]


def _derive_precedence(
    manifest_rows: Sequence[ManifestRow], group_by_row: Mapping[str, str],
) -> tuple[PrecedenceEdge, ...]:
    """Derive `PrecedenceEdge`s from recorded self-switch write/read pairs.

    Within one `(map_id, event_id)`, a row whose `condition.self_switch_ch`
    is set depends on the row that WRITES that self switch -- identified by
    `"self_switch_write"` in that row's `effects`. Never derives an edge from
    `page_idx` ordering alone: that's an RGSS editor convention, not a
    recorded dependency.

    Skipped silently when neither side is claimed by any route group
    (nothing to constrain); logged at INFO and skipped when exactly one side
    is claimed and the other is not (can't express a partial edge).
    """
    rows_by_key: dict[tuple[int, int], list[ManifestRow]] = {}
    for row in manifest_rows:
        if row.kind != "page" or row.event_id is None:
            continue
        rows_by_key.setdefault((row.map_id, row.event_id), []).append(row)

    edges: set[PrecedenceEdge] = set()
    for row in manifest_rows:
        if row.kind != "page" or row.condition is None:
            continue
        letter = row.condition.self_switch_ch
        if letter is None:
            continue
        key = (row.map_id, row.event_id)
        writers = [
            r for r in rows_by_key.get(key, ())
            if r.row_id != row.row_id and "self_switch_write" in r.effects
        ]
        after_group = group_by_row.get(row.row_id)
        for writer in writers:
            before_group = group_by_row.get(writer.row_id)
            if before_group is None and after_group is None:
                continue
            if before_group is None or after_group is None:
                logger.info(
                    "precedence: self_switch:%s map%03d/ev%03d -- only one side "
                    "is claimed by a route group (writer=%s, dependent=%s); skipping",
                    letter, row.map_id, row.event_id, writer.row_id, row.row_id,
                )
                continue
            if before_group == after_group:
                continue
            reason = f"self_switch:{letter} map{row.map_id:03d}/ev{row.event_id:03d}"
            edges.add(PrecedenceEdge(before=before_group, after=after_group, reason=reason))

    return tuple(sorted(edges, key=lambda e: (e.before, e.after, e.reason)))


def _point_label(index: int, group_id: str | None) -> str:
    if group_id is not None:
        return f"group {group_id!r}"
    return "entry" if index == 0 else "exit"


def solve_route(
    chapter: Chapter,
    chapter_id: str,
    *,
    manifest_rows: Sequence[ManifestRow],
    graphs: Mapping[int, MapGraph],
    overlays: Mapping[int, TriggerOverlay],
    world: WorldGraph | None = None,
    entry: tuple[int, Cell] | None = None,
    exit_: tuple[int, Cell] | None = None,
    map_ids: Mapping[str, int] | None = None,
    destination_scripts: frozenset[str] = frozenset(),
) -> RoutePlan:
    """Solve a walk order over `chapter`'s OWN beat groups and return a `RoutePlan`.

    Only `chapter`'s own groups are routed -- any beats/groups prepended via
    `ChapterBuilder(predecessor=...)` chaining (bare-name-less, `<owner>:
    <name>`, see `_own_beats`) are skipped, whether or not they carry a
    location: they belong to another chapter's own route plan. Raises
    `RouteSolverError` if `chapter` has no own groups at all.

    `entry`/`exit_` are `(map_id, cell)` overrides; by default the entry is
    the chapter's own first beat's first declared location and the exit is
    its own last beat's last declared location (both resolved through
    `map_ids`, CLAUDE.md §4.3's map-constant registry -- pass `map_ids=`
    explicitly to avoid touching the real persisted state, e.g. in tests).
    This is deliberate, not merely a filtering side effect: the boot-walk
    harness seeds a chapter from the previous chapter's own end state, so a
    chapter's route legitimately starts at its own first beat, not its
    predecessor's.

    `destination_scripts` is forwarded to `pathing.plan_segment` unchanged:
    the set of this chapter's own trigger scripts that a route may cross
    freely (not "foreign"). Defaults to none, so every trigger this chapter
    doesn't explicitly own is avoided when possible.

    Method: **precedence-respecting greedy nearest-neighbour seed, then
    2-opt improvement over precedence-feasible reversals.** Entry is fixed
    first, exit fixed last; every pairwise cost between two nodes is
    `plan_segment(...).tile_count`, cached once and reused throughout (the
    expensive part). A segment with any trigger crossing is scored with an
    additive `_CROSSING_PENALTY` during search only, so a crossing-free
    ordering always beats a crossing ordering when either is feasible -- but
    `RoutePlan.tile_cost` is the true sum of `RouteSegment.tile_count`, never
    including the penalty. A node pair `plan_segment` cannot route at all
    scores as infinite and is never selected; if the greedy seed cannot find
    any next node to visit, or precedence has no available group left to
    place (a cycle), this raises `RouteSolverError` naming the stuck point.
    2-opt then repeatedly looks for a precedence-legal reversal that strictly
    lowers total cost, in a fixed deterministic candidate order, until no
    reversal improves or `_TWO_OPT_MAX_PASSES` is hit.

    `solver_method` on the returned plan is always `"greedy+2opt"`.
    """
    effective_map_ids = map_ids if map_ids is not None else _default_map_ids()

    beat_by_name: dict[str, Beat] = {b.name: b for b in chapter.beats}
    own_beats = _own_beats(chapter)

    # Predecessor chaining (`ChapterBuilder(predecessor=...)`) prepends the
    # predecessor chapter's beats, transitively, renamed `<owner>:<name>` --
    # `chapter.groups()` therefore returns groups for those inherited beats
    # too. Routing them here would be wrong even when they carry a location:
    # they sit on another chapter's maps, are replay-to-reach-the-state, and
    # are already covered by that chapter's own route plan (double-counting
    # otherwise). Keep only this chapter's own (bare-named) groups -- see
    # `_own_beats`'s docstring for the naming convention and its precedent.
    groups = [g for g in chapter.groups() if ":" not in g.group_id]
    if not groups:
        raise RouteSolverError(
            f"chapter {chapter.name!r}: has no own groups to route -- every "
            "group belongs to an inherited predecessor chapter"
        )

    group_points = [
        _resolve_group_point(g, beat_by_name=beat_by_name, map_ids=effective_map_ids)
        for g in groups
    ]

    entry_map, entry_cell = (
        entry if entry is not None
        else _resolve_point(
            _default_entry_location(chapter, own_beats), map_ids=effective_map_ids,
            context="chapter entry",
        )
    )
    exit_map, exit_cell = (
        exit_ if exit_ is not None
        else _resolve_point(
            _default_exit_location(chapter, own_beats), map_ids=effective_map_ids,
            context="chapter exit",
        )
    )

    # points[0] = entry, points[1..k] = group points (in groups() order),
    # points[-1] = exit.
    points: list[tuple[int, Cell]] = (
        [(entry_map, entry_cell)]
        + [(gp.map_id, gp.cell) for gp in group_points]
        + [(exit_map, exit_cell)]
    )
    n = len(points)
    group_indices = list(range(1, n - 1))  # point indices that are groups
    group_id_at: dict[int, str] = {
        idx: group_points[idx - 1].group_id for idx in group_indices
    }
    original_order: dict[int, int] = {idx: pos for pos, idx in enumerate(group_indices)}

    group_by_row: dict[str, str] = {}
    for gp in group_points:
        for row_id in gp.rows:
            group_by_row[row_id] = gp.group_id
    precedence = _derive_precedence(manifest_rows, group_by_row)

    # Precedence edges as point-index pairs (before_point, after_point).
    point_by_group: dict[str, int] = {gid: idx for idx, gid in group_id_at.items()}
    precedence_point_pairs = [
        (point_by_group[edge.before], point_by_group[edge.after]) for edge in precedence
    ]
    preds_of: dict[int, set[int]] = {idx: set() for idx in group_indices}
    for before_idx, after_idx in precedence_point_pairs:
        preds_of[after_idx].add(before_idx)

    # --- pairwise cost cache ------------------------------------------------

    cache: dict[tuple[int, int], SegmentResult | None] = {}

    def segment_between(i: int, j: int) -> SegmentResult | None:
        key = (i, j)
        if key in cache:
            return cache[key]
        start_map, start_cell = points[i]
        goal_map, goal_cell = points[j]
        try:
            result = plan_segment(
                start_map, start_cell, goal_map, goal_cell,
                graphs=graphs, overlays=overlays,
                destination_scripts=destination_scripts, world=world,
            )
        except RoutePlanningError:
            result = None
        cache[key] = result
        return result

    def score(i: int, j: int) -> float | None:
        result = segment_between(i, j)
        if result is None:
            return None
        penalty = _CROSSING_PENALTY if result.crossings else 0
        return result.tile_count + penalty

    # --- greedy nearest-neighbour seed, precedence-respecting ---------------

    placed: list[int] = [0]
    placed_set: set[int] = {0}
    remaining: set[int] = set(group_indices)

    while remaining:
        current = placed[-1]
        available = sorted(
            (idx for idx in remaining if preds_of[idx] <= placed_set),
            key=lambda idx: original_order[idx],
        )
        if not available:
            raise RouteSolverError(
                f"chapter {chapter_id}: precedence has no available group to place "
                f"next (cycle among {sorted(group_id_at[i] for i in remaining)}); "
                f"precedence edges: {[e.reason for e in precedence]}"
            )
        scored = [(score(current, idx), idx) for idx in available]
        finite = [(s, idx) for s, idx in scored if s is not None]
        if not finite:
            raise RouteSolverError(
                f"chapter {chapter_id}: greedy seed dead-ended -- no route from "
                f"{_point_label(current, group_id_at.get(current))} to any of "
                f"{[group_id_at[idx] for idx in available]}"
            )
        _, chosen = min(finite, key=lambda pair: (pair[0], original_order[pair[1]]))
        placed.append(chosen)
        placed_set.add(chosen)
        remaining.discard(chosen)

    last = placed[-1]
    if score(last, n - 1) is None:
        raise RouteSolverError(
            f"chapter {chapter_id}: greedy seed dead-ended -- no route from "
            f"{_point_label(last, group_id_at.get(last))} to exit"
        )

    sequence: list[int] = [0] + placed[1:] + [n - 1]

    # --- 2-opt improvement over precedence-feasible reversals ---------------

    def total_cost(seq: list[int]) -> float | None:
        total = 0.0
        for a, b in zip(seq, seq[1:]):
            s = score(a, b)
            if s is None:
                return None
            total += s
        return total

    def precedence_ok(seq: list[int]) -> bool:
        pos = {point: i for i, point in enumerate(seq)}
        return all(pos[before] < pos[after] for before, after in precedence_point_pairs)

    passes = 0
    improved = True
    current_cost = total_cost(sequence)
    while improved and passes < _TWO_OPT_MAX_PASSES:
        improved = False
        passes += 1
        for i in range(1, len(sequence) - 2):
            for j in range(i + 1, len(sequence) - 1):
                candidate = sequence[:i] + list(reversed(sequence[i:j + 1])) + sequence[j + 1:]
                if not precedence_ok(candidate):
                    continue
                candidate_cost = total_cost(candidate)
                if candidate_cost is None:
                    continue
                if candidate_cost < current_cost:
                    sequence = candidate
                    current_cost = candidate_cost
                    improved = True
                    break
            if improved:
                break

    # --- build the final plan -------------------------------------------

    nodes: list[RouteNode] = [RouteNode(index=0, kind="entry", map_id=entry_map, cell=entry_cell)]
    for pos, point_idx in enumerate(sequence[1:-1], start=1):
        gp = group_points[point_idx - 1]
        nodes.append(RouteNode(
            index=pos, kind="group", map_id=gp.map_id, cell=gp.cell,
            group=gp.group_id, beats=gp.beats, rows=gp.rows,
        ))
    nodes.append(RouteNode(
        index=len(sequence) - 1, kind="exit", map_id=exit_map, cell=exit_cell,
    ))

    segments: list[RouteSegment] = []
    for pos in range(len(sequence) - 1):
        a, b = sequence[pos], sequence[pos + 1]
        result = segment_between(a, b)
        if result is None:
            raise RouteSolverError(
                f"chapter {chapter_id}: internal error -- selected an unroutable "
                f"segment {_point_label(a, group_id_at.get(a))} -> "
                f"{_point_label(b, group_id_at.get(b))}"
            )
        segments.append(RouteSegment(
            from_index=pos, to_index=pos + 1, legs=result.legs,
            tile_count=result.tile_count, crossed_foreign_triggers=result.crossings,
        ))

    tile_cost = sum(s.tile_count for s in segments)

    return RoutePlan(
        chapter_id=chapter_id,
        chapter_module=chapter.name,
        nodes=tuple(nodes),
        segments=tuple(segments),
        precedence=precedence,
        tile_cost=tile_cost,
        solver_method="greedy+2opt",
    )
