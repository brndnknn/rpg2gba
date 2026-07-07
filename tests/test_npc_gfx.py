"""Unit tests for npc_gfx.py — Uranium NPC sheet -> OBJ_EVENT_GFX_* + RMXP
boot-page semantics (boot-page selection, movement mapping, door predicate)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.tileset_converter.npc_gfx import (
    gfx_constant_for_sheet,
    is_door_sheet,
    load_npc_gfx_map,
    movement_type_for,
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


# --- movement_type_for ---------------------------------------------------------

def _move_page(move_type: int, direction: int | None = None) -> dict:
    graphic = {"character_name": "X"}
    if direction is not None:
        graphic["direction"] = direction
    return {"move_type": move_type, "graphic": graphic}


@pytest.mark.parametrize(
    "direction, facing",
    [(2, "DOWN"), (4, "LEFT"), (6, "RIGHT"), (8, "UP")],
)
def test_movement_type_for_fixed_facings(direction: int, facing: str) -> None:
    assert movement_type_for(_move_page(0, direction)) == f"MOVEMENT_TYPE_FACE_{facing}"


@pytest.mark.parametrize("move_type", [0, 2, 3])
def test_movement_type_for_approach_and_custom_use_direction(move_type: int) -> None:
    assert movement_type_for(_move_page(move_type, 6)) == "MOVEMENT_TYPE_FACE_RIGHT"


def test_movement_type_for_random_wanders() -> None:
    assert movement_type_for(_move_page(1, 2)) == "MOVEMENT_TYPE_WANDER_AROUND"


def test_movement_type_for_unknown_move_type_fails_loud() -> None:
    with pytest.raises(ValueError, match="move_type"):
        movement_type_for(_move_page(99, 2))


def test_movement_type_for_unknown_direction_fails_loud() -> None:
    with pytest.raises(ValueError, match="direction"):
        movement_type_for(_move_page(0, 3))


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
