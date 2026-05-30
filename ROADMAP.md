# Pokémon Uranium → GBA ROM Conversion Pipeline: Roadmap

**Project name:** `rpg2gba`

**Goal:** Build a reusable pipeline that converts RPG Maker XP / Pokémon Essentials fan games into playable GBA ROMs, using Pokémon Uranium as the first end-to-end test case. The pipeline tooling is the long-term deliverable; the Uranium ROM is the proof of concept.

**Estimated total scope:** This is a months-long hobby project, not a weekend build. Expect 6–12 months of part-time work to get a playable Uranium build through the full pipeline. The first three phases are achievable in weeks; the back half is where the long tail lives.

---

## Two Agents in This Project

**This roadmap distinguishes between two completely separate AI agents.** Conflating them is the single most common conceptual mistake when designing this kind of system.

### The Build Agent

The AI assistant helping you *develop* rpg2gba itself. Operates inside the rpg2gba repo. Reads `CLAUDE.md`. Has full access to the codebase, can run tests, refactor, debug, write new converters. In practice this is Claude Code (or whatever you use day-to-day in your IDE). It behaves like a junior developer joining the project.

When this roadmap says "the build agent" or references `CLAUDE.md`, this is what's meant.

### The Conversion Agent

A *component of the pipeline itself* — the LLM invoked at runtime by the rpg2gba orchestrator to translate event JSON into Poryscript, one event at a time. It receives a tightly-scoped prompt, returns structured output, and has no awareness of the codebase that called it. Across Phase 4's stages this role is filled by different backends (Claude via Claude Code, local Ollama, Anthropic API), but it's always the same role.

When this roadmap says "the conversion agent" — particularly in Phase 4 — this is what's meant.

### Why the distinction matters

| | Build Agent | Conversion Agent |
|---|---|---|
| **Lives in** | Your IDE | The rpg2gba pipeline |
| **Reads** | `CLAUDE.md`, full repo, tests | Single map's event JSON + flag registry |
| **Writes** | Python, Ruby, C, Markdown | Poryscript only |
| **Tools** | File edit, bash, test runners | None — pure text in/out |
| **Memory** | Conversation + codebase | Stateless per call |
| **Failure mode** | Asks for clarification | Marks command "unhandled" |
| **Configured by** | `CLAUDE.md` | Prompt template + backend abstraction |
| **You interact with** | Constantly during development | Never directly — only via orchestrator |

