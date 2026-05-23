"""Phase 2 §2.7 tests — wild encounters (`encounters.py`).

Per CLAUDE.md §4.6 / PHASE2_PLAN §2.7:
  * round-trip: parse → build → every non-null Essentials slot list is preserved
    (conservation), across a meaningful number of maps
  * golden: 3 pinned maps (land+water+all-rod fishing; a map with uranium_extra;
    a cave-only map)
  * edge: fishing rod sub-groups present; a Headbutt/BugContest table lands in
    uranium_extra, never in a top-level fork field

Real-data tests are env-gated via the `uranium_data` fixture.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.pbs_converter import encounters
from rpg2gba.pbs_converter._id_map import IdMap
from rpg2gba.pbs_converter._marshal import dump_dat, load_json

pytestmark = pytest.mark.phase2

FIXTURES = Path(__file__).resolve().parent / "fixtures"
_FORK_FIELDS = ("land_mons", "water_mons", "rock_smash_mons")


def _build(uranium_data: Path, reference_dir: Path, tmp_path: Path):
    raw = load_json(dump_dat(uranium_data / "encounters.dat", tmp_path / "enc.json"))
    r = encounters._build_resolver(IdMap(), reference_dir)
    tables = encounters.parse_and_build(raw, r)
    return raw, tables


def test_roundtrip_conservation(
    uranium_data: Path, reference_dir: Path, tmp_path: Path
) -> None:
    """Every non-null Essentials slot list survives into exactly one output list."""
    raw, tables = _build(uranium_data, reference_dir, tmp_path)
    raw_lists = sum(sum(1 for s in slots if s) for _dens, slots in raw.values())

    def emitted_lists(m: dict) -> int:
        n = sum(1 for k in _FORK_FIELDS if k in m)
        n += len(m.get("fishing_mons", {}))
        n += len(m.get("uranium_extra", {}))
        return n

    assert raw_lists == sum(emitted_lists(m) for m in tables.values())
    assert len(tables) >= 50


def test_golden(uranium_data: Path, reference_dir: Path, tmp_path: Path) -> None:
    """3 pinned maps match the committed fixture."""
    _raw, tables = _build(uranium_data, reference_dir, tmp_path)
    expected = json.loads((FIXTURES / "encounters_golden.json").read_text(encoding="utf-8"))
    assert {k: tables[k] for k in expected} == expected


def test_edge_fishing_rod_groups(
    uranium_data: Path, reference_dir: Path, tmp_path: Path
) -> None:
    """Map 8 splits fishing into old/good/super rod sub-groups with resolved species."""
    _raw, tables = _build(uranium_data, reference_dir, tmp_path)
    fishing = tables["8"]["fishing_mons"]
    assert {"old_rod", "good_rod", "super_rod"} == set(fishing)
    assert fishing["old_rod"][0]["species"].startswith("SPECIES_")


def test_edge_extra_not_in_fork_fields(
    uranium_data: Path, reference_dir: Path, tmp_path: Path
) -> None:
    """uranium_extra labels never collide with the fork's top-level fields."""
    _raw, tables = _build(uranium_data, reference_dir, tmp_path)
    extra_maps = {k: v for k, v in tables.items() if "uranium_extra" in v}
    assert extra_maps  # at least one map carries preserved Uranium-only tables
    for m in extra_maps.values():
        assert not (set(m["uranium_extra"]) & set(_FORK_FIELDS))
