# C6 — Generator + Solver Integration: Work Breakdown and Decisions Owed

**Written:** 2026-09-17, against `625c8cc9` on `rederive-ch01-ch04`.
**Scope:** step **C6** of `REDERIVATION_PLAN.md` §16.3 — "Generator + solver integration: whole-module
emit, review doc, refusal list, idempotence test" (rulings R1, R4, R7). Everything C1–C5 built is
assumed landed; C7–C10 are out of scope except where they constrain C6.
**Sources:** `REDERIVATION_PLAN.md` §16 (rulings R1/R4/R6/R7/R8/R11/R12/R13 and the C1–C5 "landed"
notes), plus a code audit of `story_state/`, `beat_floor/`, `chapter_manifest/`, `routing/` and
`playtest/` performed 2026-09-17 against this commit.

**Sequencing note, 2026-09-17:** C7 (freeze) now runs **before** C6; see `REDERIVATION_PLAN.md`
§16.3's swap note. Step labels are stable identifiers, not sequence numbers — "C6" still means the
generator everywhere in this document. The swap closed question B1 below.

**All §4 questions were answered 2026-09-18** (group A in light of C5b, then B2/B3/C1/C2). Each
answer is recorded under its question with the measurements taken first. The original framing
follows. **This document is a breakdown plus open questions.** Where the
evidence argues for an option it is marked *(leans)* — still yours to take or reject. Answer in-file
under each question; the build agent reads your answers from here.

---

## 1. Audited state — measured 2026-09-17, not read off status markers

This repo has been burned by decision docs whose prose disagreed with the code. Every row below was
verified against `625c8cc9` today.

| Thing C6 needs | Status | Where |
|---|---|---|
| Story-state model: liveness, `stage` wave number, end state, chapter seeding | **built** (C2) | `story_state/model.py` — `build_chapter_stories`, `ChapterStory`, `RowVerdict` |
| Order-dependence *detection* | **built**, deliberately does not decide | `story_state/model.py` — `OrderDependentKey`; its own docstring defers the choice to "C6's route" |
| Per-command assertion floor, by row id | **built** (C4/C5) | `beat_floor/lookup.py` — `floor_for_row(row_id, *, build_dir=None) -> RowFloor` |
| ⊇-coverage comparison for archetype declarations | **built** (C5) | `beat_floor/coverage.py` — `assertion_key` / `covers` / `uncovered` / `contradicts` |
| Manifest row model incl. branch arms | **built** (C1) | `chapter_manifest/schema.py` — `ManifestRow`, `BranchRef`, `parent_row_id` |
| Location resolution from source data | **built** | `playtest/cells.py` (resolvers, not literals), `routing/locations.py` — `derive_locations`, `cell_for_row` |
| Route order solver (precedence + 2-opt) | **built**, but consumes a `Chapter` | `routing/solver.py` — `solve_route(chapter, chapter_id, …) -> RoutePlan` |
| Route plan serialization | **built** | `routing/plan.py` — `write_plan` / `route_path` |
| Coordinate-literal ban (enforces resolver use) | **built** | `tests/test_chapter_coordinate_literals.py` (AST lint over `playtest/chapters/*.py`) |
| **Any code that writes Python source** | **absent** | zero hits for `ast.unparse`, `codegen`, `emit_chapter`, `emit_beat` anywhere in `src/rpg2gba/` |
| **Bridge from manifest rows → a provisional `Chapter` for the solver** | **absent** | `solve_route` needs beats already registered with `group=`/`rows=` |
| **Seam-row routing point** | **absent by design, raises loud** | `routing/locations.py::cell_for_row` — "a seam beat's routing point must be supplied by hand" |
| **Facing derivation** | **warp arrivals: built (C5b); event approach: built, except direction-conditioned scripts** | *Corrected 2026-09-18 (C5b, `f05f2c72`):* `assertions.facing_for_direction` / `expected_arrival_facing(src_map, src_cell, approach)` / `arrival_landing_cell` derive a warp's arrival facing and door landing cell from the departure warp's staged direction. Facing *toward an event* was already derived before C5b: `archetypes.facing_toward` (used by item_ball/trainer/flavour_npc) and `assertions.talk_to_moving_npc`. The one gap is direction-conditioned scripts; see A4 |
| Review-doc writer for generated beats | **absent** | `chapter_manifest/render.py` renders dispositions, not beat code |
| Route artifacts on disk | **CH05 only** | `reference/routes/CH05.route.json` + `CH05.locations.json`; CH01–CH04 have none |
| Declarative beat assertions (`assertions=`) | **parameter exists, unused** | `playtest/chapter.py:398` accepts `frozenset[FloorAssertion]`; **0 of 91 beats across CH01–CH05 pass it** — `Beat.assertions = None` is documented as the expected state for a hand-written beat |
| Hand-beat corpus size | **91 beats**, 22/18/35/13/5 (**corrected 2026-09-21: 111 registered — 22/19/35/14/21, `reference/frozen/hand_beats_ch01-ch05.json`.** The AST parse counted `@….beat(` decorators only; beats also register through template calls at module level (`warp_beat`, `arrival_nudge_beat`, `whiteout_beat`, the trainer/item templates). CH05 is the bulk — 5 decorators, 21 registered; CH02 and CH04 each gain one `whiteout_beat`. Note the quoted 22/18/35/13/5 sums to 93, not 91. Rowless counts are unaffected) | AST parse 2026-09-17. An earlier `grep -c` said 95; it counted commented-out decorators. **27 of the 91 claim no row at all** — see the residue table in `REDERIVATION_PLAN.md` §16.3 |
| Static beat capture | **partial** | `scripts/freeze_rederivation.py::_beat_dicts` walks `load_chapter(chapter).beats` but captures only `name`/`own`/`group`/`rows` — it does not touch `beat.assertions` |
| `contradicts` in anger | **one working caller** | `playtest/archetypes/__init__.py:152` — checks template `extras` against the floor, fails loud at registration. `checker.py`'s `RULE_FLOOR_*` rules use `uncovered`, never `contradicts` |

