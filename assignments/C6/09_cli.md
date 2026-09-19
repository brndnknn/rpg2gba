# Task 9 — The CLI and the CH05 checkpoint (25 points)

## Goal

Implement `build_plan` and `write_outputs` in `beat_gen/__main__.py` (the click wiring is
done), and get CH05 through end to end:

```bash
.venv/bin/python -m rpg2gba.beat_gen generate --chapter CH05
# -> output/beats/ch05.generated.py, output/beats/CH05.review.md, output/beats/CH05.route.json
```

This is C6 plan C1's checkpoint: "CH05 regenerates and diffs acceptably against its hand
module and `CH05.route.json`". It's a build-agent report, not an operator gate.

## build_plan, stage by stage

1. **Load**: manifest rows, the story chain up to the chapter, floors, archetype matches, and
   the predecessor (`reference/chapters.json` via `chapter_atlas.binding.load_binding`).
2. **Select** (Task 1) and **group** (Task 2).
3. **Adapt, source half** (Task 5): merge `archetype_kwargs` into every archetype beat's kwargs.
4. **Locate** (Task 4), with real functions: `cell_for_row`, but **wrapped** so a warp beat's
   row gets `warp_candidates` (Task 5) as its approach candidates; `seam_crossings` (Task 3)
   over `build_map_graph`; and the MAP_* lookup.
5. **Solve**: `chapter_from_locations(chapter_id, records)` → `solve_route(...)` with
   `candidates=` built from each record's approach candidates. Copy the argument assembly
   from `routing/__main__.py`'s `plan` command (graphs, overlays, world, map ids,
   occupancy). Don't re-derive it.
6. **Order** (Task 4) and **adapt, route half** (Task 5): for every beat, turn its
   `approach_prefer` into `route_kwargs(template, side)`. **If the route made no pick** for a
   group (one candidate means no choice, hence no `chosen_approach`), fall back to that
   group's only candidate. A warp must never reach the emitter without a direction; a test
   checks this.
7. Return a `ChapterPlan` with the refusals from select **and** locate, the elsewhere list,
   the story's `order_dependent`, and the route.

## write_outputs

Three files in a fixed order: `emit_module`, `render_review` (with `floor_for_row` or the
chapter's floor dict as the lookup) and `write_plan`. All must be byte-identical on re-run.

## Hints

- Build it **one stage at a time in a REPL** against CH05 before writing the function. Each
  stage's output is plain data you can print.
- **Groups must stay contiguous.** `ChapterBuilder.build()` rejects a group split by
  another group's beat. `order_beats` guarantees it, and a test double-checks it against
  the route.
- The route file you write goes to `output/beats/`, **not** `reference/routes/`. C9 owns
  that move, and `reference/routes/CH05.route.json` belongs to the hand module until then.
- If the solver raises, read its message before touching anything. `RouteSolverError`
  messages name the group and the reason, and a common cause is a location record whose
  cell isn't walkable. That's a Task 4/5 bug, not a solver bug.
- **Diff against the hand module** once it runs: `load_chapter("CH05")` vs your generated
  module. Same rows claimed? Where do they differ? Put the answer in Q1.

## The blocker you will hit (found by the reference run, 2026-09-19)

With Tasks 1–8 done and the recipe above followed, 8 of the 9 CLI tests pass. The ninth,
`test_generated_module_imports_and_claims_every_owned_row`, fails **at import** on the
exit warp `m037e002_warp` (Cave 2F → map 40, Nowtoch City, which is **CH06's** map):

```
ValueError: warp_cell: MAP_NOWTOCH_CITY has 2 distinct warp exits to MAP_PASSAGE_CAVE_2F:
cell=(68, 43) event_id=19, cell=(68, 43) event_id=19 -- disambiguate with event_id=
```

Two separate things are wrong here. Work out both before you fix either.

1. **The design gap (yours to decide).** `route_kwargs("warp", …)` makes every warp a round
   trip, and a round trip makes `warp_beat` look up the *return* warp on the destination
   map. But this warp leaves the chapter: its destination is the next chapter's map, and it
   isn't in the ROM this chapter builds. Read how the hand module handles the same row (B11
   in `ch05.py`, and its comment). Then decide which stage should know that a warp is a
   **chapter boundary**, and what a boundary warp's beat should do instead. This is Task 5
   Q3 made concrete. Whatever you decide must still leave the row claimed, with its floor
   declared.
2. **A latent bug in pre-C6 code.** The two "distinct" exits are identical. Map 40's
   event 19 carries the same warp on more than one page, and nothing deduplicates identical
   `(cell, event_id)` exits when `traversal` builds `warp_exits`. Fixing that is legitimate
   (it's a real bug, and `cells.py`'s "zero/one/many" rule is being fooled by a duplicate).
   But fixing *only* that would leave you round-tripping into a map the chapter doesn't
   build. Q3.

## Tests

`tests/test_beat_gen_cli.py`: CH05 has zero refusals; the plan shape (20 beats, the two surf
items blocked, a route); groups contiguous and in route order; every warp has a direction;
deterministic `build_plan`; the three artifacts; byte-identical re-run; the generated module
**imports** and claims every planned row with declared (non-`None`) assertions; the route
file loads; and **grading against the C7 freeze**: every frozen CH05 hand row on CH05's own
maps is claimed by the generated suite (R12 amended, rule (a)).

## Questions (commit message)

1. The diff: which rows does the hand CH05 claim that the generated one doesn't, and the
   other way round? For each difference, is it a generator gap, a hand-suite quirk, or a
   ruling (look at `REDERIVATION_PLAN.md` §10 R2/R3 for the `map035` rows)?
2. The freeze test only checks hand rows **on CH05's own maps**. Why is that the right
   scope for this checkpoint, and what does C9 need to do about the rest?
3. The boundary-warp blocker: which stage did you put the decision in, what does the
   boundary beat do now, and did you also fix the duplicate-exit bug? If you did, where, and
   what test pins it?
4. Compare your solved route's group order with the hand route's
   (`B1, B2, B3, B5, B4, B8, …`). Where do they differ, and does R12 care?
