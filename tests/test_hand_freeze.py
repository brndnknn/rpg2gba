"""Tests for `rpg2gba.playtest.hand_freeze` (REDERIVATION_PLAN.md §16.3 C7).

The hand suites the freeze was captured from were deleted after the C9/P11
gate (2026-10-03), so these test the committed artifact and its loader, not
the capture. Residue-ledger tests live in `tests/test_hand_freeze_residue.py`.
"""
from __future__ import annotations

import copy
import json

import pytest
from click.testing import CliRunner

from rpg2gba.playtest import hand_freeze
from rpg2gba.playtest.hand_freeze import FrozenBeat

# Own beats per chapter as captured 2026-09-19 (C7); the freeze is fixed now.
EXPECTED_OWN_COUNTS = {"CH01": 22, "CH02": 19, "CH03": 35, "CH04": 14, "CH05": 21}


@pytest.fixture(scope="module")
def freeze() -> dict:
    return json.loads(hand_freeze.FROZEN_PATH.read_text(encoding="utf-8"))


def test_freeze_top_level_shape(freeze):
    assert list(freeze) == ["schema", "authored", "rule", "sources", "chapters"]
    assert freeze["schema"] == hand_freeze.SCHEMA
    assert freeze["authored"] == hand_freeze.AUTHORED
    assert list(freeze["chapters"]) == list(hand_freeze.CHAPTERS)


@pytest.mark.parametrize("chapter", sorted(EXPECTED_OWN_COUNTS))
def test_own_beat_counts(freeze, chapter):
    assert len(freeze["chapters"][chapter]) == EXPECTED_OWN_COUNTS[chapter]


def test_no_inherited_names(freeze):
    names = [b["name"] for beats in freeze["chapters"].values() for b in beats]
    assert names, "freeze has no beats at all"
    assert [n for n in names if ":" in n] == []


def test_every_frozen_row_is_in_a_manifest(freeze):
    known: set[str] = set()
    for chapter in hand_freeze.CHAPTERS:
        known |= hand_freeze.manifest_row_ids(chapter)
        for beat in freeze["chapters"][chapter]:
            assert set(beat["rows"]) <= known, (chapter, beat["name"])


def test_loader_reads_committed_freeze():
    beats = hand_freeze.load_frozen_hand_beats()
    assert len(beats) == sum(EXPECTED_OWN_COUNTS.values()) == 111
    assert all(isinstance(b, FrozenBeat) for b in beats)
    assert beats[0].chapter == "CH01" and beats[0].order == 0
    assert beats[-1].chapter == "CH05"
    assert all(isinstance(b.rows, tuple) for b in beats)


def test_loader_rejects_unknown_schema(tmp_path, freeze):
    doc = copy.deepcopy(freeze)
    doc["schema"] = 99
    path = tmp_path / "frozen.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="99"):
        hand_freeze.load_frozen_hand_beats(path)


def test_manifest_row_ids_reads_real_manifest():
    ids = hand_freeze.manifest_row_ids("CH01")
    assert isinstance(ids, set)
    assert "map032/ev001/p0" in ids


def test_check_cli_passes_on_committed_freeze():
    result = CliRunner().invoke(hand_freeze.cli, ["check"])
    assert result.exit_code == 0, result.output
    assert "hand-beat freeze OK" in result.output
