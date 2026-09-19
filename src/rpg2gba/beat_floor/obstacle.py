"""`blocked_obstacle`: a row whose own commands are gated on a field move
(REDERIVATION_PLAN.md §16.3 C7 residue ruling, 2026-09-18).

The assertion reads: *without `<capability>`, interacting with this event
leaves it in place (no erase, no state write), and its tile at `(x, y)` stays
impassable.* It is the negative twin of the `visual` placeholders
`condition._extract_pb_rock_smash` / `script`'s `pbPushThisBoulder` emit,
which describe what happens WITH the capability. Both are true; keep both.

Which rows are obstacles is decided by ONE detector, the manifest
generator's `_extract_page(commands)["requires"]` (built from
`generator._HEAD_REQUIRES`). Never a manifest row's `requires` field: that
one also carries reachability-derived capabilities for events standing
*behind* an obstacle (`assignments/C7/03_blocked_obstacle.md`, "The trap").

STATUS: stub (`assignments/C7/03_blocked_obstacle.md`, R2).
"""
from __future__ import annotations

from typing import Any

from rpg2gba.beat_floor.assertion import FloorAssertion, FloorRefusal


def obstacle_assertions(
    row_id: str, event: dict[str, Any], commands: list[dict[str, Any]],
) -> tuple[tuple[FloorAssertion, ...], tuple[FloorRefusal, ...]]:
    """Zero or one `blocked_obstacle` assertion for one scope.

    - no capability head in `commands`  -> ((), ())
    - exactly one capability            -> one assertion: list_index -1,
                                           code None, params x, y (the
                                           event's cell), capability;
                                           tag "position"
    - more than one capability          -> refuse ("obstacle_multiple_capabilities")
    - capability but no x or y on event -> refuse ("obstacle_missing_cell")
    """
    raise NotImplementedError
