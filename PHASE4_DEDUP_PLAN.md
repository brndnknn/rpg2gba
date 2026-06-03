# Phase 4 — Conversion Pipeline Dedup Plan

## Context

Phase 4 converts Uranium event JSON → Poryscript by spawning a fresh headless
`claude -p` process **per event** (`backends/claude_code.py`). The machinery is
idempotent at the *map* level (checkpoints) but does **no work de-duplication**:

1. **Common-event call targets are never produced.** The agent emits
   `call CommonEvent_<NNN>` for code 117 (per `prompts/system.md`), but nothing
   reads `common_events.json` — confirmed `pipeline.py` / `orchestrator.py` only
   glob `Map*.json`. So every common-event call is a dangling symbol at assembly
   (same class as the self-switch gap), *and* the dedup benefit of factoring
   shared logic into a common event is lost.
2. **Static prompt context is re-billed on every cold spawn.** The cheatsheet,
   script-call reference, and few-shots are byte-identical for all 5,301 events
   but live in the per-event **user** prompt (stdin), outside whatever caching
   `claude -p` does.
3. **Identical/near-identical events are re-converted from scratch.** Copy-pasted
   NPC idioms differ only by map/event id; each still spends a full spawn.

Budget (Pro usage) is the scarce resource, and these are the levers that decide
whether the bulk `phase4 --run` over 199 maps is affordable. This plan closes the
common-event correctness gap and removes both forms of wasted spend **before** the
prompt is frozen at the §9 #2 gate, so the frozen prompt reflects the final
structure. Every change is **additive / forward-only** — it must never force a
re-spawn of already-converted maps (see "Processing already-converted work").

**Decisions locked with the user:** all three levers, phased safest-first; event
memo uses the **normalized + re-instantiate** strategy (fail-safe to a real spawn);
the memo is **persisted** so finished conversions are reusable without a re-run.

**Constraint:** PHASE4_PLAN locks "no Anthropic API backend" — Lever 2 must work
*within* `claude -p`, i.e. by moving static content into `--system-prompt`, not by
adding a direct-API caching backend.

---

## Phase A — Convert common events once (correctness + dedup)

Lowest risk, highest necessity. Common events use global switches/vars (no
per-event self/temp-switches), so they skip the minting paths entirely.

**Data shape:** `common_events.json` is a list of 100 objects
`{id, name, trigger, switch_id, list}` — a **flat `list`, not `pages`**.

**Changes:**
- `orchestrator.py`: add `convert_common_events(common_events_path: Path)`. For
  each common event with commands, adapt its flat list into the page shape the
  existing helpers expect — `{"id", "name", "pages": [{"list": ce["list"],
  "condition": {}}]}` — then reuse the existing `_convert_event` core
  (prompt → spawn → `_commit_proposals` → compile-gate → retry-once → `_queue`).
  Skip the `_event_self_switches` / `_event_temp_switches` mint loops for common
  events (they have none). Emit all blocks to
  `output/uranium-build/scripts/CommonEvents.pory`; flush per event; checkpoint
  `checkpoints/CommonEvents.done`. Reuse `_event_has_commands` / `_event_codes`.
- Mark the payload with `{"common_event_id": NNN}` so the agent emits a **single**
  block labeled `CommonEvent_<NNN>` (3-digit, matching the `call` target rule
  already in `system.md`).
- `prompts/system.md`: add a short **Common Events** section — "when the input
  carries `common_event_id`, emit exactly one script block labeled
  `CommonEvent_<NNN>`; no page labels." (Prompt-structure change — fine pre-freeze.)
- `pipeline.py`: in `phase4 --run`, convert common events **before** maps
  (`out_dir/common_events.json`). Add a `convert-common-events` debug command
  parallel to `convert_map` (lines 273–304) for single-shot iteration.

**Reuses:** `_convert_event`, `_commit_proposals`, `_queue`, `_event_has_commands`,
`_event_codes` (`orchestrator.py`); `_phase4_backend` / `_phase4_registry`
(`pipeline.py`).

