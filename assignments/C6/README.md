# Assignment C6 — The Beat Generator

**Course:** RPG2GBA 220 — Code Generation and Test Oracles
**Prerequisite:** C7 (the freeze). Task 3 of C7 (`blocked_obstacle`) is needed before C6 gives
correct answers on the rock chapters (CH01, CH02, CH04). CH05 works without it.
**Weight:** 9 tasks, 200 points
**Authoritative background:** `C6_GENERATOR_PLAN.md` (read §2, then every "Answer" in §4) and
`REDERIVATION_PLAN.md` §16.2 (rulings R1–R13).

---

## What you are building

Today every chapter's playtest module (`playtest/chapters/chNN.py`) is written by hand. C6
replaces the hand with a **generator**: manifest rows in, a `GENERATED — do not edit` Python
module out. It runs as one pipeline, one module per stage, in a new package
`src/rpg2gba/beat_gen/`:

```
manifest rows ─┐
story verdicts ├─► select ─► group ─► locate ─► (route solver) ─► adapt ─► emit ─► chNN.generated.py
floors ────────┘       │        │         │                          │         └──► review ─► CHnn.review.md
                       │        │         └─ seam (legal crossings)  │                        CHnn.route.json
                       └─ refusals + elsewhere ────────────────────────────────────────────► (in the review)
```

| Stage | Module | Question it answers |
|---|---|---|
| 1 | `select.py` | Which rows does this chapter walk, refuse, or leave to another chapter? |
| 2 | `group.py` | Which beat claims each row, and what is it called? |
| 3 | `seam.py` | Where can the player cross a map-edge seam? |
| 4 | `locate.py` | Where is each beat group, and in what order does the solved route visit them? |
| 5 | `adapt.py` | What keyword arguments does each template call need? |
| 6 | `emit.py` | What Python source registers all of that? |
| 7 | `playtest/archetypes/generic.py` | The template for every row no archetype claims |
| 8 | `review.py` | What does the operator read before approving (§9 gate)? |
| 9 | `__main__.py` | The CLI that runs it all, plus the CH05 end-to-end checkpoint |

**`beat_gen/plan.py` is the data contract, and it's complete.** Read it first: `Selection`,
`Refusal`, `Elsewhere`, `PlannedBeat`, `ChapterPlan`. Every stage consumes or produces these.
Like `beat_floor/assertion.py`, it has no logic beyond validation. If you think the contract
is wrong, say so in your commit message. You may change it, but note the change and the reason.

## Scaffolding (2026-09-19)

Every stage has a **stub** (signatures plus contract docstrings; bodies raise
`NotImplementedError`) and a **fully written test file** that starts with a
`pytestmark = pytest.mark.skip(...)` line. Delete that line when you start a task.

| # | File | Tests | Depends on | Points |
|---|---|---|---|---|
| 1 | [`01_select.md`](01_select.md) | `tests/test_beat_gen_select.py` | — | 20 |
| 2 | [`02_group.md`](02_group.md) | `tests/test_beat_gen_group.py` | 1 (real-data test only) | 25 |
| 3 | [`03_seam.md`](03_seam.md) | `tests/test_beat_gen_seam.py` | — | 15 |
| 4 | [`04_locate.md`](04_locate.md) | `tests/test_beat_gen_locate.py` | 1, 2 (real-data test only) | 20 |
| 5 | [`05_adapt.md`](05_adapt.md) | `tests/test_beat_gen_adapt.py` | — | 30 |
| 6 | [`06_emit.md`](06_emit.md) | `tests/test_beat_gen_emit.py` | — | 20 |
| 7 | [`07_generic.md`](07_generic.md) | `tests/test_playtest_generic_template.py` | — | 30 |
| 8 | [`08_review.md`](08_review.md) | `tests/test_beat_gen_review.py` | — | 15 |
| 9 | [`09_cli.md`](09_cli.md) | `tests/test_beat_gen_cli.py` | all | 25 |

Tasks 1, 3, 5, 6, 7 and 8 are independent of each other, so pick whichever you like. The
synthetic tests in 2 and 4 don't depend on anything either; only their final real-data test
needs Task 1 (and 2).

