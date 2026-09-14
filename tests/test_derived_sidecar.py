"""Tests for the machine-derived sidecar (`CHnn.derived.json`, format v2).

The ruling (2026-09-14): the sidecar's entries are FOUR verdicts, not a
bare hash. `cosmetic`/`beat:`/`boundary` are CLERICAL -- accepted on
`derived_hash` alone, no human affirmation. `blocked:` is only ever a
PROPOSAL -- it never dispositions a row until a human copies it into the
dispositions file with an `affirmed_hash`. `checker.py` must never trust a
sidecar entry's mere presence -- it recomputes `derivation.derive_entry`
itself and flags any entry it disagrees with.

Fixture idiom matches `test_chapter_manifest_checker.py`: build `ManifestRow`
/`Disposition` objects directly, not through the generator.
"""
from __future__ import annotations

import json

import pytest

from rpg2gba.chapter_manifest.checker import (
    RULE_DERIVED_HASH_INELIGIBLE,
    RULE_DERIVED_UNAFFIRMED,
    RULE_DERIVED_VERDICT_MISMATCH,
    RULE_ROUTE_MODEL_UNENFORCED,
    RULE_UNDISPOSITIONED,
    check_chapter,
)
from rpg2gba.chapter_manifest.derivation import DerivedEntry
from rpg2gba.chapter_manifest.dispositions import (
    DispositionFileError,
    derived_path,
    load_derived,
)
from rpg2gba.chapter_manifest.schema import Disposition, ManifestRow


def _row(row_id: str = "map001/ev001/p0", **overrides) -> ManifestRow:
    defaults = dict(
        row_id=row_id,
        kind="page",
        map_id=1,
        content_hash="deadbeef00000000",
        effects=(),
        reachability_consulted=True,
    )
    defaults.update(overrides)
    return ManifestRow(**defaults)


def _disp(row_id: str, spec: str, **rest) -> Disposition:
    return Disposition.parse(row_id, spec, **rest)


def _relevant(findings):
    """Drop the route-model-unenforced warning every no-`route=` call carries
    -- same filter `test_chapter_manifest_checker.py` uses throughout."""
    return [f for f in findings if f.rule != RULE_ROUTE_MODEL_UNENFORCED]


def _per_row(findings, row_id):
    return [f for f in findings if f.row_id == row_id]


class _Beats:
    """Minimal `BeatModel`: only `claiming_beats` is exercised via the
    checker's `derive_entry` recompute."""

    def __init__(self, claims: dict[str, tuple[str, ...]] | None = None) -> None:
        self._claims = claims or {}

    def is_registered(self, beat_id: str) -> bool:
        return True

    def deferral_reason(self, beat_id: str) -> str | None:
        return None

    def claiming_beats(self, row_id: str) -> tuple[str, ...]:
        return self._claims.get(row_id, ())


# --- loader: format v2 -----------------------------------------------------


