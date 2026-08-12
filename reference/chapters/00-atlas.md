# Chapter Atlas — the whole game, at planning resolution

**Status:** live. This is the shallow, corpus-wide half of the chapter plan; the
deep half is one document per chapter in this directory, written at a detail
tier that decays with distance from the build frontier.

**What this is for.** Three questions, answerable before we build anything:

1. *What does the player do, in what order?* → the act/chapter chain below.
2. *What must the engine be able to do, and what of that is new C?* → the
   mechanics inventory (§5), which binds to the capability ledger
   `reference/guides/command_pokeemerald_map.md` rather than re-deriving verdicts.
3. *What does a ROM test for this section assert?* → each chapter document's
   beat table, which `src/rpg2gba/playtest/chapters/` mirrors beat-for-beat.

**How this document relates to the work checklist.** This atlas and each
chapter document (`NN-slug.md`) are the **plan and spec** — map rosters, story
beats, coverage targets. They do not track task status. The active chapter's
live **work checklist** is a root-level `CHnn_TODO.md` (currently
`CH02_TODO.md`) — open items, in-progress notes, done log. Once that chapter's
§9 boot gate passes, its TODO is archived to `reference/archive/` rather than
deleted, as happened with the slice-1 checklist, now at
`reference/archive/SLICE1_TODO.md`. Cross-cutting work not scoped to any one
chapter lives in `PROJECT_TODO.md`.

**Sources, and which one wins.** Act and chapter *identity, naming and ordering*
come from the wiki's `Game_Walkthrough` page. Chapter *map membership, counts and
gates* come from the converted rxdata and **always win on conflict**
(`ROM_TEST_DEV.md` Branch A1(b)). Every number below is generated, not
hand-copied:

```bash
python scripts/fetch_uranium_wiki.py Game_Walkthrough   # refresh the wiki source
python -m rpg2gba.chapter_atlas validate                # check the binding
python -m rpg2gba.chapter_atlas coverage                # every map accounted for?
python -m rpg2gba.chapter_atlas census --all --json output/uranium-build/chapter_census.json
```

Binding (the §4.3 SoT): `reference/chapters.json`.
Design record: `reference/findings/grill_chapter_atlas_2026-07-30.md`.

---

## 1. The model

| Term | Definition |
|---|---|
| **Act** | One top-level section of the walkthrough. Nine progression acts, each ending at a Gym, plus a postgame act. |
| **Chapter** | One location-unit within an act — a town plus its interiors, or a route plus its side rooms. **Chapter ≡ slice ≡ one §9 boot gate ≡ one ROM-test scenario.** |
| **Revisit** | A location entered again later behind new traversal is a **separate chapter** over the same map ids, with `visit > 1`. Map ids are deliberately *not* unique across chapters. |
| **Tier** | `full` / `medium` / `thin` — how deep that chapter's document goes. Distance from the frontier, promoted one tier where a mechanic first appears. |

**59 chapters, 10 acts, 187 bound maps + 11 explicitly unbound = 198.** The
coverage command asserts that identity, so a map cannot fall through the gap.

## 2. Acts at a glance

Counts are **de-duplicated**: a map is counted in the act where it is first
visited, so "new maps" sums to 187 and revisit chapters contribute 0 new maps.

| Act | Title | Ch | New maps | Revisited | Events | Commands | Trainers | Item grants | Enc maps |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|
| A1 | Moki Town → Gym #1 (Nowtoch City) | 6 | 26 | 0 | 514 | 7187 | 28 | 38 | 5 |
| A2 | Returning to Moki Town → Gym #2 (Burole Town) | 4 | 13 | 9 | 209 | 2480 | 16 | 12 | 1 |
| A3 | Route 4 → Gym #3 (Bealbeach City) | 9 | 39 | 0 | 885 | 10988 | 62 | 97 | 11 |
| A4 | Bealbeach City → Gym #4 (Vinoville Town) | 4 | 12 | 4 | 392 | 5745 | 28 | 24 | 2 |
| A5 | Legen Town → Gym #5 (Amatree Town) | 7 | 21 | 11 | 706 | 6674 | 30 | 85 | 5 |
| A6 | Route 10 → Route 4 → Route 12 → Gym #6 (Venesi City) | 6 | 8 | 9 | 334 | 3595 | 35 | 31 | 2 |
| A7 | Labyrinth → Silverport → Lanthanite Cave → Route 16 → Gym #7 (Snowbank) | 9 | 22 | 22 | 577 | 8177 | 42 | 57 | 5 |
| A8 | Return to Silverport → Venesi → Route 14 → Gym #8 (Tsukinami) | 4 | 8 | 10 | 389 | 4975 | 26 | 19 | 2 |
| A9 | Nuclear Plant Omicron → Zeta → Victory Road → Championship | 9 | 25 | 29 | 728 | 8355 | 46 | 56 | 10 |
| A10 | End Game (postgame) | 1 | 13 | 0 | 498 | 9073 | 4 | 0 | 7 |
| | **total** | **59** | **187** | **94** | **5232** | **67249** | **317** | **419** | **50** |

