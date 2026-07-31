# Chapter 6 — Nowtoch City

**Status:** new chapter document, authored directly from the converted rxdata
per `ROM_TEST_DEV.md` Branch A (rxdata-first, wiki cross-check only). Tier
**medium** per `reference/chapters.json`. This is the spec a chapter test
scenario gets written from — it is not itself a test, and it carries no
narrative content (house style: gates and effects only, per Branch A2).
**Not yet converted or boot-walked**; §6 records expected work, not observed
defects.

**Method note:** every fact below was read directly out of
`output/uranium-build/maps/Map0{40,41,42,43,44,45,46,47}.json`,
`output/uranium-build/map_infos.json`, `output/uranium-build/connections.json`,
`output/uranium-build/intermediate/wild_encounters.json`,
`output/uranium-build/flag_state.json`, `reference/chapters.json`, and
`reference/guides/command_pokeemerald_map.md` (checked 2026-07-31),
cross-checked against `.venv/bin/python -m rpg2gba.chapter_atlas census
--chapter CH06`. `engine/data/specials.inc` / `engine/asm/macros/event.inc`
(the vendored fork) were grepped directly for §6.1's native-analog claims
per `CLAUDE.md` §4.7. The wiki (`output/uranium-build/wiki/Nowtoch_City.wiki`)
was consulted only for §5.

---

## 1. Purpose / scope

Chapter 6 is Act A1's terminal chapter (`reference/chapters.json` CH06,
`visit: 1`), predecessor **CH05 Passage Cave**. 8 maps, `[40,41,42,43,44,45,46,47]`.
At 206 events / 2180 commands it is the densest chapter in Act 1 — nearly
three times CH01 Moki Town's command count on the same map count.

Mechanically: the player arrives from Passage Cave onto the outdoor hub (40).
The Gym (42) is closed until an item-gated house visit and an indoor cutscene
unlock it (§3); clearing its 2 trainers and Leader is Act 1's exit gate. Side
content: the Mart (41), Pokémon Center (43), and a large packed-interior
canvas (46) holding a Ranger office, the game's first Move Tutor, and its
first scripted in-game trade, plus a second interior (47) tied to the
Gym-unlock cutscene. A Metro building (44/45) offers a 3-city fast-travel
menu — present in the data but its early availability is questioned in §5/§6.
The chapter ends walking south across the Route 2 seam into Act 2 (CH07).

## 2. Map inventory

| RMXP id | Uranium identity (`map_infos.json`) | Engine dir | porymap constant | Role in chapter |
|---|---|---|---|---|
| 40 | Nowtoch City (outdoor, 79×74, tileset 23) | `NowtochCity` | `MAP_NOWTOCH_CITY` | Hub; Gym gate, doors, item balls, cave return, rival rematch |
| 41 | Nowtoch City(Pokemart) (20×15, tileset 4) | `NowtochCityPokemart` | `MAP_NOWTOCH_CITY_POKEMART` | Mart, 2 clerks, identical stock |
| 42 | Nowtoch City(Gym) (20×35, tileset 19) | `NowtochCityGym` | `MAP_NOWTOCH_CITY_GYM` | Gym 1: 2 trainers + Leader Maria; badge grant |
| 43 | Nowtoch City(Pokemon Center) (20×20, tileset 42) | `NowtochCityPokemonCenter` | `MAP_NOWTOCH_CITY_POKEMON_CENTER` | Heal/PC (`pbPokeCenterPC`); PVP+Trade receptionists just call Common Event 6 |
| 44 | Nowtoch City(Metro) (20×15) | `NowtochCityMetroStation` | `MAP_NOWTOCH_CITY_METRO_STATION` | Ticket kiosk (sells `TURTICKET`) + region-map viewer (`pbShowMap`) |
| 45 | Nowtoch City(Metro), parent=44 (40×15) | `NowtochCityMetroPlatform` | `MAP_NOWTOCH_CITY_METRO_PLATFORM` | Departure gate: 3-destination menu warp (Burole/Legen/Bealbeach), 1 item ball |
| 46 | Nowtoch City (60×40, tileset 19 — **interior**, shared w/ 42/48/49) | `NowtochCityInteriors1` | `MAP_NOWTOCH_CITY_INTERIORS_1` | Packed multi-building/floor interior canvas — see Wiring, §7 |
| 47 | Nowtoch City (35×15, tileset 19 — **interior**) | `NowtochCityLeaderHouse` | `MAP_NOWTOCH_CITY_LEADER_HOUSE` | 2-room interior behind the Fufufu door key check; hosts the Gym-unlock cutscene |