def test_load_derived_round_trips(tmp_path):
    path = derived_path("CH04", root=tmp_path)
    payload = {
        "map001/ev001/p0": {"disposition": "cosmetic", "derived_hash": "h1"},
        "map002/ev002/p0": {
            "disposition": "blocked:rock_smash", "derived_hash": "h2", "proposed": True,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = load_derived(path)
    assert result == {
        "map001/ev001/p0": DerivedEntry(disposition="cosmetic", derived_hash="h1"),
        "map002/ev002/p0": DerivedEntry(
            disposition="blocked:rock_smash", derived_hash="h2", proposed=True),
    }


def test_load_derived_missing_file_is_caller_responsibility(tmp_path):
    # dispositions.load_derived itself is strict (fails loud on malformed
    # content); a missing FILE is handled by the caller (__main__.py checks
    # .exists() first, same pattern as the dispositions file), not by this
    # loader defaulting silently. Confirm the path convention at least.
    path = derived_path("CH99", root=tmp_path)
    assert path == tmp_path / "CH99.derived.json"
    assert not path.exists()


def test_load_derived_rejects_old_bare_string_format(tmp_path):
    path = derived_path("CH01", root=tmp_path)
    path.write_text(json.dumps({"map001/ev001/p0": "h1"}), encoding="utf-8")
    with pytest.raises(DispositionFileError, match="regenerate"):
        load_derived(path)


def test_load_derived_rejects_missing_disposition_field(tmp_path):
    path = derived_path("CH01", root=tmp_path)
    path.write_text(json.dumps({"map001/ev001/p0": {"derived_hash": "h1"}}), encoding="utf-8")
    with pytest.raises(DispositionFileError, match="disposition"):
        load_derived(path)


def test_load_derived_rejects_missing_derived_hash_field(tmp_path):
    path = derived_path("CH01", root=tmp_path)
    path.write_text(json.dumps({"map001/ev001/p0": {"disposition": "cosmetic"}}), encoding="utf-8")
    with pytest.raises(DispositionFileError, match="derived_hash"):
        load_derived(path)


def test_load_derived_rejects_bad_spec(tmp_path):
    path = derived_path("CH01", root=tmp_path)
    path.write_text(
        json.dumps({"map001/ev001/p0": {"disposition": "not_a_verdict", "derived_hash": "h1"}}),
        encoding="utf-8")
    with pytest.raises(DispositionFileError):
        load_derived(path)


def test_load_derived_rejects_unknown_key(tmp_path):
    path = derived_path("CH01", root=tmp_path)
    path.write_text(
        json.dumps({"map001/ev001/p0": {
            "disposition": "cosmetic", "derived_hash": "h1", "extra": True}}),
        encoding="utf-8")
    with pytest.raises(DispositionFileError, match="unknown"):
        load_derived(path)


def test_load_derived_rejects_non_bool_proposed(tmp_path):
    path = derived_path("CH01", root=tmp_path)
    path.write_text(
        json.dumps({"map001/ev001/p0": {
            "disposition": "blocked:rock_smash", "derived_hash": "h1", "proposed": "yes"}}),
        encoding="utf-8")
    with pytest.raises(DispositionFileError, match="proposed"):
        load_derived(path)


# --- checker: clerical entry accepted on hash+verdict match ---------------


def test_clerical_cosmetic_entry_is_accepted():
    row = _row(content_hash="h1", unhandled=0)
    entry = DerivedEntry(disposition="cosmetic", derived_hash="h1")
    findings = check_chapter([row], {}, derived={row.row_id: entry})
    assert _per_row(findings, row.row_id) == []


def test_row_omitted_from_dispositions_is_derived_cosmetic():
    row = _row(content_hash="h1", unhandled=0)
    entry = DerivedEntry(disposition="cosmetic", derived_hash="h1")
    findings = check_chapter([row], {}, derived={row.row_id: entry})
    assert _per_row(findings, row.row_id) == []


def test_no_dispositions_and_no_sidecar_is_still_undispositioned():
    row = _row(content_hash="h1", unhandled=0)
    findings = check_chapter([row], {}, derived=None)
    assert [f.rule for f in _per_row(findings, row.row_id)] == [RULE_UNDISPOSITIONED]


def test_stale_derived_hash_does_not_disposition_the_row():
    row = _row(content_hash="h2", unhandled=0)
    entry = DerivedEntry(disposition="cosmetic", derived_hash="h1")
    findings = check_chapter([row], {}, derived={row.row_id: entry})
    matches = _per_row(findings, row.row_id)
    assert [f.rule for f in matches] == [RULE_UNDISPOSITIONED]
    assert "regenerate the sidecar" in matches[0].message


# --- checker: recompute disagrees with the sidecar -------------------------


def test_sidecar_cosmetic_but_recompute_derives_nothing_is_mismatch():
    # Row is NOT eligible (never staged, unhandled=None) -- derive_entry
    # recomputes None, disagreeing with the sidecar's claimed 'cosmetic'.
    row = _row(content_hash="h1")
    entry = DerivedEntry(disposition="cosmetic", derived_hash="h1")
    findings = check_chapter([row], {}, derived={row.row_id: entry})
    matches = [f for f in _per_row(findings, row.row_id)
               if f.rule == RULE_DERIVED_VERDICT_MISMATCH]
    assert len(matches) == 1
    assert matches[0].severity == "error"
    assert "regenerate the sidecar" in matches[0].message


def test_sidecar_cosmetic_but_row_is_actually_beat_claimed_is_mismatch():
    row = _row(content_hash="h1", unhandled=0)
    entry = DerivedEntry(disposition="cosmetic", derived_hash="h1")
    findings = check_chapter(
        [row], {}, derived={row.row_id: entry},
        beat_model=_Beats({row.row_id: ("B3_grant",)}))
    matches = [f for f in _per_row(findings, row.row_id)
               if f.rule == RULE_DERIVED_VERDICT_MISMATCH]
    assert len(matches) == 1
    assert "beat:B3" in matches[0].message


def test_sidecar_proposed_flag_mismatch_is_mismatch():
    # requires=('rock_smash',) derives a PROPOSED blocked: entry -- a
    # sidecar claiming the same spec but NOT proposed disagrees.
    row = _row(content_hash="h1", unhandled=0, requires=("rock_smash",))
    entry = DerivedEntry(disposition="blocked:rock_smash", derived_hash="h1", proposed=False)
    findings = check_chapter([row], {}, derived={row.row_id: entry})
    matches = [f for f in _per_row(findings, row.row_id)
               if f.rule == RULE_DERIVED_VERDICT_MISMATCH]
    assert len(matches) == 1


# --- checker: blocked: proposal is never auto-accepted ----------------------


def test_blocked_proposal_matching_recompute_is_unaffirmed_not_dispositioned():
    row = _row(content_hash="h1", unhandled=0, requires=("rock_smash",))
    entry = DerivedEntry(disposition="blocked:rock_smash", derived_hash="h1", proposed=True)
    findings = check_chapter([row], {}, derived={row.row_id: entry})
    matches = _per_row(findings, row.row_id)
    assert [f.rule for f in matches] == [RULE_DERIVED_UNAFFIRMED]
    assert matches[0].severity == "error"
    # Paste-ready JSON snippet naming the row and an affirmed_hash.
    assert row.row_id in matches[0].message
    assert '"disposition": "blocked:rock_smash"' in matches[0].message
    assert f'"affirmed_hash": "{row.content_hash}"' in matches[0].message
    # Not dispositioned -- confirmed via the effective-dispositions-driven
    # archetype-conformance pass: nothing here decides that on its own, but
    # the per-row loop reports exactly RULE_DERIVED_UNAFFIRMED and nothing
    # that would only fire for a dispositioned row (e.g. RULE_ILLEGAL_COSMETIC).


def test_hand_affirmed_blocked_overrides_a_matching_proposal():
    row = _row(content_hash="h1", unhandled=0, requires=("rock_smash",))
    entry = DerivedEntry(disposition="blocked:rock_smash", derived_hash="h1", proposed=True)
    disp = _disp(row.row_id, "blocked:rock_smash", affirmed_hash="h1")
    findings = check_chapter(
        [row], {row.row_id: disp}, derived={row.row_id: entry})
    assert all(f.rule != RULE_DERIVED_UNAFFIRMED for f in _per_row(findings, row.row_id))


# --- checker: hand disposition overrides sidecar regardless -----------------


def test_hand_beat_entry_overrides_derived_default():
    row = _row(content_hash="h1", unhandled=0)
    disp = _disp(row.row_id, "beat:B3", affirmed_hash="h1")
    entry = DerivedEntry(disposition="cosmetic", derived_hash="h1")
    findings = check_chapter(
        [row], {row.row_id: disp}, derived={row.row_id: entry},
        beat_model=_Beats({row.row_id: ("B3",)}))
    assert all(f.rule not in (RULE_DERIVED_VERDICT_MISMATCH, RULE_DERIVED_UNAFFIRMED)
               for f in _per_row(findings, row.row_id))


# --- corpus-wide tally -------------------------------------------------------


def test_derived_count_tally_breaks_down_by_verdict_and_proposals():
    cosmetic_row = _row("map001/ev001/p0", content_hash="h1", unhandled=0)
    blocked_row = _row(
        "map001/ev002/p0", content_hash="h2", unhandled=0, requires=("rock_smash",))
    findings = check_chapter(
        [cosmetic_row, blocked_row], {},
        derived={
            cosmetic_row.row_id: DerivedEntry(disposition="cosmetic", derived_hash="h1"),
            blocked_row.row_id: DerivedEntry(
                disposition="blocked:rock_smash", derived_hash="h2", proposed=True),
        })
    chapter_findings = [
        f for f in findings
        if f.rule == RULE_DERIVED_HASH_INELIGIBLE and f.row_id == "chapter"
    ]
    assert len(chapter_findings) == 1
    message = chapter_findings[0].message
    assert "cosmetic=1" in message
    assert "blocked=1" in message
    assert "1 proposal" in message


def test_derived_count_warning_absent_when_zero():
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp}, derived=None)
    assert all(
        not (f.rule == RULE_DERIVED_HASH_INELIGIBLE and f.row_id == "chapter")
        for f in findings
    )
    findings_empty = check_chapter([row], {row.row_id: disp}, derived={})
    assert all(
        not (f.rule == RULE_DERIVED_HASH_INELIGIBLE and f.row_id == "chapter")
        for f in findings_empty
    )


def test_missing_sidecar_checks_cleanly():
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    findings_no_derived = _relevant(check_chapter([row], {row.row_id: disp}))
    findings_none_derived = _relevant(
        check_chapter([row], {row.row_id: disp}, derived=None))
    assert findings_no_derived == findings_none_derived
    assert all(f.rule != RULE_DERIVED_HASH_INELIGIBLE for f in findings_no_derived)
