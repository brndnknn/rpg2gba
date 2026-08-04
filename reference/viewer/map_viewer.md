# Map Viewer — Uranium tile-feedback tool

A browser-based tool for flagging specific tiles and tile-groups on a Uranium map
so the build agent can fix them — a per-map punch list you build by tapping cells,
grouping them, and writing a note. Quantization/graphics-debugging (palette knobs,
layer isolation, diff/merge overlays, the palette inspector) is still here, but
demoted behind an **Advanced** toggle. Tile feedback is the primary job now; the
quant machinery is secondary.

**It is one tool, not two.** There are two *views* (map grid + palette inspector)
and two *delivery modes* (live server + self-contained file), all behind one shared
core. Don't go looking for a second viewer.

---

## TL;DR — flag a tile

```bash
python scripts/map_viewer_server.py --port 8765
```

Open `http://localhost:8765/` (or `http://<hostname>:8765/` over Tailscale/LAN —
it binds `0.0.0.0`, so your phone works too). The **landing page** is a searchable,
location-grouped index: every map by **id + descriptive name**, type-to-filter,
nested by RMXP parent so a town's interiors sit under it. Each row links to both
views.

Open a map, **tap a tile** (tap more to add to the selection, tap again to remove),
optionally hit **Expand similar** to grab every matching tile on the map, type a
note, and click **Save flag**. That's the whole workflow — see "The feedback
workflow" below for the full model.

The map grid defaults to the **Quantized (family)** view — the GBA render, i.e.
what the ROM will actually show. RPG Maker is the reference view now, one radio
click (or the `q` hotkey) away.

Each map is quantized from **its own tiles alone** (the render pool is just the map
you open), matching the ROM's per-map tileset packing — so the grid is a faithful
preview of the quantized ROM art. Any map with generated output under
`output/uranium-build/maps/` will render.

---

## The feedback workflow (core)

This is what the tool is for now: building a per-map list of `{cells, note}` flags
that the build agent reads and fixes.

**Selection model:**

- **Tap a cell** to toggle it into a persistent selection set — tap again to
  remove it. Selection accumulates across taps. There is **no drag-paint and no
  marquee** — drag still pans the canvas, two-finger still pinch-zooms, same as
  always.
- The **last-tapped cell** is the "focus" cell — it drives the sidebar's detail
  readout (RMXP layers, GBA metatile, collision, events), independent of whether
  that particular tap added or removed the cell from the selection.
- **Expand similar** (sidebar button, disabled until there's a focus cell with a
  real, non-void metatile) adds every cell on *this map* sharing the focused
  cell's metatile identity (`colkey_idx`). It's additive and multi-identity — tap
  a flower tile + Expand, tap a water tile + Expand, and both whole groups land in
  one selection.
- **Clear** empties the selection (disabled when already empty).

**Saving a flag:**

