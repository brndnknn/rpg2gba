"""Tests for the residue ledger validation (REDERIVATION_PLAN.md §16.3 C7, Task 2).

`validate_residue(frozen, ledger, manifest_ids) -> list[str]` in
`rpg2gba.playtest.hand_freeze`. Every test but the first builds a tiny
synthetic freeze, so these pin the RULES, not your rulings -- only
`test_residue_ledger_complete` reads the real committed files.

STATUS: implemented, skipped. DELETE the `pytestmark` line when you start
Task 2 (and delete `test_minimal_residue_rule_missing_ledger` from
`tests/test_hand_freeze.py` at the same time -- `test_missing_ledger` below
replaces it under the three-argument signature).
"""
from __future__ import annotations

import copy
import json

import pytest

from rpg2gba.playtest import hand_freeze

pytestmark = pytest.mark.skip(reason="C7 Task 2 not started -- remove this line to start")


def _beat(name: str, order: int, rows: list[str]) -> dict:
    return {"name": name, "order": order, "group": None,
            "map_constant": "MAP_MOKI_TOWN", "rows": rows}


# CH01 has two rowless beats (B1, N4) and one that claims a row (B2).
FROZEN = {
    "schema": 1,
    "authored": "2026-09-18",
    "rule": "test",
    "sources": {"CH01": {"module": "x", "blob_sha": "0" * 40}},
    "chapters": {
        "CH01": [
            _beat("B1", 0, []),
            _beat("B2", 1, ["map032/ev003/p0"]),
            _beat("N4", 2, []),
        ],
    },
}
MANIFEST_IDS = {"CH01": {"map032/ev003/p0", "map032/ev014/p0", "map032/ev015/p0"}}
LEDGER = {
    "schema": 1,
    "entries": {
        "CH01:B1": {"ruling": "open", "question": "Is spawn a floor kind?",
                    "note": "New save spawns on the house map."},
        "CH01:N4": {"ruling": "blocked_obstacle",
                    "rows": ["map032/ev014/p0", "map032/ev015/p0"],
                    "note": "Rocks stay put without the capability."},
    },
}


def _validate(ledger: dict | None, frozen: dict = FROZEN) -> list[str]:
    return hand_freeze.validate_residue(frozen, ledger, MANIFEST_IDS)


def _with_entry(key: str, entry: dict) -> dict:
    ledger = copy.deepcopy(LEDGER)
    ledger["entries"][key] = entry
    return ledger


# --- the real files -------------------------------------------------------

def test_residue_ledger_complete():
    with hand_freeze.FROZEN_PATH.open(encoding="utf-8") as f:
        frozen = json.load(f)
    with hand_freeze.RESIDUE_PATH.open(encoding="utf-8") as f:
        ledger = json.load(f)
    manifest_ids = {ch: hand_freeze.manifest_row_ids(ch) for ch in hand_freeze.CHAPTERS}
    assert hand_freeze.validate_residue(frozen, ledger, manifest_ids) == []


# --- the synthetic baseline ----------------------------------------------

def test_synthetic_baseline_is_clean():
    # If this fails, every other test here is meaningless -- fix it first.
    assert _validate(LEDGER) == []


def test_missing_ledger():
    problems = _validate(None)
    assert len(problems) == 1


# --- R1: one entry per rowless beat, no extras ---------------------------

def test_residue_missing_entry():
    ledger = copy.deepcopy(LEDGER)
    del ledger["entries"]["CH01:N4"]
    problems = _validate(ledger)
    assert len(problems) == 1
    assert "CH01:N4" in problems[0]


def test_residue_stale_entry():
    # B2 claims a row, so it is not residue: an entry for it is stale.
    ledger = _with_entry("CH01:B2", {"ruling": "bgm_debt", "note": "n"})
    problems = _validate(ledger)
    assert len(problems) == 1
    assert "CH01:B2" in problems[0]


def test_residue_unknown_beat():
    ledger = _with_entry("CH01:B99", {"ruling": "bgm_debt", "note": "n"})
    problems = _validate(ledger)
    assert len(problems) == 1
    assert "CH01:B99" in problems[0]


def test_residue_bad_ruling():
    ledger = _with_entry("CH01:B1", {"ruling": "vibes", "note": "n"})
    problems = _validate(ledger)
    assert problems and any("vibes" in p for p in problems)


def test_residue_note_required():
    ledger = _with_entry("CH01:B1", {"ruling": "bgm_debt"})
    problems = _validate(ledger)
    assert problems and any("CH01:B1" in p for p in problems)


# --- R1: required extra fields, one ruling family at a time ---------------

def test_residue_open_needs_question():
    ledger = _with_entry("CH01:B1", {"ruling": "open", "note": "n"})
    problems = _validate(ledger)
    assert problems and any("question" in p for p in problems)


@pytest.mark.parametrize("ruling",
                         ["arrival_floor", "blocked_obstacle", "state_model",
                          "covered_elsewhere"])
def test_residue_rows_rulings_need_rows(ruling):
    ledger = _with_entry("CH01:B1", {"ruling": ruling, "note": "n"})
    problems = _validate(ledger)
    assert problems and any("rows" in p for p in problems)


@pytest.mark.parametrize("ruling", ["arrival_floor", "covered_elsewhere"])
def test_residue_empty_rows_is_missing_rows(ruling):
    ledger = _with_entry("CH01:B1", {"ruling": ruling, "rows": [], "note": "n"})
    assert _validate(ledger)


@pytest.mark.parametrize("ruling", ["build_check", "retired"])
def test_residue_cites_rulings_need_cites(ruling):
    ledger = _with_entry("CH01:B1", {"ruling": ruling, "note": "n"})
    problems = _validate(ledger)
    assert problems and any("cites" in p for p in problems)


@pytest.mark.parametrize("ruling", ["bgm_debt", "not_residue"])
def test_residue_bare_rulings_need_nothing_extra(ruling):
    ledger = _with_entry("CH01:B1", {"ruling": ruling, "note": "n"})
    assert _validate(ledger) == []


# --- R1: row ids must exist in the manifest -------------------------------

def test_residue_unknown_row_id():
    ledger = _with_entry("CH01:B1", {"ruling": "covered_elsewhere",
                                     "rows": ["map032/ev003/p0", "map999/ev001/p0"],
                                     "note": "n"})
    problems = _validate(ledger)
    assert len(problems) == 1
    assert "map999/ev001/p0" in problems[0]


# --- collect, then report -------------------------------------------------

def test_residue_reports_every_problem():
    # Three independent problems -> at least three strings, not one.
    ledger = copy.deepcopy(LEDGER)
    del ledger["entries"]["CH01:N4"]                                       # missing
    ledger["entries"]["CH01:B1"] = {"ruling": "vibes", "note": "n"}        # bad ruling
    ledger["entries"]["CH01:B2"] = {"ruling": "bgm_debt", "note": "n"}     # stale
    assert len(_validate(ledger)) >= 3


def test_residue_unknown_schema():
    ledger = copy.deepcopy(LEDGER)
    ledger["schema"] = 2
    assert _validate(ledger)
