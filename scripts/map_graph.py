# ruff: noqa: E501
"""Map graph helpers for the Uranium map viewer.

Provides name lookup, parent/child relationships, warp-target extraction,
seam-connection geometry (connections.dat), and index/tree building from the
on-disk map JSON corpus.

Public API (imported by the viewer server):
    load_map_names()           -> dict[int, str]
    map_display_name(id)       -> str
    map_parent_id(id)          -> int | None
    extract_warp_targets(id)   -> list[int]
    connections_for(id)        -> list[dict]
    component_layout(id)       -> dict
    map_relationships(id)      -> dict
    build_index()              -> dict
"""
from __future__ import annotations

import functools
import json
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))
from map_viewer_common import _maps_dir, _repo_root  # noqa: E402

# ---------------------------------------------------------------------------
# Internal loaders (cached once; call .cache_clear() in tests)
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _load_map_infos() -> dict[str, dict]:
    """Load output/uranium-build/map_infos.json keyed by string map id."""
    path = _maps_dir().parent / "map_infos.json"
    return json.loads(path.read_text(encoding="utf-8"))


@functools.lru_cache(maxsize=1)
def _load_overrides() -> dict[str, dict]:
    """Load reference/map_name_overrides.json -> overrides sub-dict (or {}).

    Returns empty dict if the file is missing.
    """
    path = _repo_root() / "reference" / "map_name_overrides.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("overrides", {})


@functools.lru_cache(maxsize=1)
def _map_id_universe() -> frozenset[int]:
    """Frozenset of map ids that have a Map{NNN}.json file in _maps_dir()."""
    ids: set[int] = set()
    for p in _maps_dir().iterdir():
        name = p.name
        if name.startswith("Map") and name.endswith(".json"):
            stem = name[3:-5]
            if stem.isdigit():
                ids.add(int(stem))
    return frozenset(ids)


def _load_map_json(mid: int) -> dict:
    """Load and return the parsed JSON for Map{mid:03d}.json."""
    path = _maps_dir() / f"Map{mid:03d}.json"
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_map_names() -> dict[int, str]:
    """Return int map id -> display name for every id in the JSON universe.

    Priority: override display_name > map_infos 'name' > f'Map{mid:03d}'.
    """
    overrides = _load_overrides()
    infos = _load_map_infos()
    names: dict[int, str] = {}
    for mid in _map_id_universe():
        key = str(mid)
        if key in overrides and "display_name" in overrides[key]:
            names[mid] = overrides[key]["display_name"]
        elif key in infos and "name" in infos[key]:
            names[mid] = infos[key]["name"]
        else:
            names[mid] = f"Map{mid:03d}"
    return names


def map_display_name(map_id: int) -> str:
    """Return display name for a single map id; fallback f'Map{map_id:03d}'."""
    return load_map_names().get(map_id, f"Map{map_id:03d}")


def map_parent_id(map_id: int) -> int | None:
    """Return parent_id from map_infos for map_id, or None.

    Returns None when: map_id not in the JSON universe, parent_id is 0/absent,
    or the declared parent id has no Map JSON of its own.
    """
    universe = _map_id_universe()
    if map_id not in universe:
        return None
    info = _load_map_infos().get(str(map_id), {})
    pid = info.get("parent_id", 0)
    if not pid or pid not in universe:
        return None
    return pid


def extract_warp_targets(map_id: int) -> list[int]:
    """Return sorted distinct literal destination map ids via code-201 transfers.

    Only counts parameters[0]==0 (literal destination).  Excludes the source
    map itself.  Skips malformed events/pages/commands defensively.
    """
    try:
        doc = _load_map_json(map_id)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []

    targets: set[int] = set()
    events = doc.get("events") or []
    for event in events:
        if not isinstance(event, dict):
            continue
        pages = event.get("pages") or []
        for page in pages:
            if not isinstance(page, dict):
                continue
            commands = page.get("list") or []
            for cmd in commands:
                if not isinstance(cmd, dict):
                    continue
                if cmd.get("code") != 201:
                    continue
                params = cmd.get("parameters")
                if not isinstance(params, list) or len(params) < 2:
                    continue
                try:
                    mode = int(params[0])
                    dest = int(params[1])
                except (TypeError, ValueError):
                    continue
                if mode != 0:
                    continue  # variable-driven; skip
                if dest == map_id:
                    continue  # self-warp; exclude
                targets.add(dest)

    return sorted(targets)


# ---------------------------------------------------------------------------
# Seam connections (Data/connections.dat)
#
# Raw entry: [id_a, edge_a, offset_a, id_b, edge_b, offset_b].  Essentials
# (107__PField_Map.rb getMapConnections/getMapEdge) normalizes each (edge,
# offset) to an anchor POINT in that map's cell space — N->(off,0), S->(off,h),
# W->(0,off), E->(w,off) — and the two anchors coincide in world space.  So
# map B's origin relative to map A is (anchorA - anchorB).
# ---------------------------------------------------------------------------