**Wiring.** Entry: `Map037.json` event 2 (Passage Cave) warps to Map040
(68,43), the only inbound seam; Map040 event 19 is the return warp,
confirming the CH05/CH06 boundary. Exit: `connections.json`'s only entry
touching map 40, `[35,"N",0,40,"S",15]`, is a continuous overland seam south
into Route 2 (map 35) — also CH07's start. Maps 41–45 are conventional
single/double-door interiors. Maps 46/47 differ: `parent_id` for both is 40
(not a numbered floor), both share tileset 19 — the interior tileset also
used by the Gym and CH01's player-house maps, confirming indoor canvases
despite carrying the bare outdoor-map name — and each is reached from
multiple, physically distinct doors on map 40 (46: events 16, 27/55, 64, 65,
landing at 4 points inside 46; 47: events 17 and 66). Map 46 also carries 10
`code 201` warps whose destination is map 46 itself — internal door/floor
transitions, RPG Maker's "several buildings/floors on one map file" idiom,
not a second outdoor district (§7 flags the unresolved split).

## 3. Story beat chain

Controlling writes: `VAR_QUEST_LOG` (var 101, same global spine as
`01-moki.md` §3) plus 4 chapter-local switches gating the Gym:
`FLAG_GYM1_HOUSE_EVENT` (sw 102), `FLAG_GYM1` (sw 101 — a different id-space
from `VAR_QUEST_LOG`), and the post-badge pair
`FLAG_DEFEATED_GYM1_LEADER`/`FLAG_GYM_1_TRAINERS_OFF` (sw 55/58):

```
FLAG_GYM1_HOUSE_EVENT OFF ──(Map040 EV017, door, holds MARIAKEY)──► ON
        │
        ▼
FLAG_GYM1              OFF ──(Map047 EV013, page gated on above)──► ON
        │                    (unlocks Map040 EV014 page 1 — the gym door)
        ▼
[defeat Gym trainers + Leader Maria, Map042 EV003]
        ├─ FLAG_DEFEATED_GYM1_LEADER  OFF ──► ON
        ├─ FLAG_GYM_1_TRAINERS_OFF    OFF ──► ON
        └─ VAR_QUEST_LOG  n ──(code 122, add +1)──► n+1
```

Of 23 switch writes, only these 4 gate progression; the other 19 are
bookkeeping — 14 `FLAG_MENU_ON_EVENT` dialogue-portrait toggles, 3
`FLAG_TM07` give-once guards on the HM06 grant below, 2 Center system flags
reused across every town. Of 20 variable writes, only `VAR_QUEST_LOG` gates
progression (as an **add**, not a hard-set — absolute value not determined
here, see §7); the other 19 are `VAR_PEOPLE_TALKING` (6, dialogue plumbing),
`VAR_RIVAL_QUEST`/`VAR_RIVAL_QUEST2` (9, cross-chapter rival tracker),
`VAR_RESERVED_POKEMON_COUNT` (2, Center system), `VAR_TEMP_MOVE_CHOICE` (1,
Move Tutor scratch var), `VAR_BATTLE_VAR01` (1, generic battle-intro slot).

