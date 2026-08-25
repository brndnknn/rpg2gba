"""Phase 5 §5.4 — Map connections (overworld adjacency).

INPUT: `output/uranium-build/connections.json`, a JSON list of 6-element rows
`[map_a, edge_a, offset_a, map_b, edge_b, offset_b]`. This is a straight JSON
dump of Uranium's RGSS `Data/connections.dat` (see `scripts/map_graph.py`,
which already consumes the same file for the map viewer and cites its
source: Essentials' `107__PField_Map.rb` `getMapConnections`/`getMapEdge`).
It is NOT `parent_id` (the RMXP editor tree) and NOT derived from geometry or
region-map position — it is Uranium's own borderless-seam data, already
correct; our only job is a format translation into pokeemerald's per-map
`connections` schema.

ROW SEMANTICS — worked derivation
==================================
`edge_a`/`edge_b` are single-letter compass directions ("N"/"S"/"E"/"W") for
THAT map's own border the seam sits on (not a direction of travel). Essentials
locates an anchor point on that edge from (edge, offset):

    N -> (offset, 0)             S -> (offset, height)
    W -> (0, offset)             E -> (width, offset)

The two anchors — one per map, each in that map's own local grid — name the
SAME point in world space; that is what "connected" means. This is a
different quantity than pokeemerald's per-map `offset` field, and treating
row[2]/row[5] as if they were already pokeemerald offsets (row_a's offset
straight into map_a's entry, row_b's negated into map_b's) is the trap: it
only happens to hold when the OTHER map's raw offset is 0. `[31,"N",11,35,
"S",0]` (the CH04 seam) is deceptively close to that degenerate case; a row
like `[142,"E",0,87,"W",7]` — nonzero on the far side — is not, and would
silently misalign the seam if row_b were just negated.

`engine/src/fieldmap.c`'s `FillNorthConnection`/`FillSouthConnection`/
`FillWestConnection`/`FillEastConnection` all place the CONNECTED map's local
column/row 0 at THIS map's local column/row = the connection's `offset`
field (independent of which direction the connection is; confirmed by
reading the four `Fill*Connection` bodies, which share the identical
`x = offset + MAP_OFFSET` / `x2 = 0` structure). So the pokeemerald offset
we need is: the world displacement of map_b's local (0,0), expressed in
map_a's frame, along the shared axis. For every edge, the anchor's
shared-axis coordinate IS the raw offset itself (N/S store it as the x
component, E/W as the y component; the other component is the fixed
0/width/height and cancels out of the subtraction). The derivation collapses
to one line, always:

    offset_poke(map_a's entry, -> map_b) = offset_a - offset_b
    offset_poke(map_b's entry, -> map_a) = offset_b - offset_a   (negation)

This was cross-checked against real vendored vanilla pairs with UNEQUAL
widths and nonzero offsets on both sides (`engine/data/maps/Route112/
map.json` "offset": -60 up -> Route113, `Route113/map.json` "offset": 60
down -> Route112) — the two pokeemerald-format offsets of one seam are
always plain negatives of each other, confirming the formula above rather
than a width-scaled one.

Worked example — the CH04 acceptance seam, row `[31,"N",11,35,"S",0]`
(Map031 height/width irrelevant here; Map035 height = 57, read from
`output/uranium-build/maps/Map035.json`):

    anchor31 = (11, 0)     map31's N edge, Essentials convention
    anchor35 = (0, 57)     map35's S edge (57 = Map035's height)
    map31 "up"   entry -> MAP_ROUTE_02,    offset = 11 - 0  = 11
    map35 "down" entry -> MAP_KEVLAR_TOWN, offset = 0  - 11 = -11

Sanity check against `FillNorthConnection`: on the owning map (map31,
offset=11), local column (11+k) draws the connected map's (map35) local
column k, i.e. map31_col(x) = map35_col(x - 11). Inverting: map35_col(y) =
map31_col(y + 11). Applying the identical `Fill*Connection` formula from
map35's side (a south connection, offset=o): map35_col(x) =
map31_col(x - o); matching the inverted relation forces o = -11. Both
directions of the single row's math agree. This offset sign has NOT been
confirmed by an in-ROM walk (only the arithmetic above and the vanilla
cross-check) — flagged in the report.

Direction-letter mapping (Essentials edge -> pokeemerald `direction`):
    N -> "up", S -> "down", W -> "left", E -> "right"
(`up`=north, `down`=south, `left`=west, `right`=east — matches every
vendored fork map.json and the `OPPOSITE` table below.)

FRONTIER RULE
=============
A row is only emitted when BOTH `map_a` and `map_b` are in the build's map
set (`SLICE_MAP_IDS`, or whatever id set the caller passes). A seam to a
map that isn't staged yet is omitted, not dangled — logged at INFO naming
the row and the missing id(s), mirroring `metadata_wiring.classify_event`'s
`("skip", "out-of-slice warp")` frontier behaviour
(`reference/guides/slice_expansion_runbook.md`).

FAIL LOUD on: a malformed row (wrong length/types), an edge letter outside
N/S/E/W, a row whose two edges aren't opposite (N<->S or E<->W — anything
else can't form a straight seam and isn't representable by this schema), a
map id with no minted `MAP_*` constant, or two rows naming the same
unordered map pair (duplicate or contradictory — a seam should appear in
the source exactly once).
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# pokeemerald connection directions + their opposites (for the consistency check).
OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}

# Essentials edge letter -> pokeemerald connection direction.
EDGE_TO_DIRECTION = {"N": "up", "S": "down", "W": "left", "E": "right"}

# An edge only forms a straight seam with its geometric opposite.
EDGE_OPPOSITE = {"N": "S", "S": "N", "E": "W", "W": "E"}


@dataclass(frozen=True)
class Connection:
    """One directed edge: this map connects `direction` to `dest_map` at `offset`."""

    direction: str  # "up" | "down" | "left" | "right"
    dest_map: str  # MAP_* constant
    offset: int


@dataclass(frozen=True)
class ConnectionRow:
    """One parsed `connections.json` row (Essentials seam-edge format, see module
    docstring) — NOT yet in pokeemerald's offset convention."""

    map_a: int
    edge_a: str
    offset_a: int
    map_b: int
    edge_b: str
    offset_b: int

    @property
    def pair_key(self) -> frozenset[int]:
        return frozenset((self.map_a, self.map_b))


