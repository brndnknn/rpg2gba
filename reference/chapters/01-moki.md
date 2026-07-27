# Chapter 1 — Moki Town

**Status:** draft chapter document, promoted from
`reference/findings/moki_slice_story_chain_2026-07-16.md` per `ROM_TEST_DEV.md`
Branch A (rxdata-first, wiki cross-check only) and the 2026-07-23 "Response to
your answers" build order (item 2). This is the spec a chapter test scenario
gets written from — it is not itself a test, and it carries no narrative
content (house style: gates and effects only, per Branch A2).

**Method note:** every beat, gate, item grant, encounter table, and warp below
was read directly out of `output/uranium-build/maps/Map0{32,48,49,50,64,65,89,172}.json`,
`output/uranium-build/intermediate/wild_encounters.json`,
`output/uranium-build/flag_state.json`, and `output/uranium-build/transpile_unhandled.jsonl`
(all fresh-run artifacts, checked 2026-07-23). The Uranium wiki was consulted
only for the cross-check section below (WebSearch snippets — direct fandom.com
fetch returns HTTP 402 in this environment) and is explicitly **not** load-bearing
anywhere else in this document.

---

## 1. Purpose / scope

Chapter 1 ≡ slice 1 (Branch B1: chapter boundaries follow slice boundaries
until they provably diverge). Source of truth for the map roster:
`src/rpg2gba/tileset_converter/map_set.py:30`, `SLICE_MAP_IDS = [49, 48, 32, 50, 64, 65, 172, 89]`
— **8 maps**, confirmed unchanged since the 2026-07-16 predecessor doc.

