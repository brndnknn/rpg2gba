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
| **P8b** | **Generate the disposition files** — derive `cosmetic`/`blocked`/`unreachable`/`boundary`, join `beat:` off P8a-1's `rows=` (which now exist), hand-decide the ~109-row residue (§13.1). Affirmation is a separate pass from derivation. Carries §10 R2/R3's flip on CH04+CH05. | #65 | TODO |
| **P9** | **Route plans** for all four chapters (`routing plan --chapter CHnn --module <mod>`). Still last: `routing locations` hard-fails without P8b's output. | #67 | TODO |
| **P10** | **Discharge the inherited obligations** (§4) and delete the scaffolding that expires with this task. | — | TODO |

### Phase D — gates

| # | Step | Status |
|---|---|---|
| **P11** | **§9 boot gate, ×4.** Each re-derived chapter must boot in mGBA and be genuinely playable before the branch merges. This is an operator gate — I do not pass it on my own say-so (`CLAUDE.md` §9). The seeding recipe is `playtest walk --chapter <this> --at-beat <first> --engine engine`; predecessor `--at-end` blobs are keyed to the ROM's sha256 and any rebuild invalidates them (#85). | TODO |
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
