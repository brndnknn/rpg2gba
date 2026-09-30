"""`python -m rpg2gba.beat_gen generate --chapter CHnn` (C6 Task 9).

Ties the stages together and writes:

    chNN.py             the module (emit.py), under `--module-dir`
                        (default `src/rpg2gba/playtest/chapters_gen/`)
    CHnn.review.md      the review doc (review.py), under `--out-dir`
                        (default `output/beats/`)
    CHnn.route.json     the solved route (routing.plan.write_plan), under
                        `--out-dir`

The module lands beside the hand-written suite (`playtest/chapters/`) as a
tracked, loadable sibling package -- `playtest.chapters_gen` -- per the C9
rulings (`REDERIVATION_PLAN.md` §16.3): "no overwrite", one commit per
chapter after the operator approves its review doc. The review doc and
route JSON stay under `output/` (gitignored); only the module itself is
meant to be committed, and only when the operator says so.

STATUS: done (`assignments/C6/09_cli.md`). A warp that leaves the chapter
is a boundary beat (`adapt.is_boundary_warp`, `warp_beat(boundary=True)`).

The solver's argument assembly is imported from `routing/__main__.py`'s
`plan` command rather than copied: the lazy graph/overlay/occupancy views,
the world graph, the MAP_* -> id table and the trigger-overlay check are
one implementation, used by both CLIs (§4.3).
"""
from __future__ import annotations

import dataclasses
import functools
import json
import logging
from collections.abc import Callable, Collection, Mapping, Sequence
from pathlib import Path

import click

from rpg2gba.beat_floor.assertion import RowFloor
from rpg2gba.beat_floor.lookup import floor_for_row
from rpg2gba.beat_floor.walk import floor_for_chapter
from rpg2gba.beat_gen.adapt import (
    NoArrivalError,
    archetype_kwargs,
    escort_kwargs,
    is_boundary_warp,
    route_kwargs,
    warp_candidates,
)
from rpg2gba.beat_gen.arms import annotate_random_arms, blocked_arms, split_choice_arms
from rpg2gba.beat_gen.boundary import inbound_rows, split_outbound
from rpg2gba.beat_gen.continuity import thread_maps
from rpg2gba.beat_gen.interiors import (
    arrival_nudge_edges,
    gated_entry_edges,
    gated_region_check,
    interior_exit_edges,
    region_order_check,
)
from rpg2gba.beat_gen.guard_reach import (
    apply_guard_reach,
    check_guard_order,
    guard_enabled_by,
    guard_reaches,
)
from rpg2gba.beat_gen.liveness_edges import WriteModel, killed_before, split_threshold_enablers
from rpg2gba.beat_gen.moved_objects import scene_moved_events
from rpg2gba.beat_gen.never_fires import (
    MapFacts,
    TOUCH_TRIGGERS,
    coord_cells_by_event,
    never_fires_proof,
)
from rpg2gba.beat_gen.reach import engine_spawn, reachable_sites
from rpg2gba.beat_gen.emit import emit_module
from rpg2gba.beat_gen.facing import (
    event_ids_by_map,
    facing_sides,
    pin_records,
    split_facing_arms,
)
from rpg2gba.beat_gen.gift_ceremony import annotate_gift_ceremonies
from rpg2gba.beat_gen.group import plan_beats
from rpg2gba.beat_gen.locate import locate_beats, order_beats, route_order
from rpg2gba.beat_gen.plan import (
    LivenessProblem,
    ARCHETYPE_TEMPLATES,
    ChapterPlan,
    Elsewhere,
    PlannedBeat,
    Refusal,
    Selection,
    make_kwargs,
)
from rpg2gba.beat_gen.review import RowLocation, render_review
from rpg2gba.beat_gen.seam import SeamCrossing, connection_for, seam_crossings
from rpg2gba.beat_gen.seed import route_winner
from rpg2gba.beat_gen.page_sim import Firing
from rpg2gba.beat_gen.select import empty_events, select_rows
from rpg2gba.beat_gen.round_trip import find_round_trip
from rpg2gba.beat_gen.state_arms import FIRING_TEMPLATES, Taint, fired_pages, select_state_arms
from rpg2gba.conversion_agent.flag_registry import load_label_tables
from rpg2gba.conversion_agent.orchestrator import load_map_event_strips
from rpg2gba.story_state.extract import RowState, extract_map
from rpg2gba.beat_gen.whiteout import place_whiteout_beats
from rpg2gba.chapter_atlas.binding import ChapterBinding, load_binding
from rpg2gba.chapter_manifest.archetypes import ArchetypeMatch, classify_manifest
from rpg2gba.chapter_manifest.schema import ManifestRow, parse_row_id
from rpg2gba.playtest import chapters_gen as playtest_chapters_gen
from rpg2gba.playtest.archetypes import load_chapter_rows, map_uranium_id
from rpg2gba.playtest.chapter import load_chapter
from rpg2gba.routing.__main__ import (
    DEFAULT_CHAPTERS_PATH,
    _build_graphs_and_overlays,
    _build_world,
    _check_trigger_overlay_or_raise,
    _LazyOccupancy,
    _load_map_ids,
)
from rpg2gba.routing.locations import (
    ApproachCandidate,
    BeatLocationRecord,
    RowCell,
    _map_constant_for,  # the one MAP_* lookup; `cell_for_row` uses it too
    cell_for_row,
    chapter_from_locations,
)
from rpg2gba.routing.occupancy import _load_emitted_map, _load_map_constants_entry
from rpg2gba.routing.pathing import RoutePlanningError, landing_cell
from rpg2gba.routing.plan import write_plan
from rpg2gba.routing.solver import RouteCandidate, solve_route
from rpg2gba.story_state.model import (
    RowVerdict,
    State,
    _cmp,
    _default_value,
    _state_key_repr,
    build_chapter_stories,
)
from rpg2gba.tileset_converter.map_constants import load_display_names
from rpg2gba.traversal.collision import load_map_json
from rpg2gba.traversal.graph import MapGraph
from rpg2gba.traversal.triggers import DEFAULT_ENGINE_MAPS_DIR
from rpg2gba.traversal.world import WorldGraph

logger = logging.getLogger(__name__)

BUILD_DIR = Path("output/uranium-build")
MAP_NAME_OVERRIDES = Path("reference") / "map_name_overrides.json"
DEFAULT_OUT_DIR = Path("output/beats")
# Derived from the package's own __file__, not a cwd-relative string, so
# `generate` writes to the right place regardless of invocation directory.
DEFAULT_MODULE_DIR = Path(playtest_chapters_gen.__file__).parent


def _chain_to(binding: ChapterBinding, chapter_id: str) -> list[str]:
    """The chapter ids from the chain's root up to and including
    `chapter_id`: `build_chapter_stories` seeds each chapter from its
    predecessor's end state, so it needs the whole chain, not one id."""
    chain: list[str] = []
    current: str | None = chapter_id
    while current is not None:
        if current in chain:
            raise ValueError(f"{chapter_id}: predecessor cycle through {current}")
        chain.append(current)
        current = binding.chapter(current).predecessor
    return chain[::-1]


def _battle_on_page(match: ArchetypeMatch, floors: Mapping[str, RowFloor]) -> bool:
    page = next(rid for rid, role in match.roles.items() if role == "battle")
    return page in floors and any(a.kind == "battle" for a in floors[page].assertions)


def _generic_reads_it_better(match: ArchetypeMatch, floors: Mapping[str, RowFloor]) -> bool:
    """Matches whose page the generic template checks in full and the
    archetype's template only in part:
    - a trainer whose battle sits in an arm (Mawuli's "Wanna fight? -> Yes",
      map068/ev014): generic answers the menu per arm and checks the battle
      there, while `trainer_beats` reads intro and identity off the page;
    - a randomized flavour NPC (the TV, map048/ev011): generic checks the
      roll's write, the arm it picked (ruling 19's random arms) and the
      lines around it in one talk, while `flavour_npc_beat` checks only
      "one of the lines"."""
    if match.archetype == "trainer":
        return not _battle_on_page(match, floors)
    return match.archetype == "flavour_npc" and match.params.get("variant") == "randomized"


