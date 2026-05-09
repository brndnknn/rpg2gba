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
- **The other agent is the conversion agent.** It is a *runtime component of rpg2gba itself* — an LLM the orchestrator invokes at runtime to translate event JSON into Poryscript. It has no awareness of the codebase. Its instructions live in `src/rpg2gba/conversion_agent/prompts/system.md`, which you maintain like any other source file.

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

- **Do not run the conversion agent yourself or simulate its outputs.** When the roadmap calls for the conversion agent to do something, that work happens at pipeline runtime, not during your editing session. You write the agent; you don't roleplay as it.
- **Do not modify files in `output/` directly.** Those are generated artifacts. If they're wrong, fix the converter that produced them and re-run.
- **Do not invent pokeemerald-expansion C constants outside the flag registry.** See section 6.
- **Do not commit anything from the Uranium source tree, or any base ROM, into this repo.** Those are external inputs. They live on disk outside the repo and are referenced by config.
- **Do not bypass the manual review gates.** See section 9.
- **Do not change the conversion agent's prompt template during a Stage B or Stage C run.** Prompt changes happen between stages, never during. If you discover a prompt bug mid-run, log it and wait — don't hot-patch.

---

## Memory System

You have a persistent memory file at `MEMORY.md` in the repo root. Its purpose is to prevent you from re-scanning the entire codebase at the start of every session. **Read it before anything else. Update it before you finish.**

### Why this exists

Scanning the full repo to rebuild context burns tokens and time. MEMORY.md is your running notes on the state of the project — what's been done, what each key file actually does, what decisions have been made, and what's still open. A well-maintained MEMORY.md means the next session starts in 30 seconds, not 5 minutes.

### Structure of MEMORY.md

```markdown
# rpg2gba Agent Memory

## Current Phase
<!-- Which phase is active, what's been completed, what the next concrete task is -->

## Key File Notes
<!-- Short notes on non-obvious files. Don't duplicate what's already obvious from
     the repo layout in CLAUDE.md. Only note things that would take >30s to figure
     out from reading the file itself. -->

## Decisions Made
<!-- Architectural and data-fidelity decisions that are settled. Format:
     - [DATE] Decision: <what was decided>. Reason: <why>. -->

## Uranium-Specific Discoveries
<!-- Quirks of the Uranium source that affect converter logic.
     Things you found during Phase 0 or stumbled on later. -->

## Flag Registry Notes
<!-- Summary of any notable flag/var assignments made so far.
     Full state is in the registry file; this is just notable ones. -->

## Open Questions
<!-- Things that need the user's input before you can proceed. Clear an item
     when the user answers it. -->

## Last Session Summary
<!-- One paragraph: what you did, what you left unfinished, where to pick up. -->
```

### How to use it

**At the start of a session:**
1. Read MEMORY.md first, before any other file
2. If Current Phase or Last Session Summary tells you exactly what to do next, start there
3. If you need to verify something in code, check the specific file — don't re-scan the whole repo

**During a session:**
- Update Key File Notes when you learn something non-obvious about a file
- Add to Decisions Made when a significant decision gets settled
- Add to Open Questions when you hit something that needs user input before proceeding
- Add to Uranium-Specific Discoveries when you find a quirk

**At the end of a session (or at a natural stopping point):**
1. Update Last Session Summary with what you did and where to pick up
2. Update Current Phase to reflect progress
3. Clear any Open Questions that got answered

### Rules

- Update MEMORY.md with targeted `str_replace` edits, not full rewrites — other sections shouldn't be disturbed when you update one
- Keep entries concise. If a Key File Note is longer than two sentences, it probably belongs in `reference/` as a proper doc, not here
- Don't put information here that's already in CLAUDE.md or ROADMAP.md — link or reference instead
- MEMORY.md is committed to git. Session-to-session state persists in version history. Don't gitignore it.

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
│       ├── conversion_agent/       # Phase 4: runtime LLM component
│       │   ├── orchestrator.py     # The driver loop
│       │   ├── flag_registry.py    # Single source of truth for FLAG_*/VAR_* names
│       │   ├── backends/
│       │   │   ├── ollama.py
│       │   │   ├── claude_code.py
│       │   │   └── anthropic_api.py
│       │   └── prompts/
│       │       ├── system.md       # The agent's frozen instruction set
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
└── output/                     # Generated artifacts; gitignored
    └── uranium-build/
