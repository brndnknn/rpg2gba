# Investigation: `scripts/` — 90 files, 3 liveness markers

**Status:** blocked-on-answers
**Started:** 2026-09-07   **Last updated:** 2026-09-07 (H2 hazard sweep run — findings 6-9; H3 cleared)
**Question:** How should `scripts/` distinguish its ~20 load-bearing utilities from its ~75 spent one-offs, so that reading the directory stops producing wrong conclusions?
**Expected artifact:** undecided — likely a plan (archive move + a small number of deletions)

**Parent:** `investigations/repo-audit-dead-code-stale-docs.md` (CLOSED). Its finding 47 is
the full load-bearing/spent inventory and is the input to this investigation — **do not
re-derive it.** Its Decisions → "scripts/ policy" entry ruled that spent one-offs are
expected, not a defect, and that the inventory was "not a deletion list." That ruling is
what this doc revisits, because it predates the operator reading the directory and calling
it junk.

## Summary

`scripts/` holds 90 entries. **Three of them contain any liveness marker** — the `SPENT`
headers added to `run_bulk.py`, `prep_bulk_run.py`, `run_stats.py` during the parent
audit's Stage B, and those three got headers only because Q11 asked about them by name.
Every other spent one-off is indistinguishable by inspection from a load-bearing pipeline
step. The one place the distinction exists is finding 47 of the parent doc, and nothing in
the repo points at it.

Two consequences, one cosmetic and one not. The cosmetic one is the operator's complaint:
the directory reads as junk because ~75 of its files *are* spent and nothing says so. The
non-cosmetic one is finding 3 below — the parent audit deleted its harmful scripts from a
hand-enumerated list, and at least one file matching every one of its own deletion criteria
survived because it was not on that list.

**Update 2026-09-07 — H2's sweep is run (findings 6-9), and it found a second confirmed
hazard.** `assembly_smoke.py` (6) runs `git worktree add` and `git branch -D` against
*this repo*, because the `fork_path` it resolves from `RPG2GBA_POKEEMERALD` is now
`engine/`, which has no `.git` of its own — the docstring promise that it "NEVER touches
the fork's main checkout" was silently invalidated by the vendoring cutover. `run_human.py`
(7) writes live flag-registry state for the retired bulk run and carries no marker. The
remaining four axes came back clean (8) and three of the parent doc's five unreviewed
destructive scripts are false positives (9), so the harmful set is exactly three files:
`calibrate_map002.sh`, `assembly_smoke.py`, `run_human.py`. **Note the mechanism in
finding 6 — it is a new class:** not a script that rotted, but a script that was correct
when written and was made dangerous by an environment change (the engine cutover) that
never revisited its callers. A liveness marker would not have caught it.

## Findings

1. **90 entries, 3 marked.** Verified: `ls scripts | wc -l` → 90; `grep -rl "SPENT"
   scripts | wc -l` → 3 (`run_bulk.py`, `prep_bulk_run.py`, `run_stats.py`). The fourth
   file marked spent by the parent audit, `conversion_agent/run_report.py`, is outside
   `scripts/`.

2. **The inventory exists but is unreachable from the repo.** Parent finding 47 classifies
   ~20 load-bearing (each with an import or live-doc referrer as evidence), ~75 spent in
   named clusters (Phase-0 recon; ~17 Phase-4 one-offs; ~28 Phase-5 graphics explorers,
   the largest cluster; ~6 pathfinder previews; the closed difficulty-analysis pair), 2
   uncertain, plus 6 orphaned `.pyc` caches whose source is gone (parent finding 48).
   Nothing in `scripts/`, `CLAUDE.md`, or `reference/` links to it.

3. **CONFIRMED HAZARD — `scripts/calibrate_map002.sh` meets every criterion the parent
   audit used to delete `run_slice.py` and `regen_outputs.py`, and survived.** Verified
   first-hand. It is the only file in `scripts/` that is **both** budget-spending and
   destructive to live pipeline state: `:39` runs `convert-map --map-id 2 --model
   claude-opus-4-8` — the retired frozen-Opus regime — and `:25-35` overwrite
   `output/uranium-build/flag_state.json` from a baseline snapshot, then `rm -f` the memo
   manifest, `unhandled.jsonl`, and the `Map100`/`Map115` checkpoints. No in-file warning.
   Last touched 2026-06-04. Its only referrers are archive-only:
   `reference/archive/PHASE4_DETERMINISTIC_PLAN.md:80,726` and a dated past-tense entry at
   `reference/memory-archive.md:227`. **Why it survived:** the parent audit's Q12
   enumerated the harmful set by hand — the same failure shape as the vendor doc's hand
   inventory that was its own headline finding (parent finding 42).

