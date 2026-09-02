# CH05 — Passage Cave: live work items

**Status:** open, not yet started. Branch `ch05` **not yet cut** (see step 0).
**You are here:** → step 0, prerequisites. Nothing after it has begun.

**What this document is.** The execution path for CH05. Two other documents already
exist and this one does not repeat them:

| Document | Answers |
|---|---|
| `reference/chapters/05-passage-cave.md` | *What* CH05 contains — beats B1-B11, inventory, risks |
| `CH05_DECISIONS.md` | *Why* it is built this way — the A/B/C/D/E design calls |
| **this file** | *How* to build it, in order, with commands |

It is a **living document.** The "you are here" marker above moves, checkboxes get
ticked, and findings get appended to §Log as we go. It is not a plan written once and
then obeyed — when reality disagrees with it, the document is what changes.

On gate pass it retires to `reference/archive/` and its carryovers migrate to
`PROJECT_TODO.md`, same as `CH02_TODO.md` … `CH04_TODO.md` before it.

---

## How to read the effort annotations

Each step carries a line like:

> **Effort — you:** 10 min, mechanical · **me:** low · **attended:** no

- **you** — your wall-clock time, and whether it is mechanical (run a command, read a
  number) or judgement (you have to decide something).
- **me** — my context/token load, coarse **low / medium / high**. This is a *relative
  ranking, not a measurement.* I have no meter. Treat it as "which steps to be careful
  about," not as a budget in any real unit.
- **attended** — whether we need to be working at the same time. "no" means you can
  run it and hand me the result later, or I can run it while you do something else.

The two budgets are genuinely different and pull in opposite directions: the steps
that cost me most (READ synthesis, FIX) are the ones where handing you more work does
not help, and the steps that cost you most (the boot walk) cost me almost nothing.

---

## Ground rules carried into this chapter

1. **Scope is closed.** CH05 does CH05, plus `PROJECT_TODO.md` #62 and #67. Anything
   else that surfaces gets **filed, not fixed** (§Deferred below lists what is already
   ruled out and why). The guardrail from `BUILD_PLAN.md` §2 is that the *next*
   chapter should need data changes, not code changes — scope creep here is how a
   chapter degrades into a content grind.
2. **No local LLM this chapter** (decided 2026-09-02, reversing the earlier plan). We
   work through it together: you run the mechanical commands, I do synthesis and
   authoring, you make the calls and pull me in when stuck.
3. **Output goes to disk, not into chat.** Noisy commands (`make modern`, `phase5`)
   redirect to a log under `output/` — tell me the path and the exit code, and I read
   the tail or grep it. Short summaries (`chapter_manifest check`, `routing plan
   --dry-run`) are a screen or less; paste those directly.
4. **Five stop points, not ten.** Marked ⏸ below. Steps 1-4 run as one uninterrupted
   mechanical block because there is nothing to decide in them — they either succeed
   or fail loud. Failures interrupt regardless of the marks; how we handle a given
   failure gets decided when it happens, not pre-committed here.
5. **Every command below is copy-pasteable as written.** `$V` is
   `/home/b/repos/rpg2gba/.venv/bin/python`; set it once per shell:
   ```bash
   V=/home/b/repos/rpg2gba/.venv/bin/python
   ```
   Never set or export any `RPG2GBA_*` variable — `.env-paths` is already correct and
   a shell override silently redirects the build at a tree that cannot work
   (`CLAUDE.md` §3).

---

## Step 0 — prerequisites and branch

**Effort — you:** 5 min, mechanical · **me:** low · **attended:** no

Everything here is *in-between work* and belongs on `main` by the standing rule that
branches are for chapters only. The branch gets cut at the **end** of this step.

- [x] **D1-D4 verified as actually built** (2026-09-02). All four shipped; D1/D3 in
      commit `758abc5b`, D2 in `d3cddc5d`, D4 separately. `tests/test_chapter_coordinate_literals.py`
      20 pass, the D2 checker suite 85 pass, and `chapter_manifest check --chapter CH04`
      fires its two documented deferred-beat findings live rather than being dead code.
- [x] **`CH05_DECISIONS.md` D1/D3 sections corrected** (2026-09-02). Both still read
      "Built: … do not exist" long after the code landed; only D2 and D4 ever got a
      reconciling addendum. Fixed, because that doc is the one we consult mid-chapter.
