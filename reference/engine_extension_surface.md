# Engine Extension Surface

**Scope:** the complete, exhaustive list of ways rpg2gba is allowed to modify the
vendored `engine/` (pokeemerald-expansion, pinned upstream `21c24202` — see
`engine/RPG2GBA_VENDOR.md`). Every divergence from pristine upstream — every line —
must be one of the three mechanisms below, and every mechanism instance must have a
row in this document. If you're about to touch `engine/` and can't point at a row
here (or add one), stop.

This is the spec for a **promotion ladder**, cheapest/most-reusable first:

1. **Gen hooks** — permanent, one-time edits to tracked engine files that
   `#include`/`.include` **gitignored, pipeline-generated** files. All per-game
   content (this slice's or a future game's) flows through the generated files;
   the tracked tree never changes again once the hook exists. This is the
   default choice — prefer it whenever a converter needs to inject a table row,
   a struct, or a script include.
2. **Config-gated divergences** — a behavior change compiled in/out by a build
   flag, following the expansion's own `include/config/*.h` idiom
   (`#define FOO_ENABLED TRUE/FALSE`, gate with `#if`). Use when the change
   alters control flow/semantics rather than adding data, and the two behaviors
   (stock vs. divergent) need to coexist in the tree, selectable at compile
   time.
3. **Sentinel fences** — hand edits of last resort to tracked files, wrapped in
   `// BEGIN URANIUM PATHFINDER SLICE` / `// END ...` (or `URANIUM MAP WALKER`)
   comment pairs. Every fence is individually greppable, individually
   justified (§4 below), and individually dispositioned (KEEP /
   PROMOTE-to-config / REMOVE-when-X). This tier exists because some changes
   (a spawn-point override, a boot-sequence short-circuit) have no generated
   file to hook and aren't yet worth a config flag.

Why this document exists: (a) the next fan-game conversion reuses this surface
instead of re-deriving it from scratch; (b) build-agent sessions read this
instead of re-discovering hook locations by trial and error; (c) the fence
ledger in §4 is a greppable "did every divergence survive?" check — we lost a
fenced edit silently once (the reflection experiment, see the HISTORICAL row).

Cross-reference: `reference/native_reuse_audit_2026-07-07.md` is the verdict
analysis (is each divergence justified, is there a native alternative). This
document does not repeat that reasoning — it's the location/mechanism spec.
All line numbers below are **as of 2026-07-07 (pin 21c24202)** and will drift;
re-verify with the §7 grep before trusting a number for an edit.

---

## 1. Tier 1 — Gen hook inventory

Every row: a tracked engine file + line, what generated file it `#include`s,
which Python emitter writes that generated file, and any positional constraint
the fork's own compilation order imposes.

