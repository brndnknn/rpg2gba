# reference/archive/ — superseded planning docs

These docs were moved out of the repo root at the **2026-06-18 strategy pivot**
(LLM-as-conversion-spine retired → deterministic transpiler + vertical playable
slices). They are kept verbatim for history; their **still-authoritative content was
absorbed first** into the live docs before archiving. Live planning now lives in just
five root docs: `README.md`, `ROADMAP.md`, `CLAUDE.md`, `MEMORY.md`, `BUILD_PLAN.md`.

**Do not treat anything here as current.** If it matters, it's in a live doc; if it's
only here, it's history.

| Archived doc | Was | Live content now in |
|---|---|---|
| `ITERATIVE_ROADMAP.md` | the "ratchet" re-sequencing proposal | `BUILD_PLAN.md` (per-slice loop, differential-oracle discipline) + ROADMAP Operating Model |
| `DETERMINISTIC_EXPANSION_STRATEGY.md` | widen-the-deterministic-surface strategy | `BUILD_PLAN.md §3` + ROADMAP §Phase 4 |
| `OQ3_EMPIRICAL_PLAN.md` | move-route → applymovement determinism study | `BUILD_PLAN.md §5` (24% / 65% / 35%) |
| `PATHFINDER_SLICE_ROADMAP.md` | S1–S9 slice plan | `BUILD_PLAN.md §6` + MEMORY archive (S1–S9 history) |
| `PATHFINDER_FINDINGS.md` | slice warp-trace / findings | `BUILD_PLAN.md §6` + MEMORY Key File Notes |
| `PATHFINDER_BUILD.md` | slice build/assembly guide | `BUILD_PLAN.md §6` + `scripts/assemble_pathfinder.py` |
| `PATHFINDER_STEP2_TILE_MAP_PLAN.md` | tile-map substitution step plan (done) | superseded by quantize pipeline (`BUILD_PLAN.md §7`) |
| `PATHFINDER_STEP3_LAYOUT_PLAN.md` | layout converter step plan (done) | `src/rpg2gba/tileset_converter/layout.py` + MEMORY Key File Notes |
| `PHASE2_PLAN.md` | Phase 2 PBS plan (COMPLETE) | MEMORY (Phase 2 COMPLETE) + Key File Notes |
| `PHASE3_PLAN.md` | Phase 3 deserializer plan (COMPLETE) | MEMORY (Phase 3 COMPLETE) + Key File Notes |
| `PHASE4_PLAN.md` / `PHASE4_CALIBRATION_PLAN.md` / `PHASE4_DEDUP_PLAN.md` / `PHASE4_DETERMINISTIC_PLAN.md` | Phase 4 LLM-pipeline plans | superseded by the pivot; transpiler plan in `BUILD_PLAN.md` |
| `PHASE5_PLAN.md` | Phase 5 layout/tileset plan | ROADMAP §Phase 5 (quantize) + `BUILD_PLAN.md §7` |
| `FABLES_OBSERVATION.md` / `FABLES_IMPLEMENTATION.md` / `FABLES_DECISIONS.md` | the FABLES critique walkthrough + queue (all phases done) | MEMORY → Decisions Made (the FABLES decisions are recorded there) |

**2026-08-04 — slice 1 (pathfinder) retirement, its §9 boot-walk gate PASSED:**

| Archived doc | Was | Live content now in |
|---|---|---|
| `SLICE1_TODO.md` | slice-1 tracking ledger, 1299 lines, ~90 citation sites repo-wide (unrepointed — item numbers stable, file moved not deleted) | `PROJECT_TODO.md` #15-26 + #27 (ex-`SLICE2_TODO.md` #3), `CH02_TODO.md` (née `SLICE2_TODO.md`, renamed 2026-08-05), `ROM_TEST_DEV.md` harness section, `reference/guides/engine_gotchas.md` |
| `SLICE1_EVENTS.md` | 131-event inventory for the 8 slice-1 maps | `reference/guides/event_conversion_model.md` (§1/§12 promoted); §11.11 bug → `PROJECT_TODO.md` #20 |
| `SLICE1_FINAL_BOOT_WALK.md` | the §9 gate certificate itself | stays as the passed certificate; "Not implemented" ledger repointed in-place |
| `BOOT_WALK_CHECKLIST.md` | earlier boot-walk checklist, already superseded before this pass | history only |
| `STARTER_SPECIES_PLAN.md` | Orchynx/Raptorch/Eletux conversion plan (closed, W1-W9/S6 passed) | `reference/guides/phase7_integration_plan.md` D2 (pointer added, high value for remaining ~160 species) |
| `STARTER_QUIZ_ANSWERS.md` | S6 aptitude quiz answer key | none needed — closed, kept as a human-readable cheat sheet |
| `RMXP_MOVEMENT_FIX_PLAN.md` | RMXP blocked-move semantics fix plan | `reference/guides/custom_route_interpreter.md` ("RMXP blocked-move semantics" section; corrects its wrong §1 collision rule) |
| `moki_slice_story_chain_2026-07-16.md` | Moki story-chain + event-trigger bug research | `reference/chapters/01-moki.md` |
| `lab_starter_scene_positioning_2026-07-27.md` | Map050 starter-scene actor positioning drift | `PROJECT_TODO.md` #26 (the one surviving open question) |
| `gated_door_collapse_2026-07-26.md` | gated-doors-collapse-into-warps root cause + fix | `PROJECT_TODO.md` #25 (the `WARP_OVERRIDES` duplicate leftover) |
| `hand_conversion_audit_2026-07-31.md` | hand-conversion audit + remediation plan | `PROJECT_TODO.md` #19 (3 items) + `ROM_TEST_DEV.md` (2 harness items) |
| `slice1_queue_readthrough.md` | point-in-time transpiler-queue read-through | history only, no forward action items |
| `walker_checkpoint2_findings.md` | checkpoint-2 sign-off + 2 deferrals | both deferrals shipped (`808966cd`); history only |
| `mgba_automation_feasibility_2026-07-17.md` | headless-mGBA feasibility study | `src/rpg2gba/playtest/` (the shipped harness) |
