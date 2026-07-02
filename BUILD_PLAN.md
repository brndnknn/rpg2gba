# BUILD_PLAN.md — the active build sequence

**Status:** live. This is the project's single "current *how*" doc. `ROADMAP.md` owns
the long-term *what/why* (phases, success criteria); this owns the steps we're
executing right now. When they conflict on *what*, ROADMAP wins; on *how*, this wins.

This doc absorbs and supersedes the live content of the former root planning docs
(`PATHFINDER_*`, `ITERATIVE_ROADMAP`, `DETERMINISTIC_EXPANSION_STRATEGY`,
`OQ3_EMPIRICAL_PLAN`), now archived under `reference/archive/`.

> **Amendments 2026-07-02** (grill session on the spine; full decision record +
> slice census: `reference/grill_spine_2026-07-02.md`):
> - **§5 first-cut is overturned:** transpiler v1 does NOT stub all of 209 — it
>   emits the deterministic tier (raw `MOVEMENT_ACTION_*` + the SOFT-C rules the
>   slice's own 91 routes need) and queues the rest; anything still stubbed must
>   neutralize its paired 210 wait. The slice's opening cutscenes are move-route
>   heavy; stub-all would ship a booted-but-unplayable slice.
> - **§8 "orchestrator checkpoint/memo machinery (repurpose)" is stale:** the
>   transpiler gets a new thin driver with no checkpoints/memo (deterministic ⇒
>   full re-runs); only the unhandled-queue format + triage clustering are reused.
>   `orchestrator.py`/`backends/` remain solely the hand-invoked LLM tail tool.
> - **§4 index source pinned:** the capability index reads git-tracked *pristine*
>   `engine/` content (never the working tree — the pipeline injects Uranium
>   symbols into generated headers); the forward gate resolves index ∪ flag
>   registry ∪ map-constant registry ∪ PBS outputs, and enforces at BOTH
>   conversion time and staging. Gate failure = our bug = abort loud, never queued.
> - **Sequencing:** walker-first was drift, not a decision. The spine is anchored
>   to finishing the pathfinder slice (six-point done bar in the record; slice 1
>   stays 3 maps, starter/Route 1 = slice 2). Slice 1 assembles via
>   `assemble_pathfinder` as-is; phase5 unification is a separate post-slice unit.
> - **Prereq before any spine code:** archive the frozen-Opus oracle out of
>   gitignored `output/uranium-build/scripts/` (a `--clean` destroys it); it's a
>   one-time harvest-then-retire oracle, with goldens minted from reviewed
>   transpiler output.

---

## 1. The pivot, in one paragraph

The LLM is **retired as the conversion spine.** Event→Poryscript becomes a
**deterministic command→Poryscript transpiler** (built by generalizing the existing
timid page-walker `deterministic._dialogue_body`). The frozen-Opus prompt/bulk-run
machinery is retired; the Opus output already on disk (maps 001–007 + CommonEvents)
is kept only as a **differential-validation oracle**. The LLM survives as a
*hand-invoked tool for the irreducible tail* (branch-heavy story logic, novel
embedded Ruby), never as an unattended daemon.

Why (measured, not asserted): the dangerous error class is *compile-clean-but-wrong*
(wrong item constants, mistagged dispositions) — silent and unbounded. The
deterministic pre-filter already reproduces ~36% of events byte-for-byte identical
to Opus. And the pathfinder slice's playability blockers were **all** deterministic
pipeline gaps, not LLM gaps. A transpiler trades the LLM's silent-wrong risk for a
*bounded, visible* unhandled queue you can read to completion.

---

## 2. Operating model: vertical playable slices

We build the pipeline in **vertical slices**, not horizontal phases. A slice = *every
artifact a player touches in one play-order section, converted for real, booting and
playable* — events **and** quantized art. Then we **widen the playable frontier** one
trustworthy slice at a time.

This is the structural fix for "did a bunch of work, found out it was wrong." The
pathfinder slice booted but came back unplayable precisely because it *deferred the
load-bearing parts* (bucket tilesets, no real sprites). "Done" is not allowed to
exclude what a player sees.

**The guardrail that keeps a slice from degrading into hand-finishing one area:**
every converter stays **general, idempotent, config/data-driven.** The mechanical
test — *slice 2 must need data/config changes, not code changes.* Hold that bar and
slices build the pipeline; drop it and they become a content grind.

### Per-slice loop (checklist)
```
SLICE N
 1. SELECT the play-order section (maps + their warps/connections).
 2. EVENTS — run the deterministic transpiler over the section's events.
      • everything mechanical → Poryscript; uninterpretable script-calls → queue.
      • differential-test against the frozen-Opus oracle where it overlaps.
 3. ART — quantize the section's real tilesets + sprites to GBA 4bpp.
 4. WIRE — map constants, layouts (collision + warp metatiles), object events,
      encounters, connections.
 5. BUILD — assemble into the fork; `make modern` must exit 0.
 6. BOOT — run in mGBA; walk the section. This is the gate (see ROADMAP §9).
 7. FIX — cluster any systematic defect; fix the *converter*, re-run. Never hand-edit
      output.
 8. RECORD — MEMORY Current Phase + Decisions; commit one logical unit.
 → widen the frontier: SLICE N+1.
```

---

## 3. The deterministic transpiler (Option B)

### 3.1 Where it comes from
`src/rpg2gba/conversion_agent/deterministic.py` already contains a command-by-command
page walker, `_dialogue_body`, that emits Poryscript per command **but bails
(`return None`) on anything outside a small allow-set.** The transpiler is the
*generalization* of that walker from "bail on unknown" to "emit for every command,
queue only the uninterpretable." It is not a from-scratch rewrite.

The existing whole-event **classifiers** (`classify_ground_item`, `classify_pokemart`,
…) are **not discarded** — they become an **idiom-collapse layer** that runs on top of
the transpiler to render recognized multi-command idioms as clean macros
(`giveitem`, `pokemart`) for readability. The transpiler is the floor; classifiers
are polish.

### 3.2 Build sequence
1. **Fork capability index + verification gates** (§4) — prerequisite; the transpiler
   must resolve every symbol it emits.
2. **`transpile_page`** — generalize `_dialogue_body`:
   - text runs (101/401) → `msgbox`; transfer (201) → `warp`; control switches/vars
     (121/122) → `setflag`/`clearflag`/`setvar`/`copyvar`; self-switch (123) →
     minted flag; call CE (117) → `call`.
   - **control flow** (the real work): parse the flat command list into a tree —
     conditional branch (111/411/412) → `if/elif/else` with a condition-type emitter
     (switch / variable / `s:`-script); choices (102/402–404) → choice blocks; loops
     (112/113) → `while`; labels/jumps (118/119) → `goto`.
   - **move routes (209)** → `applymovement` — see §5. **First cut: stub-and-queue**
     so we reach a booting slice fast; resolve second.
   - **script calls (355/655)** → the idiom library (re-homed classifiers); unknown
     `pbXXX` → fail-loud queue (never silently dropped).
   - **flag/var naming** → deterministic from `reference/uranium_switches.json` /
     `uranium_variables.json` (developer-named switches → readable constants via
     `_naming.to_constant`; `s:`-prefixed conditional switches handled by a small
     interpreter — self-switch checks, time-of-day, game-state predicates).
3. **Differential-validate** — transpile the 7 done maps + CommonEvents; diff against
   the frozen-Opus `.pory`. Every divergence is either a transpiler bug or an Opus
   error we're glad to delete. This is the correctness loop (cf. the old
   iterative-roadmap "invariant 4" differential test, now applied to the whole
   transpiler instead of one classifier at a time).