```

### Things outside this repo you may need to read

- The Uranium source tree (path configured in env var `RPG2GBA_URANIUM_SRC`)
- The `pokeemerald-expansion` fork (path configured in env var `RPG2GBA_POKEEMERALD`)
- Neither path's contents go into rpg2gba's git history.

---

## 4. Operating Principles

These are non-negotiable. If a request seems to require breaking one, stop and ask.

### 4.1 Deterministic where possible, LLM where necessary

PBS data conversion is deterministic. Map deserialization is deterministic. Tileset coordinate mapping is deterministic. Only event-to-Poryscript conversion uses an LLM at runtime, and only because naming and idiom recognition genuinely benefit from it.

When you're tempted to use an LLM for something else, the answer is almost always "write a parser instead."

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

- C code only lives in the `pokeemerald-expansion` fork, never in this repo
- Follow the conventions of pokeemerald-expansion for any new code there: tabs, K&R-ish brace style, `g`-prefixed globals, `s`-prefixed statics
- New constants go in the same headers as their kin (`include/constants/species.h`, etc.)

### Conversion agent prompts

The conversion agent's prompts are source code. Treat them with the same care.

- `src/rpg2gba/conversion_agent/prompts/system.md` is the canonical instruction set
- Few-shot examples live in `src/rpg2gba/conversion_agent/prompts/few_shot/` as individual `.md` files, one per scenario, named descriptively (`give_item_with_fanfare.md`, `branching_dialogue.md`)
- Changes to these files require regenerating the calibration set output and confirming it still meets quality bar
- Do not edit these files during an active conversion run

---

## 6. The Flag Registry

This deserves its own section because it's the most common place pipelines like this go wrong.

### The problem it solves

RPG Maker uses numbered switches and variables (`Switch 42`, `Variable 17`). pokeemerald-expansion uses named flags and vars (`FLAG_RECEIVED_STARTER`, `VAR_STORY_PROGRESS`). The conversion agent must translate between them — and must do so consistently across all 200+ maps. If `Switch 42` becomes `FLAG_RECEIVED_STARTER` in one map and `FLAG_GOT_FIRST_POKEMON` in another, the game breaks.

### How the registry works

- `flag_registry.py` is a stateful singleton during a pipeline run
- The conversion agent never invents a flag name in its output. It either uses a name the registry has already assigned to that switch ID, or it *proposes* a name and the orchestrator decides whether to accept
- New flag proposals go through a validation step:
  - Name follows the `FLAG_*` / `VAR_*` convention
  - Name doesn't collide with an existing pokeemerald-expansion constant
  - Name passes a basic sanity check (not empty, not "FLAG_TODO", not gibberish)
- Once accepted, the assignment is permanent for that pipeline run
- The final registry state is dumped to a `.h` file the pokeemerald-expansion fork includes

### Pre-seeded mappings

Before the first run, the registry is pre-seeded with known stable mappings — things every Pokémon game has (received starter, beat first gym, talked to professor). Look at `reference/essentials_to_emerald_map.md` for the canonical list. Add new pre-seeds when you confirm a Uranium switch maps to a vanilla concept.

### Hard rule for you

You may modify `flag_registry.py`. You may modify `reference/essentials_to_emerald_map.md`. You may NOT manually edit the registry's persistent state file mid-run. If the registry's state is wrong, fix the input data or the registry logic — don't patch the output.

---

## 7. Working with Each Pipeline Phase

### Phase 0: Reconnaissance

Your job here is to read code and write reports in `reference/`. No production code is written in Phase 0. If you're tempted to start writing converters, you're not done with reconnaissance yet.

### Phase 2: PBS conversion

Each PBS file gets its own module under `src/rpg2gba/pbs_converter/`. Modules follow a consistent shape:

```python
def parse(path: Path) -> list[Record]: ...
def emit_c(records: list[Record], out: Path) -> None: ...
def round_trip_check(path: Path) -> bool: ...
```

When Uranium has fields vanilla Essentials doesn't, document them in `reference/uranium_custom_features.md` and decide explicitly: map to existing expansion constant, add new constant, or strip. Never silently drop a field.

### Phase 3: rxdata deserialization

The Ruby deserializer is intentionally dumb. It loads, dumps, exits. All interpretation happens in downstream Python. If the Python side is missing context to interpret something, do not add interpretation logic to Ruby — extend the JSON schema to include the missing context.

### Phase 4: Conversion agent

This is where the build/conversion role distinction is most likely to get muddled. Re-read section 1 if you feel uncertain.

Your job in Phase 4 is to:

- Build the orchestrator (`orchestrator.py`)
- Build the backend abstraction and its three implementations
- Build the flag registry
- Author and refine the conversion agent's prompts and few-shot examples
- Build the unhandled queue and the retry-with-compiler-error logic

You do *not* manually convert events yourself. The conversion agent does that at runtime.

When iterating on prompts during Stage A: change prompt → run on calibration set → review output → repeat. Don't try to fix individual bad outputs by hand-editing them; if the output is bad, the prompt or examples need work.

### Phase 6: Custom C in pokeemerald-expansion fork

This is the only phase where you write C. You're working in a separate repo (the fork). Treat that fork's conventions as authoritative. New types, abilities, or field effects follow the patterns the expansion already establishes — don't invent new patterns when an existing one fits.

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
2. **End of Phase 4 Stage A** — before any bulk conversion runs, the user approves the frozen prompt template and the calibration set output
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

### Ask before proceeding

- Anything that touches `flag_registry.py`'s policy (which names are valid, how collisions are resolved)
- Anything that changes the conversion agent's prompt structure
- Anything that changes the schema of intermediate JSON formats
- Adding new dependencies (Python, Ruby, or system packages)
- Modifying the `pokeemerald-expansion` fork in any way that changes baseline pokeemerald behavior
- Any decision about Uranium content fidelity — is this feature worth replicating, can we strip it, what's the smallest viable substitute

### Always ask

- Anything that might affect the user's Claude Pro usage budget mid-stage
- Anything that requires running for more than a few minutes
- Anything that would commit binaries, ROM data, or copyrighted material to git

---

## 11. Common Pitfalls

A list of mistakes the build agent (you, or earlier sessions of you) is likely to make:

- **Conflating the two agents.** If you're unsure whether a piece of work belongs to you or the conversion agent: code lives with you, runtime LLM calls live with the conversion agent. Always.
- **Editing generated output to "fix" something.** You must fix the converter, not its output. The output gets regenerated.
- **Hand-converting events to "show" something.** No. The conversion agent does that at runtime. Your job is to make the conversion agent capable of doing it well.
- **Adding silent fallbacks for unknown PBS fields.** Fail loud. Always.
- **Bypassing the flag registry to "just hardcode" a name.** No. Every flag name goes through the registry, even if it's a flag you're 100% sure is `FLAG_RECEIVED_STARTER`.
- **Treating the Uranium source as canonical for pokeemerald-expansion conventions.** It's not. When in doubt about how the fork should look, the fork's existing patterns win.
- **Committing files from outside the repo.** The Uranium source and base ROMs never go into git. If you find yourself running `git add` on something from `$RPG2GBA_URANIUM_SRC`, stop.
- **Skipping Phase 0.** Reconnaissance feels like procrastination. It's not. Every hour there saves five later.

---

## 12. Quick Reference

### Environment variables

| Variable | Purpose |
|---|---|
| `RPG2GBA_URANIUM_SRC` | Path to the Uranium source tree on disk |
| `RPG2GBA_POKEEMERALD` | Path to the pokeemerald-expansion fork |
| `RPG2GBA_OUTPUT` | Output directory (defaults to `./output`) |
| `OLLAMA_HOST` | Pointed at the Ubuntu desktop for Stage B runs |
| `ANTHROPIC_API_KEY` | Only needed for Stage D fallback |

### Useful one-liners

```bash
# Re-run all PBS converters from scratch
python -m rpg2gba.pipeline phase2 --clean

# Validate the flag registry's current state
python -m rpg2gba.conversion_agent.flag_registry validate

# Convert a single map for debugging (any backend)
python -m rpg2gba.pipeline convert-map --map-id 042 --backend ollama

# Build the pokeemerald-expansion fork
(cd $RPG2GBA_POKEEMERALD && make -j$(nproc) modern)
```

### Glossary

- **Build agent.** You.
- **Conversion agent.** The runtime LLM component inside rpg2gba.
- **Essentials.** Pokémon Essentials, the Ruby framework Uranium is built on.
- **PBS.** Pokémon Batch Script — Essentials' plain-text data format.
- **rxdata.** RPG Maker XP's serialized Ruby object files.
- **Poryscript.** The high-level scripting language pokeemerald-expansion uses.
- **The fork.** The user's clone of pokeemerald-expansion that becomes the Uranium ROM.
- **The roadmap.** `ROADMAP.md`. Read it.

---

*This file is authoritative for build-agent behavior. Update it when conventions change. Treat updates here with the same care as code changes.*
