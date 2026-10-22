"""Region-map sections from Uranium's ShowArea locations (PROJECT_TODO #140)."""
from __future__ import annotations

import pytest

from rpg2gba.tileset_converter import map_sections as ms
from rpg2gba.tileset_converter.map_constants import MapConstants
from rpg2gba.tileset_converter.metadata_wiring import MapFile

# A town (32) with a house (48) whose upstairs is 49; a cave whose two floors both
# show "Passage Cave" (36, 37 under 36); a map under the root with no ShowArea (18).
MAP_INFOS = {
    "55": {"name": "GAME", "parent_id": 0},
    "32": {"name": "Moki Town", "parent_id": 55},
    "48": {"name": "\\PN's house", "parent_id": 32},
    "49": {"name": "\\PN's house", "parent_id": 48},
    "36": {"name": "Passage Cave", "parent_id": 55},
    "37": {"name": "Passage Cave", "parent_id": 36},
    "18": {"name": "Route 11", "parent_id": 55},
}
METADATA = {
    "32": {"outdoor": True, "show_area": True},
    "36": {"show_area": True},
    "37": {"show_area": True},
    "48": {"map_position": [0, 13, 18]},
}


def test_show_area_map_is_its_own_section() -> None:
    assert ms.section_for(32, MAP_INFOS, METADATA) == ms.MapSection("MAPSEC_MOKI_TOWN", "MOKI TOWN")


def test_interiors_take_the_nearest_show_area_ancestor() -> None:
    assert ms.section_for(48, MAP_INFOS, METADATA).const == "MAPSEC_MOKI_TOWN"
    assert ms.section_for(49, MAP_INFOS, METADATA).const == "MAPSEC_MOKI_TOWN"


def test_floors_with_one_name_share_a_section() -> None:
    assert ms.section_for(36, MAP_INFOS, METADATA) == ms.section_for(37, MAP_INFOS, METADATA)


def test_no_show_area_ancestor_fails_loud() -> None:
    with pytest.raises(ValueError, match="no ShowArea map"):
        ms.section_for(18, MAP_INFOS, METADATA)


def test_popup_follows_the_maps_own_show_area() -> None:
    assert ms.shows_map_name(32, METADATA) is True
    assert ms.shows_map_name(48, METADATA) is False
    assert ms.shows_map_name(49, METADATA) is False


UPSTREAM = {"map_sections": [
    {"id": "MAPSEC_LITTLEROOT_TOWN", "name": "LITTLEROOT TOWN", "x": 4, "y": 11, "width": 1, "height": 1},
    {"id": "MAPSEC_VICTORY_ROAD", "name": "VICTORY ROAD"},
]}


def test_overlay_appends_sorted_unique_sections_after_upstream() -> None:
    moki = ms.MapSection("MAPSEC_MOKI_TOWN", "MOKI TOWN")
    cave = ms.MapSection("MAPSEC_PASSAGE_CAVE", "PASSAGE CAVE")
    merged = ms.overlay_sections(UPSTREAM, [moki, cave, moki])
    assert merged["map_sections"][:2] == UPSTREAM["map_sections"]
    assert merged["map_sections"][2:] == [
        {"id": "MAPSEC_MOKI_TOWN", "name": "MOKI TOWN"},
        {"id": "MAPSEC_PASSAGE_CAVE", "name": "PASSAGE CAVE"},
    ]
    assert len(UPSTREAM["map_sections"]) == 2  # input untouched


def test_overlay_refuses_a_stock_section_name() -> None:
    with pytest.raises(ValueError, match="collides with a stock"):
        ms.overlay_sections(UPSTREAM, [ms.MapSection("MAPSEC_VICTORY_ROAD", "VICTORY ROAD")])


def test_overlay_refuses_two_spellings_of_one_constant() -> None:
    with pytest.raises(ValueError, match="named both"):
        ms.overlay_sections(UPSTREAM, [
            ms.MapSection("MAPSEC_X", "X"), ms.MapSection("MAPSEC_X", "X!"),
        ])


def test_overlay_refuses_to_reach_the_metloc_specials() -> None:
    upstream = {"map_sections": [{"id": f"MAPSEC_S{i}", "name": "S"} for i in range(ms.METLOC_SPECIAL_START - 1)]}
    ms.overlay_sections(upstream, [])  # MAPSEC_NONE = 0xFC: still fits
    with pytest.raises(ValueError, match="METLOC"):
        ms.overlay_sections(upstream, [ms.MapSection("MAPSEC_NEW", "NEW")])


def _consts() -> MapConstants:
    return MapConstants(
        uranium_id=48, map_const="MAP_X", alias_const="MAP_URANIUM_48", layout_const="LAYOUT_X",
        mapsec_const="MAPSEC_X", dir_name="X", display_name="X",
    )


def test_map_file_show_map_name_overrides_the_town_rule() -> None:
    town = MapFile(consts=_consts(), map_type="MAP_TYPE_TOWN", show_map_name=False)
    assert town.to_json_dict()["show_map_name"] is False
    indoor = MapFile(consts=_consts(), map_type="MAP_TYPE_INDOOR", show_map_name=True,
                     region_map_section="MAPSEC_MOKI_TOWN")
    d = indoor.to_json_dict()
    assert d["show_map_name"] is True
    assert d["region_map_section"] == "MAPSEC_MOKI_TOWN"
    # Legacy default: the popup follows map_type.
    assert MapFile(consts=_consts(), map_type="MAP_TYPE_TOWN").to_json_dict()["show_map_name"] is True
