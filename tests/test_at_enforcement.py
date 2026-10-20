"""Tests for Q13 slice 1's `at=` enforcement
(`PLAYTEST_AUTHORING_IMPROVEMENT_V2.md` Q13, "slice 1 -- graph, and `at=`
becomes real").

Two independent checks:

- **Check 1 (offline, `chapter.py`)**: `verify_chapter_locations`/
  `assert_chapter_locations_reachable` -- a declared `BeatLocation` must be a
  cell the offline traversable graph (`rpg2gba.traversal.graph.MapGraph`)
  says is reachable. No emulator involved; these tests use the real staged
  Route 01 data (`output/uranium-build/maps/Map033.json` +
  `output/uranium-build/porymap/map_constants.json`), the same fixtures
  `tests/test_traversal_graph.py` already relies on being present.

- **Check 2 (runtime, `runner.py`)**: `_check_beat_continuity` -- a beat's
  explicit `entry_at=` (NOT `locations`/`at=`) must match where the previous
  beat actually left the player. Exercised both directly (unit) and through a
  full `run_chapter` attempt against a stub emulator (`FakeEmulator` here,
  independent of `test_runner.py`'s copy -- it needs `resolve_constant`,
  which that fixture doesn't implement).

  `entry_at=` was split out from `locations[0]` on 2026-09-05: an offline
  audit found `locations[0]` disagreed with a beat's recorded entry position
  40 times out of 51 inherited beats, so continuity is now checked only
  against the separate, opt-in `entry_at` field -- see `chapter.py`'s
  `ChapterBuilder.beat` docstring for the full measurement.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.playtest.chapter import (
    Beat,
    BeatLocation,
    Chapter,
    assert_chapter_locations_reachable,
    check_location_reachable,
    verify_chapter_locations,
)
from rpg2gba.playtest.runner import (
    BeatContinuityError,
    _check_beat_continuity,
    run_chapter,
)

# -- real staged fixtures (Route 01 / map 33) ---------------------------------
#
# Picked once, empirically, against the committed staged output: (0, 0) is a
# genuinely blocked, non-warp cell (top-left corner, outside any built room --
# see this task's report for how it was found); (3, 0) is an ordinary
# walkable cell. Neither is a door/warp tile, so the check-1 warp exception
# (chapter.py's `_reachable`) is not in play for either -- these exercise the
# plain walkable/blocked branch.
ROUTE_01 = "MAP_ROUTE_01"
BLOCKED_CELL = (0, 0)
WALKABLE_CELL = (3, 0)


def make_chapter(name: str, beats: list[Beat]) -> Chapter:
    return Chapter(name=name, doc=f"reference/chapters/{name}.md", beats=tuple(beats))


def ok(emu) -> None:
    pass


# -- check 1: reachability (chapter.py) ---------------------------------------

def test_unreachable_declared_coordinate_is_rejected() -> None:
    loc = BeatLocation(ROUTE_01, *BLOCKED_CELL, "a wall")
    chapter = make_chapter("t_unreachable", [Beat("B1", "d", ok, (loc,))])

    results = verify_chapter_locations(chapter)
    assert len(results) == 1
    assert results[0].ok is False
    assert "not reachable" in results[0].reason

    with pytest.raises(ValueError, match="not reachable"):
        assert_chapter_locations_reachable(chapter)


def test_reachable_declared_coordinate_passes() -> None:
    loc = BeatLocation(ROUTE_01, *WALKABLE_CELL, "open ground")
    chapter = make_chapter("t_reachable", [Beat("B1", "d", ok, (loc,))])

    results = verify_chapter_locations(chapter)
    assert len(results) == 1
    assert results[0].ok is True
    assert results[0].reason is None

    assert_chapter_locations_reachable(chapter)  # must not raise


def test_beat_with_no_declaration_is_unaffected() -> None:
    chapter = make_chapter("t_none", [Beat("B1", "d", ok, ()), Beat("B2", "d", ok, ())])

    assert verify_chapter_locations(chapter) == []
    assert_chapter_locations_reachable(chapter)  # must not raise

    # Never touches the map-constants state file when nothing is declared --
    # a bogus state_path must not surface as an error here.
    assert verify_chapter_locations(
        chapter, state_path=Path("/nonexistent/does/not/exist.json")) == []


def test_unresolvable_map_constant_reported_not_guessed() -> None:
    loc = BeatLocation("MAP_DOES_NOT_EXIST", 0, 0)
    chapter = make_chapter("t_unresolved", [Beat("B1", "d", ok, (loc,))])

    results = verify_chapter_locations(chapter)
    assert results[0].ok is False
    assert "does not resolve to any minted Uranium map id" in results[0].reason


def test_check_location_reachable_caches_graph_across_calls() -> None:
    """Two locations on the same map only build the offline graph once --
    `graph_cache` is shared, not merely accepted as a parameter."""
    cache: dict[int, object] = {}
    by_const = {ROUTE_01: 33}

    r1 = check_location_reachable(
        BeatLocation(ROUTE_01, *WALKABLE_CELL), beat_name="B1",
        map_const_to_uranium_id=by_const, graph_cache=cache)
    assert r1.ok
    assert 33 in cache
    graph_obj = cache[33]

    r2 = check_location_reachable(
        BeatLocation(ROUTE_01, *BLOCKED_CELL), beat_name="B2",
        map_const_to_uranium_id=by_const, graph_cache=cache)
    assert not r2.ok
    assert cache[33] is graph_obj  # same object, not rebuilt


# -- multi-point interpretation -----------------------------------------------

def test_multi_point_beat_checks_every_point_independently() -> None:
    """Check 1: every point in `locations=` is its own claim. One bad point
    among several good ones still fails the chapter-wide assertion, and the
    report names the right beat."""
    locations = (
        BeatLocation(ROUTE_01, *WALKABLE_CELL, "good point"),
        BeatLocation(ROUTE_01, *BLOCKED_CELL, "bad point"),
    )
    chapter = make_chapter("t_multi", [Beat("B1", "d", ok, locations)])

    results = verify_chapter_locations(chapter)
    assert len(results) == 2
    assert results[0].ok is True
    assert results[1].ok is False

    with pytest.raises(ValueError, match=r"B1.*not reachable"):
        assert_chapter_locations_reachable(chapter)


# -- check 2: continuity (runner.py) ------------------------------------------

class FakeEmulator:
    """Minimal stand-in for `Emulator`, local to this file: needs
    `resolve_constant` (which `test_runner.py`'s `FakeEmulator` doesn't
    implement, since none of its tests declare `at=`), plus the small
    surface `runner.py`/`stamp.py` otherwise read. `map_consts` maps a
    MAP_* string to its (group, num) pair; `resolve_constant` parses the
    `MAP_GROUP(X)`/`MAP_NUM(X)` spelling `assertions.at_map` and this task's
    `_check_beat_continuity` both use."""

    def __init__(self, rom: Path, engine: Path, screenshot_dir: Path | None = None,
                 map_consts: dict[str, tuple[int, int]] | None = None,
                 positions: list[tuple[int, int]] | None = None) -> None:
        self.rom = rom
        self.engine = engine
        self.screenshot_dir = screenshot_dir
        self.map_consts = map_consts or {}
        self._positions = list(positions or [(0, 0)])
        self._pos_i = 0
        self.symbols = {"gSaveBlock1Ptr": 0x1000, "gSaveBlock2Ptr": 0x1000,
                        "gSaveBlock3Ptr": 0x1000, "gPokemonStoragePtr": 0x1000,
                        "gRpg2gbaEmbeddedSave": 0}
        self.offsets = {"sizeof_sb1": 4, "sizeof_sb2": 4, "sizeof_sb3": 4,
                        "sizeof_storage": 4, "sizeof_es": 16,
                        "embedded_save_magic": 0xABCDEF01,
                        "off_es_sb1": 0, "off_es_sb2": 4, "off_es_sb3": 8,
                        "off_es_storage": 12}
        self._mem: dict[int, int] = {}
        self._map = (0, 0)
        self.waypoints: list = []
        self._locked = False
        self.frame = 0

    def run(self, frames: int, keys=None, on_frame=None) -> None:
        self.frame += frames

    def u32(self, addr: int) -> int:
        return self._mem.get(addr, 0)

    def read_bytes(self, addr: int, size: int) -> bytes:
        return bytes(self._mem.get(addr + i, 0) for i in range(size))

    def tap(self, key: str, hold: int = 6, release: int = 6) -> None:
        self.run(hold + release)
        if key == "A":
            self.rom.with_suffix(".sav").touch()

    def snapshot_state(self) -> dict:
        return {"frame": self.frame, "pos_i": self._pos_i, "map": self._map,
                "mem": dict(self._mem), "locked": self._locked}

    def restore_state(self, state: dict) -> None:
        self.frame = state["frame"]
        self._pos_i = state["pos_i"]
        self._map = state["map"]
        self._mem = dict(state["mem"])
        self._locked = state["locked"]

    def resolve_constant(self, expr: str) -> int:
        for map_const, (group, num) in self.map_consts.items():
            if expr == f"MAP_GROUP({map_const})":
                return group
            if expr == f"MAP_NUM({map_const})":
                return num
        raise ValueError(f"unresolvable constant expression: {expr!r}")

    def player_pos(self) -> tuple[int, int]:
        return self._positions[min(self._pos_i, len(self._positions) - 1)]

    def map_location(self) -> tuple[int, int]:
        return self._map

    def clear_field_message(self) -> None:
        pass

    def field_locked(self) -> bool:
        return self._locked

    def screenshot(self, name: str):
        if self.screenshot_dir is None:
            return None
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = self.screenshot_dir / f"{name}_f{self.frame}.png"
        path.write_bytes(b"fake-png")
        return path

    def waypoint(self, beat: str, name: str = "", note: str = "", failed: bool = False):
        from PIL import Image

        from rpg2gba.playtest.contact_sheet import Waypoint

        if self.screenshot_dir is None:
            return None
        wp_dir = self.screenshot_dir / "waypoints"
        wp_dir.mkdir(parents=True, exist_ok=True)
        path = wp_dir / f"{len(self.waypoints):02d}_{beat}_{name}.png"
        Image.new("RGB", (240, 160), (16, 32, 48)).save(path)
        wp = Waypoint(beat=beat, name=name or beat, note=note,
                      frame=self.frame, path=path, failed=failed)
        self.waypoints.append(wp)
        return wp

    def advance(self) -> None:
        """Test-only helper: move on to the next scripted position, standing
        in for whatever a real beat body's walk would have done."""
        self._pos_i += 1


