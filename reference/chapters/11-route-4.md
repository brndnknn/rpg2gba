# Chapter 11 — Route 4

**Status:** authored 2026-10-26 at chapter open. Branch `ch11-route-4`. Tier **thin** per
`reference/chapters.json` (CH11 record, `"notes": ""`), with §4 enumerated exhaustively (the content is
small). Not built; no §8. This is a spec a scenario gets written from; gates and effects only, no narrative.
First chapter of Act A3.

**Method note:** read 2026-10-26 from `reference/chapters.json` (CH10, CH11, CH12, CH13, `unbound_maps`),
`reference/act3_scope.md` (§1-§4), `reference/chapters/00-atlas.md` (CH11 row line 130, revisit table lines
314-315),
`output/uranium-build/maps/Map0{76,09}.json` (via `traversal.collision.load_map_json`),
`output/uranium-build/{map_infos,connections,common_events,flag_state}.json`,
`output/uranium-build/intermediate/{wild_encounters,encounters_raw,trainers,trainer_types,map_metadata}.json`,
`reference/uranium_{switches,variables}.json`,
`reference/{strip_list,streamed_maps,seam_warps,item_rulings,battle_rulings,npc_gfx_map,uranium_id_map}.json`,
`reference/chapters/{03-kevlar-town,06-nowtoch-city,09-route-3,10-burole-town}.md`, `BUILD_PLAN.md` (boundary
rule, lines 190-236), `PROJECT_TODO.md` #8, `src/rpg2gba/{trainer_converter/{common,battles}.py,
tileset_converter/{metadata_wiring,map_sections,invisible_wall}.py,traversal/*}`,
`engine/{include/constants/trainers.h,include/constants/rpg2gba_items.gen.h}`,
`chapter_atlas census --chapter CH11`, and scratch scripts `output/scratch/ch11_doc/{dump,reach,data,readers,
tr,gfx,species,fish}.py` (full event dump: `output/scratch/ch11_doc/dump.txt`). Wiki: `Route_4` fetched
2026-10-26 (§5). The transpiler, pipeline and ROM were not run.

---

## 1. Purpose / scope

Act A3, **first chapter of the act**. Predecessor CH10 (Burole Town), successor CH12 (Comet Cave, maps
`[7, 96, 10]`) (`reference/chapters.json`). Roster `"maps": [76, 9]`; `outdoor` 76. No gym; no badge.
Census (`chapter_atlas census --chapter CH11`, run 2026-10-26): maps=2 events=55 pages=99 commands=638
trainer_battles=8 item_grants=11 switch_writes=5 var_writes=3 conditionals=38 move_routes=43. The CLI prints
no `unhandled` count: it is **unmeasured** (maps unstaged), not clean. Events per map: 76=53, 9=2.
Mechanics list from the CLI: berry plant, cave entry/exit, character reference resolver, item ball, phone /
rematch, pushable strength boulder, self-switch write, speech bubble UI, temp switch write, trainer battle,
trainer sight, wild encounters. `[auto]`

`reference/act3_scope.md` §1 prints 790 commands for CH11. That is the raw row count including
continuation and terminator rows (a recount of `list` rows on map 76 alone gives 778); the CLI's 638 is the
comparable figure and is the one used here (§7 item 6).

Mechanically the chapter is:

1. **Entry by door, no seam.** `connections.json` has one row touching the roster, and it is the *northern*
   edge of map 76 (below), not an entry. The player arrives from CH10's exit: map 60 EV032 @(70,22) -> map 9
   (4,8) (`10-burole-town.md` §4.4). The arriving chapter owns that crossing (`BUILD_PLAN.md` boundary rule),
   so **CH11's route starts at the map 60 -> 9 door**. Then map 9 EV002 @(14,8) -> map 76 (18,102).
2. **Route 4 open-air content** (map 76): 8 trainer fights (1 in a Strength pocket), 11 item balls (1 in the
   pocket), 5 berry plants (2 in the pocket), a 12-slot land table, water and rod tables, a single 3-wide
   bridge cell band that every northbound foot route crosses (§3.2).
3. **Forward boundary to Comet Cave (CH12).** Four events on map 76 transfer to map 7 (§4.4). They are this
   chapter's `boundary` rows; CH12 claims the crossing.
4. **Three cave mouths to Route 10 (map 143, CH29)**, all inside the Strength pocket (§3.4).

State on arrival (from CH10): `sw62` ("Gym 2 trainers off", `FLAG_GYM_2_TRAINERS_OFF`) ON, written only by
map 66 EV004 (`ch11_doc/readers.py`); `sw63` OFF; `var106` 0. `[auto]`

## 2. Map inventory

| RMXP id | Uranium identity (`map_infos.json`) | Engine dir | porymap constant | Role in chapter |
|---|---|---|---|---|
| 76 | Route 04 (62x115, outdoor, ts24, parent 55) | not assigned | not assigned | Whole route; 53 events |
| 9 | Route 04 (20x15, ts12, parent 76) | not assigned | not assigned | Gatehouse: two door events, no other content |

Engine dirs and porymap constants are minted at staging, not here. `[auto]` Both resolve to
`MAPSEC_ROUTE_04` (`ROUTE 04`); only map 76 shows the name popup (#140, `map_sections.section_for` /
`shows_map_name`, run 2026-10-26).

**Wiring.** Warp pairs (code 201, param order map, x, y, dir, fade):
map 60 EV032 @(70,22) -> map 9 (4,8) (CH10's exit; claimed here);
map 9 EV001 @(3,8) -> map 60 (70,22) (return leg; map 60 is CH10's, already built);
map 9 EV002 @(14,8) -> map 76 (18,102); map 76 EV001 @(18,102) -> map 9 (13,8) (the arrival cell on 76 is
also the warp tile, handled by the `sw22` idiom, §3.5).
**Out of the roster:** map 76 EV021 @(30,8), EV023 @(30,15), EV034 @(31,15), EV035 @(29,15) -> map 7 (10,51)
(CH12); EV008 @(8,21), EV036 @(8,20), EV037 @(8,22) -> map 143 (149,25) (Route 10, CH29, unbuilt).
**Connection:** `[142,'S',52,76,'N',0]` (`connections.json`, the only row touching 76 or 9): Route 5 (CH13, ts25)
S edge <-> map 76 N edge, offset 52, a remapped connection (ts25 / ts24; `act3_scope.md` §3). Map 142 is not in
the build, so the row is not emitted until CH13 stages it (`tileset_converter/connections.py:85`, "frontier").
Map 76's north edge is Surf-only water: of its 62 N-edge cells, x 40-61 are the only ones reachable even with
Surf, and all are `surf` cells; on foot, none (`ch11_doc/fish.py`). So the connection is not a foot exit
for this chapter even once 142 exists. `[auto]`
Maps 76 and 9 are crossed again at CH32 (visit 2; `00-atlas.md:314-315`); out of scope here.

## 3. Gates and effects (read from the map JSON)

Controlling switches/vars (`reference/uranium_{switches,variables}.json`; registry names from
`output/uranium-build/flag_state.json`, gitignored derived state):
`sw62` "Gym 2 trainers off" (`FLAG_GYM_2_TRAINERS_OFF`), `sw63` "Cometcavebeware", `var106` "Rival Comet Cave
quest", `sw95` "5th leader kidnap on", `sw86` "Has Strength" (`FLAG_HAS_STRENGTH`), `sw185` "Menu on
event?". `sw63`, `var106`, `sw95` have no registry entry yet; they mint at first staging through
`_naming` (CLAUDE.md §6), never by hand.

```
sw62 ON (CH10 gym leader arm)                       <- start gate, already true on arrival
   |
   +--> EV020 p0 (Rivaltheo sheet @(30,10)) appears; EV023/EV034/EV035 p0 arm  (all gated sw62)
   |
bridge band (38..40,44): any northbound foot route crosses it
   EV032 @(38,44), EV033 @(40,44)  funnel the player onto (39,44)
   EV070 @(39,44) p0 (touch): scene, then  sw63 ON        <- end gate (nothing outside map 76 reads sw63)
   |
row y=15, x 29..31: EV035 @(29,15), EV023 @(30,15), EV034 @(31,15) p0 (event-touch): scene, var106 += 1, warp map 7
   (boundary; CH12 claims)
```

### 3.1 Start and end gates

- **`sw62`** is read on this chapter by EV020 p0 and EV023 / EV034 / EV035 p0 only (`readers.py`). It is read
  elsewhere by map 66 (CH10) and map 50 EV027 p2 (Moki); none of those is in this chapter. `[auto]`
- **`sw63`** is written only by map 76 EV070 p0 (`121 [63,63,0]`). It is read only by map 76: EV032 p2, EV033 p2,
  EV070 p1, EV072 p1, each an **empty page** (the scene actors and funnels vanish). No later chapter's
  page reads it, so it gates nothing downstream; it just retires the bridge scene. `[auto]`
- **`var106`** is written only by EV023 / EV034 / EV035 p0 (`122 [106,106,1,0,1]`, add constant 1). It is read
  by EV019 p1, EV020 p1, EV023 / EV034 / EV035 p1 (all empty pages once `var106 >= 1`). No page outside map 76
  reads it. `[auto]`
- **`sw95`** is read by EV011 p2 (changes which speech-bubble page shows; no state) and map 151 EV038 p1; written
  only by map 151 EV038 p0 (a later chapter). Dormant here: EV011 p0 stays live. `[auto]`
- Neither gate is a *chapter prerequisite check*: `sw63` is set on any northbound crossing, and `var106` is set
  by the boundary scene that CH12 claims. End state at the boundary: `sw62` ON, `sw63` ON, `var106` 0.

### 3.2 Bridge band and scene (map 76)

Static reachability (`ch11_doc/fish.py`, walkable graph from the arrival (18,102), obstacles ignored): the
cells (38,44), (39,44), (40,44) are the only walkable cells of row 44 on the foot component, and banning all
three cuts the north (the cave-mouth region, row 15 and up) off from the arrival (554 of 1060 cells remain);
banning only (39,44) does not. So **every northbound foot route steps on the band**. `[auto]`

- EV032 @(38,44) and EV033 @(40,44): blank-graphic, trigger 1 (player touch). Each runs a `209` move route on
  the player (EV032: move right, face up; EV033: move left, face up) then self-switch A; p1 (A) and p2 (`sw63`)
  are empty. Read: they push a player entering a flank cell onto (39,44). Not asserted by running it `[eye]`.
- EV070 @(39,44): blank-graphic, trigger 1, p0 ungated: balloon on the player (`207`), a `209` route walks
  EV072 ("WarnNPC", HGSS_145, starts @(39,37)) 6+ cells toward the player, a speech-bubble row (`pbCallBub(2,72,3)`),
  the NPC walks back, then `121 [63,63,0]` (`sw63` ON). p1 (`sw63`) is empty. EV072 p0 is an idle NPC
  (no commands) until then. `[auto]`
- Wiki disagreement on this trigger: §5 item 1.

### 3.3 Boundary scene (map 76 rows y=15 and y=8)

- **EV035 @(29,15), EV023 @(30,15), EV034 @(31,15)**: identical bodies, trigger 2 (event touch), p0 gated
  `sw62`: map scroll (`203`), balloons (`207`), speech bubbles (`pbCallBub`), `209` routes on EV019 / EV020 /
  the player, an `Exit`-style fade (`223`), then `201` -> map 7 (10,51), then `var106 += 1`. p1 (`var106 >= 1`)
  is empty. Three cells, three independent copies. `[auto]`
- **EV019 "Hiker" @(30,9)** (HGSS_035): p0 idle bubble NPC, p1 (`var106 >= 1`) empty. **EV020 "Theo" @(30,10)**
  (`Rivaltheo` sheet): p0 gated `sw62`, no commands; p1 (`var106 >= 1`) empty.
- **EV021 @(30,8)** (cave mouth): p0 `pbCaveEntrance` + fade + `201` -> map 7 (10,51) + a BGM change (`204`);
  p1 is the `sw22` arrival-tile idiom. The corridor at row 8 is walkable only at x=30 and x=35, and (30,9) is
  1-wide: with EV019 solid on (30,9), (30,8) is **unreachable on foot** (BFS over `MapGraph.neighbors`, banning the NPC cell), while
  (30,15) stays reachable. So until `var106 >= 1`, the only way into map 7 is the row-15 scene, and EV021 is
  reachable only after that scene has run once. `[auto]`
- While map 7 is not in the build, all four events (EV021, 023, 034, 035) are **skipped whole** by
  `metadata_wiring.classify_event` ("out-of-slice warp", `metadata_wiring.py:856`, `any(t not in slice_ids)`),
  not partially emitted. So in CH11's build the scene never fires, `var106` is never written, and EV019 / EV020
  keep their p0. (§7 item 1.)

### 3.4 Strength pocket (west, around the boulder)

EV007 "Boulder" @(9,30) (HGSS_267): p0 `pbPushThisBoulder` (the native `pushable_boulder` template,
`metadata_wiring.py:251-264`); p1 (self-switch A) the same call then `pbSetSelfSwitch(11,"A",true)`, which
flips EV011 "Ranger" @(8,31) to its p1 bubble page (dialogue only). Capability model: one `strength` obstacle
at (9,30), 2892 `surf` obstacles, nothing else (`reach.py`). Holding Rock Smash adds nothing (994 foot cells
with and without it); holding Strength adds 66 cells. The 66-cell pocket contains: EV009 Wyle (trainer), EV083
(TM42), EV041 / EV042 (Occa berry plants), EV008 / EV036 / EV037 (the three Route 10 cave mouths). Strength is
not held until CH25 (`act3_scope.md` §2: `sw86` set on map 140), so the pocket is **`blocked:strength`**
(no chapter-required item or gate sits in it). Same treatment as Route 3's Surf pocket (`09-route-3.md` §4.3).

### 3.5 Other writes and idioms

- **Door / arrival idiom** (same as `09-route-3.md` §3.3): map 76 EV001 and EV008 / EV021 / EV036 / EV037
  have p0 (touch, fade + transfer) and p1 (autorun, `sw22`, `onEvent?` -> `setTempSwitchOn("A")`); map 9 EV001 /
  EV002 are plain p0 touch warps with `Exit Door` SE and fade.
- **`sw185` bracket:** EV003 @(26,28) and EV049 @(32,9) are sign-style action events (`121` ON, message,
  `121` OFF). No reader (`09-route-3.md` §3.2 item 3; emitted and walked as a no-op there).
- **No-op events:** EV050 / EV092 / EV093 "Tree" @(41,87), (41,88), (41,89), EV051 "block" @(43,69), EV076 @(27,79):
  blank graphic, empty list. Only EV050's cell is walkable (the others sit on blocked tiles). By
  `invisible_wall.py` a blank-graphic-only event is not a wall. `[auto]`; EV050's cell `[eye]`.
- **Phone rematch:** EV071 (§4.1): p0 registers the number, p1 (self-switch B) and p2 (A) are the rematch / re-register
  pages. Same shape as `09-route-3.md` EV009 (§3.5 there).
- Variable writes beyond `var106`: none. Switch writes: `sw63` (EV070) and the two `sw185` brackets (4 rows). `[auto]`

## 4. Coverage targets

Exhaustive. Counts match the census (trainer_battles=8, item_grants=11).

### 4.1 Trainer battles

All eight are `pbTrainerBattle` inside a code-111 branch, all trigger 2 (sight); p1 (self-switch A) is a
post-fight bubble NPC. `[auto]` (`ch11_doc/tr.py`, `trainers.json` ids).

| Map | Event | Trigger | In-chapter reachable? | Notes |
|---|---|---|---|---|
| 76 | EV002 Carlton TRIATHLETE_MaleRunner (34,81): Jerbolta 13, Pahar 13 | sight | Yes | trainer id 34; class staged (pic 32) |
| 76 | EV010 Marta SCHOOLKID_Female (29,92): Kinetmunk 14 | sight | Yes | id 33; class id 63 (not the staged id-84 SCHOOLKID) |
| 76 | EV043 Ogilvy FISHERMAN (38,49): Folerog 18 (Poison Sting, Supersonic, Pound) | sight | Yes | id 253; class staged |
| 76 | EV044 Laramie PSYCHIC_Female (35,35): Brailip 14 x2 (Confusion, Water Gun, Harden, Yawn) | sight | Yes | id 254 |
| 76 | EV058 Nelson YOUNGSTER (39,66): Feleng 14, Fartog 14 | sight | Yes | id 40; class staged |
| 76 | EV059 William BLACKBELT (30,28): Baashaun 14, Mankey 14 | sight | Yes | id 35; class staged |
| 76 | EV071 Sr. Goldkorn GENTLEMAN (40,55): Ekans 14, Tancoon 14 | sight | Yes | id 36; **phone rematch**, p0 `pbPhoneRegisterBattle` (`PBTrainers::GENTLEMAN`, 2). Rematch parties exist (id 293: 3 mons at 64; id 268: 6 mons at 70) but are post-chapter |
| 76 | EV009 Wyle PkMnRANGER_Male (12,20): Arbok 33 | sight | **No: Strength pocket (`blocked:strength`)** | id 117; the wiki lists the same L33 Arbok (§5) |

No move named in these parties is in `battle_rulings.json`'s blocked list (checked: Confusion, Water Gun,
Harden, Yawn, Poison Sting, Supersonic, Pound). All 15 species resolve in `uranium_id_map.json`
(`ch11_doc` inline run). `[auto]`

**Trainer pics and classes** (`trainer_converter/common.py:68-115`, `battles.py:73-75,247-269`): classes
resolve to fork classes `TRAINER_CLASS_{TRIATHLETE, PKMN_RANGER, SCHOOL_KID, FISHERMAN, PSYCHIC, YOUNGSTER,
BLACK_BELT, GENTLEMAN}`, all defined in `engine/include/constants/trainers.h`; no WORKER-style gap. Pics are
keyed by Uranium trainer type (`SLICE_TRAINER_PICS`). **Staged:** TRIATHLETE_MALERUNNER (32), FISHERMAN (6),
YOUNGSTER (3), BLACKBELT (16). **Not staged:** PKMNRANGER_MALE (49, Wyle), GENTLEMAN (28), PSYCHIC_FEMALE (62),
SCHOOLKID_FEMALE (63). `trainer049/062/028/063.png` all exist in the Uranium tree. Expected work, §6.3.

### 4.2 Item balls / given items

All `Kernel.pbItemBall(::PBItems::X)` with a self-switch-A empty second page. `[auto]`

| Map | Item | Event | Gate | In-chapter? |
|---|---|---|---|---|
| 76 | Elixir | EV004 @(39,82) | default page | Yes |
| 76 | Ether | EV022 @(40,100) | default page | Yes |
| 76 | Super Potion | EV052 @(30,71) | default page | Yes |
| 76 | TM10 | EV077 @(40,61) | default page | Yes |
| 76 | Thunder Stone | EV078 @(28,39) | default page | Yes |
| 76 | Nugget | EV080 @(47,78) | default page | Yes |
| 76 | Ether | EV081 @(33,27) | default page | Yes |
| 76 | Dusk Ball | EV082 @(27,25) | default page | Yes |
| 76 | TM08 | EV079 @(42,16) | default page | Yes |
| 76 | Bike Wheel | EV084 @(37,24) | default page | Yes (key item; §6.1) |
| 76 | TM42 | EV083 @(14,21) | default page | **No: Strength pocket (`blocked:strength`)** |

No item is `blocked` or ruled in `reference/item_rulings.json` (only ATOMBALL, NUCLEARBALL, HAFLIBERRY, AIRMAIL,
URANIUMCORE are); every id resolves in `uranium_id_map.json`. `ITEM_BIKE_WHEEL` is generated
(`engine/include/constants/rpg2gba_items.gen.h:79`), so no engine-constant gap. No `pbReceiveItem`, no hidden
items in the roster. `[auto]`

Berry plants (not item_grants in the census; `pbPickBerry(item, 2)` then `pbBerryPlant`, self-switch A):
EV038 @(34,88) Sitrus, EV039 @(35,88) Persim, EV040 @(36,88) Chesto: reachable. EV041 @(12,18) and EV042 @(11,18)
Occa: **Strength pocket (`blocked:strength`)**. `[auto]`

### 4.3 Wild encounters and obstacles

Table key `"76"` (`wild_encounters.json`; map 9 has none). `[auto]`

| Map | Table | Contents | In-chapter reachable? |
|---|---|---|---|
| 76 | `land_mons` (rate 20, 12 slots) | Ekans 12-14 x2, Sponee 12-14 x2, Jerbolta 12-14, Tancoon 12-14 x2, Pahar 12-14 x4, Kinetmunk 14-15 | Yes (grass) |
| 76 | `water_mons` (rate 10) | Magikarp 10-15, Frynai 28-30 x2, Brailip 26-28 x2 | **No**: needs Surf |
| 76 | `fishing_mons` old | Magikarp 7-10, Brailip 7-10 | Yes: Old Rod held (CH08 grant, `09-route-3.md` §4.3); **49** `surf` cells are 4-adjacent to the foot component (x 20-49, y 16-102) |
| 76 | `fishing_mons` good | Brailip 18-22, Brailip 24-26, Frynai 19 | **No**: Good Rod not held |
| 76 | `fishing_mons` super | Frynai 34, Brailip 34, Saidine 35, Brailip 36, Saidine 36 | **No**: Super Rod not held |

Species first appearing in the corpus's wild tables for CH01-CH10 (`chapters.json` roster maps vs
`wild_encounters.json`): **Ekans, Frynai, Jerbolta, Kinetmunk, Pahar, Saidine, Sponee, Tancoon** `[auto]`.
Species resolve in `uranium_id_map.json` (Jerbolta is spelled `JERBOLTA`). Frynai / Saidine are Super/Surf only.
Map 76 has 0 ledge cells (`ledges {}`), so the ledge-direction question in MEMORY.md is **not answered** here.
The fishing suite has no beat (`09-route-3.md` §7 item 6 lead resolution); fishing is checked by the operator walk.

**Obstacle summary** (`ch11_doc/reach.py`, from the arrival (18,102)): foot component 994 cells. Foot + Strength:
1060. Foot + Surf (+ Strength): 3359 (surf water adds 2365 cells), and **no event is reachable only by Surf**;
the surf region holds the whole north edge. Not modelled by the capability model: Cut / Flash / Dive tags and
NPC blockers (`act3_scope.md` §2). Rock Smash obstacles on 76: none.

### 4.4 Warps

| Map | Warp | Destination | Chapter-relevant? |
|---|---|---|---|
| 60 / 9 | map 60 EV032 @(70,22) | map 9 (4,8) | Yes, **chapter entry** (CH10's exit; the arriving chapter owns it) |
| 9 / 60 | map 9 EV001 @(3,8) | map 60 (70,22) | Yes (return leg) |
| 9 | EV002 @(14,8) | map 76 (18,102) | Yes |
| 76 | EV001 @(18,102) | map 9 (13,8) | Yes (return leg) |
| 76 | EV035 @(29,15), EV023 @(30,15), EV034 @(31,15) | map 7 (10,51) | **Forward boundary** (`boundary`; CH12 claims). Scene events, gated `sw62`, §3.3 |
| 76 | EV021 @(30,8) | map 7 (10,51) | **Forward boundary** (`boundary`); foot-unreachable until `var106 >= 1` (§3.3) |
| 76 | EV008 @(8,21), EV036 @(8,20), EV037 @(8,22) | map 143 (149,25) | **No**: Strength pocket (`blocked:strength`); map 143 is CH29, unbuilt |
| 142 / 76 | connection `[142,S,52,76,N,0]` | Route 5 (CH13) | **No**: not emitted until 142 is staged; 76's N edge is Surf-only (§2) |

Foot check from the arrival: reachable, ignoring NPC blockers: the doors and every event except the pocket and the
five no-op events (§3.5). `[auto]` (`ch11_doc/reach.py`).

## 5. Wiki vs rxdata discrepancies

Checked against `output/uranium-build/wiki/Route_4.wiki` (fetched 2026-10-26).

1. **Bridge trigger.** Wiki trivia: the bridge scene can be avoided by approaching from the left or right.
   rxdata shows the flank cells (38,44) and (40,44) carry touch events with a player-targeted move route onto
   (39,44), and the band is the only crossing (§3.2). Data wins; `[eye]` at the walk. The wiki's remark that
   the scene can be triggered "from above" is consistent with a touch trigger on (39,44).
2. **No other disagreements** on: the 8 trainers (class, name, species, levels, including Wyle's L33 Arbok); the 11
   item balls (both Ethers present; the wiki names TM10 / TM08 / TM42 as Hidden Power / Bulk Up / Facade, which
   was not checked against the TM table, only the item ids); the berries (wiki "2x" for Sitrus / Persim / Chesto
   and "4x" for Occa is consistent with `pbPickBerry(..., 2)` per plant, one plant each and two Occa plants); the
   land, surf and three rod tables on species and level ranges (the wiki spells Fartog "Fortog"; slot
   percentages were not recomputed).
   The wiki's Poke Radar list (Fartog, Brailip) is not modelled (corpus-wide, `09-route-3.md` §5). The wiki's
   statements that the west entrance needs Strength, and that the north scene needs the second badge, agree with
   §3.4 and `sw62`. `[auto]`

## 6. Expected conversion work and risks

### 6.1 Mechanics (census list)

| Mechanic | First appears here? | Disposition | Ledger row / notes |
|---|---|---|---|
| trainer battle / sight, item ball, wild encounters, speech bubble, berry plant, temp switch, character resolver, self-switch | No | per ledger | unchanged from CH02 / CH09 |
| phone rematch (EV071) | No | native Match Call, #141 done | `command_pokeemerald_map.md:153`; as `09-route-3.md` §3.5 |
| cave entry / exit (`pbCaveEntrance`) | No | native warp fade (ledger `:138`) | only on skipped (out-of-slice) events here |
| pushable Strength boulder (EV007) | No (CH03 Kevlar) | native `pushable_boulder` template; `blocked:strength` | pocket is dormant until CH25 |
| **Forward boundary scene** (3 row-15 copies, `203` scroll / `207` balloons / player-targeted `209` / `223` fade / `201`) | **Yes** | skipped whole while map 7 is unbuilt; CH12 claims | §3.3, §7 item 1 |
| **Player-targeted move-route funnel + bridge scene** (EV032 / EV033 / EV070 / EV072) | Mostly | in-roster, will be emitted; `209` with character `-1` and an NPC-driven route | unmeasured; §7 item 4 |
| Seam crossing | **No seam** in this chapter | the one connection (142 N) is dropped until CH13 | `connections.py:85` |
| **Player movement mode** (PROJECT_TODO #8 / TEMPLATE §3) | **No** | no sprite work: the chapter grants the Bike Wheel (a key item), **not** the Bicycle. `grep -i BICYCLE` over the two map JSONs is empty | the Bicycle grant is map 73 EV001 (CH03's Kevlar), reachable only on a revisit; see §7 item 3 |

### 6.2 Unmapped script heads

Unmeasured (`unhandled: null`). Heads seen on 76 / 9 (`ch11_doc/dump.py`): `pbTrainerIntro`,
`Kernel.pbNoticePlayer`, `pbCallBub` (STRIP / bubble UI), `pbTrainerBattle`, `pbTrainerEnd`,
`pbPhoneRegisterBattle`, `pbPhoneBattleCount`, `pbPhoneIncrement`, `createPhoneTrainer`, `customTrainerBattle`,
`pbSet`, `Kernel.pbItemBall`, `pbPickBerry`, `pbBerryPlant`, `pbCaveEntrance`, `pbPushThisBoulder`,
`pbSetSelfSwitch`, `setTempSwitchOn`, `get_character`. All appeared in CH02 / CH03 / CH09. `pbSet` (EV071 p1)
was unmapped in CH08's census and appears here only inside the rematch page (the same shape as Route 3 EV009).
The `unhandled` figure is set by the first staging run, not before.

### 6.3 Backlog carried in / risks

- **Trainer pics (4).** Add `PKMNRANGER_MALE` (49), `GENTLEMAN` (28), `PSYCHIC_FEMALE` (62),
  `SCHOOLKID_FEMALE` (63) to `SLICE_TRAINER_PICS` (pic names are `battles.pic_internal_name` of the Uranium class;
  CH09 and CH10 precedent). Staged SCHOOLKID (84) is a different Uranium type from Marta's (63).
- **NPC / prop sheets.** 6 distinct sheets used by roster events are absent from `reference/npc_gfx_map.json`:
  `HGSS_122` (EV009, in the pocket), `HGSS_145` (EV072), and the berry props `berrytreeSITRUSBERRY`,
  `berrytreePERSIMBERRY`, `berrytreeCHESTOBERRY`, `berrytreeOCCABERRY` (`ch11_doc/gfx.py`). Berry props follow
  the Rawst / Cheri precedent (`npc_gfx_map.json:451-464`). `Rivaltheo` is mapped (`OBJ_EVENT_GFX_URANIUM_RIVALTHEO`).
  The loader fails loud on an unmapped visible graphic.
- **Strip entries.** None: no `light`-sheet "Luz" events on 76 or 9, and no `strip_list.json` entry for either map.
- **Tileset budget.** Map 76 is 62x115 on ts24 (the same tileset id as Route 3's map 59 and Burole's map 60). Figures on file
  (`act3_scope.md` §3, `tileset_budget()`): **973 tiles / 852 metatiles with merge off, 660 / 653 with merge on**,
  cap 1024. Under the cap either way, but it is a single-map measure, not a real build. Not in `streamed_maps.json` (`[40, 101, 122]`). Map-data size
  (62+15) x (115+14) = 9933 against `MAX_MAP_DATA_SIZE` 10240 (`fieldmap.h`, arithmetic only; moot after the
  windowed grid, #148). Map 9 is on ts12 with Route 3's gatehouse (map 1).
- **Remapped connection** to 142 (ts25 / ts24) is CH13's to build; no work here beyond not breaking it.
- **#111** stall risk applies to a 53-event map; **#151**: map 76 is neither streamed nor windowed-over-buffer, so the
  viewer is usable.
- **Tier / act.** First A3 chapter; `MEMORY.md` says to ask the operator about I6 (#153) and audio (#22) at **the
  end** of an act, not here.

## 7. Open items for the lead

1. **Forward boundary into map 7 and the route's end cell.** The only live path into Comet Cave is the row-15
   scene (EV035 / EV023 / EV034, gated `sw62`) because the Hiker (EV019 @(30,9)) blocks EV021's corridor until
   `var106 >= 1`; all four events are skipped whole while 7 is unbuilt (§3.3). Options: (a) disposition all four
   rows `boundary`, route ends on the row-15 cells (29..31,15), CH12 claims the crossing and `var106` write [recommended;
   `BUILD_PLAN.md:190-198`]; (b) end at the bridge `sw63` write only. Evidence to settle: the generated review doc's
   boundary pick and a `chapter_manifest check --chapter CH11`.
2. **CH10 exit comes alive.** Map 60 EV032 -> map 9 is out-of-slice in the built CH10 and goes live here (CH09 item 7
   precedent: CH08 was regenerated when the Moki seam appeared). Options: (a) run the slice-growth / seam-growth audit
   at open and regenerate CH10's suite only if it flags the row; (b) regenerate unconditionally. Recommend (a).
   Evidence: `rpg2gba` slice-growth output for CH10; not run here.
3. **Bike Wheel without the Bicycle.** CH11 grants the key item (EV084) but the Bicycle grant is map 73 EV001
   (Kevlar, CH03's derived `unreachable` row, `PROJECT_TODO.md` ~1252). Options: (a) CH11 emits and walks the item
   only; the Kevlar arm and the `HERO-BIKE` sprite (#8 table) land at the first chapter that revisits Kevlar and grants
   the Bicycle [recommended]; (b) add a Kevlar revisit leg to CH11 (changes its roster; against the chain). Evidence:
   operator confirmation that "Bike Wheel at CH11" in #8 means the item, not the sprite.
4. **Bridge funnel mechanics.** EV032 / EV033 are player-touch events whose move route targets the player; EV070's
   scene drives EV072 with routes. Whether the transpiler emits `209` with target `-1` inside a touch event, and how
   the generated suite crosses a three-cell band deterministically. Options: take the funnel as emitted and let beats
   step onto (39,44); or stub the funnels. Evidence: first staging run on map 76 (unmeasured).
5. **Strength-pocket dispositions.** Seven rows are `blocked:strength` (EV009, EV083, EV041, EV042, EV008, EV036,
   EV037); EV008 / EV036 / EV037 are also out-of-slice warps to map 143, which could instead read `boundary`. Recommend
   `blocked:strength` (the more basic cause; map 143 is CH29's and the pocket is unreachable regardless). Evidence:
   generated manifest dispositions.
6. **Tile fit for map 76 and census agreement.** Re-measure the real build (973 / 660 figures are single-map
   `tileset_budget()` numbers, not a build measure); the census prints 638
   commands vs `act3_scope.md`'s 790 (counting convention, §1), no action expected. Evidence: a map-76 real-build fit.

### Lead resolutions (2026-10-26, at open)

None of the six needs an operator ruling; each follows a standing rule or is settled by the first build.

1. **(a)** All four map-7 rows `boundary`; the route ends at the row-15 cells. `BUILD_PLAN.md` §2 boundary rule.
2. **(a)** Run the slice-growth audit when CH11's maps enter the build; regenerate CH10's suite only if it flags
   map 60 EV032 (CH09 item 7 precedent).
3. **(a)** CH11 emits and walks the Bike Wheel as an item only. The Bicycle and its sprite belong to whichever chapter
   revisits Kevlar and reaches map 73 EV001. This follows the rxdata and the chain; no fidelity call is involved.
4. Measured at the first staging run. Emit the funnels as written; stub them only if the transpiler or the suite
   can't cross the band, and record why here.
5. `blocked:strength` for all seven pocket rows. The cause is the boulder; map 143 is unreachable either way.
6. Measured at the first real build; no action expected.

### Build findings (2026-10-26)

- **Item 2 resolved:** the slice-growth audit flags map 60 EV032 (as it still flags CH09's gatehouse doors after
  CH10). CH11 claims the crossing; CH10 was regenerated only because map 9's constant changed
  (`MAP_ROUTE_04` -> `MAP_ROUTE_04_GATEHOUSE`, override added: both maps carry the map_infos name "Route 04").
  The module diff was that one line.
- **Item 4 measured — the bridge scene is NOT in the ROM.** EV032/EV033 (funnels) and EV070 (the warning scene)
  are blank-graphic player-touch events with no warp, which `metadata_wiring.blank_touch_drop` drops as inert;
  EV072 (the warning NPC) is hidden on every load. The NPC's approach route now transpiles (in-place jump
  token), but nothing calls it. Corpus-wide 409 blank touch events carry commands; most are deliberate drops
  (ledge/stair helpers, Burole's invisible walls), a few are scenes (here; map 040 EV020/EV021).
  **Operator 2026-10-26: run the suite as is, and REMIND THE OPERATOR before CH11 closes** — the open question
  is whether to emit dialogue-carrying blank touch events as coord events (likely regenerates CH06).
- **Cave mouth (EV021) held out of the plan:** the Hiker and Theo clear only on var106, which only the row-15
  scene writes as the player leaves for map 7. `beat_gen._exit_only_walls` now holds such actors as walls, so
  the route has one exit (the row-15 cells).
- **Sr. Goldkorn** battles as "Goldkorn" (engine name limit 10; operator 2026-10-26). His three parties are
  rematch tiers; the rematch table and the generator take party 0.
- **Pre-existing drift, not CH11's:** regenerating CH01–CH10 on current code changes CH01, CH05 and CH06
  (approach sides; one CH06 warp beat). Those suites were last regenerated 2026-10-17 and are left as
  committed (green on CH10's ROM); a refresh belongs to the next intermission.

---

*Companion docs: `reference/chapters/00-atlas.md` (CH11 row, revisit table), `03-kevlar-town.md` (Bike Wheel, B15b),
`09-route-3.md` (Surf pocket, rematch, door idiom), `10-burole-town.md` (chapter entry, exit), `reference/act3_scope.md`,
`reference/chapters.json` (CH11, CH12), `reference/strip_list.json`, `reference/guides/command_pokeemerald_map.md`,
`PROJECT_TODO.md` #8/#111/#140/#141/#148/#151, `BUILD_PLAN.md` (boundary rule).*
