# Vendored engine — provenance & rules

This `engine/` tree is **pokeemerald-expansion**, vendored into rpg2gba on
**2026-06-18**.

## Provenance
- Forked from **rh-hideout/pokeemerald-expansion** at upstream HEAD
  **`21c24202`** ("Fix Toxic Debris checking Toxic Spikes cap on the wrong side
  (#10002)").
- Imported as a **flat vendor** via `git archive HEAD` from a shallow clone — so
  there is **no upstream history** here. To take upstream fixes, re-vendor at a
  new SHA by hand (deliberate, not automatic). We do not push back upstream.

## Why vendored (not an external fork)
Custom engine C now lives in version control next to the pipeline that needs it,
the engine version is pinned (no silent upstream drift), and a fresh clone of
rpg2gba is reproducible. See MEMORY → Decisions Made 2026-06-18.

## Legal
Upstream ships **no LICENSE** (pret-style decomp; legal gray area). This is a
**personal, non-distributed** project. The decomp **source** here contains **no
copyrighted ROM data** — the base Emerald ROM and any Uranium assets are provided
separately at build time and are **never** committed. Build artifacts (`build/`,
`*.gba`) stay ignored by this tree's own `.gitignore`.

## Our custom changes (hand-written, version-controlled here)
Sentinel-fenced `URANIUM PATHFINDER SLICE` blocks in:
- `src/new_game.c` — new-game spawn redirect (→ Map049) + intro-skip callback
- `src/intro.c` — jump straight into the slice
- `include/new_game.h` — prototype

These are **test-only** baseline divergences; revert/gate before a real build.

## Generated output is NOT committed
The rpg2gba pipeline (`scripts/assemble_pathfinder.py`) writes generated maps,
layouts, scripts, and headers **into this tree**. Those are gitignored (see the
repo-root `.gitignore`) and regenerated — **never commit pipeline output as
engine source**. Known wrinkle: the assembler currently *edits a few tracked
upstream files in place* (`data/event_scripts.s`, `data/layouts/layouts.json`,
`data/maps/map_groups.json`); those stay tracked **pristine** and the assembler's
edits to them must not be committed. Making the assembler use include-hooks
instead of in-place edits is a BUILD_PLAN follow-up.