Reading notes:

* **A3 is the largest act** — 39 new maps and 9 chapters, versus A1's 26/6. It
  is not a good second slice target and should not be planned as one unit.
* **A7 and A9 are half revisits** (22/22 and 25/29). By then, most of a chapter's
  cost is new *gate states and events*, not new art or tilesets — a different
  work profile from A1–A3, and a much cheaper one if the revisit-chapter model
  holds up in A2.
* **A10 (Dream World) is 13 maps and 9,073 commands in one chapter** — the
  densest single chapter in the game, and entirely optional.

## 3. Chapter chain

Tier legend: **F** full, **M** medium, **T** thin. Status is from the binding.

| # | Chapter | Act | Tier | Maps | Trainers | Items | Notes |
|---|---|---|:-:|--:|--:|--:|---|
| CH01 | Moki Town | A1 | F | 8 | 1 | 7 | **§9 boot-walk gate passed 2026-08-04** — `01-moki.md` |
| CH02 | Route 1 | A1 | F | 2 | 9 | 7 | **built** — §9 gate passed 2026-08-12, suite 29/29; `02-route-1.md` (spec), `reference/archive/CH02_TODO.md` (retired checklist) |
| CH03 | Kevlar Town | A1 | M | 5 | 5 | 5 | bike; map 19 bound here, see §6 |
| CH04 | Route 2 | A1 | M | 1 | 4 | 3 | rockslide gate |
| CH05 | Passage Cave | A1 | M | 2 | 3 | 5 | first dungeon |
| CH06 | Nowtoch City | A1 | M | 8 | 6 | 11 | **Gym 1**, first metro, Rock Smash |
| CH07 | Route 2 (revisit) | A2 | T | 1 | 4 | 3 | overland seam opens |
| CH08 | Moki Town (revisit) | A2 | T | 8 | 1 | 7 | first revisit-model test |
| CH09 | Route 3 | A2 | T | 4 | 8 | 9 | Moki E seam |
| CH10 | Burole Town | A2 | T | 9 | 8 | 3 | **Gym 2** |
| CH11 | Route 4 | A3 | T | 2 | 8 | 11 | |
| CH12 | Comet Cave | A3 | T | 3 | 1 | 12 | |
| CH13 | Route 5 | A3 | T | 2 | 6 | 5 | |
| CH14 | Rochfale Town | A3 | T | 9 | 0 | 10 | no Gym — Cypress Lab |
| CH15 | Route 6 | A3 | T | 2 | 18 | 10 | |
| CH16 | Rochfale Tunnel | A3 | T | 1 | 4 | 0 | |
| CH17 | Route 7 | A3 | T | 4 | 11 | 16 | |
| CH18 | Nuclear Plant Epsilon | A3 | T | 3 | 3 | 3 | **data-derived, see §6** |
| CH19 | Bealbeach City | A3 | T | 13 | 11 | 30 | **Gym 3**; all game-corner content |
| CH20 | Route 7 (revisit) | A4 | T | 4 | 11 | 16 | |
| CH21 | Tandor Luxury Cruise | A4 | M | 1 | 10 | 2 | scripted vehicle |
| CH22 | Route 8 | A4 | T | 5 | 10 | 13 | Good Rod |
| CH23 | Vinoville Town | A4 | T | 6 | 8 | 9 | **Gym 4** |
| CH24 | Legen Town | A5 | T | 8 | 0 | 13 | 3 metro maps + VR building |
| CH25 | Route 11 | A5 | M | 2 | 0 | 4 | **HM04 Strength** |
| CH26 | Route 5 (revisit) | A5 | T | 2 | 6 | 5 | optional |
| CH27 | Route 9 | A5 | T | 3 | 4 | 5 | optional, day care |
| CH28 | Burole Town (revisit) | A5 | T | 9 | 8 | 3 | |
| CH29 | Route 10 / Anthell | A5 | M | 4 | 21 | 58 | **most item grants in the game** |
| CH30 | Amatree Town | A5 | M | 4 | 5 | 5 | **Gym 5**, **HM03 Surf**, barter economy |
| CH31 | Route 10 (revisit) | A6 | T | 4 | 21 | 58 | Surf shortcut |
| CH32 | Route 4 (revisit) | A6 | T | 2 | 8 | 11 | |
| CH33 | Comet Cave (revisit) | A6 | T | 3 | 1 | 12 | Surf back entrance |
| CH34 | Route 12 | A6 | T | 2 | 8 | 5 | |
| CH35 | Route 13 | A6 | T | 1 | 16 | 8 | |
| CH36 | Venesi City | A6 | T | 5 | 11 | 18 | **Gym 6** |
| CH37 | Bealbeach City (revisit) | A7 | T | 13 | 11 | 30 | optional |
| CH38 | Legen Town (revisit) | A7 | T | 8 | 0 | 13 | Surfboard + Power Glove |
| CH39 | Route 13 (revisit) | A7 | T | 1 | 16 | 8 | **uncertain binding, §6** |
| CH40 | The Labyrinth | A7 | M | 2 | 5 | 11 | first underwater map, first Mega Stone |
| CH41 | Route 15 | A7 | T | 3 | 9 | 10 | Super Rod |
| CH42 | Silverport Town | A7 | T | 5 | 4 | 2 | no Gym — Lab |
| CH43 | Lanthanite Cave | A7 | T | 2 | 6 | 15 | Waterfall-gated core |
| CH44 | Route 16 | A7 | T | 2 | 8 | 12 | ice-slide puzzles |
| CH45 | Snowbank Town | A7 | M | 8 | 10 | 7 | **Gym 7 across 4 maps**, Mega Evo, **HM08 Dive** |
| CH46 | Silverport Town (revisit) | A8 | T | 5 | 4 | 2 | |
| CH47 | Venesi City (revisit) | A8 | T | 5 | 11 | 18 | |
| CH48 | Route 14 | A8 | M | 2 | 10 | 9 | Dive surface/underwater pair |
| CH49 | Tsukinami Village | A8 | T | 6 | 16 | 10 | **Gym 8**, dual leaders |
| CH50 | Nuclear Plant Omicron | A9 | M | 1 | 0 | 1 | **HM02 Fly**, Nuclear content |
| CH51 | Bealbeach City (Rangers HQ) | A9 | T | 13 | 11 | 30 | |
| CH52 | Route 8 (Nuclear) / Hazard Zone | A9 | M | 3 | 14 | 3 | distinct maps from CH22 |
| CH53 | Nuclear Plant Zeta | A9 | M | 5 | 4 | 9 | 5-map compass complex |
| CH54 | Legen Town (revisit) | A9 | T | 8 | 0 | 13 | |
| CH55 | Victory Road | A9 | T | 6 | 24 | 42 | **most trainers in one chapter** |
| CH56 | Championship Site | A9 | M | 9 | 4 | 1 | randomised leader bracket |
| CH57 | Hall of Fame | A9 | T | 1 | 0 | 0 | credits |
| CH58 | Moki Town (postgame) | A9 | M | 8 | 1 | 7 | validates CH01's postgame exclusions |
| CH59 | Dream World | A10 | M | 13 | 4 | 0 | 13-map optional subtree |

