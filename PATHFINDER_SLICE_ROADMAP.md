# Pathfinder Slice Roadmap

> **Status:** active plan (2026-06-15). Supersedes nothing — it *re-sequences*
> existing work. Authoritative companions: `ROADMAP.md` (what), `PHASE5_PLAN.md`
> (the Phase-5 §5.1–§5.6 assignment briefs + resolved Q1–Q5), `MEMORY.md`
> (Current Phase → STRATEGY PIVOT). When this conflicts with `PHASE5_PLAN.md` on
> *how*, this file wins **for the slice only**; the corpus-wide plan stays as
> written in `PHASE5_PLAN.md`.

---

## Why this exists

The horizontal Phase-4 bulk run produces `.pory` we cannot validate until Phase 7.
The per-file Poryscript compile-gate is weak (passes unknown/bare commands through
raw; dup-labels and wrong-but-defined-elsewhere constants only surface at
assembly). We have already found **two** compile-clean-but-broken classes — wrong
Uranium item constants and mistagged dispositions (cave darkness tagged "needs C"
when it is a map-header field). Spending ~3 months of budget generating 199 maps
of un-validatable output is the exact "cheap-early / expensive-late" trap the
roadmap warns against.

**The fix is a vertical slice with a real build+boot gate.** Drive ONE play-order
slice end-to-end (events → geometry → engine → `make modern` → boot in mGBA) so
systematic-error classes surface at **3 maps, not 199**. This is the first step of
*every* candidate global strategy, so it is done regardless of what we choose next.

### What this is NOT

- **Not a Phase-4 restart.** All Phase-4 machinery — deterministic classifiers,
  `flag_registry`, orchestrator, frozen Opus prompt, memo, checkpoints — is reused
  unchanged. Only the *order* of maps changes, plus a build+boot gate is added.
- **Not a commitment to map-by-map for all 199.** That throughput decision
  (build-cycle × 199, tileset-authoring × 60) is **deferred** until this slice
  measures the real per-map cost. See "Decision deferred" at the bottom.

---

## The slice

Play-order, three maps, chosen because they are the literal Phase-0 success
criterion *"player can leave the starting town"*:

| Map | Name | Tileset | Size | Role |
|---|---|---|---|---|
| **049** | `\PN's house` (ground floor) | 19 (interior) | 30×15 | **player spawn** (`URANIUM_START_MAP=49`, x/y 7/7); has the street door → town and stairs → 048 (confirmed S1) |
| **048** | `\PN's house` (upper floor) | 19 (interior) | 20×15 | upstairs; reachable only from 049 via stairs (its only warp) |
| **032** | **Moki Town** | 22 (town outdoor) | 72×64 | walk, signs, NPCs; 52 events, 9 warps (5 out-of-slice) |

> S1 corrected an earlier guess: the **street door is on 049, not 048** — 049 is the
> ground floor where the player spawns. See `PATHFINDER_FINDINGS.md` for the full
> warp topology + disposition table.

Only **two Uranium tilesets** (19, 22) need substitution tables — a deliberately
tiny hand-authoring surface. Buildings in Moki Town that we do not include in v1
(lab, marts, other houses) have their warps **walled or stubbed** (see S5); the
first route exit may dump to a stub or be walled. The goal is boot + spawn + walk
+ read a sign + talk to an NPC + use one interior warp — not full-town coverage.

---

## Principles

1. **Reuse, don't rebuild.** Every step below maps onto an existing module or
   pipeline stage. New code is confined to the Phase-5 geometry modules that were
   always going to be written.
2. **Boot is the gate.** A step is not "done" until its output survives into a ROM
   that boots in mGBA and the slice is walkable. The compile-gate is necessary,
   not sufficient.
3. **Play-order, not id-order.** The bulk run did Maps 001–007; the player starts
   at 049. We process in the order a player experiences.
4. **Approach A tilesets** (reuse Hoenn metatiles; user-approved 2026-06-15).
   Maps render Hoenn-styled. No new tileset art in this slice.
5. **Fail loud, idempotent, one source of truth** — unchanged from CLAUDE.md §4.
6. **Do not touch frozen Phase-4 artifacts** (`prompts/`, the model,
   `uranium_script_calls.md` which feeds the frozen system prompt). Mistagged
   triage rationales are corrected *downstream here*, never in the prompt.

---

## The steps

