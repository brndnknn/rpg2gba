"""Pure split geometry (design `reference/guides/map_split_stage.md` §4–§6).

No file IO: `derive_split` takes the origin map's JSON, its collision, the cells
the player can enter it at, and the spec, and returns every piece's map JSON
plus the arrow-warp pairs, the connection rewrites and the coordinate resolver.
Every inconsistency fails loud (CLAUDE.md §4.5) with the cells involved."""
from __future__ import annotations

import copy
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from rpg2gba.map_split.ids import piece_uid
from rpg2gba.map_split.spec import SplitSpec
from rpg2gba.tileset_converter.connection_remap import STRIP_DEPTH_EW, STRIP_DEPTH_NS

Cell = tuple[int, int]

# The camera's visible extent around the player (field_camera.c, verified
# 2026-10-07): a piece needs real art for every cell this far from anywhere the
# player can stand in it.
VIEW_H = STRIP_DEPTH_EW
VIEW_V = STRIP_DEPTH_NS

# pokeemerald's backup map buffer: (width + 15) * (height + 14) <= 10240
# (engine/include/fieldmap.h MAX_MAP_DATA_SIZE, fieldmap.c:181).
MAX_MAP_DATA_SIZE = 10240

# RMXP move-route command codes that step the character one cell.
_STEP = {1: (0, 1), 2: (-1, 0), 3: (1, 0), 4: (0, -1),
         5: (-1, 1), 6: (1, 1), 7: (-1, -1), 8: (1, -1)}
_SET_MOVE_ROUTE = 209
_SET_EVENT_LOCATION = 202
_TRANSFER_PLAYER = 201
_MOVE_TYPE_CUSTOM = 3

_DIR_NAME = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}


class SplitError(ValueError):
    """A split spec that the map's geometry or events contradict."""


@dataclass(frozen=True)
class Rect:
    x0: int
    y0: int
    w: int
    h: int

    def contains(self, x: int, y: int) -> bool:
        return self.x0 <= x < self.x0 + self.w and self.y0 <= y < self.y0 + self.h


@dataclass
class Piece:
    uid: int
    k: int
    name: str
    rect: Rect
    walk: frozenset[Cell]               # origin coords
    visible: frozenset[Cell]            # origin coords, inside rect
    blocked_cells: list[Cell]           # piece-local coords (cut cells in rect)
    event_ids: list[int]
    map_json: dict = field(repr=False)


@dataclass(frozen=True)
class ArrowSeam:
    """One generated arrow-warp seam between two pieces (seam_warps.json shape)."""

    seam_id: str
    map_a: int
    map_b: int
    cells_a: tuple[Cell, ...]
    cells_b: tuple[Cell, ...]
    direction_a: str
    direction_b: str

    def as_json(self) -> dict:
        return {
            "id": self.seam_id, "map_a": self.map_a, "map_b": self.map_b,
            "cells_a": [list(c) for c in self.cells_a],
            "cells_b": [list(c) for c in self.cells_b],
            "direction_a": self.direction_a, "direction_b": self.direction_b,
        }


@dataclass
class SplitResult:
    origin: int
    pieces: list[Piece]
    seams: list[ArrowSeam]
    owner: dict[Cell, int]   # origin cell -> piece uid (every cell of the map)
    cuts: frozenset[Cell]

    def piece_by_uid(self, uid: int) -> Piece:
        for p in self.pieces:
            if p.uid == uid:
                return p
        raise KeyError(uid)

    def resolve(self, x: int, y: int, *, what: str = "cell") -> tuple[int, int, int]:
        """Origin (x, y) -> (piece uid, local x, local y). Fails loud on a cut
        cell or a cell outside its owning piece's rectangle."""
        if (x, y) in self.cuts:
            raise SplitError(f"map {self.origin}: {what} ({x},{y}) is a cut cell")
        uid = self.owner.get((x, y))
        if uid is None:
            raise SplitError(f"map {self.origin}: {what} ({x},{y}) is outside the map")
        r = self.piece_by_uid(uid).rect
        if not r.contains(x, y):
            raise SplitError(
                f"map {self.origin}: {what} ({x},{y}) is owned by piece {uid} but lies "
                f"outside its rectangle {r}"
            )
        return uid, x - r.x0, y - r.y0


