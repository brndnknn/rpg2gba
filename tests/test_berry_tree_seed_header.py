"""Tests for `scripts/assemble_pathfinder.py`'s S8d berry-tree seed-table pass
(`run_berry_tree_pass`).

Covers: only `planted: true` rows are emitted; a bare-soil (`planted: false`)
row is omitted; `planted: true` with a null `berry_item` fails loud;
a nonexistent fork constant fails loud; output is byte-identical across two
runs (CLAUDE.md §4.2). Mirrors `test_assemble_pathfinder_tileset_packing.py`'s
approach: import the script as a module via sys.path, monkeypatch
`SLICE_MAP_IDS` and the fork-index lookup so these run as fast, isolated
unit tests with no real git/fork dependency.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import assemble_pathfinder as ap  # noqa: E402

import rpg2gba.conversion_agent.fork_index as fork_index_mod  # noqa: E402


def _write_template_fields(out: Path, map_id: int, events: dict) -> None:
    path = out / "scripts" / f"Map{map_id:03d}.template_fields.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"events": events}), encoding="utf-8")


def _patch_fork_index(monkeypatch, constants: set[str]) -> None:
    fake_index = SimpleNamespace(constants=constants)
    monkeypatch.setattr(fork_index_mod, "load_or_build", lambda *a, **kw: fake_index)


def test_only_planted_rows_emitted_and_bare_soil_omitted(
    tmp_path: Path, monkeypatch
) -> None:
    out = tmp_path / "out"
    monkeypatch.setattr(ap, "SLICE_MAP_IDS", [33])
    _write_template_fields(
        out,
        33,
        {
            "100": {"berry_item": "ITEM_ORAN_BERRY", "kind": "berry_tree", "planted": True},
            "101": {"berry_item": None, "kind": "berry_tree", "planted": False},
            "102": {"berry_item": "ITEM_ORAN_BERRY", "kind": "berry_tree", "planted": True},
        },
    )
    _patch_fork_index(monkeypatch, {"ITEM_ORAN_BERRY"})

    fork = tmp_path / "fork"
    ap.run_berry_tree_pass(out, fork, dry_run=False)

    text = (fork / "data" / "scripts" / "uranium_berry_trees.h").read_text(encoding="utf-8")
    assert "URANIUM_BERRY_TREE_SEED_COUNT 2" in text
    assert text.count("X(") == 2
    assert "ITEM_ORAN_BERRY" in text
    # Bare-soil event 101 never got assigned a row (only 2 X() lines above, for
    # the 2 planted ids — the assigned tree id for 101 must not appear either).
    from rpg2gba.tileset_converter.metadata_wiring import assign_berry_tree_ids

    ids = assign_berry_tree_ids(
        {33: {100: {"kind": "berry_tree"}, 101: {"kind": "berry_tree"}, 102: {"kind": "berry_tree"}}}
    )
    bare_soil_id = ids[(33, 101)]
    assert f"X({bare_soil_id}," not in text


def test_planted_true_with_null_berry_item_fails_loud(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    monkeypatch.setattr(ap, "SLICE_MAP_IDS", [33])
    _write_template_fields(
        out,
        33,
        {"100": {"berry_item": None, "kind": "berry_tree", "planted": True}},
    )
    _patch_fork_index(monkeypatch, set())

    with pytest.raises(ValueError, match="contradictory sidecar"):
        ap.run_berry_tree_pass(out, tmp_path / "fork", dry_run=False)


def test_nonexistent_fork_constant_fails_loud(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    monkeypatch.setattr(ap, "SLICE_MAP_IDS", [33])
    _write_template_fields(
        out,
        33,
        {"100": {"berry_item": "ITEM_MADE_UP_BERRY", "kind": "berry_tree", "planted": True}},
    )
    # Fork index does NOT contain ITEM_MADE_UP_BERRY.
    _patch_fork_index(monkeypatch, {"ITEM_ORAN_BERRY"})

    with pytest.raises(ValueError, match="ITEM_MADE_UP_BERRY"):
        ap.run_berry_tree_pass(out, tmp_path / "fork", dry_run=False)


def test_output_byte_identical_across_two_runs(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    monkeypatch.setattr(ap, "SLICE_MAP_IDS", [33, 32])
    _write_template_fields(
        out,
        33,
        {
            "100": {"berry_item": "ITEM_ORAN_BERRY", "kind": "berry_tree", "planted": True},
            "101": {"berry_item": None, "kind": "berry_tree", "planted": False},
            "102": {"berry_item": "ITEM_ORAN_BERRY", "kind": "berry_tree", "planted": True},
        },
    )
    _write_template_fields(
        out,
        32,
        {"5": {"berry_item": "ITEM_PECHA_BERRY", "kind": "berry_tree", "planted": True}},
    )
    _patch_fork_index(monkeypatch, {"ITEM_ORAN_BERRY", "ITEM_PECHA_BERRY"})

    fork1 = tmp_path / "fork1"
    fork2 = tmp_path / "fork2"
    ap.run_berry_tree_pass(out, fork1, dry_run=False)
    ap.run_berry_tree_pass(out, fork2, dry_run=False)

    text1 = (fork1 / "data" / "scripts" / "uranium_berry_trees.h").read_text(encoding="utf-8")
    text2 = (fork2 / "data" / "scripts" / "uranium_berry_trees.h").read_text(encoding="utf-8")
    assert text1 == text2


def test_missing_template_fields_sidecar_fails_loud(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    monkeypatch.setattr(ap, "SLICE_MAP_IDS", [33])
    # No sidecar written at all.
    with pytest.raises(FileNotFoundError):
        ap.run_berry_tree_pass(out, tmp_path / "fork", dry_run=False)


def test_dry_run_does_not_write(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    monkeypatch.setattr(ap, "SLICE_MAP_IDS", [33])
    _write_template_fields(
        out,
        33,
        {"100": {"berry_item": "ITEM_ORAN_BERRY", "kind": "berry_tree", "planted": True}},
    )
    _patch_fork_index(monkeypatch, {"ITEM_ORAN_BERRY"})

    fork = tmp_path / "fork"
    ap.run_berry_tree_pass(out, fork, dry_run=True)
    assert not (fork / "data" / "scripts" / "uranium_berry_trees.h").exists()
