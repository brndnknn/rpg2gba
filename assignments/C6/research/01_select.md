# C6 Task 1 (select) — measured data

**Dated 2026-09-21.** This is measured data for the operator to design and implement
`beat_gen/select.py` against — not a solution, not a recommendation. Every number below was
produced by throwaway scripts under `/tmp/c6research/` against `load_chapter_rows`,
`build_chapter_stories(...)` and `floor_for_chapter`, run once and cached. (The cache built
the chain once as `["CH01".."CH05"]` and read each chapter out of it, instead of building
`["CH01".."CHnn"]` per chapter as the task specifies. Each chapter is seeded only from its
predecessors, so the statuses should be the same, but that wasn't re-measured per chapter.
No `later` appeared even with the longer chain.)
Row ids are quoted; no dialogue or story content is quoted anywhere in this doc.

---

## 1. The blocker vocabulary

### 1a — First floor-refusal reason, per chapter (count, one example row + truncated detail)

| Chapter | reason | count | example row | detail (truncated) |
|---|---|---|---|---|
| CH01 | `text_unnormalizable` | 29 | `map032/ev001/p0` | `code 101 @list[0]: text_source: character U+0022 '"' has no engine/charmap.txt e…` |
| CH01 | `non_literal_args` | 13 | `map050/ev005/p5/b4` | `jvGiveReward: reward selected by $game_variables[22], not literal: 'jvGiveReward…` |
| CH01 | `unknown_script_head` | 7 | `map032/ev009/p2` | `no recognized call head: 'list=["Orchynx","Raptorch","Eletux"]'` |
| CH01 | `story_state_refusal` | 5 | `map049/ev020/p0/b0` | `unclassified_condition: type 12 branch at list[0]: '!pbGet(1).is_a?(Numeric)…'` |
| CH01 | `unclassified_condition` | 2 | `map049/ev020/p0` | `no family matches: '!pbGet(1).is_a?(Numeric) || $game_variables[1] < 0'` |
| CH02 | `non_literal_args` | 2 | `map033/ev039/p1/b0` | `customTrainerBattle: trainer identity is a local variable, not literal…` |
| CH02 | `text_unnormalizable` | 1 | `map081/ev004/p0` | `code 101 @list[0]: text_source: character U+0022 '"' has no engine/charmap.txt e…` |
| CH03 | `text_unnormalizable` | 13 | `map031/ev007/p0` | `code 101 @list[1]: text_source: character U+002A '*' has no engine/charmap.txt e…` |
| CH03 | `unknown_script_head` | 5 | `map031/ev049/p0` | `no recognized call head: '$PokemonGlobal.seenStorageCreator=true'` |
| CH04 | `non_literal_args` | 2 | `map035/ev003/p1/b0` | `customTrainerBattle: trainer identity is a local variable, not literal…` |
| CH04 | `unknown_script_head` | 1 | `map035/ev019/p0` | `head 'for' has no extractor: 'for i in 14..18'` |
| CH05 | — | 0 | — | — |

This reproduces C6 plan B2's CH01 numbers exactly (29/13/7/5/2, sum 56 of 458) — see §7 for why
that total is *not* select's total refused count.

### 1b — Story-refusal HEAD (part before `:`), per chapter

| Chapter | head | count | example row | example string (truncated) |
|---|---|---|---|---|
| CH01 | `unparsed_state_write` | 217 | `map032/ev009/p2` | `unparsed_state_write` (no detail suffix) |
| CH01 | `unmodelled_outcome` | 83 | `map032/ev014/p0/b2` | `unmodelled_outcome:<detail>` |
| CH01 | `unclassified_condition` | 4 | `map049/ev020/p0/b0` | `unclassified_condition` |
| CH02 | `unmodelled_outcome` | 24 | — | |
| CH02 | `unparsed_state_write` | 6 | — | |
| CH03 | `unmodelled_outcome` | 10 | — | |
| CH03 | `unparsed_state_write` | 4 | — | |
| CH03 | `unmodelled_predicate` | 3 | `map067/ev009/p1` | |
| CH04 | `unparsed_state_write` | 13 | — | |
| CH04 | `unmodelled_outcome` | 12 | — | |
| CH05 | — | 0 | — | |

