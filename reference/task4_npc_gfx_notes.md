# Task 4 — NPC gfx map: working notes (2026-07-05)

Session-limit insurance: research + design state for the NPC gfx map (RMXP
`character_name` → `OBJ_EVENT_GFX_*`), captured mid-task so a fresh session
can resume. Delete or fold into a proper design doc once task 4 lands.

## Slice census (boot-active page per event, maps 49/48/32)

Method: RMXP shows the HIGHEST-index page whose conditions hold; boot state =
all switches OFF, vars 0, self-switches OFF (census script:
`census_npc_gfx.py`, rerunnable — evaluates `condition` per page). Result:

- **33 events, blank `character_name`** — invisible interactables:
  - trigger 0 (action button): furniture/sign flavor text (all of Map048/049's
    bookshelves etc., M32 EV1/4/11) → bg_event "sign" candidates.
  - trigger 1 (player touch): doors/warp mouths + cave entrances
    (M32 EV23/36/37) → coord events (warps already wired separately).
  - trigger 3/4 (autorun/parallel): M48 EV1/EV5 → map-script territory.
- **~20 events with NO boot-active page** (Theo, Bambo/16, Chyinmunk76/77,
  Kellyn/20, Letter/21, Lucille/17, post-game/stage-gated NPCs): RMXP renders
  nothing at boot → emit NO object event. Correct at boot; story-stage
  materialization (page-condition model → per-map transition script) is a
  DEFERRED design, ties to the same deferral as EV76/77 graphic swaps.
- **Doors as event graphics**: `PU-doorsdew` ×4, `FKdoors1` ×1 (trigger 1
  touch-warps) → skip object emission (door art belongs to the tileset/warp
  layer, not an NPC).
- **`fk107-rocksmash` ×3** (M32 EV14/15/33) → `OBJ_EVENT_GFX_BREAKABLE_ROCK`
  (pairs with the native `EventScript_RockSmash` the transpiler now emits).
- **`HGSS_014` ×2 (M32 EV9/EV74)**: opacity 0 + through, trigger 2 —
  invisible touch-trigger script hosts → coord events, NO object.
- **EV75 'Theo75'**: `Rivaltheo`, opacity 0, through — spawn-invisible-then-
  set_visible actor. Needs the spawn-invisible recipe (fork research pending
  below).
- **Ambient NPC move types** (RMXP `move_type`: 0 fixed, 1 random, 2 approach,
  3 custom): v1 mapping — 0/2/3 → face direction (RMXP `direction` 2=down,
  4=left, 6=right, 8=up), 1 → wander. Custom routes deferred.

## Sprite substitutions — picked BY EYE from the real sheets (lead viewed
## every PNG in $RPG2GBA_URANIUM_SRC/Graphics/Characters/)

Townsfolk (HGSS-style sheets; slice events listed):

| Uranium sheet | Looks like | Proposed OBJ_EVENT_GFX_* (verify exact name vs fork inventory) | Slice events |
|---|---|---|---|
| HGSS_000 | boy, olive hair, blue shorts | little boy / school kid M | M32 EV48 |
| HGSS_001 | little girl, red bow, cream dress | little girl | M32 EV72 |
| HGSS_005 | teen boy, bowl cut, dark/orange shirt | boy/youngster | M32 EV73 |
| HGSS_008 | young woman, brown hair, white top | girl/woman (young) | M32 EV27 |
| HGSS_009 | blond man, gray slacks | man 1 | M32 EV71 |
| HGSS_017 | woman, brown updo, white+pink dress | woman (housewife) | M32 EV12 |
| HGSS_018 | old man, bald, white beard, blue robe | old man | M32 EV69 |
| HGSS_019 | old woman, gray bun, mauve dress | old woman (or expert F) | M32 EV68 |
| HGSS_034 | heavyset person, blue overalls/apron | fat man / pokéfan M | M32 EV70 |
| HGSS_051 | man, red cap, khaki | camper (Red-style) | M32 EV13 |
| HGSS_129 | granny, white bun, warm apron dress | old woman ("Auntie") | M49 EV1 |
| Rivaltheo | boy, spiky flame-orange hair, white+red | rival-ish; fallback boy w/ red — pick from fork inventory | (EV75 op-0; Theo events have no boot page) |

Pokémon (Uranium OW sprites → vanilla lookalikes via
`OBJ_EVENT_GFX_SPECIES(name)` — macro confirmed shipping, event_objects.h:457,
OW_POKEMON_OBJECT_EVENTS=TRUE in config/overworld.h; SPECIES_* names are
vanilla so the fork-index gate accepts them):