**One correction to the earlier record.** The claim that beat coordinates "live only in hand-written
comments" is true of CH01–CH04 and false as a general statement. `cells.py`'s module docstring is
explicit — "A literal `(18, 37)` carries no claim a machine can check… A resolver *derives* the cell
from this build's own decoded output… and FAILS LOUD the moment the data doesn't support the answer"
— and the AST lint structurally forbids the literal pattern from CH05 onward. `CH05.route.json` is
headed "Generated route plan artifact — do not hand-edit," and `CH05.locations.json` carries
per-cell provenance strings naming the resolver call (`event_cell(MAP_PASSAGE_CAVE_1F, ev1)`). The
manifest → `derive_locations` → locations.json → `solver` → route.json pipeline already runs end to
end for one chapter. **This is the single largest reason C6 is a 2–3 session step rather than a 5+
one.**

---

## 2. What C6 must deliver

Obligations with their source lines in `REDERIVATION_PLAN.md`.

1. **Whole-module emit** — `playtest/chapters/chNN.py`, headed `GENERATED — do not edit`, template
   calls in solved order. (R7, L1618/L1637)
2. **Byte-identical on re-run** — §4.2 idempotence, for the module itself, not just intermediate
   JSON. (R7, L1618)
3. **Route artifact** — `reference/routes/CHnn.route.json`. P9 is folded in: "Route plans (P9) become
   a C6 output rather than a separate step." (R7, L1618/L1912-13)
4. **Review doc** — `output/beats/CHnn.review.md`: order, what each beat asserts, sampled vs offline.
   (R7, L1618)
5. **No overrides file** — binding negative constraint. (R7, L1618)
6. **Refusal list** — every unproducible row named with its blocker; the chapter stays red until the
   blocker is fixed upstream or the row carries a real verdict. (R7, L1618)
7. **Solve the order** — turn C2's partial order into one concrete linear route. "C2 builds the
   model; C6 orders it." (L1700) Includes choosing an order for order-dependent conflicting writes —
   "the order is C6's to choose, not an error" (L1716) — and recomputing each chapter's seed from
   the concrete route, because C2's end states are sound over-approximations (L1719). Cyclic
   precedence fails loud naming the cycle. (R6)
8. **All five archetypes plus the generic template**, not flavour NPCs only. (R4, L1615)
9. **Generic template for unclaimed rows and arms** — this is where three parked debts get paid: the
   6 CH05 `floor_uncovered` trainer errors (missing approach cutscene; explicitly "the fix is C6,"
   L1908-10), branch arms no archetype claims (`flavour_npc` claims none, L1874-76), and C1's pinned
   `b1` (L1882). (R11)
