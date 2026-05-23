"""Phase 2 §2.10 tests — types snapshot (`types_dump.py`).

Per PHASE2_PLAN §2.10 / D7 (dump-only, no C):
  * sanity: matrix is square, dimension == #types, nuclear_index resolves
  * value spot-check: real type matchups decode (immunity + super-effective),
    confirming the matrix[attacking][defending] convention

Real-data tests are env-gated via the `uranium_data` fixture.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.pbs_converter import types_dump

pytestmark = pytest.mark.phase2

# Type indices (reference/type_internal_names.json).
NORMAL, FIGHTING, FLYING, GROUND, GHOST = 0, 1, 2, 4, 7
FIRE = 10


def _dump(uranium_data: Path, tmp_path: Path) -> dict:
    out = tmp_path / "types_dump.json"
    # uranium_data is .../Data; dump_types expects the source root.
    types_dump.dump_types(uranium_data.parent, out)
    return json.loads(out.read_text(encoding="utf-8"))


def test_matrix_square_and_nuclear(uranium_data: Path, tmp_path: Path) -> None:
    d = _dump(uranium_data, tmp_path)
    n = len(d["types"])
    assert n == 20
    assert len(d["matrix"]) == n
    assert all(len(row) == n for row in d["matrix"])
    assert d["types"][d["nuclear_index"]] == "NUCLEAR"


def test_matchups_decode(uranium_data: Path, tmp_path: Path) -> None:
    """matrix[attacking][defending]: known immunity (0) and super-effective (4)."""
    d = _dump(uranium_data, tmp_path)
    m = d["matrix"]
    assert m[GROUND][FLYING] == 0    # Flying is immune to Ground
    assert m[GROUND][FIRE] == 4      # Ground is super-effective vs Fire
    assert m[NORMAL][GHOST] == 0     # Ghost is immune to Normal
    assert m[FIGHTING][NORMAL] == 4  # Fighting is super-effective vs Normal
    # Not a degenerate all-2s matrix.
    flat = [v for row in m for v in row]
    assert {0, 1, 2, 4} <= set(flat)
