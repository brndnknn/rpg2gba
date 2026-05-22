"""Phase 2 §2.3 tests — items (`items.py`).

Per CLAUDE.md §4.6 / PHASE2_PLAN.md §2.3:
  * round-trip: parse → emit C → regex-read back → diff price (the numeric field
    that survives into gItemsInfo[]; behavior codes go to the worklist instead)
  * golden: pinned snapshot (ITEM_REPEL + the accent-folded ITEM_POKE_BALL)
  * edge: a key-item gets `.importance = 1`
  * edge: a Uranium-original item is flagged needs_engine against the fork

All real-data tests are env-gated via the `uranium_data` fixture.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from rpg2gba.pbs_converter import items
from rpg2gba.pbs_converter._id_map import IdMap

pytestmark = pytest.mark.phase2

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _build(uranium_data: Path, reference_dir: Path) -> tuple[list[items.Item], items._ItemResolver]:
    parsed = items.parse(uranium_data / "items.dat")
    items.attach_internal_names(
        parsed, items._load_id_json(reference_dir / "item_internal_names.json")
    )
    resolver = items._build_resolver(IdMap(), reference_dir)
    for it in parsed:
        resolver.constant(it.id)
    return parsed, resolver


def _entry(c_text: str, const: str) -> str:
    m = re.search(r"    \[" + re.escape(const) + r"\] =\n    \{.*?\n    \},", c_text, re.S)
    assert m, f"{const} entry not found in emitted items.h"
    return m.group(0)


def _by_internal(parsed: list[items.Item], internal: str) -> items.Item:
    return next(it for it in parsed if it.internal_name == internal)


def test_roundtrip_price(uranium_data: Path, reference_dir: Path) -> None:
    """`.price` emitted into gItemsInfo[] re-reads to the parsed value."""
    parsed, resolver = _build(uranium_data, reference_dir)
    c_text = items.emit_items_info(parsed, resolver)
    checked = 0
    for it in parsed:
        entry = _entry(c_text, resolver.constant(it.id))
        hit = re.search(r"\.price = (\d+),", entry)
        assert hit and int(hit.group(1)) == it.price, f"{it.internal_name}.price"
        checked += 1
    assert checked >= 600


def test_golden_repel_pokeball(uranium_data: Path, reference_dir: Path) -> None:
    """Pinned output: a plain item + the accent-folded Poké Ball (POKeBALL→ITEM_POKE_BALL)."""
    parsed, resolver = _build(uranium_data, reference_dir)
    c_text = items.emit_items_info(parsed, resolver)
    got = _entry(c_text, "ITEM_REPEL") + "\n" + _entry(c_text, "ITEM_POKE_BALL") + "\n"
    expected = (FIXTURES / "items_golden.h").read_text(encoding="utf-8")
    assert got == expected


def test_edge_pokeball_accent_folded(uranium_data: Path, reference_dir: Path) -> None:
    """The typo'd internal `POKeBALL` (id 211, name "Poké Ball") → ITEM_POKE_BALL."""
    parsed, resolver = _build(uranium_data, reference_dir)
    pokeball = _by_internal(parsed, "POKeBALL")
    assert resolver.constant(pokeball.id) == "ITEM_POKE_BALL"


def test_edge_key_item_importance(uranium_data: Path, reference_dir: Path) -> None:
    """An Essentials Key Items (pocket 8) item gets `.importance = 1`."""
    parsed, resolver = _build(uranium_data, reference_dir)
    c_text = items.emit_items_info(parsed, resolver)
    key_item = next(it for it in parsed if it.pocket == items._KEY_ITEMS_POCKET)
    entry = _entry(c_text, resolver.constant(key_item.id))
    assert ".importance = 1," in entry
    # A non-key item must not carry importance.
    plain = next(it for it in parsed if it.pocket == 1)
    assert ".importance" not in _entry(c_text, resolver.constant(plain.id))


def test_edge_uranium_item_needs_engine(
    uranium_data: Path, reference_dir: Path, fork_path: Path | None
) -> None:
    """At least one Uranium-original item resolves to needs_engine against the fork."""
    if fork_path is None:
        pytest.skip("RPG2GBA_POKEEMERALD not set; can't validate needs_engine")
    parsed = items.parse(uranium_data / "items.dat")
    items.attach_internal_names(
        parsed, items._load_id_json(reference_dir / "item_internal_names.json")
    )
    id_map = IdMap()
    resolver = items._build_resolver(id_map, reference_dir)
    for it in parsed:
        resolver.constant(it.id)
    assert id_map.needs_engine["items"], "expected some Uranium-original items"