@pytest.fixture(autouse=True)
def _stub_save_in_game(monkeypatch):
    """`stamp.dump_save_blocks` drives a real in-game save through
    `scenarios.save_in_game`, which navigates a real START menu -- not
    available to this stub harness. Same seam `tests/test_runner.py`
    patches, for the same reason."""
    from rpg2gba.playtest import scenarios

    monkeypatch.setattr(scenarios, "save_in_game", lambda emu: emu.tap("A"))


def _entry(map_group: int, map_num: int, pos: tuple[int, int]) -> dict[str, object]:
    return {"map_group": map_group, "map_num": map_num, "player_pos": list(pos)}


def test_continuity_mismatch_is_caught_and_names_both_positions() -> None:
    emu = FakeEmulator(Path("rom"), Path("engine"), map_consts={ROUTE_01: (0, 33)})
    beat = Beat("B2", "d", ok, (BeatLocation(ROUTE_01, 10, 10, "expected here"),),
                entry_at=(10, 10))
    enter = _entry(0, 33, (5, 5))  # previous beat actually left the player at (5,5)

    with pytest.raises(BeatContinuityError) as exc_info:
        _check_beat_continuity(beat, enter, emu)

    message = str(exc_info.value)
    assert "(10, 10)" in message  # declared
    assert "(5, 5)" in message    # actual


