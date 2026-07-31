# Chapter 3 — Kevlar Town

**Status:** new chapter document, authored directly from the converted rxdata
per `ROM_TEST_DEV.md` Branch A (rxdata-first, wiki cross-check only). Tier
**medium** per `reference/chapters.json`. This is the spec a chapter test
scenario gets written from — it is not itself a test, and it carries no
narrative content (house style: gates and effects only, per Branch A2).
**Not yet converted or boot-walked**; §6 records expected work, not observed
defects.

**Method note:** every beat, gate, item grant, warp, and script call below was
read directly out of `output/uranium-build/maps/Map0{31,67,68,73,19}.json`,
`map_infos.json`, `connections.json`, `flag_state.json`, `common_events.json`,
`intermediate/wild_encounters.json` (all under `output/uranium-build/`), and
`src/rpg2gba/chapter_atlas/census.py` (checked 2026-07-31; `census --chapter
CH03` reproduced and cross-checked by hand). `reference/chapters.json` and
`reference/chapters/00-atlas.md` were read for scope/binding context. The
wiki (`output/uranium-build/wiki/Kevlar_Town.wiki`, `Passage_Cave.wiki`) was
consulted only for §5.

---

## 1. Purpose / scope

Chapter 3 ≡ Kevlar Town, the second town of Act 1. Roster (`reference/chapters.json`
CH03): 31 (outdoor hub), 67 (Poké Mart), 68 (Pokémon Center), 73 (a second
physical map also named "Kevlar Town" — §2), 19 ("Passage Cave", bound here
rather than to CH05 — §2/§5). Predecessor: CH02 (Route 1), entered across
Kevlar's south boundary.

Covers: arriving from Route 1; the first Poké Mart and first Pokémon Center
(guided PC/healing tutorial, a repeatable in-Center trainer battle); a shared
building strip holding a Bike Repair Shop, a Berry Boutique, and two flavor
houses; a joke NPC that gives away a Magikarp; an NPC ("Cry Boy") whose
help-request is gated behind a flag this chapter's data never sets true; a
small, self-contained boulder-puzzle cave (three Biker trainers) that enters
and exits at the same town coordinate; and the north edge, the chapter's exit
toward Route 2 (CH04). No `VAR_QUEST_LOG` write occurs anywhere in this
chapter (zero `code 122` commands touch variable 101 across all 5 maps).

## 2. Map inventory

| RMXP id | Uranium identity (`map_infos.json`) | Engine dir | porymap constant | Role in chapter |
|---|---|---|---|---|
| 31 | Kevlar Town (outdoor, order 18, `parent_id` 55) | `KevlarTown` | `MAP_KEVLAR_TOWN` | Hub; doors to 67/68/73/19, Cry Boy, gift Magikarp, berry plants, PC tutorial |
| 67 | Kevlar Town(Pokemart) | `KevlarTownPokemart` | `MAP_KEVLAR_TOWN_POKEMART` | Poké Mart + Mystery Gift deliveryman |
| 68 | Kevlar Town(Pokemon Center) | `KevlarTownPokemonCenter` | `MAP_KEVLAR_TOWN_POKEMON_CENTER` | First Pokémon Center; healing, PC tour + item reward, facility trainer |
| 73 | Kevlar Town **(name collides with map 31 — proposed `Kevlar Town Buildings`, unverified, §7)** | `KevlarTownBuildings` (proposed) | `MAP_KEVLAR_TOWN_BUILDINGS` (proposed) | Shared interior strip: Bike Repair Shop, Berry Boutique, 2 flavor houses (4 doors from map31 → 4 distinct x-regions) |
| 19 | Passage Cave (the "Grott-Hole" offshoot per wiki terminology — §5) | `PassageCave` (collides with maps 36/37, also "Passage Cave" — §7) | `MAP_PASSAGE_CAVE_GROTT_HOLE` (proposed) | Isolated boulder-push puzzle; 3 Biker trainers; dead-ends back into map31 |