Note: these counts are **occurrences across every row that carries the head in its
`refusals` tuple**, not "rows with status refused" (a row's `refusals` tuple can hold more than
one code, and `RowVerdict.status` only reaches `"refused"` for rows whose own
`_structural_refusal` is non-`None` — see §6 for the status-level count, which is smaller:
CH01 status `refused` = 101 rows, not 217+83+4).

Four distinct heads appear in CH01–CH05 today, matching the task file's "four story heads
today" hint exactly: `unparsed_state_write`, `unmodelled_outcome`, `unclassified_condition`,
`unmodelled_predicate`.

### 1c — Every reason id the code CAN produce (present or absent from today's data)

**Floor reasons** (`beat_floor/`), file:line for each:

| reason | file:line | seen in CH01–05? |
|---|---|---|
| `text_unnormalizable` | `walk.py:287`, `:407` | yes |
| `non_literal_args` | `condition.py:77,94,115,140,164,198`; `script.py:176,194,213,219,240,265` | yes |
| `unknown_script_head` | `script.py:92` | yes |
| `unclassified_condition` | `condition.py:43` | yes |
| `story_state_refusal` | `walk.py:593` | yes |
| `no_condition_extractor` | `condition.py:49` | no |
| `no_extractor` | `walk.py:368` | no |
| `warp_variable_target` | `walk.py:211` | no |
| `malformed_warp` | `walk.py:216` | no |
| `event_position_variable_target` | `walk.py:243` | no |
| `malformed_event_position` | `walk.py:248` | no |
| `malformed_common_event_call` | `walk.py:465` | no |
| `common_event_cycle` | `walk.py:471` | no |
| `missing_common_event` | `walk.py:478` | no |
| `stair_missing_source_event` | `terrain.py:195` | no |
| `stair_no_qualifying_page` | `terrain.py:106` (via `derive_stair_steps`), wired at `terrain.py:209` | no |
| `stair_branch_not_singular` | `terrain.py:124` | no |
| `stair_unknown_facing_direction` | `terrain.py:129` | no |
| `obstacle_multiple_capabilities` | `obstacle.py:51` | no |
| `obstacle_missing_cell` | `obstacle.py:56` | no |

That's 20 distinct floor reasons total; only 5 appear in the current CH01–CH05 corpus, matching
the task file's "five floor reasons... today" hint.

**Story-refusal heads** (`story_state/extract.py` and `model.py`, `code`/head string passed to
`Refusal(...)`, which becomes the head of a `RowVerdict.refusals` entry via
`_structural_refusal`, `model.py:322-351`):

| head | file:line | seen in CH01–05? |
|---|---|---|
| `unmodelled_outcome` (+`:detail`) | `model.py:346` | yes |
| `unparsed_state_condition` | `model.py:344` | no |
| `missing_arm_guard` | `model.py:341` | no |
| `unmodelled_predicate` | `extract.py:191`, `model.py:895` (common-event variant) | yes |
| `malformed_page_condition` | `extract.py:205,215` | no |
| `malformed_branch_condition` | `extract.py:265,279,292,305` | no |
| `nonconstant_variable_condition` | `extract.py:285` | no |
| `unclassified_condition` | `extract.py:327` | yes |
| `nonconstant_variable_write` | `extract.py:~554,562` | no |
| `malformed_write` | `extract.py:528,539,571,581` | no |
| `common_event_cycle` | `extract.py:585` | no |
| `missing_common_event` | `extract.py:591` | no |
| `invalid_self_switch_write_in_common_event` | `extract.py:895` | no |
| `unparseable_pokemon_center_call` | `extract.py:488` | no |
| `unparsed_state_write` | `extract.py:497` | yes |