| # | Step | Module / stage | New? | Deliverable | Plan |
|---|---|---|---|---|---|
| **S1** | Trace the slice warps | read-only analysis | — | exact neighbor/stub list for 49/48/32 | inline below |
| **S2** | **Tileset substitution** | `tileset_converter/tile_map.py` + `reference/tileset_map.json` | **yes — long pole** | loader/validator/lookup + tables for tilesets 19 & 22 | **`PATHFINDER_STEP2_TILE_MAP_PLAN.md`** |
| **S3** | **Map layout converter** | `tileset_converter/layout.py` | **yes — long pole** | `map.bin`/`border.bin`/`layouts.json` for 49/48/32 | **`PATHFINDER_STEP3_LAYOUT_PLAN.md`** |
| **S4** | Map constants | `tileset_converter/map_constants.py` | yes (small) | `MAP_*`/`LAYOUT_*`/`MAPSEC_*` for the 3 maps + alias header | inline below |
| **S5** | Map.json wiring | `tileset_converter/metadata_wiring.py` | yes | `map.json`: header, object/warp events, encounters, page dispatch | inline below |
| **S6** | Events → Poryscript | Phase-4 orchestrator (existing) | **reuse** | `.pory` for maps 49/48/32 | n/a (existing machinery) |
| **S7** | Move routes → static | `tileset_converter/move_routes.py` (degrade only) | yes (minimal) | NPCs placed static; cutscene fidelity deferred | inline below |
| **S8** | Mini Phase-7 assembly | manual + script | yes | artifacts dropped into fork, `make modern`, boot in mGBA | inline below |
| **S9** | Pathfinder log | `PATHFINDER_FINDINGS.md` (new) | yes | every systematic-error class, fed back to det. layers | inline below |

Phase-6 (engine) is intentionally **absent**: the starter town needs no Nuclear /
cave / bridge features. The cave-attribute path (`requires_flash`) is exercised by
a deliberately cave-containing **slice #2**, after this one boots.

---

### S1 — Trace the slice warps (read-only)

**Goal.** Know exactly which warp targets exist in maps 49/48/32 so S5 can wire
real warps and wall/stub the rest (no dangling `MAP_*`).

**Method.** For each of the three Phase-3 `MapNNN.json`, read every code-`201`
(Transfer Player) command in every event page; record `(target_map_id, x, y,
dir)`. Also note `pbCaveEntrance`/exits (expect none) and building-entrance warps
in Moki Town.

