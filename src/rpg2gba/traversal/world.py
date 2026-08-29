"""Corpus-wide world graph — nodes are maps, edges are every way a player can
move from one map to another.

This sits one layer above `graph.py` (which models walkability *within* one
map). It exists because the project's chapter/play-order data
(`reference/chapters.json`) was authored against
`output/uranium-build/connections.json`, which holds only the ~14 overland
scroll-seam rows for the whole corpus — it cannot see doors, cave mouths, or
stairs, all of which are ordinary command-201 warp events. Map-to-map
adjacency derived from `connections.json` alone is therefore badly
incomplete; this module assembles the full picture from three provenance-
tagged edge sources:

    warp        -- one map's literal (mode==0) command-201 "Transfer Player"
                   event (`warps.extract_warp_exits`). Directed: a warp only
                   has a reverse edge if the destination map has its own warp
                   event pointing back.
    connection  -- one row of `connections.json` (Essentials borderless-seam
                   data, parsed by `tileset_converter.connections`). Always
                   emitted in both directions -- a scroll-stitched seam is
                   inherently two-way.
    seam_warp   -- one reciprocal cell pair from `reference/seam_warps.json`
                   (`tileset_converter.seam_warps`), a hand-authored synthetic
                   arrow-warp substitute for a connection whose two maps
                   can't share a tileset. Always emitted in both directions,
                   same as a connection (it stands in for one).

Variable-driven (mode!=0) warps have no fixed destination and cannot be
graphed at all (see `warps.py`'s module docstring) -- `extract_warp_exits`
already excludes them, logging at INFO. This module does not change that; it
additionally *counts* them per map, because "this map leads somewhere we
cannot see" is exactly the kind of blind spot a world graph exists to make
countable (`WorldGraph.variable_warp_count` / `variable_warp_maps`).

Fails loud (ValueError) on: a warp whose destination map id does not exist in
the corpus (i.e. has neither a map file nor a `map_infos.json` entry); a
`connections.json` row naming an unknown map; a `seam_warps.json` entry
naming an unknown map. Per CLAUDE.md §4.5, none of these are silently
dropped or defaulted.
"""
from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from rpg2gba.tileset_converter.connections import load_connections
from rpg2gba.tileset_converter.seam_warps import DEFAULT_SEAM_WARPS_PATH, load_seam_warps

from . import collision
from . import warps as _warps
from .warps import extract_warp_exits

logger = logging.getLogger(__name__)

DEFAULT_MAP_INFOS_JSON = Path("output/uranium-build/map_infos.json")
DEFAULT_CONNECTIONS_JSON = Path("output/uranium-build/connections.json")

# CH01's outdoor map (reference/chapters.json chapters[0]: id "CH01",
# title "Moki Town", maps == [32, 48, 49, 50, 64, 65, 89, 172], outdoor ==
# 32) -- the first map the player ever stands on. Used only as the default
# anchor for "what's unreachable from the start" reporting; callers may pass
# a different map id.
DEFAULT_START_MAP_ID = 32

_EDGE_KINDS = ("warp", "connection", "seam_warp")


@dataclass(frozen=True)
class WorldEdge:
    """One directed map-to-map traversal.

    `src_cell`/`dst_cell` are the trigger/landing cell in each map's own
    local grid where known (always known for "warp" and "seam_warp"; None
    for "connection", which has no single trigger cell -- the whole shared
    edge is crossable). `event_id` is the source command-201 event id, set
    only for `kind == "warp"`.
    """

    src_map: int
    dst_map: int
    kind: str  # "warp" | "connection" | "seam_warp"
    src_cell: tuple[int, int] | None = None
    dst_cell: tuple[int, int] | None = None
    event_id: int | None = None


def _map_id_from_filename(path: Path) -> int | None:
    """`Map037.json` -> 37; anything else -> None (skipped, not an error --
    the maps directory is not guaranteed to hold only map files)."""
    stem = path.stem
    if not stem.startswith("Map"):
        return None
    try:
        return int(stem[3:])
    except ValueError:
        return None


def _count_variable_warps(map_json: dict) -> int:
    """Count command-201 events on `map_json` whose mode is NOT the literal
    (mode==0) case -- mirrors `warps.extract_warp_exits`'s own detection
    (same command code / mode constants, reused via the module rather than
    re-derived) but returns a count instead of only logging."""
    count = 0
    for event in map_json.get("events", []):
        if not event:
            continue
        for page in event.get("pages", []):
            for command in page.get("list", []):
                if command.get("code") != _warps._CODE_TRANSFER_PLAYER:
                    continue
                params = command.get("parameters", [])
                if len(params) < 4:
                    continue
                if params[0] != _warps._MODE_LITERAL:
                    count += 1
    return count


