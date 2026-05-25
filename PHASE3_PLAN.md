# Phase 3 — Map Deserialization: Implementation Plan

> Authoritative companion: `ROADMAP.md §Phase 3`, `CLAUDE.md`, `MEMORY.md`.
> If those conflict with this file, the roadmap wins for *what*, this file wins
> for *how/sequence*. Update this plan in-place (don't delete completed sections
> — strike them through with a one-line note) so the next agent can resume after
> a context cut.

---

## Context

Uranium's maps, events, and event scripts ship as Ruby `Marshal.dump` output in
`Data/Map*.rxdata` (plus `CommonEvents.rxdata`, `System.rxdata`,
`MapInfos.rxdata`). Phase 3 deserializes all of them into structured,
human-readable JSON that downstream phases consume:

- **Phase 4** (conversion agent) reads per-map event JSON — this is its sole
  input. The schema chosen here is its contract.
- **Phase 5** (map layout) reads the tile arrays and map metadata.

Phase 3 is **pure deserialization** — no Essentials semantics are interpreted, no
C is emitted, no flag names are minted. It is one Ruby deserializer plus a thin
Python driver/validator. It is **not** one of the three CLAUDE.md §9 manual
review gates; validation is a self-administered spot-check on representative maps.

What "done" looks like (ROADMAP §Phase 3 exit criteria, restated):

1. All maps deserialized to per-map JSON; `CommonEvents` and `System`
   (switch/variable tables) deserialized.
2. A command-code reference (`reference/rgss_event_commands.md`) written: every
   RPG Maker command code Uranium uses, tagged Direct / Adaptable / Needs-C /
   Strip, plus a list of the distinct script-call signatures observed.
3. Manual spot-checks on 3 representative maps confirm fidelity.
4. Output is idempotent (re-running produces byte-identical JSON).

---

## Decisions in effect (lock these in)

| # | Decision | Why |
|---|---|---|
| E1 | **Command representation is RAW + structural.** Every `RPG::EventCommand` is emitted verbatim as `{code, indent, parameters}`. Phase 3 structures only the *containers* — map → events → pages → (condition, graphic, move_route, list). No merging of text continuations (401), choice branches (402/403), or move-route sub-commands; no idiom recognition. | All command-level interpretation is Phase 4's LLM job. Keeps Phase 3 deterministic, lossless, fail-loud (CLAUDE.md §4.1/§4.5). The conversion agent gets the unaltered command stream. |
| E2 | **Script calls (codes 355/655) preserved raw; lightly cataloged.** `map_inventory.md` confirms zero non-standard *command codes* — Uranium's custom behavior hides in Script commands as `pbXxx` calls. The deserializer preserves their text losslessly inside `parameters`. §3.2's reference catalogs the ~60 standard codes in use (with Direct/Adaptable/Needs-C/Strip tags) and *lists* the distinct script-call signatures seen, without deep per-signature classification. | Deep `pbXxx` classification is most useful as Phase 4 prompt-design input and is done when Phase 4 starts. Phase 3 just surfaces the inventory. |
| E3 | **Extend `deserialize.rb`; do not write a second deserializer.** Its `rxdata` CLI branch (currently `NotImplementedError`) is implemented here, reusing its existing `jsonify` walker, `AutoStub`, and `Table/Color/Tone/WordArray/OrderedHash` `_load` stubs. The RMXP-accurate **nested** class stubs from `scripts/recon_maps.rb` (`RPG::Map`, `RPG::Event`, `Event::Page`, `Page::Condition`, `Page::Graphic`, `MoveRoute`, `MoveCommand`, `EventCommand`, `AudioFile`) are folded **into** `deserialize.rb`. | One source of truth (CLAUDE.md §4.3). `AutoStub` cannot synthesize nested constants under a stubbed namespace, and `Page` must be nested inside `Event` — both are documented landmines. Standardize on `deserialize.rb`'s fuller (non-lossy) `Color/Tone`/`Table` representations, not `recon_maps.rb`'s `@r`-only variants. |
| E4 | **One JSON file per map** at `output/uranium-build/maps/MapNNN.json`; `common_events.json` and `system.json` alongside. | Matches Phase 4's per-map orchestration + checkpointing; per-file diffs are reviewable; idempotent re-run (CLAUDE.md §4.2/§4.4). |
| E5 | **Tile data stays flat** (`{xsize, ysize, zsize, data:[...]}`, as the existing `Table` jsonify emits). No reshape into `[z][y][x]`. | Lossless; Phase 5 reshapes against the GBA tile model. Reshaping now would bake in an assumption Phase 5 owns. |
| E6 | **Switch/variable tables committed to `reference/`.** `System.rxdata`'s `@switches`/`@variables` name arrays dump to `reference/uranium_switches.json` / `uranium_variables.json` (tracked). | Small, hand-reviewable, and they are the Phase 4 flag-registry seed input. Map *event* JSON stays gitignored under `output/`. |
| E7 | **Fail loud** (CLAUDE.md §4.5). A command code outside the known catalog, a map that fails to Marshal-load, or an event missing required structure aborts with the map id + context — no silent skip, no default. | Same constraint as Phase 2. A silently dropped event surfaces as a soft-lock 5 phases later. |

