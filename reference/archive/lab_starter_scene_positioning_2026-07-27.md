**SUPERSEDED 2026-08-04 — rebuilt and boot-walked since (slice 1 §9 gate passed). §4's open mechanism question migrated live to `PROJECT_TODO.md` #26. Archived, not live.**

# Map050 starter scene — actor positioning drift (2026-07-27)

**Status:** fix applied in source, **not yet rebuilt or boot-walked**. One question
left open, to be settled by a PC playthrough of the chapter (checklist in §5). **[Stale status line — rebuilt+walked since; see stamp above.]**

**Scope:** Map050 (Professor's Lab), the starter-selection + rival-challenge scene.
Source events: `EV005` "Bambo" page 0 (autorun intro) and `EV019` "Machine" page 0
(action-button, carries the whole starter/rival cutscene). Both are hand
conversions: `src/rpg2gba/conversion_agent/hand_conversions/Map050_EV005.pory`,
`…/Map050_EV019.pory`.

---

## 1. Reported symptom

From a boot-walk of the built ROM:

- The player picks a starter from the machine.
- Theo then walks up to pick his — but **stops one tile short** of standing
  directly in front of the machine.
- Theo walks back to challenge the player, covering the correct number of steps
  *as if he had been standing on the machine-adjacent tile*.
- Net result: the two end up **diagonal** — player one tile up-and-left of Theo —
  instead of squared up side by side.

---

## 2. Mechanism

The scene is **pure relative-delta choreography**. Verified by dumping
`output/uranium-build/maps/Map050.json` EV019 page 0: every actor move is a step
count, and nothing anywhere in the event repositions anyone absolutely. So the
whole tableau's correctness rides on a single value — the tile the player is
standing on when EV019 fires. Call it **P0**.

Actor arithmetic (RMXP coords, +y = south):

| | tile |
|---|---|
| Machine (`EV019`) | (14,5) |
| Bambo (`EV005`) | (14,6) |
| Theo spawn (`EV020`) | (13,8) |
| machine-invi blockers (`EV017`/`EV018`) | (13,5), (15,5) |

- Theo: (13,8) → `walk_right` → (14,8) → net one `walk_up` → (14,7) →
  `walk_down`×2, `face_left` → **(14,9)**
- Player: P0 → `walk_left`, `walk_down`×2, `face_up` → (P0.x−1, P0.y+2), then
  `face_right`

### Uranium's anchor is (14,7)

The source route that moves Theo up carries RMXP's **Through ON** flag. That flag
only matters if the destination tile is occupied — i.e. the author expected Theo
to step *into the tile the player is vacating in that same frame batch*. Theo's
destination is (14,7), so Uranium's P0 is (14,7). Feeding that through the
arithmetic gives player (13,9) / Theo (14,9): adjacent, facing each other. Correct.

### Our anchor is forced to (14,6)

Decoded `engine/data/layouts/MokiTownProfessorLab/map.bin` (u16 per block,
collision = bits 10-11) for the region around the machine:

```
       10  11  12  13  14  15  16  17  18
y= 4    1   1   1   0   0   0   1   1   1
y= 5    0   0   0   1   0   1   0   0   0
y= 6    0   0   0   0   0   0   0   0   0
y= 7    1   0   0   0   0   0   0   0   0
y= 8    0   0   0   0   0   0   0   0   0
y= 9    1   1   0   0   0   0   0   1   1
```

(13,5) and (15,5) are collision 1 — the `machine-invi` through-blockers were
stamped correctly by `metadata_wiring.collect_through_block_cells`. That also
seals the walkable pocket at row 4, which is reachable only through row 5. The
machine object itself occupies (14,5). So **(14,6) is the only tile from which the
machine can ever be interacted with**, and P0 is deterministically (14,6) — one
tile north of Uranium's anchor.

| | Uranium (P0 = 14,7) | Ours (P0 = 14,6) |
|---|---|---|
| Player ends | (13,9) | (13,8) |
| Theo ends | (14,9) | (14,9) |
| Reads as | side by side, facing | diagonal — **the reported symptom** |

Theo halting "one short of the machine" is the same fact from the other side: he
stops on (14,7), one below the tile the player picked from.

---

## 3. Fix applied

`hand_conversions/Map050_EV019.pory` — deltas re-derived from P0 = (14,6),
preserving the source's *intent* (Theo takes the player's place at the machine,
then comes back and squares up beside them):

```
Theo   (13,8) -walk_right-> (14,8) -up x2-> (14,6) -down x3-> (14,9) face_left
Player (14,6) -left-> (13,6) -down x3-> (13,9) face_right
```

- Theo's final tile is **unchanged** at (14,9), so `Map050_EV019_Theo_Exit` and
  everything after the battle still line up.
- All eight walked tiles are collision 0.
- `Move5` deleted: the source's two back-to-back code-209 routes on Theo with no
  intervening 210 are an RMXP authoring artifact (last-wins in RGSS; the engine
  drops the second as already-in-flight), so only one ever executed on either
  side. `Move4` now carries the two-step approach outright.

1466 tests pass. **Needs `make modern` + re-stage + boot-walk to verify.**

---

## 4. Open question — for the PC playthrough

**What puts Uranium's own player on (14,7)?**

The Through-ON evidence says they are there, but the mechanism is not in the data
I could reach:

