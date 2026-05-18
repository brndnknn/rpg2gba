# Uranium `.dat` File Inventory

Pokémon Uranium ships its data as binary `.dat` files in `Data/` (alongside `Scripts.rxdata` and `Map*.rxdata`). There is **no** `PBS/` directory — Essentials compiles the human-readable PBS source to these `.dat` files at first run, and only the compiled output is shipped. The 36 files below are the authoritative list extracted from `Uranium.rgssad`.

**Two distinct binary formats are in use — not all `.dat` files are Ruby Marshal:**

- **Ruby Marshal format** (`trainers.dat`, `trainertypes.dat`, `encounters.dat`, `connections.dat`, `metadata.dat`, `townmap.dat`, `berryplants.dat`, `bttrainers.dat`, `phone.dat`, `shadowmoves.dat`): Loaded with `Marshal.load` given correct class stubs.
- **Essentials custom binary format** (`dexdata.dat`, `attacksRS.dat`, `tmpbs.dat`, `eggEmerald.dat`, `evolutions.dat`, `regionals.dat`, `moves.dat`, `items.dat`, `tutor.dat`, `tm.dat`, `metrics.dat`): Written using `fputb`/`fputw`/`fputdw` helpers (1/2/4-byte little-endian int writes). `Marshal.load` raises on these with "incompatible marshal file format". Parse using the write schema in `scripts_dump/175__Compiler.rb`.

See `scripts/spike_dat_inventory.rb` for the probe results that determined which format each file uses.

## Confirmed file list

| File | Likely concept | Custom to Uranium? | Notes |
|---|---|---|---|
| `attacksRS.dat` | **Level-up learnsets by species ID** | No | Custom binary. Index table (species_count × 8 bytes: uint32 offset + uint32 byte-length), then [level uint16, move_id uint16] pairs per species. Confirmed 201 species. "RS" = "Ruby/Sapphire era format" inherited from Essentials; unrelated to `moves.dat`. |
| `berryplants.dat` | Berry growth timers / yields | No | Standard Essentials |
| `btpokemon.dat` | Battle facility (Battle Tower-equivalent) Pokémon templates | Likely yes | Uranium has post-game battle facility content |
| `bttrainers.dat` | Battle facility trainers | Likely yes | Pairs with `btpokemon.dat` |
| `connections.dat` | Map-to-map edge connections | No | Standard Essentials |
| `dexdata.dat` | **Main species table (base stats, types, abilities, etc.)** | No | Custom binary. Flat array of 76 bytes per species, no header. Species 1 at offset 0, species N at offset (N-1)×76. Field layout defined by `requiredtypes`/`optionaltypes` dicts in `Compiler.rb`. Confirmed: 15276 bytes ÷ 76 = **201 species**. |
| `eggEmerald.dat` | Egg group / breeding compatibility | No | Standard Essentials v17 |
| `encounters.dat` | Wild encounter tables per map | No | Standard Essentials |
| `evolutions.dat` | Species evolution conditions | No | Standard Essentials |
| `intl_*.dat` (9 files) | Localization message tables | No | Will not be converted (English-only target) |
| `items.dat` | Item definitions (name, pocket, effect) | No | Standard Essentials |
| `messages.dat` | Compiled dialogue strings | No | Will be regenerated from event scripts during conversion |
| `metadata.dat` | Game-level config (start position, party limits, etc.) | No | Standard Essentials |
| `metrics.dat` | Battler positioning offsets per species (BattlerPlayerY etc.) | No | Standard Essentials sprite metrics |
| `move2anim.dat` | Move-to-animation index | Possible | May be vanilla; verify against compiler |
| `moves.dat` | Compiled move table (the main one) | No | Standard Essentials. Relationship to `attacksRS.dat` unclear |
| `phone.dat` | Phone contact list / call scripts | No | Standard Essentials |
| `regionals.dat` | Tandor regional dex numbers | Yes | Custom binary. Header: uint16 num_regionals (=1), uint16 num_species (=202). Then a 1×202 matrix of uint16 Tandor dex numbers. 200 of 201 species have a Tandor number (1–200); 1 species has no Tandor entry (likely a form or secret placeholder). **Tandor dex = 200 entries.** |
| `shadowmoves.dat` | Shadow Pokémon move set | Yes | Ruby Marshal. **Array[0] — empty.** Shadow mechanic confirmed dead: `trainers.dat` has 0 TPSHADOW hits across 331 trainers. **STRIP confirmed safe.** Nuclear-Horde snag-ball check still needs preservation (unrelated). |
| `tm.dat` | TM/HM → move mapping | No | Standard Essentials |
| `tmpbs.dat` | **Uranium-custom extra move compatibility list per species** | Yes | Custom binary. Same indexed format as `attacksRS.dat` but content is single move IDs (uint16 each, not pairs). Corresponds to the `TMPBS` field in `pokemon.txt` PBS — a Uranium-original field (`optionaltypes` in Compiler.rb, not present in vanilla Essentials v17). Confirmed 201 species. Purpose: likely additional move-compatibility data beyond TM/tutor/egg lists. |
| `townmap.dat` | Region map (Town Map UI) data | No | Standard Essentials |
| `trainerlists.dat` | Trainer category groupings | Possible | Verify; may be Uranium-only |
| `trainers.dat` | Trainer parties (per trainer ID) | No | Standard Essentials |
| `trainertypes.dat` | Trainer class definitions (BGM, AI flag, prize money) | No | Standard Essentials |
| `tutor.dat` | Move tutor → move list | No | Standard Essentials |
| `types.dat` | Type definitions and effectiveness chart | No | **Will contain Nuclear type** — central to Phase 6 decisions |
| `BackupSave.dat` | Player save backup, not data | No | Ignore for conversion |

