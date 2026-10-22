"""game_profile: Settings.rb parsing and the generated rpg2gba_game.gen.h."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.game_profile import header, settings
from rpg2gba.game_profile.settings import (
    DEFAULT_SETTINGS_RB,
    SettingsError,
    badge_requirements,
    parse_settings,
    require_bool,
    require_int,
)


def _settings(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "Settings.rb"
    p.write_text(text, encoding="utf-8")
    return p


def test_parse_int_bool_and_ignores_noise(tmp_path):
    p = _settings(tmp_path, "A = 3\nB = true\nC = false\nD = 'x'\nE = -1 # note\n  F = 7\n")
    s = parse_settings(p)
    assert s == {"A": 3, "B": True, "C": False, "E": -1, "F": 7}


def test_later_assignment_wins(tmp_path):
    assert parse_settings(_settings(tmp_path, "A = 1\nA = 2\n")) == {"A": 2}


def test_missing_and_wrong_type_fail_loud(tmp_path):
    s = parse_settings(_settings(tmp_path, "A = true\nB = 2\n"))
    with pytest.raises(SettingsError):
        require_int(s, "MISSING")
    with pytest.raises(SettingsError):
        require_int(s, "A")
    with pytest.raises(SettingsError):
        require_bool(s, "B")


def test_real_settings_badges():
    s = parse_settings(DEFAULT_SETTINGS_RB)
    assert require_bool(s, "HIDDENMOVESCOUNTBADGES") is True
    assert badge_requirements(s) == {
        "cut": 3, "flash": 0, "rock_smash": 1, "strength": 4,
        "surf": 5, "dive": 7, "fly": 8, "waterfall": 8,
    }
    assert require_int(s, "STARTING_OVER_SWITCH") == 5


_BASE = "STARTING_OVER_SWITCH = 5\n"


def _fixture(tmp_path: Path, settings: str, label: str | None = "Starting Over") -> dict:
    rb = _settings(tmp_path, settings)
    sw = tmp_path / "sw.json"
    sw.write_text(json.dumps({"5": label} if label is not None else {}), encoding="utf-8")
    var = tmp_path / "var.json"
    var.write_text("{}", encoding="utf-8")
    mc = tmp_path / "mc.json"
    mc.write_text(json.dumps({"49": {"map_const": "MAP_X_HOUSE"}}), encoding="utf-8")
    md = tmp_path / "metadata.h"
    md.write_text("#define URANIUM_START_MAP 49\n#define URANIUM_START_X 7\n"
                  "#define URANIUM_START_Y 8\n#define URANIUM_START_DIR 2\n", encoding="utf-8")
    return dict(settings_rb=rb, switches_json=sw, variables_json=var,
                map_constants_json=mc, metadata_header=md)


def test_count_mode_rendered(tmp_path):
    kw = _fixture(tmp_path, _BASE + "HIDDENMOVESCOUNTBADGES = true\nBADGEFORCUT = 3\nBADGEFORFLASH = 0\n")
    text = header.render_header(header.build_facts(**kw))
    assert "#define RPG2GBA_FIELD_MOVE_BADGES_COUNT_MODE TRUE" in text
    assert "#define RPG2GBA_FIELD_MOVE_BADGE_CUT 3" in text
    assert "#define RPG2GBA_FIELD_MOVE_BADGE_FLASH 0" in text
    assert "BADGE_SURF" not in text   # absent constant -> stock gate


def test_specific_mode_rendered(tmp_path):
    kw = _fixture(tmp_path, _BASE + "HIDDENMOVESCOUNTBADGES = false\nBADGEFORSURF = 5\n")
    text = header.render_header(header.build_facts(**kw))
    assert "COUNT_MODE FALSE" in text
    assert "#define RPG2GBA_FIELD_MOVE_BADGE_SURF 5" in text
    assert "#define RPG2GBA_NEW_GAME_MAP MAP_X_HOUSE" in text
    assert "#define RPG2GBA_NEW_GAME_Y 8" in text


def test_no_badges_omits_gate_macros(tmp_path):
    kw = _fixture(tmp_path, _BASE)
    text = header.render_header(header.build_facts(**kw))
    assert "FIELD_MOVE" not in text


def test_fail_loud_cases(tmp_path):
    with pytest.raises(SettingsError):   # badges without the mode flag
        header.build_facts(**_fixture(tmp_path, _BASE + "BADGEFORCUT = 3\n"))
    with pytest.raises(SettingsError):   # no white-out switch setting
        header.build_facts(**_fixture(tmp_path, "HIDDENMOVESCOUNTBADGES = true\n"))
    with pytest.raises(SettingsError):   # unnamed switch
        header.build_facts(**_fixture(tmp_path, _BASE, label=None))
    with pytest.raises(SettingsError):   # runtime predicate
        header.build_facts(**_fixture(tmp_path, _BASE, label="s:Night"))
    with pytest.raises(SettingsError):   # out of range
        header.build_facts(**_fixture(
            tmp_path, _BASE + "HIDDENMOVESCOUNTBADGES = true\nBADGEFORCUT = 9\n"))


def test_install_is_byte_stable(tmp_path):
    kw = _fixture(tmp_path, _BASE + "HIDDENMOVESCOUNTBADGES = true\nBADGEFORCUT = 3\n")
    fork = tmp_path / "fork"
    rel = header.install(fork, **kw)
    first = (fork / rel).read_bytes()
    header.install(fork, **kw)
    assert (fork / rel).read_bytes() == first
    assert rel == Path("include/config/rpg2gba_game.gen.h")


def test_real_data_golden():
    meta = Path("output/uranium-build/include/constants/metadata.h")
    if not meta.exists():
        pytest.skip("build artifacts absent")
    facts = header.build_facts()
    assert facts.new_game_map == "MAP_MOKI_TOWN_PLAYERS_HOUSE_1F"
    assert (facts.new_game_x, facts.new_game_y) == (7, 7)
    assert facts.new_game_heal_location == "HEAL_LOCATION_URANIUM_START"
    assert facts.whiteout_flag == "FLAG_STARTING_OVER"
    text = header.render_header(facts)
    for line in (
        "#define RPG2GBA_FIELD_MOVE_BADGES_COUNT_MODE TRUE",
        "#define RPG2GBA_FIELD_MOVE_BADGE_CUT 3",
        "#define RPG2GBA_FIELD_MOVE_BADGE_FLASH 0",
        "#define RPG2GBA_FIELD_MOVE_BADGE_ROCK_SMASH 1",
        "#define RPG2GBA_FIELD_MOVE_BADGE_STRENGTH 4",
        "#define RPG2GBA_FIELD_MOVE_BADGE_SURF 5",
        "#define RPG2GBA_FIELD_MOVE_BADGE_DIVE 7",
        "#define RPG2GBA_FIELD_MOVE_BADGE_FLY 8",
        "#define RPG2GBA_FIELD_MOVE_BADGE_WATERFALL 8",
        "#define RPG2GBA_WHITEOUT_FLAG FLAG_STARTING_OVER",
        "#define RPG2GBA_NEW_GAME_MAP MAP_MOKI_TOWN_PLAYERS_HOUSE_1F",
    ):
        assert line in text


def test_c_macros_all_emitted():
    """Every RPG2GBA_* game macro the engine C reads is one the renderer can emit."""
    engine = Path("engine")
    used: set[str] = set()
    import re
    pat = re.compile(r"\bRPG2GBA_(?:FIELD_MOVE_BADGE\w*|WHITEOUT_FLAG|NEW_GAME_\w+|PHONE_\w+)\b")
    for rel in ("src/field_move.c", "src/overworld.c", "src/new_game.c", "src/strings.c",
                "data/event_scripts.s"):
        used |= set(pat.findall((engine / rel).read_text(encoding="utf-8")))
    facts = header.GameFacts(
        badges_count_mode=True,
        badge_requirements={k: 1 for k in header._BADGE_ORDER},
        whiteout_flag="FLAG_X", new_game_map="MAP_X", new_game_x=1, new_game_y=1,
        new_game_heal_location="HEAL_LOCATION_X", phone_name="POKéPOD")
    text = header.render_header(facts)
    # Names ending in _X/_CUT style are matched by prefix only where C builds the name by token paste.
    for name in used:
        assert f"#define {name} " in text, name


def test_phone_name_from_the_games_registration_message():
    """#141: the dump says "PokÃ©pod" (mojibake); the reader returns the real word,
    and the UI form keeps the accented e lower case, as in POKéNAV."""
    assert settings.phone_name() == "Poképod"
    assert header.ui_caps("Poképod") == "POKéPOD"


def test_phone_text_redefines_the_registration_line():
    facts = header.GameFacts(
        badges_count_mode=None, badge_requirements={}, whiteout_flag="FLAG_X",
        new_game_map="MAP_X", new_game_x=1, new_game_y=1,
        new_game_heal_location="HEAL_LOCATION_X", phone_name="POKéPOD")
    text = header.render_phone_text(facts)
    assert "gText_RegisteredTrainerinPokeNav::" in text
    assert '.string "in the POKéPOD.$"' in text
    assert '#define RPG2GBA_PHONE_MENU_LABEL _("POKéPOD")' in header.render_header(facts)


def test_regional_dex_name_from_dex_names():
    assert settings.regional_dex_name() == "Tandor"