def _match_for(beat: PlannedBeat, matches: Sequence[ArchetypeMatch]) -> ArchetypeMatch:
    """The archetype match an archetype beat was planned from: same
    archetype, and every role row claimed by the beat. By event alone is
    not enough -- a page-level archetype can match two pages of one event."""
    event_id = parse_row_id(beat.rows[0]).event_id
    found = [m for m in matches
             if m.archetype == beat.template and set(m.roles) <= set(beat.rows)]
    if len(found) != 1:
        raise ValueError(
            f"beat {beat.name!r}: expected one {beat.template} match on "
            f"map {beat.map_id} event {event_id}, found {len(found)}")
    return found[0]


def _merge_kwargs(beat: PlannedBeat, extra: Mapping[str, object], *, drop: tuple[str, ...] = ()
                  ) -> PlannedBeat:
    """`beat` with `extra` merged into its kwargs. A key present on both
    sides is a stage disagreement, so it raises rather than letting one
    side silently win (§4.5)."""
    base = {k: v for k, v in beat.kwargs if k not in drop}
    clash = sorted(set(base) & set(extra))
    if clash:
        raise ValueError(f"beat {beat.name!r}: kwargs {clash} set by two stages")
    return dataclasses.replace(beat, kwargs=make_kwargs(**base, **extra))


ARRIVAL_TRIGGERS = frozenset({"autorun", "parallel"})


def _arrival_cells(world: WorldGraph, graphs: Mapping[int, MapGraph], map_id: int,
                   chain_maps: frozenset[int], entry: tuple[int, tuple[int, int]] | None,
                   ) -> tuple[tuple[int, int], ...]:
    """Where a player can arrive on `map_id` in this chapter's ROM: the
    walkable landing cells of warps into it from the chain's maps, plus the
    route entry when it is on this map. Sorted."""
    landed: set[tuple[int, int]] = set()
    if entry is not None and entry[0] == map_id:
        landed.add(entry[1])
    for e in world.edges_to(map_id):
        if e.src_map not in chain_maps or e.dst_cell is None:
            continue
        facing = next((w.dest_facing for w in graphs[e.src_map].warp_exits.get(e.src_cell, ())
                       if w.event_id == e.event_id), 0)
        try:
            # A door-tile arrival steps off in the arrival facing.
            landed.add(landing_cell(graphs[map_id], e.dst_cell, facing=facing))
        except RoutePlanningError:
            continue
    return tuple(sorted(c for c in landed if graphs[map_id].is_walkable(c)))


def _cell_fn(warp_rows: frozenset[str], graphs: Mapping[int, MapGraph],
             arrivals: Callable[[int], tuple[tuple[int, int], ...]],
             nudge_rows: frozenset[str] = frozenset(),
             obstacle_rows: frozenset[str] = frozenset()):  # noqa: ANN202
    """`cell_for_row`, except:

    - a warp beat's row, an obstacle beat's row, or any row whose routing
      cell is a solid tile, gets its walkable sides as approach candidates
      (`cell_for_row` puts the player ON a warp, which offers the solver
      nothing to pick; Task 5's `warp_candidates`). An obstacle is pressed
      into, never stood on: a Strength boulder's tile is walkable terrain
      under the boulder object, so without this the reach pass floods to
      the boulder's own occupied tile and drops the row as unreachable;
    - an autorun/parallel page is located at an ARRIVAL into its map. It
      fires when the map loads, not where its event stands (often an NPC or
      a wall), so any arrival cell is where it is observed; the solver
      picks one. An arrival nudge is the exception: `cell_for_row` already
      gives its exact landing cell (its source warp's), so it keeps that."""
    def cell_fn(row: ManifestRow) -> RowCell:
        # Before `cell_for_row`, which has no cell rule for `parallel`.
        if (row.kind == "page" and row.trigger in ARRIVAL_TRIGGERS
                and row.row_id not in nudge_rows):
            landing = arrivals(row.map_id)
            if not landing:
                raise ValueError(f"{row.row_id}: {row.trigger} page, but no arrival into "
                                 f"map {row.map_id} in this chapter's ROM")
            x, y = landing[0]
            return RowCell(
                row_id=row.row_id, map_constant=_map_constant_for(row.map_id), x=x, y=y,
                resolver=f"arrival into map {row.map_id} ({row.trigger} page)",
                approach_candidates=tuple(
                    ApproachCandidate(x=ax, y=ay, side=f"arrive@({ax},{ay})",
                                      resolver=f"arrival into map {row.map_id} at ({ax},{ay})")
                    for ax, ay in landing))
        cell = cell_for_row(row)
        # Already an adjacent cell with its event's sides (an action-button
        # warp): re-siding around it would name sides of the approach cell,
        # not of the event, and the runtime resolves them against the event.
        if cell.approach_candidates:
            return cell
        # A routing cell on a SOLID tile (an event on a building's exit
        # mat) can't be stood on; like a warp, it's used from its sides.
        solid = not graphs[row.map_id].is_walkable((cell.x, cell.y))
        if row.row_id not in warp_rows and row.row_id not in obstacle_rows and not solid:
            return cell
        return dataclasses.replace(
            cell, approach_candidates=warp_candidates((cell.x, cell.y), graphs[row.map_id]))
    return cell_fn


def _seam_fn(graphs: Mapping[int, MapGraph]):  # noqa: ANN202
    def seam_fn(row: ManifestRow) -> tuple[SeamCrossing, ...]:
        return seam_crossings(row, from_graph=graphs[row.map_id],
                              to_graph=graphs[connection_for(row).to_map])
    return seam_fn


def _picks_with_fallback(records: Sequence[BeatLocationRecord], picks: Mapping[str, str]
                         ) -> dict[str, str]:
    """The solver's picks, plus the only candidate of every group that had
    exactly one. The solver records `chosen_approach` only when it had a
    choice, so a one-candidate group comes back pick-less even though its
    side is fully decided."""
    out = dict(picks)
    for record in records:
        if record.beat_id not in out and len(record.approach_candidates) == 1:
            out[record.beat_id] = record.approach_candidates[0].side
    return out


def _apply_route_kwargs(beat: PlannedBeat, *, boundary: bool = False,
                        nudge_group: bool = False) -> PlannedBeat:
    """Turn the `approach_prefer` pick `order_beats` stamped on a beat into
    that template's route kwargs (for a warp: press direction and round
    trip, or for a `boundary` warp the stop-on-the-edge form). A warp
    without a pick raises: it would reach the emitter with no direction,
    which `warp_beat` can't walk."""
    side = dict(beat.kwargs).get("approach_prefer")
    if nudge_group and side is not None:
        # A nudge's place is its exact landing cell; neither it nor its arms
        # take a side (a solid door tile under it can still give the solver
        # candidates, and the pick lands on the whole group).
        return dataclasses.replace(beat, kwargs=make_kwargs(
            **{k: v for k, v in beat.kwargs if k != "approach_prefer"}))
    if side is None:
        if beat.template == "warp":
            raise ValueError(
                f"warp beat {beat.name!r} has no approach side: the solver made no "
                f"pick and its group has more than one candidate")
        return beat
    return _merge_kwargs(beat, dict(route_kwargs(beat.template, side, boundary=boundary)),
                         drop=("approach_prefer",))


def _chain_maps(binding: ChapterBinding, chapter_id: str) -> frozenset[int]:
    """Every map of `chapter_id` and its predecessors: what its ROM stages."""
    return frozenset(m for c in _chain_to(binding, chapter_id) for m in binding.chapter(c).maps)


