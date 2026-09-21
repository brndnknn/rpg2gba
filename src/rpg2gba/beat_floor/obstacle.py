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

One assertion per obstacle PAGE, not per scope: the capability head shows up
on the page trunk AND in branch arms (a rock's `pbRockSmashRandomEncounter`
sits in the then-arm), so `walk.floor_for_map` calls this once per page with
the trunk row id and the union of the page's scope commands.
"""
from __future__ import annotations

from typing import Any

from rpg2gba.beat_floor.assertion import FloorAssertion, FloorRefusal, make_params

# Deliberate private import (CLAUDE.md §4.3, same precedent as `terrain.py`'s
# `_generate_terrain_rows`): the generator's `_extract_page` owns capability
# detection; a second head scanner here could silently disagree with it.
from rpg2gba.chapter_manifest.generator import _extract_page


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
    capabilities = sorted(set(_extract_page(commands)["requires"]))
    if not capabilities:
        return (), ()
    if len(capabilities) > 1:
        return (), (FloorRefusal(
            row_id=row_id, reason="obstacle_multiple_capabilities", list_index=-1,
            code=None, detail=f"{row_id}: page gated on several field moves {capabilities!r}",
        ),)
    if "x" not in event or "y" not in event:
        return (), (FloorRefusal(
            row_id=row_id, reason="obstacle_missing_cell", list_index=-1, code=None,
            detail=f"{row_id}: capability {capabilities[0]!r} but event has no "
                   f"x/y (keys present: {sorted(k for k in ('x', 'y') if k in event)!r})",
        ),)
    return (FloorAssertion(
        row_id=row_id, kind="blocked_obstacle", list_index=-1, code=None,
        params=make_params(x=event["x"], y=event["y"], capability=capabilities[0]),
        tag="position",
    ),), ()
