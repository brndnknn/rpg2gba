# Pathfinder Slice Build Guide

> **What this is:** The first end-to-end assembly run of the rpg2gba pipeline —
> three maps (spawn house 1F/2F + Moki Town) compiled into a real `pokeemerald.gba`
> that boots and is walkable in mGBA. This is the S8 gate from `PATHFINDER_SLICE_ROADMAP.md`.

---

## Prerequisites — confirm these before running

| Check | How to verify |
|---|---|
| S1–S7 all done | `output/uranium-build/porymap/map_constants.json` exists + has keys 32/48/49 |
| S6 complete | `output/uranium-build/checkpoints/slice_run_state.json` → `"status": "complete"` |
| Staged scripts up to date | `output/uranium-build/staging/scripts/Map049.pory` (etc.) exist — if not, run `stage_slice_scripts.py --write` first |
| Fork is clean | `git -C $RPG2GBA_POKEEMERALD status` — no uncommitted changes you care about (the assembler writes into it) |
| `poryscript` on PATH | `poryscript --version` |
| devkitARM active | `arm-none-eabi-gcc --version` |

If the staging scripts are missing or stale, re-run staging first:

```bash
PYTHONPATH=src python scripts/stage_slice_scripts.py --write
```

This is safe to re-run; it regenerates `map.json` and the staged `.pory` files and
confirms the existence check passes (every referenced label is defined exactly once).
A non-zero exit means a label problem — fix before proceeding.

---

## The two-step run

### Step 1 — dry run (read-only sanity check)

```bash
PYTHONPATH=src python scripts/assemble_pathfinder.py --dry-run
```

Reports every file that would be written to the fork without touching anything.
Check the output for unexpected paths or missing source files. Typical output is
~20 lines: layout conversion for 3 maps, compilation of `Map049/048/032.pory` +
`CommonEvents.pory`, copies of `map.json`s + `.bin` files, upsert of
`layouts.json`, `map_groups.json` addition, `uranium_map_aliases.h`,
`uranium_flags.h`, and the `event_scripts.s` include block.

### Step 2 — live assembly

```bash
PYTHONPATH=src python scripts/assemble_pathfinder.py
```

What it does, in order:

1. **S8b — layout conversion.** Calls `convert_layout` for maps 49/48/32 using
   `reference/tileset_map.json` + the tilesets oracle. Writes `map.bin` +
   `border.bin` to `output/uranium-build/staging/layouts/<MapDir>/`.  Warp-source
   coords (the door tiles) are forced walkable: `(10,11)` and `(12,3)` on map 049,
   `(3,3)` on 048, `(28,31)` on 032.

2. **S8c — fork assembly.**
   - Compiles each map's staged `.pory` + optional dispatcher → fork
     `data/maps/<MapDir>/scripts.inc` via poryscript (fails loud on error).
   - Compiles `CommonEvents.pory` → fork `data/scripts/CommonEvents.inc`.
   - Copies `map.json` for each map → fork `data/maps/<MapDir>/map.json`.
   - Copies `.bin` layout files → fork `data/layouts/<MapDir>/`.
   - Upserts the 3 layout entries into fork `data/layouts/layouts.json`.
   - Adds `gMapGroup_Uranium` (idempotent) to fork `data/maps/map_groups.json`.
   - Writes `data/scripts/uranium_map_aliases.h` (resolves `MAP_URANIUM_32/48/49`).
   - Writes `data/scripts/uranium_flags.h` (flag/var/self-switch/temp-switch
     addresses from the registry, base offsets hardcoded at 0x1000/0x1100/0x40D0/0x14).
   - Appends a sentinel-guarded `#include`/`.include` block to
     `data/event_scripts.s` (idempotent — replaces the block if already present).

### Step 3 — build

```bash
cd $RPG2GBA_POKEEMERALD && make -j$(nproc) modern
```

Expect 1–3 minutes. If it errors, see **Troubleshooting** below.

### Step 4 — boot

Open `$RPG2GBA_POKEEMERALD/pokeemerald.gba` in mGBA. Start a new game.

---

## What's included in this build

| Map | Uranium ID | pokeemerald constant | What you get |
|---|---|---|---|
| Player's house 1F | 049 | `MAP_MOKI_TOWN_PLAYERS_HOUSE_1F` | Player spawn (7,7); stairs to 2F; street door to town |
| Player's house 2F | 048 | `MAP_MOKI_TOWN_PLAYERS_HOUSE_2F` | Upstairs; stairs back to 1F |
| Moki Town | 032 | `MAP_MOKI_TOWN` | Full 72×64 outdoor town; all 52 events wired |

**Events present:**
- Signs, NPCs with dialogue (converted by the Phase-4 orchestrator)
- Self-switch-gated events (talk-once, etc.)
- In-slice warps: 1F ↔ 2F (stairs) + 1F ↔ Moki Town (street door) + town side

**Tilesets:** two substitution tables only (ts19 interior → `gTileset_Building` +
`gTileset_BrendansMaysHouse`; ts22 town → `gTileset_General` + `gTileset_Petalburg`).
Maps render Hoenn-styled (Approach A, no new art).

---

## What's NOT included