def _fail(msg: str, row_index: int, raw: object) -> None:
    raise ValueError(f"connections.json row {row_index} ({raw!r}): {msg}")


def parse_connections(raw_rows: list) -> list[ConnectionRow]:
    """Validate + parse raw `connections.json` rows into `ConnectionRow`s.

    Fails loud on: wrong row length/shape, non-integer map ids/offsets, an
    edge letter outside N/S/E/W, or a row whose two edges aren't opposite
    (can't form a straight seam)."""
    rows: list[ConnectionRow] = []
    for i, raw in enumerate(raw_rows):
        if not isinstance(raw, list | tuple) or len(raw) != 6:
            _fail("expected a 6-element [map_a, edge_a, offset_a, map_b, edge_b, offset_b] row", i, raw)
        map_a, edge_a, offset_a, map_b, edge_b, offset_b = raw
        for label, val in (("map_a", map_a), ("offset_a", offset_a), ("map_b", map_b), ("offset_b", offset_b)):
            if not isinstance(val, int) or isinstance(val, bool):
                _fail(f"{label}={val!r} is not an int", i, raw)
        for label, edge in (("edge_a", edge_a), ("edge_b", edge_b)):
            if edge not in EDGE_TO_DIRECTION:
                _fail(f"{label}={edge!r} is not one of N/S/E/W", i, raw)
        if EDGE_OPPOSITE[edge_a] != edge_b:
            _fail(f"edges {edge_a!r}/{edge_b!r} aren't opposite (N<->S or E<->W) — not a straight seam", i, raw)
        rows.append(ConnectionRow(map_a, edge_a, offset_a, map_b, edge_b, offset_b))
    return rows


