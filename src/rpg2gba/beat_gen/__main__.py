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
import re
from collections.abc import Callable, Collection, Mapping, Sequence
from pathlib import Path

import click

from rpg2gba.beat_floor.assertion import RowFloor
from rpg2gba.beat_floor.lookup import floor_for_row
from rpg2gba.beat_floor.walk import floor_for_chapter
from rpg2gba.beat_gen.adapt import (
    NoArrivalError,
    arm_row_ids,
    archetype_kwargs,
    escort_kwargs,
    is_boundary_warp,
    route_kwargs,
    trainer_consts_for,
    warp_candidates,
)
from rpg2gba.pbs_converter._naming import to_constant
from rpg2gba.beat_gen.arms import annotate_random_arms, blocked_arms, split_choice_arms
from rpg2gba.beat_gen.boundary import inbound_rows, split_outbound
from rpg2gba.beat_gen.continuity import attach_reclears, thread_maps
from rpg2gba.beat_gen.interiors import (
    arrival_nudge_edges,
    gated_entry_edges,
    gated_interior_edges,
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
from rpg2gba.beat_gen.counter_shadow import counter_shadow_proof
from rpg2gba.beat_gen.reach import engine_spawn, reachable_sites
from rpg2gba.beat_gen.rooms import Place, PlaceWorld, RoomIndex
from rpg2gba.beat_gen.emit import emit_module
from rpg2gba.beat_gen.facing import (
    OneShot,
    check_title_pages,
    event_ids_by_map,
    facing_sides,
    fold_one_shot_arms,
    one_shot_arms,
    one_shot_pages,
    pin_records,
    split_facing_arms,
)
from rpg2gba.beat_gen.gift_ceremony import annotate_gift_ceremonies
from rpg2gba.beat_gen.group import deferred_retalks, plan_beats
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
from rpg2gba.beat_gen.seam import (
    SeamCrossing, connection_crossings, connection_for, seam_crossings,
)
from rpg2gba.beat_gen.seed import deferred_loader, route_winner, walked_loader
from rpg2gba.beat_gen.page_sim import Firing
from rpg2gba.beat_gen.smash_lanes import sight_trainers_for, split_lane_gated, wait_edges
from rpg2gba.beat_gen.select import (
    cleared_obstacle_pages,
    dropped_events,
    empty_events,
    funnel_pages,
    select_rows,
)
from rpg2gba.beat_gen.round_trip import find_round_trip
from rpg2gba.beat_gen.state_arms import FIRING_TEMPLATES, Taint, fired_pages, select_state_arms
from rpg2gba.conversion_agent.flag_registry import load_label_tables
from rpg2gba.conversion_agent.transpiler import _ROCK_SMASH_RE, smashable_rock_event_ids
from rpg2gba.conversion_agent.orchestrator import load_map_event_strips
from rpg2gba.story_state.extract import RowState, extract_map
from rpg2gba.story_state.state import Switch, Test, Variable
from rpg2gba.beat_gen.whiteout import place_whiteout_beats
from rpg2gba.capability_sites import FIELD_CAPABILITY_ITEMS, teach_beat_name
from rpg2gba.chapter_atlas.binding import ChapterBinding, load_binding
from rpg2gba.chapter_manifest.capability_model import (
    _chain_ids,
    build_capability_model,
    taught_in_chain,
)
from rpg2gba.chapter_manifest.archetypes import ArchetypeMatch, classify_manifest
from rpg2gba.chapter_manifest.schema import ManifestRow, parse_row_id
from rpg2gba.playtest import chapters_gen as playtest_chapters_gen
from rpg2gba.playtest.archetypes import load_chapter_rows, map_uranium_id
from rpg2gba.playtest.cells import emitted_object, has_local_id, seam_press, seam_warp_cells
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
    _rom_touch_cells,
    cell_for_row,
    chapter_from_locations,
)
from rpg2gba.routing.occupancy import (
    MapOccupancy,
    _load_emitted_map,
    _load_map_constants_entry,
)
from rpg2gba.routing.connections import connections_between, load_connections
from rpg2gba.routing.pathing import RoutePlanningError, landing_cell
from rpg2gba.routing.plan import write_plan
from rpg2gba.routing.solver import RouteCandidate, RouteSolverError, solve_route
from rpg2gba.story_state.model import (
    RowVerdict,
    State,
    _cmp,
    _default_value,
    _state_key_repr,
    _write_satisfies,
    build_chapter_stories,
)
from rpg2gba.tileset_converter.invisible_wall import invisible_wall_ids, is_invisible_wall_page
from rpg2gba.tileset_converter.map_constants import load_display_names
from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS
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


def _party_ambiguous(match: ArchetypeMatch, floors: Mapping[str, RowFloor]) -> bool:
    """More than one trainers.json party matches the page's battle identity."""
    page = next(rid for rid, role in match.roles.items() if role == "battle")
    battles = [a for a in floors[page].assertions if a.kind == "battle"]
    if len(battles) != 1 or battles[0].param("kind") != "trainer":
        return False  # trainer_kwargs owns that error
    battle = battles[0]
    return len(trainer_consts_for(
        battle.param("name"), to_constant("TRAINER_CLASS", battle.param("trainer_type")),
        row_id=page)) > 1


def _generic_reads_it_better(match: ArchetypeMatch, floors: Mapping[str, RowFloor]) -> bool:
    """Matches whose page the generic template checks in full and the
    archetype's template only in part:
    - a trainer whose battle sits in an arm (Mawuli's "Wanna fight? -> Yes",
      map068/ev014): generic answers the menu per arm and checks the battle
      there, while `trainer_beats` reads intro and identity off the page;
    - a randomized flavour NPC (the TV, map048/ev011): generic checks the
      roll's write, the arm it picked (ruling 19's random arms) and the
      lines around it in one talk, while `flavour_npc_beat` checks only
      "one of the lines";
    - a trainer whose party is picked at run time (Theo in Nowtoch,
      map14000/ev079: `pbGet(1)` from the starter): `trainer_beats` needs
      one trainer const, while generic accepts any staged party of that
      identity -- the check CH01's lab battle already gets (operator call
      2026-10-09)."""
    if match.archetype == "trainer":
        return not _battle_on_page(match, floors) or _party_ambiguous(match, floors)
    return match.archetype == "flavour_npc" and match.params.get("variant") == "randomized"


def _match_for(beat: PlannedBeat, matches: Sequence[ArchetypeMatch]) -> ArchetypeMatch:
    """The archetype match an archetype beat was planned from: same
    archetype, and every role row claimed by the beat. By event alone is
    not enough -- a page-level archetype can match two pages of one event."""
    event_id = parse_row_id(beat.rows[0]).event_id
    deferred = set(dict(beat.kwargs).get("deferred_retalks", ()))
    found = [m for m in matches
             if m.archetype == beat.template and set(m.roles) - deferred <= set(beat.rows)]
    if len(found) != 1:
        raise ValueError(
            f"beat {beat.name!r}: expected one {beat.template} match on "
            f"map {beat.map_id} event {event_id}, found {len(found)}")
    return found[0]


def claim_generic_archetypes(beats: Sequence[PlannedBeat], claims: Mapping[str, str]
                             ) -> tuple[PlannedBeat, ...]:
    """Each generic beat holding a row in `claims` (row -> archetype of a
    match handed to the generic template) gets `archetype=` pairs for those
    rows, so the conformance rule sees the archetype claimed."""
    return tuple(
        _merge_kwargs(b, {"archetype": tuple((r, claims[r]) for r in b.rows if r in claims)})
        if b.template == "generic" and any(r in claims for r in b.rows) else b
        for b in beats)


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


def _with_return_press(beat: PlannedBeat) -> PlannedBeat:
    """A round-tripping threshold/arrow warp's `return_direction` from the
    warp geometry (`derive_return_direction`): `route_kwargs` can only
    reverse the forward press, which is wrong where both sides are entered
    the same way (CH06's park cave mouth: UP in, UP back out)."""
    kwargs = dict(beat.kwargs)
    if (beat.template != "warp" or "return_direction" not in kwargs
            or kwargs.get("mechanism") not in ("threshold", "arrow")):
        return beat
    from rpg2gba.playtest.archetypes.warp import derive_return_direction

    press = derive_return_direction(
        str(kwargs["map_constant"]), str(kwargs["dest_map_constant"]),
        int(kwargs["event_id"]), str(kwargs["direction"]))
    if press == kwargs["return_direction"]:
        return beat
    return _merge_kwargs(beat, {"return_direction": press}, drop=("return_direction",))


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


