# Map viewer — performance & fidelity backlog

Investigation 2026-06-28 into two complaints about the map viewer
(`scripts/map_viewer_server.py` + `map_viewer_common.py`, quantizer under
`src/rpg2gba/tileset_converter/graphics/`):

1. New pages and re-quantized pages load **really slowly**.
2. The quantized preview **doesn't match the original game** — colours are
   sometimes off, and things are sometimes layered differently.

This doc records what was fixed, the measured root cause, and the remaining
work so we can come back to it.

---

## Framing: the viewer is (meant to be) a faithful ROM preview

The viewer has two render modes. **"RPG Maker" mode** draws the original Uranium
art in true z-order (the ground truth). **"Quantized" mode** runs the *same code
path the ROM build uses* (`_render_column` + `build_quantized_tileset_family` over
the same map pool). So the differences you see between the two modes are **real
conversion losses, not viewer bugs** — fixing them improves the ROM, not just the
preview.

**Caveat discovered (see "Viewer-vs-ROM pooling drift" below): the viewer's pool
is now STALE relative to the per-map-synthetic-id packing the ROM uses.** The
viewer still pools by the real `tileset_id` stored in the map JSONs, so it can
over-constrain palettes vs the actual ROM.

---

## Performance

### What was done (2026-06-28) — the three quick wins

All three are committed in `raster.py` + `map_viewer_common.py`:

1. **Startup `tileset_id → map_ids` index** (`map_viewer_common.py:_get_tileset_index`).
   `_ensure_tileset_analysis` used to `glob("Map*.json")` and JSON-parse **all ~300
   maps on every cache miss** just to find the ones sharing a tileset. Now the
   directory is scanned **once per session** into a cached index; subsequent misses
   are an O(1) lookup, and a warm analysis returns without reading any map JSON.

2. **Preserve the warm rasterizer across re-quant** (`set_quantize_params` +
   `_refresh_postquant` + a `quant_generation` token on `_MapState`). Re-quant used
   to `_map_cache.clear()`, throwing away every map's `TileRasterizer` PIL cache and
   pre-quant metatile composites. Now re-quant only drops the *quant-dependent*
   caches (`_tileset_analysis_cache`, `_metatile_png_cache`) and bumps a generation
   token; `_ensure_loaded` lazily re-runs **only the quantize step** for a map the
   next time it's touched — grids and tile renders survive.

