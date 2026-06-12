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

- **Current position:** Phase 1 COMPLETE except 1.5c-green (blocked on non-F1
  findings, see "G1 findings" below — user decisions needed). G1 run 2026-06-12
  with user OK: smoke red pre-regen, dup flagged; maps 1–7 regenerated at zero
  spawns; corpus dup scan = 0; targeted re-assembly of Map002 shows the dup gone.
  244 pass / 10 skips; ruff clean on `src tests` + new scripts (7 repo-wide hits
  pre-existing in old recon scripts).
- **Phase 2 COMPLETE (2026-06-12):** 274 pass / 10 skips. Live triage: 214 queued,
  29 novel clusters reviewed (`reference/novel_cluster_review.md`).
- **Phase 3 3.1–3.3 DONE (2026-06-12, `e394986`):** 284 pass / 10 skips, ruff clean.
  STRIP skip wired (CEs 4/5/6 stub-emitted, never queued). Next: **3.4 regen CEs
  4/5/6** (NullBackend, 0 spawns) → **3.5 GATE G2** (2–3 frozen-Opus rider spawns,
  needs user OK) → 3.6 deterministic Wait/SE tolerance. Three §10 calls + the G1
  findings still awaiting user decisions.

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
- [x] **1.5a [GATE G1 — user OK'd 2026-06-12]** smoke on pre-regen output → RED.
      Full build died first at the CE-084 `\$` preproc error (see findings), so the
      dup evidence came from a targeted run of the fork's exact event_scripts.s
      toolchain (preproc|cpp|preproc|as) with only Map002.inc wired:
      ``Map002.pory:116: Error: symbol `Map002_Receptionist_TRADE_Page1' is
      already defined`` ✓
- [x] **1.5b** regen maps 1–7 (`--maps 1 2 3 4 5 6 7`, NullBackend, **0 spawns**)
      → corpus dup-label scan **0** (103 labels / 8 .pory; `scripts/dup_label_scan.py`).
      Two latent bugs fixed en route, see commits: (a) 1.1's `_reinstantiate`
      stale-guard bailed on same-(map,event) replay (own flag tokens misread as
      stale → every self/temp-switch event would have re-spawned); (b) 1.3's
      `run_replay` used `convert_all`, which would have walked into unconverted
      maps 8+ and mutated memo/registry mid-bulk-run — now converts selected ids only.
- [ ] **1.5c** smoke green — **BLOCKED on non-F1 findings** (below). F1 scope is
      verified: targeted Map002 re-assembly post-regen shows the dup GONE; residual
      errors are exactly the recorded findings. Full-corpus green needs the findings
      dispositioned first (user call; most look deterministic-repair-able).

### G1 findings (all pre-existing agent output, compile-gate-green, assembly-red)

All from the §9-reviewed first corpus (CommonEvents + maps 1–7); queue/triage fodder
for Phase 2, possible deterministic post-accept repairs (would need design OK):

1. **CE-084 `\"` escape** (`CommonEvents.pory:285`, `msgbox("\"Garroooough!\"")`):
   poryscript doesn't support `\"` — silently splits into garbage text blocks; GAS/
   preproc dies on `unknown escape '\$'`. **This single error aborts the whole
   event_scripts.s assembly** (preproc exits before `as` runs), masking everything
   else. Fix needs a re-spawn (CE, not memoised) or content decision.
2. **`healparty` ×2** (Map002 EV001): not a fork command (correct:
   `special(HealPlayerParty)`). Poryscript passes unknown commands through raw.
3. **Bare `call CommonEvent_NNN` ×3** (Map002 → CEs 4/5/6, the strip-list CEs):
   poryscript splits into two raw statements; correct form `call(CommonEvent_NNN)`.
4. **Constant-naming drift, 4 families** (unresolved at assembly; smoke now
   dummy-defines them via opt-in `--define-unresolved`, each logged as FINDING):
   - `ITEM_TURTICKET` / `ITEM_KELLYNLETTER` — agent used internal names; Phase 2
     minted `ITEM_TUR_TICKET` (494) / `ITEM_KELLYNS_LETTER` (572). Deterministic map.
   - `TRAINER_<CLASS>_<NAME>` scheme (7 tokens seen) ≠ registry `TRAINER_<NAME>_<ID>`
     scheme — Phase 5/7 reconciliation.
   - `MULTI_*` ×4 — agent-invented multichoice ids; need `gMultichoiceLists`
     entries (Phase 5/6).
   - `FLAG_MAP007_EVENT019_SSA` — agent setflag for a self-switch the orchestrator
     never minted (set is inside a script call, not code 123) — mint-derivation gap.
   (Counts above are from the full 9-file scan incl. the since-deleted Map008
   orphan partial; the live 8-file corpus shows a subset. All return as maps convert.)
