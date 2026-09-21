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

Expected own-beat counts: **ch01 22 / ch02 19 / ch03 35 / ch04 14 / ch05 21 = 111**.

> **Correction, 2026-09-19.** This section used to say 22/18/35/13/5 = 91. That figure comes
> from `C6_GENERATOR_PLAN.md` §1 and `REDERIVATION_PLAN.md`, and it was measured by counting
> `@….beat(` **decorators** in the source. `load_chapter` returns every **registered** beat,
> and not every beat is registered by a decorator. The freeze must use the registered list,
> because a registered beat is what claims rows, and rows are what C9 grades. Q4 asks you to
> account for the 20-beat difference. (Rowless counts are unaffected: CH02 has 4, CH04 3,
> CH05 0.)

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

> **Hint — how and where to raise `FreezeError`.** The class already exists in the stub
> (`class FreezeError(Exception)`), so there is nothing to define. You only need to know
> *when* to raise it and *what* to put in it.
>
> - **Raise it in `build_freeze()`, once, after the loop.** Not inside the per-row check.
>   A `raise` leaves the function immediately, which is exactly what collect-then-raise is
>   avoiding. Inside the loop you only `problems.append(...)`.
> - **The message is the only channel the operator sees.** The `write` command catches it
>   with `except FreezeError as exc` and prints `freeze NOT written:\n{exc}`. So
>   `"\n".join(problems)` gives one problem per line, and each line must stand alone: name the
>   chapter, the beat, and the offending value (`CH03:B7 claims 'map099/ev001/p0', not in
>   manifest`). A bare `"bad row"` is useless at 2am.
> - **Two kinds of problem, one exception.** A dirty module (R2) and an unknown row (R3) both
>   mean "unsafe to write", so both go into the same `problems` list and the same
>   `FreezeError`. One run then reports both.
> - **Don't raise `FreezeError` for everything.** Match the exception to the meaning:
>   - `FreezeError`: the freeze *content* is unsafe (dirty module, bad row). `write` and
>     `check` both catch it and turn it into a clean CLI message.
>   - `ValueError`: bad *input data* or a schema you don't know
>     (`load_frozen_hand_beats`, and the duplicate-`row_id` case in `manifest_row_ids`).
>   - `RuntimeError` / `FileNotFoundError`: environment failures (git can't resolve a path,
>     manifest file missing). These are *not* caught by the CLI, so they surface as a
>     traceback. That is deliberate: they mean the tooling is broken, not that the freeze is
>     wrong.
> - **Test it the same way the tests do.** `pytest.raises(FreezeError)` as a context manager,
>   then check the text with `str(excinfo.value)`. `test_unknown_row_fails_loud` asserts the
>   bad row id appears in the message, so if you leave it out, that test tells you.
> - **`raise ... from exc`** only matters if you catch something and re-raise a different
>   type. You probably don't need it in `build_freeze`, since you are raising fresh from a
>   list, not translating another exception. (The CLI wrapper already does it for you.)

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
- **`tests/test_hand_freeze.py`**: **implemented, live** (as of 2026-09-19; the old
  `pytestmark` skip is gone). It holds the six named tests plus **build-order tests**, at
  least one per stub, so you get a red→green signal at every step instead of only at the end.

The function names are public (no leading `_`), unlike in the tables above, because the
tests call them directly.

## Working test-first

Run just the tests for the step you're on with `-k`:

| Step | Function(s) | Run | Status 2026-09-19 |
|---|---|---|---|
| 1 | `head_blob_sha`, `worktree_blob_sha` | `-k "sha"` | ✅ done |
| 2 | `own_beats` | `-k "own_beat"` | ✅ done |
| 2 | `manifest_row_ids` | `-k manifest_row_ids` | ⬜ |
| 3 | `build_freeze` | `-k "freeze_top_level or serialisable or deterministic or inherited or uncommitted or all_problems or unknown_row"` | ⬜ |
| 4 | `diff_freeze` | `-k "diff_freeze or stale"` | ⬜ |
| 4 | minimal `validate_residue` | `-k minimal_residue` | ⬜ |
| 5 | `load_frozen_hand_beats` | `-k loader` | ⬜ |

```bash
.venv/bin/pytest tests/test_hand_freeze.py -q -k manifest_row_ids
.venv/bin/pytest tests/test_hand_freeze.py -q          # everything, when you think you're done
```

Most tests share one module-scoped `freeze` fixture that calls `build_freeze()` once. Until
step 3 works, those tests show up as **ERROR** (the fixture failed), not FAIL. That's expected.
A test that ERRORs is waiting on `build_freeze`, not failing on its own logic.

**A clean tree matters.** The R2 check means any uncommitted edit to a `chNN.py` makes
`build_freeze` refuse, and then every fixture-based test ERRORs with your own `FreezeError`.
If that happens, read the message: it's the feature working. `hand_freeze.py` itself is *not*
covered by the check, so you can edit it freely.

