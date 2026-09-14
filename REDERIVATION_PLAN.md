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
| **P8a-2** | **Re-author those beats onto the archetype templates**, adopting `entry_at`, paying the coordinate literals down to zero (§5). Now a code-quality and assertion-strength step, not a P8b prerequisite. Needs the §13.3 templates; #94 (registry) is DONE 2026-09-10 (`c91f70d3`) and no longer gates it. **Read §5's warning first: some literals are load-bearing ROM-verified truth, and the AST ratchet counts literals without ever asking whether one is still true.** | #67, §13 | TODO |
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