# --------------------------------------------------------------------------- geometry


def _flood(start: Iterable[Cell], passable: set[Cell]) -> set[Cell]:
    seen = set(start)
    stack = list(seen)
    while stack:
        x, y = stack.pop()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n in passable and n not in seen:
                seen.add(n)
                stack.append(n)
    return seen


def _components(cells: set[Cell]) -> list[set[Cell]]:
    left = set(cells)
    out: list[set[Cell]] = []
    for c in sorted(cells, key=lambda c: (c[1], c[0])):
        if c in left:
            comp = _flood([c], left)
            left -= comp
            out.append(comp)
    return out


def _dilate(cells: Iterable[Cell], width: int, height: int) -> set[Cell]:
    out: set[Cell] = set()
    for x, y in cells:
        for yy in range(max(0, y - VIEW_V), min(height, y + VIEW_V + 1)):
            for xx in range(max(0, x - VIEW_H), min(width, x + VIEW_H + 1)):
                out.add((xx, yy))
    return out


def _ownership(walk_by_uid: Mapping[int, set[Cell]], width: int, height: int) -> dict[Cell, int]:
    """Every cell -> nearest piece by 8-way BFS from the pieces' walkable cells.
    Deterministic: sources are enqueued in (uid, y, x) order."""
    owner: dict[Cell, int] = {}
    q: deque[Cell] = deque()
    for uid in sorted(walk_by_uid):
        for c in sorted(walk_by_uid[uid], key=lambda c: (c[1], c[0])):
            owner[c] = uid
            q.append(c)
    while q:
        x, y = q.popleft()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                n = (x + dx, y + dy)
                if 0 <= n[0] < width and 0 <= n[1] < height and n not in owner:
                    owner[n] = owner[(x, y)]
                    q.append(n)
    return owner


# --------------------------------------------------------------------------- events


def _route_cells(start: Cell, moves: list[dict]) -> list[Cell]:
    x, y = start
    out = [start]
    face = (0, 1)
    for mv in moves:
        c = mv.get("code")
        if c in _STEP:
            face = _STEP[c]
            dx, dy = face
        elif c == 12:
            dx, dy = face
        elif c == 13:
            dx, dy = -face[0], -face[1]
        elif c == 14:
            p = mv.get("parameters") or [0, 0]
            dx, dy = int(p[0]), int(p[1])
        else:
            continue
        x, y = x + dx, y + dy
        out.append((x, y))
    return out


def _check_events(
    events: list[dict], owner: dict[Cell, int], cuts: frozenset[Cell], origin: int
) -> None:
    """Fail loud on anything a split would silently break: a page acting on an
    event in another piece, or a fixed patrol crossing a cut."""
    pos = {e["id"]: (e["x"], e["y"]) for e in events}
    problems: list[str] = []
    for e in events:
        eid = e["id"]
        mine = owner[(e["x"], e["y"])]
        for pi, page in enumerate(e.get("pages", [])):
            if page.get("move_type") == _MOVE_TYPE_CUSTOM:
                path = _route_cells((e["x"], e["y"]), (page.get("move_route") or {}).get("list", []))
                hit = [c for c in path if c in cuts]
                if hit:
                    problems.append(f"EV{eid:03d} p{pi}: autonomous route crosses cut cell(s) {hit}")
            for cmd in page.get("list", []):
                code = cmd.get("code")
                params = cmd.get("parameters") or []
                if code in (_SET_MOVE_ROUTE, _SET_EVENT_LOCATION) and params:
                    target = params[0]
                    if isinstance(target, int) and target > 0 and target != eid:
                        if target not in pos:
                            continue  # dangling RMXP reference; not ours to judge
                        theirs = owner[pos[target]]
                        if theirs != mine:
                            problems.append(
                                f"EV{eid:03d} p{pi}: code {code} acts on EV{target:03d}, "
                                f"which lands in piece {theirs} (this event: {mine})"
                            )
    if problems:
        raise SplitError(
            f"map {origin}: the split separates events that act on each other:\n  "
            + "\n  ".join(problems)
        )


