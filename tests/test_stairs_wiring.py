"""Tests for the diagonal-stair wiring in `metadata_wiring.py`.

Covers the fix for the shipped-ROM bug where Route 1's diagonal staircases
(Map033 (57,9)/(57,10)/(57,11)) read as solid walls: `collect_through_block_cells`
used to classify every RMXP diagonal-stair "player touch" event (blank
graphic, through=False) as an invisible obstacle and force-block its cell.
The approved fix drops the RMXP script entirely and uses pokeemerald-
expansion's native sideways-stairs metatile behaviors on a passable tile
instead (see `rpg2gba.tileset_converter.stairs`), so a stair event must:

  - contribute NO cell to `collect_through_block_cells`'s blocked set;
  - contribute its (x, y) -> "stairs_left"/"stairs_right" kind to
    `collect_stair_behavior_cells` instead;
  - emit no object_event/bg_event/coord_event in `build_object_events` (pure
    geometry now, no script/dialogue), without disturbing the local-id
    positions of the surviving events.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.tileset_converter import map_constants as mc
from rpg2gba.tileset_converter import metadata_wiring as mw

_REAL_MAP033 = Path("/home/b/repos/rpg2gba/output/uranium-build/maps/Map033.json")

_SLICE = {49}


# --- fixture helpers (mirrors tests/test_tileset_converter.py's _page/_event
# and tests/test_stairs.py's move-route builders, so a stair page here is
# built the exact same way `stairs.py` expects to detect one) -----------------

def _page(
    trigger: int = 0,
    cond: dict | None = None,
    cmds: list | None = None,
    name: str = "",
    opacity: int = 255,
    direction: int = 2,
    move_type: int = 0,
    through: bool = False,
    direction_fix: bool = False,
) -> dict:
    return {
        "trigger": trigger,
        "condition": cond or {},
        "graphic": {"character_name": name, "opacity": opacity, "direction": direction},
        "move_type": move_type,
        "list": cmds or [],
        "through": through,
        "direction_fix": direction_fix,
    }


def _event(eid: int, x: int, y: int, pages: list[dict], name: str | None = None) -> dict:
    return {
        "id": eid, "name": name if name is not None else f"E{eid}",
        "x": x, "y": y, "pages": pages,
    }


def _branch_command(indent: int = 0) -> dict:
    """The code-111 'character direction, player' conditional branch — the
    shape `stairs._page_qualifies` looks for."""
    return {"code": 111, "indent": indent, "parameters": [6, -1, 6]}


def _move_route_command(codes: list[int], *, target: int = -1, code: int = 209) -> dict:
    """A set-move-route command (205/209) targeting `target`, embedding
    diagonal move codes `stairs._page_move_codes` extracts."""
    move_list = [{"code": c, "parameters": []} for c in codes]
    move_list.append({"code": 0, "parameters": []})
    return {
        "code": code,
        "indent": 1,
        "parameters": [target, {"list": move_list, "repeat": False, "skippable": False}],
    }


def _stair_page(codes: list[int]) -> dict:
    """A minimal RMXP diagonal-stair "player touch" page: solid
    (through=False), blank graphic, with the branch+move-route shape
    `stairs.detect_stair_cells` recognizes."""
    return _page(
        trigger=1, through=False,
        cmds=[_branch_command(), _move_route_command(codes)],
    )


def _npc_gfx() -> dict[str, str]:
    return {
        "HGSS_000": "OBJ_EVENT_GFX_URANIUM_HGSS_000",
        "HGSS_005": "OBJ_EVENT_GFX_URANIUM_HGSS_005",
    }


# --- collect_through_block_cells excludes stair events ------------------------

def test_collect_through_block_cells_excludes_stair_event() -> None:
    """A map whose only through=false blank-graphic event is a diagonal-stair
    event yields NO blocked cells — the native fix needs the tile passable."""
    map_json = {
        "map_id": 49,
        "events": [_event(1, 57, 9, [_stair_page([6, 7])])],  # RIGHT axis
    }
    assert mw.collect_through_block_cells(map_json) == set()


def test_collect_through_block_cells_blocks_real_obstacle_not_stair() -> None:
    """A real invisible-obstacle event (blank graphic, through=false, no
    stair script shape) alongside a stair event: only the obstacle's cell is
    blocked, the stair cell is not."""
    obstacle = _event(1, 4, 4, [_page(trigger=0, through=False)])  # no stair shape
    stair = _event(2, 57, 9, [_stair_page([6, 7])])
    map_json = {"map_id": 49, "events": [obstacle, stair]}
    assert mw.collect_through_block_cells(map_json) == {(4, 4)}


# --- collect_stair_behavior_cells ---------------------------------------------

def test_collect_stair_behavior_cells_left_and_right() -> None:
    left = _event(1, 3, 4, [_stair_page([5, 8])])  # NE/SW axis -> LEFT
    right = _event(2, 57, 9, [_stair_page([6, 7])])  # NW/SE axis -> RIGHT
    map_json = {"map_id": 49, "events": [left, right]}
    assert mw.collect_stair_behavior_cells(map_json) == {
        (3, 4): "stairs_left",
        (57, 9): "stairs_right",
    }


# --- build_object_events: no object events, local ids unaffected -------------

def test_stair_events_do_not_appear_among_object_events() -> None:
    consts = mc.MapConstantRegistry(Path("x")).mint(49, "Route 1")
    npc = _event(1, 4, 4, [_page(name="HGSS_000")])
    stair = _event(2, 57, 9, [_stair_page([6, 7])])
    map_json = {"map_id": 49, "events": [npc, stair]}

    result = mw.build_object_events(map_json, consts, _SLICE, npc_gfx=_npc_gfx())

    placed = {(o.x, o.y) for o in result.object_events}
    assert (57, 9) not in placed
    assert (2, mw.DROP_STAIR) in result.drops


def test_stair_event_removal_does_not_renumber_surviving_local_ids() -> None:
    """The hard constraint: skipping a stair event must not shift the
    porymap-local-id positions of the OTHER events. `local_id_map` is
    populated only on an actual `object_events.append`, so a map WITH a
    stair event wedged between two NPCs must produce the exact same
    local_id_map/placement for those NPCs as a map where the stair event
    never existed at all."""
    consts = mc.MapConstantRegistry(Path("x")).mint(49, "Route 1")
    npc_a = _event(1, 4, 4, [_page(name="HGSS_000")])
    stair = _event(5, 57, 9, [_stair_page([6, 7])])  # wedged between the ids
    npc_b = _event(9, 20, 20, [_page(name="HGSS_005")])

    with_stair = {"map_id": 49, "events": [npc_a, stair, npc_b]}
    without_stair = {"map_id": 49, "events": [npc_a, npc_b]}

    result_with = mw.build_object_events(with_stair, consts, _SLICE, npc_gfx=_npc_gfx())
    result_without = mw.build_object_events(without_stair, consts, _SLICE, npc_gfx=_npc_gfx())

    assert result_with.local_id_map == {"1": 1, "9": 2}
    assert result_with.local_id_map == result_without.local_id_map
    with_xy = [(o.x, o.y) for o in result_with.object_events]
    without_xy = [(o.x, o.y) for o in result_without.object_events]
    assert with_xy == without_xy == [(4, 4), (20, 20)]


# --- real-data regression: Map033 (57,9)/(57,10)/(57,11) ----------------------

def test_map033_real_stair_cells_passable_and_behavior_tagged() -> None:
    if not _REAL_MAP033.exists():
        pytest.skip(f"{_REAL_MAP033} not found")
    with _REAL_MAP033.open(encoding="utf-8") as f:
        map_json = json.load(f)

    blocked = mw.collect_through_block_cells(map_json)
    behaviors = mw.collect_stair_behavior_cells(map_json)

    for cell in [(57, 9), (57, 10), (57, 11)]:
        assert cell not in blocked
        assert behaviors[cell] == "stairs_right"
