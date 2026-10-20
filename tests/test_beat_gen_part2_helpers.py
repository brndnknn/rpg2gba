"""Focused tests for a handful of C6 part two helpers (CH01 end to end):

- `beat_gen.reach.engine_spawn`: reads the new-game spawn (MetadataHome)
  from the generated metadata header.
- `beat_gen.group.plan_beats`: page-named beats when one event has two
  matches of the same archetype.
- `beat_gen.plan.PlannedBeat`: empty rows are legal only for "transit".
"""
from __future__ import annotations

import pytest

from rpg2gba.beat_floor.assertion import RowFloor
from rpg2gba.beat_gen import group
from rpg2gba.beat_gen.reach import engine_spawn
from rpg2gba.beat_gen.plan import PlannedBeat, make_kwargs
from rpg2gba.chapter_manifest.archetypes import ArchetypeMatch
from rpg2gba.chapter_manifest.schema import ManifestRow


# ---------------------------------------------------------------------------
# engine_spawn -- MetadataHome
# ---------------------------------------------------------------------------


def test_engine_spawn_reads_metadata_home():
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


# ---------------------------------------------------------------------------
# __main__._successor_exit_group -- the crossing into the next chapter's maps
# ---------------------------------------------------------------------------


def _crossing_floor(row_id: str, kind: str, dest: int) -> RowFloor:
    from rpg2gba.beat_floor.assertion import FloorAssertion

    key = "map_id" if kind == "warp" else "other_map_id"
    return RowFloor(row_id=row_id, trigger="player_touch", refusals=(), assertions=frozenset({
        FloorAssertion(row_id=row_id, kind=kind, list_index=-1, code=None,
                       params=((key, dest),))}))


def test_successor_exit_is_the_seam_into_the_next_chapter_not_the_cave_warp_back():
    # CH06: page 2 of the park's cave warp leads back to map 37 (the
    # predecessor's); the Route 2 seam leads to map 35 (CH07's).
    from rpg2gba.beat_gen.__main__ import _successor_exit_group

    cave, seam = "map14002/ev019/p2", "map14000/seam/S/map035"
    floors = {cave: _crossing_floor(cave, "warp", 37),
              seam: _crossing_floor(seam, "seam_crossing", 35)}
    beats = [PlannedBeat(name="cave", template="warp", map_id=14002, rows=(cave,), group="cave"),
             PlannedBeat(name="seam", template="seam", map_id=14000, rows=(seam,), group="seam")]
    own = (40, 41, 42, 43, 46, 47)
    assert _successor_exit_group(beats, floors, own, (35,)) == "seam"
    # A split piece counts as its map (CH05's exit lands on piece 14002 of
    # map 40); the last chapter has no successor.
    assert _successor_exit_group(beats[:1], {cave: _crossing_floor(cave, "warp", 14002)},
                                 (36, 37), own) == "cave"
    assert _successor_exit_group(beats, floors, own, None) is None
    # Two crossings into the successor name neither.
    floors[cave] = _crossing_floor(cave, "warp", 35)
    assert _successor_exit_group(beats, floors, own, (35,)) is None
