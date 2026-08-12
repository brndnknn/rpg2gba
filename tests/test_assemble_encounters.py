"""Tests for `scripts/assemble_pathfinder.py`'s wild-encounter staging pass
(S8b4, `run_encounters_pass`).

Wild encounter DATA is already fully converted (`pbs_converter/encounters.py`
output) and the grass metatile behavior already works; the missing link is
that nothing ever wired the per-map tables into the fork's
`gWildMonHeaders` group, so `GetCurrentMapWildMonHeaderId`
(`engine/src/wild_encounter.c:379-404`) finds no row and silently returns
`HEADER_NONE`. This suite covers the wiring `assemble_pathfinder.py` owns:

  * an end-to-end run against a small fake fork tree + fake output tree,
    exercising the real `rpg2gba.tileset_converter.wild_encounters` module
    (`build_encounter_entries` / `upsert_encounters`) -- not mocked, since the
    module's contract is known and landed on disk during this session
  * `--dry-run` writes nothing to the fork's `wild_encounters.json`
  * `--skip-encounters` skips the pass entirely (dispatch wiring in `main()`)
  * the known-species union: a species present only in the staged species
    manifest, and a species present only in the fork's own constants (via
    `fork_index`), are both accepted

Heavy/global dependencies (`fork_index.load_or_build`, which normally shells
out to git against the real `engine/` tree) are monkeypatched to a fake index
so these run as fast, isolated unit tests against synthetic fork/output trees
-- matching `test_assemble_pathfinder_tileset_packing.py`'s approach to the
same orchestrator shape.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import assemble_pathfinder as ap  # noqa: E402

import rpg2gba.conversion_agent.fork_index as fi_mod  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _fork_wild_encounters_json() -> dict:
    """Minimal fork `src/data/wild_encounters.json` shape: one gWildMonHeaders
    group declaring slot counts for all four field kinds (mirrors the real
    fork's engine/src/data/wild_encounters.json contract that
    wild_encounters.py reads)."""
    return {
        "wild_encounter_groups": [
            {
                "label": "gWildMonHeaders",
                "for_maps": True,
                "fields": [
                    {"type": "land_mons", "encounter_rates": [20]},
                    {"type": "water_mons", "encounter_rates": [20]},
                    {"type": "rock_smash_mons", "encounter_rates": [20]},
                    {
                        "type": "fishing_mons",
                        "encounter_rates": [20, 20, 20],
                        "groups": {
                            "old_rod": [0],
                            "good_rod": [1],
                            "super_rod": [2],
                        },
                    },
                ],
                "encounters": [],
            }
        ]
    }


def _make_fork(tmp_path: Path) -> Path:
    fork = tmp_path / "fork"
    dest = fork / "src" / "data" / "wild_encounters.json"
    dest.parent.mkdir(parents=True)
    dest.write_text(json.dumps(_fork_wild_encounters_json(), indent=2) + "\n", encoding="utf-8")
    return fork


def _make_out(tmp_path: Path, *, maps: dict) -> Path:
    """A fake `out/uranium-build`-shaped tree: species manifest (staging one
    species, SPECIES_FOO) + intermediate/wild_encounters.json (`maps` keyed by
    Uranium map id string)."""
    out = tmp_path / "out"
    (out / "species").mkdir(parents=True)
    (out / "species" / "species_manifest.json").write_text(
        json.dumps({"species": [{"species_constant": "SPECIES_FOO"}]}), encoding="utf-8"
    )
    (out / "intermediate").mkdir(parents=True)
    (out / "intermediate" / "wild_encounters.json").write_text(
        json.dumps({"maps": maps}), encoding="utf-8"
    )
    return out


def _land_table(species: str) -> dict:
    return {"land_mons": {"encounter_rate": 20, "mons": [{"species": species, "min_level": 3, "max_level": 5}]}}


class _FakeForkIndex:
    """Stand-in for `conversion_agent.fork_index.ForkIndex` -- only the
    `.constants` attribute `run_encounters_pass` reads."""

    def __init__(self, constants: set[str]) -> None:
        self.constants = constants


# ---------------------------------------------------------------------------
# End-to-end + species union
# ---------------------------------------------------------------------------

def test_run_encounters_pass_end_to_end_writes_expected_entries(
    tmp_path: Path, monkeypatch,
) -> None:
    """Two slice maps: one whose only encounter species is staged in the
    species manifest (SPECIES_FOO), one whose only species is a vanilla
    species known only via the fork constants index (SPECIES_BAR) -- both
    must be accepted (the known-species union) and both entries land in the
    fork's `gWildMonHeaders.encounters`."""
    fork = _make_fork(tmp_path)
    out = _make_out(
        tmp_path,
        maps={
            "32": _land_table("SPECIES_FOO"),
            "33": _land_table("SPECIES_BAR"),
        },
    )
    consts = {
        "32": {"map_const": "MAP_MOKI_TOWN"},
        "33": {"map_const": "MAP_ROUTE_01"},
    }

    monkeypatch.setattr(ap, "SLICE_MAP_IDS", [32, 33])
    monkeypatch.setattr(
        fi_mod, "load_or_build", lambda *a, **kw: _FakeForkIndex({"SPECIES_BAR", "SPECIES_UNRELATED"})
    )

    base_before = (fork / "src" / "data" / "wild_encounters.json").read_text(encoding="utf-8")

    ap.run_encounters_pass(out, fork, consts, dry_run=False)

    overlay_path = fork / "src" / "data" / "wild_encounters.gen.json"
    assert overlay_path.is_file()
    # The committed base is never touched -- only the overlay is written.
    assert (fork / "src" / "data" / "wild_encounters.json").read_text(encoding="utf-8") == base_before

    written = json.loads(overlay_path.read_text(encoding="utf-8"))
    group = written["wild_encounter_groups"][0]
    by_map = {e["map"]: e for e in group["encounters"]}
    assert set(by_map) == {"MAP_MOKI_TOWN", "MAP_ROUTE_01"}
    assert by_map["MAP_MOKI_TOWN"]["land_mons"]["mons"][0]["species"] == "SPECIES_FOO"
    assert by_map["MAP_ROUTE_01"]["land_mons"]["mons"][0]["species"] == "SPECIES_BAR"
    assert by_map["MAP_MOKI_TOWN"]["base_label"] == "gMokiTown"
    assert by_map["MAP_ROUTE_01"]["base_label"] == "gRoute01"


