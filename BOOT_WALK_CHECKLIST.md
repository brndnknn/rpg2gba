# Slice 1 Boot-Walk Checklist — ROM built 2026-07-14

Companion for walking the 8-map slice (49/48/32 + new interiors 50/64/65/172/89).
Everything listed **should work** in the taildropped ROM. Check boxes as you go;
give feedback by item ID — "L4: machine invisible", "T2: room feels empty" is
plenty. Art problems on specific cells: flag them in the map viewer
(`reference/map_feedback/`). Findings land in `SLICE1_TODO.md` #11 as usual.

The **Not implemented** list at the bottom is what NOT to report — known gaps,
deliberate deferrals, and test-rig behavior.

---

## 0. Boot & player — B

- [X] **B1** — Boots in mGBA; no Emerald intro/truck; spawn in Player's House 1F
- [X] **B2** — New game silently grants Badge 3 + lv5 Geodude with Rock Smash — *deliberate test harness, not a bug*
- [X] **B3** — Player is the Uranium hero; walk animation clean in all 4 directions
- [X] **B4** — Run (hold B after getting running shoes) works; run animation clean

## 1. Player's House 1F — Map 49 — H

- [X] **H1** — Interior art correct (real Uranium tiles)
- [X] **H2** — Auntie gives running shoes ONCE; talking again advances to later dialogue, no repeat gift
- [ ] **H3** — Ninja letter reads as scrolling text boxes **Comment** Ninja letter doesn't exist yet, i think its probably part of something later in the game, or atleast not before the character gets their first pokemon
- [X] **H4** — Stairs warp to 2F **Comment** technically works but player is shown facing down when they should be facing way from the stairs. so in the players home they should be facing right after the warp to 2F and left after the warp to 1F but in both cases they face down. 
- [X] **H5** — Exit to Moki Town (tile below the rug; rug itself inert + arrival above it = faithful Uranium data)
- [X] **H6** — All 4 NPCs static — correct, they don't move in Uranium either **Comment** the aunt character is static and shes the only npc that should be there at the beginning of the game. the other characters must be for returns later in the story line

## 2. Player's House 2F — Map 48 — U

- [X] **U1** — Art correct
- [X] **U2** — No visible NPCs (correct)
- [X] **U3** — Stairs warp back to 1F

## 3. Moki Town — Map 32 — M

