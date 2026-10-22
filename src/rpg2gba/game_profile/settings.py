"""Strict reader for the handful of Essentials `Settings.rb` constants the engine profile needs.

Only `NAME = <int|true|false>` lines are understood. Everything else in the file
is ignored; a *wanted* constant that is missing or has any other value shape
fails loud (CLAUDE.md §4.5). Kept dependency-free so low-level modules
(`capability_sites`) can import it without a cycle.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SETTINGS_RB = REPO_ROOT / "reference" / "scripts_dump" / "002__Settings.rb"

#: Settings.rb constant -> field-move key (also the macro suffix, upper-cased).
BADGE_CONSTANTS: dict[str, str] = {
    "BADGEFORCUT": "cut",
    "BADGEFORFLASH": "flash",
    "BADGEFORROCKSMASH": "rock_smash",
    "BADGEFORSTRENGTH": "strength",
    "BADGEFORSURF": "surf",
    "BADGEFORDIVE": "dive",
    "BADGEFORFLY": "fly",
    "BADGEFORWATERFALL": "waterfall",
}

_LINE = re.compile(r"^([A-Z][A-Z0-9_]*)\s*=\s*(-?\d+|true|false)\s*(?:#.*)?$")


class SettingsError(ValueError):
    """A required Settings.rb constant is missing or malformed."""


def parse_settings(path: Path = DEFAULT_SETTINGS_RB) -> dict[str, int | bool]:
    """Every top-level `NAME = <int|true|false>` assignment in the file.

    Ruby semantics: a later assignment to the same name wins."""
    out: dict[str, int | bool] = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        m = _LINE.match(raw.strip())
        if not m:
            continue
        name, text = m.groups()
        value: int | bool = (text == "true") if text in ("true", "false") else int(text)
        out[name] = value
    return out


def require_int(settings: dict[str, int | bool], name: str) -> int:
    value = settings.get(name)
    if value is None or isinstance(value, bool):
        raise SettingsError(f"Settings.rb: {name} missing or not an integer (got {value!r})")
    return value


def require_bool(settings: dict[str, int | bool], name: str) -> bool:
    value = settings.get(name)
    if not isinstance(value, bool):
        raise SettingsError(f"Settings.rb: {name} missing or not true/false (got {value!r})")
    return value


def badge_requirements(settings: dict[str, int | bool]) -> dict[str, int]:
    """`{move_key: N}` for each BADGEFOR* present (absent ones are omitted)."""
    out: dict[str, int] = {}
    for const, key in BADGE_CONSTANTS.items():
        if const in settings:
            out[key] = require_int(settings, const)
    return out


_DEX_NAMES_START = re.compile(r"^def\s+pbDexNames\b")
_DEX_NAME = re.compile(r'_INTL\("([^"]+)"\)')
# The dump's "Pokédex" is mojibake ("PokÃ©dex"), so match any spelling.
_POKEDEX_SUFFIX = re.compile(r"\s+Pok\S*dex$", re.IGNORECASE)


def regional_dex_name(path: Path = DEFAULT_SETTINGS_RB) -> str:
    """The region of the game's first dex, from `pbDexNames` ("Tandor Pokédex" ->
    "Tandor"). Essentials unlocks only dex 0 at the start
    (`107__PField_Map.rb:204`). Fails loud if the block or its first name is missing."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    for i, raw in enumerate(lines):
        if _DEX_NAMES_START.match(raw.strip()):
            for body in lines[i:]:
                m = _DEX_NAME.search(body)
                if m:
                    name = _POKEDEX_SUFFIX.sub("", m.group(1)).strip()
                    if not name:
                        raise SettingsError(f"Settings.rb: pbDexNames' first entry {m.group(1)!r} names no region")
                    return name
                if body.strip().startswith("]"):
                    break
    raise SettingsError("Settings.rb: no pbDexNames entry")
