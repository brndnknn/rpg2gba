# Assignment C8 — Stage 7: Finishing the Shared Ruby Subset

**Course:** RPG2GBA 230 — Static Analysis and Fail-Loud Pipelines
**Weight:** 3 tasks, 100 points total
**Prerequisites:** C8 stages 1–4 and 6 are landed (they are). Python 3.11 dataclasses, pytest,
click. You do **not** need to have written the interpreter to do this assignment.
**Estimated effort:** Task 1 ≈ 5–7 h · Task 2 ≈ 2–3 h · Task 3 ≈ 2–3 h

---

## Background (read this first)

C8 replaced five independent regex readers of embedded Ruby with one shared package,
`src/rpg2gba/ruby_subset/` (lexer → parser → concrete evaluator → row-scope input search).
Six of its seven stages are done:

| Stage | What it did | Status |
|---|---|---|
| 1–2 | lexer/parser/AST; concrete evaluator + builtin table | DONE |
| 3 | row-scope input search (`search.py`) | DONE |
| 4 | `story_state` extraction onto the interpreter; the resolver fixpoint | DONE |
| 5 | `beat_floor/script.py` parses whole statements | **not this assignment** |
| 6 | the transpiler's `_RubyLocal`/array/argmax path | DONE (`ruby_idioms.py`) |
| 7 | **three loose ends** | **this assignment** |

Stage 7 is the tidy-up stage. It is three genuinely independent jobs in three different
packages, and they can be done in any order, by different people, in parallel. None of them
requires understanding the interpreter's internals — each is about a *seam* where two parts of
the pipeline currently disagree with each other.

Authoritative background: `REDERIVATION_PLAN.md` §16.3, the "C8 shape" ruling (rulings (b) and
(e)) and the stage list item **(7)**. Read those before starting.

## The three tasks

| # | File | What you build | Points |
|---|---|---|---|
| 1 | [`01_jvgivereward.md`](01_jvgivereward.md) | A real `jvGiveReward` extractor, replacing today's blanket refusal | 45 |
| 2 | [`02_strip_honoring.md`](02_strip_honoring.md) | `beat_floor` honouring stripped common events on code-117 | 25 |
| 3 | [`03_engine_audit_flags.md`](03_engine_audit_flags.md) | `engine-audit` checking `FLAG_SYS_*` against the fork index | 30 |

**Order:** any. They touch disjoint files. If you want the cheapest win first, do 3, then 2,
then 1.

### A theme worth naming

All three tasks are the same shape underneath, and it is the shape CLAUDE.md §4.3 exists to
prevent: **two parts of the pipeline hold the same belief separately, and they have drifted.**

- Task 1: `story_state`'s interpreter can resolve the Bambo reward ladder, but `beat_floor`
  refuses it with a hard-coded string written before the interpreter existed.
- Task 2: `story_state` treats a call to a stripped common event as a no-op; `beat_floor`
  inlines its body anyway. Same 117 command, two answers.
- Task 3: a table says `$Trainer.pokedex` maps to `FLAG_SYS_POKEDEX_GET`; a *pytest test*
  checks that flag exists in the fork; the `engine-audit` command that is supposed to own that
  check does not run it.

In each case the fix is not new cleverness — it is deleting the second opinion.

### Scaffolding status

Each task has a stub and a **fully written** test file, so you work test-first: pick a test,
make it pass, move on. A test file whose task you have not started carries a
`pytestmark = pytest.mark.skip(...)` line so the suite stays green. Delete that line when you
start the task.

| Task | Where you work | Tests (written for you) | Skip line? |
|---|---|---|---|
| 1 | **stub**: `src/rpg2gba/beat_floor/reward_ladder.py`, plus edits to `script.py` / `condition.py` | `tests/test_beat_floor_reward_ladder.py` | present |
| 2 | edits only: `beat_floor/walk.py`, `beat_floor/lookup.py` | `tests/test_beat_floor_strip_honoring.py` | present |
| 3 | edits only: `story_state/engine_audit.py` | `tests/test_story_state_engine_audit_flags.py` | present |

Only Task 1 gets a stub module, because it is the only task that adds a new unit. Tasks 2 and
3 are changes to working code — there is nothing to stub without breaking what is already
there, so their contracts live in the task files and the tests.

