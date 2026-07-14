# Corpus-Scaling Audit — 2026-07-14

**Question:** do the slice-1 packing schemes (tilesets, sprite palettes, ROM
layout) survive scaling to the full 199-map corpus — and if not, where and when
do they break?

**Answer in one line:** the per-RMXP-tileset union packing **breaks at slice 2**
(Moki Town + Route 01 alone bust both 1024 caps); per-map packing (already
walker-proven) fits 171/194 non-empty maps and is the fallback that works;
BG palettes are fine everywhere tested; the OBJ 4-shared-bank sprite scheme
dies well before full corpus; the 32 MB ROM fits only with a vanilla-content
stripping pass.

## Method

Five census/probe scripts (session scratchpad, `census_tilesets.py` /
`census_permap.py` / `census_sprites.py` / `probe_quant_worst.py` + aggregate
one-liners), all built on the *real* pipeline code — `column_keys_for_maps` +
`_render_column` from `graphics/build_slice_tilesets.py`, rendered at frame 0,
8×8 quadrants deduped flip-aware, transparent quadrants excluded. "Prequant
tiles" below = that count; the real emitter's post-quantization merge shaves
~9 % more (calibration: Map032 census 1108 prequant vs the actually-emitted
997/1024 with anims). Palette numbers come from running the real
`_canonicalize_and_quantize` packer. Sprite colors are raw source-PNG opaque
colors (upper bound on post-median-cut). All 199 Phase-3 map JSONs, 38 tilesets
in use, 5 blank maps (14/30/38/55/56) excluded where noted.

## 1. BG tileset budgets — the binding constraint, and it binds at slice 2

A GBA tileset pair has two hard 1024 caps: distinct 8×8 tiles and metatile
ids (each = primary 512 + secondary 512).

**Union-per-RMXP-tileset (the current slice scheme) is dead at corpus scale:**
21 of 38 tilesets exceed the tile cap and 19 exceed the metatile cap once all
their maps are unioned. The two biggest offenders are exactly the two tilesets
the playable frontier lives on:

| tileset | maps | union columns (metatiles) | union prequant tiles |
|---|---|---|---|
| ts19 (interiors: houses, labs — 59 maps incl. all slice-1 interiors) | 59 | 2 999 | ~3 700 |
| ts22 (Moki Town / Route 01 outdoor family) | 6 | 3 741 | ~3 260 |
| ts55 | 7 | 3 403 | ~3 586 |
| ts32 | 19 | 2 600 | ~3 668 |
| ts25 / ts24 / ts28 / ts30 … | 2–4 each | 2 000–2 700 | 2 200–2 700 |

**It does not fail gradually — it fails on the very next slice.** Moki Town
(Map032, ts22, 839 columns) + Route 01 (Map033, ts22, 1 016 columns) union to
**1 607 metatiles / 1 611 prequant tiles** — over both caps, before any other
ts22 map joins. The slice-1 build only fits because one big map per tileset is
in so far. (The ts19 interiors union across the 7 slice interiors is still
tiny — interiors individually run 50–90 columns — but 59 interiors union to
~3 700 tiles, so ts19 dies a few slices later.)

**Per-map packing (the walker Phase B scheme, `map_set.py` synthetic ids)
scales:** 171 of 194 non-empty maps fit both caps individually. Distribution of
per-map prequant tiles: 143 maps ≤ 512, 20 ≤ 900, 9 ≤ 1024, 8 in the
1024–1200 borderline band (post-quant merge likely fits most — Map032 itself
is in this band at 1108 and actually emits at 997), 14 genuinely over
(> 1200). The 9 maps whose *metatile* count alone exceeds 1024
(040/071/084/094/101/117/143/144/187) and the census tile-overflow set match
`WALKER_OVERFLOW_MAP_IDS` exactly — independent cross-validation of the
walker-era numbers.

The ~14–16 genuine monsters (up to Map094: 1 806 metatiles / ~2 000 tiles)
need a reduction strategy regardless of scheme: intra-map region split
(two layouts + a seam), and/or the build-side pixel-identity column collapse
deferred in SLICE1_TODO #10 (Map032's 839 column keys are only 697 pixel
classes — a ~17 % metatile reduction on that map for free; unmeasured on the
monsters).

