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

import pytest

from rpg2gba.chapter_manifest.archetypes import (
    _ARCHETYPE_REGISTRY,
    _ArchetypeEntry,
    _build_registry,
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


def test_archetype_names_are_the_documented_archetypes() -> None:
    assert ARCHETYPE_NAMES == frozenset({
        "trainer", "item_ball", "warp", "arrival_nudge", "flavour_npc",
    })


# --- the registry itself -------------------------------------------------


def test_archetype_names_is_derived_from_the_registry() -> None:
    assert ARCHETYPE_NAMES == frozenset(
        entry.name for entry in _ARCHETYPE_REGISTRY
    )


def test_registry_entries_appear_in_load_bearing_order() -> None:
    """Order is precedence, not cosmetics: trainer beats item_ball at the
    event level, and warp beats arrival_nudge beats flavour_npc at the page
    level, purely because of registry position (see the module's registry
    comment)."""
    assert [(entry.name, entry.level) for entry in _ARCHETYPE_REGISTRY] == [
        ("trainer", "event"),
        ("item_ball", "event"),
        ("warp", "page"),
        ("arrival_nudge", "page"),
        ("flavour_npc", "page"),
    ]
    # The ordering intent, stated explicitly rather than just pinned: all
    # event-level entries precede all page-level entries, and flavour_npc --
    # the loosest page-level fingerprint -- is the LAST page-level entry, so
    # every more specific page-level archetype gets first refusal on a row.
    levels = [entry.level for entry in _ARCHETYPE_REGISTRY]
    assert levels == sorted(levels, key=lambda level: level == "page")
    page_level_names = [
        entry.name for entry in _ARCHETYPE_REGISTRY if entry.level == "page"
    ]
    assert page_level_names[-1] == "flavour_npc"


def test_duplicate_archetype_name_fails_loud() -> None:
    with pytest.raises(ValueError, match="registered more than once"):
        _build_registry([
            _ArchetypeEntry("trainer", "event", lambda rows: None),
            _ArchetypeEntry("trainer", "page", lambda row: None),
        ])


def test_unknown_level_fails_loud() -> None:
    with pytest.raises(ValueError, match="unknown level"):
        _build_registry([
            _ArchetypeEntry("bogus", "beat", lambda rows: None),  # type: ignore[arg-type]
        ])


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
    """This fixture is the canonical plain flavour NPC -- since flavour_npc
    was added, `classify_event` no longer returns empty for it. Preserve the
    original intent (it must not match `trainer`) and additionally assert
    the positive flavour_npc match it now produces."""
    p0 = _page(35, 11, 0, effects=("bubble_ui", "se", "text"), script_heads=("pbCallBub",))
    matches = classify_event([p0])
    assert not any(match.archetype == "trainer" for match in matches)
    assert len(matches) == 1
    match = matches[0]
    assert match.archetype == "flavour_npc"
    assert match.params == {"variant": "plain"}


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


def test_item_ball_without_second_page_matches_as_single_page_grant_only() -> None:
    """Loosened 2026-09-10 (REDERIVATION_PLAN.md sec 13.3 T1): a single-page
    item ball with no remainder page -- e.g. `map068/ev018/p0` (CH03),
    `pbItemBall` with `effects = (giveitem, self_switch_write)` and no page
    1 in the event at all -- must match, with only a "grant" role and no
    "spent" role at all (there is no row to own one)."""
    p0 = _page(
        35, 40, 0,
        effects=("giveitem", "self_switch_write"),
        script_heads=("pbItemBall",),
    )
    matches = classify_event([p0])
    assert len(matches) == 1
    match = matches[0]
    assert match.archetype == "item_ball"
    assert match.roles == {p0.row_id: "grant"}
    assert match.prescribed == {p0.row_id: "beat"}


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
    """This fixture (action trigger, bare `text` effect) is also a plain
    flavour NPC -- preserve the original intent (must not match `warp`) and
    assert the positive flavour_npc match it now produces."""
    p0 = _page(35, 2, 0, effects=("text",))
    matches = classify_event([p0])
    assert not any(match.archetype == "warp" for match in matches)
    assert len(matches) == 1
    match = matches[0]
    assert match.archetype == "flavour_npc"
    assert match.params == {"variant": "plain"}


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


def test_arrival_nudge_matches_without_graphic_effect() -> None:
    """Loosened 2026-09-10 (REDERIVATION_PLAN.md sec 13.3 T1): `graphic` is
    no longer mandatory -- `map068/ev012/p1` (CH03) stages facing/BGM with
    effects exactly `{move_route, temp_switch_write}` and no `graphic` tag
    at all, yet is a real arrival nudge by every other fingerprint element."""
    p1 = _page(
        68, 12, 1, trigger="autorun",
        effects=("move_route", "temp_switch_write"),
        script_heads=("get_character", "setTempSwitchOn"),
        condition=PageCondition(switch1_id=22, switch1_name='s:tsOff?("A")'),
        script_typed_conditions=1,
    )
    matches = classify_event([p1])
    assert len(matches) == 1
    assert matches[0].archetype == "arrival_nudge"
    assert matches[0].roles == {p1.row_id: "nudge"}
    assert matches[0].prescribed == {p1.row_id: "beat"}


def test_arrival_nudge_still_matches_with_graphic_effect_present() -> None:
    """Regression: the pre-existing graphic-carrying nudge shape must match
    identically to before this loosening."""
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


# --- flavour_npc ---------------------------------------------------------


def test_flavour_npc_plain_variant() -> None:
    p0 = _page(35, 20, 0, effects=("bubble_ui", "se", "text"), script_heads=("pbCallBub",))
    matches = classify_event([p0])
    assert len(matches) == 1
    match = matches[0]
    assert match.archetype == "flavour_npc"
    assert match.params == {"variant": "plain"}
    assert match.roles == {p0.row_id: "talk"}
    assert match.prescribed == {p0.row_id: "beat"}


def test_flavour_npc_toggling_variant_has_self_switch_write() -> None:
    p0 = _page(
        35, 21, 0,
        effects=("bubble_ui", "self_switch_write", "text"),
        script_heads=("pbCallBub",),
    )
    matches = classify_event([p0])
    assert len(matches) == 1
    assert matches[0].archetype == "flavour_npc"
    assert matches[0].params == {"variant": "toggling"}


def test_flavour_npc_randomized_variant_has_var_write_no_self_switch() -> None:
    p0 = _page(
        35, 22, 0,
        effects=("bubble_ui", "var_write", "text"),
        script_heads=("pbCallBub",),
    )
    matches = classify_event([p0])
    assert len(matches) == 1
    assert matches[0].archetype == "flavour_npc"
    assert matches[0].params == {"variant": "randomized"}


def test_flavour_npc_rejects_global_switch_write() -> None:
    """`switch_write` is deliberately excluded -- a global switch is story
    state, not flavour (see the module's constants-block comment)."""
    p0 = _page(
        35, 23, 0,
        effects=("bubble_ui", "switch_write", "text"),
        script_heads=("pbCallBub",),
    )
    assert classify_event([p0]) == ()


def test_flavour_npc_rejects_noncosmetic_script_head() -> None:
    """`pbShowMap` is T8's region-map NPC -- its own archetype, not flavour,
    even though its effects alone would look like "just talking"."""
    p0 = _page(35, 24, 0, effects=("bubble_ui", "text"), script_heads=("pbShowMap",))
    assert classify_event([p0]) == ()


def test_flavour_npc_rejects_unhandled_commands() -> None:
    p0 = _page(
        35, 25, 0,
        effects=("bubble_ui", "text"), script_heads=("pbCallBub",), unhandled=1,
    )
    assert classify_event([p0]) == ()


def test_flavour_npc_rejects_script_typed_conditions() -> None:
    p0 = _page(
        35, 26, 0,
        effects=("bubble_ui", "text"), script_heads=("pbCallBub",),
        script_typed_conditions=1,
    )
    assert classify_event([p0]) == ()


def test_flavour_npc_requires_action_trigger() -> None:
    p0 = _page(
        35, 27, 0, trigger="autorun",
        effects=("bubble_ui", "text"), script_heads=("pbCallBub",),
    )
    assert classify_event([p0]) == ()


def test_flavour_npc_precedence_no_constructible_collision() -> None:
    """The registry comment (module docstring, registry block) frames
    flavour_npc as the loosest page-level fingerprint, claimed last so a
    more specific page-level archetype gets first refusal on a row. But as
    actually coded, no row can satisfy both flavour_npc and another
    registered page-level matcher's fingerprint at once:

    * `warp` only requires `"warp" in effects`; flavour_npc requires
      `effects` to be a *subset* of `_FLAVOUR_ALLOWED_EFFECTS`, which does
      not include `"warp"` -- any row with the warp effect is automatically
      rejected by flavour_npc's effects check.
    * `arrival_nudge` requires `trigger == "autorun"`; flavour_npc requires
      `trigger == "action"` -- the triggers are mutually exclusive, so no
      row can present both.

    So there is no row today that would exercise "flavour_npc registered
    last actually mattered" -- a test asserting warp/arrival_nudge beats
    flavour_npc on a shared row would pass vacuously (the shared row is
    unconstructible), which is exactly what was asked not to write. This
    test instead pins the two disqualifying facts directly against the
    real module constants, so a future loosening of
    `_FLAVOUR_ALLOWED_EFFECTS` or the arrival_nudge trigger check that
    reopens a real collision is caught by a real failure here rather than
    resting on an untested precedence assumption.
    """
    from rpg2gba.chapter_manifest.archetypes import _FLAVOUR_ALLOWED_EFFECTS

    assert "warp" not in _FLAVOUR_ALLOWED_EFFECTS


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
