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

**Status:** recorded, not yet discussed.

### I2. Graphics cleanup

Two defects the operator saw during the CH08 walk and chose not to fix inside
the chapter.

**I2a. Static tiles glitch over animated tiles.** Where a static tile sits on
top of an animated one, the static tile glitches at one point in the animation
cycle. Most visible on Route 1 near the animated water: trees and rocks that
overhang the water glitch.

**I2b. Large boulders use the wrong palette.** The large boulders don't share
the palette of the surrounding rocky terrain, so they look out of place.

**Status:** recorded, not yet discussed.

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

**Status:** recorded, not yet discussed.

### I4. Stream the world instead of splitting maps

**What the operator sees.** Large maps are currently split into pieces to fit
the engine's tileset and palette limits; map 40 is the example. Related to I3,
graphics could perhaps be handled differently.

**The question.** Could the engine keep in memory only what is on screen and
the area just around it, with tiles and palettes swapped in and out of RAM as
the player moves? That is how open-world games such as GTA or Breath of the
Wild stream a huge world without loading all of it. Is this possible at all on
GBA hardware, knowing it would be a much bigger engine change?

**Status:** recorded, not yet discussed.

### I5. Where the ROM size limit actually comes from

**The question.** The project has worked to a maximum ROM size. Is that limit
set by what a standard GBA cartridge can hold, or by the console itself? The
operator plays mostly in emulators. On real hardware they would use an SD-card
flash cartridge, which already stores hundreds of games, so a standard
cartridge's capacity may not be the real ceiling. Where is the limit, really?

**Status:** recorded, not yet discussed.

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

**Status:** recorded, not yet discussed.

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
