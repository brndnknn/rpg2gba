"""Corpus-wide invariants for post-warp facing (C5b model).

Since C5b (2026-09-18, WARP_RETAIN_FACING_PROPOSAL.md §0) the arrival facing
rides on the DEPARTURE warp: `metadata_wiring.warp_facing_for` writes the
RMXP transfer direction onto the source warp_event's `"facing"`, and the
engine (RPG2GBA_WARP_RETAIN_FACING) either applies it or -- for RMXP
direction 0, "retain current facing" -- keeps the facing the player walked
in with. So an arrival's facing is no longer a property of the arrival tile:
for a retain warp it is whichever way the player was moving when they
stepped onto the source cell, i.e. one facing per way the source cell can be
ENTERED (`_approach_facings`).

The unit tests in `test_tileset_converter.py` pin `warp_facing_for` on
synthetic fixtures. This file pins the *result* over the real built slice,
as the properties that matter to a player:

    when you land, you are not facing (or auto-stepped onto) the warp you
    just came out of, and a door-tile arrival's exit step lands on ground.

These replace the pre-C5b tier-3 derivation tests (arrival-keyed coordinate
table, `compute_arrival_facings`) one for one; see each test's docstring.

Skips when the slice output isn't staged, matching `test_assembly.py`.
"""
from __future__ import annotations

import json
import os
from collections import deque
from pathlib import Path

import pytest

from rpg2gba.tileset_converter import metadata_wiring as mw
from rpg2gba.tileset_converter.layout import TileGrid, column_blocked, column_key
from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS
from rpg2gba.tileset_converter.seam_warps import (
    behavior_cells_for,
    load_seam_warps,
    seams_for_slice,
)
from rpg2gba.traversal.graph import build_map_graph

_OUT = Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build"
_MAPS_DIR = _OUT / "maps"
_TILESETS = _OUT / "tilesets.json"

# (dx, dy) one step in each engine DIR_* direction. y grows south.
_DIR_VECTOR: dict[str, tuple[int, int]] = {
    "DIR_NORTH": (0, -1),
    "DIR_SOUTH": (0, 1),
    "DIR_WEST": (-1, 0),
    "DIR_EAST": (1, 0),
}

_HAVE_OUTPUT = (
    _MAPS_DIR.is_dir() and _TILESETS.is_file()
    and (_OUT / mw.WARP_OVERRIDES_FILENAME).is_file()
    and all((_MAPS_DIR / f"Map{uid:03d}.json").is_file() for uid in SLICE_MAP_IDS)
)

pytestmark = pytest.mark.skipif(
    not _HAVE_OUTPUT, reason="staged slice output not present"
)

# (src_uid, src_x, src_y, dest_uid, dest_x, dest_y, facing)
Arrival = tuple[int, int, int, int, int, int, str]


@pytest.fixture(scope="module")
def slice_data() -> tuple[dict[int, dict], dict[int, list[mw.WarpSpec]], dict]:
    """The real slice maps, their warp specs, and the tileset oracle."""
    slice_set = set(SLICE_MAP_IDS)
    maps = {
        uid: json.loads(
            (_MAPS_DIR / f"Map{uid:03d}.json").read_text(encoding="utf-8")
        )
        for uid in SLICE_MAP_IDS
    }
    warp_lists = {
        uid: [spec for _event, spec in mw.classify_map_events(maps[uid], slice_set)[1]]
        for uid in SLICE_MAP_IDS
    }
    tilesets = json.loads(_TILESETS.read_text(encoding="utf-8"))
    return maps, warp_lists, tilesets


@pytest.fixture(scope="module")
def door_cells() -> dict[int, set[tuple[int, int]]]:
    """The cells the emitted layout stamps MB_NON_ANIMATED_DOOR on -- the
    build's own `warp_overrides.gen.json`, the assembler's exact input."""
    return mw.load_warp_overrides(_OUT)


@pytest.fixture(scope="module")
def directional_cells(slice_data) -> dict[int, dict[tuple[int, int], str]]:
    """Arrow-warp and diagonal-stair cells per map: the same
    `behavior_overrides` union `scripts/assemble_pathfinder.py` feeds
    `convert_layout`. The engine faces an arrival on these by tile, not by
    the warp, so no arrival may land on one (R5)."""
    maps, _warp_lists, _tilesets = slice_data
    seam_cells = behavior_cells_for(seams_for_slice(load_seam_warps(), set(SLICE_MAP_IDS)))
    return {
        uid: {**mw.collect_stair_behavior_cells(maps[uid]), **seam_cells.get(uid, {})}
        for uid in SLICE_MAP_IDS
    }


