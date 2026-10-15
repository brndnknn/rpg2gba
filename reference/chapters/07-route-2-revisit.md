# Chapter 7 — Route 2 (revisit)

**Status:** authored 2026-10-14 at chapter open; **gate-passed 2026-10-15** (gen
suite 480/480 from boot; operator walk: cutscene as expected, ledges correct; findings
filed as PROJECT_TODO #140 and #141). *(2026-10-15: CH07A, named as the successor
throughout this doc, was folded into **CH08** "Route 1 + Moki Town (revisit)"; read
"CH07A" below as CH08.)* Tier **thin** per `reference/chapters.json` (CH07 record), with §4
enumerated exhaustively because the chapter is one map and 21 events. No §8. This is
a spec a scenario gets written from; gates and effects only, no narrative.

**Method note:** read 2026-10-14 from `reference/chapters.json` (CH07, CH07A),
`output/uranium-build/maps/Map035.json`, `output/uranium-build/connections.json`,
`output/uranium-build/intermediate/wild_encounters.json`,
`output/uranium-build/transpile_unhandled.jsonl` (map 35 rows),
`reference/manifests/CH04.dispositions.json`, `PROJECT_TODO.md` #33/#92/#128, and
`chapter_atlas census --chapter CH07`. Map 35's events are the same data CH04 read;
see `reference/chapters/04-route-2.md` for the first-visit analysis (its §3.1 beats
and §4 rows are not repeated here except where reachability changes). Wiki: **not
checked** (§5).

---

## 1. Purpose / scope

Second visit to Route 2 (RMXP 35, "Route 02", 42x57). Predecessor CH06 (Nowtoch City,
map 40), successor CH07A (Route 1 revisit, maps 33/81, entered via Kevlar 31)
(`reference/chapters.json` CH07/CH07A). Roster `"maps": [35]`. Census
(`chapter_atlas census --chapter CH07`): maps=1 events=21 pages=40 commands=398
trainer_battles=4 item_grants=3 switch_writes=2 conditionals=22 move_routes=27;
unhandled queue=6. Identical to CH04's totals, as expected: same map, same events.

Mechanically: the content CH04 dispositioned `blocked:rock_smash` — 28 rows,
`grep -c '"disposition": "blocked:rock_smash"' reference/manifests/CH04.dispositions.json`
— opens here: the five Rock events (ids 14-18), the north pocket (ids 19-26: 2 trainer
battles, 2 item balls, a 4-event scripted scene) and the `35 N<->S 40` seam. `[auto]`
The player has Rock Smash from CH06 (`HM06`, events 20/21/79 on map 40;
`reference/chapters/06-nowtoch-city.md` §3 B7). CH07 adds no persistent state: still
no `code 122` and only the `FLAG_MENU_ON_EVENT` bracket (CH04 §3).

## 2. Map inventory

| RMXP id | Uranium identity (`map_infos.json`) | Engine dir | porymap constant | Role in chapter |
|---|---|---|---|---|
| 35 | Route 02 (`parent_id` 55) | `Route2` (proposed, unassigned; CH04 §7 open) | `MAP_ROUTE_2` (proposed) | Whole chapter; rockslide and north pocket opened |

**Wiring.** `connections.json` has two rows touching 35: `[35,'N',0,14000,'S',-5]` and
`[31,'N',11,35,'S',0]` (`grep -n '35' output/uranium-build/connections.json`). Note the
north seam now lands on **14000**, the main piece of map 40 after the 2026-10-09 split
(CH04 doc still says 40; its dispositions row is `map035/seam/N/map14000`). Entry
boundary: the N seam from map 14000 (CH06 end state; the chapter's first crossing).
Exit boundary: the S seam to Map031 (Kevlar), which is CH07A's entry leg (CH07A notes:
walk `35 -> 31 -> 33 -> 32`). The cave warp id 1 (20,33) -> Map036 is still the map's
only `code 201`; not chapter-relevant on this visit (§4.4).

## 3. Story beat chain

Thin tier: roster and gates, no beat table. Gates, all read from `Map035.json`:

- **Rocks 14-18** (page 0, trigger 0 action, no switch/var gate): `111 [12,
  'Kernel.pbRockSmash']` then `pbEraseThisEvent`, `Kernel.pbRockSmashRandomEncounter`,
  self-switch A on. Page 1 = cleared. Needs Rock Smash capability (§6.1, §7).