- [X] **M1** — Art + layout legible town-wide
- [X] **M2** — Flowers animate (4 frames); pond water animates
- [X] **M3** — Collision sane: no walk-through-walls, no stuck-on-walkable cells **Comment** generally works other than issue with Pokedex ceremony, see description below
- [X] **M4** — Tall grass covers feet; tree canopy draws over player
- [ ] **M5** — NPC movement: Chyinmunk + Barewl wander; pacers (the left-right walkers) patrol; lookers turn in place. *Exact range/cadence vs PC Uranium = open fine-tune (#12), just note anything that feels badly off* **Comment** see map viewer export for notes on the issues with this. 
- [X] **M6** — Granny gives Rare Candy ONCE; dialogue advances after **Comment** This works, but sprite doesn't look like granny.
- [X] **M7** — Rock smash: 3 rocks smashable with Geodude; break animation plays; rock stays gone while on the map (re-forms on re-entry = faithful)
- [X] **M8** — PC works; region map item works **Comment** PC and map both work, show emerald versions. 
- [ ] **M9** — Pokédex ceremony (professor event): plays through, starter choice registers ("Go! <starter>!" matches pick), Pokédex granted. *Ball/starter sprites do NOT swap during it (known gap #6) — verdict: does the scene read acceptably anyway?* **Comment** some issues here for sure but we'll focus on the issues with the main map to start. 
- [ ] **M10** — Emotes (! / ?) pop over NPCs where expected **Not sure where/when this should happen
- [X] **M11** — East edge (toward Route 03): blocked cleanly, no walking into void
- [X] **M12** — Dialogue town-wide: readable, wrapped, no overflow/overdraw

### NEW doors — the point of this build

- [X] **M13** — Lab door (17,11) enters Map 50
- [X] **M14** — House-1 door (24,42) enters Map 65
- [X] **M15** — House-2 door (43,31) enters Map 64
- [X] **M16** — Theo's door (56,42) enters Map 172
- [ ] **M17** — Cave entrances (3, NE) + ONE remaining door (EV005) still inert — *expected, see gap list* **Comment** no Idea where this is supposed to be, I don't even see it on the map viewer

## 4. NEW — Professor Lab, Map 50 — L

**Comment** visually the lab looks fine, but the pokedex ceremony is supposed to start as soon as you walk in the door. in PC Uranium the game takes the controls and the place auto walks to stand next to theo and the prof starts his speech. in the current ROM build the event isn't triggered until the player walks all the way up to the tile infront of the prof and presses A. the player is then auto walked up until it's in a black void and the prof starts his speech at that point. 

- [ ] **L1** — Art + palettes look right by eye (biggest silent-failure risk: NPC colors)
- [ ] **L2** — NPCs render with correct colors + sane placement
- [ ] **L3** — Ball machine prop renders (64×64 — first use of new sprite class)
- [ ] **L4** — NPC dialogue readable
- [ ] **L5** — Exit returns to town just outside the lab door

## 5. NEW — House 1 (Map 65) — N1 / House 2 (Map 64) — N2

- [X] **N1a** — House 1: art + residents' colors
- [X] **N1b** — House 1: dialogue
- [X] **N1c** — House 1: exit back to street
- [X] **N2a** — House 2: art + residents' colors
- [X] **N2b** — House 2: dialogue
- [X] **N2c** — House 2: exit back to street

## 6. NEW — Theo's House 1F (Map 172) / 2F (Map 89) — T

**Comment** for Theo's house everything looks as it should for the first visit, it matches what PC Uranium has. 
- [X] **T1** — 1F art + NPCs
- [X] **T2** — 1F: anything obviously MISSING? (staging dropped 6 non-emitted event pages here — want eyes on whether the room reads complete)
- [X] **T3** — Stairs up to 2F
- [X] **T4** — 2F art + NPCs
- [X] **T5** — Stairs back down + street exit

## 7. Cross-cutting

- [X] **X1** — Every new interior: NPC/sprite colors by eye (all sheets share ≤4 palette banks; overflow = silent garbage, no build error)
- [X] **X2** — Audio: note what plays where (stock Emerald / silence). Nothing is converted — this is the #7 "what's the slice-1 audio bar" decision, not a bug report **Comment** Emerald music plays
- [ ] **X3** — Warp round-trips: every door you enter, exit again — arrival tile sane both directions

---

## 8. Moki story chain — ROM `762e98aa` / `5dd32b10` / round-3 `c9128e58` (2026-07-17) — S

> Round-3 walk (`c9128e58`): postgame Theo "Champion" misfire by the player's
> house is GONE (EV080 base-page gate fix); S1–S5 pass. Frontier = S6 —
> answering YES to the aptitude test.

> `5dd32b10` (taildropped 2026-07-17) is `762e98aa`'s slice data relinked with
> the committed embedded-save boot branch. One behavior note for the walk:
> **if you save in-game, the next boot CONTINUES that save** (new, intended).
> For a fresh start-of-chain walk, delete the ROM's save in your emulator
> first, or just don't save mid-walk.

The early-game event chain end to end (findings doc
`reference/findings/moki_slice_story_chain_2026-07-16.md` §2.1 beat list; bugs
A/B/B'/C/D fixed 2026-07-17, then the lab-intro loop + trip-tile round-2 fixes).
Walk it in order on a fresh save.

- [X] **S1** — Auntie gives running shoes; quest log var advances (same as H2, start of chain)
- [X] **S2** — Theo trip tile: walking beside the fence at column 26 (the tile row just above or below the blocked fence cell at (26,12)) fires the Theo run-up scene ONCE; never refires afterward
- [X] **S3** — Lab intro autorun: fires as soon as you enter the lab (no talk needed), player auto-walks to position — sane path, no black void, no wall clipping
- [X] **S4** — Test prompt at end of intro: YES/NO box appears (labels are generic YES/NO — the custom "Yes!"/"Wait a minute..." wording is a known cosmetic loss, don't report). **Either answer ends the scene cleanly — NO refire, no wall-walk loop**
- [X] **S5** — Answered NO ("wait"): walk away and talk to the professor again — he re-offers the test
- [ ] **S6** — Answered YES: aptitude test Q&A plays — 4 questions, each a real 3-option menu; answers steer the result; starter granted matches the outcome and is NAMED (Emerald stand-ins by decision: TREECKO/TORCHIC/MUDKIP for the Orchynx/Raptorch/Eletux lines); Theo's counter-pick announced by name. Retake path: answer NO, re-talk, YES → skips straight to the questions. *(No Pokédex here — Uranium grants it later, not in this event; rival battle intentionally still skipped — known gap.)* — retest on ROM `6e85edb3`
- [ ] **S7** — PokéPod scene in Theo's house 1F: fires on entry after the lab visit, advances the quest chain (var 101 → 2)
- [ ] **S8** — Ceremony at the town's west exit: trigger fires when crossing the exit path tiles (relocated to (17,42)/(16,43) — the original trigger tile was unreachable); correct NPCs are present and choreographed (professor, rival, aide + starter); no wrong-sprite actors
- [ ] **S9** — Ceremony completes: quest log → 4, scene never refires on re-entering the area
- [ ] **S10** — Post-chain sanity: rocks still smashable/respawn, Auntie/granny dialogue unchanged, warp facings unchanged (no regressions from the story-chain rework)

## Not implemented — do NOT report these as bugs

**Known gaps, open items (tracked in SLICE1_TODO):**
- Audio — all RMXP BGM/SFX stripped; stock Emerald or silence plays (#7)
- Door animations — every warp behaves as a plain door; doors don't animate open, stairs/mats act like doors (#8)
- Live sprite swaps — Pokédex ceremony ball/starters don't change graphics (#6); the 12 Luz light props don't flicker (same limitation)
- Auntie's RAPTORCH dialogue branch — one branch of her dialogue silently absent (blocked on Uranium species constants, #2)
- NPC movement fine-tuning — ranges/timing not yet matched eye-to-eye vs PC Uranium (#12)
- EV005 door in Moki Town — dest never wired this round, inert wall
- Cave entrances → Route 01/33 — slice-2 frontier, blocked by design
- Route 03 east seam — connections unconverted engine-wide (#9); edge should just block

**Engine/pipeline limits (accepted for slice 1):**
- Boot-page static: page changes swap the SCRIPT only — NPC graphics/visibility/movement never change mid-visit
- Pond-adjacent reflections over-eager (engine-native wide scan; narrow-scan fix rejected 2026-07-07)

**Deliberate / test rig:**
- Badge 3 + Geodude + Rock Smash at new game — standing HM test harness (kept indefinitely per #5 decision)
- MALE player hardcoded; HEROINE not converted
- Bike/surf/fish player poses still Emerald Brendan (none reachable in slice)
- Ninja letter = scrolling text, not the bespoke card UI (Phase-8 candidate)

---

*Feedback: item IDs + one line each is ideal. New findings get logged into
`SLICE1_TODO.md` #11 by the build agent.*
