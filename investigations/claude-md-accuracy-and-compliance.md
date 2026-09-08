# Investigation: CLAUDE.md — what it claims that is false, and what it mandates that nobody does

**Status:** **closed 2026-09-08** — folded into `investigations/repo-reorientation-strategy.md` (its D7). Q5 carried forward there as Q8. See the closing note at the end.
**Started:** 2026-09-07   **Last updated:** 2026-09-07
**Question:** Which parts of CLAUDE.md are factually wrong about the repo, and which of its rules are stated but not consistently followed?
**Expected artifact:** undecided

**Parent:** `investigations/repo-audit-dead-code-stale-docs.md` (CLOSED). That audit swept
the root markdown corpus for *frontier* claims and fixed CLAUDE.md §3, §5 and §7 as part of
its Stage A and C. It never audited CLAUDE.md as a whole against the filesystem, and it
never asked the compliance question at all. Sibling docs:
`investigations/conversion-agent-package-boundary.md`,
`investigations/scripts-dir-liveness.md`.

**Two failure classes in scope**, per the operator's framing:
- **(A) False claims** — the file asserts something about the repo that is not true.
  Example given: §1's "Two agents, one project" (`CLAUDE.md:15-22`), which opens the whole
  document by centering the conversion agent.
- **(B) Unfollowed rules** — the file mandates something the codebase does not consistently
  do. A rule that is routinely ignored is worse than an absent one: it teaches the reader
  the document is decorative, and that discount gets applied to the rules that *are*
  load-bearing.

## Summary

CLAUDE.md is 425 lines, last substantively edited 2026-09-07 by the parent audit, which
fixed the sections it happened to touch and left the rest unexamined. Three verification
passes are now in, and **the two failure classes came back very unevenly.**

**Class A (false claims) is real and concentrated in the file's maps and tables.** §3's
directory tree omits nine whole packages under `src/rpg2gba/`, describes `reference/` in
its pre-2026-07-13 flat layout, and gives a `conversion_agent/` child list that shows the
retired LLM regime's members while hiding the deterministic spine — the exact inversion of
§4.1's stated priority (1-4). §12's env table is wrong about its own source file in both
directions (5). §6 tells the reader the flag registry is "dormant during the current
Phase 2" when Phase 4 is the active phase per the authority §7 itself designates (8). And
§4.3's source-of-truth table no longer names the actual mint point for `MOVE_*`/`SPECIES_*`
(7) — a gap **the parent audit's own consolidation created** and did not backfill.

**Class B (unfollowed rules) is real but narrow, and it is a scope problem rather than
neglect.** The first sweep reported §5's Python rules clean — but it covered only
`src/rpg2gba/`. Re-measured across all three trees with an AST scan (15): the
built-in-generics ban holds **perfectly, repo-wide**, while "type hints on all public
functions" holds in `src/` (0 of 1018 missing a return hint) and fails in `scripts/` (17%)
and `tests/` (18%). §5 is headed "Code Conventions" with no scope qualifier, so it reads as
repo-wide law while being enforced in one of three directories. §5's Ruby rule has the same
defect (14). Everything else checked clean: no `print()` in library code, no unencoded text
reads, Click everywhere and argparse nowhere (10); §8's three coverage claims all hold
against real test files (11); the few-shot convention is accurate to the filename (12). The
one outright broken instruction is §8's `ruby test/test_deserializer.rb` — **the file and
the entire `test/` directory do not exist** (9).

