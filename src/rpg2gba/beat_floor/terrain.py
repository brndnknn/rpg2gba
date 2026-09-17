"""Row-level floors for the two manifest row kinds with no command list
(REDERIVATION_PLAN.md §16.3 C5): `seam` rows (overland connections) and
`terrain` rows (diagonal-stair cells, absorbed from their RMXP event).

Neither kind has a page to walk, so neither goes through `walk.py`'s
per-command dispatch. Each gets exactly one row-level assertion --
`seam_crossing` or `stair_crossing` -- built straight from the same fields
`chapter_manifest.generator` already derived for the manifest row itself
(`SeamRef`/`TerrainRef`), so the row SET and row IDS this module produces are
exactly what the generator emits: `_generate_seam_rows`/`_generate_terrain_rows`
are called directly, never re-implemented (CLAUDE.md §4.3, §4.7 "verify
against the real fork" applied to our own generator instead).

A stair row's `steps` are the one piece of information `TerrainRef` does not
carry (it only has the cell's resolved `behavior`, not the player's facing
branch or move-route displacement) -- `derive_stair_steps` recovers that from
the RMXP source event directly (never from converted Poryscript, per R11's
proxy-oracle rule), by parsing the stair idiom's own control-flow shape: one
code-111 player-facing branch (condition kind 6, character -1) whose `then`
arm is the branch's own tested facing and whose `else` arm is that facing's
compass complement, each arm's own diagonal move-route commands summing to
that arm's net (dx, dy).
"""

from __future__ import annotations

from typing import Any

from rpg2gba.beat_floor.assertion import FloorAssertion, FloorRefusal, RowFloor, make_params
from rpg2gba.chapter_manifest.generator import (
    _flatten_scope,
    _generate_seam_rows,
    _generate_terrain_rows,
    detect_stair_cells,
)
from rpg2gba.conversion_agent.transpiler import IfNode, parse_tree
from rpg2gba.tileset_converter.stairs import _page_qualifies

# --- stair-idiom constants (mirrors `tileset_converter.stairs`'s own reading
# of the idiom; the classification itself -- which cells are stairs at all,
# and which `StairSide` each gets -- is never re-derived here, only imported
# via `detect_stair_cells`/`_generate_terrain_rows`). --------------------

_CONDITION_KIND_CHARACTER_DIRECTION = 6
_CONDITION_CHARACTER_PLAYER = -1
_MOVE_ROUTE_CODES = (205, 209)
_MOVE_ROUTE_TARGET_PLAYER = -1

# RMXP facing values -> the step direction a code-111 type-6 branch tests.
_STEP_DIR_BY_FACING: dict[int, str] = {2: "DOWN", 4: "LEFT", 6: "RIGHT", 8: "UP"}
# Each facing's compass complement -- what the branch's `else` arm implicitly
# tests, since the idiom is always a binary (this-facing / not-this-facing)
# split between two opposite directions on one axis.
_COMPLEMENT_FACING: dict[int, int] = {2: 8, 8: 2, 4: 6, 6: 4}
# RMXP diagonal move-route codes -> net (dx, dy), matching
# `tileset_converter.stairs`'s own module docstring exactly (5 SW, 6 SE,
# 7 NW, 8 NE).
_MOVE_DELTA: dict[int, tuple[int, int]] = {5: (-1, 1), 6: (1, 1), 7: (-1, -1), 8: (1, -1)}


def _find_stair_page(event: dict[str, Any]) -> dict[str, Any] | None:
    """The event's page carrying the stair idiom, or None.

    Reuses `stairs._page_qualifies` (trigger==player-touch, contains a
    code-111 character-direction branch on the player) rather than
    re-implementing the shape check -- the same rule `detect_stair_cells`
    used to decide this event is a stair cell in the first place.
    """
    for page in event.get("pages", []) or []:
        if _page_qualifies(page):
            return page
    return None


def _diagonal_delta(commands: list[dict[str, Any]]) -> tuple[int, int]:
    """Net (dx, dy) of every player-targeted diagonal move-route command in
    `commands`. Zero when the arm has none (e.g. the bottom-of-stair cell's
    "facing into the stair" arm does nothing further -- see Map033 ev026's
    empty `then` arm)."""
    dx = dy = 0
    for cmd in commands:
        if cmd.get("code") not in _MOVE_ROUTE_CODES:
            continue
        params = cmd.get("parameters") or []
        if len(params) < 2 or params[0] != _MOVE_ROUTE_TARGET_PLAYER:
            continue
        move_route = params[1] or {}
        for move_cmd in move_route.get("list") or []:
            delta = _MOVE_DELTA.get(move_cmd.get("code"))
            if delta is not None:
                dx += delta[0]
                dy += delta[1]
    return dx, dy


