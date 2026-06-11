# Fable's Observation — Decision Log

Companion to `FABLES_OBSERVATION.md` (the 2026-06-09 critique). One section per
suggestion, recording **what was decided, the evidence behind it, and the details
needed to implement it later**. Working through these with the user one at a time;
treat this as preplanning notes for pipeline upgrades — nothing here is implemented
until its section says so.

| # | Suggestion | Status |
|---|---|---|
| 1 | Throughput decision | **DECIDED 2026-06-11** — option (a), no implementation needed |
| 2 | Deterministic STRIP skip | **DESIGN SETTLED 2026-06-11** — not yet implemented |
| 3 | Cluster-aware triage | **DESIGN SETTLED 2026-06-11** — build FIRST (before #2) |
| 4 | Recurring rung-2 assembly smoke | **DESIGN SETTLED 2026-06-11** |
| F1 | *Finding:* name-derived label collisions (live bug) | **FIX DESIGNED 2026-06-11** — front of the implementation queue |
| 5 | Q2/MapInfos naming contradiction | **DESIGN SETTLED 2026-06-11** |
| 6 | Move-route section in PHASE5_PLAN | **DESIGN SETTLED 2026-06-11** — section write queued with implementation |
| 7 | Commit the pile + compress MEMORY | **DONE 2026-06-11** |
| 8 | Phase 5 reachability check | not yet discussed |

---

## Suggestion 1 — Make the throughput decision explicitly

**Decision (2026-06-11): option (a) — accept calendar time on the Pro plan.**
Keep `run_bulk.py --timed` running until the corpus is done (~2,500 remaining
Opus spawns at observed ~22/day ≈ ~3 months), overlapped with Phase 5 build work.

- **Option (b) (AnthropicAPIBackend / Batch API) rejected by the user up front** — no
  API-key spend. The backend abstraction still admits it if that ever changes.
- **Option (c) (route trivial tier to Sonnet) rejected on measurement.** The critique's
  "~27% trivial tier" came from the 2026-06-03 difficulty scan, which predates the
  deterministic pre-filter — the pre-filter was then built to claim exactly that
  mechanical tier. Re-measured with the real classifiers
  (`scripts/measure_trivial_tier.py`): only **133 of 2,584 LLM-bound events (5.1%)**
  are still trivial → ≈4% calendar savings, not worth a second quality bar.

**Implementation: none.** This is a course-hold. Already recorded:

- ROADMAP Phase 4 strategy section rewritten (dead Ollama/staged plan retired to a
  historical note; decided single-model shape + measured numbers written in).
- MEMORY.md Decisions Made entry [2026-06-11].

**Follow-up resolved (2026-06-11, same day): classifier near-misses = Tier 1 only,
as a rider on the suggestion-#2 implementation.** Family analysis
(`scripts/near_miss_families.py`) showed the 133 trivial-but-unclaimed events
fragment into **35 families** (all still ahead of the run — 0 on checkpointed maps,
0 memo-covered):

- **Tier 1 (~40 events, DO):** dialogue events rejected only for `Wait (106)` and/or
  plumbing `SE (250)` (incl. the Chyinmunk/Barewl cry NPCs). One change — extend
  Classifier 1's tolerated-code set — with one validation question (does Opus strip
  wait/SE in dialogue context; Map200 precedent says strip-as-plumbing, confirm with
  ~2–3 spawns). Implement alongside the STRIP skip: same deterministic-side,
  nothing-frozen-touched, mid-run-safe class of change. Value decays as the run
  advances — do it when that window opens or not at all.