- [x] **`PROJECT_TODO.md` #28 Cave half resolved, #62 part 1 marked done.** See §Deferred.
- [ ] **Cut the branch.**
      ```bash
      git switch -c ch05
      ```

**What good looks like:** `git branch --show-current` prints `ch05`, and `git status`
is clean because everything above was already committed to `main`.

---

## Step 1 — SELECT

**Effort — you:** 2 min, mechanical · **me:** low · **attended:** no

Not a judgement call. The chapter comes from the atlas chain in order, and CH05's
binding is already written: `reference/chapters.json` gives **maps 36 and 37**, act
A1, predecessor CH04, traversal `35 → 36 ↔ 37 → 40` confirmed by the warp graph.

The one real action is adding the maps to the build set:

- [ ] Add `36, 37` to `SLICE_MAP_IDS` in `src/rpg2gba/tileset_converter/map_set.py:34`,
      following the existing per-chapter comment convention above it.

Note map **19** is *also* named "Passage Cave" and is **not** ours — it belongs to
CH03, because the warp graph shows it connects only to and from Kevlar (31) and never
reaches Route 02 or Nowtoch. A naive reading of the name mis-assigns it. `chapters.json`
already records this; do not let it surprise you when grepping for the name.

**Why this step is first and separate:** `SLICE_MAP_IDS` is the single source of truth
that *both* the collision emitter and the NPC-passability gate read (`CLAUDE.md` §4.3).
Everything downstream keys off it, so getting it wrong makes steps 2-4 produce
confidently wrong output rather than failing.

---

## Step 2 — EVENTS

**Effort — you:** 5 min to run · **me:** medium (reading the unhandled queue) · **attended:** no

Run the deterministic transpiler over maps 36 and 37. Everything mechanical becomes
Poryscript; anything uninterpretable lands in an explicit unhandled queue.

```bash
$V -m rpg2gba.pipeline convert-map --map-id 036 > output/ch05-events-036.log 2>&1
echo "exit=$?"
$V -m rpg2gba.pipeline convert-map --map-id 037 > output/ch05-events-037.log 2>&1
echo "exit=$?"
```

**Good:** exit 0, and the unhandled queue is short and boring. **Bad:** a queue entry
naming a `pbXXX` script call we have never seen, or an unknown command code. That is
the transpiler failing *loud and bounded* by design — it is a work item, not a crash.

Hand me the two log paths and the exit codes; I read the queues, not the whole logs.

**Why it sits here:** it needs nothing but the deserialized map JSON, and everything
after it needs its output. It is also the step most likely to surface genuinely new
work, so it runs before you have invested effort in art or wiring.

---

## Step 3 — ART

**Effort — you:** 10-20 min, mostly waiting · **me:** low · **attended:** no

Quantize maps 36/37's real tilesets and sprites to GBA 4bpp. This is the step the
pathfinder slice deferred, which is exactly why that slice booted and was unplayable.
A chapter is not done until it is playable *with real art* (`CLAUDE.md` §9, §11).

Two specific risks for a cave, both worth checking rather than assuming:

- **Tileset budget.** A tileset has two hard 1024 caps — metatile ids and distinct
  8×8 tiles. `WALKER_OVERFLOW_MAP_IDS` (`map_set.py:64`) lists the maps that blow
  them; **36 and 37 are not on it**, so they should fit. If the budget guard fires
  anyway, that is a real finding and it stops the chapter.
- **Legibility in the dark.** Passage Cave runs with Flash darkness. Art that reads
  fine at full brightness can be unreadable through the flash overlay, and the boot
  walk is where you would find that out. Worth an eyeball at step 8 specifically.

**Good:** quantized output for both maps, no budget-guard failure. **Bad:** anything
that makes you reach for a hand-edit of the output — fix the converter instead
(`CLAUDE.md` §11).

---

## Step 4 — WIRE

**Effort — you:** 15-30 min, mostly waiting · **me:** low · **attended:** no

Map constants, layouts (collision + warp metatiles), object events, encounters,
connections. This is the heavy mechanical build.

```bash
$V -m rpg2gba.pipeline phase5 --maps slice > output/ch05-phase5.log 2>&1
echo "exit=$?"
```

Then generate the manifest that step 5 reads:

```bash
$V -m rpg2gba.chapter_manifest generate --chapter CH05
```