def _rebase_event(event: dict, rect: Rect) -> dict:
    e = copy.deepcopy(event)
    e["x"] -= rect.x0
    e["y"] -= rect.y0
    return e


# --------------------------------------------------------------------------- main


def derive_split(
    map_json: dict,
    blocked: Mapping[Cell, bool],
    entry_cells: Iterable[Cell],
    spec: SplitSpec,
) -> SplitResult:
    """Split `map_json` per `spec`.

    `blocked` is the origin's collision (`traversal.collision.build_blocked_grid`).
    `entry_cells` are where the player can enter the map (warp arrivals and the
    passable edge cells of its connections); the walkable area is everything
    reachable from them, and each entry cell counts as walkable even if its tile
    reads blocked (a door the player steps out of)."""
    origin = spec.origin
    width, height = int(map_json["width"]), int(map_json["height"])
    cuts = spec.cuts
    in_map = {(x, y) for y in range(height) for x in range(width)}

    out_of_map = sorted(c for c in cuts if c not in in_map)
    if out_of_map:
        raise SplitError(f"map {origin}: cut cell(s) outside the map: {out_of_map}")

    entries = set(entry_cells) & in_map
    on_cut = sorted(entries & cuts)
    if on_cut:
        raise SplitError(
            f"map {origin}: cut cell(s) {on_cut} are where the player enters the map "
            "(a warp arrival or connection edge) — move the cut"
        )
    passable = {c for c in in_map if not blocked[c]} | entries
    walk_all = _flood(entries, passable)
    walk = walk_all - cuts

    # components -> pieces via seeds
    comps = _components(walk)
    comp_of = {c: i for i, comp in enumerate(comps) for c in comp}
    piece_comps: dict[int, set[int]] = {}
    for p in spec.pieces:
        for s in p.seeds:
            if s not in comp_of:
                why = "a cut cell" if s in cuts else (
                    "outside the map" if s not in in_map else "not walkable/reachable")
                raise SplitError(f"map {origin}: piece {p.k} ({p.name}) seed {s} is {why}")
            piece_comps.setdefault(p.k, set()).add(comp_of[s])
    claimed: dict[int, int] = {}
    for k, ci in sorted(piece_comps.items()):
        for i in ci:
            if i in claimed and claimed[i] != k:
                raise SplitError(
                    f"map {origin}: pieces {claimed[i]} and {k} both have seeds in one walkable "
                    f"area (around {min(comps[i], key=lambda c: (c[1], c[0]))}) — the cuts "
                    "don't separate them"
                )
            claimed[i] = k
    orphans = [i for i in range(len(comps)) if i not in claimed]
    if orphans:
        detail = ", ".join(
            f"{len(comps[i])} cells around {min(comps[i], key=lambda c: (c[1], c[0]))}"
            for i in orphans
        )
        raise SplitError(f"map {origin}: walkable area(s) with no piece seed: {detail}")

    walk_by_uid: dict[int, set[Cell]] = {}
    for i, k in claimed.items():
        walk_by_uid.setdefault(piece_uid(origin, k), set()).update(comps[i])
    owner = _ownership(walk_by_uid, width, height)

    events = list(map_json.get("events") or [])
    _check_events(events, owner, cuts, origin)

    tiles = map_json["tiles"]
    zs, xs_, ys_ = tiles["zsize"], tiles["xsize"], tiles["ysize"]
    data = tiles["data"]

    pieces: list[Piece] = []
    for p in spec.pieces:
        uid = p.uid(origin)
        mine = walk_by_uid[uid]
        visible = _dilate(mine, width, height)
        # The rectangle covers everything in view plus every event this piece
        # owns (an off-screen invisible/stripped event still needs a cell);
        # cells outside `visible` are emitted empty, so the extra area costs no art.
        my_cells = set(visible) | {(e["x"], e["y"]) for e in events
                                   if owner[(e["x"], e["y"])] == uid}
        x0 = min(x for x, _ in my_cells)
        y0 = min(y for _, y in my_cells)
        rect = Rect(x0, y0, max(x for x, _ in my_cells) - x0 + 1,
                    max(y for _, y in my_cells) - y0 + 1)
        if (rect.w + 15) * (rect.h + 14) > MAX_MAP_DATA_SIZE:
            raise SplitError(
                f"map {origin} piece {p.k}: {rect.w}x{rect.h} exceeds the engine's map "
                f"buffer ((w+15)*(h+14) > {MAX_MAP_DATA_SIZE})"
            )
        new_data = [0] * (zs * rect.h * rect.w)
        for z in range(zs):
            for ly in range(rect.h):
                for lx in range(rect.w):
                    ox, oy = rect.x0 + lx, rect.y0 + ly
                    if (ox, oy) in visible:
                        new_data[z * rect.h * rect.w + ly * rect.w + lx] = \
                            data[z * ys_ * xs_ + oy * xs_ + ox]
        my_events = [e for e in events if owner[(e["x"], e["y"])] == uid]
        outside = [e["id"] for e in my_events if not rect.contains(e["x"], e["y"])]
        if outside:
            raise SplitError(
                f"map {origin} piece {p.k}: event(s) {outside} are owned by this piece but "
                f"lie outside its rectangle {rect}"
            )
        blocked_local = sorted(
            (cx - rect.x0, cy - rect.y0) for cx, cy in cuts if rect.contains(cx, cy)
        )
        piece_json = {k: copy.deepcopy(v) for k, v in map_json.items() if k not in ("tiles", "events")}
        piece_json.update({
            "map_id": uid,
            "width": rect.w,
            "height": rect.h,
            "tiles": {"xsize": rect.w, "ysize": rect.h, "zsize": zs, "data": new_data},
            "events": [_rebase_event(e, rect) for e in my_events],
            "split": {
                "origin": origin, "k": p.k, "name": p.name,
                "x0": rect.x0, "y0": rect.y0,
                "blocked_cells": [list(c) for c in blocked_local],
            },
        })
        pieces.append(Piece(
            uid=uid, k=p.k, name=p.name, rect=rect, walk=frozenset(mine),
            visible=frozenset(visible), blocked_cells=blocked_local,
            event_ids=[e["id"] for e in my_events], map_json=piece_json,
        ))

    seams = _arrow_seams(origin, cuts, walk_by_uid, {pc.uid: pc.rect for pc in pieces})
    return SplitResult(origin=origin, pieces=pieces, seams=seams, owner=owner, cuts=cuts)


