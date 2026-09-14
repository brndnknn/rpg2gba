"""Tests for the machine-derived sidecar (`CHnn.derived.json`).

The ruling: a THIRD file, `row_id -> derived_hash`, sits beside the
generated manifest and the hand-authored dispositions file. `checker.py`
must never trust a sidecar entry's mere presence -- it recomputes
eligibility itself (`ManifestRow.may_be_cosmetic`) and flags any entry that
sits on a row it independently judges ineligible for machine derivation.

Fixture idiom matches `test_chapter_manifest_checker.py`: build `ManifestRow`
/`Disposition` objects directly, not through the generator.
"""
from __future__ import annotations

import json

from rpg2gba.chapter_manifest.checker import (
    RULE_DERIVED_BEAT_CLAIMED,
    RULE_DERIVED_HASH_INELIGIBLE,
    RULE_ROUTE_MODEL_UNENFORCED,
    RULE_UNDISPOSITIONED,
    check_chapter,
)
from rpg2gba.chapter_manifest.dispositions import derived_path, load_derived
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


# --- eligible row: sidecar entry passes ---------------------------------


def test_derived_hash_on_eligible_row_passes():
    # unhandled=0, kind="page", no state-writing effects, no unrecognized
    # heads -- ManifestRow.may_be_cosmetic is True for this row.
    row = _row(effects=(), content_hash="h1", unhandled=0)
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    findings = check_chapter(
        [row], {row.row_id: disp}, derived={row.row_id: "h1"})
    # No per-row finding for this row_id -- the corpus-wide count warning
    # (row_id="chapter") is expected and covered separately below.
    assert all(
        not (f.rule == RULE_DERIVED_HASH_INELIGIBLE and f.row_id == row.row_id)
        for f in findings
    )


# --- ineligible row: sidecar entry is a new error ------------------------


def test_derived_hash_on_ineligible_row_is_error():
    # Default row has unhandled=None ("never staged") -- may_be_cosmetic is
    # False, so a derived_hash sitting on it is illegitimate regardless of
    # what the disposition itself says.
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    findings = check_chapter(
        [row], {row.row_id: disp}, derived={row.row_id: "h1"})
    matches = [f for f in findings if f.rule == RULE_DERIVED_HASH_INELIGIBLE
               and f.row_id == row.row_id]
    assert len(matches) == 1
    assert matches[0].severity == "error"


def test_derived_hash_on_ineligible_row_via_state_writing_effect():
    # A second, independently-real ineligibility path: state-writing effects
    # veto `may_be_cosmetic` even when the row IS staged (unhandled=0).
    row = _row(effects=("giveitem",), content_hash="h1", unhandled=0)
    disp = _disp(row.row_id, "beat:B1", affirmed_hash="h1")
    findings = check_chapter(
        [row], {row.row_id: disp}, derived={row.row_id: "h1"})
    matches = [f for f in findings if f.rule == RULE_DERIVED_HASH_INELIGIBLE
               and f.row_id == row.row_id]
    assert len(matches) == 1
    assert matches[0].severity == "error"


# --- corpus-wide count ----------------------------------------------------


def test_derived_count_warning_present_when_nonzero():
    row = _row(effects=(), content_hash="h1", unhandled=0)
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    findings = check_chapter(
        [row], {row.row_id: disp}, derived={row.row_id: "h1"})
    chapter_findings = [
        f for f in findings
        if f.rule == RULE_DERIVED_HASH_INELIGIBLE and f.row_id == "chapter"
    ]
    assert len(chapter_findings) == 1
    assert chapter_findings[0].severity == "warning"
    assert "1 row" in chapter_findings[0].message


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


# --- missing sidecar checks cleanly ---------------------------------------


def test_missing_sidecar_checks_cleanly():
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    findings_no_derived = _relevant(check_chapter([row], {row.row_id: disp}))
    findings_none_derived = _relevant(
        check_chapter([row], {row.row_id: disp}, derived=None))
    assert findings_no_derived == findings_none_derived
    assert all(f.rule != RULE_DERIVED_HASH_INELIGIBLE for f in findings_no_derived)


def test_load_derived_missing_file_is_caller_responsibility(tmp_path):
    # dispositions.load_derived itself is strict (fails loud on malformed
    # content); a missing FILE is handled by the caller (__main__.py checks
    # .exists() first, same pattern as the dispositions file), not by this
    # loader defaulting silently. Confirm the path convention at least.
    path = derived_path("CH99", root=tmp_path)
    assert path == tmp_path / "CH99.derived.json"
    assert not path.exists()


