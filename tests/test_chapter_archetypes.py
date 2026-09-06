"""Fingerprint tests for the archetype classifier, plus a frozen regression.

Positive/negative cases are small hand-built `ManifestRow` instances --
CLAUDE.md 4.6's "explicit edge-case test for whatever quirk" applies here as
"a plain dialogue NPC and a spent-page-only event must NOT match". The
regression test derives CH04's real manifest and asserts it equals
`reference/frozen/archetype_expectations.json`, frozen before this module
existed (task-mandated order: freeze, then derive, then diff).
"""
from __future__ import annotations

import json
from pathlib import Path

from rpg2gba.chapter_manifest.archetypes import (
    ARCHETYPE_NAMES,
    classify_event,
    classify_manifest,
)
from rpg2gba.chapter_manifest.schema import (
    ManifestRow,
    PageCondition,
    content_hash,
    page_row_id,
    row_from_dict,
)

_FROZEN_PATH = Path("reference/frozen/archetype_expectations.json")
_CH04_MANIFEST_PATH = Path("reference/manifests/CH04.manifest.json")


def _page(
    map_id: int,
    event_id: int,
    page_idx: int,
    *,
    trigger: str | None = "action",
    effects: tuple[str, ...] = (),
    script_heads: tuple[str, ...] = (),
    condition: PageCondition | None = None,
    script_typed_conditions: int = 0,
    unhandled: int | None = 0,
) -> ManifestRow:
    return ManifestRow(
        row_id=page_row_id(map_id, event_id, page_idx),
        kind="page",
        map_id=map_id,
        content_hash=content_hash({"e": event_id, "p": page_idx}),
        effects=effects,
        script_heads=script_heads,
        unhandled=unhandled,
        script_typed_conditions=script_typed_conditions,
        event_id=event_id,
        event_name=f"EV{event_id:03d}",
        page_idx=page_idx,
        condition=condition,
        trigger=trigger,
    )


# --- ARCHETYPE_NAMES ---------------------------------------------------


def test_archetype_names_are_the_four_documented_archetypes() -> None:
    assert ARCHETYPE_NAMES == frozenset({
        "trainer", "item_ball", "warp", "arrival_nudge",
    })


# --- trainer -------------------------------------------------------------


def test_trainer_battle_with_two_retalk_pages_and_phone() -> None:
    p0 = _page(
        35, 3, 0, trigger="event_touch",
        effects=("bubble_ui", "self_switch_write", "text", "trainerbattle"),
        script_heads=(
            "pbCallBub", "pbNoticePlayer", "pbPhoneRegisterBattle",
            "pbTrainerBattle", "pbTrainerEnd", "pbTrainerIntro",
        ),
    )
    p1 = _page(
        35, 3, 1,
        effects=("bubble_ui", "control_flow", "self_switch_write", "text"),
        script_heads=(
            "createPhoneTrainer", "pbCallBub", "pbPhoneBattleCount",
            "pbPhoneIncrement", "pbTrainerEnd", "pbTrainerIntro",
        ),
    )
    p2 = _page(
        35, 3, 2,
        effects=("bubble_ui", "control_flow", "text"),
        script_heads=("pbCallBub", "pbPhoneBattleCount", "pbPhoneRegisterBattle"),
    )
    matches = classify_event([p0, p1, p2])
    assert len(matches) == 1
    match = matches[0]
    assert match.archetype == "trainer"
    # `rider` is False here even though page 0 writes a self-switch: every
    # trainer page 0 does that to gate its re-talk page, so it carries no
    # signal. The param tracks an item grant folded into the battle page.
    assert match.params == {
        "trigger": "event_touch", "phone": True, "double": False,
        "retalk_pages": 2, "rider": False,
    }
    assert match.roles == {p0.row_id: "battle", p1.row_id: "retalk", p2.row_id: "retalk"}
    assert match.prescribed == {p0.row_id: "beat", p1.row_id: "beat", p2.row_id: "beat"}


