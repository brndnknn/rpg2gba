# Task 1 — Freeze Capture (35 points)

## Goal

Write a module that captures **what each hand beat claims** in CH01–CH05 into a committed JSON
file, plus a `check` command that fails when that file goes stale. This file becomes the
grading target for the generated suites (C6/C9).

You are freezing **rows and identity only**. You are *not* capturing assertion values,
emulator behaviour, or anything from inside a beat's body. R12 was amended specifically so
that no AST parsing or emulator run is needed (`REDERIVATION_PLAN.md` "R12 AMENDED").

## Learning objectives

- Load Python objects from a registry (`load_chapter`) and project them into a stable
  serialisable shape
- Build provenance into an artifact (git blob hashes) so staleness is detectable
- Design `write` / `check` commands that are idempotent and fail loud

## Where things are

| Thing | Location |
|---|---|
| Chapter loader | `src/rpg2gba/playtest/chapter.py:696` `load_chapter(name) -> Chapter` |
| `Beat` dataclass | `src/rpg2gba/playtest/chapter.py:126`, fields `name, description, run, locations, entry_at, group, rows, archetype, assertions` |
| Prior art (read it, **do not import it**) | `scripts/freeze_rederivation.py`, especially `_beat_dicts` (line 153) and `_git_blob_sha` (line 101) |
| Manifests (for row-id validation) | `reference/manifests/CHnn.manifest.json`, a JSON list of rows, each with a `row_id` |
| Output file | `reference/frozen/hand_beats_ch01-ch05.json` (new) |
| Your module | `src/rpg2gba/playtest/hand_freeze.py` (new) |
| Your tests | `tests/test_hand_freeze.py` (new) |

> **Why not extend `scripts/freeze_rederivation.py`?** Its docstring says it's scaffolding
> scheduled for deletion at P10, and says not to build on it. Your file will be read by C9's
> grading test, so it needs a loader that lives in `src/`. Copy patterns from it; don't
> import from it.

## Key fact: composed beat lists

`load_chapter("CH03").beats` returns CH03's own beats **plus every predecessor's**.
Inherited beats are renamed with a prefix (`CH01:B1`). Own beats have bare names (`B1`,
`N4`). **Freeze own beats only.** Each beat is frozen once, under the chapter that owns it.

```python
import re
_INHERITED = re.compile(r"^CH\d\d:")

own = [b for b in load_chapter("CH03").beats if not _INHERITED.match(b.name)]
```

Expected own-beat counts: **ch01 22 / ch02 18 / ch03 35 / ch04 13 / ch05 5 = 91**. If you get
different numbers, stop and find out why before going further.

## Requirements

### R1 — File format

`write` produces exactly this shape (key order as shown, `indent=2`, trailing newline):

```json
{
  "schema": 1,
  "authored": "2026-09-18",
  "rule": "REDERIVATION_PLAN.md §16.3 R12 (amended 2026-09-17): rows + identity; order/group recorded, not graded",
  "sources": {
    "CH01": {"module": "src/rpg2gba/playtest/chapters/ch01.py", "blob_sha": "4f1c…"},
    "CH02": {"module": "…", "blob_sha": "…"}
  },
  "chapters": {
    "CH01": [
      {"name": "B1", "order": 0, "group": null, "map_constant": "MAP_…", "rows": []},
      {"name": "B2", "order": 1, "group": null, "map_constant": "MAP_…", "rows": ["map032/ev003/p0"]}
    ]
  }
}
```

- `order` is the beat's index among the chapter's **own** beats, in registration order.
- `map_constant` is `beat.locations[0].map_constant`, or `null` if the beat has no locations.
- `rows` keeps the tuple's order, converted to a list.
- `authored` is a module constant, **not** `date.today()`. Using today's date would break
  idempotence. Explain why in Q2.

### R2 — Provenance

