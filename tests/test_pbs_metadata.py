"""Phase 2 §2.8 tests — map metadata + player spawn (`metadata.py`).

Per CLAUDE.md §4.6 / PHASE2_PLAN §2.8:
  * round-trip: parse global + maps → re-derive a per-map field across many maps
  * golden: the player-spawn metadata.h matches the pinned fixture
  * edge: an outdoor map with weather decodes (enum→name + chance); a map with a
    healing spot carries it

Real-data tests are env-gated via the `uranium_data` fixture.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.pbs_converter import metadata
from rpg2gba.pbs_converter._marshal import dump_dat, load_json

pytestmark = pytest.mark.phase2

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _raw(uranium_data: Path, tmp_path: Path) -> list:
    return load_json(dump_dat(uranium_data / "metadata.dat", tmp_path / "md.json"))


def test_roundtrip_maps(uranium_data: Path, tmp_path: Path) -> None:
    """Parsing yields a global spawn + a healthy number of per-map records."""
    raw = _raw(uranium_data, tmp_path)
    g = metadata.parse_global(raw)
    maps = metadata.parse_maps(raw)
    assert g.home_map > 0
    assert len(maps) >= 150
    # Every emitted record has at least one field (parse_maps drops empties).
    assert all(m.fields for m in maps)


def test_golden_spawn(uranium_data: Path, tmp_path: Path) -> None:
    """metadata.h (player spawn) matches the pinned fixture."""
    raw = _raw(uranium_data, tmp_path)
    got = metadata.emit_constants(metadata.parse_global(raw))
    assert got == (FIXTURES / "metadata_golden.h").read_text(encoding="utf-8")


def test_edge_weather_and_healing(uranium_data: Path, tmp_path: Path) -> None:
    """Map 12 is outdoor with Rain@50%; map 2 carries a [map,x,y] healing spot."""
    raw = _raw(uranium_data, tmp_path)
    by_id = {m.map_id: m.fields for m in metadata.parse_maps(raw)}
    assert by_id[12]["outdoor"] is True
    assert by_id[12]["weather"] == "Rain"
    assert isinstance(by_id[12]["chance"], int)
    assert len(by_id[2]["healing_spot"]) == 3  # [map, x, y]
