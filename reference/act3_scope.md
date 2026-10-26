# Act 3 scope (CH11–CH19) — pre-open investigation, 2026-10-26

Read-only scoping done before opening CH11, at the operator's request (the A2→A3 intermission was
skipped). Four questions: what can't be reached, what gets stitched, whether the chapter divisions
hold, and which big chunks of work to expect. Raw evidence (scripts and scan dumps) is under
`output/scratch/a3_{reach,stitch,chapters,work}/` (gitignored; regenerate from the scripts there).
Facts marked **verified** were re-checked by the lead in the rxdata; the rest are sub-agent findings
with the evidence they cited. Mechanical terms only — no story content.

Act 3 as `reference/chapters.json` defines it today:

| Chapter | Title | Maps |
|---|---|---|
| CH11 | Route 4 | 76, 9 |
| CH12 | Comet Cave | 7, 96, 10 |
| CH13 | Route 5 | 142, 154 |
| CH14 | Rochfale Town | 12, 13, 92, 93, 130, 104, 98, 91 |
| CH15 | Route 6 | 22, 105 |
| CH16 | Rochfale Tunnel | 17 |
| CH17 | Route 7 | 8, 115, 178, 205 |
| CH18 | Nuclear Plant Epsilon | 122, 123, 125 |
| CH19 | Bealbeach City | 101, 102, 103, 108, 58, 109, 113, 126, 156, 3, 11, 52 |

`chapter_atlas validate` and `coverage` pass (59 chapters; 198 maps, 182 bound, 16 declared unbound).
No Act 3 map is in `strip_list.json`.

---

## 1. Size

Events / pages / commands from the rxdata. CH10 (153 / ~230 / 2137) is the yardstick.

| Chapter | Events | Pages | Commands | Trainer battles |
|---|---|---|---|---|
| CH11 | 55 | 99 | 790 | 8 |
| CH12 | 57 | 94 | 726 | |
| CH13 | 34 | 50 | 490 | |
| CH14 | 95 | 133 | 1343 | |
| CH15 | 97 | 155 | 1421 | 18 |
| CH16 | 8 | 14 | 126 | 0 |
| CH17 | 74 | 147 | 1295 | |
| CH18 | 57 | 91 | 1060 | |
| CH19 | 326 | 511 | 5505 | |

Act total ≈ 62 trainer battles and 97 item grants. Act 3 is ~4–4.5× Act 2 overall. CH19 alone is
~2.5× CH10, but map 156 (Ranger HQ) holds 1774 of its commands and most of those pages need
progress variables (V123 ≥ 12, V126 ≥ 9) that only later acts set — they are dormant in Act 3.

---

## 2. Reachability — what the player can't get to

