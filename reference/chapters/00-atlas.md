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

**60 chapters, 10 acts, 187 bound maps + 11 explicitly unbound = 198.** The
coverage command asserts that identity, so a map cannot fall through the gap.
(`validate` also reports 17 revisit chapters, up from 16, and a tier split of
2 full / 17 medium / 41 thin — CH07A, added 2026-08-29, is thin. See §7.)

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
* **A2 is now 5 chapters, not 4** — CH07A was inserted 2026-08-29 (§7). Its two
  maps (33, 81) were already bound to CH02 in A1, so they add nothing to A2's
  "new maps" count under the de-dup rule; the rest of this table's A2 row
  (revisited/events/commands/trainers/item grants/enc maps) was generated
  before that insertion and is pending a census recompute.

## 3. Chapter chain

Tier legend: **F** full, **M** medium, **T** thin. Status is from the binding.

| # | Chapter | Act | Tier | Maps | Trainers | Items | Notes |
|---|---|---|:-:|--:|--:|--:|---|
| CH01 | Moki Town | A1 | F | 8 | 1 | 7 | **§9 boot-walk gate passed 2026-08-04** — `01-moki.md` |
| CH02 | Route 1 | A1 | F | 2 | 9 | 7 | **built** — §9 gate passed 2026-08-12, suite 29/29; `02-route-1.md` (spec), `reference/archive/CH02_TODO.md` (retired checklist) |
| CH03 | Kevlar Town | A1 | M | 5 | 5 | 5 | **built** — §9 gate passed 2026-08-19, suite 60/60; bike; map 19 bound here, see §6 |
| CH04 | Route 2 | A1 | M | 1 | 4 | 3 | **built** — §9 gate passed 2026-08-27, suite 74/74; rockslide gate; `04-route-2.md` (spec), `reference/archive/CH04_TODO.md` (retired) |
| CH05 | Passage Cave | A1 | M | 2 | 3 | 5 | first dungeon |
| CH06 | Nowtoch City | A1 | M | 8 | 6 | 11 | **Gym 1**, first metro, Rock Smash |
| CH07 | Route 2 (revisit) | A2 | T | 1 | 4 | 3 | overland seam opens |
| CH07A | Route 1 (revisit) | A2 | T | 2 | 9 | 7 | inserted 2026-08-29, see §7; maps 33/81, rides Kevlar (31) as entry leg |
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

**2 full · 17 medium · 41 thin.** The gradient is distance-based, with a
promotion rule: *the chapter where a mechanic first appears is promoted one
tier*, because that is where the "what needs new code" answer lives and it is
cheap to write once. Promoted chapters and their reason are recorded in each
chapter's `notes` field in `reference/chapters.json`.

As the frontier advances, retier: the active chapter and its successor go
`full`, the rest of the active act goes `medium`. Nothing else changes.

## 5. Mechanics inventory

Derived from script-call heads across all 59 chapters as of the last recompute
(CH07A, added 2026-08-29, is not yet reflected). The count is **chapters
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

## 7. Slice-1 coverage audit (2026-08-29)

`PLAYTEST_AUTHORING_IMPROVEMENT_V2.md` Q11 bound a chain re-check as a **slice-1
exit criterion**: the chapter chain had been authored against `connections.json`'s
14 overland rows, and was to be re-audited exactly once against the full
warp/door connectivity graph. That graph now exists —
`src/rpg2gba/traversal/world.py`, CLI `python -m rpg2gba.traversal world` — and
this section is the close-out.

**What was measured.** 199 maps, **1108 edges** (warp 1076, connection 28,
seam_warp 4) — a 79x expansion over the 14 rows the chain was originally
authored with. 12 connected components: one of 188 maps, plus 11 singletons,
all editor scratch/menu/cutscene maps (30 POKE-URANIUM, 38 ETC, 39 Test Area,
55 GAME, 56 MOVIES, 62 Unknown, 103 Gym3.1, 107 Labyrinth(Underwater), 118
Route 14(Underwater), 124 Gym3, 999 Map999). 47 one-way (non-reciprocal) map
pairs, most of them legitimate one-way story warps (the Championship Site
gauntlet 131→194/195→196/197→199, the intro→title-screen edges, Hall of Fame
199→48). 9 variable-driven (`mode != 0`) warps, all on map 212 "Palace of
Dreams", whose destinations are chosen at runtime — the offline graph cannot
see them, so this is a named, countable blind spot rather than an unmeasured
one.

**Three data findings from the world graph itself:**

1. Map 183 "Rochfale Town" has 8 outgoing warps and **zero incoming edges** —
   the player can never walk into it. It is a dangling RPG Maker editor
   duplicate, currently bound to **CH14**. Needs verification before CH14 is
   built. *(Resolved 2026-09-17: verified unreachable — including map 212's variable
   warps, which only target 212 itself — and STRIP-listed along with 124 "Gym3";
   both moved to `unbound_maps`. Both are drafts painted against the full
   `Outside.png` sheet, so their tile ids overrun their bound tileset.)*
