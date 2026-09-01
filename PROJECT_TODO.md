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

### 31. Give the Pokédex Uranium's real Tandor regional dex

**User decision 2026-08-11: wanted, not deferred.** The current dex is
National mode with the staged Uranium species grafted onto the end of the
vanilla national list, past `NATIONAL_DEX_PECHARUNT`. That was the minimum fix
to stop caught species being invisible (#see 2026-08-11b, `f3af5820`) and was
taken as an explicit stopgap. Uranium's own dex is the **Tandor regional dex**,
and that's what the ROM should show: Tandor numbering, Tandor ordering, no
vanilla species interleaved.

**The source data is already parsed.** `pbs_converter/pokemon.py:259
parse_regionals` reads `Data/regionals.dat` and returns
`out[0][species_id]` = the Tandor dex number for that species (0 = no entry);
Uranium has exactly one regional dex, 202 species-slots including the ID-0
placeholder. Nothing currently consumes it.

**The engine lever** is `RegionalToNationalOrder` (`src/pokemon.c:5261`), which
indexes `sHoennToNationalOrder` (`src/pokemon.c:392`, sized
`HOENN_DEX_COUNT - 1`); `CreatePokedexList` walks `i < REGIONAL_DEX_COUNT` and
maps through it (`src/pokedex.c:2194-2218`), and `NationalToRegionalOrder`
(`:5222`) is the inverse. So a Tandor dex means generating a
Tandor→national order table plus its count, in place of the Hoenn one, behind
the usual sentinel-fenced generated-header hook.

**Open questions to settle before building it:**
- Whether to keep National mode available at all as a second dex mode (vanilla
  species are still in the ROM and catchable in principle), or make Tandor the
  only dex and revert the `special(EnableNationalPokedex)` from the grant at
  `transpiler.py:2634`. Reverting it is only safe once regional covers every
  staged species — otherwise this bug returns.
- The dex UI names the mode "HOENN" in several strings and uses
  `gPokedexBgHoenn_Pal` vs `gPokedexBgNational_Pal` (`src/pokedex.c:2154`);
  decide whether to retheme or leave the vanilla labels.
- Only 24 species are staged today, so a full Tandor table will have holes
  until the species set grows. Needs a rule for unstaged entries — most likely
  the same fail-loud-or-omit choice the rest of the pipeline makes, not a
  silent gap.

**Done looks like:** the in-game dex lists Tandor species in Tandor order with
Tandor numbers, generated from `regionals.dat` rather than hand-authored, and
a caught species appears at its real Uranium dex number.

### 32. Priority-1 layer rule needs a south-neighbour refinement before the crop-field maps

**Shipped 2026-08-12 (CH02 tree-tops fix, see CH02_TODO #16): a p==1 column now
gets `LAYER_NORMAL` when the column is passable, `LAYER_COVERED` when blocked.**
That honours the stand-on half of RMXP's row-relative p==1 (walk behind the tree
canopy) and keeps the stand-south half (head not covered by a cliff/hedge lip)
wherever the art is solid. It is a pure function of the column key, so metatile
budgets are untouched.

**Where it is knowingly wrong:** a *passable* p==1 cell whose SOUTH neighbour is
also passable. The player can stand south of it, and their head is then occluded
by art RMXP would have drawn under them. Corpus census (all 199 maps,
`layout.column_blocked` rule):

```
flipped to LAYER_NORMAL   9554 cells over 142 maps
of which south-passable   6531 (68.4%)
Map187 1961 · Map117 1868 · Map163 1366 · Map121 815 · Map028 273 · rest <60 each
worst tiles: ts30/ts50 463 + 471 = 11 902 of the 6531 cells' p1 tiles
```

Tiles 463/471 are **tall wheat/crop field** art — big walkable fields where every
cell is passable, so the south neighbour always is too, and the art is full-tile
height. Under the shipped rule the player's head is buried in wheat on every step
through those four maps. In CH01+CH02 the same defect touches only 5 cells (the
Map033 stump shoulders + one Map032 bush) and was accepted for the CH02 gate.

**The refinement** is "flip only if the south neighbour is blocked" — exact RMXP
for every reachable state. That is *cell* context, not column context, so a column
used both ways in one map needs a per-cell metatile copy. Budget matters: ts1033
ships with 2 spare metatiles. Do the copy-cost census before committing to it.

**Due:** before Map117 / Map187 / Map163 / Map121 / Map028 enter a chapter (all
Act 2+). Not urgent for the current frontier.

### 33. Auto-derive ledge jump directions from RMXP passage bits — DONE 2026-08-24

*Migrated from `CH02_TODO.md` #1 on the CH02 gate pass 2026-08-12. **Closed
2026-08-24** during CH04's approval wait. Full derivation table + ts22
inventory: `reference/archive/CH02_TODO.md` #1.*

**Resolution.** `terrain_tags.column_behavior` derives the direction from the
passage byte's low nibble; `ledge_directions` stays empty and is now purely an
escape hatch. Sole clear bit -> `MB_JUMP_*` (0x08 south / 0x01 north / 0x02
east / 0x04 west); 0x0F is a plain wall, silent; >=2 clear bits warns once and
falls back to `MB_NORMAL`. The four `MB_JUMP_*` values resolve once at
construction and fail loud if the fork lacks one. Suite 2358 passed / 19
skipped. Derived directions reproduce the archive's hand-verified ts22
inventory exactly (0x07/0x0B/0x0D/0x0E -> S/W/E/N), and map 35's 16 tag-1
cells all derive `MB_JUMP_SOUTH` with zero ambiguity. **Caveat:** no ROM has
been built with this yet, **and CH04 will not clear it** (user, 2026-08-25):
map 35's 16 tag-1 cells all sit on the far side of the rockslide, which is
geometrically impassable until Rock Smash arrives, so CH04 *builds* the derived
ledges but cannot reach them — the boot-walk gate will pass without any ledge
ever being jumped. First real hardware proof therefore waits on the chapter that
opens the rockslide; do not read CH04's green gate as validating this item, and
do not register a CH04 beat for it. `reference/archive/PATHFINDER_FINDINGS.md:106` mislabels tiles 840-842
(0x0E) as a south ledge; it is north. Left unedited as archived history.

Ledge directionality is fully recoverable from data already deserialized —
Essentials never stores a jump direction, so the tile's 4-dir passage bits are
the whole story (sole clear bit = the jump direction; 0x0F = pure wall). Rule:
0x08→`MB_JUMP_SOUTH`, 0x01→`MB_JUMP_NORTH`, 0x02→`MB_JUMP_EAST`,
0x04→`MB_JUMP_WEST`; 0 clear bits → `MB_NORMAL` silently; ≥2 → warn +
`MB_NORMAL`. The empty `ledge_directions` override in
`reference/terrain_tag_map.json` stays as an escape hatch and wins over the
derivation — do not grow it.

**Where:** `tileset_converter/terrain_tags.py` `column_behavior`, deriving when
the override table misses. Tests in `tests/test_terrain_tags.py`: one per
direction + blocker + ambiguous + override-wins. **Verify:** Route 01's six
warning tiles resolve without hand entries, and Map032's ~30 south-ledge
over-block cells become jumpable in-game. Until it lands, builds keep firing 3
benign warnings for ts22 tiles 840/841/842 (the Moki pond-dock front, where
`MB_NORMAL` and `MB_JUMP_NORTH` behave identically anyway).

### 34. Secondary-tileset animation support

*Migrated from `CH02_TODO.md` #2 on the CH02 gate pass 2026-08-12.*

Still open, still not blocking: animated tiles currently must fit the 512-tile
PRIMARY partition. ts1033 (Route 01) sits well inside it at 131 animated tiles.
The secondary-callback variant is only forced when ts28's maps reach the
frontier (543 animated tiles). Detail: `reference/archive/SLICE1_TODO.md` #10.

Related, and owed to a §9 walk rather than a code change: Route 01's transparent
waterfall autotile quantized cleanly and has passed a still-frame eye gate, but
has **never been looked at in motion on hardware**.

### 35. Uranium-original moves silently absent from staged learnsets

*Migrated from `CH02_TODO.md` #11 on the CH02 gate pass 2026-08-12; user-ruled
accepted debt, not a defect.*

`species_converter.stage.emit_learnsets` gates every level-up move against the
fork's real `MOVE_*` constants and DROPS the entry when the fork has no such
move (loud warning + a `dropped_learnset_moves` record in
`species_manifest.json`). CH02 dropped 3 entries, all `MOVE_METAL_WHIP` (Uranium
move id 562): BAREWL @29, DEAREWL @29, GARAREWL @31. Nothing invented, nothing
silent — those three Pokémon are simply missing a level-up move until Uranium's
move set is staged into the engine, a much larger unit than any chapter needs.

### 36. Map033 EV028 "Luz" stripped — revisit if an additive-glow path exists

*Migrated from `CH02_TODO.md` #12 on the CH02 gate pass 2026-08-12; user-ruled
strip 2026-08-05, recorded here so the reference survives.*

An RMXP ambient-lighting event: one page, trigger 0, empty command list, graphic
`light` = a soft alpha-gradient yellow glow circle. GBA 4bpp has no additive
blend and a smooth gradient bands badly at 15 colours. Recorded in
`reference/strip_list.json`'s `map_events` (with an `expect_name` renumbering
guard); `build_object_events` honours that list and drops the event before any
graphics lookup, so its sheet needs no `npc_gfx_map.json` entry. This is the
first live entry in `map_events` — the deterministic path never read that array
before (only the retired LLM orchestrator did), so the plumbing landed with it.

