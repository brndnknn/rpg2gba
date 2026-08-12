# Chapter 2 — Route 1

**Status:** new chapter document, authored directly from the converted rxdata
per `ROM_TEST_DEV.md` Branch A (rxdata-first, wiki cross-check only). Tier
**full** per `reference/chapters.json` (CH02, act A1, visit 1). This is the
spec a chapter test scenario gets written from — it is not itself a test, and
it carries no narrative content (house style: gates and effects only, per
Branch A2). **Not yet converted or boot-walked**; §6 records expected work,
not observed defects. **CH02 was built and passed its §9 boot-walk gate
2026-08-12** (route1 suite 29/29, ROM `68ba5268`); the work checklist is retired
to `reference/archive/CH02_TODO.md` and its still-open items moved to
`PROJECT_TODO.md` #32–#36. This document still owns the spec, beats, and
coverage targets.

**Method note:** every beat, gate, item grant, encounter table, and warp below
was read directly out of `output/uranium-build/maps/Map033.json` and
`Map081.json`, cross-referenced against `output/uranium-build/map_infos.json`,
`connections.json`, `intermediate/wild_encounters.json`, `flag_state.json`,
`reference/uranium_switches.json`, `reference/uranium_variables.json`,
`reference/chapters.json`, `reference/chapters/00-atlas.md`, and
`output/uranium-build/porymap/map_constants.json` (all checked 2026-07-31).
Two facts that reach outside the chapter's own two maps were verified against
their source maps directly and are cited as such: the Old Rod gate variable's
write site (`Map042.json`, Nowtoch City Gym) and CH01's own mechanic
inventory (`output/uranium-build/maps/Map0{32,48,49,50,64,65,89,172}.json`,
via `chapter_atlas census --chapter CH01`), used only to check the "first
appearance" claims in §6, never to source a gate. The Uranium wiki
(`output/uranium-build/wiki/Route_1.wiki`) was consulted only for §5 and is
not load-bearing anywhere else in this document.

---

## 1. Purpose / scope

Chapter 2 ≡ Route 1, the chapter immediately after Moki Town (CH01,
predecessor) and the current build frontier — the next vertical slice after
slice 1. Source of truth for the map roster: `reference/chapters.json` CH02
record — `"maps": [33, 81]`, `"predecessor": "CH01"`, `"tier": "full"`,
`"visit": 1`. Two maps: map 33 ("Route 01", 79×53, 51 events, the outdoor
route, `outdoor` field of the chapter record) and map 81 ("Route 01 (old rod
house)", 20×15, 4 events, a single interior).

The chapter covers: crossing from Moki Town into Route 1 via a screen-fade
passage, walking a route with wild grass and a lake, fighting up to nine
sight-triggered trainers (two of which register a phone rematch), collecting
seven static items and picking berries from two of three berry plants,
encountering six Rock-Smash-gated boulders (the move itself is not
obtainable in this chapter — see §6), visiting a fisherman's house that
withholds its Old Rod grant until the player has cleared Gym 1 elsewhere in
the act, and exiting north into Kevlar Town (CH03, successor). The chapter
writes essentially no persistent state of its own — see §3.

## 2. Map inventory

| RMXP id | Uranium identity (`map_infos.json`) | Engine dir | porymap constant | Role in chapter |
|---|---|---|---|---|
| 33 | Route 01 (outdoor) | `Route01` | `MAP_ROUTE_01` | Hub route: 9 trainers, 7 item balls, 6 rock obstacles, 3 berry plants, land/water/fishing encounter tables, both chapter-boundary passages |
| 81 | Route 01 (old rod house) | `Route01OldRodHouse` | `MAP_ROUTE_01_OLD_ROD_HOUSE` | Fisherman interior; Old Rod grant (Gym-1-gated); the chapter's one variable write |

Both constants are already minted in `output/uranium-build/porymap/map_constants.json`
(no `map_name_overrides.json` entry exists for either id — the raw
`map_infos.json` display names are used as-is).

**Wiring.** `output/uranium-build/connections.json` — the curated
pokeemerald-style scroll-seam list — has 14 entries total and **none for map
33**; per its generator's own docstring (`src/rpg2gba/tileset_converter/connections.py:1-30`)
that file is explicitly a partial/stretch-goal pass, and RMXP itself has no
native "connection" concept (all inter-map movement is a warp/transfer
event) — so the absence is not a gap in this document, just an unconverted
seam. The real boundary mechanism, read directly from the event data, is two
three-tile passages that play a screen-darkening `pbCaveEntrance`/`pbCaveExit`
transition (despite neither map being a dungeon — most likely reused purely
for the visual tone-shift of an underpass):
- **East, to Moki Town (CH01):** three adjacent trigger tiles on each side,
  each funneling to a single fixed arrival point on the far map (not a
  tile-for-tile pairing). Map032 (8,43)/(8,44)/(8,45) [`EV037`/`EV023`/`EV036`
  respectively, each `pbCaveEntrance` + `code 201`→Map033(70,11)] all land at
  the same Map033 spot; Map033 (70,11)/(70,12)/(70,13) [`EV023`/`EV022`/`EV024`,
  each `pbCaveExit` + `code 201`→Map032(8,43)] all land at the same Map032 spot.
