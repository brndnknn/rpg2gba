# Chapter 9 — Route 3

**Status:** authored 2026-10-22 at chapter open. *(Updated 2026-10-23: **gate passed** — operator §9 walk; gen suite 567/567 from boot on ROM `757095f9`; seam probe passed.)*
Branch `ch09-route-3`. Tier **thin** per `reference/chapters.json` (CH09 record), with the
content set in §4 enumerated exhaustively (it is small). No §8. This is a spec a scenario gets
written from; gates and effects only, no narrative. Map 177 (dojo) was removed from the roster
2026-10-22 and parked in `unbound_maps` (`reference/chapters.json`, `unbound_maps."177"`); the
Surf-only pocket that holds its door is out of scope (§4.3).

**Method note:** read 2026-10-22 from `reference/chapters.json` (CH08/CH09/CH10, `unbound_maps`),
`output/uranium-build/maps/Map0{01,54,59}.json` (+ `Map032.json` tileset id),
`output/uranium-build/connections.json`, `output/uranium-build/map_infos.json`,
`output/uranium-build/common_events.json`, `output/uranium-build/chapter_census.json`,
`output/uranium-build/intermediate/{wild_encounters,trainers}.json`,
`reference/uranium_{switches,variables}.json`, `reference/strip_list.json`,
`reference/streamed_maps.json`, `reference/scripts_dump/`, `reference/uranium_data/
trainer_class_internal_names.json`, `src/rpg2gba/trainer_converter/{common,battles}.py`,
`src/rpg2gba/playtest/chapters_gen/{ch01,ch08}.py`, `reference/chapters/{02,07,08}-*.md`,
`PROJECT_TODO.md` #27/#91/#111/#141/#148/#150/#151, `chapter_atlas census --chapter CH09`,
and scratch scripts `output/scratch/ch09_dojo_reach.py` (foot components) and
`output/scratch/ch09_doc_{dump,readers,ce,enc,tr,misc,reach2}.py` (event/read-site dumps).
Wiki: **not checked** (§5; no `Route_3.wiki` is cached under `output/uranium-build/wiki/`).

---

## 1. Purpose / scope

First pass over Route 3. Act A2, tier thin. Predecessor CH08 (Route 1 + Moki revisit),
successor CH10 (Burole Town, map 60) (`reference/chapters.json`). Roster
`"maps": [59, 1, 54]`; `outdoor` 59. Census (`chapter_atlas census --chapter CH09`, run
2026-10-22): maps=3 events=46 pages=74 commands=539 trainer_battles=8 item_grants=8
switch_writes=3 conditionals=33 move_routes=37; unmapped script heads: **unmeasured**
(`unhandled: null`, the maps are unstaged; the CLI prints no `var_writes` / head list for this
chapter). Per-map events: 59 Route 03 130x66 ev=35 (enc: `land_mons`, `water_mons`,
`fishing_mons`); 1 Route 03 20x15 ev=6; 54 Route 03 20x15 ev=5. Tilesets: 59 ts24, 1 ts12,
54 ts19 (Moki 32 is ts22). `output/uranium-build/chapter_census.json` is **stale**: it still
lists map 177 (events=2 pages=3 commands=81), which the live CLI excludes (35+6+5 = 46 events
matches the CLI). 177-excluded numbers are the ones above. `[auto]`

Mechanically the chapter is three things:

1. **Entry seam.** Moki Town (32) E edge to Route 3 (59) W edge, row
   `[32,"E",26,59,"W",0]` (`output/uranium-build/connections.json`; the only row touching
   59/1/54). Converting it is `PROJECT_TODO.md` #27. Most of #27's original text is
   superseded: the seam machinery exists (`connections.py`, `connection_remap.py`, live on
   31<->35 and 40<->35), so this is a remapped seam between ts22 and ts24 using that machinery;
   the plan for it lives in #27 (lead), not here.
