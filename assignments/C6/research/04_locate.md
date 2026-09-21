# C6 Task 4 (locate) — measured data

**Dated 2026-09-21.** Measured data for the operator to design and implement `beat_gen/locate.py`
against — **not a solution, not a recommendation.** Every number below came from throwaway
scripts under `/tmp/c6research/` (`locate1.py`..`locate4.py`) against the cached
`/tmp/c6research/data.pkl` (CH01–CH05 `rows`/`verdicts`/`floors`, one gather run), plus direct
reads of `reference/routes/CH05.route.json` / `CH05.locations.json` and one live
`derive_locations` call against the real, already-implemented `routing/locations.py`. `select.py`
and `group.py` are still stubs (`NotImplementedError`), so nothing here ran the real C6 pipeline
end to end — CH05 group/row sets in §2 were reconstructed by hand from `classify_manifest`
output plus the pinned 20-beat name list in `tests/test_beat_gen_group.py:221-233`, cross-checked
against `reference/routes/CH05.route.json`'s own `rows` field (§6). No dialogue or story content
is quoted; row ids, map/event ids, and cell coordinates only.

---

## 1. The existing pipeline, step by step

### 1a — `derive_locations` (`routing/locations.py:441-495`)

Iterates `rows` (the **whole manifest**, in manifest order — the loop is `for row in rows:`,
`:467`), looks up each row's `beat:<id>` disposition (`:468-479`), and for every row disposed to a
beat, calls `cell_for_row(row)` (`:479`) and appends the result to `claimed[beat_id]`. Once every
row is walked, for each `beat_id` in first-appearance order it calls
`choose_routing_point(beat_id, candidates)` (`:484`) and builds one `BeatLocationRecord` (`:485-494`).
A record's `rows` field is `tuple(c.row_id for c in candidates)` — literally the ordered list of
manifest row ids that contributed a cell, `:491`.

### 1b — `choose_routing_point` (`:374-438`)

Quoted rationale (`:401-409`, the two-part rule):

> "1. **Collapse identical cells first.** Several pages of one event resolve to the same cell...
> 2. **A beat that spans genuinely different cells is a traversal, and a traversal is represented
> by where it ENDS** — its last claimed row. Both idioms that create multi-cell beats are round
> trips... Routing cost is a function of where the NEXT beat departs from, so the terminal row is
> the honest representative; taking the first would charge the solver for a position the player
> has already left."

Mechanically: dedupe `candidates` by `(map_constant, x, y)` preserving first-seen order
(`:415-421`); if exactly one distinct cell, return it; otherwise return the **last** distinct
cell (`:426`) and log every candidate at INFO.

### 1c — `chapter_from_locations` (`:567-596`)