def derive_stair_steps(
    event: dict[str, Any],
) -> tuple[tuple[tuple[str, int, int], ...], str | None]:
    """`(steps, refusal_reason)` for one stair event's RMXP source.

    `steps` is `()` and `refusal_reason` is a stable snake_case id whenever
    the event's source does not match the exact idiom this function knows how
    to read -- never a guess (CLAUDE.md §4.5)."""
    page = _find_stair_page(event)
    if page is None:
        return (), "stair_no_qualifying_page"

    commands = page.get("list") or []
    tree = parse_tree(commands)

    branch_nodes: list[IfNode] = []
    for node in tree:
        if not isinstance(node, IfNode):
            continue
        params = node.cmd.get("parameters") or []
        if (
            len(params) >= 3
            and params[0] == _CONDITION_KIND_CHARACTER_DIRECTION
            and params[1] == _CONDITION_CHARACTER_PLAYER
        ):
            branch_nodes.append(node)

    if len(branch_nodes) != 1:
        return (), "stair_branch_not_singular"

    node = branch_nodes[0]
    direction = node.cmd["parameters"][2]
    if direction not in _STEP_DIR_BY_FACING:
        return (), "stair_unknown_facing_direction"

    then_dir = direction
    else_dir = _COMPLEMENT_FACING[direction]
    then_commands = _flatten_scope(node.then, commands)
    else_nodes = node.otherwise if node.otherwise is not None else []
    else_commands = _flatten_scope(else_nodes, commands)

    then_dx, then_dy = _diagonal_delta(then_commands)
    else_dx, else_dy = _diagonal_delta(else_commands)

    steps = tuple(sorted((
        (_STEP_DIR_BY_FACING[then_dir], then_dx, then_dy),
        (_STEP_DIR_BY_FACING[else_dir], else_dx, else_dy),
    )))
    return steps, None


def seam_floors_for_map(
    map_id: int, connections: list[list[Any]],
) -> dict[str, RowFloor]:
    """Every `seam_crossing` `RowFloor` for `map_id`'s own side of each
    overland connection touching it, via `generator._generate_seam_rows` --
    the same enumeration `chapter_manifest.generator` uses, so the row set
    and row ids agree by construction."""
    rows = _generate_seam_rows({map_id}, connections, {map_id: False})
    result: dict[str, RowFloor] = {}
    for row in rows:
        seam = row.seam
        assert seam is not None
        assertion = FloorAssertion(
            row_id=row.row_id, kind="seam_crossing", list_index=-1, code=None,
            params=make_params(
                map_id=seam.map_id, direction=seam.direction, offset=seam.offset,
                other_map_id=seam.other_map_id, other_direction=seam.other_direction,
                other_offset=seam.other_offset,
            ),
            tag="position",
        )
        result[row.row_id] = RowFloor(
            row_id=row.row_id, trigger="seam",
            assertions=frozenset({assertion}), refusals=(),
        )
    return result


def stair_floors_for_map(map_id: int, map_data: dict[str, Any]) -> dict[str, RowFloor]:
    """Every `stair_crossing` `RowFloor` for `map_id`'s diagonal-stair cells,
    via `generator._generate_terrain_rows` over `detect_stair_cells` -- the
    same detection/enumeration the generator itself uses, so the row set and
    row ids agree by construction. A cell whose source event doesn't match the
    exact stair idiom (`derive_stair_steps`) gets a `FloorRefusal` instead of
    an assertion."""
    stair_cells = detect_stair_cells(map_data)
    rows = _generate_terrain_rows(map_id, stair_cells, reachability_consulted=False)
    events_by_id = {e["id"]: e for e in (map_data.get("events") or []) if e}

    result: dict[str, RowFloor] = {}
    for row in rows:
        terrain = row.terrain
        assert terrain is not None
        event = events_by_id.get(terrain.source_event_id)
        if event is None:
            result[row.row_id] = RowFloor(
                row_id=row.row_id, trigger="player_touch", assertions=frozenset(),
                refusals=(FloorRefusal(
                    row_id=row.row_id, reason="stair_missing_source_event",
                    list_index=-1, code=None,
                    detail=(
                        f"map {map_id} terrain row cites event "
                        f"{terrain.source_event_id}, absent from this map's events"),
                ),),
            )
            continue

        steps, reason = derive_stair_steps(event)
        if reason is not None:
            result[row.row_id] = RowFloor(
                row_id=row.row_id, trigger="player_touch", assertions=frozenset(),
                refusals=(FloorRefusal(
                    row_id=row.row_id, reason=reason, list_index=-1, code=111,
                    detail=(
                        f"map {map_id} event {terrain.source_event_id} "
                        f"({event.get('name')!r}): {reason}"),
                ),),
            )
            continue

        assertion = FloorAssertion(
            row_id=row.row_id, kind="stair_crossing", list_index=-1, code=None,
            params=make_params(
                x=terrain.x, y=terrain.y, side=_side_value(row, stair_cells),
                steps=steps,
            ),
            tag="position",
        )
        result[row.row_id] = RowFloor(
            row_id=row.row_id, trigger="player_touch",
            assertions=frozenset({assertion}), refusals=(),
        )
    return result


def _side_value(row: Any, stair_cells: list[Any]) -> str:
    """`StairSide.value` ("left"|"right") for `row`'s terrain cell, read off
    the same `StairCell` list `_generate_terrain_rows` was built from -- never
    re-derived from `TerrainRef.behavior`, which is the pokeemerald constant
    name, not the `StairSide` enum."""
    terrain = row.terrain
    for cell in stair_cells:
        if cell.event_id == terrain.source_event_id and cell.x == terrain.x and cell.y == terrain.y:
            return cell.side.value
    raise ValueError(
        f"terrain row {row.row_id!r}: no matching StairCell for event "
        f"{terrain.source_event_id} at ({terrain.x},{terrain.y})")
