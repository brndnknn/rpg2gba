# Chapter 10 — Burole Town

**Status:** authored 2026-10-23 at chapter open. Branch `ch10-burole-town`. Tier **thin** per
`reference/chapters.json` (CH10 record, lines 148-152), with §4 enumerated exhaustively (the
content is small). Not built; no §8. This is a spec a scenario gets written from; gates and effects
only, no narrative.

**Method note:** read 2026-10-23 from `reference/chapters.json` (CH10, CH11, CH24, `unbound_maps`),
`output/uranium-build/maps/Map0{60,66,02,04,29,85,90,05,06}.json`,
`output/uranium-build/{map_infos,connections,common_events,flag_state}.json`,
`output/uranium-build/intermediate/{wild_encounters,encounters_raw,trainers,trainer_types,map_metadata}.json`,
`reference/uranium_{switches,variables}.json`, `reference/{strip_list,streamed_maps,seam_warps,item_rulings,npc_gfx_map,uranium_id_map}.json`,
`reference/guides/command_pokeemerald_map.md`, `reference/chapters/{00-atlas,06-nowtoch-city,08-route-1-moki-revisit,09-route-3,06-tileset-plan}.md`,
`src/rpg2gba/{conversion_agent/transpiler.py,trainer_converter/{common,battles}.py,tileset_converter/map_sections.py,traversal/*}`,
`engine/{data/specials.inc,asm/macros/event.inc,src/party_menu.c,src/field_specials.c,include/fieldmap.h,include/constants/trainers.h}`,
`chapter_atlas census --chapter CH10`, and scratch scripts `output/scratch/ch10_doc_{dump,misc,tr,writers,reach,sections,tt,gfx,items,ce}.py`
(full event dump: `output/scratch/ch10_doc_dump.txt`). Wiki: `Burole_Town`, `Burole_Town_Gym` fetched 2026-10-23 (§5).
The transpiler, pipeline and ROM were not run.

---

## 1. Purpose / scope

Act A2, **last chapter of the act**. Predecessor CH09 (Route 3), successor CH11 (Route 4, maps `[76, 9]`)
(`reference/chapters.json`). Roster `"maps": [60, 66, 2, 4, 29, 85, 90, 5, 6]`; `outdoor` 60. Gym 2 is map 66.
Census (`chapter_atlas census --chapter CH10`, run 2026-10-23): maps=9 events=161 pages=229 commands=1860
trainer_battles=8 item_grants=3 switch_writes=68 var_writes=34 choices=16 conditionals=119 move_routes=100;
unmapped script heads: `pbChooseNonEggPokemon` (§6.2). The CLI prints no `unhandled` count for this
chapter: it is **unmeasured** (maps unstaged), not clean. Events per map: 60=68, 66=51, 2=12, 4=5, 29=11,
85=3, 90=3, 5=5, 6=3 (sums to 161). `[auto]`

Mechanically the chapter is:

1. **Entry by door, no seam.** `connections.json` has no row touching any roster map
   (`ch10_doc_reach.py`). Entry is CH09's exit doors: map 1 EV002 @(5,3) -> map 60 (18,58) and EV005 @(6,3)
   -> map 60 (19,58) (`reference/chapters/09-route-3.md:221`). The arriving chapter owns that crossing
   (`BUILD_PLAN.md` boundary rule), so **CH10's route starts at the map 1 -> 60 door**.
2. **Town (map 60), 5 interior doors, Pokémon Center, Mart, 4 shops, a friendship readout NPC, a
   party-for-sale NPC.**
3. **Optional school (map 29):** 4 talk-battles; the last gives a Nugget (§3.2).
4. **Gym 2 (map 66):** 3 sight trainers, a 15-rock puzzle that gates the leader, leader fight, badge + TM (§3.1).
5. **Exit to Route 4** by map 60 EV032 @(70,22) -> map 9 (4,8) (§4.4). Map 9 is CH11's; CH11 owns that crossing.
6. **Metro maps 5, 6: PARKED out of CH10 2026-10-23** (operator); no reachable entrance in CH10. They stay
   bound to CH28, the Burole revisit after CH24 (§2 Wiring, §7 item 1). The roster is now 7 maps; census
   figures in this doc were read with 5/6 included (+8 events; 7-map totals in §7 item 1).

## 2. Map inventory