Builds a `ChapterBuilder` and, for each record, calls
`builder.beat(record.beat_id, ..., map_constant=..., at=(x, y), rows=record.rows)` with a body
that only raises (`_never_run`, `:579-586`) — "this chapter exists only for the offline route
solve, never for a run." **No `group=` is passed.** Per `ChapterBuilder.beat`'s own docstring
(`playtest/chapter.py:412-415`): "A beat with no `group` gets its own singleton group, named after
the beat itself." So every `BeatLocationRecord.beat_id` becomes both a beat name **and** its own
group id, 1:1 — confirmed directly by `routing/__main__.py:416-418`'s comment: "`chapter_from_
locations` gives every derived beat its own singleton group, named after the beat — so
`record.beat_id` IS the group id `solve_route` will see."

### 1d — `routing/__main__.py plan` → `candidates=` wiring (`:397-424`)

Only on the `--locations` path (`locations_opt is not None`): loads the locations file, builds
`chapter_obj = chapter_from_locations(...)`, then for every record with a non-empty
`approach_candidates`, builds
`route_candidates[record.beat_id] = tuple(RouteCandidate(x=c.x, y=c.y, side=c.side,
resolver=c.resolver) for c in record.approach_candidates)` (`:419-424`). This dict is passed as
`solve_route(..., candidates=route_candidates)` (`:450`). On the **other** path (`--module`,
importing an authored chapter module), `route_candidates` stays the empty dict declared before the
`if` (`:395`) — never populated.

---

## 2. `cell_for_row` over CH05 — per row, per pinned group

CH05's pinned 14 groups (from `tests/test_beat_gen_group.py:221-233`'s 20 beat names, minus
`_arms` suffixes, cross-checked against `classify_manifest(CH05 rows)` and
`reference/routes/CH05.route.json`'s per-node `rows` field). Branch/arm rows are **not** run
through `cell_for_row` here — §3 shows why (it raises `unknown row kind 'branch'` unconditionally)
— only the page/terrain rows each group owns directly.

| group | rows (page/terrain) | `cell_for_row` result | chosen (terminal) | n approach candidates | sides |
|---|---|---|---|---|---|
| `m036e001_warp` | `map036/ev001/p0` | OK `event_cell`, (17,40) | same | 0 | — |
| `m036e002_warp` | `map036/ev002/p0` | OK `event_cell`, (17,4) | same | 0 | — |
| `m036e002_arrival_nudge` | `map036/ev002/p1` | OK `event_cell`, (17,4) | same | 0 | — |
| `m036e003_item_ball` | `p0`,`p1` (both → same cell) | OK `approach_to`, (10,34) | (10,34) | 4 | north,south,east,west |
| `m036e004_trainer` | `p0`,`p1` (same cell) | OK `approach_to`, (18,28) | (18,28) | 3 | north,south,east |
| `m036e005_item_ball` | `p0`,`p1` (same cell) | OK `approach_to`, (21,7) | (21,7) | 1 | west |
| `m036e006_trainer` | `p0`,`p1` (same cell) | OK `approach_to`, (6,12) | (6,12) | 4 | north,south,east,west |
| `m037e001_warp` | `map037/ev001/p0` | OK `event_cell`, (16,27) | same | 0 | — |
| `m037e002_warp` | `map037/ev002/p0` | OK `event_cell`, (16,5) | same | 0 | — |
| `m037e004_trainer` | `p0`,`p1` (same cell) | OK `approach_to`, (24,9) | (24,9) | 4 | north,south,east,west |
| `m037e005p0` | `map037/ev005/p0` | OK `approach_to`, (8,6) | same | 4 | north,south,east,west |
| `m037e005p1` | `map037/ev005/p1` | OK `approach_to`, (8,6) | same | 4 | north,south,east,west |
| `m037stair11x9` | `stairs/11,9`, `stairs/11,10` | OK `stair_approach` each, DISTINCT cells (10,9) then (10,10) | **(10,10)** (terminal = last row, `11,10`) | 2 | west,east |
| `m037stair20x9` | `stairs/20,9`, `stairs/20,10` | OK `stair_approach` each, DISTINCT cells (19,9) then (19,10) | **(19,10)** (terminal = last row, `20,10`) | 2 | west,east |

**Zero refusals across all 14 groups**, confirming the pinned real-data test's expectation
(`test_real_ch05_every_group_locates`: `refusals == []`, `len(records) == 14`).

`m036e003_item_ball`/`m036e004_trainer`/etc. each have **two candidate rows that resolve to the
identical cell** — `choose_routing_point`'s "collapse identical cells first" branch fires, so the
terminal-row question never arises for them. Only the two staircase groups actually exercise the
terminal-row branch in real CH05 data (two genuinely distinct cells each).

### A measured inconsistency worth flagging (not a Task-4 bug, a corpus-freshness one)

A live call to `derive_locations` against the **current** `reference/manifests/CH05.manifest.json`
+ `CH05.dispositions.json` gives `B13 = (10, 10)`, `B14 = (19, 10)` — matching the table above
exactly. But the **committed** `reference/routes/CH05.locations.json` (last touched in commit
`507b1997`) has `B13 = (10, 9)`, `B14 = (19, 9)` — the *other* end of each staircase — because its
stored `candidates` array lists the two terrain rows in the opposite order (`11,10` before `11,9`)
from the current manifest's order (`11,9` at manifest index 39, `11,10` at index 40, confirmed by
direct enumeration). `choose_routing_point` always returns the terminal (last) distinct candidate,
so a reordered candidate list silently flips which end gets picked. This is evidence the committed
locations file is stale relative to the current manifest ordering — not something Task 4 needs to
fix, but worth knowing if you compare your own output against that file by eye.

---

## 3. Arms located through their page

**Measured across all of CH01–CH05: every branch row's page, looked up in the FULL manifest and
run through `cell_for_row`, succeeds. 0 failures out of 488 branch rows.**

| Chapter | branch rows | page locates OK | page locate fails |
|---|---|---|---|
| CH01 | 247 | 247 | 0 |
| CH02 | 88 | 88 | 0 |
| CH03 | 91 | 91 | 0 |
| CH04 | 44 | 44 | 0 |
| CH05 | 18 | 18 | 0 |
| **total** | **488** | **488** | **0** |

The owning page was found via `parse_row_id(branch_row_id).owning_page_row_id` (flat-grammar
lookup, no `parent_row_id` walk needed — confirmed for this exact purpose already in
`02_group.md` §1b) and looked up in a dict keyed over the **whole chapter's rows**, not any
"owned" subset.

This directly answers the CH01/CH03 orphan-arm cases named in `02_group.md` §7 (arms whose owning
page was refused by Task 1's story/floor logic, not by `cell_for_row`): I re-ran `cell_for_row`
on each named owning page directly —

| Chapter | orphan page | `cell_for_row` result |
|---|---|---|
| CH01 | `map089/ev004/p0` | OK — `MAP_MOKI_TOWN_THEOS_HOUSE_2F` (2,6), `approach_to(...,ev4)` |
| CH01 | `map172/ev004/p0` | OK — `MAP_MOKI_TOWN_THEOS_HOUSE_1F` (10,7), `event_cell(...,ev4)` |
| CH03 | `map031/ev049/p0` | OK — `MAP_KEVLAR_TOWN` (21,14), `approach_to(...,ev49)` |

So the fact that a page was refused by `select_rows` (story-state/floor reasons, an *upstream*,
semantic judgement about whether the chapter should walk that content) is independent of whether
that page's row still has a mechanically valid cell. **This is exactly why `rows_by_id` must be
the whole manifest, not just `sel.owned`**: an arm claimed by a beat (its row survived Task 1's
floor/story filtering even though its page did not) still needs `rows_by_id[owning_page_id]` to
exist so its page's row object can be handed to `cell_for_row` — a `rows_by_id` restricted to
owned rows would raise `KeyError` on the page lookup for every one of these 10 real arms (6 in
CH01, 4 in CH03).

---

## 4. Location failures corpus-wide (page + terrain rows only; branch/seam excluded, see §3/§5)

### 4a — Success/fail counts, reconciling to row-kind totals

| Chapter | page rows | terrain rows | page+terrain total | `cell_for_row` OK | `cell_for_row` fails |
|---|---|---|---|---|---|
| CH01 | 210 | 0 | 210 | 206 | 4 |
| CH02 | 76 | 7 | 83 | 77 | 6 |
| CH03 | 127 | 3 | 130 | 129 | 1 |
| CH04 | 40 | 0 | 40 | 40 | 0 |
| CH05 | 21 | 4 | 25 | 25 | 0 |
| **total** | **474** | **14** | **488** | **477** | **11** |

(Row-kind totals from direct enumeration of each chapter's manifest rows: `dict(Counter(r.kind for
r in rows))`; e.g. CH01 = `{page: 210, branch: 247, seam: 1}` — 210+247+1 = 458, matching the
`assignments/C6/README.md` table's CH01 total of 458 exactly. Same reconciliation holds for all
five chapters.)

### 4b — Failures by error type

| error type | count | meaning |
|---|---|---|
| `other` (no walkable adjacent cell) | 7 | `approach_to` raises "this event cannot be approached at all under the offline graph's collision data" — the event exists but every neighbour is unwalkable |
| `trigger_no_cell_rule` | 2 | `row.trigger` is not in `_ON_EVENT_TRIGGERS` or `_ADJACENT_TRIGGERS` |
| `stair_unwalkable` | 2 | `_stair_approach` found an E/W neighbour owning a `stair_diagonal` edge but it isn't walkable (both are one CH02 run, `map033`, cells `52,41` and `53,44`) |
| **total** | **11** | |

Four examples of `other` (all `approach_to` events with zero walkable neighbours):
`CH01 map048/ev001/p1`, `CH01 map048/ev005/p1`, `CH01 map049/ev018/p1`, `CH03 map067/ev001/p0`.
The other three are in CH02 (4a's CH02 row: 6 = 3 `other` + 1 `parallel` + 2 stair). None of
the seven pages has branch arms, which is why §3 still shows 0 arm failures.

*(Lead note, 2026-09-21: the two `stair_unwalkable` cells, map033 `52,41` and `53,44`, are the
two ends of the diagonal CH02 run in `02_group.md` §2c. Under the whole-group refusal rule,
**both** Task 2 grouping candidates refuse this run in full. King-move adjacency makes one 4-cell
group containing both bad cells. Orthogonal adjacency makes two 2-cell groups, each containing
one. So the stair-key decision doesn't change CH02's coverage today, only the refusal count and
the beat names.)*

### 4c — Trigger values seen (page rows only, all 5 chapters) and their membership

| trigger | count | in `_ON_EVENT_TRIGGERS` | in `_ADJACENT_TRIGGERS` |
|---|---|---|---|
| `action` | 347 | no | **yes** |
| `player_touch` | 60 | **yes** | no |
| `autorun` | 38 | **yes** | no |
| `event_touch` | 27 | no | **yes** |
| `parallel` | 2 | no | no |

`parallel` is the only trigger value observed anywhere in CH01–CH05 that has no cell rule at all;
both its occurrences (`CH01 map048/ev005/p0`, `CH02 map033/ev004/p0`) raise
`trigger_no_cell_rule`. This is the only way a **page** row (as opposed to a branch/seam row)
reaches `cell_for_row`'s unconditional-raise branch (`:363-367`) in the real corpus — 2 of 474
page rows, 0.4%.

**Net for "how often the whole-group refusal rule will fire" (README's group-refusal rule, task
file "Rules the tests pin"):** in this corpus, 11 of 488 page+terrain rows (2.3%) fail
`cell_for_row` for a mechanical reason (7 unapproachable events, 2 unparseable trigger values, 2
unwalkable stair neighbours). Every failing row's *group* would be refused wholesale under the
task's stated rule, whatever grouping Task 2 assigns those rows to — this table does not attempt
to map each failing row to a Task-2 group, since `group.py` is unimplemented and the grouping key
for `parallel`-triggered/unapproachable-event rows in CH01–CH04 is undetermined.

---

## 5. `ApproachCandidate` — fields, real formats, and what the tests pin

### 5a — Fields (`routing/locations.py:52-76`)

```python
@dataclass(frozen=True)
class ApproachCandidate:
    x: int
    y: int
    side: str
    resolver: str