- **North, to Kevlar Town (CH03, successor):** a genuine tile-for-tile pair —
  Map033 (15,5)→Map031(15,42) [`EV045`] and Map033 (16,5)→Map031(16,42)
  [`EV046`], both `pbCaveExit`.
- **Interior door:** Map033 (39,18) `EV027` ↔ Map081 (9,12)/(9,14) `EV001`-adjacent
  entry / `EV003` exit — a plain warp + screen fade, no cave effect.

Both cave-effect events already exist, unconditioned, inside CH01's own
Map032 — `01-moki.md` §4.4 lists them as "inert... slice-2 frontier" only
because Route 1 did not exist yet when that document was written. This
chapter is the first place that passage resolves to a real destination.

## 3. Story beat chain

`VAR_QUEST_LOG` (variable 101, `flag_state.json:254`) — the chain-controlling
variable everywhere else in Act 1 — is **never written** by either of this
chapter's maps: `grep`-ing both maps' `code 122` commands for `variable_id`
101 (or a range containing it) returns nothing. Route 1 has, in fact, exactly
**one** variable write in its entire 55-event, 581-command corpus
(`census --chapter CH02` → `var_writes=1`), and it is not a state variable at
all:

```
Map081.json:1300-1309, EV002 page 0, code 122:
  VAR_PEOPLE_TALKING (var 102) := random(0, 1)
```

`VAR_PEOPLE_TALKING` (`flag_state.json:255`) is re-rolled every time this one
flavor NPC is talked to, to pick between two stock lines (`code 111` type 1,
`[1, 102, 0, 1, 0]` → `VAR_PEOPLE_TALKING == 1`) — a per-interaction dialogue
randomizer, not persistent chapter state. **This chapter has no local
state-machine spine to diagram.** The only *meaningful* gate in the chapter
is a **read** of a variable this chapter never writes:

```
VAR_BATTLE_VAR01 (var 103, flag_state.json:256)  <5  ──(Map081 EV001, read-only)──►  Old Rod withheld, redirect dialogue only
VAR_BATTLE_VAR01 >=5  (written ONLY by Map042.json:3083-3091, EV003 "Maria" —
                        Nowtoch City Gym, outside this chapter, alongside
                        $Trainer.badges[0]=true)                              ──►  Old Rod granted
```

`Map081` EV001's grant branch is `code 111` type 1, `[1, 103, 0, 5, 1]`
(`Map081.json:989-996`) — variable 103 ≥ 5. Nothing in Route 1's own maps ever
sets variable 103; the only `code 122` write to it anywhere in the 199-map
corpus is Maria's Gym-1 win script. See §7 for why this resolves (rather than
restates) the `chapters.json` open question about act-boundary gating.

### 3.1 Positive beats

Route 1 is an open route, not a linearly-gated interior like Moki Town's
buildings — nothing here forces a particular traversal order except the two
chapter-boundary passages. Beats are listed grouped by kind and ordered by
ascending event id within each group; this is a plausible single playthrough,
not an asserted canonical path.

