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

## Done this session (uncommitted, tests green)

- `src/rpg2gba/tileset_converter/graphics/palette_families.py` + `tests/test_palette_families.py`
  (13 tests): `seam_components(rows, map_ids)`, `compute_component_palettes(lists)`,
  `make_pinned_quantizer(palettes)` (a `quantizer=` hook for `emit_tileset` /
  `analyze_tileset_palettes`). Library only; nothing consumes it yet. Reviewed by lead.
- `scripts/verify_viewer_rom_match.py` Mode A rewritten for per-map synth tilesets; it now
  calls the real `build_slice_tilesets` with stubbed writes. **18/18 slice maps pass,
  0 px diff** against the 10-02 artifacts. Mode B refuses (exit 1) until the viewer is fixed.
  `tests/test_verify_viewer_rom_match.py` (3 tests).
- Open aside: stale `engine/data/tilesets/primary/uranium19`, `uranium22`, `*_cmp*` dirs —
  check whether tracked; likely delete.

## Step 4 progress (2026-10-04, uncommitted)

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
5. **G3t and V1 are tuned on CH01–06 art only.** Later chapters will add tilesets: decide whether
   the fixed palettes are frozen (stable colours across chapters) or refit (which re-colours
   shipped chapters).
6. **Viewer and oracle parity.** Any of P1–P3 must go into `map_viewer_common` and
   `verify_viewer_rom_match.py` in the same change, or the viewer stops telling the truth.
7. **Persisted artifact.** P2's palettes plus the tile→palette table would be a new committed
   intermediate (`.gen.json`). Ask first (CLAUDE.md §10), same as step 2's palette-families file.

### How this relates to steps 2–4 above

P2 generalises step 2: game-wide groups instead of per-seam components. The two can stack: fixed
groups first, then the seam component's palettes for the remaining slots. P1 is orthogonal and
helps every map, seam or not. The **Seam palettes** viewer toggle (step 4) previews step 2 only;
none of P1–P3 is in the viewer yet.

## Later (not approved)

- **Step 1: split map 40** so each piece fits under the caps. Measure the cut lines first.
- **Step 3: border-strip import.** Check fieldmap.c first: imported strip metatiles must sit
  at the SAME IDs in both tilesets, or the neighbour's raw IDs resolve wrong. That decides
  whether any stitched seam is possible, or whether every seam stays an arrow warp.
- Kevlar↔R02 could then go back to a real seam.
