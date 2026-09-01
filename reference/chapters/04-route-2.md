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
| B7 | 35 | none | walk up to the tile adjacent to the cave entrance (20,33) | the approach tile is reachable, and (20,33) itself reads **BLOCKED** — the crossing into Passage Cave is deferred to CH05. See the frontier note below |

**B7 is a frontier beat, not a warp beat (operator decision, 2026-08-25).**
Map 036 is CH05's and is not in `SLICE_MAP_IDS` this chapter, and the pipeline
drops any `code 201` whose destination is out of slice —
`metadata_wiring.classify_event` returns `("skip", "out-of-slice warp")`, so id 1
"EV001" emits no `warp_event` and no object, and `assembly.prune_orphan_blocks`
removes its `.pory` body. The cave-mouth tile therefore compiles as blocked
terrain. This is documented frontier behaviour, not a defect
(`reference/guides/slice_expansion_runbook.md` §5), and it is the same shape CH02
used for its own unstaged exit: `playtest/chapters/ch02.py` B17 walks to the
approach tiles, asserts the boundary reads BLOCKED, and defers the crossing to
the chapter that stages the destination. The three alternatives — pulling map 36
into CH04, or stubbing it — were both rejected as absorbing CH05's scope. Retire
this assertion when CH05 stages map 36; `WARP_OVERRIDES[35]` gets its (20,33)
entry then, not now (listing it earlier stamps a door with no warp behind it).

**B8 falls with B7.** `classify_event`'s skip is decided per *event*, not per
page (`_event_transfers` scans every page, and one out-of-slice `code 201`
skips the whole event), so id 1 "EV001" page 1 — the once-per-visit
`s:tsOff?("A")` autorun that B8 asserts — is not emitted either. B8 is
therefore unwalkable on this chapter for the same reason B7 is, and both
return when CH05 stages map 36. Their manifest rows (`map035/ev001/p0`,
`map035/ev001/p1`) keep their `beat:` dispositions — the disposition records
what the source page *is*, not whether this chapter's slice happens to emit
it — but neither is a CH04 boot-gate assertion.

### 3.1 Manifest reconciliation (2026-08-22)

The B1–B7 table above was authored 2026-07-31, before the generated manifest
existed. It is now bound to `reference/manifests/CH04.manifest.json` (42 rows)
and `reference/manifests/CH04.dispositions.json`. The manifest is the approval
object; this table is the prose rendering of it, not a second source of truth.

| Beat | Manifest row(s) |
|---|---|
| B1 | `map035/seam/S/map031` |
| B2 | `map035/ev003/p0` |
| B3 | `map035/ev009/p0` |
| B4 | `map035/ev012/p0` |
| B5 | `map035/ev013/p0` |
| B6 | `map035/ev014/p0`, `map035/ev017/p0` — **only these two**, see below |
| B7 | `map035/ev001/p0` |
| B8 | `map035/ev001/p1` |
| B9 | `map035/ev002/p0` |
| B10 | `map035/ev003/p1` |
| B11 | `map035/ev003/p2` |
| B12 | `map035/ev009/p1` |
| B13 | `map035/ev011/p0` |
| B14 | `map035/ev012/p1` |
| B15 | *(none - encounter table, not an event page)* |

**Eight further beats**, surfaced by enumerating every event page rather than
the ones a reader thought to write down, plus one non-event beat the manifest
cannot see. These are stated in the same action/effect form as B1-B7 so they
are walkable at the boot gate rather than merely acknowledged:

| Beat | Map | Gate | Player action (test) | Expected effect (observable) |
|---|---|---|---|---|
| B8 | 35 | none | arrive on Map035 on a fresh visit, then take a second step | id 1 "EV001" pg1 autorun fires exactly once - gated on the runtime predicate `s:tsOff?("A")`, made once-per-visit by `setTempSwitchOn`. No player-visible message; it re-evaluates page conditions, so it can gate later behaviour in the same visit. Assert it does not re-fire |
| B9 | 35 | none | face (19,34) from the cave-entrance approach and press A | id 2 "EV002" shows the `\sign[sign1]` sign frame: "Old entrance to Nowtoch City." No player-visible state change - the `FLAG_MENU_ON_EVENT` (switch 185) bracket is a menu lock, not a story gate, but a switch write is a switch write, so the row cannot be dispositioned cosmetic |
| B10 | 35 | after B2, self-switch B set (and A clear) | talk to Larrie @(18,36) | id 3 pg1: "So you have returned for a rematch?..." - the phone rematch offer. Page precedence caveat: pg2 (self-switch A) outranks pg1, so this page is only reachable through the phone-rematch path that clears A |
| B11 | 35 | after B2, self-switch A set | talk to Larrie @(18,36) | id 3 pg2: "Watch your step! In caves, Pokemon can jump out from anywhere" - defeated re-talk |
| B12 | 35 | after B3, self-switch A set | walk back onto (16,42) and press A | id 9 pg1: the ball is gone and nothing happens - no second Potion. This is the one-shot assertion for B3 |
| B13 | 35 | none | talk to the Barewl @(17,36), directly west of Larrie | id 11: `pbCallBub(2)` emote bubble, then cry SE `015Cry`, then text "Bare! Bar!". Writes no state, but has three independently breakable observables |
| B14 | 35 | after B4, self-switch A set | talk to Timothy @(18,47) | id 12 pg1: "Someone tougher than me? Impossible!" - defeated re-talk, the counterpart to B11 |
| B15 | 35 | none | walk in tall grass anywhere in the corridor south of the rockslide | a wild battle starts. Species drawn from `land_mons` (Chyinmunk, Birbie, Cubbug, Barewl, Mankey, Owten), levels 3-5, encounter rate 25 (§4.3). **No manifest row** - see below |