**Species data confirmed: `dexdata.dat`.** 201 species × 76 bytes = 15,276 bytes flat binary. Field layout from `Compiler.rb` `requiredtypes`/`optionaltypes` dicts. Tandor dex = 200 entries (from `regionals.dat`). One internal species ID (201) has no Tandor number — identity TBD.

## Phase 2 implications

The roadmap's Phase 2 plan assumes parsing PBS text. With no PBS source shipped, the converters must instead parse two distinct binary formats directly:

**Custom Essentials binary** (`dexdata.dat`, `attacksRS.dat`, `tmpbs.dat`, `eggEmerald.dat`, `evolutions.dat`, `regionals.dat`, `moves.dat`, `items.dat`, `tutor.dat`, `tm.dat`): Write Python parsers by reading the `fputb`/`fputw`/`fputdw` write sequences in `scripts_dump/175__Compiler.rb`. No Ruby involved.

**Ruby Marshal** (`trainers.dat`, `trainertypes.dat`, `encounters.dat`, `connections.dat`, `metadata.dat`, etc.): Load with `Marshal.load` in a Ruby script with minimal class stubs, dump to JSON, consume in Python — same approach as the map/script recon scripts.

Key confirmed facts for Phase 2 planning:
1. **Species → `dexdata.dat`**: 201 species, 76 bytes each, field offsets known from Compiler.
2. **Learnsets → `attacksRS.dat`**: indexed binary, 201 species, [level, move_id] pairs.
3. **Shadow Pokémon → STRIP**: 0 TPSHADOW hits in 331 trainers, `shadowmoves.dat` empty.
4. **`tmpbs.dat` → Uranium-custom**: extra move list per species; include in species JSON output.
5. **`types.dat` → 20-type effectiveness matrix**: Nuclear type already encoded. Confirmed 400-entry matrix (20×20). Parse in Phase 6.
6. **`bt*.dat`**: defer to post-Phase-7.
7. **`messages.dat`**: regenerated from event scripts during conversion; skip in Phase 2.