_EDGES = ("N", "S", "E", "W")


@functools.lru_cache(maxsize=1)
def _load_connections_raw() -> tuple[tuple, ...]:
    """Raw connections.dat entries as tuples.

    Reads the JSON cache at output/uranium-build/connections.json; if absent,
    dumps it once from `$RPG2GBA_URANIUM_SRC/Data/connections.dat` via the
    repo's Ruby marshal helper (writing the cache).  If neither is possible
    the viewer degrades to no-seams with a logged warning.
    """
    cache = _maps_dir().parent / "connections.json"
    if cache.is_file():
        raw = json.loads(cache.read_text(encoding="utf-8"))
        return tuple(tuple(e) for e in raw)
    try:
        import os

        from map_viewer_common import _load_dotenv

        _load_dotenv()
        src = os.environ.get("RPG2GBA_URANIUM_SRC")
        if not src:
            raise RuntimeError("RPG2GBA_URANIUM_SRC not set")
        from rpg2gba.pbs_converter._marshal import dump_dat, load_json

        raw = load_json(dump_dat(Path(src) / "Data" / "connections.dat", cache))
        return tuple(tuple(e) for e in raw)
    except Exception as exc:  # degrade, don't kill the viewer
        log.warning("connections.dat unavailable (%s); seam features disabled", exc)
        return ()


@functools.lru_cache(maxsize=None)
def map_dims(map_id: int) -> tuple[int, int]:
    """(width, height) in cells from the map JSON."""
    doc = _load_map_json(map_id)
    return int(doc["width"]), int(doc["height"])


def _anchor(map_id: int, edge: str, offset: int) -> tuple[int, int]:
    """The Essentials anchor point for (edge, offset) on map_id."""
    w, h = map_dims(map_id)
    if edge == "N":
        return (offset, 0)
    if edge == "S":
        return (offset, h)
    if edge == "W":
        return (0, offset)
    if edge == "E":
        return (w, offset)
    raise ValueError(f"connections.dat: unknown edge {edge!r} on map {map_id}")


def connections_for(map_id: int) -> list[dict]:
    """Seam connections touching map_id, with full geometry.

    Each entry::

        {
          'id': other_map_id, 'name': str,
          'edge': 'N'|'S'|'E'|'W',      # MY edge the seam sits on
          'origin': [dx, dy],           # other map's (0,0) relative to mine
          'band': [lo, hi],             # my-edge cell range shared with other
                                        # (x range for N/S, y range for E/W;
                                        #  hi is exclusive)
        }
    """
    out: list[dict] = []
    for entry in _load_connections_raw():
        if len(entry) != 6:
            continue
        a, ea, oa, b, eb, ob = entry
        for mid, me, mo, oid, oe, oo in ((a, ea, oa, b, eb, ob), (b, eb, ob, a, ea, oa)):
            if mid != map_id or me not in _EDGES or oe not in _EDGES:
                continue
            try:
                ax, ay = _anchor(mid, me, int(mo))
                bx, by = _anchor(oid, oe, int(oo))
                w, h = map_dims(mid)
                ow, oh = map_dims(oid)
            except (FileNotFoundError, json.JSONDecodeError, OSError, KeyError):
                continue
            dx, dy = ax - bx, ay - by
            if me in ("N", "S"):
                band = [max(0, dx), min(w, dx + ow)]
            else:
                band = [max(0, dy), min(h, dy + oh)]
            if band[0] >= band[1]:
                continue  # degenerate seam (no shared edge cells)
            out.append({
                "id": oid,
                "name": map_display_name(oid),
                "edge": me,
                "origin": [dx, dy],
                "band": band,
            })
    return sorted(out, key=lambda c: (c["edge"], c["id"]))


def component_layout(map_id: int) -> dict:
    """BFS the seam graph from map_id into one shared cell space.

    Returns ``{'members': [{'id','name','ox','oy','w','h'}, ...], 'w': W,
    'h': H, 'anchor': map_id}`` with offsets normalized so the component's
    bounding box starts at (0, 0).  A map with no seams yields one member.
    Inconsistent multi-path offsets (shouldn't happen with 14 seams) keep the
    first-reached position and log a warning.
    """
    pos: dict[int, tuple[int, int]] = {map_id: (0, 0)}
    queue = [map_id]
    while queue:
        cur = queue.pop(0)
        cx, cy = pos[cur]
        for conn in connections_for(cur):
            oid = conn["id"]
            ox, oy = cx + conn["origin"][0], cy + conn["origin"][1]
            if oid in pos:
                if pos[oid] != (ox, oy):
                    log.warning(
                        "component_layout(%d): map %d reached at %s and %s; keeping first",
                        map_id, oid, pos[oid], (ox, oy),
                    )
                continue
            pos[oid] = (ox, oy)
            queue.append(oid)
    min_x = min(x for x, _ in pos.values())
    min_y = min(y for _, y in pos.values())
    members = []
    for mid in sorted(pos):
        x, y = pos[mid]
        w, h = map_dims(mid)
        members.append({
            "id": mid,
            "name": map_display_name(mid),
            "ox": x - min_x,
            "oy": y - min_y,
            "w": w,
            "h": h,
        })
    return {
        "members": members,
        "w": max(m["ox"] + m["w"] for m in members),
        "h": max(m["oy"] + m["h"] for m in members),
        "anchor": map_id,
    }