**B15 has no manifest row, by construction.** The manifest enumerates event
pages and overland seams; an encounter table is neither, so no generated row
can ever represent it. Any beat class that is not an event page is invisible
to the approval object - the reason B15 was absent from this document until
2026-08-25. Encounter tables, connection-only seams and tileset behaviour all
have to be added to the beat list by hand.

**B12-B14 were reclassified from `cosmetic` on 2026-08-25.** The rule that had
been applied was *does this page write state?*; ev011/p0, ev012/p1 and
ev009/p1 write none and so fell out of the beat list. That rule is wrong: it
made Larrie's defeated re-talk a beat (B11, because it rides on
`pbPhoneRegisterBattle` state) while Timothy's identical-in-kind re-talk was
cosmetic. The rule is now *is there anything a player can press A on and
observe?* - `cosmetic` means decoration with no trigger, not "writes no
state". Only id 8 "Sign" @(19,33) survives as reachable-and-cosmetic on this
map: despite the name it has an empty command list and no graphic, and is not
the sign by the cave entrance (that is id 2, B9).

**B6 is two rows, not five.** The five Rock events split on reachability, and
the split changes their verdicts:

- **Rocks 14 (20,28) and 17 (19,29)** are outer boulders with an open face.
  The player can stand adjacent on visit 1 and press A. `Kernel.pbRockSmash`'s
  false branch is empty, so the observable outcome is that nothing happens —
  that is what B6 asserts. Dispositioned `deferred:rock_smash`.
- **Rocks 15 (21,29), 16 (22,28) and 18 (21,28)** are interior: BFS over the
  tileset passage bytes finds no adjacent walkable tile in the south-reachable
  region while their neighbours stand. The player cannot attempt them at all,
  so they are `unreachable:boxed_in_by_outer_rocks`, not deferrals. Recording
  them as deferred would have put three rows in the Rock Smash backlog that no
  player can reach with Rock Smash in hand until 14/17 clear first.

Everything north of the rock line — events 19–26, and the `35 N<->S 40` seam —
is `unreachable:` for this chapter and belongs to CH07.

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
| 35 | `land_mons` (rate 25) | 12-entry table: Chyinmunk, Birbie, Cubbug, Barewl, Mankey, Owten, all lv3–5 | Yes — B15, the whole grass corridor south of the gate |

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

- **Switch 22**, gating id 1 "EV001" page 1 (an autorun player-nudge before
  `setTempSwitchOn("A")`), has no name in `flag_state.json`; purpose beyond
  "skip if mid-interaction" unconfirmed. A corpus-wide switch audit would
  settle it.
- **Engine dir/porymap constant for map 35** are proposed (`Route2` /
  `MAP_ROUTE_2`) but unassigned — no naming pass has run for this map yet.

### RESOLVED

- **NE-quadrant reachability — MEASURED 2026-08-22, inference confirmed.**
  A passability grid was built from `tilesets.json["22"].passages` joined with
  Map035's tile layers, and BFS'd from the south-accessible region with the
  five Rock events solid (`through=false`). Result: every event the doc had
  called "beyond the gate" (ids 19–26) and the `35 N<->S 40` seam are
  genuinely unreachable, and the rock cluster is the only path north. §4.1 and
  §4.2's reachability column is now measured fact, not inference.
- **Rockslide contradiction — ADJUDICATED 2026-08-22.** Event 19's
  rock-clearing page is engine-ungated (no switch, variable or self-switch
  condition), which had been read as contradicting the wiki-sourced claim that
  Route 2 stays blocked until Rock Smash. Both are true: the gate is
  *geometric*, not conditional. Event 19's event-touch tile is unreachable
  from the south while the rocks stand, so the cutscene can only fire after
  the Passage Cave → Nowtoch detour brings the player back down from the
  north. CH04's gate is real and CH07's revisit stands. Closes
  `PLAYTEST_AUTHORING_IMPROVEMENT.md` §7.2.
- **Rock reachability is not uniform** — rocks 14 and 17 are attemptable on
  visit 1, rocks 15, 16 and 18 are not. See §3.1.

---

*Companion docs: `reference/chapters/00-atlas.md` (corpus-wide model and
mechanics inventory), `reference/chapters.json` (CH04/CH05/CH06/CH07 binding
records), `reference/findings/grill_chapter_atlas_2026-07-30.md` (design
record), `ROM_TEST_DEV.md` (Branch A/B decisions this document implements).*
