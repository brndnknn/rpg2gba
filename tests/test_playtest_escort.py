"""Registration tests for `rpg2gba.playtest.archetypes.escort` (ruling 11).

Same offline discipline as `tests/test_playtest_generic_template.py`: only
what `escort_beat` REGISTERS (rows, declared assertions, locations) --
never the body driving an emulator (that's P11's boot gate). `cells.
approach_to`/`event_cell` and `archetypes.map_uranium_id` are monkeypatched
on the `escort` module's own bound names (it imports them by name), so
these tests need no staged `output/uranium-build/`.
"""
from __future__ import annotations

import pytest

from rpg2gba.beat_floor.assertion import FloorAssertion, FloorRefusal, RowFloor, make_params
from rpg2gba.playtest.archetypes import escort
from rpg2gba.playtest.chapter import ChapterBuilder

MAP_ID = 36
EVENT_ID = 5
PAGE = f"map{MAP_ID:03d}/ev{EVENT_ID:03d}/p0"
ARM0 = f"{PAGE}/b0"
ORIGIN_CONST = "MAP_PASSAGE_CAVE_1F"
DEST_CONST = "MAP_ROUTE_02"
DEST_UID = 99

APPROACH = (10, 10)
EVENT_XY = (10, 9)   # north of APPROACH: facing_toward picks "up"


def _builder() -> ChapterBuilder:
    return ChapterBuilder("TEST", doc="escort template test")


def _a(kind: str, list_index: int, row: str = PAGE, **params) -> FloorAssertion:
    return FloorAssertion(row_id=row, kind=kind, list_index=list_index,
                          code=None if list_index < 0 else 101, params=make_params(**params))


def _floor(*assertions: FloorAssertion, refused: bool = False, row: str = PAGE) -> RowFloor:
    refusals = (FloorRefusal(row, "text_unnormalizable", 0, 101, "x"),) if refused else ()
    return RowFloor(row_id=row, trigger="action", assertions=frozenset(assertions),
                    refusals=refusals)


def _warp(*, map_id: int = DEST_UID, x: int = 5, y: int = 6, direction: int = 0,
         arrives_on_door: bool = False, row: str = PAGE) -> FloorAssertion:
    return _a("warp", -1, row=row, map_id=map_id, x=x, y=y, direction=direction,
             arrives_on_door=arrives_on_door)


def _page_floor(*, trigger: str = "action", warp_kwargs: dict | None = None) -> RowFloor:
    warp_kwargs = warp_kwargs or {}
    return _floor(
        _a("trigger", -1, trigger=trigger),
        _a("completes", -1),
        _warp(**warp_kwargs),
        _a("text", 2, index=0, text="hi"),
        _a("audio", 1, code=241, name="bgm"),   # not in ESCORT_EXECUTED_KINDS
    )


def _arm_floor() -> RowFloor:
    return _floor(
        _a("switch_write", 5, row=ARM0, switch_id=10, value=True),
        _a("item_grant", 6, row=ARM0, item="POKEBALL", quantity=1),  # not executed
        row=ARM0,
    )


def _lookup(floors: dict[str, RowFloor]):
    def lookup(row_id: str) -> RowFloor:
        return floors[row_id]
    return lookup


def _patch_cells(monkeypatch, *, uid_by_const: dict[str, int] | None = None) -> None:
    monkeypatch.setattr(escort, "approach_to",
                        lambda map_constant, event_id, prefer=None: APPROACH)
    monkeypatch.setattr(escort, "event_cell",
                        lambda map_constant, event_id: EVENT_XY)
    table = uid_by_const if uid_by_const is not None else {DEST_CONST: DEST_UID}
    monkeypatch.setattr(escort, "map_uranium_id", lambda const: table[const])


