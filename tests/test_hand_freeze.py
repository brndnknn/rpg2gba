"""Tests for `rpg2gba.playtest.hand_freeze` (REDERIVATION_PLAN.md §16.3 C7, Task 1).

The six tests the assignment names come first; the ones under "Build-order
tests" were added so each stub function gets its own red→green signal as
you implement it, in the order `01_freeze_capture.md` suggests.

Every test that calls `build_freeze()` needs the five `chNN.py` hand
modules to be committed (R2) -- an uncommitted edit to one of them makes
`build_freeze` refuse, which is correct behaviour, not a test bug.

Task 2's residue tests live in `tests/test_hand_freeze_residue.py`.
"""
from __future__ import annotations

import copy
import json

import pytest

from rpg2gba.playtest import hand_freeze
from rpg2gba.playtest.hand_freeze import FreezeError, FrozenBeat

# Registered own beats, measured 2026-09-19 via load_chapter. NOT the 22/18/35/13/5 = 91
# decorator count the plan quotes: templates and helpers register beats too.
EXPECTED_OWN_COUNTS = {"CH01": 22, "CH02": 19, "CH03": 35, "CH04": 14, "CH05": 21}


@pytest.fixture(scope="module")
def freeze() -> dict:
    """One real build, shared by the read-only tests (load_chapter is not free)."""
    return hand_freeze.build_freeze()


def _first_claimed_row() -> tuple[str, str, str]:
    """(chapter, beat name, row id) of the first row any own beat claims."""
    for chapter in hand_freeze.CHAPTERS:
        for beat in hand_freeze.own_beats(chapter):
            if beat["rows"]:
                return chapter, beat["name"], beat["rows"][0]
    raise AssertionError("no own beat claims any row -- own_beats is wrong")


# --- the six named tests -------------------------------------------------

@pytest.mark.parametrize("chapter", sorted(EXPECTED_OWN_COUNTS))
def test_own_beat_counts(chapter):
    assert len(hand_freeze.own_beats(chapter)) == EXPECTED_OWN_COUNTS[chapter]


def test_no_inherited_names(freeze):
    names = [b["name"] for beats in freeze["chapters"].values() for b in beats]
    assert names, "freeze has no beats at all"
    assert [n for n in names if ":" in n] == []


def test_build_is_deterministic(freeze):
    assert hand_freeze.dump(hand_freeze.build_freeze()) == hand_freeze.dump(freeze)


def test_unknown_row_fails_loud(monkeypatch):
    chapter, beat_name, row = _first_claimed_row()
    real = hand_freeze.manifest_row_ids

    def dropping(ch: str) -> set[str]:
        ids = real(ch)
        return ids - {row} if ch == chapter else ids

    monkeypatch.setattr(hand_freeze, "manifest_row_ids", dropping)
    with pytest.raises(FreezeError) as excinfo:
        hand_freeze.build_freeze()
    message = str(excinfo.value)
    assert row in message
    assert beat_name in message
    assert chapter in message


def test_check_detects_stale_blob(freeze):
    tampered = copy.deepcopy(freeze)
    tampered["sources"]["CH02"]["blob_sha"] = "0" * 40
    problems = hand_freeze.diff_freeze(tampered, freeze)
    assert any("stale" in p and "CH02" in p for p in problems), problems


def test_loader_roundtrip(tmp_path, freeze):
    path = tmp_path / "frozen.json"
    path.write_text(hand_freeze.dump(freeze), encoding="utf-8")
    beats = hand_freeze.load_frozen_hand_beats(path)
    assert len(beats) == sum(EXPECTED_OWN_COUNTS.values()) == 111
    assert all(isinstance(b, FrozenBeat) for b in beats)
    assert beats[0].chapter == "CH01" and beats[0].order == 0
    assert beats[-1].chapter == "CH05"
    assert all(isinstance(b.rows, tuple) for b in beats)


# --- build-order tests (one per stub, in the suggested order) ------------