10. **Zero hand overrides** — R1, "a hard constraint, not a target." (L1612)

**Explicitly not C6:** freezing hand beats (C7 — which now lands *before* C6 and supplies its grading
target), overwriting CH01–CH05 (C9), the Ruby-subset interpreter (C8; rows needing it refuse by name),
the `offline:` verdict head and ROM sampling (C10).

---

## 3. Work breakdown and sizing

Ordered by dependency. Sizes are relative; the whole step is estimated at **2–3 sessions** given §1.

| # | Part | What it is | Size |
|---|---|---|---|
| 1 | **Provisional-`Chapter` bridge** | Synthesize `BeatGroup`s from manifest rows + archetype matches + `story_state` stages, so `solve_route` has something to order. Locations already resolve, so this is grouping and wiring, not derivation. | **Medium** |
| 2 | **Order solve + seed recompute** | Run the solver; resolve `OrderDependentKey`; recompute the chapter seed from the concrete route; re-check liveness. Likely a small fixpoint (order → reseed → re-check). Cycle → fail loud naming it. | **Medium** |
| 3 | **Source emitter** | `FloorAssertion` / archetype match → Python text: imports, beat bodies or template calls, the `CHAPTER = chNN.build()` tail. Archetype rows are near-free (ch05 registers them as bare parameterized calls). The generic-template path carries the real work. | **Medium** |
| 4 | **Generic template absorbing named debt** | Falls out of #3; pays the trainer approach-cutscene errors, unclaimed branch arms, and C1's `b1`. | **Small-medium** |
| 5 | **Refusal list + red-chapter plumbing** | Aggregate and report. The refusal vocabulary already exists (`Refusal`, `FloorRefusal`, `RowVerdict.status`). | **Small-medium** |
| 6 | **Route artifacts for CH01–CH05** | New output, not new code — `write_plan` / `route_path` exist. | **Small** |
| 7 | **Review doc** | Format over data #2 and #3 already hold. No writer exists today. | **Small** |
| 8 | **Idempotence test** | Cheap as a test; a determinism tax threaded through everything above. `RowFloor.assertions` is a `frozenset` — every emit path needs an explicit sort. Establish the rule in #3 rather than debug it in #8. | **Small** |

---

## 4. Open questions

Answer in-file. Each has a **Question**, the **evidence**, the **options**, and a blank **Answer**.

### Group A — the four inputs geometry cannot derive

**All of group A answered 2026-09-18.** The notes below keep the record in order: the C5b check,
the measurements, then the answer. The net result is zero authoring hints and no hint store. Every
input is either derived or a solver pick from a derived legal set, and the review doc shows every
pick. The answers add implementation work to parts #1–#2 and #7: a seam resolver, the stair
round-trip, mechanism derivation, direction-arm side constraints, and route-derived entry cells in
place of `_CHAPTER_MAP_START_CELLS`.

**Status after C5b, checked 2026-09-18 against `f05f2c72`.** C5b closed **only the arrival-facing
half of A4.** It did not touch seams (A1), warp `mechanism` (A2), stair `side` (A3), or the start-cell
table (A5), so **A0 is still owed.** C5b did change two inputs to it. First, the `warp` floor now
carries each row's code-201 params (`map_id`, `x`, `y`, `direction`, and the new `arrives_on_door`),
and `floor_for_row` reads them by row id. That removes the premise in A2 that "the manifest doesn't
carry the destination": the generator can read it from the floor without a `ManifestRow` schema
change. Second, the build's door-cell set (`walk.load_door_cells`) is now wired into the floor. It
gives a derivation path for `mechanism == "door"` on the *departure* cell too. Per-question notes
follow.

This is the heart of the step. R1 says zero hand overrides is a hard constraint and R7 says "No
overrides file," but four facts a beat needs are documented as *not derivable from map geometry*.
They cannot live as hand edits in a `GENERATED` module. Where they live instead is a schema decision,
and CLAUDE.md §10 puts intermediate-JSON schema changes in the ask-first column.

**A0 — Where do non-derivable authoring inputs live?**
*(This is the one that unblocks A1–A4; answer it first.)*

