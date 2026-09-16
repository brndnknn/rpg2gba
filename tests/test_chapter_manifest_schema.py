"""Round-trip and rule tests for the manifest's shared contract.

The generator writes rows and the checker reads them back. Those are separate
modules, so the round trip is the seam where a schema change can silently
diverge: the generator emits a new field, a lenient reader defaults it away,
and the rules then evaluate against a row that is not the row on disk. These
tests pin the round trip strict in both directions.
"""
from __future__ import annotations

import pytest

from rpg2gba.chapter_manifest.schema import (
    BranchRef,
    Disposition,
    DispositionError,
    ManifestRow,
    PageCondition,
    SeamRef,
    TerrainRef,
    branch_row_id,
    content_hash,
    page_row_id,
    parse_row_id,
    row_from_dict,
    row_id_sort_key,
    row_to_dict,
    seam_row_id,
    terrain_row_id,
)


def _page_row() -> ManifestRow:
    return ManifestRow(
        row_id=page_row_id(35, 3, 1),
        kind="page",
        map_id=35,
        content_hash=content_hash({"list": [{"code": 101}]}),
        effects=("giveitem", "text"),
        script_heads=("pbItemBall", "pbSomethingNovel"),
        unrecognized_heads=("pbSomethingNovel",),
        other_codes=(213,),
        requires=("rock_smash",),
        unhandled=2,
        script_typed_conditions=1,
        event_id=3,
        event_name="Trainer(4)",
        page_idx=1,
        condition=PageCondition(self_switch_ch="A", switch1_id=55, switch1_name="gym1_cleared"),
        trigger="action button",
    )


def _seam_row() -> ManifestRow:
    return ManifestRow(
        row_id=seam_row_id(35, "N", 40),
        kind="seam",
        map_id=35,
        content_hash=content_hash([35, "N", 0, 40, "S", 15]),
        effects=("warp",),
        seam=SeamRef(35, "N", 0, 40, "S", 15),
    )


def _terrain_row() -> ManifestRow:
    terrain = TerrainRef(x=12, y=8, behavior="MB_SIDEWAYS_STAIRS_LEFT_SIDE", source_event_id=6)
    return ManifestRow(
        row_id=terrain_row_id(37, "stairs", 12, 8),
        kind="terrain",
        map_id=37,
        content_hash=content_hash({
            "x": 12, "y": 8, "behavior": "MB_SIDEWAYS_STAIRS_LEFT_SIDE", "source_event_id": 6,
        }),
        effects=(),
        terrain=terrain,
    )


@pytest.mark.parametrize("row", [_page_row(), _seam_row(), _terrain_row()])
def test_row_round_trips_exactly(row: ManifestRow) -> None:
    assert row_from_dict(row_to_dict(row)) == row


def test_terrain_row_id_formatting() -> None:
    assert terrain_row_id(37, "stairs", 12, 8) == "map037/terrain/stairs/12,8"


def test_terrain_row_is_never_cosmetic() -> None:
    assert not _terrain_row().may_be_cosmetic


def test_row_from_dict_rejects_a_missing_field() -> None:
    payload = row_to_dict(_page_row())
    del payload["requires"]
    with pytest.raises(ValueError, match="missing"):
        row_from_dict(payload)


def test_row_from_dict_rejects_an_unknown_field() -> None:
    payload = row_to_dict(_page_row())
    payload["reachable_from"] = ["B12"]
    with pytest.raises(ValueError, match="unknown"):
        row_from_dict(payload)


def test_content_hash_is_key_order_independent() -> None:
    assert content_hash({"a": 1, "b": 2}) == content_hash({"b": 2, "a": 1})


def test_content_hash_tracks_a_content_change() -> None:
    before = content_hash({"list": [{"code": 101, "parameters": ["hi"]}]})
    after = content_hash({"list": [{"code": 101, "parameters": ["bye"]}]})
    assert before != after


