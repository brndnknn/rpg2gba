"""Detector for map-connection seams that were invisible when a chapter was
authored and are crossable now (`REDERIVATION_PLAN.md` step P2b, filed as
PROJECT_TODO #91 -- the seam-side counterpart to `slice_growth`'s `code 201`
detector).

`tileset_converter.connections.build_connections` applies a frontier rule: a
`connections.json` row is only emitted once BOTH its endpoint maps are in the
build's map set (`SLICE_MAP_IDS`, or whatever id set the caller passes -- see
its own "FRONTIER RULE" docstring section). `SLICE_MAP_IDS` only ever grows as
chapters are staged, so a seam row naming one of an already-shipped chapter's
own maps and a then-unbuilt neighbour was correctly omitted at authoring time
(the connected map didn't exist yet) but silently becomes a *live* scroll seam
the moment a later chapter stages the far side -- the row itself never
changes and nothing re-examines it.

This is the exact class of bug `slice_growth.py` cannot see (it scans `code
201` warp commands inside RPG Maker events; a map-connection seam is a
different mechanism entirely, declared in `connections.json` and sometimes
realised as a synthetic arrow-warp pair via `reference/seam_warps.json`
instead of an actual scrolling connection -- see
`tileset_converter.seam_warps`). It has already produced one real bug: CH03's
beat B25 asserted the north edge of Kevlar Town toward what was then-unbuilt
Route 2 was "a clean impassable wall", and had to be reconciled by hand on
2026-08-26 once Route 2 (CH04) was staged and the `connections.json` row
`[31, "N", 11, 35, "S", 0]` came alive.

This module answers, per gated (`status: "built"`) chapter: which
`connections.json` rows name one of that chapter's own maps and a map that
was out-of-slice when the chapter was authored and is in-slice in the
current `SLICE_MAP_IDS`?

Chapter-slice bookkeeping is **not** reimplemented here -- `CLAUDE.md` §4.3,
one source of truth per concept. `slice_growth.gated_chapter_slices` already
derives each gated chapter's authoring-time slice (the cumulative union of
CH01..CHnn's own maps) and fails loud if that union disagrees with
`SLICE_MAP_IDS`; this module reuses it verbatim rather than re-deriving the
same fact a second way. Likewise, row parsing/validation is delegated to
`tileset_converter.connections.load_connections`/`parse_connections`, and the
arrow-warp-realised-instead-of-a-real-connection distinction is delegated to
`tileset_converter.seam_warps.load_seam_warps`/`suppressed_pairs` -- this
module only adds the historical (authoring-time slice) dimension neither of
those has any reason to know about.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from rpg2gba.slice_growth import ChapterSlice, gated_chapter_slices
from rpg2gba.tileset_converter.connections import ConnectionRow, load_connections
from rpg2gba.tileset_converter.seam_warps import (
    DEFAULT_SEAM_WARPS_PATH,
    load_seam_warps,
    suppressed_pairs,
)

logger = logging.getLogger(__name__)

DEFAULT_CHAPTERS_JSON = Path("reference/chapters.json")
DEFAULT_CONNECTIONS_JSON = Path("output/uranium-build/connections.json")


class SeamGrowthError(RuntimeError):
    """A source-of-truth file this detector reads is malformed or the sources
    contradict each other (`reference/seam_warps.json` naming a map pair that
    `connections.json` never declares). Raised instead of silently guessing --
    this detector's whole premise is "the seam data on disk is the seam data
    in the ROM," so a contradiction there makes every result below suspect.
    """


@dataclass(frozen=True)
class SeamGrowthEdge:
    """One `connections.json` row where `own_map_id` (one of the reporting
    chapter's own maps) shares a seam with `target_map_id`, and that target
    was out-of-slice when the chapter was authored and is in-slice now.

    `own_edge`/`own_offset` and `target_edge`/`target_offset` are the row's
    raw Essentials-convention fields (`connections.ConnectionRow`'s own
    fields, re-oriented so `own_*` always describes the reporting chapter's
    side) -- not yet in pokeemerald's `offset` convention; see
    `connections.py`'s module docstring for that derivation.

    `realized_as` is `"arrow_warp"` if `reference/seam_warps.json` replaces
    this row's real scroll connection with a synthetic arrow-warp pair
    (`tileset_converter.seam_warps`), else `"connection"`. Either way the
    seam becomes crossable the moment both maps are staged -- this field is
    informational, not a filter.
    """

    own_map_id: int
    own_edge: str
    own_offset: int
    target_map_id: int
    target_edge: str
    target_offset: int
    realized_as: str  # "connection" | "arrow_warp"


@dataclass
class ChapterSeamGrowthReport:
    """Everything found for one gated chapter."""

    chapter_id: str
    own_map_ids: tuple[int, ...]
    authored_slice_size: int
    current_slice_size: int
    edges: list[SeamGrowthEdge] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.edges

    def format(self) -> str:
        if not self.edges:
            return f"{self.chapter_id}: clean -- no newly-crossable out-of-slice seams"
        rows = sorted(self.edges, key=lambda e: (e.own_map_id, e.target_map_id))
        lines = [
            f"{self.chapter_id}: {len(rows)} newly-crossable seam(s) "
            f"(authored against {self.authored_slice_size} maps, now {self.current_slice_size}):"
        ]
        for e in rows:
            lines.append(
                f"  Map{e.own_map_id:03d} ({e.own_edge}@{e.own_offset}) "
                f"<-> Map{e.target_map_id:03d} ({e.target_edge}@{e.target_offset}) "
                f"[{e.realized_as}]"
            )
        return "\n".join(lines)


def _realized_as_map(seam_warps_json: Path) -> dict[frozenset[int], str]:
    """`{pair_key: "arrow_warp"}` for every seam `reference/seam_warps.json`
    declares. Absent file -> empty map (every row is a plain connection) --
    `seam_warps.json` is optional infrastructure, not a hard dependency of
    this detector."""
    if not seam_warps_json.is_file():
        return {}
    seams = load_seam_warps(seam_warps_json)
    return {pair: "arrow_warp" for pair in suppressed_pairs(seams)}


def _check_seam_warps_reference_real_rows(
    connection_rows: list[ConnectionRow], realized_as: dict[frozenset[int], str]
) -> None:
    row_pairs = {row.pair_key for row in connection_rows}
    undeclared = set(realized_as) - row_pairs
    if undeclared:
        raise SeamGrowthError(
            "reference/seam_warps.json declares an arrow-warp replacement for "
            f"map pair(s) {[sorted(p) for p in undeclared]}, but connections.json "
            "has no row for them -- nothing to suppress (contradictory "
            "declaration between the two source-of-truth files)"
        )


def find_seam_growth_edges(
    chapter: ChapterSlice,
    connection_rows: list[ConnectionRow],
    current_slice_ids: frozenset[int],
    realized_as: dict[frozenset[int], str] | None = None,
) -> list[SeamGrowthEdge]:
    """Every `connections.json` row naming one of `chapter`'s own maps and a
    map that was outside `chapter.authoring_slice` and is inside
    `current_slice_ids` now.

    A row whose *other* endpoint also belongs to `chapter`'s own maps (an
    internal seam introduced by the same chapter) is not growth -- `own_map_ids`
    is a subset of `authoring_slice` by construction (`gated_chapter_slices`),
    so the "out of authoring_slice" test excludes it naturally. A row whose
    other endpoint is still out-of-slice today (not yet built by any chapter)
    is not growth either -- it is exactly as invisible as it was at authoring
    time."""
    realized_as = realized_as or {}
    own = set(chapter.own_map_ids)
    edges: list[SeamGrowthEdge] = []
    for row in connection_rows:
        if row.map_a in own:
            own_id, own_edge, own_offset = row.map_a, row.edge_a, row.offset_a
            other_id, other_edge, other_offset = row.map_b, row.edge_b, row.offset_b
        elif row.map_b in own:
            own_id, own_edge, own_offset = row.map_b, row.edge_b, row.offset_b
            other_id, other_edge, other_offset = row.map_a, row.edge_a, row.offset_a
        else:
            continue

        if other_id in chapter.authoring_slice:
            continue  # already visible at authoring time
        if other_id not in current_slice_ids:
            continue  # still not built; not "growth" yet

        edges.append(
            SeamGrowthEdge(
                own_map_id=own_id,
                own_edge=own_edge,
                own_offset=own_offset,
                target_map_id=other_id,
                target_edge=other_edge,
                target_offset=other_offset,
                realized_as=realized_as.get(row.pair_key, "connection"),
            )
        )
    return edges


def detect_seam_growth(
    chapters_json: Path = DEFAULT_CHAPTERS_JSON,
    connections_json: Path = DEFAULT_CONNECTIONS_JSON,
    seam_warps_json: Path = DEFAULT_SEAM_WARPS_PATH,
    *,
    current_slice_ids: list[int] | None = None,
    only_chapters: set[str] | None = None,
) -> list[ChapterSeamGrowthReport]:
    """The full detector: for every gated chapter (or the subset named in
    `only_chapters`), report every newly-crossable out-of-slice-then/
    in-slice-now map-connection seam touching that chapter's own maps.

    This is the whole point of the module -- see the module docstring and
    `REDERIVATION_PLAN.md` step P2b (PROJECT_TODO #91)."""
    if current_slice_ids is None:
        from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS

        current_slice_ids = SLICE_MAP_IDS
    current_slice = frozenset(current_slice_ids)

    slices = gated_chapter_slices(chapters_json, current_slice_ids=current_slice_ids)
    if only_chapters is not None:
        slices = [s for s in slices if s.chapter_id in only_chapters]

    connection_rows = load_connections(connections_json)
    realized_as = _realized_as_map(seam_warps_json)
    _check_seam_warps_reference_real_rows(connection_rows, realized_as)

    reports = []
    for chapter in slices:
        edges = find_seam_growth_edges(chapter, connection_rows, current_slice, realized_as)
        reports.append(
            ChapterSeamGrowthReport(
                chapter_id=chapter.chapter_id,
                own_map_ids=chapter.own_map_ids,
                authored_slice_size=len(chapter.authoring_slice),
                current_slice_size=len(current_slice),
                edges=edges,
            )
        )
    return reports


__all__ = [
    "ChapterSeamGrowthReport",
    "SeamGrowthEdge",
    "SeamGrowthError",
    "detect_seam_growth",
    "find_seam_growth_edges",
]


# --- CLI ---------------------------------------------------------------------
#
# The command itself is defined once, in `pipeline.py` as `rpg2gba seam-growth`
# (§4.3 -- one definition, not two), mirroring `slice_growth.py`. This module
# form just delegates, so both invocations are the same code path.

if __name__ == "__main__":  # pragma: no cover
    from rpg2gba.pipeline import seam_growth_cmd

    raise SystemExit(seam_growth_cmd(standalone_mode=True))