---

## Phase B — Prompt-cache restructure (cut per-spawn token cost)

Move the static tonnage into the cacheable `--system-prompt` so back-to-back
spawns hit Anthropic's server-side prompt cache (5-min TTL). Helps **every** event,
not just duplicates.

**Changes:**
- `prompt_builder.py`: split `build_prompt` (lines 97–119) into
  - `build_static_context(cheatsheet, script_call_ref, few_shots) -> str` — the
    frozen, event-invariant block, and
  - `build_user_prompt(event_json, registry_state, command_ref) -> str` — only the
    per-event-variable content (filtered command ref, registry state, event JSON).
- `pipeline.py::_phase4_backend` (line 199): compose the backend's `system_prompt`
  = `load_system_prompt()` + `build_static_context(...)`. This becomes the stable
  `--system-prompt` for `claude_code` (fully cacheable) and the system message for
  `ollama`.
- `backends/claude_code.py`: add lightweight **measurement** — have
  `_parse_response` read `usage.cache_read_input_tokens` /
  `cache_creation_input_tokens` from the `claude -p` JSON envelope and log them, to
  confirm caching actually engages (empirical check for the "does `claude -p` cache
  a custom system prompt" uncertainty). If it doesn't engage, the restructure is
  still correct and harmless; note the result for the gate.

**Gate note:** changes prompt *structure* (content moves system⇄user). Behavior
should be equivalent (same text, different channel) but isn't provably identical —
**re-run the calibration map(s) after this** to confirm quality before freezing.

---

## Phase C — Event memoization (cut spawn count), persisted

Skip the spawn when an event is structurally identical to one already converted.
**Fail-safe:** any doubt → fall through to a real spawn.

**Key (narrowed for safety):** normalize out **only** `map_id` and the event's own
`id`; keep `name`, dialogue, and all command content in the key. Because the agent
derives script-block labels from the event *name* (kept in the key), the **only**
map/event-derived tokens left in a reused script are the self/temp-switch flag
names — produced by the deterministic `self_switch_flag_name` /
`temp_switch_flag_name` (`flag_registry.py:60,70`), which we can rewrite exactly.

**Storage — persistent, prompt-fingerprinted manifest:**
- `self._memo: dict[str, MemoEntry]` backed by
  `output/uranium-build/memo_manifest.json`:
  `{ "prompt_fingerprint": "<12-hex>", "entries": { "<hash>": {script, new_flags,
  new_vars, unhandled, src_map, src_event} } }`.
- `prompt_fingerprint = sha256(system.md + static_context)[:12]`. On load, if the
  fingerprint ≠ current, **discard the manifest** (don't reuse old-prompt outputs
  under a new prompt). Saved incrementally next to `flag_state.json` so a mid-run
  stop preserves it. This is what makes already-converted work reusable across runs
  (see next section).

**Loop changes (all in `orchestrator.py`, `_convert_event` line 108):**
- `key = _memo_key(payload)` = `sha256(json.dumps(payload − map_id − id,
  sort_keys=True))`.
  - **Miss:** spawn as today; on accept, store the MemoEntry (and persist).
  - **Hit:** `_reinstantiate(entry.script, src→cur)` — regex-rewrite
    `FLAG_MAP{srcm:03}_EVENT{srce:03}_SS{L}` / `_TS{K}` → current map/event for each
    letter/key the event uses. **Guard:** assert no
    `FLAG_MAP{srcm:03}_EVENT{srce:03}_` substring survives; then run the existing
    `compile_fn`. Either check fails → discard the hit, fall through to a real spawn
    (fail-safe). On success, replay `_commit_proposals(entry)` and the
    `mint_self_switch` / `mint_temp_switch` loops for the **current** map/event (so
    the registry stays correct), then return the re-instantiated script.
- Only accepted scripts are memoized (queued events have no script to reuse).

**Why correct:** proposals are keyed by integer switch/var IDs that live in the
hashed content, so a key match implies identical proposals; self/temp-switch mints
run per-event regardless of the memo; the compile gate + stale-token guard catch any
unexpected divergence before a reused script is accepted.

---

## Processing already-converted work without a full re-run

The pipeline is already **forward-only**: `convert_map` skips any map with a
`checkpoints/MapNNN.done` (`orchestrator.py:78`). None of A/B/C re-runs finished
maps. Concretely:

- **Phase A is purely additive.** Run `convert-common-events` once. Existing map
  `.pory` files are untouched; their `call CommonEvent_<NNN>` references now resolve.
  No map re-spawn.
- **Phase B/C are forward-only.** Pending maps pick up the restructure + memo
  automatically; finished maps stay valid (their output already compiled and is on
  disk). No re-spawn of done maps.
- **The already-converted Map002** can't retroactively seed the memo (no stored
  per-event hashes for output produced before the manifest existed). Two cheap,
  bounded options — **never a full re-run**:
  1. **Leave it.** It's checkpointed and skipped; costs nothing. The 197 pending
     maps build the manifest among themselves during the bulk run.
  2. **Re-validate it once** under the new prompt structure — which Phase B's gate
     note already calls for. That single, one-map run *also* writes Map002's events
     into the persistent manifest, so its conversions become reusable by every
     pending map. Two birds, one cheap run.
