"""Coordinate resolvers for playtest chapter authoring.

**The ban.** As of CH05, `src/rpg2gba/playtest/chapters/*.py` may no longer
hardcode a map coordinate as a bare two-integer tuple literal
(`LARRIE_APPROACH = (18, 37)`-style). Three CH04 test failures traced to
exactly that pattern: a coordinate typed by hand, never checked against the
decoded map data it claimed to describe, silently wrong until a ROM run
caught it. `tests/test_chapter_coordinate_literals.py` is the lint that
enforces the ban (via AST, over `src/rpg2gba/playtest/chapters/*.py`); this
module is the replacement vocabulary a chapter author reaches for instead of
typing numbers.

**Why a resolver is not "the same thing, just longer."** A literal `(18, 37)`
carries no claim a machine can check — it is exactly as trustworthy typed
correctly as typed one tile off. A resolver *derives* the cell from this
build's own decoded output (`output/uranium-build/maps/Map###.json`, the
tileset arrays, the offline traversal graph in `rpg2gba.traversal.graph`) and
FAILS LOUD (CLAUDE.md §4.5) the moment the data doesn't support the answer it
was asked for — an event id that doesn't exist, an approach side that isn't
walkable, a warp with no destination match or more than one. A wrong literal
sits in the corpus looking exactly as confident as a correct one; a resolver
that can't derive an answer says so, at authoring time, in words that name
the map and what to do next. That asymmetry — silent-wrong vs. loud-can't —
is the entire point of the ban.

**The escape hatch.** `raw_cell()` exists for the residue: geometry the
pipeline's decoded data genuinely cannot express (an off-map camera anchor,
a point measured by hand against a screenshot). Every call is counted debt,
never free — see its docstring.

**Performance / idempotence.** `traversal.graph.build_map_graph` re-parses a
map's JSON and its tileset arrays from disk; chapter modules call these
resolvers many times at import time (module-level constants), so per-map
graphs are cached in a module-level dict keyed only on the resolved Uranium
map id -- the same inputs `build_map_graph` itself takes, so repeated calls
for the same map are pure cache hits and the cache can never make two calls
with identical inputs disagree (CLAUDE.md §4.2).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..tileset_converter.connections import ConnectionRow, load_connections
from ..tileset_converter.layout import column_key
from ..tileset_converter.terrain_tags import DEFAULT_TERRAIN_TAG_MAP, TerrainTagTable
from ..traversal.collision import build_tile_grid, load_map_json, load_tileset_arrays
from ..traversal.direction import Direction
from ..traversal.graph import MapGraph, build_map_graph
from . import chapter as _chapter

Cell = tuple[int, int]

#: Fork-independent instance used only for its `effective_tag()` -- exactly
#: `traversal.ledges`'s `_EFFECTIVE_TAG_ONLY` trick (see that module's
#: docstring): `TerrainTagTable.effective_tag` touches no fork data, only the
#: raw `terrain_tags` array and a column key, so constructing an otherwise-
#: empty table purely to call it is safe reuse of the one place the
#: "which tile's tag wins in a column" rule lives (CLAUDE.md §4.3), not a
#: second implementation of it.
_EFFECTIVE_TAG_ONLY = TerrainTagTable({}, {}, 0, 0, {})

DEFAULT_SEAM_WARPS_JSON = Path("reference/seam_warps.json")

_PREFER_TO_DIRECTION: dict[str, Direction] = {
    "north": Direction.NORTH,
    "south": Direction.SOUTH,
    "east": Direction.EAST,
    "west": Direction.WEST,
}

# Per-map graph cache. Keyed on the Uranium map id alone -- the only input
# `build_map_graph` is ever given here (this module always calls it with its
# defaults for maps_dir/tilesets_json/terrain_tag_map), so a repeated
# resolver call for the same map is a pure cache hit rather than re-parsing
# Map###.json and the tileset arrays from disk again. A plain dict rather
# than functools.lru_cache: the cache is process-lifetime and small (one
# entry per map a chapter touches), and a dict makes the "keyed on inputs
# only" invariant (CLAUDE.md §4.2 -- idempotence) visually obvious at the
# call site below rather than hidden behind a decorator.
_GRAPH_CACHE: dict[int, MapGraph] = {}

# The map_constant -> Uranium id reverse index is likewise cheap to reuse
# across many resolver calls in one chapter module's import, and reading it
# is a real file read (`output/uranium-build/porymap/map_constants.json`).
# `None` sentinel distinguishes "not yet loaded" from "loaded, happens to be
# empty" (which would never legitimately occur, but the sentinel pattern
# costs nothing and keeps the intent explicit).
_MAP_CONST_INDEX: dict[str, int] | None = None

#: tag (int, Essentials PBTerrain 0-22) -> MB_* behavior NAME (str), read
#: straight from `reference/terrain_tag_map.json` and never re-derived
#: (CLAUDE.md §4.3 -- this is the one source of truth for tag spelling; see
#: `tileset_converter.terrain_tags`). Kept as names, not fork-resolved
#: numeric enum values: `grass_cell` needs no `$RPG2GBA_POKEEMERALD` build
#: artifact, only "does this tag's *name* say MB_TALL_GRASS", so there is no
#: reason to pull in `_behavior_value`'s fork-header parse.
_TAG_BEHAVIOR_NAMES: dict[int, str] | None = None

#: seam_warps.json's `seams` list, cached whole -- it is small (currently one
#: entry) and read many times per chapter-module import, same rationale as
#: `_GRAPH_CACHE`/`_MAP_CONST_INDEX` above.
_SEAM_WARPS_CACHE: list[dict] | None = None


def _local_id_table_path(uid: int) -> Path:
    """Where staging writes map `uid`'s RMXP-event-id -> local-id table.

    Honours `RPG2GBA_OUTPUT` the same way the rest of the pipeline does
    (read, never set -- CLAUDE.md sec 3); `.env-paths` is what populates it.
    """
    root = Path(os.environ.get("RPG2GBA_OUTPUT", "output"))
    return root / "uranium-build" / "staging" / "local_ids" / f"Map{uid:03d}.json"


def _map_const_index() -> dict[str, int]:
    global _MAP_CONST_INDEX
    if _MAP_CONST_INDEX is None:
        # Reuses `chapter.py`'s own loader (built on `MapConstantRegistry`,
        # CLAUDE.md §4.3's one source of truth for map identity) rather than
        # hand-parsing the persisted JSON a second time -- see this task's
        # brief: import and call chapter.py's helper, never re-derive it.
        _MAP_CONST_INDEX = _chapter._load_map_const_to_uranium_id(
            _chapter.default_map_constants_state_path()
        )
    return _MAP_CONST_INDEX


def _tag_behavior_names(path: Path = DEFAULT_TERRAIN_TAG_MAP) -> dict[int, str]:
    global _TAG_BEHAVIOR_NAMES
    if _TAG_BEHAVIOR_NAMES is None:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        _TAG_BEHAVIOR_NAMES = {
            int(tag_str): entry["behavior"] for tag_str, entry in raw["tags"].items()
        }
    return _TAG_BEHAVIOR_NAMES


def _seam_warps(path: Path = DEFAULT_SEAM_WARPS_JSON) -> list[dict]:
    global _SEAM_WARPS_CACHE
    if _SEAM_WARPS_CACHE is None:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        _SEAM_WARPS_CACHE = raw["seams"]
    return _SEAM_WARPS_CACHE


def _uranium_id(map_constant: str, *, resolver: str) -> int:
    uid = _map_const_index().get(map_constant)
    if uid is None:
        raise ValueError(
            f"{resolver}: map constant {map_constant!r} does not resolve to "
            "any minted Uranium map id -- check the spelling against "
            "output/uranium-build/porymap/map_constants.json, or run the "
            "Phase 5 map-constant minting step if the state file is stale"
        )
    return uid


def _graph_for(map_constant: str, *, resolver: str) -> tuple[int, MapGraph]:
    uid = _uranium_id(map_constant, resolver=resolver)
    graph = _GRAPH_CACHE.get(uid)
    if graph is None:
        graph = build_map_graph(uid)
        _GRAPH_CACHE[uid] = graph
    return uid, graph


def _event_lookup(uid: int, event_id: int, *, map_constant: str, resolver: str) -> dict:
    map_json = load_map_json(uid)
    for event in map_json.get("events", []):
        if event and event.get("id") == event_id:
            return event
    known = sorted(e["id"] for e in map_json.get("events", []) if e)
    raise ValueError(
        f"{resolver}: {map_constant} (Uranium map {uid}) has no event id "
        f"{event_id} -- known event ids on this map are {known}"
    )


def event_cell(map_constant: str, event_id: int) -> Cell:
    """The cell event `event_id` occupies on `map_constant`.

    Fails loud, naming the map and the event ids that DO exist, if
    `event_id` is absent -- a typo'd event id is exactly the class of bug a
    bare literal would have hidden as "close enough".
    """
    uid, _graph = _graph_for(map_constant, resolver="event_cell")
    event = _event_lookup(uid, event_id, map_constant=map_constant, resolver="event_cell")
    return (event["x"], event["y"])


def local_id(map_constant: str, event_id: int) -> int:
    """The COMPILED object-event local id for RMXP event `event_id`.

    Not a coordinate, but the same class of hand-transcribed constant the
    ban exists for: `emu.object_event()` addresses the remapped space that
    `tileset_converter.local_id_remap` mints at staging, so an RMXP event id
    typed straight into a chapter addresses the wrong NPC (or none) and
    looks exactly as confident either way. CH02 and CH03 both carry theirs
    as literals with a citation comment; this is the resolver that replaces
    the comment with a check.

    Reads the staged table (`output/uranium-build/staging/local_ids/
    Map###.json`, generated output -- never hand-edited, CLAUDE.md sec 11)
    and fails loud two ways, because they need different fixes: a map with
    no table has not been through the staging step that writes one, while a
    map whose table omits the event means the event was never emitted as an
    object event at all (no boot page, or stripped).
    """
    uid = _uranium_id(map_constant, resolver="local_id")
    path = _local_id_table_path(uid)
    if not path.exists():
        raise ValueError(
            f"local_id: {map_constant} (Uranium map {uid}) has no local-id "
            f"table at {path} -- that file is written by "
            "scripts/stage_slice_scripts.py, so this map has not been "
            "staged; run the staging step before authoring against it"
        )
    table = json.loads(path.read_text(encoding="utf-8"))
    resolved = table.get(str(event_id))
    if resolved is None:
        known = sorted(int(k) for k in table)
        raise ValueError(
            f"local_id: {map_constant} (Uranium map {uid}) event {event_id} "
            f"is not an emitted object event -- events with local ids on "
            f"this map are {known}. An event with no boot page (or one that "
            "is stripped) never becomes an object event and has no local id"
        )
    return int(resolved)


def approach_to(map_constant: str, event_id: int, *, prefer: str | None = None) -> Cell:
    """The cell a player stands on to interact with event `event_id`.

    Candidates are `MapGraph.interaction_cells` around the event's own cell:
    each walkable orthogonal neighbour, or the cell across a counter on that
    side, kept in the deterministic N/S/E/W order.
    Without `prefer`, the first walkable candidate wins. With `prefer` (one
    of "north"/"south"/"east"/"west"), that specific side is required --
    fails loud if it isn't walkable rather than silently falling back to a
    different side, since a chapter author who wrote `prefer="south"` made a
    real claim about which side of the event the beat approaches from (e.g.
    matching a script's own directional check).

    If NO adjacent cell is walkable at all, fails loud saying the event
    cannot be approached from any side -- a real finding about the map, not
    an error to paper over with a nearby-but-wrong cell.
    """
    uid, graph = _graph_for(map_constant, resolver="approach_to")
    event = _event_lookup(uid, event_id, map_constant=map_constant, resolver="approach_to")
    cell = (event["x"], event["y"])

    # Walkable sides, reaching across a counter where there is one
    # (`MapGraph.interaction_cells`).
    by_side = dict(graph.interaction_cells(cell))
    candidates = list(by_side.values())

    if prefer is not None:
        direction = _PREFER_TO_DIRECTION.get(prefer)
        if direction is None:
            raise ValueError(
                f"approach_to: {map_constant} event {event_id}: prefer="
                f"{prefer!r} is not one of {sorted(_PREFER_TO_DIRECTION)}"
            )
        if direction not in by_side:
            dx, dy = direction.delta
            raise ValueError(
                f"approach_to: {map_constant} event {event_id} (cell {cell}) "
                f"cannot be approached from the {prefer} side -- that cell "
                f"({(cell[0] + dx, cell[1] + dy)}) is out of bounds or not "
                f"walkable, and no counter reaches across it; walkable "
                f"candidates are {candidates or 'none'}"
            )
        return by_side[direction]

    if not candidates:
        raise ValueError(
            f"approach_to: {map_constant} event {event_id} (cell {cell}) has "
            "no walkable adjacent cell on any side -- this event cannot be "
            "approached at all under the offline graph's collision data"
        )
    return candidates[0]


def _matching_warp_exits(graph: MapGraph, dest_uid: int):
    matches = []
    for cell, exits in graph.warp_exits.items():
        for exit_ in exits:
            if exit_.dest_map == dest_uid:
                matches.append((cell, exit_))
    matches.sort(key=lambda pair: (pair[0][1], pair[0][0], pair[1].event_id))
    return matches


def warp_cell(map_constant: str, *, to: str, event_id: int | None = None) -> Cell:
    """The cell you stand on (and trigger) to warp from `map_constant`
    toward map constant `to`.

    Searches `graph.warp_exits` for exits whose destination is `to`'s
    Uranium id. Exactly one match returns its trigger cell. Zero matches
    fails loud. MORE than one match ALSO fails loud, listing every candidate
    cell and its event id and telling the caller to disambiguate with
    `event_id=` -- an ambiguous warp is never resolved by silently picking
    the first candidate, per this ban's whole point.
    """
    uid, graph = _graph_for(map_constant, resolver="warp_cell")
    dest_uid = _uranium_id(to, resolver="warp_cell")
    matches = _matching_warp_exits(graph, dest_uid)

    if event_id is not None:
        matches = [(cell, exit_) for cell, exit_ in matches if exit_.event_id == event_id]
        if not matches:
            raise ValueError(
                f"warp_cell: {map_constant} (Uranium map {uid}) has no warp "
                f"exit to {to} with event_id={event_id}"
            )

    if not matches:
        raise ValueError(
            f"warp_cell: {map_constant} (Uranium map {uid}) has no warp "
            f"exit whose destination is {to} (Uranium map {dest_uid})"
        )
    if len(matches) > 1:
        listing = ", ".join(f"cell={cell} event_id={exit_.event_id}" for cell, exit_ in matches)
        raise ValueError(
            f"warp_cell: {map_constant} has {len(matches)} distinct warp "
            f"exits to {to}: {listing} -- disambiguate with event_id="
        )
    return matches[0][0]


def arrival_cell(map_constant: str, *, from_map: str, event_id: int | None = None) -> Cell:
    """Where the player lands arriving in `map_constant` from `from_map`.

    This is the destination side of a warp: build `from_map`'s graph, find
    its warp exits whose destination is `map_constant`'s Uranium id, and
    return `(dest_x, dest_y)`. Same zero/one/many fail-loud discipline as
    `warp_cell` -- ambiguity (two events on `from_map` both leading into
    `map_constant`, e.g. two doors into the same room) must be broken by the
    caller passing `event_id=`, never guessed.
    """
    from_uid, from_graph = _graph_for(from_map, resolver="arrival_cell")
    dest_uid = _uranium_id(map_constant, resolver="arrival_cell")
    matches = _matching_warp_exits(from_graph, dest_uid)

    if event_id is not None:
        matches = [(cell, exit_) for cell, exit_ in matches if exit_.event_id == event_id]
        if not matches:
            raise ValueError(
                f"arrival_cell: {from_map} (Uranium map {from_uid}) has no "
                f"warp exit to {map_constant} with event_id={event_id}"
            )

    if not matches:
        raise ValueError(
            f"arrival_cell: {from_map} (Uranium map {from_uid}) has no warp "
            f"exit whose destination is {map_constant} (Uranium map {dest_uid})"
        )
    # Several exits that all land on the same cell are not ambiguous about
    # the answer -- e.g. Map049 EV002's p1 and p3 are two transfer pages of
    # one door, both landing on Moki (28,31), and `event_id=` cannot tell
    # pages of one event apart anyway.
    landings = {(exit_.dest_x, exit_.dest_y) for _cell, exit_ in matches}
    if len(matches) > 1 and len(landings) > 1:
        listing = ", ".join(f"cell={cell} event_id={exit_.event_id}" for cell, exit_ in matches)
        raise ValueError(
            f"arrival_cell: {from_map} has {len(matches)} distinct warp "
            f"exits to {map_constant}: {listing} -- disambiguate with event_id="
        )
    _cell, exit_ = matches[0]
    return (exit_.dest_x, exit_.dest_y)


def entry_cell(chapter_id: str, map_constant: str) -> Cell:
    """The derived cell at which chapter `chapter_id`'s walk first enters
    `map_constant`.

    Reads `chapter_manifest.generator._start_cells` -- the derivation that
    replaced the old hand-kept per-chapter start-cell table (A5,
    C6_GENERATOR_PLAN.md) -- rather than holding a second copy here
    (CLAUDE.md §4.3). `_start_cells` derives the engine spawn plus every
    landing a reachable warp/seam/connection puts the player on, flooded
    over the chapter's own chain, via `beat_gen.reach.chapter_entry_cells`.

    The derivation's value is a `frozenset[Cell]`, because some maps hold
    several disconnected walkable components each entered by its own door
    (Kevlar's building strip, map 73). Beat authoring, unlike the
    reachability flood that unions all of them, needs exactly ONE cell to
    stand a beat on, so this resolver still returns a single `Cell` -- but on
    a genuinely multi-start map there is no non-arbitrary way to pick one,
    and guessing would be exactly the "confident wrong answer" A5's design
    warns against. It therefore fails loud on more than one derived cell,
    naming every candidate, rather than silently returning one of them.

    Fails loud on a miss: a `(chapter_id, map)` pair with no derivable entry
    cell means nothing in the chapter's chain (engine spawn over itself and
    its predecessors) reaches this map -- this resolver cannot derive or
    approximate one on its own. If the map genuinely is entered, the gap is
    upstream (the chain, connections, or seam warps this derivation reads),
    not something to patch here.
    """
    from ..chapter_manifest.generator import _start_cells

    uid = _uranium_id(map_constant, resolver="entry_cell")
    root = Path(os.environ.get("RPG2GBA_OUTPUT", "output"))
    build_dir = root / "uranium-build"
    cells = _start_cells(chapter_id, uid, build_dir)
    if cells is None:
        raise ValueError(
            f"entry_cell: no derivable entry cell for chapter {chapter_id!r} "
            f"on {map_constant} (Uranium map {uid}) -- no reachable "
            "warp/seam/connection lands on this map from the engine spawn "
            f"over {chapter_id}'s chain (chapter_manifest.generator._start_cells)"
        )
    if len(cells) > 1:
        listing = ", ".join(str(c) for c in sorted(cells))
        raise ValueError(
            f"entry_cell: chapter {chapter_id!r} on {map_constant} (Uranium "
            f"map {uid}) has {len(cells)} derived entry cells ({listing}) "
            "-- this map holds more than one disconnected walkable component "
            "(e.g. several shops entered by separate doors from one map "
            "record), so there is no single non-arbitrary entry cell. "
            "entry_cell() cannot guess which door a beat means -- disambiguate "
            "by authoring the beat with the specific cell it actually enters "
            "on, read directly from generator._start_cells, instead of "
            "calling entry_cell() for this map"
        )
    (cell,) = cells
    return cell


def stair_approach(map_constant: str, *, stair_event: int, side: str) -> Cell:
    """The cell a player stands on to use the sideways staircase event
    `stair_event`, entering from `side` ("east" or "west").

    A sideways staircase is used by pressing a HORIZONTAL direction into it;
    the engine redirects the step diagonally across
    (`MB_SIDEWAYS_STAIRS_*`, modelled as `traversal.graph`'s `stair_diagonal`
    edge). So the routing point is never the stair cell itself -- no edge in
    the graph targets one -- it is the flat cell you press from.

    **`side` is required, deliberately.** Which end a beat enters from is an
    authoring claim, not something geometry can decide: CH02's B2 and B3 walk
    each of Route 01's two staircases in BOTH directions, and that is the
    whole point of those beats. A resolver that picked a side for the author
    could not express them. This mirrors `approach_to`'s `prefer=`: naming a
    side means the side is required, and an unwalkable one fails loud rather
    than silently substituting the other.

    **Why walkability is the test, and not `stair_diagonal` ownership.**
    `routing.locations._stair_approach` asks a different question -- "which
    cell does the stair edge depart FROM" -- and answers it by looking for a
    neighbour that owns a `stair_diagonal` edge. That rule holds in the
    middle of a staircase run and breaks at its ends: the flat cell you walk
    in from does not own the edge, while an unwalkable cell partway along a
    diagonal run does. Measured on Map033, ownership reproduces 4 of the 6
    independently ROM-verified stair approaches in the corpus and returns an
    unstandable cell for the other 2; plain walkability reproduces **all 6**
    (CH02's four `STAIR*_APPROACH` constants, verified against a booted ROM
    by CH02's own §9 gate, plus CH05's two `raw_cell` escapes). See
    `tests/test_cells_stair_approach.py`, which pins exactly those six.

    **Identified by event id, not coordinates**, matching `event_cell` and
    `approach_to`. A stair IS an event (`tileset_converter.stairs`
    detects them from their move-route pages), so naming it by id keeps the
    call free of the bare coordinate tuples the ban exists to remove -- a
    `stair=(20, 9)` argument would itself be an unchecked literal, exactly
    what a resolver is supposed to replace.

    Fails loud when the named side is out of bounds or not walkable, and
    when `stair_event` is not a detected diagonal-stair event on that map --
    an approach to something that is not a staircase is a stale beat, not an
    answer to round off.
    """
    if side not in ("east", "west"):
        raise ValueError(
            f"stair_approach: side={side!r} must be 'east' or 'west' -- a "
            "sideways staircase is entered by a horizontal press, so north/"
            "south are not approaches to it"
        )
    uid, graph = _graph_for(map_constant, resolver="stair_approach")

    from ..tileset_converter.stairs import detect_stair_cells

    stairs = {c.event_id: (c.x, c.y) for c in detect_stair_cells(load_map_json(uid))}
    if stair_event not in stairs:
        raise ValueError(
            f"stair_approach: {map_constant} event {stair_event} is not a "
            f"diagonal-stair event -- detected stair events on this map are "
            f"{sorted(stairs) or 'none'}. Either the beat is stale or this is "
            "not a sideways staircase."
        )

    sx, sy = stairs[stair_event]
    cell = (sx - 1, sy) if side == "west" else (sx + 1, sy)
    if not graph.in_bounds(cell):
        raise ValueError(
            f"stair_approach: {map_constant} stair event {stair_event} "
            f"(cell {(sx, sy)}) has no {side} neighbour -- {cell} is out of "
            "bounds"
        )
    if not graph.is_walkable(cell):
        other = (sx + 1, sy) if side == "west" else (sx - 1, sy)
        hint = (
            f" (the {'east' if side == 'west' else 'west'} side, {other}, is "
            "walkable -- if the beat really enters from there, say so)"
            if graph.in_bounds(other) and graph.is_walkable(other)
            else " (neither side is walkable; this cell is probably partway "
            "along a diagonal run rather than at one of its ends)"
        )
        raise ValueError(
            f"stair_approach: {map_constant} stair event {stair_event} "
            f"(cell {(sx, sy)}) cannot be entered from the {side}: {cell} is "
            f"not walkable{hint}"
        )
    return cell


def grass_cell(map_constant: str, x: int, y: int) -> Cell:
    """Confirms `(x, y)` on `map_constant` is a tall-grass cell and returns it.

    **This resolver validates; it does not choose.** A chapter author who
    reaches for a grass cell already knows which one -- both of the pairs
    this replaces (`ch02.py` Route 01, `ch04.py` Route 2) were established
    by reading the metatile behavior byte directly out of the decoded
    tileset data and, for Route 01, cross-checked against a booted ROM
    passing that chapter's §9 gate. A resolver that instead *picked* "the
    best grass cell" on a map could silently pick a different pair from the
    one a passed gate already verified -- overwriting a verified fact with a
    plausible-looking guess is worse than not deriving one at all. So the
    caller names the cell (two plain ints, per the ban's own carve-out for
    `raw_cell` -- a `grass_cell(mc, (x, y))` signature would itself be the
    two-int tuple literal this whole module exists to remove) and this
    resolver's entire job is to assert, against this build's own decoded
    tileset arrays, that the named cell genuinely carries the MB_TALL_GRASS
    behavior -- turning an unchecked literal into a checked one, exactly
    `approach_to`'s `prefer=` contract applied to a different fact.

    Derivation reuses the Phase 5 terrain-tag rule as data, not a rebuilt
    decoder: `column_key` (the RMXP multi-layer stack) feeds
    `TerrainTagTable.effective_tag` (topmost-nonzero-tag wins) against the
    map's own tileset `terrain_tags` array, and the resulting tag is looked
    up in `reference/terrain_tag_map.json` -- the same one source of truth
    `terrain_tags.py`'s real Phase 5 emission reads (CLAUDE.md §4.3), just
    read for its tag->behavior *name* rather than a fork-resolved enum
    value, since this library (like `traversal.ledges`, which the same
    `_EFFECTIVE_TAG_ONLY` placeholder trick is borrowed from) has no need to
    touch `$RPG2GBA_POKEEMERALD` at all to answer "is this MB_TALL_GRASS".

    One documented gap, inherited from `traversal.ledges`'s use of the same
    placeholder: `effective_tag` is called WITHOUT an `is_opaque` callback
    (this library has no graphics/raster data to build one from), so the
    "solid tag-0 tile stops a covering water tag from leaking upward" rule
    (`TerrainTagTable.effective_tag`'s own docstring, the fix for boot gate
    2026-07-06's reflective-grass bug) does not apply here. In practice this
    can only produce a false "not grass" or a wrong named tag on a column
    that stacks a non-opaque covering tile over grass with a decorative tag
    of its own -- it cannot manufacture a false "yes, this is grass" out of
    nothing, so it does not undermine the fail-loud direction this resolver
    exists for.

    Fails loud two ways, because they need different fixes: `(x, y)` out of
    the map's bounds is a typo in the coordinates themselves, while an
    in-bounds cell whose effective tag resolves to some other behavior (the
    error names it) means the citation that produced the coordinate was
    wrong, or the map's tileset/layout changed under it.
    """
    uid, graph = _graph_for(map_constant, resolver="grass_cell")
    cell = (x, y)
    if not graph.in_bounds(cell):
        raise ValueError(
            f"grass_cell: {map_constant} (Uranium map {uid}) cell {cell} is "
            f"out of bounds ({graph.width}x{graph.height})"
        )

    map_json = load_map_json(uid)
    tileset_id = map_json["tileset_id"]
    grid = build_tile_grid(map_json)
    arrays = load_tileset_arrays(tileset_id)
    key = column_key(grid, x, y)
    tag = _EFFECTIVE_TAG_ONLY.effective_tag(arrays.terrain_tags, key)

    names = _tag_behavior_names()
    behavior = names.get(tag, f"<tag {tag} not in terrain_tag_map.json>")
    if behavior != "MB_TALL_GRASS":
        raise ValueError(
            f"grass_cell: {map_constant} (Uranium map {uid}) cell {cell} is "
            f"not tall grass -- its effective terrain tag is {tag} "
            f"({behavior}), not MB_TALL_GRASS"
        )
    return cell


def cell_for_local_id(map_constant: str, local_id_value: int) -> Cell:
    """The cell of the object event whose COMPILED local id is
    `local_id_value` -- the inverse of `local_id()` above.

    `local_id()` answers "what local id does RMXP event N get"; some
    beats (CH03's `BOULDERS`, three rock-pushing puzzle objects on map 19)
    are naturally keyed the other way around -- the beat already knows
    which local id `emu.object_event()` needs to address, and wants the
    cell that object currently occupies, not a coordinate typed by hand
    next to a comment citing the id. `event_cell()` cannot serve this
    either: it is keyed on the RMXP event id, which is exactly the
    identifier this call does NOT have.

    Reuses the same staged local-id table `local_id()` reads
    (`output/uranium-build/staging/local_ids/Map###.json`, CLAUDE.md §4.3 --
    one table, read two directions, never a second copy or a second parse of
    the map JSON to reconstruct it) and searches it for the RMXP event id(s)
    mapped to `local_id_value`, then resolves that event's cell the same way
    `event_cell` does.

    Fails loud two ways: a map with no staged table (not yet through
    staging, same message as `local_id()`'s equivalent case) and a
    `local_id_value` absent from the table, naming every local id the table
    DOES define so a typo'd id is obvious. Also fails loud -- a case
    `local_id()` cannot hit, since it looks up in the other direction -- if
    `local_id_value` is somehow assigned to more than one RMXP event; the
    remap that produces this table is supposed to mint one local id per
    emitted object event, so two events sharing one is a real corruption in
    the staged table, not something to resolve by picking either.
    """
    uid, _graph = _graph_for(map_constant, resolver="cell_for_local_id")
    path = _local_id_table_path(uid)
    if not path.exists():
        raise ValueError(
            f"cell_for_local_id: {map_constant} (Uranium map {uid}) has no "
            f"local-id table at {path} -- that file is written by "
            "scripts/stage_slice_scripts.py, so this map has not been "
            "staged; run the staging step before authoring against it"
        )
    table = json.loads(path.read_text(encoding="utf-8"))
    matches = [int(event_id) for event_id, lid in table.items() if int(lid) == local_id_value]
    if not matches:
        known = sorted({int(lid) for lid in table.values()})
        raise ValueError(
            f"cell_for_local_id: {map_constant} (Uranium map {uid}) has no "
            f"object event with local id {local_id_value} -- local ids on "
            f"this map are {known}"
        )
    if len(matches) > 1:
        raise ValueError(
            f"cell_for_local_id: {map_constant} (Uranium map {uid}) local id "
            f"{local_id_value} is assigned to more than one RMXP event "
            f"({sorted(matches)}) -- the staged local-id table is supposed "
            "to be one-to-one; this is corruption in that table, not "
            "something to resolve by guessing one"
        )
    event = _event_lookup(uid, matches[0], map_constant=map_constant, resolver="cell_for_local_id")
    return (event["x"], event["y"])


def _connection_row_between(uid_a: int, uid_b: int) -> ConnectionRow | None:
    """The real `connections.json` row joining Uranium maps `uid_a`/`uid_b`,
    if one exists, else None. Used only by `seam_cells`'s fallback path --
    see that function's docstring for why a hit here is itself an error, not
    an alternate source of cells."""
    root = Path(os.environ.get("RPG2GBA_OUTPUT", "output"))
    path = root / "uranium-build" / "connections.json"
    if not path.is_file():
        return None
    rows = load_connections(path)
    wanted = frozenset((uid_a, uid_b))
    for row in rows:
        if row.pair_key == wanted:
            return row
    return None


def seam_cells(map_constant: str, *, to: str) -> tuple[Cell, ...]:
    """The seam cell(s) on `map_constant`'s side of its arrow-warp seam
    crossing into `to`.

    **Why this exists alongside `warp_cell`/`arrival_cell`, not folded into
    them.** Those two resolve command-201 warp events -- an authored map
    event with an id, a destination, and (for `arrival_cell`) a fixed
    landing cell. A seam (`reference/seam_warps.json`) is a DIFFERENT thing
    structurally: two synthetic `MB_*_ARROW_WARP` metatiles substituted for
    a whole-border pokeemerald map CONNECTION, used only when the two maps'
    combined tileset can't fit pokeemerald's 1024-8x8-tile cap
    (`seam_warps.json`'s own `_comment`). There is no event id to key on and
    no single "the" warp -- the schema pairs `cells_a[i]` with `cells_b[i]`
    reciprocally, and a real seam (Kevlar Town <-> Route 2, today's only
    entry) is TWO cells wide, so this needed its own resolver rather than a
    third keyword bolted onto `warp_cell`.

    **Why it returns a tuple, always, never a bare `Cell`.** The Kevlar seam
    is two cells side by side and picking one for the caller would repeat
    exactly the mistake `grass_cell`'s docstring argues against: a resolver
    that silently chose between (31,0) and (32,0) could choose differently
    from the cell a chapter's own boot-gate walk already verified (only
    x=32's landing is open; x=31's landing cell is blocked -- see
    `ch04.py`'s module docstring). Returning the whole `cells_a`/`cells_b`
    list in the JSON's own documented pairing order lets the caller index
    into it (`seam_cells(...)[1]`) -- an int index is not a coordinate
    literal, so it is not something `test_chapter_coordinate_literals.py`'s
    walker flags, and the choice of WHICH cell is still the author's claim,
    not this resolver's guess. A seam with only one cell still returns a
    1-tuple, so callers never need to branch on arity.

    **Lookup order and the three fail-loud cases.** Seams are looked up by
    which ones touch `to` first, not by the (map_constant, to) pair
    directly, so a bad `map_constant` argument produces a DIFFERENT error
    than an entirely unknown `to`:

    1. No `seam_warps.json` entry touches `to` at all. Falls back to
       `output/uranium-build/connections.json` (`tileset_converter.
       connections.load_connections`, the real per-pair adjacency data --
       see that module for the row schema) for the SAME map pair. A hit
       there means the two maps share an ordinary whole-border pokeemerald
       CONNECTION, not a substituted arrow-warp seam -- structurally the
       thing `warp_cell`/`arrival_cell` and this resolver both do not
       cover, since a connection has no fixed handful of cells to name (it
       spans the entire shared edge). That is reported as its own error,
       distinct from "no seam at all", because the fix differs: there is
       real adjacency data, this resolver just cannot express a whole-edge
       crossing as a `Cell` tuple. Neither seam nor connection data at all
       is the "no seam at all" case.
    2. `to` has a seam_warps.json entry, but `map_constant` is not its other
       side -- naming whichever map(s) `to` DOES seam with, so a typo'd
       `map_constant` (or a chapter author's wrong assumption about which
       two maps are seamed) is obvious immediately rather than surfacing as
       a wrong cell later.
    3. More than one seam entry both touches `to` AND has `map_constant` as
       its other side (impossible in today's single-entry corpus, but not
       structurally impossible as the table grows) -- ambiguous, listing
       every candidate seam id.
    """
    uid = _uranium_id(map_constant, resolver="seam_cells")
    neighbor_uid = _uranium_id(to, resolver="seam_cells")

    touching_neighbor = [
        s for s in _seam_warps() if neighbor_uid in (s["map_a"], s["map_b"])
    ]
    if not touching_neighbor:
        row = _connection_row_between(uid, neighbor_uid)
        if row is not None:
            raise ValueError(
                f"seam_cells: {map_constant} and {to} share a real "
                f"connections.json border ({row}), not a seam_warps.json "
                "arrow-warp substitution -- that is a whole-edge crossing "
                "with no fixed cell(s) to name, structurally outside what "
                "warp_cell/arrival_cell/seam_cells can express"
            )
        raise ValueError(
            f"seam_cells: no seam_warps.json entry touches {to} (Uranium "
            f"map {neighbor_uid}) at all -- known seam ids are "
            f"{sorted(s['id'] for s in _seam_warps())}"
        )

    party = [
        s for s in touching_neighbor if uid in (s["map_a"], s["map_b"])
    ]
    if not party:
        partners = sorted(
            {s["map_a"] if s["map_a"] != neighbor_uid else s["map_b"] for s in touching_neighbor}
        )
        raise ValueError(
            f"seam_cells: {to} (Uranium map {neighbor_uid}) has a seam, but "
            f"not with {map_constant} (Uranium map {uid}) -- its seam "
            f"partner map id(s) are {partners}"
        )
    if len(party) > 1:
        ids = sorted(s["id"] for s in party)
        raise ValueError(
            f"seam_cells: {map_constant} and {to} are joined by "
            f"{len(party)} distinct seam_warps.json entries ({ids}) -- "
            "ambiguous"
        )

    seam = party[0]
    cells = seam["cells_a"] if seam["map_a"] == uid else seam["cells_b"]
    return tuple((c[0], c[1]) for c in cells)


def raw_cell(x: int, y: int, *, why: str) -> Cell:
    """The escape hatch: returns `(x, y)` unchanged, no derivation at all.

    Every call is counted debt (`tests/test_chapter_coordinate_literals.py`
    tracks it against a file's ratchet budget, and a new chapter is born
    with a budget of zero) -- this is not a quiet way around the ban, it is
    the ban's one deliberately visible escape, for geometry the decoded
    corpus genuinely cannot express (an off-map camera anchor, a point
    measured by hand against a screenshot).

    `why` is required and must be non-empty (raises `ValueError` otherwise).
    It should say two things: what could not be derived through
    `event_cell`/`approach_to`/`warp_cell`/`arrival_cell`/`stair_approach`,
    and what verified
    the number instead (a screenshot, a hand count against the decoded JSON,
    a doc's own measured value) -- a `why` that just restates the numbers
    back is not a reason.
    """
    if not why or not why.strip():
        raise ValueError(
            "raw_cell: why= is required and must be a non-empty string -- "
            "every raw_cell call is counted debt (CLAUDE.md §4.5); state "
            "what could not be derived and what verified this number instead"
        )
    return (x, y)