Two things to expect specifically here:

- **Encounters:** maps 36 and 37 carry only a `Cave` table (Tonemy / Barewl / Grozard /
  Dunsparce, Lv 4-6, densities 15 and 20). It folds into `land_mons`, and that is
  correct, not a compromise — see §Deferred #28. `wild_encounters.py:259-264` logs an
  `uranium_extra` drop at info level for maps that have one; for 36/37 there is
  nothing to drop.
- **Darkness:** `metadata_wiring._dark_map_for` already wires `dark_map` →
  `requires_flash`, and the engine handles the rest natively (`gMapHeader.cave`,
  `FLAG_SYS_USE_FLASH`, `SetDefaultFlashLevel` at `engine/src/overworld.c:1103`, the
  transitions in `engine/src/fldeff_flash.c`). **No new C.** If you find yourself
  writing engine code for cave darkness, stop — something else is wrong.

**Good:** exit 0, manifest written to `reference/manifests/CH05.manifest.json`.

---

## ⏸ STOP 1 — look at the manifest together

**Effort — you:** 15 min, judgement · **me:** medium · **attended:** yes

```bash
$V -m rpg2gba.chapter_manifest review --chapter CH05
```

We look at the generated rows before you spend an hour dispositioning them. What I am
looking for: does the row count and shape match what `05-passage-cave.md` predicts, do
the archetype classifications land where expected, and is anything present that the
spec does not mention. Cheap to catch here, expensive after step 5.

---

## Step 5 — READ

**Effort — you:** 1-2 hours, pure judgement · **me:** medium · **attended:** partly

**This is your step, and it is the highest-yield one in the chapter.** In CH04 the
equivalent read-through caught 4 missed beats and a wrong `cosmetic` rule definition,
and at that point it was still informal with no home in the loop. It has a home now:
`BUILD_PLAN.md:97` step 5, checklist at `reference/guides/read_through_checklist.md`.

**CH05 is the checklist's first real use.** Nothing in the repo shows it has been run
yet — CH04's run predated it. So treat the checklist itself as under test: if it asks
a question that does not fit a row, that is a finding about the checklist.

Work the checklist per row and record a disposition for each:

- Is the verdict answering the right question **for that row's `kind`** (page / seam /
  terrain), not merely mechanically legal?
- **Was any row on the page skipped?** A human's eye slides off a row that was visible
  the whole time. This is the failure the checklist exists for.
- A **verdict-definition** error found here is fixed as a *definition* and re-reviewed
  across every row of that kind — not patched on the one row where you noticed it.

Dispositions go in `reference/manifests/CH05.dispositions.json`. Expected shape from
the spec's B1-B11:

| Beat | What | Template |
|---|---|---|
| B1 | enter cave from Route 2 | `warp` (cave entrance) |
| B2 | Escape Rope pickup | `item_ball` |
| B3 | Manny (HIKER), event-sight | `trainer` |
| B4 | Great Ball pickup | `item_ball` |
| B5 | Keichi (BLACKBELT) | `trainer` |
| B6, B7 | TM76 / Sableyeite | **deferred** — `blocked:surf`, no live beat |
| B8 | warp 1F → 2F | `warp` |
| B9 | Nuñes (HIKER) | `trainer` |
| B10 | NPC gives Revive | **no template** — hand-written |
| B11 | exit to Nowtoch | `warp` (cave exit) |
| — | Map036 EV002 p1 arrival nudge | `arrival_nudge` |

Nine of ten live beats are templated. The templates are *helpers you call*, not a
generator — the rejection of a generator was deliberate
(`PLAYTEST_AUTHORING_IMPROVEMENT_V2.md:309-330`). Beat ordering, B10, and the
provenance prose are hand-written.

**B6/B7 must be authored as deferred beats**, in the `DEFERRED_BEATS` idiom CH02 and
CH04 use — not as live beats. TM76 and Sableyeite sit in a 30-tile room that opens
only into a water pocket disconnected from the walkable region: Map036 has 513 walkable
tiles in 7 connected components, 450 reachable on foot from the entrance, and that room
is not among them. Surf is granted at map 143 (Act 5) — the longest capability deferral
found in the corpus. This is a second, much longer arm on the stranded-revisit backlog
alongside the Rock Smash one.

## ⏸ STOP 2 — after your READ pass

