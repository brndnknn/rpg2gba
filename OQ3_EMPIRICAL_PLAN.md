# OQ-3 — empirical plan: is RMXP move-route → `applymovement` deterministic?

**Status:** Step 1 EXECUTED 2026-06-13 (`scripts/moveroute_coverage.py`) — see §7.
Step 2 (budget-gated calibration) pending user authorization; Step 3 follows it.
**Date:** 2026-06-13.
**Relationship to existing docs:** Answers open question **OQ-3** from
`ITERATIVE_ROADMAP.md §9` (carried forward from `DETERMINISTIC_EXPANSION_STRATEGY.md`).
OQ-3 is one of only two questions that actually gate whether the iterative
restructure hits its full envelope (the other is the OQ-4/OQ-R4 Phase-6 scoping
call). Resolving OQ-3 unblocks Group 3 (move/warp/door) and a chunk of Group 4,
and its answer reshapes how much Track-C work OQ-R4 should authorize.

**The question (verbatim from the roadmap):** Is the RMXP move-command →
pokeemerald movement-action mapping deterministic (direct-macro ~70% per the
06-03 census), or does speed/frequency/through-flag handling need per-event
judgement?

---

## 1. The catch: the standard validation method does NOT work here

The iterative roadmap's default classifier validation (invariant 4) is "replay the
candidate classifier against the frozen-Opus oracle and diff the normalized
Poryscript." **That cannot answer OQ-3.**

The frozen system prompt (`src/rpg2gba/conversion_agent/prompts/system.md:156–170`)
explicitly tells Opus **not** to emit `applymovement` — it emits a
`# UNHANDLED: move route` breadcrumb + one `unhandled[]` entry instead. So on all
7 bulk-done maps the frozen-Opus oracle contains **zero** move-route conversions to
diff against. (This is the 2026-06-03 decision: move routes deferred to Phase 5
because every non-player target resolves to a pokeemerald local id assigned only
during Phase-5 wiring.)

Consequence: OQ-3 needs a *different* method than every other classifier — a
structural census plus a small bounded calibration, not a differential test
against the existing oracle.

---

## 2. Decompose OQ-3 into the question it actually is

OQ-3 conflates two things that must be measured separately:

- **(a) Vocabulary determinism** — does RMXP move-command *N* map to a fixed
  pokeemerald `MOVEMENT_ACTION_*`? **This is the real OQ-3.**
- **(b) Target resolution** — player / this-event / other-event, and can we name
  the local id? This is **already answered**: it is Track-B-gated (06-03 census:
  player 38% / this 31% / other 31%, ~1.3 target classes/event). Not a vocabulary
  question.

Isolate (a) by measuring on the **player-only subset (531 events, 45% — per the
PHASE5_PLAN §5.5 census)**, where there is no local-id dependency. That subset is
also exactly the Group-3 "reclaimable first" cut, so the measurement set and the
first reclaim target are the same set.

---

## 3. The plan

### Step 1 — Structural coverage census (zero LLM, ~a few hours, likely answers it)

New `scripts/moveroute_coverage.py`, mirroring `scripts/idiom_frequency.py`'s
corpus walk + `rpg2gba.conversion_agent.lane.real_commands`. For it:

1. Enumerate the RMXP move-command codes actually used across all **3,804 `209`
   routes** (histogram by occurrence). RMXP move-command codes are 1–45
   (1–8 move dirs, 9 random, 10/11 toward/away player, 12/13 forward/backward,
   14 jump, 15 wait, 16–26 turns, 27/28 switch on/off, 29 speed, 30 freq,
   31–40 anim/dirfix/through/on-top toggles, 41 graphic, 42 opacity, 43 blending,
   44 play SE, 45 script).
