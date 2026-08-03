# Hand-conversion audit and remediation plan (2026-07-31)

**Status:** audit complete, nothing remediated yet. Triggered by a PC playthrough
of the Moki lab chapter that found three defects our ROM shipped and nothing in
the pipeline flagged.

**Scope:** every entry in `reference/findings/hand_bucket_queue.jsonl` and every
file in `src/rpg2gba/conversion_agent/hand_conversions/`, plus the corpus-wide
gaps the audit exposed.

---

## 1. What the playthrough found

Three defects in the Map050 (Professor's Lab) starter scene, all shipped:

1. A cutscene plays when the player receives their starter. We convert none of it
   and never queued it.
2. The player and Theo end up a tile lower than they should before the rival
   battle. Both should stand where they started; both should walk to the tile
   directly in front of the machine.
3. A large amount of post-battle dialogue is missing.

All three trace to one root cause: **Map050 EV019 was hand-converted without
justification.**

---

## 2. Root cause — the ledger authorized it with an empty evidence box

`hand_bucket_queue.jsonl` line 6:

```json
"reason": "hand_conversions/Map050_EV019.pory; backfilled 2026-07-25
           per ROM_TEST_DEV.md E1 — PENDING RETIREMENT, see evidence",
"evidence": {"greps": [], "decomposition_attempted": "",
             "decomposition_failed_because": "", "legacy_unaudited": true}
```

It says "see evidence" and there is no evidence. It is flagged `PENDING
RETIREMENT` — the doubt was recorded at backfill time and overridden.

Contrast line 5 (Map050 EV005, the aptitude test), which is what a justified
hand conversion looks like: three greps against the fork, a four-part
decomposition, and a specific argument that a 4-deep tally feeding an argmax
with tie-break overrides is irreducible *by shape*, not by capability.

`load_queue_jsonl` raises on a `hand` entry with a blank evidence box — but only
**warns** when `legacy_unaudited: true`. The flag meant to mark an audit backlog
became a permanent exemption. Two entries use it; both are unjustified.

### The stated trigger did not warrant it

The `reason` field names exactly one blocker: a `canlose` `pbTrainerBattle`
inside a code-111 conditional-on-script. That was a genuine transpiler gap —
roughly **4 nodes out of 257**. The correct response was to teach the transpiler
`trainerbattle_earlyrival` and leave the other 250 commands machine-generated.
The file's own header concedes the point: *"Base content is verbatim transpiler
output; deltas: …"*. The transpiler **did** transpile this event. Hand
conversion was not a necessity, it was a convenient place to put edits.

---

## 3. The two defects in `Map050_EV019.pory`

### 3.1 Dialogue loss — 37 source strings, 18 emitted

Source page 0 is 257 commands. The win branch (cmds 107–172) carries ~13 message
boxes; we ship one. The lose branch (cmds 175–231) carries ~9; we ship one.

Lost content includes a **three-box type-matchup tutorial** (cmds 144–146, and
again at 208–211 on the other branch) — a game mechanic taught to the player, not
flavour text — plus an on-screen heal, Theo's exit dialogue, and the professor's
closing beats.

The 2026-07-21 note in the file documents mapping both RMXP branches onto
`trainerbattle_earlyrival` and observes the scene "converges either way". That is
true of *control flow*. It was treated as content-equivalence, and the 22 lines of
dialogue living inside those branches were never recovered.

### 3.2 Positioning — a correct conversion was overwritten by hand

The source gives Theo two separate move routes after his pick:

```
cmd 54: [move up]
cmd 56: [Through ON, move up]     -> (14,8) -> (14,7) -> (14,6)
cmd 59: player [move left, move down, move down, turn up]
```

Theo reaches (14,6), the tile in front of the machine, stepping into the tile the
player vacates in the same frame batch — which is what the Through-ON flag is
there for. Both actors then square up.

The committed version (`e4561b07`) had this **right**: `Move4` and `Move5` each
carried one `walk_up`, and the player's `Move6` was `walk_left, walk_down,
walk_down`. Faithful to source.

The on-screen symptom was real, but its cause was that **two back-to-back
`applymovement` calls on the same object with no intervening `waitmovement` are
dropped by the engine** — a corpus-wide transpiler bug (§5.2). It was instead
diagnosed as a map-geometry anchor mismatch: `Move5` was deleted, and a third
`walk_down` was added to the player's route to compensate. Theo's half came out
accidentally correct; the player gained a step the source never had. That extra
step is defect #2 from the playthrough.

### 3.3 The findings doc must be retracted, not amended

`reference/findings/lab_starter_scene_positioning_2026-07-27.md` argues Uranium's
anchor is (14,7) and ours is forced to (14,6). This is wrong, and the reasoning is
circular: the Through-ON evidence it cites as proof of a (14,7) anchor actually
proves Theo ends at (14,6). The arithmetic only closed at (14,7) because the
second of Theo's routes had already been dropped.

Its §4 states plainly that the mechanism was unreachable and the question open.
The fix shipped through the §9 review gate anyway. That is the process failure —
not a missing tool.

**Retained from that doc** (both findings stand, tracked in §5.5 and §5.6): §6.1
scripted-route collision stalls, §6.2 the discarded counter bit, and §7 that the
harness has never read `gObjectEvents`.

---

## 4. Map032 EV009 (Pokédex ceremony) — misplaced, not wrong

Its evidence box is populated and `legacy_unaudited: false`. Its greps are
accurate: the fork genuinely has no script-callable live graphics swap. But its
decomposition verdict is —

> "no single native shape covering all of it; only sub-pieces matched existing
> native shapes -- the whole event does not"

— **the wrong bar.** The transpiler emits command by command and never needs one
native shape covering a whole event. No event in the corpus has one. Stated that
way, the test justifies hand-converting anything.

The seven hand-authored deltas from the file header:

| # | Delta | Actually is |
|---|---|---|
| 1 | `$game_player.x==17` guard → `getplayerxy` + early exit | idiom pattern; hand-copied across 3 pages |
| 2 | `$game_player.y<=43` reposition → walk route | idiom pattern |
| 3 | var-151 starter readback → `copyvar` + clamp + per-branch text | idiom pattern — **the same one hand-authored again in EV019** |
| 4 | `$Trainer.pokedex=true` → `setflag(FLAG_SYS_POKEDEX_GET)` + `special(SetUnlockedPokedexFlags)` | one-line table entry (§4.7 native-analog ledger) |
| 5 | change-graphic move routes | **deferred, not solved** (file lines 99, 142) |
| 6 | anim 104 → exclamation, anim 18 → dropped | table |
| 7 | step-forward/backward → `walk_in_place_right` | table |

Four table entries, two idiom patterns, and the one blocker that supposedly
justified the whole thing was punted on. 331 lines hand-authored around a gap it
did not close.

**Its text is intact** (38 source strings → 37 emitted), so this is not urgent.
It retires once §5.1 lands.

---

## 5. Remediation plan

### 5.1 Expose live sprite swap (move-command 41) — tier 3

> **DONE 2026-08-02.** `RPG2GBA_SetObjectEventGfx` (`engine/data/specials.inc:646`,
> implemented in `engine/src/event_object_movement.c`), the `setobjectgfx` macro in
> `engine/asm/macros/event.inc`, the transpiler rule
> (`transpiler._emit_route_with_gfx_swaps`), and the sheet→constant table
> (`reference/npc_gfx_map.json`). **Verification scene BOOT-WALKED 2026-08-02 on
> ROM `e0f6d30f` — PASSED** ("Theo spawns and the capture tutorial works as
> expected"). Remaining, corpus-wide rather than per-item: the table covers the
> sheets the slice uses, so the other 36 census maps' sheets are unmapped until
> their art is converted, and a *pattern*-moving swap on an ordinary walk-cycle
> sheet still queues by design.

RMXP move-command 41 repaints an event's sprite in place mid-scene. Emerald
resolves an object's sprite at spawn only.

**Census: 1,115 occurrences across 499 events in 44 maps.** Top: Map071 (244),
Map212 (131), Map052 (80), Map040 (74). Currently dropped everywhere as
`# UNHANDLED code 209 ... codes [41]`.

The engine function already exists and does exactly this —
`ObjectEventSetGraphicsIdByLocalIdAndMap`, `engine/src/event_object_movement.c:3164`.
Nothing exposes it to scripts (no macro in `asm/macros/event.inc`, no entry in
`data/specials.inc`). Work: a `def_special`, a macro, a transpiler rule for
move-command 41, and an RMXP-graphic-name → `OBJ_EVENT_GFX_*` mapping. Additive
to the engine; does not change baseline pokeemerald behaviour. Still fork work —
confirm scope with the user per CLAUDE.md §10.

**Verification scene:** Map032 EV009 page 2. Cmds 52/60/68 repaint event 77 to
the professor's starter (branching on the player's choice); cmd 106 repaints
event 76 to `PU-POKEBALL` for the ball throw. Today the throw plays its full
sound sequence — throw, three `ballshake`, `balldrop` — while the wild sprite
stands there and then vanishes. No ball ever appears on screen.