- [x] Commits: 1.1+1.2 `dc8e436` · 1.3 `9921285` · 1.4 `ed6e857`

## Phase 2 — #3 cluster-aware triage

- [x] **2.1 (Sonnet)** `src/rpg2gba/conversion_agent/triage.py` +
      `tests/test_triage.py` (28 tests). As spec'd, plus measured deviations: queue
      `line` is LLM-reported and unreliable (1-based/0-based/wrong mix) → join by
      command_code within the page, line as hint, 355/655 description-naming
      heuristic for multi-match pages; clusters group by (key, disposition).
- [x] **2.2 (lead)** `run_report` clustered triage (legacy `triage()` fallback) +
      `run_stats.py --novel`.
- [x] **2.3 (lead)** ROADMAP Phase 4 exit criterion → "every *cluster* has a
      decision".
- [x] **2.4 (lead)** First novel review DONE → **`reference/novel_cluster_review.md`**
      (Haiku fan-out skipped — descriptions sufficed). Live queue: **214** entries
      (not 241 — the old count held ~27 dupes from the Map004 interrupt-resume;
      two orchestrator queue-corruption bugs found + fixed en route: append-only
      re-conversion duplication, and memo-reused entries logging the SOURCE event's
      identity). Clustered: 69 move-route + 31 warp + 25 needs-engine + 2 phase8 +
      87 novel/29 clusters. Three §10 calls queued for the user (racing minigame,
      dream sequence, VS-intro — see review doc); ~10 novel entries auto-supersede
      when 3.1's `strip_list.json` lands; `healparty` traced to a bug in the
      **frozen** `uranium_script_calls.md:54` (`pbHealAll → healparty` — not a fork
      command; fix post-run).
- [x] Commits: 2.1 `f322f64` (+`389e116` queue fixes) · 2.2+2.3 `5f9f596` · 2.4 `2511535`

## Phase 3 — #2 STRIP skip + near-miss Tier-1 rider

- [x] **3.1 (lead)** `reference/strip_list.json`: CEs 4/5/6, `expect_name`
      assertions, `feature`, `stub_message` = "The Tandor Network is currently
      unavailable." ; `map_events: []`.
- [x] **3.2 (lead)** `orchestrator.py`: loader (fail-loud name assertion, absent
      file = empty + info log); CE stub path (`# STRIPPED:` + msgbox + end,
      compile-gated, through the blocks ledger, never queued); `(map_id, event_id)`
      skip in `convert_map`; `run_report` counts `# STRIPPED:`; CLAUDE.md §4.3 row.
      (Existing `test_convert_common_events*` shift CE ids → 104/105/107 since the
      orchestrators now load the real strip_list.)
- [x] **3.3 (Sonnet)** `tests/test_strip_skip.py` (10): stub emission+compile; name
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
- [ ] Commits: 3.1+3.2+3.3 `e394986` · 3.4 `____` · 3.6 `____`

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

- [ ] Smoke: red on pre-regen output → green post-regen (G1) — *red ✓ + dup-free ✓
      2026-06-12; full green blocked on the G1 findings (non-F1 scope)*
- [x] Triage: live queue deduped to 214; 59% auto-tagged by entries (strip rule
      inactive until 3.1; ≥70% expected after) — novel residue = **29 clusters**
      (within the 30–50 design band; per-cluster is the review-labor metric), all
      reviewed in `reference/novel_cluster_review.md`
- [ ] `CommonEvents.pory`: exactly 3 `# STRIPPED:` stubs, compiles
- [ ] Pre-filter claims ≈ +40 after rider (post-G2)
- [ ] `tilesets.json` terrain-tag spot-check; identity check flags map 7
- [ ] Clean tree; only `reachability.py` + `map_constants.py` integration left
      (blocked on Phase 5 §5.1–5.4 by design)
