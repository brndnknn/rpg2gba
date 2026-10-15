# Chapter 8 — Route 1 + Moki Town (revisit)

**Status:** authored 2026-10-15 at chapter open; not yet converted, staged or boot-walked.
Branch `ch08-moki-town-revisit`. Tier **thin** per `reference/chapters.json` (CH08 record),
with the new-content set in §4 enumerated exhaustively. No §8. This is a spec a scenario
gets written from; gates and effects only, no narrative. CH08 is the merge (operator,
2026-10-15) of the planned CH07A "Route 1 (revisit)" and the old CH08 "Moki Town (revisit)";
CH07A had no manifest, suite or branch, so nothing was renamed.

**Method note:** read 2026-10-15 from `reference/chapters.json` (CH07/CH08/CH09),
`output/uranium-build/maps/Map0{31,32,33,48,49,50,64,65,81,89,172}.json`,
`output/uranium-build/connections.json`, `reference/manifests/CH01..CH03.{dispositions,derived}.json`,
`reference/chapters/{01-moki,02-route-1,00-atlas}.md` (atlas §7),
`reference/frozen/slice2_blocked_expectations.json` (CH02 `DEFERRED_ROCK_GATED`),
`reference/uranium_{switches,variables}.json`, `PROJECT_TODO.md` #27/#44/#50/#92/#111/#122/
#127/#128/#138/#140/#141, `chapter_atlas census --chapter CH08`, and a
`rpg2gba.traversal` reachability run on Map032 (§7 item 1). The Moki half is the same data
CH01 read; see `reference/chapters/01-moki.md` for first-visit analysis, not repeated here
except where a gate state changes. Wiki: **not checked** (§5).

---

## 1. Purpose / scope

Third pass over Route 1 / second pass over Moki Town. Predecessor CH07 (Route 2 revisit, map
35), successor CH09 (Route 3, map 59) (`reference/chapters.json`). Roster
`"maps": [33, 81, 32, 48, 49, 50, 64, 65, 89, 172]`; `outdoor` 32. Census
(`chapter_atlas census --chapter CH08`): maps=10 events=186 pages=293 commands=3341
trainer_battles=10 item_grants=14 switch_writes=25 var_writes=19; unmapped script heads:
`jvGiveReward`, `jvNextReward`, `pbGet`, `pbSet`. Per-map events: 33 Route 01 79x53 ev=51;
81 Old Rod house ev=4; 32 Moki Town 72x64 ev=52; 48 ev=13; 49 ev=22; 50 lab ev=27; 64 ev=4;
65 ev=3; 89 ev=6; 172 ev=4. The census "queue" figures (21/3/13/16/133) come from the
full-corpus transpile queue, not a CH08 run, and are not trusted here; map 172's 133 is the
CH01 Theo scene (Map172 EV004 p0, 197 commands, `var101` 0->2), not postgame content.

Mechanically the chapter is two things:

1. **Route 1 half (was CH07A).** Content CH02 dispositioned `blocked:rock_smash` opens
   (Rock Smash granted in CH06). The walk is the CH07 end state -> Kevlar Town (31, transit
   only) -> Route 1 (33, plus the Old Rod house 81).
2. **Moki half.** Same maps as CH01 at a later story state; **no new conversion, only new
   gate states**: `sw55` "Gym 1 defeated" (written CH06, `Map042` EV003 p0) turns on a
   cutscene (Map032 EV078) and the lab events (Map050 EV027, EV005 p5-p7). `var101` "Quest
   Log" ends CH01 at 4 and the CH06 gym write adds 1 (Map042 EV003 p0 `code 122`, add-1), so
   CH08 opens with `var101` = 5 (derived from the write sites; story-state model to confirm,
   §7 item 11).

The chapter's route ends at the crossing into CH09's maps (rule since 2026-10-13,
`beat_gen.__main__._successor_exit_group`); that crossing is the Moki E seam, which does not
exist yet (§7 item 2).

## 2. Map inventory