def test_run_encounters_pass_skips_maps_with_no_table(tmp_path: Path, monkeypatch) -> None:
    """A slice map with no entry in intermediate/wild_encounters.json is
    silently skipped (not an error) -- the log-only "no table" case."""
    fork = _make_fork(tmp_path)
    out = _make_out(tmp_path, maps={"32": _land_table("SPECIES_FOO")})
    consts = {"32": {"map_const": "MAP_MOKI_TOWN"}, "33": {"map_const": "MAP_ROUTE_01"}}

    monkeypatch.setattr(ap, "SLICE_MAP_IDS", [32, 33])
    monkeypatch.setattr(fi_mod, "load_or_build", lambda *a, **kw: _FakeForkIndex(set()))

    ap.run_encounters_pass(out, fork, consts, dry_run=False)

    overlay_path = fork / "src" / "data" / "wild_encounters.gen.json"
    written = json.loads(overlay_path.read_text(encoding="utf-8"))
    group = written["wild_encounter_groups"][0]
    assert [e["map"] for e in group["encounters"]] == ["MAP_MOKI_TOWN"]


def test_run_encounters_pass_fails_loud_without_species_manifest(
    tmp_path: Path, monkeypatch,
) -> None:
    fork = _make_fork(tmp_path)
    out = tmp_path / "out"  # no species/ subdir at all
    (out / "intermediate").mkdir(parents=True)
    (out / "intermediate" / "wild_encounters.json").write_text(
        json.dumps({"maps": {}}), encoding="utf-8"
    )
    monkeypatch.setattr(ap, "SLICE_MAP_IDS", [32])
    with pytest.raises(FileNotFoundError):
        ap.run_encounters_pass(out, fork, {}, dry_run=False)


