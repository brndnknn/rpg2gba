# Pathfinder Step 2 — Tileset Substitution (`tile_map.py` + `tileset_map.json`)

> Detailed implementation plan for **S2** of `PATHFINDER_SLICE_ROADMAP.md`.
> Implements `PHASE5_PLAN.md §5.1` scoped to the pathfinder's two tilesets
> (**19 interior, 22 Moki Town**). Q1–Q5 are already resolved (PHASE5_PLAN); this
> plan does not re-open them. The stub `src/rpg2gba/tileset_converter/tile_map.py`
> already defines the data model and block-packing constants — we fill the
> `NotImplementedError`s and author the table data.

---

## What "done" means for the slice

1. `tile_map.py`'s `load_tile_map`, `_validate`, `TileMap.lookup`,
   `TileMap.tileset_for` are implemented and tested.
2. `reference/tileset_map.json` has **complete** `tilesets` + `tiles` entries for
   Uranium tilesets **19** and **22** — every tile id that maps 49/48/32 actually
   use resolves, and `lookup` fails loud on anything else.
3. Collision/elevation on each mapped tile is good enough that S3+S8 produce a
   **walkable** bedroom, house, and town (the real test is boot, not the unit test).

This is the *long pole* because (2) is hand-authoring grunt work. The two
techniques below shrink it from "hundreds of ids" to "a few dozen".

---

## v1 APPROACH (DECIDED 2026-06-15) — pure passability buckets

The P2 census found **433 distinct tiles** (117 in tileset 19, 316 in 22) — too
many to hand-author for throwaway Approach-A art. **User decision: pure passability
buckets first, hand-map the high-frequency tiles later.** Everything below the
"Tileset assignment" heading describes the eventual **hand-mapped** table (the
refinement iteration); for **v1**, that table is mostly empty and resolution falls
to per-tileset buckets:

- **`tileset_map.json` gains a `buckets` section** (per Uranium tileset):
  ```json
  "buckets": {
    "19": { "passable": <metatile>, "blocked": <metatile>, "void": <metatile> },
    "22": { "passable": <metatile>, "blocked": <metatile>, "void": <metatile> }
  }
  ```
  Just **3 metatile ids per tileset** (a generic floor/ground, a generic wall, a
  border/void) — ~6 ids for the whole slice, harvested from the vanilla analogue
  maps (`BrendansHouse_1F` floor+wall; `LittlerootTown` ground+wall). The `tiles`
  table stays in the schema but is **empty in v1** (it is where hand-mapping lands
  later — each `tiles` entry will override its bucket).

- **`lookup(tileset_id, tile_id)` resolution order (v1):**
  1. explicit `tiles[tileset_id][_normalize(tile_id)]` if present (empty in v1);
  2. else **bucket fallback**: read `passages[tile_id]` from `tilesets.json`; if
     `(passage & 0x0F) == 0` → `buckets[ts].passable` (collision 0); else
     `buckets[ts].blocked` (collision 1). Elevation 3.
  3. Fail loud only if the tileset has **no bucket** (never silently metatile 0).
  ⇒ `TileMap` now also holds the per-tileset `passages` arrays (load them in
  `load_tile_map` from `output/uranium-build/tilesets.json`). This keeps fail-loud
  in spirit — the fallback is explicit, logged, and counted, not a silent default.

- **Collision comes from the source `passages`, combined across layers** — this is
  resolved in S3's `collapse_column`, not here: a cell is blocked if **any
  non-empty layer whose `priorities[tile]==0`** has `passage & 0x0F != 0` (the
  `priorities>0` over-the-player roof/treetop tiles do not block). For v1 a simpler
  topmost-non-empty collision is acceptable; the layer-combined rule is the
  refinement §5.6 reachability backstops.

- **Warps/doors/stairs need no special tile:** they are passable (passable bucket,
  collision 0) and S5's `warp_event` fires on the coordinate regardless of the
  tile's appearance.