```

`resolver` is "a call an author could paste into a chapter module to pin this exact side" for an
`approach_to`-derived beat (a literal, valid `prefer=` call); for a `stair_approach`-derived beat
there is no public `cells.py` side parameter *predating* 2026-09-08 (module docstring, `:64-70`),
but as of `_stair_side_candidates`'s current code (`:170-200`) `stair_approach` DOES now take a
required `side=`, so its `resolver` string is likewise paste-able — see the real examples below.

### 5b — Real examples from CH05 (§2's table, verbatim strings)

- `approach_to`-derived (4-way): `approach_to(MAP_PASSAGE_CAVE_1F, ev3, prefer="north")`,
  `..., prefer="south")`, `..., prefer="east")`, `..., prefer="west")` — side values are exactly
  `"north"`/`"south"`/`"east"`/`"west"`, in that fixed N/S/E/W order (`_approach_side_candidates`
  iterates `adjacent_approach_cells` then matches against `CARDINALS`).
- `stair_approach`-derived (2-way): `stair_approach(MAP_PASSAGE_CAVE_2F, stair_event=8,
  side='west')`, `stair_approach(MAP_PASSAGE_CAVE_2F, stair_event=8, side='east')` — side values
  are `"west"`/`"east"` only, west first (`_stair_side_candidates:189`, `for side, (nx, ny) in
  (("west", ...), ("east", ...))`).

No `resolver`/`side` pair for a **seam** crossing exists anywhere in the real corpus — CH05 has no
seam rows (README table), and `beat_gen/seam.py`'s `SeamCrossing` (its Task-3 output type) carries
`exit_cell`, `entry_cell`, `press` ("UP"/"DOWN"/"LEFT"/"RIGHT") — **no `side` or `resolver` field
at all** (`seam.py:24-32`). Task 4 has to invent both when turning a `SeamCrossing` into an
`ApproachCandidate`; nothing existing to reuse for that specific conversion.

### 5c — What the pinned tests actually require of a seam candidate's `side`

Quoting `tests/test_beat_gen_locate.py:87-94` verbatim:

```python
def test_seam_row_offers_every_crossing_as_a_candidate():
    records, _ = _locate([PlannedBeat(name="s", template="seam", map_id=1, rows=(SEAM,),
                                      group="s")])
    (rec,) = records
    assert (rec.map_constant, rec.x, rec.y) == ("MAP_ONE", 5, 0)   # first crossing
    assert [(a.x, a.y) for a in rec.approach_candidates] == [(5, 0), (6, 0)]
    assert len({a.side for a in rec.approach_candidates}) == 2    # distinguishable picks