| RMXP id | Uranium identity | Role in chapter |
|---|---|---|
| 31 | Kevlar Town | **Transit only** (entry leg from Route 2's S seam, exit S into Route 1); owes nothing new except one cleanup page (§3.4) |
| 33 | Route 01 (79x53) | Whole map re-walked; 6 rocks, 5 trainer battles, 3 item balls open |
| 81 | Old Rod house | Old Rod grant NPC (§4.2); first chapter that can pass its gate |
| 32 | Moki Town (72x64, outdoor) | Chapter's outdoor hub; sw55 cutscene; 3 rocks (§3.3) |
| 50 | Lab (Bambo) | sw55 autorun (§3.2); Pokédex-count reward NPC (§3.2) |
| 48, 49, 64, 65, 89, 172 | Moki interiors | Already walked in CH01; revisit for gate-state changes only (see §3.5) |

**Wiring.** `connections.json` rows touching the roster: `[32,'E',26,59,'W',0]` (the Moki
<-> Route 3 seam, unconverted, §7 item 2) and `[31,'N',11,35,'S',0]` (Kevlar's N seam to
Route 2, the chapter entry). Kevlar -> Route 1 is not an overland row: it is a warp pair
(walk `35 -> 31 -> 33 -> 32`, atlas §7). Engine dirs and porymap constants for 33/81 are
CH02's/not assigned; this doc does not mint any.

## 3. Gates and effects (read from the map JSON)

Thin tier: roster and gates, no beat table. `swNN`/`varNN` names from
`reference/uranium_switches.json` / `uranium_variables.json`.

### 3.1 Moki Town sw55 cutscene (Map032 EV078 / EV079)

- **EV078 "Trainer(6)" @(27,42), page 0**: gate `sw55`; trigger 2 (touch). Body: turns the
  player to face by the player's y vs 45, player-facing move route, balloon/animation
  (`207` id 17 on EV079), music change, EV079 moves 5 tiles down, two `pbCallBub` lines, fade
  out, sets self-switch A on **EV078 and EV079** (`pbSetSelfSwitch`, one script row with a
  `655` continuation), then `201` warps the player to **Map050 (14,7)** facing 8. Page 1
  (self-switch A) is empty, so the scene is one-shot. `[auto]`
- **EV079 "BamboAfterGym" @(33,45)**: p0 gated `sw55`, no commands (the actor).
- The `pbSetSelfSwitch` multi-row script and the `207` animation id 17 are the transpiler
  points to check (§6.2).

### 3.2 Lab (Map050)

- **EV027 @(17,19), page 0**: gate `sw55`; trigger 3 (autorun). Sequence: bubble lines,
  `pbSet(2,$Trainer.pokedexSeen)` + `pbSet(3,$Trainer.pokedexOwned)` into vars 2/3 purely to
  display them in a text box (`\v[2]`, `\v[3]`), then a conditional `Kernel.pbReceiveItem(
  POKeBALL,10)` (a recognized head; **10 Poké Balls**), more lines, sets self-switch A.
  Pages 1/2: empty (self-switch A; `sw62`). CH01 derived marks p0 `refused:story-state:
  party_model` (#127): the reads of `pokedexSeen`/`pokedexOwned` are what the refusal sees.
  The `pbSet` here is a display read, not state the engine needs.
- **EV005 "Bambo" @(14,6)**: pages p0-p4 are CH01 content (aptitude test). New this chapter:
  - **p5**, gate `var101 >= 5`: registers a phone contact (`pbPhoneRegisterNPC(35,"Professor
    Bamb'o",50)`), then a yes/no. On yes: reads `PROFREWARDS[pbGet(22)+1][0]`, dex seen/owned
    into vars 2/3, then a branch ladder on `jvNextReward` and `var22` "BAMBO REWARD" (0..10):
    each rung says a line and calls `jvGiveReward`; rungs 4, 6, 8 grant an Egg (party-full
    arm sets self-switch A off), rung 10 ends the ladder. Heads `jvNextReward`,
    `jvGiveReward`, `pbGet`, `pbSet`, `PROFREWARDS` are unmapped (census). CH01 derived:
    `unreachable:beat_gen: the story model places it in no chapter`.
  - **p6**, gate `var101 >= 5` AND self-switch A: re-entry arm that calls `jvGiveReward` and
    sets self-switch A on; the party-full arm leaves it off. CH01 derived: `refused:party_model`.
  - **p7**, gate `var22 >= 10`: two lines, no state. CH01 derived: unreachable (no chapter).
  - Net: a **repeatable Pokédex-count reward NPC**. Whether any rung can fire at CH08 depends
    on the party's dex counts (rung 0 needs none; rung 1 needs a catch count set by
    `PROFREWARDS`), see §7 item 4.
- The `var101 >= 4` flavor pages the brief listed (Map032 EV009 p3, EV016 p1, EV002 p1,
  EV076 p1, EV077 p1, Map050 EV019 p2) are **not new**: `var101` is 4 at CH01's end, CH01
  derived already dispositions them (EV009 p3 `beat:m032e009`, EV019 p2 `beat:m050e019p2`,
  the rest `cosmetic`), and all but EV009 p3 (1 command) carry zero commands. Nothing owed.

### 3.3 Moki Town rocks (Map032 EV014 @(65,45), EV015 @(66,46), EV033 @(66,44))

CH01 dispositions all three `blocked:rock_smash` (negative beat N4; six rows p0/p1). Page 0
calls `Kernel.pbRockSmash`; its else-branch calls `isRockSmashSoftlocked?` (PROJECT_TODO #50;
unrecognized head), the arm that self-smashes when a Nuzlocke-style softlock guard fires. The
transpiler's rock idiom drops both arms (CH07 doc §7 4a), so the guard is lost; it is a
Nuzlocke-only guard and is stripped, not ported (§7 item 6). Rock persistence is ruled
(CH07 §7 4a): rocks respawn via their `FLAG_TEMP_11..15` template flags.

### 3.4 Kevlar transit (Map031)

Only **Map031 EV049 "NurseTut" p2** changes against CH03: gate `sw55`, autorun, comment
"This is to fix an old bug"; sets `$PokemonGlobal.seenStorageCreator = true` (a two-row
script, `355` + `655`) and `116` (erase event). CH03 derived: `unreachable:beat_gen: the
story model places it in no chapter` (no chapter holds both sw55 and Kevlar until now).
Everything else on 31 is still locked behind Strength (HM04, CH25), the Bike Wheel (CH11),
and later badges, i.e. `blocked:strength` (CH03 holds exactly 10 such rows: 2 on map 31,
8 on map 19). Kevlar rides along: enter from Route 2's S seam, cross, exit south into Route
1, full warp assertion per seam. Open item on the bookkeeping: §7 item 8.

### 3.5 Moki interiors (48, 49, 50, 64, 65, 89, 172)

Gates that move with `sw55`/`var101` besides §3.2: Map172 EV001 "Cam" p2 (`sw55`, empty,
cosmetic); Map050 EV001 p1, EV002 p1, EV004 p1, EV019 p1 and EV020 p1 (`var101 >= 1`, mostly
empty, CH01 content). `sw125` "FINAL EVENT" (postgame) pages across all Moki maps (including
Map032 EV080 p0 and the Map064/065 p1 twins) stay dormant: out of scope. #44 (flavor
interiors 64/65/89 shipped untested in CH01) names CH08 as "the natural place CH01's interiors
get walked again": see §8-equivalent in §7 item 9.