def test_continuity_match_does_not_raise() -> None:
    emu = FakeEmulator(Path("rom"), Path("engine"), map_consts={ROUTE_01: (0, 33)})
    beat = Beat("B2", "d", ok, (BeatLocation(ROUTE_01, 10, 10),), entry_at=(10, 10))
    enter = _entry(0, 33, (10, 10))

    _check_beat_continuity(beat, enter, emu)  # must not raise


def test_continuity_unaffected_when_beat_declares_nothing() -> None:
    emu = FakeEmulator(Path("rom"), Path("engine"))
    beat = Beat("B2", "d", ok, ())
    enter = _entry(0, 33, (999, 999))

    _check_beat_continuity(beat, enter, emu)  # nothing to check, must not raise


def test_continuity_not_checked_without_entry_at_even_if_at_disagrees() -> None:
    """A beat that declares `at=`/`locations=` but no `entry_at=` makes no
    inherited-position claim at all -- `locations[0]` disagreeing with the
    inherited position must not raise. This is the corrected behaviour: the
    old check read `locations[0]` as the inherited claim and would have
    raised here."""
    emu = FakeEmulator(Path("rom"), Path("engine"), map_consts={ROUTE_01: (0, 33)})
    locations = (
        BeatLocation(ROUTE_01, 10, 10, "trigger tile, not an entry claim"),
        BeatLocation(ROUTE_01, 40, 40, "interaction point"),
    )
    beat = Beat("B2", "d", ok, locations)  # no entry_at=
    enter = _entry(0, 33, (999, 999))  # wildly disagrees with locations[0]

    _check_beat_continuity(beat, enter, emu)  # not checked at all, must not raise


