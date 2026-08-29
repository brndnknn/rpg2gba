# Chapter 5 — Passage Cave

**Status:** new chapter document, authored directly from the converted rxdata
per `ROM_TEST_DEV.md` Branch A (rxdata-first, wiki cross-check only). Tier
**medium** per `reference/chapters.json`. This is the spec a chapter test
scenario gets written from — it is not itself a test, and it carries no
narrative content (house style: gates and effects only, per Branch A2).
**Not yet converted or boot-walked**; §6 records expected work, not observed
defects.

**Method note:** every fact below was read from `output/uranium-build/`
(`maps/Map0{19,35,36,37,40}.json`, `map_infos.json`, `connections.json`,
`intermediate/wild_encounters.json`, `intermediate/map_metadata.json`,
`flag_state.json`, `tilesets.json`, `transpile_unhandled.jsonl`) and
`reference/chapters.json`/`00-atlas.md`, checked 2026-07-31. All totals
match `chapter_atlas census --chapter CH05` exactly. The wiki
(`output/uranium-build/wiki/Passage_Cave.wiki`) was consulted only for §5.

---

## 1. Purpose / scope

Chapter 5 is the two-map cave connecting Route 2 (CH04) to Nowtoch City
(CH06) — the first interior dungeon in the game. `chapters.json` tier-
promotes it to medium for that novelty alone ("first dungeon; first
candidate for cave/Flash handling"), despite the smallest map roster of any
A1 chapter (2 maps, 16 events, 142 commands). CH04's notes record a direct
Route 2↔Nowtoch seam (`connections.json`: `35 N<->S 40`) that the wiki gates
behind Rock Smash — on a first pass this cave is the only way through, a
forced connector, not an optional route.

Map roster source of truth: `reference/chapters.json` CH05 (`"maps": [36,
37]`). Mechanically: enter from Route 2, cross Map036 (2 trainer battles, 4
item balls, wild grass), warp into Map037 (1 trainer battle, 1 NPC item,
wild grass, four diagonal-staircase "Stairs" events that are mandatory
for the exit — §3), exit into Nowtoch City. No
story variable advances anywhere in this chapter — §3.

## 2. Map inventory

| RMXP id | Uranium identity (`map_infos.json`) | Engine dir | porymap constant | Role in chapter |
|---|---|---|---|---|
| 36 | Passage Cave (`parent_id:55`, `dark_map:true`) | `PassageCave` (proposed, §7) | `MAP_PASSAGE_CAVE` (proposed) | Entry hall; 4 item balls, 2 trainer battles, warp to Route 2 (CH04) and Map037 |
| 37 | Passage Cave (`parent_id:36`, `dark_map:true`) | `PassageCave2` (proposed, §7) | `MAP_PASSAGE_CAVE_2` (proposed) | Back hall; 1 trainer battle, 1 NPC item, warp to Map036, exit to Nowtoch (CH06) |

**Wiring.** Map036 is the chapter's outdoor-equivalent parent
(`"outdoor":36`); Map037 is its RMXP child. No `connections.json` seam
touches either — the chapter is pure warp, matching `00-atlas.md` §5's
"cave entry/exit — native." Four legs, each one `code 201` (2 per map,
§4.4): **35→36** Map035 EV001 `pbCaveEntrance` → Map036 (17,39)
(`Map035.json:7285-7301`); **36→35** Map036 EV001 (17,40) `pbCaveExit` →
Map035 (20,33) (`Map036.json:5395-5411`); **36→37** Map036 EV002 page 0
(17,4) → Map037 (16,26) (`:5513-5522`; page 1, switch 22 = runtime
predicate `s:tsOff?("A")`, is the arrival-nudge idiom, §7); **37→36**
Map037 EV001 (16,27) → Map036 (17,4), dir 0 = retain
(`Map037.json:3163-3172`; the earlier "dir=4" reading was wrong — the
`code 201` parameter layout is `[?, map, x, y, dir, fade]`); **37→40**
Map037 EV002 (16,5) `pbCaveExit` → Map040 Nowtoch (68,43)
(`:3288-3304`), the boundary to CH06. Map040 also warps back to Map037
(16,6), twice — a source/arrival pair (`Map040.json:25229`,`:25405`).
**Map019** (also "Passage Cave") warps only to/from Map031 Kevlar Town
(`Map019.json:5588`) and is **excluded** — §5 #1.

## 3. Story beat chain

`VAR_QUEST_LOG` and every other RMXP variable are **untouched**: `code 122`
appears zero times in either map — no quest-log advance here, no state
spine invented. The only writes are **4 `code 121` switch writes**, all
inside Map037 EV005 (the item-granting NPC), all to switch 185
(`FLAG_MENU_ON_EVENT`, `flag_state.json:151`), bracketing that NPC's
dialogue on both pages:

```
FLAG_MENU_ON_EVENT  off ──[Map037 EV005, talk]──► on   (bracket dialogue + item grant)
FLAG_MENU_ON_EVENT  on  ──[Map037 EV005, same tail]──► off
```

A scratch/mutex flag for one interaction, not persistent state — reused
nowhere else. With no variable spine, the table below is the traversal plus
the self-switch-gated (once-only) pickups/battles along it.

| Beat | Map | Gate | Player action (test) | Expected effect (observable) |
|---|---|---|---|---|
| B1 | 35→36 | — | enter cave from Route 2 | `pbCaveEntrance`, warp to Map036 (17,39) |
| B2 | 36 | self-switch A off | walk to (10,35) | EV003: `pbItemBall(ESCAPEROPE)` (`Map036.json:5765-5771`); self-switch A set |
| B3 | 36 | event sight | approach Trainer(5) (18,29) | `pbTrainerBattle(HIKER,"Manny")` (`:6008-6014`); self-switch A after |
| B4 | 36 | none | walk to (22,7) | EV005: `pbItemBall(GREATBALL)` (`:6196-6201`) |
| B5 | 36 | event sight | approach Trainer(3) (6,13) | `pbTrainerBattle(BLACKBELT,"Keichi")` (`:6438-6444`) |
| ~~B6~~ | 36 | **blocked: Surf** | — | EV008 `pbItemBall(TM76)` (`:6626-6631`) sits in a sealed room; **deferred beat**, §7 |
| ~~B7~~ | 36 | **blocked: Surf** | — | EV009 `pbItemBall(SABLEYEITE)`, a Mega Stone (`:6782-6787`); same sealed room, **deferred beat**, §7 |
| B8 | 36→37 | player-touch | walk onto (17,4) | warp to Map037 (16,26) |
| B9 | 37 | event sight | approach Trainer(3) (24,10) | `pbTrainerBattle(HIKER,"Nuñes")` (`Map037.json:3701-3707`) |
| B10 | 37 | none | talk to EV005 (8,7) | flag on → `pbReceiveItem(REVIVE)` (`:3973-3979`) → flag off; self-switch A after |
| B11 | 37→40 | player-touch | walk onto (16,5) | `pbCaveExit`, warp to Map040 (68,43) — boundary to CH06 |

Four Map037 events (ids 3,6,7,8, all "Stairs") write no state, so they
carry no beat in the table above — but they are **not** inert, and the
2026-08-28 CH05 dry-run corrects this document on that point
(`PLAYTEST_AUTHORING_IMPROVEMENT_V2.md` §5.2/§5.9). Each is the diagonal-
staircase idiom already met on Map033: a player-touch, `through=false`
event whose `code 111` character-direction branch reads the player's
facing and force-moves them one tile **diagonally** (ev3/ev6 at (20,10)/
(20,9), move codes 6/7 = NW/SE axis; ev7/ev8 at (11,10)/(11,9), codes 5/8
= NE/SW). `tileset_converter/stairs.py` already classifies all four, so
they convert to native `MB_SIDEWAYS_STAIRS_RIGHT_SIDE` / `_LEFT_SIDE`
metatile behaviours — no object event and no script reach the ROM.
**They are mandatory traversal:** a BFS over Map037's real walkability
makes the cave exit (16,5) UNREACHABLE from the arrival cell with the
four cells blocked (the trainer and the gift both keep stair-free paths).
Any beat reaching the CH06 boundary crosses one.

## 4. Coverage targets

Enumerated from the converted data. This chapter is small enough that every
table below is exhaustive, not a sample.

### 4.1 Trainer battles — all 3 (`trainer_battles=3`)

| Map | Event | Trigger | In-chapter reachable? | Notes |
|---|---|---|---|---|
| 36 | Trainer(5) "Manny" (HIKER) | event sight, `code 111` type-12 `pbTrainerBattle` | Yes (B3) | not repeatable after |
| 36 | Trainer(3) "Keichi" (BLACKBELT) | event sight | Yes (B5) | same pattern |
| 37 | Trainer(3) "Nuñes" (HIKER) | event sight | Yes (B9) | same pattern |

No `code 301` exists in either map; no other trainer events exist in the
2-map roster. `[auto]`

### 4.2 Item balls / given items — all 5 (`item_grants=5`)

| Map | Item | Event | Gate | In-chapter? |
|---|---|---|---|---|
| 36 | Escape Rope | EV003 p0 | first-pickup self-switch only | Yes (B2) |
| 36 | Great Ball | EV005 p0 | same | Yes (B4) |
| 36 | TM76 (Stealth Rock) | EV008 p0 | same | **No — `blocked:surf`**, §7 |
| 36 | Sableyeite (Mega Stone) | EV009 p0 | same | **No — `blocked:surf`**, §7 |
| 37 | Revive | EV005 p0 (NPC talk) | `pbReceiveItem` inside flag bracket | Yes (B10) |

No `switch 125`-style postgame gate exists — zero `code 122` writes, and all
4 `code 121` writes are already covered in §3. `[auto]`

### 4.3 Wild encounters — both tables (`enc[land_mons]` ×2)

| Map | Table | Contents | In-chapter reachable? |
|---|---|---|---|
| 36 | `land_mons` (rate 15) | 12-entry: Tonemy×2, Barewl×3, Grozard×3, Dunsparce×4, lv 4–6 | Yes |
| 37 | `land_mons` (rate 20) | identical spread, rate 20 | Yes |

No `water_mons`/`fishing_mons`/`cave`/`headbutt_*` keys exist for either
map — one table each, neither rod- nor item-gated. `[auto]`

### 4.4 Warps — all 4 chapter-relevant legs

| Map | Warp | Destination | Chapter-relevant? |
|---|---|---|---|
| 36 | EV001 (17,40) | Map035 Route 2 (20,33) | Yes — boundary to CH04 |
| 36 | EV002 p0 (17,4) | Map037 (16,26) | Yes — internal crossing |
| 37 | EV001 (16,27) | Map036 (17,4) | Yes — internal crossing |
| 37 | EV002 (16,5) | Map040 Nowtoch (68,43) | Yes — boundary to CH06 |

`code 201` per map: Map036=2, Map037=2, equal to logical-warp count exactly
— no arrival-pair duplication *within* this chapter (that's on Map040's
side). Map019 has one warp, to Map031 Kevlar (`Map019.json:5588`) —
excluded, §5 #1. `[auto]`

## 5. Wiki vs rxdata discrepancies

Checked against `output/uranium-build/wiki/Passage_Cave.wiki`:

1. **Wiki describes one location, three rooms**: "Room 1 (Route 2 Side)",
   "Room 2 (Nowtoch City Side)", "Grott-Hole (Kevlar Town)" (post-HM04
   Strength). Rxdata: Room 1/2 are Map036/037 (this chapter); Grott-Hole is
   Map019, warp-isolated to Kevlar with **no** link to 36/37
   (`Map019.json:5588`). Matches/corroborates `00-atlas.md` §6 disagreement
   #4. Map019 is bound to **CH03**, not this chapter.
2. **No disagreement on darkness.** Wiki: "very dark ... small sphere of
   light." Data: `map_metadata.json` marks both maps `"dark_map": true`
   (lines 284, 292). Recorded as corroboration for §6, not conflict.
3. **Items, trainers, species all match 1:1** — wiki's Room 1/2 items and
   trainers (Manny, Keichi, "Nuñez"/data "Nuñes") match §4.1/§4.2; catch
   table (Tonemy/Barewl/Grozard/Dunsparce, lv 4–6) matches §4.3.
4. **Grott-Hole's HM04 Strength gate sits oddly against Map019's CH03/A1
   binding** — Strength arrives much later in the act chain. Concerns
   Map019/CH03, not this chapter; **not resolved here** — §7.

## 6. Expected conversion work and risks

**Mechanics binding** (verdicts owned by
`reference/guides/command_pokeemerald_map.md`):

| Mechanic | First here? | Disposition | Ledger row |
|---|---|---|---|
| cave entry/exit | **Yes** — first dungeon | native, WIRE, **no new C** | `:130` `pbCaveEntrance`/`pbCaveExit` → cave-darkness flag + `EventScript_UseFlash` |
| item ball | No (CH01/02 already) | native | classifier 8, `giveitem` |
| item grant | No | native | `pbReceiveItem` → `giveitem` |
| trainer battle | No (CH01 has 1) | native | hidden in `code 111` type-12, corpus-wide |
| trainer sight | No (CH02 already dense) | native | `pbNoticePlayer` |
| wild encounters | No (CH01 has `land_mons`) | native | day/night gap generic |

Both maps `"dark_map": true` (`map_metadata.json:284,292`) — first exercise
of the native cave-darkness/Flash path. No engine search found any
indication custom C is needed here.

**Unmapped script heads** (`get_character`, `pbCallBub`,
`setTempSwitchOn`):

| Head | Assessment |
|---|---|
| `get_character` | RGSS accessor (`scripts_dump/041_Interpreter.rb:536`), returns `Game_Character` by relative id (−1=player,0=this event,N=event N); no effect alone — feeds `pbNoticePlayer` and a compiler `.onEvent?` idiom (Map036 EV002 p1); not a converter gap |
| `pbCallBub` | STRIP (`:154`) — cosmetic emote bubble before trainer dialogue |
| `setTempSwitchOn` | DET (`:113`) — classifier candidate; one script-form use (Map036 EV002 p1 tail), distinct from §3's raw `code 121` writes |

**Known risks / gaps:** conversion-readiness is **unmeasured** (neither map
is in the slice-1 staged set; `unhandled` is `null`, and zero
`transpile_unhandled.jsonl` entries means "never staged," not "clean");
TM76/Sableyeite reachability without Surf is unconfirmed (§7, affects
B6/B7); the four "Stairs" events and Map036 EV002 page 1 have no
discernible function pending a boot-walk (§7); `PassageCave`/`PassageCave2`
names are proposed only, no `engine/data/maps/` entry exists yet; the
Sableyeite grant here sits oddly against `00-atlas.md`'s "first Mega Stone"
credit to CH40 (flagged for the atlas maintainer, §7).

## 7. Open items for the lead

### 7.1 Decisions owed before this chapter builds

These were deliberately deferred by the operator on 2026-08-29 and pulled
out of `MEMORY.md`'s Open Questions and `PROJECT_TODO.md`'s Open section —
they are **not** open questions on current work, since nothing upstream of
CH05 depends on them. This document is their single live home; they are
settled here when the CH05 branch opens.

1. **Cave darkness / Flash — a CLAUDE.md §10 content-fidelity call.** Maps
   36 and 37 are both `DarkMap: true` (`intermediate/metadata_raw.json`
   field 9; 26 maps corpus-wide). `pbs_converter/metadata.py:114` parses
   `dark_map` and nothing downstream reads it —
   `tileset_converter/metadata_wiring.py:602` hardcodes
   `"requires_flash": False`, a §4.5 silent default, so this chapter —
   which `chapters.json` tier-promoted *for* being the first cave/Flash
   candidate — currently converts fully lit. Wiring `requires_flash: true`
   is **not** the fix: HM05 has no grant site anywhere in the 199-map
   corpus, and Uranium's own `CanUseMove(:FLASH)`
   (`scripts_dump/103__PField_HiddenMoves.rb:1161-1176`) additionally
   requires `BADGEFORFLASH` — so a `true` header yields a cave the player
   can never light. At least three options: render darkness and grant
   Flash from somewhere; render it and accept an unlightable cave; or
   strip darkness corpus-wide and record the decision. This **retro-
   applies to map 19 (Grott-Hole)**, which is also `DarkMap` and already
   shipped as a lit room through CH03's §9 boot-walk gate, unremarked.
   `DarkMap` is a *map property* — a capability surface that is neither a
   page, a seam, nor a terrain tag, and therefore invisible to the
   manifest. (`PLAYTEST_AUTHORING_IMPROVEMENT_V2.md` §5.3.)
2. **The engine map names for 36 and 37.** Both are named "Passage Cave"
   in `map_infos.json`, so `MapConstantRegistry.mint` fails loud (`map 37
   ('Passage Cave') -> MAP_PASSAGE_CAVE collides with already-minted map
   36`) and `reference/map_name_overrides.json` currently records both as
   `"CORRECT — no override"`. §2 of this document proposes `PassageCave` /
   `PassageCave2`; map 19 set the precedent, disambiguated to "Passage
   Cave Grott-Hole" on the same grounds. The names themselves are
   unconfirmed — no `engine/data/maps/` entry exists for either. This is a
   naming decision plus two `overrides` entries with evidence; the
   fail-loud is working as designed and only the data is missing.
   (`PLAYTEST_AUTHORING_IMPROVEMENT_V2.md` §5.5.)
3. **The two unresolved cross-references**, carried forward from §7.3
   below because they also want an operator call, not just a note: (a)
   Sableyeite here versus `00-atlas.md` crediting CH40 with the "first
   Mega Stone" — needs the atlas maintainer to confirm which credit is
   right, or to record that both are genuine Mega Stones and the atlas
   phrasing should change; (b) Grott-Hole's HM04 Strength gate against map
   19's CH03/A1 binding — needs someone to check the corpus-wide HM
   availability order against map 19's act placement and either confirm
   the ordering is fine as designed or flag it as a sequencing defect
   for CH03.

### 7.2 Build prerequisites this chapter carries

Work the CH05 build inherits, not open questions:

- **B6/B7 become deferred beats** owed to a Surf revisit (Map143, Act 5),
  since TM76 and Sableyeite sit in a Surf-sealed 30-tile room (§7.3,
  RESOLVED entry below).
- The **arrival-nudge autorun** archetype (`map036/ev002/p1`;
  byte-identical fingerprint to CH04's `map035/ev001/p1`, which carries
  `beat:B8`; 324 instances across 73 maps) is missing from the Tier-1
  template build set and CH05 needs it authored.
  (`PLAYTEST_AUTHORING_IMPROVEMENT_V2.md` §5.6.)
- Two mechanical fail-loud repairs land with this chapter: the
  `unhandled: 0`-versus-null distinction, and `requires_flash` reading its
  parsed metadata instead of the hardcoded literal. Both are tracked in
  `PROJECT_TODO.md` (#54 and #56) in a section parked against this branch.
- Standing guardrail: **a green CH05 §9 boot-walk gate is not evidence**
  that slice 2, the capability model, or the mart/Poké Center/PC templates
  are correct — CH05 measures zero exposure to all three
  (`PLAYTEST_AUTHORING_IMPROVEMENT_V2.md` §5.8).
- The decided-but-unbuilt **re-disposition of the whole built corpus**
  during CH05's build, with its ordering safeguard: freeze the expected
  answers first, then derive, then diff, then write.
- **Route-planning ordering is now satisfied, not owed.** The dry run
  flagged a build-ordering hazard: landing the `_route_waypoints`
  fail-loud before slice 1's stair model would make every stair-crossing
  leg on Map037 raise, since a leg reachable only across a sideways
  staircase is unroutable by the 4-neighbour planner
  (`PLAYTEST_AUTHORING_IMPROVEMENT_V2.md` §5.9). Slice 1 landed in commits
  `f780a972`..`46bd2efe` and the fail-loud landed after it in `f705b642`,
  all on 2026-08-28 — so the graph and the fail-loud are both in place and
  the chapter is routable. No action needed here.

### 7.3 Loose ends and resolved notes

- **~~TM76/Sableyeite reachability without Surf.~~ RESOLVED 2026-08-28 —
  they need Surf; they are NOT collectible in CH05.** The tile stack under
  both coordinates is dry floor, which is why the earlier read was
  inconclusive — but connectivity settles it. A BFS over Map036's real
  walkability (repo's own `layout.column_blocked` against
  `tilesets.json["32"]`) finds **513 walkable tiles in 7 components, 450
  reachable on foot from the entrance (17,39)**, and both items sit inside
  a **sealed 30-tile room**, bbox x 31-36 / y 11-16: ordinary wall (terrain
  tag 0) north, east and west, and its one southern opening drops into a
  **water pocket (terrain tag 7, `isSurfable?`)** that is itself
  disconnected from the walkable region. Every other target is reachable —
  Escape Rope d=11, Manny d=15, Keichi d=49, Great Ball d=65, the Map037
  warp d=63. **B6 and B7 therefore become deferred beats owed to the Surf
  revisit (Map143, Act 5)**, in the `DEFERRED_BEATS` idiom CH02/CH04 use —
  not live beats. Wiki §5 #3 was right.
- **~~Two sets of inert events, purpose unclear.~~ RESOLVED 2026-08-28 by
  the CH05 dry-run — neither set is inert.** The four "Stairs" events on
  Map037 are forced diagonal moves and are mandatory for the exit (§3).
  Map036 EV002 page 1 (switch 22 `s:tsOff?("A")`, autorun) is the
  **arrival-nudge** idiom: `get_character(0).onEvent?` -> go transparent ->
  step the player one tile off the arrival cell -> `setTempSwitchOn("A")`.
  Its fingerprint is byte-identical to CH04's `map035/ev001/p1` (which
  carries `beat:B8`), and the idiom occurs **324 times across 73 maps** —
  a corpus archetype, not a template left behind
  (`PLAYTEST_AUTHORING_IMPROVEMENT_V2.md` §5.6).
- **Two cross-references flagged but not resolved in this document**:
  Sableyeite vs `00-atlas.md`'s "first Mega Stone" credit to CH40 (§6), and
  Grott-Hole's HM04 Strength gate vs Map019's CH03/A1 binding (§5 #4,
  Map019 out of scope here). Promoted to operator decisions in §7.1 #3
  above; kept here as the evidence trail.

---

*Companion docs: `reference/chapters/00-atlas.md` (corpus-wide model and
mechanics inventory this document binds against), `reference/chapters/
01-moki.md` (the structural sibling this document's tables and register
follow), `reference/chapters.json` (CH03/CH04/CH05 binding records),
`reference/guides/command_pokeemerald_map.md` (the capability ledger §6
points at), `ROM_TEST_DEV.md` (harness design and the Branch A/B/G
decisions this document implements).*