**Consequence for connections (FABLE_PLAN steps 1–2):** "make seam-adjacent
maps share one tileset" is arithmetically impossible for the first seam that
matters (1 611 > 1 024), so the connections design must work *across* two
per-map tilesets. The natural mechanism: emit the neighbor's visible border
strip (camera sees ≤ ~8 metatiles deep past the seam) into *this* map's own
tileset as extra columns — bounded cost, e.g. Route 01's west edge ≈ 8 × 53
columns before dedup, far less after (border terrain is repetitive). The
FABLE_PLAN step-1 eye-census remains useful for judging how much of each strip
dedups away, but the architectural question is already answered: per-map
tilesets + border-strip import, not shared tilesets.

## 2. BG palettes — not a constraint

The real two-phase packer fits every map tested inside 16 BG banks — probed on
the four worst/most-diverse maps, all → **13 palettes**: Map094 (ts22, 1 806
metatiles), Map101 (ts28, 1 556), Map122 (ts31, 1 008), Map032 (ts22, 839,
matches the emitted slice tileset). No palette-driven redesign needed; the
packer's agglomerative bin-packing keeps ~20 % headroom even at maximum art
diversity. (Raw color counts of 1 000–2 300 per tileset union are irrelevant —
median-cut-per-tile does the work before packing.)

## 3. Tileset animation — three bounded gaps

- **55 columns corpus-wide trip the 64-frame lcm fail-loud guard** (ts22×3,
  ts25×3, ts30×3, ts32×3, ts33×12, ts41×12, ts43×6, ts55×13). Cause: a
  19-frame water autotile stacked with a 5-frame autotile in one column →
  lcm 95. Fix is a guard raise to ≥ 95 plus ROM-cost check (95 frames × 32 B ×
  affected tiles ≈ tens of KiB), or rendering such columns per-tile instead of
  per-column-lcm. Today these columns fail the build loud.
