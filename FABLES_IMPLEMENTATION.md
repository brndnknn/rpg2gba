# Critique-queue implementation — live progress tracker

Executes the consolidated queue from `FABLES_DECISIONS.md` (designs are authoritative
there; this file is the **runbook + checklist**). Tick items as they complete, with
commit hashes. If a session dies mid-run: read this file top to bottom, find the first
unticked box, and resume there.

**Approved plan:** `~/.claude/plans/glistening-gathering-dolphin.md` (2026-06-11).

## Standing constraints

- Nothing frozen is touched: `system.md`, model `claude-opus-4-8`, prompt-borne
  reference docs (memo fingerprint must not change).
- Pause-gates requiring explicit user OK:
  - **G1** — first fork smoke build (`make modern`, several minutes)
  - **G2** — ~2–3 frozen-Opus validation spawns for the near-miss rider (budget)
- Every work item: `pytest` green **from repo root** + `ruff check` clean + one
  commit (`Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`).
- Bulk run stays stopped until Phase 1 regen completes. Resuming after = user's call.
- Delegation (per /delegate): Sonnet sub-agents own only NEW files (one writer per
  file); the lead owns all edits to existing modules and all commits.

## Status

- **Current position:** Phase 1 — 1.1–1.4 DONE and committed (verified 2026-06-11:
  243 pass / 10 skips from repo root; ruff clean on `src tests` + both new scripts —
  the 7 repo-wide ruff hits are pre-existing in old recon/measurement scripts,
  untouched). Next box: **1.5a = GATE G1, ask user** before running the smoke
  build on pre-regen output.

---

## Phase 1 — F1 label uniquing + repair, verified by #4 smoke harness

- [x] **1.1 (lead)** *(done 2026-06-11 — suite 235 pass / ruff clean; one legacy test
      assertion in `tests/test_conversion_agent.py` updated to the EV-qualified label
      format)* `orchestrator.py`: `_qualify_labels(script, map_id, event_id)` —
      idempotent `Map{NNN:03d}_` → `Map{NNN:03d}_EV{eee:03d}_` rewrite (skip when
      already followed by `EV{eee:03d}_`), applied on all three accept paths (LLM,
      memo after `_reinstantiate`, deterministic) before the compile-gate; memo
      stores qualified scripts; `_reinstantiate` prefix rewrite extended to
      `Map{src}_EV{srcev}_` → `Map{cur}_EV{curev}_` + stale guard (old unqualified
      entries: old rewrite then qualification); per-map duplicate-label fail-loud
      assertion at `.pory` flush; `NullBackend` in `backends/__init__.py`.
- [x] **1.2 (Sonnet)** `tests/test_label_uniquing.py`: same-named events → distinct
      labels; goto refs rewritten; idempotence; memo cross-map EV-prefix rewrite;
      `EVnnn`-named events not double-qualified; dup assertion fires.
- [x] **1.3 (Sonnet)** `scripts/regen_outputs.py`: `--maps N…`/`--all-done`,
      `--ce N…`; clears checkpoints/ledger entries (+`CommonEvents.done` when CEs
      targeted); deletes orphaned partial `.pory` (no checkpoint); re-runs
      orchestrator with `NullBackend` (zero spawns by construction, abort loud on
      any miss).
- [x] **1.4 (Sonnet)** `scripts/assembly_smoke.py`: fork worktree on throwaway
      branch; all `.pory`→`.inc`; generated headers (registry `dump_header`,
      `MAP_URANIUM_<N>` dummy aliases, `TRAINER_*` from `intermediate/trainers.json`,
      fail loud on unknown unresolved family); `.include` wiring; `make -j modern`;
      duplicate-symbol/undefined-ref error clustering. Script only — first real
      build is gate G1.
- [ ] **1.5a [GATE G1 — ask user]** smoke on pre-regen output → must flag the
      `Map002_Receptionist_TRADE_Page1` duplicate (red)
- [ ] **1.5b** `regen_outputs.py --all-done` (maps 1–7, 0 spawns) → corpus dup-label
      scan = 0 on regenerated output
- [ ] **1.5c** smoke again → green
- [x] Commits: 1.1+1.2 `dc8e436` · 1.3 `9921285` · 1.4 `ed6e857`

## Phase 2 — #3 cluster-aware triage

- [ ] **2.1 (Sonnet)** `src/rpg2gba/conversion_agent/triage.py` +
      `tests/test_triage.py`: source-join (map|CE, event, page, line) → real command;
      cluster key (code + 355/655 sig head + 111 condition type + 201 mode);
      auto-dispositions (move-routes→phase5, fixed warps→phase5, UNHANDLED-table
      sigs→needs-engine via md-table parse, strip-listed CEs→superseded [tolerant if
      `strip_list.json` absent], `$PokemonGlobal.randomizer` 111→phase8); default
      NOVEL; synthetic-fixture tests.