## 4. Detail tiers

**2 full · 17 medium · 40 thin.** The gradient is distance-based, with a
promotion rule: *the chapter where a mechanic first appears is promoted one
tier*, because that is where the "what needs new code" answer lives and it is
cheap to write once. Promoted chapters and their reason are recorded in each
chapter's `notes` field in `reference/chapters.json`.

As the frontier advances, retier: the active chapter and its successor go
`full`, the rest of the active act goes `medium`. Nothing else changes.

## 5. Mechanics inventory

Derived from script-call heads across all 59 chapters. The count is **chapters
that need it**, which is the number that matters for sequencing: a mechanic
needed by 52 chapters must be right early.

| Chapters | Mechanic | Disposition |
|--:|---|---|
| 52 | trainer battle | native — but see §6, they are *all* hidden in conditionals |
| 47 | item ball | native `giveitem` (classifier 8) |
| 45 | trainer sight | native |
| 41 | item grant | native |
| 41 | wild encounters | native; day/night tables are a converter gap (`ROM_TEST_DEV.md` §0) |
| 37 | cave entry/exit | native |
| 29 | PC access | native `goto(EventScript_PC)` — verified |
| 20 | poké mart | native `pokemart` (classifier 9) |
| 20 | phone / rematch | **likely native Match Call** — was tagged C, corrected 2026-07-30 |
| 18 | scripted wild battle | native |
| 15 | gift pokémon | native `givemon` |
| 15 | berry plant | native berry trees |
| 13 | region map | native |
| 10 | rock smash encounter | native |
| 8 | rock smash | native |
| 6 | nuclear cure | **new C** — `reference/guides/nuclear_type_spec.md` |
| 6 | party species check | native `checkspecies` |
| 3 | party heal | native `special HealPlayerParty` — **not** `healparty` |
| 3 | lottery | **native Lottery Corner** — was tagged C, corrected 2026-07-30 |
| 3 | slot machine | **native `playslotmachine`** — was tagged C, corrected 2026-07-30 |
| 3 | voltorb flip | **genuinely new C** — zero engine presence |
| 3 | bespoke letter UI | accepted deferral (`SLICE1_TODO.md`) |
| 2 | double trainer battle | native |
| 1 | berry mart / vehicle state | native |