| RMXP id | Uranium identity (`map_infos.json`) | Engine dir | porymap constant | Role in chapter |
|---|---|---|---|---|
| 60 | Burole Town (80x67, outdoor, ts24, parent 55) | not assigned | not assigned | Hub; 68 events (35 glow, §3.3) |
| 66 | Burole Town(Gym) (42x40, ts32, parent 60; `battle_back: Cave`) | not assigned | not assigned | Gym 2 |
| 2 | Burole Town (PC) (20x20, ts42, parent 60) | not assigned | not assigned | Center: heal, PC, 3 online-service receptionists |
| 4 | Burole Town (Mart) (20x15, ts4, parent 60) | not assigned | not assigned | Mart, mystery-gift NPC (stripped), 2 NPCs |
| 29 | Burole Town (40x20, ts19, parent 60) | not assigned | not assigned | School: two halves joined by internal warps; 4 talk-battles |
| 85 | Burole Town (20x15, ts19, parent 60) | not assigned | not assigned | House, 2 NPCs |
| 90 | Burole Town (20x15, ts19, parent 60) | not assigned | not assigned | House, 2 NPCs |
| 5 | Burole Town(Metro) (20x15, ts19, parent 60) | not assigned | not assigned | Metro entrance hall: ticket kiosk, 2 region-map viewers |
| 6 | Burole Town(Metro) (40x15, ts19, parent 5) | not assigned | not assigned | Metro platform: departure menu (3 ticket-gated warps) |

Engine dirs and porymap constants are minted at staging, not here. `[auto]`

**Wiring.** Warp pairs (code 201, `Map0NN.json`; param order map, x, y, dir):
60 EV001 @(18,58) -> map 1 (5,3) and EV062 @(19,58) -> map 1 (6,3) (return legs to CH09; arrival tiles are
also warp tiles, handled by the `sw22` idiom, §3.4);
60 EV002 @(21,20) <-> map 2 (8,18) (back via map 2 EV002 @(7,19), EV008 @(8,19));
60 EV003 @(22,45) <-> map 4 (10,10); 60 EV044 @(12,41) <-> map 29 (7,13); 60 EV047 @(11,31) <-> map 90 (9,12);
60 EV048 @(14,24) <-> map 85 (9,12);
60 EV004 @(39,7) -> map 66 (19,36) (cave entrance, `pbCaveEntrance`) <-> map 66 EV012 @(19,37) -> map 60 (39,7)
(`pbCaveExit`); map 29 EV007 @(15,5) -> map 29 (37,5) and EV008 @(38,5) -> map 29 (14,5);
60 EV008 @(58,20) and EV009 @(59,20) -> map 5 (8,10), **page 0 gated on `sw85` (METRO MASTER)**;
map 5 EV002 @(8,11) -> map 60 (58,20); map 5 EV001 @(14,4) <-> map 6 EV010 @(5,12);
map 6 EV002 @(10,7) menu -> maps 45 / 168 / 11 (each consumes `TURTICKET`).
**Inbound from outside the roster:** map 1 (CH09); map 9 EV001 @(3,8) -> map 60 (70,22) (CH11);
maps 45 / 168 / 11 (Nowtoch / Legen / Bealbeach metro platforms) -> map 6 (10,8)
(`ch10_doc_reach.py`). `[auto]`

**Metro disposition.** `sw85` is written ON only at map 167 EV013 and EV018 (Legen Town, CH24;
`ch10_doc_writers.py`), so map 60's metro doors are dead through CH10: p0 of EV008/EV009 needs `sw85`, and
NPCs EV015 @(59,21) and EV020 @(58,21) stand in front of them until `sw85` (their p1 is empty). Maps 5 and 6
are therefore reachable in CH10 only by a ticket ride from another town's platform. Precedent: the operator
parked CH06's metro maps 44/45 on 2026-10-10 with the rule "rebind at the first other station the chain
reaches; decide then between folding in and one Metro chapter" (`reference/chapters.json:457-458`,
`reference/chapters/06-nowtoch-city.md:32-37`). **Ruled 2026-10-23 (operator): park 5/6**, per the dojo rule (no reachable entrance → not built). They
are not in `unbound_maps`: CH28 still binds them, and a map cannot be both (`tests/test_chapter_atlas.py`
`test_bound_and_unbound_maps_account_for_the_whole_corpus`). The 44/45 rebind is decided at CH28. Map 60
EV008/EV009 are chapter-boundary warps (gated, never fire in CH10); NPCs EV015/EV020 stay as map-60 content.
CH28 (Burole revisit, after CH24 sets `sw85`) already lists 5/6 and is the natural rebind point.

## 3. Gates and effects (read from the map JSON)

Controlling switches/vars (`reference/uranium_{switches,variables}.json`; registry names from
`output/uranium-build/flag_state.json`, which is gitignored derived state):
`sw62` "Gym 2 trainers off" (`FLAG_GYM_2_TRAINERS_OFF`, flag_state.json:17, status "proposed" at :243),
`sw67` "Gym 2 Gempuzzle", `var108` "Gym 2 Gempuzzle", `var107` "Battle Var School", `sw85` "METRO MASTER"
(`FLAG_METRO_MASTER`), `var43` "Reserved - Pokemon Count", `sw5` "Starting Over". `sw67`/`var108`/`var107`
have no registry entry yet; they mint at first staging (§4.3 of `CLAUDE.md`: names via `_naming`).

