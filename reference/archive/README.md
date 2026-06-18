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
