"""In-memory model and strict serializer for a per-chapter route plan.

A route plan is the frozen output of the offline routing solver (built on top
of `pathing.py`): a walk order over a chapter's beat groups, plus the concrete
tile-level legs that connect them. It is authored/generated once per chapter
and stored on disk at ``reference/routes/<chapter_id>.route.json`` — see
`route_path`.

Mirrors `chapter_manifest.schema`'s row round-trip discipline: `plan_to_dict`/
`plan_from_dict` are both strict (CLAUDE.md §4.5) so a stale or hand-edited
file fails loud rather than silently reinterpreting itself under a newer
schema, and `chapter_manifest.dispositions`'s path convention for where the
file lives on disk.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ROUTES_DIR = Path("reference") / "routes"

Cell = tuple[int, int]

_NODE_KINDS: frozenset[str] = frozenset({"entry", "group", "exit"})
_CERTAINTIES: frozenset[str] = frozenset({"certain", "possible"})

_SCHEMA_VERSION = 1


class RoutePlanError(ValueError):
    """A route plan (or its on-disk JSON form) is malformed."""


@dataclass(frozen=True)
class RouteWarp:
    """One map-to-map hop taken by a route segment.

    `event_id` is the RMXP warp event that fires the hop, and is None for a
    `seam_warp` edge: a seam warp is an arrow-warp substituted for a map
    connection whose two maps cannot share a tileset
    (`reference/seam_warps.json`), so it has no originating event to name.
    A `connection`-kind edge never reaches here at all -- it carries no
    tile-level cells, and `pathing.plan_segment` raises on one.
    """

    event_id: int | None
    dest_map: int
    dest_cell: Cell


@dataclass(frozen=True)
class RouteLeg:
    map_id: int
    tiles: tuple[Cell, ...]  # inclusive start..end on this map, >= 1 tile
    exit_warp: RouteWarp | None = None

    def __post_init__(self) -> None:
        if not self.tiles:
            raise RoutePlanError(
                f"map {self.map_id}: RouteLeg.tiles must be non-empty"
            )


@dataclass(frozen=True)
class TriggerCrossing:
    map_id: int
    cell: Cell
    script: str
    certainty: str  # "certain" | "possible"
    declared: bool = False  # a human has explicitly accepted this crossing

    def __post_init__(self) -> None:
        if self.certainty not in _CERTAINTIES:
            raise RoutePlanError(
                f"map {self.map_id} cell {self.cell}: certainty {self.certainty!r} "
                f"is not one of {sorted(_CERTAINTIES)}"
            )


@dataclass(frozen=True)
class ChosenApproach:
    """Which SIDE of a `RouteNode`'s cell the solver chose to approach it
    from, when the beat behind that node carried more than one legal side
    (`routing.solver.RouteCandidate`, `routing.locations.ApproachCandidate`).

    `resolver` is a call an author can paste into a chapter module (for an
    `approach_to`-derived beat) or prose-as-code (for a stair beat, which has
    no paste-able `cells.py` side parameter) that pins this exact side --
    see `routing.locations.ApproachCandidate`'s docstring.
    """

    side: str
    resolver: str


@dataclass(frozen=True)
class RouteNode:
    index: int
    kind: str  # "entry" | "group" | "exit"
    map_id: int
    cell: Cell
    group: str | None = None
    beats: tuple[str, ...] = ()
    rows: tuple[str, ...] = ()  # manifest row_ids this group exercises
    chosen_approach: ChosenApproach | None = None

    def __post_init__(self) -> None:
        if self.kind not in _NODE_KINDS:
            raise RoutePlanError(
                f"node {self.index}: unknown kind {self.kind!r}; expected one of "
                f"{sorted(_NODE_KINDS)}"
            )
        if self.kind == "group":
            if self.group is None:
                raise RoutePlanError(
                    f"node {self.index}: kind 'group' requires a non-None 'group'"
                )
            if not self.beats:
                raise RoutePlanError(
                    f"node {self.index}: kind 'group' requires a non-empty 'beats'"
                )
        else:
            if self.group is not None:
                raise RoutePlanError(
                    f"node {self.index}: kind {self.kind!r} must have group=None, "
                    f"got {self.group!r}"
                )
            if self.beats != ():
                raise RoutePlanError(
                    f"node {self.index}: kind {self.kind!r} must have beats=(), "
                    f"got {self.beats!r}"
                )
            if self.chosen_approach is not None:
                raise RoutePlanError(
                    f"node {self.index}: kind {self.kind!r} must have "
                    f"chosen_approach=None, got {self.chosen_approach!r}"
                )


@dataclass(frozen=True)
class RouteSegment:
    from_index: int
    to_index: int
    legs: tuple[RouteLeg, ...]
    tile_count: int
    crossed_foreign_triggers: tuple[TriggerCrossing, ...] = ()


@dataclass(frozen=True)
class PrecedenceEdge:
    before: str  # group id
    after: str  # group id
    reason: str


@dataclass(frozen=True)
class RoutePlan:
    chapter_id: str  # "CH05"
    chapter_module: str  # "passage_cave"
    nodes: tuple[RouteNode, ...]
    segments: tuple[RouteSegment, ...]
    precedence: tuple[PrecedenceEdge, ...]
    tile_cost: int
    solver_method: str

    def __post_init__(self) -> None:
        for i, node in enumerate(self.nodes):
            if node.index != i:
                raise RoutePlanError(
                    f"{self.chapter_id}: node indices must be exactly 0..{len(self.nodes) - 1} "
                    f"in order; node at position {i} has index {node.index}"
                )
        if not self.nodes:
            raise RoutePlanError(f"{self.chapter_id}: nodes must be non-empty")
        if self.nodes[0].kind != "entry":
            raise RoutePlanError(
                f"{self.chapter_id}: first node must have kind 'entry', got "
                f"{self.nodes[0].kind!r}"
            )
        if self.nodes[-1].kind != "exit":
            raise RoutePlanError(
                f"{self.chapter_id}: last node must have kind 'exit', got "
                f"{self.nodes[-1].kind!r}"
            )

        expected_segment_count = len(self.nodes) - 1
        if len(self.segments) != expected_segment_count:
            raise RoutePlanError(
                f"{self.chapter_id}: expected {expected_segment_count} segment(s) for "
                f"{len(self.nodes)} node(s), got {len(self.segments)}"
            )
        for i, segment in enumerate(self.segments):
            if segment.from_index != i or segment.to_index != i + 1:
                raise RoutePlanError(
                    f"{self.chapter_id}: segments must chain consecutively; segment at "
                    f"position {i} has from={segment.from_index} to={segment.to_index}, "
                    f"expected from={i} to={i + 1}"
                )

        group_ids = {node.group for node in self.nodes if node.kind == "group"}
        for edge in self.precedence:
            for name in ("before", "after"):
                group_id = getattr(edge, name)
                if group_id not in group_ids:
                    raise RoutePlanError(
                        f"{self.chapter_id}: precedence edge {name}={group_id!r} does not "
                        f"name a group present in nodes ({sorted(group_ids)})"
                    )

        computed_cost = sum(segment.tile_count for segment in self.segments)
        if computed_cost != self.tile_cost:
            raise RoutePlanError(
                f"{self.chapter_id}: tile_cost {self.tile_cost} does not match the sum of "
                f"segment tile_counts ({computed_cost})"
            )


# --- serialization -----------------------------------------------------


def _cell_to_list(cell: Cell) -> list[int]:
    return [cell[0], cell[1]]


def _cell_from_list(value: Any, *, context: str) -> Cell:
    if not (isinstance(value, list) and len(value) == 2):
        raise RoutePlanError(f"{context}: expected a 2-element cell array, got {value!r}")
    x, y = value
    return (x, y)


def _warp_to_dict(warp: RouteWarp | None) -> dict[str, Any] | None:
    if warp is None:
        return None
    return {
        "event_id": warp.event_id,
        "dest_map": warp.dest_map,
        "dest_cell": _cell_to_list(warp.dest_cell),
    }


def _warp_from_dict(data: Any, *, context: str) -> RouteWarp | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise RoutePlanError(f"{context}: expected an object or null for exit_warp, got {data!r}")
    expected = {"event_id", "dest_map", "dest_cell"}
    got = set(data)
    if missing := expected - got:
        raise RoutePlanError(f"{context}: exit_warp is missing {sorted(missing)}")
    if unknown := got - expected:
        raise RoutePlanError(f"{context}: exit_warp carries unknown keys {sorted(unknown)}")
    return RouteWarp(
        event_id=data["event_id"],
        dest_map=data["dest_map"],
        dest_cell=_cell_from_list(data["dest_cell"], context=f"{context}.dest_cell"),
    )


def _leg_to_dict(leg: RouteLeg) -> dict[str, Any]:
    return {
        "map_id": leg.map_id,
        "tiles": [_cell_to_list(cell) for cell in leg.tiles],
        "exit_warp": _warp_to_dict(leg.exit_warp),
    }


def _leg_from_dict(data: Any, *, context: str) -> RouteLeg:
    if not isinstance(data, dict):
        raise RoutePlanError(f"{context}: expected an object for a leg, got {data!r}")
    expected = {"map_id", "tiles", "exit_warp"}
    got = set(data)
    if missing := expected - got:
        raise RoutePlanError(f"{context}: leg is missing {sorted(missing)}")
    if unknown := got - expected:
        raise RoutePlanError(f"{context}: leg carries unknown keys {sorted(unknown)}")
    tiles = tuple(
        _cell_from_list(cell, context=f"{context}.tiles[{i}]")
        for i, cell in enumerate(data["tiles"])
    )
    return RouteLeg(
        map_id=data["map_id"],
        tiles=tiles,
        exit_warp=_warp_from_dict(data["exit_warp"], context=f"{context}.exit_warp"),
    )


def _crossing_to_dict(crossing: TriggerCrossing) -> dict[str, Any]:
    return {
        "map_id": crossing.map_id,
        "cell": _cell_to_list(crossing.cell),
        "script": crossing.script,
        "certainty": crossing.certainty,
        "declared": crossing.declared,
    }


def _crossing_from_dict(data: Any, *, context: str) -> TriggerCrossing:
    if not isinstance(data, dict):
        raise RoutePlanError(f"{context}: expected an object for a trigger crossing, got {data!r}")
    expected = {"map_id", "cell", "script", "certainty", "declared"}
    got = set(data)
    if missing := expected - got:
        raise RoutePlanError(f"{context}: trigger crossing is missing {sorted(missing)}")
    if unknown := got - expected:
        raise RoutePlanError(f"{context}: trigger crossing carries unknown keys {sorted(unknown)}")
    return TriggerCrossing(
        map_id=data["map_id"],
        cell=_cell_from_list(data["cell"], context=f"{context}.cell"),
        script=data["script"],
        certainty=data["certainty"],
        declared=data["declared"],
    )


def _chosen_approach_to_dict(chosen: ChosenApproach | None) -> dict[str, Any] | None:
    if chosen is None:
        return None
    return {"side": chosen.side, "resolver": chosen.resolver}


def _chosen_approach_from_dict(data: Any, *, context: str) -> ChosenApproach | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise RoutePlanError(
            f"{context}: expected an object or null for chosen_approach, got {data!r}"
        )
    expected = {"side", "resolver"}
    got = set(data)
    if missing := expected - got:
        raise RoutePlanError(f"{context}: chosen_approach is missing {sorted(missing)}")
    if unknown := got - expected:
        raise RoutePlanError(f"{context}: chosen_approach carries unknown keys {sorted(unknown)}")
    return ChosenApproach(side=data["side"], resolver=data["resolver"])


def _node_to_dict(node: RouteNode) -> dict[str, Any]:
    return {
        "index": node.index,
        "kind": node.kind,
        "map_id": node.map_id,
        "cell": _cell_to_list(node.cell),
        "group": node.group,
        "beats": list(node.beats),
        "rows": list(node.rows),
        "chosen_approach": _chosen_approach_to_dict(node.chosen_approach),
    }


def _node_from_dict(data: Any, *, context: str) -> RouteNode:
    if not isinstance(data, dict):
        raise RoutePlanError(f"{context}: expected an object for a node, got {data!r}")
    required = {"index", "kind", "map_id", "cell", "group", "beats", "rows"}
    optional = {"chosen_approach"}
    got = set(data)
    if missing := required - got:
        raise RoutePlanError(f"{context}: node is missing {sorted(missing)}")
    if unknown := got - required - optional:
        raise RoutePlanError(f"{context}: node carries unknown keys {sorted(unknown)}")
    return RouteNode(
        index=data["index"],
        kind=data["kind"],
        map_id=data["map_id"],
        cell=_cell_from_list(data["cell"], context=f"{context}.cell"),
        group=data["group"],
        beats=tuple(data["beats"]),
        rows=tuple(data["rows"]),
        # `chosen_approach` is a schema addition (routing DP candidate-side
        # selection): absent on any route plan written before it existed,
        # so it defaults to None here rather than joining `required` --
        # mirrors `routing.locations.load_locations`'s back-compat `.get()`
        # discipline for the same reason (an already-committed file must
        # keep loading).
        chosen_approach=_chosen_approach_from_dict(
            data.get("chosen_approach"), context=f"{context}.chosen_approach"),
    )


def _segment_to_dict(segment: RouteSegment) -> dict[str, Any]:
    return {
        "from": segment.from_index,
        "to": segment.to_index,
        "legs": [_leg_to_dict(leg) for leg in segment.legs],
        "tile_count": segment.tile_count,
        "crossed_foreign_triggers": [
            _crossing_to_dict(c) for c in segment.crossed_foreign_triggers
        ],
    }


def _segment_from_dict(data: Any, *, context: str) -> RouteSegment:
    if not isinstance(data, dict):
        raise RoutePlanError(f"{context}: expected an object for a segment, got {data!r}")
    expected = {"from", "to", "legs", "tile_count", "crossed_foreign_triggers"}
    got = set(data)
    if missing := expected - got:
        raise RoutePlanError(f"{context}: segment is missing {sorted(missing)}")
    if unknown := got - expected:
        raise RoutePlanError(f"{context}: segment carries unknown keys {sorted(unknown)}")
    legs = tuple(
        _leg_from_dict(leg, context=f"{context}.legs[{i}]")
        for i, leg in enumerate(data["legs"])
    )
    crossings = tuple(
        _crossing_from_dict(c, context=f"{context}.crossed_foreign_triggers[{i}]")
        for i, c in enumerate(data["crossed_foreign_triggers"])
    )
    return RouteSegment(
        from_index=data["from"],
        to_index=data["to"],
        legs=legs,
        tile_count=data["tile_count"],
        crossed_foreign_triggers=crossings,
    )


def _precedence_to_dict(edge: PrecedenceEdge) -> dict[str, Any]:
    return {"before": edge.before, "after": edge.after, "reason": edge.reason}


def _precedence_from_dict(data: Any, *, context: str) -> PrecedenceEdge:
    if not isinstance(data, dict):
        raise RoutePlanError(f"{context}: expected an object for a precedence edge, got {data!r}")
    expected = {"before", "after", "reason"}
    got = set(data)
    if missing := expected - got:
        raise RoutePlanError(f"{context}: precedence edge is missing {sorted(missing)}")
    if unknown := got - expected:
        raise RoutePlanError(f"{context}: precedence edge carries unknown keys {sorted(unknown)}")
    return PrecedenceEdge(before=data["before"], after=data["after"], reason=data["reason"])


def plan_to_dict(plan: RoutePlan) -> dict[str, Any]:
    """Plain-JSON form of a route plan, per the on-disk shape documented in
    `plan.py`'s module docstring / the routing task brief."""
    return {
        "schema": _SCHEMA_VERSION,
        "_comment": [
            "Generated route plan artifact -- do not hand-edit. Produced by the "
            "offline routing solver (rpg2gba.routing) from a chapter's manifest "
            "and traversal data. Re-run the solver rather than patching this file.",
        ],
        "chapter": plan.chapter_id,
        "chapter_module": plan.chapter_module,
        "nodes": [_node_to_dict(node) for node in plan.nodes],
        "segments": [_segment_to_dict(segment) for segment in plan.segments],
        "precedence": [_precedence_to_dict(edge) for edge in plan.precedence],
        "cost": {"tiles": plan.tile_cost},
        "solver": {"method": plan.solver_method},
    }


