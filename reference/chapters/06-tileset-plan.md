# CH06 tileset plan — seam palettes + viewer parity (written 2026-10-04)

Operator goal: before CH06 tileset work, SEE Kevlar (31) + Route 2 (35) + Nowtoch (40)
with shared seam palettes, stitched, in a viewer that tells the truth about the ROM.
Operator approved steps 2 and 4 below; steps 1 and 3 are not started and not approved.

## Established facts (2026-10-04)

- **One shared tileset for 31∪35∪40 is impossible:** ~1587 metatiles / ~2194 tiles vs
  1024/1024 caps; only ~15% of map 40's metatiles appear in 31∪35. Map 40 alone
  (1278 mt / 1539 tiles) busts both caps, so **map 40 must be split** whatever we decide.
  Quantization knobs only move tile counts by ~±2% and never touch the metatile cap.
- **The ROM has no Uranium connections at all** (every Uranium `engine/data/maps/*/map.json`
  has `"connections": null`); 31↔35 is an arrow warp (`reference/seam_warps.json`).
- **Why palettes stopped being shared:** 4db0deb9 (2026-08-05) made tilesets per-map
  (budget fix for 32∪33) and implemented only part 1 of the July design
  (`reference/guides/connections_and_palette_families.md`); parts 2 (component-pinned
  palettes, user-approved) and 3 (border-strip import) were never built (PROJECT_TODO #27).
  59a0a4a9 explicitly deferred the Kevlar/R02/Nowtoch seam to CH06.
- **Viewer is stale:** `scripts/map_viewer_common.py:437-451` still pools slice maps by REAL
  tileset id (31/32/33/35 together), so it shows sharing the ROM doesn't have. Stitched mode
  draws each map with its own art and cannot show what fieldmap.c does (neighbour metatile
  IDs, 7 cells deep, drawn through the CURRENT map's tileset).

## Done 2026-10-04 (committed `e1ee646a`)

- `src/rpg2gba/tileset_converter/graphics/palette_families.py` + `tests/test_palette_families.py`
  (13 tests): `seam_components(rows, map_ids)`, `compute_component_palettes(lists)`,
  `make_pinned_quantizer(palettes)` (a `quantizer=` hook for `emit_tileset` /
  `analyze_tileset_palettes`). Library only; nothing consumes it yet. Reviewed by lead.
- `scripts/verify_viewer_rom_match.py` Mode A rewritten for per-map synth tilesets; it now
  calls the real `build_slice_tilesets` with stubbed writes. **18/18 slice maps pass,
  0 px diff** against the 10-02 artifacts. Mode B refuses (exit 1) until the viewer is fixed.
  `tests/test_verify_viewer_rom_match.py` (3 tests).
- Open aside: stale `engine/data/tilesets/primary/uranium19`, `uranium22`, `*_cmp*` dirs —
  check whether tracked; likely delete. *(Checked 2026-10-06: untracked (gitignored) and
  referenced by nothing in `engine/src`/`include`/`data/tilesets` — `uranium19{,_cmpcur,_cmpdiv,_cmpfam}`
  and the same four for 22 are leftovers of the June palette A/B/C compare. Safe to delete; not yet deleted.)*

## Step 4 progress (2026-10-04, committed `e1ee646a`)

- **Items 1, 2, 3, 5 DONE.** Per-map pooling; `?sp=1` seam-palettes toggle; `/api/seamcheck/<id>`
  + stitched overlay; oracle Mode B re-enabled — **18/18 slice maps, 0 px diff**. Mode B also
  caught a viewer bug: pool metatiles dropped `n_frames`, so animated columns' later frames never
  reached the quantizer (maps 31/32/33/36 drifted); fixed via `_render_pool_column`.
  Full suite 4850 passed / 17 skipped.
- **Smoke (item 6, in-process):** component (31, 35, 40) for all three; seam palettes fit
  2187 union metatiles → 13 × 15-colour palettes; first seam render 8.8 s, then ~1 s.
  Seam-check cost (missing unique / strip unique): 31←35 22/73 · 35←31 39/70 · 35←40 29/56 ·
  40←35 31/59.
- Known caveat: `_handle_quantize`'s eager re-quant uses the plain view, so a knob that breaks
  only the seam view 500s on reload instead of a clean 400.
- **Item 4 DONE.** `/api/shared?map=N` (component) or `?maps=a,b,…`; stitched "Shared tiles"
  overlay with partner/basis selects + pair matrix. Bases: `rmxp_id`, `rmxp_image`, `rom_mt`,
  `rom_tile` (8×8, flip-canonical, palette-resolved). Measured: 31/35 share **100 metatiles by id /
  108 by image in RMXP but 0 ROM metatiles and 3 ROM 8×8 tiles** — the per-map-palette loss.
  40 shares no ids with 31/35 (ts23 vs ts22) but 144 / 86 metatiles by image.
  Caveat: cells whose pool index falls outside the artifact are dropped from ROM sets silently.
- Server restarted for the operator's eye check (port 8765). **Next: operator looks; approval of
  the seam-palette look gates step 2.**

## Next — step 4: viewer parity (one agent owns all viewer files)

Files: `scripts/map_viewer_common.py`, `scripts/map_viewer_server.py`,
`scripts/map_viewer/viewer.js` (+ page template), `tests/test_map_viewer_fingerprint.py`,
new `tests/test_map_viewer_seams.py`.

1. **Per-map pooling** by default (`pool_map_ids = [map_id]`); fix the docstring; update the
   fingerprint test at ~340-350 (it asserts the old shared-pool behaviour).
2. **"Seam palettes" toggle** (off by default), next to the existing quantize knobs and the
   non-stock badge. When on: component from `seam_components` over ALL connections.json rows
   (map 40 isn't in SLICE_MAP_IDS); render each member's metatile list with its own raster;
   `compute_component_palettes` (lists sorted by map id); cache by component + member
   fingerprints + knobs; the per-map analysis uses `make_pinned_quantizer(pals)`.
3. **"ROM seam check" overlay** in stitched mode. Endpoint `/api/seamcheck/<id>`: for each
   (A, neighbour B), B's 7-deep strip at the shared edge (clamped to the overlap) and which
   strip metatiles, compared by rendered IMAGE hash not column key, are absent from A's
   per-map pool. JS draws a hatch on the missing cells and a per-seam summary. That number
   is the cost of border-strip import.
4. **"Shared tiles" view (operator request 2026-10-04): see which tiles maps share in BOTH
   the original RPG Maker data AND the ROM.** For a chosen set of maps (default: the stitched
   component; also allow arbitrary picks such as 31+35+40):
   - **RMXP side:** tiles are shared when two maps use the same RMXP tileset and the same
     tile id (column key). Compare by RMXP tileset + tile id; maps on different RMXP
     tilesets (31/35 on ts22, 40 on ts23) share nothing by id, so also offer a
     rendered-image match to show identical art across tilesets.
   - **ROM side:** tiles are shared when the emitted GBA tilesets contain the same thing.
     Decode the real artifacts (reuse the oracle's `TilesetROM` / `load_tileset_rom` from
     `scripts/verify_viewer_rom_match.py`) and compare per map at two levels: metatiles
     (decoded 16×16 image) and 8×8 tiles (pixels + palette colours). Maps without artifacts
     (e.g. 40) show as "not in ROM".
   - **UI:** highlight cells whose metatile is shared with each other selected map, plus a
     summary matrix of shared and unique counts per map pair, for RMXP and ROM side by side.
     The point is to see where the two diverge: shared in RMXP but not in the ROM is
     exactly what the per-map tilesets and the seams lose.
   - Endpoint plus tests as for the seam check. Same file ownership as the rest of step 4.
5. Then re-enable oracle Mode B against per-map pooling.
6. Smoke-test in-process (31/35/40 seam-palette render, timing, union size), then restart
   the viewer server for the operator's eye check. Remember the `?g=` cache bug
   (PROJECT_TODO #13/#14): hard-reload the page when comparing.

## Step 2 in the build — only after the operator approves the look

Wire `palette_families` into `build_slice_tilesets` / `assemble_pathfinder.run_graphics_pass`:
components restricted to the build set, pinned quantizer per member, a log and fail-loud
guard on the pinned-quantizer `max_shift_5bit`. Decide whether pinned palettes become a
committed `.gen.json` (that is a new intermediate artifact, so ask first, CLAUDE.md §10). Run
the oracle Mode A after the rebuild.

## Candidate palette design — research 2026-10-05 (NOT approved, nothing built)

Operator question: can recurring art (the rocky highland around 31/35/40, grass, trees) get the
same colours on every map? Researched in scratch only. Every number below comes from re-running
the ROM-exact per-map quantization path from the viewer (pool via `map_viewer_common._ensure_loaded`
→ `emit._canonicalize_and_quantize`) with swapped quantizers, over the 26 CH01–06 maps. Metric:
"ge3" = slot-weighted pool pixels whose max-channel 5-bit shift is ≥3. Scripts and renders are in
`output/scratch/` (gitignored, so they may not survive a wipe): `rock_*`, `rockslot_*`, `green2_*`,
`roofdiag*`, `combo_*`, `ward_*`.

### The design: three independent pieces, each a separate approval

| Piece | What | Where | Effect (ge3, CH01–06) |
|---|---|---|---|
| **P1. Usage-weighted reduction** | Replace the per-palette `_median_cut(pal, 15)` in `quantize.build_quantized_tileset` (~line 310) with a **Ward merge**: repeatedly merge the colour pair with the lowest `w_a·w_b/(w_a+w_b)·‖c_a−c_b‖²` (RGB555; `w` = the colour's pixel count in that palette's tiles). | production packer (every map) | 755.8k → 111.7k (**−85%**) on its own |
| **P2. Shared fixed palettes** | One game-wide rock palette (V1) plus 3 usage-weighted green palettes (G3t), pinned into every map that uses ≥ N=8 of that group's 8×8 tiles; exempt maps keep the slots. | new: wraps the packer as a `quantizer=` hook, like `palette_families.make_pinned_quantizer` | with P1: 755.8k → **102.3k (−86%)**; shared art is pixel-identical across maps (394/394 shared tiles; BASE 0/394) |
| **P3. Tuning** | Accent slots in the green set (pink flower, trunk browns, real yellow flower centre). Fix the open items below. | P2's palette build | pink ≥3 share 71.6% → 34.7% |

**P1 is the biggest and simplest lever and can land alone.** It confirms the July finding that
95% of colour collapse happens in the per-palette reduction (`graphics_conversion_notes.md` §10;
`memory-archive.md`). July only tried *repacking*, which it found to be a dead end, and never tried
replacing the reduction. Note: the global-vocabulary `_median_cut` call (~line 262) is never reached
by the family packer (`_NO_VOCAB_CUT`), so the July warning against vocab weighting ("Do NOT revisit
vocab weighting", `connections_and_palette_families.md`) is a different site. Its risk is still
real: rare detail colours being swallowed. That did not show up by eye with full weights.
sqrt-damped weights were **worse** everywhere.

### Root causes found along the way

- **31 vs 35 look different** because every map quantizes alone (4db0deb9). The same tileset-22
  art lands in different palettes. A rebuild with today's code reproduces this; the viewer is correct.
- **Moki's orange roof stripes are fragile under today's packer** (`roofdiag.md`).
  - The `brown` family is a catch-all: 353 tiles, ~182 colours, covering roofs, trunks, dirt and rock.
  - The unweighted median-cut box-splits it.
  - Removing just 2 colours (the rock tiles) merges the two stripe oranges, which are 3 steps
    apart, into one tan.
  - BASE keeps the stripes by luck.
  - The cause is neither family allocation (refuted) nor V1 capturing the tiles (refuted).
- **BASE already mis-renders**: Moki's cliff faces come out pink, Nowtoch's rock pale yellow, and
  Nowtoch's grey cobble olive. P1 and P2 fix all three.
- **An unweighted closest-pair merge** (tried before Ward) fixed the roofs but turned Nowtoch's
  slate greys flat green, because large grey areas got merged into a nearby green. Ward's weight
  term is what prevents that.

### Palettes as researched

- **V1 rock** (11 rock + 2 grass + 2 water, so cliff edges against grass or water fit one palette):
  `392929 735242 73635a 845a4a 946b4a ad7b63 ad845a bd8463 c6946b d6a573 e7b57b | 63b563 73d673 | 528cad 5a94b5`.
  - It covers 46 flip-canonical rock/cliff images losslessly: 32.5k layer cells, 7 RMXP tilesets
    (22, 23, 24, 25, 30, 36, 50).
  - The rock/cliff cells as a share of each CH01–06 map: Moki 16%, Route 01 16%, Kevlar 26%,
    Route 02 71%, Nowtoch 30%.
  - Seven of the 12 rock/water/grass edge tiles land fully; the dark-water edges still fall back.
- **Grey, olive and pink rock are different families.** Squeezed into V1 they read as brown.
  - Pink (Comet Cave, maps 36/37) and yellow sandstone are mostly exact **palette swaps** of base
    rock tiles (14 of 20 tinted tiles; pink renders at 0 shift through its own palette).
  - So tints are best done as swap palettes loaded only where used, not as slots in V1.
  - Red speckled cliff faces are not swaps.
- **G3t green**: 3 palettes built by usage-weighted clustering, with an adjacency (Potts) penalty
  so that neighbouring grass quadrants share a palette. Two palettes carry 4 accent slots each
  (trunk browns, white, grey, pink, yellow); one is pure green.
  - The hex values and the tile→palette table are in `output/scratch/ward_G.pkl` / `ward_cost.md`.
  - Unweighted green palettes (an earlier attempt) were clearly worse: dark olive trees and an
    8×8 checkerboard.

### Measured costs and budget

- **Budget**: outdoor maps (31, 32, 33, 35, 40) reserve 4 palettes (V1 + G3t), leaving 9 for the
  packer. With N=8, every interior and cave map in CH01–06 is exempt and keeps 13.
  - The N=8 threshold exempted maps 19, 36, 37, 42, 45 and 47, which have 1–7 rock tiles.
    Exemption was equal or better on each.
- **Cost of a reserved slot** without P1: +2.7% ge3 on the rest of each map. With P1 the rest is
  far better than BASE on every map except a few caves (+0–22 px).

### Open items before any build

1. **Nowtoch panel grid.** Ward merges the two slate greys (586070 / 687078; 24k px), so the
   panel/roof cross-hatch goes flat. Look at why two large, distinct greys merge: the packer
   probably gives that palette too many colour families.
2. **Mixed-palette cells.** Pinning trunk tiles in G3t raised grass/tree cells with mixed
   palettes from 4.4% to 36%. Not visible in the crops, but re-run the adjacency refinement
   after pinning.
3. **Trunks** are still at 39.5% ≥3 vs BASE 26.9%.
4. **Small artefacts:** Kevlar's sand path loses its speckle; Route 01's water is a little dark;
   blue flowers grow a grey petal (31, 33).
5. ~~**G3t and V1 are tuned on CH01–06 art only.**~~ **RULED 2026-10-06 (operator): frozen.**
   Later chapters add palettes (e.g. swap palettes for pink/sandstone rock); they never refit
   V1/G3t, because a refit re-colours chapters that already passed their boot gate.
6. ~~**Viewer and oracle parity.**~~ **RULED 2026-10-06: a standing rule, not a question.**
   Implemented by `graphics/rom_quantize.py` — the one definition of the ROM quantizer;
   `build_slice_tilesets` emits with it, and the viewer's `ROM_STOCK_*` (which the oracle sets)
   are read from it, so they cannot drift.
7. ~~**Persisted artifact.**~~ **RULED 2026-10-06: not needed for now.** The palettes are source
   constants in `shared_palettes.py` and `classify_tile` assigns tiles at build time. Revisit
   (and ask, CLAUDE.md §10) only if the research's hand-refined tile→palette table is adopted
   for item 2.

**P1 + P2 IN THE ROM BUILD (2026-10-06, operator-directed):** `rom_quantize.ROM_FAMILY_PARAMS =
FamilyParams(reduction="ward")`, `ROM_SHARED_PALETTES = True`. Open items 1–4 (and P3) are
still open; they are tuning on top of what now ships, not blockers to it.

### P1 in the viewer — built 2026-10-05 (committed `9dfc3663`; look approved, viewer default)

- `FamilyParams.reduction` (`"median_cut"` stock | `"ward"`) → `_pack_subset` →
  `build_quantized_tileset(reduction=)`; `_ward_reduce` in `quantize.py` (weights =
  per-vocab-index pixel counts over the palette's member tiles, extra frames count 1).
  Only the per-palette cut changes; the phase-1 vocab cut is untouched.
- Viewer: knob-bar "Reduction" select (`knobbar.js`, injected after the overflow
  control); `params_from_dict`/`get_quantize_params` carry it; honoured in both the
  per-map and the seam-palette paths; lights the non-stock badge.
- ROM path untouched (default stock). Oracle Mode B with stock: 18/18, 0 px. No time cost
  (31/35/40 render times identical). Tests: `tests/test_quantize_ward.py` (7),
  `tests/test_map_viewer_reduction_knob.py` (9).
- Not yet: Ward in the ROM build or the oracle (item 6 above). Those follow the operator's
  approval.

### P2 preview in the viewer — built 2026-10-05 (committed `9dfc3663`; look approved, viewer default)

- `graphics/shared_palettes.py`: `ROCK_V1` + `GREEN_G3T` as **provisional constants copied from
  the research** (not re-derived; open item 5), `fit_palette`, `make_shared_quantizer(base,
  min_tiles=8, rock_max_shift=1)` — reserves V1 / the 3 greens per map past the threshold, packs
  the rest with `base` (so Ward composes). **Deviation:** green tiles take the best-SSE green
  palette, not the research's adjacency-refined table, so mixed-palette grass cells may be worse.
- Viewer: knob-bar "shared palettes (P2)" checkbox; viewer-only state (`_shared_palettes`, not a
  `FamilyParams` field); `meta.shared_palettes` carries per-map counts. Combining with `?sp=1`
  fails loud (reaches the client as a 500, not a 400).
- Measured (Ward + shared): outdoor maps 31/32/33/35/40 reserve 4 palettes; 19 and 36 are under the
  threshold. No time cost. **31∩35, 308 common opaque 8×8 source quads: 52 identical after
  quantization without shared, 186 with.** 11 of 193 shared-palette-coloured quads still differ
  (not investigated). Stock oracle Mode B still 18/18, 0 px; full suite 4901 passed.
- **Operator approved the look (2026-10-05): Ward + shared palettes are the VIEWER DEFAULT.**
  `map_viewer_common` has `ROM_STOCK_*` / `set_rom_stock_quantize()` and `VIEWER_DEFAULT_*` /
  `set_viewer_default_quantize()`. `non_stock` still means "differs from the ROM build", so the
  badge is lit by default; knob bar has Reset (viewer default) and ROM view. Oracle Mode B sets
  the ROM config explicitly. `?sp=1` with shared on returns a 400. **The ROM build is still stock.**
- **The 11 "differing" tiles are a measurement artefact** (`output/scratch/diff11.md`): all are
  near-rock browns (best V1 fit max shift 5, so not rock; not green family) that go to the per-map
  packer on both maps and happen to land on shared-palette colours. Every tile actually pinned on
  both 31 and 35 (182) is byte-identical; all 122 non-identical common quads are packer tiles.
  Possible palette-design follow-up: loosen the rock test (e.g. shift ≤5 with SSE ≤~350 catches
  9 of 11) or add a second rock-ish palette.
- **"Palette sets" overlay (2026-10-05; operator eye-checked and approved 2026-10-06):** toolbar checkbox,
  shortcut `p`, single-map + stitched. Tints each 8×8 quadrant by `shared_palettes.classify_tile`
  (now the one classification the quantizer uses): rock / G0 / G1 / G2 / packer; hatched = in a
  set but under the 8-tile threshold on this map. Layers are the ROM's bottom/top BG, not RMXP
  layers. `GET /api/palsets/<id>`. Shown whether or not shared palettes are on.

### How this relates to steps 2–4 above

P2 generalises step 2: game-wide groups instead of per-seam components. The two can stack: fixed
groups first, then the seam component's palettes for the remaining slots. P1 is orthogonal and
helps every map, seam or not. The **Seam palettes** viewer toggle (step 4) previews step 2 only.
*(Corrected 2026-10-06: P1 and the P2 preview are in the viewer and are its default since
2026-10-05; P3 is not built. None of P1–P3 is in the ROM build.)*

## Later (not approved)

- **Step 1: split map 40** so each piece fits under the caps. Measure the cut lines first.
  **Measured 2026-10-06** (real build path, ROM quantizer; scripts `output/scratch/
  {measure_map40,flip_stages_map40,layer_test_map40,cut_scan_map40,cut_scan3_map40,
  render_cuts_map40}.py`, gitignored):
  - Whole map: **1278 metatiles / 1544 tiles** vs 1024/1024 (+254 / +520); palettes 13/13.
  - Flip reuse is already on (raw pixels, H/V/HV): 2062 → 1748 distinct quads (−314);
    post-quant merge → 1543. Transparent-pixel RGB is not hiding matches.
  - Baking: art alone (every RMXP tile rendered by itself) = 1234 quads (~1090 ROM) — **over
    the cap even with zero baking**. Current baking rule = 1748; "bake only when forced"
    (one RMXP layer per GBA slot in ≤2-layer all-p0 cells) = 1585 (~−145 ROM). 549 of 1277
    columns are 3-layer, so most baking is forced by the 2-slot metatile. The fork has no
    triple-layer metatiles (`NUM_TILES_PER_METATILE 8`).
  - **No 2-piece straight cut fits**: best exact worst piece 1125 tiles (H y=31); halves
    each keep ~70% of the tiles because the art repeats city-wide.
  - **3 pieces fit with ~40–150 tiles headroom** (exact): HH y=23,42 → 912/923/888 tiles;
    VV x=34,55 → 873/912/933; V x=55 + left H y=34 → 929/872/933. Metatiles ≤ 604.
  - Every fitting cut runs through open streets (30–90 walkable crossing cells); the city
    has no natural chokepoints, so arrow warps are not viable — pieces need real seams,
    i.e. **step 3 (border-strip import) is a prerequisite of step 1**, and the strip
    metatiles cost tiles out of that headroom.
  - **Engine (verified 2026-10-06):** `fieldmap.c` `FillConnection` copies the neighbour's raw
    metatile ids 7 cells deep (east: 8), drawn through the current tileset; crossing a
    connection (`overworld.c` `LoadMapFromCameraTransition`) reloads ONLY the secondary
    tileset + palettes 6–12. So connected pieces must share one primary, and each piece must
    hold its neighbours' strip art at the neighbours' ids (shared primary, or duplicated in
    its own secondary).
  - **Seam cost of the three fitting layouts (`seam_cost_map40.py`): all OVER.** Strips in the
    shared primary alone need 745–812 metatiles / 1226–1340 tiles (primary cap 512/511). The
    floor — each piece holding own + visible strip art — is still over on every piece
    (pre-quant upper bound, ~×0.9 after quant): HH 1187/1407/1155; VV 1160/1401/1227;
    V+H 1228/1197/1227 tiles. Strips add 127–410 tiles per piece; middle pieces see two.
  - **Repetition (`repetition_map40.py`):** of 1748 pre-quant quads, 38.6% are used by exactly
    one cell and 65% by ≤4; only 10% by 20+. By column class: overhang (priority ≥1: roofs,
    tree tops, tall objects) 787, solid (walls, faces, fences) 733, ground static 189, ground
    autotile 39 — **buildings are 87% of the cost; ground is ~13%**, so an Emerald-style shared
    "general" primary of ground art would hold only ~230 quads. Heat map: `map40_rarity.png`.
  - **Near-duplicate merge (lossy, original pixels, alpha shape must match, flips allowed,
    K = pixels allowed to differ by >24/255):** exact ROM tiles 1544 → K=0 1347 · K=2 1170 ·
    **K=4 1063**. By eye (crops `map40_merge_{north,southwest}.png`): K=4 indistinguishable;
    K=8 garbles sign text ("SUBWAY") and roof panels; K=16 visibly broken. Metatiles do not
    drop (1277), so the metatile cap still forces a split. The scratch merge also dropped
    animation frames on merged animated metatiles (26 → 11 animated tiles) — a real
    implementation must exclude animated quads.
  - **With K=4 merge (animated excluded; `seam_cost_merged_map40.py`), a seamless 2-piece split
    FITS.** 1748 → 1075 merged quads. 30 of 131 two-piece cuts pass the floor (own + visible
    strips); the best also pass the engine check (one shared primary, per-piece secondaries,
    strip ids agreeing): V x=48 exact floor 803/821 tiles; V x=45–49 and H y=31 fit. Shared
    primary ~434–507 mt / ~497–512 t; each secondary ≤512 mt / ~300–350 t.
    **Metatiles are now the binding cap:** the larger piece needs 946–1019 of 1024 ids and
    the strip-id constraint lands at exactly 512 under the scratch greedy — a real id
    allocator must be built and checked. Palettes are not modelled (primary 6 shared,
    secondary 7 per piece → needs a two-stage quantizer). 3-piece layouts pass the floor but
    fail the strip-id check under this greedy (560–639 > 512) — more cuts, more strips.
- **Corpus outlook (2026-10-06, `output/scratch/overflow_census.py`; re-measured the walker's
  16 `WALKER_OVERFLOW_MAP_IDS` under today's ROM quantizer + K=4 merge, exact emit):**
  - Must split, metatiles > 1024 (merge does not reduce metatiles): 40 Nowtoch CH06 (1278),
    117 Route 08 CH22 (1209), 143 Route 10 CH31 (1066), 144 Venesi City CH47 (1062),
    101 Bealbeach City CH51 (1557), 187 Route 08 Nuclear CH52 (1413), 84 Dream Mountain CH59
    (1249), 71 Abyssal Venesi CH59 (~1062, grid count — its `Floatstone` autotile asset is
    missing from the source tree, so it can't render), 94 "Mapa intro" (no chapter, 150×150,
    1816).
  - Must split, tiles even after merge: 122 Nuclear Plant Epsilon CH18 (1009 mt, 1189 tiles
    at K=4).
  - Fit with the K=4 merge alone, no split: 60 Burole CH28 (952), 209 / 213 CH59 (939 / 955),
    151 Amatree CH30 (989), 146 Tsukinami CH49 (996), 128 Legen CH54 (1003) — the last three
    with < 40 tiles spare.
  - 84 and 143 also exceed the 128 KiB per-tileset animation-art budget (177 / 131 KiB).
  - Not re-checked: maps that fit in July but sat near a cap.
- **Metatile merge (2026-10-06, `metatile_merge.py`):** metatiles that draw identically with the
  same behavior + layer type can share an id (collision lives in map.bin). Lossless merge alone:
  40 1277→1051, 143 1065→894, 144 1061→777, 117 1208→1003, 84 1247→861, 187 1412→1186,
  101 1556→1193, 94 1815→1363; after K=4 tile merge: 1005 / 878 / 695 / 988 / 803 / 1162 /
  1064 / 1208. So 117, 143, 144, 84 no longer need splitting; 187, 101, 94 still do.
- **Map 40 unsplit (`single_map_fit.py`, exact emit, incl. void + build copies):**
  current rule + metatile merge 1052 mt / 1544 t; + K=4 **1007 mt / 1080 t** (−56 tiles);
  min-bake + metatile merge 1101 / 1425; min-bake + K=4 **1048 mt / 1026 t** (−24 mt, −2 t).
  Min-bake costs metatiles (separate layers expose differences baking hid). Neither variant
  fits; a per-column hybrid might, with ~zero headroom.
- **K=5 / K=6 (`k6_map40.py`):** current rule + metatile merge: K=5 992 mt / 1040 t (over);
  **K=6 989 mt / 1005 t — FITS UNSPLIT (+35 mt, +19 tiles spare)**. Min-bake: K=5 1039/1004,
  K=6 1039/972 (metatiles over). By eye (`map40_k6_{north,southwest,east}.png`): K=6 ≈ K=4 —
  "SUBWAY" sign intact, gym roof panels intact; K=8 still garbles the sign. Already at K=4 the
  flat grey roofs' grid texture gets noisier than the original.
- **Per-group K (`k_groups_map40.py`; `classify_tile` group: rock 81 / green 470 / other 1171
  static quads; merges stay within a group):** (rock/green K, other K) → metatiles / tiles:
  (4,4) 1011/1103 · (8,4) 994/1031 · **(12,4) 982/992 fits +42/+32** · (16,4) 976/960 ·
  **(8,6) 993/996 fits +31/+28** · (12,6) 981/957 · (16,6) 975/925 (+49/+99). By eye
  (`map40_kgroups_*.png`): trees, grass, cliffs fine at every level; **but "green" is a hue
  family, not foliage** — the green-roofed building (east) loses its brick pattern at K=16 and
  its door emblem softens from K=12. Fix if pursued: apply the high K only to green/rock tiles
  from non-building columns (or exclude priority/solid building columns).
- **Step 3: border-strip import.** Check fieldmap.c first: imported strip metatiles must sit
  at the SAME IDs in both tilesets, or the neighbour's raw IDs resolve wrong. That decides
  whether any stitched seam is possible, or whether every seam stays an arrow warp.
- Kevlar↔R02 could then go back to a real seam.