```

The test's fake `_seam_fn` (`:52-53`) returns two crossings both with `press="UP"` and different
`exit_cell`s (`(5,0)` and `(6,0)`) — so `press` alone cannot distinguish them; whatever `side`
value Task 4's code derives has to vary with cell, not just press direction, to satisfy `len(...)
== 2`. No specific string is pinned (no `assert a.side == "..."` anywhere in the seam test), only
distinctness. The record's own cell is the **first** crossing (`SeamFn`'s return order), mirroring
"the first crossing is the record's cell" from the task file.

---

## 6. The committed `reference/routes/CH05.route.json`

### 6a — Node list (all 13 nodes)

| idx | kind | group | beats | map | cell | chosen_approach |
|---|---|---|---|---|---|---|
| 0 | entry | — | () | 35 | (19,49) | — |
| 1 | group | B1 | B1, B1_nudge, B1_in | 36 | (17,40) | None |
| 2 | group | B2 | B2, B2_spent | 36 | (11,35) | None |
| 3 | group | B3 | B3, B3_retalk1 | 36 | (19,29) | None |
| 4 | group | B5 | B5, B5_retalk1 | 36 | (7,13) | None |
| 5 | group | B4 | B4, B4_spent | 36 | (21,7) | None |
| 6 | group | B8 | B8_return, B8_nudge, B8 | 37 | (16,27) | None |
| 7 | group | B9 | B9, B9_retalk1 | 37 | (23,10) | None |
| 8 | group | B14 | B14 | 37 | (19,9) | None |
| 9 | group | B13 | B13 | 37 | (10,9) | None |
| 10 | group | B10 | B10, B10_retalk | 37 | (8,8) | None |
| 11 | group | B11 | B11 | 37 | (16,5) | None |
| 12 | exit | — | () | 37 | (16,5) | — |

**Every group node's `chosen_approach` is `None`.** `top-level: "chapter_module": "CH05"`,
`"solver": {"method": "greedy+2opt"}`.

### 6b — Why no `chosen_approach` anywhere: traced in `solver.py`

`chosen_approach` is only ever set at `solver.py:907-916`, inside the per-group node-build loop:

```python
chosen_approach: ChosenApproach | None = None
meta = candidate_meta.get(gp.group_id)
if meta is not None:
    picked = meta.get(cell)
    ...
    chosen_approach = ChosenApproach(side=picked.side, resolver=picked.resolver)
