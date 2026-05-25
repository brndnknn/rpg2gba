# Phase 4 — Event → Poryscript (Conversion Agent): Implementation Plan

> Authoritative companion: `ROADMAP.md §Phase 4`, `CLAUDE.md`, `MEMORY.md`,
> `reference/flag_registry_policy.md`. If those conflict with this file, the
> roadmap wins for *what*, this file wins for *how/sequence*. Update this plan
> in-place (don't delete completed sections — strike them through with a one-line
> note) so the next agent can resume after a context cut.

---

## Context

Phase 3 deserialized every Uranium map into per-map event JSON. Phase 4 builds
the **conversion agent** — the runtime LLM component (ROADMAP "Two Agents")
invoked once per event by the orchestrator to translate that JSON into idiomatic
Poryscript. **You (build agent) build the machinery; you never convert events
yourself nor simulate the conversion agent's output** (CLAUDE.md §1, §11).

**This plan covers MACHINERY ONLY.** It builds + tests the deterministic
scaffolding (registry, backends, compile-gate, orchestrator, queue, prompt
assembly, few-shots) and stops *before* any calibration or conversion run. The
staged strategy (calibration → bulk → cleanup) — all driven through the headless
Claude Code backend — and the **`CLAUDE.md §9 #2` manual review gate** (user
approves the frozen prompt + calibration output before any bulk run) are the next
milestone — out of scope here, but the machinery must be ready to feed them.

What "machinery done" looks like:

1. `flag_registry.py` mints/persists/validates `FLAG_*`/`VAR_*` assignments,
   pre-seeded from a tracked map + the Phase 3 sidecars; `validate` CLI green.
2. `ClaudeCodeBackend` (headless `claude -p`) makes a real per-event call and
   parses the structured response; `OllamaBackend` is an optional local fallback;
   both satisfy the `ConversionBackend` ABC.
3. A Poryscript compile-gate wrapper shells to a pinned binary and reports
   success / structured error.
4. The orchestrator runs the full per-event loop (checkpoint → prompt → backend
   → compile → retry-once → accept/queue) idempotently, proven on a **synthetic
   tiny map with a mock backend** (CLAUDE.md §8).
5. `pipeline.py phase4` + `convert-map` are wired; `pytest -m phase4` green;
   full suite green; ruff clean.

---

## Decisions in effect (lock these in)

