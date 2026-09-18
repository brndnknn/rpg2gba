"""Tests for `rpg2gba.playtest.hand_freeze` (REDERIVATION_PLAN.md §16.3 C7).

STATUS: stubs. The module-level skip keeps the suite green while the module
is unimplemented -- DELETE the `pytestmark` line when you start Task 1, then
work each test from skip to red to green.
"""
from __future__ import annotations

import pytest

from rpg2gba.playtest import hand_freeze

pytestmark = pytest.mark.skip(reason="C7 Task 1 stub -- remove this line to start")

EXPECTED_OWN_COUNTS = {"CH01": 22, "CH02": 18, "CH03": 35, "CH04": 13, "CH05": 5}


def test_own_beat_counts():
    # For each chapter, len(hand_freeze.own_beats(ch)) == EXPECTED_OWN_COUNTS[ch].
    raise NotImplementedError


def test_no_inherited_names():
    # No beat in build_freeze()["chapters"] has ":" in its name.
    raise NotImplementedError


def test_build_is_deterministic():
    # dump(build_freeze()) twice -> identical strings.
    raise NotImplementedError


def test_unknown_row_fails_loud(monkeypatch):
    # Wrap the real manifest_row_ids so it drops one row a beat really claims
    # (pick one from own_beats). build_freeze() must raise FreezeError, and
    # the message must name that row.  Hint: pytest.raises(..., match=...)
    raise NotImplementedError


def test_check_detects_stale_blob():
    # Take a rebuilt freeze, deep-copy it, change one sources[..]["blob_sha"],
    # and assert diff_freeze(tampered, rebuilt) contains a "stale" problem.
    raise NotImplementedError


def test_loader_roundtrip(tmp_path):
    # Write dump(build_freeze()) to tmp_path, load it with
    # load_frozen_hand_beats(path) -> 91 FrozenBeat objects, CH01's first.
    raise NotImplementedError