Treat them as separate systems. The build agent should not be modifying the conversion agent's prompts at runtime; the conversion agent should not be writing converter code. Each has one job.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites & Environment Setup](#prerequisites--environment-setup)
3. [Phase 0: Reconnaissance](#phase-0-reconnaissance)
4. [Phase 1: Foundation & Project Skeleton](#phase-1-foundation--project-skeleton)
5. [Phase 2: PBS Data Conversion](#phase-2-pbs-data-conversion)
6. [Phase 3: Map Deserialization](#phase-3-map-deserialization)
7. [Phase 4: Event → Poryscript (Conversion Agent)](#phase-4-event--poryscript-conversion-agent)
8. [Phase 5: Map Layout & Tileset Conversion](#phase-5-map-layout--tileset-conversion)
9. [Phase 6: Custom Engine Features (Nuclear Type)](#phase-6-custom-engine-features-nuclear-type)
10. [Phase 7: Integration & Build](#phase-7-integration--build)
11. [Phase 8: Playtest & Polish](#phase-8-playtest--polish)
12. [Agent Guidance](#agent-guidance)
13. [Known Pitfalls](#known-pitfalls)
14. [Glossary](#glossary)
15. [References](#references)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  SOURCE: Pokémon Uranium (RPG Maker XP + Essentials)        │
│  - PBS/*.txt           (data: pokemon, moves, items, etc.)  │
│  - Data/*.rxdata       (serialized Ruby: maps, events)      │
│  - Graphics/**/*.png   (sprites, tilesets, UI)              │
│  - Audio/**/*.{ogg,mp3}                                     │
│  - Scripts.rxdata      (engine code — NOT converted)        │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ PBS Parser   │      │ rxdata       │      │ Tileset      │
│ (Python,     │      │ Deserializer │      │ Converter    │
│ deterministic│      │ (Ruby script │      │ (manual +    │
│ ~95%)        │      │ → JSON)      │      │ scripted)    │
└──────────────┘      └──────────────┘      └──────────────┘
        │                     │                     │
        ▼                     ▼                     ▼
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ C data       │      │ Event JSON   │      │ Porymap      │
│ tables       │      │              │      │ tilesets     │
│ (.h/.c)      │      │              │      │              │
└──────────────┘      └──────┬───────┘      └──────────────┘
                             │
                             ▼
                      ┌──────────────┐
                      │ Conversion   │
                      │ Agent        │
                      │ (Ollama /    │
                      │ Claude /     │
                      │ + flag map)  │
                      └──────┬───────┘
                             │
                             ▼
                      ┌──────────────┐
                      │ Poryscript   │
                      │ (.pory)      │
                      └──────────────┘
                             │
                             ▼
        ┌────────────────────────────────────────┐
        │ pokeemerald-expansion fork             │
        │ + Nuclear type (custom C)              │
        │ + converted data, scripts, maps        │
        └────────────────────────────────────────┘
                             │
                          (make)
                             ▼
                    ┌────────────────┐
                    │ uranium.gba    │
                    └────────────────┘
```

---

## Prerequisites & Environment Setup

### Hardware

Run the build pipeline on the **Ubuntu desktop**. The GBA decomp toolchain is happiest on Linux, builds are CPU-bound, and the Uranium project files are large enough that the M2 Air's 8GB RAM will struggle once VS Code, the LLM agent, and a build are all running. SSH in from the MacBook via Tailscale for development; reserve the Mac for editing.

### Toolchain

| Tool | Purpose | Install |
|---|---|---|
| **devkitPro / devkitARM** | GBA cross-compiler | `pacman` via dkp-pacman |
| **agbcc** | Older C compiler used by pokeemerald | Build from source ([agbcc repo](https://github.com/pret/agbcc)) |
| **pokeemerald-expansion** | Base ROM project to fork | Clone from rh-hideout |
| **Porymap** | Visual map editor | Build from source or appimage |
| **Poryscript** | Script language compiler (built into pokeemerald-expansion) | Comes with the project |
| **Ruby 3.x** | For the rxdata deserializer | apt or rbenv |
| **Python 3.11+** | PBS converter, orchestration | apt |
| **Pillow** | Tileset image processing | pip |
| **Claude Code** | LLM agent for Layer 2 conversion | npm |
| **Git LFS** | Large binary asset storage | apt |

### Source Materials

- **Pokémon Uranium source:** Pokémon Uranium was **not** open-sourced. The artifact is the distributed game (download `Pokemon_Uranium_1.3.2.zip` or similar). Most game data is packed inside `Uranium.rgssad`, an RPG Maker XP RGSSAD v1 archive; extract it with `scripts/extract_rgssad.py` (no PBS source ships — Essentials compiles the human-readable PBS to binary `.dat` files, so Phase 2 reads `.dat` via Ruby instead of parsing text). The distribution contains copyrighted Game Freak assets (sprites, sounds reused from official games) — the resulting ROM will too, so this is a personal-use-only project.
- **pokeemerald-expansion:** rh-hideout fork of pret's pokeemerald. Already includes Gen 1–9 data, modern battle mechanics, and a working Poryscript pipeline. Fork this; don't start from vanilla pokeemerald.
- **Clean Pokémon Emerald base ROM:** Required by the decomp build to extract a few baseline assets. You provide this yourself.

### Repository Structure (the pipeline tool itself)

```
rpg2gba/
├── README.md
├── ROADMAP.md                  # this file
├── CLAUDE.md                   # build agent instructions
├── pyproject.toml
├── src/
│   ├── pbs_converter/
│   │   ├── __init__.py
│   │   ├── pokemon.py
│   │   ├── moves.py
│   │   ├── items.py
│   │   ├── trainers.py
│   │   ├── abilities.py
│   │   └── encounters.py
│   ├── rxdata_deserializer/
│   │   └── deserialize.rb
│   ├── conversion_agent/       # the runtime LLM component
│   │   ├── orchestrator.py
│   │   ├── flag_registry.py
│   │   ├── backends/
│   │   │   ├── ollama.py
│   │   │   ├── claude_code.py
│   │   │   └── anthropic_api.py
│   │   └── prompts/
│   │       ├── system.md
│   │       └── few_shot/
│   ├── tileset_converter/
│   │   └── ...
│   └── pipeline.py             # top-level entry point
├── tests/
├── reference/
│   ├── poryscript_cheatsheet.md
│   ├── rgss_event_commands.md
│   └── essentials_to_emerald_map.md
└── output/
    └── uranium-build/          # gitignored; intermediate artifacts
```

---

## Phase 0: Reconnaissance

**Duration:** 1–2 weeks part-time. **Don't skip this.** Every hour spent here saves five later.

### Goals

Build a complete inventory of what you're actually converting before writing any code.

### Tasks

**0.1 Acquire and unpack Uranium**
- Download the distributed game (`Pokemon_Uranium_1.3.2.zip`) and extract the zip
- Run `scripts/extract_rgssad.py` on `Uranium.rgssad` to unpack `Data/` (maps + `.rxdata` + compiled `.dat` files); the unpacked tree lives outside the rpg2gba repo, referenced by `RPG2GBA_URANIUM_SRC`
- Document directory layout in `reference/uranium_structure.md`
- Note the Essentials version it's built on (Uranium is **v17** — see `reference/uranium_essentials_version.md`); this matters because the PBS format changed between versions

**0.2 Compiled `.dat` inventory** *(was: PBS file inventory)*
- The distribution ships only Essentials' compiled `.dat` files, not human-readable `PBS/*.txt`
- List every `.dat` file, identify what PBS concept it corresponds to (`reference/uranium_dat_inventory.md`)
- Flag Uranium-specific files (`shadowmoves.dat`, `regionals.dat`, `tmpbs.dat`, etc.)
- Identify which `.dat` holds the species table (notably absent from a `pokemon.dat`-named file) — this is a spike task before Phase 2 can start

**0.3 Map inventory**
- Count `.rxdata` map files
- Estimate total event count (script for this — open each map, count events)
- Identify maps with "complex" events (long script bodies, custom commands)

**0.4 Custom mechanic survey**
- Read `Scripts.rxdata` (deserialize first; it's a big tree of Ruby scripts) and identify everything Uranium added on top of vanilla Essentials
- Expected list for Uranium:
  - Nuclear type (new type, new effectiveness rules)
  - Mega Evolution handling
  - Online features: GTS, online battles, virtual trainers, mystery gift — **all to be stripped**, not converted
  - Pokémon speech translation flavor system — likely cosmetic, can be reduced to plain dialogue
  - Custom abilities tied to Nuclear-type Pokémon
- Write each item up in `reference/uranium_custom_features.md` with an explicit decision: **Convert / Adapt / Strip**

**0.5 Asset inventory**
- Total sprite count, audio file count, tileset count
- Identify which assets are Uranium-original vs. reused from official games
- Flag anything copyright-fragile

**0.6 Define "playable" success criteria**
This is the most important deliverable of Phase 0. Write down what "done" means before the first phase that produces converter code. Suggested minimum bar:
- Player can leave the starting town
- At least one trainer battle works correctly
- At least one Nuclear-type Pokémon battles correctly with proper type effectiveness
- A save file persists across sessions on Delta
- No crash bugs in the first ~30 minutes of gameplay

### Phase 0 Exit Criteria

- [ ] Inventory documents written
- [ ] Custom feature decisions made and documented
- [ ] Success criteria defined
- [ ] You can articulate, in one paragraph, why each Layer 4 custom-C feature is or isn't worth implementing

---

## Phase 1: Foundation & Project Skeleton

**Duration:** ~1 week.

### Goals

Have a clean pokeemerald-expansion fork that builds successfully, plus the empty pipeline repo scaffolded.

### Tasks

**1.1 Fork pokeemerald-expansion**
- Create a fork named something like `uranium-gba`
- Verify a clean build: `make -j$(nproc)` should produce a working `pokeemerald.gba`
- Test the resulting ROM in Delta on your iPhone — establish that the baseline works on your target device before changing anything

**1.2 Set up the pipeline repo**
- Initialize `rpg2gba` repo
- Add `pyproject.toml`, basic CI (lint + test), pre-commit hooks
- Create the directory structure listed above
- Stub out empty modules

**1.3 Write CLAUDE.md (for the build agent)**
- This document is for the **build agent only** — the AI assistant working in the rpg2gba codebase day-to-day
- It is not the conversion agent's prompt; that lives in `src/rpg2gba/conversion_agent/prompts/` and is governed separately
- You have a pattern for CLAUDE.md from Recursor — adapt it
- Specify: code conventions, when to ask for clarification, how to handle data fidelity decisions, the boundary between deterministic converters and LLM-assisted ones, the rule that the build agent never modifies the conversion agent's prompts at runtime

**1.4 Establish a "smoke test ROM"**
- Apply a single trivial change to the forked pokeemerald-expansion (e.g., rename the player) to confirm your edit-build-flash-test loop works
- Time how long a full build takes — this number drives everything later

### Phase 1 Exit Criteria

- [ ] Forked decomp builds and runs in Delta
- [ ] Pipeline repo scaffolded with passing CI
- [ ] CLAUDE.md written
- [ ] Build cycle time documented

---

## Phase 2: PBS Data Conversion

**Duration:** 2–3 weeks.

### Goals

Convert all Uranium PBS files to pokeemerald-expansion C data tables. This is the most deterministic phase and the one where you'll learn the most about Uranium's actual content.

### Approach

PBS conversion is **Ruby + Python, occasionally LLM**. Uranium's distribution ships compiled `.dat` files only (no PBS text), so the input layer is a **Ruby `Marshal.load` deserializer** that dumps each `.dat` to JSON. The Python converters then read JSON and emit C — same downstream contract as the original text-PBS plan. The LLM is still invoked only for fuzzy decisions (naming a custom ability, mapping a non-standard move effect to a closest-match constant).

### Spike before Phase 2 starts

Before any per-record converter is written, do a deserialization spike:
1. Add `scripts/dump_dat.rb` that loads each `.dat` with class stubs and prints its top-level Ruby class name and shape
2. Confirm which `.dat` holds the species table (it's not named `pokemon.dat` in Uranium's distribution; see `reference/uranium_dat_inventory.md`)
3. Manually verify one entry round-trips correctly (e.g., load `moves.dat`, find Pound, confirm power=40)

Without this spike, none of the per-record converters can be written.

### Order of attack

Do these in order — each depends on the species/move IDs being stable. The "input file" column below is the compiled `.dat` rather than its conceptual PBS source.

**2.1 species data → C** (input: TBD by spike — possibly `attacksRS.dat`, `tmpbs.dat`, or inside `dexdata.dat`)
- Parse all entries
- Generate `gSpeciesInfo[]` entries in pokeemerald-expansion's format
- Generate the `SPECIES_*` enum
- Handle Uranium's 190+ Pokémon, including Nuclear-type entries
- Custom abilities get placeholder names; resolved in 2.4

**2.2 moves → battle moves** (input: `moves.dat`, possibly cross-checked with `attacksRS.dat`)
- Generate `gMovesInfo[]` entries
- For each move, identify whether it's a vanilla Gen 1–9 move (use existing constant) or a Uranium-original move (new entry)
- Uranium-original move effects often map to existing effect constants — LLM-assisted decision

**2.3 items** (input: `items.dat`)
- Generate item data
- Map item categories (Pokéball, healing, evolution stone, key item) to existing pokeemerald-expansion categories

**2.4 abilities** (input: TBD — abilities may live inside species/`tmpbs.dat`)
- Most will map to existing abilities
- Custom abilities (Nuclear-related, others) get marked for Phase 6 C implementation

**2.5 TM/HM lists** (input: `tm.dat`, `tutor.dat`)
- Translate to expansion's TM data structure

**2.6 trainers** (input: `trainers.dat`, `trainertypes.dat`, `trainerlists.dat`)
- Generate trainer parties and trainer class data
- Important: trainer scripts in maps reference these by ID — keep IDs stable

**2.7 encounters** (input: `encounters.dat`)
- Wild encounter tables per map
- These tie into map IDs from Phase 5, so output keyed by Uranium map ID for now

**2.8 metadata and game-level config** (input: `metadata.dat`)
- Starting position, party limits, etc.

### Validation

For each `.dat`, write a round-trip test: deserialize → emit C → re-parse the C → diff against the deserialized structure. Anything that doesn't round-trip cleanly is a bug.

### Phase 2 Exit Criteria

- [ ] All shipped `.dat` files (excluding localization and `BackupSave.dat`) have a converter or an explicit STRIP decision
- [ ] Round-trip tests pass
- [ ] Generated C compiles cleanly when dropped into the fork
- [ ] A test ROM with all Uranium species data builds and at least the species list shows correctly in the Pokédex (even if maps and events aren't done yet)
- [ ] **Mapping table file** committed: `reference/uranium_id_map.json` with every Uranium internal name → expansion constant name

---

## Phase 3: Map Deserialization

**Duration:** 1–2 weeks.

### Goals

Convert all `.rxdata` files into a structured, human-readable JSON format that downstream tools (and the LLM agent) can consume.

### Approach

`.rxdata` files are Ruby's `Marshal.dump` output — serialized object graphs of `RPG::Map`, `RPG::Event`, `RPG::EventCommand`, and so on. The deserializer **must be Ruby**, because reimplementing `Marshal` in Python is a known rabbit hole. Use a minimal Ruby script that loads the RPG Maker class definitions (or stubs) and dumps each map to JSON.

### Tasks

**3.1 Ruby deserializer**
- Load the RPG Maker XP RGSS class stubs (these exist as open-source reference)
- Iterate every `Map*.rxdata` file in `Data/`
- For each map, output a JSON file containing:
  - Tile data (3 layers × width × height)
  - Events list, each event with:
    - `id`, `name`, `x`, `y`
    - Pages (events have multiple pages with conditions)
    - Each page has a list of commands (the meat)
  - Connections, encounters reference, BGM

**3.2 Command code reference**
- RPG Maker stores event commands as numbered codes (101 = show text, 111 = conditional branch, etc.)
- Build a complete reference table at `reference/rgss_event_commands.md` with every code Uranium uses
- Tag each as: **Direct Poryscript equivalent / Adaptable / Needs C / Strip**

**3.3 Switches and variables dump**
- Extract the global switch and variable definitions from `System.rxdata`
- These are the named flags/vars the AI agent will need to map to pokeemerald-expansion's `FLAG_*` and `VAR_*` namespace

**3.4 Common Events**
- `CommonEvents.rxdata` contains reusable scripts called from many maps
- Deserialize these separately; they'll often map to Poryscript `script` blocks shared across maps

### Validation

- Pick 3 representative maps (a town, a route, a building interior) and manually inspect the JSON output against the in-game behavior
- Confirm event count matches what RPG Maker editor would show

### Phase 3 Exit Criteria

- [ ] All maps deserialized to JSON
- [ ] Common events deserialized
- [ ] Switch/variable tables extracted
- [ ] Command code reference written
- [ ] Manual spot-checks on 3 maps confirm fidelity

---

## Phase 4: Event → Poryscript (Conversion Agent)

**Duration:** 4–8 weeks. This is the big phase.

### Goals

Build the **conversion agent** — the runtime LLM component of rpg2gba that translates deserialized event JSON into idiomatic Poryscript. The agent is invoked once per event by the orchestrator. By the end of this phase, every Uranium map has a corresponding `.pory` file generated by the conversion agent.

> **Reminder on terminology:** Throughout Phase 4, "the conversion agent" refers to the LLM running inside the pipeline, not the build agent helping you write the pipeline code. The two agents do not interact. The build agent writes the conversion agent's prompts, scaffolding, and orchestration; the conversion agent then runs autonomously inside those guardrails.

### Why this needs an LLM, not a script

A rule-based converter could mechanically translate command codes 1:1, but the output would be unreadable garbage. The win from LLM use is in:
- **Naming.** `Switch 42` becomes `FLAG_RECEIVED_STARTER`, not `FLAG_SWITCH_42`. This requires reading the surrounding context.
- **Idiom matching.** A 12-command RPG Maker sequence that means "give the player an item with a fanfare" should become `giveitem ITEM_X` in Poryscript, not 12 separate calls.
- **Edge case handling.** Events that mix dialogue with custom commands need creative restructuring.

### Strategy: Hybrid Local-First, Escalate When Needed

The conversion agent has multiple viable LLM backends. The right approach is a staged, local-first one that matches the project's existing philosophy (and your existing Ollama setup). Note that **the conversion agent is the same component throughout** — only its backend changes per stage.

**Stage A — Prompt Development (5 calibration maps): Claude as conversion agent backend, via Claude Code**
- Pick 5 representative maps: a small town, a route, a building interior, a complex story scene, and one with custom commands
- Use Claude Code interactively as the conversion agent's backend, iterating on the prompt structure, few-shot examples, and output format
- This stage uses Claude Code for fast iteration on the conversion agent itself — you (or the build agent) are tuning the conversion agent's prompts based on what comes out
- Goal: converge on a prompt that produces clean, idiomatic Poryscript that compiles on first try ~80% of the time
- Output of this stage is a frozen prompt template, not converted maps

**Stage B — Bulk First Pass: Local Ollama as conversion agent backend**
- Run the frozen prompt against the entire map corpus using a local model on the Ubuntu desktop
- **Recommended model:** Qwen3 7B or larger (you've already validated tool-call reliability with this), or gpt-oss 20b if you want more headroom for nuanced output
- Run overnight, in batches, with a checkpoint after every map so any crash is recoverable
- Quality bar at this stage: "syntactically valid Poryscript that compiles, even if ugly or verbose"
- Expect ~70–85% of maps to come through cleanly; the rest land in an unhandled/needs-review queue

**Stage C — Quality & Unhandled Pass: Claude as conversion agent backend, via Claude Code**
- Take the maps the local backend flagged as unhandled or that produced obviously wrong output
- Take a 10% random sample of "passed" output for sanity checking — don't trust the local model blindly
- Run these through Claude Code interactively, in 5-hour windows
- This is where the bulk of your Pro subscription's budget gets spent

**Stage D — API Fallback (only if needed)**
- Only escalate to direct Anthropic API as the conversion agent's backend if Stage C runs into Pro window exhaustion repeatedly, or if you need programmatic retry-with-compiler-error loops at scale
- If you do escalate: use prompt caching aggressively (the stable prompt chunk is 8–15k tokens, cacheable), and use `claude-opus-4-8` for hard maps, `claude-sonnet-4-6` for routine ones
- Realistic cost if it comes to this: $20–80 (much lower than the original estimate, because most maps will already be done by then)

### Why this beats the API-first approach

- Costs $0–20 instead of $50–200
- Uses the Ubuntu desktop you already have, with the Ollama setup you already have
- Calendar time, not wall-clock time, becomes the bottleneck — and you can run the local model overnight while you do other things
- Forces good engineering hygiene: resumability, checkpointing, idempotent re-runs — all of which would be needed eventually anyway
- Keeps the API as a real fallback rather than the primary path

### Architecture

**4.1 Flag/variable registry (deterministic, backend-agnostic)**
- Build `flag_registry.py`: a stateful service that, given a switch ID, returns either an existing `FLAG_*` name or assigns a new one
- The registry persists across all map conversions in a single run
- Pre-seed with known mappings from vanilla Essentials → pokeemerald-expansion conventions
- Write the final registry out as a header file the pokeemerald-expansion fork can include
- This component is identical regardless of which backend the conversion agent is using

**4.2 Conversion agent backend abstraction**
- Build a thin LLM client interface inside `src/rpg2gba/conversion_agent/`: `convert_event(event_json, registry_state, prompt) -> ConversionResult`
- Implement three backends behind it:
  - `OllamaBackend` (local, used for Stage B)
  - `ClaudeCodeBackend` (interactive, used for Stages A and C — really a "review and approve" wrapper around terminal Claude Code sessions)
  - `AnthropicAPIBackend` (programmatic, used for Stage D if needed)
- This abstraction is the single most important architectural decision in this phase. It lets the conversion agent swap backends per stage without rewriting the orchestrator
- The backend abstraction is *also* what cleanly separates the conversion agent (one stable component) from its varying LLM provider (the implementation detail)

**4.3 Per-map orchestrator loop**
- The orchestrator drives the conversion agent. For each map JSON:
  1. Check checkpoint: if this map is already converted and validated, skip
  2. Load the map's event list
  3. For each event, the orchestrator builds a prompt for the conversion agent containing:
     - The deserialized event commands (JSON)
     - The current flag registry state (what's already been named)
     - The Poryscript reference cheatsheet (cached / stable)
     - 2–3 few-shot examples of similar conversions (cached / stable)
     - Instructions to flag any command it can't translate
  4. The conversion agent processes the prompt via whichever backend is configured
  5. The orchestrator parses the response: extracts the Poryscript block, extracts any new flag/var name proposals, extracts any "unhandled" annotations
  6. Runs the output through the Poryscript compiler immediately
  7. On compile success: updates registry, writes the `.pory` file, writes checkpoint
  8. On compile failure: logs error to retry queue with the compiler message; does not advance

**4.4 Unhandled command queue**
- Anything the conversion agent can't translate, plus anything that fails to compile after retry, lands in `output/unhandled.jsonl`
- Review this queue at the end of each stage
- Decide per item: implement custom Poryscript macro / write C handler / strip / accept loss

**4.5 Iteration strategy**
- Don't try to convert all 200+ maps in one pass with any backend
- Stage A converges the conversion agent's prompt on 5 maps. Stage B handles the bulk. Stage C cleans up the tail.
- Resist the urge to do "one big run" — checkpoint-based incremental progress is the only sustainable approach for a corpus this size

### Local backend considerations

- **Memory bandwidth, not GPU cores, is the bottleneck on the Ubuntu desktop.** A 20B model will run, but slowly. Plan for 30s–2min per event conversion at that size
- Qwen3 7B is the pragmatic sweet spot — fast enough to chew through the corpus overnight, capable enough for syntactically valid output
- Keep `OLLAMA_HOST` pointed at the desktop so you can kick off runs from the MacBook over Tailscale and monitor remotely
- Local models tend to be more verbose and less idiomatic; the few-shot examples in the conversion agent's prompt are doing more work here than they would with Claude. Invest extra time in those examples during Stage A

### Validation

- Each generated `.pory` file must compile through Poryscript without errors before being committed
- Spot-check generated scripts against original RPG Maker events for semantic equivalence on the 5 calibration maps
- After Stage B, run a 10% random-sample manual review on local-backend output before declaring it "passed"

### Phase 4 Exit Criteria

- [ ] Conversion agent implementation is complete with all three backends working
- [ ] All maps have generated `.pory` files
- [ ] All `.pory` files compile through Poryscript
- [ ] Flag registry is complete and consistent
- [ ] Unhandled queue is fully triaged (every item has a decision)
- [ ] 10% sample of Stage B output has been manually reviewed and approved

---

## Phase 5: Map Layout & Tileset Conversion

**Duration:** 4–6 weeks (longer if you do tilesets carefully).

### Goals

Convert RPG Maker map layouts into Porymap-compatible format, including tileset graphics adapted to GBA constraints.

### The hard part

GBA has hard tile constraints: 8×8 pixel tiles, 16-color palettes per tile, max 16 palettes per tileset. RPG Maker uses 32×32 logical tiles built from arbitrary art with full RGB palettes. You can't just resize.

### Two approaches

**Approach A: Reuse pokeemerald-expansion tilesets** *(recommended for first pass)*
- Substitute Uranium's RPG Maker tiles with the closest matching existing pokeemerald-expansion tiles (grass, path, building exterior, etc.)
- Loses art identity but is dramatically faster
- Maps will look like Hoenn-styled versions of Uranium's regions
- Acceptable for proof-of-concept

**Approach B: Recreate Uranium's tilesets in GBA format** *(do later)*
- Manually reauthor each tileset
- Significant pixel art work; weeks per major tileset
- Save for Phase 8 polish or a v2

### Tasks (Approach A)

**5.1 Tile mapping table**
- Build a manual JSON map: Uranium tileset ID + tile index → pokeemerald-expansion metatile ID
- This is grunt work; budget time for it
- Most "grass" maps to one or two metatiles, most "path" similar; the long tail is interior tiles

**5.2 Map layout converter**
- Python script reads the tile arrays from Phase 3 JSON
- Applies the tile mapping table
- Outputs Porymap-compatible map JSON files

**5.3 Map metadata wiring**
- Hook up the converted maps to the encounter tables from Phase 2
- Hook up the events from Phase 4 to map coordinates
- Set up warps (transitions between maps)

**5.4 Connections**
- RPG Maker uses different conventions for map connections than pokeemerald
- Manual wiring in Porymap, working from Uranium's overworld map as reference

### Phase 5 Exit Criteria

- [ ] All maps render in Porymap
- [ ] Warps connect correctly
- [ ] Encounter tables are wired to maps
- [ ] Events appear at correct coordinates

---

## Phase 6: Custom Engine Features (Nuclear Type)

**Duration:** 1–2 weeks.

### Goals

Implement Uranium's Nuclear type as a real working type in the pokeemerald-expansion fork.

### Tasks

**6.1 Add the type constant**
- Extend `TYPE_*` enum with `TYPE_NUCLEAR`
- Update type count in headers

**6.2 Type effectiveness chart**
- pokeemerald-expansion uses `gTypeEffectiveness[]`
- Add Nuclear's effectiveness rules: super-effective against everything except Steel and other Nuclear types (per Uranium's rules — verify exact chart from source)
- All non-Nuclear moves are not very effective against Nuclear types (with documented exceptions)

**6.3 Type icon graphics**
- Add Nuclear type icon to the GBA UI sheet
- Update type display logic in battle UI

**6.4 Special status: Nuclear-type Pokémon take damage outside battle**
- In Uranium, Nuclear Pokémon lose HP each step until cured
- Implement as a field effect tied to the species/form flag
- Tie into existing field effect tick logic in pokeemerald-expansion

**6.5 Nuclear-cured-form transitions**
- Some Nuclear Pokémon have a "cured" non-Nuclear counterpart species
- Implement as form change tied to a key item or event flag
- Easier path: implement as evolution method, since the engine already supports complex evolution conditions

### Phase 6 Exit Criteria

- [ ] Nuclear type is selectable in trainer/wild Pokémon data
- [ ] Type chart correctly applies in battle
- [ ] Nuclear-type field effect ticks
- [ ] At least one Nuclear-cured transition works in a test save

---

## Phase 7: Integration & Build

**Duration:** 2–3 weeks.

### Goals

Bring all converted artifacts into the fork, build a complete ROM, and get it loading on Delta.

### Tasks

**7.1 Drop in converted assets**
- All generated C files from Phase 2 → fork's `src/data/`
- All `.pory` files from Phase 4 → fork's `data/scripts/`
- All converted maps from Phase 5 → fork's `data/maps/`
- Nuclear type code from Phase 6 → fork's `src/`

**7.2 Resolve build errors**
- Expect dozens to hundreds initially
- Most will be name mismatches (Uranium ID vs. expansion constant name)
- Some will be Poryscript syntax errors not caught by the standalone compiler
- Some will be C struct field mismatches between expansion versions

**7.3 ROM size budget**
- GBA ROM cap: 32MB. pokeemerald is ~16MB baseline. Uranium's content (sprites especially) is large.
- If you blow the budget: drop sprite resolution, reduce music quality, cut content
- Monitor the build output for size warnings

**7.4 Save file format check**
- Make sure the save format change (new species, new flags) doesn't conflict with the expansion's save migration logic

**7.5 First ROM boot**
- Open in Delta
- Goal: title screen renders, new game starts, player can take a step

### Phase 7 Exit Criteria

- [ ] Full build succeeds
- [ ] ROM loads in Delta on iPhone
- [ ] First 60 seconds of gameplay run without crash

---

## Phase 8: Playtest & Polish

**Duration:** Open-ended. The Phase 0 success criteria define the floor.

### Tasks

**8.1 Playthrough log**
- Play in 30-minute sessions, log every bug
- Categorize: blocker / functional / cosmetic / lore-breaking
- Triage by category

**8.2 Common bug categories to expect**
- **Soft locks:** event flags not getting set correctly; player gets stuck
- **Wrong dialogue:** LLM picked the wrong branch; gendered pronouns swapped
- **Sprite mismatches:** trainer sprite doesn't match the data
- **Battle imbalance:** AI behaves wrong because move data converted incorrectly
- **Music cuts:** audio compression issues or missing tracks
- **Map seam visual glitches:** tile mapping table edge cases

**8.3 Iteration loop**
- Fix bugs by category
- Re-run the relevant pipeline phase if it's a systematic issue, not a one-off

**8.4 Documentation pass**
- Update `rpg2gba` README with everything learned
- Document which Uranium features made it, which were stripped, which are partially working

**8.5 Pipeline generalization**
- Once Uranium is playable, audit which parts of the pipeline are Uranium-specific vs. reusable
- Refactor toward generic — the next target (Insurgence) should reuse most of this

---

## Agent Guidance

This roadmap involves two agents (see [Two Agents in This Project](#two-agents-in-this-project) above). Each gets its own guidance.

### Build Agent Guidance

What you'd hand to Claude Code (or any agent) working in the rpg2gba repo. The full version lives in `CLAUDE.md`; this is the conceptual outline.

**Operating principles**

1. **Stop and ask when uncertain.** Mismatched flag names propagate; mismatched move IDs corrupt battle balance silently. Bias toward asking rather than guessing on data fidelity questions.
2. **Idempotence.** Every converter should be re-runnable. No converter writes to a file it didn't create. Output to `output/` directories that can be wiped clean.
3. **One source of truth per concept.** The flag registry is the only place flag names are minted. The PBS species converter is the only place `SPECIES_*` constants are minted. Other tools read from these, never invent their own.
4. **Manual review gates.** After Phase 2, after Phase 4, and after Phase 7, there is a hard manual review checkpoint. Don't let the build agent push past these autonomously.
5. **Boundary respect.** The build agent works on rpg2gba code, not on the conversion agent's prompts at runtime. If the conversion agent's prompts need updating, that's a deliberate code change reviewed like any other.

**What the build agent is NOT allowed to do**

- Modify the PBS converter outputs by hand (those are deterministic; if they're wrong, fix the script, not the output)
- Invent new pokeemerald-expansion C constants outside the flag registry
- Modify `output/` artifacts directly to "fix" something — fix the converter that produced them
- Skip writing tests for new converters

### Conversion Agent Guidance

The conversion agent is the runtime LLM component inside rpg2gba. Its instructions live in `src/rpg2gba/conversion_agent/prompts/system.md` — the build agent maintains this file, but the conversion agent is what actually consumes it. The conceptual outline:

**The conversion agent's job, in one sentence**

Translate one RPG Maker event's command list into the equivalent Poryscript, using the provided flag registry for naming, and explicitly flag anything it can't translate.

**Prompting conventions**

- Always include the current flag registry state
- Always include 2–3 few-shot examples of a similar conversion
- Demand structured output: a JSON block with the Poryscript code, new flags proposed, and unhandled command annotations
- The orchestrator rejects and retries if the output doesn't compile through Poryscript

**What the conversion agent is NOT allowed to do**

- Invent flag names without proposing them to the registry — the orchestrator owns the registry, not the agent
- Skip events it can't translate — must explicitly emit an `unhandled` annotation with the event's identity and the unrecognized command codes
- Output anything other than the structured response format
- Reach outside its prompt — it has no codebase access, no tools, no memory across calls
- Refer to the build agent or the wider pipeline — it doesn't know those exist, and shouldn't pretend to

**Failure modes to design against**

- **Hallucinated flag names.** Mitigated by the registry being the source of truth and the orchestrator validating new flag proposals before accepting them.
- **Silently skipped commands.** Mitigated by structured output that requires explicit acknowledgment of every input command.
- **Verbose, non-idiomatic output (especially from local backends).** Mitigated by quality of few-shot examples and the optional Stage C refinement pass.

---

## Known Pitfalls

A non-exhaustive list of traps documented before they bite:

- **Essentials version drift.** Uranium was built on a specific Essentials version. PBS format and field names changed between versions. Pin to Uranium's exact version when reading reference docs.
- **`Marshal.load` security.** Don't run the rxdata deserializer on untrusted files. It's loading arbitrary Ruby objects.
- **Encoding gotchas.** Uranium's text data may be Windows-1252 or UTF-8 depending on origin. Set encoding explicitly in every file read.
- **Sprite color depth.** RPG Maker sprites are full-color PNG. GBA sprites are 4bpp indexed (16 colors per palette). Conversion will visibly degrade sprites; budget for manual cleanup of important ones (player, starters, gym leaders).
- **Music format.** RPG Maker uses OGG/MP3. GBA uses sappy/m4a sequences. You're not converting music — you'll need to either substitute existing pokeemerald music or commission/source new sequences. Consider this a Phase 8 nice-to-have.
- **The conversion agent will hallucinate flag names.** Build the registry as a deterministic gate; never let the conversion agent write directly to the canonical list.
- **Build times scale poorly.** Once all content is in, full builds may take 10+ minutes. Set up incremental builds early and use `make -j`.
- **iPhone Delta save compatibility.** Save state format must be GBA-standard. The expansion's save extensions are GBA-compatible by default but verify on a test save before deep playtesting.
- **The legal corner.** This is for personal use only. Don't distribute the resulting ROM. Don't put the Uranium source or pokeemerald base ROM in a public repo. The pipeline tool itself can be public; the build artifacts cannot.

---

## Glossary

- **Essentials / Pokémon Essentials:** Ruby-based fan-made framework on top of RPG Maker XP, used by most PC Pokémon fan games.
- **PBS (Pokémon Batch Script):** Plain text data files used by Essentials for species, moves, items, etc.
- **rxdata:** Binary serialized Ruby object format used by RPG Maker XP for maps, events, scripts, and system data.
- **pokeemerald:** The pret community's full disassembly of Pokémon Emerald, allowing modification in C.
- **pokeemerald-expansion:** Community fork (rh-hideout) adding Gen 4–9 mechanics, modern features, and quality-of-life upgrades.
- **Porymap:** Visual map editor for pokeemerald-family projects.
- **Poryscript:** Higher-level scripting language that compiles to pokeemerald's native script bytecode.
- **devkitARM / agbcc:** Cross-compiler toolchains for building GBA ROMs.
- **Layer (1/2/3/4):** This roadmap's framing of conversion difficulty — data, events, engine, custom features.

---

## References

- pret/pokeemerald (decomp project)
- rh-hideout/pokeemerald-expansion (the fork to start from)
- huderlem/poryscript (script compiler)
- huderlem/porymap (map editor)
- Pokémon Essentials Wiki (PBS format docs)
- RPG Maker XP RGSS reference (event command codes)
- Pokémon Uranium 1.3.2 distribution (the team's last public release; not open-sourced — extract the `.rgssad` archive to access game data)

---

*This roadmap is a living document. Update phase exit criteria, durations, and pitfalls as you go. The goal is for this file to read like a debriefing of a real project by the time Uranium is playable.*