def test_trainer_rider_is_true_only_when_the_battle_page_grants_an_item() -> None:
    p0 = _page(
        35, 99, 0, trigger="event_touch",
        effects=("giveitem", "self_switch_write", "text", "trainerbattle"),
        script_heads=(
            "pbReceiveItem", "pbTrainerBattle", "pbTrainerEnd", "pbTrainerIntro",
        ),
    )
    p1 = _page(
        35, 99, 1, effects=("bubble_ui", "text"), script_heads=("pbCallBub",),
    )
    match = classify_event([p0, p1])[0]
    assert match.params["rider"] is True


def test_trainer_battle_no_phone_one_retalk_page() -> None:
    p0 = _page(
        35, 12, 0, trigger="event_touch",
        effects=("bubble_ui", "self_switch_write", "text", "trainerbattle"),
        script_heads=(
            "pbCallBub", "pbNoticePlayer", "pbTrainerBattle",
            "pbTrainerEnd", "pbTrainerIntro",
        ),
    )
    p1 = _page(
        35, 12, 1,
        effects=("bubble_ui", "text"),
        script_heads=("pbCallBub",),
    )
    matches = classify_event([p0, p1])
    assert len(matches) == 1
    assert matches[0].params["phone"] is False
    assert matches[0].params["retalk_pages"] == 1


def test_trainer_double_battle_head_sets_double_param() -> None:
    p0 = _page(
        40, 1, 0, trigger="event_touch",
        effects=("trainerbattle",),
        script_heads=("pbDoubleTrainerBattle",),
    )
    matches = classify_event([p0])
    assert matches[0].params["double"] is True
    assert matches[0].params["retalk_pages"] == 0
    assert matches[0].roles == {p0.row_id: "battle"}


def test_plain_dialogue_npc_does_not_match_trainer() -> None:
    p0 = _page(35, 11, 0, effects=("bubble_ui", "se", "text"), script_heads=("pbCallBub",))
    assert classify_event([p0]) == ()


# --- item_ball -------------------------------------------------------------


def test_item_ball_grant_and_spent_pages() -> None:
    p0 = _page(
        35, 9, 0,
        effects=("giveitem", "self_switch_write"),
        script_heads=("pbItemBall",),
    )
    p1 = _page(35, 9, 1, condition=PageCondition(self_switch_ch="A"))
    matches = classify_event([p0, p1])
    assert len(matches) == 1
    match = matches[0]
    assert match.archetype == "item_ball"
    assert match.roles == {p0.row_id: "grant", p1.row_id: "spent"}
    assert match.prescribed == {p0.row_id: "beat", p1.row_id: "cosmetic"}


def test_item_ball_spent_page_only_does_not_match_alone() -> None:
    """A lone spent-page (no p0 grant) must not fabricate an item_ball match."""
    p1 = _page(35, 9, 1, condition=PageCondition(self_switch_ch="A"))
    assert classify_event([p1]) == ()


def test_item_ball_without_second_page_does_not_match() -> None:
    p0 = _page(
        35, 40, 0,
        effects=("giveitem", "self_switch_write"),
        script_heads=("pbItemBall",),
    )
    assert classify_event([p0]) == ()


def test_item_ball_second_page_not_gated_on_self_switch_does_not_match() -> None:
    p0 = _page(
        35, 41, 0,
        effects=("giveitem", "self_switch_write"),
        script_heads=("pbItemBall",),
    )
    p1 = _page(35, 41, 1)  # no self-switch condition
    assert classify_event([p0, p1]) == ()


# --- warp --------------------------------------------------------------


def test_warp_page_matches_on_warp_effect() -> None:
    p0 = _page(
        35, 1, 0, trigger="player_touch",
        effects=("graphic", "screen_fx", "warp"),
        script_heads=("pbCaveEntrance",),
    )
    matches = classify_event([p0])
    assert len(matches) == 1
    assert matches[0].archetype == "warp"
    assert matches[0].params == {"trigger": "player_touch"}
    assert matches[0].roles == {p0.row_id: "warp"}
    assert matches[0].prescribed == {p0.row_id: "beat"}


def test_page_without_warp_effect_does_not_match_warp() -> None:
    p0 = _page(35, 2, 0, effects=("text",))
    assert classify_event([p0]) == ()


# --- arrival_nudge -----------------------------------------------------