2. Map 999 has a `Map999.json` file but no `map_infos.json` entry, so it sits
   outside the "187 bound + 11 unbound = 198" identity entirely — no coverage
   check can see it. `coverage` confirms it directly: *"maps in corpus but in
   no chapter and not declared unbound: 999 (Map999)"*. It is also an orphan
   in the world graph — no edges at all.
3. Four maps declared in `unbound_maps` do have real edges into the playable
   graph: 51 (Intro) → 48, 57; 57 (Nuclear Plant) → 48; 94 (Mapa intro) → 14,
   95; 95 (Intro 2) → 14. Being unbound is still probably right — these are
   pre-title/cutscene maps — but "unbound" and "disconnected" are not the same
   claim, and this atlas did not previously distinguish them.

**The coverage audit — walked legs.** For each chapter, `coverage` takes the
shortest map-to-map path from the predecessor chapter's `outdoor` map to the
chapter's own `outdoor` map, and reports any transit maps belonging to neither
chapter. It found **14 unmodelled walked legs**, not the single one Q11 knew
about:

| leg | transit map | covered by | at/after leg |
|---|---|---|---|
| CH07→CH08 | 31 (Kevlar Town) | CH03 | -- STRANDED -- |
| CH07→CH08 | 33 (Route 01) | CH02 | -- STRANDED -- |
| CH18→CH19 | 8 (Route 07) | CH17, CH20 | CH20 |
| CH20→CH21 | 117 (Route 08) | CH22 | CH22 |
| CH25→CH26 | 128 (Legen Town) | CH24, CH38, CH54 | CH38, CH54 |
| CH25→CH26 | 27 (Route 09) | CH27 | CH27 |
| CH25→CH26 | 22 (Route 06) | CH15 | -- STRANDED -- |
| CH25→CH26 | 12 (Rochfale Town) | CH14 | -- STRANDED -- |
| CH26→CH27 | 12 (Rochfale Town) | CH14 | -- STRANDED -- |
| CH26→CH27 | 22 (Route 06) | CH15 | -- STRANDED -- |
| CH27→CH28 | 128 (Legen Town) | CH24, CH38, CH54 | CH38, CH54 |
| CH27→CH28 | 129 (Legen Town(Metro)) | CH24, CH38, CH54 | CH38, CH54 |
| CH27→CH28 | 168 (Legen Town(Metro)) | CH24, CH38, CH54 | CH38, CH54 |
| CH28→CH29 | 9 (Route 04) | CH11, CH32 | CH32 |
| CH28→CH29 | 76 (Route 04) | CH11, CH32 | CH32 |
| CH33→CH34 | 142 (Route 05) | CH13, CH26 | -- STRANDED -- |
| CH37→CH38 | 8 (Route 07) | CH17, CH20 | -- STRANDED -- |
| CH37→CH38 | 117 (Route 08) | CH22 | -- STRANDED -- |
| CH37→CH38 | 140 (Route 11) | CH25 | -- STRANDED -- |
| CH38→CH39 | 140 (Route 11) | CH25 | -- STRANDED -- |
| CH38→CH39 | 117 (Route 08) | CH22 | -- STRANDED -- |
| CH38→CH39 | 8 (Route 07) | CH17, CH20 | -- STRANDED -- |
| CH38→CH39 | 101 (Bealbeach City) | CH19, CH37, CH51 | CH51 |
| CH38→CH39 | 144 (Venesi City) | CH36, CH47 | CH47 |
| CH45→CH46 | 88 (Route 16) | CH44 | -- STRANDED -- |
| CH45→CH46 | 132 (Route 16) | CH44 | -- STRANDED -- |
| CH45→CH46 | 106 (Lanthanite Cave) | CH43 | -- STRANDED -- |
| CH51→CH52 | 8 (Route 07) | CH17, CH20 | -- STRANDED -- |
| CH53→CH54 | 28 (Route 08 (plant)) | CH22 | -- STRANDED -- |
| CH53→CH54 | 117 (Route 08) | CH22 | -- STRANDED -- |
| CH53→CH54 | 140 (Route 11) | CH25 | -- STRANDED -- |
| CH58→CH59 | 59 (Route 03) | CH09 | -- STRANDED -- |
| CH58→CH59 | 1 (Route 03) | CH09 | -- STRANDED -- |
| CH58→CH59 | 60 (Burole Town) | CH10, CH28 | -- STRANDED -- |
| CH58→CH59 | 5 (Burole Town(Metro)) | CH10, CH28 | -- STRANDED -- |
| CH58→CH59 | 6 (Burole Town(Metro)) | CH10, CH28 | -- STRANDED -- |
| CH58→CH59 | 11 (Bealbeach City(Metro)) | CH19, CH37, CH51 | -- STRANDED -- |
| CH58→CH59 | 3 (Bealbeach City(Metro)) | CH19, CH37, CH51 | -- STRANDED -- |
| CH58→CH59 | 101 (Bealbeach City) | CH19, CH37, CH51 | -- STRANDED -- |
| CH58→CH59 | 144 (Venesi City) | CH36, CH47 | -- STRANDED -- |
| CH58→CH59 | 97 (Venesi City) | CH36, CH47 | -- STRANDED -- |

