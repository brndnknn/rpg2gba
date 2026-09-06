# Pre-re-derivation audit — what CH05 found that should land before #65

**Written 2026-09-06, immediately after CH05's §9 gate pass and merge (`af0d8e25`).**

**The question this answers:** the plan says the next task is `PROJECT_TODO.md` #65 +
#62 parts 3-4 — regenerate CH01-CH03's manifests, re-migrate their dispositions, and
re-derive the corpus. Is there work CH05 discovered that is cheaper to do *before* that,
rather than during or after?

**The answer: yes, and one finding changes the shape of the task rather than just its
order.** Six items should land first. The rest can follow. There is also a set of
obligations the re-derivation *inherits* — things CH05 deliberately left for it, which
are not defects and are not in the #71-#86 list, but which the work must do or it will
have to be done twice.

**Sources.** Every claim below traces to `reference/archive/CH05_TODO.md` (§Deferred and
§Log), the 32 commit messages on the merged `ch05` branch, or a check against the current
tree, cited inline. Nothing here is recalled from memory.

---

## 1. The test I applied

`#62`'s ordering safeguard is *freeze the expected answers, derive, diff, then write* —
never derive-and-write in one pass, or a regression in the derivation logic reads as a
correct re-disposition.

That safeguard is good, and it is narrower than it looks. It protects against **a
regression in the derivation code**. It does not protect against:

- **inputs that legitimately changed** since the chapters were built — the diff is real,
  large, and you cannot separate signal from noise;
- **derivation logic already known to be wrong** — you would be freezing expectations
  produced by code you have already filed a bug against;
- **checks that pass vacuously** — a clean diff means nothing if the check measures
  nothing.

So the question for each CH05 finding is not "is it important?" but:

> **Does it change what the re-derivation produces, or does it weaken your ability to
> tell a good diff from a bad one?**

If yes, it belongs before the freeze. If no, it can wait.

---

## 2. Tier A — must land before the freeze

### A1. `_CHAPTER_MAP_START_CELLS` covers only CH04 and CH05 — 15 maps have no verified start cell

Not filed as a numbered item anywhere; it is buried in #65's remediation sentence. It is
the actual blocker.

`generator.py:242` currently holds four entries: `("CH04", 35)`, and CH05's three. CH01
needs 8 maps, CH02 2, CH03 5. Without a verified start cell for a map, the generator does
**not** fail — it logs a warning and carries on (`generator.py:266-279`), and the warning
says exactly what goes wrong:

> "the offline reachability source was NOT consulted for this map. Terrain-gated
> capabilities (surf, waterfall) cannot appear in `requires[]` for ANY row on this map as
> a result … an absence of requires entries here is not evidence the map has no
> capability gates."

Re-deriving CH01-CH03 today therefore produces manifests that are schema-valid, load
cleanly, check green — and are **capability-blind on all 15 maps**. Freeze that and the
frozen expectation encodes the blindness. Every later capability audit diffs against a
baseline that was never measured.

**Do first:** derive and verify a start cell per (chapter, map) for CH01-CH03. This is
the single largest piece of genuine work in the whole task and it is a prerequisite, not
a step.

### A2. #83 — trainer battle staging is all-or-nothing, and the damage surfaces in the wrong chapter

`trainer_converter/stage.py:619-625` catches `build_staged_battles`' failure, logs a
WARNING, leaves `staged_battles` empty, and exits 0. One unstageable trainer discards
**every** battle in the manifest.

This already happened during CH05 and it is the exact failure mode a multi-chapter
re-derivation will reproduce at scale: CH05's Keichi took **CH04's 17 already-good
battles down to 0**, and the damage surfaced as a **CH01** failure (`TRAINER_THEO_9/10/11`
undefined on Map050), because the transpiler walks `SLICE_MAP_IDS` in tuple order and
aborts at the first map that fails.

A re-derivation across three chapters restages all of them. With this bug in place, a
single bad trainer anywhere produces a red in a chapter that has nothing to do with it,
while the run reports success. That is not merely a bug to fix later — it makes the
derive/diff loop actively misleading to debug.

**It is also the cheapest high-value fix in this list.** The pic half legitimately stands
alone; the battle half should stage per-trainer or abort.

### A3. #75 — a vacuous check and a clean check are indistinguishable

Zero `CROSSING` lines reads identically whether the route is genuinely clean or the
trigger overlay was empty. CH05 proved this is not hypothetical: its first solve reported
a clean 155-tile route, and after object events actually existed the same order was found
to enter trainer sight cones in **five** places.