The tests were checked against a throwaway reference implementation kept outside the repo, so
a failure means your code, not the test.

## Measured facts you are allowed to trust

Everything below was measured on **2026-09-23** against the staged corpus. Each task file
repeats the numbers it needs; they are collected here so you can sanity-check your progress.

| Fact | Value |
|---|---|
| `PROFREWARDS` rungs | 12 entries; index 0 is `[0]` (no reward) and index 11 is `[999]` (a crash workaround, unreachable) |
| Rungs that grant items | 7 rungs, granting **8** items (index 5 grants two) |
| Rungs that grant eggs | 3 (indices 4, 6, 8) |
| `jvGiveReward` call sites | 11, all on `Map050` `ev005` — **7** bare code-`355` script calls, **4** code-`111` type-12 conditions |
| CH01 story rows refusing on the ladder | ~33 branch rows under `map050/ev005/p5` and `/p6` |
| `jvNextReward` call sites | 1 |
| Strip-listed common events | ids **4, 5, 6** (GTS / VT / LOBBY) |
| Code-117 calls to a stripped CE, corpus-wide | **36**, across 11 maps |
| …of those, in **staged** chapters | **3**, all on `Map068` (CH03): `ev009/p0`, `ev011/p0`, `ev013/p0` |
| `ENGINE_ATTRIBUTES` entries | **4** (the plan's ruling text names only 3 — see Task 3) |

## Required reading

- `CLAUDE.md` §4 (operating principles — especially **§4.3 one source of truth** and
  **§4.5 fail loud**) and §5 (Python conventions). **These are graded.**
- `REDERIVATION_PLAN.md` §16.3: the "C8 shape" ruling, and the "C8 stage 4 landed" and
  "C8 stage 6 landed" entries (they establish the patterns Tasks 2 and 3 copy).
- `src/rpg2gba/beat_floor/assertion.py` — the whole data contract, ~150 lines.

## House rules (apply to every task)

- **Python style (CLAUDE.md §5):** type hints on public functions; `list[str]` and `X | None`,
  never `typing.List` or `Optional`; `pathlib.Path`; `logging`, never `print` in `src/`;
  `encoding="utf-8"` on every file read; click for CLIs.
- **Fail loud (§4.5).** On unexpected input, raise or refuse with a precise message. Never
  silently default. A refusal that names *why* is a feature, not a failure — two of these three
  tasks are about making a refusal **more specific**, not about making it disappear.
- **One source of truth (§4.3).** Every task here has an existing table, loader or index you
  must reuse. Each task file names it. Writing a second one loses points even if it works.
- **Never set `RPG2GBA_*` env vars.** Run commands bare (CLAUDE.md §3).
- **Never hand-edit `output/`.** Fix the producer.
- **Running tests.** The full suite stalls (`PROJECT_TODO.md` #111). Run your own test file
  directly, then the whole suite in two halves before you submit:
  ```bash
  .venv/bin/pytest tests/test_beat_floor_reward_ladder.py -q
  python /tmp/c6_suite_half.py 1
  python /tmp/c6_suite_half.py 2
  ```
  Baseline at the start of this assignment: **4282 passed / 16 skipped**.
- **No ROM runs.** Everything lands unit-green; emulator walks wait for the P11 gate.

## Submission checklist

- [ ] Your task's new tests pass, and the existing `tests/test_beat_floor_*.py`,
      `tests/test_story_state_*.py` tests still pass
- [ ] `python -m rpg2gba.story_state engine-audit` still exits 0
- [ ] Refusal counts moved the way your task file predicts — **report the before/after numbers
      in the commit message**, do not just assert they improved
- [ ] A dated **"C8 stage 7 landed"** entry in `REDERIVATION_PLAN.md` §16.3
- [ ] `MEMORY.md` → Current Phase updated with a targeted edit
- [ ] One commit per task, on the current branch (`rederive-ch01-ch04`)

## Rubric summary

| Criterion | Where |
|---|---|
| Correctness against the spec | each task file, "Requirements" |
| **Reuse of the named source of truth** (§4.3) | each task file, "The source of truth you must reuse" |
| Refusals stay loud and get *more* specific, never vaguer | each task file |
| Tests: the named cases exist and are meaningful | each task file, "Tests" |
| Conventions (§4/§5) | all |
| Written answers (short, in the commit message) | each task file, "Questions" |
