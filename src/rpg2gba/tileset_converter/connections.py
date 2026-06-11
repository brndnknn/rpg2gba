"""Phase 5 §5.4 — Map connections (overworld adjacency).

ASSIGNMENT
==========
Objective
    Produce pokeemerald map `connections` — which map borders which, in which
    direction, at what offset — for the overworld maps.

THE TRAP (read this before writing code)
    `map_infos.json`'s `parent_id` is only the RMXP *editor tree* (how the maps
    were organized in the editor), NOT spatial adjacency. RMXP has no first-class
    "connections" concept the way pokeemerald does: in RMXP the player moves
    between maps via warp/transfer events, and the overworld is a set of separate
    maps. So you CANNOT derive real adjacency from parent_id.

    Real adjacency has to come from one of:
      - region-map coordinates (map_metadata MapPosition = [region, x, y]) — maps
        whose region tiles are edge-adjacent are candidates for a connection;
      - or manual wiring against Uranium's overworld map (ROADMAP §5.4 explicitly
        allows manual Porymap work here).

    Treat full automation as a STRETCH GOAL. A correct first pass may wire only
    the high-confidence route<->town adjacencies (e.g. inferred from MapPosition)
    and emit a documented worklist of everything left for manual wiring. Fail loud
    / list explicitly — do NOT silently emit a wrong or empty connection.

Inputs
    map_infos.json (names + the misleading parent_id tree),
    intermediate/map_metadata.json (MapPosition per map),
    the MapConstantRegistry (to name connection targets), warp targets (cross-check).
Output
    `connections` arrays merged into each map.json + group ordering hints for
    map_groups.json.

Constraints
    - No connection references a non-existent MAP_* (fail loud).
    - Offsets consistent both directions: A connects up to B  <=>  B connects
      down to A, with negated offset.

Acceptance
    [ ] no connection -> a non-existent MAP_*
    [ ] bidirectional consistency (up/down, left/right, offsets negate)
    [ ] a documented list of maps left for manual wiring (explicit, not silent)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# pokeemerald connection directions + their opposites (for the consistency check).
OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}


@dataclass(frozen=True)
class Connection:
    """One directed edge: this map connects `direction` to `dest_map` at `offset`."""

    direction: str  # "up" | "down" | "left" | "right"
    dest_map: str  # MAP_* constant
    offset: int


def infer_connections(
    uranium_id: int,
    map_metadata: dict,
    resolve_map: "callable",
) -> list[Connection]:
    """Best-effort adjacency for one map from region-map MapPosition (Q-stretch).

    Compare this map's MapPosition rectangle against its neighbors'; emit a
    Connection for each shared edge. Low confidence by nature — only emit edges
    you're sure of, and let `manual_worklist()` collect the rest."""
    raise NotImplementedError("5.4: infer high-confidence adjacency from MapPosition")


def check_bidirectional(connections_by_map: dict[str, list[Connection]]) -> list[str]:
    """Return a list of inconsistencies: any A->B edge whose reverse B->A is missing
    or has a non-negated offset. Empty list == consistent."""
    raise NotImplementedError("5.4: verify A->B implies B->A with negated offset")


def manual_worklist(all_map_ids: list[int], wired: set[int]) -> list[int]:
    """The maps with no auto-inferred connection — the explicit hand-wiring list
    (ROADMAP §5.4 allows manual Porymap work). Surface it, never swallow it."""
    return [m for m in all_map_ids if m not in wired]
