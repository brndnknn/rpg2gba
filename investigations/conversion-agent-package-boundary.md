# Investigation: `conversion_agent/` — a live spine under a retired regime's name

**Status:** **closed 2026-09-08** — folded into `investigations/repo-reorientation-strategy.md` (its D7). See the closing note at the end.
**Started:** 2026-09-07   **Last updated:** 2026-09-07
**Question:** Does `src/rpg2gba/conversion_agent/` still describe what it contains, and if not, what should the package boundary be?
**Expected artifact:** undecided — likely a plan (a scoped, pure-motion refactor commit)

**Parent:** `investigations/repo-audit-dead-code-stale-docs.md` (CLOSED). That audit's
finding 28 established there is **no orphaned module** anywhere in `src/rpg2gba/` — every
file is imported from somewhere. This investigation starts from that result and asks the
question the audit did not: the code is alive, but is the *label* on it true?

## Summary

`src/rpg2gba/conversion_agent/` is the home of the **live deterministic transpiler spine**
— the thing `CLAUDE.md` §4.1 spends a whole section insisting is *not* the LLM. It also
holds the flag registry, which §4.3 names the single source of truth for `FLAG_*`/`VAR_*`.
Roughly four of its ~17 members actually belong to the LLM regime the directory is named
for, and per Q11 of the parent audit that regime is a hand-invoked tail tool, not a spine.