- **Evidence:** `stair_approach`'s docstring — "`side` is required, deliberately… Which end a beat
  enters from is an authoring claim, not something geometry can decide." `warp.py` requires
  `mechanism` and `direction` for the same reason: `ManifestRow` doesn't carry the code-201
  destination that would settle mechanism, and `MapGraph.warp_exits` records a destination cell, not
  a press direction.
- **Options:**
  1. **Structured fields on `ManifestRow`** — generated half of the manifest, derived where possible,
     explicit where not. Schema change; §10 gate. *(leans — keeps one source of truth per concept,
     §4.3, and the row already carries `SeamRef`/`TerrainRef` of exactly this shape.)*
  2. **Fields on `Disposition`** — the hand-edited half. No generator-schema change, and dispositions
     are already the place a human records a judgement about a row. But it mixes "what this row is"
     with "what verdict it gets."
  3. **A new sidecar** (`reference/authoring_hints.json`) keyed by row id. Cleanest separation,
     worst discoverability, and a fourth file to keep in sync.
- **Question:** which, and does your answer change if a hint is needed for only ~5 rows across
  CH01–CH05 versus ~50?
- **Update 2026-09-18 (C5b):** still open. The hint count is lower than when this was written. Warp
  destination and arrival facing no longer need hints, and door `mechanism` may not either (A2).
  The remaining candidates are seam routing points (A1), threshold/arrow press direction (A2),
  stair `side` (A3), and possibly event-approach facing (A4). The §5 measurement is still unrun.
- **Answer (2026-09-18): no hint store; underivable inputs refuse.** The A1–A5 answers left
  **zero** non-derivable inputs in CH01–CH05. Seam crossing cell, stair end, warp press side and
  event approach side are all solver picks from a derived legal set. The source constrains a pick
  where it cares (the A4 direction arms), and the review doc shows every pick. Mechanism, facing,
  landing cell and entry cells are all derived. So no hint mechanism is built: no `ManifestRow`
  field, no `Disposition` field, no sidecar. If a later chapter hits an input the generator can't
  derive or legally pick, that row refuses by name on the refusal list and stays red until the
  derivation is written. A hint store would be a new ask-first decision (§10), not a default.

**A1 — Seam rows have no resolver at all.**

- **Evidence:** `routing/locations.py::cell_for_row` raises loud for `kind == "seam"`: a seam carries
  a connection direction/offset, not a cell. CH05 has no seam rows, so this has never been exercised
  — CH01–CH04 will hit it.
- **Note:** the count of seam rows across CH01–CH05 is **not yet measured**. That is a measurement
  the build agent should take before you answer, not a question for you.
- **Options:** (a) write a real seam resolver from connection geometry — derive the cell on each side
  from direction + offset; (b) treat the seam routing point as an A0 authoring hint; (c) both — a
  resolver with a hint as the documented override for seams where geometry is ambiguous.
- **Question:** is a seam's routing point genuinely underivable, or has it just never been written?
  If a resolver is feasible, does it belong to C6 or is it its own small step?
- **Update 2026-09-18 (C5b):** unchanged. `cell_for_row` still raises for `kind == "seam"`
  (`routing/locations.py:338`). `cells.seam_cells()` is unrelated: it resolves
  `reference/seam_warps.json` arrow-warp seams, not `connections.json` border rows. Its own
  docstring says so (`cells.py:677`).
- **Measured 2026-09-18:** 4 seam rows in CH01–CH05. CH01: 1, CH02: 0, CH03: 1, CH04: 2
  (`map035/seam/N/map040`, `map035/seam/S/map031`), CH05: 0.
- **Answer (2026-09-18): resolver + solver picks, inside C6.** Write a resolver that returns the
  legal crossing set from connection geometry: edge cells walkable on both sides whose landing is
  open (the Kevlar x=31/x=32 case). The route solver picks the cheapest cell, the same way it
  picks approach sides, and the review doc shows the pick. No authoring hint and no override path.

**A2 — Warp `mechanism` and `direction`.**

- **Evidence:** `warp.py` derives the trigger cell, arrival cell, and expected facing/BGM from staged
  output, but takes `mechanism` (door/threshold/arrow) and `direction`/`return_direction` as explicit
  caller parameters, documented as not derivable.
- **Question:** `mechanism` looks recoverable from the source code-201 command if the manifest carried
  it. Is extending the manifest generator to record the warp destination in scope for C6, or does
  `mechanism` become an A0 hint? And is a default policy (threshold unless the tile is a door tile)
  acceptable, or must every warp be explicit?
