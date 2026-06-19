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

**Include-hooks — permanent infrastructure (commit these).** Sentinel-fenced
`URANIUM PATHFINDER SLICE` blocks that let the assembler inject the slice WITHOUT
editing any tracked upstream file in place — all per-slice content lands in
gitignored generated files, so the tree stays clean after an assembly run:
- `data/event_scripts.s` — `#include`s the generated flag/alias headers and
  `.include`s the generated `data/maps/uranium_includes.inc` (the slice's
  script-include list).
- `map_data_rules.mk` — `URANIUM_MAP_GROUPS` / `URANIUM_LAYOUTS` read the assembler's
  `*.gen.json` overlays when present, else the pristine upstream manifests.

These hooks are stable across slices (they don't change as the frontier widens). Like
the divergences below, they assume the assembler has run before `make modern`.

**Test-only baseline divergences — revert/gate before a real build.** Sentinel-fenced
blocks in:
- `src/new_game.c` — new-game spawn redirect (→ Map049) + intro-skip callback
- `src/intro.c` — jump straight into the slice
- `include/new_game.h` — prototype

## Generated output is NOT committed
The rpg2gba pipeline (`scripts/assemble_pathfinder.py`) writes generated maps,
layouts, scripts, and headers **into this tree**. Those are gitignored (see the
repo-root `.gitignore`) and regenerated — **never commit pipeline output as
engine source**. The assembler does **not** edit any tracked upstream file in place;
it writes gitignored overlays — `data/maps/map_groups.gen.json`,
`data/layouts/layouts.gen.json`, `data/maps/uranium_includes.inc`, the
`uranium_*.h` / `CommonEvents.inc` headers, and the per-map dirs — which the committed
include-hooks above pull in. So after an assembly run `git status` stays clean (only
the two committed hook files differ from raw upstream).