```
var108 = random 0..14  (map 66 EV021, parallel, runs once: self-switch A)
   |
   v   hit the rock whose index == var108 (one of 15 rocks, map 66)
sw67 OFF -> ON  --(pillar EV045, action button, needs sw67)--> opens the leader's corridor (self-switches)
   |
   v   defeat leader (map 66 EV004)
badge[1] (FLAG_BADGE02_GET) + TM31 + sw62 OFF -> ON  (sw62 only inside the TM-granted arm)

var107 += 1 per school battle won (maps 29 EV002, EV009, EV010), James (EV011) page 1 needs var107 >= 3
   -> Nugget page needs var107 >= 3 and James's self-switch A
```

### 3.1 Gym 2 (map 66), same terms as CH06's gym (`06-nowtoch-city.md:57,94-96,117`)

- **Trainers:** EV001 Tod (10,21), EV002 Jang (18,25), EV003 Martin (29,21): p0 trigger 2 (sight) fight,
  p1 (self-switch A) idle, p2 (`sw62`) idle. No page elsewhere reads their self-switches, so **they are not
  gates** to the leader. `[auto]`
- **Puzzle:** EV021 @(17,38) (trigger 4, parallel, no gate): `122` sets `var108` = random(0..14), then
  self-switch A. 15 rock events (ids 5-11, 13-20, graphic `fk107-rocksmash`) each: `111 Kernel.pbRockSmash`
  -> sound + move route, self-switch A (rock gone, page 1 empty = does not respawn), then `111 var108 == N`
  (N is unique per rock, 0-14): arm A = `sw67` ON + ME jingle; else arm B = `Kernel.pbRockSmashRandomEncounter`.
  So exactly one rock sets `sw67`; which one is random per game. `[auto]`
- **Pillar:** EV045 "Pillar" @(19,16), trigger 0, p0: `111 sw67 ON` -> quake effect, `pbSetSelfSwitch` on EV046,
  EV047 (Pillar2) and EV048-053 (Fakefloor) via a `for i in 48..53` loop, self-switch A on itself. p1 empty. Without
  `sw67` the page does nothing. Static reachability (`ch10_doc_reach.py`, ignores event blockers) puts the pillar
  and the leader both adjacent to the on-foot region from the entrance (19,36), so the pillar is the gate. `[auto]`
- **Leader:** EV004 "Davern" @(19,5), p0: `pbTrainerBattle(LEADER_Caff,"Davern")` win arm: `$Trainer.badges[1]=true`
  (-> `FLAG_BADGE02_GET`, `transpiler.py:607-611`), ME, `Kernel.pbReceiveItem(TM31)`; inside the TM-granted arm:
  `sw62` ON + self-switch A. p1 (self-switch A) idle. **No `VAR_QUEST_LOG` write** (CH06's leader did
  +1 on it; none of `var101` is written anywhere in this chapter). `[auto]`
- **Other gym events:** EV024 @(17,34) gives Fresh Water once (p0 default, self-switch A; p2 `sw62` idle);
  EV025-032 "Stairs" (8 events, trigger 1, `111` on player direction 6 or 4, move route; the stair idiom);
  EV033-044 "fog1" (12 events, trigger 1, `111` direction 8, `206` fog opacity; visual, STRIP per ledger
  line 162). Badge 2 opens no HM gate: `capabilities.py:95-96` lists badge indices Flash 0, Rock Smash 1, Cut 3,
  Strength 4, Surf 5, Dive 7, Waterfall 8. `[auto]`

### 3.2 School (map 29, second-floor half x >= 28)

EV002 Diana (28,9), EV009 Rich (37,10), EV010 Tracey (34,5): trigger 0 (talk) -> yes/no -> `pbTrainerBattle`
inside the yes arm; on win `122 var107 += 1` and self-switch A; p1 idle. EV011 James (31,6): p0 flavour; p1
(`var107 >= 3`) yes/no + battle, win -> self-switch A; p2 (`var107 >= 3` and A): `pbReceiveItem(NUGGET)` then
self-switch B; p3 (B) idle. EV003-006 (first-floor NPCs) have only the `sw185` bracket. `[auto]`

### 3.3 Glow events (strip)

Map 60 has **35** events with graphic `light`, one page gated `sw106` ("NIGHT? People"), empty command list,
looping move route: 33 named "Luz" and two unnamed (EV041 @(17,66), EV071 @(20,66)). Ids: 21-30, 33-41, 65, 66, 71,
72-84. Same shape as the entries already stripped for maps 31/32/33/40/59. **No `map_events` entry exists for
any roster map** (`reference/strip_list.json`, all `map_id` values: 33, 31, 32, 40, 59, 49). 35 entries owed
(§6.3, §7 item 4). Maps 66, 2, 4, 29, 85, 90, 5, 6 have none. `[auto]`

### 3.4 Door / arrival idiom

Same as CH09 §3.3: door events (map 60 EV002, EV003, EV044, EV047, EV048 with door animation rows `208`/`209`;
EV001/EV062/EV004/EV008/EV009 with a plain fade) run p0 (touch) -> `201`; p1 (autorun, `sw22`) -> `onEvent?` ->
`setTempSwitchOn("A")`. EV032 (Route 4 exit) differs: its p1 gate is `sw12` (`s:tsOn?("A")`), p0 ungated. `[auto]`