2. Hand-author the candidate map: each code → `MOVEMENT_ACTION_*` from the fork
   header `include/constants/event_object_movement.h` (confirmed present). Bucket
   each code:
   - **A — direct macro:** dirs 1–8, turns 16–26, jump 14, wait 15 → fixed
     `MOVEMENT_ACTION_*`.
   - **B — parameterized-deterministic:** speed (29) selects
     `WALK_SLOW/NORMAL/FAST` for the following steps; a fixed function, not
     judgement.
   - **C — no static analog / context-dependent:** random (9), toward/away player
     (10/11), forward/backward (12/13, facing-relative), through/dirfix/anim/on-top
     toggles (31–40), graphic (41), opacity (42), play SE (44), script (45).
3. Per event: **fully deterministic** iff every command ∈ A∪B. Report the
   histogram, split by target class, and — critically — **dump the exact commands
   that pushed each event into bucket C.**

Step 1 alone gives the hard ceiling and names every breaker. The §5.5 stub
estimated "direct-macro ~70%"; this turns the estimate into a verified per-event
number and reveals whether the ~30% residue is one or two recurring C-commands
(fixable with a rule) or genuinely scattered (judgement → Opus tail).

### Step 2 — Settle the contested commands (small *bounded calibration*, NOT the oracle)

For each bucket-C command that actually occurs, decide its canonical rule
(drop / approximate / hoist-as-side-effect / genuine-judgement). Because the
frozen oracle is empty for move routes, ground truth comes from a **one-time
targeted calibration** — the escape hatch the roadmap itself names in §8.3.

Take a stratified **~30–50-event sample** covering each C-command and establish the
canonical `applymovement` for each, either via a throwaway calibration prompt
variant or by authoring the expected mapping as a golden test. This is authoring a
*test oracle*, not hand-converting events for the bulk run — it writes no `.pory`
and never touches the frozen bulk config, so iterative-roadmap invariants 1
(frozen config) and 2 (no mid-step surface change) both hold.

**Decision rule per C-command:** deterministic iff one fixed rule reproduces the
canonical output across every sampled context. If the same command needs different
handling depending on a branch/variable (e.g. "move toward player" in a scripted
cutscene vs. a chase), it is judgement → those events stay Group-5 Opus tail.
The §5.5 leans (opacity → binary-visible, through → drop, on-top → drop,
SE/graphic/switch → hoist) become **validated** here instead of assumed.

### Step 3 — Quantify and decide

Output the 3-way partition of the 1,191 move-route events:

- **fully-deterministic + player-only** → reclaim now (no Track-B dep) — sizes the
  immediate Group-3 win.
- **fully-deterministic + self/other-target** → reclaimable after Track-B local-ids.
- **contains a judgement C-command** → Opus tail (Group 5).

That partition + the validated rule set **is** the empirical answer to OQ-3, and it
directly feeds the OQ-R4 scoping math (how many of the ~1,191 go free vs. stay
paid).

---

## 4. Cost

- **Step 1:** pure Python, zero spend, reuses `idiom_frequency.py` scaffolding.
- **Step 2:** bounded ~30–50-event calibration, one-time, off the frozen path.
- **Step 3:** bookkeeping.

Step 1 alone likely resolves OQ-3; Step 2 is only needed if the bucket-C residue
turns out to be large or scattered.

---

## 7. Step 1 results (executed 2026-06-13)

`scripts/moveroute_coverage.py` (zero-spend, mirrors `idiom_frequency.py`). It
reproduces the plan's anchors exactly — **3,804 `209` routes, 1,191 events, 531
player-only (45%)** — which cross-validates the corpus walk.

### The headline numbers, two ways

The candidate map buckets each inner code A (fixed macro) / B (parameterized-
deterministic) / C (no analog / context-dependent). Within C, a **SOFT** subset
(through, opacity, SE, graphic, on-top, freq, anim, blend, switch) is the §5.5
drop/hoist/approximate family — rule-fixable, not judgement; the rest is **HARD**
(diagonals, random, toward/away-player, facing-relative steps & turns, script).

