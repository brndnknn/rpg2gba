# C6 Task 2 (group) — measured data

**Dated 2026-09-21.** Measured data for the operator to design and implement
`beat_gen/group.py` against — **not a solution, not a recommendation.** Every number below
came from throwaway scripts under `/tmp/c6research/` (`group1.py`..`group4.py`, `group2b.py`)
against the cached `/tmp/c6research/data.pkl` (CH01–CH05 `rows`/`verdicts`/`floors`), run once.
No dialogue or story content is quoted; row ids and trainer/item constants only.

**On the "owned" set used below (items 3, 7):** Task 1 (`select.py`) is not implemented yet.
Everywhere this doc says "approximate owned set," it is the scratch bucket simulation in
`/tmp/c6research/verify_buckets.py` (reused verbatim, extended to log each row's bucket),
**not** Task 1's real output. Treat every count that depends on it as a sanity check, not a
pinned fact — Task 1's actual rule table may bucket some of these rows differently once
written.

---

## 1. Row ids, nesting, `owning_page`

### 1a — `parse_row_id` fields (`schema.py:887-923`)

`ParsedRowId(kind, map_id, event_id, page_idx, arm_index, direction, other_map_id, subkind,
x, y)`. Only the fields meaningful for `kind` are populated; the rest are `None`. Two derived
properties: `owning_page_row_id` (page id for `page`/`branch`, `None` for `seam`/`terrain`) and
`event_key` (`(map_id, event_id)`, same restriction).

Demo (`group1.py`):

| row_id | kind | owning_page_row_id |
|---|---|---|
| `map001/ev002/p0` | page | `map001/ev002/p0` |
| `map050/ev005/p5/b4` | branch | `map050/ev005/p5` |
| `map035/seam/N/map040` | seam | `None` |
| `map037/terrain/stairs/11,9` | terrain | `None` |

### 1b — Branch-id grammar is flat regardless of nesting depth (`branch_row_id`, `schema.py:797-802`)

> "always suffixed onto its PAGE row id, flat, regardless of nesting depth... `map050/ev005/p0/b2`,
> never `.../b0/b2`. Nesting is carried by `ManifestRow.parent_row_id`, not by the id string."

**Measured consequence, confirmed over all 5 chapters (`group1.py`):** for every branch row in
CH01–CH05, `parse_row_id(row.row_id).owning_page_row_id` — computed from the id string alone,
zero hops — is **identical** to the page reached by walking `parent_row_id` until a `page` row
is hit. No mismatch in 488 branch rows checked (247+88+91+44+18). This is exactly the task
hint's "One of those is a single line": the parent-walk is never actually necessary to answer
`owning_page` correctly on real data, because the id grammar already encodes it flat.

### 1c — Depth distribution (hops from arm to its page via `parent_row_id`)

| Chapter | branch rows | depth 1 (parent=page) | depth 2 | depth 3 | depth 4 | direct-parent-is-arm | direct-parent-is-page |
|---|---|---|---|---|---|---|---|
| CH01 | 247 | 170 | 29 | 38 | 10 | 77 | 170 |
| CH02 | 88 | 82 | 6 | 0 | 0 | 6 | 82 |
| CH03 | 91 | 81 | 10 | 0 | 0 | 10 | 81 |
| CH04 | 44 | 40 | 4 | 0 | 0 | 4 | 40 |
| CH05 | 18 | 18 | 0 | 0 | 0 | 0 | 18 |

Sums reconcile: depth columns sum to branch-row count in every row; `direct-parent-is-arm +
direct-parent-is-page` also sums to branch-row count (every branch row's direct parent is either
a page or another branch, no third case observed).

**`parent_row_id` does point at another arm** (nesting), confirmed in 4 of 5 chapters. Examples
(`group1.py`):

- CH01: `map032/ev014/p0/b2` → parent `map032/ev014/p0/b1`; `map032/ev014/p0/b3` → same parent
  (two siblings nested one level under `b1`). 77 such rows total.
- CH02: `map033/ev039/p1/b1` → parent `map033/ev039/p1/b0`. 6 total.
- CH03: `map019/ev006/p0/b1`/`b2` → parent `.../b0`; `.../b4`/`b5` → parent `.../b3` (two
  separate nesting sites on the same page). 10 total.
- CH04: `map035/ev003/p1/b1`/`b2` → parent `.../p1/b0`. 4 total.
- CH05: none — every CH05 arm is a direct child of its page.

CH05's own manifest is the simplest case in the corpus for this question: zero nesting, so
`owning_page`'s nested-arm behavior is untested by real CH05 data and rests entirely on the
synthetic test (`test_owning_page_of_a_nested_arm`) plus §1b's cross-chapter confirmation.

---

## 2. Stairs

### 2a — Every terrain row, CH02/CH03/CH05, full `TerrainRef` (`group2.py`)

| row_id | map | x,y | behavior | source_event_id |
|---|---|---|---|---|
| `map033/terrain/stairs/52,41` | 33 | 52,41 | `MB_SIDEWAYS_STAIRS_RIGHT_SIDE` | 69 |
| `map033/terrain/stairs/52,42` | 33 | 52,42 | `MB_SIDEWAYS_STAIRS_RIGHT_SIDE` | 66 |
| `map033/terrain/stairs/53,43` | 33 | 53,43 | `MB_SIDEWAYS_STAIRS_RIGHT_SIDE` | 48 |
| `map033/terrain/stairs/53,44` | 33 | 53,44 | `MB_SIDEWAYS_STAIRS_RIGHT_SIDE` | 47 |
| `map033/terrain/stairs/57,9`  | 33 | 57,9  | `MB_SIDEWAYS_STAIRS_RIGHT_SIDE` | 33 |
| `map033/terrain/stairs/57,10` | 33 | 57,10 | `MB_SIDEWAYS_STAIRS_RIGHT_SIDE` | 31 |
| `map033/terrain/stairs/57,11` | 33 | 57,11 | `MB_SIDEWAYS_STAIRS_RIGHT_SIDE` | 26 |
| `map031/terrain/stairs/25,16` | 31 | 25,16 | `MB_SIDEWAYS_STAIRS_RIGHT_SIDE` | 27 |
| `map031/terrain/stairs/25,17` | 31 | 25,17 | `MB_SIDEWAYS_STAIRS_RIGHT_SIDE` | 26 |
| `map031/terrain/stairs/25,18` | 31 | 25,18 | `MB_SIDEWAYS_STAIRS_RIGHT_SIDE` | 24 |
| `map037/terrain/stairs/11,9`  | 37 | 11,9  | `MB_SIDEWAYS_STAIRS_LEFT_SIDE`  | 8 |
| `map037/terrain/stairs/11,10` | 37 | 11,10 | `MB_SIDEWAYS_STAIRS_LEFT_SIDE`  | 7 |
| `map037/terrain/stairs/20,9`  | 37 | 20,9  | `MB_SIDEWAYS_STAIRS_RIGHT_SIDE` | 6 |
| `map037/terrain/stairs/20,10` | 37 | 20,10 | `MB_SIDEWAYS_STAIRS_RIGHT_SIDE` | 3 |

Every row's `source_event_id` is distinct within its chapter — confirms the README's "every stair
cell is its own RMXP event" for CH02/CH03 too, not just CH05.

### 2b — CH05's hand module (`playtest/chapters/ch05.py:604-666`), what the two cells of one staircase share

`ch05.py` registers two staircase beats: `B14` (east) claims `("map037/terrain/stairs/20,9",
"map037/terrain/stairs/20,10")`, `B13` (west) claims `("map037/terrain/stairs/11,9",
"map037/terrain/stairs/11,10")`. Each beat's `stair_approach(MAP_2F, stair_event=<N>, side=...)`
call uses **one of the two cells' `source_event_id`** as `stair_event` (B14: `stair_event=6`,
matching `20,9`'s source event; B13: `stair_event=8`, matching `11,9`'s source event) — the
*other* cell's event id (`3` for the east pair, `7` for the west pair) is never referenced by
`ch05.py` at all.

