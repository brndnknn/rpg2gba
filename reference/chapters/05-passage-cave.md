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
wild grass, four inert "Stairs" events — §7), exit into Nowtoch City. No
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
predicate `s:tsOff?("A")`, is an inert one-time turn idiom, §7); **37→36**
Map037 EV001 (16,27) → Map036 (17,4) (`Map037.json:3163-3172`); **37→40**
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
| B6 | 36 | none | walk to (31,15) | EV008: `pbItemBall(TM76)` (`:6626-6631`); Surf-reachability unconfirmed, §7 |
| B7 | 36 | none | walk to (34,12) | EV009: `pbItemBall(SABLEYEITE)`, a Mega Stone (`:6782-6787`); same §7 caveat |
| B8 | 36→37 | player-touch | walk onto (17,4) | warp to Map037 (16,26) |
| B9 | 37 | event sight | approach Trainer(3) (24,10) | `pbTrainerBattle(HIKER,"Nuñes")` (`Map037.json:3701-3707`) |
| B10 | 37 | none | talk to EV005 (8,7) | flag on → `pbReceiveItem(REVIVE)` (`:3973-3979`) → flag off; self-switch A after |
| B11 | 37→40 | player-touch | walk onto (16,5) | `pbCaveExit`, warp to Map040 (68,43) — boundary to CH06 |

Four Map037 events (ids 3,6,7,8, all "Stairs") are omitted: each is a
player-touch trigger with only a turn-in-place move route — no text,
switch, variable, or item command anywhere. They gate and observe
nothing — §7.

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
| 36 | TM76 (Stealth Rock) | EV008 p0 | same | Yes (B6) — path untraced, §7 |
| 36 | Sableyeite (Mega Stone) | EV009 p0 | same | Yes (B7) — path untraced, §7 |
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

- **TM76/Sableyeite reachability without Surf.** Tile stack under both
  coordinates is dry floor (Map036 layer0=2617 at (31,15), 2678 at (34,12);
  layers 1/2 both `0`; no autotile/pond id in range 0–335 touches either
  spot). Wiki (§5 #3) implies reaching them needs Surf, and path
  connectivity from the entrance was not traced. Surf isn't granted until
  Act 5 (CH30) — needs a boot-walk/connectivity check before assuming
  B6/B7 collectible here.
- **`PassageCave`/`PassageCave2` naming unconfirmed** — no
  `engine/data/maps/` entry exists for either map.
- **Two sets of inert events, purpose unclear.** Map036 EV002 page 1
  (switch 22 `s:tsOff?("A")`, autorun; silent turn + temp-switch set, no
  dialogue/item/state change found) and the four "Stairs" events on Map037
  (ids 3,6,7,8; turn-in-place only) both look like inert templates. Flag
  both for an eye-check once art exists.
- **Two cross-references flagged but not resolved in this document**:
  Sableyeite vs `00-atlas.md`'s "first Mega Stone" credit to CH40 (§6), and
  Grott-Hole's HM04 Strength gate vs Map019's CH03/A1 binding (§5 #4,
  Map019 out of scope here).

---

*Companion docs: `reference/chapters/00-atlas.md` (corpus-wide model and
mechanics inventory this document binds against), `reference/chapters/
01-moki.md` (the structural sibling this document's tables and register
follow), `reference/chapters.json` (CH03/CH04/CH05 binding records),
`reference/guides/command_pokeemerald_map.md` (the capability ledger §6
points at), `ROM_TEST_DEV.md` (harness design and the Branch A/B/G
decisions this document implements).*
