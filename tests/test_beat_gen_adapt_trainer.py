"""`beat_gen.adapt._trainer_const_for`: one battle's trainer constant from the
floor's (name, class). Rematch tiers resolve to the tier-1 party (CH11)."""
from __future__ import annotations

import pytest

from rpg2gba.beat_gen import adapt


def _tiers(*parties: tuple[str, int]) -> dict[str, dict]:
    return {const: {"name": "Sr. Goldkorn", "trainer_class": "TRAINER_CLASS_GENTLEMAN",
                    "party_id": party} for const, party in parties}


def test_rematch_tiers_resolve_to_party_zero(monkeypatch):
    monkeypatch.setattr(adapt, "_trainers_json", lambda: _tiers(
        ("TRAINER_SR_GOLDKORN_268", 2), ("TRAINER_SR_GOLDKORN_293", 1),
        ("TRAINER_SR_GOLDKORN_36", 0)))
    assert adapt._trainer_const_for("Sr. Goldkorn", "TRAINER_CLASS_GENTLEMAN",
                                    row_id="map076/ev071/p0") == "TRAINER_SR_GOLDKORN_36"


def test_two_party_zero_entries_stay_ambiguous(monkeypatch):
    monkeypatch.setattr(adapt, "_trainers_json", lambda: _tiers(
        ("TRAINER_SR_GOLDKORN_1", 0), ("TRAINER_SR_GOLDKORN_2", 0)))
    with pytest.raises(ValueError, match="ambiguous"):
        adapt._trainer_const_for("Sr. Goldkorn", "TRAINER_CLASS_GENTLEMAN", row_id="x")