Result: v1 is **~6 hand-picked metatiles total**, every tile resolves, the slice is
walkable with correct collision, and it looks flat (one floor + one wall texture
per tileset). The rest of this document is the **later** fidelity pass.

---

---

## Two facts that shrink the grunt work

### Fact 1 — Autotiles collapse 48→1

RMXP tile ids `48..383` are **autotiles**: 7 autotiles × 48 auto-bordering
variants each (`autotile_n` owns ids `[48n, 48n+47]`, base `48n`). All 48 variants
of one autotile are the **same logical terrain** (a floor, water, a path) drawn
with different edges. Under Approach A we do not reproduce edges — we map the whole
autotile to **one** metatile.

⇒ **`lookup` normalizes any autotile id to its base before the table lookup:**

```python
def _normalize(tile_id: int) -> int:
    if 48 <= tile_id < 384:          # autotile range
        return (tile_id // 48) * 48  # 52,56,76 -> 48 ; 100 -> 96 ; ...
    return tile_id                   # 0 (empty) and >=384 (static) unchanged
```

So `tileset_map.json` keys autotiles by **base id only** (`48,96,144,192,240,288,
336`), not the 336 individual variant ids. Confirmed against Map049: its floor
ids `48,52,56,76` are all autotile 1 → one entry `"48"` covers them.

### Fact 2 — Static-tile palette per map is small

Static tiles (`≥384`) are real furniture/wall/decoration tiles. A bedroom uses
maybe 15–30 distinct ones; a small town 30–60. We only author the ids the **three
slice maps actually reference**, harvested mechanically (below), not the whole
tileset.

---

## Prerequisites (run once, before authoring)

### P1 — Generate the passages oracle

`tilesets.json` is **not yet in `output/`**. Generate it so we can inherit
source-side walkability:

```
ruby src/rpg2gba/rxdata_deserializer/deserialize.rb tilesets \
     <uranium Data dir> output/uranium-build/
```

