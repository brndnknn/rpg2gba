# Gated doors collapse into unconditional warps (`classify_event`)

**Found:** 2026-07-26, by the chapter playtest harness failing Moki beat **B2**.
**Status:** **FIXED 2026-07-26** (converter + tests + re-staged). ROM rebuild and
a B2 re-run still pending — see §7.
**Owner file:** `src/rpg2gba/tileset_converter/metadata_wiring.py` (`classify_event`).

---

## 1. The symptom

`python -m rpg2gba.playtest run --chapter moki` fails at B2 ("Leaving 1F before
talking to Auntie is blocked"), twice in a row, classified `fail` not `flake`:

```
B2: expected map MAP_MOKI_TOWN_PLAYERS_HOUSE_1F but map_location()
    reads group=75 num=2
```

The player walks straight out of the player's house before talking to Auntie.
Bundle: `output/playtest/bundles/moki/20260725T183643525888Z/`.

**The test is right and the ROM is wrong** — see §2. This is a converter bug,
not a harness bug and not a bad assertion.

## 2. What Uranium actually does

`output/uranium-build/maps/Map049.json`, event id 1 (`EV002`), at **(10,11)** —
the front-door tile. Four pages, **all trigger 1 (player-touch)**:

| Page | Condition | Commands |
|---|---|---|
| 0 | none (fallback) | `101` `"I'd better say goodbye to Auntie first."` → `209` move route (shove player back) |
| 1 | Switch **52** | `250` "Exit Door" SFX → `223` fade → `106` wait → **`201` Transfer Player → map 32 (28,31)** → `223` restore |
| 2 | Switch 125 | `101` Kellyn letter line → `209` move route (turn back) |
| 3 | Switch 125 + self-switch A | same transfer as page 1 |

RMXP activates the **highest-index satisfied page**. Page 0 has no condition, so
with Switch 52 off the door refuses. Switch 52 is named **`Mum`**
(`reference/uranium_switches.json`), and it is set by Auntie's own conversation.

So the gate is real and correct: **you cannot leave Map049 until Auntie's talk
sets Switch 52.**

**Precision worth keeping:** the gate is `FLAG_MUM`, *not* the running-shoes
flag. Auntie's page-1 script sets both — `setflag FLAG_SYS_B_DASH` and
`setflag FLAG_MUM` (staged `MokiTownPlayersHouse1F/scripts.inc`) — so "talk to
Auntie" gates both, but the door reads `FLAG_MUM`. **The Auntie side of the
conversion is correct**; only the door lost its gate.

## 3. Root cause

```python
# metadata_wiring.py:430
def classify_event(event, slice_ids):
    transfers = _event_transfers(event)          # scans ALL pages
    if transfers:
        targets = {t[0] for t in transfers}
        if any(t not in slice_ids for t in targets):
            return ("skip", "out-of-slice warp")
        if event["pages"][0].get("trigger") == TRIGGER_PLAYER_TOUCH:
            dest_uid, dx, dy, ddir = transfers[0]
            return ("warp", WarpSpec(event["x"], event["y"], dest_uid, dx, dy, ddir))
    return ("object", None)
```

If **any** page carries a `201` and page 0 is player-touch, the entire event
becomes one unconditional `warp_event`, and the object_event is dropped — the
docstring says so outright: *"the object_event is dropped to avoid a double
warp; its .pory body goes unreferenced."*

For EV002 that means:

- the `WarpSpec` is built from `transfers[0]`, i.e. **page 1's** transfer;
- pages 0 and 2 — the two refusal pages — are **silently discarded**;
- `Map049_EV002` appears **8×** in `output/uranium-build/scripts/Map049.pory`
  and **0×** in `output/uranium-build/staging/scripts/Map049.pory` and in the
  staged `MokiTownPlayersHouse1F/scripts.inc`;
- staged `MokiTownPlayersHouse1F/map.json` has an unconditional
  `warp_events[0] = {x:10, y:11 → MAP_MOKI_TOWN}` and an **empty**
  `coord_events` array.

The classifier's assumption — "player-touch + contains a transfer ⇒ plain door"
— holds only when *every* page transfers. It never checks which page the
transfer is on, nor whether the other pages are gates.

This is a **§4.5 fail-loud violation**: pages are dropped silently, with a
comment that rationalizes the drop.

## 4. Blast radius (measured)

Census method: for every event, keep those where page 0 is player-touch, at
least one page has a `201`, all targets are in scope (so `classify_event` would
say "warp" rather than "skip"), and **at least one page has no transfer** (that
page is a gate whose behavior is lost). Script:
`scratchpad/gated_door_census.py` (method reproduced above; scratchpad is not
committed).

**Slice 1 — 7 events:**

| Map | Event | Tile | Pages | Gate pages | Gate shows dialogue |
|---|---|---|---|---|---|
| 049 | EV002 | (10,11) | 4 | 0, 2 | **yes, both** |
| 050 | EV001 | (14,19) | 2 | 0 | **yes** |
| 032 | EV003 | (17,11) | 2 | 1 | no |
| 032 | EV005 | (28,31) | 2 | 1 | no |
| 032 | EV006 | (43,31) | 2 | 1 | no |
| 032 | EV007 | (24,42) | 2 | 1 | no |
| 032 | EV017 | (56,42) | 2 | 1 | no |

- **Map050 EV001 is the lab exit** — the `VAR_QUEST_LOG >= 1` gate that
  `reference/chapters/01-moki.md` beat **B10** describes. It is currently
  ungated too. B10 as written walks out *after* the gate is satisfied, so it
  would pass green while the gate is missing — a coverage hole, and a second
  reason to add negative beats for gated doors.
- The five Map032 entries are the inverse shape: page 0 transfers, page 1 is a
  silent no-op page, i.e. warps that should switch **off** under a condition and
  are currently always on.

**Corpus-wide: 341 events across 75 maps**, of which **22 have a gate page
carrying dialogue** — player-visible refusals that never fire.

## 5. The fix as built (2026-07-26)

Four changes in `metadata_wiring.py`, plus tests.

**(1) `classify_event` — collapse only when every PLAYER-TOUCH page transfers.**
The first draft of this rule said "every page", which was too broad: it
reclassified Moki Town's five house doors, whose second page is a **switch-22
autorun cutscene** (trigger 3), not a door gate. An autorun page reaches the
player through ON_FRAME_TABLE and does not make the door conditional. Narrowing
to player-touch pages leaves those five as plain warps (verified) and catches
exactly the two real gated doors.

**(2) `build_object_events` — a blank player-touch event that carries a transfer
emits a `coord_event` instead of dropping as `blank_trigger1`.** Blank
player-touch events with no transfer anywhere are the original inert shape and
still drop, so the change is scoped to gated doors.

**(3) No relocation for gated doors.** The coord-event path normally relocates
off a non-standable tile to its standable neighbours, because RMXP touch
triggers fire on a BUMP while porymap coord_events fire on STAND. That is wrong
here: RMXP calls the door cell impassable, but the warp-override pass forces
exactly these cells walkable with the tileset's door metatile
(`MB_NON_ANIMATED_DOOR`, collision 0). Relocating put Map049's gate on the
approach tile (10,10) — firing the refusal on merely walking past the door — and
put Map050's gate on (14,18), colliding with the arrival warp there. Gated doors
now keep their own cell.

**(4) `ObjectBuildResult.gated_door_cells` → unioned into the override set
`build_slice_maps` returns.** A gated door has no warp_event but still needs the
door metatile + collision 0, or the player cannot step into the doorway to trip
the gate. This also keeps the computed set equal to the hand-maintained
`assemble_pathfinder.WARP_OVERRIDES` mirror (`49: {(10,11), (12,3)}`,
`50: {(14,19)}`) — without it the two silently diverged, which would have
quietly re-broken the doors the next time anyone reconciled them.

### Verified output

Re-staged and re-assembled clean (both the fork-index and text gates passed):

| Map | Gate cell | Emitted | Warp on that tile |
|---|---|---|---|
| 049 | (10,11) | `coord_event` → `Map049_EV002_Dispatch` | no |
| 050 | (14,19) | `coord_event` → `Map050_EV001_Dispatch` | no |

The generated dispatchers carry the real gates — Map049 tests pages high→low
(`FLAG_FINAL_EVENT` + self-switch → page 4, `FLAG_FINAL_EVENT` → page 3,
**`FLAG_MUM` → page 2 (the warp)**, else page 1, the refusal); Map050 is
`compare VAR_QUEST_LOG, 1` / `goto_if_ge` → warp page, else the refusal page.

### Tests

`tests/test_tileset_converter.py`: three new `classify_event` cases (gated door →
object, all-touch-pages-transfer → still warp, autorun page does not gate), and
`test_build_slice_maps_smoke` now asserts the coord_event sits on (10,11) with no
warp_event racing it. Suite: **1439 passed, 16 skipped.**

## 7. Still open

- **The ROM has not been rebuilt**, so beat B2 has not actually been re-run. The
  fix is verified at the data level (map.json + scripts.inc + dispatcher logic)
  but not yet on hardware. `make -C engine -j$(nproc) modern`, then
  `python -m rpg2gba.playtest run --chapter moki`.
- **Corpus-wide: 25 events across 14 maps, 18 with visible refusal dialogue**
  (re-measured 2026-07-26 under the narrowed player-touch rule — the 341/75
  figure in §4 was the over-broad first count, and is kept there only to show
  how much of it was the autorun-page false positive). These are now *handled
  by the same code path* the moment their map enters a slice; nothing further is
  owed unless a specific one misbehaves.
- `assemble_pathfinder.WARP_OVERRIDES` is still a **hand-maintained duplicate**
  of what `build_slice_maps` computes. It happens to agree now, and (4) is what
  keeps it agreeing, but deriving it would remove the hazard for good.

## 6. Related loose end found alongside

The playtest runner enforces ROM-vs-blob provenance (sha256, refuses a seed blob
across a rebuild) but has **no ROM-vs-staged-source freshness check**. On
2026-07-25 a full re-stage ran at 13:36:23 and the harness ran at 13:36:43
against `engine/pokeemerald.gba` built at **12:50:55** — no `make modern` in
between. It didn't change the B2 verdict (the current staged scripts have no
EV002 either), but it means a run can be certified "fresh" against a stale
binary. Cheap guard: refuse to run if anything under `engine/data` or
`engine/src` is newer than the ROM. Same hazard class as the `.sav` gotcha in
`BOOT_WALK_CHECKLIST` §8.
