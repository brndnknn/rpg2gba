"""Single source of truth for *which* Uranium maps a build targets.

Historically the map set was hard-coded as ``SLICE_MAP_IDS = [49, 48, 32]`` in five
separate scripts. This module replaces those copies: the slice constant lives here
once, and :func:`resolve_map_ids` provides the "slice vs full" selector the Map
Walker's Phase B needs (build all 199 maps) while keeping the 3-map slice
reproducible for regression comparison.

Profiles:
  * ``"slice"`` — the proven 3-map pathfinder slice (1F spawn, 2F, Moki Town).
  * ``"full"``  — every ``MapNNN.json`` on disk, minus whole-map STRIP entries.
  * a comma-separated id list (e.g. ``"49,48,32,7"``) — an explicit ad-hoc batch,
    used to validate the all-maps pipeline incrementally before the full corpus.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# The proven 3-map pathfinder slice, in boot order: Map 49 (Player's House 1F,
# spawn @7,7), Map 48 (2F), Map 32 (Moki Town). Kept for reproducible slice builds.
SLICE_MAP_IDS: list[int] = [49, 48, 32]

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
        return discover_all_map_ids(maps_dir, strip_list=strip_list)

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