- **ts28's animated tiles alone are 543 > 512**, so the "animated tiles pack
  into the primary block" rule breaks there — the secondary-callback variant
  (already an open in SLICE1_TODO #10) becomes mandatory for ts28's maps
  (101 among them).
- Max observed per-column frame need elsewhere: 19 (fits). The 20-entry DMA
  queue per frame remains untested at many-effects (unchanged risk note from
  SLICE1_TODO #10).

## 4. OBJ sprites and palette banks — redesign needed before NPC-heavy slices

- **270 distinct visible-NPC character sheets** corpus-wide carry boot-page
  graphics (door sheets excluded); slice 1 has converted 18 (+ player). That's
  the remaining art-conversion workload, mostly mechanical under the existing
  sprites.py classes. One data bug found: `fk087-machop` is referenced once but
  no such file exists in `Graphics/Characters` (fail-loud will catch it; needs
  a mapping or strip entry).
- **The "all converted NPCs share ≤ 4 global 16-color banks" scheme dies:**
  66 maps exceed 4 banks of raw union colors, 24 exceed 8, and 3 (Map195,
  Map084, Map216) exceed 15 banks *raw* — more colors than the entire OBJ
  palette space before quantization. Per-sheet median-cut will compress these
  substantially (the slice's 18 sheets fit 4 banks), but a global static
  allocation cannot hold 270 sheets.
- **Recommended shape:** per-map palette packing — quantize the union of each
  map's boot-page sheets into per-map shared banks (same packer discipline as
  BG), emit per-map palette tags, and let the engine's native dynamic
  tag-loading do the rest. Player keeps the dedicated 0x1138 bank. The 16-slot
  OBJ ceiling (minus player, minus reflection/field-effect slots) is the
  budget; the three worst maps may additionally need sheet-level palette
  sharing decided by eye. This is a converter-level change (sprite_emit
  allocation), not engine surgery.
- Rough sprite ROM cost at full conversion: 270 sheets ≈ 0.8–1.3 MB
  (9-frame walkers ≈ 4.6 KiB, 1-frame props ≈ 0.5 KiB, a few large props).

## 5. ROM budget — fits only with vanilla stripping

Measured now: **26.47 MB of 32 MB used (78.88 %)** — with the *entire vanilla
Emerald game still in* (slice builds don't stub stock content; only walker
builds did). Headroom: **7.08 MB**.

Full-corpus additions, estimated from the censuses:

| component | basis | estimate |
|---|---|---|
| Per-map tilesets (tiles+metatiles+attrs+pals) | 82 373 prequant tiles ×32 B + 54 495 metatiles ×16 B + attrs + 199×16 pals | **~3.8 MB** (−~9 % post-quant) |
| Animation frame tables | slice ts22 ≈ 20 KiB; 15 animated tilesets, some 95-frame | ~0.3–0.8 MB |
| Map layouts | 560 633 cells × 2 B | **1.12 MB** |
| Event scripts + text | 515 KB source dialogue chars + bytecode/labels overhead | ~1–2 MB |
| NPC overworld sprites | 270 sheets | ~0.8–1.3 MB |
| Uranium mon battle sprites/icons (not yet in any pipeline) | ~190 species × front/back/icon/pals | ~1–1.5 MB |
| Trainer sprites, type icon, UI odds | — | ~0.3–0.8 MB |
| **Total** | | **~8.5–11 MB** |

That overshoots the 7.08 MB headroom by ~1.5–4 MB **before audio** (still
undecided — sequenced m4a is small, sampled audio is not). The recovery lever
is proven: the walker builds already stub stock map data to fit; a Phase-7
stripping pass over vanilla Hoenn layouts/scripts/tilesets/text (keeping
battle/species data, which Uranium's kept-vanilla mons use) should recover an
estimated 2–4 MB. Verdict: **feasible, but ROM % needs tracking per slice**,
and the stripping pass should be assumed in the Phase-7 plan rather than
treated as an emergency escape.

## 6. What this changes (recommended actions, in order)

> **SUPERSEDED IN PART 2026-07-14 (same day, user-approved direction):** items
> 1–2 below are replaced by the **Emerald-style shared-primary design** — a
> per-biome "Uranium-General" primary (cross-tileset common art, 6 pinned
> palettes) + per-map secondaries (7 palettes) — which also fixes the
> same-art-different-colors quantization inconsistency the plain per-map
> scheme would keep. Rationale, measurements (outdoor-family tile overlap up
> to 30% pairwise), and validation gate: `FABLE_PLAN.md` step 2. Items 3–6
> stand unchanged.

1. **Adopt per-map tileset packing for the slice pipeline before slice 2**
   (Route 01 forces it). The machinery exists (`map_set.py` synthetic ids,
   `phase5.convert_all`); the work is promoting it from walker-only to the
   slice/assembler path — including the warp/tile_map overlay and staging
   hygiene (the known shared-mutable-staging wart).
2. **Fold the border-strip import mechanism into the connections design**
   (FABLE_PLAN step 2) — shared tilesets are off the table by arithmetic; the
   seam eye-census (step 1) now measures strip dedup potential, not scheme
   choice.
3. **Plan the monster-map reduction pass** (14–16 maps): pixel-identity column
   collapse first (cheap, measured 17 % on Map032), intra-map split for
   whatever remains. None of these maps is on the near frontier — not urgent,
   but it gates "full corpus", and Map094 is in ts22's family (town-adjacent).
4. **Redesign OBJ palette allocation to per-map packed banks** before the
   first NPC-heavy slice (town interiors are fine; the 66-maps-over-4-banks
   set includes major cities).
5. **Animation:** raise the lcm guard to ≥ 95 with per-column ROM-cost
   accounting; schedule the secondary-anim callback variant when ts28's maps
   enter the frontier.
6. **Track ROM usage per slice build** (one `ls`-grade number in the build
   log) and write the vanilla-stripping pass into the Phase-7 plan.

## Loose ends / data bugs found en route

- `fk087-machop` sheet referenced by one boot page, file missing from
  `Graphics/Characters` — needs an npc_gfx_map entry pointing at the real
  file (case/spelling) or a strip decision.
- 5 blank placeholder maps (14/30/38/55/56) and per-map garbage tile ids are
  already handled by existing drop paths; unchanged.
- Census scripts live in the session scratchpad (patterns:
  `census_tilesets.py`, `census_permap.py`, `census_sprites.py`,
  `probe_quant_worst.py`); the method is fully described above and rebuilds
  from `output/uranium-build/maps` + the real graphics pipeline in ~30 s.
