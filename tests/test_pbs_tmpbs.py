"""Phase 2 §2.9 tests — TMPBS (`tmpbs.py`).

Per CLAUDE.md §4.6 / PHASE2_PLAN §2.9:
  * round-trip: parse → emit → regex-read MOVE_* per species → diff vs parsed
  * golden: a pinned species' TMPBS array (ORCHYNX)
  * edge: a species with an empty TMPBS list emits no block

Real-data tests are env-gated via the `uranium_data` fixture.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from rpg2gba.pbs_converter import tmpbs
from rpg2gba.pbs_converter._id_map import IdMap
from rpg2gba.pbs_converter.pokemon import parse_dexdata, parse_indexed_u16_list

pytestmark = pytest.mark.phase2

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _build(uranium_data: Path, reference_dir: Path):
    species = parse_dexdata(uranium_data / "dexdata.dat")
    n = len(species) - 1
    parsed = parse_indexed_u16_list(uranium_data / "tmpbs.dat", n)
    species_internal = tmpbs._load_id_json(reference_dir / "species_internal_names.json")
    r = tmpbs._build_resolver(IdMap(), reference_dir)
    text = tmpbs.emit_header(parsed, species_internal, r)
    return parsed, species_internal, r, text


def _block(text: str, internal: str) -> str:
    m = re.search(
        r"static const u16 sUraniumTMPBS_" + re.escape(internal) + r"\[\] = \{.*?\};",
        text,
        re.S,
    )
    assert m, f"no TMPBS block for {internal}"
    return m.group(0)


def test_roundtrip(uranium_data: Path, reference_dir: Path) -> None:
    """Each species' emitted MOVE_* count (sans terminator) matches its parsed list."""
    parsed, species_internal, r, text = _build(uranium_data, reference_dir)
    checked = 0
    for species_id, moves in enumerate(parsed):
        if species_id == 0 or not moves:
            continue
        block = _block(text, species_internal[species_id])
        got = re.findall(r"(MOVE_\w+),", block)
        assert got[-1] == "MOVE_UNAVAILABLE"
        assert len(got) - 1 == len(moves)
        checked += 1
    assert checked >= 150


def test_golden_orchynx(uranium_data: Path, reference_dir: Path) -> None:
    """ORCHYNX's TMPBS array matches the pinned fixture."""
    _parsed, _si, _r, text = _build(uranium_data, reference_dir)
    got = _block(text, "ORCHYNX") + "\n"
    assert got == (FIXTURES / "tmpbs_golden.h").read_text(encoding="utf-8")


def test_edge_empty_species_no_block(uranium_data: Path, reference_dir: Path) -> None:
    """A species with an empty TMPBS list produces no array block."""
    parsed, species_internal, _r, text = _build(uranium_data, reference_dir)
    empty_id = next(
        i for i, m in enumerate(parsed) if i != 0 and not m and i in species_internal
    )
    assert f"sUraniumTMPBS_{species_internal[empty_id]}[]" not in text
