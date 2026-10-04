# Task 4 — Locate and order (20 points)

## Goal

Implement `beat_gen/locate.py`:

1. `locate_beats`: planned beats → one `BeatLocationRecord` per **group**, plus `cell`
   refusals for anything that can't be located.
2. `route_order`: a solved route's nodes → (group order, picks).
3. `order_beats`: planned beats → reordered by the route, with each pick applied.

The solve itself happens in between (Task 9 wires it); this task is the adapter on both
sides of it.

## Reuse first: most of this pipeline already runs

Read `routing/locations.py` from `derive_locations` to the end. For **disposition**-named
beats (`beat:B4`) the repo already does:

```
manifest rows ─► cell_for_row ─► choose_routing_point ─► BeatLocationRecord
                                             chapter_from_locations(records) ─► Chapter ─► solve_route(candidates=…)
```

`routing/__main__.py`'s `plan` command shows the `candidates=` wiring. Your `locate_beats`
builds the same `BeatLocationRecord`s from **planned** beats instead. After that, the existing
`chapter_from_locations` and `solve_route` need no changes.

## The two gaps you fill

- **Branch rows.** `cell_for_row` refuses them. An arm is located through its page: same
  map, same cell, same approach candidates, **but the arm's own `row_id`** on the candidate,
  so the record still says which rows it covers.
- **Seam rows.** Also refused. Call `seam_fn(row)` (Task 3). The first crossing is the
  record's cell, and **every** crossing becomes an `ApproachCandidate`, so the solver can
  pick among them. Give each candidate a `side` label that stays distinct and readable in the
  review doc.

## Rules the tests pin

- The record key is the **group** (`beat_id=group`), and records come in first-appearance
  order. A group's rows are all its beats' rows, in beat order.
- If **any** row in a group can't be located, the whole group is refused (every row gets a
  `cell` refusal; the failing one keeps its error text in `detail`), and the group gets no
  record. A half-located group would let a beat claim a row nobody can reach.
- `order_beats` moves whole groups, keeps the in-group order, and applies each pick as
  `approach_prefer` on **every** beat of the group. Existing kwargs survive, and kwargs stay
  sorted (`PlannedBeat` will refuse otherwise).

## Hints

- `choose_routing_point` already decides which of a group's cells represents it (the
  **terminal** row: read its docstring for why). Don't re-decide it.
- `rows_by_id` is the **whole manifest**, not just owned rows. Why does that matter for an
  arm whose page was refused?
- `dataclasses.replace(beat, kwargs=make_kwargs(**{**dict(beat.kwargs), "approach_prefer": side}))`
  is one way to add a kwarg to a frozen beat.
- `route_order` is about five lines. The committed `reference/routes/CH05.route.json` has
  no picks at all. Why not? (Look at what `chosen_approach` requires.) Q2.

## Tests

`tests/test_beat_gen_locate.py`: the group record, arm-through-page, seam candidates, the
group-refusal rule, ordering, `route_order` on a synthetic route and on the real CH05 file,
`order_beats` including its two failure modes, and the real CH05 check (14 groups, 0
refusals).

## Questions (commit message)

1. Why one record per *group* and not per beat? What does the solver actually route between?
2. Why does the committed CH05 route have no `chosen_approach` anywhere? What does that mean
   for a warp beat, which needs a press direction (Task 5)?