You hand me the dispositions; I check them against the manifest and we reconcile
disagreements. Then:

```bash
$V -m rpg2gba.chapter_manifest check --chapter CH05
```

Expect a `route_model_unenforced` warning at this point — there is no route plan on
disk yet. **Do not read that warning as a pass.** It means the rule could not run.
Step 6 is what silences it.

---

## Step 6 — ROUTE

**Effort — you:** 20 min, judgement · **me:** medium · **attended:** yes

**CH05 is the first chapter in the project to carry a route plan at all.** `PROJECT_TODO.md`
#67: CH01-CH03 cannot be solved (their pre-slice-2 manifests are refused by
`load_manifest`), and CH04 solves but its plan disagrees with its registered order by
18 tiles of pure walk distance — suboptimal, not wrong, and not worth turning a closed
chapter red over. So `RULE_ROUTE_ORDER` has been unenforced for every chapter gated to
date, and slice 3 is validated **forward, from here**.

```bash
$V -m rpg2gba.routing plan --chapter CH05 --module ch05 --dry-run
```

Read the summary. **Any `CROSSING` line is a beat that will fire the wrong event** —
fix it here, not after the walk goes wrong.

## ⏸ STOP 3 — you approve the ORDER

This is a real gate, not a formality (`BUILD_PLAN.md` §2 step 6). You approve the
**order**, not just the beat set: registration order *is* playthrough order, and the
plan is the thing you are signing off. Solving after the beats are written inverts
that — the solver then just grades an order nobody can change without reopening the
chapter, which is exactly the state CH01-CH04 are in.

Then write it and register the beats in that order:

```bash
$V -m rpg2gba.routing plan --chapter CH05 --module ch05
```

- [ ] Author `src/rpg2gba/playtest/chapters/ch05.py`, beat groups in the approved order.
- [ ] **No bare coordinate literals.** CH05 is the first chapter under the D1 ban and
      the lint is zero-tolerance for CH05+ (the CH01-CH04 debt has a ratchet budget).
      Use the resolvers in `src/rpg2gba/playtest/cells.py` — `event_cell`, `approach_to`,
      `warp_cell`, `arrival_cell`, `entry_cell` — and the `raw_cell(x, y, why="...")`
      escape hatch only with a real reason, counted per chapter. Three CH04 failures
      traced to unverified coordinate literals; that is what the ban is for.
- [ ] Re-run `chapter_manifest check --chapter CH05`. `route_model_unenforced` should
      now be gone and `RULE_ROUTE_ORDER` enforcing.

---

## Step 7 — BUILD

**Effort — you:** 10-15 min, mostly waiting · **me:** low · **attended:** no

```bash
$V -m rpg2gba.pipeline phase5 --maps slice > output/ch05-build.log 2>&1
make -C engine -j$(nproc) modern > output/ch05-make.log 2>&1
echo "exit=$?"
```

`make modern` must exit 0. Then the headless suite, which is the cheap filter before
you spend your own time walking:

```bash
$V -m rpg2gba.playtest run --chapter CH05 --engine engine
```

## ⏸ STOP 4 — before the boot walk

We look at the headless results together. Anything red gets fixed before you pick up a
device — the boot walk is the expensive resource in this loop and it should be spent on
things only a human can see.

---

## Step 8 — BOOT (the §9 gate)

**Effort — you:** 45-90 min, judgement, hands-on · **me:** low · **attended:** no

Per your standing rule, the walk starts at **the previous chapter's end** — seed from
CH04's blob rather than replaying from the beginning:

```bash
$V -m rpg2gba.playtest seeds --chapter CH04
$V -m rpg2gba.playtest walk --chapter CH04 --at-end --engine engine
```

Then deliver it to the phone:

```bash
tailscale file cp <the .gba> iphone182:
```

## ⏸ STOP 5 — the gate itself

A chapter is not done until it **boots in mGBA and the section is genuinely playable —
warps fire, NPCs sane, layout legible, art included.** You walk it. Specific things to
look at this chapter, beyond the beat list:

