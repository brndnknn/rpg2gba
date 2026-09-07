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

**CORRECTED 2026-09-07:** this section used to claim the custom diff was three
test-only files ("revert/gate before a real build"). That was false and had
gone stale enough to be actively dangerous — an agent trusting it would delete
or gate working engine features believing them to be disposable test scaffolding.
The real custom diff, as of this correction, is **77 files / +2647 -343 lines**
and includes whole new source files (a 761-line map-walker debug mode, an
embedded-save boot path), new engine mechanics (a movement-type bytecode
interpreter, a live-graphics-swap special), gameplay content (four new berries,
two new key items), pacing/save-layout changes, and roughly 15 generated-content
include-hooks. None of that is test-only, and none of it should be reverted
before "a real build" — it *is* the real build.

### The canonical check: diff against the vendor-import commit

There is no hand-maintained file list here anymore — that list is what rotted
into the false claim above. The primary view of what's custom vs. pristine is:

```
git diff 80cdfce2 HEAD -- engine/
```

`80cdfce2` is the commit that imported this tree via `git archive` (see
Provenance above). Everything after it in this repo's history is a hand-written
custom change (plus incidental doc edits to this file itself).

Upstream `21c24202` (the SHA this tree was forked from) is **not usable** as
the diff base: this tree was imported as a flat `git archive` snapshot with no
upstream history carried over, so `21c24202` is not a reachable commit object
in *this* repository — `git diff 21c24202 HEAD` will simply fail to resolve.

**But `80cdfce2` is NOT a pristine baseline — corrected 2026-09-07.** This
section used to claim the import "was a straight archive, not a rebase or a
patched checkout" and that `80cdfce2` was "the last point at which `engine/` was
byte-identical to upstream. **Both were false.** The import was taken from a
*dirty* working tree, so three files arrived already carrying custom edits and
the diff above is structurally blind to them:

| File | What is below the baseline |
|---|---|
| `src/intro.c` | skip intro / title / menu, boot straight into a new game |
| `src/new_game.c` | `CB2_StartUraniumSlice` + new-game spawn override into Moki Town |
| `include/new_game.h` | its declaration |

33 lines total. Established by comparing blob hashes against upstream
`21c24202` while an external clone of it still existed (deleted 2026-09-07):
**29,958 of 29,961 files were identical**, those three the only content
exceptions. Twelve upstream files are also simply absent — `tools/compresSmol/*`,
which `.gitignore` excludes, plus `tools/mgba/mgba-rom-test.exe`. Benign.

All 33 lines *are* properly `// BEGIN URANIUM PATHFINDER SLICE` / `// END`
fenced, so a sentinel grep does find them. That is the whole point:

> **Fences miss unfenced edits; the diff misses pre-import edits. Neither check
> is complete on its own — run both and take the union.**

Re-run that `git diff` whenever you need to know what's custom — don't trust a
prose summary (including the one below) to still be accurate; verify against
the diff first, then grep the four sentinels for anything below the baseline.

### Orientation (not an inventory) of the major feature areas

This is a map to help you find your way into the diff above, not a substitute
for reading it. Do not use this list to decide what's safe to revert — always
check the diff. Verified against `git diff 80cdfce2 HEAD -- engine/` on
2026-09-07:

- **Uranium Map Walker** — a whole new debug ROM mode for inspecting converted
  maps without playing through them: `src/uranium_map_walker.c` (new, 761
  lines), `include/uranium_map_walker.h` (new), `include/config/uranium_walker.h`
  (new, the `URANIUM_MAP_WALKER` build switch). Gated call sites in
  `src/event_object_movement.c`, `src/field_control_avatar.c`, `src/overworld.c`,
  and a day/night-tint override in `include/config/overworld.h`.
- **Embedded save (dev/review boot-continue)** — `include/uranium_embedded_save.h`
  and `src/uranium_embedded_save.c` (both new): a const blob a playtest harness
  can stamp into a `.gba` so it boots straight into a tested state. Wired into
  the boot path in `src/new_game.c` (`CB2_StartUraniumSlice`).
- **Event-range expansion** — `include/config/rpg2gba.h` (new; the
  `RPG2GBA_EXPAND_EVENT_RANGES` switch and region-size constants), extending
  `constants/flags.h` and `constants/vars.h` with converter-owned flag/var
  regions above the vanilla ranges, cleared per-map-transition in
  `src/event_data.c`, and offset in save-layout terms by flipping
  `FREE_MYSTERY_EVENT_BUFFERS` in `include/config/save.h` (FALSE → TRUE).
- **Movement-type bytecode interpreter** — a new autonomous NPC movement type
  (`MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE`, `constants/event_object_movement.h`)
  backed by a full bytecode FSM in `src/event_object_movement.c` that replays
  per-object RMXP move-route programs.