- **Out-of-slice buildings in Moki Town** (lab, other houses, marts) — their warp
  events are dropped from `map.json`; the door tiles read as blocked collision, so
  the player simply can't enter them. No stub map needed.
- **West cave exit** (→ Map033 `pbCaveEntrance`) — walled at the collision level,
  no warp_event emitted.
- **Move routes / NPC movement** — Phase-4 queued all 209 commands; NPCs in this
  build are static objects placed at their page coordinate, facing their default
  direction. The queue entries remain for `§5.5` later.
- **Starter cutscene** (Map032 EV009, Prof. Bamb'o) — events are present and
  dialogue fires, but the scripted walk sequence, `pbGet(151)` starter selection,
  Pokédex grant, and `pbPhoneRegisterNPC` are Phase-4 queue entries (`UNHANDLED`
  breadcrumbs in the `.pory`).
- **Globally-gated events** (those controlled by `$game_switches[SW1_125]`,
  `VAR_101`, etc.) — the global flag/var names weren't minted in time for dispatch;
  affected events (`Theo`, `Bambo`, rival actors, `Luz` sprites) are wired as
  static objects (`script "0x0"`, i.e. no interaction). Queue entries remain.
- **Phase-6 engine features** — Rock Smash, `pbCaveEntrance`, `pbShowMap`,
  `pbTrainerPC`, `displayNinjaLetter` — these are UNHANDLED breadcrumbs; the events
  exist but do nothing useful.
- **Wild encounters** — Moki Town has none; Map049/048 are indoors. Nothing to
  configure.
- **Maps 001–007 and everything else** — the bulk run (7/199 maps done) is paused;
  none of those maps are assembled here.

---

## What success looks like (S8 acceptance)

The boot gate passes when all of the following are true:

- [ ] `make modern` exits 0 (no build errors, no link errors)
- [ ] ROM boots in mGBA — title screen + new game without crash
- [ ] New game starts in the **bedroom** (map 049, spawn tile 7,7)
- [ ] Player can walk around the room without falling through floor or getting stuck
- [ ] **Stairs work:** walk up the stairs → 2F; walk down → back to 1F
- [ ] **Street door works:** walk through the front door → Moki Town; walk to the
      house door in town → back to 1F
- [ ] At least one **sign** in Moki Town shows text on interaction
- [ ] At least one **NPC** in Moki Town shows dialogue on interaction
- [ ] No crash in the first few minutes of walking around

The visual tileset won't look like Uranium (it's Hoenn geometry). That is expected
and is not a failure.

---

## What comes next if it works

1. **Log S9 findings** in `PATHFINDER_FINDINGS.md` — every systematic error class
   the build surfaced (constant mismatches, collision errors, label gaps, etc.) with
   dispositions: fix deterministically, fix in triage, or defer.

2. **Decisions D/E** (pending user input):
   - (D) Bless the two deferred flag mappings (`runningShoes=true` →
     `FLAG_SYS_B_DASH`? ; `$Trainer.pokedex=true` → `FLAG_SYS_POKEDEX_GET`?)
   - (E) Fidelity scope for the Prof. Bamb'o starter cutscene (Map032 EV009) —
     full replication vs minimal give-starter + Pokédex.

3. **Global strategy decision** — with per-map cost and error classes measured,
   decide between: (a) map-by-map for all 199, (b) fix deterministic layers then
   resume horizontal, or (c) hybrid. See `PATHFINDER_SLICE_ROADMAP.md` "Decision
   deferred."

4. **Move routes (`§5.5`)** — now that the boot loop is proven, wire the 209
   command translation layer so NPCs animate and cutscenes work in slice #2.

5. **Slice #2** — a cave-containing map to exercise the `requires_flash` path and
   validate collision/reachability on a different tileset.

---

## Troubleshooting

**`poryscript failed on Map032`** — re-run `stage_slice_scripts.py --write` and
check for "existence check FAIL" output. An undefined label means a dispatcher or
CommonEvents ref is missing from the staged set.

**`make modern` undefined symbol `MAP_URANIUM_*`** — check that
`data/scripts/uranium_map_aliases.h` was written and that `event_scripts.s`
has the `#include` line for it inside the sentinel block.

**`make modern` undefined symbol `FLAG_*` or `VAR_*`** — `uranium_flags.h` not
included, or the flag base addresses overlap vanilla. Check `event_scripts.s` for
the sentinel block and the `#include "data/scripts/uranium_flags.h"` line.

**`make modern` duplicate label** — a `CommonEvents.pory` block name collides with
a vanilla script. The existence check in `stage_slice_scripts.py` catches
duplicates *within* the slice set; vanilla labels are only checked at link time.
Rename the offending CommonEvent block (it won't affect memo — label names are
internal).

**ROM boots but map looks wrong / player walks through walls** — a tileset bucket
mapping is wrong. Check `reference/tileset_map.json` and cross-reference
`scripts/pathfinder_collision_preview.py` output for the failing map.

**ROM boots but warp doesn't fire** — the warp source tile was mapped to a blocked
metatile and its coord wasn't in `WALKABLE_OVERRIDES`. Add the coord to the dict
in `assemble_pathfinder.py` and re-run from Step 1.
