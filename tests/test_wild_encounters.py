"""Tests for `rpg2gba.tileset_converter.wild_encounters` — the emission layer
that bridges the Phase 2 `wild_encounters.json` intermediate (Uranium-map-id
keyed) into the fork's `engine/src/data/wild_encounters.json` (MAP_*-keyed,
fixed slot counts, flat fishing array).

All fixtures here are synthetic and self-contained (built inline via
`tmp_path`) — no dependency on `RPG2GBA_URANIUM_SRC` / `RPG2GBA_POKEEMERALD`,
so this suite always runs.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from rpg2gba.tileset_converter import wild_encounters as we

KNOWN_SPECIES = {
    "SPECIES_WURMPLE",
    "SPECIES_POOCHYENA",
    "SPECIES_MAGIKARP",
    "SPECIES_GOLDEEN",
    "SPECIES_TENTACOOL",
}

# A small fork-shaped fields block: 3 land / 2 water / 2 rock_smash / 4 fishing
# slots (old_rod:1, good_rod:2, super_rod:1) — deliberately smaller than the
# real engine/include/constants/wild_encounter.h counts (12/5/5/10) so the
# tests exercise the "read counts from the fork's own fields block, never
# hardcode" contract rather than accidentally hardcoding the real numbers too.
_FORK_FIELDS = [
    {"type": "land_mons", "encounter_rates": [20, 20, 10]},
    {"type": "water_mons", "encounter_rates": [60, 30]},
    {"type": "rock_smash_mons", "encounter_rates": [60, 30]},
    {
        "type": "fishing_mons",
        "encounter_rates": [70, 30, 60, 20],
        "groups": {"old_rod": [0], "good_rod": [1, 2], "super_rod": [3]},
    },
]


def _fork_json(encounters: list[dict] | None = None) -> dict:
    return {
        "wild_encounter_groups": [
            {
                "label": "gWildMonHeaders",
                "for_maps": True,
                "fields": _FORK_FIELDS,
                "encounters": encounters if encounters is not None else [],
            }
        ]
    }


def _write_fork(tmp_path: Path, encounters: list[dict] | None = None, trailing_newline: bool = True) -> Path:
    path = tmp_path / "wild_encounters_fork.json"
    text = json.dumps(_fork_json(encounters), indent=2, ensure_ascii=False)
    if trailing_newline:
        text += "\n"
    path.write_text(text, encoding="utf-8")
    return path


def _mon(species: str, lo: int, hi: int) -> dict:
    return {"species": species, "min_level": lo, "max_level": hi}


def _base_intermediate() -> dict:
    return {
        "_comment": "test fixture",
        "maps": {
            "33": {
                "land_mons": {
                    "encounter_rate": 20,
                    "mons": [
                        _mon("SPECIES_WURMPLE", 2, 4),
                        _mon("SPECIES_POOCHYENA", 3, 5),
                        _mon("SPECIES_WURMPLE", 2, 2),
                    ],
                },
                "water_mons": {
                    "encounter_rate": 60,
                    "mons": [
                        _mon("SPECIES_MAGIKARP", 5, 10),
                        _mon("SPECIES_MAGIKARP", 5, 10),
                    ],
                },
                "fishing_mons": {
                    "old_rod": [_mon("SPECIES_MAGIKARP", 5, 10)],
                    "good_rod": [
                        _mon("SPECIES_GOLDEEN", 10, 20),
                        _mon("SPECIES_MAGIKARP", 10, 20),
                    ],
                    "super_rod": [_mon("SPECIES_TENTACOOL", 20, 30)],
                },
                "uranium_extra": {
                    "cave": {"encounter_rate": 5, "mons": [_mon("SPECIES_WURMPLE", 1, 1)]}
                },
            },
            "81": None,
        },
    }


def _write_intermediate(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "wild_encounters_intermediate.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


MAP_IDS = [33, 81]
MAP_CONSTS = {33: "MAP_ROUTE_1"}


# --- golden --------------------------------------------------------------

def test_golden_entry(tmp_path: Path) -> None:
    inter = _write_intermediate(tmp_path, _base_intermediate())
    fork = _write_fork(tmp_path)

    entries = we.build_encounter_entries(
        inter, MAP_IDS, MAP_CONSTS, KNOWN_SPECIES, fork_encounters_path=fork
    )

    assert len(entries) == 1
    entry = entries[0]
    assert entry.uranium_map_id == 33
    assert entry.map_const == "MAP_ROUTE_1"
    assert entry.base_label == "gRoute1"
    assert entry.data == {
        "map": "MAP_ROUTE_1",
        "base_label": "gRoute1",
        "land_mons": {
            "encounter_rate": 20,
            "mons": [
                _mon("SPECIES_WURMPLE", 2, 4),
                _mon("SPECIES_POOCHYENA", 3, 5),
                _mon("SPECIES_WURMPLE", 2, 2),
            ],
        },
        "water_mons": {
            "encounter_rate": 60,
            "mons": [
                _mon("SPECIES_MAGIKARP", 5, 10),
                _mon("SPECIES_MAGIKARP", 5, 10),
            ],
        },
        "fishing_mons": {
            "encounter_rate": we.DEFAULT_FISHING_ENCOUNTER_RATE,
            "mons": [
                _mon("SPECIES_MAGIKARP", 5, 10),
                _mon("SPECIES_GOLDEEN", 10, 20),
                _mon("SPECIES_MAGIKARP", 10, 20),
                _mon("SPECIES_TENTACOOL", 20, 30),
            ],
        },
    }
    # uranium_extra is dropped, never carried into the fork body
    assert "uranium_extra" not in entry.data


def test_base_label_matches_fork_convention(tmp_path: Path) -> None:
    """MAP_ROUTE101 -> gRoute101, matching the fork's own committed example."""
    inter = _write_intermediate(
        tmp_path,
        {
            "maps": {
                "5": {
                    "land_mons": {
                        "encounter_rate": 20,
                        "mons": [
                            _mon("SPECIES_WURMPLE", 1, 1),
                            _mon("SPECIES_WURMPLE", 1, 1),
                            _mon("SPECIES_WURMPLE", 1, 1),
                        ],
                    }
                }
            }
        },
    )
    fork = _write_fork(tmp_path)
    entries = we.build_encounter_entries(
        inter, [5], {5: "MAP_ROUTE101"}, KNOWN_SPECIES, fork_encounters_path=fork
    )
    assert entries[0].base_label == "gRoute101"


