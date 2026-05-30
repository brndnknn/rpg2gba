# Phase 4 Calibration Plan: Get the conversion-agent run to succeed

## Context

Phase 4 machinery is code-complete (100 tests pass, ruff clean, poryscript 3.6.0 wired).
But the **one real calibration attempt** — `convert-map` on Map002 (the Pokémon Center)
via the headless `claude -p` backend — failed and produced no reviewable output. The
`output/uranium-build/unhandled.jsonl` from that run shows the three root causes:

1. **EV001 timed out twice at 300s** (62-command branching event). Timeout is now 600s in
   code but *untested*.
2. **The agent has no guidance for Uranium's custom `pbXxx` script calls** (command code
   355/655) and queues them. `pbCallBub` alone is **3,456 instances = 43% of all 7,961
   script-call invocations** — with no handling, nearly every event queues. This is the
   real blocker, and it's prompt/content work, not machinery.
3. **The run pre-dated the incremental-flush fix**, so nothing was saved to inspect.

We confirmed `pbCallBub` is purely cosmetic (sets `$talkingEvent`/`$Bubble`/`$Numbubbles`
globals an emote routine reads later — `170__PSystem_Utilities.rb:2506`), so it can be
stripped. The goal of this plan is to **fix everything we know is broken before spending
any more Pro usage on a run**, then run a cheap smoke test, then get Map002 fully
converting and compiling — the substance of the §9 #2 calibration gate.

**Decisions (from the user):**
- Strip `pbCallBub` and other cosmetic calls silently *for now*; revisit emote fidelity
  later (open follow-up).
- Pro subscription → **no `--max-budget-usd`** (it forces API-key auth and bypasses Pro
  OAuth). Per-event 600s timeout is the only guardrail.
- **Compare both models** (`claude-sonnet-4-6` vs `claude-opus-4-8`) on the same events —
  don't just default to Sonnet. The `--model` knob is the mechanism (Part B).
- Sequence: smoke test → Map002 until green → other calibration maps later.

---

## Part A — Prompt & reference content (the core fix)

