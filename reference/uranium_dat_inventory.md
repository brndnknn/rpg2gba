# Uranium `.dat` File Inventory

Pokémon Uranium ships its data as binary `.dat` files in `Data/` (alongside `Scripts.rxdata` and `Map*.rxdata`). There is **no** `PBS/` directory — Essentials compiles the human-readable PBS source to these `.dat` files at first run, and only the compiled output is shipped. The 36 files below are the authoritative list extracted from `Uranium.rgssad`.

The `.dat` files are Ruby `Marshal.dump` output (same format as `.rxdata`). Reading them requires the matching Essentials class definitions to be in scope — see `scripts_dump/175__Compiler.rb` for the writing logic, which dictates the read schema.

## Confirmed file list

| File | Likely concept | Custom to Uranium? | Notes |
|---|---|---|---|
| `attacksRS.dat` | Move data in Ruby/Sapphire-compatible format | Possible | "RS" suffix suggests R/S-style; relationship to `moves.dat` not yet confirmed |
| `berryplants.dat` | Berry growth timers / yields | No | Standard Essentials |
| `btpokemon.dat` | Battle facility (Battle Tower-equivalent) Pokémon templates | Likely yes | Uranium has post-game battle facility content |
| `bttrainers.dat` | Battle facility trainers | Likely yes | Pairs with `btpokemon.dat` |
| `connections.dat` | Map-to-map edge connections | No | Standard Essentials |
| `dexdata.dat` | Pokédex flavor entries (height/weight/category/description) | No | Standard Essentials |
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
| `regionals.dat` | Regional Pokédex tables (Tandor dex) | Likely yes | Uranium-specific dex region |
| `shadowmoves.dat` | Shadow Pokémon move set | Yes | Engine is code-complete in `scripts_dump/124_Pokemon_ShadowPokemon.rb` (806 lines, loads `shadowmoves.dat` via `makeShadow`) but **never activated** — no map/trainer sets `snagMachine=true`. Recommended: STRIP after confirming `trainers.txt` has no `TPSHADOW=true` rows. The Nuclear-Horde feature (script 224) aliases `pbIsSnagBall?` and must be preserved separately. |
| `tm.dat` | TM/HM → move mapping | No | Standard Essentials |
| `tmpbs.dat` | Unknown — name suggests "temp PBS" intermediate | Yes | Investigate; possibly compilation scratch left in build |
| `townmap.dat` | Region map (Town Map UI) data | No | Standard Essentials |
| `trainerlists.dat` | Trainer category groupings | Possible | Verify; may be Uranium-only |
| `trainers.dat` | Trainer parties (per trainer ID) | No | Standard Essentials |
| `trainertypes.dat` | Trainer class definitions (BGM, AI flag, prize money) | No | Standard Essentials |
| `tutor.dat` | Move tutor → move list | No | Standard Essentials |
| `types.dat` | Type definitions and effectiveness chart | No | **Will contain Nuclear type** — central to Phase 6 decisions |
| `BackupSave.dat` | Player save backup, not data | No | Ignore for conversion |

**Where is species data?** Notably absent from this list: a `pokemon.dat` or `species.dat`. In Essentials v17 the compiled species table is typically named `species.dat` or stored under an Essentials-specific name. It may live inside `dexdata.dat` (combined with Pokédex flavor) or under a name we haven't recognized — `attacksRS.dat` and `tmpbs.dat` are both candidates worth opening. **Spike task before Phase 2:** open the unrecognized `.dat` files in Ruby and print their top-level class to confirm. (See Phase 2 implications below.)

## Phase 2 implications

The roadmap's Phase 2 plan assumes parsing PBS text. With no PBS source shipped, the converters must instead:

1. **Extend the Ruby deserializer.** Add a script (e.g., `scripts/dump_dat.rb`) that loads each `.dat` with `Marshal.load`, given the right class stubs, and dumps to JSON.
2. **Map the JSON to the existing converter modules.** The Python modules under `src/rpg2gba/pbs_converter/` consume the JSON instead of text.
3. **Identify the species table.** Cannot start `pbs_converter/pokemon.py` until we know which `.dat` holds species data.
4. **Confirm `types.dat` shape.** Determines whether Nuclear type is already represented as a 15th type in the table, and how its effectiveness rules are encoded — feeds Phase 6 directly.
5. **Decide per Uranium-only file.** `regionals.dat` (convert), `shadowmoves.dat` (recommend strip), `tmpbs.dat` (investigate), `bt*.dat` (defer to post-Phase-7 if scope allows).

The deterministic-converter goal is preserved — the parser just lives one level deeper (Ruby Marshal instead of `.txt`).
