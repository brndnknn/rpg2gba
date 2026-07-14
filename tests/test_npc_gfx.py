"""Unit tests for npc_gfx.py — Uranium NPC sheet -> OBJ_EVENT_GFX_* + RMXP
boot-page semantics (boot-page selection, movement mapping, door predicate)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.tileset_converter.metadata_wiring import ObjectEvent
from rpg2gba.tileset_converter.npc_gfx import (
    MovementSpec,
    gfx_constant_for_sheet,
    is_door_sheet,
    load_npc_gfx_map,
    movement_spec_for,
    select_boot_page,
)

REAL_NPC_GFX_MAP = Path("reference/npc_gfx_map.json")


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
    defines every gfx constant it mints (18 entries)."""
    raw = json.loads(REAL_NPC_GFX_MAP.read_text(encoding="utf-8"))
    gfx_names = [entry["gfx"] for entry in raw.values()]
    headers = _headers_for(tmp_path, gfx_names)
    result = load_npc_gfx_map(REAL_NPC_GFX_MAP, headers)
    assert len(result) == 18
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

def _move_page(move_type: int, direction: int = 2, route: dict | None = None) -> dict:
    page = {
        "move_type": move_type,
        "graphic": {"character_name": "X", "direction": direction},
    }
    if route is not None:
        page["move_route"] = route
    return page