def test_escort_beat_happy_path(monkeypatch):
    _patch_cells(monkeypatch)
    floors = {PAGE: _page_floor(), ARM0: _arm_floor()}
    b = _builder()
    escort.escort_beat(
        b, chapter_id="CH05", beat_name="m036e005_escort", rows=(PAGE, ARM0),
        map_constant=ORIGIN_CONST, map_id=MAP_ID, event_id=EVENT_ID,
        dest_map_constant=DEST_CONST, floor_lookup=_lookup(floors),
    )
    (beat,) = b.build().beats
    assert beat.rows == (PAGE, ARM0)
    assert beat.archetype == "warp"

    kinds = {a.kind for a in beat.assertions}
    assert kinds == {"trigger", "completes", "warp", "text", "switch_write"}
    assert "audio" not in kinds and "item_grant" not in kinds

    assert len(beat.locations) == 2
    origin_loc, dest_loc = beat.locations
    assert origin_loc.map_constant == ORIGIN_CONST
    assert (origin_loc.x, origin_loc.y) == APPROACH
    assert dest_loc.map_constant == DEST_CONST
    assert (dest_loc.x, dest_loc.y) == (5, 6)


def test_escort_beat_raises_on_non_action_trigger(monkeypatch):
    _patch_cells(monkeypatch)
    floors = {PAGE: _page_floor(trigger="player_touch"), ARM0: _arm_floor()}
    with pytest.raises(ValueError, match="action-button"):
        escort.escort_beat(
            _builder(), chapter_id="CH05", beat_name="e", rows=(PAGE,),
            map_constant=ORIGIN_CONST, map_id=MAP_ID, event_id=EVENT_ID,
            dest_map_constant=DEST_CONST, floor_lookup=_lookup(floors),
        )


def test_escort_beat_raises_on_warp_destination_mismatch(monkeypatch):
    # map_uranium_id(DEST_CONST) resolves to something other than the
    # floor's own warp map_id (DEST_UID).
    _patch_cells(monkeypatch, uid_by_const={DEST_CONST: DEST_UID + 1})
    floors = {PAGE: _page_floor()}
    with pytest.raises(ValueError, match="transfers to map"):
        escort.escort_beat(
            _builder(), chapter_id="CH05", beat_name="e", rows=(PAGE,),
            map_constant=ORIGIN_CONST, map_id=MAP_ID, event_id=EVENT_ID,
            dest_map_constant=DEST_CONST, floor_lookup=_lookup(floors),
        )


def test_escort_beat_raises_on_door_landing_with_retained_facing(monkeypatch):
    _patch_cells(monkeypatch)
    floors = {PAGE: _page_floor(warp_kwargs={"arrives_on_door": True, "direction": 0})}
    with pytest.raises(ValueError, match="retained"):
        escort.escort_beat(
            _builder(), chapter_id="CH05", beat_name="e", rows=(PAGE,),
            map_constant=ORIGIN_CONST, map_id=MAP_ID, event_id=EVENT_ID,
            dest_map_constant=DEST_CONST, floor_lookup=_lookup(floors),
        )


def test_escort_beat_raises_on_a_stray_row_from_another_page(monkeypatch):
    _patch_cells(monkeypatch)
    other_page = f"map{MAP_ID:03d}/ev{EVENT_ID:03d}/p1"
    stray = f"{other_page}/b0"
    floors = {PAGE: _page_floor(), ARM0: _arm_floor(),
             stray: _floor(_a("switch_write", 0, row=stray, switch_id=1, value=True), row=stray)}
    with pytest.raises(ValueError, match="not arms of"):
        escort.escort_beat(
            _builder(), chapter_id="CH05", beat_name="e", rows=(PAGE, stray),
            map_constant=ORIGIN_CONST, map_id=MAP_ID, event_id=EVENT_ID,
            dest_map_constant=DEST_CONST, floor_lookup=_lookup(floors),
        )


def test_escort_beat_raises_on_a_refused_floor(monkeypatch):
    _patch_cells(monkeypatch)
    floors = {PAGE: _floor(refused=True)}
    with pytest.raises(ValueError, match="refused"):
        escort.escort_beat(
            _builder(), chapter_id="CH05", beat_name="e", rows=(PAGE,),
            map_constant=ORIGIN_CONST, map_id=MAP_ID, event_id=EVENT_ID,
            dest_map_constant=DEST_CONST, floor_lookup=_lookup(floors),
        )
