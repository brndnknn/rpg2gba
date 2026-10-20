"""Tests for `scripts/assemble_pathfinder.py`'s heal-location overlay pass
(S8b6, `run_heal_location_pass`).

The pass appends the slice's derived white-out respawn points (start-anchor +
Pokémon Center entries, `rpg2gba.pbs_converter.heal_locations.generate_entries`)
onto an overlay of the fork's committed `src/data/heal_locations.json`, picked
up by `engine/json_data_rules.mk`'s `RPG2GBA_HEAL_LOCATIONS` hook. Since the
`heal_locations` module is being developed in parallel elsewhere, these tests
monkeypatch `generate_entries` to a fixed contract-shaped return value rather
than depending on real data -- matching `test_berry_tree_seed_header.py`'s
approach to the same orchestrator shape.

Covers: (a) the gen file is upstream entries + Uranium entries, in order, with
the upstream file left untouched; (b) running twice produces byte-identical
output (CLAUDE.md §4.2); (c) an id collision with upstream raises; (d) a
resolved entry naming a map outside `SLICE_MAP_IDS` raises; (e) `--dry-run`
(via the pass's own `dry_run` flag) writes nothing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import assemble_pathfinder as ap  # noqa: E402

from rpg2gba.pbs_converter import heal_locations as hl  # noqa: E402


_UPSTREAM = {
    "heal_locations": [
        {
            "id": "HEAL_LOCATION_PETALBURG_CITY",
            "map": "MAP_PETALBURG_CITY",
            "x": 20,
            "y": 17,
            "respawn_map": "MAP_PETALBURG_CITY_POKEMON_CENTER_1F",
            "respawn_npc": "LOCALID_PETALBURG_NURSE",
        },
    ]
}

_CONSTS = {
    "49": {"map_const": "MAP_MOKI_TOWN_PLAYERS_HOUSE_1F"},
    "12": {"map_const": "MAP_KEVLAR_TOWN_POKEMON_CENTER"},
}

_ENTRIES = [
    hl.HealLocationEntry(
        id="HEAL_LOCATION_URANIUM_START",
        map="MAP_MOKI_TOWN_PLAYERS_HOUSE_1F",
        x=7,
        y=7,
    ),
    hl.HealLocationEntry(
        id="HEAL_LOCATION_KEVLAR_TOWN_POKEMON_CENTER",
        map="MAP_KEVLAR_TOWN_POKEMON_CENTER",
        x=8,
        y=13,
    ),
]


def _write_upstream(fork: Path, data: dict = _UPSTREAM) -> Path:
    path = fork / "src" / "data" / "heal_locations.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _patch_generate_entries(monkeypatch, entries: list, resolutions: list | None = None) -> None:
    monkeypatch.setattr(
        hl, "generate_entries", lambda **kwargs: (entries, resolutions or [])
    )


def test_gen_file_is_upstream_plus_uranium_entries_and_upstream_untouched(
    tmp_path: Path, monkeypatch
) -> None:
    out = tmp_path / "out"
    fork = tmp_path / "fork"
    monkeypatch.setattr(ap, "SLICE_MAP_IDS", [49, 12])
    upstream_path = _write_upstream(fork)
    upstream_before = upstream_path.read_text(encoding="utf-8")
    _patch_generate_entries(monkeypatch, _ENTRIES)

    ap.run_heal_location_pass(out, fork, _CONSTS, dry_run=False)

    # Upstream file is never modified.
    assert upstream_path.read_text(encoding="utf-8") == upstream_before

    gen_path = fork / "src" / "data" / "heal_locations.gen.json"
    gen = json.loads(gen_path.read_text(encoding="utf-8"))
    ids = [e["id"] for e in gen["heal_locations"]]
    assert ids == [
        "HEAL_LOCATION_PETALBURG_CITY",
        "HEAL_LOCATION_URANIUM_START",
        "HEAL_LOCATION_KEVLAR_TOWN_POKEMON_CENTER",
    ]
    # Upstream entry's extra fields (respawn_*) survive untouched.
    petalburg = gen["heal_locations"][0]
    assert petalburg["respawn_npc"] == "LOCALID_PETALBURG_NURSE"
    # New entries carry only the four required fields.
    start = gen["heal_locations"][1]
    assert start == {
        "id": "HEAL_LOCATION_URANIUM_START",
        "map": "MAP_MOKI_TOWN_PLAYERS_HOUSE_1F",
        "x": 7,
        "y": 7,
    }

    # Review copy under output/ was also written.
    review = json.loads((out / "heal_locations.json").read_text(encoding="utf-8"))
    assert [e["id"] for e in review["heal_locations"]] == [
        "HEAL_LOCATION_URANIUM_START",
        "HEAL_LOCATION_KEVLAR_TOWN_POKEMON_CENTER",
    ]


def test_output_byte_identical_across_two_runs(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    monkeypatch.setattr(ap, "SLICE_MAP_IDS", [49, 12])
    _patch_generate_entries(monkeypatch, _ENTRIES)

    fork1 = tmp_path / "fork1"
    fork2 = tmp_path / "fork2"
    _write_upstream(fork1)
    _write_upstream(fork2)

    ap.run_heal_location_pass(out, fork1, _CONSTS, dry_run=False)
    ap.run_heal_location_pass(out, fork2, _CONSTS, dry_run=False)

    text1 = (fork1 / "src" / "data" / "heal_locations.gen.json").read_text(encoding="utf-8")
    text2 = (fork2 / "src" / "data" / "heal_locations.gen.json").read_text(encoding="utf-8")
    assert text1 == text2

    # Re-running against the SAME fork (re-reading the upstream file fresh,
    # never the prior overlay) is also idempotent -- entries must not
    # accumulate across repeated runs.
    ap.run_heal_location_pass(out, fork1, _CONSTS, dry_run=False)
    text1_again = (fork1 / "src" / "data" / "heal_locations.gen.json").read_text(encoding="utf-8")
    assert text1_again == text1


def test_id_collision_with_upstream_fails_loud(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    fork = tmp_path / "fork"
    monkeypatch.setattr(ap, "SLICE_MAP_IDS", [49, 12])
    _write_upstream(fork)
    colliding = [
        hl.HealLocationEntry(
            id="HEAL_LOCATION_PETALBURG_CITY",  # already exists upstream
            map="MAP_MOKI_TOWN_PLAYERS_HOUSE_1F",
            x=7,
            y=7,
        )
    ]
    _patch_generate_entries(monkeypatch, colliding)

    with pytest.raises(ValueError, match="already exists"):
        ap.run_heal_location_pass(out, fork, _CONSTS, dry_run=False)


def test_map_outside_slice_fails_loud(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    fork = tmp_path / "fork"
    monkeypatch.setattr(ap, "SLICE_MAP_IDS", [49, 12])
    _write_upstream(fork)
    off_slice = [
        hl.HealLocationEntry(
            id="HEAL_LOCATION_SOME_OTHER_TOWN",
            map="MAP_SOME_OTHER_TOWN",  # not in _CONSTS' SLICE_MAP_IDS entries
            x=1,
            y=1,
        )
    ]
    _patch_generate_entries(monkeypatch, off_slice)

    with pytest.raises(ValueError, match="never assembles"):
        ap.run_heal_location_pass(out, fork, _CONSTS, dry_run=False)


def test_dry_run_writes_nothing(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    fork = tmp_path / "fork"
    monkeypatch.setattr(ap, "SLICE_MAP_IDS", [49, 12])
    _write_upstream(fork)
    _patch_generate_entries(monkeypatch, _ENTRIES)

    ap.run_heal_location_pass(out, fork, _CONSTS, dry_run=True)

    assert not (fork / "src" / "data" / "heal_locations.gen.json").exists()
    assert not (out / "heal_locations.json").exists()


def test_missing_upstream_file_fails_loud(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    fork = tmp_path / "fork"  # no heal_locations.json written at all
    monkeypatch.setattr(ap, "SLICE_MAP_IDS", [49, 12])
    _patch_generate_entries(monkeypatch, _ENTRIES)

    with pytest.raises(FileNotFoundError):
        ap.run_heal_location_pass(out, fork, _CONSTS, dry_run=False)