| Tracked file : line | Includes | Emitter | Positional constraint |
|---|---|---|---|
| `src/data/object_events/object_event_graphics.h:639-641` | `uranium_object_event_graphics.gen.h` | `sprite_emit.py` (`"graphics"`) | Hosts pic **data arrays** (`INCGFX_U16`) + palette DATA arrays; must come before anything referencing them. Same-directory quoted `#include` (see §5). |
| `src/data/object_events/object_event_graphics_info.h:7229-7231` | `uranium_object_event_graphics_info.gen.h` | `sprite_emit.py` (`"graphics_info"`) | Struct defs; must follow `object_event_graphics.h`'s pic tables (uses `sPicTable_*` symbols) and `event_object_movement.c`'s anim-table symbols. |
| `src/data/object_events/object_event_graphics_info_decls.gen.h` hooked at `object_event_graphics_info_pointers.h:404-406` | `uranium_object_event_graphics_info_decls.gen.h` | `sprite_emit.py` (`"graphics_info_decls"`) | Must sit **ABOVE** `gObjectEventGraphicsInfoPointers[]` (line 408) — `event_object_movement.c` includes this pointers file **before** `object_event_graphics_info.h`, so the array needs forward `extern` decls, not the real struct defs, in scope. |
| `object_event_graphics_info_pointers.h:805-807` (inside the array, line 408-808) | `uranium_object_event_graphics_info_pointers.gen.h` | `sprite_emit.py` (`"graphics_info_pointers"`) | Designated-initializer entries (`[OBJ_EVENT_GFX_URANIUM_X] = &...`) INSIDE the array braces, after the `#endif // IS_FRLG` block, before the closing `};`. |
| `src/data/object_events/object_event_pic_tables.h:3033-3035` | `uranium_object_event_pic_tables.gen.h` | `sprite_emit.py` (`"pic_tables"`) | Same-directory quoted include; must precede `object_event_graphics_info.h`'s struct defs (they reference `sPicTable_*`). |
| `include/constants/event_objects.h:426-432` | `constants/uranium_event_objects.gen.h` | `sprite_emit.py` (`"constants"`) | Defines `OBJ_EVENT_GFX_URANIUM_*` / `OBJ_EVENT_PAL_TAG_URANIUM_*` (ids from 388 up) + `NUM_URANIUM_OBJ_EVENT_GFX`; line 431 extends `NUM_OBJ_EVENT_GFX` to `(388 + NUM_URANIUM_OBJ_EVENT_GFX)` — must be included before that `#define`. |
| `src/event_object_movement.c:580-583` | `data/object_events/uranium_object_event_palettes.gen.h` | `sprite_emit.py` (`"palettes"`) | INSIDE `sObjectEventSpritePalettes[]`, must sit **BEFORE** the `OBJ_EVENT_PAL_TAG_NONE` terminator at line 585 (table is terminator-scanned; see §5). |
| `src/data/tilesets/headers.h:1545-1549` | `uranium_tilesets.gen.h` | tileset `graphics/emit.py` / `build_slice_tilesets.py` | Comment notes: "Placed after graphics.h + metatiles.h in tilesets.c, so the symbols it references exist." |
| `src/data/tilesets/graphics.h:3052-3055` | `uranium_graphics.gen.h` | tileset emitter | Tile/palette data arrays; must precede `headers.h`'s struct defs. |
| `src/data/tilesets/metatiles.h:412-415` | `uranium_metatiles.gen.h` | tileset emitter | Metatile/attribute binaries; must precede `headers.h`'s struct defs. |
| `include/tilesets.h:64-67` | `uranium_externs.gen.h` | tileset emitter | `extern const struct Tileset gTileset_Uranium*;` decls, inside the header guard, before `#endif`. |
| `data/event_scripts.s:1739-1746` | `data/scripts/uranium_map_aliases.h`, `data/scripts/uranium_flags.h` (`#include`), `data/maps/uranium_includes.inc` (`.include`) | `assemble_pathfinder.py` (flag registry dump + map-alias + per-slice script-include list) | End of the std-scripts include chain; requires the assembler to have run first (generated files are gitignored). |
| `map_data_rules.mk:7-15` | `data/maps/map_groups.gen.json`, `data/layouts/layouts.gen.json` (wildcard-preferred) | `assemble_pathfinder.py` (S8a) | `$(wildcard ...)` resolves at `make` parse time; falls back to pristine upstream `map_groups.json`/`layouts.json` when no `.gen.json` is staged. Keeps the upstream JSON files byte-for-byte untouched. |

**Sub-hook inside the pointers file — repoint, not a gen include (see Tier 3 C2):**
`object_event_graphics_info_pointers.h:409-419` repoints
`OBJ_EVENT_GFX_BRENDAN_NORMAL`/`OBJ_EVENT_GFX_BRENDAN_FIELD_MOVE` at
`gObjectEventGraphicsInfo_UraniumPlayerNormal`/`...UraniumPlayerFieldMove`. This
is a **fence**, not a hook — it edits an existing designated-initializer line in
place rather than including a new file (`-Woverride-init`/`-Werror` forbids a
second entry for the same index; see §5).

### The stub system

A fresh clone (or any build with zero sprites staged) must compile with **zero
content**. `sprite_emit.write_stub_gen_files` (`src/rpg2gba/tileset_converter/graphics/sprite_emit.py:711-751`,
`_GEN_RELPATHS` dict at :186-198) writes all 7 `.gen.h` fragments in empty form:
`NUM_URANIUM_OBJ_EVENT_GFX 0`, empty bodies for graphics/pic_tables/graphics_info/
palettes/pointers.

The `graphics_info_decls` stub is special: because the two **tracked** pointer
repoints in `object_event_graphics_info_pointers.h:411,418` reference
`gObjectEventGraphicsInfo_UraniumPlayerNormal` / `...UraniumPlayerFieldMove`
**unconditionally** (they're fenced hand edits, not gen-hook content — they exist
whether or not a player sprite was staged), the stub decls file `#define`s those
two symbols back to the vanilla structs so the unconditional reference still
resolves:

