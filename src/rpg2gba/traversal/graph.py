"""The offline traversable graph — single source of truth for "where can the
player walk on map N", derived purely from decoded RMXP data. No ROM, no
emulator (PLAYTEST_AUTHORING_IMPROVEMENT_V2.md Q13, slice 1).

Modelled inputs, and where each one comes from (CLAUDE.md §4.3 — every rule
below is reused from its one source of truth, never reimplemented):

    collision   -- `tileset_converter.layout.column_blocked` via `collision.py`
    staircases  -- `tileset_converter.stairs.stair_cell_sides`
    ledges      -- `ledges.derive_ledge_direction` (reuses
                   `terrain_tags.TerrainTagTable.effective_tag`)
    warps       -- `warps.extract_warp_exits` (command-201 events)
    elevation   -- NOT MODELLED. RMXP/Essentials carries no per-tile
                   elevation/height field anywhere in the decoded map data;
                   pokeemerald's `Metatile.elevation` is a converter-invented
                   constant (always PASSABLE_ELEVATION or BLOCKED_ELEVATION,
                   mirroring collision — see `tile_map.PASSABLE_ELEVATION`),
                   not a real height value carried through from the source.
                   There is nothing in the decoded corpus to derive real
                   elevation from. This is a genuine gap, not an oversight:
                   `MapGraph.elevation_modelled` is always False and
                   `MapGraph.elevation_note` explains it — per CLAUDE.md §4.5
                   (fail loud / record explicitly, never silently default), a
                   cliff-rim edge is planned straight through it, same as
                   today's runtime planner, and callers must not assume
                   otherwise.

CRITICAL MODELLING CORRECTION — sideways staircases are not an 8-neighbour
edge (see PLAYTEST_AUTHORING_IMPROVEMENT_V2.md §5.9, ~line 1720): a stair
cell is an ordinary PASSABLE cell. The player presses EAST or WEST, and the
*engine* (not tile geometry) turns that single press into a one-tile diagonal
displacement — confirmed against
`engine/src/event_object_movement.c:6681` `GetSidewaysStairsCollision` and
`engine/src/field_player_avatar.c:2209-2237`
`GetRightSideStairsDirection`/`GetLeftSideStairsDirection`:

    MB_SIDEWAYS_STAIRS_RIGHT_SIDE (NW/SE axis): press WEST -> land NW of the
        stair cell; press EAST -> land SE of it.
    MB_SIDEWAYS_STAIRS_LEFT_SIDE  (NE/SW axis): press WEST -> land SW; press
        EAST -> land NE.

This module represents that as a *displacement*, not a graph edge between two
adjacent cells: `Edge.kind == "stair_diagonal"` names the press direction
separately from the resulting cell, so a consumer can both plan a path (BFS
over `neighbors()`) and predict exactly where the player ends up after each
step, per Q13.1's "non-trigger divergence" contract — the whole reason this
distinction is load-bearing is that modelling it as a plain 8-neighbour edge
plans a correct-looking path that then mispredicts the post-step cell, which
is precisely the "offline graph is wrong about the engine" divergence class.

SIMPLIFICATION, documented: the real engine additionally special-cases the
*first* step onto a staircase from ordinary ground when that entry step's
direction is the "wrong" one for the stair's side (see
`GetSidewaysStairsCollision`'s `currentBehavior != nextBehavior` checks) --
that asymmetry exists to support pokeemerald's TOP/BOTTOM staircase-end
metatile variants. `tileset_converter.stairs` never emits those variants (it
only classifies plain LEFT_SIDE/RIGHT_SIDE, per its own docstring), so this
graph applies the diagonal displacement uniformly to every EAST/WEST press
touching a stair cell, entry included. If a future converter change starts
emitting TOP/BOTTOM stair metatiles, this simplification would need revisiting.

Ledges are one-way (terrain tag 1): `ledges.py` derives a jump *direction*
per ledge cell from the sole-clear-passage-bit rule (mirroring
`terrain_tags.column_behavior`, hardware-unverified until CH07 per repo
convention — carried here unchanged, not resolved). A ledge cell is never a
resting cell in this graph: `neighbors()` only ever presents it as the
*landing* two tiles beyond an approach cell in the jump direction, exactly
matching the engine's confirmed 2-tile jump
(`event_object_movement.c:5981-5984`, `GetJump2MovementAction`). There is no
edge back the other way -- ignoring that directionality plans an impossible
return path.

Warps (`warps.py`) are exposed as metadata (`MapGraph.warp_exits`) keyed by
trigger cell, resolved from literal (mode==0) command-201 events. They are
NOT force-stamped passable here the way the Phase 5 layout converter's
`warp_overrides` mechanism does at build time (that mechanism folds in
additional S1 warp-trace bookkeeping this library doesn't have access to and
isn't asked to reproduce) -- a warp trigger cell's walkability is decided by
plain collision like any other cell. If a warp sits on a cell that reads
blocked under plain collision, that is a real, reportable gap between this
graph and the build pipeline's own override set; it is not silently patched
here.
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from rpg2gba.tileset_converter.layout import column_key
from rpg2gba.tileset_converter.stairs import StairSide, stair_cell_sides

from . import collision
from .direction import CARDINALS, Direction
from .ledges import derive_ledge_direction as _derive_ledge_direction
from .ledges import load_ledge_direction_overrides
from .warps import WarpExit, extract_warp_exits

logger = logging.getLogger(__name__)

Cell = tuple[int, int]

_ELEVATION_NOTE = (
    "not modelled: RMXP/Essentials decoded map data carries no per-tile "
    "elevation/height field. pokeemerald's Metatile.elevation is a "
    "converter-invented constant that mirrors collision, not real terrain "
    "height, so there is nothing in the decoded corpus to derive it from. A "
    "cliff-rim edge is planned straight through, same as today's runtime "
    "planner (documented gap, CLAUDE.md §4.5)."
)


@dataclass(frozen=True)
class Edge:
    """One outgoing traversal from a cell.

    `kind` is "walk" (ordinary single-tile cardinal step), "stair_diagonal"
    (an E/W press redirected by a sideways-stairs cell — see module
    docstring), or "ledge_jump" (a one-way 2-tile ledge jump). `press` is the
    direction the player pressed to produce this edge (not necessarily the
    direction of net displacement, e.g. a stair_diagonal `press=WEST` can
    land NW or SW depending on the stair's side)."""

    target: Cell
    kind: str
    press: Direction


@dataclass
class MapGraph:
    """The offline traversable graph for one map."""

    map_id: int
    width: int
    height: int
    tileset_id: int
    blocked: dict[Cell, bool]  # raw collision, no stair/ledge/warp overrides
    stair_sides: dict[Cell, StairSide] = field(default_factory=dict)
    ledge_directions: dict[Cell, Direction] = field(default_factory=dict)
    warp_exits: dict[Cell, list[WarpExit]] = field(default_factory=dict)
    elevation_modelled: bool = False
    elevation_note: str = _ELEVATION_NOTE
    # Counter tiles (`collision.build_counter_grid`): not stood on, but
    # interacted ACROSS -- see `interaction_cells`.
    counters: frozenset[Cell] = frozenset()

    # -- basic queries --------------------------------------------------

    def interaction_cells(self, cell: Cell) -> list[tuple[Direction, Cell]]:
        """Where the player stands to use an event at `cell`, per side, in
        N/S/E/W order: the orthogonal neighbour if walkable, or -- when that
        neighbour is a counter -- the cell one further out, since the engine
        reaches across a counter (`Game_Player#check_event_trigger_there`;
        pokeemerald's MB_COUNTER). Kevlar's Center nurse stands behind one.
        Used where the player stands; `reachability.adjacent_approach_cells`
        (the manifest's `requires` model) is deliberately unchanged."""
        out: list[tuple[Direction, Cell]] = []
        x, y = cell
        for d in CARDINALS:
            dx, dy = d.delta
            near = (x + dx, y + dy)
            if self.is_walkable(near):
                out.append((d, near))
            elif near in self.counters and self.is_walkable((x + 2 * dx, y + 2 * dy)):
                out.append((d, (x + 2 * dx, y + 2 * dy)))
        return out

    def in_bounds(self, cell: Cell) -> bool:
        x, y = cell
        return 0 <= x < self.width and 0 <= y < self.height

    def is_stair(self, cell: Cell) -> bool:
        return cell in self.stair_sides

    def is_ledge(self, cell: Cell) -> bool:
        return cell in self.ledge_directions

    def is_walkable(self, cell: Cell) -> bool:
        """Post-override walkability. A stair cell is ALWAYS passable (Phase
        5's layout converter force-stamps stair cells passable regardless of
        their source RMXP passage byte — see `layout.convert_layout`'s
        `behavior_overrides` docstring; the stair script did the moving in
        Uranium, not tile geometry, so the source passage is not
        authoritative here). A ledge cell is never a resting cell (see module
        docstring) -- always reported not-walkable so it can only appear in
        `neighbors()` as a jump landing two tiles beyond, never as a stop."""
        if not self.in_bounds(cell):
            return False
        if self.is_ledge(cell):
            return False
        if self.is_stair(cell):
            return True
        return not self.blocked.get(cell, True)

    # -- stair displacement -----------------------------------------------

    def stair_press_result(self, cell: Cell, press: Direction) -> Cell | None:
        """The resulting cell for pressing `press` (EAST or WEST only) while
        touching stair cell `cell`, per the axis table in the module
        docstring. None if `cell` isn't a stair cell or `press` isn't E/W."""
        side = self.stair_sides.get(cell)
        if side is None or press not in (Direction.EAST, Direction.WEST):
            return None
        x, y = cell
        if side is StairSide.RIGHT:  # NW/SE axis
            return (x - 1, y - 1) if press is Direction.WEST else (x + 1, y + 1)
        else:  # StairSide.LEFT -- NE/SW axis
            return (x - 1, y + 1) if press is Direction.WEST else (x + 1, y - 1)

    # -- neighbours ---------------------------------------------------------

    def neighbors(self, cell: Cell) -> list[Edge]:
        """Outgoing edges from `cell`, respecting stair displacement and
        one-way ledge jumps (see module docstring for both rules)."""
        if not self.in_bounds(cell):
            return []
        edges: list[Edge] = []

        if self.is_stair(cell):
            for press in (Direction.EAST, Direction.WEST):
                result = self.stair_press_result(cell, press)
                if result is not None and self.is_walkable(result):
                    edges.append(Edge(result, "stair_diagonal", press))
            for d in (Direction.NORTH, Direction.SOUTH):
                target = (cell[0] + d.delta[0], cell[1] + d.delta[1])
                if self.is_walkable(target):
                    edges.append(Edge(target, "walk", d))
            return edges

        for d in CARDINALS:
            step = (cell[0] + d.delta[0], cell[1] + d.delta[1])
            if not self.in_bounds(step):
                continue

            if self.is_ledge(step):
                if self.ledge_directions[step] is d:
                    landing = (step[0] + d.delta[0], step[1] + d.delta[1])
                    if self.is_walkable(landing):
                        edges.append(Edge(landing, "ledge_jump", d))
                continue  # a ledge is never a normal step, jumpable or not

            if self.is_stair(step) and d in (Direction.EAST, Direction.WEST):
                result = self.stair_press_result(step, d)
                if result is not None and self.is_walkable(result):
                    edges.append(Edge(result, "stair_diagonal", d))
                continue

            if self.is_walkable(step):
                edges.append(Edge(step, "walk", d))

        return edges

    # -- graph queries --------------------------------------------------

    def reachable_from(self, start: Cell) -> set[Cell]:
        """BFS reachability set from `start` (inclusive), honoring all edge
        rules in `neighbors()`."""
        if not self.is_walkable(start):
            raise ValueError(f"start cell {start} is not walkable on map {self.map_id}")
        seen = {start}
        queue: deque[Cell] = deque([start])
        while queue:
            cur = queue.popleft()
            for edge in self.neighbors(cur):
                if edge.target not in seen:
                    seen.add(edge.target)
                    queue.append(edge.target)
        return seen

    def shortest_path(self, start: Cell, goal: Cell) -> list[Cell] | None:
        """BFS shortest cell sequence start->goal (inclusive both ends), or
        None if unreachable. Unweighted: every edge (walk/stair/ledge) counts
        as one step, matching the golden-test's step-count convention."""
        if not self.is_walkable(start):
            raise ValueError(f"start cell {start} is not walkable on map {self.map_id}")
        if start == goal:
            return [start]
        came_from: dict[Cell, Cell] = {}
        seen = {start}
        queue: deque[Cell] = deque([start])
        while queue:
            cur = queue.popleft()
            for edge in self.neighbors(cur):
                if edge.target in seen:
                    continue
                seen.add(edge.target)
                came_from[edge.target] = cur
                if edge.target == goal:
                    path = [goal]
                    node = goal
                    while node != start:
                        node = came_from[node]
                        path.append(node)
                    path.reverse()
                    return path
                queue.append(edge.target)
        return None

    def connected_components(self) -> list[set[Cell]]:
        """All maximal reachable sets over every walkable cell on the map
        (treating `neighbors()` as directed — a ledge's one-way jump can put
        two cells in the same component without the reverse holding, so this
        is components of the underlying *undirected* reachability closure:
        two cells share a component iff each can reach the other by some
        path OR the graph connects them through a one-way link either way —
        concretely: union-find over every edge, direction ignored, since
        "can walk between these two areas at all" is the useful question for
        a reviewable dump; use `reachable_from`/`shortest_path` directly when
        directionality (a one-way ledge drop) matters)."""
        parent: dict[Cell, Cell] = {}

        def find(c: Cell) -> Cell:
            while parent.setdefault(c, c) != c:
                c = parent[c]
            return c

        def union(a: Cell, b: Cell) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for cell in self.blocked:
            if self.is_walkable(cell):
                find(cell)
                for edge in self.neighbors(cell):
                    union(cell, edge.target)

        groups: dict[Cell, set[Cell]] = {}
        for cell in list(parent):
            groups.setdefault(find(cell), set()).add(cell)
        return list(groups.values())


def build_map_graph(
    map_id: int,
    maps_dir: Path = collision.DEFAULT_MAPS_DIR,
    tilesets_json: Path = collision.DEFAULT_TILESETS_JSON,
    terrain_tag_map: Path | None = None,
) -> MapGraph:
    """Build the offline traversable graph for `map_id` from decoded data on
    disk. `terrain_tag_map` defaults to `ledges.DEFAULT_TERRAIN_TAG_MAP`
    (`reference/terrain_tag_map.json`)."""
    from .ledges import DEFAULT_TERRAIN_TAG_MAP

    map_json = collision.load_map_json(map_id, maps_dir)
    tileset_id = map_json["tileset_id"]
    grid = collision.build_tile_grid(map_json)
    arrays = collision.load_tileset_arrays(tileset_id, tilesets_json)
    blocked = collision.build_blocked_grid(grid, arrays)

    stair_sides = stair_cell_sides(map_json)

    overrides = load_ledge_direction_overrides(terrain_tag_map or DEFAULT_TERRAIN_TAG_MAP)
    ledge_directions: dict[Cell, Direction] = {}
    for y in range(grid.ysize):
        for x in range(grid.xsize):
            key = column_key(grid, x, y)
            if not key:
                continue
            direction = _derive_ledge_direction(
                tileset_id, key,
                terrain_tags=arrays.terrain_tags,
                passages=arrays.passages,
                overrides=overrides,
            )
            if direction is not None:
                ledge_directions[(x, y)] = direction

    stair_ledge_overlap = set(stair_sides) & set(ledge_directions)
    if stair_ledge_overlap:
        raise ValueError(
            f"map {map_id}: cell(s) {sorted(stair_ledge_overlap)} are classified "
            "as both a staircase and a ledge — contradictory derived data"
        )

    warp_list = extract_warp_exits(map_json)
    warp_exits: dict[Cell, list[WarpExit]] = {}
    for w in warp_list:
        warp_exits.setdefault(w.cell, []).append(w)

    return MapGraph(
        map_id=map_id,
        width=map_json["width"],
        height=map_json["height"],
        tileset_id=tileset_id,
        blocked=blocked,
        stair_sides=stair_sides,
        ledge_directions=ledge_directions,
        warp_exits=warp_exits,
        counters=frozenset(c for c, is_counter in
                           collision.build_counter_grid(grid, arrays).items() if is_counter),
    )