def load_connections(path: Path) -> list[ConnectionRow]:
    """Load + parse `connections.json` from *path*."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return parse_connections(raw)


def _check_duplicates(rows: list[ConnectionRow]) -> None:
    seen: dict[frozenset[int], ConnectionRow] = {}
    for row in rows:
        prior = seen.get(row.pair_key)
        if prior is not None:
            raise ValueError(
                f"duplicate/contradictory connection rows for map pair "
                f"{sorted(row.pair_key)}: {prior} and {row}"
            )
        seen[row.pair_key] = row


def build_connections(
    rows: list[ConnectionRow],
    map_ids: set[int],
    resolve_map_const: Callable[[int], str],
) -> dict[str, list[Connection]]:
    """Build pokeemerald connections for every row whose BOTH endpoints are in
    *map_ids* (the frontier rule — a seam to an unstaged map is omitted and
    logged at INFO, never dangled).

    Returns `{MAP_* const: [Connection, ...]}`. `resolve_map_const(uid)` must
    raise (KeyError/ValueError) for an unminted id — that failure propagates
    unchanged (fail loud, rule 4). Fails loud on any duplicate/contradictory
    row for the same unordered map pair, checked BEFORE frontier filtering so
    a bad row in the source is never silently dropped as "out of slice".
    Deterministic: each map's connection list is sorted, so repeated calls on
    the same input are byte-identical (idempotence, rule 5)."""
    _check_duplicates(rows)

    result: dict[str, list[Connection]] = {}
    for row in rows:
        missing = [m for m in (row.map_a, row.map_b) if m not in map_ids]
        if missing:
            logger.info(
                "omitting connection row %s: map(s) %s not in this build's map set",
                (row.map_a, row.edge_a, row.offset_a, row.map_b, row.edge_b, row.offset_b),
                missing,
            )
            continue

        try:
            const_a = resolve_map_const(row.map_a)
        except (KeyError, ValueError) as exc:
            raise ValueError(f"connection row {row}: map {row.map_a} has no MAP_* constant") from exc
        try:
            const_b = resolve_map_const(row.map_b)
        except (KeyError, ValueError) as exc:
            raise ValueError(f"connection row {row}: map {row.map_b} has no MAP_* constant") from exc

        offset_a = row.offset_a - row.offset_b
        offset_b = -offset_a

        conn_a = Connection(direction=EDGE_TO_DIRECTION[row.edge_a], dest_map=const_b, offset=offset_a)
        conn_b = Connection(direction=EDGE_TO_DIRECTION[row.edge_b], dest_map=const_a, offset=offset_b)
        result.setdefault(const_a, []).append(conn_a)
        result.setdefault(const_b, []).append(conn_b)

    for const in result:
        result[const].sort(key=lambda c: (c.direction, c.dest_map, c.offset))
    return result


def check_bidirectional(connections_by_map: dict[str, list[Connection]]) -> list[str]:
    """Return a list of inconsistencies: any A->B edge whose reverse B->A is missing
    or has a non-negated offset. Empty list == consistent."""
    problems: list[str] = []
    for map_const, conns in connections_by_map.items():
        for conn in conns:
            reverse_list = connections_by_map.get(conn.dest_map, [])
            match = next(
                (
                    r
                    for r in reverse_list
                    if r.dest_map == map_const and r.direction == OPPOSITE[conn.direction]
                ),
                None,
            )
            if match is None:
                problems.append(
                    f"{map_const} -{conn.direction}-> {conn.dest_map} (offset {conn.offset}) "
                    f"has no reverse entry on {conn.dest_map}"
                )
            elif match.offset != -conn.offset:
                problems.append(
                    f"{map_const} -{conn.direction}-> {conn.dest_map} (offset {conn.offset}) "
                    f"vs reverse offset {match.offset} (expected {-conn.offset})"
                )
    return problems


def connections_json(conns: list[Connection]) -> list[dict]:
    """Render a map's `Connection` list into the exact `map.json` `connections`
    array shape (`[{"map": ..., "offset": ..., "direction": ...}, ...]`)."""
    return [{"map": c.dest_map, "offset": c.offset, "direction": c.direction} for c in conns]


def build_slice_connections(
    connections_path: Path,
    map_ids: list[int] | set[int],
    resolve_map_const: Callable[[int], str],
) -> dict[int, list[dict]]:
    """Top-level entry point: load `connections.json`, apply the frontier rule
    against *map_ids*, verify bidirectional consistency, and return
    `{uranium_map_id: connections_json(...)}` — ONLY for maps that ended up
    with at least one emitted connection (a map with none is simply absent;
    callers should `.get(uid)` and treat a miss as "no connections", the
    `MapFile.connections` default). Fails loud (via `build_connections`'
    duplicate/malformed/unresolvable checks, or an internal consistency
    AssertionError) rather than emit a partial or wrong result."""
    rows = load_connections(connections_path)
    by_const = build_connections(rows, set(map_ids), resolve_map_const)

    problems = check_bidirectional(by_const)
    if problems:
        raise AssertionError("connection bidirectional-consistency check failed:\n" + "\n".join(problems))

    const_to_uid = {resolve_map_const(uid): uid for uid in map_ids}
    out: dict[int, list[dict]] = {}
    for map_const, conns in by_const.items():
        uid = const_to_uid.get(map_const)
        if uid is None:
            # Shouldn't happen: build_connections only emits for ids in map_ids,
            # so every key must resolve back — fail loud if the const map is
            # somehow inconsistent (e.g. a resolver that isn't a stable function).
            raise AssertionError(f"connection result named {map_const!r}, which isn't in map_ids")
        out[uid] = connections_json(conns)
    return out
