# Fable Capacity Plan — days-scale horizon

Fable (this model tier) may leave the Pro plan soon. This is the ordered plan for
spending the remaining access on the work where model quality matters most:
design decisions that propagate corpus-wide, and specs a cheaper model can
execute later. Slice grind, test pinning, viewer work, and doc housekeeping are
explicitly *not* on this list — those run fine on Opus/Sonnet under the existing
/delegate pattern.

Rationale (from the session that produced this): the expensive historical
failures were reasoning failures (invented `healparty`, silently-flattened
branches, false "needs custom C" claims, unpinned palette off-by-one), and the
wins were multi-constraint root-causes. Optimize Fable time for design +
hard debugging, not typing.

## Step 1 — USER: measure how bad the seam problem actually is

Claim to verify: per-map synthetic tileset packing conflicts with GBA map
connections, because the engine renders a connected neighbor's border rows/cols
using the *current* map's tileset banks → tileset bleed at seams. User's
counter-hunch: this is less of a problem than it sounds. Check before designing
anything.

What to investigate (any of these can kill or shrink the problem):

- **Do seam pairs share a Uranium tileset?** For each of the 14
  `connections.dat` seams (recon already done — Checkpoint-2 notes,
  `reference/viewer/walker_checkpoint2_findings.md`), compare the two maps'
  RMXP tileset ids. If a connected pair uses the same source tileset, packing
  them into one shared synth pair (per connected component instead of per map)
  may dissolve the bleed with data changes only.
- **How much of the neighbor is ever visible?** GBA draws ~7 rows / ~15 cols of
  the neighbor at the edge. If Uranium's seam borders are mostly uniform
  terrain (grass/path/treeline), even a mismatched render may be cosmetically
  tolerable or fixable with border-metatile alignment alone.
- **Column-key overlap at the actual border strips.** Even across different
  tilesets, if the border strips' columns resolve to visually-equivalent
  metatiles, a small seam-alias table could map neighbor metatile ids into the
  current map's table.
- Existing tooling to lean on: the map viewer, `scripts/compare_collision.py`
  patterns, and the connections recon in the Checkpoint-2 findings doc.

Deliverable: a short verdict per seam — SHARED-TILESET / UNIFORM-BORDER /
GENUINELY-MIXED — and a call on whether step 2 is a real design session or a
small mechanical fix.

## Step 2 — Connections design — DIRECTION CHOSEN 2026-07-14 (user approved):
## Emerald-style shared "Uranium-General" primary + per-map secondary

Step-1 seam census DONE (all 14 seams enumerated with tileset pairing — 6/14
same-tileset, 8/14 differ; even same-tileset pairs mostly bust the shared-1024
budget). But the design direction changed after the user observed **color
inconsistency** (same tree/cliff art quantizes to different colors per map,
e.g. Route 02 vs Nowtoch cliffs): Emerald solves this structurally —
`gTileset_General` is primary for 416 layouts and owns BG palettes 0–5
game-wide; secondaries carry area art in palettes 6–12. Measured on Uranium's
outdoor family (ts22/23/24/25/28/30): tilesets share pixel-identical rendered
tiles (ts22∩ts24 = 688 = 30% of smaller; family dedup saves ~2 900 tiles), so
the same architecture fits us:

- **Uranium-General primary per biome family** (outdoor / cave / interior):
  cross-tileset common tiles, ≤512, with 6 palettes computed once + pinned.
- **Per-map secondary** with only non-General art, quantized against the
  remaining 7 palettes (`quantize_tile_to_palette` pattern).
- Buys: identical common art everywhere (the color complaint), seams mostly
  render right even across DIFF-tileset pairs (border art is mostly General;
  strip-import shrinks to secondary remnants), ~MB-scale ROM dedup, monster-
  map relief. Supersedes the audit §6.1–6.2 plain "per-map packing +
  border-strip import" as the step-2 design.