def test_condition_describes_rather_than_exposing_raw_values() -> None:
    condition = PageCondition(self_switch_ch="A", variable_id=7, variable_name="rival", variable_min=3)
    described = condition.describe()
    assert "self-switch A is ON" in described
    assert "variable 7 (rival) >= 3" in described


def test_unconditional_page_describes_as_always() -> None:
    assert PageCondition().describe() == "always"
    assert PageCondition().is_unconditional


def test_self_switch_write_forbids_cosmetic() -> None:
    """A dialogue NPC that sets a self-switch changes its own future behaviour."""
    row = ManifestRow(
        row_id="x", kind="page", map_id=1, content_hash="0",
        effects=("text", "self_switch_write"),
    )
    assert not row.may_be_cosmetic
    assert row.blocking_tags() == ("self_switch_write",)


def test_pure_dialogue_page_may_be_cosmetic() -> None:
    # `unhandled=0` explicitly: this test is about cosmetic-safe effects,
    # not staging status, and the default is now `None` ("never staged"),
    # which would make `may_be_cosmetic` False for an unrelated reason.
    row = ManifestRow(
        row_id="x", kind="page", map_id=1, content_hash="0", effects=("text", "se"),
        unhandled=0,
    )
    assert row.may_be_cosmetic


def test_unstaged_row_forbids_cosmetic_even_with_no_effects() -> None:
    """`unhandled is None` (never staged) is its own veto, independent of
    the unhandled-count check and the effects check below it -- an
    unmeasured row is never "clean", even with an empty effect set."""
    row = ManifestRow(
        row_id="x", kind="page", map_id=1, content_hash="0", effects=(),
        unhandled=None,
    )
    assert not row.may_be_cosmetic


def test_unhandled_queue_entries_forbid_cosmetic() -> None:
    """The free check for a dead conversion with no beat written at all."""
    row = ManifestRow(
        row_id="x", kind="page", map_id=1, content_hash="0", effects=("text",), unhandled=1,
    )
    assert not row.may_be_cosmetic


@pytest.mark.parametrize("tag", ["control_flow", "erase_event", "temp_switch_write"])
def test_new_state_writing_tags_forbid_cosmetic(tag: str) -> None:
    row = ManifestRow(
        row_id="x", kind="page", map_id=1, content_hash="0", effects=("text", tag),
    )
    assert not row.may_be_cosmetic
    assert tag in row.blocking_tags()


@pytest.mark.parametrize("tag", ["bubble_ui", "animation", "screen_fx"])
def test_new_cosmetic_safe_tags_permit_cosmetic(tag: str) -> None:
    # `unhandled=0`: see test_pure_dialogue_page_may_be_cosmetic's comment.
    row = ManifestRow(
        row_id="x", kind="page", map_id=1, content_hash="0", effects=("text", tag),
        unhandled=0,
    )
    assert row.may_be_cosmetic
    assert row.blocking_tags() == ()


def test_seam_row_is_never_cosmetic() -> None:
    assert not _seam_row().may_be_cosmetic


def test_unrecognized_head_blocks_disposition_and_owes_a_citation() -> None:
    row = _page_row()
    assert not row.is_dispositionable
    assert row.needs_citation


def test_classified_script_typed_conditional_owes_no_citation() -> None:
    # Narrowed 2026-09-12 (REDERIVATION_PLAN.md §14.6, Ruling 2):
    # `script_typed_conditions` counting > 0 used to owe a citation on its
    # own. It no longer does -- only an *unclassified* condition
    # (`condition_unclassified` non-empty) does. A row whose sole
    # script-typed condition landed in a known idiom family
    # (`conditions.classify_condition`) needs no human judgment.
    row = ManifestRow(
        row_id="x", kind="page", map_id=1, content_hash="0",
        effects=("text",), script_typed_conditions=1,
        condition_families=("pb_rock_smash",),
    )
    assert row.is_dispositionable
    assert not row.needs_citation