**The headline: the genuinely-new-C set is small and localised.** Voltorb Flip,
lottery and slot machine all live in **Bealbeach City alone** (CH19/37/51 are the
same maps), and of the three only Voltorb Flip is actually absent from the
engine. Outside that one town, the only new-C mechanic in the whole game is the
Nuclear type.

Unmapped script heads, in frequency order, are the capability-ledger backlog:
`pbCallBub` (59), `get_character` (56), `setTempSwitchOn` (56),
`pbSetSelfSwitch` (41), `pbSetPokemonCenter` (35), `pbPokerus` (23).

## 6. Wiki-vs-data disagreements

Recorded here rather than silently resolved, per house style. **In every case the
data wins.**

| # | Wiki says | Data says | Resolution |
|---|---|---|---|
| 1 | Seaspray Town, Ara City exist | No such maps in `map_infos.json` | Do not exist. `SKILL.md` corrected. |
| 2 | Rochfale = Gym 4, Silverport = Gym 8 | Neither has a Gym map (Cypress Lab / Lab) | Wiki *navigation* was wrong; the walkthrough *body* agrees with the data. |
| 3 | Burole Town absent from navigation | `Burole Town` (60) + `Burole Town(Gym)` (66) | Gym 2. |
| 4 | Passage Cave is one place | Map 19 warps **only** to/from Kevlar; the traversal is 35→36↔37→40 | Map 19 bound to **CH03 Kevlar**, not CH05. |
| 5 | Epsilon never entered | Warp graph shows 122 ↔ 8 (Route 07) both ways | Bound as **CH18**. |
| 6 | "Maskara Island" | No such map | Context-matched to Route 13 (CH39) — **unverified, flagged**. |
| 7 | "Hazard Zone", "Bell Island", "Tandor Underground", "Fossil Sidequest cave" | No maps of those names | Mechanic/area labels spanning existing maps; resolved in `chapters.json` notes. |
| 8 | Route 8 revisited as Nuclear | Map **187**, distinct from map 117 | A separate chapter (CH52), not a revisit. |

## 7. Known gaps in this atlas

Honest limits, so nothing here is over-trusted:

1. **Conversion-readiness is unmeasured for 195 of 199 maps.** The transpiler's
   unhandled queue only covers staged maps — CH01 — so the census reports
   `unhandled: null` (not `0`) elsewhere. A corpus survey currently **aborts**:
   `transpile_driver run --maps full --dry-run` fails the fork-index gate on
   Map008 because Uranium `TRAINER_*` constants are only staged for CH01.
   Until a gate-tolerant survey mode exists, "what needs conversion work" is
   answered per chapter only after that chapter is staged. *This is the single
   highest-value follow-up in the plan.*
2. **`--dry-run` is not dry.** `transpile_driver.py:405` writes
   `transpile_unhandled.jsonl` outside the `if write:` guard, so a survey run
   overwrites the slice queue. Back it up first, or fix the guard.
3. **Gates are not yet bound.** `gate_in` is `null` for every chapter; the
   quest-var chain is only mapped for CH01. Filling it needs a corpus-wide
   control-variable census, which the census tool can do but does not yet.
4. **Encounter tables are counted, not validated.** 50 maps carry tables; the
   day/night gap and the Evening-bucket decision are still open.
5. **CH39's map binding is a guess** (see §6 #6).
6. **Map 62 "Unknown"** — 24 events, unreferenced by the walkthrough, currently
   unbound. Needs a look before it is bound or stripped.
7. **A stray `Map999.json`** exists with no `map_infos.json` entry. Unexplained.