| Uranium mon | Sprite look | Vanilla stand-in | Slice events |
|---|---|---|---|
| PU-Chyinmunk | tan+blue squirrel, all fours | SPECIES(PACHIRISU) (alt SENTRET) | M32 EV8/EV10 |
| PU-Orchynx | green metal kitten, head sprout | SPECIES(CHIKORITA) (alt SHINX) | M32 EV18 |
| PU-Raptorch | dark bipedal raptor, flame tail | SPECIES(CHARMANDER) | M32 EV22 |
| PU-Eletux | blue quadruped, fin hood, gold spots | SPECIES(SHINX) | M32 EV20 |
| PU-Barewl | small brown mon, anvil/rock head | SPECIES(ARON) | M32 EV35 |

## Design intent (pending research confirmation)

- SoT: `reference/npc_gfx_map.json` — `character_name` → gfx constant (+
  optional per-name notes), hand-reviewable, fail-loud on unmapped names
  (CLAUDE.md §4.3/§4.5). Doors/rocksmash/blank classified by RULE, not table.
- Local id MUST equal RMXP event id (task-4 constraint #1 — 207 emotes,
  applymovement/setobjectxy/removeobject targets are literal RMXP ids).
- Page selection at conversion = the census's boot-state rule (deterministic).
- EV76/77 (ceremony actors): no boot page → no object v1; the hand override's
  applymovement(76/77, …) only runs at story stage 2 which is unreachable on
  slice 1 without debug var poking — acceptable; note in walkthrough.

## Explorer findings (recorded 2026-07-05; two Sonnet Explore agents)

### Repo wiring (metadata_wiring.py et al.)

- `build_object_events()` metadata_wiring.py:284-330 emits EVERY object with
  hardcoded `DEFAULT_GFX = "OBJ_EVENT_GFX_NINJA_BOY"` (L57, set at L307/L328)
  — the S9 "NPC crowd" defect in code form. `movement_type` always
  `MOVEMENT_TYPE_NONE` (dataclass default L86, RMXP `move_type` never read);
  `flag` always `"0"`; elevation always 3; `trainer_type`/`sight` hardcoded
  in `to_dict()` (L89-102, all porymap-required fields present).
- **CRITICAL — local-id constraint VIOLATED today.** mapjson.cpp:249-255: the
  compiled runtime local id = 1-based ARRAY POSITION in `object_events`; a
  JSON `local_id` key (mapjson.cpp:438-443) only mints a cosmetic #define.
  `classify_map_events` (L207-222) drops warps/skips from the object list, so
  positions shift below RMXP event ids (proved: Map049 EV004 → local id 2).
  Every emitted `applymovement(16,…)`/`setobjectxy(20,…)`/emote target uses
  the LITERAL RMXP id → currently wrong at runtime. Fix options: (a) pad the
  array with fillers so position==id — rejected, Map032 ids reach 81
  (template count/spawn overhead); (b) **REMAP at staging**: wiring produces
  a per-map `{rmxp_event_id → local_id}` table; a staging-time pass rewrites
  integer targets in applymovement/setobjectxy/addobject/removeobject in the
  `.pory` (or the transpiler consumes the table via ctx). DECIDE NEXT SESSION
  — (b) preferred. Affects the Map032_EV009 hand override too (targets
  16/76/77/2).
- `classify_event()` L186-204: 3 buckets only — "skip" (any out-of-slice
  code-201), "warp" (in-slice 201 + page[0].trigger==1 player-touch),
  everything else "object". `character_name` NEVER inspected; coord_events/
  bg_events ALWAYS emitted empty (MapFile.to_json_dict L168-169) — no
  coord/bg category exists yet.
- Page data survives fully in maps/Map*.json per page: `graphic`
  {character_name, opacity, direction (2/4/6/8), pattern, …}, `move_type`,
  `through`, `step_anime`, `walk_anime`, `trigger`. NOTHING downstream reads
  them for objects today; no page-selection logic exists anywhere — open slot.
- Script wiring: object.script = `page_label(uid,eid,1)` (base page) or
  `dispatch_label` (self-switch dispatcher, build_page_dispatcher L236-267;
  falls back to base page on global switch/var gates) or `"0x0"` (no body).
