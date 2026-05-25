---
name: phase-walkthrough
description: Walk the user through everything built in a completed pipeline phase (PBS converters, map deserializer, conversion agent, tilesets, engine features, …), one logical unit at a time, paused between chunks. Designed for reviewing on small screens (e.g. mobile SSH) and as the briefing for a manual review gate. Pass the phase number (e.g. /phase-walkthrough 3); defaults to the most-recently-completed phase. Use when the user wants a guided tour of a phase's work, a refresher on what each §N.x section does, or a structured pre-gate review.
allowed-tools: [Read, Bash, Grep]
---

# /phase-walkthrough [N]

A variant of `/walkthrough` adapted for **completed, committed, multi-session work** instead of the current session's edits. The user is reviewing a finished pipeline phase — often on a small screen (phone over SSH). Walk them through it one logical unit at a time, pausing for input between each.

This is the natural companion to a **manual review gate** (CLAUDE.md §9 gates fall at the end of Phases 2, 4, and 7): it surfaces what each unit does, what it emits, and the decisions/gotchas worth a second look before any generated artifact lands downstream.

## Step 0 — Resolve the phase and orient

1. **Which phase?** The argument is the phase number (`/phase-walkthrough 3` → Phase 3). If absent, infer from `MEMORY.md → Current Phase` (the active or most-recently-completed phase) and state which one you picked. If it's genuinely ambiguous, ask before proceeding.
2. **Orient before you say anything.** Read, up front:
   - `PHASE{N}_PLAN.md` if it exists — its `§N.x` task sections **are** the chunk list, and its "Verification — exit gate" section drives the `gate` view.
   - `MEMORY.md` — Key File Notes (your richest source for chunk summaries; lean on it), Decisions Made, Open Questions, Last Session Summary.
   - `git log --oneline --grep "Phase {N}"` (or `-15` and eyeball) so summaries match what's actually committed.
   - The phase's source tree (see the source map below), to confirm the live modules match the plan.

Do not invent work that isn't in the plan, commits, or modules. If asked about something outside this phase, exit the walkthrough and answer normally.

## Phase source map

Where each phase's material lives. **Trust the live tree / plan over this table if they diverge** — it's a starting pointer, not gospel.

| Phase | Plan | Primary modules | Key emitted / derived artifacts |
|---|---|---|---|
| 2 — PBS data | `PHASE2_PLAN.md` | `src/rpg2gba/pbs_converter/` | `output/uranium-build/` C tables; `reference/uranium_id_map.json` |
| 3 — Map deserialization | `PHASE3_PLAN.md` | `src/rpg2gba/map_deserializer/`, `rxdata_deserializer/deserialize.rb` | `output/uranium-build/maps/`; `reference/rgss_event_commands.md`; switch/var sidecars |
| 4 — Conversion agent | *(TBD)* | `src/rpg2gba/conversion_agent/` | `.pory` files; flag registry; unhandled queue |
| 5 — Map/tileset | *(TBD)* | `src/rpg2gba/tileset_converter/` | Porymap maps + tilesets |
| 6 — Nuclear engine | *(TBD)* | the `pokeemerald-expansion` fork | custom C engine features |

## Step 1 — Build the chunk list

Derive the chunks for phase N. **Each chunk is one coherent unit of intent** — a converter/module plus its tests and its output, not a single file or commit.

1. **If `PHASE{N}_PLAN.md` exists:** its `§N.x` per-task sections are the chunks, in order (plus a §N.0 "scaffolding / shared helpers" chunk if the phase has one). Cross-check each against the live module tree.
2. **Otherwise:** group the phase's commits + modules into logical units yourself — one per module or feature — in dependency order.

Always reconcile against the live tree. If a module was renamed, added, or merged since the plan was written, trust the tree and adjust the list.

## Step 2 — Send the overview

First message is the numbered title list only — **no summaries**:

