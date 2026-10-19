# I3 + I5: what the engine should be, and how the game gets into it

**Status:** research and options (2026-10-19). Nothing decided. The decisions
go in `reference/intermission_a1_a2.md` §3. All measurements, with method, are
in `reference/findings/rom_ledger_2026-10-19.md`, cited below as "ledger §n".

## 1. The question

The operator asked:
- Should we keep a stripped-down engine, Emerald's engine with Emerald's game
  data (maps, trainers, species, …) commented out but still in the files, and
  have the pipeline write all game content into it?
- Or should we leave the stock engine as it is and have the pipeline take
  pieces of Emerald out as needed?
- And separately: which of our engine additions belong to a reusable
  "rpg2gba engine" for any RPG Maker conversion, such as streaming, and which
  belong to Uranium, such as its Pokémon?

## 2. Short answer

> **Measured 2026-10-19:** the species profile plus stubbed stock layouts took
> the CH08 ROM from 26.55 MiB to **12.15 MiB**. It compiled first time, CH08
> passed 498/498 from boot, and the save layout was unchanged. Details are in
> ledger §4a. The estimates below hold.

1. **The ROM limit (I5) is mostly solved by one switch the expansion already
   has.**
   - 55% of today's ROM (≈ 15.4 MB) is stock species data, and 9.5 MB of
     that is cries.
   - The expansion's `P_FAMILY_*` switches compile a species' data out
     without renumbering anything.
   - Turning off every family Uranium doesn't use recovers **≈ 14 MB**.
   - The free space rises from 5.45 MiB to about 19 MB, against a full-game
     need of ≈ 10–12 MB.
   - (The 2026-10-16 note that "10 MiB is stock music" was wrong. Music is
     ≈ 1.7 MB in total; ledger §1.)
2. **What you described as "comment it out but keep it readable" already
   exists in the engine, in two forms:**
   - **switches**, like `P_FAMILY_*`, which wrap stock data in `#if`;
   - **overlays**, which the pipeline already uses for `map_groups`, `layouts`
     and others: a generated copy of a stock table is built in place of the
     original and the original is left untouched.

   Each form costs one small fenced hook in a stock file, the same pattern as
   the 49 hooks we already have. Neither needs stock *content* edited.
   *(Corrected 2026-10-19: this used to say "neither needs anyone to edit stock
   files". We already have ~104 edited stock files, and a profile adds one more
   hook, in `species_enabled.h`.)*
3. **So I recommend Option B below:** keep the stock engine untouched, and let
   the pipeline write a per-game *profile* that switches off and stubs
   whatever that game doesn't use, alongside the game content it already
   generates.
   - A committed "blank" fork (Option A) costs a lot and buys little. Stock
     ids are positional, and stock C names stock maps and species in over a
     hundred files.
   - The code we'd remove is small (ledger §3).
4. **Your layering idea is right.** The engine splits cleanly into four parts,
   and today they are mixed together only in their *labels*:
   - upstream expansion;
   - an rpg2gba engine layer (streaming and the others), reusable for any
     game;
   - generated game content;
   - the test harness.

   About 1,000 lines of Uranium facts are still hand-typed into C. Each one has
   a data source the pipeline could read (§5).

## 3. The four layers

| Layer | What's in it | Who writes it | Lives in |
|---|---|---|---|
| **0. Upstream** | pokeemerald-expansion as vendored | upstream | `engine/`, tracked, ideally untouched |
| **1. rpg2gba engine** | Mechanisms any RPG Maker conversion needs (list below) | us, by hand, fenced `RPG2GBA …` | `engine/`, tracked |
| **2. Game content and profile** | Everything specific to *this* game: its maps, species, trainers, items, flags, spawn, starter, HM gates, *and* which stock content to switch off | the pipeline, generated per game | gitignored `*.gen.*` files reached through hooks |
| **3. Test harness** | Map walker, embedded save, intro skip | us, by hand | `engine/`, tracked, behind a config switch |

**Layer 1 today** (ledger §6, about 30 files and 2,000 lines). All of it is
generic, even where it is named "Uranium":
- **Map display (the bulk):** the streaming tile cache, the windowed big-map
  grid and 11-bit metatile ids.
