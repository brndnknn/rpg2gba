"""Tests for `rpg2gba.conversion_agent.queue_evidence` — search-evidence
schema enforcement on `hand`-bucketed unhandled-queue entries.

Design ref: ROM_TEST_DEV.md §E1. Per CLAUDE.md §4.6: round-trip, complete-
record pass, missing-field-named-individually, and load-time fail-loud
coverage.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.conversion_agent.queue_evidence import (
    GrepRecord,
    QueueEntry,
    QueueSchemaViolation,
    SearchEvidence,
    enforce_hand_evidence,
    load_queue_jsonl,
    missing_evidence_fields,
    save_queue_jsonl,
    validate_entry,
)


def _complete_evidence() -> SearchEvidence:
    return SearchEvidence(
        greps=(
            GrepRecord(
                command='grep -n "HealPlayerParty" engine/data/specials.inc',
                result_summary="line 42: def_special HealPlayerParty -- native special exists.",
            ),
        ),
        decomposition_attempted="Checked for a native heal-party special before hand-authoring.",
        decomposition_failed_because="It didn't fail; recorded here as a worked example.",
    )


def _entry(bucket="hand", evidence=None, **raw_overrides) -> QueueEntry:
    raw = {
        "map_id": 1,
        "event_id": 2,
        "page": 1,
        "command_code": 355,
        "description": "example",
    }
    raw.update(raw_overrides)
    return QueueEntry(raw=raw, bucket=bucket, evidence=evidence)


# ---------------------------------------------------------------------------
# Non-hand buckets never require evidence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bucket", ["native", "idiom", "defer"])
def test_non_hand_bucket_never_requires_evidence(bucket):
    entry = _entry(bucket=bucket, evidence=None)
    assert validate_entry(entry) == []
    enforce_hand_evidence(entry)  # must not raise


# ---------------------------------------------------------------------------
# hand entry without evidence raises
# ---------------------------------------------------------------------------


def test_hand_entry_with_no_evidence_raises():
    entry = _entry(bucket="hand", evidence=None)
    with pytest.raises(QueueSchemaViolation) as exc:
        enforce_hand_evidence(entry)
    assert "hand" in str(exc.value)
    assert entry.identity() in str(exc.value)


def test_hand_entry_with_empty_evidence_raises():
    entry = _entry(bucket="hand", evidence=SearchEvidence())
    with pytest.raises(QueueSchemaViolation):
        enforce_hand_evidence(entry)


# ---------------------------------------------------------------------------
# A complete evidence record passes
# ---------------------------------------------------------------------------


def test_hand_entry_with_complete_evidence_passes():
    entry = _entry(bucket="hand", evidence=_complete_evidence())
    assert validate_entry(entry) == []
    enforce_hand_evidence(entry)  # must not raise


# ---------------------------------------------------------------------------
# Each individual missing sub-field is reported by name
# ---------------------------------------------------------------------------


def test_missing_greps_reported_by_name():
    evidence = SearchEvidence(
        greps=(),
        decomposition_attempted="tried something",
        decomposition_failed_because="because reasons",
    )
    missing = missing_evidence_fields(evidence)
    assert missing == ["evidence.greps"]


def test_missing_grep_subfields_reported_by_name():
    evidence = SearchEvidence(
        greps=(GrepRecord(command="", result_summary=""),),
        decomposition_attempted="tried something",
        decomposition_failed_because="because reasons",
    )
    missing = missing_evidence_fields(evidence)
    assert "evidence.greps[0].command" in missing
    assert "evidence.greps[0].result_summary" in missing


def test_missing_decomposition_attempted_reported_by_name():
    evidence = SearchEvidence(
        greps=(GrepRecord(command="grep foo", result_summary="no hits"),),
        decomposition_attempted="",
        decomposition_failed_because="because reasons",
    )
    missing = missing_evidence_fields(evidence)
    assert missing == ["evidence.decomposition_attempted"]


def test_missing_decomposition_failed_because_reported_by_name():
    evidence = SearchEvidence(
        greps=(GrepRecord(command="grep foo", result_summary="no hits"),),
        decomposition_attempted="tried something",
        decomposition_failed_because="",
    )
    missing = missing_evidence_fields(evidence)
    assert missing == ["evidence.decomposition_failed_because"]


def test_missing_evidence_object_entirely_reported_by_name():
    assert missing_evidence_fields(None) == ["evidence"]


def test_enforce_error_message_names_every_missing_field():
    evidence = SearchEvidence(greps=(), decomposition_attempted="", decomposition_failed_because="")
    entry = _entry(bucket="hand", evidence=evidence)
    with pytest.raises(QueueSchemaViolation) as exc:
        enforce_hand_evidence(entry)
    msg = str(exc.value)
    assert "evidence.greps" in msg
    assert "evidence.decomposition_attempted" in msg
    assert "evidence.decomposition_failed_because" in msg


# ---------------------------------------------------------------------------
# legacy_unaudited: reported as a violation, but doesn't raise
# ---------------------------------------------------------------------------


def test_legacy_unaudited_entry_logs_but_does_not_raise(caplog):
    evidence = SearchEvidence(legacy_unaudited=True)
    entry = _entry(bucket="hand", evidence=evidence)
    assert validate_entry(entry) != []  # still reported as incomplete
    with caplog.at_level("WARNING"):
        enforce_hand_evidence(entry)  # must not raise
    assert "legacy_unaudited" in caplog.text


# ---------------------------------------------------------------------------
# Round-trip serialize/deserialize
# ---------------------------------------------------------------------------


def test_round_trip_hand_entry_with_evidence():
    original = _entry(bucket="hand", evidence=_complete_evidence(), event_name="Trainer_6")
    data = original.to_dict()
    restored = QueueEntry.from_dict(data)
    assert restored.raw == original.raw
    assert restored.bucket == original.bucket
    assert restored.evidence == original.evidence


def test_round_trip_non_hand_entry_without_evidence():
    original = _entry(bucket="native", evidence=None)
    restored = QueueEntry.from_dict(original.to_dict())
    assert restored.bucket == "native"
    assert restored.evidence is None


def test_from_dict_rejects_invalid_bucket():
    with pytest.raises(QueueSchemaViolation):
        QueueEntry.from_dict({"raw": {}, "bucket": "maybe"})


# ---------------------------------------------------------------------------
# jsonl load fails loud on a violating entry
# ---------------------------------------------------------------------------


def test_load_queue_jsonl_fails_loud_on_bad_hand_entry(tmp_path: Path):
    bad = _entry(bucket="hand", evidence=None)
    path = tmp_path / "queue.jsonl"
    path.write_text(
        __import__("json").dumps(bad.to_dict()) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(QueueSchemaViolation) as exc:
        load_queue_jsonl(path)
    assert str(path) in str(exc.value)


def test_load_queue_jsonl_accepts_legacy_violation(tmp_path: Path, caplog):
    legacy = _entry(bucket="hand", evidence=SearchEvidence(legacy_unaudited=True))
    path = tmp_path / "queue.jsonl"
    path.write_text(
        __import__("json").dumps(legacy.to_dict()) + "\n",
        encoding="utf-8",
    )
    with caplog.at_level("WARNING"):
        entries = load_queue_jsonl(path)
    assert len(entries) == 1
    assert "legacy_unaudited" in caplog.text


def test_load_queue_jsonl_round_trips_clean_entries(tmp_path: Path):
    entries = [
        _entry(bucket="native", evidence=None, event_id=1),
        _entry(bucket="hand", evidence=_complete_evidence(), event_id=2),
        _entry(bucket="defer", evidence=None, event_id=3),
    ]
    path = tmp_path / "queue.jsonl"
    save_queue_jsonl(path, entries)
    loaded = load_queue_jsonl(path)
    assert [e.bucket for e in loaded] == ["native", "hand", "defer"]
    assert loaded[1].evidence == entries[1].evidence


def test_save_queue_jsonl_refuses_to_write_bad_hand_entry(tmp_path: Path):
    bad = _entry(bucket="hand", evidence=None)
    path = tmp_path / "queue.jsonl"
    with pytest.raises(QueueSchemaViolation):
        save_queue_jsonl(path, [bad])
    assert not path.exists()


def test_malformed_json_line_fails_loud(tmp_path: Path):
    path = tmp_path / "queue.jsonl"
    path.write_text("{not json\n", encoding="utf-8")
    with pytest.raises(QueueSchemaViolation):
        load_queue_jsonl(path)


# ---------------------------------------------------------------------------
# The committed slice-1 backfill artifact itself loads clean (with the one
# known, explicitly-flagged legacy gap).
# ---------------------------------------------------------------------------


def test_committed_hand_bucket_queue_loads(caplog):
    path = Path(__file__).resolve().parents[1] / "reference" / "findings" / "hand_bucket_queue.jsonl"
    with caplog.at_level("WARNING"):
        entries = load_queue_jsonl(path)
    assert len(entries) >= 1
    buckets = {e.bucket for e in entries}
    assert buckets <= {"native", "idiom", "hand", "defer"}
    # The M49 EV20 legacy entry is expected to log, not raise.
    assert "legacy_unaudited" in caplog.text