15 distinct heads total; 4 appear today. **`unclassified_condition` is ambiguous**: it is both
a *floor* reason (`condition.py:43`, when a `111` type-12 condition's text doesn't classify) and
a *story-refusal head* (`extract.py:327`, same underlying classifier, surfaced through
`story_state` instead). They are the same underlying event but reach `select_rows` through two
different inputs (`floors[row_id].refusals[0].reason` vs. `verdicts[row_id].refusals[i]`'s
head), and the task's rule table (rule 3 before rule 7) means the story-state occurrence always
wins when both are present on the same row — confirmed in the data: every CH01 row with a
floor-first-reason of `unclassified_condition` (2 rows) *also* has a story verdict of status
`refused` whose head is `unclassified_condition` (see §6, `overlap_story_refused_and_floor_refused`
includes `map049/ev020/p0` and its arm). So in practice CH01–CH05 never puts
`unclassified_condition` in front of `blocker_for` via the floor path alone.

### 1d — What the docs say each blocker covers, and what's undocumented

`plan.py:47-51` (`Blocker` docstring):
> `#109` is the text-normalisation gap; `C8` is the Ruby-subset interpreter; `story-state` is an
> outcome-table or modelling gap in `story_state/`; `floor` is any other floor refusal (stairs,
> obstacles); `cell` is "no location could be derived".

`C6_GENERATOR_PLAN.md` B2 (`:349-374`) does not name a blocker-per-reason table; it only gives
the CH01 count breakdown quoted in §7 below and the ruling "an honest refusal counts as done."

`tests/test_beat_gen_select.py`'s `test_blocker_table` (`:56-69`) is the only place a
reason→blocker mapping is actually pinned, and it covers exactly 10 reasons:

| reason | blocker (test-pinned) |
|---|---|
| `text_unnormalizable` | `#109` |
| `unknown_script_head` | `C8` |
| `non_literal_args` | `C8` |
| `unparsed_state_write` | `C8` |
| `unmodelled_outcome` | `story-state` |
| `unmodelled_predicate` | `story-state` |
| `unclassified_condition` | `story-state` |
| `story_state_refusal` | `story-state` |
| `stair_no_qualifying_page` | `floor` |
| `obstacle_missing_cell` | `floor` |

**Tension worth flagging, not resolving:** `story_state_refusal` is itself a *floor* reason
(`walk.py:593`, `FloorRefusal.reason == "story_state_refusal"`), yet the test maps it to blocker
`story-state`, not `floor`. *(Lead note: this is probably not a contradiction. "Any other" reads as "any floor refusal
not already owned by `#109`/`C8`/`story-state`", and `story_state_refusal` is the floor
relaying a story-model refusal, so it goes to the stage that has to fix it. The pattern the
pinned table follows is "classify by who fixes it, not by which input reported it". Check that
reading against the table before extending it.)*

