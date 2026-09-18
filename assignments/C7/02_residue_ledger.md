# Task 2 — The Residue Ledger (25 points)

## Goal

Some hand beats claim **no rows**. Row-coverage grading can't see them, so anything they
check would be silently lost when the hand suites are eventually removed. For each rowless
beat, decide where its guarantee lives now, and record that decision in a hand-authored
ledger that Task 1's `check` enforces.

This task is mostly **judgment**, and very little code. Reading beat bodies is the work.

## Learning objectives

- Classify test cases by *where their oracle comes from* (source data, a state model, a
  build-time check, or nowhere yet)
- Encode decisions in data that a machine can enforce, so a missing decision is a failure
  rather than a TODO
- Reconcile a measured number against a documented one, and correct the document

## The ruling vocabulary

These come from the operator rulings in `REDERIVATION_PLAN.md` ("DECIDED 2026-09-18" table,
around line 2047, and the triage just before it). Use exactly these strings:

| `ruling` | Meaning | Required extra fields |
|---|---|---|
| `arrival_floor` | Covered by the `warp` floor kind (destination, direction, `arrives_on_door`, C5b) | `rows`: the warp row(s) that cover it |
| `bgm_debt` | BGM check. Named debt tied to `PROJECT_TODO.md` #22; every header is `MUS_LITTLEROOT` today, so the check is vacuous | — |
| `blocked_obstacle` | Field-move obstacle without its capability. Covered by Task 3's floor kind | `rows`: the obstacle rows |
| `state_model` | A second or repeat interaction reaches a different page. Covered by flooring that page under the highest-live-page rule (R6) | `rows`: the page(s) now in force |
| `covered_elsewhere` | Re-checks a row another beat already claims | `rows` |
| `build_check` | The defect class is caught at build time, not by a beat (e.g. `connections.py`: unminted/out-of-build target) | `cites`: file or function |
| `retired` | Explicitly retired by an operator ruling | `cites`: plan line |
| `not_residue` | A harness technique (`field_locked()`) or a read that verifies an existing kind (party reads → `pokemon_grant`) | — |
| `open` | None of the above fits. **This is allowed**, but it's a decision you still owe | `question`: one sentence |

Every entry also carries a `note` (one sentence, mechanical, no story content).

## File format — `reference/frozen/hand_beats_residue.json`

```json
{
  "schema": 1,
  "entries": {
    "CH03:B25": {
      "ruling": "retired",
      "cites": "REDERIVATION_PLAN.md §16.3 DECIDED 2026-09-18, ch03.B25 row",
      "note": "Map-edge wall column; void/crash class moved to connections.py build checks."
    },
    "CH03:B31": {
      "ruling": "bgm_debt",
      "note": "Asserts arrival BGM equals the map header; vacuous until #22 maps Uranium BGM."
    },
    "CH01:N4": {
      "ruling": "blocked_obstacle",
      "rows": ["map032/ev014/p0", "map032/ev015/p0", "map032/…"],
      "note": "Three rocks refuse to break without Rock Smash and stay impassable."
    }
  }
}
```

Keys are `"<chapter>:<beat name>"`. The three entries above are **worked examples**. You may
keep them, but verify the `rows` for `CH01:N4` yourself. `CH01.dispositions.json` has the
rocks with `"negative_beat": "N4"`, which is the fastest way to find them.

## The beats to rule on

Measured 2026-09-18 by parsing every `@….beat(...)` decorator. This is a starting list, not
gospel (see R3).