- **Update 2026-09-18 (C5b): partly answered, narrower question.**
  - *Destination, no longer a question:* the code-201 destination is now on the `warp` floor, keyed
    by row id. So "extend the manifest generator to record it" is unnecessary, and no schema change
    is needed for it. `warp.py`'s module docstring still says the target "is not on the row". That
    is true of `ManifestRow` but stale as an argument, because the generator reads the floor.
  - *Arrival facing, derived:* it comes from the floor's `direction`, or from the approach for
    retain (0), via `assertions.facing_for_direction`.
  - *Door landing cell, derived:* it comes from `arrives_on_door`.
  - *`mechanism`, still a required caller parameter* (`warp.py:145`). Door-ness of the departure
    cell is now derivable from the same door-cell set C5b wired in, `src_cell ∈ door_cells[src_map]`,
    but nothing does it yet. That leaves threshold vs arrow, which would need a metatile-behavior
    check on the departure tile.
  - *`direction`/`return_direction` (which D-pad is held to cross), still explicit.* C5b made this
    more important: for a retain (0) warp, the held direction *is* the arrival facing.
  - **Remaining question:** can `mechanism` be derived (door from door cells, arrow from tile
    behavior, threshold otherwise)? And is the press direction for threshold/arrow warps derivable
    from the warp cell's position on the map edge, or an A0 hint?
  - *New known gap from C5b:* the template's reciprocal leg does not apply the door exit step,
    because there is no floor for the unclaimed return row. A reciprocal that lands on a door tile
    will fail its exact-position check in-ROM (`REDERIVATION_PLAN.md` §16.3 "C5b landed"). The
    generator will hit this wherever it emits `round_trip=True`.
- **Measured 2026-09-18:** there are 51 non-seam warp rows in CH01–CH05.
  - **46** depart from door-stamped cells (CH01 18, CH02 7, CH03 17, CH04 1, CH05 3).
  - **0** are arrow warps. Arrows exist only as `seam_warps.json` substitutions, and those are
    seam rows.
  - **0** are map-edge thresholds.
  - **4** are event-script warps fired by their own trigger: `map032/ev078/p0` (event touch),
    `map037/ev002/p0` (player touch), and `map049/ev021/p0`, which is action-triggered and has two
    branch arms (direction 0 and 6).
  - **2** refuse for unrelated reasons: `map172/ev004/p2` (text) and `map031/ev049/p0` (Ruby head).
- **Finding:** the door/threshold split in `warp.py` matches nothing in the ROM for these rows. The
  build stamps **every** warp source cell `MB_NON_ANIMATED_DOOR` (`warp_overrides.gen.json`:
  "warp-source + gated-door cells"). The engine treats that as a step-on warp from any direction
  (`IsWarpMetatileBehavior`, `field_control_avatar.c:1029`). The hold-UP `TryDoorWarp` path that
  `assertions.enter_door` models fires only for *animated* `MetatileBehavior_IsWarpDoor` tiles.
  This is why CH05's four hand `warp_beat` calls pass `mechanism="threshold"` on door-stamped cells
  and are correct to.
- **Answer (2026-09-18): derive everything; the solver picks the side.**
  - `mechanism` comes from data: a door-stamped cell or a touch trigger means a step-on crossing.
  - `direction` and `return_direction` are the solver's cheapest walkable approach side, the same
    choice as A1/A3, and the review doc shows the pick. C5b then derives arrival facing and the
    door-exit landing from that approach, and its R5 guard already proves every reachable approach
    lands on walkable ground.
  - The action-triggered device row (`map049/ev021/p0`) goes to the generic template (press A on
    the event), not `warp_beat`.
  - No authoring hint.

**A3 — Stair `side`.**

- **Evidence:** documented as an authoring claim. Geometry gives the legal set; it does not say which
  end the beat means.
- **Question:** can the route solver just *pick* — cheapest side by the same DP it already uses for
  approach sides — and let the review doc surface the choice for your approval? Or is the entered end
  semantically load-bearing in a way a cost function would get wrong?
- **Update 2026-09-18 (C5b):** unchanged. `cells.stair_approach(…, side=)` still requires `side`
  (`cells.py:431`). Its docstring gives the counter-case to a cost-function pick: CH02's B2/B3
  walk each Route 01 staircase in **both** directions, and that is the point of those beats.