The cost is not runtime — nothing is broken — it is that a directory name is read as a
status claim. It already produced one wrong conclusion from the operator ("why does this
still exist at all?"), and it is exactly the class of self-description error the parent audit
exists to remove: an artifact asserting something about the project that is no longer true,
sitting in a place agents are told to trust.

## Findings

1. **The live spine is inside `conversion_agent/`.** Verified first-hand by grep for
   importers: `src/rpg2gba/pipeline.py:66,71` (the `transpile-events` command added by the
   parent audit's Stage E), `src/rpg2gba/tileset_converter/metadata_wiring.py:53,60,928`,
   `scripts/stage_slice_scripts.py:40-41`. The modules reached this way are
   `transpile_driver.py`, `transpiler.py`, `flag_registry.py`, `fork_index.py`, and
   `orchestrator.load_map_event_strips`.

2. **Package contents split cleanly into two regimes.** Listing of
   `src/rpg2gba/conversion_agent/`: `transpiler.py`, `deterministic.py`,
   `transpile_driver.py`, `poryscript.py`, `flag_registry.py`, `fork_index.py`,
   `triage.py`, `lane.py`, `queue_evidence.py`, `hand_overrides.py` — current spine and
   its support. `orchestrator.py`, `backends/`, `prompt_builder.py`, `prompts/`,
   `hand_conversions/`, `run_report.py` — the LLM regime, of which per the parent audit
   Q11 `backends/` + `orchestrator.py` are **retained by explicit policy**
   (`BUILD_PLAN.md:26`) as the hand-invoked tail tool, and `run_report.py` is marked SPENT.
   *Confidence: high on the membership, medium on the exact boundary for `triage.py`,
   `lane.py`, `hand_overrides.py`, `queue_evidence.py` — these were not traced this session.*

3. **`orchestrator.py` straddles the boundary.** `metadata_wiring.py:60` imports
   `load_map_event_strips` from it — a `strip_list.json` reader (`CLAUDE.md` §4.3 source of
   truth) — while `orchestrator.convert_all` is the retired bulk spine (parent finding 24)
   whose CLI entry now refuses. So the module is simultaneously live-utility and
   retired-driver. Any split has to decide where that function goes.

4. **The parent audit asked the wrong question about this package, and said so.** Finding
   28: "No whole orphaned module exists in `src/rpg2gba/` … The dead code here is *retired
   call paths inside live files*, not abandoned modules." Correct, and it is why a
   liveness-based sweep could never have flagged the name.

## Hypotheses / unverified

- **H1. A rename is mechanically cheap.** Estimated ~25 import sites across `src/`,
  `scripts/`, `tests/`, plus doc path references (`CLAUDE.md` §3's tree, §4.3's table,
  `BUILD_PLAN.md:26`, `reference/guides/how_to_use_agents.md`). Not counted precisely —
  do that before committing to a plan. *Confirm by:* grep for `conversion_agent` across
  the repo and count distinct files.
- **H2. `triage.py`, `lane.py`, `queue_evidence.py`, `hand_overrides.py` belong with the
  spine.** They read as transpiler-adjacent (unhandled-queue and idiom machinery) rather
  than LLM machinery, but no importer trace was run. *Confirm by:* tracing importers of
  each, the way finding 1 traced the spine.
- **H3. Nothing outside this repo imports the package path.** Nothing should — it is not a
  published package — but `pyproject.toml`'s entry points and any `.claude/skills/*`
  references are worth checking before motion. *Confirm by:* grep `pyproject.toml` and
  `.claude/`.

## Decisions

- **2026-09-07 — split from the parent audit into its own doc.** Q: append to
  `repo-audit-dead-code-stale-docs.md` or start fresh? A: fresh, referencing the parent.
  *Effect:* the parent returns to CLOSED with its original scope intact; this doc owns the
  question. Rationale: the parent is a closed 105 KB artifact whose plan is fully executed;
  reopening it for a live question recreates the multi-job-document problem it was written
  to fix.

## Open questions

### Q1. Rename the package, split it, or leave it and document?
Three shapes. (a) **Leave it**, add a header comment to `__init__.py` saying the name is
historical — zero risk, but the misleading name stays in every import line, every file
path an agent reads, and `CLAUDE.md`'s tree. (b) **Flat rename** to something like
`events/` — fixes the label, ~25 import sites, one reviewable commit. (c) **Split**: the
spine to `events/`, the retired-regime members (`orchestrator.py`, `backends/`,
`prompt_builder.py`, `prompts/`, `hand_conversions/`) to `llm_tail/` — encodes `CLAUDE.md`
§4.1's spine-vs-tail distinction in the directory tree itself, but has to resolve finding
3's straddle.

**Recommendation:** (c), as its own commit containing **no change other than motion**, so
the diff is reviewable as pure renames. §4.1 already spends a section drawing this exact
line in prose; putting it in the filesystem means it cannot be misread again. Resolve
finding 3 by moving `load_map_event_strips` into the spine package (it is a strip-list
reader, not orchestration) and leaving the rest of `orchestrator.py` in `llm_tail/`.
**Blocked on:** —
**Answer:**

### Q2. If we move, does `CLAUDE.md` §4.3's source-of-truth table need re-anchoring?
`flag_registry.py` is named in §4.3 by path, as is the `prompts/` layout in §3's tree and
§5's "conversion agent prompts" convention. A move invalidates all three. The parent audit's
Q6 answer says fix the text in the same change, never file it.

**Recommendation:** Yes — same commit, per Q6. Add a one-line dated note in `MEMORY.md`
Decisions recording the old path, since sub-agents and skills carry stale paths in their
briefs for a while and a grep for the old name should land on an explanation.
**Blocked on:** Q1
**Answer:**

### Q3. Is the `prompts/` tree still worth keeping in-tree at all?
`CLAUDE.md` §5 treats the conversion agent's prompts as source code and §7 records they are
"no longer frozen" since the bulk run retired. Q11 of the parent found no event has been
punted to the LLM since the pivot. So the prompt corpus is maintained-in-principle,
unexercised-in-fact.

**Recommendation:** Keep, unchanged — `convert-map` is still a supported path and CLAUDE.md
§4.1 deliberately preserves the tail tool. This is a note so the next reader does not
mistake "unexercised" for "dead"; the parent's finding 27 is the cautionary tale for
exactly that inference.
**Blocked on:** Q1
**Answer:**

## Next steps

1. Answer Q1 — everything else is downstream of the shape.
2. Before any motion: run H1's precise import-site count and H2's importer traces for the
   four unclassified modules. Neither is more than a few greps; both change the size of the
   commit.
3. If Q1 = (b) or (c): execute as a pure-motion commit, then a second commit for the doc
   text (Q2). Run `pytest` before and after and compare against the known baseline —
   **2984 passed, 16 skipped, 2 failed**, the two reds being
   `test_ground_item_differential_vs_frozen_opus` and
   `test_pokemart_differential_vs_frozen_opus`, which are pre-existing and depend on a
   gitignored oracle under `output/`.

## Ground covered

- **Importers of the package — traced** (finding 1). `pipeline.py`, `metadata_wiring.py`,
  `stage_slice_scripts.py`. Test-side importers were *not* enumerated.
- **Liveness of the modules — already settled by the parent audit**, findings 24-28 and 44,
  plus its second-pass sweep of `transpiler.py`/`deterministic.py` which found **zero
  confirmed-dead lines**. Do not re-run a dead-code sweep here; it has been done twice.

---

## CLOSED 2026-09-08 — folded into `investigations/repo-reorientation-strategy.md`

The operator chose that doc's **option C**: sort the tree by the project's generalization goal
rather than by liveness. Its **step 4** splits the codebase into three buckets — **pipeline**
(game-agnostic conversion code) / **game pack** (per-game data and content) / **instrumentation**
(tools that show what the pipeline did).

**That split answers this doc's central question by construction, and answers it better than a
rename would.** This investigation was choosing between renaming `conversion_agent/` and
redrawing its boundary; the three-bucket sort redraws the boundary as a side effect of work
being done anyway, and it dissolves the premise — the package stops being one directory whose
*name* has to describe a mixed population. Its ~4 LLM-regime members and its deterministic
spine land in different buckets on evidence (import-trace or git-recency), which is the
standard `repo-reorientation-strategy.md` finding 18 established.

Nothing here is lost: findings 1+ remain the evidence base for where each member goes when
step 4 runs.
