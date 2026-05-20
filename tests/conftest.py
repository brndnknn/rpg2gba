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


@pytest.fixture(scope="session")
def reference_dir() -> Path:
    """The repo's committed `reference/` sidecars."""
    return REPO_ROOT / "reference"


@pytest.fixture(scope="session")
def fork_path() -> Path | None:
    """`$RPG2GBA_POKEEMERALD` if set and present, else None."""
    p = os.environ.get("RPG2GBA_POKEEMERALD")
    return Path(p) if p and Path(p).is_dir() else None