**How far the tests were checked (2026-09-19).** A throwaway reference implementation was
written against every test file in a scratch worktree outside the repo, then discarded.
Results: Tasks 1–8 all green (select 30, group 17, seam 13, locate 12, adapt 33, emit 29,
generic 19, review 8). Task 9 was 8 of 9, and the one failure is a real design gap, written
up in `09_cli.md` as "The blocker you will hit". One test bug was found and fixed before you
got it. So the contract is feasible end to end: CH05 goes from manifest to an importable,
byte-identical generated module. A test can still be wrong, though, because C6 is new design.
If you're convinced one is, argue it in the commit message and change it; don't quietly
weaken your code to pass it.

## Measured facts you'll need (2026-09-19)

| | CH01 | CH02 | CH03 | CH04 | CH05 |
|---|---|---|---|---|---|
| manifest rows | 458 | 171 | 222 | 86 | 43 |
| rows with a non-empty `requires` | 18 | 60 | 18 | 57 | 8 |
| seam rows | 1 | 0 | 1 | 2 | 0 |
| terrain (stair) rows | 0 | 7 | 3 | 0 | 4 |
| `order_dependent` keys | 1 (`switch:104`) | 0 | 0 | 0 | 0 |

- **Story verdicts don't map 1:1 onto manifest rows.** Seam and terrain rows have no verdict at
  all, and `story_state` has verdicts for some events the manifest leaves out. Always iterate
  the **manifest**.
- **`cell_for_row` refuses every branch row** ("unknown row kind 'branch'") and every seam row,
  both by design.
- **Every stair cell is its own RMXP event.** CH05's two staircases are four terrain rows with
  four different `source_event_id`s.
- **The story model says "live" for rows the capability model says are blocked.** CH05's two
  item balls across water are live in the story but need `surf`. Task 1 has to handle this.

## Deliberately NOT in this assignment (C6 part two)

These are C6 deliverables per `C6_GENERATOR_PLAN.md`, but their designs depend on what you
build here, so they'll be scaffolded once part one lands:

- **A5**: derive per-map entry cells from the solved route, and delete
  `_CHAPTER_MAP_START_CELLS` (four consumers run before a route exists).
- **Seed recompute**: re-derive each chapter's seed from the concrete route (the order → reseed →
  re-check fixpoint).
- **A4 direction arms**: a type-6 facing condition pins which side an arm is approached from
  (Bambo walks both arms).
- **B1 double claims**: while hand and generated suites coexist, `RULE_UNREGISTERED_BEAT` and
  `RULE_ARCHETYPE_CONFORMANCE` must tolerate two beats claiming one row.
- **Running CH01–CH04 end to end.** Part one's checkpoint is CH05 (the C1 answer: "CH05, then
  CH01"). CH01 is part two's opener.

## House rules

Same as C7 (`assignments/C7/README.md`, "House rules"): CLAUDE.md §4/§5 conventions are
graded; fail loud; idempotence; never edit `output/` by hand; never set `RPG2GBA_*`; no ROM
runs. Two additions:

- **Determinism is a first-class requirement here**, not a nice-to-have. R7 demands
  byte-identical output. `RowFloor.assertions` is a **frozenset**, so any code path that
  iterates it and emits text needs an explicit sort. Establish that habit in Task 1, not
  when Task 9's idempotence test fails.
- **Reuse before you write.** At least four stages have a near-complete existing helper
  (`crossing_cells`, `derive_locations`/`chapter_from_locations`, `declare_assertions`,
  `_extract_page`). Each task file names the one it expects you to find. Writing a second
  version of an existing detector is the §4.3 failure this project keeps paying for.

## Running tests

```bash
.venv/bin/pytest tests/test_beat_gen_select.py -q          # one task
.venv/bin/pytest tests/test_beat_gen_*.py tests/test_playtest_generic_template.py -q
```

The full suite still stalls (`PROJECT_TODO.md` #111), so run it in two halves before any
commit.

## Submission

- One commit per task, on `rederive-ch01-ch04`, with the task's Questions answered in the
  message.
- After Task 9: a dated "C6 part one landed" entry in `REDERIVATION_PLAN.md` §16.3, and a
  targeted `MEMORY.md` → Current Phase edit.
- The CH05 review doc (`output/beats/CH05.review.md`) is a **build-agent report, not an
  operator gate** at this stage (C6 plan C1 answer). Read it yourself and note anything that
  looks wrong.