| Beat | file:line | What the body checks (mechanically) |
|---|---|---|
| CH01:B1 | ch01.py:273 | new save spawns on the house 1F map; running-shoes flag not yet set |
| CH01:B6 | ch01.py:615 | an intro dialogue reaches a yes/no prompt without unlocking the field early |
| CH01:B9 | ch01.py:736 | a scene runs straight into a trainer battle; after winning, a quest var = 1 and the starter flag is set |
| CH01:N4 | ch01.py:835 | three Rock Smash rocks block movement, don't erase, and start no encounter |
| CH01:B14 | ch01.py:971 | re-crossing the ceremony trigger tiles is a no-op (no lock, no quest-var change) |
| CH01:B15 | ch01.py:1002 | chapter-end checkpoint: quest var still 4 |
| CH02:B4 | ch02.py:1337 | walking Route 1 grass eventually starts a wild (not trainer) battle |
| CH02:B14 | ch02.py:1545 | two already-defeated sight trainers don't rebattle or turn |
| CH02:N2 | ch02.py:1786 | two Route 1 boulders refuse Rock Smash and keep blocking |
| CH02:B17 | ch02.py:1799 | walking to the north boundary leaves the player still on Route 1 |
| CH03:B27 | ch03.py:622 | a warp lands at the exact cell, facing away from the return warp |
| CH03:B1_return | ch03.py:732 | re-crosses a warp other beats already claimed |
| CH03:B30 | ch03.py:830 | a building door arrival facing |
| CH03:B31 | ch03.py:841 | that building's arrival BGM |
| CH03:B28 | ch03.py:1050 | another building door arrival facing |
| CH03:B29 | ch03.py:1061 | that building's arrival BGM |
| CH03:N4 | ch03.py:1144 | a mart purchase with insufficient money is refused; money/bag unchanged |
| CH03:B32 | ch03.py:1300 | a third building door arrival facing |
| CH03:B33 | ch03.py:1315 | that building's arrival BGM, then exits |
| CH03:N2 | ch03.py:1468 | repeatedly refusing an offer increments a var by 1 each time |
| CH03:N7 | ch03.py:1581 | two boulders refuse to move without Strength |
| CH03:N6 | ch03.py:1754 | every reachable warp resolves to a built `MAP_*` constant |
| CH03:B25 | ch03.py:1765 | a map's north edge is a clean wall, not a void |
| CH04:B6 | ch04.py:835 | two rockslide rocks block, don't erase, start no encounter |
| CH04:B7 | ch04.py:881 | the player stops one tile short of a cave mouth (crossing is CH05's) |
| CH04:B15 | ch04.py:1066 | walking grass eventually starts a wild (not trainer) battle |

CH05 has none.

## Requirements

### R1 — One entry per rowless beat, no extras

Extend Task 1's `check` so that it fails when:
- a frozen beat with `rows == []` has no ledger entry,
- a ledger key names a beat that isn't frozen, or that *does* claim rows (stale entry),
- a `ruling` isn't in the vocabulary,
- a required extra field is missing (see table),
- any row id listed in `rows` doesn't exist in that chapter's manifest.

Put the validation in a pure function, `validate_residue(frozen, ledger, manifest_ids) -> list[str]`,
that returns problem strings. `check` prints them and exits 1 if there are any.

### R2 — Rule on every beat

Read each body (the file:line is given). Pick a ruling. **Prefer the most specific one:**
`covered_elsewhere` with real rows beats `open`. You will not be able to place every beat in
the existing categories. That's expected, and `open` is the honest answer; *don't stretch a
category to avoid it.* Wild-encounter beats and boundary non-crossings are likely candidates
for real thought.

### R3 — Reconcile the count

`REDERIVATION_PLAN.md` (around line 1996) says **27** rowless beats: ch01 6 / ch02 4 / ch03 14 /
ch04 3 / ch05 0. The re-measurement above finds **26**, with ch03 at 13. The plan's triage
also names `ch03.N1`, `N3` and `B12` as no-refire beats. Work out which number is right
(your Task 1 freeze file is the authority now) and add a dated correction next to the plan's
table. **Don't** silently rewrite the old number: CLAUDE.md §7 asks for a dated correction.

## Tests (add to `tests/test_hand_freeze.py`)

| Test | Asserts |
|---|---|
| `test_residue_ledger_complete` | `validate_residue` on the committed files returns `[]` |
| `test_residue_missing_entry` | drop one entry → a problem naming that beat |
| `test_residue_stale_entry` | add `"CH05:B1"` (which claims rows) → a problem |
| `test_residue_bad_ruling` | `"ruling": "vibes"` → a problem |
| `test_residue_open_needs_question` | an `open` entry with no `question` → a problem |

## Questions (commit message)

1. How many `open` entries did you end up with? For each, one line on what a future ruling
   would need to decide.
2. `CH03:N2` asserts a var *does* change. Should that beat have claimed a row all along? If so,
   which one, and why does it matter that it didn't?
3. Explain in two sentences why `bgm_debt` beats aren't a coverage gap *today*, even though
   nothing replaces them.