**Docs don't say** where the 10 floor reasons and 11 story heads absent from the test table
belong (§1c's "no" rows). The task file names only "the stair and obstacle reasons from C5 and
C7" as needing classification beyond the 10 pinned; it does not name the other 8 floor reasons
(`no_extractor`, `no_condition_extractor`, `warp_variable_target`, `malformed_warp`,
`event_position_variable_target`, `malformed_event_position`, `malformed_common_event_call`,
`common_event_cycle`, `missing_common_event`) or the 11 story heads beyond the 4 seen. None of
these appear in CH01–CH05 today, so `blocker_for`'s behavior on them is unconstrained by any
real-data test — only by whatever the implementer decides the table should cover.

`cell` (`plan.py:47`) is documented as belonging to `locate.py`/`seam.py`
(`locate.py:39`, `seam.py:49`, `review.py:22` — the blocker display order), not to
`select.py`. No floor or story-state reason in the corpus maps to it.

---

## 2. `RowVerdict.status` vocabulary and counts per chapter

| Chapter | live | refused | undetermined | later | unreachable |
|---|---|---|---|---|---|
| CH01 | 262 | 101 | 94 | 0 | 0 |
| CH02 | 157 | 24 | 4 | 0 | 0 |
| CH03 | 196 | 15 | 16 | 0 | 0 |
| CH04 | 63 | 19 | 2 | 0 | 0 |
| CH05 | 51 | 0 | 0 | 0 | 0 |

**`later` never occurs in CH01–CH05** when the chain is built as `["CH01", …, "CH0N"]`
(the chain the task file specifies) — there is no chapter *after* the one being modelled in
scope, so nothing can be assigned ownership beyond it. `later`/`owner` is exercised only once
you build a chain that runs past the chapter whose ownership you're checking (e.g. building
`["CH01".."CH05"]` and reading `stories["CH01"].rows`, not `stories["CH05"].rows`). Task 1's
own real-data tests (`_real`) always read `stories[chapter].rows` for the *last* chapter in the
chain they built, so `later` is untested by the pinned real-data tests and only covered by the
synthetic `test_later_goes_elsewhere_with_its_owner`.

`unreachable` also never occurs in this corpus; every unresolved row in CH01–CH05 lands
`undetermined` instead (an `undetermined` status means "we don't know", `unreachable` means "we
know it's dead" — see `model.py:1117`, `1412`: both derive from the same
`_undetermined_detail(...)` call, branching only on whether that helper returns a detail
string).

---

## 3. Coverage mismatch (manifest vs. verdicts)

| Chapter | manifest rows | manifest rows w/ no verdict | by kind | verdict ids not in manifest |
|---|---|---|---|---|
| CH01 | 458 | 1 | `seam`: 1 | 0 |
| CH02 | 171 | 7 | `terrain`: 7 | 21 |
| CH03 | 222 | 4 | `seam`: 1, `terrain`: 3 | 9 |
| CH04 | 86 | 2 | `seam`: 2 | 0 |
| CH05 | 43 | 4 | `terrain`: 4 | 12 |

Every "manifest row with no verdict" is a `seam` or `terrain` row — consistent with the task
file's "seam and terrain rows skip the story rules entirely" (rule 2) and the README's "`story_state`
has verdicts for some events the manifest leaves out."

"Verdict ids not in manifest" examples (row ids only, no content):
- CH02: `map033/ev026/p0`, `map033/ev026/p0/b0`, `map033/ev026/p0/b1`, `map033/ev031/p0`, `map033/ev031/p0/b0`, … (21 total)
- CH03: `map031/ev024/p0`, `map031/ev024/p0/b0`, `map031/ev024/p0/b1`, `map031/ev026/p0`, `map031/ev026/p0/b0`, … (9 total)
- CH05: `map037/ev003/p0`, `map037/ev003/p0/b0`, `map037/ev003/p0/b1`, `map037/ev006/p0`, `map037/ev006/p0/b0`, `map037/ev006/p0/b1`, `map037/ev007/p0`, `map037/ev007/p0/b0`, `map037/ev007/p0/b1`, `map037/ev008/p0`, `map037/ev008/p0/b0`, `map037/ev008/p0/b1` (12 total; all `map037`, all `page`/`branch` shaped)

