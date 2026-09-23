"""Focused tests for a handful of C6 part two helpers (CH01 end to end):

- `beat_gen.reach.engine_spawn`: reads the new-game spawn off the real
  vendored engine's `new_game.c`.
- `beat_gen.group.plan_beats`: page-named beats when one event has two
  matches of the same archetype.
- `beat_gen.adapt._toggled_page`: derives `toggled_page_idx` from the page a
  toggling NPC's self-switch write reveals.
- `beat_gen.plan.PlannedBeat`: empty rows are legal only for "transit".
"""
from __future__ import annotations

import pytest

from rpg2gba.beat_floor.assertion import FloorAssertion, RowFloor, make_params
from rpg2gba.beat_gen import group
from rpg2gba.beat_gen.reach import engine_spawn
from rpg2gba.beat_gen.adapt import _toggled_page
from rpg2gba.beat_gen.plan import PlannedBeat, make_kwargs
from rpg2gba.chapter_manifest.archetypes import ArchetypeMatch
from rpg2gba.chapter_manifest.schema import ManifestRow, PageCondition


# ---------------------------------------------------------------------------
# engine_spawn -- against the real vendored engine (no RPG2GBA_* set)
# ---------------------------------------------------------------------------


def test_engine_spawn_reads_the_real_new_game_c():
    assert engine_spawn() == (49, (7, 7))


# ---------------------------------------------------------------------------
# group.plan_beats -- page-named beats for a double archetype match
# ---------------------------------------------------------------------------


def _page(map_id: int, event_id: int, page: int) -> ManifestRow:
    return ManifestRow(row_id=f"map{map_id:03d}/ev{event_id:03d}/p{page}", kind="page",
                       map_id=map_id, content_hash="x", event_id=event_id, page_idx=page)


def _match(archetype: str, map_id: int, event_id: int, page: int, role: str = "talk"
          ) -> ArchetypeMatch:
    row_id = f"map{map_id:03d}/ev{event_id:03d}/p{page}"
    return ArchetypeMatch(archetype=archetype, map_id=map_id, event_id=event_id,
                          params={}, roles={row_id: role}, prescribed={row_id: "beat"})


def _plain(row_id: str) -> RowFloor:
    return RowFloor(row_id=row_id, trigger="action", assertions=frozenset(), refusals=())


def test_two_matches_of_the_same_archetype_on_one_event_get_page_named_beats():
    p0, p1 = _page(32, 12, 0), _page(32, 12, 1)
    rows = [p0, p1]
    matches = [
        _match("flavour_npc", 32, 12, 0),
        _match("flavour_npc", 32, 12, 1),
    ]
    floors = {r.row_id: _plain(r.row_id) for r in rows}

    beats = group.plan_beats(rows, matches, floors)

    assert [b.name for b in beats] == ["m032e012p0_flavour_npc", "m032e012p1_flavour_npc"]
    assert all(b.template == "flavour_npc" for b in beats)


def test_single_match_of_an_archetype_is_not_page_named():
    # Sanity control: with only one match on the event, the plain
    # `m{map}e{event}_{archetype}` name is used, matching test_beat_gen_group.
    p0 = _page(36, 4, 0)
    beats = group.plan_beats([p0], [_match("flavour_npc", 36, 4, 0)],
                             {p0.row_id: _plain(p0.row_id)})
    assert [b.name for b in beats] == ["m036e004_flavour_npc"]


# ---------------------------------------------------------------------------
# adapt._toggled_page
# ---------------------------------------------------------------------------


def _self_switch_write_floor(row_id: str, event_id: int, letter: str) -> RowFloor:
    a = FloorAssertion(row_id=row_id, kind="self_switch_write", list_index=0, code=123,
                       params=make_params(event_id=event_id, letter=letter, value=0),
                       tag="flow")
    return RowFloor(row_id=row_id, trigger="action", assertions=frozenset({a}), refusals=())


def test_toggled_page_idx_derived_from_the_page_the_self_switch_reveals():
    talk_row = "map032/ev012/p0"
    floors = {talk_row: _self_switch_write_floor(talk_row, 12, "B")}
    rows = [
        ManifestRow(row_id=talk_row, kind="page", map_id=32, content_hash="x",
                   event_id=12, page_idx=0),
        ManifestRow(row_id="map032/ev012/p2", kind="page", map_id=32, content_hash="x",
                   event_id=12, page_idx=2, condition=PageCondition(self_switch_ch="B")),
    ]

    out = _toggled_page(talk_row, floors, rows)

    assert out == {"self_switch_letter": "B", "toggled_page_idx": 2}


def test_toggled_page_returns_empty_when_no_self_switch_write():
    talk_row = "map032/ev012/p0"
    floors = {talk_row: _plain(talk_row)}
    rows = [ManifestRow(row_id=talk_row, kind="page", map_id=32, content_hash="x",
                       event_id=12, page_idx=0)]

    assert _toggled_page(talk_row, floors, rows) == {}


def test_toggled_page_omits_letter_when_it_is_the_default_a():
    talk_row = "map032/ev012/p0"
    floors = {talk_row: _self_switch_write_floor(talk_row, 12, "A")}
    rows = [
        ManifestRow(row_id=talk_row, kind="page", map_id=32, content_hash="x",
                   event_id=12, page_idx=0),
        ManifestRow(row_id="map032/ev012/p2", kind="page", map_id=32, content_hash="x",
                   event_id=12, page_idx=2, condition=PageCondition(self_switch_ch="A")),
    ]

    out = _toggled_page(talk_row, floors, rows)

    assert "self_switch_letter" not in out
    assert out["toggled_page_idx"] == 2


# ---------------------------------------------------------------------------
# plan.PlannedBeat -- empty rows only for "transit"
# ---------------------------------------------------------------------------


def test_transit_beat_accepts_empty_rows():
    beat = PlannedBeat(name="a_transit", template="transit", map_id=1, rows=(),
                       group="a", kwargs=make_kwargs(hops=()))
    assert beat.rows == ()


def test_non_transit_beat_rejects_empty_rows():
    with pytest.raises(ValueError, match="claims no rows"):
        PlannedBeat(name="a", template="generic", map_id=1, rows=(), group="a")


def test_transit_beat_rejects_nonempty_rows():
    with pytest.raises(ValueError, match="must claim no rows"):
        PlannedBeat(name="a_transit", template="transit", map_id=1, rows=("map001/ev001/p0",),
                   group="a")
