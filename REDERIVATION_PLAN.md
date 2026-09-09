# Re-derivation plan — CH01–CH04

**Opened 2026-09-09.** Tracking document for `PROJECT_TODO.md` **#65** (manifests +
dispositions) and **#67** (route plans), executed under **#62**'s ordering safeguard.

> **Status document for this task only.** `MEMORY.md` → Current Phase remains the sole
> authority on the project frontier (`CLAUDE.md` §7). This file owns the step list and its
> state; when the task closes, its durable conclusions go to `MEMORY.md` / `PROJECT_TODO.md`
> and this file is archived.

**Live status (2026-09-09): P1 and P2 DONE. P6 census done; its table change is the next task. Nothing derived yet.**

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
| **P3** | **Encode boundary ownership.** "A boundary crossing belongs to the chapter being opened, not the one shipping" (operator, 2026-09-04) exists in no code and not in `BUILD_PLAN.md`. `build_beat_model` loads a chapter's own module plus predecessors, **never successors**, so a boundary row claimed by the arriving chapter cannot satisfy the shipping chapter's disposition — CH04 permanently reports `unregistered_beat` for `beat:B8`. All four chapters have a forward boundary and all four answers freeze at once. | #72, #73 | TODO |
| **P4** | **Fix ROUTE-before-object-events ordering** (`#74`) and **make `destination_scripts` per-segment** (`#76`). A trainer's own sight cone is still a foreign hazard on the segment walking to it. Required now that route plans are in scope; same root cause as P1. | #74, #76 | TODO |

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
| **P2b** | **The seam-crossing counterpart to P2.** `slice_growth` covers `code 201` only. Map-connection seams (`connections.json`, `tileset_converter/connections.py`) went live the same way and are invisible to it — CH03's B25 is the known instance. Enumerate, per gated chapter, every connection edge that became crossable after that chapter was authored. | new (from P2) | TODO |

### Phase B — resolvers and data

| # | Step | Item | Status |
|---|---|---|---|
| **P5** | **Three new `cells.py` resolvers**, surfaced by the literal inventory (§5): a grass-cell resolver (4 literals), a seam/connection-edge resolver (2 — these are map connections, not `code 201` warps, so `warp_cell`/`arrival_cell` don't apply), and a local-id-keyed lookup for the ch03 boulders (3 — `event_cell` keys on RMXP event id, not the compiled local id). Without these, 9 literals can only land as counted `raw_cell(..., why=)` debt. | new | TODO |
| **P6** | **Derive the CH01–CH03 start cells** — `_CHAPTER_MAP_START_CELLS` (`chapter_manifest/generator.py:243`) holds 4 entries (CH04:35, CH05:35/36/37). Needed: **CH01 8 maps** (49, 48, 32, 50, 64, 65, 172, 89), **CH02 2** (33, 81), **CH03 5** (31, 67, 68, 73, 19) = **15**. A missing entry does **not** fail — it warns, and the manifest is capability-blind on that map (`generator.py:266-279`): terrain-gated capabilities cannot appear in `requires[]` for any row. Re-deriving without this yields manifests that load clean, check green, and are blind on all 15 maps — and the freeze would encode the blindness. **This is the bulk of the work and a prerequisite, not a step.** | A1 (inside #65) | census DONE, entries TODO |

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
| **P6a** | Change the table's value type to `frozenset[Cell]`; union the floods in `_build_reachability_context`; migrate the 4 existing entries. | A1 | TODO |
| **P6b** | Register the 9 evidence-backed entries, each citing its source (warp geometry, or the specific beat whose `_assert_near` verified it). | A1 | TODO |
| **P6c** | Boot-walk CH01 to observe its 6 arrival cells. Needs a ROM run. | A1 | TODO |

### Phase C — the derivation (branch `rederive-ch01-ch04`)

| # | Step | Item | Status |
|---|---|---|---|
| **P7** | **Freeze.** Write the expected answers for all four chapters from their committed, gate-passed artifacts *before* generating anything. Per #62, verbatim: *freeze the expected answers, derive, diff, then write — never derive-and-write in one pass, or a regression in the derivation logic reads as a correct re-disposition.* Precedent for the format: `reference/frozen/archetype_expectations.json`. | #62 | TODO |
| **P8** | **Derive, diff, adjudicate** — manifests + dispositions for CH01–CH04, one chapter at a time, diffed against P7's freeze. Every diff line classified 1/2/3 per §1. Category-3 lines stop the pass. | #65 | TODO |
| **P9** | **Route plans** for all four chapters (`routing plan --chapter CHnn --module <mod>`), and re-author beats adopting `entry_at`. Pay down the coordinate literals to zero (§5). | #67 | TODO |
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
- **Give `map035/ev001/p1` an owner** — CH05's B1 doesn't exercise CH04's arrival-nudge
  autorun on the Route 2 side (`d390e59f`'s admitted residual).
- **Know that `resolved_trigger_scripts` approximates "resolved" as "the beat passed"**
  (`a460e823`) — holds for latching shapes, not for a TEMP-switch page that re-arms on map
  re-entry. Documented, not fixed. Relevant before trusting the oracle across four chapters.
- **Re-verify `reference/frozen/archetype_expectations.json`** rather than assuming it
  passes: it was written from CH04's dispositions *before* the classifier existed.
- **Fix CH03's B25 description string**, which still says the north edge leads to "unbuilt"
  Route 2. Reconciled 2026-08-26; the prose never caught up.

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

## 7. Log

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