def _arrow_seams(
    origin: int, cuts: frozenset[Cell], walk_by_uid: Mapping[int, set[Cell]],
    rects: Mapping[int, Rect],
) -> list[ArrowSeam]:
    """Every cut cell with walkable cells of two different pieces on opposite
    sides becomes one reciprocal arrow pair (design §5)."""
    where = {c: uid for uid, cells in walk_by_uid.items() for c in cells}
    pairs: dict[tuple[int, int], list[tuple[Cell, Cell, str, str]]] = {}
    used: dict[Cell, Cell] = {}
    for cx, cy in sorted(cuts, key=lambda c: (c[1], c[0])):
        for d in ((1, 0), (0, 1)):
            a = (cx - d[0], cy - d[1])
            b = (cx + d[0], cy + d[1])
            ua, ub = where.get(a), where.get(b)
            if ua is None or ub is None or ua == ub:
                continue
            for cell in (a, b):
                if cell in used:
                    raise SplitError(
                        f"map {origin}: walkable cell {cell} borders two cut cells "
                        f"({used[cell]} and {(cx, cy)}) — it can't carry two arrows"
                    )
                used[cell] = (cx, cy)
            dir_a = _DIR_NAME[d]                    # a walks toward the cut
            dir_b = _DIR_NAME[(-d[0], -d[1])]       # b walks toward the cut
            if ua > ub:
                ua, ub, a, b, dir_a, dir_b = ub, ua, b, a, dir_b, dir_a
            pairs.setdefault((ua, ub), []).append((a, b, dir_a, dir_b))
    seams: list[ArrowSeam] = []
    for (ua, ub), rows in sorted(pairs.items()):
        dirs = {(r[2], r[3]) for r in rows}
        if len(dirs) != 1:
            raise SplitError(
                f"map {origin}: pieces {ua} and {ub} meet along cuts with different "
                f"crossing directions {sorted(dirs)} — one seam per piece pair"
            )
        ra, rb = rects[ua], rects[ub]
        (dir_a, dir_b), = dirs
        seams.append(ArrowSeam(
            seam_id=f"split{origin:03d}_{ua}_{ub}",
            map_a=ua, map_b=ub,
            cells_a=tuple((a[0] - ra.x0, a[1] - ra.y0) for a, _b, _da, _db in rows),
            cells_b=tuple((b[0] - rb.x0, b[1] - rb.y0) for _a, b, _da, _db in rows),
            direction_a=dir_a, direction_b=dir_b,
        ))
    return seams


