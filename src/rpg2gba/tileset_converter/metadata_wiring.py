"""Phase 5 §5.3 — Map metadata wiring (the map.json assembler).

ASSIGNMENT
==========
Objective
    Assemble each `data/maps/<Name>/map.json`: the header, the OBJECT EVENTS
    (every Uranium event placed at its (x, y) with its `script` pointing at the
    Phase 4-generated dispatcher), the WARP EVENTS, and the WILD-ENCOUNTER hookup.

The interesting part — the per-page dispatcher (deterministic; YOUR job)
    An RMXP event has multiple *pages*, and which page is active is chosen at
    runtime by the page `condition` (switch on / variable >= N / self-switch).
    pokeemerald has no page concept: one object_event points at one script label.
    So you generate a small dispatcher script per multi-page event:

        Map001_npc_Dispatch::
            goto_if_set FLAG_..., Map001_npc_Page2   @ from page-2's condition
            goto Map001_npc_Page1

    The page *bodies* (`Map001_npc_PageN`) already exist — Phase 4 produced them.
    You wire the selection skeleton from the structured Phase 3 page conditions.
    This was prototyped by hand in the rung-3 spike (see MEMORY.md). It is
    deterministic control flow, NOT a conversion-agent task (CLAUDE.md §1/§11).

Inputs
    MapNNN.json (events: each has id, name, x, y, pages[].condition/graphic),
    the MapConstantRegistry, the per-map .pory block labels from Phase 4,
    intermediate/wild_encounters.json (keyed by Uranium map id),
    intermediate/map_metadata.json (music/weather/map_type/healing-spot).
Output
    output/uranium-build/porymap/maps/<Name>/map.json

Constraints
    - Each event placed exactly once at its correct (x, y).
    - `script` labels match the Phase 4 .pory block names EXACTLY (or the
      dispatcher you emit, which in turn gotos them). Fail loud on a label the
      .pory doesn't define.
    - Encounter table present iff the map has wild slots.

Acceptance
    [ ] each event -> one object_event at the right (x, y)
    [ ] script labels resolve to real .pory blocks (or generated dispatchers)
    [ ] encounter table present iff wild slots exist
    [ ] page dispatch reflects the Phase 3 page conditions (golden test)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .map_constants import MapConstants

logger = logging.getLogger(__name__)

# Default elevation for placed NPCs (pokeemerald convention; refine per map later).
DEFAULT_ELEVATION = 3


@dataclass
class ObjectEvent:
    """One placed event -> a pokeemerald object_event entry in map.json."""

    x: int
    y: int
    graphics_id: str  # OBJ_EVENT_GFX_* — Q-for-later: map RMXP graphic -> gfx const
    script: str  # the dispatcher / page-1 label in the Phase 4 .pory
    flag: str = "0"  # visibility flag (0 = always shown)
    movement_type: str = "MOVEMENT_TYPE_NONE"
    elevation: int = DEFAULT_ELEVATION


@dataclass
class WarpEvent:
    """A code-201 transfer -> a pokeemerald warp_event. dest_map is a MAP_* const."""

    x: int
    y: int
    dest_map: str
    dest_warp_id: int = 0


@dataclass
class MapFile:
    """The assembled map.json. Serialize with `to_json_dict()`."""

    consts: MapConstants
    music: str = "MUS_LITTLEROOT"
    weather: str = "WEATHER_NONE"
    map_type: str = "MAP_TYPE_TOWN"
    object_events: list[ObjectEvent] = field(default_factory=list)
    warp_events: list[WarpEvent] = field(default_factory=list)
    connections: list[dict] = field(default_factory=list)  # filled by connections.py (5.4)

    def to_json_dict(self) -> dict:
        """Build the dict matching the fork's data/maps/<Name>/map.json schema."""
        raise NotImplementedError("5.3: assemble the map.json dict")


def build_object_events(
    map_json: dict, pory_labels: set[str], consts: MapConstants
) -> list[ObjectEvent]:
    """Place every Uranium event as an object_event pointing at its script label.

    For a multi-page event, point `script` at the dispatcher you emit (see
    `build_page_dispatcher`); for single-page, point straight at the page label.
    Fail loud if the target label isn't in `pory_labels`."""
    raise NotImplementedError("5.3: events -> object_events with resolved script labels")


def build_page_dispatcher(event: dict, consts: MapConstants) -> str | None:
    """Emit a Poryscript dispatcher for a multi-page event from its page conditions.

    Returns the dispatcher script text (and its label is what object_events point
    at), or None for a single-page event (no dispatch needed). Read each page's
    `condition` (switch_id/switch_valid, variable_id/variable_value,
    self_switch_ch/self_switch_valid) and emit goto_if_set / compare chains in the
    SAME flag/var naming the Phase 4 registry used (FLAG_MAP{id}_EVENT{id}_SS{L}
    for self switches). Highest-priority (last) satisfiable page wins, mirroring
    RMXP's top-down page evaluation."""
    raise NotImplementedError("5.3: generate the per-page dispatcher from page conditions")


def build_warp_events(map_json: dict, resolve_map: "callable") -> list[WarpEvent]:
    """Extract code-201 transfers into warp_events. `resolve_map` turns an Uranium
    map id into a MAP_* via the MapConstantRegistry. (Note: many warps were queued
    by Phase 4 as unhandled; the geometry warp_event is the deterministic record.)"""
    raise NotImplementedError("5.3: code-201 transfers -> warp_events")


def wire_encounters(uranium_map_id: int, encounters_path: Path) -> dict | None:
    """Return the pokeemerald wild-encounter entry for this map, or None if it has
    no wild slots. Read intermediate/wild_encounters.json (keyed by Uranium id)."""
    raise NotImplementedError("5.3: wild_encounters.json[map_id] -> map.json encounter entry")
