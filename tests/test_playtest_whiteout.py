"""Tests for `src/rpg2gba/playtest/whiteout.py`.

Same discipline as `tests/test_playtest.py`'s `_FakeEmu`: no mgba
dependency, so these run everywhere. `force_white_out`/`whiteout_beat`
duck-type `Emulator` (only `TYPE_CHECKING`-imported), so a plain fake
object exercises them without importing `playtest.emulator` at all.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.playtest.chapter import ChapterBuilder
from rpg2gba.playtest.errors import ScenarioError
from rpg2gba.playtest.whiteout import (
    DEFAULT_HEAL_LOCATIONS_JSON,
    force_white_out,
    load_heal_location,
    read_last_heal_location,
    whiteout_beat,
)


class _FakeMemory:
    """Sparse little-endian byte store, same shape as test_playtest.py's."""

    def __init__(self) -> None:
        self._bytes: dict[int, int] = {}

    def get(self, addr: int, width: int) -> int:
        value = 0
        for i in range(width):
            value |= self._bytes.get(addr + i, 0) << (8 * i)
        return value

    def set(self, addr: int, width: int, value: int) -> None:
        for i in range(width):
            self._bytes[addr + i] = (value >> (8 * i)) & 0xFF


_OFFSETS = {
    "off_main_state": 0x438,
    "off_main_callback2": 0x004,
    "off_sb1_lastheallocation": 0x1C,
}
_SB1_ADDR = 0x02020000
_MAIN_ADDR = 0x03000000
_CB2_OVERWORLD_ADDR = 0x08010000
_CB2_WHITEOUT_ADDR = 0x08020000


class _FakeEmu:
    """Duck-typed stand-in for `Emulator`.

    `overworld_input_ready`/`run` model `CB2_WhiteOut`'s real state
    machine: writing `gMain.callback2` to `CB2_WhiteOut | 1` and then
    running frames increments `gMain.state` each `run()` call, and once it
    reaches 120 the fake snaps `callback2` back to `CB2_Overworld | 1` --
    same handoff shape as the real engine (`overworld.c:1927-1951`), so the
    poll loop in `force_white_out` has something real to observe.
    """

    def __init__(self, *, last_heal_location: tuple[int, int] = (3, 5),
                 frames_to_finish: int = 120,
                 engine_sets_starting_over: bool = True,
                 heal_page_clears_it: bool = True) -> None:
        # The fenced DoWhiteOut FlagSet and the respawn map's heal page
        # (PROJECT_TODO #108): the white-out sets the flag as it hands back
        # control, and draining the arrival scripts clears it.
        self.flags: set[str] = set()
        self._engine_sets_starting_over = engine_sets_starting_over
        self._heal_page_clears_it = heal_page_clears_it
        self.symbols = {
            "gMain": _MAIN_ADDR,
            "CB2_Overworld": _CB2_OVERWORLD_ADDR,
            "CB2_WhiteOut": _CB2_WHITEOUT_ADDR,
        }
        self.offsets = dict(_OFFSETS)
        self._mem = _FakeMemory()
        self._frames_to_finish = frames_to_finish
        self.sb1 = _SB1_ADDR
        self._player_pos = (99, 99)
        self._map_location = (0, 0)
        self.settle_field_calls = 0
        self.wait_for_map_grid_calls = 0
        self.restore_calls: list[bytes] = []
        self._snapshot_counter = 0
        # gMain.callback2 starts at CB2_Overworld|1 (input-ready).
        self.write_u32(_MAIN_ADDR + _OFFSETS["off_main_callback2"],
                       _CB2_OVERWORLD_ADDR | 1)
        group, num = last_heal_location
        self.write_u8(_SB1_ADDR + _OFFSETS["off_sb1_lastheallocation"], group)
        self.write_u8(_SB1_ADDR + _OFFSETS["off_sb1_lastheallocation"] + 1, num)

    # -- raw memory -----------------------------------------------------
    def u8(self, addr: int) -> int:
        return self._mem.get(addr, 1)

    def u32(self, addr: int) -> int:
        return self._mem.get(addr, 4)

    def write_u8(self, addr: int, value: int) -> None:
        self._mem.set(addr, 1, value)

    def write_u32(self, addr: int, value: int) -> None:
        self._mem.set(addr, 4, value)

    # -- state machine ----------------------------------------------------
    def overworld_input_ready(self) -> bool:
        cb2 = self.u32(self.symbols["gMain"] + self.offsets["off_main_callback2"])
        return cb2 == (self.symbols["CB2_Overworld"] | 1)

    def run(self, frames: int, keys=None) -> None:
        cb2 = self.u32(self.symbols["gMain"] + self.offsets["off_main_callback2"])
        if cb2 == (self.symbols["CB2_WhiteOut"] | 1):
            state = self.u8(self.symbols["gMain"] + self.offsets["off_main_state"])
            state += frames
            if state >= self._frames_to_finish:
                self.write_u32(
                    self.symbols["gMain"] + self.offsets["off_main_callback2"],
                    self.symbols["CB2_Overworld"] | 1,
                )
                self._player_pos = (8, 13)
                self._map_location = (1, 2)
                if self._engine_sets_starting_over:
                    self.flags.add("FLAG_STARTING_OVER")
            else:
                self.write_u8(
                    self.symbols["gMain"] + self.offsets["off_main_state"], state)

    def wait_for_map_grid(self) -> int:
        self.wait_for_map_grid_calls += 1
        return 0

    def settle_field(self) -> int:
        self.settle_field_calls += 1
        if self._heal_page_clears_it:
            self.flags.discard("FLAG_STARTING_OVER")
        return 0

    def flag(self, name: str) -> bool:
        return name in self.flags

    def screenshot(self, name: str):
        return None

    def player_pos(self) -> tuple[int, int]:
        return self._player_pos

    def map_location(self) -> tuple[int, int]:
        return self._map_location

    def resolve_constant(self, name: str) -> int:
        # assertions.require_map calls MAP_GROUP(x)/MAP_NUM(x); the fake
        # chapter map always resolves to the fake map_location() above.
        return {"MAP_GROUP(MAP_FAKE)": 1, "MAP_NUM(MAP_FAKE)": 2}[name]

    def snapshot_state(self) -> bytes:
        self._snapshot_counter += 1
        return f"snap{self._snapshot_counter}".encode()

    def restore_state(self, state: bytes) -> None:
        self.restore_calls.append(state)