- **Ranger scene, id 19 "Trainer(4)" @(25,26)**: page 0 engine-ungated (all conditions
  invalid), trigger 2 (touch), `through` true. Body sets self-switch A on ids 19-22 and
  runs `for i in 14..18: pbSetSelfSwitch(i,"A",true)`, i.e. **clears all five rocks
  without Rock Smash** (`.venv/bin/python -I` dump of Map035 ev19 `code 355`, list
  lines 114-116; unhandled queue rows for the same lines). `[auto]`
- **Switch 185 `FLAG_MENU_ON_EVENT`** bracket on id 2 (sign): the census's whole
  `switch_writes=2`; a menu lock, not a story gate (CH04 §3).

Consequence for the chapter note "Rock Smash clears the rockslide"
(`reference/chapters.json` CH07 `notes`): the data has two independent clearing paths
(ev19's scene, and each rock's own Rock Smash page). Which one the walk takes depends
on approach side and on whether ev19's tile is reachable from the north seam. Not
determined here (§7 item 1).

## 4. Coverage targets

Exhaustive (cheap: 4 + 3 + 1 + 1 rows). All counts match the census.

### 4.1 Trainer battles

| Map | Event | Trigger | In-chapter reachable? | Notes |
|---|---|---|---|---|
| 35 | Hiker Larrie (id 3 @(18,36)) | touch | Yes, already beaten (CH04 B2); defeated re-talk pages 1/2 | south of the rocks; in the seam exit path |
| 35 | Youngster Timothy (id 12 @(18,47)) | touch | Yes, already beaten (CH04 B4) | same |
| 35 | Bird Keeper Brent (id 23 @(26,9)) | touch | **Yes, new** (CH04 row was `blocked:rock_smash`) | page 0 `pbTrainerBattle(BIRDKEEPER,"Brent",…)` then `pbPhoneRegisterBattle`; p1 rematch via `customTrainerBattle`; p2 defeated re-talk |
| 35 | Hiker Chuck (id 24 @(29,23)) | touch | **Yes, new** | page 0 `pbTrainerBattle(HIKER,"Chuck",…)`; p1 defeated re-talk |

New this chapter: 2 battles. `[auto]` (`grep pbTrainerBattle` on Map035.json: 4 hits)

### 4.2 Item balls / given items

| Map | Item | Event | Gate | In-chapter? |
|---|---|---|---|---|
| 35 | Potion | id 9 @(16,42) | default page | Already taken in CH04 (B3/B12); one-shot assertion only |
| 35 | Super Potion | id 25 @(30,10) | default page | **Yes, new** |
| 35 | TM78 (Captivate) | id 26 @(29,29) | default page | **Yes, new**; CH04 BFS put it east of the rocks behind a wall segment (`map035/ev026/p0` note), reachability from the north side unmeasured (§7 item 2) |

`[auto]`

### 4.3 Wild encounters

| Map | Table | Contents | In-chapter reachable? |
|---|---|---|---|
| 35 | `land_mons` rate 25 | 12 slots: Chyinmunk x3, Birbie x2, Cubbug, Barewl, Mankey, Owten x4, all lv 3-5 | Yes, whole map now |

`maps["35"]` has only `land_mons`. **No `rock_smash_mons`** table exists for map 35, yet
rocks 14-18 each call `Kernel.pbRockSmashRandomEncounter` (CH04 §4.3). If the walk
smashes a rock, the encounter roll has no table. `[auto]`

### 4.4 Warps

| Map | Warp | Destination | Chapter-relevant? |
|---|---|---|---|
| 35 | cave entrance id 1 @(20,33) | Map036 (17,39) | No for traversal (already used in CH04/CH05); still the only `code 201`; unhandled-queue rows ev1 p0 lines 4-5 are post-warp unreachable commands |
| 35 | N seam to 14000 (offset -5) | Nowtoch main piece | **Yes**, chapter entry crossing |
| 35 | S seam to 31 | Kevlar Town | **Yes**, chapter exit crossing (CH07A entry) |

## 5. Wiki vs rxdata discrepancies

**Not checked** for CH07 specifically. CH04 §5 already compared the same map against
`output/uranium-build/wiki/Route_2.wiki`, including the Ranger clearing the rockslide;
that finding (wiki says the Ranger clears it after the player doubles back; data's ev19
is engine-ungated) bears directly on §3 here and is carried, not re-derived. Open
(§7 item 5).