"STRANDED" here means the strict finding: a transit map covered only by
chapters **before** the leg, i.e. no chapter at or after the leg re-covers it.
Only the **CH07→CH08 leg** strands content in that strict sense — the walk is
`35 → 31 → 33 → 32`, and map 31 (Kevlar Town) was covered only by CH03, map 33
(Route 01) only by CH02, both earlier than the leg with nothing later picking
them back up. Every other leg's "STRANDED" rows are transit maps covered by
some *earlier* chapter only — which is a stranding claim only if the leg newly
unblocks content there, and that is **not derivable today**, because
`reference/manifests/` holds dispositions for CH04 alone. Those 12 other legs
are recorded as countable debt, re-checked once each chapter carries its own
manifest.

**The five decisions taken (operator-adjudicated 2026-08-29):**

1. **`CH07A "Route 1 (revisit)"` is inserted between CH07 and CH08** — maps
   [33, 81], outdoor 33, visit 2, act A2, tier thin. Full rationale is in its
   `reference/chapters.json` entry: it restores CH02's 10
   `DEFERRED_ROCK_GATED` beats (5 trainer battles, B3's staircase run, B14b, 3
   item balls) and the Old Rod content in map 81 (gated on
   `VAR_BATTLE_VAR01 >= 5`, written by CH06/Map042), and owes 6 boulder beats
   never authored since Rock Smash was granted in CH06.
2. **Kevlar (31) does not get its own chapter here.** It rides along as
   CH07A's entry leg — enter from Route 2, cross Kevlar, exit south into
   Route 1, full warp assertion per seam — because at Rock Smash time it owes
   nothing.
3. **Kevlar's and Passage Cave's real debt is a recorded permanent hold,
   decided at CH25.** Their 10 deferrals are Strength ×7 (HM04, granted CH25),
   Bike Wheel ×1 (CH11), post-Gym-5 story flag ×1, and B26 whose dev-only flag
   `sw130` is never set anywhere in the corpus — a mis-disposition owed a
   re-triage to `unreachable`. No leg in the 60-chapter chain re-crosses
   Kevlar at or after CH25; it is Fly-only. The operator chose to record this
   as a countable hold rather than mint a revisit chapter now.
4. **The other 12 legs are recorded as countable debt**, each owed a re-check
   once its chapters have dispositions.
5. **Id `CH07A`, not a renumber.** `binding.py` accepts any unique string id;
   renumbering CH08–CH59 would invalidate every `CHnn` reference in the docs
   and the committed manifest filenames.
   `tests/test_chapter_atlas.py::test_chapter_ids_are_contiguous_and_play_ordered`
   was updated to permit a letter-suffixed insertion while still requiring
   contiguous base numbers and play-ordered ids.

## 8. Known gaps in this atlas

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
5. **CH39's map binding is a guess** (see §6 #6). **CH18's data-derived binding
   (§6 #5) and CH39's guess were both flagged uncertain before the 2026-08-29
   coverage audit (§7) and neither was re-examined in that pass** — they still
   owe verification.
6. **Map 62 "Unknown"** — 24 events, unreferenced by the walkthrough, currently
   unbound. Needs a look before it is bound or stripped.
7. **`Map999.json` has no `map_infos.json` entry** — confirmed by the
   2026-08-29 `coverage` run (§7): it falls outside the 187+11=198 identity
   entirely, and it is also an orphan in the world graph (no edges in or out).
   Still unexplained; needs a look before it is bound, declared unbound, or
   stripped.
8. **Map 183 "Rochfale Town" (bound to CH14) has zero incoming edges** in the
   1108-edge world graph — 8 outgoing warps, none reciprocated. It reads as a
   dangling RPG Maker editor duplicate the player can never walk into. Found
   by the 2026-08-29 audit (§7); needs verification before CH14 is built.
   *(Resolved 2026-09-17: verified and STRIP-listed; see finding 1 above.)*
9. **Four `unbound_maps` entries have real graph edges into the playable
   world**: 51 (Intro) → 48, 57; 57 (Nuclear Plant) → 48; 94 (Mapa intro) →
   14, 95; 95 (Intro 2) → 14. Found by the 2026-08-29 audit (§7). Being
   unbound (pre-title/cutscene maps) is still probably the right call, but
   this atlas previously conflated "unbound" with "disconnected" and they are
   not the same claim.
10. **12 of the 14 walked legs found by the 2026-08-29 coverage audit (§7)
    are recorded as countable debt, not resolved** — whether they newly
    unblock content in an earlier-covering chapter is undecided pending
    per-chapter manifests, which today exist only for CH04.
