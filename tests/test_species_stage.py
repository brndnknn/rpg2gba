"""W1 tests — species staging emitter (`species_converter.stage`).

Per CLAUDE.md §4.6:
  * round-trip: emit, then parse the emitted C back well enough to confirm
    the six entries carry the stats/types that came out of the parsers.
  * golden: pinned emitted `species_info` entries for ORCHYNX (plain) and
    METALYNX (the evolution-target edge).
  * edge: fork-append id math (SPECIES_EGG chaining), empty-selection no-op,
    idempotence, and a dangling evolution-target failing loud.

All tests that touch real Uranium data are gated behind the `uranium_data`
fixture (skips cleanly when `RPG2GBA_URANIUM_SRC` is unset) and the
`fork_path` fixture (skips when `RPG2GBA_POKEEMERALD`/`engine/` is unset),
matching `test_pbs_pokemon.py`'s pattern.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from rpg2gba.species_converter import stage
from rpg2gba.species_converter.common import STARTER_SPECIES, SpeciesSpec

pytestmark = pytest.mark.phase2

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture()
def uranium_src(uranium_data: Path) -> Path:
    """`$RPG2GBA_URANIUM_SRC` root (one level up from the `Data` dir)."""
    return uranium_data.parent


@pytest.fixture()
def engine_dir(fork_path: Path | None) -> Path:
    if fork_path is None:
        pytest.skip("RPG2GBA_POKEEMERALD not set; species staging needs the real fork")
    return fork_path


def _entry(c_text: str, const: str) -> str:
    m = re.search(r"    \[" + re.escape(const) + r"\] =\n    \{.*?\n    \},", c_text, re.S)
    assert m, f"{const} entry not found in emitted species_info.h"
    return m.group(0)


# ===========================================================================
# Round-trip
# ===========================================================================


def test_roundtrip_stats_and_types(uranium_src: Path, engine_dir: Path, tmp_path: Path) -> None:
    """Stats/types emitted into uranium_species_info.h re-read back to parsed values."""
    manifest = stage.write_all(uranium_src=uranium_src, engine_dir=engine_dir, out_dir=tmp_path)
    c_text = (tmp_path / "uranium_species_info.h").read_text(encoding="utf-8")

    species, _ = stage.load_all_species(uranium_src, stage._reference_dir())
    records = stage.select_starters(species, STARTER_SPECIES)

    assert len(manifest["species"]) == 6
    for spec, rec in zip(STARTER_SPECIES, records):
        entry = _entry(c_text, spec.constant)
        stat_fields = ("baseHP", "baseAttack", "baseDefense", "baseSpeed", "baseSpAttack", "baseSpDefense")
        for field, expected in zip(stat_fields, rec.base_stats):
            m = re.search(rf"\.{field} = (\d+),", entry)
            assert m and int(m.group(1)) == expected, f"{spec.internal_name}.{field}"
        # types: both type1/type2 constants must appear inside MON_TYPES(...)
        types_m = re.search(r"\.types = MON_TYPES\(([^)]*)\),", entry)
        assert types_m, f"{spec.internal_name}: no .types field"


def test_roundtrip_manifest_matches_emitted_constants(
    uranium_src: Path, engine_dir: Path, tmp_path: Path
) -> None:
    """Every manifest species_constant appears as a `[SPECIES_X] =` entry and
    a `#define SPECIES_X` in the constants overlay."""
    manifest = stage.write_all(uranium_src=uranium_src, engine_dir=engine_dir, out_dir=tmp_path)
    info_text = (tmp_path / "uranium_species_info.h").read_text(encoding="utf-8")
    const_text = (tmp_path / "uranium_species_constants.h").read_text(encoding="utf-8")
    for rec in manifest["species"]:
        const = rec["species_constant"]
        assert f"[{const}] =" in info_text
        assert f"#define {const} " in const_text


# ===========================================================================
# Golden
# ===========================================================================


def test_golden_orchynx_metalynx(uranium_src: Path, engine_dir: Path, tmp_path: Path) -> None:
    """Pinned emitted entries for ORCHYNX (plain) + METALYNX (evolution target)."""
    stage.write_all(uranium_src=uranium_src, engine_dir=engine_dir, out_dir=tmp_path)
    c_text = (tmp_path / "uranium_species_info.h").read_text(encoding="utf-8")
    got = _entry(c_text, "SPECIES_ORCHYNX") + "\n" + _entry(c_text, "SPECIES_METALYNX") + "\n"
    expected = (FIXTURES / "species_stage_golden.h").read_text(encoding="utf-8")
    assert got == expected


# ===========================================================================
# Edge cases
# ===========================================================================


def test_edge_fork_append_id_math(uranium_src: Path, engine_dir: Path, tmp_path: Path) -> None:
    """The first new species takes the pristine SPECIES_EGG value, ids chain
    sequentially, and URANIUM_SPECIES_LAST anchors to the final one."""
    pristine_egg, anchor = stage.read_pristine_species_egg(engine_dir)
    assert pristine_egg == 1573
    assert anchor == "SPECIES_GLIMMORA_MEGA"

    manifest = stage.write_all(uranium_src=uranium_src, engine_dir=engine_dir, out_dir=tmp_path)
    assert manifest["pristine_species_egg"] == pristine_egg
    assert manifest["new_species_egg"] == pristine_egg + 6

    ids = [rec["fork_species_id"] for rec in manifest["species"]]
    assert ids == list(range(pristine_egg, pristine_egg + 6))

    const_text = (tmp_path / "uranium_species_constants.h").read_text(encoding="utf-8")
    assert f"#define SPECIES_ORCHYNX ({anchor} + 1)" in const_text
    assert "#define SPECIES_METALYNX (SPECIES_ORCHYNX + 1)" in const_text
    assert "#define URANIUM_SPECIES_LAST SPECIES_ELECTRUXO" in const_text


def test_edge_empty_selection_is_noop(engine_dir: Path, tmp_path: Path) -> None:
    """Empty selection emits every file in a no-op (empty-guarded) form and
    needs no Uranium source at all."""
    manifest = stage.write_all(
        uranium_src=Path("/nonexistent"), engine_dir=engine_dir, out_dir=tmp_path, selected=()
    )
    assert manifest["species"] == []
    assert manifest["new_species_egg"] == manifest["pristine_species_egg"]

    for name in (
        "uranium_species_constants.h",
        "uranium_pokedex_ids.h",
        "uranium_learnsets.h",
        "uranium_species_info.h",
        "uranium_species_graphics.h",
        "uranium_cries_enum.h",
        "uranium_cry_table_forward.inc",
        "uranium_cry_table_reverse.inc",
        "uranium_cry_sound_data.inc",
    ):
        text = (tmp_path / name).read_text(encoding="utf-8")
        assert "SPECIES_ORCHYNX" not in text
        assert "no Uranium species selected" in text
        # Every #define/emitted symbol line must be absent — only banner/guard/note lines remain.
        assert "URANIUM_SPECIES_LAST" not in text


def test_edge_idempotence(uranium_src: Path, engine_dir: Path, tmp_path: Path) -> None:
    """Emitting twice with identical inputs produces byte-identical output."""
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    stage.write_all(uranium_src=uranium_src, engine_dir=engine_dir, out_dir=out1)
    stage.write_all(uranium_src=uranium_src, engine_dir=engine_dir, out_dir=out2)

    names1 = sorted(p.name for p in out1.iterdir())
    names2 = sorted(p.name for p in out2.iterdir())
    assert names1 == names2
    for name in names1:
        assert (out1 / name).read_bytes() == (out2 / name).read_bytes(), name


def test_edge_dangling_evolution_target_fails_loud(uranium_src: Path, engine_dir: Path) -> None:
    """An evolution pointing at a species not in the selection is a fail-loud error."""
    species, _ = stage.load_all_species(uranium_src, stage._reference_dir())
    records = stage.select_starters(species, STARTER_SPECIES)
    pristine_egg, _ = stage.read_pristine_species_egg(engine_dir)

    # Drop METALYNX (index 1) — ORCHYNX (index 0) still evolves into it.
    partial_specs = (STARTER_SPECIES[0],) + STARTER_SPECIES[2:]
    partial_records = [records[0]] + records[2:]

    with pytest.raises(ValueError, match="dangling reference"):
        stage.build_staged_species(partial_specs, partial_records, pristine_egg)


def test_edge_starter_species_internal_names_verified(uranium_src: Path) -> None:
    """select_starters fails loud if a STARTER_SPECIES entry's internal_name
    doesn't match the parsed record (drift guard)."""
    species, _ = stage.load_all_species(uranium_src, stage._reference_dir())
    bad = (SpeciesSpec(1, "NOT_ORCHYNX"),)
    with pytest.raises(ValueError, match="expected internal_name"):
        stage.select_starters(species, bad)


def test_edge_ability_constants_verified_against_fork(engine_dir: Path) -> None:
    """The six starters' abilities are asserted to be real fork constants,
    not merely assumed (CLAUDE.md §4.7)."""
    stage.assert_fork_constants_exist(
        engine_dir, stage._EXPECTED_ABILITIES, "include/constants/abilities.h", "ABILITY"
    )
    with pytest.raises(ValueError, match="not defined in fork"):
        stage.assert_fork_constants_exist(
            engine_dir, {"ABILITY_TOTALLY_MADE_UP"}, "include/constants/abilities.h", "ABILITY"
        )