def test_unclassified_script_typed_conditional_owes_a_citation() -> None:
    row = ManifestRow(
        row_id="x", kind="page", map_id=1, content_hash="0",
        effects=("text",), script_typed_conditions=1,
        condition_unclassified=("SomeNovelUnrecognizedCheck?",),
    )
    assert row.is_dispositionable
    assert row.needs_citation


def test_structurally_determined_row_owes_no_citation() -> None:
    row = ManifestRow(
        row_id="x", kind="page", map_id=1, content_hash="0",
        effects=("giveitem",), script_heads=("pbItemBall",),
    )
    assert not row.needs_citation


@pytest.mark.parametrize(
    "spec, verdict, argument",
    [
        ("cosmetic", "cosmetic", None),
        ("boundary", "boundary", None),
        ("beat:B12", "beat", "B12"),
        ("blocked:rock_smash", "blocked", "rock_smash"),
        ("blocked:rock_smash|strength", "blocked", "rock_smash|strength"),
        ("blocked:tooling:emulator_set_flag", "blocked", "tooling:emulator_set_flag"),
        ("unreachable:dev-only flag sw130", "unreachable", "dev-only flag sw130"),
    ],
)
def test_disposition_parses_and_reformats(spec: str, verdict: str, argument: str | None) -> None:
    parsed = Disposition.parse("row", spec)
    assert (parsed.verdict, parsed.argument) == (verdict, argument)
    assert parsed.spec == spec


def test_disposition_rejects_unknown_verdict() -> None:
    with pytest.raises(DispositionError, match="unknown verdict"):
        Disposition.parse("row", "probably-fine")


def test_blocked_requires_a_capability() -> None:
    with pytest.raises(DispositionError, match="requires an argument"):
        Disposition.parse("row", "blocked")


def test_blocked_rejects_unsorted_capability_set() -> None:
    # Re-pinned for the "+"-is-AND / "|"-is-OR grammar (2026-09-10): the
    # within-set sortedness rule now applies to a "+"-joined AND set, not to
    # "|" (which now separates alternatives and has its own ordering rule,
    # covered below).
    with pytest.raises(DispositionError, match="sorted ascending"):
        Disposition.parse("row", "blocked:strength+rock_smash")


def test_blocked_rejects_duplicate_capability() -> None:
    with pytest.raises(DispositionError, match="sorted ascending"):
        Disposition.parse("row", "blocked:rock_smash+rock_smash")


def test_blocked_rejects_malformed_argument() -> None:
    with pytest.raises(DispositionError, match="not a valid 'blocked:' argument"):
        Disposition.parse("row", "blocked:Rock Smash")


def test_blocked_rejects_empty_argument() -> None:
    with pytest.raises(DispositionError, match="requires an argument"):
        Disposition.parse("row", "blocked:")


def test_blocked_rejects_empty_alternative() -> None:
    with pytest.raises(DispositionError, match="not a valid 'blocked:' argument"):
        Disposition.parse("row", "blocked:rock_smash||surf")


def test_blocked_rejects_empty_token_in_and_set() -> None:
    with pytest.raises(DispositionError, match="not a valid 'blocked:' argument"):
        Disposition.parse("row", "blocked:rock_smash++surf")


def test_blocked_rejects_out_of_order_alternatives() -> None:
    # Both alternatives are singleton AND sets, but "strength" sorts after
    # "rock_smash" -- canonical order is (size, then sorted member tuple).
    with pytest.raises(DispositionError, match="canonical order"):
        Disposition.parse("row", "blocked:strength|rock_smash")


def test_blocked_rejects_out_of_order_alternatives_by_size() -> None:
    # A one-member set must sort before a two-member set of the same
    # "first token", regardless of textual order.
    with pytest.raises(DispositionError, match="canonical order"):
        Disposition.parse("row", "blocked:rock_smash+strength|rock_smash")