def _predecessor_end(predecessor: str) -> tuple[int, tuple[int, int]]:
    """Where the predecessor's walk leaves the player: its own last beat's
    last declared location (A5: "the chapter start is the previous
    chapter's end"). Read from its registered module, which C9 makes the
    generated one."""
    chapter = load_chapter(predecessor)
    own = [b for b in chapter.beats if ":" not in b.name and b.locations]
    if not own:
        raise ValueError(f"{predecessor}: no own beat declares a location to start from")
    loc = own[-1].locations[-1]
    return map_uranium_id(loc.map_constant), (loc.x, loc.y)


_PRESS_INTO = (((0, 1), "UP"), ((0, -1), "DOWN"), ((-1, 0), "RIGHT"), ((1, 0), "LEFT"))
"""(offset of the approach cell from the warp tile, the press onto it):
standing south of it you press UP, and so on. N/S/W/E-side order."""


_STEP_TRIGGERS = frozenset({1, 2})
"""RMXP page triggers a player fires by walking into the event: player touch,
event touch. Action (0) needs A; autorun (3) and parallel (4) need no step."""


def _stepped_transfers(maps: frozenset[int], build_dir: Path) -> frozenset[tuple[int, int]]:
    """(map id, event id) of every event with a Transfer Player on a page
    that stepping into the event fires. A transit hop crosses by holding a
    direction into the tile, so only these are hops; a transfer on an action
    or autorun page is a scripted scene (Map049's Letter: switch-gated, A to
    read, then a cutscene move to 2F), which the world graph records as a
    warp edge all the same (`traversal.warps` keeps every literal 201)."""
    out: set[tuple[int, int]] = set()
    for map_id in sorted(maps):
        for event in load_map_json(map_id, build_dir / "maps").get("events", []):
            if event and any(
                    page.get("trigger") in _STEP_TRIGGERS
                    and any(c.get("code") == 201 for c in page.get("list", []))
                    for page in event.get("pages", [])):
                out.add((map_id, event["id"]))
    return frozenset(out)


def _gated_doors(maps: frozenset[int], build_dir: Path) -> frozenset[tuple[int, int]]:
    """(map id, event id) of every GATED door among `maps`: an event whose
    player-touch pages don't all transfer (`metadata_wiring.classify_event`'s
    own "object", not "warp", outcome -- a live non-transfer touch page plus
    a conditioned transfer page, its own docstring's canonical example is
    Map049 EV002, the starting house's exit). Reused rather than re-derived
    (CLAUDE.md §4.3): that function already carries the S1 keep-list rule and
    the exact reasoning for why a gate must not collapse into an
    unconditional warp. `slice_ids=maps` -- an out-of-slice transfer here
    would be a chapter-boundary warp, not a gate, and `classify_event`
    already returns "skip" for those rather than "object"."""
    from rpg2gba.tileset_converter.metadata_wiring import classify_event

    out: set[tuple[int, int]] = set()
    for map_id in sorted(maps):
        for event in load_map_json(map_id, build_dir / "maps").get("events", []):
            if not event:
                continue
            kind, _ = classify_event(event, maps)
            if kind == "object" and _event_transfers_present(event):
                out.add((map_id, event["id"]))
    return frozenset(out)


def _event_transfers_present(event: dict) -> bool:
    """Does any page of `event` carry a code-201 Transfer Player? Cheap
    local re-check (`metadata_wiring._event_transfers` is private) so
    `_gated_doors` only flags "object" events that are actually doors, not
    every non-warp event on the map."""
    return any(cmd.get("code") == 201 for page in event.get("pages", []) or []
               for cmd in page.get("list", []) or [])


def _warp_presses(beats: Sequence[PlannedBeat]) -> dict[tuple[int, int], str]:
    """(map id, event id) -> the direction each warp beat presses into its
    warp (the side the route solver picked)."""
    out: dict[tuple[int, int], str] = {}
    for b in beats:
        if b.template != "warp":
            continue
        kwargs = dict(b.kwargs)
        out[(b.map_id, int(kwargs["event_id"]))] = str(kwargs["direction"])
    return out


def _route_between(world: WorldGraph, maps: frozenset[int],
                   reach: frozenset[tuple[int, tuple[int, int]]],
                   graphs: Mapping[int, MapGraph], *,
                   stepped_transfers: frozenset[tuple[int, int]] | None = None,
                   warp_presses: Mapping[tuple[int, int], str] | None = None):  # noqa: ANN202
    """`continuity.RouteBetween` over this chapter's maps: the fewest warp
    hops from map `a` to map `b`, each crossed from a reachable walkable side
    of its warp tile. Deterministic: edges are tried in sorted order.

    `stepped_transfers` (see `_stepped_transfers`) limits `warp` edges to the
    events a step fires; None keeps every edge (synthetic test worlds).
    `warp_presses` ((map id, event id) -> press) is the side each warp beat
    crosses from; a hop over one of those uses it. Otherwise the first
    reachable side in `_PRESS_INTO` order -- `reach` floods through warp
    tiles, so that side can be one the live walker can only reach by
    stepping on the warp (2026-09-27: Map048's stairs, north side (3,2))."""
    def lands_reachably(e) -> bool:  # noqa: ANN001
        """The arrival's LANDING is reachable (a door arrival's destination
        cell is the solid door tile; the player stands one step off it)."""
        facing = next((w.dest_facing for w in graphs[e.src_map].warp_exits.get(e.src_cell, ())
                       if w.event_id == e.event_id), 0)
        try:
            return (e.dst_map, landing_cell(graphs[e.dst_map], e.dst_cell, facing=facing)) in reach
        except RoutePlanningError:
            return False

    edges = sorted(
        (e for m in sorted(maps) for e in world.edges_from(m)
         if e.kind in ("warp", "seam_warp") and e.dst_map in maps
         and e.src_cell is not None and e.dst_cell is not None
         and (e.kind != "warp" or stepped_transfers is None
              or (e.src_map, e.event_id) in stepped_transfers)
         and lands_reachably(e)),
        key=lambda e: (e.src_map, e.dst_map, e.src_cell, e.dst_cell))

    def hop_for(edge) -> tuple[str, int, int, str, str] | None:  # noqa: ANN001
        x, y = edge.src_cell
        press = (warp_presses or {}).get((edge.src_map, edge.event_id))
        if press is not None:
            # The warp's own beat already crosses it from the side the route
            # solver picked (its pathing keeps off warp tiles; `reach` does
            # not): cross it the same way.
            dx, dy = next(d for d, p in _PRESS_INTO if p == press)
            return (_map_constant_for(edge.src_map), x + dx, y + dy, press,
                    _map_constant_for(edge.dst_map))
        for (dx, dy), press in _PRESS_INTO:
            if (edge.src_map, (x + dx, y + dy)) in reach:
                return (_map_constant_for(edge.src_map), x + dx, y + dy, press,
                        _map_constant_for(edge.dst_map))
        return None

    usable = [(e, h) for e in edges if (h := hop_for(e)) is not None]

    @functools.cache
    def route(a: int, b: int) -> "tuple[continuity.RouteStep, ...]":
        # The 4th element of each step is the hop's door event id (the
        # source map's warp event), which `continuity.thread_maps`' gated-
        # door guard needs -- `Hop` itself (`generic.transit_beat`'s own
        # shape) carries no event id, so it rides alongside instead.
        prev: dict[int, tuple[int, tuple]] = {a: (a, ())}
        frontier = [a]
        while frontier and b not in prev:
            nxt: list[int] = []
            for m in frontier:
                for e, h in usable:
                    if e.src_map == m and e.dst_map not in prev:
                        prev[e.dst_map] = (m, (e.src_map, e.dst_map, h, e.event_id))
                        nxt.append(e.dst_map)
            frontier = nxt
        if b not in prev or a == b:
            raise ValueError(f"no warp route from map {a} to map {b} over {sorted(maps)}")
        path = []
        node = b
        while node != a:
            node, step = prev[node]
            path.append(step)
        return tuple(reversed(path))

    return route


