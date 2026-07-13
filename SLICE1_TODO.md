# Slice 1 TODO — Map 49 (Player's House 1F) ↔ 48 (2F) ↔ 32 (Moki Town)

Working checklist for finishing the pathfinder slice to the §9 bar (boots in
mGBA, genuinely playable, warps/NPCs/layout/art all real). Commit updates as
items close; move an item to **Done** with a one-line result rather than
deleting it. Facts here are pointers — the cited code/docs stay authoritative.

## Open

### 1. Temp-switch page conditions still defer dispatch (8 Moki NPCs)

The bug-#7 dispatcher fix (`710e258c`) covers self-switch / named-global-switch /
named-variable page gates. Census (39 multi-page slice events): 31 dispatched,
**8 still defer to Page1** — all gated on the script-switch pair
`s:tsOff?("A")` (id 22) / `s:tsOn?("A")` (id 12): Map032 EV003/005/006/007/017/
023/037 (tsOff) + EV036 (tsOn). These are within-visit dialogue toggles (temp
switches reset on map exit), not repeat-item givers — cosmetic, not
progression-breaking.

**Fix sketch:** in `metadata_wiring.build_page_dispatcher`, when a page's
switch gate resolves to a script switch, pattern-match the switch label
(`registry.label_for_switch`) against `s:tsOn?("X")` / `s:tsOff?("X")`. These
predicates test the *event's own* per-event temp switch — the same flags the
transpiler's `setTempSwitchOn` idiom already mints — so emit
`flag(temp_switch_flag_name(uid, eid, X))` (tsOn) or `!flag(...)` (tsOff) and
`registry.mint_temp_switch(uid, eid, X)` when a registry is present (mirrors
the self-switch minting added in bug #7). No `FLAG_*` is minted for the `s:`
switch id itself, so the CLAUDE.md §6 rule ("never mint a FLAG_* for `s:`
switches") stays intact — the predicate resolves against an already-legitimate
per-event flag. Any other `s:` label still defers.

**Verify first:** read the `tsOn?`/`tsOff?` helper definition in
`reference/scripts_dump/` to confirm the predicate is scoped to the calling
event (not a global lookup) before wiring it. Ask the user before building —
this extends dispatcher semantics.

### 2. Auntie's queued `pbHasSpecies?(RAPTORCH)` branch (the 1 live queue entry)

`transpile_unhandled.jsonl` is down to one real slice entry: Map049 EV001,
code 111 conditional on `pbHasSpecies?(::PBSpecies::RAPTORCH)` — a branch of
Auntie's dialogue is an `# UNHANDLED` marker. The fork ships `checkspecies`
(asm/macros/event.inc:2541) + `DoesPlayerPartyContainSpecies`, but
`SPECIES_RAPTORCH` isn't in the pristine fork index, so the capability gate
would reject it. Blocked on Uranium species constants joining the gate extras
(Phase 7 integration); revisit then. (88 CommonEvent queue entries also remain,
but the slice calls zero CEs — not slice-blocking.)

### 3. `\wt[n]` text-pause timing — calibrate by eye

`deterministic.translate_text_codes` maps `\wt[n]` → `{PAUSE 0xHH}` with a
first-guess `n*3` frames formula. Never calibrated against real hardware feel.
While walking dialogue-heavy NPCs, judge whether pauses feel right; adjust the
multiplier in one place if not.

### 5. Remove the new_game.c test harness — needs a decision

Sentinel-fenced `TEST HARNESS` block after `CB2_NewGame()` grants
FLAG_BADGE03_GET + a Geodude knowing Rock Smash so the rock-smash path is
testable from a fresh boot. Tracked obligation: remove when real progression
covers it — but slice 1 never grants a badge (the Pokédex ceremony gives the
starter only). Decide with the user: keep the harness for slice 1's gate, or
narrow it (starter-only via ceremony, drop the badge/Geodude?).

### 6. Pokédex-ceremony live sprite swaps (EV76 ball / EV77 starters)

Deferred from task 4: RMXP change-graphic move-route commands on the ceremony
events have no fork-native script-callable gfx swap (`VAR_OBJ_GFX_ID_x`
resolves at spawn only). Recipe if wanted: `setvar` + `removeobject` +
`addobject`. General limitation behind it: page-driven sprite changes aren't
reflected — object gfx is the static boot page's. Judge in-game whether the
ceremony reads acceptably without it.

### 7. Audio — everything is a `# audio` comment

The transpiler comments out all RMXP audio commands; no Uranium BGM/SFX are
converted. Verify what actually plays on the slice maps (likely stock Emerald
defaults from map.json) and decide the slice-1 bar: accept stock audio, silence,
or start a minimal BGM mapping. §9 doesn't name audio, but "genuinely playable"
is the user's call.

### 8. Warp-class refinement

Every warp cell gets MB_NON_ANIMATED_DOOR regardless of kind (door / stairs /
mat) — deferred from Checkpoint 2. Doors don't animate open; stairs/mats behave
like doors. Fidelity polish, low risk. Fix = per-kind behavior in the tileset
warp-metatile emission (`build_slice_tilesets` / `tile_map.WarpInfo`).

### 9. Moki Town east edge — the Route 03 seam

`connections.dat` seams are unconverted (Checkpoint-2 deferral); Moki Town E ↔
Route 03 is on the slice-2 frontier. For slice 1, verify the east edge fails
*cleanly* (blocked, no walk-into-void) rather than converting the connection.

### 10. Tile-animation follow-ups (core feature done + user-verified — see Done)

Open questions left behind by the 2026-07-12 animation build:

- **Cadence fidelity.** 16 ticks/frame (~267 ms) is vanilla Emerald's water
  cadence, adopted as a first guess and approved by eye — RMXP's actual
  autotile speed was never measured against Uranium running in-engine. If a
  side-by-side ever shows a mismatch, adjust the `% 16` divisor in
  `_write_anim_fragment` (one place).
- **Corpus generalization.** Slice 1 exercises 2 effects on 1 tileset; the
  corpus has 69 multi-frame autotiles (up to 64 frames — `seatest.png`).
  Untested at scale: animated tiles landing in the SECONDARY tileset (current
  code packs them into the primary block and fails loud past 512 — fine for
  the slice, needs a secondary-callback variant eventually), many effects per
  tileset (DMA queue caps at 20 entries/frame), and columns hitting the
  64-frame lcm guard.
- **Waterfall / transparency.** ts22 slot 1 (`PU-Waterfall(transp)`, 5
  frames) is unused by Map032 cells — the first animated+transparent autotile
  arrives with Route 01 (slice 2). Stipple/alpha classify interaction with
  frame quantization untested.
- **Viewer "expand similar" over-split** (investigated 2026-07-12 — NOT a
  viewer bug): grouping is exact `column_key` equality and autotile
  shape-variants stay distinct; the 34 flower cells are ONE autotile whose 12
  shape variants render pixel-identical → 15 groups (+3 cells with a real z2
  sparkle overlay); water fragmentation adds legit edge shapes + z2 foam
  overlays. Candidate fix: collapse column-key groups whose rasterized pixels
  are identical (viewer UX + possible metatile-count win). Re-reported
  2026-07-13; the *color* half of that report was a separate real viewer bug —
  see `PROJECT_TODO.md` #13/#14.

### 11. Remaining boot-gate walk findings

The user is mid-walk. Bugs #1–#7 (palette off-by-one, dialogue overflow,
invisible rocks, pond reflections, rock debris/respawn, repeated dialogue) are
fixed. Add new findings here as they're reported.

## Accepted deferrals (not slice-1 work — listed so they aren't re-litigated)

- **HEROINE player** — slice boots MALE hardcoded; heroine sheets are exact-2×
  and convert cleanly when wanted.
- **Bike/surf/fish/field-move player poses** beyond rock smash — still Emerald
  Brendan; none slice-reachable.
- **`displayNinjaLetter` card UI** — letter renders as a scrolling msgbox;
  bespoke scene is a Phase-8 custom-C candidate.
- **88 CommonEvent queue entries** — slice calls zero CEs.
- **Base-page own condition ignored by dispatchers** — Page1 is always the
  fallback; sprite is static anyway (see bug-#7 notes in MEMORY).

## Done

- **2026-07-13 — #4 Moki ledge tiles: resolved by analysis, work moved to
  `SLICE2_TODO.md` #1**: the 3 warning tiles (ts22 840/841/842) are the
  pond-dock front at Map032 (37–39,53); Essentials gates ledge jumps purely by
  the tile's 4-dir passage bits (stock v17 — jump dir = movement dir, never
  stored), and 0x0E opens only the water side → from land they're walls, so
  the MB_NORMAL fallback is already faithful. Nothing to hand-map, and no
  slice-1 surface to test jumps on. Jump directions are auto-derivable
  corpus-wide from passage bits — derivation rule + ts22 inventory in
  SLICE2_TODO #1; the ~30 south-ledge over-block residual moves there too.
  The 3 build warnings stay (benign) until the derivation lands.
- **2026-07-12 — tile animation (Map032 flowers + pond)**: RMXP animated
  autotiles → GBA tileset anims, deterministic pipeline end-to-end (per-column
  lcm frame rendering, frame-aware dedup with static-demotion, union-color
  quantization, contiguous per-effect tile blocks, gen'd
  `uranium_anims.gen.h` callback via sentinel hook in
  `engine/src/tileset_anims.c`). ts22 = pond 57×19f + flowers 4×4f,
  997/1024 tiles. Viewer gained an "Animated" overlay. User-verified in-game.
  Follow-ups tracked in Open #10.
- **2026-07-11 — bug #7 repeated NPC dialogue** (`710e258c`): page dispatchers
  for global switch/var gates; Auntie + rare-candy granny advance correctly.
  User-verified on device.
- **2026-07-10 — audit F1+F2** (`5fc67dbf`): flag/var ranges grown behind
  `RPG2GBA_EXPAND_EVENT_RANGES`; temp-switch region clears on map transition.
  User boot-walked.
- **2026-07-11 — test debt: 2 known MAP_MOKI_TOWN failures**: root cause was a
  real registry gap, not just a test-fixture issue. `map_constants.
  load_vanilla_map_consts` read the *working tree's* generated
  `include/constants/map_groups.h`; a **built** engine's copy already carries
  this slice's own previously-emitted `MAP_MOKI_TOWN` etc. from a prior
  assemble, so a fresh mint saw its own output as a false "vanilla"
  collision. Fixed at the source: `load_vanilla_map_consts` now reads the
  vanilla `MAP_*` set from **git HEAD** (`_load_vanilla_map_ids_pristine`,
  one `git archive` of `data/maps/`, ~900 dirs' `map.json` `"id"` fields —
  `map_groups.h` itself is upstream-gitignored/build-generated, never
  committed) instead of the working tree, mirroring `fork_index`'s
  pristine-git-read pattern. Uranium map dirs are excluded by construction
  (`data/maps/*/` gitignored repo-root-side, never committed) — no false
  collision, and real vanilla-collision detection still works. Applies to
  every caller of `build_map_constants` (`assemble_pathfinder`, `phase5`,
  `stage_slice_scripts`), not just these two tests. Also uncovered + fixed a
  second, previously-masked bug: `test_build_slice_maps_smoke` never passed
  `npc_gfx` to `build_slice_maps`, which real slice maps (visible NPCs)
  require since the 2026-07-06 NPC-gfx-map landing — fixed by loading the
  real `reference/npc_gfx_map.json` against the built fork headers, skipping
  cleanly if either isn't present. 964 pass, 0 known failures.
