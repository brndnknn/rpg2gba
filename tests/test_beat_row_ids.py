"""`playtest.chapter._validate_row_id` is answerable to the real manifests.

That validator re-implements the row-id shapes `chapter_manifest.schema`
mints (`page_row_id` / `seam_row_id` / `terrain_row_id`) as three local
regexes, deliberately, so `playtest` need not import `chapter_manifest`
just to check a string. The cost of that copy is drift, and it has now
drifted twice in the same direction -- both times by spelling out an
enumeration the schema never restricted:

* terrain rows were rejected outright until 2026-09-04 (the pattern did
  not exist), which is why CH05's B13/B14 could not claim their stair rows;
* seam rows were `(NORTH|SOUTH|EAST|WEST)` until 2026-09-11, matching
  NOTHING the generator emits -- every seam direction in the corpus is a
  single letter, because it comes verbatim from `connections.json`. CH04's
  B1 was the first beat that tried to claim a seam row, and it could not.

Nothing compared the copy against the original, so both sat unnoticed.
This test is that comparison: every row id in every committed manifest
must validate. It fails the moment the generator mints a shape the
validator cannot accept -- which is the only way this class of bug
announces itself.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.playtest.chapter import _validate_row_id

MANIFEST_DIR = Path("reference/manifests")


def _manifest_paths() -> list[Path]:
    return sorted(MANIFEST_DIR.glob("*.manifest.json"))


def test_manifest_dir_is_populated():
    """A glob that silently matches nothing would make every test below
    vacuously green (CLAUDE.md 4.5)."""
    paths = _manifest_paths()
    assert paths, f"no committed manifests under {MANIFEST_DIR}"


@pytest.mark.parametrize("path", _manifest_paths(), ids=lambda p: p.stem)
def test_every_committed_row_id_validates(path: Path):
    rows = json.loads(path.read_text(encoding="utf-8"))
    assert rows, f"{path} is empty"
    for row in rows:
        row_id = row["row_id"]
        # Raises ValueError with an actionable message if the validator's
        # local patterns have drifted from what the schema mints.
        _validate_row_id(row_id, beat_name=f"<{path.stem}>")


def test_every_committed_seam_row_validates():
    """The regression that motivated this file, stated directly: seam rows
    exist in the committed corpus and every one of them must pass."""
    seen = 0
    for path in _manifest_paths():
        for row in json.loads(path.read_text(encoding="utf-8")):
            if row.get("kind") == "seam":
                _validate_row_id(row["row_id"], beat_name=f"<{path.stem}>")
                seen += 1
    assert seen, "no seam rows in any committed manifest -- this test would be vacuous"
