# Slice 1 — FINAL Boot-Walk Checklist

**ROM:** `moki-slice1-final-db3b53f5.gba` — md5 `db3b53f55c938d3ebbf2e0511964e8f9`,
built 2026-08-03 from HEAD `2f914c33` (clean tree, full re-stage + `make modern`;
byte-identical to the 08-02 build, which is the evidence nothing was stale).

**Harness state: OFF.** No spawn override, no pre-set flags/vars, no granted
party. This is a genuine new game from `CB2_StartUraniumSlice` → Player's House
1F @ (7,7). The one thing still armed is `FLAG_BADGE03_GET` (see *Deliberate*
below).

**Chapter suite:** moki **GREEN 17/17, first attempt, fresh save**, on this exact
binary. So every mechanical gate below (`[auto]`) already passed headless — walk
them only as sanity, and spend your attention on the `[eye]` items, which the
suite structurally cannot see.

---

## RESULT — §9 gate PASSED, 2026-08-04

User completed this walk. Two real defects surfaced (both **general transpiler
bugs, not map data** — see `MEMORY.md` Last Session Summary 2026-08-04 for full
root-cause writeups) and were fixed in the same session:

1. **A3f-adjacent: Map032 rare-candy NPC printed a broken player-name string**
   (`\pn` case-sensitivity vs the charmap) — fixed, `_TEXT_SUBS` regex now
   case-insensitive.
