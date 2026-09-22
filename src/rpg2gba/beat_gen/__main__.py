"""`python -m rpg2gba.beat_gen generate --chapter CHnn` (C6 Task 9).

Ties the stages together and writes, under `--out-dir` (default
`output/beats/`):

    chNN.generated.py   the module (emit.py)
    CHnn.review.md      the review doc (review.py)
    CHnn.route.json     the solved route (routing.plan.write_plan)

Output lands in `output/` by ruling (C6 plan B1): C9, not C6, owns putting
a generated module under `playtest/chapters/` and a route under
`reference/routes/`.

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
import logging
import os
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import click

from rpg2gba.beat_floor.assertion import RowFloor
from rpg2gba.beat_floor.lookup import floor_for_row
from rpg2gba.beat_floor.walk import floor_for_chapter
from rpg2gba.beat_gen.adapt import (
    NoArrivalError,
    archetype_kwargs,
    is_boundary_warp,
    route_kwargs,
    warp_candidates,
)
from rpg2gba.beat_gen.boundary import inbound_rows, split_outbound
from rpg2gba.beat_gen.continuity import thread_maps
from rpg2gba.beat_gen.reach import reachable_sites
from rpg2gba.beat_gen.emit import emit_module
from rpg2gba.beat_gen.group import plan_beats
from rpg2gba.beat_gen.locate import locate_beats, order_beats, route_order
from rpg2gba.beat_gen.plan import (
    ARCHETYPE_TEMPLATES,
    ChapterPlan,
    Elsewhere,
    PlannedBeat,
    Refusal,
    Selection,
    make_kwargs,
)
from rpg2gba.beat_gen.review import render_review
from rpg2gba.beat_gen.seam import SeamCrossing, connection_for, seam_crossings
from rpg2gba.beat_gen.select import select_rows
from rpg2gba.chapter_atlas.binding import ChapterBinding, load_binding
from rpg2gba.chapter_manifest.archetypes import ArchetypeMatch, classify_manifest
from rpg2gba.chapter_manifest.schema import ManifestRow, parse_row_id
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
from rpg2gba.routing.pathing import RoutePlanningError, landing_cell
from rpg2gba.routing.plan import write_plan
from rpg2gba.routing.solver import RouteCandidate, solve_route
from rpg2gba.story_state.model import build_chapter_stories
from rpg2gba.traversal.graph import MapGraph
from rpg2gba.traversal.world import WorldGraph

logger = logging.getLogger(__name__)

BUILD_DIR = Path("output/uranium-build")
DEFAULT_OUT_DIR = Path("output/beats")
MANIFEST_DIR = Path("reference/manifests")


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
    cells = {e.dst_cell for e in world.edges_to(map_id)
             if e.src_map in chain_maps and e.dst_cell is not None}
    if entry is not None and entry[0] == map_id:
        cells.add(entry[1])
    landed: set[tuple[int, int]] = set()
    for c in cells:
        try:
            landed.add(landing_cell(graphs[map_id], c))   # a door-tile arrival steps off
        except RoutePlanningError:
            continue
    return tuple(sorted(landed))


def _cell_fn(warp_rows: frozenset[str], graphs: Mapping[int, MapGraph],
             arrivals: Callable[[int], tuple[tuple[int, int], ...]],
             nudge_rows: frozenset[str] = frozenset()):  # noqa: ANN202
    """`cell_for_row`, except:

    - a warp beat's row, or any row whose routing cell is a solid tile, gets
      its walkable sides as approach candidates (`cell_for_row` puts the
      player ON a warp, which offers the solver nothing to pick; Task 5's
      `warp_candidates`);
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
        # A routing cell on a SOLID tile (an event on a building's exit
        # mat) can't be stood on; like a warp, it's used from its sides.
        solid = not cell.approach_candidates and not graphs[row.map_id].is_walkable(
            (cell.x, cell.y))
        if row.row_id not in warp_rows and not solid:
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


_SPAWN_RE = re.compile(
    r"^\s*SetWarpDestination\(MAP_GROUP\((MAP_\w+)\),\s*MAP_NUM\(\1\),\s*WARP_ID_NONE,"
    r"\s*(\d+),\s*(\d+)\);", re.MULTILINE)