| Beat | Map | Gate | Player action (test) | Expected effect (observable) |
|---|---|---|---|---|
| B1 | 33 | arrive from Moki Town (CH01) | walk east passage tile (8,43-45 on Map032) | `pbCaveEntrance` screen-darken, warp to Map033 (70,11), `pbCaveExit` screen-restore; `setTempSwitchOn("A")` marks the arrival tile fired once (`Map033.json` EV022/23/24) |
| B2 | 33 | none | walk into `land_mons` grass anywhere on the map | 25%-rate encounter from a 12-entry table (Chyinmunk/Birbie/Cubbug, all lv2-3) — `intermediate/wild_encounters.json:928` |
| B3 | 33 | none, flavor | approach EV098 "Chyinmunk" (37,8) | `pbCallBub(2)` + cry SFX + "Chyin.. Chyin!" — no state change |
| B4 | 33 | none, flavor | talk to EV099 "npc" (42,27) | Fortog/Antidote hint dialogue — no state change |
| B5 | 33 | trigger=2 (sight), self-switch A off | approach EV009 "Trainer(3)" Marko, FISHERMAN (30,41) | `pbTrainerBattle(FISHERMAN,"Marko",...)` (`Map033.json:13298`); win/loss both set self-switch A; win also registers a phone rematch (`pbPhoneRegisterBattle`) |
| B6 | 33 | trigger=2, self-switch A off | approach EV010 "Trainer(4)" Bob, YOUNGSTER (48,42) | `pbTrainerBattle(YOUNGSTER,"Bob",...)` (`:13538`); self-switch A set after, no rematch registered |
| B7 | 33 | trigger=2, self-switch A off | approach EV030 "Trainer(5)" Flood, BUGCATCHER (21,23), patrols (move_type=3) | `pbTrainerBattle(BUGCATCHER,"Flood",...)` (`:16458`); no rematch |
| B8 | 33 | trigger=2, self-switch A off | approach EV034 "Trainer(4)" Tath, SCHOOLKID (36,8) | `pbTrainerBattle(SCHOOLKID,"Tath",...)` (`:17367`); no rematch |
| B9 | 33 | trigger=2, self-switch A off | approach EV035 "Trainer(2)" Brandon, TRIATHLETE_MaleRunner (15,23), patrols | `pbTrainerBattle(TRIATHLETE_MaleRunner,"Brandon",...)` (`:17672`); no rematch |
| B10 | 33 | trigger=2, self-switch A off | approach EV039 "Trainer(5)" Brandon, FISHERMAN (13,36), patrols | `pbTrainerBattle(FISHERMAN,"Brandon",...)` (`:18755`); win registers phone rematch (3-page event: initial fight page 0, phone-rematch fight page 1 gated `pbPhoneBattleCount>=1`, post-rematch dialogue page 2) |
| B11 | 33 | trigger=2, self-switch A off | approach EV041 "Trainer(4)" Gertha, EXPERT_Female (25,37) | `pbTrainerBattle(EXPERT_Female,"Gertha",...)` (`:19599`); no rematch |
| B12 | 33 | trigger=2, self-switch A off | approach EV053 "Trainer(5)" Richey, YOUNGSTER (17,9), patrols | `pbTrainerBattle(YOUNGSTER,"Richey",...)` (`:21644`); win registers phone rematch, same 3-page structure as B10 |
| B13 | 33 | trigger=2, self-switch A off | approach EV103 "Trainer(3)" Lynette, LASS (51,25) | `pbTrainerBattle(LASS,"Lynette",...)` (`:23353`); no rematch |
| B14 | 33 | self-switch A off | walk onto EV002 item tile (50,7) | Potion granted, self-switch A set (`Map033.json:12645`) |
| B15 | 33 | self-switch A off | walk onto EV003 item tile (31,30) | Potion granted, self-switch A set |
| B16 | 33 | self-switch A off | walk onto EV008 item tile (13,19) | Repel granted, self-switch A set (`:13086`) |
| B17 | 33 | self-switch A off | walk onto EV025 item tile (12,9) | Antidote granted, self-switch A set |
| B18 | 33 | self-switch A off | walk onto EV032 item tile (55,41) | Rare Candy granted, self-switch A set (`:16918`) |
| B19 | 33 | self-switch A off | walk onto EV037 item tile (9,38) | Super Potion granted, self-switch A set (`:18193`) |
| B20 | 33 | self-switch A off | walk onto EV050 item tile (29,7) | Antidote granted, self-switch A set |
| B21 | 33 | `Kernel.pbRockSmash` (a Pokémon must know the move — not obtainable this chapter, see §6) | use Rock Smash on EV029 "Rock" (13,21) | boulder erased (`pbEraseThisEvent`, `:16268`), `pbRockSmashRandomEncounter` rolled |
| B22 | 33 | same | use Rock Smash on EV036 "Rock" (14,16) | boulder erased (`:18090`), encounter rolled |
| B23 | 33 | same | use Rock Smash on EV038 "Rock" (15,17) | boulder erased (`:18556`), encounter rolled |
| B24 | 33 | same | use Rock Smash on EV040 "Rock" (12,39) | boulder erased (`:19409`), encounter rolled |
| B25 | 33 | same | use Rock Smash on EV042 "Rock" (17,24) | boulder erased (`:19993`), encounter rolled |
| B26 | 33 | same | use Rock Smash on EV044 "Rock" (12,35) | boulder erased (`:20303`), encounter rolled |
| B27 | 33 | self-switch A off | walk onto EV100 "BerryPlant" (62,36) | `pbPickBerry(ORANBERRY,2)` (`:22901`), then the tile becomes a growing `pbBerryPlant` (page 1) |
| B28 | 33 | none | interact with EV101 "BerryPlant" (62,35) | `pbBerryPlant` only (`:22982`) — no pickable fruit found this pass, see §7 |
| B29 | 33 | self-switch A off | walk onto EV102 "BerryPlant" (62,34) | `pbPickBerry(ORANBERRY,2)` (`:23117`), then `pbBerryPlant` (page 1) |
| B30 | 33 | `$PokemonGlobal.surfing` true | reach the shoreline strip at EV143–147 (43–47,11) | `Kernel.pbCancelVehicles` cancels Surf at the map edge (`:23607`–`23963`) — "vehicle state," first appearance this chapter |
| B31 | 33 → 81 | none | walk through EV027 door (39,18) | warp to Map081 (9,12), facing up |
| B32 | 81 | `VAR_BATTLE_VAR01 < 5` (i.e. Gym 1 not yet cleared) | talk to EV001 "fisherman" (7,8) | redirect dialogue only ("...you need to defeat Maria..."); no item, no switch/var change — **see N1** |
| B33 | 81 | `VAR_BATTLE_VAR01 >= 5` | talk to EV001 "fisherman" | Old Rod granted (`$PokemonBag.pbStoreItem(OLDROD)`, `Map081.json:1039`), `FLAG_MENU_ON_EVENT` (switch 185) toggled around the dialogue, self-switch A set — this positive beat can only occur after CH06 (Gym 1) is cleared elsewhere in the act |
| B34 | 81 | self-switch A off | talk to EV002 "brother" NPC (12,8) | flavor dialogue, one of two lines chosen by `VAR_PEOPLE_TALKING` (see §3 above) — the chapter's one variable write fires here |
| B35 | 81 | none, flavor | read EV004 sign (9,5) | "Old Rod: Not just for Magikarp anymore..." — no state change |
| B36 | 81 → 33 | none | walk through EV003 door (9,14) | warp back to Map033 (39,18) |
| B37 | 33 → Kevlar Town (CH03) | none | walk north passage tiles (15,5)/(16,5) | `pbCaveExit` screen-darken, warp to Map031 (15,42)/(16,42) — out of chapter scope |

