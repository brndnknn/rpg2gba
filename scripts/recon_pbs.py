#!/usr/bin/env python3
"""Phase 0.2 — PBS file inventory.

Counts entries in each PBS file, flags non-standard files, and checks pokemon.txt
for custom fields that might indicate Uranium-specific extensions.

Usage:
    RPG2GBA_URANIUM_SRC=/path/to/uranium python scripts/recon_pbs.py
"""
import os
import re
from pathlib import Path

URANIUM_SRC = Path(os.environ["RPG2GBA_URANIUM_SRC"])
PBS_DIR = URANIUM_SRC / "PBS"
OUT = Path("reference/pbs_inventory.md")

VANILLA_PBS = {
    "abilities.txt", "encounters.txt", "items.txt", "metadata.txt",
    "moves.txt", "phone.txt", "pokemon.txt", "pokemonforms.txt",
    "ribbons.txt", "shadow.txt", "tm.txt", "townmap.txt", "regionmap.txt",
    "trainers.txt", "trainertypes.txt",
}

# Known standard fields in vanilla Essentials pokemon.txt (v15/v16 era)
STANDARD_POKEMON_FIELDS = {
    "Name", "InternalName", "Type1", "Type2", "BaseStats", "GenderRate",
    "GrowthRate", "BaseEXP", "EffortPoints", "Rareness", "Happiness",
    "Abilities", "HiddenAbility", "Moves", "TutorMoves", "EggMoves",
    "Compatibility", "StepsToHatch", "Height", "Weight", "Color", "Shape",
    "Habitat", "Kind", "Pokedex", "FormName", "BattlerPlayerX", "BattlerPlayerY",
    "BattlerEnemyX", "BattlerEnemyY", "BattlerAltitude", "BattlerShadowX",
    "BattlerShadowSize", "Evolutions", "WildItemCommon", "WildItemUncommon",
    "WildItemRare", "RegionalNumbers", "MegaStone", "MegaMove", "MegaMessage",
}


def count_sections(text: str) -> int:
    return len(re.findall(r"^\[", text, re.MULTILINE))


def all_field_names(path: Path) -> set[str]:
    fields = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^([A-Za-z][A-Za-z0-9]*)\s*=", line)
        if m:
            fields.add(m.group(1))
    return fields


if not PBS_DIR.exists():
    raise SystemExit(f"PBS directory not found: {PBS_DIR}")

pbs_files = sorted(PBS_DIR.glob("*.txt"))
rows = []
for f in pbs_files:
    text = f.read_text(encoding="utf-8", errors="replace")
    sections = count_sections(text)
    standard = f.name.lower() in VANILLA_PBS
    note = "" if standard else "⚠ non-standard"
    rows.append((f.name, sections, note))

pokemon_txt = PBS_DIR / "pokemon.txt"
custom_fields: list[str] = []
if pokemon_txt.exists():
    found = all_field_names(pokemon_txt)
    custom_fields = sorted(found - STANDARD_POKEMON_FIELDS)

lines = [
    "# PBS File Inventory",
    "",
    f"PBS directory: `{PBS_DIR}`",
    "",
    "| File | Sections | Notes |",
    "|---|---|---|",
    *[f"| `{name}` | {n} | {note} |" for name, n, note in rows],
    "",
    "## Custom fields in pokemon.txt",
    "",
    "Fields not present in vanilla Essentials v15/v16. May indicate Uranium-specific extensions.",
    "",
]
if custom_fields:
    lines += [f"- `{f}`" for f in custom_fields]
else:
    lines.append("None detected.")

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"Written: {OUT}")