- **Does the cave read in the dark?** Step 3's legibility risk, only visible here.
- **The arrival nudge on Map036 EV002.** The `arrival_nudge` template has never run in
  a ROM — CH04's `beat:B8` was authored and deliberately never registered, because its
  sibling warp page was out of slice. This is its **first live exercise**, against the
  corpus's second-largest idiom (324 instances across 73 maps, behind only the
  door/warp event at 996). Of the four templates, this is the one to bet on
  misbehaving. Two failure shapes: a **freeze on arrival** (the move route hangs, field
  never unlocks) or a **warp loop** (the guard flag never sets, the autorun refires
  while you are still on the warp tile). The second is not hypothetical — `WARP_FACING_HANDOFF.md`
  and commit `b7c5b8d7` document a boot-tested case of a down-stairs warp re-firing
  `TryArrowWarp` and bouncing the player back upstairs.

**A green CH05 gate is not evidence** that slice 2, the capability model, or the
mart/Center/PC templates are correct. CH05 exercises zero seam rows, zero populated
`requires[]`, zero mart/Center/PC instances, and its only `blocked:` rows are
terrain-derived Surf rather than switch/variable-derived — the least representative
possible confirmation. Their real validation is the retroactive re-derivation of
CH01-CH04, which is post-CH05 work (§Deferred).

---

## Step 9 — FIX

**Effort — you:** varies · **me:** high · **attended:** yes

Cluster any systematic defect and **fix the converter, then re-run.** Never hand-edit
generated output — it gets regenerated (`CLAUDE.md` §11).

The `/debug` workflow drives this: clarify the symptom → localize the layer → fix →
full verified rebuild with hash evidence → taildrop for retest.

---

## Step 10 — RECORD

**Effort — you:** 5 min · **me:** low · **attended:** no

- [ ] `MEMORY.md` → Current Phase and Decisions Made.
- [ ] `reference/chapters.json` → CH05 `status` to gated, with the gate note (date,
      suite result, ROM hash) in the established format.
- [ ] Retire this file to `reference/archive/`, migrating carryovers to `PROJECT_TODO.md`.
- [ ] Commit as one logical unit; merge `ch05`.

---

## Deferred — filed, not fixed

Recorded so they are not re-litigated mid-chapter.

- **#28 Cave encounters — RESOLVED 2026-09-02, no work owed.** Emerald has no cave
  encounter concept: `struct WildEncounterTypes` has five pools and none is a cave, and
  all 11 `gMapHeader.cave` / `MAP_TYPE_UNDERGROUND` sites are lighting, transitions,
  battle backdrop, DexNav cosmetics, Dusk Ball flavor and the region map — never table
  or rate selection. On the data side, 23 Uranium maps carry a `Cave` slot and **zero**
  of them also carry a populated `Land`-family table, so the fold into `land_mons` is
  lossless corpus-wide. The **time-of-day** half of #28 stays open and is out of CH05's
  scope: `OW_TIME_OF_DAY_ENCOUNTERS` is one flag away, but `_LAND_SOURCES` ranks plain
  `Land` above the time-split tables, so flipping it without auditing that precedence
  changes behavior on unwalked maps.
- **#57 — 12 unmodelled walked legs.** Deferred to **CH07 at the earliest** (operator
  decision, 2026-09-02).
- **#65 — CH01-CH03 manifests no longer load.** Immediately **after** CH05.
- **#62 parts 3-4 — corpus re-disposition.** Folded into #65, so also **after** CH05.
  This is a deliberate deviation: the recorded decision said "during CH05's build," and
  we are moving it out, because corpus-wide re-derivation mid-chapter is precisely the
  scope creep the loop guardrail exists to prevent. **The ordering safeguard moves with
  it and must not be lost:** *freeze the expected answers, derive, diff, then write* —
  never derive-and-write in one pass, or a regression in the derivation logic reads as
  a correct re-disposition.
- **#62 part 1 — DONE**, by D4 on 2026-09-01, two days after the item was filed. The
  `arrival_nudge` template and its classifier both exist. Its untested-in-ROM residue is
  live at step 8, not here.
- **#67 — route plans.** In scope; it *is* step 6.

---

## Log

Append findings, surprises and decisions here as they happen, newest last.

- **2026-09-02** — Prerequisite pass run before the branch. D1-D4 all confirmed built
  and tested. Found `CH05_DECISIONS.md` D1/D3 sections stale ("Built: … do not exist"
  about shipped code, never reconciled the way D2/D4 were) and corrected them. Found
  `PROJECT_TODO.md` #62 part 1 stale in the same way. #28's Cave half investigated and
  closed. Local-LLM pre-fill dropped from the plan.