(`deserialize.rb tilesets` mode already exists — see MEMORY "Phase-5-prep
artifacts".) Yields per-tileset `passages` / `priorities` / `terrain_tags` flat
arrays. `passages[tile_index]` is the RMXP per-tile passability bitfield — the
ground truth for collision inheritance (§5.6 also consumes this).

### P2 — Harvest the used tile-id set

Write a throwaway analysis helper (`scripts/pathfinder_tile_census.py`, read-only,
no converter logic) that, for maps 49/48/32:

- builds the `TileGrid` (reuse `layout.TileGrid`), walks every `(x,y,z)`,
- collects `_normalize(tile_id)` for all non-zero ids, grouped by `tileset_id`,
- prints, per tileset, the sorted distinct **normalized** ids and an occurrence
  count, and tags each `autotile n` vs `static (row,col)=divmod(id-384,8)`.

Output is the **exact authoring worklist**: tileset 19 → {its ids}, tileset 22 →
{its ids}. (This script is a planning/authoring aid, not pipeline code — it may
live in `scripts/` and is not part of the §5.1 acceptance.)

---

## Tileset assignment (Q4) for the slice

Q4's "one universal pair" generalizes to **one pair per Uranium tileset**; the
slice has two:

| Uranium tileset | Role | pokeemerald primary | pokeemerald secondary | Why |
|---|---|---|---|---|
| **19** | player's house interior | `gTileset_Building` | `gTileset_BrendansMaysHouse` | vanilla player-house interior — direct thematic match for `\PN's house`. **Primary is `gTileset_Building`, the INDOOR primary — not `gTileset_General` (outdoor). Confirmed from `LittlerootTown_BrendansHouse_1F`'s layout entry during the S2 harvest.** |
| **22** | Moki Town outdoor | `gTileset_General` | `gTileset_Petalburg` | the shared early-region small-town secondary — **this is the tileset `LittlerootTown` (Emerald's starter hometown) itself uses** (layouts.json:109), not Petalburg City's own. Carries grass/path/tree/house-wall/house-door/water/fence/sign. |

Both are confirmed present in the fork (`data/tilesets/secondary/brendans_mays_house`,
`.../petalburg`). Note: there is **no** `gTileset_Littleroot` — Littleroot, Oldale,
and the other early towns all share `gTileset_Petalburg`, so it is the correct
hometown analogue despite the name. Secondaries are swappable later without
touching `tile_map.py`.

### Sourcing real metatile ids (no Porymap GUI needed)

We need legal `metatile_id`s in the chosen tilesets and their visual roles. Rather
than eyeball a GUI, **harvest them from a vanilla map that already uses the
tileset**:

1. Pick a vanilla analogue map: `BrendansHouse_1F` (interior — the player's house)
   / `LittlerootTown` (town — Emerald's starter hometown, the right analogue for a
   starter hometown; it uses the same `gTileset_Petalburg` secondary we assigned to
   tileset 22, so its blocks are legal targets).
2. Decode its `data/layouts/<Name>/map.bin` with the inverse of `to_block`
   (`metatile = block & 0x3FF`, `collision = (block>>10)&3`, `elev=(block>>12)`).
3. The set of metatile ids it uses, cross-referenced with where they sit on the
   map (a floor fills the room interior; walls line the top; a door is one tile on
   the bottom edge), gives **known-good ids with known roles and known
   collision/elevation** — exactly what we copy into `tileset_map.json`.

This makes the table data *derived from working vanilla maps*, not guessed. A small
read helper for this can reuse `layout.read_blockdata`.

### Minimum role set the slice needs

- **Interior (19):** floor, wall (top/side, impassable), inner-wall trim, a door /
  warp tile (passable, the 48→32 / 49↔48 exits), 2–4 furniture statics
  (bed/desk/shelf — collision=1), a generic "void/border" tile.
- **Town (22):** grass (passable, elevation 3), path/dirt, tree (impassable),
  house-wall (impassable), house-door (passable warp tile), sign (impassable, the
  sign event sits on it), water (impassable — HM-gated, fine for v1), fence
  (impassable), void/border.

Roughly **~12 interior + ~16 town** metatile assignments. That is the whole S2
authoring job.

---

## `tile_map.py` implementation

### `load_tile_map(path)`

- Open with `encoding="utf-8"`; `json.load`.
- Call `_validate(raw)` **before** building anything (fail loud early).
- Coerce string JSON keys → `int`: `tilesets {int: TilesetChoice}`,
  `tiles {int: {int: Metatile}}`, and (optional) `stacks {int: {str: Metatile}}`
  keeping the `"z0,z1,z2"` string key as-is for composite lookup.
- Build `Metatile(metatile_id, collision, elevation)` from each entry; apply the
  documented defaults when a field is omitted (`collision=0`, `elevation=3` — the
  dataclass defaults already encode this, but be explicit when constructing from
  partial dicts).
- Return `TileMap(tiles, tilesets, stacks)`. **Note:** the current stub's
  `TileMap.__init__` takes `(tiles, tilesets)` — extend it to also accept the
  optional `stacks` map (default empty) so Q1 composite overrides work; keep the
  signature backward-compatible.

### `_validate(raw)`

Fail loud (raise `ValueError` with a precise message) if:

- top-level keys `"tilesets"` and `"tiles"` are missing (`_SCHEMA`);
- any `tilesets` entry lacks `primary`/`secondary` or they are not non-empty str;
- any `tiles` metatile id is missing, `None`, negative, or `> 0x3FF` (the
  10-bit `METATILE_ID_MASK` ceiling — anything bigger silently truncates in
  `to_block`, the exact silent-default we forbid);
- any `collision` ∉ {0,1,2,3} or `elevation` ∉ 0..15 (their packed field widths);
- a `tiles` key references a `tileset_id` absent from `tilesets`;
- (if present) any `stacks` composite key is not three comma-separated ints.

Validation is the safety net that stops a malformed hand-edit from reaching S3.

### `TileMap.lookup(tileset_id, tile_id)`

Resolution order (Q1 hybrid + Fact 1):

1. **Empty:** `tile_id == 0` → raise/return per the documented policy. **Decision
   for the slice:** `lookup` only ever receives a *chosen* tile id from
   `collapse_column` (which already picked the topmost non-empty layer), so a `0`
   reaching here means "the whole column was empty" — that is `collapse_column`'s
   call, not `lookup`'s. Keep `lookup` strict: `tile_id == 0` is not a valid
   single-tile lookup; the empty-column policy lives in S3. (`lookup` may simply
   never be called with 0.)
2. **Composite stacks** are consulted in `collapse_column` (it has the full
   `z0,z1,z2`), *not* here — `lookup` is the single-tile resolver. Keep the
   responsibilities split exactly as the stubs draw them.
3. `nid = _normalize(tile_id)` (Fact 1).
4. `try: return self._tiles[tileset_id][nid]` — on `KeyError`, **re-raise with
   both ids and the normalized id** in the message, e.g.
   `f"unmapped tile: tileset={tileset_id} tile_id={tile_id} (normalized {nid}); add it to reference/tileset_map.json"`.
   Never return a default.

### `TileMap.tileset_for(tileset_id)`

Return `self._tilesets[tileset_id]`; `KeyError` → re-raise naming the unmapped
tileset id ("no (primary,secondary) assigned").

---

## Collision / elevation policy (Q3, for the slice)

Inherit the baseline from the chosen metatile (already encoded by copying
collision/elevation out of the harvested vanilla blocks). Two slice-specific
refinements, applied as per-tile overrides in `tileset_map.json` only where the
vanilla baseline is wrong for our use:

- A tile the player must **stand on / walk through** (floor, path, grass, door,
  warp tile) → `collision = 0`.
- A tile that is **scenery / furniture / wall / tree / sign** → `collision = 1`.
- Cross-check against the P1 `passages` oracle: if RMXP says a tile is passable but
  our metatile inherited `collision=1` (or vice-versa), the override fixes it. This
  is the cell-level walkability guard that §5.6 automates later; for the slice we
  apply it by hand to the ~28 mapped tiles.
- `elevation = 3` (normal ground) for everything walkable indoors and on town
  ground; keep vanilla elevation for multi-level town tiles if any (unlikely in a
  flat starter town).

---

## Tests (`tests/test_tileset_converter.py`, un-skip the 5.1 cases)

- **Golden:** a tiny hand-built table (2 tilesets, a handful of tiles incl. one
  autotile base and one static) → assert `lookup` returns the exact `Metatile`.
- **Autotile normalization:** `lookup(t, 52)` and `lookup(t, 76)` both resolve to
  the entry keyed `48`. `lookup(t, 96)` → entry `96`, not `48`.
- **Fail loud:** `lookup` on an unmapped id raises with both ids in the message;
  `tileset_for` on an unmapped tileset raises.
- **Round-trip:** load → serialize → load is stable (same in-memory structure).
- **Validate rejects:** metatile id `> 0x3FF`, `collision = 4`, missing
  `secondary`, a `tiles` tileset absent from `tilesets` — each raises `ValueError`.
- **Slice integration (lightweight):** load the *real* `reference/tileset_map.json`
  and assert every normalized id from the P2 census of maps 49/48/32 resolves
  (this is the "no holes" guard; it can be marked to skip if the census file isn't
  present, like the phase4 live-binary tests).

---

## Work order

1. P1 generate `tilesets.json`; P2 write the census helper, run it → authoring
   worklist.
2. Implement `load_tile_map` / `_validate` / `lookup` / `tileset_for` + unit tests
   (golden/autotile/fail-loud/round-trip/validate) — these need no table data.
3. Harvest metatile ids from `BrendansHouse_1F` + `LittlerootTown` map.bin.
4. Author `tileset_map.json` entries for tilesets 19 & 22 from the worklist +
   harvested ids; run the slice-integration test until zero holes.
5. Hand off to S3 (`layout.py`) — it consumes `lookup`/`tileset_for`.

**Do not** proceed to S3 emit until step 4's no-holes test is green: a hole there
becomes an invisible bad metatile (or a hard fail) in the layout.