## Hints for the remaining stubs

These tell you what to think about, not what to type.

### `manifest_row_ids(chapter)`

Three lines. The path pattern is in the "Where things are" table. Remember `encoding="utf-8"`.
There's also a `_read_json` helper at the bottom of the file. It's defined *after*
`manifest_row_ids`, but it's still fine to call because the name is looked up when the
function *runs*, not when it's defined. What should happen if the manifest file doesn't
exist? (§4.5 answers that, and `open()` already does the right thing.)

### `build_freeze()`

This is the one with real structure. Sketch it on paper first:

1. One `problems: list[str] = []` for the **whole** build, not one per chapter.
2. For each chapter: get the module path. Compare `head_blob_sha` with `worktree_blob_sha`,
   and on a mismatch append a problem that names the chapter. Then get `own_beats`, and
   check each claimed row against `manifest_row_ids(chapter)`.
3. After the loop: `if problems: raise FreezeError(...)`.
4. Only then assemble the dict, **in R1's key order**. `test_freeze_top_level_shape` checks
   `list(freeze) == [...]`, and a dict literal keeps insertion order.

Things to decide yourself:
- When a module is dirty, do you still check its rows? (Either answer passes the tests. Pick
  the one that gives the operator the most useful single error message.)
- Call `manifest_row_ids` **once per chapter**, not once per beat or per row. It reads a file.
- Call helpers through the module's global names (`manifest_row_ids(ch)`, not a local alias
  captured earlier). The tests `monkeypatch.setattr(hand_freeze, "manifest_row_ids", …)`, and
  monkeypatching replaces the module attribute, so only global lookups see the fake.

### `diff_freeze(committed, rebuilt)`

It's pure: two dicts in, `list[str]` out. Two passes over `CHAPTERS`:
- Compare `sources[ch]["blob_sha"]` → `"stale: CHnn module changed since freeze"`.
- Compare `chapters[ch]` → a "beats differ" problem naming the chapter.

A plain `!=` on the two beat lists passes the tests. For a *useful* message, think about what
the operator needs to know. "CH03 differs" is correct; "CH03:B1 rows differ" is actionable.
Going further is optional.

Edge case to think about: if a chapter is stale, its beat list will very likely differ too.
Report both, or suppress the second? There's no single right answer. Put your reasoning in a
comment.

### minimal `validate_residue(frozen, ledger)`

Just enough for Task 1: if `ledger is None` and any frozen beat has `rows == []`, return
**one** problem. Otherwise return `[]`. Task 2 replaces the body (and adds a third
parameter). Keep it short and don't write any Task 2 logic yet.

### `load_frozen_hand_beats(path)`

- Read the file and check `schema == SCHEMA` **before** touching anything else. On a
  mismatch, raise `ValueError` with the bad version in the message. (The test matches on
  `"99"`. `FreezeError` would be wrong here: it means "unsafe to *write*".)
- Walk `CHAPTERS` in order, not `data["chapters"]` in file order. Why is that the safer
  choice, even though they agree today?
- `rows` must become a `tuple`: the dataclass is `frozen=True`, and a frozen dataclass
  holding a list is only shallowly frozen (and unhashable).

## Tests (`tests/test_hand_freeze.py`)

Each of these must exist:

| Test | Asserts |
|---|---|
| `test_own_beat_counts` | per-chapter own counts are 22/18/35/13/5 |
| `test_no_inherited_names` | no frozen `name` contains `:` |
| `test_build_is_deterministic` | `dump(build_freeze()) == dump(build_freeze())` |
| `test_unknown_row_fails_loud` | monkeypatch `manifest_row_ids` to drop one real row → `build_freeze` raises and the message names the row |
| `test_check_detects_stale_blob` | a freeze dict with a tampered `blob_sha` → `check` logic reports stale |
| `test_loader_roundtrip` | `load_frozen_hand_beats` on a `tmp_path` file written by `dump(build_freeze())` returns 111 beats |

Tip: split `check` into a pure function (`diff_freeze(committed, rebuilt) -> list[str]`) and
a thin click wrapper. Then you can test the pure function without invoking the CLI.

## Questions (answer in the commit message, 2–4 sentences each)

1. Why freeze only own beats rather than the composed list? What would go wrong in a diff?
2. Why is `authored` a constant and not today's date? Which CLAUDE.md principle applies?
3. `order` and `group` are recorded but never graded. Why record them at all?
4. *(Added 2026-09-19.)* The plan says 91 beats and your freeze says 111. Which 20 beats
   account for the difference, and how does each get registered without a decorator? (Start
   with CH05's names such as `B3_retalk1`, then find the odd one out in CH02 and in CH04.)
   Then write a dated correction next to the "91" in `C6_GENERATOR_PLAN.md` §1 (CLAUDE.md §7).