# -- force_white_out -----------------------------------------------------


def test_force_white_out_requires_overworld_ready() -> None:
    emu = _FakeEmu()
    emu.write_u32(emu.symbols["gMain"] + emu.offsets["off_main_callback2"], 0xDEAD)
    with pytest.raises(ScenarioError, match="input-ready"):
        force_white_out(emu, beat="TEST")


def test_force_white_out_fails_loud_on_zero_last_heal_location() -> None:
    emu = _FakeEmu(last_heal_location=(0, 0))
    with pytest.raises(ScenarioError, match="never set"):
        force_white_out(emu, beat="TEST")


def test_force_white_out_writes_state_zero_and_callback2_with_thumb_bit() -> None:
    emu = _FakeEmu(frames_to_finish=4)
    force_white_out(emu, beat="TEST", frame_budget=100)
    # Handed back to CB2_Overworld once finished.
    assert emu.overworld_input_ready()
    assert emu.settle_field_calls == 1
    assert emu.wait_for_map_grid_calls == 1


def test_force_white_out_thumb_bit_set_on_trigger_write() -> None:
    """Regression for the THUMB_BIT convention: capture the callback2 value
    mid-flight (before the fake snaps it back) to confirm the trigger write
    itself carried the low bit."""
    emu = _FakeEmu(frames_to_finish=10_000)  # never finishes within budget
    with pytest.raises(ScenarioError, match="never handed control back"):
        force_white_out(emu, beat="TEST", frame_budget=8)
    cb2 = emu.u32(emu.symbols["gMain"] + emu.offsets["off_main_callback2"])
    assert cb2 == (emu.symbols["CB2_WhiteOut"] | 1)


def test_force_white_out_times_out_loud() -> None:
    emu = _FakeEmu(frames_to_finish=10_000)
    with pytest.raises(ScenarioError, match="never handed control back"):
        force_white_out(emu, beat="TEST", frame_budget=8)


def test_read_last_heal_location() -> None:
    emu = _FakeEmu(last_heal_location=(7, 9))
    assert read_last_heal_location(emu) == (7, 9)


# -- load_heal_location ----------------------------------------------------


