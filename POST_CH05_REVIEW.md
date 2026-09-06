# Post-CH05 review

**Written 2026-09-06, after CH05 passed its §9 gate and merged to `main` (`af0d8e25`).**

One document, for reading later. It covers three things:

1. **[What closed](#1-what-closed)** — CH05's gate and what the merge actually brought.
2. **[Pipeline gaps CH05 filled with a human](#2-pipeline-gaps-ch05-filled-with-a-human)** — hand-work that recurs every chapter. **Fix before anything else stages a map.**
3. **[Ordering inside the re-derivation](#3-ordering-inside-the-re-derivation)** — what's cheaper before #65's freeze than during it.

Sections 2 and 3 answer genuinely different questions and are ordered by urgency, not by
the plan's order. **§2 is the one that blocks CH06.** §3 only matters once #65 starts.

**[Decisions I need from you](#0-decisions-i-need-from-you)** is first, because that is
what a review is for.

**Provenance.** Every claim traces to `reference/archive/CH05_TODO.md` (§Deferred and
§Log), the 32 commit messages on the merged `ch05` branch, or a check against the current
tree, cited inline. Nothing is recalled from memory. Where a number is a weak estimate it
says so.

---

## 0. Decisions I need from you

| # | Decision | Why it's yours | My recommendation |
|---|---|---|---|
| D1 | **Sequence: G1/G2/G3 (§2) before CH06 or before #65?** | It reorders the agreed plan | **Before both.** They're small, mechanical, and each already cost a full debugging loop at CH05's scale. G2 decides whether CH06's first ROM has working doors. |
| D2 | **#86 — refresh the frozen-Opus differential oracle, or accept two permanent reds?** | Content call, not mechanical | Decide *before* starting any derive-and-diff. Starting from a red baseline means two failures to remember to ignore on every run. |
| D3 | **`CH05_DECISIONS.md` — archive it or keep it in root?** | No precedent; CH05 is the first chapter to have one | Archive. Its D1 coordinate-literal ban lives in the lint, not the doc. `chapters.json` cites the path, so I'd fix that citation in the same commit. |
| D4 | **Delete the `ch05` branch?** | Yours to keep or drop | Safe to delete — the merge commit preserves the history. |
| D5 | **Tier 2 batching (§2)** — worth doing alongside G1? | Scope call | Yes. Same "tell me everything missing in one run" change applied to a second table, and CH06's Gym lands several new trainer classes at once. |

---

## 1. What closed

CH05 (Passage Cave, maps 36+37) passed its §9 boot-walk gate on 2026-09-06. Chapter suite
**93/93** — 74 inherited beats replayed plus 19 of its own — on ROM `b7b470c4`. Step 9
(FIX) took nothing; the walk came back clean. `chapters.json` status is `built`,
`CH05_TODO.md` is retired to `reference/archive/`, carryovers migrated as
`PROJECT_TODO.md` #71-#86.

Post-merge verification on `main`: **2 failed, 2982 passed, 16 skipped** — identical to
pre-merge, both failures the known stale oracle (D2 above). No merge-induced breakage.

**What the merge actually brought**, beyond chapter content: two new subsystems
(`routing/locations.py`, `routing/occupancy.py`), a substantially rewritten `solver.py`
(+554, layered DP choosing group order *and* per-group approach side together), the four
archetype templates made callable for the first time, and ~2,400 lines of new tests.
`ch04.py` was also edited — its B7 was silently invalidated when maps 36/37 joined
`SLICE_MAP_IDS`, and its deferred B8 was permanently reassigned to CH05.

**Read the tally narrowly.** CH05 exercises zero seam rows, zero populated `requires[]`,
zero mart/Center/PC instances, and its only `blocked:` rows are terrain-derived Surf
rather than switch-derived. A green gate here is close to no evidence about slice 2, the
capability model, or the non-warp templates. That is precisely why #65 is next.

What it *does* validate, forward: the route solver end to end (first chapter to carry a
plan at all), all four archetype templates as callable code, and the `arrival_nudge`
idiom in a real ROM — the corpus's second-largest idiom at 324 instances across 73 maps,
and the thing STOP 5 named as most likely to misbehave. It survived.

---

## 2. Pipeline gaps CH05 filled with a human

`BUILD_PLAN.md` §2's guardrail: *the next chapter should need **data** changes, not
**code** changes.* Measured against it, CH05 needed code changes in six places, and four
were mechanical work a human did because nothing does it.

### Why this is urgent rather than tidy

Counted from the decoded map JSON (`output/uranium-build/maps/Map0NN.json`):

| | CH05 (36, 37) | CH06 (40-47) | ratio |
|---|---|---|---|
| maps | 2 | **8** | 4× |
| events | 16 | **206** | 13× |
| `code 201` (warp) commands | 4 | **41** | 10× |

Every hand-step below scales with one of those rows. CH06 is also a Gym city with a
Poké Center, a Mart and the first metro station — the first chapter to exercise the
mart/Center/PC templates at all.

*A trainer count is deliberately omitted. A crude script-scan finds ~6 for CH06 against
CH05's 3, but the heuristic is unreliable and almost certainly undercounts a Gym. The
warp and event columns are straight command-code counts and are solid.*

### G1. The three pinned lists have no completeness check — and this is filed nowhere

Four lists must move together when a chapter is added. Exactly one is guarded:

| List | Location | Validated? |
|---|---|---|
| `SLICE_MAP_IDS` | `tileset_converter/map_set.py:26` | **Yes** — `test_chapter_atlas.py:253` asserts it equals the `built`+`in_progress` set in `chapters.json` |
| `SLICE_TRAINER_BATTLES` | `trainer_converter/common.py:148` | **No** |
| `SLICE_TRAINER_PICS` | `trainer_converter/common.py:89` | **No** |
| `STARTER_SPECIES` | `species_converter/common.py:124` | **No** |

`test_trainer_battles.py` and `test_species_gate.py` check that entries which *are*
present are valid, and fail loud on bad ones. Nothing checks the lists are **complete**
for the current `SLICE_MAP_IDS`. An omission isn't caught — it surfaces later as a
transpile abort. CH05's §Log:

> "Step 1 documented only `SLICE_MAP_IDS`; three more pinned lists … were never
> mentioned. **Each omission failed separately and looked unrelated to the last, costing
> a full loop.**"

Every entry is derivable: trainers from the map events, pics from `trainertypes.dat`,
species from the parties plus evolution chains (`STARTER_SPECIES` stages whole families
only because `build_staged_species` fails loud on a dangling evolution target — itself
derivable).

**Fix:** derive the expected sets from `SLICE_MAP_IDS` and fail loud listing *everything*
missing at once. The one-at-a-time discovery is the whole cost; the lists are fine as
pinned append-only data.

### G2. `WARP_OVERRIDES` — filed as #25 since 2026-08-04, and CH05 showed the failure mode

Hand-adding four cells to `scripts/assemble_pathfinder.py` was the difference between a
working chapter and a completely inert one. Before it (`08baf280`) the player **could not
enter the Passage Cave, leave it, or use the 1F↔2F stairs.** Every warp event compiled;
none fired, because an unstamped warp tile is plain floor.

The derivation isn't unknown — the commit *states the algorithm* and then executes it by
hand: the maps' own `code 201` events, `trigger=1`, blank graphic, **excluding** the
arrival warps `_resolve_all_warp_events` mints on every destination (plain floor by
design, and they must stay that way).

#25 already prescribes the fix — "derive `WARP_OVERRIDES` from `build_slice_maps`'s
computed set instead of hand-listing it" — and notes the two sources "happen to agree
today … but nothing enforces it." CH05 is the **third** chapter to open this gate by
hand; the commit says so: *"This is the same gate CH02 and CH03 each had to open for
their own frontier."*

**CH06 has 41 warp commands against CH05's 4.** Doing this by hand a fourth time at ten
times the volume is the single most likely way CH06 boots inert.

### G3. #83 — trainer staging is all-or-nothing, which is what makes G1 catastrophic

`trainer_converter/stage.py:619-625` catches the failure, logs a WARNING, leaves
`staged_battles` empty, and **exits 0**. One unstageable trainer discards every battle in
the manifest.

Its real significance is as an amplifier. CH05's Keichi took **CH04's 17 already-good
battles down to 0**, and the damage surfaced as a **CH01** failure (`TRAINER_THEO_9/10/11`
undefined on Map050), because the transpiler walks `SLICE_MAP_IDS` in tuple order and
aborts at the first failing map.

So the observed symptom of "you forgot to pin a CH06 trainer" is **"CH01 is broken."**
Fix G1 and this is rarer; fix G3 and it's legible when it happens. Both are cheap.

### G4. #79 — no stair resolver, so stairs are hand-typed coordinates

`playtest/cells.py` has resolvers for events, approaches, warps, arrivals and entries —
and nothing for a staircase. CH05's B13 and B14 are the chapter's **only** two `raw_cell`
escape hatches (`chapters/ch05.py:548`, `:586`) purely because of this, in the first
chapter born under the zero-literal ban.

The logic already exists: `routing/locations.py`'s `_stair_approach` resolves a stair row
to the E/W neighbour owning the `stair_diagonal` edge. A port, not a discovery.

### Tier 2 — judgment stays human; the loop around it should improve

Not gaps in the above sense. A human should keep making these calls. What should change
is that the pipeline surfaces the whole list at once instead of one item per build.

- **`_CLASS_ENCOUNTER_MUSIC` / `_CLASS_PIC_INTERNAL_NAME`** (`trainer_converter/battles.py:75`, `:103`).
  CH05 added one class and justifying it took two independent fork sources
  (`constants/trainers.h:562`'s comment naming Black Belts, plus vanilla's own at
  `src/data/trainers.h:1329`). That care is correct and should not be automated. But CH06
  is a Gym — several new classes at once. `test_multiple_failures_all_reported_not_just_first`
  already exists for the battle builder; the class-mapping gate should behave the same.
- **`reference/npc_gfx_map.json`.** Choosing which fork sprite resembles a Uranium NPC is
  judgment. Already fails loud on a missing sheet (`build_object_events`) — right
  behaviour. Only wants G1-style batching.
- **`reference/warp_facing_overrides.json`.** CH05 hand-added two entries. The file's own
  comment says use it *only* where tier 3 is genuinely ambiguous. **#107** already records
  a measured second-order reachability check that resolves both CH05 cases uniquely and
  neither map33 case — so part of this is closable, and #107 is where it lives.
- **`_CHAPTER_MAP_START_CELLS`** (`generator.py:242`). Three hand entries for CH05. The
  cell must be *verified*, so a human stays in the loop — but see §3 A1: the generator
  currently **warns** rather than failing when one is missing, which is the actual defect.

### Tier 3 — correctly hand-authored; leave alone

- **`SABLEYEITE` → `ITEM_SABLENITE`** (`reference/uranium_id_map.json`). A content-fidelity
  call: same species, same mega evolution, already wired, only the display name differs.
  Exactly what a hand-maintained id map is for.
- **B11 hand-written rather than templated.** `map037/ev002` never compiles to a warp
  (Map040 out of slice), so `warp_beat` would wait forever. Correct as authored; the
  boundary convention (#72) is the general answer.

### Two workarounds that quietly became infrastructure

- **`scripts/stage_species.py` and `scripts/stage_trainers.py`** were written during CH05
  as the fast, `output/`-only half of the assembler's species and trainer passes, "for
  iterating on pinned lists without the art passes." They are now the practical way to
  work G1 — and they are **absent from `reference/guides/slice_expansion_runbook.md`**, so
  CH06 starts by not knowing they exist.
- **`_walk_unplanned_for_replay`** (`emulator.py:3035`) is scaffolding that expires when
  CH01-CH04 are re-derived, and it fired **zero** times in CH05's green run. See §3 §5;
  noted here so it isn't mistaken for load-bearing code.

---

## 3. Ordering inside the re-derivation

Only relevant once #65 + #62 parts 3-4 start.

### The test applied

#62's safeguard is *freeze the expected answers, derive, diff, then write.* It protects
against **a regression in the derivation code**. It does not protect against inputs that
legitimately changed, derivation logic already known to be wrong, or checks that pass
vacuously. So per finding: **does it change what the re-derivation produces, or weaken
your ability to tell a good diff from a bad one?**

### A1. `_CHAPTER_MAP_START_CELLS` covers only CH04 and CH05

Not filed as a numbered item; it's one clause inside #65's remediation sentence. It is the
real blocker. `generator.py:242` holds four entries. CH01 needs 8 maps, CH02 2, CH03 5.
Without one the generator does **not** fail — it warns (`generator.py:266-279`):

> "the offline reachability source was NOT consulted for this map. Terrain-gated
> capabilities (surf, waterfall) cannot appear in `requires[]` for ANY row on this map …
> an absence of requires entries here is not evidence the map has no capability gates."

Re-deriving today yields manifests that load clean, check green, and are
**capability-blind on all 15 maps**. Freeze that and the frozen expectation encodes the
blindness. This is the largest piece of genuine work in the task, and it is a
prerequisite, not a step.

### A2. #83 — trainer staging all-or-nothing

Same item as G3. A three-chapter restage reproduces it at scale while reporting success.

### A3. #75 — a vacuous check and a clean check are indistinguishable

Zero `CROSSING` lines reads identically whether the route is clean or the trigger overlay
was empty. Not hypothetical: CH05's first solve reported a clean 155-tile route, and once
object events existed the same order entered trainer sight cones in **five** places.

This is exactly the shape #62's safeguard cannot catch — a frozen expectation of "no
crossings" derived from an overlay that measured nothing looks identical to a correct
one. The project already has the right idiom (`route_model_unenforced` refuses to look
like a pass). Apply it: dispositions carry trainer rows but the overlay yields no
`TRAINER_SIGHT` tiles on those maps → fail loud (`CLAUDE.md` §4.5).

### A4. #72 + #73 — the boundary convention is a ruling with no encoding

*A boundary crossing belongs to the chapter being opened, not the one shipping* (operator,
2026-09-04). It exists in the archived TODO and two PROJECT_TODO entries — **nowhere in
code or `BUILD_PLAN.md`.** The tooling half is worse: `build_beat_model` loads a chapter's
own module plus predecessors, **never successors**, so a boundary row claimed by the
arriving chapter cannot satisfy the shipping chapter's disposition (CH04 permanently
reports `unregistered_beat` for `beat:B8`; counted debt). The re-derivation
re-dispositions three chapters, each with a forward boundary, and freezes all three
answers at once.

### A5. The unfiled one — `SLICE_MAP_IDS` grew 2.25× and nothing detects what that invalidated

**This changes the shape of the task and has no PROJECT_TODO number.** It appears only as
an *example* inside #72.

`metadata_wiring.classify_event` skips an **entire event** on any out-of-slice `code 201`.
So every warp from a gated chapter's maps into then-unbuilt territory was invisible when
that chapter's manifest was generated and its beats authored — and is live now:

| Chapter | Maps in `SLICE_MAP_IDS` when built | Today |
|---|---|---|
| CH01 | 8 | **18** |
| CH02 | 10 | **18** |
| CH03 | 15 | **18** |
| CH04 | 16 | **18** |

It has bitten twice, and only one was caught early:

- **CH03's B25** — "the north edge toward *unbuilt* Route 2 is a clean impassable wall."
  Reconciled 2026-08-26 when Route 2 was built; the author re-verified the beat's cell
  isn't one of the two seam-warp cells (`ch03.py:1407-1413`). The description string still
  says "unbuilt."
- **CH04's B7** — asserted "the player steps onto the cave mouth, no warp fires." True
  only while map 36 was unstaged. CH05 staged it, the warp went live, and crossing there
  would have teleported the player into the cave for **five downstream beats** all
  declaring `map_constant=MAP_ROUTE_02` (`ch04.py:882-890`). Found 2026-09-04, repaired
  late.

Both catches were a human noticing. The exposure isn't random — it's each gated chapter's
**forward boundary** (Moki→Route 1, Route 1→Kevlar, Kevlar→Route 2, Route 2→Cave), so it's
small and enumerable. But re-deriving three chapters at once against a grown map set
generates this class in bulk, and #62's safeguard gives no protection because the frozen
expectations would be frozen from the same stale assumption.

**Wanted before the freeze:** a check enumerating, per gated chapter, every event on its
maps carrying a `code 201` to a map that was out-of-slice at authoring time and is
in-slice now. That list is the real scope of the re-derivation, and nobody can currently
produce it.

### A6. `entry_at` is adopted by zero chapters, so beat-continuity is a corpus-wide no-op

`d673f06b` found that of **51 declared `locations[0]` values corpus-wide, 40 disagreed**
with the beat's own recorded entry position — 13 matched the end position, 27 matched
neither. The check had been "making 40 beats assert a position their author never wrote
down." The fix was correct: a new opt-in `Beat.entry_at`.

Verified against the tree: `grep -c entry_at` over `ch01.py` … `ch05.py` returns **0 for
all five**. Nobody opted in, including CH05. `_check_beat_continuity` enforces nothing
anywhere today. Defensible as transitional — but the re-derivation is the moment to adopt
it, and if beats are re-authored without it the opportunity is gone.

### Tier B — cheap, and they make the loop trustworthy

- **#86** (D2 above) — decide before starting, not during.
- **#74** — ROUTE runs before object events exist. Only bites if the re-derivation also
  gives chapters route plans; #67 says CH04 is explicitly *not* reopened, so it may not
  apply. If any chapter gets a plan, fix first (same root as A3).
- **#76** — `destination_scripts` is per-solve, not per-segment. Same conditional. A
  trainer's own sight cone is still a foreign hazard on the segment walking to it.
- **#79** — the stair resolver (G4). CH02's Map033 carries sideways staircases, so
  re-authoring CH02's beats without it means new `raw_cell` debt in the chapter with the
  largest budget.

### Tier C — does not block

`#71`, `#77`, `#78`, `#80`, `#81`, `#82`, `#84`, `#85`. Of these `#71`, `#82` and `#85`
are pure `BUILD_PLAN.md` edits costing minutes — worth batching into one doc commit
whenever, but they change nothing about the derivation.

### Obligations the re-derivation inherits

**Not defects, not in #71-#86.** Things CH05 deferred *to* this work. Missing them means
doing the re-derivation twice.

- **Delete `_walk_unplanned_for_replay`.** `c2daf169` reinstated a greedy-walk fallback for
  CH01-CH04's replayed beats because *"CH01-CH04's beats were authored while
  `_route_waypoints` degraded to an unprotected greedy walk on every planning failure.
  Their declared coordinates have therefore never been held to a strict planner."* Scoped
  to `INHERITED` beats, recorded via `KIND_REPLAY_FALLBACK` (`emulator.py:3035`,
  `contradictions.py:79`). The commit says it **expires by construction**. It fired **zero
  times** in CH05's green run (`0a9d276c`) — scaffolding that has never caught anything.
- **Fix `ch04.py`'s `_press_a_live` fixed-facing bug, and replace CH02/CH03's
  hand-transcribed local-id literals with `cells.local_id`.** `a38a1812` names both:
  *"Those two existing copies are left alone: they belong to chapters that have not been
  re-derived yet."* A written IOU addressed to this task.
- **Pay down the 123 coordinate literals.** `_PRE_BAN_BUDGET`
  (`tests/test_chapter_coordinate_literals.py:95`): ch01 **13**, ch02 **45**, ch03 **42**,
  ch04 **23**. The ratchet checks only the *count*, never whether a given literal is still
  correct. If a re-derived row moves a cell, nothing connects that to the hardcoded
  literal — it won't fail loud, it'll be quietly wrong. CH05 was born at zero and proved
  the resolvers suffice for a whole chapter.
- **CH05's B1 still doesn't exercise CH04's arrival-nudge autorun on the Route 2 side**
  (`map035/ev001/p1`, a row CH04 owns) — `d390e59f`'s admitted residual. The re-derivation
  is when that row gets an owner.
- **`resolved_trigger_scripts` approximates "resolved" as "the beat passed"**
  (`a460e823`) — holds for latching shapes, not for a TEMP-switch page that re-arms on map
  re-entry. Documented, not fixed. Worth knowing before trusting the oracle across three
  chapters.

---

## 4. Suggested order

1. **D2** — settle the oracle so the baseline is unambiguous.
2. **G1, G2, G3** (§2) — before CH06 *and* before #65. Small, mechanical, each already
   cost a loop.
3. **G4 / #79** — before whichever comes first of CH06 or re-authoring CH02's beats.
4. **A3 (#75)** — fail loud on a vacuous overlay; a guard on the process itself.
5. **Build the A5 detector and run it.** Its output is the actual scope of #65 and does
   not exist yet.
6. **Encode A4 (#72), fix #73** so boundary ownership is derived, not decided ad hoc.
7. **Derive the CH01-CH03 start cells (A1).** The bulk of the work.
8. *Then* freeze, derive, diff, write — adopting `entry_at` (A6) and discharging the
   inherited obligations as you go.

Steps 1-6 are small. Step 7 is the real work and is a prerequisite either way. The
argument is that doing 1-6 first costs little and converts step 8 from a diff nobody can
read into one that means something.

---

## 5. What this document is not

It is not a claim that #65 is the wrong next task — it is the right one, and CH05's gate
being weak evidence is exactly why. §3 is about **ordering within it**. §2 is a separate
and more urgent claim: four pieces of recurring hand-work that block CH06 regardless of
what happens with #65.
