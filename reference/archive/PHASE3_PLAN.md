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

- [x] **P1.** `$RPG2GBA_URANIUM_SRC/Data/` reachable; `Map*.rxdata` (199),
      `CommonEvents.rxdata`, `System.rxdata`, `MapInfos.rxdata` all present.
- [x] **P2.** `ruby` available; `deserialize.rb dat` mode still works (Phase 2 suite).
- [x] **P3.** Inventory oracle confirmed: 199 maps / 5,301 events / 8,429 pages.
      The `rxdata` smoke run reproduces these counts exactly; 58 distinct command
      codes, all within the known catalog.

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

### 3.0 — Deserializer core (`deserialize.rb` rxdata branch) — ✓ COMPLETE

- [x] Folded `recon_maps.rb`'s nested `RPG` stubs into `deserialize.rb` (kept the
      fuller `Color/Tone/Table` `_load`). **Wrinkle:** Marshal does NOT trigger
      `const_missing` for *nested* names (`RPG::System`, `System::Words`), so
      added `marshal_load_lenient` — on "undefined class/module X", synthesise the
      stub class and retry. The `RPG.const_missing` is kept as belt-and-suspenders
      but the lenient loader is the real fix.
- [x] Implemented `rxdata <data_dir> <output_dir>`: writes `maps/MapNNN.json`
      (zero-padded, matches source) + `common_events.json` + `system.json` +
      `map_infos.json`. Map/event/page/command containers shaped explicitly (E1);
      command `parameters`, condition, graphic, encounter_list via generic walker.
- [x] Fail loud: `marshal_load_lenient` aborts with the filename on a real load
      error (only `undefined class/module` is recovered).
- [x] Stable output: explicit key ordering + events sorted by id. Smoke run:
      199 maps / 5301 events / 8429 pages (exact), script calls preserved raw.

### 3.1 — Python driver (`map_deserializer/driver.py`) — ✓ COMPLETE

- [x] `driver.run(uranium_src, out_dir, clean)`: wipes `maps/`, shells to
      `deserialize.rb rxdata`, returns map count. Fail-loud on non-zero exit.
- [x] Wired `pipeline.py phase3 [--clean]` → driver → validate → command_catalog.
      **Note:** run via the project venv: `.venv/bin/python -m rpg2gba.pipeline`.

### 3.2 — Command-code reference + script-call list (`command_catalog.py`) — ✓ COMPLETE

- [x] Scans maps + common events; tallies all codes. **59 codes in use, 83,237
      command instances.** Coverage guard (E7): `CATALOG` is a superset of the
      standard RGSS set; any code outside it is fail-loud. Zero unknown today.
- [x] Emits `reference/rgss_event_commands.md`: code → name + advisory
      Direct/Adaptable/NeedsC/Strip tag + count.
- [x] Extracts distinct script-call signatures from 355/655 (**250 distinct**),
      listed with counts under "Script calls (Phase 4 input)" — no per-signature
      classification yet (E2).

### 3.3 — Switch / variable dump — ✓ COMPLETE

- [x] `command_catalog._write_switch_var_tables` writes
      `reference/uranium_switches.json` (**235 named**) +
      `uranium_variables.json` (**119 named**), `{index: name}`, named entries
      only. Phase 4 flag-registry seed; cross-ref `MEMORY.md → Flag Registry Notes`.
      **Finding:** some "switches" are Essentials script-switches, e.g.
      `s:pbIsWeekday(-1,2,4,6)` — evaluated, not stored. Phase 4 must special-case.

### 3.4 — Common events — ✓ COMPLETE

- [x] `common_events.json` (100 entries) shaped with `{id, name, trigger,
      switch_id, list}`; presence + parseability checked by `validate_output`.

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

- [x] **V1.** `.venv/bin/python -m rpg2gba.pipeline phase3 --clean` exits 0; emits
      199 `maps/MapNNN.json` + `common_events.json` + `system.json` +
      `map_infos.json` + the three `reference/` sidecars.
- [x] **V2.** `pytest -m phase3 -v` green (9 tests); full suite 75 passed; ruff clean.
- [x] **V3.** Idempotence: `test_idempotence` re-runs clean and asserts byte
      identity across all 199 map JSON; golden tests pin 4 maps byte-for-byte.
- [ ] **V4.** *(user)* Manual spot-check: open Map002 (Burole Town PC interior),
      Map001/Map021 (routes), Map071 (stress, 1018-cmd page) JSON; confirm event
      counts + a few scripts vs in-game (`pokemon-uranium-wiki` skill). **Note a
      naming oddity to verify:** `map_infos["1"]` = "Route 03" but `Map001`'s BGM
      is "PU-Hero House" — confirm the map-id↔name alignment.
- [ ] **V5.** *(user)* Review `reference/rgss_event_commands.md`: every code
      tagged; script-call list present (250 signatures).
- [x] **V6.** `MEMORY.md` updated (Current Phase → Phase 3 done / Phase 4 next;
      new Last Session Summary; switch/var sidecars noted as flag-registry seed).
      Committed.

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