## 6. Expected conversion work and risks

### 6.1 Mechanics binding table

Census mechanics list (13): cave entry/exit, character reference resolver (no-op),
event erase (persistent), item ball, phone / rematch, rock smash, rock smash encounter,
self-switch write, speech bubble UI, temp switch write, trainer battle, trainer sight,
wild encounters. Verdicts are owned by `reference/guides/command_pokeemerald_map.md`.

| Mechanic | First appears here? | Disposition | Ledger row / notes |
|---|---|---|---|
| rock smash | No (CH02, Route 1; grant in CH06) | native | ledger `00-atlas.md` §5 row 8; not exercised here: ev19 clears the rocks; smashing deferred to CH07A (§7 4c) |
| rock smash encounter | No | native (`EventScript_RockSmash` + `special RockSmashWildEncounter`, ledger line 136 ✓VERIFIED) | no map-35 table, §4.3 |
| self-switch write (remote, `pbSetSelfSwitch`) | No | per ledger | ev19 mass-clear loop; `for i in 14..18` is the 2 unhandled script rows |
| event erase (persistent) | No | per ledger | each rock's `pbEraseThisEvent` |
| trainer battle / sight, phone rematch, item ball, wild encounters, cave entry/exit, speech bubble, temp switch, character resolver | No | per ledger | unchanged from CH04 §6.1 |

### 6.2 Unmapped script heads

Census line, unassessed (thin tier). Unhandled queue for map 35 = 6 rows
(`grep '"map_id": 35' output/uranium-build/transpile_unhandled.jsonl`): ev1 p0 lines
4-5 (commands after a warp), ev19 p0 lines 77-78 (`207` animation id 32 on targets
21/22, no emote mapping), ev19 p0 lines 114-115 (`for i in 14..18` loop). The ev19
rows sit on the chapter's headline scene; the loop is what clears the rocks, so the
chapter does not convert cleanly until it is handled.

### 6.3 Known risks / gaps (backlog items due here)

- **PROJECT_TODO #92 (capability model).** Asks: model field capabilities as badge AND
  (move OR item), since Uranium has no HMs and the grant is not a `code 121/122`
  write; CH04's 28 `blocked:rock_smash` rows report `capability_model_unenforced`.
  CH07 and CH07A are the first consumers. Remainder: move alternative, Map167 gadget
  items, requirement groups.
- **PROJECT_TODO #128.** `blocked:` verdicts are never auto-dispositioned; revisit once
  #92's requirement groups exist. CH07 must either supply that or hand-copy
  verdicts for the rows it unblocks.
- **PROJECT_TODO #33 (ledge jump directions).** Map 35's 16 tag-1 cells all derive
  `MB_JUMP_SOUTH` (`terrain_tags.column_behavior`) and sit beyond the rockslide;
  never exercised on hardware. CH07 is the first chance. `[eye]` jump direction fires
  on all 16 cells when approached from the north; do not read CH04's green gate as
  validating it. **Checked on hardware 2026-10-15 (operator walk): jumps are correct.**
  All 16 cells are `MB_JUMP_SOUTH`, though, so only that one direction is verified.
- CH04's 28 `blocked:rock_smash` dispositions need re-triage to `beat:` rows (CH07 has
  no manifest yet: `ls reference/manifests` shows CH01-CH06 only, CH06 with no
  dispositions file).
- Seam target changed to 14000 (map 40 split) with offset -5; CH04 doc text is stale.

## 7. Open items for the lead

1. **Is Rock Smash needed at all? — ANSWERED 2026-10-14: not from the north.**
   `rpg2gba.traversal` (`reachable_with`, held capabilities `{}`) from the N-seam stretch
   x35 16..20 (14000 x 11..15) reaches the whole rows-26–29 pocket, including all three
   open neighbours of ev19 (25,26): (24,26), (25,27), (26,26); (25,25) is a wall. No rock
   cell is crossed. From the S seam (map 31) the pocket is reachable only with
   `rock_smash`, so CH04's `blocked:rock_smash` held only for the south approach.
   Scratch: `output/scratch/r2.py`..`r6.py`.
2. **Reachability of ids 20-26 from the N seam — ANSWERED:** every one of ev19–26 has a
   cell or neighbour in the no-capability set from x35 16..20. The 16 ledge cells were not
   re-checked.