### 3.3 Honest limits
Verbose output for hard events — fine; the goal is *playable*, not *maintainable
fan-port*. The transpiler does **not** make hard events free; it makes them *honest*:
branch-heavy story logic with novel embedded Ruby becomes a **visible, prioritized
queue** instead of a silent-wrong risk. That queue is where the hand-invoked LLM (or
the operator) does deliberate, reviewed work.

---

## 4. Fork-index verification guard (both directions)

Root cause of the `healparty`-was-invented / over-queued-engine-features bugs: the
gate only ever checked **syntax** (poryscript), never whether emitted symbols *exist*
in the fork, nor whether a native analog *already existed*. Verified evidence:
`HealPlayerParty` IS a defined special (`data/specials.inc:20`) — the analog was
right there. The fork exposes **624 specials + 385 script-command macros** + thousands
of constants; that is the vocabulary every decision must be checked against.

**Build a fork capability index** (deterministic, rebuilt from the fork, idempotent),
consolidating today's piecemeal parsers (`load_fork_constants`, `load_multi_constants`,
`load_charmap_chars`):
- `commands` — 385 macros in `asm/macros/event.inc`
- `specials` — 624 `def_special` in `data/specials.inc`
- `constants` by category — `include/constants/*.h` (ITEM_/MOVE_/FLAG_/VAR_/MAP_/
  OBJ_EVENT_GFX_/MOVEMENT_ACTION_/MUS_/SE_/MULTI_/…)

**Forward gate — catch invented symbols.** After poryscript, resolve every emitted
command/special/constant against the index, or **fail loud at conversion time.**
Closes the hole where invented commands/unresolved symbols sailed through to die at
`make modern`. (Bonus: poryscript can also be handed a command list to reject unknown
commands itself.)

**Reverse gate — catch over-queuing.** Nothing may be queued "needs custom code"
without an explicit *no-analog* entry **backed by a fork search**. Splits the one
conflated queue into three honest buckets:
- **native analog exists** → emit it, don't queue *(the wrongly-flagged class)*
- **genuinely needs engine** → Phase 6, *with the evidence no analog exists*
- **unknown / unverified** → a human checks it against the fork