def test_load_derived_round_trips(tmp_path):
    path = derived_path("CH04", root=tmp_path)
    payload = {"map001/ev001/p0": "h1", "map002/ev002/p0": "h2"}
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_derived(path) == payload


# --- three-way join: manifest row + disposition + derived entry ----------


def test_three_way_join_all_present_on_one_row():
    row = _row(effects=(), content_hash="h1", unhandled=0)
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    findings = _relevant(check_chapter(
        [row], {row.row_id: disp}, derived={row.row_id: "h1"}))
    # A human affirmed the row (affirmed_hash) AND the machine derived it
    # (derived_hash) -- both claims about the same row_id are legal
    # together; the stronger (human) claim does not need the weaker
    # (machine) one absent, and vice versa. The only finding left is the
    # corpus-wide "N rows carry a derived_hash" tally (row_id="chapter");
    # nothing is wrong with THIS row on any axis (undispositioned,
    # stale/unaffirmed, illegal_cosmetic, derived_hash_ineligible).
    assert all(f.row_id != row.row_id for f in findings)
    assert [f for f in findings if f.rule == RULE_DERIVED_HASH_INELIGIBLE
            and f.row_id == "chapter"]


# --- derived default: a sidecar entry IS the disposition ------------------


class _Beats:
    """Minimal `BeatModel`: only `claiming_beats` is exercised here."""

    def __init__(self, claims: dict[str, tuple[str, ...]]) -> None:
        self._claims = claims

    def is_registered(self, beat_id: str) -> bool:
        return True

    def deferral_reason(self, beat_id: str) -> str | None:
        return None

    def claiming_beats(self, row_id: str) -> tuple[str, ...]:
        return self._claims.get(row_id, ())


def _per_row(findings, row_id):
    return [f for f in findings if f.row_id == row_id]


def test_row_omitted_from_dispositions_is_derived_cosmetic():
    row = _row(content_hash="h1", unhandled=0)
    findings = check_chapter([row], {}, derived={row.row_id: "h1"})
    assert _per_row(findings, row.row_id) == []


def test_no_dispositions_and_no_sidecar_is_still_undispositioned():
    row = _row(content_hash="h1", unhandled=0)
    findings = check_chapter([row], {}, derived=None)
    assert [f.rule for f in _per_row(findings, row.row_id)] == [RULE_UNDISPOSITIONED]


def test_stale_derived_hash_does_not_disposition_the_row():
    row = _row(content_hash="h2", unhandled=0)
    findings = check_chapter([row], {}, derived={row.row_id: "h1"})
    matches = _per_row(findings, row.row_id)
    assert [f.rule for f in matches] == [RULE_UNDISPOSITIONED]
    assert "regenerate the sidecar" in matches[0].message


def test_requires_row_is_not_derived():
    # blocked outranks cosmetic: may_be_cosmetic is True, may_be_derived is not.
    row = _row(content_hash="h1", unhandled=0, requires=("rock_smash",))
    assert row.may_be_cosmetic and not row.may_be_derived
    findings = check_chapter([row], {}, derived={row.row_id: "h1"})
    rules = {f.rule for f in _per_row(findings, row.row_id)}
    assert rules == {RULE_UNDISPOSITIONED, RULE_DERIVED_HASH_INELIGIBLE}


def test_citation_owing_row_is_not_derived():
    row = _row(content_hash="h1", unhandled=0,
               condition_unclassified=("a || b",), script_typed_conditions=1)
    assert row.may_be_cosmetic and not row.may_be_derived


def test_beat_claimed_row_left_to_derived_default_is_error():
    row = _row(content_hash="h1", unhandled=0)
    findings = check_chapter(
        [row], {}, derived={row.row_id: "h1"},
        beat_model=_Beats({row.row_id: ("B3_grant",)}))
    matches = [f for f in _per_row(findings, row.row_id)
               if f.rule == RULE_DERIVED_BEAT_CLAIMED]
    assert len(matches) == 1
    assert matches[0].severity == "error"
    assert "B3_grant" in matches[0].message


def test_hand_beat_entry_overrides_derived_default():
    row = _row(content_hash="h1", unhandled=0)
    disp = _disp(row.row_id, "beat:B3", affirmed_hash="h1")
    findings = check_chapter(
        [row], {row.row_id: disp}, derived={row.row_id: "h1"},
        beat_model=_Beats({row.row_id: ("B3",)}))
    assert all(f.rule != RULE_DERIVED_BEAT_CLAIMED for f in findings)
