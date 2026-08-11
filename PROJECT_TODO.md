# Project TODO — cross-cutting, cross-chapter loose ends

Working checklist for things that are **not** phase-plan items (→ `ROADMAP.md`)
and **not** scoped to the active chapter (→ `CH02_TODO.md`, the current
frontier checklist), but keep getting deferred across sessions and need a
home so they don't get lost. Retired chapter checklists live in
`reference/archive/` (e.g. `reference/archive/SLICE1_TODO.md`). Commit
updates as items close; move to **Done** with a one-line result rather than
deleting. Facts here are pointers — the cited code/docs stay authoritative.

## Open

### 1. Delete the old external pokeemerald-expansion clone

`engine/` is the vendored, in-repo copy now (cutover done 2026-06-19). The old
external clone at `/home/b/repos/pokeemerald-expansion` is stale and
superseded but was never removed — the agent's attempt was classifier-blocked,
needs a user-run `rm -rf`. Also clean the stale `.claude/settings.local.json`
allowlist entry naming the old clone path. (MEMORY.md Open Questions.)

### 2. Locate the Nuclear type's 1/8-HP-per-turn out-of-battle effect

Not in `217_Nuclear_Forms_Moves.rb`; likely a field/step hook or
`PokeBattle_Pokemon` patch. Needed before Phase 6 (custom engine work for the
Nuclear type) can start in earnest.

### 3. GBA charmap handling for accented characters

Sidecars are correct UTF-8 (`Pok\xE9mon`); `tileset_converter.assembly.normalize_pory`
owns charmap legality at staging (normalizes or fails loud) and the quantize
pipeline owns glyph rendering — but full correctness for é/♀/♂ across the
whole corpus (not just the slice) is unverified. Phase 5/6 integration
concern.

### 4. TMPBS field semantics

`tmpbs.dat` is confirmed a Uranium-custom extra move list per species, but
whether it's a move-reminder list or a broader compatibility list is still
open. Needed to decide the Phase 2 JSON representation before a full-corpus
PBS re-run.

### 5. Verify pre-seeded `VAR_GYM8_*` / `VAR_TANDOR_CHAMPIONSHIP_*` names

Proposed in Flag Registry Notes (MEMORY.md); may need renaming once the full
flag-registry policy is exercised outside the slice.

### 6. F3 — yesnobox two-step → native `msgbox(text, MSGBOX_YESNO)`

From the 2026-07-07 native-reuse audit (`reference/native_reuse_audit_2026-07-07.md`):
small transpiler fidelity win, not yet built. F1/F2 (the critical ones) are
done; F4 was no-action.

### 7. HEROINE player sprite

Slice boots MALE hardcoded. HEROINE sheets are exact-2× and convert cleanly
with the existing `sprites.convert_player_sheets` path whenever wanted —
mechanical, not blocked on anything.

### 8. Bike / surf / fish / field-move player poses beyond rock smash

HERO-BIKE/SURF/FISH etc. exist but are nonstandard grids (264×288, 384×384 —
not 4×4-of-64), so the exact-2×/majority-vote pipeline doesn't apply as-is.
None are slice-1-reachable; needed once a later slice touches water/cycling
routes.

### 9. `displayNinjaLetter` card UI

Currently converts as a scrolling msgbox (hand override, Map049 EV021). A
bespoke letter-card scene is a Phase-8 custom-C candidate if the flattened
version reads poorly in-game.

### 10. Full-corpus art walk is sampled only

Checkpoint-2 certification (2026-07-02) covered the 8-map walker batch by
sample, not exhaustively. Follow-up open: a systematic pass over all 199 maps'
converted art once more slices exist to make it worth doing in bulk.

### 11. 88 CommonEvent queue entries

Zero are called by slice 1, so they're out of scope there, but they're real
unconverted transpiler queue residue that blocks any slice that does call a
CE. Will need the CE-context idiom/native/hand triage (same shape as the
slice-1 event triage) once a slice pulls one in.

### 13. Map viewer: launch-stale quantized colors (browser-cache bug) — FIX APPLIED, verify