- Type a note in the textarea (placeholder: "Describe what's wrong with these
  tiles…") and click **Save flag** (disabled until something is selected). One
  flag covers the *whole* current selection. Schema:
  ```json
  {"cells": [[x, y], ...], "note": "..."}
  ```
  Bare prose — no category/severity field.
- The **flag list** below shows each saved flag as `<N cells>` + its note. Click a
  row to re-select its cells and load its note back into the textarea for editing
  — **Save flag** then replaces it in place instead of adding a duplicate. The
  **✕** on a row deletes it immediately.
- Flagged cells get an orange **⚑** marker on the canvas (drawn unconditionally,
  not gated behind Advanced), so you can see punch-list coverage while panning.
- **Export JSON** writes `MapNNN_feedback.json` — the current flag list as-is. In
  **server mode** it POSTs to `/api/feedback/export` and the *server* writes the file
  to `output/map_feedback/` on the machine running it (not a browser download — the
  viewer is usually driven from a phone, and the file is only useful next to the rest
  of the pipeline output); the written path is echoed under the button. In **static
  mode** there's no server to write to, so it falls back to a browser download — the
  only way to get flags out of static mode.

**Storage:** flags persist to git-tracked `reference/map_feedback/MapNNN.json` — a
JSON list of `{cells, note}` objects. This is deliberate: flags are hand-authored
review data, not regenerable output, so they must survive `rm -rf output/` /
`pipeline --clean`. Server mode writes the whole file on every Save/delete via
`POST /api/feedback` (body `{map_id, flags}`) and loads it via
`GET /api/feedback/<id>` on page load. The **old** location — gitignored
`output/uranium-build/map_viewer_issues/` (one note per cell, keyed `"x,y"`, no
grouping) — is **retired**; old files are **not** migrated, so re-flag anything you
want kept under the new model. Static/phone mode has no server to write to, so
flags live in memory only for the session — Export JSON before you close the tab.

---

## Architecture (why it's split across files)

```
map_viewer_common.py        ← shared CORE (data + rendering + map-grid template)
├─ build_map_data(map_id)       extract cells / metatiles / palette usage  →  dict
├─ render_tile_png()            one RMXP 16×16 tile  →  PNG
├─ render_metatile_png()        one metatile layer (bottom/top/post_*)  →  PNG
├─ load_feedback() / save_feedback()   per-map flag list  ↔  reference/map_feedback/MapNNN.json
└─ MAP_VIEWER_HTML              the map-grid VIEW + feedback UI (template)

build_map_viewer.py         ← STATIC mode  (self-contained .html, base64-inlined)
└─ build_config(map_id)         map data + every tile/metatile as base64 PNG

palette_page.py             ← second VIEW: the palette inspector (Advanced-tier)
└─ PALETTE_VIEWER_HTML          palette swatches + suspect-tile grid + colour-change popup

map_graph.py                ← map RELATIONSHIPS (no rendering, pure metadata)
├─ build_index()                landing-page data: flat name list + parent_id forest
└─ map_relationships(id)        per-map nav: name, parent, children, warp targets

map_viewer_server.py        ← SERVER mode  (live HTTP, lazy /api/* PNG rendering,
                               /api/feedback persistence)
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
| `GET /palettes/<id>` | palette inspector (lazy images, Advanced-tier) |
| `GET /api/map/<id>` | `build_map_data` JSON |
| `GET /api/tile/<mapid>/<tid>.png` | one RMXP tile PNG |
| `GET /api/metatile/<mapid>/<idx>.png?layer=bottom\|top\|post_bottom\|post_top` | one metatile-layer PNG |
| `GET /api/feedback/<id>` | this map's saved flags (JSON list) |
| `POST /api/feedback` | replace a map's whole flag list (body: `{map_id, flags}`) |
| `POST /api/quantize` | apply live family-packer knobs (Advanced only) |

Images render lazily on request and are cached (both in the browser via
`immutable` cache headers and in a module-level cache server-side), so the first
view of a map is a little slow, then snappy. Cross-links between the two views
(`Palettes →` and `← Map` buttons) **only exist in server mode**, and flag saves
only persist to disk in server mode.

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

Static files are larger (all images inlined) and have **no cross-view nav buttons,
no cross-map nav strip, and no flag persistence** (those need live routes/server) —
build flags in the session and **Export JSON** before closing the tab.

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

**View toggle (always visible, core):**

| Option | Shows |
|---|---|
| **RPG Maker** | the 3 RMXP source layers composited (what RPG Maker draws) — reference view |
| **Quantized (family)** | the post-quantization art from the family packer — what the ROM actually shows. **Default.** |

Flip with the radio, or the `q` hotkey (ignored while a text field has focus, so
typing a note doesn't trigger it). The original 8-way layer radio
(RMXP/L0/L1/L2/GBA/GBA↓/GBA↑/Post-Q) still exists in the page but is
unconditionally hidden (`#layer-debug`, inline `display:none` — a separate
mechanism from the Advanced toggle below); unhide it by hand to restore the full
layer inspector.