- **battle_setup rematch/heal fixes** — a earlyrival heal-after/tutorial flag
  bug fix and a battle-script wait fix in `src/battle_setup.c` and
  `data/battle_scripts_1.s`, plus the generated PokePod rematch-table
  include-hooks in `constants/rematches.h` / `src/battle_setup.c`.
- **Palette/sound pacing knobs** — `RPG2GBA_FADE_DELTA_Y`, `RPG2GBA_BGM_TEMPO_SCALE`,
  and `RPG2GBA_FAST_TEXT_DEFAULT` in `include/config/rpg2gba.h`, applied in
  `src/palette.c`, `src/sound.c`, and `src/new_game.c` (`SetDefaultOptions`).
- **Uranium-original berries and key items** — Acai/Bacu/Cupu/Guara berries and
  the Sprinklotad/Bike Wheel key items, spanning `constants/items.h`,
  `src/berry.c`, `src/data/items.h`, `src/data/graphics/*.h`,
  `src/item_menu_icons.c`, and new art under `graphics/berries/` and
  `graphics/items/`.
- **A script-callable live graphics swap** — `RPG2GBA_SetObjectEventGfx`
  (`asm/macros/event.inc`, `data/specials.inc`, `include/event_object_movement.h`,
  `src/event_object_movement.c`), backing RMXP's move-command 41 ("Change
  Graphic") which had no engine-side equivalent.
- **New-game boot redirect** — `src/new_game.c` (spawn redirect + harness code,
  extensively commented in place), `src/intro.c` (`SetUpCopyrightScreen`
  short-circuit, sole boot hook), `include/new_game.h` (prototype). This is the
  one area with real "test-harness" character (e.g. the standing rock-smash
  `FlagSet(FLAG_BADGE03_GET)`), but even here most of the file's diff is
  permanent slice-boot plumbing, not scaffolding to strip.
- **Corpus-sized capacity increases** — `constants/opponents.h`
  (`TRAINERS_COUNT_EMERALD`/`MAX_TRAINERS_COUNT_EMERALD` raised to cover the
  full Uranium trainer corpus) and `constants/flags.h` (relocating
  `TRAINER_REGISTERED_FLAGS_START` to a new `RPG2GBA_TRAINER_REGISTERED_FLAGS_*`
  region) — both save-layout-breaking, both explained in place.
- **Roughly 15 generated-content include-hooks** — the recurring pattern of "the
  assembler writes a gitignored `*.gen.h`/`*.gen.json`/`.inc` file; a committed,
  sentinel-fenced one-or-two-line hook includes it, falling back to an empty
  stub or pristine upstream data when nothing is staged." Present in
  `constants/species.h`, `constants/pokedex.h`, `constants/trainers.h`,
  `constants/opponents.h`, `constants/rematches.h`, `constants/event_objects.h`,
  `constants/cries.h`, `include/tilesets.h`, `src/data/tilesets/{graphics,headers,metatiles}.h`,
  `src/data/object_events/object_event_{graphics,graphics_info,graphics_info_pointers,pic_tables}.h`,
  `src/data/pokemon/species_info.h`, `src/data/graphics/{pokemon,trainers}.h`,
  `src/data/script_menu.h` (custom multichoice, same pattern), `sound/cry_tables.inc`
  (x2) and `sound/direct_sound_data.inc`, `data/event_scripts.s`, `data/map_events.s`,
  `data/trainers.party`, `map_data_rules.mk`, `Makefile` (wild_encounters overlay),
  and `tools/wild_encounters/wild_encounters_to_header.py`.

Every item above is fenced with a sentinel comment naming its feature area
(`URANIUM PATHFINDER SLICE`, `URANIUM MAP WALKER`, `URANIUM EMBEDDED SAVE`, or
`RPG2GBA EVENT RANGE EXPANSION`) — grep the tree for those four strings to find
every fenced block. A handful of single-line edits to existing `#define`s
(e.g. `constants/flags.h`'s `TRAINER_REGISTERED_FLAGS_START`,
`constants/opponents.h`'s trainer-count constants) carry an inline explanatory
comment naming the change instead of a full BEGIN/END bracket, because the
change is a one-line value substitution, not an insertable block — the comment
is still grep-able by the same sentinel vocabulary.

## Generated output is NOT committed
The rpg2gba pipeline (`scripts/assemble_pathfinder.py`) writes generated maps,
layouts, scripts, and headers **into this tree**. Those are gitignored (see the
repo-root `.gitignore`) and regenerated — **never commit pipeline output as
engine source**. The assembler does **not** edit any tracked upstream file in place;
it writes gitignored overlays — `data/maps/map_groups.gen.json`,
`data/layouts/layouts.gen.json`, `data/maps/uranium_includes.inc`, the
`uranium_*.h` / `CommonEvents.inc` headers, and the per-map dirs — which the committed
include-hooks described above pull in. So after an assembly run `git status` stays
clean against this repo's committed state (only the tracked hook files, not the
generated overlays they pull in, ever show as changed).
