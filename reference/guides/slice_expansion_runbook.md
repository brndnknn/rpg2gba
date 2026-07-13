# Slice Expansion Runbook — adding new maps to the playable slice

**What this is:** the mechanical, step-by-step process for widening the playable
slice (currently Uranium maps 49/48/32) to new maps. The *philosophy* of the
per-slice loop (SELECT → EVENTS → ART → WIRE → BUILD → BOOT → FIX → RECORD)
lives in `BUILD_PLAN.md` §2 — this doc is the concrete file-and-command layer
under it. The §9 boot gate (CLAUDE.md) applies to every map added: a widened
slice isn't done until the new maps boot in mGBA and are genuinely playable,
art included.

**Audience:** Brandon + the build agent. Most steps are agent-run; the boot
gate walk is Brandon's.

Line numbers below were verified 2026-07-13 — re-grep before trusting them
blindly.

---

## 0. Recon before touching anything

For each candidate map id:

1. **Eyeball it in the map viewer** — `python scripts/map_viewer_server.py
   --port 8765`, browse `/map/<id>`. Works pre-conversion (reads
   `output/uranium-build/maps/` + `tilesets.json` from the Phase 3 run).
   Feedback convention: flag cells in the viewer → saves to git-tracked
   `reference/map_feedback/MapNNN.json` (per `reference/viewer/map_viewer.md`; the
   README's "Issues panel → map_viewer_issues/" description is stale — that
   store is retired).
2. **Check the name** — the map must have a display name in
   `output/uranium-build/intermediate/map_infos.json` or an entry in
   `reference/map_name_overrides.json` (`overrides` key wins). Missing name →
   `build_map_constants` raises at step 4.
3. **Check the tileset budget** — new maps pull in their `tileset_id`'s whole
   tileset (pooled with any slice map sharing it). Hard fail-loud limits in
   `graphics/emit.py`: 1024 tiles, 1024 metatiles, 13 palettes, animated
   block ≤ 512 (must fit PRIMARY). `map_set.WALKER_OVERFLOW_MAP_IDS` lists 16
   known over-budget maps — adding one of those means solving its overflow
   first (an explicit id list is honored and fails loud at emit time).
4. **Check for connection seams** — `connections.dat` seamless route↔town
   edges are **unconverted engine-wide** (14 exist; inventory in
   `reference/viewer/walker_checkpoint2_findings.md` §4). If the new map joins a
   neighbor via a *connection* (not a warp), that seam will not exist in-game;
   decide up front whether that's acceptable for the slice or the seam design
   work has to land first.
5. **Census the events** — dry-run the transpiler on the candidate ids
   (step 3 with `--dry-run`) and read the queue output to size the manual
   tail (hand overrides, natives, new idioms) before committing to the map.

## 1. Widen the map set — one real edit + two hazard literals

- **Source of truth:** `src/rpg2gba/tileset_converter/map_set.py:28` —
  `SLICE_MAP_IDS: list[int] = [49, 48, 32]`. Edit this. Everything that
  matters imports it (`assemble_pathfinder`, `stage_slice_scripts`'
  `DEFAULT_SLICE`, viewer pooling, parity oracle, previews).
- **HAZARD — hand-edit these too, they are separate literals:**
  - `scripts/stage_slice_scripts.py:53` — `ALLOWED_MAPS = {49, 48, 32}`.
    Controls which warp destinations survive `prune_map_pory`. Miss it and
    the new maps' warps are treated as out-of-slice and dropped even though
    wiring covered them.
  - `scripts/assemble_pathfinder.py:58-62` — `WARP_OVERRIDES` (per-map warp
    *source* coordinates). Each new map needs its entry (mirrors
    `build_slice_maps`' returned `src_coords` — the wiring preview scripts
    help enumerate them). Miss it and the warp tile never gets the door
    metatile stamped: warp silently inert.