# ---------------------------------------------------------------------------
# --dry-run writes nothing
# ---------------------------------------------------------------------------

def test_run_encounters_pass_dry_run_writes_nothing(tmp_path: Path, monkeypatch) -> None:
    fork = _make_fork(tmp_path)
    out = _make_out(tmp_path, maps={"32": _land_table("SPECIES_FOO")})
    consts = {"32": {"map_const": "MAP_MOKI_TOWN"}}
    dest = fork / "src" / "data" / "wild_encounters.json"
    before = dest.read_text(encoding="utf-8")
    overlay_path = fork / "src" / "data" / "wild_encounters.gen.json"

    monkeypatch.setattr(ap, "SLICE_MAP_IDS", [32])
    monkeypatch.setattr(fi_mod, "load_or_build", lambda *a, **kw: _FakeForkIndex(set()))

    ap.run_encounters_pass(out, fork, consts, dry_run=True)

    after = dest.read_text(encoding="utf-8")
    assert after == before
    assert not overlay_path.exists()  # no overlay file created at all


# ---------------------------------------------------------------------------
# --skip-encounters / dispatch wiring in main()
# ---------------------------------------------------------------------------

def _stub_out_other_passes(monkeypatch) -> None:
    monkeypatch.setattr(ap, "run_graphics_pass", lambda *a, **kw: None)
    monkeypatch.setattr(ap, "run_layout_pass", lambda *a, **kw: None)
    monkeypatch.setattr(ap, "run_fork_pass", lambda *a, **kw: None)
    monkeypatch.setattr(ap, "run_berry_tree_pass", lambda *a, **kw: None)
    monkeypatch.setattr(ap, "run_rematch_pass", lambda *a, **kw: None)


def _prep_main_env(tmp_path: Path, monkeypatch) -> None:
    fork = tmp_path / "fork"
    fork.mkdir()
    out_root = tmp_path / "output"
    (out_root / "uranium-build" / "porymap").mkdir(parents=True)
    (out_root / "uranium-build" / "porymap" / "map_constants.json").write_text(
        "{}", encoding="utf-8"
    )
    monkeypatch.setenv("RPG2GBA_POKEEMERALD", str(fork))
    monkeypatch.setenv("RPG2GBA_OUTPUT", str(out_root))


def test_skip_encounters_flag_prevents_dispatch(tmp_path: Path, monkeypatch) -> None:
    _prep_main_env(tmp_path, monkeypatch)
    _stub_out_other_passes(monkeypatch)
    called = {"hit": False}
    monkeypatch.setattr(ap, "run_encounters_pass", lambda *a, **kw: called.__setitem__("hit", True))
    monkeypatch.setattr(
        sys, "argv",
        ["assemble_pathfinder.py", "--dry-run", "--skip-graphics", "--skip-layout",
         "--skip-species", "--skip-trainers", "--skip-encounters"],
    )

    rc = ap.main()

    assert rc == 0
    assert called["hit"] is False


def test_encounters_pass_dispatched_by_default(tmp_path: Path, monkeypatch) -> None:
    """Without --skip-encounters, the pass runs (dispatched after the
    species/trainer staging block, before run_fork_pass -- see
    `run_encounters_pass`'s docstring for the ordering rationale)."""
    _prep_main_env(tmp_path, monkeypatch)
    _stub_out_other_passes(monkeypatch)
    called = {"hit": False}
    monkeypatch.setattr(ap, "run_encounters_pass", lambda *a, **kw: called.__setitem__("hit", True))
    monkeypatch.setattr(
        sys, "argv",
        ["assemble_pathfinder.py", "--dry-run", "--skip-graphics", "--skip-layout",
         "--skip-species", "--skip-trainers"],
    )

    rc = ap.main()

    assert rc == 0
    assert called["hit"] is True
