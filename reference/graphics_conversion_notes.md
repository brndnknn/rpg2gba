# Graphics Conversion — Working Notes

**Status:** living design doc for the Uranium → GBA graphics pipeline. Started
2026-06-19. Findings + open questions we're talking through before building the
converter. Not authoritative spec yet — this is where we reason; decisions that
stick get promoted to `ROADMAP.md` / converter code.

---

## TL;DR

1. **Uranium art is a 2× nearest-neighbour upscale.** Downscaling ÷2 is lossless
   for every visible pixel. Native: RMXP 32×32 tiles → **16×16** (= one GBA
   metatile, exactly); 64×64 charset cells → **32×32** native.
2. After ÷2 the **only remaining lossy step is palette quantization** (truecolor →
   GBA 15-bit, ≤15 colours per tile).
3. Overworld NPC count is capped by the **engine (16 object events / 15 NPCs)**
   long before any GBA hardware limit. Uranium exceeds this on dense town/stadium
   maps — but the upper-bound counts overstate it; real simultaneous counts depend
   on event page conditions (deep dive in progress).

---

## 1. The 2× upscale discovery

- **Evidence — 2×2 block uniformity** (fraction of aligned 2×2 blocks that are one
  solid colour, best alignment phase): HERO sheet 99.89%, player frame 100%,
  tilesets 99.4–100%. Emerald native control: 46–56%. ⇒ Uranium = 2× nearest.
- **Lossless round-trip** (÷2 → ×2, diff vs original): PU-Veneza **0.000%**,
  HERO 0.032%, tilesets ~0.3%.
- **The HERO 0.032% is invisible:** all differing pixels have alpha=0
  (transparent-black `(0,0,0,0)` vs transparent-white `(255,255,255,0)` stored
  under transparent pixels). Visible-pixel diff = 0; premultiplied-RGBA diff = 0.
  ⇒ bit-exact for anything that renders.
- **Downscaler:** take 1 px per aligned 2×2 block (phase (0,0) on the full source).
  `scripts/downscale_compare.py::downscale_2x`. Verifier:
  `scripts/pixel_grid_analysis.py`.

**Converter actions:**
- ÷2 first, globally.
- **Normalize transparent-pixel RGB (or premultiply)** before downscaling so the
  transparent-colour inconsistency can't leak.
- **Flag opaque tiles where a 2×2 block isn't uniform** (the <0.35% on some
  tilesets) — those are the only places ÷2 isn't bit-exact; decide per-case
  (pick majority colour / keep at higher res / accept).

## 2. Tilesets → GBA

- RMXP **32×32 tile → 16×16 native = one GBA 16×16 metatile.** Clean 1:1, no
  resample. 256-wide RMXP atlas → 128-wide native = 4 tiles across.
- **Remaining hard step = palette quantization** per tile: GBA uses 16-colour
  sub-palettes (index 0 transparent → 15 usable), with the primary/secondary split
  (primary owns palette slots 0–5, secondary 6–12 in this engine).
- Not covered here yet: RMXP **autotiles** (ids 48–383) and **3 layers + priority**
  — that's layout/compositing, separate from pixel scale.

## 3. Sprites → GBA

- Native standing frames: hero **18×27**; HGSS NPC cast widths cluster 14–30,
  **median 17**, heights ≤32.