2. **Post-ceremony (after A6): Map050 (14,16) permanently blocked** — a hidden
   NPC stayed solid after `set_invisible` (collision doesn't check `invisible`).
   Fixed via `_insert_terminal_hide_removeobject`; a follow-up respawn
   regression (NPCs reappearing after camera update, since the template's
   `flagId` was null) was caught and fixed in the next pass (`8b8bfed5`,
   "Hidden NPCs stop blocking their tile, and stop coming back").

All items below are marked passed on that basis — the two exceptions above were
the actual findings, both closed. No other `[eye]` item was reported as broken.
This doc is retained as the §9 certificate; it is not a live checklist.

---

## Preflight — do this first

- [x] **P1** — **Delete any existing `.sav` next to this ROM in your emulator.**
      A leftover save silently continues instead of starting a new game
      (`BOOT_WALK_CHECKLIST` §8 / SLICE1_TODO #22). This ROM is *pristine* —
      no stamped state blob — so a stale `.sav` is the one thing that can
      invalidate the whole walk.
- [x] **P2** — Don't save in-game mid-walk unless you want to resume; the boot
      path prefers a flash save over new-game.

---

## Part A — the story chain, in order, from boot

Walk it straight through. Suite-covered beats are tagged with their beat id.

### A1. Player's House 1F (Map 49)

- [x] **A1a** `[auto B1]` Boots straight into 1F — no Rayquaza intro, no title, no truck
- [x] **A1b** `[auto B2]` Leaving before talking to Auntie is refused with dialogue
- [x] **A1c** `[auto B3]` Auntie gives running shoes once; re-talk advances, no repeat gift
- [x] **A1d** `[eye]` Interior art + Auntie's palette; player walk/run animation clean all 4 ways
- [x] **A1e** `[eye]` Stairs to 2F — **post-warp facing** (should face away from the stairs, not down)

### A2. Player's House 2F (Map 48)

- [x] **A2a** `[eye]` Art correct, no NPCs (correct), stairs back down
- [x] **A2b** `[eye]` Post-warp facing on the way back down

### A3. Moki Town (Map 32) — first crossing

- [x] **A3a** `[eye]` Layout legible town-wide; tall grass covers feet; canopy draws over player
- [x] **A3b** `[eye]` Flowers animate (4 frames), pond animates; cadence not obviously wrong
- [x] **A3c** `[eye]` NPC movement reads right vs PC Uranium (wanderers wander, pacers pace, lookers turn)
- [x] **A3d** `[auto B4]` Theo's cameo fires once crossing the fence row, never refires
- [x] **A3e** `[eye]` **#15 — the choreography, not the trigger.** Does Theo actually
      *run up → talk → run ahead*? The suite only proves the trigger fired and state
      advanced. This is the beat most likely to be visibly incomplete.
- [x] **A3f** `[eye]` Rare-Candy woman gives it once (sheet HGSS_008 = young woman in a
      tank top; that IS Uranium's own data — only re-flag if PC Uranium differs)
- [x] **A3g** `[eye]` PC + region map work (both show Emerald versions — expected)
- [x] **A3h** `[eye]` East edge toward Route 03 blocks cleanly, no walking into void
- [x] **A3i** `[eye]` Dialogue town-wide: wrapped, no overflow, no overdraw

### A4. Professor's Lab (Map 50)

- [x] **A4a** `[auto B5]` **#14 re-verify** — entering the lab **autoruns** Bambo's intro
      (controls taken, player auto-walks). The 07-14 symptom was "only fires on A-press,
      then walks into black void." Confirm it does not reproduce at all.
- [x] **A4b** `[eye]` The auto-walk path is sane — no void, no wall clipping
- [x] **A4c** `[auto B6/N3]` Aptitude-test Yes/No prompt; answering **No** re-offers cleanly
- [x] **A4d** `[auto B7]` **Yes** → 4-question quiz, each a real 3-option menu
- [x] **A4e** `[eye]` **Answers steer the result.** Suite runs one answer path; by eye,
      confirm the "Go! \<starter\>!" line matches the pick (`STARTER_QUIZ_ANSWERS.md`)
- [x] **A4f** `[auto B8]` Interacting with the Machine grants the starter, named, in the party
- [x] **A4g** `[eye]` **#26/#27** — the ball machine prop **animates** (multi-state), the
      starter's sprite appears exactly once (no double pop-up), ball/starter gfx swaps land
- [x] **A4h** `[auto B9]` Theo's rival battle fires straight out of the machine scene
- [x] **A4i** `[eye]` **#29 — NEW, never walked.** Theo's **in-battle trainer sprite is
      Uranium's**, not a stock Emerald Youngster. Colors sane, not garbage.
- [x] **A4j** `[eye]` Battle is losable: **walk the LOSS path too** — no white-out, no
      freeze on Theo's last line, party auto-heals either way, Theo leaves the lab
- [x] **A4k** `[eye]` Lab art + every NPC palette by eye (silent-failure risk: shared banks)
- [x] **A4l** `[auto B10]` Lab exit stays shut until the quest var advances, then opens

### A5. Theo's House (Maps 172 / 89)

- [x] **A5a** `[auto N2]` Skipping Theo's house → redirect dialogue, and **no state advances**
- [x] **A5b** `[auto B11/B12]` Door always open; entering 1F autoruns the PokePod scene
- [x] **A5c** `[eye]` Theo is **visible** for the scene on **both** the win and loss paths
- [x] **A5d** `[eye]` 1F art + NPCs; does the room read *complete*? (staging dropped 6
      non-emitted pages here)
- [x] **A5e** `[eye]` **Map 89 (2F) — NEVER WALKED.** Stairs up, art, NPCs, stairs back down

### A6. The west-exit ceremony + capture tutorial (Map 32)

- [x] **A6a** `[auto B13]` Crossing the west-exit tiles plays the ceremony
- [x] **A6b** `[eye]` Cast is present and choreographed (professor, rival, aide, starter);
      no wrong-sprite actors; the `!` emote pops where expected
- [x] **A6c** `[eye]` The **ball throw** reads correctly — this is the audit's own
      verification scene, now fully machine-generated
- [x] **A6d** `[eye]` Pokédex + 5 Poké Balls granted; Pokédex opens and is sane
- [x] **A6e** `[auto B14]` Re-crossing the tiles does **not** refire the scene
- [x] **A6f** `[auto B15]` Terminal state persists; Route 01 is correctly out of scope

---

## Part B — the two houses nobody has ever walked

**Maps 64 and 65 have been built since 2026-07-14 and never looked at.** Highest
odds of a silent art/palette failure in the whole slice.

- [x] **B1** `[eye]` House 1 (Map 65, door at 24,42): art, residents' colors, dialogue, exit
- [x] **B2** `[eye]` House 2 (Map 64, door at 43,31): art, residents' colors, dialogue, exit

---

## Part C — cross-cutting sweep

- [x] **C1** `[eye]` **Warp round-trips.** Every door you enter, exit again — arrival tile
      and facing sane in both directions
- [x] **C2** `[eye]` **Palette sweep across all 5 interiors.** Converted sheets share ≤4
      banks; overflow is silent color garbage with no build error. The eye is the gate.
- [x] **C3** `[eye]` Depth ordering anywhere it matters — nothing drawn behind a wall it
      should be in front of, or vice versa
- [x] **C4** `[eye]` Post-chain sanity: Auntie/Rare-Candy dialogue unchanged, warp facings
      unchanged, nothing regressed behind you

---

## Not implemented — do NOT report these

**Provenance note (2026-08-04):** `SLICE1_TODO.md` retired to
`reference/archive/`; its item numbers below are unchanged (file moved, not
deleted) but live tracking of each has moved on: #7→`PROJECT_TODO.md` #22,
#9→`SLICE2_TODO.md` #3, #28 §5.5→`PROJECT_TODO.md` #17, #28 §5.6→
`PROJECT_TODO.md` #18. #8 (door animations) has no live tracker — it's a
scoped-and-deferred content-fidelity call, see
`reference/guides/event_conversion_model.md` "Deliberately not used".

**Known open items (tracked in SLICE1_TODO):**
- **Audio** — every RMXP BGM/SFX is a comment; stock Emerald plays everywhere (#7).
  The slice-1 audio bar is still your call, not a bug.
- **Door animations** — every warp is a plain door; doors don't animate open, stairs
  and mats behave as doors (#8)
- **Rock smash is NOT testable in this build** — the standing Geodude+Rock-Smash grant
  has been off since 2026-07-21 (it was disabled to test the losable rival battle, and
  a granted second mon would distort that battle). The rocks are there; you have nothing
  that knows the move. Say the word and I'll re-arm it for a follow-up ROM.
- **EV005 door** in Moki Town — dest never wired, inert wall by design
- **Cave entrances** (3, NE) → Route 01/33 — slice-2 frontier, blocked by design
- **Route 03 east seam** — connections unconverted engine-wide (#9); the edge should
  simply block
- **`MB_COUNTER` not emitted** (#28 §5.6) — talking across a counter behaves as a wall
- **Cutscene `applymovement` routes don't check collision** (#28 §5.5) — only page-level
  ambient routes are simulated. A scripted actor can walk through something.

**Engine/pipeline limits accepted for slice 1:**
- Boot-page static: a page change swaps the SCRIPT only — an NPC's graphic, visibility
  and movement never change mid-visit (except where a script explicitly calls the new
  `setobjectgfx`)
- Pond-adjacent reflections are over-eager (engine-native wide scan; narrow-scan fix
  rejected 2026-07-07)
- Generic `YES`/`NO` menu labels where Uranium had custom wording

**Deliberate / test rig:**
- New game silently sets **Badge 3** (`FLAG_BADGE03_GET`) — leftover of the HM rig
- MALE player hardcoded; HEROINE not converted
- Bike/surf/fish poses are still Emerald Brendan (none reachable in slice 1)
- Ninja letter absent — gated on later story state, correctly

---

*Feedback: item ID + one line each is ideal ("A4i: Theo's sprite is magenta").
Per-cell art problems: flag them in the map viewer (`reference/map_feedback/`).
Findings get logged into `SLICE1_TODO.md` #11.*
