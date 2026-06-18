# Deterministic Expansion Strategy

**Status:** proposal / brief — not yet roadmap-ratified.
**Date:** 2026-06-13.
**Owner question:** should we widen the deterministic pre-filter (and build engine
features to feed it) *alongside* event translation, instead of leaning on bulk
Opus runs to clear the corpus?

---

## 1. Thesis

The deterministic-vs-Opus boundary is **not fixed**. Every event Opus "handles"
is an idiom that simply has no mechanical target *yet*. We move an event into the
free (deterministic) lane three ways:

1. **Classifier** — a `classify_*` function in
   `src/rpg2gba/conversion_agent/deterministic.py` recognizes an idiom and emits
   the known Poryscript. Pure Python, no C.
2. **STRIP** — a script-call is a verified no-op; drop it (`_DIALOGUE_STRIP_RE`).
3. **Engine** — build a real target in the `pokeemerald-expansion` fork (Phase 6),
   *then* a classifier can emit the new macro mechanically.

Widening this surface is the lever that shrinks Opus spend. The bulk run should be
the small long-tail at the *end*, not the thing we sit and wait on. Crucially, the
corpus is static JSON on disk — we can measure the entire idiom distribution with
**zero Opus calls** and rank what to build next.

## 2. Mechanism (no new architecture)

All of this builds on the classifier system already shipped. A new classifier is:

- a pure fn `(map_id, event, ctx) -> str | DetResult | None`,
- returns Poryscript on a confident structural match, `None` to fall through to Opus,
- never raises (the dispatcher swallows),
- appended to the `_CLASSIFIERS` list; `try_deterministic` claims the event before
  it reaches the LLM lane,
- output still passes the orchestrator's compile-gate + self/temp-switch mint, so a
  wrong guess is caught, and a non-match costs nothing.

Engine (tier B) work only adds the *macro* the classifier emits; the classifier
half still lives in `deterministic.py`.

## 3. Measurement (the analyzer)

`scripts/idiom_frequency.py` — static scan of `output/uranium-build/maps/*.json`
using the real `try_deterministic`. Reports, for every Opus-bound event, the
command-idiom blocking it and how often it recurs. Re-run it after every batch to
watch the free-fraction climb.

**Current baseline:** 3581 non-empty events — **29% free, 70% (2535) fall to Opus**
(296 of those are human-lane / hand-convertible today).

Signatures are distinct command-*sets*, so each count is the **upper bound** a
single classifier could reach — it must still verify structure, not just the set.

## 4. Target tiers

### Tier A — classifier-only, no C (~515 events, doable now)
| idiom | events | target |
|---|---|---|
| self-switch conditional gate `{111,123,411,412}` | 230 | stereotyped if-self-switch block |
| pure move-route `{209,210,509}` | 89+ | `applymovement` |
| shop / PC / heal (`pbPokemonMart`, `pbSetPokemonCenter`, `pbPokeCenterPC`) | ~120 | native pokeemerald macros |
| give-item (`item`, `pbReceiveItem`) | ~54 | `giveitem` |
| single-warp + `pbCaveExit` | ~21 | warp + queue overlay as Phase-6 UNHANDLED |

### Tier B — engine + classifier pairs (Phase-6 C)
- **Door/cave transition-warp idiom** — **~240 events**, the single biggest lever.
  `{106,111,201,208,209,210,223,…,setTempSwitchOn}`: fade → walk-into-door move
  route → transfer → temp-switch. One engine-backed classifier collapses all.
- Named Uranium field mechanics, each a script-call cluster: `pbRockSmash…` 65,
  `pbBerryPlant` 53, `pbCaveExit/Entrance` 51+47, Strength `Boulder` 51,
  `Stairs` 61, `pbBridgeOn/Off` 65.

### Tier C — irreducible Opus tail
Branch-heavy story logic (`111` blocks 1628 events, `122 Control Variables` 412).
Conditions vary per event → genuine judgement. Do **not** chase deterministically.

