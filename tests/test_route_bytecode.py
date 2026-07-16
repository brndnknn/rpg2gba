"""Tests for rpg2gba.tileset_converter.route_bytecode.

SoT: reference/guides/custom_route_interpreter.md
"""
from __future__ import annotations

from rpg2gba.tileset_converter.route_bytecode import (
    OP_END_LOOP,
    OP_END_STOP,
    OP_FACE_DOWN,
    OP_FACE_LEFT,
    OP_FACE_RIGHT,
    OP_FACE_UP,
    OP_STEP_DOWN,
    OP_STEP_LEFT,
    OP_STEP_RIGHT,
    OP_STEP_UP,
    OP_THROUGH_OFF,
    OP_THROUGH_ON,
    OP_WAIT,
    encode_route,
)


def _cmd(code: int, parameters: list | None = None) -> dict:
    return {"code": code, "parameters": parameters or []}


def _route(codes: list[int], repeat: bool = True) -> dict:
    return {"repeat": repeat, "skippable": True, "list": [_cmd(c) for c in codes]}


# --- idle header formula, all frequencies ------------------------------


def test_idle_header_frequency_1():
    route = _route([1])
    assert encode_route(route, 1)[0] == 190


def test_idle_header_frequency_2():
    route = _route([1])
    assert encode_route(route, 2)[0] == 144


def test_idle_header_frequency_3():
    route = _route([1])
    assert encode_route(route, 3)[0] == 102


def test_idle_header_frequency_4():
    route = _route([1])
    assert encode_route(route, 4)[0] == 64


def test_idle_header_frequency_5():
    route = _route([1])
    assert encode_route(route, 5)[0] == 30


def test_idle_header_frequency_6():
    route = _route([1])
    assert encode_route(route, 6)[0] == 0


# --- single-axis loop, pinned byte-for-byte -----------------------------


def test_single_axis_loop_repeat():
    # left x3, right x3, freq 3, repeat=true
    route = _route([2, 2, 2, 3, 3, 3], repeat=True)
    result = encode_route(route, 3)
    assert result == [
        102,
        OP_STEP_LEFT,
        OP_STEP_LEFT,
        OP_STEP_LEFT,
        OP_STEP_RIGHT,
        OP_STEP_RIGHT,
        OP_STEP_RIGHT,
        OP_END_LOOP,
    ]


def test_single_axis_loop_no_repeat_ends_stop():
    route = _route([2, 2, 2, 3, 3, 3], repeat=False)
    result = encode_route(route, 3)
    assert result[-1] == OP_END_STOP
    assert result[0] == 102


# --- multi-leg loop ------------------------------------------------------


def test_multi_leg_loop():
    # left, up, up, down, down, right
    route = _route([2, 4, 4, 1, 1, 3], repeat=True)
    result = encode_route(route, 6)
    assert result == [
        0,
        OP_STEP_LEFT,
        OP_STEP_UP,
        OP_STEP_UP,
        OP_STEP_DOWN,
        OP_STEP_DOWN,
        OP_STEP_RIGHT,
        OP_END_LOOP,
    ]


# --- through toggle (town-square patrol) --------------------------------


def test_through_toggle_pattern():
    # step down, THROUGH_ON, step down x2, THROUGH_OFF, step down
    route = {
        "repeat": True,
        "skippable": True,
        "list": [
            _cmd(1),
            _cmd(37),
            _cmd(1),
            _cmd(1),
            _cmd(38),
            _cmd(1),
        ],
    }
    result = encode_route(route, 3)
    assert result == [
        102,
        OP_STEP_DOWN,
        OP_THROUGH_ON,
        OP_STEP_DOWN,
        OP_STEP_DOWN,
        OP_THROUGH_OFF,
        OP_STEP_DOWN,
        OP_END_LOOP,
    ]


# --- wait command --------------------------------------------------------


def test_wait_command_encodes_frames():
    # wait param 5 -> frames = 5*2-1 = 9
    route = {
        "repeat": True,
        "skippable": True,
        "list": [_cmd(1), _cmd(15, [5])],
    }
    result = encode_route(route, 3)
    assert result == [102, OP_STEP_DOWN, OP_WAIT, 9, OP_END_LOOP]