CH05's 12 are all on `map037`, a map the story model walks (it's in the chain's cumulative
scope, e.g. reachable from a common event or an earlier chapter's map) but that the CH05
manifest generator did not emit rows for. `select_rows` never iterates `verdicts` directly (per
the task file's warning), so this mismatch only matters if a future manifest change starts
emitting `map037` rows for CH05 without also confirming their verdicts still resolve — it
doesn't affect Task 1 as specified, which always keys off `rows` (manifest) order.

---

## 4. Rule 6 data (`requires`)

| Chapter | rows w/ `requires` | by capability | by kind | rows w/ `blocked_obstacle` floor assertion | rows w/o it |
|---|---|---|---|---|---|
| CH01 | 18 | `rock_smash`: 18 | `page`: 6, `branch`: 12 | 3 | 15 |
| CH02 | 60 | `rock_smash`: 58, `surf`: 2 | `page`: 26, `branch`: 34 | 6 | 54 |
| CH03 | 18 | `strength`: 18 | `page`: 10, `branch`: 8 | 5 | 13 |
| CH04 | 57 | `rock_smash`: 57 | `page`: 27, `branch`: 30 | 5 | 52 |
| CH05 | 8 | `surf`: 8 | `page`: 4, `branch`: 4 | 0 | 8 |

Every chapter has far more `requires`-nonempty rows than `blocked_obstacle`-bearing rows — most
`requires` rows are **not** the obstacle itself; they're reachability-derived (C7 Task 3's
trap). Code citation for the union that produces `ManifestRow.requires`:
`chapter_manifest/generator.py:990`:
```python
requires = tuple(sorted(set(extracted["requires"]) | set(reach_requires)))
```
`extracted["requires"]` (`_extract_page`, `generator.py:626`, via `_HEAD_REQUIRES`,
`generator.py:218`) is the head-derived half (the row's own commands call
`pbRockSmash`/`pbRockSmashRandomEncounter`/`pbPushThisBoulder`); `reach_requires`
(`generator.py:975`, `_reachability_requires`) is added for any event reachable only past an
obstacle. **`ManifestRow.requires` does not record which half contributed a given capability** —
once unioned, the two sources are indistinguishable from the field alone. The only
source-of-truth discriminator that exists today for "is this row itself the obstacle" is
whether its floor carries a `blocked_obstacle` assertion (C7 Task 3's ruling, referenced in the
task file's hints).

---

## 5. CH05 `map036/ev008` in full

Four manifest rows, all `kind="page"` or `"branch"`, all `requires=("surf",)`:

| row_id | kind | verdict.status | verdict.owner | verdict.blockers | floor assertion kinds | floor refusals | `blocked_obstacle`? |
|---|---|---|---|---|---|---|---|
| `map036/ev008/p0` | page | live | CH05 | () | `completes`, `item_grant`, `trigger` | () | no |
| `map036/ev008/p0/b0` | branch | live | CH05 | () | `completes`, `self_switch_write`, `trigger` | () | no |
| `map036/ev008/p0/b1` | branch | live | CH05 | `('harness:full_bag',)` | `completes`, `trigger` | () | no |
| `map036/ev008/p1` | page | live | CH05 | () | `completes`, `trigger` | () | no |

The story model says every one of these is `live` (verdict.status), owned by CH05, with no
refusals. The floor never asserts `blocked_obstacle` on any of them. So under the task's rule
table, rule 3/4/5 don't fire (status is `live`, not `refused`/`undetermined`/`later`), and rule
6 fires: `requires=("surf",)` is non-empty and no floor assertion says this row *is* the
obstacle → `Elsewhere("blocked")`.

`map036/ev009` mirrors this exactly (also 4 rows, `p0`, `p0/b0`, `p0/b1`, `p1`, same shape).
Together these are the 8 rows CH05's test (`test_real_ch05_owns_all_but_the_surf_items`) expects
under `sel.elsewhere`, all status `"blocked"`. Confirmed by direct measurement: `select`-rule
simulation over real CH05 data yields exactly `owned=35, elsewhere=8 (all "blocked"), refused=0`.

---

## 6. Precedence overlaps

Counts of rows where more than one rule-table condition is simultaneously true (this is what
the ordering in rule 3 > 6 > 7 actually decides — ties broken by whichever rule comes first).

| Chapter | story-refused ∧ floor-refused | `requires`-blocked ∧ floor-refused | undetermined ∧ floor-refused | `requires`-blocked ∧ story-refused |
|---|---|---|---|---|
| CH01 | 32 (e.g. `map032/ev009/p2`, `map049/ev020/p0/b0`) | 0 | 4 (e.g. `map049/ev020/p0`, `map050/ev024/p0/b1`) | 6 (e.g. `map032/ev014/p0/b2`) |
| CH02 | 2 (`map033/ev039/p1/b0`, `map033/ev053/p1/b0`) | 1 (`map033/ev039/p1/b0`) | 0 | 6 (e.g. `map033/ev039/p1/b0..b3`, `p2/b0`) |
| CH03 | 7 (e.g. `map067/ev009/p1`) | 0 | 5 (e.g. `map031/ev007/p1`) | 0 |
| CH04 | 3 (`map035/ev003/p1/b0`, `map035/ev019/p0`, `map035/ev023/p1/b0`) | 2 (`map035/ev019/p0`, `map035/ev023/p1/b0`) | 0 | 13 (e.g. `map035/ev019/p0..b3`) |
| CH05 | 0 | 0 | 0 | 0 |

Every chapter except CH05 has real overlap cases, so the ordering genuinely matters — it isn't
academic. Row `map033/ev039/p1/b0` (CH02) is simultaneously story-refused, floor-refused, *and*
`requires`-blocked, so it's the one row in this corpus where all three rules could fire; rules
3 and 6 both outrank rule 7 in the task's table, and rule 3 outranks rule 6, so this row's fate
depends specifically on 3-before-6 (confirmed by `test_story_refusal_wins_over_blocked` in the
pinned test file — same shape, synthetic).

---

## 7. CH01 refusal counts — B2 vs. the full rule table

B2 (`C6_GENERATOR_PLAN.md:360-361`) measured **56 of 458** CH01 rows refusing, using
`floor_for_chapter` alone, grouped by **first floor-refusal reason**: 29 `text_unnormalizable`,
13 `non_literal_args`, 7 `unknown_script_head`, 5 `story_state_refusal`, 2
`unclassified_condition`. §1a above reproduces this exactly.

Running the **full rule table** (rules 1-8, using the test-pinned `blocker_for` table) over the
same CH01 data:

| bucket | count |
|---|---|
| owned | 234 |
| refused | **215** |
| elsewhere | 9 |

Refused-row reasons (by rule that catches them):
- rule 3 (story `status == "refused"`, first head): `unparsed_state_write` 70, `unmodelled_outcome` 27, `unclassified_condition` 4 (= 101, the §2 status count)
- rule 4 (story `status == "undetermined"`): 94, reason `undetermined`
- rule 7 (floor-refused, no earlier rule fired): `text_unnormalizable` 18, `unknown_script_head` 2

*(Corrected 2026-09-21 by the lead: the first draft put the 2 `unknown_script_head` rows under
rule 3. They are floor refusals reaching rule 7; no story head is `unknown_script_head`. Totals
were unaffected. Through the test-pinned table the 215 split by blocker: `#109` 18, `C8` 72,
`story-state` 125.)*

215 ≠ 56 because B2 counted **floor refusals only** (the task file's own hint). The task's rule
table gives **rule 3 (story-state `refused`) and rule 4 (`undetermined`) precedence over rule 7
(floor-refused)** — so a row that is both story-refused *and* floor-refused (32 such CH01 rows,
§6) counts once, under its story-state reason, never its floor reason. The 94 `undetermined`
rows alone account for most of the gap (56 → 215 is +159; 94 of that is `undetermined`, which
B2's floor-only count never touches at all — `undetermined` is a story-model status, not a
floor reason). The remaining rows are story-`refused` rows whose *first* floor reason (if any)
differs from their story head, or that have no floor refusal at all.

---

## 8. Refusal-string shape check

Checked every `RowVerdict.refusals` entry across CH01–CH05 (all rows, all chapters): **zero**
entries contain more than one `:`. Every entry is either a bare head (`"unparsed_state_write"`,
`"unclassified_condition"`) or `"head:detail"` with exactly one colon (e.g.
`"unmodelled_outcome:<detail>"`). `str.partition(":")` (the task file's suggested approach)
is safe over the measured corpus; no entry was found that would produce a wrong head under that
split. (This does not prove no `head:detail` value can ever itself contain a colon — `detail`
strings are free text sourced from `guard.outcome.detail`, `model.py:346` — only that none does
today.)

---

## 9. Determinism notes

- **`RowFloor.assertions` is a `frozenset`** (`assertion.py:102`). Any code in `select.py` that
  needs to test for a specific assertion kind (`blocked_obstacle`, rule 6) can use a set
  membership test (`any(a.kind == "blocked_obstacle" for a in floor.assertions)`) — order
  doesn't matter for that. It would matter only if `select.py` ever formats/prints multiple
  assertions from the same floor; nothing in the rule table calls for that.
- **`RowFloor.refusals` and `RowVerdict.refusals` are tuples, not sets** (`assertion.py:103`,
  `model.py:214`) — insertion order is preserved and is the source of "the row's *first* floor
  refusal" (rule 7) being well-defined. Order of construction, traced:
  1. `_walk_commands` refusals, in command/`list_index` order (`walk.py:634-636`)
  2. story-state-derived refusals for the row, appended next (`walk.py:638-642`,
     `_state_assertions_for_row`)
  3. `blocked_obstacle`-extractor refusals (C7 Task 3), appended last via
     `dataclasses.replace(floor, refusals=floor.refusals + refused, ...)` (`walk.py:728`)

  All three stages are themselves built from stable, ordered source data (the page's command
  list, in file order), so "first floor refusal" is deterministic and reproducible across runs
  — but it is an artifact of *construction order*, not a sort; nothing re-sorts `refusals` by
  reason or `list_index` after assembly.
- `RowVerdict.refusals`'s order comes from `_structural_refusal`'s `parent + own` concatenation
  (`model.py:348`) — parent-chain refusals first, this row's own last — again deterministic by
  construction, not by an explicit sort.

---

## Decisions left to you

- **`blocker_for`'s table size.** The test file pins 10 reasons. §1c lists 20 floor reasons and
  15 story heads that exist in code; only 5 + 4 appear in today's CH01–CH05 data. Do you build
  the table to cover only what's tested (raising `ValueError` on everything else, including
  reasons that exist in code but haven't been seen yet), or pre-classify the full vocabulary
  now so a future chapter/edge case doesn't hard-crash `select_rows`? Both are consistent with
  "fail loud" (§4.5) — the question is whether "loud" happens at CH06 or at design time.
- **The `story_state_refusal` / `floor` tension (§1d).** The `Blocker` docstring's plain-English
  gloss ("`floor` is any other floor refusal") doesn't match the test's mapping of
  `story_state_refusal` (a floor reason) to `story-state`. If you extend `blocker_for` beyond
  the 10 pinned reasons, you'll need your own rule for what "any other floor refusal" means
  given this exception already exists.
- **`unclassified_condition`'s dual origin (§1c).** It's mintable from both the floor path and
  the story-state path on the same underlying event. The rule table's ordering (rule 3 before
  rule 7) already resolves which one `select_rows` sees when both are present on one row — but
  whether that's the *right* call (vs. e.g. checking floor and story-state reasons for
  consistency and flagging a disagreement) is a design question the task file doesn't raise and
  the tests don't probe.
- **Where `no_story_verdict`'s reason id comes from.** Rule 2 requires minting a refusal with
  reason `"no_story_verdict"` — this string exists nowhere in `story_state/` or `beat_floor/`;
  it's `select.py`'s own literal (confirmed: `test_event_row_without_verdict_is_refused_not_dropped`
  pins it). Whether `blocker_for` should even be consulted for it (vs. hardcoding
  `blocker="story-state"` at the rule-2 call site) is open — the rule table's phrasing
  ("refused, `story-state`, `no_story_verdict`") suggests the blocker is fixed, not looked up.