## 4. Coverage targets

Exhaustive for the new content; counts checked against `reference/manifests/CH02.dispositions.json`
and the map JSON.

### 4.1 Trainer battles (Route 1, previously `blocked:rock_smash`)

| Map | Event | Position | Trigger / note |
|---|---|---|---|
| 33 | EV009 Trainer(3) (Fisherman Marko, CH02 B5) | (30,41) | sight; `pbTrainerBattle` |
| 33 | EV010 Trainer(4) (Youngster Bob, B6) | (48,42) | sight |
| 33 | EV035 Trainer(2) (triathlete Brandon, B9 + B14b 2-tile walk) | (15,23) | patrol; `blocked` p0/p1 |
| 33 | EV041 Trainer(4) (Expert Gertha, B10) | (25,37) | sight |
| 33 | EV039 Trainer(5) (Brandon phone trainer, B12) | (13,36) | 3 pages; phone-rematch (`pbPhoneRegisterBattle`), #141 applies |

Five battles. The other four Route 1 trainers (EV030, EV034, EV053, EV103) were not rock-gated
and were covered in CH02.

### 4.2 Item balls / given items

| Map | Item | Event | Gate | Note |
|---|---|---|---|---|
| 33 | Repel | EV008 @(13,19) (B15b) | default page | new (was rock-gated) |
| 33 | Super Potion | EV037 @(9,38) (B15c) | default page | new |
| 33 | Rare Candy | EV032 @(55,41) (B15d) | default page | new; wiki/data position is **not** near the rock cluster (02-route-1.md note) |
| 81 | Old Rod | EV001 @(7,8) p0 | `var103 >= 5` ("Battle Var01", written by CH06/Map042) | `pbStoreItem(OLDROD)`; else-branch gives hint text; the page brackets `sw185` (menu-on-event) on/off |
| 50 | Poké Ball x10 | EV027 p0 | `sw55`, autorun | `pbReceiveItem(POKeBALL,10)` |
| 50 | Egg(s) | EV005 p5/p6 | `var101 >= 5`, dex rung | `jvGiveReward` (unmapped); see §7 item 4 |