def _blocked(map_json: dict, tilesets: dict, x: int, y: int) -> bool:
    """RMXP multi-layer passability for one cell of a real slice map, through
    the single implementation of the rule (`layout.column_blocked`)."""
    tiles = map_json["tiles"]
    grid = TileGrid(tiles["xsize"], tiles["ysize"], tiles["zsize"], tiles["data"])
    ts = tilesets[str(map_json["tileset_id"])]
    return column_blocked(
        column_key(grid, x, y),
        passages=ts["passages"],
        priorities=ts.get("priorities"),
        terrain_tags=ts.get("terrain_tags"),
    )


def _in_bounds(map_json: dict, x: int, y: int) -> bool:
    return 0 <= x < map_json["width"] and 0 <= y < map_json["height"]


def _walkable(map_json: dict, tilesets: dict, x: int, y: int) -> bool:
    return _in_bounds(map_json, x, y) and not _blocked(map_json, tilesets, x, y)


_EDGE_CELLS = {
    "N": lambda w, h: [(x, 0) for x in range(w)],
    "S": lambda w, h: [(x, h - 1) for x in range(w)],
    "W": lambda w, h: [(0, y) for y in range(h)],
    "E": lambda w, h: [(w - 1, y) for y in range(h)],
}


@pytest.fixture(scope="module")
def reachable(slice_data, door_cells) -> dict[int, set[tuple[int, int]]]:
    """Per map, every cell the player can actually stand on: a
    `traversal.graph.MapGraph` flood (directional passability, ledges,
    stairs) from every way INTO the map -- warp arrivals, seam arrow-warp
    cells, and the edges of connections between two built maps. A cell that
    is merely open but reachable only THROUGH a warp cell (the one-tile pocket
    behind a cave mouth, the strip behind the Route 1 warp column) is
    excluded, which is what makes "the ways a warp can be entered" a real
    claim rather than a passability guess.

    A door-tile arrival starts the player on its LANDING cell (the exit step,
    `_landing`), not on the door or its other neighbours. That landing depends
    on the arrival facing, which for a retain warp depends on how its source
    was approached on the other map -- so this is a fixed point: flood,
    derive retain-warp approaches from the flood, seed their landings, repeat
    until nothing new is reachable."""
    maps, warp_lists, _tilesets = slice_data
    built = set(SLICE_MAP_IDS)
    graphs = {uid: build_map_graph(uid, _MAPS_DIR, _TILESETS) for uid in built}

    def _starts(uid: int, cell: tuple[int, int]) -> set[tuple[int, int]]:
        # A cell that is itself unwalkable raw collision is left through its
        # walkable neighbours; used only for non-door entries.
        x, y = cell
        return {c for c in [(x, y), (x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
                if graphs[uid].is_walkable(c)}

    base: dict[int, set[tuple[int, int]]] = {uid: set() for uid in built}
    seam_cells = behavior_cells_for(seams_for_slice(load_seam_warps(), built))
    for uid, cells in seam_cells.items():
        for cell in cells:
            base[uid] |= _starts(uid, cell)
    # Scripted transfers: an event that is NOT collapsed into a warp_event (a
    # gated door, a story transfer) still moves the player via its page's
    # `warp()`. CH06's gym (Map042) and Maria's house (Map047) are entered
    # ONLY this way (Map040 EV014 / EV017), so without these seeds neither
    # building is reachable and its exit warp looks unenterable.
    for uid in built:
        objects, _warps, _skips = mw.classify_map_events(maps[uid], built)
        for event in objects:
            for dest_uid, x, y, _dir in mw._event_transfers(event):
                if dest_uid in built and _in_bounds(maps[dest_uid], x, y):
                    base[dest_uid] |= _starts(dest_uid, (x, y))
    connections = json.loads((_OUT / "connections.json").read_text(encoding="utf-8"))
    for a, a_dir, _ao, b, b_dir, _bo in connections:
        if a in built and b in built:
            for uid, side in ((a, a_dir), (b, b_dir)):
                w, h = maps[uid]["width"], maps[uid]["height"]
                base[uid] |= {c for c in _EDGE_CELLS[side](w, h) if graphs[uid].is_walkable(c)}

    # Stepping onto a warp cell (or a seam arrow cell) ends the walk, so the
    # flood never passes THROUGH one to the far side.
    barriers = {
        uid: {(s.src_x, s.src_y) for s in warp_lists[uid]} | set(seam_cells.get(uid, {}))
        for uid in built
    }
    reach: dict[int, set[tuple[int, int]]] = {uid: set() for uid in built}
    while True:
        seeds = {uid: set(cells) for uid, cells in base.items()}
        for src_uid, specs in warp_lists.items():
            for spec in specs:
                dest_uid, cell = spec.dest_uid, (spec.dest_x, spec.dest_y)
                if dest_uid not in built or not _in_bounds(maps[dest_uid], *cell):
                    continue
                if cell not in door_cells.get(dest_uid, set()):
                    seeds[dest_uid] |= _starts(dest_uid, cell)
                    continue
                facing = mw.warp_facing_for(spec.dest_dir)
                facings = (_approach_facings(src_uid, spec, warp_lists, reach)
                           if facing == mw.RETAIN_FACING else {facing})
                for f in facings:
                    dx, dy = _DIR_VECTOR[f]
                    landing = (cell[0] + dx, cell[1] + dy)
                    if graphs[dest_uid].is_walkable(landing):
                        seeds[dest_uid].add(landing)
        new = {uid: _flood(graphs[uid], seeds[uid], barriers[uid]) for uid in built}
        if new == reach:
            return reach
        reach = new


def _flood(graph, starts: set[tuple[int, int]],
           barriers: set[tuple[int, int]]) -> set[tuple[int, int]]:
    """BFS over `graph.neighbors` from `starts`, never entering a barrier."""
    seen = {s for s in starts if s not in barriers}
    queue = deque(seen)
    while queue:
        cur = queue.popleft()
        for edge in graph.neighbors(cur):
            if edge.target not in seen and edge.target not in barriers:
                seen.add(edge.target)
                queue.append(edge.target)
    return seen


def _approach_facings(
    src_uid: int, spec: mw.WarpSpec, warp_lists: dict[int, list[mw.WarpSpec]],
    reachable: dict[int, set[tuple[int, int]]],
) -> set[str]:
    """Every facing the player can have on stepping onto `spec`'s source
    cell: one per reachable, non-warp neighbour it can be entered from (the
    player moves from that neighbour INTO the cell, so faces away from it).
    This is what an RMXP direction-0 warp's arrival facing can be."""
    siblings = {(s.src_x, s.src_y) for s in warp_lists[src_uid]}
    facings: set[str] = set()
    for dir_const, (dx, dy) in _DIR_VECTOR.items():
        frm = (spec.src_x - dx, spec.src_y - dy)
        if frm not in siblings and frm in reachable[src_uid]:
            facings.add(dir_const)
    return facings


def _arrivals(slice_data, reachable) -> list[Arrival]:
    """Every (source warp, possible arrival facing) pair landing in bounds on
    a built map: explicit directions once, retain warps once per approach."""
    maps, warp_lists, _tilesets = slice_data
    out: list[Arrival] = []
    for src_uid, specs in warp_lists.items():
        for spec in specs:
            dest = maps.get(spec.dest_uid)
            if dest is None or not _in_bounds(dest, spec.dest_x, spec.dest_y):
                continue
            facing = mw.departure_facing(spec, warp_lists)
            options = (
                _approach_facings(src_uid, spec, warp_lists, reachable)
                if facing == mw.RETAIN_FACING else {facing}
            )
            out.extend(
                (src_uid, spec.src_x, spec.src_y, spec.dest_uid, spec.dest_x, spec.dest_y, f)
                for f in options
            )
    return out


def test_every_warp_has_a_resolvable_arrival_facing(slice_data, reachable) -> None:
    """Replaces the pre-C5b "every arrival has an explicit facing row" test.

    Every kept departure warp's direction must resolve (`warp_facing_for`
    raises on anything but 0/2/4/6/8), and a retain warp must be enterable
    from at least one side -- otherwise its arrival facing is undefined, the
    case the old tier-3 derivation failed loud on as "enclosed"."""
    _maps, warp_lists, _tilesets = slice_data
    unenterable = []
    for src_uid, specs in warp_lists.items():
        for spec in specs:
            if mw.warp_facing_for(spec.dest_dir) != mw.RETAIN_FACING:
                continue
            if not _approach_facings(src_uid, spec, warp_lists, reachable):
                unenterable.append((src_uid, spec.src_x, spec.src_y))
    assert unenterable == [], (
        f"retain-facing warps with no walkable approach (arrival facing undefined): "
        f"{unenterable}"
    )


def _landing(arrival: Arrival, door_cells: dict[int, set[tuple[int, int]]]) -> tuple[int, int]:
    """Where the player ends up: the arrival cell, or one step on in the
    arrival facing when it is a door tile (Task_ExitNonAnimDoor)."""
    _su, _sx, _sy, dest_uid, x, y, facing = arrival
    if (x, y) not in door_cells.get(dest_uid, set()):
        return (x, y)
    dx, dy = _DIR_VECTOR[facing]
    return (x + dx, y + dy)


#: Arrivals that face straight back into a warp IN URANIUM ITSELF, kept
#: faithful by operator ruling rather than corrected:
#:   Map045 EV010 (Metro platform gate, (5,12)) -> station (14,5), RMXP dir 6
#:   (right) -- facing Map044 EV001's gate at (15,5). Same behaviour in
#:   Uranium (apparent authoring slip); ruled 2026-10-07: keep faithful.
_FAITHFUL_FACE_BACK: set[Arrival] = {(45, 5, 12, 44, 14, 5, "DIR_EAST")}


def test_arrival_never_faces_the_warp_it_came_out_of(
    slice_data, door_cells, reachable,
) -> None:
    """The player must not face (from where they end up) a warp cell: the
    first step forward would warp them straight back. Covers every possible
    retain-warp approach, not just one derived facing, which is what the
    pre-C5b "derived arrival never faces a wall" test was guarding against
    (a wrong facing guess)."""
    maps, warp_lists, _tilesets = slice_data
    bad = []
    for arrival in _arrivals(slice_data, reachable):
        if arrival in _FAITHFUL_FACE_BACK:
            continue
        dest_uid, facing = arrival[3], arrival[6]
        lx, ly = _landing(arrival, door_cells)
        dx, dy = _DIR_VECTOR[facing]
        ahead = (lx + dx, ly + dy)
        if ahead in {(s.src_x, s.src_y) for s in warp_lists[dest_uid]}:
            bad.append((arrival, ahead))
    assert bad == [], f"arrivals facing straight back into a warp cell: {bad}"


def test_door_arrival_exit_step_lands_on_walkable_ground(
    slice_data, door_cells, reachable,
) -> None:
    """R5 guard. A door-tile arrival walks the player one step on in their
    arrival facing, so for EVERY facing it can arrive with (every approach of
    a retain warp, or the authored direction) that step must land in bounds,
    on walkable ground, and not on another warp cell -- else the exit step
    bumps a wall or re-warps. Fails loud, listing each bad (warp, facing)."""
    maps, warp_lists, tilesets = slice_data
    bad = []
    for arrival in _arrivals(slice_data, reachable):
        dest_uid, x, y = arrival[3], arrival[4], arrival[5]
        if (x, y) not in door_cells.get(dest_uid, set()):
            continue
        lx, ly = _landing(arrival, door_cells)
        dest = maps[dest_uid]
        if not _walkable(dest, tilesets, lx, ly):
            bad.append((arrival, (lx, ly), "unwalkable"))
        elif (lx, ly) in {(s.src_x, s.src_y) for s in warp_lists[dest_uid]}:
            bad.append((arrival, (lx, ly), "warp cell"))
    assert bad == [], f"door-tile arrivals whose exit step goes nowhere: {bad}"


def test_no_arrival_lands_on_an_arrow_or_stair_tile(
    slice_data, directional_cells, reachable,
) -> None:
    """R5 guard. The engine faces an arrival on an arrow-warp or diagonal-
    stair tile by the tile (GetAdjustedInitialDirection's arrow/stair
    branches), silently overriding the warp's own facing -- so none may exist."""
    bad = sorted({
        (a[3], a[4], a[5], directional_cells[a[3]][(a[4], a[5])])
        for a in _arrivals(slice_data, reachable)
        if (a[4], a[5]) in directional_cells.get(a[3], {})
    })
    assert bad == [], f"arrivals on direction-owning tiles: {bad}"


def test_uranium_authored_wall_facers_are_pinned(slice_data) -> None:
    """Decided: faithful (WARP_RETAIN_FACING_PROPOSAL.md §0 R4, 2026-09-18).

    Uranium sometimes authors a transfer direction that faces a wall. Maps
    49 and 172 are the stairwell landings in the Moki houses: the player
    comes down from 2F onto (11,3), one tile west of the stairs at (12,3),
    and Uranium's transfer says direction 4 (west) -- into the wall at
    (10,3). The operator ruled to reproduce that faithfully rather than
    "improve" it (CLAUDE.md §10: content-fidelity calls are the user's).

    Pinned as an exact set so a NEW authored wall-facer shows up as a
    failure and gets a deliberate look, instead of hiding in a warning."""
    maps, warp_lists, tilesets = slice_data
    authored_bad: dict[tuple[int, int, int], str] = {}
    for specs in warp_lists.values():
        for spec in specs:
            facing = mw.warp_facing_for(spec.dest_dir)
            dest = maps.get(spec.dest_uid)
            if facing == mw.RETAIN_FACING or dest is None \
                    or not _in_bounds(dest, spec.dest_x, spec.dest_y):
                continue
            dx, dy = _DIR_VECTOR[facing]
            nx, ny = spec.dest_x + dx, spec.dest_y + dy
            key = (spec.dest_uid, spec.dest_x, spec.dest_y)
            if not _in_bounds(dest, nx, ny):
                authored_bad[key] = f"{facing} -> off-map"
            elif _blocked(dest, tilesets, nx, ny):
                authored_bad[key] = f"{facing} -> blocked ({nx},{ny})"
    assert authored_bad == {
        (49, 11, 3): "DIR_WEST -> blocked (10,3)",
        (172, 11, 3): "DIR_WEST -> blocked (10,3)",
    }


def test_former_hand_overrides_now_follow_from_retain(slice_data, reachable) -> None:
    """Replaces `test_load_warp_facing_overrides_shipped_file_loads_clean`.

    `reference/warp_facing_overrides.json` (deleted in C5b) hand-pinned three
    arrivals where the old arrival-keyed derivation was ambiguous. All three
    are RMXP direction 0, and under retain semantics each source can only be
    entered one way -- which is exactly the direction the file pinned. So
    the file's content is now a consequence of the source data, not a
    correction to it."""
    former = {
        (32, 8, 43): "DIR_EAST",    # Route 1 (70,11..13) -> Moki Town west edge
        (36, 17, 39): "DIR_NORTH",  # Route 2 -> cave 1F
        (37, 16, 26): "DIR_NORTH",  # cave 1F stairs -> 2F
    }
    facings: dict[tuple[int, int, int], set[str]] = {}
    for a in _arrivals(slice_data, reachable):
        key = (a[3], a[4], a[5])
        if key in former:
            facings.setdefault(key, set()).add(a[6])
    assert facings == {key: {f} for key, f in former.items()}


def test_kevlar_chapter_three_arrivals_face_up(slice_data, reachable) -> None:
    """Regression pin for the reported CH03 bug (four destinations landed the
    player facing down): these warps are RMXP direction 0 ("retain"), and
    each source can only be entered moving north, so the only possible
    arrival facing is north.

    Route 1 -> Kevlar Town (two-tile-wide edge warp), and the town's Poke
    Mart / Poke Center / flower-shop doors."""
    expected_dests = {
        (31, 15, 42),  # Route 1 -> Kevlar Town, west tile
        (31, 16, 42),  # Route 1 -> Kevlar Town, east tile
        (67, 10, 10),  # town -> Poke Mart
        (68, 8, 18),   # town -> Poke Center
        (73, 44, 12),  # town -> flower shop
    }
    facings: dict[tuple[int, int, int], set[str]] = {}
    for a in _arrivals(slice_data, reachable):
        key = (a[3], a[4], a[5])
        if key in expected_dests:
            facings.setdefault(key, set()).add(a[6])
    assert facings == {key: {"DIR_NORTH"} for key in expected_dests}