- **Not a counter tile.** RMXP reaches one tile past a counter
  (`Game_Map#counter?`, passage bit 0x80). Tile 641 at (14,6) has
  `passages = 0` — no counter bit, not blocked. (Tileset 19 *does* have 17 real
  counter tiles; on Map050 they sit at (8-10,17), nowhere near the machine.)
- **Not a proxy event.** The full Map050 event list has nothing at (14,6) except
  Bambo himself.
- **Bambo vacates it.** `EV005` page 0 command [120] moves him
  `move_right, turn_left` → (15,6), before "Go ahead and take it", so (14,6) is
  empty and passable by the time the player takes the ball.

Taken literally that says Uranium's player should *also* end up on (14,6), and
Uranium's own scene should show the same diagonal. Something in that chain is
wrong and a playthrough will show which.

**Consequence worth stating plainly:** if the original *is* staggered, then the
fix in §3 makes our version look **better than Uranium**, which is a §10
content-fidelity call, not a bug fix. Either answer is fine — but it should be a
decision, not an accident.

---

## 5. What to watch for on PC

In order, during the lab scene. None of this needs coordinates — it's all "is
there a gap between these two sprites".

1. **The intro march.** When the professor's scene pulls you north up the room,
   where do you stop — directly below him, or with one empty tile between you?
2. **Does he step aside** before telling you to take a ball? Which way, and does
   he stay there for the rest of the scene?
3. **Taking your ball.** Are you standing *directly below the machine*, or is
   there a tile between you and it? Can you even walk onto the tile directly
   below the machine?
4. **Can you trigger the machine from two tiles away** (standing where the
   professor was, one further back, and pressing A)? This is the single most
   diagnostic observation — a yes means there's a reach mechanism we haven't
   modelled.
5. **"I'm tired of waiting!"** — is Theo directly below you, or one tile off?
6. **Theo's turn at the machine.** Does he end up on the exact tile you stood on?
   Directly in front of the machine, or one back?
7. **The challenge.** Are you and Theo side by side and facing each other, or
   diagonal? (If diagonal on PC too — see §4's consequence.)
8. **Where you end up** relative to where you started the scene.

---

## 6. Adjacent gaps found while investigating

Neither caused this bug; both are real and corpus-wide.

1. **RMXP blocked-move stall is unmodelled for *scripted* (code-209) routes.**
   `tileset_converter/route_sim.py` and the custom C route interpreter
   (`MovementType_UraniumCustomRoute_Callback`) model it only for page-level
   ambient `move_type == 3` routes. Embedded cutscene routes compile to vanilla
   `applymovement`, whose `walk_*` actions **never check collision**
   (`InitNpcForMovement`, `engine/src/event_object_movement.c:7287-7305`).
   Uranium leans on the "walk N tiles, stop when you bump into someone" idiom —
   `EV005` page 0 marches the player `move_up`×10 — so any such route can land a
   different tile on GBA than in RMXP. This is the same root class as the
   already-fixed ambient-route bug, in the one place the fix didn't reach.

2. **The RMXP counter bit (0x80) is discarded corpus-wide.**
   `tileset_converter/tile_map.py:50-53` masks passages with `0x0F` and comments
   the high bits off as "non-collision flags"; nothing anywhere emits
   `MB_COUNTER`. The engine supports counter-reach **natively, zero custom C** —
   `MetatileBehavior_IsCounter` (`engine/src/metatile_behavior.c:490`) is consumed
   by `GetInteractedObjectEventScript`
   (`engine/src/field_control_avatar.c:400-409`), which looks one tile beyond a
   counter for the object event to interact with. Note collision is *not* derived
   from the behavior — a counter metatile must also be placed with a non-zero
   collision bit to block.

---

## 7. Harness follow-up

The suite could not have caught this: **nothing in `src/rpg2gba/playtest/` has ever
read `gObjectEvents`**, so the harness knows the player's position and nothing
about any other actor on screen. The symbol is already in the linker map
(`engine/pokeemerald.map:5142`, `OBJECT_EVENTS_COUNT` = 16); only the struct field
offsets need probing into `offsets.py`.

Design sketch (layers, cheapest first) — full rationale in the session discussion:

1. `Emulator.object_events()` / `npc(local_id)` → position, facing, graphics id,
   active/invisible. Turns this bug into a one-line B9 assertion: *Theo and the
   player are orthogonally adjacent and facing each other.*
2. Generic per-beat invariants (no per-scene authoring): no two actives sharing a
   tile, nobody on a non-zero-collision tile, nobody off-map — **plus** the one
   that would actually have caught this: *while dialogue is on screen, the
   speaking NPC is adjacent to the player and facing them.*
3. Source-derived expectations: extend `route_sim.py` to cutscene routes, emit
   expected end position/facing per actor, and diff the RMXP-simulated endpoint
   against the Emerald-simulated one **at build time, corpus-wide, no emulator**.
   Gap §6.1 is exactly what that diff detects.
4. Contact-sheet frames get a scene-state JSON sidecar (map, player + every NPC's
   coords and facing) so geometry can be audited from the sheet. Also: the
   2026-07-27 capture change lands frames on the dialogue moment, which is right
   for text and wrong for this bug — the stagger shows in the *aftermath*. Beats
   that move NPCs want both frames.