`blob_sha` is the git blob of the chapter module at `HEAD`
(`git rev-parse HEAD:<path>`). If the module has uncommitted changes, `write` must
**refuse** with a clear error, because a freeze of uncommitted code can't name its own
source. Hint: compare `git hash-object <path>` against the `HEAD` blob.

### R3 — Row-id validation (fail loud)

Every row id a beat claims must exist in that chapter's manifest. If one doesn't, raise with
the chapter, beat name and bad row id. Don't drop it and don't warn.

### R4 — CLI

```bash
.venv/bin/python -m rpg2gba.playtest.hand_freeze write [--force]
.venv/bin/python -m rpg2gba.playtest.hand_freeze check
```

- `write` refuses to overwrite an existing file unless `--force` is given.
- `check` rebuilds the freeze in memory and compares it with the committed file. It exits
  non-zero, naming what differs, if:
  1. a module's `blob_sha` no longer matches `HEAD` (report "stale: CHnn module changed since freeze"),
  2. the rebuilt content differs from the file, or
  3. *(hook for Task 2)* any frozen beat with `rows == []` has no entry in the residue
     ledger. Until Task 2 exists, have this raise if the ledger file is missing.

Use click, following the house style of `src/rpg2gba/beat_floor/__main__.py`. Add an
`if __name__ == "__main__": cli()` guard, or a `__main__.py` if you prefer the package form.

### R5 — A loader for downstream use

Expose a public function that C9 will call later:

```python
@dataclass(frozen=True)
class FrozenBeat:
    chapter: str
    name: str
    order: int
    group: str | None
    map_constant: str | None
    rows: tuple[str, ...]


def load_frozen_hand_beats(path: Path = FROZEN_PATH) -> list[FrozenBeat]:
    """Every frozen hand beat, CH01 first, in order. Fails loud on a
    schema version it doesn't know."""
```

## Skeleton (fill in the bodies)

```python
"""Freeze CH01–CH05's hand beats: rows + identity (REDERIVATION_PLAN.md §16.3 C7)."""
from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click

from rpg2gba.playtest.chapter import load_chapter

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
FROZEN_PATH = REPO_ROOT / "reference" / "frozen" / "hand_beats_ch01-ch05.json"
CHAPTERS = ("CH01", "CH02", "CH03", "CH04", "CH05")
AUTHORED = "2026-09-18"
SCHEMA = 1


def _module_path(chapter: str) -> str:
    return f"src/rpg2gba/playtest/chapters/{chapter.lower()}.py"


def _head_blob_sha(repo_relative: str) -> str: ...
def _worktree_blob_sha(repo_relative: str) -> str: ...
def _manifest_row_ids(chapter: str) -> set[str]: ...
def own_beats(chapter: str) -> list[dict[str, Any]]: ...
def build_freeze() -> dict[str, Any]: ...
def dump(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
```

## Tests (`tests/test_hand_freeze.py`)

Each of these must exist:

| Test | Asserts |
|---|---|
| `test_own_beat_counts` | per-chapter own counts are 22/18/35/13/5 |
| `test_no_inherited_names` | no frozen `name` contains `:` |
| `test_build_is_deterministic` | `dump(build_freeze()) == dump(build_freeze())` |
| `test_unknown_row_fails_loud` | monkeypatch `_manifest_row_ids` to drop one real row → `build_freeze` raises and the message names the row |
| `test_check_detects_stale_blob` | a freeze dict with a tampered `blob_sha` → `check` logic reports stale |
| `test_loader_roundtrip` | `load_frozen_hand_beats` on a `tmp_path` file written by `dump(build_freeze())` returns 91 beats |

Tip: split `check` into a pure function (`diff_freeze(committed, rebuilt) -> list[str]`) and
a thin click wrapper. Then you can test the pure function without invoking the CLI.

## Questions (answer in the commit message, 2–4 sentences each)

1. Why freeze only own beats rather than the composed list? What would go wrong in a diff?
2. Why is `authored` a constant and not today's date? Which CLAUDE.md principle applies?
3. `order` and `group` are recorded but never graded. Why record them at all?
