# Iterative Conversion Roadmap — the "step-and-expand" restructure

**Status:** proposal / draft — not yet roadmap-ratified.
**Date:** 2026-06-13.
**Relationship to existing docs:** This proposes re-sequencing the *conversion
campaign* (Phases 4/5/6) from the linear "finish the Phase-4 bulk run, then do 5,
then 6" order into an interleaved ratchet. It builds directly on
`DETERMINISTIC_EXPANSION_STRATEGY.md` (the *what* — widen the deterministic
surface) and turns it into a *how* (the operating loop). `ROADMAP.md` stays
authoritative until/unless the operator ratifies this; nothing here changes the
frozen §9 calibration config.

**The one-line pitch:** Stop treating the bulk run as a 3-month background daemon
you wait on. Treat it as a tool you fire in **bounded steps**, and between steps do
the Phase-5/6 work and classifier work that shrinks the next step. The Opus tail
ratchets down each cycle; you only ever spend budget on what is *irreducible at
that moment*.

---

## 1. The core idea: a ratchet, not a daemon

The old plan and the new plan converge to the same finished ROM. They differ in
**order**, and order changes both cost and risk.

| | Linear (old) | Iterative (proposed) |
|---|---|---|
| Bulk run | one long continuous grind, ~3 months | many bounded steps (`--limit N` / one `--timed` window) |
| 5 & 6 work | starts after bulk completes | happens *between* steps, feeding the next one |
| Integration test | once, at the end | incrementally, every step |
| Opus spend | pays for events 5/6 would later make free | only the residue that is genuinely irreducible *now* |
| Operator experience | set it and wait | always an active build front |

**One step =**
1. *expand* the free (deterministic) surface — add/upgrade classifiers, and do
   whatever Phase-5 wiring or Phase-6 engine work those classifiers depend on;
2. *validate* the expansion against the frozen-Opus oracle already on disk;
3. *re-measure* with `scripts/idiom_frequency.py` and confirm the free-fraction
   climbed;