# --- fishing flattening ----------------------------------------------------

def test_fishing_flatten_uses_fork_group_indices(tmp_path: Path) -> None:
    inter = _write_intermediate(tmp_path, _base_intermediate())
    fork = _write_fork(tmp_path)
    entries = we.build_encounter_entries(
        inter, MAP_IDS, MAP_CONSTS, KNOWN_SPECIES, fork_encounters_path=fork
    )
    mons = entries[0].data["fishing_mons"]["mons"]
    # groups: old_rod=[0], good_rod=[1,2], super_rod=[3]
    assert mons[0]["species"] == "SPECIES_MAGIKARP"  # old_rod
    assert mons[1]["species"] == "SPECIES_GOLDEEN"  # good_rod[0]
    assert mons[2]["species"] == "SPECIES_MAGIKARP"  # good_rod[1]
    assert mons[3]["species"] == "SPECIES_TENTACOOL"  # super_rod


# --- uranium_extra dropped, logged -----------------------------------------

def test_uranium_extra_dropped_and_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    inter = _write_intermediate(tmp_path, _base_intermediate())
    fork = _write_fork(tmp_path)
    with caplog.at_level(logging.INFO):
        entries = we.build_encounter_entries(
            inter, MAP_IDS, MAP_CONSTS, KNOWN_SPECIES, fork_encounters_path=fork
        )
    assert "uranium_extra" not in entries[0].data
    assert any("dropped uranium_extra" in r.message and "cave" in r.message for r in caplog.records)


# --- null table skipped ------------------------------------------------------

def test_null_table_skipped_silently(tmp_path: Path) -> None:
    inter = _write_intermediate(tmp_path, _base_intermediate())
    fork = _write_fork(tmp_path)
    entries = we.build_encounter_entries(
        inter, MAP_IDS, MAP_CONSTS, KNOWN_SPECIES, fork_encounters_path=fork
    )
    assert {e.uranium_map_id for e in entries} == {33}


def test_absent_table_skipped_silently(tmp_path: Path) -> None:
    """A map id with no key at all (not even null) is treated the same as null."""
    data = _base_intermediate()
    del data["maps"]["81"]
    inter = _write_intermediate(tmp_path, data)
    fork = _write_fork(tmp_path)
    entries = we.build_encounter_entries(
        inter, MAP_IDS, MAP_CONSTS, KNOWN_SPECIES, fork_encounters_path=fork
    )
    assert {e.uranium_map_id for e in entries} == {33}


