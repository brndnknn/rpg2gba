"""Generate `include/config/rpg2gba_game.gen.h`: the game facts hand-typed in engine C before I3 S4.

Three facts, each read by a generic fenced hook in the engine that falls back to
stock behaviour when its macro is absent:

* HM badge gates (`field_move.c`) from `Settings.rb` HIDDENMOVESCOUNTBADGES / BADGEFOR*.
* The white-out flag (`overworld.c`): the flag-registry name of `STARTING_OVER_SWITCH`.
* The new-game spawn (`new_game.c`): Essentials `MetadataHome`, resolved to a `MAP_*`
  through `heal_locations` (the same resolution that emits the start heal location).
* The phone's name (`strings.c` start menu, `event_scripts.s` Match Call registration
  line, #141): from the game's own "Registered {1} in the <name>." message. The
  registration line is assembly, so it is written as `data/scripts/rpg2gba_phone_text.inc`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from rpg2gba.conversion_agent.flag_registry import load_label_tables
from rpg2gba.pbs_converter._c_emit import generated_banner
from rpg2gba.pbs_converter._naming import to_constant
from rpg2gba.pbs_converter.heal_locations import (
    DEFAULT_MAP_CONSTANTS_JSON,
    DEFAULT_METADATA_HEADER,
    START_ANCHOR_ID,
    _load_map_constants,
    initial_anchor,
)

from .settings import (
    DEFAULT_PHONE_RB,
    DEFAULT_SETTINGS_RB,
    REPO_ROOT,
    SettingsError,
    badge_requirements,
    parse_settings,
    phone_name,
    require_bool,
    require_int,
)

logger = logging.getLogger(__name__)

GENERATOR = "rpg2gba.game_profile.header"
HEADER_REL = Path("include/config/rpg2gba_game.gen.h")
PHONE_TEXT_REL = Path("data/scripts/rpg2gba_phone_text.inc")
DEFAULT_SWITCHES_JSON = REPO_ROOT / "reference" / "uranium_switches.json"
DEFAULT_VARIABLES_JSON = REPO_ROOT / "reference" / "uranium_variables.json"

#: Macro suffix per BADGEFOR* key.
_BADGE_ORDER = ("cut", "flash", "rock_smash", "strength", "surf", "dive", "fly", "waterfall")


@dataclass(frozen=True)
class GameFacts:
    badges_count_mode: bool | None      # None when no BADGEFOR* is present
    badge_requirements: dict[str, int]  # move key -> N (0 = no badge needed)
    whiteout_flag: str                  # FLAG_* of STARTING_OVER_SWITCH
    new_game_map: str                   # MAP_*
    new_game_x: int
    new_game_y: int
    new_game_heal_location: str         # HEAL_LOCATION_*
    phone_name: str                     # as the UI shows it, e.g. "POKéPOD"


def whiteout_flag(
    settings: dict[str, int | bool] | None = None,
    switches_json: Path = DEFAULT_SWITCHES_JSON,
    variables_json: Path = DEFAULT_VARIABLES_JSON,
) -> str:
    """The flag-registry name of `STARTING_OVER_SWITCH` (what the engine's
    `RPG2GBA_WHITEOUT_FLAG` expands to). Fails loud if the switch is unnamed or
    is a runtime predicate."""
    if settings is None:
        settings = parse_settings()
    switch_id = require_int(settings, "STARTING_OVER_SWITCH")
    switches, _vars = load_label_tables(switches_json, variables_json)
    label = switches.get(switch_id)
    if not label:
        raise SettingsError(f"STARTING_OVER_SWITCH = {switch_id} has no name in {switches_json}")
    if label.startswith("s:"):
        raise SettingsError(
            f"switch {switch_id} ({label!r}) is a runtime predicate; it has no FLAG_*"
        )
    return to_constant("FLAG", label)


def build_facts(
    settings_rb: Path = DEFAULT_SETTINGS_RB,
    switches_json: Path = DEFAULT_SWITCHES_JSON,
    variables_json: Path = DEFAULT_VARIABLES_JSON,
    map_constants_json: Path = DEFAULT_MAP_CONSTANTS_JSON,
    metadata_header: Path = DEFAULT_METADATA_HEADER,
    phone_rb: Path = DEFAULT_PHONE_RB,
) -> GameFacts:
    settings = parse_settings(settings_rb)

    badges = badge_requirements(settings)
    count_mode = require_bool(settings, "HIDDENMOVESCOUNTBADGES") if badges else None
    for key, n in badges.items():
        if n < 0 or n > 8:
            raise SettingsError(f"Settings.rb: badge requirement for {key} is {n}, outside 0..8")

    flag = whiteout_flag(settings, switches_json, variables_json)

    anchor = initial_anchor(metadata_header)
    consts = _load_map_constants(map_constants_json)
    entry = consts.get(anchor.map_id)
    if entry is None:
        raise KeyError(
            f"MetadataHome map {anchor.map_id} has no entry in {map_constants_json}"
        )
    return GameFacts(
        badges_count_mode=count_mode,
        badge_requirements=badges,
        whiteout_flag=flag,
        new_game_map=entry["map_const"],
        new_game_x=anchor.x,
        new_game_y=anchor.y,
        new_game_heal_location=START_ANCHOR_ID,
        phone_name=ui_caps(phone_name(phone_rb)),
    )


def ui_caps(name: str) -> str:
    """Emerald's capitalisation for a proper noun in UI text: upper case, but the
    accented e stays lower case, as in POKéNAV and POKéDEX."""
    return name.upper().replace("\u00c9", "\u00e9")


def render_header(facts: GameFacts) -> str:
    banner = generated_banner(
        "Settings.rb + metadata.dat + switch names", GENERATOR, timestamp=False
    )
    lines = [
        banner.rstrip("\n"),
        "#ifndef GUARD_CONFIG_RPG2GBA_GAME_GEN_H",
        "#define GUARD_CONFIG_RPG2GBA_GAME_GEN_H",
        "",
    ]
    if facts.badges_count_mode is not None:
        lines += [
            "// Hidden-move gates. COUNT_MODE TRUE: needs at least N badges of any kind;",
            "// FALSE: needs badge number N specifically. N = 0: no badge needed.",
            f"#define RPG2GBA_FIELD_MOVE_BADGES_COUNT_MODE {'TRUE' if facts.badges_count_mode else 'FALSE'}",
        ]
        for key in _BADGE_ORDER:
            if key in facts.badge_requirements:
                lines.append(
                    f"#define RPG2GBA_FIELD_MOVE_BADGE_{key.upper()} {facts.badge_requirements[key]}"
                )
        lines.append("")
    lines += [
        "// Set on every white-out (Essentials pbStartOver).",
        f"#define RPG2GBA_WHITEOUT_FLAG {facts.whiteout_flag}",
        "",
        "// New-game spawn (Essentials MetadataHome).",
        f"#define RPG2GBA_NEW_GAME_MAP {facts.new_game_map}",
        f"#define RPG2GBA_NEW_GAME_X {facts.new_game_x}",
        f"#define RPG2GBA_NEW_GAME_Y {facts.new_game_y}",
        f"#define RPG2GBA_NEW_GAME_HEAL_LOCATION {facts.new_game_heal_location}",
        "",
        "// The phone's name: the start-menu label, and the Match Call registration line",
        f"// ({PHONE_TEXT_REL}, which event_scripts.s includes when this is defined).",
        f'#define RPG2GBA_PHONE_MENU_LABEL _("{facts.phone_name}")',
        "#define RPG2GBA_PHONE_TEXT_INC 1",
        "",
        "#endif // GUARD_CONFIG_RPG2GBA_GAME_GEN_H",
        "",
    ]
    return "\n".join(lines)


def render_phone_text(facts: GameFacts) -> str:
    """`gText_RegisteredTrainerinPokeNav` (event_scripts.s) with the game's phone name."""
    return (
        f"@ GENERATED by {GENERATOR} -- do not edit.\n"
        "gText_RegisteredTrainerinPokeNav::\n"
        '\t.string "Registered {STR_VAR_1} {STR_VAR_2}\\n"\n'
        f'\t.string "in the {facts.phone_name}.$"\n'
    )


def install(
    fork: Path,
    settings_rb: Path = DEFAULT_SETTINGS_RB,
    switches_json: Path = DEFAULT_SWITCHES_JSON,
    variables_json: Path = DEFAULT_VARIABLES_JSON,
    map_constants_json: Path = DEFAULT_MAP_CONSTANTS_JSON,
    metadata_header: Path = DEFAULT_METADATA_HEADER,
) -> Path:
    """Write `<fork>/include/config/rpg2gba_game.gen.h`; byte-stable. Returns the engine-relative path."""
    facts = build_facts(settings_rb, switches_json, variables_json,
                        map_constants_json, metadata_header)
    for rel, text in ((HEADER_REL, render_header(facts)), (PHONE_TEXT_REL, render_phone_text(facts))):
        dest = Path(fork) / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists() or dest.read_text(encoding="utf-8") != text:
            dest.write_text(text, encoding="utf-8")
    logger.info("  game profile: spawn %s (%d,%d), whiteout %s, %d badge gates",
                facts.new_game_map, facts.new_game_x, facts.new_game_y,
                facts.whiteout_flag, len(facts.badge_requirements))
    return HEADER_REL
