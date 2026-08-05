"""Tests for `scripts/assemble_pathfinder.py`'s per-map synthetic tileset-id
packing (CH02_TODO #4).

The walker path (`phase5.py convert_all` step 3-4) already solved the "two maps
sharing an RMXP tileset id overflow the 1024-metatile/tile budget" problem by
giving each map its own synthetic tileset id (`map_set.synth_tileset_id`). This
promotes that same scheme into the slice assembler (`run_graphics_pass` /
`run_layout_pass` / `run_fork_pass`) -- these tests cover the wiring, not the
underlying converters (`build_slice_tilesets` / `convert_layout` already have
their own test coverage).

Heavy dependencies (`sprite_pass.run_sprite_pass`, the real tileset renderer,
the real layout converter) are monkeypatched out so these run as fast, isolated
unit tests -- matching `test_phase5.py`'s approach to the same orchestrator
shape on the walker side.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import assemble_pathfinder as ap  # noqa: E402

from rpg2gba.tileset_converter.map_set import synth_tileset_id  # noqa: E402


# ---------------------------------------------------------------------------
# run_graphics_pass: synthetic tileset_id + source_tileset_of round-trip
# ---------------------------------------------------------------------------

def test_run_graphics_pass_assigns_synthetic_ids_and_source_tileset_of(
    tmp_path: Path, monkeypatch,
) -> None:
    """Two maps sharing an RMXP tileset id (like Map032/Map033 on RMXP 22) must
    reach `build_slice_tilesets` with DISTINCT synthetic tileset_ids, and the
    `source_tileset_of` callback passed alongside must resolve each synthetic id
    back to the correct real RMXP id -- exactly what phase5's walker path does."""
    out = tmp_path / "out"
    (out / "maps").mkdir(parents=True)
    (out / "maps" / "Map032.json").write_text(
        json.dumps({"tileset_id": 22, "tiles": []}), encoding="utf-8"
    )
    (out / "maps" / "Map033.json").write_text(
        json.dumps({"tileset_id": 22, "tiles": []}), encoding="utf-8"
    )

    monkeypatch.setattr(ap, "SLICE_MAP_IDS", [32, 33])
    monkeypatch.setattr(ap, "WARP_OVERRIDES", {32: set(), 33: set()})

    captured: dict = {}

    def fake_build_slice_tilesets(maps, warp_coords, **kwargs):
        captured["maps"] = maps
        captured["source_tileset_of"] = kwargs["source_tileset_of"]
        return {}

    import rpg2gba.tileset_converter.graphics.build_slice_tilesets as bst_mod
    monkeypatch.setattr(bst_mod, "build_slice_tilesets", fake_build_slice_tilesets)

    ap.run_graphics_pass(out, tmp_path / "fork", dry_run=True)

    maps = dict(captured["maps"])  # {map_id: map_json}
    assert set(maps.keys()) == {32, 33}

    synth_32 = synth_tileset_id(32)
    synth_33 = synth_tileset_id(33)
    assert maps[32]["tileset_id"] == synth_32
    assert maps[33]["tileset_id"] == synth_33
    # Distinct synthetic ids -- this is the whole point: pooling on the shared
    # real id (22) is what overflowed the 1024 budget.
    assert synth_32 != synth_33

    resolve = captured["source_tileset_of"]
    assert resolve(synth_32) == 22
    assert resolve(synth_33) == 22


def test_run_graphics_pass_leaves_original_map_json_untouched(
    tmp_path: Path, monkeypatch,
) -> None:
    """The synth-id rewrite is a shallow copy -- the on-disk Map032.json's
    tileset_id must never be mutated (idempotence, CLAUDE.md §4.2)."""
    out = tmp_path / "out"
    (out / "maps").mkdir(parents=True)
    (out / "maps" / "Map032.json").write_text(
        json.dumps({"tileset_id": 22, "tiles": []}), encoding="utf-8"
    )

    monkeypatch.setattr(ap, "SLICE_MAP_IDS", [32])
    monkeypatch.setattr(ap, "WARP_OVERRIDES", {32: set()})

    import rpg2gba.tileset_converter.graphics.build_slice_tilesets as bst_mod
    monkeypatch.setattr(bst_mod, "build_slice_tilesets", lambda *a, **kw: {})

    ap.run_graphics_pass(out, tmp_path / "fork", dry_run=True)

    on_disk = json.loads((out / "maps" / "Map032.json").read_text(encoding="utf-8"))
    assert on_disk["tileset_id"] == 22


# ---------------------------------------------------------------------------
# run_layout_pass: matching synthetic tileset_key
# ---------------------------------------------------------------------------

class _FakeLayout:
    def __init__(self, name: str, layout_const: str) -> None:
        self.name = name
        self.layout_const = layout_const
        self.blocks = []

    def to_layouts_entry(self) -> dict:
        return {"id": self.layout_const, "name": f"{self.name}_Layout"}

    def write(self, staging_dir: Path) -> None:
        pass