```c
#define gObjectEventGraphicsInfo_UraniumPlayerNormal    gObjectEventGraphicsInfo_BrendanNormal
#define gObjectEventGraphicsInfo_UraniumPlayerFieldMove gObjectEventGraphicsInfo_BrendanFieldMove
```

The real (non-stub) decls renderer (`_render_graphics_info_decls`) never emits
these `#define`s — it emits true `extern` declarations of the real structs
instead, once a player is actually staged.

---

## 2. Tier 2 — Config-gated divergences

### `URANIUM_MAP_WALKER` (`include/config/uranium_walker.h`, default `FALSE`)

A single build flag that gates a self-contained debug ROM mode — a cursor-based
map inspector, not normal gameplay. When `TRUE`, gates (all `#if URANIUM_MAP_WALKER == TRUE`):

- **NPC/script suppression:**
  - `src/event_object_movement.c:2898-2904` — `TrySpawnObjectEvents` returns
    early when the walker is active (also gates the in-view scroll-spawn path,
    not just initial spawn).
  - `src/field_control_avatar.c:214-222` — the walker owns A/B/R/L/START
    (`Task_UraniumWalker`); every field button handler (interaction, door-warp,
    start menu, select, dexnav, debug) short-circuits to `FALSE` (no script
    consumed, cursor movement still proceeds).
  - `src/field_control_avatar.c:695-700` — `TryStartStepBasedScript` returns
    `FALSE` (suppresses coord/warp/misc step-based scripts).
  - `src/overworld.c:2590-2597` — inverted gate (`#if URANIUM_MAP_WALKER != TRUE`):
    `TrySpawnObjectEvents`, `FollowerNPC_HandleSprite`, `UpdateFollowingPokemon`,
    `TryRunOnWarpIntoMapScript` only run when the walker is OFF.
- **Bounds-clamp collision:** `src/event_object_movement.c:6526-6538` — free
  movement within map bounds; walking past `gMapHeader.mapLayout->width/height`
  returns `COLLISION_IMPASSABLE` instead of reading garbage.
- **`OW_ENABLE_DNS` force-off:** `include/config/overworld.h:102-111` — raw
  display (no day/night tint) under the walker flag; normal slice builds keep
  vanilla `OW_ENABLE_DNS TRUE`.
- **The whole `src/uranium_map_walker.c` feature set** (entirely wrapped
  `#if URANIUM_MAP_WALKER == TRUE` at :10 through :760): ListMenu-based START
  jump-menu (scrollable list of every map), R-button warp-tile overlay,
  invisible-anchor boot, L-toggle coord/metatile HUD, warp-follow + back-stack.
  Declared in `include/uranium_map_walker.h` (also `#include`s
  `config/uranium_walker.h` and self-guards `#if URANIUM_MAP_WALKER == TRUE`
  around its own prototypes).
