"""Tests for the promoted playtest assertion helpers
(`src/rpg2gba/playtest/assertions.py`).

`PLAYTEST_AUTHORING_IMPROVEMENT.md` finding H: every good assertion helper
used to live as a private function inside whichever chapter module invented
it, unreachable from the others. This file tests the promoted, de-duplicated
versions in isolation, without an emulator where possible (light fakes where
one is needed), plus a structural check that the move did not drop or
duplicate a beat in any of the three chapter modules.

Convention follows `tests/test_playtest.py`: a minimal `_FakeEmu`-shaped
stand-in exposing only what each function under test actually reads, no
mgba dependency.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.playtest import assertions
from rpg2gba.playtest.errors import ScenarioError


# -- flag_ssa: pure string formatting -----------------------------------------

def test_flag_ssa_default_letter() -> None:
    assert assertions.flag_ssa(68, 18) == "FLAG_MAP068_EVENT018_SSA"


def test_flag_ssa_explicit_letter_and_zero_padding() -> None:
    assert assertions.flag_ssa(31, 14, "D") == "FLAG_MAP031_EVENT014_SSD"


def test_route1_flag_ssa_wrapper_matches_general_form() -> None:
    """`ch02.py`'s `_flag_ssa(event_id, letter)` is now a thin wrapper over
    `assertions.flag_ssa(33, event_id, letter)` -- pin that it produces the
    exact same string the old hardcoded-Map033 implementation did."""
    from rpg2gba.playtest.chapters import ch02

    assert ch02._flag_ssa(18) == "FLAG_MAP033_EVENT018_SSA" == assertions.flag_ssa(33, 18)
    assert ch02._flag_ssa(18, "B") == assertions.flag_ssa(33, 18, "B")


# -- small fakes ---------------------------------------------------------------

class _FakeEmu:
    """Minimal stand-in exposing only what the navigation/facing/BGM/species
    helpers under test read: resolve_constant/map_location/player_pos/run/
    screenshot/object_event/symbols/offsets, plus a fake `_mem` party store
    mirroring `tests/test_playtest.py`'s `_FakeEmu` shape closely enough for
    `read_party_species`/`player_starter_species` to exercise the real
    `battle.decrypt_species` against it."""

    def __init__(self, *, constants=None, symbols=None, offsets=None,
                 map_group_num=(0, 0), pos=(0, 0)) -> None:
        self._constants = constants or {}
        self.symbols = symbols or {}
        self.offsets = offsets or {}
        self._map = map_group_num
        self._pos = pos
        self.screenshots: list[str] = []
        self._mem: dict[int, int] = {}

    def resolve_constant(self, expr: str) -> int:
        return self._constants[expr]

    def map_location(self) -> tuple[int, int]:
        return self._map

    def player_pos(self) -> tuple[int, int]:
        return self._pos

    def run(self, frames: int, keys: list[str] | None = None) -> None:
        pass  # never actually moves in these tests -- see docstrings below

    def screenshot(self, name: str) -> str:
        self.screenshots.append(name)
        return f"/tmp/{name}.png"

    # -- u32 memory store for decrypt_species-backed tests --------------------
    def u32(self, addr: int) -> int:
        value = 0
        for i in range(4):
            value |= self._mem.get(addr + i, 0) << (8 * i)
        return value

    def write_u32(self, addr: int, value: int) -> None:
        for i in range(4):
            self._mem[addr + i] = (value >> (8 * i)) & 0xFF


# -- at_map / require_map -----------------------------------------------------

_MAP_CONSTANTS = {"MAP_GROUP(MAP_KEVLAR_TOWN)": 3, "MAP_NUM(MAP_KEVLAR_TOWN)": 5,
                   "MAP_GROUP(MAP_ROUTE_01)": 3, "MAP_NUM(MAP_ROUTE_01)": 2}


def test_at_map_true_when_group_and_num_match() -> None:
    emu = _FakeEmu(constants=_MAP_CONSTANTS, map_group_num=(3, 5))
    assert assertions.at_map(emu, "MAP_KEVLAR_TOWN") is True
    assert assertions.at_map(emu, "MAP_ROUTE_01") is False


def test_require_map_raises_with_a_screenshot_on_mismatch() -> None:
    emu = _FakeEmu(constants=_MAP_CONSTANTS, map_group_num=(3, 2))
    with pytest.raises(ScenarioError, match="expected map MAP_KEVLAR_TOWN"):
        assertions.require_map(emu, "B1", "MAP_KEVLAR_TOWN")
    assert emu.screenshots == ["B1_wrong_map"]


def test_require_map_passes_silently_on_match() -> None:
    emu = _FakeEmu(constants=_MAP_CONSTANTS, map_group_num=(3, 5))
    assertions.require_map(emu, "B1", "MAP_KEVLAR_TOWN")  # must not raise
    assert emu.screenshots == []


# -- try_step ------------------------------------------------------------------

class _StepEmu(_FakeEmu):
    """`run()` moves the fake position on the Nth call, simulating a step
    that lands after `moves_after` calls to `run(1, [...])` (or never, if
    `moves_after` is None -- a genuine wall bump)."""

    def __init__(self, moves_after: int | None) -> None:
        super().__init__()
        self._moves_after = moves_after
        self._calls = 0

    def run(self, frames: int, keys: list[str] | None = None) -> None:
        if keys is None:
            return
        self._calls += 1
        if self._moves_after is not None and self._calls == self._moves_after:
            self._pos = (self._pos[0], self._pos[1] + 1)


def test_try_step_reports_movement() -> None:
    emu = _StepEmu(moves_after=3)
    assert assertions.try_step(emu, "DOWN") is True


def test_try_step_reports_no_movement_on_a_wall_bump() -> None:
    emu = _StepEmu(moves_after=None)
    assert assertions.try_step(emu, "DOWN") is False


# -- assert_near ---------------------------------------------------------------

def test_assert_near_within_tolerance_does_not_raise() -> None:
    emu = _FakeEmu(pos=(9, 12))
    assertions.assert_near(emu, "B3", (8, 12))  # dx=1, within default tolerance 1


def test_assert_near_outside_tolerance_raises_with_screenshot() -> None:
    emu = _FakeEmu(pos=(9, 12))
    with pytest.raises(ScenarioError, match=r"landed at \(9,12\), expected near \(8, 12\)"):
        assertions.assert_near(emu, "B3", (8, 12), tolerance=0)
    assert emu.screenshots == ["B3_wrong_landing"]


# -- assert_arrival_settled ------------------------------------------------------

class _ArrivalEmu(_FakeEmu):
    def __init__(self, *, pos: tuple[int, int], locked: bool = False) -> None:
        super().__init__(pos=pos)
        self._locked = locked
        self.settled = False

    def settle_field(self) -> None:
        self.settled = True

    def field_locked(self) -> bool:
        return self._locked


def test_arrival_settled_nudged_accepts_exactly_one_tile_off() -> None:
    emu = _ArrivalEmu(pos=(8, 44))
    assertions.assert_arrival_settled(emu, "B1", (8, 43), nudged=True)
    assert emu.settled and emu.screenshots == []


def test_arrival_settled_nudged_rejects_staying_on_the_arrival_cell() -> None:
    emu = _ArrivalEmu(pos=(8, 43))
    with pytest.raises(ScenarioError, match="still at arrival cell"):
        assertions.assert_arrival_settled(emu, "B1", (8, 43), nudged=True)
    assert emu.screenshots == ["B1_no_nudge"]


def test_arrival_settled_nudged_rejects_two_tiles_off() -> None:
    emu = _ArrivalEmu(pos=(9, 44))
    with pytest.raises(ScenarioError, match="Manhattan distance 2"):
        assertions.assert_arrival_settled(emu, "B1", (8, 43), nudged=True)


def test_arrival_settled_unnudged_requires_the_exact_cell() -> None:
    assertions.assert_arrival_settled(
        _ArrivalEmu(pos=(15, 7)), "B1", (15, 7), nudged=False)
    emu = _ArrivalEmu(pos=(15, 8))
    with pytest.raises(ScenarioError, match="no nudge applies"):
        assertions.assert_arrival_settled(emu, "B1", (15, 7), nudged=False)
    assert emu.screenshots == ["B1_moved_on_arrival"]


def test_arrival_settled_fails_on_a_locked_field_before_checking_position() -> None:
    emu = _ArrivalEmu(pos=(15, 7), locked=True)
    with pytest.raises(ScenarioError, match="field still locked"):
        assertions.assert_arrival_settled(emu, "B1", (15, 7), nudged=False)
    assert emu.screenshots == ["B1_stuck"]


# -- warp-arrival facing: the flagship promoted case --------------------------

def test_assert_player_facing_matches() -> None:
    class _Obj:
        facing = "UP"

    emu = _FakeEmu(constants={"LOCALID_PLAYER": 1})
    emu.object_event = lambda localid: _Obj()
    assertions.assert_player_facing(emu, "B27", "UP")  # must not raise


def test_assert_player_facing_mismatch_raises() -> None:
    class _Obj:
        facing = "DOWN"

    emu = _FakeEmu(constants={"LOCALID_PLAYER": 1})
    emu.object_event = lambda localid: _Obj()
    with pytest.raises(ScenarioError, match="player facing DOWN, expected UP"):
        assertions.assert_player_facing(emu, "B27", "UP")
    assert emu.screenshots == ["b27_wrong_facing"]


@pytest.mark.parametrize(
    ("direction", "approach", "expected"),
    [(2, "UP", "DOWN"), (4, "UP", "LEFT"), (6, "DOWN", "RIGHT"), (8, "LEFT", "UP"),
     (0, "LEFT", "LEFT"), (None, "RIGHT", "RIGHT")],
)
def test_facing_for_direction(direction, approach, expected) -> None:
    """An explicit RMXP direction wins; 0/None ("retain facing") keeps the
    facing the player crossed with (C5b, RPG2GBA_WARP_RETAIN_FACING)."""
    assert assertions.facing_for_direction(direction, approach) == expected


def test_facing_for_direction_rejects_unknowns() -> None:
    with pytest.raises(ValueError, match="unknown RMXP transfer direction 5"):
        assertions.facing_for_direction(5, "UP")
    with pytest.raises(ValueError, match="approach 'NORTH'"):
        assertions.facing_for_direction(0, "NORTH")


def test_arrival_landing_cell_steps_off_a_door_in_the_facing() -> None:
    """A door-tile arrival lands one step on in the arrival facing (the
    engine's Task_ExitNonAnimDoor); any other arrival stays put."""
    assert assertions.arrival_landing_cell((5, 5), "DOWN", False) == (5, 5)
    assert assertions.arrival_landing_cell((5, 5), "DOWN", True) == (5, 6)
    assert assertions.arrival_landing_cell((5, 5), "UP", True) == (5, 4)
    assert assertions.arrival_landing_cell((5, 5), "LEFT", True) == (4, 5)
    assert assertions.arrival_landing_cell((5, 5), "RIGHT", True) == (6, 5)


def _stage_map(tmp_path, monkeypatch, specs) -> None:
    """Stage an (empty) Map031.json and fake the classifier to return
    `specs` for it -- `expected_arrival_facing` must read the staged map and
    thread it through `classify_map_events`, not a hardcoded table."""
    from rpg2gba.tileset_converter import map_set, metadata_wiring

    maps_dir = tmp_path / "uranium-build" / "maps"
    maps_dir.mkdir(parents=True)
    (maps_dir / "Map031.json").write_text('{"marker": 1}', encoding="utf-8")
    monkeypatch.setenv("RPG2GBA_OUTPUT", str(tmp_path))
    monkeypatch.setattr(map_set, "SLICE_MAP_IDS", (31,))

    def _fake_classify(map_json, slice_set):
        assert map_json == {"marker": 1}  # the staged file was actually read
        return None, [({"id": i}, s) for i, s in enumerate(specs)]

    monkeypatch.setattr(metadata_wiring, "classify_map_events", _fake_classify)


def test_expected_arrival_facing_reads_the_staged_departure_warp(
        tmp_path, monkeypatch) -> None:
    from rpg2gba.tileset_converter.metadata_wiring import WarpSpec

    _stage_map(tmp_path, monkeypatch, [
        WarpSpec(src_x=20, src_y=12, dest_uid=68, dest_x=8, dest_y=18, dest_dir=0),
        WarpSpec(src_x=16, src_y=5, dest_uid=31, dest_x=16, dest_y=42, dest_dir=8),
    ])
    # explicit direction on the warp at (16, 5) wins over the approach
    assert assertions.expected_arrival_facing(31, (16, 5), "DOWN") == "UP"
    # retain (0) at (20, 12): the approach is kept
    assert assertions.expected_arrival_facing(31, (20, 12), "LEFT") == "LEFT"


def test_expected_arrival_facing_raises_when_no_warp_on_cell(
        tmp_path, monkeypatch) -> None:
    _stage_map(tmp_path, monkeypatch, [])
    with pytest.raises(ScenarioError, match=r"yields 0 distinct kept-warp directions"):
        assertions.expected_arrival_facing(31, (16, 5), "UP")


def test_expected_arrival_facing_raises_when_warps_disagree(
        tmp_path, monkeypatch) -> None:
    from rpg2gba.tileset_converter.metadata_wiring import WarpSpec

    _stage_map(tmp_path, monkeypatch, [
        WarpSpec(src_x=1, src_y=1, dest_uid=2, dest_x=0, dest_y=0, dest_dir=2),
        WarpSpec(src_x=1, src_y=1, dest_uid=2, dest_x=0, dest_y=0, dest_dir=8),
    ])
    with pytest.raises(ScenarioError, match=r"yields 2 distinct kept-warp directions"):
        assertions.expected_arrival_facing(31, (1, 1), "UP")


# -- post-warp BGM --------------------------------------------------------------

class _EngineEmu(_FakeEmu):
    def __init__(self, engine: Path, *, bgm_song_id: int,
                 constants=None) -> None:
        super().__init__(constants=constants)
        self.engine = engine
        self._bgm_song_id = bgm_song_id

    def bgm_song_id(self) -> int:
        return self._bgm_song_id


def _write_map_header(engine: Path, map_dir: str, music: str) -> None:
    d = engine / "data" / "maps" / map_dir
    d.mkdir(parents=True)
    (d / "map.json").write_text(json.dumps({"music": music}), encoding="utf-8")


def test_expected_bgm_song_id_reads_the_maps_own_header(tmp_path) -> None:
    _write_map_header(tmp_path, "KevlarTownPokemonCenter", "MUS_POKE_CENTER")
    emu = _EngineEmu(tmp_path, bgm_song_id=0, constants={"MUS_POKE_CENTER": 42})
    assert assertions.expected_bgm_song_id(emu, "KevlarTownPokemonCenter") == 42


def test_assert_bgm_passes_when_song_matches(tmp_path) -> None:
    _write_map_header(tmp_path, "KevlarTownPokemart", "MUS_MART")
    emu = _EngineEmu(tmp_path, bgm_song_id=7, constants={"MUS_MART": 7})
    assertions.assert_bgm(emu, "B29", "KevlarTownPokemart")  # must not raise


def test_assert_bgm_raises_with_screenshot_on_mismatch(tmp_path) -> None:
    _write_map_header(tmp_path, "KevlarTownPokemart", "MUS_MART")
    emu = _EngineEmu(tmp_path, bgm_song_id=99, constants={"MUS_MART": 7})
    with pytest.raises(ScenarioError, match="playing song id 99, expected 7"):
        assertions.assert_bgm(emu, "B29", "KevlarTownPokemart")
    assert emu.screenshots == ["b29_wrong_bgm"]


# -- party species reads -------------------------------------------------------
#
# Exercises the real `battle.decrypt_species` (unencrypted here: personality
# and otId both 0, so the XOR key is 0 and the stored word is plaintext) --
# same struct-layout offsets `tests/test_playtest.py` uses for the same
# purpose, kept minimal to just what these two functions read.

_PARTY_OFFSETS = {
    "off_pkmn_box": 0,
    "off_boxpkmn_personality": 0,
    "off_boxpkmn_otid": 4,
    "off_boxpkmn_secure": 32,
    "val_num_substruct_bytes": 12,
    "sizeof_pkmn": 100,
}


def _write_plaintext_species(emu: _FakeEmu, box_addr: int, species: int) -> None:
    # personality=otId=0 -> XOR key 0 -> the secure word is plaintext, and
    # substruct 0 sits at the base of `secure` for personality%24==0 (see
    # `battle.py`'s sSubstructOffsets table, row 0 index 0).
    emu.write_u32(box_addr + 32, species & 0x7FF)


def _party_emu(species_slots: list[int | None]) -> _FakeEmu:
    """`species_slots` in slot order; `None` leaves a slot at its default
    (species 0, i.e. SPECIES_NONE) without writing anything."""
    emu = _FakeEmu(
        constants={"SPECIES_NONE": 0, "PARTY_SIZE": 6},
        symbols={"gPlayerParty": 0x02000000},
        offsets=dict(_PARTY_OFFSETS),
    )
    for slot, species in enumerate(species_slots):
        if species is None:
            continue
        box_addr = 0x02000000 + slot * _PARTY_OFFSETS["sizeof_pkmn"]
        _write_plaintext_species(emu, box_addr, species)
    return emu


def test_player_starter_species_reads_slot_zero() -> None:
    emu = _party_emu([387, 1, 2])
    assert assertions.player_starter_species(emu) == 387


def test_player_starter_species_returns_species_none_when_empty() -> None:
    """Promoted verbatim from `ch01.py`: no early-out, so an empty party
    reads back SPECIES_NONE itself (B8 relies on exactly this)."""
    emu = _party_emu([])
    assert assertions.player_starter_species(emu) == 0


def test_read_party_species_stops_at_the_first_species_none() -> None:
    emu = _party_emu([387, 129, None, 6])  # slot 3 (6) must not be read
    assert assertions.read_party_species(emu) == [387, 129]


def test_party_has_species_true_when_present() -> None:
    emu = _party_emu([1, 129, 6])
    assert assertions.party_has_species(emu, 129) is True


def test_party_has_species_false_when_absent_or_empty() -> None:
    emu = _party_emu([1, 2])
    assert assertions.party_has_species(emu, 129) is False
    assert assertions.party_has_species(_party_emu([]), 129) is False


# -- structural: the refactor must not change any chapter's registered beats -

def test_beat_counts_unchanged_after_the_assertions_refactor() -> None:
    """Pins finding H's promotion as behaviour-preserving: moving helpers
    into `assertions.py` must not add, drop, or rename a beat. Import-based,
    not grep-based -- `ch02.py`/`ch03.py` both contain prose comments
    describing the `@X.beat(...)` decorator syntax without applying it, so a
    grep count over-counts (see the task brief this test was written for)."""
    from rpg2gba.playtest.chapter import load_chapter

    # route1 went 30 -> 31 on 2026-08-27: N5 (re-talking defeated Richey) was
    # registered once the silent-`Page2` bug it guards was fixed. kevlar
    # chains route1 as its predecessor, so it carries the same +1.
    # route1 went 31 -> 32 on 2026-09-13: B18 (the initial white-out anchor,
    # REDERIVATION_PLAN.md §14.7/§15.6) was registered; kevlar carries the +1.
    # 2026-09-14: moki 17 -> 18 (N4, the refused Moki rocks); route1 +1 for
    # that, +4 for the Moki<->Route 1 boundary-claim crossings after B1
    # (32 -> 37); kevlar carries both, +1 for N7 (the refused Kevlar
    # boulders) and +4 for the Route 1<->Kevlar crossings after B27 (62 -> 72).
    # 2026-09-15: moki 18 -> 22 (the 2F stop, B3_up/B3_signs/B3_pc/B3_down);
    # route1 and kevlar carry the +4 (41, 76).
    expected = {"CH01": 22, "CH02": 41, "CH03": 76}
    for name, count in expected.items():
        chapter = load_chapter(name)
        assert len(chapter.beats) == count, f"{name}: beat count drifted"


def test_deferred_tuples_survive_the_refactor_intact() -> None:
    """`ch02.DEFERRED_ROCK_GATED` and `ch03.DEFERRED_BEATS` are inert
    tuples of undecorated functions that no registered beat touches --
    ready-made regression tests for content years away. The refactor must
    not disturb their entry counts."""
    from rpg2gba.playtest.chapters import ch02, ch03

    assert len(ch02.DEFERRED_ROCK_GATED) == 10
    assert len(ch03.DEFERRED_BEATS) == 10


# -- talk_to_moving_npc: the NPC does not stay where it spawned ---------------


class _MovingNpc:
    """The minimum `talk_to_moving_npc` reads: an NPC position that can
    change under it, a player position, and an interact that reports
    whether anything fired."""

    def __init__(self, npc: tuple[int, int], player: tuple[int, int], *,
                 blocked: set[tuple[int, int]] | None = None,
                 fires: bool = True) -> None:
        self.npc = npc
        self.player = player
        self.blocked = blocked or set()
        self.fires = fires
        self.walks: list[tuple[int, int]] = []
        self.faced: list[str] = []
        self.interacts = 0

    class _Ev:
        def __init__(self, x: int, y: int) -> None:
            self.x, self.y = x, y

    def object_event(self, local_id: int) -> "_MovingNpc._Ev":
        return self._Ev(*self.npc)

    def player_pos(self) -> tuple[int, int]:
        return self.player

    def walk_to(self, x: int, y: int, *args, **kwargs) -> None:
        self.walks.append((x, y))
        if (x, y) in self.blocked or (x, y) == self.npc:
            raise ScenarioError(f"blocked at {(x, y)}")
        self.player = (x, y)

    def face(self, direction: str) -> None:
        self.faced.append(direction)

    def interact(self, require_script: bool = True) -> bool:
        self.interacts += 1
        return self.fires

    def screenshot(self, name: str) -> str:
        return f"{name}.png"


def test_talk_to_moving_npc_uses_the_side_the_player_already_stands_on() -> None:
    """The B10 case: the NPC walked onto the derived approach cell and the
    player is standing on its vacated spawn tile. No walk is needed at all
    -- the player only has to turn around."""
    emu = _MovingNpc(npc=(8, 8), player=(8, 7))

    assertions.talk_to_moving_npc(emu, "B10", 2)

    assert emu.walks == []            # already adjacent; nothing to walk
    assert emu.faced == ["DOWN"]      # player is NORTH of the NPC
    assert emu.interacts == 1


def test_talk_to_moving_npc_walks_to_a_live_side_when_not_adjacent() -> None:
    emu = _MovingNpc(npc=(8, 8), player=(3, 3))

    assertions.talk_to_moving_npc(emu, "B10", 2)

    # First side tried is the first walkable one in _TALK_SIDES order.
    assert emu.walks[0] == (8, 9)
    assert emu.player == (8, 9)
    assert emu.faced == ["UP"]        # player ended SOUTH of the NPC


def test_talk_to_moving_npc_tries_another_side_when_one_is_blocked() -> None:
    """A blocked side is not a failure -- an NPC in a corridor has fewer
    than four, and which ones are open changes as it moves."""
    emu = _MovingNpc(npc=(8, 8), player=(3, 3), blocked={(8, 9), (8, 7)})

    assertions.talk_to_moving_npc(emu, "B10", 2)

    assert (8, 9) in emu.walks and (8, 7) in emu.walks
    assert emu.player == (7, 8)       # fell through to the west side
    assert emu.faced == ["RIGHT"]


def test_talk_to_moving_npc_fails_loud_with_the_last_seen_position() -> None:
    """An NPC that can never be reached is a finding about the map, not
    something to pass over quietly."""
    emu = _MovingNpc(npc=(8, 8), player=(3, 3),
                     blocked={(8, 9), (8, 7), (7, 8), (9, 8)})

    with pytest.raises(ScenarioError, match=r"last seen at \(8, 8\)"):
        assertions.talk_to_moving_npc(emu, "B10", 2, attempts=2)


def test_talk_to_moving_npc_uses_the_callers_walk() -> None:
    """`WalkInterrupted` is a `ScenarioError`, so the blocked-side handler
    would swallow a wild encounter. A caller on a map with a live encounter
    table passes its own absorbing walker instead."""
    emu = _MovingNpc(npc=(8, 8), player=(3, 3))
    absorbed: list[tuple[int, int]] = []

    def _absorbing(x: int, y: int) -> None:
        absorbed.append((x, y))
        emu.walk_to(x, y)

    assertions.talk_to_moving_npc(emu, "B10", 2, walk=_absorbing)

    assert absorbed == [(8, 9)]
