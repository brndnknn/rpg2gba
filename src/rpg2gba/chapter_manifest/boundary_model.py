"""Concrete `checker.BoundaryModel` over the slice/seam growth detectors and
the chapter chain.

`checker.py` deliberately never imports `rpg2gba.slice_growth`,
`rpg2gba.seam_growth`, `rpg2gba.chapter_atlas`, or `rpg2gba.playtest` -- a
`Protocol` is the seam. This module is the thin adapter the CLI wires into
`checker.check_chapter`'s `boundary_model=` argument so
`RULE_BOUNDARY_NOT_CROSSING`/`RULE_BOUNDARY_UNCLAIMED` can actually run
instead of degrading to `RULE_BOUNDARY_MODEL_UNENFORCED`. It is the sibling
of `beat_model.py`/`archetype_model.py`/`route_model.py`, which solve the
same layering problem the same way.

It joins two independent facts a `boundary` disposition asserts, which live
in different places on purpose:

- **is this row really a forward crossing?** -- a fact about this chapter's
  own maps, derived from `slice_growth.gated_chapter_slices`/
  `find_slice_growth_events` (for `code 201` warp rows -- page rows) and
  `seam_growth.find_seam_growth_edges` (for map-connection seam rows, which
  `slice_growth` structurally cannot see -- it only scans RPG Maker event
  transfer commands, not `connections.json`). Both detectors already answer
  "does this event/seam lead to a map outside the chapter's authoring-time
  slice" -- exactly the question `is_forward_crossing` needs, re-keyed onto
  the manifest's own row-id shape (`schema.page_row_id`/`seam_row_id`)
  rather than the detectors' own `(map_id, event_id, page_indices)` /
  `(own_map_id, own_edge, target_map_id)` shapes.
- **does the arrival claim it?** -- a fact about the chapter chain
  (`chapter_atlas.binding.ChapterBinding.successor`) and the successor
  chapter's own registered beats (`playtest.chapter.load_chapter`'s
  `Chapter.beats`, each carrying a `rows` tuple -- the same `beat.rows` walk
  `playtest.archetypes.ChapterArchetypeModel` already does for the
  archetype-conformance rule).

Without this adapter the rule can still catch nothing at all about a
`boundary` disposition beyond its bare syntax -- it would always degrade to
`RULE_BOUNDARY_MODEL_UNENFORCED`.
"""
from __future__ import annotations

import logging
from pathlib import Path

from rpg2gba.chapter_atlas.binding import load_binding
from rpg2gba.playtest.chapter import Chapter, load_chapter
from rpg2gba.seam_growth import find_seam_growth_edges
from rpg2gba.slice_growth import (
    ChapterSlice,
    gated_chapter_slices,
    find_slice_growth_events,
)
from rpg2gba.tileset_converter.connections import load_connections

from .schema import page_row_id, seam_row_id

logger = logging.getLogger(__name__)

DEFAULT_MAPS_DIR = Path("output/uranium-build/maps")
DEFAULT_CONNECTIONS_JSON = Path("output/uranium-build/connections.json")


def _crossing_row_ids(
    chapter_slice: ChapterSlice,
    current_slice_ids: frozenset[int],
    *,
    maps_dir: Path,
    connections_json: Path,
) -> frozenset[str]:
    """Every manifest row id on `chapter_slice`'s own maps that either
    detector reports as a newly-visible-or-always-visible forward crossing.

    Row-id derivation is the one thing this function adds on top of the two
    detectors' own results (`CLAUDE.md` §4.3 -- neither detector has any
    reason to know the manifest's row-id convention):

    - `SliceGrowthEvent.page_indices` is every page of the event that
      carries the transfer; each page is its own row
      (`page_row_id(map_id, event_id, page_idx)`).
    - `SeamGrowthEdge` names one row per the reporting chapter's own side
      (`seam_row_id(own_map_id, own_edge, target_map_id)`), matching
      `seam_row_id`'s own doc: "seams are keyed from the crossing map's
      side."
    """
    row_ids: set[str] = set()

    events = find_slice_growth_events(chapter_slice, maps_dir, current_slice_ids)
    for event in events:
        for page_idx in event.page_indices:
            row_ids.add(page_row_id(event.map_id, event.event_id, page_idx))

    connection_rows = load_connections(connections_json)
    edges = find_seam_growth_edges(chapter_slice, connection_rows, current_slice_ids)
    for edge in edges:
        row_ids.add(seam_row_id(edge.own_map_id, edge.own_edge, edge.target_map_id))

    return frozenset(row_ids)


