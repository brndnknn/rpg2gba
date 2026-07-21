"""Tests for the species category in the fork capability gate (W5 part A,
STARTER_SPECIES_PLAN.md §W5).

Policy under test (deliberate, per the plan): the gate's species extras come
from `species_manifest.json` (written by `species_converter.stage`), and
ONLY species listed there pass — never the full `reference/uranium_id_map.json`
`needs_engine.species` table. An id-mapped-but-unstaged species (e.g.
SPECIES_URAYNE) must still be rejected; widening the gate to accept it would
defeat its entire purpose (catching references to symbols the engine does
not actually define, CLAUDE.md §4.7).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.conversion_agent import fork_index as fi


@pytest.fixture(scope="module")
def index() -> fi.ForkIndex:
    return fi.build()


def _write_manifest(path: Path, species_constants: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "generator": "rpg2gba.species_converter.stage",
                "pristine_species_egg": 1573,
                "new_species_egg": 1573 + len(species_constants),
                "species": [
                    {
                        "uranium_id": i + 1,
                        "internal_name": const.removeprefix("SPECIES_"),
                        "fork_species_id": 1573 + i,
                        "species_constant": const,
                        "national_dex_constant": f"NATIONAL_DEX_{const.removeprefix('SPECIES_')}",
                        "cry_constant": f"CRY_{const.removeprefix('SPECIES_')}",
                    }
                    for i, const in enumerate(species_constants)
                ],
            }
        ),
        encoding="utf-8",
    )


def test_staged_species_passes_verify_script(tmp_path: Path, index: fi.ForkIndex) -> None:
    manifest = tmp_path / "species_manifest.json"
    _write_manifest(manifest, ["SPECIES_RAPTORCH"])

    extras = fi.registry_extra_symbols(species_manifest_path=manifest)
    assert "SPECIES_RAPTORCH" in extras
    assert "NATIONAL_DEX_RAPTORCH" in extras
    assert "CRY_RAPTORCH" in extras

    script = "checkspecies(SPECIES_RAPTORCH)\nif (var(VAR_RESULT) == TRUE) {\n    end\n}\n"
    violations = fi.verify_script(script, index, extra_symbols=extras)
    assert violations == []


def test_unstaged_species_still_reported_as_violation(
    tmp_path: Path, index: fi.ForkIndex
) -> None:
    # SPECIES_RAPTORCH is staged; SPECIES_URAYNE (id-mapped per
    # reference/uranium_id_map.json's needs_engine.species, but never staged
    # by W5) must still be rejected — this is the important regression.
    manifest = tmp_path / "species_manifest.json"
    _write_manifest(manifest, ["SPECIES_RAPTORCH"])

    extras = fi.registry_extra_symbols(species_manifest_path=manifest)
    assert "SPECIES_URAYNE" not in extras

    script = "checkspecies(SPECIES_URAYNE)\nif (var(VAR_RESULT) == TRUE) {\n    end\n}\n"
    violations = fi.verify_script(script, index, extra_symbols=extras)
    assert len(violations) == 1
    assert violations[0].symbol == "SPECIES_URAYNE"
    assert violations[0].kind == "constant"


def test_missing_manifest_tolerated(index: fi.ForkIndex) -> None:
    # No species converter run yet — a None path contributes no extras and
    # is not an error (mirrors the flag_state_path/map_constants_path
    # optionality already established for the other two categories).
    extras = fi.registry_extra_symbols(species_manifest_path=None)
    assert extras == set()

    script = "checkspecies(SPECIES_RAPTORCH)\nif (var(VAR_RESULT) == TRUE) {\n    end\n}\n"
    violations = fi.verify_script(script, index, extra_symbols=extras)
    assert len(violations) == 1
    assert violations[0].symbol == "SPECIES_RAPTORCH"


def test_malformed_manifest_fails_loud(tmp_path: Path) -> None:
    manifest = tmp_path / "species_manifest.json"
    # Missing the "species" key entirely — shape drift, must raise (KeyError),
    # never silently default to no extras.
    manifest.write_text(json.dumps({"version": 1}), encoding="utf-8")

    with pytest.raises(KeyError):
        fi.registry_extra_symbols(species_manifest_path=manifest)


def test_malformed_manifest_entry_missing_constant_fails_loud(tmp_path: Path) -> None:
    manifest = tmp_path / "species_manifest.json"
    manifest.write_text(
        json.dumps({"version": 1, "species": [{"internal_name": "RAPTORCH"}]}),
        encoding="utf-8",
    )

    with pytest.raises(KeyError):
        fi.registry_extra_symbols(species_manifest_path=manifest)
