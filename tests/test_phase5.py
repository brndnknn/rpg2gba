"""Tests for the Map Walker phase5 orchestrator helpers.

Full convert_all is an integration path (writes into the fork); these cover the
isolated, pure-ish helpers — currently the stock-map-data drop (map_walker_plan
§5.5), which is the size lever behind the full-corpus walker build.
"""

from __future__ import annotations

import json
from pathlib import Path

from rpg2gba.tileset_converter import phase5


def _write_gen_layouts(fork: Path, entries: list[dict]) -> Path:
    gen = fork / "data" / "layouts" / phase5._GEN_LAYOUTS
    gen.parent.mkdir(parents=True, exist_ok=True)
    gen.write_text(
        json.dumps({"layouts_table_label": "gMapLayouts", "layouts": entries}),
        encoding="utf-8",
    )
    return gen


def test_stub_stock_layout_bins_repoints_all_entries(tmp_path: Path) -> None:
    gen = _write_gen_layouts(
        tmp_path,
        [
            {
                "id": "LAYOUT_LITTLEROOT_TOWN",
                "name": "LittlerootTown_Layout",
                "width": 20,
                "height": 20,
                "primary_tileset": "gTileset_General",
                "secondary_tileset": "gTileset_Petalburg",
                "border_filepath": "data/layouts/LittlerootTown/border.bin",
                "blockdata_filepath": "data/layouts/LittlerootTown/map.bin",
            },
            {
                "id": "LAYOUT_ROUTE101",
                "name": "Route101_Layout",
                "width": 20,
                "height": 40,
                "primary_tileset": "gTileset_General",
                "secondary_tileset": "gTileset_Fallarbor",
                "border_filepath": "data/layouts/Route101/border.bin",
                "blockdata_filepath": "data/layouts/Route101/map.bin",
            },
        ],
    )

    phase5._stub_stock_layout_bins(tmp_path, gen)

    stub = f"data/layouts/{phase5._STUB_LAYOUT_DIR}"
    data = json.loads(gen.read_text(encoding="utf-8"))
    for entry in data["layouts"]:
        assert entry["blockdata_filepath"] == f"{stub}/map.bin"
        assert entry["border_filepath"] == f"{stub}/border.bin"
        # Identity + tileset refs are preserved — the MAP_*/LAYOUT_* constants and
        # tileset symbols must keep resolving (no C reference breaks).
        assert entry["id"].startswith("LAYOUT_")
        assert entry["primary_tileset"] == "gTileset_General"

    # The tiny dummy bins actually exist on disk (they get .incbin'd at build time).
    stub_dir = tmp_path / "data" / "layouts" / phase5._STUB_LAYOUT_DIR
    assert (stub_dir / "map.bin").read_bytes() == b"\x00\x00"
    assert (stub_dir / "border.bin").read_bytes() == b"\x00" * 8


def test_stub_stock_layout_bins_is_idempotent(tmp_path: Path) -> None:
    gen = _write_gen_layouts(
        tmp_path,
        [
            {
                "id": "LAYOUT_X",
                "name": "X_Layout",
                "width": 10,
                "height": 10,
                "primary_tileset": "gTileset_General",
                "secondary_tileset": "gTileset_Petalburg",
                "border_filepath": "data/layouts/X/border.bin",
                "blockdata_filepath": "data/layouts/X/map.bin",
            }
        ],
    )
    phase5._stub_stock_layout_bins(tmp_path, gen)
    first = gen.read_text(encoding="utf-8")
    phase5._stub_stock_layout_bins(tmp_path, gen)
    assert gen.read_text(encoding="utf-8") == first


class _FakeConsts:
    def __init__(self, dir_name: str) -> None:
        self.dir_name = dir_name


