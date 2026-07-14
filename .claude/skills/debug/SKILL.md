---
name: debug
description: >
  Lead-debugger workflow for boot-walk findings (something looked or behaved
  wrong in the ROM on device/mGBA). Use when the user reports an in-game
  issue, invokes /debug, or asks to fix a boot-gate bug. Orchestrates the
  cycle: clarify the symptom → localize the layer → fix via sub-agents →
  full verified rebuild with hash evidence → taildrop for retest. Guides the
  LEAD agent; it is not a sub-agent brief. Advisory on method; all standing
  repo rules (CLAUDE.md, §9/§10 gates) still apply.
---

# debug — boot-walk finding, from report to retest ROM

You are the lead debugger. The user found something wrong while playing the
slice ROM. Your job ends when a **provably fresh** ROM containing the fix is
on their phone, or when the finding turns out to need a user decision.

Invoking /debug is standing consent for **one full rebuild per fix cycle**
(the multi-minute chain does not need a separate ask). Everything else
follows normal session rules.

## Phase 0 — Intake (clarify only what's missing)

Restate the symptom in one sentence. Then ask ONLY for details the report
doesn't already contain (AskUserQuestion; skip entirely if the report is
precise):

- Which map, and where — viewer coords or a nearby landmark.
- Expected vs observed (what would Uranium-on-PC do there?).
- Reproducible or once-off; exact steps if non-obvious.
- Which ROM — the taildrop timestamp is enough.

No investigation toward a fix until the symptom is unambiguous.

## Phase 1 — Localize before hypothesizing

The pipeline is a chain of boundaries: Uranium data → Phase-3 JSON →
transpiler/classifiers → .pory → staging → engine gen files → make → ROM.
The symptom lives at exactly one of them.

1. **Find the last correct artifact.** Diff representations across
   boundaries (map JSON vs .pory vs staged .inc vs emitted PNG/pal vs
   in-game) instead of reasoning about the symptom. Preview-right-but-
   ROM-wrong means the emission boundary, not the art (bug #1).
2. **Faithful-vs-bug check.** Before designing any fix, verify what Uranium
   actually does: the map JSON, `reference/scripts_dump/*.rb`, or ask the
   user to check on PC. Two past "bugs" were faithful data (rug/warp
   pattern; pond-dock ledges). Fixing faithful behavior is a regression.
3. **Grep the engine, don't theorize about it.** Engine mysteries are
   documented in code (`GetFlagPointer(0)` null sentinel, anim-table
   semantics, reflection scan box). §4.7 applies to debugging, not just
   conversion.
4. **Probe, then size.** Write a scratchpad probe/census script against real
   data (the `reflect_probe.py` / `dispatch_census.py` pattern). It settles
   the hypothesis AND tells you whether this is one cell or a corpus-wide
   class — the fix design differs completely.

## Phase 2 — Fix

- Delegate per the established pattern: research sub-agents for fork/RGSS
  reads, Sonnet builders on disjoint files; the lead owns cross-file seams
  and ALL `engine/` edits (brief: "read
  `reference/guides/engine_extension_surface.md` first").
- Fix the converter, never its output (§11). If the fix needs a fidelity or
  engine-baseline call (drop content? change vanilla behavior?), STOP and
  ask the user (§10) — the reflection narrow-scan was a working "fix" the
  user rejected.
- **Pin the violated invariant**, not the fix: identify why no existing test
  caught this (bug #1: nothing pinned palette slot 0) and pin that.

## Phase 3 — Rebuild with evidence (trust-critical; never skip)

Past cycles delivered ROMs where the fix silently wasn't inside (edit lost
from the tree; stale staging) — indistinguishable, from the user's side,
from "forgot to rebuild". So the rebuild is mechanical and evidenced:

1. `git diff` (or `git status`) shows the fix in the working tree. The
   reflection edit once vanished from the tree while the tested ROM had it.
2. Clean known stale state: slice and walker builds share mutable staging +
   engine gen files — clean both when build flavors switched; remember the
   accumulating `staging/layouts/layouts.json` wart and the fork_index
   `_INDEX_FORMAT` bump rule if extractors changed.
3. Hash the current ROM: `sha1sum engine/pokeemerald.gba` (record it).
4. Run the FULL chain — transpile driver → stage_slice_scripts →
   assemble_pathfinder → `make -C engine -j16 modern`. No shortcuts, no
   "this fix only touches X". Run the test suite too.
5. Hash again. **If the hash didn't change, the fix did not reach the ROM —
   stop and investigate; never ship an unchanged hash.** (Engine-only edits
   may legitimately skip the assemble steps, but the make + hash-change
   rules still hold.)
6. Taildrop (`tailscale file cp engine/pokeemerald.gba iphone182:`) and
   report in the SAME message: short sha1, build timestamp, one line of
   what changed, and what to check in-game.

## Close-out bookkeeping (owned by this skill)

- Add/close the finding in `SLICE1_TODO.md` #11 (or the current slice's
  checklist): one line, symptom → root cause → fix.
- Update MEMORY.md's current-work entry per the memory protocol.
- Commit per repo norms (usually after the user's retest confirms).
