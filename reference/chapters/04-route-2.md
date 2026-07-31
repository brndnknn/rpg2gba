# Chapter 4 — Route 2

**Status:** new chapter document, authored directly from the converted rxdata
per `ROM_TEST_DEV.md` Branch A (rxdata-first, wiki cross-check only). Tier
**medium** per `reference/chapters.json`. This is the spec a chapter test
scenario gets written from — it is not itself a test, and it carries no
narrative content (house style: gates and effects only, per Branch A2).
**Not yet converted or boot-walked**; §6 records expected work, not observed
defects.

**Method note:** every fact below (outside §5) was read directly from
`reference/chapters.json` (CH04/CH07 records), `output/uranium-build/map_infos.json`,
`output/uranium-build/connections.json`, `output/uranium-build/maps/Map035.json`
(and, for the cave hand-off, `Map036.json`/`Map037.json`), `output/uranium-build/intermediate/wild_encounters.json`,
`output/uranium-build/flag_state.json`, and `chapter_atlas census --chapter
CH04` / `--chapter CH02` output, checked 2026-07-31. The cached
`output/uranium-build/wiki/Route_2.wiki` was consulted **only** for §5.

---

## 1. Purpose / scope

Chapter 4 = the first visit to Route 2, a single map (RMXP id 35, "Route 02",
42×57) linking Kevlar Town (CH03) to the north. Map roster:
`reference/chapters.json` CH04 — `"maps": [35]`. Census totals
(`chapter_atlas census --chapter CH04`): 21 events, 40 pages, 398 commands, 4
trainer battles, 3 item grants, **2** switch writes, **0** variable writes, 22
conditionals, 27 move routes.

Mechanically: a straight south-to-north walk through tall grass. Two trainer
battles and one item ball are reachable immediately; a five-boulder rockslide
then blocks all further progress, and the only way onward is the
cave-entrance warp into Passage Cave (CH05). A second pocket of the map — two
more trainer battles, two more item balls, and the scripted event that
eventually clears the rockslide — sits beyond that gate, out of scope for
this visit; `reference/chapters.json` records it opening on the CH07 revisit.
Route 2 does not advance any persistent state variable at all (§3).

## 2. Map inventory

| RMXP id | Uranium identity (`map_infos.json`) | Engine dir | porymap constant | Role in chapter |
|---|---|---|---|---|
| 35 | Route 02 (id 35, `parent_id` 55) | `Route2` (proposed, unassigned — §7) | `MAP_ROUTE_2` (proposed) | Whole chapter; mountain-pass corridor, rockslide gate mid-route |

**Wiring.** South edge: `connections.json` `[31,'N',11,35,'S',0]`, a
borderless seam to Map031 (Kevlar Town, CH03) — the entry boundary. North
edge: `connections.json` `[35,'N',0,40,'S',15]`, a borderless seam to Map040
(Nowtoch City, CH06); it exists in the graph but is unusable this chapter
(§3/§6) — CH07's ("Route 2 (revisit)") note "Rock Smash clears the
rockslide; the overland 35<->40 seam becomes usable" confirms it is closed on
visit 1. The real exit is a warp, not a seam: `Map035.json` id 1 ("EV001",
20,33), the map's only `code 201` command, transfers to Map036 (17,39),
Passage Cave's entrance (CH05). Map036 warps to Map037, which warps to
Map040, confirming the atlas's "35→36↔37→40" traversal note from this side.

## 3. Story beat chain

