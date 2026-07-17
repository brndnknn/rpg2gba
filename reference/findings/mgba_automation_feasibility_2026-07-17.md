# Feasibility: automated ROM playtesting via headless mGBA

*2026-07-17 — feasibility study only, nothing implemented. Requested scenario:
build a ROM, then have a scripted harness boot it, walk the player to Auntie
(Map049 hard gate), advance the interaction to the Running Shoes grant, verify
it, and leave behind a save the user can resume from to confirm the shoes work.*

## Bottom line

**Feasible, with one redirect.** The installed `mgba-qt 0.10.2` is the wrong
vehicle — its scripting is Lua loaded *manually* through the Tools menu, with no
`--script` CLI flag (that flag is an mGBA 0.11 feature request, not in any
release) and explicitly no headless mode. The practical path is **mGBA's Python
bindings (`libmgba-py`)**: a headless `libmgba` core driven directly from
Python — frame stepping, key injection, memory reads, savestates, screenshots —
which drops straight into our existing pytest/venv world with no emulator window,
no Xvfb, no socket bridge. This is a proven pattern: **PokéBot Gen3** runs
exactly this stack against Ruby/Sapphire/Emerald/FireRed/LeafGreen, including
full overworld navigation and dialogue automation on Emerald — the same engine
family our ROM is.

Two facts make our situation *better* than PokéBot's:

1. **We build the ROM, so we own the symbols.** The fork build leaves
   `pokeemerald.elf` + `pokeemerald.map` next to `pokeemerald.gba` (verified in
   the live `engine/` build: `gSaveBlock1Ptr` @ `0x030051d0`, `gObjectEvents` @
   `0x020015c0`, `gMain` @ `0x030066cc`; note the old external clone's map has a
   *different* `gObjectEvents` address — proof the harness must always parse the
   map file of the build under test). No reverse-engineered address tables — the harness
   parses the linker map from the same build that produced the ROM under test,
   so addresses can never go stale.
2. **The slice ROM already skips the intro** (spawn-override/intro-skip custom C
   in `engine/`), so "boot to overworld" is nearly immediate — no
   name-entry/Birch-speech automation needed.

## How the pieces fit

```
pytest test  ──►  libmgba-py core (headless)  ──►  output ROM (.gba)
     │                    │
     │  parse             │  read8/16/32 at symbol addrs
     ▼                    ▼
pokeemerald.map     game state: player x/y, map id,
(same build)        script-engine busy?, FLAG_* bits
```

- **Boot & run:** load ROM, `run_frame()` in a loop. Headless — a video buffer
  exists (grabbable as PNG for taildrop) but nothing needs a display. Wall-clock
  is fast: an uncapped core runs hundreds of frames/sec, so a whole scenario is
  seconds, not minutes.
- **Input:** set/clear the joypad bitmask between frames (hold DOWN for n
  frames, tap A, etc.).
- **State reading:** `gSaveBlock1Ptr` is a pointer in EWRAM/IWRAM — read the
  4-byte pointer, then read fields at offsets into SaveBlock1 (player coords,
  `flags[]`). `FLAG_SYS_B_DASH` = `SYSTEM_FLAGS + 0x60`
  (`include/constants/flags.h:1463`) → one bit test at
  `saveblock1 + offsetof(flags) + flag/8`. Object positions also via
  `gObjectEvents` directly.
