"""Phase 2 §2.1 tests — species (`pokemon.py`).

Per CLAUDE.md §4.6 / PHASE2_PLAN.md §2.1:
  * round-trip: parse → emit C → regex-read back → diff
  * golden: pinned snapshot of real output (ORCHYNX starter + URAYNE Nuclear)
  * edge: species 201 (Gengar) has no Tandor dex entry
  * edge: a Uranium-original ability is marked needs_engine

All are env-gated via the `uranium_data` fixture (skip if the source is absent).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from rpg2gba.pbs_converter import pokemon
from rpg2gba.pbs_converter._id_map import IdMap

pytestmark = pytest.mark.phase2

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _build(uranium_data: Path, reference_dir: Path) -> tuple[list, pokemon._Resolver]:
    """Parse all species + side data and build a resolver (no fork needed)."""
    species = pokemon.parse_dexdata(uranium_data / "dexdata.dat")
    n = len(species) - 1
    pokemon.attach_side_data(
        species,
        level_up_moves=pokemon.parse_attacks_rs(uranium_data / "attacksRS.dat", n),
        evolutions=pokemon.parse_evolutions(uranium_data / "evolutions.dat", n),
        egg_moves=pokemon.parse_indexed_u16_list(uranium_data / "eggEmerald.dat", n),
        regionals_matrix=pokemon.parse_regionals(uranium_data / "regionals.dat"),
    )
    pokemon.attach_internal_names(
        species, pokemon._load_id_json(reference_dir / "species_internal_names.json")
    )
    resolver = pokemon._build_resolver(IdMap(), reference_dir)
    for s in species:
        if s is not None:
            resolver.species_constant(s.id)
    return species, resolver


def _entry(c_text: str, const: str) -> str:
    m = re.search(r"    \[" + re.escape(const) + r"\] =\n    \{.*?\n    \},", c_text, re.S)
    assert m, f"{const} entry not found in emitted species_info.h"
    return m.group(0)


def test_roundtrip_stats(uranium_data: Path, reference_dir: Path) -> None:
    """Stats emitted into species_info.h re-read back to the parsed values."""
    species, resolver = _build(uranium_data, reference_dir)
    c_text = pokemon._emit_species_info(species, resolver)
    checked = 0
    for s in species:
        if s is None:
            continue
        entry = _entry(c_text, pokemon.to_constant("SPECIES", s.internal_name))
        for field, expected in zip(pokemon._STAT_FIELDS, s.base_stats):
            m = re.search(rf"\.{field} = (\d+),", entry)
            assert m and int(m.group(1)) == expected, f"{s.internal_name}.{field}"
        catch = re.search(r"\.catchRate = (\d+),", entry)
        assert catch and int(catch.group(1)) == s.rareness
        checked += 1
    assert checked >= 200


def test_golden_orchynx_urayne(uranium_data: Path, reference_dir: Path) -> None:
    """Pinned output for the starter + a Nuclear legendary (D5 fixture)."""
    species, resolver = _build(uranium_data, reference_dir)
    c_text = pokemon._emit_species_info(species, resolver)
    got = _entry(c_text, "SPECIES_ORCHYNX") + "\n" + _entry(c_text, "SPECIES_URAYNE") + "\n"
    expected = (FIXTURES / "pokemon_golden.h").read_text(encoding="utf-8")
    assert got == expected


def test_edge_species201_no_tandor_dex(uranium_data: Path, reference_dir: Path) -> None:
    """Species 201 (Gengar) has no Tandor regional dex number."""
    species, _ = _build(uranium_data, reference_dir)
    s201 = species[201]
    assert s201 is not None
    assert s201.internal_name == "GENGAR"
    assert s201.regional_dex_number is None


def test_gate_unobtainable_and_extra_hidden_sidecars(
    uranium_data: Path, tmp_path: Path
) -> None:
    """V5 gate deltas via the real run() path:
    * unobtainable_species.json isolates exactly id 201 GENGAR, and its emitted
      species_info entry carries the UNOBTAINABLE marker comment.
    * extra_hidden_abilities.json records the 8 species with a 2nd hidden ability,
      and every extra is flagged needs_engine on the id_map.
    """
    id_map = IdMap()
    pokemon.run(uranium_data.parent, tmp_path, id_map)
    inter = tmp_path / "intermediate"

    unobtainable = json.loads((inter / "unobtainable_species.json").read_text(encoding="utf-8"))
    assert unobtainable == ["SPECIES_GENGAR"]

    info = (tmp_path / "src" / "data" / "pokemon" / "species_info.h").read_text(encoding="utf-8")
    assert "UNOBTAINABLE" in _entry(info, "SPECIES_GENGAR")

    extra = json.loads((inter / "extra_hidden_abilities.json").read_text(encoding="utf-8"))
    assert len(extra) == 8
    assert {"SPECIES_MAGIKARP", "SPECIES_MINYAN"} <= set(extra)
    for consts in extra.values():
        assert consts, "extra-hidden entry must be non-empty"
        for c in consts:
            assert c in id_map.needs_engine["abilities"], f"{c} not flagged needs_engine"


def test_edge_evolutions_forward_only(uranium_data: Path) -> None:
    """The 0xC0 data bits are filtered: methods stay within EVONAMES range."""
    species = pokemon.parse_dexdata(uranium_data / "dexdata.dat")
    n = len(species) - 1
    evos = pokemon.parse_evolutions(uranium_data / "evolutions.dat", n)
    for per_species in evos:
        for method_idx, _param, _target in per_species:
            assert 0 <= method_idx < len(pokemon._EVONAMES), method_idx


def test_edge_uranium_ability_needs_engine(
    uranium_data: Path, reference_dir: Path, fork_path: Path | None
) -> None:
    """A Uranium-original ability resolves to needs_engine against the fork."""
    if fork_path is None:
        pytest.skip("RPG2GBA_POKEEMERALD not set; can't validate needs_engine")
    id_map = IdMap()
    resolver = pokemon._build_resolver(id_map, reference_dir)
    # ABILITY_GEIGER_SENSE is a Uranium-original (Urayne's ability).
    geiger_id = next(i for i, n in resolver.ability_internal.items() if n == "GEIGERSENSE")
    const = resolver.ability_constant(geiger_id)
    assert const == "ABILITY_GEIGER_SENSE"
    assert const in id_map.needs_engine["abilities"]