# --- fail-loud cases ---------------------------------------------------------

def test_unknown_species_fails_loud(tmp_path: Path) -> None:
    data = _base_intermediate()
    data["maps"]["33"]["land_mons"]["mons"][0]["species"] = "SPECIES_BOGUS"
    inter = _write_intermediate(tmp_path, data)
    fork = _write_fork(tmp_path)
    with pytest.raises(ValueError, match="SPECIES_BOGUS"):
        we.build_encounter_entries(
            inter, MAP_IDS, MAP_CONSTS, KNOWN_SPECIES, fork_encounters_path=fork
        )


def test_too_few_slots_fails_loud(tmp_path: Path) -> None:
    data = _base_intermediate()
    data["maps"]["33"]["land_mons"]["mons"].pop()  # 2 instead of the required 3
    inter = _write_intermediate(tmp_path, data)
    fork = _write_fork(tmp_path)
    with pytest.raises(ValueError, match="land_mons"):
        we.build_encounter_entries(
            inter, MAP_IDS, MAP_CONSTS, KNOWN_SPECIES, fork_encounters_path=fork
        )


def test_too_many_slots_fails_loud(tmp_path: Path) -> None:
    data = _base_intermediate()
    data["maps"]["33"]["land_mons"]["mons"].append(_mon("SPECIES_WURMPLE", 1, 1))  # 4
    inter = _write_intermediate(tmp_path, data)
    fork = _write_fork(tmp_path)
    with pytest.raises(ValueError, match="land_mons"):
        we.build_encounter_entries(
            inter, MAP_IDS, MAP_CONSTS, KNOWN_SPECIES, fork_encounters_path=fork
        )


def test_fishing_rod_count_mismatch_fails_loud(tmp_path: Path) -> None:
    data = _base_intermediate()
    data["maps"]["33"]["fishing_mons"]["good_rod"].append(_mon("SPECIES_MAGIKARP", 1, 1))  # 3 not 2
    inter = _write_intermediate(tmp_path, data)
    fork = _write_fork(tmp_path)
    with pytest.raises(ValueError, match="good_rod"):
        we.build_encounter_entries(
            inter, MAP_IDS, MAP_CONSTS, KNOWN_SPECIES, fork_encounters_path=fork
        )


def test_missing_map_const_fails_loud(tmp_path: Path) -> None:
    inter = _write_intermediate(tmp_path, _base_intermediate())
    fork = _write_fork(tmp_path)
    with pytest.raises(ValueError, match="MAP_"):
        we.build_encounter_entries(
            inter, MAP_IDS, {}, KNOWN_SPECIES, fork_encounters_path=fork
        )


# --- upsert overlay: base untouched, idempotence, replace-vs-append ---------

def test_upsert_writes_overlay_not_base(tmp_path: Path) -> None:
    inter = _write_intermediate(tmp_path, _base_intermediate())
    fork = _write_fork(tmp_path)
    base_text_before = fork.read_text(encoding="utf-8")
    entries = we.build_encounter_entries(
        inter, MAP_IDS, MAP_CONSTS, KNOWN_SPECIES, fork_encounters_path=fork
    )

    overlay = we.overlay_path(fork)
    assert overlay == fork.with_name("wild_encounters_fork.gen.json")
    assert not overlay.exists()

    n = we.upsert_encounters(fork, entries)

    assert n == 1
    assert overlay.exists()
    # Base file is byte-identical after the call -- never written in place.
    assert fork.read_text(encoding="utf-8") == base_text_before

    raw = json.loads(overlay.read_text(encoding="utf-8"))
    group = raw["wild_encounter_groups"][0]
    assert [e["map"] for e in group["encounters"]] == ["MAP_ROUTE_1"]


def test_upsert_idempotent(tmp_path: Path) -> None:
    inter = _write_intermediate(tmp_path, _base_intermediate())
    fork = _write_fork(tmp_path)
    entries = we.build_encounter_entries(
        inter, MAP_IDS, MAP_CONSTS, KNOWN_SPECIES, fork_encounters_path=fork
    )
    overlay = we.overlay_path(fork)

    n1 = we.upsert_encounters(fork, entries)
    text_after_first = overlay.read_text(encoding="utf-8")
    n2 = we.upsert_encounters(fork, entries)
    text_after_second = overlay.read_text(encoding="utf-8")

    assert n1 == 1
    assert n2 == 1
    assert text_after_first == text_after_second

    raw = json.loads(text_after_second)
    group = raw["wild_encounter_groups"][0]
    assert len(group["encounters"]) == 1  # no duplicate appended


