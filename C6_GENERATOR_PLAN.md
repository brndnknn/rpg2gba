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

**This document is a breakdown plus open questions. The questions in §4 are not decided.** Where the
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
| **Facing derivation** | **absent** | nothing in `cells.py`/`locations.py` computes it; `warp.py` only checks an expected facing |
| Review-doc writer for generated beats | **absent** | `chapter_manifest/render.py` renders dispositions, not beat code |
| Route artifacts on disk | **CH05 only** | `reference/routes/CH05.route.json` + `CH05.locations.json`; CH01–CH04 have none |
| Declarative beat assertions (`assertions=`) | **parameter exists, unused** | `playtest/chapter.py:398` accepts `frozenset[FloorAssertion]`; **0 of 91 beats across CH01–CH05 pass it** — `Beat.assertions = None` is documented as the expected state for a hand-written beat |
| Hand-beat corpus size | **91 beats**, 22/18/35/13/5 | AST parse 2026-09-17. An earlier `grep -c` said 95; it counted commented-out decorators. **27 of the 91 claim no row at all** — see the residue table in `REDERIVATION_PLAN.md` §16.3 |
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
- **Answer:**

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
- **Answer:**

**A2 — Warp `mechanism` and `direction`.**

- **Evidence:** `warp.py` derives the trigger cell, arrival cell, and expected facing/BGM from staged
  output, but takes `mechanism` (door/threshold/arrow) and `direction`/`return_direction` as explicit
  caller parameters, documented as not derivable.
- **Question:** `mechanism` looks recoverable from the source code-201 command if the manifest carried
  it. Is extending the manifest generator to record the warp destination in scope for C6, or does
  `mechanism` become an A0 hint? And is a default policy (threshold unless the tile is a door tile)
  acceptable, or must every warp be explicit?
- **Answer:**

**A3 — Stair `side`.**

- **Evidence:** documented as an authoring claim. Geometry gives the legal set; it does not say which
  end the beat means.
- **Question:** can the route solver just *pick* — cheapest side by the same DP it already uses for
  approach sides — and let the review doc surface the choice for your approval? Or is the entered end
  semantically load-bearing in a way a cost function would get wrong?
- **Answer:**

**A4 — Facing is entirely underived.**

- **Evidence:** nothing in `cells.py`/`locations.py` computes facing; `warp.py`'s `assert_facing`
  only checks an expected value against staged output.
- **Question:** for a beat that approaches an event from a resolved side, is facing simply "toward the
  event" — i.e. mechanically derivable from approach side, and the gap is that nobody wrote the two
  lines? Or are there beats whose facing differs from their approach direction?
- **Answer:**

**A5 — `_CHAPTER_MAP_START_CELLS`.**

- **Evidence:** a hand-populated `dict[(chapter_id, map_id), frozenset[Cell]]` with citation comments;
  its docstring insists values be "verified (an emulator-observed position, a warp-exit constant), not
  guessed from geometry." It covers chapter *entry* cells only, not beats.
- **Question:** is this a permanent, intentional hand seam — in which case R1's "zero hand overrides"
  should be written down as excluding it, so a later agent doesn't try to "fix" it — or a gap C6 is
  expected to close?
- **Answer:**

### Group B — emit mechanics

**B1 — Where does C6's output land?** — **CLOSED 2026-09-17 by the C7/C6 swap.**

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
- **Answer:**

**B3 — Order-dependent writes: policy or case-by-case?**

- **Evidence:** CH01's switch 104 (lab door vs Auntie, both writing it, either order legal). L1716
  says the order is C6's to choose.
- **Options:** (a) a deterministic tiebreak rule (e.g. lowest row id, or whichever the route solver's
  cost function prefers) applied everywhere, with every instance listed in the review doc *(leans —
  generic, and the review doc is where you catch a bad one)*; (b) fail loud and require an A0-style
  hint per conflict.
- **Question:** which, and do you want every `OrderDependentKey` surfaced in the review doc even when
  the tiebreak was uncontroversial?
- **Answer:**

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
- **Answer:**

**C2 — Does the review doc gate C9?**

- **Evidence:** R7 requires `output/beats/CHnn.review.md` but does not say who reads it or when.
  `ch05.py`'s docstring describes being authored against an *operator-approved* route plan.
- **Question:** is the review doc a build-agent artifact (evidence the generator did something sane)
  or an operator gate (you read and approve it before C9 overwrites a chapter)? If a gate, does it
  belong in CLAUDE.md §9's list?
- **Answer:**

---

## 5. Things the build agent should measure before you answer

Not questions for you — work to be done first, because the answers above change with the numbers.

- Count seam rows across CH01–CH05 (sizes A1).
- Count rows needing warp `mechanism`/`direction` and stair `side` (sizes A0 — 5 hints or 50).
- Count rows that would refuse today for C8-blocked reasons, per chapter (sizes B2).
- Confirm whether `solve_route`'s `candidates=` parameter already accepts `locations.py` output
  independently of the `Chapter` argument — this determines how much of part #1 is genuinely new.