```

`candidate_meta[gp.group_id]` is only populated inside `_sites_for_group` (`:649-670`), and only
when `effective_candidates.get(gp.group_id)` is **truthy** (`:650-652`: `raw = effective_
candidates.get(gp.group_id); if not raw: return (gp.cell,)` — no `candidate_meta` entry at all in
that branch). `effective_candidates = candidates or {}` (`:644`), where `candidates` is
`solve_route`'s own `candidates=` **parameter**.

Tracing who calls `solve_route` for CH05: `routing/__main__.py plan_cmd` declares
`route_candidates: dict[...] = {}` at `:395` and only populates it inside the `if locations_opt is
not None:` branch (`:397-424`) — the `--locations` path. On the **other** branch (`:425-430`,
`module = module or chapter; chapter_obj = load_chapter(module)`), `route_candidates` is never
touched, so it reaches `solve_route(..., candidates=route_candidates)` at `:446-451` still `{}`.
`chapter_module: "CH05"` in the committed file (not some other module name) is consistent with
either path since `--module` defaults to the chapter id per the CLI docstring (`__main__.py:9-14`)
— it does **not** by itself distinguish which path ran. What does distinguish it: the file's
`rows` fields (§6c) name **hand beat ids** (`B1`, `B8_nudge`, ...) as `beats=`, which is exactly
what an **authored** `playtest/chapters/ch05.py` module registers (its own `B1`/`B8` names) — the
`--locations` path instead produces one record per `BeatLocationRecord.beat_id`, which
`chapter_from_locations` turns into a *singleton group per beat* (§1c), meaning a group like B1
(three beats: `B1`, `B1_nudge`, `B1_in`) could never appear as one three-beat group node under that
path. **So this route was solved against the authored `chapters/ch05.py` module (the `--module`
path), not the derived-locations file — despite `CH05.locations.json` also existing on disk (§2's
inconsistency note).** With `candidates={}` for every group, `_sites_for_group` returns each
group's single `_resolve_group_point` cell for every group, so `chosen_approach` can never be set
anywhere in this file, by construction — it is not a partially-solved or stale artifact, it is what
the `--module` path with the current CLI always produces.

**What this means for a warp beat needing a press direction (Task 5):** B11's node here carries no
`chosen_approach`, so nothing in this route records which side the beat was reached from — the
same is true for every other node. A downstream consumer that needs "which side was picked" (a
warp beat's press direction) cannot read it off `CH05.route.json` as committed; it would have to
come from the beat's own hand-authored `at=`/`prefer=`, or from re-solving via the `--locations`
path with `approach_candidates` populated.

### 6c — Group ids: hand B-numbers vs. generated names

Every group id in the committed route is a **hand-authored short id** (`B1`..`B14`, matching
`chapters/ch05.py`'s own registration names), not a generated name like `m036e004_trainer`. The
generated 14-group naming (§2) has **no representation anywhere in this file** — it is a property
only of what Task 2's `group.py` will produce once implemented, and Task 9 (CLI/wiring) will be
what actually re-solves a route keyed on those generated names.

---

## 7. `RouteNode` kinds and fields

`_NODE_KINDS = frozenset({"entry", "group", "exit"})` (`routing/plan.py:29`) — no other kind
exists or is validated. Full dataclass (`:101-142`):

```python
@dataclass(frozen=True)
class RouteNode:
    index: int
    kind: str                              # "entry" | "group" | "exit"
    map_id: int
    cell: Cell                             # (x, y)
    group: str | None = None
    beats: tuple[str, ...] = ()
    rows: tuple[str, ...] = ()             # manifest row_ids this group exercises
    chosen_approach: ChosenApproach | None = None