@dataclass
class WorldGraph:
    """The corpus-wide map adjacency graph."""

    edges: list[WorldEdge]
    names: dict[int, str]
    map_ids: frozenset[int]
    maps_without_info: frozenset[int]  # has a map file, absent from map_infos.json
    infos_without_map: frozenset[int]  # has a map_infos.json entry, no map file on disk
    variable_warp_count: int
    variable_warp_maps: dict[int, int]  # map_id -> count of variable-driven warps on it

    _from_index: dict[int, list[WorldEdge]] = field(default_factory=dict, init=False, repr=False)
    _to_index: dict[int, list[WorldEdge]] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        for e in self.edges:
            self._from_index.setdefault(e.src_map, []).append(e)
            self._to_index.setdefault(e.dst_map, []).append(e)

    # -- basic queries ----------------------------------------------------

    def edges_from(self, map_id: int) -> list[WorldEdge]:
        return list(self._from_index.get(map_id, []))

    def edges_to(self, map_id: int) -> list[WorldEdge]:
        return list(self._to_index.get(map_id, []))

    def neighbors(self, map_id: int) -> list[int]:
        """Distinct destination map ids reachable by one edge from `map_id`,
        sorted for determinism."""
        return sorted({e.dst_map for e in self.edges_from(map_id)})

    def is_bidirectional(self, a: int, b: int) -> bool:
        """True iff there is at least one edge a->b AND at least one b->a."""
        fwd = any(e.dst_map == b for e in self.edges_from(a))
        back = any(e.dst_map == a for e in self.edges_from(b))
        return fwd and back

    def one_way_pairs(self) -> list[tuple[int, int]]:
        """Directed (src, dst) pairs with an edge src->dst but no edge in the
        opposite direction. Each gap is reported once, as the forward
        direction that exists."""
        present = {(e.src_map, e.dst_map) for e in self.edges}
        return sorted(p for p in present if (p[1], p[0]) not in present)

    def orphan_maps(self) -> list[int]:
        """Maps with neither an outgoing nor an incoming edge."""
        return sorted(
            m for m in self.map_ids if not self.edges_from(m) and not self.edges_to(m)
        )

    # -- graph-wide queries -------------------------------------------------

    def reachable_from(self, map_id: int) -> set[int]:
        """BFS reachability set (inclusive) over directed edges."""
        seen = {map_id}
        queue: deque[int] = deque([map_id])
        while queue:
            cur = queue.popleft()
            for e in self.edges_from(cur):
                if e.dst_map not in seen:
                    seen.add(e.dst_map)
                    queue.append(e.dst_map)
        return seen

    def hop_distances_from(self, map_id: int) -> dict[int, int]:
        """BFS hop count (inclusive, `map_id` itself is 0) over directed
        edges."""
        dist = {map_id: 0}
        queue: deque[int] = deque([map_id])
        while queue:
            cur = queue.popleft()
            for e in self.edges_from(cur):
                if e.dst_map not in dist:
                    dist[e.dst_map] = dist[cur] + 1
                    queue.append(e.dst_map)
        return dist

    def shortest_path(self, src: int, dst: int) -> list[WorldEdge] | None:
        """Shortest edge sequence src->dst (BFS, unweighted), or None if
        unreachable. Empty list if src == dst."""
        if src == dst:
            return []
        seen = {src}
        came_from: dict[int, WorldEdge] = {}
        queue: deque[int] = deque([src])
        while queue:
            cur = queue.popleft()
            for e in self.edges_from(cur):
                if e.dst_map in seen:
                    continue
                seen.add(e.dst_map)
                came_from[e.dst_map] = e
                if e.dst_map == dst:
                    path = [e]
                    node = e.src_map
                    while node != src:
                        prev = came_from[node]
                        path.append(prev)
                        node = prev.src_map
                    path.reverse()
                    return path
                queue.append(e.dst_map)
        return None

    def connected_components(self) -> list[set[int]]:
        """Maximal groups of maps connected by any edge, direction ignored
        (union-find over the undirected closure -- mirrors
        `graph.MapGraph.connected_components`'s rationale: "can move between
        these two maps at all" is the useful question for a corpus-wide
        summary; use `reachable_from` when directionality matters). Every map
        in `map_ids` appears in exactly one component, including orphans
        (singleton components)."""
        parent: dict[int, int] = {}

        def find(m: int) -> int:
            while parent.setdefault(m, m) != m:
                m = parent[m]
            return m

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for m in self.map_ids:
            find(m)
        for e in self.edges:
            union(e.src_map, e.dst_map)

        groups: dict[int, set[int]] = {}
        for m in self.map_ids:
            groups.setdefault(find(m), set()).add(m)
        return list(groups.values())