class _FakeRegistry:
    def __init__(self, dirs: dict[int, str]) -> None:
        self._dirs = dirs

    def get(self, mid: int) -> _FakeConsts:
        return _FakeConsts(self._dirs[mid])

    def write_alias_header(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("// fake\n", encoding="utf-8")

    def write_walker_maps_header(self, map_ids: list[int], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("// fake\n", encoding="utf-8")


def _layout_entry(dir_name: str, tileset: str) -> dict:
    return {
        "id": f"LAYOUT_{dir_name.upper()}",
        "name": f"{dir_name}_Layout",
        "width": 10,
        "height": 10,
        "primary_tileset": tileset,
        "secondary_tileset": f"{tileset}B",
        "border_filepath": f"data/layouts/{dir_name}/border.bin",
        "blockdata_filepath": f"data/layouts/{dir_name}/map.bin",
    }


def test_assemble_fork_ignores_stale_staging_layouts(tmp_path: Path, monkeypatch) -> None:
    """A prior wider run leaves extra entries in staging layouts.json; the fork
    manifest must only gain THIS batch's layouts (a stale entry references a
    gTileset_Uranium* symbol this build never emits -> undefined ref at link)."""
    fork = tmp_path / "fork"
    porymap = tmp_path / "porymap"
    staging = tmp_path / "staging"

    # The tmp fork is not a git repo; stock detection is git-based in production.
    # RouteStock stands in for a tracked upstream dir outside every map group.
    monkeypatch.setattr(phase5, "_git_tracked_dirs", lambda f, rel: {"RouteStock"})

    # Pristine upstream manifest + map_groups.
    (fork / "data" / "layouts").mkdir(parents=True)
    (fork / "data" / "layouts" / "layouts.json").write_text(
        json.dumps({"layouts_table_label": "gMapLayouts", "layouts": []}),
        encoding="utf-8",
    )
    (fork / "data" / "maps").mkdir(parents=True)
    (fork / "data" / "maps" / "map_groups.json").write_text(
        json.dumps({"group_order": []}), encoding="utf-8"
    )

    batch_entry = _layout_entry("MokiTown", "gTileset_Uranium1032")
    stale_entry = _layout_entry("VinovilleTown", "gTileset_Uranium1121")

    # Staging: bins for the batch map + a CUMULATIVE layouts.json (batch + stale).
    (staging / "layouts" / "MokiTown").mkdir(parents=True)
    (staging / "layouts" / "MokiTown" / "map.bin").write_bytes(b"\x00\x00")
    (staging / "layouts" / "MokiTown" / "border.bin").write_bytes(b"\x00" * 8)
    (staging / "layouts" / "layouts.json").write_text(
        json.dumps({"layouts_table_label": "gMapLayouts",
                    "layouts": [batch_entry, stale_entry]}),
        encoding="utf-8",
    )
    (porymap / "maps" / "MokiTown").mkdir(parents=True)
    (porymap / "maps" / "MokiTown" / "map.json").write_text("{}", encoding="utf-8")

    # Stale generated dirs from the prior wider run (the makefile globs these),
    # plus a tracked stock dir that must survive the prune.
    (fork / "data" / "maps" / "VinovilleTown").mkdir()
    (fork / "data" / "maps" / "VinovilleTown" / "map.json").write_text("{}", encoding="utf-8")
    (fork / "data" / "layouts" / "VinovilleTown").mkdir()
    (fork / "data" / "layouts" / "VinovilleTown" / "map.bin").write_bytes(b"\x00\x00")
    (fork / "data" / "maps" / "RouteStock").mkdir()
    (fork / "data" / "maps" / "RouteStock" / "scripts.inc").write_text("x\n", encoding="utf-8")

    phase5._assemble_fork(
        [32], _FakeRegistry({32: "MokiTown"}), porymap, staging, fork,
        batch_layouts=[batch_entry],
        drop_stock_map_data=False,
    )

    gen = fork / "data" / "layouts" / phase5._GEN_LAYOUTS
    ids = [e["id"] for e in json.loads(gen.read_text(encoding="utf-8"))["layouts"]]
    assert ids == ["LAYOUT_MOKITOWN"]

    # The stale dirs are pruned; batch + tracked stock dirs survive.
    assert not (fork / "data" / "maps" / "VinovilleTown").exists()
    assert not (fork / "data" / "layouts" / "VinovilleTown").exists()
    assert (fork / "data" / "maps" / "MokiTown" / "map.json").is_file()
    assert (fork / "data" / "layouts" / "MokiTown" / "map.bin").is_file()
    assert (fork / "data" / "maps" / "RouteStock" / "scripts.inc").is_file()