def test_blocked_rejects_duplicate_alternative() -> None:
    with pytest.raises(DispositionError, match="more than once"):
        Disposition.parse("row", "blocked:rock_smash|rock_smash")


def test_blocked_rejects_superset_alternative() -> None:
    # If rock_smash alone already opens the row, listing rock_smash+surf as
    # a second alternative is not a second minimal route -- it's a
    # non-minimal restatement of the first.
    with pytest.raises(DispositionError, match="already suffices"):
        Disposition.parse("row", "blocked:rock_smash|rock_smash+surf")


def test_blocked_accepts_or_of_and_sets() -> None:
    disp = Disposition.parse("row", "blocked:rock_smash|strength+surf")
    assert disp.argument == "rock_smash|strength+surf"


def test_assertable_only_applies_to_blocked() -> None:
    with pytest.raises(DispositionError, match="only applies to verdict 'blocked'"):
        Disposition(row_id="row", verdict="beat", argument="B1", assertable=True)


def test_negative_beat_requires_assertable_true() -> None:
    with pytest.raises(DispositionError, match="requires assertable=True"):
        Disposition(row_id="row", verdict="blocked", argument="rock_smash", negative_beat="B6")


def test_negative_beat_must_look_like_a_beat_label() -> None:
    with pytest.raises(DispositionError, match="not a beat name"):
        Disposition(
            row_id="row", verdict="blocked", argument="rock_smash",
            assertable=True, negative_beat="the boulder one",
        )


def test_blocked_row_with_assertable_and_negative_beat_round_trips() -> None:
    disp = Disposition(
        row_id="row", verdict="blocked", argument="rock_smash",
        assertable=True, negative_beat="B6",
    )
    assert disp.spec == "blocked:rock_smash"
    assert disp.assertable is True
    assert disp.negative_beat == "B6"


def test_cosmetic_takes_no_argument() -> None:
    with pytest.raises(DispositionError, match="takes no argument"):
        Disposition.parse("row", "cosmetic:looks nice")


def test_boundary_takes_no_argument() -> None:
    with pytest.raises(DispositionError, match="takes no argument"):
        Disposition.parse("row", "boundary:CH05/B1")


def test_beat_argument_must_look_like_a_beat_label() -> None:
    with pytest.raises(DispositionError, match="not a beat name"):
        Disposition.parse("row", "beat:the one with the boulder")


def test_archetype_exempt_rejects_empty_reason() -> None:
    with pytest.raises(DispositionError, match="non-empty"):
        Disposition(row_id="row", verdict="beat", argument="B14", archetype_exempt="")


def test_archetype_exempt_rejects_whitespace_only_reason() -> None:
    with pytest.raises(DispositionError, match="non-empty"):
        Disposition(row_id="row", verdict="beat", argument="B14", archetype_exempt="   ")


def test_archetype_exempt_round_trips_with_a_reason() -> None:
    disp = Disposition(
        row_id="row", verdict="beat", argument="B14",
        archetype_exempt="12-head gym-7 handler; no parameter makes this a standard trainer",
    )
    assert disp.archetype_exempt == (
        "12-head gym-7 handler; no parameter makes this a standard trainer"
    )


def test_row_ids_are_stable_and_zero_padded() -> None:
    assert page_row_id(35, 3, 1) == "map035/ev003/p1"
    assert seam_row_id(35, "n", 40) == "map035/seam/N/map040"


def test_reachability_consulted_defaults_false() -> None:
    """Conservative default: a row built without saying so is treated as
    "the reachability source was never asked about this map" (CLAUDE.md
    §4.5 -- absence of evidence is not evidence of absence)."""
    row = ManifestRow(row_id="x", kind="page", map_id=1, content_hash="0")
    assert row.reachability_consulted is False