# --------------------------------------------------------------------------- connections


def rebase_connection_row(
    row: list, result: SplitResult, origin_dims: tuple[int, int],
    other_dims: tuple[int, int],
) -> list:
    """Rewrite one `connections.json` row naming the split origin so it names
    the piece that owns the connection's walkable crossing (design §6). Fails
    loud if no piece, or more than one, holds walkable cells on the shared span,
    or if that piece's rectangle doesn't reach the origin's edge."""
    row = list(row)
    origin = result.origin
    side = 0 if int(row[0]) == origin else 3
    if int(row[side]) != origin:
        raise SplitError(f"connections row {row} does not name map {origin}")
    edge, off = row[side + 1], int(row[side + 2])
    other_off = int(row[3 - side + 2])
    width, height = origin_dims
    ow, oh = other_dims
    # the other map's local 0 sits at origin-local (off - other_off) along the edge
    start = off - other_off
    length = ow if edge in ("N", "S") else oh
    if edge in ("N", "S"):
        y = 0 if edge == "N" else height - 1
        span = [(x, y) for x in range(max(0, start), min(width, start + length))]
    else:
        x = 0 if edge == "W" else width - 1
        span = [(x, y) for y in range(max(0, start), min(height, start + length))]
    walk = {c: p.uid for p in result.pieces for c in p.walk}
    owners = sorted({walk[c] for c in span if c in walk})
    if len(owners) != 1:
        raise SplitError(
            f"map {origin}: connection {row} — expected exactly one piece with walkable "
            f"cells on the shared edge, found {owners}"
        )
    piece = result.piece_by_uid(owners[0])
    r = piece.rect
    touches = {"N": r.y0 == 0, "S": r.y0 + r.h == height,
               "W": r.x0 == 0, "E": r.x0 + r.w == width}[edge]
    if not touches:
        raise SplitError(
            f"map {origin}: connection {row} — piece {piece.uid}'s rectangle {r} does not "
            f"reach the {edge} edge"
        )
    row[side] = piece.uid
    row[side + 2] = off - (r.x0 if edge in ("N", "S") else r.y0)
    return row


def rewrite_transfer(params: list, results: Mapping[int, SplitResult], where: str) -> list:
    """A code-201 parameter list with a direct target into a split map, retargeted
    to the owning piece in its local frame. Anything else is returned unchanged."""
    if len(params) < 4 or params[0] != 0 or not isinstance(params[1], int):
        return params
    res = results.get(params[1])
    if res is None:
        return params
    uid, lx, ly = res.resolve(int(params[2]), int(params[3]), what=f"transfer target ({where})")
    out = list(params)
    out[1], out[2], out[3] = uid, lx, ly
    return out