**No `VAR_QUEST_LOG` write, and no `code 122` (variable) command of any kind,
exists anywhere in `Map035.json`** (grep for code 122: zero hits, matching
the census's absent `var_writes`). The only `code 121` (switch) writes are a
pair on one event, and they are not a story gate:

```
FLAG_MENU_ON_EVENT (switch 185) OFF ──[Map035.json id2 "EV002" pg0]──► show sign text ──► ON
```

(id 2 "EV002" @(19,34): `code 121 [185,185,0]`, a `code 101` Show Text ("Old
entrance to Nowtoch City."), then `code 121 [185,185,1]`. `flag_state.json`
names switch 185 `FLAG_MENU_ON_EVENT` — a generic menu-lock bracket around a
message, not a chapter flag. This is the census's entire `switch_writes=2`.)

Route 2 is a pure traversal chapter: the beat chain below is built from the
map's only real gate — the rockslide — plus entry/exit, not from any write.

| Beat | Map | Gate | Player action (test) | Expected effect (observable) |
|---|---|---|---|---|
| B1 | 31 → 35 | none | walk north across the `31 N<->S 35` seam | player arrives on Map035's south edge |
| B2 | 35 | none | reach (18,36) | id 3 "Trainer(5)" (event-touch) fires `pbTrainerBattle(HIKER,"Larrie",…)`; win or lose, `pbPhoneRegisterBattle(...)` registers a phone rematch |
| B3 | 35 | none | walk onto (16,42) | id 9 "EV009" pg0, default (ungated): `Kernel.pbItemBall(POTION)` grants one Potion, self-switch A set (one-shot) |
| B4 | 35 | none | reach (18,47) | id 12 "Trainer(3)" (event-touch) fires `pbTrainerBattle(YOUNGSTER,"Timothy",…)` |
| B5 | 35 | none | read id 13 "EV013" @(10,30) | Show Text: "In the event of a roadblock, Nowtoch City may be reached through Passage Cave." — in-fiction hint for B6, no state change |
| B6 | 35 | the rockslide | try to continue north through (19–22, 28–29) | **Blocked** — 5 "Rock" events (ids 14–18, graphic `fk107-rocksmash`) are each impassable until individually cleared via `Kernel.pbRockSmash`, unavailable this chapter (Rock Smash is a CH06 grant). No route north exists on visit 1 |
| B7 | 35 → 36 | none | walk onto the cave-entrance tile (20,33) | id 1 "EV001" pg0: `pbCaveEntrance`, then `code 201` warp to Map036 (17,39) — hands off to CH05 |

## 4. Coverage targets

Enumerated from `Map035.json` and `wild_encounters.json`. All four
subsections are exhaustive, not sampled — only 4 trainer events, 3 item
grants, 1 encounter table, and 1 warp exist, so full enumeration is as cheap
as a notable-rows summary would have been.

### 4.1 Trainer battles

| Map | Event | Trigger | In-chapter reachable? | Notes |
|---|---|---|---|---|
| 35 | Hiker Larrie (id 3, "Trainer(5)") | event-touch @(18,36) | Yes (B2) | south of the rockslide gate |
| 35 | Youngster Timothy (id 12, "Trainer(3)") | event-touch @(18,47) | Yes (B4) | south of the gate |
| 35 | Bird Keeper Brent (id 23, "Trainer(4)") | event-touch @(26,9) | **No** | north of the gate (§2); reachable only after Rock Smash, on the CH07 revisit |
| 35 | Hiker Chuck (id 24, "Trainer(4)") | event-touch @(29,23) | **No** | same reason |

All 4 `pbTrainerBattle` calls on the map are listed (matches census
`trainer_battles=4`). `[auto]`

### 4.2 Item balls / given items

| Map | Item | Event | Gate | In-chapter? |
|---|---|---|---|---|
| 35 | Potion | id 9 "EV009" @(16,42) | ungated (default page) | Yes — B3 |
| 35 | Super Potion | id 25 "EV025" @(30,10) | ungated (default page) | **No** — beyond the gate |
| 35 | TM78 (Captivate) | id 26 "EV026" @(29,29) | ungated (default page) | **No** — beyond the gate, next to the rock cluster |

All 3 `Kernel.pbItemBall` calls on the map are listed (matches census
`item_grants=3`). `[auto]`

### 4.3 Wild encounters

| Map | Table | Contents | In-chapter reachable? |
|---|---|---|---|
| 35 | `land_mons` (rate 25) | 12-entry table: Chyinmunk, Birbie, Cubbug, Barewl, Mankey, Owten, all lv3–5 | Yes — the whole grass corridor south of the gate |

`wild_encounters.json`'s `maps["35"]` has only the `land_mons` key — no
`water_mons`/`fishing_mons` table exists for this map. `[auto]` The rock
events (ids 14–18) each call `Kernel.pbRockSmashRandomEncounter` on a
successful smash, but no discrete `rock_smash_mons` table exists for map 35
anywhere in `wild_encounters.json` (only map 118 has one corpus-wide) — a
converter-data gap, moot for visit 1 since Rock Smash isn't available yet.

### 4.4 Warps

| Map | Warp | Destination | Chapter-relevant? |
|---|---|---|---|
| 35 | Cave entrance @(20,33) (id 1 "EV001") | Map036 (17,39) | Yes — B7, the chapter's exit into CH05 |

The map's only `code 201` command (count confirmed: 1). The two
`connections.json` seams (to Map031/CH03, to Map040/CH06) are borderless
map-edge connections, not warps — covered in §2's Wiring instead. `[auto]`

## 5. Wiki vs rxdata discrepancies

Checked against `output/uranium-build/wiki/Route_2.wiki`.

1. **Route description matches the data.** Wiki: "...two routes north from
   Kevlar Town to Nowtoch City. The overland route is initially blocked by a
   rockslide, forcing you to take Passage Cave, but after you reach Nowtoch
   City (and defeat Maria at the Gym), you may double back... When you reach
   the east side of the rockslide, a Pokémon Ranger appears and clears it for
   you." Corroborates §3/§6: the 5 "Rock" events (ids 14–18) are the
   rockslide, and id 19 ("Trainer(4)" @(25,26), an invisible event-touch
   trigger despite its template name) is the Ranger scene, whose script
   clears the same 5 ids via `for i in 14..18: pbSetSelfSwitch(i,"A",true)`.
   No disagreement.
2. **Item locations match** (Potion SW of the cave/S of Larrie; Super Potion
   E of Brent; TM78 S of Chuck) — confirmed by event coordinates. TM78's
   "hidden behind large boulder" detail has no distinct boulder event at
   (29,29) to check it against; unconfirmable, not a contradiction.
3. **Wiki's catch table lists a Poké Radar division** (Dunsparce, Tofurang)
   absent from `wild_encounters.json` (only `land_mons` for map 35). Data
   wins: no Radar table is modeled here. Recorded as a gap, not resolved.
4. **Trainer team compositions aren't checkable** from this map — those
   rosters live in PBS trainer data, out of scope here.

## 6. Expected conversion work and risks

### 6.1 Mechanics binding table

Verdicts are owned by `reference/guides/command_pokeemerald_map.md`; this
table only points at `00-atlas.md` §5. **None of these mechanics make a
first appearance in CH04** — `chapter_atlas census --chapter CH02` (Route 1)
already lists all 8, and CH04 carries no novelty-promotion note in
`reference/chapters.json` (unlike CH02's own, or CH06's "Rock Smash grant"),
consistent with staying `medium`.

| Mechanic | First appears here? | Disposition | Ledger row / notes |
|---|---|---|---|
| cave entry/exit | No (by CH02) | native | `00-atlas.md` §5 |
| item ball | No (by CH02) | native `giveitem` (classifier 8) | `00-atlas.md` §5 |
| phone / rematch | No (by CH02) | likely native Match Call | `00-atlas.md` §5 (corrected 2026-07-30) |
| rock smash | No (by CH02, Route 1) | native | `00-atlas.md` §5 |
| rock smash encounter | No (by CH02, Route 1) | native | `00-atlas.md` §5; no table for map 35, §4.3 |
| trainer battle | No (by CH02) | native — hidden in `code 111` conditionals | `00-atlas.md` §5; CLAUDE.md §4.7 trap |
| trainer sight | No (by CH02) | native | `00-atlas.md` §5 |
| wild encounters | No (by CH02) | native; day/night tables are a converter gap | `00-atlas.md` §5 |

### 6.2 Unmapped script heads

| Head | Assessment |
|---|---|
| `get_character` | id→event-object resolver (`get_character(0)`=player), used for `pbNoticePlayer`/`onEvent?` checks — needs an id lookup in the transpiler, not a real gap |
| `pbCallBub` | speech-bubble/emote overlay (Ranger scene) — cosmetic, no state effect |
| `pbEraseThisEvent` | removes the calling event after a one-shot action (each of the 5 rocks) — needs a `removeobject`-equivalent |
| `pbSetSelfSwitch` | sets a **remote** event's self switch by id, not "this event" — the Ranger scene mass-clears rock ids 14–18 with it; needs an id-indexed setter |
| `setTempSwitchOn` | transient/local flag (cave warp's page-1 bracket) — likely a scratch flag, not a registry entry |
| `trainer` | bare Ruby local inside `customTrainerBattle(trainer,…)` (rematch pages) — a tokenizer artifact of that call, not a real head |

### 6.3 Known risks / gaps

- **Conversion-readiness is unmeasured for map 35** (`unhandled: null`) — not
  one of the 8 slice-1 maps, so the transpiler's queue has never staged it.
- **No `rock_smash_mons` table for map 35** — moot for visit 1, relevant once
  CH07 opens the north side.
- **NE-quadrant reachability and the engine dir/porymap constant are both
  unconfirmed** — no tile-passability data and no naming pass yet; both
  carried into §7.

## 7. Open items for the lead

- **NE-quadrant reachability (§4.1/§4.2) is an inference, not a directly
  measured fact** — no passability grid exists to confirm the rock cluster
  (ids 14–18) is the *only* path north. Rests on the sign text (id 13), the
  CH07 revisit note, and wiki corroboration (§5#1). Settled by a
  passability-grid read, if the pipeline ever exposes one.
- **Switch 22**, gating id 1 "EV001" page 1 (an autorun player-nudge before
  `setTempSwitchOn("A")`), has no name in `flag_state.json`; purpose beyond
  "skip if mid-interaction" unconfirmed. A corpus-wide switch audit would
  settle it.
- **Engine dir/porymap constant for map 35** are proposed (`Route2` /
  `MAP_ROUTE_2`) but unassigned — no naming pass has run for this map yet.

---

*Companion docs: `reference/chapters/00-atlas.md` (corpus-wide model and
mechanics inventory), `reference/chapters.json` (CH04/CH05/CH06/CH07 binding
records), `reference/findings/grill_chapter_atlas_2026-07-30.md` (design
record), `ROM_TEST_DEV.md` (Branch A/B decisions this document implements).*
