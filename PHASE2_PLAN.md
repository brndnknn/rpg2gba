# Phase 2 — PBS Data Conversion: Implementation Plan

> Authoritative companion: `ROADMAP.md §Phase 2`, `CLAUDE.md`, `MEMORY.md`,
> `reference/uranium_dat_inventory.md`. If those conflict with this file, the
> roadmap wins for *what*, this file wins for *how/sequence*. Update this plan
> file in-place (do **not** delete completed sections — strike them through and
> add a one-line note) so the next agent can pick up after a context cut.

---

## Context

Why this work: Uranium ships only Essentials' compiled `.dat` files; there is
no PBS source text. Phase 2's job is to convert those `.dat` files into the C
data tables that pokeemerald-expansion uses (`gSpeciesInfo[]`, `gMovesInfo[]`,
item / ability / TM / trainer / encounter tables) plus a canonical
`reference/uranium_id_map.json` so every downstream phase (especially the
conversion agent in Phase 4 and the map wiring in Phase 5) has stable IDs.

What "done" looks like for Phase 2 (roadmap §Phase 2 exit criteria, restated):

1. Every shipped `.dat` we said we'd convert has a converter, OR an explicit
   STRIP/DEFER decision recorded in `uranium_dat_inventory.md`.
2. Round-trip + golden tests pass for each converter.
3. The generated C drops cleanly into the pokeemerald-expansion fork and a
   test ROM at least lists Uranium species in the Pokédex.
4. `reference/uranium_id_map.json` committed with every Uranium internal name
   → expansion constant.

Phase 2 prep (the `.dat` deserialization spike) is **complete** as of
2026-05-18 (see MEMORY.md). All open questions for Phase 2 entry are
resolved. We are starting cold on the converters themselves.

---

## Decisions in effect (lock these in)

| # | Decision | Why |
|---|---|---|
| D1 | Custom Essentials binary files (`dexdata.dat`, `moves.dat`, `items.dat`, `tm.dat`, `tutor.dat`, `attacksRS.dat`, `tmpbs.dat`, `evolutions.dat`, `eggEmerald.dat`, `regionals.dat`, `metrics.dat`) are parsed in **Python**, reading the write schema directly out of `reference/scripts_dump/175__Compiler.rb`. No Ruby invoked for these. | Eliminates a Ruby-Python round-trip for the bulk of the data. The format is just `fputb`/`fputw`/`fputdw` little-endian ints — trivial in Python. |
| D2 | Ruby Marshal files (`trainers.dat`, `trainertypes.dat`, `encounters.dat`, `connections.dat`, `metadata.dat`, `townmap.dat`, `berryplants.dat`, `phone.dat`, `shadowmoves.dat`) are deserialized by a single Ruby script (`src/rpg2gba/rxdata_deserializer/deserialize.rb` is extended to handle both `.rxdata` and Marshal `.dat`) into JSON. Python reads the JSON. | Don't reimplement Ruby `Marshal.load` in Python (known rabbit hole). The Phase 3 deserializer can do double duty here. |
| D3 | Uranium-original moves / abilities / items with no clean vanilla expansion equivalent → **emit a stub constant + placeholder entry, mark in `uranium_id_map.json` under `needs_engine`**. Real engine behavior is Phase 6. | Per user direction. Keeps Phase 2 lossless: nothing is silently mapped to a near-but-wrong vanilla constant. Phase 6 has a concrete worklist. |
| D4 | Battle-facility data (`btpokemon.dat`, `bttrainers.dat`, `trainerlists.dat`) → **DEFER** (post-Phase 7). Add explicit STRIP-with-rationale entry in `uranium_dat_inventory.md`. | Per user direction. Phase 0 success criteria don't require battle facility; cutting it slims Phase 2. |
| D5 | Golden-test fixtures = **pinned output snippets from real Uranium `.dat`** (run once on real data, hand-review first N records, commit those). | Per user direction. Trades hand-derived rigor for authoring speed; fixture review is the human gate. |
| D6 | `move2anim.dat`, `intl_*.dat`, `BackupSave.dat` → **SKIP** in Phase 2 (regenerated downstream, irrelevant, or not data). `messages.dat` is **read-only-dumped** to JSON sidecars in `reference/` (see §2.0) — we need its strings to populate display names but never emit it back. Record both in inventory. | Per inventory; no behavioral change for the SKIPs. `messages.dat` carve-out is forced by the discovery that custom-binary `.dat` files don't carry names. |
| D7 | `types.dat` (20-type matrix incl. Nuclear) → **read & dump JSON only** in Phase 2 (`reference/types_dump.json`). The actual `gTypeEffectiveness[]` C emit is Phase 6. | Reading is cheap and unblocks Phase 6 planning; emitting C means coupling to Nuclear-type engine work. |
| D8 | Failure mode is **fail-loud** (CLAUDE.md §4.5). No silent defaults for unknown fields, no auto-coerced enum values. A surprise field aborts the converter with the path+offset. | Same constraint as roadmap. Codify in every parser's helper layer. |