Method: traversal world graph + `reachable_with` from every incoming warp cell, holding Rock Smash
only (what the player has at A2's end). Static collision only — NPC blockers and teleport pads are
not simulated, and Cut obstacles are invisible to the model.

**Every warp on the Act 3 critical path is reachable with Rock Smash alone.** No HM or missing map
cuts the chain. The gaps:

| Area | Maps | Cause | Severity |
|---|---|---|---|
| Surf water and shores | 7, 8, 76, 96, 122, 142 | Surf not held until ~Gym 6. Same treatment as Route 3 (`blocked:surf`). Route 7 (8) and the plant (122) are mostly water (~1.4k of 7k and ~1k of 5.4k cells are land). | Low–medium; optional content |
| Strength boulder pockets | 7 (EV017; EV20–22 behind it), 96 (EV010, EV013), 76 (EV007) | Strength (HM04) arrives in CH25 (switch SW86 "Has Strength" is set on map 140). | Low; optional pockets |
| Touch-warps to later chapters | 76 EV008/036/037 → 143 (Route 10, CH29); 22 EV069 → 27 (Route 9, CH27); 8 EV064/065 → 188 (CH52, VAR123-gated); 101 EV058 → 14 (title screen, unbound, SW30-gated) | Destination not built in Act 3. | Medium; must be sealed/inert at build |
| Bealbeach metro | 3, 11 (stations); 101 EV20–23 (entrance guards) | Departures go to 6 (CH28), 168 (CH24/38/54), 45 (parked unbound); the entrance switch SW85 is written only on map 167 (CH54). Same situation as Burole's station (`10-burole-town.md` §7.1). | Medium; the metro is unusable in Act 3 |
| Gym3.1 | 103 | Orphan: no incoming warp or connection, 0 events. | Low; but it is bound to CH19 |
| Blocked berry | 122 EV018/019 | `pbPickBerry(HAFLIBERRY)`; HAFLIBERRY is `kind: blocked` in `item_rulings.json` (needs a Nuclear type) → conversion fails loud. | Medium; needs a ruling or strip before CH18 |
| Epsilon teleport pads | 123 EV011 → 125; 156 EV2/EV5 → 101 | Pads aren't simulated, so statically unreachable; pad pages sit on SW52 / self-switch conditions. | Low; verify at CH18 |

**Story-flag gates.** Almost every switch an Act 3 page reads is set inside CH01–CH19. Exceptions are
pages that only *empty out* once a later switch is set (SW81 on 22 EV56/57/78; SW85 on 101 EV20–23;
SW95 on 76 EV11; SW123/125 on 156) — their page 0 stays live in Act 3, and modelling those NPCs as
walls cuts no warp. SW118 gates the 101 EV83 ferry to 144 and is set only later (unreachable by
design). Switches with no setter are runtime predicates, not flags (SW12/22 time switches, SW31,
SW33, SW59–61 "has starter X", SW105/106 day/night, SW750).

**Corrected during review:** Comet Cave map 7 EV001 has a page on SW86 ("Has Strength"), which one
report read as a gate. **Verified:** it is not — EV001 page 0 is the autorun partner-join scene,
and the SW86/SW68 pages are its later idle states.

**Not determined:** Cut/Flash/Dive tags (the model can't see them); whether any Surf/Strength
pocket holds a required item; whether blocked battle moves appear in Act 3 trainer/wild sets (only
map JSON was scanned, not PBS trainers); whether the bike wheel (atlas: a CH11 item) gates anything.

---

## 3. Stitching — which maps join

Connections come from Uranium's `connections.dat` (`output/uranium-build/connections.json`, 14 rows
in the whole corpus; `tileset_converter/connections.py`). A row is emitted only when both maps are in
the build. Connected maps on the **same** RMXP tileset share one physical tileset (the union must fit
1024 tiles / 1024 metatiles); on **different** tilesets they become a remapped connection (each keeps
its own tileset, imports the neighbour's border art, ids translated by `connection_remap`). Seam
warps are only for pairs that can't do either — `seam_warps.json` is empty today.

Only five connections touch Act 3; none join an earlier act:

| Edge | Tilesets | Kind |
|---|---|---|
| 142 (Route 5, CH13) S ↔ 76 (Route 4, CH11) N | 25 / 24 | remapped connection |
| 12 (Rochfale, CH14) W ↔ 22 (Route 6, CH15) E | 25 / 25 | shared tileset group |
| 8 (Route 7, CH17) N ↔ 101 (Bealbeach, CH19) S | 28 / 28 | shared tileset group |
| 142 E → 87 | 25 / 27 | frontier: 87 is CH34; dropped until then |
| 8 W → 117 | 28 / 30 | frontier: 117 is CH22; dropped until then |

Everything else in the act — all of Comet Cave, the tunnel, Rochfale's interiors, the plant
interiors and Bealbeach's 11 interiors — is warp-only.

**Tile budget** (`tileset_budget()` in `scripts/map_viewer_common.py`; tiles / metatiles, cap 1024):

| Map | CH | RMXP ts | Size | Merge off | Merge on |
|---|---|---|---|---|---|
| 76 | 11 | 24 | 62×115 | 973 / 852 | 660 / 653 |
| 142 | 13 | 25 | 106×45 | 869 / 854 | 634 / 679 |
| 12 | 14 | 25 | 70×70 | 985 / 875 | 729 / 745 |
| 22 | 15 | 25 | 130×60 | 803 / 738 | 610 / 583 |
| 8 | 17 | 28 | 100×100 | 879 / 606 | 597 / 462 |
| 101 | 19 | 28 | 80×72 | **1762 / 1557** | **1316 / 1073** |
| 122 | 18 | 31 | 80×90 | **1645 / 1009** | **1122 / 841** |
| 123 | 18 | 49 | 80×80 | 332 / 297 | 147 / 179 |
| 7 | 12 | 32 | 60×60 | 349 / 238 | 271 / 155 |
| 17 | 16 | 32 | 70×30 | 221 / 167 | 145 / 106 |

Interiors (102, 108, 156, 52 on ts 19) run 190–413 tiles.

Risks:
- **101 and 122 are over the cap but already streamed** (`streamed_maps.json` = 40, 101, 122, since
  the I4 intermission). Streaming maps never get tile merge.
- **Shared groups are unmeasured.** {12, 22} on ts 25 (729 + 610 merged) is the one to watch;
  {8, 101} includes a streamed map, so it needs a look at how a streamed map shares a group. The
  budget tool measures one map's pool at a time.
- Non-streamed Act 3 outdoor maps fit **only with merge on** (76 and 12 are near 1000 with it off).
- **Corrected during review:** one report flagged map 22 (130×60) as over the map-data buffer
  (`(w+15)*(h+14) > 10240`). That limit was lifted 2026-10-18 by the windowed backup grid (#148,
  `engine/src/fieldmap.c` `BigMapInit`); Route 3 already exceeds it and works. Not a risk.

---

## 4. Chapter divisions

### 4.1 The ordering error (verified)

**CH17 → CH18 → CH19 is not playable in that order.**
- Route 7's entrance to the plant (map 8 EV019) only warps to 122 if the player holds
  `KELLYNLETTER`.
- That item's only grant is Bealbeach Ranger HQ (map 156 EV027), which also sets SW72.
- Bealbeach's gym door (101 EV003, page 2) only warps to the gym (102) once SW70 is on; SW70 is set
  in the plant (123 EV011).

Real order: Route 7 → Bealbeach + Ranger HQ (SW72, letter) → back to Route 7 → plant (SW70) →
Bealbeach gym (SW71 on 102 EV077). The generator would be asked for a letter from a chapter that
hasn't run.

### 4.2 Per chapter

| Chapter | Start gate → end gate | Verdict |
|---|---|---|
| CH11 Route 4 | SW62 (set on 66 in CH10) → SW63 set on 76; V106 local to 76; exit to 7 unconditional | ok |
| CH12 Comet Cave | partner-join autorun on 7 EV001; SW68 (96 EV011), SW66 (10 EV001) → exit to 142 | ok |
| CH13 Route 5 | no gate either side; only V116 (a sidequest local to 142); pass-through to 154 → Rochfale | merge candidate |
| CH14 Rochfale | 12 EV055 forces the lab (98); 98 EV004 sets V109 = 1 and SW34 | ok |
| CH15 Route 6 | V109 1→2 (22 EV026) → 4, 5 (105 EV001) → 6 (22 EV013). V109 = 3 never set. No forced bounce back to Rochfale | ok |
| CH16 Rochfale Tunnel | 8 events, no switch/var reads or writes; 22 EV061 → 17 → 17 EV005 → 8 | merge candidate |
| CH17 Route 7 | forced scene 8 EV015 sets SW69; ~26 of 74 events dormant (V120 ≥ 1, V123 ≥ 15, set later); map 8 is also CH20 | adjust (see 4.1) |
| CH18 Plant | SW74 (122 EV016) → V124 notebook count in 123 → SW70 (123 EV011) | adjust (see 4.1) |
| CH19 Bealbeach | ends SW71 (102 EV077) + 101 EV010 aftermath (V120 = 1, ferry ticket) → hands off to CH20 on Route 7 | adjust |

Otherwise the act is linear: 76 → 7 → 96 → 10 → 142 → 154 → 12 → 22 → 17 → 8, with no bounce
through the tunnel. No Act 3 story map is missing from the lists; 143 (Route 4 door) and 27
(Route 6 door) belong to later chapters.

### 4.3 Proposed adjustments (none decided)

1. **Fix the order:** move 156 into CH18 → CH18 = [156, 122, 123, 125] "Bealbeach arrival + plant";
   entry walks 8 → 101 → 156, back to 8, into the plant; ends on SW70. 156's existing revisit
   bindings (CH37, CH51) don't change. CH18 grows to ~130 events / ~2800 commands.
   *Alternative:* insert a new "Bealbeach arrival" chapter before the plant — cleaner, but
   renumbers every later `CHnn`.
2. **CH19 = Bealbeach city + gym, after the plant**, ending on SW71 + the 101 EV010 aftermath.
3. **Trim CH19:** drop metro stations 3 and 11 (unusable until CH54; Burole precedent) and orphan
   103. Optionally split out the Game Corner (52, 919 commands) and the elevator building
   (108/58, ~850 commands) as side content — neither feeds a story gate. After the move and trims
   CH19 is ~250 events / ~3700 commands.
4. **Merge CH12 + CH13** (Route 5 has no gate of its own; merged ≈ 91 events / ~1200 commands,
   still under CH10).
5. **Merge CH15 + CH16** (the tunnel is a pure connector; CH15 would end on arriving at Route 7).

Merges 4 and 5 either leave gaps in the numbering or renumber every later chapter; that cost is
shared with option 1's alternative.

---

## 5. Big chunks of work

Ranked. "Handled" means the transpiler/census already recognizes it. The census shows an empty
unhandled queue for every Act 3 chapter, but it only lists script heads it doesn't recognize at
all — it doesn't prove clean output for the ones it does.

1. **Heal-location crash on map 8 (CH17). Small, fix first.** Map 8 EV037 calls
   `pbSetPokemonCenter` from an autorun page (trigger 4). `transpile-events run --dry-run` dies in
   `heal_locations._mint_center_entries`: "staged call site (map 8, event 37) could not be
   resolved: trigger 4 is not Action Button". Any transpile staging map 8 fails.
2. **Bealbeach Game Corner (map 52, CH19). Largest single piece.**
   - Slots (`pbSlotMachine` ×12, EV11, EV19–29): native `playslotmachine` / `slot_machine.c`; no
     transpiler handler yet. Wiring.
   - Lottery (`pbLottery`, `pbSetLotteryNumber`; EV2–3): native `lottery_corner.c` + specials. Wiring.
   - **Voltorb Flip** (`pbVoltorbFlip` ×12, EV30–35): no engine equivalent (`grep -ri voltorb
     engine/` is empty). New C minigame screen, or a stub. Already an operator call in the command
     map (OQ-R4).
   - Coin prize counter (EV44, 45, 73): Ruby parallel arrays (`item=[...][pbGet(1)]`, `price=[...]`),
     `$PokemonGlobal.coins`, `pbSet`/`pbGet`, `Kernel.pbAddPokemon(pbGet(1),pbGet(4))`. A shape the
     transpiler has no mapping for.
   - Time-gated events: `pbSetEventTime` ×15, `pbGetTimeNow` (108 EV029) — unknown heads.
3. **Partner and two-opponent battles. Medium.**
   - Partner ally through Comet Cave (7, 96, 10): `pbRegisterPartner`/`pbDeregisterPartner`, plus
     `pbAddDependency2`/`pbRemoveDependency2` (follower). Engine has it natively
     (`BATTLE_TYPE_INGAME_PARTNER`, `setmultitrainerbattle ... partnerId`, follower-NPC macros);
     the transpiler has nothing (the dependency calls are stripped as noise). The command map marks
     it "RECHECK, likely C-light".
   - Two-opponent trainer battles: `pbTrainerBattle(..., true, ...)` double flag on 8 EV016/017 and
     101 EV075/076, the ninja pair on 142 EV035. The trainer idioms exclude
     `pbDoubleTrainerBattle`; the `true` branch is unverified.
   - Double wild battle (`pbDoubleWildBattle`, 8 EV046): native `setwildbattle` species2/level2.
   - Scripted wild battles are known to the census; the capture-or-blackout variant on 123
     (`!pbWildBattle(...)` + `nuzBlackout`) is a likely gap.
4. **Nuclear content (CH18). Medium–large, partly deferrable.**
   - Nuclear-type species in encounters (Tancoon, Gyarados, Trawpint Nuclear forms).
   - 12 Nuclear moves `blocked`, 5 abilities `inert` in `battle_rulings.json`; no Nuclear type in the
     engine.
   - Nuclear cure service (`pbChooseNuclearCurePokemon` + `party[i].nuclearFree = true`, 156
     EV072) needs a per-mon save bit (`reference/guides/nuclear_type_spec.md` §5.2) — a save-format
     change, so it belongs with the #153 save-across-builds decision.
   - Pokérus: `Kernel.pbPokerus?` is collapsed to false (`transpiler.py` ~840, "deferred to CH18");
     no Act 3 map actually infects.
   - `nextBattleNuclearHorde`: no Act 3 uses.
   - HAFLIBERRY on 122 (see §2).
5. **One-off Ruby calls. Small each, ~8.** `pbPunchBag` (178 EV001, a 313-line minigame; stub or
   port — deferred in `chapters.json`); `pbGenerateEgg(NUPIN)` (113; a non-starter egg shape);
   `pbGetStones` + `pbChooseAblePokemon` + `pbRaiseEffortValues` (52 EV064/073);
   `pbFlyAnimation` (22 EV013) and `pbMEStop` (142 EV035) — strip/map;
   `NeoCI.FossilRessurectionExample` (98 EV008; fossils are given on map 7) — revive analog
   unverified; `pbShowMap` (native region map), `pbHasSpecies`, `pbChoosePokemon`/`pbGetPokemon`
   (existing party-pick pattern).
6. **Art. Medium, mostly mechanical.** New RMXP tilesets 25 (CH13), 28 and 33 (CH17), 31 and 49
   (CH18), 10 and 38 (CH19). ~50 new overworld sprites (CH19 20, many `HGSS_*`; CH15 8; CH17 8;
   CH18 4). CH19 uses picture commands (231/232/235) and tone fades (223). Trainer classes to check
   against the mapping: COOLCOUPLE, SUPERSCIENTIST, RIVAL, PkMnRANGER, LEADER_Cali, NINJASURFERS,
   TRIATHLETE_*, HERO, GENTLEMAN, LASS.

**Dismissed:** gym 3 (102) has no puzzle — trainers, door warps (EV84–96) and teleport pads only. No
elevator or metro *scripting* found (the metro is blocked by gates, §2). No cave darkness/Flash or
ice in Comet Cave; its boulders (`pbPushThisBoulder`), cave entrance/exit, Surf, fishing, berries,
marts and phone rematches are all already handled.

---

## 6. Open questions — and which chapter each is due by

Nothing below blocks CH11.

| # | Question | Due by |
|---|---|---|
| Q1 | Merge CH12 + CH13? Renumber or leave a gap? | CH12 open |
| Q2 | Merge CH15 + CH16? | CH15 open |
| Q3 | CH18/CH19 order fix: move 156 into CH18, or insert a new chapter (renumbers)? | CH17 open (CH17's end state changes) |
| Q4 | Drop 3, 11, 103 from CH19; Game Corner / elevator building as side content? | CH19 open |
| Q5 | Voltorb Flip: build in C, or stub? Punch bag: port or stub? | CH17 (punch bag) / CH19 |
| Q6 | Partner battles through Comet Cave: build natively (recommended — the engine has it) or simplify? | CH12 open |
| Q7 | HAFLIBERRY on 122: strip the berry plant or rule the item? | CH18 open |
| Q8 | Nuclear cure save bit: build in CH18, or defer with #153? | CH18 open |