- **Events and scripting:**
  - expanded flag/var ranges;
  - the RMXP move-route interpreter (`MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE`);
  - Change Graphic;
  - warp retain-facing.
- **Map seams:** connection remap and split siblings.
- **Pacing knobs.**
- **Three vanilla bug fixes.**

**What's not generic yet in Layer 1:**
- **Names.** About a dozen `Uranium*` identifiers sit on generic mechanisms.
- **Sizes taken from Uranium's census**, written into tracked headers:
  - flag/var region sizes, 384/384/1280/256;
  - trainer capacity, 1189/1280.

  A different game needs different numbers, so these should come from a
  generated header.
- **The intro skip is unconditional.** A shipped ROM could never show a title
  screen.

## 4. The options for stock content

### Option A — a committed "blank" engine

Strip Emerald's content out of the vendored tree once by comment or deletion.
Commit the result, and have the pipeline fill it.

- **For:** the tree reads as "an engine with no game in it". Nothing to stub
  per build.
- **Against:**
  - **Ids are positional.** `SPECIES_*`, `ITEM_*`, `MAP_*`, `TRAINER_*`,
    `MUS_*` and object graphics ids are enums or ordered tables. Removing an
    entry renumbers everything after it, or leaves a hole someone has to fill
    by hand.
  - **Stock C names stock content everywhere.** For example:
    - `SPECIES_*` in 103 `.c` files;
    - `MAP_*` in 55;
    - `TRAINER_*` in 73;
    - all 481 `MUS_*`/`SE_*` ids are used somewhere.

    Each one is a compile error to chase, or a dummy to invent. The expansion's
    own deletion tool, which writes those dummies, calls itself "not fully
    tested and will likely break your game" (ledger §7).
  - **The code is not where the bytes are.** Every Emerald *system*
    (Frontier, link, contests, Pokénav, TV …) totals ≈ 1–1.5 MB, and the big
    ones are wired into ~70 core files (ledger §3). Removing them is the most
    work for the least space.
  - **Upgrades get harder.** Every expansion upgrade lands on the files a
    blank base has rewritten. Our existing check of "what did we change"
    (`git diff 80cdfce2`) would grow from ~100 files to thousands.
  - **No other game benefits.** The next fan game also keeps its own handful
    of canon species, items and moves. Which stock content to keep is
    *per game*, so a single committed blank cut is wrong for the second game.

### Option B — stock engine, plus a generated per-game profile (recommended)

Layer 0 stays as vendored, apart from fenced include hooks: 49 today, plus one
for the species profile. The pipeline computes, from the game's own data,
which stock content the game uses, and writes a profile that drops the rest:

| Stock content | How the profile drops it | ≈ Saved | New work |
|---|---|---|---|
| Species | Generated `P_FAMILY_*` overrides (one switch per family, read from `uranium_id_map.json` plus evolution and form partners). Ids stay stable. | 14 MB | One hook in `species_enabled.h`, plus a generator. Must be built and walked once with Uranium's appended species. |
| Stock map layouts | `_stub_stock_layout_bins`, already written; turn it on in chapter builds | 0.67 MB | Flip a call in `assemble_pathfinder.py` |
| Stock tilesets | Point the stubbed layouts at one stub tileset in the `layouts` overlay | 0.8 MB | Small |
| Stock map scripts and events | An overlay for `event_scripts.s`'s per-map includes, giving label-only stubs. The shared `data/scripts/*.inc` the engine calls stay. | 1.1 MB | One hook, plus a list of labels C reaches |
| Stock music | Repoint unused `song_table.inc` rows to a stub song. Prune samples. | ≤ 1.5 MB | Waits on #22 |
| Emerald systems | Leave them linked and unreachable | — | none |

- **For:**
  - Stock source stays complete and readable.
  - Every saving can be reversed by one regeneration.
  - Each game computes its own keep-list.
  - The patterns are already proven here: the overlays, the layout stub, and
    the fork-index gate that fails loud if generated content names something
    that has been dropped.
- **Against:**
  - Stock source stays in the repo, even though it never reaches the ROM.
  - Dropped species keep their empty `gSpeciesInfo` slot, ≈ 0.4 MB of table
    in total.
  - Stock C that would show a dropped species (Emerald's starter screen,
    Frontier) still compiles but would draw nothing. It is unreachable in
    Uranium.