4. **Two lower-risk neighbours, for calibration.** `scripts/convert_one_event.py` also
   spends budget on the frozen-Opus path (`--model claude-opus-4-8`) but sandboxes to a
   throwaway temp `out_dir` and requires `--yes`; its docstring is explicit that it never
   mutates live state. Risk is budget only, not corruption. `scripts/run_bulk.py` is
   budget-spending but now carries its `SPENT` header. Destructive-but-not-budget:
   `prep_bulk_run.py`, `route_movement_diff.py`, `map_viewer_common.py`,
   `assembly_smoke.py`, `fetch_libmgba.py` — all use `rm`/`rmtree`/`unlink` on
   scratch or fetched paths; none reviewed in detail this session.

5. **`scripts/alpha_rule_explainer.py` is the representative spent file.** Cited by the
   operator as an example. It is one of the ~28 Phase-5 graphics explorers (git-dated
   2026-06-21); its results are folded into
   `reference/guides/graphics_conversion_notes.md:224`, which names it and
   `hero_room_palette.py` as by-eye explainers produced for the user. Correctly retained by
   the parent audit's policy, and correctly unreadable as such from the file itself.

6. **CONFIRMED HAZARD (new, 2026-09-07 sweep) — `scripts/assembly_smoke.py` runs
   `git worktree add` / `git branch -D` against *this repo*, believing it is a separate
   fork clone.** Verified first-hand. `:763` resolves `fork_path` from
   `RPG2GBA_POKEEMERALD`, which since the vendoring cutover is `engine/` — and `engine/`
   has **no `.git`** (`ls -d engine/.git` → not found; `git -C engine rev-parse
   --show-toplevel` → `/home/b/repos/rpg2gba`). So `:433`'s `git -C <fork> worktree add -b
   rpg2gba-smoke-branch output/smoke-worktree` creates a worktree of **rpg2gba** on a new
   branch off the current HEAD, and `:450`'s `git -C <fork> branch -D rpg2gba-smoke-branch`
   deletes a branch in the operator's own repo. `_create_or_reuse_worktree`'s docstring
   still promises "NEVER touches the fork's main checkout working tree" — a guarantee that
   became void when the fork became this repo. Everything downstream then writes into
   `output/smoke-worktree/include/constants/…` and `data/event_scripts.s` (`:512-606`),
   paths that do not exist in an rpg2gba checkout, and `cmd_build` (`:634`) runs
   `make -j$(nproc) modern` there — a multi-minute run that `CLAUDE.md` §10 says to ask
   about first. **Referrers are archive-only:** `reference/archive/FABLES_IMPLEMENTATION.md:71`,
   `reference/archive/FABLES_DECISIONS.md:360,364`, `reference/findings/critique_2026-07-01.md:179`.
   Same shape as finding 3 — spent, unmarked, and silently miswired by an environment
   change made long after it was written.

7. **`scripts/run_human.py` writes live flag-registry state and belongs to the retired
   bulk-run regime, with no marker.** `:101` opens the real `_phase4_registry(out_dir,
   clean=False)` and `:130` calls `registry.save(orchestrator.registry_state_path)` against
   the shared `output/uranium-build/` tree — the one file `CLAUDE.md` §6 forbids hand-editing
   mid-run. Its stated purpose (`:1-11`) is seeding the memo "so when `run_bulk.py` (Opus)
   later sweeps the corpus those events are free memo hits" — i.e. the 199-map bulk run
   retired 2026-06-18, whose driver already carries a `SPENT` header. Zero budget risk
   (it is the hand-conversion path), so this is a marking problem, not a deletion one.
   Sibling `scripts/run_tutor.py` is the safe one: its docstring is explicit that nothing is
   written and no usage is spent — verified, no action.

8. **NEGATIVE RESULT — the other H2 axes came back clean.** (a) *Writes into `engine/`:*
   the only script that writes there is `assemble_pathfinder.py`, which is load-bearing
   (`README.md:87`, `BUILD_PLAN.md:40`, three test modules import it) and gates every
   `fork/` write behind `--dry-run` (`:184-213`). (b) *Git-mutating scripts:* a repo-wide
   grep for `git add|commit|push|checkout|reset|clean` across `scripts/` returns **nothing**
   outside finding 6's worktree calls. (c) *Default-on `--write`/`--apply` flags:* none —
   `stage_slice_scripts.py:410` defaults to dry-run, `prep_bulk_run.py:35` and
   `convert_one_event.py:68` gate on `--yes`. (d) *Broader budget sweep* (`anthropic`,
   `claude_code`, `ollama`, `--model`, `convert_all`) adds no script to the parent doc's
   three; `assembly_smoke.py` and `assemble_pathfinder.py` matched only on comments/imports.

9. **Three of the parent doc's five unreviewed destructive scripts are false positives.**
   `route_movement_diff.py:232` rmtree's a `tempfile.mkdtemp()` dir (`:144`) and carries a
   comment at `:142` stating registry.save never touches the shared tree.
   `map_viewer_common.py` has **no** destructive call at all — the grep hit was the phrase
   `rm -rf output/` inside a docstring at `:232`. `fetch_libmgba.py:32` rmtree's only
   `<venv>/site-packages/mgba` behind an explicit refusal-to-run-outside-a-venv guard
   (`:25`). `prep_bulk_run.py:68-78` is genuinely destructive but already `SPENT`-marked and
   `--yes`-gated. Net: the destructive list narrows to finding 3, finding 6 and finding 7.

## Hypotheses / unverified

- **H1. Moving spent scripts to `scripts/archive/` breaks nothing.** Parent finding 47
  lists ~20 load-bearing scripts with their referrers, so the blast radius should be zero
  — but referrers include *doc instructions* and *skill files*, not just imports.
  *Confirm by:* for each script proposed to move, grep its basename repo-wide including
  `.claude/` and `reference/`, and treat any live (non-archive, non-dated) hit as a block.
- **~~H2.~~ CONFIRMED and closed 2026-09-07 — there was one more finding-3-class hazard,
  plus one marking gap.** Swept all four remaining axes (writes into `engine/`,
  git-mutating commands, default-on `--write`/`--apply`, broadened budget patterns) and
  re-reviewed the five unreviewed destructive scripts. Result: findings 6 (`assembly_smoke.py`,
  confirmed hazard), 7 (`run_human.py`, unmarked live-state writer), 8 (the axes are
  otherwise clean), 9 (three false positives cleared). **New sub-hypothesis it raises —
  H4** below.
- **~~H3.~~ CONFIRMED and cleared 2026-09-07.** All 6 were still present and all 6 are
  gitignored (`.gitignore:2`), so removal was untracked-only: `_tmp_smoke_human`,
  `_tmp_smoke_tutor`, `_tmp_sonnet_tier`, `build_map_viewer`, `palette_page`,
  `scratch_items_probe`. Deleted. Original text: the 6 orphaned `.pyc` caches were not re-checked
  after the remediation passes. Harmless, but they let a filename search surface a module
  that does not exist. *Confirm by:* listing `scripts/__pycache__/` against the source list.
- **H4 (new). Other scripts may have been silently miswired by the engine cutover the same
  way finding 6 was.** 21 scripts reference `RPG2GBA_POKEEMERALD` or a `pokeemerald` path.
  Finding 6's failure is not staleness — the script is internally consistent and its
  docstring is a lie only because `engine/` stopped being a separate git repo. Any script
  that assumes the fork is (a) its own git repo, (b) outside this repo's tree, or (c)
  safe to `--clean` independently is exposed. *Confirm by:* for each of the 21, check
  whether it assumes fork-as-separate-repo — specifically `git -C <fork>`, paths written
  relative to a fork root that would collide with rpg2gba's own tree, and any `rm`/`rmtree`
  rooted at the fork. Finding 8(b) already establishes `git -C <fork>` appears **only** in
  `assembly_smoke.py`, so (a) is closed; (b) and (c) are not.

## Decisions

- **2026-09-07 — split from the parent audit into its own doc.** Q: append to
  `repo-audit-dead-code-stale-docs.md` or start fresh? A: fresh, referencing the parent.
  *Effect:* the parent stays CLOSED at its original scope; this doc owns `scripts/` hygiene
  and inherits finding 47 as input rather than re-deriving it.

## Open questions

### Q1. Delete `scripts/calibrate_map002.sh`?
Finding 3. It matches the parent Q12's stated criteria exactly — cannot be run correctly,
no in-file warning, replacement documented — and was missed only because that set was
hand-enumerated.

**Recommendation:** Delete it. Handle the referrers the way Stage B did: leave the dated
past-tense entries in `reference/archive/` and `reference/memory-archive.md` alone, because
those are history, not live instructions. Separately, add a one-line refusal or a dated
header to `scripts/convert_one_event.py` (finding 4) — it is sandboxed so deletion is not
warranted, but nothing in it says the frozen-Opus config it targets is retired.

**Amended 2026-09-07 after the H2 sweep — the deletion set is now three files, and they
want three different treatments:**
- `calibrate_map002.sh` — **delete** (finding 3, unchanged).
- `assembly_smoke.py` — **do not delete; disarm.** Finding 6's git calls are actively
  wrong, but the script's other half (poryscript compile-gate, header emission, unresolved-
  constant dummying) is the only tooling of its kind and would have to be rewritten if the
  smoke build is ever wanted again. Cheapest correct fix: make `_create_or_reuse_worktree`
  fail loud when `git -C <fork> rev-parse --show-toplevel` is not the fork itself, plus a
  dated `SPENT`-style header. That converts a silent miswire into a §4.5 loud failure.
- `run_human.py` — **mark only** (finding 7). A `SPENT` header naming the retired bulk run
  and the `registry.save()` at `:130`. No behaviour change; it is the hand-conversion path
  and costs nothing to keep.
**Blocked on:** —
**Answer:**

### Q2. Mark, move, or leave the ~75 spent one-offs?
Finding 1-2. (a) **Leave**, per the parent's original scripts/-policy decision — but that
decision is what produced the reaction that started this doc. (b) **Mark**: a one-line
dated `SPENT` header on each, mechanically, driven off finding 47's clusters. (c) **Move**
to `scripts/archive/`, mirroring the `reference/archive/` convention the repo already uses
for retired docs.

**Recommendation:** (c), with (b) applied to the handful whose status is genuinely
uncertain rather than spent. A path says "spent" simultaneously to an `ls`, a grep, a
`--help`-style exploration, and a sub-agent's file listing; a header only says it to
whoever opens the file. `reference/archive/` already proves the convention works here, and
per finding 47 only ~20 scripts are load-bearing, so the surface that has to be verified is
small. Cost is one round of H1's referrer checks.
**Blocked on:** —
**Answer:**

### Q3. Should the inventory get a durable home in the repo?
Finding 2: the only load-bearing/spent classification lives in a closed investigation doc.
If Q2 = (c), the directory layout becomes the inventory and no separate file is needed. If
Q2 = (a) or (b), the classification needs somewhere to live that agents actually read.

**Recommendation:** Only if Q2 is not (c) — then a short `scripts/README.md` listing the
~20 load-bearing scripts and what invokes each, with everything unlisted presumed spent.
An allow-list inverts the maintenance burden correctly: new load-bearing scripts get added
by the person wiring them up, and the list rots toward *over*-reporting spent-ness, which
is the safe direction. Do **not** write a 75-line spent inventory into the repo; parent
finding 34 is what happens to hand-maintained lists here.
**Blocked on:** Q2
**Answer:**

### Q4. Sweep for more finding-3-class hazards before or after the archive move?
H2. Two axes were checked (budget, destructive); at least two more are plausible (writes
into `engine/`, default-on `--write` flags).

**Recommendation:** Before. The whole lesson of finding 3 is that a hand-enumerated harmful
set misses things, and moving files into `scripts/archive/` makes a hazard *quieter* rather
than gone — an archived script still runs if invoked. Sweep first, delete what is harmful,
then move what is merely spent.
**Blocked on:** —
**Answer:** **Before — and the sweep is now run** (2026-09-07, at the operator's
instruction). Findings 6-9. It was worth doing first: it found one more confirmed hazard
(`assembly_smoke.py`) that an archive move would have hidden rather than fixed, and it
cleared three of the five suspects so the remaining decision surface is smaller. The
question is closed; what it opened is H4 and the amended Q1.

## Next steps

1. ~~Answer Q4 (ordering)~~ — answered 2026-09-07, sweep run before any motion.
2. ~~Run H2's sweep~~ — done 2026-09-07; findings 6-9.
3. ~~Re-check H3's orphaned `.pyc` caches~~ — done 2026-09-07; all 6 present, all 6
   gitignored, all 6 deleted.
4. Answer the **amended Q1** — now three files with three treatments (delete
   `calibrate_map002.sh`, disarm `assembly_smoke.py`, mark `run_human.py`), not one
   deletion. This is the only thing blocking remediation.
5. Optional: run H4's check across the 21 fork-referencing scripts. Sub-axis (a) is already
   closed by finding 8(b); (b) and (c) are open. Do this before Q2's archive move for the
   same reason Q4 was answered "before".
6. If Q2 = (c): run H1's per-script referrer grep across `.claude/`, `reference/`, `src/`,
   `tests/`, treating live hits as blocks; then move in one pure-motion commit.
5. Verify with `pytest` against the known baseline — **2984 passed, 16 skipped, 2 failed**
   (`test_ground_item_differential_vs_frozen_opus`,
   `test_pokemart_differential_vs_frozen_opus`; pre-existing, gitignored oracle under
   `output/`).

## Ground covered

- **The load-bearing/spent classification — already done**, parent finding 47. Inherited
  as input. Do not re-derive.
- **Budget-spending scripts — swept.** `grep -rln "claude-opus\|--model\|phase4 --run"
  scripts/` → `run_bulk.py`, `convert_one_event.py`, `calibrate_map002.sh`. Complete for
  that pattern.
- **Destructive scripts — swept.** `grep -rln "rm -rf\|rm -f\|shutil.rmtree\|unlink("
  scripts/` → `prep_bulk_run.py`, `route_movement_diff.py`, `calibrate_map002.sh`,
  `map_viewer_common.py`, `assembly_smoke.py`, `fetch_libmgba.py`. Only the intersection
  with the budget list was reviewed in detail; the other five are unreviewed (H2).
- **~~Other hazard axes — not looked at.~~ Swept 2026-09-07** (finding 8). *Writes into
  `engine/`:* `grep -rln "engine/" scripts/` → 8 files; only `assemble_pathfinder.py`
  actually writes there, by design and `--dry-run`-gated. *Git-mutating:* `git
  add|commit|push|checkout|reset|clean` → zero hits; `git worktree`/`branch -D` → only
  `assembly_smoke.py` (finding 6). *Default-on write flags:* none; every writer is
  opt-in (`--write`, `--yes`) or documented (`assemble_pathfinder`). *Budget, broadened*
  to `anthropic|claude_code|ollama|--model|convert_all` → adds nothing to the three
  already known. *Subprocess-invoking scripts:* only `compile_pory.py` (poryscript binary)
  and `assembly_smoke.py`.
- **The five previously-unreviewed destructive scripts — all five now reviewed**
  (finding 9). Three are false positives, `prep_bulk_run.py` was already marked, and
  `assembly_smoke.py` is finding 6.
- **Fork-cutover miswiring beyond `assembly_smoke.py` — not looked at.** 21 scripts
  reference the fork path; only the `git -C <fork>` axis was checked. That gap is H4.

---

## 2026-09-08 — kept open by decision, with new evidence

`investigations/repo-reorientation-strategy.md` closed on 2026-09-08 and folded in two of its
three sibling docs. **This one was deliberately kept open** (its D7): no decision there answers
the liveness-marker question, and that question is the root cause the other three kept
circling — "3 of 90 files carry a marker, and the load-bearing inventory lives only in a
document nothing points at."

Two new inputs for whoever resumes this:

1. **A third instance of the name-reads-retired / is-load-bearing trap, and the highest-stakes
   one yet.** `scripts/assemble_pathfinder.py` is the assembly step of *every* chapter build
   (`README.md:84-96`, `BUILD_PLAN.md:121`), was edited mid-CH05 to fix a live defect (commit
   `08baf280`), and is referenced by 20+ files — while carrying the name of an era retired and
   archived on 2026-08-04. `calibrate_map002.sh` and `assembly_smoke.py` (findings 3, 6 above)
   were landmines to disarm; **this one is the build.** See reorientation finding 18. A fourth
   instance exists outside `scripts/`: `ROM_TEST_DEV.md`, 33 referrers, reads as an untitled
   transcript (finding 33).

2. **`scripts/` turns out to be mostly a third category, not a binary.** The reorientation's
   D1 established — after the operator pointed out that a general-vs-game-specific sort would
   have condemned the map viewer server — that the repo has three kinds of thing, not two:
   pipeline, game pack, and **instrumentation**. Most of `scripts/`'s load-bearing set is
   instrumentation (map viewer, oracle harvest, comparison renderers, verification scripts).
   **This reframes the marker question:** the useful marker may not be `SPENT` vs. nothing, but
   a positive statement of which bucket a file belongs to and what reads it. A file marked
   "instrumentation, read by the CH0N boot-walk loop" cannot be misread the way
   `assemble_pathfinder.py` currently is.