3. **ev19's facing guard — DECODED:** `[6,-1,6]` is code 111 subtype 6, "player faces
   east". Page 0 is event-touch, no conditions; its tile is blocked, so it fires on a bump.
   Facing east (bumping from (24,26)) runs the *skip* arm: SSA on 19–22, exit, rocks
   untouched. Bumping from (25,27) facing north or (26,26) facing west runs the full scene.
   The transpiler already emits this correctly (`GetPlayerFacingDirection == DIR_EAST`).
   The route solver has to choose a non-east approach. The open part: does it model this?
4. **`rock_smash_mons` for map 35 — ANSWERED: none needed.** Uranium has no RockSmash
   table for map 35 (`intermediate/encounters_raw.json` key "35": density 0, slot 3
   empty), so `pbRockSmashRandomEncounter` (`scripts_dump/103__PField_HiddenMoves.rb:379`,
   flat 25% then `pbEncounter`) finds nothing. Native `special RockSmashWildEncounter`
   (`engine/src/wild_encounter.c:807`) returns FALSE on a NULL table; no battle, no crash.
   Corpus: 6 maps call it; only map 118 has a table (native uses its `encounter_rate`,
   Uranium a flat 25%).
4a. **Rock persistence — RULED 2026-10-14 (operator): keep respawning rocks everywhere.**
   Uranium is mixed. Rocks on maps 32, 35 and 66 write self-switch A to a blank page, so
   they stay gone. Map 33's six rocks only `pbEraseThisEvent`, so they return; coral on
   maps 107 and 118 also returns. The build keeps every rock on its `FLAG_TEMP_11..15` template
   flag. Native smash `removeobject` sets that flag and the next map load clears it, so
   rocks return (`metadata_wiring.py:2754-2777` yield). **Consequence for ev19:** its
   `for i in 14..18 pbSetSelfSwitch(i,"A",true)` loop is still UNHANDLED (2 queue rows).
   Transpiling it as `setflag(FLAG_MAP035_EVENT014..018_SSA)` would be WRONG under this
   ruling. Dispatch would select the rocks' page 2 (`end`) while each object stays visible
   on its TEMP flag, leaving five solid, inert rocks. The scene should hide the rocks for
   the visit instead (`removeobject` each, which sets their TEMP flags). They then return
   on re-entry and need Rock Smash, which the player holds by CH07. Still owed:
   Moki's rocks carry an `isRockSmashSoftlocked?` arm that self-smashes. The transpiler's
   rock idiom drops both arms, so that arm is lost.
4b. **ev19 animation 32 ("Ranger - Capture", `reference/animation_names.json`) — RULED
   2026-10-14: `emote_heart`** (`engine/asm/macros/movement.inc:95`) over targets 21/22.
   Closes the two `207` queue rows once built.
4c. **Rock-smash capability (#92):** the gate is badge count ≥1 AND (party member knows
   ROCKSMASH OR `BOXINGGLOVES`) (`scripts_dump/103__PField_HiddenMoves.rb:385-389`). Before
   Legen Town, the only source is teaching `HM06` (from CH06 B7) to a party member. Rocks
   **15 (21,29) and 16 (22,28) can be faced from the north pocket** at (22,29)/(23,28),
   so smashing one before bumping ev19 needs no leave-and-return
   (`output/scratch/r7_rock_faces.py`). 14 and 17 face only the south side; 18 is boxed in.
   **RULED 2026-10-14 (operator): defer to CH07A.** CH07 clears the rockslide via ev19
   only; the rock rows go to the later chapter (ELSEWHERE). #92/#128 and the
   "HM06 taught" slice of #127 move to CH07A (Route 1's six rocks, which have no
   alternative).
5. **Wiki:** CH07-specific check not run; Ranger/rockslide ordering vs ev19 unresolved.
6. **Census agreement:** doc totals equal the census; no disagreement found.
7. Engine dir / porymap constant for map 35 still unassigned (carried from CH04 §7).
8. Switch 22 gating ev1 p1 still unnamed in `flag_state.json` (carried from CH04 §7).

---

*Companion docs: `reference/chapters/04-route-2.md` (first visit, same map),
`reference/chapters/06-nowtoch-city.md` (Rock Smash grant), `reference/chapters/00-atlas.md`
(§5 ledger, §7 CH07A insertion), `reference/guides/command_pokeemerald_map.md`,
`reference/chapters.json` (CH07/CH07A), `PROJECT_TODO.md` #33/#92/#128.*
