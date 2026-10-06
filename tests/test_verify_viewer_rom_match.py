"""Grouping tests for scripts/verify_viewer_rom_match.py (per-map tileset scheme).

The script is not a package module, so it is loaded by path. These tests cover
the cheap, pure parts: one group per map keyed by the synthetic tileset id, the
synth -> real table, stair/seam cell merging, overlay cross-check, and Mode B's
viewer-vs-ROM comparison on synthetic data. The full oracle needs the built engine and is run by hand.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from rpg2gba.tileset_converter.map_set import synth_tileset_id

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "verify_viewer_rom_match.py"


@pytest.fixture(scope="module")
def oracle():
    spec = importlib.util.spec_from_file_location("verify_viewer_rom_match", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # @dataclass resolves annotations via sys.modules
    try:
        spec.loader.exec_module(mod)
        yield mod
    finally:
        sys.modules.pop(spec.name, None)


def _write_map(out_dir: Path, map_id: int, tileset_id: int) -> None:
    maps = out_dir / "maps"
    maps.mkdir(parents=True, exist_ok=True)
    (maps / f"Map{map_id:03d}.json").write_text(
        json.dumps({"tileset_id": tileset_id, "width": 1, "height": 1, "data": []}),
        encoding="utf-8",
    )


def test_one_group_per_map_even_on_shared_real_tileset(oracle, tmp_path, monkeypatch):
    # Map031 and Map032 share RMXP tileset 22: the old scheme pooled them.
    _write_map(tmp_path, 31, 22)
    _write_map(tmp_path, 32, 22)
    _write_map(tmp_path, 49, 19)
    (tmp_path / "connections.json").write_text("[]", encoding="utf-8")
    import rpg2gba.tileset_converter.metadata_wiring as mw

    monkeypatch.setattr(mw, "collect_stair_behavior_cells", lambda mj: {(1, 2): "stair"})
    seam = {32: {(3, 4): "arrow"}}
    maps, synth_to_real, stair_cells = oracle.per_map_inputs(tmp_path, [31, 32, 49], seam)

    assert [m for m, _ in maps] == [31, 32, 49]
    assert [j["tileset_id"] for _, j in maps] == [synth_tileset_id(m) for m in (31, 32, 49)]
    assert len({j["tileset_id"] for _, j in maps}) == 3
    assert synth_to_real == {1031: 22, 1032: 22, 1049: 19}
    assert stair_cells[31] == {(1, 2): "stair"}
    assert stair_cells[32] == {(1, 2): "stair", (3, 4): "arrow"}


def test_connected_maps_share_one_group(oracle, tmp_path):
    _write_map(tmp_path, 31, 22)
    _write_map(tmp_path, 35, 22)
    (tmp_path / "connections.json").write_text(
        json.dumps([[31, "N", 11, 35, "S", 0]]), encoding="utf-8")
    maps, synth_to_real, _ = oracle.per_map_inputs(tmp_path, [31, 35], {})
    assert [j["tileset_id"] for _, j in maps] == [synth_tileset_id(31)] * 2
    assert synth_to_real == {1031: 22}


def test_cross_check_overlay(oracle):
    fresh = {"tiles": {"1031": {"a": {"metatile": 0}}}, "source_tilesets": {"1031": 22}}
    assert oracle._cross_check_overlay(fresh, json.loads(json.dumps(fresh)), 1031) == []
    stale = {"tiles": {"1031": {"a": {"metatile": 1}}}, "source_tilesets": {"1031": 22}}
    problems = oracle._cross_check_overlay(fresh, stale, 1031)
    assert len(problems) == 1 and problems[0].startswith("tiles:")
    assert oracle._cross_check_overlay(fresh, {}, 1031) != []


def _state(colkeys, postquant, pool_key_to_idx):
    from types import SimpleNamespace

    return SimpleNamespace(
        colkeys_sorted=colkeys, metatile_imgs_postquant=postquant,
        pool_key_to_idx=pool_key_to_idx,
    )


class _FakeRom:
    """decode_metatile(i) -> (bottom, top) solid-colour 16x16 RGBA."""

    def __init__(self, colours):
        self.colours = colours

    def decode_metatile(self, i):
        import numpy as np

        b = np.zeros((16, 16, 4), dtype=np.uint8)
        t = np.zeros((16, 16, 4), dtype=np.uint8)
        b[...] = (*self.colours[i], 255)
        return b, t


def test_compare_viewer_to_rom_uses_pool_index_and_counts_px(oracle):
    import numpy as np

    def solid(c):
        a = np.zeros((16, 16, 4), dtype=np.uint8)
        a[...] = (*c, 255)
        return a

    zero = np.zeros((16, 16, 4), dtype=np.uint8)
    ck_a, ck_b = ((1, 2),), ((3, 4),)
    # colkey idx 0 is the empty column (skipped); ROM index = pool index, not colkey idx.
    st = _state([(), ck_a, ck_b], [None, (solid((8, 8, 8)), zero), (solid((9, 9, 9)), zero)],
                {ck_a: 0, ck_b: 1})
    rom = _FakeRom([(8, 8, 8), (9, 9, 9)])
    assert oracle.compare_viewer_to_rom(31, st, rom, "t") == (2, 0, 0)

    bad = _FakeRom([(8, 8, 8), (10, 9, 9)])  # ck_b's bottom differs on all 256 px
    assert oracle.compare_viewer_to_rom(31, st, bad, "t") == (2, 1, 256)


def test_compare_viewer_to_rom_goes_through_dedup_remap(oracle):
    import numpy as np

    from rpg2gba.tileset_converter.tile_map import serialize_column_key

    def solid(c):
        a = np.zeros((16, 16, 4), dtype=np.uint8)
        a[...] = (*c, 255)
        return a

    zero = np.zeros((16, 16, 4), dtype=np.uint8)
    ck_a, ck_b, ck_c = ((1, 2),), ((3, 4),), ((5, 6),)
    # Pool idx 0/1/2; the ROM folded a and c into ONE metatile (index 0) and
    # renumbered b to 1, so pool index != ROM index for b and c.
    st = _state([ck_a, ck_b, ck_c],
                [(solid((8, 8, 8)), zero), (solid((9, 9, 9)), zero), (solid((8, 8, 8)), zero)],
                {ck_a: 0, ck_b: 1, ck_c: 2})
    rom = _FakeRom([(8, 8, 8), (9, 9, 9)])
    committed = {"tiles": {"1031": {
        serialize_column_key(ck_a): {"metatile": 0},
        serialize_column_key(ck_b): {"metatile": 1},
        serialize_column_key(ck_c): {"metatile": 0},
    }}}
    idx = oracle.rom_index_table(committed, 1031)
    assert oracle.compare_viewer_to_rom(31, st, rom, "t", idx) == (3, 0, 0)
    # Without the remap, ck_c would be compared at (non-existent) ROM index 2.
    with pytest.raises(IndexError):
        oracle.compare_viewer_to_rom(31, st, rom, "t")
    # A column the overlay does not know is a hard error, not a silent skip.
    with pytest.raises(KeyError):
        oracle.compare_viewer_to_rom(31, st, rom, "t", {})
    assert oracle.rom_index_table(committed, 9999) == {}
