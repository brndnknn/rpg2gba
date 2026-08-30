"""Offline traversal model — single source of truth for "where can the player
walk on map N", "what fires if they step there", and "what would unblock a
cell they cannot reach". No ROM, no emulator.

Two data provenances live here, deliberately:

* `graph`/`collision`/`ledges`/`warps`/`world` read **decoded RMXP data**
  (`output/uranium-build/`) — the source game's own geometry.
* `triggers` reads the **emitted pokeemerald data** (`engine/data/maps/`),
  because trigger geometry is a property of what shipped, not of what
  RPG Maker meant. pokeemerald has no event-touch analogue at all, so an
  RMXP-derived trigger model would predict tiles the ROM does not have and
  miss the sight lines it does (see `triggers.py` for the engine citations).

`capabilities` spans both: obstacle events come from RMXP event scripts,
while surf/waterfall gates exist only as terrain tags.

Public API::

    build_map_graph(map_id, ...) -> MapGraph
    MapGraph.is_walkable(cell) -> bool
    MapGraph.neighbors(cell) -> list[Edge]
    MapGraph.reachable_from(start) -> set[Cell]
    MapGraph.shortest_path(start, goal) -> list[Cell] | None
    MapGraph.connected_components() -> list[set[Cell]]

    build_trigger_overlay(map_id, graph=...) -> TriggerOverlay
    TriggerOverlay.certain_tiles() / .possible_tiles() / .foreign_tiles(scripts)

    build_capability_map(map_id, ...) -> CapabilityMap
    CapabilityMap.capability_at(cell) -> Capability | None
"""
from __future__ import annotations

from .capabilities import (
    PREDICATES,
    VERIFIED_CAPABILITIES,
    Capability,
    CapabilityMap,
    CapabilityPredicate,
    Obstacle,
    UnverifiedCapabilityError,
    build_capability_map,
)
from .direction import CARDINALS, Direction
from .graph import Cell, Edge, MapGraph, build_map_graph
from .ledges import derive_ledge_direction, load_ledge_direction_overrides
from .reachability import (
    BlockedVerdict,
    PermanentlyUnstandableGoalError,
    adjacent_approach_cells,
    derive_blocked_verdict,
    derive_blocked_verdict_for_event,
    is_reachable_with,
    minimal_capability_sets,
    reachable_with,
)
from .triggers import (
    Certainty,
    TriggerKind,
    TriggerOverlay,
    TriggerRef,
    build_trigger_overlay,
)
from .warps import WarpExit, extract_warp_exits

__all__ = [
    "CARDINALS",
    "Direction",
    "Cell",
    "Edge",
    "MapGraph",
    "build_map_graph",
    "derive_ledge_direction",
    "load_ledge_direction_overrides",
    "WarpExit",
    "extract_warp_exits",
    # trigger overlay
    "Certainty",
    "TriggerKind",
    "TriggerOverlay",
    "TriggerRef",
    "build_trigger_overlay",
    # capabilities
    "Capability",
    "CapabilityMap",
    "CapabilityPredicate",
    "Obstacle",
    "PREDICATES",
    "UnverifiedCapabilityError",
    "VERIFIED_CAPABILITIES",
    "build_capability_map",
    # capability-tagged reachability
    "BlockedVerdict",
    "PermanentlyUnstandableGoalError",
    "adjacent_approach_cells",
    "derive_blocked_verdict",
    "derive_blocked_verdict_for_event",
    "is_reachable_with",
    "minimal_capability_sets",
    "reachable_with",
]