3. **numpy the two per-pixel Python loops**:
   - `raster.downscale_2x` — the 2×2-block top-left sampler is now `arr[0::2, 0::2]`
     (byte-identical; guarded by `test_graphics_raster.py`'s `.tobytes()` test).
   - `map_viewer_common.build_map_data` `rmxp_tile_colors` — distinct-colour dedup is
     now `np.unique(visible, axis=0)` instead of a Python `for px in visible` loop.

### Measured impact (tileset 22 / Moki Town, 6-map pool, 3741 pool keys)

| Step | Time |
|---|---|
| `column_keys_for_maps` + filter | 0.06s |
| `_render_column` × 3741 (cold tile cache) | 0.15s |
| `_render_column` × 3741 (warm cache) | 0.12s |
| **`analyze_tileset_palettes` (quantize)** | **22.3s** |
| `build_map_data` recompute (cache hit) | 0.15s |

So for a big outdoor tileset the page load and every re-quant are **~22s, and ~all
of it is the quantizer.** The quick wins help cold-load I/O (300 reads → 1), small
interior maps (where quantize is cheap and the glob was a bigger share), and same-map
re-navigation — but they **do not move the headline number** on large maps, because
that number is the quantizer.

### The real bottleneck — the agglomerative palette packer (deeper fix)

`cProfile` of the quantize step: **`int.bit_count` called 186 million times = the
dominant cost**, inside `build_quantized_tileset` (`quantize.py:161`). It's the
exhaustive pairwise-union scan of the greedy merge loop (`quantize.py:242-255`):

```python
while len(masks) > max_palettes:          # ~ (k - max_palettes) steps
    for x in range(len(masks)):           # O(k)
        for y in range(x + 1, len(masks)):# O(k)  -> O(k^2) per step
            u = (mx | masks[y]).bit_count()
```

With k ≈ 1000 distinct colour-set bitmasks reduced to 13 palettes, that's
O(k²·(k−13)) ≈ 1.6×10⁸ union-popcounts — matching the 186M measured. This runs
**once per hue-family subset** (9× here via the family packer), on first load of a
tileset *and* on every re-quant.

**Fix options (ranked):**

1. **Vectorise the pairwise-union matrix with numpy.** Pack each mask into a few
   `uint64` words (vocab ≤ 195 bits → 4 words); compute the full k×k union-popcount
   matrix with broadcasting + a popcount, take the argmin. After each merge only one
   row/col changes, so update incrementally. Turns the inner Python double loop into
   numpy. Biggest, most self-contained win.
2. **Heap of `(union_size, i, j)` pairs** with lazy invalidation — classic
   greedy-merge acceleration, O(k² log k). More code than the numpy matrix.
3. **Free subset-collapse pre-pass.** Any mask that is a subset of another merges
   into it at zero colour cost; doing all of those first shrinks k cheaply before
   the O(k²) loop. Cheap, but only a constant-factor help.

⚠ `quantize.py` feeds the **ROM build** — any change here must produce identical (or
explicitly validated-equivalent) palettes. Validate against a golden quantize of
Moki Town before landing.

### Smaller remaining perf items (cheap, lower impact)

- **`resolve_alpha` recomputed 3× per tile** in `build_quantized_tileset_family`
  (`quantize.py:477, 485, 199`). Resolve once, pass the resolved tiles down.
- **`tilesets.json` parsed twice per cold map load** (`map_viewer_common.py:267` then
  again inside `load_tileset_sources`, `sources.py:142`). Parse once, share.
- **Pool-metatile render not cached separately from the analysis.** Currently moot
  (render is 0.15s vs 22s quantize), but if the quantizer is fixed, cache the
  param-independent `_render_column` pool results keyed by `frozenset(map_ids)` so a
  re-quant skips re-rendering too.
- **`build_map_data` recomputes every GET** (cells grid, palette tables) even on a
  cache hit. Measured at 0.15s for a 4608-cell map — fine for now; cache its
  param-independent parts in `_MapState` only if it becomes a problem.

---

## Fidelity — colours

The viewer's Quantized mode is what the ROM renders; colour differences from the
original game come from:

### Fundamental (GBA hardware — cannot be removed)

- **8-bit → 5-bit per channel** (`quantize.py:to_5bit`, `:49-55`). ±7 per channel.
  Currently floors; **round-to-nearest would halve the average error** — a small,
  safe improvement (verify it doesn't break golden tests).
- **16 colours per palette.** When a merged palette group exceeds 15 colours it's
  median-cut reduced (`quantize.py:257-263`) and minority colours snap to a
  neighbour. Dense tilesets (Moki Town: 381 distinct 5-bit colours into ≤195 / 15
  per palette) hit this constantly. The *degree* of loss is tunable (below).

### Avoidable (quantizer choices — these are the "close but off" cases)

1. **Shadows vanish entirely.** Uranium's ~33%-uniform-alpha shadow tiles classify
   as `"drop"` (`quantize.py:46, 80-96` — `SOLID_BODY_FRAC = 0.02`), so the whole
   tile goes transparent and the ground shows through. Probably the most visible
   "doesn't look like the game." Was a deliberate call (stipple rejected for scroll
   shimmer). **A third per-tile mode (50%-threshold → opaque shadow) would bring
   shadows back** without shimmer, at the cost of opacity.
2. **Dominant-hue misclassification** (`quantize.py:_dominant_family`, `:347`). A
   mixed/transition tile is assigned wholesale to one hue family by its single
   most-common pixel; its minority colours then compete in the wrong palette and
   shift. Same class as the old "paths turn green" bug. Fix: multi-colour family
   voting, or give straddling tiles budget from both families.
3. **Over-budget palette merges** (the 16-colour item above). Better hue-family
   splitting (tune `FamilyParams.green_cuts` / `palette_floor` — already exposed as
   the viewer's runtime knobs) keeps more groups under 15.
4. **Transparent-pixel RGB contamination** on threshold-mode fringe pixels
   (`quantize.py:88-93`). Uranium stores non-black RGB under transparent pixels;
   pixels with 128 ≤ alpha < 255 are kept at their source RGB before the palette
   snap. Fix noted in `graphics_conversion_notes.md §1` but not done: normalise
   transparent RGB to the nearest opaque neighbour before quantizing.

---

## Fidelity — layering

A **fundamental architectural mismatch**, but the damage is bounded and locatable.

- RMXP has **3 tile layers + per-tile priority**; a GBA metatile has only **2 BG
  layers** (bottom, then player, then top). The collapse
  (`build_slice_tilesets.py:_render_column`, `:115-141`) puts all priority==0 tiles
  on the bottom layer and all priority>0 tiles on the top layer.
- **Layer inversion:** wherever a column has a priority>0 tile on a *lower* z than a
  priority==0 tile, the GBA composite renders them in the opposite order from RMXP's
  z-order. That's the "things layered different."
- **Priority is per-tile-id** in RMXP (`build_slice_tilesets.py:129`), so a tile
  flagged priority>0 goes over the player *everywhere* it appears — no per-cell
  override.

**It's a permanent 2-layer limit, but the failing cells are few and findable.** A
one-time census over the map JSONs — flag every column where
`priority[tile(x,y,z)] > 0 AND some tile(x,y,z') with z' > z has priority == 0` —
identifies every inversion. Those could then be special-cased or fixed at the
source-map level. The viewer already lets you *see* each one by toggling RPG Maker
vs Quantized mode (`map_viewer_common.py:944` z-order vs `:956-958` bottom/top).

Non-issues confirmed during the investigation: warp-override metatiles are visually
identical to their column (only the behaviour differs); empty-autotile-slot tiles
render transparent and compose correctly.

---

## Viewer-vs-ROM pooling drift (important)

The viewer's `_ensure_tileset_analysis` pools **all maps sharing the real
`tileset_id`** in the map JSONs (e.g. tileset 22 → maps [31,32,33,35,39,94], 3741
pool keys). But the ROM build now uses **per-map synthetic tileset ids**
(`1000 + map_id`, `phase5.convert_all`) — it packs **each map's palette alone**.

So the viewer currently **over-pools**: it quantizes 6 maps' colours into one
13-palette budget, while the ROM gives each map its own 13 palettes. The viewer can
therefore look **more colour-starved than the actual ROM**, and its "faithful
preview" docstring is stale. To realign the viewer with production it should pool
per-map (synthetic-id) the way `phase5.convert_all` does. This also happens to
shrink k dramatically (per-map pools are far smaller than the 6-map pool), which
would cut the quantize time as a side effect.

---

## Pointers

- Quantizer: `src/rpg2gba/tileset_converter/graphics/quantize.py`
- Layering / column collapse: `src/rpg2gba/tileset_converter/graphics/build_slice_tilesets.py`,
  `src/rpg2gba/tileset_converter/layout.py`
- Viewer: `scripts/map_viewer_common.py`, `scripts/map_viewer_server.py`
- Design notes: `reference/graphics_conversion_notes.md`
- Production per-map packing: `src/rpg2gba/tileset_converter/phase5.py` (`convert_all`)