| # | Decision | Why |
|---|---|---|
| F1 | **Registry is the sole minter of `FLAG_*`/`VAR_*`.** The conversion agent only *proposes*; the orchestrator validates + commits via the registry. Backend-agnostic. | CLAUDE.md §4.3 (one SoT), `flag_registry_policy.md`. Hardcoding/agent-invented names is the #1 way these pipelines break. |
| F2 | **Pre-seed = `reference/essentials_to_emerald_map.md` (authored here) + Phase 3 sidecars** (`uranium_switches.json`/`uranium_variables.json`). Essentials *script-switches* (e.g. `s:pbIsWeekday(...)`, runtime-evaluated) are special-cased: **no `FLAG_*` minted**. | The sidecars are the real seed (MEMORY → Flag Registry Notes). Script-switches are computed, not stored — minting flags for them is wrong (Phase 3 §3.3 finding). |
| F3 | **Mutable state is regenerable + lives under `output/`** (gitignored): registry state JSON, checkpoints, generated `.pory`, `unhandled.jsonl`. The final registry `.h` for the fork is produced at integration (Phase 7), not committed here. **Never hand-edit the registry state mid-run** (CLAUDE.md §6, `flag_registry_policy.md`). | Idempotence + checkpoint recovery (CLAUDE.md §4.2/§4.4). Fix input data or registry logic, never the output. |
| F4 | **Primary programmatic backend = `ClaudeCodeBackend` via headless `claude -p`.** Per event the orchestrator spawns `claude -p --output-format json --system-prompt <frozen>` (no tools, single turn), feeds the event JSON on stdin, parses the structured object. Each spawn is a *separate* CC process = a distinct conversion-agent instance — **never the build-agent session**. `OllamaBackend` is an optional local fallback behind the same ABC. **No `AnthropicAPIBackend`.** | User decision (primary route, headless per-event). A separate subprocess keeps the build/conversion boundary clean (CLAUDE.md §1) while giving Claude-quality output. Diverges from ROADMAP §4.2's three-backend list intentionally. **Budget:** real runs spend Pro/API budget → gated on the user (CLAUDE.md §10). |
| F5 | **Compile-gate is mandatory.** Every event's Poryscript compiles through the pinned `poryscript` binary before acceptance. Compile fail → **retry once** with the compiler error appended to the prompt → second fail → append to `output/unhandled.jsonl`, advance. | ROADMAP §4.3 steps 6–8. Fail-loud (CLAUDE.md §4.5) with full recovery via the queue; a silently-dropped event is a soft-lock 4 phases later. |
| F6 | **Granularity: prompt per-event, file per-map.** The orchestrator iterates events; the agent sees one event's JSON + registry state + few-shots + cheatsheet. Per-map `.pory` aggregates that map's event scripts. | ROADMAP §4.3 (per-event prompt) + §7.1 (`.pory` files per map drop into `data/scripts/`). Per-map files = reviewable diffs + per-map checkpoints. |
| F7 | **Build-agent boundary in tests.** Orchestrator/backend tests use a deterministic **`MockBackend`** returning canned `ConversionResult`s + tiny synthetic maps. No test embeds real or hand-authored "conversion agent" output dressed as machine output. | CLAUDE.md §8 (tiny synthetic map), §11 (don't hand-convert to "show" something). The build agent proves the *pipe*, not the *translation*. |
| F8 | **Scope = machinery only; stop before the §9 #2 gate.** No calibration/bulk/cleanup runs, no frozen prompt declaration, no calibration-set output in this plan. | User decision. The gate is a human checkpoint; the machinery must exist and be tested first. |

---

## Prerequisites & sanity checks

- [x] **P1.** Phase 3 outputs present: `output/uranium-build/maps/MapNNN.json`
      (199), `reference/uranium_switches.json`, `uranium_variables.json`,
      `rgss_event_commands.md`. (Re-run `phase3 --clean` if `output/` is wiped.)
- [ ] **P2.** Poryscript binary obtained: **download a pinned release** from
      `huderlem/poryscript`, place outside the repo, reference via a configurable
      path (env `RPG2GBA_PORYSCRIPT`, default discovered on `PATH`). Needed for the
      compile-gate test (4.2). *New tool — confirm version with the user.*
      **STILL PENDING** — `test_compile_gate` skips until this is done.
- [ ] **P3.** `claude` CLI on `PATH` + authenticated (the headless backend shells
      to it). Needed only when a real run starts (calibration onward), **not** to
      build/test the machinery (tests use `MockBackend`). Ollama at `$OLLAMA_HOST`
      is the optional fallback — defer entirely.
- [x] **P4.** Authored the three reference artifacts:
      `reference/essentials_to_emerald_map.md`, `reference/poryscript_cheatsheet.md`,
      `prompts/few_shot/*.md` (3 examples).

---

## Architecture

### Module layout (additions / fills)

```
src/rpg2gba/conversion_agent/
├── flag_registry.py        # FILL stubs: pre-seed, mint, validate, persist, dump_header
├── orchestrator.py         # FILL stubs: per-event loop, checkpoint, retry, queue
├── prompt_builder.py       # NEW: assemble system.md + registry + few-shot + cheatsheet + event
├── poryscript.py           # NEW: compile-gate wrapper (shell to pinned binary)
├── backends/
│   ├── __init__.py         # exists: ConversionResult + ConversionBackend ABC (keep)
│   ├── claude_code.py      # FILL: PRIMARY — headless `claude -p` subprocess per event (F4)
│   └── ollama.py           # FILL (lower priority): optional local fallback, HTTP + parse
└── prompts/
    ├── system.md           # reconcile lightly with the final output schema
    └── few_shot/           # NEW: author representative examples (one .md per scenario)
reference/
├── essentials_to_emerald_map.md   # NEW: registry pre-seed source (F2)
└── poryscript_cheatsheet.md       # NEW: stable prompt chunk
src/rpg2gba/pipeline.py     # wire phase4 + convert-map (replace NotImplementedError)
```

Reuse the `phase3` wiring in `pipeline.py` (driver→validate→catalog) as the
command-structure pattern; reuse `_resolve_paths()` / `_load_dotenv()`.

### Data flow

```
output/uranium-build/maps/MapNNN.json ─┐
reference/uranium_switches.json        │   ┌─ flag_registry (pre-seed F2) ─┐
reference/uranium_variables.json       ├──►│  state: output/.../flag_state.json
reference/essentials_to_emerald_map.md ┘   └──────────────┬─────────────────┘
                                                          ▼
   per event:  prompt_builder ──► backend.convert_event() ──► ConversionResult
                                                          │  (script, new_flags, new_vars, unhandled)
                                          registry.propose_* (validate/commit)
                                                          ▼
                              poryscript.compile(script) ──► ok? ──► write MapNNN.pory + checkpoint
                                                          └─ fail ─► retry once ─► unhandled.jsonl
```

All mutable artifacts under `output/uranium-build/` (gitignored, idempotent, F3):
`scripts/MapNNN.pory`, `flag_state.json`, `checkpoints/`, `unhandled.jsonl`.

### Key shapes

- **`ConversionResult`** (already defined): `script: str`, `new_flags: dict`,
  `new_vars: dict`, `unhandled: list[dict]`. Reconcile `system.md`'s JSON schema
  (lists of `{switch_id,name,reason}`) with this dataclass during 4.4.
- **Registry state file** (`flag_state.json`): `{switches:{id:name},
  variables:{id:name}, source:{name:"preseed|proposed"}}` — regenerable; hard
  rule F3.
- **`unhandled.jsonl`**: one JSON object per line —
  `{map_id, event_id, page, line, command_code, description, reason}`.
- **Checkpoint**: per-map marker (compiled + validated) so a re-run skips it.

---

## Per-task list

### 4.1 — Flag/variable registry (`flag_registry.py`)
- Implement the stubs: `get_flag`/`get_var`, `propose_flag`/`propose_var`
  (validate → commit), `dump_header`, load/save state (F3).
- Validation rules (from `flag_registry_policy.md`): `FLAG_*`/`VAR_*` convention;
  SCREAMING_SNAKE_CASE; reject empty / `FLAG_TODO` / gibberish; **collision**
  detection (same name → different id, or clash with a known fork constant).
- Pre-seed loader (F2): read `essentials_to_emerald_map.md` + the two sidecars;
  special-case script-switches (`s:` prefix) → no mint.
- `validate` CLI: load state, re-run all validation invariants, exit non-zero on
  any violation.
- **Sub-task 4.1a — author `reference/essentials_to_emerald_map.md`**: the
  canonical Uranium-switch → vanilla-concept pre-seed table (received starter,
  beat gym N, etc.), seeded from the gym/championship/puzzle names already
  catalogued in MEMORY → Flag Registry Notes.

### 4.2 — Poryscript binary + compile-gate (`poryscript.py`)
- Obtain the pinned release (P2); resolve the binary via `RPG2GBA_PORYSCRIPT` env
  / `PATH`; fail-loud with an install hint if absent.
- `compile(script: str) -> CompileResult{ok, stdout, stderr}`: write to a temp
  `.pory`, shell out (reuse the subprocess pattern from `_marshal.py`), capture
  the compiler message for the retry prompt.

### 4.3 — Backends (`claude_code.py` primary, `ollama.py` fallback)
- `ClaudeCodeBackend.convert_event` (PRIMARY, F4): spawn
  `claude -p --output-format json --system-prompt <frozen>` per event (reuse the
  subprocess pattern from `_marshal.py`), feed event JSON + registry state on
  stdin, parse the structured object into `ConversionResult`. Run with **no tools
  / single turn** so the spawned process is a pure text-in/out conversion agent
  (config via flags / a constrained settings file). Fail-loud on malformed JSON
  or non-zero exit. Make the `claude` path + model configurable. Unit-test the
  parser with canned process output (no live spawn).
- `OllamaBackend.convert_event` (optional fallback, lower priority): POST to
  `$OLLAMA_HOST` (`/api/chat`, `format=json`), same parse into `ConversionResult`.
  Build behind the ABC so it's selectable, but it is not the primary path.

### 4.4 — Prompt assembly (`prompt_builder.py`) + stable chunks
- `build_prompt(event_json, registry_state) -> str`: compose `system.md` +
  current registry state + 2–3 few-shot examples + the cheatsheet + the event
  JSON + the unrecognized-command reference. Keep the stable chunk first
  (cache-friendly for any future API use).
- **Sub-task 4.4a — author `reference/poryscript_cheatsheet.md`** (stable prompt
  chunk) and **`prompts/few_shot/*.md`** (one per scenario: give-item-with-fanfare,
  branching-dialogue, trainer-battle, multi-page NPC, self-switch). These are
  *examples of the contract*, not hand-conversions of real Uranium events (F7).
- Lightly reconcile `system.md`'s output schema with `ConversionResult`.

### 4.5 — Orchestrator loop (`orchestrator.py`)
- `__init__(backend, registry, output_dir)`; `convert_map(path)`;
  `convert_all(map_dir)`.
- Per ROADMAP §4.3: checkpoint-skip → load events → per-event prompt → backend →
  parse → registry commit → `poryscript.compile` → retry-once-with-error → write
  `MapNNN.pory` + checkpoint on success, else `unhandled.jsonl`.
- Idempotent + resumable (F3): re-run skips completed maps; partial output never
  corrupts state.

### 4.6 — Unhandled queue + triage
- Append-only `output/unhandled.jsonl` writer; a small `triage` summary
  (counts by command_code / map) to drive the end-of-stage review (ROADMAP §4.4).

### 4.7 — Pipeline wiring (`pipeline.py`)
- Replace the `phase4` + `convert-map` `NotImplementedError`s: construct
  registry + chosen backend + orchestrator; `phase4 [--clean]` runs
  `convert_all`; `convert-map --map-id NNN --backend {claude_code,ollama}`
  (default `claude_code`) runs one map. Provide a `MockBackend` injection point so
  tests never spawn `claude` / hit the network.

---

## Test strategy (`tests/test_conversion_agent.py`, `phase4` marker)

Add a `phase4` marker to `pyproject.toml` (mirror the `phase3` gating in
`conftest.py`). No test calls a live LLM.

1. **Registry.** Pre-seed load; mint + retrieve; collision detection (dup
   name→diff id; clash with fork constant); validation rejects (`FLAG_TODO`,
   empty, bad case); script-switch special-case (no mint); state save/load
   round-trip + idempotent reload; `validate` CLI exit codes.
2. **Backend parse.** `ClaudeCodeBackend` response parser against canned `claude
   -p` JSON output + malformed output (fail-loud), with the subprocess mocked — no
   live spawn. Same for the `OllamaBackend` parser with a mocked HTTP call.
3. **Compile-gate.** `poryscript.compile` returns ok on a hand-written valid
   `.pory`, and `{ok:false, stderr}` on a deliberately broken one. *(Requires the
   P2 binary; skip-marker if absent.)*
4. **Orchestrator integration (the core test, CLAUDE.md §8).** A tiny synthetic
   map + a deterministic `MockBackend`: assert checkpoint-skip on re-run,
   retry-once on a compile failure, `unhandled.jsonl` append on double-failure,
   registry commit of proposed flags, and byte-identical `.pory` across two runs
   (idempotence).
5. **Prompt assembly.** Golden assertion that `build_prompt` output contains each
   required section (system rules, registry state, ≥1 few-shot, cheatsheet, the
   event JSON).

---

## Verification — Phase 4 *machinery* gate (not the §9 #2 gate)

- [x] **V1.** `flag_registry validate` exits 0 — "OK: 8 flags, 5 vars, 34
      script-switches blocked".
- [x] **V2.** Full suite **97 passed / 1 skipped**, ruff clean. (The skip is
      `test_compile_gate`, gated on P2; the orchestrator loop is covered via an
      injected fake compiler + MockBackend.)
- [x] **V3.** Orchestrator integration tests prove the loop end-to-end
      (retry-once, double-failure→queue, proposal commit, checkpoint-skip +
      idempotence) with a fake compiler. The real-binary compile-gate is the only
      piece pending P2.
- [x] **V4.** `pipeline phase4 --clean` (dry) pre-seeds 8 flags + 5 vars, blocks
      34 script-switches, reports 199 maps pending — no live model.
- [x] **V5.** `MEMORY.md` updated (Current Phase, Flag Registry Notes, new Last
      Session Summary; oldest summary evicted to the archive). *Not yet committed —
      pending user.*
- [ ] **V6 (NEXT MILESTONE, not this plan).** `CLAUDE.md §9 #2`: with machinery
      in place, run calibration on 5 maps via the headless Claude Code backend,
      freeze the prompt, and present the calibration output for the user's approval
      **before** any bulk run. Budget-gated (CLAUDE.md §10). *Out of scope here (F8).*

---

## Critical files (read first when resuming)

- `ROADMAP.md §Phase 4` (staged strategy, §4.1–4.5 architecture)
- `CLAUDE.md` §1/§11 (two-agent boundary), §6 (flag registry), §8 (synthetic-map
  test), §9 (#2 gate), §10 (ask-before for prompt-structure / schema / deps)
- `reference/flag_registry_policy.md`
- `MEMORY.md` → Current Phase, **Flag Registry Notes** (pre-seed seed list),
  Open Questions (script-switch caveat)
- `src/rpg2gba/conversion_agent/` (the stubs to fill) + `prompts/system.md`
- `reference/uranium_switches.json` / `uranium_variables.json` /
  `rgss_event_commands.md` (Phase 3 inputs)
- `src/rpg2gba/pbs_converter/_marshal.py` (subprocess-shell pattern to reuse)
- `src/rpg2gba/pipeline.py` (`phase3` wiring = the command pattern)

## Resume-after-context-cut checklist

1. Read `MEMORY.md` end-to-end, then this plan.
2. First unchecked `- [ ]` (Prereqs, then 4.x) is where to start.
3. `pytest -m phase4 -v` for current machinery status.
4. Update checkboxes + add a wrinkle note under each §4.x as you go.
5. **Do not** start calibration / any conversion run — that's the §9 #2 gate,
   gated on the user (F8, V6).