def test_load_heal_location_happy_path(tmp_path: Path) -> None:
    p = tmp_path / "heal_locations.json"
    p.write_text(json.dumps({
        "heal_locations": [
            {"id": "HEAL_LOCATION_URANIUM_START",
             "map": "MAP_MOKI_TOWN_PLAYERS_HOUSE_1F", "x": 7, "y": 7},
            {"id": "HEAL_LOCATION_KEVLAR_TOWN_POKEMON_CENTER",
             "map": "MAP_KEVLAR_TOWN_POKEMON_CENTER", "x": 8, "y": 13},
        ]
    }), encoding="utf-8")
    entry = load_heal_location("HEAL_LOCATION_KEVLAR_TOWN_POKEMON_CENTER", p)
    assert entry.map_const == "MAP_KEVLAR_TOWN_POKEMON_CENTER"
    assert (entry.x, entry.y) == (8, 13)


def test_load_heal_location_missing_id(tmp_path: Path) -> None:
    p = tmp_path / "heal_locations.json"
    p.write_text(json.dumps({"heal_locations": []}), encoding="utf-8")
    with pytest.raises(ScenarioError, match="not found in"):
        load_heal_location("HEAL_LOCATION_NOPE", p)


def test_load_heal_location_missing_file(tmp_path: Path) -> None:
    p = tmp_path / "does_not_exist.json"
    with pytest.raises(ScenarioError, match="not found at"):
        load_heal_location("HEAL_LOCATION_URANIUM_START", p)


def test_default_heal_locations_json_path() -> None:
    assert DEFAULT_HEAL_LOCATIONS_JSON == Path("output/uranium-build/heal_locations.json")


# -- whiteout_beat -----------------------------------------------------------


def _builder(name: str = "CHZZ_TEST") -> ChapterBuilder:
    return ChapterBuilder(name, doc="test-only, not a real chapter doc")


def test_whiteout_beat_registers_with_no_rows_archetype_or_at(tmp_path: Path) -> None:
    p = tmp_path / "heal_locations.json"
    p.write_text(json.dumps({"heal_locations": [
        {"id": "HEAL_LOCATION_KEVLAR_TOWN_POKEMON_CENTER",
         "map": "MAP_FAKE", "x": 8, "y": 13},
    ]}), encoding="utf-8")
    b = _builder()
    whiteout_beat(
        b, beat_name="B99",
        heal_location_id="HEAL_LOCATION_KEVLAR_TOWN_POKEMON_CENTER",
        heal_locations_json=p,
    )
    chapter = b.build()
    assert [beat.name for beat in chapter.beats] == ["B99"]
    beat = chapter.beats[0]
    assert beat.rows == ()
    assert beat.archetype is None
    assert beat.locations == ()


def test_whiteout_beat_registration_fails_loud_on_missing_id_when_file_exists(
        tmp_path: Path) -> None:
    p = tmp_path / "heal_locations.json"
    p.write_text(json.dumps({"heal_locations": []}), encoding="utf-8")
    b = _builder()
    with pytest.raises(ScenarioError, match="not found in"):
        whiteout_beat(
            b, beat_name="B99", heal_location_id="HEAL_LOCATION_NOPE",
            heal_locations_json=p,
        )


def test_whiteout_beat_run_passes_and_restores_state(tmp_path: Path) -> None:
    p = tmp_path / "heal_locations.json"
    p.write_text(json.dumps({"heal_locations": [
        {"id": "HEAL_LOCATION_KEVLAR_TOWN_POKEMON_CENTER",
         "map": "MAP_FAKE", "x": 8, "y": 13},
    ]}), encoding="utf-8")
    b = _builder()
    whiteout_beat(
        b, beat_name="B99",
        heal_location_id="HEAL_LOCATION_KEVLAR_TOWN_POKEMON_CENTER",
        heal_locations_json=p,
    )
    chapter = b.build()
    emu = _FakeEmu(frames_to_finish=4)
    chapter.beats[0].run(emu)
    assert emu.restore_calls == [b"snap1"]


def test_whiteout_beat_restores_state_even_when_assertion_fails(tmp_path: Path) -> None:
    p = tmp_path / "heal_locations.json"
    p.write_text(json.dumps({"heal_locations": [
        {"id": "HEAL_LOCATION_KEVLAR_TOWN_POKEMON_CENTER",
         "map": "MAP_FAKE", "x": 999, "y": 999},  # wrong on purpose
    ]}), encoding="utf-8")
    b = _builder()
    whiteout_beat(
        b, beat_name="B99",
        heal_location_id="HEAL_LOCATION_KEVLAR_TOWN_POKEMON_CENTER",
        heal_locations_json=p,
    )
    chapter = b.build()
    emu = _FakeEmu(frames_to_finish=4)
    with pytest.raises(ScenarioError, match="expected exactly"):
        chapter.beats[0].run(emu)
    assert emu.restore_calls == [b"snap1"]