Root-caused 2026-07-13 (Brandon: flowers wrong colors on server launch, Apply
& re-render fixes them): all `/api/tile|metatile` PNGs are served
`Cache-Control: immutable, max-age=1y` with `?g=<_quant_generation>` as the
only cache-buster, and the generation was a module global reset to 0 on every
process start — including the hot-reload `os.execv` self-restarts — so bytes
the browser cached under a low `g` in an earlier process lifetime re-serve
forever on relaunch. (Packer itself proven deterministic; per-group URL
independence explains the mixed-vintage colors.) **Fix applied** in
`map_viewer_common.py`: `_quant_generation` seeded from the millisecond
clock, so a generation never repeats across lifetimes. Verify on the next
viewer walk (colors correct on first launch, no hard-reload needed), then
move to Done.

### 14. Map viewer + oracle: animated frames missing from quantization census

Found during the #13 trace; identical in both viewer render paths (so it does
NOT explain #13's symptom), but it's a real viewer↔ROM parity gap of exactly
the class the 2026-07-12 pool-scope fix was meant to close. The viewer never
threads animation frames into quantization: the analysis-pool build calls
`_render_column(ck, raster, priorities)` with no `n_frames`
(`map_viewer_common.py:474`), unlike the real pipeline
(`build_slice_tilesets.py:373`/`:396` passes
`n_frames=column_n_frames(...)`), so `MetatileImage.frames` is always `None`
and `emit.py`'s `extra_tile_colors` union stays empty — animated tiles'
frame-1+ colors never widen their assigned palette in the viewer preview,
while the ROM's do. `scripts/verify_viewer_rom_match.py` Mode B has no
frame handling either, so the oracle can't catch this divergence.

**Fix guide:** pass `n_frames=column_n_frames(ck, raster)` in the
`map_viewer_common.py:474` pool build (import `column_n_frames` from
`build_slice_tilesets`); the `:610` pre-quant renders serve the RPG Maker
reference view and shouldn't need frames — verify when building. Teach the
oracle's viewer mode the same, then re-run Mode B on the slice to prove
parity including animated columns.

### 15. Source→emitted dialogue census as a build-time gate

Nothing compares source event text (code-101/401) to emitted script text
(`msgbox` + text blocks). Need a corpus-wide count-and-ratio check that fails
loud past a threshold, modeling code-401 continuation lines merging into one
`msgbox` (not a strict 1:1 demand). Measured baselines from the audit: Map032
EV009 38→37 (complete), Map049 EV021 18→16 (fine, 401 merges), Map050 EV005
102→60 (unexplained, see #19), Map050 EV019 37→18 (the loss that triggered
the whole audit, since fixed). Must also cover hand-conversion files —
`hand_overrides.py:63` splices them in verbatim and skips every existing
coverage mechanism; its `_validate` only checks label-collision namespace
hygiene, not content. Migrated from SLICE1_TODO #28 §5.3 / hand-conversion
audit §5.3, 2026-08-04.

### 16. Close the `legacy_unaudited` escape hatch — still only warns

