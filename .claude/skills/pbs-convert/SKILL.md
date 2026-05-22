---
name: pbs-convert
description: >
  Step-by-step workflow for converting one Pokémon Uranium PBS data section
  (species, moves, items, abilities, TM/HM, trainers, encounters, metadata)
  into pokeemerald-expansion C tables. Use when the user asks to convert,
  port, or emit a Phase 2 PBS section, or to work on a §2.x converter under
  src/rpg2gba/pbs_converter/. Encodes the repeated decode→reconcile→map→emit→
  worklist→test pipeline and its gotchas. Advisory only — it tells you HOW to
  process a section; it does not change conversion logic or decide WHICH section
  to do.
---

# pbs-convert — Phase 2 PBS section workflow

Every Phase 2 section (`§2.x` in `PHASE2_PLAN.md`) runs the **same six-step
pipeline**. This skill is that pipeline, written once. The section is the
variable; the workflow is the constant. The user tells you which section to do
("convert §2.4 abilities") — you don't pick it here.

**This skill is the *how*, not the *what*.** It encodes the existing, working
process used for §2.1 species, §2.2 moves, and §2.3 items. It is advisory: don't
invent new conversion logic, and when something is genuinely new, follow the
repo's existing decision pattern (document + map/add/strip), not a fresh design.

Three working principles inherited from `CLAUDE.md`:

- **Fail loud (§4.5).** Unrecognized field, unknown tag, missing sidecar → raise
  with file + offset, never silently default.
- **Idempotent output (§4.2/§4.4).** Emit with `timestamp=False`; a clean re-run
  must produce byte-identical files (`diff -r`-clean). All output lands under
  `output/uranium-build/` (gitignored).
- **One source of truth (§4.3).** Constants are minted through the `IdMap`
  (`reference/uranium_id_map.json`), never hand-written.

Mirror the structure of the three completed sections — they are the golden
references (see **Worked references** at the bottom). Cite them; don't re-derive
them.

---

## Shared toolbox — reuse these, don't rewrite them

All four live in `src/rpg2gba/pbs_converter/`.

| Module | What it gives you |
|---|---|
| `_binary.py` | `DatReader(path)` — little-endian reads `b()`/`w()`/`dw()`/`sb()`/`sw()`, length-prefixed `s()` (Windows-1252 w/ UTF-8 fallback), varint, `seek`/`at`/`bytes`. Plus `parse_indexed(path, count, body_parser, ...)` for files with an `(offset, length)` header. Raises `BinaryReadError` on EOF/out-of-range. |
| `_naming.py` | `to_constant(prefix, name)` → `PREFIX_UPPER_SNAKE`; `_fold_accents` (NFKD diacritic strip); `load_fork_constants(header_path, prefix)` → set of existing fork constants (empty set if header missing = "can't validate"). |
| `_id_map.py` | `IdMap` — `load`/`save`, `add(category, internal, constant, *, needs_engine=False)` (idempotent; raises `IdMapConflictError`), `mark_needs_engine(category, constant)`. Categories incl. `species, moves, items, abilities, trainers, ...`; `needs_engine` tracked for `moves, abilities, items, species`. |
| `_c_emit.py` | `escape_c_string(s)`; `generated_banner(source_dat, generator_module, *, timestamp=False)`; `wrap_header(guard, body, *, banner="")`. |

---

## The six-step pipeline

For each step: what to do, which helper/path, and a worked reference.

### 1. Inspect the source `.dat`
Find the file under `$RPG2GBA_URANIUM_SRC/Data/`. Consult
`reference/uranium_dat_inventory.md` (file list + format notes) and
`reference/uranium_structure.md` (full schema disassembly) for layout.