class ChapterBoundaryModel:
    """Satisfies `chapter_manifest.checker.BoundaryModel`.

    Built once per `check_chapter` call, from the reporting chapter's own
    crossing row ids (computed eagerly, at construction, from the two
    detectors) and its successor chapter id (from `ChapterBinding`, also
    resolved eagerly -- `successor()` is cheap, pure in-memory lookup, no
    reason to defer it). The successor's playtest module, in contrast, is
    loaded lazily and cached, because loading it is the expensive/fallible
    half (a real Python import) and not every `boundary` row necessarily
    needs it looked at more than once.
    """

    def __init__(
        self,
        chapter_id: str,
        crossing_row_ids: frozenset[str],
        successor_id: str | None,
    ) -> None:
        self._chapter_id = chapter_id
        self._crossing_row_ids = crossing_row_ids
        self._successor_id = successor_id
        self._successor_module_checked = False
        self._successor_chapter: Chapter | None = None
        self._successor_claimed_rows: frozenset[str] = frozenset()

    def is_forward_crossing(self, row_id: str) -> bool:
        return row_id in self._crossing_row_ids

    def successor_chapter_id(self) -> str | None:
        return self._successor_id

    def _ensure_successor_loaded(self) -> None:
        if self._successor_module_checked:
            return
        self._successor_module_checked = True
        if self._successor_id is None:
            return
        try:
            chapter = load_chapter(self._successor_id)
        except KeyError:
            logger.info(
                "boundary model: successor chapter %r (of %r) has no "
                "playtest module yet -- claim-checking for %r's boundary "
                "row(s) is unenforced until it does",
                self._successor_id, self._chapter_id, self._chapter_id,
            )
            return
        self._successor_chapter = chapter
        claimed: set[str] = set()
        for beat in chapter.beats:
            claimed.update(beat.rows)
        self._successor_claimed_rows = frozenset(claimed)

    def successor_has_module(self) -> bool:
        self._ensure_successor_loaded()
        return self._successor_chapter is not None

    def successor_claims(self, row_id: str) -> bool:
        self._ensure_successor_loaded()
        return row_id in self._successor_claimed_rows


def build_boundary_model(
    chapter_id: str,
    *,
    maps_dir: Path = DEFAULT_MAPS_DIR,
    connections_json: Path = DEFAULT_CONNECTIONS_JSON,
) -> ChapterBoundaryModel | None:
    """Adapter for `chapter_id`, or None when the rule cannot be enforced yet.

    Returns None -- leaving both boundary rules to degrade to
    `RULE_BOUNDARY_MODEL_UNENFORCED` -- only when `chapter_id` itself has no
    gated (`status: "built"`) slice in `reference/chapters.json`, i.e. the
    crossing-detection half has nothing to run against yet: a chapter still
    being authored has no committed, built map roster for the detectors to
    scan. That is the ordinary state of a chapter before its own §9 gate,
    not an error, and it is logged so the reason is visible in the check
    output.

    A chapter that IS gated but whose `chapters.json`/`SLICE_MAP_IDS` union
    disagrees (`slice_growth.SliceGrowthError`) is NOT that case -- the two
    §4.3 sources of truth this whole detector pair rests on have drifted,
    every result would be built on a wrong premise, and this raises through
    rather than silently returning None (CLAUDE.md §4.5).
    """
    from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS

    current_slice = frozenset(SLICE_MAP_IDS)
    slices = gated_chapter_slices(current_slice_ids=SLICE_MAP_IDS)
    slice_by_id = {s.chapter_id: s for s in slices}
    chapter_slice = slice_by_id.get(chapter_id)
    if chapter_slice is None:
        logger.info(
            "no gated chapter slice for %s -- the boundary crossing rules "
            "are unenforced; they start checking once the chapter reaches "
            "status=='built' in reference/chapters.json",
            chapter_id,
        )
        return None

    crossing_row_ids = _crossing_row_ids(
        chapter_slice, current_slice,
        maps_dir=maps_dir, connections_json=connections_json,
    )

    binding = load_binding()
    successor = binding.successor(chapter_id)
    successor_id = successor.id if successor is not None else None

    return ChapterBoundaryModel(chapter_id, crossing_row_ids, successor_id)