The reverse gate is curation, not full automation (knowing `pbBerryPlant` truly has
no analog is semantic) — but the index makes each search cheap and authoritative.
Native-analog ledger lives in `reference/essentials_to_emerald_map.md`. **Seed the
vocabulary up front** by reading `specials.inc` + `event.inc` in full, so "no native
equivalent" is a checkable claim — this alone retires a chunk of the standing Phase-6
queue (most "engine feature" tags ship natively: cave/Flash, bridges, PC, region map,
relearner, trade, rock smash — only the Nuclear type is genuinely new C).

---

## 5. Move-route determinism (OQ-3 answer)

1,191 events touch code 209. Empirical census (`scripts/moveroute_coverage.py`):
**raw macro determinism 24%, potential 65% after 5 SOFT-C rules, irreducible HARD
tail 35%.** So in the transpiler: emit direct `MOVEMENT_ACTION_*` where deterministic,
apply the SOFT-C rules for the param-deterministic middle, and **stub-and-queue** the
hard tail. First cut stubs *all* of 209 to reach a booting slice; the 24%→65% work is
the second pass. Re-bucketing edit point = the `CANDIDATE` dict + `SOFT_C` set in that
script.

---

## 6. Active slice: pathfinder (Maps 49 / 48 / 32)

**Work unit.** Map 49 = Player's House 1F (spawn @7,7) ↔ Map 48 = 2F ↔ Map 32 = Moki
Town. This is the game start (new-game spawns at 49), already wired through S1–S9; the
remaining gaps are exactly the art + the systematic fixes the slice exists to surface.
(Full S1–S9 history: `reference/memory-archive.md`.)

**S9 boot diagnosis — 3 root-cause classes:**
1. **Warps don't fire — FIXED (converter level).** pokeemerald gates warps on
   `IsWarpMetatileBehavior`; the v1 bucket layout gave warp tiles a plain floor
   metatile (`MB_NORMAL`), so nothing fired. Fix: a per-tileset `warps` metatile in
   `tileset_map.json` + `TileMap.warp()` + `convert_layout` stamps it at each warp
   coord. Chosen `MB_NON_ANIMATED_DOOR` step-on doors — **ts19→metatile 529**,
   **ts22→metatile 167**. (Needs re-assemble + rebuild + boot to confirm in-game.)
2. **Crowd of identical NPCs — OPEN.** `metadata_wiring.build_object_events` emits
   *every* non-warp event as a solid `OBJ_EVENT_GFX_NINJA_BOY` with no check for an
   RMXP graphic (invisible script triggers become solid NPCs) and no real gfx map.
   Fix: skip/invisible+non-blocking for graphic-less events; build the RMXP
   `character_name` → `OBJ_EVENT_GFX_*` map.
3. **Layout "makes no sense" — OPEN (by-design v1).** The passability-bucket scheme
   collapses each tileset to two metatiles (floor/wall +void): no doors, furniture,
   stairs, structure. The real fix is the image pipeline (§7) — actual per-tile
   substitution.

Recommended order: warps (done) → NPC visibility+gfx → real tile substitution.

---

## 7. Image pipeline (quantize real art) — greenfield

Decision: **quantize Uranium's real tilesets/sprites to GBA format**, not substitute
closest Hoenn tiles. The reusable capability, and the only path to an
actually-Uranium-looking ROM.

Today `tileset_converter` maps *metatile IDs and structure* only (`tile_map`,
`layout`, `assembly`). Actual **PNG→GBA-4bpp graphics** (32×32 RGB → 8×8 tiles,
16-color palettes, ≤16 palettes/tileset, 4bpp indexed) does not exist yet — new
pipeline code, real GBA constraints. Deterministic + idempotent + **validated by
looking at the booted ROM**, same discipline as the transpiler. Accept degraded
fidelity on a first pass; manual polish of hero assets (player/starters) is Phase-8.

---

## 8. Retained vs retired

| Retained | Retired |
|---|---|
| Phase 2 PBS converters, Phase 3 deserializer | LLM-as-conversion-spine / bulk run |
| All deterministic classifiers (→ idiom-collapse layer) + flag registry | Frozen-prompt discipline (`system.md` now an editable tail-tool prompt) |
| Assembly: normalize/prune/charmap/existence-check | Horizontal phase-ordered campaign |
| Pathfinder S1–S9 converters (tile_map/layout/map_constants/metadata_wiring/assembly) | Frozen-Opus `.pory` *as product* (→ kept only as differential oracle) |
| Orchestrator checkpoint/memo machinery (repurpose) | 19 scattered root planning docs |

**Tracked obligation:** the fork-baseline divergences (`new_game.c` WarpToTruck spawn
override + `intro.c` intro-skip, sentinel-fenced, uncommitted) are *test-only* and
must be reverted/gated before any real build — a fresh fork clone drops them. See
MEMORY → Decisions Made.
