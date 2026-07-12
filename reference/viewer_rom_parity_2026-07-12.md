# Map viewer ↔ ROM tileset parity — findings + fix design (2026-07-12)

**Status: RESOLVED same day — fix landed + parity PROVEN.** Both fixes landed
(viewer pool/staleness/badge in `scripts/map_viewer_common.py` + oracle
`scripts/verify_viewer_rom_match.py`), and the oracle passed both ways against the
2026-07-12 15:02 build artifacts in `engine/`:

- **Mode A** (pipeline simulation vs decoded ROM bytes): ts19 134/134 metatiles,
  0/68,608 px differ; ts22 842/842, 0/431,104 px differ. Reconstructed column-key→index
  order agrees with `reference/tileset_map.gen.json` exactly.
- **Mode B** (viewer render path vs decoded ROM bytes): ts19 all 129 columns covered via
  BOTH Map049+Map048, ts22 all 839 via Map032 — **0 differing pixels anywhere**.

The viewer's quantized view is now byte-identical to the ROM's tile data. §6 checklist
is retained for provenance; only its step 6 (eye-check with Brandon) remains. Everything
below documents what was found and why the fix is shaped this way. NOTE: a running
viewer server must be restarted ONCE to pick up the fixed code; after that, pipeline
rebuilds are picked up automatically (the staleness fix).

**Symptom (Brandon, 2026-07-12):** the map viewer's Quantized (family) view does not
match the tiles the built ROM shows in mGBA, even after a full from-scratch rebuild
(transpile → stage → assemble → make). So it is a real processing difference, not
staleness alone.

---

## 1. What is already correct — the shared code path

The viewer's quantized mode does NOT re-implement quantization. It calls the real
pipeline code:

- `scripts/map_viewer_common.py:287-289` → `emit.analyze_tileset_palettes(pool_metatiles,
  max_palettes=13, quantizer=partial(build_quantized_tileset_family, params=FamilyParams()))`
- `analyze_tileset_palettes` (`src/rpg2gba/tileset_converter/graphics/emit.py:200-242`)
  internally uses the same `_canonicalize_and_quantize` (`emit.py:132-168`) as
  `emit_tileset`: flip-aware 8×8 canonicalization (`_flip_canonical`, `emit.py:115-129`),
  same family packer, same `to_5bit` truncate-then-bit-replicate math
  (`quantize.py:49-55`), same alpha classification (`quantize.py:61-96`), and reassembles
  preview pixels via the shared `_reassemble_quantized` (`emit.py:182-197`).

**Therefore: given the same input pool and stock knobs, viewer pixels are byte-identical
to ROM pixels by construction.** The divergence must come from the *inputs*, and it does.

Ruled OUT as causes (verified in trace):

- emit's Step-2.5 post-quantization merge (`emit.py:271-297`) — storage dedup only,
  changes no pixel color.
- The viewer omitting the void metatile + warp-door copies from its pool — documented
  harmless at `emit.py:213-217` (void has no opaque pixels; door copies duplicate
  already-present columns) and verified.
- 8→5-bit rounding differences — same `to_5bit` code both sides.
- Run-to-run nondeterminism for the *same* pool in the *same* order — `column_keys_for_maps`
  returns `sorted()` keys (`build_slice_tilesets.py:188-204`), so a fixed caller is
  reproducible. (Ties in the packer's greedy merge and in `_allocate_by_overflow`
  ARE order-sensitive — `quantize.py:242-256`, `:428-462` — but that only bites when two
  callers present different pools/orders, which is exactly the root cause below.)

## 2. ROOT CAUSE — pool scope

**The viewer quantizes each map's tiles alone; the ROM quantizes per real RMXP tileset
across all slice maps sharing it.**

- Viewer: `_ensure_tileset_analysis()` at `scripts/map_viewer_common.py:223-293` sets
  `pool_map_ids = [map_id]` (line ~238). Its docstring (~230-236) justifies this by
  the **phase5 walker** build (`phase5.py:61-63` — synthetic tileset id `1000 + map_id`,
  one pool per map). That justification is TRUE for walker ROMs but FALSE for the
  boot-gate ROM.
- The boot-gate ROM: `scripts/assemble_pathfinder.py::run_graphics_pass` (~:137-174)
  calls `build_slice_tilesets(maps, ...)` with NO `source_tileset_of`, over
  `SLICE_MAP_IDS = [49, 48, 32]` (`src/rpg2gba/tileset_converter/map_set.py:28`).
  `build_slice_tilesets` groups by the maps' REAL `tileset_id`
  (`build_slice_tilesets.py:249-251`):
  - tileset **19** → Map049 + Map048 **pooled together**, one shared 13-palette budget,
    one `emit_tileset` call;
  - tileset **22** → Map032 alone (singleton by coincidence).

