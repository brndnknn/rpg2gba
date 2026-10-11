"""Tests for the derived beat-locations layer (`routing.locations`).

This module is what lets step 6 approve an ORDER before the chapter's
playtest module exists, so its two load-bearing behaviours are: it resolves
every dispositioned beat to exactly one routing point, and it refuses --
loudly -- to invent one for a row shape it cannot locate (CLAUDE.md §4.5).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.playtest.chapter import _validate_row_id
from rpg2gba.routing import locations as loc_mod
from rpg2gba.routing.locations import (
    ApproachCandidate,
    BeatLocationRecord,
    RowCell,
    cell_for_row,
    chapter_from_locations,
    choose_routing_point,
    load_locations,
    write_locations,
)
from rpg2gba.tileset_converter.stairs import StairSide
from rpg2gba.traversal.graph import MapGraph


def _cell(row_id: str, x: int, y: int, map_constant: str = "MAP_A") -> RowCell:
    return RowCell(row_id=row_id, map_constant=map_constant, x=x, y=y,
                   resolver="test")


def _open_grid(width: int, height: int) -> dict[tuple[int, int], bool]:
    return {(x, y): False for x in range(width) for y in range(height)}


# --------------------------------------------------------------------------
# approach-side / stair-side candidate derivation (the operator-approved
# schema addition: `approach_candidates` alongside the existing single x/y)
# --------------------------------------------------------------------------


def test_approach_side_candidates_all_four_walkable(monkeypatch):
    """Four walkable sides emit four `ApproachCandidate`s in N/S/E/W order,
    each carrying a paste-able `prefer=` resolver string."""
    graph = MapGraph(map_id=999, width=5, height=5, tileset_id=0,
                      blocked=_open_grid(5, 5))
    monkeypatch.setattr(loc_mod, "build_map_graph", lambda map_id: graph)
    monkeypatch.setattr(loc_mod, "event_cell", lambda mc, ev: (2, 2))

    candidates = loc_mod._approach_side_candidates(999, "MAP_X", 7)

    assert [(c.x, c.y, c.side) for c in candidates] == [
        (2, 1, "north"), (2, 3, "south"), (3, 2, "east"), (1, 2, "west"),
    ]
    assert candidates[0].resolver == 'approach_to(MAP_X, ev7, prefer="north")'
    assert candidates[3].resolver == 'approach_to(MAP_X, ev7, prefer="west")'


def test_approach_side_candidates_skip_unwalkable_sides(monkeypatch):
    """A blocked side is simply absent -- never a placeholder or a guess."""
    blocked = _open_grid(5, 5)
    blocked[(2, 1)] = True  # north of the event is walled
    graph = MapGraph(map_id=999, width=5, height=5, tileset_id=0, blocked=blocked)
    monkeypatch.setattr(loc_mod, "build_map_graph", lambda map_id: graph)
    monkeypatch.setattr(loc_mod, "event_cell", lambda mc, ev: (2, 2))

    candidates = loc_mod._approach_side_candidates(999, "MAP_X", 7)

    assert [c.side for c in candidates] == ["south", "east", "west"]


def test_approach_side_candidates_skip_a_warp_tile(monkeypatch):
    """CH06's Fufufu stands below the gym door: the door tile is no side."""
    graph = MapGraph(map_id=999, width=5, height=5, tileset_id=0,
                     blocked=_open_grid(5, 5), warp_exits={(2, 1): ()})
    monkeypatch.setattr(loc_mod, "build_map_graph", lambda map_id: graph)
    monkeypatch.setattr(loc_mod, "event_cell", lambda mc, ev: (2, 2))

    candidates = loc_mod._approach_side_candidates(999, "MAP_X", 7)

    assert [c.side for c in candidates] == ["south", "east", "west"]


def test_stair_side_candidates_both_sides_legal(monkeypatch):
    """A stair beat with both E/W neighbours walkable emits both, west then
    east -- the full set `_stair_approach` itself picks the first (west) of."""
    graph = MapGraph(
        map_id=999, width=5, height=5, tileset_id=0, blocked=_open_grid(5, 5),
        stair_sides={(2, 2): StairSide.RIGHT},
    )
    monkeypatch.setattr(loc_mod, "build_map_graph", lambda map_id: graph)

    candidates = loc_mod._stair_side_candidates(999, "MAP_X", 2, 2)

    assert [(c.x, c.y, c.side) for c in candidates] == [(1, 2, "west"), (3, 2, "east")]
    # Since 2026-09-08 `playtest.cells.stair_approach` takes a required side
    # (POST_CH05_REVIEW.md G4), so the resolver is a real paste-able call
    # rather than the prose-as-code this used to have to emit.
    for c in candidates:
        assert c.resolver.startswith("stair_approach(MAP_X, ")
        assert f"side={c.side!r}" in c.resolver