The chapter covers: waking up in the player's house, the Auntie running-shoes
gate, the Theo cameo trip tile, the lab visit (Bamb'o intro → aptitude test →
starter pickup → Theo's tutorial battle), the Theo's-house PokéPod scene, and
the Pokédex/catch-tutorial ceremony at the west exit of town — i.e. everything
up to but not including the walk out onto Route 01.

## 2. Map inventory

| RMXP id | Uranium identity (`map_infos.json`) | Engine dir | porymap constant | Role in chapter |
|---|---|---|---|---|
| 49 | Player's House 1F (spawn @7,7) | `MokiTownPlayersHouse1F` | `MAP_MOKI_TOWN_PLAYERS_HOUSE_1F` | Start; Auntie gate |
| 48 | Player's House 2F | `MokiTownPlayersHouse2F` | `MAP_MOKI_TOWN_PLAYERS_HOUSE_2F` | Wake-up room, PC, region map |
| 32 | Moki Town (outdoors) | `MokiTown` | `MAP_MOKI_TOWN` | Hub; Theo trip tile, Granny, rocks, ceremony |
| 50 | Professor Bamb'o's Lab | `MokiTownProfessorLab` | `MAP_MOKI_TOWN_PROFESSOR_LAB` | Intro, aptitude test, starter, Theo battle |
| 65 | Unnamed house 1 (door @32:24,42) | `MokiTownHouse1` | `MAP_MOKI_TOWN_HOUSE_1` | Flavor interior, no chain beats |
| 64 | Unnamed house 2 (door @32:43,31) | `MokiTownHouse2` | `MAP_MOKI_TOWN_HOUSE_2` | Flavor interior, no chain beats |
| 172 | Theo's House 1F (door @32:56,42) | `MokiTownTheo172` | `MAP_MOKI_TOWN_THEO_172` | PokéPod scene |
| 89 | Theo's House 2F (via 172 stairs) | `MokiTownTheo` | `MAP_MOKI_TOWN_THEO` | Flavor interior, no chain beats |

Wiring: `engine/data/maps/groups.inc:592-599`, `connections.inc:523-530`. Parent
map relationships (`map_infos.json` `parent_id`) confirm 48→49→32 as the
outdoor exit chain and 89→172→32 as Theo's house.

## 3. Story beat chain

`VAR_QUEST_LOG` (registry name for RMXP variable 101, `flag_state.json:254`) is
the only state machine spanning the chapter. Confirmed writes, in order:

```
0 ──[Map050 EV019 "Machine": +1]──► 1 ──[Map172 EV004 "Theo" autorun: =2]──► 2 ──[Map032 EV009 page 2: =4]──► 4
```

No other write to `VAR_QUEST_LOG` exists anywhere in the 8 maps (confirmed by
grepping each map's command list for `code 122` operating on variable 101).
`>=5` is read by Map050 EV005 pages 5/6 but never written in-chapter — that
increment is out of scope (post-chapter content living on the same physical
maps, see §6).

### 3.1 Positive beats

| Beat | Map | Gate | Player action (test) | Expected effect (observable) |
|---|---|---|---|---|
| B1 | 48 | new game | none — arrival state | Player spawns in Map049 (per B1 boot check), not Map048; potion/starting-inventory claim **unverified this pass**, see §7 |
| B2 | 49 | none | leave 1F without talking to Auntie | **Blocked** — player cannot pass the exit tile; no state change (mechanical redirect, not a story beat but the chapter's first gate) |
| B3 | 49 | talk to Auntie (event 1, "Auntie") | interact | `FLAG_SYS_B_DASH` set (native Emerald run flag; RMXP source: `$PokemonGlobal.runningShoes=true`); `FLAG_MAP049_EVENT001_SSA` set (gift-once self-switch, `flag_state.json:322`) — re-talking advances to later dialogue, no repeat grant |
| B4 | 32 | walk the fence row at column 26, near (26,12) | walk through the coord-touch trigger tile | Map032 EV074 fires once ("Theo runs up"); `FLAG_MAP032_EVENT074_SSA` set (`flag_state.json:314`) — never refires |
| B5 | 50 | enter the lab (any `VAR_QUEST_LOG` value < required for later pages) | walk in | Map050 EV005 "Bambo" page-0 autorun scene fires immediately on entry (BOOT_WALK S3, passed) |
| B6 | 50 | scene from B5 completes | none (scripted) | Aptitude-test Yes/No prompt (EV005 page 2, gated `self_switch D` set by the page-0 autorun) |
| B7 | 50 | answer Yes | menu choice | 4-question quiz plays; answering No returns to the offer (BOOT_WALK S5, passed) and can be retaken |
| B8 | 50 | quiz resolves | pick up the starter from "Machine" (event 19) | `VAR_QUEST_LOG` 0→1 (Map050 EV019 page 0, `code 122` set) — the lab's **only** quest-log write; starter species named + placed in party |
| B9 | 50 | `VAR_QUEST_LOG >= 1` | talk to Theo (event 20) | `pbTrainerBattle(PBTrainers::RIVAL, "Theo", …)` fires (Map050.json:9009) — a real, losable trainer battle; win or lose, party auto-heals after and Theo leaves the lab (BOOT_WALK S6b, passed) |
| B10 | 50 → 32 | `VAR_QUEST_LOG >= 1` | exit the lab | Lab exit warp (EV001 page 1) only unlocks at this gate |
| B11 | 32 → 172 | `VAR_QUEST_LOG >= 1` | enter Theo's house | door always open; the gate that matters is what's *inside* |
| B12 | 172 | `VAR_QUEST_LOG >= 1` | enter 1F | Map172 EV004 "Theo" autorun (PokéPod scene) fires; ends with `VAR_QUEST_LOG` 1→2 (hard set); `FLAG_MAP172_EVENT004_SSA` set (fired-once) |
| B13 | 32 | `VAR_QUEST_LOG >= 2`, cross the west-exit path tiles (relocated to (17,42)/(16,43) per the S8 fix note — **discrepancy, 2026-07-24:** live `Map032.json` event 9 puts the coordinate-touch tile at **(16,42)**, not (16,43); the scenario approaches via (17,42) and steps west onto the data-confirmed (16,42). Both readings agree on the crossing direction. Resolve against current map data before trusting the doc value) | walk the trigger tiles | Map032 EV009 page 2 ceremony fires: choreographed capture demo, ends with `VAR_QUEST_LOG` 2→4 (`code 122` at Map032.json's EV009 page-2 tail — confirmed `[101, 101, 0, 0, 4]`, i.e. **`VAR_QUEST_LOG`**, not the old wrong-var bug, see §6) |
| B14 | 32 | `VAR_QUEST_LOG >= 4` | re-enter the ceremony trigger tiles | scene does not refire (page 3 is the post-ceremony no-op page, gated `==4`) |
| B15 | 32 → Route 01 | — | walk west | out of chapter scope |

### 3.2 Negative beats (mandatory per ROM_TEST_DEV Branch B2)

Every gate above with a data-confirmed refusal/redirect page gets a companion
negative beat.

| Beat | Map | Violation tested | Assert refusal fires | Assert no state advanced |
|---|---|---|---|---|
| N1 | 49 | ~~Try to leave 1F before talking to Auntie (companion to B2)~~ | **SUPERSEDED 2026-07-27 — not implemented.** B2 already tests this exact gate with this exact assertion set; N1 was written as a second identical call to the same helper and could not fail unless B2 failed first. Dropped from the harness (`chapters/moki.py`, `tests/test_moki_chapter.py::DROPPED_DOC_BEATS`). | — |
| N2 | 32 | Skip Theo's house: after B8 (`VAR_QUEST_LOG==1`), walk straight to the west-exit ceremony trigger tiles before entering Map172 | Map032 EV009 **page 1** fires (gated exactly `VAR_QUEST_LOG==1`) — the professor's "go get Theo" redirect line, then the player is turned back toward town, **no ceremony plays** | **`VAR_QUEST_LOG` is unchanged (stays 1).** Confirmed directly from the command list of EV009 page 1 (`Map032.json`): the page contains a sign-check branch, one `pbCallBub` emote call, one dialogue line, and a player turn-back move route — **zero `code 122` (control-variable) commands anywhere in the page.** This answers the motivating question from ROM_TEST_DEV Branch B2 explicitly: **the pre-Theo redirect does not write any variable.** The only way `VAR_QUEST_LOG` advances past 1 is the real PokéPod scene in Map172 (B12). |
| N3 | 50 | Talk to the aptitude-test offer and answer No (companion to B7) | scene ends cleanly, professor re-offers on next talk (BOOT_WALK S5 already passed) | quiz is not scored; no starter granted; `VAR_QUEST_LOG` stays 0 |

**N2 is the one to build first** — it is exactly the case named in
`ROM_TEST_DEV.md` ("if you try to skip Theo's house and go straight to the catch
tutorial, the professor tells you to go get theo") and it is now answered from
the data rather than from suspicion, per the B2 resolution: *"derive the
permutations from the event data rather than from suspicion."*

## 4. Coverage targets

Enumerated from the converted map/intermediate data, not the wiki (Branch B2/C2
requirement). This is the checklist a chapter-1 test scenario should be checked
against for completeness.

### 4.1 Trainer battles

| Map | Event | Trigger | In-chapter reachable? | Notes |
|---|---|---|---|---|
| 50 | "Theo" (event 20) | talk, gated `VAR_QUEST_LOG>=1` | Yes (B9) | Only trainer battle anywhere in the 8-map roster (`grep code:301` across all 8 maps returns zero — the battle is a scripted `pbTrainerBattle` call, not the raw RGSS battle-processing command) |

No other trainer events exist in Moki Town or its interiors. `[auto]`

### 4.2 Item balls / given items

| Map | Item | Event | Gate | In-chapter? |
|---|---|---|---|---|
| 32 | 5× Poké Ball | EV009 "Trainer(6)" page 2 | `VAR_QUEST_LOG>=2` | Yes — part of B13 |
| 32 | Rare Candy | EV027 page 0 | ungated (default page) | Yes — Granny giveaway (BOOT_WALK M6) |
| 32 | 10× Poké Ball | EV009 page 2 | same event as above | duplicate row — same grant already covered |
| 49 | Lava Cookie | EV018 "Post Cutscene" | `switch 125 == true` ("FINAL EVENT") | **No** — postgame only |
| 50 | Poké Radar | EV022 "Postgame Cutscene" | `switch 125 == true` | **No** — postgame only |
| 172 | HM07 | EV004 "Theo" page 2 | `switch 125 == true` | **No** — postgame only |

Confirmed by reading each grant's page `condition` object directly. The three
postgame grants sit on the same physical maps as chapter-1 content but gate on
switch 125, the same "FINAL EVENT" switch already ruled out for Map032
EV078/EV080 in the predecessor doc — consistent with the corpus pattern of
reusing early maps for late-game revisits. **These three are out of chapter-1
scope; do not test them here.** `[auto]`

Starting-inventory claim (predecessor doc's "PC holds a free Potion" at B1):
**not found** in `Map048.json`/`Map049.json` (no `code 126` item-change command,
no `pbReceiveItem` call) or in `system.json`. If real, it lives in a
Trainer/party-default config not covered by this pass — flagged as an open
item in §7, not asserted as a beat.

### 4.3 Wild encounters

| Map | Table | Contents | In-chapter reachable? |
|---|---|---|---|
| 32 | `land_mons` (rate 5) | 12-entry Chyinmunk table, levels 2–6 | Yes — the only grass-encounter map in the chapter |
| 32 | `fishing_mons.old_rod` | Fartog lv5–6 | **No** — no rod is obtainable in chapter 1 |
| 32 | `fishing_mons.good_rod` | Magikarp/Fartog | **No** — same reason |
| 32 | `fishing_mons.super_rod` | Magikarp/Fartog/Blubelrog | **No** — same reason |

No `water_mons`, `cave`, `headbutt_*`, or `bug_contest` tables exist for
Map032 or any of the 7 interiors (`wild_encounters.json` has no entries for
maps 48/49/50/64/65/89/172 at all — interiors carry no encounter table, which
is faithful). Per ROM_TEST_DEV §0/C2: golden test covers table contents for
all of these with no emulator; the one live-wiring check for chapter 1 is a
single walk-into-grass on Map032 asserting a Chyinmunk encounter fires. `[auto]`
(table contents) `[auto]` (live grass wiring, once the harness's battle
mini-driver lands) — fishing rows stay untested this chapter (item gate,
see above).

### 4.4 Warps

| Map | Warp | Destination | Chapter-relevant? |
|---|---|---|---|
| 49 | Stairs | Map048 | Yes (BOOT_WALK H4) |
| 49 | Exit (below rug) | Map032 | Yes (H5) |
| 48 | Stairs | Map049 | Yes (U3) |
| 32 | Lab door (17,11) | Map050 | Yes (M13) |
| 32 | House-1 door (24,42) | Map065 | Yes (M14) |
| 32 | House-2 door (43,31) | Map064 | Yes (M15) |
| 32 | Theo's door (56,42) | Map172 | Yes (M16) |
| 32 | East edge (toward Route 03) | blocked, connections unconverted | Yes — assert clean block, not a walk-through (M11) |
| 32 | Cave entrances (×3) + one remaining door (EV005) | inert | **No** — slice-2 frontier / known gap, do not test as a defect (M17) |
| 50 | Exit | Map032, arrival just outside lab door | Yes (L5) |
| 65 | Exit | Map032 (24,42) | Yes (N1c) |
| 64 | Exit | Map032 (43,31) | Yes (N2c) |
| 172 | Exit | Map032 (56,42) | Yes (T5, partial) |
| 172 | Stairs up | Map089 | Yes (T3) |
| 89 | Stairs down | Map172 | Yes (T5) |

`code 201` (RGSS Transfer Player) counts per map, for cross-check against the
above: Map032=9, Map048=1, Map049=5, Map050=1, Map064=1, Map065=1, Map089=1,
Map172=4 — higher than the table above because arrival warps are emitted
alongside source warps (per the 2026-07-02 warp-fidelity fix) and Map049/172
carry extra postgame-only warp variants. `[auto]` for round-trip position
sanity (BOOT_WALK X3, currently unchecked).

## 5. Wiki vs rxdata discrepancies

Carried forward from the predecessor doc (re-verified against the same rxdata
this pass; no new discrepancies found beyond these three):

1. **Wiki does not describe the professor sending the player to fetch Theo.**
   The rxdata (Map032 EV009 page 1, `VAR_QUEST_LOG==1`) has this exact line:
   *"I want to show you and Theo how to catch a Pokémon. Can you go get him?
   He should be in his house."* This is N2's redirect page. The rxdata is
   authoritative; the wiki walkthrough skips this intermediate state entirely.
2. **Wiki is inconsistent on whether the tutorial wild battle precedes or
   follows the Pokédex hand-off** at B13. Rxdata: it is all one scripted scene
   inside EV009 page 2 — Bamb'o's capture demo is pure choreography
   (`applymovement`-equivalent RGSS move routes on events 16/2/76/77), not a
   real battle. No `code 301` battle-processing command appears anywhere in
   the page.
3. **fandom.com returns HTTP 402** in this environment for direct fetch;
   cross-check went through WebSearch snippets only, timeboxed. Treat any wiki
   detail in this document as soft corroboration, never as a gate source.

No additional discrepancies surfaced this pass — the beat table, gates, and
variable writes above were all read directly from the map JSON, not inferred
from the wiki.

## 6. Known open issues and deferred items

**Correcting the brief's premise:** the task background states "1 live
slice-1 entry, a Map049 species-check blocked on Phase 7." This is **stale**.
`SLICE1_TODO.md` and `MEMORY.md` both record the starter-species conversion as
**closed 2026-07-21** — `pbHasSpecies?` → `checkspecies(SPECIES_*)` compiles
clean in Auntie's dialogue on Map049, and the boot-walk for that fix passed
(ROM `b0b21993`). There is no live species-check queue entry for Map049 in
the current `transpile_unhandled.jsonl`. **Do not carry this claim forward.**

Current state of `output/uranium-build/transpile_unhandled.jsonl`, filtered to
entries that touch the 8-map roster (by `map_id`) or a common event the
roster calls:

| map_id / CE | Event | Count | Assessment |
|---|---|---|---|
| 50 | Aide (`isCustomGame?` branch), Postgame Cutscene, LilyHazma (nuclear-cure NPC), EV026, EV027 | 12 | All gated `switch 125` (postgame) or otherwise unreachable at `VAR_QUEST_LOG` values chapter 1 produces — **not chapter-1 blocking** |
| 64 | EV003 warp | 1 | Classifier-flagged placeholder `MAP_URANIUM_32` constant, resolved at Phase 5 build time — cosmetic queue residue, not a runtime defect (same for 65/172 below) |
| 65 | EV003 warp | 1 | Same as above |
| 172 | EV002 warp, Theo (several `code 202`/`207`/postgame `pokegear`) | 9 | Warp entry same placeholder-residue pattern; the Theo entries are the **postgame** branch (HM07, `switch 125`) plus a couple of in-chapter cosmetic animation calls (`code 207` self-animation, no v1 self-reference) that degrade gracefully to no animation, not a hard failure |
| CE 76 "TheoBattle" | — | 62 | **Resolved this pass — false alarm, reclassify to defer.** Checked directly: `grep '"code": 117'` (RGSS common-event call) across all 8 roster maps returns **zero hits everywhere**, including Map050. Nothing in the chapter calls any common event at all. The working B9 battle is a direct `pbTrainerBattle(PBTrainers::RIVAL, "Theo", …)` script call authored inline in Map050's own "Theo" event (confirmed at `Map050.json:9009`), not a call into CE76. CE76's 62 unhandled entries are queue residue from a common event the chapter never reaches — same shape as CE10/11/12/35/37/51/86/87 below, just missing its own row in the predecessor doc's defer bucket. Should be moved there; not a chapter-1 gap. |

Also present in the raw jsonl but **confirmed not chapter-1 relevant** (no
`map_id` in the 8-map roster and no `common_event_id` any roster map calls):
CE10/11 (racing minigames), CE12 (Abyssal Venesi reset), CE35 (Bambo Phone
Call — a later-game callback mechanic), CE37 (Gym 8 puzzle), CE51 (day/night
NPC swap), CE86/87 (Fennel dream sequences). These match the predecessor
doc's "defer" bucket and remain correctly out of scope.

**Design/implementation fixes from the predecessor doc, current status
(re-verified this pass):**

- **BUG A (coord-event `VAR_TEMP_0` collision, blocked Theo's B4 trip tile):**
  fixed — BOOT_WALK S2 passed.
- **BUG B/B' (autorun pages mis-triggered or dropped):** fixed — B5 (lab
  intro) and B12 (PokéPod scene) both pass their respective boot-walk items
  (S3, and the 2026-07-21 Theo-visible fix for S7 pending re-walk).
- **BUG C (`applymovement` collision on choreographed hidden actors):**
  `local_id_remap.py` now raises `ValueError` on any unmapped/colliding local
  id rather than warning-and-leaving (confirmed in source, this pass);
  `hidden_actor_bracket.py` exists implementing the §5 "emit gated-off actors
  behind a visibility flag" design, and is now branch-aware per the S7 fix
  note. B13's ceremony choreography should be safe, but **S8/S9 have not yet
  been boot-walked** (checklist still shows them unchecked) — do not mark this
  beat "passed" without that walk.
- **BUG D (ceremony ended writing the wrong variable):** fixed — confirmed
  directly in `hand_conversions/Map032_EV009.pory:218`, now
  `setvar(VAR_QUEST_LOG, 4)`.

**Chapter-1 frontier per BOOT_WALK_CHECKLIST §8:** S7 (PokéPod scene) is the
last *un-passed* item with a landed fix awaiting re-walk; S8/S9/S10 (ceremony
completion + post-chain regression sanity) are built but unwalked.

**Slice-2-frontier items, not chapter-1 bugs:** cave entrances, the one
remaining inert door (EV005) in Moki Town, and the Route 03 east-seam block —
all documented gaps, not defects, per BOOT_WALK_CHECKLIST's "Not implemented"
list.

## 7. Open items for the lead

- **N2 confirms the redirect writes no variable** — this was the single most
  important open question handed to this doc; answered definitively from the
  rxdata (see §3.2). No ambiguity here.
- **CE76 "TheoBattle" is confirmed dead code for this chapter** (§6) — no
  common-event call exists anywhere in the 8-map roster (`code 117` count is
  zero on all 8 maps). Recommend moving its 62 queue entries into the
  predecessor doc's defer bucket alongside CE10/11/12/35/37/51/86/87 so the
  live queue count for slice 1 stops looking larger than it is.
- **"PC holds a free Potion" at B1** — could not verify in map/system rxdata
  this pass; either drop it from the chapter's expected state or point me at
  where Trainer default-items/party config lives so it can be re-checked.
- **B13/S8/S9 not yet boot-walked** — the design fixes for BUG C look complete
  in source, but per CLAUDE.md's fail-loud discipline this document does not
  claim the ceremony beat "passes" until that walk happens. Flagging so it
  isn't accidentally treated as done because the code changes read clean.
- **Item grant "duplicate row"** in §4.2 (10× vs 5× Poké Ball on the same
  event) — the map data literally contains both a `pbReceiveItem(POKeBALL,5)`
  and elsewhere in the corpus a `pbReceiveItem(POKeBALL,10)` reference for the
  same ceremony template; only one fires per the actual page-2 script read for
  Map032. Listed as a data-hygiene note, not a chapter-1 blocker.

## 8. By-eye checks `[eye]` for this chapter

Pulled from `BOOT_WALK_CHECKLIST.md`'s still-open `[ ]` items that are
inherently visual (art/legibility/palette/animation), reproduced here as the
chapter's waypoint list per ROM_TEST_DEV Branch G's contact-sheet plan:

- **L1/L2** — Lab (Map050) art + palettes, NPC colors by eye (flagged as the
  single biggest silent-failure risk — NPC palette overflow is silent, no
  build error)
- **L3** — Ball-machine prop (64×64 sprite class, first use in the corpus)
- **L4** — Lab NPC dialogue readability
- **M5** — NPC movement cadence vs PC Uranium (range/timing fine-tune, #12 —
  functionally working, feel-tuning only)
- **M9** — Pokédex ceremony: does the scene read acceptably given the known
  gap that ball/starter sprites don't swap mid-scene
- **M10** — Emote (!/?) placement over NPCs, timing unclear even to the
  human operator — needs a reference pass against PC Uranium
- **X1** — Every new interior's NPC/sprite colors (shared ≤4 palette banks;
  overflow is silent)
- **X3** — Warp round-trips: arrival tile sane in both directions, every door

Everything else in the checklist's still-open list (H3 ninja letter, M17 cave
doors) is a documented deferral, not a by-eye check for this chapter.

---

*Companion docs: `reference/findings/moki_slice_story_chain_2026-07-16.md`
(predecessor, superseded by this file for chapter-authoring purposes but kept
for its bug-investigation narrative), `BOOT_WALK_CHECKLIST.md` §0-§8 (walk
status), `SLICE1_TODO.md` (live fix tracker), `ROM_TEST_DEV.md` (harness design
and the Branch A/B/G decisions this document implements).*