---

## Prerequisites & sanity checks

- [ ] **P1.** `$RPG2GBA_URANIUM_SRC/Data/` reachable; `Map*.rxdata`,
      `CommonEvents.rxdata`, `System.rxdata`, `MapInfos.rxdata` present.
- [ ] **P2.** Confirm `ruby` available and `deserialize.rb dat` mode still works
      (smoke: it's exercised by the Phase 2 suite).
- [ ] **P3.** Confirm the inventory oracle: `reference/map_inventory.md` =
      199 maps / 5,301 events / 8,429 pages, zero unknown codes. The conservation
      test asserts against these numbers; if `recon_maps.rb` is re-run and they
      change, update both.

---

## Architecture

### Module layout (additions)

```
src/rpg2gba/
├── rxdata_deserializer/
│   └── deserialize.rb          # implement `rxdata` branch; fold in recon_maps.rb RPG stubs
├── map_deserializer/           # NEW Python package (driver + validation + catalog)
│   ├── __init__.py
│   ├── driver.py               # invoke deserialize.rb, place per-map JSON, idempotent
│   ├── validate.py             # conservation + schema-conformance checks
│   └── command_catalog.py      # scan JSON → reference/rgss_event_commands.md + script-call list
└── pipeline.py                 # wire up `phase3 [--clean]` Click command
```

Reuse the subprocess-to-Ruby pattern already in
`src/rpg2gba/pbs_converter/_marshal.py` (`dump_dat`/`load_json`) for `driver.py`'s
shell-out to `deserialize.rb`.

### Data flow

```
$RPG2GBA_URANIUM_SRC/Data/Map*.rxdata        deserialize.rb rxdata
  CommonEvents.rxdata, System.rxdata    ───►  (Marshal.load + jsonify)  ───► output/uranium-build/maps/MapNNN.json
  MapInfos.rxdata                                                              output/uranium-build/common_events.json
                                                                               output/uranium-build/system.json
                                                          │
                                                          ├─► validate.py (counts vs map_inventory.md; schema)
                                                          └─► command_catalog.py ─► reference/rgss_event_commands.md
                                                                                    reference/uranium_switches.json
                                                                                    reference/uranium_variables.json
```

`output/uranium-build/` is gitignored; re-running `phase3` must produce
byte-identical JSON (idempotence).

### JSON schema (the Phase 4 contract — E1)

Per map (`MapNNN.json`):
```json
{
  "map_id": 7,
  "tileset_id": 12,
  "width": 40, "height": 30,
  "bgm": {"name": "...", "volume": 80, "pitch": 100},
  "bgs": {"...": "..."},
  "encounter_step": 30,
  "tiles": {"xsize": 40, "ysize": 30, "zsize": 3, "data": ["..."]},
  "events": [
    {
      "id": 1, "name": "EV001", "x": 12, "y": 8,
      "pages": [
        {
          "condition": {"...": "switch/variable/self-switch validity + ids"},
          "graphic": {"character_name": "...", "direction": 2, "...": "..."},
          "trigger": 0,
          "move_type": 0,
          "move_route": {"repeat": true, "list": [{"code": 1, "parameters": []}]},
          "list": [
            {"code": 101, "indent": 0, "parameters": ["..."]},
            {"code": 401, "indent": 0, "parameters": ["..."]}
          ]
        }
      ]
    }
  ]
}
```
- `tiles.data` is the flat signed-int16 array from `Table` (E5).
- `list` commands are verbatim; **401/402/403/408/655 continuations are NOT
  merged** (E1).
- Script-call commands (355 + 655 continuations) keep their raw string lines in
  `parameters`.

`common_events.json`: array of `{id, name, trigger, switch_id, list}`.
`system.json` (+ extracted sidecars): `{switches: [...names], variables: [...names]}`.

---

## Per-task list

### 3.0 — Deserializer core (`deserialize.rb` rxdata branch)

- [ ] Fold `recon_maps.rb`'s `RPG` module stubs into `deserialize.rb` (nested
      `Event::Page::Condition/Graphic`, `MoveRoute`, `MoveCommand`,
      `EventCommand`, `AudioFile`, `BGM/BGS/ME/SE`). Keep `deserialize.rb`'s
      fuller `Color/Tone/Table` `_load` (not `recon_maps.rb`'s `@r`-only).
- [ ] Implement `rxdata <data_dir> <output_dir>`: glob `Map[0-9]*.rxdata`, sort,
      `Marshal.load` each, `jsonify`, write `MapNNN.json` (zero-padded to match
      source, e.g. `Map007.json`). Also load `CommonEvents.rxdata`,
      `System.rxdata`, `MapInfos.rxdata` → their JSON files.
- [ ] Fail loud on any map that raises during load (abort with map id), per E7.
- [ ] Stable JSON key ordering for idempotent diffs.

### 3.1 — Python driver (`map_deserializer/driver.py`)

- [ ] `run(clean: bool)`: optionally wipe `output/uranium-build/maps/`, shell to
      `deserialize.rb rxdata` (reuse `_marshal.py` subprocess pattern),
      confirm expected file count.
- [ ] Wire `pipeline.py phase3 [--clean]` Click command.

### 3.2 — Command-code reference + script-call list (`command_catalog.py`)

- [ ] Scan all map + common-event JSON; tally every distinct command `code` and
      its frequency. Assert no code outside the known catalog (E7) — currently
      zero unknown, so this *locks* the invariant.
- [ ] Emit `reference/rgss_event_commands.md`: each code in use → name +
      Direct / Adaptable / Needs-C / Strip tag (seed names from
      `recon_maps.rb`'s `COMMON_CODES` comments).
- [ ] Extract distinct **script-call signatures** from code-355/655 command
      bodies (the leading `pbXxx(` / method token); list them with occurrence
      counts in the same doc under a "Script calls (Phase 4 input)" section. No
      per-signature Direct/Adaptable/etc. tagging yet (E2).

### 3.3 — Switch / variable dump

- [ ] From `system.json`, write `reference/uranium_switches.json` and
      `reference/uranium_variables.json` (`{index: name}`), committed (E6). These
      seed the Phase 4 flag registry; cross-reference the pre-seed candidates
      already in `MEMORY.md → Flag Registry Notes`.

### 3.4 — Common events

- [ ] Confirm `common_events.json` deserializes (handled by 3.0); validate each
      entry has `{id, name, trigger, list}`.

---

## Test strategy (round-trip is impossible — see Context)

`tests/test_map_deserializer.py`, gated by the existing `conftest.py` env-var
skip + a `phase3` marker (add to `pyproject.toml`).

1. **Conservation test.** Deserialize the corpus; assert aggregate counts equal
   `map_inventory.md` (199 maps / 5,301 events / 8,429 pages) and that per-map
   event/page counts match the inventory table. This is the primary fidelity
   guard in lieu of round-trip.
2. **Schema-conformance test.** Every `MapNNN.json` has the required top-level
   keys; every event has `id/name/x/y/pages`; every page has `list`; every
   command has `code/indent/parameters`. Fail loud on any miss.
3. **Command-coverage test.** No command code outside the known catalog appears
   (locks the zero-unknown invariant).
4. **Golden test.** Pin 3–4 representative maps' JSON under
   `tests/fixtures/` and assert byte-equality: a town, a route, a building
   interior (selected via `reference/map_names.json`), **plus the worst-case
   page** (Map 71, 1,018 commands) as a stress fixture.
5. **Idempotence.** Two `phase3 --clean` runs; `diff -r` of
   `output/uranium-build/maps/` empty.

---

## Verification — Phase 3 exit gate

- [ ] **V1.** `python -m rpg2gba.pipeline phase3 --clean` exits 0; emits one JSON
      per map + `common_events.json` + `system.json` + the `reference/` sidecars.
- [ ] **V2.** `pytest -m phase3 -v` green.
- [ ] **V3.** Idempotence: re-run, `diff -r` empty.
- [ ] **V4.** Manual spot-check (ROADMAP §Phase 3 validation): open the 3
      representative maps' JSON, confirm event count + a couple of event scripts
      against expected in-game behavior (use the `pokemon-uranium-wiki` skill /
      `reference/map_names.json` to identify maps).
- [ ] **V5.** `reference/rgss_event_commands.md` reviewed: every code tagged;
      script-call list present.
- [ ] **V6.** `MEMORY.md` updated — Current Phase → Phase 3 done / Phase 4 ready;
      new Last Session Summary; note switch/var sidecars as Phase 4 flag-registry
      seed. Commit.

---

## Critical files (read first when resuming)

- `ROADMAP.md` §Phase 3
- `CLAUDE.md` §§4.1–4.6 (determinism, idempotence, fail-loud), §4.3 (one SoT)
- `MEMORY.md` (Current Phase, Flag Registry Notes, Open Questions)
- `src/rpg2gba/rxdata_deserializer/deserialize.rb` (extend the `rxdata` branch)
- `scripts/recon_maps.rb` (RMXP-accurate nested stubs + `COMMON_CODES` seed)
- `src/rpg2gba/pbs_converter/_marshal.py` (subprocess-to-Ruby pattern to reuse)
- `reference/map_inventory.md` (the conservation-test oracle)

## Resume-after-context-cut checklist

1. Read `MEMORY.md` end-to-end, then this plan.
2. First unchecked `- [ ]` is where to start.
3. `output/uranium-build/maps/` contents = how far the last session got (derived;
   SoT is whether driver + tests pass).
4. `pytest -m phase3 -v` for current status.
5. Update checkboxes + add a wrinkle note under each §3.x as you go.