class _NoOccupancy:
    def blocked_cells(self) -> frozenset[tuple[int, int]]:
        return frozenset()


class _ChainOccupancy:
    """NPC walls on the chain's own maps only. A successor searched for a
    `later` owner may not be emitted yet (CH06's map 040), so it has no
    overlay; the search only names an owner and plans no walk there, so it
    floods that map's geometry alone."""

    def __init__(self, occupancy: Mapping, chain_maps: frozenset[int]) -> None:
        self._occupancy = occupancy
        self._chain_maps = chain_maps

    def __getitem__(self, map_id: int):  # noqa: ANN204
        return self._occupancy[map_id] if map_id in self._chain_maps else _NoOccupancy()


def _staged(chapter_id: str, maps: Sequence[int], graphs: Mapping[int, MapGraph],
            build_dir: Path) -> bool:
    """Every map of a successor has decoded data AND a graph this build can
    build. The corpus is converted progressively: past the frontier a map's
    tileset may not be staged (tile ids beyond its passages array), and the
    `later`-owner search stops there rather than guess."""
    for m in maps:
        if not (build_dir / "maps" / f"Map{m:03d}.json").exists():
            logger.info("later-owner search stops at %s: map %03d is not decoded", chapter_id, m)
            return False
        try:
            graphs[m]
        except KeyError as exc:
            logger.info("later-owner search stops at %s: map %03d has no graph (%s)",
                        chapter_id, m, exc)
            return False
    return True


def _split_unreachable(
    records: Sequence[BeatLocationRecord], entry: tuple[int, tuple[int, int]],
    graphs: Mapping[int, MapGraph], world: WorldGraph, chain_maps: frozenset[int],
    binding: ChapterBinding, chapter_id: str, occupancy: Mapping, build_dir: Path,
) -> tuple[list[BeatLocationRecord], dict[str, str | None]]:
    """(records the player can reach, {unreachable row: later owner}).

    Row by row: a group spanning several cells (an obstacle group's rocks, an
    exit strip, a staircase) keeps the rows the player can reach and is
    re-pointed at one of them when its routing row is the unreachable one; a
    group with no reachable row leaves the plan. The owner is the first
    successor chapter whose maps, added to this chain, make the row
    reachable. A successor is searched when every map of it is staged in
    `build_dir`, with or without a committed manifest (CH04's north seam onto
    map 040 belongs to CH06, which has none yet), so None means "no staged
    chapter opens it". The search stops once every row has an owner."""
    def row_sites(cell: RowCell) -> list[tuple[int, tuple[int, int]]]:
        m = map_uranium_id(cell.map_constant)
        return [(m, (c.x, c.y)) for c in cell.approach_candidates] or [(m, (cell.x, cell.y))]

    reach = reachable_sites(entry, graphs, world, chain_maps, occupancy)
    kept: list[BeatLocationRecord] = []
    dropped: dict[str, list[tuple[int, tuple[int, int]]]] = {}
    for record in records:
        ok = [c for c in record.candidates if any(s in reach for s in row_sites(c))]
        ok_rows = {c.row_id for c in ok}
        for c in record.candidates:
            if c.row_id not in ok_rows:
                dropped[c.row_id] = row_sites(c)
        # A row with no cell of its own (it rides on another row's cell)
        # follows its group's routing point.
        routing_ok = any(s in reach for s in (
            [(map_uranium_id(record.map_constant), (a.x, a.y)) for a in record.approach_candidates]
            or [(map_uranium_id(record.map_constant), (record.x, record.y))]))
        if not ok and not routing_ok:
            for row in record.rows:
                dropped.setdefault(row, [])
            logger.info("%s: %s is unreachable from the entry over this chapter's maps",
                        chapter_id, record.beat_id)
            continue
        rows = tuple(r for r in record.rows if r not in dropped)
        if routing_ok or not ok:
            kept.append(dataclasses.replace(record, rows=rows, candidates=tuple(ok)))
            continue
        first = ok[0]
        kept.append(dataclasses.replace(
            record, rows=rows, candidates=tuple(ok), map_constant=first.map_constant,
            x=first.x, y=first.y, resolver=first.resolver,
            approach_candidates=first.approach_candidates))
        logger.info("%s: %s re-pointed at reachable row %s", chapter_id, record.beat_id,
                    first.row_id)

    later: dict[str, str | None] = {row: None for row in dropped}
    wider = chain_maps
    nxt = binding.successor(chapter_id) if dropped else None
    while nxt is not None and any(owner is None for owner in later.values()) and _staged(
            nxt.id, nxt.maps, graphs, build_dir):
        wider = wider | frozenset(nxt.maps)
        reach = reachable_sites(entry, graphs, world, wider, _ChainOccupancy(occupancy, chain_maps))
        for row, sites in dropped.items():
            if later[row] is None and any(s in reach for s in sites):
                later[row] = nxt.id
        nxt = binding.successor(nxt.id)
    return kept, later


def _warp_dest(beat: PlannedBeat, floors: Mapping[str, RowFloor]) -> int:
    dests = {a.param("map_id") for r in beat.rows for a in floors[r].assertions
             if a.kind == "warp"}
    if len(dests) != 1:
        raise ValueError(f"warp beat {beat.name!r}: {len(dests)} destinations {sorted(dests)}")
    return dests.pop()


def _group_boundary_exits(beats: Sequence[PlannedBeat], floors: Mapping[str, RowFloor],
                          chain_maps: frozenset[int]) -> tuple[PlannedBeat, ...]:
    """One group per chapter EXIT, not per warp tile. A wide exit is a
    contiguous strip of warp tiles on one map bound for the same map
    (CH01's Moki -> Route 1: events 23, 36, 37 at (8,43..45); CH02's Route 1
    -> Kevlar: events 45 and 46). As separate groups the solver sees several
    terminal candidates and refuses. A strip is grouped under the name of
    its first beat in plan order."""
    from rpg2gba.playtest.cells import event_cell

    tiles: dict[str, tuple[int, int, int, int]] = {}      # beat -> (map, dest, x, y)
    for b in beats:
        if b.template == "warp" and is_boundary_warp(b, floors, chain_maps):
            x, y = event_cell(_map_constant_for(b.map_id), parse_row_id(b.rows[0]).event_id)
            tiles[b.name] = (b.map_id, _warp_dest(b, floors), x, y)
    group_of: dict[str, str] = {}
    for b in beats:                       # plan order: the first tile names the strip
        if b.name not in tiles or b.name in group_of:
            continue
        group_of[b.name] = b.group
        stack = [b.name]
        while stack:
            m, d, x, y = tiles[stack.pop()]
            for other, (om, od, ox, oy) in tiles.items():
                if other not in group_of and (om, od) == (m, d) and abs(ox - x) + abs(oy - y) == 1:
                    group_of[other] = b.group
                    stack.append(other)
    return tuple(dataclasses.replace(b, group=group_of[b.name]) if b.name in group_of else b
                 for b in beats)


def _never_fires_elsewhere(
    planned: Sequence[PlannedBeat], dead_groups: Mapping[str, str],
) -> tuple[Elsewhere, ...]:
    """Every row of a dead arrival-nudge group (C9 ruling 3): `dead_groups`
    maps a group id to the `NoArrivalError` proof text, and every row of
    every beat in that group becomes a `never_fires` elsewhere entry
    carrying that proof as `detail`."""
    return tuple(
        Elsewhere(row_id, "never_fires", detail=dead_groups[b.group])
        for b in planned if b.group in dead_groups for row_id in b.rows)


