"""Shared pytest fixtures for the Phase 2 converter suite.

Pure-unit tests (`test_binary`, `test_id_map`, `test_c_emit`) have no
environment dependency and always run. Tests that read the real Uranium `.dat`
files take the `uranium_data` fixture, which skips when `RPG2GBA_URANIUM_SRC`
is unset — so the suite is green on a machine that doesn't have the source.
Mark those tests `@pytest.mark.phase2`.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from rpg2gba.pipeline import _load_dotenv

# Populate os.environ from the repo-root .env so the fixtures resolve without
# the developer having to export the vars in their shell first.
_load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def uranium_data() -> Path:
    """Path to `$RPG2GBA_URANIUM_SRC/Data`; skips the test if unavailable."""
    src = os.environ.get("RPG2GBA_URANIUM_SRC")
    if not src:
        pytest.skip("RPG2GBA_URANIUM_SRC not set")
    data = Path(src) / "Data"
    if not data.is_dir():
        pytest.skip(f"{data} not found")
    return data


_REAL_BUILD = (REPO_ROOT / "output" / "uranium-build").resolve()


@pytest.fixture(autouse=True)
def _synthetic_builds_have_no_entry_cells(monkeypatch: pytest.MonkeyPatch) -> None:
    """`chapter_manifest.generator._start_cells` (A5) derives entry cells from
    the real corpus's world graph and fails loud without it. A synthetic
    `tmp_path` build has no world graph, so there it answers "no derivable
    entry" -- the documented unenforced path. The real build still runs the
    real derivation; a test that needs specific cells patches `_start_cells`
    itself (later `setattr` wins)."""
    from rpg2gba.chapter_manifest import generator

    real = generator._start_cells

    def start_cells(chapter_id: str, map_id: int, build_dir: Path):  # noqa: ANN202
        if Path(build_dir).resolve() != _REAL_BUILD:
            return None
        return real(chapter_id, map_id, build_dir)

    monkeypatch.setattr(generator, "_start_cells", start_cells)


@pytest.fixture(autouse=True)
def _synthetic_tilesets_skip_corpus_tile_merge(monkeypatch: pytest.MonkeyPatch) -> None:
    """ROM_TILE_MERGE is on in production, and its corpus table only knows real
    Uranium quads. Synthetic-rasterizer tests of `build_slice_tilesets` would KeyError
    on it, so the default is off here; a test of the merge passes `tile_merge=True` and
    its own `merge_table` explicitly."""
    from rpg2gba.tileset_converter.graphics import build_slice_tilesets as bst

    monkeypatch.setattr(bst, "_rom_tile_merge_enabled", lambda: False)


@pytest.fixture(scope="session")
def reference_dir() -> Path:
    """The repo's committed `reference/` sidecars."""
    return REPO_ROOT / "reference"


@pytest.fixture(scope="session")
def fork_path() -> Path | None:
    """`$RPG2GBA_POKEEMERALD` if set and present, else None."""
    p = os.environ.get("RPG2GBA_POKEEMERALD")
    return Path(p) if p and Path(p).is_dir() else None