**Wiring.** All 4 interiors carry `parent_id: 31`. `connections.json`'s only
seam touching this roster is `[31, "N", 11, 35, "S", 0]` — a continuous north
edge to map 35, named **"Route 02"** (CH04) in `map_infos.json`. Every other
boundary is a discrete `code-201` warp: the south edge is two paired tiles,
Map031 EV23 `(15,43)→Map033(15,7)` and EV35 `(16,43)→Map033(16,7)` — Map033
is "Route 01" (CH02), the entry boundary. Map19's entrance is Map031 EV34
`(13,7)→Map019(11,29)`; Map19's **only** `code-201` command anywhere in the
map is its own EV7, `(11,30)→Map031(13,7)` — the same coordinate its entrance
sits on. No warp in Map019 targets any map but 31, and no warp anywhere in
the roster targets map19 from any map but 31 — the evidence for
`chapters.json`'s note that map19 binds to CH03, not CH05 (the real
Kevlar↔Nowtoch through-cave is maps 36/37, via the map31↔35 seam). See §5.

## 3. Story beat chain

No `VAR_QUEST_LOG` write exists here. The local spine runs through two
switches and one one-shot variable:

```
FLAG_SIDEQUEST_CRY_BOY (sw99)     unset ─[Map031 EV7 "Cry Boy" pg1, accept]─► set
FLAG_SIDEQUEST_CRYBOY_END (sw100) unset ─[Map019 EV6 "Richboy", battle resolves]─► set
FLAG_NURSE_TUTORIAL (sw126)       unset ─[Map031 EV49 "NurseTut", walkthrough ends]─► set
VAR_HA_MAGIKARP (var200)          0 ─────[Map031 EV14, gift accepted]──────────────► 1
```