Different pool → different hue-family color census → different `_allocate_by_overflow`
budget split (`quantize.py:428-462`) → different agglomerative merges → **different final
palettes and snapped colors** for Maps 48/49 in the viewer vs the ROM. This is the
structural "at least one difference in how they are processed".

### Build-flavor caveat (important)

Which pooling is "correct" depends on which ROM you compare against:

| ROM flavor | Built by | Pooling truth |
|---|---|---|
| Slice boot-gate ROM (current, walker OFF) | `scripts/assemble_pathfinder.py` | per REAL tileset_id over SLICE_MAP_IDS (49+48 together) |
| Map-walker ROM (199 maps) | `pipeline phase5` | per map (synthetic id 1000+map_id) |

The fix targets the **slice** ROM — that's the §9 gate artifact Brandon walks. If a
walker ROM comparison is ever needed again, the viewer pool would need a mode switch.

## 3. Secondary causes — why even Map032 can look stale/wrong

These don't change the pipeline output but can make a *running viewer* show non-ROM
pixels:

1. **Server never re-reads disk.** `_ensure_loaded` (`map_viewer_common.py:326-332`)
   returns the cached `_MapState` if present — no mtime check, ever. After a rebuild
   regenerates `Map*.json` / `tilesets.json` / `tileset_map.gen.json`, a long-running
   server keeps serving pre-rebuild renders until restarted. (Note the viewer never
   reads `tileset_map.gen.json` at all — it re-derives its own column-key set.)
2. **Quantize knobs are silent global state.** `set_quantize_params`
   (`map_viewer_common.py:187-204`, via `POST /api/quantize`,
   `map_viewer_server.py:209-228`) permanently overwrites `_family_params`/`_max_palettes`
   for the whole server process. The 2026-07-11 refocus hid the knob bar behind the
   Advanced toggle, so non-stock knobs are now invisible. One Apply with tweaked knobs
   → every map quantizes non-stock until restart, with no indication.
3. **Browser immutable caching.** Tile/metatile PNGs are served with
   `Cache-Control: … immutable` (`map_viewer_server.py:65,278-282`); the `&g=` cache-bust
   token (`_quant_generation`) bumps only on knob Apply, not on data changes — so even a
   server restart + browser reload can show cached stale PNGs for URLs without a fresh
   token.
4. **(Display-only, not data)** mGBA color-correction shades RGB555 differently than the
   viewer's `(q<<3)|(q>>2)` 8-bit expansion. The palette *data* is identical; ignore
   small uniform brightness differences when eyeballing.

## 4. The fix (designed this session; sub-agents were building it)

### 4a. Viewer pool fix — `scripts/map_viewer_common.py`
In `_ensure_tileset_analysis`:
- opened map ∈ `SLICE_MAP_IDS` (import from `rpg2gba.tileset_converter.map_set`) →
  `pool_map_ids = [m for m in SLICE_MAP_IDS if tileset_id(m) == tileset_id(opened)]`
  (read each slice map's JSON `tileset_id`; this reproduces `build_slice_tilesets`'
  `by_ts` grouping exactly: [49,48] for either house map, [32] for Moki Town);
- non-slice map → keep `[map_id]` self-pool (no shipped truth to match);
- rewrite the misleading phase5 docstring (~:230-236) per §2's build-flavor table.
The `_tileset_analysis_cache` key `frozenset(pool_map_ids)` stays valid. Check the
atlas-bound filtering (~:258-274) still resolves the opened map's keys against a
union-of-two-maps analysis.

### 4b. Staleness fix — same files
- Fingerprint (mtime+size) the map's `Map{NNN}.json` + `tilesets.json` in `_MapState`;
  `_ensure_loaded` rebuilds on change. Include pooled maps' fingerprints in/alongside
  the analysis cache key. Clear the PNG caches on reload.
- Bump `_quant_generation` on any stale reload, and append the `&g=` token to ALL
  tile/metatile image URLs (today only post-quant carries it — see `getMetatileURL`,
  `map_viewer_common.py:~934`).

### 4c. Non-stock knob badge — same files
Always-visible toolbar badge (outside the Advanced-gated area) when
`_family_params != FamilyParams()` or `_max_palettes != 13`.

### 4d. Independent oracle — NEW `scripts/verify_viewer_rom_match.py`
Stop asserting parity; prove it against the actual emitted bytes.

