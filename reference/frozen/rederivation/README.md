# The CH01–CH04 re-derivation freeze

**Written 2026-09-10 for `REDERIVATION_PLAN.md` step P7.** Scaffolding: this
directory and its generator (`scripts/freeze_rederivation.py`) are scheduled for
deletion at **P10**. Nothing in the pipeline reads these files.

## What this is

`PROJECT_TODO.md` **#62**, verbatim: *freeze the expected answers, derive, diff,
then write — never derive-and-write in one pass, or a regression in the
derivation logic reads as a correct re-disposition.*

One file per chapter, `CH0n.freeze.json`, capturing the committed, gate-passed
state of that chapter's manifest, dispositions, and beats **before** P8
regenerates anything. Format precedent: `../archetype_expectations.json`.

Each source artifact is pinned by its **git blob sha**, not by a hash of the
working file. That is deliberate: P8 *will* overwrite the working manifests, and
a working-file hash would become a dangling reference the moment it did. A blob
sha stays resolvable forever, so `tests/test_rederivation_freeze.py` can keep
verifying the freeze against exactly what was frozen.

Regenerate or verify:

```bash
python scripts/freeze_rederivation.py write
python scripts/freeze_rederivation.py check   # non-zero on drift
```

## What it actually protects — read this before trusting a P8 diff

|  | CH01 | CH02 | CH03 | CH04 |
|---|---|---|---|---|
| Manifest rows frozen | 211 | 83 | 131 | 42 |
| Dispositions frozen | **none — never existed** | **none** | **none** | 42 |
| Own beats (composed) | 17 (17) | 14 (31) | 30 (61) | 13 (74) |
| Own beats claiming manifest rows | 0 | 0 | 0 | 0 |

Three things that table is saying, each of which limits P8:

**1. Only CH04 has a hand-authored expected answer.** `CH01/CH02/CH03.dispositions.json`
do not exist and, verified against `git log --all`, never have. For those three
chapters #62's safeguard is **structurally unavailable on the disposition side**:
there is no prior answer to diff against, and an expectation written now would be
authored by the same process that derives it — which `REDERIVATION_PLAN.md` §1
identifies as exactly how #90 got through ("the frozen expectation and the
derivation come from the same rule, so they agree with each other and disagree
with the ROM"). No dispositions were invented here to fill the gap. That would
have manufactured the appearance of a check.

**2. The CH01–CH03 manifests are themselves derivation output, not an
expectation.** They were generated retroactively in `de9343cb`, long after those
chapters shipped, specifically so slice 2's re-derivation would have "something to
diff against." So manifest-side agreement in P8 proves only that *the derivation
did not change*. It is a regression test, never a correctness test. CH04's
dispositions are the only artifact here that a human authored and a gate passed.

**3. No beat in CH01–CH04 claims a manifest row.** All 19 of CH05's own beats
carry `rows=`; none of the 74 own beats across CH01–CH04 do. The beat↔row join
that makes CH05's checks meaningful does not exist for any chapter being
re-derived, and P8 cannot lean on it. Pinned by
`test_no_chapter_before_ch05_claims_manifest_rows_from_a_beat` so it fails loudly
if it stops being true.

`beats` is the **composed** list `load_chapter` returns — a chapter's own beats
plus, recursively, every predecessor's — so CH01's 17 appear in all four files.
Each entry carries `own` (bare name = own, `CHnn:` prefix = inherited). Diff `own`
beats per chapter; an inherited-beat diff belongs to the chapter that owns it.

## What CH01–CH03 had instead of dispositions

Reconstructed from the archive 2026-09-10, because "there is no dispositions file"
invites the wrong conclusion — those chapters were built under a real process, it
just produced no per-row artifact.

The process was: a hand-written beat list, **approved by the operator before build
work** (explicit from CH02 on); build; the chapter's headless playtest suite green
on one build; then a human §9 boot-walk in mGBA. Completion meant *the chapter
plays*, asserted by a passing suite and a human walk — never *every event page has
a decision*, because nothing enumerated the pages. Decisions that would today be
`cosmetic` / `blocked` / `unreachable` were written as prose, scattered across the
chapter doc's "known open issues" tables, cells in its beat-chain table, and
`DEFERRED_BEATS` tuples in the chapter module.

`reference/archive/PLAYTEST_AUTHORING_IMPROVEMENT.md` (2026-08-20) is the
post-mortem on that process across CH01–CH03, and its one-line diagnosis is the
reason the manifest exists: *"Every failure class in this document is the same
shape: an omission that no artifact made visible."* Its evidence is worth carrying
into P8 — CH03's approved beat count grew **35 → 60** between approval and gate,
which the doc is careful to call omission discovered late rather than scope creep;
and CH01/CH02 both passed §9 with a warp-continuation bug live, because their
beats simply never asserted a post-warp state write.

Surviving disposition-*like* records, none exhaustive, none machine-checked:

| Artifact | Covers | Trust |
|---|---|---|
| `reference/archive/SLICE1_EVENTS.md` | all 131 CH01 events, hand-compiled, with an explicit `DROP:`/`SKIP:` taxonomy | Best of the lot, but CH01 only, and self-flagged: *"a map, not a source of truth"* |
| `reference/chapters/0{1,2,3}-*.md` §6/§7 | leftover `transpile_unhandled` queue items, not event pages | Partial, and CH01's own §7 flags itself as drifted |
| `DEFERRED_BEATS` in the chapter modules | what the author remembered to defer | Fine as a record of intent; useless as a completeness check |
| §9 gate record in `00-atlas.md` | pass/fail per chapter | High confidence the chapter plays; none that every page was considered |

**The consequence for P8:** for CH01–CH03 the evidence of record is the chapter
doc, the gate-passed beats, and the booted ROM — in that order of convenience and
the reverse order of authority. Per `REDERIVATION_PLAN.md` §1, where a frozen
literal and a resolver disagree, **the booted ROM breaks the tie**. Expect to need
it, and expect the count of rows needing it to be the real cost estimate for this
task.