4. *take a bounded bulk step* against the shrunken tail (which also grows the
   oracle for the next step's validation);
5. *assemble-and-smoke* the newly converted maps so systematic defects surface
   early;
6. *record* (MEMORY + tracker) and commit; then loop.

The bulk run is step 4 of the loop — never the whole game.

---

## 2. Why this order (the dependency rationale)

Two facts make interleaving strictly better than linear, not just more engaging:

**2.1 Phases 5 and 6 unblock Phase 4's deterministic surface.** The deterministic
classifiers that would claim the biggest Opus-bound clusters depend on artifacts
that only exist *after* 5/6 work:

- **Move-route / door-transition idioms** (~240 door events + 1,191 events
  touching code 209) resolve their targets to pokeemerald *local object ids*,
  which are assigned only during Phase-5 map wiring (the 2026-06-03 deferral).
- **Field mechanics** (bridge, rock-smash, boulder, stairs, berry, cave-exit)
  become a one-line classifier *only after* the Phase-6 engine macro they emit
  exists.

So the linear order pays Opus to convert events that doing 5/6 first would have
made free. Reversing the dependency — let 5 and 6 *inform* 4's classifiers — keeps
the bulk run on the truly irreducible tail.

**2.2 Linear defers all integration risk to month 3 — and that has already bitten
us.** Bug F1 (name-derived script labels colliding) was invisible to every
per-event gate and only `make modern` caught it. Grind the bulk for 3 months and
*then* assemble, and a systematic `.pory` defect is baked into 199 maps before
anyone tries to build them. Incremental assembly (step 5 of the loop) surfaces
such defects at map 12, not map 199. This *serves* the §9-gate philosophy (catch
systematic error cheap-early), it does not bypass it.

**Live baseline (2026-06-13, `idiom_frequency.py`):** 3,581 non-empty events —
**1,046 free (29%)**, **2,535 to Opus**, 296 of those in the hand-convert lane.
Every step's job is to move events leftward across that 29% line.

---

## 3. Invariants that make iteration safe

These hold for the entire campaign. They are what let us change the deterministic
surface repeatedly without corrupting a months-long run.

1. **The §9-frozen config never changes.** Model = `claude-opus-4-8`, system prompt
   = `system.md` @ `03dda3f`, for the whole campaign. The memo fingerprint is the
   system prompt, so hand-, Opus-, and deterministic-seeded entries all share one
   memo. Classifiers live *before* the LLM in `_convert_event`, so adding them
   never touches the frozen config.
2. **Surface changes happen between steps, never mid-step.** Classifier, STRIP,
   and engine edits land while the bulk run is stopped. `run_bulk.py --timed`
   stops cleanly at per-map/per-CE checkpoints, so this is just "let the current
   step finish, then edit, then start the next step." Never hot-patch a live round.
3. **Memoization is one-directional — so front-load.** A new classifier claims only
   events the bulk has **not yet reached**. It does *not* refund events Opus already
   converted (those are memoized at Opus's output). Therefore the ROI of a
   classifier decays as the bulk progresses: build the high-count cheap ones
   *before* the bulk reaches their events. Corollary: **do not resume the bulk
   until Track-A group 1 is in** (§6).
4. **Every new classifier is differentially validated before it is trusted.**
   The frozen-Opus oracle (`memo_manifest.json` + per-map `.pory`) is already on
   disk and *grows every step*. Per classifier: collect its claimed events,
   intersect with events Opus already converted, diff the normalized Poryscript +
   `unhandled[]` (whitespace/labels/registry-names normalized → must be
   byte-identical). Mismatch ⇒ classifier bug (fix) or Opus inconsistency
   (deterministic becomes canonical + a recorded §10 fidelity decision). Ships as a
   pytest per classifier. This is the semantic net; the compile-gate is the syntax
   net. (Strategy doc §7.)
5. **Fail-loud and the compile-gate still stand.** A script-call with real effect
   is queued UNHANDLED, never silently STRIPped. A classifier whose output fails
   the compile-gate falls through to Opus — a wrong guess costs nothing.
6. **Every step leaves the tree shippable.** Full pytest green (incl. the `phase4`
   marker), the fork builds (`make -j modern`) if any C changed, MEMORY + tracker
   updated, one logical commit per classifier/feature.
7. **The §9 manual gates are unchanged.** End-of-Phase-2 (passed), end-of-Phase-4
   calibration (passed), end-of-Phase-7 playthrough still gate as written.

---

## 4. The repeating step (operational checklist)

Each iteration of the loop runs this checklist. It is deliberately mechanical so
it survives context resets and stays the same whether the step's expansion is a
classifier, a Phase-5 wiring change, or a Phase-6 engine macro.

```
STEP N
─ 1. MEASURE
     • run scripts/idiom_frequency.py; snapshot free%, Opus count, top signatures
     • diff against last step's snapshot (record the delta in the tracker)
─ 2. PICK TARGET  (decision rule in §8)
     • choose the highest leverage = (events_unblocked × spawns_saved) / build_effort
     • prefer: Track A (no C) > Phase-5-unblocked > Phase-6-unblocked
     • confirm any required fidelity call (§10) is already settled; if not, stop
       and surface it — do not guess
─ 3. BUILD THE UNBLOCK
     • classifier in deterministic.py (pure fn, never raises, appended to
       _CLASSIFIERS), and/or
     • Phase-5 wiring (map_constants / local-id assignment / collision …), and/or
     • Phase-6 engine macro in the fork (+ the classifier that emits it)
─ 4. VALIDATE
     • differential test vs frozen-Opus oracle (invariant 4) — new pytest
     • compile-gate over the claimed events
     • full pytest incl. phase4 marker
     • if C changed: cd $RPG2GBA_POKEEMERALD && make -j modern  (clean)
─ 5. RE-MEASURE
     • re-run idiom_frequency.py; confirm free% climbed by ~the expected count
     • if it didn't, the classifier's structural guard is too tight (or the count
       was an upper-bound mirage) — investigate before proceeding
─ 6. BULK STEP  (only if budget available and a tail remains)
     • run_bulk.py --limit N   (bounded; resumable; default model unchanged)
     • this converts a slice of the shrunken tail AND grows the oracle
─ 7. ASSEMBLE + SMOKE  (incremental)
     • assemble the maps converted so far → .inc + support headers, make modern
     • cluster any errors; a systematic .pory defect must surface here, not at
       map 199 (the F1 lesson)
─ 8. RECORD
     • update MEMORY (Current Phase + any Key File Note), tick the tracker
     • commit (one logical commit); note free% before/after in the message
LOOP → STEP N+1
```

Not every step needs all of 6–7 (e.g. a pure Track-A step may skip the bulk slice
and just bank the free events for the next resume). The fixed parts are
MEASURE → BUILD → VALIDATE → RE-MEASURE → RECORD.

---

## 5. The three tracks (plus a zero-spend fourth)

Work is organized into tracks by *what unblocks it*, not by phase number. Steps
draw from whichever track has the best-leverage target available.

- **Track A — Deterministic expansion (no C, no Phase-5 dep).** New classifiers +
  STRIP entries in `deterministic.py`. Cheapest, fastest, highest immediate ROI.
  Run this track *first and continuously*.
- **Track B — Phase-5 map assembly.** Tiles → `map_constants.py` →
  collision/connections → local-object-id assignment → incremental assembly smoke.
  Unblocks the warp/move-route/door classifiers in Track A *and* provides step-7
  integration testing. The single biggest enabler.
- **Track C — Phase-6 engine.** Fork C for field mechanics + Nuclear type +
  abilities/effects. Reordered from the roadmap's order to *events-unblocked-first*.
  Most expensive track; each item is gated on a per-mechanic fidelity call (§10).
- **Track D — Hand-convert lane (optional, zero spend).** The existing
  `run_human.py` machinery. For genuinely one-off events no classifier justifies.
  Folds into the ratchet: a Track-A classifier that claims an in-lane idiom (e.g.
  the 230-gate) *also* shrinks Track D, so the human is never asked to hand-grind a
  repeating idiom.

---

## 6. Prioritized backlog (the actual step sequence)

Ordered by leverage. Counts are the live `idiom_frequency.py` upper bounds
(distinct command-set signatures / call-occurrence among Opus-bound events) — the
classifier must still verify structure, so realistic reclaim runs lower (cf.
Classifier 1: 620 upper → 372 actual). Each block is roughly one or more steps.

### Group 1 — Track A, no dependencies (do BEFORE resuming the bulk)
The reason the bulk stays paused at 7/199 until this lands (invariant 3).

| Target | Signature / call | Upper bound | Notes |
|---|---|---|---|
| **Self-switch gate** | `{111, 123, 411, 412}` | **230** | The #1 lever. **Validate first:** signature has *no* 101 text — some may be autorun/parallel state-machines, not the talk-once idiom. Drill the 111 condition-type before trusting; classifier claims only events whose 111 is a self-switch check. Also the bulk of the 296-event hand lane → shrinks Track D too. |
| Shop / PC / heal | `pbPokemonMart` (18 clean), `pbPokeCenterPC` (17 clean), `pbSetPokemonCenter` (60) | ~120 | Native pokeemerald macros (`pokemart`, `…PC`, heal). Clean single-call signatures are near-free. |
| Give-item | `item` (38) + `pbReceiveItem` (16) | ~54 | `giveitem`. Needs the symbol→`ITEM_*` map (Phase-2 `item_field_codes.json`); unknown symbol ⇒ fall through. |
| Show-map sign | `{101, pbShowMap}` | 18 | Single clean signature. |

### Group 2 — Track B foundation (unblocks the biggest Track-A clusters)
Build enough Phase-5 wiring to (a) emit real `MAP_*` constants and (b) assign
local object ids. This is the gate for everything move-route/warp/door.

- `tile_map.py` → `map_constants.py` (consults `map_name_overrides.json` first).
- Collision + connections + spawn/heal-spot landing points.
- Local-object-id assignment convention (the move-route blocker).
- Stand up the persistent assembly smoke worktree (critique #4) for step-7.

### Group 3 — Track A, post-Track-B (move/warp/door)
| Target | Signature | Upper bound | Notes |
|---|---|---|---|
| **Door transition** | `{106,111,201,208,209,210,223,…,setTempSwitchOn}` | ~240 | Biggest single lever; needs local ids (Group 2). One engine-light classifier collapses the family (the 119 + 51 + 26 + 24 variants). |
| Pure move-route | `{209, 210, 509}` | 89 | Gated on **Q3** (is RMXP move-cmd → `applymovement` deterministic?). Player-only subset (~45% per 06-03 census) is reclaimable first. |
| Simple-warp resolve | `201` clusters | (already 304 claimed by C4) | C4 emits `MAP_URANIUM_<N>` placeholders; Group 2 turns them into real constants. Plus **Q2** double-warp-bounce call. |

### Group 4 — Track C, field mechanics (engine + classifier pairs, by frequency)
Each is one Phase-6 macro + one classifier, gated on a per-mechanic fidelity call
(**Q4**). Ordered by event count:

| Mechanic | Call | Upper bound | Clean-signature today |
|---|---|---|---|
| Bridge | `pbBridgeOn` / `pbBridgeOff` | 41 + 24 | **Yes** — `{script:pbBridgeOn}` (35) / `{script:pbBridgeOff}` (21) are bare single-call signatures. Cheapest Track-C win. |
| Rock smash | `pbRockSmashRandomEncounter` | 65 | Mixed with 111/209/item — needs more structural work. |
| Stairs | (109/209 family) | 61 + 43 + 18 | Move-route-coupled (Group 2 dep). |
| Berry plant | `pbBerryPlant` | 53 | `{111,123,412,pbBerryPlant}` — needs berry-tree engine state. |
| Cave exit / entrance | `pbCaveExit` / `pbCaveEntrance` | 51 + 47 | Escape-point + Flash; real effect (fail-loud, not STRIP). Door-family adjacent. |
| Strength boulder | `{111,250,412}` "Boulder" | 51 | Native pokeemerald strength-boulder support exists — may be Track-A-after-mapping, not new C. |

### Group 5 — the irreducible Opus tail (what the bulk was always for)
Branch-heavy story logic (`111` blocks 1,628 events; `122` Control Variables 412;
`121` Control Switches 246; `102/402/404` choices 219). Conditions vary per event
⇒ genuine judgement. **Do not chase deterministically.** The bulk run's bounded
steps clear this, and it is *all that should remain* by the time Groups 1–4 land.

---

## 7. The spend model (why front-loading matters)

The bulk run's cost is one Opus spawn per event it reaches that the deterministic
pre-filter did not already claim. Two consequences govern sequencing:

- **A classifier built before the bulk reaches its events saves a spawn each;
  built after, it saves zero** (those events are already Opus-converted and
  memoized — no refund). So a classifier's budget value is proportional to *how
  many of its events are still unreached*. The 230-gate built now (bulk at 7/199)
  saves ≈230 spawns; built after a full grind it saves 0.
- **Re-running after a classifier batch is free and correct at residue scope.**
  Memoization means already-converted events never re-hit Opus, so you re-run only
  the residue — no double spend, no need to re-validate the whole corpus for
  budget (you re-validate for *correctness* via the differential test, which is
  free).

Practical rule: **the campaign's first move is Track-A Group 1 with the bulk
paused.** Every step after that interleaves a bounded bulk slice with the next
expansion, so the tail the bulk pays for only ever gets smaller.

A rough envelope (illustrative, not a commitment): Groups 1–4 plausibly move
~700–1,000 events left of the 29% line (heavily discounted from the ~1,100 upper
bound for structural-verification shrinkage). That would cut the Opus tail from
~2,535 toward ~1,500–1,800 — and that residue is exactly the Group-5 story logic
that needs judgement anyway. Wall-time savings are real but secondary; the primary
wins are *spawns not spent on determinizable work* and *integration risk retired
continuously*.

---

## 8. Decision rule: is this step worth building?

Build the unblock when **all** hold; otherwise leave the events for the Opus tail:

1. **Leverage clears the bar:** `events_unblocked × spawns_saved_each` materially
   exceeds build effort. (A 230-event classifier: yes. A 3-event one-off: use
   Track D or let Opus take it.)
2. **Structure is verifiable deterministically** — the classifier can *prove* the
   match, not merely recognize the command set. If the idiom's meaning varies with
   a branch condition or a global variable, it is Group-5 judgement, not a
   classifier.
3. **It passes the differential test** vs the frozen-Opus oracle (invariant 4), or
   — where there is no oracle yet — a one-time targeted calibration pass settles
   the canonical output.
4. **Any fidelity call it requires (§10) is already decided.** Never guess a
   replicate/substitute/strip decision to unblock a classifier; surface it and
   wait. (The `MSGBOX_SIGN` near-miss is the cautionary tale: a plausible guess
   that the oracle later contradicted.)
5. **For Track C only:** the engine macro is worth the C — i.e. the mechanic is
   CONVERT/ADAPT, not STRIP, and replicating it now beats stubbing it for a Phase-8
   ADAPT. (Several field mechanics may rationally be *stubbed now, ADAPTed later* —
   see Q5.)

If a target fails the bar, it is not a failure — it is correctly assigned to the
Opus tail, which is what the bulk run is for.

---

## 9. Open questions (need operator input)

Restructure-specific decisions first, then the carry-forwards from
`DETERMINISTIC_EXPANSION_STRATEGY.md §8`.

**New to this restructure:**

- **OQ-R1 — Ratify or shadow?** Do we amend `ROADMAP.md`'s 4→5→6 sequencing to
  this ratchet, or keep this as a parallel proposal doc and treat the 5/6 work as
  "scoped exceptions pulled forward"? (Ratifying is cleaner for the tracker;
  shadowing is lower-ceremony.)
- **OQ-R2 — How big is a step?** A fixed `--limit N` (e.g. 100 events), one
  `--timed` window, or "until the next classifier is ready"? This sets the rhythm
  and how often you context-switch between bulk-watching and building.
- **OQ-R3 — Gate the first bulk resume on Group 1?** Recommended **yes** (invariant
  3 — front-loading). Confirm you're OK leaving the bulk paused at 7/199 until the
  230-gate + shop/PC/heal + give-item classifiers land and validate.
- **OQ-R4 — How much Phase-6 C do we actually want during the campaign?** This is
  the biggest scoping call. Track C is the expensive track. Option (a) build the
  high-frequency field-mechanic engines now (bridge, cave-exit) to determinize
  ~200 events; option (b) **stub/substitute them now and defer real engine work to
  Phase 8 ADAPT** (precedent: racing minigame, dream sequence, Custom Mode), letting
  Opus or a stub-classifier handle the events. Per-mechanic, but a default stance
  would help.
- **OQ-R5 — Persistent assembly worktree for step-7?** Stand up the critique-#4
  smoke harness now (throwaway branch, runs incrementally every step) vs assemble
  ad-hoc? Recommended: stand it up with Group 2, since incremental assembly is half
  the point of the restructure.

**Carried forward (still open):**

- **OQ-3 (was strategy Q3) — Move-route → `applymovement` determinism.** The
  linchpin: 1,191 events touch 209. Is the RMXP move-command → pokeemerald
  movement-action mapping deterministic (direct-macro ~70% per the 06-03 census),
  or does speed/frequency/through-flag handling need per-event judgement? Resolving
  this unblocks Group 3 and a chunk of Group 4.
- **OQ-4 (was strategy Q4) — Per-mechanic fidelity calls.** For
  bridge/cave/boulder/stairs/berry/rock-smash: replicate in-engine, substitute, or
  strip? Each is a §10 call *before* its classifier. (Bridge is the cheapest and
  highest-leverage to decide first.)
- **OQ-2 (was strategy Q2) — Double-warp bounce.** Collapse to a single
  `warp(true_target)` or emit verbatim? Fidelity call; my lean is *emit verbatim*
  (safe, a dead line is cheaper than being wrong about GBA warp staging).
- **OQ-5 (was strategy Q5) — Re-run scope.** Confirmed approach: re-run **residue
  only** between steps (memoization makes this correct and free); whole-corpus
  re-validation is for correctness (differential test), not budget.

---

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| **Half-done sprawl** across three phases; "where was I." | The §4 checklist is the single source of step state; MEMORY Current-Phase updated every step; one logical commit per unblock. |
| **MEMORY drift** under faster iteration. | Step 8 is non-optional; keep entries targeted (the existing eviction discipline). |
| **Over-determinizing** — chasing Group-5 idioms and emitting compiles-but-wrong. | The §8 decision rule (verifiable structure) + the differential test. When in doubt, it's the Opus tail. |
| **Fork left unbuildable** by a Track-C step. | Step-4 `make modern` gate; C changes that alter baseline behavior need operator sign-off (CLAUDE.md §10). |
| **Mid-step surface change corrupts a live round.** | Invariant 2 — edits only between steps; `--timed`/`--limit` stop cleanly at checkpoints. |
| **Front-loading missed** — bulk resumed too early, spends on determinizable events. | OQ-R3 gate; invariant 3; the spend model (§7) is the standing reminder. |

---

## 11. Recommended first three steps (concrete)

1. **Step 1 (Track A, bulk paused):** drill the `{111,123,411,412}` 230-signature
   to confirm how many are the genuine self-switch gate; build that classifier;
   differential-test it against the maps Opus already did; re-measure. Expected:
   free% climbs from 29% toward ~34–35%.
2. **Step 2 (Track A):** shop/PC/heal + give-item + show-map classifiers (~190
   upper bound, clean single-call signatures). Re-measure; *then* take the first
   bounded bulk slice against the now-smaller tail.
3. **Step 3 (Track B foundation):** `map_constants.py` + local-id assignment +
   stand up the assembly smoke worktree. This unblocks Group 3 and turns the C4
   warp placeholders into real constants — set up for the door-transition lever.

After Step 3, the loop is self-sustaining: measure, pick the top remaining lever,
build, validate, bulk-slice, assemble, record, repeat — until Group 5 is all that
remains and the bulk's bounded steps finish it off.




