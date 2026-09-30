"""Tests for `beat_gen.moved_objects` (ROM run 24: flag + live) and its
consumers: the emitted `moved_by=` kwarg, the review section, and the
flavour harness's three `_start_talk` branches."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from rpg2gba.beat_gen import emit, review
from rpg2gba.beat_gen.moved_objects import scene_moved_events
from rpg2gba.beat_gen.plan import ChapterPlan, PlannedBeat, make_kwargs
from rpg2gba.playtest import assertions
from rpg2gba.playtest.archetypes import flavour_npc
from rpg2gba.playtest.errors import ScenarioError
from rpg2gba.traversal.collision import load_map_json

BUILD_MAPS = Path(__file__).resolve().parents[1] / "output" / "uranium-build" / "maps"


def _route(*codes: int) -> dict:
    return {"__class__": "RPG::MoveRoute",
            "list": [{"__class__": "RPG::MoveCommand", "code": c, "parameters": []}
                     for c in (*codes, 0)]}


def _cmd(code: int, *params) -> dict:
    return {"code": code, "indent": 0, "parameters": list(params)}


def _event(eid: int, *pages: list[dict]) -> dict:
    return {"id": eid, "pages": [{"list": lst} for lst in pages]}


def test_own_page_209_self_move() -> None:
    ev = _event(5, [_cmd(209, 0, _route(3))])
    assert scene_moved_events(50, [ev]) == {5: ("map050/ev005/p0",)}


def test_209_from_another_event_and_rows_sorted() -> None:
    ev5 = _event(5, [_cmd(101)])
    ev19 = _event(19, [_cmd(209, 5, _route(1))], [_cmd(209, 5, _route(14))])
    got = scene_moved_events(50, [None, ev19, ev5])
    assert got == {5: ("map050/ev019/p0", "map050/ev019/p1")}


def test_202_set_event_location() -> None:
    ev = _event(7, [_cmd(202, 0, 0, 3, 4, 2)])
    assert scene_moved_events(9, [ev, _event(8, [_cmd(202, 7, 0, 1, 1, 2)])]) == {
        7: ("map009/ev007/p0", "map009/ev008/p0")}


def test_turn_only_route_not_flagged() -> None:
    ev = _event(5, [_cmd(209, 0, _route(16, 17, 29))])
    assert scene_moved_events(50, [ev]) == {}


def test_player_target_ignored() -> None:
    ev = _event(5, [_cmd(209, -1, _route(4)), _cmd(202, -1, 0, 1, 1, 2)])
    assert scene_moved_events(50, [ev]) == {}


@pytest.mark.parametrize("cmd", [
    _cmd(209), _cmd(209, 0), _cmd(209, 0, {"list": "x"}), _cmd(209, "a", _route(1)),
    _cmd(209, 0, {"list": [{"parameters": []}]}), _cmd(202),
])
def test_malformed_fails_loud_with_row_id(cmd: dict) -> None:
    with pytest.raises(ValueError, match="map050/ev005/p0"):
        scene_moved_events(50, [_event(5, [cmd])])


@pytest.mark.skipif(not (BUILD_MAPS / "Map050.json").exists(), reason="no build output")
def test_real_map050_flags_professor_and_ev20() -> None:
    got = scene_moved_events(50, load_map_json(50, BUILD_MAPS)["events"])
    assert "map050/ev005/p0" in got[5]
    assert "map050/ev019/p0" in got[5]
    assert "map050/ev019/p0" in got[20]


# --- emit / review --------------------------------------------------------------

def _beat(**kw) -> PlannedBeat:
    return PlannedBeat(name="m050e005p1", template="flavour_npc", map_id=50,
                       rows=("map050/ev005/p1",), group="m050e005p1",
                       kwargs=make_kwargs(map_id=50, event_id=5, **kw))


def test_emit_moved_by_only_when_non_empty() -> None:
    plain = emit.render_call("ch01", "CH01", _beat())
    assert "moved_by" not in plain
    moved = emit.render_call("ch01", "CH01", _beat(moved_by=("map050/ev005/p0",)))
    assert "    moved_by=('map050/ev005/p0',),\n" in moved


def test_review_lists_scene_moved_npcs() -> None:
    def doc(*beats: PlannedBeat) -> str:
        plan = ChapterPlan(chapter_id="CH01", predecessor=None, beats=beats)
        return review._scene_moved(plan, locate=None)
    assert doc(_beat()) == ["none"]
    lines = doc(_beat(moved_by=("map050/ev005/p0",)))
    assert len(lines) == 1 and "m050e005p1" in lines[0] and "map050/ev005/p0" in lines[0]


# --- _start_talk branches --------------------------------------------------------

class _Emu:
    def __init__(self, live: tuple[int, int]) -> None:
        self.live = live
        self.walks: list[tuple[int, int]] = []
        self.faced: list[str] = []
        self.interacts = 0

    class _Ev:
        def __init__(self, x: int, y: int) -> None:
            self.x, self.y = x, y

    def object_event(self, local_id: int) -> "_Emu._Ev":
        return self._Ev(*self.live)

    def walk_to(self, x: int, y: int) -> None:
        self.walks.append((x, y))

    def face(self, direction: str) -> None:
        self.faced.append(direction)

    def interact(self, require_script: bool = True) -> bool:
        self.interacts += 1
        return True

    def screenshot(self, name: str) -> str:
        return f"{name}.png"


@pytest.fixture
def talk(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    live_calls: list[tuple] = []
    monkeypatch.setattr(flavour_npc, "local_id", lambda mc, ev: 3)
    monkeypatch.setattr(flavour_npc, "has_local_id", lambda mc, ev: True)
    monkeypatch.setattr(flavour_npc, "event_cell", lambda mc, ev: (14, 6))
    monkeypatch.setattr(flavour_npc, "event_page_moves", lambda mc, ev, pg: False)
    monkeypatch.setattr(assertions, "talk_to_moving_npc",
                        lambda emu, beat, lid, **kw: live_calls.append((beat, lid)))
    return live_calls


def _go(emu: _Emu, moved_by: tuple[str, ...] = ()) -> None:
    flavour_npc._start_talk(emu, "B1", "MAP_X", 5, 1, (14, 7), "UP", "must speak", moved_by)


def test_start_talk_strict_when_npc_at_template(talk: list[tuple]) -> None:
    emu = _Emu((14, 6))
    _go(emu)
    assert (emu.faced, emu.interacts, talk) == (["UP"], 1, [])


def test_start_talk_follows_live_when_flagged(talk: list[tuple],
                                              caplog: pytest.LogCaptureFixture) -> None:
    emu = _Emu((15, 6))
    with caplog.at_level(logging.INFO):
        _go(emu, ("map050/ev005/p0",))
    assert talk == [("B1", 3)] and emu.interacts == 0
    assert "(15, 6)" in caplog.text and "(14, 6)" in caplog.text
    assert "map050/ev005/p0" in caplog.text


def test_start_talk_fails_loud_when_unflagged_and_displaced(talk: list[tuple]) -> None:
    emu = _Emu((15, 6))
    with pytest.raises(ScenarioError, match=r"B1.*\(15, 6\).*\(14, 6\).*no page moves"):
        _go(emu)
    assert talk == [] and emu.interacts == 0


def test_start_talk_strict_for_a_background_talk_target(
        talk: list[tuple], monkeypatch: pytest.MonkeyPatch) -> None:
    # ROM run 25: a sign/bookshelf is no object event, so it has no local id
    # and no live position; the strict path runs without reading one.
    monkeypatch.setattr(flavour_npc, "has_local_id", lambda mc, ev: False)

    def no_local_id(mc: str, ev: int) -> int:
        raise AssertionError("local_id read for a non-object event")

    monkeypatch.setattr(flavour_npc, "local_id", no_local_id)
    emu = _Emu((99, 99))
    _go(emu)
    assert (emu.faced, emu.interacts, talk) == (["UP"], 1, [])


def test_has_local_id_on_real_staging() -> None:
    from rpg2gba.playtest.cells import has_local_id
    # ROM run 25: map049 ev4 is a background talk target, no object event.
    assert has_local_id("MAP_MOKI_TOWN_PLAYERS_HOUSE_1F", 4) is False
    assert has_local_id("MAP_MOKI_TOWN_PROFESSOR_LAB", 5) is True
