"""Tests for the code-209 (Set Move Route) generic beat-floor extractor.

REDERIVATION_PLAN.md §16.3 C4 / R11: a route asserts net displacement where
predictable, else completion-only (a `visual` assertion, never a refusal).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.beat_floor.assertion import ExtractContext
from rpg2gba.beat_floor.move_route import MOVE_STEP_CODES, extract_move_route

REPO_ROOT = Path(__file__).resolve().parents[1]
CH01_CH05_MAP_IDS = [19, 31, 32, 33, 35, 36, 37, 48, 49, 50, 64, 65, 67, 68, 73, 81, 89, 172]


def _ctx(row_id: str = "map001/ev001/p0") -> ExtractContext:
    return ExtractContext(
        map_id=1,
        event_id=1,
        page_idx=0,
        row_id=row_id,
        event={},
        map_data={},
        common_events_by_id={},
    )


def _step(code: int, *parameters: object) -> dict:
    return {"code": code, "parameters": list(parameters)}


def _route(steps: list[dict], *, repeat: bool = False, skippable: bool = False) -> dict:
    return {"list": [*steps, _step(0)], "repeat": repeat, "skippable": skippable}


def _cmd(target: int, route: dict) -> dict:
    return {"code": 209, "parameters": [target, route]}


def _displacement(result):
    assertions, refusals = result
    assert refusals == ()
    assert len(assertions) == 1
    a = assertions[0]
    assert a.code == 209
    return a


def test_straight_moves_displacement():
    route = _route([_step(1), _step(1), _step(3)])  # down, down, right
    a = _displacement(extract_move_route(_cmd(-1, route), 5, _ctx()))
    assert a.kind == "displacement"
    assert a.tag == "position"
    params = dict(a.params)
    assert params["target"] == -1
    assert params["dx"] == 1
    assert params["dy"] == 2
    assert params["facing"] == "right"
    assert a.offline is False  # displacement is ROM-only


def test_diagonal_clears_facing():
    route = _route([_step(1), _step(6)])  # down, then lower-right diagonal
    a = _displacement(extract_move_route(_cmd(0, route), 0, _ctx()))
    params = dict(a.params)
    assert params["dx"] == 1
    assert params["dy"] == 2
    assert params["facing"] is None


def test_jump_adds_xy():
    route = _route([_step(14, 3, -2)])
    a = _displacement(extract_move_route(_cmd(4, route), 0, _ctx()))
    params = dict(a.params)
    assert params["dx"] == 3
    assert params["dy"] == -2


def test_absolute_turn_sets_facing_no_displacement():
    route = _route([_step(16)])  # turn down
    a = _displacement(extract_move_route(_cmd(0, route), 0, _ctx()))
    params = dict(a.params)
    assert params["dx"] == 0
    assert params["dy"] == 0
    assert params["facing"] == "down"


def test_step_forward_known_facing():
    route = _route([_step(16), _step(12)])  # turn down, step forward
    a = _displacement(extract_move_route(_cmd(0, route), 0, _ctx()))
    params = dict(a.params)
    assert params["dx"] == 0
    assert params["dy"] == 1
    assert params["facing"] == "down"


def test_step_forward_unknown_facing_is_unpredictable():
    route = _route([_step(12)])
    assertions, refusals = extract_move_route(_cmd(0, route), 0, _ctx())
    assert refusals == ()
    a = assertions[0]
    assert a.kind == "visual"
    assert a.tag == "visual"
    detail = dict(a.params)["detail"]
    assert detail == "unpredictable_route:step_forward_unknown_facing"


def test_relative_turn_180_from_known_facing():
    route = _route([_step(16), _step(22)])  # turn down, turn 180 -> up
    a = _displacement(extract_move_route(_cmd(0, route), 0, _ctx()))
    assert dict(a.params)["facing"] == "up"


def test_direction_fix_suppresses_facing_update():
    route = _route([_step(16), _step(35), _step(2), _step(36)])  # face down, fix, walk left, unfix
    a = _displacement(extract_move_route(_cmd(0, route), 0, _ctx()))
    params = dict(a.params)
    assert params["facing"] == "down"  # unchanged by the fixed walk-left
    assert params["dx"] == -1


def test_repeat_is_unpredictable():
    route = _route([_step(1)], repeat=True)
    a = extract_move_route(_cmd(0, route), 0, _ctx())[0][0]
    assert a.kind == "visual"
    assert dict(a.params)["detail"] == "unpredictable_route:repeat"


def test_skippable_keeps_intended_displacement():
    route = _route([_step(1)], skippable=True)
    a = extract_move_route(_cmd(0, route), 0, _ctx())[0][0]
    assert a.kind == "displacement"
    assert (a.param("dx"), a.param("dy")) == (0, 1)


def test_random_move_is_unpredictable():
    route = _route([_step(1), _step(9)])
    a = extract_move_route(_cmd(0, route), 0, _ctx())[0][0]
    assert dict(a.params)["detail"] == "unpredictable_route:random_move"


def test_toward_player_move_is_unpredictable():
    route = _route([_step(10)])
    a = extract_move_route(_cmd(0, route), 0, _ctx())[0][0]
    assert dict(a.params)["detail"] == "unpredictable_route:toward_player"


def test_away_player_turn_is_unpredictable():
    route = _route([_step(26)])
    a = extract_move_route(_cmd(0, route), 0, _ctx())[0][0]
    assert dict(a.params)["detail"] == "unpredictable_route:away_player_turn"


def test_route_switch_write_is_unpredictable():
    route = _route([_step(27, 5, 5, 0)])
    a = extract_move_route(_cmd(0, route), 0, _ctx())[0][0]
    assert dict(a.params)["detail"] == "unpredictable_route:route_switch_write"


def test_script_step_is_unpredictable():
    route = _route([_step(45, "some_script_call")])
    a = extract_move_route(_cmd(0, route), 0, _ctx())[0][0]
    assert dict(a.params)["detail"] == "unpredictable_route:script"


def test_unknown_code_is_unpredictable(caplog):
    route = _route([_step(99)])
    with caplog.at_level("WARNING"):
        a = extract_move_route(_cmd(0, route), 0, _ctx())[0][0]
    assert dict(a.params)["detail"] == "unpredictable_route:unknown_step_code:99"
    assert "unrecognized" in caplog.text


def test_neutral_codes_do_not_affect_displacement():
    route = _route([
        _step(1),           # walk down
        _step(15, 2),        # wait
        _step(29, 6),        # change speed
        _step(30, 4),        # change frequency
        _step(31), _step(32),
        _step(33), _step(34),
        _step(37), _step(38),
        _step(39), _step(40),
        _step(41, "graphic", 0),
        _step(42, 128),
        _step(43, 1),
        _step(44, {"name": "SE"}),
    ])
    a = _displacement(extract_move_route(_cmd(0, route), 0, _ctx()))
    params = dict(a.params)
    assert params["dx"] == 0
    assert params["dy"] == 1
    assert params["facing"] == "down"


def test_never_raises_on_malformed_cmd():
    cmd = {"code": 209, "parameters": [0, {}]}
    assertions, refusals = extract_move_route(cmd, 0, _ctx())
    assert refusals == ()
    assert len(assertions) == 1


def test_move_step_codes_covers_documented_range():
    assert MOVE_STEP_CODES == frozenset(range(46))


@pytest.mark.skipif(
    not (REPO_ROOT / "output" / "uranium-build" / "maps").is_dir(),
    reason="requires output/uranium-build/maps corpus",
)
def test_corpus_ch01_ch05_move_routes_never_raise():
    maps_dir = REPO_ROOT / "output" / "uranium-build" / "maps"
    predicted = 0
    unpredictable = 0
    reason_tally: dict[str, int] = {}
    seen_codes: set[int] = set()

    for map_id in CH01_CH05_MAP_IDS:
        map_path = maps_dir / f"Map{map_id:03d}.json"
        if not map_path.is_file():
            continue
        data = json.loads(map_path.read_text(encoding="utf-8"))
        for event in data.get("events", []):
            if event is None:
                continue
            for page_idx, page in enumerate(event.get("pages", [])):
                row_id = f"map{map_id:03d}/ev{event['id']:03d}/p{page_idx}"
                ctx = ExtractContext(
                    map_id=map_id, event_id=event["id"], page_idx=page_idx,
                    row_id=row_id, event=event, map_data=data,
                    common_events_by_id={},
                )
                for list_index, cmd in enumerate(page.get("list", [])):
                    if cmd.get("code") != 209:
                        continue
                    route = cmd.get("parameters", [None, {}])[1]
                    if isinstance(route, dict):
                        for step in route.get("list", []):
                            seen_codes.add(step.get("code", 0))
                    assertions, refusals = extract_move_route(cmd, list_index, ctx)
                    assert refusals == ()
                    a = assertions[0]
                    if a.kind == "displacement":
                        predicted += 1
                    else:
                        unpredictable += 1
                        detail = dict(a.params)["detail"]
                        reason = detail.split(":", 1)[1] if ":" in detail else detail
                        reason_tally[reason] = reason_tally.get(reason, 0) + 1

    assert seen_codes <= MOVE_STEP_CODES, seen_codes - MOVE_STEP_CODES
    print(f"predicted={predicted} unpredictable={unpredictable} reasons={reason_tally}")
