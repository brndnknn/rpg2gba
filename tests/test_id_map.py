"""Unit tests for `pbs_converter._id_map`."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.pbs_converter._id_map import (
    CATEGORIES,
    NEEDS_ENGINE_CATEGORIES,
    IdMap,
    IdMapConflictError,
    IdMapUnknownCategoryError,
)


def test_load_missing_file_returns_empty(tmp_path: Path) -> None:
    m = IdMap.load(tmp_path / "absent.json")
    for cat in CATEGORIES:
        assert m.get(cat, "anything") is None


def test_add_and_get(tmp_path: Path) -> None:
    m = IdMap()
    m.add("species", "EEVEE", "SPECIES_EEVEE")
    assert m.get("species", "EEVEE") == "SPECIES_EEVEE"
    assert m.get("species", "MISSING") is None


def test_add_is_idempotent(tmp_path: Path) -> None:
    m = IdMap()
    m.add("moves", "TACKLE", "MOVE_TACKLE")
    m.add("moves", "TACKLE", "MOVE_TACKLE")  # same pair — should not raise
    assert m.get("moves", "TACKLE") == "MOVE_TACKLE"


def test_add_conflict_raises_fail_loud() -> None:
    m = IdMap()
    m.add("moves", "GAMMARAY", "MOVE_GAMMARAY")
    with pytest.raises(IdMapConflictError) as exc:
        m.add("moves", "GAMMARAY", "MOVE_GAMMA_RAY")
    assert "GAMMARAY" in str(exc.value)
    assert "MOVE_GAMMARAY" in str(exc.value)
    assert "MOVE_GAMMA_RAY" in str(exc.value)


def test_unknown_category_raises() -> None:
    m = IdMap()
    with pytest.raises(IdMapUnknownCategoryError):
        m.get("not_a_category", "X")
    with pytest.raises(IdMapUnknownCategoryError):
        m.add("not_a_category", "X", "X_CONST")


def test_needs_engine_inline_flag() -> None:
    m = IdMap()
    m.add("abilities", "CHERNOBYL", "ABILITY_CHERNOBYL", needs_engine=True)
    assert "ABILITY_CHERNOBYL" in m.needs_engine["abilities"]
    # Idempotent re-add with the same flag does not duplicate
    m.add("abilities", "CHERNOBYL", "ABILITY_CHERNOBYL", needs_engine=True)
    assert m.needs_engine["abilities"].count("ABILITY_CHERNOBYL") == 1


def test_needs_engine_post_hoc_mark() -> None:
    m = IdMap()
    m.add("moves", "GAMMARAY", "MOVE_GAMMARAY")
    m.mark_needs_engine("moves", "MOVE_GAMMARAY")
    assert "MOVE_GAMMARAY" in m.needs_engine["moves"]


def test_needs_engine_unknown_category_raises() -> None:
    m = IdMap()
    with pytest.raises(IdMapUnknownCategoryError):
        m.mark_needs_engine("trainers", "TRAINER_X")
    # sanity — trainers is a real category but not in NEEDS_ENGINE_CATEGORIES
    assert "trainers" in CATEGORIES
    assert "trainers" not in NEEDS_ENGINE_CATEGORIES


def test_save_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "id_map.json"
    m = IdMap()
    m.add("species", "URAYNE", "SPECIES_URAYNE")
    m.add("moves", "GAMMARAY", "MOVE_GAMMARAY", needs_engine=True)
    m.add("abilities", "CHERNOBYL", "ABILITY_CHERNOBYL", needs_engine=True)
    m.save(path)

    loaded = IdMap.load(path)
    assert loaded.get("species", "URAYNE") == "SPECIES_URAYNE"
    assert loaded.get("moves", "GAMMARAY") == "MOVE_GAMMARAY"
    assert "MOVE_GAMMARAY" in loaded.needs_engine["moves"]
    assert "ABILITY_CHERNOBYL" in loaded.needs_engine["abilities"]


def test_save_is_sorted_for_stable_diff(tmp_path: Path) -> None:
    path = tmp_path / "sorted.json"
    m = IdMap()
    m.add("species", "ZZZ", "SPECIES_ZZZ")
    m.add("species", "AAA", "SPECIES_AAA")
    m.add("species", "MMM", "SPECIES_MMM")
    m.save(path)

    raw = json.loads(path.read_text(encoding="utf-8"))
    keys = list(raw["species"].keys())
    assert keys == sorted(keys)