---

## Prerequisites & sanity checks

Run these *first*. Each is a tight loop, not a multi-hour task.

- [x] **P1. Verify Phase 1 fork is set up.** ~~`make modern` clean-tree build~~
      DONE 2026-05-20: fork cloned (shallow `--depth 1`, HEAD `21c24202`) at
      `/home/b/repos/pokeemerald-expansion`; path in `.env`. **`make modern`
      not yet run** (needs devkitARM) — exit criterion #3 / V6 still deferred,
      but struct verification (P4) is unblocked.
- [x] **P2. Verify `$RPG2GBA_URANIUM_SRC/Data/` is reachable** — DONE: 254
      files in `Data/`.
- [x] **P3. Verify `reference/scripts_dump/175__Compiler.rb` exists** — DONE:
      present (131 KB).
- [~] **P4. Verify pokeemerald-expansion C shapes.** SPECIES shapes verified
      2026-05-20 → `reference/pokeemerald_struct_shapes.md` + MEMORY.md Key
      File Notes (designated initializers; field map; learnset/egg/evolution
      macros; teachableLearnset is build-generated; hidden-ability drift).
      Moves/items/abilities/trainers/encounters shapes deferred to their
      §2.x sections (verify each just before that converter's emit). Read
      these once and record any drift from what this plan assumes (note in
      MEMORY.md):
      - `include/constants/species.h` — `SPECIES_*` enum layout
      - `src/data/pokemon/species_info.h` — `gSpeciesInfo[]` struct shape
      - `src/data/moves_info.h` — `gMovesInfo[]` struct shape
      - `src/data/items.h` — `gItems[]` struct shape
      - `include/constants/abilities.h` — `ABILITY_*` enum
      - `include/constants/moves.h` — `MOVE_*` enum
      - `data/trainers.party` and `src/data/trainers.h` — trainer format
      - `src/data/wild_encounters.json` — encounter format

If P4 reveals the expansion has changed the shape of any of these structs
from what this plan assumes, **update this plan file before coding** — do not
just paper over the diff inside a converter.

---

## Architecture

### Module layout (additions; existing skeleton stays)

```
src/rpg2gba/
├── pbs_converter/
│   ├── __init__.py
│   ├── _binary.py          # NEW — Essentials custom-binary read helpers
│   ├── _naming.py          # NEW — shared name→expansion-constant rule + fork constant-set loader (used by §2.1–§2.4)
│   ├── _id_map.py          # NEW — load/append/save reference/uranium_id_map.json
│   ├── _c_emit.py          # NEW — shared C-emit helpers (string escape, header guards, comment banners)
│   ├── pokemon.py          # § 2.1
│   ├── moves.py            # § 2.2
│   ├── items.py            # § 2.3
│   ├── abilities.py        # § 2.4
│   ├── tm_hm.py            # § 2.5 (rename from any existing stub if needed)
│   ├── trainers.py         # § 2.6
│   ├── encounters.py       # § 2.7
│   ├── metadata.py         # § 2.8
│   └── tmpbs.py            # § 2.9 (auxiliary species data; bundled into pokemon.py output)
├── rxdata_deserializer/
│   └── deserialize.rb      # extend to also dump Marshal-format .dat → JSON
├── pipeline.py             # wire up `phase2` Click command (currently NotImplementedError)
└── (no changes to conversion_agent/* in Phase 2)
```

### Data-flow

```
$RPG2GBA_URANIUM_SRC/Data/*.dat
        │
        ├── (custom binary)              ── _binary.py readers ──► dataclass records ──► emit_c ──► output/uranium-build/src/data/*.h|*.c
        │
        └── (Ruby Marshal) ──► deserialize.rb (Ruby) ──► output/uranium-build/intermediate/<name>.json ──► Python emitters ──► output/uranium-build/src/data/*.h|*.c

                                                                   ▼
                                                    reference/uranium_id_map.json (incrementally appended)
```

`output/uranium-build/` is gitignored. Wiping it and re-running `rpg2gba
phase2` must produce byte-identical results (CLAUDE.md §4.2 — idempotence).

### Cross-cutting components

**`_binary.py`** — thin stream reader matching Essentials' `fputb`/`fputw`/
`fputdw` (1/2/4-byte unsigned little-endian). API:
```python
class DatReader:
    def __init__(self, path: Path) -> None: ...
    def b(self) -> int           # uint8
    def w(self) -> int           # uint16 LE
    def dw(self) -> int          # uint32 LE
    def s(self) -> str           # length-prefixed (encodeString in Compiler.rb)
    def at(self, offset: int) -> "DatReader"   # seek into a slice
    @property
    def remaining(self) -> int
    @property
    def eof(self) -> bool
```
Plus a helper `parse_indexed(path, entry_size_in_bytes, length_unit,
body_parser)` for the recurring "`[offset, length]` table at front, then
per-species blob" layout. **Warning — the meaning of the stored `length`
field differs per file** (this is the kind of bug that costs an afternoon
if you don't pin it):

| File | Per-entry size | Stored `length` field means | Source |
|---|---|---|---|
| `attacksRS.dat` | 4 bytes per pair (level uint16 + move_id uint16) | `pair_count × 2` (uint16 count) — divide by 2 to get pair count | Compiler line ~2630 |
| `eggEmerald.dat` | 2 bytes per entry (move_id uint16) | element count (= byte count / 2) | Compiler ~2580 |
| `tmpbs.dat` | 2 bytes per entry (move_id uint16) | element count | Compiler ~2599 |
| `tutor.dat` | 2 bytes per entry (move_id uint16) | element count | Compiler ~2613 |
| `evolutions.dat` | 5 bytes per evolution (uint8 method/flag + uint16 param + uint16 species) | **byte count** (= 5 × evolution count) | Compiler ~2556 |
| `tm.dat` | uint16 species_id per entry | (verify before coding — Compiler.rb section TBD) | — |

The fixed-table header is always `mx × 8` bytes (mx pairs of uint32
offset + uint32 length), so `payload_start_offset = species_count × 8`.
Body data starts at that offset. **`moves.dat` is NOT indexed** — see
§2.2; it's a flat 14-byte-per-move table.

**`_id_map.py`** — owns `reference/uranium_id_map.json`. Shape:
```json
{
  "version": 1,
  "species":   {"URAYNE": "SPECIES_URAYNE", "EEVEE": "SPECIES_EEVEE", ...},
  "moves":     {"GAMMARAY": "MOVE_GAMMARAY", "TACKLE": "MOVE_TACKLE", ...},
  "items":     {...},
  "abilities": {"CHERNOBYL": "ABILITY_CHERNOBYL", ...},
  "trainer_classes": {...},
  "types":     {"NUCLEAR": "TYPE_NUCLEAR", ...},
  "needs_engine": {
    "moves":     ["MOVE_GAMMARAY", "MOVE_RADIOACID", ...],
    "abilities": ["ABILITY_CHERNOBYL", ...],
    "items":     [...]
  }
}
```
Provides `get(category, internal)`, `add(category, internal, constant,
needs_engine: bool=False)` (idempotent — re-adding the same pair is a
no-op; conflicting constant for same internal is a fail-loud error).
Loaded once per `phase2` run, saved at end. Per CLAUDE.md §6 this is the
single source of truth — no other module gets to mint constants.

**`_c_emit.py`** — utilities: `escape_c_string`, `wrap_header(guard, body)`,
`generated_banner(source_dat, generator_module)`. Every emitted `.h`/`.c`
starts with a "DO NOT EDIT — generated by rpg2gba.pbs_converter.X" banner
that names the source `.dat` and the generator module.

**`deserialize.rb` extension** — accept a `--dat` flag that switches it
from `.rxdata` map mode to "load one Marshal-format `.dat`, dump JSON".
Reuses class-stub strategy from `scripts/spike_dat_inventory.rb`
(specifically the `AutoStub` pattern at lines 18–35 and the `Table` /
`Color` / `Tone` `_load` stubs at lines 38–57). Output: one JSON file per
input `.dat` at `output/uranium-build/intermediate/<name>.json`.

---

## Per-converter task list

Strict ordering. Each step depends on `_binary.py` + `_id_map.py` existing.
After 2.0 the rest can be parallelized if needed, but follow the order on
single-threaded execution because move/ability IDs feed species, and
species IDs feed encounters/trainers.

### 2.0 — Cross-cutting scaffolding (incl. names sidecar)

**Important prerequisite added during planning:** the custom-binary `.dat`
files do **not** carry display names — Essentials routes names and
descriptions through `MessageTypes`, which serialize into `messages.dat`.
That file was originally flagged as SKIP (D6), but Phase 2 needs a
read-only extract of it to populate move/item/species/ability display
strings. Action:

- [x] Write `scripts/dump_messages.rb` — emitted 22 sidecars (species_names.json …
      script_texts.json) covering all `MessageTypes` buckets. Required adding
      a custom `OrderedHash._load`/`_dump` since Essentials shipped its own
      ordered-hash class with a non-default Marshal format. **Found in
      passing:** `species_names[201] = "Gengar"` — resolves MEMORY.md's open
      question about species 201 (it's a placeholder/Easter-egg slot,
      explaining why it has no Tandor dex entry in `regionals.dat`).
- [ ] One-shot count-verification test (deferred until §2.1/2.2 land — needs
      a parsed `dexdata.dat`/`moves.dat` to compare against).

Standard scaffolding:

- [x] Write `_binary.py` with `DatReader` + `parse_indexed`. Includes the
      Essentials variable-length-int decoder (`_decode_int`) used by
      `encodeString`. Fail-loud per CLAUDE.md §4.5.
- [x] Write `_id_map.py` with load/add/save. `add` is idempotent on identical
      pairs; conflicting constants raise `IdMapConflictError`. `save` sorts
      keys for stable diffs.
- [x] Write `_c_emit.py` with `escape_c_string`, `wrap_header`,
      `generated_banner`.
- [x] Extend `deserialize.rb` with `dat <input> <output>` mode (Marshal load
      → JSON via a generic `jsonify` walker). `rxdata` mode still stubs for
      Phase 3. Smoke-tested against `metadata.dat` (218 entries) and
      `trainers.dat` (331 entries).
- [x] Wire `pipeline.py` `phase2 --clean` Click command with lazy converter
      discovery — modules that haven't been written yet are skipped, so the
      pipeline runs partial Phase 2 work cleanly.
- [x] Tests: `test_binary.py` (11 tests), `test_id_map.py` (10 tests),
      `test_c_emit.py` (6 tests). **27/27 passing**.

### 2.1 — Species (`pokemon.py`) — source: `dexdata.dat`

Schema (from `175__Compiler.rb:2269+` `requiredtypes`/`optionaltypes`,
already cited in MEMORY.md and inventory):

- 76 bytes per species, flat array, no header. Species N at offset
  `(N-1) × 76`. Count = `file_size / 76` (expect 201).
- Field offsets within each 76-byte record (from Compiler `[offset, type]`
  tuples — `u`=uint8, `w`=uint16, `i`=int8, etc.):
  - `Color` @6 (uint8 enum: Red/Blue/...)
  - `Habitat` @7 (uint8 enum)
  - `Type1` @8 (uint8 → PBTypes index)
  - `Type2` @9 (uint8 → PBTypes index; defaults to Type1 if absent)
  - `BaseStats` @10 (6 × uint8: HP/Atk/Def/Spd/SpA/SpD)
  - `Rareness` @16 (uint8)
  - `GenderRate` @18 (uint8 enum)
  - `Happiness` @19 (uint8)
  - `GrowthRate` @20 (uint8 enum)
  - `StepsToHatch` @21 (uint16)
  - `EffortPoints` @23 (6 × uint8)
  - `Compatibility` @31 (uint8 × 2: egg group 1/2)
  - `Height` @33 (uint16 fixed-point)
  - `Weight` @35 (uint16 fixed-point)
  - `BaseEXP` @38 (uint16)
  - `Abilities` @29 (uint8 × 2)
  - `HiddenAbility` @40 (uint8 × 4)
  - `WildItemCommon` @48 / `WildItemUncommon` @50 / `WildItemRare` @52 (uint16 each)
  - Remaining bytes are padding / unused in v17.
  - **String fields (`Name`, `Kind`, `Pokedex`, `FormNames`) are NOT in
    `dexdata.dat`** — they live in `messages.dat` and are extracted by
    `scripts/dump_messages.rb` (see §2.0) into JSON sidecars. The
    `InternalName` (used to mint `SPECIES_*` constants) comes from the
    `PBSpecies` script section in `Scripts.rxdata` (already dumped at
    `reference/scripts_dump/` — grep for `class PBSpecies`).
- Auxiliary side data tied to species ID:
  - **Level-up learnsets** — `attacksRS.dat`, indexed format. Header is
    one `[offset, length]` pair per species (8 bytes each), then each
    species' block is `length / 4` pairs of `[level: uint16, move_id: uint16]`.
    See Compiler `f.fputdw(offset); f.fputdw(...length*2)` site (~line 2633).
  - **TMPBS** (Uranium-original extra move list) — `tmpbs.dat`, indexed
    format, single uint16 move IDs per entry. See ~line 2599.
  - **Egg moves** — `eggEmerald.dat`, indexed format, single uint16 move
    IDs per entry. See ~line 2580.
  - **Tutor moves per species** — `tutor.dat`, indexed format, single
    uint16 move IDs per entry. See ~line 2610.
  - **Evolutions** — `evolutions.dat`, indexed format, blocks of 5-byte
    records `[method: uint8, param: uint16, target_species: uint16]`. See
    ~line 2557-2566.
  - **Regional dex numbers** — `regionals.dat`, header `[num_regionals
    uint16, num_species uint16]`, then `num_regionals × num_species` uint16
    matrix of Tandor dex numbers.
  - **Battler metrics** — `metrics.dat`, parallel signed-word arrays
    (BattlerPlayerY/EnemyY/Altitude) keyed by species ID.

Output:
- `output/uranium-build/src/data/pokemon/species_info.h` — `gSpeciesInfo[]`
  entries, one per species. Use the existing `gSpeciesInfo` struct shape
  found in P4. Display strings (`Name`, `Kind`, `Pokedex`) come from the
  `species_names.json` / `species_kinds.json` / `species_pokedex.json`
  sidecars produced in §2.0.
- `output/uranium-build/include/constants/species.h` — `SPECIES_*` enum
  (every species; Uranium-originals get the `SPECIES_` prefix on their
  Uranium internal name).
- `output/uranium-build/src/data/pokemon/level_up_learnsets.h`,
  `evolutions.h`, `tutor_learnsets.h`, `egg_moves.h`, `tmpbs.h` (the last
  is Uranium-specific; see "needs_engine" decision below).
- Species 201 (no Tandor number) → emit with internal name discovered from
  the bytes; record in `uranium_id_map.json` and surface in
  `Open Questions` in MEMORY.md if its purpose remains unclear after this
  pass.
- Uranium-original abilities referenced in `Abilities`/`HiddenAbility`
  fields that don't resolve in `id_map.abilities` → mark `needs_engine` per
  D3. Same for any move ID in a learnset that's Uranium-original.

Tasks:
- [x] Write `Species` dataclass + `parse(path) -> list[Species]` for `dexdata.dat`.
- [x] Parse `attacksRS.dat` into per-species level-up learnset lists.
- [x] Parse `evolutions.dat` into per-species evolution lists. **Fixed mask:
      method = `byte & 0x3F`; only `byte & 0xC0 == 0` rows are forward
      evolutions (the rest are prevolution/form rows Essentials also stores).**
- [x] Parse `eggEmerald.dat`, `tutor.dat` into per-species move lists. (tutor.dat
      ships empty; teachableLearnset is build-generated by the fork — not emitted.)
- [x] Parse `regionals.dat` into Tandor dex number lookup.
- [~] ~~Parse `metrics.dat` into per-species battler offset lookup.~~ **DEFERRED:**
      Marshal-format, only affects battler sprite positioning; not needed for a
      Pokédex-listing milestone. Revisit if sprites look misaligned in Phase 5/7.
- [x] Resolve internal names from `PBSpecies` (via `species_internal_names.json`);
      mint `SPECIES_*` via `_id_map`.
- [x] Emit `species.h` (constants), `species_info.h`, `level_up_learnsets.h`,
      `egg_moves.h`. **Evolutions are emitted *inline* in `species_info.h`
      (`.evolutions = EVOLUTION(...)`) — the modern expansion has no separate
      `evolutions.h`. `tutor_learnsets.h` intentionally not emitted (see above).**
      Tandor dex carried in `intermediate/tandor_dex.json` for Phase 5.
- [x] Mark Uranium-original abilities & moves referenced from species as
      `needs_engine` (validated against the fork's enum constant sets via
      `_naming.load_fork_constants`): 27 moves, 17 abilities, 7 items, 166 species.
- [x] Round-trip test (`test_roundtrip_stats`: stats+catchRate re-read from C).
- [x] Golden test: `tests/fixtures/pokemon_golden.h` pins ORCHYNX (starter) +
      URAYNE (Nuclear). (`gSpeciesInfo` keys by `[SPECIES_*]`, so a designated-
      initializer entry per species rather than `[0..4]` positional.)
- [x] Edge test: species 201 (Gengar) round-trips with no Tandor dex entry.
- [x] Edge test: a Uranium-original ability (`ABILITY_GEIGER_SENSE`) is marked
      `needs_engine`. Plus `test_edge_evolutions_forward_only` for the mask fix.

### 2.2 — Moves (`moves.py`) — source: `moves.dat` + `messages.dat`-derived sidecar — ✓ COMPLETE (2026-05-20)

Schema (verified from `175__Compiler.rb` lines ~1166–1280):
- **`moves.dat` is a flat 14-byte-per-move table**, not indexed. Each
  move occupies `movedata.length` indices keyed by move ID (0..maxID),
  zero-padded for unused IDs. Pack format `"vCCCCCCvCvC"`:
  - uint16 LE — function code (effect ID)
  - uint8 — base damage
  - uint8 — type (PBTypes index)
  - uint8 — category (0=Physical, 1=Special, 2=Status)
  - uint8 — accuracy
  - uint8 — total PP
  - uint8 — additional-effect chance
  - uint16 LE — target
  - uint8 — priority (treat as signed int8)
  - uint16 LE — flags bitfield (16 bits; flag chars a..p map to bits 0..15)
  - uint8 — dummy (legacy contest type slot, always 0)
- **Move names and descriptions are NOT in `moves.dat`** — they're routed
  through `MessageTypes::Moves` / `MessageTypes::MoveDescriptions`, which
  serialize into `messages.dat`. The Python emitter reads
  `reference/move_names.json` and `reference/move_descriptions.json`
  (produced once by `scripts/dump_messages.rb` in §2.0).
- Internal names (`MOVE_TACKLE` etc.) come from the `PBMoves` script
  section in `Scripts.rxdata` — already dumped at
  `reference/scripts_dump/`. Grep for `class PBMoves` to find the file.

Tasks:
- [x] Write `Move` dataclass + `parse(path) -> list[Move]` for `moves.dat` (flat 14-byte records, struct `"<HBBBBBBHBHB"`).
- [x] Resolve `MOVE_*` via `_naming.to_constant` on the display name (matches §2.1 learnset emit) + mint via `_id_map`, keyed by internal name from `reference/move_internal_names.json` (the dumped `PBMoves` section).
- [x] Nuclear moves flagged `needs_engine` (detected by type idx 18, not a hardcoded name list → 9 moves). **Deviation:** ALL move effects deferred to Phase 6, not just Nuclear — every move emits `EFFECT_PLACEHOLDER` (`EFFECT_NONE` would lose the distinction) + `// TODO Phase 6: function code N` comment + a complete `intermediate/move_function_codes.json` worklist. See MEMORY.md 2026-05-20 decision.
- [x] Emit `moves_info.h` (`gMovesInfo[]`, designated initializers) and `moves.h` (`MOVE_*` `#define`s). Target via PBTargets→`TARGET_*` map; positive flags only.
- [x] Cross-check covered by the shared resolver: `pokemon.py` learnset/egg-move emit resolves every referenced move id through `move_constant`, which fails loud if the id is absent from `move_internal_names.json`.
- [x] Round-trip test (`test_pbs_moves.py::test_roundtrip_numeric` — power/accuracy/pp/priority).
- [x] Golden test: `tests/fixtures/moves_golden.h` pins MOVE_TACKLE + the Nuclear move MOVE_ATOMIC_PUNCH.
- [x] Edge tests: Nuclear move `needs_engine`; every move `EFFECT_PLACEHOLDER` + worklisted losslessly.

### 2.3 — Items (`items.py`) — source: `items.dat`

Schema (from `pbCompileItems` around line 810): indexed binary; per item:
ID, internal name, display name, plural name, pocket (uint8), price
(uint16), description (string), use in field flag (uint8), use in battle
flag (uint8), special item type (uint8), Mach Bike / TM / HM / etc.
markers.

Tasks:
- [ ] Verify exact `items.dat` field order against `pbCompileItems` (Compiler.rb ~810). Update schema above if different.
- [ ] Write `Item` dataclass + parser.
- [ ] Build pocket/category enum-mapping table from P4 (`include/constants/items.h` in fork).
- [ ] Mint `ITEM_*` constants via `_id_map`; mark Uranium-original items as `needs_engine`.
- [ ] Emit `items.h` and `items.h` constants header.
- [ ] Round-trip test.
- [ ] Golden test: snapshot first 5 items + one Uranium-original.
- [ ] Edge test: a `needs_engine` item is correctly marked.

### 2.4 — Abilities (`abilities.py`) — source: `dexdata.dat` references + script-side names

Abilities don't have their own `.dat`. Compiler.rb `pbCompileAbilities`
writes them into a script section, not a separate file.

Tasks:
- [ ] Read every `Abilities` and `HiddenAbility` byte from `dexdata.dat` to get the set of ability IDs in use.
- [ ] Locate the `PBAbilities` script section in `reference/scripts_dump/`; build ID → internal name map.
- [ ] Mint `ABILITY_*` via `_id_map`; mark Uranium-originals (incl. `CHERNOBYL`) as `needs_engine`.
- [ ] Emit `include/constants/abilities.h` with only the Uranium-original `ABILITY_*` constants.
- [ ] Emit `src/data/abilities/uranium_abilities.c` with NULL/no-op placeholder handlers.
- [ ] Round-trip test (parse → emit → re-extract ID set → diff).
- [ ] Golden test: snapshot Uranium-only `ABILITY_*` block into `tests/fixtures/abilities_golden.h`.

### 2.5 — TM / HM (`tm_hm.py`) — source: `tm.dat`, `tutor.dat`

Both are indexed-binary with single uint16 move IDs per entry.

- `tm.dat`: entry index = TM number, body = list of species IDs that can
  learn that TM. (Verify per Compiler.rb — the inverse mapping may also
  be valid; pick whichever matches the file's byte structure.)
- `tutor.dat`: entry per species, body = list of move IDs that species
  can learn from move tutors. (Already touched by §2.1; this step writes
  the dedicated output.)

Tasks:
- [ ] Verify `tm.dat` byte structure against Compiler.rb; nail down direction (TM→species or species→TM).
- [ ] Parse `tm.dat` and `tutor.dat`.
- [ ] Emit `tm_hm_compatibility.h` (per-species bitfield, matching P4-discovered shape).
- [ ] Emit `tutor_learnsets.h` here (remove from §2.1 emit list — single source).
- [ ] Round-trip test.
- [ ] Golden test: snapshot one species' TM bitfield + one species' tutor list.
- [ ] Edge test: a species that learns 0 TMs round-trips correctly.

### 2.6 — Trainers (`trainers.py`) — source: `trainers.dat` + `trainertypes.dat`

These are **Ruby Marshal format** (per D2 — uses `deserialize.rb --dat`).

- `trainers.dat`: array of trainer objects. Each has class ID, name,
  party (array of Pokémon templates: species, level, item, moves,
  IV/EV, ability index, gender, nickname). No `TPSHADOW=true` rows
  (MEMORY.md confirms 0 hits across 331 trainers — but assert this
  invariant in the parser, fail-loud if it changes).
- `trainertypes.dat`: array of trainer-class definitions: name, BGM,
  AI flag, base prize money, double-battle flag.

Tasks:
- [ ] Use `deserialize.rb --dat` to dump `trainers.dat` and `trainertypes.dat` to JSON.
- [ ] Write Python parser over the JSON into `Trainer` / `TrainerType` dataclasses.
- [ ] Assert 0 `TPSHADOW` hits across all trainers; fail loud if non-zero.
- [ ] Mint `TRAINER_*` and `TRAINER_CLASS_*` via `_id_map`, preserving Uranium IDs.
- [ ] Emit `trainers.h`, `trainers.h` constants, `trainer_classes.h`.
- [ ] Add banner pointing to MEMORY.md 2026-05-15 decision re: script 216 custom trainers (Phase 4 work, not here).
- [ ] Round-trip test.
- [ ] Golden test: snapshot first 3 trainers + all class definitions.
- [ ] Edge test: a doubles trainer + a trainer with a custom-moveset Pokémon.

### 2.7 — Encounters (`encounters.py`) — source: `encounters.dat`

**Ruby Marshal format** (D2 → JSON).

Hash keyed by map ID; value is the encounter table for that map (slots
per encounter type: grass, surf, fishing, rock smash, headbutt, etc.;
each slot = [species_id, min_level, max_level]).

Tasks:
- [ ] Use `deserialize.rb --dat` to dump `encounters.dat` to JSON.
- [ ] Write Python parser into per-map `EncounterTable` dataclasses.
- [ ] Map Essentials encounter types → expansion encounter types via a static lookup table inside `encounters.py`.
- [ ] Emit `wild_encounters.json` keyed by Uranium map ID (Phase 5 remaps).
- [ ] Round-trip test.
- [ ] Golden test: snapshot first 3 map encounter tables (pick maps from `reference/map_inventory.md` covering grass + water + fishing).

### 2.8 — Metadata (`metadata.py`) — source: `metadata.dat`

**Ruby Marshal format** (D2 → JSON).

Hash of map-level metadata. Per Essentials: weather, outdoor flag, BGM
override, battle background, escape map, etc. Plus a global "Home"
record at index 0 with party start position.

Tasks:
- [ ] Use `deserialize.rb --dat` to dump `metadata.dat` to JSON.
- [ ] Parse JSON into `GlobalMetadata` + `MapMetadata` dataclasses.
- [ ] Emit `metadata.h` (player spawn x/y/map/direction).
- [ ] Emit `map_metadata.json` for per-map metadata (Phase 5 consumer).
- [ ] Round-trip test.
- [ ] Golden test: snapshot global record + one map record.

### 2.9 — TMPBS sidecar (`tmpbs.py`) — source: `tmpbs.dat`

Functionally already parsed alongside §2.1, but it's Uranium-original
and worth a dedicated module for the emit step.

Tasks:
- [ ] Parse `tmpbs.dat` (indexed format, single uint16 per entry).
- [ ] Emit `uranium_tmpbs.h` as a per-species extra-moves table.
- [ ] Add `// TODO: confirm tmpbs semantics — see MEMORY.md Open Questions` banner on the emitted header.
- [ ] Round-trip test.
- [ ] Golden test: snapshot a species with a non-empty TMPBS list.

### 2.10 — Types snapshot (`types_dump`, no emit) — source: `types.dat`

Per D7, Phase 2 dumps a JSON sidecar only.

Tasks:
- [ ] Verify `types.dat` format (Marshal vs custom). Route accordingly.
- [ ] Parse 20-type effectiveness matrix; locate Nuclear index.
- [ ] Resolve type names from `Scripts.rxdata` `PBTypes` section.
- [ ] Emit `reference/types_dump.json` with `{ "types": [...], "matrix": [[...]], "nuclear_index": N }`. No C emission.
- [ ] Sanity test: matrix is 20×20 and Nuclear index is present.

---

## Testing strategy (CLAUDE.md §4.6 mandate)

Every converter module gets:
1. **Round-trip test** — parse the real `.dat`, emit C, re-extract the
   dataclass records from the emitted C, diff against the parsed records.
   The "re-extract from C" side uses lightweight regex parsing inside the
   test; we are not building a full C parser.
2. **Golden test** — snapshot the first N records of generated output
   into `tests/fixtures/<module>_golden.<ext>`, then assert byte-equality
   on subsequent runs (per D5).
3. **Edge-case test** — one per Uranium-original quirk that wouldn't be
   exercised by the golden subset (see edge call-outs under each §2.x).

Tests share fixtures via `tests/conftest.py`. Add a session-scoped fixture
that points at `$RPG2GBA_URANIUM_SRC/Data/` and **skips** the entire
Phase 2 test suite if the env var is unset (so CI on a stranger's machine
doesn't error out). Pure-unit tests for `_binary.py` and `_id_map.py`
have no env-var dependency and always run.

`pytest -m phase2` should run the converter suite; `pytest` (no marker)
runs only the env-independent tests by default. Add a `phase2` marker in
`pyproject.toml`.

---

## Verification — Phase 2 exit gate

Run in order. Tick each as it passes.

- [ ] **V1. Fresh full run.** `rm -rf output/uranium-build && python -m rpg2gba.pipeline phase2 --clean` exits 0 and emits every `.h`/`.c`/`.json` listed in §§2.1–2.10.
- [ ] **V2. All Phase 2 tests pass.** `pytest -m phase2 -v` — green.
- [ ] **V3. Registry consistency check.** `python -m rpg2gba.conversion_agent.flag_registry validate` confirms `uranium_id_map.json` constants don't collide with the seed flag-registry list.
- [ ] **V4. Idempotence check.** Re-run `python -m rpg2gba.pipeline phase2 --clean`; `diff -r` of the two `output/uranium-build/` trees must be empty.
- [ ] **V5. Manual review — user gate (CLAUDE.md §9 #1).**
  - [ ] User reviews `reference/uranium_id_map.json` (esp. `needs_engine` buckets — Phase 6 worklist).
  - [ ] User reviews `reference/uranium_dat_inventory.md` — every shipped `.dat` has CONVERTED or STRIP/DEFER.
  - [ ] User spot-checks generated C: a Nuclear species, a vanilla species, a trainer party, an encounter table.
- [ ] **V6. Fork drop-in build** (skip + log to MEMORY.md if P1 deferred).
  - [ ] Copy `output/uranium-build/src/data/*.h` and `output/uranium-build/include/constants/*.h` into matching directories in `$RPG2GBA_POKEEMERALD`.
  - [ ] `(cd $RPG2GBA_POKEEMERALD && make -j$(nproc) modern)` succeeds.
  - [ ] Boot resulting ROM in Delta; Pokédex lists Uranium species (CLAUDE.md exit criterion #3).
- [ ] **V7. MEMORY.md updated.** Set `Current Phase` to "Phase 3 ready"; rewrite `Last Session Summary` to capture what closed and any deferrals. Commit.

---

## Critical files (read first when resuming)

- `ROADMAP.md` §Phase 2 (lines ~292–363)
- `CLAUDE.md` §§4.1–4.6, §6, §9 (operating principles, flag registry,
  manual review gates)
- `MEMORY.md` (always — especially Current Phase, Open Questions, Last
  Session Summary)
- `reference/uranium_dat_inventory.md` (authoritative `.dat` list +
  format split + status)
- `reference/scripts_dump/175__Compiler.rb` (binary write schemas — every
  custom-binary parser is reading this for its field order)
- `scripts/spike_dat_inventory.rb` (proven `Marshal.load` stub pattern;
  copy `AutoStub` and the `Table`/`Color`/`Tone` `_load` stubs for the
  Ruby deserializer extension)
- `src/rpg2gba/pbs_converter/*.py` (current stubs — replace, don't append)
- `src/rpg2gba/rxdata_deserializer/deserialize.rb` (currently raises
  NotImplementedError — extend per D2)
- `src/rpg2gba/pipeline.py` (the `phase2` Click command is the entry
  point you wire up)

## Resume-after-context-cut checklist

If a future session picks this up cold:

1. Read `MEMORY.md` end-to-end (it's the load-bearing artifact).
2. Read this plan file. Each `- [ ]` item is unfinished; each `- [x]` is
   done. Find the first unchecked item and start there.
3. Check `output/uranium-build/` — anything in there from a prior session
   is evidence of how far the previous agent got. Treat as derived; the
   source of truth is whether the generator + test pass.
4. Run `pytest -m phase2 -v` to see current converter status. Greens are
   already done.
5. Before writing new code: re-confirm P4 (pokeemerald-expansion struct
   shapes) — if the fork has been updated between sessions, the C output
   shape might have drifted.
6. Update this plan file's checkboxes as you complete steps; add a brief
   note under each §2.x entry if you hit an unexpected wrinkle worth
   carrying forward.