### 3.2 Negative beats (mandatory per ROM_TEST_DEV Branch B2)

Only beats with a data-confirmed gate get a negative companion; the many
ungated beats above (flavor text, unconditioned item balls, sight-triggered
trainers) have no meaningful "skip" case to test.

| Beat | Map | Violation tested | Assert refusal fires | Assert no state advanced |
|---|---|---|---|---|
| N1 | 81 | Visit the fisherman (B32/B33's gate) before Gym 1 is cleared, i.e. with `VAR_BATTLE_VAR01 < 5` | EV001 page 0's outer branch is *not* taken; the redirect dialogue block plays instead ("Hey, I am a fisherman... But first you need to defeat Maria...") | `VAR_BATTLE_VAR01` unchanged (still whatever CH01–CH05 left it at, always `<5` on a first visit); no `pbStoreItem` call executes; self-switch A on EV001 stays off, so page 0 replays identically on every repeat visit until Gym 1 is cleared |
| N2 | 33 | Attempt Rock Smash on any of B21–B26 without a party Pokémon that knows the move | `Kernel.pbRockSmash` returns false inside the `code 111`/type-12 branch (`:16268` et al.); the branch body (erase + encounter roll) never executes | boulder event is not erased, self-switch/erasure state unchanged, no `pbRockSmashRandomEncounter` roll occurs |
| N3 | 33 | Re-approach an already-defeated trainer (e.g. B5, Marko) | page 0 (the fight page) is no longer active — self-switch A is set; page 1's `EndBattle`/`EndSpeech` line plays instead | no second `pbTrainerBattle` call fires, no additional phone-rematch registration beyond the one at first win |
| N4 | 33 | Re-touch an already-collected item ball tile (e.g. B14, EV002) | page 0 (the grant page) is no longer active; page 1 has **zero commands** (`Map033.json` EV002 page 1's `list` is a single no-op `code 0`) | no second item is granted, self-switch A stays set from the first pickup |

**N1 is the one to build first** — it directly answers the open question
carried in `reference/chapters.json`'s CH02 notes field ("the wiki says the
Old Rod is granted only after Gym 1... verify against event data"). See §7
for the resolution.

## 4. Coverage targets

Enumerated from the converted map/intermediate data, not the wiki.

### 4.1 Trainer battles

| Map | Event | Trigger | In-chapter reachable? | Notes |
|---|---|---|---|---|
| 33 | EV009 "Trainer(3)" Marko (FISHERMAN) | event touch (sight), stationary | Yes (B5) | win registers `pbPhoneRegisterBattle` |
| 33 | EV010 "Trainer(4)" Bob (YOUNGSTER) | event touch (sight), stationary | Yes (B6) | no rematch |
| 33 | EV030 "Trainer(5)" Flood (BUGCATCHER) | event touch (sight), patrol (move_type 3) | Yes (B7) | no rematch |
| 33 | EV034 "Trainer(4)" Tath (SCHOOLKID) | event touch (sight), stationary | Yes (B8) | no rematch |
| 33 | EV035 "Trainer(2)" Brandon (TRIATHLETE_MaleRunner) | event touch (sight), patrol | Yes (B9) | no rematch |
| 33 | EV039 "Trainer(5)" Brandon (FISHERMAN) | event touch (sight), patrol | Yes (B10) | 3-page phone-rematch structure (`pbPhoneRegisterBattle`/`pbPhoneBattleCount`/`createPhoneTrainer`/`customTrainerBattle`/`pbPhoneIncrement`) |
| 33 | EV041 "Trainer(4)" Gertha (EXPERT_Female) | event touch (sight), stationary | Yes (B11) | no rematch |
| 33 | EV053 "Trainer(5)" Richey (YOUNGSTER) | event touch (sight), patrol | Yes (B12) | same 3-page phone-rematch structure as EV039 |
| 33 | EV103 "Trainer(3)" Lynette (LASS) | event touch (sight), stationary | Yes (B13) | no rematch |

[auto] Exactly 9 `Trainer(N)`-named events across the 2-map roster, matching
`census --chapter CH02` `trainer_battles=9`; all 9 are `code 111`/type-12
(script) branches wrapping `pbTrainerBattle(...)` — `grep '"code": 301'`
across both maps returns zero hits, consistent with the corpus-wide trap
documented in this doc's authoring spec. No trainer event exists on map 81.

### 4.2 Item balls / given items

| Map | Item | Event | Gate | In-chapter? |
|---|---|---|---|---|
| 33 | Potion | EV002 | self-switch A off (first visit) | Yes (B14) |
| 33 | Potion | EV003 | self-switch A off | Yes (B15) |
| 33 | Repel | EV008 | self-switch A off | Yes (B16) — physical reachability relative to the Rock-Smash boulders not independently confirmed, see §7 |
| 33 | Antidote | EV025 | self-switch A off | Yes (B17) |
| 33 | Rare Candy | EV032 | self-switch A off | Yes (B18) |
| 33 | Super Potion | EV037 | self-switch A off | Yes (B19) — same topology caveat as Repel, see §7 |
| 33 | Antidote | EV050 | self-switch A off | Yes (B20) |
| 81 | Old Rod | EV001 | `VAR_BATTLE_VAR01` (var 103) ≥ 5, written only by `Map042.json` EV003 (Nowtoch City Gym / Maria win, outside this chapter) | **No** on this (first) visit — becomes reachable only once CH06's Gym 1 is cleared; see §3.2 N1, §7 |

[auto] 7 `pbItemBall`/`Kernel.pbItemBall` events + 1 `$PokemonBag.pbStoreItem`
event = 8 item-granting events across the 2-map roster. No `code 126`
(Change Items) command exists in either map, so no other grant path exists.
**Census note:** `item_grants=7` counts only the `pbItemBall`/`pbReceiveItem`
heads (`src/rpg2gba/chapter_atlas/census.py:308-309`); the Old Rod's
`pbStoreItem` call is invisible to that counter and to the `mechanics:` line,
even though it is the chapter's single most load-bearing grant — flagged in
§7, not treated as a data error.

### 4.3 Wild encounters

| Map | Table | Contents | In-chapter reachable? |
|---|---|---|---|
| 33 | `land_mons` (rate 25) | 12 entries: Chyinmunk×2 lv2-3, Birbie×3 lv2-3, Cubbug×7 lv2-3 | Yes (B2) — the only grass-encounter map in the chapter, no item/move gate |
| 33 | `water_mons` (rate 10) | 5 entries: Magikarp×3 lv10-15, Folerog×2 lv22-25 | **No** — Surf (HM03) is not obtainable until CH30 Amatree Town, act A5 (`00-atlas.md` §3) |
| 33 | `fishing_mons.old_rod` | Magikarp lv5-6, Fartog lv5-6 | **No** — the Old Rod itself is §4.2's Gym-1-gated grant, unreachable this visit |
| 33 | `fishing_mons.good_rod` | Magikarp lv15-18, Folerog×2 lv22-25 | **No** — Good Rod not introduced until CH22 Route 8, act A4 (`00-atlas.md` §3) |
| 33 | `fishing_mons.super_rod` | Magikarp×2 lv28, Folerog×3 lv35-36 | **No** — Super Rod not introduced until CH41 Route 15, act A7 (`00-atlas.md` §3) |

Map 81 has no encounter table entry in `wild_encounters.json` (no `"81"`
key) — an interior, faithfully table-less. No day/night table split exists
for map 33's tables (single `land_mons`/`water_mons`/`fishing_mons` keys
only, `intermediate/wild_encounters.json:928`ff) — the known day/night gap
noted in `00-atlas.md` §5 does not manifest as a missing *table variant*
here, only as the separate, unrelated day-only "Luz" light sprite (EV028,
§6). [auto] All 5 tables above account for every encounter row map 33
carries; none of the four gated tables get a live wiring check this chapter,
golden-content coverage only.

### 4.4 Warps

| Map | Warp | Destination | Chapter-relevant? |
|---|---|---|---|
| 33 | East passage ×3 (EV022/23/24, cave-fade) | Map032 Moki Town (8,43) | Yes (B1) — chapter's entry seam from CH01 |
| 33 | North passage ×2 (EV045/46, cave-fade) | Map031 Kevlar Town (15,42)/(16,42) | Yes (B37) — chapter's exit seam to CH03 |
| 33 | Old-rod-house door (EV027, 39,18) | Map081 (9,12) | Yes (B31) — interior link within chapter |
| 81 | House exit (EV003, 9,14) | Map033 (39,18) | Yes (B36) — same door, reverse |

[auto] `code 201` count: Map033 = 6, Map081 = 1 = 7 total (`grep '"code": 201'`
across both maps), matching the 7 rows above exactly (3 + 2 + 1 + 1) — no
arrival-only duplicate warps in this chapter's roster, unlike Moki's 8-map
one. The 7 "Stairs"-named events (EV026/031/033/047/048/066/069) are **not**
warps — each is a `code 111` type-6 (character-facing) branch plus a
move-route only, staying on map 33 (elevation/ledge traversal); none contain
a `code 201`.

## 5. Wiki vs rxdata discrepancies

Checked against `output/uranium-build/wiki/Route_1.wiki` (79 lines).

1. **Old Rod grant timing.** The wiki states plainly: "Once you have defeated
   Maria at the Nowtoch City Gym you'll pass back along Route 1... Be sure to
   stop in the house and talk to the fisherman to get the Old Rod"
   (`Route_1.wiki:19,22`). The rxdata agrees exactly: `Map081` EV001 gates
   the grant on `VAR_BATTLE_VAR01 >= 5`, and the only write of that variable
   anywhere in the corpus sets it to exactly 5 inside Maria's (Gym 1) win
   script (`Map042.json:3083-3091`), alongside `$Trainer.badges[0]=true`. No
   discrepancy — this confirms, rather than contradicts, `chapters.json`'s
   open question (§7).
2. **Trainer roster.** The wiki lists 9 named trainers (Lynette, Tath, Flood,
   Richey, two Brandons, Gertha, Marko, Bob — `Route_1.wiki:56-74`) matching
   the 9 `Trainer(N)`-named events in §4.1 by name and class exactly. No
   discrepancy.
3. **Rock-Smash "alternate path."** The wiki states a boulder blocks part of
   the route requiring Rock Smash, and that Repel, Super Potion, Rare Candy,
   and "several stronger trainers" sit past it (`Route_1.wiki:17,19,31-33`).
   The rxdata confirms 6 `Kernel.pbRockSmash`-gated boulder events exist
   (§3.1 B21-B26) but — because no tile-passability data was read this pass
   — does **not** itself establish which items or trainers sit on which side
   of them. This is left as an open, unconfirmed item in §7 rather than
   asserted from the wiki.
4. **Route infobox directions.** `north=Kevlar Town, east=Moki Town`
   (`Route_1.wiki:6-7`) matches the two cave-fade passage directions found in
   the rxdata exactly (§2 Wiring). No discrepancy.
5. **Encounter species/levels.** The wiki's grass table (Chyinmunk/Birbie/
   Cubbug, lv2-3) and fishing/water tables (Magikarp/Fortog↔Folerog)
   (`Route_1.wiki:38-53`) match `wild_encounters.json` map 33 exactly in
   species and level ranges (§4.3). The wiki additionally lists a
   Poké-Radar-only tier (Fortog lv26-29, Magikarp lv15-18, `Route_1.wiki:41-42`)
   that has **no counterpart anywhere in `wild_encounters.json`** — the Poké
   Radar mechanic is not modeled in the converted data at all. Recorded here
   per house style; out of this document's scope.