This is precisely the shape #62's safeguard is meant to catch and structurally cannot: a
frozen expectation of "no crossings" derived from an overlay that measured nothing looks
identical to a correct one.

The project already has the right idiom — `route_model_unenforced` refuses to look like a
pass. Apply it here: if a chapter's dispositions carry trainer rows but the overlay yields
no `TRAINER_SIGHT` tiles on those maps, fail loud (`CLAUDE.md` §4.5).

### A4. #72 + #73 — the boundary convention is a ruling with no encoding, and three boundaries go live at once

Operator ruling 2026-09-04: *a boundary crossing belongs to the chapter being opened, not
the one shipping.* It exists in `reference/archive/CH05_TODO.md` and in two PROJECT_TODO
entries. It exists **nowhere in code or in `BUILD_PLAN.md`.**

The tooling half (#73) is worse: `build_beat_model` loads a chapter's own module plus its
predecessors, **never its successors**. So a boundary row claimed by the arriving chapter
cannot satisfy the shipping chapter's disposition — CH04 permanently reports
`unregistered_beat` for its `beat:B8` and that is counted debt, not a bug to chase.

The re-derivation re-dispositions CH01, CH02 and CH03 — each of which has a forward
boundary. Without the convention encoded, the derivation assigns boundary-row ownership
by whatever the code happens to do, and you freeze that answer for all three at once.

### A5. The unfiled one — `SLICE_MAP_IDS` grew 2.25× and nothing detects what that invalidated

**This is the finding that changes the shape of the task, and it has no PROJECT_TODO
number.** It appears only as an *example* inside #72.

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
  Reconciled 2026-08-26 when Route 2 was built; the author re-verified that the beat's
  cell is not one of the two seam-warp cells (`ch03.py:1407-1413`). The beat's own
  description string still says "unbuilt."
- **CH04's B7** — asserted "the player steps onto the cave mouth, no warp fires." True
  only while map 36 was unstaged. CH05 staged it; the warp went live; crossing there
  would have teleported the player into the cave for **five downstream beats** that all
  declare `map_constant=MAP_ROUTE_02` (`ch04.py:882-890`). Found 2026-09-04, repaired late.

Both catches were a human noticing. The exposure is not random — it is each gated
chapter's **forward boundary** (Moki→Route 1, Route 1→Kevlar, Kevlar→Route 2,
Route 2→Cave), so it is small and enumerable. But re-deriving three chapters at once
against a grown map set is exactly the condition that generates this class in bulk, and
#62's safeguard gives no protection because the frozen expectations would be frozen from
the same stale assumption.

**Wanted before the freeze:** a check that enumerates, per gated chapter, every event on
its maps carrying a `code 201` to a map that was out-of-slice at authoring time and is
in-slice now. That list is the real work item of the re-derivation, and right now nobody
can produce it.

### A6. `entry_at` is adopted by zero chapters, so beat-continuity is a corpus-wide no-op

`d673f06b` found that of **51 declared `locations[0]` values corpus-wide, 40 disagreed**
with the beat's own recorded entry position — 13 matched the end position, 27 matched
neither. The check had been "making 40 beats assert a position their author never wrote
down." The fix was correct: a new opt-in `Beat.entry_at` field, so continuity is checked
only where a beat actually claims a position.

Verified against the current tree: `grep -c entry_at` over `ch01.py` … `ch05.py` returns
**0 for all five**. Nobody opted in, including CH05. `_check_beat_continuity` therefore
enforces nothing anywhere today.

That is defensible as a transitional state, but it means the re-derivation is the moment
to adopt it — and if the beats are re-authored without it, the opportunity is gone and
the field stays dead weight.

---

## 3. Tier B — cheap, and they make the loop trustworthy

- **#86 — the frozen-Opus oracle is stale.** Two permanently red tests
  (`test_deterministic.py`). You are about to run a large derive-and-diff; starting from
  a red suite means every subsequent run has two failures you have to remember to ignore.
  Refreshing the oracle is an operator content call, which is why this is Tier B and not
  Tier A — but decide it before starting, not during.
- **#74 — ROUTE runs before object events exist.** Only bites if the re-derivation also
  gives chapters route plans. #67 says CH04 is explicitly *not* reopened for this, so it
  may not apply. If any chapter gets a plan, this must be fixed first or the plan is
  solved against a vacuous overlay (same root as A3).
- **#76 — `destination_scripts` is per-solve, not per-segment.** Same conditional: only
  matters if re-routing. A trainer's own sight cone is still a foreign hazard on the
  segment walking to that trainer.
