# Task 3 — Seam: the legal crossing set (15 points)

## Goal

Implement `beat_gen/seam.py`: for a seam row (a whole shared map edge), return every **legal**
crossing `(exit_cell, entry_cell, press)`. The route solver will pick one, and the review doc
shows the pick (C6 plan A1: "resolver + solver picks, inside C6").

## Reuse first

`routing/connections.py` already has the hard part. `crossing_cells(connection, from_graph=,
to_graph=)` maps one edge onto the other with the offset formula, which was cross-checked
against `engine/src/fieldmap.c`, and keeps the pairs where both cells are walkable. Read its
module docstring end to end: it derives the formula and gives a worked example on a real
seam. Your module adds two things:

1. `connection_for(row)`: a `SeamRef` → a directed `MapConnection`.
2. The **landing-open** filter: after arriving on `entry_cell`, the cell one more step in
   the same direction must be walkable too. Otherwise the player lands against a wall.

## Why the landing filter exists

A1 names it: "the Kevlar x=31/x=32 case". On the Kevlar Town → Route 2 seam (`map031/seam/N/map035`;
*corrected 2026-09-21: this said "Route 1 → Route 2", but map031 is Kevlar Town*),
column 31 is walkable on both sides, but the tile just past the landing is a wall. Column 32
is fine. `test_real_kevlar_seam_x31_closed_x32_open` pins exactly that. Load both maps with
`traversal.graph.build_map_graph` and look for yourself before you write the filter.

## Hints

- `connections.py` has a private edge-letter → `Direction` table. Reusing a private name
  across modules is a judgment call that the repo already makes in places (`terrain.py`
  imports generator privates). Either reuse it with a comment, or write the four-entry
  mapping and say why. Don't write both.
- `press` is the D-pad direction held to cross: a north seam is crossed pressing `UP`.
  `Direction` already knows its own (dx, dy). Check `traversal/direction.py` before you
  write a step table.
- `crossing_cells` **raises** when the edges don't overlap and **returns empty** when
  they overlap but everything is walled. Keep that distinction (the tests pin both): one is
  bad data, the other is a legal-but-uncrossable seam that becomes a `cell` refusal in Task 4.
- The result must be sorted. `SeamCrossing` is `order=True`, so `sorted()` just works.

## Tests

`tests/test_beat_gen_seam.py`: the field mapping, all four directions, offset shift, walled
exit/entry, a closed landing, empty vs raise, and the real Kevlar seam (28 legal crossings,
x=31 excluded).

## Questions (commit message)

1. Explain the offset formula in your own words, using the Kevlar seam's numbers.
2. The landing filter looks one step past the edge. Is one step always enough? Construct (or
   find) a case where the landing is open but the player still can't get anywhere useful. Is
   that the seam resolver's problem or the route solver's?