- **Measured 2026-09-18:** 14 stair (terrain) rows in CH01–CH05. CH02: 7, CH03: 3, CH05: 4.
- **Answer (2026-09-18): always round-trip.** The generic stair beat crosses from the solver's
  cheapest walkable end and then crosses back, the same idiom as `warp_beat(round_trip=True)`.
  Every staircase is proven in both directions, which covers CH02 B2/B3 by construction, so the
  solver's pick only decides the starting end and cannot hide an untested direction. No authoring
  hint. `cells.stair_approach`'s required `side=` stays as the hand-module contract; the generator
  derives both ends and needs no hint for it.

**A4 — Facing is entirely underived.**

- **Evidence:** nothing in `cells.py`/`locations.py` computes facing; `warp.py`'s `assert_facing`
  only checks an expected value against staged output.
- **Question:** for a beat that approaches an event from a resolved side, is facing simply "toward the
  event" — i.e. mechanically derivable from approach side, and the gap is that nobody wrote the two
  lines? Or are there beats whose facing differs from their approach direction?
- **Update 2026-09-18 (C5b): half closed.** The evidence line above is now false for warps.
  Arrival facing is derived: the explicit departure direction wins, otherwise the approach is
  retained (`assertions.facing_for_direction` / `expected_arrival_facing`). The ch01/ch03 facing
  checks were re-sourced onto it (ch03 B27/B28/B30/B32 → UP, ch01 `B3_up` → RIGHT), and the three
  former hand overrides now follow from source data. That leaves only facing **toward an event**
  on approach.
- **Correction, same day:** facing toward an event is also largely built. The first C5b check
  searched only `cells`/`assertions`/`locations` and missed it.
  - `archetypes.facing_toward(approach, target)` derives the facing from an orthogonal approach
    cell, and `item_ball`, `trainer` and `flavour_npc` all use it.
  - Moving NPCs have a shared `assertions.talk_to_moving_npc`. The `ch02`/`ch03` helpers are
    chapter-local variants of it.
  - The approach side itself is a solver/route pick. CH05's `approach_prefer=` values appear to
    come from its route plan (unverified).
  - The residual gap is scripts that branch on the player's direction (RMXP code 111, type 6).
- **Measured 2026-09-18:** 20 direction-conditioned branches in CH01–CH05.
  - **14** are the stair idiom (`Stairs`/`EVnnn` events on maps 31, 33 and 37), which A3 covers.
  - **6**, on 4 events, make the approach side choose which arm runs:
    - map050 ev5 `Bambo` p2 (right and left; action trigger)
    - map050 ev26 (up; action)
    - map031 ev49 `NurseTut` (up; action; the row already refuses for a Ruby head)
    - map035 ev19 `Trainer(4)` (right; event touch)
- **Answer (2026-09-18): the arm pins the side.** Derive a side constraint from the condition:
  facing RIGHT means approach from the west, and so on. Each direction-gated arm becomes its own
  interaction from the side that selects it, so Bambo walks both the right and left arms. Where no
  arm is direction-gated, the solver picks freely, and `facing_toward` derives the facing as it
  does today. No authoring hint.

**A5 — `_CHAPTER_MAP_START_CELLS`.**

- **Evidence:** a hand-populated `dict[(chapter_id, map_id), frozenset[Cell]]` with citation comments;
  its docstring insists values be "verified (an emulator-observed position, a warp-exit constant), not
  guessed from geometry." It covers chapter *entry* cells only, not beats.
- **Question:** is this a permanent, intentional hand seam — in which case R1's "zero hand overrides"
  should be written down as excluding it, so a later agent doesn't try to "fix" it — or a gap C6 is
  expected to close?
- **Update 2026-09-18 (C5b):** unchanged. The table is still at `chapter_manifest/generator.py:353`
  and still hand-cited.
- **Measured 2026-09-18:** 19 entries.
  - **15** (CH01–CH03) were registered 2026-09-09 under a stated *derived* rule, applied by hand:
    every in-slice code-201 destination into the map, minus self-warps, minus unwalkable cells,
    with a one-component check. Map 73's four doors sit in four components and are the exception.
  - **1** non-warp entry, CH01/49 (7,7): the engine's new-game spawn (`new_game.c:174`), itself a
    source fact.
  - **4** CH04/CH05 entries carry no citation.