def _opened_before(
    gated: frozenset[tuple[int, int]], chapter_id: str, build_dir: Path,
    verdicts: Mapping[str, RowVerdict],
) -> frozenset[tuple[int, int]]:
    """Gated doors an EARLIER chapter already opened: a transfer page of the
    door is owned (live) by a chapter other than `chapter_id` (2026-10-15,
    CH08: the lab's exit, Map050 EV001, opens at `var101 >= 1` in CH01; the
    revisit walks out through it with no warp beat of its own)."""
    out: set[tuple[int, int]] = set()
    for map_id, event_id in sorted(gated):
        event = next((ev for ev in load_map_json(map_id, build_dir / "maps").get("events", [])
                      if ev and ev["id"] == event_id), None)
        if event is None:
            continue
        for idx, page in enumerate(event.get("pages", []) or []):
            if not any(c.get("code") == 201 for c in page.get("list", []) or []):
                continue
            v = verdicts.get(f"map{map_id:03d}/ev{event_id:03d}/p{idx}")
            if v is not None and v.owner is not None and v.owner != chapter_id:
                out.add((map_id, event_id))
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
                   rooms: RoomIndex | None = None,
                   stepped_transfers: frozenset[tuple[int, int]] | None = None,
                   warp_presses: Mapping[tuple[int, int], str] | None = None):  # noqa: ANN202
    """(`continuity.RouteBetween`, door steps) over this chapter's maps. The
    door steps map (map id, warp event) to every usable hop over that warp,
    for an arrival nudge that must land through one particular door
    (2026-10-02: Moki's stacked west exit, Kevlar's shop doors). The route: the fewest warp
    hops from place `a` to place `b` (`rooms.Place`, `(map id, room)`), each
    crossed from a reachable walkable side of its warp tile. A hop leaves the
    room of the side it is pressed from and lands in the room of its landing
    cell. Deterministic: edges are tried in sorted order.

    `stepped_transfers` (see `_stepped_transfers`) limits `warp` edges to the
    events a step fires; None keeps every edge (synthetic test worlds).
    `warp_presses` ((map id, event id) -> press) is the side each warp beat
    crosses from; a hop over one of those uses it. Otherwise the first
    reachable side in `_PRESS_INTO` order -- `reach` floods through warp
    tiles, so that side can be one the live walker can only reach by
    stepping on the warp (2026-09-27: Map048's stairs, north side (3,2)).
    `rooms` defaults to a `RoomIndex` over `graphs`."""
    rooms = rooms if rooms is not None else RoomIndex(graphs)

    def lands_reachably(e) -> bool:  # noqa: ANN001
        """The arrival's LANDING is reachable (a door arrival's destination
        cell is the solid door tile; the player stands one step off it).
        A seam arrival lands ON its arrow tile, and `reach` floods through
        warp tiles the live walker never steps on: it must have a reachable
        non-warp neighbour to walk off by (ROM run 74: Route 2 (20,56) is
        walled in except by its twin arrow (21,56))."""
        if e.kind == "seam_warp":
            exits = graphs[e.dst_map].warp_exits
            arrows = set(seam_warp_cells(e.dst_map, e.src_map))
            x, y = e.dst_cell
            return any((e.dst_map, n) in reach and n not in arrows and n not in exits
                       for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
        facing = next((w.dest_facing for w in graphs[e.src_map].warp_exits.get(e.src_cell, ())
                       if w.event_id == e.event_id), 0)
        try:
            return (e.dst_map, landing_cell(graphs[e.dst_map], e.dst_cell, facing=facing)) in reach
        except RoutePlanningError:
            return False

    connection_press: dict[tuple[int, int], str] = {}

    def connection_edges() -> list:
        """A real map connection has no trigger cell, so the world edge
        carries none: give each one the crossing the seam resolver picks
        (an edge cell reachable on this side whose offset-mapped cell on
        the far side is walkable, reachable and has an open landing), so a
        hop can stand on it and hold the edge press."""
        out = []
        loaded = None
        reached_maps = {m for m, _ in reach}
        for m in sorted(maps):
            for e in world.edges_from(m):
                if e.kind != "connection" or e.dst_map not in maps:
                    continue
                if e.src_map not in reached_maps or e.dst_map not in reached_maps:
                    # Outside this chapter's reachable world (CH09 enters at
                    # Moki's east edge; Kevlar/Route 2/Nowtoch are behind the
                    # rock wall): no crossing to pick, nothing to fail on. A
                    # connection both of whose maps ARE reached still has to
                    # line up, below.
                    logger.info("connection %d -> %d: a side is unreached from the entry "
                                "-- not a route edge", e.src_map, e.dst_map)
                    continue
                if loaded is None:
                    loaded = load_connections()
                picked = None
                for conn in connections_between(loaded, e.src_map, e.dst_map):
                    for c in connection_crossings(
                            conn, from_graph=graphs[e.src_map], to_graph=graphs[e.dst_map]):
                        if ((e.src_map, c.exit_cell) in reach
                                and (e.dst_map, c.entry_cell) in reach):
                            picked = c
                            break
                    if picked is not None:
                        break
                if picked is None:
                    raise ValueError(
                        f"connection {e.src_map} -> {e.dst_map}: no edge cell is passable "
                        "and reachable on both sides (offset-consistent)")
                connection_press[(e.src_map, e.dst_map)] = picked.press
                out.append(dataclasses.replace(
                    e, src_cell=picked.exit_cell, dst_cell=picked.entry_cell))
        return out

    edges = sorted(
        [e for m in sorted(maps) for e in world.edges_from(m)
         if e.kind in ("warp", "seam_warp") and e.dst_map in maps
         and e.src_cell is not None and e.dst_cell is not None
         and (e.kind != "warp" or stepped_transfers is None
              or (e.src_map, e.event_id) in stepped_transfers)
         and lands_reachably(e)] + connection_edges(),
        key=lambda e: (e.src_map, e.dst_map, e.src_cell, e.dst_cell))

    @functools.cache
    def dry_main(map_id: int) -> frozenset[tuple[int, int]]:
        """The largest region of `map_id`'s reachable cells connected without
        stepping on a warp tile -- where the live walker (which never steps
        on one) actually roams. `reach` alone floods through warps."""
        graph = graphs[map_id]
        warps = graph.warp_exits
        cells = {c for m, c in reach if m == map_id and c not in warps}
        best: set[tuple[int, int]] = set()
        seen: set[tuple[int, int]] = set()
        for seed in sorted(cells):
            if seed in seen:
                continue
            region = {seed}
            todo = [seed]
            while todo:
                cur = todo.pop()
                for e in graph.neighbors(cur):
                    if e.target in cells and e.target not in region:
                        region.add(e.target)
                        todo.append(e.target)
            seen |= region
            if len(region) > len(best):
                best = region
        return frozenset(best)

    def hop_for(edge) -> tuple[str, int, int, str, str] | None:  # noqa: ANN001
        x, y = edge.src_cell
        if edge.kind == "connection":
            # Stand ON the edge cell and hold the edge press.
            return (_map_constant_for(edge.src_map), x, y,
                    connection_press[(edge.src_map, edge.dst_map)],
                    _map_constant_for(edge.dst_map))
        press = (warp_presses or {}).get((edge.src_map, edge.event_id))
        if press is not None:
            # The warp's own beat already crosses it from the side the route
            # solver picked (its pathing keeps off warp tiles; `reach` does
            # not): cross it the same way.
            dx, dy = next(d for d, p in _PRESS_INTO if p == press)
            return (_map_constant_for(edge.src_map), x + dx, y + dy, press,
                    _map_constant_for(edge.dst_map))
        if edge.kind == "seam_warp":
            # An arrow fires on its own direction only; stand on the far
            # side of it from that press. `reach` floods through arrow
            # tiles, so the first reachable side can be a twin arrow cell
            # pressed the wrong way (CH06's park seam, run 2026-10-11).
            press = seam_press(edge.src_map, edge.dst_map, edge.src_cell)
            if press is None:
                raise ValueError(f"seam edge {edge.src_map}->{edge.dst_map} at {edge.src_cell}: "
                                 "no seam_warps entry names its direction")
            dx, dy = next(d for d, p in _PRESS_INTO if p == press)
            if (edge.src_map, (x + dx, y + dy)) not in reach:
                return None
            return (_map_constant_for(edge.src_map), x + dx, y + dy, press,
                    _map_constant_for(edge.dst_map))
        # `reach` floods through warp tiles, so a side can itself be another
        # warp, or a pocket reachable only across one: stand only in the
        # map's main warp-free region (`dry_main`). CH08 ROM runs: Route 1's
        # stacked east exits EV022-24 -- EV023 (70,11)'s south side was
        # EV022's own tile (70,12), its north side (70,10) a pocket above the
        # stack; the west side (69,11) is the one CH02's own warp beat uses.
        dry = dry_main(edge.src_map)
        for (dx, dy), press in _PRESS_INTO:
            if (x + dx, y + dy) in dry:
                return (_map_constant_for(edge.src_map), x + dx, y + dy, press,
                        _map_constant_for(edge.dst_map))
        return None

    usable = []
    for e in edges:
        h = hop_for(e)
        if h is not None:
            usable.append((e, h, rooms.place_of(e.src_map, (h[1], h[2])),
                           rooms.landing_place(e)))

    @functools.cache
    def route(a: Place, b: Place) -> "tuple[continuity.RouteStep, ...]":
        # The 4th element of each step is the hop's door event id (the
        # source map's warp event), which `continuity.thread_maps`' gated-
        # door guard needs -- `Hop` itself (`generic.transit_beat`'s own
        # shape) carries no event id, so it rides alongside instead.
        prev: dict[Place, tuple[Place, tuple]] = {a: (a, ())}
        frontier = [a]
        while frontier and b not in prev:
            nxt: list[Place] = []
            for m in frontier:
                for e, h, src, dst in usable:
                    if src == m and dst not in prev:
                        prev[dst] = (m, (src, dst, h, e.event_id))
                        nxt.append(dst)
            frontier = nxt
        if b not in prev or a == b:
            raise ValueError(f"no warp route from {a} to {b} over {sorted(maps)}")
        path = []
        node = b
        while node != a:
            node, step = prev[node]
            path.append(step)
        return tuple(reversed(path))

    door_steps: dict[tuple[int, int], list] = {}
    for e, h, src, dst in usable:
        door_steps.setdefault((e.src_map, e.event_id), []).append((src, dst, h, e.event_id))
    return route, {k: tuple(v) for k, v in door_steps.items()}


def _nudge_source(beat: PlannedBeat) -> tuple[int, int | None]:
    """(map, warp event) an arrival nudge's arrival comes from: the event is
    the template's own `from_event_id`, None when one warp is the only
    candidate (2026-10-02: Kevlar's shop doors, one nudge per door)."""
    kwargs = dict(beat.kwargs)
    event = kwargs.get("from_event_id")
    return (map_uranium_id(kwargs["from_map_constant"]),
            None if event is None else int(event))


def _beat_place(rooms: RoomIndex, beat: PlannedBeat, cell: tuple[int, int] | None) -> Place:
    """The place a beat stands in: the room of `cell` on its map. A
    single-room map is room 0 whatever the cell; a multi-room map with no cell
    for the beat fails loud."""
    if not rooms.is_multi_room(beat.map_id):
        return (beat.map_id, 0)
    if cell is None:
        raise ValueError(f"beat {beat.name!r} has no cell, and map {beat.map_id} has several "
                         f"rooms: cannot tell which room it is in")
    return rooms.place_of(beat.map_id, cell)


def _record_cell(record: BeatLocationRecord) -> tuple[int, int]:
    """Where the player stands for a located group: its first approach cell,
    else the located cell itself."""
    if record.approach_candidates:
        first = record.approach_candidates[0]
        return (first.x, first.y)
    return (record.x, record.y)


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


class _FixedBlocked:
    def __init__(self, cells: frozenset[tuple[int, int]]) -> None:
        self._cells = cells

    def blocked_cells(self) -> frozenset[tuple[int, int]]:
        return self._cells


class _ExtraWalls:
    """`occupancy` with `extra` cells held solid per map (`_tripwire_refusals`)."""

    def __init__(self, occupancy: Mapping,
                 extra: Mapping[int, frozenset[tuple[int, int]]]) -> None:
        self._occupancy = occupancy
        self._extra = extra

    def __getitem__(self, map_id: int) -> _FixedBlocked:
        return _FixedBlocked(self._occupancy[map_id].blocked_cells()
                             | self._extra.get(map_id, frozenset()))


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
            # The routing cell itself may sit in an unreachable pocket while
            # another approach candidate is reachable (CH07's south seam: its
            # first cell (0,56) is cut off, (20..25,56) are not). The solver
            # routes to that cell, so point it at the first reachable
            # candidate, in candidate order.
            record_map = map_uranium_id(record.map_constant)
            first_ok = next((a for a in record.approach_candidates
                             if (record_map, (a.x, a.y)) in reach), None)
            # Only when the routing cell IS one of the candidates: an event
            # cell with candidates on its sides is where the player stands ON
            # the event (an `onEvent?` arm reads that), not an alternative.
            if (routing_ok and first_ok is not None
                    and (record_map, (record.x, record.y)) not in reach
                    and any((a.x, a.y) == (record.x, record.y)
                            for a in record.approach_candidates)):
                logger.info("%s: %s routing cell (%d,%d) is unreachable -- re-pointed at "
                            "reachable candidate (%d,%d)", chapter_id, record.beat_id,
                            record.x, record.y, first_ok.x, first_ok.y)
                record = dataclasses.replace(record, x=first_ok.x, y=first_ok.y)
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
    # Arm rows count too (adapt._warp_assertion): a gated door's transfer
    # sits on its branch-arm floor, not the page trunk's.
    dests = {a.param("map_id") for r in beat.rows
             for rid in (r, *arm_row_ids(floors, r))
             for a in floors[rid].assertions if a.kind == "warp"}
    if len(dests) != 1:
        raise ValueError(f"warp beat {beat.name!r}: {len(dests)} destinations {sorted(dests)}")
    return dests.pop()


def _successor_exit_group(beats: Sequence[PlannedBeat], floors: Mapping[str, RowFloor],
                          own_maps: Collection[int], successor_maps: Collection[int] | None,
                          ) -> str | None:
    """The one group whose crossing (a warp or a seam) lands on a map the
    successor chapter adds, or None. The chapter's route ends there: its
    walk hands the player to the next chapter where that chapter begins
    (operator 2026-10-13 -- CH06 ended back in the cave it arrived through,
    when the way on is Nowtoch's overland seam to Route 2). Maps compare by
    Uranium origin, so a split piece counts as its map. Several candidates
    are logged and none is named (the solver's own rules stand)."""
    if not successor_maps:
        return None
    from rpg2gba.map_split.ids import origin_of

    targets = {origin_of(m) for m in successor_maps} - {origin_of(m) for m in own_maps}
    groups: set[str] = set()
    for b in beats:
        if b.template == "warp":
            dest = _warp_dest(b, floors)
        elif b.template == "seam":
            seams = [a for a in floors[b.rows[0]].assertions if a.kind == "seam_crossing"]
            if len(seams) != 1:
                continue
            dest = seams[0].param("other_map_id")
        else:
            continue
        if origin_of(int(dest)) in targets:
            groups.add(b.group)
    if len(groups) > 1:
        logger.info("successor exit: %d groups cross into the next chapter (%s); "
                    "naming none", len(groups), sorted(groups))
        return None
    return next(iter(groups), None)


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


def _page_candidate(verdicts: Mapping[str, RowVerdict], end_state, states: Mapping[str, RowState],
                    *, definite: bool = False) -> Callable[[str], bool]:
    """Can this page be the live page at all, within the chapter? A page the
    story model calls live or undetermined can; one it rules out
    (`unreachable`, `later`) can't; a `refused` page (its BODY isn't modelled,
    its condition is) can when every test of its condition is possible in the
    chapter's saturated end state. A page with no verdict can.

    `definite` asks for positive evidence instead: an undetermined page, or
    one with no verdict, can't. That is the question an actor's CLEARING
    page answers (`actor_never_blocks`): an optimistic answer there removes
    a wall (2026-10-11, CH06: Nowtoch's crowd clears on the Metro switch,
    which nothing in the chapter sets -- the model only called it
    undetermined because unmodelled rows elsewhere havoc every global)."""
    ends = dict(end_state)

    def possible_at_end(test) -> bool:  # noqa: ANN001
        values = ends.get(_state_key_repr(test.key))
        if values is None:
            values = tuple(_default_value(test.key))
        return "TOP" in values or any(_cmp(test.op, v, test.value) for v in values)

    def candidate(rid: str) -> bool:
        verdict = verdicts.get(rid)
        if verdict is None or verdict.status == "undetermined":
            return not definite
        if verdict.status == "live":
            return True
        if verdict.status == "refused":
            return all(possible_at_end(t) for t in states[rid].page_tests)
        return False
    return candidate


_DISPATCH_EVENT_RE = re.compile(r"^Map(\d{3,})_EV(\d{3})_")


def _page_visible(page: Mapping) -> bool:
    graphic = page.get("graphic") or {}
    return bool(graphic.get("character_name")) and graphic.get("opacity", 255) > 0


def actor_never_blocks(pages: Sequence[Mapping], can_live: Callable[[int], bool],
                       can_clear: Callable[[int], bool] | None = None) -> bool:
    """`_StoryOccupancy`'s rule for one event's pages: no visible page can be
    live in the chapter, or a graphic-less page above every visible one can
    (the actor clears) -- judged by `can_clear`, default `can_live`. An
    event with no visible page isn't an actor here."""
    can_clear = can_clear if can_clear is not None else can_live
    visible = [i for i, p in enumerate(pages) if _page_visible(p)]
    if not visible:
        return False
    if not any(can_live(i) for i in visible):
        return True
    return any(not _page_visible(pages[j]) and can_clear(j)
               for j in range(max(visible) + 1, len(pages)))


_TRANSITION_BLOCK_RE = re.compile(r"MAP_SCRIPT_ON_TRANSITION\s*\{")
_CLEARFLAG_RE = re.compile(r"^\s*clearflag\(\s*(FLAG_\w+)\s*\)\s*$")
_SETFLAG_RE = re.compile(r"^\s*setflag\(\s*(FLAG_\w+)\s*\)\s*$")


def transition_hidden_scripts(map_id: int, build_dir: Path) -> frozenset[str]:
    """Scripts of the map's object events the ROM hides on every load: the
    event's template `flag` (staged `map.json`) is set unconditionally -- a
    top-level `setflag` of the map's `MAP_SCRIPT_ON_TRANSITION` block, not one
    nested in an `if` -- in the map's dispatch `.pory`, and no `clearflag` of it appears anywhere
    in the block (map050's EV024 is hidden until FINAL_EVENT: it can block). Such an object is
    spawned only inside a script (CH07's Route 2 cutscene actors,
    FLAG_TEMP_16..18) and never stands on its tile outside one. Read from the
    ROM's own staging, not RMXP opacity. Fails loud when a map with flagged
    objects (its own `Map<id>_EV...` scripts; an item ball's
    pickup flag is not one) has no dispatch file."""
    constants = json.loads((build_dir / "porymap" / "map_constants.json")
                           .read_text(encoding="utf-8"))
    entry = constants.get(str(map_id))
    if entry is None:
        return frozenset()
    map_path = build_dir / "porymap" / "maps" / entry["dir_name"] / "map.json"
    if not map_path.exists():
        return frozenset()
    flagged = {oe["script"]: oe["flag"]
               for oe in json.loads(map_path.read_text(encoding="utf-8")).get("object_events", [])
               if oe.get("flag") and oe["flag"] != "0"
               and str(oe.get("script", "")).startswith(f"Map{map_id:03d}_EV")}
    if not flagged:
        return frozenset()
    pory = build_dir / "porymap" / "dispatch" / f"Map{map_id:03d}_dispatch.pory"
    if not pory.exists():
        raise FileNotFoundError(
            f"map {map_id} stages flag-hidden objects {sorted(flagged)} but has no dispatch "
            f"file {pory}; cannot tell which its ON_TRANSITION hides")
    text = pory.read_text(encoding="utf-8")
    set_flags: set[str] = set()
    cleared: set[str] = set()      # at any depth: a conditional clear can show it
    for m in _TRANSITION_BLOCK_RE.finditer(text):
        depth = 0                  # nesting inside the block; 0 = its top level
        for raw in text[m.end():].splitlines():
            line = raw.split("#", 1)[0]
            unset = _CLEARFLAG_RE.match(line)
            if unset:
                cleared.add(unset.group(1))
            if depth == 0:
                flag = _SETFLAG_RE.match(line)
                if flag:
                    set_flags.add(flag.group(1))
            depth += line.count("{") - line.count("}")
            if depth < 0:
                break
    return frozenset(script for script, flag in flagged.items() if flag in set_flags - cleared)


class _StoryOccupancy(Mapping):
    """`_LazyOccupancy` without the objects that can never be visible in the
    chapter: a flag-hidden actor (2026-10-02, late NPCs placed by the
    converter) none of whose visible-graphic pages can be the live page
    (`_page_candidate`). On the ROM such an object is never spawned, so it
    blocks nothing -- map050's FINAL_EVENT-gated EV024/EV025 had taken
    EV007's only approach cell away. An event with no story verdict for a
    visible page stays blocking (`_page_candidate` answers True).

    Also dropped, optimistically: an actor that CLEARS within the chapter --
    a graphic-less page above every visible page that can be live in it
    (RMXP: the highest live page wins, so once it is live the actor is gone
    for good). Fufufu (map14001/ev018) stands on the gym door's only
    approach until a switch-101 scene sets her self-switch B; as a permanent
    wall she pushed the whole gym out of CH06 (operator call 2026-10-09).
    The route still orders the gym after that scene through the door's own
    switch-101 page.

    `walls` are (map, event) pairs an obstacle beat claims: they stay
    blocking whatever the story model says. Moki's rocks clear on a self
    switch the `Kernel.pbRockSmash` arm writes; the model explores both arms
    of that Ruby test, calls the smashed page live, and the walk was routed
    into a cell the rocks still box in (2026-10-12). `build_plan` releases a
    wall whose clearing page is lifted by ANOTHER claimed beat's write
    (`_released_walls`): that clear is a real route step, not the rock's own
    Ruby test."""

    def __init__(self, inner: Mapping, *, build_dir: Path, candidate_for,  # noqa: ANN001
                 clear_for=None,  # noqa: ANN001
                 walls: frozenset[tuple[int, int]] = frozenset(),
                 dropped: frozenset[tuple[int, int]] = frozenset()) -> None:
        self._inner = inner
        self._dropped = dropped
        self._build_dir = build_dir
        self._candidate_for = candidate_for
        self._clear_for = clear_for if clear_for is not None else candidate_for
        self._walls = walls
        self._cache: dict[int, MapOccupancy] = {}
        self._hidden_cache: dict[int, frozenset[str]] = {}

    def with_walls(self, extra: Collection[tuple[int, int]]) -> "_StoryOccupancy":
        """The same view with `extra` (map, event) pairs held as walls."""
        return _StoryOccupancy(self._inner, build_dir=self._build_dir,
                               candidate_for=self._candidate_for, clear_for=self._clear_for,
                               walls=self._walls | frozenset(extra), dropped=self._dropped)

    def with_dropped(self, extra: Collection[tuple[int, int]]) -> "_StoryOccupancy":
        """The same view with `extra` (map, event) pairs not blocking at all
        (a barrier group's invisible walls, flooded as already cleared)."""
        return _StoryOccupancy(self._inner, build_dir=self._build_dir,
                               candidate_for=self._candidate_for, clear_for=self._clear_for,
                               walls=self._walls, dropped=self._dropped | frozenset(extra))

    def _rom_hidden(self, map_id: int) -> frozenset[str]:
        if map_id not in self._hidden_cache:
            self._hidden_cache[map_id] = transition_hidden_scripts(map_id, self._build_dir)
        return self._hidden_cache[map_id]

    def _never_visible(self, map_id: int, event_id: int) -> bool:
        if (map_id, event_id) in self._walls:
            return False
        if (map_id, event_id) in self._dropped:
            return True
        if f"Map{map_id:03d}_EV{event_id:03d}_Dispatch" in self._rom_hidden(map_id):
            logger.info("occupancy: map %d ev %d is hidden by the map's ON_TRANSITION "
                        "(spawned only inside a script) -- not blocking", map_id, event_id)
            return True
        data = load_map_json(map_id, self._build_dir / "maps")
        event = next((e for e in data.get("events", []) if e and e["id"] == event_id), None)
        if event is None:
            return False
        candidate = self._candidate_for(map_id)
        clears = self._clear_for(map_id)
        return actor_never_blocks(
            event.get("pages", []),
            lambda i: candidate(f"map{map_id:03d}/ev{event_id:03d}/p{i}"),
            lambda i: clears(f"map{map_id:03d}/ev{event_id:03d}/p{i}"))

    def clearing_rows(self, map_id: int) -> dict[tuple[int, int], tuple[str, ...]]:
        """cell -> the clearing page rows of an actor dropped from `map_id`
        because it CLEARS in the chapter (not because it is never visible):
        it still stands there until one of those pages goes live, so a beat
        that needs its cell waits for them (`_clearing_enablers`)."""
        out: dict[tuple[int, int], tuple[str, ...]] = {}
        candidate, clears = self._candidate_for(map_id), self._clear_for(map_id)
        data = load_map_json(map_id, self._build_dir / "maps")
        for tile in self._inner[map_id].tiles:
            m = _DISPATCH_EVENT_RE.match(tile.script)
            if not m or int(m.group(1)) != map_id:
                continue
            event_id = int(m.group(2))
            if (map_id, event_id) in self._walls:
                continue
            event = next((e for e in data.get("events", []) if e and e["id"] == event_id), None)
            if event is None:
                continue
            pages = event.get("pages", [])
            rid = f"map{map_id:03d}/ev{event_id:03d}/p{{}}".format
            visible = [i for i, p in enumerate(pages) if _page_visible(p)]
            if not visible or not any(candidate(rid(i)) for i in visible):
                continue
            rows = tuple(rid(j) for j in range(max(visible) + 1, len(pages))
                         if not _page_visible(pages[j]) and clears(rid(j)))
            if rows:
                out[tile.cell] = rows
        return out

    def __getitem__(self, map_id: int) -> MapOccupancy:
        if map_id not in self._cache:
            occ = self._inner[map_id]
            kept = []
            for tile in occ.tiles:
                m = _DISPATCH_EVENT_RE.match(tile.script)
                if m and int(m.group(1)) == map_id and self._never_visible(map_id, int(m.group(2))):
                    logger.info("occupancy: map %d %s is never visible, or clears, in this "
                                "chapter -- not blocking %s", map_id, tile.script, tile.cell)
                    continue
                kept.append(tile)
            self._cache[map_id] = dataclasses.replace(occ, tiles=tuple(kept))
        return self._cache[map_id]

    def __iter__(self):  # noqa: ANN204 - Mapping protocol
        return iter(self._inner)

    def __len__(self) -> int:
        return len(self._inner)


def _clearing_enablers(
    records: Sequence[BeatLocationRecord], clearing_rows: Callable[[int], Mapping],
    graphs: Mapping[int, MapGraph], enabled_by: Mapping[str, tuple[tuple[str, ...], ...]],
) -> dict[str, tuple[str, ...]]:
    """row -> an extra any-of enabler group: the writers that clear the actor
    standing on every cell its beat could be worked from (operator,
    2026-10-11: "order after the clear"). `_StoryOccupancy` drops a
    clearing actor from the walls, but it stands there until it clears --
    CH06's gym door page 0 is touched only from Fufufu's tile.

    The cells are the record's approach candidates, else the walkable
    non-warp sides of its own cell (a touch page is located on its event).
    Every one must be held by a clearing actor; the group is every
    enabler of every clearing page of those actors. Keyed by the record's
    first row, which `_derive_story_precedence` maps to its group."""
    out: dict[str, tuple[str, ...]] = {}
    for record in records:
        map_id = map_uranium_id(record.map_constant)
        held = clearing_rows(map_id)
        if not held or map_id not in graphs:
            continue
        graph = graphs[map_id]
        cells = [(c.x, c.y) for c in record.approach_candidates] or [
            n for n in ((record.x, record.y - 1), (record.x, record.y + 1),
                        (record.x - 1, record.y), (record.x + 1, record.y))
            if graph.is_walkable(n) and n not in graph.warp_exits]
        if not cells or (record.x, record.y) in held or not all(c in held for c in cells):
            continue
        writers = sorted({w for c in cells for row in held[c]
                          for group in enabled_by.get(row, ()) for w in group})
        if writers:
            out[record.rows[0]] = tuple(writers)
    return out


def _held_capabilities(binding: ChapterBinding, chapter_id: str) -> frozenset[str]:
    """Field capabilities the walk holds from this chapter's START (CH08 §9):
    obtainable by the predecessor chain -- enough badges and the HM (or its
    alternative item) granted (`ChapterCapabilityModel.obtainable`). Whether
    the move is taught yet doesn't matter here: the chapter's first smash beat
    teaches it (`_with_teach`)."""
    predecessor = binding.chapter(chapter_id).predecessor
    if predecessor is None:
        return frozenset()
    model = build_capability_model(predecessor)
    if model is None:
        return frozenset()
    return frozenset(t for t in FIELD_CAPABILITY_ITEMS if model.obtainable(t))


def _with_teach(beats: Sequence[PlannedBeat], taught: Collection[str]) -> tuple[PlannedBeat, ...]:
    """The first `smash` beat (walk order) per capability no predecessor
    suite has taught gets `teach=<teach_beat_name>`: it teaches the HM through
    the bag before clearing anything. That literal in the module is also what
    `capability_model.taught_in_chain` reads to call the capability held."""
    seen = set(taught)
    out = []
    for b in beats:
        cap = dict(b.kwargs).get("capability") if b.template == "smash" else None
        if cap is not None and cap not in seen:
            seen.add(cap)
            b = _merge_kwargs(b, {"teach": teach_beat_name(cap)})
        out.append(b)
    return tuple(out)


def _rock_approach_cells(map_id: int, event_id: int) -> frozenset[tuple[int, int]]:
    """Every walkable approach cell of a rock (a side that isn't walkable
    raises in `approach_to` and is simply not an approach)."""
    from rpg2gba.playtest.cells import approach_to
    constant = _map_constant_for(map_id)
    cells: set[tuple[int, int]] = set()
    for side in ("north", "south", "east", "west"):
        try:
            cells.add(tuple(approach_to(constant, event_id, prefer=side)))  # type: ignore[arg-type]
        except ValueError:
            continue
    return frozenset(cells)


@functools.lru_cache(maxsize=None)
def _map_lanes(constant: str) -> dict[int, frozenset[tuple[int, int]]]:
    from rpg2gba.playtest.cells import trainer_sight_lanes
    return trainer_sight_lanes(constant)


def _trainer_lane(map_id: int, event_id: int) -> frozenset[tuple[int, int]] | None:
    """A sight trainer's lane, or None when the event is no sight trainer on
    the ROM (no object, or no sight)."""
    from rpg2gba.playtest.cells import has_local_id, local_id
    constant = _map_constant_for(map_id)
    if not has_local_id(constant, event_id):
        return None
    return _map_lanes(constant).get(local_id(constant, event_id))


def _trainer_looks_around(map_id: int, event_id: int) -> bool:
    """`smash_lanes.split_lane_gated`'s `looks_around`: the trainer's compiled
    object turns at random (MOVEMENT_TYPE_LOOK_AROUND)."""
    from rpg2gba.playtest.cells import trainer_movement_type
    return trainer_movement_type(_map_constant_for(map_id), event_id) == "MOVEMENT_TYPE_LOOK_AROUND"


def _solve_with_lane_gates(gates: Mapping[str, tuple[int, ...]], solver: Callable,
                           *args: object, **kwargs: object):  # noqa: ANN202
    """`solve_route`, failing loud about lane gates when the solve can't
    order them: a gating trainer whose own approach needs the very rock it
    gates (passage through a released rock) is a precedence cycle."""
    try:
        return solver(*args, **kwargs)
    except RouteSolverError as exc:
        if not gates:
            raise
        raise RouteSolverError(
            f"{exc} -- lane-gated smash/stair beat(s) {dict(gates)} must follow their "
            "gating trainers' beats; if a gating trainer cannot be reached without "
            "smashing that rock, the order is a cycle") from exc


def _with_sight_trainers(beats: Sequence[PlannedBeat]) -> tuple[PlannedBeat, ...]:
    """Every smash beat gets `sight_trainers=`: the trainer events on its map
    still undefeated when it runs, whose lanes its walk must avoid."""
    sight = sight_trainers_for(beats, _trainer_lane)
    return tuple(_merge_kwargs(b, {"sight_trainers": sight[b.name]})
                 if b.template == "smash" else b for b in beats)


def _smashable_by_walk(
    held: Collection[str], maps: Collection[int], build_dir: Path,
    row_states: Callable[[int], Mapping[str, RowState]],
) -> tuple[frozenset[tuple[int, int]], frozenset[tuple[int, int]]]:
    """(rocks the walk clears ITSELF, rocks another event clears), each as
    (map, event), over every smashable rock on `maps` (CH08 §9). The first is
    empty unless Rock Smash is held. A rock some other event clears (CH07's
    rockslide: event 19's remote self-switch writes) stays that event's
    business -- the `_released_walls` test, with every row on the map as a
    candidate clearer -- so neither it nor its own rows count as held."""
    if "rock_smash" not in held:
        return frozenset(), frozenset()

    def events_of(m: int) -> list[dict]:
        return [ev for ev in load_map_json(m, build_dir / "maps").get("events", []) if ev]

    rocks = _smashable_rock_walls(maps, events_of)
    candidates = {rid for m in {m for m, _ in rocks} for rid in row_states(m)}
    externally = _released_walls(
        rocks, candidates, row_states=row_states,
        pages_of=lambda m, e: next((ev.get("pages", []) for ev in events_of(m)
                                    if ev["id"] == e), []))
    return frozenset(rocks) - frozenset(externally), frozenset(externally)


def _rock_yes_arm(row: ManifestRow) -> bool:
    """Is `row` the `then` arm of a rock's `Kernel.pbRockSmash` test -- the arm
    the held walk takes (its smash beat answers YES)? The else arm is the
    no-capability one."""
    b = row.branch
    return (row.kind == "branch" and b is not None and b.arm_kind == "then"
            and b.condition_type == 12 and isinstance(b.condition_text, str)
            and _ROCK_SMASH_RE.match(b.condition_text) is not None)


def _smashable_rock_walls(
    maps: Collection[int], events_of: Callable[[int], list[dict]],
) -> frozenset[tuple[int, int]]:
    """(map, event) of every smashable rock on `maps`, whether or not an
    obstacle beat claims it (CH07's rocks 14 and 17 belong to CH04)."""
    return frozenset((m, e) for m in sorted(maps) for e in smashable_rock_event_ids(events_of(m)))


def _released_walls(
    walls: Collection[tuple[int, int]], claimed_rows: Collection[str], *,
    row_states: Callable[[int], Mapping[str, RowState]],
    pages_of: Callable[[int, int], Sequence[Mapping]],
    blocks: Callable[[Mapping], bool] = _page_visible,
) -> dict[tuple[int, int], tuple[str, ...]]:
    """(map, event) wall -> the claimed rows that clear it, for each wall some
    OTHER claimed beat clears (CH07: a cutscene sets the self-switch that
    blanks the rockslide). A wall stays one when its only clearer is its own
    event (Moki's rocks: the rock's own `Kernel.pbRockSmash` arm -- the story
    model reads both arms of that test as live, which is wrong). A clearer is a
    row on another event whose write satisfies a test of a graphic-less page
    above every visible page of the wall's event (the clearing page
    `actor_never_blocks` and `clearing_rows` use). `blocks` says which pages
    make the event a wall (default: visible ones; `_barrier_walls` passes the
    invisible-wall test)."""
    out: dict[tuple[int, int], tuple[str, ...]] = {}
    for map_id, event_id in sorted(walls):
        pages = pages_of(map_id, event_id)
        visible = [i for i, p in enumerate(pages) if blocks(p)]
        if not visible:
            continue
        states = row_states(map_id)
        tests = []
        for j in range(max(visible) + 1, len(pages)):
            state = states.get(f"map{map_id:03d}/ev{event_id:03d}/p{j}")
            if not blocks(pages[j]) and state is not None:
                tests.extend(state.page_tests)
        if not tests:
            continue
        clearers = []
        for rid in sorted(claimed_rows):
            if not rid.startswith("map"):
                continue
            parsed = parse_row_id(rid)
            if (parsed.map_id, parsed.event_id) == (map_id, event_id):
                continue
            rs = row_states(parsed.map_id).get(rid)
            if rs is not None and any(_write_satisfies(w, t) for w in rs.writes for t in tests):
                clearers.append(rid)
        if clearers:
            out[(map_id, event_id)] = tuple(clearers)
    return out


def _page_leaves_chain(page: Mapping, chain_maps: Collection[int]) -> bool:
    """Does this page transfer the player (code 201, direct designation) to a
    map outside the chapter's chain?"""
    return any(c.get("code") == 201 and c.get("parameters", [None])[0] == 0
               and c["parameters"][1] not in chain_maps for c in page.get("list", []))


def _commands_write_any(commands: Sequence[Mapping], tests: Sequence[Test]) -> bool:
    """Does any raw command write a switch (121) or variable (122) a test reads?
    For a `computed` row whose writes aren't resolved here: it may clear the
    actor, so it counts as a clearer (the safe direction for `_exit_only_walls`)."""
    switches = {t.key.id for t in tests if isinstance(t.key, Switch)}
    variables = {t.key.id for t in tests if isinstance(t.key, Variable)}
    for c in commands:
        params = c.get("parameters") or []
        if len(params) < 2:
            continue
        lo, hi = params[0], params[1]
        ids = switches if c.get("code") == 121 else variables if c.get("code") == 122 else set()
        if any(lo <= i <= hi for i in ids):
            return True
    return False


def _exit_only_walls(
    chain_maps: Collection[int], events_of: Callable[[int], list[dict]], *,
    row_states: Callable[[int], Mapping[str, RowState]],
) -> frozenset[tuple[int, int]]:
    """(map, event) actors that can clear only as the player LEAVES the chapter.

    `actor_never_blocks` drops an actor once its graphic-less clearing page can
    be live. CH11 Route 4: the Hiker (map076 EV019) and Theo (EV020) block the
    cave mouth's one-wide corridor until var106 >= 1, and var106 is written only
    by the row-15 scene pages, which warp to Comet Cave (map 7, CH12) -- the
    transpiler hoists the write above that warp. Inside the chapter the actors
    stand; treating them as cleared put the cave mouth in the plan as a second
    exit. Every writer on the chain that satisfies a clearing test must be a
    page that leaves the chain; one in-chapter writer keeps today's rule."""
    def pages_of(m: int, e: int) -> Sequence[Mapping]:
        return next((ev.get("pages", []) for ev in events_of(m) if ev and ev["id"] == e), [])

    writers: list[tuple[str, RowState]] = [
        (rid, rs) for m in sorted(chain_maps) for rid, rs in row_states(m).items()]
    out: set[tuple[int, int]] = set()
    for map_id in sorted(chain_maps):
        states = row_states(map_id)
        for ev in events_of(map_id):
            if not ev:
                continue
            pages = ev.get("pages", [])
            visible = [i for i, p in enumerate(pages) if _page_visible(p)]
            if not visible:
                continue
            tests = [t for j in range(max(visible) + 1, len(pages)) if not _page_visible(pages[j])
                     for t in getattr(states.get(f"map{map_id:03d}/ev{ev['id']:03d}/p{j}"),
                                      "page_tests", ())]
            if not tests:
                continue
            clearers = [rid for rid, rs in writers
                        if any(_write_satisfies(w, t) for w in rs.writes for t in tests)
                        or (rs.computed is not None and not rs.writes
                            and _commands_write_any(rs.computed.commands, tests))]
            if not clearers:
                continue
            def leaves(rid: str) -> bool:
                p = parse_row_id(rid)
                if p.event_id is None or p.page_idx is None:
                    return False
                writer_pages = pages_of(p.map_id, p.event_id)
                return (p.page_idx < len(writer_pages)
                        and _page_leaves_chain(writer_pages[p.page_idx], chain_maps))
            if all(leaves(rid) for rid in clearers):
                out.add((map_id, ev["id"]))
    return frozenset(out)


def _barrier_walls(
    maps: Collection[int], events_of: Callable[[int], list[dict]],
    claimed_rows: Collection[str], *, row_states: Callable[[int], Mapping[str, RowState]],
) -> dict[tuple[int, int], tuple[str, ...]]:
    """(map, event) -> clearer rows, for a barrier group: each invisible wall
    (`invisible_wall_ids`) another claimed row clears, plus the HOST pillar --
    the visible event whose own claimed row is that clearer and whose own
    graphic-less page above its visible ones that same row's write lifts
    (Burole Gym EV045: its script removes 45/46/47 and sets their self-switch
    A). The host is the one place an own-event clearer counts; rocks keep
    their exclusion in `_released_walls`. The host carries the walls' clearers,
    so the pillar row itself is excluded from passage enablers."""
    def pages_of(m: int, e: int) -> Sequence[Mapping]:
        return next((ev.get("pages", []) for ev in events_of(m) if ev and ev["id"] == e), [])

    out: dict[tuple[int, int], tuple[str, ...]] = {}
    for m in sorted(maps):
        ids = invisible_wall_ids(events_of(m))
        if not ids:
            continue
        walls = _released_walls(
            {(m, e) for e in ids}, claimed_rows, row_states=row_states, pages_of=pages_of,
            blocks=is_invisible_wall_page)
        states = row_states(m)
        for pair, clearers in walls.items():
            out[pair] = clearers
            logger.info("barrier wall map %d ev %d is cleared by %s", *pair, list(clearers))
            for rid in clearers:
                parsed = parse_row_id(rid)
                if parsed.map_id != m or parsed.event_id == pair[1]:
                    continue
                pages = pages_of(m, parsed.event_id)
                visible = [i for i, p in enumerate(pages) if _page_visible(p)]
                if not visible:
                    continue
                tests = []
                for j in range(max(visible) + 1, len(pages)):
                    st = states.get(f"map{m:03d}/ev{parsed.event_id:03d}/p{j}")
                    if not _page_visible(pages[j]) and st is not None:
                        tests.extend(st.page_tests)
                rs = states.get(rid)
                if rs is not None and any(_write_satisfies(w, t) for w in rs.writes for t in tests):
                    host = (m, parsed.event_id)
                    out[host] = tuple(sorted({*out.get(host, ()), *clearers}))
                    logger.info("barrier host map %d ev %d clears itself with %s", *host, rid)
    return out


def _expand_to_pages(
    released: Mapping[tuple[int, int], tuple[str, ...]], claimed_rows: Collection[str],
) -> dict[tuple[int, int], tuple[str, ...]]:
    """Each clearer widened to every claimed row under its owning page. A
    one-shot page can be split into several groups (facing arms, CH07's event
    19); they are one physical bump, and any may be the walk's actual trigger,
    so ordering against the write's row alone would miss the others."""
    out: dict[tuple[int, int], tuple[str, ...]] = {}
    for pair, clearers in released.items():
        pages = {parse_row_id(c).owning_page_row_id or c for c in clearers}
        out[pair] = tuple(sorted(set(clearers) | {
            r for r in claimed_rows
            if r.startswith("map") and (parse_row_id(r).owning_page_row_id or r) in pages}))
    return out


def _released_killers(
    beats: Sequence[PlannedBeat], released: Mapping[tuple[int, int], tuple[str, ...]],
) -> dict[str, tuple[str, ...]]:
    """obstacle row -> the clearers of its released wall, which must come
    after it. `killed_before` only covers `FIRING_TEMPLATES`, and an obstacle
    beat doesn't fire its page, so the "the rock is gone afterwards" edge is
    not derived there; the clearer's write lifts a higher page of the rock's
    event, exactly what a killer edge says."""
    out: dict[str, tuple[str, ...]] = {}
    for b in beats:
        if b.template != "obstacle":
            continue
        for rid in b.rows:
            parsed = parse_row_id(rid)
            clearers = released.get((parsed.map_id, parsed.event_id))
            if clearers:
                out[rid] = clearers
    return out


def _tripwire_refusals(
    beats: Sequence[PlannedBeat], records: Sequence[BeatLocationRecord],
    released: Mapping[tuple[int, int], tuple[str, ...]], *,
    tripwire_cells: Callable[[int, int], frozenset[tuple[int, int]]],
    reach_avoiding: Callable[[Mapping[int, frozenset[tuple[int, int]]]], frozenset],
) -> list[Refusal]:
    """Obstacle rows whose refusal can't be walked before their own clearer.
    `_released_killers` puts an obstacle beat before the beat that clears
    its wall, but when that clearer is a Trainer(N) sight tripwire (coord
    triggers on its sight ray, `_rom_touch_cells`) and every approach to the
    obstacle crosses the ray, walking up fires the clearer first: the wall
    is gone before it can be refused (2026-10-14, CH07: Route 2's rockslide
    faces lie past event 19's ray). `reach_avoiding(cells)` floods from the
    entry with the released walls standing and `cells` held solid."""
    record_of = {r.beat_id: r for r in records}
    out: list[Refusal] = []
    for b in beats:
        if b.template != "obstacle" or b.group not in record_of:
            continue
        record = record_of[b.group]
        map_id = map_uranium_id(record.map_constant)
        sites = [(map_id, (c.x, c.y)) for c in record.approach_candidates] or [
            (map_id, (record.x, record.y))]
        for rid in b.rows:
            parsed = parse_row_id(rid)
            wires: dict[int, set[tuple[int, int]]] = {}
            owners: set[str] = set()
            for clearer in released.get((parsed.map_id, parsed.event_id), ()):
                cp = parse_row_id(clearer)
                cells = tripwire_cells(cp.map_id, cp.event_id)
                if cells:
                    wires.setdefault(cp.map_id, set()).update(cells)
                    owners.add(f"map{cp.map_id:03d}/ev{cp.event_id:03d}")
            if not wires:
                continue
            reach = reach_avoiding({m: frozenset(c) for m, c in wires.items()})
            if any(s in reach for s in sites):
                continue
            out.append(Refusal(
                row_id=rid, blocker="cell", reason="clearer_tripwire",
                detail=(f"every approach crosses the sight tripwire of {sorted(owners)}, "
                        "which clears this obstacle -- it is gone before it can be refused")))
    return out


def _clearer_sides_with_walls(
    records: Sequence[BeatLocationRecord],
    walls: Mapping[tuple[int, int], tuple[str, ...]],
    reach_with: Callable[[frozenset[tuple[int, int]]], Collection[tuple[int, tuple[int, int]]]],
) -> list[BeatLocationRecord]:
    """A beat that is itself a clearer of barrier `walls` is worked while those
    walls still stand, so only the approach sides reachable with them standing
    count (Burole Gym: the pillar row is the one link to the corridor north of
    it, so the pillar is pressed from the south, never from the cell behind
    it). `reach_with(own_walls)` floods from the entry with them held. Narrow
    rule, barrier groups only; a record keeps all its candidates if none
    survive (the old behaviour)."""
    cache: dict[frozenset[tuple[int, int]], Collection] = {}
    out: list[BeatLocationRecord] = []
    for rec in records:
        own = frozenset(p for p, cl in walls.items() if set(cl) & set(rec.rows))
        if own and len(rec.approach_candidates) > 1:
            if own not in cache:
                cache[own] = reach_with(own)
            m = map_uranium_id(rec.map_constant)
            kept = tuple(c for c in rec.approach_candidates if (m, (c.x, c.y)) in cache[own])
            if kept and len(kept) < len(rec.approach_candidates):
                logger.info("%s: approach sides %s dropped -- unreachable with %s standing",
                            rec.beat_id,
                            sorted(c.side for c in rec.approach_candidates if c not in kept),
                            sorted(own))
                rec = dataclasses.replace(rec, approach_candidates=kept)
        out.append(rec)
    return out


def _passage_enablers(
    records: Sequence[BeatLocationRecord], released: Mapping[tuple[int, int], tuple[str, ...]],
    *, reach_blocked: Collection[tuple[int, tuple[int, int]]],
    reach_open: Collection[tuple[int, tuple[int, int]]], exclude_rows: Collection[str],
) -> dict[str, tuple[str, ...]]:
    """row -> an any-of enabler group, for a record the player can reach from
    the chapter entry only THROUGH a released clearing actor: none of its sites
    is reachable while the released actors block (`reach_blocked`) but some is
    once they are dropped (`reach_open`). The group is every released actor's
    clearing writers, same shape as `_clearing_enablers`'. The caller floods
    twice (only when something was released), so this costs nothing on a
    chapter without a released wall. Records of `exclude_rows` (the walls
    themselves and their clearers) are skipped: their own edge is the reverse
    one (`_released_killers`) and an enabler would be a cycle."""
    writers = tuple(sorted({w for ws in released.values() for w in ws}))
    out: dict[str, tuple[str, ...]] = {}
    if not writers:
        return out
    # A record on a map with released walls waits on THOSE walls' clearers
    # (CH08: Route 1's rocks are opened by Route 1's smash beat, not Moki's);
    # elsewhere, on any clearer, as before.
    writers_on: dict[int, set[str]] = {}
    for (wall_map, _event), ws in released.items():
        writers_on.setdefault(wall_map, set()).update(ws)
    skip = set(exclude_rows)
    for record in records:
        if skip & set(record.rows):
            continue
        map_id = map_uranium_id(record.map_constant)
        sites = [(map_id, (c.x, c.y)) for c in record.approach_candidates] or [
            (map_id, (record.x, record.y))]
        if (not any(s in reach_blocked for s in sites)
                and any(s in reach_open for s in sites)):
            local = writers_on.get(map_id)
            out[record.rows[0]] = tuple(sorted(local)) if local else writers
    return out


def _drop_dead_before_clear(
    beats: Sequence[PlannedBeat], clearing: Mapping[str, tuple[str, ...]],
    group_order: Sequence[str], group_of_row: Mapping[str, str],
) -> tuple[tuple[PlannedBeat, ...], tuple[Elsewhere, ...]]:
    """The other half of "order after the clear" (operator, 2026-10-11): a
    row the solver still put before every claimed writer that clears its
    actor could not go after the clear -- a killer of its page comes first
    (`_feasible_any_of` drops the alternatives), so the page is dead by the
    time the actor moves. It never fires; its page's rows leave the walk.
    CH06: the gym door's "closed" page is worked only from Fufufu's tile,
    and the key removal that ends it precedes the scene that moves her."""
    pos = {g: i for i, g in enumerate(group_order)}
    dead: dict[str, str] = {}
    for rid, writers in clearing.items():
        group = group_of_row.get(rid)
        writer_groups = {group_of_row[w] for w in writers if w in group_of_row} - {group}
        if group not in pos or not writer_groups or not all(g in pos for g in writer_groups):
            continue
        if all(pos[g] > pos[group] for g in writer_groups):
            dead[rid] = (f"{rid} is worked only from a clearing actor's tile, and the "
                         f"route could not put it after any of its clearing writers "
                         f"{sorted(writers)} -- its page is dead by then; it never fires")
    if not dead:
        return tuple(beats), ()

    def page_of(r: str) -> str:
        return parse_row_id(r).owning_page_row_id or r

    out: list[PlannedBeat] = []
    gone: list[Elsewhere] = []
    for b in beats:
        drop = [r for r in b.rows if page_of(r) in dead]
        gone += [Elsewhere(r, "never_fires", detail=dead[page_of(r)]) for r in drop]
        kept = tuple(r for r in b.rows if r not in drop)
        if kept == b.rows:
            out.append(b)
        elif kept:
            out.append(dataclasses.replace(b, rows=kept))
        else:
            logger.info("clearing actor: %s never fires; beat %s dropped", drop, b.name)
    return tuple(out), tuple(gone)


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
    return _drop_never_fires(beats, proofs)


def _counter_never_fires(
    beats: Sequence[PlannedBeat], *, row_states, event_cell, graphs: Mapping[int, MapGraph],
    build_dir: Path,
) -> tuple[tuple[PlannedBeat, ...], tuple[Elsewhere, ...]]:
    """Third source of `never_fires` (`beat_gen/counter_shadow.py`): an action
    page whose event sits on a counter cell as no object, with an emitted
    object across the counter from every side -- pokeemerald answers with the
    object behind (2026-10-02, operator: accept the ROM's order)."""
    constants = build_dir / "porymap" / "map_constants.json"
    objects: dict[int, frozenset[tuple[int, int]]] = {}

    def object_cells(map_id: int) -> frozenset[tuple[int, int]]:
        if map_id not in objects:
            entry_ = _load_map_constants_entry(map_id, constants)
            emitted = _load_emitted_map(map_id, entry_["dir_name"], DEFAULT_ENGINE_MAPS_DIR)
            objects[map_id] = frozenset(
                (o["x"], o["y"]) for o in emitted.get("object_events", []))
        return objects[map_id]

    proofs: dict[str, str] = {}
    for b in beats:
        for rid in b.rows:
            page = parse_row_id(rid).owning_page_row_id or rid
            parsed = parse_row_id(page)
            if page in proofs or parsed.kind != "page":
                continue
            states = row_states(parsed.map_id)
            if page not in states or states[page].trigger != "action":
                continue
            cell = event_cell(page)
            if cell is None:
                continue
            proof = counter_shadow_proof(page, cell, graph=graphs[parsed.map_id],
                                         object_cells=object_cells(parsed.map_id))
            if proof is not None:
                proofs[page] = proof
                logger.info("never_fires: %s", proof)
    return _drop_never_fires(beats, proofs)


def _drop_never_fires(
    beats: Sequence[PlannedBeat], proofs: Mapping[str, str],
) -> tuple[tuple[PlannedBeat, ...], tuple[Elsewhere, ...]]:
    """`beats` without the rows of the proven pages (`proofs`: page row id ->
    proof), and those rows as `never_fires` elsewhere entries."""
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


# Elsewhere statuses whose rows cannot fire during this chapter's walk.
_CANNOT_FIRE_HERE = frozenset({"blocked", "unreachable", "later"})


def _unwalked_taint(beats: Sequence[PlannedBeat], verdicts: Sequence[RowVerdict],
                    row_states, elsewhere: Sequence[Elsewhere] = ()) -> list[Taint]:  # noqa: ANN001
    """Every write of a live row whose page the walk never fires -- or fires
    but which keeps running (a parallel page) -- as `state_arms` taint.

    A row the generator itself placed elsewhere as blocked (a capability it
    lacks), unreachable or later cannot fire in this chapter at all, so it
    taints nothing (2026-10-02, ROM run 64: the story model counts Grott-Hole
    Richboy's switch-100 arm live in CH03 -- it does not enforce Strength --
    so Maury's switch-100 page on map 73 read as undecided, not dead)."""
    fired = {p for b in beats if b.template in FIRING_TEMPLATES for p in fired_pages(b)}
    cannot_fire = {e.row_id for e in elsewhere if e.status in _CANNOT_FIRE_HERE}
    out: list[Taint] = []
    for v in verdicts:
        if v.status != "live" or v.row_id in cannot_fire:
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


def _dropped_events(rows: Sequence[ManifestRow],
                    build_dir: Path) -> dict[tuple[int, int], str]:
    """`select.dropped_events` over every map `rows` touch."""
    out: dict[tuple[int, int], str] = {}
    for map_id in sorted({r.map_id for r in rows if r.map_id is not None}):
        out.update(dropped_events(map_id, load_map_json(map_id, build_dir / "maps")))
    return out


def _funnel_pages(rows: Sequence[ManifestRow], build_dir: Path) -> dict[str, str]:
    """`select.funnel_pages` over every map `rows` touch."""
    out: dict[str, str] = {}
    for map_id in sorted({r.map_id for r in rows if r.map_id is not None}):
        out.update(funnel_pages(map_id, load_map_json(map_id, build_dir / "maps")))
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
                                    deferred_for=deferred_loader(chapter_id, module_dir),
                                    walked_for=walked_loader(chapter_id, module_dir),
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
    held = _held_capabilities(binding, chapter_id)
    held_obstacles, foreign_cleared = _smashable_by_walk(
        held, chain_maps, build_dir, _row_states_for(build_dir, resolved))
    cleared_pages = cleared_obstacle_pages(
        rows, floors,
        {m: load_map_json(m, build_dir / "maps")
         for m in sorted({r.map_id for r in rows if r.map_id is not None})},
        exclude=held_obstacles)
    selection = split_outbound(select_rows(rows, verdicts, floors, stripped=stripped,
                                           empty=empty,
                                           dropped=_dropped_events(rows, build_dir),
                                           funnels=_funnel_pages(rows, build_dir),
                                           held=held, held_obstacles=held_obstacles,
                                           foreign_cleared=foreign_cleared,
                                           cleared_pages=cleared_pages),
                               floors, chain_maps,
                               successor.id if successor is not None else None)
    # A cleared obstacle's empty page (a rock's "smashed" page: self switch A,
    # no graphic, no commands) has nothing to talk to on the ROM; the smash
    # beat asserts the rock is gone (CH08 §9).
    if held_obstacles:
        def _empty_obstacle_page(r: ManifestRow) -> bool:
            if r.kind != "page" or r.event_id is None \
                    or (r.map_id, r.event_id) not in held_obstacles:
                return False
            ev = next((e for e in load_map_json(r.map_id, build_dir / "maps").get("events", [])
                       if e and e["id"] == r.event_id), None)
            page = (ev or {}).get("pages", [])[r.page_idx] if ev else None
            return page is not None and all(c.get("code") == 0 for c in page.get("list") or [])
        cleared = [r for r in selection.owned if _empty_obstacle_page(r)]
        if cleared:
            gone_ids = {r.row_id for r in cleared}
            selection = Selection(
                owned=tuple(r for r in selection.owned if r.row_id not in gone_ids),
                refusals=selection.refusals,
                elsewhere=selection.elsewhere + tuple(
                    Elsewhere(r.row_id, "empty_page",
                              detail="the cleared obstacle's empty page; its smash beat "
                                     "asserts the obstacle is gone")
                    for r in cleared))
    # A blank, empty page of an object the ROM hides by flag (the visibility
    # machinery, `metadata_wiring.build_object_events`) has nothing to talk to
    # either: on that page the object isn't spawned (2026-10-15, CH08: Theo's
    # father Cam, Map172 EV001 p2 on sw55 -- absent in Uranium too).
    def _hidden_blank_page(r: ManifestRow) -> bool:
        if r.kind != "page" or r.event_id is None:
            return False
        ev = next((e for e in load_map_json(r.map_id, build_dir / "maps").get("events", [])
                   if e and e["id"] == r.event_id), None)
        pages = (ev or {}).get("pages", [])
        if r.page_idx is None or r.page_idx >= len(pages):
            return False
        page = pages[r.page_idx]
        if (page.get("graphic") or {}).get("character_name") \
                or not all(c.get("code") == 0 for c in page.get("list") or []):
            return False
        const = _map_constant_for(r.map_id)
        if not has_local_id(const, r.event_id):
            return False
        # Only the minted FLAG_HIDE_* hides (`FlagRegistry.mint_hide_flag`):
        # an item ball's own flag hides it too, but its spent page keeps the
        # approved "re-touch grants nothing" beat (CH05 map036 ev003/ev005 p1).
        return str(emitted_object(const, r.event_id).get("flag", "")).startswith("FLAG_HIDE_MAP")

    hidden_blank = [r for r in selection.owned if _hidden_blank_page(r)]
    if hidden_blank:
        gone_ids = {r.row_id for r in hidden_blank}
        selection = Selection(
            owned=tuple(r for r in selection.owned if r.row_id not in gone_ids),
            refusals=selection.refusals,
            elsewhere=selection.elsewhere + tuple(
                Elsewhere(r.row_id, "empty_page",
                          detail="a blank, empty page: the ROM hides the object by flag "
                                 "on it, so there is nothing to talk to")
                for r in hidden_blank))
    # A seam into a map the ROM doesn't build yet can't be crossed: the chapter
    # that builds the far side owns it (2026-10-15, CH08: Moki's east seam to
    # Route 3 is CH09's, #27). Before CH08 such seams were never reachable.
    unbuilt = [r for r in selection.owned
               if r.seam is not None and r.seam.other_map_id not in SLICE_MAP_IDS]
    if unbuilt:
        gone = {r.row_id for r in unbuilt}
        selection = Selection(
            owned=tuple(r for r in selection.owned if r.row_id not in gone),
            refusals=selection.refusals,
            elsewhere=selection.elsewhere + tuple(
                Elsewhere(r.row_id, "later",
                          successor.id if successor is not None
                          and r.seam.other_map_id in successor.maps else None)
                for r in unbuilt))
    inbound: tuple[ManifestRow, ...] = ()
    if predecessor is not None:
        pred_rows = load_chapter_rows(predecessor)
        pred_floors = floor_for_chapter(predecessor, build_dir=build_dir)
        inbound = inbound_rows(pred_rows, pred_floors,
                               frozenset(binding.chapter(chapter_id).maps),
                               _chain_maps(binding, predecessor))
        inbound_sel = select_rows(inbound, {v.row_id: v for v in stories[predecessor].rows},
                                  pred_floors, stripped=stripped,
                                  empty=_empty_events(inbound, build_dir),
                                  dropped=_dropped_events(inbound, build_dir),
                                  funnels=_funnel_pages(inbound, build_dir))
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
    # A held rock's YES arm is `capability:`-blocked in the story model (it
    # holds no capability there) but the walk takes it: the smash beat claims it.
    held_yes_arms = {r.row_id for r in selection.owned
                     if _rock_yes_arm(r) and (r.map_id, r.event_id) in held_obstacles}
    selection = blocked_arms(selection, all_verdicts, fork_owned | held_yes_arms)
    # CH08 §9: with the capability held, an obstacle page's remaining arms
    # (the no-capability / declined branch: "a Pokémon may be able to smash
    # it") are the branch the walk does NOT take -- its smash beat answers YES.
    if held_obstacles:
        def _held_arm(r: ManifestRow) -> bool:
            return (r.kind == "branch" and r.event_id is not None
                    and (r.map_id, r.event_id) in held_obstacles
                    and r.row_id not in held_yes_arms)
        declined = [r for r in selection.owned if _held_arm(r)]
        if declined:
            declined_ids = {r.row_id for r in declined}
            selection = Selection(
                owned=tuple(r for r in selection.owned if r.row_id not in declined_ids),
                refusals=selection.refusals,
                elsewhere=selection.elsewhere + tuple(
                    Elsewhere(r.row_id, "unselected_arm",
                              detail="the no-capability branch; the walk holds the "
                                     "capability and its smash beat answers YES (CH08 §9)")
                    for r in declined))
    # An archetype template reads its whole page -- arms included -- so a
    # match whose page has a refused arm can't register as that archetype
    # (CH01's map065/ev001: a #109 text gap on one arm). It falls to the
    # generic template, which reads each row's own floor; the arm stays a
    # named refusal.
    refused_ids = {r.row_id for r in selection.refusals}
    all_matches = [
        m for m in classify_manifest(inbound) + classify_manifest(rows)
        if not any(rid.startswith(f"{page}/") for page in m.roles for rid in refused_ids)]
    matches = tuple(m for m in all_matches if not _generic_reads_it_better(m, floors))
    # A match handed to the generic template is still that archetype: the
    # generic beat claims it, or the conformance rule reads the row as
    # unclaimed (CH06's TVs, map046/ev006+ev008; CH01's map048/ev011).
    generic_claims = {row: m.archetype for m in all_matches
                      if _generic_reads_it_better(m, floors) for row in m.roles}
    # A trainer's deferred retalk page (`group.deferred_retalks`) is a generic
    # beat of its own, still that trainer's retalk.
    generic_claims |= {row: m.archetype for m in matches
                       for row in deferred_retalks(m, rows_by_id)}
    fork_rows = tuple(r.row_id for r in selection.owned if r.row_id in fork_owned)
    beats = plan_beats(tuple(r for r in selection.owned if r.row_id not in fork_owned),
                       matches, floors, held_obstacles=held_obstacles)
    beats = claim_generic_archetypes(beats, generic_claims)
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
    one_shot_by_row: dict[str, OneShot] = {}
    for map_id, event_ids in sorted(event_ids_by_map(r for b in beats for r in b.rows).items()):
        map_data = load_map_json(map_id, build_dir / "maps")
        found = facing_sides(map_id, map_data, event_ids)
        sides_by_row.update(found)
        one_shot_by_row.update(one_shot_arms(map_id, map_data, found))
    beats, facing_pins, facing_elsewhere = split_facing_arms(
        beats, sides_by_row, one_shot_by_row)

    # 3d. Lane-gated rocks (`beat_gen/smash_lanes.py`): a rock every approach
    #     of which lies in a later trainer's sight lane is smashed after that
    #     trainer, in a second smash group.
    lane_split = split_lane_gated(beats, approach_cells=_rock_approach_cells,
                                  lane_of=_trainer_lane,
                                  looks_around=_trainer_looks_around)
    beats = lane_split.beats
    for name, gating in lane_split.gates.items():
        logger.info("lane-gated beat %s waits on trainer event(s) %s", name, list(gating))

    # 4. Locate. Graphs are lazy: a seam or a route may touch maps outside
    #    the chapter's own list (`routing.__main__._LazyGraphs`).
    graphs, overlays = _build_graphs_and_overlays(list(binding.chapter(chapter_id).maps),
                                                  build_dir)
    world = _build_world(build_dir)
    entry = _predecessor_end(predecessor) if predecessor is not None else engine_spawn()
    obstacle_walls = frozenset((p.map_id, p.event_id) for b in beats if b.template == "obstacle"
                               for p in map(parse_row_id, b.rows))
    # A wall another claimed beat clears is a clearing actor, not a wall
    # (`_released_walls`; CH07's rockslide, cleared by a cutscene).
    # Every smashable rock on the chain is a wall too, claimed by an obstacle
    # beat or not: the story model reads both arms of `Kernel.pbRockSmash`
    # and calls the smashed page live (Moki, 2026-10-12), but on the ROM the
    # rocks stand until something removes them.
    rock_walls = _smashable_rock_walls(
        chain_maps, lambda m: [ev for ev in load_map_json(m, build_dir / "maps").get("events", [])
                               if ev])
    obstacle_walls = obstacle_walls | rock_walls
    released = _released_walls(
        obstacle_walls, {r for b in beats for r in b.rows}, row_states=row_states,
        pages_of=lambda m, e: next((ev.get("pages", []) for ev in load_map_json(
            m, build_dir / "maps").get("events", []) if ev and ev["id"] == e), []))
    # Barrier group: invisible walls (and their host pillar) another claimed
    # row clears -- Burole Gym's pillar row, cleared by the gem puzzle.
    barrier = _barrier_walls(
        chain_maps, lambda m: [ev for ev in load_map_json(m, build_dir / "maps").get("events", [])
                               if ev],
        {r for b in beats for r in b.rows}, row_states=row_states)
    for pair, clearers in barrier.items():
        released.setdefault(pair, clearers)
    # CH08 §9: a smash beat clears its own rocks (held capability).
    for b in beats:
        if b.template == "smash":
            for rid in b.rows:
                p = parse_row_id(rid)
                released.setdefault((p.map_id, p.event_id), tuple(b.rows))
    for pair, clearers in released.items():
        logger.info("obstacle wall map %d ev %d is cleared by %s -- released", *pair,
                    list(clearers))
    exit_walls = _exit_only_walls(
        chain_maps, lambda m: [ev for ev in load_map_json(m, build_dir / "maps").get("events", [])
                               if ev], row_states=row_states)
    for pair in sorted(exit_walls):
        logger.info("actor map %d ev %d clears only on a page leaving the chapter -- held as a wall",
                    *pair)
    obstacle_walls = obstacle_walls | exit_walls
    occupancy = _StoryOccupancy(
        _LazyOccupancy(build_dir), build_dir=build_dir,
        candidate_for=lambda m: _page_candidate(all_verdicts, story.end_state, row_states(m)),
        clear_for=lambda m: _page_candidate(all_verdicts, story.end_state, row_states(m),
                                            definite=True),
        walls=obstacle_walls - frozenset(released))
    # 3c. Touch pages the walk can't step on while they are live (guard rows,
    #     arrival displacement): never_fires, not beats.
    facts_for = _map_facts_factory(
        row_states=row_states, page_for=_page_for(build_dir), event_cell=_event_cell(build_dir),
        build_dir=build_dir, graphs=graphs, world=world, chain_maps=chain_maps, entry=entry,
        occupancy=occupancy, verdicts=all_verdicts, end_state=story.end_state)
    beats, touch_elsewhere = _touch_never_fires(beats, row_states=row_states, facts_for=facts_for)
    beats, counter_elsewhere = _counter_never_fires(
        beats, row_states=row_states, event_cell=_event_cell(build_dir), graphs=graphs,
        build_dir=build_dir)
    dead_elsewhere = dead_elsewhere + touch_elsewhere + counter_elsewhere
    warp_rows = frozenset(r for b in beats if b.template == "warp" for r in b.rows)
    records, cell_refusals = locate_beats(
        beats, rows_by_id,
        cell_fn=_cell_fn(warp_rows, graphs,
                         lambda m: _arrival_cells(world, graphs, m, chain_maps, entry),
                         frozenset(r for b in beats if b.template == "arrival_nudge"
                                   for r in b.rows),
                         frozenset(r for b in beats if b.template in ("obstacle", "smash")
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

    # 4b2. An obstacle walked up to only across its clearer's sight tripwire
    #      is cleared before it can be refused (`_tripwire_refusals`).
    if released:
        tripwire_maps = frozenset(binding.chapter(chapter_id).maps) | {entry[0]}
        walled = occupancy.with_walls(released)
        tripwire_refused = _tripwire_refusals(
            beats, records, released,
            tripwire_cells=lambda m, e: _rom_touch_cells(m, e) if m in tripwire_maps
            else frozenset(),
            reach_avoiding=lambda extra: reachable_sites(
                entry, graphs, world, tripwire_maps,
                _ChainOccupancy(_ExtraWalls(walled, extra), tripwire_maps)))
        if tripwire_refused:
            gone = {r.row_id for r in tripwire_refused}
            for r in tripwire_refused:
                logger.info("clearer tripwire: %s refused -- %s", r.row_id, r.detail)
            cell_refusals = [*cell_refusals, *tripwire_refused]
            beats = tuple(dataclasses.replace(b, rows=tuple(r for r in b.rows if r not in gone))
                          for b in beats if set(b.rows) - gone)
            records = [dataclasses.replace(r, rows=tuple(x for x in r.rows if x not in gone))
                       for r in records if set(r.rows) - gone]

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
    # 2026-10-11 (operator): a beat worked only from a clearing actor's tile
    # comes after the clear (`_clearing_enablers`).
    story_enabled_by = dict(story_enabled_by)
    clearing = _clearing_enablers(records, occupancy.clearing_rows, graphs, enabled_by)
    for rid, writers in clearing.items():
        logger.info("clearing actor: %s waits on any of %s", rid, list(writers))
        story_enabled_by[rid] = tuple(story_enabled_by.get(rid, ())) + (writers,)
    for rid, groups in wait_edges(lane_split, beats).items():
        story_enabled_by[rid] = tuple(story_enabled_by.get(rid, ())) + groups
    killers = killed_before(beats, wm=wm, seed=seeds[chapter_id],
                            claimed_rows=claimed_rows)
    passage: dict[str, tuple[str, ...]] = {}  # row -> the released walls' clearers it waits on
    if released:
        released = _expand_to_pages(released, claimed_rows)
        # Passage through a released actor waits on its clearers; the wall's
        # own obstacle beat comes before them.
        killers = dict(killers)
        for rid, after in _released_killers(beats, released).items():
            killers[rid] = tuple(sorted({*killers.get(rid, ()), *after}))
        # Flooded over the chapter's own maps plus the entry's, NOT the whole
        # chain: a detour through earlier chapters' maps (CH07: Nowtoch ->
        # Passage Cave -> Route 2's south door) reaches the south half without
        # the rockslide, but it is not this chapter's walk -- the beats here
        # are placed on the way the player came in. Rocks that no beat claims
        # are in `released` too (every smashable rock is a wall).
        flood_maps = frozenset(binding.chapter(chapter_id).maps) | {entry[0]}
        reach_open = reachable_sites(
            entry, graphs, world, flood_maps,
            _ChainOccupancy(occupancy.with_dropped(barrier), flood_maps))
        reach_blocked = reachable_sites(entry, graphs, world, flood_maps,
                                        _ChainOccupancy(occupancy.with_walls(released),
                                                        flood_maps))
        records = _clearer_sides_with_walls(
            records, {p: released[p] for p in barrier if p in released},
            lambda own: reachable_sites(entry, graphs, world, flood_maps, _ChainOccupancy(
                occupancy.with_walls(own), flood_maps)))
        candidates = {   # the solver reads sides from here, not from the records
            r.beat_id: tuple(RouteCandidate(x=c.x, y=c.y, side=c.side, resolver=c.resolver)
                             for c in r.approach_candidates)
            for r in records if r.approach_candidates}
        excluded = {r for b in beats if b.template in ("obstacle", "smash") for r in b.rows}
        excluded |= {w for ws in released.values() for w in ws}
        for rid, writers in _passage_enablers(
                records, released, reach_blocked=reach_blocked, reach_open=reach_open,
                exclude_rows=excluded).items():
            logger.info("passage through released actor: %s waits on any of %s",
                        rid, list(writers))
            passage[rid] = writers
            story_enabled_by[rid] = tuple(story_enabled_by.get(rid, ())) + (writers,)
    # 2026-09-28 ruling (one-way warps): enter a dead-end interior, do its
    # first-visit beats, leave; an arrival nudge after the warp landing on it.
    warp_beats = [b for b in beats if b.template == "warp"]
    # Places (`beat_gen/rooms.py`): a map with several disconnected rooms is
    # several regions. A group's place is the room of its located cell; the
    # dict keeps the FIRST beat per group (later writes win in `reversed`).
    rooms = RoomIndex(graphs)
    record_of = {r.beat_id: r for r in records}
    group_map = {b.group: _beat_place(rooms, b, (_record_cell(record_of[b.group])
                                                  if b.group in record_of else None))
                 for b in reversed(beats)}
    entry_place = rooms.place_of(*entry)
    soft = arrival_nudge_edges(
        nudge_groups={b.group: (b.map_id, *_nudge_source(b))
                      for b in beats if b.template == "arrival_nudge"},
        warp_groups={b.group: (b.map_id, _warp_dest(b, floors), int(dict(b.kwargs)["event_id"]))
                     for b in warp_beats})
    regions = dict(
        chapter_maps=frozenset(group_map.values()) | {entry_place}, entry_map=entry_place,
        group_map=group_map,
        group_warps={b.group: ((b.map_id, int(dict(b.kwargs)["event_id"])),)
                     for b in warp_beats},
        label=rooms.label, node_map=lambda place: place[0])
    place_world = PlaceWorld(world, rooms)
    gated = _gated_doors(chain_maps, build_dir)
    gated = gated - _opened_before(gated, chapter_id, build_dir, all_verdicts)
    terminal = _successor_exit_group(
        beats, floors, binding.chapter(chapter_id).maps,
        successor.maps if successor is not None else None)
    route = _solve_with_lane_gates(
        lane_split.gates, solve_route,
        chapter_from_locations(chapter_id, records), chapter_id,
        manifest_rows=all_rows, graphs=graphs, overlays=overlays,
        world=world, map_ids=_load_map_ids(build_dir),
        occupancy=occupancy, candidates=candidates, entry=entry,
        enabled_by=story_enabled_by, threshold_enabled_by=threshold_by, killed_before=killers,
        guard_enabled_by=guard_enabled_by(guard_waits, {r.beat_id: r.rows[0] for r in records}),
        soft_precedence=lambda accepted, any_of: soft + interior_exit_edges(
            place_world, **regions, hard_and_story=accepted, any_of=any_of),
        order_violations=region_order_check(place_world, **regions),
        # 2026-09-30 (operator): a region whose exit is a gated door is held
        # hard, and what its exit waits on outside comes before its entry.
        # A region behind gated entrances only opens with its first entry.
        derived_precedence=lambda accepted, any_of: gated_entry_edges(
            place_world, **regions, gated_doors=gated, hard_and_story=accepted, any_of=any_of,
        ) + gated_interior_edges(
            place_world, **regions, gated_doors=gated, hard_and_story=accepted),
        hard_order_violations=gated_region_check(place_world, **regions, gated_doors=gated),
        terminal_group=terminal,
    )

    # 6. Order, then adapt's route half. A warp whose destination is on no
    #    map of this chapter's chain is a chapter boundary (09_cli.md's
    #    blocker): it stops on the solver's side instead of round-tripping
    #    into a map this chapter's ROM doesn't build.
    group_order, picks = route_order(route.nodes)
    check_guard_order(guard_waits, group_order, group_of_row)
    beats = order_beats(beats, group_order, _picks_with_fallback(records, picks))
    if held:
        predecessor_chain = (_chain_ids(binding, predecessor)
                             if predecessor is not None else frozenset())
        beats = _with_teach(beats, taught_in_chain(predecessor_chain))
    beats, cleared_too_late = _drop_dead_before_clear(beats, clearing, group_order, group_of_row)
    nudge_groups = {b.group for b in beats if b.template == "arrival_nudge"}
    # 6b. Ruling 19 steps 4-5 (`beat_gen/state_arms.py`): with the order and
    #     the cells known, keep only the arms the walk's state and position
    #     select, re-firing a page whose own writes select the rest.
    liveness_problems: list[LivenessProblem] = []
    beats, state_elsewhere = select_state_arms(
        beats, seeds[chapter_id], order_problems=liveness_problems, row_states=row_states, page_for=_page_for(build_dir),
        firing_for=_firing_for(records, nudge_groups, _event_cell(build_dir)),
        taint=_unwalked_taint(beats, story.rows, row_states, selection.elsewhere),
        walkable=lambda rid: rid in floors and not floors[rid].refused,
        choice_openers=lambda rid: [a.list_index for a in floors[rid].assertions
                                    if a.kind == "choice"] if rid in floors else [])
    check_title_pages(
        beats, lambda page: row_states(parse_row_id(page).map_id)[page].trigger)
    # 6c. An arms beat of a one-shot page another beat fires has no second
    #     firing to step into (`beat_gen/facing.py` `fold_one_shot_arms`).
    page_owners = {o for b in beats if b.template == "generic" for r in b.rows
                   if (o := parse_row_id(r).owning_page_row_id) is not None}
    one_shot_pg: dict[str, OneShot] = {}
    for map_id in sorted({parse_row_id(o).map_id for o in page_owners}):
        one_shot_pg.update(one_shot_pages(
            map_id, load_map_json(map_id, build_dir / "maps"),
            (o for o in page_owners if parse_row_id(o).map_id == map_id)))
    beats, one_shot_elsewhere = fold_one_shot_arms(beats, one_shot_pg, floors)
    beats = tuple(
        _apply_route_kwargs(
            b, boundary=b.template == "warp" and is_boundary_warp(b, floors, chain_maps),
            nudge_group=b.group in nudge_groups)
        for b in beats)
    beats = tuple(_with_return_press(b) for b in beats)
    beats = _with_sight_trainers(beats)

    # 7. Map continuity (`beat_gen/continuity.py`): each warp's start and
    #    end side follow from where the player is and where the next beat is.
    group_node = {n.group: n for n in route.nodes if n.kind == "group"}

    def solved_place(b: PlannedBeat) -> Place:
        node = group_node.get(b.group)
        return _beat_place(rooms, b, node.cell if node is not None and node.map_id == b.map_id
                           else None)

    press_dir = dict(_PRESS_INTO)
    side_offset = {p: d for d, p in press_dir.items()}
    beat_place = {b.name: solved_place(b) for b in beats}
    warp_origin: dict[str, Place] = {}
    warp_dest: dict[str, Place] = {}
    for b in beats:
        if b.template not in ("warp", "escort"):
            continue
        kwargs = dict(b.kwargs)
        if b.template == "warp":
            if kwargs.get("boundary", False):
                origin = beat_place[b.name]
            else:
                from rpg2gba.playtest.cells import event_cell
                ex, ey = event_cell(_map_constant_for(b.map_id), int(kwargs["event_id"]))
                dx, dy = side_offset[str(kwargs["direction"])]
                origin = _beat_place(rooms, b, (ex + dx, ey + dy))
            warp_origin[b.name] = origin
        else:
            origin = beat_place[b.name]
        dest_map = _warp_dest(b, floors)
        landings = sorted({e.dst_map for e in place_world.edges_from(origin)
                           if e.event_id == int(kwargs["event_id"]) and e.dst_map[0] == dest_map})
        if landings:
            warp_dest[b.name] = landings[0]
        elif not rooms.is_multi_room(dest_map):
            warp_dest[b.name] = (dest_map, 0)
        else:
            raise ValueError(f"{b.template} beat {b.name!r}: no edge from {origin} over event "
                             f"{kwargs['event_id']} lands on multi-room map {dest_map}")
    route_between, door_steps = _route_between(
        world, chain_maps, reachable_sites(entry, graphs, world, chain_maps, occupancy),
        graphs, rooms=rooms, stepped_transfers=_stepped_transfers(chain_maps, build_dir),
        warp_presses=_warp_presses(beats))
    beats = thread_maps(
        beats, start=rooms.place_of(route.nodes[0].map_id, route.nodes[0].cell),
        beat_place=beat_place, warp_dest=warp_dest, warp_origin=warp_origin,
        nudge_source={b.name: _nudge_source(b) for b in beats if b.template == "arrival_nudge"},
        places_on_map={m: rooms.places_on_map(m)
                       for m in sorted({b.map_id for b in beats} | set(chain_maps))},
        route_between=route_between, door_steps=door_steps,
        gated_doors=gated,
    )
    # 7b. A transit's arrival reloads its map: walls cleared earlier there stand again.
    beats = attach_reclears(beats, _map_constant_for, passage)

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
        elsewhere=(selection.elsewhere + dead_elsewhere + choice_elsewhere + facing_elsewhere
                   + state_elsewhere + one_shot_elsewhere + cleared_too_late),
        order_dependent=_live_order_dependent(
            story.order_dependent, state_elsewhere + facing_elsewhere),
        route=route,
        liveness_problems=tuple(liveness_problems),
        lane_gates=tuple(sorted(lane_split.gates.items())),
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
    from rpg2gba.beat_gen.beats_sidecar import render_sidecar
    beats_path = out_dir / f"{plan.chapter_id}.beats.json"
    beats_path.write_text(
        render_sidecar(plan, floor_lookup=lambda row_id: floor_for_row(row_id, build_dir=build_dir),
                       locate=_ViewerLocator(build_dir)),
        encoding="utf-8")
    logger.info("wrote %s", beats_path)  # sidecar: not in the returned fixed-order triple
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