- Ignore the stale literals in `scripts/run_slice.py:66` (retired LLM path),
  `scripts/pathfinder_tile_census.py:25`, `scripts/pathfinder_warp_trace.py:19`
  (one-off S1-era tools) — update only if you actually use them.
- Tests pinning the set: `tests/test_map_set.py` asserts
  `parse_map_ids("slice") == SLICE_MAP_IDS` (updates itself); fixture
  literals in `tests/test_tileset_converter.py:585,845,873,880` are
  informational — check whether any assertion breaks, don't blind-edit.

## 2. Per-map prerequisites (before the pipeline will pass)

- **NPC graphics — fail-loud, not drop:** every `character_name` on an
  emitted object event must resolve through `reference/npc_gfx_map.json`
  (`metadata_wiring.py:743-747` raises KeyError naming the missing sheet).
  For each new sheet:
  - Entry `"<sheet>": {"gfx": "OBJ_EVENT_GFX_URANIUM_<NAME>"}` — the constant
    must match `npc_gfx.gfx_constant_for_sheet`'s derivation exactly
    (`npc_gfx.py:51-57`; `sprite_pass` fails loud on disagreement).
  - `sprite_pass` then auto-converts the real PNG from
    `$RPG2GBA_URANIUM_SRC/Graphics/Characters/` (case-insensitive; missing
    file → FileNotFoundError). Entries pointing at a plain vanilla
    `OBJ_EVENT_GFX_*` are reused as-is, not converted.
  - **Palette budget:** all converted NPC sheets share **≤ 4 sprite
    palettes** (player has its own 5th). Overflow = silent color garbage on
    hardware, so re-check the union after adding sheets (`sprite_pass`
    docstring; preview PNG + eye check, per the validate-graphics-by-eye
    rule).
  - Sheets that exist only as door graphics are dropped by
    `npc_gfx.is_door_sheet` — no entry needed.
- **Name overrides:** add `reference/map_name_overrides.json` entries for
  floor/building disambiguation or vanilla-collision renames (the mint error
  messages tell you when).
- **Strip decisions:** whole-map or per-event strips go in
  `reference/strip_list.json` (never hand-edit generated output).
- **Hand overrides:** genuinely irreducible events get
  `src/rpg2gba/conversion_agent/hand_conversions/Map###_EV###.pory`
  (filename format enforced; all labels must stay in that event's
  namespace).

## 3. Transpile events

```bash
.venv/bin/python -m rpg2gba.conversion_agent.transpile_driver run --maps slice
# or explicit ids while iterating:  --maps 49,48,32,50   [--dry-run]
```

- `--maps slice` resolves through `map_set` — after step 1 it includes the
  new maps automatically.
- Writes `output/uranium-build/scripts/Map###.pory` + **`Map###.traits.json`
  sidecar** (staging refuses to run without it) + refreshed
  `transpile_unhandled.jsonl`, and saves registry mints to
  `flag_state.json`.
- The **fork capability gate runs here** (per map + CommonEvents): an
  unresolvable command/constant aborts with RuntimeError — that's a
  transpiler bug or a missing native mapping, never a queue item (§4.7).
- **Read the new queue entries to completion** (CLAUDE.md §4.1) and bucket
  them: native / idiom / hand / defer — same discipline as
  `reference/findings/slice1_queue_readthrough.md`.

## 4. Stage + wire

```bash
.venv/bin/python scripts/stage_slice_scripts.py --write
```

- Wiring always covers the full `DEFAULT_SLICE`; the positional arg only
  narrows which maps get *staged*.
- Regenerates porymap `map.json` (object/bg/coord events, page dispatchers,
  warps), runs the sprite pass, prunes out-of-slice warp blocks, and
  fail-loud checks: traits sidecar present, every referenced label defined
  exactly once, no out-of-slice `MAP_URANIUM_*` in kept text.
