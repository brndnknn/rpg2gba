"""Offline route solver — turns a `Chapter` (beats/groups) into a `RoutePlan`.

Builds one route node per `BeatGroup` (plus a fixed entry and exit node),
derives `PrecedenceEdge`s from two sources -- the chapter manifest's recorded
self-switch read/write pairs, and the corpus-wide warp topology (`world`,
see `_derive_warp_precedence`) -- and orders the group nodes to minimize tile
cost subject to those precedence constraints and a strong bias against
crossing a foreign trigger tile.

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
from ..playtest.chapter import Beat, BeatGroup, BeatLocation, Chapter, resolved_trigger_scripts
from ..tileset_converter.map_constants import DEFAULT_STATE_PATH, MapConstantRegistry
from ..traversal.graph import Cell, MapGraph
from ..traversal.triggers import TriggerOverlay
from ..traversal.world import WorldGraph
from .occupancy import MapOccupancy
from .pathing import RoutePlanningError, SegmentResult, plan_segment
from .plan import ChosenApproach, PrecedenceEdge, RouteNode, RoutePlan, RouteSegment

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


@dataclass(frozen=True)
class RouteCandidate:
    """One legal SIDE a group's beat could be approached/used from, handed
    in by the caller via `solve_route`'s `candidates=` mapping (built from
    `routing.locations.ApproachCandidate` for the derived-locations path --
    see `routing/__main__.py`'s `plan` command).

    Kept decoupled from `routing.locations.ApproachCandidate` (rather than
    imported) so `solver.py` has no dependency on `locations.py`; the two
    shapes are identical by convention, not by inheritance.
    """

    x: int
    y: int
    side: str
    resolver: str


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
    """Where the chapter's route starts.

    A declared `Chapter.route_entry` wins outright. Otherwise this falls back
    to the first own beat's first location, which is the same cell the solver
    uses as that group's INTERACTION point -- the one later segments are
    costed from. That conflation is fine for a beat that begins where it acts,
    and wrong for one that begins on the far side of its own warp
    (`warp_beat(start_side="dest")`): CH05's B1 acts on the cave's exit warp
    but the chapter begins on Route 02. See `Chapter.route_entry` for the
    measured cost of overloading the one field.
    """
    if chapter.route_entry is not None:
        return chapter.route_entry
    if not own_beats:
        raise RouteSolverError(
            f"chapter {chapter.name!r}: has no own beats (only inherited "
            "predecessor beats) -- cannot derive a route entry"
        )
    first = own_beats[0]
    if not first.locations:
        raise RouteSolverError(
            f"chapter {chapter.name!r}: first own beat {first.name!r} declares no "
            "location to use as the route entry, and the chapter declares no "
            "route_entry=; pass entry= explicitly"
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


def _derive_warp_precedence(
    manifest_rows: Sequence[ManifestRow],
    group_by_row: Mapping[str, str],
    group_points: Sequence[_GroupPoint],
    world: WorldGraph | None,
    *,
    entry_map: int,
    entry_group_id: str | None,
    chapter_id: str,
    exit_provided: bool,
) -> tuple[tuple[PrecedenceEdge, ...], tuple[int, Cell] | None]:
    """Derive `PrecedenceEdge`s from warp topology, plus this chapter's
    terminal boundary group's own point if one is identifiable.

    Returns `((), None)` when `world` is None: no warp precedence can be
    derived without the corpus-wide map graph.

    `exit_provided` is whether the caller already passed an explicit `exit_=`
    to `solve_route`. When true, rule 2 (below) is skipped entirely -- no
    terminal-group detection, no rule-2 edges, and critically no ambiguity
    raise: an explicit `exit_=` is itself the disambiguation the ambiguous
    case exists to demand, so re-deriving (and possibly rejecting) a terminal
    group the caller didn't ask for would be wrong. Rule 1 always runs
    regardless of `exit_provided`.

    A "chapter map" is any map a `group_points` entry sits on, plus
    `entry_map`. A group "owns a warp landing on map X" when one of its rows
    is a warp row (`row.kind == "page"` and `"warp" in row.effects`) whose
    `(row.map_id, row.event_id)` resolves, through `world.edges_from(row.
    map_id)`, to a `WorldEdge` of kind "warp" with `dst_map == X`.

    Rule 1 (introducing-warp precedence): for each chapter map X other than
    `entry_map`, find the groups that own a warp landing on X from a chapter
    map. If exactly one such group G exists, every OTHER group located on X
    must come after G (reason `warp_topology:mapNNN`). Zero or 2+ candidates
    means the constraint can't be expressed singularly; logged at INFO and
    skipped for that map, same discipline as `_derive_precedence`.

    Rule 2 (terminal boundary group): a candidate terminal group is one that
    owns a warp landing OUTSIDE the chapter's map set, excluding
    `entry_group_id` (the chapter's own entry warp always points back at the
    predecessor map and must never be treated as the exit). Exactly one
    candidate T means every other group must come before T (reason
    `warp_boundary:mapNNN`, NNN = T's destination map), and T's own
    `(map_id, cell)` is returned as the route's terminal point. Two or more
    candidates raises `RouteSolverError` naming each candidate and its
    destination -- the caller must disambiguate with an explicit `exit_=`.
    Zero candidates returns no rule-2 edges and `terminal_point=None`.
    """
    if world is None:
        return (), None

    map_by_group: dict[str, int] = {gp.group_id: gp.map_id for gp in group_points}
    chapter_maps: set[int] = set(map_by_group.values()) | {entry_map}

    # dst_map -> group_ids owning a warp row that lands on dst_map from a
    # chapter map.
    introducers: dict[int, set[str]] = {}
    # group_id -> dst_maps (outside the chapter) it owns a warp row landing on.
    outbound: dict[str, set[int]] = {}

    for row in manifest_rows:
        if row.kind != "page" or "warp" not in row.effects or row.event_id is None:
            continue
        if row.map_id not in chapter_maps:
            continue
        group_id = group_by_row.get(row.row_id)
        if group_id is None:
            continue
        for edge in world.edges_from(row.map_id):
            if edge.kind != "warp" or edge.event_id != row.event_id:
                continue
            introducers.setdefault(edge.dst_map, set()).add(group_id)
            if edge.dst_map not in chapter_maps:
                outbound.setdefault(group_id, set()).add(edge.dst_map)

    edges: set[PrecedenceEdge] = set()

    # --- rule 1: introducing-warp precedence --------------------------------

    # A map needs an "introducing" warp only if the chapter has to let itself
    # in. Two maps never do: the one the chapter STARTS on, and the one its
    # declared entry warp LANDS on -- reaching that one is what starting there
    # means.
    #
    # Missing the second is not a tie-break, it derives an impossible order.
    # CH05 enters the Passage Cave from Route 02, and its entry beat B1 claims
    # `map036/ev001` -- the cave's OUTBOUND event, because that is the only row
    # CH05's manifest owns at that seam. So B1 does not look like a way *in*,
    # the rule credited B8 (the 1F<->2F stairs, whose reciprocal does land on
    # map 36) and emitted `B8 -> B1`: use the stairs before entering the cave.
    # That forced the whole 1F sweep to run north-first and cross a trainer's
    # trigger tile twice. While the entry was inside the cave this was masked,
    # because `entry_map` alone already skipped map 36.
    # Keyed on the entry MAP, not the entry cell: standing anywhere on map X
    # you can walk to any warp on map X and cross it, so nothing has to
    # "introduce" what X warps to. Keying it on the cell was too narrow -- it
    # held only while the chapter's declared entry happened to BE the warp
    # tile, and stopped applying the moment CH05's entry became the cell CH04
    # actually hands over on, two dozen tiles short of the cave mouth.
    #
    # Maps deeper in are unaffected: map 37 is reachable only through map 36,
    # never from the entry map, so it still requires its introducing warp.
    entry_landing_maps: set[int] = set()
    if world is not None:
        for edge in world.edges_from(entry_map):
            if edge.kind in ("warp", "seam_warp"):
                entry_landing_maps.add(edge.dst_map)

    for map_id in sorted(chapter_maps - {entry_map} - entry_landing_maps):
        candidates = introducers.get(map_id, set())
        if len(candidates) != 1:
            logger.info(
                "precedence: warp_topology:map%03d -- %d group(s) own a warp "
                "landing on map %d from within the chapter (%s); need exactly "
                "one to derive an introducing-warp edge, skipping",
                map_id, len(candidates), map_id, sorted(candidates),
            )
            continue
        (introducer,) = candidates
        for gp in group_points:
            if gp.map_id == map_id and gp.group_id != introducer:
                edges.add(PrecedenceEdge(
                    before=introducer, after=gp.group_id,
                    reason=f"warp_topology:map{map_id:03d}",
                ))

    # --- rule 2: terminal boundary group ------------------------------------

    terminal_point: tuple[int, Cell] | None = None
    if exit_provided:
        return tuple(sorted(edges, key=lambda e: (e.before, e.after, e.reason))), terminal_point

    candidates = {g: dsts for g, dsts in outbound.items() if g != entry_group_id}
    if len(candidates) == 1:
        (terminal_group, dsts), = candidates.items()
        dst_map = min(dsts)
        for gp in group_points:
            if gp.group_id != terminal_group:
                edges.add(PrecedenceEdge(
                    before=gp.group_id, after=terminal_group,
                    reason=f"warp_boundary:map{dst_map:03d}",
                ))
        terminal_gp = next(gp for gp in group_points if gp.group_id == terminal_group)
        terminal_point = (terminal_gp.map_id, terminal_gp.cell)
    elif len(candidates) >= 2:
        detail = ", ".join(
            f"{g!r} (-> map{min(dsts):03d})" for g, dsts in sorted(candidates.items())
        )
        raise RouteSolverError(
            f"chapter {chapter_id}: {len(candidates)} groups each own an outbound "
            f"warp leaving the chapter's own maps ({detail}) -- cannot pick a "
            "single terminal group; pass exit_= explicitly to disambiguate"
        )

    return tuple(sorted(edges, key=lambda e: (e.before, e.after, e.reason))), terminal_point


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
    occupancy: Mapping[int, MapOccupancy] | None = None,
    candidates: Mapping[str, tuple[RouteCandidate, ...]] | None = None,
) -> RoutePlan:
    """Solve a walk order over `chapter`'s OWN beat groups and return a `RoutePlan`.

    Only `chapter`'s own groups are routed -- any beats/groups prepended via
    `ChapterBuilder(predecessor=...)` chaining (bare-name-less, `<owner>:
    <name>`, see `_own_beats`) are skipped, whether or not they carry a
    location: they belong to another chapter's own route plan. Raises
    `RouteSolverError` if `chapter` has no own groups at all.

    `entry`/`exit_` are `(map_id, cell)` overrides; by default the entry is
    the chapter's own first beat's first declared location (resolved through
    `map_ids`, CLAUDE.md §4.3's map-constant registry -- pass `map_ids=`
    explicitly to avoid touching the real persisted state, e.g. in tests).
    This is deliberate, not merely a filtering side effect: the boot-walk
    harness seeds a chapter from the previous chapter's own end state, so a
    chapter's route legitimately starts at its own first beat, not its
    predecessor's.

    The default exit, absent an explicit `exit_=`, is no longer simply "the
    chapter's own last beat's last declared location": if warp topology
    (`world`, see `_derive_warp_precedence`) identifies exactly one group that
    owns a warp leaving the chapter's own maps (excluding the entry group),
    that group's own point becomes the exit -- forcing that group last
    without also walking back to an unrelated cell afterward. Only when no
    such single terminal group is identifiable does the exit fall back to the
    last-own-beat's-last-location default.

    Also raises `RouteSolverError` if, absent an explicit `exit_=`, warp
    topology identifies two or more candidate terminal groups (each owning a
    warp leaving the chapter's own maps) -- passing `exit_=` explicitly
    disambiguates and suppresses this check entirely (see
    `_derive_warp_precedence`).

    `destination_scripts` is forwarded to `pathing.plan_segment` unchanged:
    the set of this chapter's own trigger scripts that a route may cross
    freely (not "foreign"). Defaults to none, so every trigger this chapter
    doesn't explicitly own is avoided when possible.

    `occupancy` (per map id, `routing.occupancy.MapOccupancy`) is likewise
    forwarded to `pathing.plan_segment` unchanged: stationary-NPC tiles that
    hard-block every segment's tile-level path, on both the preferred and
    fallback route. Defaults to `None` (no occupancy data, current behaviour
    unchanged) -- pass it explicitly to route around real NPC occupancy.

    `candidates` (group id -> tuple of `RouteCandidate`, i.e. legal SIDES of
    that group's own cell) breaks the circularity that a resolver like
    `approach_to`/`stair_approach` used to resolve on its own: rather than a
    fixed N/S/E/W (or west-then-east) tiebreak deciding which side a beat is
    approached from, the group carries every legal side and the solver picks
    among them AS PART OF ordering -- see the layered-DP note below. Defaults
    to `None` (equivalent to an empty mapping): every group not present (or
    mapped to an empty/falsy tuple) keeps exactly one site, its own
    `_resolve_group_point` cell, reproducing today's behaviour exactly.
    Candidate cells occupied by a stationary NPC (`occupancy`) are dropped
    before solving; if EVERY candidate for a group is occupied, this raises
    `RouteSolverError` naming the group, its beats, and the blocking NPC(s)
    -- never silently falls back to a blocked cell. The chosen side (if any)
    is recorded on the corresponding `RouteNode.chosen_approach`.

    Method: **precedence-respecting greedy nearest-neighbour seed, then
    2-opt improvement over precedence-feasible reversals -- both scored
    through a layered DP over candidate sites, never a per-step greedy
    candidate pick.** Entry is fixed first, exit fixed last. For any FIXED
    order of groups, each group contributes one "layer" of candidate cells
    (its own single cell, or every entry in `candidates[group_id]` with
    occupied cells dropped); the true cost of that order is the shortest
    path through this layered DAG, edge weights being
    `plan_segment(...).tile_count` (+ `_CROSSING_PENALTY` for a foreign-
    trigger crossing, search-time only, never in the final `tile_cost`)
    between adjacent layers' candidates. The greedy seed extends this DP one
    layer at a time as it places each next group (an O(1)-per-candidate
    incremental step, not a full re-solve); 2-opt re-runs the full DP for
    every candidate reversal it considers. Every pairwise
    `plan_segment(...)` call, keyed by `(point_index, cell, point_index,
    cell)`, is cached once and reused for the rest of the solve -- never
    recomputed inside the DP or the 2-opt loop. Ties break deterministically
    toward the earlier candidate in `candidates[group_id]`'s own order (the
    callers of `solve_route` are expected to supply that order already
    N/S/E/W or west-then-east, per `routing.locations.ApproachCandidate`).

    A node pair `plan_segment` cannot route at all scores as infinite and is
    never selected; if the greedy seed cannot find any next node to visit,
    or precedence has no available group left to place (a cycle), this
    raises `RouteSolverError` naming the stuck point. 2-opt then repeatedly
    looks for a precedence-legal reversal that strictly lowers total cost,
    in a fixed deterministic candidate order, until no reversal improves or
    `_TWO_OPT_MAX_PASSES` is hit.

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

    # A trigger a predecessor's beat already resolved is not foreign to this
    # chapter (`playtest.chapter.resolved_trigger_scripts`). CH05 must pass
    # Timothy's event-touch tile to reach the cave at all -- `plan_segment`
    # tries a trigger-free path first and there is none -- and CH04:B4 has
    # already defeated him by then, so the tile fires nothing.
    resolved_scripts = resolved_trigger_scripts(chapter)
    effective_destination_scripts = frozenset(destination_scripts) | {
        script for scripts in resolved_scripts.values() for script in scripts
    }

    group_by_row: dict[str, str] = {}
    for gp in group_points:
        for row_id in gp.rows:
            group_by_row[row_id] = gp.group_id
    self_switch_precedence = _derive_precedence(manifest_rows, group_by_row)

    entry_group_id = next(
        (gp.group_id for gp in group_points if (gp.map_id, gp.cell) == (entry_map, entry_cell)),
        None,
    )
    warp_precedence, terminal_point = _derive_warp_precedence(
        manifest_rows, group_by_row, group_points, world,
        entry_map=entry_map,
        entry_group_id=entry_group_id, chapter_id=chapter_id,
        exit_provided=exit_ is not None,
    )

    if exit_ is not None:
        exit_map, exit_cell = exit_
    elif terminal_point is not None:
        exit_map, exit_cell = terminal_point
    else:
        exit_map, exit_cell = _resolve_point(
            _default_exit_location(chapter, own_beats), map_ids=effective_map_ids,
            context="chapter exit",
        )

    precedence = tuple(sorted(
        set(self_switch_precedence) | set(warp_precedence),
        key=lambda e: (e.before, e.after, e.reason),
    ))

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

    # Precedence edges as point-index pairs (before_point, after_point).
    point_by_group: dict[str, int] = {gid: idx for idx, gid in group_id_at.items()}
    precedence_point_pairs = [
        (point_by_group[edge.before], point_by_group[edge.after]) for edge in precedence
    ]
    preds_of: dict[int, set[int]] = {idx: set() for idx in group_indices}
    for before_idx, after_idx in precedence_point_pairs:
        preds_of[after_idx].add(before_idx)

    # --- candidate sites per point index -------------------------------

    effective_candidates = candidates or {}
    # group_id -> {(x, y): RouteCandidate}, for reattaching side/resolver
    # metadata to whichever cell the DP ends up choosing for that group.
    candidate_meta: dict[str, dict[Cell, RouteCandidate]] = {}

    def _sites_for_group(gp: _GroupPoint) -> tuple[Cell, ...]:
        raw = effective_candidates.get(gp.group_id)
        if not raw:
            return (gp.cell,)
        map_occupancy = occupancy.get(gp.map_id) if occupancy is not None else None
        blocked = map_occupancy.blocked_cells() if map_occupancy is not None else frozenset()
        kept = [c for c in raw if (c.x, c.y) not in blocked]
        if not kept:
            occupants = sorted({
                map_occupancy.at((c.x, c.y)).script
                for c in raw
                if map_occupancy is not None and map_occupancy.at((c.x, c.y)) is not None
            })
            raise RouteSolverError(
                f"chapter {chapter_id}: group {gp.group_id!r} (beats "
                f"{list(gp.beats)}) has {len(raw)} approach candidate(s) "
                f"({[(c.x, c.y, c.side) for c in raw]}), all occupied by "
                f"stationary NPC(s) {occupants} -- cannot route this beat "
                "from any side"
            )
        candidate_meta[gp.group_id] = {(c.x, c.y): c for c in kept}
        return tuple((c.x, c.y) for c in kept)

    site_cells: dict[int, tuple[Cell, ...]] = {0: (entry_cell,)}
    for idx in group_indices:
        site_cells[idx] = _sites_for_group(group_points[idx - 1])
    site_cells[n - 1] = (exit_cell,)

    # --- pairwise cost cache, keyed by (point, cell, point, cell) -----------

    site_cache: dict[tuple[int, Cell, int, Cell], SegmentResult | None] = {}

    def segment_between(i: int, cell_i: Cell, j: int, cell_j: Cell) -> SegmentResult | None:
        key = (i, cell_i, j, cell_j)
        if key in site_cache:
            return site_cache[key]
        start_map = points[i][0]
        goal_map = points[j][0]
        try:
            result = plan_segment(
                start_map, cell_i, goal_map, cell_j,
                graphs=graphs, overlays=overlays,
                destination_scripts=effective_destination_scripts, world=world,
                occupancy=occupancy,
            )
        except RoutePlanningError:
            result = None
        site_cache[key] = result
        return result

    def site_score(i: int, cell_i: Cell, j: int, cell_j: Cell) -> float | None:
        result = segment_between(i, cell_i, j, cell_j)
        if result is None:
            return None
        penalty = _CROSSING_PENALTY if result.crossings else 0
        return result.tile_count + penalty

    # --- greedy nearest-neighbour seed, precedence-respecting ---------------
    #
    # `prev_layer` holds, for the group/point most recently placed, the best
    # DP cost from entry to each of ITS candidate cells. Each step extends
    # this one layer at a time (an O(1)-per-candidate incremental DP step,
    # never a full re-solve, never a per-step greedy candidate pick within a
    # single group -- see `solve_route`'s docstring).

    placed: list[int] = [0]
    placed_set: set[int] = {0}
    remaining: set[int] = set(group_indices)
    prev_layer: dict[Cell, float] = {entry_cell: 0.0}

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

        layer_by_idx: dict[int, dict[Cell, float]] = {}
        scored: list[tuple[float, int]] = []
        for idx in available:
            layer: dict[Cell, float] = {}
            for cell_j in site_cells[idx]:
                best: float | None = None
                for cell_i, cost_i in prev_layer.items():
                    s = site_score(current, cell_i, idx, cell_j)
                    if s is None:
                        continue
                    total = cost_i + s
                    if best is None or total < best:
                        best = total
                if best is not None:
                    layer[cell_j] = best
            if layer:
                layer_by_idx[idx] = layer
                scored.append((min(layer.values()), idx))

        if not scored:
            raise RouteSolverError(
                f"chapter {chapter_id}: greedy seed dead-ended -- no route from "
                f"{_point_label(current, group_id_at.get(current))} to any of "
                f"{[group_id_at[idx] for idx in available]}"
            )
        _, chosen = min(scored, key=lambda pair: (pair[0], original_order[pair[1]]))
        placed.append(chosen)
        placed_set.add(chosen)
        remaining.discard(chosen)
        prev_layer = layer_by_idx[chosen]

    last = placed[-1]
    final_layer: dict[Cell, float] = {}
    for cell_j in site_cells[n - 1]:
        best = None
        for cell_i, cost_i in prev_layer.items():
            s = site_score(last, cell_i, n - 1, cell_j)
            if s is None:
                continue
            total = cost_i + s
            if best is None or total < best:
                best = total
        if best is not None:
            final_layer[cell_j] = best
    if not final_layer:
        raise RouteSolverError(
            f"chapter {chapter_id}: greedy seed dead-ended -- no route from "
            f"{_point_label(last, group_id_at.get(last))} to exit"
        )

    sequence: list[int] = [0] + placed[1:] + [n - 1]

    # --- 2-opt improvement over precedence-feasible reversals ---------------
    #
    # Every candidate order (including the seed itself) is scored by a FULL
    # layered-DP pass over its own point sequence, `_dp_cost` below -- never
    # a per-step greedy candidate pick -- so the order comparison reflects
    # the true optimal arrive+depart cost for each candidate order, not one
    # tied to whichever cell a previous step happened to pick.

    def _dp_cost(seq: list[int]) -> float | None:
        layer: dict[Cell, float] = {site_cells[seq[0]][0]: 0.0}
        for pos in range(1, len(seq)):
            i, j = seq[pos - 1], seq[pos]
            next_layer: dict[Cell, float] = {}
            for cell_j in site_cells[j]:
                best = None
                for cell_i, cost_i in layer.items():
                    s = site_score(i, cell_i, j, cell_j)
                    if s is None:
                        continue
                    total = cost_i + s
                    if best is None or total < best:
                        best = total
                if best is not None:
                    next_layer[cell_j] = best
            if not next_layer:
                return None
            layer = next_layer
        return min(layer.values())

    def total_cost(seq: list[int]) -> float | None:
        return _dp_cost(seq)

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

    # --- final candidate assignment for the chosen order --------------------
    #
    # Re-run the DP once more, with backpointers, to recover WHICH candidate
    # cell was chosen at each position of the final `sequence` -- ties break
    # toward the earlier candidate in `site_cells[j]`'s own order, since a
    # strict `<` keeps the first-seen minimum and both the per-layer and
    # per-predecessor iteration orders are exactly that candidate order.

    def _dp_assignment(seq: list[int]) -> dict[int, Cell]:
        first_site = site_cells[seq[0]][0]
        layer: dict[Cell, float] = {first_site: 0.0}
        backptrs: list[dict[Cell, Cell]] = [{}]
        for pos in range(1, len(seq)):
            i, j = seq[pos - 1], seq[pos]
            next_layer: dict[Cell, float] = {}
            back: dict[Cell, Cell] = {}
            for cell_j in site_cells[j]:
                best = None
                best_prev: Cell | None = None
                for cell_i, cost_i in layer.items():
                    s = site_score(i, cell_i, j, cell_j)
                    if s is None:
                        continue
                    total = cost_i + s
                    if best is None or total < best:
                        best = total
                        best_prev = cell_i
                if best is not None:
                    next_layer[cell_j] = best
                    back[cell_j] = best_prev
            if not next_layer:
                raise RouteSolverError(
                    f"chapter {chapter_id}: internal error -- selected an "
                    f"unroutable transition between sequence position "
                    f"{pos - 1} and {pos}"
                )
            layer = next_layer
            backptrs.append(back)
        chosen: list[Cell] = [(0, 0)] * len(seq)
        chosen[-1] = min(layer, key=lambda c: layer[c])
        for pos in range(len(seq) - 1, 0, -1):
            chosen[pos - 1] = backptrs[pos][chosen[pos]]
        return {seq[pos]: chosen[pos] for pos in range(len(seq))}

    chosen_cell_by_point = _dp_assignment(sequence)

    # --- build the final plan -------------------------------------------

    nodes: list[RouteNode] = [
        RouteNode(index=0, kind="entry", map_id=entry_map, cell=chosen_cell_by_point[0])
    ]
    for pos, point_idx in enumerate(sequence[1:-1], start=1):
        gp = group_points[point_idx - 1]
        cell = chosen_cell_by_point[point_idx]
        chosen_approach: ChosenApproach | None = None
        meta = candidate_meta.get(gp.group_id)
        if meta is not None:
            picked = meta.get(cell)
            if picked is None:
                raise RouteSolverError(
                    f"chapter {chapter_id}: internal error -- chosen cell {cell} "
                    f"for group {gp.group_id!r} is not among its own candidates"
                )
            chosen_approach = ChosenApproach(side=picked.side, resolver=picked.resolver)
        nodes.append(RouteNode(
            index=pos, kind="group", map_id=gp.map_id, cell=cell,
            group=gp.group_id, beats=gp.beats, rows=gp.rows,
            chosen_approach=chosen_approach,
        ))
    nodes.append(RouteNode(
        index=len(sequence) - 1, kind="exit", map_id=exit_map,
        cell=chosen_cell_by_point[n - 1],
    ))

    segments: list[RouteSegment] = []
    for pos in range(len(sequence) - 1):
        a, b = sequence[pos], sequence[pos + 1]
        cell_a = chosen_cell_by_point[a]
        cell_b = chosen_cell_by_point[b]
        result = segment_between(a, cell_a, b, cell_b)
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
