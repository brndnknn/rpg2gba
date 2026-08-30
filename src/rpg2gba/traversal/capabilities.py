"""Per-map traversal capability classification.

Given a decoded Uranium map (`output/uranium-build/maps/Map###.json`), find
every blocked/obstacle cell that a hidden-move-style capability (Rock Smash,
Strength, Surf, Waterfall) would unblock, so a later reachability pass can
compute `blocked:<capability set>` verdicts.

Two routes by which a capability gate appears (CLAUDE.md §4.3 — reference/
scripts_dump/103__PField_HiddenMoves.rb and 002__Settings.rb are the sources
of truth for the predicates; this module does not invent thresholds):

(a) Event heads. The Ruby method that gates an obstacle event appears either
    as a script command (code 355, continued by 655) or inside a Conditional
    Branch's script-condition parameter (code 111, e.g.
    ``{"code": 111, "parameters": [12, "Kernel.pbRockSmash"]}``). Both forms
    must be scanned — a bare code-355 `pbRockSmash` head does not exhaust the
    corpus; many rocks and every code-111 boulder are gated purely through
    the branch form. Missing that form is the known trap (confirmed via
    map 96's three boulders, events 8/9/10, which carry `pbPushThisBoulder`
    only inside code-111 branches).

(b) Terrain tags (`reference/terrain_tag_map.json`, tags 0-22). Water/
    waterfall gates come ONLY from terrain tags, never from events: tags
    5 (DeepWater), 7 (Water), 17 (StillWater) -> SURF; tags 8 (Waterfall),
    9 (WaterfallCrest) -> WATERFALL.

`cut`, `flash`, and `dive` have no grant site and no obstacle surface
anywhere in the corpus scanned so far. They stay in the `Capability` enum
(the predicate table documents their real in-game gating) but are excluded
from `VERIFIED_CAPABILITIES`; asking `build_capability_map` to derive one
raises `UnverifiedCapabilityError` rather than silently returning an empty
result.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from rpg2gba.traversal.collision import (
    DEFAULT_MAPS_DIR,
    DEFAULT_TILESETS_JSON,
    TilesetArrays,
    build_tile_grid,
    load_map_json,
    load_tileset_arrays,
)
from rpg2gba.tileset_converter.layout import TileGrid, column_key

logger = logging.getLogger(__name__)


class Capability(Enum):
    """A hidden-move-style traversal capability."""

    ROCK_SMASH = "rock_smash"
    STRENGTH = "strength"
    SURF = "surf"
    WATERFALL = "waterfall"
    CUT = "cut"        # unverified: no grant site/obstacle surface in corpus
    FLASH = "flash"    # unverified: no grant site/obstacle surface in corpus
    DIVE = "dive"       # unverified: no grant site/obstacle surface in corpus


#: Capabilities this module can actually detect obstacles for, from real
#: corpus evidence (event heads for ROCK_SMASH/STRENGTH, terrain tags for
#: SURF/WATERFALL). CUT/FLASH/DIVE are real predicates (below) but have no
#: known obstacle-detection method — see `UnverifiedCapabilityError`.
VERIFIED_CAPABILITIES: frozenset[Capability] = frozenset(
    (Capability.ROCK_SMASH, Capability.STRENGTH, Capability.SURF, Capability.WATERFALL)
)


class UnverifiedCapabilityError(ValueError):
    """Raised when asked to derive obstacles for a capability with no known
    grant site/obstacle surface in the corpus (CUT, FLASH, DIVE). Detection
    for these must not be invented — fail loud instead (CLAUDE.md §4.5)."""


@dataclass(frozen=True)
class CapabilityPredicate:
    """The real player-state predicate that grants a capability, per
    reference/scripts_dump/103__PField_HiddenMoves.rb and 002__Settings.rb.
    Structured, not free text, so a later gate-evaluation pass can consume it
    directly (CLAUDE.md: model data, don't stringify it)."""

    capability: Capability
    badge_index: int
    required_move: str | None
    alternative_item: str | None
    extra_condition: str | None  # e.g. "strengthUsed"


#: BADGEFORFLASH=0, BADGEFORROCKSMASH=1, BADGEFORCUT=3, BADGEFORSTRENGTH=4,
#: BADGEFORSURF=5, BADGEFORDIVE=7, BADGEFORWATERFALL=8
#: (reference/scripts_dump/002__Settings.rb).
PREDICATES: dict[Capability, CapabilityPredicate] = {
    Capability.ROCK_SMASH: CapabilityPredicate(
        capability=Capability.ROCK_SMASH,
        badge_index=1,
        required_move="ROCKSMASH",
        alternative_item="BOXINGGLOVES",
        extra_condition=None,
    ),
    Capability.STRENGTH: CapabilityPredicate(
        capability=Capability.STRENGTH,
        badge_index=4,
        required_move="STRENGTH",
        alternative_item=None,
        extra_condition="strengthUsed",
    ),
    Capability.SURF: CapabilityPredicate(
        capability=Capability.SURF,
        badge_index=5,
        required_move="SURF",
        alternative_item=None,
        extra_condition=None,
    ),
    Capability.WATERFALL: CapabilityPredicate(
        capability=Capability.WATERFALL,
        badge_index=8,
        required_move="WATERFALL",
        alternative_item=None,
        extra_condition=None,
    ),
    Capability.CUT: CapabilityPredicate(
        capability=Capability.CUT,
        badge_index=3,
        required_move="CUT",
        alternative_item=None,
        extra_condition=None,
    ),
    Capability.FLASH: CapabilityPredicate(
        capability=Capability.FLASH,
        badge_index=0,
        required_move="FLASH",
        alternative_item=None,
        extra_condition=None,
    ),
    Capability.DIVE: CapabilityPredicate(
        capability=Capability.DIVE,
        badge_index=7,
        required_move="DIVE",
        alternative_item=None,
        extra_condition=None,
    ),
}


@dataclass(frozen=True)
class Obstacle:
    """One blocked cell and the capability that unblocks it."""

    cell: tuple[int, int]
    capability: Capability
    source: str  # "event" | "terrain"
    detail: str  # event id/name, or terrain tag number
    event_id: int | None


@dataclass
class CapabilityMap:
    """All obstacles found on one map, keyed by cell."""

    map_id: int
    obstacles: dict[tuple[int, int], Obstacle] = field(default_factory=dict)

    def capability_at(self, cell: tuple[int, int]) -> Capability | None:
        obstacle = self.obstacles.get(cell)
        return obstacle.capability if obstacle is not None else None

    def cells_for(self, capability: Capability) -> set[tuple[int, int]]:
        return {
            cell
            for cell, obstacle in self.obstacles.items()
            if obstacle.capability is capability
        }

    def capabilities_present(self) -> set[Capability]:
        return {obstacle.capability for obstacle in self.obstacles.values()}


# --- Event-head detection ---------------------------------------------------

#: Recognized Ruby heads -> capability. Order doesn't matter: the two
#: substrings never collide (`pbRockSmashRandomEncounter` contains
#: `pbRockSmash`, which is intentional — both heads gate the same capability).
#: Anything else that merely *looks* plausible (e.g. a bare `pbSurf`/`pbCut`/
#: `pbFlash` head, which real Essentials code does define) is deliberately
#: NOT in this table — those capabilities have no verified obstacle-detection
#: method (see `UnverifiedCapabilityError`), and guessing at their heads here
#: would silently fabricate detection CLAUDE.md §4.5 forbids.
_EVENT_HEAD_CAPABILITY: dict[str, Capability] = {
    "pbPushThisBoulder": Capability.STRENGTH,
    "pbRockSmash": Capability.ROCK_SMASH,
}

_SCRIPT_CODES = (355, 655)
_CONDITIONAL_BRANCH_CODE = 111


def _script_text(command: dict) -> str | None:
    """The Ruby text carried by one command, or None if it carries none.

    Code 355/655 (script/continuation): `parameters[0]` is the text. Code 111
    (Conditional Branch): a script-condition branch carries its Ruby snippet
    at `parameters[1]` (`parameters[0]` is the branch-type selector, `12` for
    a script condition — non-script conditional branches don't carry text at
    all and are correctly ignored here)."""
    code = command.get("code")
    params = command.get("parameters") or []
    if code in _SCRIPT_CODES:
        return params[0] if params and isinstance(params[0], str) else None
    if code == _CONDITIONAL_BRANCH_CODE:
        if len(params) >= 2 and isinstance(params[1], str):
            return params[1]
        return None
    return None


def _event_capability(event: dict) -> Capability | None:
    """The capability gating this event, or None if no recognized head is
    found anywhere across all of its pages/commands. An event counts once
    even if the same head appears on multiple pages or multiple times on one
    page."""
    for page in event.get("pages", []):
        for command in page.get("list", []):
            text = _script_text(command)
            if text is None:
                continue
            for head, capability in _EVENT_HEAD_CAPABILITY.items():
                if head in text:
                    return capability
    return None


def _find_event_obstacles(map_json: dict) -> list[Obstacle]:
    obstacles: list[Obstacle] = []
    for event in map_json.get("events", []):
        capability = _event_capability(event)
        if capability is None:
            continue
        cell = (event["x"], event["y"])
        obstacles.append(
            Obstacle(
                cell=cell,
                capability=capability,
                source="event",
                detail=f"{event['id']}:{event.get('name', '')}",
                event_id=event["id"],
            )
        )
    return obstacles


# --- Terrain-tag detection ---------------------------------------------------

_TERRAIN_TAG_CAPABILITY: dict[int, Capability] = {
    5: Capability.SURF,       # DeepWater
    7: Capability.SURF,       # Water
    17: Capability.SURF,      # StillWater
    8: Capability.WATERFALL,  # Waterfall
    9: Capability.WATERFALL,  # WaterfallCrest
}


def _effective_terrain_tag(terrain_tags: list[int], key: tuple[tuple[int, int], ...]) -> int:
    """The cell's effective terrain tag: the topmost (highest z) tile in `key`
    (bottom-first, per `column_key`) whose tag is nonzero wins; 0 if every
    layer's tag is 0 or `key` is empty (mirrors
    `tileset_converter.terrain_tags.TerrainTagTable.effective_tag`'s topmost-
    nonzero rule, without the opaque-cover stop — that stop only matters for
    graphics emission, not for "is this cell gated by water/waterfall?")."""
    for _z, tile_id in reversed(key):
        if 0 <= tile_id < len(terrain_tags) and terrain_tags[tile_id] != 0:
            return terrain_tags[tile_id]
    return 0


def _find_terrain_obstacles(grid: TileGrid, arrays: TilesetArrays) -> list[Obstacle]:
    obstacles: list[Obstacle] = []
    for y in range(grid.ysize):
        for x in range(grid.xsize):
            key = column_key(grid, x, y)
            tag = _effective_terrain_tag(arrays.terrain_tags, key)
            capability = _TERRAIN_TAG_CAPABILITY.get(tag)
            if capability is None:
                continue
            obstacles.append(
                Obstacle(
                    cell=(x, y),
                    capability=capability,
                    source="terrain",
                    detail=str(tag),
                    event_id=None,
                )
            )
    return obstacles


# --- Public entry point ------------------------------------------------------

def build_capability_map(
    map_id: int,
    maps_dir: Path = DEFAULT_MAPS_DIR,
    tilesets_json: Path = DEFAULT_TILESETS_JSON,
    capabilities: frozenset[Capability] | None = None,
) -> CapabilityMap:
    """Classify every obstacle cell on `map_id` by the capability that
    unblocks it.

    `capabilities` restricts which capabilities are derived (defaults to
    `VERIFIED_CAPABILITIES`, i.e. all four). Passing any capability outside
    `VERIFIED_CAPABILITIES` (CUT, FLASH, DIVE) raises
    `UnverifiedCapabilityError` immediately — there is no known corpus
    evidence to derive them from, so returning an empty set for them would
    silently look like "verified, just none present on this map" (CLAUDE.md
    §4.5: fail loud, never default silently).

    Terrain-tag obstacles (SURF/WATERFALL) are computed first, then event
    obstacles (ROCK_SMASH/STRENGTH) are applied on top — the two sources
    don't overlap in the corpus (rocks/boulders don't sit on water tiles),
    but if they ever did, the event source wins as the more specific one."""
    wanted = VERIFIED_CAPABILITIES if capabilities is None else frozenset(capabilities)
    unverified = wanted - VERIFIED_CAPABILITIES
    if unverified:
        names = ", ".join(sorted(c.value for c in unverified))
        raise UnverifiedCapabilityError(
            f"cannot derive obstacles for unverified capability(ies) {names}: "
            "no grant site or obstacle surface exists anywhere in the corpus "
            "for them; detection must not be invented (CLAUDE.md §4.5)"
        )

    obstacles: dict[tuple[int, int], Obstacle] = {}

    if Capability.SURF in wanted or Capability.WATERFALL in wanted:
        map_json = load_map_json(map_id, maps_dir)
        grid = build_tile_grid(map_json)
        arrays = load_tileset_arrays(map_json["tileset_id"], tilesets_json)
        for obstacle in _find_terrain_obstacles(grid, arrays):
            if obstacle.capability in wanted:
                obstacles[obstacle.cell] = obstacle
    else:
        map_json = load_map_json(map_id, maps_dir)

    if Capability.ROCK_SMASH in wanted or Capability.STRENGTH in wanted:
        for obstacle in _find_event_obstacles(map_json):
            if obstacle.capability in wanted:
                obstacles[obstacle.cell] = obstacle

    return CapabilityMap(map_id=map_id, obstacles=obstacles)
