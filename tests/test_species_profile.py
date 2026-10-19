"""species_converter.profile: the per-game species family profile."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.species_converter import profile

ENABLED = """\
#define P_GEN_1_POKEMON TRUE
#define P_FAMILY_BULBASAUR               P_GEN_1_POKEMON
#define P_FAMILY_EEVEE                   P_GEN_1_POKEMON
#define P_FAMILY_GASTLY                  P_GEN_1_POKEMON
"""

FAMILIES = """\
#if P_FAMILY_BULBASAUR
    [SPECIES_BULBASAUR] =
    {
    },
    [SPECIES_IVYSAUR] =
#endif //P_FAMILY_BULBASAUR

#if P_FAMILY_EEVEE
    [SPECIES_EEVEE] =
#if P_GEN_6_CROSS_EVOS
    [SPECIES_SYLVEON] =
#endif //P_GEN_6_CROSS_EVOS
#endif //P_FAMILY_EEVEE

#if P_FAMILY_GASTLY
    [SPECIES_GASTLY] =
    [SPECIES_GENGAR] =
#endif //P_FAMILY_GASTLY
"""

SPECIES_H = """\
#define SPECIES_BULBASAUR 1
#define SPECIES_IVYSAUR 2
#define SPECIES_GASTLY 92
#define SPECIES_GENGAR 94
#define SPECIES_EEVEE 133
#define SPECIES_SYLVEON 700
"""


def _fork(tmp_path: Path, families: str = FAMILIES) -> Path:
    fork = tmp_path / "engine"
    (fork / "include" / "config").mkdir(parents=True)
    (fork / "include" / "constants").mkdir(parents=True)
    info = fork / "src" / "data" / "pokemon" / "species_info"
    info.mkdir(parents=True)
    (fork / "include" / "config" / "species_enabled.h").write_text(ENABLED, encoding="utf-8")
    (fork / "include" / "constants" / "species.h").write_text(SPECIES_H, encoding="utf-8")
    (info / "gen_1_families.h").write_text(families, encoding="utf-8")
    return fork


def _id_map(tmp_path: Path, species: dict[str, str]) -> Path:
    path = tmp_path / "id_map.json"
    path.write_text(json.dumps({"species": species}), encoding="utf-8")
    return path


def test_species_to_family_follows_blocks_and_nested_ifs(tmp_path: Path) -> None:
    owner = profile.species_to_family(_fork(tmp_path))
    assert owner["SPECIES_IVYSAUR"] == "P_FAMILY_BULBASAUR"
    assert owner["SPECIES_SYLVEON"] == "P_FAMILY_EEVEE"  # cross-gen evo nested in the family
    assert owner["SPECIES_GENGAR"] == "P_FAMILY_GASTLY"


def test_profile_keeps_used_families_and_ignores_custom_species(tmp_path: Path) -> None:
    fork = _fork(tmp_path)
    ids = _id_map(tmp_path, {"GENGAR": "SPECIES_GENGAR", "SYLVEON": "SPECIES_SYLVEON",
                             "ORCHYNX": "SPECIES_ORCHYNX"})  # custom: not in species.h
    p = profile.build_profile(fork, ids)
    assert p.keep == ("P_FAMILY_EEVEE", "P_FAMILY_GASTLY")
    assert p.drop == ("P_FAMILY_BULBASAUR",)
    assert p.used_species == ("SPECIES_GENGAR", "SPECIES_SYLVEON")


def test_header_forces_dropped_families_false(tmp_path: Path) -> None:
    fork = _fork(tmp_path)
    p = profile.write_profile(fork, tmp_path / "out", _id_map(tmp_path, {"EEVEE": "SPECIES_EEVEE"}))
    text = (tmp_path / "out" / profile.PROFILE_HEADER).read_text(encoding="utf-8")
    assert "#undef P_FAMILY_BULBASAUR\n#define P_FAMILY_BULBASAUR FALSE" in text
    assert "#define P_FAMILY_EEVEE FALSE" not in text
    sidecar = json.loads((tmp_path / "out" / "species_profile.json").read_text(encoding="utf-8"))
    assert sidecar["keep"] == list(p.keep)


def test_profile_is_idempotent(tmp_path: Path) -> None:
    fork = _fork(tmp_path)
    ids = _id_map(tmp_path, {"EEVEE": "SPECIES_EEVEE"})
    profile.write_profile(fork, tmp_path / "out", ids)
    first = (tmp_path / "out" / profile.PROFILE_HEADER).read_bytes()
    profile.write_profile(fork, tmp_path / "out", ids)
    assert (tmp_path / "out" / profile.PROFILE_HEADER).read_bytes() == first


def test_used_species_outside_any_family_fails_loud(tmp_path: Path) -> None:
    fork = _fork(tmp_path, families=FAMILIES.replace("    [SPECIES_GENGAR] =\n", ""))
    with pytest.raises(ValueError, match="SPECIES_GENGAR"):
        profile.build_profile(fork, _id_map(tmp_path, {"GENGAR": "SPECIES_GENGAR"}))


def test_mismatched_family_close_fails_loud(tmp_path: Path) -> None:
    bad = FAMILIES.replace("#endif //P_FAMILY_GASTLY", "#endif //P_FAMILY_EEVEE")
    with pytest.raises(ValueError, match="closes while"):
        profile.species_to_family(_fork(tmp_path, families=bad))


def test_real_engine_keeps_uraniums_fifteen_families() -> None:
    """Against the vendored engine and the real id map (measured 2026-10-19)."""
    engine = Path(__file__).resolve().parents[1] / "engine"
    p = profile.build_profile(engine)
    assert len(p.used_species) == 35
    assert set(p.keep) == {
        "P_FAMILY_EKANS", "P_FAMILY_MANKEY", "P_FAMILY_GASTLY", "P_FAMILY_MAGIKARP",
        "P_FAMILY_EEVEE", "P_FAMILY_MAREEP", "P_FAMILY_MISDREAVUS", "P_FAMILY_DUNSPARCE",
        "P_FAMILY_GLIGAR", "P_FAMILY_CORSOLA", "P_FAMILY_LOTAD", "P_FAMILY_SABLEYE",
        "P_FAMILY_BUIZEL", "P_FAMILY_COTTONEE", "P_FAMILY_SPRITZEE",
    }