class _Row:
    """Minimal ManifestRow stand-in; cell_for_row only reads these fields."""

    def __init__(self, row_id: str, kind: str, map_id: int = 37,
                 event_id: int | None = None, trigger: str | None = None,
                 terrain=None) -> None:
        self.row_id = row_id
        self.kind = kind
        self.map_id = map_id
        self.event_id = event_id
        self.trigger = trigger
        self.terrain = terrain


# --------------------------------------------------------------------------
# choose_routing_point
# --------------------------------------------------------------------------

def test_identical_cells_collapse_without_a_policy_decision():
    """Several pages of one event resolve to the same cell -- the common
    case must never reach the multi-cell rule at all."""
    candidates = (_cell("map036/ev003/p0", 10, 34),
                  _cell("map036/ev003/p1", 10, 34))
    assert choose_routing_point("B2", candidates) is candidates[0]


def test_multi_cell_beat_routes_on_its_terminal_row():
    """A beat spanning distinct cells is a traversal, represented by where
    it ENDS -- routing cost is about where the NEXT beat departs from."""
    first = _cell("map036/ev002/p0", 17, 4, "MAP_PASSAGE_CAVE_1F")
    last = _cell("map037/ev001/p0", 16, 27, "MAP_PASSAGE_CAVE_2F")
    assert choose_routing_point("B8", (first, last)) is last


def test_duplicates_do_not_shadow_the_terminal_cell():
    """Deduplication must preserve order, so a repeated early cell cannot
    win over a genuinely later one."""
    a = _cell("r0", 1, 1)
    a_again = _cell("r1", 1, 1)
    b = _cell("r2", 9, 9)
    assert choose_routing_point("B?", (a, a_again, b)) is b


def test_single_candidate_is_returned_unchanged():
    only = _cell("map036/ev001/p0", 17, 40)
    assert choose_routing_point("B1", (only,)) is only


# --------------------------------------------------------------------------
# cell_for_row -- fail-loud paths (no map data needed)
# --------------------------------------------------------------------------

def test_seam_row_fails_loud_rather_than_guessing_a_cell():
    """Seam rows carry a direction/offset, not a cell, and no resolver in
    cells.py converts one. Guessing here is exactly the silent default §4.5
    forbids."""
    with pytest.raises(ValueError, match="seam rows carry a connection"):
        cell_for_row(_Row("map035/seam/NORTH/map036", "seam"))


def test_unknown_trigger_fails_loud_naming_the_fix():
    with pytest.raises(ValueError, match="has no cell rule"):
        cell_for_row(_Row("map036/ev007/p0", "page", event_id=7,
                          trigger="parallel_process"))


def test_page_row_without_event_id_fails_loud():
    with pytest.raises(ValueError, match="no event_id"):
        cell_for_row(_Row("map036/ev007/p0", "page", trigger="action"))


def test_unknown_row_kind_fails_loud():
    with pytest.raises(ValueError, match="unknown row kind"):
        cell_for_row(_Row("map036/whatever", "cutscene"))


# --------------------------------------------------------------------------
# persistence round trip
# --------------------------------------------------------------------------

def test_locations_file_round_trips(tmp_path: Path):
    records = [
        BeatLocationRecord(
            beat_id="B8",
            map_constant="MAP_PASSAGE_CAVE_2F",
            x=16, y=27,
            resolver="event_cell(MAP_PASSAGE_CAVE_2F, ev1)",
            rows=("map036/ev002/p0", "map037/ev001/p0"),
            candidates=(_cell("map036/ev002/p0", 17, 4, "MAP_PASSAGE_CAVE_1F"),
                        _cell("map037/ev001/p0", 16, 27, "MAP_PASSAGE_CAVE_2F")),
        ),
    ]
    path = tmp_path / "CH05.locations.json"
    write_locations("CH05", records, path)

    chapter_id, loaded = load_locations(path)
    assert chapter_id == "CH05"
    assert loaded == records


def test_approach_candidates_round_trip(tmp_path: Path):
    """`approach_candidates` is a distinct field from `candidates` (row
    candidates), round-tripping its own x/y/side/resolver shape."""
    records = [
        BeatLocationRecord(
            beat_id="B10", map_constant="MAP_PASSAGE_CAVE_2F", x=8, y=6,
            resolver='approach_to(MAP_PASSAGE_CAVE_2F, ev5)',
            rows=("map037/ev005/p0",),
            candidates=(_cell("map037/ev005/p0", 8, 6, "MAP_PASSAGE_CAVE_2F"),),
            approach_candidates=(
                ApproachCandidate(8, 6, "north",
                                  'approach_to(MAP_PASSAGE_CAVE_2F, ev5, prefer="north")'),
                ApproachCandidate(8, 8, "south",
                                  'approach_to(MAP_PASSAGE_CAVE_2F, ev5, prefer="south")'),
            ),
        ),
    ]
    path = tmp_path / "CH05.locations.json"
    write_locations("CH05", records, path)

    chapter_id, loaded = load_locations(path)
    assert chapter_id == "CH05"
    assert loaded == records

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["beats"][0]["approach_candidates"] == [
        {"x": 8, "y": 6, "side": "north",
         "resolver": 'approach_to(MAP_PASSAGE_CAVE_2F, ev5, prefer="north")'},
        {"x": 8, "y": 8, "side": "south",
         "resolver": 'approach_to(MAP_PASSAGE_CAVE_2F, ev5, prefer="south")'},
    ]
    # `candidates` (row candidates) is untouched by the new field -- still
    # exactly its own row_id/map_constant/x/y/resolver shape.
    assert payload["beats"][0]["candidates"] == [
        {"row_id": "map037/ev005/p0", "map_constant": "MAP_PASSAGE_CAVE_2F",
         "x": 8, "y": 6, "resolver": "test"},
    ]


