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
- **The other "agent" is a tail tool, not a peer.** The conversion spine is the **deterministic transpiler** you write and run (§4.1) — that is where conversion happens. What remains of the LLM is a *runtime component of rpg2gba itself*, **retired as the spine on 2026-06-18** and hand-invoked only for the irreducible tail (branch-heavy story logic, novel embedded Ruby the transpiler can't interpret). It has no awareness of the codebase. Its prompt lives in `src/rpg2gba/conversion_agent/prompts/system.md` — **no longer frozen** (see §7) — and you maintain it like any other source file. Its shrinking is the point: anything it handles that could be handled deterministically is a transpiler feature waiting to be written.

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

**Orientation, not an inventory.** This section names the handful of places you need to get
your bearings. It is deliberately *not* a directory tree — a hand-drawn tree lived here until
2026-09-08, went stale in nine packages, and was the third such stale tree in this repo.
**Run `ls src/rpg2gba/` for the current package list**; the filesystem is the inventory.

- **`src/rpg2gba/`** — the pipeline. The five packages worth knowing by name:
  `pbs_converter/` (PBS data → C tables), `map_deserializer/` + `rxdata_deserializer/`
  (RMXP `.rxdata` → JSON, via Ruby), `conversion_agent/` (**the deterministic event→Poryscript
  transpiler lives here**, despite the name — plus the flag registry and the hand-invoked LLM
  tail tool), and `tileset_converter/` (graphics, layout, and map assembly). The chapter loop's
  own packages — `chapter_atlas/`, `chapter_manifest/`, `routing/`, `playtest/` — are listed
  with their commands in §7.
- **`reference/`** — hand-authored docs and the source-of-truth JSONs (§4.3). `guides/` is
  pipeline knowledge, `chapters/` is the per-chapter corpus plan, `archive/` is retired docs
  (read `reference/archive/README.md` first — it maps each archived doc to where its live
  content went).
- **`scripts/`** — utilities and instrumentation (the map viewer, oracle/comparison tools).
  **~75 of its ~95 files are spent one-offs and only three say so**, so do not infer liveness
  from a filename here. `scripts/assemble_pathfinder.py` in particular is named for a retired
  era and is the assembly step of *every* chapter build.
- **`engine/`** — the vendored pokeemerald-expansion fork; custom C lives here. See below.
- **`output/`** — generated artifacts, gitignored, safe to wipe and regenerate.
- **`tests/`**, **`investigations/`** — the suite, and durable investigation docs.

### Things outside this repo you may need to read

- The Uranium source tree (path configured in env var `RPG2GBA_URANIUM_SRC`) — stays external; its contents never enter git.

### The vendored engine (`engine/`)

The `pokeemerald-expansion` fork is **vendored** in `engine/`, pinned at upstream `21c24202` (see `engine/RPG2GBA_VENDOR.md`). Custom engine C (Phase 6, plus the slice's spawn-override/intro-skip) lives there in version control — no longer an external sibling clone. `RPG2GBA_POKEEMERALD` is the path the pipeline uses, and the **cutover is DONE** (2026-06-19): it points at `engine/`, this repo's vendored tree. There is no external sibling clone at all any more — **`/home/b/repos/pokeemerald-expansion` was deleted 2026-09-07** (operator-run, after the audit established that nothing unique lived in it: `80cdfce2` already holds the pristine baseline, and upstream is one `git clone` from GitHub). If a doc or script sends you to that path, the reference is stale — you want `engine/`. `engine/build/` and the assembler's generated output under `engine/` are gitignored.

**To see what we changed versus stock pokeemerald-expansion, run `git diff 80cdfce2 HEAD -- engine/`** — but read the next paragraph before trusting it as complete. `80cdfce2` is the vendor-import commit; upstream `21c24202` is not a reachable object in this repo, so it cannot be used as a diff base. Never trust a hand-maintained list of "the custom files"; one rotted badly enough to be the top finding of the 2026-09-07 repo audit.

**`80cdfce2` is not a pristine baseline, and neither check is complete alone (verified 2026-09-07).** The vendor import was taken from a *dirty* working tree: three files arrived already carrying custom edits, so the diff above cannot see them. Verified by blob hash against upstream `21c24202` before the external clone was deleted — 29,958 of 29,961 files identical, the exceptions being `include/new_game.h`, `src/intro.c` and `src/new_game.c` (33 lines: the intro/title/menu skip and the new-game spawn override into Moki Town). All 33 lines *are* properly `URANIUM PATHFINDER SLICE`-fenced, so a sentinel grep finds them. This is the exact inverse of the §5 trap: **fences miss unfenced edits, and the diff misses pre-import edits. Use both — the union is the answer, neither half is.** (12 upstream files are also absent from `engine/`: `tools/compresSmol/*`, which `engine/.gitignore` excludes, plus `tools/mgba/mgba-rom-test.exe`. Benign.) `engine/RPG2GBA_VENDOR.md` carries an orientation summary of the feature areas, explicitly *not* an inventory.

**Never set `RPG2GBA_*` yourself — not inline, not exported, not in a subshell.** The tracked `.env-paths` file at the repo root holds the correct values and the pipeline loads it at startup. Shell env *wins* over that file, so an inline override silently redirects the build at a tree that cannot work. This has burned a full session: an agent exported the stale clone path, hit the pristine tree's missing `include/config/rpg2gba.h`, and reported a fabricated "the fork lacks the event-range extension" blocker. The header has been committed at `engine/include/config/rpg2gba.h` since `5fc67dbf`. Run the pipeline commands bare and let it resolve its own paths.

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
| Constant *spelling* for every `SPECIES_*`/`MOVE_*`/`ITEM_*`/`ABILITY_*`/`TYPE_*` | `src/rpg2gba/pbs_converter/_naming.py` → `to_constant(prefix, name)` — the single mint point (consolidated 2026-09-07; it replaced five hand-copied `*_constant` helpers, two of which had drifted) |
| Name → constant *resolution* at emit time | `src/rpg2gba/pbs_converter/_resolve.py` (`MoveResolverMixin`, `SpeciesResolverMixin`, `ItemResolverMixin`, `AbilityResolverMixin`, `TypeResolverMixin`) |
| `SPECIES_*` table contents | `src/rpg2gba/pbs_converter/pokemon.py` output |
| `MOVE_*` table contents | `src/rpg2gba/pbs_converter/moves.py` output |
| `FLAG_*` / `VAR_*` names | `src/rpg2gba/conversion_agent/flag_registry.py` |
| Uranium internal name → expansion constant | `reference/uranium_id_map.json` |
| Tile substitution table | `reference/tileset_map.json` |
| Whole-artifact STRIP decisions (CE ids / whole maps / map events) | `reference/strip_list.json` |
| Corrected map identity / display name (overrides `MapInfos`) | `reference/map_name_overrides.json` |
| Act / chapter chain, tiers, map membership | `reference/chapters.json` (prose half: `reference/chapters/00-atlas.md`) |
| Seam warp pairs (arrow-warp substitution for a connection whose maps can't share a tileset) | `reference/seam_warps.json` |

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
- **Reverse:** never queue anything "needs custom C" without a fork search proving no native analog exists. `HealPlayerParty` was a defined special the whole time the agent invented `healparty`. Native-analog ledger: **`reference/guides/command_pokeemerald_map.md`** (corrected 2026-07-30 — this rule used to point at `essentials_to_emerald_map.md`, which is the flag/var *pre-seed* table for the registry, not a capability ledger; the misdirection is part of why the `healparty` claim survived so long).

Most "engine feature" tags ship natively (cave/Flash, bridges, PC, region map, relearner, trade, rock smash); only the Nuclear type is genuinely new C.

---

## 5. Code Conventions

### Python

- Python 3.11+
- **Scope of this section:** the rules below are binding in `src/rpg2gba/`. In `scripts/` and
  `tests/` only the built-in-generics ban is binding — it holds repo-wide and is enforced.
  (Measured 2026-09-07: type-hint coverage is complete in `src/` and ~17%/18% short in
  `scripts/`/`tests/`. A pytest test has no caller, so `-> None` on it buys nothing. Scoping
  the rule is deliberate — a rule everyone breaks teaches the reader this file is decorative.)
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

- C code lives in the **vendored engine** (`engine/`, pokeemerald-expansion) — in-repo now, not an external fork. Mark custom edits with sentinel fences so they're locatable against pristine upstream. The vocabulary is **four** strings, not one (corrected 2026-09-07); pick the one matching the feature area:
  - `URANIUM PATHFINDER SLICE` — the original slice work and most generated-content include-hooks
  - `URANIUM MAP WALKER` — the map-walker harness (NPC suppression, free movement)
  - `URANIUM EMBEDDED SAVE` — boot-continue instead of always-new-game
  - `RPG2GBA EVENT RANGE EXPANSION` — the expanded flag/var ranges

  Normal form is a `// BEGIN <sentinel> — why` / `// END <sentinel>` pair; a bare `// <sentinel>: …` opener with a matching `// END <sentinel>` also occurs in older edits. **A fence is a locator, not a revert script** — grep for the sentinels to find edits, but use `git diff 80cdfce2 HEAD -- engine/` (§3) as the authority on what is actually custom. Fenced-only reverts have historically missed unfenced one-line edits.
- Follow the conventions of pokeemerald-expansion for any new code there: tabs, K&R-ish brace style, `g`-prefixed globals, `s`-prefixed statics
- New constants go in the same headers as their kin (`include/constants/species.h`, etc.)

### Conversion agent prompts

The conversion agent's prompts are source code. Treat them with the same care.

- `src/rpg2gba/conversion_agent/prompts/system.md` is the canonical instruction set
- Few-shot examples live in `src/rpg2gba/conversion_agent/prompts/few_shot/` as individual `.md` files, one per scenario, named descriptively (`give_item_with_fanfare.md`, `branching_dialogue.md`)
- The prompt is **no longer frozen** (the bulk run is retired); edit it like any source file. It serves only the hand-invoked tail tool now, so changes are scoped to that tool, not a 199-map run.

---

## 6. The Flag Registry

The full policy lives in **`reference/guides/flag_registry_policy.md`**. **It is a Phase 4
component and Phase 4 is the active phase** (`MEMORY.md` → Current Phase), so this is live
right now — read it before touching flags or vars. It's the most common place pipelines like
this go wrong, so don't wing it. *(Corrected 2026-09-08: this paragraph used to say the
registry was "dormant during the current Phase 2", which was false and, worse, told the
reader to skip the hard rule immediately below it.)*

**Hard rule (applies always):** Every flag/var name goes through the registry —
never hardcode one, even one you're certain of. You may modify `flag_registry.py`
and `reference/guides/essentials_to_emerald_map.md`, but you may **never** hand-edit the
registry's persistent state file mid-run. If the state is wrong, fix the input
data or the registry logic — don't patch the output.

**Naming is now mostly deterministic:** Uranium named most of its switches/vars
(`reference/uranium_switches.json` / `uranium_variables.json`), so readable
`FLAG_*`/`VAR_*` come straight from `_naming.to_constant` — no LLM. The `s:`-prefixed
conditional switches are runtime predicates (self-switch checks, time-of-day), not
stored flags; never mint a `FLAG_*` for them.

---

## 7. Working with Each Pipeline Phase

**`MEMORY.md` → Current Phase is the *sole* authority on the frontier** — what is
done, what is in progress, and what to do next. Nothing else in this repo states
current status, and where another document appears to, `MEMORY.md` wins without
argument. (Established 2026-09-07: the repo audit found six documents each implicitly
claiming currency with nothing ranking them, which is why agents kept picking up
retired processes.)

Everything else is a **topic reference** — correct about its subject, silent about the
frontier:

| Document | Owns | Does *not* own |
|---|---|---|
| `MEMORY.md` → Current Phase | the frontier: active phase, next concrete task | — |
| `ROADMAP.md` | per-phase goals, tasks, exit criteria (Phases 0–8) | what phase we're on |
| `BUILD_PLAN.md` | *how* — the transpiler design and the per-chapter operating loop | which chapter is next |
| `reference/chapters/00-atlas.md` (+ `chapters.json`, per-chapter docs) | the corpus-wide chapter plan and each chapter's scope | which chapters are done |
| `PROJECT_TODO.md` | the open-item backlog | priority order or currency |

Read `MEMORY.md` first, then whichever topic references your task actually needs. If
you catch a topic reference asserting frontier status, fix it in place with a dated
correction in the same change — don't file it.

**Phase 4 was pivoted (2026-06-18):** the LLM-driven bulk run is retired. Event→
Poryscript is now a deterministic transpiler you build and run (`BUILD_PLAN.md §3`);
the existing classifiers become an idiom-collapse layer on top; the LLM is a
hand-invoked tail tool only, and its prompt (`system.md`) is **no longer frozen**.
The conversion campaign runs as **vertical playable chapters**, not a horizontal grind
— a chapter isn't done until it boots and is playable, art included (§9). Chapters
replaced ad-hoc "slices" as the unit of work (2026-08-05); the identity is
**chapter ≡ slice ≡ one §9 boot gate ≡ one ROM-test scenario** (`00-atlas.md` §1), so
the loop didn't change, only how sections are chosen and named. "Slice" survives in
code identifiers (`SLICE_MAP_IDS`) — deliberately not renamed.

### The chapter loop's entry points

**The `rpg2gba` console script is not the whole CLI, and reading `pipeline.py` alone will
mislead you.** It registers the pipeline *stages* (`phase2`, `phase3`, `phase4`, `phase5`,
`convert-map`, `convert-common-events`, `transpile-events`). The **chapter loop** — the way
work actually gets done now — lives in four separate packages, invoked as modules:

```bash
# SELECT — which chapter, and does the atlas agree it is coherent?
python -m rpg2gba.chapter_atlas validate | coverage | census

# READ — generate and check the chapter's manifest
python -m rpg2gba.chapter_manifest generate --chapter CHnn
python -m rpg2gba.chapter_manifest check    --chapter CHnn   # enforces RULE_ROUTE_ORDER

# ROUTE — solve the visit order, then write the plan
python -m rpg2gba.routing plan --chapter CHnn --module <mod> --dry-run
python -m rpg2gba.routing plan --chapter CHnn --module <mod>   # writes reference/routes/CHnn.route.json

# BOOT — the §9 gate
python -m rpg2gba.playtest run  --chapter CHnn
python -m rpg2gba.playtest walk --chapter CHnn --at-beat B7
```

Each is also an `rpg2gba` subcommand (added 2026-09-08): `rpg2gba chapter-atlas`,
`chapter-manifest`, `routing`, `playtest` — hyphenated, same subcommands underneath. Both
forms work and delegate to the same click groups. The full loop with its build/assembly steps
is `BUILD_PLAN.md §2`; the runnable end-to-end recipe is `README.md`.

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

# pokeemerald-expansion
cd $RPG2GBA_POKEEMERALD && make -j$(nproc) modern
```

*(Removed 2026-09-08: a `ruby test/test_deserializer.rb` line that pointed at a file and
directory which do not exist. The Ruby deserializer is covered indirectly through
`map_deserializer`'s Python tests; there is no standalone Ruby suite. If you want one, that
is a task, not a doc fix.)*

### When tests fail

Fix the failure. Do not skip, mark xfail, or comment out failing tests without explicit user approval. If a test is genuinely wrong, fix the test and explain why in the commit message.

---

## 9. Manual Review Gates

There are three points where you must stop and wait for the user, even if everything appears to be working:

1. **End of Phase 2** — before any PBS-generated content is committed to the pokeemerald-expansion fork, the user reviews the generated C output and the unfixed-issues list
2. **Per-chapter boot gate** — a chapter is not "done" until its ROM boots in mGBA and the section is genuinely playable (warps fire, NPCs sane, layout legible — *art included*, not deferred). The user walks each chapter before the frontier widens. (Replaces the retired end-of-Phase-4 frozen-prompt/bulk-run gate.) **For a generated chapter, the gate starts with the review doc** (added 2026-09-18, `C6_GENERATOR_PLAN.md` C2). The user reads and approves `CHnn.review.md` before the generated module is committed as `playtest/chapters_gen/chNN.py` (C9) and before the walk. *(Corrected 2026-09-24: C9 lands the generated suite **beside** the hand `chNN.py`, never over it; removing the hand suite is a separate operator-gated step — `REDERIVATION_PLAN.md` §16.3 "C9 rulings".)* That doc is the only human-visible record of the route solver's picks: seam cell, stair starting end, warp press side, event approach side and order-dependent writes.
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
- **Calling a chapter "done" while deferring art.** The pathfinder slice (CH01) booted but was unplayable because it deferred tilesets/sprites. A chapter isn't done until it's playable with real (quantized) art (§9).
- **Editing generated output to "fix" something.** Fix the converter, not its output — the output gets regenerated. (Corollary: never add silent fallbacks for unknown fields, and never emit a symbol the fork doesn't define; fail loud.)

---

## 12. Quick Reference

### Environment variables

The pipeline loads the tracked `.env-paths` at startup. **Never override any `RPG2GBA_*`
variable on a command line** — not inline, not exported, not in a subshell (§3). The table
below says where each value actually comes from, because that distinction has mattered.

| Variable | Set in | Purpose |
|---|---|---|
| `RPG2GBA_URANIUM_SRC` | `.env-paths` | Uranium source tree — note the `_unpacked` suffix; the parent dir is incomplete and looks broken if you check it by mistake |
| `RPG2GBA_POKEEMERALD` | `.env-paths` | The vendored engine — `engine/` in this repo, never an external clone |
| `RPG2GBA_PORYSCRIPT` | `.env-paths` | The `poryscript` binary. Resolved via this var or `PATH`; `poryscript.py` fails loud if absent |
| `RPG2GBA_OUTPUT` | **code default** (`"output"`) | Output directory. *Not* in `.env-paths`; it is an in-code default you may override via the environment if you genuinely need to |
| `OLLAMA_HOST` | `.env.example` only | Ollama server for the retired bulk path; not part of the chapter loop |

*(Corrected 2026-09-08: this table used to claim all four lived in `.env-paths`. It omitted
`RPG2GBA_PORYSCRIPT`, which does, and asserted `RPG2GBA_OUTPUT`/`OLLAMA_HOST` were pinned
there, which they are not.)*

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