### 4.3 Rocks and obstacles

Route 1: six rocks, all `Kernel.pbRockSmash` + `pbEraseThisEvent` (so they **respawn**,
CH07 §7 4a): EV029 @(13,21), EV036 @(14,16), EV038 @(15,17), EV040 @(12,39), EV042 @(17,24),
EV044 @(12,35). EV141 "block" @(54,40) is also `blocked:rock_smash` (no pbRockSmash call;
a blocking event). The six rock beats (CH02 doc B21-B26) were never authored; CH02's
negative beat N2 flips to a positive. Moki: three rocks, §3.3. CH02 also holds two
`blocked:surf` rows (map033 EV013, EV020), still blocked (Surf not granted). Route 1's
`rock_smash_mons` table is **not checked** here (§7 item 7).

### 4.4 Warps / crossings

| Crossing | Role |
|---|---|
| Route 2 S seam -> Map031 (`[31,'N',11,35,'S',0]`) | chapter entry |
| Kevlar -> Route 1 (warp pair) | transit; full warp assertion |
| Route 1 <-> Moki (existing CH01/CH02 pair) | Route 1 -> Moki leg |
| Old Rod house (81) door | enter/exit assertion |
| Moki interiors' doors | already asserted in CH01 |
| **Moki E seam `[32,'E',26,59,'W',0]` -> Map059** | **chapter exit; not built** (§7 item 2) |

## 5. Wiki vs rxdata discrepancies

**Not checked** for CH08. The CH02/CH01 docs already compared Route 1 / Moki against the wiki.
The Route 1 rock-gated item/trainer topology was unconfirmed there; this chapter's solver run
is its first real test (02-route-1.md §5 #3).

## 6. Expected conversion work and risks

### 6.1 Mechanics

Census mechanics are all previously seen (rock smash and its encounter, trainer battle/sight,
phone rematch, item ball, self-switch write, event erase, wild encounters, cave entry/exit).
Verdicts live in `reference/guides/command_pokeemerald_map.md`. New to be ruled: a
Pokédex-count reward ladder (no native analog checked yet, §7 item 4).

### 6.2 Unmapped script heads

Census: `jvGiveReward`, `jvNextReward`, `pbGet`, `pbSet`. All four sit on Map050 (EV005 p5/p6
reward ladder; EV027's `pbSet` display reads, and EV005 p0's `pbGet(151)` which is CH01
content). Not hand-faked; they fail loud until ruled. Also queued: Map032 EV014/015/033
`isRockSmashSoftlocked?` (#50); the two-row `pbSetSelfSwitch(78..)/(79..)` and `207` animation
id 17 in EV078; the two-row `seenStorageCreator` script in Map031 EV049.

### 6.3 Backlog carried in

- **#92 (capability model)**, **#128 (`blocked:` revisit)**, and the HM06-taught slice of
  **#127 (party/dex model)**: deferred from CH07 (CH07 §7 4c). CH08 is the first chapter that
  needs a rock smashed. Rock Smash gate is badge count >= 1 AND (party member knows
  ROCKSMASH OR key item BOXINGGLOVES) (`scripts_dump/103__PField_HiddenMoves.rb:385-389`).
  #127's wider `party_model` refusal also covers Map050 EV027 p0 and EV005 p6 (above).
- **#50** `isRockSmashSoftlocked` head (Moki rocks): §3.3, §7 item 6.
- **#27** Moki E seam -> Route 3 (whole seams feature, 3 parts): §7 item 2.
- **#138** Map032 EV080 emote: EV080 p0 is gated `sw125` only (the page's `var123 == 17` is
  marked invalid), so it is **dormant** in this story state, yet #138 says the spawn is
  "visible in built CH01". The two do not agree: check whether the transpiler gates the page
  (§7 item 10).
- **#141** phone-rematch `RegSpeech` dropped: applies to Route 1's phone trainer (EV039) and
  to the new `pbPhoneRegisterNPC` in Bambo p5 (§3.2).
- **#140** map-name popup reads LITTLEROOT TOWN on every map; visible on every crossing here.
- **#44** CH01/CH03 flavor interiors untested; names CH08 as the re-walk point (§7 item 9).
- **#122** (C10 offline verdict head), **#111** (`_minimal_sets_for_predicate` blow-up in
  full-suite runs): general carry; CH08's roster is 10 maps, the largest revisit so far, so
  #111's blow-up is a live risk for the checker (Map033 is 79x53).

## 7. Open items for the lead