So the honest read: CLAUDE.md's rules are mostly real and mostly kept; what has rotted is
its *description of the repo*, and where a rule does go unkept it is because the rule never
said where it applied. Those want different fixes — Q1/Q2 for the descriptions, Q5 for the
scope. Note also what this sweep **cannot** see: process rules (§9's gates, §10's ask-first
list, §2's boundaries) are not grep-checkable and were not audited. See H2.

## Findings

1. **§3's tree omits nine packages under `src/rpg2gba/`.** `CLAUDE.md:79-99` shows
   `pbs_converter/`, `rxdata_deserializer/`, `conversion_agent/`, `tileset_converter/`,
   `pipeline.py`. Actually present and unlisted: `chapter_atlas/`, `chapter_manifest/`
   (13 files), `map_deserializer/`, `playtest/` (~20 files), `routing/`,
   `species_converter/`, `text_validator/`, `trainer_converter/`, `traversal/`.
   **Wrong action it causes:** an agent using the tree as its map of what exists does not
   learn the chapter-manifest, playtest-harness, routing or map-deserializer packages
   exist, and may rebuild what is already there.

2. **§3's `conversion_agent/` child list is missing most of the live spine.**
   `CLAUDE.md:90-97` lists `orchestrator.py`, `flag_registry.py`, `backends/{ollama,
   claude_code}.py`, `prompts/`. Unlisted: `transpiler.py`, `deterministic.py`,
   `transpile_driver.py`, `triage.py`, `hand_overrides.py`, `fork_index.py`,
   `poryscript.py`, `lane.py`, `queue_evidence.py`, `run_report.py`, `prompt_builder.py`,
   `hand_conversions/`, and a **third backend, `backends/human.py`**. So the tree shows
   the retired LLM regime's members and hides the deterministic spine — the exact inversion
   of §4.1's stated priority. Feeds
   `investigations/conversion-agent-package-boundary.md` finding 2.

3. **§3 describes `reference/` in its pre-reorganization flat layout.**
   `CLAUDE.md:103-107` names `reference/poryscript_cheatsheet.md`,
   `reference/rgss_event_commands.md`, `reference/essentials_to_emerald_map.md`. All three
   moved to `reference/guides/` in commit `c7f4cba8` (2026-07-13). Only
   `reference/uranium_id_map.json` is still where the tree says. The tree also omits
   `uranium_data/`, `recon/`, `viewer/`, `findings/`, `archive/`, `chapters/`,
   `manifests/`, `routes/`, `frozen/`, `scripts_dump/`, `map_feedback/`.
   **Wrong action it causes:** an agent follows a path from the tree, gets a
   file-not-found, and may conclude the doc does not exist rather than that it moved.
   *Note this survived the parent audit's Stage C, which fixed two other stale
   `reference/` paths elsewhere in the repo but not this tree.*

4. **§3's tree omits every root-level tracking document, including the one §3 itself
   depends on.** Present at root and unlisted: `BUILD_PLAN.md`, `MEMORY.md`,
   `PROJECT_TODO.md`, `POST_CH05_REVIEW.md`, `CH05_DECISIONS.md`, `ROM_TEST_DEV.md`,
   `PLAYTEST_AUTHORING_IMPROVEMENT_V2.md`, `investigations/`, and **`.env-paths`** — which
   `CLAUDE.md:126` calls the authoritative source of every `RPG2GBA_*` value. Mild on its
   own; notable because §7's document-authority table and §3's tree now disagree about
   which documents exist.

5. **§12's env-var table is half wrong about its own source.** `CLAUDE.md:392` states "All
   of these live in the tracked `.env-paths` at the repo root and are already correct."
   `.env-paths` actually defines three variables: `RPG2GBA_URANIUM_SRC` (matches),
   `RPG2GBA_POKEEMERALD` (matches), and `RPG2GBA_PORYSCRIPT` — **which the table omits
   entirely**. Of the four the table lists, `RPG2GBA_OUTPUT` and `OLLAMA_HOST` are **not in
   `.env-paths` at all**; both are commented out in `.env.example`, and `RPG2GBA_OUTPUT` is
   a code-level default at `src/rpg2gba/pipeline.py:102,444`.
   **Wrong action it causes:** an agent believes `RPG2GBA_OUTPUT`/`OLLAMA_HOST` are pinned
   when they are defaults, and never learns a poryscript binary path is configured — which
   matters for map-conversion work. This is a §3-class error inside the §12 quick reference:
   the rule "never set `RPG2GBA_*` yourself, `.env-paths` has them" is correct, but the
   table beside it misdescribes what `.env-paths` contains.

6. **§12's four one-liners all still work — verified, no action.** `phase2 --clean`
   (`pipeline.py:145-152`), `flag_registry validate` (`flag_registry.py:640,652,666`),
   `convert-map --map-id` (`pipeline.py:351-363`), and `make modern`
   (`engine/Makefile:339`) are each accurate as written. Recorded as a negative result so
   nobody re-checks. Minor: the `make` line requires `RPG2GBA_POKEEMERALD` to be in the
   shell environment, which `CLAUDE.md:126` tells you never to put there — the pipeline
   loads `.env-paths` itself but does not export into your shell. Cosmetic tension, not an
   error.

7. **§4.3's source-of-truth table no longer names the real mint point — and the parent
   audit is why.** `CLAUDE.md:151-152` names `pbs_converter/pokemon.py` and `moves.py` as
   the sources of truth for `SPECIES_*` and `MOVE_*`. The parent audit's second remediation
   pass created `src/rpg2gba/pbs_converter/_resolve.py` holding the five shared resolver
   mixins, all delegating to `_naming.to_constant` (`_naming.py:47`). Neither `_resolve.py`
   nor `_naming.py` appears in §4.3's table, and `to_constant` is consumed from ~11 modules
   across `pbs_converter/`, `tileset_converter/`, `trainer_converter/` and
   `conversion_agent/`. **This is a §4.3 violation created by a change made to fix a §4.3
   violation** — the consolidation was right, the table was never updated to follow it.
   *Sharpest instance of the file drifting behind its own repo.*

8. **§6 states the wrong active phase, and §7 is the rule it breaks.** `CLAUDE.md:254-255`:
   the flag registry "is a Phase 4 component, dormant during the current Phase 2. Read it
   when Phase 4 starts." `MEMORY.md` → Current Phase — which `CLAUDE.md:274-275` declares
   the **sole** frontier authority — has the project deep in Phase 4 with CH01-CH05 gate-
   passed. CLAUDE.md even contradicts itself internally: `:89` tags `conversion_agent/` as
   "Phase 4: transpiler + classifiers". **Wrong action it causes:** an agent reads §6, takes
   the registry for dormant future work, and skips the hard rules two paragraphs below it —
   including "every flag/var name goes through the registry, never hardcode one."
   §7's own instruction ("if you catch a topic reference asserting frontier status, fix it
   in place with a dated correction") applies to this passage, inside the same file.

9. **CONFIRMED — §8 documents a test command whose file and directory do not exist.**
   `CLAUDE.md:325`: `ruby test/test_deserializer.rb`. Verified first-hand: `ls test` →
   "No such file or directory"; a repo-wide `find -name "test_deserializer*"` outside
   `engine/` returns nothing. Python tests live in `tests/` (plural) and no Ruby test file
   exists there either. The **only** unambiguous Class-B hit in the sweep, and it is a
   documented command that fails rather than a rule people ignore.

10. **NEGATIVE RESULT — §5's Python conventions are followed, essentially without
    exception.** Swept across `src/rpg2gba/`: `from typing import` has 30 hits, **zero**
    importing the banned `List`/`Dict`/`Tuple`/`Optional`/`Union`; the only two `print(`
    hits in library code are inside a `@click.command()` (`triage.py:530`) and a docstring
    example (`text_validator/__init__.py:23`); all 17 `open(` calls lacking `encoding=` are
    binary opens (`Image.open`, `wave.open`, `tarfile.open`), with every text open carrying
    `encoding="utf-8"`; `click` in 12 files and `argparse` in zero. Recorded as a finding
    because the *absence* of drift here is the load-bearing result — it is what makes
    finding 9 an isolated defect rather than evidence of a decorative document.

11. **NEGATIVE RESULT — §8's three coverage claims all hold.** Round-trip + golden PBS
    tests: `tests/test_pbs_items.py:48`, `test_pbs_moves.py:45`, `test_pbs_abilities.py:39`
    plus golden fixtures under `tests/fixtures/`. Orchestrator synthetic-map integration:
    `tests/test_conversion_agent.py:487`. Flag-registry collision / validation / persistence:
    same file at `:83,138` (collision), `:95,313,335,349,354,369` (validation),
    `:107,146,195,258,808` (persistence).

12. **NEGATIVE RESULT — §5's few-shot prompt convention is accurate.**
    `src/rpg2gba/conversion_agent/prompts/few_shot/` holds 5 `.md` files, and both filenames
    §5 cites as examples (`give_item_with_fanfare.md`, `branching_dialogue.md`) exist
    exactly as named.

13. **§4.7's macro count is off by one; the specials count is right.** `CLAUDE.md:178`
    claims "624 specials in `data/specials.inc`, 385 macros in `asm/macros/event.inc`".
    Verified first-hand: `grep -c '^\s*\.macro' engine/asm/macros/event.inc` → **386**;
    specials → **624** correct (a raw `def_special` grep returns 625, one of which is the
    macro's own definition line). Cosmetic — §4.7's actual mechanism is "grep the fork", not
    the number — but it is a hardcoded count in a file that tells you never to trust
    hardcoded inventories.

14. **§5's Ruby-minimality rule is a gray area, not a violation.** "Do not add new Ruby code
    beyond what's needed for deserialization" (`CLAUDE.md:227-229`). In-package Ruby is
    exactly one file, `src/rpg2gba/rxdata_deserializer/deserialize.rb`, as specified. But
    `scripts/` holds five more (`recon_maps.rb`, `recon_scripts.rb`, `dump_messages.rb`,
    `dump_constants.rb`, `spike_dat_inventory.rb`) — all Phase-0 recon, all in the spent
    cluster per the parent audit's finding 47. The rule's wording scopes to the deserializer
    module, so this is not a breach; it is a rule whose scope is narrower than its
    imperative tone suggests. (`reference/scripts_dump/*.rb` are extracted *Uranium* game
    scripts, not authored code — out of scope.)

15. **CONFIRMED Class-B hit — §5's typing convention is two rules, and the second is
    followed only in `src/`.** The operator named this line. Measured with an AST scan over
    every public (non-`_`-prefixed) function in the repo:
    - **The built-in-generics ban is followed perfectly.** Zero `from typing import
      List|Dict|Tuple|Optional|Union` and zero `List[`/`Optional[`-style annotations across
      `src/`, `scripts/` **and** `tests/`. This half is not the problem.
    - **"Type hints on all public functions" (`CLAUDE.md:191`) is not.** `src/rpg2gba/`:
      1018 public functions, **0** missing a return hint, 4 missing a parameter hint.
      `scripts/`: 268 public functions, **48 (17%)** missing a return hint, 38 (14%) missing
      a parameter hint. `tests/`: 3307 public functions, **627 (18%)** missing a return hint,
      387 (11%) missing a parameter hint.

    §5 is headed "Code Conventions" with no scope qualifier, so it reads as repo-wide while
    being enforced in exactly one of three trees. Worst offenders: `tests/
    test_chapter_manifest_checker.py` (79), `tests/test_assembly.py` (44),
    `tests/test_playtest.py` (37); `scripts/tree_debug.py` (9),
    `scripts/render_pc_exterior_compare.py` (6). The four `src/` misses are the *same*
    parameter in four sibling files — `manifest_dir=None` in
    `playtest/archetypes/{arrival_nudge,item_ball,trainer,warp}.py`
    (e.g. `arrival_nudge.py:44`), everything else in those signatures annotated. Almost
    certainly `Path | None`.

    **This is the same shape as finding 14** (the Ruby rule): a rule whose imperative tone is
    repo-wide and whose real scope is one directory. Two of the file's conventions now share
    that defect, which suggests §5 needs a scope statement rather than 675 individual fixes.

## Hypotheses / unverified

- **H1. The drift is structural, not incidental: §3's tree has no owner and no check.**
  Every stale entry in findings 1-4 is in the one artifact nothing generates and nothing
  tests. This is the parent audit's finding-34 class (hand-maintained inventories rot) and
  its finding-42 class (a hand list of custom engine files rotted into a dangerous claim),
  now appearing a third time. *Confirm by:* checking whether any test, hook, or CI step
  reads §3's tree — expected answer is no.

- **H2. Class B may be real in the process rules, where a grep cannot reach.** §9's three
  manual review gates, §10's proceed/ask-before/always-ask lists, and §2's "what you do NOT
  do" boundaries are all rules about agent *behaviour*, and nothing in this sweep could
  check them. The operator's "not followed consistently" remark arrived without a line
  selection, so which rule was meant is unknown. *Confirm by:* the operator naming the line
  (Q3), or by sampling recent session transcripts / git history for gate-skipping — the
  latter is expensive and should not start without Q3's answer.

## Decisions

- **2026-09-07 — scope is CLAUDE.md itself, two failure classes.** Q: what is this
  investigation about? A: (A) false claims and (B) unfollowed rules, per the operator's two
  messages. *Effect:* the verification fan-out covers both — structural/pointer accuracy
  and convention compliance — rather than staleness alone.
- **2026-09-07 — Q3 answered: the unfollowed line is §5's typing convention.** Measured
  (finding 15). *Effect:* confirmed a Class-B defect my first sweep missed by scoping to
  `src/` and to only half the rule; opened Q5. Also a method lesson for this doc — a
  "negative result" is only as broad as the tree it was run over, and finding 10 as
  originally written overstated its own reach.
- **2026-09-07 — own doc, not an append to the parent audit.** Same rationale as the two
  sibling docs: the parent is a closed artifact with an executed plan.

## Open questions

### Q1. Stop hand-maintaining §3's directory tree, or regenerate it?
Findings 1-4 are all one artifact: a hand-drawn tree that nothing generates and nothing
tests. This is the third appearance of the same class in this repo — the parent audit's
finding 34 (hand-maintained lists rot) and finding 42 (a hand list of custom engine files
rotted into a claim whose failure mode was destroying working C). Options: (a) update the
tree by hand now; (b) delete the tree and replace it with a one-line instruction to run
`ls src/rpg2gba/`; (c) keep a tree but generate it, with a test that fails when it drifts.

**Recommendation:** (b), plus a short hand-written paragraph naming only the four or five
packages a newcomer needs oriented to and explicitly labelled *orientation, not an
inventory*. That is precisely the shape the parent audit landed on for
`engine/RPG2GBA_VENDOR.md` under its Q10, for the same reason, and it is already proven in
this repo. (a) restarts the rot clock; (c) buys accuracy at the cost of a test nobody will
thank you for when it goes red on an unrelated branch.
**Blocked on:** —
**Answer:**

### Q2. Fix the four substantive false claims now, in this branch?
Findings 5 (§12 env table), 7 (§4.3 missing `_resolve.py`/`_naming.py`), 8 (§6's "current
Phase 2"), 9 (§8's nonexistent Ruby test command). Each is a small, independent, unambiguous
edit; none needs a decision beyond "yes". Finding 13's off-by-one macro count rides along.

**Recommendation:** Yes, as one commit, separate from whatever Q1 becomes. Per the parent
audit's Q6 the fix goes in the same change that records the finding, never filed for later
— and finding 8 in particular is a rule-suppressing error: it tells an agent to skip §6's
registry rules entirely. For finding 9, decide between deleting the line and writing the
missing Ruby test; deleting is right unless you want the coverage, in which case that is
its own task, not a doc fix.
**Blocked on:** —
**Answer:**

### Q3. Which line did you mean by "not being followed consistently"?
The compliance sweep came back nearly clean (findings 10-12): §5's Python rules and §8's
coverage claims are real and enforced. The only mechanical hit is finding 9. So either the
remark pointed at finding 9, or at a rule a grep cannot check — §9's review gates, §10's
ask-before-proceeding lists, §2's boundaries (H2).

**Recommendation:** Name the line and I will scope it as its own finding. I would not start
a transcript/history audit for gate compliance speculatively — it is expensive, and if the
answer is "§10's ask-before-proceeding list" the fix is likely to be rewriting the rule to
be checkable rather than measuring how often it was missed.
**Blocked on:** —
**Answer:** **§5's Python typing convention** (2026-09-07, in chat). Measured — see finding
15. The operator was right and my sweep was wrong in scope: it checked only `src/rpg2gba/`
and only the banned-imports half of the rule. The generics ban holds repo-wide; "type hints
on all public functions" holds in `src/` and fails in `scripts/` (17%) and `tests/` (18%).
Opens Q5. Does **not** open the process-rule audit — H2 stays unexplored and unblocked-on.

### Q4. Is CLAUDE.md carrying weight it should delegate?
Not a defect finding, an editorial one. §1's "Two agents, one project" (`:15-22`) spends the
file's most-read real estate on a distinction whose second half — the conversion agent — has
not been invoked once since the 2026-06-18 pivot (parent audit Q11). The framing is not
*false*: §4.1 and §7 both correctly describe the LLM as a hand-invoked tail tool. But an
agent reads §1 before §4.1, and the opening establishes the LLM as co-equal architecture.
Related: `investigations/conversion-agent-package-boundary.md` asks the same question about
the directory name.

**Recommendation:** Rewrite §1's second bullet to lead with the deterministic transpiler as
the spine and demote the conversion agent to a subordinate clause, keeping the role-confusion
warning (which is still useful — it stops an agent hand-faking conversions, per §2). Do not
delete the section. Sequence this *after* Q1 of the package-boundary doc, since if that
package is renamed, §1's prose changes anyway and one edit serves both.
**Blocked on:** — (but sequence after `conversion-agent-package-boundary.md` Q1)
**Answer:**

### Q5. Scope §5's conventions, or enforce them everywhere?
Finding 15, and finding 14 shares its shape. §5 reads as repo-wide law; it is enforced in
`src/rpg2gba/` and not in `scripts/` or `tests/`. Options: (a) **scope the rule** — state
that §5 governs `src/rpg2gba/` and that `scripts/`/`tests/` are held to the generics ban
only; (b) **enforce it** — annotate ~675 functions, most of them one-line test bodies;
(c) **enforce mechanically** — add ruff's `ANN` rules with a per-directory config, which
makes the scope decision explicit in a file that cannot rot silently.

**Recommendation:** (a) now, (c) later if you want it to stay true. Test functions returning
`-> None` are annotation noise that buys nothing — the value of a return hint is at an API
boundary, and a pytest test has no caller. Making `src/` the stated scope turns a rule
everyone breaks into a rule everyone keeps, which is the whole point; (b) is 675 edits for
no defect caught. If you do want (c) eventually, note ruff is already in use on this repo
and the parent audit ran it clean on every file it touched.
**Blocked on:** —
**Answer:**

## Next steps

1. ~~Answer Q3~~ — answered 2026-09-07; see finding 15 and Q5.
2. Answer Q5 — it is the one with a real fork (scope the rule vs. annotate 675 functions).
3. Answer Q1 and Q2; both are executable immediately and independently. Q2 is four small
   edits plus finding 13's count; Q1 is a decision about one section.
4. Sequence Q4 after `conversion-agent-package-boundary.md` Q1, so §1's prose is rewritten
   once rather than twice.
5. Not started, and deliberately: any audit of process-rule compliance (§9 gates, §10
   ask-first). Blocked on Q3; see H2 for why it should not start speculatively.

## Ground covered

- **§3 repository layout — swept** against the filesystem (findings 1-4).
- **§12 quick reference — swept**; env table wrong (5), one-liners all correct (6).
- **§3's vendored-engine subsection (`:118-129`) — deliberately not re-verified.** The
  parent audit rewrote it on 2026-09-07 and its closing finding is precisely about that
  text; re-checking it here would duplicate work done twice already.
- **§4.3 / §4.7 / §6 / §7 pointer sweep — done.** Every file path named in those four
  sections exists at the path given; the 2026-07-13 reorg and the 2026-09-07 archiving pass
  left **no** stale paths in them. The errors there are claim errors (7, 8, 13), not path
  errors. `command_pokeemerald_map.md` was read and does genuinely function as the §4.7
  capability ledger; `essentials_to_emerald_map.md` does genuinely function as the flag/var
  pre-seed table, exactly as §4.7 describes.
- **§5 Python conventions — swept twice.** The first pass (findings 10-12) covered
  `src/rpg2gba/` only and reported clean; that scope was too narrow and the second pass
  (finding 15) covers `src/`, `scripts/` and `tests/` with an AST scan, which is the
  authoritative measurement. §8's coverage claims and §5's few-shot convention are clean and
  need no re-check.
- **Process-rule compliance (§9, §10, §2) — not looked at.** Not checkable by grep; blocked
  on Q3.
- **§1, §2, §11 prose — read, not systematically verified.** §11's three pitfalls each cite
  a real incident recorded in the parent audit or MEMORY.md; no error found, but no
  line-by-line check was run.

---

## CLOSED 2026-09-08 — folded into `investigations/repo-reorientation-strategy.md`

The operator walked that doc's questions on 2026-09-08. **Its **D4** answers this doc's Q1 (delete §3's hand-drawn tree — recommendation (b) adopted) and Q4 (§1's framing rewritten to lead with the deterministic spine), and its step 1 covers Q2's four factual fixes. `CLAUDE.md` is restored from `CLAUDE.md.bak` and **edited in place, not rewritten** — the section verdict was 1 DROP / 6 KEEP-BUT-FIX / 6 KEEP-AS-IS, and §2/§9/§10 exist in binding form nowhere else in the corpus.**

Its remaining question, **Q5 (scope §5's typing convention to `src/` vs. annotate ~675 functions; recommendation (a) now, (c) later)**, is carried forward as **Q8** of the
reorientation doc and is non-blocking.