def plan_from_dict(data: dict[str, Any]) -> RoutePlan:
    """Rebuild a `RoutePlan`, rejecting any top-level key set that is not
    exactly the expected shape (CLAUDE.md §4.5 -- mirrors
    `chapter_manifest.schema.row_from_dict`'s strictness)."""
    if not isinstance(data, dict):
        raise RoutePlanError(f"expected a JSON object for a route plan, got {type(data).__name__}")

    expected = {
        "schema", "_comment", "chapter", "chapter_module", "nodes",
        "segments", "precedence", "cost", "solver",
    }
    got = set(data)
    if missing := expected - got:
        raise RoutePlanError(f"route plan is missing {sorted(missing)}")
    if unknown := got - expected:
        raise RoutePlanError(f"route plan carries unknown keys {sorted(unknown)}")

    if data["schema"] != _SCHEMA_VERSION:
        raise RoutePlanError(
            f"route plan has schema {data['schema']!r}, expected {_SCHEMA_VERSION}"
        )

    cost = data["cost"]
    if not (isinstance(cost, dict) and set(cost) == {"tiles"}):
        raise RoutePlanError(f"route plan 'cost' must be exactly {{'tiles': <int>}}, got {cost!r}")

    solver = data["solver"]
    if not (isinstance(solver, dict) and set(solver) == {"method"}):
        raise RoutePlanError(
            f"route plan 'solver' must be exactly {{'method': <str>}}, got {solver!r}"
        )

    nodes = tuple(
        _node_from_dict(n, context=f"nodes[{i}]") for i, n in enumerate(data["nodes"])
    )
    segments = tuple(
        _segment_from_dict(s, context=f"segments[{i}]") for i, s in enumerate(data["segments"])
    )
    precedence = tuple(
        _precedence_from_dict(p, context=f"precedence[{i}]")
        for i, p in enumerate(data["precedence"])
    )

    return RoutePlan(
        chapter_id=data["chapter"],
        chapter_module=data["chapter_module"],
        nodes=nodes,
        segments=segments,
        precedence=precedence,
        tile_cost=cost["tiles"],
        solver_method=solver["method"],
    )