- Arming site: `src/new_game.c:265-275` (`CB2_StartUraniumSlice`, flips
  `sWalkerActive` via `UraniumWalker_Begin()` before the map load) and
  `src/overworld.c:1902-1909` (`gFieldCallback = UraniumWalker_FieldCB_MapLoad`
  instead of the truck-suppression fallback — same "callback consumed
  synchronously inside `DoMapLoadLoop`" timing constraint documented in §5).

### Planned — `RPG2GBA` flag/var space expansion

**Not yet implemented; pending user decision.** Fixes audit finding F1
(`reference/native_reuse_audit_2026-07-07.md` §F1): the current registry bases
(`FLAG_BASE = 0x1000`, `SELFSWITCH_BASE = 0x1100` in
`scripts/assemble_pathfinder.py:64-68`) are **out-of-bounds writes** into
`vars[]` — `GetFlagPointer` (`engine/src/event_data.c:226`) does not bounds-check
against `FLAGS_COUNT`. The proper fix is a sentinel-fenced (then config-gated)
expansion of `FLAGS_COUNT`/`VARS_COUNT` (`include/global.h:146,1132`) with named
`RPG2GBA_*_START` range constants placed above the vanilla ranges, plus a
save-block-size / sector-budget re-check. This is the **first generic
(non-Uranium) surface entry** — every converted game needs more flag/var space
than vanilla ships, so this generalizes past the current slice.

---

## 3. Tier 3 — Sentinel fence ledger

One row per fence. **Disposition** is KEEP (permanent, justified, no better
mechanism available), PROMOTE-to-config (works today, should become a Tier-2
flag), or REMOVE-when-X (tracked debt with an explicit trigger).

| Location | What it changes | Why | Disposition |
|---|---|---|---|
| `src/new_game.c:141-150` (`WarpToTruck`) | Redirects new-game spawn to Map049 Player's House 1F @ (7,7) instead of the vanilla truck interior | Slice needs to be reachable on boot without the vanilla intro sequence | KEEP, candidate for config promotion |
| `src/new_game.c:245-286` (`CB2_StartUraniumSlice`) | Stamps a default identity, skips Rayquaza intro/title/Birch, calls stock `CB2_NewGame()`, arms the walker (`UraniumWalker_Begin()`) before map load | Sole boot-gate entry point; must live here because `CB2_NewGame`'s `DoMapLoadLoop()` consumes `gFieldCallback` synchronously (arming after `CB2_NewGame()` returns is a no-op — documented in-line) | KEEP |
| `src/new_game.c:277-284` (TEST HARNESS inside `CB2_StartUraniumSlice`) | `FlagSet(FLAG_BADGE03_GET)` + gives a Geodude knowing Rock Smash, unconditionally, on every boot | Makes rock smash testable from a fresh boot without real progression; must run AFTER `CB2_NewGame()` since `NewGameInitData()` zeroes the party inside it | **REMOVE** when real progression grants badge03 + a rock-smash-capable party mon through normal play — tracked obligation, not permanent |
| `src/intro.c:1051-1064` (`SetUpCopyrightScreen`) | Short-circuits: force-blanks display, jumps straight to `CB2_StartUraniumSlice`, returns 0 before the vanilla copyright/intro/multiboot logic runs | Sole slice-boot hook; no `SKIP_TITLESCREEN`-style config exists in this fork (verified — only unrelated `B_FAST_INTRO_*`) | KEEP, candidate for config promotion |
| `src/overworld.c:1893-1910` (inside `CB2_NewGame`) | Suppresses `ExecuteTruckSequence` (truck metatile rewrite, camera shake, locked controls); arms `FieldCB_WarpExitFadeFromBlack` instead (or `UraniumWalker_FieldCB_MapLoad` when the walker is active) | The slice spawns into a normal map, not `InsideOfTruck`; must be swapped here specifically because the truck sequence runs synchronously inside `DoMapLoadLoop()` — this is the only point in the call chain where swapping the callback still works | KEEP (truck-suppression half) / walker-arm half already config-gated under `URANIUM_MAP_WALKER` |
| `src/data/object_events/object_event_graphics_info_pointers.h:409-412` | `[OBJ_EVENT_GFX_BRENDAN_NORMAL] = &gObjectEventGraphicsInfo_UraniumPlayerNormal` (repoints the vanilla Brendan-normal pointer entry) | Player walk/run art: swaps in the converted Uranium hero sheet in place of Brendan without touching `NUM_OBJ_EVENT_GFX`/adding a new id — vanilla struct falls back via the stub `#define` when unstaged | KEEP |
| `src/data/object_events/object_event_graphics_info_pointers.h:415-419` | `[OBJ_EVENT_GFX_BRENDAN_FIELD_MOVE] = &gObjectEventGraphicsInfo_UraniumPlayerFieldMove` (repoints the vanilla Brendan-field-move pointer entry) | Rock-smash pose; needs a 1-tick terminating anim (Uranium has no field-move pose — a looping anim here would softlock the held movement) | KEEP |

**HISTORICAL (do not re-apply):** a narrow-scan edit to
`ObjectEventGetNearbyReflectionType` in `src/event_object_movement.c` was applied
2026-07-06, rejected by the user 2026-07-07, and **reverted to pristine
upstream** — confirmed by grep: no `URANIUM` marker exists anywhere near that
function or its reflection tables today. Any future reflection work (water/ice
tile reflections for converted maps) needs a **different approach** than the one
tried; don't re-derive the same narrow-scan patch.

---

## 4. Build gotchas

Hard-won invariants. Keep each entry short; add new ones here when a boot gate
surfaces something not already listed.

- **Same-directory quoted includes.** Hooks inside `src/data/object_events/*.h`
  need `#include "uranium_....gen.h"` (quoted, same directory) — GCC resolves
  quoted includes relative to the includING file's directory, not the compile
  root.
- **Decls-above-array ordering.** `object_event_graphics_info_pointers.h`'s
  decls hook must sit ABOVE the array (`event_object_movement.c` includes this
  pointers file BEFORE `object_event_graphics_info.h`, so only forward decls are
  in scope at that point).
- **Entries-inside-braces.** The pointers hook and the palettes hook both live
  INSIDE their respective array's `{ ... }` braces, not after them.
- **Terminator-scanned palette table.** The palette entries hook must sit
  BEFORE the `OBJ_EVENT_PAL_TAG_NONE` terminator in `sObjectEventSpritePalettes[]`
  — the table is scanned until it hits that sentinel.
- **`-Woverride-init` + `-Werror` in CFLAGS.** A duplicate designated
  initializer for the same array index is a **build error**, not a warning.
  Repoint an existing entry by fencing/editing the tracked line in place
  (Tier 3), never by having a gen hook emit a second `[SAME_INDEX] = ...`.
- **GBA linker discards nonzero file-scope `.data` statics.** Make lookup
  structs `const`; zero-init any mutable file-scope statics.
- **Generated headers must exist before `make`.** Always run the assembler
  (which writes the `.gen.h`/`.gen.json` files) first. Fresh clones rely on
  `write_stub_gen_files` for a zero-content compile.
- **`gFieldCallback` is consumed synchronously by `DoMapLoadLoop`.** Arming it
  after `CB2_NewGame()` returns is a no-op — the load loop has already consumed
  it. Arm it INSIDE `CB2_NewGame` (see `src/overworld.c:1893-1910`), not from
  the caller.
- **Shared mutable staging + engine gen-state across build flavors.** Slice and
  walker builds share `staging/layouts/layouts.json`, which ACCUMULATES across
  runs; stale entries produce undefined `gTileset_Uranium10xx` link errors.
  Clean both staging and engine gen-state when switching build flavors.
- **Flag ids below `0x4000` are NOT bounds-checked.** `GetFlagPointer`
  (`src/event_data.c:226`) only guards against `SPECIAL_FLAGS_START` (0x4000);
  ids past `FLAGS_COUNT` silently write into `vars[]` (audit F1). Never assign
  a new flag/var id without checking the actual allocation bound (`FLAGS_COUNT`/
  `VARS_COUNT` in `include/global.h`) AND checking for named-constant collisions
  in `include/constants/vars.h` — "past `FLAGS_COUNT`" is not automatically
  "free," it can be out-of-bounds.

---

## 5. How to add a new divergence

1. **Try Tier 1 first.** Can this be a generated-file `#include` behind a
   one-time hook? If the tracked file doesn't already have a hook where you
   need one, adding the hook is itself a Tier-1 (or, if it changes behavior
   rather than adding data, Tier-2) change — add it deliberately, not as a
   side effect of an unrelated task.
2. **Tier 2 if it's a behavior switch.** Two coexisting behaviors selectable at
   compile time → a new `#define FOO TRUE/FALSE` in `include/config/*.h`,
   gated with `#if`, following the fork's own idiom (see `uranium_walker.h` as
   the template).