Of 21 total switch writes, the 17 not shown are local bookkeeping: switch185
(`FLAG_MENU_ON_EVENT`, a menu-suppress-during-dialogue toggle, 5 NPCs, 15
writes) and switches 3/5 (Pokémon Center flavor flags, 2 writes). Of 7 total
variable writes, the 6 not shown are likewise non-progression: var102
(`VAR_PEOPLE_TALKING`, a random-line selector, 4 NPCs, 4 writes) and var43
(`VAR_RESERVED_POKEMON_COUNT`, a party-length scratch value for the Center
counter's ball-sprite display, 2 writes).

| Beat | Map | Gate | Player action (test) | Expected effect (observable) |
|---|---|---|---|---|
| B1 | 31 | CH02 predecessor | cross south boundary | Arrive on Map031 via (15,43)/(16,43); no state write — entry point |
| B2 | 31 | none | talk "NurseTut" (EV49) | Walkthrough scene; ends with sw126 set; re-talk is the no-op page |
| B3 | 31→68 | none | enter Center door (20,12) | Warp to Map068 (8,18) |
| B4 | 68 | none | talk counter NPC (EV1) | `pbSetPokemonCenter`; Yes/No heal; var43=party length; if `pbPokerus?`, sw3 set |
| B5 | 68 | none | talk PC-tour NPC (EV15) | Tour scene; ends with `pbReceiveItem(ORANBERRY,5)` (in a code-111/type-12 conditional) + self-switches 16/17 |
| B6 | 68 | none | touch item-ball tile (EV18) | `pbItemBall(ANTIDOTE)` once (self-switch gate) |
| B7 | 68 | none | talk Mawuli (EV14) | `pbTrainerBattle(RICHBOY,"Mawuli",...)`; win/lose, in-scene heal + re-offer — a facility loop, not one-time |
| B8 | 31→67 | none | enter Mart door (37,14) | Warp to Map067; `pbPokemonMart([...])` at EV1; "Deliveryman" (EV9) checks `pbNextMysteryGiftID>0` |
| B9 | 31→73 | none | enter Berry Boutique door (35,6) | Warp to Map073 (44,12); EV6 grants Bacu Berry (+3 more on continuation lines census misses, §4.2), + Sprinklotad if unheld |
| B10 | 73 | none | talk Bike Repair NPC (EV1) | If `BIKEWHEEL` qty>0: wheel deleted, `BICYCLE` granted. **No Bike Wheel source in this chapter** — §5 #3, §7 |
| B11 | 31 | none | talk "EV014" (29,20) | Joke dialogue; `pbAddPokemon(MAGIKARP,100)`; var200 0→1 (re-talk guard) |
| B12 | 31 | sw86 `FLAG_HAS_STRENGTH` | talk "Cry Boy" (EV7) | Page0 (ungated) idle only; page1 (sets sw99) needs sw86 true. **Sw86 written exactly once corpus-wide** (Map140/Route11, sets it 0/off) — reachability unresolved, §7 |
| B13 | 31→19 | none | enter cave door (13,7) | Warp to Map019 (11,29); 3 "Boulder" push events; sight Bikers Lou (EV4)/Joe (EV5); Richard (EV6) sets sw100 after 1 of 2 branches (sw94-gated postgame variant, out of scope) |
| B14 | 19→31 | none | walk exit tile (11,30) | Warp to Map031 (13,7) — only warp target anywhere in Map019 |
| B15 | 31→35 | none | walk off north edge | Seam crossing into Map035 "Route 02" — chapter exit, out of scope |

## 4. Coverage targets

Census totals: `trainer_battles=5`, `item_grants=5`, `switch_writes=21`,
`var_writes=7`, `choices=5`, `conditionals=43`, `move_routes=72`.

### 4.1 Trainer battles

5 script-level `pbTrainerBattle` calls, 4 distinct trainers — every one a
`code-111`/type-12 Ruby branch, not `code-301` (zero `code-301` hits in the
5 maps, matching the corpus-wide trap).

| Map | Event | Trigger | In-chapter reachable? | Notes |
|---|---|---|---|---|
| 19 | "Trainer(4)" / Lou (EV4) | event touch (sight) | Yes (B13) | BIKER class |
| 19 | "Trainer(4)" / Joe (EV5) | event touch (sight) | Yes (B13) | BIKER class |
| 19 | "Richboy" / Richard (EV6) | event touch (sight) | Yes (B13) | BIKER; **2 calls** in one page, branched on sw94 — same NPC, harder post-Gym-5 team; census counts both |
| 68 | "EV014" / Mawuli (EV14) | action button | Yes (B7) | RICHBOY; repeatable facility battle |

No other trainer events in the 5-map roster. `[auto]`

### 4.2 Item balls / given items

5 script-detectable grants, plus one real grant the census tooling misses.

| Map | Item | Event | Gate | In-chapter? |
|---|---|---|---|---|
| 73 | Bicycle | EV1 "Bike Repair Shop" | must hold `BIKEWHEEL` (consumed) | **Unclear** — no source this chapter; wiki says Route 4 (§5 #3) |
| 73 | Sprinklotad | EV3 / EV6 pg1 (2 offers, 1 NPC) | only if not held | Yes (B9) |
| 73 | Bacu/Guara/Cupu/Acai Berry | EV6 pg0 | none | Yes (B9) — only Bacu Berry is census-visible; rest are on `code-655` continuation lines |
| 68 | 5× Oran Berry | EV15 (PC tour NPC) | tour completion | Yes (B5) |
| 68 | Antidote (item ball) | EV18 | standard item-ball gate | Yes (B6) |

`item_grants` counts raw `code-126` (none exist here) plus script calls whose
**first line** starts `pbReceiveItem`/`pbItemBall`. The Bicycle grant
(`Kernel.pbReceiveItem(BICYCLE)`, Map073 EV1) is real but sits on a
`code-655` continuation line after a `$PokemonBag.pbDeleteItem(...)`
statement whose leading `$` the census's head-regex doesn't match — a
tooling gap, not a missing grant. `[auto]`

### 4.3 Wild encounters

None: `encounter_list` is `[]` in all 5 map JSONs, and `wild_encounters.json`
has no entries for ids 31/67/68/73/19. `[auto]`

### 4.4 Warps

| Map | Warp | Destination | Chapter-relevant? |
|---|---|---|---|
| 31 | South doors (15,43)/(16,43) | Map033 (Route 01, CH02) | Yes — entry boundary (B1) |
| 31 (seam) | North edge | Map035 "Route 02" (CH04) | Yes — exit boundary (B15) |
| 31 | Cave door (13,7) | Map019 (11,29) | Yes (B13) |
| 19 | Exit (11,30) | Map031 (13,7) | Yes (B14) — only warp target anywhere in Map019 |
| 31 | Buildings — Maury's apartment (37,28) | Map073 (24,12) | No — Maury's state never advances this chapter |
| 31 | Buildings — couple's house (32,28) | Map073 (64,12) | No — flavor interior |

The remaining 7 `code-201` commands (mart door + return, Center door ×2 +
returns, Berry-Boutique door + return, Bike-Shop door + return) are routine
interior connectors, all chapter-relevant (B3/B8/B9/B10) — 13 `code-201`
commands total plus the 1 seam, matching a manual count. No warp in this
roster targets a map outside `{31, 33, 35, 67, 68, 73, 19}`. `[auto]`

## 5. Wiki vs rxdata discrepancies

Checked against `Kevlar_Town.wiki` and `Passage_Cave.wiki`.

1. `Kevlar_Town.wiki` infobox: `north=Route 2`. Matches exactly —
   `connections.json`'s only seam here is `[31,"N",11,35,"S",0]` and map35 is
   "Route 02". No disagreement.
2. `00-atlas.md` §6 #4 characterizes the wiki as treating "Passage Cave" as
   one continuous place. `Passage_Cave.wiki`'s body already distinguishes it:
   the infobox lists only `north=Nowtoch City|south=Route 2` (the
   through-cave, maps 36/37), and a "Grott-Hole" subsection states: *"While
   the grott-hole is a part of the Passage Cave system, it does not connect
   to the through cave between Kevlar Town and Nowtoch City."* Exact
   agreement with the §2 warp trace. **Not actually a disagreement** — the
   wiki corroborates the CH03 binding once read past its own nav infobox.
   Flagged for the atlas owner in §7; not changed here.
3. `Kevlar_Town.wiki` Bicycle Shop: the Bike Wheel "can be found on Route 4"
   (CH11, Act 3). No map in this chapter grants one (no `pbReceiveItem`/
   `code-126` of `BIKEWHEEL` anywhere in the roster). If current, B10 is
   **not completable during a CH03 visit-1 playthrough** — only the shop
   logic exists here. See §7.
4. Wiki gives Mawuli 3× Chyinmunk lv.4, repeatable grinding. Data agrees on
   the repeatable mechanic (EV14 heals + re-offers, no state advance); team
   composition lives in PBS trainer data, outside this document's scope.
5. Wiki places Oran/Pecha Berry pickups "below/left of the Berry Boutique" —
   matches the 5 `BerryPlant` events on **Map031** (ids 42–46, x32–36/y5–10),
   clustered outside the Map031 EV4 door (35,6) into the Boutique. No
   disagreement.
6. No other discrepancies found.

## 6. Expected conversion work and risks

### 6.1 Mechanics binding table

Verdicts owned by `reference/guides/command_pokeemerald_map.md`.

| Mechanic | First appears here? | Disposition | Ledger row / notes |
|---|---|---|---|
| poké mart | **Yes** | native `pokemart` (classifier 9) | `00-atlas.md` §5 |
| boulder pushing (`pbPushThisBoulder`) | **Yes** | **object-driven** — `OBJ_EVENT_GFX_PUSHABLE_BOULDER`, **not** `MB_PUSHABLE_BOULDER`; corrected in the ledger, do not re-invert | `reference/guides/command_pokeemerald_map.md` |
| PC access | No — already CH01 (`Map048` `pbTrainerPC`, `Map050` `pbPokeCenterPC`) | native | Adds the first *public* Center PC + tutorial NPC, not the mechanic — corrects the task brief's premise, see §7 |
| gift pokemon | No — already CH01 (`Map050` starter, 2× `pbAddPokemon`) | native `givemon` | Adds 2 more instances (Magikarp, "Compensation Man" Luxi) |
| trainer battle | No (CH01) | native | §4.1 |
| trainer sight | No (CH02) | native | map19's 2 sight-trigger Bikers |
| item ball / item grant | No (CH01/CH02) | native `giveitem` | §4.2 |
| cave entry/exit | No (CH02) | native | map19 |
| berry plant | No (CH02) | native berry trees | map31 |

### 6.2 Unmapped script heads

| Head | Assessment |
|---|---|
| `get_character` | Resolves an actor ref for move-route/animation; likely a classifier gap, not a new feature |
| `id` | Bare local-var assignment (`id=pbNextMysteryGiftID`), not a call — head-detector misfires |
| `pbCallBub` | Dialogue textbox positioning; near-ubiquitous cosmetic no-op |
| `pbNextMysteryGiftID` | Mystery Gift query (map67 Deliveryman); deferred feature |
| `pbPokerus` | Pokérus check at the healing counter; flavor RNG, needs an analog or no-op |
| `pbPushThisBoulder` | First appearance here — object-driven push, §6.1 |
| `pbSetPokemonCenter` | Marks the map as a healing location; likely native healing-location metadata |
| `pbSetSelfSwitch` | Explicit self-switch set from script; converter should already handle self-switches generically |
| `setTempSwitchOn` | RGSS scratch-flag idiom; local UI bookkeeping only |

### 6.3 Known risks / gaps

- Conversion-readiness is **unmeasured** for all 5 maps — none are in
  `SLICE_MAP_IDS = [49,48,32,50,64,65,172,89]`, so `unhandled` is `null`.
- Map73 and map19 both need `map_name_overrides.json` entries before
  Phase-5 mint (name/engine-dir collisions — details in §7).
- The Cry Boy → Richboy chain (sw99/100) and the Bike Wheel grant (B10) both
  look unreachable within this chapter's own data (details in §7).
- The Berry Boutique's `pbPokemonMart([...])` (EV3/EV6) is a second, distinct
  item-list shop call, same special as the Poké Mart (map67) — no engine
  concern, just two shops sharing one census mechanic tag.
- Tileset/art budget not assessed this pass.

## 7. Open items for the lead

- **Map73 name/engine dir** (§2): proposed `Kevlar Town Buildings` /
  `KevlarTownBuildings` / `MAP_KEVLAR_TOWN_BUILDINGS`, provisional — evidence
  is the 4 doors from map31 landing at 4 distinct x-regions inside map73
  (x≈5 Bike Shop, x≈24 Maury's apartment, x≈44 Berry Boutique, x≈64 a
  couple's house). Needs a `map_name_overrides.json` entry.
- **Map19's engine dir** needs disambiguation from maps 36/37 (same
  `map_infos.json` name "Passage Cave"); proposed `PassageCaveGrottHole` /
  `MAP_PASSAGE_CAVE_GROTT_HOLE`, unreviewed. Separately, the existing
  `map_name_overrides.json` "reviewed" entry for map19 describes it as the
  through-cave, contradicted by my warp trace and the wiki (§5 #2) — I did
  not edit that file; flagging for its owner.
- **Cry Boy → Richboy reachability** (B12, §3): sw86 gates the offer and is
  written exactly once corpus-wide (Map140/Route11 CH25), to **0/off**.
  Checked via a full-corpus scan of `code-121` writes to switch86 plus
  `common_events.json`; doesn't rule out a grant in raw embedded Ruby text
  outside those two command shapes.
- **Bike Wheel source** (B10, §5 #3): absent from this chapter; wiki says
  Route 4, but the Boutique's own item list shows version-dependent content
  ("As of 1.0… as of 1.2.6…"), so that claim may be stale. Needs a
  corpus-wide `pbReceiveItem(...BIKEWHEEL...)` search before
  `chapters.json`'s "Introduces the bike" note can be read as the *grant*,
  not just the shop, being CH03 content.
- **"Compensation Man" (map31 EV50, Luxi gift)** is gated on sw130
  (`FLAG_FILE_RECOVERY`), never written anywhere in the corpus (on or off,
  like sw86) — reads as a developer save-recovery event, not normal
  progression; flagging so it isn't mistaken for a testable beat.
- **Trainer team compositions** for Lou/Joe/Richard/Mawuli were not verified
  against PBS trainer data — out of this document's map-JSON scope.

---

*Companion docs: `reference/chapters/00-atlas.md` (corpus-wide binding and
mechanics inventory), `reference/chapters.json` (CH03 binding record),
`reference/map_name_overrides.json` (map identity arbitration — needs new
entries per §7), `reference/guides/command_pokeemerald_map.md` (mechanics
capability ledger), `ROM_TEST_DEV.md` (Branch A/B house-style decisions this
document implements).*