## 6. Expected conversion work and risks

### Mechanics binding table

| Mechanic | First appears here? | Disposition | Ledger row / notes |
|---|---|---|---|
| berry plant | **Yes** — absent from CH01's mechanic set | native berry trees | `00-atlas.md` §5 |
| trainer sight (event-touch trigger) | **Yes** — CH01's one trainer (Theo) is talk-triggered (`trigger=0`, `Map050.json`), not sight-triggered | native | `00-atlas.md` §5 |
| vehicle state (`pbCancelVehicles`) | **Yes** — absent from CH01's mechanic set | native (berry mart / vehicle state row) | `00-atlas.md` §5 |
| phone / rematch — battle-rematch sub-case (`pbPhoneRegisterBattle`/`Increment`/`BattleCount`/`createPhoneTrainer`/`customTrainerBattle`) | **Yes**, this specific sub-case | likely native Match Call — corrected 2026-07-30, not regressed here | `00-atlas.md` §5 |
| phone / rematch — contact-registration sub-case (`pbPhoneRegisterNPC`) | No — already present in CH01 (Map032 EV009, Map050 EV005) | same disposition | census buckets both sub-cases under one label; see below |
| rock smash / rock smash encounter | No — CH01's own Moki Town map already has 3 unconditioned `Kernel.pbRockSmash`/`pbRockSmashRandomEncounter` events (`Map032.json` EV014/015/033), not postgame-gated | native | `00-atlas.md` §5 |
| cave entry/exit | No, as script heads — CH01's Map032 already contains the Moki-side half of this exact passage (EV023/036/037), marked "inert" only because Route 1 didn't exist yet (`01-moki.md` §4.4) | native | `00-atlas.md` §5 |
| wild encounters | **No** — CH01's Moki Town already has a live, tested `land_mons` table (`01-moki.md` §4.3) | native; day/night tables are a known converter gap | `00-atlas.md` §5 |
| trainer battle | No — CH01 has 1 (Theo) | native, hidden in `code 111`/type-12 conditionals | `00-atlas.md` §5 |
| item ball | No — CH01 has 7 | native `giveitem` (classifier 8) | `00-atlas.md` §5 |

