"""Region-map sections: which named location each map belongs to (PROJECT_TODO #140).

Uranium shows a location popup on entering a map whose metadata sets `ShowArea`,
naming it with the map's MapInfos name, and skips it when that name equals the
map just left (`101__PField_Field.rb:1895-1909`). Interiors never set `ShowArea`.

The engine's equivalent is the map header's `region_map_section` (a `MAPSEC_*`
whose `gRegionMapEntries` name the popup prints) plus `show_map_name`. Operator
rulings 2026-10-21 (`reference/intermission_a1_a2.md` §3):

- **One section per location.** A map belongs to the section of its nearest
  self-or-ancestor (MapInfos `parent_id` tree) that sets `ShowArea`, keyed by that
  map's MapInfos name, so a town's houses share the town's section and a cave's
  floors share one. `show_map_name` is the map's own `ShowArea`.
- **Names are what Uranium displays**, upper-cased like Emerald's popups.
- **Region-map coordinates stay zero** until Tandor's region map is converted.
- `OW_HIDE_REPEAT_MAP_POPUP` stays stock (off).

A staged map with no `ShowArea` self-or-ancestor fails loud: 32 maps game-wide
(Route 11, the dream maps, the Hall of Fame, ...) have none, Uranium shows no popup
there, and which section they take is a decision for the chapter that first builds
one.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from ..map_split.ids import origin_of
from ..pbs_converter._naming import to_constant

logger = logging.getLogger(__name__)

# Section values share a byte with the METLOC_* specials, which start at 0xFD
# (`region_map_sections.constants.json.txt`); MAPSEC_NONE follows the last entry.
METLOC_SPECIAL_START = 0xFD


@dataclass(frozen=True)
class MapSection:
    """A named location: its constant and the popup's (upper-cased) name."""

    const: str
    name: str


def section_for(uid: int, map_infos: dict, metadata: dict) -> MapSection:
    """The section map `uid` belongs to. `map_infos` is the deserialized
    `map_infos.json`; `metadata` is `map_metadata.json`'s `maps` dict."""
    origin = origin_of(uid)
    seen: set[int] = set()
    mid: int | None = origin
    while mid and mid not in seen:
        seen.add(mid)
        if (metadata.get(str(mid)) or {}).get("show_area"):
            name = map_infos[str(mid)]["name"]
            const = to_constant("MAPSEC", name)
            if const == "MAPSEC_":
                raise ValueError(f"map {uid}: section map {mid} name {name!r} yields no constant")
            return MapSection(const=const, name=name.upper())
        mid = (map_infos.get(str(mid)) or {}).get("parent_id")
    raise ValueError(
        f"map {uid}: no ShowArea map at or above it in MapInfos, so it belongs to no "
        "location Uranium names (Uranium shows no popup there). Which section it takes "
        "is undecided (PROJECT_TODO #140): ask the operator."
    )


def shows_map_name(uid: int, metadata: dict) -> bool:
    """`show_map_name`: Uranium's `ShowArea` flag for this map itself."""
    return bool((metadata.get(str(origin_of(uid))) or {}).get("show_area"))


def load_inputs(map_infos_path: Path, metadata_path: Path) -> tuple[dict, dict]:
    """(map_infos, metadata `maps` dict) from the two intermediate JSON files."""
    map_infos = json.loads(map_infos_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")).get("maps", {})
    return map_infos, metadata


def overlay_sections(upstream: dict, sections: list[MapSection]) -> dict:
    """The engine's `region_map_sections.json` with `sections` appended (sorted
    by constant, deduplicated; upstream order untouched, so no stock section
    renumbers). Coordinates are left out, which the template reads as zero.
    Fails loud on a clash with a stock section, a name with two spellings, or
    an overflow into the METLOC specials."""
    stock = upstream.get("map_sections", [])
    stock_ids = {e["id"] for e in stock}
    by_const: dict[str, MapSection] = {}
    for s in sections:
        if s.const in stock_ids:
            raise ValueError(
                f"{s.const} ({s.name!r}) collides with a stock region-map section; "
                "decide a distinct name (PROJECT_TODO #140)"
            )
        prior = by_const.setdefault(s.const, s)
        if prior.name != s.name:
            raise ValueError(f"{s.const} is named both {prior.name!r} and {s.name!r}")
    added = [{"id": s.const, "name": s.name} for s in sorted(by_const.values(), key=lambda s: s.const)]
    total = len(stock) + len(added)  # == MAPSEC_NONE's value
    if total >= METLOC_SPECIAL_START:
        raise ValueError(
            f"{len(added)} game sections + {len(stock)} stock puts MAPSEC_NONE at {total}, "
            f"into the METLOC specials (0x{METLOC_SPECIAL_START:X}); compile out stock sections first"
        )
    merged = dict(upstream)
    merged["map_sections"] = list(stock) + added
    return merged
