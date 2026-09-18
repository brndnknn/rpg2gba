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

> **Hint — running git from Python.** Use `subprocess.run` with the command as a *list*
> (no shell string). Read the output from `.stdout` and check `.returncode` yourself.
> The repo already does exactly this in `scripts/freeze_rederivation.py:101–113`
> (`_git_blob_sha`). Read it, then write your own version:
>
> ```python
> result = subprocess.run(
>     ["git", "rev-parse", f"HEAD:{repo_relative}"],
>     cwd=REPO_ROOT,          # run from the repo root, whatever the caller's cwd is
>     capture_output=True,    # collect stdout/stderr instead of printing them
>     text=True,              # give me str, not bytes
> )
> if result.returncode != 0:
>     raise RuntimeError(f"... {result.stderr.strip()}")
> sha = result.stdout.strip()   # strip the trailing newline
> ```
>
> The two commands you need, and what each answers:
> - `git rev-parse HEAD:src/…/ch01.py` gives the blob of the file **as committed**
> - `git hash-object src/…/ch01.py` gives the blob of the file **as it is on disk right now**
>
> If they differ, the file has uncommitted edits. Try both in a terminal first on a clean
> file, then after adding a blank line, so you know what you're comparing.

### R3 — Row-id validation (fail loud)

Every row id a beat claims must exist in that chapter's manifest. If one doesn't, raise with
the chapter, beat name and bad row id. Don't drop it and don't warn.

> **Hint — what "fail loud" means here, and what it doesn't.** It does *not* mean "crash on
> the first problem". It means that problems are never silently dropped, and that a bad
> freeze is never written. Use the **collect, then raise** pattern: check *everything*,
> gather every problem into a list, and after the loop raise once with all of them. Then a
> single run shows you every bad row, not just the first:
>
> ```python
> problems: list[str] = []
> for chapter in CHAPTERS:
>     known = _manifest_row_ids(chapter)
>     for beat in own_beats(chapter):
>         for row in beat["rows"]:
>             if row not in known:
>                 problems.append(f"{chapter}:{beat['name']} claims {row!r}, not in manifest")
> if problems:
>     raise FreezeError("\n".join(problems))
> # only reached when clean -> safe to return / write
> ```
>
> **And yes, no file is written when there are problems.** This file is the *grading oracle*
> for C9. A freeze that quietly leaves out a bad row would later grade the generator against
> a smaller target than the hand suite actually had, which is exactly the silent loss C7
> exists to prevent. The fix for a bad row goes in the **hand module** (`chNN.py`: correct or
> remove the stale id) or the manifest, never in the freeze. You probably won't hit any,
> since C1 regenerated the manifests and the checker has been clean, but the check is there
> so you'd find out if you did.
>
> Task 2's `validate_residue` uses the same shape (it returns `list[str]`), so reuse the
> pattern. Also: read manifests as **raw JSON** (`json.load` then `{r["row_id"] for r in rows}`),
> the same way `scripts/freeze_rederivation.py:136` (`_manifest_rows_by_id`) does, and not
> through `chapter_manifest.schema`'s loader. You only need the ids, and the raw read has
> fewer ways to fail.

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

**Already wired for you.** The stub `src/rpg2gba/playtest/hand_freeze.py` has the click
group, both commands, `--force`, the refuse-to-overwrite check and the exit codes. The
commands call `build_freeze()`, `diff_freeze()` and `dump()`. You implement those and the
helpers under them; you shouldn't need to touch the CLI code.

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

## Stub files (start here)

- **`src/rpg2gba/playtest/hand_freeze.py`**: constants, `FreezeError`, `FrozenBeat`,
  `dump()` and the whole CLI are done. Every function that raises `NotImplementedError` is
  yours. A suggested order that keeps you able to run something at each step:
  1. `head_blob_sha`, `worktree_blob_sha` (try them in a REPL:
     `from rpg2gba.playtest.hand_freeze import *; head_blob_sha(module_path("CH01"))`)
  2. `manifest_row_ids`, `own_beats`
  3. `build_freeze`. At this point `write` works.
  4. `diff_freeze`, plus a minimal `validate_residue`. At this point `check` works.
  5. `load_frozen_hand_beats`
- **`tests/test_hand_freeze.py`**: the six tests, stubbed with a comment saying what each
  asserts. The whole file is **skipped** by a `pytestmark` line so the suite stays green;
  delete that line when you start.

The function names are public (no leading `_`), unlike in the tables above, because the
tests call them directly.

## Tests (`tests/test_hand_freeze.py`)

Each of these must exist:

| Test | Asserts |
|---|---|
| `test_own_beat_counts` | per-chapter own counts are 22/18/35/13/5 |
| `test_no_inherited_names` | no frozen `name` contains `:` |
| `test_build_is_deterministic` | `dump(build_freeze()) == dump(build_freeze())` |
| `test_unknown_row_fails_loud` | monkeypatch `manifest_row_ids` to drop one real row → `build_freeze` raises and the message names the row |
| `test_check_detects_stale_blob` | a freeze dict with a tampered `blob_sha` → `check` logic reports stale |
| `test_loader_roundtrip` | `load_frozen_hand_beats` on a `tmp_path` file written by `dump(build_freeze())` returns 91 beats |

Tip: split `check` into a pure function (`diff_freeze(committed, rebuilt) -> list[str]`) and
a thin click wrapper. Then you can test the pure function without invoking the CLI.

## Questions (answer in the commit message, 2–4 sentences each)

1. Why freeze only own beats rather than the composed list? What would go wrong in a diff?
2. Why is `authored` a constant and not today's date? Which CLAUDE.md principle applies?
3. `order` and `group` are recorded but never graded. Why record them at all?