- **Tier 2 (~37 events, DECLINED):** two-page warps (12; page-dispatch wrinkle) and
  tone-only/bridge-SE near-decoratives (25; unvalidated "what does Opus emit for
  cosmetic-only events"). Two new classifiers + two validation rounds for ~2 days of
  calendar — fails the same bar that dropped Classifier 5.
- **Tier 3 (~56 events, DECLINED):** quote-bearing `\sign` texts (Opus quote rule
  unconfirmed — C7 bails by design) + 27 families of 1–4 events. Long tail.

Net: ~40 of the 133 get claimed cheaply (≈2 days of run time); the rest go to Opus
as normal.

---

## Suggestion 2 — Deterministic STRIP skip (orchestrator-side)

**Decision (2026-06-11): build it — as a pipeline-completeness feature, not a budget
rescue.** Phase-0 feature-level STRIP decisions currently have no enforcement path in
the orchestrator (only script-call signatures in the frozen prompt and command-code
rules are enforced). Close that gap with a machine-readable, per-game strip list the
orchestrator consults before spawning. Motivation shifted from the critique's framing:
the user wants the pipeline **complete and efficient for future runs and future
Essentials games**, not just this Uranium run.

### Measurements that shaped the design (2026-06-11)

- The three online CEs are **already spent this run**: CE 4 `GTS/WT` (205 cmds),
  CE 5 `VT` (179), CE 6 `LOBBY` (171) — converted 2026-06-05-ish; CE 5 alone is 4.2KB
  of Poryscript across 4 goto-chained blocks. They contributed **27 of the 241
  unhandled entries** (all "untranslatable online feature" noise).
- Exactly **36 map events reference CEs 4/5/6** — all `Receptionist PVP`/`Receptionist
  TRADE` copies across 12 Tandor Network lobby maps. They collapse to **6 memo keys;
  3 are already memoized** from map 2 (each a 5-line `lock/faceplayer/call/release/end`
  script, zero queue replay). Only map 152 holds 3 unmemoized variants → **~3 spawns**
  of remaining map-side cost. Budget argument for this run ≈ dead.
- **No other Phase-0 STRIP feature meaningfully surfaces in map events.** Signature
  scan (Mega Evolution, Achievements, Scoreboard, BetaSave, FMOD, Win32API,
  EliteBattle) found only 5 events with `$PokemonGlobal.nextBattleBack=`
  (EliteBattle cosmetic; maps 62/147/148/202) — those correctly go to the queue
  per the "absent from the script-call table = UNHANDLED" rule.
- Fresh-run value (Uranium re-run or a future game): the jumbo CE spawns never
  happen, callers stay cheap, queue stays clean.

### Design (settled)

1. **New per-game data file `reference/strip_list.json`** — joins the CLAUDE.md §4.3
   source-of-truth table as "whole-artifact STRIP decisions" (add the row when
   implementing). Schema sketch:

   ```json
   {
     "common_events": [
       {"id": 4, "expect_name": "GTS/WT",
        "feature": "online (phase0: scripts 233/235/236)",
        "stub_message": "The Tandor Network is currently unavailable."},
       {"id": 5, "expect_name": "VT", "feature": "online", "stub_message": "..."},
       {"id": 6, "expect_name": "LOBBY", "feature": "online", "stub_message": "..."}
     ],
     "map_events": []
   }
   ```

   - `expect_name` is a **fail-loud assertion**: if a re-export renumbers CEs, the
     mismatch aborts rather than stubbing the wrong event.
   - `feature` ties each entry back to the Phase-0 audit doc
     (`reference/uranium_custom_features.md`).
   - Missing file = empty list (a game with no strip decisions is valid); log at
     info level.
2. **CE stubs, not call-site stripping.** `convert_common_events` checks the list
   before spawning and emits a deterministic stub:

   ```
   script CommonEvent_004 {
       # STRIPPED: online (phase0 disposition — strip_list.json)
       msgbox("The Tandor Network is currently unavailable.")
       end
   }
   ```

   Compile-gated and recorded in `checkpoints/CommonEvents.blocks.json` like any other
   block; zero spawns. Every `call CommonEvent_004` site stays valid — this resolves
   the dangling-symbol wrinkle. Stubs do **not** queue (system.md STRIP ≠ queue rule);
   the `# STRIPPED:` comment makes output self-documenting and countable by
   `run_report`.
3. **Keep the receptionist callers; ship `map_events` empty for Uranium.** The callers
   convert normally and become NPCs that deliver the stub's "service unavailable"
   line — better fidelity than skipping them, at near-zero cost (memo covers 30/36).
   The `map_events` mechanism (`(map_id, event_id)` pairs, mirroring the
   `_event_has_commands` skip in `convert_map`) exists for future games where an
   event *is* the feature (e.g. a trade machine with no NPC value).
4. **Layer boundary stays clean — document it in the strip-list schema/README:**
   - whole-artifact strips (CE ids, map-event ids) → orchestrator strip list (this);
   - intra-event script-call strips (the Actan "strip the call, keep the event"
     pattern) → the game's script-call reference table (rides in the prompt);
   - command-code strips (104, 206, 108, bare 210) → system.md (game-agnostic).
5. **Touches nothing frozen.** No prompt change → memo fingerprint unchanged,
   checkpoints undisturbed. Safe to implement mid-run at a between-rounds commit
   window; zero effect on this run unless remediation (below) is also done.

### Implementation checklist (when picked up)

- [ ] `reference/strip_list.json` (3 online CEs; `map_events: []`)
- [ ] Loader + name assertion (fail loud on mismatch; absent file = empty)
- [ ] Stub path in `orchestrator.convert_common_events` (before `_convert_common_event`;
      compile-gate the stub; write through the blocks ledger)
- [ ] `map_events` skip in `orchestrator.convert_map` (next to `_event_has_commands`)
- [ ] CLAUDE.md §4.3 row: "Whole-artifact STRIP decisions | `reference/strip_list.json`"
- [ ] §4.6 tests: stub emission + compile, name-assertion failure, absent-file behavior,
      ledger idempotence on re-run, map-event skip
- [ ] `run_report` counts `# STRIPPED:` blocks (optional, small)
- [ ] **Rider (near-miss Tier 1, decided 2026-06-11 — see suggestion 1):** extend
      Classifier 1's tolerated-code set with `Wait (106)` + plumbing `SE (250)` after
      a ~2–3-spawn frozen-Opus validation of the strip-as-plumbing shape; claims ~40
      events (`scripts/near_miss_families.py` families 1–2 + kin) + tests

### Open sub-decisions (user call, before/while implementing)

1. **This-run remediation.** (a) Leave the already-converted CE 4/5/6 blocks; stubs land
   on the next fresh run, and cluster-aware triage (suggestion #3) auto-dispositions the
   27 queue entries. (b) Add a small maintenance path (e.g. `--regen-ce 4 5 6`) that
   programmatically clears just those ledger entries + the `CommonEvents.done`
   checkpoint and re-runs the CE pass → stubs replace the blocks at zero spawn cost,
   retiring the queue noise now. *Build-agent recommendation: (b) — small, and avoids
   hand-editing checkpoint state.*
2. **Stub voice.** Silent `end` vs. short "unavailable" msgbox. *Recommendation:
   msgbox — reads as intentional (like the vanilla games' decommissioned facilities),
   not broken.*
3. **`nextBattleBack` follow-up** (not this feature): when the prompt unfreezes after
   the bulk run, give `$PokemonGlobal.nextBattleBack=` a STRIP row in
   `reference/uranium_script_calls.md`. Until then its 5 queue entries are by-design.

---

## Suggestion 3 — Cluster-aware triage

**Decision (2026-06-11): build it, and build it FIRST — before the suggestion-#2 strip
skip.** It is read-only reporting over output artifacts (zero risk to the live run, no
frozen artifact touched, can land mid-run any time) and pays out every round
immediately. The #2 strip skip + near-miss Tier-1 rider follow in one
orchestrator-touching window.

### Why the current tool can't triage (measured 2026-06-11)

- `orchestrator.triage()` groups by the `reason` field — **all 241 queue entries say
  "agent-flagged unhandled"**, so the report's triage section is one undifferentiated
  line.
- The agent's free-prose `description` doesn't cluster reliably ("Move route" /
  "Move Route" / "move route").
- But the entries are joinable to source: every entry identifies its event
  (`map_id`+`event_id` or `common_event_id`), and 228/241 carry `page`+`line`.
  The 13 without `line` are the deterministic Classifier-4 warp entries
  (machine-generated descriptions, trivially tagged).

### Design (settled)

1. **Cluster by source-join, not by prose.** Look up each entry's actual RMXP command
   in the Phase-3 JSON (`maps/MapNNN.json` / `common_events.json`) via
   (map|CE, event, page, line) and derive a deterministic cluster key: command code,
   plus script-call signature head (355/655), branch-condition type (111), fixed-vs-
   variable mode (201). No prompt change, no queue-schema change, fully retroactive.
2. **Auto-disposition rule table** mapping clusters to already-made decisions
   (counts = today's 241):
   - 209/210/509 move routes → Phase-5-deferred (2026-06-03 decision) — ~78
   - 201 fixed-target warps → Phase-5 placeholder constants (C4 design) — ~35
   - 355/655 sigs in the UNHANDLED table → by-design needs-engine (**parse
     `reference/uranium_script_calls.md` — single source, don't duplicate**) — ~25
   - entries from strip-listed CEs → superseded-by-strip (reads `strip_list.json`,
     needs only the file, not the #2 orchestrator hook) — 27
   - 111 branches: **subdivide by script-condition content, conservatively** —
     recognized subfamilies only (e.g. `$PokemonGlobal.randomizer` → Phase-8 Custom
     Mode); unrecognized branches default to NOVEL
   - everything else → **NOVEL** (expected residue today: ~30–50)
3. **Novel-cluster review is delegated to the build agent, not the user** (user
   decision 2026-06-11, spoiler-avoidance): the build agent reviews novel clusters
   between rounds using the event JSON, `scripts_dump/`, and the
   `pokemon-uranium-wiki` skill, and presents any §10 content-fidelity calls to the
   user in **mechanical, spoiler-free terms** (codes, gating, feature needs, abstract
   scene stakes — no plot). Norm saved to persistent agent memory
   (`user-avoid-uranium-spoilers`). If a call genuinely can't be made blind, say so
   explicitly rather than leak story content.
4. **Exit-criterion reword** (when implemented): ROADMAP Phase 4 "every item gets a
   decision" → "every *cluster* gets a decision."

### Implementation checklist (when picked up)

- [ ] Source-join + cluster-key derivation (likely a new `triage` module or extension
      of `run_report.py`; keep `orchestrator.triage()` as the trivial fallback)
- [ ] Auto-disposition rules incl. the `uranium_script_calls.md` table parser and the
      `strip_list.json` reader (file-only dependency on #2)
- [ ] Clustered triage in `collect_stats`/`format_stats` (run_stats + bulk-runner exit
      report show it per round)
- [ ] `--novel` listing mode (the build-agent review queue)
- [ ] Tests: synthetic queue + map JSON, no external binaries
- [ ] ROADMAP Phase 4 exit-criterion reword
- [ ] First novel-cluster review pass over the existing 241 once the tool lands

---

## Finding F1 — Name-derived script labels collide (LIVE BUG, found 2026-06-11)

**Discovered while investigating suggestion #4.** Script-block labels are
`Map{NNN}_{event_name}_Page{n}` — but RMXP event names aren't unique, and copy-paste
naming is endemic. **This is assembly-class bug #3, and the largest.**

### Evidence

- `Map002.pory` **today** contains two `script Map002_Receptionist_TRADE_Page1`
  blocks (one calls `CommonEvent_006`, the other `CommonEvent_004`); Map008's partial
  output has `Map008_Trainer1_Page1/2` twice.
- Corpus-wide: **103/199 maps** have same-named command-bearing events — 255 collision
  groups, **~768 would-be duplicate labels** (`Stairs`×17 map 22, `Coral`×30 map 118,
  `NuclearBoat`×10 map 8).
- `deterministic.py:_page_label` uses the same name-based scheme → Classifier 4/6
  claims collide too.
- **No existing gate sees it:** the compile gate checks events in isolation, and whole-
  file poryscript *accepts* duplicate script names (Map002.pory compiled rc 0 at the §9
  gate review). Only fork assembly (`make modern`) catches it.

### Fix (designed; nothing frozen is touched)

1. **Orchestrator-side label rewrite at accept time:** qualify labels with the event id
   (`Map002_EV010_Receptionist_TRADE_Page1`) via the string-rewrite technique
   `_reinstantiate` already proved (definitions and goto references rewrite together).
   Applies to LLM, memo, and deterministic accept paths.
2. `deterministic.py:_page_label` gains the event id natively (our code, not the
   prompt's). The frozen agent keeps emitting name-based labels — the orchestrator
   rewrite normalizes them; baking the qualified scheme into `system.md` is a
   post-run / future-game prompt change.
3. **Memo interplay:** entries store the qualified script; `_reinstantiate` extends its
   prefix rewrite to `Map{src}_EV{srcev}_` → `Map{cur}_EV{curev}_` (+ stale-token
   guard, as today).
4. **Repair of already-converted maps ≈ zero spawns:** every accepted event is its own
   memo entry, so wiping the done-map checkpoints and re-running replays everything
   through memo/deterministic with the uniquifier active (same regen mechanism as the
   proposed `--regen-ce`). Verify with the #4 smoke harness afterwards.
5. Phase 5 label derivation reads final labels from `.pory` output, so no downstream
   breakage (Phase 5 metadata_wiring not yet built).

**Priority: FRONT of the implementation queue** — the run is actively producing
colliding output. Order decided 2026-06-11: **F1 label fix → #3 triage → #2 strip skip
+ near-miss Tier-1 rider — with the #4 smoke harness landing alongside F1 to verify the
repair end-to-end.**

---

## Suggestion 4 — Recurring rung-2 assembly smoke check

**Decision (2026-06-11): build it.** The per-event compile gate structurally cannot see
assembly-class bugs; three have now occurred (SS-flag definition gap, memo label-prefix
bug, F1 label collisions — the first two were caught by luck/live confirmation, F1 by
this investigation). A recurring `make modern` smoke over all current output turns
"discover systemic assembly bug at Phase 7" into "discover it at map 20." It gains an
immediate regression corpus: its first run must flag the Map002 duplicate (pre-F1-repair).

### Design (settled)

1. **Persistent fork worktree** on a throwaway smoke branch — main fork checkout never
   touched (same hygiene as the rung-2 spike); first build slow, incremental rebuilds
   fast thereafter.
2. Compile all current `.pory` → `.inc` (poryscript), drop into
   `data/scripts/rpg2gba_smoke/`, `.include` from `data/event_scripts.s`.
3. **Generated support headers for by-design-unresolved constant families** (the key
   wrinkle — a naive build fails on *expected* placeholders):
   - FLAG_*/VAR_* (incl. SS/TS mints): `flag_registry dump_header` — already exists
     (rung-2 step B proved registry→header→assembler).
   - `MAP_URANIUM_<N>`: dummy aliases via the same alias-header mechanism Phase 5 will
     use for real (19 distinct referenced so far).
   - `TRAINER_*`: **real ids from Phase 2 `intermediate/trainers.json`** (11 distinct so
     far; no placeholders needed).
   - Vanilla-named ITEM_*/SE_*/MUS_* resolve against the fork (collision-by-name is a
     Phase 7 roster concern, not an assembly concern).
   - Anything still unresolved after these = genuine bug → **fail loud**.
4. Parse build errors into clusters (duplicate symbol / undefined reference), report.
5. **Cadence: between rounds** — the machine idles during the 5h-window pauses anyway.
   Report-only but loud; never blocks or aborts the run. Manual
   `scripts/assembly_smoke.py` first; optional `run_bulk` wiring later.

### Implementation checklist (when picked up)

- [ ] `scripts/assembly_smoke.py`: worktree setup/teardown, .pory→.inc, header
      generation, include wiring, `make -j modern`, error clustering, report
- [ ] MAP_URANIUM placeholder-alias generator (scan output for `MAP_URANIUM_\d+`)
- [ ] TRAINER_* header from `trainers.json`
- [ ] Fail-loud check for unknown unresolved constant families
- [ ] First-run regression assertion: detects the known Map002 duplicate before the F1
      repair, passes clean after
- [ ] (later, optional) hook into `run_bulk` pause windows

---

## Suggestion 5 — Q2/MapInfos naming contradiction

**Decision (2026-06-11): resolve it with an overrides file + signals-first identity
check, before `map_constants.py` is implemented.** Q2's mechanism (readable canonical
names + alias header) stands; what changes is the *trust model* for `map_infos.json`
names. Stakes are higher than the critique stated: `display_name` feeds
`show_map_name`, so a stale label is the **player-visible location header**, not just
an internal constant.

### Measurements (2026-06-11)

- `map_infos.json` has **198 entries for 199 maps** — one map has no entry at all
  (identify it; guaranteed fail-loud case for `mint`).
- **35 duplicate-name groups** (`Rochfale Town`×6, `Route 03`×4, `Burole Town`×4…) —
  many are *legitimate* MAPSEC-style grouping (route segments / town + outskirts),
  not errors.
- **Both `Comet Cave`×3 and `Passage Cave`×3 exist** — with map 7 known-stale, the two
  dungeons' floors may be cross-assigned; naive dedup would mint wrong-dungeon
  constants. Plus junk: map 39 `Test Area`, map 81 `Route 01 (old rod house)`.

### Design (settled)

1. **Signals first, wiki second.** A free script harvests per-map identity signals —
   town-sign text in the map's own events (map 32's sign says "Moki Town"), BGM names
   (how map 7 was caught: "PU-Passage Cave"), connection topology, the map_infos
   parent tree — and **flags only disagreements** with the map_infos name. The
   `pokemon-uranium-wiki` skill then arbitrates the flagged maps + the ~50 canonical
   overworld locations.
2. **`reference/map_name_overrides.json`** — new one-source-of-truth corrections file
   (id → corrected name + evidence string + date). `MapConstantRegistry.mint` consults
   it before `map_infos.json`. Phase-3 output stays unedited; the override file is
   committed and reviewable. Joins the CLAUDE.md §4.3 table when implemented.
3. **Q2 amendment: separate `MAP_*` identity from `MAPSEC_*`/display grouping.** The
   stub mints MAPSEC 1:1 per map; the duplicate names are the natural grouping signal
   (Route 03's segments share one MAPSEC + one on-screen header, no `_2/_3` suffixes).
4. **Wiki pass = build-agent research under the spoiler norm** (user sees only the
   corrections table — town/route names, no wiki plot content).

### Implementation checklist (when picked up — Phase 5 pre-task, before map_constants)

- [ ] Identify the map missing from `map_infos.json`
- [ ] `scripts/map_identity_check.py`: harvest sign-text/BGM/connection/parent signals,
      flag disagreements with map_infos names
- [ ] Build-agent wiki arbitration pass over flagged maps + ~50 canonical locations →
      `reference/map_name_overrides.json` (with evidence strings)
- [ ] `map_constants.py`: consult overrides before map_infos; MAPSEC grouping support
      (shared section constants + display names)
- [ ] CLAUDE.md §4.3 row for the overrides file
- [ ] Check GBA location-header length limits against the corrected names

---

## Suggestion 6 — Move-route section in PHASE5_PLAN.md

**Decision (2026-06-11): write section 5.5 (Move Routes) into PHASE5_PLAN.md, carrying
the census below and open questions Q-MR1–Q-MR5.** The questions themselves get
answered at implementation time, alongside the rest of the queued suggestions — the
section's job is to make the deferred scope visible and bounded. The 2026-06-03
decision (agent breadcrumbs + queue, no `applymovement`) stands unchanged.

### Census (2026-06-11) — the deferred debt, measured

- 1,191 events carry scripted 209 routes; **531 (45%) target only the player** →
  translatable with `OBJ_EVENT_ID_PLAYER`, **no local-id dependency**.
- Trigger profile: autorun 393 + parallel 134 = **527 cutscene/ambient events** (the
  fidelity-critical tier); player/event-touch 510 (mostly nudge/anti-stuck patterns);
  talk 154.
- **Scope reduction:** page-level autonomous movement (wandering NPCs, `move_type`)
  is NOT 209 work — it maps natively to pokeemerald `movement_type` in 5.3 metadata
  wiring.
- Vocabulary (~20k commands) splits into three translator classes:
  1. **Direct macro map (~70%)** — moves/turns/waits/jumps/diagonals all have
     movement-macro equivalents.
  2. **Hoistable side-effects** — `play_se` 287, `change_graphic` 608, route-embedded
     switches 12: split the route, emit a script command between `applymovement`s.
  3. **Approximate-or-drop** — `change_opacity` 2,280 (binary
     `set_invisible`/`set_visible`), `through_on/off` 1,757 (no equivalent),
     `always_on_top` 171. RMXP ghost/fade flourishes; binary is the honest substitute.

### Open design questions for the section (answer at implementation)

- **Q-MR1 — local-id convention:** object-event local ids minted in event-id order,
  mapping persisted by 5.3 (one source of truth). Check pokeemerald's per-map
  object-template ceiling (~64) vs Uranium's biggest maps (map 148 events into the
  190s).
- **Q-MR2 — vocabulary translator** (three classes above).
- **Q-MR3 — timing conversion:** RMXP 40fps wait frames → GBA 60fps `delay_*`.
- **Q-MR4 — injection architecture** (the genuinely open one): translated routes must
  re-enter emitted `.pory` without hand-editing generated output — deterministic
  idempotent post-pass over `.pory` + queue, vs regen-with-translator via memo replay
  (the F1-repair mechanism). The frozen agent keeps emitting breadcrumbs either way.
- **Q-MR5 — degrade tiers:** player-only (531) first, dependency-free; cutscene (527)
  = fidelity-critical; rest default to static-NPC degrade, queue as audit trail.

### Implementation checklist (when picked up)

- [ ] Write PHASE5_PLAN.md §5.5 with the census + Q-MR1–5 + exit-criteria additions
- [ ] Acceptance-test stubs in `tests/test_tileset_converter.py` pattern (skipped
      checklist style, like the other Phase 5 sections)

---

## Suggestion 7 — Commit the pile + compress MEMORY.md (EXECUTED 2026-06-11)

Done immediately rather than queued — pure hygiene, zero pipeline risk, compounds in
cost every session it's deferred. Verified green first (235 pass / 10 skips = the
Phase 5 acceptance stubs; ruff clean).

- **Commit `ceb9320`** — Phase 4 bulk-run harness: backends error taxonomy
  (RateLimit/Transport/BudgetReached + orchestrator re-raise), the 06-08
  false-positive rate-limit fix, per-CE resumability ledger, `run_report`,
  `prep_bulk_run`/`run_bulk --timed --limit`/`run_stats`, `tests/test_bulk_run.py`.
  The production run is finally pinned to a hash.
- **Commit `b7a7be2`** — Phase 5 scaffold: `tileset_converter` package (7 modules +
  README), `PHASE5_PLAN.md`, `reference/tileset_map.json` seed,
  `tests/test_tileset_converter.py`.
- **Third commit** — critique-walkthrough docs: this file, the ROADMAP Phase 4
  strategy rewrite, MEMORY.md updates + compression, memory-archive additions, and
  the promoted measurement scripts.
- **Measurement scripts promoted** (option chosen: commit, not delete):
  `scripts/measure_trivial_tier.py` (ex `_tmp_sonnet_tier.py`) and
  `scripts/near_miss_families.py` (ex `_tmp_near_miss_families.py`) — they import the
  live classifiers so they stay self-updating; all citations updated.
- **MEMORY.md compressed:** Current Phase rewritten to ~18 lines of live state (run
  position, pre-filter summary, F1 live bug, the decided implementation queue, Phase 5
  status, frozen-config gate paragraph, phase one-liners, env config). The Phase 4
  build narrative (machinery → calibration A–D → rung 2/3 → dedup A/B/C → pre-filter
  C1–C7 → scaffold) moved **verbatim** to `reference/memory-archive.md` under "Phase 4
  Build Narrative".