def _route(codes: list[int], repeat: bool = True) -> dict:
    """A `move_route` dict for `codes` in order, with the RMXP-mandated
    trailing code-0 sentinel entry appended (`movement_spec_for` strips it)."""
    return {
        "repeat": repeat,
        "skippable": True,
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


def test_movement_spec_for_unknown_move_type_fails_loud() -> None:
    with pytest.raises(ValueError, match="move_type"):
        movement_spec_for(_move_page(99, 2))


def test_movement_spec_for_unknown_direction_fails_loud() -> None:
    with pytest.raises(ValueError, match="direction"):
        movement_spec_for(_move_page(0, 3))


# random (move_type 1) -----------------------------------------------------------

def test_movement_spec_for_random_wanders() -> None:
    assert movement_spec_for(_move_page(1, 2)) == MovementSpec("MOVEMENT_TYPE_WANDER_AROUND", 0, 0)


# approach player (move_type 2) --------------------------------------------------

def test_movement_spec_for_approach_fails_loud() -> None:
    """No native pokeemerald analog, zero occurrences corpus-wide — fail loud
    rather than guess at a substitute (SLICE1_TODO #12)."""
    with pytest.raises(ValueError, match="approach player"):
        movement_spec_for(_move_page(2, 2))


# custom route (move_type 3) -----------------------------------------------------

def test_movement_spec_for_custom_repeat_false_is_static() -> None:
    """A one-shot (repeat=False) route plays once at boot, then stands — not a
    demotion, even though the route itself translates."""
    route = _route([3, 3, 3], repeat=False)
    spec = movement_spec_for(_move_page(3, direction=6, route=route))
    assert spec.movement_type == "MOVEMENT_TYPE_FACE_RIGHT"
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
    spec = movement_spec_for(_move_page(3, route=_route([16, 19])))
    assert spec.movement_type == "MOVEMENT_TYPE_FACE_DOWN_AND_UP"
    assert spec.demoted is None


def test_movement_spec_for_custom_turn_pair_left_right() -> None:
    spec = movement_spec_for(_move_page(3, route=_route([17, 18])))
    assert spec.movement_type == "MOVEMENT_TYPE_FACE_LEFT_AND_RIGHT"


def test_movement_spec_for_custom_single_turn_face_left() -> None:
    """A single turn code faces its OWN direction, not `graphic.direction`."""
    spec = movement_spec_for(_move_page(3, direction=8, route=_route([17])))
    assert spec.movement_type == "MOVEMENT_TYPE_FACE_LEFT"


def test_movement_spec_for_custom_turn_triple_down_up_left() -> None:
    spec = movement_spec_for(_move_page(3, route=_route([16, 17, 19])))
    assert spec.movement_type == "MOVEMENT_TYPE_FACE_DOWN_UP_AND_LEFT"


def test_movement_spec_for_custom_relative_turn_looks_around() -> None:
    """Any 20..26 relative/random/player-relative turn code forces the
    direction set to all four, regardless of what else is present."""
    spec = movement_spec_for(_move_page(3, route=_route([24])))
    assert spec.movement_type == "MOVEMENT_TYPE_LOOK_AROUND"


def test_movement_spec_for_custom_pacer_wide() -> None:
    spec = movement_spec_for(_move_page(3, route=_route([2, 2, 2, 3, 3, 3])))
    assert spec.movement_type == "MOVEMENT_TYPE_WALK_LEFT_AND_RIGHT"
    assert spec.range_x == 2
    assert spec.range_y == 0
    assert spec.demoted is None


def test_movement_spec_for_custom_pacer_narrow() -> None:
    spec = movement_spec_for(_move_page(3, route=_route([2, 2, 3, 3])))
    assert spec.movement_type == "MOVEMENT_TYPE_WALK_LEFT_AND_RIGHT"
    assert spec.range_x == 1
    assert spec.range_y == 0


def test_movement_spec_for_custom_pacer_with_waits_wanders() -> None:
    """A WAIT code anywhere in the loop -> the pause-y WANDER_ variant, not the
    continuous WALK_ variant."""
    spec = movement_spec_for(_move_page(3, route=_route([2, 15, 3, 15])))
    assert spec.movement_type == "MOVEMENT_TYPE_WANDER_LEFT_AND_RIGHT"
    assert spec.range_x == 1
    assert spec.range_y == 0


def test_movement_spec_for_custom_vertical_pacer() -> None:
    spec = movement_spec_for(_move_page(3, route=_route([1, 1, 4, 4])))
    assert spec.movement_type == "MOVEMENT_TYPE_WALK_UP_AND_DOWN"
    assert spec.range_x == 0
    assert spec.range_y == 1


def test_movement_spec_for_custom_random_move_loop_wanders() -> None:
    """TRANSLATION == {9} only (waits/neutral fine) -> WANDER_AROUND, same as
    move_type 1."""
    spec = movement_spec_for(_move_page(3, route=_route([9, 15])))
    assert spec == MovementSpec("MOVEMENT_TYPE_WANDER_AROUND", 0, 0)


def test_movement_spec_for_custom_net_drift_demotes() -> None:
    """A loop that doesn't return to its start drifts a little further every
    pass -- can't be a bounded pokeemerald patrol -> demoted static."""
    spec = movement_spec_for(_move_page(3, direction=4, route=_route([2, 2])))
    assert spec.movement_type == "MOVEMENT_TYPE_FACE_LEFT"
    assert spec.demoted is not None
    assert "drift" in spec.demoted


def test_movement_spec_for_custom_mixed_axes_demotes() -> None:
    spec = movement_spec_for(_move_page(3, route=_route([2, 1])))
    assert spec.movement_type == "MOVEMENT_TYPE_FACE_DOWN"
    assert spec.demoted is not None


def test_movement_spec_for_custom_toward_player_demotes() -> None:
    """Code 10 (toward-player) has no native pokeemerald analog."""
    spec = movement_spec_for(_move_page(3, route=_route([10])))
    assert spec.demoted is not None


def test_movement_spec_for_custom_translation_and_turn_mixed_demotes() -> None:
    """A route that both walks and spins has no native equivalent."""
    spec = movement_spec_for(_move_page(3, route=_route([2, 16])))
    assert spec.demoted is not None


def test_movement_spec_for_custom_missing_move_route_fails_loud() -> None:
    """A move_type 3 page with no `move_route` key at all is malformed input,
    not "nothing to do" -- KeyError propagates (CLAUDE.md §4.5)."""
    with pytest.raises(KeyError):
        movement_spec_for(_move_page(3))


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