What the two cells of one hand staircase **share**: `map_id` (37 both), `behavior` (identical
string), and are orthogonally adjacent (`x` equal, `y` differs by 1). What they **do not share**:
`source_event_id` (always different — confirmed above, every cell has its own event) and the
literal row_id obviously.

### 2c — Candidate grouping keys, counts per chapter vs. hand-authored counts

**Candidate A — group by `source_event_id`.** Every group is size 1 (confirmed for all three
chapters: CH02 7 groups, CH03 3 groups, CH05 4 groups, all singletons). This is the task hint's
"obvious key gives four one-cell staircases" — reproduced exactly for CH05, and generalizes: it
gives one-cell "staircases" everywhere in the corpus, never matching any hand module.

**Candidate B — group by `(map_id, behavior)`, connected components under 4-directional
(orthogonal) adjacency:**

| Chapter | groups | sizes |
|---|---|---|
| CH02 | 3 | `{52,41;52,42}`=2, `{53,43;53,44}`=2, `{57,9;57,10;57,11}`=3 |
| CH03 | 1 | `{25,16;25,17;25,18}`=3 |
| CH05 | 2 | `{11,9;11,10}`=2, `{20,9;20,10}`=2 |

CH05 matches the hand module exactly (2 groups of 2). CH03 has no hand module to compare against
(see §2d). **CH02 does not match its hand module** — see next.