### 37. No sweep for engine map dirs orphaned by a past rename

*Found 2026-08-12 during the CH03 build; the drift half is fixed, the debris half
is not — see `CH03_TODO.md` #7/#14.*

`MapConstantRegistry.mint()` now re-mints on identity drift, so a
`map_name_overrides.json` edit is no longer silently ignored. Nothing, however,
cleans up what a rename leaves behind: `engine/data/maps/<OldName>/` and
`engine/data/layouts/<OldName>/` survive with a `map.json` naming a layout
constant that no longer exists.

That is **fatal, not cosmetic**. `mapjson` refuses such a dir ("Failed to find
matching layout for LAYOUT_X"), therefore never writes its `connections.inc`, and
make then dies with `No rule to make target
'data/maps/<OldName>/connections.inc'` — an error naming neither the rename nor
the stale directory. Two orphans (`MokiTownTheo`, `MokiTownTheo172`, from maps
172/89's rename to `MokiTownTheosHouse1F/2F`) had been sitting in the tree
undetected until a full mapjson pass finally touched them.

Wanted: the assembler compares engine map dirs against the layout manifest it
just generated and fails loud (or cleans) on any whose layout constant is
absent. Cheap — a scratch version of exactly this check found both orphans in
one pass, and confirmed there are no others today.

### 38. Common-event calls had never assembled (fixed) — but nothing gates the syntax

*Fixed 2026-08-12 (`CH03_TODO.md` #12); logged here because the class of bug is
corpus-wide, not CH03-specific.*

The transpiler emitted `call CommonEvent_004`. Poryscript has a bare `goto Label`
keyword but no bare `call Label`, so that parsed as two bare commands and
assembled into `call` (no operand) plus a stray `CommonEvent_004` instruction.
Every common-event call the pipeline has ever emitted was broken; it went
unnoticed only because CH01/CH02 call no common events, and map68 is the first
map that does.

The fix is one character class at two emit sites. What is still missing is a
**gate**: the fork-capability index validates specials/macros/constants the
pipeline emits, but nothing validates that emitted *Poryscript* is syntactically
what we think it is — a command that silently degrades into two bare commands
passes every check we have until the assembler chokes 20 minutes into a build.
Worth a cheap post-transpile lint over emitted `.pory` (known command names,
parenthesised argument forms).

### 47. `kevlar.py` B25 asserts the Kevlar↔Route 2 seam is BLOCKED — now stale

Migrated from `CH04_TODO.md` on the CH04 §9 gate pass (2026-08-27).
`src/rpg2gba/playtest/chapters/kevlar.py` B25 was written when Route 2 had no
entrance; `connections.py` landed in CH04 and the seam now crosses live (CH04
B1 walks it). B25 still passes only because it asserts the *south row 56*
collision run, not the seam itself — confirm that reading, then flip the beat
to assert a working crossing. It is CH03's file, so this is a deliberate
cross-chapter edit, not drift.

### 48. CH04 residual harness gaps — B10 and B15

Migrated from `CH04_TODO.md`. `route2.py` registers 13 of 15 beats.
- **B10** (Larrie's rematch *offer*) needs a PokeNav/Match-Call driver and a
  self-switch setter the emulator harness does not have; recorded in
  `DEFERRED_BEATS`, not dropped. Same driver would unblock the wider
  match-call rematch surface.
- **B15's two grass cells** are inferred coordinates, not decoded from the map;
  flagged in `route2.py`'s docstring. Settle on the next Route 2 build.
  (B1's Kevlar-side approach column was decoded to x=31 during the 2026-08-26
  run — that half is closed.)

### 49. Playtest checker: capability model (Q3) and rule-set versioning (Q7) still absent

Migrated from `CH04_TODO.md` "Carried, not blocking".
- **Q3 capability model** is unbuilt, so `checker.py` rule 7
  (`deferred_no_granting_chapter`) cannot enforce CH04's 5 `rock_smash`
  deferrals — they pass on a `capability_model_unenforced` warning. Operator
  decision 2026-08-22: accept warnings for now. CH06 is the grant chapter per
  `reference/chapters.json`; enforcement matters most once CH06/CH07 land.
- **Q7 rule-set versioning** is designed but absent from `checker.py` — no
  rule-set version field, so no gate stamp records one and no lag report can
  be generated. (`reference/playtest_rule_versions.json`, added 2026-08-27,
  versions the *playtest harness* beats, not the manifest checker.)

### 50. `isRockSmashSoftlocked` is an unrecognized script head on map 32

Migrated from `CH04_TODO.md`. Last unrecognized head in CH01's map-32 fixture;
out of CH04's scope but filed so it is not rediscovered. Rule it (or its
containing page) when CH01's interiors or the Rock Smash grant chapter is next
touched.

### 52. Route 2 Poké Radar catch-table entries missing from `wild_encounters.json`

Migrated from `CH04_TODO.md` (`reference/chapters/04-route-2.md` §5, item 3).
The Route 2 wiki page lists a Poké Radar division (Dunsparce, Tofurang) that is
absent from `wild_encounters.json`. Data gap, unresolved — Poké Radar is not an
engine feature the pipeline models yet, so this is a "when Radar lands" note,
not a CH04 miss.

### 57. 12 unmodelled walked legs still owed a per-chapter re-check

*Filed 2026-08-29 out of the corpus-wide world-graph audit
(`src/rpg2gba/traversal/world.py`, `python -m rpg2gba.traversal world`) that
closed Q13 slice 1 (`PLAYTEST_AUTHORING_IMPROVEMENT_V2.md`) — 199 maps, 1108
edges (1076 warp, 28 connection, 4 seam_warp) against the 14 overland rows
`connections.json` was originally authored with. The audit walks each
chapter's predecessor chain (shortest path, predecessor `outdoor` map →
chapter `outdoor` map) and reports transit maps belonging to neither chapter.
It found 14 unmodelled legs; CH07→CH08 is fixed today (new chapter `CH07A`
"Route 1 (revisit)" in `reference/chapters.json`). The remaining 12 all cross
maps some *earlier* chapter already covers — e.g. CH25→CH26 crosses Rochfale
Town (12) and Route 6 (22); CH37→CH38 and CH38→CH39 cross Route 07 (8),
Route 08 (117) and Route 11 (140); CH58→CH59 crosses 10 maps including both
Burole and Bealbeach metro pairs. Whether any of them strand content depends
on whether the leg newly unblocks rows dispositioned `blocked:` there, which
needs per-chapter dispositions — `reference/manifests/` only covers CH04
today (§43a). So the re-check is owed once a chapter acquires a manifest, not
now, and it's mechanical: re-run the audit, and for each transit map ask
whether the capabilities held at that leg unblock any `blocked:` row on it.
The audit script lives only in a scratchpad today; promote it into
`src/rpg2gba/chapter_atlas/` as a real subcommand (e.g. `chapter_atlas legs`)
so it's re-runnable rather than re-derived each time.

### 58. Map 183 "Rochfale Town" is unreachable but bound to CH14

Filed 2026-08-29, same world-graph audit as §57. Map 183 has 8 outgoing warps
and zero incoming edges in the full 199-map graph — the player can never walk
into it. Rochfale Town has several same-named maps (12, 92, 93, 104, 130,
183); 183 looks like a dangling RPG Maker editor duplicate. CH14's roster
needs verification against the graph before CH14 is built: either 183 is
genuinely dead content and belongs in `unbound_maps`, or one of the other
Rochfale maps warps into it by a route the graph missed.

### 59. Map 999 sits outside the coverage identity entirely

Filed 2026-08-29, same world-graph audit as §57.
`output/uranium-build/maps/Map999.json` exists but has no `map_infos.json`
entry, so it's invisible to the "187 bound + 11 unbound = 198" coverage
assertion and has no graph edges. Decide whether it's a decoder artifact, an
editor leftover, or real content, then either give it an `unbound_maps` entry
or stop emitting it.

### 60. Four `unbound_maps` entries have live edges into the playable graph

Filed 2026-08-29, same world-graph audit as §57. 51 (Intro) → 48, 57; 57
(Nuclear Plant) → 48; 94 (Mapa intro) → 14, 95; 95 (Intro 2) → 14. "Declared
unbound" and "disconnected from the playable graph" are currently the same
claim in `unbound_maps`, but these four show they aren't. The bindings are
probably still correct (pre-title/cutscene maps), but the reason strings
should say so explicitly, and `chapter_atlas coverage` could assert the
distinction instead of leaving it implicit.

### 61. Kevlar Town (31) + Passage Cave (19): 10 deferrals held past CH25, one mis-triaged

Filed 2026-08-29, same world-graph audit as §57. No leg in the 59-chapter
chain re-crosses Kevlar Town at or after CH25 — it's Fly-only from there. Its
10 deferrals are Strength ×7 (HM04, granted at CH25 Route 11), Bike Wheel ×1
(CH11), a post-Gym-5 story flag ×1, and B26, whose dev-only flag `sw130` /
`FLAG_FILE_RECOVERY` is never set anywhere in the corpus — a mis-disposition
owed a re-triage from `deferred` to `unreachable`. Operator decision
2026-08-29: record this as a countable hold and settle it when CH25 actually
reaches the frontier, rather than minting a revisit chapter now. B26's
re-triage is the one piece actionable immediately, independent of CH25.

### 63. CH04 owes two negative beats — `map035/ev014/p1` and `map035/ev017/p1`

Surfaced by slice 2's new `blocked_missed_assertion` checker rule, which is the
first thing in the repo able to see this class at all. Both rows are the
*cleared* pages of the two Route 2 boulders whose approach the player can already
reach unaided, so a negative beat is writable today: walk up, press A, assert the
refusal. `ev014/p0` and `ev017/p0` already carry `negative_beat: "B6"`; their p1
siblings carry none.

Not urgent and not a defect — CH04 passed its §9 gate and the rule is explicitly a
missed-opportunity warning, not an error. Right time to spend it is CH07A, the
Rock Smash revisit that walks map 35 again. Until then `check --chapter CH04`
reports 2 warnings of this kind by design; do not silence them.

### 64. `CapabilityModel.grants_capability` is the wrong signature — 28 warnings standing

`check --chapter CH04` emits 28 `capability_model_unenforced` warnings because no
capability model is supplied, and none can honestly be written against the current
Protocol. `grants_capability(name) -> chapter_id | None` assumes a capability is a
boolean granted by exactly one chapter. The Part 4c census
(`PLAYTEST_AUTHORING_IMPROVEMENT_V2.md`, "AMENDED 2026-08-27") found otherwise:
capabilities are **predicates over player state**, and Uranium grants every field
move by **two disjoint routes** — `rock_smash` is `numbadges >= 1 AND (knows
ROCKSMASH OR holds BOXINGGLOVES)`, and the same move-or-gadget shape holds for
strength/`POWERGLOVE`, surf/`SURFBOARD`, dive/`SCUBAGEAR`, waterfall/`CLIMBINGPICK`,
with all five gadgets granted from one event (Map167/ev28) on a badge-count ladder
at a different point in the game than the HMs.

Some gates are also not derivable at all: `old_rod` sits behind `var[103] >= 5`,
and variable 103 is named "Battle Var01" — the only artifact stating what it means
is the dialogue text, so a name-keyed classifier misses it *confidently*. The
redesigned model must therefore accept hand annotation.

Deliberately left standing rather than papered over with a model that would answer
confidently and wrongly. The sibling rule `approach_model_unenforced` is now down
to 1 row (the seam, which has no event cell) because that half **was** derivable —
see `chapter_manifest/approach_model.py`.

### 65. CH01–CH03 manifests no longer load — `reachability_consulted` is a required field

Slice 2 added `ManifestRow.reachability_consulted: bool` (`chapter_manifest/schema.py`),
and `row_from_dict` does a strict field-set equality check by design — a missing key
fails loud with "regenerate the manifest rather than patching it". CH04 was regenerated
as part of the slice; `CH01.manifest.json`, `CH02.manifest.json` and `CH03.manifest.json`
were not, so any `chapter_manifest` command pointed at those three (`check`, `render`,
load) now hard-fails on the first row.

The same break applies on the disposition side: the `deferred:` verdict and the
geography-flavoured `unreachable:<reason>` arguments were removed from `_VERDICTS` in
favour of `blocked:<set>`, so an un-migrated dispositions file fails `Disposition.parse`.
Only CH04 has a dispositions file today, and it was hand-migrated.

This is the intended fail-loud shape, not a defect — but it is an unacknowledged schema
break on three gate-closed chapters, and a bystander running `check --chapter CH02` gets
a crash with no other clue. **Remediation:** regenerate CH01–CH03 manifests once the
per-(chapter,map) verified start cells exist for their maps (`_CHAPTER_MAP_START_CELLS`
in `generator.py` currently covers CH04 only), and diff the result before committing —
regenerating a gate-closed chapter's manifest is not a no-op edit.

*Found 2026-08-30 during the slice-2 commit review.*

### 67. No chapter routed so far carries a route plan, and CH01-CH03 cannot get one

Slice 3's `RULE_ROUTE_ORDER` only enforces anything when
`reference/routes/<chapter>.route.json` exists; with no plan on disk
`build_route_model` returns None and the rule degrades to its
`route_model_unenforced` warning. **No route plan is committed for CH01-CH04**,
so the rule is unenforced for every chapter gated to date. Two separate
reasons, and only the second is a defect:

1. **CH01-CH03 cannot be solved at all.** Their manifests predate slice 2 and
   are missing `reachability_consulted`, so `load_manifest` refuses them
   ("regenerate the manifest rather than patching it") before the solver
   sees a single beat. Regenerating a gate-closed chapter's manifest is
   itself #65, so this is blocked behind that, not behind routing.

2. **CH04 solves, but its plan disagrees with its registered order.** The
   solver walks `B1 B15 B4 B9 B7 B3 B12 B5 B6 B13 B11 B2 B14` for 112 tiles;
   `route2.py` registers `B1 B4 B14 B2 B3 B5 B6 B7 B9 B11 B12 B13 B15`,
   which the solver's own cost model scores at 130 tiles. **Both orders are
   entirely free of foreign-trigger crossings and neither has an unroutable
   segment** -- measured 2026-08-30, not assumed. So the 18-tile gap is pure
   walk distance: the registered order is suboptimal, not wrong, and nothing
   about CH04's passed gate is invalidated by it.

   Committing `CH04.route.json` as-is would therefore turn `check --chapter
   CH04` red over a cosmetic reorder of a closed chapter. Not done.

**Consequence: slice 3 is validated forward, from CH05, not retroactively.**
This is the one place slice 3 differs from slice 2, whose retroactive
re-derivation over CH01-CH04 was an explicit part of its build
(`PLAYTEST_AUTHORING_IMPROVEMENT_V2.md`, "Validation -- CH05 is not
sufficient evidence"). Slice 3 has no equivalent, and the reason is
structural: slice 2 re-derived a *fact about the world* that a gated chapter
already recorded the right answer to, whereas slice 3 proposes an *ordering
the operator has to approve* -- there is no pre-existing approved route to
re-derive, because ordering was convention until now.

What slice 3 does get instead is the CH04 B2/B3 incident as a worked case:
the plan puts B3 at position 5 and B2 at position 11, while the chapter
registers B2 at 3 ahead of B3 at 4. That is exactly the inversion whose
un-checked walk crossed Timothy's event-touch tile and fought the wrong
trainer, and `RULE_ROUTE_ORDER` reports it as an error. The rule would have
caught the original incident.

**Remediation:** solve and commit CH05's plan as part of CH05's authoring
loop, where the operator approves the route before the chapter module is
written and the two agree by construction. Revisit CH04 only if #65 reopens
it for another reason -- do not reorder a gated chapter's beats to satisfy
this rule on its own.

*Found 2026-08-30 finishing slice 3.*

**Widened 2026-08-30 by slice 4.** The same absence now leaves a second rule
unenforced. `compare_walk` reports `compared: false` for every chapter, so the
trigger-divergence check that would have caught CH04's B2/B3 incident cannot
fail anything either. Same remediation, same chapter: committing CH05's
approved plan turns on `RULE_ROUTE_ORDER` *and* runtime divergence enforcement
together, and neither one is on before that. Slice 4's non-enforcing halves —
the walked path, Q8's ledger, the frame rule, the conformance report — do not
wait on a plan and are live now.

### 68. Nothing pins slice 4's frame-rule phrase list to the harness's own text

`playtest/frame_rule.py` classifies a beat's failure message as a negative
claim by regex over an explicit phrase list, several entries of which were
derived by grepping the harness's current `ScenarioError` strings. Nothing
keeps the two in step: a future beat that phrases a negative claim a new way
("the flag was never set", say) is silently not covered, and the rule's
conservative bias means that failure mode is quiet by design — it prefers
missing a negative claim over refusing an unrelated failure.

This is accepted, not a defect: the escape hatch is that any author can
satisfy the rule with one `mark_frame()` call, and a false refusal is more
expensive than a miss. Worth a re-grep of `src/rpg2gba/playtest/` for new
negative-claim phrasings whenever a chapter adds a batch of beats.

*Found 2026-08-30 building slice 4.*

### 69. A green test run writes synthetic chapter names into a tracked reference file

`run_chapter` records the rule-set version of every chapter that passes into
`reference/playtest_rule_versions.json`, and the runner's unit tests pass with
synthetic chapters (`t1`, `t2`, `t9`, and now slice 4's `v4path`, `v4noplan`,
...). Those names are already committed in that file from earlier runs, and
every `pytest tests/test_runner*.py` adds any new ones, so the file shows up
dirty after a plain test run and `rules-lag` reports chapters that do not
exist.

Cosmetic, but it makes `git status` lie after a test run, which is the kind of
noise that trains an operator to ignore a dirty tree. The fix is for the tests
to point the recorder at a `tmp_path` (the runner would need to accept the
state path, or the tests would need to monkeypatch `rules._STATE_PATH`), plus a
one-time cleanup of the synthetic names already committed.

*Found 2026-08-30 building slice 4; the leak itself predates it.*

### 70. The test suite writes into tracked `reference/playtest_rule_versions.json`

Running `pytest` mutates a committed §4.3-adjacent reference file. Observed
2026-09-01: a full suite run added a `"CH03": 2` key to the working tree with no
test asking for it, and the file already carries `kevlar3`, `t1`, `t2`, `t4`,
`t5`, `t9`, `t10`, `t12`, `t13`, `v4conformance`, `v4noplan`, `v4offplan`,
`v4path`, `v4perbeat`, `v4v1fields` — every one of them a test fixture's chapter
name that leaked in the same way and was then committed.

Some test calls `rules.record_chapter_version` (or drives a runner that does)
against the real default path instead of a `tmp_path`; `tests/test_observed_beats.py`'s
`run_chapter` fixture is the confirmed one. It used to be merely untidy, because
fixture names like `t1` and `v4path` could never collide with a real chapter.
**The #66 rename made it worse:** fixtures now name themselves `CH03` to match
the production convention, so a leaked write lands *on a real chapter's key* and
silently overwrites its recorded rule version instead of sitting beside it as
obvious junk. That turns a cosmetic leak into a data-corruption path, and it is
the reason this is filed rather than tolerated further. The file cannot be
trusted as a record of which chapters were gated under which rule version, which
is the one thing it is for.

**Remediation:** find the writer that misses the `tmp_path` fixture, pin the
default path behind a fixture that fails if a test touches it, and delete the 15
leaked fixture keys in the same commit.

*Found 2026-09-01 while migrating the file's keys for #66.*

## Parked until the CH05 branch is cut (do not raise before then)

These are real, tracked work items, scoped entirely to CH05. They are not open
questions and not blockers on any work that precedes CH05. **Operator
instruction, 2026-08-29:** stop raising them in status reports or "what's
next" summaries — they were being resurfaced every session even though the
call on when to act on them is deliberately deferred until CH05's branch is
open and the chapter is actually in front of him (this project cuts branches
for chapter builds only; everything in between commits straight to main).
Nothing here is decided or dropped by being parked. `reference/chapters/
05-passage-cave.md` §7 is the chapter-local home for the same items; that
section and this one must stay in sync. **Trigger to unpark: the CH05 branch
is cut.** At that point this whole section becomes the CH05 build's opening
worklist.

### 51. Q5.1 citation-verification experiment — run across CH04 + CH05

Migrated from `CH04_TODO.md`. A blind second-agent pass over citation-triggered
disposition rows only, scoped to run on CH04 and CH05; kept as standing
practice if it catches at least one silent pass across both chapters. CH04's
pass is done; **CH05's pass, and the decision it feeds, wait on the CH05
branch being cut.**

### 62. CH05-scoped items scattered across `PLAYTEST_AUTHORING_IMPROVEMENT_V2.md` Part 5 with no tracked home

Filed 2026-08-29 out of an audit of `PLAYTEST_AUTHORING_IMPROVEMENT_V2.md` Part 5
(the CH05 dry run) that found several concrete findings never landed in either
this file or `reference/chapters/05-passage-cave.md` §7. Parked here as CH05-build
work, not open questions:

- **The arrival-nudge autorun archetype is missing from Q0's Tier-1 template
  build set entirely** (§5.6). Fingerprint `map036/ev002/p1` — autorun trigger,
  `get_character(0).onEvent?` branch, `setTempSwitchOn` tail, player nudged one
  tile off the arrival cell — is byte-identical to CH04's `map035/ev001/p1`
  (`beat:B8`), and a corpus census puts the idiom at **324 instances across 73
  maps**, bigger than the item ball (243), staircase (222) and cave-exit (102)
  archetypes combined and second only to the door/warp event (996). It belongs in
  Tier 1, and CH05 needs it authored before its beats can be written.
- **TM76 and Sableyeite sit in a Surf-sealed 30-tile room** (§5.7): Map036 has 513
  walkable tiles in 7 connected components, 450 reachable on foot from the
  entrance, but the room at bbox x 31-36/y 11-16 opens only into a water pocket
  disconnected from the walkable region. Both pickups are `blocked:surf`, and
  Surf is granted at Map143 (Act 5) — the longest capability deferral found in the
  corpus so far. `05-passage-cave.md` B6/B7 must be authored as deferred beats
  (the CH02/CH04 `DEFERRED_BEATS` idiom), not live beats: a second, much longer
  arm on the stranded-revisit backlog alongside the Rock Smash one (§39/§57).
- **The standing guardrail that a green CH05 §9 gate is NOT evidence** that
  slice 2, the capability model, or the mart/Poké Center/PC templates are correct
  (§5.8, restating Q13). CH05 exercises zero seam rows, zero populated
  `requires[]`, zero mart/Center/PC instances, and its only `blocked:` rows are
  terrain-derived Surf, not switch/variable-derived — the least-representative
  possible confirmation. Their real validation is the retroactive re-derivation
  of CH01-CH04.
- **The decided-but-unbuilt re-disposition of the whole built corpus during
  CH05's build**, with its ordering safeguard: freeze the expected answers,
  derive, diff, then write — do not derive-and-write in one pass, or a
  regression in the derivation logic reads as a correct re-disposition. Cross-
  referenced by `PLAYTEST_AUTHORING_IMPROVEMENT_V2.md` §5.6, §5.7, §5.8, Q3 and
  Q13.

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

### 69. `chapters.json` credits CH30 with the HM03 Surf grant; the corpus says map 143

Found while building B2 (2026-09-01). `reference/chapters.json`'s CH30 (Amatree
Town, maps 151/170/171/69) carries the note *"the HM03 Surf grant -- the single
largest traversal unlock in the game."* The decoded corpus does not support it:
scanning all **199** decoded maps, `Kernel.pbReceiveItem(::PBItems::HM03)` occurs
on **map 143 only** — events 22 (`'the event'`, 27,46) and 24 (`'theo event2'`,
27,47). Map 143 is not in CH30; it belongs to **CH29** (Route 10 / Anthell, act
A5, visit 1) and **CH31** (Route 10 revisit, act A6, visit 2).

This matters beyond tidiness: it decides which chapter owns the Surf revisit debt
CH05 just acquired (its four `blocked:surf` rows on map 036). Owed to a Route 10
chapter, not to Amatree Town.

**Not fixed here on purpose.** Correcting the factual claim is one thing; deciding
*which* chapter owns a capability grant is a chapter-assignment call (CLAUDE.md
§10, "any decision about Uranium content fidelity"), and CH29-vs-CH31 is a real
choice — the grant sits on a map both chapters contain. Needs the atlas
maintainer. Evidence is recorded in
`reference/frozen/ch05_surf_expectations.json`'s `granting_chapter` block.


## Done

- **#66 — an atlas chapter id now names its own playtest module** (2026-09-01,
  `CH05_DECISIONS.md` E1). The proposed fix was a `playtest_module` field in
  `reference/chapters.json`; the operator's answer dissolved the field instead
  of adding it — *"should they be named by place? why aren't they named by the
  chapters"*. The four modules were renamed to their chapter ids
  (`moki.py`->`ch01.py`, `route1.py`->`ch02.py`, `kevlar.py`->`ch03.py`,
  `route2.py`->`ch04.py`), so the mapping is the name and there is nothing left
  to record. The old names were an accident of order: CH01-CH03 were written
  before `chapters.json` and the atlas ids existed.

  **`ChapterBuilder`'s name string moved with the filename** (`"moki"` ->
  `"CH01"`), because renaming only the file would have left
  `load_chapter("ch01").name == "moki"` — the same mapping problem one layer
  down rather than gone. That changed the beat-qualification prefixes
  (`moki:B1` -> `CH01:B1`), the observed-beats filenames
  (`observed_beats/kevlar.json` -> `CH03.json`), the contact-sheet stems, and
  the keys of `reference/playtest_rule_versions.json` (migrated in the same
  commit; the four real chapters keep their recorded versions).
  `load_chapter` lowercases its argument, so an atlas id passes through
  verbatim from `chapters.json` and the filesystem still gets a conventional
  lowercase module name.

  **`--module` survives as an override, not a requirement.**
  `routing/__main__.py` defaults it to the chapter id. It is still a separate
  option, and `RoutePlan.chapter_module` is still recorded on every plan,
  because `divergence.load_plan_index_for_module` deliberately joins on the
  recorded value rather than on the naming convention — a convention that holds
  today is not the same as a binding the artifact carries, and the revisit
  chapters (CH07A) are the case where the two will part company.


