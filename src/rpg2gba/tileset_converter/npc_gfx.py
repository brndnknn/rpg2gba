"""Phase 5 §5.3 support — Uranium NPC graphic sheet -> pokeemerald OBJ_EVENT_GFX_*.

Uranium places NPCs by RMXP "character sheet" filename (``graphic.character_name``
on a page, e.g. ``"HGSS_000"``, ``"PU-Chyinmunk"``); pokeemerald object_events need
an ``OBJ_EVENT_GFX_*`` constant. This module is the single source of truth (CLAUDE.md
§4.3) for that mapping (`reference/npc_gfx_map.json`, validated against the fork's
real constants — CLAUDE.md §4.7), plus the RMXP boot-state semantics
`metadata_wiring` needs to decide WHICH of an event's pages is even active before it
can ask "what's this event's graphic":

  - `select_boot_page` — RMXP shows the highest-index page whose condition holds at
    boot (all switches off, all variables 0, all self-switches off).
  - `movement_type_for` — RMXP `move_type` (+ `graphic.direction` for the fixed/
    approach/custom cases) -> a pokeemerald `MOVEMENT_TYPE_*`.
  - `is_door_sheet` — the two Uranium door-tile sheet families, which are STRIPPED
    (never emitted as an object_event; a warp_event/tileset door tile is what
    actually makes the door work) rather than mapped to a gfx constant.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from ..pbs_converter._naming import to_constant

logger = logging.getLogger(__name__)

DEFAULT_NPC_GFX_MAP = Path("reference/npc_gfx_map.json")

#: Prefix for every minted Uranium NPC gfx constant (mirrors `_naming.to_constant`
#: usage elsewhere: PREFIX + normalized name -> PREFIX_NORMALIZED_NAME).
GFX_PREFIX = "OBJ_EVENT_GFX_URANIUM"

# RMXP page.move_type values (Essentials/RGSS EventPage#move_type).
MOVE_TYPE_FIXED = 0
MOVE_TYPE_RANDOM = 1
MOVE_TYPE_APPROACH = 2
MOVE_TYPE_CUSTOM = 3

# RMXP graphic.direction values -> the facing suffix on MOVEMENT_TYPE_FACE_*.
_DIRECTION_TO_FACING = {2: "DOWN", 4: "LEFT", 6: "RIGHT", 8: "UP"}

# Uranium's two door-tile sheet families (case-insensitive prefix match).
_DOOR_SHEET_PREFIXES = ("pu-doors", "fkdoors")

_DEFINE_RE = re.compile(r"^\s*#define\s+([A-Za-z_][A-Za-z0-9_]*)")


def gfx_constant_for_sheet(sheet_stem: str) -> str:
    """Deterministic ``OBJ_EVENT_GFX_URANIUM_*`` constant for an RMXP character
    sheet stem (the `character_name` string, e.g. ``"HGSS_000"``,
    ``"PU-Chyinmunk"``). Routes through `_naming.to_constant`, the same
    normalizer every Phase 2 converter uses (CLAUDE.md §4.3 — one normalizer,
    not a bespoke regex here)."""
    return to_constant(GFX_PREFIX, sheet_stem)


def _collect_header_defines(header_paths: list[Path]) -> set[str]:
    """Every ``#define NAME`` identifier across `header_paths`. Fails loud if a
    header doesn't exist — a missing header means we CAN'T validate, which is not
    the same as "nothing to validate" (CLAUDE.md §4.5)."""
    names: set[str] = set()
    for path in header_paths:
        if not path.is_file():
            raise FileNotFoundError(f"npc gfx header not found: {path}")
        for line in path.read_text(encoding="utf-8").splitlines():
            m = _DEFINE_RE.match(line)
            if m:
                names.add(m.group(1))
    return names


def load_npc_gfx_map(json_path: Path, header_paths: list[Path]) -> dict[str, str]:
    """Load + validate `reference/npc_gfx_map.json`: character_name -> gfx
    constant, every constant checked against real ``#define``s in `header_paths`
    (CLAUDE.md §4.7 forward gate — an invented constant fails loud here, not at
    `make modern`). Also fails loud on a duplicate JSON key or an entry missing
    the required ``"gfx"`` field; ``"fallback"``/``"note"`` are informational and
    unchecked."""
    if not json_path.is_file():
        raise FileNotFoundError(f"npc gfx map not found: {json_path}")
    if not header_paths:
        raise ValueError("load_npc_gfx_map requires at least one header_paths entry")

    def _dict_no_dupes(pairs: list[tuple[str, object]]) -> dict[str, object]:
        out: dict[str, object] = {}
        for key, value in pairs:
            if key in out:
                raise ValueError(f"{json_path}: duplicate key {key!r}")
            out[key] = value
        return out

    raw = json.loads(
        json_path.read_text(encoding="utf-8"), object_pairs_hook=_dict_no_dupes
    )
    defines = _collect_header_defines(header_paths)

    result: dict[str, str] = {}
    for character_name, entry in raw.items():
        if "gfx" not in entry:
            raise ValueError(f"{json_path}: entry {character_name!r} missing required 'gfx' field")
        gfx = entry["gfx"]
        if gfx not in defines:
            raise ValueError(
                f"{json_path}: entry {character_name!r} gfx constant {gfx!r} is not "
                f"#define'd in any of {[str(p) for p in header_paths]}"
            )
        result[character_name] = gfx
    return result


def select_boot_page(event: dict) -> dict | None:
    """The page RMXP displays at BOOT (all switches off, all variables 0, all
    self-switches off): the highest-index page whose condition holds, or `None`
    if every page is gated off at boot (e.g. an event that only appears after a
    story switch flips).

    RMXP semantics: a page's condition holds at boot iff it has no switch1/
    switch2/self-switch gate (those all read as OFF at boot) AND either it has no
    variable gate or the variable gate is ``value <= 0`` (the RMXP test is
    ``game_variables[id] >= value``; every variable reads 0 at boot, so
    ``0 >= value`` holds iff ``value <= 0``)."""
    for page in reversed(event["pages"]):
        cond = page["condition"]
        if cond.get("switch1_valid") or cond.get("switch2_valid") or cond.get("self_switch_valid"):
            continue
        if cond.get("variable_valid") and cond.get("variable_value", 0) > 0:
            continue
        return page
    return None


def movement_type_for(page: dict) -> str:
    """The pokeemerald `MOVEMENT_TYPE_*` for a page's RMXP `move_type`:

    - 0 (fixed) / 2 (approach) / 3 (custom) -> ``MOVEMENT_TYPE_FACE_<DIR>`` from
      the page's `graphic.direction` (2/4/6/8 -> DOWN/LEFT/RIGHT/UP).
    - 1 (random) -> ``MOVEMENT_TYPE_WANDER_AROUND``.

    Fails loud on an unknown `move_type` or an unknown `direction` — no silent
    default movement (CLAUDE.md §4.5)."""
    move_type = page["move_type"]
    if move_type == MOVE_TYPE_RANDOM:
        return "MOVEMENT_TYPE_WANDER_AROUND"
    if move_type in (MOVE_TYPE_FIXED, MOVE_TYPE_APPROACH, MOVE_TYPE_CUSTOM):
        direction = page["graphic"]["direction"]
        facing = _DIRECTION_TO_FACING.get(direction)
        if facing is None:
            raise ValueError(f"unknown RMXP facing direction {direction!r}")
        return f"MOVEMENT_TYPE_FACE_{facing}"
    raise ValueError(f"unknown RMXP move_type {move_type!r}")


def is_door_sheet(character_name: str) -> bool:
    """True for Uranium's two door-tile sheet families (case-insensitive prefix
    match on ``"PU-doors"`` / ``"FKdoors"``). These are the door's own tile
    graphic riding along as an "event" — the real door behavior is the warp_event
    plus the tileset's door metatile, so a door-sheet event is stripped rather
    than mapped to a gfx constant."""
    name = (character_name or "").lower()
    return name.startswith(_DOOR_SHEET_PREFIXES)
