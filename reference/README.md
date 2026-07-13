# reference/ layout

Hand-authored docs and derived data the build agent and humans read. Organized 2026-07-13.

| Location | What goes there |
|---|---|
| *top level* | Source-of-truth JSONs pinned by CLAUDE.md §4.3 (`uranium_id_map.json`, `tileset_map.json`, `strip_list.json`, `map_name_overrides.json`, `terrain_tag_map.json`, `npc_gfx_map.json`, `animation_names.json`, `uranium_switches.json`, `uranium_variables.json`, gitignored `tileset_map.gen.json`) + the memory files (`memory-protocol.md`, `memory-archive.md`) |
| `uranium_data/` | Passive JSON dumps from the Uranium source (names, descriptions, dex entries, trainer speeches, script texts). Written by recon scripts, read by `pbs_converter/` |
| `recon/` | Phase-0/1 investigation docs of the Uranium source (structure, inventories, command censuses) |
| `guides/` | Active how-to and mapping docs (Poryscript cheatsheet, RGSS command reference, Essentials→Emerald ledger, engine extension surface, runbooks) |
| `viewer/` | Map viewer + map walker tooling docs |
| `findings/` | Dated session findings, censuses, audits |
| `archive/` | Retired plans and historical records — paths inside are left as they were written |
| `map_feedback/` | Per-map issue JSONs written by the map viewer's feedback UI |
| `scripts_dump/` | Verbatim Uranium Ruby scripts (gitignored — never committed) |

New files: match the category above; only SoT JSONs and memory files belong at top level.
Historical docs (`archive/`, `memory-archive.md`) intentionally keep pre-reorg paths.