def _engine_spawn() -> tuple[int, tuple[int, int]]:
    """The new-game spawn, read from the engine's `WarpToTruck` (A5: CH01's
    start is "the engine spawn", a source fact -- `new_game.c`'s fenced
    override). Exactly one uncommented `SetWarpDestination` must be there."""
    root = Path(os.environ.get("RPG2GBA_POKEEMERALD", "engine"))
    source = (root / "src" / "new_game.c").read_text(encoding="utf-8")
    body = source[source.index("static void WarpToTruck(void)\n{"):]
    body = body[:body.index("\n}\n")]
    found = _SPAWN_RE.findall(body)
    if len(found) != 1:
        raise ValueError(f"new_game.c WarpToTruck: expected one SetWarpDestination, found "
                         f"{len(found)}")
    const, x, y = found[0]
    return map_uranium_id(const), (int(x), int(y))


_PRESS_INTO = (((0, 1), "UP"), ((0, -1), "DOWN"), ((-1, 0), "RIGHT"), ((1, 0), "LEFT"))
"""(offset of the approach cell from the warp tile, the press onto it):
standing south of it you press UP, and so on. N/S/W/E-side order."""


def _route_between(world: WorldGraph, maps: frozenset[int],
                   reach: frozenset[tuple[int, tuple[int, int]]]):  # noqa: ANN202
    """`continuity.RouteBetween` over this chapter's maps: the fewest warp
    hops from map `a` to map `b`, each crossed from a reachable walkable side
    of its warp tile. Deterministic: edges are tried in sorted order."""
    edges = sorted(
        (e for m in sorted(maps) for e in world.edges_from(m)
         if e.kind in ("warp", "seam_warp") and e.dst_map in maps
         and e.src_cell is not None and (e.dst_map, e.dst_cell) in reach),
        key=lambda e: (e.src_map, e.dst_map, e.src_cell, e.dst_cell))

    def hop_for(edge) -> tuple[str, int, int, str, str] | None:  # noqa: ANN001
        x, y = edge.src_cell
        for (dx, dy), press in _PRESS_INTO:
            if (edge.src_map, (x + dx, y + dy)) in reach:
                return (_map_constant_for(edge.src_map), x + dx, y + dy, press,
                        _map_constant_for(edge.dst_map))
        return None

    usable = [(e, h) for e in edges if (h := hop_for(e)) is not None]

    @functools.cache
    def route(a: int, b: int) -> tuple[tuple[int, int, tuple[str, int, int, str, str]], ...]:
        prev: dict[int, tuple[int, tuple]] = {a: (a, ())}
        frontier = [a]
        while frontier and b not in prev:
            nxt: list[int] = []
            for m in frontier:
                for e, h in usable:
                    if e.src_map == m and e.dst_map not in prev:
                        prev[e.dst_map] = (m, (e.src_map, e.dst_map, h))
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


def _split_unreachable(
    records: Sequence[BeatLocationRecord], entry: tuple[int, tuple[int, int]],
    graphs: Mapping[int, MapGraph], world: WorldGraph, chain_maps: frozenset[int],
    binding: ChapterBinding, chapter_id: str, occupancy: Mapping,
) -> tuple[list[BeatLocationRecord], dict[str, str | None]]:
    """(records the player can reach, {unreachable row: later owner}).

    Row by row: a group spanning several cells (an obstacle group's rocks, an
    exit strip, a staircase) keeps the rows the player can reach and is
    re-pointed at one of them when its routing row is the unreachable one; a
    group with no reachable row leaves the plan. The owner is the first
    successor chapter whose maps, added to this chain, make the row
    reachable. Only chapters with a committed manifest are searched --
    beyond them the maps aren't staged in this build -- so None means "no
    chapter derived so far opens it"."""
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

    later: dict[str, str | None] = {}
    if dropped:
        wider, owners = chain_maps, []
        nxt = binding.successor(chapter_id)
        while nxt is not None and (MANIFEST_DIR / f"{nxt.id}.manifest.json").exists():
            wider = wider | frozenset(nxt.maps)
            owners.append((nxt.id, reachable_sites(entry, graphs, world, wider, occupancy)))
            nxt = binding.successor(nxt.id)
        for row, sites in dropped.items():
            later[row] = next((cid for cid, rs in owners if any(s in rs for s in sites)), None)
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