**Output.** A table in `PATHFINDER_FINDINGS.md`: each warp → keep / no-emit / wall.
**DONE (2026-06-15)** — see that file. Actual rule (data-derived): KEEP the five
in-slice warps (49↔48 stairs; **49↔32** street door + town side; the Letter
event's in-slice warps); **NO-EMIT** the four out-of-slice building doors
(Map050/064/065/172) so nothing references a missing map; **WALL** the three west
cave-exit tiles (→Map033, `pbCaveEntrance`) so the player can't leave the converted
area. Moki Town becomes a closed sandbox.

**Acceptance.** No warp in the emitted maps references a `MAP_*` outside {49,48,32}.
✓ (no-emit drops all out-of-slice references entirely; no stub map needed).

---

### S4 — Map constants  ·  `map_constants.py`

Implements the resolved **Q2**: readable `MAP_<NAME>` minted from `map_infos.json`,
reached from frozen `.pory` via an alias header `#define MAP_URANIUM_<N>
MAP_<NAME>`. For the slice:

- Mint `MAP_MOKI_TOWN` (32), `MAP_MOKI_TOWN_PLAYERS_HOUSE_1F` (**49**),
  `MAP_MOKI_TOWN_PLAYERS_HOUSE_2F` (**48**) — sanitize `\PN's house` → drop the
  `\PN` control code. Floor disambiguation comes from the **S1 warp topology**
  (049 has the street door → ground floor; 048 is upstairs), *not* the RMXP editor
  `order` field (which is just tree display order and would mislabel them).
  `LAYOUT_*` and `MAPSEC_MOKI_TOWN` likewise.
- Emit the alias header so any warp the Phase-4 pass wrote as `MAP_URANIUM_49`
  resolves.
- Persisted, idempotent (same id → same constant across runs).

**Acceptance.** Names are valid C identifiers, no collision with vanilla `MAP_*`,
every slice warp target resolves.

---

### S5 — Map.json wiring  ·  `metadata_wiring.py`

Assemble `output/uranium-build/porymap/maps/<Name>/map.json` for the 3 maps:

- **Header** from `intermediate/map_metadata.json` (music, weather, `map_type`:
  49/48 = `MAP_TYPE_INDOOR`, 32 = `MAP_TYPE_TOWN`). Player spawn (49 @ 7,7) wired
  via the metadata Home record.
- **Object events**: each Uranium event → one `object_event` at its `(x,y)`,
  `script` = the Phase-4 `.pory` dispatcher label (from S6). Local ids minted in
  event-id order (the one source of truth 5.5 also consumes).
- **Warp events** from S1's keep-list; walled warps emit no warp_event (the
  metatile collision blocks them); stubs warp to the stub map. S5 also supplies the
  **walkable-override set** (each kept warp's source coord) to S3's `convert_layout`
  so warp/door tiles are forced collision 0 — they read as blocked from source
  passage but must be steppable (S2 finding; see `PATHFINDER_FINDINGS.md`).
- **Encounters**: Moki Town has none typically (`encounter_list: []` in Map032);
  emit a table only if wild slots exist.
- **Page dispatch**: deterministic skeleton selecting which page's `.pory` body
  runs from the Phase-3 page `condition` (switch/var/self-switch gates). This is
  **build-agent work, not the conversion agent's** (CLAUDE.md §1).

**Acceptance.** Each event once at correct `(x,y)`; `script` labels match `.pory`
block names exactly; warps resolve.

---

### S6 — Events → Poryscript (existing Phase-4 machinery)

Run the orchestrator on **only** maps 49/48/32 (none are in the done-set 001–007).
Most events are dialogue / signs / self-switch / call-CE → deterministic
classifiers + a handful of Opus spawns. No new code; same frozen prompt, memo,
checkpoints, compile-gate. Output `.pory` into `output/uranium-build/scripts/`.

Command: the existing per-map run path (e.g. `convert-map --map-id 049`), three
maps. Budget: trivial (tens of spawns at most).

**Acceptance.** `.pory` for all three maps compile through Poryscript.

---

### S7 — Move routes → static (degrade only for v1)

Phase-4 queues every `209/210/509` move route as an `# UNHANDLED: move route`
breadcrumb (frozen behavior). Full translation is `move_routes.py` (§5.5) — **not**
done here. For the pathfinder, **degrade to static**: NPCs are placed at their
page coordinates with `movement_type = MOVEMENT_TYPE_FACE_<dir>` (or
`_WANDER_AROUND` where the page had autonomous `movement_type` — that is native,
not 209 work). Scripted cutscene routes (rival/mom walk-ons) are dropped to static
for v1 and remain in the queue as an audit trail. Fidelity returns with §5.5 after
boot.

**Acceptance.** No NPC blocks a required path by standing on it (cross-check with
S-reachability spot check); every dropped route still has a queue entry.

---

### S8 — Mini Phase-7 assembly + boot

The integration loop, pulled forward for one region. **Manual + a thin assembly
script** (`scripts/assemble_pathfinder.py`, new), because `pipeline.py phase5`
wiring is deferred (PHASE5_PLAN: wire pipeline last).

1. Copy Phase-2 generated C (already done) into the fork `src/data/` — once.
2. Copy slice `.pory` → fork `data/scripts/`; the alias header (S4) → an included
   header; `CommonEvents.pory` (already converted) for any `call CommonEvent_*`.
3. Copy slice layouts (`map.bin`/`border.bin` + the 3 `layouts.json` entries
   merged into the fork's `layouts.json`) and `map.json`s + `map_groups.json`
   membership for a new `gMapGroup_Moki`.
4. Set the new-game spawn to `MAP_MOKI_TOWN_PLAYERS_HOUSE_2F` (7,7) for the test
   (vanilla starts elsewhere; override `sNewGameMapData`-equivalent or warp on
   `NewGame`).
5. `cd $RPG2GBA_POKEEMERALD && make -j16 modern`. Resolve build errors (expect
   name mismatches — the systematic classes we are hunting).
6. Boot `pokeemerald.gba` in **mGBA** on the desktop.

**Acceptance (the real gate).** ROM boots; new game starts in the bedroom; player
walks; warps 2F→1F→Moki Town work; at least one sign and one NPC dialogue fire; no
crash in the first few minutes.

---

### S9 — Pathfinder log  ·  `PATHFINDER_FINDINGS.md` (new)

Capture **every** systematic-error class the slice surfaces (not one-offs):
constant-name mismatches, collision/walkability errors from Q3/Q4 substitution,
dispatch bugs, assembly failures, prompt/triage tags proven wrong. Each gets a
disposition: fix in a deterministic layer (preferred), fix in triage planning, or
defer with a reason. This log is the actual product of the pathfinder — it is what
makes the global sequencing decision an informed one.

---

## Pathfinder exit criteria

- [ ] S2: `tile_map.py` loads + validates `tileset_map.json`; tilesets 19 & 22
      fully mapped (every tile id used by maps 49/48/32 resolves, fail-loud proven).
- [ ] S3: `layout.py` emits byte-identical `map.bin`/`border.bin` for the 3 maps;
      round-trips; golden test passes.
- [ ] S4: constants mint + alias header resolves every slice warp.
- [ ] S5: three `map.json`s with events at correct coords, warps wired/walled.
- [ ] S6: three `.pory` compile.
- [ ] S8: **ROM boots in mGBA; the slice is walkable per the S8 acceptance.**
- [ ] S9: findings logged with dispositions.

---

## Decision deferred (revisit after boot)

Once the slice boots and S9 has the per-map cost + error classes, decide the global
strategy with data:

- **(a) map-by-map for all 199** — if per-map cost is low and errors are local.
- **(b) fix deterministic layers, then resume horizontal** — if errors are
  systematic and cheaply fixed centrally (likely, given what we have already seen).
- **(c) hybrid** — vertical for geometry-critical regions (caves/gyms), horizontal
  for routine maps.

Do **not** pre-commit. The slice exists to make this choice cheap.
