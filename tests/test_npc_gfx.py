"""Unit tests for npc_gfx.py — Uranium NPC sheet -> OBJ_EVENT_GFX_* + RMXP
boot-page semantics (boot-page selection, movement mapping, door predicate)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.tileset_converter.metadata_wiring import ObjectEvent
from rpg2gba.tileset_converter.npc_gfx import (
    _WALK_SEQUENCE_QUIRKS,
    MOVEMENT_TYPE_CUSTOM_ROUTE,
    MapPassability,
    MovementSpec,
    gfx_constant_for_sheet,
    is_door_sheet,
    load_npc_gfx_map,
    movement_spec_for,
    select_boot_page,
    static_face_spec,
)
from rpg2gba.tileset_converter.route_bytecode import encode_route

REAL_NPC_GFX_MAP = Path("reference/npc_gfx_map.json")
ENGINE_MOVEMENT_C = Path("engine/src/event_object_movement.c")


# --- gfx_constant_for_sheet ---------------------------------------------------

def test_gfx_constant_for_sheet_pinned_examples() -> None:
    """The four pinned minting examples from the task spec."""
    assert gfx_constant_for_sheet("HGSS_000") == "OBJ_EVENT_GFX_URANIUM_HGSS_000"
    assert gfx_constant_for_sheet("PU-Chyinmunk") == "OBJ_EVENT_GFX_URANIUM_PU_CHYINMUNK"
    assert (
        gfx_constant_for_sheet("fk107-rocksmash") == "OBJ_EVENT_GFX_URANIUM_FK107_ROCKSMASH"
    )
    assert gfx_constant_for_sheet("Rivaltheo") == "OBJ_EVENT_GFX_URANIUM_RIVALTHEO"


# --- load_npc_gfx_map ---------------------------------------------------------

def _headers_for(tmp_path: Path, defines: list[str]) -> list[Path]:
    path = tmp_path / "event_objects.h"
    path.write_text(
        "\n".join(f"#define {name} {i}" for i, name in enumerate(defines)) + "\n",
        encoding="utf-8",
    )
    return [path]


def test_load_npc_gfx_map_real_file_validates(tmp_path: Path) -> None:
    """The real reference/npc_gfx_map.json loads cleanly against a header that
    defines every gfx constant it mints. Entry count isn't pinned — the map
    grows as new sheets are added (e.g. the "ZP- Professor" hidden-actor
    entry, findings §3.3/§5) — only that every entry resolves."""
    raw = json.loads(REAL_NPC_GFX_MAP.read_text(encoding="utf-8"))
    gfx_names = [entry["gfx"] for entry in raw.values()]
    headers = _headers_for(tmp_path, gfx_names)
    result = load_npc_gfx_map(REAL_NPC_GFX_MAP, headers)
    assert len(result) == len(raw)
    assert result["HGSS_000"] == "OBJ_EVENT_GFX_URANIUM_HGSS_000"
    assert result["PU-Chyinmunk"] == "OBJ_EVENT_GFX_URANIUM_PU_CHYINMUNK"


def test_load_npc_gfx_map_unknown_constant_fails_loud(tmp_path: Path) -> None:
    """A gfx constant absent from every header fails loud."""
    json_path = tmp_path / "npc_gfx_map.json"
    json_path.write_text(
        json.dumps({"Foo": {"gfx": "OBJ_EVENT_GFX_URANIUM_FOO", "fallback": "x", "note": "n"}}),
        encoding="utf-8",
    )
    headers = _headers_for(tmp_path, ["OBJ_EVENT_GFX_SOMETHING_ELSE"])
    with pytest.raises(ValueError, match="not #define'd"):
        load_npc_gfx_map(json_path, headers)


def test_load_npc_gfx_map_missing_gfx_field_fails_loud(tmp_path: Path) -> None:
    json_path = tmp_path / "npc_gfx_map.json"
    json_path.write_text(json.dumps({"Foo": {"fallback": "x"}}), encoding="utf-8")
    headers = _headers_for(tmp_path, [])
    with pytest.raises(ValueError, match="missing required 'gfx'"):
        load_npc_gfx_map(json_path, headers)


def test_load_npc_gfx_map_duplicate_key_fails_loud(tmp_path: Path) -> None:
    json_path = tmp_path / "npc_gfx_map.json"
    # Hand-write raw JSON text with a duplicate top-level key (json.dumps from a
    # dict can't produce one — Python dicts can't hold a duplicate key).
    json_path.write_text(
        '{"Foo": {"gfx": "OBJ_EVENT_GFX_URANIUM_FOO"}, '
        '"Foo": {"gfx": "OBJ_EVENT_GFX_URANIUM_FOO"}}',
        encoding="utf-8",
    )
    headers = _headers_for(tmp_path, ["OBJ_EVENT_GFX_URANIUM_FOO"])
    with pytest.raises(ValueError, match="duplicate key"):
        load_npc_gfx_map(json_path, headers)


def test_load_npc_gfx_map_missing_file_fails_loud(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_npc_gfx_map(tmp_path / "absent.json", [tmp_path / "h.h"])


def test_load_npc_gfx_map_missing_header_fails_loud(tmp_path: Path) -> None:
    json_path = tmp_path / "npc_gfx_map.json"
    json_path.write_text(
        json.dumps({"Foo": {"gfx": "OBJ_EVENT_GFX_URANIUM_FOO"}}), encoding="utf-8"
    )
    with pytest.raises(FileNotFoundError):
        load_npc_gfx_map(json_path, [tmp_path / "does_not_exist.h"])


# --- select_boot_page ---------------------------------------------------------

def _page(cond: dict | None = None, **extra) -> dict:
    base = {"condition": cond or {}, "graphic": {"character_name": "", "direction": 2}}
    base.update(extra)
    return base


def test_select_boot_page_single_page_holds() -> None:
    event = {"pages": [_page()]}
    assert select_boot_page(event) is event["pages"][0]


def test_select_boot_page_highest_valid_wins() -> None:
    """Two pages both hold at boot (no gate at all) -> the higher-index one wins."""
    p0 = _page()
    p1 = _page()
    event = {"pages": [p0, p1]}
    assert select_boot_page(event) is p1


def test_select_boot_page_switch_gate_excludes() -> None:
    p0 = _page()
    p1 = _page(cond={"switch1_valid": True, "switch1_id": 5})
    event = {"pages": [p0, p1]}
    assert select_boot_page(event) is p0  # p1's switch reads OFF at boot

    p2 = _page(cond={"switch2_valid": True, "switch2_id": 5})
    event2 = {"pages": [p0, p2]}
    assert select_boot_page(event2) is p0


def test_select_boot_page_self_switch_excludes() -> None:
    p0 = _page()
    p1 = _page(cond={"self_switch_valid": True, "self_switch_ch": "A"})
    event = {"pages": [p0, p1]}
    assert select_boot_page(event) is p0  # self-switches read OFF at boot


def test_select_boot_page_variable_value_le_zero_holds() -> None:
    """RMXP condition is `game_variables[id] >= value`; every variable is 0 at
    boot, so the page holds iff value <= 0."""
    p0 = _page()
    p_holds = _page(cond={"variable_valid": True, "variable_id": 1, "variable_value": 0})
    event_holds = {"pages": [p0, p_holds]}
    assert select_boot_page(event_holds) is p_holds  # 0 >= 0 -> holds, higher index wins

    p_blocked = _page(cond={"variable_valid": True, "variable_id": 1, "variable_value": 1})
    event_blocked = {"pages": [p0, p_blocked]}
    assert select_boot_page(event_blocked) is p0  # 0 >= 1 -> false, falls back

    p_neg = _page(cond={"variable_valid": True, "variable_id": 1, "variable_value": -3})
    event_neg = {"pages": [p0, p_neg]}
    assert select_boot_page(event_neg) is p_neg  # 0 >= -3 -> holds


def test_select_boot_page_none_when_all_gated() -> None:
    p0 = _page(cond={"switch1_valid": True, "switch1_id": 1})
    event = {"pages": [p0]}
    assert select_boot_page(event) is None


# --- movement_spec_for ---------------------------------------------------------

def _move_page(
    move_type: int, direction: int = 2, route: dict | None = None, frequency: int = 6
) -> dict:
    """Frequency defaults to 6 (RMXP's only gap-free setting) so the axis-patrol
    pins below exercise the continuous WALK_* branch; the corpus norm is 3."""
    page = {
        "move_type": move_type,
        "move_frequency": frequency,
        "graphic": {"character_name": "X", "direction": direction},
    }
    if route is not None:
        page["move_route"] = route
    return page


def _route(codes: list[int], repeat: bool = True, skippable: bool = True) -> dict:
    """A `move_route` dict for `codes` in order, with the RMXP-mandated
    trailing code-0 sentinel entry appended (`movement_spec_for` strips it)."""
    return {
        "repeat": repeat,
        "skippable": skippable,
        "list": [{"code": c, "parameters": []} for c in codes] + [{"code": 0, "parameters": []}],
    }


# fixed (move_type 0) -----------------------------------------------------------

@pytest.mark.parametrize(
    "direction, facing",
    [(2, "DOWN"), (4, "LEFT"), (6, "RIGHT"), (8, "UP")],
)
def test_movement_spec_for_fixed_facings(direction: int, facing: str) -> None:
    spec = movement_spec_for(_move_page(0, direction))
    assert spec == MovementSpec(f"MOVEMENT_TYPE_FACE_{facing}")
    assert spec.route_bytecode is None  # move_type 0 is untouched by the interpreter


def test_movement_spec_for_unknown_move_type_fails_loud() -> None:
    with pytest.raises(ValueError, match="move_type"):
        movement_spec_for(_move_page(99, 2))


def test_movement_spec_for_unknown_direction_fails_loud() -> None:
    with pytest.raises(ValueError, match="direction"):
        movement_spec_for(_move_page(0, 3))


# random (move_type 1) -----------------------------------------------------------

def test_movement_spec_for_random_wanders() -> None:
    spec = movement_spec_for(_move_page(1, 2))
    assert spec == MovementSpec("MOVEMENT_TYPE_WANDER_AROUND", 0, 0)
    assert spec.route_bytecode is None  # move_type 1 is untouched by the interpreter


# approach player (move_type 2) --------------------------------------------------

def test_movement_spec_for_approach_fails_loud() -> None:
    """No native pokeemerald analog, zero occurrences corpus-wide — fail loud
    rather than guess at a substitute (SLICE1_TODO #12)."""
    with pytest.raises(ValueError, match="approach player"):
        movement_spec_for(_move_page(2, 2))


# custom route (move_type 3) -----------------------------------------------------

# --- custom-route bytecode interpreter wiring (interpreter-first) -----------
# `reference/guides/custom_route_interpreter.md` pipeline data path step 2:
# `_spec_for_custom_route` tries `encode_route` before any native/static
# classification. These pin the exact bytecode for the interpreter's core
# encodable shapes; the demote case (below) confirms the existing fallback
# classifier still runs, untouched, for what `encode_route` can't encode.

def test_movement_spec_for_custom_route_single_axis_repeat_encodes() -> None:
    """An encodable single-axis repeat route (left x3, right x3, freq 3) ->
    CUSTOM_ROUTE with the exact contract bytecode: idle header 102 (freq 3),
    the literal step opcodes, END_LOOP (repeat=true)."""
    route = _route([2, 2, 2, 3, 3, 3], repeat=True)
    spec = movement_spec_for(_move_page(3, route=route, frequency=3))
    assert spec.movement_type == MOVEMENT_TYPE_CUSTOM_ROUTE
    assert spec.route_bytecode == (102, 0x01, 2, 2, 2, 3, 3, 3, 0)
    assert spec.route_bytecode == tuple(encode_route(route, 3))
    assert spec.demoted is None


def test_movement_spec_for_custom_route_through_toggle_encodes() -> None:
    """A through-toggle route (some steps, code 37 THROUGH_ON, steps, code 38
    THROUGH_OFF) -> CUSTOM_ROUTE; THROUGH_ON/OFF are in `encode_route`'s v1
    scope, not dropped or demoted."""
    route = _route([3, 3, 37, 3, 3, 38], repeat=True)
    spec = movement_spec_for(_move_page(3, route=route, frequency=6))
    assert spec.movement_type == MOVEMENT_TYPE_CUSTOM_ROUTE
    assert spec.route_bytecode == (0, 0x01, 3, 3, 0x30, 3, 3, 0x31, 0)
    assert spec.route_bytecode == tuple(encode_route(route, 6))
    assert spec.demoted is None


def test_movement_spec_for_custom_repeat_false_is_static() -> None:
    """RE-PINNED (interpreter-first): a one-shot (repeat=False) route still
    encodes fine (`encode_route` emits END_STOP instead of END_LOOP), so the
    bytecode interpreter now wins over the old static-face fallback."""
    route = _route([3, 3, 3], repeat=False)
    spec = movement_spec_for(_move_page(3, direction=6, route=route))
    assert spec.movement_type == MOVEMENT_TYPE_CUSTOM_ROUTE
    assert spec.route_bytecode == tuple(encode_route(route, 6))
    assert spec.demoted is None


def test_movement_spec_for_custom_flicker_prop_is_static() -> None:
    """Graphic-swap (41) + wait (15), no translation or turn codes — a Luz-style
    flicker prop, not a movement bug — not a demotion."""
    spec = movement_spec_for(_move_page(3, direction=8, route=_route([41, 15])))
    assert spec.movement_type == "MOVEMENT_TYPE_FACE_UP"
    assert spec.demoted is None


def test_movement_spec_for_custom_turn_cycle_looks_around() -> None:
    route = _route([42, 16, 15, 17, 15, 18, 15, 19, 15, 42, 15])
    spec = movement_spec_for(_move_page(3, route=route))
    assert spec.movement_type == "MOVEMENT_TYPE_LOOK_AROUND"
    assert spec.range_x == 0
    assert spec.range_y == 0
    assert spec.demoted is None


def test_movement_spec_for_custom_turn_pair_down_up() -> None:
    """RE-PINNED (interpreter-first): absolute turn codes (16-19) are FACE
    opcodes `encode_route` handles directly, so this now plays as bytecode
    instead of the native FACE_DOWN_AND_UP combo."""
    route = _route([16, 19])
    spec = movement_spec_for(_move_page(3, route=route))
    assert spec.movement_type == MOVEMENT_TYPE_CUSTOM_ROUTE
    assert spec.route_bytecode == tuple(encode_route(route, 6))
    assert spec.demoted is None


def test_movement_spec_for_custom_turn_pair_left_right() -> None:
    """RE-PINNED (interpreter-first) — see turn_pair_down_up above."""
    route = _route([17, 18])
    spec = movement_spec_for(_move_page(3, route=route))
    assert spec.movement_type == MOVEMENT_TYPE_CUSTOM_ROUTE
    assert spec.route_bytecode == tuple(encode_route(route, 6))


def test_movement_spec_for_custom_single_turn_face_left() -> None:
    """RE-PINNED (interpreter-first) — a single FACE opcode still encodes."""
    route = _route([17])
    spec = movement_spec_for(_move_page(3, direction=8, route=route))
    assert spec.movement_type == MOVEMENT_TYPE_CUSTOM_ROUTE
    assert spec.route_bytecode == tuple(encode_route(route, 6))


def test_movement_spec_for_custom_turn_triple_down_up_left() -> None:
    """RE-PINNED (interpreter-first) — see turn_pair_down_up above."""
    route = _route([16, 17, 19])
    spec = movement_spec_for(_move_page(3, route=route))
    assert spec.movement_type == MOVEMENT_TYPE_CUSTOM_ROUTE
    assert spec.route_bytecode == tuple(encode_route(route, 6))


def test_movement_spec_for_custom_relative_turn_looks_around() -> None:
    """Any 20..26 relative/random/player-relative turn code forces the
    direction set to all four, regardless of what else is present."""
    spec = movement_spec_for(_move_page(3, route=_route([24])))
    assert spec.movement_type == "MOVEMENT_TYPE_LOOK_AROUND"


def test_movement_spec_for_custom_pacer_wide() -> None:
    """RE-PINNED (interpreter-first): an all-cardinal-step repeat route
    encodes cleanly, so this now plays as bytecode instead of the native
    WALK_LEFT_AND_RIGHT patrol."""
    route = _route([2, 2, 2, 3, 3, 3])
    spec = movement_spec_for(_move_page(3, route=route))
    assert spec.movement_type == MOVEMENT_TYPE_CUSTOM_ROUTE
    assert spec.route_bytecode == tuple(encode_route(route, 6))
    assert spec.demoted is None


def test_movement_spec_for_custom_pacer_narrow() -> None:
    """RE-PINNED (interpreter-first) — see pacer_wide above."""
    route = _route([2, 2, 3, 3])
    spec = movement_spec_for(_move_page(3, route=route))
    assert spec.movement_type == MOVEMENT_TYPE_CUSTOM_ROUTE
    assert spec.route_bytecode == tuple(encode_route(route, 6))


def test_movement_spec_for_custom_pacer_with_waits_wanders() -> None:
    """A WAIT code anywhere in the loop -> the pause-y WANDER_ variant, not the
    continuous WALK_ variant."""
    spec = movement_spec_for(_move_page(3, route=_route([2, 15, 3, 15])))
    assert spec.movement_type == "MOVEMENT_TYPE_WANDER_LEFT_AND_RIGHT"
    assert spec.range_x == 1
    assert spec.range_y == 0


def test_movement_spec_for_custom_vertical_pacer() -> None:
    """RE-PINNED (interpreter-first) — see pacer_wide above."""
    route = _route([1, 1, 4, 4])
    spec = movement_spec_for(_move_page(3, route=route))
    assert spec.movement_type == MOVEMENT_TYPE_CUSTOM_ROUTE
    assert spec.route_bytecode == tuple(encode_route(route, 6))


def test_movement_spec_for_custom_random_move_loop_wanders() -> None:
    """TRANSLATION == {9} only (waits/neutral fine) -> WANDER_AROUND, same as
    move_type 1."""
    spec = movement_spec_for(_move_page(3, route=_route([9, 15])))
    assert spec == MovementSpec("MOVEMENT_TYPE_WANDER_AROUND", 0, 0)


def test_movement_spec_for_custom_net_drift_demotes() -> None:
    """RE-PINNED (interpreter-first): `encode_route` doesn't care about net
    drift — it just plays the literal step sequence on loop — so this no
    longer demotes to a static face; it plays as bytecode. (The old
    native-classifier drift-demotion — case g in `movement_spec_for` — is
    still exercised via the diagonal/move-random demote tests below, which
    `encode_route` genuinely can't encode.)"""
    route = _route([2, 2])
    spec = movement_spec_for(_move_page(3, direction=4, route=route))
    assert spec.movement_type == MOVEMENT_TYPE_CUSTOM_ROUTE
    assert spec.route_bytecode == tuple(encode_route(route, 6))
    assert spec.demoted is None


def test_movement_spec_for_custom_mixed_axes_demotes() -> None:
    """RE-PINNED (interpreter-first): mixed-axis cardinal steps still encode
    fine as bytecode — no native-patrol shape restriction applies."""
    route = _route([2, 1])
    spec = movement_spec_for(_move_page(3, route=route))
    assert spec.movement_type == MOVEMENT_TYPE_CUSTOM_ROUTE
    assert spec.route_bytecode == tuple(encode_route(route, 6))


def test_movement_spec_for_custom_toward_player_demotes() -> None:
    """Code 10 (toward-player) is in `encode_route`'s demote set (no engine
    primitive in v1) -> falls through to the existing static-face fallback,
    unchanged by the interpreter-first change."""
    spec = movement_spec_for(_move_page(3, route=_route([10])))
    assert spec.route_bytecode is None
    assert spec.demoted is not None


def test_movement_spec_for_custom_translation_and_turn_mixed_demotes() -> None:
    """RE-PINNED (interpreter-first): a STEP mixed with a FACE opcode is fine
    for the bytecode interpreter (it can walk AND spin), so this now encodes
    instead of hitting the native classifier's case-e demotion."""
    route = _route([2, 16])
    spec = movement_spec_for(_move_page(3, route=route))
    assert spec.movement_type == MOVEMENT_TYPE_CUSTOM_ROUTE
    assert spec.route_bytecode == tuple(encode_route(route, 6))


def test_movement_spec_for_custom_missing_move_route_fails_loud() -> None:
    """A move_type 3 page with no `move_route` key at all is malformed input,
    not "nothing to do" -- KeyError propagates (CLAUDE.md §4.5)."""
    with pytest.raises(KeyError):
        movement_spec_for(_move_page(3))


# frequency-gated pacing (case g) --------------------------------------------

def test_movement_spec_for_custom_pacer_low_frequency_wanders() -> None:
    """RE-PINNED (interpreter-first): `encode_route` doesn't demote on
    frequency — it just bakes the frequency into the idle header byte — so
    the Moki pacer shape (Map032 EV027/068/070, freq 3) now plays as
    bytecode with the deterministic idle (102 for freq 3) instead of the old
    native WANDER_LEFT_AND_RIGHT random-pause approximation. This is exactly
    the pacing fix the interpreter exists for (WANDER randomizes; bytecode
    doesn't)."""
    route = _route([3, 3, 3, 2, 2, 2])
    spec = movement_spec_for(_move_page(3, route=route, frequency=3))
    assert spec.movement_type == MOVEMENT_TYPE_CUSTOM_ROUTE
    assert spec.route_bytecode == tuple(encode_route(route, 3))
    assert spec.route_bytecode[0] == 102  # idle header for move_frequency 3


def test_movement_spec_for_custom_vertical_pacer_low_frequency_wanders() -> None:
    """RE-PINNED (interpreter-first) — see pacer_low_frequency_wanders above
    (Map032 EV069/071 shape: up x2, down x2 at freq 3)."""
    route = _route([4, 4, 1, 1])
    spec = movement_spec_for(_move_page(3, route=route, frequency=3))
    assert spec.movement_type == MOVEMENT_TYPE_CUSTOM_ROUTE
    assert spec.route_bytecode == tuple(encode_route(route, 3))


# walk-sequence loops (case g2) -----------------------------------------------

def test_movement_spec_for_loop_out_and_back() -> None:
    """RE-PINNED (interpreter-first): Map032 EV048/EV072 shape (left, up x2,
    down x2, right) is an encodable multi-leg loop of all-cardinal steps, so
    it now plays as bytecode instead of the native WALK_SEQUENCE_LEFT_UP_
    DOWN_RIGHT approximation. Doubles as the "encodable multi-leg loop"
    interpreter-wiring case."""
    route = _route([2, 4, 4, 1, 1, 3], repeat=True)
    spec = movement_spec_for(_move_page(3, route=route, frequency=3))
    assert spec.movement_type == MOVEMENT_TYPE_CUSTOM_ROUTE
    expected = tuple(encode_route(route, 3))
    assert spec.route_bytecode == expected
    # idle, flags (skippable=0x01), LEFT UP UP DOWN DOWN RIGHT, END_LOOP
    assert expected == (102, 0x01, 2, 4, 4, 1, 1, 3, 0)
    assert spec.demoted is None


def test_movement_spec_for_loop_ring_with_mid_leg_spawn_shifts_anchor() -> None:
    """RE-PINNED (interpreter-first): Map032 EV008's ring (down x5, right x6,
    up x6, left x6 with mid-leg through-toggles, down x1) is all STEP +
    THROUGH_ON/OFF opcodes `encode_route` handles natively, so it now plays
    as bytecode. Doubles as the "through-toggle route" interpreter-wiring
    case (some steps, code 37, steps, code 38)."""
    codes = [1] * 5 + [3] * 6 + [4] * 6 + [2, 2, 37, 2, 2, 38, 2, 2, 1]
    route = _route(codes)
    spec = movement_spec_for(_move_page(3, route=route, frequency=6))
    assert spec.movement_type == MOVEMENT_TYPE_CUSTOM_ROUTE
    assert spec.route_bytecode == tuple(encode_route(route, 6))
    # THROUGH_ON (0x30) then THROUGH_OFF (0x31) both survive in the stream.
    assert 0x30 in spec.route_bytecode
    assert 0x31 in spec.route_bytecode
    assert spec.demoted is None


def test_movement_spec_for_loop_corner_spawn_rectangle() -> None:
    """RE-PINNED (interpreter-first) — see loop_out_and_back above."""
    route = _route([1, 1, 3, 3, 4, 4, 2, 2])
    spec = movement_spec_for(_move_page(3, route=route))
    assert spec.movement_type == MOVEMENT_TYPE_CUSTOM_ROUTE
    assert spec.route_bytecode == tuple(encode_route(route, 6))


def test_movement_spec_for_loop_zigzag_demotes() -> None:
    """RE-PINNED (interpreter-first): a zig-zag closed loop of cardinal steps
    has no native WALK_SEQUENCE analog (old case-h demotion), but the
    bytecode interpreter doesn't care about shape — it just replays the
    literal step sequence — so this now plays instead of demoting. This is
    exactly the interpreter's value-add: decorative patrol shapes the native
    classifier can't reproduce now play faithfully."""
    route = _route([1, 3, 1, 3, 4, 4, 2, 2])
    spec = movement_spec_for(_move_page(3, route=route))
    assert spec.movement_type == MOVEMENT_TYPE_CUSTOM_ROUTE
    assert spec.route_bytecode == tuple(encode_route(route, 6))
    assert spec.demoted is None


def test_movement_spec_for_custom_diagonal_code_demotes() -> None:
    """A DEMOTED route (diagonal code 5 is out of `encode_route`'s v1 scope)
    -> falls through to the EXISTING native/static fallback classifier,
    unchanged by the interpreter-first change: translation-only with no
    cardinal/loop analog -> case-h static demotion."""
    spec = movement_spec_for(_move_page(3, route=_route([5, 5, 5])))
    assert spec.route_bytecode is None
    assert spec.movement_type == "MOVEMENT_TYPE_FACE_DOWN"
    assert spec.demoted is not None


def test_walk_sequence_quirk_table_matches_fork_source() -> None:
    """`_WALK_SEQUENCE_QUIRKS` is a pinned copy of the fork's per-sequence
    loop-closure checks — re-derive every entry from the C source (CLAUDE.md
    §4.7: the fork is the source of truth, not our memory of it)."""
    import re

    src = ENGINE_MOVEMENT_C.read_text(encoding="utf-8")
    pattern = re.compile(
        r"MovementType_WalkSequence([A-Za-z]+)_Step1[^{]*\{"
        r".*?directionSequenceIndex == (\d) && objectEvent->initialCoords\.([xy])",
        re.DOTALL,
    )
    derived: dict[tuple[str, ...], tuple[int, str]] = {}
    for name, idx, axis in pattern.findall(src):
        dirs = tuple(re.findall(r"Up|Down|Left|Right", name))
        assert len(dirs) == 4, name
        derived[tuple(d.upper() for d in dirs)] = (int(idx), axis)
    assert derived == _WALK_SEQUENCE_QUIRKS


# static_face_spec -------------------------------------------------------------

def test_static_face_spec_uses_graphic_direction_and_reason() -> None:
    """No `facing` override -> derives from `page["graphic"]["direction"]`, same
    as before the parameter was added. This is the case `_demote` (custom-route
    case-h demotions, no passability data available) relies on — it must keep
    getting the authored graphic direction unchanged, never the simulated one."""
    spec = static_face_spec(_move_page(0, direction=8), "spawn locked")
    assert spec == MovementSpec("MOVEMENT_TYPE_FACE_UP", demoted="spawn locked")


def test_static_face_spec_explicit_facing_overrides_graphic_direction() -> None:
    """A caller with an RMXP route SIMULATION result (metadata_wiring, not yet
    landed) passes `facing` explicitly to demote to the simulated stall facing
    instead of the page's authored graphic direction — the blocked-move rule:
    an NPC that stalls against an obstacle has already turned to face it and
    stays turned that way, so the real on-PC facing can differ from whatever
    direction the page happened to author."""
    spec = static_face_spec(_move_page(0, direction=2), "blocked at spawn", facing="LEFT")
    assert spec == MovementSpec("MOVEMENT_TYPE_FACE_LEFT", demoted="blocked at spawn")


def test_static_face_spec_invalid_facing_fails_loud() -> None:
    """An unrecognized facing string must raise, not silently mint a garbage
    MOVEMENT_TYPE_FACE_SIDEWAYS constant (CLAUDE.md §4.5)."""
    with pytest.raises(ValueError, match="facing"):
        static_face_spec(_move_page(0, direction=2), "blocked at spawn", facing="SIDEWAYS")


# MapPassability ---------------------------------------------------------------

def _passability(
    layer0: list[int], layer1: list[int], passages: list[int],
    priorities: list[int] | None = None, width: int = 3,
    open_cells: set[tuple[int, int]] = frozenset(),
) -> MapPassability:
    height = len(layer0) // width
    map_json = {
        "tiles": {
            "xsize": width, "ysize": height, "zsize": 3,
            "data": layer0 + layer1 + [0] * len(layer0),
        }
    }
    tileset = {"passages": passages, "priorities": priorities or [0] * len(passages)}
    return MapPassability.from_map(map_json, tileset, open_cells=open_cells)


def test_map_passability_exit_blocked_by_upper_layer_decoration() -> None:
    """The Map032 EV012 shape: walkable ground under a passage-15 z1 tile —
    the RMXP scan hits the decoration first, all four exits blocked."""
    mp = _passability(
        layer0=[1, 1, 1], layer1=[0, 2, 0],
        passages=[0, 0, 15],
    )
    assert mp.exit_blocked(1, 0) is True
    assert mp.exit_blocked(0, 0) is False
    assert mp.cell_clear(1, 0) is False
    assert mp.cell_clear(0, 0) is True


def test_map_passability_priority_zero_ground_stops_scan() -> None:
    """A priority-0 fully-passable upper tile DECIDES passable — the blocked
    ground beneath it never gets scanned (RMXP layer rules)."""
    mp = _passability(
        layer0=[3, 3, 3], layer1=[0, 1, 0],
        passages=[0, 0, 0, 15],  # tile 3 (ground) blocked, tile 1 clear
        priorities=[0, 0, 0, 0],
    )
    assert mp.exit_blocked(1, 0) is False  # tile 1 decides at z1
    assert mp.exit_blocked(0, 0) is True  # bare blocked ground


def test_map_passability_open_cells_override() -> None:
    """Converter-level unblocks (map_set.WALKABLE_OVERRIDES) read fully open."""
    mp = _passability(
        layer0=[1, 1, 1], layer1=[0, 2, 0],
        passages=[0, 0, 15], open_cells={(1, 0)},
    )
    assert mp.exit_blocked(1, 0) is False
    assert mp.cell_clear(1, 0) is True


def test_map_passability_out_of_bounds_not_clear() -> None:
    mp = _passability(layer0=[1], layer1=[0], passages=[0, 0], width=1)
    assert mp.cell_clear(-1, 0) is False
    assert mp.cell_clear(0, 5) is False
    assert mp.exit_blocked(-1, 0) is False  # off-map spawn is a data bug, not a lock


def test_map_passability_standable_open_tile_true() -> None:
    """A bare-ground cell (passage 0, priority 0) is standable — this must
    equal the layout pass's collision==0 verdict for the same cell."""
    mp = _passability(layer0=[1, 1, 1], layer1=[0, 0, 0], passages=[0, 0])
    assert mp.standable(0, 0) is True


def test_map_passability_standable_sealed_top_layer_false() -> None:
    """The Map032 EV074 shape: a passage-15 z1 decoration over open ground —
    the first non-empty tile (top down) seals the cell, not standable."""
    mp = _passability(layer0=[1, 1, 1], layer1=[0, 2, 0], passages=[0, 0, 15])
    assert mp.standable(1, 0) is False
    assert mp.standable(0, 0) is True


def test_map_passability_standable_open_cells_override() -> None:
    """A converter-level unblock forces standable=True even over sealed tile
    data."""
    mp = _passability(
        layer0=[1, 1, 1], layer1=[0, 2, 0], passages=[0, 0, 15], open_cells={(1, 0)},
    )
    assert mp.standable(1, 0) is True


def test_map_passability_standable_out_of_bounds_false() -> None:
    mp = _passability(layer0=[1], layer1=[0], passages=[0, 0], width=1)
    assert mp.standable(-1, 0) is False
    assert mp.standable(0, 5) is False


# ObjectEvent.to_dict --------------------------------------------------------

def test_object_event_to_dict_emits_movement_range() -> None:
    oe = ObjectEvent(
        x=1, y=2, graphics_id="OBJ_EVENT_GFX_URANIUM_X", script="0x0",
        movement_type="MOVEMENT_TYPE_WALK_LEFT_AND_RIGHT",
        movement_range_x=2, movement_range_y=0,
    )
    d = oe.to_dict()
    assert d["movement_range_x"] == 2
    assert d["movement_range_y"] == 0


def test_object_event_to_dict_default_range_is_zero() -> None:
    oe = ObjectEvent(x=1, y=2, graphics_id="OBJ_EVENT_GFX_URANIUM_X", script="0x0")
    d = oe.to_dict()
    assert d["movement_range_x"] == 0
    assert d["movement_range_y"] == 0


# --- is_door_sheet -------------------------------------------------------------

@pytest.mark.parametrize(
    "name",
    ["PU-doors1", "pu-doors_2", "FKdoors", "fkdoors3", "PU-Doors-Building"],
)
def test_is_door_sheet_true(name: str) -> None:
    assert is_door_sheet(name) is True


@pytest.mark.parametrize("name", ["HGSS_000", "Rivaltheo", "", None, "PU-Chyinmunk"])
def test_is_door_sheet_false(name) -> None:
    assert is_door_sheet(name) is False