# Step 1 -- git helpers

def test_head_and_worktree_sha_agree_on_committed_file():
    # README.md is committed and (normally) unmodified; both views agree.
    head = hand_freeze.head_blob_sha("README.md")
    assert len(head) == 40
    assert head == hand_freeze.worktree_blob_sha("README.md")


def test_head_blob_sha_fails_loud_on_unknown_path():
    with pytest.raises(RuntimeError):
        hand_freeze.head_blob_sha("no/such/file.py")


# Step 2 -- manifest ids and own beats

def test_manifest_row_ids_reads_real_manifest():
    ids = hand_freeze.manifest_row_ids("CH01")
    assert isinstance(ids, set)
    assert "map032/ev001/p0" in ids


def test_own_beat_dict_shape():
    beats = hand_freeze.own_beats("CH05")
    assert [b["order"] for b in beats] == list(range(len(beats)))
    for b in beats:
        assert list(b) == ["name", "order", "group", "map_constant", "rows"]
        assert isinstance(b["rows"], list)


# Step 3 -- build_freeze

def test_freeze_top_level_shape(freeze):
    assert list(freeze) == ["schema", "authored", "rule", "sources", "chapters"]
    assert freeze["schema"] == hand_freeze.SCHEMA
    assert freeze["authored"] == hand_freeze.AUTHORED
    assert list(freeze["sources"]) == list(hand_freeze.CHAPTERS)
    assert list(freeze["chapters"]) == list(hand_freeze.CHAPTERS)
    src = freeze["sources"]["CH01"]
    assert src == {
        "module": hand_freeze.module_path("CH01"),
        "blob_sha": hand_freeze.head_blob_sha(hand_freeze.module_path("CH01")),
    }


def test_freeze_is_json_serialisable(freeze):
    # dump() must not need a custom encoder (no tuples-vs-lists surprises on reload).
    assert json.loads(hand_freeze.dump(freeze)) == freeze


def test_uncommitted_module_refuses(monkeypatch):
    real = hand_freeze.worktree_blob_sha

    def dirty(path: str) -> str:
        return "f" * 40 if path == hand_freeze.module_path("CH04") else real(path)

    monkeypatch.setattr(hand_freeze, "worktree_blob_sha", dirty)
    with pytest.raises(FreezeError, match="CH04"):
        hand_freeze.build_freeze()


def test_all_problems_reported_at_once(monkeypatch):
    # Collect-then-raise: two different problems, ONE FreezeError naming both.
    real = hand_freeze.worktree_blob_sha

    def dirty(path: str) -> str:
        return "f" * 40 if path in {hand_freeze.module_path("CH02"),
                                    hand_freeze.module_path("CH04")} else real(path)

    monkeypatch.setattr(hand_freeze, "worktree_blob_sha", dirty)
    with pytest.raises(FreezeError) as excinfo:
        hand_freeze.build_freeze()
    assert "CH02" in str(excinfo.value) and "CH04" in str(excinfo.value)


# Step 4 -- diff_freeze and the minimal validate_residue

def test_diff_freeze_clean(freeze):
    assert hand_freeze.diff_freeze(freeze, copy.deepcopy(freeze)) == []


def test_diff_freeze_detects_beat_change(freeze):
    tampered = copy.deepcopy(freeze)
    tampered["chapters"]["CH03"][0]["rows"].append("map999/ev001/p0")
    problems = hand_freeze.diff_freeze(tampered, freeze)
    assert problems and any("CH03" in p for p in problems), problems
    # Blob shas are untouched, so nothing may be called stale.
    assert not any("stale" in p for p in problems)


# Step 5 -- loader

def test_loader_rejects_unknown_schema(tmp_path, freeze):
    doc = copy.deepcopy(freeze)
    doc["schema"] = 99
    path = tmp_path / "frozen.json"
    path.write_text(hand_freeze.dump(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="99"):
        hand_freeze.load_frozen_hand_beats(path)