**Candidate C — group by `(map_id, behavior)`, connected components under 8-directional
(king-move, diagonal-inclusive) adjacency** (`group2b.py`):

| Chapter | groups | sizes |
|---|---|---|
| CH02 | 2 | `{52,41;52,42;53,43;53,44}`=4, `{57,9;57,10;57,11}`=3 |
| CH03 | 1 | `{25,16;25,17;25,18}`=3 (unchanged) |
| CH05 | 2 | `{11,9;11,10}`=2, `{20,9;20,10}`=2 (unchanged) |

**Why B and C diverge on CH02:** the map033 run's raw coordinates, in y-order, step
`(52,41)→(52,42)→(53,43)→(53,44)`. The middle step is `dx=1, dy=1` — a **diagonal** neighbour,
not orthogonal. `ch02.py`'s own comment (`chapters/ch02.py:73-75`) calls this **one** run: "the
rest of the route is the (52,41)-(53,44) staircase" — a single 4-cell staircase, currently
**DEFERRED, not registered** (`chapters/ch02.py:1305`, "every cell of this staircase run"). Under
candidate B (orthogonal-only) this run splits into two 2-cell components that don't touch;
under candidate C (king-move) it is one 4-cell component, matching `ch02.py`'s own prose exactly.
`ch02.py`'s registered `B2` claims the OTHER map033 run — `(57,9),(57,10),(57,11)` — as one
3-row beat (`chapters/ch02.py:1266-1272`), which both candidate B and C agree is a single
3-cell group.