- **#79 — no stair resolver in `cells.py`.** CH02's Map033 carries sideways staircases
  (the 2026-08-07 boot-walk finding). Re-authoring CH02's beats without a resolver means
  new `raw_cell` debt in a chapter that already has the largest budget. The logic exists
  — `routing/locations.py`'s `_stair_approach` — so this is a port, not a discovery.

---

## 4. Tier C — does not block; do them whenever

`#71` (ART step has no owning command), `#77` (`routing locations --check`), `#78`
(`RULE_ROUTE_APPROACH` blind spot), `#80` (`find_match` single `(map, event)` key), `#81`
(warp beat has no proof it crossed), `#82` (visual route gate), `#84` (`ITEM_TM76` sanity
check), `#85` (boot-walk seeding recipe).

`#71`, `#82` and `#85` are pure `BUILD_PLAN.md` edits and cost minutes — worth batching
into one doc commit at any point, but they change nothing about the derivation.

---

## 5. Obligations the re-derivation inherits

These are **not defects and not in #71-#86.** They are things CH05 explicitly deferred
*to* this work. Missing them means doing the re-derivation twice.

- **Delete `_walk_unplanned_for_replay`.** `c2daf169` reinstated a greedy-walk fallback
  for CH01-CH04's replayed beats, because *"CH01-CH04's beats were authored while
  `_route_waypoints` degraded to an unprotected greedy walk on every planning failure.
  Their declared coordinates have therefore never been held to a strict planner."* It is
  scoped to `INHERITED` beats only and recorded via `KIND_REPLAY_FALLBACK`
  (`emulator.py:3035`, `contradictions.py:79`). The commit states it **expires by
  construction**: once CH01-CH04 have been through the new beat pipeline it is dead code
  to delete. Note it fired **zero times** in CH05's green run (`0a9d276c`) — the warp
  filter was the whole fix — so it is scaffolding that has never caught anything.
- **Fix `ch04.py`'s `_press_a_live` fixed-facing bug, and replace CH02/CH03's
  hand-transcribed local-id literals with `cells.local_id`.** `a38a1812` names both and
  says explicitly: *"Those two existing copies are left alone: they belong to chapters
  that have not been re-derived yet."* This is a written IOU addressed to this task.
- **Pay down the 123 coordinate literals.** `_PRE_BAN_BUDGET`
  (`tests/test_chapter_coordinate_literals.py:95`): ch01 **13**, ch02 **45**, ch03 **42**,
  ch04 **23**. The ratchet only checks the *count*; it cannot tell whether any given
  literal is still correct. If a re-derived row moves a cell, nothing connects that fact
  to the hardcoded literal — it will not fail loud, it will be quietly wrong. CH05 was
  born at zero and proved the resolvers are sufficient for a whole chapter.
- **CH05's B1 still does not exercise CH04's arrival-nudge autorun on the Route 2 side**
  (`map035/ev001/p1`, a row CH04 owns) — `d390e59f`'s admitted residual. The
  re-derivation is when that row gets an owner.
- **`resolved_trigger_scripts` approximates "resolved" as "the beat passed"**
  (`a460e823`) — holds for latching shapes, not for a TEMP-switch page that re-arms on
  map re-entry. Documented, not fixed. Worth knowing before trusting the oracle across
  three chapters.

---

## 6. Recommended sequence

1. **Decide #86** (refresh the frozen-Opus oracle or accept two known reds) so the
   baseline is unambiguous.
2. **Fix #83** — trainer staging per-trainer-or-abort. Smallest fix, largest effect on
   how debuggable everything after it is.
3. **Fix #75** — fail loud on a vacuous overlay. This is a guard on the process itself.
4. **Build the A5 detector** and run it. Its output — the per-chapter list of newly-live
   boundary events — is the actual scope of the re-derivation, and it does not exist yet.
5. **Encode #72, fix #73** so boundary ownership is derived, not decided ad hoc.
6. **Derive the CH01-CH03 start cells (A1).** The bulk of the work.
7. *Then* freeze, derive, diff, write — with #79 in hand if CH02's stairs are touched,
   adopting `entry_at` (A6), and discharging §5's inherited obligations as you go.

Steps 1-5 are small. Step 6 is the real work and is a prerequisite either way. The
argument of this document is that doing 1-5 first costs little and converts step 7 from
a diff nobody can read into one that means something.

---

## 7. What this document is not

It is not a claim that #65 is the wrong next task — it is the right one, and CH05's gate
being weak evidence (zero seam rows, zero populated `requires[]`, zero mart/Center/PC
instances, terrain-derived rather than switch-derived `blocked:` rows) is exactly why.
It is a claim about **ordering within it**, and about six specific things that are
cheaper now than later.