def map_relationships(map_id: int) -> dict:
    """Return relationship dict for map_id.

    Shape::

        {
            'id': int, 'name': str,
            'parent': {'id': int, 'name': str} | None,
            'children': [{'id': int, 'name': str}, ...],
            'warps':    [{'id': int, 'name': str}, ...],
            'connections': [connections_for() entry, ...],
        }

    children = maps in the universe whose map_parent_id() == map_id, sorted by id.
    warps    = extract_warp_targets resolved to names, sorted by id.
    connections = seam connections with geometry (see connections_for).
    """
    names = load_map_names()
    universe = _map_id_universe()

    pid = map_parent_id(map_id)
    parent = {"id": pid, "name": names.get(pid, f"Map{pid:03d}")} if pid is not None else None

    children = sorted(mid for mid in universe if map_parent_id(mid) == map_id)
    warp_ids = extract_warp_targets(map_id)

    return {
        "id": map_id,
        "name": names.get(map_id, f"Map{map_id:03d}"),
        "parent": parent,
        "children": [{"id": c, "name": names.get(c, f"Map{c:03d}")} for c in children],
        "warps": [{"id": w, "name": names.get(w, f"Map{w:03d}")} for w in warp_ids],
        "connections": connections_for(map_id),
    }


def build_index() -> dict:
    """Build the full map index and parent-child forest.

    Returns::

        {
            'maps': [{'id': int, 'name': str, 'parent_id': int | None}, ...],
            'tree': [node, ...],
        }

    where node = {'id': int, 'name': str, 'children': [node, ...]}.

    A map is a root when its parent_id is 0/None/absent OR points to a
    non-existent map id.  Siblings are sorted by id.  Cycles are broken
    defensively (the cycle member becomes a root).
    """
    names = load_map_names()
    universe = _map_id_universe()

    # Flat list sorted by id
    maps_list = sorted(
        (
            {
                "id": mid,
                "name": names.get(mid, f"Map{mid:03d}"),
                "parent_id": map_parent_id(mid),
            }
            for mid in universe
        ),
        key=lambda m: m["id"],
    )

    # --- cycle-safe effective parent ----------------------------------------
    # Walk each map's declared parent chain; if we encounter the map itself,
    # it's in a cycle and should be treated as a root.
    def _effective_parent(mid: int) -> int | None:
        pid = map_parent_id(mid)
        if pid is None:
            return None
        # Walk pid's ancestry; if we see mid again => cycle
        visited: set[int] = set()
        cur: int | None = pid
        while cur is not None:
            if cur == mid:
                return None  # cycle detected; make mid a root
            if cur in visited:
                break  # loop in ancestry not involving mid; stop
            visited.add(cur)
            cur = map_parent_id(cur)
        return pid

    # Build children map
    children_of: dict[int, list[int]] = {mid: [] for mid in universe}
    roots: list[int] = []
    for mid in sorted(universe):
        pid = _effective_parent(mid)
        if pid is None:
            roots.append(mid)
        else:
            children_of[pid].append(mid)

    def _build_node(mid: int, ancestors: frozenset[int]) -> dict:
        if mid in ancestors:
            # Cycle guard — treat as leaf
            return {"id": mid, "name": names.get(mid, f"Map{mid:03d}"), "children": []}
        new_ancestors = ancestors | {mid}
        kids = sorted(children_of.get(mid, []))
        return {
            "id": mid,
            "name": names.get(mid, f"Map{mid:03d}"),
            "children": [_build_node(k, new_ancestors) for k in kids],
        }

    tree = [_build_node(r, frozenset()) for r in sorted(roots)]

    return {"maps": maps_list, "tree": tree}


# ---------------------------------------------------------------------------
# __main__ self-summary
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    universe = _map_id_universe()
    print(f"Map universe: {len(universe)} maps")

    names = load_map_names()
    for sample_id in (32, 49, 48):
        if sample_id in universe:
            rel = map_relationships(sample_id)
            parent_str = (
                f"{rel['parent']['id']} ({rel['parent']['name']})"
                if rel["parent"] else "none"
            )
            children_str = (
                ", ".join(f"{c['id']} ({c['name']})" for c in rel["children"])
                or "none"
            )
            warps_str = (
                ", ".join(f"{w['id']} ({w['name']})" for w in rel["warps"])
                or "none"
            )
            print(
                f"\nMap {sample_id} — {rel['name']}\n"
                f"  parent  : {parent_str}\n"
                f"  children: {children_str}\n"
                f"  warps   : {warps_str}"
            )

    idx = build_index()
    print(f"\nbuild_index: {len(idx['maps'])} maps, {len(idx['tree'])} root nodes in tree")