- **Answer (2026-09-18): derive in C6 and delete the table.** C6 computes each map's entry cells
  from the concrete route: the chapter start (the previous chapter's end, or the engine spawn for
  CH01) plus the landing cells (`arrival_landing_cell`, which covers door exit steps) of the warps
  and seams the route actually crosses into that map. Liveness is re-checked against those cells
  in part #2's fixpoint, which also settles map 73's multi-component case. R1 stays unqualified,
  with no permanent hand seam.
  - *Implementation consequence:* the table has consumers that run before any route exists:
    `generator.py`'s reachability context, `approach_model.py:92,139`,
    `traversal/reachability.py:408` and `cells.py`'s entry-cell lookup. Each needs a route-derived
    replacement, or to move behind the solve, before the table can go. Size this in part #2.

### Group B — emit mechanics

**B1 — Where does C6's output land?** — **CLOSED 2026-09-17 by the C7/C6 swap.**

*(Corrected 2026-09-24: C9 does **not** overwrite `chNN.py`; it commits the generated suite as
`playtest/chapters_gen/chNN.py` beside it — `REDERIVATION_PLAN.md` §16.3 "C9 rulings".)*
With the freeze landing first, this stopped being a safety question. C9 still owns overwriting
`chNN.py` (one commit per chapter, graded against the frozen file), so C6 emits to
`output/beats/chNN.generated.py` by convention — but nothing irreplaceable is at risk either way, and
the grading target is the frozen JSON rather than an ad-hoc diff against the hand module. No decision
owed.

**Strengthened 2026-09-17 by the R12 amendment:** the hand modules are not deleted when the generated
suite goes green. Both suites coexist until coverage is confirmed, and removing the hand suite is a
separate operator-gated step. So C6's emit is non-destructive by ruling, not just by convention.
Implementation note: while both exist, two beats claim the same rows — confirm
`RULE_UNREGISTERED_BEAT` and `RULE_ARCHETYPE_CONFORMANCE` tolerate that, or scope them per-module.

**B2 — How red is red?**

- **Evidence:** R7 — "the chapter stays red until the blocker is fixed upstream or the row carries a
  real verdict." Upstream refusal counts at C4 landed were non-trivial and several wait on C8, which
  comes *after* C6.
- **Question:** if CH01 emits with, say, 30 refusals all blocked on C8, is that a successful C6 (the
  refusal list is the deliverable, redness is expected and correct) or a failed one? Put differently:
  what is C6's exit criterion — the generator runs and refuses honestly, or the generator produces a
  green chapter?
- **Measured 2026-09-18** (`floor_for_chapter`, rows grouped by first refusal reason): 80 of 980
  rows refuse.
  - CH01: 56 of 458. 29 `text_unnormalizable`, 13 `non_literal_args`, 7 `unknown_script_head`,
    5 `story_state_refusal`, 2 `unclassified_condition`.
  - CH02: 3 of 171. 2 `non_literal_args`, 1 text.
  - CH03: 18 of 222. 13 text, 5 script head.
  - CH04: 3 of 86. 2 `non_literal_args`, 1 script head.
  - CH05: **0** of 43.

  Roughly 43 are #109 text gaps, fixable upstream now. About 30 are script heads or non-literal
  args that probably wait on C8. Many rows carry more than one reason, so fixing #109 alone does
  not clear every row it touches.
