# Connections & Palette Families — Step-2 Design (decided 2026-07-14)

The architecture for map connections (seams) and cross-map color
consistency, decided after the corpus-scaling audit, the seam census, the
shared-tileset prototypes, and a user eye-gate. Evidence trail:
`reference/findings/corpus_scaling_audit_2026-07-14.md`, `FABLE_PLAN.md`
step 2 (running log with all measured numbers), and the visual study in
`output/tileset_palette_study/` (regenerable via its `scripts/`).

## The decision, in three parts

1. **Per-map tileset packing** (each map gets its own dedicated
   primary+secondary pair, walker-style synthetic ids). Every shared-tileset
   variant was measured and fails: Uranium outdoor maps need ~600–1 100
   map-specific tiles, so any shared block starves the 512-tile secondary
   (Hoenn's General/secondary split assumes art economy Uranium doesn't
   have). 171/194 non-empty maps fit; the ~14–16 monster maps need a
   separate split/collapse pass regardless.
2. **Palette families pinned per seam component** (USER-APPROVED by eye
   2026-07-14, Moki+Route 03 previews): the 14 `connections.dat` seams form
   8 connected components (max 4 maps); each component's maps are quantized
   against ONE palette set computed over the component's tile union.
   Quantization is deterministic → same art + same palettes = pixel-identical
   rendering across the component, so seam borders match chromatically.
   All 8 components pack into 13 palettes (2–34 s each with the production
   family packer). Isolated maps (no seam) keep per-map packs at zero cost.
   Known accepted cost: component packs shift colors slightly more than
   per-map packs (Moki dirt reads orange vs the original warm tan; the user
   prefers this consistent drift over per-map inconsistent drift).
   **Do NOT revisit vocab weighting** — linear and log-damped area weighting
   both reproduce the historical cross-family-snap bug (red roofs, salmon
   cliffs); the packer's unweighted two-phase design stands.
3. **Border-strip import for seam geometry**: the engine renders a
   connected neighbor's border with the CURRENT map's tilesets, so each map
   in a component imports the neighbor's visible border strip (≤ ~8
   metatiles deep past the seam) as extra columns/tiles in its own tileset.
   With component-pinned palettes those imported tiles quantize to exactly
   the neighbor's colors. Strips are small and repetitive; per-map budgets
   absorb them (verify per component at build — fail loud on overflow like
   everything else).

## The 8 components (from `connections.dat`, 14 entries)

Moki+R03 · R05+R04+R12 · Rochfale+R06 · Silverport+R15 · Snowbank+Gym ·
Kevlar+R02+Nowtoch · R07+R08+plant+Bealbeach · Venesi+R13+R14+Tsukinami.
(Entry format `[map_a, edge, offset, map_b, edge, offset]`; the census with
tileset pairing and per-map budgets is in the study folder's
`connections.json` + `census_permap.json`.)

## Implementation sketch (slice-2 scope = Moki+R03 only)

1. **Promote per-map packing** from the walker path (`map_set.py`,
   `phase5.convert_all`) into the slice/assembler path (S8a currently packs
   per RMXP tileset — Moki+Route 01 already bust that at slice 2). Includes
   tile_map overlay + warp metatiles + staging hygiene per map.
2. **New SoT artifact: pinned component palettes** —
   `reference/palette_families.gen.json` (or per-component files): component
   id → 13 palettes, computed once from the component's tile union by the
   production packer, committed like `tileset_map.gen.json` overlays.
   Consumers: `build_slice_tilesets` quantizes member maps' tiles against
   the pinned set (`quantize_tile_to_palette` path — same mechanism the
   animation frames already use) instead of deriving palettes per pack.
   Component membership table (map id → component) derived from
   `connections.dat` deterministically; isolated maps absent → per-map pack.
3. **Emit `connections` in map.json** for member maps (porymap schema:
   direction/offset/map) so the engine renders the seam; RMXP offset signs →
   GBA offset convention needs one careful worked example (Kevlar N offset
   11 vs Moki E offset 26 — verify in-ROM at the boot gate).
4. **Border-strip import**: for each connection, enumerate the neighbor's
   border strip columns (depth ~8), render+quantize them into THIS map's
   tileset as extra metatiles, and stamp them into a border/edge region the
   connection renders. (Exact mechanism for what the engine samples at the
   edge — `map.json` border block vs the neighbor's real map data — needs a
   fork read of `fieldmap.c` connection handling before coding; do that
   first, §4.7.)
5. **Anim + terrain integration**: animated tiles and terrain-tag behaviors
   already key per tileset — unchanged by pinning (palettes only). Animated
   frames re-quantize against the pinned palette exactly as today.
6. Slice-2 boot gate walks the Moki↔Route 03 seam: colors match, collision
   sane at the edge, no tile garbage in the neighbor strip.

## Standing constraints

- Monster maps inside components (Nowtoch, Bealbeach, Venesi, Tsukinami…)
  still exceed per-map budgets alone — the split/collapse pass gates those
  components' conversion, not Moki+R03.
- Palette pinning is per component, not global: art shared BETWEEN
  components may still differ slightly across distant regions. Accepted;
  revisit only if a walk makes it jarring (option then: merge components
  into larger families and re-eye-check, cost grows with union size).
- `RPG2GBA_*` budget guards stay fail-loud everywhere (tiles, metatiles,
  palettes, strip overflow).