```

`__post_init__` enforces (`:112-142`): `kind` must be one of the three; a `"group"` node **must**
have non-`None` `group` and non-empty `beats`; an `"entry"`/`"exit"` node **must** have `group is
None`, `beats == ()`, and `chosen_approach is None` (raises `RoutePlanError` otherwise). CH05's
real file matches this exactly: node 0/12 (`entry`/`exit`) have `group: null, beats: []`; every
`group` node (1–11) has a non-null `group` and non-empty `beats`.

---

## 8. `order_beats` inputs — groups with >1 beat, and existing kwargs

Of the CH05 pinned 20 beats / 14 groups (§2), **6 groups have exactly 2 beats** (a main beat plus
its `_arms` beat); the remaining **8 groups have exactly 1 beat**. 6×2 + 8×1 = 20, reconciling to
the pinned beat count.

| multi-beat group | beats |
|---|---|
| `m036e002_arrival_nudge` | `m036e002_arrival_nudge`, `m036e002_arrival_nudge_arms` |
| `m036e003_item_ball` | `m036e003_item_ball`, `m036e003_item_ball_arms` |
| `m036e004_trainer` | `m036e004_trainer`, `m036e004_trainer_arms` |
| `m036e005_item_ball` | `m036e005_item_ball`, `m036e005_item_ball_arms` |
| `m036e006_trainer` | `m036e006_trainer`, `m036e006_trainer_arms` |
| `m037e004_trainer` | `m037e004_trainer`, `m037e004_trainer_arms` |

| single-beat group | beat |
|---|---|
| `m036e001_warp` | `m036e001_warp` |
| `m036e002_warp` | `m036e002_warp` |
| `m037e001_warp` | `m037e001_warp` |
| `m037e002_warp` | `m037e002_warp` |
| `m037e005p0` | `m037e005p0` |
| `m037e005p1` | `m037e005p1` |
| `m037stair11x9` | `m037stair11x9` |
| `m037stair20x9` | `m037stair20x9` |

**Concrete existing-kwarg case:** `tests/test_beat_gen_group.py:115` pins
`arms.kwarg("skip_claimed") is True` for an `_arms` beat — i.e. every `_arms` beat in this pinned
plan already carries `kwargs=make_kwargs(skip_claimed=True)` before `locate.order_beats` ever
touches it. The task file's example (`dataclasses.replace(beat, kwargs=make_kwargs(**{**dict(beat
.kwargs), "approach_prefer": side}))`) has to preserve this existing `skip_claimed=True` alongside
whatever `approach_prefer` it adds — `test_order_beats_moves_whole_groups_and_applies_picks`
(`test_beat_gen_locate.py:146-154`) pins exactly this: the `_arms` beat starts with
`skip_claimed=True` and after `order_beats` still has it (`out[2].kwarg("skip_claimed") is True`)
*plus* the new `approach_prefer` — both kwargs present, sorted (enforced by
`PlannedBeat.__post_init__`, `plan.py:125-129`).

---

## Decisions left to you

- **Seam candidate `side` labels (§5b/§5c).** Nothing existing to reuse — `SeamCrossing` has no
  `side` field, and no real-corpus example exists (CH05 has no seam rows). The synthetic test only
  requires two crossings to produce two *distinct* `side` values; it does not pin a format. `press`
  alone is not always sufficient (the test's own fake data has two crossings sharing one `press`
  value but different cells).
- **What `resolver` string to write for a seam candidate.** The existing convention (§5a/§5b) is a
  paste-able `cells.py` call for `approach_to`/`stair_approach`-derived candidates. `playtest/
  cells.py` has no seam-crossing function (per `seam.py`'s own module docstring, "the review doc
  shows the pick," implying prose-as-code is at least acceptable for other non-paste-able cases —
  see `ApproachCandidate`'s own docstring on `stair_approach`'s pre-2026-09-08 state). Whether a
  seam `resolver` string should even attempt to look paste-able, given no function exists to paste,
  is yours to decide.
- **Whether/how to surface the §2 staleness finding.** `CH05.locations.json` disagrees with a live
  `derive_locations` run on B13/B14's chosen cell, purely from stored-candidate-order drift. This
  is not a Task-4 code question, but if your `locate_beats` output gets compared against that file
  by eye during development, the mismatch is a fact about the file, not a bug in your code.
- **How to represent "which side was picked" for a warp beat's press direction (Task 5), given
  §6b's finding that the committed CH05 route has zero `chosen_approach` values anywhere.** That is
  explicitly out of Task 4's scope (Task 4 only has to write `route_order`/`order_beats` correctly
  against *whatever* a route contains, including an all-`None` one) but bears on how much Task 4's
  `order_beats` output can be trusted to carry a real pick once Task 9 wires the real solve — with
  `candidates=` unpopulated (as in the committed file), `order_beats`'s `picks` mapping will
  legitimately be empty for every group, same as `route_order`'s own real-CH05 test already pins
  (`test_route_order_real_ch05_file`: `picks == {}`).