- **Answer (2026-09-18): an honest refusal counts as done.** C6 exits when the generator emits all
  five chapters idempotently and every refusing row is on the refusal list, each with a named
  upstream blocker (#109, C8 or story-state). Only CH05, which has no refusals, must be green.
  Redness elsewhere is the correct output, not a C6 failure. #109 is fixed whenever convenient
  and does not gate C6.

**B3 — Order-dependent writes: policy or case-by-case?**

- **Evidence:** CH01's switch 104 (lab door vs Auntie, both writing it, either order legal). L1716
  says the order is C6's to choose.
- **Options:** (a) a deterministic tiebreak rule (e.g. lowest row id, or whichever the route solver's
  cost function prefers) applied everywhere, with every instance listed in the review doc *(leans —
  generic, and the review doc is where you catch a bad one)*; (b) fail loud and require an A0-style
  hint per conflict.
- **Question:** which, and do you want every `OrderDependentKey` surfaced in the review doc even when
  the tiebreak was uncontroversial?
- **Measured 2026-09-18** (`build_chapter_stories`, CH01–CH05): there is **1** instance in the
  whole corpus. CH01's `switch:104` (`Rival-Lab2`) is written by `map049/ev001/p2` and
  `map050/ev001/p1` with values {False, True}. CH02–CH05 have none.
- **Answer (2026-09-18): the solver decides, and every instance is listed.** There is no separate
  tiebreak rule. The solved route's order decides which write lands, and the chapter seed is
  recomputed from it (part #2). The review doc lists every `OrderDependentKey` with the order
  taken and the resulting end-state value, including uncontroversial ones.

### Group C — scope and sequencing

**C1 — All five chapters at once, or prove on CH05 first?**

- **Evidence:** CH05 is the only chapter with an existing route artifact and the only one whose module
  already uses archetype templates and resolvers. CH01–CH04 are hand-written, declare nothing, and all
  their rows currently land in `floor_undeclared`.
- **Lean revised 2026-09-17 by measurement.** CH05 has **zero rowless beats and zero negative beats**
  — the entire coverage-residue risk class is absent from it. It remains the only chapter with a
  known-good route to diff against, so it is a good proving ground for generator *mechanics* and a
  useless one for the residue. Do not read a green CH05 as evidence the coverage scheme works.
- **Options:** (a) build the generator against CH05 first, then widen — but treat CH01 or CH03 (14
  rowless beats) as the real test of coverage *(leans)*; (b) all five from the start, on the theory
  that CH01's scale is what the design must survive.
- **Question:** which, and if (a), is "CH05 regenerates and diffs acceptably" a checkpoint you want to
  review before CH01–CH04 are attempted?
- **Measured 2026-09-18:** CH05 has 43 rows, 0 refusals, 0 seams, 0 order-dependent keys and 0
  rowless beats. CH01 carries every hard case: the corpus's only `OrderDependentKey`, a seam row,
  56 refusals, the direction-arm event (A4, Bambo), the action-triggered device warp (A2) and 458
  rows. So CH01 is a better real test than CH03.
- **Answer (2026-09-18): CH05, then CH01, then CH02–CH04.** Build against CH05 until it regenerates
  and diffs acceptably against its hand module and `CH05.route.json`. Then go straight to CH01,
  then the rest. The CH05 checkpoint is a **build-agent report, not an operator gate**: the
  operator sees its review doc, but work does not stop for it.

**C2 — Does the review doc gate C9?**

- **Evidence:** R7 requires `output/beats/CHnn.review.md` but does not say who reads it or when.
  `ch05.py`'s docstring describes being authored against an *operator-approved* route plan.
- **Question:** is the review doc a build-agent artifact (evidence the generator did something sane)
  or an operator gate (you read and approve it before C9 overwrites a chapter)? If a gate, does it
  belong in CLAUDE.md §9's list?
- **Context added 2026-09-18:** group A's answers turned every former hand-authored choice (seam
  cell, stair starting end, warp press side, event approach side, order-dependent writes) into a
  solver pick. Its only human-visible record is the review doc.
- **Answer (2026-09-18): it is an operator gate, folded into CLAUDE.md §9 gate 2.** *(Corrected
  2026-09-24: there is no overwrite; read "before each chapter's C9 commit". Approval is per
  chapter.)* Before each chapter's C9 overwrite, and for every future generated chapter, the operator reads and approves
  `CHnn.review.md`, then walks the ROM. This is part of the per-chapter boot gate, not a new fourth
  gate, because the generator outlives the rederivation. §9 was amended the same day.

---

## 5. Things the build agent should measure before you answer

Not questions for you — work to be done first, because the answers above change with the numbers.

- ~~Count seam rows~~ and ~~count rows needing warp `mechanism`/`direction` and stair `side`~~.
  **Done 2026-09-18:** 4 seam, 51 warp and 14 stair rows. The per-question notes in §4 group A
  have the breakdown.
- ~~Count rows that would refuse today for C8-blocked reasons, per chapter~~. **Done 2026-09-18:**
  see B2.
- Confirm whether `solve_route`'s `candidates=` parameter already accepts `locations.py` output
  independently of the `Chapter` argument — this determines how much of part #1 is genuinely new.