- **Selective re-process of genuinely-stale maps** (e.g. a map converted before a
  fix landed): delete only that `checkpoints/MapNNN.done` and run
  `convert-map --map-id N` (it already unlinks the checkpoint, line 300–302). The
  registry is append-only and idempotent — re-proposing the same id→name returns the
  existing name, re-minting the same self/temp-switch key is a no-op — so a
  single-map re-run won't corrupt shared state. For a *clean* registry re-process,
  restore `flag_state.baseline.json` first.
- **Never required:** a corpus-wide `phase4 --clean`. `--clean` is only for a
  deliberate from-scratch rebuild (it wipes scripts/checkpoints/registry state,
  `pipeline.py:177-183`).

---

## Cross-cutting

- **Sequencing:** A → B → C, each independently shippable and tested. B and C must
  both land before the bulk `phase4 --run`; A must land before any fork assembly.
- **Gate:** B and A both touch prompt structure — lock them in, then re-run
  calibration (Map002) to confirm quality before the §9 #2 freeze. No active run
  exists now, so no "don't edit prompt mid-run" conflict.
- **Memory:** update `MEMORY.md` (Current Phase + Key File Notes for the
  common-event pass and the persistent memo).

## Verification

- `pytest` (full suite) + `pytest -m phase4` (real poryscript) green; `ruff check`
  clean (src + tests).
- **New unit tests** (`tests/test_conversion_agent.py`, MockBackend + fake compiler,
  no live binaries):
  - *Phase A:* synthetic 2-entry `common_events.json` → `CommonEvents.pory` has
    `CommonEvent_<NNN>`-labeled blocks; checkpoint written; a failing entry queues.
  - *Phase B:* `build_user_prompt` output excludes the cheatsheet;
    `build_static_context` contains it + the few-shots; backend system prompt =
    system.md + static.
  - *Phase C:* two events identical except map/event id → backend invoked **once**;
    the second's script carries the *current* self-switch names; a forced stale token
    (guard-fail) falls back to a real spawn (call count increments); manifest
    persists + reloads, and a fingerprint mismatch discards it.
- **Dry check:** `phase4 --clean` (no `--run`) still reports 8 flags / 5 vars /
  34 script-switches blocked / 199 maps pending — structure unchanged.
- **Budget-gated live confirmation (user-approved):** `convert-common-events` on a
  couple of common events; then a 2-map live run where the maps share a copy-pasted
  event, to observe a real cross-map memo hit and the logged
  `cache_read_input_tokens`. Spends budget → confirm with the user first.