- [ ] **2.2 (lead)** `run_report` clustered triage + `run_stats.py --novel`;
      `orchestrator.triage()` stays as fallback.
- [ ] **2.3 (lead)** ROADMAP Phase 4 exit criterion → "every *cluster* has a
      decision".
- [ ] **2.4 (lead)** First novel review over the live 241 (Haiku fan-out for source
      snippets; lead judges; spoiler-free report; promote deterministic conclusions
      into rules).
- [ ] Commits: 2.1 `____` · 2.2+2.3 `____` · 2.4 `____`

## Phase 3 — #2 STRIP skip + near-miss Tier-1 rider

- [ ] **3.1 (lead)** `reference/strip_list.json`: CEs 4/5/6, `expect_name`
      assertions, `feature`, `stub_message` = "The Tandor Network is currently
      unavailable." ; `map_events: []`.
- [ ] **3.2 (lead)** `orchestrator.py`: loader (fail-loud name assertion, absent
      file = empty + info log); CE stub path (`# STRIPPED:` + msgbox + end,
      compile-gated, through the blocks ledger, never queued); `(map_id, event_id)`
      skip in `convert_map`; `run_report` counts `# STRIPPED:`; CLAUDE.md §4.3 row.
- [ ] **3.3 (Sonnet)** `tests/test_strip_skip.py`: stub emission+compile; name
      mismatch aborts; absent file OK; ledger idempotence; map-event skip; no queue
      entries.
- [ ] **3.4 (lead)** `regen_outputs.py --ce 4 5 6` → 3 stub blocks in
      `CommonEvents.pory`, compiles rc 0; 27 stale queue entries auto-classify as
      superseded (Phase 2 triage).
- [ ] **3.5 [GATE G2 — ask user]** rider validation: 2–3 frozen-Opus spawns on
      family-1/2 events (dialogue+Wait, dialogue+SE — candidates map 174 ev9,
      map 31 ev9) via `scripts/convert_one_event.py`; confirm strip-as-plumbing.
- [ ] **3.6 (lead)** `deterministic.py` `_dialogue_body` Wait-106/SE-250 tolerance
      per G2 evidence + tests; recount via `scripts/count_deterministic_actual.py` +
      `scripts/near_miss_families.py` (expect ≈ +40 claims, ~93 trivial left).
- [ ] Commits: 3.1+3.2+3.3 `____` · 3.4 `____` · 3.6 `____`

## Phase 4 — Phase-5-track prep (parallel Sonnet fan-out, disjoint files)

- [ ] **4.1 (Sonnet)** PHASE5_PLAN.md §5.5 (move-route census + Q-MR1–5) + §5.6
      (reachability: directed BFS w/ ledge edges, passages oracle, three-mode
      classification, Phase 7 puzzle checklist) + skipped acceptance stubs in
      `tests/test_tileset_converter.py`.
- [ ] **4.2 (Sonnet)** `deserialize.rb` `tilesets` mode: `Tilesets.rxdata` →
      `tilesets.json` (per-tile `terrain_tags` + `passages`) + pytest against the
      real file.
- [ ] **4.3 (Sonnet)** `scripts/map_identity_check.py`: sign-text/BGM/parent-tree/
      dup-group signals vs `map_infos.json`; flag disagreements; identify the
      missing 199th map.
- [ ] **4.4 (lead)** Wiki arbitration (delegated per-location lookups, lead
      synthesizes) → `reference/map_name_overrides.json` (map 7 → Passage Cave is
      the known seed) + CLAUDE.md §4.3 row. Spoiler-free output for the user.
- [ ] **4.5 (lead)** Close out: tick FABLES_DECISIONS checklists, MEMORY.md
      live-state update, final commit; offer to resume `run_bulk.py --timed`.
- [ ] Commits: 4.1 `____` · 4.2 `____` · 4.3 `____` · 4.4 `____` · 4.5 `____`

## Verification gates (end state)

- [ ] Smoke: red on pre-regen output → green post-regen (G1)
- [ ] Triage: ≥ ~80% of the live 241 auto-tagged; novel residue ≈ 30–50
- [ ] `CommonEvents.pory`: exactly 3 `# STRIPPED:` stubs, compiles
- [ ] Pre-filter claims ≈ +40 after rider (post-G2)
- [ ] `tilesets.json` terrain-tag spot-check; identity check flags map 7
- [ ] Clean tree; only `reachability.py` + `map_constants.py` integration left
      (blocked on Phase 5 §5.1–5.4 by design)