- **B2 — `blocked:surf` is derived, not asked for** (2026-09-01, CH05
  prerequisite — `CH05_DECISIONS.md` B2, "option 1, but derived from the route
  finder not from you asking a question").

  **The engine already worked; the entry point was switched off.** `surf` has
  been a first-class capability since slice 2 —
  `traversal/capabilities.py`'s `_TERRAIN_TAG_CAPABILITY` maps terrain tags 5,
  7 and 17 to `Capability.SURF` — and the terrain-obstacle route inverts the
  event route correctly (water reads as collision; holding Surf flips it
  passable). What was missing was one table entry:
  `_CHAPTER_MAP_START_CELLS` held CH04 only, so
  `_build_reachability_context` returned `None` for CH05 and **no** row on
  either map could carry a terrain-gated capability.

  **The start cells are derived, not typed.** Each CH05 map is entered by
  exactly one code-201 transfer, so its arrival cell is a fact about the data:
  `Map035` ev001 (20,33) → map 36 **(17,39)**; `Map036` ev002 (17,4) → map 37
  **(16,26)**. Both reproduced with `extract_warp_exits`, and both agree with
  the cell the CH05 dry run used independently. The comment says plainly that
  CH05 has no boot-walk harness yet, so these are stronger than a guess and
  weaker than an observed post-load position.

  **Result, measured:** CH05 generates `requires: ["surf"]` on exactly
  `map036/ev008/p0`, `ev008/p1`, `ev009/p0`, `ev009/p1` — the TM76 and
  Sableyeite item balls in the sealed room at x31-36/y11-16 — and on **no other
  row**; the other 11 map036 page rows and all of map 37 stay clear;
  `reachability_consulted` is now true for every CH05 row. CH04 regenerates
  byte-identical.

  **Guarded by `reference/frozen/ch05_surf_expectations.json` +
  `tests/test_ch05_surf_oracle.py` (5 tests).** The oracle records honestly that
  it is **not** a blind freeze — the derivation predates it and was spot-checked
  during investigation — and names what *is* independent: the sealed-room
  analysis written up in the CH05 dry run before any surf derivation ran. Its
  negative arm is the load-bearing half, since a bug marking the whole map
  surf-gated would satisfy the positive arm alone. Mutation-tested: moving the
  CH05 start cell inside the sealed room turns the end-to-end test red.

  **Still owed, and not in scope here:** authoring the four `blocked:surf`
  dispositions and their deferred beats. The generator only ever populates
  `requires[]`; it never writes a disposition, and `dispositions.py` says that
  separation is the point. Authoring lands in CH05's own build at the new READ
  step, with the derived answer already sitting on the rows. Also unenforced by
  design: `blocked:surf` will raise `capability_model_unenforced` exactly as
  CH04's 28 `blocked:rock_smash` rows do — no `CapabilityModel` implementation
  exists and `chapters.json` has no structured grants field (see #69).

  Suite **2792 passed, 19 skipped** (was 2787/19).

- **D1 + D3 — the coordinate literal ban, and the read-through gets a written
  home** (2026-09-01, CH05 prerequisites — `CH05_DECISIONS.md` D1 and D3, both
  "option 1").

  **D1.** `src/rpg2gba/playtest/cells.py` is the resolver vocabulary a chapter
  author uses instead of typing coordinates: `event_cell`, `approach_to`
  (walkable neighbour in deterministic N/S/E/W order, `prefer=` to pick a side),
  `warp_cell` / `arrival_cell` (both sides of a warp, from
  `MapGraph.warp_exits`), `entry_cell` (reads
  `generator._CHAPTER_MAP_START_CELLS` — one table, not two), and the counted
  escape hatch `raw_cell(x, y, why=...)` which refuses an empty `why`. Ambiguity
  never resolves silently: more than one matching warp fails loud listing every
  candidate. The decision named four resolvers; `event_cell` and `arrival_cell`
  were added because without them the two commonest literal patterns (an
  event's own cell, and post-warp arrival cells) would all have become
  `raw_cell` escapes, which defeats the ban. Per-map graphs are cached keyed on
  the map id, so the resolvers stay idempotent (§4.2).

  **The lint** is `tests/test_chapter_coordinate_literals.py`, AST-walking
  `chapters/*.py` as a pytest test — the shape `tests/test_moki_chapter.py`
  already established for "no hardcoded flag/var ids". It flags four things: a
  bare two-int tuple anywhere, an inline `at=(x, y)`, a `raw_cell` with no
  `why=`, and a `raw_cell` with an empty one. **Grandfathering is a ratchet, not
  an exemption:** `_PRE_BAN_BUDGET` freezes the four pre-ban chapters at their
  measured counts (moki 13, route1 45, kevlar 42, route2 25) and fails if a
  count rises — *and* fails if one drops without the budget being lowered to
  match. Any chapter file not in the budget, CH05 onward, must be at zero. The
  four existing chapters are deliberately NOT retrofitted: that would mean
  editing three gate-passed chapters for no functional gain, and it would give
  them an import-time dependency on decoded output they do not have today.

  **D3.** `BUILD_PLAN.md`'s per-chapter loop gains **READ at position 5**,
  pushing ROUTE to 6 and the loop to 10 steps. It sits there because it needs
  step 4's generated manifest and authored dispositions, and must precede
  ROUTE's operator sign-off — which *is* the approve-before-build gate the
  decision names. Until now the ordering was inverted: the route plan was
  approved on its own, ahead of a read-through with no written home. The
  verdict-correctness checklist and its decaying blind-spot appendix are
  `reference/guides/read_through_checklist.md`, grounded entirely in what CH04's
  informal read-through actually caught (the page-vs-event `cosmetic` definition
  error behind B14, the "Sign" name-vs-content confusion, the B15 encounter
  table). The appendix ships with one worked decay already recorded — diagonal
  staircases came off it the same day B1 landed — and one correction: `dark_map`
  is **still** a live blind spot, because 2026-08-31 wired it into the emitted
  map header, not into the manifest, so no verdict is ever authored about
  darkness.

  Suite **2787 passed, 19 skipped** (was 2767/19). `ruff check` clean on both new
  files; the repo's pre-existing 201 ruff findings are unchanged and untouched.

- **54. `unhandled: 0` was indistinguishable from "map never transpiled"; and
  the four Map037 staircases disposed as `cosmetic`** (2026-09-01, CH05
  prerequisites — `CH05_DECISIONS.md` C1 and B1, both "build the fix").

  **C1.** `ManifestRow.unhandled` is now three-valued: a positive int is that
  many queue entries, `0` means the map *was* staged and this page produced
  none (a measured clean result), and `None` means the map was never staged so
  the queue says nothing at all. `may_be_cosmetic` returns False on `None` —
  unmeasured must not read as clean. The staged set comes from
  `_load_staged_map_ids(build_dir / "scripts")`, i.e. the transpiler's own
  `Map###.pory` output, **not** from the queue's contents: a cleanly-transpiled
  map produces zero queue rows, which is exactly what an unstaged map produces,
  so inferring staged-ness from the queue is the bug rather than the fix. A
  missing `scripts/` dir warns and returns the empty set — nothing can then be
  `cosmetic`, which fails safe. `RULE_ILLEGAL_COSMETIC` gained a third arm
  checked *first* (`None` is falsy and would otherwise fall into the
  state-writing-tags message and misreport the cause); `render.py` prints
  `unhandled: null (map never staged)`.

  **B1.** Diagonal-stair events are absorbed into `kind="terrain"` rows and no
  longer emit a page row at all. Detection reuses
  `tileset_converter.stairs.detect_stair_cells` — no second detector, since the
  layout converter is the single source of truth for which cell gets which
  native metatile behaviour (§4.3). New `TerrainRef(x, y, behavior,
  source_event_id)` beside `SeamRef`, new `terrain` field, new
  `terrain_row_id(map_id, subkind, x, y)` with a `subkind` slot so later terrain
  kinds don't collide with stairs at the same cell. Terrain rows can never be
  `cosmetic`, same as seams.

  Measured on the real corpus: CH05 generates **21 page + 4 terrain = 25 rows**
  (the same 25 the dry run projected — absorbed, not double-counted), all four
  staircases carrying the right side (`map037/terrain/stairs/11,9` and `11,10`
  LEFT, `20,9` and `20,10` RIGHT), no leftover page rows on events 3/6/7/8, and
  **0 of 25 rows `may_be_cosmetic`** where previously every one of them was.
  CH04 still checks 0 errors / 42 rows.

  Adding the `terrain` field broke `row_from_dict`'s strict field-set equality —
  the same mechanism that broke CH01–CH03 when `reachability_consulted` landed
  (#65) — so `reference/manifests/CH04.manifest.json` was regenerated in the
  same change. Diff is exactly 42 `"terrain": null` additions plus the two seam
  rows' `unhandled` moving `0` → `null` (seams never set the field, so they took
  the new default; correct, and they can't be cosmetic anyway). No
  `content_hash` moved, no row added or removed, and a second regeneration is a
  no-op. Suite **2767 passed, 19 skipped**.

- **56. `requires_flash` was a hardcoded `False`; `dark_map` was parsed and never
  read** (2026-08-31, operator ruling, CH05 branch opening) — the content call
  this entry was waiting on came back as "just render it": in Uranium, **Flash is
  not an HM** (level-up move + **TM70**), so the "HM05 has no grant site in 199
  maps" objection was not describing a gate, and a `DarkMap` cave is not pitch
  black in either engine — both light a radius around the player. So the fix is
  the honest wiring, and the fail-loud stub this entry proposed is unnecessary:
  `dark_map` now flows straight to `requires_flash`. `MapFile` gained a
  `requires_flash: bool = False` field serialized in `to_json_dict()`; new
  `_dark_map_for(uid, metadata_path)` reads the parsed metadata beside
  `_map_type_for` (their shared lookup factored into `_metadata_entry_for`,
  behaviour-preserving); both `MapFile(...)` sites in `metadata_wiring.py`
  (`build_slice_maps`, `build_warps_only_maps`) pass it. In the fork
  `requires_flash` becomes `gMapHeader.cave`, and `overworld.c:1106
  SetDefaultFlashLevel()` gives a cave a small lit radius with
  `FLAG_SYS_USE_FLASH` unset, a large one with it set — native Emerald, no
  engine change. Retro-applies to all **25** dark maps in the decoded corpus
  (`{7,10,17,19,36,37,72,74,80,83,96,105,106,118,123,150,162,189,191,192,193,202,
  205,208,213}`), so **CH03's map 19 becomes dark on its next regeneration** —
  the class-P instance that shipped lit through CH03's §9 gate. Tests
  `test_map_json_requires_flash_follows_field` + `test_dark_map_for` in
  `tests/test_tileset_converter.py`; full suite 2758 passed, 19 skipped.
  `05-passage-cave.md` §7.1 item 1 updated. CH05 dry run §5.3.

- **53. Maps 36 and 37 shared the display name "Passage Cave"** (2026-08-31,
  operator ruling, CH05 branch opening) — `map_infos.json` named both floors
  "Passage Cave" and `map_name_overrides.json` recorded both as `"CORRECT — no
  override"`, so the strict (non-walker) path raised `map 37 ('Passage Cave') ->
  MAP_PASSAGE_CAVE collides with already-minted map 36`. The fail-loud was
  working as designed; only the data was missing. Operator named them **Passage
  Cave 1F** (36) and **Passage Cave 2F** (37) — floor labels, the shape map 19's
  "Passage Cave Grott-Hole" set — rejecting the doc's `PassageCave` /
  `PassageCave2` proposal because the bare `2` carries no meaning. Two
  `overrides` entries written with evidence; the superseded `reviewed` verdicts
  keep their original text. `build_map_constants` over {19,31,35,36,37} now
  mints `MAP_PASSAGE_CAVE_1F`/`PassageCave1F` and
  `MAP_PASSAGE_CAVE_2F`/`PassageCave2F` clean. `05-passage-cave.md` §2 table and
  §7.1 item 2 updated. `PLAYTEST_AUTHORING_IMPROVEMENT_V2.md` §5.5.

- **55. Command code 408 (Comment continuation) missing from `_CODE_IGNORED`**
  (fixed `511ef4af`, 2026-08-28) — `generator.py:107` ignored 108 (Comment) but
  not 408 (Comment continuation), so a two-line RMXP comment put a code in
  `other_codes` and made `is_dispositionable` False; the only reason
  `map037/ev004/p0` was CH05's one undispositionable row. `_CODE_IGNORED` now
  reads `frozenset({0, 509, 106, 108, 408, 413})` — verified current at
  `src/rpg2gba/chapter_manifest/generator.py:107`, with 408 treated as a
  structural rider on 108, same as 413 is on 412. `PROJECT_TODO` #55;
  `PLAYTEST_AUTHORING_IMPROVEMENT_V2.md` §5.10. Landed before the CH01-CH03
  manifests are generated, since it changes what they say; `pytest -k
  manifest`: 109 passed. The CH05 dry-run doc and this file's own record of
  the finding were not updated at the time the fix landed.

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

### 39. `pbPushThisBoulder` is unconverted — due in CH25, the chapter that grants Strength

*Reclassified out of `CH03_TODO.md` #20 on 2026-08-17, where it had been logged
as Kevlar Town's biggest blocker. It never blocked CH03.*

`pbPushThisBoulder` (`reference/scripts_dump/101__PField_Field.rb:2850`) pushes
only `if $PokemonMap.strengthUsed`, and returns false otherwise — the standard
series mechanic. So an unpushable boulder in a pre-Strength chapter is the
design working, and converting this function would not have changed any beat's
outcome in CH03.

**Due in CH25 (Route 11)** — the chapter that *grants* HM04 (`00-atlas.md`
line 116), not the chapter before it. It should land alongside the mechanic it
enables, where a beat can actually exercise a push; shipping it earlier means
committing an unverifiable conversion.

**Scope when it comes up** — 5 queue entries, plus the content they gate:

| Map | Entries | What |
|---|---|---|
| 19 (Passage Cave Grott-Hole) | 17 (all of them) | 3 boulders + the Biker encounters: 3 `pbTrainerIntro(:BIKER)`, 3 `Kernel.pbNoticePlayer`, 3 `pbTrainerEnd`, 4 `pbTrainerBattle` conditionals (Lou/Joe/Richard), 1 warp back to map31 |
| 31 (Kevlar Town) | 2 of 17 | the two outdoor boulders, `EV001` (10,16) and `EV037` (12,16) |

Map019 **stays in `SLICE_MAP_IDS` now** (user call, 2026-08-17) so the cave is
built and art-checked well before Strength arrives — only its beats are
deferred.

**Implementation note already settled:** the push is **object-driven** —
`OBJ_EVENT_GFX_PUSHABLE_BOULDER`, **not** `MB_PUSHABLE_BOULDER`
(`reference/chapters/03-kevlar-town.md` §6.1 — "corrected in the ledger, do not
re-invert").

The same CH25 work unblocks the **Cry Boy sidequest** in Kevlar Town, which is
the same return trip: *"After getting HM04 in Legen Town, come back and speak to
the boy crying just outside of the entrance of the Poké Mart"*
(`Kevlar_Town.wiki:30`). CH03's B18 correctly observes only the pre-Strength
idle page today.

### 40. Commands stranded after a `Transfer Player` warp — 176 rows, two unrelated classes

*Filed 2026-08-17 after CH03's queue triage. The single queue signature —
"command follows a Transfer Player warp: pokeemerald halts the script at the
warp (ScrCmd_warp/DoWarp), unlike RMXP which keeps running the page" — covers
two problems with nothing in common. Do not size them as one job.*

RMXP keeps executing an event page after code 201; pokeemerald halts the script
at the warp. Anything after the transfer is therefore unreachable in the port,
and the transpiler queues it instead of dropping it silently (correct — §4.5).

**Distribution:** map172 **132**, map32 13, map31 12, map33 11, map49 3, map81 2,
map48/50/89 1 each. 176 total, over 9 maps. That shape is the whole story: one
map is a real problem, the rest are choreography.

#### 40a. The cosmetic tail — 44 rows, everything except map172's cutscene

31× code 223 `CHANGE_TONE`, 11× code 204 `CHANGE_MAP_SETTINGS`, 2× code 241
`PLAY_BGM`.

**The 223s cost nothing.** Every one observed is `Tone rgba [0,0,0,0]` over ~6
frames — *neutral*, i.e. the fade back **in** that closes a fade-out/fade-in pair
around the transfer. The transpiler already strips the opening half as subsumed
by the native warp (`transpiler.py:242-249`, the `pbCaveEntrance` note: "the GBA
warp performs its own map-transition fade"). This is the same argument from the
other side. Stripping them is a no-op that quiets ~2/3 of this signature.

The 204s are fog (subtype 1 — e.g. `"004-Shade02"`, opacity 60, zoom 250): a
real but minor visual loss with precedent for accepting it (the Map033 "Luz"
ambient-light strip, `CH02_TODO` #11/#12). The 241s are destination BGM, largely
moot while audio is still substitution-based with slice maps on `MUS_LITTLEROOT`
(the per-map `reference/audio_map.json` wiring from
`audio_decision_2026-07-14.md` was never built).

**Action:** strip 223-to-neutral after a warp as a recognized breadcrumb, and
rule on fog/BGM as accepted debt. Cheap, and it stops this signature from
looking like 176 rows of lost logic.

#### 40b. Map172's Theo cutscene — 131 rows, genuinely dropped, due CH58

**131 of map172's 132 rows belong to one event: `EV4 'Theo'` page 3.** The codes
are real content, not choreography: 40× 101 `SHOW_TEXT`, 19× 106 `WAIT`, 14× 355
`SCRIPT`, 9× 209 `MOVE_ROUTE`, 4× 223, 2× 202 `SET_EVENT_LOCATION`, 2× 207, 1×
111 `COND_BRANCH`, and 1 nested 201 `TRANSFER`. (The 34× 509 rows are the
editor's per-step display duplicates of the 209s — `transpiler.py:95` — not
independent logic.) A whole cutscene sits after the page's warp.

**Not near-term.** Page 3's condition is `switch1_id 125, switch1_valid true` —
switch 125 is the "FINAL EVENT" **postgame** gate. `chapters.json` already names
this exact case: CH58 (Moki Town postgame, A9) is "where the postgame pages on
slice-1 maps finally fire ... the switch-125 'FINAL EVENT' grants that
01-moki.md §4.2 rules out of CH01 (Lava Cookie on 49, Poke Radar on 50, **HM07
Waterfall on 172**)". So this is CH58 work, and **CH08's visit-2 return to
map172 is unaffected** — page 3 cannot fire there.

**This one needs a structural fix, not a strip.** The content has to run at the
destination, since the source page cannot continue past its own warp: split the
tail into a script that fires on arrival (a map-script `ON_TRANSITION`/
`ON_FRAME` on the destination, gated so it runs once), rather than trying to
keep executing at the source. Worth designing when CH58 is written — and worth
checking then whether any other page-3-style postgame page hides the same shape.

### 41. 106 items the id map names and the fork does not define — plus Phase 2's item output is a dead end

*Filed 2026-08-19 out of `CH03_TODO.md` #27, where it was surfaced by CH03's
item-grant fix. Not chapter-blocking; it will keep surfacing one chapter at a
time until it is done properly.*

`reference/uranium_id_map.json` maps 607 Uranium items to `ITEM_*` constants and
already precomputes the shortfall in its own `needs_engine.items`: **111 of them
do not exist in `engine/include/constants/items.h`.** Five were added by hand for
CH03 (the four Uranium berries + Sprinklotad, `67fd0435`); **106 remain**,
including Uranium-original held items, mega stones, key items and mail.

Every one is an item grant, mart entry or held item that will fail the §4.7
forward gate and queue when its map is converted.

**The compounding half is the real finding: Phase 2's item converter output never
reaches the engine.** `pbs_converter/items.py` emits both
`include/constants/items.h` and a `gItemsInfo[]` table into
`output/uranium-build/`, and **nothing includes or copies them into `engine/`**.
Compare the flags and map-alias hooks (`engine/data/event_scripts.s:1743`,
`map_events.s:27`) — there is no items equivalent, so that output is currently
written and discarded.

**Scope it as a Phase-2→engine integration, not 106 hand edits.** It also needs a
decision the five berries dodged: those were vanilla-equivalent, so their data
could be copied from a twin. An original held item or mega stone has no twin and
needs real hold-effect data from Uranium's `item_field_codes` worklist
(`items.py:308-321`, already generated and never read).

### 42. Shape-C item grants with a non-empty then-body — 60 of 150 sites still queue

*Filed 2026-08-19 out of `CH03_TODO.md` #25 item 2, which is otherwise closed.*

Uranium grants items three ways. Shape C is the awkward one: a `code-111`
type-12 conditional whose **test expression is the grant itself**, because
`Kernel.pbReceiveItem` returns whether the item was accepted, and the then-body
is the success path. 152 sites / 56 maps corpus-wide.

`43aa482e` handles the common case — an **empty** then-body, i.e. a pure
side-effect wrapper — by emitting `giveitem`. **60 sites with a non-empty
then-body still queue**, most of them on items the fork does not define (#41),
which is why the two want planning together.

Do **not** approximate the success path. Emerald's `giveitem` already sets
`VAR_RESULT`, so the faithful mapping is plausible and cheap to verify against
`engine/` (§4.7) — but the bag-full / refusal semantics have to be checked
before a then-body is wired to it, not assumed.

Worth remembering why this class was invisible for so long: **the queue entry
names the conditional, not the grant hiding inside its test expression** — the
same lesson as `CH03_TODO.md` #26(b).

### 43. Beat classes the manifest cannot see, and the `cosmetic` rule

*Filed 2026-08-25 out of the operator's read of CH04's beat list, which found
four gaps in a chapter that had already been fully dispositioned.*

Two findings, both corpus-wide, both structural rather than CH04-specific.

**(a) The manifest enumerates event pages and overland seams — nothing else.**
An encounter table is neither, so no generated row can ever represent one.
CH04 had no beat covering "walk in the tall grass, get a wild battle" because
nothing in the approval object could prompt for it. The same hole applies to
any beat class that is not an event page: encounter tables, tileset behaviour
(counters, ledges, water), connection-only seams, field-move surfaces. Either
the generator grows non-page row kinds, or every chapter doc needs a
hand-authored "beats with no manifest row" section that a reviewer is
required to fill. Decide which before the next chapter is authored — CH04 got
its B15 by hand (`04-route-2.md` §3.1).

**(b) `cosmetic` was being decided on state writes, not observability.**
The rule actually applied was *does this page write state?* That made Larrie's
defeated re-talk a beat (it rides on `pbPhoneRegisterBattle`) while Timothy's
identical-in-kind re-talk was `cosmetic`, and it dropped a talk-triggered NPC
with an emote bubble, a cry SE and a line of dialogue. None of those write
state; all three break independently. The rule is now *is there anything a
player can press A on and observe?* — `cosmetic` means decoration with no
trigger.

CH04 was re-swept under (b): `ev009/p1`, `ev011/p0`, `ev012/p1` became
`beat:B12`/`B13`/`B14`. **CH01–CH03 have not been re-swept** and passed their
§9 gates under the old rule, so each may be carrying interactive rows filed as
cosmetic. The sweep is mechanical — cross-reference trigger against
disposition, flag action-trigger rows dispositioned `cosmetic` — and the
checker cannot catch it, since `cosmetic` on a state-free row is legal by
construction.

**The sweep was run 2026-08-25; results and remediation are §44.** It could not
be mechanical after all — CH01–CH03 have no manifest to cross-reference.

### 45. Defeated Larrie faces you and says nothing — ROOT-CAUSED, FIXED, AND CONFIRMED IN PLAY 2026-08-27

**CLOSED (2026-08-27).** Confirmed in play by CH04's §9 boot walk: route2
chapter suite GREEN 74/74 on ROM `5953e98f`, the first run in which a defeated
phone trainer speaks its idle line — B11 (Larrie) and `route1:N5` (Richey)
both pass. The cause is the engine's re-talk resume address, and it makes the
symptom exact.

On a re-talk the engine runs its own scaffolding,
`EventScript_TryDoNormalTrainerBattle` (`engine/data/scripts/trainer_battle.inc:9-21`):
`lock`, `faceplayer` — *this is the turn-to-face the operator sees* — then
`GetTrainerFlag`, already set, so it falls to `EventScript_NoNormalTrainerBattle`'s
`gotopostbattlescript`. That resolves through `BattleSetup_GetScriptAddrAfterBattle`
(`engine/src/battle_setup.c:1574`) to `sTrainerBattleEndScript`, which
`TrainerBattleLoadArgs` (`battle_setup.c:1058`) sets to
`(u8 *)data + sizeof(TrainerBattleParameter)` — **the byte immediately after
the packed trainerbattle command, i.e. the next line of the calling script.**

§46 put the route to `Page2` in `trainerbattle_single`'s FOUR-ARGUMENT
continue-script instead. That is a different pointer, `battleScriptRetAddrA`,
consumed only by `gotobeatenscript` / `BattleSetup_GetTrainerPostBattleScript`
(`scrcmd.c:2478`, `battle_setup.c:1582`), which fires **exactly once**, on the
return from a won battle. So the branch ran once, with the self-switch still
clear, and never again — `Page2` was unreachable in every state, and Page1's
next line was `release`/`end`. Lock, faceplayer, silence. Permanently, on any
tile, for both trainers.

Vanilla puts the re-talk continuation in the fall-through, not the 4th
argument (`Route102_EventScript_Calvin`: `trainerbattle_single`, then
`specialvar ShouldTryRematchBattle`, then the post-battle msgbox). The
classifier now does the same: Page1 is `trainerbattle_single(...)` followed by
`goto(Page2)`, and the 4th argument keeps only the one-shot registration (its
now-dead self-switch check is dropped; the `setflag` stays, because
`metadata_wiring` reads that self-switch for page conditions).

**Fix:** `deterministic.classify_phone_rematch_trainer_battle`. Regression
tests: `tests/test_phone_rematch_classifier.py::test_larrie_page1_falls_through_to_page2_after_trainerbattle`
and the ev039 golden. In-play guard: `route1:N5`, now registered (below).

**The two-datum key.** The operator supplied both: position is irrelevant
(sight-approach or direct interaction, same result), and **Richey exhibits it
too**, on a save the harness never touched, beaten by a different playthrough.
That killed the harness explanation and the tile explanation together, and
left the one thing Larrie and Richey share and Timothy doesn't — the phone
shape. The engine read followed in minutes.

*The original filing and its refuted claims are kept below, unedited.*

---

*Original filing — superseded by the resolution above:*

*Filed 2026-08-27 from CH04's suite run on ROM `b07a02f8`; **substantially
corrected the same day by the operator's own boot walk of that ROM**, which
refuted the original diagnosis. The corrected version is below; the refuted
claims are kept explicitly, because two of them were confidently wrong and
the next reader should not re-derive them from the same evidence.*

**This is the live blocker for CH04's §9 gate**: B11 fails on it, and
B12-B15 are gated behind B11.

**What actually happens in game (operator boot walk, ROM `b07a02f8`).**
Re-talking defeated Larrie: he **turns to face the player, and NO text box
appears at all.** The script starts — the `faceplayer` is visible — and then
produces nothing. (The match-call registration message DOES appear, correctly,
immediately after the battle itself; an earlier revision of this item
mis-recorded that as happening on re-talk. It does not.)

**Youngster Timothy, same map, re-talks correctly** and shows his line. He is
the plain vanilla shape — `trainerbattle_single` with a trailing msgbox, no
phone registration and no rematch branch. **No PHONE trainer is verified in
play**, so §46's fix is unproven for its whole class; Route 1's Richey was
not walked.

**Leading hypothesis: the branch works and the defect is one level deeper.**
`Page2` runs `specialvar(VAR_RESULT, IsTrainerReadyForRematch)` and takes the
idle-line msgbox ONLY on `VAR_RESULT == FALSE`; otherwise it falls into
`trainerbattle_rematch`. If that special returns anything but FALSE and no
rematch is actually available, the rematch command does nothing visible and
the script ends — which is precisely "faces you, no text". That would mean
the `goto_if_set ...SSA -> Page2` fix from §46 IS working and the bug is the
rematch arm. Under investigation; if it holds, the fix is to gate or drop the
rematch arm rather than to touch the dispatch again.

**The harness is NOT the primary defect, and the operator's argument is the
reason.** A mispositioned harness cannot explain a human standing in the
correct tile, facing the trainer, and getting no box. The harness's
coordinate discrepancy (below) may still be real and may still be why
`interact()` reported "no script started", but it is a SECOND, lesser
problem — do not let it absorb this item.

**REFUTED — do not carry these forward.** Both came from harness
observations and both are wrong:

1. ~~"A defeated trainer cannot be re-talked anywhere in this build; pressing
   A starts no script at all."~~ False. A script demonstrably runs — the
   trainer faces the player and prints a message. The harness's
   `interact()` reporting "did not start a script", reproduced by driving
   the emulator directly from `pre_beat.gba`, is a **harness** failure to
   reach or detect the interaction, not the game's behavior.
2. ~~"The trainer is not rendered."~~ False. Larrie is plainly visible in the
   B11 contact-sheet frame (`route2-sheet-6.png`, the yellow-hatted Hiker,
   same sprite as the B2 frame) and in play. That claim came from
   misidentifying a distant sprite in a probe screenshot as the Barewl.

**Still open, secondary: the harness's object-coordinate read.** It places
Larrie at `(18,39)` against a template of `(18,36)`, and Richey at `(17,11)`
against `(17,9)`, while static objects on the same maps (the Barewl at
(17,36), the item balls, the rocks) report their templates exactly. Since the
trainers are rendered and DO respond in play, these coordinates look wrong or
stale, which would explain `interact()`'s "no script started" report from a
seeded state. That is an `emulator.py` object-decode question —
`off_objevent_currentcoords`, and whether a trainer that has run an approach
sequence keeps its live position in the field the harness reads. **Elevation
remains ruled out** (object elevation 3; staged terrain elevation 3 at the
template, at the reported tile, and at the player's tile; the only z-check is
`ObjectEventDoesElevationMatch` and 0 is a wildcard), as does
`TryOverrideTemplateCoordsForObjectEvent` moving them (it assigns only
`movementType`, never coordinates, despite its name).

**Eliminated 2026-08-27 (checked, do not re-check).**

- **The emission is correct.** The assembled chain in
  `engine/data/maps/Route02/scripts.inc` is complete and well-formed:
  `goto_if_set FLAG_MAP035_EVENT003_SSA` -> a label that `goto`s
  `Map035_EV003_Page2`; `Page2` itself has the `specialvar VAR_RESULT,
  IsTrainerReadyForRematch`, the `compare`/`goto_if_eq`, the msgbox arm and
  the `trainerbattle_rematch` arm, all present. Not a dropped command, not a
  mis-wired label, not a bad goto.
- **`IsTrainerReadyForRematch` is a real special** (`data/specials.inc:81`)
  and is FALSE-safe for a trainer absent from the rematch table
  (`TrainerIdToRematchTableId` -> -1 -> FALSE). Larrie IS in the table
  (`uranium_rematch_table.gen.h`, `REMATCH_URANIUM_LARRIE_4`, five identical
  stages — the generator emitted no real rematch variants). Richey likewise.
- **Neither `Page2` arm is silent by design.** FALSE prints the idle msgbox;
  TRUE runs `PlayTrainerEncounterMusic` / `ShowTrainerIntroSpeech` /
  `waitmessage` / `waitbuttonpress` / `BattleSetup_StartRematchBattle`, i.e.
  visible text and a battle. "Faces you, then nothing" matches neither arm,
  so the original rematch-arm hypothesis is **REFUTED**.
- **In the harness's seeded state the script does not start at all from the
  beat's authored tile.** Pressing A at (18,37) facing UP leaves the field
  unlocked and `gSpecialVar_Result` untouched across 120 frames. That
  corroborates the coordinate discrepancy (Larrie is not at his template
  (18,36) in that state) but does NOT explain the in-play symptom, where the
  script demonstrably starts.

**The open contradiction.** In real play the script starts (the trainer
faces the player) and then prints nothing. In every seeded state reachable
from the harness, the script does not start at all. Both observations are
solid; they cannot both be explained by "the harness stands in the wrong
tile" alone, because in play the human stands in the right one. The next
datum needed is **where Larrie is standing when the player talks to him** —
his own tile relative to where he stood before the battle — and whether a
second consecutive talk behaves differently. Asked of the operator
2026-08-27; do not guess it.

**Next steps, in order.**
1. Confirm or refute the `IsTrainerReadyForRematch` hypothesis above — read
   what the special returns for a trainer with no available rematch, and
   whether `trainerbattle_rematch` is silently inert in that case.
2. If confirmed, decide what the idle path should be. The rematch arm is
   currently unreachable content anyway: nothing in this pipeline makes a
   rematch "ready", and B10 (the rematch offer) is already deferred for want
   of a Match Call driver.
3. Separately, fix the harness object-coordinate read and re-point B11 at the
   live position. B11 asserting the idle line stays the correct assertion.

**Resolved 2026-08-27:** the trainer that re-talked correctly on the walk was
**Timothy**, not Richey — confirmed by the operator. So no phone trainer's
re-talk has been observed working, and §46's fix remains unverified in play
for its class.

**Blast radius.** CH01-CH03 all passed their §9 gates without this being
visible, because CH04's B11 is the first beat in the corpus that re-talks a
defeated trainer at all.

### 46. Phone-rematch trainers' `Page2` was dead code — FIXED 2026-08-27, then RE-FIXED the same day (see §45); CLOSED, confirmed in play by CH04's §9 walk (ROM `5953e98f`)

*Filed and fixed the same day. **The fix recorded below was half right and did
not work**: the collapsed-pages dead end it diagnosed was real, but it moved
the branch into `trainerbattle_single`'s four-argument continue-script, which
the engine runs exactly once — on the return from a won battle — and never on
a re-talk. `Page2` stayed unreachable, and §45's silent NPC is what that looks
like in play. §45 carries the engine citations and the corrected fix
(the branch belongs in Page1's fall-through, where vanilla puts it). Read §45
first; the text below is the superseded reasoning, kept because it was
confidently argued and the next reader deserves to know where it went wrong.*

`deterministic`'s phone-rematch classifier emits three blocks per phone
trainer: the `trainerbattle_single` page, a `_RegisterMatchCall`
continue-script, and a `Page2` steady state carrying the
`IsTrainerReadyForRematch` branch and the post-defeat idle line. Nothing ever
referenced `Page2`: `transpile_driver._record_collapsed_pages` marked the
event `collapsed_pages`, and `metadata_wiring._resolve_script` read that
trait as "resolve to the page-1 label, build no dispatcher". Re-talking a
defeated phone trainer therefore re-ran the headless match-call registrar and
the NPC said nothing.

Four events corpus-wide: map33/ev39 (Brandon), map33/ev53 (Richey),
map35/ev3 (Larrie), map35/ev23 (Brent). **Two are Route 1's, so CH02 passed
its §9 gate on 2026-08-12 with two silent NPCs in it.** Map050/ev19 (Theo)
was unaffected — it gets a real `_Dispatch` — which is what localises the
bug to the `collapsed_pages` rematch-trainer shape rather than to multi-page
trainers generally.

**Fix:** the `_RegisterMatchCall` block now leads with a check on the SSA
flag it already sets and jumps to `Page2` when set. That is where vanilla
puts it (`Route102_EventScript_Calvin`'s 4th `trainerbattle_single`
argument runs both after the battle and on every later re-talk via
`gotopostbattlescript`).

**A dispatcher wrapping the trainer script is NOT an option — do not retry
it.** It was tried first and broke sight-trainer detection outright:
`GetTrainerFlagFromScriptPointer` (`engine/src/battle_setup.c:1232`) casts
the object event's RAW SCRIPT BYTES at a fixed offset to read the opponent
id, so the object's script must have `trainerbattle_*` as its literal first
command. Wrapping it made the engine read garbage as a trainer id;
`route1:B13` (Richey's first battle, previously green) failed immediately on
the live suite. The comment recording this now lives at the classifier's
post-battle-script construction.

### 44. CH01/CH03 flavor interiors shipped untested — DEFERRED to the end of Act 1

*Filed 2026-08-25 from the §43(b) re-sweep of CH01–CH03 under the new
observability rule. **Deferred by the operator until the first chapter group
(Act 1, CH01–CH06) is complete** — do not action before CH06's §9 gate passes.*

**Deferral rationale.** Neither chapter is the frontier, both already hold a
passed §9 gate, and Act 2 opens with revisit chapters that re-enter this exact
content — CH08 is Moki Town (revisit), the first test of the revisit model, and
is the natural place CH01's interiors get walked again. Doing the remediation
then folds it into work already scheduled instead of reopening two closed gates
mid-Act-1.

**The sweep could not be mechanical.** §43(b) assumed a trigger-vs-disposition
cross-reference. There is nothing to cross-reference: `reference/manifests/`
holds only `CH04.*` — CH01–CH03 predate the manifest system and have **no
manifest and no dispositions file**. The assessment was made against the prose
specs and the playtest scenarios instead. Corollary worth carrying: the checker
is structurally blind to every pre-CH04 chapter, so any future corpus-wide
disposition rule change has the same hole.

**Findings — 12 rows would flip to `beat:`, 3 need a human ruling, 0 are
incidentally covered by the existing scenarios.**

- **CH02 is clean.** Its beat table already treats flavor NPCs as first-class
  beats regardless of state writes (B3 Chyinmunk sprite, B4 hint NPC, B34
  brother NPC, B35 sign) — exactly the rows the old rule would have discarded.
  Nothing to do. Not a coincidence worth ignoring: the author's instinct was
  the new rule two chapters early.
- **CH01 — 8 flips.** `01-moki.md` labels Map064, Map065 and Map089 "Flavor
  interior, no chain beats", and `moki.py` never enters any of them. Map064:
  ev001/p0 and ev002/p0 (talk-trigger dialogue NPCs), plus the Chyinmunk
  (`pbCallBub` emote + cry SE + line — literally the Barewl pattern §43(b)
  flipped). Map065: ev001/p0, ev002/p0. Map089: EV003, EV004, EV005, EV006,
  EV007 (all talk-trigger flavor lines). The `p1` twins of the Map064/065 NPCs
  stay cosmetic — switch-125-gated postgame, unreachable in-chapter.
- **CH03 — 4 flips.** `kevlar.py`'s B16 does door-in/door-out warp checks on
  Maury's apartment and the couple's house and never talks to anyone inside.
  Map073: EV005/p0 (Maury, "have you gotten my wallet back?"), EV010 and EV011
  (the couple), and **EV008, a boutique-interior NPC absent from the beat table
  entirely**.
- **Needs a human ruling before beats are written, because it sets the count:**
  Map089 EV002 (touch-trigger, `code 209/509` picture display, no text — cannot
  tell from codes whether the player observes anything) and Maury's EV005 pages
  1 and 2 (self-switch-gated variants whose in-chapter reachability is unclear).

**Remediation when it comes due:** ~5 new beats in `moki.py` (three interiors,
collapsing the postgame-gated twins) and ~3–5 in `kevlar.py` (Map073's
interiors), same shape as CH04's B12–B14 — enter, talk, assert the box opens and
closes. Update `01-moki.md` / `03-kevlar-town.md` beat tables to match; the
"flavor interior, no chain beats" labels are what caused this and should go.

**Caveat on provenance:** the row list is a sub-agent's judgment read of the
deserialized event data, not a row-by-row human verification. Re-confirm each
row against `output/uranium-build/maps/Map0{64,65,73,89}.json` when the work is
picked up.