- **Mode A (`--mode pipeline`)**: for each slice tileset (19→[49,48], 22→[32]),
  reconstruct the metatile list exactly as `build_slice_tilesets` does (sorted column
  keys via `column_keys_for_maps` + `_render_column`, then void metatile, then door
  copies in `sorted(door_keys)` order, then transparent door fallback —
  `build_slice_tilesets.py:334-370`; metatile index = list position). Run the same
  simulation (`analyze_tileset_palettes`, family packer, defaults). Decode the emitted
  artifacts and byte-compare per metatile. Cross-check the reconstructed
  column-key→index order against `reference/tileset_map.gen.json` before comparing.
- **Mode B (`--mode viewer`)**: same decode side, but expected images come from
  `map_viewer_common`'s render path — this is the end-to-end claim ("the viewer shows
  the ROM's bytes"). Run after 4a lands.
- Exit nonzero on any mismatch; print per-tileset counts + example differing pixels.

**Decode spec** (mirrors `emit.py`; re-verify against code, don't trust this table blind):

| Artifact | Location (per tileset half) | Format |
|---|---|---|
| `tiles.png` | `<fork>/data/tilesets/{primary,secondary}/uranium<ts>/` | P-mode PNG; PIXEL VALUES are the 4-bit indices; embedded palette is a dummy grey ramp (`emit.py:354-375`) — ignore it |
| `palettes/NN.pal` | same | JASC-PAL text, 16× "R G B" 8-bit decimals = exact 5-bit-expanded `(q<<3)|(q>>2)` values; slot 0 always "0 0 0" (`emit.py:393-414`) |
| `metatiles.bin` | same | 8 LE u16 per metatile: 4 bottom quads TL,TR,BL,BR then 4 top; entry = `(tile & 0x3FF) | (hflip<<10) | (vflip<<11) | (pal<<12)` (`emit.py:314-327`) |
| `metatile_attributes.bin` | same | 1 LE u16 per metatile: `(behavior & 0xFF) | (layer_type<<12)` (`emit.py:329-332`) |

Index math: GBA tile 0 = reserved transparent; real tiles are numbered 1..N globally
across the pair, split into the primary file for the first `NUM_TILES_IN_PRIMARY` (512)
and secondary above that; metatiles split at `NUM_METATILES_IN_PRIMARY` (512)
(`emit.py:298-303, 348-391`). Opaque pixel indices are `palette_slot + 1`
(`emit.py:302-312`), so pal-file line k maps to pixel index k (line 1 = index 1 …).
For which half's `NN.pal` the engine actually loads for a given pal number, check
`NUM_PALS_IN_PRIMARY` in the fork's `include/fieldmap.h`; verify whether emit writes
identical content to both halves.

**Which fork tree holds the artifacts:** `$RPG2GBA_POKEEMERALD` — since the 2026-06-19
cutover this is the vendored `engine/`. Confirm via the `.env` the scripts load
(`map_viewer_server.py::_load_dotenv`) and artifact mtimes before comparing.

### 4e. Doc update
`reference/map_viewer.md` — the (uncommitted) "Per-map data pool" caveat section is now
wrong for slice maps; rewrite per §4a.

## 5. Expected outcome

- Maps 48/49: quantized view changes (joint ts19 pool) and now matches the ROM.
- Map032: view should already match a *freshly restarted* viewer with stock knobs; if
  Mode A/B still reports mismatches for ts22, suspect (in order): stale server state
  (§3.1), non-stock knobs (§3.2), browser cache (§3.3), and only then a genuine residual
  pipeline difference — which Mode A will localize to exact metatiles/pixels.
- Per Brandon's standing preference: validate by eye too (side-by-side viewer vs mGBA),
  not just by the byte-compare.

## 6. Resume checklist (if the session cut before landing)

1. `git status` — look for edits to `scripts/map_viewer_common.py`,
   `scripts/map_viewer_server.py`, `reference/map_viewer.md`, and a new
   `scripts/verify_viewer_rom_match.py`. Two sub-agents owned those disjoint sets;
   either may have finished. NOTE: `map_viewer_{common,server}.py` + `map_viewer.md`
   ALSO carry the earlier uncommitted 2026-07-11 feedback-rework — do not revert.
2. If the viewer fix landed: smoke it (`build_map_data(49/48/32)`; maps 49+48 must share
   ONE analysis cache entry keyed frozenset({49,48})). If not: implement §4a-c.
3. If the verifier landed: run Mode A for both tilesets, then Mode B (Mode B was
   deliberately not run by its author — the viewer file was being edited concurrently).
   If not: implement §4d.
4. `ruff check` both scripts; `node --check` the extracted embedded JS; run any
   map_viewer-related tests (grep tests/ for map_viewer).
5. Restart the viewer server before any visual comparison (until §4b lands, a running
   server is stale by design).
6. Update `MEMORY.md` + the auto-memory discrepancy note with the outcome; taildrop a
   fresh static Map viewer page or screenshots if Brandon wants an eye-check.
