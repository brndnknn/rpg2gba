"""Tilesets.rxdata deserializer test (FABLES #8 — passages + terrain_tags oracle).

Shells to `deserialize.rb tilesets <data_dir> <out_dir>` and validates the
output JSON shape.  Requires the real Uranium tree; skips cleanly when
`RPG2GBA_URANIUM_SRC` is unset or the file is absent.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

# conftest.py calls _load_dotenv() at import time so env vars are populated
# before any fixture runs — no extra action needed here.

DESERIALIZER = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "rpg2gba"
    / "rxdata_deserializer"
    / "deserialize.rb"
)


def _tilesets_rxdata() -> Path | None:
    src = os.environ.get("RPG2GBA_URANIUM_SRC")
    if not src:
        return None
    p = Path(src) / "Data" / "Tilesets.rxdata"
    return p if p.is_file() else None


@pytest.fixture(scope="module")
def tilesets_json(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """Run the Ruby deserializer once and return the parsed JSON dict."""
    rxdata = _tilesets_rxdata()
    if rxdata is None:
        pytest.skip("Tilesets.rxdata not found — set RPG2GBA_URANIUM_SRC")
    out_dir = tmp_path_factory.mktemp("tilesets_out")
    proc = subprocess.run(
        ["ruby", str(DESERIALIZER), "tilesets", str(rxdata.parent), str(out_dir)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"deserialize.rb tilesets exited {proc.returncode}:\n{proc.stderr.strip()}"
    )
    out_file = out_dir / "tilesets.json"
    assert out_file.is_file(), "tilesets.json not produced"
    return json.loads(out_file.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_json_parses(tilesets_json: dict) -> None:
    """tilesets.json must be a non-empty dict."""
    assert isinstance(tilesets_json, dict)
    assert len(tilesets_json) >= 1


def test_at_least_one_tileset(tilesets_json: dict) -> None:
    """Uranium ships at least one tileset (empirically 60)."""
    assert len(tilesets_json) >= 1


def test_each_tileset_has_required_keys(tilesets_json: dict) -> None:
    """Every entry must carry id, name, terrain_tags, and passages."""
    required = {"id", "name", "terrain_tags", "passages"}
    for ts_id, ts in tilesets_json.items():
        missing = required - ts.keys()
        assert not missing, f"tileset {ts_id!r} missing keys: {missing}"


def test_terrain_tags_nonempty(tilesets_json: dict) -> None:
    """Every tileset's terrain_tags list must be non-empty."""
    for ts_id, ts in tilesets_json.items():
        assert len(ts["terrain_tags"]) > 0, f"tileset {ts_id!r} has empty terrain_tags"


def test_passages_nonempty(tilesets_json: dict) -> None:
    """Every tileset's passages list must be non-empty."""
    for ts_id, ts in tilesets_json.items():
        assert len(ts["passages"]) > 0, f"tileset {ts_id!r} has empty passages"


def test_array_lengths_match(tilesets_json: dict) -> None:
    """terrain_tags, passages, and priorities must all have the same length."""
    for ts_id, ts in tilesets_json.items():
        n = len(ts["terrain_tags"])
        assert len(ts["passages"]) == n, (
            f"tileset {ts_id!r}: passages len {len(ts['passages'])} != terrain_tags len {n}"
        )
        if "priorities" in ts:
            assert len(ts["priorities"]) == n, (
                f"tileset {ts_id!r}: priorities len {len(ts['priorities'])} != terrain_tags len {n}"
            )


def test_array_entries_are_integers(tilesets_json: dict) -> None:
    """Spot-check first entry of each array — entries must be integers."""
    for ts_id, ts in tilesets_json.items():
        assert isinstance(ts["terrain_tags"][0], int), (
            f"tileset {ts_id!r}: terrain_tags[0] is not int"
        )
        assert isinstance(ts["passages"][0], int), (
            f"tileset {ts_id!r}: passages[0] is not int"
        )


def test_tileset_count(tilesets_json: dict) -> None:
    """Uranium has exactly 60 tilesets (empirically verified)."""
    assert len(tilesets_json) == 60
