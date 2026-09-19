# Task 8 — The review doc (15 points)

## Goal

Implement `beat_gen/review.py`: `ChapterPlan` → `CHnn.review.md`. C6 plan C2 made this doc
part of the §9 per-chapter boot gate: the operator reads and approves it before a generated
module replaces a hand one. After group A's answers, it's the **only** human-visible record
of the solver's picks (seam cell, stair start, warp press side, approach side,
order-dependent writes). A pick the doc hides is a pick nobody approved.

## Required sections, in this order

| Section | Must show |
|---|---|
| `# CHnn …` title | the chapter |
| `## Summary` | counts: beats, groups, rows claimed, refusals, elsewhere, offline-eligible rows |
| `## Order` | every beat in plan order: name, template, group, row count, **the pick** (`approach_prefer`, or a warp's `direction`) |
| `## Assertions` | per beat: its rows' floor kinds, and whether each row is **offline**-checkable or needs the **ROM** (`RowFloor.offline_eligible`) |
| `## Refusals` | grouped by blocker in the fixed order `#109`, `C8`, `story-state`, `floor`, `cell`; each with row, reason, detail |
| `## Elsewhere` | row, status, owner or required capability |
| `## Order-dependent writes` | each key, the **order taken** (writers in the order the plan runs them), and the value that lands |

An empty section says so ("none"). A silently empty section reads the same as a doc that
forgot the section.

## The one computation: order-dependent writes

C2 found one real case in the corpus: CH01's `switch:104`, written `False` by the lab page and
`True` by Auntie. Either order is legal, so the order is C6's to choose (B3's answer: "the
solver decides, and every instance is listed"). For each `OrderDependentKey`:

1. find the planned beat that claims each writer row, and sort the writers by that beat's
   position in `plan.beats`;
2. the **last** writer's value lands. Read it from that writer's floor: the `switch_write`
   whose `switch_id` matches the key.

Show the writers in that order and the landing value. The test checks that the order matches
the plan, not `key.writers`.

## Hints

- Decide your table format once (a markdown table for Order, bullet lists for the rest) and
  keep row order deterministic. Everything you iterate that came from a set needs a sort.
- The key string is `"switch:104"`. Parse it; don't pattern-match the whole string. What else
  might a key look like? (`story_state/model.py`'s `_state_key_repr` knows.) Handle what you
  must and raise on the rest.
- `floor_lookup` is injected so the tests can pass a dict's `__getitem__`. Keep it that way.

## Tests

`tests/test_beat_gen_review.py`: title and section order, determinism, the pick on the Order
line, kinds plus ROM/offline, refusal grouping, elsewhere details, the order-dependent write
(order taken, landing value), and non-empty "empty" sections.

## Questions (commit message)

1. Read your generated `CH05.review.md` (after Task 9) as if you were the operator. What's
   the one thing you'd want added before you'd approve a chapter from it?
2. Why does the doc have to show picks the solver made "uncontroversially", like a warp with
   only one walkable side?
