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

**Rewritten 2026-10-20 (I3 S6).** The custom diff against the vendor import is
109 files, +4907/-396 lines (measured with the command below on that date).
Since I3 (`reference/engine_layers_i3_i5.md`) the edits follow one pattern:
the stock engine stays as vendored, apart from fenced hooks; the pipeline
generates each game's content and facts into gitignored `*.gen.h`/`.inc`/`.json`
files those hooks pull in; generic features any RPG Maker conversion wants are
hand-written engine code; and test-only behaviour sits behind one switch.

### The canonical check: diff against the vendor-import commit

There is no hand-maintained file list here; one rotted into a false claim in
2026-09. The primary view of what's custom vs. pristine is:

```
git diff 80cdfce2 HEAD -- engine/
```

`80cdfce2` is the commit that imported this tree via `git archive` (see
Provenance above). Upstream `21c24202` is **not usable** as the diff base: it is
not a reachable commit object in this repository.

**`80cdfce2` is not a pristine baseline.** The import was taken from a dirty
working tree, so three files arrived already carrying custom edits the diff
cannot see (verified 2026-09-07 by blob hash against upstream; 29,958 of 29,961
files identical):

| File | What is below the baseline |
|---|---|
| `src/intro.c` | skip the copyright screen, intro and title; boot straight into a new game |
| `src/new_game.c` | `CB2_StartRpg2gbaHarness` + the new-game spawn override |
| `include/new_game.h` | its declaration |

All of those lines are fenced (`RPG2GBA HARNESS` / `RPG2GBA GAME PROFILE` since
S6), so a sentinel grep finds them:

> **Fences miss unfenced edits; the diff misses pre-import edits. Neither check
> is complete on its own: run both and take the union.**

### Fence vocabulary

Every custom block is fenced `// BEGIN <sentinel> — why` ... `// END <sentinel>`
(`@` in asm, `#` in make/python); a few one-line edits carry a single
`// <sentinel>: ...` comment instead. Seven sentinels:

| Sentinel | What it marks |
|---|---|
| `RPG2GBA GAME PROFILE` | hooks for generated per-game content and facts (species, items, moves, trainers, maps, tilesets, cries, sprites, sizes, spawn), and switches that compile out stock content the game doesn't use |
| `RPG2GBA ENGINE` | generic engine features any converted game wants (custom move routes, connection remaps, split-map warps, live sprite swap, warp facing, pacing knobs, bag description paging, game-move/ability behaviour) |
| `RPG2GBA EVENT RANGE EXPANSION` | the extra converter-owned flag/var regions |
| `RPG2GBA STREAMING` | 11-bit metatile ids, the streaming tile cache, the windowed big-map grid |
| `RPG2GBA HARNESS` | test-harness boot: skip to a new game, fixed default name |
| `RPG2GBA EMBEDDED SAVE` | a save blob a playtest stamps into the ROM (harness) |
| `RPG2GBA MAP WALKER` | the Map Walker debug ROM mode (harness) |

The `URANIUM PATHFINDER SLICE`, `URANIUM MAP WALKER` and `URANIUM EMBEDDED SAVE`
sentinels were retired in S6; every block was reassigned to one of the above.

### The harness switch

`include/config/rpg2gba_harness.h` holds the two test switches:

- `RPG2GBA_HARNESS` (default `TRUE`): boot straight into a new game (no
  copyright screen, intro, title or main menu), name the player "RED", and load
  an embedded save when one is stamped in. `FALSE` gives the stock boot.
  Spawning at the game's own start map without the moving-truck scene is a game
  fact, not harness: it follows `RPG2GBA_NEW_GAME_MAP` (generated game profile).
- `RPG2GBA_MAP_WALKER` (default `FALSE`): the Map Walker debug ROM; requires
  the harness.

Walk ROMs add three things to the embedded save (`struct Rpg2gbaWalkExtras`,
`reference/walk_qol_plan.md`): a ROM id, so an in-game save made on that ROM
continues on the next boot; species to give on boot; and party-wide EXP Share,
via `FLAG_RPG2GBA_EXP_SHARE` (stock `FLAG_UNUSED_0x020`, wired to
`I_EXP_SHARE_FLAG` in `config/item.h`). The id is kept in SaveBlock2's unused
`filler_90`.

### Orientation (not an inventory) of the feature areas

A map into the diff, not a substitute for it; check the diff before reverting
anything.

- **Generated content hooks** (`RPG2GBA GAME PROFILE`, ~50 blocks): species,
  dex ids, learnsets, cries and sprites; items, berries and icons; moves,
  abilities and the TM/HM list; trainers, parties, pics and rematches; object
  event sprites and palettes; tilesets, metatiles and animations; maps,
  layouts, scripts, wild encounters, heal locations, trades; the species
  family profile; the game profile (HM badge gates, white-out flag, spawn) and
  census sizes (flag/var regions, trainer capacity, bag pockets). Most use
  `__has_include` with a stock fallback, so the tree also builds as stock.
- **Engine features** (`RPG2GBA ENGINE`): the custom-route bytecode movement
  type (`src/event_object_movement.c`), connection id remaps
  (`src/rpg2gba_connection_remap.c`, `src/fieldmap.c`), split-map warps
  (`src/rpg2gba_split_maps.c`), `RPG2GBA_SetObjectEventGfx`, warp arrival
  facing, palette/BGM/text pacing knobs, bag description paging, field-move
  badge gates, battle behaviour for the game's own moves and abilities (with
  tests in `test/battle/rpg2gba/`).
- **Streaming** (`RPG2GBA STREAMING`): `src/field_stream.c`, `src/fieldmap.c`,
  `src/field_camera.c`, `include/global.fieldmap.h`.
- **Harness** (`RPG2GBA HARNESS`, `EMBEDDED SAVE`, `MAP WALKER`): `src/intro.c`,
  `src/new_game.c`, `src/rpg2gba_embedded_save.c`, `src/rpg2gba_map_walker.c`
  and its gated call sites.

## Generated output is NOT committed
The rpg2gba pipeline (`scripts/assemble_pathfinder.py`) writes generated maps,
layouts, scripts, and headers **into this tree**. Those are gitignored (see the
repo-root `.gitignore`) and regenerated — **never commit pipeline output as
engine source**. The assembler does **not** edit any tracked upstream file in place;
it writes gitignored overlays — `data/maps/map_groups.gen.json`,
`data/layouts/layouts.gen.json`, `data/maps/rpg2gba_includes.inc`,
`src/data/heal_locations.gen.json`, the
`rpg2gba_*.h` / `*.gen.h` / `CommonEvents.inc` headers, and the per-map dirs — which the committed
include-hooks described above pull in. So after an assembly run `git status` stays
clean against this repo's committed state (only the tracked hook files, not the
generated overlays they pull in, ever show as changed).