**Correction to this chapter's brief:** the task premise that "wild
encounters, rock smash (and rock-smash encounters), berry plants, phone/
rematch, and vehicle state" all first appear at CH02 does not fully survive a
CH01 cross-check. Verified against CH01's own converted maps: **berry
plant**, **trainer sight**, and **vehicle state** are genuine first
appearances; **wild encounters** and **rock smash/rock smash encounter** are
not (CH01's Moki Town map carries live, unconditioned instances of both);
**phone/rematch** is a first appearance only for its battle-rematch sub-case,
not the mechanic label as a whole (CH01 already has phone contact
registration). See §7.

### Unmapped script heads

| Head | Assessment |
|---|---|
| `get_character` | RGSS/Essentials accessor for a `Game_Character` by id (`get_character(0)` = the player). Used here only as a pointer inside `pbNoticePlayer(get_character(0))` (trainer-sight look-at) and `get_character(0).onEvent?` (arrival-tile check). Not a mechanic — a converter-classifier idiom gap (needs to resolve to the player object), not new C. |
| `pbCallBub` | Emote-bubble helper (bubble type 2 = "!" in every call this chapter). Native analog exists: `MOVEMENT_ACTION_EMOTE_EXCLAMATION_MARK`/`_QUESTION_MARK`/`_HEART`/`_X`/`_DOUBLE_EXCL_MARK` (`engine/include/constants/event_object_movement.h:180-182,252-253`), driven via `applymovement`. Classifier gap, not new C. |
| `pbEraseThisEvent` | Essentials script permanently erasing the current event (persisted). Native analog: the `removeobject` macro (`engine/asm/macros/event.inc:677`). Used on all 6 Rock events in this chapter. Classifier gap, not new C. |
| `setTempSwitchOn` | Uranium-authored Ruby helper wrapping self-switch control, used identically to a `code 123` self-switch-A-ON here (cave-arrival tiles, EV022/23/24/27/45/46). Likely a pure wrapper; its own Ruby source is not in this repo's view, so its exact semantics are a one-time lookup in Uranium's Scripts, not necessarily a converter gap. |
| `trainer` | **Not a real call** — a false positive of the census's leading-identifier regex. Both occurrences (`Map033.json` EV039/EV053 page 1) are the local-variable assignment `trainer = createPhoneTrainer(...)`, not a script-call head. No-op for capability-ledger purposes. |

### Known risks / gaps

- **Conversion-readiness is unmeasured for both maps** (`unhandled: null` in
  `census --chapter CH02`'s per-map lines) — maps 33/81 are not in the slice-1
  staged set (`SLICE_MAP_IDS = [49, 48, 32, 50, 64, 65, 172, 89]`), so the
  transpiler's unhandled queue has never run against them. What of this
  chapter's 581 commands actually converts clean is unknown until it is
  staged, per `00-atlas.md` §7 item 1.
- **Rock-Smash item/trainer topology (§4.2, §5 #3) is unconfirmed** — no
  tile-passability data was read this pass; whether Repel/Super Potion (and
  any trainers) sit behind the 6 boulders is currently only the wiki's claim,
  not independently verified from rxdata.
- **Old Rod is a forward, same-act, cross-chapter gate, not an act-boundary
  one** (§7) — the chapter's single interesting beat depends entirely on
  state written by a later chapter (CH06) in the *same* act (A1). Test
  harness sequencing for CH02 needs to be able to set `VAR_BATTLE_VAR01`
  directly (or run CH02 after CH06) rather than assuming everything a
  chapter needs is local to it.
- **Tileset/art budget** is unassessed this pass — a 79×53 outdoor route with
  a lake, forest, and boulder graphics is a larger art surface than any of
  CH01's interiors; no palette/sprite budget check has been done.
- **Two of the three berry-plant events (EV100/EV102) grant fruit, one
  (EV101) does not** (§3.1 B27-B29) — not yet explained; see §7.

## 7. Open items for the lead

- **Old Rod gating — resolved, not merely restated.** `reference/chapters.json`'s
  CH02 note speculated the grant "may be gated across an act boundary." It is
  not: Gym 1 (CH06, Nowtoch City) is still act A1 per `00-atlas.md` §2's own
  act table ("A1: Moki Town → Gym #1 (Nowtoch City)"). The real shape is a
  **forward, same-act, cross-chapter gate** — the item sits in CH02 (an early
  chapter) but is behaviorally inert until CH06 (a later chapter in the same
  act) writes `VAR_BATTLE_VAR01 := 5` (`Map042.json:3083-3091`). A first-visit
  ROM test of CH02 should assert the item is **absent**, not present.
- **Rock-Smash-gated item/trainer topology unconfirmed** (§4.2, §6) — I could
  not determine from event data alone which of the 7 item balls or 9
  trainers sit on the far side of the 6 boulder events. The wiki's "alternate
  path" claim (§5 #3) is suggestive but not authoritative per house style.
  Settling this needs either tile-passability data or a boot-walk.
  Coordinate note for whoever picks this up: the 6 rocks cluster tightly at
  x=12–17, y=16–39; Repel (EV008, 13,19) and Super Potion (EV037, 9,38) sit
  inside that box and are plausible candidates, but Rare Candy (EV032,
  55,41) does **not** — it is nowhere near the rock cluster, so a naive
  "items near rocks are gated" heuristic is already contradicted by one data
  point and should not be trusted without real passability data.
- **census `item_grants=7` undercounts the chapter's real item-granting
  events by one** (§4.2) — the Old Rod's `$PokemonBag.pbStoreItem` call isn't
  in `MECHANIC_BY_HEAD`/`item_grants`'s recognized heads
  (`src/rpg2gba/chapter_atlas/census.py:308-309`). Not a defect in this
  document; flagged for whoever maintains the census tool.
  `pbStoreItem` may be worth adding to that classifier given it's a real,
  chapter-load-bearing grant path elsewhere in the corpus too.
- **EV101 "BerryPlant" (62,35) has no `pbPickBerry` call**, unlike its two
  neighbors EV100/EV102 (§3.1 B27-B29, §6). Whether this is a deliberate
  "already picked" / "not yet grown" state, a data-entry gap in Uranium's own
  source, or something a later-loaded page/switch resolves was not
  determined this pass — flagged rather than guessed.
- **This chapter's "first appearance" brief needed correction** (§6) — wild
  encounters and rock smash/rock-smash-encounter are already present,
  unconditioned, in CH01's own Moki Town map (`Map032.json` EV014/015/033
  for rocks; the live, tested `land_mons` table per `01-moki.md` §4.3 for
  encounters). Berry plant, trainer sight, and vehicle state are genuine
  first appearances; phone/rematch is a first appearance only for its
  battle-rematch sub-case. Whoever maintains `00-atlas.md` §4's promotion
  rule may want to double-check which chapter actually earned CH01's
  existing `full` tier promotion credit for rock smash / cave entry-exit,
  since by this reading it should trace to CH01, not CH02.
- **Three CH02 work items are tracked in `CH02_TODO.md`, not here:**
  auto-deriving ledge jump directions from RMXP passage bits (item 1);
  Route 01's animated/transparent autotile plus secondary-tileset animation
  support (item 2); and, blocking — must land before conversion starts —
  promoting per-map tileset packing into `assemble_pathfinder.py` (item 4).
- **The Moki Town ↔ Route 03 seam has moved to `PROJECT_TODO.md`** — Route 03
  is CH09 (Act 2), not part of this chapter, so the seam is off-frontier
  under the chapter model.

---

*Companion docs: `reference/chapters/00-atlas.md` (corpus-wide chain, acts,
mechanics inventory, capability-ledger binding), `reference/chapters/01-moki.md`
(predecessor chapter, source of the cave-passage "inert" note this document
resolves), `reference/chapters.json` (CH02 binding record and the Old-Rod
open question this document answers), `reference/guides/command_pokeemerald_map.md`
(capability ledger, not re-derived here), `ROM_TEST_DEV.md` (harness design
and the Branch A/B decisions this document implements).*
