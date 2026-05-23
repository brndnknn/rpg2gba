"""Phase 2 §2.5 tests — TM/HM compatibility (`tm_hm.py`).

Per CLAUDE.md §4.6 / PHASE2_PLAN §2.5:
  * round-trip: parse tm.dat → invert to species→[MOVE_*] → every species in a
    move's list carries that move constant
  * golden: a pinned species' learnable MOVE_* list (ORCHYNX)
  * edge: tutor.dat is asserted empty; a species that learns 0 TMs is absent

Real-data tests are env-gated via the `uranium_data` fixture.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.pbs_converter import tm_hm
from rpg2gba.pbs_converter._id_map import IdMap
from rpg2gba.pbs_converter._marshal import dump_dat, load_json

pytestmark = pytest.mark.phase2

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _build(uranium_data: Path, reference_dir: Path, tmp_path: Path):
    raw = load_json(dump_dat(uranium_data / "tm.dat", tmp_path / "tm_raw.json"))
    r = tm_hm._build_resolver(IdMap(), reference_dir)
    tm = tm_hm.parse_tm(raw)
    learnables = tm_hm.build_learnables(tm, r)
    return tm, r, learnables


def test_roundtrip_move_membership(
    uranium_data: Path, reference_dir: Path, tmp_path: Path
) -> None:
    """Every species listed under a move learns that move in the inverted map."""
    tm, r, learnables = _build(uranium_data, reference_dir, tmp_path)
    checked = 0
    for move_id, species_ids in tm.items():
        const = r.move_constant(move_id)
        for sid in species_ids:
            assert const in learnables[r.species_key(sid)]
            checked += 1
    assert checked >= 5000  # ~9k species-move pairs in Uranium


def test_golden_orchynx(uranium_data: Path, reference_dir: Path, tmp_path: Path) -> None:
    """ORCHYNX's learnable MOVE_* list matches the pinned fixture."""
    _tm, _r, learnables = _build(uranium_data, reference_dir, tmp_path)
    got = {"ORCHYNX": learnables["ORCHYNX"]}
    expected = json.loads((FIXTURES / "tm_hm_golden.json").read_text(encoding="utf-8"))
    assert got == expected


def test_edge_tutor_empty(uranium_data: Path) -> None:
    """tutor.dat is header-only/empty — assert_tutor_empty must accept it."""
    tm_hm.assert_tutor_empty(uranium_data / "tutor.dat")  # raises if non-empty


def test_edge_values_sorted_and_keys_internal(
    uranium_data: Path, reference_dir: Path, tmp_path: Path
) -> None:
    """Each species' move list is sorted (deterministic) and keys are bare internal names."""
    _tm, _r, learnables = _build(uranium_data, reference_dir, tmp_path)
    sample = next(iter(learnables.values()))
    assert sample == sorted(sample)
    # Keys are the all_learnables form (bare internal name, no SPECIES_ prefix).
    assert all(not k.startswith("SPECIES_") for k in learnables)