- GBA overworld object frame = **16×32** (engine also supports 8/16/32/64; **32×32
  "big object"** is used in vanilla for the bike/surf player — so it's first-class).
- **Fit into 16×32:** ~77% of the 254-sprite HGSS cast fit with a ≤3px width trim;
  **~23% are ≥20px wide** and want 32×32 (or a smarter body-centered crop). The
  naive center-crop clips one-sided props (e.g. Gillian, 25px).
- **32×32 downsides:** 2× OBJ VRAM/frame (512 vs 256 B), 2× per-scanline width,
  overhangs the tile L/R (clipping + z-order), field-effect (shadow/reflection/
  grass) alignment must be retuned, and all states must be authored at 32×32.

**Converter actions:**
- Default player + cast to **16×32** (trim / body-center crop); reserve **32×32**
  for genuinely wide sprites (threshold ~native width ≥ 20).
- Build a **body-centered crop** (ignore one-sided props) instead of naive center.

## 4. Overworld NPC limits (engine + hardware)

Verified in the fork / GBATEK. Smallest binds:

| Limit | Value | Note |
|---|---|---|
| **Object-event slots** | **16** (player+15) | `OBJECT_EVENTS_COUNT` — the wall |
| Templates / map | 64 | `OBJECT_EVENT_TEMPLATES_COUNT` |
| Spawn window | 19×16 tiles | `MAP_OFFSET=7`; `pos.x-2..+17, pos.y..+16` |
| pokeemerald sprites | 64 | `MAX_SPRITES` |
| Hardware OAM | 128 | |
| Per-scanline OBJ | 1210 px (954 if H-blank-free) | normal sprite = 1 cycle/px |
| OBJ VRAM | ~1024 tiles (32 KB) | |
| OBJ palettes | 16 (~5 overworld slots) | `PALSLOT_*` — variety squeeze |

At 15 NPCs the hardware is far from saturated (per-scanline ~256/1210; OAM ~30–40;
VRAM ~136 tiles). **Palette slots (~5) are the real secondary squeeze** — 15 NPCs
must share ~5 palettes.

**Levers:** crowd-bake static audiences into the tilemap (not object events); NPC
culling pass; or raise `OBJECT_EVENTS_COUNT` (a `#define`; changes fork baseline →
needs operator sign-off).

### Headroom to raise `OBJECT_EVENTS_COUNT` (measured from the built ELF)

The binding constraint is **not** work RAM — it's the **flash save block**.

- **EWRAM:** 256 KB total, ~227.7 KB used (`.ewram.sbss` = 0x37964), **~34 KB free**.
  Per extra slot ≈ **77 B** (`gObjectEvents` 36 + `SaveBlock1.objectEvents` 36 +
  `sMovementScripts` 4 + `localIds` 1). ⇒ EWRAM alone allows hundreds of slots.
- **`SaveBlock1` (flash):** capped at 4 sectors × `SECTOR_DATA_SIZE` 3968 =
  **15,872 B**; currently **15,696 B** ⇒ **176 B free**. `SaveBlock1` contains
  `objectEvents[OBJECT_EVENTS_COUNT]` at +36 B/slot ⇒ **only ~4 more slots** before
  the `SaveBlock1FreeSpace` STATIC_ASSERT fails the build.
- `struct ObjectEvent` = 36 B, `struct Sprite` = 68 B (`gSprites[MAX_SPRITES+1]` =
  4420 B). At ≤~20 object events, `MAX_SPRITES` (64) and OAM (128) are untouched.

**Verdict:** **16 → ~20 is nearly free** (fits the 176 B save headroom, trivial
EWRAM). Going to 32 needs ~400 B reclaimed from `SaveBlock1` (or a save-format
change) and probably a `MAX_SPRITES` bump if you actually draw 32+reflections. So
crowd-baking, not a big count bump, is the lever for the 28–102 cases.

## 5. Uranium density vs the cap (upper-bound scan)

`scripts/npc_density_scan.py`. Counts an event if ANY page has a sprite graphic
(UPPER BOUND).

- **16 / 199 maps** exceed 15-in-window; **5 maps** exceed 64 object-templates.
- Worst: Amatree Gym (102 / 144 events), Championship arenas (40/22/20 — audiences),
  **Bealbeach Resort (28 / 41)**, Nowtoch (22 / 110), Tsukinami (21 / 55), towns
  (17–19).
- **Caveat:** these are upper bounds in general. RMXP page conditions *can* swap
  NPCs in/out, so true simultaneous counts are often lower — **but not always.**

### Resort (Map052) — real simultaneous count (deep dive, `scripts/map052_npc_density.py`)

The upper bound held: **the Resort really does hit 28 NPCs in one 19×16 window.**
- 73 events: 31 never-sprite, **41 always-sprite, 0 conditional**, 1 tile-graphic.
- The only switch referenced (SW33) gates *which dialogue page* runs, not sprite
  visibility (both pages have a graphic). No variables gate visibility. ⇒ the NPC
  set is **constant at 41 regardless of game state** — page conditions give zero
  relief here.
- Densest window (camera ≈ (31,6), tiles x29–47/y6–21): **28 sprites = 12
  interactable + 16 cosmetic** (a stationary column of 16 at x=40). Budget 15 ⇒
  **+13 over.**
- Fix: **crowd-bake the x=40 column** (16 identical stationary figures) into the
  tilemap; that alone brings the peak to ~15. Culling can't hide behind story
  phases here because there are none.
- Lesson: dense Uranium maps split into (a) genuine constant crowds → crowd-bake,
  vs (b) story-gated swaps → page-condition analysis. The Resort is type (a).

## 6. Open questions / decisions

- [ ] **Tileset palette quantization** strategy: how to assign ≤N 16-colour
  sub-palettes per tileset; shared-vs-per-area; dithering or not. (Main lossy step
  — this is where the slice pipeline stops pending decisions; see §8.)
- [ ] **NPC palette clustering**: group Uranium's varied sprites onto ~5 shared
  overworld palette slots without ugly recolouring.
- [ ] **NPC budgeting policy** per map: cull vs crowd-bake vs raise the cap.
- [ ] **Player / wide-sprite frame**: 16×32 trim vs 32×32 — per-sprite by native
  width? what threshold?
- [ ] **Body-centered crop** vs naive center for >16px sprites.
- [ ] Handling the **<0.35% non-2×-conforming** opaque tile pixels. (ts22 measured
  ~1.3% of opaque 2×2 blocks non-uniform; top-left sampling accepts it for now.)
- [x] **Autotiles** — DONE (faithful variant assembly, §8). 3-layer/priority
  *visual* collapse is handled by `layout.collapse_column` (topmost non-empty);
  the new nuance to wire is that an autotile pointing at an **empty slot** is
  visually transparent (must fall through to the layer below — see §8).

## 7b. Decisions locked (2026-06-20)

- **Scope of the first graphics step = tilesets only.** Player stays vanilla
  Brendan/May, NPCs stay `NINJA_BOY` placeholders. Sprites are a separate pipeline.
- **Autotiles = faithful variant assembly** (not collapse-to-representative).
- New `gTileset_Uranium_*` tilesets (not overwriting vanilla); dedicated
  primary+secondary pair each (→ 1024 8×8 tiles / 1024 metatiles / 13 palettes,
  so even Moki Town's 364 metatiles fit comfortably); 8×8 dedup standard.
- Behaviours stay `MB_NORMAL` except the existing warp tiles (no `MB_TALL_GRASS`
  — encounters would be new functionality).
- `tileset_map.json`'s `tiles` table becomes a **generated** artifact (the image
  pipeline emits the `(tileset_id,tile_id)→metatile_id` map alongside the
  binaries, since they must agree). §4.3 source-of-truth shift, noted.

## 8. Implementation — image pipeline steps 1–3 (BUILT 2026-06-20)

Package: `src/rpg2gba/tileset_converter/graphics/`. Pure-PIL (no numpy yet);
produces 16×16 RGBA tiles. **Stops before quantization (step 4)** per the locked
plan — palette decisions pending.

- **Step 1 `sources.py`** — `load_tileset_sources(tileset_id)` → `TilesetSources`
  (tileset PNG + 7 autotile-slot PNG paths, `None` = empty slot). Fail-loud on a
  named-but-missing asset. Needed a `deserialize.rb` change: `shape_tileset` now
  emits `autotile_names` (the stub already declared it; only the dump dropped it).
  Re-dumped `tilesets.json` (60 tilesets).
- **Step 2 `autotile.py`** — `flatten_autotile(template, variant)` → 32×32.
  `AUTOTILE_TABLE` transcribed **verbatim** from Uranium's own renderer
  (`scripts_dump/039_TileDrawingHelper_v17.rb` `bltSmallAutotile`): variant =
  `tile_id % 48` (Uranium **bakes** the resolved variant into map data — confirmed
  by the 52-distinct-ids-across-4-bases census, so no neighbour recompute);
  height-32 templates are animation strips (variant ignored, take frame-0 32×32);
  else assemble 4 16×16 quadrants via `AUTOTILE_TABLE[v>>3][v&7]` (1-based piece
  ids into a 6-col grid).
- **Step 3 `raster.py`** — `TileRasterizer(sources).render(tile_id)` → 16×16 RGBA,
  cached/idempotent. static (≥384) = crop atlas cell `((id-384)%8,(id-384)//8)`;
  autotile (48–383) = flatten then ÷2; empty-slot autotile / id 0 = transparent.
  `downscale_2x` = top-left of each 2×2 block (matches the validated
  `downscale_compare.py::downscale_2x`).

**Findings while building:**
- **Both slice tilesets are clean 2× upscales** (exact pairwise 2×2-uniformity:
  `Indoor(1)` 100%, `PU-Route01-02-Moki-Kevlar` 98.67% opaque). NB: a box-vs-nearest
  *proxy* gave a misleading 62% for ts22 (averaging rounds ±1) — use exact
  pairwise equality to judge 2×-ness, not `reduce(2)` vs `resize(NEAREST)`.
- **ts19 slot 6 (base 336) is an empty autotile**, but Map048 has 4 top-layer
  cells (ids 370/372/374/376) referencing it over real floor → they render
  transparent. The wire step's visual collapse must let them fall through.

**Validation (look at the booted-equivalent art):** `scripts/render_slice_tiles.py`
reconstructs each map by rendering every cell and alpha-compositing the 3 RMXP
layers → `output/slice_map0{49,48,32}_reconstruct.png`. Map049 (interior) and
Map032 (Moki Town, the autotile + budget stress case) both render as crisp,
recognizable Uranium art (grass/water/path autotile edges all correct). True
colour — quantization is the next step.

**Tests:** `tests/test_graphics_{sources,autotile,raster}.py` (19, all pass).

## 9. Step-4 (quantization) decisions — visual analysis (2026-06-20)

Prototyped the options as labelled visuals (`scripts/step4_visual_explainer.py`,
`scripts/hero_room_palette.py`, `scripts/alpha_rule_explainer.py`) for the user to
decide by eye. Findings:

- **Palette demand is fine at the real GBA budget.** Hero's room (Map048): 178
  colours, *under* the 195-slot ceiling → near-free. Moki Town (Map032): 459→333
  colours (15-bit alone merges 126), *over* the ceiling → needs real reduction to
  ~160–195 colours (mean shift ~1.1–1.4 on a 0–31 scale ≈ mostly invisible). A
  rough **joint per-8×8 quantizer at 13 palettes ×16 makes Moki Town ≈ raw** — the
  naive median-cut-then-pack's scary counts (20–64 palettes) were a packing
  artifact, not a real ceiling.
- **Step-4 design calls (recommended):** joint per-8×8 quantizer (NOT two-stage
  median-cut), 15-bit colour, **no dithering** (shimmers when scrolling; not needed
  at full budget), allocate ~13 palettes to outdoor tilesets / fewer to interiors.
- **Binary-alpha rule = TWO sub-decisions.** GBA 4bpp has no partial alpha.
  Uranium partial-alpha px split into (a) thin AA object **edges** (Moki Town: 37
  tiles, low stakes → 50% threshold) and (b) semi-transparent **shadows** — soft
  object-base shadows + 3 *uniformly* semi-transparent black tiles. For shadows:
  **keep-opaque → ugly black blobs (rejected)**; 50%/drop → shadows vanish (clean,
  flatter); **stipple (50% checker of the translucent px) → reads as translucent,
  GBA-authentic**. Recommendation: per-tile classify — sparse-AA → 50% threshold,
  shadow-dominated → stipple. ~40 tiles total in Moki Town.
- **Still open / pending user pick:** stipple-vs-threshold for shadows; final
  palette-budget split interior vs outdoor; whether to run the joint quantizer over
  the FULL 72×64 town (one fixed 13-palette set) to confirm the whole-map look
  (crops build per-crop palettes, so true demand is slightly tighter).
  **→ Resolved 2026-06-20 (see §10):** user picked **numpy**, **per-tile classify**,
  **full-town confirm first**; the full-town run passed. **Shadows: stipple REJECTED,
  user chose DROP** (see §10) — so the shadow sub-decision above lands on "shadows
  vanish (clean, flatter)", not stipple.

## 10. Step-4 (quantization) — BUILT + validated (2026-06-20)

Package: `src/rpg2gba/tileset_converter/graphics/quantize.py` (numpy — new dep,
user-approved; pinned `numpy>=1.26` in `pyproject.toml`). User decisions taken this
session: **add numpy**, **per-tile alpha classify**, **confirm full-town first**.

- **Binary alpha (`classify_tile`/`resolve_alpha`):** per-tile, keyed on the
  **solid-opaque-body fraction** (`SOLID_BODY_FRAC = 0.02`). A tile with a real
  opaque body (fully-opaque fraction ≥ 0.02 — tree canopy, fence) ⇒ **threshold**
  (opaque where alpha≥128, drops the low-alpha fringe); a bodyless semi-transparent
  wash (< 0.02 opaque — shadows) ⇒ **drop** (every partial pixel → transparent, so the
  shadow falls away and the ground tile below shows through); no partial alpha ⇒ binary
  passthrough. **NB two corrections:** (1) the body test was first a partial-alpha-
  FRACTION test (`SHADOW_PARTIAL_FRAC`) — WRONG, see the black-tree-tops bug below;
  (2) shadows were first **stippled** (50% `(col+row)%2==0` checker, "GBA-authentic
  translucent") — **user rejected the stipple (shimmers when scrolling) 2026-06-20 and
  chose DROP** ("handle house/object shadows the way we did the area under the trees").
  Confirmed on Moki Town: the 10 shadow tiles (576/577/1017-1019/1025/1026/1028 +
  the tree-base quadrants of 475/483) are a uniform ~33% alpha (77–89) across 198
  cells; dropping them shows clean ground (they sit over grass — no holes), no black
  blobs, no stipple. This **supersedes** the earlier AskUserQuestion "per-tile
  classify → stipple shadows" pick. (`scripts/shadow_locate.py` finds + profiles them;
  `_house_shadow.png` is the before/after.)
- **Colour reduction (`build_quantized_tileset`) — TWO-PHASE PALETTE PACKER:** this is
  a **15-colour bin-packing / palette-MERGING problem, not k-means colour clustering**
  (the key realisation — see the orange-tree bug below). A census
  (`scripts/tile_color_census.py`) found **99.1% of Moki Town's 8×8 tiles already have
  ≤15 distinct colours (median 5)**, so each tile is losslessly representable by one
  palette; loss comes ONLY from forcing tiles to SHARE a palette whose combined set
  exceeds 15. Algorithm: **(1) global vocabulary** — median-cut the tileset's distinct
  colours down to `global_colors` (default `max_palettes*colors_per_palette` = 195),
  shedding the excess by merging *similar* colours only (dark green→near dark green,
  invisible; never cross-family); remap every tile's colours to this shared vocab.
  **(2) agglomerative tile packing** — represent each tile's colour set as a **bitmask
  over the vocab** and greedily merge the two palettes with the smallest colour UNION
  (`(a|b).bit_count()`) until ≤`max_palettes` remain (tiles sharing colours cluster →
  coherent palettes); only a palette still over 15 is **locally** reduced (median-cut
  its own colours), so residual loss is always a within-palette near-merge, never a
  cross-family snap. 15-bit (`to_5bit`), **no dithering**. `weights`/`iterations` are
  accepted but unused.
- **THREE bugs found + fixed 2026-06-20, all by the USER LOOKING at the render
  (numbers hid every one):**
  1. **Paths-turned-green.** Lloyd seeded from *area-weighted* pixels; the small-area
     path tan `(231,219,162)` had no palette → whole path network went green. Metric
     (2.64/31) hid it (grass ≫ path). First fix = distinct-colour seeding.
  2. **Black tree-tops.** `classify_tile` sent tree-canopy edge tiles to **stipple**
     (they had lots of partial alpha), dithering the soft edge into a black-and-
     transparent checker; Uranium stores ~black RGB under transparent pixels, so the
     kept stipple pixels were black. Fix = classify on **solid-body fraction** not
     partial-alpha fraction (tree = body+fringe → threshold, which keeps the true-green
     high-alpha edge and drops the contaminated low-alpha pixels). Measured cleanly:
     shadows are 0.0% opaque, every foliage tile ≥9% → `SOLID_BODY_FRAC = 0.02`.
  3. **Orange/white tree-shading.** Even with distinct seeding, Lloyd's median-cut
     *refit* dropped minority colours from incoherent palettes, so dark tree-shadow
     green `(16,142,66)` snapped to orange/white. **This is what exposed Lloyd as the
     wrong algorithm** — the census showed tiles don't NEED colour reduction, only
     palette sharing. Replaced the whole quantizer with the two-phase packer above.
  Diagnostics built: `scripts/quantize_diag.py` (rank tiles by weight×shift, true→
  mapped colour + palette mean), `scripts/tree_alpha_diag.py` (black-fringe signature
  + magenta-backed before/after strips), `scripts/tile_color_census.py` (per-tile
  distinct-colour distribution → "it's bin-packing").
- **Validation (`scripts/quantize_moki_preview.py`) — AFTER all three fixes:** full
  Moki Town (Map032, ts22), one fixed ≤13-palette set → 364 tile_ids / 923 unique 8×8
  → **on-screen mean shift 0.95/31; by eye the GBA-4bpp render matches the true-colour
  source** — path tan, water blue, roofs red, trees solid green (no black tops, no
  orange/white blotches), flowers pink. Outputs `output/quantize_moki_{compare,
  quantized,palettes}.png`.
- **Tests:** `tests/test_graphics_quantize.py` (30, all pass; `to_5bit`, the
  solid-body alpha classify/resolve rules, the ≤max-palettes / ≤15-colours / every-
  tile-representable invariants, lossless-fit, determinism). Full graphics suite 49.
- **DURABLE LESSONS:** (1) **validate graphics by EYE, never a pixel-averaged metric**
  — all three bugs were invisible to mean-shift (area-blind to small/important regions)
  and obvious in the render; (2) **diagnose by ranking the worst offenders and reading
  true→mapped colours**, don't summarise to a mean; (3) **measure the problem's
  structure before picking an algorithm** — the per-tile colour census reframed this
  from k-means to bin-packing and only then did it come right.
- **NEXT (pending user sign-off):** wire the GBA 4bpp **binary emitter** —
  `gTileset_Uranium_*` 8×8 dedup → indexed `.bin` + `.pal`, metatile attributes
  carry the per-8×8 palette numbers; `tileset_map.json` `tiles` table becomes a
  generated artifact (§7b). **Stipple/shadow path still under-exercised** (Moki Town
  shadows are few — stress a shadow-heavy map before declaring step 4 done).

## 11. GBA BG-palette budget — why the cap is 13 (verified vs `engine/`, 2026-06-22)

The quantizer's `max_palettes=13` (`emit.NUM_PALS_TOTAL`) is **not tunable headroom — it is a
hard engine boundary.** A field map has 16 BG palettes; the overworld system claims them:

| slot | content | tileset-usable? |
|---|---|---|
| 0–5 | primary tileset (`LoadPrimaryTilesetPalette`, `fieldmap.c:1057`) | in use |
| 6–12 | secondary tileset (`LoadSecondaryTilesetPalette`, `fieldmap.c:1062`) | in use |
| 13 | unassigned, but **excluded from weather/time blending** (`PALETTES_MAP = 0x1FFF`, `palette.h:18`; enforced `field_weather.c:672`, `overworld.c:1746/1777`) | only with a C change |
| 14 | `STD_WINDOW_PALETTE_NUM` (text-box border) — rewritten on **every** dialogue (`menu.h:10`, `menu.c:208`) | hard conflict |
| 15 | `DLG_WINDOW_PALETTE_NUM` (dialogue text) — rewritten on **every** dialogue (`menu.h:8`, `menu.c:207`) | hard conflict |

`emit.py`'s `6` / `13` match the headers exactly. **14/15 are off-limits** (any tile using them
flashes to window colours during NPC interactions). **13 is the only expansion candidate**, and
only if you also widen `PALETTES_MAP` to `0x3FFF` and update the three blend sites — otherwise
slot-13 tiles never receive weather/day-night tinting and look wrong outdoors.

**Implication for dense tilesets (e.g. Moki / tileset 22):** measured 381 distinct 5-bit colours
vs the 13×15 = **195** hardware ceiling (all 13 palettes full; mean snap 1.3/31, max 4). Even
claiming slot 13 only lifts the ceiling to 210 — still ~half of 381 — so palette merging on dense
outdoor tilesets is a genuine **colour-budget** constraint, not a packer inefficiency. The lever is
the source art (fewer near-duplicate colours), not the palette count. Inspect per-tile merge loss
with the map viewer's **Merge** overlay / **Worst palette merges** panel (`scripts/map_viewer_*`).

## 7. Throwaway analysis scripts (in `scripts/`, write to gitignored `output/`)

- `downscale_compare.py` — ÷2 downscaler + original-vs-output compare.
- `pixel_grid_analysis.py` — 2×2 uniformity + lossless round-trip + pixel-grid render.
- `fit_npc_frames.py` — fit sprites into the 16×32 frame + overflow stats.
- `hgss_contact_sheet.py` — full HGSS cast at GBA scale + fit tiers.
- `npc_density_scan.py` — per-map NPC density vs the 16/64 caps + spawn-window math.
- `render_pc_exterior_compare.py`, `render_player_compare.py` — earlier side-by-sides.