def test_locations_file_without_approach_candidates_still_loads(tmp_path: Path):
    """A committed file written before this field existed must still load --
    `load_locations` defaults it, never invalidating an older file."""
    path = tmp_path / "CH05.locations.json"
    path.write_text(json.dumps({
        "chapter": "CH05",
        "beats": [{
            "beat_id": "B1", "map_constant": "MAP_A", "x": 1, "y": 1,
            "resolver": "event_cell(MAP_A, ev1)", "rows": ["map036/ev001/p0"],
            "candidates": [],
        }],
    }), encoding="utf-8")

    chapter_id, loaded = load_locations(path)
    assert chapter_id == "CH05"
    assert loaded[0].approach_candidates == ()


def test_every_candidate_is_persisted_for_review(tmp_path: Path):
    """The whole point of auto-resolving is that the reviewer can still see
    what was collapsed and overrule it at STOP 3."""
    records = [
        BeatLocationRecord(
            beat_id="B13", map_constant="MAP_PASSAGE_CAVE_2F", x=10, y=9,
            resolver="stair_approach(MAP_PASSAGE_CAVE_2F, stair=(11,9))",
            rows=("map037/terrain/stairs/11,10", "map037/terrain/stairs/11,9"),
            candidates=(_cell("map037/terrain/stairs/11,10", 10, 10),
                        _cell("map037/terrain/stairs/11,9", 10, 9)),
        ),
    ]
    path = tmp_path / "CH05.locations.json"
    write_locations("CH05", records, path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert len(payload["beats"][0]["candidates"]) == 2


# --------------------------------------------------------------------------
# the synthetic Chapter handed to the solver
# --------------------------------------------------------------------------

def _records() -> list[BeatLocationRecord]:
    return [
        BeatLocationRecord("B1", "MAP_PASSAGE_CAVE_1F", 17, 40, "event_cell",
                           ("map036/ev001/p0",),
                           (_cell("map036/ev001/p0", 17, 40),)),
        BeatLocationRecord("B2", "MAP_PASSAGE_CAVE_1F", 10, 34, "approach_to",
                           ("map036/ev003/p0",),
                           (_cell("map036/ev003/p0", 10, 34),)),
    ]


def test_synthetic_chapter_carries_the_derived_locations():
    chapter = chapter_from_locations("CH05", _records())
    assert [b.name for b in chapter.beats] == ["B1", "B2"]
    assert [(b.locations[0].x, b.locations[0].y) for b in chapter.beats] == [
        (17, 40), (10, 34)]


def test_synthetic_chapter_beats_are_singleton_groups():
    """No grouping is derived: collapsing beats into one indivisible stop is
    an authoring decision, and inventing one would silently constrain the
    order the solver is supposed to be free to choose."""
    chapter = chapter_from_locations("CH05", _records())
    assert [g.group_id for g in chapter.groups()] == ["B1", "B2"]


def test_synthetic_chapter_bodies_refuse_to_run():
    """A derived chapter is for the offline solve only; running one would be
    a silently empty playthrough."""
    chapter = chapter_from_locations("CH05", _records())
    with pytest.raises(RuntimeError, match="offline route solve"):
        chapter.beats[0].run(None)


# --------------------------------------------------------------------------
# the chapter.py row-id gap terrain rows exposed
# --------------------------------------------------------------------------

def test_terrain_row_ids_are_valid_beat_rows():
    """Terrain rows were rejected by `_validate_row_id` until 2026-09-04,
    which made CH05's B13/B14 unable to claim the stair rows they exercise."""
    _validate_row_id("map037/terrain/stairs/11,9", beat_name="B13")


def test_page_and_seam_row_ids_still_validate():
    _validate_row_id("map035/ev014/p1", beat_name="B1")
    _validate_row_id("map035/seam/NORTH/map036", beat_name="B1")


def test_a_bare_nonsense_row_id_still_fails():
    with pytest.raises(ValueError, match="row-id shape"):
        _validate_row_id("map037/stairs/11,9", beat_name="B13")
