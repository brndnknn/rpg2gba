# Re-derivation plan — CH01–CH04

**Opened 2026-09-09.** Tracking document for `PROJECT_TODO.md` **#65** (manifests +
dispositions) and **#67** (route plans), executed under **#62**'s ordering safeguard.

> **Status document for this task only.** `MEMORY.md` → Current Phase remains the sole
> authority on the project frontier (`CLAUDE.md` §7). This file owns the step list and its
> state; when the task closes, its durable conclusions go to `MEMORY.md` / `PROJECT_TODO.md`
> and this file is archived.

**Live status (2026-09-10): Phases A, B done; P7 (freeze) done. All four manifests are
re-derived and adjudicated — CH01 `55b98f51`, CH02/CH03 committed after
`investigations/ch02_ch03_rederivation_adjudication.md`, every diff line category 1, no
category-3 finding anywhere.**

**P8 has been split (§13, operator ruling 2026-09-10) and its halves now straddle P9.**
Measurement showed a disposition file is ~70% a join the code can make for itself, blocked
only because no beat before CH05 records the rows it covers. So beat re-authoring (**P8a**,
which populates `rows=`) now comes *before* disposition authoring (**P8b**, now largely
generated). What remains: P8a for four chapters, then P8b, then §10 R2/R3's flip on
CH04+CH05 and the ~109-row hand-decided residue. Blocking questions are ruled in §10, §12
and §13. Branch `rederive-ch01-ch04`.

**2026-09-16: §16 supersedes the hand-disposition pass.** Beats are now generated (P8c, steps
C1–C10); P8a-2 is retired and §15.3's residue becomes the generator's backlog. Read §16 before
any further P8 work.

---

## 1. Why this task exists

CH01–CH05 all passed their §9 boot gates, but CH05's green gate is deliberately weak
evidence for everything except CH05 (`MEMORY.md`, 2026-09-06): it exercises zero seam rows,
zero populated `requires[]`, zero mart/Center/PC instances, and its only `blocked:` rows are
terrain-derived. Slice 2, the capability model, and the non-warp archetype templates have
never been validated against a chapter that uses them. **The retroactive re-derivation of
CH01–CH04 is their validation.**

Two things force it beyond validation:

- **#65 — CH01–CH03's manifests no longer load.** `ManifestRow.reachability_consulted`
  became a required field and `row_from_dict` does strict field-set equality, so
  `chapter_manifest check/render/load` hard-fails on all three. The disposition side broke
  the same way (`deferred:`/`unreachable:<reason>` → `blocked:<set>`); only CH04's was
  hand-migrated.
- **#67 — no chapter before CH05 carries a route plan**, and CH01–CH03 cannot get one until
  #65 clears.

CH01–CH03 were authored before route planning and before the beat archetype templates
existed. **Differences are expected and are the point.** The whole difficulty of this task
is telling three kinds of difference apart:

1. the derivation is better than the hand-authored answer (accept),
2. the hand-authored answer was always wrong (accept, and note it),
3. the derivation code regressed (reject).

#62's safeguard — **freeze the expected answers, derive, diff, then write; never
derive-and-write in one pass** — separates (3) from (1) and (2). It cannot separate (1) from
(2), and it is structurally blind to a rule that is wrong on both sides. #90 is the
precedent: the frozen expectation and the derivation come from the same rule, so they agree
with each other and disagree with the ROM. **Where a frozen literal and a resolver disagree,
the booted ROM breaks the tie — not the frozen file.**

## 2. Scope and decisions (operator, 2026-09-09)