### 3.5 Other writes and brackets

- `sw185` ("Menu on event?") on/off bracket around NPC pages (60 EV005, 010, 013-017, 043; 29 EV003-006; 85 EV001-002;
  90 EV001-002): no reader known (`09-route-3.md` §7 items 3/9 emitted and walked it as a no-op). Treat the same.
- `var102` (People Talking) `122` random(0..N) pick drives NPC flavour branches (60 EV010, 012-017; 2 EV004, EV007;
  29 EV003-006; 85, 90 NPCs). Flavour only. `var43`/`sw5`: the Center nurse (map 2 EV001: `var43` = party size, `sw5` OFF on p1 white-out
  arrival). `[auto]`

## 4. Coverage targets

Exhaustive. Counts match the census (trainer_battles=8, item_grants=3).

### 4.1 Trainer battles

| Map | Event | Trigger | In-chapter reachable? | Notes |
|---|---|---|---|---|
| 66 | EV001 Tod HIKER (10,21): Grozard 14 x2 | sight | Yes | `TRAINER_TOD_30` |
| 66 | EV002 Jang BLACKBELT (18,25): Tonemy 14 x2 | sight | Yes | `TRAINER_JANG_31` |
| 66 | EV003 Martin WORKER (29,21): Barewl 14 x2 | sight | Yes | `TRAINER_MARTIN_32`; class has no fork constant (below) |
| 66 | EV004 Davern LEADER_Caff (19,5): Grozard 15, Modrille 15, Dearewl 15, Tofurang 16 (4 moves set), items Potion x2 | talk | Yes, behind the puzzle (§3.1) | `TRAINER_DAVERN_29` (party matches the wiki). `trainers.json` also holds `TRAINER_DAVERN_274` (6 mons at 70); which key the event's `pbTrainerBattle` resolves to is not confirmed here (§7 item 8) |
| 29 | EV002 Diana SCHOOLKID (28,9): Cubblfly 14, Smore 14 | talk + yes | Yes | `TRAINER_DIANA_43` |
| 29 | EV009 Rich TUBER_Male (37,10): Orchynx 12, Raptorch 12, Eletux 12 | talk + yes | Yes | `TRAINER_RICH_44` |
| 29 | EV010 Tracey SCHOOLKID_Male (34,5): Tonemy 12, Grozard 12, Barewl 13 | talk + yes | Yes | `TRAINER_TRACEY_45` |
| 29 | EV011 James YOUNGSTER (31,6): Dunsparce 12, Kinetmunk 14, Barand 14 | talk + yes, p1 `var107>=3` | Yes after 3 wins | `TRAINER_JAMES_46` |

`[auto]` (`ch10_doc_tr.py`). **Trainer pics and classes** (`trainer_converter/common.py:69-109`,
`battles.py:66-100`; Uranium `trainerNNN.png` exists for ids 3, 4, 13, 16, 22, 25, 71, 84, 87,
`ch10_doc_gfx.py`):
staged already: HIKER (4), BLACKBELT (16), YOUNGSTER (3), TUBER_MALE (25), SCHOOLKID (84).
**Not clean:** (a) WORKER (Uranium id 22, display "WORKER"): `resolve_trainer_class` derives
`TRAINER_CLASS_WORKER`, and `grep WORKER engine/include/constants/trainers.h` returns nothing, so staging
fails loud until a class ruling exists; (b) SCHOOLKID_MALE (id 13, Tracey) resolves to the same fork class
`TRAINER_CLASS_SCHOOL_KID` as staged SCHOOLKID (id 84, female), and the pic map is keyed per fork class,
so Tracey would take Diana's pic; (c) LEADER_Caff (id 87) resolves to `TRAINER_CLASS_LEADER`, whose pic row
is Maria's `LEADER_ROXANNE` (id 71) and whose comment says "a second leader needs a per-trainer pic"
(`battles.py:81-84`). The leader class has gender-keyed music rows; Davern's type is Male
(`trainer_types.json`). §7 item 5.

### 4.2 Item balls / given items

| Map | Item | Event | Gate | In-chapter? |
|---|---|---|---|---|
| 66 | TM31 | EV004 | win vs Davern | Yes |
| 66 | Fresh Water | EV024 @(17,34) | default page, self-switch A | Yes |
| 29 | Nugget | EV011 p2 @(31,6) | `var107 >= 3` and James's fight won | Yes |