1. **Do the Moki rocks gate the east exit? — ANSWERED analytically 2026-10-15.**
   `rpg2gba.traversal` on Map032 (`reachable_with`, held `{}` vs `{rock_smash}`, start
   (27,43)): with nothing held, the map's east edge (x=71) is **not reached**; with
   `rock_smash` it is, at rows 43-47, and the three rock-neighbour cells (66,45), (67,46),
   (67,44) open only then. Rocks (65,45), (66,46), (66,44) are the only `rock_smash`
   obstacles on 32 (the rest are surf terrain). Caveat: the seam's overlap rows into Map059
   depend on offset 26 and on #27's convention; this shows the rocks are the gate, not
   which rows the seam covers. A hardware pass is still owed.
2. **Does CH08 build the Moki E seam (#27), or does the route end at the rocks?** Rule since
   2026-10-13: a chapter's route ends at the crossing into the successor's maps. With no seam
   built, `_successor_exit_group` finds no crossing and returns None (the solver's own end
   rule). Options: (a) CH08 builds #27 (per-map tileset packing, pinned palette family for
   the Moki+R03 component, border-strip import: the first seam anywhere), route ends at the
   crossing; (b) CH09 builds it, CH08 ends at the smashed rocks. `chapters.json` CH08 notes
   say the seam is CH09's crossing.
3. **Kevlar NurseTut cleanup (Map031 EV049 p2):** assert the page's effect (sets
   `seenStorageCreator`, erases the guide) or leave unreachable? It is invisible, autorun on
   `sw55`; it fires on entry. If asserted, the beat needs the erase to be observable.
4. **Pokédex-count reward NPC (Bambo p5-p7, unmapped `jv*` heads):** model, stub, or defer?
   Needs a dex model (#127) and an Egg-grant path. Rung 0 (no reward, text only) is the only
   one reachable without catches. Option: stub the ladder to its rung-0 text and log a
   `deferred` row; the `pbPhoneRegisterNPC` call needs its own ruling (a native
   `register_matchcall` or none).
5. **Map050 EV027's 10 Poké Balls:** `pbReceiveItem` is a recognized head; the unrecognized
   `pbSet` rows only populate vars 2/3 for text display. Emit the item grant and drop the
   display reads (replace `\v[2]`/`\v[3]` with fixed text), or wait for #127?
6. **`isRockSmashSoftlocked` (#50):** the census calls it a Nuzlocke-only guard (stripped).
   Confirm and strip the arm explicitly (list in `strip_list.json`) so the arm is a ruling,
   not a silent drop.
7. **Route 1 `rock_smash_mons`:** CH07 §7 4 found map 35 had none. Does map 33 have a
   RockSmash encounter table (`encounters_raw.json` key "33"), and does each of the six rocks
   roll it? Not checked here.
8. **Kevlar's deferral bookkeeping disagrees.** The old CH07A notes said Kevlar owes
   "Strength x7, Bike Wheel x1, post-Gym-5 x1, and B26"; atlas §7 item 3 says "10 deferrals"
   for Kevlar **and** Passage Cave combined; `CH03.dispositions.json` holds exactly 10
   `blocked:strength` rows (2 on map 31, 8 on map 19), no Bike Wheel or Gym-5 rows. The "B26"
   label in `playtest/chapters_gen/ch03.py` / `03-kevlar-town.md` is a different beat. Which
   count is the ledger entry for the permanent hold decided at CH25?
9. **#44 flavor interiors:** do the generated CH01 suite beats already cover 64/65/89 (#44's
   text predates generated suites; "not verified")? If not, does CH08 own them or still
   defer to end of Act 1 (CH06 gate has passed)?
10. **Map032 EV080 (#138):** dormant (`sw125`) per the data but reported visible in built CH01.
    Check the transpiled output before CH08 relies on either reading.
11. **`var101` at chapter start:** derived 5 from write sites (CH01 end 4, Map042 EV003 +1).
    Confirm against the story-state model so Bambo p5 is live exactly when expected.
12. **Census agreement:** doc totals equal the census where compared; the census "queue"
    numbers are stale (§1) and not used.

---

*Companion docs: `reference/chapters/01-moki.md`, `02-route-1.md`, `03-kevlar-town.md`,
`07-route-2-revisit.md`, `00-atlas.md` (§5 ledger, §7 CH07A insertion),
`reference/guides/command_pokeemerald_map.md`, `reference/chapters.json` (CH08/CH09),
`PROJECT_TODO.md` #27/#44/#50/#92/#111/#122/#127/#128/#138/#140/#141.*