| Question | Decision |
|---|---|
| Do the re-derived chapters get route plans? | **Yes** — #67 is in scope, not deferred. This promotes #74 and #76 from conditional to required. |
| Is CH04 in scope? | **Yes.** All four chapters. (Supersedes #67's "CH04's order is not reopened" and POST_CH05_REVIEW's CH01–CH03 framing — three documents disagreed; this is the ruling.) |
| Adopt `entry_at`? | **Yes.** Zero of five chapter modules use it today, so `_check_beat_continuity` enforces nothing corpus-wide. Re-authoring is the only window. |
| Coordinate literals | **Drive all four to zero and delete `_PRE_BAN_BUDGET`.** See §5. |
| `blocked:` token naming (#93) | **Prefix variable-derived tokens with `var_`**; switch tokens stay bare. §10 R1. |
| Who owns `map035/ev001/p0`? | **CH05.** CH04 dispositions it `boundary`; CH05's B1 claims it in `rows=`. §10 R2. |
| Who owns `map035/ev001/p1`? | **CH05.** It registers an `arrival_nudge_beat`; CH04 dispositions it `boundary`. Two code changes, in P8's scope. §10 R3. |

**Branch policy.** `MEMORY.md` says branches are for chapter builds and in-between work goes
straight to `main`. This task is both, so it splits:

- **Steps P1–P6 (tooling, guards, resolvers, start cells) → `main`.** They are cross-chapter
  infrastructure and touch no chapter module.
- **Steps P7–P10 (the derivation itself, which re-authors four gate-passed chapter modules)
  → a branch**, `rederive-ch01-ch04`, merged after the §9 re-walks pass.

Reversible either way; flagged here rather than assumed.

## 3. Ordered steps

Status values: `TODO` · `IN PROGRESS` · `DONE` · `BLOCKED`.

### Phase A — guards and detectors (make the diff legible before generating it)

| # | Step | Item | Status |
|---|---|---|---|
| **P1** | **Fail loud on a vacuous trigger overlay.** Zero `CROSSING` lines currently reads identically whether the route is clean or the overlay measured nothing. CH05's first solve reported a clean 155-tile route; once object events existed the same order entered trainer sight cones in **five** places. Apply the existing `route_model_unenforced` idiom: dispositions carry trainer rows but the overlay yields no `TRAINER_SIGHT` tiles on those maps → fail loud (§4.5). | #75 | **DONE** `f73d4b52` |
| **P2** | **Build the A5 detector and run it.** Per gated chapter, enumerate every event on its maps carrying a `code 201` to a map that was out-of-slice when that chapter was authored and is in-slice now. `metadata_wiring.classify_event` skips an **entire event** on any out-of-slice `code 201`, so these were invisible at authoring time and are live now. Has already bitten twice (CH03 B25, CH04 B7 — the latter would have teleported the player for five downstream beats). **This detector's output is the real scope of the task and nobody can currently produce it.** No PROJECT_TODO number; file one. | A5 (unfiled) | **DONE** `f4190f2f` |
| **P3** | **Encode boundary ownership.** "A boundary crossing belongs to the chapter being opened, not the one shipping" (operator, 2026-09-04) exists in no code and not in `BUILD_PLAN.md`. `build_beat_model` loads a chapter's own module plus predecessors, **never successors**, so a boundary row claimed by the arriving chapter cannot satisfy the shipping chapter's disposition — CH04 permanently reports `unregistered_beat` for `beat:B8`. All four chapters have a forward boundary and all four answers freeze at once. | #72, #73 | **DONE** `2b6a3b6e` + `14aa6f43` |
| **P4a** | **Fix ROUTE-before-object-events ordering** (`#74`). `BUILD_PLAN.md` §2: BUILD is now step 6, ROUTE step 7. Doc-only; #75 is what keeps it honest. | #74 | **DONE** `2b6a3b6e` |
| **P4b** | **Make `destination_scripts` per-segment** (`#76`). A trainer's own sight cone is still a foreign hazard on the segment walking to it. Required now that route plans are in scope; same root cause as P1. | #76 | **DONE** `18869baf` |

**P2 result (2026-09-09).** `rpg2gba slice-growth` — `src/rpg2gba/slice_growth.py`.
**Six affected events**, and every one is its chapter's forward boundary, exactly the shape
the review predicted:

| Chapter | Events | Target | Cells |
|---|---|---|---|
| CH01 | `Map032` EV023, EV036, EV037 | Map033 (Route 1) | (8,44) (8,45) (8,43) |
| CH02 | `Map033` EV045, EV046 | Map031 (Kevlar) | (15,5) (16,5) |
| CH03 | — clean, **but see below** | — | — |
| CH04 | `Map035` EV001 | Map036 (Passage Cave) | (20,33) |

CH04's is the already-known B7 cave-mouth bug, which is the detector corroborating itself
against a case with a human-verified answer.

**CH03 is not audited by this result.** Its forward boundary (Kevlar → Route 2) is a *map
connection seam*, not a `code 201` warp, so this detector structurally cannot see it. The
seam half needs its own check — filed as **P2b** below. Do not read "CH03: clean" as "CH03
is safe."

**The first thing to look at is CH02's pair.** `ch02.py:278` names (16,5) as
`NORTH_EXIT_TILE_B`, *"for B17's failure message only; never stepped on"*, under a comment
describing the north boundary as blocked terrain. That was true against a 10-map slice with
Kevlar out of it; map 31 has been staged since 2026-08-19. Whether the tile is reachable
today is an audit item, not yet a confirmed bug — but a route plan that steps there warps
the player to Kevlar mid-chapter.

| # | Step | Item | Status |
|---|---|---|---|
| **P2b** | **The seam-crossing counterpart to P2.** `slice_growth` covers `code 201` only. Map-connection seams (`connections.json`, `tileset_converter/connections.py`) went live the same way and are invisible to it — CH03's B25 is the known instance. Enumerate, per gated chapter, every connection edge that became crossable after that chapter was authored. | new (from P2) | **DONE** `3e4265a7` (#91) |

### Phase B — resolvers and data

| # | Step | Item | Status |
|---|---|---|---|
| **P5** | **Three new `cells.py` resolvers**, surfaced by the literal inventory (§5): a grass-cell resolver (4 literals), a seam/connection-edge resolver (2 — these are map connections, not `code 201` warps, so `warp_cell`/`arrival_cell` don't apply), and a local-id-keyed lookup for the ch03 boulders (3 — `event_cell` keys on RMXP event id, not the compiled local id). Without these, 9 literals can only land as counted `raw_cell(..., why=)` debt. | new | **DONE** `502ed4e3` |
| **P6** | **Derive the CH01–CH03 start cells** — `_CHAPTER_MAP_START_CELLS` (`chapter_manifest/generator.py:243`) holds 4 entries (CH04:35, CH05:35/36/37). Needed: **CH01 8 maps** (49, 48, 32, 50, 64, 65, 172, 89), **CH02 2** (33, 81), **CH03 5** (31, 67, 68, 73, 19) = **15**. A missing entry does **not** fail — it warns, and the manifest is capability-blind on that map (`generator.py:266-279`): terrain-gated capabilities cannot appear in `requires[]` for any row. Re-deriving without this yields manifests that load clean, check green, and are blind on all 15 maps — and the freeze would encode the blindness. **This is the bulk of the work and a prerequisite, not a step.** | A1 (inside #65) | **DONE** (P6a/P6b) |

**P6 census result (2026-09-09).** Of the 15 pairs, **9 are usable today without a ROM
run** and **6 need a fresh boot-walk** — all six are CH01's, because CH01's suite never calls
`_assert_near` on arrival, only confirms the map changed.

- **Mechanical (6):** maps 64, 65, 89, 81, 67, 68 — a single inbound `code 201` (or two
  tiles of one wide door agreeing on one cell), so the arrival cell is a fact about the data.
- **Already path-1 in the repo (3):** maps 33, 31, 73 — these fail the strict "exactly one
  inbound" test, but `ch02.py`/`ch03.py` already carry position-verified `_assert_near`
  assertions from green §9 gates. Stronger evidence than the rule requires, sitting unused.
- **Need a boot-walk (6):** CH01's maps 32, 48, 49, 50, 172.
- **Zero disagreements** between a derived cell and an existing hand-authored constant.

**The table's value type changes (operator, 2026-09-09).** Map 73 (Kevlar's building strip)
is one map record holding **four shops in four disconnected components** — verified: 70×15,
5 components, and the four arrival cells sit in four different ones. From a single start cell
at the boutique (44,12), only 2 of its 11 events are reachable; the other 6 would be judged
unreachable when they are reachable through their own doors. **Registering a wrong entry is
worse than registering none** — absent, `has_walkable_approach` returns `None`
("unanswerable", honest); present-but-wrong it returns `False`, a confident wrong answer the
freeze would encode.

So `_CHAPTER_MAP_START_CELLS` becomes `dict[tuple[str, int], frozenset[Cell]]` and
`_build_reachability_context` floods from **all** of a map's start cells, unioning the
results. CH04/CH05's existing entries become one-element sets. Note this is *not* the same
condition as the outdoor maps (32, 33, 31) having many components — those are terrain-gated,
which is exactly what the capability model already handles correctly.

| # | Step | Item | Status |
|---|---|---|---|
| **P6a** | Change the table's value type to `frozenset[Cell]`; union the floods in `_build_reachability_context`; migrate the 4 existing entries. | A1 | **DONE** `70f7677f` |
| **P6b** | Register the start cells. **All 15 landed, not 9** — see below. | A1 | **DONE** `90c5470a` |
| **P6c** | ~~Boot-walk CH01 to observe its 6 arrival cells.~~ **No longer blocks the derivation** — see below. Needed only if a CH01 beat wants `entry_cell()` to name a specific arrival tile. | A1 | DEFERRED |

**P6 outcome (2026-09-09): all 15 registered, no ROM run needed.** The census measured
against the table's "exactly one inbound warp" rule and concluded 6 of 15 needed a boot-walk.
Measured against what the table is *for* — flooding reachability — all 15 are derivable, and
the argument is the point:

- Registered set = every literal `code 201` destination targeting the map from an in-slice
  source, minus self-warps, **minus destinations that are not walkable**. That last filter is
  load-bearing, not hygiene: `Map031` (23,28)/(32,28)/(35,6)/(37,28) and `Map033` (39,18) are
  shop-exit *door tiles* — blocked metatiles the warp lands you on and steps you off. A door
  tile as a start cell floods nothing, reporting every event on the map unreachable.
- That set is a **superset** of "first arrival", which would be unsound if a registered cell
  could sit in a component the chapter can't reach. On **14 of 15 it can't**: all cells share
  one connected component, so the flood is identical whichever is chosen. The proof is
  monotone — adding a capability only merges components, never splits them.
- **Map 73 is the exception and is exact, not superset**: four doors, four components, all
  four entered during CH03.
- **CH01/49 is the one non-derived entry** — CH01 starts there via the fork's own spawn
  override, so `engine/src/new_game.c:174` is the citation.

The soundness argument is now `tests/test_start_cell_registry.py` (38 checks) rather than a
paragraph: every registered cell must be walkable, every entry's cells must share one
component, map 73 pinned as the deliberate four-way exception.

**Why P6c is deferred rather than done.** The boot-walk was only ever needed to name CH01's
*exact* first-arrival tile. For reachability that is unobservable (see above). It still
matters for `entry_cell()`, the beat-authoring resolver, which returns one cell and now fails
loud on a multi-start map — so a CH01 beat that wants a named arrival tile needs either an
observation or the specific cell written into the beat. That is a P9 question, not a
prerequisite.

### Phase C — the derivation (branch `rederive-ch01-ch04`)

| # | Step | Item | Status |
|---|---|---|---|
| **P7** | **Freeze.** Write the expected answers for all four chapters from their committed, gate-passed artifacts *before* generating anything. Per #62, verbatim: *freeze the expected answers, derive, diff, then write — never derive-and-write in one pass, or a regression in the derivation logic reads as a correct re-disposition.* Precedent for the format: `reference/frozen/archetype_expectations.json`. | #62 | **DONE** `aaae306e` |
| **P8** | **Derive, diff, adjudicate the manifests** — CH01–CH04, one chapter at a time, diffed against P7's freeze. Every diff line classified 1/2/3 per §1. Category-3 lines stop the pass. Also carries §10 R3's two code changes and R1's `var_` prefix. | #65 | **DONE** — CH01 `55b98f51`, CH02/CH03 adjudicated + committed, CH04 clean. All category 1. |
| **P8a-1** | **Declare `rows=` (and `archetype=`) on every CH01–CH04 beat.** The half of P8a that P8b actually needs: §13.1's join input. Done by annotating the existing hand-written beats rather than by template adoption — the templates populate `rows=` as a side effect, but the declaration is the deliverable and does not require them. | #67, §13 | **DONE 2026-09-11** — CH04 `962bf578`, CH02 `677ef344`/`d62be7d3`, CH01+CH03 `8fe197d8`. 48 of the 74 own beats carry `rows=`, 73 rows claimed, 22 carry `archetype=`; the other 26 beats claim nothing and each file records why. |
| **P8a-2** | **Re-author those beats onto the archetype templates**, adopting `entry_at`, paying the coordinate literals down to zero (§5). Now a code-quality and assertion-strength step, not a P8b prerequisite. Needs the §13.3 templates; #94 (registry) is DONE 2026-09-10 (`c91f70d3`) and no longer gates it. **Read §5's warning first: some literals are load-bearing ROM-verified truth, and the AST ratchet counts literals without ever asking whether one is still true.** | #67, §13 | **RETIRED 2026-09-16** — subsumed by §16 C5/C9 (regenerated behind a frozen match-or-beat test) |
| **P8c** | **Generated beats** — branch-arm rows, story-state model, engine forks, generic extractor floor with layered archetypes, whole-module generator, Ruby-subset interpreter, CH01–CH05 regenerated behind a freeze, offline flavour checks. Steps C1–C10 in §16.3. | §16 | TODO |
| **P8b** | **Generate the disposition files** — derive `cosmetic`/`blocked`/`unreachable`/`boundary`, join `beat:` off P8a-1's `rows=` (which now exist), hand-decide the **100**-row residue (measured; §13.1's ~109 was close). Affirmation is a separate pass from derivation. Carries §10 R2/R3's flip on CH04+CH05. **Read §14 first — it carries the operator's four rulings and corrects four claims made elsewhere in this plan.** Precedence is `boundary` > `beat` > `blocked` > `cosmetic` (§14.4); clerical rows get `derived_hash`, not `affirmed_hash` (§14.2); and P8b now absorbs **all ten** transpiler work items for the 28 undispositionable rows, item 7 timeboxed (§14.1). | #65 | TODO |
| **P9** | **Route plans** for all four chapters (`routing plan --chapter CHnn --module <mod>`). Still last: `routing locations` hard-fails without P8b's output. | #67 | TODO |
| **P10** | **Discharge the inherited obligations** (§4) and delete the scaffolding that expires with this task. | — | TODO |

### Phase D — gates

| # | Step | Status |
|---|---|---|
| **P11** | **§9 boot gate, ×5** (was ×4 — §14.3's nudge assertion changes CH05's B1 *behaviour*, and the operator's gate rule is that behaviour changes need a walk while declarative `rows=`/docstring edits do not). Each re-derived chapter, **plus CH05**, must boot in mGBA and be genuinely playable before the branch merges. This is an operator gate — I do not pass it on my own say-so (`CLAUDE.md` §9). The seeding recipe is `playtest walk --chapter <this> --at-beat <first> --engine engine`; predecessor `--at-end` blobs are keyed to the ROM's sha256 and any rebuild invalidates them (#85). | TODO |
| **P12** | Fold conclusions into `MEMORY.md` + `PROJECT_TODO.md`, archive this file. | TODO |

## 4. Obligations this task inherits

Not defects, not filed in #71–#86. Things CH05 deferred *to* this work — missing them means
doing the re-derivation twice.

- **Delete `_walk_unplanned_for_replay`** (`playtest/emulator.py:3035`). It restores the old
  greedy walk for inherited beats because CH01–CH04's coordinates "have never faced a strict
  planner." Scoped by the `<owner>:<name>` prefix, recorded as `KIND_REPLAY_FALLBACK`,
  **self-expires** — re-derived chapters run unprefixed and get the strict planner. It fired
  **zero** times in CH05's green run. **Note the timing trap:** it is the airbag for exactly
  the failure mode this task introduces, and it deflates in the same pass. Verified still
  present in the tree 2026-09-09.
- **Fix `ch04.py`'s `_press_a_live` fixed-facing bug** and **replace CH02/CH03's
  hand-transcribed local-id literals with `cells.local_id`** — `a38a1812` left both alone
  explicitly because "they belong to chapters that have not been re-derived yet." A written
  IOU addressed to this task.
- ~~**Give `map035/ev001/p1` an owner**~~ — **RULED, §10 R3** (2026-09-10). CH05 registers an
  `arrival_nudge_beat` for it grouped with B1; CH04 dispositions it `boundary`. Two code
  changes land in P8 to make that expressible.
- **Know that `resolved_trigger_scripts` approximates "resolved" as "the beat passed"**
  (`a460e823`) — holds for latching shapes, not for a TEMP-switch page that re-arms on map
  re-entry. Documented, not fixed. Relevant before trusting the oracle across four chapters.
- **Re-verify `reference/frozen/archetype_expectations.json`** rather than assuming it
  passes: it was written from CH04's dispositions *before* the classifier existed.
- **Fix CH03's B25 description string**, which still says the north edge leads to "unbuilt"
  Route 2. Reconciled 2026-08-26; the prose never caught up.
- ~~**Settle who owns `map035/ev001`**~~ — **RULED, §10 R2 + R3** (2026-09-10): both pages go
  to CH05, `p0` by P3's crossing rule and `p1` by the `arrival_nudge` archetype. The
  contradiction was real (found 2026-09-10 while building `boundary_model.py`): CH04's
  `DEFERRED_BEATS` reason said *CH05's entry beat claims this row*; `ch05.py`'s module
  docstring said the opposite twice (*"owned by CH04's manifest, not this one"*, *"not
  claimable here"*), and `successor_claims` confirmed CH05 claimed neither page in any
  beat's `rows=`. **Both docstrings are now wrong in the same direction and must be
  corrected in P8**, along with CH04's two `DEFERRED_BEATS` entries (§10's closing note).

## 5. The coordinate literals — 123, and what they actually are

`tests/test_chapter_coordinate_literals.py` walks each chapter module's AST and flags **any
`ast.Tuple` of exactly two int constants, anywhere in the file**. The ratchet is `==`, not
`<=`: a count going up fails, and a count dropping below budget *also* fails, demanding the
budget table be lowered to match. **It counts; it never asks whether a literal is still
true.** Nothing links `STAIR1_EAST_APPROACH = (58, 10)` to the map data it claims to
describe, so a re-derived row that moves a cell produces no error — the literal is quietly
wrong. That is the only construct in the pipeline that can fail silently.

Measured 2026-09-09; all four reconcile exactly with `_PRE_BAN_BUDGET`.

| File | Count | Resolver-shaped | No resolver today |
|---|---|---|---|
| `ch01.py` | 13 | 12 | 1 |
| `ch02.py` | 45 | 38 | 7 |
| `ch03.py` | 42 | 34 | 8 |
| `ch04.py` | 23 | 18 | 5 |
| **total** | **123** | **102** | **21** |

- **102 resolver-shaped** — the event/warp id is already documented in-file (usually in an
  adjacent comment), so there is a mechanical path to `event_cell` / `approach_to` /
  `warp_cell` / `arrival_cell`. "Path in principle," not "done": each swap is a diff line to
  adjudicate.
- **6 are false positives** — ch02/ch03/ch04 each carry a direction-vector dict
  (`"DOWN": (0, 1)`). Movement unit vectors, not cells; the AST rule cannot tell them apart.
- **15 genuinely have no resolver** — 4 grass cells, 2 seam/connection edges, 3 local-id
  boulders (all three addressed by **P5**), plus 2 arbitrary scripted-walk waypoints, 3
  diagnostic/never-stepped-on tiles, and `CEREMONY_ROWS = (43, 45)` which is a row *range*,
  not a cell. The last 6 land as `raw_cell(..., why=)` counted debt — the sanctioned escape
  hatch, structurally invisible to the walker, but a non-empty `why=` is its own enforced rule.
- **ch03 carries 3 pure duplicates** (lines 507, 513, 556) — inline literals repeating a
  value already named as a constant in the same file. Free.
- **Some literals are load-bearing truth, not debt.** #90's precedent: `_stair_approach`
  returned unstandable cells for 3 of 7 stair cells on Map033, and the hand-typed literals
  were the only record of the ROM-verified correct approach for CH02's B2/B3. Replacing one
  has to *reproduce* a verified fact, not overwrite it.

## 6. Already cleared — do not redo

D1–D5 (answered 2026-09-08) · **#88** `rpg2gba slice-pins` · **#25** derived
`WARP_OVERRIDES` · **#83** fatal trainer staging · **#86** dead differential tests removed ·
**#79 + #90** stair resolver (`507b1997`, landed specifically because the bug would have
fired the moment CH02 was re-derived and #62's safeguard could not have caught it) ·
**#55** code-408 comment continuation (landed before these manifests are generated, "since
it changes what they say") · **#66** chapter-module renames.

**Not in scope:** #87 (`CommonEvents.pory` harvest) is a **CH06** prerequisite, not this
task's. #44 (CH01/CH03 flavor interiors) is operator-deferred until after CH06's gate. #89
and #37 are independent. #85 is a minutes-long doc fix worth batching in, since P11 walks
four chapters with the recipe it corrects.

## 8. Corrections to this plan, measured 2026-09-10 during P7

Three of §1/§5's claims did not survive contact with the artifacts. They are
corrected here rather than in place because each changes what P8 can conclude.

1. **"CH01–CH03's manifests no longer load … the disposition side broke the same way; only
   CH04's was hand-migrated"** (§1) implies three disposition files that rotted. There are
   none, and `git log --all` shows there never were. §1's framing is wrong in a way that
   matters: **#62's safeguard is structurally unavailable for CH01–CH03's disposition side**,
   because there is no prior answer to diff against. See
   `reference/frozen/rederivation/README.md` for the full statement and for what those
   chapters had instead (an operator-approved beat list, a green suite, a human walk — no
   per-row artifact; `reference/archive/PLAYTEST_AUTHORING_IMPROVEMENT.md` is the post-mortem).
2. **The manifests fail to load on two missing fields, not one** — `reachability_consulted`
   *and* `terrain`. §1 names only the first. Any tool in P8 that reads a pre-`de9343cb`
   manifest must read raw JSON, not go through `row_from_dict`.
3. **No beat in CH01–CH04 claims a manifest row.** All 19 of CH05's own beats carry `rows=`;
   none of the 74 own beats across CH01–CH04 do. The beat↔row join that made CH05's checks
   meaningful does not exist for any chapter being re-derived. Pinned as a test.

Note also that beat counts quoted anywhere as 17/31/61/74/93 are **composed** totals
(a chapter plus all predecessors). Own counts are **17/14/30/13/19**.

## 10. Operator rulings, 2026-09-10

Three decisions taken before P8's CH02/CH03/CH04 passes. Each was blocking: R1 because
CH01–CH03's dispositions are the first work in the corpus to write `blocked:` tokens at
volume, R2/R3 because P8 cannot adjudicate `map035/ev001` while CH04 and CH05 contradict
each other about it in writing (§4).

### R1 — `blocked:` tokens: prefix variables, not switches (`PROJECT_TODO.md` #93)

`capability_sites.token_for_label` gains a `var_` prefix for variable-derived tokens;
switch-derived tokens keep the bare slug. `blocked:got_pokemon` is a switch;
`blocked:var_quest_log_4` is variable 101 at threshold 4. #93's five colliding bases stop
colliding by construction, and the *kind* of gate becomes readable in the disposition
itself, which is worth having on its own.

**Measured before deciding: the migration cost on committed artifacts is zero.** The only
`blocked:` tokens anywhere in the corpus are `blocked:rock_smash` ×28 (CH04) and
`blocked:surf` ×4 (CH05), and per #92 neither is switch- or variable-derived — they resolve
to no `code 121`/`122` site at all. Every token this decision touches is one that has not
been written yet, so #93's "touches all 97 switch tokens" figure was prospective; prefixing
only variables avoids it regardless.

The asymmetry is deliberate. Prefixing both was rejected as noise on the common case (a
plain boolean story gate). An override table for the five was rejected as the
hand-maintained-list-beside-a-derivation shape — the same failure as `render.py`'s silent
verdict drop (§11, P3) and CLAUDE.md §3's rotted file lists; a token's spelling would come
to depend on unrelated data, so adding a Uranium *variable* could silently rename an
existing *switch*'s token.

**Carries one obligation:** a switch label that itself slugs to a leading `var_` would
re-open the collision. `token_for_label` must fail loud on that rather than mint it
(CLAUDE.md §4.5). Nothing in the current label set does, which is why this is a guard and
not a rename.

### R2 — `map035/ev001/p0` is `boundary`, claimed by CH05's B1

CH04 dispositions the Route 2 → Passage Cave entrance warp as `boundary`; CH05's B1 adds
`map035/ev001/p0` to its `rows=`. P3's ownership rule applied literally: the crossing
belongs to the chapter being opened.

**Nothing needs building for this half.** `rows=` is shape-validated only
(`chapter.py:_validate_row_id` matches the row-id grammar and does not check membership in
the chapter's own manifest), and `boundary_model._ensure_successor_loaded` gathers
`beat.rows` from the successor's *module*, not its manifest. CH05's B1 already walks this
exact crossing via the derived reciprocal — it gains a row id, not a test.

The rejected alternative was resurrecting CH04's `b7` and keeping `beat:B7`. It is
self-contained, but it makes CH04's B7 walk into Passage Cave, so CH04's §9 gate would
depend on CH05's map being staged — inverting the chapter dependency order that P3's rule
exists to protect.

### R3 — `map035/ev001/p1` is `boundary` too, and P8 builds the plumbing

CH05 registers an `arrival_nudge_beat` for it, grouped with B1; CH04 dispositions it
`boundary`. Two code changes land in P8 to make that expressible:

1. **`find_match` gains a manifest-chapter override.** It resolves rows via
   `load_chapter_rows(chapter_id)`, so `arrival_nudge_beat(chapter_id="CH05", map_id=35)`
   reads CH05's manifest, which has no map 35, and raises. A chapter must be able to
   register an archetype instance on a *predecessor's* map.
2. **`is_forward_crossing` widens from page-level to event-level.** `p1` is an autorun, not
   a transfer, so the page-level test rejects it and CH04 is left with no verdict meaning
   "the arriving chapter claims this."

**Why not `cosmetic`, which was the first recommendation and is wrong.**
`archetypes._match_arrival_nudge` matches this row exactly — `trigger="autorun"`, heads
`{get_character, setTempSwitchOn}`, effects `{graphic, move_route, temp_switch_write}`, one
script-typed condition, `switch1_id=22` — and returns `prescribed={row_id: "beat"}`. A
`cosmetic` disposition would contradict the classifier on a row it holds an opinion about,
and `reference/frozen/archetype_expectations.json` (§4) is where that contradiction would
surface. This is not a special case: it is 1 of 324 `arrival_nudge` instances across 73
maps, homeless only because its arrival cell sits on the predecessor's map.

Nor is anything already folded in. `warp.py:254` states the contract directly — *"A beat
that wants to ASSERT an arrival autorun (the `arrival_nudge` archetype) claims that page as
its own row and does not go through this template."* `warp_beat`'s `settle_field()` drains
the autorun so the next leg does not trip over a locked field; it asserts nothing. CH05
already runs the correct pairing on its own map (`B8_return` + `B8_nudge`, `group="B8"`).

**This ruling reaches CH01.** All six of
`map032/{ev005,ev006,ev007,ev023,ev036,ev037}/p1` match the same fingerprint (verified
2026-09-10 against the re-derived manifest). Three — `ev023`/`ev036`/`ev037` — are CH01's
forward boundary and become `boundary` alongside their `p0`s under the widening, claimed by
CH02; the other three are the house-door fade partners, which CH01 claims itself with
ordinary `arrival_nudge_beat` calls. That is all 6 of the "forward-boundary rows" plus 3
more off `investigations/ch01_coverage.md`'s 31-row `wants_a_beat` list, with no new
hand-written beat.

### Two things measured while ruling, neither of which was the expected answer

**The `_TSA` flags are not a transpiler bug.** Every `setTempSwitchOn` compiles to
`setflag(FLAG_MAP0nn_EVENTnnn_TSA)` and there is **no `clearflag` for any of them anywhere
in the corpus** — which reads exactly like a per-visit RMXP temp switch
(`reference/scripts_dump/022_Game_Event_v17.rb:78`; `@tempSwitches` is an instance var on
`Game_Event`, recreated on every map load) rendered as a permanent flag. It is not.
`engine/data/scripts/uranium_flags.h` allocates them from `RPG2GBA_TEMPSWITCH_BASE` =
`RPG2GBA_TEMP_FLAGS_START`, and `engine/src/event_data.c:65` zeroes that entire range inside
`ClearTempFieldEventData`, under an `RPG2GBA EVENT RANGE EXPANSION` fence whose own comment
says *"converted-game temp switches share the vanilla temp-flag lifetime (reset on every map
transition)."* Faithful. Recorded here because the absent `clearflag` will look like a bug
again to the next reader, and because this is CLAUDE.md §4.7's reverse gate working: the
fork was checked before the claim was made.

**CH04's `b7`/`b8` deferral expired without anyone noticing.** `b8_autorun_deferred`'s
docstring states its own resurrection condition — *"restore this once CH05 stages map 36 and
event id 1 starts compiling again"* — and both halves have been true since CH05's gate.
`output/uranium-build/scripts/Map035.pory` compiles `Map035_EV001_Page1` **and** `Page2`
today. A deferral whose condition is written down but never re-checked is the same failure
class as `ch02.py`'s stale `NORTH_EXIT_TILE_B` comment (§3, P2) and as CH04's `beat:B7` /
`beat:B8` dispositions pointing at unregistered beats. **Neither beat is resurrected** — R2
and R3 give both rows to CH05 — but the two `DEFERRED_BEATS` entries must go in P8, since
their stated reason is now false.

## 12. Operator ruling, 2026-09-10 — the `blocked:` grammar gains a disjunction

Surfaced by P8's CH02/CH03 adjudication and blocking disposition authoring, so ruled the
same day. Full evidence in `investigations/ch02_ch03_rederivation_adjudication.md` §3.

**The defect.** `BlockedVerdict.as_disposition()` narrowed to `minimal_sets[0]` and
`_reachability_requires` did the same at `generator.py:410`. On 18 CH02 rows — and, it
turned out, on **all 10** of CH02's frozen-oracle beats on Map033 — the real answer is two
independent minimal sets, `rock_smash` *or* `surf`. The second was discarded silently, and
the old grammar could not have expressed it anyway: `|` in `blocked:a|b` meant **AND**, the
members of one minimal set. Authoring CH01–CH03's dispositions before fixing this would
have frozen `blocked:rock_smash` onto rows whose gate is an either/or — §1's stated failure
mode, where the frozen literal and the resolver agree with each other and disagree with the
game.

**The ruling.** `|` now means **OR** (alternative minimal sets, any one suffices); `+` means
**AND** (members within one set); `+` binds tighter. **Migration cost measured before
deciding and it is zero:** every `blocked:` spec committed anywhere in
`reference/manifests/*.dispositions.json` is a single bare token (`blocked:rock_smash` ×28,
`blocked:surf` ×4). Nothing in the corpus used `|`, so no disposition file changes and none
was touched — they are under P7's freeze. Rejected alternative: keep `|` as AND and add a
third separator for OR, which leaves two punctuation marks needing a precedence rule for a
conjunction that has never once occurred in the corpus.

**The checker's fold changes with it**, and this is the substantive half.
`checker.py` looped per token and treated each as an independent claim. Under a disjunction
that is wrong in both directions: `RULE_BLOCKED_ALREADY_GRANTED` must fire when **at least
one** alternative is wholly granted, and `RULE_BLOCKED_NO_GRANT_SITE` only when **every**
alternative is impossible — one impossible alternative beside a viable one is precisely what
a correct `blocked` claims. Note the old fold was already too aggressive under AND semantics
too (one held capability does not open a cell needing two); it never fired because no
multi-token spec has ever existed.

**`requires[]` is deliberately NOT changed.** `ManifestRow.requires` stays a flat
`tuple[str, ...]` reporting one minimal set — widening it is a manifest schema change and a
separate decision. The narrowing there is now logged at warning level instead of being
silent, and the disposition layer carries the full disjunction.

## 11. Log

- **2026-09-09** — Plan opened. Scope set by operator: route plans in, CH04 in, `entry_at`
  adopted, literals to zero. Blocker list assembled from `POST_CH05_REVIEW.md` §3,
  `PROJECT_TODO.md` #65/#62/#67/#72–#76, and `MEMORY.md`; verified against the tree
  (`_CHAPTER_MAP_START_CELLS` = 4 entries; `_walk_unplanned_for_replay` live; `entry_at`
  adoption zero; no A5 detector present in `src/`, `scripts/`, or `tests/`).
- **2026-09-09** — P2 done (`f4190f2f`): `rpg2gba slice-growth`, 6 affected events, all
  forward boundaries. Surfaced **P2b** (the seam counterpart) as new scope, and one audit
  item: `ch02.py`'s `NORTH_EXIT_TILE_B` comment has been stale since 2026-08-19.
- **2026-09-09** — P1 done (`f73d4b52`): `trigger_overlay_vacuous`, verified in both
  directions against CH05's real manifest. Suite 3060 passed / 17 skipped.
- **2026-09-09** — P6 census done; splits 9 mechanical / 6 needing a boot-walk, and forced
  the start-cell table's value type to change (P6a). Cleared a blocker found on the way:
  `MOVEMENT_TYPE_BERRY_TREE_GROWTH` was unclassified and failed the CH03/CH04 route solve
  (`6bece623`).
- **2026-09-09** — P2b done (`3e4265a7`, #91): `rpg2gba seam-growth`. One finding, CH03's
  Kevlar→Route 2 seam — the known B25 case, which is what validates it.
- **2026-09-09** — P6a (`70f7677f`) + P6b (`90c5470a`): start-cell table is a `frozenset`,
  all 15 CH01–CH03 entries registered, soundness pinned by test. P6c deferred.
  Suite 3114 passed / 17 skipped.
- **2026-09-09** — P5 done (`502ed4e3`): `grass_cell`, `cell_for_local_id`, `seam_cells` in
  `playtest/cells.py`. Corrects §5's inventory — the seam resolver covers **one** literal, not
  two: ch03's `NORTH_EDGE_APPROACH` was never a seam cell and ch02's north-exit constants have
  rows in neither `seam_warps.json` nor `connections.json`. Suite 3130 passed / 17 skipped.
- **2026-09-09** — P4a done (`2b6a3b6e`, #74 RESOLVED): BUILD/ROUTE swapped in `BUILD_PLAN.md`
  §2, and #72's boundary convention written down for the first time. Also corrected step 4's
  claim that WIRE stages object events — `phase5` never has, and that misreading is what put
  ROUTE at step 6.
- **2026-09-10** — P4b done (`18869baf`, #76): `destination_scripts` is now per-segment, the
  destination group's own scripts unioned in only on the segment ending there. Its converse
  test needed a `warp_topology` precedence edge to force an order — corridor topology alone
  cannot, because `_CROSSING_PENALTY` makes erasing a crossing worth thousands of tiles to the
  search. **Any order-asserting test in `test_routing_solver.py` that relies on cost asymmetry
  is suspect for the same reason; not yet swept.** Suite 3132 passed / 17 skipped.
- **2026-09-10** — P3 done (`14aa6f43`, #72/#73): argument-free `boundary` verdict,
  `ChapterBinding.successor`, `_check_boundary`'s five outcomes, and `boundary_model.py`
  joining slice_growth + seam_growth with the successor's registered beats. Closes Phase A.
  Found and fixed a silent drop on the way: a `boundary` row never reached `render.py`'s
  review output at all; the hand-written verdict tuples there are now cover-checked against
  `schema._VERDICTS` at import. CH04/CH05 still check 0 errors, counts unchanged — no
  committed disposition uses `boundary` yet, and switching one is P7/P8's call, not this
  step's. Suite 3161 passed / 17 skipped.
- **2026-09-10** — P7 done (`aaae306e`), branch `rederive-ch01-ch04` opened.
  `reference/frozen/rederivation/CH0n.freeze.json` ×4 + `scripts/freeze_rederivation.py`
  (`write`/`check`, idempotent, expires at P10). Sources pinned by **git blob sha**, not by a
  hash of the working file, so the reference survives P8 overwriting the manifests.
  **Three plan claims corrected by measurement while building it — see §8.** Suite 3196
  passed / 17 skipped.
- **2026-09-10** — `714d8832` + `f36e278c`: `src/rpg2gba/capability_sites.py`, the first
  actual `CapabilityModel` implementation — 268 tokens from 518 switch and 731 variable
  writes, with grants keyed to the granting map **event**, not to a chapter
  (`chapters.json` is a plan; 55 of its 60 chapters will be re-cut, so "unblocked by CH57"
  rots silently). Every `blocked:` row in the corpus had been checked against nothing until
  this. Filed **#92** (`rock_smash`/`surf` have no `code 121`/`122` grant site at all —
  Uranium has no HMs, so the real gate is `badge AND (move OR item)`, which `blocked:a|b`'s
  AND-only grammar cannot express) and **#93** (the token collision, ruled in §10 R1). Suite
  3198 → 3230 passed / 17 skipped.
- **2026-09-10** — `4519c12e`: `freeze_rederivation check` no longer asserts that P8 has not
  started. `build_freeze` reads the working tree, so the old "regenerating reproduces the
  committed freeze" assertion went red the moment CH01 was re-derived — which is the freeze
  working as designed. `check` now re-reads the pinned git blobs and verifies the claim a
  freeze actually makes (*these bytes are what `<path>` held at blob `<sha>`*), which stays
  checkable forever; `write` refuses to clobber an existing freeze without `--force`.
- **2026-09-10** — **P8, CH01 half done** (`55b98f51`). Manifest diff vs. the P7 freeze: 211
  rows, none added, none removed, no content-hash changes, and exactly one field on one row
  — `map032/seam/E/map059` unhandled `0 → None`. Category 1: seam rows have no event page
  for `transpile_unhandled` to join against, so `None` ("never measured") is the schema's
  honest value and the frozen `0` read as "measured, none found". **No category-3 finding.**
  Per §8.1 that agreement proves only that the derivation did not drift, so the deliverable
  is the coverage analysis — `investigations/ch01_coverage.md`: of 211 rows, 56 gated
  post-CH01, 40 gated same-visit, 68 inert, 16 covered, **31 wanting a beat**. §10 R3 takes 9
  of those 31 without a hand-written beat; most of the rest are whole maps no beat enters
  (Map048, Map064, Map065, Map089). Map048 — the player's own upstairs — carries a parallel
  process setting `FLAG_GAME_RUNNING` and `FLAG_JUKEBOX`, so **neither has ever been set
  during a CH01 boot-walk**. No dispositions authored: CH01's `CHnn.dispositions.json` still
  does not exist (§8.1), so there was nothing to diff on that side.
- **2026-09-10** — **Three operator rulings, §10**, unblocking P8's CH02/CH03/CH04 passes:
  `var_`-prefixed variable tokens (#93), and both pages of `map035/ev001` to CH05 via
  `boundary` plus two small code changes carried in P8. Two measurements taken while ruling
  are recorded there rather than filed: the `_TSA` flags are faithful (not the transpiler bug
  they look like — `event_data.c:65` clears the range every map transition), and CH04's
  `b7`/`b8` deferral condition expired unnoticed.
- **2026-09-10** — **P8, CH02 + CH03 manifest halves adjudicated**
  (`investigations/ch02_ch03_rederivation_adjudication.md`). **Every diff line is category 1;
  no category-3 finding.** The 7+3 row swap is the #54 stair absorption (`292a94bf`) — exact
  cell-for-cell coverage, each terrain row's `source_event_id` naming the event it replaced,
  and lossless (all 10 removed rows were pure `move_route` with no script, no condition, no
  `unhandled`). **Not** #79/#90/`507b1997`, which touches only the beat-authoring approach
  resolver; the misattribution was made once during this pass and is corrected in the doc.
  The 25 `requires` diffs are `reachability_consulted: False → True` — maps 33/31/19 got
  their `_CHAPTER_MAP_START_CELLS` entries in `90c5470a` (P6b), so the old `[]` was an
  unmeasured default, not a judgment. All 25 are approach gates (mechanism 2), not script
  gates. #92 makes them unenforceable, not wrong. Two findings that are not diff lines: the
  `minimal_sets[0]` discard (ruled in §12) and the fact that `content_hash` covers only the
  raw RMXP page, so it is blind to every one of the 25 field diffs by construction and gives
  the row swap no continuity check at all.
- **2026-09-10** — **§12 ruling implemented.** `blocked:` gains a disjunction: `|` = OR,
  `+` = AND. `as_disposition` emits every minimal set; `schema.parse_blocked_argument` is the
  shared parser and `_validate_blocked_argument` enforces canonical order plus a
  proper-superset rejection (a non-minimal alternative beside the minimal one it is redundant
  with); `checker.py`'s fold is per-alternative, not per-token. `requires[]` unchanged by
  design, its narrowing now logged rather than silent. **One frozen-oracle test re-pinned,
  not the oracle:** `test_ch02_beats_all_gated_on_rock_smash` asserted
  `"blocked:rock_smash"` against all 10 CH02 beats and now asserts `"blocked:rock_smash|surf"`
  — the discard was hiding a second route on every one of them.
  `reference/frozen/slice2_blocked_expectations.json` was **not** touched; its
  `expected_capability` field is still accurate, merely incomplete. Suite 3274 passed / 17
  skipped (was 3261/17). CH04 0 errors / 44 warnings / 42 rows and CH05 0 errors / 5 warnings
  / 25 rows, both unchanged.

## 13. Operator ruling, 2026-09-10 — the disposition file is mostly derivable, and P8/P9 are in the wrong order

Opened when the operator asked why dispositions are hand-authored at all. Five
measurements followed; each is reproducible and cited below. The short version: **a
disposition file is ~70% bookkeeping over a join the code could make for itself, and the
join is missing only because no beat before CH05 records which rows it covers.**

### 13.1 What was measured

**Four of the five verdicts already have a derivation.** `blocked:<spec>` and
`unreachable:geography` come out of `BlockedVerdict.as_disposition()`
(`traversal/reachability.py:253`) in the exact authored spelling — `schema.py`'s grammar
comment says so outright (*"the derivation layer and the authored layer share one grammar,
so a derived value can be affirmed as-is"*). `cosmetic` is gated by the generator-computed
`may_be_cosmetic`. `boundary` falls out of `boundary_model.is_forward_crossing` +
`successor_claims` (P3, `14aa6f43`). Only **`beat:<name>` has no derivation.**

**And `beat:` is underivable for a data reason, not a logic reason.** Measured: **0 of the
74 own beats in CH01–CH04 carry `rows=`; all 19 of CH05's do.** Re-running the join off
`Beat.rows` for CH05 finds **21 row-refs against 21 authored `beat:` rows — exact set
match, 0 missing, 0 extra.** 13 agree outright; the other 8 differ only by beat-family
head (`beat:B8_nudge` derived vs `beat:B8` authored), which is `beat_model.py`'s documented
prefix-family rule, not a judgment. With that normalization a generator reproduces **CH05's
entire 25-row file**.

**A generator that ignores `rows=` does badly, and that is the control.** Value-for-value
against the two committed files: **CH04 24/42, CH05 4/25.** Nearly every disagreement is the
mechanical side saying `cosmetic`/nothing where the human said `beat:Bnn`. This is the
measurement that proves the gap is the missing join and not an algorithmic shortfall.

**Two hazards a naive generator would hit.** (a) **46 rows across CH01–CH04 are both
`may_be_cosmetic` and carry a non-empty `BlockedVerdict`** — precedence is a real decision,
not a default. (b) **`derive_blocked_verdict` is wrong on obstacle rows**: it asks whether a
tile *adjacent* to the event is reachable, so a Rock Smash boulder you can already stand
beside derives `reachable_now=True`. That is why 5 of CH04's committed `blocked:rock_smash`
rows do not reproduce. Filed as **#95**; it makes derived `blocked:` unreliable on exactly
the class #92 already flagged, independent of any generator.

**Residue, reconciled.** Two counts were produced and they measure different things; both
are right. Rows unclaimed by any archetype: **CH01 178 / CH02 29 / CH03 91 / CH04 22 = 320**.
Of those, `may_be_cosmetic` is true for **126/17/54/14 = 211**, leaving **52/12/37/8 ≈ 109**
with no mechanical signal at all. **That ~109 is the disposition file's actual content** —
the rows where someone decides whether a piece of Uranium is worth testing. The other ~211
is clerical.

### 13.2 The ruling — P8 splits, and its halves straddle P9

Deriving `beat:` requires `rows=`; `rows=` is populated by the archetype templates;
adopting the templates is beat re-authoring, which P9 already owns. Nothing about beat
authoring needs a disposition file, while `routing locations` hard-fails without one
(`routing/__main__.py:490`). So the dependency chain admits exactly one order, and the plan
has two of its links backwards:

| New step | Was | Work |
|---|---|---|
| **P8a** | part of P9 | Re-author CH01–CH04's beats onto the archetype templates, adopting `entry_at`. Every template call populates `rows=` and `archetype=`. |
| **P8b** | P8 | Generate the disposition files: derive `cosmetic`/`blocked`/`unreachable`/`boundary`, join `beat:` off `rows=`, leave the ~109-row residue for hand decision. |
| **P9** | P9 | Route plans (unchanged; still last, still needs P8b's output). |

**Affirmation stays separate from derivation.** `affirmed_hash` is the mechanism that means
*a human looked at this row's content* (`RULE_UNAFFIRMED_DISPOSITION`). A generator that
auto-affirms its own output makes that rule vacuous. The generator proposes; affirming is
its own pass.

**Templates stay author-called.** `MEMORY.md` → Key File Notes is explicit that the
`playtest/archetypes/` templates are *not* a generator — the chapter file remains a linear,
approvable document with hand-controlled registration order. Nothing here changes that: P8a
is a human calling more templates, not a script writing `ch01.py`.

### 13.2a What P8a-1 found, 2026-09-11

The ruling above assumed `rows=` arrives as a side effect of template adoption. It does
not have to, and separating them turned out to matter: the declaration is one keyword
argument per beat, while template adoption is a rewrite of gate-passed beats carrying
ROM-verified specifics. P8a-1 shipped the declaration alone and unblocked P8b; P8a-2 keeps
the rewrite.

**26 of the 74 beats claim no row, and that is the answer, not a gap.** Four recurring
shapes, each documented in the chapter file that hit it:

1. **Several beats, one page.** RMXP packs an intro, a choice and both branches into a
   single page, so CH01's B6/N3 and B8/B9 contend for one row. Rule applied: the row goes to
   the beat that asserts the most about it. CH02's N1/N2/N4 and CH03's three are the same.
2. **Proving a dispatcher inert is not exercising a page.** CH01's B14 re-crosses at
   `VAR_QUEST_LOG >= 4`, where the touch dispatcher falls to `end`; `map032/ev009/p3` is live
   at that value but is action-trigger and B14 never presses A.
3. **No row kind represents it.** Boot state, a terminal checkpoint, a wild-encounter table,
   trainer pacing (a movement type belongs to the object event, not a page), and CH03's seven
   warp-arrival-facing / map-BGM beats.
4. **Boundary crossings — five of them, all waiting on P8b.** CH01→CH02 `map032/ev023/p0`,
   CH02→CH03 `map033/ev046/p0`, CH03's `map031/seam/N/map035`, and CH04/CH05's known two.
   None is claimed yet: §10 R2/R3 gives the row to the ARRIVING chapter through
   `boundary_model.successor_claims`, **no chapter in the corpus makes such a claim today**
   (CH05 claims only maps 36/37, so R2 is ruled and unimplemented), and claiming for one pair
   alone would reintroduce the inconsistency §10 removes.

**"Seam" in a beat description means a warp twice out of three times.** CH02's B1 and CH03's
B1 both say "crossing"/"seam" and both cross a `code 201` warp; `connections.json` has neither
a 32↔33 nor a 33↔31 edge. Only CH03's B25 sits on a real connection. Both misreadings were
made and corrected during this pass — check `connections.json` before believing the prose.

**One silently fatal bug surfaced.** `playtest/chapter.py`'s seam row-id regex read
`(NORTH|SOUTH|EAST|WEST)`; real ids are single letters, straight from `connections.json`, so
the pattern matched nothing the generator has ever emitted and no beat could claim a seam row
at all. CH04's B1 was the first to try. Fixed with `tests/test_beat_row_ids.py`, which
validates every row id in every committed manifest against the validator — the comparison
that was missing in both this drift and #94's.

### 13.3 The template-candidate list

Corpus census, **199 maps / 8197 event pages / 630 distinct fingerprints**. The four
existing archetypes cover **2337 pages = 28.5%**.

**The largest single shape is not a template candidate: 3545 pages on 150 maps have no
commands at all** — idle poses, resolved "nothing left to say" pages, ambient decoration.
They want `cosmetic`, which §13.1's derivation already gives them. The population that
actually wants a beat is ~2586, not 8197, and every count below should be read against that
denominator.

Ordered by value. "Blocked on" names a §13.4 transpile item the template cannot be written
before.

| # | Candidate | Pages | Maps | Blocked on |
|---|---|---|---|---|
| T1 | **Predicate loosenings, not new templates** — `arrival_nudge` requiring a `graphic` effect tag; `item_ball` requiring a page-1 "spent" row (single-page item balls exist, e.g. `map068/ev018/p0`); `pbReceiveItem` NPC gifts alongside `pbItemBall` | ~95 | 56 | — |
| T2 | **Flavour-NPC family** — three variants only: plain talk, randomized talk (`random()` + flat if-chain), toggling talk (self-switch two-state). **Eight fingerprint clusters collapse to this one family**; they fragment only on cosmetic tags (`pbCallBub`, `se`, `var_write`) | ~915 | 112+ | — |
| T3 | **Staircase / terrain** — needs a terrain-aware classification path; see §13.5 | ~10s | — | — |
| T4 | **Strength boulder** (`pbPushThisBoulder`) | 70 | 11 | X1 |
| T5 | **Berry tree** (`pbBerryPlant` / `pbPickBerry`) | 96 | 12 | — (already native, see §13.5) |
| T6 | **Surf dismount / vehicle cancel** (`pbCancelVehicles`) | ~5+ | 1+ | X2 |
| T7 | **Rock Smash boulder** — already fully converted to native `EventScript_RockSmash`; unnamed, not unhandled | 11 local | 2 | — |
| T8 | **Region-map NPC** (`pbShowMap` → `FieldShowRegionMap`) | 6 local | 2 | — |
| T9 | **Bridge toggle** (`pbBridgeOn`) | 36 | 3 | verify |
| T10 | **Common-event delegate** — a page whose whole body is one `call(CommonEvent_nnn)` | 53 | 21 | #87 |
| T11 | **Cave exit** (`pbCaveExit`) | 32 | 13 | X3 (partial) |

T1+T2 alone take mechanical coverage of the non-inert corpus from ~28.5% to roughly 60%.

**Blocker on all of it: the classifier is not open for extension.** `classify_event`
(`archetypes.py:198-224`) is a hand-written `if`/`elif` sequence and `ARCHETYPE_NAMES` is a
literal set; a fifth archetype means editing both by hand. Tolerable at five, untenable at
fifteen. **Converting that dispatch to a registry is step zero** — filed as **#94**,
**DONE 2026-09-10** (`c91f70d3`): `_ARCHETYPE_REGISTRY` is the dispatch now and
`ARCHETYPE_NAMES` derives from it. Read #94's closing note before writing an
event-level matcher — event-level precedence is first-claim-wins, so a third
event-level archetype is silently skipped on any event `trainer` already matched.

### 13.4 The transpile-candidate list

Requested by the operator: the mechanics a template needs *transpiled first*. Rock Smash is
the precedent and the proof that this is routine — RMXP's `pbRockSmash` choreography is
discarded wholesale and replaced by native `EventScript_RockSmash`. Each item below is the
same move for a different mechanic.

Source: `output/uranium-build/transpile_unhandled.jsonl`, **340 entries / 69 kinds**.
**Scope caveat: only 18 of 199 maps are staged**, so these counts are the CH01–CH04 slice's
share, not the corpus's.

| # | Item | Entries | Maps | Note |
|---|---|---|---|---|
| X1 | **`pbPushThisBoulder`** → native Strength | 5 | 2 | Blocks T4. Same shape as Rock Smash's native swap. |
| X2 | **`$PokemonGlobal.surfing` conditional** → native Surf state | 5 | 1 | Blocks T6. |
| X3 | **`pbCaveExit`** | 7 | 3 | Partially handled — CH05's B1 crosses one. |
| X4 | **`pbSet`** | 10 | 2 | |
| X5 | **"command follows a Transfer Player warp"** — pokeemerald halts the script at a warp, so everything after `code 201` on the page is dropped | **~150** | 12+ | **The single largest category.** Structural, not a mechanic; spans codes 223/101/509/106/204/355/209/210/241/202/207. |
| X6 | **Commands outside the v1 deterministic tier** — 231/224/232/235/202 (picture/animation) | ~67 | 1–2 | Heavily concentrated on one map. |
| X7 | **`pbTrainerIntro` / `pbTrainerEnd` residue** | 6 | 1 | Trainer archetype covers the shape; these are stragglers. |
| X8 | **Button-input conditionals** (`code 111`) | 3 | 1 | |
| X9 | **`code 122` operand kind 6** (random/item/actor) | 2 | 1 | |
| X10 | **Animation ids with no emote mapping** (`code 207`) | 2 | 1 | |

**X5 is the one to look at first** and it is not a template blocker — it is a correctness
issue in shipped chapters. ~150 dropped commands across 12+ staged maps means page bodies
that silently do less than the source does, inside chapters that have passed their §9 gates.

### 13.5 Three claims corrected while measuring

1. **Berry trees are converted, not missing.** A sub-agent read "no `.pory` output" as
   "unconverted"; `transpiler.py:644` converts **item balls and berry plants to native
   object-template idioms**. No script *is* the correct output, exactly as for Rock Smash.
   The `MOVEMENT_TYPE_BERRY_TREE_GROWTH` fix (`6bece623`) is the corroborating evidence.
   T5 is therefore unblocked.
2. **A staircase is not a warp, and cannot become one.** Two independent reasons.
   `warp_beat`'s whole body proves *the map changed* (`wait_for_map` → `require_map`), and
   `warp.py:223-229` explicitly refuses a same-map crossing; a sideways staircase stays on
   one map and asserts a position delta instead (`ch05.py:576`). Separately the stair event
   is **absorbed into a `terrain` row and its page row dropped** (`generator.py:670-677`),
   and `classify_manifest` only looks at `kind == "page"` — so there is no `ArchetypeMatch`
   to find. This cuts *for* T3, not against it: terrain rows carry `TerrainRef(x, y,
   behavior, source_event_id)`, so a staircase template needs **no fingerprinting at all**.
   It needs a terrain-aware path the classifier does not have.
3. **One fingerprint, two behaviours.** The 84-row `action / () / ()` cluster is ~45
   "content consumed/gone" pages and ~39 "silent ambient decoration" pages, separable only
   by whether `character_name` is blank in the source JSON. Both land `cosmetic`, so nothing
   is blocked — recorded because a fingerprint-only classifier would merge them, and the
   next shape like it may not be harmless.

## 14. Operator rulings, 2026-09-11 — the four P8b questions

Four decisions carried from the operator to the build agent before the disposition pass,
together with what was **measured against the tree while deciding** — several of which
correct earlier sections of this plan. Where this section and §13 disagree, this section
wins: it was measured, §13 estimated.

### 14.0 Measured ground state (not estimates)

| | CH01 | CH02 | CH03 | CH04 | total |
|---|---|---|---|---|---|
| manifest rows | 211 | 83 | 131 | 42 | **467** |
| distinct `content_hash` | 157 | 60 | 108 | 27 | **352** |
| `may_be_cosmetic` | 127 | 31 | 56 | 19 | **233** |
| non-empty `requires` | 3 | 26 | 10 | 25 | **64** |
| claimed by an own beat's `rows=` | 13 | 24 | 26 | 10 | **73** |
| `cosmetic ∩ requires` | 0 | 10 | 1 | 12 | **23** |
| `beat ∩ requires` | 0 | 0 | 0 | 0 | **0** |
| `beat ∩ cosmetic` | 1 | 8 | 3 | 4 | **16** |
| `is_dispositionable == False` | 19 | 0 | 9 | 0 | **28** |
| need a hand `source` citation | 32 | 40 | 29 | 18 | **119** |
| residue — no signal at all | 46 | 14 | 32 | 8 | **100** |

Residue is **100** against §13.1's ~109, and cosmetic-eligible **233** against its ~211 —
close enough to confirm the method. But §13.1's **46** for `cosmetic ∩ blocked` does **not
reproduce**: the real figure is **23**, measured with the real `ManifestRow.may_be_cosmetic`
property (an intermediate draft's 31 was also wrong, from an incomplete `STATE_WRITING_TAGS`
set). Treat 23 as the number and §13.1's 46 as unexplained.

Already discharged, contrary to the step text: **#95 is DONE** (`derive_blocked_verdict_for_event`
gained keyword-only `require_clearing`; `map035/ev014`/`ev017` reproduce CH04's hand-authored
`blocked:rock_smash`, closing §13.1 hazard (b)); **§10 R3's two code changes are in the tree**
(`find_match(..., manifest_chapter_id=...)`, `is_forward_crossing` now event-level) with only
the data-side flip outstanding; **#93 and #94 are DONE**; `write_dispositions` already exists
(`chapter_manifest/dispositions.py:111`).

### 14.1 Q1 — the 28 undispositionable rows: FIX ALL TEN WORK ITEMS

Target is **zero errors**, not a shorter red list. Item 7 is timeboxed (below).

**Root cause, previously unstated: recognition and emission are two unlinked layers.**
`unrecognized_heads` / `other_codes` are judged *only* against two hand-maintained tables
local to the manifest tool — `_CODE_EFFECT` (`chapter_manifest/generator.py:82-107`) and
`MECHANIC_BY_HEAD` (`chapter_atlas/census.py:78-135`) — and **never** against
`conversion_agent/transpiler.py`, the actual spine. `generator.py:600-604` documents the gap.
Consequence: **6 of the 28 rows, and parts of 2 more, are flagged for work already done.**
Wiring these so drift fails loud is part of this fix, not a follow-up.

**Verified clearance ladder.** Per-signature counts do not sum — rows carry multiple
blocking signatures (`map049/ev001/p3` alone carries 104, 221 *and* 222). Distinct-row
clearances, measured:

| # | Work | Clears | Nature |
|---|---|---|---|
| 1 | `_CODE_EFFECT` entries for 104/116/221/222 + `MECHANIC_BY_HEAD` for `pbPokerus`, `pbNextMysteryGiftID` | 6 | bookkeeping only — transpiler already handles all of these |
| 2 | `isRockSmashSoftlocked` static collapse | 3 | 3rd instance of an existing idiom (`_emit_nuzlocke_mode_strip` `transpiler.py:2320-2336`) |
| 3 | `pbSetPokemonCenter` → `setrespawn` + `HEAL_LOCATION_*` minting | 1 | **a real bug — see 14.1a** |
| 4 | X4 `pbGet`/`pbSet` → `getvar`/`setvar` via the registry | 3 | trivial |
| 5 | code 202 → `setobjectxy` + local-id plumbing | 3 | moderate; highest corpus payoff |
| 6 | `isCustomGame` / `showRulesetSettings` strips | 1 | statically dead (Custom Mode unportable) |
| 7 | 118/119 branch-embedded label residue | 3 | **timeboxed — see 14.1b** |
| 8 | `pbPushThisBoulder` → `TF_KIND_PUSHABLE_BOULDER` | 5 | third instance of existing machinery |
| 9 | `jvGiveReward` / `jvNextReward` reward ladder | 2 | composition of native primitives |
| 10 | `pbNextMysteryGiftID` | 1 | collapses into item 1 — already decided |

**Four Q1-relevant claims in this plan are WRONG. Carry these corrections, not the
original text:**

1. **"X1 is verified cheap — the Rock Smash swap exactly" (§13.4) is FALSE.** Rock Smash is
   a *script* substitution: one `goto` at self-contained `EventScript_RockSmash`
   (`engine/data/scripts/field_move_scripts.inc:64-93`), and the event keeps its ordinary
   NPC classification and sprite. A boulder has **no meaningful script** — the push is
   engine C keyed on `gObjectEvents[id].graphicsId == OBJ_EVENT_GFX_PUSHABLE_BOULDER`
   (`engine/src/field_player_avatar.c:1044`, `Task_PushBoulder` `:1813-1878`), and
   `EventScript_StrengthBoulder` carries only the one-time Strength dialogue that every
   vanilla boulder shares verbatim (`engine/data/maps/VictoryRoad_1F_Frlg/map.json:75-117`).
   It is an **object-declaration override**, a different pipeline layer. The cited evidence
   (`EventScript_UseStrength`, `FLAG_SYS_USE_STRENGTH`, `MB_STRENGTH_BUTTON`) is true but
   proves the wrong thing; `reference/chapters/03-kevlar-town.md:247` already ruled
   object-driven, **not** `MB_PUSHABLE_BOULDER`.
   Still bounded: a **third `TF_KIND_*` instance**. `KNOWN_TEMPLATE_KINDS`
   (`metadata_wiring.py:244`) holds `item_ball` and `berry_tree` today; add the boulder kind
   to it, to validation (`:1374-1415`) and to emission (`:2317-2342`), plus one transpiler
   detector in the shape of `detect_item_ball` (`transpiler.py:694-818`). **No `engine/`
   changes.** Note `record_trait("smashable_rock")` is a **flag-only** channel
   (`metadata_wiring.py:1453-1469` sets `ObjectEvent.flag` and nothing else) and was never
   90% of a boulder answer — likely why this sat deferred.
2. **Code 202's "no obvious native analog" is FALSE.** `setobjectxy`
   (`engine/asm/macros/event.inc:702-707`) and `setobjectxyperm` (`:879`) exist, and
   `reference/guides/command_pokeemerald_map.md:88` already tags it **WIRE**, needing only a
   local id — the same plumbing code 116 already does via `ctx.event_id`
   (`transpiler.py:1898`). **199 corpus occurrences**: highest-payoff item on the list.
3. **The freeze objection to absorbing transpiler work is FALSE ON MECHANISM.**
   `generator.py:716` computes `content_hash(page)` over the **raw deserialized RMXP page**,
   not over transpiler output. Fixing the transpiler cannot stale any `affirmed_hash`;
   `RULE_STALE_DISPOSITION` will not fire. Other manifest fields (`unrecognized_heads`,
   `other_codes`, `unhandled`) will diff against the P7 freeze — that is the freeze working
   as designed. Consistent with 14.2's caveat that `content_hash` was blind to all 25
   `reachability_consulted` diffs.
4. **Mystery Gift was already decided and implemented, and is recorded in the wrong place.**
   `transpiler.py:303-306`: *"the Mystery Gift subsystem is not ported (user-approved strip,
   2026-08-19)"*, with `_emit_mystery_gift_id_strip` at `:2338-2358`. `map067/ev009/p1` is
   blocked purely by the `census.py` table gap. Per `strip_list.json`'s own layer-split
   header, the durable record belongs in **`reference/recon/uranium_script_calls.md`**, which
   currently lists only `pbReceiveMysteryGift` (prose *"Feature not wired"*, no STRIP tag)
   and **does not list `pbNextMysteryGiftID` at all**. Also correct two docs that contradict
   the ruling: `reference/chapters/03-kevlar-town.md:263` (*"deferred feature"*) and
   `06-nowtoch-city.md:221` (*"⚠RECHECK/STRIP-leaning"*). **Residual gap to fail loud on:**
   the regex matches only the `pbNextMysteryGiftID>0` comparison form, not a bare assignment
   (`id=pbNextMysteryGiftID`, `03-kevlar-town.md:261`).

#### 14.1a Item 3 is a real bug and must be promoted out of chapter scope

**Pokémon Centers heal but never become the respawn point.** `deterministic.py:91`
classifies `Kernel.pbSetPokemonCenter` as **STRIP**, justified by *"respawn is wired from
metadata, not events"* — **that wiring does not exist.** `pbs_converter/metadata.py:13`
parses Uranium's `HealingSpot` field into `map_metadata.json` and stops there;
`grep -rn HEAL_LOCATION src/` returns **zero hits**; `engine/src/data/heal_locations.json`
is still 100% stock Hoenn/Kanto, so no `HEAL_LOCATION_*` constant exists for any Uranium
Center. Uranium's own `pbSetPokemonCenter` (`reference/scripts_dump/101__PField_Field.rb:1666-1676`)
stamps map/x/y/direction into a single global "last Center wins" slot.

**Full native analog exists** (§4.7 reverse gate, verified): `setrespawn <HEAL_LOCATION_*>`
(`engine/asm/macros/event.inc:1455-1459`) → `ScrCmd_setrespawn` → `SetLastHealLocationWarp`
with `SCREFF_SAVE` (`engine/src/scrcmd.c:2699-2706`). No custom C.

This was found once before at chapter scope — `playtest/chapters/ch03.py:83-88` finding #7,
*"No healing-location/respawn metadata write anywhere… zero hits"* — and **never promoted to
`PROJECT_TODO.md` or the roadmap.** File it corpus-wide this time. Note it is invisible to a
§9 boot walk unless the walk white-outs, which is why a gate-passed chapter ships it.

`pbPokerus` is the opposite and needs no work beyond item 1's table entry: it is a display
getter, and `transpiler.py:567-577` already hard-folds the predicate to the RMXP `else` arm
deliberately, since nothing can be infected this early.

#### 14.1b Item 7 is timeboxed (operator ruling) — **SUPERSEDED 2026-09-12: ITEM 7 IS DROPPED, see §14.8**

> **Do not action this subsection.** Measured 2026-09-12: none of the three rows below is a
> label problem, no queue entry in the corpus carries code 118/119, and item 7 is empty for
> this branch. Kept for the reasoning, not the ruling. §14.8 owns it.

The terminating-region label shape already hoists to `goto` (`transpiler.py:1231-1265`,
`:1880-1888`) and covers 31 of 51 corpus labels. The other 20 sit inside a choice/branch arm
and fall out on dedent — poryscript's flat `goto` cannot express them as-is. **Attempt it; if
it needs a control-flow restructuring that is not already a known pattern, STOP and report —
do not invent one.** The 3 affected rows (`map031/ev014/p0`, `map050/ev004/p2`,
`map050/ev005/p0`) then ship red with a named backlog item for the operator to rule on.

#### 14.1c Item 9's open sub-question

The ladder gates on live `$Trainer.pokedexOwned` against thresholds
10/20/30/50/75/100/125/150/175/194 (`reference/scripts_dump/213_Bambo_Reward.rb`). Variable
22 (`"BAMBO REWARD"`, `reference/uranium_variables.json:23`) is a **claimed-rung index, not a
dex counter** — its only writer in the whole corpus is `jvNextReward:18`. Eight rungs grant
items, three grant eggs, the last egg's species resolving from the starter-choice flags;
one-time each, strictly sequential, nothing repeatable. `jvNextReward` gates and advances;
`jvGiveReward` pays out the current rung.
All primitives exist: `giveegg` (`engine/asm/macros/event.inc:1176`), `giveitem` (`:2122`),
`checkitemspace` (`:580` — the native analog of the Ruby `pbReceiveItem` bag-space check),
and Pokédex-count specials `GetFrlgPokedexCount` / `HasAllMons`
(`engine/data/specials.inc:573-574`). **Open:** those specials are Kanto/FRLG-dex shaped —
establish which matches the port's actual dex mode before costing this tight. This would be
the pipeline's first `giveegg`-emitting classifier.

### 14.2 Q2 — affirmation at four-chapter scale: SPLIT THE MECHANISM

The generator writes the ~233 `may_be_cosmetic` clerical rows with a **distinct,
separately-counted marker** (`derived_hash` *alongside*, not instead of, `affirmed_hash`), so
`affirmed_hash` keeps meaning "a human looked" and `RULE_UNAFFIRMED_DISPOSITION` keeps its
teeth on exactly the rows it was written for. The build agent hand-writes the ~100 residue
decisions and the 101 new citations; **the operator reviews those per chapter before commit.**

- **`derived_hash` must be counted corpus-wide**, the way `archetype_exempt` already is.
  That field's docstring (`schema.py:489-493`) is both the design precedent and the argument
  against letting the generator write `affirmed_hash`: *"not a boolean, because a boolean
  opt-out is exactly the un-greppable rubber stamp this field exists to prevent… A row's
  exemption is counted corpus-wide (`checker.py`), so growth in this field is visible, not
  quiet drift."*
- **Two docstrings must be amended in the same change**, because P8b introduces a second
  writer and both currently deny one exists: `dispositions.py`'s module docstring (*"The
  generator never writes here — that separation is the whole point"*) and, not previously
  noted, **`Disposition`'s own docstring at `schema.py:453-458`** (*"Hand-edited and
  committed. The generator joins it by `row_id` and never writes to it"*).
- **Affirmation surface is ~200, not 425.** 352 distinct `content_hash` of 467 rows, so 115
  rows are exact content duplicates that one judgment legitimately covers — CH04 already does
  this (`map035/ev015/p1`, `ev016/p1`, `ev018/p1` share hash `6c2d90d22489cb2a` and one note).
  Plus 123 fully inert page rows, and the 119 citation-needing rows collapse to **30 distinct
  `script_heads` signatures** whose top four clusters are already-settled idioms
  (`setTempSwitchOn` = `arrival_nudge`; the trainer group; `pbItemBall`; `pbRockSmash`) — so a
  citation there is transcription of a known answer, and one `source` string is correct for a
  whole cluster.
- **Caveat, carried:** `content_hash` covers the raw RMXP page only, so a shared hash means
  "same source page", **not** "same derived situation" — it did not move for any of the 25
  `reachability_consulted` field diffs.

**Residue posture (Q2 sub):** default **`cosmetic`** unless something argues otherwise,
**except** that a residue row with a persistent state write (`switch_write` / `var_write`) on
a map no beat enters is **flagged for a beat**, not dispositioned cosmetic. A flag no test has
ever set is a flag nobody knows works. This splits CH01's Map048/064/065/089 residue cluster
on a principle rather than a coin flip. The live case is `map048/ev005/p0` — a
parallel-process event on the player's own upstairs setting `FLAG_GAME_RUNNING` and
`FLAG_JUKEBOX`, on a map no CH01 beat enters — which under this ruling **gets a beat**.

### 14.3 Q3 — the 13 unclaimed boundary rows: ALL 13, INCLUDING CH05, PLUS THE NUDGE ASSERTION

Add `rows=` claims to CH02, CH03, CH04 **and CH05**; flip the four CH04 boundary rows to
`boundary`; correct both contradictory docstrings; drop CH04's false B8 `DEFERRED_BEATS`
entry. **CH05 is in bounds for P8b** despite being gate-passed and outside the nominal
four-chapter scope.

The three-way contradiction, verified verbatim on disk:

- `ch04.py:1134-1136` — *"Permanently deferred here, not pending: CH05's entry beat claims
  this row"*, dated 2026-09-04 and **false**; CH05 claims nothing on map 35.
- `ch05.py:121-136` — says the reverse twice: `map035/ev001/p0` *"owned by CH04's manifest,
  not this one"*, and `map035/ev001/p1` *"is CH04's row, not claimable here."*
- `CH04.dispositions.json` — still asserts both as `beat:B7` / `beat:B8`.

`chapter.py:109-119` `_validate_row_id` is **shape-only** — three regexes, no
manifest-membership check. **So CH05's refusal rests on a belief that is simply false:** the
validator permits a predecessor's row id. Fix the docstring, not the validator. (Note also
that `B7` is a live registered beat at `ch04.py:877` and is **not** in `DEFERRED_BEATS`; only
B8 has a deferral tuple, so the phrase "CH04's b7/b8 deferral" conflates two things.)

**The wrinkle that chose (A+) over (A): the two rows are not equally claimable.** `ch05.py`'s
B1 already drives `map035/ev001/p0` via the derived reciprocal (*"exercised but not
claimed"*), so claiming p0 is purely declarative. But the same docstring admits B1 is *"still
short of the pre-conversion hand-written beat in one respect"* — the old beat asserted the
arrival nudge's specific one-tile displacement for `map035/ev001/p1`, and `round_trip=True`
*"asserts map+position on each leg but has no nudge-specific step."* Claiming p1 as-is would
be a claim **no assertion backs**. So: **add the nudge-specific displacement assertion to
CH05's B1**, making the p1 claim actually tested.

**Gate rule (Q3 sub), operator:** declarative changes — a `rows=` claim, a docstring
correction — need **no** new §9 walk, because they move no ROM bytes and change no beat
behaviour. A change to beat **behaviour** does need one. The gate follows whether the ROM or
the walk actually changed, not which file was touched.

> **Consequence, stated so it is not a surprise at P11:** the nudge assertion *is* a
> behaviour change to CH05, so under this rule **P11 is ×5, not ×4.** §3's Phase D wording is
> updated accordingly. If the nudge assertion is later dropped back to plain declarative
> claims, P11 returns to ×4.

### 14.4 Q4 — precedence: `boundary` > `beat` > `blocked` > `cosmetic`

Q4 sets only the middle pair; `boundary` outranking both was already settled by §10 R2/R3.

A row a beat actually walks is asserted, so `beat:` is simply the truer statement; a real
capability gate outranks decoration; and `cosmetic` keeps meaning "nothing asserts this and
nothing gates it," which is what makes it safe to derive in bulk.

**The `blocked > cosmetic` half is not a proposal — it describes the standing corpus.** Of
the 23 `cosmetic ∩ requires` rows, 12 are CH04's, and its committed file chose `blocked:` on
**every one**, including `map035/ev015/p1`, which has *empty* `effects` and is therefore pure
decoration by `may_be_cosmetic`'s letter. A human looked and said no: the row is behind a
capability gate, and "decoration" would lose that. CH04 passed a gate on those decisions, so
ordering `blocked` above `beat` (rejected) would have had P8b rewriting gate-passed hand
decisions on the strength of a generator rule.

**`beat` vs `blocked` does not collide anywhere in the corpus — measured, all four chapters,
overlap 0/0/0/0.** Both candidate orderings compute identical output on all 467 rows today.
This rule is therefore written *before* a collision appears, not to rescue rows — and one
will appear: P8a-1 only just added `rows=`, P8a-2 adds more beats, and a beat walking up to a
Rock Smash boulder is the obvious future case. Two caveats: `requires` is the *narrowed*
single minimal set (§12 left it flat by design), so it understates blocking where a row has
alternative sets; and `blocked:` on the 23 rows lands as `capability_model_unenforced`
warnings while #92 is open — honest, but unenforced.

### 14.5 Recorded so it is not re-derived later

- **#92 remains OPEN and P8b cannot close it.** `rock_smash` and `surf` have no grant site in
  the capability model, so every `blocked:rock_smash` / `blocked:surf` row reports
  `capability_model_unenforced` (~26 of CH04's current 38 warnings). P8b multiplies these
  across CH02/CH03. **Expect the warning count to rise sharply; it is not a regression.**
- **`note` is unenforced.** No checker rule reads it; CH04 carries one on 42/42 rows by
  authoring habit, not requirement. Worth knowing before budgeting notes at scale.
- **Live drift to fix in P8b** (§5 of the retired question file): `chapter.py:109-119`'s
  `_validate_row_id` error message still teaches the long-form seam spelling
  `'map035/seam/NORTH/map036'`, while `_SEAM_ROW_RE` accepts both and every real generated id
  is single-letter (`map031/seam/N/map035`). The example validates while matching no row the
  generator has ever emitted — the same drift §13.2a fixed in the pattern, surviving in the
  message that teaches it.
- **P8a-1's five unclaimed boundary crossings** (§13.2a item 4) are the same objects as
  14.3's 13 rows seen from the beat side. 14.3 answers both.
- `map035/seam/N/map040` derives identically under both `require_clearing` questions and is
  not an obstacle case; its non-reproduction under #95 is a disposition-generator concern
  handled by 14.1/14.4, not a derivation defect.

### 14.6 Operator rulings, 2026-09-12 — where `derived_hash` lives, and the condition classifier

Two rulings, both taken after measurement rather than from priors. **The measurement refuted
the build agent's own proposal on the way**, which is why the numbers are recorded here: the
cheap-looking lever was worth ~0 rows and the expensive-looking one was worth ~110.

**Ruling 1 — `derived_hash` goes in a GENERATED SIDECAR, not the dispositions file.**
`reference/manifests/CHnn.derived.json`, written by `generator.py`, mapping `row_id →
derived_hash` and nothing else. The checker loads manifest + dispositions + derived and joins
three ways by `row_id`.

- **`dispositions.py` stays single-writer** and its module docstring stays *true* rather than
  being amended — "The generator never writes here — that separation is the whole point" is
  the invariant, and 14.2's two-writer plan would have retired it in exchange for one fewer
  file. `Disposition`'s docstring at `schema.py:453-458` also stays literally correct. So
  **one docstring amendment, not the two 14.2 predicted** — and the one is a *reference* to
  the sidecar, not a retraction.
- **The checker recomputes eligibility itself** from the manifest and never trusts the
  generator's stamp: a `derived_hash` satisfies `RULE_UNAFFIRMED_DISPOSITION` only on a row
  whose eligibility predicate the checker re-derives and confirms. A `derived_hash` present on
  an ineligible row is a new error, not a pass. Otherwise the stamp is exactly the
  un-greppable rubber stamp `archetype_exempt`'s docstring exists to prevent.
- `derived_hash` is still **counted corpus-wide**, as 14.2 required; the count reads the
  sidecar.
- **The deciding argument is the cross-game pipeline, not this branch.** The end state is a
  new Essentials fan game dropped in with *no* hand-authored dispositions file at all — every
  row derived. A sidecar makes "no hand file" the natural resting state (the checker loads a
  file that isn't there and finds zero hand decisions). Two-writers-in-one-file makes the
  hand-authored file *mandatory*, because it would be where the generated stamps live: a new
  game's first run would have to create a file whose stated purpose is "things a human
  decided." Secondary benefit: the two files' row counts **are** the automation ratio, per
  chapter, readable from the filesystem and in git history, instead of a metric needing a
  script.

**Ruling 2 — P8b stops discarding the condition string and classifies it.** `needs_citation`
narrows to *unclassified* families. This is a manifest-schema change and a checker-rule change,
ruled in under CLAUDE.md §10.

**Measured ground state for ruling 2 (2026-09-12, all five manifests + all 18 CH01–CH05 map
JSONs under `output/uranium-build/maps/`):**

| | |
|---|---|
| Rows, corpus-wide | **492** (CH01 211, CH02 83, CH03 131, CH04 42, CH05 25). CH01–CH04 = 467, matching 14.0 |
| Citation-owing rows | **128** — `script_typed_conditions` only **110**, both **11**, `unrecognized_heads` only **7** |
| Rows a head fix could ever clear | **18** of 128 |
| Script-typed condition instances | **147**, collapsing to **76 distinct texts**, collapsing to **14 idiom families** |
| Judgment-free families | **10 of 14** — one function/attribute name with interchangeable literal arguments |
| Uranium-specific families | **4** (`jvGiveReward`/`jvNextReward`, `isCustomGame?`, `showRulesetSettings`, `isRockSmashSoftlocked?`) ≈ **16 of 147 instances, ~11%** |

- **The string is in hand and thrown away.** `generator.py:575-580` sees code 111 /
  `COND_TYPE_SCRIPT` (12), increments the count, and discards `params[1]`. The generator then
  re-walks the same condition text 40 lines later (`:619-628`) to pull heads out of it. The
  manifest records *that* a page has a Ruby condition and nothing about what it says — which
  is the whole reason 110 rows owe a human a citation. The data needed to classify them was
  discarded at parse time, not absent from the source.
- **Recognition already exists; it is not applied to condition text.** `get_character`,
  `pbItemBall`, `pbTrainerBattle`, `pbRockSmash`, `pbPickBerry`, `pbHasSpecies` and
  `pbPhoneBattleCount` are all in the transpiler's recognized set today. This is **the
  corpus's largest single instance of #97** (recognition and emission as unlinked layers) and
  #97 should be read as pointing here.
- **Text-level uniqueness is not shape-level uniqueness.** 55 of 76 distinct texts occur
  exactly once (72% of texts, 37% of instances) but nearly all are the same four call patterns
  with different literals — 22 distinct `pbTrainerBattle(...)`, plus `Kernel.pbItemBall`,
  `Kernel.pbReceiveItem`, `$game_player.y` variants. Do not cost this off the singleton count.
- **Two genuine outliers need judgment and get a fallback bucket, not a pattern:**
  `!pbGet(1).is_a?(Numeric) || $game_variables[1] < 0` and one sibling are compound booleans,
  not bare comparisons.
- **REFUTED, recorded so it is not re-proposed:** deriving the `source` citation by joining
  `script_heads` against `reference/recon/uranium_script_calls.md` clears ~**0** additional
  rows. Only 18 of 128 rows involve an unrecognized head, and the 11 heads behind them
  (`pbPushThisBoulder`, `isRockSmashSoftlocked`, `pbGet`, `pbSet`, `isCustomGame`,
  `showRulesetSettings`, `jvGiveReward`, `jvNextReward`, `pbNextMysteryGiftID`, `pbPokerus`,
  `pbSetPokemonCenter`) are **exactly 14.1's ten work items**. The head half of the citation
  surface was already in scope; the hypothesis that a recon join would shrink it was wrong.
- **Carried caveat — this is an instance-and-shape measurement, not a per-row one.** The
  residual after classification is **estimated** at 15–25 rows of the 110, not measured; a
  per-row family join was offered before the ruling and the operator declined it as
  unnecessary. If the residual lands materially above 25, that is new information, not a
  regression.
- **CH04 and CH05 are already paid for.** All 27 of their citation-owing rows carry a
  non-empty `source` today (18 + 9, zero missing), so the classifier's win is CH01–CH03's
  101 rows. Existing hand citations become redundant but stay valid.
- **Incidental defect found while inventorying, fix in passing:**
  `chapter_atlas/census.py` `MECHANIC_BY_HEAD` declares `"pbRockSmash"` twice (`:90` and
  `:109`), the second silently shadowing the first. Same value, so no behaviour change today.
- **Cross-game reusability is the point.** ~89% of condition instances are vanilla Essentials
  shapes (`get_character`, `$game_player`, `$PokemonGlobal`, `Kernel.pbItemBall`,
  `pbPhoneBattleCount`), so the classifier transfers to the next fan game unchanged. Per-row
  hand citation transfers to nothing.

### 14.7 Operator ruling, 2026-09-12 — item 3 builds the emitter, and the white-out beat becomes a standing precedent

**Ruling: option 1 — build the generic heal-location emitter AND teach the harness to white
out.** Plus a standing rule for where the verification beat goes, stated below.

**The derivation was already parsed and thrown on the floor.** `metadata.dat` carries per-map
`HealingSpot = [map, x, y]`; `pbs_converter/metadata.py:106` parses it into
`MapMetadata.fields["healing_spot"]`; **nothing in `src/` or `scripts/` ever reads it**. There
is no `heal_location` emitter in the repo. #96's "the wiring does not exist" is exactly right.

**Measured (2026-09-12): 22 maps carry a healing spot corpus-wide**, and they are Center
interiors pointing at outdoor coordinates — maps **49 and 50 → `[32, 28, 32]`** (Moki Town),
map **68 → `[31, 20, 13]`** (Kevlar Town). That is a **1:1 fit** for pokeemerald's
`engine/src/data/heal_locations.json` entry shape (`id`, `map`, `x`, `y`; `respawn_map` /
`respawn_npc` / `respawn_x` / `respawn_y` are the newer in-Center respawn polish and are
**optional**). So: mint `HEAL_LOCATION_*` from metadata, emit `setrespawn(...)` at the
`pbSetPokemonCenter` call site. **66 call sites collapse onto 22 locations; this branch touches
two.** No engine C, no fidelity loss.

**A live recon ruling was carrying a retired premise.**
`reference/recon/uranium_script_calls.md:71` ruled `pbSetPokemonCenter` redundant because it is
"captured deterministically by §2.8 `metadata.py` as `HealingSpot` and **wired in Phase 5**"
(false — nothing consumes it), and rejected `setrespawn` because the constant is one "the agent
can't derive from the event JSON." True of an **LLM reading one event's JSON**; false of the
transpiler, which joins the event's map id against metadata. The conclusion outlived the spine
it was reasoned about. Corrected in place, dated.

**LATENT BUG, found while grounding this ruling — a white-out today lands in vanilla Petalburg
City.** The new-game spawn override (`engine/src/new_game.c:172-208`, `URANIUM PATHFINDER
SLICE`) calls `SetWarpDestination(MAP_MOKI_TOWN_PLAYERS_HOUSE_1F, …)` and **never sets a heal
location**. Our boot path skips the intro/title/Birch speech, so no script ever runs
`setrespawn` either. `ClearSav1` zeroes `gSaveBlock1Ptr->lastHealLocation`, and
`SetWarpDestinationToLastHealLocation` (`overworld.c:758-763`) reads that zero as mapGroup 0 /
mapNum 0 = **`MAP_PETALBURG_CITY`** (`engine/include/constants/map_groups.h:15`). Every
gate-passed chapter ships this. **The initial anchor must be set in the same fenced
`new_game.c` block as the spawn override**, per the operator's ruling that the game's opening
respawn is Moki Town.

**STANDING PRECEDENT (operator, 2026-09-12) — a white-out beat goes in the chapter AFTER the
chapter that establishes or changes a respawn anchor.** Rationale: a respawn anchor set in
chapter N is only *provable* once the player is somewhere else, and the chapter that sets it is
standing on it. Applied to the current corpus:

| Anchor event | Set in | White-out beat goes in |
|---|---|---|
| Initial anchor = Moki Town (`new_game.c`, game open) | CH01 | **CH02** |
| Kevlar Town Center visited → anchor moves | CH03 | **CH04** |

This is a rule for the atlas, not a one-off: every future chapter containing a Center owes its
successor a white-out beat asserting the new anchor. It also makes CH02's beat a **regression
test for the Petalburg bug above** — it fails today and must, until the `new_game.c` fix lands.

Scope note: the ruling is the emitter plus harness capability plus these two beats, not a
white-out in all five chapters — the beat proves the anchor, and one anchor needs one proof.

### 14.8 Operator ruling, 2026-09-12 — item 7 is dropped, and the queue↔manifest page offset is fixed in P8b

**Ruling: drop item 7 from §14.1's ten. P8b's work-item count is nine.** Measured, not
argued — §14.1b's premise does not survive contact with the three rows it names.

| Row §14.1b blames on labels | What actually blocks it | Cleared by |
|---|---|---|
| `map031/ev014/p0` | **nothing** — `unrecognized_heads=[]`, `script_typed_conditions=0`, `unhandled=0` | already clean |
| `map050/ev004/p2` | `isCustomGame`, `showRulesetSettings` | **item 6** |
| `map050/ev005/p0` | `pbGet` | **item 4** |

`hoistable_label_region` already returns a region for all three pages: `(2,23)` for
`map031/ev014/p0` (runs to end of page; its `joke` label has **zero** jumps to it), `(40,53)`
for `map050/ev004/p2` (terminating, code-115 Exit at 39), `(50,129)` for `map050/ev005/p0`
(same-indent code-115 at 128 — the very "Map050 EV005's aptitude-test body" the module note at
`transpiler.py:1244` already lists as a qualifying shape). The hoist is wired end to end
(`:4021-4029`); the queueing `else` at `:1885-1892` is simply not reached by these pages.
**Corpus-wide: 0 of the 340 entries in `output/uranium-build/transpile_unhandled.jsonl` carry
code 118 or 119**, and maps 31 and 50 are both staged (14 and 18 entries), so that is a real
absence rather than an unstaged map.

Consequence: **P8b no longer contains a timeboxed item or a red-ship path.** Nothing in scope
needs a control-flow restructuring, so nothing can tempt an agent into inventing one. This is
the **fifth** corrected claim in §14.1.

The 20 non-hoistable labels from the 2026-08-01 census are real and unrefuted; **none lands on
a CH01–CH05 page.** Item 7 is empty *for this branch*, not wrong forever — it returns at
whichever future chapter first stages one. **A regression test is added in P8b** asserting no
code 118/119 ever reaches the transpile queue for the staged corpus, so that day fails loud
instead of shipping a broken `goto`.

**Ruling 2 — the queue↔manifest page offset is a P8b fix, not a backlog entry
(`PROJECT_TODO.md` #98).** `transpile_unhandled.jsonl`'s `page` field is **1-based**; manifest
`row_id` page suffixes are **0-based**. `map050/ev004` queue page 3 is manifest `p2`;
`map050/ev005` queue pages 6 and 7 are `p5` and `p6`. Any queue↔manifest join that does not
correct for this attributes an entry to the wrong page, and **manifest `p0` can never match
anything** — which is precisely how three rows acquired a label bug they do not have.

- **Normalize the queue writer to 0-based.** The manifest's `row_id`s are load-bearing inside
  committed `.dispositions.json` files and must not move; the queue is regenerated output and
  can.
- P8b is the step that joins these two artifacts most heavily, so the offset is fixed *before*
  the disposition pass reads them, not after.
- Filed under the standing lesson this is the third instance of: **a measurement taken through
  a generator attributes its own bugs to whatever it was measuring.**

### 14.9 Operator ruling, 2026-09-12 — #92's vocabulary: collapse the token, structure the model

**Ruling: the `blocked:` token stays collapsed. The conjunction moves into the capability
model.** This answers the decision `PROJECT_TODO.md` #92 reserved for the operator.

Uranium has no HMs: the real gate on a Rock Smash boulder is **`badge AND (move OR item)`**,
and `blocked:a|b` means AND-of-a-set with no OR, so the verdict string cannot express it.
*(Corrected 2026-09-13: that grammar claim is false. `schema.parse_blocked_argument` reads `|`
as OR and `+` as AND, and `checker.py`'s blocked rules already evaluate that OR-of-ANDs form.
The ruling below stands on its other grounds — churn, and that no beat can observe which
conjunct refused.)*

**Rejected — compound grammar in the verdict** (`blocked:badge1&(rock_smash_move|boxinggloves)`):
it churns every committed `blocked:rock_smash` in CH04/CH05, hands the checker a parser to
maintain, and encodes a distinction **no beat can assert** — a negative beat walks up, presses
A and observes a refusal; it never learns which conjunct failed.

**Adopted — `rock_smash` remains one token** meaning "can rock smash in the field," with the
structure held as **requirement groups** on the derivation: one group per conjunct, alternatives
within a group. `rock_smash` requires `{badge_1}` and `{move_unlock, boxinggloves}`. The grant
point in route order is **`max` over groups of `min` over alternatives**. Same shape for
strength/`POWERGLOVE`, surf/`SURFBOARD`, dive/`SCUBAGEAR`, waterfall/`CLIMBINGPICK`.

- **Zero churn, and the committed files were already right.** Every existing
  `blocked:rock_smash` / `blocked:surf` disposition is correct under this reading, so nothing
  authored to date is invalidated.
- **`CapabilitySite` needs one addition.** Today it is a flat
  `(token, row_id, map_id, chapter_id, detail)` (`capability_sites.py:238-248`), which can only
  express a *union* of sites — OR-semantics — so it cannot currently say "the badge is also
  required." Requirement groups are a small structured field on `CapabilityDerivation`, not a
  new verdict vocabulary and not a schema change to dispositions.
- **Derived where possible, hand-annotated where not** — the same split ruled in §14.6 for
  dispositions. #64's `old_rod` case is why the annotation path is mandatory rather than
  optional: it sits behind `var[103] >= 5`, variable 103 is named "Battle Var01", and the only
  artifact stating what it means is dialogue text — a name-keyed classifier misses it
  *confidently*.
- **Consequence for the warning count.** #92 becomes closable inside or just after P8b, and the
  `capability_model_unenforced` warnings go green *honestly* rather than multiplying across
  CH02/CH03 as §14.5 predicted. §14.5's "expect the count to rise sharply" now holds only for
  the window between P8b's disposition pass and the requirement-groups landing.
- **Unchanged:** #92's standing prohibition. Do not make a row green by inventing a grant site.
  A token with no derivable and no annotated grant stays *unenforced*, which is an honest "not
  checked".

### 14.10 Operator ruling, 2026-09-12 — notes are for judgment rows, and a durable ruling never lives in one

**Ruling 1: generator-derived clerical rows get no authored `note`.** The `derived_hash` plus
the row's own manifest facts already state why the row is cosmetic; a note there restates the
machine's conclusion in prose. Notes stay on the **hand** rows — residue, boundary, blocked —
where the note *is* the argument and nothing else records it. ~233 rows of authoring cost
bought back.

**Ruling 2: a corpus-wide convention may not live in a disposition note. The warp round-trip
idiom is promoted to `BUILD_PLAN.md` §2**, beside the boundary-crossing convention it pairs
with; the two CH05 notes that carried it now cite it instead.

Measured before ruling, because §14.5's framing was slightly off:

- **`note` is not unread.** `render.py:141-142` prints it into the human-readable review
  artifact — so it is *unenforced* (no checker rule) but it is the text the operator reads at
  review time. That is a different thing from dead.
- **The two chapters use notes for two different jobs.** CH04: 42/42 rows, median 84 chars,
  and repeated verbatim boilerplate (`"Spent page."` ×3, `"Cleared state of a
  not-yet-approachable rock."` ×3). CH05: 25/25 rows, median **240** chars, max **1618**, and
  substantive — coordinates, doc-beat cross-references, and operator rulings recorded nowhere
  else. The split falls exactly on clerical-vs-judgment, which is the §14.6 split again.
- **Why ruling 2 matters beyond tidiness:** the warp round-trip idiom is a rule for every warp
  in the corpus and it was sitting in one row's free text — un-greppable, and it dies the day
  that row is re-dispositioned. Same pattern that left the Poké Center respawn bug inside
  `playtest/chapters/ch03.py` for a month (#96).

**Still in CH05's notes, flagged not moved** (out of this ruling's scope, operator to confirm):
the **one-beat-id-per-EVENT** rule (operator, 2026-09-04), which appears in three separate
notes and is corpus-wide by the same argument. The sideways-staircase "one observable per
staircase" reasoning went to `BUILD_PLAN.md` §2 as a corollary of the warp idiom, since it is
the same "one physical thing owns both its rows" shape.

### 14.11 Operator ruling, 2026-09-12 — item 9 is dropped; its two rows are `unreachable`, not undispositionable

**Ruling: drop item 9's emission from P8b. Eight work items, not nine.** The reward ladder
lands in the chapter that can prove it, on the same principle as §14.7's white-out precedent.

**§14.1c asked the wrong gate.** Item 9's two rows (`map050/ev005/p5`, `p6`) are **not** gated
on a dex count. Both pages carry the RMXP condition **`variable 101 >= 5`**, and variable 101
is **"Quest Log"** (`reference/uranium_variables.json`). The dex thresholds live *inside* the
page script (`jvNextReward`), so they govern rung selection, not page reachability.

**Census of every `code 122` write to Quest Log across all 199 deserialized maps — four
writers, and only two of them can cross 5:**

| Site | Op | Value | Chapter |
|---|---|---|---|
| `Map032 ev9/p2` | set | **4** | CH01 |
| `Map172 ev4/p0` | set | 2 | CH01 |
| `Map042 ev3/p0` | **+1** | — | **CH06** |
| `Map050 ev19/p0` | **+1** | — | — |

The highest *constant* write is 4. Quest Log crosses 5 only via the increments, the first of
which is the **CH06 gym**. **Those two pages are provably unreachable in CH01–CH05** — which is
where the operator placed them from play knowledge ("no beats until we return to Moki Town post
Act 1") before the census confirmed it.

- **Verdict: `unreachable:var_quest_log_5`** *(token corrected 2026-09-13 — #93's `var_` prefix;
  the checker never resolves `unreachable:` tokens against the capability model, so the
  annotation described below is not needed)*. `unreachable` is already in the vocabulary
  (`schema.py:90`), and `capability_sites._resolve_threshold` handles
  `<variable>_<threshold>` tokens natively; `quest_log_4` is already a derived token (#92).
  **`unreachable` is a verdict, not an error, so §14.1's zero-errors ruling stays intact.**
- **These two rows are the first real user of §14.9's hand-annotation path.**
  `_resolve_threshold` returns `None` (undetermined) here, not a clean grant, because the writes
  that cross 5 are *increments* and its docstring refuses to guess when constant writes fall
  short but computed writes exist. That refusal is correct; the rows get a hand-annotated
  requirement group citing the census above.
- **Corrected in passing (build agent, same session):** the earlier claim that "rungs 1–3 are
  walkable, so walking them exercises the shape" was answering the dex gate while the page gate
  is Quest Log. No rung is observable in this branch — not three, not zero-of-three. The dex
  findings below stand for the ladder's internals whenever it is built.
- **Item 9's mechanism findings are kept, because they close §14.1c permanently.** The port runs
  National mode with Uranium species grafted past `NATIONAL_DEX_PECHARUNT`, and
  `engine/include/constants/uranium_pokedex_ids.h:38-39` `#undef`s and re-pins
  `NATIONAL_DEX_COUNT` to `NATIONAL_DEX_BAARIETTE`, so `GetNationalPokedexCount`'s
  `i < NATIONAL_DEX_COUNT` loop (`pokedex.c:4547`) covers the grafted range — without that
  override it would return 0 caught forever, silently. Vanilla species are uncatchable in the
  port, so caught-count *is* Uranium-caught, identically before and after #31: **item 9 has no
  dependency on #31 and §14.1c is closed.** Mechanism when built:
  `setvar VAR_0x8004, 1` → `special GetFrlgPokedexCount` → compare `0x8006`. `HasAllMons` is a
  complete-dex boolean and is the wrong tool. `giveegg` is native (`event.inc:1176`), so the egg
  rungs are not new machinery either. Coverage caveat for whoever builds it: only **33 species
  are staged** today, so 7 of the 10 rungs (10/20/30/50/75/100/125/150/175/194) are unreachable
  even once the page opens.

---

## 15. P8b — final scope (settled 2026-09-12)

**Read this section before starting P8b. It supersedes §14.1's ten-item list.** §14.1–§14.5 are
the 2026-09-11 rulings; §14.6–§14.11 are the 2026-09-12 rulings that reshaped them; this
section is the union, stated once. Where §14.1 and this section disagree, **this section wins**.

### 15.1 The eight work items

Item 7 is dropped (§14.8 — not a label problem; its rows belong to items 4 and 6). Item 9 is
dropped (§14.11 — its rows are `unreachable`, not work). Item 10 folds into item 1.

| # | Work | Clears | Nature |
|---|---|---|---|
| 1 | `_CODE_EFFECT` (104/116/221/222) + `MECHANIC_BY_HEAD` (`pbPokerus`, `pbNextMysteryGiftID`) entries | 6 | bookkeeping; transpiler already handles these (#97) |
| 2 | Collapse `isRockSmashSoftlocked` statically | 3 | third instance of `_emit_nuzlocke_mode_strip` |
| 3 | Heal-location emitter + `setrespawn` (§14.7) | 1 | **grew** — see 15.2 |
| 4 | X4 `pbGet`/`pbSet` → `getvar`/`setvar` via the registry | 3 | trivial |
| 5 | Code 202 → `setobjectxy` + local-id plumbing | 3 | moderate; **highest corpus payoff (199 occurrences)** |
| 6 | Strip `isCustomGame` / `showRulesetSettings` | 1 | statically dead |
| 8 | `pbPushThisBoulder` → `TF_KIND_PUSHABLE_BOULDER` | 5 | third `TF_KIND_*` instance; no `engine/` changes |

Counts are distinct-row clearances and **do not sum** — rows carry multiple blocking
signatures. Also fix in passing: the duplicate `"pbRockSmash"` key in `MECHANIC_BY_HEAD`
(`census.py:90` and `:109`, second shadows first, same value).

### 15.2 The five structural changes ruled in on 2026-09-12

1. **`derived_hash` sidecar** (§14.6). Generator writes `reference/manifests/CHnn.derived.json`
   — `row_id → derived_hash`, nothing else. `dispositions.py` stays single-writer and its
   invariant docstring stays *true*. The checker loads manifest + dispositions + derived, joins
   three ways, and **recomputes eligibility itself**: a `derived_hash` on an ineligible row is a
   new error, not a pass. Counted corpus-wide like `archetype_exempt`. Rationale is the
   cross-game pipeline — a new Essentials game has no hand-authored dispositions file at all,
   and the two files' row counts *are* the automation ratio.
2. **Condition classifier** (§14.6). Stop discarding `params[1]` at `generator.py:575-580`;
   classify the condition text into idiom families; narrow `needs_citation` to *unclassified*
   families only. 147 instances → 76 texts → **14 families, 10 judgment-free**; ~89% are vanilla
   Essentials shapes, so this transfers to the next fan game. Two compound-boolean outliers get
   a fallback bucket, not a pattern. Manifest-schema + checker-rule change, ruled in under
   CLAUDE.md §10. Residual estimated 15–25 rows of the 110 — **estimated, not measured.**
3. **Heal-location emitter + white-out beats** (§14.7, **corrected 2026-09-12 — see §15.6**).
   Emit `heal_locations.json` entries and `setrespawn` at the `pbSetPokemonCenter` call sites.
   Set the **initial** anchor in the fenced `new_game.c` block — today a white-out lands in
   vanilla Petalburg City. New harness capability: force a party wipe and assert the
   post-white-out map/coords. **Two beats:** CH02 asserts the initial anchor, CH04 asserts the
   Kevlar anchor. CH02's is expected to **fail** until the `new_game.c` fix lands.
   **Do not derive these from the `healing_spot` metadata** — that is a different system
   entirely (§15.6).
4. **Capability requirement groups** (§14.9) — **SCOPED DOWN 2026-09-13 (operator): badge
   count only; everything else deferred to CH06**, where Gym 1 (Map042) first puts a badge in
   the chain and the data can inform the design. What P8b builds: a scan of
   `$Trainer.badges[N]=true` script writes (8 badges, 9 sites, no revocations) plus a cited
   `BADGEFOR*` threshold table (`Settings.rb:144-151`; Uranium counts badges,
   `HIDDENMOVESCOUNTBADGES=true`). The badge is **necessary, not sufficient**: threshold unmet
   in the chapter chain = confirmed blocked; threshold met = *undetermined*, never granted,
   because the (move OR item) conjunct is unmodelled. In CH01–CH05 no badge is held, so this
   alone settles every `blocked:rock_smash`/`blocked:surf` row. **Deferred to CH06:**
   requirement groups proper, the move alternative (`pbCheckMove` is live party state, and
   Gym 1's TM27 is Return, so the source is unidentified — #92 point 1), the Map167 gadget
   items, route-order vs chapter-chain granularity, and the hand-annotation file.
   `map050/ev005/p5`/`p6` need no annotation: `unreachable:` verdicts are never checked
   against the capability model. Zero churn to committed dispositions.
5. **Queue↔manifest page offset** (§14.8, #98). Normalize the **queue writer** to 0-based
   before the disposition pass reads either artifact. Manifest `row_id`s must not move — they
   are load-bearing inside committed dispositions files.

### 15.3 Disposition posture

- **Precedence:** `boundary` > `beat` > `blocked` > `cosmetic` (§14.4). Beat and blocked have
  zero measured overlap; CH04's committed dispositions already chose `blocked` over `cosmetic`
  on 12 gated rows.
- **Boundary rows:** all 13 claimed, **CH05 included** (§14.3). CH04's four flip to `boundary`.
  Three contradictory docstrings corrected (`ch04.py`, `ch05.py`, `CH04.dispositions.json`).
  CH05's B1 gains a nudge-displacement assertion — a real behaviour change, which is why the
  merge gate is **×5**.
- **Residue:** default `cosmetic`, **except** a row with a persistent state write on a map no
  beat enters, which is flagged for a beat instead (§14.2). Live case: `map048/ev005/p0`.
- **Notes:** none authored on generator-derived clerical rows; kept on hand rows, where the note
  *is* the argument (§14.10). A corpus-wide convention never lives in a note.

### 15.4 Tests P8b adds

- No code 118/119 ever reaches the transpile queue for the staged corpus (§14.8) — so the day a
  future chapter stages one of the 20 non-hoistable labels, it fails loud.
- A duplicate-key guard on the head tables, and the #97 divergence test (every head/code the
  transpiler handles is present in the manifest tables and vice versa).

### 15.5 What P8b does NOT close

- **#92 point 1** — identifying the non-switch grant source for field capabilities. Requirement
  groups give it a home; the source itself is still unidentified.
- **#31** — the Tandor regional dex. Independent of everything above (§14.11).
- **The reward ladder** — filed against whichever chapter first drives Quest Log ≥ 5, which
  owes it a beat.
- **P8a-2** — the archetype-template rewrite. Not a P8b prerequisite (§13.2a).

### 15.6 Correction, 2026-09-12 — `HealingSpot` is Teleport's destination, not the respawn

**§14.7 and §15.2.3 named the wrong source.** Uranium carries two unrelated globals and the
ruling conflated them. Verified in the decompiled Ruby, both directions:

| Global | Fed by | Consumed by |
|---|---|---|
| `$PokemonGlobal.healingSpot` | the `HealingSpot` **map metadata** field, re-read on every map change (`101__PField_Field.rb:1824-1825`) | the **TELEPORT** hidden move (`103__PField_HiddenMoves.rb:1211,1228`) and the region map. **Not the respawn.** |
| `$PokemonGlobal.pokecenter{MapId,X,Y,Direction}` | `Kernel.pbSetPokemonCenter` **only** (`101__PField_Field.rb:1666-1676`) | `Kernel.pbStartOver`, the white-out handler, which copies all four into `$game_temp.player_new_*` (`:1921-1948`) |

So the 22-map `healing_spot` table is the Teleport/Fly destination list. Deriving heal
locations from it would have produced respawn points that are right by coincidence where a
town has one Center and wrong everywhere else — and silently, since a white-out is invisible
to a boot walk that never white-outs. **`pbSetPokemonCenter` call sites are the only correct
source.**

Recount on the corrected source: **64 call sites across 42 maps**, not 66 across 22 — the 22
was the metadata table's row count, i.e. the other system's. In the staged corpus there is
**exactly one**: `Map068` (Kevlar Town Pokémon Center) event 1 at (8,11), a bare
`Kernel.pbSetPokemonCenter` with no arguments, so the respawn is the player's own tile at call
time, not the event's.

**The initial anchor is `MetadataHome`, not "Moki Town."** `pbStartOver` falls back to
`MetadataHome` when `pokecenterMapId` was never set, and `metadata.py` already emits that as
`URANIUM_START_MAP/X/Y/DIR = 49/7/7/2` — inside the Player's House 1F, on the spawn tile, not
outdoors in the town. **Operator ruling 2026-09-12: match Uranium faithfully — map 49 at
(7,7).** CH02's white-out beat asserts that, so it is the *initial anchor* beat rather than
the "Moki anchor" beat §14.7 called it.

Consequence for §14.7's standing precedent: unchanged. A white-out beat still goes in the
chapter *after* the one that establishes an anchor. Only the anchor's coordinates and their
derivation move.

### 15.7 Operator ruling, 2026-09-14 — generated `beat:` and `boundary` are clerical; `blocked:` is a proposal

**Why it came up.** The first disposition-pass step (`9baada83`) made a `derived_hash` sidecar
entry *be* a `cosmetic` disposition. Measured against it, CH01–CH03 still showed 231 open rows,
but only ~73 needed judgment: 63 are joins off an existing beat's `rows=`, 11 are forward
crossings, 20 carry a non-empty `requires`, and 64 are archetype-recognized rows no beat lists.
§13.2 said "the generator proposes; affirming is its own pass" — applied to all of those, that
is a ~160-row rubber-stamp review of decisions already made elsewhere.

**Ruling.** The sidecar grows from `row_id → derived_hash` to
`row_id → {disposition, derived_hash[, proposed]}` (an intermediate-format change, ruled in
under CLAUDE.md §10), and the generator derives four verdicts with §14.4's precedence:

| Verdict | Derived from | Status |
|---|---|---|
| `boundary` | `boundary_model.is_forward_crossing` | **clerical** — accepted on `derived_hash` |
| `beat:<family>` | the beat(s) whose `rows=` list the row; one family head, else no derivation | **clerical** |
| `blocked:<spec>` | `row.requires` | **proposal only** — never dispositions a row until a human copies it into the dispositions file with `affirmed_hash` |
| `cosmetic` | `may_be_derived` | clerical (unchanged, §14.2) |

A row that is undispositionable or owes a citation is never derived. The checker recomputes the
derivation itself and errors on any sidecar entry that disagrees, and a clerical derived verdict
still passes through every per-verdict rule (unregistered beat, boundary claims, capability)
except affirmation. The dispositions file stays single-writer.

**Why `blocked:` is held back.** It is the one negative claim — "untestable, so no test" —
and its model is deliberately narrow (§15.2 item 4, badge-only) with a known false-positive
history on obstacle rows (#95). A wrong clerical `blocked` silently switches testing off.
**Revisit at CH06**, when requirement groups make the capability model real.

**What this does not change.** `affirmed_hash` keeps meaning "a human looked" on every
hand-written row; the ~73-row residue (story state writes, the six undispositionable/citation
rows, `map048/ev005/p0`'s beat flag) is still hand-decided. The 64 archetype-recognized-but-
unlisted rows are closed by adding them to existing beats' `rows=`, not by P8a-2 — P8a-2 would
not make one more row derivable, since P8a-1 already declared `rows=`.

### 15.8 Operator ruling, 2026-09-15 — derived `cosmetic` follows #43(b), not state writes

**Why it came up.** A census of what CH01's unvisited houses would open found the generator
still deciding `cosmetic` on the pre-#43(b) rule: `may_be_cosmetic` was "no state-writing
tag", so a talk NPC (text, bubble, cry) derived `cosmetic`. `PROJECT_TODO.md` #43(b) had
replaced that on 2026-08-25 with *is there anything a player can press A on and observe?*;
CH04 was re-swept under it, the P8b derivation never was. Measured: **100 triggered text
rows derived `cosmetic` — CH01 79, CH02 2, CH03 19**, CH04/CH05 0.

**Ruling.** The generator follows #43(b). `ManifestRow.is_player_observable` = a page with a
player trigger (`action`/`player_touch`/`event_touch`) and any effect; such a row is never
`may_be_cosmetic`. A triggered page with no commands stays eligible; autorun/parallel pages
keep the state-writing rule. The checker's `illegal_cosmetic` names the new reason.

**Effect.** Derived `cosmetic` CH01 131 → 52, CH02 8 → 6, CH03 55 → 36; those rows rejoin the
hand-decided residue. `undispositioned` is now **CH01 132 / CH02 17 / CH03 48** (was
53/15/29). No committed hand-written `cosmetic` disposition became illegal. §15.3's "residue
default `cosmetic`" is narrowed accordingly: a triggered row the player can observe wants a
beat, or `unreachable:` when its page can't be reached in-chapter (e.g. Map064/065's
`FINAL EVENT`-gated p1 twins).


## 16. P8c — generated beats (operator rulings, 2026-09-16)

**Read this section before any further P8b/P8a work. It supersedes §15.3's hand-disposition
pass and P8a-2.** The ~182 remaining `undispositioned` errors (CH01 118 / CH02 16 / CH03 48)
are no longer hand work: they become the generator's backlog. Everything in §15.1/§15.2 that
is committed stays committed.

### 16.1 Why

§15.7's "add missing rows to existing beats" closed one row, not 64 (`88fb1a8b`); §15.8 then
put ~100 talk rows back into the residue. T2 (`fd96ba8c`) made the scale visible: the templates
derive a beat's *body*, but every instance still needed a hand-written call whose only real
content was placement. Measured corpus-wide the same day (every chapter's manifest built in
memory, rows deduplicated across map revisits): **946 `flavour_npc` rows** (704 plain / 156
toggling / 86 randomized) on 750 events across 128 maps — ~1,100 beats if all walked on
hardware. §13.3's long tail is ~40% of the ~2,586 beat-worthy pages over 630 fingerprints.
Hand authoring does not reach the end of that, and a hand-written beat is how a branch gets
missed.

### 16.2 The rulings

| # | Question | Ruling |
|---|---|---|
| R1 | Authoring | **Beats are generated.** The operator goal is zero hand overrides, and it is a hard constraint, not a target. |
| R2 | Flavour NPCs at scale | **Offline check for every row; a stratified ROM sample walks on hardware.** New verdict head **`offline:<archetype>`**, distinct from `beat:` so the two never read as the same thing in counts. A failing offline check is an **error**. |
| R3 | ROM sample | One per **variant × map × emission shape** (flag-hidden object, condition-gated page, …). **Resampled when a later chapter revisits a map** — story state has changed what its NPCs say. |
| R4 | Generator coverage | **All five archetypes** plus the generic template (R11), not flavour NPCs only. |
| R5 | Branches | **Branch arms are their own manifest rows** — each arm of a code 102 Show Choices and each code 111 Conditional Branch is a child row (`map050/ev005/p0/b2`) needing its own verdict. Manifest-schema change, ruled in under CLAUDE.md §10. Every committed hash on a branching page is invalidated and re-derived. |
| R6 | Story state and order | **One derived story-state model** over global switches, variables and self-switches, seeded from the predecessor chapter's end state. Liveness uses **RMXP's highest-live-page rule** (a page is live only if its conditions hold *and* no higher page's do). A row is walked once, at the **earliest** route position where it is live. Precedence generalizes `_derive_precedence`'s self-switch pairs to every write. Never live in the chapter → derived verdict (R8); unplaceable because precedence is cyclic → fail loud naming the cycle. The spine is generated too: no hand-written story beats. |
| R7 | Output artifact | **Whole-file generated `playtest/chapters/chNN.py`**, headed `GENERATED — do not edit`, template calls in solved order, byte-identical on re-run (§4.2). Plus `reference/routes/CHnn.route.json` and `output/beats/CHnn.review.md` (order, what each beat asserts, sampled vs offline). **No overrides file.** A row the generator cannot produce is refused and listed with its named blocker; the chapter stays red until the blocker is fixed upstream or the row carries a real verdict. |
| R8 | Row ownership | A row is owned by the **earliest chapter in the chain where the state model finds it live**. An earlier manifest gives it the derived verdict **`later:CHnn`**, which the checker verifies against CHnn's generated suite (unredeemed = error in the claiming chapter). It gates CHnn, not the manifest chapter. `unreachable:` is reserved for rows live nowhere, recorded with the furthest chapter modelled. Settles §15's open ruling and Grott Hole (`map019`, needs Strength → `later:CH25`). |
| R9 | Engine transitions | **Precondition-gated forks.** Engine-side state changes (first: **white-out** — sets `FLAG_STARTING_OVER`, moves to the tracked respawn point) are snapshot → walk what they unlock → restore, placed at the earliest point they make a row live, never on the main path, never a pinned end-of-chapter beat. White-out's precondition is a held party. The full transition list is found by grepping the fenced engine code for `FlagSet`/`VarSet`, not guessed. Under this, `map049/ev022/p0` and `map068/ev001/p1` return to CH01/CH03 (their respawn anchors are in-chapter) — **inferred, confirm when the model runs**. |
| R10 | Embedded Ruby state | **One Ruby-subset interpreter, shared with the transpiler** (§4.3). Values depending on player input fork over every outcome the consuming branch can take; each outcome is a branch-arm row reached by a search over inputs. The main path carries the first outcome in source order. An expression outside the subset refuses the row by name. Live case: `map050/ev019` (array tally in var 151 indexed by var 2, outcome = `index(max)`). |
| R11 | The long tail | **A generic page template from the source command list is the floor for every row; archetypes are layered on top, not a fallback.** Trigger derived from page trigger type; one extractor per command code, expected values **always from the RMXP source, never from converted Poryscript** (the proxy-oracle rule); visual-only commands assert only that the page completes and returns control; a code with no extractor refuses the row. Archetypes claim first and *add* stronger oracles; where both cover a command the stronger wins per extractor. Checker rule: a row's generated assertions ⊇ its generic floor. A row is offline-eligible only if **every** floor assertion is offline-checkable (a `var_write` pulls a flavour NPC into the ROM sample). T1-third, T3, T4–T11 and service NPCs are built only if the generic floor proves too weak for them. |
| R12 | CH01–CH05 | **Regenerate all five behind a frozen match-or-beat test.** Before any `chNN.py` is overwritten, freeze each hand beat's rows, assertion kinds, cells and values to `reference/frozen/hand_beats_ch01-ch05.json` (D4's `archetype_expectations.json` precedent). Generated suites must cover every frozen row with an assertion at least as strong and reproduce every frozen literal; a mismatch is fixed in the generator or state model, never excepted. One commit per chapter. |
| R13 | Scope and sequencing | **Stay on `rederive-ch01-ch04`; build only what CH01–CH05 need.** Interpreter subset, extractors and engine transitions cover exactly what the five chapters contain; everything else fails loud and is extended by the first later chapter that needs it. **No intermediate hardware check** — P11 remains the single boot gate. |

### 16.3 Steps

Each lands unit-green. None is ROM-verified before P11.

| # | Step | Rulings | Status |
|---|---|---|---|
| **C1** | Branch-arm manifest rows; re-derive CH01–CH05 manifests and sidecars; re-affirm invalidated hashes | R5 | DONE 2026-09-16 — see "C1 landed" below |
| **C2** | Story-state model: highest-live-page liveness, earliest-live placement, `later:`/`unreachable:` derivation, generalized precedence | R6, R8 | DONE 2026-09-16 — C2a (extraction + outcome table) and C2b (model, CLI); see "C2b landed" below |
| **C3** | Engine-transition forks, white-out first, with the fenced-engine grep for the rest | R9 | DONE 2026-09-16 — fork model, engine audit, `FLAG_MUM` seed; day/night deferred to its first real reader; see "C3" below |
| **C4** | Generic per-command extractors for every code present in CH01–CH05, source-derived | R11 | DONE 2026-09-17 — `beat_floor/`; see "C4 landed" below |
| **C5** | Archetype templates refactored onto the generic floor; the ⊇-floor checker rule; seam and stair floors | R11 | DONE 2026-09-17 — `beat_floor/{coverage,lookup,terrain}.py`, all five templates declare; see "C5 landed" below |
| **C5b** | Warp facing moves into the engine: retain-facing fallback, per-warp departure direction in `struct WarpEvent`, pending-facing special for script warps, door tiles yield to the warp's direction; arrival-facing table and tiers 1–3 deleted | `WARP_RETAIN_FACING_PROPOSAL.md` §0 R1–R6 | **DONE 2026-09-18** (unit-green); see "C5b landed" below |
| **C7** | Freeze CH01–CH05 hand beats — **rows + identity only; coverage is the test, not literal match** (R12 amended 2026-09-17) | R12 | **DONE 2026-09-21** (unit-green); see "C7 landed" below |
| **C6** | Generator + solver integration: whole-module emit, review doc, refusal list, idempotence test | R1, R4, R7 | **Part one DONE 2026-09-22** (unit-green; CH05 end to end); see "C6 part one landed" below. Part two (map continuity, boundary claims, A5, CH01–CH04) IN PROGRESS |
| **C8** | Shared Ruby-subset interpreter + input search; `map050/ev019` | R10 | **IN PROGRESS** — shape ruled 2026-09-23; see "C8 shape" below |
| **C9** | Regenerate CH01–CH05 behind the frozen test, one commit per chapter | R12 | TODO |
| **C10** | `offline:` verdict head, offline flavour checker, ROM sample selection | R2, R3 | TODO |

**C1 shape (operator, 2026-09-16):** (a) every code 111 yields **two** arm rows, then and
else, even when the source has no 411 — the fall-through is a walkable path; (b) the parent
page row is **trunk only**: its effects and hash cover commands outside every arm (a 111's
condition text runs in the enclosing scope, so it is trunk), and each arm row covers its own
scope with nested arms excluded — no effect counted twice; (c) arm ids are **flat `bN`** in
source order of arm openers across the page (`map050/ev005/p0/b2`), with a `parent_row_id`
field for nesting, sorted numerically. Code 112 loops are not branches and stay in their
enclosing scope. Measured load: 111s CH01 113 / CH02 51 / CH03 43 / CH04 22 / CH05 13; 402
choice arms CH01 21 / CH03 11; no 403 cancel arms.

**C1 landed (2026-09-16).** `schema.BranchRef`, `kind="branch"`, `parent_row_id`, one
`parse_row_id` / `row_id_sort_key` (the duplicate regexes in `boundary_model.py` and
`playtest/chapter.py` are gone); the generator walks the transpiler's own `parse_tree`. Three
details beyond the shape above: an arm's hash includes its `BranchRef`, so an arm goes stale
when its condition changes and not only its body; a page with **no** arms hashes exactly as
before, so only branching pages were invalidated; and `schema.whole_page_views` folds arms back
into their page for **what-is-this-page** questions. `archetypes.classify_manifest` uses it,
because D4's fingerprints are whole-page facts; without it `map035/ev001/p1` read as a bare
`warp` and CH05 failed to import. All **47** stale page decisions (CH01 3 / CH02 16 / CH03 2 /
CH04 17 / CH05 9) were re-affirmed mechanically, on proof that each old `affirmed_hash` equals
today's whole-page hash, so the source under the decision is unchanged and trunk ⊆ page.
Result: rows CH01 458 / CH02 171 / CH03 222 / CH04 86 / CH05 43. Errors are now only
`undispositioned` + `derived_unaffirmed`: page rows CH01 116 / CH02 13 / CH03 45, branch
rows CH01 163 / CH02 63 / CH03 51 / CH04 36 / CH05 10. That is the generator's backlog, not
hand work. `archetype_conformance` was verified row-for-row identical to the pre-C1 checker.
**Debt handed to C5:** archetype templates claim page rows only, so arm rows of claimed pages
stay unclaimed (e.g. `map035/ev001/p1/b0,b1` → `boundary_unclaimed`, pinned in
`test_check_real_ch04_carries_no_boundary_dispositions_yet`); `approach_model` answers `None`
for branch rows.

**C2 shape (operator, 2026-09-16):** (a) **per-family outcome table** — every condition
family in `conditions.py` declares, per arm, how that arm becomes live: player input, random,
evaluated from modelled state, an engine fork (trainer loss → C3 white-out), a harness
primitive, a capability, or not yet modelled. An unmodelled family or unclassified condition
refuses the arm by name. Type-6 facing checks are player input. (b) **Contrived arms are
walked**: an arm reachable only through a contrived setup (item-ball else-arm on a full bag)
is a real branch, and the missing harness state is its named blocker until the primitive
exists — no new verdict, no `unreachable:`. (c) **Random outcomes: offline all, ROM first** —
every outcome is live and checked offline (C10); a ROM walk asserts whichever outcome the RNG
produced is in the valid set. No RNG-control primitive. (d) **CH01 is seeded from the intro
chain**: the model runs over unbound Intro map 51 and whatever it transfers through to the
first CH01 arrival; C3's fenced-engine grep checks that the `new_game.c` override sets the same
state and fails loud where it doesn't.

(e) **Day/night is clock input, and the engine owes it** (operator, same day, found by
C2b's triggered-common-event guard): common event 51 (parallel, gated on switch 51 GAME
RUNNING, set on map048) sets switch 105 DAY / 106 NIGHT from the real-time hour every 200
frames. Triggered common events become modelled pseudo-rows (`common/ceNNN`), and a
`time_of_day` condition family is player input (the clock), so once GAME RUNNING is possible
both 105 and 106 are possible and day-only and night-only rows are all live. **C3 carries CE
51 as an engine transition the ROM must implement from the RTC** — nothing sets 105/106 today,
so CH01–CH03's 19 night-lamp `Luz` events (Moki 11, Kevlar 7, Route 1 1, all on 106) never
show. A ROM walk of a night row names `set_clock` as its harness blocker. CH06 Nowtoch has 60+
rows gated the same way. *(Corrected 2026-09-16 by C3: the 19 lamps are no-port under the
2026-08-05 ruling, so nothing in CH01–CH05 is missing; day/night is deferred to its first real
reader. See "C3 closed".)*

Design (lead, same day). **C2 builds the model; C6 orders it.** Package `story_state/`: per
row (page trunk or arm scope) its **reads** (page conditions; 111 types 0/1/2; families via
the table) and **writes** (121/122/123; `pbSetSelfSwitch`, `$game_switches[N]=`,
`$game_variables[N]=`/`pbSet` with constant values; 117 inlines the common event's writes); a
non-constant or unparsed write refuses the row by name until C8. Values are **sets** (a switch
is `{False}`, `{True}` or both; a random 122 gives its range), so "possibly live" is exact
under forks. Liveness is RMXP's highest-live-page rule plus the arm's guard and every ancestor
arm's guard. Temp switches (`tsOn?`/`tsOff?`, `setTempSwitchOn`) reset on map entry, so they
behave like per-visit input. Autorun and parallel pages are **forced**: they fire as soon as they
are live on the player's map. Chapters are modelled in chain order, each over the maps of
every chapter up to itself (backtracking is allowed), seeded from its predecessor's end state.
The model outputs a **partial order**: `enabled_by` (writes a row needs, as any-of groups),
`killed_by` (writes that end its liveness), ownership (`later:CHnn` / `unreachable:` with the
furthest chapter modelled), and the chapter's end state. *(Amended same day, after real data: the first rule here
failed loud whenever two unordered rows wrote different values to one key. CH01's lab door
and Auntie both unlock at variable 101 ≥ 1 and set switch 104 ON and OFF, and the player may
do them in either order — the order is C6's to choose, not an error. Now: writes within one
page execution are ordered by list index, with mutually exclusive arms joined; conflicting
unordered writes across pages **join** and are listed as `order_dependent` keys in the
report. C2's end states are sound over-approximations, and **C6 recomputes each chapter's seed
from its concrete route**. Refusals do not starve saturation: guard-refused rows still
contribute their parseable writes, unparsed writes make the keys they name "any value", and a
row that is not live because of either is `undetermined`, not `unreachable`.)* Split: **C2a** extraction + outcome
table + refusals; **C2b** liveness, saturation, partial order, chain seeding, ownership, CLI.

**C2b landed (2026-09-16).** `story_state/model.py`: `_live_status` (highest-live-page rule plus
ancestor arm guards), `saturate` (fixpoint), `compute_enabled_by` / `compute_killed_by`,
`compute_end_state` (per-page shadowing by `list_index`, sibling arms joined, cross-page
conflicts recorded as `order_dependent`, only a precedence cycle raises), `model_intro` (CH01's
seed from the Intro chain) and `build_chapter_stories` (chain walk, `later:CHnn` / `unreachable`
/ `undetermined`). `extract.py` gained `havoc_keys` / `havoc_global` for unparsed writes and
`extract_triggered_common_events` (`common/ceNNN` pseudo-rows; a refused pseudo-row whose gate is
possibly true fails loud). `conditions.py` gained `time_of_day` (ruling (e)), the one compound
condition that classifies. CLI: `python -m rpg2gba.story_state report --chapter CHnn` →
`output/story_state/CHnn.json`. Measured, row status per chapter (chain modelled through each):

| | live | refused | unreachable | undetermined |
|---|---|---|---|---|
| CH01 | 261 | 101 | 77 | 18 |
| CH02 | 157 | 24 | 4 | 0 |
| CH03 | 196 | 15 | 16 | 0 |
| CH04 | 63 | 19 | 0 | 2 |
| CH05 | 51 | 0 | 0 | 0 |

The only `order_dependent` key is CH01's switch 104 (`map049/ev001/p2` vs `map050/ev001/p1`,
the amendment's case). CH01's refusals are mostly `unparsed_state_write` (C8's interpreter) and
`unmodelled_outcome` (outcome-table gaps). **Not yet confirmed:** R9's inference that
`map049/ev022/p0` / `map068/ev001/p1` return to their own chapters waits on C3.

**C3 (2026-09-16).** Measured from source: `Kernel.pbStartOver` sets switch 5 Starting Over on
both its Pokémon Center and `MetadataHome` paths and moves the player to
`$PokemonGlobal.pokecenterMapId` (`101__PField_Field.rb:1920-1978`), which only
`pbSetPokemonCenter` writes; before any call it is home, map 49. Wild and trainer losses both
reach it. Design (lead): `story_state/transitions.py` declares transitions, engine obligations
and harness-only engine writes. **White-out**: precondition switch 2 Got Pokemon (set only by
the starter choice, `map050/ev019`), write switch 5 := ON, lands on `EngineKey("respawn_map")`,
which extraction now writes from `pbSetPokemonCenter` and the Intro seeds from
`initial_anchor()`. The fork runs per chapter over the chapter's **saturated** state (a
white-out before CH03's center visit still lands on 49), walks only rows on the landing maps
plus pseudo-rows, owns what it unlocks with blocker `fork:whiteout` and `enabled_by`
`engine:whiteout`, and never touches the end state. **R9's inference confirmed:**
`map049/ev022/p0` is CH01's (landing [49]); `map068/ev001/p1` is owned by CH03 (landing
[49, 68]), still reported `refused` for its soft `$Trainer.party.length` write (C8);
`map048/ev013/p0` stays `unreachable` because white-out never lands on 48. `story_state/
engine_audit.py` + `python -m rpg2gba.story_state engine-audit` scan the four sentinel fences
for `FlagSet`/`FlagClear`/`FlagToggle`/`VarSet` and fail on undeclared writes, missing
transition writes, owed obligations, and Intro-seed keys a chapter reads that `new_game.c`
doesn't set. Only two fenced writes exist (`DoWhiteOut`'s `FLAG_STARTING_OVER`, the harness's
`FLAG_BADGE03_GET`). First run found two gaps: **switch 52 Mum** (Intro sets it,
`map049/ev002/p1` reads it) and **CE 51 day/night** (switches 105/106 unnamed and unset).
**Operator, same day:** fix both in the engine as part of C3: a fenced `FlagSet(FLAG_MUM)` in the
spawn override, and 105/106 named and set from the RTC.

**C3 closed, same day.** `NewGameInitData` sets `FLAG_MUM` after vanilla's map-flag reset,
fenced; the audit treats a `new_game.c` write matching the Intro seed as declared. **Day/night
was re-ruled once measured:** every CH01–CH05 row reading 105/106 is a `Luz` lamp, all 19
already under the 2026-08-05 no-port ruling (map 31's seven and map 33's one were listed; map
32's eleven, the same kind, were not, and are now). Corpus-wide, 387 rows read 105/106 and only
22 are not lamps (maps 12/40/60/93/101/183). The registry also mints `FLAG_*` only for a live
reader, so naming the flags now would have meant working around §6. **Operator:** an
obligation is owed only when a row the ROM keeps reads its switches. `chapter_read_keys` skips
strip-listed events, and a reader-less obligation is reported as `deferred_obligations`, not
failed. The first chapter with a real reader implements CE 51 from the RTC (Uranium's boundary:
day is 6 ≤ hour < 20, `112_PField_Time_v17.rb:42-49`; hook alongside `DoTimeBasedEvents`,
`engine/src/clock.c`). `engine-audit` now exits 0.

**C4 shape (operator, 2026-09-16):** (a) **script 355/655 has one extractor per call head**
(`census._script_head`), not one per code; visual-only heads (`pbCallBub`, 324) assert only
completion; a head with no extractor refuses the row by name. The same holds for 111 type 12:
one extractor per `conditions.py` family, and an unclassified condition refuses. (b) **Move
routes assert net displacement where it is predictable**: the moved character's `(dx, dy)`
and final facing, derived from the source steps. A route with an unpredictable step (random,
toward/away player, a skippable or repeating route, step-forward with unknown facing) asserts
only completion. (c) **Audio (241/242/249/250) is audio-only**: completion plus an
`audio`-tagged assertion, not checked until audio is mapped, and it doesn't refuse the row.

Design (lead, same day). Package **`beat_floor/`** (neither `playtest` nor `chapter_manifest`
imports it the wrong way: the checker reaches it at C5 and the generator at C6).
`assertion.py`: frozen `FloorAssertion(row_id, kind, list_index, code, params, offline,
tag)` and `FloorRefusal(row_id, code, list_index, reason, detail)`, plus
`RowFloor(row_id, trigger, assertions, refusals)`. The floor is a **set**. Order is not
asserted, which makes loops (112/113), labels (118/119) and the ⊇ rule trivial. **Every row gets
`trigger` and `completes`.** State writes are **not re-derived**: `switch_write` /
`var_write` / `self_switch_write` come from `story_state.extract`'s `RowState.writes` (§4.3),
so a 121/122/123 or a state-writing script head contributes through the story model, and a
write refused there refuses the floor row. Offline-checkable kinds: `text`, `choice`,
`switch_write`, `self_switch_write`, `warp`, `heal_party`, `erase_event`, `item_grant`;
ROM-only kinds: `var_write` (R11's own example), `displacement`, `event_position`,
`battle`. Code 117 inlines the common event body's assertions, attributed to the calling
117's `list_index`. Code 115 ends its scope's walk. Code 111's *condition* runs in its
enclosing scope, so a type-12 family extractor belongs to the enclosing row. CLI:
`python -m rpg2gba.beat_floor report --chapter CHnn` → `output/beat_floor/CHnn.json`. A
census test pins every (code / head / family / move-step) present in CH01–CH05 to an extractor.

**C4 landed (2026-09-17).** `beat_floor/{assertion,walk,script,condition,move_route}.py`.
Three details beyond the design above: (1) the contract gained **`pokemon_grant`** and
**`service`** (ROM-only). A first pass had tagged marts, PCs, save, the starter selector and the
online features as `visual`, which would have silently weakened the floor: `visual` means
presentation only. (2) **`skippable` routes stay predictable.** Ignore If Can't Move only
changes what a blocked step does, and collision is not modelled. The one-route
`step_forward_unknown_facing` pair is the only other unpredictable reason. (3) Stair events
absorbed into `terrain` rows get no floor. A real-corpus test pins the floor's rows to exactly
each manifest's `page`+`branch` rows; seam and terrain rows have no event commands, and they
are C5/C6's business. Measured (report is byte-identical on re-run):

| | rows | refused | offline-eligible |
|---|---|---|---|
| CH01 | 457 | 56 | 334 |
| CH02 | 164 | 3 | 134 |
| CH03 | 218 | 18 | 157 |
| CH04 | 84 | 3 | 65 |
| CH05 | 39 | 0 | 35 |

**Zero `no_extractor`.** Refusal reasons: `text_unnormalizable` 82 (#109's `"`/`[`/`*`, plus
`\v[N]`; §16.4), `story_state_refusal` 32, `unknown_script_head` 38 and `non_literal_args` 19
(embedded Ruby: assignments, `for` loops, `createPhoneTrainer` locals feeding
`customTrainerBattle`; all C8), `unclassified_condition` 6. **Found in passing, not fixed:**
`conditions.py`'s `pb_trainer_battle` docstring says CH01–CH05 has no `canlose=true` site, but a
rival battle passes `canlose=true` with result variable 7. Check this when the white-out fork
reads trainer losses. `story_state` still models stair-absorbed events as rows (harmless: they
carry no writes). Suite **3790 passed / 16 skipped**.

**C5 shape (operator + lead, 2026-09-17).** (a) **Seam and terrain rows get a floor in C5**
(operator): they have no command list, so C4 left them out, and R1's zero-hand-beat rule would
otherwise leave B1/B13/B14-shaped rows with no oracle at C9. Two row-level ROM-only kinds:
`seam_crossing` (both sides of the `connections.json` pair) and `stair_crossing` (cell, side,
and the per-step diagonal displacement derived from the RMXP stair event's facing branches and
move codes). The ⊇ rule then has no row-kind exemption. (b) **Declared assertions, one
vocabulary** (lead): `Beat.assertions: frozenset[FloorAssertion] | None`; `None` is
undeclared, which is not the same as declaring nothing. `beat_floor/coverage.py` holds the one
definition: a floor assertion is covered by a declared one with the same `(row_id, kind,
list_index, code)` whose params include the floor's params with equal values. Extra params are
how an archetype is stronger (arrival facing, BGM id, exact nudge delta). An extra that
contradicts a source param fails loud at registration. (c) **Honest declarations**:
`playtest.archetypes.declare_assertions` declares a row's floor filtered to the kinds the
template's body actually executes, plus extras. An unexecuted kind is left undeclared, so the
checker reports it rather than the template claiming it. Each template's declared kinds are
pinned by a test that proves the body checks them. (d) **Refused floors** skip the ⊇ rule; the
refusal is the row's named blocker. (e) **Severity**: a declared shortfall is an error; an
undeclared (hand-written) beat claiming a row is reported, not failed, until C9 replaces the hand
suites. A `GENERATED` module (C6) has no undeclared beats by construction. (f) Branch rows: a
template claims and declares the arm rows its walk actually traverses; the arms it does not walk
stay for C6's generic template.

**C5 landed (2026-09-17).** `beat_floor/coverage.py` (`assertion_key` / `covers` /
`uncovered` / `contradicts`), `beat_floor/lookup.py`, `beat_floor/terrain.py`
(`seam_floors_for_map`, `stair_floors_for_map`), `chapter_manifest/floor_model.py`, and four
checker rules — `floor_uncovered`, `floor_undeclared`, `floor_missing`,
`floor_model_unenforced` — wired into `chapter_manifest check`. All five templates declare
through one `archetypes.declare_assertions`; `Beat.assertions` is `frozenset[FloorAssertion]
| None`, `None` meaning undeclared. Stair displacement is derived from the RMXP event's
type-6 facing branch and its 205/209 move codes, refusing by name
(`stair_no_qualifying_page`, `stair_branch_not_singular`,
`stair_unknown_facing_direction`) rather than guessing. Item (f) is real: `warp` and
`arrival_nudge` share one `walked_arms` helper, `item_ball` claims only the `"always"` arm
(leaving the bag-full harness arm), `trainer` claims only the arm carrying the defeat write,
and `flavour_npc` claims no arms at all. Suite **3861 passed / 16 skipped**.

Four stale pins were updated, not weakened: three `item_ball` expectations in
`test_playtest_archetype_templates.py` (a claimed arm turns `archetype` into a row→name
mapping and adds the arm to `rows`), and C1's deliberate CH04 pin
`test_check_real_ch04_carries_no_boundary_dispositions_yet`, whose two unclaimed nudge arms
became one — `b0` is now claimed, `b1` waits for C6.

Only **CH05's** sidecar moved (`map036/ev002/p1/b0` `cosmetic`→`beat:B8`, plus derived
entries for the two newly-claimed item_ball arms); CH01–CH04 regenerate byte-identically,
which is §4.2 idempotence holding. Measured after regeneration:

| | errors | `floor_uncovered` | `floor_undeclared` (warning) |
|---|---|---|---|
| CH01 | 279 | 0 | 24 |
| CH02 | 76 | 0 | 30 |
| CH03 | 96 | 0 | 34 |
| CH04 | 36 | 0 | 10 |
| CH05 | 14 | **6** | 7 |

**Why the ⊇ rule only bites CH05, and what its 6 errors are (operator-ruled 2026-09-17).**
`ch05.py` is the *only* chapter module that imports the archetype templates; CH01–CH04 are
hand-written and declare nothing, so every one of their rows lands in `floor_undeclared` — a
warning by ruling (e), precisely because C9 replaces those suites. `floor_uncovered` can
only fire on a row that declared something, and only CH05 has any. The other four are not
passing the ⊇ rule; they are not yet graded by it.

All 6 are the **`trainer` template, and all name one missing capability: it does not assert
the approach cutscene.** `map036/ev004/p0`, `map036/ev006/p0` and `map037/ev004/p0` each
miss five floor assertions — `pbTrainerIntro` (audio), `pbNoticePlayer` and `pbCallBub`
(visual), the pre-battle line (`text`), and `pbTrainerEnd`; their `p1` pages each miss
`pbCallBub`. `warp`, `item_ball` and `arrival_nudge` cover their floors in full. **Ruled:
accept as named debt.** The floor already enumerates exactly what is missing, and C6's
generic template emits it for free; hand-authoring those oracles now is work C9 deletes, and
inverts §4.1. Do not "fix" this by strengthening `trainer.py` — the fix is C6.

C1–C6 stand on their own. C7 must land before C9 overwrites anything. Route plans (P9) become
a C6 output rather than a separate step.

**C7 and C6 swapped, 2026-09-17 (operator).** C7 now runs first. **The step labels are stable
identifiers, not sequence numbers** — every "the fix is C6" / "waits for C6" reference elsewhere in
this file still means the generator, and C6_GENERATOR_PLAN.md is unaffected in scope. Renumbering
was rejected precisely because those references would rot.

Why: nothing ever required C6 first. The only stated constraint was C7 before C9, and the C6-first
listing was presentation order. Freezing first (a) removes the safety question of where C6's emit
may land — C9 still owns overwriting `chNN.py`, but nothing irreplaceable is at risk, and (b) gives
the generator a fixed grading target from day one instead of an ad-hoc diff against hand modules.
C7 depends on nothing C6 builds.

**C7 gains a validation pass (same ruling).** CH01–CH04 declare no assertions, so every row lands in
`floor_undeclared` and `beat_floor.coverage.contradicts` has never been able to fire on them: their
literals have never been checked against the source floor. Freezing them unvalidated collides with
R12's "a mismatch is fixed in the generator or state model, never excepted" — a wrong hand literal
would become ground truth the generator is then required to reproduce. This is §5's warning ("some
literals are load-bearing ROM-verified truth, and the AST ratchet counts literals without ever
asking whether one is still true") pointed at the freeze. So: before `hand_beats_ch01-ch05.json` is
blessed, every captured value is run through `contradicts` against its row's `RowFloor`, and
contradictions are adjudicated as hand-beat bugs **then**, while fixing them is ordinary work.
Afterwards the file is authoritative and R12's no-exceptions rule is safe to apply.

The rejected steelman for C6-first was that the generator's output shape should dictate the freeze
shape. C5 already shipped the comparison vocabulary (`assertion_key` / `covers` / `contradicts`), so
the freeze can be expressed in `FloorAssertion` terms today without waiting.

**Measured 2026-09-17, and it makes C7 bigger than the swap assumed.** C7 is still independent of
C6, but it is not cheap. `ChapterBuilder.beat()` (`playtest/chapter.py:398`) accepts a declarative
`assertions=frozenset[FloorAssertion]`, and **0 of the 95 beats across CH01–CH05 pass it**
(22/19/36/13/5); `Beat.assertions = None` is the documented expected state for a hand-written beat.
Assertion kinds, cells and values live inside beat bodies as imperative calls against a live
`Emulator`. The repo's one existing static capture, `scripts/freeze_rederivation.py::_beat_dicts`,
captures only `name`/`own`/`group`/`rows` and deliberately does not touch `beat.assertions`. R12's
cited precedent, `reference/frozen/archetype_expectations.json`, was **hand-authored from prose** by
its own header's admission ("CH05 matches below are DERIVED FROM PROSE ONLY, not verified
byte-exact").

So capture is one of: hand-author 95 beats' values; bespoke AST extraction over the ~20 assertion
helpers; or emulator-driven recording — **the third collides with the standing rule that P8b work
lands unit-green and chapter walks wait for the P11 gate.**

**R12 AMENDED 2026-09-17 (operator). Freeze coverage, not literals.** The generated suite is **not**
required to reproduce the hand suite's literal values, and **is not required to route the same way** —
beat order, grouping and approach differences between the hand and generated suites are expected and
fine. The requirement is a floor, not a match: **the generated suite must cover everything the hand
suite covered, at least as well.** Covering *more* is the expected outcome, not a failure.

This replaces "reproduce every frozen literal" in R12 as originally written. Consequences:

1. **What gets frozen** shrinks to what is mechanically capturable today: the set of rows each hand
   beat claims, plus beat identity. `scripts/freeze_rederivation.py::_beat_dicts` already captures
   `name`/`own`/`group`/`rows` — no per-beat literal transcription, no AST extraction, no emulator
   capture. The expensive capture problem above dissolves.
2. **Order and grouping are captured but NOT graded.** They are recorded for review only; a routing
   difference is never a failure.
3. **Grading is two rules:** (a) every frozen row is claimed by some generated beat, and (b) each
   generated beat's assertions ⊇ that row's floor (C5's existing ⊇ rule). Values come from the source
   floor, which is also what made the separate validation pass unnecessary — the floor *is* the
   oracle, so there is no hand literal left to validate.
4. **The hand suites are not deleted on a green test.** C9 does not overwrite `chNN.py`. The
   generated module lands alongside the hand module, both are kept, and removal of the hand suite is
   a **separate operator-gated step** taken only after coverage is confirmed. Note for whoever
   implements this: while both suites exist, two beats claim the same rows — check
   `RULE_UNREGISTERED_BEAT` and `RULE_ARCHETYPE_CONFORMANCE` tolerate double-claiming, or scope them
   per-module.

**The one real gap in this scheme, and it must be handled explicitly.** Floor-⊇ grading proves the
generated suite covers the hand suite only for hand content that is *derivable from the RMXP source*.
Hand beats also assert things the command list cannot show — negative beats (an exit is blocked,
something does *not* happen), hardware-observed facts, and beats claiming no row at all, which a
row-coverage test cannot even see. These are **not** covered by rules (a) and (b) and would be
silently lost. They must be enumerated and adjudicated one by one, not auto-graded.

**Residue measured 2026-09-17 (AST parse of the five modules, not grep).** Corpus is **91 beats**,
not 95 — ch01 22 / ch02 18 / ch03 35 / ch04 13 / ch05 5; the earlier 95 came from a `grep -c` that
counted commented-out decorators.

| | ch01 | ch02 | ch03 | ch04 | ch05 |
|---|---|---|---|---|---|
| beats | 22 | 18 | 35 | 13 | 5 |
| claim a row | 16 | 14 | 21 | 10 | 5 |
| **claim no row** | **6** | **4** | **14** | **3** | **0** |
| negative beats | 3 | 2 | 8 | 1 | 0 |

**27 of 91 beats claim no row at all** *(corrected 2026-09-21: 27 of **111** registered beats — 22/19/35/14/21; the 91 was a decorator count. The 27 stands: CH01 6 / CH02 4 / CH03 14 / CH04 3 / CH05 0, confirmed against `reference/frozen/hand_beats_ch01-ch05.json`)* and are invisible to row-coverage grading. In ch03 the rowless
set is almost entirely two families: arrival-BGM beats with their reciprocal-warp partners
(`B27`–`B33`), and every negative beat (`N1`, `N2`, `N4`, `N6`, `N7`). That is not incidental — a
negative or audio fact has no command-list row to point at, so the authors claimed none.

**CH05 contains none of this risk** — zero rowless beats, zero negative beats. It is therefore a fine
proving ground for generator *mechanics* and a useless one for this residue. (Bears on
`C6_GENERATOR_PLAN.md` question C1.)

**Triage — most of the residue is derivable from a source other than the page command list.** "Not in
the command list" is not the same as "not derivable," and the distinction decides how much is
genuinely hand work:

1. **Derivable from a different source; wants a new extractor, not a hand beat.**
   - *BGM* (`ch03.B29/B31/B33`, and `assert_bgm=True` in CH05's templates): the value is the compiled
     map's own `music` header field. `beat_floor/` has **no audio extractor at all** today.
   - *Blocked movement / impassable edge* (`ch01.B2`, `ch01.N4`, `ch02.N1/N2`, `ch03.N7/B15/B25`,
     `ch04.B6`): collision and passability come from the traversal graph. `beat_floor/terrain.py` is
     the precedent — a row-level kind with no command list behind it.
   - *Arrival position and facing* beyond the bare warp destination: the floor's `warp` kind carries
     no facing param today.
2. **Already derivable — via the state model, not the page.** The no-refire / no-op-page beats
   (`ch01.B14`, `ch03.N1/N3/B12`) assert that a *second* interaction hits a different page. Under
   R6's highest-live-page rule that is a source fact C2 already models; grading them means floor-ing
   the other page, not inventing an oracle.
3. **Genuinely not source-derivable; stays hand-authored or moves house.**
   - *Cross-chapter unobtainability* ("Rock Smash is unobtainable this chapter" — `ch01.N4`,
     `ch02.N2`, `ch03.N7`): a claim about chapter scope, not about any row. This arguably belongs to
     the chapter atlas or `story_state`, not to a beat.
   - *No-crash / no-void at an unbuilt edge* (`ch03.B25`): an assertion about the absence of an
     engine failure mode.
   - *`emu.field_locked()` as a proxy for "something happened"*: pervasive, with no floor kind.
   - *Live party/species RAM reads* (`player_starter_species`, `party_has_species`).

**DECIDED 2026-09-18 (operator, grill session).** Three corrections to the triage above came out of
reading the code first, and they changed the rulings:

- *The floor's `warp` kind already carries the direction* — `beat_floor/walk.py:209-212` records
  `direction=params[4]`. The "no facing param" line above is wrong.
- *Every built map's header music is `MUS_LITTLEROOT`* (`metadata_wiring.py:81` `DEFAULT_MUSIC`,
  never overridden; Uranium BGM is unconverted pending `PROJECT_TODO.md` #22). The hand BGM beats
  compare the header to itself and are vacuous today.
- *The "blocked movement" beats are not collision tests.* `ch01.N4`, `ch02.N2`, `ch04.B6` (Rock
  Smash) and `ch03.N7` (Strength) are field-move obstacles in a chapter with no grant site — the
  capability model's `blocked:<cap>` verdict, which the hand beats simply never claimed. `ch01.B2`
  already claims its row. `ch03.B25` is the map-edge case, below.

| Residue | Ruling |
|---|---|
| Arrival position + facing | **Extractor, delivered inside C5b.** The `warp` floor gains `arrives_on_door` from the emitted layout; the generator resolves dir 0 from its own approach and computes the final cell (destination + the door auto-step in the facing direction, `WARP_RETAIN_FACING_PROPOSAL.md` §0 R5). Covers the P11 nudge risks (CH02 B1, CH03 B16). |
| BGM | **Named debt, non-blocking, tied to #22.** No extractor over a placeholder. When #22 lands a substitution table, the extractor comes with it (header music = `audio_map.json`[RMXP BGM]). The debt does **not** block the hand-suite removal step; #22 may stay open indefinitely. |
| Field-move obstacles | **Extractor now (C7 residue work, before C6):** a `blocked_obstacle` floor kind per row dispositioned `blocked:<cap>` — interaction leaves it in place (no erase, no state write) and its tile stays impassable. **C6 groups these beats by (map, blocking capability)**, matching the hand N4/N7 split; each assertion carries its row id, so a failure still names the rock. |
| Cross-chapter unobtainability | **Does not move to the atlas.** It is already the capability model's fact (`capability_sites.py`, `RULE_BLOCKED_NO_GRANT_SITE`/`RULE_BLOCKED_ALREADY_GRANTED`), and the ROM consequence is the `blocked_obstacle` kind. A second home would violate §4.3. |
| `ch03.B25` map edge | **Retired as adjudicated residue.** Its premise (Route 2 unbuilt) is gone; it now tests one wall column. The void/crash defect class is caught at build time by `connections.py` (unminted target, out-of-build target, bidirectionality). The hand beat stays in `ch03.py` until hand-suite removal; nothing is owed. |
| Live party reads, `emu.field_locked()` | **Not residue.** Party reads verify the existing `pokemon_grant` kind (`beat_floor/script.py:199`); `field_locked()` is a harness technique, not a claim. |

Group 2 still needs no ruling — covered, just not wired.

**One correction to R12's mental model, from the same measurement.** CH05's template beats express
BGM as an *extra param* on the existing `warp` assertion. Since the source floor carries no `bgm`
param, `coverage.contradicts` cannot check it — `coverage.py`'s rule is that extra declared
assertions with no floor key are allowed and ignored. So CH05's BGM checks have exactly the same
epistemic status as CH01–CH04's: an un-cross-checked literal, merely packaged in the structured type.
Being expressed as a `FloorAssertion` does not make a claim source-verified.

**Superseded below (kept for the reasoning, no longer the question):** the validation pass exists
because hand literals have never been checked against the source floor. If every frozen literal must
be validated against the floor anyway, the floor is the value oracle — so freezing the literal may be
the wrong thing to freeze. A coarser freeze (rows, beat identity, assertion *strength* — roughly what
`freeze_rederivation.py` already captures), with values taken from the floor, collapses the capture
problem and the validation pass together, and sits better with §5's warning that a hand literal may
no longer be true. The cost is that R12's "reproduce every frozen literal" weakens to "cover every
frozen row at least as strongly," which is a weaker guarantee against silent regression.

**C5b added 2026-09-18 (operator).** Warp arrival facing is re-founded on the departure side; the
full rulings and measurements are `WARP_RETAIN_FACING_PROPOSAL.md` §0, which is the authority —
this entry only places the step. It lands **before C6** so the generator derives warp assertions
from the final model rather than from `compute_arrival_facings`, which C5b deletes. It is
independent of C7 (C7 freezes rows and identity, not facing literals). Scope, in landing order:

1. Engine (`engine/`, fenced `URANIUM PATHFINDER SLICE`, gated on `RPG2GBA_WARP_RETAIN_FACING`,
   default ON): retain-facing fallback; `ScrCmd_warp` stores instead of resets; `struct WarpEvent`
   direction byte + `warp_def` + `mapjson` + size `STATIC_ASSERT`; departure override in the
   step-on/door paths; `SetWarpArrivalFacing` special with clear-on-map-load; door branch yields
   to the stored direction. `make modern` clean.
2. Pipeline: `metadata_wiring` emits `"facing"` on departure warps from `dest_dir`; the transpiler
   emits the special before `warp(...)` for explicit `params[4]`; delete `compute_arrival_facings`,
   the ON_WARP_INTO_MAP_TABLE facing block, `_derive_retain_facing`, and
   `reference/warp_facing_overrides.json`.
3. Tests: rewrite `tests/test_warp_facing_invariant.py` onto the new semantics (tier-3 assertions
   replaced, not deleted; wall-facer pin reworded "decided: faithful"); add R5's door-tile guard;
   re-source `ch03.py::_expected_arrival_facing` from RMXP `dest_dir`.
4. Floor (added 2026-09-18, C7 residue ruling): the `warp` floor kind gains `arrives_on_door` from
   the emitted layout, so a beat's expected final cell is derivable (destination + auto-step in the
   facing direction). Dir-0 facing is resolved by the generator from its approach, not the floor.

Unit-green only. **ROM risks carried into P11:** the Moki (32)(8,43..45) ↔ Route 1 (33)(70,11)
edge stack (the only built-map case where door-south and the authored direction disagree), the
three never-walked explicit-direction script warps (map032/ev078, map049/ev021, map172/ev004),
and dir-0 building exits whose arrival auto-step now follows the approach direction.

**C6 part one landed 2026-09-22** (unit-green; no ROM run — P11). The `assignments/C6/` brief, all
nine tasks, delegated to the build agent in full by the operator. Suite **4127 passed / 16 skipped**
(two halves, #111). `python -m rpg2gba.beat_gen generate --chapter CH05` writes
`output/beats/{ch05.generated.py,CH05.review.md,CH05.route.json}`: 20 beats, 14 groups, 35 rows,
**0 refusals**, 8 elsewhere (the surf item balls). Each task's commit answers its Questions. What
the build found:

- **Boundary warps** (Task 9's blocker): a warp whose destination is on no map of the chapter
  chain is a boundary. `warp_beat(boundary=True)` stops on the approach cell, never steps on,
  claims the row and declares nothing (the crossing is owed to the chapter being opened, §10 R2).
  It stops short because standing on the tile, as hand B11 does, asserts "unstaged", which breaks
  the day the next chapter stages (hand ch04's B7, 2026-09-04). The duplicate-exit bug is fixed
  in `traversal/warps.py`.
- **CH01 refuses 215 rows**, not B2's 56. B2 measured floor refusals only; the full rule table
  adds 94 `undetermined` story rows and story-headed refusals. B2's exit criterion is unaffected.
- **Generic template**: four lead fixes the offline tests couldn't reach (trigger vocabulary
  `player_touch`, one page run per beat instead of one per arm row, fire from an adjacent cell,
  seam edge letter vs press). Known P11 limit: a page's arms are often mutually exclusive, and one
  walk takes one.
- **Diff vs hand CH05**: hand-only = CH04's three `map035/ev001` boundary rows (R2/R3 successor
  claims, which the generator doesn't produce yet); generated-only = eleven branch arms. Visit
  order matches.
- **Top finding, drives part two:** the generated suite doesn't track which map the player is on
  between beats. Every warp round-trips from its own map, so three of CH05's four warps start or
  end on the wrong map, and the 1F nudge runs while the player is on 2F. The hand module solved
  each case by hand. Part two opens with a map-continuity pass, successor boundary claims, and a
  route entry taken from the predecessor's end (A5).

**C7 landed 2026-09-21** (unit-green; no ROM run — P11). Built as the `assignments/C7/` brief, on
the operator's instruction to complete it. What shipped:

- **Freeze** — `playtest/hand_freeze.py` (`write` / `check`), `reference/frozen/hand_beats_ch01-ch05.json`:
  111 registered own beats, git blob provenance, refuses a dirty module or unknown row. **Deviation from
  the brief:** a chapter's beats claim rows a *predecessor's* manifest owns (16 rows: CH02→map032,
  CH05→map035…), so a row is known if any manifest CH01..this chapter carries it.
- **Residue ledger** — `reference/frozen/hand_beats_residue.json`, enforced by `check` through the
  table-driven `validate_residue`. 27 entries: 7 covered_elsewhere, 4 blocked_obstacle, 4 arrival_floor,
  3 bgm_debt, 2 state_model, 1 retired, 1 build_check, **6 open** (CH01:B1, CH02:B4, CH02:B17, CH03:N4,
  CH04:B7, CH04:B15 — questions in the ledger). CH03:N1 is `covered_elsewhere`, not `state_model`
  (its event has one page).
- **`blocked_obstacle`** — `beat_floor/obstacle.py`; the head appears on trunk *and* arms, so
  `floor_for_map` calls it once per page over the concatenated scope commands. `scripts/check_blocked_obstacles.py`:
  0 mismatches; unmatched `blocked:` rows are p1/p2 follow-ups, behind-obstacle NPCs, and `surf` (no head modelled).
- Not run: the whole suite (#111) — only `test_hand_freeze*` and `tests/test_beat_floor_*` (all green).

**C5b landed 2026-09-18** (unit-green; no ROM run — P11). Suite **3891 passed / 16 skipped**
(two halves, #111). What actually shipped, where it differs from the plan, and what it found:

- **Engine** (commit "C5b engine"): as scoped, with two deviations from §0's letter.
  `struct WarpEvent` is **12 bytes, not 10** — modern builds with `-mabi=apcs-gnu`, which rounds
  struct sizes to 4; the pad is explicit and the `STATIC_ASSERT` caught it on the first build.
  `ScrCmd_warp` **keeps vanilla's Reset and carries only the direction** (its own facing, or a
  pending `SetWarpArrivalFacing` one) rather than calling `StoreInitialPlayerAvatarState`, so a
  script warp still drops bike/surf state exactly as vanilla. The departure override lives in
  `SetupWarp`, which every Store→SetupWarp path (step-on, arrow, door) shares.
- **Pipeline:** `metadata_wiring.warp_facing_for` writes `"facing"` on every source warp_event
  (arrival-only warp_events stay `0`); `deterministic.warp_lines` emits the special pair for
  explicit script-warp directions, used by the transpiler and the simple-warp classifier. The
  RMXP 2/4/6/8 → `DIR_*` table now has one home, `deterministic.RMXP_DIRECTION_TO_DIR_CONST`
  (the transpiler had its own copy). `render_map_scripts` lost its `facings` parameter.
  `fork_index` pins 625 specials.
- **Floor:** `warp` gains `arrives_on_door`, read from the build's `warp_overrides.gen.json`
  (exactly the cells the assembler stamps `MB_NON_ANIMATED_DOOR`). `ExtractContext.door_cells`
  carries it; `floor_for_map` requires `door_cells=` and `_extract_warp` raises without it.
- **Playtest:** `assertions.facing_for_direction` (explicit wins, else approach),
  `arrival_landing_cell` (door → one step on), and `expected_arrival_facing(src_map, src_cell,
  approach)` re-keyed on the departure warp. The `warp` template now asserts the landing cell,
  not the raw arrival, on its forward leg. **Its reciprocal leg does not** (no floor for the
  unclaimed row) — a reciprocal landing on a door tile will fail that exact check in-ROM.
- **Invariants** (`tests/test_warp_facing_invariant.py`, rewritten): arrival facings are
  enumerated per *reachable* approach — a `traversal.graph` flood from every way into a map,
  warp cells as barriers, door landings seeded to a fixed point. The R5 guard is green: every
  door-tile arrival's exit step lands on walkable non-warp ground for every approach, and no
  arrival lands on an arrow or stair tile. **All three entries of the deleted
  `warp_facing_overrides.json` now follow from the source data** (Route 1 → Moki east, both
  cave arrivals north) — pinned by `test_former_hand_overrides_now_follow_from_retain`. The
  first draft, using plain passability, flagged exactly those three as hazards: one-tile pockets
  behind cave mouths and the strip behind the Route 1 warp column are open but unreachable.
- **Re-sourced chapter facing checks** resolve offline against the staged build: ch03 B27/B28/
  B30/B32 (Route 1 seam, Mart, Center, Boutique) → **UP**, ch01 `B3_up` → **RIGHT** (dir 0, stairs pressed right).
  First in-ROM confirmation at P11.

**C8 shape (operator, 2026-09-23).** Measured first: **21 distinct rows / 85 refusal entries**
blocked on embedded Ruby (floor rows CH01 59 / CH02 4 / CH03 15 / CH04 7 / CH05 0; story_state
`unparsed_state_write` sites 21 / 2 / 2 / 3 / 0). "Shared (§4.3)" means CLAUDE.md §4.3: today
five independent regex readers parse embedded Ruby (`story_state/extract.py`, `transpiler.py`'s
`_RubyLocal`/array/argmax, `beat_floor/script.py`, `beat_floor/condition.py`,
`chapter_manifest/conditions.py`; `census._script_head` counts heads only). Rulings:
(a) **New package `ruby_subset/`** — tokenizer, small AST, evaluator over `story_state`'s value
sets. `story_state` and `beat_floor/script.py` move onto it now; the transpiler moves only its
`_RubyLocal`/array/argmax path (the `map050/ev019` idiom). The two 111-condition readers stay
until something they refuse needs it (R13). (b) **Engine-held unlock attributes become
`EngineKey`s** — `$PokemonGlobal.runningShoes` / `$Trainer.pokedex` / `$Trainer.pokegear`
(native `FLAG_SYS_B_DASH` / `FLAG_SYS_POKEDEX_GET` / `FLAG_SYS_POKENAV_GET`), asserted by the
floor and checked by `engine-audit`; `$game_map.need_refresh` is visual-only. **Party and dex
quantities** (`$Trainer.party…`, `pokedexSeen`/`pokedexOwned`) are **not** modelled: they refuse
under one named blocker **`party_model`**, which also absorbs the existing `unmodelled` party
families in `conditions.py`; option "bounded input + `set_party` harness" or a real party model
is a later step, taken by the first chapter that needs those rows green. (c) **Input search is
exhaustive with a fail-loud cap** (4096 input combinations); main path takes the first outcome
in source order, the rest become arm rows (R10). (d) **Every script-head extractor parses the
whole statement through the interpreter.** Found while measuring:
`x=pbGet(151).index(pbGet(151).max)` passes the C4 floor refusal-free because head-only matching
reads it as a bare `pbGet` getter — a silent false negative. Refusal counts may rise before they
fall. (e) **Content fidelity:** `system("start http://…")` and `$lobbyreset` (online lobby) go on
the strip list; `jvGiveReward` gets its own extractor that reads `PROFREWARDS` from source rather
than interpreting Uranium's script library. **To verify before building:** Bambo's
`index(max)` yields 0..2 while `map050/ev019` compares var 151 against 1..3. *(Verified same day:
Bambo's `map050/ev005/p0/b2` runs the argmax, a `{1↔0}` remap, then a code 122 `var151 += 1` at list 127, so var
151 ∈ {1,2,3}. The input is four inline `\ch[2,0,…]` text choices of three options each — an
Essentials text escape, not a 102 — so 81 combinations. `story_state` does not model `\ch` today;
the transpiler parses it (`transpiler.py:670`). `pbStarterSelector` is presentation only.)*

**C8 design (lead, 2026-09-23; operator: build agent implements).** Stages, one commit each:
(1) `ruby_subset/{lexer,ast,parser}.py` — parses every 355/655 block and 111-type-12 script in
CH01–CH05, pinned by a real-corpus test; out-of-subset syntax raises a named `RubyParseError`.
(2) `ruby_subset/evaluate.py` — **concrete** execution (not abstract set arithmetic, which arrays
and `index(max)` don't survive) over one assignment of inputs; builtins by table (`pbGet`,
`pbSet`, `pbSetSelfSwitch`, `$game_switches`/`$game_variables`, `Array#index/max/[]/[]=`);
unknown call → named refusal; `$Trainer.party…`/dex counts → `party_model`; unlock attributes →
`EngineKey` writes. (3) **Page-level input search** — runs the page's command sequence (text
`\ch`, 102/402, 355/655, 121/122/123, 111) over the product of input domains and read-key value
sets, capped at 4096; output = written value sets plus a **witness** (input vector) per outcome.
(4) `story_state/extract.py` writes move onto it; the report JSON gains `witnesses`. (5)
`beat_floor/script.py` parses whole statements. (6) the transpiler's `_RubyLocal`/array/argmax
path.

*Stages 3–4 refined (lead, same day), after reading `model.py`.* The unit of evaluation is a
**row scope**, meaning the row's own flattened command list (`_flatten_scope`, the same one
extraction uses), not one script block. Bambo's `b2` has four `\ch` writes to var 2 and five
script blocks that must run in order within one execution. Stage 3's `ruby_subset/search.py`
runs a scope concretely. It handles text `\ch` (via a pure `parse_inline_choice` lifted out of
`transpiler._emit_inline_choice`, §4.3), 121/122/123, 355/655 and 117 (a strip-listed CE is a
no-op). Nested arm scopes are skipped, since they are their own rows. Out-of-scope reads come
from a `read_domain(key)` callback, and the product of reads and inputs is capped at 4096. The
output is the per-key value sets, the effects, and the first witness per `(key, value)` in DFS
order. `ev019/p0`'s switch 59/60/61 writes (trunk; `b1` holds the three `pbAddPokemon`
grants — corrected by stage 3) depend on var 151, which Bambo writes, so they
**cannot resolve at extraction time**. Stage 4 therefore adds a **resolver fixpoint around
saturation**. A script-bearing row whose run reads out-of-scope state or input becomes
*computed*. Its writes are evaluated against the previous iteration's saturated value sets
(sound, since saturation is already a flow-insensitive union). The resolver starts from the seed
and repeats until the writes stop changing, which terminates because the value sets only grow
and are capped. A computed row that reads a TOP value refuses by name. A row whose run reads
nothing folds to static `Assign`s at extraction, exactly as today, so `beat_floor` is unaffected
for it.

(7) `jvGiveReward`/`PROFREWARDS` extractor, `engine-audit` `FLAG_SYS_*`, and two
corrections found the same day: **CEs 4/5/6 (GTS/VT/LOBBY) are already in `strip_list.json`**
with a stub message — the `$lobbyreset`/`system(...)` refusals exist only because
`story_state`/`beat_floor` inline code 117 without honoring common-event strips, so the fix is
there, not a new strip entry (ruling (e) is satisfied by the existing entries); and **the
`for i in $Trainer.party / i.nuzlocke_heal / end` loop is not `party_model`** — `nuzlocke_heal`
is the original `heal` aliased under Uranium's Nuzlocke override (`220_Custom_Mode.rb:212-223`),
always followed by a code 314 Recover All (`transpiler.py:516`), so with no Nuzlocke mode in the
port it is a builtin no-op. `static_predicates` (`$PokemonGlobal.randomizer = false`) still has
no consumer anywhere in `src/` — noted, not C8's.

*Stage 7 re-scoped to three tasks (2026-09-23), after measuring each item above.* Two of the
four things item (7) lists are already closed: the **`nuzlocke_heal` correction landed in stage
4** (`evaluate.py::_is_nuzlocke_party_loop` matches the loop structurally and emits a no-op
effect), and **`story_state`'s half of the 117 strip-honoring landed there too** — only
`beat_floor`'s half is outstanding. Two further measured corrections to the text above: the
`jvGiveReward` extractor **already exists** (`beat_floor/script.py:397` and
`condition.py:189`), as a deliberate `non_literal_args` refusal, so the work is to *replace* it,
not add one; and the refusal's stated reason is wrong in an instructive way — `jvGiveReward`
reads only `$game_variables[22]` and switches 59/60/61, all modelled, while it is
**`jvNextReward`** that reads `$Trainer.pokedexOwned` and must keep refusing `party_model`
(`reference/scripts_dump/213_Bambo_Reward.rb`). Strip-honoring's blast radius is smaller than it
looks: 36 code-117 calls to CEs 4/5/6 corpus-wide across 11 maps, but only **3 in staged
chapters**, all on `Map068` (CH03) at `ev009`/`ev011`/`ev013` page 0 `list[0]`. Written up as
`assignments/C8/` (three tasks: the reward ladder, `beat_floor` strip-honoring, and surfacing
the `FLAG_SYS_*` fork check inside `engine-audit`, where it is currently only a standalone
pytest grep of `flags.h` that bypasses `fork_index`).

**C8 stage 4 landed (2026-09-23).** `story_state` extraction now runs the interpreter, and the
resolver fixpoint runs around saturation. New `story_state/scope_search.py` (`ComputedScope`,
`run_scope`, `scope_needs_interpreter`, `writes_from_result`, `witness_citations`,
`named_write_targets`); `extract.py` routes any scope carrying a 355 or an inline `\ch` through
`search_scope` **as a whole** and the five regex readers plus `_STATE_WRITE_SMELL_RE` are
deleted; `model.py` gains `resolve_computed_rows`/`_resolve_computed_row`, and `RowVerdict`
gains `witnesses` (in the report JSON — 40 CH01 rows carry one). `search_scope` grew
`write_index` (the last position per key, so a resolved write can carry `Assign.list_index`) and
an optional `index_of` (the flattened scope's offsets are not the owning page's list indices).

`unparsed_state_write` **21 / 2 / 2 / 13 / 0 → 7 / 0 / 0 / 0 / 0**; the surviving 7 are computed
CH01 rows that never become live, so the placeholder is never resolved. Live refusals now:
CH01 `party_model` 68, `search_nonscalar_value` 19, `computed_row_self_reference` 11;
CH03 `party_model` 4, `computed_row_self_reference` 1; CH02/CH04/CH05 none of these.
Ruling (b) landed as a side effect (`EngineKey('pokedex')` is a resolved write), and so did
correction 1: `story_state` honours `stripped_ce_ids` on 117, which suppresses CH03's three
GTS/VT/LOBBY `no_port`/`$lobbyreset` refusals at source. Suite **4282 passed / 16 skipped**
(two halves), engine audit OK.

Five findings worth keeping, each a real defect the work exposed:

1. **The fixpoint oscillated, it did not diverge.** Widening a counter to TOP makes the next
   pass refuse on *reading* that TOP, which drops the havoc, which lets it resolve again. A
   refusal is the top of this lattice: `resolve_computed_rows` now treats a row that resolves to
   a refusal as **settled** and never re-runs it. `MAX_RESOLVER_PASSES = 8` is a fail-loud bound,
   not the mechanism.
2. **A key a row both reads and writes is a counter** (`map050/ev019/p0`'s `Variable(101)`) and
   has no enumerable value set — re-running it against a flow-insensitive union feeds its own
   previous values back and the set grows by one per pass until the blowup guard. The whole row
   widens (`computed_row_self_reference`), which is exactly the standing it had before C8.
3. **The interpreter's refusals must be SOFT.** Landing them in the hard bucket excluded rows
   from saturation outright — FIX 2a's original starvation bug, re-introduced. Every write-level
   interpreter code is soft; only its structural failures (`search_ce_cycle`,
   `search_missing_common_event`, `search_malformed_write`) stay hard.
4. **A refusing search reports no keys, so FIX 2b's per-key havoc was silently lost** (every
   refusal became `havoc_global`, quietly changing row statuses). Restored by
   `named_write_targets`, which names write targets from the **AST** rather than by regex.
5. **`builtins.py`'s vocabulary was scanned from the chapter maps, never INTRO's `Map051`.** A
   refusal aborts the whole scope, so one undeclared `$PokemonGlobal.runToggle` discarded the
   script block that also sets switch 52 — `FLAG_MUM`'s Intro seed vanished and the engine audit
   caught it. Declared with citations, plus `pbChangePlayer`/`pbEventScreen`/`pbShowPokemon`/
   `pbDisposePokemon`/`pbGenderSelector`; a `_parse_body` gap on a brace-block's closing `}` was
   fixed the same way (the brace-block path had never met real data). **The lesson generalises:
   a table built by scanning "the corpus" is only as complete as the maps that scan covered.**

Two calls made here that a later step may overturn: `party_model` and `search_nonscalar_value`
map to the **`story-state`** blocker in `beat_gen/select.py` rather than earning a new `Blocker`
literal (ruling (b) names `party_model` a blocker, but the literal set is C6's contract and
`plan.py`'s `Blocker` is unchanged); and `search_nonscalar_value` is a genuinely new refusal —
a variable holding a species name (`'Eletux'`), which `state.Assign.values` (`bool | int`)
cannot carry.

**C8 stage 6 landed (2026-09-23).** The transpiler's `_RubyLocal`/array/argmax path now reads
through `ruby_subset`. New `conversion_agent/ruby_idioms.py`: twelve pure matchers over a parsed
statement (`match_local_from_var`, `match_local_addsub`, `match_local_wrap`,
`match_array_literal`, `match_array_bump`, `match_array_argmax`, `match_remap_arm_open`,
`match_local_const_assign`, `is_block_end`, `match_var_from_local`, `match_string_list`,
`match_var_from_list_index`), replacing thirteen anchored regexes now deleted from
`transpiler.py`. **The module recognizes; it does not emit** — every emitter
(`_emit_argmax`'s `>=` chain, the scratch-var allocation, `_emit_local_materialize`) stays put,
so this is a swap of the reader only. `_emit_array_literal` now takes parsed `values` instead of
a raw body string.

**Gate: transpiler output byte-identical** across all 19 staged maps plus `CommonEvents.pory`
*and* the queue JSON, before vs after. That was the point of the stage's shape — it is why the
two widenings the AST now makes available were both deliberately declined (see the module
docstring). Suite **4320 passed / 16 skipped** (two halves). *(Corrected 2026-09-23: the entry
first said 4282, the number measured before that same commit's 38 new `ruby_idioms` tests were
added. No behaviour changed — the count was written down early.)*

Three things worth keeping:

1. **The idiom is smaller than it looks and entirely on two maps.** Census of all 664 script
   rows in the staged corpus: 3 `x=pbGet(N)`, 1 `x-=2`, 2 postfix wraps, 1 array literal, 4
   indexed bumps, 1 argmax, 2 remap arms, 2 arm bodies, 2 write-backs, 1 string list, 1 indexed
   readback — every one of them on `map050` or `map032`. The gate therefore covers 100% of the
   affected sites, not a sample.
2. **Widening `pbGet(N)` to also accept `$game_variables[N]` is measurably a no-op** (same 8
   rows matched either way, all 664 rows scanned). Declined anyway: the narrow miss queues the
   row where a human sees it (§4.5), where the wide form would quietly handle an unmeasured
   shape.
3. **The `if x==A / x=B / elsif / end` remap chain is still matched one row at a time.** RMXP
   delivers it as separate 655 rows and `_merge_script_call_rows` deliberately refuses to fuse
   them (they are complete statements, not wrap fragments), so parsing the chain as one `ast.If`
   would mean buffering rows across a page and flushing unterminated ones — a larger change than
   this stage bought. The opener row is normalized into a parseable statement instead (`elsif`
   → `if`, append `end`); the two-line normalization is in `match_remap_arm_open`.

### 16.4 Known work the generator will refuse until fixed (not decisions)

- **#109** — `text_source` rejects the straight quote staging converts; corpus-wide the text
  oracle reads **877 of 946** flavour rows. Extend the fix to `*` and `[` (51 `"`, 12 `*`/`[`;
  `assembly._CHARMAP_SUBS` already substitutes them at staging — reuse it, §4.3).
- **`^` in `map207/ev011/p0`** — no staging substitution exists, so this may be a real ROM
  text defect, not an oracle gap. Check before assuming either.
- **5 untranslatable control codes** in flavour dialogue (e.g. `map052/ev003/p1`).
- **#110** — five toggling instances with no page at `page_idx + 1`; under R6 the toggled page
  comes from the state model, not an index default, so this should dissolve rather than need a
  parameter.
- **`map033/ev024/p0`** — `pbCaveExit` with 3 `# UNHANDLED`; a transpiler gap (§13.3 T11/X3),
  then an ordinary `warp` beat.

### 16.5 What this retires

- **P8a-2** (template re-authoring) — subsumed by C5/C9.
- **§15.3's residue posture** — no hand residue; rows are generated, refused with a blocker, or
  carry a derived verdict.
- **`DEFERRED_BEATS`** — a deferral becomes a derived `later:CHnn`.
- **The 2026-09-14 `archetype_conformance` options** — never recorded, and overtaken.
