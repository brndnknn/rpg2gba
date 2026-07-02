# Grill session: the missing spine (2026-07-02)

**What this is:** decision record from the grill-me session on critique target #1
(`reference/critique_2026-07-01.md`): the deterministic transpiler + fork capability
index — "next tasks #1/#2 since 2026-06-18, zero code." Ten decisions, resolved in
dependency order. Slice command-census evidence in the appendix.

---

## Decisions

**D1 — Walker-first was drift.** No deliberate resequencing ever happened; the walker
absorbed the sessions without a decision. Acknowledged, not defended. (Consequence:
the spine starts on merit, below, not on plan seniority.)

**D2 — Spine anchor = finish the pathfinder slice.** The spine is built *in service
of* making slice 1 (Maps 49/48/32) genuinely done per §9: capability index →
`transpile_page` → oracle harvest → re-transpile the slice's events → NPC gfx map →
playable boot gate. Walker Checkpoint 2 proceeds in parallel as a user-owned
validation track; boot findings feed the graphics/warp converters, orthogonal to the
events spine.

**D3 — Capability index reads git-tracked pristine `engine/` content**, never the
working tree. The pipeline injects Uranium symbols into generated headers
(`map_groups.h` defining `MAP_MOKI_TOWN` is the live example — it's why 2 tests fail),
so a working-tree index can't distinguish upstream vocabulary from our own prior
output. The forward gate resolves emissions against **index ∪ flag registry ∪
map-constant registry ∪ PBS outputs** — pristine fork vocabulary in the index,
Uranium-minted namespaces from their own single sources of truth.

**D4 — Forward gate enforces at BOTH conversion time and staging.** Conversion-time
check right after poryscript-compile (error carries map/event context). Staging-time
lint at the single choke point before `make`, covering *every* producer (transpiler,
LLM tail, hand conversions, memo reuse, oracle files). A gate failure is **our bug —
abort loud, never queued**; the unhandled queue is for input we can't read, not
output we got wrong.

**D5 — Transpiler = new thin driver; orchestrator untouched.** `transpile_page` + a
control-flow tree parser in a new module beside `deterministic.py`, driven by a thin
"transpile the corpus, write .pory per map" loop with **no checkpoints/memo** — a
deterministic pass re-runs in seconds, so full re-runs replace resumability. Reuse
only the `unhandled.jsonl` queue format and cluster-aware triage. `orchestrator.py` +
`backends/` stay as the hand-invoked LLM tail tool. **BUILD_PLAN §8's "repurpose the
checkpoint/memo machinery" line is corrected as stale.**

**D6 — Oracle = one-time harvest, then retire.** Normalized-text diff (not bytes)
against the frozen-Opus `.pory` (maps 001–007 + CommonEvents) once per transpiler
milestone; every divergence **cluster** gets a disposition — transpiler bug (fix) or
Opus error (note, discard). Permanent regression protection comes from goldens minted
from *reviewed transpiler output*, never from Opus text (locking Opus phrasing would
invert authority and fight the idiom-collapse layer). After the harvest the oracle
retires to the archive.
**Hard prerequisite discovered:** the oracle lives only in gitignored
`output/uranium-build/scripts/` — `prep_bulk_run.py --yes` or a `--clean` destroys
it. **Archive it (e.g. `reference/archive/oracle_pory/`) before any spine work.**
(Committing it is consistent with `reference/script_texts.json` already being
tracked.)

**D7 — 209 policy for v1 = deterministic tier, not stub-all.** Emit
`applymovement`/`waitmovement` for directly-mappable routes (the ~24% raw
`MOVEMENT_ACTION_*` tier plus whichever SOFT-C rules the slice's own routes need),
queue the rest; hand-resolve only queue entries that block slice progression. Any
route still stubbed must **neutralize its paired 210 wait** or the script hangs.
**This deliberately overturns BUILD_PLAN §5's "first cut stubs all of 209"** — that
sequencing predates the slice anchor, and the census (appendix) shows 91 move routes
with 80 paired waits concentrated in the slice's opening cutscenes: stub-all would
reproduce the exact "booted but unplayable" failure the slice model exists to prevent.

**D8 — Queue residue: build agent first, human gate.** Residue with ≥2 occurrences or
a plausible native analog → build agent extends the idiom library / condition
interpreter, with a fork-search evidence entry per the reverse gate; the user reviews
the mapping (a CLAUDE.md §10 fidelity call). True one-off story logic → user by hand
or the LLM tail tool at the user's discretion. At slice-1 scale the LLM tool is
likely not needed at all (13 distinct 355 heads; `pbCallBub` 65× **STRIP stands** with
the Phase-8 emote revisit note on file).

**D9 — Slice 1 assembles via `assemble_pathfinder` as-is.** The transpiler writes
`.pory` where `stage_slice_scripts` already expects them; zero new plumbing before
the boot gate. The dual-path unification (phase5 growing a full-fidelity scripts
mode; assemble_pathfinder retiring) becomes its own explicit post-slice work unit,
informed by the boot. Duplication carried a little longer, eyes open.

**D10 — Done bar (six points), slice 1 stays 3 maps:**
1. Capability index built from pristine git content.
2. Forward gate live at conversion + staging.
3. Oracle harvest complete — every divergence cluster dispositioned; oracle archived,
   then retired.
4. Slice re-transpiled with the queue **read to completion** (every entry: idiom /
   native / STRIP / hand).
5. NPC gfx map done (no ninja-boy crowd; graphic-less events invisible+non-blocking).
6. `make modern` exit 0 + the user walks the boot in mGBA: intro cutscenes play,
   warps fire, dialogue readable.

Starter/lab and Route 1 live in the neighbor maps (50/64/65/172, 33) → **slice 2 by
construction**, which makes slice 2 the first genuine test of the "slice 2 must need
data changes, not code changes" guardrail. The Phase 0 criterion "player can leave
the starting town" is certified at slice 2, not slice 1.

---

## Implied build order

0. **Prereq:** archive the frozen-Opus oracle out of `output/` (D6).
1. Capability index (pristine-content parser, consolidating `load_fork_constants` /
   `load_multi_constants` / `load_charmap_chars`) + forward gate at both points (D3, D4).
2. `transpile_page`: control-flow tree (111/411/412, 112/113, labels), condition
   interpreter (`s:`/code-111 script conditions), 209 deterministic tier,
   classifier re-homing as idiom-collapse layer (D5, D7).
3. Oracle harvest + cluster dispositions (D6).
4. Slice re-transpile + queue drain (D8).
5. NPC gfx map (`character_name` → `OBJ_EVENT_GFX_*`, skip/invisible for
   graphic-less).
6. Assemble via `assemble_pathfinder`, boot, user walks the gate (D9, D10).

---

## Appendix: slice command census (measured 2026-07-02)

Maps 49/48/32 = 87 events, 137 pages, ~1,594 commands.

| Code | Meaning | Map049 | Map048 | Map032 | Total |
|---|---|---|---|---|---|
| 209 | move route | 15 | 1 | 75 | **91** |
| 210 | wait move completion | 9 | 0 | 71 | **80** |
| 509 | embedded route steps | 91 | 6 | 323 | 420 |
| 111 | conditional branch | 22 | 3 | 38 | 63 |
| 112/113 | loop / break | 0 | 0 | 6+6 | 12 |
| 102 | choices | 0 | 0 | 0 | **0** |
| 355/655 | script call | 29 | 4 | 76 | 109 |
| 121/122 | switch / var | 15 | 4 | 3 | 22 |
| 123 | self-switch | 2 | 2 | 9 | 13 |
| 201 | transfer (warp) | 5 | 1 | 9 | 15 |

**355 heads (102 blocks → 13 distinct):** `pbCallBub` 65 (STRIP), `setTempSwitchOn` 8
(deterministic mint), `pbEraseThisEvent` 6, `Kernel.pbRockSmashRandomEncounter` 6
(native), `pbSetSelfSwitch` 5 (deterministic mint), `pbCaveEntrance` 3 (native),
`displayNinjaLetter` 2 (novel), `pbShowMap` 2 (native), singles: `$PokemonGlobal`
runningShoes, `pbTrainerPC` (native), `list`, `$Trainer`, `pbPhoneRegisterNPC`.

**111 script-condition heads (32):** `$game_player` 10, `get_character` 8, `Kernel` 7,
`pbHasSpecies` 3, `isRockSmashSoftlocked` 3, one complex `pbGet(1)` expression.
