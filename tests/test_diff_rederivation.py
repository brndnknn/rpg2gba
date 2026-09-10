"""Tests for `scripts/diff_rederivation.py`.

Scaffolding for REDERIVATION_PLAN.md's P8 step; expires alongside the script
it tests at P10 (module docstring there). All fixtures here are synthetic --
none of these tests depend on the real `reference/` data being in any
particular state, since two other agents are editing chapter modules and
capability_sites.py concurrently while this task runs.

Exercises the pure comparison functions (`_diff_rows`, `_diff_dispositions_values`,
`_diff_beats`) directly rather than `diff_chapter`, which shells out to the real
generator/build directory -- that path is covered instead by running the CLI
by hand against CH01-CH04 (REDERIVATION_PLAN.md P8), not by this suite.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = str(REPO_ROOT / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import diff_rederivation as dr  # noqa: E402


def _row(row_id: str, **overrides) -> dict:
    base = {
        "row_id": row_id,
        "kind": "page",
        "map_id": 1,
        "content_hash": "aaaa1111aaaa1111",
        "effects": [],
        "script_heads": [],
        "unrecognized_heads": [],
        "other_codes": [],
        "requires": [],
        "unhandled": 0,
        "script_typed_conditions": 0,
        "event_id": 1,
        "event_name": "Dummy",
        "page_idx": 0,
        "condition": None,
        "trigger": None,
        "seam": None,
        "terrain": None,
        "reachability_consulted": True,
    }
    base.update(overrides)
    return base


# --- _diff_rows --------------------------------------------------------------


def test_added_row_reported():
    frozen = {"map001/ev001/p0": _row("map001/ev001/p0")}
    fresh = {
        "map001/ev001/p0": _row("map001/ev001/p0"),
        "map001/ev002/p0": _row("map001/ev002/p0"),
    }
    added, removed, field_diffs, hash_diffs, _ = dr._diff_rows(frozen, fresh)
    assert added == ["map001/ev002/p0"]
    assert removed == []
    assert field_diffs == []
    assert hash_diffs == []


def test_removed_row_reported():
    frozen = {
        "map001/ev001/p0": _row("map001/ev001/p0"),
        "map001/ev002/p0": _row("map001/ev002/p0"),
    }
    fresh = {"map001/ev001/p0": _row("map001/ev001/p0")}
    added, removed, field_diffs, hash_diffs, _ = dr._diff_rows(frozen, fresh)
    assert added == []
    assert removed == ["map001/ev002/p0"]
    assert field_diffs == []


def test_changed_field_reported_and_not_auto_benign():
    frozen = {"map001/ev001/p0": _row("map001/ev001/p0", requires=[])}
    fresh = {"map001/ev001/p0": _row("map001/ev001/p0", requires=["rock_smash"])}
    added, removed, field_diffs, hash_diffs, _ = dr._diff_rows(frozen, fresh)
    assert added == removed == []
    assert len(field_diffs) == 1
    d = field_diffs[0]
    assert d.row_id == "map001/ev001/p0"
    assert d.field == "requires"
    assert d.before == []
    assert d.after == ["rock_smash"]
    assert d.benign is False


def test_content_hash_change_reported_separately_from_field_diffs():
    frozen = {"map001/ev001/p0": _row("map001/ev001/p0", content_hash="old_hash_0001")}
    fresh = {"map001/ev001/p0": _row("map001/ev001/p0", content_hash="new_hash_0002")}
    added, removed, field_diffs, hash_diffs, _ = dr._diff_rows(frozen, fresh)
    assert field_diffs == []
    assert len(hash_diffs) == 1
    assert hash_diffs[0].field == "content_hash"
    assert hash_diffs[0].before == "old_hash_0001"
    assert hash_diffs[0].after == "new_hash_0002"


def test_benign_unhandled_none_only_for_seam_rows():
    # Seam row: 0 -> None is the known-benign CH01 finding.
    frozen_seam = {"map001/seam/E/map002": _row(
        "map001/seam/E/map002", kind="seam", unhandled=0)}
    fresh_seam = {"map001/seam/E/map002": _row(
        "map001/seam/E/map002", kind="seam", unhandled=None)}
    _, _, field_diffs, _, _ = dr._diff_rows(frozen_seam, fresh_seam)
    assert len(field_diffs) == 1
    assert field_diffs[0].benign is True
    assert field_diffs[0].benign_reason is not None

    # Same 0 -> None transition on a page row must NOT be auto-marked benign
    # -- the mark is narrowly scoped to seam rows only (module docstring).
    frozen_page = {"map001/ev001/p0": _row("map001/ev001/p0", kind="page", unhandled=0)}
    fresh_page = {"map001/ev001/p0": _row("map001/ev001/p0", kind="page", unhandled=None)}
    _, _, field_diffs_page, _, _ = dr._diff_rows(frozen_page, fresh_page)
    assert len(field_diffs_page) == 1
    assert field_diffs_page[0].benign is False


def test_frozen_row_missing_newer_schema_fields_does_not_diff():
    """A frozen row that predates `reachability_consulted`/`terrain`
    (CH01-CH03's real shape) must not report those as diffs when the fresh
    row carries them -- this is the raw-JSON path working, not
    `schema.row_from_dict`, which would have refused to load the row at
    all."""
    old_row = _row("map001/ev001/p0")
    del old_row["reachability_consulted"]
    del old_row["terrain"]
    frozen = {"map001/ev001/p0": old_row}
    fresh = {"map001/ev001/p0": _row(
        "map001/ev001/p0", reachability_consulted=True, terrain=None)}
    added, removed, field_diffs, hash_diffs, _ = dr._diff_rows(frozen, fresh)
    assert added == removed == field_diffs == hash_diffs == []


def test_frozen_row_missing_schema_fields_still_diffs_other_fields():
    """The schema-addition skip must not swallow a REAL diff on the same row."""
    old_row = _row("map001/ev001/p0", requires=[])
    del old_row["reachability_consulted"]
    del old_row["terrain"]
    frozen = {"map001/ev001/p0": old_row}
    fresh = {"map001/ev001/p0": _row(
        "map001/ev001/p0", requires=["surf"], reachability_consulted=True, terrain=None)}
    added, removed, field_diffs, hash_diffs, _ = dr._diff_rows(frozen, fresh)
    assert added == removed == []
    assert len(field_diffs) == 1
    assert field_diffs[0].field == "requires"


# --- _diff_dispositions_values ------------------------------------------------


def test_dispositions_both_null_reports_nothing_to_diff():
    note, added, removed, changed = dr._diff_dispositions_values("CHxx", None, None)
    assert note is not None
    assert "nothing to diff" in note
    assert added == removed == changed == []


def test_dispositions_frozen_null_fresh_present_is_new_content_not_added_rows():
    fresh = {"map001/ev001/p0": "cosmetic"}
    note, added, removed, changed = dr._diff_dispositions_values("CHxx", None, fresh)
    assert note is not None
    assert "new authored content" in note
    # Must NOT be reported as row-by-row "added" -- there is no prior answer
    # to diff against, so calling it "added" would misrepresent it as drift.
    assert added == removed == changed == []


def test_dispositions_fresh_null_frozen_present_flags_disappearance():
    frozen = {"map001/ev001/p0": "cosmetic"}
    note, added, removed, changed = dr._diff_dispositions_values("CHxx", frozen, None)
    assert note is not None
    assert removed == ["map001/ev001/p0"]
    assert added == changed == []


def test_dispositions_changed_value_reported():
    frozen = {"map001/ev001/p0": "cosmetic"}
    fresh = {"map001/ev001/p0": "beat:B3"}
    note, added, removed, changed = dr._diff_dispositions_values("CHxx", frozen, fresh)
    assert note is None
    assert added == removed == []
    assert len(changed) == 1
    assert changed[0].before == "cosmetic"
    assert changed[0].after == "beat:B3"


def test_dispositions_added_and_removed_rows():
    frozen = {"map001/ev001/p0": "cosmetic", "map001/ev002/p0": "cosmetic"}
    fresh = {"map001/ev001/p0": "cosmetic", "map001/ev003/p0": "blocked:rock_smash"}
    note, added, removed, changed = dr._diff_dispositions_values("CHxx", frozen, fresh)
    assert note is None
    assert added == ["map001/ev003/p0"]
    assert removed == ["map001/ev002/p0"]
    assert changed == []


# --- _diff_beats ---------------------------------------------------------------


def _beat(name: str, own: bool, **overrides) -> dict:
    base = {"name": name, "own": own, "map_constant": "MAP_TEST", "group": None, "rows": []}
    base.update(overrides)
    return base


def test_beats_only_own_beats_compared():
    frozen = [_beat("CH01:B1", own=False), _beat("B5", own=True)]
    fresh = [_beat("CH01:B1", own=False, map_constant="MAP_CHANGED"), _beat("B5", own=True)]
    added, removed, changed = dr._diff_beats(frozen, fresh)
    # The inherited beat's field changed, but it is not "own" to this
    # chapter, so it must not surface here at all.
    assert added == removed == changed == []


def test_beats_added_removed_and_changed():
    frozen = [_beat("B1", own=True), _beat("B2", own=True, group="G1")]
    fresh = [
        _beat("B1", own=True, rows=["map001/ev001/p0"]),
        _beat("B3", own=True),
    ]
    added, removed, changed = dr._diff_beats(frozen, fresh)
    assert added == ["B3"]
    assert removed == ["B2"]
    assert len(changed) == 1
    assert changed[0].row_id == "B1"
    assert changed[0].field == "rows"
    assert changed[0].after == ["map001/ev001/p0"]


# --- ChapterDiff aggregate / has_anything_to_adjudicate -----------------------


def test_has_anything_to_adjudicate_false_on_clean_diff():
    diff = dr.ChapterDiff(chapter="CHxx", frozen_row_count=1, fresh_row_count=1)
    assert diff.has_anything_to_adjudicate is False


def test_has_anything_to_adjudicate_true_on_added_row():
    diff = dr.ChapterDiff(chapter="CHxx", rows_added=["map001/ev001/p0"])
    assert diff.has_anything_to_adjudicate is True


def test_has_anything_to_adjudicate_ignores_benign_field_diffs():
    benign = dr.FieldDiff(
        row_id="map001/seam/E/map002", field="unhandled", before=0, after=None,
        benign=True, benign_reason="known benign",
    )
    diff = dr.ChapterDiff(chapter="CHxx", field_diffs=[benign])
    assert diff.unresolved_field_diffs == []
    assert diff.has_anything_to_adjudicate is False


def test_has_anything_to_adjudicate_true_on_unresolved_field_diff():
    not_benign = dr.FieldDiff(
        row_id="map001/ev001/p0", field="requires", before=[], after=["surf"],
    )
    diff = dr.ChapterDiff(chapter="CHxx", field_diffs=[not_benign])
    assert diff.has_anything_to_adjudicate is True


def test_diff_to_dict_round_trips_shape():
    diff = dr.ChapterDiff(
        chapter="CHxx", frozen_row_count=2, fresh_row_count=3,
        rows_added=["map001/ev002/p0"],
    )
    payload = dr.diff_to_dict(diff)
    assert payload["chapter"] == "CHxx"
    assert payload["frozen_row_count"] == 2
    assert payload["fresh_row_count"] == 3
    assert payload["rows_added"] == ["map001/ev002/p0"]
    assert payload["has_anything_to_adjudicate"] is True
    assert payload["dispositions"]["note"] is None
    assert payload["beats"]["added"] == []
