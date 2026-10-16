# Intermission: between Act 1 and Act 2

**Status:** collecting (opened 2026-10-16). Act 1 (CH01–CH08) is built and
merged; Act 2 (CH09 onward) does not open until this list is worked through.

**Purpose.** A place for the operator's non-chapter concerns that were held back
while the chapter loop was running. First we record them. Then we decide which
to tackle now and which go to the longer backlog (`PROJECT_TODO.md`). After that,
existing backlog items that could move forward are triaged here too.

**Process.** Items are recorded as the operator gives them, without follow-up
questions. Discussion, sizing and the now/later call come after the list is
complete.

---

## 1. Operator items

### I1. The party is too weak for walk ROMs

**What the operator sees.** At the end of CH08 the party is still one Pokémon,
because the generated suites never catch or add any. A §9 walk therefore means
fighting every trainer with that one Pokémon. That takes time, usually needs
healing between battles, and sometimes ends in a loss and a reboot. This is
why the operator asked for a `CH08-complete` ROM: to walk the chapter's maps
without fighting.

**What the operator wants.** A party that makes walks fast. Options raised:
- catch Pokémon along the way, or
- add Pokémon to the team directly, and
- possibly inflate levels,

so that a walk doesn't stall on healing, Pokémon Center trips, or lost battles.

**Status:** researched 2026-10-16 (below); not yet discussed.

#### Research (2026-10-16)