def test_upsert_replaces_changed_entry(tmp_path: Path) -> None:
    inter = _write_intermediate(tmp_path, _base_intermediate())
    fork = _write_fork(tmp_path)
    overlay = we.overlay_path(fork)
    entries = we.build_encounter_entries(
        inter, MAP_IDS, MAP_CONSTS, KNOWN_SPECIES, fork_encounters_path=fork
    )
    we.upsert_encounters(fork, entries)

    # Change the source data (drop water_mons) and re-run. The base is always
    # re-read fresh, so the second overlay is built from the base again --
    # never from the first overlay -- and replaces the entry rather than
    # appending a second one.
    data = _base_intermediate()
    del data["maps"]["33"]["water_mons"]
    inter2 = _write_intermediate(tmp_path, data)
    entries2 = we.build_encounter_entries(
        inter2, MAP_IDS, MAP_CONSTS, KNOWN_SPECIES, fork_encounters_path=fork
    )
    we.upsert_encounters(fork, entries2)

    raw = json.loads(overlay.read_text(encoding="utf-8"))
    group = raw["wild_encounter_groups"][0]
    assert len(group["encounters"]) == 1  # still exactly one entry for MAP_ROUTE_1
    assert "water_mons" not in group["encounters"][0]


def test_upsert_replaces_vanilla_row_for_colliding_map(tmp_path: Path) -> None:
    """An entry for a map already present in the vanilla base (e.g. a Uranium
    map constant that happens to collide with a vanilla one) replaces that row
    rather than duplicating it."""
    inter = _write_intermediate(tmp_path, _base_intermediate())
    vanilla_row = {
        "map": "MAP_ROUTE_1",
        "base_label": "gRoute1",
        "land_mons": {
            "encounter_rate": 20,
            "mons": [_mon("SPECIES_POOCHYENA", 1, 1)] * 3,
        },
    }
    fork = _write_fork(tmp_path, encounters=[vanilla_row])
    overlay = we.overlay_path(fork)
    entries = we.build_encounter_entries(
        inter, MAP_IDS, MAP_CONSTS, KNOWN_SPECIES, fork_encounters_path=fork
    )

    we.upsert_encounters(fork, entries)

    raw = json.loads(overlay.read_text(encoding="utf-8"))
    group = raw["wild_encounter_groups"][0]
    assert len(group["encounters"]) == 1  # vanilla row replaced, not duplicated
    assert group["encounters"][0]["land_mons"]["mons"][0]["species"] == "SPECIES_WURMPLE"


def test_upsert_preserves_trailing_newline(tmp_path: Path) -> None:
    inter = _write_intermediate(tmp_path, _base_intermediate())
    fork_no_nl = _write_fork(tmp_path, trailing_newline=False)
    fork_no_nl = fork_no_nl.rename(fork_no_nl.with_name("wild_encounters_no_nl.json"))
    entries = we.build_encounter_entries(
        inter, MAP_IDS, MAP_CONSTS, KNOWN_SPECIES, fork_encounters_path=fork_no_nl
    )
    we.upsert_encounters(fork_no_nl, entries)
    overlay_no_nl = we.overlay_path(fork_no_nl)
    assert not overlay_no_nl.read_text(encoding="utf-8").endswith("\n")

    fork_nl = _write_fork(tmp_path, trailing_newline=True)
    fork_nl = fork_nl.rename(fork_nl.with_name("wild_encounters_with_nl.json"))
    entries2 = we.build_encounter_entries(
        inter, MAP_IDS, MAP_CONSTS, KNOWN_SPECIES, fork_encounters_path=fork_nl
    )
    we.upsert_encounters(fork_nl, entries2)
    overlay_nl = we.overlay_path(fork_nl)
    assert overlay_nl.read_text(encoding="utf-8").endswith("\n")


def test_upsert_out_path_equal_to_base_fails_loud(tmp_path: Path) -> None:
    inter = _write_intermediate(tmp_path, _base_intermediate())
    fork = _write_fork(tmp_path)
    entries = we.build_encounter_entries(
        inter, MAP_IDS, MAP_CONSTS, KNOWN_SPECIES, fork_encounters_path=fork
    )
    with pytest.raises(ValueError, match="out_path must not equal fork_encounters_path"):
        we.upsert_encounters(fork, entries, out_path=fork)