No `pbItemBall`, no berry plants, no hidden items in the roster. `[auto]` Purchases (not grants):
map 60 EV005 Lisa's shop (Energy Powder, Energy Root, Heal Powder, Aromatic Herb, Sachet, Destiny Knot; gated
on a yes/no), EV006 ball vendor (Dusk, Heal, Level, Lure, Repeat, Net, Nest), EV018 (Oran, Sitrus, Pecha berries,
X Accuracy); map 4 EV002 Mart (Poké Ball, Great Ball, Super Potion, Potion, Antidote, Ice Heal, Parlyz Heal,
Repel, Escape Rope); map 5 EV003 kiosk (`TURTICKET`). Every item resolves in `uranium_id_map.json`;
Aromatic Herb is generated as a held item (`item_rulings.json`, `"AROMATICHERB": held`). `[auto]`
Party-for-sale NPC: map 60 EV007 offers Mareep (12), Pahar (10), Magikarp (8) via `Kernel.pbAddPokemon`
after a funds check (`3800>$Trainer.money` etc.) and `$Trainer.money-=<price>`.

### 4.3 Wild encounters

| Map | Table | Contents | In-chapter reachable? |
|---|---|---|---|
| all 9 | none | `wild_encounters.json` and `encounters_raw.json` have no key for 60, 66, 2, 4, 29, 85, 90, 5, 6 | n/a |

`[auto]`. Consequences: no grass table; map 60's lake (301 `surf`-tagged cells, `ch10_doc_reach.py`) has no water or
fishing table, so Old Rod yields nothing here; the 15 gym rocks call `pbRockSmashRandomEncounter` against no
table (native `RockSmashWildEncounter` returns FALSE on a NULL table, `08-route-1-moki-revisit.md:263`).
Rock Smash is held in this chain (HM06 from CH06; `08-route-1-moki-revisit.md:337` "held is derived"), and the gym
rocks are the 15 `rock_smash` obstacles the traversal model finds on map 66. Surf is not held: the lake
region adds 200 reachable cells and no event (`ch10_doc_reach.py`). Map 60 has 0 ledge cells, none on any
roster map (`ch10_doc_reach.py`), so the ledge-direction question in MEMORY.md is **not answered** here.

### 4.4 Warps

| Map | Warp | Destination | Chapter-relevant? |
|---|---|---|---|
| 1 / 60 | map 1 EV002, EV005 | map 60 (18,58), (19,58) | Yes, chapter entry (CH09's doors) |
| 60 | EV001, EV062 | map 1 (5,3), (6,3) | Yes, return legs |
| 60 | EV002, EV003, EV044, EV047, EV048 | maps 2, 4, 29, 90, 85 | Yes |
| 60 / 66 | EV004 / EV012 | gym (19,36) / town (39,7) | Yes |
| 29 | EV007, EV008 | internal pair | Yes |
| 60 | EV032 @(70,22) | map 9 (4,8) (Route 4, CH11) | Yes, **chapter exit** (CH11 owns the crossing) |
| 60 | EV008, EV009 | map 5 (8,10) | **No**: p0 gated `sw85` (set in CH24) |
| 5 / 6 | EV001, EV010, EV002 | internal and back to 60 (58,20) | **No**: reachable only by ticket ride (§2) |
| 6 | EV002 menu | maps 45, 168, 11 | **No**: ticket-gated; 168 and 11 not yet built, 45 parked |

`[auto]` Foot reachability from the arrival (18,58): every non-glow event on map 60 is adjacent to the 1070-cell
on-foot region (`ch10_doc_reach.py`), including the Route 4 exit and the metro doors.

## 5. Wiki vs rxdata discrepancies

Checked against `output/uranium-build/wiki/Burole_Town.wiki` and `Burole_Town_Gym.wiki` (fetched 2026-10-23).

1. **Friendship thresholds.** Wiki's table: 255 / 200-254 / 150-199 / 100-149 / 50-99 / 1-49 / 0. The rxdata
   ladder in map 60 EV042 is `stage 1 if h>=1, 2 if >=50, 3 if >=100, 4 if >=150, 5 if >=220, 6 if >=255`. The
   fifth step is **220 vs the wiki's 200**. Data wins. The engine's native `GetLeadMonFriendship` uses 200
   (`engine/src/field_specials.c:4607-4624`), so it would follow the wiki, not the data (§6.1).
2. **No other disagreements** on: the eight trainers (class, name, species, levels all match; gym
   trainers 14 x2, school 12-14), Davern's party levels 15/15/15/16 and his Tofurang moves, his 2 Potions, TM31,
   the Fresh Water NPC at the gym entrance, the Nugget needing all four school fights, the party-for-sale NPC
   (Mareep 3800 L12, Pahar 2500 L10, Magikarp 500 L8), and every shop list (Lisa's, ball vendor, consumables,
   Mart). The wiki's Davern moves for Grozard/Modrille/Dearewl are not in rxdata (no move list set; default
   learnset), so not comparable. Wiki's "find the Bright Gem among boulders" matches the 15-rock puzzle; the wiki's
   count is unstated. Wiki says the Underground is unusable on first visit; rxdata agrees through `sw85`.
   No wild tables on the page, none in rxdata. `[auto]`

## 6. Expected conversion work and risks

### 6.1 Mechanics (census list)

