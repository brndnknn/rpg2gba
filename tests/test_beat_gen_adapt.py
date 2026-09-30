"""Tests for `rpg2gba.beat_gen.adapt` (C6 Task 5).

The oracle for `archetype_kwargs` is the hand-written `ch05.py`: every
value in `EXPECTED` below is what its author typed into the template call
(B1-B9). The generator has to reach the same values from source data.

STATUS: implemented, skipped. DELETE the `pytestmark` line to start Task 5.
"""
from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest

from rpg2gba.beat_gen import adapt
from rpg2gba.beat_gen.emit import TEMPLATE_CALLS
from rpg2gba.beat_gen.plan import PlannedBeat
from rpg2gba.traversal.graph import MapGraph

CAVE_1F, CAVE_2F = "MAP_PASSAGE_CAVE_1F", "MAP_PASSAGE_CAVE_2F"
MAP_CONSTANTS = {35: "MAP_ROUTE_02", 36: CAVE_1F, 37: CAVE_2F, 40: "MAP_FORTY"}


def _trainer(const: str, event_id: int, map_const: str = CAVE_1F, map_id: int = 36) -> dict:
    return {"map_constant": map_const, "map_id": map_id, "event_id": event_id,
            "trainer_const": const, "defeat_flag": f"TRAINER_FLAGS_START + {const}",
            "trigger": "event_touch", "phone": False, "double": False,
            "retalk_pages": 1, "rider": False}


EXPECTED = {
    ("warp", 36, 1): {"map_constant": CAVE_1F, "map_id": 36, "event_id": 1,
                      "dest_map_constant": "MAP_ROUTE_02", "mechanism": "threshold"},
    ("warp", 36, 2): {"map_constant": CAVE_1F, "map_id": 36, "event_id": 2,
                      "dest_map_constant": CAVE_2F, "mechanism": "threshold"},
    ("warp", 37, 1): {"map_constant": CAVE_2F, "map_id": 37, "event_id": 1,
                      "dest_map_constant": CAVE_1F, "mechanism": "threshold"},
    ("warp", 37, 2): {"map_constant": CAVE_2F, "map_id": 37, "event_id": 2,
                      "dest_map_constant": "MAP_FORTY", "mechanism": "threshold"},
    ("arrival_nudge", 36, 2): {"map_constant": CAVE_1F, "map_id": 36, "event_id": 2,
                               "from_map_constant": CAVE_2F, "from_event_id": 1},
    ("item_ball", 36, 3): {"map_constant": CAVE_1F, "map_id": 36, "event_id": 3,
                           "item": "ITEM_ESCAPE_ROPE", "negative_beat": True},
    ("item_ball", 36, 5): {"map_constant": CAVE_1F, "map_id": 36, "event_id": 5,
                           "item": "ITEM_GREAT_BALL", "negative_beat": True},
    ("trainer", 36, 4): _trainer("TRAINER_MANNY_5", 4),
    ("trainer", 36, 6): _trainer("TRAINER_KEICHI_248", 6),
    ("trainer", 37, 4): _trainer("TRAINER_NUNES_128", 4, CAVE_2F, 37),
}

# Keywords the emitter supplies, or the route decides (Task 4 / route_kwargs).
NOT_SOURCE = {"builder", "chapter_id", "beat_name", "beat_prefix", "direction",
              "return_direction", "round_trip", "start_side", "approach_prefer", "group"}


@pytest.fixture(scope="module")
def ch05():
    from rpg2gba.beat_floor.walk import floor_for_chapter
    from rpg2gba.chapter_manifest.archetypes import classify_manifest
    from rpg2gba.playtest.archetypes import load_chapter_rows
    matches = {(m.archetype, m.map_id, m.event_id): m
               for m in classify_manifest(load_chapter_rows("CH05"))}
    return matches, floor_for_chapter("CH05", build_dir=Path("output/uranium-build"))


def _kwargs(key, ch05) -> dict:
    matches, floors = ch05
    m = matches[key]
    beat = PlannedBeat(name=f"m{key[1]:03d}e{key[2]:03d}_{key[0]}", template=key[0],
                       map_id=key[1], rows=tuple(sorted(m.roles)), group="g")
    return dict(adapt.archetype_kwargs(beat, m, floors,
                                       map_constant_fn=MAP_CONSTANTS.__getitem__))


# --- archetype_kwargs against the hand module -------------------------------

@pytest.mark.parametrize("key", sorted(EXPECTED), ids=lambda k: f"{k[0]}-{k[1]}-{k[2]}")
def test_matches_what_the_hand_author_typed(key, ch05):
    got = _kwargs(key, ch05)
    for name, value in EXPECTED[key].items():
        assert got.get(name) == value, f"{key} {name}: got {got.get(name)!r}"


@pytest.mark.parametrize("key", sorted(EXPECTED), ids=lambda k: f"{k[0]}-{k[1]}-{k[2]}")
def test_only_keywords_the_template_accepts_and_every_required_one(key, ch05):
    module, func, _ = TEMPLATE_CALLS[key[0]]
    params = inspect.signature(getattr(importlib.import_module(module), func)).parameters
    got = _kwargs(key, ch05)
    assert set(got) <= set(params) - NOT_SOURCE
    required = {n for n, p in params.items() if p.default is inspect.Parameter.empty}
    assert required - NOT_SOURCE <= set(got)


