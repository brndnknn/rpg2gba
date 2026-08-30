"""Offline per-chapter route planning — turns a chapter's beat groups into a
frozen, tile-level walk order.

Two data provenances feed this, deliberately:

* `plan` is the artifact model + strict serializer for the frozen output
  (`reference/routes/<chapter_id>.route.json`) — no traversal logic lives
  here, only the shape and the round trip.
* `pathing` is tile-level BFS with an avoid-set (a chapter's own foreign
  trigger tiles) plus the cross-map stitching glue that turns a `WorldGraph`
  hop sequence into concrete `RouteLeg`s.
* `solver` is the offline solver itself: `Chapter` (beats/groups) +
  `ManifestRow`s (for precedence) in, a validated `RoutePlan` out.

Public API::

    solve_route(chapter, chapter_id, *, manifest_rows, graphs, overlays, ...) -> RoutePlan

    path_avoiding(graph, start, goal, avoid) -> list[Cell] | None
    plan_segment(start_map, start_cell, goal_map, goal_cell, *, graphs, overlays,
                 destination_scripts, world=None) -> SegmentResult

    RoutePlan, RouteNode, RouteSegment, RouteLeg, RouteWarp, PrecedenceEdge,
    TriggerCrossing, RoutePlanError
    plan_to_dict, plan_from_dict, write_plan, load_plan, route_path
"""
from .pathing import RoutePlanningError, SegmentResult, path_avoiding, plan_segment
from .plan import (
    PrecedenceEdge,
    RouteLeg,
    RouteNode,
    RoutePlan,
    RoutePlanError,
    RouteSegment,
    RouteWarp,
    TriggerCrossing,
    load_plan,
    plan_from_dict,
    plan_to_dict,
    route_path,
    write_plan,
)
from .solver import RouteSolverError, solve_route

__all__ = [
    # plan
    "PrecedenceEdge",
    "RouteLeg",
    "RouteNode",
    "RoutePlan",
    "RoutePlanError",
    "RouteSegment",
    "RouteWarp",
    "TriggerCrossing",
    "load_plan",
    "plan_from_dict",
    "plan_to_dict",
    "route_path",
    "write_plan",
    # pathing
    "RoutePlanningError",
    "SegmentResult",
    "path_avoiding",
    "plan_segment",
    # solver
    "RouteSolverError",
    "solve_route",
]
