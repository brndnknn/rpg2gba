# Spec — Uranium Map Inspector (HTML viewer/editor)

**Status:** draft for review. **Author:** build agent, 2026-06-22.
**Supersedes:** the ad-hoc debug scripts `scripts/tree_debug.py` (per-layer render)
and `scripts/compare_collision.py` (collision diff) — the inspector generalizes both
into one interactive surface and reuses their data layer.

## 1. Purpose

A browser tool to inspect a converted Uranium map **cell-by-cell** — RMXP source
(3 layers) vs GBA output (2 layers), collision (ours vs Uranium ground-truth),
metatiles, palettes, events, metadata — and to **flag and override** conversion
problems. It is the working surface for the per-slice §9 boot-review gate: walk a
map, see exactly why each cell came out the way it did, and record/fix defects.

## 2. The one hard constraint (read first)

CLAUDE.md §4.4 / §11: **the converter output in `output/` is generated; you fix the
input, never the output.** So the "editor" must **never write to `output/`.** Every
edit persists to a **source-of-truth override file under `reference/`**, and the map
is re-derived by re-running the deterministic converter. This keeps idempotence
(§4.2) intact and means "editing the map" == "editing an override + rebuild." Any
edit type whose override file + converter hook does not yet exist is a *converter
feature to add first*, not something the HTML can fake. This is the gating design
fact, not a detail.

## 3. Scope

**In:** per-cell inspection; per-layer + composite rendering; collision overlay +
ours-vs-Uranium diff; priority/terrain/event/warp overlays; post-quant ("what's in
the ROM") view; issue annotation/export; a bounded override set (§6).

**Out (now):** authoring map *geometry* (we don't redraw Uranium maps); palette
editing; editing many maps at once; anything touching `output/` directly.

## 4. Data sources (all already on disk)

| Data | Source | Notes |
|---|---|---|
| Tile grid (3 layers), w/h, tileset_id, events | `output/uranium-build/maps/MapNNN.json` | `tiles{xsize,ysize,zsize,data}`, flat row/layer-major |
| passages / priorities / terrain_tags / names | `output/uranium-build/tilesets.json` keyed by ts id | per tile_id |
| RMXP tile image (16×16 RGBA) | `tileset_converter.graphics.raster.TileRasterizer.render(tid)` | 0=empty, 48–383=autotile, ≥384=atlas |
| GBA metatile (bottom/top 16×16) | `graphics.build_slice_tilesets._render_column(key, rast, pri)` | the priority split (pri>0 → top) |
| GBA collision (ours) | `layout._cell_blocked` / `collapse_column` | single-bit collapse |
| Uranium-truth collision | `scripts/compare_collision.uranium_passable` | faithful `playerPassable?` |
| Post-quant ROM bytes (optional) | emitted `tiles.png` + `metatiles.bin` + `palettes/*.pal` | decode for true on-ROM pixels |
| Existing overrides | `reference/tileset_map.json`, `strip_list.json`, `map_name_overrides.json` | read + (some) write |

## 5. Architecture — two phases

**Phase A — Viewer (static, no server).** A build script
`scripts/build_map_viewer.py` loads the map + tilesets, pre-renders every *used*
tile and metatile to base64 PNG, serialises cells+metadata to JSON, and emits one
self-contained `output/map_viewer/MapNNN.html` (data + vanilla JS inline). Open
locally **or send to the phone via Taildrop.** Read-only. Immediately useful, zero
infra, low risk.

**Phase B — Editor (thin local server).** `scripts/map_viewer_server.py` serves the
same UI plus a small REST API:
- `GET /api/map/<id>` → cells + metadata (JSON)
- `GET /api/tile/<ts>/<tid>.png`, `GET /api/metatile/<id>.png` → lazy renders
- `POST /api/override` → write one override to the right `reference/*.json`
- `POST /api/rebuild/<id>` → re-run the converter for this map, return fresh data
Runs on the Ubuntu desktop; browser at `localhost`. **Flask** (installed into the
project `.venv`, declared in `pyproject.toml`) for routing / JSON / static serving —
new deps are fine now as long as they live in the venv, not the machine (CLAUDE.md
§10). stdlib `http.server` remains a zero-dep fallback if we'd rather not add Flask.

**Recommendation:** ship A, then add B when you actually need edits to persist.

## 6. Override model (the editor's real contract)

| Edit action | Persists to | Converter consumer | Exists? |
|---|---|---|---|
| Force cell walkable/blocked | `reference/collision_overrides.json` `{map:{"x,y":0/1}}` | `layout.convert_layout` (like `warp_overrides`) | **new hook** |
| Move a tile_id → GBA top/bottom | `reference/layer_overrides.json` `{ts:{tid:"top"/"bottom"}}` | `_render_column` priority split | **new hook** |
| Substitute a tile / map a column | `reference/tileset_map.json` (+ `.gen.json` overlay) | `tile_map.lookup` / `lookup_column` | exists |
| Mark warp cell | warp trace input | `convert_layout` `warp_overrides` | exists |
| Strip a cell/event/map | `reference/strip_list.json` | strip pass | exists |
| Annotate / flag issue (no convert change) | `reference/map_issues.json` | none (review punch-list) | **new, trivial** |

The two **new hooks** (collision_overrides, layer_overrides) are the editor's main
prerequisite work — and they're exactly the two bug classes we've already hit
(faithful-but-want-to-override collision; tree-canopy-on-wrong-layer). Annotation is
free and worth doing first regardless.

## 7. UI

- **Canvas:** map as a zoom/pan grid, composite by default; hover → coords, click →
  select cell.
- **Layer selector:** RMXP composite | L0 | L1 | L2 | GBA composite | GBA bottom |
  GBA top | post-quant.
- **Overlays (toggle, drawn over the layer):** collision (red/green); **collision
  diff** (highlight ours≠Uranium); priority heatmap; terrain tags; events; warps;
  override markers.
- **Cell inspector (sidebar) for the selected cell:** coords, tileset; per RMXP
  layer → thumb + tile_id + passage (binary) + priority + terrain (+ autotile name);
  column_key → resolved metatile id, bottom/top thumbs, layer_type, behavior;
  collision ours vs Uranium (mismatch flag); active overrides.
- **Edit controls (Phase B):** force collision; tile→layer; substitute; warp; strip
  — each posts an override, optional rebuild + refresh.
- **Issue list:** flagged cells + notes, export JSON = the per-slice review list.

## 8. Tech

- Backend/build: Python, reuse the existing package (rasterizer/layout/quantize/
  compare_collision). Server = **Flask** in `.venv` (or stdlib `http.server` for zero deps).
- Frontend: vanilla JS + `<canvas>`, single file, no build step. Base64 images in A,
  lazy-fetched in B. Overlays = semi-transparent canvas passes.

## 9. Phasing / rough effort

- **A1** static viewer: composite + per-layer + cell inspector. (~½ day)
- **A2** overlays: collision + diff + events + priority.
- **A3** post-quant decode panel (serves the deferred palette-bug hunt).
- **B1** stdlib server + lazy tile API (same UI).
- **B2** override write + rebuild for collision & layer (needs the §6 new hooks).
- **B3** issue-list export.

## 10. Open decisions (for the user)

1. **Scope now:** viewer-only (A), or commit to the editor (B) too? (Rec: A first.)
2. **Primary target:** phone (static file via Taildrop) or desktop (localhost
   server)? Editing implies desktop.
3. **First override to wire** (if B): collision, or tile→layer (the tree canopy)?
4. **Annotation pass:** want the free issue-flagging/export in A1 as the review
   punch-list?
