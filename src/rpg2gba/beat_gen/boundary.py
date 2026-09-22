"""Chapter-boundary rows (C6 part two; REDERIVATION_PLAN.md §10 R2/R3).

A warp whose destination is on no map of a chapter's chain is a boundary:
the far side belongs to a chapter not built yet. Two stages care:

- The chapter being LEFT keeps the crossing page (as a `warp_beat(boundary=
  True)` beat that stops at the edge, `adapt.is_boundary_warp`) and hands
  every OTHER page and arm of that event to its successor. Boundary-ness is
  a property of the event, not the page (R3): an arrival autorun that nudges
  the player off the landing cell can only fire on the way back in.
- The chapter being ENTERED claims its predecessor's events that warp onto
  its own maps, every page and arm of them (R2: "the crossing belongs to the
  chapter being opened"). Only this chapter's ROM stages the far side, so
  only its walk can cross them.

Destinations come from each row's floor `warp` assertion, and chapter
membership from `reference/chapters.json` (§4.3) -- the same two sources
`adapt.is_boundary_warp` reads, so the two can't disagree.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from rpg2gba.beat_floor.assertion import RowFloor
from rpg2gba.beat_gen.plan import Elsewhere, Selection
from rpg2gba.chapter_manifest.schema import ManifestRow, parse_row_id


def warp_destinations(rows: Sequence[ManifestRow], floors: Mapping[str, RowFloor]
                      ) -> dict[str, frozenset[int]]:
    """{page row id: destination maps} for every page whose floor carries a
    warp. A page can warp to more than one map (a scripted transfer in each
    branch, CH01's map049/ev021/p0); it is a crossing if any of them is."""
    out: dict[str, frozenset[int]] = {}
    for row in rows:
        if row.kind != "page" or row.row_id not in floors:
            continue
        dests = frozenset(a.param("map_id") for a in floors[row.row_id].assertions
                          if a.kind == "warp")
        if dests:
            out[row.row_id] = dests
    return out


def _event_key(row_id: str) -> tuple[int, int] | None:
    return parse_row_id(row_id).event_key


def split_outbound(
    selection: Selection,
    floors: Mapping[str, RowFloor],
    chain_maps: frozenset[int],
    successor_id: str | None,
) -> Selection:
    """`selection` with every owned row of a boundary event, except the
    crossing page itself, moved to `Elsewhere("boundary", successor_id)`.
    The crossing page stays owned: it gets the stop-at-the-edge beat."""
    dests = warp_destinations(selection.owned, floors)
    crossings = {rid for rid, maps in dests.items() if maps - chain_maps}
    events = {_event_key(rid) for rid in crossings}
    owned: list[ManifestRow] = []
    handed: list[Elsewhere] = []
    for row in selection.owned:
        if row.row_id not in crossings and _event_key(row.row_id) in events:
            handed.append(Elsewhere(row.row_id, "boundary", successor_id))
        else:
            owned.append(row)
    if not handed:
        return selection
    return Selection(owned=tuple(owned), refusals=selection.refusals,
                     elsewhere=selection.elsewhere + tuple(handed))


def inbound_rows(
    pred_rows: Sequence[ManifestRow],
    pred_floors: Mapping[str, RowFloor],
    chapter_maps: frozenset[int],
    pred_chain_maps: frozenset[int],
) -> tuple[ManifestRow, ...]:
    """Every predecessor row (page or arm, manifest order) on an event with
    a page that warps onto one of `chapter_maps` from outside the
    predecessor's own chain -- the crossings this chapter opens."""
    dests = warp_destinations(pred_rows, pred_floors)
    events = {_event_key(rid) for rid, maps in dests.items()
              if (maps & chapter_maps) - pred_chain_maps}
    return tuple(r for r in pred_rows
                 if r.kind in ("page", "branch") and _event_key(r.row_id) in events)
