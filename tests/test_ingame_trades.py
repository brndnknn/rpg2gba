"""NPC in-game trades: Uranium pbStartTrade -> native sIngameTrades rows."""
import json
from pathlib import Path

import pytest

from rpg2gba import ingame_trades as it

LIMITS = it.NameLimits(pokemon_name=12, trainer_name=10)
SPECIES = {
    "FARTOG": "SPECIES_FARTOG",
    "BAASHAUN": "SPECIES_BAASHAUN",
}


def resolve(name: str) -> str | None:
    return SPECIES.get(name)


def _script(lines: list[str], indent: int = 2) -> list[dict]:
    cmds = [{"code": 355, "indent": indent, "parameters": [lines[0]]}]
    cmds += [{"code": 655, "indent": indent, "parameters": [ln]} for ln in lines[1:]]
    return cmds


CHOOSE = [
    "pbChoosePokemon(1,3,",
    "proc {|poke|",
    " !poke.egg? and ",
    "  poke.species==PBSpecies::FARTOG",
    "})",
]


def _trade(nick: str = "Yuoaman", ot: str = "Baro", extra: str = "") -> list[str]:
    return [
        "pbStartTrade(",
        "pbGet(1),",
        "PBSpecies::BAASHAUN,",
        f'"{nick}",',
        f'"{ot}"{extra}',
        ")",
    ]


def _map(choose: list[str] = CHOOSE, trade: list[str] | None = None,
         event_id: int = 14) -> dict:
    page_list = (
        [{"code": 355, "indent": 1, "parameters": ["pbChoosePokemon(1,3)"]}]  # plain, unrelated
        + _script(choose)
        + [{"code": 111, "indent": 2, "parameters": [1, 1, 0, -1, 5]}]
        + _script(trade if trade is not None else _trade(), 3)
        + [{"code": 0, "indent": 0, "parameters": []}]
    )
    return {"events": [{"id": event_id, "name": "EV014", "pages": [{"list": page_list}]}]}


def test_golden_spec_ev014_shape() -> None:
    specs = it.detect_trades_in_map(_map(), 46, resolve, LIMITS)
    assert len(specs) == 1
    s = specs[0]
    assert s.const == "INGAME_TRADE_MAP046_EV014"
    assert (s.map_id, s.event_id, s.page) == (46, 14, 0)
    assert s.species == "SPECIES_BAASHAUN"
    assert s.requested_species == "SPECIES_FARTOG"
    assert (s.nickname, s.ot_name, s.ot_gender) == ("Yuoaman", "Baro", 0)


def test_explicit_gender_arg() -> None:
    specs = it.detect_trades_in_map(_map(trade=_trade(extra=",1")), 46, resolve, LIMITS)
    assert specs[0].ot_gender == 1
    assert ".otGender = FEMALE" in it.emit_table(specs)


def test_split_piece_names_by_origin() -> None:
    assert it.trade_const(14000, 5) == "INGAME_TRADE_MAP040_EV005"
    assert it.trade_const(46, 14) == "INGAME_TRADE_MAP046_EV014"
    specs = it.detect_trades_in_map(_map(), 14003, resolve, LIMITS)
    assert specs[0].const == "INGAME_TRADE_MAP040_EV014"
    assert specs[0].map_id == 14003


def test_unsupported_filter_fails_loud() -> None:
    bad = ["pbChoosePokemon(1,3,", "proc {|poke|", " poke.species==PBSpecies::FARTOG", "})"]
    with pytest.raises(ValueError, match="unsupported pbChoosePokemon filter"):
        it.detect_trades_in_map(_map(choose=bad), 46, resolve, LIMITS)


def test_trade_without_filter_fails_loud() -> None:
    m = _map()
    # only the plain (filterless) choose precedes the trade
    m["events"][0]["pages"][0]["list"] = (
        [{"code": 355, "indent": 1, "parameters": ["pbChoosePokemon(1,3)"]}]
        + _script(_trade(), 3)
    )
    with pytest.raises(ValueError, match="no preceding"):
        it.detect_trades_in_map(m, 46, resolve, LIMITS)


def test_overlong_nickname_fails_loud() -> None:
    with pytest.raises(ValueError, match="nickname"):
        it.detect_trades_in_map(_map(trade=_trade(nick="A" * 13)), 46, resolve, LIMITS)


def test_overlong_ot_name_fails_loud() -> None:
    with pytest.raises(ValueError, match="OT name"):
        it.detect_trades_in_map(_map(trade=_trade(ot="B" * 11)), 46, resolve, LIMITS)


def test_unstaged_species_fails_loud() -> None:
    with pytest.raises(ValueError, match="not staged"):
        it.detect_trades_in_map(_map(), 46, lambda n: None, LIMITS)


def test_scan_idempotent_and_rendered_text(tmp_path: Path) -> None:
    (tmp_path / "Map046.json").write_text(json.dumps(_map()), encoding="utf-8")
    a = it.scan_trades(tmp_path, [46], resolve, LIMITS)
    b = it.scan_trades(tmp_path, [46], resolve, LIMITS)
    assert a == b
    assert it.emit_enum(a) == it.emit_enum(b)
    assert it.emit_table(a) == it.emit_table(b)

    enum = it.emit_enum(a)
    assert "#define URANIUM_INGAME_TRADE_MEMBERS \\\n    INGAME_TRADE_MAP046_EV014,\n" in enum
    table = it.emit_table(a)
    for line in (
        "[INGAME_TRADE_MAP046_EV014] =",
        '.nickname = _("Yuoaman"),',
        ".species = SPECIES_BAASHAUN,",
        ".ivs = {15, 15, 15, 15, 15, 15},",
        ".abilityNum = 0,",
        ".conditions = {0, 0, 0, 0, 0},",
        ".heldItem = ITEM_NONE,",
        ".mailNum = -1,",
        '.otName = _("Baro"),',
        ".otGender = MALE,",
        ".sheen = 0,",
        ".requestedSpecies = SPECIES_FARTOG",
    ):
        assert line in table
    assert f".personality = {a[0].personality:#010x}," in table
    assert f".otId = {a[0].ot_id}," in table


def test_zero_trades_emit_valid_empty_fragments() -> None:
    assert it.emit_enum([]).rstrip().endswith("#define URANIUM_INGAME_TRADE_MEMBERS")
    assert "[INGAME_TRADE" not in it.emit_table([])


def test_missing_map_file_fails_loud(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        it.scan_trades(tmp_path, [46], resolve, LIMITS)


def test_enum_and_table_filenames_distinct() -> None:
    # both land in one out dir; a clash silently overwrites one fragment
    assert it.ENUM_FILENAME != it.TABLE_FILENAME