def _nudge_row(map_id: int, event_id: int, page_idx: int) -> ManifestRow:
    return _page(
        map_id, event_id, page_idx, trigger="autorun",
        effects=("graphic", "move_route", "temp_switch_write"),
        script_heads=("get_character", "setTempSwitchOn"),
        condition=PageCondition(switch1_id=22, switch1_name='s:tsOff?("A")'),
        script_typed_conditions=1,
        unhandled=2,
    )


def test_arrival_nudge_fingerprint() -> None:
    p1 = _nudge_row(35, 1, 1)
    matches = classify_event([p1])
    assert len(matches) == 1
    assert matches[0].archetype == "arrival_nudge"
    assert matches[0].roles == {p1.row_id: "nudge"}
    assert matches[0].prescribed == {p1.row_id: "beat"}


def test_arrival_nudge_requires_autorun_trigger() -> None:
    p1 = _nudge_row(35, 1, 1)
    not_autorun = ManifestRow(**{**p1.__dict__, "trigger": "action"})
    assert classify_event([not_autorun]) == ()


def test_arrival_nudge_requires_switch_condition() -> None:
    p1 = _nudge_row(35, 1, 1)
    no_condition = ManifestRow(**{**p1.__dict__, "condition": None})
    assert classify_event([no_condition]) == ()


def test_event_can_produce_warp_and_arrival_nudge_from_different_pages() -> None:
    """The documented map035/ev001 shape: p0 is a cave-entrance warp, p1 is
    the arrival-nudge staging page. One event, two archetype matches, no
    role collision -- see the module docstring for why this is page-level
    rather than merged into one event-spanning match."""
    p0 = _page(
        35, 1, 0, trigger="player_touch",
        effects=("graphic", "screen_fx", "warp"),
        script_heads=("pbCaveEntrance",),
    )
    p1 = _nudge_row(35, 1, 1)
    matches = classify_event([p0, p1])
    assert len(matches) == 2
    archetypes = {match.archetype for match in matches}
    assert archetypes == {"warp", "arrival_nudge"}
    all_roles: dict[str, str] = {}
    for match in matches:
        all_roles.update(match.roles)
    assert all_roles == {p0.row_id: "warp", p1.row_id: "nudge"}


# --- classify_manifest: grouping, ordering, kind filtering ------------------


def test_classify_manifest_skips_seam_and_terrain_rows() -> None:
    seam = ManifestRow(
        row_id="map035/seam/N/map040", kind="seam", map_id=35,
        content_hash=content_hash("x"), effects=("warp",),
    )
    terrain = ManifestRow(
        row_id="map037/terrain/stairs/11,10", kind="terrain", map_id=37,
        content_hash=content_hash("y"),
    )
    assert classify_manifest([seam, terrain]) == ()


def test_classify_manifest_groups_by_map_and_event_and_sorts_output() -> None:
    # Event 2's rows come first in input order; event 1 should sort first.
    ev2_p0 = _page(
        35, 2, 0, trigger="player_touch", effects=("warp",),
    )
    ev1_p0 = _page(
        35, 1, 0,
        effects=("giveitem", "self_switch_write"),
        script_heads=("pbItemBall",),
    )
    ev1_p1 = _page(35, 1, 1, condition=PageCondition(self_switch_ch="A"))
    matches = classify_manifest([ev2_p0, ev1_p0, ev1_p1])
    assert [match.event_id for match in matches] == [1, 2]


# --- regression: CH04 real manifest vs. the frozen expectations file -------


def test_ch04_manifest_matches_frozen_expectations() -> None:
    rows_data = json.loads(_CH04_MANIFEST_PATH.read_text(encoding="utf-8"))
    rows = [row_from_dict(data) for data in rows_data]
    matches = classify_manifest(rows)

    derived = [
        {
            "archetype": match.archetype,
            "map_id": match.map_id,
            "event_id": match.event_id,
            "params": dict(match.params),
            "roles": dict(match.roles),
            "prescribed": dict(match.prescribed),
        }
        for match in matches
    ]

    frozen = json.loads(_FROZEN_PATH.read_text(encoding="utf-8"))
    expected = frozen["CH04"]["matches"]

    assert derived == expected