**Why Emerald's own catching tutorial is not a substitute.** Emerald's is 20
lines of script (`engine/data/maps/PetalburgCity/scripts.inc:31`) because the
catch is one `special StartWallyTutorialBattle` into a real battle, backed by
`battle_setup.c:466`, `BATTLE_TYPE_CATCH_TUTORIAL`, and an entire dedicated
battle controller (`battle_controller_wally.c`, ~400 lines). It is hardwired to
`SPECIES_RALTS` at level 5, swaps the player's party out, and requires the player
to sit in an interactive battle. Uranium's scene is 224 overworld commands, a
different species, a different catcher, and non-interactive. Retargeting one onto
the other is a §10 fidelity *substitution*, not a conversion. The puppet-theatre
route converts exactly — Emerald can already do every individual beat; the only
missing verb is "repaint that sprite".

> **General law worth keeping:** RPG Maker puts the complexity in the event;
> Emerald puts the complexity in C. Essentials has no battle system worth using
> for Pokémon, so it stages these scenes as overworld puppet theatre and the event
> balloons. Emerald's script language is thin because anything hard is a `special`.
> Same screen time, opposite architectures.

### 5.2 Fix dropped back-to-back `applymovement`

Two consecutive `applymovement` calls on the same object with no intervening
`waitmovement`: the engine drops the second as already-in-flight. RMXP authors
consecutive code-209 routes on one target routinely.