| Mechanic | First appears here? | Disposition | Ledger row / notes |
|---|---|---|---|
| trainer battle/sight, item grant, speech bubble, self-switch, temp switch, character resolver, cave entry/exit, PC access, poke mart, gift pokemon, white-out anchor, rock smash + encounter | No | per ledger | `command_pokeemerald_map.md:120,123,126,136,138,164`; unchanged from CH01-CH08 |
| **15-rock random-gem puzzle** (third arm `var108 == N` inside the rock idiom) | **Yes** | needs a transpiler look: the rock idiom drops both arms and `goto(EventScript_RockSmash)` (`08-route-1-moki-revisit.md` §7 item 6); here a per-rock `sw67` arm sits between | §7 item 3 |
| **Pillar open scene** (quake + `for` loop of `pbSetSelfSwitch`) | Yes | `pbSetSelfSwitch` loop handled (`transpiler.py:131-143,1923`); quake is `special ShakeCamera` (ledger 101) | |
| **Party pick + friendship readout** (map 60 EV042) | Mostly | `pbChooseNonEggPokemon` unmapped, §6.2 | §7 item 2 |
| **Shop-with-haggle party sale** (EV007) | Yes | `givemon` (`event.inc:1052`), `checkmoney`/`removemoney` (`event.inc:1350-1366`) | `$Trainer.money` has no `transpiler.py` hit (grep), unmeasured |
| region map (map 5 EV004/EV005) | Built-chapter first use unconfirmed | `special FieldShowRegionMap` (`06-nowtoch-city.md:212`) | CH06 recorded it first, then parked its map |
| online-service receptionists (map 2 EV009, EV010, EV012 -> common events 5 "VT", 6 "LOBBY", 4 "GTS/WT") | No (CH06 map 43 has the same) | CH06 line 58 | their lists include `system("start http://...")` and a randomizer branch: strip candidates, §7 item 6 |
| pokerus check (map 2 EV001), mystery-gift id (map 4 EV003 p1, `sw31`) | check: folded to else arm (`transpiler.py:790-800`, deferred); gift: census "stripped" | | `sw31` is a runtime predicate, never a stored flag |
| Seam crossing | **No seam** | | `connections.json` empty for the roster |
| **Player movement mode** (PROJECT_TODO #8 / TEMPLATE §3) | **No** | no sprite work | none of the 3 grants, the shops or any event gives Bike, Surf, surfboard or Dive: `grep -i "BICYCLE|SCUBA|SURFBOARD|SURF|DIVE"` over the nine map JSONs is empty. `[auto]` |

### 6.2 Unmapped script heads

- **`pbChooseNonEggPokemon(1,2)`, 1 use: Map060 EV042 "Dr Footstep" @(55,32), p0**, inside the yes arm of a
  yes/no. Defined `reference/scripts_dump/170__PSystem_Utilities.rb:2079`: opens the party menu with an
  egg filter, stores the chosen slot in game var 1 (-1 on cancel) and the nickname in var 2. Page continues: `111 var1 < 0`
  -> exit; then Ruby `poke=pbGetPokemon(1); h=poke.happiness; stage=…` ladder (§5), `pbSet(3,stage)`, and a 7-way `111`
  branch on `var3` (one message each). No state is written beyond scratch vars 1-3.
  **Native analog, searched (§4.7):** `special ChoosePartyMon` (`engine/data/specials.inc:182`,
  `waitstate=1`; `engine/src/party_menu.c:7889-7904`) opens the choose-mon party menu and `BufferMonSelection`
  stores the slot in `VAR_0x8004`, `PARTY_NOTHING_CHOSEN` on cancel (`party_menu.c:7835-7841`). The egg filter is
  reachable natively: `ScriptGetPartyMonSpecies` returns `MON_DATA_SPECIES_OR_EGG` for slot `VAR_0x8004`
  (`field_specials.c:1641-1644`). **Friendship of an arbitrary slot has no special**: the only readers are
  `GetLeadMonFriendship` (lead mon only, stage 0-6, `field_specials.c:4607-4624`, `specials.inc:582`) and
  `GetLeadMonFriendshipScore` (`specials.inc:253`); `grep MON_DATA_FRIENDSHIP src/scrcmd.c` is empty. So the
  unknowns are the stage source (lead-only approximation, or a small new special) and the 200-vs-220 step
  (§5 item 1): §7 item 2. Ledger class: `pbChoose*Pokemon` is JUDGE (`command_pokeemerald_map.md:169`).
- Other heads seen, all handled elsewhere in the repo or ledgered: `pbCallBub` (STRIP), `pbSetPokemonCenter` (STRIP),
  `pbPokeCenterPC`, `pbShowMap`, `pbCaveEntrance`/`pbCaveExit`, `pbTrainerIntro`/`Kernel.pbNoticePlayer`/`pbTrainerEnd`,
  `pbPokemonMart`, `Kernel.pbReceiveItem`, `Kernel.pbAddPokemon`, `Kernel.pbRockSmash`, `Kernel.pbRockSmashRandomEncounter`,
  `pbSetSelfSwitch`, `setTempSwitchOn`, `get_character(0).onEvent?`, `$PokemonBag.pbQuantity`/`pbDeleteItem`,
  `$Trainer.party.length`, `$game_map.need_refresh`. Random-operand `122` is handled (`transpiler.py:4447-4453`).
  `Kernel.pbPokerus?` (folded), `pbNextMysteryGiftID` / `pbReceiveMysteryGift` (strip; ledger `:143` ⚠RECHECK).
  Not found by grep in `transpiler.py`: `$Trainer.money-=` and the money-compare condition (§6.1).

### 6.3 Backlog carried in / risks

- **Glow strips (35 entries, map 60)**, §3.3. **NPC sheets:** 9 of 41 distinct character sheets used by roster
  events are absent from `reference/npc_gfx_map.json` (91 entries): `HGSS_047` (60 EV007), `HGSS_191` (EV011),
  `HGSS_226` (EV014), `HGSS_052` (EV042), `HGSS_131` (EV086), `PU-doorsdew` (EV044/047/048), `HGSS_041` (66 EV003),
  `PU-Davern` (66 EV004), `PU-BurolePillar` (66 EV045). The loader fails loud on an unmapped visible graphic.
- **Trainer classes/pics** (§4.1): WORKER has no fork class; SCHOOLKID_MALE and LEADER_Caff share a staged fork class.
- **Tileset budget.** Map 60 is 80x67 on ts24 (the same tileset id as Route 3's map 59). The only figure on file is
  **952 tiles at the K=4 merge** (`reference/chapters/06-tileset-plan.md:330`, "Fit with the K=4 merge alone, no split:
  60 Burole CH28 (952)"). That file is headed 2026-10-04 (its merge section 2026-10-06), was written for CH28, and
  **predates** the streaming/11-bit engine work (2026-10-16/18) and the per-map tileset build; do not treat it as
  current. Not in `streamed_maps.json` (`[40, 101, 122]`); `connections.json` has no row for any roster map; a grep of
  `seam_warps.json` for 60/66/29/85/90 is empty (ids 2/4/5/6 not grepped, moot with no connection).
  Map data size: (80+15) x (67+14) = 7695 against `MAX_MAP_DATA_SIZE` 10240 (`fieldmap.h:17,25-27`), arithmetic only,
  not cross-checked against #148's list. Re-measure at open (§7 item 7).
- **Map-name popup (#140):** all nine maps resolve to `MAPSEC_BUROLE_TOWN` ("BUROLE TOWN"); only map 60 shows the popup
  (`ch10_doc_sections.py`, `map_sections.section_for`). No fail-loud maps.
- **#111** stall risk applies to a 68-event map; **#151** viewer cannot be trusted on a streamed/windowed map, but map 60 is
  neither, so the viewer is usable for it.
- **A2 close:** this is the act's last chapter; `MEMORY.md` says to ask the operator about I6 (#153) and audio (#22) at
  its close.

## 7. Open items for the lead

1. **Metro rebind decision.** Maps 5, 6 are in the CH10 roster, but their only in-chapter entrance is dead (`sw85`
   unwritten until CH24), and CH06's parked maps 44/45 carry the rule "decide at the first other station the chain reaches".
   Options: (a) build 5/6 as roster-only, inert (departure menu skipped whole because 168 and 11 are unbuilt and 45 is
   parked, per the CH06 out-of-slice-warp precedent, `06-nowtoch-city.md:299-303`); (b) fold 44/45 in as well; (c) park 5/6 too.
   Evidence to settle: operator ruling. Also whether an all-inert pair satisfies the atlas coverage identity.
   **RESOLVED 2026-10-23 (operator): (c) park 5/6** out of CH10; still bound to CH28 (§2 Metro disposition).
   7-map census (2026-10-23): events=153 pages=221 commands=1702 trainer_battles=8 item_grants=3
   switch_writes=68 var_writes=34 choices=11 conditionals=116 move_routes=98; unmapped head unchanged.
2. **EV042 friendship readout.** Pick: lead-only approximation of `GetLeadMonFriendship`, or a new special that reads
   `MON_DATA_FRIENDSHIP` for `VAR_0x8004`, and the 200-vs-220 step (§5 item 1). Evidence: operator ruling on fidelity;
   confirm no existing macro reads another slot (searched `specials.inc`, `scrcmd.c`, `event.inc` only).
3. **15-rock gem puzzle.** Does the transpiler's rock idiom accept the extra `var108 == N` arm, and how is the random
   `var108` init reproduced (the suite must hit the right rock deterministically; seeded engine RNG, or the beat reads
   the var)? Evidence: staging run on map 66, and a look at how the manifest models `random(15)`.
4. **Strip entries.** 35 `Luz`/glow `map_events` entries for map 60 (§3.3), ids listed there; EV041/EV071 are named
   "EV041"/"EV071", so `expect_name` needs those names. Confirm.
5. **Trainer classes/pics.** WORKER (no fork class), SCHOOLKID_MALE (pic collision), LEADER_Caff (per-trainer pic).
   Evidence: class ruling (map WORKER to an existing fork class?), per-trainer pic mechanism.
6. **Online-service receptionists (map 2) and web call.** Strip or stub common events 4/5/6? Evidence: CH06's treatment of
   its identical map 43 receptionists (`06-nowtoch-city.md:58`; not checked beyond that line).
7. **Tileset fit for map 60.** Re-measure with the current build (952 is 2026-10 stale). Evidence: a map-60-only real-build
   fit, not run here.
8. **Davern's trainer key.** `TRAINER_DAVERN_29` (15-16 party, matches wiki) vs `_274` (6 mons at 70). Evidence: how
   `trainer_converter` keys `pbTrainerBattle(LEADER_Caff,"Davern",...)` (party id), not run here.
9. **Census `unhandled` is unmeasured** (`unhandled: null`, maps unstaged). The rest of EV042's Ruby block (`pbGetPokemon`,
   `.happiness`) and `$Trainer.money` may add unmapped heads the census list does not show. Evidence: first staging run.
10. **Money / purchase arm.** Whether the transpiler emits `checkmoney`/`removemoney` for EV007's `$Trainer.money` forms.
   Evidence: staging run.
11. **Map 66 `battle_back: Cave`** in `map_metadata.json`: confirm the engine battle-background mapping covers it.
12. **Leader events with a full bag.** The `sw62` write sits inside the TM-granted arm, so a full bag after the badge write
    leaves `sw62` OFF; not resolved here whether the suite needs a refusal beat.
13. **Wiki check:** done (§5); only item 1 of §5 differs.

### Gate close-out (2026-10-26)

**CH10 GATE PASSED 2026-10-26** — operator walked the gym and the end state; gen suite 673/673 on the
rebuilt ROM (2026-10-25). Items 2-12, as the built chapter has them:

2. **Done.** New special `GetPartyMonFriendshipStageRpg2gba` (`engine/src/field_specials.c:5786-5807`) reads
   the slot `ChoosePartyMon` picked (not lead-only); steps 255/220/150/100/50/1. The suite refuses the arms
   (C8: `pbChooseNonEggPokemon` has no generator handler).
3. **Done.** Each rock runs `EventScript_Rpg2gbaRockSmashReturn`, then its `var108 == N` arm (gem) or the
   wild-encounter arm (`Map066.pory:63-81`). `var108` = `random(15)` once per save on first entry (EV021),
   as in Uranium. The suite smashes all 15 rocks in one beat; the one-of-N rule makes the gem write certain
   after it. **Walk finding fixed 2026-10-25:** the side pillars EV046/047 are RMXP invisible walls and were
   hidden at load, so the leader was reachable without the gem. They now spawn as invisible solid objects
   (`tileset_converter/invisible_wall.py`), and beat_gen orders smash → pillar → leader.
4. **Done.** 35 map-60 `map_events` strip entries; EV041/EV071 carry `expect_name` "EV041"/"EV071".
5. **Done.** WORKER is a new engine class (`TRAINER_CLASS_WORKER`). Battle pics are keyed by Uranium trainer
   type (`trainer_converter/common.py:108-114`): LEADER_Caff and SCHOOLKID_MALE get their own pics.
6. **Done.** Stubbed: common events 4/5/6 print "The Tandor Network is unavailable." (`CommonEvents.pory:1-17`).
7. **Done.** Map 60 fits: the chapter builds and the suite is green. No fresh tile count was recorded.
8. **Done.** The leader battles `TRAINER_DAVERN_29` (`Map066.pory:28`), the wiki-matching party.
9. **Done.** No unmapped Ruby heads are queued for CH10 maps. The remaining queue entries are warp
   placeholders and post-Transfer commands.
10. **Done.** EV007 emits `checkmoney`/`removemoney` (3800/2500/500, `Map060.pory:387-537`). The suite refuses
    the money arms (`unmodelled_outcome:$Trainer.money`) and the `\G` text (#109).
11. **Carried → `PROJECT_TODO.md` #155.** `battle_back: Cave` is never read; the gym battles on the indoor
    background. The engine has cave natively (`MAP_TYPE_UNDERGROUND`, `battle_setup.c:741`). Cosmetic.
12. **Accepted.** `sw62` (`FLAG_GYM_2_TRAINERS_OFF`) is still written only inside the TM-granted arm, as in
    Uranium. The suite takes the sibling arm (`harness:full_bag`, ruling 19), so the full-bag branch is not
    exercised.

---

*Companion docs: `reference/chapters/00-atlas.md` (lines 244, 334-336), `06-nowtoch-city.md` (Gym 1 precedent, parked metro),
`08-route-1-moki-revisit.md` (Rock Smash), `09-route-3.md` (entry crossing), `reference/chapters.json` (CH10, `unbound_maps`),
`reference/strip_list.json`, `reference/guides/command_pokeemerald_map.md`, `PROJECT_TODO.md` #8/#111/#140/#148/#151/#153,
`BUILD_PLAN.md` (boundary rule).*
