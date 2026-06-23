# Map Viewer — Uranium tile/palette review tool

A browser-based tool for eyeballing how a Uranium map converts to GBA art:
the metatile layout, the RMXP→GBA layer collapse, and the palette quantization.
Built for the per-slice §9 boot gate — "does this map render as real Uranium art?"

**It is one tool, not two.** There are two *views* (map grid + palette inspector)
and two *delivery modes* (live server + self-contained file), all behind one shared
core. Don't go looking for a second viewer.

---

## TL;DR — just show me a map

```bash
python scripts/map_viewer_server.py --port 8765
```

Open `http://localhost:8765/` (or `http://<hostname>:8765/` over Tailscale/LAN —
it binds `0.0.0.0`, so your phone works too). The **landing page** is a searchable,
location-grouped index: every map by **id + descriptive name**, type-to-filter,
nested by RMXP parent so a town's interiors sit under it. Each row links to both
views. One launch serves both views for every map.

Currently the data pool is the pathfinder slice — **maps 49, 48, 32** (plus whatever
map you open). Other maps may render but aren't guaranteed (the tileset atlas is
quantized over the slice only; see "Scope & caveats").

---

## Architecture (why it's split across files)

```
map_viewer_common.py        ← shared CORE (data + rendering + map-grid template)
├─ build_map_data(map_id)       extract cells / metatiles / palette usage  →  dict
├─ render_tile_png()            one RMXP 16×16 tile  →  PNG
├─ render_metatile_png()        one metatile layer (bottom/top/post_*)  →  PNG
└─ MAP_VIEWER_HTML              the map-grid VIEW (template)

build_map_viewer.py         ← STATIC mode  (self-contained .html, base64-inlined)
└─ build_config(map_id)         map data + every tile/metatile as base64 PNG

palette_page.py             ← second VIEW: the palette inspector
└─ PALETTE_VIEWER_HTML          palette swatches + suspect-tile grid + colour-change popup

map_graph.py                ← map RELATIONSHIPS (no rendering, pure metadata)
├─ build_index()                landing-page data: flat name list + parent_id forest
└─ map_relationships(id)        per-map nav: name, parent, children, warp targets

map_viewer_server.py        ← SERVER mode  (live HTTP, lazy /api/* PNG rendering)
```

The dependency chain proves it's one system:
`palette_page.build_palette_html()` → `build_map_viewer.build_config()` →
`map_viewer_common.build_map_data()`. The server serves both views; the static
builder emits both files. They share data extraction, rendering, and swatch helpers.

**Not part of this tool:** `tree_debug.py` — a separate script that emits a **PNG**
(not HTML) showing the per-layer RMXP→GBA collapse for one region. See its own
section below.

---

## The two delivery modes

### Server mode (recommended)

```bash
python scripts/map_viewer_server.py --port 8765        # default port 8765, host 0.0.0.0
```

Routes:

| Route | Serves |
|---|---|
| `GET /` | landing page — searchable, name + parent-tree index, links to both views |
| `GET /map/<id>` | map-grid viewer (lazy images) |
| `GET /palettes/<id>` | palette inspector (lazy images) |
| `GET /api/map/<id>` | `build_map_data` JSON |
| `GET /api/tile/<mapid>/<tid>.png` | one RMXP tile PNG |
| `GET /api/metatile/<mapid>/<idx>.png?layer=bottom\|top\|post_bottom\|post_top` | one metatile-layer PNG |

Images render lazily on request and are cached (both in the browser via
`immutable` cache headers and in a module-level cache server-side), so the first
view of a map is a little slow, then snappy. Cross-links between the two views
(`Palettes →` and `← Map` buttons) **only exist in server mode**.

### Static mode (offline / phone fallback)

Build self-contained HTML files — every tile/metatile is base64-inlined, no
server or network needed. Survives Taildrop to a phone.

```bash
python scripts/build_map_viewer.py 32 49 48      # specific maps
python scripts/build_map_viewer.py --all         # every map
```

Writes to `output/map_viewer/` (override with `--out-dir`). Per map it emits
**both** files:

- `MapNNN.html` — map-grid viewer
- `MapNNN_palettes.html` — palette inspector

You can also build just the palette page for one map:

```bash
python scripts/palette_page.py 32 [--out path.html]
```

Static files are larger (all images inlined) and have **no cross-view nav buttons
and no cross-map nav strip** (those need live routes) — open the files separately.

---

## Landing page & cross-map navigation (server mode only)

The landing page and the cross-map nav strip both need live routes, so static
files don't have them. Data comes from `map_graph.py` — pure metadata, no rendering.

**Landing page** (`GET /`, `build_index()`): every openable map by **id + name**,
type-to-filter (matches id or name), grouped into the RMXP editor tree so a town's
interiors and a dungeon's floors nest under their parent. Each row links to the map
view and the palette view.

**Cross-map nav strip** (top of both views, `map_relationships(id)` injected into
the page config as `graph`): a horizontal chip bar — **⌂ Index** · the current map ·
**up** (parent) · **sub** (child maps) · **warp→** (distinct code-201 transfer
destinations). Every chip jumps to `/map/<id>`, so you can walk the world: town →
its houses/gym → the maps its doors warp to. Shown only in server mode (the strip
stays hidden when `V.graph` is absent, e.g. static files).