# -- starting_over_rows (PROJECT_TODO #108) --------------------------------


def _starting_over_chapter(tmp_path: Path):
    p = tmp_path / "heal_locations.json"
    p.write_text(json.dumps({"heal_locations": [
        {"id": "HEAL_LOCATION_KEVLAR_TOWN_POKEMON_CENTER",
         "map": "MAP_FAKE", "x": 8, "y": 13},
    ]}), encoding="utf-8")
    b = _builder()
    whiteout_beat(
        b, beat_name="B99",
        heal_location_id="HEAL_LOCATION_KEVLAR_TOWN_POKEMON_CENTER",
        heal_locations_json=p, starting_over_rows=("map068/ev001/p1",),
    )
    return b.build()


def test_whiteout_beat_claims_starting_over_rows(tmp_path: Path) -> None:
    assert _starting_over_chapter(tmp_path).beats[0].rows == ("map068/ev001/p1",)


def test_whiteout_beat_starting_over_set_then_cleared_passes(tmp_path: Path) -> None:
    emu = _FakeEmu(frames_to_finish=4)
    _starting_over_chapter(tmp_path).beats[0].run(emu)
    assert emu.restore_calls == [b"snap1"]


def test_whiteout_beat_fails_when_the_engine_never_sets_starting_over(tmp_path: Path) -> None:
    """A cleared flag alone proves nothing: the ROM without DoWhiteOut's
    FlagSet also ends with it clear, so the set half must be observed too."""
    emu = _FakeEmu(frames_to_finish=4, engine_sets_starting_over=False)
    with pytest.raises(ScenarioError, match="not set when control returned"):
        _starting_over_chapter(tmp_path).beats[0].run(emu)
    assert emu.restore_calls == [b"snap1"]


def test_whiteout_beat_fails_when_the_heal_page_never_runs(tmp_path: Path) -> None:
    emu = _FakeEmu(frames_to_finish=4, heal_page_clears_it=False)
    with pytest.raises(ScenarioError, match="still set after the arrival scripts"):
        _starting_over_chapter(tmp_path).beats[0].run(emu)
    assert emu.restore_calls == [b"snap1"]


@pytest.mark.skipif(not Path("output/uranium-build/maps").is_dir(),
                    reason="no converted corpus on disk")
def test_whiteout_fork_beat_declares_only_what_it_proves() -> None:
    """Rulings 15 and 17: the generated form declares trigger/completes/
    switch_write/heal_party for CH01's home Starting Over page; the
    walk-checked visual stays undeclared."""
    from rpg2gba.playtest.whiteout import whiteout_fork_beat

    b = ChapterBuilder("CH01", doc="reference/chapters/01-moki-town.md")
    whiteout_fork_beat(b, chapter_id="CH01", beat_name="m049_whiteout", group="g",
                       rows=("map049/ev022/p0",),
                       heal_location_id="HEAL_LOCATION_URANIUM_START")
    beat = b.build().beats[0]
    assert beat.rows == ("map049/ev022/p0",)
    assert {a.kind for a in beat.assertions} == {
        "trigger", "completes", "switch_write", "heal_party"}


@pytest.mark.skipif(not Path("output/uranium-build/maps").is_dir(),
                    reason="no converted corpus on disk")
def test_whiteout_fork_beat_declares_the_landing_pages_text() -> None:
    """The Kevlar nurse's Starting Over heal (map068/ev001/p1) speaks: its
    lines are read back from the drain that ran it, so `text` is declared
    and the page's floor is covered."""
    from rpg2gba.beat_floor.coverage import uncovered
    from rpg2gba.beat_floor.lookup import floor_for_row
    from rpg2gba.playtest.whiteout import whiteout_fork_beat

    b = ChapterBuilder("CH04", doc="reference/chapters/04-route-02.md")
    whiteout_fork_beat(b, chapter_id="CH04", beat_name="m068_whiteout", group="g",
                       rows=("map068/ev001/p1",),
                       heal_location_id="HEAL_LOCATION_KEVLAR_TOWN_POKEMON_CENTER")
    beat = b.build().beats[0]
    assert "text" in {a.kind for a in beat.assertions}
    walk_checked = {"audio", "visual", "displacement"}   # not graded (ruling 7)
    assert [a for a in uncovered(floor_for_row("map068/ev001/p1"), beat.assertions)
            if a.kind not in walk_checked] == []