3. **Tier 3 only as last resort**, and only with:
   - A `// BEGIN URANIUM PATHFINDER SLICE` / `// END ...` (or `URANIUM MAP
     WALKER`) fence, so it's greppable.
   - A row added to §4 of this document with a disposition.
   - A concrete removal/promotion trigger if the disposition isn't KEEP.
4. **Every addition gets a row in this document.** No exceptions — an
   undocumented divergence is how a fenced edit gets silently lost (see the
   HISTORICAL reflection row).
5. **Prefer conversion-time validation over runtime checks.** If the change
   introduces a new symbol/constant the pipeline emits, gate it through the
   fork-capability index (CLAUDE.md §4.7) so an invented symbol fails loud at
   conversion time, not at `make` time or (worse) silently at runtime.
6. **New invariants discovered at a boot gate go in §4**, immediately, before
   moving on — that's exactly how the existing gotcha list was built.

---

## 6. Verification one-liners

List every fence (should match every `URANIUM` row in §1/§3 above):

```
git -C engine grep -n URANIUM -- 'src/*' 'include/*' 'data/*' '*.mk'
```

Clean build after the assembler has run (real content staged):

```
make -C engine -j$(nproc) modern
```

Stub-only build check (simulates a fresh clone / zero content staged —
`write_stub_gen_files` must be called first, then the same build must succeed):

```
python -c "from pathlib import Path; from rpg2gba.tileset_converter.graphics.sprite_emit import write_stub_gen_files; write_stub_gen_files(Path('engine'))"
make -C engine -j$(nproc) modern
```