| Partition | player-only (reclaim now) | self/other (Track-B) | tail | deterministic % |
|---|---|---|---|---|
| **Conservative** (A/B only) | 158 | 137 | 896 | **295/1191 = 24%** |
| **Potential** (A/B + SOFT-C) | 199 | 581 | 411 | **780/1191 = 65%** |

### The answer to OQ-3

**Vocabulary determinism is real but conditional, and the §5.5 "~70%" estimate
was measuring the *potential*, not the raw macro rate.**

- **Raw 1:1 macro determinism is only 24%.** A pure direct-macro translator
  (no drop/hoist/approximate rules) leaves 76% of move-route events to Opus.
- **The 24%→65% gap is NOT scattered judgement — it is ~5 recurring SOFT-C
  commands**, exactly the §5.5-predicted families:
  - Through ON/OFF (37/38): **1,757 events** combined — the single biggest killer.
  - Change Opacity (42): 527 events.
  - Play SE (44): 275; Change Graphic (41): 274; On-top (39/40): ~170.
  Each is one fixed rule (37/38 → drop; 42 → binary visible/invisible; 44 → hoist
  `playse`; 41 → hoist sprite swap; 39/40 → drop/fixed-priority). If those rules
  are behavior-preserving, determinism jumps to **65%**.
- **The irreducible HARD tail is 411 events (35%)**: relative/random turns
  (20/21/22/24), diagonals (5–8, no GBA diagonal walk), toward/away-player moves
  (10/11), facing-relative step fwd/back (12/13), random move (9), script (45).
  These genuinely need Opus (or a per-event facing-tracking analysis beyond a
  static vocabulary map).

### Bucket-B parameter caveats (held up well)

- **Jump (14):** 205 occ, only **10** are diagonal/>2-tile true-C — **174 are
  `(0,0)` jump-in-place** (→ `MOVEMENT_ACTION_JUMP_IN_PLACE_*`, mappable). Jump is
  effectively deterministic.
- **Wait (15):** frames cluster at 1/2/4/5/6/8/10/30 → round to `DELAY_{1,2,4,8,16}`.
- **Speed (29):** values 1–6 → `WALK_{SLOW,NORMAL,FAST,FASTER}`. Both clean functions.

### Decision this produces

Step 1 resolves the *structure* of OQ-3: the mapping is deterministic for a
**well-defined 65% ceiling**, gated on validating **five specific SOFT-C rules** —
not an open-ended judgement problem. That turns Step 2 from "is this even
determinizable?" into a **narrow, ~30–50-event calibration stratified across
exactly those 5 commands** (does dropping through / approximating opacity /
hoisting SE & graphic / dropping on-top preserve the behavior Opus would emit?).

Step 2 spends Pro budget, so it is **gated on user authorization** (CLAUDE.md §10).
If the user declines the calibration, the SOFT-C leans can be adopted as-is at
implementation with the §5.5 rationale and revisited at the Phase-7 playthrough.

**Immediate reclaim (no Step 2, no Track-B):** 158 player-only events are
fully-deterministic under A/B macros *today* — the concrete Group-3 first cut.

---

## 5. Traps to watch (from PHASE5_PLAN §5.5)

- **40 → 60 fps timing.** RMXP move timing does not map 1:1 to pokeemerald frame
  cadence; a route that "looks identical" command-for-command can play at a
  different speed.
- **Through-flag (codes 37/38).** It is an object *property*, not a movement
  action — there is no `MOVEMENT_ACTION_*` for it, so "drop" is the likely rule,
  but only the Step-2 calibration confirms dropping it doesn't change observable
  behavior Opus would otherwise have preserved.

Make sure the Step-2 sample deliberately includes routes exercising both.

---

## 6. Decision: build Step 1?

Step 1 (`scripts/moveroute_coverage.py`) is the cheap, zero-spend move that
produces the real per-event numbers and tells us whether Step 2's calibration is
even necessary. That is the recommended first action when OQ-3 work begins.