def write_plan(plan: RoutePlan, path: Path) -> None:
    """Serialize `plan` deterministically: `json.dumps(..., indent=2)` plus a
    trailing newline, utf-8. Byte-identical on repeated calls for the same
    plan -- every collection in `plan_to_dict` is already ordered (tuples
    preserve insertion order; nothing here iterates a set or dict whose order
    is not itself derived from an ordered field)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(plan_to_dict(plan), indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
    logger.info("wrote route plan for %s to %s", plan.chapter_id, path)


def load_plan(path: Path) -> RoutePlan:
    """Load and strictly parse a route plan from `path`."""
    with path.open(encoding="utf-8") as f:
        try:
            raw = json.load(f)
        except json.JSONDecodeError as exc:
            raise RoutePlanError(f"{path}: invalid JSON: {exc}") from exc
    try:
        return plan_from_dict(raw)
    except RoutePlanError as exc:
        raise RoutePlanError(f"{path}: {exc}") from exc


def route_path(chapter_id: str, *, root: Path | None = None) -> Path:
    """Path convention: ``reference/routes/<chapter_id>.route.json`` (mirrors
    `chapter_manifest.dispositions.disposition_path`)."""
    base = root if root is not None else ROUTES_DIR
    return base / f"{chapter_id}.route.json"