- **Verification:** assert the flag bit flips after the Auntie interaction;
  assert map id / coords along the way ("warp to 2F fired", "reached Map049
  tile x,y").

### The critical design rule: poll state, don't count frames

A frame-scripted input tape ("press A at frame 812") is brittle — any text-speed,
RNG, or converter change breaks it. The harness should instead be a tiny
state machine:

```
walk_to(x, y):    hold direction key until player coords == target (with timeout)
interact():       tap A, then wait until the script engine is idle again
advance_dialog(): tap A whenever a message-box is waiting, until idle
```

"Script engine idle" is readable from memory (`ScriptContext` status /
`gMain.callback1` / a lock flag — pick whichever symbol proves most stable; all
are in the map file). Every primitive gets a frame-budget timeout so a hang
fails loud with a screenshot instead of spinning. This is exactly how PokéBot
navigates, and it makes the test robust against dialogue length and timing
changes — which is what we want, since the converted scripts are precisely the
thing that keeps changing.

### The save-at-the-end requirement

Two complementary artifacts, both cheap:

- **In-game save (the one you asked for):** after the shoes are granted, the
  harness scripts START → SAVE → confirm through the menu (same
  poll-and-press primitives). mGBA writes the flash save as `<rom>.sav`. You
  then launch the ROM normally in mgba-qt, choose CONTINUE, and you're standing
  in the house with Running Shoes — a genuine end-to-end proof, because it also
  exercises real save/load of the converted map.
- **Savestate:** `save_state` to a file as a bonus artifact (instant resume at
  the exact frame). Note a savestate is an emulator snapshot, not an in-game
  save — good for debugging, but the `.sav` is the honest artifact.

Both (plus per-step screenshots) can be taildropped after a run.

## Risks / open questions

- **`libmgba-py` build & pin.** It's hanzi's fork of the in-tree bindings
  ("modified to build easily"), used in production by PokéBot; venv is Python
  3.12.3, which PokéBot supports. It builds `libmgba` from source (cmake +
  standard deps) — that's a system-ish toolchain step, so per CLAUDE.md §10 it
  needs a green light before installing anything outside the venv. First spike
  answers whether prebuilt wheels cover our platform or we compile.
- **Struct-field offsets.** The linker map gives symbol *addresses*; field
  offsets inside `SaveBlock1`/`ObjectEvent` come from the DWARF in
  `pokeemerald.elf` (pyelftools, one-time extraction per build) or from a small
  generated offsets header. Straightforward, just has to be done from the build
  artifacts, not hardcoded — same "no invented constants" discipline as §4.7.
- **SaveBlock encryption/ASLR-ish features.** pokeemerald-expansion keeps the
  vanilla moving-saveblock behavior off by default in modern builds, but verify
  once that `gSaveBlock1Ptr` dereference is stable across boots; if the ROM ever
  enables saveblock obfuscation, read through the pointer each time (which the
  design already does).
- **RMXP-side nondeterminism.** NPC random-walk (EV008's patrol) can body-block
  the player. The poll-based walker retries naturally, but pathing around a
  blocking NPC may need a "step aside and retry" fallback. Timeout+screenshot
  keeps failures diagnosable.
- **What this gate does NOT cover:** art legibility, palette garbage, animation
  jank — anything by-eye. This harness is a *regression floor* under the §9
  boot-walk (boots, story chain completes, flags set, saves work), not a
  replacement for it. The manual gate stays.

## Alternatives considered

| Option | Verdict |
|---|---|
| `mgba-qt 0.10.2` + Lua script | No CLI script loading in 0.10.x, no headless mode; manual menu click per run. Dead end without upgrading. |
| mGBA 0.11-dev build + `--script` + Lua socket bridge (mgba-http / mgba-mcp) | Works, but adds a dev-build dependency plus an IPC layer, and input over a socket is not frame-accurate. Only attractive if we later want to puppet a *visible* emulator. |
| `mgba-rom-test` | Headless, but designed for ROMs that self-report a pass/fail register (the decomp's own test runner uses it). Wrong shape for "play the game." |
| BizHawk / lua-in-other-emulators | Heavier, Windows-leaning, no advantage over libmgba-py here. |

## First steps (in order, each ~an hour, stop at any red flag)

1. **Spike: bindings install.** Add `libmgba-py` to the venv (per §10, flag any
   system-level deps first). Load the current slice ROM, run 600 frames
   headless, dump a screenshot. *Proves: build + boot + video.*
2. **Spike: symbol-driven read.** Parse `pokeemerald.map`, read
   `gSaveBlock1Ptr` → player coords, print them while holding DOWN for 60
   frames. *Proves: input injection + memory model + that coords move.*
3. **Spike: script-engine idle detection.** Find the most reliable "dialogue
   waiting / script busy" signal and wrap the three primitives (`walk_to`,
   `interact`, `advance_dialog`). *This is the only genuinely fiddly part.*
4. **The scenario:** boot → 2F → 1F → Auntie → dialogue → assert
   `FLAG_SYS_B_DASH` → scripted in-game save → emit `.sav` + savestate +
   screenshots. Package as `tests/playtest/` (pytest, but marked/opt-in — it
   needs the built ROM and symbol files, so it's not part of the default unit
   run).
5. **Then decide** whether to fold it into the build loop (post-assemble smoke
   test per slice ROM) and how scenario definitions should be written so slice
   2+ scenarios are data, not code.

## Spike results (2026-07-17 — all four passed, same day)

The full target scenario ran headless in seconds: boot → walk (7,7)→(4,5)
around the furniture → face Auntie → 202 A-taps of dialogue →
`FLAG_SYS_B_DASH` flips true → scripted START→SAVE→YES → 128 KiB `.sav`
written → flag verified *inside the flash image* by parsing the sector format
(active-slot SaveBlock1 chunk, sector id 2, counter check) → savestate saved
and round-tripped into a fresh core (`B_DASH=True` after load). Spike scripts +
artifacts live in the session scratchpad (`harness.py`, `spike*_*.py`,
`probe_offsets.c`, screenshots); nothing is productionized yet.

What the spikes established beyond the plan:

- **No compiling needed.** The prebuilt `libmgba-py_0.2.0_ubuntu-lunar.zip`
  ships an abi3 `_pylib.so` that links the system `libmgba.so.0.10` installed
  with mgba-qt; every `ldd` dep resolves. Only new venv dep: `cffi` (declared
  in pyproject). Speed: ~2 300 fps headless (600-frame boot in 0.26 s).
- **Gotcha: `mgba.core.load_path()` does not attach a save file** — call
  `core.autoload_save()` before `reset()` or the in-game save silently writes
  nowhere.
- **Struct offsets: probe-compile, not DWARF.** The ELF's debug info is ~5 KiB
  (startup only). Reliable method: compile a `probe_offsets.c` of
  `offsetof`/constant-sized char arrays against `engine/include` with the
  ROM's exact flags (**`-mabi=apcs-gnu` matters** — it changes layout; devkitARM
  gcc default ABI errors on the enum bitfields in `pokemon.h`) and read values
  back via `nm -S`. Verified: `SaveBlock1.pos`@0, `.location`@4,
  `.flags`@0x1270, `FLAG_SYS_B_DASH`=0x8C0, `ObjectEvent.currentCoords`@0x10.
- **Script-idle signal solved (spike 3's risk item).** `sLockFieldControls`
  is static and absent from the linker map, but its address falls out of the
  literal pool of `ArePlayerFieldControlsLocked` (in the map): `objdump -d`
  the function, take the pooled word + the `ldrb` offset (this build:
  0x030016c4+4 = 0x030016c8; +5 is `sGlobalScriptContextStatus`). Re-derive
  per build in the real harness. Poll-based `walk_to`/`advance_dialog` on top
  of it proved fully stable, including greedy two-axis pathing around the
  house furniture.
- **Save-menu navigation is trivially scriptable** (BAG/RED/SAVE/OPTION/EXIT,
  two DOWNs + A + A), and `.sav` verification doesn't need the emulator at
  all — the sector parser in `spike4_verify_sav.py` is ~30 lines.

**[RESOLVED same day — superseded by the embedded-save build below]**
**Open decision for the user:** the slice's intro-skip
(`CB2_StartUraniumSlice`) *always* starts a new game — `gSaveFileStatus` is
never consulted — so neither the harness nor a human can CONTINUE into the
written save on the current ROM (verified: fresh boot after save →
`B_DASH=False` at spawn). The "launch it yourself and have the shoes" proof
needs one of: (a) slice hook boots `CB2_ContinueSavedGame` when a valid save
exists (changes boot-walk workflow — a stale `.sav` would skip fresh-boot
state), (b) a held-key override (e.g. hold B at boot = force new game), or
(c) keep always-new-game and rely on `.sav` parsing + savestates as the
proof. Cosmetic finding, same session: the save-info window says
"LITTLEROOT TOWN" — slice maps don't set a region-map section yet.

## Built (2026-07-17, same day): harness productionized + embedded-save review ROMs

User direction: regression tests always start from a brand-new game; review
artifacts must be a **single taildroppable .gba** that boots already in the
tested state (they play on the phone, never at the machine — pairing a
separate `.sav` there is impractical). Implemented as:

**Engine (sentinel-fenced `URANIUM PATHFINDER SLICE` / `URANIUM EMBEDDED
SAVE`):** `engine/src/uranium_embedded_save.c` + `include/
uranium_embedded_save.h` reserve a zero-filled const blob
(`gUraniumEmbeddedSave`, 0xD088 bytes: magic + 4 sizes + SaveBlock1/2/3 +
PokemonStorage) and `UraniumEmbeddedSave_TryLoad()` (validate → copy into
live save blocks → `CopyPartyAndObjectsFromSave()` → status OK; size mismatch
= red-screen hang, fail loud). `CB2_StartUraniumSlice` (new_game.c) now
branches: valid flash save → `CB2_ContinueSavedGame`; else stamped blob →
same; else the existing new-game path (harness/regression path unchanged;
walker builds keep always-new-game). **Engine gotcha burned into the code
comments: the blob and its reads must be `volatile`** — the Makefile defaults
LTO on, and without volatile GCC folded `magic == 0` against the const zero
initializer, shrank TryLoad to 4 bytes, and section-GC dropped the blob
entirely (first build proved it). Also `CB2_InitCopyrightScreenAfterBootup`
runs `LoadGameSave(SAVE_NORMAL)` before the hook, which is what makes the
flash-continue branch a one-liner.

**Pipeline (`src/rpg2gba/playtest/`):** `emulator.py` (headless core wrapper +
poll-state primitives walk_to/interact/advance_dialog/save, screenshots on
every failure), `symbols.py` (linker-map lookup + static-address recovery via
objdump literal pools), `offsets.py` (probe-compile against engine headers,
per build, no hardcoded numbers), `scenarios.py` (registry;
`moki-running-shoes` is scenario #1), `stamp.py` (blob build + ROM stamping +
click CLI). Bindings installed per-venv by `scripts/fetch_libmgba.py` (not
pip-installable; abi3 zip). Tests: `tests/test_playtest.py` — 3 unit tests
always on; the end-to-end (scenario → stamp → all three boot paths asserted)
is opt-in via `RPG2GBA_PLAYTEST=1` and ran green in ~11 s.

**Shipped:** `python -m rpg2gba.playtest.stamp --engine engine --scenario
moki-running-shoes --out output/uranium-build/review_moki_shoes.gba` →
taildropped to iphone182 (stamped ROM md5 `d06c772b`, from pristine engine
build `5dd32b10`). Boot-verified headless before sending: opens standing
below Auntie at (4,5), Map049, running shoes set; in-game saves on-device
take priority over the blob on subsequent boots. Full suite: 1228 passed /
15 skipped.

Sources: [mGBA scripting docs](https://mgba.io/docs/scripting.html) ·
[mGBA scripting announcement (headless "notably absent")](https://mgba.io/2022/05/29/scripting/) ·
[mGBA issue #3289 — `--script` CLI flag request](https://github.com/mgba-emu/mgba/issues/3289) ·
[libmgba-py](https://github.com/hanzi/libmgba-py) ·
[PokéBot Gen3](https://github.com/40Cakes/pokebot-gen3) ·
[mGBA-http write-up](https://www.nikouusitalo.com/blog/use-any-language-to-control-mgba/)
