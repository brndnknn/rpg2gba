"""Single source of truth for *which* Uranium maps a build targets.

Historically the map set was hard-coded as ``SLICE_MAP_IDS = [49, 48, 32]`` in five
separate scripts. This module replaces those copies: the slice constant lives here
once, and :func:`resolve_map_ids` provides the "slice vs full" selector the Map
Walker's Phase B needs (build all 199 maps) while keeping the 3-map slice
reproducible for regression comparison.

Profiles:
  * ``"slice"`` — the proven 3-map pathfinder slice (1F spawn, 2F, Moki Town).
  * ``"full"``  — every ``MapNNN.json`` on disk, minus whole-map STRIP entries and
    minus the Map Walker technical exclusions (:data:`WALKER_EXCLUDED_MAP_IDS` =
    overflow maps + empty placeholder maps).
  * a comma-separated id list (e.g. ``"49,48,32,7"``) — an explicit ad-hoc batch,
    used to validate the all-maps pipeline incrementally before the full corpus.
    Explicit lists are NOT filtered for overflow — asking for an overflow map by id
    is honored and fails loud at emit time (the 1024-metatile budget guard).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# The proven 3-map pathfinder slice, in boot order: Map 49 (Player's House 1F,
# spawn @7,7), Map 48 (2F), Map 32 (Moki Town). Kept for reproducible slice builds.
SLICE_MAP_IDS: list[int] = [49, 48, 32]

# Maps that overflow a GBA per-tileset budget even as a dedicated per-map tileset,
# so they can't build (map_walker_plan §5.4, decision #14). A tileset has TWO hard
# 1024 caps (each = primary 512 + secondary 512): metatile ids AND distinct 8x8
# tiles. Two groups, both excluded from the v1 walker "full" corpus; a metatile/tile
# dedup or intra-map-split pass is the planned follow-up:
#   * metatile overflow (census, >1024 metatiles)
#   * 8x8-tile overflow (measured via the real render+quantize path, >1024 tiles)
# Scoped to "full" only — an explicit id-list naming one is honored and fails loud
# at emit time (the budget guard in emit_tileset).
WALKER_OVERFLOW_MAP_IDS: frozenset[int] = frozenset(
    {94, 101, 187, 40, 84, 117, 143, 71, 144}  # >1024 metatiles
    | {60, 122, 128, 146, 151, 209, 213}       # >1024 8x8 tiles
)

# Blank placeholder maps: their tile grid is entirely empty (0 non-empty columns),
# so no tileset can be built for them and there is nothing to display. Found by the
# corpus pre-flight; excluded from the walker "full" corpus like the overflow maps.
WALKER_EMPTY_MAP_IDS: frozenset[int] = frozenset({14, 30, 38, 55, 56})

# Everything the walker "full" corpus drops (technical exclusions, not game STRIPs).
WALKER_EXCLUDED_MAP_IDS: frozenset[int] = WALKER_OVERFLOW_MAP_IDS | WALKER_EMPTY_MAP_IDS

_MAP_FILE_RE = re.compile(r"^Map(\d+)\.json$")


def discover_all_map_ids(maps_dir: Path, *, strip_list: Path | None = None) -> list[int]:
    """Return every Uranium map id with a ``MapNNN.json`` under *maps_dir*, sorted
    ascending, with whole-map STRIP entries removed.

    Map numbering is non-contiguous (gaps where Uranium deleted maps), so we
    discover from disk rather than assuming a range.
    """
    ids: list[int] = []
    for path in maps_dir.glob("Map*.json"):
        match = _MAP_FILE_RE.match(path.name)
        if match:
            ids.append(int(match.group(1)))
    if not ids:
        raise FileNotFoundError(f"no MapNNN.json files under {maps_dir}")
    stripped = _stripped_map_ids(strip_list)
    return sorted(i for i in ids if i not in stripped)


def _stripped_map_ids(strip_list: Path | None) -> set[int]:
    """Whole-map ids marked for exclusion in ``reference/strip_list.json``."""
    if strip_list is None or not strip_list.exists():
        return set()
    data = json.loads(strip_list.read_text(encoding="utf-8"))
    return {int(entry["id"]) for entry in data.get("maps", [])}


def parse_map_ids(spec: str, maps_dir: Path, *, strip_list: Path | None = None) -> list[int]:
    """Resolve a map-set *spec* to a concrete id list.

    *spec* is ``"slice"``, ``"full"``, or a comma-separated id list. Explicit ids
    are validated against what exists on disk (fail-loud on a typo'd / missing id).
    """
    spec = spec.strip()
    if spec == "slice":
        return list(SLICE_MAP_IDS)
    if spec == "full":
        ids = discover_all_map_ids(maps_dir, strip_list=strip_list)
        return [i for i in ids if i not in WALKER_EXCLUDED_MAP_IDS]

    try:
        requested = [int(tok) for tok in spec.split(",") if tok.strip()]
    except ValueError as exc:
        raise ValueError(
            f"bad map-set spec {spec!r}: expected 'slice', 'full', or a comma-separated id list"
        ) from exc
    if not requested:
        raise ValueError(f"empty map-set spec {spec!r}")

    available = set(discover_all_map_ids(maps_dir, strip_list=strip_list))
    missing = [i for i in requested if i not in available]
    if missing:
        raise ValueError(
            f"map id(s) {missing} not present on disk under {maps_dir} (or STRIP-listed)"
        )
    return requested


# Back-compat alias for the older selector name used in early plan drafts.
def resolve_map_ids(profile: str, maps_dir: Path, *, strip_list: Path | None = None) -> list[int]:
    """Alias for :func:`parse_map_ids`; *profile* is ``"slice"``/``"full"``/id-list."""
    return parse_map_ids(profile, maps_dir, strip_list=strip_list)