### Cross-cutting prerequisite
`setTempSwitchOn` (345 events) is the connective tissue under most tier-A/B
signatures — Uranium's temp-switch system. Settling how it maps to self/temp-flags
unblocks several signatures at once; do it early.

## 5. Recommended sequence

1. Clear **tier A** (no C, ~515 events) — fastest free-fraction gain.
2. Settle `setTempSwitchOn` mapping (prerequisite for B).
3. Build the **door-transition idiom** engine+classifier (~240).
4. Pick off named field mechanics by frequency.
5. Run Opus only on the residue; re-run the analyzer between batches.

## 6. Guardrails (unchanged)

- Classifier/STRIP/engine changes happen **between** runs, never mid-run.
- Engine changes that alter baseline pokeemerald behavior need operator sign-off (§10).
- §9 review gates still stand.
- Fail-loud: a script-call with real effect (e.g. `pbCaveExit`'s Flash/escape-point)
  is **queued UNHANDLED**, never silently STRIPped.

---

## 7. Resolved

- **`setTempSwitchOn` mapping (was open Q#1) — CLOSED, no new policy needed.**
  Per-map-*visit* state (`Game_Event#@tempSwitches`, rebuilt every map load), **not**
  a saved self-switch. Already settled: `uranium_script_calls.md:40` →
  `setflag(FLAG_MAP{ID}_EVENT{ID}_TS{letter})` (TS, not SS), and
  `flag_registry.py` already ships `temp_switch_flag_name` + `mint_temp_switch`
  + `RPG2GBA_TEMPSWITCH_BASE`. Maps to pokeemerald's native auto-reset `FLAG_TEMP_*`
  range (Phase-7 points `tempswitch_base` there — *confirm the auto-reset-on-warp
  behavior against the fork*). Remaining work is pure wiring: a classifier that
  recognizes `355 setTempSwitchOn("A")`, calls `mint_temp_switch`, emits `setflag`.

- **Semantic validation of new classifiers (was open Q#7) — ANSWERED: differential
  testing vs frozen-Opus.** Oracle is already on disk (`memo_manifest.json` +
  per-map `.pory`), so it costs zero Opus calls. Per classifier: (1) collect events
  it claims; (2) intersect with events Opus already converted; (3) diff emitted
  Poryscript **and** `unhandled[]` entries, normalized (whitespace, labels, registry
  flag-names — should be byte-identical); (4) acceptance = exact normalized match;
  every mismatch hand-triaged → classifier bug (fix) or Opus inconsistency
  (deterministic output becomes canonical + a recorded §10 fidelity decision);
  (5) events with no Opus oracle → spot-check or a one-time targeted calibration
  pass. Ship as a pytest per classifier (§4.6/§8). Compile-gate stays the syntax
  net; this is the semantic net, and its mismatches surface exactly the events
  needing a fidelity call.

## 8. Open questions (need operator input)

1. **Phase 4/6 interleave — ratify in ROADMAP?** Current roadmap sequences Phase 4
   before Phase 6. This brief proposes interleaving. Do we formally amend the
   ordering, or treat engine work here as scoped exceptions?
2. **Double-warp bounce — collapse or preserve?** Collapse to a single
   `warp(true_target)` in the classifier (cleaner, relies on our reading of GBA warp
   staging), or emit verbatim (safe, carries a dead line)? Fidelity call (§10).
3. **Move-route (209/509) → `applymovement`.** Is the RMXP move-command → pokeemerald
   movement-action mapping deterministic enough for a classifier, or does it need
   per-event judgement (speed/frequency/through flags)?
4. **Field mechanics fidelity (§10).** For boulder/stairs/berry/rock-smash/bridge —
   which do we replicate in-engine, which substitute, which strip? Per-mechanic call
   before building each classifier.
5. **Re-run scope & budget.** After each classifier batch, do we re-run only the
   residue (memoization implies the already-deterministic events never hit Opus
   anyway), or re-validate the whole corpus? Affects Pro-usage budget.
