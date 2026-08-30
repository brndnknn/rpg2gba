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
    Disposition,
    DispositionError,
    ManifestRow,
    PageCondition,
    SeamRef,
    content_hash,
    page_row_id,
    row_from_dict,
    row_to_dict,
    seam_row_id,
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


@pytest.mark.parametrize("row", [_page_row(), _seam_row()])
def test_row_round_trips_exactly(row: ManifestRow) -> None:
    assert row_from_dict(row_to_dict(row)) == row


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
    row = ManifestRow(
        row_id="x", kind="page", map_id=1, content_hash="0", effects=("text", "se"),
    )
    assert row.may_be_cosmetic


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
    row = ManifestRow(
        row_id="x", kind="page", map_id=1, content_hash="0", effects=("text", tag),
    )
    assert row.may_be_cosmetic
    assert row.blocking_tags() == ()


def test_seam_row_is_never_cosmetic() -> None:
    assert not _seam_row().may_be_cosmetic


def test_unrecognized_head_blocks_disposition_and_owes_a_citation() -> None:
    row = _page_row()
    assert not row.is_dispositionable
    assert row.needs_citation


def test_script_typed_conditional_alone_owes_a_citation() -> None:
    row = ManifestRow(
        row_id="x", kind="page", map_id=1, content_hash="0",
        effects=("text",), script_typed_conditions=1,
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
    with pytest.raises(DispositionError, match="sorted ascending"):
        Disposition.parse("row", "blocked:strength|rock_smash")


def test_blocked_rejects_duplicate_capability() -> None:
    with pytest.raises(DispositionError, match="sorted ascending"):
        Disposition.parse("row", "blocked:rock_smash|rock_smash")


def test_blocked_rejects_malformed_argument() -> None:
    with pytest.raises(DispositionError, match="not a valid 'blocked:' argument"):
        Disposition.parse("row", "blocked:Rock Smash")


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


def test_beat_argument_must_look_like_a_beat_label() -> None:
    with pytest.raises(DispositionError, match="not a beat name"):
        Disposition.parse("row", "beat:the one with the boulder")


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