def test_reachability_consulted_round_trips() -> None:
    row = ManifestRow(
        row_id="x", kind="page", map_id=1, content_hash="0",
        reachability_consulted=True,
    )
    assert row_from_dict(row_to_dict(row)) == row


# --- branch rows (REDERIVATION_PLAN.md §16.3 C1) --------------------------


def test_branch_row_id_is_flat_off_the_page_row() -> None:
    page = page_row_id(50, 5, 0)
    assert branch_row_id(page, 2) == "map050/ev005/p0/b2"
    # Flat even for a nested arm -- nesting lives in `parent_row_id`, never
    # in the id string.
    assert branch_row_id(page, 10) == "map050/ev005/p0/b10"


def test_branch_ref_round_trips_through_a_branch_row() -> None:
    branch = BranchRef(
        arm_index=0, arm_kind="then", opener_code=111, opener_index=3,
        choice_index=None, choice_text=None,
        condition_type=12, condition_text="Kernel.pbTrainerBattle(1)",
        explicit=True,
    )
    row = ManifestRow(
        row_id=branch_row_id(page_row_id(50, 5, 0), 0),
        kind="branch",
        map_id=50,
        content_hash=content_hash({"commands": []}),
        event_id=5,
        event_name="Trainer",
        page_idx=0,
        condition=PageCondition(),
        trigger="action",
        branch=branch,
        parent_row_id=page_row_id(50, 5, 0),
    )
    assert row_from_dict(row_to_dict(row)) == row


def test_parse_row_id_round_trips_all_four_kinds() -> None:
    page = page_row_id(35, 3, 1)
    branch = branch_row_id(page, 2)
    seam = seam_row_id(35, "n", 40)
    terrain = terrain_row_id(37, "stairs", 11, 9)

    p = parse_row_id(page)
    assert p.kind == "page"
    assert p.map_id == 35 and p.event_id == 3 and p.page_idx == 1
    assert p.owning_page_row_id == page
    assert p.event_key == (35, 3)

    b = parse_row_id(branch)
    assert b.kind == "branch"
    assert b.map_id == 35 and b.event_id == 3 and b.page_idx == 1 and b.arm_index == 2
    assert b.owning_page_row_id == page
    assert b.event_key == (35, 3)

    s = parse_row_id(seam)
    assert s.kind == "seam"
    assert s.map_id == 35 and s.direction == "N" and s.other_map_id == 40
    assert s.owning_page_row_id is None
    assert s.event_key is None

    t = parse_row_id(terrain)
    assert t.kind == "terrain"
    assert t.map_id == 37 and t.subkind == "stairs" and t.x == 11 and t.y == 9
    assert t.owning_page_row_id is None
    assert t.event_key is None


def test_parse_row_id_rejects_malformed_row_id() -> None:
    with pytest.raises(ValueError):
        parse_row_id("not-a-row-id")


def test_row_id_sort_key_orders_branch_arms_numerically() -> None:
    page = page_row_id(50, 5, 0)
    ids = [branch_row_id(page, n) for n in (10, 2, 0, 1)]
    assert sorted(ids, key=row_id_sort_key) == [
        branch_row_id(page, 0), branch_row_id(page, 1),
        branch_row_id(page, 2), branch_row_id(page, 10),
    ]


def test_row_id_sort_key_orders_mixed_row_kinds_without_error() -> None:
    ids = [
        seam_row_id(50, "e", 51),
        branch_row_id(page_row_id(50, 5, 0), 10),
        page_row_id(50, 5, 0),
        terrain_row_id(50, "stairs", 1, 2),
        branch_row_id(page_row_id(50, 5, 0), 2),
    ]
    ordered = sorted(ids, key=row_id_sort_key)
    # Just needs to not raise, and to keep the two branch rows in numeric
    # order relative to each other.
    assert ordered.index(branch_row_id(page_row_id(50, 5, 0), 2)) < ordered.index(
        branch_row_id(page_row_id(50, 5, 0), 10))
