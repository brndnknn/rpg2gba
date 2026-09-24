"""`engine_flag_write` -- C8 ruling (b)'s engine-held unlocks, asserted by the floor.

story_state writes an `EngineKey` for `$PokemonGlobal.runningShoes=true` and its
three siblings; the floor turns that write into `engine_flag_write` on the native
`FLAG_SYS_*`, and the generic template checks it in the ROM with one flag read.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.beat_floor import walk
from rpg2gba.playtest.archetypes import generic
from rpg2gba.playtest.errors import ScenarioError
from rpg2gba.ruby_subset.builtins import ENGINE_ATTRIBUTES

MAP_ID = 1
ROW_ID = "map001/ev001/p0"
MAPS_DIR = Path(__file__).resolve().parents[1] / "output" / "uranium-build" / "maps"


def _row(script: str):
    commands = [{"code": 355, "parameters": [script]}]
    map_data = {"events": [{"id": 1, "pages": [
        {"trigger": 0, "condition": {}, "list": commands}]}]}
    rows = walk.floor_for_map(
        MAP_ID, map_data, common_events=[], switch_labels={}, door_cells={})
    return rows[ROW_ID]


def _flag_writes(row):
    return [a for a in row.assertions if a.kind == "engine_flag_write"]


@pytest.mark.parametrize(("namespace", "attribute"), sorted(ENGINE_ATTRIBUTES))
def test_every_unlock_attribute_becomes_its_native_flag(namespace, attribute):
    row = _row(f"{namespace}.{attribute}=true")
    (a,) = _flag_writes(row)
    assert a.param("flag") == ENGINE_ATTRIBUTES[(namespace, attribute)].flag
    assert a.param("value") is True
    assert a.list_index == 0
    assert a.tag == "state"
    assert not row.refused
    assert row.offline_eligible  # same standing as switch_write


def test_split_row_write_still_asserts_once():
    row = _row("$PokemonGlobal.seenStorageCreator=\ntrue")
    assert [a.param("flag") for a in _flag_writes(row)] == ["FLAG_SYS_PC_LANETTE"]


def test_non_unlock_engine_keys_are_not_flags():
    # The respawn anchor is an EngineKey too, but not an unlock: no flag.
    row = _row("Kernel.pbSetPokemonCenter")
    assert _flag_writes(row) == []


@pytest.mark.skipif(not MAPS_DIR.is_dir(), reason="output/uranium-build/maps not staged")
def test_running_shoes_row_asserts_b_dash_in_the_real_corpus():
    data = json.loads((MAPS_DIR / "Map049.json").read_text(encoding="utf-8"))
    rows = walk.floor_for_map(
        49, data, common_events=[], switch_labels={}, door_cells={})
    flags = [a.param("flag") for a in _flag_writes(rows["map049/ev001/p0"])]
    assert flags == ["FLAG_SYS_B_DASH"]


class _FakeEmu:
    def __init__(self, flags: dict[str, bool]) -> None:
        self.flags = flags

    def flag(self, name: str) -> bool:
        return self.flags[name]

    def screenshot(self, name: str) -> str:
        return f"{name}.png"


def _step(value: bool = True) -> generic.Step:
    return generic.Step(
        row_id=ROW_ID, kind="engine_flag_write", list_index=0,
        params=(("flag", "FLAG_SYS_B_DASH"), ("value", value)))


def test_handler_passes_when_the_flag_is_set():
    generic.STEP_HANDLERS["engine_flag_write"](_FakeEmu({"FLAG_SYS_B_DASH": True}), "B1", _step())


def test_handler_fails_loud_when_the_flag_is_clear():
    with pytest.raises(ScenarioError, match="FLAG_SYS_B_DASH reads False"):
        generic.STEP_HANDLERS["engine_flag_write"](
            _FakeEmu({"FLAG_SYS_B_DASH": False}), "B1", _step())