# -- end-to-end through run_chapter -------------------------------------------

def test_run_chapter_fails_the_beat_on_continuity_mismatch(tmp_path: Path) -> None:
    """A full `run_chapter` attempt: B1 leaves the player at (5, 5); B2
    declares entry_at=WALKABLE_CELL on the same map. The mismatch must
    surface as B2's own failure, not a silent wrong start."""
    rom = tmp_path / "rom.gba"
    rom.write_bytes(bytes(0x400))

    def b1(emu: FakeEmulator) -> None:
        emu.advance()  # moves to (5, 5), the scripted position after B1

    def b2(emu: FakeEmulator) -> None:
        pass  # never reached; continuity check fails before this runs

    # B2's declared cell must itself be reachable (check 1 runs up front,
    # ahead of any attempt) -- WALKABLE_CELL, not the (5, 5) B1 actually
    # lands at, so this exercises check 2 (continuity) specifically, not
    # check 1 (reachability). entry_at= is what makes this an inherited-
    # position claim `_check_beat_continuity` actually checks.
    beats = (
        Beat("B1", "first", b1, ()),
        Beat("B2", "second", b2, (BeatLocation(ROUTE_01, *WALKABLE_CELL, "wrong"),),
             entry_at=WALKABLE_CELL),
    )
    chapter = Chapter(name="t_e2e", doc="reference/chapters/t_e2e.md", beats=beats)

    def factory(rom_path: Path, engine_path: Path, screenshot_dir):
        return FakeEmulator(rom_path, engine_path, screenshot_dir,
                             map_consts={ROUTE_01: (0, 33)},
                             positions=[(0, 0), (5, 5)])

    result = run_chapter(chapter, rom, tmp_path / "engine",
                          output_root=tmp_path / "out", emulator_factory=factory,
                          rerun_on_failure=False)

    assert result.verdict == "fail"
    b1_outcome, b2_outcome = result.attempts[0].beats
    assert b1_outcome.status == "pass"
    assert b2_outcome.status == "fail"
    assert f"({WALKABLE_CELL[0]}, {WALKABLE_CELL[1]})" in b2_outcome.error
    assert "(5, 5)" in b2_outcome.error