2. **Route 3 open-air content** (map 59): 8 trainer fights, 7 item balls, 3 reachable berry
   plants, 12-slot land table, plus a house (54) and a gatehouse (1) entered by door warps.
3. **Exit.** Map 1 is a gatehouse; its far warps (EV002 @(5,3), EV005 @(6,3)) go to map 60
   (Burole Town, CH10). Boundary rule (`BUILD_PLAN.md` ~line 205): the arriving chapter owns
   a crossing, so CH09's route **ends at the map 1 -> 60 door**.

## 2. Map inventory

| RMXP id | Uranium identity | Role in chapter |
|---|---|---|
| 59 | Route 03 (130x66, outdoor, ts24) | Whole map except the Surf pocket (§4.3); first chapter map over `MAX_MAP_DATA_SIZE` (§6.3) |
| 1 | Route 03 gatehouse (20x15, ts12, child of 59) | Transit: enter from 59, exit N-side doors to map 60 (chapter exit) |
| 54 | Route 03 house (20x15, ts19, child of 59) | One item ball (§4.2), three NPCs |

**Wiring.** Seam: `[32,'E',26,59,'W',0]` (entry, unbuilt, #27). Warp pairs (event, cell ->
destination; `Map059.json` / `Map001.json` / `Map054.json` code 201):
59 EV010 @(87,8) -> map 1 (5,11); 59 EV020 @(88,8) -> map 1 (6,11); map 1 EV001 @(5,12) -> 59
(87,8); map 1 EV006 @(6,12) -> 59 (88,8); 59 EV023 @(31,26) -> map 54 (7,9) facing 8; map 54
EV002 @(7,10) -> 59 (31,26); map 1 EV002 @(5,3) -> map 60 (18,58); map 1 EV005 @(6,3) -> map 60
(19,58). `[auto]` Engine dirs and porymap constants are not assigned; this doc mints none.

## 3. Gates and effects (read from the map JSON)

Thin tier: roster and gates, no beat table. Names from `reference/uranium_switches.json`.

### 3.1 Gates on map 59 / 1 / 54

Only three condition kinds appear on any page in the roster (`output/scratch/ch09_doc_dump.py`):
self-switch A/B (fight done, item taken, berry state), `sw22` (`s:tsOff?("A")`, the door
re-arm idiom, §3.3), and `sw106` ("NIGHT? People", the Luz glows, §3.4). **No page is gated on
a story switch or variable.** `[auto]`

### 3.2 State writes (switch_writes=3)

- **Map059 EV024 @(37,38), page 0**, trigger 4 (parallel), no gate: `121` sets `sw51`
  ("GAME RUNNING") ON, then self-switch A on (`123`). Page 1 (self-switch A) is empty, so it is
  one-shot. `[auto]`
- `sw51` readers: no map page and no script reads it. The only reader is **common event 51**
  ("Only Day people", trigger 2 parallel, gated on `sw51`; `common_events.json`), which the
  repo already documents as the day/night clock updater (`src/rpg2gba/story_state/
  transitions.py:95`, `src/rpg2gba/chapter_manifest/conditions.py:46`). Common events 57 and 60
  carry `switch_id` 51 with trigger 0 (inert). The only other writer in the corpus is Map048
  EV005 (a Moki interior). `[auto]`
- **Map059 EV026 @(21,41), page 0**, no gate, NPC: `121` `sw185` ON, bubble + one message,
  `121` `sw185` OFF. `sw185` is "Menu on event?" (menu-on-event bracket). It is written by ~20
  events across the corpus in this same on/off bracket; **no reader** was found in any map
  page, in `common_events.json`, or by `\b185\b` in `reference/scripts_dump/` (the only hits
  are unrelated numeric tables). `[auto]` (§7 item 3)
- Variable writes: Map059 EV009 p1 script `pbSet(1, result == BR_WIN ? 0 : 1)` writes `var1`
  (scratch var, read back the next row). Not a story variable. `[auto]`

### 3.3 Door / arrival pattern (`sw22`, trigger 1 + trigger 3)

