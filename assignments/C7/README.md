# Assignment C7 — Freezing the Hand-Written Beat Suites

**Course:** RPG2GBA 210 — Data Pipelines and Test Oracles
**Weight:** 3 tasks, 100 points total
**Prerequisites:** Python 3.11 dataclasses, pytest, click, reading JSON, `git` basics
**Estimated effort:** Task 1 ≈ 3–4 h · Task 2 ≈ 2–3 h · Task 3 ≈ 4–6 h

---

## Background (read this first)

Chapters CH01–CH05 each have a **hand-written playtest module**
(`src/rpg2gba/playtest/chapters/chNN.py`). Each module is a list of **beats**: a beat is a
function that drives the emulator and asserts something about the game. A beat can also
**claim rows**. A row is one line of the chapter manifest, usually a single RMXP event page,
with ids like `map032/ev014/p0`.

A later step (C6) will **generate** these suites from the RMXP source. Before that happens we
must freeze what the hand suites cover, so the generated suites can be graded against them.
The grading rule (see `REDERIVATION_PLAN.md` §16.3, "R12 AMENDED 2026-09-17"):

1. every row a hand beat claimed must be claimed by some generated beat, and
2. every generated beat's assertions must be ⊇ that row's **floor**. The floor is the set of
   assertions that the RMXP source implies (`src/rpg2gba/beat_floor/`).

Rule 1 only works for beats that claim rows. **26–27 hand beats claim none.** Nobody grades
those automatically, so each one must be ruled on by hand. Separately, one class of those
rowless beats ("this rock can't be smashed yet") lacks the floor kind it needs. You will add
that kind.

## The three tasks

| # | File | What you build | Points |
|---|---|---|---|
| 1 | [`01_freeze_capture.md`](01_freeze_capture.md) | A freeze module + CLI that writes and checks `reference/frozen/hand_beats_ch01-ch05.json` | 35 |
| 2 | [`02_residue_ledger.md`](02_residue_ledger.md) | A hand-authored ledger ruling on every rowless beat, enforced by Task 1's `check` | 25 |
| 3 | [`03_blocked_obstacle.md`](03_blocked_obstacle.md) | A new `blocked_obstacle` floor kind in `beat_floor/` | 40 |

**Order:** Do 1 before 2, because Task 2's ledger is validated by Task 1's `check` command.
Task 3 is independent and can be done at any point.

### Scaffolding status (2026-09-19)

Every task now has a stub module and a **fully written** test file, so you work test-first:
pick a test, make it pass, move on. A test file whose task you haven't started carries a
`pytestmark = pytest.mark.skip(...)` line so the suite stays green. Delete that line when
you start the task.

| Task | Stub (yours to fill) | Tests (written for you) | Skip line? |
|---|---|---|---|
| 1 | `src/rpg2gba/playtest/hand_freeze.py` | `tests/test_hand_freeze.py` | **removed**: live now |
| 2 | same module, `validate_residue` | `tests/test_hand_freeze_residue.py` | present |
| 3 | `src/rpg2gba/beat_floor/obstacle.py` (+ edits to `assertion.py`, `walk.py`) | `tests/test_beat_floor_obstacle.py` | present |

The tests were checked against a throwaway reference implementation (kept outside the repo),
so a failure means your code, not the test. The one exception is a test that reads **your**
hand-authored data (`test_residue_ledger_complete`), which is red until that data exists.

Two measured corrections came out of writing the tests. Both are recorded in the task files:
the own-beat total is **111, not 91** (Task 1, Q4), and the build directory is
**`output/uranium-build/`, not `output/`** (Task 3).

## Required reading

- `CLAUDE.md` §4 (operating principles: fail loud, idempotence, one source of truth) and §5
  (Python conventions). **These are graded.**
- `REDERIVATION_PLAN.md` from "C7 and C6 swapped, 2026-09-17" through the "DECIDED 2026-09-18"
  table (around lines 1916–2063).
- `src/rpg2gba/beat_floor/assertion.py`: the whole file is only about 150 lines.

## House rules (apply to every task)

- **Python style (CLAUDE.md §5):** type hints on public functions; `list[str]` and `X | None`,
  never `typing.List` or `Optional`; `pathlib.Path`; `logging`, never `print` in `src/`;
  `encoding="utf-8"` on every file read; click for CLIs.
- **Fail loud (§4.5).** On unexpected input, raise with a precise message. Never silently
  default or skip.
- **Idempotence (§4.2).** Running `write` twice must produce byte-identical output.
- **Never hand-edit generated output** (`output/`). The frozen file you write in Task 1 lives
  in `reference/frozen/`: it's committed, and it's produced by your tool, never typed by hand.
  The ledger in Task 2 *is* hand-authored, and that's the only file in this assignment that is.
- **Never set `RPG2GBA_*` env vars.** Run commands bare (CLAUDE.md §3).
- **Running tests.** The full suite stalls (`PROJECT_TODO.md` #111). Run your own test files
  directly, then run the whole suite in two halves before you submit, for example:
  ```bash
  .venv/bin/pytest tests/test_hand_freeze.py -q
  .venv/bin/pytest tests/test_beat_floor_obstacle.py tests/test_beat_floor_walk.py -q
  ```
- **No ROM runs.** Everything here lands "unit-green". Emulator walks wait for the P11 gate.

## Submission checklist

- [ ] All new tests pass, and the existing `tests/test_beat_floor_*.py` tests still pass
- [ ] `write` run twice gives an identical file (`git diff --stat` is empty after the second run)
- [ ] `check` exits 0 on a clean tree
- [ ] A dated **"C7 landed"** entry in `REDERIVATION_PLAN.md` §16.3, and the C7 row in the
      §16.3 step table marked DONE
- [ ] `MEMORY.md` → Current Phase updated with a targeted edit (next step becomes C6)
- [ ] One commit per task, on the current branch (`rederive-ch01-ch04`)

## Rubric summary

| Criterion | Where |
|---|---|
| Correctness against the spec | each task file, "Requirements" |
| Tests: the named cases exist and are meaningful | each task file, "Tests" |
| Conventions (§4/§5) | all |
| Written answers (short, in the commit message or PR notes) | each task file, "Questions" |
