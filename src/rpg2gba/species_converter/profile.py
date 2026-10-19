"""Per-game species profile: switch off every stock species family the game never uses.

The expansion wraps each family's data (info, graphics, cries, learnsets,
follower sprites) in `#if P_FAMILY_<NAME>` and leaves every `SPECIES_*` id
defined, so disabling a family drops its data without renumbering anything
(reference/engine_layers_i3_i5.md; measured in
reference/findings/rom_ledger_2026-10-19.md §4a).

The keep-list is the whole game's, not the built chapters': every stock
`SPECIES_*` that `reference/uranium_id_map.json` maps a Uranium species to
(operator, 2026-10-19). The output is a generated header that `#undef`s and
redefines each unused family as FALSE; `engine/include/config/species_enabled.h`
includes it last through a fenced `__has_include` hook.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

PROFILE_HEADER = "rpg2gba_species_profile.gen.h"
#: Engine-relative directory the profile header is written into.
PROFILE_DEST = Path("include/config")

ID_MAP_PATH = Path(__file__).resolve().parents[3] / "reference" / "uranium_id_map.json"

_FAMILY_DEFINE = re.compile(r"^#define\s+(P_FAMILY_[A-Z0-9_]+)\s", re.MULTILINE)
_FAMILY_OPEN = re.compile(r"^#if\s+(P_FAMILY_[A-Z0-9_]+)\s*$")
_FAMILY_CLOSE = re.compile(r"^#endif\s*//\s*(P_FAMILY_[A-Z0-9_]+)")
_SPECIES_ENTRY = re.compile(r"^\s*\[(SPECIES_[A-Z0-9_]+)\]\s*=")
_SPECIES_CONST = re.compile(r"^#define\s+(SPECIES_[A-Z0-9_]+)\s", re.MULTILINE)


@dataclass(frozen=True)
class SpeciesProfile:
    keep: tuple[str, ...]      # P_FAMILY_* names left as the engine has them
    drop: tuple[str, ...]      # P_FAMILY_* names forced FALSE
    used_species: tuple[str, ...]  # the stock SPECIES_* that decided `keep`


def engine_families(fork: Path) -> list[str]:
    """Every `P_FAMILY_*` the engine's `species_enabled.h` defines, in file order."""
    text = (Path(fork) / "include" / "config" / "species_enabled.h").read_text(encoding="utf-8")
    return list(dict.fromkeys(_FAMILY_DEFINE.findall(text)))


def species_to_family(fork: Path) -> dict[str, str]:
    """`SPECIES_*` -> the `P_FAMILY_*` block its species-info entry sits in.

    Parsed from `src/data/pokemon/species_info/gen_*_families.h`, where every
    family is one `#if P_FAMILY_X` ... `#endif //P_FAMILY_X` block. A species
    listed in two families would make the keep decision ambiguous, so it fails
    loud."""
    out: dict[str, str] = {}
    info_dir = Path(fork) / "src" / "data" / "pokemon" / "species_info"
    files = sorted(info_dir.glob("gen_*_families.h"))
    if not files:
        raise FileNotFoundError(f"no gen_*_families.h under {info_dir}")
    for path in files:
        family: str | None = None
        for line in path.read_text(encoding="utf-8").splitlines():
            m = _FAMILY_OPEN.match(line)
            if m:
                family = m.group(1)
                continue
            m = _FAMILY_CLOSE.match(line)
            if m:
                if m.group(1) != family:
                    raise ValueError(f"{path.name}: {m.group(1)} closes while {family} is open")
                family = None
                continue
            m = _SPECIES_ENTRY.match(line)
            if m and family is not None:
                prev = out.setdefault(m.group(1), family)
                if prev != family:
                    raise ValueError(f"{m.group(1)} is in both {prev} and {family}")
    return out


def stock_species(fork: Path) -> frozenset[str]:
    """`SPECIES_*` constants the stock engine header defines (Uranium's are appended
    by a separate generated header, so they are not in this set)."""
    text = (Path(fork) / "include" / "constants" / "species.h").read_text(encoding="utf-8")
    return frozenset(_SPECIES_CONST.findall(text))


def used_stock_species(fork: Path, id_map_path: Path = ID_MAP_PATH) -> list[str]:
    """The stock `SPECIES_*` the game maps any of its species to."""
    id_map = json.loads(Path(id_map_path).read_text(encoding="utf-8"))
    stock = stock_species(fork)
    return sorted({c for c in id_map["species"].values() if c in stock})


def build_profile(fork: Path, id_map_path: Path = ID_MAP_PATH) -> SpeciesProfile:
    families = engine_families(fork)
    owner = species_to_family(fork)
    used = used_stock_species(fork, id_map_path)
    keep: set[str] = set()
    for species in used:
        family = owner.get(species)
        if family is None:
            raise ValueError(
                f"{species} is used by the game but sits in no P_FAMILY_* block of "
                "species_info/gen_*_families.h; cannot decide whether to keep it"
            )
        keep.add(family)
    unknown = keep - set(families)
    if unknown:
        raise ValueError(f"families not defined in species_enabled.h: {sorted(unknown)}")
    return SpeciesProfile(
        keep=tuple(f for f in families if f in keep),
        drop=tuple(f for f in families if f not in keep),
        used_species=tuple(used),
    )


def render_header(profile: SpeciesProfile) -> str:
    lines = [
        "// Generated by rpg2gba (species_converter/profile.py). Do not edit.",
        "// Species families the converted game never uses; their data is compiled out.",
        f"// Kept {len(profile.keep)}: " + ", ".join(profile.keep),
        "",
    ]
    for family in profile.drop:
        lines += [f"#undef {family}", f"#define {family} FALSE"]
    return "\n".join(lines) + "\n"


def write_profile(fork: Path, out_dir: Path, id_map_path: Path = ID_MAP_PATH) -> SpeciesProfile:
    """Write the profile header into `out_dir` and a JSON sidecar for the build
    report; returns the profile. The caller copies the header into the engine."""
    profile = build_profile(fork, id_map_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / PROFILE_HEADER).write_text(render_header(profile), encoding="utf-8")
    (out_dir / "species_profile.json").write_text(
        json.dumps({"keep": profile.keep, "drop": profile.drop,
                    "used_species": profile.used_species}, indent=1) + "\n",
        encoding="utf-8",
    )
    logger.info("  species profile: keep %d families, drop %d (from %d used stock species)",
                len(profile.keep), len(profile.drop), len(profile.used_species))
    return profile