**Choose the decode path** (see Gotchas — this is the #1 source of mistakes):
- **Fixed-size flat records** — every record is the same byte width, indexed by
  position, empty slots are all-zero. Read with `struct`/manual `DatReader`
  calls. *Ref: `moves.py` (`_RECORD_STRUCT`, 14-byte records).*
- **Indexed offset/length header** — file starts with `count × (uint32 offset,
  uint32 length)`, then per-record bodies. Use `parse_indexed(...)`. The body is
  either:
  - **TLV** (self-describing tag bytes) — *ref: `items.py`*, or
  - **plain u16 arrays** (length = element count) — *ref: `pokemon.py` level-up
    learnsets / egg moves.*

### 2. Reconcile internal names
Attach the sidecar JSONs from `reference/`: `<section>_internal_names.json`
(from `Constants.rxdata`), `<section>_names.json` (display names), and
`<section>_descriptions.json` where present. **Prefer the display name** for
minting — expansion constants follow the spaced/canonical name; fall back to the
internal name when no display string exists. *Ref: each converter's
`attach_internal_names` / `_load_id_json`.*

### 3. Map Uranium IDs → expansion constants
Build the resolver:
1. `to_constant(prefix, name)` to derive the candidate constant.
2. Validate against the fork via `load_fork_constants(<fork header>, prefix)`
   (needs `$RPG2GBA_POKEEMERALD`). A derived name **not** in the fork set is a
   Uranium-original.
3. Pre-mint every constant through `IdMap.add(...)` *before* emitting, so
   cross-references (learnsets referencing `MOVE_*`, evolutions referencing
   `SPECIES_*`) resolve consistently.
4. Uranium-originals → `IdMap.mark_needs_engine(category, constant)`.

`IdMap.add` raises `IdMapConflictError` if the same internal name maps to two
constants — that's the consistency guarantee, let it fail loud.

### 4. Emit the C
Banner first: `generated_banner(source, "rpg2gba.pbs_converter.<section>",
timestamp=False)`, wrapped with `wrap_header(guard, body, banner=banner)`.
- **Constants header** → `output/uranium-build/include/constants/<section>.h`
- **Data table** (designated initializers) →
  `output/uranium-build/src/data/<section>.h` (or `src/data/pokemon/*` for
  species sub-tables).

Match the struct field layout in `reference/pokeemerald_struct_shapes.md`
(`gSpeciesInfo`, `gMovesInfo`, items, etc.). **Defer unknown behavior to
placeholders** (e.g. `EFFECT_PLACEHOLDER` for move effects) rather than guessing
— the real behavior is captured in the worklist (step 5). *Ref: `moves.py`
`emit_moves_info`, `items.py` `emit_items_info`/`emit_constants`.*

### 5. Write the `needs_engine` worklist JSON
Under `output/uranium-build/intermediate/`, keyed by the minted constant,
preserving the **raw Essentials behavior codes** so nothing is lost (the C table
placeholdered them; the worklist remembers them for Phase 6). *Refs:
`item_field_codes.json` (item_use/battle_use/item_type/machine_move),
`move_function_codes.json` (function_code/effect_chance).*

If the section has a field vanilla Essentials lacks, **document it** in
`reference/uranium_custom_features.md` with an explicit decision: **map** to an
existing constant, **add** a new one, or **strip**. Never silently drop a field.

### 6. Add tests
In `tests/test_pbs_<section>.py`, marked `@pytest.mark.phase2`, env-gated through
the `conftest.py` fixtures (`uranium_data`, `reference_dir`, `fork_path` — tests
skip cleanly when env vars are unset). Three kinds, mirroring the existing test
files:
1. **Round-trip** — parse → emit C → regex-read-back → diff numeric fields
   (assert a meaningful count, e.g. ≥200 entries checked).
2. **Golden snapshot** — compare two extracted entries (one vanilla, one
   Uranium-original) against a committed `tests/fixtures/<section>_golden.h`.
3. **Edge case** — the section's specific quirk (e.g. accent folding,
   `needs_engine` flagging, key-item importance).

---

## Delegating to sub-agents (cost control)

