# CLAUDE.md

**Audience:** This file is for the AI agent assisting development in the `rpg2gba` repository. If you are reading this, you are the **build agent**. Read this entire file before making changes. Re-read it when you've been away from the repo for a while.

**Authoritative companion document:** `ROADMAP.md`. When this file and the roadmap conflict, the roadmap wins for *what* to build; this file wins for *how* to build it.

---

## 1. Context You Need

### What rpg2gba is

A pipeline that converts RPG Maker XP / Pokémon Essentials fan games into playable GBA ROMs based on `pokeemerald-expansion`. The first test target is Pokémon Uranium. The pipeline tooling is the long-term deliverable; any specific ROM is a byproduct.

### Two agents, one project

There are two AI agents in this project. **You are one of them.** Do not confuse your role with the other.

- **You are the build agent.** You work on rpg2gba's Python, Ruby, and C code. You read this file. You have full repo access and can run tests, refactor, and propose new features. You behave like a developer joining the project.
- **The other agent is the conversion agent.** It is a *runtime component of rpg2gba itself* — an LLM, **retired as the conversion spine (2026-06-18) and kept only as a hand-invoked tool for the irreducible tail** (branch-heavy story logic, novel embedded Ruby the deterministic transpiler can't interpret). It has no awareness of the codebase. Its prompt lives in `src/rpg2gba/conversion_agent/prompts/system.md` — **no longer frozen** (see §7) — which you maintain like any other source file.

You will never run as the conversion agent. The conversion agent will never run as you. If you find yourself uncertain which role you're in, you're the build agent — the conversion agent doesn't read CLAUDE.md.

### Your operator

The user is a developer comfortable with Python, Swift, C, CLI tooling, and GBA homebrew. They have prior experience with Pokémon decomp projects and RPG Maker. They prefer concise technical assessments over verbose hedging. They will tell you when they want more depth.

---

## 2. Your Role and Boundaries

### What you do

- Write and maintain Python code for the deterministic converters (PBS parsing, map deserialization orchestration, tileset conversion)
- Write and maintain Ruby code for the rxdata deserializer
- Write and maintain C code in the `pokeemerald-expansion` fork for custom engine features (Phase 6 work)
- Maintain the conversion agent's prompts and few-shot examples as source artifacts
- Write tests, run them, and fix failures
- Investigate Uranium's source to answer questions about its data and behavior
- Propose architectural changes when you spot problems

### What you do NOT do

- **Do not roleplay the conversion agent or hand-fake its outputs.** The deterministic transpiler is yours to write and run; the LLM tail tool, when invoked, runs at pipeline runtime, not during your editing session. You write both — you don't hand-author an LLM "conversion" to show what it would do.
- **Do not modify files in `output/` directly.** Those are generated artifacts. If they're wrong, fix the converter that produced them and re-run.
- **Do not invent pokeemerald-expansion C constants outside the flag registry.** See section 6.
- **Do not commit the Uranium source tree, any base ROM, build artifacts, or pipeline-generated output.** The `pokeemerald-expansion` *decomp source* is the one exception — it is **vendored in `engine/`** (see `engine/RPG2GBA_VENDOR.md`); the base ROM, Uranium assets, `engine/build/`, and the assembler's generated output under `engine/` are still **never** committed (gitignored).
- **Do not bypass the manual review gates.** See section 9.
- **Do not claim the engine can't do something without checking the fork.** No "needs custom C" / "no native equivalent" without a grep/read of `$RPG2GBA_POKEEMERALD` that proves it (§4.7). The fork is on disk; verifying costs seconds.

---

## Memory System

You have a persistent memory file at `MEMORY.md` in the repo root. It's your
running notes on project state — what's done, what each key file does, what's been
decided, what's open — so you don't re-scan the whole repo every session. The full
protocol and section template live in `reference/memory-protocol.md`; read it once
to learn the structure. The rules that bind every session:

- **Read MEMORY.md first, before any other file. Update it before you finish.**
- Make **targeted edits, not full rewrites** — don't disturb sections you aren't changing.
- Keep entries concise. A Key File Note longer than two sentences belongs in `reference/` as a proper doc.
- Don't duplicate what's already in CLAUDE.md or ROADMAP.md — link instead.
- **Evict stale entries.** Keep at most the 2 most recent Last Session Summary entries and only *live* Open Questions in MEMORY.md; move retired summaries and resolved-question breadcrumbs to `reference/memory-archive.md`. Before retiring a resolved question, confirm its conclusion is captured in Decisions Made or Uranium-Specific Discoveries.
- MEMORY.md is committed to git; don't gitignore it.

---

## 3. Repository Layout

```
rpg2gba/
├── README.md                   # Public-facing project description
├── ROADMAP.md                  # The plan; read for "what next"
├── CLAUDE.md                   # This file
├── pyproject.toml
├── src/
│   └── rpg2gba/
│       ├── pbs_converter/          # Phase 2: deterministic Python
│       │   ├── pokemon.py
│       │   ├── moves.py
│       │   ├── items.py
│       │   ├── trainers.py
│       │   ├── abilities.py
│       │   └── encounters.py
│       ├── rxdata_deserializer/    # Phase 3: Ruby
│       │   └── deserialize.rb
│       ├── conversion_agent/       # Phase 4: transpiler + classifiers; LLM tail-only
│       │   ├── orchestrator.py     # The driver loop
│       │   ├── flag_registry.py    # Single source of truth for FLAG_*/VAR_* names
│       │   ├── backends/
│       │   │   ├── ollama.py
│       │   │   └── claude_code.py
│       │   └── prompts/
│       │       ├── system.md       # Tail-tool prompt (no longer frozen)
│       │       └── few_shot/       # Example conversions, one .md per scenario
│       ├── tileset_converter/      # Phase 5
│       └── pipeline.py             # Top-level orchestration entry point
├── tests/
│   ├── test_pbs_pokemon.py     # Round-trip and golden-output tests
│   ├── ...
├── reference/                  # Hand-authored docs the build agent and humans read
│   ├── poryscript_cheatsheet.md
│   ├── rgss_event_commands.md
│   ├── essentials_to_emerald_map.md
│   └── uranium_id_map.json     # Authoritative ID mapping table
├── scripts/                    # One-off utilities, debugging tools
├── engine/                     # Vendored pokeemerald-expansion (pinned); custom C lives here
└── output/                     # Generated artifacts; gitignored
    └── uranium-build/
```

### Things outside this repo you may need to read

- The Uranium source tree (path configured in env var `RPG2GBA_URANIUM_SRC`) — stays external; its contents never enter git.

### The vendored engine (`engine/`)

The `pokeemerald-expansion` fork is **vendored** in `engine/`, pinned at upstream `21c24202` (see `engine/RPG2GBA_VENDOR.md`). Custom engine C (Phase 6, plus the slice's spawn-override/intro-skip) lives there in version control — no longer an external sibling clone. `RPG2GBA_POKEEMERALD` is the path the pipeline uses; the **cutover** to point it at `engine/` (which needs a one-time build to generate the headers the pipeline reads, and a re-assemble so the custom C compiles) is a follow-up — until then it still points at the old external clone. `engine/build/` and the assembler's generated output under `engine/` are gitignored.

---

## 4. Operating Principles

These are non-negotiable. If a request seems to require breaking one, stop and ask.

### 4.1 The deterministic transpiler is the spine; the LLM is for the irreducible tail

The whole pipeline is deterministic: PBS data, map deserialization, tileset/layout, **and event→Poryscript** (a command→Poryscript transpiler — `BUILD_PLAN.md §3`). The LLM is **not** the conversion spine; it is a hand-invoked tool for the genuinely irreducible tail (branch-heavy story logic, novel embedded Ruby), and even then its output is reviewed and verified against the fork (§4.7).

When you're tempted to reach for the LLM, the answer is almost always "write/extend the transpiler instead." The transpiler fails *loud and bounded* (an explicit unhandled queue you can read to completion); the LLM fails *silent and unbounded* (compile-clean-but-wrong). For a get-it-right-once corpus, the former wins.

### 4.2 Idempotence

Every converter must be safely re-runnable from scratch. If running it twice produces different output (other than timestamps), that's a bug. If running it on partially-completed output corrupts state, that's a bug. The orchestrator depends on this for checkpoint recovery.

### 4.3 One source of truth per concept

| Concept | Source of truth |
|---|---|
| `SPECIES_*` constants | `src/rpg2gba/pbs_converter/pokemon.py` output |
| `MOVE_*` constants | `src/rpg2gba/pbs_converter/moves.py` output |
| `FLAG_*` / `VAR_*` names | `src/rpg2gba/conversion_agent/flag_registry.py` |
| Uranium internal name → expansion constant | `reference/uranium_id_map.json` |
| Tile substitution table | `reference/tileset_map.json` |
| Whole-artifact STRIP decisions (CE ids / whole maps / map events) | `reference/strip_list.json` |
| Corrected map identity / display name (overrides `MapInfos`) | `reference/map_name_overrides.json` |

Anything else that *uses* these reads from the source of truth. Nothing else *creates* them.

### 4.4 Output goes in `output/`

All generated files land under `output/`. The directory is gitignored. Wiping it and re-running the pipeline must produce identical results from identical inputs.

### 4.5 Fail loud

When a converter encounters something it doesn't recognize — an unexpected PBS field, an unknown event command, a missing sprite — it should fail loudly with a precise error message, not silently default. Silent defaults are how a 200-map corpus ends up with three subtly broken trainer battles you don't find until Phase 8.

### 4.6 Tests for every converter

Every module in `src/rpg2gba/pbs_converter/` has a corresponding test in `tests/`. New converters do not get merged without:

1. A round-trip test (parse → emit → parse → diff)
2. At least one golden-output test against a hand-curated sample
3. An explicit edge-case test for whatever quirk Uranium does that vanilla Essentials doesn't

### 4.7 Verify against the real fork (both directions)

The fork (`$RPG2GBA_POKEEMERALD`) is the source of truth for what the engine can do — not your memory of it. Maintain a fork-capability index (624 specials in `data/specials.inc`, 385 macros in `asm/macros/event.inc`, all `include/constants/*.h`) and gate against it:

- **Forward:** every command/special/constant the pipeline emits must resolve in the index, or fail loud at conversion time — catches invented symbols (e.g. `healparty`) before `make modern`.
- **Reverse:** never queue anything "needs custom C" without a fork search proving no native analog exists. `HealPlayerParty` was a defined special the whole time the agent invented `healparty`. Native-analog ledger: `reference/essentials_to_emerald_map.md`.

Most "engine feature" tags ship natively (cave/Flash, bridges, PC, region map, relearner, trade, rock smash); only the Nuclear type is genuinely new C.

---

## 5. Code Conventions

### Python

- Python 3.11+
- Type hints on all public functions
- **Use built-in generic types for hints — never import `List`, `Dict`, `Tuple`, `Optional`, `Union` from `typing`.** Python 3.11 supports all of these natively:
  - `list[str]` not `List[str]`
  - `dict[str, int]` not `Dict[str, int]`
  - `tuple[str, ...]` not `Tuple[str, ...]`
  - `str | None` not `Optional[str]`
  - `str | int` not `Union[str, int]`
- You may still import from `typing` for things that have no built-in equivalent: `Protocol`, `TypeVar`, `Generic`, `TypedDict`, `Literal`, `Callable`, `Any`, `cast`, `overload`.
- `dataclasses` for structured records, not bare dicts
- `pathlib.Path` everywhere, never raw string paths
- Logging via the `logging` module, never `print()` in non-script code
- Click for any new CLI entry points
- Explicit `encoding="utf-8"` on every file read; assume Uranium files might be Windows-1252 and handle that case explicitly

```python
# Good
def parse_species(path: Path) -> list[Species]:
    with path.open(encoding="utf-8") as f:
        return _parse(f.read())

def find_by_name(name: str) -> Species | None:
    return _index.get(name)

def merge(a: list[str], b: list[str]) -> dict[str, list[str]]:
    ...

# Bad — don't do this
from typing import List, Optional, Dict
def parse_species(filename) -> List[Species]: ...
def find_by_name(name: str) -> Optional[Species]: ...
```

### Ruby

- Ruby 3.x for the rxdata deserializer
- The deserializer is intentionally minimal — load class stubs, marshal-load files, dump JSON, exit
- Do not add new Ruby code beyond what's needed for deserialization. If you find yourself wanting to write business logic in Ruby, write it in Python and have it consume the JSON output.

### C

- C code lives in the **vendored engine** (`engine/`, pokeemerald-expansion) — in-repo now, not an external fork. Mark custom edits with `URANIUM PATHFINDER SLICE`-style sentinel fences so they're revertable against pristine upstream
- Follow the conventions of pokeemerald-expansion for any new code there: tabs, K&R-ish brace style, `g`-prefixed globals, `s`-prefixed statics
- New constants go in the same headers as their kin (`include/constants/species.h`, etc.)

### Conversion agent prompts

The conversion agent's prompts are source code. Treat them with the same care.

- `src/rpg2gba/conversion_agent/prompts/system.md` is the canonical instruction set
- Few-shot examples live in `src/rpg2gba/conversion_agent/prompts/few_shot/` as individual `.md` files, one per scenario, named descriptively (`give_item_with_fanfare.md`, `branching_dialogue.md`)
- The prompt is **no longer frozen** (the bulk run is retired); edit it like any source file. It serves only the hand-invoked tail tool now, so changes are scoped to that tool, not a 199-map run.

---

## 6. The Flag Registry

The full policy lives in **`reference/flag_registry_policy.md`** — it's a Phase 4
component, dormant during the current Phase 2. Read it when Phase 4 starts. It's
the most common place pipelines like this go wrong, so don't wing it.

**Hard rule (applies always):** Every flag/var name goes through the registry —
never hardcode one, even one you're certain of. You may modify `flag_registry.py`
and `reference/essentials_to_emerald_map.md`, but you may **never** hand-edit the
registry's persistent state file mid-run. If the state is wrong, fix the input
data or the registry logic — don't patch the output.

**Naming is now mostly deterministic:** Uranium named most of its switches/vars
(`reference/uranium_switches.json` / `uranium_variables.json`), so readable
`FLAG_*`/`VAR_*` come straight from `_naming.to_constant` — no LLM. The `s:`-prefixed
conditional switches are runtime predicates (self-switch checks, time-of-day), not
stored flags; never mint a `FLAG_*` for them.

---

## 7. Working with Each Pipeline Phase

Per-phase detail — goals, tasks, exit criteria — lives in **ROADMAP.md** (Phases
0–8). The **active build sequence** (the deterministic transpiler + the per-slice
operating loop) lives in **`BUILD_PLAN.md`**; the active phase and next concrete task
live in **MEMORY.md → Current Phase**. Read both before you start.

**Phase 4 was pivoted (2026-06-18):** the LLM-driven bulk run is retired. Event→
Poryscript is now a deterministic transpiler you build and run (`BUILD_PLAN.md §3`);
the existing classifiers become an idiom-collapse layer on top; the LLM is a
hand-invoked tail tool only, and its prompt (`system.md`) is **no longer frozen**.
The conversion campaign runs as **vertical playable slices**, not a horizontal grind
— a slice isn't done until it boots and is playable, art included (§9).

---

## 8. Testing Expectations

### What good looks like

- Every PBS converter has round-trip + golden tests
- The orchestrator has integration tests using a tiny synthetic map
- The flag registry has tests for collision detection, validation rules, and state persistence
- The pokeemerald-expansion fork builds cleanly after every change you make to it

### Running tests

```bash
# Python
pytest

# Ruby
ruby test/test_deserializer.rb

# pokeemerald-expansion
cd $RPG2GBA_POKEEMERALD && make -j$(nproc) modern
```

### When tests fail

Fix the failure. Do not skip, mark xfail, or comment out failing tests without explicit user approval. If a test is genuinely wrong, fix the test and explain why in the commit message.

---

## 9. Manual Review Gates

There are three points where you must stop and wait for the user, even if everything appears to be working:

1. **End of Phase 2** — before any PBS-generated content is committed to the pokeemerald-expansion fork, the user reviews the generated C output and the unfixed-issues list
2. **Per-slice boot gate** — a vertical slice is not "done" until its ROM boots in mGBA and the section is genuinely playable (warps fire, NPCs sane, layout legible — *art included*, not deferred). The user walks each slice before the frontier widens. (Replaces the retired end-of-Phase-4 frozen-prompt/bulk-run gate.)
3. **End of Phase 7** — before declaring the ROM "playable," the user does a manual playthrough of the success-criteria scenarios

These gates exist because each one is a place where systematic errors propagate cheaply to fix early and expensively to fix late. Do not push past them on autopilot.

---

## 10. When to Ask the User vs Proceed

### Proceed without asking

- Implementing functionality that's already specified in the roadmap or this file
- Fixing obvious bugs in code you wrote in the same session
- Adding tests for code that lacks them
- Refactoring within a single module for clarity, without changing the module's public interface
- Updating reference docs to reflect what the code actually does
- Adding a new Python/Ruby **package** dependency — install it into the project `.venv` only (never globally: no `sudo`, no `pip install --user`, no system site-packages) and declare it in `pyproject.toml` so the env stays reproducible

### Ask before proceeding

- Anything that touches `flag_registry.py`'s policy (which names are valid, how collisions are resolved)
- Anything that changes the conversion agent's prompt structure
- Anything that changes the schema of intermediate JSON formats
- Installing **system/global** packages (apt, devkitPro, global `npm`, etc.) — anything that touches the machine outside the project `.venv`
- Modifying the `pokeemerald-expansion` fork in any way that changes baseline pokeemerald behavior
- Any decision about Uranium content fidelity — is this feature worth replicating, can we strip it, what's the smallest viable substitute

### Always ask

- Anything that might affect the user's Claude Pro usage budget mid-stage
- Anything that requires running for more than a few minutes
- Anything that would commit binaries, ROM data, or copyrighted material to git

---

## 11. Common Pitfalls

The three most expensive, most repeated mistakes — internalize these; the full
list is in ROADMAP.md "Known Pitfalls":

- **Claiming the engine can't do X without checking the fork.** The most expensive recent bug class — `healparty` was invented while `HealPlayerParty` existed; "engine features" were queued that ship natively. Grep `$RPG2GBA_POKEEMERALD` first, every time (§4.7).
- **Calling a slice "done" while deferring art.** The pathfinder slice booted but was unplayable because it deferred tilesets/sprites. A slice isn't done until it's playable with real (quantized) art (§9).
- **Editing generated output to "fix" something.** Fix the converter, not its output — the output gets regenerated. (Corollary: never add silent fallbacks for unknown fields, and never emit a symbol the fork doesn't define; fail loud.)

---

## 12. Quick Reference

### Environment variables

| Variable | Purpose |
|---|---|
| `RPG2GBA_URANIUM_SRC` | Path to the Uranium source tree on disk |
| `RPG2GBA_POKEEMERALD` | Path to the pokeemerald-expansion fork |
| `RPG2GBA_OUTPUT` | Output directory (defaults to `./output`) |
| `OLLAMA_HOST` | Ollama server on the Ubuntu desktop (accessed over Tailscale) |

### Useful one-liners

```bash
# Re-run all PBS converters from scratch
python -m rpg2gba.pipeline phase2 --clean

# Validate the flag registry's current state
python -m rpg2gba.conversion_agent.flag_registry validate

# Convert a single map for debugging
python -m rpg2gba.pipeline convert-map --map-id 042

# Build the pokeemerald-expansion fork
(cd $RPG2GBA_POKEEMERALD && make -j$(nproc) modern)
```

### Glossary

See the Glossary in **ROADMAP.md** for term definitions (build agent, conversion
agent, Essentials, PBS, rxdata, Poryscript, the fork).

---

*This file is authoritative for build-agent behavior. Update it when conventions change. Treat updates here with the same care as code changes.*