def _page_candidate(verdicts: Mapping[str, RowVerdict], end_state, states: Mapping[str, RowState]
                    ) -> Callable[[str], bool]:
    """Can this page be the live page at all, within the chapter? A page the
    story model calls live or undetermined can; one it rules out
    (`unreachable`, `later`) can't; a `refused` page (its BODY isn't modelled,
    its condition is) can when every test of its condition is possible in the
    chapter's saturated end state. A page with no verdict can."""
    ends = dict(end_state)

    def possible_at_end(test) -> bool:  # noqa: ANN001
        values = ends.get(_state_key_repr(test.key))
        if values is None:
            values = tuple(_default_value(test.key))
        return "TOP" in values or any(_cmp(test.op, v, test.value) for v in values)

    def candidate(rid: str) -> bool:
        verdict = verdicts.get(rid)
        if verdict is None or verdict.status in ("live", "undetermined"):
            return True
        if verdict.status == "refused":
            return all(possible_at_end(t) for t in states[rid].page_tests)
        return False
    return candidate


def _map_facts_factory(
    *, row_states, page_for, event_cell, build_dir: Path, graphs: Mapping[int, MapGraph],
    world: WorldGraph, chain_maps: frozenset[int], entry: tuple[int, tuple[int, int]], occupancy,
    verdicts: Mapping[str, RowVerdict], end_state,
) -> Callable[[int], MapFacts]:
    """map id -> the `MapFacts` the walk provers read (cached)."""
    facts_cache: dict[int, MapFacts] = {}
    constants = build_dir / "porymap" / "map_constants.json"

    def facts_for(map_id: int) -> MapFacts:
        if map_id not in facts_cache:
            entry_ = _load_map_constants_entry(map_id, constants)
            emitted = _load_emitted_map(map_id, entry_["dir_name"], DEFAULT_ENGINE_MAPS_DIR)
            facts_cache[map_id] = MapFacts(
                map_id=map_id,
                coord_cells=coord_cells_by_event(map_id, emitted.get("coord_events", [])),
                states=row_states(map_id), page_for=page_for, event_cell=event_cell,
                graph=graphs[map_id], blocked=occupancy[map_id].blocked_cells(),
                arrivals=_arrival_cells(world, graphs, map_id, chain_maps, entry),
                candidate=_page_candidate(verdicts, end_state, row_states(map_id)))
        return facts_cache[map_id]
    return facts_for


def _touch_never_fires(
    beats: Sequence[PlannedBeat], *, row_states, facts_for: Callable[[int], MapFacts],
) -> tuple[tuple[PlannedBeat, ...], tuple[Elsewhere, ...]]:
    """Second source of `never_fires` (2026-09-28 ruling, `beat_gen/never_fires.py`):
    a walked touch page whose coord-trigger cells the walk can't step on
    while it is live -- guard rows that push the player off, and the cell an
    arrival scene leaves them on. The page's rows leave the beats and become
    `never_fires` elsewhere entries carrying the proof."""
    proofs: dict[str, str] = {}
    for b in beats:
        for rid in b.rows:
            page = parse_row_id(rid).owning_page_row_id or rid
            if page in proofs or parse_row_id(page).kind != "page":
                continue
            states = row_states(parse_row_id(page).map_id)
            if page not in states or states[page].trigger not in TOUCH_TRIGGERS:
                continue
            proof = never_fires_proof(page, facts_for(parse_row_id(page).map_id))
            if proof is not None:
                proofs[page] = proof
                logger.info("never_fires: %s", proof)
    if not proofs:
        return tuple(beats), ()
    kept: list[PlannedBeat] = []
    elsewhere: list[Elsewhere] = []
    for b in beats:
        rows = tuple(r for r in b.rows if (parse_row_id(r).owning_page_row_id or r) not in proofs)
        elsewhere.extend(
            Elsewhere(r, "never_fires",
                      detail=proofs[parse_row_id(r).owning_page_row_id or r])
            for r in b.rows if r not in rows)
        if rows == b.rows:
            kept.append(b)
        elif rows:
            kept.append(dataclasses.replace(b, rows=rows))
    return tuple(kept), tuple(elsewhere)


def _row_states_for(build_dir: Path, resolved: Mapping[str, RowState] | None = None):  # noqa: ANN202
    """map_id -> that map's extracted story row states (cached), with any
    computed row the story model resolved (`resolved`) in place of its
    extraction-time placeholder."""
    common_events = json.loads((build_dir / "common_events.json").read_text(encoding="utf-8"))
    ref_dir = Path(__file__).resolve().parents[3] / "reference"
    switch_labels, _ = load_label_tables(
        ref_dir / "uranium_switches.json", ref_dir / "uranium_variables.json")
    overlay = dict(resolved or {})

    @functools.cache
    def states(map_id: int):  # noqa: ANN202
        out = extract_map(map_id, load_map_json(map_id, build_dir / "maps"),
                          common_events=common_events, switch_labels=switch_labels)
        return {rid: overlay.get(rid, rs) for rid, rs in out.items()}
    return states


def _event_cell(build_dir: Path):  # noqa: ANN202
    """page row id -> its event's (x, y) on the map."""
    @functools.cache
    def cells(map_id: int) -> dict[int, tuple[int, int]]:
        data = load_map_json(map_id, build_dir / "maps")
        return {e["id"]: (e["x"], e["y"]) for e in data.get("events", []) or []}

    def cell(page_row_id: str) -> tuple[int, int] | None:
        parsed = parse_row_id(page_row_id)
        return cells(parsed.map_id).get(parsed.event_id)
    return cell


def _moved_by(build_dir: Path):  # noqa: ANN202
    """(map id, event id) -> the rows whose scripts move that event."""
    @functools.cache
    def moved(map_id: int) -> dict[int, tuple[str, ...]]:
        data = load_map_json(map_id, build_dir / "maps")
        return scene_moved_events(map_id, data.get("events", []) or [])

    def moved_by(map_id: int, event_id: int) -> tuple[str, ...]:
        return moved(map_id).get(event_id, ())
    return moved_by


class _ViewerLocator:
    """`review.Locator` over the build: map names as the map viewer shows
    them (`map_infos.json` + `map_name_overrides.json`, §4.3) and each row's
    event tile from the map JSON."""

    def __init__(self, build_dir: Path) -> None:
        infos = build_dir / "map_infos.json"
        self._names = load_display_names(infos, MAP_NAME_OVERRIDES) if infos.exists() else {}
        self._event_cell = _event_cell(build_dir)

    def map_name(self, map_id: int) -> str:
        return self._names.get(map_id, "")

    def row(self, row_id: str) -> RowLocation:
        parsed = parse_row_id(row_id)
        name = self.map_name(parsed.map_id)
        if parsed.kind in ("page", "branch"):
            return RowLocation(parsed.map_id, name, self._event_cell(row_id))
        if parsed.kind == "terrain":
            return RowLocation(parsed.map_id, name, (parsed.x, parsed.y))
        return RowLocation(parsed.map_id, name,
                           note=f"{parsed.direction} edge -> Map{parsed.other_map_id:03d}")


def _firing_for(records: Sequence[BeatLocationRecord], nudge_groups: Collection[str],
                event_cell):  # noqa: ANN001, ANN202
    """(beat, page row id) -> the `Firing` the walk makes: the player's cell
    (a nudge's landing; the picked arrival or approach side's cell; the only
    candidate), the event's cell, and the beat's choice answers."""
    by_group = {r.beat_id: r for r in records}

    def firing(beat: PlannedBeat, page_row_id: str) -> Firing:
        rec = by_group.get(beat.group)
        kwargs = dict(beat.kwargs)
        side = kwargs.get("approach_prefer")
        cell: tuple[int, int] | None = None
        if rec is not None and beat.group in nudge_groups:
            cell = (rec.x, rec.y)
        elif isinstance(side, str) and side.startswith("arrive@("):
            x, y = side[len("arrive@("):-1].split(",")
            cell = (int(x), int(y))
        elif rec is not None:
            sides = [c for c in rec.approach_candidates if side is None or c.side == side]
            if len(sides) == 1:
                cell = (sides[0].x, sides[0].y)
        return Firing(cell=cell, event_cell=event_cell(page_row_id),
                      choice_answers=dict(kwargs.get("choice_answers", ())))
    return firing