`load_queue_jsonl` raises on a `hand` queue entry with a blank evidence box,
but only **warns** when `legacy_unaudited: true` — verified still true at
`queue_evidence.py:241`. That flag was meant to mark an audit backlog and
became a permanent exemption; it let an unjustified hand conversion
(Map050 EV019) ship three real defects into the ROM before anyone caught it
(see `reference/findings/hand_conversion_audit_2026-07-31.md`). Fix: make
`legacy_unaudited` raise like a blank evidence box, then audit or retire
every remaining user of the flag (see #19 for the one still outstanding).
Also still undone: document the "hand conversion never amortizes" rule in
CLAUDE.md §4.1 and in a `hand_conversions/` README. Migrated from
SLICE1_TODO #28 §5.4 / hand-conversion audit §5.4, 2026-08-04.

### 17. Model scripted-route collision stalls for cutscene (`applymovement`) routes

RMXP stalls a move route when its destination tile is blocked/occupied and
Uranium leans on that idiom ("walk N tiles, stop when you bump into
someone") — e.g. Map050 EV005 page 0 marches the player `move_up`×10. On
GBA, `route_sim.py` and `MovementType_UraniumCustomRoute_Callback` only
model this for page-level ambient routes (`move_type == 3`); embedded
cutscene routes compile to vanilla `applymovement`, whose `walk_*` actions
never check collision (`InitNpcForMovement`,
`engine/src/event_object_movement.c:7287-7305`, path verified present).
Consequence: any such scripted route can land a different tile on GBA than
in RMXP, corpus-wide, silently. Extending `route_sim` to cutscene routes
also enables a build-time, no-emulator diff of RMXP-simulated vs
Emerald-simulated actor endpoints — see #26 for the specific instance this
would have caught. Migrated from SLICE1_TODO #28 §5.5 / hand-conversion
audit §5.5 / `reference/findings/lab_starter_scene_positioning_2026-07-27.md`
§6.1, 2026-08-04.

### 18. Emit `MB_COUNTER` for RMXP counter-passage tiles

`tileset_converter/tile_map.py:50-53` masks RMXP passages with `0x0F` and
discards the high bits as "non-collision flags" (path/lines verified
current). The counter bit is `0x80`; nothing emits `MB_COUNTER` anywhere in
the corpus, so counter-reach (talking over a counter to the tile beyond it)
is lost everywhere it appears. The engine supports it natively, zero custom
C: `MetatileBehavior_IsCounter` (`engine/src/metatile_behavior.c:490`,
verified present) is consumed by `GetInteractedObjectEventScript`
(`engine/src/field_control_avatar.c:400-409`, verified present), which looks
one tile beyond a counter for the object event to interact with. Note
collision is not derived from the behavior — a counter metatile must also
carry a non-zero collision bit to actually block. Migrated from
SLICE1_TODO #28 §5.6 / hand-conversion audit §5.6, 2026-08-04.

### 19. Hand-conversion audit backlog — three unresolved items (non-harness)

From `reference/findings/hand_conversion_audit_2026-07-31.md` §6 "Still
open" (harness items excluded — another agent tracks those):

- **Map049 EV020** is the other `legacy_unaudited: true, greps: []` ledger
  entry in `hand_bucket_queue.jsonl`. It has a ledger line but **no file**
  under `src/rpg2gba/conversion_agent/hand_conversions/` (verified absent
  2026-08-04). Never discussed or audited the way EV019 was. Needs the same
  audit treatment, or retirement if it turns out moot (SLICE1_TODO #28 notes
  it may be absent from the 2026-07-24 slice dry-run).
- **Map050 EV005 text ratio is unexplained.** 102 source strings → 60
  emitted. The hand-bucket retirement of EV005 (#23-era work) is otherwise
  justified, but this ratio was never accounted for — multi-page branching
  may explain it, or may not. Strongest existing argument for #15's build
  gate.
- **`pbStarterSelector` cutscene never read.** The EV019 header calls it
  "presentation-only" and substitutes a text box; nobody has opened the
  Uranium source for it. A PC playthrough reported an unconverted cutscene
  at this point in the lab scene. Read it in `RPG2GBA_URANIUM_SRC` and
  confirm or correct the substitution.

Migrated from hand-conversion audit §6, 2026-08-04.

### 20. Map050 EV026 — dead lab PC, one-line fix, never boot-walked

Real, unreported bug found while compiling `SLICE1_EVENTS.md` (§11.11), not
from a device walk. The lab PC's `pbPokeCenterPC` call sits inside an
unhandled code-111 character-facing conditional, so it was never emitted —
the event compiles to a bg event whose body is just `lock`/`release`/`end`.
Interacting with the PC does nothing. Map048 EV004's PC works because its
call isn't wrapped in a conditional. Fix: emit `goto(EventScript_PC)` for
this event, same as Map048 EV004 (`data/scripts/pc.inc`, vanilla). One line,
needs a build and a boot-walk to confirm. Migrated from
`SLICE1_EVENTS.md` §11.11, 2026-08-04.

### 21. No freshness guard: ROM under test vs currently staged source

The playtest runner enforces ROM-vs-seed-blob provenance (sha256) but has no
check that the ROM binary is newer than staged source. Has bitten twice: a
2026-07-25 harness run against a 45-minute-stale binary, and 2026-07-30 three
days of runs against a build (`1d1dde30`) the user had already rejected.
Same hazard class as the `.sav` residue bug and `BOOT_WALK_CHECKLIST.md` §8.
Guard: refuse to run if anything under `engine/data` or `engine/src` is
newer than the built ROM. Migrated from SLICE1_TODO #30 / also flagged in
`reference/findings/gated_door_collapse_2026-07-26.md` §6, 2026-08-04.

### 22. Audio — open user decision, ROM currently plays stock Emerald music

The transpiler comments out every RMXP audio command; no Uranium BGM/SFX
convert. The ROM currently plays whatever stock Emerald default falls out
of `map.json` (e.g. Littleroot's theme). Architecture already sketched in
`reference/findings/audio_decision_2026-07-14.md`: a fork-index-validated
substitution table `reference/audio_map.json`, wired into `metadata_wiring`
per-map BGM plus transpiler `playbgm`/`playfanfare`/`playse` — real
conversion/streaming was rejected by arithmetic (ROM budget). What's
outstanding is the user's call on the bar: accept stock audio as-is,
silence, or build the ~15-row substitution table (recommended). Not
slice-specific — applies to every future slice until decided. Migrated from
SLICE1_TODO #7, 2026-08-04.

### 23. Tile-animation follow-ups — untested beyond the slice's 2 effects

Core animation feature is done and user-verified (2026-07-12 build), but
three follow-ups were never checked:

- **Cadence fidelity.** 16 ticks/frame (~267 ms) is vanilla Emerald's water
  cadence, adopted as a first guess and approved by eye. RMXP's actual
  autotile speed in Uranium was never measured against it. Adjustable via
  the `% 16` divisor in `_write_anim_fragment` if a side-by-side ever shows
  a mismatch.
- **Corpus generalization untested.** Slice 1 exercises 2 effects on 1
  tileset; the corpus has 69 multi-frame autotiles (up to 64 frames,
  `seatest.png`). Untested: animated tiles landing in the SECONDARY tileset
  (current code packs into the primary block, fails loud past 512 — fine
  for the slice, needs a secondary-callback variant eventually), many
  effects per tileset (DMA queue caps at 20 entries/frame), and columns
  hitting the 64-frame lcm guard.
- **Waterfall / transparency untested.** ts22 slot 1 (`PU-Waterfall(transp)`,
  5 frames) is unused by the slice's Map032 cells — the first
  animated+transparent autotile arrives with Route 01 (slice 2). Stipple/
  alpha classify interaction with frame quantization is unverified.

Migrated from SLICE1_TODO #10, 2026-08-04.

### 24. PU-POKEBALL content-fidelity sign-off outstanding

`PU-POKEBALL` (the thrown-ball sprite in the capture-tutorial ball-throw
scene, Map032 EV009 P3/EV76) currently reuses the vanilla
`OBJ_EVENT_GFX_POKE_BALL` graphic rather than staging Uranium's own
still-pose sheet. This is a CLAUDE.md §10 content-fidelity substitution
call, not a bug — the scene itself boot-walked and passed 2026-08-02
(ROM `e0f6d30f`). The user's explicit sign-off on the substitution (accept
vanilla ball vs. convert Uranium's sheet) is still outstanding. Migrated
from SLICE1_TODO #23, 2026-08-04.

### 25. `assemble_pathfinder.WARP_OVERRIDES` is a hand-maintained duplicate

`scripts/assemble_pathfinder.py:58` defines a hand-written `WARP_OVERRIDES:
dict[int, set[tuple[int, int]]]` that must agree with what
`metadata_wiring.build_slice_maps` (`src/rpg2gba/tileset_converter/
metadata_wiring.py:2257`) computes for gated-door and warp-override cells —
a source-of-truth duplication that violates CLAUDE.md §4.3 ("one source of
truth per concept"). They happen to agree today (the gated-door fix's item
(4), `ObjectBuildResult.gated_door_cells`, is what keeps them agreeing) but
nothing enforces it, so a future reconciliation could silently re-diverge
and quietly re-break doors. Fix: derive `WARP_OVERRIDES` from
`build_slice_maps`'s computed set instead of hand-listing it. Migrated from
`reference/findings/gated_door_collapse_2026-07-26.md` §7, 2026-08-04.

### 26. Lab starter scene: what puts Uranium's own player on (14,7)? — unresolved, plus a fidelity call riding on the answer

`reference/findings/lab_starter_scene_positioning_2026-07-27.md` §4 poses an
open mechanism question, subsequently shown to rest on a retracted
argument (`reference/findings/hand_conversion_audit_2026-07-31.md` §3.3 —
the doc's own Through-ON evidence, read correctly, proves Theo ends at
(14,6), not (14,7); the "Uranium's anchor is (14,7)" claim doesn't survive).
What's left genuinely unresolved even after the retraction: nothing in the
reachable data (map collision, tileset counter bits, nearby events) explains
what mechanism would put Uranium's own player somewhere other than our
computed (14,6) anchor at the machine — the doc ruled out a counter tile
and a proxy event and found Bambo (EV005) vacates the spot, but never
identified a positive mechanism. Separately, and regardless of how the
mechanism question resolves: if a device playthrough of *original* Uranium
shows the same tile relationship, then whichever positioning our current
conversion produces should be a deliberate CLAUDE.md §10 content-fidelity
decision ("does our version look better than the original, and is that
okay") rather than an accident of which bug got fixed first. Needs a PC (or
emulator) playthrough of stock Uranium's lab scene to settle. Migrated from
`reference/findings/lab_starter_scene_positioning_2026-07-27.md` §4,
2026-08-04.

### 27. Moki Town east seam → Route 03: connections + border-strip import

Was `SLICE2_TODO.md` #3, moved here 2026-08-05 during the slice→chapter
reorientation: under the chapter model Route 03 is **CH09, in Act 2** — seven
chapters past the current frontier — so the Moki↔Route 03 seam is not CH02
work. It stays prerequisite-chained on per-map tileset packing
(`CH02_TODO.md` #4), and it should resurface when CH09 is planned, or earlier
if a CH01/CH02 boot-walk shows the east map edge needs real neighbour art.
This is the first of 14 `connections.dat` seams, and no seam anywhere in the
corpus is converted yet, so this item is the whole seams feature, not just
one map pair.

Originally migrated from SLICE1_TODO #9, 2026-08-04. CH01 only proved the seam
fails *cleanly* (blocked, no walk-into-void); converting it for real is this
item — Moki Town↔Route 03 (`[32,E,26, 59,W,0]`) is the first of 14
`connections.dat` seams and the nearest one to the frontier.

Architecture decided in `reference/guides/connections_and_palette_families.md`
(2026-07-14, user-approved by eye) — three parts:

1. **Per-map tileset packing** must land first (`CH02_TODO.md` #4) — shared
   per-RMXP tilesets are arithmetically impossible for this seam (Map032 ∪
   Map033 on ts22 = 1607 metatiles / 1611 tiles, over both 1024 caps).
2. **Palette families pinned per seam component** — Moki+R03 is one of 8
   `connections.dat` components; quantize both maps' tile union against ONE
   pinned palette set (new SoT artifact `reference/palette_families.gen.json`
   or per-component files) so seam colors match exactly. Consumer:
   `build_slice_tilesets` (`src/rpg2gba/tileset_converter/graphics/build_slice_tilesets.py`)
   quantizes member maps against the pinned set instead of deriving per-pack.
3. **Border-strip import** — emit the neighbor's visible border strip (≤ ~8
   metatiles deep past the seam) into each map's own tileset as extra
   columns, so the engine's native `connections` renderer (porymap
   `map.json` direction/offset/map schema) draws real neighbor art instead of
   VRAM garbage ("tileset bleed"). Exact sampling mechanism (map.json border
   block vs neighbor's real map data) needs a fork read of `fieldmap.c`
   connection handling before coding (§4.7) — not yet done.

**Also open, not yet resolved:** RMXP offset-sign → GBA offset-convention
worked example (Kevlar N offset 11 vs Moki E offset 26) — verify in-ROM at
the boot gate, per the design doc's own open note.

**Done looks like:** Map032 emits a real `connections` entry to Map033 (and
vice versa) in map.json; crossing the seam in mGBA shows continuous art with
no palette snap and no garbage strip; collision at the boundary is sane.

### 28. Time-of-day + Uranium-only encounter tables are dropped corpus-wide

The encounter emitter (`tileset_converter/wild_encounters.py`, landed 2026-08-09,
CH02_TODO #15) fills the fork's four native fields and drops everything else
into `uranium_extra`, unemitted. Uranium's 13 `EncounterType` slots include
four the fork has no host for at all (Cave, HeadbuttLow/High, BugContest) and
three that it *does* support but we don't wire: LandMorning / LandDay /
LandNight.

The time-of-day three are the tractable half. The fork already supports them —
`OW_TIME_OF_DAY_ENCOUNTERS` (`engine/include/config/overworld.h:95`, currently
FALSE) plus time-suffixed `base_label`s, with `OW_TIME_OF_DAY_FALLBACK`
(`:97`) and `OW_TIME_OF_DAY_DISABLE_FALLBACK` (`:96`) governing what happens
when a slot is empty. Today every map emits only the `TIME_MORNING` fallback
slot, which is also what vanilla does, so nothing is *broken* — it's fidelity
loss, silent unless you know to look.

Not frontier-urgent but not free either: `_LAND_SOURCES`
(`pbs_converter/encounters.py:57`) already prefers a plain `land` table when
one exists, so a map with BOTH plain and time-split tables (Route 1 is one —
densities `[25,10,10,0,0,0,0,0,0,25,25,25,25]`) silently uses the plain one and
the variants never surface. Turning the config on without auditing that
precedence would change behavior on maps nobody has walked.

**Care about it when:** a chapter's spec calls out a mon that only appears at
one time of day, or a cave chapter lands (Cave has no fork host at all and is
currently folded into `land_mons` as a fallback source).

**Done looks like:** a decision on whether Uranium's time-split tables are
worth `OW_TIME_OF_DAY_ENCOUNTERS = TRUE` corpus-wide; if yes, emitter support
for suffixed base_labels + a documented precedence rule between plain and
split tables. Also cross-referenced by `00-atlas.md:175`.

### 30. `text_validator` never scans generated C data headers

`extraction.py:95` `_CORPUS_GLOBS` covers only `scripts/*.pory`,
`staging/scripts/*.pory` and `porymap/dispatch/*.pory`. Generated data headers
— `species/uranium_species_info.h`, `src/data/items.h`, `src/data/moves_info.h`
— are never read, so the whole `.description` overlong/unwrapped class went
undetected until it was seen on a device (2026-08-11 boot walk). The module
already owns the right primitive (`measure_line_width_px`) and a line-width
rule; only the corpus is too narrow.

Note the rule needs a per-field budget to be useful here, not the single
`MSGBOX_WIDTH_PX`: a Pokédex entry is 224px × 4 lines (see
`DEX_DESCRIPTION_WIDTH_PX`), a bag item description is a much narrower window,
and dialogue is the message box. Wrapping itself is solved for staged species
(`wrap_to_width`); this item is about *detection* across every emitter, so an
unwired header can't ship broken the day it gets hooked up.

**Done looks like:** the validator reads generated headers with a field →
budget table, and a deliberately overlong description in any emitter fails the
suite rather than reaching a ROM.

## Accepted deferrals (not currently planned — listed so they aren't re-litigated)

- **Reflection narrow-scan** — tried and reverted 2026-07-07 (user: "not
  actually a fix"). Do not re-apply; if pond reflections get revisited it
  needs a different approach than narrowing the engine scan box.
- **new_game.c test harness** — `SLICE1_TODO.md` #5 decision landed (`4b8ca7ce`):
  **keep `FlagSet(FLAG_BADGE03_GET)` indefinitely** (user decision, standing rig,
  not a to-remove obligation). Its Rock-Smash-Geodude companion lines were
  separately disabled 2026-07-21 (rock smash not walkable on current builds) and
  are dead code alongside 3 other DISABLED harness blocks in the same function —
  see Group C cleanup, `reference/guides/engine_gotchas.md` is not the home for
  this, `ROM_TEST_DEV.md`'s "new_game.c debug-harness re-arm technique" section is.

## Done

- **12. Map viewer hot-reload** (2026-07-13) — built as scoped, both halves:
  tileset source PNGs joined the request-time stat fingerprint (eager
  `sources.tileset_source_paths` + memoized per-map derivation in
  `map_viewer_common`), and `map_viewer_server.py` self-restarts via
  `os.execv` when any imported repo source changes (watch set derived from
  `sys.modules` each 1 s poll, so converter modules are covered; `--no-watch`
  opt-out). Browser still needs a manual F5 after restart, as scoped.
  Live-verified end-to-end; +33 tests.

### 29. `stage_slice_scripts` existence check is blind to engine-defined labels

Found 2026-08-09 while rebuilding CH02. `stage_slice_scripts.py --write` exits
1 with `FAIL: 2 undefined script reference(s): BerryTreeScript,
Common_EventScript_FindItem`. Both labels are real and vanilla —
`engine/data/scripts/berry_tree.inc:1` and
`engine/data/scripts/item_ball_scripts.inc:1` — but the dangling-reference check
(`stage_slice_scripts.py:560-585`, `asm.find_dangling_references`) builds its
defined-set from staged `.pory` text plus the dispatchers and CommonEvents only.
Any map.json object script pointing at an engine-provided label therefore reads
as dangling by construction.

Pre-existing, not caused by the trainer-pacing change: the already-shipped
`engine/data/maps/Route01/map.json` carries 10 such references, so every CH02
build since berry trees and item balls landed has exited 1 here. Not a build
blocker — `assemble_pathfinder` and `make modern` are separate steps with their
own fork-index gate — but it is a **loud check that is now routinely ignored**,
which is exactly how a real dangling reference gets waved through.

Fix: feed the check an engine-defined label set (scan `engine/data/scripts/*.inc`
for `^Label::`, the same way the fork-capability index is built per CLAUDE.md
§4.7) and only report labels defined in neither place. Do not special-case these
two by name.

**FIXED 2026-08-09.** New `assembly.engine_defined_labels(engine_root)` harvests
`^Label::` (double-colon only — a scan of every script reference in the vendored
tree found zero targeting a single-colon label, which the engine uses for text
and movement bodies) and `find_dangling_references` grew an `engine_defined`
parameter unioned into the defined-set, defaulting to `None` so no other caller
moved. `stage_slice_scripts` passes it using the engine root it already had.
4924 labels; fail-loud floor at 100, because a silently-empty scan would restore
the exact false-negative the function exists to kill. Exits 0 now.

**The scan scope is the load-bearing part.** The obvious glob `data/**/*.inc`
also matches `engine/data/maps/<Map>/scripts.inc` — per-map output assembled from
*our own* staged `.pory`, blanket-gitignored at `.gitignore:124`. Trusting that
would let a stale artifact from a previous build vouch for a label the current
staging no longer emits, which is a worse failure than the one being fixed: a
dropped script would pass the gate. Scope is therefore `data/scripts/**/*.inc`
plus top-level `data/*.s` / `data/*.inc`, excluding `data/maps/**` and
`data/layouts/**`. Including the generated trees inflated the count from 4924 to
23290 — a useful smell if anyone re-widens it.
`test_engine_defined_labels_excludes_generated_per_map_scripts_inc` pins it.

**The false alarm was not harmless — it silently skipped staging.** `main()`'s
`--write` block (`stage_slice_scripts.py:602-606`) sits *after* the existence
check's `return 1` (`:592`), so a failing check writes **no** `.pory` to
`output/uranium-build/staging/scripts/` at all. `assemble_pathfinder` then runs
off whatever `.pory` a previous run left there while happily picking up fresh
map.json/layout data from its own path. Every CH02 build since berry trees
landed was therefore a mixed build: current map data, stale scripts. Caught
2026-08-09 when ROM `5d4a7622` (built through the failing gate) and `360e8506`
(built after the fix) differed by 160 bytes from a change that touches no
emitted content; `360e8506` reproduces byte-identically across repeat runs, so
the pipeline is idempotent and `5d4a7622` was the anomaly. Fixing the check
closed this by making the gate pass, but the ordering is still a trap — a
genuine future failure would skip the writes the same way. Worth making the
write unconditional (or the failure an exception) so a red gate can never leave
a half-staged tree behind; not done here.