Prefer **merging** consecutive routes on the same target into a single movement
block over inserting a `waitmovement` — merging preserves RMXP's semantics (one
continuous motion); a wait inserts a beat that was never authored. Then sweep the
corpus for other instances.

### 5.3 Source→emitted dialogue census as a build-time check

Nothing compares source event text to emitted script text. Count code-101/401 per
source event against emitted `msgbox` + text blocks, report the ratio, fail loud
past a threshold. Code-401 continuation lines legitimately merge into one
`msgbox`, so the check must model that rather than demand 1:1.

Measured baselines:

```
Map032 EV009:  38 -> 37   complete
Map049 EV021:  18 -> 16   fine (401 merges)
Map050 EV005: 102 -> 60   quiz; multi-page branching, needs a look
Map050 EV019:  37 -> 18   the known loss
```

**This must cover hand-conversion files.** `hand_overrides` splices them in
verbatim and "runs no further processing" (`hand_overrides.py:63`), so today they
are exempt from every coverage mechanism the deterministic corpus has. Its
`_validate` checks namespace hygiene only — label collisions, not content.

### 5.4 Raise the bar; close the `legacy_unaudited` hatch

Replace the justification test. **New bar: "is the blocking construct unique to
this event, or did I just meet it here first?"** A corpus census of the blocking
construct is mandatory evidence before anything is bucketed `hand`. EV009 fails
this test 499 times over.

Make `load_queue_jsonl` raise on `legacy_unaudited` entries instead of warning,
and audit or retire both users of the flag.

Document in CLAUDE.md §4.1 and the `hand_conversions/` README:

> Hand conversion is the only tier whose cost never amortizes. An idiom rule or an
> engine primitive is paid once and serves every instance in the corpus. A hand
> file buys exactly one event and must be maintained by hand forever — and, unlike
> a transpiler gap, it fails silently: a queued `UNHANDLED` line is countable, a
> hand-authored approximation reads as finished.

**The tiers, for reference.** An "idiom" is not something Emerald can't do — it is
something Emerald *can* do, written in a shape the transpiler doesn't recognise
yet. The work is Python-side pattern matching, zero engine work.

| Tier | What's hard | Where the work goes | Cost |
|---|---|---|---|
| 1 Straight | nothing — 1:1 map | table entry | trivial, reusable |
| 2 Idiom | meaning is in the *cluster*, not any one command | matcher in `deterministic.py` | one rule → every instance |
| 3 Engine gap | Emerald lacks the primitive | C + macro/special + transpiler rule | one patch → every instance |
| 4 Hand | control flow unrecoverable from the flattened stream | a `.pory` file, forever | **one event, never amortizes** |

Tiers 2 and 3 are independent. The failure in both EV009 and EV019 was routing a
tier-2 or tier-3 problem to tier 4.