**Overlays — core (always visible):** Collision (ours vs Uranium's passability),
Events (on by default), Warps (on by default).

**Overlays — Advanced only:** Diff (render mismatch), Priority (RMXP draw-above-
player priority), Merge (palette-merge-loss heat-map) — see "Advanced" below.

**Zoom:** `−` / `+` / `Fit` buttons, mouse wheel, or two-finger pinch; current
factor shown (default 2×).

**Sidebar (right):** the **Feedback** panel (see "The feedback workflow" above)
plus a trimmed cell inspector. Tap a cell to see its RMXP layers (tile id, passage,
priority, terrain), GBA metatile thumbnails (raw pre-quant + shipped post-quant),
collision (ours vs Uranium's, with mismatch flagged), and any events on that cell.
Palette detail and per-quadrant fit only appear when Advanced is on.

### Advanced (collapsed by default)

Click **Advanced** in the toolbar (title: "Show quantization / graphics-debug
controls"; adds `body.adv`) to reveal the whole quantization/graphics-debug layer:

- **The knob bar** — live `FamilyParams` tuning: `green cuts` (interior hue° in
  (70,170) that split the green band into sub-families), `dark<` / `neutral sat<`
  (value/saturation cutoffs for the dark/neutral families), `pal floor` (min
  sub-palettes per family), `overflow` (colors vs coverage allocation), `max pals`
  (≤13). **Apply & re-render** POSTs `/api/quantize` → the server re-quantizes
  eagerly (so a bad knob value surfaces as an HTTP 400 and rolls back instead of
  breaking the reload) → the page reloads, re-rendering the map **and** both
  palette views under the new params. A monotonic `generation` token is appended
  to post-quant image URLs (`&g=`) to defeat the browser's `immutable` cache.
  Server mode only — it hides itself in static exports even with Advanced on.
- **Diff** / **Priority** / **Merge** overlay checkboxes.
- The **Palettes →** link to this map's palette inspector.
- The **Worst palette merges** sidebar panel — a collapsible list of the metatiles
  that lost the most colour to quantization; click one to jump to a cell using it.
- The per-cell **Palettes** section (RMXP source colours, GBA sub-palettes, colour
  changes) and the per-8×8-quadrant palette-fit breakdown, appended to the cell
  inspector.

Turning Advanced back off clears the Diff/Priority/Merge overlay checkboxes, so the
canvas returns to a clean feedback view rather than leaving a stale debug overlay on.
It does NOT reset the knobs themselves — if they're non-default, the always-visible
"⚠ non-stock quantize" toolbar badge (see "Scope & caveats" below) stays lit even
with Advanced collapsed, so you don't forget a render is tuned away from stock.

---

## View 2: the palette inspector (`/palettes/<id>`)

Advanced-tier: reached only via the (Advanced-only) **Palettes →** link. The page
itself has no Advanced toggle of its own — the whole thing is quant-debug content,
so its knob bar is always visible there.

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
RPG Maker/Quantized toggle isn't fine-grained enough.

---

## Scope & caveats

- **Data pool matches the shipped ROM's grouping.** The boot-gate ROM is built by
  `scripts/assemble_pathfinder.py` (`run_graphics_pass`), which calls
  `build_slice_tilesets(maps, ...)` with no `source_tileset_of` over `SLICE_MAP_IDS`
  (`rpg2gba.tileset_converter.map_set`). Inside, maps are grouped by their REAL
  `map_json["tileset_id"]` — Map048 and Map049 (Player's House 1F/2F) both carry
  tileset 19 and are quantized together into ONE shared 13-palette budget; Map032
  (Moki Town, tileset 22) is alone. `_ensure_tileset_analysis` replicates this
  exactly: for a slice map, the pool is every `SLICE_MAP_IDS` member sharing the
  opened map's real `tileset_id`, so the "Quantized (family)" view matches the ROM
  byte-for-byte given the same inputs. (The Map Walker's phase5 build instead feeds
  a unique synthetic tileset id per map — a different, per-map pool that is NOT what
  the §9 boot-gate ROM compares against.) Non-slice maps have no shipped ROM truth
  to match and self-pool (`pool_map_ids = [map_id]`) as a preview-only best effort.
- **Reads generated artifacts** under `output/uranium-build/` (`maps/`,
  `tilesets.json`). The server re-checks a stat-only fingerprint (mtime+size) of
  these files on every request; if a rebuild changed them since a map was last
  loaded, it auto-reloads that map's state (and, for slice maps, invalidates its
  pool siblings too via a bumped generation token) instead of serving stale bytes.
  It still doesn't trigger the pipeline itself — you still have to re-run it.
- **Non-stock quantization is flagged.** The knob bar (Advanced-only) can leave
  `_family_params`/`_max_palettes` non-default for the life of the server. A small
  "⚠ non-stock quantize" badge in the toolbar — always visible, not gated behind
  Advanced — appears whenever the live knobs differ from stock, so a viewer can't
  silently mistake a tuned render for the shipped ROM's.
- **Needs `.env-paths`.** All three entry points call `_load_dotenv()` for
  `RPG2GBA_*` paths; run from the repo root.
- **Zero external deps for the server** (stdlib `http.server`); the rendering core
  needs `numpy` + `Pillow` (already in the project `.venv`).
- **Feedback flags are committed, generated output is not.** Flags live in
  git-tracked `reference/map_feedback/MapNNN.json` — hand-authored review data,
  commit it like any other reference doc. `output/map_viewer/` (static-mode HTML)
  is still gitignored generated art — don't commit that.