def _fail_unknown_map(context: str, map_id: int) -> None:
    raise ValueError(f"{context}: map {map_id} does not exist in the corpus")


def build_world_graph(
    maps_dir: Path = collision.DEFAULT_MAPS_DIR,
    map_infos: Path = DEFAULT_MAP_INFOS_JSON,
    connections_json: Path = DEFAULT_CONNECTIONS_JSON,
    seam_warps: Path = DEFAULT_SEAM_WARPS_PATH,
) -> WorldGraph:
    """Build the corpus-wide `WorldGraph` from decoded data on disk.

    Iterates every `Map*.json` file under `maps_dir` for warp edges, every
    row of `connections_json` (both directions), and every seam of
    `seam_warps` (both directions). See module docstring for the fail-loud
    contract.
    """
    maps_dir = Path(maps_dir)
    map_infos = Path(map_infos)
    connections_json = Path(connections_json)
    seam_warps = Path(seam_warps)

    map_paths: dict[int, Path] = {}
    for p in sorted(maps_dir.glob("Map*.json")):
        mid = _map_id_from_filename(p)
        if mid is not None:
            map_paths[mid] = p

    infos_raw: dict[str, dict] = json.loads(map_infos.read_text(encoding="utf-8"))
    info_ids = {int(k) for k in infos_raw}

    map_ids = frozenset(set(map_paths) | info_ids)
    maps_without_info = frozenset(set(map_paths) - info_ids)
    infos_without_map = frozenset(info_ids - set(map_paths))

    names: dict[int, str] = {}
    for mid in map_ids:
        info = infos_raw.get(str(mid))
        names[mid] = info["name"] if info and "name" in info else f"Map{mid:03d}"

    edges: list[WorldEdge] = []
    variable_warp_maps: dict[int, int] = {}
    variable_warp_count = 0

    for mid, path in sorted(map_paths.items()):
        map_json = json.loads(path.read_text(encoding="utf-8"))

        var_count = _count_variable_warps(map_json)
        if var_count:
            variable_warp_maps[mid] = var_count
            variable_warp_count += var_count

        for w in extract_warp_exits(map_json):
            if w.dest_map not in map_ids:
                raise ValueError(
                    f"map {mid} event {w.event_id}: warp destination map "
                    f"{w.dest_map} does not exist in the corpus (no map file, "
                    "no map_infos.json entry)"
                )
            edges.append(
                WorldEdge(
                    src_map=mid,
                    dst_map=w.dest_map,
                    kind="warp",
                    src_cell=w.cell,
                    dst_cell=(w.dest_x, w.dest_y),
                    event_id=w.event_id,
                )
            )

    for row in load_connections(connections_json):
        for m in (row.map_a, row.map_b):
            if m not in map_ids:
                raise ValueError(
                    f"connections.json row {row}: map {m} does not exist in the corpus"
                )
        edges.append(WorldEdge(src_map=row.map_a, dst_map=row.map_b, kind="connection"))
        edges.append(WorldEdge(src_map=row.map_b, dst_map=row.map_a, kind="connection"))

    for seam in load_seam_warps(seam_warps):
        for m in (seam.map_a, seam.map_b):
            if m not in map_ids:
                raise ValueError(
                    f"seam_warps.json seam {seam.seam_id!r}: map {m} does not exist "
                    "in the corpus"
                )
        for (xa, ya), (xb, yb) in zip(seam.cells_a, seam.cells_b):
            edges.append(
                WorldEdge(
                    src_map=seam.map_a, dst_map=seam.map_b, kind="seam_warp",
                    src_cell=(xa, ya), dst_cell=(xb, yb),
                )
            )
            edges.append(
                WorldEdge(
                    src_map=seam.map_b, dst_map=seam.map_a, kind="seam_warp",
                    src_cell=(xb, yb), dst_cell=(xa, ya),
                )
            )

    return WorldGraph(
        edges=edges,
        names=names,
        map_ids=map_ids,
        maps_without_info=maps_without_info,
        infos_without_map=infos_without_map,
        variable_warp_count=variable_warp_count,
        variable_warp_maps=variable_warp_maps,
    )