def build_plan(chapter_id: str, *, build_dir: Path = BUILD_DIR) -> ChapterPlan:
    """Run stages 1-4 for one chapter and return the fully decided plan."""
    # 1. Load.
    binding = load_binding(DEFAULT_CHAPTERS_PATH)
    predecessor = binding.chapter(chapter_id).predecessor
    successor = binding.successor(chapter_id)
    rows = load_chapter_rows(chapter_id)
    stories = build_chapter_stories(_chain_to(binding, chapter_id), build_dir=build_dir,
                                    chapters_path=DEFAULT_CHAPTERS_PATH)
    story = stories[chapter_id]
    verdicts = {v.row_id: v for v in story.rows}
    floors: dict[str, RowFloor] = floor_for_chapter(chapter_id, build_dir=build_dir)
    chain_maps = _chain_maps(binding, chapter_id)

    # 2. Select, hand boundary events to the successor, and claim the
    #    predecessor's crossings into this chapter (§10 R2/R3,
    #    `beat_gen/boundary.py`). Inbound beats search the predecessor's
    #    manifest (`manifest_chapter_id=`).
    selection = split_outbound(select_rows(rows, verdicts, floors), floors, chain_maps,
                               successor.id if successor is not None else None)
    inbound: tuple[ManifestRow, ...] = ()
    if predecessor is not None:
        pred_rows = load_chapter_rows(predecessor)
        pred_floors = floor_for_chapter(predecessor, build_dir=build_dir)
        inbound = inbound_rows(pred_rows, pred_floors,
                               frozenset(binding.chapter(chapter_id).maps),
                               _chain_maps(binding, predecessor))
        inbound_sel = select_rows(inbound, {v.row_id: v for v in stories[predecessor].rows},
                                  pred_floors)
        selection = Selection(owned=inbound_sel.owned + selection.owned,
                              refusals=inbound_sel.refusals + selection.refusals,
                              elsewhere=inbound_sel.elsewhere + selection.elsewhere)
        floors.update({r.row_id: pred_floors[r.row_id] for r in inbound})
    all_rows = tuple(inbound) + tuple(rows)
    rows_by_id = {r.row_id: r for r in all_rows}
    # An archetype template reads its whole page -- arms included -- so a
    # match whose page has a refused arm can't register as that archetype
    # (CH01's map065/ev001: a #109 text gap on one arm). It falls to the
    # generic template, which reads each row's own floor; the arm stays a
    # named refusal.
    refused_ids = {r.row_id for r in selection.refusals}
    matches = tuple(
        m for m in classify_manifest(inbound) + classify_manifest(rows)
        if not any(rid.startswith(f"{page}/") for page in m.roles for rid in refused_ids))
    beats = plan_beats(selection.owned, matches, floors)
    inbound_ids = frozenset(r.row_id for r in inbound)
    beats = tuple(
        _merge_kwargs(b, {"manifest_chapter_id": predecessor})
        if inbound_ids and set(b.rows) <= inbound_ids else b
        for b in beats)

    # 3. Adapt, source half. An arrival nudge nothing lands on never fires:
    #    its whole group (the nudge and its arms) is refused by name.
    planned = beats
    adapted: list[PlannedBeat] = []
    dead_groups: dict[str, str] = {}
    for b in planned:
        if b.template in ARCHETYPE_TEMPLATES:
            try:
                b = _merge_kwargs(b, dict(archetype_kwargs(
                    b, _match_for(b, matches), floors,
                    map_constant_fn=_map_constant_for, rows=all_rows)))
            except NoArrivalError as exc:
                dead_groups[b.group] = str(exc)
        adapted.append(b)
    dead_refusals = tuple(Refusal(row_id, "cell", "no_arrival", dead_groups[b.group])
                          for b in planned if b.group in dead_groups for row_id in b.rows)
    beats = tuple(b for b in adapted if b.group not in dead_groups)
    beats = _group_boundary_exits(beats, floors, chain_maps)

    # 4. Locate. Graphs are lazy: a seam or a route may touch maps outside
    #    the chapter's own list (`routing.__main__._LazyGraphs`).
    graphs, overlays = _build_graphs_and_overlays(list(binding.chapter(chapter_id).maps),
                                                  build_dir)
    world = _build_world(build_dir)
    entry = _predecessor_end(predecessor) if predecessor is not None else _engine_spawn()
    warp_rows = frozenset(r for b in beats if b.template == "warp" for r in b.rows)
    records, cell_refusals = locate_beats(
        beats, rows_by_id,
        cell_fn=_cell_fn(warp_rows, graphs,
                         lambda m: _arrival_cells(world, graphs, m, chain_maps, entry),
                         frozenset(r for b in beats if b.template == "arrival_nudge"
                                   for r in b.rows)),
        seam_fn=_seam_fn(graphs), map_constant_fn=_map_constant_for)
    # A refused group has no record, so the solver can't visit it; its
    # beats leave the plan and survive only as refusals in the review doc.
    located = {r.beat_id for r in records}
    beats = tuple(b for b in beats if b.group in located)

    # 4b. Geography (`beat_gen/reach.py`): a group no site of which the
    #     player can reach from the entry over this chapter's maps belongs
    #     to the first successor whose maps open it.
    occupancy = _LazyOccupancy(build_dir)
    records, later = _split_unreachable(records, entry, graphs, world, chain_maps,
                                        binding, chapter_id, occupancy)
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

    # 5. Solve, with the same argument assembly as `routing plan`. The
    #    route starts where the predecessor leaves the player (A5), not at
    #    this chapter's first record.
    _check_trigger_overlay_or_raise(list(all_rows), chapter_id, overlays)
    candidates = {
        r.beat_id: tuple(RouteCandidate(x=c.x, y=c.y, side=c.side, resolver=c.resolver)
                         for c in r.approach_candidates)
        for r in records if r.approach_candidates
    }
    route = solve_route(
        chapter_from_locations(chapter_id, records), chapter_id,
        manifest_rows=all_rows, graphs=graphs, overlays=overlays,
        world=world, map_ids=_load_map_ids(build_dir),
        occupancy=occupancy, candidates=candidates, entry=entry,
    )

    # 6. Order, then adapt's route half. A warp whose destination is on no
    #    map of this chapter's chain is a chapter boundary (09_cli.md's
    #    blocker): it stops on the solver's side instead of round-tripping
    #    into a map this chapter's ROM doesn't build.
    group_order, picks = route_order(route.nodes)
    beats = order_beats(beats, group_order, _picks_with_fallback(records, picks))
    nudge_groups = {b.group for b in beats if b.template == "arrival_nudge"}
    beats = tuple(
        _apply_route_kwargs(
            b, boundary=b.template == "warp" and is_boundary_warp(b, floors, chain_maps),
            nudge_group=b.group in nudge_groups)
        for b in beats)

    # 7. Map continuity (`beat_gen/continuity.py`): each warp's start and
    #    end side follow from where the player is and where the next beat is.
    beats = thread_maps(
        beats, start_map=route.nodes[0].map_id,
        warp_dest={b.name: _warp_dest(b, floors) for b in beats if b.template == "warp"},
        nudge_source={b.name: map_uranium_id(dict(b.kwargs)["from_map_constant"])
                      for b in beats if b.template == "arrival_nudge"},
        route_between=_route_between(
            world, chain_maps, reachable_sites(entry, graphs, world, chain_maps, occupancy)),
    )

    return ChapterPlan(
        chapter_id=chapter_id,
        predecessor=predecessor,
        beats=beats,
        refusals=selection.refusals + dead_refusals + tuple(cell_refusals),
        elsewhere=selection.elsewhere,
        order_dependent=story.order_dependent,
        route=route,
    )


def write_outputs(plan: ChapterPlan, out_dir: Path, *, build_dir: Path = BUILD_DIR) -> list[Path]:
    """Write the three artifacts; return their paths in a fixed order
    (module, review, route). Overwrites; must be byte-identical on re-run."""
    if plan.route is None:
        raise ValueError(f"{plan.chapter_id}: plan has no solved route to write")
    out_dir.mkdir(parents=True, exist_ok=True)
    module_path = out_dir / f"{plan.chapter_id.lower()}.generated.py"
    review_path = out_dir / f"{plan.chapter_id}.review.md"
    route_path = out_dir / f"{plan.chapter_id}.route.json"

    module_path.write_text(emit_module(plan), encoding="utf-8")
    review_path.write_text(
        render_review(plan, floor_lookup=lambda row_id: floor_for_row(row_id, build_dir=build_dir)),
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
def generate(chapter_id: str, out_dir: Path) -> None:
    """Generate one chapter's module, review doc and route."""
    plan = build_plan(chapter_id)
    for path in write_outputs(plan, out_dir):
        logger.info("wrote %s", path)
    if plan.refusals:
        logger.warning("%s: %d rows refused -- see the review doc",
                       chapter_id, len(plan.refusals))


if __name__ == "__main__":
    cli()