**Net: no adjacent-cell pair in the whole CH01–CH05 corpus has differing `behavior`** (§2e), and
the corpus's one diagonal-linked run (CH02 map033) means an orthogonal-only adjacency key
under-groups relative to what `ch02.py` calls one staircase, while a king-move key reproduces
every hand-authored/hand-described grouping seen in the corpus (CH02's registered `B2`, CH02's
deferred 4-cell comment, CH05's `B13`/`B14`). This is presented as a measured fact, not an
instruction to use king-move adjacency — `ch02.py`'s deferred run is commentary, not a test-pinned
beat, so it is weaker evidence than CH05's registered beats.

### 2d — CH03: no hand module comparison available

*(Lead check, 2026-09-21:)* `playtest/chapters/ch03.py` has no stair beat and no comment about
the map031 (25,16)-(25,18) run (a grep for `terrain`/`stair` finds nothing relevant). Both
adjacency candidates give one 3-cell group, but no hand beat confirms it.

One more fact bearing on the diagonal question: these are `MB_SIDEWAYS_STAIRS_*` tiles, and
the engine moves the player diagonally on and off sideways stairs:
`GetSidewaysStairsCollision` (`engine/src/event_object_movement.c:6686-6723`) returns
`COLLISION_SIDEWAYS_STAIRS_TO_LEFT/RIGHT`, commented "move diagonally". A diagonal step between
two cells of one run is therefore how the engine actually walks these tiles, not an artifact of
the data.

### 2e — Adjacent-pair behaviour-field check (all chapters, `group2.py`)

Every same-map orthogonally-adjacent terrain-row pair in CH02, CH03, CH05 has **identical**
`behavior`. Zero pairs differ. So the test file's `test_adjacent_stairs_with_different_behavior_
are_separate` scenario (two adjacent cells, different `behavior` → separate staircases) is
**synthetic-only** — no real CH01–CH05 data exercises that branch of whatever rule is chosen.

---

## 3. Archetype matches

### 3a — Match counts by archetype, per chapter (`classify_manifest`, `group3.py`)

| Chapter | arrival_nudge | flavour_npc | item_ball | trainer | warp | total |
|---|---|---|---|---|---|---|
| CH01 | 8 | 79 | 0 | 1 | 21 | 109 |
| CH02 | 6 | 3 | 7 | 9 | 7 | 32 |
| CH03 | 10 | 22 | 1 | 4 | 18 | 55 |
| CH04 | 1 | 2 | 3 | 4 | 1 | 11 |
| CH05 | 1 | 0 | 4 | 3 | 4 | 12 |

*(Corrected 2026-09-21 by the lead: the first draft said `flavour_npc` is missing from
`ARCHETYPE_TEMPLATES`. It isn't. `plan.py:35` and `:45` list all five archetypes, including
`flavour_npc`, and `emit.TEMPLATE_CALLS` maps it to `flavour_npc_beat`. All five archetypes that
`classify_manifest` produces are claimable templates. Note that CH05 has 0 `flavour_npc` matches,
so no pinned CH05 test exercises one, while CH01 has 79.)*

### 3b — Role names used, and whether role rows are ever branch rows

All role names seen across CH01–CH05: `battle`, `grant`, `nudge`, `retalk`, `spent`, `talk`,
`warp` (`archetypes.py`'s docstring at `:114-118` names all six of `"battle"`, `"retalk"`,
`"grant"`, `"spent"`, `"warp"`, `"nudge"` — `"talk"` is the seventh, `flavour_npc`'s own role,
added by `_match_flavour_npc`, `:271-278`, not mentioned in that docstring).

**No role row is ever a branch row**, in any chapter. Every `ArchetypeMatch.roles` key observed
is a `kind="page"` row — consistent with `classify_manifest` only ever iterating
`row.kind == "page"` rows into its per-event groups (`archetypes.py:411-415`).

### 3c — Half-owned matches under the approximate owned set

| Chapter | half-owned matches | detail |
|---|---|---|
| CH01 | 1 | `trainer` at (map 50, event 19): **`battle`** role `map050/ev019/p0` missing, bucket `refused:story:unparsed_state_write` |
| CH02 | 1 | `trainer` at (map 33, event 53): `retalk` role `map033/ev053/p1` missing, bucket `refused:undetermined` |
| CH03 | 0 | — |
| CH04 | 1 | `trainer` at (map 35, event 3): `retalk` role `map035/ev003/p1` missing, bucket `refused:undetermined` |
| CH05 | 0 | — |

CH01's case is the odd one out: the missing role is the **battle** page, not a retalk page —
worth noting since the task file's own framing ("a trainer can't be registered without its
retalk page") reads as retalk-specific, but the archetype-match rule as stated ("claims its role
rows only if all of them are owned") is symmetric in every role, and CH01 measures a case where
it's the battle role that's missing.

### 3d — Trainers whose retalk page is not owned (Q3 data), broader than §3c

§3c's "half-owned matches" undercounts this question, because a match only counts as "half-owned"
when at least one role IS owned — a trainer whose battle role is *also* not owned doesn't show up
there (nothing partially claims it; it's fully unowned). Listing every trainer match with an
unowned retalk role regardless of the battle role's status:

| Chapter | trainer (map, event) | unowned retalk row | bucket |
|---|---|---|---|
| CH02 | (33, 9) | `map033/ev009/p1` | `elsewhere:blocked` |
| CH02 | (33, 10) | `map033/ev010/p1` | `elsewhere:blocked` |
| CH02 | (33, 35) | `map033/ev035/p1` | `elsewhere:blocked` |
| CH02 | (33, 39) | `map033/ev039/p1` | `refused:undetermined` |
| CH02 | (33, 39) | `map033/ev039/p2` | `elsewhere:blocked` |
| CH02 | (33, 41) | `map033/ev041/p1` | `elsewhere:blocked` |
| CH02 | (33, 53) | `map033/ev053/p1` | `refused:undetermined` |
| CH03 | (19, 5)  | `map019/ev005/p1` | `elsewhere:blocked` |
| CH03 | (19, 5)  | `map019/ev005/p2` | `elsewhere:blocked` |
| CH03 | (19, 6)  | `map019/ev006/p1` | `elsewhere:blocked` |
| CH04 | (35, 3)  | `map035/ev003/p1` | `refused:undetermined` |
| CH04 | (35, 23) | `map035/ev023/p1` | `refused:undetermined` |
| CH04 | (35, 23) | `map035/ev023/p2` | `elsewhere:blocked` |
| CH04 | (35, 24) | `map035/ev024/p1` | `elsewhere:blocked` |

14 rows total across CH02–CH04; CH01 and CH05 have none. `elsewhere:blocked` dominates (9 of
14) — these are retalk pages gated behind a `requires` capability (rock_smash/strength) the
chapter's own approximate-owned-set simulation marks `elsewhere`, not `refused`.

---

## 4. Arms of archetype pages: what each template claims vs. leaves

Code citations for how each template decides which arms it walks:

| Template | Mechanism | Citation |
|---|---|---|
| `warp` | `walked_arms(row_id, "warp", floor_lookup=...)` | `archetypes/warp.py:352` |
| `arrival_nudge` | `walked_arms(row_id, "displacement", floor_lookup=...)` | `archetypes/arrival_nudge.py:146` |
| `trainer` | own scan, `i in range(8)`, `f"{battle_row_id}/b{i}"`, looks for a `self_switch_write` assertion whose derived flag name matches the caller's `defeat_flag=` | `archetypes/trainer.py:169-199` (`_defeat_write_declaration`) |
| `item_ball` | direct children only (`r.parent_row_id == grant_row_id`, no deeper walk), then picks the one arm `chapter_manifest.conditions.classify_condition` marks `"always"` | `archetypes/item_ball.py:120-185` (`_claim_self_switch_arm`) |

`walked_arms` (`playtest/archetypes/__init__.py:106-129`) is the one shared implementation for
`warp`/`arrival_nudge`: it walks `f"{row_id}/b{index}"` for `index = 0, 1, 2, ...` until
`floor_lookup` raises `KeyError`, claiming every arm whose floor carries an assertion of the
given `kind`. Because branch ids are flat per page (§1b) this walk sees *every* arm of the page
regardless of nesting depth — it does not need to distinguish depth-1 from depth-2 arms.
`trainer` and `item_ball` do NOT use `walked_arms`; each has its own bespoke arm-selection logic
(trainer's own `range(8)` scan; item_ball's direct-children-only filter, which explicitly
**excludes** nested arms — an arm whose `parent_row_id` is another arm would never be considered
by `_claim_self_switch_arm`, unlike `walked_arms`, which does not care about `parent_row_id` at
all).

**Measured counts** (`group4.py`; "total arms" = every branch row whose flat owning page is the
matched archetype page, at any nesting depth; the claim counts approximate what each template's
own logic would select, given the manifest data alone — trainer's real `defeat_flag=` isn't
available from the manifest so its count below is "arms carrying `self_switch_write`," a
superset of what a specific `defeat_flag=` string would actually match):

| Chapter | warp: total arms / `walked_arms("warp")` would claim | arrival_nudge: total / `walked_arms("displacement")` | trainer battle: total arms / carrying `self_switch_write` | item_ball grant: direct-child arms / carrying `self_switch_write` |
|---|---|---|---|---|
| CH01 | 6 / 0 | 16 / 5 | 10 / 0 | 0 / 0 |
| CH02 | 0 / 0 | 12 / 1 | 18 / 9 | 14 / 7 |
| CH03 | 4 / 0 | 20 / 8 | 14 / 4 | 2 / 1 |
| CH04 | 0 / 0 | 2 / 1 | 8 / 4 | 6 / 3 |
| CH05 | 0 / 0 | 2 / 1 | 6 / 3 | 8 / 4 |

`warp` never claims any arm in this corpus (0 of 10 total arms across all chapters carry a
`"warp"`-kind floor assertion) — every matched warp page's arms are something else (item grants,
condition branches unrelated to the crossing itself). This is worth flagging: the generic
`_arms` beat is where **every** arm of a matched `warp` page ends up in this corpus, not a
residue after the template claims some.

### `skip_claimed` / claimed-rows handling in `playtest/chapter.py`

**No public accessor exists yet.** `ChapterBuilder` (`chapter.py:389-396`) stores registered
beats in a single field, `_beats: list[Beat]` — private, no leading-underscore-free property or
method exposing it. `grep` for `def beats`/`@property` in `chapter.py` returns nothing. The
`skip_claimed=True` behavior the task file describes ("rows some earlier beat in `builder`
already claims are dropped first") is **not implemented anywhere today** — `generic_beat` in
`playtest/archetypes/generic.py:68-83` is itself an unimplemented stub (Task 7, not Task 2), and
its docstring is the only place `skip_claimed`'s contract is written down. Whatever `group.py`
emits as `kwargs=make_kwargs(skip_claimed=True)` is a promise to Task 7's future implementation,
not something `group.py` itself can verify by calling into `ChapterBuilder` — Task 2's own tests
only check that the `PlannedBeat.kwargs` carries `("skip_claimed", True)` (`test_beat_gen_group.py:115`), not that any claiming actually happens.

---

## 5. Obstacles

`blocked_obstacle`'s capability param: `assertion.py:41`, `"blocked_obstacle", # params: x, y,
capability ("rock_smash"|"strength")` — read via `a.param("capability")`. (Real data also shows
`"surf"` as a capability value elsewhere in the corpus, per the C6 README's "surf" mentions, but
no CH01–CH05 row's `blocked_obstacle` assertion uses `surf` — see table below; every observed
`blocked_obstacle` row is `rock_smash` or `strength`.)

| Chapter | map | capability | rows | events | spans multiple events? |
|---|---|---|---|---|---|
| CH01 | 32 | `rock_smash` | 3 | 14, 15, 33 | yes |
| CH02 | 33 | `rock_smash` | 6 | 29, 36, 38, 40, 42, 44 | yes |
| CH03 | 19 | `strength` | 3 | 1, 2, 3 | yes |
| CH03 | 31 | `strength` | 2 | 1, 37 | yes |
| CH04 | 35 | `rock_smash` | 5 | 14, 15, 16, 17, 18 | yes |
| CH05 | — | — | 0 | — | — |

**Every group spans multiple events** — no `(map, capability)` group in this corpus is a single
event's obstacle. CH03 is the only chapter with two separate `(map, capability)` groups (both
`strength`, different maps). Total obstacle rows: CH01 3, CH02 6, CH03 5, CH04 5, CH05 0 — sums
match the per-chapter `blocked_obstacle` counts in the Task 1 research doc's §4 table exactly
(3/6/5/5/0).

---

## 6. Seams

Every seam row's full `SeamRef` (`group2.py`):

| row_id | map_id | direction | offset | other_map_id | other_direction | other_offset |
|---|---|---|---|---|---|---|
| `map032/seam/E/map059` | 32 | E | 26 | 59 | W | 0 |
| `map031/seam/N/map035` | 31 | N | 11 | 35 | S | 0 |
| `map035/seam/N/map040` | 35 | N | 0 | 40 | S | 15 |
| `map035/seam/S/map031` | 35 | S | 0 | 31 | N | 11 |

Per chapter: CH01 1, CH02 0, CH03 1, CH04 2, CH05 0 — matches the C6 README's table exactly.
**No duplicate `(map, direction, other)` key** in the corpus — every seam row is unique on that
triple, so the naming rule `m{map:03d}seam{dir}{other:03d}` never collides in CH01–CH05.

Note `map031/seam/N/map035` (CH03) and `map035/seam/S/map031` (CH04) are reciprocals of the same
physical connection, appearing as two separate rows (one per owning chapter's map side) — exactly
per `seam_row_id`'s own docstring (`schema.py:862-869`: "a seam appears once per map it touches").
Their `(map, direction, other)` keys (`(31,"N",35)` vs `(35,"S",31)`) are naturally distinct, so
this doesn't collide either, but it's the corpus's one case where two seam rows describe "the
same edge" and a beat_name reader should not assume seam rows are 1:1 with physical connections.

---

## 7. Orphan arms (owned arm, owning page not owned, approximate owned set)

| Chapter | orphan arms | page bucket |
|---|---|---|
| CH01 | 6 | `map089/ev004/p0`: `refused:floor:text_unnormalizable` (1 arm); `map172/ev004/p0`: `refused:floor:unknown_script_head` (5 arms: b0,b1,b2,b4,b5) |
| CH02 | 0 | — |
| CH03 | 4 | `map031/ev049/p0`: `refused:floor:unknown_script_head` (all 4 arms, b0-b3) |
| CH04 | 0 | — |
| CH05 | 0 | — |

Every orphan-arm case in this corpus has the owning page refused by a **floor** reason (rule 7 in
the Task 1 research doc's vocabulary), never a story-state refusal or an `elsewhere` bucket. Both
examples are `unknown_script_head`/`text_unnormalizable` pages where the page row itself never
got its content classified, but at least one branch arm's *own* floor was independently clean
enough to be bucketed `owned`. This is the task file's "arms of an unowned page get their own
generic `<page-name>_arms` beat" test scenario (`test_arms_of_an_unowned_page_get_their_own_
generic_beat`), now confirmed to occur in real data (10 total instances across CH01/CH03).

---

## 8. The CH05 20-beat pinned plan vs. `ch05.py`

Read directly from the pinned test list (`tests/test_beat_gen_group.py:221-234`) and
`playtest/chapters/ch05.py`, no code run (static citation only):

| Pinned generated beat(s) | `ch05.py` hand beat | Row(s) |
|---|---|---|
| `m036e001_warp` | `B1` (one of B1's three registered calls; only this call's row, `map036/ev001/p0`, is CH05's own manifest row) | `map036/ev001/p0` |
| `m036e002_warp` | `B8` (the lone forward-crossing call) | `map036/ev002/p0` |
| `m036e002_arrival_nudge` + `_arms` | `B8_nudge` | `map036/ev002/p1` |
| `m036e003_item_ball` + `_arms` | `B2` | `map036/ev003/*` |
| `m036e004_trainer` + `_arms` | `B3` (Manny) | `map036/ev004/*` |
| `m036e005_item_ball` + `_arms` | `B4` | `map036/ev005/*` |
| `m036e006_trainer` + `_arms` | `B5` (Keichi) | `map036/ev006/*` |
| `m037e001_warp` | `B8_return` (its own claimed warp-back call) | `map037/ev001/p0` |
| `m037e002_warp` | `B11` (**hand-written despite matching the `warp` archetype fingerprint** — Map040 isn't staged, see `ch05.py`'s own B11 section) | `map037/ev002/p0` |
| `m037e004_trainer` + `_arms` | `B9` (Nunes) | `map037/ev004/*` |
| `m037e005p0` | `B10` | `map037/ev005/p0` |
| `m037e005p1` | `B10_retalk` | `map037/ev005/p1` |
| `m037stair11x9` | `B13` | `map037/terrain/stairs/11,9`, `.../11,10` |
| `m037stair20x9` | `B14` | `map037/terrain/stairs/20,9`, `.../20,10` |

**Hand beats with no counterpart in the pinned 20-beat list:** `B1_nudge` and `B1_in`. Both are
registered with `manifest_chapter_id="CH04"` — they claim rows from *CH04's* manifest
(`map035/ev001/p1` and `map035/ev001/p0`), not CH05's. `select_rows(rows=CH05's own rows, ...)`
only ever sees CH05's manifest, so `sel.owned` for the CH05 real-data test cannot contain those
row ids at all — they're structurally outside what `group.plan_beats` for CH05 is ever asked to
claim. This is a fact about the *test's* scope, not a gap in `group.py`.

**Group structure diverges from the hand module's groups.** `ch05.py` puts `B8_return`,
`B8_nudge`, `B8` in one shared `group="B8"` (deliberately, so the route solver keeps them
contiguous — see the module docstring's "one stop, three beats, three crossings"). But the
pinned generated names show `m037e001_warp` (≈`B8_return`), `m036e002_arrival_nudge`
(≈`B8_nudge`), and `m036e002_warp` (≈`B8`) as **three separate archetype matches**, each a
single-row `ArchetypeMatch` on its own page — under the naming table's rule ("Each beat's group
is its own name, except `_arms` beats"), each gets its **own** `group` value equal to its own
name, not one shared group. Grouping these three back into one route-solver stop (matching
`ch05.py`'s intent) is not something Task 2's per-match claiming rule does on its own — it would
need to happen in a later stage (locate/route), if at all. Presented as a fact for you to weigh,
not a claim about what's correct.

**Order**: the pinned list follows manifest position (page_idx within an event, event order
within a map, map order) — e.g. `m036e002_warp` (page 0) before `m036e002_arrival_nudge` (page
1), matching the task's "beats come out ordered by the manifest position of their first row."
The hand module's registration order (B1, B2, B3, B5, B4, B8x3, B9, B14, B13, B10x2, B11) is
route-order, not manifest-position order, and differs from the pinned generated order in several
places (e.g. `ch05.py` registers B5 — Keichi, event 6 — before B4 — Great Ball, event 5 — with an
explicit comment explaining why; the generated order puts `m036e005_item_ball` before
`m036e006_trainer`, i.e. manifest/event order, the opposite of the hand module's route order).

---

## 9. Determinism

- **`classify_manifest` sorts its output** by `min(match.roles)` (`archetypes.py:421`,
  `matches.sort(key=lambda match: min(match.roles))`) — deterministic regardless of dict/set
  iteration order upstream, since `min()` over a `Mapping`'s keys iterates then compares strings.
  Groups are also iterated in `sorted(groups)` order by `(map_id, event_id)` before classifying
  each event (`archetypes.py:418`).
- **`ArchetypeMatch.roles`/`.prescribed` are plain `dict`s, not sorted.** Insertion order is
  deterministic by construction in every matcher (`_match_trainer` inserts `p0` first, then
  `rows[1:]` in page order; `_match_item_ball` inserts `grant` then `spent`), so iterating
  `.roles.items()` is reproducible run-to-run, but nothing enforces sorted-by-row-id order — a
  future matcher that built `roles` from a `set` would silently break this.
- **`RowFloor.assertions` is a `frozenset`** (confirmed by the test file's `_rock`/`_plain`
  helpers constructing it as `frozenset({...})`/`frozenset()`). Any `group.py` code that needs
  "the `blocked_obstacle` assertion's `capability` param" for a row must not assume there is
  exactly one such assertion in insertion order — it should search/filter (`next(a for a in
  floor.assertions if a.kind == "blocked_obstacle")`) rather than index, and if a row could ever
  carry more than one `blocked_obstacle` assertion (not observed in this corpus — every measured
  row has exactly one), iterating a frozenset for output needs an explicit sort per CLAUDE.md's
  "Determinism is a first-class requirement" house rule.
- **`beat_name`'s own contract** (`test_name_does_not_depend_on_row_order`) requires the row-set
  identity, not the input `Sequence[ManifestRow]`'s order, to determine the name — consistent
  with every naming rule in the task table keying off map/event/page/capability/direction/other,
  never off row position in the passed-in list.
- **`PlannedBeat.kwargs`** is enforced sorted-by-key at construction (`plan.py:122-129`,
  `PlannedBeat.__post_init__`) — `make_kwargs` (`plan.py:58-62`) is the one canonical builder;
  `group.py` should build `kwargs=make_kwargs(...)` rather than a hand-sorted tuple, mirroring
  `beat_floor.assertion.make_params`'s shape per that function's own docstring.

---

## Decisions left to you

- **Stair grouping key (§2c/2d).** Candidate A (by `source_event_id`) never matches any hand
  module. Candidate B (orthogonal-only adjacency) matches CH05's registered beats and CH02's
  registered `B2`, but splits CH02's map033 (52,41)-(53,44) run — which `ch02.py`'s own
  (unregistered, DEFERRED) commentary calls one staircase — into two components. Candidate C
  (king-move/diagonal-inclusive adjacency) matches every hand-authored or hand-described grouping
  seen, registered or not. Whether to key on 4- or 8-directional adjacency, and whether a
  DEFERRED/unregistered hand comment should carry weight against a registered beat's grouping, is
  yours to weigh — no test in `test_beat_gen_group.py` exercises the diagonal case (its two
  stair tests are both same-`x` chains, i.e. orthogonal either way).
- **`behavior` as part of the grouping key.** Zero real adjacent-pair counterexamples exist
  (§2e) — the "different behavior stays separate" rule is entirely synthetic-test-driven today.
  Including it costs nothing observed in this corpus but is unverified against any real staircase
  that actually has mixed behaviors at adjacent cells.
- **`flavour_npc` (§3a).** It's a real claimable archetype (see the correction in §3a), but no
  CH05 test covers it. Its 79 CH01 matches first run in part two. Since the claiming layer is one
  loop over all matches, there's nothing special to decide here unless you want an archetype
  allow-list.
- **What "all role rows owned" means for a match whose missing role is `battle`, not `retalk`**
  (§3c, CH01's case). The task file's rationale ("a trainer can't be registered without its
  retalk page") only narrates the retalk direction; the rule itself ("claims its role rows only
  if all of them are owned") is symmetric, and the one measured battle-missing case bears that
  out identically. No decision needed here, but worth confirming your reading matches before you
  build it, since the prose could mislead a reader into hand-coding an asymmetric check.
- **`skip_claimed` (§4) — not actually open.** Nothing can execute it yet, but that's by design:
  Task 7 adds `ChapterBuilder.claimed_rows()` and implements `skip_claimed` in `generic_beat`
  (`07_generic.md`, "Registration rules"). Task 2 only has to emit the kwarg. *(Lead note,
  2026-09-21.)*
- **The CH05 `B8` stop (§8).** The hand module routes three beats (two warps and a nudge on two
  maps) as one group. The generated plan gives each its own group, so the solver sees three
  stops where the hand module had one. Task 2's naming rule is pinned by the test, so this isn't
  yours to change here. It matters for Task 9's Q4 (route order comparison).