### Option C — B now, selective compile-outs later

Same as B. If the budget ever needs more, add `RPG2GBA_` switches that compile
out whole Emerald systems, one system at a time, starting with the
lowest-entanglement ones. **No current measurement says we need this.**

## 5. Hand-written Uranium facts that should become generated

Each of these is C we typed by hand, with the source the pipeline could read
(ledger §6):

| Fact | Where now | Generate from | Note |
|---|---|---|---|
| 4 berries + 3 key items | inserted **mid-enum** in `constants/items.h` (every id from TM01 shifts by +4), plus `items.h`, `berry.c`, 14 art files | PBS `items.txt`, berry plants, item art | This is #41 (110 missing items). Generated items should be **appended after stock**, and the mid-enum insertion removed. Changes item ids, so it must land before a keeper save (I6). |
| HM badge gates | `field_move.c` (old code left dead below a `return`) | `Settings.rb` `BADGEFOR*` | Becomes a generated table |
| New-game spawn, heal point, default name | `new_game.c` | map metadata Home | |
| Starter multichoice with literal names | `script_menu.h` | the starter event | A generic "multichoice from generated strings" hook |
| `FLAG_STARTING_OVER` on white-out | `overworld.c` (no stub fallback) | flag registry | Generic "white-out flag" config |
| Flag/var region sizes, trainer capacity | `config/rpg2gba.h`, `opponents.h` | the census the pipeline already runs | Generated sizes; also shrinks the 210 KB empty trainer-slide table (ledger §4) |

There are also three items already in the backlog of the same "engine data the
pipeline should generate" shape: #140 (map-name sections), #31 (the regional
dex) and #35 (Uranium's own moves).

## 6. Suggested order

1. **Measure (cheap, first).**
   - One experiment build with a hand-written `P_FAMILY` profile and stock
     layouts stubbed.
   - Confirm it compiles with Uranium's appended species, read the real
     saving, and run the CH08 suite.
   - This turns the ≈ 14 MB estimate into a number before anything is
     designed around it.
2. **Profile generator.**
   - Generated species profile, plus layout, tileset and script stubbing in
     chapter builds.
   - A per-build ROM-usage line in the build log, so budget is tracked
     chapter by chapter, as the July audit asked.
3. **Hand facts → generators** (§5).
   - Items first, because it renumbers item ids and so belongs before I6's
     keeper save.
   - Then HM gates, spawn, starter menu and sizes.
4. **Relabel Layer 1.**
   - `Uranium*` → `RPG2GBA_*` on the generic mechanisms.
   - Move fences.
   - Put the intro skip behind the harness switch.
   - Correct `RPG2GBA_VENDOR.md`, which says 16 hooks when there are 49.
   - This is mechanical, and best done in one pass after step 3 so names
     settle once.
5. **Music** follows #22's decision, which the corrected budget re-opens.
   Real Uranium audio is no longer ruled out by space.

Steps 1–2 are what I5 needs. Steps 3–4 are what makes the next game cheaper.
None of them blocks CH09, except that step 3's item renumbering should come
before any save you mean to keep.

**Not in scope here.** The Python pipeline also has Uranium-isms, such as
`uranium_id_map.json` and the `URANIUM_*` contract names in generated files.
Making the *pipeline* game-agnostic is its own question.

## 7. Open questions for the operator

1. **Direction:** Option B (stock engine plus generated profile), or do you
   still want a committed blank base (A) for readability?
2. **Canon species art:** for Uranium's 35 canon species, keep the engine's
   stock sprites and cries, or convert Uranium's own? That decides whether
   their families stay enabled for graphics or only for ids.
3. **Emerald systems** (Frontier, contests, link, TV …): leave them linked and
   unreachable, or plan compile-outs anyway for tidiness?
4. **Item renumbering:** OK to move the hand-inserted Uranium items to the end
   of the item list, generated? This changes item ids, so old saves break once
   more.
5. **Ordering:** run step 1's experiment now, as part of this intermission, or
   after CH09 opens?
6. **Release ROM:** should a shipped Uranium ROM show a title screen, and its
   own intro? That decides how the intro skip is gated.