### 5.5 Model scripted-route collision stalls

(From the retracted doc §6.1 — not the cause of the positioning bug, but real.)

RMXP stalls a move route when the destination is blocked. `route_sim.py` and
`MovementType_UraniumCustomRoute_Callback` model this only for page-level ambient
routes (`move_type == 3`). Embedded cutscene routes compile to vanilla
`applymovement`, whose `walk_*` actions never check collision
(`InitNpcForMovement`, `engine/src/event_object_movement.c:7287-7305`). Uranium
leans on the "walk N tiles, stop when you bump into someone" idiom — Map050 EV005
page 0 marches the player `move_up` ×10 — so any such route can land a different
tile on GBA than in RMXP.

Extending `route_sim` to cutscene routes also enables a build-time, corpus-wide,
no-emulator diff of RMXP-simulated vs Emerald-simulated endpoints per actor.

### 5.6 Emit `MB_COUNTER`

(From the retracted doc §6.2.)

`tileset_converter/tile_map.py:50-53` masks RMXP passages with `0x0F` and
dismisses the high bits as "non-collision flags". The counter bit is `0x80`.
Nothing emits `MB_COUNTER`, so counter-reach is lost everywhere it appears.

The engine supports it natively, zero custom C: `MetatileBehavior_IsCounter`
(`engine/src/metatile_behavior.c:490`) is consumed by
`GetInteractedObjectEventScript` (`engine/src/field_control_avatar.c:400-409`),
which looks one tile beyond a counter for the object event to interact with.
Collision is **not** derived from the behaviour — a counter metatile must also
carry a non-zero collision bit to block.

### 5.7 Retire the two hand conversions

- **Map050 EV019** — retire, restoring the lost dialogue and reverting the
  player's invented `walk_down`. Blocked on §5.2 for a clean result.
- **Map032 EV009** — retire once §5.1 lands. The var-151 readback idiom should
  become a shared transpiler rule serving both events.

> **Both DONE.** EV019 2026-08-01 (`d5ae2e3e`), EV009 2026-08-02 — seven deltas
> into four table entries and three idioms, 35 source message units → 37 msgbox,
> 0 queue entries. **EV009 boot-walked 2026-08-02 (ROM `e0f6d30f`) — PASSED.**
> EV019's scene rode the 2026-08-02 lab-scene pass on `36cdee71`; its restored
> win/lose dialogue has not been read on device end to end.

Retained in the hand bucket: **Map050 EV005** (aptitude test — genuinely
irreducible by shape) and **Map049 EV021** (letter — endgame, deprioritised by
the user).

> **EV005 was retired anyway**, 2026-08-01 (`edbec873`) — its "irreducible by
> shape" claim disproved by censusing the three constructs behind it (RMXP
> label/jump hoist, array-valued vars, the shared `pbStarterSelector` emitter).
> `hand_conversions/` now holds **Map049 EV021 only**.

---

## 6. Still open

- **Map049 EV020** — the other `legacy_unaudited: true, greps: []` entry. Has a
  ledger entry but **no file** under `hand_conversions/`. Never discussed. Needs
  the audit EV019 just got.
- **Map050 EV005** — 102 source strings → 60 emitted. The hand bucket is justified
  here, but that ratio needs explaining; multi-page branching may account for it.
- **`pbStarterSelector`** — the EV019 header calls it "presentation-only" and
  substitutes a text box. Nobody opened it. The playthrough reports an
  unconverted cutscene at this point. Read it in the Uranium source and confirm
  or correct.
- **Harness cannot see NPCs** — nothing in `src/rpg2gba/playtest/` has ever read
  `gObjectEvents`, so it knows the player's position and nothing about any other
  actor. The symbol is in the linker map (`engine/pokeemerald.map:5142`,
  `OBJECT_EVENTS_COUNT` = 16); only struct field offsets need probing into
  `offsets.py`. Would turn this bug into a one-line assertion: *Theo and the
  player are orthogonally adjacent and facing each other.*
- **Contact sheets capture the wrong frame for geometry.** The 2026-07-27 change
  lands frames on the dialogue moment, which is right for text and wrong for
  positioning — the stagger shows in the *aftermath*. Beats that move NPCs want
  both frames.

---

## 7. One-line summary

An under-justified bucket assignment produced all three defects the playthrough
found. The queue entry predicted it — `PENDING RETIREMENT`, empty evidence — and
a `legacy_unaudited` flag let it ship anyway.
