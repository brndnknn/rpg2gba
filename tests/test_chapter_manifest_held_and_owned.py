"""Operator rulings 2026-10-15: "subtract held caps" and "owned rows outrank
cosmetic" (`generator.held_capabilities_at_start`, `derivation.derive_entry`
rule 5/6)."""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.chapter_manifest import generator
from rpg2gba.chapter_manifest.capability_model import taught_in_chain
from rpg2gba.chapter_manifest.derivation import DerivedEntry, derive_entry
from rpg2gba.chapter_manifest.generator import generate_chapter_manifest
from rpg2gba.chapter_manifest.generator_status import GeneratorStatus
from rpg2gba.chapter_manifest.schema import ManifestRow
from tests.test_chapter_manifest_generator import (
    _patch_start_cells,
    _rock_and_sign_events,
    _setup_reachability_chapter,
)

_RID = "map001/ev001/p0"


# --- change 1: held capabilities are subtracted from requires -----------------


def _generate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **kwargs) -> list[ManifestRow]:
    _patch_start_cells(monkeypatch, "CHR", 99, frozenset({(1, 0)}))
    build_dir, chapters_path = _setup_reachability_chapter(
        tmp_path, "CHR", 99, 3, 3, _rock_and_sign_events(), wall_cells={(0, 1), (2, 1)})
    return generate_chapter_manifest(
        "CHR", build_dir=build_dir, chapters_path=chapters_path, **kwargs)


def test_held_capability_removed_from_both_requires_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = _generate(tmp_path, monkeypatch, held_capabilities=frozenset({"rock_smash"}))
    sign = next(r for r in rows if r.event_id == 2)   # reachability source
    rock = next(r for r in rows if r.event_id == 1)   # per-head source
    assert sign.requires == ()
    assert rock.requires == ()


def test_non_held_capability_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = _generate(tmp_path, monkeypatch, held_capabilities=frozenset({"surf"}))
    assert next(r for r in rows if r.event_id == 2).requires == ("rock_smash",)
    assert next(r for r in rows if r.event_id == 1).requires == ("rock_smash",)


def test_default_held_set_comes_from_the_capability_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []

    def fake(chapter_id: str, *, build_dir: Path, chapters_path: Path) -> frozenset[str]:
        seen.append(chapter_id)
        return frozenset({"rock_smash"})

    monkeypatch.setattr(generator, "held_capabilities_at_start", fake)
    rows = _generate(tmp_path, monkeypatch)
    assert seen == ["CHR"]
    assert all(r.requires == () for r in rows if r.event_id in (1, 2))


def test_unregistered_chapter_holds_nothing(tmp_path: Path) -> None:
    held = generator.held_capabilities_at_start(
        "CH_NO_SUCH_CHAPTER", build_dir=tmp_path, chapters_path=Path("reference/chapters.json"))
    assert held == frozenset()


def test_taught_in_chain_accepts_repr_quoting(tmp_path: Path) -> None:
    """beat_gen writes module literals with repr() -- single quotes."""
    (tmp_path / "ch08.py").write_text("smash_beat(teach='teach_rock_smash')\n", encoding="utf-8")
    assert taught_in_chain(frozenset({"CH08"}), tmp_path) == frozenset({"rock_smash"})


# --- change 2: elsewhere:later: outranks cosmetic -----------------------------


def _row(**overrides) -> ManifestRow:
    defaults = dict(row_id=_RID, kind="page", map_id=1, content_hash="h1",
                    effects=(), reachability_consulted=True, unhandled=0)
    defaults.update(overrides)
    return ManifestRow(**defaults)


def _derive(row: ManifestRow, spec: str | None) -> DerivedEntry | None:
    status = GeneratorStatus(specs={_RID: spec} if spec else {})
    return derive_entry(row, beat_model=None, boundary_model=None, generator_status=status)


def test_row_is_cosmetic_without_a_generator_record() -> None:
    assert _derive(_row(), None) == DerivedEntry(disposition="cosmetic", derived_hash="h1")


@pytest.mark.parametrize("spec", ["elsewhere:later: CH01", "elsewhere:later: CH09"])
def test_elsewhere_later_beats_cosmetic(spec: str) -> None:
    entry = _derive(_row(), spec)
    assert entry == DerivedEntry(disposition=spec, derived_hash="h1")
    assert not entry.proposed


@pytest.mark.parametrize("spec", [
    "elsewhere:later",  # bare `later`: no owner named, not the `later:` form
    "elsewhere:empty_page: all empty",
    "elsewhere:never_fires: proof",
    "elsewhere:stripped: strip_list.json",
    "refused:story-state: unmodelled_outcome",
    "unreachable:no route",
])
def test_other_generator_records_still_lose_to_cosmetic(spec: str) -> None:
    assert _derive(_row(), spec).disposition == "cosmetic"


def test_elsewhere_later_does_not_outrank_blocked() -> None:
    entry = _derive(_row(requires=("rock_smash",)), "elsewhere:later: CH01")
    assert entry.disposition == "blocked:rock_smash" and entry.proposed
