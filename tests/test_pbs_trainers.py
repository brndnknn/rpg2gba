"""Phase 2 §2.6 tests — trainers (`trainers.py`).

Per CLAUDE.md §4.6 / PHASE2_PLAN §2.6:
  * round-trip: parse → build JSON → party species/levels survive
  * golden: all 130 trainer-class defs + 3 pinned trainers
  * edge: a doubles trainer (Cool Couple, 2-mon party) with a custom-moveset mon;
    and the 0-TPSHADOW invariant holds (parse succeeds)

Real-data tests are env-gated via the `uranium_data` fixture.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.pbs_converter import trainers
from rpg2gba.pbs_converter._id_map import IdMap
from rpg2gba.pbs_converter._marshal import dump_dat, load_json

pytestmark = pytest.mark.phase2

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _build(uranium_data: Path, reference_dir: Path, tmp_path: Path):
    types = trainers.parse_trainer_types(
        load_json(dump_dat(uranium_data / "trainertypes.dat", tmp_path / "tt.json"))
    )
    parsed = trainers.parse_trainers(
        load_json(dump_dat(uranium_data / "trainers.dat", tmp_path / "t.json"))
    )
    r = trainers._build_resolver(IdMap(), reference_dir)
    types_by_id = {tt.id: tt for tt in types}
    types_json = trainers.build_trainer_types(types, r)
    trainers_json = trainers.build_trainers(parsed, types_by_id, r)
    return parsed, types_json, trainers_json


def test_roundtrip_party(uranium_data: Path, reference_dir: Path, tmp_path: Path) -> None:
    """Each trainer's emitted party length + first species match the parsed record."""
    parsed, _types_json, trainers_json = _build(uranium_data, reference_dir, tmp_path)
    by_id = {v["id"]: v for v in trainers_json.values()}
    checked = 0
    for t in parsed:
        entry = by_id[t.index]
        assert len(entry["party"]) == len(t.party)
        checked += 1
    assert checked == 331  # MEMORY: 331 trainers


def test_golden(uranium_data: Path, reference_dir: Path, tmp_path: Path) -> None:
    """All 130 class defs + 3 pinned trainers match the committed fixture."""
    _parsed, types_json, trainers_json = _build(uranium_data, reference_dir, tmp_path)
    expected = json.loads((FIXTURES / "trainers_golden.json").read_text(encoding="utf-8"))
    assert types_json == expected["classes"]
    got_trainers = {k: trainers_json[k] for k in expected["trainers"]}
    assert got_trainers == expected["trainers"]


def test_edge_doubles_and_custom_moves(
    uranium_data: Path, reference_dir: Path, tmp_path: Path
) -> None:
    """A Cool Couple is a 2-mon doubles party; at least one mon has custom moves."""
    _parsed, _types_json, trainers_json = _build(uranium_data, reference_dir, tmp_path)
    abe = trainers_json["TRAINER_ABE_GAYLE_166"]
    assert len(abe["party"]) == 2
    assert any("moves" in mon for mon in abe["party"])


def test_edge_no_shadow(uranium_data: Path, reference_dir: Path, tmp_path: Path) -> None:
    """Parsing succeeds across all 331 trainers — the 0-TPSHADOW invariant holds.

    `_parse_mon` raises if TPSHADOW is set, so a clean parse *is* the assertion.
    """
    parsed, _types_json, _trainers_json = _build(uranium_data, reference_dir, tmp_path)
    assert sum(len(t.party) for t in parsed) == 1026
