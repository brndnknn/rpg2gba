"""Tests for `rpg2gba.beat_gen.group` (C6 Task 2).

STATUS: implemented, skipped. DELETE the `pytestmark` line to start Task 2.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.beat_floor.assertion import FloorAssertion, RowFloor, make_params
from rpg2gba.beat_gen import group
from rpg2gba.chapter_manifest.archetypes import ArchetypeMatch
from rpg2gba.chapter_manifest.schema import ManifestRow, SeamRef, TerrainRef


def _page(map_id: int, event_id: int, page: int) -> ManifestRow:
    return ManifestRow(row_id=f"map{map_id:03d}/ev{event_id:03d}/p{page}", kind="page",
                       map_id=map_id, content_hash="x", event_id=event_id, page_idx=page)


def _arm(parent: str, n: int, *, parent_row: str | None = None) -> ManifestRow:
    # `parent_row` lets a nested arm name its enclosing ARM as parent_row_id.
    return ManifestRow(row_id=f"{parent}/b{n}", kind="branch", map_id=int(parent[3:6]),
                       content_hash="x", parent_row_id=parent_row or parent)


def _stair(map_id: int, x: int, y: int, behavior: str = "MB_SIDEWAYS_STAIRS_LEFT_SIDE",
           ev: int = 1) -> ManifestRow:
    return ManifestRow(row_id=f"map{map_id:03d}/terrain/stairs/{x},{y}", kind="terrain",
                       map_id=map_id, content_hash="x",
                       terrain=TerrainRef(x=x, y=y, behavior=behavior, source_event_id=ev))


def _seam(map_id: int, direction: str, other: int) -> ManifestRow:
    return ManifestRow(row_id=f"map{map_id:03d}/seam/{direction}/map{other:03d}", kind="seam",
                       map_id=map_id, content_hash="x",
                       seam=SeamRef(map_id=map_id, direction=direction, offset=0,
                                    other_map_id=other, other_direction="S", other_offset=0))


def _match(archetype: str, map_id: int, event_id: int, pages: dict[int, str]) -> ArchetypeMatch:
    roles = {f"map{map_id:03d}/ev{event_id:03d}/p{p}": role for p, role in pages.items()}
    return ArchetypeMatch(archetype=archetype, map_id=map_id, event_id=event_id,
                          params={}, roles=roles, prescribed={r: "beat" for r in roles})


def _plain(row_id: str) -> RowFloor:
    return RowFloor(row_id=row_id, trigger="action", assertions=frozenset(), refusals=())


def _rock(row_id: str, capability: str = "rock_smash") -> RowFloor:
    a = FloorAssertion(row_id=row_id, kind="blocked_obstacle", list_index=-1, code=None,
                       params=make_params(x=1, y=1, capability=capability), tag="position")
    return RowFloor(row_id=row_id, trigger="action", assertions=frozenset({a}), refusals=())


def _floors(rows, special: dict[str, RowFloor] | None = None) -> dict[str, RowFloor]:
    special = special or {}
    return {r.row_id: special.get(r.row_id, _plain(r.row_id)) for r in rows}


def _by_name(beats):
    return {b.name: b for b in beats}


# --- owning_page ------------------------------------------------------------

def test_owning_page_of_a_page_is_itself():
    assert group.owning_page(_page(1, 2, 0)) == "map001/ev002/p0"


def test_owning_page_of_a_nested_arm():
    page = "map001/ev002/p0"
    nested = _arm(page, 3, parent_row=f"{page}/b1")   # b3 sits inside b1
    assert group.owning_page(nested) == page


def test_owning_page_rejects_row_level_kinds():
    with pytest.raises(ValueError):
        group.owning_page(_seam(35, "N", 40))


# --- beat_name --------------------------------------------------------------

def test_names():
    assert group.beat_name("trainer", [_page(36, 4, 0), _page(36, 4, 1)]) == "m036e004_trainer"
    assert group.beat_name("generic", [_page(37, 5, 1)]) == "m037e005p1"
    assert group.beat_name("obstacle", [_page(32, 14, 0), _page(32, 15, 0)],
                           key="rock_smash") == "m032obstacle_rock_smash"
    assert group.beat_name("stair", [_stair(37, 11, 10), _stair(37, 11, 9)]) == "m037stair11x9"
    assert group.beat_name("seam", [_seam(35, "N", 40)]) == "m035seamN040"


def test_name_does_not_depend_on_row_order():
    a, b = _page(36, 4, 0), _page(36, 4, 1)
    assert group.beat_name("trainer", [a, b]) == group.beat_name("trainer", [b, a])


# --- plan_beats: the claiming order ----------------------------------------

def test_archetype_claims_its_pages_and_arms_ride_in_an_arms_beat():
    p0, p1 = _page(36, 4, 0), _page(36, 4, 1)
    b0, b1 = _arm(p0.row_id, 0), _arm(p0.row_id, 1)
    rows = [p0, b0, b1, p1]
    beats = group.plan_beats(rows, [_match("trainer", 36, 4, {0: "battle", 1: "retalk"})],
                             _floors(rows))
    assert [b.name for b in beats] == ["m036e004_trainer", "m036e004_trainer_arms"]
    main, arms = beats
    assert main.template == "trainer" and main.rows == (p0.row_id, p1.row_id)
    assert arms.template == "generic" and arms.rows == (b0.row_id, b1.row_id)
    assert arms.group == main.group == "m036e004_trainer"
    assert arms.kwarg("skip_claimed") is True


def test_switch_gated_retalk_leaves_the_trainer_group():
    # The Nowtoch gym trainers: p1 (self-switch A, their own defeat) stays in
    # the group; p2 (switch 58, written by the leader) takes its own beat so
    # the route can put the battle before the leader (operator call 2026-10-10).
    from dataclasses import replace

    from rpg2gba.chapter_manifest.schema import PageCondition

    p0, p1 = _page(42, 1, 0), _page(42, 1, 1)
    p1 = replace(p1, condition=PageCondition(self_switch_ch="A"))
    p2 = replace(_page(42, 1, 2), condition=PageCondition(switch1_id=58))
    rows = [p0, p1, p2]
    match = _match("trainer", 42, 1, {0: "battle", 1: "retalk", 2: "retalk"})
    assert group.deferred_retalks(match, {r.row_id: r for r in rows}) == (p2.row_id,)
    beats = _by_name(group.plan_beats(rows, [match], _floors(rows)))
    main = beats["m042e001_trainer"]
    assert main.rows == (p0.row_id, p1.row_id)
    assert main.kwarg("deferred_retalks") == (p2.row_id,)
    assert beats["m042e001p2"].template == "generic"
    assert beats["m042e001p2"].group != main.group


def test_self_switch_retalks_stay_in_the_trainer_group():
    from dataclasses import replace

    from rpg2gba.chapter_manifest.schema import PageCondition

    p0 = _page(36, 4, 0)
    p1 = replace(_page(36, 4, 1), condition=PageCondition(self_switch_ch="A"))
    match = _match("trainer", 36, 4, {0: "battle", 1: "retalk"})
    assert group.deferred_retalks(match, {r.row_id: r for r in (p0, p1)}) == ()


def test_match_with_an_unowned_row_is_dropped_to_generic():
    # p1 was refused upstream, so it is not in `owned`: the trainer template
    # cannot register half a match, and p0 falls to the generic template.
    p0 = _page(36, 4, 0)
    beats = group.plan_beats([p0], [_match("trainer", 36, 4, {0: "battle", 1: "retalk"})],
                             _floors([p0]))
    assert [(b.name, b.template) for b in beats] == [("m036e004p0", "generic")]


def test_unclaimed_page_gets_a_generic_beat_with_its_own_arms():
    p0 = _page(37, 5, 0)
    b0, b1 = _arm(p0.row_id, 0), _arm(p0.row_id, 1)
    rows = [p0, b0, b1]
    (beat,) = group.plan_beats(rows, [], _floors(rows))
    assert (beat.name, beat.template) == ("m037e005p0", "generic")
    assert beat.rows == (p0.row_id, b0.row_id, b1.row_id)
    assert beat.kwargs == ()


def test_arms_of_an_unowned_page_get_their_own_generic_beat():
    page_id = "map037/ev005/p0"               # refused upstream, not owned
    b0 = _arm(page_id, 0)
    (beat,) = group.plan_beats([b0], [], _floors([b0]))
    assert beat.template == "generic" and beat.rows == (b0.row_id,)
    assert beat.name == "m037e005p0_arms"


def test_obstacles_group_by_map_and_capability():
    r1, r2, r3 = _page(32, 14, 0), _page(32, 15, 0), _page(32, 16, 0)
    s1 = _page(32, 20, 0)
    rows = [r1, s1, r2, r3]
    floors = _floors(rows, {r1.row_id: _rock(r1.row_id), r2.row_id: _rock(r2.row_id),
                            r3.row_id: _rock(r3.row_id), s1.row_id: _rock(s1.row_id, "strength")})
    beats = _by_name(group.plan_beats(rows, [], floors))
    rock = beats["m032obstacle_rock_smash"]
    assert rock.template == "obstacle"
    assert rock.rows == (r1.row_id, r2.row_id, r3.row_id)
    assert rock.kwarg("capability") == "rock_smash"
    assert beats["m032obstacle_strength"].rows == (s1.row_id,)


def test_stairs_group_by_adjacent_cells_not_by_event():
    # Real CH05 shape: every stair CELL has its own source event.
    rows = [_stair(37, 11, 9, ev=8), _stair(37, 11, 10, ev=7),
            _stair(37, 20, 9, "MB_SIDEWAYS_STAIRS_RIGHT_SIDE", ev=6),
            _stair(37, 20, 10, "MB_SIDEWAYS_STAIRS_RIGHT_SIDE", ev=3)]
    beats = _by_name(group.plan_beats(rows, [], _floors(rows)))
    assert set(beats) == {"m037stair11x9", "m037stair20x9"}
    assert beats["m037stair11x9"].rows == ("map037/terrain/stairs/11,9",
                                           "map037/terrain/stairs/11,10")


def test_adjacent_stairs_with_different_behavior_are_separate():
    rows = [_stair(37, 11, 9), _stair(37, 11, 10, "MB_SIDEWAYS_STAIRS_RIGHT_SIDE")]
    assert len(group.plan_beats(rows, [], _floors(rows))) == 2


def test_each_seam_is_its_own_beat():
    rows = [_seam(35, "N", 40), _seam(35, "S", 31)]
    beats = group.plan_beats(rows, [], _floors(rows))
    assert [(b.name, b.template) for b in beats] == [("m035seamN040", "seam"),
                                                     ("m035seamS031", "seam")]


def test_order_follows_first_row_in_manifest_order():
    a, b = _page(1, 9, 0), _page(1, 3, 0)
    beats = group.plan_beats([a, b], [], _floors([a, b]))
    assert [x.name for x in beats] == ["m001e009p0", "m001e003p0"]


# --- warp match becomes an escort when the page is action-triggered --------

def _warp_page(map_id: int, event_id: int, page: int = 0) -> ManifestRow:
    return ManifestRow(row_id=f"map{map_id:03d}/ev{event_id:03d}/p{page}", kind="page",
                       map_id=map_id, content_hash="x", event_id=event_id, page_idx=page,
                       trigger="action")


def _warp_match(map_id: int, event_id: int, page: int = 0) -> ArchetypeMatch:
    row_id = f"map{map_id:03d}/ev{event_id:03d}/p{page}"
    return ArchetypeMatch(archetype="warp", map_id=map_id, event_id=event_id,
                          params={}, roles={row_id: "warp"}, prescribed={row_id: "beat"})


def test_action_trigger_warp_match_becomes_one_escort_beat_with_its_arms():
    p0 = _warp_page(41, 6)
    b0, b1 = _arm(p0.row_id, 0), _arm(p0.row_id, 1)
    rows = [p0, b0, b1]
    beats = group.plan_beats(rows, [_warp_match(41, 6)], _floors(rows))
    assert [(b.name, b.template) for b in beats] == [("m041e006_escort", "escort")]
    (beat,) = beats
    assert beat.rows == (p0.row_id, b0.row_id, b1.row_id)
    assert beat.group == "m041e006_escort"


def test_player_touch_warp_match_is_unchanged():
    p0 = _page(41, 6, 0)   # `_page`: no `trigger` field set (defaults, not "action")
    b0 = _arm(p0.row_id, 0)
    rows = [p0, b0]
    beats = group.plan_beats(rows, [_warp_match(41, 6)], _floors(rows))
    assert [(b.name, b.template) for b in beats] == [
        ("m041e006_warp", "warp"), ("m041e006_warp_arms", "generic"),
    ]
    main, arms = beats
    assert main.rows == (p0.row_id,)
    assert arms.rows == (b0.row_id,)


def test_every_row_claimed_exactly_once():
    p0, p1 = _page(36, 4, 0), _page(36, 4, 1)
    rows = [p0, _arm(p0.row_id, 0), p1, _page(36, 7, 0), _stair(36, 1, 1)]
    beats = group.plan_beats(rows, [_match("trainer", 36, 4, {0: "battle", 1: "retalk"})],
                             _floors(rows))
    claimed = [r for b in beats for r in b.rows]
    assert sorted(claimed) == sorted(r.row_id for r in rows)


def test_deterministic():
    p0 = _page(36, 4, 0)
    rows = [p0, _arm(p0.row_id, 0), _page(36, 5, 0)]
    m = [_match("trainer", 36, 4, {0: "battle"})]
    assert group.plan_beats(rows, m, _floors(rows)) == group.plan_beats(rows, m, _floors(rows))


# --- real data: CH05 --------------------------------------------------------

def test_real_ch05_plan():
    from rpg2gba.beat_floor.walk import floor_for_chapter
    from rpg2gba.beat_gen.select import select_rows
    from rpg2gba.chapter_manifest.archetypes import classify_manifest
    from rpg2gba.playtest.archetypes import load_chapter_rows
    from rpg2gba.story_state.model import build_chapter_stories

    build = Path("output/uranium-build")
    rows = load_chapter_rows("CH05")
    story = build_chapter_stories(["CH01", "CH02", "CH03", "CH04", "CH05"], build_dir=build,
                                  chapters_path=Path("reference/chapters.json"))["CH05"]
    floors = floor_for_chapter("CH05", build_dir=build)
    sel = select_rows(rows, {v.row_id: v for v in story.rows}, floors)
    beats = group.plan_beats(sel.owned, classify_manifest(rows), floors)

    assert [b.name for b in beats] == [
        "m036e001_warp",
        "m036e002_warp",
        "m036e002_arrival_nudge", "m036e002_arrival_nudge_arms",
        "m036e003_item_ball", "m036e003_item_ball_arms",
        "m036e004_trainer", "m036e004_trainer_arms",
        "m036e005_item_ball", "m036e005_item_ball_arms",
        "m036e006_trainer", "m036e006_trainer_arms",
        "m037e001_warp",
        "m037e002_warp",
        "m037e004_trainer", "m037e004_trainer_arms",
        "m037e005p0", "m037e005p1",
        "m037stair11x9", "m037stair20x9",
    ]
    claimed = sorted(r for b in beats for r in b.rows)
    assert claimed == sorted(r.row_id for r in sel.owned)