Main sessions run on Opus; offload suitable work to Haiku/Sonnet sub-agents.
**Sub-agents draft and gather; the main session decides and reviews.** Always
verify a sub-agent's reported layout/constants against the source before
committing converter logic to it (fail loud, don't trust blindly).

**Good to delegate** (read-heavy / mechanical, returns a conclusion):
- *Step 1 inspect* — point an `Explore`/Sonnet agent at the `.dat` plus
  `uranium_dat_inventory.md` / `uranium_structure.md` to report the record
  layout (offsets, field types, which decode path). Verify before coding.
- *Step 3 fork-constant lookup* — searching `$RPG2GBA_POKEEMERALD` headers for
  which names already exist as vanilla constants is broad fan-out search →
  `Explore`/Haiku.
- *Step 6 tests* — scaffolding the three test kinds by mirroring an existing
  `tests/test_pbs_<section>.py` is pattern-replication → Sonnet, then review.
- *Validation* — cross-referencing emitted output against the Uranium wiki
  (pairs with the `pokemon-uranium-wiki` skill) → Sonnet/Haiku.

**Keep on the main (Opus) session** (judgment calls):
- Step 3 resolver / `IdMap` minting — collision and `needs_engine` decisions.
- Step 4 C-emission design and any **map/add/strip** fidelity decision.
- The end-of-Phase-2 review gate (`CLAUDE.md` §9).

---

## Wiring into the pipeline

The converter exposes `run(uranium_src: Path, out_dir: Path, id_map: IdMap) ->
None`. `pipeline.py` `_load_converters()` lazy-imports each module in
`module_order` (`pokemon, moves, items, abilities, tm_hm, trainers, encounters,
metadata, tmpbs`) and registers it if it has a `run`. **The module filename must
match its `module_order` entry.** No manual registration needed beyond that.

```bash
# run/debug a single section
python -m rpg2gba.pipeline phase2 --only <section>
# full clean re-run (verifies idempotence)
python -m rpg2gba.pipeline phase2 --clean
```

The pipeline `IdMap.save()`s back to `reference/uranium_id_map.json` after a run.

---

## Gotchas (bake these in)

- **TLV vs indexed `fput` — pick the right decode path per section.** `items.dat`
  uses self-describing **TLV** tag bytes (`i` varint int, `"` length-prefixed
  string, `0` nil, `T`/`F` bool) inside an offset/length header. Learnsets/egg
  moves use plain **indexed u16 arrays** (length = element count). `moves.dat` is
  **fixed-size flat**. Getting this wrong yields garbage offsets, not a clean
  error — check the layout first.
- **Diacritic folding.** `_naming._fold_accents` NFKD-decomposes and drops
  combining marks (Unicode category `Mn`), so "Poké Ball" → `ITEM_POKE_BALL`, not
  `ITEM_POK_BALL`. Always route names through `to_constant` — never hand-fold.
- **Mixed-case constant regex.** `_naming._CONST_RE`
  (`^\s*(?:#define\s+)?([A-Z][A-Z0-9_]*)\b`) matches both `#define NAME val` and
  enum members (`NAME,` / `NAME = ALIAS, // comment`) when loading fork
  constants. Combined with accent/typo folding, this correctly resolves messy
  internal names like `POKeBALL` → `ITEM_POKE_BALL`.

---

## Worked references

The three completed sections are the canonical examples — imitate their shape.

| Section | Converter | Golden fixture | Worklist |
|---|---|---|---|
| §2.1 species | `src/rpg2gba/pbs_converter/pokemon.py` | `tests/fixtures/pokemon_golden.h` | `intermediate/tandor_dex.json` |
| §2.2 moves | `src/rpg2gba/pbs_converter/moves.py` | `tests/fixtures/moves_golden.h` | `intermediate/move_function_codes.json` |
| §2.3 items | `src/rpg2gba/pbs_converter/items.py` | `tests/fixtures/items_golden.h` | `intermediate/item_field_codes.json` |