### A1. New reference: `reference/uranium_script_calls.md`
Author a translation table for the **top ~40 script-call signatures** (covers ~80%+ of the
7,961 invocations; data in `reference/rgss_event_commands.md`). Each row tagged one of:
- **MAP** — confident Poryscript equivalent (give the equivalent).
- **STRIP** — cosmetic / no game-state effect (emit nothing).
- **UNHANDLED** — no safe equivalent / needs-engine (agent must queue it; do **not** guess
  a Poryscript special we can't verify — honors §4.5 fail-loud / §9).

Concrete tags (initial; user reviews at the gate):
- STRIP: `pbCallBub`, `set_fog2`, `XInput.vibrate`, `$game_map.need_refresh`,
  `pbRemoveDependency2` (cosmetic/engine-bookkeeping).
- MAP: `setTempSwitchOn`/`pbSetSelfSwitch`→`setflag` (per-event flag), `pbSet`/
  `$game_variables[N]=`→`setvar VAR_*`, `Kernel.pbReceiveItem`/`Kernel.pbItemBall`→
  `giveitem`, `pbPokemonMart`→`pokemart`, `Kernel.pbSetPokemonCenter`→`setrespawn`,
  `pbTrainerIntro`/`pbTrainerEnd`→trainer intro/defeat text inside `trainerbattle`.
- UNHANDLED (verify before mapping): `pbPokeCenterPC`, `pkmn.pbLearnMove`,
  `pbPhoneRegisterBattle`, `pbBerryPlant`, `pbChoosePokemon`,
  `Kernel.pbRockSmashRandomEncounter`, `pbCaveEntrance`/`pbCaveExit`, `pbBridgeOn`,
  `pbSetEventTime`, `Kernel.pbNoticePlayer`.
- The ~210-signature long tail is intentionally undocumented → agent queues them (expected;
  that's what `unhandled.jsonl` is for).

When a tag is uncertain, read the call's definition in `reference/scripts_dump/` (grep
`def <name>`) before deciding MAP vs UNHANDLED.

### A2. Wire the reference into the prompt
- `src/rpg2gba/conversion_agent/prompt_builder.py`: add `load_script_call_reference(reference_dir)`
  (mirrors `load_cheatsheet`, lines ~41–46) and include it as a **stable chunk** in
  `build_prompt()` (lines ~80–100), e.g. a `# Uranium script-call reference` section.
- `src/rpg2gba/conversion_agent/orchestrator.py`: cache it at init alongside `self._cheatsheet`
  (lines ~56–58) and pass into `build_prompt`.
- Keep it tight (~40 rows) — it's re-billed on every cold spawn, same concern that drove the
  per-event command-ref trim.

### A3. Fix and extend `src/rpg2gba/conversion_agent/prompts/system.md`
- **Stale refs (lines 3–4):** `src/conversion_agent/...` → `src/rpg2gba/conversion_agent/...`;
  `AGENTS.md` → `CLAUDE.md`.
- Add a short section pointing at the script-call reference and stating the rule: *calls
  tagged STRIP emit nothing; MAP calls use the given equivalent; only flag `unhandled` for
  calls absent from the reference or tagged UNHANDLED.* Add the strip-cosmetic rule
  explicitly so the agent stops queueing `pbCallBub`.

### A4. Add few-shot(s) targeting Map002
`src/rpg2gba/conversion_agent/prompts/few_shot/` (loaded alphabetically):
- `pokemon_center_heal.md` — the EV001 pattern: `Kernel.pbSetPokemonCenter` + nurse
  dialogue + `pbCallBub` (shown stripped) + a yes/no choice branch (codes 111/411/412) +
  `healparty`. This is the exact shape that timed out.
- Optionally a PC example (EV003 `pbPokeCenterPC`) consistent with whatever A1 decides for
  that call.

---

## Part B — Machinery (small)

### B1. `--model` knob on `convert-map` / `phase4` (enables the model comparison)
`src/rpg2gba/pipeline.py`: thread `--model` through `_phase4_backend()` (lines ~196–207)
into `ClaudeCodeBackend(system_prompt, model=...)`, defaulting to `claude-sonnet-4-6`. This
is the mechanism for the Sonnet-vs-Opus comparison in Part D. **No budget plumbing** (Pro).
Timeout left at 600s; only revisit if a model still times out after the prompt fixes (the
prompt work should reduce model flailing, the likely timeout cause).

---

## Part C — Pre-flight verification (no Pro usage)

Run in order; all are free (no `claude` spawn):
1. `ruff check` + `ruff format --check` on touched files.
2. `pytest` — full suite must stay green (100 pass). Adjust prompt-assembly tests in
   `tests/test_conversion_agent.py` (the `test_build_prompt_has_sections` family, lines
   ~263–294) to expect the new script-call section.
3. `pytest -m phase4` — exercises `test_compile_gate` against the **real** poryscript 3.6.0
   binary; confirms `RPG2GBA_PORYSCRIPT` + `-cc`/`-fc` configs resolve. (This is the only
   end-to-end check of the compiler before we rely on it as the gate.)
4. `python -m rpg2gba.pipeline phase4 --clean` (dry, no `--run`) — confirm pre-seed still
   reports 8 flags + 5 vars, 34 script-switches blocked, 199 maps pending after the
   reference/prompt changes.
5. **Pick the smoke-test map:** scan `output/uranium-build/maps/*.json` for the map with the
   fewest events / smallest command count (a one-line sign NPC) to validate the pipe for the
   least possible spend.

---

## Part D — The gated run (spends Pro usage — proceed only on user go-ahead)

Prompt files are edited **between** runs only, never during one (CLAUDE.md §1/§5).

1. **Smoke test (Sonnet first):** `convert-map --map-id <trivial> --model claude-sonnet-4-6`.
   Verify the full pipe end-to-end: `claude` spawns, response parses, script compiles
   through poryscript, `.pory` + registry flush to disk. Catches machinery bugs cheaply.
   Then repeat with `--model claude-opus-4-8` to confirm both model paths work.
2. **Map002 — iterate to green (on Sonnet):** `convert-map --map-id 2 --model claude-sonnet-4-6`.
   Inspect the `.pory`, registry deltas, and `unhandled.jsonl`. Iterate `system.md` /
   few-shots / `uranium_script_calls.md` **between** runs until: EV001/EV003/EV004 convert
   and compile, `pbCallBub` no longer queues, `unhandled.jsonl` is long-tail-only.
3. **Model comparison on Map002:** once the prompt is stable, run Map002 through **both**
   models from an identical registry baseline and compare. Method to keep it fair: snapshot
   `output/uranium-build/flag_state.json` and force-reconvert (the checkpoint delete in
   `convert-map` already does this); run model A → copy its `Map002.pory` + the new
   `unhandled.jsonl` lines + registry delta aside → restore the `flag_state.json` snapshot →
   run model B → capture the same. Compare on: (a) compile pass/fail, (b) # unhandled
   (tail-only?), (c) Poryscript idiom/readability, (d) flag/var naming quality, (e) latency
   vs the 600s timeout. This comparison is what informs the frozen-model choice at the gate.
4. **Then** expand to the rest of the calibration set with the chosen model (deferred per
   user).
5. Freeze the prompt **and the model**; present Map002 output (both models' results) for the
   **§9 #2 manual review gate** before any bulk `phase4 --run`.

---

## Verification (definition of done for this plan)

- `pytest` green (100+), `pytest -m phase4` green, ruff clean.
- `phase4 --clean` dry counts unchanged (8/5/34/199).
- Smoke-test map: `.pory` emitted, compiles, registry/flush correct.
- Map002: all events convert + compile; `unhandled.jsonl` free of `pbCallBub` and of any of
  the calls tagged MAP/STRIP in the reference; remaining queue entries are expected
  long-tail UNHANDLED calls only.
- Map002 run through **both** `claude-sonnet-4-6` and `claude-opus-4-8` from an identical
  registry baseline, with a side-by-side comparison (compile, unhandled count, idiom,
  naming, latency) to inform the frozen-model choice.

## Open follow-ups (record in MEMORY.md, not done now)
- **Revisit `pbCallBub` emote fidelity** — currently stripped; user wants to reconsider
  mapping it to a pokeemerald emote/field-effect later.
- Verify the UNHANDLED-tagged calls' real semantics (`pbPokeCenterPC`, `pkmn.pbLearnMove`,
  etc.) against `scripts_dump/` and decide MAP vs needs-engine as the calibration corpus
  grows.