Not NPC walk-ups: the "p0 trigger 1 with a move route, p1 gated `sw22` trigger 3" pairs are
**door-tile events**. Instances: Map059 EV008, EV010, EV020, EV023; Map001 EV002, EV005. Page 0
(player touch) runs the door animation (`208`/`209` player move-route rows on EV010/EV020/EV023
and EV008) then `201` warp; page 1 (autorun, `sw22`) checks `get_character(0).onEvent?` and runs
`setTempSwitchOn("A")` (the arrival-tile one-shot). Same idiom as CH02's cave-arrival tiles
(`reference/chapters/02-route-1.md` §6.2 `setTempSwitchOn`: "used identically to a self-switch-A
ON"; ledger row `command_pokeemerald_map.md:121` "classifier candidate"). Map 1's EV001/EV006
(entry doors) have only a p0 warp, no arrival page. `[auto]`

### 3.4 Luz glow events (strip)

Map059 EV001 @(86,10), EV002 @(89,10), EV003 @(32,28): name "Luz", one page gated `sw106`,
trigger 0, empty command list, graphic `light`, looping move route (`[auto]`, byte-identical in
shape to the Luz entries already stripped for maps 31/32/33/40). **No entry exists** for maps
59/1/54 in `reference/strip_list.json` `map_events` (grep `"map_id": (59|1|54)` returns
nothing). Three entries are owed (§6.3, §7 item 1); maps 1 and 54 have no Luz events.

### 3.5 Trainer rematch page structure (EV009)

Map059 EV009 "Trainer(4)" @(57,26) BUGCATCHER is the only 3-page phone trainer: p0 (fight, then
`pbPhoneRegisterBattle`), p1 (self-switch B, gated `pbPhoneBattleCount>=1`: `createPhoneTrainer`
+ `customTrainerBattle` + `pbSet(1,...)` + `pbPhoneIncrement`), p2 (self-switch A, re-register
prompt). Same shape as Route 1 EV039/EV053 (`reference/chapters/02-route-1.md` B10/B12) and
Route 2 EV023 Brent (`07-route-2-revisit.md:90`). Disposition in the built CH08 suite for the
same shape: p0 walked (`ch08.py:74-76` `m033e039p0`, p2 `m033e039p2`), p1 `unreachable`
(`ch08.py:743`), p1/p2 arms `story-state: unmodelled_outcome:phone_battle_count(trainer)`
(`ch08.py:1045-1050`). Registration is now native (`register_matchcall` behind a yes/no, gated on
the Pokégear flag; #141 DONE 2026-10-21). Expected identical disposition for EV009. `[auto]`

## 4. Coverage targets

Exhaustive. Counts match the CLI (trainer_battles=8, item_grants=8).

### 4.1 Trainer battles (all map 59, trigger 2 touch/sight, p0 fight then p1 idle page)

| Map | Event | Position | Class / name / party | In-chapter reachable? | Notes |
|---|---|---|---|---|---|
| 59 | EV009 Trainer(4) | (57,26) | BUGCATCHER Sack: Smore 11, Sponee 11, Cubblfly 11 | Yes | phone rematch, §3.5 |
| 59 | EV012 Trainer(3) | (16,44) | TUBER_Female Lara: Fartog 12 | Yes | 13-row move route |
| 59 | EV018 Trainer(5) | (80,32) | BLACKBELT Chan: Mankey 12 x2 | Yes | 22-row move route |
| 59 | EV027 Trainer(3) | (39,45) | TUBER_Male Johnny: Grozard 12 | Yes | |
| 59 | EV029 Trainer(4) | (65,41) | SAILOR Marc: Sponee 12, Lotad 13, Fartog 14 | Yes | |
| 59 | EV031 Trainer(4) | (38,35) | LASS Julianna: Feleng 10, Birbie 12, Cubblfly 10 | Yes | |
| 59 | EV032 Trainer(4) | (79,23) | PICNICKER Sophy: Owten 12, Feleng 12, Owten 13 | Yes | |
| 59 | EV050 Trainer(4) | (9,21) | PICNICKER Shauna: Fartog 10, Smore 12 | Yes | |

Eight single battles `[auto]` (`trainers.json` keys TRAINER_{SACK_28,LARA_21,CHAN_27,JOHNNY_22,
MARC_41,JULIANNA_250,SOPHY_42,SHAUNA_249}). Foot reachability: every event on 59 except EV008,
EV011, EV015 is adjacent to the on-foot component entered at the west edge row 17
(`output/scratch/ch09_doc_reach2.py`, static graph, ignores event blockers). Trainer pics:
Uranium `Graphics/Characters/trainer<id>.png` exist for all seven classes (ids 12, 16, 2, 19,
25, 46, 60). Staged in `trainer_converter.common.SLICE_TRAINER_PICS` already: BUGCATCHER (12),
BLACKBELT (16), LASS (2). **Not yet staged: TUBER_Female (19), TUBER_Male (25), SAILOR (46),
PICNICKER (60)**; each needs a `SLICE_TRAINER_PICS` entry and a
`battles._CLASS_PIC_INTERNAL_NAME` row (fork classes `TRAINER_CLASS_TUBER_F/_M`, `_SAILOR`,
`_PICNICKER` exist in `engine/include/constants/trainers.h:455-456,464,484`; the stock front
pics `tuber_f.png`/`tuber_m.png` also exist under `engine/graphics/trainers/front_pics/`, but the
pipeline converts the Uranium art, not those). The Uranium-name -> fork-class map
(`reference/uranium_id_map.json:2124-2125` gives `TRAINER_CLASS_TUBER_FEMALE/_MALE`, which differs
from the fork spelling) must resolve to the fork classes; `[auto]`, resolution not run (§7 item 4).

### 4.2 Item balls / given items

| Map | Item | Event | Gate | In-chapter? |
|---|---|---|---|---|
| 59 | Rare Candy | EV013 @(31,31) | default page | Yes |
| 59 | Water Stone | EV014 @(55,44) | default page | Yes |
| 59 | Star Dust | EV019 @(82,14) | default page | Yes |
| 59 | Repel | EV033 @(87,37) | default page | Yes |
| 59 | TM49 | EV034 @(58,26) | default page | Yes |
| 59 | Burn Heal | EV037 @(27,19) | default page | Yes |
| 59 | TM19 | EV051 @(18,17) | default page | Yes |
| 54 | Net Ball | EV001 @(3,6) | default page | Yes |

All are `Kernel.pbItemBall(::PBItems::X)` with a self-switch-A empty second page `[auto]`.
Berry plants (not item_grants in the census): Map059 EV005 @(74,19) Oran, EV006 @(75,19) Rawst,
EV007 @(76,19) Cheri (reachable, `pbPickBerry` / `pbBerryPlant`, self-switch A) and **EV011
@(110,21) Liechi (Surf pocket, `blocked:surf`)**. Berry mechanic first appeared in CH02
(`02-route-1.md` §6.1).

### 4.3 Wild encounters and obstacles

Encounter table key `"59"` (`wild_encounters.json`; map 1 and 54 have none), `[auto]`:

| Map | Table | Contents | In-chapter reachable? |
|---|---|---|---|
| 59 | `land_mons` (rate 25, 12 slots) | Mankey 9-10, Smore 9-10, Owten 9-10, Smore, Mankey, Owten, Feleng 9-11 x3, Lotad 9-11 x2, Buizel 9-11 | Yes (grass) |
| 59 | `water_mons` (rate 15) | Magikarp 10-15, Folerog 28-30 x2, Brailip 26-28 x2 | **No**: needs Surf (not granted by CH09; Surf pocket included) |
| 59 | `fishing_mons` old/good/super | Old: Fartog 7-10, Lotad 7-10; Good: Lombre 18-22, Folerog 20-24 x2; Super: Folerog 34 x2, Brailip 36 x3 | Old Rod held (CH08 grant), Good/Super Rod **No**; whether the on-foot area touches fishable water is not checked (§7 item 6) |

Species first appearing in the corpus's wild tables for CH01-CH08 (`chapters.json` roster maps vs
`wild_encounters.json`): **Brailip, Buizel, Feleng, Lombre, Lotad, Smore** `[auto]` (the lead's
list omitted Brailip, which is water-only here). No ledges on Route 3, so the ledge-direction
question in MEMORY.md is not answered by this chapter.

**Blocked / out-of-scope rows (not beats), Surf-only east pocket, `blocked:surf`:**

| Map | Event | Cell | What | Note |
|---|---|---|---|---|
| 59 | EV008 | (106,20) | door to dojo map 177 (p0 trigger 1 `201` -> map 177 (9,10); p1 `sw22` arrival tile) | map 177 parked in `unbound_maps`; rebind at the first chapter that reaches the pocket with Surf |
| 59 | EV015 | (105,21) | sign (one message, no state) | blocked:surf |
| 59 | EV011 | (110,21) | BerryPlant (Liechi) | blocked:surf |

Evidence: `output/scratch/ch09_dojo_reach.py`: from (0,17) the foot component holds 1259 cells,
foot+surf 4849; these three events are the only non-Luz events outside the foot component; east
edge reachable cells foot 0, surf 0 (`[auto]`). Other signs/NPCs on 59: EV035 @(13,19) sign (one
message), EV004 NPC @(27,40) (bubble + one message, 7-row move route), EV026 NPC (§3.2). EV041-044
"Stairs" @(43,33),(43,32),(44,31),(44,30): trigger 1, `111` branch on the player's direction
(`[6,-1,4]`), 12 commands each; a `stair_beat` archetype exists (`ch08.py:8` import), whether it covers
this 4-event shape is not checked.

### 4.4 Warps

| Map | Warp | Destination | Chapter-relevant? |
|---|---|---|---|
| 32 / 59 | seam `[32,E,26,59,W,0]` | Moki E <-> Route 3 W | Yes, chapter entry (unbuilt, #27) |
| 59 | EV010 @(87,8), EV020 @(88,8) | map 1 (5,11), (6,11) | Yes |
| 1 | EV001 @(5,12), EV006 @(6,12) | 59 (87,8), (88,8) | Yes (return legs) |
| 59 | EV023 @(31,26) | map 54 (7,9) | Yes (house enter/exit assertion) |
| 54 | EV002 @(7,10) | 59 (31,26) | Yes |
| 1 | EV002 @(5,3), EV005 @(6,3) | map 60 (18,58), (19,58) | **Chapter exit** (CH10 owns map 60; the arriving chapter owns the crossing) |
| 59 | EV008 @(106,20) | map 177 | **No** (`blocked:surf`, §4.3) |

Foot check: the entry foot component from the W edge reaches the doors at (87,8), (88,8), (31,26)
(`ch09_dojo_reach.py` output). Which W-edge rows the seam actually covers is #27's convention;
with the RMXP offset 26 and Route 3 y = Moki y - 26, Moki's post-smash E-edge rows 43-47
(`08-route-1-moki-revisit.md` §7 item 1) land on Route 3 rows 17-21, which is exactly the large
component's W-edge rows (the sign convention itself is open in #27, §7 item 5). `[auto]` pending
#27.

## 5. Wiki vs rxdata discrepancies

**Not checked.** No `Route_3.wiki` is cached (`output/uranium-build/wiki/` has no Route 3
page) and this authoring pass did not fetch one. Nothing in this doc is wiki-sourced. To do at the
walk: compare the trainer count (8), item list (§4.2) and encounter list (§4.3) against the Route 3
wiki page via `scripts/fetch_uranium_wiki.py` (`CH09` `wiki_page`: "Route 3").

## 6. Expected conversion work and risks

### 6.1 Mechanics (census: berry plant, character reference resolver, item ball, phone /
rematch, speech bubble UI, temp switch write, trainer battle, trainer sight, wild encounters)

| Mechanic | First appears here? | Disposition | Ledger row / notes |
|---|---|---|---|
| trainer battle / sight, item ball, wild encounters, speech bubble, berry plant, temp switch, character resolver | No | per ledger | unchanged from CH02/CH08 (`02-route-1.md` §6.1) |
| phone rematch (EV009) | No | native Match Call, §3.5 | `command_pokeemerald_map.md:152`; #141 DONE |
| Seam crossing (map connection) | No (31<->35 shared, 40<->35 remapped) — first remapped **E/W** seam | #27 | entry only; `[auto]` |
| **Map over map-data buffer (130x66)** | **Yes, first in a chapter build** | engine windowed backup grid (#148 DONE) | §6.3 |
| New trainer classes TUBER_F/M, SAILOR, PICNICKER | Yes (pics unstaged) | stage pics, §4.1 | §7 item 4 |

### 6.2 Unmapped script heads

Unmeasured (`unhandled: null`). Script heads seen in the roster pages (`ch09_doc_dump.py`):
`pbCallBub`, `pbTrainerIntro`, `Kernel.pbNoticePlayer`, `pbTrainerBattle`, `pbTrainerEnd`,
`pbPhoneRegisterBattle`, `pbPhoneBattleCount`, `pbPhoneIncrement`, `createPhoneTrainer`,
`customTrainerBattle`, `pbSet`, `pbPickBerry`, `pbBerryPlant`, `Kernel.pbItemBall`,
`setTempSwitchOn`, `get_character`. All appeared in CH02/CH07/CH08. `pbSet` was unmapped in
CH08's census (Map050); here it appears only inside EV009 p1 (the rematch page, `unreachable`
in the CH08 analog). The `unhandled` figure is set by the first staging run, not before.

### 6.3 Backlog carried in / risks

- **#27 Moki E seam**: the chapter's entry; design in a separate plan. This doc only requires
  that the seam exist and that beats assert the crossing.
- **Route 3 is 130x66**, first map over `MAX_MAP_DATA_SIZE` in a chapter build; handled in the
  engine by the windowed backup grid (#148 DONE 2026-10-18; Route 3: 0 screen-check mismatches,
  0 window-vs-layout mismatches). It is **not** in `reference/streamed_maps.json` (`[40,101,122]`),
  so it uses the stock load-once path and is subject to the 1024-tile cap and tile merge. Risk
  record: whether per-map ts24 plus the seam border-strip import (Moki ts22) fits stock caps is
  #27's question (§7 item 5).
- **#111** (`_minimal_sets_for_predicate` blow-up on full-suite runs; found on a 3-4 map
  chapter): live risk for the checker on a 130x66 map with 35 events.