- Prune rule (assembly.py:109-176): a `.pory` block survives iff its label's
  event id appears in ANY object/coord/bg `script` field (prefix regex
  `^Map\d+_EV(\d+)_` — one reference keeps ALL of that event's blocks);
  warp_events excluded. → bg/coord events with script labels KEEP their
  event's blocks — good, EV21 Letter etc. survive via their entries.
- SoT loader pattern to copy: `terrain_tag_map.json` +
  `terrain_tags.load_terrain_tag_map` (terrain_tags.py:158-181) — JSON names
  fork enum, loader parses the real fork header and fails loud on unknown
  names (§4.7 forward gate).

### Fork mechanisms (engine/, citations verified by agent)

- Humanoid inventory (include/constants/event_objects.h): BOY_1/2/3, LASS,
  MAN_1..5, WOMAN_1..5, OLD_MAN (L55), OLD_WOMAN (L56), PROF_BIRCH (L90),
  MOM (241), SCIENTIST_1/2, HIKER, FISHERMAN, SAILOR, LITTLE_BOY (37),
  LITTLE_GIRL (38), NURSE, RICH_BOY (41), CAMPER (57), PICNICKER (58),
  BLACK_BELT, COOK, REPORTER_M/F, ARTIST, GENTLEMAN, TWIN, POKEFAN_F/M,
  EXPERT_M/F exist too; plus FRLG dupes. Props: CUTTABLE_TREE,
  **BREAKABLE_ROCK (L86)**, ITEM_BALL (59), PUSHABLE_BOULDER. **No blank/
  invisible gfx constant exists.**
- **Spawn-invisible recipe:** `"movement_type": "MOVEMENT_TYPE_INVISIBLE"`
  (event_object_movement.h:81; Kecleon Route120 map.json:502-513 is the
  vanilla exemplar). `set_visible`/`set_invisible` movement actions toggle
  the runtime `objectEvent->invisible` bool (event_object_movement.c:8719-30);
  respawn re-derives invisible from movementType (c:1856-57) → reveals are
  NON-persistent, same as RMXP page-graphic semantics. Template `flag` field
  = spawn-suppression (FlagGet gate, c:2918), a different axis. CAVEAT:
  invisible objects are SOLID (Kecleon is a deliberate invisible obstacle) —
  RMXP `through=true` opacity-0 events are walkable → emitting them creates
  invisible walls. v1 therefore SKIPS them (see decisions).
- bg_events sign shape (LittlerootTown map.json:239-246): `{"type":"sign",
  x, y, "elevation":0, "player_facing_dir":"BG_EVENT_PLAYER_FACING_ANY",
  "script": label}`. coord_events trigger shape (BattlePikeRoomNormal:47-56):
  `{"type":"trigger", x, y, elevation, "var":"VAR_…", "var_value":"0",
  "script": label}` — NOTE coord events need a var+value gate field pair.
- mapjson.cpp does ZERO semantic validation of graphics_id — raw text into
  the .inc, resolved at assembly (map_events.s includes constants headers);
  missing/empty required field = FATAL. All porymap fields our ObjectEvent
  already emits are required.
- Static movement strings (vanilla-verified): MOVEMENT_TYPE_FACE_DOWN/UP/
  LEFT/RIGHT (13/12/14/15), WANDER_AROUND (7), LOOK_AROUND (6).
- BUILD-VERIFY ITEM: `OBJ_EVENT_GFX_SPECIES(PACHIRISU)` as a graphics_id
  string expands via cpp in the map_events.s TU — confirm SPECIES_* is in
  scope there (event_objects.h:457 macro references SPECIES_##name) before
  relying on it; if not in scope, fall back to plain archetype sprites for
  the 5 Pokémon NPCs.

## v1 decisions (lead, 2026-07-05 — pending user sign-off on the sprite table)

1. New SoT `reference/npc_gfx_map.json` (terrain_tag_map pattern):
   `character_name` → `OBJ_EVENT_GFX_*` string + note; loader validates
   against event_objects.h, fail-loud on unmapped/unknown. Rules (not table
   rows): blank name, door sheets (`PU-doors*`, `FKdoors*`), no-boot-page →
   handled structurally.
2. Boot-active page (census rule) decides an event's graphic + direction +
   move type: move_type 0/2/3 → FACE_{dir}, 1 → WANDER_AROUND.
3. Blank-gfx trigger-0 events → bg_events "sign" (facing ANY); blank-gfx
   trigger-1 non-warp (cave mouths) → stay objects? NO — they're touch →
   coord_events… BUT coord shape needs var/var_value; simplest v1: leave them
   as (invisible-solid?) — UNRESOLVED, decide at build: candidates =
   coord_events with VAR_TEMP_0/0 gate (fires every step — verify semantics)
   or keep as today's objects minus sprite. RECORD: cave mouths EV23/36/37
   currently classify "skip" (out-of-slice warp) anyway → moot for slice 1.
4. Opacity-0 or no-boot-page events → NO object emitted v1 (RMXP-faithful at
   boot; avoids invisible walls). Story-stage materialization +
   MOVEMENT_TYPE_INVISIBLE cutscene actors = deferred design, one package
   with the local-id remap.
5. `fk107-rocksmash` → OBJ_EVENT_GFX_BREAKABLE_ROCK (pairs with the native
   EventScript_RockSmash emission).
6. Pokémon NPCs → OBJ_EVENT_GFX_SPECIES(lookalike) pending the build-verify
   item; fallbacks in the sprite table above.