**Why the party stays weak.** The suite never fights honestly. Its battle
driver (`playtest/battle.py:193-340`, `win_battle`/`zero_enemy_hp`) writes the
enemy's HP to 0 in RAM and lets the real faint path end the battle. So:
- the player never takes damage in a suite run;
- the starter gets only the experience those instant wins pay;
- the only other party members are scripted gifts the chapters walk (the Luxi
  gift; CH03's Magikarp check).

Nothing boosts levels. The starter is given at level 5
(`MokiTownProfessorLab/scripts.inc:2414`), so a walk ROM inherits a party that
was fine for the harness and useless for a human.

**Usable today, with no code change: the engine's debug menu.**
pokeemerald-expansion's overworld debug menu is on in non-release builds
(`include/config/debug.h:5`, `DISABLED_ON_RELEASE`). Our builds aren't release
builds, and `Debug_ShowMainMenu` is linked into the current ROM. **Hold R and
press START in the overworld.** It offers:
- "Heal party" (`debug.c:616`);
- "Pokémon (Basic)" / "(Complex)": pick a species and level, and optionally
  moves, IVs and nature (`debug.c:2819`, `:2861`, `:3018`).

Not yet checked: whether the species list reaches the 38 staged Uranium species
(they are appended after the expansion's roster), and whether any of our
input hooks swallow R+START outside the map-walker build.

**Options for a real fix:**

| Option | How | Notes |
|---|---|---|
| **a. Debug menu by hand** | The operator gives and heals as they go. | Works now. Manual every walk. |
| **b. Walk party stamped into walk ROMs** | Before stamping, the harness runs the engine's own give-Pokémon routine, or writes the party into RAM, then syncs it into the save. A per-act party spec (species + level) would be a small reference file. | A RAM *writer* doesn't exist yet: the readers decode the encrypted Pokémon format but nothing encodes it. Running `ScriptGiveMon`/`givemon` through the engine avoids writing that encoder, but needs a hook to run a script from the harness. There's precedent: a removed boot-party rig in `new_game.c` (re-arm recipe in `ROM_TEST_DEV.md`). |
| **c. Catch along the way** | The suite catches wild Pokémon (the encounter tables are converted) and keeps them. | The most "real" option. It needs a capture driver, and catches would change the suite's own state, which every later chapter replays. The heaviest of the three. |
| **d. Make battles easier instead** | Experience and level-cap configs (`config/battle.h`, `caps.h`). No level scaling exists. | Doesn't fix a level-5 starter, and changes engine balance (baseline behaviour, so the operator would need to approve it). |

**Which species are available.** 38 Uranium species are staged
(`species_converter/common.py:64-158`), plus every vanilla species. Several
of CH01–CH08's wild Pokémon are *not* staged (Comite, Cocaran, Cassnail,
Brailip, Tubjaw). How their encounter slots are emitted wasn't traced.

**Relationship to I6.** If I6's option A or B lands, the operator's own party
replaces the stamped one, and (b) becomes the fallback for walks that start
from a fresh suite state.

### I2. Graphics cleanup

Two defects the operator saw during the CH08 walk and chose not to fix inside
the chapter.

**I2a. Static tiles glitch over animated tiles.** Where a static tile sits on
top of an animated one, the static tile glitches at one point in the animation
cycle. Most visible on Route 1 near the animated water: trees and rocks that
overhang the water glitch.

**I2b. Large boulders use the wrong palette.** The large boulders don't share
the palette of the surrounding rocky terrain, so they look out of place.

**Status:** researched 2026-10-16 (below); not yet discussed.

#### Research (2026-10-16)

**I2a: root cause found, and it's a bug in the near-duplicate tile merge, not
in animation.** Confirmed in the code.

- **The animation itself is consistent.** A cell with animated water under a
  tree or rock composites the overlay into every frame (`build_slice_tilesets.py:317-333`).
  None of these is the cause:
  - frame counts are the least common multiple of the source animations
    (Route 1 has 4, 5, 19 and 95; no guard hits);
  - the cycle wraps correctly;
  - every frame keeps one palette;
  - animated tile slots are never shared with static tiles.
- **The bug: `MergeTable.apply_metatile` (`tile_merge.py:237-252`).** When the
  merge swaps a *static* 8×8 quarter for its near-duplicate representative,
  it writes the new art into frame 0 only, then returns the metatile with its
  original animation frames unchanged (`:252` passes `mt.frames` through).
  - In a column that has animation anywhere (e.g. water elsewhere in the same
    metatile), that static quarter now has frame 0 = merged art and frames
    1…n = original art.
  - The "is this really static?" check (`emit._effective_frames`) sees the
    frames differ, so it emits the quarter as a spurious animated tile.
  - **On screen:** once per cycle, and at map load, the tree or rock quarter
    flips to slightly different art and back.
- **Measured on Route 1 (tileset `uranium1033`):** 29 such tiles. 28 are in
  the 19-frame water animation and 1 is in the 4-frame one. Their pixel change
  at the 0→1 and 18→0 frame transitions is ~10× that of every other step.
  - The source pond animation changes smoothly, so the jump is ours.
  - They also waste ROM (28 tiles × 19 frames) and per-frame DMA.
- **Not yet done:**
  - Booting the ROM to match these tiles to the exact spots the operator saw.
  - A count of other tilesets. Any tileset with an animated column and a
    merged static quarter has the same bug.
- **Fix (small):**
  - In `apply_metatile`, write the replacement quarter into every frame, so a
    static quarter stays static.
  - Add a fail-loud check in emit for the signature "frame 0 differs, frames
    1…n identical".
  - Add a test in `tests/test_tile_merge.py` for a metatile with frames plus a
    merged static quarter. No such test exists.

**I2b: probably the sprite palette packing. Moderate confidence; it needs the
operator to confirm which boulder.**
- **The rocks and boulders are sprites (object events), not map tiles.** They
  are converted Uranium sheets:
  - the Rock Smash rock is `fk107-rocksmash` → `OBJ_EVENT_GFX_URANIUM_FK107_ROCKSMASH`;
  - the Strength boulder is `HGSS_267` → `OBJ_EVENT_GFX_URANIUM_HGSS_267`
    (`reference/npc_gfx_map.json:72-76`, `:287-291`).
- **Sprite colours are shared across all NPCs.** `sprite_emit.py` packs *all*
  NPC and prop sheets into at most 4 shared 15-colour sprite palettes
  (`MAX_PALETTES = 4`; the banks hold 17/35/26/11 sheets). Both boulder sheets
  share bank 1 with dozens of others.
- **Measured on the Rock Smash rock:** its tan-grey source colours come out
  olive and brighter (e.g. (80,72,56) → (66,82,49)).
- **Why they can't match the ground.** Sprite palettes and map palettes are
  separate hardware banks, quantized independently. Nothing ties a rock
  sprite's colours to the rocky ground it sits on.
- **Fix options:**
  - give rock and boulder props their own sprite palette, as the player
    sprite has;
  - reserve a prop-only shared bank;
  - snap prop colours to the map's rock palette at emit time.

  The constraint is the sprite palette budget: 4 shared banks plus the player.
- **Open:** whether the operator means the Rock Smash rocks (Route 1, Moki,
  Route 2), the Strength boulders (Kevlar), or a large boulder drawn as map
  tiles, which isn't ruled out.

**Correction (operator, 2026-10-16): I2b is the large boulders drawn into the
map as tiles**, not the Rock Smash or Strength sprites. The sprite-palette
finding above is real but is not this defect. Re-investigation of the tile-art
boulders follows.

**I2b, tile-art boulders: root cause found. High confidence; confirmed by eye.**
A source-vs-ROM render of Route 2 shows pink and salmon wedges and red
streaks on the big boulders' shaded lower edges, where the source is an even
brown (`output/scratch/boulder_crop_35_13_12.png`, a scratch artefact).
- **Which art.** RMXP tileset 22 (`PU-Route01-02-Moki-Kevlar`) has 2×2 boulders
  (tile ids 667/668/675/676 and a second shape 665/666/673/674). Maps 31, 32,
  33 and 35 all use that tileset. Route 2 has ~25 of these boulders; Route 1
  has none (its rock is cliff plateau).
- **Mechanism: palette families decided by one colour per 8×8 piece.**
  1. The production packer (`quantize.build_quantized_tileset_family`,
     `quantize.py:578-626`) sorts every 8×8 piece into a hue family.
  2. It decides by the piece's single most frequent colour
     (`_dominant_family`, `quantize.py:444-482`).
  3. Hue below 15° counts as "red" and 15–45° as "brown".
  4. The boulder's dark shaded quarters fall just under the 15° cut. 5 of the
     16 pieces of one boulder were classed "red" and packed into a palette of
     rail oranges and pinks (pal 9, no tan ramp).
  5. The colours are then snapped to the nearest entry in that palette, so the
     tans turn pink. Even the "brown" pieces were split across two palettes
     (0 and 6), so one boulder ended up on three palettes.
  6. Nothing keeps the pieces of one multi-tile object together.
- **Measured.**
  - Ground: mean error 0.2–3 per piece.
  - Boulder: 5–13 per piece.
  - Example remap: (192,144,104) → (200,128,128).
  - 895 of the boulder's 1024 pixels sit within a small distance of palette 0
    (the ground's tan ramp), so keeping it on palette 0 would be nearly
    lossless.
- **Likely corpus-wide.** Any shaded brown or red-brown object near the 15°
  cut is at risk: rocks, cliffs, trunks, roofs, cave walls. Only tileset 22 has
  been measured.
- **Fixes, cheapest first, all in `quantize.py`:**
  1. Tune the family cuts (`FamilyParams`, `quantize.py:435-442`): widen
     "brown" down to ~5°, or make the red cut depend on saturation and
     brightness.
  2. Classify a piece by *all* its colours, not just the most frequent one.
  3. Before packing, put a piece in an existing palette from another family
     when that palette already covers its colours within a small error.
  4. Keep the pieces of one multi-tile object in the same family. This is the
     real coherence fix and needs new plumbing.

  Any of these changes every map's palettes. Each needs a by-eye check over
  the built maps (trunks, rails, roofs) before it lands.

### I3. Generate the game-specific engine code instead of hand-writing it

**What the operator sees.** Getting this game working has taken many hand
edits to the engine's C code. The pipeline also only *adds* to Emerald: maps,
Pokémon tables and so on are appended, and nothing is removed. So the ROM
still ships with all of Emerald's graphics, maps and Pokémon, including ones
Uranium never uses.

**Why it matters.** The long-term goal is to convert other fan games with this
tool. After Uranium, converting the next game should be much less work, without
redoing this kind of hand work.

**What the operator wants to explore:**
- Pull the Uranium-specific parts out of the engine.
- Have the pipeline read the RPG Maker data and *generate* whatever C code each
  feature needs.
- Stop shipping Emerald content the converted game doesn't use.

The operator expects this to need a longer conversation. It is a big change
from how the project has been working, which is why it is being raised
between acts.

**Status:** researched 2026-10-16 (below); not yet discussed.

#### Research (2026-10-16)

**Short answer: most of the engine is already generated. The hand-written
Uranium C is a short list, and stripping stock content has real levers. Some
already exist, and one is already on.**

**What the engine edits are today.** 96 engine files changed since the vendor
import (`git diff --stat 80cdfce2 HEAD -- engine/`, +3402/−373), plus the three
files edited before import. Sorted by kind:

| Kind | What | Examples |
|---|---|---|
| **Already generated** (include hooks) | ~30 sites `#include` a pipeline-written, gitignored `*.gen.h`. Each has a generator module behind it. | species, cries, learnsets, dex numbers, trainers, parties, rematches, trades, tilesets, metatiles, anims, object-event graphics, move routes, wild encounters, heal locations, map groups/layouts, flag constants |
| **Generic fan-game features** | C any RPG Maker conversion wants, not tied to Uranium content | expanded flag/var ranges (`config/rpg2gba.h`); the RMXP move-route interpreter (`MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE`); Change Graphic; warp retain-facing; split-map sibling and connection-remap mechanisms; pacing knobs (text speed, fades, BGM tempo) |
| **Hand-written Uranium facts** | Data typed into C by hand. **Every one has a source the pipeline could read.** | HM gates by badge count (`field_move.c:11-100` ← `Settings.rb` `BADGEFOR*`); new-game spawn (`new_game.c:179-226` ← metadata Home); 4 berries + 2 key items + Maria's Key typed into `items.h`/`berry.c` (← PBS items; this is #41's "106 items never reach the engine"); trainer-count capacity (← trainer PBS); the early-rival heal fix (`battle_setup.c:1328`, a named trainer) |
| **Test harness** | Exists for the playtests, not the game | intro skip, the map walker (761 lines), the embedded save |

So I3 is not "pull Uranium out of a hand-written engine". It is three smaller
jobs:
1. **Turn the 5 hand-written fact groups into generators.** Items (#41) is the
   big one. HM gates and the spawn point are small.
2. **Rename and fence the generic features as `RPG2GBA`, not `URANIUM`.** They
   are the reusable engine for the next game. Today they are labelled as
   Uranium work, and some are sized by Uranium's census (flag/var counts),
   which a generator could size per game.
3. **Strip stock content** (below). This is the part I5 makes mandatory.

**Stripping stock content: the levers.**

| Content | ROM today | Lever | Entanglement |
|---|---|---|---|
| Species (~1500, Uranium uses ~200) | 5.88 MiB | **Built in:** `include/config/species_enabled.h` has a `P_FAMILY_<NAME>` switch per family. Setting one FALSE drops its info, graphics, learnsets, cries and follower sprites. `SPECIES_*` ids stay defined, so nothing renumbers. rpg2gba sets none today. | Low: the engine's own feature, designed for this. Caveats: the file warns that changing the latest generation changes the save block (dex flags), and whether it builds cleanly with Uranium's appended species is unverified. A generator would write the switches from the species Uranium actually uses. |
| Music and sound | 10.05 MiB | `sound/song_table.inc` is positional. Pointing an unused song's row at a dummy keeps every `MUS_*` id stable, with no C changes. | Medium: 46 `src/` files and every stock map header name `MUS_*`. Shared instrument samples only shrink if no kept song uses them (unverified). Depends on #22's audio decision. |
| Stock map layouts | (≈1.1 MiB, already saved) | **Already on:** `phase5._stub_stock_layout_bins` (default `drop_stock_map_data=True`) points every stock layout at a 2-byte stub, so all constants stay valid. | None. Done. |
| Stock map scripts, events, tilesets | part of `maps.o` / `tilesets.o` / scripts | Same repoint-don't-delete idea: stub the scripts and tilesets of maps that are never loaded. | High if deleted: 18 `src/` files and 12 script files name stock maps. The 2026-07-01 critique already ruled "repoint, don't delete" so the vendored engine stays diffable. The 2026-07-14 audit estimated 2–4 MiB recoverable here. |

**Prior record.** `reference/findings/corpus_scaling_audit_2026-07-14.md:133-159`
had already concluded the full corpus "fits only with vanilla stripping": a
full-corpus add of ~8.5–11 MiB against 7.08 MiB of headroom at the time. I5's
fresher numbers agree. This is a known conclusion that never got scheduled.

### I4. Stream the world instead of splitting maps

**What the operator sees.** Large maps are currently split into pieces to fit
the engine's tileset and palette limits; map 40 is the example. Related to I3,
graphics could perhaps be handled differently.

**The question.** Could the engine keep in memory only what is on screen and
the area just around it, with tiles and palettes swapped in and out of RAM as
the player moves? That is how open-world games such as GTA or Breath of the
Wild stream a huge world without loading all of it. Is this possible at all on
GBA hardware, knowing it would be a much bigger engine change?

**Status:** researched 2026-10-16 (below); not yet discussed.

#### Research (2026-10-16)

**Short answer: yes, the hardware can do it.** Streaming tile *graphics* is a
known GBA technique. The engine already streams half of the picture. What
forces the splits is the other half, plus a data format limit that is the
engine's own and not the hardware's.

**What the engine already streams.** The on-screen tilemap is a 32×32 ring
buffer. As the camera moves, only the incoming row or column of metatiles is
redrawn (`engine/src/field_camera.c:123` `RedrawMapSlicesForCameraUpdate`,
`:138-187`). So the *map layout* already works the way the operator describes.

**What it doesn't stream, and the three limits that force splits:**

| Limit | Value | Where it comes from | Hardware or engine? |
|---|---|---|---|
| Tile graphics in VRAM | 1024 tiles (512 primary + 512 secondary), loaded once per map | `fieldmap.h:8-14`; loaded whole at map entry (`fieldmap.c:1025-1136`) | **Both.** A BG tilemap entry has a 10-bit tile index, so one BG layer can address 1024 tiles. *Which* 1024 are loaded is engine policy. |
| Metatiles per map | 1024 | The map grid is a `u16`: 10-bit metatile id + 2 collision bits + 4 elevation bits (`global.fieldmap.h:5-12`) | **Engine only.** It is a data-format choice. Metatile definitions live in ROM, and the hardware never sees them. |
| BG palettes | 13 of 16 (3 kept for UI/text) | `fieldmap.h`, `palette.h:18` | Hardware: 16 palettes × 16 colours. |

**What actually forced Map 40's split: metatiles and tiles, not palettes or map
size.** Map 40 alone is 1278 metatiles. A 1024-metatile cap can't be met by any
amount of colour work, since quantization doesn't touch metatile count
(MEMORY.md, 2026-10-04). Unsplit with the near-duplicate tile merge off, it is
~1544 tiles. The 2026-07-14 corpus audit
(`reference/findings/corpus_scaling_audit_2026-07-14.md`) found:
- **16 maps over a cap:** 9 over 1024 metatiles (040, 071, 084, 094, 101, 117,
  143, 144, 187; worst is Map094 at ~1806) and 7 over 1024 tiles.
- **Palettes were never the constraint.** The four worst maps all fit 13 BG
  palettes.
- **Only Map 40 has been split so far**, so 15 more splits are queued on this
  path.

**What a streaming engine would look like.** It has two parts, matching the two
engine limits:
1. **Widen the metatile id.** Store the map grid with a 16-bit metatile id
   (a `u32` grid, or a separate id array beside the collision/elevation bits),
   and give each map one large metatile table in ROM. The cost is EWRAM: the map
   buffer is 10240 cells, so `u16`→`u32` adds 20 KB of 256 KB. Everything that
   reads or writes the grid by id would need touching (behaviour lookup, door
   and field-effect metatile swaps, `MapGridSetMetatileIdAt` callers, and the
   `mapjson`/layout tooling).
2. **A VRAM tile cache instead of a fixed tileset pair.** Keep up to ~1024 tiles
   resident. When a metatile row or column enters view, load any of its tiles
   not already resident into free slots, and evict tiles that are no longer on
   screen (reference counts over the visible window).
   - **Bandwidth is not the problem.** One incoming row is at most 16 metatiles ×
     8 tiles × 32 B ≈ 4 KB. A step lasts several frames, and VBlank DMA moves far
     more than that per frame.
   - **The real constraint is unique tiles in one screen.** About 17×12
     metatiles are visible plus margin. That could in theory exceed 1024 unique
     tiles, but real maps are nowhere near it. A build-time check would fail
     loud on any window that is.
   - **Palettes need no streaming for Uranium**, since every map already fits 13.
     If a future game needs it, the constraint becomes "any screen-sized window
     uses ≤13 palettes", which the quantizer can enforce. The tile's palette
     number is written per tilemap entry at draw time, so it can be remapped.

**What it would also fix:**
- **Seams (#27):** the engine draws a connected neighbour with the *current*
  map's tileset, which is why each map has to import its neighbour's border
  strip. With a cache, the neighbour's tiles are just more cache entries.
- **The split workarounds go away:** arrow warps between pieces, NPCs that
  can't see across a cut, and events that fail loud when they reference
  another piece.
- **Art quality:** the near-duplicate tile merge exists to squeeze maps under
  the 1024-tile cap. That pressure largely goes.

**What it touches:**
- `fieldmap.c` (load), `field_camera.c` (draw).
- `tileset_anims.c`: animation frames are DMA'd into fixed tile slots today, so
  animated tiles would need pinned cache slots. The 20-entry animation queue
  stays.
- Metatile behaviour lookup, door/field-effect metatile swaps.
- The layout format and its build tools.
- Save compatibility. This matters to I6: a save made before the change would
  need migrating.

**Possible middle path, not yet verified.** BG1–BG3 share charblock 0 today
(`overworld.c:320-355`). If the bottom and top metatile layers sat on BGs
pointed at *different* charblocks, each layer could address its own 1024
tiles. That would roughly double tile capacity without a cache, but not lift
the metatile cap. BG VRAM is 64 KB and charblock 2 / screenblocks 28-31 are
taken, so how much is really free needs a VRAM map before believing it.

**Scale of the decision.**
- **Keep splitting:** 15 more maps, each with its own cut spec and the costs
  above.
- **Streaming engine:** one large, engine-wide change, the biggest this project
  would have made. It is reusable for every future fan game, which ties it to
  I3. It also changes what "a map" is for every tool downstream.

### I5. Where the ROM size limit actually comes from

**The question.** The project has worked to a maximum ROM size. Is that limit
set by what a standard GBA cartridge can hold, or by the console itself? The
operator plays mostly in emulators. On real hardware they would use an SD-card
flash cartridge, which already stores hundreds of games, so a standard
cartridge's capacity may not be the real ceiling. Where is the limit, really?

**Status:** researched 2026-10-16 (below); not yet discussed.

#### Research (2026-10-16)

**Short answer: the limit is the console's, not the cartridge's, and it is
32 MiB.** The SD card doesn't change it.

- **Where 32 MiB comes from.** The GBA addresses cartridge ROM through a 32 MiB
  window at `0x08000000–0x09FFFFFF`. The same window is mirrored at `0x0A…`
  and `0x0C…` for different wait states; they are not extra space. 24 address
  lines × 16-bit words = 32 MiB. Our linker script declares exactly that:
  `ROM (rx) : ORIGIN = 0x8000000, LENGTH = 32M` (`engine/ld_script_modern.ld:11`).
- **Why the SD card doesn't help.** A flash cart copies *one* game from the SD
  card into its own RAM or flash, then presents it to the console through that
  same 32 MiB window. Card size is about how many games, not how big one game
  can be.
- **Going past 32 MiB needs bank switching**: hardware on the cartridge that
  swaps which part of a bigger ROM appears in the window, with game code to
  drive it. No retail GBA *game* did this. Only the 64 MiB GBA Video carts did.
  - mGBA supports that one Video-cart mapper, and a developer called it "not
    really suitable for ROM hacks". A ROM simply padded past 32 MiB crashes.
  - A newer EZ-Flash Omega revision reportedly has 64 MiB of RAM for those Video
    ROMs. That comes from forum posts, not a spec sheet.
  - So a >32 MiB Uranium would need custom bank-switching code in the engine
    *and* a cart and emulator that implement a matching mapper. In practice the
    ceiling is 32 MiB everywhere, emulators included.

**How much of it we use today** (from `engine/pokeemerald.map`, current
build):
- **26.7 MiB used of 32** (`__rom_end = 0x09AB6A9C`), so **~5.3 MiB free**. The
  `.gba` file is always 32 MiB because it is padded, so its size says nothing
  about how full it is.
- **What takes the space:**

  | Content | Size | Notes |
  |---|---|---|
  | `data/sound_data.o` | 10.05 MiB | Stock Emerald/expansion music and cries. Uranium uses none of its own audio yet (#22). |
  | `src/pokemon.o` | 5.88 MiB | The expansion's full species roster with graphics, ~1500 species. 24 Uranium species are staged. |
  | `src/tilesets.o` | 1.13 MiB | Stock + ours |
  | `event_object_movement.o` | 0.99 MiB | Overworld sprites |
  | `graphics.o` | 0.92 MiB | |
  | `data/maps.o` | 0.72 MiB | Stock + ours |
  | `tileset_anims.o` | 0.41 MiB | Mostly ours; Route 1's water alone is 95 frames |

- **Uranium's ~30 built maps cost roughly 0.8 MiB** of tileset data (tiles,
  palettes, metatiles, animation frames), about 27 KiB per map.

**Rough projection, to show the direction, not a budget.** About 160 more maps
at that rate is ~4–5 MiB of tilesets alone. Add their layouts, events and
scripts, ~200 Uranium species' graphics (at the expansion's ~4 KiB per
species, ~0.8 MiB), and any Uranium audio. **The full game does not fit in
5.3 MiB while all of stock Emerald stays in the ROM.**

**What follows.** The ceiling can't realistically be raised, so the room has to
come from what we ship. That is I3's "stop shipping unused Emerald content":
- stock music (most of the 10 MiB, if Uranium substitutes or brings its own),
- the ~1300 species Uranium never uses,
- Emerald's own maps and tilesets.

I5 therefore turns I3 from a cleanliness goal into a requirement for finishing
the game. It also re-opens #22's audio arithmetic, which assumed today's
budget.

Sources: [GBAtemp "GBA MAX ROM Size?"](https://gbatemp.net/threads/gba-max-rom-size.530489/),
[mGBA forums, 0.7 beta 1 thread (64 MiB GBA Video support)](https://forums.mgba.io/showthread.php?tid=4885),
[GBAtemp EZ-Flash Omega Definitive Edition B](https://gbatemp.net/threads/new-version-ez-flash-omega-definitive-edition-b.682007/).

### I6. Carry the operator's own save from walk to walk

**What the operator sees.** Boot-walk ROMs that start at a fixed point work
well. But each walk starts from the suite's state, not the operator's own
game, so testing doesn't feel like playing. The operator wants to play the
game as it is built, not wait until everything is finished.

**What the operator wants.** Start one real playthrough, build a party, and
keep using that save and party on every walk after that. This beats I1's
"add Pokémon as we go" idea; I1 is the fallback if this can't be done.
Possible shapes the operator raised:
- Load the operator's save directly into each new ROM build. The save might
  need migrating whenever ROM changes would break it, perhaps only at act
  boundaries.
- The operator plays and sends the save. The pipeline lifts the party out of it
  and puts that party into the next walk ROM's start state.
- Some other way of getting the same result.

**Status:** researched 2026-10-16 (below); not yet discussed.

#### Research (2026-10-16)

**Short answer: doable, but not today.** Three things in the current design
work against it, and all three are fixable.

**1. Walk ROMs ignore in-game saves, by design.** A walk ROM carries an
embedded save, the "seed blob": the four save blocks copied raw out of
emulator RAM and patched into the ROM (`playtest/stamp.py`, engine
`uranium_embedded_save.c`). At boot the engine loads the blob *before* looking
at the `.sav` (`new_game.c:359-387`). That was deliberate: it fixed the
2026-08-01 bug where an old `.sav` hijacked the walk. The consequence is that
**saving on a walk ROM does nothing useful.** Every boot returns to the
stamped point. So today the operator *cannot* carry progress forward even
within one ROM.

**2. A rebuild can silently change what saved data means.** The pokeemerald
save has no version field. A `.sav` loads if every sector's signature and
checksum match, and the checksums cover struct-sized chunks. So:
- if a rebuild changes a save struct's **size**, an old save is rejected as
  corrupt;
- if sizes stay equal, the save **loads, but nothing is re-mapped**. Any id that
  moved now points at the wrong thing.

What can move between builds, checked against the code:

| Saved thing | Stable today? | Why |
|---|---|---|
| **Flag / var numbers** | **No: the main problem** | `flag_registry.dump_header` (`flag_registry.py:585-599`) numbers flags by *sorted position*, not by id. Only 31 of Uranium's 235 switches are minted so far. Any later chapter that mints a lower-numbered switch shifts every flag above it. Hide flags are worse: they are numbered *after* all self-switches, so any new self-switch shifts every hide flag. |
| Map numbers | Mostly yes | `map_constants.write_map_groups` orders maps by id-sorted position too, but all 204 maps (whole corpus plus split pieces) are already minted, so new chapters don't add any. A future split that removes a map would shift the ones after it. |
| Species | Yes | Append-only by design (`species_converter/common.py:7-9`). The dex flag arrays grow by one byte every 8 new species, which changes the save block size. |
| Heal locations | Yes in effect | The save stores the warp (map number + x/y), not the heal-location enum. |
| Object local ids | Not saved | Hidden/removed state lives in flags, so it rides on the flag row above. |
| Items | Unknown | How Uranium-added item ids are assigned at staging wasn't traced (#41). |
| Save struct sizes | Changes occasionally | Flag/var range changes and dex growth change sizes. The CH04 work avoided one such change precisely because it "invalidates every save and seed blob". |

The seed blob has the same exposure. The engine checks only a magic number
and the four sizes, which is why blobs are thrown away on every rebuild (keyed
by ROM hash). That is a *policy* guarding against the silent-shift row above,
not a format limit.

**3. No tooling reads a party from a save file.** The harness reads the party
from live emulator RAM (`assertions.read_party_species`/`_moves`, with the
decryption already written), and it can write a save by driving the START
menu. Nothing parses a `.sav` file or moves data between builds.

**What each of the operator's options would take:**

| Option | Needs | Notes |
|---|---|---|
| **A. Keep one `.sav` across builds** | (1) a "play" build mode where the `.sav` wins and the blob only seeds a first boot; (2) **stable ids**: flags/vars numbered by their Uranium id (or a persisted append-only order) instead of sorted position, which is a flag-registry policy change, so the operator's call; (3) a save-format version stamped into the ROM, so a build that changes a size fails loud instead of rejecting the save as "corrupt". | Closest to "just playing". Once ids are stable, most chapter builds wouldn't break the save at all. Size changes would still need a migration step. |
| **B. Transplant the party** | A `.sav` reader (sector layout, checksums, the encrypted party/box format; the decryption exists for RAM reads) and a writer that puts the party, plus bag and money, into the next walk ROM's seed blob before stamping. | Doesn't depend on stable flags, since story state comes from the suite and only the party carries over. Works today's way: one ROM per walk, now with the operator's own team. Story choices don't carry. |
| **C. Migrate the full save** | B's reader and writer, plus a translation table per build (old flag/var/map ids → new) from the registry state of both builds. | Most general, and the most machinery. Mostly unnecessary if A's stable ids land. |

**Observation.** A's step (2), stable flag numbering, is a correctness
improvement regardless. It is the same silent-shift hazard that forces seed
blobs to be thrown away on every rebuild. With it in place, B becomes a small
tool and C is rarely needed.

---

## 2. Backlog items to consider moving forward

Candidates from `PROJECT_TODO.md`, grouped by how they relate to §1. This is a
shortlist, not a decision: each one is "worth discussing now", and §3 records
what is actually picked up. Where a quick grep suggested an entry is stale, the row
says so. The descriptions are pointers; the
backlog entry stays authoritative.

### 2a. Feeds an operator item directly

| # | Item | Relates to | Why now |
|---|---|---|---|
| 23 | Tile-animation follow-ups: cadence, many effects per tileset, frames hitting the lcm guard, transparent waterfall untested | I2a | The overhang glitch is in exactly this code path. The "frames × layered static tile" case was never in the follow-up list. |
| 14 | Map viewer / oracle leave animation frames out of quantization | I2a, I2b | The viewer can't show an animated-tile colour problem the ROM has, so it can't be used to check the I2 fixes. |
| 34 | Secondary-tileset animation support (animated tiles must fit the 512-tile primary block) | I2a, I4 | Forced once ts28's maps arrive. Any rework of how tiles are packed (I2/I4) should account for it. |
| 10 | The full-corpus art walk was sampled, never exhaustive | I2 | I2b-type palette mismatches are what a systematic pass would catch. |
| 41 | 106 items the fork doesn't define, and Phase 2's item output never reaches the engine | I3 | The clearest existing case of "generated C written, then discarded". It is the template for I3's generator-into-engine path. |
| 140 | Every map's name popup says LITTLEROOT TOWN (minted `MAPSEC_*` never reach `region_map_sections.json`) | I3, walk feel | Same shape as #41: engine data the pipeline should generate. Visible on every walk. |
| 96 | Pokémon Centers heal but never set the respawn point; white-out goes to vanilla Petalburg | I6, I1 | **Looks built but never closed.** `pbs_converter/heal_locations.py`, `setrespawn` emission in the transpiler, the anchor in `new_game.c`, and white-out beats in `ch01`/`ch03`/`ch06` all exist (2026-10-16 grep). Confirm, then move to Done. A real playthrough (I6) depends on it. |
| 31 | Pokédex should be Uranium's Tandor regional dex, generated from `regionals.dat` | I3, I6 | Operator decision 2026-08-11: wanted. It is engine data from game data, and visible in a real playthrough. |
| 35 | Uranium-original moves silently missing from staged learnsets | I3, I1 | Staging Uranium's own moves is part of "generate what the game needs". It also affects the party built under I1/I6. |
| 37 | Nothing sweeps engine map dirs orphaned by a rename | I3 | Any I3 work that regenerates engine content needs a reliable clean-out step. This is the existing hole. |
| 22 | Audio: the ROM plays stock Emerald music (`MUS_LITTLEROOT` everywhere); a decision is still owed | I3, walk feel | Was blocked on an operator decision. It also turns on I5: the budget arithmetic that ruled out real audio conversion assumed today's ROM size limit. |
| 27 | Moki E seam → Route 03: per-map packing, pinned palette families, border-strip import | I4 | Due at CH09 anyway, the first Act 2 chapter. If I4 changes how tilesets and palettes load, this design changes with it. |
| 85 | `BUILD_PLAN.md`'s boot-walk seeding recipe is wrong (seeds are invalidated by the rebuild) | I6 | Doc fix. Whatever I6 lands replaces or extends this recipe. |
| 21 | No freshness guard: the ROM under test vs the staged source | I6 | A persistent save makes "which build is this?" matter more. |

### 2b. Due "at the end of Act 1", or closeable now that CH08 is built

| # | Item | State |
|---|---|---|
| 44 | CH01/CH03 flavour interiors shipped untested; deferred to the end of Act 1 | Already verified (2026-10-15) as superseded by the generated suites. Move to Done. |
| 50 | `isRockSmashSoftlocked` unrecognized head | Noted "move to Done on CH08's gate". |
| 127 | No party/dex model | Built in CH08 (the scoped version). Close, or narrow to what's left. |
| 92, 128 | Capability model can't see field capabilities; `blocked:` held back until the model is real | CH08 built requirement groups for Rock Smash. Close or narrow: the gadget items and other HMs remain. |
| 63 | CH04 owes two negative beats on Route 2's rocks | Its stated "right time" was the first real smash chapter, which was CH08. Decide: write them, or retire. |
| 69, 70 | Running the tests writes into tracked `reference/playtest_rule_versions.json` | Hit again this session: the file was dirty after the runs. A small fix that stops `git status` lying. |
| 122 | C10 offline checker: "build it before a run gets long" | The CH08 run (CH01–CH08 from boot) is the longest yet. Re-time it and decide. |
| 147, 146, 145, 144 | CH08 leftovers: the `unselected_arm` label, `giveitem` VAR_RESULT, two reward rungs, dex-count text | Small, and all in code that is fresh in mind. |

### 2c. Visible on a walk, independent of §1

| # | Item |
|---|---|
| 141, 142 | Phone-rematch trainers register without asking; Bambo's phone contact is dropped. |
| 20 | Dead lab PC (Map050 EV026). **Probably fixed:** `Map050.pory` now emits a PC script (2026-10-16 grep). Confirm on a walk, then move to Done. |
| 7 | HEROINE player sprite: mechanical, never done. |
| 24 | Sign-off owed on substituting the vanilla Poké Ball sprite. |

**Deliberately left out:** items scoped to a later chapter (#39 CH25, #40b
CH58, #143 Legen Town, #32 crop-field maps, #113/#112 maps not yet built) and
pure checker/route-tooling items (#67, #73, #75, #77, #78, #80, #81) that
nothing in §1 touches.

## 3. Decisions

*(None yet.)*