- **#151** viewer/oracle don't read the streamed format or the windowed grid: Route 3 cannot be
  checked in the viewer faithfully; ROM is the authority.
- **#91** no seam-growth audit: `rpg2gba slice-growth` cannot see seam edges, so the 32 E -> 59 W
  crossing is invisible to it (it is the CH01/CH08 `later: CH09` row).
- **#150 residual (E/W)**: engine copies 7 columns into a west neighbour; if the camera shows part
  of an 8th column mid-step on a west-side crossing it reads the border block. No remapped E/W seam
  exists yet; "probe it on the first one (CH09, Moki E <-> Route 3 W)". Applies to the 59 W edge
  (import depth N/S/W 7, E 8 per `connection_remap.strip_depth`).
- **CH01/CH08 beats that assume Moki's E edge is closed.** No beat asserts the edge directly
  (no `blocked edge` beat); the dependence is the rock wall that gates the east exit:
  `ch01.py:885-893` `m032obstacle_rock_smash` (negative obstacle beat, rows EV014/EV015/EV033
  p0), `ch08.py:366-375` `m032smash_rock_smash` (positive smash beat, "releases its own rock
  wall"), and the `later` seam rows `ch01.py:1785` `'map032/seam/E/map059': 'later'`,
  `ch08.py:693` `'map032/seam/E/map059': 'later: CH09'`. Once the seam exists, CH08's
  chapter-end route (`_successor_exit_group`) gains a crossing and **CH01/CH08 suites must be
  regenerated** (§7 item 7). Related: CH08 §7 item 2 ruled "CH09 builds the Moki E seam".
- **Luz strip entries** (§3.4).
- **Trainer pics** for four new classes (§4.1).

## 7. Open items for the lead

1. **Luz strip entries.** Three `map_events` entries owed in `reference/strip_list.json`:
   `{map_id: 59, event_id: 1, 2, 3, expect_name: "Luz"}` (cells (86,10), (89,10), (32,28)); none
   exist for 59/1/54 today. Confirm (evidence: same shape as the map 31/32/33/40 entries; they are
   the only readers of `sw106` on this chapter, so listing them lets day/night stay unbuilt).
2. **Switch 51 readers.** Found: only common event 51 (parallel day/night updater, gated on
   `sw51`). No map page reads it. Confirm EV024's write can be dropped, or emitted as a no-op, with
   the day/night system unbuilt (it only re-asserts a flag common event 51 reads; Map048 EV005 is
   the other writer).
3. **Switch 185 readers.** None found (maps, common events, `reference/scripts_dump/`). Evidence
   that would settle it: a read in the Uranium Scripts RGSS source not present in `scripts_dump`
   (e.g. in a menu-open path), or a confirmation that "menu on event?" is write-only for our
   engine. Treat EV026's on/off bracket as droppable until a reader is shown.
4. **Trainer pics / class resolution.** Stage TUBER_Female (trainer019), TUBER_Male (025), SAILOR
   (046), PICNICKER (060) in `SLICE_TRAINER_PICS` and `_CLASS_PIC_INTERNAL_NAME`; confirm the
   Uranium -> fork class resolution turns `TRAINER_CLASS_TUBER_FEMALE` (trainers.json) into the
   fork's `TRAINER_CLASS_TUBER_F`. Run the trainer stage to settle it; not run here.
5. **Seam geometry vs Route 3 caps (#27 plan).** Does Route 3 (130x66, ts24, not streamed) fit the
   stock tile cap once the Moki ts22 border strip is imported, or does it need adding to
   `streamed_maps.json`; and is the offset sign Route 3 y = Moki y - 26 (so Moki E rows 43-47 meet
   Route 3 rows 17-21)? Evidence: the #27 plan's tileset-count result and the in-ROM crossing probe.
6. **Fishing reachability.** Old Rod is held (CH08). Does the on-foot component border fishable
   water? Evidence: terrain-tag scan of tiles adjacent to the foot component, or a walk.
7. **Regeneration of earlier suites.** CH01/CH08 `later` seam rows (`ch01.py:1785`,
   `ch08.py:693`) and the smash/obstacle beats (§6.3) should be re-checked once the seam is built;
   which suites need regeneration (CH01, CH08, anything replaying them) is the lead's call.
8. **Phone-rematch disposition.** Expected same as CH08's EV039 (§3.5): p0/p2 walked, p1
   `unreachable`, rematch arms `story-state:phone_battle_count`. Confirm once the CH09 manifest
   is generated.
9. **Story-switch gates from CH10+.** None found: every page on 59/1/54 is gated only on
   self-switch, `sw22`, `sw106` (§3.1). Confirm against the generated manifest (the dojo door and
   its map 177 are the only out-of-chapter dependency and they are parked).
10. **Census agreement.** Doc totals equal the live CLI (events 46 = 35+6+5, trainers 8, item
    grants 8, switch writes 3). `chapter_census.json` still lists map 177 (2/3/81), so a re-census
    export would currently print 48/77/620 for events/pages/commands; regenerate it. CLI prints no
    `var_writes` or unmapped-head list for this chapter (`unhandled: null`).
11. **Wiki check** (§5): fetch `Route 3` and compare trainer/item/encounter lists.

**Lead resolutions 2026-10-22.** Item 5 closed by the #27 measurements
(`output/scratch/ch09_seam_budget.py`, `ch09_seam_align.py`): 32 and 59 stay on their own
tilesets (1032 / 1059) with a remapped seam; 59 + Moki's W strip = 749 metatiles / 680 tiles,
32 + Route 3's E strip = 724 / 697, both under 1024/1024, so **Route 3 is not streamed**. The
offset is confirmed: Route 3 y = Moki y − 26 (Moki E rows 26–63 meet Route 3 rows 0–37). The same
convention, checked by walkable-edge alignment, picks the live offsets on 31<->35 and 40<->35. The
plan itself is `PROJECT_TODO.md` #27.

**Lead resolutions 2026-10-22 (pre-walk).** Items 1, 4 and 7 were done in the build (Luz strips,
the four classes with tuber → fork `TUBER_F/_M`, CH08 regenerated to end at the Moki E seam).
- **Item 6 (fishing): reachable on foot.** Terrain-tag scan (`output/scratch/ch09_fish_reach.py`,
  SURF tags 5/7/17): 75 water cells are 4-adjacent to the west-edge foot component, in two
  clusters (x 12–20, y 44–47; and y 16, x 18–20+), e.g. stand (12,46) facing S. Maps 1 and 54
  have no water. Only the Old Rod is held, so only slots 0–1 (Fartog, Lotad) are live. The
  generated suite has no fishing beat; fishing is checked by the operator walk, not the runner.
- **Item 10 (census): done.** `output/chapter_census.json` regenerated: 3 maps, events 46,
  pages 74, commands 539, map 177 gone; equals the CLI and this doc.
- **Item 11 (wiki): matches.** `Route_3` fetched via `scripts/fetch_uranium_wiki.py`: all 8
  trainers match on class, name, species and level (the wiki spells Fartog "Fortog"); the
  8 item balls (Net Ball = map 54 beach house) and Cheri/Oran/Rawst match; Liechi is Surf-only
  on the wiki too; grass, surf and all three rod tables match on species and level. The wiki's
  Poké Radar list (Magikarp, Brailip) is not modelled. That is corpus-wide, not a CH09 item.

**Lead resolutions 2026-10-23 (gate close).** Recorded from the approved suite's review doc.
- **Item 2 (sw51):** EV024 p0's write is emitted and walked (`m059e024p0`: switch + self-switch
  write); harmless with day/night unbuilt (#126). Not dropped.
- **Item 3 (sw185):** EV026's on/off bracket is emitted and walked (`m059e026p0`); no reader,
  no effect. Not dropped.
- **Item 8 (phone rematch):** as expected. EV009 p0 is fought and p2 walked; p1 is
  `unreachable`, and the rematch arms refuse as `unmodelled_outcome:phone_battle_count`.
- **Item 9 (story gates):** none. `chapter_manifest check --chapter CH09` has 0 errors.
- **Found in the walk and fixed in-chapter:** water was a collision wall, so the Old Rod
  refused at the shore (now collision 0 / elevation 1, `cde27560`); look-around trainer
  ambush in the suite (`5f49f7c5`); Uranium fishing sprite (`9a88b039`, `8466e5c5`; the
  south cast is lowered half a tile on purpose, operator ruling).

---

*Companion docs: `reference/chapters/00-atlas.md`, `01-moki.md`, `02-route-1.md`,
`07-route-2-revisit.md`, `08-route-1-moki-revisit.md`, `reference/chapters.json` (CH08/CH09/CH10,
`unbound_maps` 177), `reference/strip_list.json`, `reference/guides/command_pokeemerald_map.md`,
`PROJECT_TODO.md` #27/#91/#111/#141/#148/#150/#151, `BUILD_PLAN.md` (boundary rule).*
