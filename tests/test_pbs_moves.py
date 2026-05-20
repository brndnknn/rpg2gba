"""Phase 2 §2.2 tests — moves (`moves.py`).

Per CLAUDE.md §4.6 / PHASE2_PLAN.md §2.2:
  * round-trip: parse → emit C → regex-read back → diff numeric fields
  * golden: pinned snapshot (MOVE_TACKLE + the Nuclear move MOVE_ATOMIC_PUNCH)
  * edge: every move emits EFFECT_PLACEHOLDER and its raw function code is in
    the Phase 6 worklist (effects are deliberately deferred)
  * edge: a Nuclear-type move is flagged needs_engine against the fork

All are env-gated via the `uranium_data` fixture (skip if the source is absent).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from rpg2gba.pbs_converter import moves
from rpg2gba.pbs_converter._id_map import IdMap

pytestmark = pytest.mark.phase2

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _build(uranium_data: Path, reference_dir: Path) -> tuple[list, moves._MoveResolver]:
    parsed = moves.parse(uranium_data / "moves.dat")
    moves.attach_internal_names(
        parsed, moves._load_id_json(reference_dir / "move_internal_names.json")
    )
    resolver = moves._build_resolver(IdMap(), reference_dir)
    for m in parsed:
        if m is not None:
            resolver.move_constant(m.id)
    return parsed, resolver


def _entry(c_text: str, const: str) -> str:
    m = re.search(r"    \[" + re.escape(const) + r"\] =\n    \{.*?\n    \},", c_text, re.S)
    assert m, f"{const} entry not found in emitted moves_info.h"
    return m.group(0)


def test_roundtrip_numeric(uranium_data: Path, reference_dir: Path) -> None:
    """power/accuracy/pp/priority emitted into moves_info.h re-read to parsed values."""
    parsed, resolver = _build(uranium_data, reference_dir)
    c_text = moves.emit_moves_info(parsed, resolver)
    checked = 0
    for m in parsed:
        if m is None:
            continue
        entry = _entry(c_text, resolver.move_constant(m.id))
        for field, expected in (
            ("power", m.power),
            ("accuracy", m.accuracy),
            ("pp", m.pp),
            ("priority", m.priority),
        ):
            hit = re.search(rf"\.{field} = (-?\d+),", entry)
            assert hit and int(hit.group(1)) == expected, f"{m.internal_name}.{field}"
        checked += 1
    assert checked >= 600


def test_golden_tackle_atomic_punch(uranium_data: Path, reference_dir: Path) -> None:
    """Pinned output for a vanilla move + a Nuclear (Uranium-original) move."""
    parsed, resolver = _build(uranium_data, reference_dir)
    c_text = moves.emit_moves_info(parsed, resolver)
    got = _entry(c_text, "MOVE_TACKLE") + "\n" + _entry(c_text, "MOVE_ATOMIC_PUNCH") + "\n"
    expected = (FIXTURES / "moves_golden.h").read_text(encoding="utf-8")
    assert got == expected


def test_edge_effects_placeholdered_and_worklisted(
    uranium_data: Path, reference_dir: Path
) -> None:
    """Effects are deferred: every move is EFFECT_PLACEHOLDER, codes kept losslessly."""
    parsed, resolver = _build(uranium_data, reference_dir)
    c_text = moves.emit_moves_info(parsed, resolver)
    # No move resolves to a real EFFECT_* in Phase 2.
    assert ".effect = EFFECT_PLACEHOLDER" in c_text
    assert not re.search(r"\.effect = EFFECT_(?!PLACEHOLDER)", c_text)
    # The worklist round-trips the raw function code for a known move.
    tackle = next(m for m in parsed if m is not None and m.internal_name == "TACKLE")
    const = resolver.move_constant(tackle.id)
    worklist = {
        resolver.move_constant(m.id): m.function_code
        for m in parsed
        if m is not None
    }
    assert worklist[const] == tackle.function_code


def test_edge_nuclear_move_needs_engine(
    uranium_data: Path, reference_dir: Path, fork_path: Path | None
) -> None:
    """A Nuclear-type move resolves to needs_engine against the fork."""
    if fork_path is None:
        pytest.skip("RPG2GBA_POKEEMERALD not set; can't validate needs_engine")
    parsed = moves.parse(uranium_data / "moves.dat")
    moves.attach_internal_names(
        parsed, moves._load_id_json(reference_dir / "move_internal_names.json")
    )
    id_map = IdMap()
    resolver = moves._build_resolver(id_map, reference_dir)
    nuke = next(
        m for m in parsed if m is not None and m.type_index == moves.NUCLEAR_TYPE_INDEX
    )
    const = resolver.move_constant(nuke.id)
    assert const in id_map.needs_engine["moves"]