def test_run_layout_pass_uses_matching_synthetic_tileset_key(
    tmp_path: Path, monkeypatch,
) -> None:
    out = tmp_path / "out"
    (out / "maps").mkdir(parents=True)
    for mid in (32, 33):
        (out / "maps" / f"Map{mid:03d}.json").write_text(
            json.dumps({"tileset_id": 22, "tiles": []}), encoding="utf-8"
        )

    consts = {
        "32": {"dir_name": "MokiTown", "layout_const": "LAYOUT_MOKITOWN"},
        "33": {"dir_name": "Route01", "layout_const": "LAYOUT_ROUTE01"},
    }

    monkeypatch.setattr(ap, "SLICE_MAP_IDS", [32, 33])
    monkeypatch.setattr(ap, "WARP_OVERRIDES", {32: set(), 33: set()})
    monkeypatch.setattr(ap, "WALKABLE_OVERRIDES", {})

    import rpg2gba.tileset_converter.metadata_wiring as mw_mod
    monkeypatch.setattr(mw_mod, "collect_through_block_cells", lambda map_json: set())

    import rpg2gba.tileset_converter.tile_map as tm_mod
    monkeypatch.setattr(tm_mod, "load_tile_map", lambda *a, **kw: object())

    captured_keys: dict[int, int] = {}

    import rpg2gba.tileset_converter.layout as layout_mod

    def fake_convert_layout(map_json, tile_map, *, name, layout_const, tileset_key=None, **kw):
        captured_keys[layout_const] = tileset_key
        return _FakeLayout(name, layout_const)

    monkeypatch.setattr(layout_mod, "convert_layout", fake_convert_layout)

    entries = ap.run_layout_pass(out, consts, tmp_path / "staging", dry_run=True)

    assert captured_keys["LAYOUT_MOKITOWN"] == synth_tileset_id(32)
    assert captured_keys["LAYOUT_ROUTE01"] == synth_tileset_id(33)
    assert [e["id"] for e in entries] == ["LAYOUT_MOKITOWN", "LAYOUT_ROUTE01"]


# ---------------------------------------------------------------------------
# _resolve_batch_layout_entries: no cumulative-staging leak (run_fork_pass)
# ---------------------------------------------------------------------------

def _entry(layout_const: str) -> dict:
    return {"id": layout_const, "name": layout_const.title()}


def test_resolve_batch_layout_entries_prefers_the_passed_batch(tmp_path: Path) -> None:
    consts = {"32": {"layout_const": "LAYOUT_MOKITOWN"}}
    batch = [_entry("LAYOUT_MOKITOWN")]
    result = ap._resolve_batch_layout_entries(
        consts, [32], batch, tmp_path / "unused.json",
    )
    assert result is batch


def test_resolve_batch_layout_entries_filters_cumulative_to_current_map_ids(
    tmp_path: Path,
) -> None:
    """A prior wider run leaves extra (stale) entries in the cumulative staging
    file -- when this run has no batch of its own (--skip-layout), only the
    entries for the CURRENT map set may be used, never the whole file."""
    staging_layouts_json = tmp_path / "layouts.json"
    staging_layouts_json.write_text(
        json.dumps({
            "layouts": [
                _entry("LAYOUT_MOKITOWN"),
                _entry("LAYOUT_ROUTE01"),       # stale: not in this run's map set
                _entry("LAYOUT_VINOVILLETOWN"),  # stale: not in this run's map set
            ]
        }),
        encoding="utf-8",
    )
    consts = {"32": {"layout_const": "LAYOUT_MOKITOWN"}}

    result = ap._resolve_batch_layout_entries(
        consts, [32], None, staging_layouts_json,
    )

    assert [e["id"] for e in result] == ["LAYOUT_MOKITOWN"]


def test_resolve_batch_layout_entries_fails_loud_when_staging_missing(
    tmp_path: Path,
) -> None:
    consts = {"32": {"layout_const": "LAYOUT_MOKITOWN"}}
    with pytest.raises(FileNotFoundError):
        ap._resolve_batch_layout_entries(
            consts, [32], None, tmp_path / "does_not_exist.json",
        )


def test_resolve_batch_layout_entries_fails_loud_when_entry_missing(
    tmp_path: Path,
) -> None:
    staging_layouts_json = tmp_path / "layouts.json"
    staging_layouts_json.write_text(
        json.dumps({"layouts": [_entry("LAYOUT_ROUTE01")]}), encoding="utf-8",
    )
    consts = {"32": {"layout_const": "LAYOUT_MOKITOWN"}}

    with pytest.raises(KeyError):
        ap._resolve_batch_layout_entries(
            consts, [32], None, staging_layouts_json,
        )