def _unwalked_taint(beats: Sequence[PlannedBeat], verdicts: Sequence[RowVerdict],
                    row_states) -> list[Taint]:  # noqa: ANN001
    """Every write of a live row whose page the walk never fires -- or fires
    but which keeps running (a parallel page) -- as `state_arms` taint."""
    fired = {p for b in beats if b.template in FIRING_TEMPLATES for p in fired_pages(b)}
    out: list[Taint] = []
    for v in verdicts:
        if v.status != "live":
            continue
        page = parse_row_id(v.row_id).owning_page_row_id or v.row_id
        states = row_states(parse_row_id(v.row_id).map_id)
        rs = states.get(v.row_id)
        if rs is None or (page in fired and states[page].trigger != "parallel"):
            continue
        out.extend(rs.writes)
        out.extend(rs.havoc_keys)
    return out


def _live_order_dependent(keys: Sequence, elsewhere: Sequence[Elsewhere]) -> tuple:
    """`story.order_dependent` without the writers the liveness check demoted
    (`state_arms`, they never run on the route); a key left with fewer than
    two writers no longer depends on the order."""
    gone = {e.row_id for e in elsewhere if e.status == "never_fires"}
    out = []
    for k in keys:
        writers = tuple(w for w in k.writers if w not in gone)
        if len(writers) >= 2:
            out.append(dataclasses.replace(k, writers=writers))
    return tuple(out)


def _page_for(build_dir: Path):  # noqa: ANN202
    """page row id -> that page's raw RMXP dict."""
    def page(page_row_id: str) -> dict:
        parsed = parse_row_id(page_row_id)
        data = load_map_json(parsed.map_id, build_dir / "maps")
        event = next(e for e in data["events"] if e["id"] == parsed.event_id)
        return event["pages"][parsed.page_idx]
    return page


def _empty_events(rows: Sequence[ManifestRow], build_dir: Path) -> set[tuple[int, int]]:
    """`select.empty_events` over every map `rows` touch."""
    out: set[tuple[int, int]] = set()
    for map_id in sorted({r.map_id for r in rows if r.map_id is not None}):
        out |= empty_events(map_id, load_map_json(map_id, build_dir / "maps"))
    return out


