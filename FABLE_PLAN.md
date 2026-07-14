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

## Step 2 — Connections design (scope set by step 1)

If step 1 says "mostly shared tilesets": design = connected-component packing
(group maps that share seams into one synth tileset family; verify tile/palette
budgets still fit per component). If "genuinely mixed": full design session —
options include seam-alias metatile tables, border-row re-emission, or accepting
per-seam curated borders. Either way the output is a `reference/` design doc,
not code. Moki Town E ↔ Route 03 is the slice-2 frontier seam, so this gates
slice 2 regardless.

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

## Step 5 — Phase 6 + Phase 7 specs (if time remains)

- **Nuclear type spec:** type-chart source of truth from Uranium data, field
  damage tick integration point, cured-form via evolution method vs form
  change. Written so a Sonnet builder can implement against it.
- **Phase 7 integration/reconciliation plan:** the `items.py` full-replacement
  landmine (vanilla item behavior zeroed — flagged at items.py:284-286),
  Uranium species constants joining the fork-gate extras (unblocks SLICE1_TODO
  #2), save-capacity re-check against later slices' mint counts.

## Standing reserve

Any boot-gate bug that resists a first-pass diagnosis goes to Fable while
access lasts — that bug class (palette off-by-one, vacuous cycle detection,
reflection scan box, null-flag respawn) is where the tier difference has paid
for itself.
