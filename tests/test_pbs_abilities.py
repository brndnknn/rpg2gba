"""Phase 2 §2.4 tests — abilities (`abilities.py`).

Per CLAUDE.md §4.6 / PHASE2_PLAN.md §2.4:
  * round-trip: compute the Uranium-original set → emit constants header →
    regex-read the `#define`s back → diff the {constant: id} mapping
  * golden: the emitted Uranium-only ABILITY_* block matches the pinned fixture
  * edge: CHERNOBYL (a *form*-only ability, absent from dexdata's species
    records) is still emitted and flagged needs_engine; a vanilla ability is not

Distinguishing Uranium-original abilities from vanilla ones requires the fork's
ability enum, so these tests skip when `RPG2GBA_POKEEMERALD` is unset.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from rpg2gba.pbs_converter import abilities
from rpg2gba.pbs_converter._id_map import IdMap

pytestmark = pytest.mark.phase2

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _build(
    reference_dir: Path, fork_path: Path | None
) -> tuple[IdMap, abilities._AbilityResolver, list[int]]:
    if fork_path is None:
        pytest.skip("RPG2GBA_POKEEMERALD not set; can't classify Uranium-original abilities")
    id_map = IdMap()
    r = abilities._build_resolver(id_map, reference_dir)
    originals = sorted(aid for aid in r.ability_internal if r.is_uranium_original(aid))
    return id_map, r, originals


def test_roundtrip_constants(reference_dir: Path, fork_path: Path | None) -> None:
    """Every `#define ABILITY_* <id>` re-reads to the minted (constant, id) pair."""
    _id_map, r, originals = _build(reference_dir, fork_path)
    c_text = abilities.emit_constants(originals, r)
    read_back = {
        m.group(1): int(m.group(2))
        for m in re.finditer(r"#define (ABILITY_\w+) (\d+)", c_text)
    }
    expected = {r.constant(aid): aid for aid in originals}
    assert read_back == expected
    assert len(read_back) >= 17  # the contiguous Uranium ability block


def test_golden_block(reference_dir: Path, fork_path: Path | None) -> None:
    """The full emitted Uranium-only constants header matches the pinned fixture."""
    _id_map, r, originals = _build(reference_dir, fork_path)
    got = abilities.emit_constants(originals, r)
    expected = (FIXTURES / "abilities_golden.h").read_text(encoding="utf-8")
    assert got == expected


def test_edge_chernobyl_form_ability(
    uranium_data: Path, reference_dir: Path, fork_path: Path | None
) -> None:
    """CHERNOBYL is a form-only ability missing from dexdata yet must be emitted.

    It is the URAYNE form-2 ability, assigned by script rather than stored in any
    base species record — so the dexdata scan never sees it. The sidecar-based
    classification must still pick it up and flag it needs_engine.
    """
    id_map, r, originals = _build(reference_dir, fork_path)
    # Not present in the dexdata-referenced in-use set...
    in_use = abilities.collect_ability_ids(uranium_data / "dexdata.dat")
    chernobyl_id = next(i for i, n in r.ability_internal.items() if n == "CHERNOBYL")
    assert chernobyl_id not in in_use
    # ...but still emitted as a Uranium-original constant and marked needs_engine.
    c_text = abilities.emit_constants(originals, r)
    assert "#define ABILITY_CHERNOBYL" in c_text
    assert "ABILITY_CHERNOBYL" in id_map.needs_engine["abilities"]


def test_edge_vanilla_not_emitted(reference_dir: Path, fork_path: Path | None) -> None:
    """A vanilla ability (Stench, id 1) is referenced directly, never redefined here."""
    _id_map, r, originals = _build(reference_dir, fork_path)
    c_text = abilities.emit_constants(originals, r)
    assert "ABILITY_STENCH" not in c_text
    assert not r.is_uranium_original(1)