def build_plan(chapter_id: str, *, build_dir: Path = BUILD_DIR,
               out_dir: Path = DEFAULT_OUT_DIR,
               module_dir: Path = DEFAULT_MODULE_DIR) -> ChapterPlan:
    """Run stages 1-4 for one chapter and return the fully decided plan.
    `module_dir` is where the predecessors' generated modules are read from
    (their routes decide their order-dependent writes, `beat_gen/seed.py`)."""
    # 1. Load. Each predecessor's end state is seeded from its own solved
    #    route (C6 seed recompute).
    binding = load_binding(DEFAULT_CHAPTERS_PATH)
    predecessor = binding.chapter(chapter_id).predecessor
    successor = binding.successor(chapter_id)
    rows = load_chapter_rows(chapter_id)
    resolved: dict[str, RowState] = {}
    seeds: dict[str, State] = {}
    stories = build_chapter_stories(_chain_to(binding, chapter_id), build_dir=build_dir,
                                    chapters_path=DEFAULT_CHAPTERS_PATH,
                                    winner_for=route_winner(chapter_id, module_dir),
                                    resolved_out=resolved, seed_out=seeds)
    story = stories[chapter_id]
    verdicts = {v.row_id: v for v in story.rows}
    floors: dict[str, RowFloor] = floor_for_chapter(chapter_id, build_dir=build_dir)
    chain_maps = _chain_maps(binding, chapter_id)

    # 2. Select, hand boundary events to the successor, and claim the
    #    predecessor's crossings into this chapter (§10 R2/R3,
    #    `beat_gen/boundary.py`). Inbound beats search the predecessor's
    #    manifest (`manifest_chapter_id=`).
    stripped = load_map_event_strips(Path(__file__).resolve().parents[3] / "reference")
    empty = _empty_events(rows, build_dir)
    selection = split_outbound(select_rows(rows, verdicts, floors, stripped=stripped,
                                           empty=empty),
                               floors, chain_maps,
                               successor.id if successor is not None else None)
    inbound: tuple[ManifestRow, ...] = ()
    if predecessor is not None:
        pred_rows = load_chapter_rows(predecessor)
        pred_floors = floor_for_chapter(predecessor, build_dir=build_dir)
        inbound = inbound_rows(pred_rows, pred_floors,
                               frozenset(binding.chapter(chapter_id).maps),
                               _chain_maps(binding, predecessor))
        inbound_sel = select_rows(inbound, {v.row_id: v for v in stories[predecessor].rows},
                                  pred_floors, stripped=stripped,
                                  empty=_empty_events(inbound, build_dir))
        selection = Selection(owned=inbound_sel.owned + selection.owned,
                              refusals=inbound_sel.refusals + selection.refusals,
                              elsewhere=inbound_sel.elsewhere + selection.elsewhere)
        floors.update({r.row_id: pred_floors[r.row_id] for r in inbound})
    all_rows = tuple(inbound) + tuple(rows)
    rows_by_id = {r.row_id: r for r in all_rows}
    # White-out fork rows have no tile; `whiteout.place_whiteout_beats`
    # places them after ordering (rulings 15-16).
    fork_owned = {rid for f in story.forks if f.transition == "whiteout"
                  for rid in f.owned_row_ids}
    # Ruling 19: exclusive arms the walk doesn't take leave the plan.
    all_verdicts = {v.row_id: v for s in stories.values() for v in s.rows}
    selection = blocked_arms(selection, all_verdicts, fork_owned)
    # An archetype template reads its whole page -- arms included -- so a
    # match whose page has a refused arm can't register as that archetype
    # (CH01's map065/ev001: a #109 text gap on one arm). It falls to the
    # generic template, which reads each row's own floor; the arm stays a
    # named refusal.
    refused_ids = {r.row_id for r in selection.refusals}
    matches = tuple(
        m for m in classify_manifest(inbound) + classify_manifest(rows)
        if not any(rid.startswith(f"{page}/") for page in m.roles for rid in refused_ids)
        and not _generic_reads_it_better(m, floors))
    fork_rows = tuple(r.row_id for r in selection.owned if r.row_id in fork_owned)
    beats = plan_beats(tuple(r for r in selection.owned if r.row_id not in fork_owned),
                       matches, floors)
    inbound_ids = frozenset(r.row_id for r in inbound)
    beats = tuple(
        _merge_kwargs(b, {"manifest_chapter_id": predecessor})
        if inbound_ids and set(b.rows) <= inbound_ids else b
        for b in beats)
    # Ruling 19: one beat per choice arm, then RNG-selected arms are claimed
    # but checked on whichever fired.
    row_states = _row_states_for(build_dir, resolved)
    arms_by_page: dict[str, list[str]] = {}
    for r in all_rows:
        owner = parse_row_id(r.row_id).owning_page_row_id
        if owner is not None and r.branch is not None:
            arms_by_page.setdefault(owner, []).append(r.row_id)
    beats, choice_elsewhere = split_choice_arms(
        beats,
        branch_of=lambda rid: rows_by_id[rid].branch if rid in rows_by_id else None,
        parent_of=lambda rid: row_states(parse_row_id(rid).map_id)[rid].parent_row_id,
        killed_by=lambda page: (all_verdicts[page].killed_by if page in all_verdicts else ()),
        choice_openers=lambda rid: [a.list_index for a in floors[rid].assertions
                                    if a.kind == "choice"],
        round_trip=lambda page, loser, walked, claimed: find_round_trip(
            page, loser, walked, seed=seeds[chapter_id], row_states=row_states,
            page_for=_page_for(build_dir), branch_of=lambda rid: rows_by_id[rid].branch,
            arms_of=lambda pg: arms_by_page.get(pg, ()), claimed=claimed,
            event_cell=_event_cell(build_dir)),
    )
    beats = annotate_random_arms(beats, row_states, _page_for(build_dir))

    # 3. Adapt, source half. An arrival nudge nothing lands on never fires
    #    (C9 ruling 3): its whole group (the nudge and its arms) is dropped
    #    from beats and its rows become `never_fires` elsewhere entries, not
    #    refusals -- the proof is the `NoArrivalError` message.
    planned = beats
    adapted: list[PlannedBeat] = []
    dead_groups: dict[str, str] = {}
    for b in planned:
        if b.template in ARCHETYPE_TEMPLATES:
            try:
                b = _merge_kwargs(b, dict(archetype_kwargs(
                    b, _match_for(b, matches), floors,
                    map_constant_fn=_map_constant_for, rows=all_rows,
                    moved_by_fn=_moved_by(build_dir))))
            except NoArrivalError as exc:
                dead_groups[b.group] = str(exc)
        elif b.template == "escort":
            b = _merge_kwargs(b, dict(escort_kwargs(b, floors, map_constant_fn=_map_constant_for)))
        adapted.append(b)
    dead_elsewhere = _never_fires_elsewhere(planned, dead_groups)
    beats = tuple(b for b in adapted if b.group not in dead_groups)
    beats = _group_boundary_exits(beats, floors, chain_maps)
    # 3b. A4 (`beat_gen/facing.py`): an arm gated on the player's facing is
    #     its own group, walked from the side that selects it.
    sides_by_row: dict[str, frozenset[str]] = {}
    for map_id, event_ids in sorted(event_ids_by_map(r for b in beats for r in b.rows).items()):
        sides_by_row.update(facing_sides(
            map_id, load_map_json(map_id, build_dir / "maps"), event_ids))
    beats, facing_pins = split_facing_arms(beats, sides_by_row)

    # 4. Locate. Graphs are lazy: a seam or a route may touch maps outside
    #    the chapter's own list (`routing.__main__._LazyGraphs`).
    graphs, overlays = _build_graphs_and_overlays(list(binding.chapter(chapter_id).maps),
                                                  build_dir)
    world = _build_world(build_dir)
    entry = _predecessor_end(predecessor) if predecessor is not None else engine_spawn()
    occupancy = _LazyOccupancy(build_dir)
    # 3c. Touch pages the walk can't step on while they are live (guard rows,
    #     arrival displacement): never_fires, not beats.
    facts_for = _map_facts_factory(
        row_states=row_states, page_for=_page_for(build_dir), event_cell=_event_cell(build_dir),
        build_dir=build_dir, graphs=graphs, world=world, chain_maps=chain_maps, entry=entry,
        occupancy=occupancy, verdicts=all_verdicts, end_state=story.end_state)
    beats, touch_elsewhere = _touch_never_fires(beats, row_states=row_states, facts_for=facts_for)
    dead_elsewhere = dead_elsewhere + touch_elsewhere
    warp_rows = frozenset(r for b in beats if b.template == "warp" for r in b.rows)
    records, cell_refusals = locate_beats(
        beats, rows_by_id,
        cell_fn=_cell_fn(warp_rows, graphs,
                         lambda m: _arrival_cells(world, graphs, m, chain_maps, entry),
                         frozenset(r for b in beats if b.template == "arrival_nudge"
                                   for r in b.rows),
                         frozenset(r for b in beats if b.template == "obstacle"
                                   for r in b.rows)),
        seam_fn=_seam_fn(graphs), map_constant_fn=_map_constant_for)
    records, facing_refusals = pin_records(records, facing_pins)
    cell_refusals = [*cell_refusals, *facing_refusals]
    # A refused group has no record, so the solver can't visit it; its
    # beats leave the plan and survive only as refusals in the review doc.
    located = {r.beat_id for r in records}
    beats = tuple(b for b in beats if b.group in located)

    # 4b. Geography (`beat_gen/reach.py`): a group no site of which the
    #     player can reach from the entry over this chapter's maps belongs
    #     to the first successor whose maps open it.
    records, later = _split_unreachable(records, entry, graphs, world, chain_maps,
                                        binding, chapter_id, occupancy, build_dir)
    trimmed: list[PlannedBeat] = []
    for b in beats:
        rows = tuple(r for r in b.rows if r not in later)
        if len(rows) == len(b.rows):
            trimmed.append(b)
        elif rows:
            trimmed.append(dataclasses.replace(b, rows=rows))
    beats = tuple(trimmed)
    selection = Selection(owned=selection.owned, refusals=selection.refusals,
                          elsewhere=selection.elsewhere + tuple(
                              Elsewhere(row_id, "later", owner)
                              for row_id, owner in later.items()))

    # 4c. Guard walls (`beat_gen/guard_reach.py`): approach cells the player
    #     can't reach while a coord guard is live are dropped, or the beat waits
    #     for a claimed row that ends the guard (2026-09-29, the lab's signs).
    group_of_row = {r: b.group for b in beats for r in b.rows}
    guard_cache: dict[int, Sequence] = {}

    def reaches_for(map_id: int):  # noqa: ANN202
        if map_id not in guard_cache:
            guard_cache[map_id] = guard_reaches(
                facts_for(map_id), seed=seeds[chapter_id], default=_default_value)
        return guard_cache[map_id]

    records, guard_waits = apply_guard_reach(
        records, reaches_for=reaches_for, map_of=lambda rec: map_uranium_id(rec.map_constant),
        row_state=lambda rid: row_states(parse_row_id(rid).map_id).get(rid),
        group_of_row=group_of_row)
    for wait in guard_waits:
        logger.info("guard_reach: %s", wait.describe())

    # 5. Solve, with the same argument assembly as `routing plan`. The
    #    route starts where the predecessor leaves the player (A5), not at
    #    this chapter's first record.
    # Only rows the plan still walks: a trainer row that went to `later`
    # (Grott-Hole, map 19) mustn't demand sight tiles on a map not routed.
    walked = {r for b in beats for r in b.rows}
    walked |= {parse_row_id(r).owning_page_row_id for r in walked} - {None}
    walked_pages = {parse_row_id(r).owning_page_row_id for r in walked} - {None}
    _check_trigger_overlay_or_raise(
        [r for r in all_rows
         if r.row_id in walked or parse_row_id(r.row_id).owning_page_row_id in walked_pages],
        chapter_id, overlays)
    candidates = {
        r.beat_id: tuple(RouteCandidate(x=c.x, y=c.y, side=c.side, resolver=c.resolver)
                         for c in r.approach_candidates)
        for r in records if r.approach_candidates
    }
    # Ruling 16: story-state enablers order beats too. Every chain
    # chapter's verdicts, since inbound rows are the predecessor's.
    enabled_by = {v.row_id: v.enabled_by for s in stories.values() for v in s.rows}
    # 2026-09-29 ruling (page liveness): an enabler candidate that can't reach a
    # `>=` threshold drops out (`threshold:` edges), and a page's beat comes
    # before every claimed write that lifts a higher page of its event
    # (`killer:` edges) -- `beat_gen/liveness_edges.py`.
    def state_of(rid: str):  # noqa: ANN202
        if not rid.startswith("map"):    # a common-event row / an engine marker: no map state
            return None
        return row_states(parse_row_id(rid).map_id).get(rid)
    claimed_rows = {r for b in beats for r in b.rows}
    wm = WriteModel(state_of, _page_for(build_dir))
    story_enabled_by, threshold_by = split_threshold_enablers(
        enabled_by, wm=wm, seed=seeds[chapter_id], claimed_rows=claimed_rows)
    killers = killed_before(beats, wm=wm, seed=seeds[chapter_id],
                            claimed_rows=claimed_rows)
    # 2026-09-28 ruling (one-way warps): enter a dead-end interior, do its
    # first-visit beats, leave; an arrival nudge after the warp landing on it.
    warp_beats = [b for b in beats if b.template == "warp"]
    group_map = {b.group: b.map_id for b in reversed(beats)}
    soft = arrival_nudge_edges(
        nudge_groups={b.group: (b.map_id, map_uranium_id(dict(b.kwargs)["from_map_constant"]))
                      for b in beats if b.template == "arrival_nudge"},
        warp_groups={b.group: (b.map_id, _warp_dest(b, floors)) for b in warp_beats})
    regions = dict(
        chapter_maps=frozenset(group_map.values()) | {entry[0]}, entry_map=entry[0],
        group_map=group_map,
        group_warps={b.group: ((b.map_id, int(dict(b.kwargs)["event_id"])),)
                     for b in warp_beats})
    gated = _gated_doors(chain_maps, build_dir)
    route = solve_route(
        chapter_from_locations(chapter_id, records), chapter_id,
        manifest_rows=all_rows, graphs=graphs, overlays=overlays,
        world=world, map_ids=_load_map_ids(build_dir),
        occupancy=occupancy, candidates=candidates, entry=entry,
        enabled_by=story_enabled_by, threshold_enabled_by=threshold_by, killed_before=killers,
        guard_enabled_by=guard_enabled_by(guard_waits, {r.beat_id: r.rows[0] for r in records}),
        soft_precedence=lambda accepted, any_of: soft + interior_exit_edges(
            world, **regions, hard_and_story=accepted, any_of=any_of),
        order_violations=region_order_check(world, **regions),
        # 2026-09-30 (operator): a region whose exit is a gated door is held
        # hard, and what its exit waits on outside comes before its entry.
        derived_precedence=lambda accepted, any_of: gated_entry_edges(
            world, **regions, gated_doors=gated, hard_and_story=accepted, any_of=any_of),
        hard_order_violations=gated_region_check(world, **regions, gated_doors=gated),
    )

    # 6. Order, then adapt's route half. A warp whose destination is on no
    #    map of this chapter's chain is a chapter boundary (09_cli.md's
    #    blocker): it stops on the solver's side instead of round-tripping
    #    into a map this chapter's ROM doesn't build.
    group_order, picks = route_order(route.nodes)
    check_guard_order(guard_waits, group_order, group_of_row)
    beats = order_beats(beats, group_order, _picks_with_fallback(records, picks))
    nudge_groups = {b.group for b in beats if b.template == "arrival_nudge"}
    # 6b. Ruling 19 steps 4-5 (`beat_gen/state_arms.py`): with the order and
    #     the cells known, keep only the arms the walk's state and position
    #     select, re-firing a page whose own writes select the rest.
    liveness_problems: list[LivenessProblem] = []
    beats, state_elsewhere = select_state_arms(
        beats, seeds[chapter_id], order_problems=liveness_problems, row_states=row_states, page_for=_page_for(build_dir),
        firing_for=_firing_for(records, nudge_groups, _event_cell(build_dir)),
        taint=_unwalked_taint(beats, story.rows, row_states),
        walkable=lambda rid: rid in floors and not floors[rid].refused,
        choice_openers=lambda rid: [a.list_index for a in floors[rid].assertions
                                    if a.kind == "choice"] if rid in floors else [])
    beats = tuple(
        _apply_route_kwargs(
            b, boundary=b.template == "warp" and is_boundary_warp(b, floors, chain_maps),
            nudge_group=b.group in nudge_groups)
        for b in beats)

    # 7. Map continuity (`beat_gen/continuity.py`): each warp's start and
    #    end side follow from where the player is and where the next beat is.
    beats = thread_maps(
        beats, start_map=route.nodes[0].map_id,
        warp_dest={b.name: _warp_dest(b, floors) for b in beats
                   if b.template in ("warp", "escort")},
        nudge_source={b.name: map_uranium_id(dict(b.kwargs)["from_map_constant"])
                      for b in beats if b.template == "arrival_nudge"},
        route_between=_route_between(
            world, chain_maps, reachable_sites(entry, graphs, world, chain_maps, occupancy),
            graphs, stepped_transfers=_stepped_transfers(chain_maps, build_dir),
            warp_presses=_warp_presses(beats)),
        gated_doors=gated,
    )

    # 8. White-out fork beats ride after their enablers (`beat_gen/whiteout.py`).
    heal_entries = json.loads(
        (build_dir / "heal_locations.json").read_text(encoding="utf-8"))["heal_locations"]
    beats = place_whiteout_beats(beats, fork_rows, enabled_by,
                                 map_constant_for=_map_constant_for, heal_entries=heal_entries)

    # 9. A refused gift arm inside a claimed page still runs its ceremony
    #    (`beat_gen/gift_ceremony.py`).
    beats = annotate_gift_ceremonies(beats, selection.refusals, floors)

    return ChapterPlan(
        chapter_id=chapter_id,
        predecessor=predecessor,
        beats=beats,
        refusals=selection.refusals + tuple(cell_refusals),
        elsewhere=selection.elsewhere + dead_elsewhere + choice_elsewhere + state_elsewhere,
        order_dependent=_live_order_dependent(story.order_dependent, state_elsewhere),
        route=route,
        liveness_problems=tuple(liveness_problems),
    )