```
Phase {N} walkthrough — {T} units (all committed, working tree clean):

1. §{N}.0 scaffolding + shared helpers
2. §{N}.1 …
...
{T}. §{N}.x …

Reply `next` to start, `goto K` to jump, or `gate` for the review-gate view.
```

Then **stop and wait.** Do not begin chunk 1 in the same message.

## Step 3 — Walk through chunks

For each chunk, send a **summary only** — no code by default. Aim for ~5 lines max (small screen). Shape it as:

- **Input** — what it consumes (which `.dat`/`.rxdata`/JSON, what format), one phrase.
- **Output** — what it emits (C, intermediate JSON, reference doc) and any source-of-truth constants/IDs it mints.
- **The catch** — the one gotcha, deferral, fidelity decision, or fail-loud assertion worth knowing. Pull it from MEMORY Key File Notes / Decisions / Open Questions.

End every chunk with the affordance line (T = total chunks):

```
[chunk M of T] — next · show code · explain · decisions · goto K · gate · done
```

Then **stop and wait.** Never auto-advance.

## Step 4 — Handle replies

| Reply | Action |
|---|---|
| `next` / `n` / Enter | Advance to next chunk |
| `back` / `b` | Previous chunk |
| `goto K` / `K` | Jump to chunk K |
| `skip` | Advance, mark skipped in your mental state |
| `show code` / `code` | Read the relevant module from the phase's source dir and show the smallest snippet that conveys the work (the emit/parse/shape function, not the whole file). Stay on the chunk. |
| `decisions` | Surface the Decisions Made / Open Questions entries tied to this chunk. Stay on the chunk. |
| `explain` / `why` | Deeper reasoning: why this format, what was reconciled against the fork/contract, alternatives rejected. Stay on the chunk. |
| `gate` | Switch to the review-gate view (see below). |
| `done` / `q` | End the walkthrough. |
| Anything else | Treat as a freeform question about the current chunk; answer, then re-show the affordance line. |

When showing code, prefer the actual file over memory — the work is committed, so `Read` the module or `git show <sha>:<path>`. Keep snippets phone-sized.

## The `gate` view

The user may be driving a review with this walkthrough. On `gate`, step out of the per-chunk flow and present the phase's gate/exit view, sourced from `PHASE{N}_PLAN.md`'s "Verification — exit gate" section and MEMORY:

- **First, say whether this phase is a hard gate.** CLAUDE.md §9 hard gates are **Phases 2, 4, and 7** — those require the user to stop before anything propagates. Other phases (3, 5, 6, 8) have only the plan's self-administered exit gate; say so plainly so the user knows whether they're blocking anything.
- **Exit-gate checklist (Vx items)** — walk the plan's verification list: which are done (tests/idempotence/build) and which remain (usually user spot-checks or a downstream build). Mark each.
- **Worklists / deferral buckets** — anything the phase pushed downstream: `reference/uranium_id_map.json` `needs_engine`, per-converter `intermediate/*_codes.json`, the command/script-call inventory, etc.
- **Inventory / coverage** — the phase's "everything accounted for" artifact (e.g. `reference/uranium_dat_inventory.md` CONVERTED/STRIP/DEFER; or the command-code coverage guard).
- **Open decisions** — any MEMORY Open Questions awaiting the user's call that belong to this phase.
- **Spot-checks** — offer to pull representative generated artifacts (a Nuclear species record, a trainer party, an encounter table, a deserialized map's events) so the user can eyeball real output.
- **Still blocked** — note anything that can't be verified yet (e.g. a fork build needing devkitARM).

After the gate view, offer to return to the walkthrough (`goto K`) or end.

## Style notes

- No emojis. No raw `git diff` / tool dumps without summarizing first.
- Do not summarize at the end — on `done` or last-chunk + `next`, say "Done. {T} units reviewed." and stop.
- This skill reviews **committed** work; it does not modify code. If a reply requires a change, exit the walkthrough and address it as a normal edit.
- The structure is identical across phases — only the source material (plan, commits, modules) changes per phase. Re-source it every time from Step 0; never reuse a stale chunk list from a previous phase.