- **Validation gate RUN 2026-07-14 — shared-TILE architectures FAIL the
  budget; pinned family PALETTES survive as the color fix.** Prototype
  results (scratchpad proto_general{,2,3}.py, outdoor family
  ts22/23/24/25/28/30, 21 maps, 12 035 unique tiles):
  - Cross-tileset General (top-512) DOES pack into 6 palettes with the base
    packer (mean shift 1.29/31; round-1 "failure" was the family packer's
    per-hue-group floor — use `build_quantized_tileset` for capped packs).
  - BUT every tile-sharing variant starves the per-map secondary: strict
    family General → 17/21 maps over 512 residual (median coverage 40%);
    per-RMXP-tileset primary → Kevlar 671 / Route 01 613 / Map008 598 over;
    per-seam-component primary → 5/8 components over even on non-monster
    maps (Kevlar 519, Map142 658, Map145 682…). Root cause: Uranium outdoor
    maps need ~600–1 100 map-specific tiles; Hoenn's 512/512 primary/
    secondary split assumes art economy Uranium doesn't have. Total 1024/map
    is the hardware-ish ceiling (10-bit tile ids), so shared blocks directly
    cannibalize map budget.
  - **Revised step-2 architecture:** per-map packing (audit §6.1 stands
    after all) + **family-pinned palettes** (quantize every map in a biome
    family against ONE pinned 13-palette set → same art renders identical
    colors everywhere, deterministically) + border-strip import for seams
    (strips are small; per-map budgets absorb them). Component-shared
    primaries remain a selective optimization where they fit (Snowbank
    pair fits today).
  - **Per-seam-component repack (user retest) RUN 2026-07-14, dev maps
    excluded: all 8 components pack into 13 palettes**, 2–34 s each (vs
    15 min for the whole-family blob — prefer component-sized packs).
    Measured 5-bit shift, component pack vs per-map baseline: Moki+R03
    1.56 (bases 1.45/1.48); Kevlar+R02+Nowtoch 1.62 (1.36/0.75/1.51);
    Rochfale+R06 1.63; Silverport+R15 1.63; Snowbank 1.18; R05+R04+R12
    1.78; Venesi×4 1.80; Bealbeach×4 1.96 (worst). Pinning costs ~+0.1–0.5
    mean on complex maps but up to +1.4 on simple ones (Map099 0.38→1.80,
    Map035 0.75→1.62) — vs the slice's shipped 0.93–0.98. Verdict: palette
    grouping at seam-component granularity is the right unit; EYE CHECK
    REQUIRED before adopting (numbers are advisory per quantize.py's rule).
  - **Eye-check round SENT 2026-07-14 (verdict pending):** full-map
    before/after previews for Moki+R03 taildropped + in
    `output/tileset_palette_study/` (per-map LEFT vs component-pinned RIGHT
    + unquantized originals). Lead's read: original plateau dirt = warm tan;
    per-map pack drifts it PINK, component pack drifts it ORANGE — neither
    faithful, but the component version drifts BOTH maps identically (the
    actual win: chromatically seamless seams). **Next lever if user rejects
    both hues: cell-count WEIGHTS** — the packer treats unique tiles equally
    (`build_quantized_tileset(weights=...)` exists, unused); large-area
    terrain (dirt = huge area, few unique tiles) deserves palette resolution
    proportional to coverage. Study folder README carries the full round log.
  - Test C RESULT (whole-family blob, superseded by the above granularity): The production
    packer (`build_quantized_tileset_family`) packs the ENTIRE outdoor-family
    union — all 12 035 unique tiles across ts22/23/24/25/28/30 — into
    **13 palettes** (took ~15 min; fine as a once-per-family offline
    computation; the plain global packer is too slow at this size — use the
    family packer). Remaining acceptance = BY EYE per quantize.py's own
    rule: render before/after previews of two maps sharing art (e.g. Route
    02 vs Nowtoch cliffs, Moki vs Route 03 trees) under the pinned set and
    have the user compare. Then the implementation is: compute + pin family
    palettes once (new SoT artifact), quantize each map's tiles against
    them via the `quantize_tile_to_palette` path instead of deriving
    per-pack palettes.

## Step 3 — Corpus-scaling audit — DONE 2026-07-14

Findings: **`reference/findings/corpus_scaling_audit_2026-07-14.md`**. Headline:
per-tileset union packing breaks at slice 2 (Moki+Route 01 = 1 611 tiles /
1 607 metatiles > both 1024 caps) → adopt per-map packing (walker-proven,
171/194 maps fit; 14–16 monsters need a split/collapse pass); BG palettes fine
everywhere (worst maps all 13/16); OBJ 4-global-bank sprite scheme dies at
corpus (270 sheets, 66 maps > 4 banks) → per-map packed banks; ROM fits only
with a Phase-7 vanilla-stripping pass (~8.5–11 MB additions vs 7.08 MB
headroom). **Side effect on steps 1–2:** shared seam tilesets are
arithmetically impossible, so the connections mechanism must be border-strip
import across per-map tilesets; the step-1 eye-census now measures strip dedup
potential, not scheme choice.

## Step 4 — Audio architecture decision — DONE 2026-07-14

Findings: **`reference/findings/audio_decision_2026-07-14.md`**. Headline:
substitution table `reference/audio_map.json` (new SoT, fork-index-validated)
consumed by metadata_wiring (per-map BGM replaces the MUS_LITTLEROOT hardcode)
+ transpiler (playbgm/playfanfare/playse; SKIP/unmapped → comment+report).
Conversion/streaming rejected by arithmetic (187 MB OGG, 3 MIDIs, ~7 MB ROM
headroom). Demand is small: ~65 distinct BGM, 11 MEs (all standard jingles),
head-heavy SE. Slice-1 bar (user call pending): ~15-row table for the 8 slice
maps. Phase-8 lane: sequence signature tracks as MUS_URANIUM_*, one table row
each.

## Step 5 — Phase 6 + Phase 7 specs — DONE 2026-07-14

- **`reference/guides/nuclear_type_spec.md`** — implementation-ready Phase 6
  spec. Notable: ROADMAP §6.4 was WRONG (no out-of-battle HP drain exists in
  Uranium — the field damage is plain poison; the real mechanic is 50%
  in-battle disobedience for `isNuclear? && !nuclearFree`, cured by the
  EXPUNGE field move — all verified in `reference/scripts_dump/`). ROADMAP
  6.4 corrected. Type chart verified from `types_dump.json` (Nuclear: 2× vs
  all except Steel/Nuclear ½×; takes 2× from all except Nuclear ½×); type
  index remap Uranium→fork required (fork TYPE_NUCLEAR = 21 after STELLAR).
- **`reference/guides/phase7_integration_plan.md`** — the debt ledger
  (D1–D10: items.h merge-not-replace, species gfx/cries pipeline gap, fork-
  gate extras unblocking SLICE1_TODO #2, engine cutover first, encounters/
  trainers wiring, save-capacity, vanilla stripping, audio table, deferred
  Phase-2 exit criteria) with order of attack and verify-first warnings.

## Standing reserve

Any boot-gate bug that resists a first-pass diagnosis goes to Fable while
access lasts — that bug class (palette off-by-one, vacuous cycle detection,
reflection scan box, null-flag respawn) is where the tier difference has paid
for itself.