# --- inherited-beat trigger resolution ----------------------------------


def test_resolved_trigger_scripts_exempts_only_inherited_registered_beats() -> None:
    """A trigger a predecessor's beat already ran is not foreign any more.

    Three properties in one, because they are the three ways this can go
    wrong:

    * an INHERITED beat's dispositioned row is exempt (CH04:B4 defeated
      Timothy, so CH05 may walk across his event-touch tile);
    * a row whose beat is DEFERRED is NOT exempt -- a `beat:` disposition is
      an intent, and CH04 disposes `beat:` on rows it never runs;
    * this chapter's OWN triggers are never exempt, which is the check.
    """
    from rpg2gba.playtest.chapter import load_chapter, resolved_trigger_scripts

    resolved = resolved_trigger_scripts(load_chapter("CH05"))

    # CH04:B4 fights Timothy (map035/ev012/p0) during the replay.
    assert "Map035_EV012_Page1" in resolved.get(35, set())

    # CH04's B8/B10 are in DEFERRED_BEATS -- dispositioned, never run.
    assert "Map035_EV001_Page2" not in resolved.get(35, set())
    assert "Map035_EV003_Page2" not in resolved.get(35, set())

    # CH05's own maps contribute nothing: its own beats are not inherited.
    assert 36 not in resolved
    assert 37 not in resolved


def test_a_chapter_with_no_predecessor_resolves_nothing() -> None:
    """The exemption exists only for a replay. CH01 has no predecessor, so
    every trigger stays foreign to it -- the pre-existing behaviour."""
    from rpg2gba.playtest.chapter import load_chapter, resolved_trigger_scripts

    assert resolved_trigger_scripts(load_chapter("CH01")) == {}


def test_page_row_script_names_the_compiled_label() -> None:
    """The row id's page number is 0-based, the label's is 1-based -- the
    one place that knows it, so the two exemption paths cannot drift."""
    from rpg2gba.playtest.chapter import page_row_script

    assert page_row_script("map037/ev004/p0") == (37, "Map037_EV004_Page1")
    assert page_row_script("map035/ev012/p1") == (35, "Map035_EV012_Page2")
    # Seam and terrain rows name no page script at all.
    assert page_row_script("map035/seam/NORTH/map036") is None
    assert page_row_script("map037/terrain/stairs/20,9") is None


def test_own_rows_become_exempt_only_after_their_beat_passes() -> None:
    """The narrowing in `resolved_trigger_scripts` is about a trigger the
    chapter has not resolved YET; it must not outlive the beat.

    CH05's B14 walks west from B9's stop across Hiker Nunes' two
    event-touch tiles, and B9 defeated him two beats earlier -- so by then
    the tile fires nothing. Before B9 runs, the same tile is a real
    finding, and that must not change.
    """
    from rpg2gba.playtest.runner import _WalkOracle

    oracle = _WalkOracle("CH05")
    assert oracle._resolved_scripts.get(37, set()) == set()

    # Terrain rows contribute nothing (B14's own rows are stair cells).
    oracle.mark_rows_resolved(
        ("map037/terrain/stairs/20,9", "map037/terrain/stairs/20,10"))
    assert oracle._resolved_scripts.get(37, set()) == set()

    # B9's battle page, once B9 has passed.
    oracle.mark_rows_resolved(("map037/ev004/p0",))
    assert oracle._resolved_scripts[37] == {"Map037_EV004_Page1"}


def test_marking_a_row_drops_the_cached_overlay_for_that_map() -> None:
    """The overlay is built once per map with the exemption already baked
    in, so a newly resolved page has to invalidate it -- otherwise the
    beat that resolved the trigger is the last one to benefit."""
    from rpg2gba.playtest.runner import _WalkOracle

    oracle = _WalkOracle("CH05")
    oracle._triggers[37] = {(1, 1): ()}
    oracle._triggers[36] = {(2, 2): ()}

    oracle.mark_rows_resolved(("map037/ev004/p0",))

    assert 37 not in oracle._triggers      # rebuilt with the new exemption
    assert 36 in oracle._triggers          # untouched map keeps its cache
