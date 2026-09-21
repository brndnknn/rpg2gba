"""Tests for `rpg2gba.beat_floor.obstacle` and its wiring into
`walk.floor_for_map` (REDERIVATION_PLAN.md §16.3 C7, Task 3).

The fixture pages are cut down from real output (verified 2026-09-19):
`ROCK_PAGE` from `Map033.json` ev29 p0 (the move route dropped), and
`BOULDER_PAGE` from `Map031.json` ev1 p0. Note where the Rock Smash calls
sit: the `111` condition is on the page TRUNK, and the then-arm holds a
second capability call (`Kernel.pbRockSmashRandomEncounter`). That is what
R4 is about.

STATUS: implemented, skipped. DELETE the `pytestmark` line when you start
Task 3.
"""
from __future__ import annotations

import pytest

from rpg2gba.beat_floor import coverage, walk
from rpg2gba.beat_floor.assertion import OFFLINE_KINDS, FloorAssertion, make_params

MAP_ID = 1
EVENT_ID = 1
TRUNK = "map001/ev001/p0"
ROCK_CELL = (13, 21)

_ROCK_SFX = {"__class__": "RPG::AudioFile", "volume": 100,
             "name": "notverydamage", "pitch": 70}

ROCK_PAGE = [
    {"code": 111, "indent": 0, "parameters": [12, "Kernel.pbRockSmash"]},
    {"code": 250, "indent": 1, "parameters": [_ROCK_SFX]},
    {"code": 355, "indent": 1, "parameters": ["pbEraseThisEvent"]},
    {"code": 355, "indent": 1, "parameters": ["Kernel.pbRockSmashRandomEncounter"]},
    {"code": 0, "indent": 1, "parameters": []},
    {"code": 411, "indent": 0, "parameters": []},
    {"code": 0, "indent": 1, "parameters": []},
    {"code": 412, "indent": 0, "parameters": []},
    {"code": 0, "indent": 0, "parameters": []},
]

BOULDER_PAGE = [
    {"code": 355, "indent": 0, "parameters": ["pbPushThisBoulder"]},
    {"code": 0, "indent": 0, "parameters": []},
]

TEXT_PAGE = [
    {"code": 101, "indent": 0, "parameters": ["Nice day."]},
    {"code": 0, "indent": 0, "parameters": []},
]


def _event(commands: list[dict], *, cell: tuple[int, int] | None = ROCK_CELL,
           trigger: int = 0) -> dict:
    event = {"id": EVENT_ID, "name": "Rock",
             "pages": [{"trigger": trigger, "condition": {}, "list": commands}]}
    if cell is not None:
        event["x"], event["y"] = cell
    return event


def _floors(commands: list[dict], **kwargs) -> dict:
    """Every row floor for a one-event synthetic map (trunk + arms)."""
    return walk.floor_for_map(
        MAP_ID, {"events": [_event(commands, **kwargs)]},
        common_events=[], switch_labels={}, door_cells={},
    )


def _obstacles(floors: dict) -> list[FloorAssertion]:
    return [a for f in floors.values() for a in f.assertions if a.kind == "blocked_obstacle"]


def _only_obstacle(floors: dict) -> FloorAssertion:
    found = _obstacles(floors)
    assert len(found) == 1, found
    return found[0]


# --- the extractor, through the real walker -------------------------------

def test_rock_smash_page_gets_obstacle():
    a = _only_obstacle(_floors(ROCK_PAGE))
    assert a.list_index == -1
    assert a.code is None
    assert a.tag == "position"
    assert dict(a.params) == {"x": 13, "y": 21, "capability": "rock_smash"}
    assert a.params == make_params(x=13, y=21, capability="rock_smash")


def test_strength_boulder_gets_obstacle():
    a = _only_obstacle(_floors(BOULDER_PAGE, trigger=1))
    assert a.row_id == TRUNK
    assert a.param("capability") == "strength"


def test_plain_npc_gets_none():
    assert _obstacles(_floors(TEXT_PAGE)) == []


def test_visual_placeholder_kept():
    # The WITH-capability placeholder and the WITHOUT-capability kind coexist.
    floors = _floors(ROCK_PAGE)
    kinds = {a.kind for f in floors.values() for a in f.assertions}
    assert {"visual", "blocked_obstacle"} <= kinds


def test_missing_cell_refuses():
    floors = _floors(ROCK_PAGE, cell=None)
    assert _obstacles(floors) == []
    reasons = [r.reason for f in floors.values() for r in f.refusals]
    assert reasons.count("obstacle_missing_cell") == 1


def test_one_row_per_obstacle_page():
    # R4: trunk + arms together carry exactly one, and on a real row id.
    floors = _floors(ROCK_PAGE)
    assert len(floors) > 1, "fixture should produce a trunk AND arm rows"
    a = _only_obstacle(floors)
    assert a.row_id in floors
    assert floors[a.row_id].row_id == a.row_id


def test_obstacle_row_keeps_existing_assertions():
    # The merge in floor_for_map adds; it must not replace what was there.
    floors = _floors(ROCK_PAGE)
    row = floors[_only_obstacle(floors).row_id]
    assert {"trigger", "completes"} <= {a.kind for a in row.assertions}


# --- the pure function ----------------------------------------------------

def test_pure_function_no_capability():
    assert _call(TEXT_PAGE) == ((), ())


def test_multiple_capabilities_refuses():
    both = [BOULDER_PAGE[0], *ROCK_PAGE]
    assertions, refusals = _call(both)
    assert assertions == ()
    assert [r.reason for r in refusals] == ["obstacle_multiple_capabilities"]
    assert refusals[0].row_id == TRUNK


def test_missing_y_alone_refuses():
    event = _event(BOULDER_PAGE)
    del event["y"]
    assertions, refusals = _call(BOULDER_PAGE, event=event)
    assert assertions == ()
    assert [r.reason for r in refusals] == ["obstacle_missing_cell"]


def test_cell_zero_is_a_real_cell():
    # (0, 0) is a legal map cell. "Missing" means absent, not falsy.
    assertions, refusals = _call(BOULDER_PAGE, event=_event(BOULDER_PAGE, cell=(0, 0)))
    assert refusals == ()
    assert dict(assertions[0].params)["x"] == 0


def _call(commands: list[dict], *, event: dict | None = None):
    from rpg2gba.beat_floor.obstacle import obstacle_assertions
    return obstacle_assertions(TRUNK, event or _event(commands), commands)


# --- the contract ---------------------------------------------------------

def test_not_offline():
    assert "blocked_obstacle" not in OFFLINE_KINDS
    floors = _floors(BOULDER_PAGE, trigger=1)
    row = floors[_only_obstacle(floors).row_id]
    assert not row.offline_eligible


def test_covers_roundtrip():
    a = _only_obstacle(_floors(ROCK_PAGE))
    assert coverage.covers(a, a)
    other = FloorAssertion(
        row_id=a.row_id, kind=a.kind, list_index=a.list_index, code=a.code,
        params=make_params(x=13, y=21, capability="strength"), tag=a.tag,
    )
    assert coverage.contradicts(other, a)
    assert not coverage.covers(other, a)
