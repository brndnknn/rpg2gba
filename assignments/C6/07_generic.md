# Task 7 — The generic template (30 points)

## Goal

Implement `playtest/archetypes/generic.py`: the template R11 calls "the floor for every row".
It registers beats for every row no archetype claims. It pays three named debts (C6 plan
part #4): the trainer approach-cutscene gaps, unclaimed branch arms, and C1's pinned `b1`.
It also provides the three row-level shapes (`obstacle_beat`, `stair_beat`, `seam_beat`).

Also add one public method to `playtest/chapter.py`: `ChapterBuilder.claimed_rows() ->
frozenset[str]`. `skip_claimed` needs it, and reaching into `builder._beats` from another
module is the thing a public method exists to prevent.

## The design, already fixed in the stub

- `steps_for(floor)` is **pure**: the ordered list of checks a row's floor implies. It's
  offline-testable.
- `STEP_HANDLERS[kind](emu, beat_name, step)` drives the emulator for one step. Only a ROM
  walk (P11) exercises it.
- **Honesty** (C5 ruling (c)): declare only what the body executes. Here that's the pinned
  invariant `set(STEP_HANDLERS) == GENERIC_EXECUTED_KINDS`, and registration declares through
  `declare_assertions(rows, executed_kinds=GENERIC_EXECUTED_KINDS, template="generic")`,
  the same function the other five templates use.

## Your decision: `GENERIC_EXECUTED_KINDS`

The tests require `trigger`, `completes` and `text`, and forbid the row-level kinds. Past
that it's your call, and it's the most consequential call in C6. Each kind you add raises
coverage, but it also needs a handler you can defend. Look at `flavour_npc.py`'s `talk` body
for how existing templates check text and self-switches, and at `emulator.py` for what
can be read: `flag`, `var`, `bag_item_quantity`, `object_event`, `map_location`. A kind you
leave out isn't lost. It shows up as `floor_uncovered` in the checker, which is exactly how the
trainer debt got found.

## Registration rules

- **Floors first**: raise `ValueError` naming any refused row *before* registering anything.
- **Location**: the owning page's approach cell via `routing.locations.cell_for_row`, using
  `approach_prefer`'s candidate when given. Arms are located through their page (Task 4 had
  the same rule).
- **`skip_claimed`**: drop rows `builder.claimed_rows()` already has. Register nothing if
  none remain.
- `obstacle_beat`: declares the `blocked_obstacle` assertions only, and checks the capability.
  Location = the first rock's cell.
- `stair_beat` / `seam_beat`: declare their rows' `stair_crossing` / `seam_crossing`.
  `seam_beat` takes exactly one row.

## Two traps the reference implementation fell into

Both came up while checking these tests (2026-09-19), and the tests can't catch either one.

- **The three row-level bodies must actually execute what they declare.** `obstacle_beat`
  declares `blocked_obstacle`, so its body has to walk up to each rock, press A and try to
  step onto it, then assert the rock is still there and the player hasn't moved. A body that
  only walks up is exactly the dishonesty `STEP_HANDLERS` exists to prevent in the generic
  body. Nothing offline can check it, so your commit message should say, for each of the
  three, which declared param each line of the body checks.
- **Flag and var names go through the registry. Always.** A `switch_write` handler needs the
  `FLAG_*` name for a switch id. Formatting one yourself (`f"FLAG_SWITCH_{id}"`) breaks
  CLAUDE.md §6's hard rule: "Every flag/var name goes through the registry — never hardcode
  one". Find how `conversion_agent/flag_registry.py` names a switch and a self-switch
  (`self_switch_flag_name` exists) and use that. If no name can be found, the handler raises;
  it doesn't guess.

## Hints

- `steps_for`'s sort key: `trigger` first and `completes` last, even though both have
  `list_index -1`. A key tuple like `(bucket, list_index, kind, repr(params))`, where `bucket`
  is 0/1/2, does it. The `repr(params)` tiebreak is what `coverage.uncovered` already uses.
  Look there.
- The body for `generic_beat` is a loop over `steps_for(floor)` per row, calling handlers.
  Walk up and interact **once** for the page, not once per row. Arms run inside the same
  interaction.
- For the MAP_* constant of a Uranium map id there is an existing lookup. Find it
  (`routing/locations.py` uses one) rather than parsing the constants file again.
- The trainer debt: after this task, does the checker actually count a generic beat's
  declarations toward the trainer's rows? Read `chapter_manifest/floor_model.py` and find
  out whether declarations from two beats claiming one row are unioned. Q3.

## Tests

`tests/test_playtest_generic_template.py`: the honesty contract (three tests), `steps_for`
ordering, filtering, refusal and determinism, `claimed_rows`, `generic_beat`'s
rows/assertions/location/`skip_claimed`/refusal, `obstacle_beat` success and two failures,
and `stair_beat`/`seam_beat` against real floors.

## Questions (commit message)

1. Which kinds did you put in `GENERIC_EXECUTED_KINDS`, and for one kind you *left out*, what
   would its handler need that the emulator API doesn't give you today?
2. Why must `steps_for` be pure, and what would you lose by folding it into the handler loop?
3. Does the checker union declarations across beats that claim the same row? What does your
   answer mean for C5's six `floor_uncovered` trainer errors?
