"""Regression test for the Kevlar Town Strength boulders (CH03,
`map031/ev001/p0` and `map031/ev037/p0`).

Confirms against REAL build output (`output/uranium-build/maps/Map031.json`)
-- not a synthetic fixture -- that both `pbPushThisBoulder` pages already
carry a `blocked_obstacle{capability: "strength"}` assertion at the event's
own cell, via `obstacle.obstacle_assertions`'s wiring into
`walk.floor_for_map` (keyed off `chapter_manifest.generator._HEAD_REQUIRES`,
independent of `script.SCRIPT_HEAD_EXTRACTORS["pbPushThisBoulder"]`'s
`visual` placeholder -- both assertions coexist on the same row floor, see
`beat_floor/obstacle.py` module docstring).

Investigation finding (2026-09-25): this already works end to end for the
floor. The two rows still surface as "later -- owner None" in
`output/beats/CH03.review.md` because `beat_gen.select.select_rows` Rule 5
(`verdict.status == "later"`) fires before Rule 6 (the obstacle-row
exemption) ever looks at the floor -- a story-state verdict question, not a
beat_floor one. See this file's module docstring / the handback report for
the file:line.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.beat_floor import walk

_MAP031 = Path(__file__).resolve().parents[1] / "output" / "uranium-build" / "maps" / "Map031.json"

pytestmark = pytest.mark.skipif(
    not _MAP031.exists(), reason="requires a built output/uranium-build/maps/Map031.json"
)


def _floors_for_map031() -> dict:
    data = json.loads(_MAP031.read_text(encoding="utf-8"))
    return walk.floor_for_map(
        31, data, common_events=[], switch_labels={}, door_cells={},
    )


def _obstacle(floors: dict, row_id: str):
    floor = floors[row_id]
    found = [a for a in floor.assertions if a.kind == "blocked_obstacle"]
    assert len(found) == 1, (row_id, found)
    return found[0]


def test_boulder_ev001_is_a_strength_obstacle_at_its_own_cell():
    floors = _floors_for_map031()
    a = _obstacle(floors, "map031/ev001/p0")
    assert dict(a.params) == {"x": 10, "y": 16, "capability": "strength"}


def test_boulder_ev037_is_a_strength_obstacle_at_its_own_cell():
    floors = _floors_for_map031()
    a = _obstacle(floors, "map031/ev037/p0")
    assert dict(a.params) == {"x": 12, "y": 16, "capability": "strength"}


def test_boulder_rows_are_not_refused():
    floors = _floors_for_map031()
    for row_id in ("map031/ev001/p0", "map031/ev037/p0"):
        assert not floors[row_id].refusals, (row_id, floors[row_id].refusals)