**Name & tree sources:** names resolve `reference/map_name_overrides.json`
(corrected names win) → `map_infos.json` `name` → `Map{id:03d}` fallback. The tree
is the RMXP `parent_id` (editor-organization tree — reliably groups interiors with
their town and floors with their dungeon, but is **not** compass adjacency).
Overworld N/S/E/W borders (`connections.dat`, 14 sparse edges) are intentionally
**not** wired yet. The "view a whole multi-floor structure on one page" composite is
**Phase B** (not built); each floor is currently its own per-map view.

---

## View 1: the map-grid viewer (`/map/<id>`)

A zoomable canvas of the map. Title bar = "Map Inspector".

**Layer radio (what the canvas draws):**

| Option | Shows |
|---|---|
| **RMXP** | all 3 RMXP source layers composited (what RPG Maker draws) — the default |
| **L0 / L1 / L2** | one RMXP source layer at a time |
| **GBA** | both GBA metatile layers composited (pre-quantization) |
| **GBA↓ / GBA↑** | the GBA bottom / top metatile layer alone |
| **Post-Q** | the post-quantization art (palette-reduced — what the ROM actually shows) |

> RMXP vs GBA isolates the **layer-collapse**; GBA vs Post-Q isolates the
> **quantization drift**. Use them to localize where a render looks wrong.

**Overlay checkboxes (drawn on top):**

| Overlay | Meaning |
|---|---|
| Collision | passability — compares our collision vs Uranium's |
| Diff | cells where our render differs from the source |
| Priority | RMXP priority (which tiles draw above the player) |
| Merge | heat-map of palette-merge loss (brighter = more colour snapped away) |
| Events | event markers (on by default) |
| Warps | warp markers (on by default) |

**Zoom:** `−` / `+` / `Fit`, current factor shown (default 2×).

**Inspector sidebar (right):**

- Click a cell → per-layer breakdown (tile id, RMXP priority, which metatile).
- **Worst palette merges** — collapsible list of the metatiles that lost the most
  colour to quantization; click one to jump to a cell using it.
- **Issues** — flag the selected cell, attach a note, and **Export JSON**
  (downloads `MapNNN_issues.json`). ⚠️ Issues live in memory only — they do **not**
  persist across a reload; export before you close the tab.

`Palettes →` (server mode) jumps to this map's palette inspector.

---

## View 2: the palette inspector (`/palettes/<id>`)

Per GBA sub-palette, shows the 15 colour swatches (used vs unused, slot 0 =
transparent) and a grid of the metatile thumbnails that draw from that palette.

- **Suspect tiles** (≤2 colours) are border-highlighted — these are the tiles most
  likely mis-quantized (a tile that should be richer but collapsed to 1–2 colours).
- **Bad** tiles (high merge severity) get a red border.
- **Suspects only (≤2c)** button filters to just those; **Hide empty pals** collapses
  unused palettes.
- Click any tile → popup with the post-quant thumbnail (bottom+top stacked), which
  palette slots it actually uses, and every colour change
  (original source colour → snapped palette colour, changed ones flagged).

Swatch tooltips give RGB, hex, and the BGR555 value (the GBA's native 15-bit form).

`← Map` (server mode) jumps back to this map's grid viewer.

---

## `tree_debug.py` — separate per-layer collapse debugger

Not part of the viewer. Emits a **PNG** for one rectangular region, with side-by-side
panels: the 3 RMXP source layers, the RMXP composite, the GBA bottom/top layers, and
the GBA composite — coordinate-labelled, plus a per-cell text table of tile ids +
priority. The GBA columns are *pre-quantization* (`_render_column` output), so it
isolates the collapse/priority logic from quantization.

```bash
python scripts/tree_debug.py --x0 33 --y0 40 --x1 43 --y1 48 --zoom 7
```

Reach for this when a specific spot's layer stacking looks wrong and the viewer's
GBA/Post-Q toggles aren't fine-grained enough.

---

## Scope & caveats

- **Slice-scoped data pool.** The palette analysis is computed over the pathfinder
  slice (`SLICE_MAP_IDS = [49, 48, 32]`) plus the opened map, matching how
  `build_slice_tilesets` quantizes each tileset over only the slice maps that share
  it. Opening a non-slice map whose tiles fall outside the slice tileset atlas can
  crash the rasterizer — expected, not a bug in the viewer.
- **Reads generated artifacts** under `output/uranium-build/` (`maps/`,
  `tilesets.json`). Re-run the graphics pipeline if those are stale; the viewer
  doesn't regenerate them.
- **Needs `.env-paths`.** All three entry points call `_load_dotenv()` for
  `RPG2GBA_*` paths; run from the repo root.
- **Zero external deps for the server** (stdlib `http.server`); the rendering core
  needs `numpy` + `Pillow` (already in the project `.venv`).
- Output (`output/map_viewer/`, `MapNNN_issues.json`) is gitignored generated art —
  don't commit it.
