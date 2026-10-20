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