def test_wait_command_clamped_to_255():
    route = {
        "repeat": True,
        "skippable": True,
        "list": [_cmd(1), _cmd(15, [200])],
    }
    result = encode_route(route, 3)
    assert result[-1] == OP_END_LOOP
    assert result[3] == 255


def test_wait_command_missing_params_demotes():
    route = {
        "repeat": True,
        "skippable": True,
        "list": [_cmd(1), _cmd(15, [])],
    }
    assert encode_route(route, 3) is None


# --- turn-in-place (FACE) opcodes ----------------------------------------


def test_face_opcodes_all_directions():
    route = _route([16, 17, 18, 19], repeat=False)
    result = encode_route(route, 3)
    assert result == [
        102,
        OP_FACE_DOWN,
        OP_FACE_LEFT,
        OP_FACE_RIGHT,
        OP_FACE_UP,
        OP_END_STOP,
    ]


# --- repeat=false -> END_STOP --------------------------------------------


def test_repeat_false_ends_stop():
    route = _route([1], repeat=False)
    result = encode_route(route, 3)
    assert result[-1] == OP_END_STOP


def test_repeat_true_ends_loop():
    route = _route([1], repeat=True)
    result = encode_route(route, 3)
    assert result[-1] == OP_END_LOOP


# --- demote triggers ------------------------------------------------------


def test_demote_diagonal():
    route = _route([5])
    assert encode_route(route, 3) is None


def test_demote_move_random():
    route = _route([9])
    assert encode_route(route, 3) is None


def test_demote_toward_player():
    route = _route([10])
    assert encode_route(route, 3) is None


def test_demote_away_player():
    route = _route([11])
    assert encode_route(route, 3) is None


def test_demote_forward():
    route = _route([12])
    assert encode_route(route, 3) is None


def test_demote_backward():
    route = _route([13])
    assert encode_route(route, 3) is None


def test_demote_jump():
    route = _route([14])
    assert encode_route(route, 3) is None


def test_demote_relative_turn():
    route = _route([20])
    assert encode_route(route, 3) is None


def test_demote_face_player():
    route = _route([25])
    assert encode_route(route, 3) is None


def test_demote_face_away():
    route = _route([26])
    assert encode_route(route, 3) is None


def test_demote_unknown_code():
    route = _route([999])
    assert encode_route(route, 3) is None


# --- empty / dropped-only routes -----------------------------------------


def test_empty_route_demotes():
    route = _route([])
    assert encode_route(route, 3) is None


def test_dropped_only_route_demotes():
    # just an SE code (44) - drops silently, leaves zero real ops
    route = _route([44])
    assert encode_route(route, 3) is None


def test_dropped_codes_mixed_with_real_ops():
    # switch, speed, freq-change, graphic, opacity, blend, SE, script all drop
    route = {
        "repeat": True,
        "skippable": True,
        "list": [
            _cmd(27),
            _cmd(28),
            _cmd(29),
            _cmd(30),
            _cmd(1),
            _cmd(41),
            _cmd(42),
            _cmd(43),
            _cmd(44),
            _cmd(45),
        ],
    }
    result = encode_route(route, 3)
    assert result == [102, OP_STEP_DOWN, OP_END_LOOP]


# --- terminator code 0 stops scanning ------------------------------------


def test_terminator_stops_scanning():
    route = {
        "repeat": True,
        "skippable": True,
        "list": [_cmd(1), _cmd(2), _cmd(0), _cmd(3)],
    }
    result = encode_route(route, 3)
    assert result == [102, OP_STEP_DOWN, OP_STEP_LEFT, OP_END_LOOP]


# --- structurally broken input raises ------------------------------------


def test_missing_list_key_raises():
    route = {"repeat": True, "skippable": True}
    try:
        encode_route(route, 3)
        raised = False
    except KeyError:
        raised = True
    assert raised
