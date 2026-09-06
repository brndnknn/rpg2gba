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

from ..traversal.collision import load_map_json
from ..traversal.direction import Direction
from ..traversal.graph import MapGraph, build_map_graph
from ..traversal.reachability import adjacent_approach_cells
from . import chapter as _chapter

Cell = tuple[int, int]

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

    Candidates are `adjacent_approach_cells` around the event's own cell,
    filtered to `graph.is_walkable`, kept in the deterministic N/S/E/W order.
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

    candidates = [c for c in adjacent_approach_cells(graph, cell) if graph.is_walkable(c)]

    if prefer is not None:
        direction = _PREFER_TO_DIRECTION.get(prefer)
        if direction is None:
            raise ValueError(
                f"approach_to: {map_constant} event {event_id}: prefer="
                f"{prefer!r} is not one of {sorted(_PREFER_TO_DIRECTION)}"
            )
        dx, dy = direction.delta
        wanted = (cell[0] + dx, cell[1] + dy)
        if wanted not in candidates:
            raise ValueError(
                f"approach_to: {map_constant} event {event_id} (cell {cell}) "
                f"cannot be approached from the {prefer} side -- that cell "
                f"({wanted}) is out of bounds or not walkable; walkable "
                f"candidates are {candidates or 'none'}"
            )
        return wanted

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
    if len(matches) > 1:
        listing = ", ".join(f"cell={cell} event_id={exit_.event_id}" for cell, exit_ in matches)
        raise ValueError(
            f"arrival_cell: {from_map} has {len(matches)} distinct warp "
            f"exits to {map_constant}: {listing} -- disambiguate with event_id="
        )
    _cell, exit_ = matches[0]
    return (exit_.dest_x, exit_.dest_y)


def entry_cell(chapter_id: str, map_constant: str) -> Cell:
    """The verified cell at which chapter `chapter_id`'s walk first enters
    `map_constant`.

    Reads `chapter_manifest.generator._CHAPTER_MAP_START_CELLS` -- the one
    table of hand-verified (chapter, map) start cells, keyed by
    `(chapter_id, uranium_map_id)` -- rather than holding a second copy here
    (CLAUDE.md §4.3). See that table's own comment block in `generator.py`
    for the citation discipline an entry must satisfy before it's added
    (cross-checked against an independent validation run, never the table's
    own invention, never guessed from map geometry).

    Fails loud on a miss: a `(chapter_id, map)` pair with no registered start
    cell is a real gap in that chapter's build (a verified entry point has
    not been recorded yet), not something this resolver can derive or
    approximate on its own -- the fix is to register a citation-backed entry
    in `_CHAPTER_MAP_START_CELLS` during that chapter's own build, per its
    comment block, not to guess one here.
    """
    from ..chapter_manifest.generator import _CHAPTER_MAP_START_CELLS

    uid = _uranium_id(map_constant, resolver="entry_cell")
    cell = _CHAPTER_MAP_START_CELLS.get((chapter_id, uid))
    if cell is None:
        raise ValueError(
            f"entry_cell: no verified start cell registered for chapter "
            f"{chapter_id!r} on {map_constant} (Uranium map {uid}) -- add a "
            f"citation-backed entry to _CHAPTER_MAP_START_CELLS in "
            "src/rpg2gba/chapter_manifest/generator.py as part of that "
            "chapter's own build; it must be verified (an emulator-observed "
            "position, a warp-exit constant), not guessed from geometry"
        )
    return cell


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
    `event_cell`/`approach_to`/`warp_cell`/`arrival_cell`, and what verified
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
