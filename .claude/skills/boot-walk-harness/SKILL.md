---
name: boot-walk-harness
description: >
  Set up a test harness so a new part of the game can be boot-walked without
  replaying everything to reach it. Use when the user wants to walk new
  content, asks for a ROM positioned at a specific point, says "set up a
  harness", or invokes /boot-walk-harness. Covers both paths: seeding from a
  played chapter's save blob (default) and the new_game.c rung (escape hatch
  for states the game cannot produce). Guides the LEAD agent; advisory on
  method — CLAUDE.md §9/§10 gates still apply.
---

# boot-walk-harness — put the player at the frontier, cheaply

Goal: the user boots a ROM and is **already standing in the content they
need to walk**. No replaying Moki to reach Route 1.

Two mechanisms exist. Pick with the decision below; do not default to the
one that needs an engine rebuild.

## Phase 0 — Pick the mechanism

Ask one question of the data, not of the user: **is the target reachable by
beats that already exist?**

```
python -m rpg2gba.playtest list                 # chapters + their beats (gen suite)
python -m rpg2gba.playtest seeds --chapter <ch> --suite gen --output output/playtest-gen --engine engine  # states on THIS build
```

| Situation | Mechanism |
|---|---|
| Target sits at/behind an existing beat | **Seed blob** — `walk --at-beat` |
| Target is just past the end of a converted chapter | **Seed blob** — `walk --at-end` |
| Target is deep in content with no beats yet | **Generate the beats first**, then seed |
| State the game cannot produce (test party, badge/HM grant, forced loss path) | **`new_game.c` rung** |

The blob path is strongly preferred: no rebuild, and the state is *real* —
reached by actually playing the events, so it cannot diverge from what the
game produces. A hand-written rung is a guess about which flags matter, and
that guess has been wrong before (a skipped scene left an NPC misplaced,
needing a manual `TryMoveObjectEventToMapCoords` to paper over).

## Phase 1 — Seed-blob path (default)

The runner drops a seed blob at **every beat boundary** during a run, keyed
to the ROM's sha256. One green run arms every start point in the chapter.

```bash
# 1. produce the blobs (also the regression check — must be green).
#    --from-beat X (iteration only) needs that chapter's own green blobs.
python -m rpg2gba.playtest run --chapter <ch> --suite gen --output output/playtest-gen --engine engine

# 2. what states does this build have?
python -m rpg2gba.playtest seeds --chapter <ch> --suite gen --output output/playtest-gen --engine engine

# 3. build the walk ROM
python -m rpg2gba.playtest walk --chapter <ch> --at-beat B10 --suite gen --output output/playtest-gen --engine engine
python -m rpg2gba.playtest walk --chapter <ch> --at-end --suite gen --output output/playtest-gen --engine engine
```

Semantics that bite if misread:

- A blob filed under `B10` holds the state **before B10 runs** — it is the
  seed you would start B10 from.
- `--at-end` prefers the stamped chapter-complete ROM, falling back to the
  furthest beat seed.
- Verification is **on by default** and boots the result with a deliberately
  foreign `.sav` paired. That is not paranoia: on 2026-08-01 save residue on
  the device silently shadowed a stamped ROM and it booted somewhere else
  entirely. Do not pass `--no-verify` for anything going to the user.
- **Every blob dies on every ROM rebuild**, by design. A stale blob is
  refused loudly with both hashes; the fix is always a fresh green run, never
  a hand-edit of the metadata.

Deliver with `tailscale file cp <rom> iphone182:`.

## Phase 2 — No beats yet? Generate them, don't reach for C

New content with no beats is the common case at the frontier, and the answer
is to extend the chapter, because beats pay off twice: they seed the walk
ROM *and* they become the regression floor that stops the user re-walking
this area after every later fix. Nobody hand-writes beats any more — suites
are generated.

1. Chapter doc first (`reference/chapters/NN-*.md`) and the chapter entry in
   `reference/chapters.json`, rxdata-first with the wiki as cross-check.
2. Generate: `python -m rpg2gba.beat_gen generate --chapter CHnn`. Output
   lands in `output/beats/` (the module, `CHnn.review.md`, the route json).
3. **Operator gate (CLAUDE.md §9):** the user reads and approves
   `CHnn.review.md` — the only human-visible record of the route solver's
   picks. Only then commit the module as
   `src/rpg2gba/playtest/chapters_gen/chNN.py`. Do not commit before approval.
4. If a beat is wrong, fix the generator (`src/rpg2gba/beat_gen/`) or its
   inputs and regenerate — never hand-edit the generated module.
5. Historical note: the old hand-authoring traps (append-vs-insert order,
   dead APPROACH constants, `at=` not moving the player) lived in the deleted
   `playtest/chapters/*.py` suites. Beat order and approach tiles are now the
   route solver's job; if a generated beat shows those symptoms, that is a
   `beat_gen` bug. One trap still applies: the LAST beat sets the chapter's
   end state, which must leave field controls released or the
   chapter-complete stamp fails (`stamp.dump_save_blocks` refuses a
   mid-script state) and takes the walk ROM with it.

Only after the chapter runs green do you have seeds.

## Phase 3 — `new_game.c` rung (escape hatch)

Use only for states the game cannot produce. Full recipe — the
`VAR_QUEST_LOG` ladder, which flags/vars each rung implies, the
`WarpToTruck` spawn swap, the party-must-be-real rule — is preserved in
`ROM_TEST_DEV.md` under **"new_game.c debug-harness re-arm technique"**.
Read it there; do not reconstruct it from memory.

Three rules that are not optional:

- Fence the block with `URANIUM PATHFINDER SLICE`-style sentinels.
- Only one `SetWarpDestination` call may be active at a time.
- **Disable the rung and revert the spawn before running the chapter
  suite.** An armed harness defeats the suite's fresh-start guarantee by
  construction — this has already produced one confusing red run.

A rebuild is a §10 ask-first item. Get it before starting.

## Phase 4 — Hand off

Whichever path produced the ROM:

- The suite must be **green on that exact build** before anything is
  taildropped. No exceptions — a walk ROM whose build fails the suite wastes
  the user's walk on a known bug.
- Send the contact sheet with it (`output/playtest-gen/review/<ch>-sheet.png`; built as `<--output>/review/`, so `output/playtest/review/` if `--output` is omitted).
  It covers the by-eye categories by scanning images instead of playing, and
  you can read it too — that is the only mechanism here that catches "logic
  out what's on screen and something is wrong."
- Say plainly what the ROM is positioned at, what the suite covered, and
  what is left for the user's eyes. Automation replaces the *re-walk*; the
  first walk of new content and every by-eye category stay §9 manual.

## Do not

- Hand-edit blob metadata to dodge a hash refusal.
- Ship a walk ROM with `--no-verify`.
- Reach for a `new_game.c` rung because generating/regenerating beats felt like more work —
  the beats are the deliverable that stops the next ten re-walks.
- Call a chapter walkable while deferring art. Playable includes real
  quantized art (§9).
