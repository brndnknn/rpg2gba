"""Concrete `checker.ApproachModel` over the offline traversal graph.

`checker.py` deliberately never imports `traversal` (CLAUDE.md §4.3 -- the
checker judges rules, not graphs; a `Protocol` is the seam). This module is
the thin adapter the CLI wires into `checker.check_chapter`'s `approach=`
argument so `RULE_BLOCKED_MISSED_ASSERTION` can actually run instead of
degrading to `RULE_APPROACH_MODEL_UNENFORCED` on every `blocked:` row.

The question this model answers is reachability-from-entry, not local
collision-openness: "starting from this chapter's registered start cell, with
no field-move capability held, can the player reach any tile orthogonally
adjacent to this event?" That is exactly the APPROACH question --
`reachability.derive_blocked_verdict_for_event(..., require_clearing=False)
.reachable_now` -- deliberately not the CLEARING question
`generator._reachability_requires` asks with `require_clearing=True` to
populate `requires[]` (backlog #95): this model is asking whether the
player can walk up and press A, which is answered by an open approach tile
alone, not by whether an obstacle sitting on the event's own tile has been
cleared. A prior version of this model asked
a purely LOCAL question (is a neighbouring tile collision-open) and it was
wrong: local walkability answers True across an entire open outdoor room
whether or not the player can actually get into that room, which fired the
rule on all 17 CH04 `north_of_rockslide_gate` rows -- floor that is only
locally open, behind rocks the player has not crossed yet.
"""
from __future__ import annotations

import logging
from pathlib import Path

from rpg2gba.traversal.capabilities import CapabilityMap
from rpg2gba.traversal.collision import (
    DEFAULT_MAPS_DIR,
    DEFAULT_TILESETS_JSON,
    load_map_json,
)
from rpg2gba.traversal.graph import MapGraph
from rpg2gba.traversal.reachability import derive_blocked_verdict_for_event_from_starts

from .generator import _build_reachability_context
from .schema import ManifestRow

logger = logging.getLogger(__name__)

Cell = tuple[int, int]
_Context = tuple[MapGraph, CapabilityMap, frozenset[Cell]]


class GraphApproachModel:
    """`has_walkable_approach(row)`: "can the player, starting from this
    chapter's registered entry cell and holding no field-move capability,
    reach a tile orthogonally adjacent to this event RIGHT NOW" -- Q3
    decision 3's "walk up to it and press A" read literally: "walk up" means
    from where the player actually is, not "some neighbouring tile happens
    to be floor".

    Reuses `reachability.derive_blocked_verdict_for_event` wholesale --
    same BFS, same capability corrections, same (graph, capability_map,
    start) triple `generator._build_reachability_context` already builds for
    `requires[]` -- rather than reimplementing any part of it (CLAUDE.md
    §4.3). `.reachable_now` is exactly this model's answer when it can
    answer at all. Called with `require_clearing=False`: "walk up to it and
    press A" is the approach question, not the clearing question -- an
    obstacle event that is fully approachable but not yet cleared still
    lets the player walk up and interact (that's what triggers the
    Rock-Smash prompt in the first place), so demanding clearing here would
    misanswer this model's actual question.

    WHAT THIS TRUSTS, so a surprising answer is diagnosable rather than
    mysterious:

    * Elevation is PERMANENTLY UNMODELLED in `MapGraph` (its own module
      docstring) -- a cliff-rim tile reads walkable, and reachability
      computed on top of it inherits that gap. A `RULE_BLOCKED_MISSED_
      ASSERTION` finding that looks wrong at a cliff edge is `MapGraph`'s
      own documented, accepted limitation, not a bug here.
    * Obstacle events ARE now accounted for, unlike a plain collision read:
      `capabilities.CapabilityMap` tags event-source obstacles (rocks,
      boulders) and terrain-source obstacles (surf water, waterfall), and
      `reachability.py`'s BFS applies both correction directions uniformly
      to every stepped-to cell (its own module docstring) -- an
      uncleared sibling rock flips an otherwise-collision-open cell to
      blocked, exactly the gap the earlier local-only version of this model
      could not see and this one closes.
    * Held capabilities are always the empty set here (`reachable_now`
      answers "with nothing held") -- this model never asks "reachable
      WITH rock_smash", only "reachable right now, unaided". That is
      deliberate: the rule this feeds asks whether a negative beat can be
      written TODAY, not after some future chapter grants a capability.

    Gated by the same registry `generator._build_reachability_context` uses
    for reachability-derived `requires[]` (`generator._CHAPTER_MAP_START_CELLS`):
    a map absent from it answers `None` (unanswerable) for every row on it.
    One gate for "is this map's traversal picture vetted enough to comment
    on", not two.
    """

    def __init__(
        self,
        chapter_id: str,
        maps_dir: Path = DEFAULT_MAPS_DIR,
        tilesets_json: Path = DEFAULT_TILESETS_JSON,
    ) -> None:
        self._chapter_id = chapter_id
        self._maps_dir = maps_dir
        self._tilesets_json = tilesets_json
        self._contexts: dict[int, _Context | None] = {}
        self._event_cells: dict[int, dict[int, Cell]] = {}

    def _context_for(self, map_id: int) -> _Context | None:
        if map_id not in self._contexts:
            self._contexts[map_id] = _build_reachability_context(
                self._chapter_id, map_id, self._maps_dir, self._tilesets_json)
        return self._contexts[map_id]

    def _event_cell(self, map_id: int, event_id: int) -> Cell | None:
        if map_id not in self._event_cells:
            try:
                map_json = load_map_json(map_id, self._maps_dir)
            except FileNotFoundError:
                logger.warning(
                    "approach model: no decoded map data for map %03d; cannot "
                    "answer has_walkable_approach for any row on it", map_id,
                )
                self._event_cells[map_id] = {}
            else:
                self._event_cells[map_id] = {
                    event["id"]: (event["x"], event["y"])
                    for event in map_json.get("events", [])
                }
        return self._event_cells[map_id].get(event_id)

    def has_walkable_approach(self, row: ManifestRow) -> bool | None:
        """See the class docstring for what True/False/None each mean."""
        if row.kind != "page" or row.event_id is None:
            return None  # a seam row has no event cell to test
        context = self._context_for(row.map_id)
        if context is None:
            return None  # map not in generator._CHAPTER_MAP_START_CELLS
        graph, capability_map, starts = context
        event_cell = self._event_cell(row.map_id, row.event_id)
        if event_cell is None:
            return None  # event vanished from the decoded map data
        verdict = derive_blocked_verdict_for_event_from_starts(
            graph, capability_map, starts, event_cell, require_clearing=False,
        )
        return verdict.reachable_now
