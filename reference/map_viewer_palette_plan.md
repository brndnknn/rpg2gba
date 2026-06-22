# Plan: Palette + color-mapping view in the map tile viewer

> Resume doc. Mirrors the approved plan at `~/.claude/plans/i-want-to-add-mutable-minsky.md`.
> Status: approved, implementation not yet started. Built under `/delegate` (delegation-first) mode.

## Context

The map viewer (`scripts/build_map_viewer.py` static builder + `scripts/map_viewer_server.py`
+ shared core `scripts/map_viewer_common.py`) lets us inspect converted Uranium maps
cell-by-cell during the per-slice review gate. It can show RMXP source layers and a "GBA"
metatile layer, plus collision/priority/event overlays — but it is **blind to palettes**.

We want to debug the quantizer (the lossy step where RPG-Maker truecolor art is forced
into GBA 16-color sub-palettes). The user wants, per tile:

1. The **RPG Maker palette** it uses (the artist's source colors).
2. The **GBA palette** it uses (the assigned ≤15-color sub-palette).
3. **Which colors got changed to which** (original → quantized mapping).

Plus a true **post-quant canvas layer** so the whole map can be viewed in real quantized
colors (the `post-quant` toolbar option is currently stubbed but unimplemented; spec
`reference/map_inspector_spec.md` §9 A3 anticipates this "palette-bug hunt" panel).

This serves the §9 per-slice boot/art gate and the standing "validate graphics by eye"
norm — averaged shift metrics hide exactly the per-region color wrecks this view exposes.

## Key findings that drive the design

- **The viewer's "GBA" layer does NOT quantize.** `_render_column`
  (`build_slice_tilesets.py:114`) just composites raw, downscaled RMXP tiles into
  bottom/top layers. The real quantization happens only inside `emit_tileset`.
- **The real palette assignment is per-tileset, over the full pool** of column-keys
  across *all maps sharing that tileset* (`build_slice_tilesets.py:191-256`), fed to
  `emit_tileset` → Step 1 canonicalizes 8×8 quadrants, Step 2 calls
  `build_quantized_tileset` (`emit.py:120-202`). So a tile's palette depends on what
  other tiles share the tileset — a per-map quantize would diverge from the ROM.
- **The original→quantized color mapping is computed then discarded.** In
  `quantize.py:258-270` each tile's pixels are snapped to its palette
  (`new = pal[_nearest(px, pal)]`); only aggregate shift stats survive in
  `QuantizeResult.stats`. The per-color pairs are never returned.

Chosen approach (confirmed with user): **run the real emit/quantize code path** so the
viewer matches the shipped ROM by construction, and **capture** the color mapping at its
source rather than reverse-engineering on-disk `.pal`/`tiles.png`/`metatiles.bin`.

## Design

### Data contract (lead owns this; pinned so tasks can run in parallel)

**`QuantizeResult.color_map`** (new field, `quantize.py`): `list[list[tuple]]` indexed by
input-tile — for each tile, the distinct opaque-pixel mapping
`(orig_rgb8, final_rgb8)` where `orig_rgb8` is the tile's original 8-bit color and
`final_rgb8` is the GBA palette color it became (so a single arrow captures *both* the
8→5-bit truncation and the palette snap — the end-to-end "what changed"). Derive from
`resolved[i]` (pre-`to_5bit`) and the already-computed `new`/`pal`.

**`analyze_tileset_palettes(metatile_list) -> PaletteAnalysis`** (new, in `emit.py`):
reuses emit Steps 1–2 (factor the canonicalize + `build_quantized_tileset` core into a
shared helper that both `emit_tileset` and this analyzer call — so they cannot drift).
Returns, without writing files:
- `palettes`: `list[list[rgb8]]` — the sub-palettes (index 0 = transparent).
- per metatile (by list position = column-key order): for each of the 8 quadrants its
  `palette_index`, and the quadrant's `color_map` slice (orig→final pairs).

**`build_map_data` additions** (`map_viewer_common.py`): a top-level `palettes` block
(the sub-palette swatch colors), `rmxp_tile_colors` (`{tile_id: [[r,g,b],...]}` distinct
source colors per used tile, from `TileRasterizer.render`), and per-cell
`gba_palette_indices` + `color_changes` keyed off the cell's column-key.

**Render layer names** (pinned, so the static builder + server can be built against them):
`render_metatile_png(map_id, idx, layer)` gains `layer="post_bottom"` and
`layer="post_top"` returning the *quantized* composited quadrants reassembled into 16×16.
Front-end `post-quant` base layer composites `post_bottom` + `post_top`.

### UI (inside the `MAP_VIEWER_HTML` template in `map_viewer_common.py`)

- Toolbar: add `<input type=radio name=layer value="post-quant"> Post-Q`; add a
  `drawCellBase` branch compositing the two post layers via `getMetatileURL`.
- `updateSidebar()`: new **Palettes** section for the selected cell —
  - *RMXP palette*: swatch strip of the cell's source colors (from `rmxp_tile_colors`).
  - *GBA palette*: a 16-swatch strip per distinct sub-palette the cell's metatile uses
    (index 0 rendered as a transparency checker).
  - *Color changes*: `origSwatch → quantSwatch` rows, changed entries flagged; hover
    shows hex + BGR555 value. Default to showing changed colors, with a "show all" toggle.

## Files to change

| File | Change | Owner |
|---|---|---|
| `src/rpg2gba/tileset_converter/graphics/quantize.py` | add+populate `QuantizeResult.color_map` | Task A |
| `tests/test_graphics_quantize.py` | test color_map capture | Task A |
| `src/rpg2gba/tileset_converter/graphics/emit.py` | factor Steps 1–2 into shared core; add `analyze_tileset_palettes` | Task B |
| `src/rpg2gba/tileset_converter/graphics/build_slice_tilesets.py` | expose per-tileset pool gathering for the analyzer (reuse existing logic) | Task B |
| `tests/test_build_slice_tilesets.py` | assert `emit_tileset` output byte-identical after refactor | Task B |
| `scripts/map_viewer_common.py` | backend plumbing (`_ensure_loaded`, `build_map_data`, `render_metatile_png` post layers) **and** the embedded HTML/JS UI | Task C |
| `scripts/build_map_viewer.py` | render + inline post-quant metatile PNGs | Task D |
| `scripts/map_viewer_server.py` | serve `post_bottom`/`post_top` via `/api/metatile` | Task D |
| `reference/map_inspector_spec.md` | document the new panel + layer | Lead/Haiku |

Note: `map_viewer_common.py` holds **both** the Python data layer and the embedded
HTML/JS template, so it is a single-owner file (Task C does both halves) — front-end and
backend cannot be split across concurrent writers.

## How `/delegate` is used (explicit)

**Planning (done).** Research was fanned out to **2 parallel `Explore` agents** (one
mapped the viewer tool, one mapped the graphics/quantize pipeline). The lead (Opus) then
read the critical files directly (`map_viewer_common.py`, `quantize.py`,
`build_slice_tilesets.py`, `emit.py`), made the design calls, and authored this plan —
per the delegate skill, research is delegated but synthesis + the plan stay with the lead.

**Implementation (post-approval) — model routing + file partitioning.** All coding tasks
go to **Sonnet** (`general-purpose`); the doc summary can go to **Haiku**; the lead keeps
integration, the shared data-contract above, the final test run, and any git/commit step.
File sets are disjoint per round (no two writers touch one file):

- **Round 1 — parallel (disjoint files):**
  - *Task A (Sonnet)* — owns `quantize.py` + `tests/test_graphics_quantize.py`.
  - *Task B (Sonnet)* — owns `emit.py` + `build_slice_tilesets.py` + `tests/test_build_slice_tilesets.py`.
  - Both consume the pinned `color_map` contract; lead runs the combined suite after they return.
- **Round 2 — parallel (disjoint files), after Round 1 merged:**
  - *Task C (Sonnet)* — owns `scripts/map_viewer_common.py` (data layer + UI).
  - *Task D (Sonnet)* — owns `scripts/build_map_viewer.py` + `scripts/map_viewer_server.py`,
    built against the pinned render-layer names.
- **Lead (Opus)** — pins/maintains the data contract, integrates each round, runs the full
  `pytest` + a manual viewer build, cross-checks exactness against an emitted `.pal`,
  updates `MEMORY.md`, and owns any commit. *Task E (Haiku)* may draft the
  `map_inspector_spec.md` update from the lead's notes.

Each brief will be full prose (cold-start agents): goal, exact files to touch, the pinned
contract, what to return. Results are relayed back here, not shown to the user directly.

## Verification

1. **Unit:** `pytest tests/test_graphics_quantize.py tests/test_build_slice_tilesets.py` —
   color_map populated; `emit_tileset` output unchanged after the refactor.
2. **Full suite:** `pytest` — no regressions.
3. **Build + eyeball (per "validate by eye"):** `python scripts/build_map_viewer.py 32`,
   open `output/map_viewer/Map032.html`: toggle the **Post-Q** layer (map renders in
   quantized colors), click cells, confirm the **Palettes** section shows RMXP colors, GBA
   palette swatches, and changed-color arrows.
4. **Server smoke:** `python scripts/map_viewer_server.py`, load a map, toggle Post-Q,
   click cells — post-quant tiles fetch and palette data renders.
5. **Exactness spot-check:** for one cell, compare its GBA palette swatches against the
   emitted `data/tilesets/.../palettes/NN.pal` for that tileset (a couple of colors).

## Resume checklist (where to pick up)

- [x] Round 1: Task A (`quantize.py` `QuantizeResult.color_map`) + Task B (`emit.py` `analyze_tileset_palettes`/`PaletteAnalysis`, `build_slice_tilesets.column_keys_for_maps`) — ran serial (B depends on A's field). 41 tests pass; emit output unchanged.
- [x] Lead: integrated Round 1, `pytest tests/test_graphics_quantize.py tests/test_build_slice_tilesets.py` = 41 passed; API imports verified.
- [x] Lead: extended analyzer (`emit.py`) to also return per-metatile quantized `quant_bottom`/`quant_top` (exact reassembly w/ flips, verified); 41 tests still pass.
- [x] Round 2: Task C (`map_viewer_common.py`: full-pool analysis cache, `_MapState.metatile_imgs_postquant`, `render_metatile_png` post-layers, `build_map_data` keys `palettes`/`rmxp_tile_colors`/`colkey_palettes`, Palettes sidebar section + Post-Q layer + swatch CSS) + Task D (`build_map_viewer.py` inlines post_bottom/post_top; `map_viewer_server.py` whitelists them) — ran parallel, disjoint files.
- [x] Lead: full `pytest` = 506 passed, 11 skipped, **2 pre-existing unrelated failures** (`test_build_slice_constants` / `test_build_slice_maps_smoke`: `MAP_MOKI_TOWN` vanilla collision in the map-constants path — fail identically on clean HEAD, not this feature). Built `output/map_viewer/Map002.html` (363 KB); all new markers present.
- [x] Post-Round-2 (lead, on the running server, map 32):
  - **Slice-scoped pool fix** — `_ensure_tileset_analysis` now scopes to `SLICE_MAP_IDS=[49,48,32]` ∪ opened map (filtered by tileset), keyed/cached by the matched map-id set, result stored on `_MapState`. Fixes the map-32 rasterizer crash (a non-slice Route map on shared tileset 22 referenced an out-of-atlas tile) and matches the ROM's per-tileset pool.
  - **Raw-vs-post-quant inspector** — GBA Metatile section now shows both raw (pre-quant) and post-quant (shipped) bottom/top thumbnails.
  - **Merge indicators** — `colkey_palettes` gained `quadrant_fit`/`merge_colors`/`merge_severity` (a "merge" = `orig>>3 != final>>3`, i.e. real snap not 8→5 truncation); new **Merge** overlay (severity heat-map), per-8×8-quadrant fit badges (green/amber/red) in the inspector, and a collapsible **Worst palette merges** panel (top-20, click-to-jump).
- [x] Engine check (delegated, read-only): BG-palette budget — `max_palettes=13` is a HARD boundary (14/15 = dialogue window pals; 13 unblended by weather/time). Recorded in `graphics_conversion_notes.md §11`. Moki ts22 = 381 colours vs 195 ceiling → merging is a budget constraint.
- [x] Docs updated: `graphics_conversion_notes.md §11`, `MEMORY.md` Map Inspector entry, this resume doc.
- [ ] USER (per-slice gate §9): walk the live viewer — Post-Q layer, raw-vs-post-quant compare, Merge overlay + Worst-merges panel on map 32.
- [ ] Open follow-up (not done): full-pool/slice analysis first-load cost on heavy tilesets (e.g. ts19) is unmeasured; `map_inspector_spec.md` not yet updated for the palette feature; non-slice maps analyze themselves alone (no shipped truth). `SLICE_MAP_IDS` must track `assemble_pathfinder.SLICE_MAP_IDS` if the slice widens.