| Beat | Map | Gate | Player action (test) | Expected effect (observable) |
|---|---|---|---|---|
| B1 | 40 | none | talk to "Fufufu" (event 18, (49,15)) | `MARIAKEY` added to bag |
| B2 | 40 | hold `MARIAKEY` | interact with door EV017 (event 17, (47,61)) | door unlocks; `FLAG_GYM1_HOUSE_EVENT` OFF→ON; warp to Map047 (5,9) |
| B3 | 47 | `FLAG_GYM1_HOUSE_EVENT` valid | walk onto EV013's tile (event 13, (4,10)) | scripted wake-up scene; `FLAG_GYM1` OFF→ON |
| B4 | 40 | `FLAG_GYM1` valid | approach gym-door NPC (EV014, event 14, (49,14)) | page 0 ("Gym is closed!") flips to page 1: move-route scene → warp to Map042 (9,24) |
| B5 | 42 | in the gym | defeat 2 Gym trainers (events 1 "Myla", 2 "Jack") | trainer-sight/battle only; ungated, not required to reach the Leader |
| B6 | 42 | reach Leader | defeat Leader Maria (event 3 "EV003") | `TM27` granted; `FLAG_DEFEATED_GYM1_LEADER` + `FLAG_GYM_1_TRAINERS_OFF` OFF→ON; `VAR_QUEST_LOG` += 1 |
| B7 | 40 | `FLAG_DEFEATED_GYM1_LEADER` valid | rematch Theo, any of 3 copies (events 20, 21, 79) | `HM06` granted (Rock Smash, chapter's headline item); rival-tracker bookkeeping writes |

## 4. Coverage targets

Enumerated from the converted data; totals per the census, notable/risky rows
enumerated per medium-tier convention.

### 4.1 Trainer battles

6 total, matching the census. All 3 Theo-rematch copies are the **same
logical encounter** (identical `pbTrainerBattle(RIVAL,"Theo",…)`, identically
gated), duplicated for different approach paths — same pattern as
`01-moki.md` §4.2's duplicate-row item grant.

| Map | Event | Trigger | In-chapter reachable? | Notes |
|---|---|---|---|---|
| 42 | "EV003" (Leader Maria) | talk, ungated | Yes (B6) | Badge climax; only `LEADER_*` trainer here |
| 40 | events 20, 21, 79 (Theo rematch ×3) | talk, `FLAG_DEFEATED_GYM1_LEADER` | Yes (B7) | Same logical battle, 3 copies (§3) |

Remaining 2 (Gym trainers "Myla"/"Jack", map 42) are routine and ungated. `[auto]`

### 4.2 Item balls / given items

11 grant commands, matching the census; 9 distinct logical grants (HM06 ×3 = 1).

| Map | Item | Event | Gate | In-chapter? |
|---|---|---|---|---|
| 40 | `HM06` (Rock Smash) | events 20/21/79 | `FLAG_DEFEATED_GYM1_LEADER` | Yes — B7, headline grant |
| 42 | `TM27` | event 3 "EV003" | badge battle won | Yes — B6 |
| 46 | Pokémon trade (`pbStartTrade`, event 14) | — | ungated door reach | Yes, but not a `pbReceiveItem` — see §6.2 |

Remaining 6 (`MARIAKEY` B1; `XATTACK` item ball event 60; `FRESHWATER` map 42
event 4; `GREATBALL` item ball map 45 event 2; `FULLHEAL` map 46 event 17
"RangerF"; `POTION`×5 map 46 event 20 "NPC"; `TM45` map 46 event 24) are all
ungated walk-up grants — routine, reachable. `[auto]`

### 4.3 Wild encounters

**Zero.** `wild_encounters.json`'s `maps` object has no entry for any of
maps 40–47 (confirmed directly and via the census, which shows no `enc[...]`
annotation on any of the 8 map lines). Expected for an all-urban chapter, but
a direct **correction** to this task's brief, which stated 1 of 8 carries a
table — see §7.

### 4.4 Warps

41 `code 201` commands total (40=15, 41=1, 42=1, 43=2, 44=2, 45=4, 46=14,
47=2) — higher than the door count because arrival warps are emitted
alongside source warps (`01-moki.md` §4.4 same pattern). The 2
chapter-boundary warps:

| Map | Warp | Destination | Chapter-relevant? |
|---|---|---|---|
| 40 | event 19 "EV019" | Map037 (Passage Cave, CH05) | Yes — chapter entry |
| 40 | south edge (`connections.json`) | Map035 (Route 2, CH04/CH07) | Yes — chapter **exit**, the only one |
| 45 | event 3 "Subwaymenu" | Maps 6/168/11 (Burole/Legen/Bealbeach Metro) | **No** — ticket-gated (§6.2), destinations outside CH06's roster regardless |

Remaining 38 are intra-chapter door/floor warps (mart/gym/center/metro doors,
plus map 46's 10 internal floor-to-floor warps) — routine. `[auto]`

## 5. Wiki vs rxdata discrepancies

Checked against `output/uranium-build/wiki/Nowtoch_City.wiki`.

1. **Wiki labels the Rock Smash reward "HM01."** The rxdata's constant for
   the B7 grant is `PBItems::HM06`. Wiki's label is the move name, not
   Uranium's own HM index; data's `HM06` is authoritative.
2. **Wiki: Move Tutor "will only teach moves if you have acquired 4
   badges."** Rxdata gates the tutor's teaching page (event 3, map 46) on
   switch 85 (`FLAG_METRO_MASTER`), not a badge count — no such conditional
   exists in that page. Both agree the tutor is non-functional this chapter
   (nothing in CH06 sets switch 85); they disagree on *what* ungates it.
   Data wins: the observable gate is `FLAG_METRO_MASTER`.
3. **Wiki: the Metro "is still under construction and cannot be used" on
   first visit.** Not enforced in the rxdata: the ticket kiosk (map 44,
   event 4) sells `TURTICKET` ungated, and the departure menu (map 45, event
   3) is an ungated default page too — the only in-script gate is holding a
   ticket, purchasable on the spot. No switch/var blocks either. Open
   sequence-break question, not resolved here — see §7.
4. **No discrepancy** on the Gym-unlock house-visit account, the item list
   (X Attack/TM45/TM27/Fresh Water/Full Heal/Potion/Great Ball all
   corroborated), or the Ranger-HQ item givers — all match §2–§4 above.

## 6. Expected conversion work and risks

### 6.1 Mechanics binding table

Verdicts owned by `command_pokeemerald_map.md`; this table only binds.
**Bold** = first appearance in the corpus (`chapters.json` notes: "First Gym,
first metro/Tandor-Underground station, and the Rock Smash grant").

| Mechanic | First appears here? | Disposition | Ledger row / notes |
|---|---|---|---|
| trainer battle, trainer sight, item ball/grant, poke mart, PC access, cave entry/exit | no | native | existing DET/WIRE rows |
| **region map** | yes | native | not in the ledger by head (`pbShowMap`); verified this pass: `special FieldShowRegionMap`, `engine/data/specials.inc:274`. `00-atlas.md` §5 already lists "region map: native" |
| **Pokémon trade** | yes | native (⚠RECHECK exact special) | ledger row `pbStartTrade` (WIRE); verified this pass: `CreateInGameTradePokemon`/`DoInGameTradeScene`, `engine/data/specials.inc:275-277` |
| **Move Tutor** | yes | native | no ledger row for `pbMoveTutorChoose` (only `pbMoveTutor` is listed); verified this pass: `special ChooseMonForMoveTutor`, `engine/data/specials.inc:498`, wired via `event.inc:2696-2701`. Recommend adding a row |
| **metro fast travel** | yes | **unresolved** | not in the ledger; `census.py`'s `pbMetro` head is never actually called here — see §7 |

### 6.2 Unmapped script heads

14 heads — one more than this task's briefing listed (`pkmn` appears in the
live re-run, absent from the brief; flagged in §7).

| Head | Assessment |
|---|---|
| `get_character` | Plumbing — event/player object by local id; needs local-id resolution, not a mechanic |
| `id` | Plumbing — bare attribute read inside a larger expression |
| `pbCallBub` | STRIP per ledger — cosmetic emote bubble |
| `pbChoosePokemon` | JUDGE per ledger — feeds the map-46 trade and Move Tutor flows |
| `pbGetPokemon` | Plumbing paired with `pbChoosePokemon`, same JUDGE bucket |
| `pbMoveTutorChoose` | Converter gap only — native (§6.1), missing its own ledger row |
| `pbNextMysteryGiftID` | Mystery Gift plumbing; ledger's `pbReceiveMysteryGift` is ⚠RECHECK/STRIP-leaning |
| `pbPlayCry` | STRIP per ledger — cosmetic |
| `pbPokerus` | **Not in the ledger at all** — genuinely unassessed, real gap to raise centrally |
| `pbSetPokemonCenter` | STRIP per ledger — respawn already captured by `metadata.py` §2.8 |
| `pbSetSelfSwitch` | DET per ledger — classifier candidate |
| `pbStartTrade` | Converter gap only — native (§6.1) |
| `pkmn` | Plumbing — bare local alias, pairs with ledger's `pkmn.setAbility`/`setItem` JUDGE row |
| `setTempSwitchOn` | DET per ledger — orchestrator-minted classifier candidate |

### 6.3 Known risks / gaps

- **Conversion-readiness is unmeasured for all 8 maps** (`unhandled: null` —
  none staged; `00-atlas.md` §7 gap 1). No defect claims from this document.
- **Choices (21) cluster in map 46**: 15 of 21 (12 in the Move Tutor event,
  3 in the trade flow) vs. 4 in the metro's Subwaymenu and 1 each at the
  Center/Kiosk — the chapter's branch-heaviest event set, most likely tail
  work for the LLM tool rather than the deterministic transpiler.
- **Map 46's building/floor split is inferred, not confirmed** — 4 external
  doors plus 10 internal warps suggest several buildings and/or multiple
  floors packed on one 60×40 canvas (wiki's "third floor, same building as
  Name Rater" corroborates a multi-floor building somewhere here). A
  faithful porymap conversion likely needs to **split map 46 into several
  map files** — a real Phase-5 risk, not just a naming question.
- **Metro fast-travel has no native-equivalent ledger binding yet** (§6.1) —
  every primitive (choice menu, screen tone, SE, warp) is native, but no
  mechanic row certifies that centrally, and (§5 item 3) the kiosk/menu are
  ticket-gated only, not switch-gated — whether destination-side gating
  exists is unresolved.

## 7. Open items for the lead

- **§4.3 correction**: task briefing says 1 of 8 maps has an encounter
  table; direct inspection + fresh census both show **zero**. Recommend
  correcting the briefing's premise.
- **§6.2 correction**: task briefing lists 13 unmapped heads; the live
  re-run reports **14**, adding `pkmn`. All other totals match exactly —
  worth a second confirmation run before treating this document as final.
- **Metro mechanic has no ledger disposition** (§6.1/§6.3) — what would
  settle it: a ledger pass adding a named "metro fast travel" row, plus
  checking whether Burole/Legen/Bealbeach's own metro-arrival maps gate
  entry independently (out of scope here).
- **Map 46/47 naming is proposed, not verified** (§2, §6.3) — inferred from
  tileset id, door count, NPC names, and item-grant locations matching the
  wiki, but no tile-level render was consulted. A porymap render of map 46
  would confirm or refute the building-split reading.
- **`VAR_QUEST_LOG`'s absolute value** entering/leaving this chapter is not
  determined here — the B6 write is a relative `+1`, and CH02–CH05 aren't
  yet authored to chain the value forward from `01-moki.md`'s exit state.
  Not blocking at medium tier; flagged for a future full-tier promotion.

---

*Companion docs: `reference/chapters/00-atlas.md` (corpus-wide atlas),
`reference/chapters/01-moki.md` (worked full-tier example this document's
register follows), `reference/chapters/TEMPLATE.md` (structure contract),
`reference/guides/command_pokeemerald_map.md` (capability ledger, owns all
§6.1 verdicts), `reference/chapters.json` (CH06 binding record), `CLAUDE.md`
§4.5/§4.7 (fail-loud and verify-against-the-fork).*