def write_outputs(plan: ChapterPlan, out_dir: Path, *, module_dir: Path | None = None,
                  build_dir: Path = BUILD_DIR) -> list[Path]:
    """Write the three artifacts; return their paths in a fixed order
    (module, review, route). Overwrites; must be byte-identical on re-run.

    `module_dir` (default `DEFAULT_MODULE_DIR`, `playtest/chapters_gen/`)
    is where the module (`chNN.py`) lands; `out_dir` still owns the review
    doc and route JSON. Callers that must not write into `src/` (tests)
    pass an explicit `module_dir=`."""
    if plan.route is None:
        raise ValueError(f"{plan.chapter_id}: plan has no solved route to write")
    out_dir.mkdir(parents=True, exist_ok=True)
    module_dir = DEFAULT_MODULE_DIR if module_dir is None else module_dir
    module_dir.mkdir(parents=True, exist_ok=True)
    module_path = module_dir / f"{plan.chapter_id.lower()}.py"
    review_path = out_dir / f"{plan.chapter_id}.review.md"
    route_path = out_dir / f"{plan.chapter_id}.route.json"

    module_path.write_text(emit_module(plan), encoding="utf-8")
    review_path.write_text(
        render_review(plan, floor_lookup=lambda row_id: floor_for_row(row_id, build_dir=build_dir),
                      locate=_ViewerLocator(build_dir)),
        encoding="utf-8")
    write_plan(plan.route, route_path)
    return [module_path, review_path, route_path]


@click.group()
def cli() -> None:
    """The C6 beat generator."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


@cli.command()
@click.option("--chapter", "chapter_id", required=True, help="e.g. CH05")
@click.option("--out-dir", type=click.Path(path_type=Path), default=DEFAULT_OUT_DIR,
              show_default=True)
@click.option("--module-dir", type=click.Path(path_type=Path), default=DEFAULT_MODULE_DIR,
              show_default=True, help="Where the generated chNN.py module is written.")
def generate(chapter_id: str, out_dir: Path, module_dir: Path) -> None:
    """Generate one chapter's module, review doc and route."""
    plan = build_plan(chapter_id, out_dir=out_dir, module_dir=module_dir)
    for path in write_outputs(plan, out_dir, module_dir=module_dir):
        logger.info("wrote %s", path)
    if plan.refusals:
        logger.warning("%s: %d rows refused -- see the review doc",
                       chapter_id, len(plan.refusals))


if __name__ == "__main__":
    cli()
