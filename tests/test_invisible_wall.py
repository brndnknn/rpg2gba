"""Invisible walls (RMXP named, opacity-0, non-through, scriptless action page):
predicate, conditional visibility, and the generated transparent sprite."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from rpg2gba.conversion_agent.flag_registry import FlagRegistry
from rpg2gba.tileset_converter import map_constants as mc
from rpg2gba.tileset_converter import metadata_wiring as mw
from rpg2gba.tileset_converter.graphics.sprite_emit import _GEN_RELPATHS, emit_sprites
from rpg2gba.tileset_converter.graphics.sprites import (
    GBA_FRAME_PX,
    NUM_OUTPUT_FRAMES,
    ConvertedSprite,
)
from rpg2gba.tileset_converter.hidden_actor_bracket import never_visible_event_ids
from rpg2gba.tileset_converter.invisible_wall import (
    INVISIBLE_GFX,
    is_invisible_wall_event,
    is_invisible_wall_page,
)

import numpy as np

_END = {"code": 0, "indent": 0, "parameters": []}


def _wall_page(**overrides) -> dict:
    page = {
        "condition": {},
        "graphic": {"character_name": "HGSS_000", "opacity": 0, "direction": 2, "tile_id": 0},
        "move_type": 0,
        "list": [dict(_END)],
        "through": False,
        "direction_fix": False,
        "trigger": 0,
    }
    for key, value in overrides.items():
        if key in ("opacity", "character_name"):
            page["graphic"][key] = value
        else:
            page[key] = value
    return page


def _blank_ssa_page() -> dict:
    return {
        "condition": {"self_switch_valid": True, "self_switch_ch": "A"},
        "graphic": {"character_name": "", "opacity": 255, "direction": 2, "tile_id": 0},
        "move_type": 0,
        "list": [dict(_END)],
        "through": False,
        "direction_fix": False,
        "trigger": 0,
    }


def _pillar2(eid: int = 46, x: int = 18, y: int = 16) -> dict:
    return {"id": eid, "name": "Pillar2", "x": x, "y": y,
            "pages": [_wall_page(), _blank_ssa_page()]}


# --- (a) predicate -----------------------------------------------------------


def test_pillar2_shape_is_an_invisible_wall() -> None:
    assert is_invisible_wall_event(_pillar2()["pages"])


def test_trigger_1_is_not_a_wall() -> None:
    assert not is_invisible_wall_page(_wall_page(trigger=1))
    assert not is_invisible_wall_event([_wall_page(trigger=1), _blank_ssa_page()])


def test_through_is_not_a_wall() -> None:
    assert not is_invisible_wall_event([_wall_page(through=True), _blank_ssa_page()])


def test_nonempty_command_list_is_not_a_wall() -> None:
    cmds = [{"code": 101, "indent": 0, "parameters": ["hi"]}, dict(_END)]
    assert not is_invisible_wall_event([_wall_page(list=cmds), _blank_ssa_page()])


def test_later_visible_page_disqualifies_the_event() -> None:
    visible = _wall_page(opacity=255, character_name="Rivaltheo")
    visible["condition"] = {"self_switch_valid": True, "self_switch_ch": "A"}
    assert not is_invisible_wall_event([_wall_page(), visible])


def test_blank_tile_graphic_page_disqualifies_the_event() -> None:
    tile = _blank_ssa_page()
    tile["graphic"]["tile_id"] = 385  # a tile draws something
    assert not is_invisible_wall_event([_wall_page(), tile])


def test_only_blank_pages_is_not_a_wall() -> None:
    assert not is_invisible_wall_event([_blank_ssa_page()])


def test_wall_event_is_not_never_visible() -> None:
    map_json = {"events": [_pillar2()]}
    assert never_visible_event_ids(map_json) == set()


# --- (b) conditional hide + object_event ------------------------------------


def test_pillar2_gets_conditional_hide_and_invisible_object_event() -> None:
    reg = FlagRegistry()
    consts = mc.MapConstantRegistry(Path("x")).mint(66, "Burole Town Gym")
    map_json = {"map_id": 66, "events": [_pillar2()]}
    result = mw.build_object_events(
        map_json, consts, {66}, npc_gfx={}, flag_registry=reg,
        required_actor_ids={46},
    )
    assert len(result.object_events) == 1
    obj = result.object_events[0]
    assert (obj.x, obj.y) == (18, 16)
    assert obj.graphics_id == "OBJ_EVENT_GFX_RPG2GBA_INVISIBLE" == INVISIBLE_GFX
    assert obj.flag != "0"
    assert result.local_id_map["46"] == 1
    lines = result.transition_lines
    # Not an unconditional setflag: hidden, then un-hidden unless self-switch A
    # is set (the blank page wins), i.e. hidden only under self-switch A.
    assert lines[0] == "# EV046 Pillar2"
    assert lines[1] == f"setflag({obj.flag})"
    assert lines[2].startswith("if (!")
    assert lines[3] == f"    clearflag({obj.flag})"


def test_unreferenced_wall_still_spawns() -> None:
    """No script targets the wall, so it is not a required actor; it still
    spawns (it blocks in RMXP)."""
    reg = FlagRegistry()
    consts = mc.MapConstantRegistry(Path("x")).mint(66, "Burole Town Gym")
    map_json = {"map_id": 66, "events": [_pillar2(47, 20, 16)]}
    result = mw.build_object_events(
        map_json, consts, {66}, npc_gfx={}, flag_registry=reg,
    )
    assert [o.graphics_id for o in result.object_events] == [INVISIBLE_GFX]


def test_wall_without_blank_page_is_always_present() -> None:
    reg = FlagRegistry()
    consts = mc.MapConstantRegistry(Path("x")).mint(66, "Burole Town Gym")
    event = {"id": 5, "name": "block", "x": 1, "y": 1, "pages": [_wall_page()]}
    result = mw.build_object_events(
        {"map_id": 66, "events": [event]}, consts, {66}, npc_gfx={}, flag_registry=reg,
    )
    assert result.object_events[0].graphics_id == INVISIBLE_GFX
    assert result.object_events[0].flag == "0"
    assert result.transition_lines == []


# --- (c) generator -----------------------------------------------------------


def _sprite() -> ConvertedSprite:
    frame = np.zeros((GBA_FRAME_PX, GBA_FRAME_PX, 4), dtype=np.uint8)
    frame[0, 0] = (0, 0, 0, 255)
    return ConvertedSprite(
        name="aaa", frames=[frame.copy() for _ in range(NUM_OUTPUT_FRAMES)],
        cycle="neutral02", asymmetry=0.0, content_size=(1, 1),
    )


def test_emit_sprites_generates_the_invisible_graphic(tmp_path: Path) -> None:
    result = emit_sprites([_sprite()], tmp_path)
    # id follows the sorted URANIUM_* ids (388 + 1 sprite)
    assert result.gfx_ids[INVISIBLE_GFX] == 389
    read = {k: (tmp_path / p).read_text(encoding="utf-8") for k, p in _GEN_RELPATHS.items()}
    assert f"#define {INVISIBLE_GFX} 389" in read["constants"]
    assert "#define NUM_RPG2GBA_OBJ_EVENT_GFX 2" in read["constants"]
    assert "gObjectEventPic_Rpg2gbaInvisible[]" in read["graphics"]
    assert "-mwidth 2 -mheight 2" in read["graphics"].split("Rpg2gbaInvisible")[1]
    assert "sPicTable_Rpg2gbaInvisible" in read["pic_tables"]
    info = read["graphics_info"].split("gObjectEventGraphicsInfo_Rpg2gbaInvisible")[1]
    assert ".width = 16" in info and ".height = 16" in info
    assert ".anims = sAnimTable_Inanimate" in info
    assert "gObjectEventGraphicsInfo_Rpg2gbaInvisible;" in read["graphics_info_decls"]
    assert (
        f"[{INVISIBLE_GFX}] = &gObjectEventGraphicsInfo_Rpg2gbaInvisible,"
        in read["graphics_info_pointers"]
    )


def test_invisible_png_is_fully_transparent_16x16(tmp_path: Path) -> None:
    emit_sprites([_sprite()], tmp_path)
    png = tmp_path / "graphics/object_events/pics/uranium/rpg2gba_invisible.png"
    img = Image.open(png)
    assert img.mode == "P" and img.size == (16, 16)
    assert not np.asarray(img).any()  # every pixel is palette index 0 (transparent)


# --- map-level: a revealed actor is not a wall -------------------------------


def _host(eid: int, cmd: dict) -> dict:
    page = _wall_page(list=[cmd, dict(_END)], graphic={"character_name": "", "opacity": 255})
    return {"id": eid, "name": "host", "x": 0, "y": 0, "pages": [page]}


def test_wall_ids_plain_pillar_is_a_wall() -> None:
    from rpg2gba.tileset_converter.invisible_wall import invisible_wall_ids

    assert invisible_wall_ids([_pillar2()]) == {46}


def test_move_route_target_is_not_a_wall() -> None:
    from rpg2gba.tileset_converter.invisible_wall import invisible_wall_ids

    route = {"code": 209, "indent": 0, "parameters": [46, {"list": []}]}
    assert invisible_wall_ids([_pillar2(), _host(9, route)]) == set()


def test_player_and_self_route_targets_do_not_matter() -> None:
    from rpg2gba.tileset_converter.invisible_wall import invisible_wall_ids

    player = {"code": 209, "indent": 0, "parameters": [-1, {"list": []}]}
    assert invisible_wall_ids([_pillar2(), _host(9, player)]) == {46}


def test_script_get_character_target_is_not_a_wall() -> None:
    from rpg2gba.tileset_converter.invisible_wall import invisible_wall_ids

    script = {"code": 355, "indent": 0, "parameters": ["get_character(46).opacity = 255"]}
    assert invisible_wall_ids([_pillar2(), _host(9, script)]) == set()
    cont = {"code": 655, "indent": 0, "parameters": ["$game_map.events[46].opacity=255"]}
    assert invisible_wall_ids([_pillar2(), _host(9, cont)]) == set()


def test_revealed_wall_shape_is_not_placed_as_invisible() -> None:
    reg = FlagRegistry()
    consts = mc.MapConstantRegistry(Path("x")).mint(66, "Burole Town Gym")
    route = {"code": 209, "indent": 0, "parameters": [46, {"list": []}]}
    map_json = {"map_id": 66, "events": [_pillar2(), _host(9, route)]}
    try:
        result = mw.build_object_events(
            map_json, consts, {66}, npc_gfx={}, flag_registry=reg, required_actor_ids={46},
        )
    except KeyError:
        return  # falls back to the sheet path (HGSS_000 unmapped here): not the wall sprite
    assert all(o.graphics_id != INVISIBLE_GFX for o in result.object_events)