def test_kwargs_are_sorted(ch05):
    matches, floors = ch05
    m = matches[("trainer", 36, 4)]
    beat = PlannedBeat(name="t", template="trainer", map_id=36, rows=tuple(sorted(m.roles)),
                       group="g")
    got = adapt.archetype_kwargs(beat, m, floors, map_constant_fn=MAP_CONSTANTS.__getitem__)
    assert [k for k, _ in got] == sorted(k for k, _ in got)


def test_missing_floor_assertion_fails_loud(ch05):
    matches, floors = ch05
    m = matches[("item_ball", 36, 3)]
    beat = PlannedBeat(name="i", template="item_ball", map_id=36,
                       rows=tuple(sorted(m.roles)), group="g")
    stripped = dict(floors)
    grant = floors["map036/ev003/p0"]
    stripped["map036/ev003/p0"] = type(grant)(
        row_id=grant.row_id, trigger=grant.trigger, refusals=(),
        assertions=frozenset(a for a in grant.assertions if a.kind != "item_grant"))
    with pytest.raises(ValueError, match="map036/ev003"):
        adapt.archetype_kwargs(beat, m, stripped, map_constant_fn=MAP_CONSTANTS.__getitem__)


def test_single_page_item_ball_reads_its_own_self_switch_write():
    # map068/ev018 (Kevlar's Pokemon Center Antidote): one page, code 123
    # ['A', 0] -- no spent page to read the letter from, and the template
    # refuses to guess it.
    from rpg2gba.beat_floor.walk import floor_for_chapter
    from rpg2gba.chapter_manifest.archetypes import classify_manifest
    from rpg2gba.playtest.archetypes import load_chapter_rows
    m = next(m for m in classify_manifest(load_chapter_rows("CH03"))
             if (m.archetype, m.map_id, m.event_id) == ("item_ball", 68, 18))
    floors = floor_for_chapter("CH03", build_dir=Path("output/uranium-build"))
    beat = PlannedBeat(name="i", template="item_ball", map_id=68,
                       rows=tuple(sorted(m.roles)), group="g")
    got = dict(adapt.archetype_kwargs(beat, m, floors, map_constant_fn=lambda _: "MAP_X"))
    assert got["negative_beat"] is False
    assert got["self_switch_letter"] == "A"


@pytest.mark.parametrize(("chapter", "row_id", "expected"), [
    # map064/ev001: toggles inside page 0 (a self-switch branch); page 1 is
    # an unrelated switch-125 page. ROM run 35 read it as the second line.
    ("CH01", "map064/ev001/p0", None),
    # map073/ev005: page 1's self-switch reveals page 2.
    ("CH03", "map073/ev005/p1", 2),
])
def test_toggling_npc_names_its_revealed_page_or_none(chapter, row_id, expected):
    from rpg2gba.beat_floor.walk import floor_for_chapter
    from rpg2gba.chapter_manifest.archetypes import classify_manifest
    from rpg2gba.playtest.archetypes import load_chapter_rows
    rows = load_chapter_rows(chapter)
    m = next(m for m in classify_manifest(rows)
             if m.archetype == "flavour_npc" and row_id in m.roles)
    map_id = m.map_id
    floors = floor_for_chapter(chapter, build_dir=Path("output/uranium-build"))
    beat = PlannedBeat(name="f", template="flavour_npc", map_id=map_id,
                       rows=tuple(sorted(m.roles)), group="g")
    got = dict(adapt.archetype_kwargs(beat, m, floors, map_constant_fn=lambda _: "MAP_X",
                                      rows=rows))
    assert got["variant"] == "toggling"
    assert got["toggled_page_idx"] == expected


# --- warp_candidates ------------------------------------------------------------

def _graph(walls: set[tuple[int, int]] = frozenset()) -> MapGraph:
    blocked = {(x, y): (x, y) in walls for x in range(3) for y in range(3)}
    return MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=blocked)


def test_warp_candidates_open_all_round():
    got = adapt.warp_candidates((1, 1), _graph())
    assert [(c.side, c.x, c.y) for c in got] == [("north", 1, 0), ("east", 2, 1),
                                                 ("south", 1, 2), ("west", 0, 1)]


def test_warp_candidates_skip_walls_and_edges():
    got = adapt.warp_candidates((1, 0), _graph({(0, 0)}))   # top edge, wall to the west
    assert [c.side for c in got] == ["east", "south"]


def test_warp_candidates_skip_a_neighbouring_warp():
    # ROM run 51: stacked warps on one edge; standing on the next one fires it.
    graph = _graph()
    graph.warp_exits[(1, 0)] = []
    graph.warp_exits[(1, 2)] = []
    got = adapt.warp_candidates((1, 1), graph)
    assert [c.side for c in got] == ["east", "west"]


# --- route_kwargs ---------------------------------------------------------------

@pytest.mark.parametrize("side, press, back", [
    ("south", "UP", "DOWN"), ("north", "DOWN", "UP"),
    ("west", "RIGHT", "LEFT"), ("east", "LEFT", "RIGHT"),
])
def test_warp_pick_becomes_a_press(side, press, back):
    assert dict(adapt.route_kwargs("warp", side)) == {
        "direction": press, "return_direction": back, "round_trip": True}


@pytest.mark.parametrize("template", ["trainer", "item_ball", "flavour_npc", "generic"])
def test_other_templates_take_approach_prefer(template):
    assert adapt.route_kwargs(template, "east") == (("approach_prefer", "east"),)


def test_unknown_side_fails_loud():
    with pytest.raises(ValueError, match="up-ish"):
        adapt.route_kwargs("warp", "up-ish")