- Out-of-slice doors on the NEW maps become NO-EMIT + blocked cells by
  design (`classify_event` "out-of-slice warp"; `collect_through_block_cells`
  keeps them walled). That's the frontier behaving correctly, not a bug.

## 5. Assemble into the engine

```bash
.venv/bin/python scripts/assemble_pathfinder.py            # full pass
#   --dry-run          report only
#   --skip-graphics    reuse already-emitted tilesets (S8a)
#   --skip-layout      reuse generated layout .bin (S8b)
```

- Runs tileset emission (budget guards fire here), layouts, map constants
  (vanilla-collision check against the fork's **git HEAD**, not working
  tree), the staging fork gate again, and emits `uranium_flags.h` from the
  registry.
- **Warts to clean when things link weird:**
  - `output/uranium-build/staging/layouts/layouts.json` **accumulates**
    (upsert-only). Stale entries from walker runs or dropped maps →
    undefined `gTileset_Uranium10xx` at link. Delete the manifest (and any
    stale engine `data/maps|layouts` dirs) when switching build flavors or
    renumbering. (`engine_extension_surface.md` §"build gotchas".)
  - Build flavor flag: `engine/include/config/uranium_walker.h`
    `URANIUM_MAP_WALKER` must be `FALSE` for the playable slice.
  - `make -C engine clean` after flavor switches.

## 6. Build + boot gate

```bash
make -C engine -j$(nproc) modern
```

- Taildrop the ROM to Brandon's phone: `tailscale file cp
  engine/pokeemerald.gba iphone182:` (SendUserFile doesn't reach the phone).
- **§9 gate per CLAUDE.md:** Brandon walks the new maps — warps fire both
  directions, NPCs sane, layout legible, real quantized art, dialogue
  readable. Log findings in the live `SLICE*_TODO.md`; flag art cells via
  the viewer (`reference/map_feedback/`).
- Compare viewer vs ROM with `scripts/verify_viewer_rom_match.py` when art
  looks off (parity oracle; `reference/viewer/viewer_rom_parity_2026-07-12.md`).

## Fail-loud quick reference

| Error | Meaning | Fix where |
|---|---|---|
| `map {id} has no name in map_infos/overrides` | new map unnamed | `map_name_overrides.json` |
| `MAP_* collides with vanilla` / minted dup | name clash | `map_name_overrides.json` entry |
| KeyError `<sheet>` … `npc_gfx_map.json entry` | unmapped NPC sheet | `npc_gfx_map.json` (+ sheet PNG exists) |
| gfx constant disagrees with derivation | JSON entry vs `gfx_constant_for_sheet` | fix the JSON constant |
| tiles/metatiles/palettes over budget (emit.py) | tileset too big | shrink pool / overflow work item |
| animated block > 512 | anims must fit PRIMARY | tileset work (secondary-callback variant is an open follow-up) |
| traits sidecar FileNotFoundError | staging ran before transpile | re-run transpile driver |
| fork-gate RuntimeError | emitted symbol not in pristine index | fix transpiler/native mapping (§4.7), never the output |
| kept text references dropped label / out-of-slice `MAP_URANIUM_*` | prune inconsistency | check `ALLOWED_MAPS` (step 1 hazard) |
| undefined `gTileset_Uranium10xx` at link | stale layouts.json | delete staging layouts manifest, re-assemble |

## Limits every new map inherits (known, tracked)

- `connections.dat` seams unconverted (step 0.4).
- Animated tiles must land in the PRIMARY tileset; secondary-callback
  variant not built yet (`SLICE1_TODO` #10).
- Page dispatch selects the *script* only — boot-page gfx/visibility/
  movement stay static (MEMORY, bug-#7 notes).
- Warp cells are all `MB_NON_ANIMATED_DOOR` regardless of door/stairs/mat
  (`SLICE1_TODO` #8).
- NPC movement wiring is under investigation (`SLICE1_TODO` #12).
